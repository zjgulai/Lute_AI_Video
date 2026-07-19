from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.pipeline.authorized_live_harness import EXECUTE_ENV, run_authorized_live_harness
from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_RECORD_ENV,
    ACCOUNT_READINESS_SCOPE,
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    DEFAULT_AUTH_BUDGET_LIMIT,
    DEFAULT_AUTH_BUDGET_LIMIT_USD,
    DEFAULT_AUTH_MODEL,
    DEFAULT_AUTH_PROVIDER,
    DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
    DEFAULT_AUTH_TEST_SCOPE,
    PROVIDER_REVALIDATION_REF,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
)
from src.services.provider_cost import ValidatedProviderBudgetAuthorization
from src.services.provider_execution import (
    ProviderExecutionContext,
    get_provider_execution_context,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "authorized_live_token_smoke_harness.py"


def test_harness_is_disabled_by_default_without_provider_call():
    calls: list[str] = []

    report = run_authorized_live_harness(
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"}
    )

    assert report.status == "disabled"
    assert report.provider_call_executed is False
    assert report.preflight is None
    assert calls == []


def test_dry_run_passes_after_preflight_without_provider_call(tmp_path: Path):
    calls: list[str] = []
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(
        mode="dry_run",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.preflight is not None
    assert report.preflight.provider_call_allowed is True
    assert report.job_spec is not None
    assert len(report.job_specs) == 4
    assert report.job_spec == report.job_specs[-1]
    assert report.job_spec.provider == "poyo"
    assert report.job_spec.model == "seedance-2"
    assert report.job_spec.scenario == "toolbox"
    assert report.job_spec.step_name == "momcozy_sterilizer_asset_video"
    assert report.job_spec.brand_bundle_id == "bundle_momcozy_candidate"
    assert report.job_spec.cost_ceiling_usd == 2.5
    assert [spec.model for spec in report.job_specs[:3]] == ["gpt-image-2", "gpt-image-2", "gpt-image-2"]
    assert [spec.step_name for spec in report.job_specs] == [
        "momcozy_sterilizer_main_45_image",
        "momcozy_sterilizer_uv_benefit_image",
        "momcozy_sterilizer_kitchen_scene_image",
        "momcozy_sterilizer_asset_video",
    ]
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.asset_status == "pending_review"
    assert report.artifact_manifest.image_count == 3
    assert report.artifact_manifest.video_count == 1
    assert report.artifact_manifest.delivery_accepted is False
    assert report.artifact_manifest.publish_allowed is False
    assert report.artifact_manifest.approved_brand_token_write is False
    assert len(report.artifact_manifest.artifacts) == 4
    assert report.job_spec.reference_asset_ids == report.artifact_manifest.video_reference_asset_refs
    assert len(report.artifact_manifest.video_reference_asset_refs) == 3
    assert all(
        ref.startswith("artifact://authorized-live/") for ref in report.artifact_manifest.video_reference_asset_refs
    )
    assert len(report.job_records) == 4
    assert all(record.status == "prepared" for record in report.job_records)
    assert all(record.delivery_accepted is False for record in report.job_records)
    assert all(record.publish_allowed is False for record in report.job_records)
    assert calls == []


def test_dry_run_job_spec_uses_approval_provider_model_and_per_job_budget(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        provider="poyo",
        model="seedance-2",
        budget_limit_usd=3.0,
        budget_stop_loss={
            "max_total_cost_usd": 3.0,
            "per_job_cost_ceiling_usd": 2.0,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
    )
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(mode="dry_run", env=env)

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.job_spec is not None
    assert report.job_spec.provider == "poyo"
    assert report.job_spec.model == "seedance-2"
    assert report.job_spec.cost_ceiling_usd == 2.0
    assert [spec.cost_ceiling_usd for spec in report.job_specs] == [2.0, 2.0, 2.0, 2.0]


def test_execute_mode_requires_extra_execute_flag_after_preflight(tmp_path: Path):
    calls: list[str] = []
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert report.blocked_reasons == [f"{EXECUTE_ENV}=1 is required for execute mode"]
    assert calls == []


def test_execute_mode_blocks_when_submitter_is_not_configured(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"

    report = run_authorized_live_harness(mode="execute", env=env)

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert report.blocked_reasons == ["provider submitter is not configured"]
    assert len(report.job_specs) == 4
    assert report.artifact_manifest is not None


def test_execute_mode_does_not_build_submitter_factory_when_preflight_blocks(tmp_path: Path):
    calls: list[str] = []
    env = {RUN_TOKEN_SMOKE_ENV: "1", EXECUTE_ENV: "1"}

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter_factory=lambda: calls.append("built") or None,
        execution_context_initializer=_execution_context_initializer,
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert calls == []


def test_execute_mode_blocks_when_submitter_factory_returns_none(tmp_path: Path):
    calls: list[str] = []
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter_factory=lambda: calls.append("built") or None,
        execution_context_initializer=_execution_context_initializer,
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert report.blocked_reasons == ["provider submitter is not configured"]
    assert calls == ["built"]


def test_execute_mode_uses_submitter_factory_after_preflight_and_execute_gate(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"
    factory_calls: list[str] = []
    submitter_calls: list[str] = []

    def submitter(spec: Any) -> dict[str, str]:
        assert get_provider_execution_context() is not None
        submitter_calls.append(spec.job_id)
        return _provider_response(spec)

    def factory() -> Any:
        assert get_provider_execution_context() is not None
        factory_calls.append("built")
        return submitter

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter_factory=factory,
        execution_context_initializer=_execution_context_initializer,
    )

    assert report.status == "submitted"
    assert report.provider_call_executed is True
    assert factory_calls == ["built"]
    assert len(submitter_calls) == 4
    assert get_provider_execution_context() is None


def test_execute_mode_with_submitter_runs_asset_pack_once_in_order_without_retry(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"
    calls: list[Any] = []
    account_ids: list[str] = []

    def submitter(spec: Any) -> dict[str, str]:
        context = get_provider_execution_context()
        assert context is not None
        account_ids.append(context.account_id)
        calls.append(spec)
        return _provider_response(spec)

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter=submitter,
        execution_context_initializer=_execution_context_initializer,
    )

    assert report.status == "submitted"
    assert report.provider_call_executed is True
    assert len(calls) == 4
    assert account_ids == ["account-authorized-live-fixture"] * 4
    assert get_provider_execution_context() is None
    assert len({spec.job_id for spec in calls}) == 4
    assert [spec.model for spec in calls[:3]] == ["gpt-image-2", "gpt-image-2", "gpt-image-2"]
    assert calls[-1].model == "seedance-2"
    assert report.artifact_manifest is not None
    assert calls[-1].reference_asset_ids == report.artifact_manifest.video_reference_asset_refs
    assert report.provider_response_refs == {spec.job_id: f"provider:{spec.job_id}" for spec in calls}
    assert len(report.job_records) == 4
    assert all(record.status == "submitted" for record in report.job_records)
    assert all(record.delivery_accepted is False for record in report.job_records)
    assert all(record.publish_allowed is False for record in report.job_records)
    assert all(artifact.media_url for artifact in report.artifact_manifest.artifacts)
    assert report.artifact_manifest.artifacts[-1].media_url == (
        "https://cdn.example.test/momcozy_sterilizer_i2v_15s_authorized_live_fixture.mp4"
    )


def test_execute_mode_requires_provider_media_url_for_artifact_manifest(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"

    def submitter(spec: Any) -> dict[str, str]:
        return {"provider_job_id": f"provider:{spec.job_id}"}

    try:
        run_authorized_live_harness(
            mode="execute",
            env=env,
            submitter=submitter,
            execution_context_initializer=_execution_context_initializer,
        )
    except ValueError as exc:
        assert "missing media_url" in str(exc)
    else:
        raise AssertionError("execute mode must fail when provider media_url is missing")


def test_execute_mode_rejects_noncanonical_budget_token_before_context_or_factory(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    approval_record.write_text(
        approval_record.read_text().replace('"budget_limit_usd": 3.0', '"budget_limit_usd": 3e0')
    )
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"
    calls: list[str] = []

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter_factory=lambda: calls.append("factory") or None,
        execution_context_initializer=lambda specs, authorization: (
            calls.append("context") or _execution_context_initializer(specs, authorization)
        ),
    )

    assert report.status == "blocked"
    assert report.blocked_reasons == ["provider budget authorization is invalid"]
    assert calls == []


def test_execute_mode_rejects_expired_authority_before_context_or_factory(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, expires_at="2026-06-04T01:00:00Z")
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"
    calls: list[str] = []

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter_factory=lambda: calls.append("factory") or None,
        execution_context_initializer=lambda specs, authorization: (
            calls.append("context") or _execution_context_initializer(specs, authorization)
        ),
    )

    assert report.status == "blocked"
    assert report.blocked_reasons == ["provider budget authorization is invalid"]
    assert calls == []


def test_cli_default_is_disabled_and_json_parseable():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "disabled"
    assert payload["provider_call_executed"] is False


def test_cli_source_has_explicit_poyo_http_submitter_opt_in():
    source = SCRIPT_PATH.read_text()

    assert "--enable-poyo-http-submitter" in source
    assert "build_authorized_live_poyo_runtime_submitter" in source
    assert "PoyoClient" not in source
    assert "httpx" not in source


def _ready_env(approval_record: Path) -> dict[str, str]:
    account_readiness = _write_account_readiness_record(approval_record.parent)
    env = {
        RUN_TOKEN_SMOKE_ENV: "1",
        APPROVAL_RECORD_ENV: str(approval_record),
        ACCOUNT_READINESS_RECORD_ENV: str(account_readiness),
    }
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _provider_response(spec: Any) -> dict[str, str]:
    extension = "mp4" if spec.job_id == "momcozy_sterilizer_i2v_15s_authorized_live_fixture" else "png"
    return {
        "provider_job_id": f"provider:{spec.job_id}",
        "artifact_ref": _artifact_ref_for_job_id(spec.job_id),
        "media_url": f"https://cdn.example.test/{spec.job_id}.{extension}",
        "thumbnail_ref": f"https://cdn.example.test/{spec.job_id}.jpg",
    }


def _execution_context_initializer(
    job_specs: list[Any],
    authorization: ValidatedProviderBudgetAuthorization,
) -> ProviderExecutionContext:
    assert len(job_specs) == 4
    return ProviderExecutionContext(
        tenant_id="authorized-live-harness",
        budget_job_kind="compatibility",
        budget_job_id="compat_authorized_live_fixture",
        account_id="account-authorized-live-fixture",
        scenario_or_resource_type="toolbox",
        effective_cap_usd_nanos=authorization.per_job_cost_ceiling_usd_nanos,
        budget_source_kind="validated_authorization",
        trusted_authorization_ref=authorization.authorization_ref,
        budget_policy_version="provider-budget.v1",
        generation_policy_version="authorized-live.v1",
        provider_max_retries=0,
    )


def _artifact_ref_for_job_id(job_id: str) -> str:
    return {
        "momcozy_sterilizer_main_45_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2"
        ),
        "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2"
        ),
        "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2"
        ),
        "momcozy_sterilizer_i2v_15s_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-i2v-15s-seedance-2"
        ),
    }[job_id]


