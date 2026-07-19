"""Hermetic idempotency guards for scenario gate approval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.pipeline.gate_manager import approve_gate
from src.pipeline.state_manager import PipelineStateManager

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "gate-approve-idempotency-contract.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "gate-approve-idempotency.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"


def test_gate_approve_idempotency_contract_is_documented_and_in_scope() -> None:
    assert CONTRACT_PATH.exists(), "gate approve idempotency contract config is missing"
    contract = yaml.safe_load(CONTRACT_PATH.read_text())
    scope_targets = {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert contract["retry_same_selection"]["result"] == "idempotent_success"
    assert contract["retry_different_selection"]["result"] == "conflict_error"
    assert RUNBOOK_PATH.exists(), "gate approve idempotency runbook is missing"
    assert "docs/runbooks/gate-approve-idempotency.md" in scope_targets


def _gate_1_state(label: str = "gate-approve-idempotency") -> dict[str, Any]:
    from src.pipeline.generation_policy import (
        EffectiveGenerationPolicy,
        resolve_generation_execution_profile,
    )

    policy = EffectiveGenerationPolicy(
        tenant_id="default",
        scenario="s1",
        enable_media_synthesis=False,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )
    state = {
        "schema_version": 1,
        "label": label,
        "scenario": "s1",
        "tenant_id": "default",
        "config": {
            "product_catalog": {"product_name": "Test"},
            "brand_guidelines": {},
            "enable_media_synthesis": False,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
            "effective_generation_policy": policy.model_dump(mode="json"),
        },
        "steps": {
            "strategy": {"output": {}, "status": "done"},
            "scripts": {"output": [{"text": "original"}], "status": "done"},
        },
        "current_step": "scripts",
        "gates": {
            "gate_1_script": {
                "status": "awaiting_approval",
                "candidates": [
                    {
                        "id": "c1",
                        "variant": "creative",
                        "data": {"scripts": [{"text": "creative script"}]},
                        "score": {"overall": 0.9},
                    }
                ],
                "selected_ids": [],
                "approved": False,
            }
        },
    }
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    state["config"]["effective_generation_execution_profile"] = profile.model_dump()
    state["config"]["provider_job_caps"] = dict(profile.provider_job_caps)
    return state


@pytest.mark.asyncio
async def test_repeated_approve_same_selection_is_idempotent_and_preserves_state(
    isolated_state_dir,
    monkeypatch: pytest.MonkeyPatch,
):
    manager = PipelineStateManager()
    state = _gate_1_state()
    await manager.save(state["label"], state)

    first = await approve_gate(state["label"], "gate_1_script", ["c1"])
    first_state = await manager.load(state["label"])

    retry_saves = 0
    original_save = PipelineStateManager.save

    async def counted_save(
        self: PipelineStateManager,
        label: str,
        value: dict[str, Any],
    ) -> None:
        nonlocal retry_saves
        retry_saves += 1
        await original_save(self, label, value)

    monkeypatch.setattr(PipelineStateManager, "save", counted_save)

    retry = await approve_gate(state["label"], "gate_1_script", ["c1"])
    retry_state = await manager.load(state["label"])

    assert "error" not in retry
    assert first["approved"] is True
    assert first["idempotent"] is False
    assert retry["approved"] is True
    assert retry["idempotent"] is True
    assert retry["selected_ids"] == ["c1"]
    assert retry["selected_variants"] == ["creative"]
    assert retry["next_step"] == "compliance"
    assert retry_state == first_state
    assert retry_saves == 0


@pytest.mark.asyncio
async def test_router_does_not_start_background_resume_for_idempotent_approve(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.routers import scenario

    create_task_calls: list[object] = []
    register_calls: list[object] = []

    class FakeStateManager:
        async def load(self, label: str) -> dict[str, Any]:
            return {"label": label, "tenant_id": "default", "scenario": "s1"}

    async def fake_approve_gate(label: str, gate_id: str, selected_ids: list[str]) -> dict[str, Any]:
        return {
            "gate_id": gate_id,
            "label": label,
            "approved": True,
            "idempotent": True,
            "selected_ids": selected_ids,
            "selected_variants": ["creative"],
            "next_step": "compliance",
        }

    def fake_create_task(coro: Any) -> object:
        create_task_calls.append(coro)
        coro.close()
        return object()

    def fake_register_background_task(task: object, label: str) -> str:
        register_calls.append((task, label))
        return "task-id"

    monkeypatch.setattr("src.pipeline.state_manager.PipelineStateManager", FakeStateManager)
    monkeypatch.setattr("src.pipeline.gate_manager.approve_gate", fake_approve_gate)
    monkeypatch.setattr(scenario.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(scenario, "_register_background_task", fake_register_background_task)

    result = await scenario.approve_gate_decision(
        "s1",
        "gate-approve-idempotency",
        "gate_1_script",
        {"selected_ids": ["c1"]},
    )

    assert result["approved"] is True
    assert result["idempotent"] is True
    assert result["resumed"] is False
    assert result["resuming"] is False
    assert "background_task_id" not in result
    assert create_task_calls == []
    assert register_calls == []
