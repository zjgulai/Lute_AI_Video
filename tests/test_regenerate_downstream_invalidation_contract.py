"""Hermetic contract tests for regenerate downstream invalidation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_editor import invalidate_downstream

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "regenerate-downstream-invalidation-contract.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "regenerate-downstream-invalidation.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"


def test_regenerate_downstream_invalidation_contract_is_documented_and_in_scope() -> None:
    assert CONTRACT_PATH.exists(), "regenerate downstream invalidation contract config is missing"
    contract = yaml.safe_load(CONTRACT_PATH.read_text())
    scope_targets = {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert contract["gate_rule"] == "invalidate_gates_at_or_after_regenerated_step"
    assert RUNBOOK_PATH.exists(), "regenerate downstream invalidation runbook is missing"
    assert "docs/runbooks/regenerate-downstream-invalidation.md" in scope_targets


def _done_step(output: Any = None) -> dict[str, Any]:
    return {
        "status": "done",
        "output": output if output is not None else {"value": "old"},
        "edited": True,
        "edited_output": {"value": "old-edit"},
        "started_at": "2026-06-01T00:00:00",
        "completed_at": "2026-06-01T00:00:01",
        "duration_ms": 100,
    }


@pytest.mark.asyncio
async def test_regenerating_s1_scripts_invalidates_all_dependent_gates(isolated_state_dir):
    manager = PipelineStateManager()
    label = "regen-s1-script-gates"
    await manager.save(
        label,
        {
            "label": label,
            "scenario": "s1",
            "tenant_id": "default",
            "config": {},
            "current_step": "assemble_final",
            "steps": {
                "strategy": _done_step(),
                "scripts": _done_step([{"text": "old script"}]),
                "compliance": _done_step(),
                "storyboards": _done_step(),
                "continuity_storyboard_grid": _done_step(),
                "keyframe_images": _done_step(),
                "video_prompts": _done_step(),
                "thumbnail_prompts": _done_step(),
                "seedance_clips": _done_step(),
                "tts_audio": _done_step(),
                "thumbnail_images": _done_step(),
                "assemble_final": _done_step(),
                "audit": _done_step(),
            },
            "gates": {
                "gate_1_script": {"status": "approved", "approved": True, "selected_ids": ["old-script"]},
                "gate_2_keyframe": {"status": "approved", "approved": True, "selected_ids": ["old-frame"]},
                "gate_3_clips": {"status": "approved", "approved": True, "selected_ids": ["old-clip"]},
                "gate_4_final": {"status": "awaiting_approval", "approved": False, "candidates": [{"id": "old-final"}]},
            },
        },
    )

    updated = await invalidate_downstream(label, "scripts", manager)

    assert updated["current_step"] == "compliance"
    assert updated["steps"]["scripts"]["status"] == "done"
    assert updated["steps"]["compliance"]["status"] == "pending"
    assert updated["steps"]["compliance"]["output"] is None
    assert updated["steps"]["assemble_final"]["status"] == "pending"
    assert updated["steps"]["assemble_final"]["invalidated_by"] == "scripts"
    assert updated["gates"] == {}
    assert updated["invalidated_gates"] == [
        {
            "gate_id": "gate_1_script",
            "after_step": "scripts",
            "invalidated_by": "scripts",
        },
        {
            "gate_id": "gate_2_keyframe",
            "after_step": "keyframe_images",
            "invalidated_by": "scripts",
        },
        {
            "gate_id": "gate_3_clips",
            "after_step": "seedance_clips",
            "invalidated_by": "scripts",
        },
        {
            "gate_id": "gate_4_final",
            "after_step": "assemble_final",
            "invalidated_by": "scripts",
        },
    ]


@pytest.mark.asyncio
async def test_regenerating_s1_keyframes_preserves_upstream_script_gate(isolated_state_dir):
    manager = PipelineStateManager()
    label = "regen-s1-keyframe-gates"
    await manager.save(
        label,
        {
            "label": label,
            "scenario": "s1",
            "tenant_id": "default",
            "config": {},
            "current_step": "assemble_final",
            "steps": {
                "strategy": _done_step(),
                "scripts": _done_step(),
                "compliance": _done_step(),
                "storyboards": _done_step(),
                "continuity_storyboard_grid": _done_step(),
                "keyframe_images": _done_step(),
                "video_prompts": _done_step(),
                "seedance_clips": _done_step(),
                "assemble_final": _done_step(),
                "audit": _done_step(),
            },
            "gates": {
                "gate_1_script": {"status": "approved", "approved": True, "selected_ids": ["script-c1"]},
                "gate_2_keyframe": {"status": "approved", "approved": True, "selected_ids": ["frame-c1"]},
                "gate_3_clips": {"status": "approved", "approved": True, "selected_ids": ["clip-c1"]},
                "gate_4_final": {"status": "approved", "approved": True, "selected_ids": ["final-c1"]},
            },
        },
    )

    updated = await invalidate_downstream(label, "keyframe_images", manager)

    assert updated["current_step"] == "video_prompts"
    assert updated["gates"] == {
        "gate_1_script": {"status": "approved", "approved": True, "selected_ids": ["script-c1"]},
    }
    assert [entry["gate_id"] for entry in updated["invalidated_gates"]] == [
        "gate_2_keyframe",
        "gate_3_clips",
        "gate_4_final",
    ]