def _write_approval_record(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "authorized-live-approval.json"
    provider = str(overrides.get("provider", DEFAULT_AUTH_PROVIDER))
    model = str(overrides.get("model", DEFAULT_AUTH_MODEL))
    provider_model_scope = str(overrides.get("provider_model_scope", DEFAULT_AUTH_PROVIDER_MODEL_SCOPE))
    test_scope = str(overrides.get("test_scope", DEFAULT_AUTH_TEST_SCOPE))
    budget_limit = str(overrides.get("budget_limit", DEFAULT_AUTH_BUDGET_LIMIT))
    payload: dict[str, Any] = {
        "approval_id": "approval_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-04T00:00:00Z",
        "expires_at": "2099-06-04T04:00:00Z",
        "provider": provider,
        "model": model,
        "provider_model_scope": provider_model_scope,
        "test_scope": test_scope,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "budget_limit": budget_limit,
        "budget_limit_usd": DEFAULT_AUTH_BUDGET_LIMIT_USD,
        "sample_plan": {
            "max_sample_count": 4,
            "max_provider_calls": 4,
            "scenarios": ["toolbox"],
            "toolbox_tool_ids": ["product-image", "ecommerce-visual", "storyboard"],
            "sample_ids": [
                "momcozy-sterilizer-main-45-gpt-image-2",
                "momcozy-sterilizer-uv-benefit-gpt-image-2",
                "momcozy-sterilizer-kitchen-scene-gpt-image-2",
                "momcozy-sterilizer-i2v-15s-seedance-2",
            ],
            "asset_package": {
                "brand": "momcozy",
                "product": "sterilizer",
                "image_count": 3,
                "video_count": 1,
                "asset_status": "pending_review",
                "delivery_accepted": False,
                "publish_allowed": False,
                "approved_brand_token_write": False,
            },
            "s5_requires_separate_confirmation": True,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": 3.0,
            "per_job_cost_ceiling_usd": 2.5,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
        "approval_statement": _approval_statement(provider_model_scope, test_scope, budget_limit),
    }
    payload.update(overrides)
    if {"provider", "model", "budget_limit"} & overrides.keys() and "approval_statement" not in overrides:
        payload["approval_statement"] = _approval_statement(
            str(payload["provider_model_scope"]),
            str(payload["test_scope"]),
            str(payload["budget_limit"]),
        )
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _write_account_readiness_record(tmp_path: Path) -> Path:
    path = tmp_path / "provider-account-readiness.json"
    payload: dict[str, Any] = {
        "template_only": False,
        "readiness_id": "account_readiness_harness_fixture",
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider": "poyo",
        "checked_by": "user",
        "checked_at": "2026-06-06T00:00:00Z",
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "available_credit_usd": 3.0,
        "minimum_required_credit_usd": 3.0,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _approval_statement(provider_model_scope: str, test_scope: str, budget_limit: str) -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=provider_model_scope,
        test_scope=test_scope,
        budget_limit=budget_limit,
    )
