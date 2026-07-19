"""Hermetic contract tests for persisted scenario pipeline state JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.step_runner import StepRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "scenario-state-persistence-contract.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "scenario-state-persistence-schema.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
FRESH_INIT_SQL_PATH = REPO_ROOT / "src" / "storage" / "migrations" / "001_init.sql"


def _load_contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "scenario state persistence contract config is missing"
    data = yaml.safe_load(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "scenario state persistence contract must be a YAML object"
    return data


def test_scenario_state_persistence_contract_is_documented_and_in_scope():
    contract = _load_contract()
    scope_targets = {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert contract["scenarios"] == ["s1", "s2", "s3", "s4", "s5"]
    assert RUNBOOK_PATH.exists(), "scenario state persistence schema runbook is missing"
    assert "docs/runbooks/scenario-state-persistence-schema.md" in scope_targets


def test_fresh_init_schema_contains_regeneration_audit_columns() -> None:
    sql = FRESH_INIT_SQL_PATH.read_text()

    assert (
        "ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS regenerate_chain "
        "JSONB DEFAULT '[]';"
    ) in sql
    assert (
        "ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS soft_degraded_reasons "
        "JSONB DEFAULT '[]';"
    ) in sql


def _contract_state(label: str = "contract-pg-projection") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "label": label,
        "scenario": "s1",
        "tenant_id": "tenant-contract",
        "config": {"tenant_id": "tenant-contract"},
        "steps": {},
        "current_step": "strategy",
        "mode": "step_by_step",
        "trace_id": "trace-contract",
        "errors": [],
        "media_synthesis_errors": [],
        "gates": {},
        "pipeline_degraded": False,
        "degraded_reason": None,
        "structured_errors": [],
    }


def test_repository_payload_coerces_trace_id_to_string():
    from src.pipeline.state_manager import _repository_payload

    payload = _repository_payload({
        **_contract_state(),
        "trace_id": 55663019,
    })

    assert payload["trace_id"] == "55663019"


def test_pg_projection_preserves_bounded_lifecycle_via_persisted_config():
    from src.pipeline.state_manager import _hydrate_execution_lifecycle, _repository_payload

    state = {
        **_contract_state(label="bounded-pg-projection"),
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "no_media",
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
        "execution_profile_id": "generation-execution.v1:s1:no-media",
        "provider_job_caps": {},
    }
    state["config"].update(
        {
            "effective_generation_execution_profile": {
                "profile_id": "generation-execution.v1:s1:no-media",
                "provider_job_caps": {},
            },
            "provider_job_caps": {},
        }
    )

    payload = _repository_payload(state)
    pg_projection = {"label": state["label"], **payload}
    hydrated = _hydrate_execution_lifecycle(pg_projection)

    assert hydrated["status"] == "completed_bounded"
    assert hydrated["lifecycle_status"] == "completed_bounded"
    assert hydrated["completion_kind"] == "no_media"
    assert hydrated["request_succeeded"] is True
    assert hydrated["success"] is False
    assert hydrated["full_media_success"] is False
    assert hydrated["pipeline_complete"] is False
    assert hydrated["publish_allowed"] is False
    assert hydrated["delivery_accepted"] is False
    assert hydrated["execution_profile_id"] == "generation-execution.v1:s1:no-media"
    assert hydrated["provider_job_caps"] == {}


def test_lifecycle_hydration_rejects_success_escalation() -> None:
    from src.pipeline.state_manager import _hydrate_execution_lifecycle

    state = _contract_state(label="tampered-lifecycle")
    state["config"]["execution_lifecycle"] = {
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "no_media",
        "request_succeeded": True,
        "success": True,
        "full_media_success": True,
        "pipeline_complete": True,
        "publish_allowed": True,
        "delivery_accepted": True,
    }

    with pytest.raises(ValueError, match="lifecycle"):
        _hydrate_execution_lifecycle(state)


def test_lifecycle_hydration_rejects_top_level_only_claims() -> None:
    from src.pipeline.state_manager import _hydrate_execution_lifecycle

    state = {
        **_contract_state(label="top-level-only-lifecycle"),
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "success": False,
    }

    with pytest.raises(ValueError, match="envelope"):
        _hydrate_execution_lifecycle(state)


def test_lifecycle_hydration_rejects_top_level_envelope_mismatch() -> None:
    from src.pipeline.state_manager import _hydrate_execution_lifecycle

    state = _contract_state(label="mismatched-lifecycle")
    state["config"]["execution_lifecycle"] = {
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "no_media",
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    state["success"] = True

    with pytest.raises(ValueError, match="mismatch"):
        _hydrate_execution_lifecycle(state)


def test_lifecycle_hydration_rejects_profile_and_caps_claim_tamper() -> None:
    from src.pipeline.state_manager import _hydrate_execution_lifecycle

    lifecycle = {
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "bounded_media",
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
        "execution_profile_id": "generation-execution.v1:s1:tampered",
        "provider_job_caps": {"video": True},
    }
    state = {
        **_contract_state(label="tampered-profile-lifecycle"),
        **lifecycle,
    }
    state["config"].update(
        {
            "effective_generation_execution_profile": {
                "profile_id": "generation-execution.v1:s1:bounded-seedance",
                "provider_job_caps": {"video": 1},
            },
            "provider_job_caps": {"video": 1},
            "execution_lifecycle": dict(lifecycle),
        }
    )

    with pytest.raises(ValueError, match="profile/caps"):
        _hydrate_execution_lifecycle(state)


def test_pg_projection_preserves_regenerate_audit_fields() -> None:
    from src.pipeline.state_manager import _repository_payload

    payload = _repository_payload(
        {
            **_contract_state(label="regenerate-audit-pg"),
            "regenerate_chain": [{"upstream_step": "scripts", "attempt": 1}],
            "soft_degraded_reasons": [{"reason": "fixture"}],
        }
    )

    assert payload["regenerate_chain"] == [
        {"upstream_step": "scripts", "attempt": 1}
    ]
    assert payload["soft_degraded_reasons"] == [{"reason": "fixture"}]


def test_preexecution_provider_caps_do_not_create_partial_lifecycle_envelope() -> None:
    from src.pipeline.state_manager import _repository_payload

    state = {
        **_contract_state(label="preexecution-caps"),
        "provider_job_caps": {"video": 1},
    }
    state["config"]["provider_job_caps"] = {"video": 1}

    payload = _repository_payload(state)

    assert "execution_lifecycle" not in payload["config"]


@pytest.mark.asyncio
async def test_real_state_manager_pg_roundtrip_preserves_bounded_lifecycle_and_audit_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import state_manager as state_manager_module

    rows: dict[str, dict[str, Any]] = {}

    class FakeRepository:
        async def get_by_label(self, label: str) -> dict[str, Any] | None:
            row = rows.get(label)
            return dict(row) if row is not None else None

        async def create(self, data: dict[str, Any]) -> None:
            rows[data["label"]] = {"id": "row-1", **data}

        async def update(self, row_id: str, data: dict[str, Any]) -> None:
            assert row_id == "row-1"
            label = next(label for label, row in rows.items() if row["id"] == row_id)
            rows[label] = {"id": row_id, "label": label, **data}

    monkeypatch.setattr(state_manager_module.PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(state_manager_module, "HAS_STORAGE", True)
    monkeypatch.setattr(state_manager_module, "is_pg_available", lambda: True)
    monkeypatch.setattr(state_manager_module, "PipelineStateRepository", FakeRepository)

    profile_id = "generation-execution.v1:s1:no-media"
    lifecycle = {
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "no_media",
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
        "execution_profile_id": profile_id,
        "provider_job_caps": {},
    }
    state = {
        **_contract_state(label="bounded-real-pg-roundtrip"),
        **lifecycle,
        "regenerate_chain": [{"upstream_step": "scripts", "attempt": 1}],
        "soft_degraded_reasons": [{"reason": "optional fixture fallback"}],
    }
    state["config"].update(
        {
            "effective_generation_execution_profile": {
                "profile_id": profile_id,
                "provider_job_caps": {},
            },
            "provider_job_caps": {},
            "execution_lifecycle": dict(lifecycle),
        }
    )

    manager = state_manager_module.PipelineStateManager(use_pg=True)
    await manager.save(state["label"], state)
    loaded = await manager.load(state["label"])
    fs_state = json.loads(
        (tmp_path / "pipeline_states" / f"{state['label']}.json").read_text()
    )

    assert rows[state["label"]]["regenerate_chain"] == state["regenerate_chain"]
    assert rows[state["label"]]["soft_degraded_reasons"] == state["soft_degraded_reasons"]
    assert fs_state == state
    assert loaded == state


@pytest.mark.asyncio
async def test_pg_backfill_preserves_contract_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    contract = _load_contract()

    from src.pipeline import state_manager as state_manager_module

    created_rows: list[dict[str, Any]] = []

    class FakeRepository:
        async def get_by_label(self, label: str) -> None:
            return None

        async def create(self, data: dict[str, Any]) -> None:
            created_rows.append(data)

    monkeypatch.setattr(state_manager_module.PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(state_manager_module, "is_pg_available", lambda: True)
    monkeypatch.setattr(state_manager_module, "PipelineStateRepository", FakeRepository)

    manager = state_manager_module.PipelineStateManager(use_pg=False)
    state = _contract_state()
    await manager.save(state["label"], state)

    manager.use_pg = True
    loaded = await manager.load(state["label"])

    assert loaded == state
    assert len(created_rows) == 1
    missing = set(contract["required_top_level_keys"]) - set(created_rows[0])
    assert missing == set()


@pytest.mark.asyncio
async def test_fs_to_pg_migration_preserves_contract_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = _load_contract()

    from src.pipeline import state_manager as state_manager_module

    created_rows: list[dict[str, Any]] = []

    class FakeRepository:
        async def get_by_label(self, label: str) -> None:
            return None

        async def create(self, data: dict[str, Any]) -> None:
            created_rows.append(data)

    monkeypatch.setattr(state_manager_module.PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(state_manager_module, "PipelineStateRepository", FakeRepository)
    monkeypatch.setattr(state_manager_module, "HAS_STORAGE", True)

    manager = state_manager_module.PipelineStateManager(use_pg=False)
    state = _contract_state(label="contract-migrate")
    await manager.save(state["label"], state)

    migrated_count = await state_manager_module.PipelineStateManager.migrate_from_fs_to_pg()

    assert migrated_count == 1
    assert len(created_rows) == 1
    missing = set(contract["required_top_level_keys"]) - set(created_rows[0])
    assert missing == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
async def test_init_state_persists_contract_shape_for_all_scenarios(
    scenario: str,
    isolated_state_dir: Path,
):
    contract = _load_contract()

    from src.pipeline.state_manager import PipelineStateManager

    manager = PipelineStateManager()
    runner = StepRunner(manager)
    label = f"contract-{scenario}"
    config = {"tenant_id": f"tenant-{scenario}", "product": {"name": f"Fixture {scenario}"}}

    saved_label = await runner.init_state(
        config=config,
        mode="step_by_step",
        label=label,
        scenario=scenario,
    )

    assert saved_label == label
    state_path = isolated_state_dir / "pipeline_states" / f"{label}.json"
    persisted = json.loads(state_path.read_text())

    missing = set(contract["required_top_level_keys"]) - set(persisted)
    assert missing == set()

    assert persisted["label"] == label
    assert persisted["scenario"] == scenario
    assert persisted["mode"] in contract["allowed_modes"]
    assert persisted["tenant_id"] == f"tenant-{scenario}"
    assert isinstance(persisted["schema_version"], int)
    assert isinstance(persisted["trace_id"], str) and persisted["trace_id"]
    assert persisted["pipeline_degraded"] is False
    assert persisted["degraded_reason"] is None

    for key in contract["json_object_keys"]:
        assert isinstance(persisted[key], dict), f"{key} must persist as JSON object"
    for key in contract["json_array_keys"]:
        assert isinstance(persisted[key], list), f"{key} must persist as JSON array"

    expected_steps = get_scenario_step_order(scenario)
    assert list(persisted["steps"]) == expected_steps
    assert persisted["current_step"] == expected_steps[0]
    assert persisted["gates"] == {}

    step_required_keys = set(contract["step_record_required_keys"])
    for step_name, step_record in persisted["steps"].items():
        assert set(step_record) == step_required_keys, step_name
        assert step_record["status"] == "pending"
        assert step_record["output"] is None
        assert step_record["edited"] is False
        assert step_record["edited_output"] is None
        assert step_record["started_at"] == ""
        assert step_record["completed_at"] == ""
        assert step_record["duration_ms"] == 0
