"""Task 4/Task 9 route, state, Gate, and restart execution-context contracts."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.models.provider_cost import ProviderCostContractError
from src.pipeline.generation_policy import (
    DEFERRED_GENERATION_CONTROL_KEYS,
    EffectiveGenerationPolicy,
    GenerationScenario,
    bind_effective_generation_policy,
    reset_effective_generation_policy,
)
from src.services.provider_execution import (
    PROVIDER_EXECUTION_CONFIG_KEY,
    ProviderExecutionService,
    bind_provider_execution_context,
    get_provider_execution_context,
    project_provider_execution_context,
    reset_provider_execution_context,
)
from src.storage import db as db_module
from src.storage.provider_cost_repository import ProviderCostRepository

TENANT_ID = "tenant-provider-routes"
POLICY_VERSION = "generation-safety.v2"


def _install_sqlite_connection(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_pg_available", False)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)


@pytest.fixture
def sqlite_route_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "provider-route-context.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite_connection(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def _execution_service() -> ProviderExecutionService:
    return ProviderExecutionService(
        repository=ProviderCostRepository(require_postgres=False),
        server_cap_usd_nanos=100_000_000,
    )


def _generation_policy(scenario: GenerationScenario = "s1") -> EffectiveGenerationPolicy:
    return EffectiveGenerationPolicy(
        tenant_id=TENANT_ID,
        scenario=scenario,
        provider_submit_allowed=True,
        enable_media_synthesis=False,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )


@pytest.mark.asyncio
async def test_steprunner_persists_only_safe_bound_execution_projection(
    sqlite_route_db: sqlite3.Connection,
    isolated_state_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    context = await _execution_service().initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id="scenario_s1_context_001",
        scenario_or_resource_type="s1",
        generation_policy_version=POLICY_VERSION,
    )
    generation_token = bind_effective_generation_policy(_generation_policy())
    execution_token = bind_provider_execution_context(context)
    try:
        manager = PipelineStateManager(use_pg=False)
        label = await StepRunner(manager).init_state(
            config={"tenant_id": TENANT_ID},
            mode="auto",
            label="scenario_s1_context_001",
            scenario="s1",
        )
    finally:
        reset_provider_execution_context(execution_token)
        reset_effective_generation_policy(generation_token)

    state = await manager.load(label)
    assert state is not None
    assert state["tenant_id"] == TENANT_ID
    projection = state["config"][PROVIDER_EXECUTION_CONFIG_KEY]
    assert projection == project_provider_execution_context(context)
    assert "account_id" not in projection
    assert "effective_cap_usd_nanos" not in projection

    seen: list[str] = []

    async def provider_free_step(
        self: Any,
        step_name: str,
        run_state: dict[str, Any],
    ) -> dict[str, Any]:
        del self, run_state
        rebound = get_provider_execution_context()
        assert rebound is not None
        seen.append(rebound.account_id)
        from src.services.provider_execution import get_provider_operation_scope

        operation_scope = get_provider_operation_scope()
        assert operation_scope is not None
        assert operation_scope.scope_id == "s1.strategy"
        return {"step": step_name, "provider_call": False}

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", provider_free_step)
    restarted = await StepRunner(manager).run_step(label, "strategy")
    assert restarted["steps"]["strategy"]["status"] == "done"
    assert seen == [context.account_id]
    assert get_provider_execution_context() is None


@pytest.mark.asyncio
async def test_steprunner_rejects_client_forged_projection_without_bound_context(
    sqlite_route_db: sqlite3.Connection,
    isolated_state_dir: Path,
) -> None:
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    generation_token = bind_effective_generation_policy(_generation_policy())
    try:
        with pytest.raises(ProviderCostContractError) as exc_info:
            await StepRunner(PipelineStateManager(use_pg=False)).init_state(
                config={
                    "tenant_id": TENANT_ID,
                    PROVIDER_EXECUTION_CONFIG_KEY: {
                        "version": "provider-execution.v1",
                        "budget_job_kind": "canonical",
                        "budget_job_id": "client-forged",
                    },
                },
                mode="auto",
                scenario="s1",
            )
    finally:
        reset_effective_generation_policy(generation_token)
    assert exc_info.value.code == "provider_execution_context_missing"


@pytest.mark.asyncio
async def test_restart_tamper_fails_before_pipeline_construction(
    sqlite_route_db: sqlite3.Connection,
    isolated_state_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import _SCENARIO_CONFIGS, StepRunner

    context = await _execution_service().initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id="scenario_s1_tamper_001",
        scenario_or_resource_type="s1",
        generation_policy_version=POLICY_VERSION,
    )
    policy_token = bind_effective_generation_policy(_generation_policy())
    context_token = bind_provider_execution_context(context)
    manager = PipelineStateManager(use_pg=False)
    try:
        label = await StepRunner(manager).init_state(
            config={"tenant_id": TENANT_ID},
            mode="auto",
            label="scenario_s1_tamper_001",
            scenario="s1",
        )
    finally:
        reset_provider_execution_context(context_token)
        reset_effective_generation_policy(policy_token)

    state = await manager.load(label)
    assert state is not None
    state["config"][PROVIDER_EXECUTION_CONFIG_KEY]["budget_job_id"] = "scenario_s1_forged_account"
    await manager.save(label, state)
    original = _SCENARIO_CONFIGS["s1"]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s1",
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    failed = await StepRunner(manager).run_step(label, "strategy")

    assert failed["steps"]["strategy"]["status"] == "error"
    assert failed["pipeline_degraded"] is True
    assert "provider_execution_context_missing" in failed["errors"][0]
    assert get_provider_execution_context() is None


def test_client_authority_keys_are_rejected_by_generation_request_normalizer() -> None:
    assert {
        "provider_execution_context",
        "provider_account_id",
        "budget_job_kind",
        "budget_job_id",
        "effective_cap_usd_nanos",
        "trusted_authorization_ref",
        "regeneration_epoch",
    } <= DEFERRED_GENERATION_CONTROL_KEYS


@pytest.mark.asyncio
async def test_fast_registry_keeps_internal_projection_out_of_public_status(
    sqlite_route_db: sqlite3.Connection,
) -> None:
    from src.tasks import fast_task_registry

    context = await _execution_service().initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id="fast_context_registry_001",
        scenario_or_resource_type="fast",
        generation_policy_version=POLICY_VERSION,
    )
    projection = project_provider_execution_context(context)

    release = asyncio.Event()

    async def pending() -> dict[str, bool]:
        await release.wait()
        return {"success": True}

    task = asyncio.create_task(pending())
    try:
        task_id = fast_task_registry.register_fast_task(
            task,
            task_id="fast_context_registry_001",
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
            provider_execution_projection=projection,
        )
        internal = fast_task_registry.get_fast_task_execution_projection(
            task_id,
            tenant_id=TENANT_ID,
        )
        public = fast_task_registry.get_fast_task(task_id, tenant_id=TENANT_ID)
        assert internal == projection
        assert public is not None
        assert PROVIDER_EXECUTION_CONFIG_KEY not in public
        assert "account_id" not in repr(public)
        assert "effective_cap_usd_nanos" not in repr(public)
    finally:
        release.set()
        await task
        fast_task_registry._fast_tasks.clear()


def _assert_execution_before_provider_capable_work(
    function: Any,
    first_provider_marker: str,
) -> None:
    source = inspect.getsource(function)
    marker = "initialize_and_bind_provider_execution_context"
    assert marker in source
    assert source.index(marker) < source.index(first_provider_marker)


def test_canonical_async_routes_initialize_context_after_owner_before_provider_work() -> None:
    from src.routers import scenario

    fast_source = inspect.getsource(scenario._fast_submit_validated)
    assert fast_source.index("if not claim.is_owner") < fast_source.index(
        "initialize_and_bind_provider_execution_context"
    )
    _assert_execution_before_provider_capable_work(
        scenario._fast_submit_validated,
        "_inject_api_keys",
    )

    scenario_source = inspect.getsource(scenario._submit_scenario_validated)
    assert scenario_source.index("if not claim.is_owner") < scenario_source.index(
        "initialize_and_bind_provider_execution_context"
    )
    _assert_execution_before_provider_capable_work(
        scenario._submit_scenario_validated,
        "_inject_api_keys",
    )
    assert "budget_job_id=task_id" in fast_source
    assert "budget_job_id=label" in scenario_source


@pytest.mark.parametrize(
    "function_name",
    [
        "run_s1_product_direct",
        "run_s2_brand_campaign",
        "run_s3_influencer_remix",
        "run_s4_live_shoot",
        "run_s5_brand_vlog",
        "start_s1_pipeline",
        "fast_generate",
    ],
)
def test_direct_routes_create_server_compatibility_identity_before_provider_work(
    function_name: str,
) -> None:
    from src.routers import scenario

    function = getattr(scenario, function_name)
    source = inspect.getsource(function)
    assert "new_compatibility_job_id" in source
    _assert_execution_before_provider_capable_work(function, "_inject_api_keys")
    initialization = source.split("_inject_api_keys", maxsplit=1)[0]
    assert "output_label" not in initialization


@pytest.mark.asyncio
async def test_direct_fast_http_uses_fresh_compatibility_accounts_not_artifact_ids(
    sqlite_route_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.services import fast_mode

    captured: list[tuple[str, str, str]] = []

    class FakeFastService:
        async def generate(self, **kwargs: Any) -> dict[str, Any]:
            context = get_provider_execution_context()
            assert context is not None
            captured.append(
                (
                    context.budget_job_id,
                    context.account_id,
                    kwargs["artifact_run_id"],
                )
            )
            return {
                "status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
            }

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/fast/generate",
                headers=auth_headers,
                json={
                    "user_prompt": "fixture",
                    "duration": 10,
                    "enable_tts": False,
                },
            )
            for _ in range(2)
        ]

    assert [response.status_code for response in responses] == [200, 200]
    assert len({job_id for job_id, _account_id, _artifact_id in captured}) == 2
    assert len({account_id for _job_id, account_id, _artifact_id in captured}) == 2
    assert all(job_id.startswith("compat_") for job_id, _account_id, _artifact_id in captured)
    assert all(
        artifact_id.startswith("fast_generate_") and artifact_id != job_id
        for job_id, _account_id, artifact_id in captured
    )
    from src.services.provider_execution import get_provider_operation_scope

    assert get_provider_operation_scope() is None
    rows = sqlite_route_db.execute(
        "SELECT job_id FROM job_budget_accounts WHERE tenant_id = ? AND job_kind = ? AND scenario_or_resource_type = ?",
        ("default", "compatibility", "fast"),
    ).fetchall()
    assert {row["job_id"] for row in rows} == {job_id for job_id, _account_id, _artifact_id in captured}
    for response in responses:
        public = repr(response.json()).lower()
        assert "account_id" not in public
        assert "usd_nanos" not in public


@pytest.mark.asyncio
async def test_direct_fast_account_failure_precedes_provider_service_construction(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.routers import scenario
    from src.services import fast_mode

    calls: list[str] = []

    async def fail_account(**_kwargs: Any) -> None:
        calls.append("account")
        raise ProviderCostContractError(
            "provider_cost_store_unavailable",
            "fixture account store unavailable",
        )

    def forbidden_service() -> None:
        calls.append("provider-service")
        raise AssertionError("provider service must not be constructed")

    monkeypatch.setattr(
        scenario,
        "initialize_and_bind_provider_execution_context",
        fail_account,
    )
    monkeypatch.setattr(fast_mode, "get_fast_mode_service", forbidden_service)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/generate",
            headers=auth_headers,
            json={
                "user_prompt": "fixture",
                "duration": 10,
                "enable_tts": False,
            },
        )

    assert response.status_code == 500
    assert calls == ["account"]


def test_legacy_pipeline_reuses_server_thread_id_before_translation() -> None:
    from src.routers.pipeline import start_pipeline

    source = inspect.getsource(start_pipeline)
    marker = "initialize_and_bind_provider_execution_context"
    assert "budget_job_id=thread_id" in source
    assert source.index(marker) < source.index("_inject_api_keys")
    assert source.index(marker) < source.index("product_catalog = await translate_catalog_to_english")


def test_step_runner_and_gate_manager_bind_persisted_context_before_construction() -> None:
    from src.pipeline import gate_manager, step_runner

    runner_source = inspect.getsource(step_runner.StepRunner._execute_step)
    assert "persisted_provider_execution_scope" in runner_source
    assert runner_source.index("persisted_provider_execution_scope") < runner_source.index(
        "pipeline = pipeline_class()"
    )

    for function in (
        gate_manager.generate_candidates,
        gate_manager.regenerate_candidate,
    ):
        source = inspect.getsource(function)
        assert "persisted_provider_execution_scope" in source
        assert source.index("persisted_provider_execution_scope") < source.index("SkillRegistry().execute")


def test_regeneration_persists_epoch_before_execution_or_future_ordinal_work() -> None:
    from src.pipeline import gate_manager
    from src.pipeline.step_runner import StepRunner

    step_source = inspect.getsource(StepRunner.regenerate_step)
    assert "persist_trusted_regeneration_epoch" in step_source
    assert step_source.index("persist_trusted_regeneration_epoch") < step_source.index("self._execute_step")

    gate_source = inspect.getsource(gate_manager.regenerate_candidate)
    assert "persist_trusted_regeneration_epoch" in gate_source
    assert gate_source.index("persist_trusted_regeneration_epoch") < gate_source.index("SkillRegistry().execute")


def test_authorized_live_harness_validates_exact_authority_before_submitter_construction() -> None:
    from src.pipeline.authorized_live_harness import (
        AuthorizedLiveHarnessReport,
        run_authorized_live_harness,
    )

    source = inspect.getsource(run_authorized_live_harness)
    assert "_load_strict_budget_authorization" in source
    assert "execution_context_initializer" in source
    assert source.index("build_token_smoke_preflight_report") < source.index("_load_strict_budget_authorization")
    assert source.index("_load_strict_budget_authorization") < source.index(
        "execution_context_initializer(job_specs, authorization)"
    )
    assert source.index("execution_context_initializer(job_specs, authorization)") < source.index("submitter_factory()")
    report_schema = repr(AuthorizedLiveHarnessReport.model_json_schema()).lower()
    assert "usd_nanos" not in report_schema
    assert "account_id" not in report_schema


def test_pipeline_and_scenario_http_mounts_restore_request_execution_context() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "api.py").read_text()

    assert "from src.services.provider_execution import provider_execution_request_scope" in source
    assert source.count("Depends(provider_execution_request_scope)") == 2


def test_task9_operation_scope_registry_is_finite_and_slot_bound() -> None:
    from src.services.provider_execution import (
        build_provider_operation_instance,
        resolve_provider_operation_scope,
    )

    scope = resolve_provider_operation_scope("s1", "scripts")
    assert scope.version == "provider-operation-scope.v1"
    assert scope.scenario == "s1"
    assert scope.step == "scripts"
    assert scope.catalog_operation == "chat_completion"
    assert scope.logical_operation_template == "s1.scripts"
    assert build_provider_operation_instance(scope, slot="candidate.standard") == (
        "s1.scripts.candidate.standard"
    )

    with pytest.raises(ProviderCostContractError) as unknown:
        resolve_provider_operation_scope("s1", "client-controlled-step")
    assert unknown.value.code == "provider_cost_rule_unavailable"

    with pytest.raises(ProviderCostContractError) as wildcard:
        build_provider_operation_instance(scope, slot="../client-ordinal")
    assert wildcard.value.code == "provider_cost_rule_unavailable"

    with pytest.raises(ProviderCostContractError) as client_slot:
        build_provider_operation_instance(scope, slot="client.elevated")
    assert client_slot.value.code == "provider_cost_rule_unavailable"

    with pytest.raises(ProviderCostContractError) as unbounded:
        build_provider_operation_instance(scope, slot="segment.64")
    assert unbounded.value.code == "provider_cost_rule_unavailable"


@pytest.mark.asyncio
async def test_task9_skill_registry_overrides_client_operation_scope() -> None:
    from src.services.provider_execution import (
        bind_provider_operation_scope,
        reset_provider_operation_scope,
        resolve_provider_operation_scope,
    )
    from src.skills.base import SkillCallable, SkillResult
    from src.skills.registry import SkillRegistry

    captured: list[dict[str, Any]] = []

    class CaptureSkill(SkillCallable):
        name = "task9-capture"
        description = "Task 9 fixture"
        max_retries = 1

        async def execute(self, params: dict[str, Any]) -> SkillResult:
            captured.append(params)
            return SkillResult(success=True, data={"ok": True})

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            return [] if params else ["params required"]

        def validate_output(self, data: Any) -> list[str]:
            return []

        def fallback(self, params: dict[str, Any]) -> SkillResult:
            return SkillResult(success=False, error="fallback must not run")

    registry = SkillRegistry()
    registry._skills["task9-capture"] = CaptureSkill()
    token = bind_provider_operation_scope(resolve_provider_operation_scope("s2", "scripts"))
    try:
        result = await registry.execute(
            "task9-capture",
            {"operation_scope": "client.elevated", "provider_max_retries": 0},
        )
    finally:
        reset_provider_operation_scope(token)

    assert result.success is True
    assert captured[0]["operation_scope"] == "s2.scripts"
    assert captured[0]["provider_operation_scope"] == "s2.scripts"

    token = bind_provider_operation_scope(resolve_provider_operation_scope("s2", "scripts"))
    try:
        with pytest.raises(ProviderCostContractError) as forged:
            await registry.execute(
                "task9-capture",
                {
                    "operation_instance": "client.elevated",
                    "provider_max_retries": 0,
                },
            )
    finally:
        reset_provider_operation_scope(token)
    assert forged.value.code == "provider_cost_rule_unavailable"


def test_task9_all_route_families_reference_server_context_binding() -> None:
    from src.routers import pipeline, scenario

    route_functions = [
        scenario._fast_submit_validated,
        scenario._submit_scenario_validated,
        scenario.run_s1_product_direct,
        scenario.run_s2_brand_campaign,
        scenario.run_s3_influencer_remix,
        scenario.run_s4_live_shoot,
        scenario.run_s5_brand_vlog,
        scenario.start_s1_pipeline,
        scenario.fast_generate,
        pipeline.start_pipeline,
    ]
    for function in route_functions:
        source = inspect.getsource(function)
        assert "initialize_and_bind_provider_execution_context" in source
        assert source.index("initialize_and_bind_provider_execution_context") < source.index(
            "_inject_api_keys"
        )


@pytest.mark.asyncio
async def test_task9_operation_scopes_are_isolated_across_concurrent_tasks() -> None:
    from src.services.provider_execution import (
        get_provider_operation_scope,
        provider_operation_scope,
        resolve_provider_operation_scope,
    )

    async def read_scope(scenario: str, step: str) -> str:
        async with provider_operation_scope(resolve_provider_operation_scope(scenario, step)):
            await asyncio.sleep(0)
            scope = get_provider_operation_scope()
            assert scope is not None
            return scope.scope_id

    assert await asyncio.gather(
        read_scope("s1", "scripts"),
        read_scope("s5", "vlog_strategy"),
    ) == ["s1.scripts", "s5.vlog_strategy"]
    assert get_provider_operation_scope() is None
