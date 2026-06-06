from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.toolbox_contracts import ToolboxToolId
from src.pipeline.token_smoke_preflight import (
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
)
from src.pipeline.toolbox.provider_readiness import (
    TOOLBOX_TOOL_SCOPE_FIELD,
    build_toolbox_provider_readiness,
)


def test_toolbox_provider_readiness_blocks_by_default_without_provider_call():
    readiness = build_toolbox_provider_readiness(ToolboxToolId.PRODUCT_IMAGE, env={})

    assert readiness.evidence_level == "L2-fixture-or-dry-run"
    assert readiness.ready_for_dry_run is True
    assert readiness.ready_for_authorized_live is False
    assert readiness.provider_call_allowed is False
    assert readiness.approval_record_ref is None
    assert any("RUN_TOKEN_SMOKE=1" in reason for reason in readiness.blocker_reasons)
    assert any("approval record" in reason for reason in readiness.blocker_reasons)


def test_toolbox_provider_readiness_requires_tool_scoped_approval(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, toolbox_tool_ids=[])
    env = _ready_env(approval_record)

    readiness = build_toolbox_provider_readiness(ToolboxToolId.PRODUCT_IMAGE, env=env)

    assert readiness.ready_for_authorized_live is False
    assert readiness.provider_call_allowed is False
    assert readiness.approved_provider == "poyo"
    assert readiness.approved_model == "seedance-2"
    assert readiness.approved_budget_limit_usd == 1.0
    assert readiness.blocker_reasons == [
        f"approval record sample_plan.{TOOLBOX_TOOL_SCOPE_FIELD} must include product-image"
    ]


def test_toolbox_provider_readiness_passes_for_approved_tool_without_provider_call(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, toolbox_tool_ids=["product-image", "six-view"])
    env = _ready_env(approval_record)

    readiness = build_toolbox_provider_readiness(ToolboxToolId.PRODUCT_IMAGE, env=env)

    assert readiness.evidence_level == "L2-fixture-or-dry-run"
    assert readiness.ready_for_dry_run is True
    assert readiness.ready_for_authorized_live is True
    assert readiness.provider_call_allowed is True
    assert readiness.approval_record_ref == str(approval_record)
    assert readiness.approved_provider == "poyo"
    assert readiness.approved_model == "seedance-2"
    assert readiness.approved_budget_limit_usd == 1.0
    assert readiness.preflight_report_id is not None
    assert readiness.blocker_reasons == []
    assert "sk_fixture_secret" not in readiness.model_dump_json()


def test_toolbox_provider_readiness_does_not_cross_authorized_tool_scope(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, toolbox_tool_ids=["product-image"])
    env = _ready_env(approval_record)

    readiness = build_toolbox_provider_readiness(ToolboxToolId.DIGITAL_HUMAN, env=env)

    assert readiness.ready_for_authorized_live is False
    assert readiness.provider_call_allowed is False
    assert readiness.blocker_reasons == [
        f"approval record sample_plan.{TOOLBOX_TOOL_SCOPE_FIELD} must include digital-human"
    ]


def _ready_env(approval_record: Path) -> dict[str, str]:
    env = {
        RUN_TOKEN_SMOKE_ENV: "1",
        APPROVAL_RECORD_ENV: str(approval_record),
    }
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _write_approval_record(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "authorized-live-toolbox-approval.json"
    provider = str(overrides.get("provider", "poyo"))
    model = str(overrides.get("model", "seedance-2"))
    budget_limit = str(overrides.get("budget_limit", "$1.00"))
    toolbox_tool_ids = overrides.pop("toolbox_tool_ids", ["product-image"])
    payload: dict[str, Any] = {
        "approval_id": "approval_toolbox_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-06T00:00:00Z",
        "provider": provider,
        "model": model,
        "budget_limit": budget_limit,
        "budget_limit_usd": 1.0,
        "sample_plan": {
            "max_sample_count": 2,
            "max_provider_calls": 2,
            "scenarios": ["toolbox"],
            "s5_requires_separate_confirmation": True,
            TOOLBOX_TOOL_SCOPE_FIELD: toolbox_tool_ids,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": 1.0,
            "per_job_cost_ceiling_usd": 0.5,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
        "approval_statement": APPROVAL_STATEMENT_TEMPLATE.format(
            provider=provider,
            model=model,
            budget_limit=budget_limit,
        ),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path
