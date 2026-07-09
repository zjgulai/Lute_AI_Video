"""Tool-level authorized-live readiness checks for the AI video toolbox.

The readiness check reuses the C21 token smoke preflight and adds a per-tool
approval scope. It never submits provider jobs.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.toolbox_contracts import ToolboxProviderReadiness, ToolboxToolId
from src.pipeline.token_smoke_preflight import (
    APPROVAL_RECORD_ENV,
    TokenSmokePreflightReport,
    build_token_smoke_preflight_report,
)
from src.pipeline.toolbox.planner import TOOLBOX_PROVIDER_PROFILE_ID

TOOLBOX_TOOL_SCOPE_FIELD = "toolbox_tool_ids"


def build_toolbox_provider_readiness(
    tool_id: ToolboxToolId,
    *,
    env: Mapping[str, str] | None = None,
    approval_record_path: str | Path | None = None,
) -> ToolboxProviderReadiness:
    """Evaluate whether a toolbox tool may enter authorized-live execution.

    Passing this check does not execute a provider call. It only proves that the
    local approval, key, capability, budget, and tool-scope gates are satisfied.
    """
    env = env or os.environ
    preflight = build_token_smoke_preflight_report(env=env, approval_record_path=approval_record_path)
    tool_scope_blocker = _tool_scope_blocker(tool_id, preflight, env, approval_record_path)
    blocker_reasons = [
        check.detail
        for check in preflight.checks
        if check.status == "block"
    ]
    if tool_scope_blocker:
        blocker_reasons.append(tool_scope_blocker)

    ready_for_authorized_live = preflight.provider_call_allowed and not tool_scope_blocker
    return ToolboxProviderReadiness(
        readiness_id=f"tbx_provider_readiness_{tool_id.value}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        tool_id=tool_id,
        provider_profile_id=TOOLBOX_PROVIDER_PROFILE_ID,
        ready_for_dry_run=True,
        ready_for_authorized_live=ready_for_authorized_live,
        provider_call_allowed=ready_for_authorized_live,
        approval_record_ref=preflight.approval_record_ref,
        approved_provider=preflight.approved_provider,
        approved_model=preflight.approved_model,
        approved_budget_limit_usd=preflight.approved_budget_limit_usd,
        preflight_report_id=preflight.report_id,
        blocker_reasons=blocker_reasons,
    )


def _tool_scope_blocker(
    tool_id: ToolboxToolId,
    preflight: TokenSmokePreflightReport,
    env: Mapping[str, str],
    approval_record_path: str | Path | None,
) -> str | None:
    if preflight.blocked:
        return None

    record_path_raw = approval_record_path or env.get(APPROVAL_RECORD_ENV, "")
    if not record_path_raw:
        return f"approval record must include sample_plan.{TOOLBOX_TOOL_SCOPE_FIELD} for {tool_id.value}"

    payload = _read_approval_payload(Path(record_path_raw).expanduser())
    sample_plan = payload.get("sample_plan")
    tool_ids = sample_plan.get(TOOLBOX_TOOL_SCOPE_FIELD) if isinstance(sample_plan, Mapping) else None
    if not _tool_id_allowed(tool_id, tool_ids):
        return f"approval record sample_plan.{TOOLBOX_TOOL_SCOPE_FIELD} must include {tool_id.value}"
    return None


def _read_approval_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tool_id_allowed(tool_id: ToolboxToolId, tool_ids: Any) -> bool:
    if not isinstance(tool_ids, list):
        return False
    allowed = {str(value).strip() for value in tool_ids}
    return "*" in allowed or tool_id.value in allowed
