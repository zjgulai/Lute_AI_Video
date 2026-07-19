"""Task 5 DeepSeek exact-usage and single-mutation accounting contracts.

All provider responses and transport failures are explicit in-process fakes.  The
only persistence is the disposable SQLite ledger supplied by ``conftest.py``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.models.provider_cost import MAX_SIGNED_BIGINT, ProviderCostContractError
from src.services.provider_cost import ProviderCostService, TrustedRegenerationEpoch
from src.services.provider_execution import (
    ProviderExecutionService,
    _provider_execution_context_var,
    bind_provider_execution_context,
    reset_provider_execution_context,
    with_trusted_regeneration_epoch,
)
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.storage.provider_cost_repository import ProviderCostRepository
from src.tools import llm_client as llm_module
from src.tools.llm_client import LLMClient, LLMNotConfiguredError, _request_api_keys

CHECKED_AT = datetime(2026, 7, 17, 9, 0, 0, tzinfo=UTC)
TENANT_ID = "tenant-provider-cost-llm"
PRO_CAP_USD_NANOS = 2_000_000_000
FIXTURE_KEY = "fixture-deepseek-key-never-sent"
PRO_OPERATION = "llm.chat.default"
FLASH_OPERATION = "fast.prompt_enhance"


def _usage(
    *,
    prompt_tokens: object = 10,
    cache_hit: object = 3,
    cache_miss: object = 7,
    completion_tokens: object = 5,
    total_tokens: object = 15,
) -> dict[str, object]:
    return {
        "prompt_tokens": prompt_tokens,
        "prompt_cache_hit_tokens": cache_hit,
        "prompt_cache_miss_tokens": cache_miss,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


class _FakeTransport:
    def __init__(
        self,
        *,
        usage: dict[str, object] | None = None,
        content: str = "settled provider content",
        error: BaseException | None = None,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.usage = usage
        self.content = content
        self.error = error
        self.entered = entered
        self.release = release
        self.attempts = 0

    async def ainvoke(self, messages: list[Any]) -> Any:
        assert len(messages) == 2
        self.attempts += 1
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error
        metadata: dict[str, object] = {}
        if self.usage is not None:
            metadata["token_usage"] = self.usage
        return SimpleNamespace(
            content=self.content,
            response_metadata=metadata,
        )


class _GateTransport(_FakeTransport):
    """Return valid script/scoring JSON while retaining exact usage facts."""

    async def ainvoke(self, messages: list[Any]) -> Any:
        system_prompt = str(messages[0].content)
        if "expert video script evaluator" in system_prompt.lower():
            self.content = json.dumps(
                {
                    "text_quality": 0.8,
                    "strategy_fit": 0.8,
                    "usp_coverage": 0.8,
                    "platform_fit": 0.8,
                    "brand_tone": 0.8,
                    "overall": 0.8,
                    "explanation": "fixture score",
                }
            )
        else:
            self.content = json.dumps(
                {
                    "segments": [
                        {
                            "segment_type": "hook",
                            "start_time": 0,
                            "end_time": 3,
                            "voiceover": "Hook",
                            "visual_description": "Product close-up",
                            "text_overlay": "Hook",
                        },
                        {
                            "segment_type": "solution",
                            "start_time": 3,
                            "end_time": 25,
                            "voiceover": "Solution",
                            "visual_description": "Product in use",
                            "text_overlay": "Solution",
                        },
                        {
                            "segment_type": "cta",
                            "start_time": 25,
                            "end_time": 30,
                            "voiceover": "Shop now",
                            "visual_description": "Product hero",
                            "text_overlay": "Shop",
                        },
                    ],
                    "hashtags": [],
                    "cta_text": "Shop now",
                    "total_duration": 30,
                }
            )
        return await super().ainvoke(messages)


@asynccontextmanager
async def _paid_client_scope(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transport: _FakeTransport,
    job_id: str,
    provider: str = "deepseek",
    cap_usd_nanos: int = PRO_CAP_USD_NANOS,
    scenario_or_resource_type: str = "fast",
) -> AsyncIterator[tuple[LLMClient, ProviderCostRepository, Any, list[dict[str, Any]]]]:
    import langchain_openai

    repository = ProviderCostRepository(require_postgres=False)
    catalog = ProviderPriceCatalog.load_default()
    execution_service = ProviderExecutionService(
        repository=repository,
        server_cap_usd_nanos=cap_usd_nanos,
        clock=lambda: CHECKED_AT,
    )
    context = await execution_service.initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id=job_id,
        scenario_or_resource_type=scenario_or_resource_type,
        generation_policy_version="generation-safety.v1",
    )

    constructor_calls: list[dict[str, Any]] = []

    def fake_chat_openai(**kwargs: Any) -> _FakeTransport:
        constructor_calls.append(kwargs)
        return transport

    monkeypatch.setattr(llm_module, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", fake_chat_openai)

    def cost_service_factory(registry: Any) -> ProviderCostService:
        return ProviderCostService(
            repository=repository,
            price_catalog=catalog,
            operation_registry=registry,
            clock=lambda: CHECKED_AT,
        )

    client = LLMClient(
        provider=provider,
        timeout=0.05,
        price_catalog=catalog,
        cost_service_factory=cost_service_factory,
    )
    key_token = _request_api_keys.set({"DEEPSEEK_API_KEY": FIXTURE_KEY})
    context_token = bind_provider_execution_context(context)
    try:
        yield client, repository, context, constructor_calls
    finally:
        reset_provider_execution_context(context_token)
        _request_api_keys.reset(key_token)


def _attempt_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute("SELECT * FROM provider_cost_attempts ORDER BY created_at, attempt_id").fetchall()


@pytest.mark.asyncio
async def test_missing_context_blocks_sdk_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langchain_openai

    constructions = 0

    def forbidden_constructor(**_kwargs: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("SDK client must not be constructed")

    monkeypatch.setattr(llm_module, "ChatOpenAI", forbidden_constructor)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", forbidden_constructor)
    key_token = _request_api_keys.set({"DEEPSEEK_API_KEY": FIXTURE_KEY})
    context_token = _provider_execution_context_var.set(None)
    try:
        with pytest.raises(ProviderCostContractError) as exc_info:
            await LLMClient(provider="deepseek").ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
    finally:
        _provider_execution_context_var.reset(context_token)
        _request_api_keys.reset(key_token)

    assert exc_info.value.code == "provider_execution_context_missing"
    assert constructions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_keys",
    [{}, {"DEEPSEEK_API_KEY": "   "}],
    ids=["missing", "whitespace"],
)
async def test_no_key_is_explicit_zero_attempt_local_branch(
    monkeypatch: pytest.MonkeyPatch,
    request_keys: dict[str, str],
) -> None:
    constructions = 0

    def forbidden_constructor(**_kwargs: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("SDK client must not be constructed")

    monkeypatch.setattr(llm_module, "ChatOpenAI", forbidden_constructor)
    key_token = _request_api_keys.set(request_keys)
    context_token = _provider_execution_context_var.set(None)
    try:
        with pytest.raises(LLMNotConfiguredError):
            await LLMClient(provider="deepseek").ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
    finally:
        _provider_execution_context_var.reset(context_token)
        _request_api_keys.reset(key_token)

    assert constructions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model", "operation_key", "endpoint"),
    [
        ("openai", "gpt-4o", PRO_OPERATION, "https://api.deepseek.com"),
        ("anthropic", "claude-sonnet-4", PRO_OPERATION, "https://api.deepseek.com"),
        ("kimi", "moonshot-v1", PRO_OPERATION, "https://api.deepseek.com"),
        ("deepseek", "deepseek-chat", PRO_OPERATION, "https://api.deepseek.com"),
        ("deepseek", "deepseek-reasoner", PRO_OPERATION, "https://api.deepseek.com"),
        ("deepseek", "deepseek-v4-unknown", PRO_OPERATION, "https://api.deepseek.com"),
        ("deepseek", "deepseek-v4-pro", "caller.operation", "https://api.deepseek.com"),
        ("deepseek", "deepseek-v4-pro", PRO_OPERATION, "https://fixture.invalid"),
    ],
)
async def test_unknown_provider_model_operation_or_endpoint_is_zero_network_blocked(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
    operation_key: str,
    endpoint: str,
) -> None:
    del isolated_provider_cost_db
    transport = _FakeTransport(usage=_usage())
    monkeypatch.setattr(llm_module, "DEEPSEEK_API_BASE", endpoint)
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id=f"invalid-{provider}-{model}".replace("/", "-"),
        provider=provider,
    ) as (client, _repository, _context, constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model=model,
                operation_key=operation_key,
            )

    assert exc_info.value.code == "provider_cost_rule_unavailable"
    assert constructor_calls == []
    assert transport.attempts == 0


@pytest.mark.asyncio
async def test_caller_cannot_override_frozen_completion_cap(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_provider_cost_db
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="override-cap",
    ) as (client, _repository, _context, constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
                max_completion_tokens=1,
            )

    assert exc_info.value.code == "provider_cost_rule_unavailable"
    assert constructor_calls == []
    assert transport.attempts == 0


@pytest.mark.asyncio
async def test_insufficient_job_cap_blocks_before_sdk_construction(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="insufficient-cap",
        cap_usd_nanos=100_000_000,
    ) as (client, _repository, _context, constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )

    assert exc_info.value.code == "provider_budget_exhausted"
    assert constructor_calls == []
    assert transport.attempts == 0
    assert _attempt_rows(isolated_provider_cost_db) == []


@pytest.mark.asyncio
async def test_sdk_construction_failure_releases_pre_submit_reservation(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langchain_openai

    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="constructor-failure",
    ) as (client, repository, context, _constructor_calls):

        def failing_constructor(**_kwargs: Any) -> None:
            raise RuntimeError("fixture constructor failure")

        monkeypatch.setattr(llm_module, "ChatOpenAI", failing_constructor)
        monkeypatch.setattr(langchain_openai, "ChatOpenAI", failing_constructor)
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
        account = await repository.get_account(
            tenant_id=TENANT_ID,
            account_id=context.account_id,
        )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"
    assert transport.attempts == 0
    assert len(rows) == 1
    assert rows[0]["state"] == "released"
    assert account is not None
    assert account["reserved_usd_nanos"] == 0
    assert account["settled_usd_nanos"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "operation_key", "expected_reserved", "expected_settled"),
    [
        ("deepseek-v4-pro", PRO_OPERATION, 436_781_760, 7_406),
        ("deepseek-v4-flash", FLASH_OPERATION, 140_573_440, 2_389),
    ],
)
async def test_success_reserves_maximum_envelope_settles_exact_usage_then_returns_content(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    operation_key: str,
    expected_reserved: int,
    expected_settled: int,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id=f"success-exact-usage-{model}",
    ) as (client, repository, context, constructor_calls):
        result = await client.ainvoke(
            "sensitive-system-fixture",
            "sensitive-user-fixture",
            model=model,
            operation_key=operation_key,
        )
        attempt = await repository.get_account(
            tenant_id=TENANT_ID,
            account_id=context.account_id,
        )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert result == "settled provider content"
    assert transport.attempts == 1
    assert len(constructor_calls) == 1
    assert constructor_calls[0]["model"] == model
    assert constructor_calls[0]["base_url"] == "https://api.deepseek.com"
    assert constructor_calls[0]["max_completion_tokens"] == 4_096
    assert constructor_calls[0]["max_retries"] == 0
    assert len(rows) == 1
    assert rows[0]["state"] == "settled"
    assert rows[0]["logical_operation"] == f"{operation_key}.primary"
    assert rows[0]["reserved_usd_nanos"] == expected_reserved
    assert rows[0]["settled_usd_nanos"] == expected_settled
    persisted_attempt = repr(dict(rows[0]))
    for forbidden in (
        "sensitive-system-fixture",
        "sensitive-user-fixture",
        "settled provider content",
        FIXTURE_KEY,
    ):
        assert forbidden not in persisted_attempt
    assert attempt is not None
    assert attempt["reserved_usd_nanos"] == 0
    assert attempt["settled_usd_nanos"] == expected_settled


@pytest.mark.asyncio
async def test_settled_invalid_json_is_contract_error_without_local_fallback(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage(), content="not-json")
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="settled-invalid-json",
    ) as (client, _repository, _context, _constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.invoke_json(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )

    assert exc_info.value.code == "provider_cost_usage_invalid"
    rows = _attempt_rows(isolated_provider_cost_db)
    assert len(rows) == 1
    assert rows[0]["state"] == "settled"
    assert transport.attempts == 1


@pytest.mark.asyncio
async def test_changed_prompt_in_same_operation_slot_conflicts_before_second_mutation(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="same-slot-different-intent",
    ) as (client, _repository, _context, constructor_calls):
        assert (
            await client.ainvoke(
                "system",
                "first user intent",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
            == "settled provider content"
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "changed user intent",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert exc_info.value.code == "provider_cost_attempt_conflict"
    assert transport.attempts == 1
    assert len(constructor_calls) == 1
    assert len(rows) == 1
    assert rows[0]["logical_operation"] == f"{PRO_OPERATION}.primary"
    assert rows[0]["ordinal"] == 0


@pytest.mark.asyncio
async def test_explicit_server_slots_are_distinct_exactly_once_operations(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="server-owned-slots",
    ) as (client, _repository, _context, _constructor_calls):
        for slot in ("candidate.standard", "candidate.creative"):
            assert (
                await client.ainvoke(
                    "system",
                    f"intent for {slot}",
                    model="deepseek-v4-pro",
                    operation_key=PRO_OPERATION,
                    operation_instance=slot,
                )
                == "settled provider content"
            )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert transport.attempts == 2
    assert sorted((row["logical_operation"], row["ordinal"]) for row in rows) == sorted(
        [
            (f"{PRO_OPERATION}.candidate.standard", 0),
            (f"{PRO_OPERATION}.candidate.creative", 0),
        ]
    )


@pytest.mark.asyncio
async def test_invalid_operation_instance_is_zero_network_blocked(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="invalid-operation-instance",
    ) as (client, _repository, _context, constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
                operation_instance="../caller-controlled",
            )

    assert exc_info.value.code == "provider_cost_rule_unavailable"
    assert constructor_calls == []
    assert transport.attempts == 0
    assert _attempt_rows(isolated_provider_cost_db) == []


@pytest.mark.asyncio
async def test_trusted_workflow_regeneration_advances_same_logical_operation_ordinal(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="trusted-regeneration",
    ) as (client, _repository, context, _constructor_calls):
        assert (
            await client.ainvoke(
                "system",
                "same intent",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
                operation_instance="candidate.standard",
            )
            == "settled provider content"
        )
        regenerated = with_trusted_regeneration_epoch(
            context,
            TrustedRegenerationEpoch(
                operation_key="gate.regenerate.scripts",
                epoch_ref="fixture-regeneration-epoch",
            ),
        )
        regeneration_token = bind_provider_execution_context(regenerated)
        try:
            assert (
                await client.ainvoke(
                    "system",
                    "same intent",
                    model="deepseek-v4-pro",
                    operation_key=PRO_OPERATION,
                    operation_instance="candidate.standard",
                )
                == "settled provider content"
            )
            assert transport.attempts == 2
            assert (
                await client.ainvoke(
                    "system",
                    "same creative intent",
                    model="deepseek-v4-pro",
                    operation_key=PRO_OPERATION,
                    operation_instance="candidate.creative",
                )
                == "settled provider content"
            )
            with pytest.raises(ProviderCostContractError) as reused_epoch:
                await client.ainvoke(
                    "system",
                    "different regenerated intent",
                    model="deepseek-v4-pro",
                    operation_key=PRO_OPERATION,
                    operation_instance="candidate.standard",
                )
            assert reused_epoch.value.code == "provider_cost_attempt_conflict"
            assert transport.attempts == 3
        finally:
            reset_provider_execution_context(regeneration_token)

    rows = _attempt_rows(isolated_provider_cost_db)
    assert transport.attempts == 3
    assert sorted((row["logical_operation"], row["ordinal"]) for row in rows) == sorted(
        [
            (f"{PRO_OPERATION}.candidate.standard", 0),
            (f"{PRO_OPERATION}.candidate.standard", 1),
            (f"{PRO_OPERATION}.candidate.creative", 0),
        ]
    )


@pytest.mark.asyncio
async def test_gate_generate_and_regenerate_uses_new_epoch_for_identical_script_and_score(
    isolated_state_dir: Any,
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import candidate_scorer, gate_manager
    from src.pipeline.state_manager import PipelineStateManager
    from src.skills.script_writer import ScriptWriterSkill
    from tests.generation_policy_test_utils import attach_execution_policy
    from tests.test_generation_policy_step_guard import _state

    transport = _GateTransport(usage=_usage())
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="gate-regeneration-identical-intent",
        scenario_or_resource_type="s1",
    ) as (client, _repository, context, _constructor_calls):
        state = _state("s1", media=False, current_step="scripts")
        attach_execution_policy(
            state,
            scenario="s1",
            media=False,
            tenant_id=TENANT_ID,
            execution_context=context,
        )
        state["steps"]["strategy"].update(
            {
                "status": "done",
                "output": [{"id": "brief", "topic": "fixture", "usp_priority": ["portable"]}],
            }
        )
        await PipelineStateManager().save(state["label"], state)

        monkeypatch.setattr(llm_module, "llm", client)
        monkeypatch.setattr(candidate_scorer, "llm", client)

        async def execute_script_skill(self: Any, skill_name: str, params: dict[str, Any]) -> Any:
            del self
            assert skill_name == "script-writer-skill"
            return await ScriptWriterSkill().safe_execute(params)

        monkeypatch.setattr(gate_manager.SkillRegistry, "execute", execute_script_skill)
        monkeypatch.setattr(gate_manager, "score_candidate", candidate_scorer.score_candidate)

        generated = await gate_manager.generate_candidates(state["label"], "gate_1_script")
        assert len(generated["candidates"]) == 3
        assert transport.attempts == 6  # three script generations plus three scores

        standard_id = next(
            candidate["id"] for candidate in generated["candidates"] if candidate["variant"] == "standard"
        )
        regenerated = await gate_manager.regenerate_candidate(state["label"], "gate_1_script", standard_id)
        assert regenerated["candidate"]["variant"] == "standard"
        assert transport.attempts == 8  # same script and score intents, new trusted epoch

    rows = _attempt_rows(isolated_provider_cost_db)
    script_rows = [
        row
        for row in rows
        if row["logical_operation"] == "skill.script_writer.gate.gate_1_script.variant.standard.brief.0.lang.en"
    ]
    score_rows = [
        row
        for row in rows
        if row["logical_operation"] == "pipeline.candidate_scorer.gate.gate_1_script.candidate.standard"
    ]
    assert sorted(row["ordinal"] for row in script_rows) == [0, 1]
    assert sorted(row["ordinal"] for row in score_rows) == [0, 1]
    script_epoch_rows = {row["ordinal"]: row["regeneration_epoch_ref"] for row in script_rows}
    score_epoch_rows = {row["ordinal"]: row["regeneration_epoch_ref"] for row in score_rows}
    assert script_epoch_rows[0] is None
    assert script_epoch_rows[1].startswith("regen_")
    assert score_epoch_rows[0] is None
    assert score_epoch_rows[1].startswith("regen_")
    assert script_epoch_rows[1] == score_epoch_rows[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
        _usage(cache_hit=4),
        _usage(cache_hit=True, cache_miss=9),
        _usage(cache_miss=-1, cache_hit=11),
        _usage(
            prompt_tokens=MAX_SIGNED_BIGINT + 1,
            cache_hit=0,
            cache_miss=MAX_SIGNED_BIGINT + 1,
            total_tokens=MAX_SIGNED_BIGINT + 6,
        ),
        _usage(
            prompt_tokens=995_905,
            cache_hit=0,
            cache_miss=995_905,
            completion_tokens=4_096,
            total_tokens=1_000_001,
        ),
        _usage(
            prompt_tokens=995_905,
            cache_hit=995_905,
            cache_miss=0,
            completion_tokens=1,
            total_tokens=995_906,
        ),
        _usage(
            prompt_tokens=1,
            cache_hit=1,
            cache_miss=0,
            completion_tokens=4_097,
            total_tokens=4_098,
        ),
    ],
    ids=[
        "missing-cache-split",
        "cache-conservation",
        "bool",
        "negative",
        "overflow",
        "actual-over-reserve",
        "input-envelope-exceeded-but-cheap",
        "output-envelope-exceeded-but-cheap",
    ],
)
async def test_invalid_or_over_reservation_usage_holds_accounting_error_and_returns_no_content(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    usage: dict[str, object],
) -> None:
    transport = _FakeTransport(usage=usage)
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="invalid-usage",
    ) as (client, repository, context, _constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
        account = await repository.get_account(
            tenant_id=TENANT_ID,
            account_id=context.account_id,
        )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert exc_info.value.code == "provider_cost_accounting_error"
    assert transport.attempts == 1
    assert len(rows) == 1
    assert rows[0]["state"] == "accounting_error"
    assert rows[0]["settled_usd_nanos"] == 0
    assert account is not None
    assert account["reserved_usd_nanos"] == 436_781_760
    assert account["settled_usd_nanos"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transport_error",
    [ConnectionError("fixture disconnect"), TimeoutError("fixture timeout")],
    ids=["disconnect", "timeout"],
)
async def test_transport_uncertainty_is_ambiguous_single_attempt_without_fallback(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    transport_error: BaseException,
) -> None:
    transport = _FakeTransport(error=transport_error)
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="ambiguous-transport",
    ) as (client, repository, context, _constructor_calls):
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.ainvoke(
                "system",
                "user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
        account = await repository.get_account(
            tenant_id=TENANT_ID,
            account_id=context.account_id,
        )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert exc_info.value.code == "provider_cost_outcome_ambiguous"
    assert transport.attempts == 1
    assert rows[0]["state"] == "ambiguous"
    assert account is not None
    assert account["reserved_usd_nanos"] == 436_781_760
    assert account["settled_usd_nanos"] == 0


@pytest.mark.asyncio
async def test_same_fingerprint_concurrency_sends_one_mutation(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    transport = _FakeTransport(usage=_usage(), entered=entered, release=release)
    async with _paid_client_scope(
        monkeypatch,
        transport=transport,
        job_id="concurrent-replay",
    ) as (client, _repository, _context, _constructor_calls):
        owner = asyncio.create_task(
            client.ainvoke(
                "system",
                "same user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        with pytest.raises(ProviderCostContractError) as replay_error:
            await client.ainvoke(
                "system",
                "same user",
                model="deepseek-v4-pro",
                operation_key=PRO_OPERATION,
            )
        release.set()
        assert await owner == "settled provider content"

    rows = _attempt_rows(isolated_provider_cost_db)
    assert replay_error.value.code == "provider_cost_attempt_conflict"
    assert transport.attempts == 1
    assert len(rows) == 1
    assert rows[0]["state"] == "settled"


def test_fast_mode_model_metadata_does_not_construct_llm_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.services.fast_mode import FastModeService

    def forbidden_get_client(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("FastModeService init must not construct an LLM SDK client")

    monkeypatch.setattr(LLMClient, "_get_client", forbidden_get_client)
    service = FastModeService()

    assert service._llm_model == "deepseek-v4-flash"


def test_llm_mutation_source_has_no_generic_retry_tracker_or_response_preview() -> None:
    source = inspect.getsource(llm_module.LLMClient)

    assert "retry_with_backoff" not in source
    assert "cost_tracker" not in source
    assert "raw_preview" not in source
    assert "max_retries=0" in source


def test_active_deepseek_aliases_are_removed_from_runtime_callers() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        root / "src/services/fast_mode.py",
        root / "src/agents/strategy.py",
        root / "src/agents/script_writer.py",
        root / "src/skills/product_strategy.py",
        root / "src/skills/script_writer.py",
        root / "web/src/lib/modelProviderConfig.ts",
    ]

    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        assert "deepseek-chat" not in source, path
        assert "deepseek-reasoner" not in source, path
