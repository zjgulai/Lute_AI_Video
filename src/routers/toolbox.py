"""Toolbox dry-run API for standalone AI video creative tools."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from src.models.commercial_contracts import EvidenceLevel
from src.models.toolbox_contracts import (
    ToolboxInjectionAuditSummary,
    ToolboxInjectionAuditSummaryList,
    ToolboxInjectionDraft,
    ToolboxRequest,
    ToolboxToolId,
)
from src.pipeline.toolbox.planner import (
    build_toolbox_injection_audit_summary,
    build_toolbox_injection_draft,
    build_toolbox_plan,
    build_toolbox_prompt_preview,
    build_toolbox_run_state,
    project_toolbox_artifacts,
    project_toolbox_run_state,
)
from src.pipeline.toolbox.registry import list_toolbox_tools

router = APIRouter(prefix="/toolbox", tags=["toolbox"])

_RUNS: dict[str, Any] = {}


@router.get("/tools")
async def list_tools() -> dict[str, Any]:
    return {
        "evidence_level": EvidenceLevel.L2_FIXTURE_OR_DRY_RUN.value,
        "tools": [tool.model_dump(mode="json") for tool in list_toolbox_tools()],
    }


@router.post("/{tool_id}/plan")
async def plan_toolbox_run(tool_id: ToolboxToolId, body: dict[str, Any]) -> dict[str, Any]:
    request = _parse_toolbox_request(tool_id, body)
    return build_toolbox_plan(request).model_dump(mode="json", exclude_none=True)


@router.post("/{tool_id}/prompt-preview")
async def preview_toolbox_prompt(tool_id: ToolboxToolId, body: dict[str, Any]) -> dict[str, Any]:
    request = _parse_toolbox_request(tool_id, body)
    plan = build_toolbox_plan(request)
    return build_toolbox_prompt_preview(request, plan).model_dump(mode="json", exclude_none=True)


@router.post("/{tool_id}/run")
async def run_toolbox_dry_run(tool_id: ToolboxToolId, body: dict[str, Any]) -> dict[str, Any]:
    request = _parse_toolbox_request(tool_id, body)
    state = build_toolbox_run_state(request)
    _RUNS[state.run_id] = state
    return project_toolbox_run_state(state)


@router.get("/runs")
async def list_toolbox_runs(
    limit: int = Query(default=20, ge=1, le=100),
    tool_id: ToolboxToolId | None = None,
) -> dict[str, Any]:
    states = list(_RUNS.values())
    if tool_id is not None:
        states = [state for state in states if state.request.tool_id == tool_id]
    states = states[-limit:]
    states.reverse()
    return {
        "evidence_level": EvidenceLevel.L2_FIXTURE_OR_DRY_RUN.value,
        "runs": [project_toolbox_run_state(state) for state in states],
    }


@router.get("/runs/audit-summaries")
async def list_toolbox_run_audit_summaries(
    limit: int = Query(default=20, ge=1, le=100),
    tool_id: ToolboxToolId | None = None,
) -> ToolboxInjectionAuditSummaryList:
    states = list(_RUNS.values())
    if tool_id is not None:
        states = [state for state in states if state.request.tool_id == tool_id]
    states = states[-limit:]
    states.reverse()
    return ToolboxInjectionAuditSummaryList(
        summaries=[
            build_toolbox_injection_audit_summary(state)
            for state in states
        ]
    )


@router.get("/runs/{run_id}")
async def get_toolbox_run(run_id: str) -> dict[str, Any]:
    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Toolbox run not found")
    return project_toolbox_run_state(state)


@router.get("/runs/{run_id}/artifacts")
async def get_toolbox_run_artifacts(run_id: str) -> dict[str, Any]:
    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Toolbox run not found")
    return project_toolbox_artifacts(state)


@router.get("/runs/{run_id}/audit-summary")
async def get_toolbox_run_audit_summary(run_id: str) -> ToolboxInjectionAuditSummary:
    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Toolbox run not found")
    return build_toolbox_injection_audit_summary(state)


@router.post("/runs/{run_id}/inject")
async def preview_toolbox_injection_draft(run_id: str) -> ToolboxInjectionDraft:
    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Toolbox run not found")
    return build_toolbox_injection_draft(state)


def _parse_toolbox_request(tool_id: ToolboxToolId, body: dict[str, Any]) -> ToolboxRequest:
    body_tool_id = body.get("tool_id")
    if body_tool_id != tool_id.value:
        raise HTTPException(
            status_code=422,
            detail=f"toolbox path/body mismatch: path={tool_id.value}; body={body_tool_id}",
        )
    try:
        return ToolboxRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
