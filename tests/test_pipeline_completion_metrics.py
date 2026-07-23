from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.storage.repository import PipelineStateRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINES = (
    "s1_product_pipeline.py",
    "s2_brand_pipeline_v2.py",
    "s3_remix_pipeline.py",
    "s4_live_shoot_pipeline.py",
    "s5_brand_vlog_pipeline.py",
)


class MemoryStateManager:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, Any]] = {}

    async def save(self, label: str, state: dict[str, Any]) -> None:
        self.saved[label] = deepcopy(state)

    async def load(self, label: str) -> dict[str, Any] | None:
        state = self.saved.get(label)
        return deepcopy(state) if state is not None else None


def _terminal_state(
    *,
    lifecycle_status: str = "completed_bounded",
    degraded: bool = False,
    current_step: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "label": "s1_completion_fixture",
        "scenario": "s1",
        "config": {},
        "lifecycle_status": lifecycle_status,
        "current_step": current_step,
        "pipeline_degraded": degraded,
        "errors": list(errors or []),
        "trace_id": "trace-completion-fixture",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle_status", ["completed_bounded", "completed_full"])
async def test_successful_terminal_completion_is_claimed_and_emitted_once(
    lifecycle_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MemoryStateManager()
    runner = StepRunner(cast(Any, manager))
    state = _terminal_state(lifecycle_status=lifecycle_status)
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    assert await runner.finalize_pipeline_completion(
        state,
        started_at=time.perf_counter() - 0.01,
    )
    reloaded = await manager.load(state["label"])
    assert reloaded is not None
    second_runner = StepRunner(cast(Any, manager))
    assert not await second_runner.finalize_pipeline_completion(
        reloaded,
        started_at=time.perf_counter() - 0.02,
    )

    assert len(recorded) == 1
    assert recorded[0]["success"] is True
    claim = reloaded["config"]["pipeline_completion_metric_v1"]
    assert claim["version"] == "pipeline-completion-metric.v1"
    assert claim["outcome"] == "success"


@pytest.mark.asyncio
async def test_repeated_degraded_completion_is_one_persisted_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MemoryStateManager()
    runner = StepRunner(cast(Any, manager))
    state = _terminal_state(
        lifecycle_status="running",
        degraded=True,
        current_step="strategy",
        errors=["strategy_failed"],
    )
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    assert await runner.finalize_pipeline_completion(
        state,
        started_at=time.perf_counter(),
    )
    reloaded = await manager.load(state["label"])
    assert reloaded is not None
    assert not await runner.finalize_pipeline_completion(
        reloaded,
        started_at=time.perf_counter(),
    )

    assert len(recorded) == 1
    assert recorded[0]["success"] is False
    assert recorded[0]["error_count"] == 1


@pytest.mark.asyncio
async def test_concurrent_independent_runners_emit_one_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MemoryStateManager()
    state = _terminal_state()
    await manager.save(state["label"], state)
    first = await manager.load(state["label"])
    second = await manager.load(state["label"])
    assert first is not None and second is not None
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    results = await asyncio.gather(
        StepRunner(cast(Any, manager)).finalize_pipeline_completion(
            first,
            started_at=time.perf_counter(),
        ),
        StepRunner(cast(Any, manager)).finalize_pipeline_completion(
            second,
            started_at=time.perf_counter(),
        ),
    )

    assert sorted(results) == [False, True]
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_filesystem_completion_claim_is_atomic_across_managers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    first_manager = PipelineStateManager(use_pg=False)
    second_manager = PipelineStateManager(use_pg=False)
    state = _terminal_state()
    await first_manager.save(state["label"], state)
    first = deepcopy(state)
    second = deepcopy(state)
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    results = await asyncio.gather(
        StepRunner(first_manager).finalize_pipeline_completion(
            first,
            started_at=time.perf_counter(),
        ),
        StepRunner(second_manager).finalize_pipeline_completion(
            second,
            started_at=time.perf_counter(),
        ),
    )

    assert sorted(results) == [False, True]
    assert len(recorded) == 1
    persisted = first_manager._load_from_fs(state["label"])
    assert persisted is not None
    assert "pipeline_completion_metric_v1" in persisted["config"]


@pytest.mark.asyncio
async def test_filesystem_stale_save_cannot_delete_completion_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    manager = PipelineStateManager(use_pg=False)
    original = _terminal_state()
    await manager.save(original["label"], original)
    first = deepcopy(original)
    stale_save = deepcopy(original)
    stale_finalize = deepcopy(original)
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    assert await StepRunner(manager).finalize_pipeline_completion(
        first,
        started_at=time.perf_counter(),
    )
    await manager.save(original["label"], stale_save)
    assert not await StepRunner(manager).finalize_pipeline_completion(
        stale_finalize,
        started_at=time.perf_counter(),
    )

    persisted = manager._load_from_fs(original["label"])
    assert persisted is not None
    assert "pipeline_completion_metric_v1" in persisted["config"]
    assert len(recorded) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("durable_failure", [False, True])
async def test_filesystem_stale_finalizer_emits_current_durable_outcome(
    durable_failure: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    manager = PipelineStateManager(use_pg=False)
    durable = (
        _terminal_state(
            lifecycle_status="running",
            degraded=True,
            current_step="strategy",
            errors=["strategy_failed"],
        )
        if durable_failure
        else _terminal_state()
    )
    stale = (
        _terminal_state()
        if durable_failure
        else _terminal_state(
            lifecycle_status="running",
            degraded=True,
            current_step="strategy",
            errors=["strategy_failed"],
        )
    )
    await manager.save(durable["label"], durable)
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    assert await StepRunner(manager).finalize_pipeline_completion(
        stale,
        started_at=time.perf_counter(),
    )

    persisted = manager._load_from_fs(durable["label"])
    assert persisted is not None
    claim = persisted["config"]["pipeline_completion_metric_v1"]
    assert claim["outcome"] == ("failure" if durable_failure else "success")
    assert claim["error_count"] == (1 if durable_failure else 0)
    assert [item["success"] for item in recorded] == [not durable_failure]


@pytest.mark.asyncio
async def test_sqlite_completion_claim_uses_one_write_winner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.storage import repository as repository_module

    connection = sqlite3.connect(tmp_path / "completion.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE pipeline_states (
            id TEXT PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            scenario TEXT,
            config TEXT NOT NULL,
            current_step TEXT,
            errors TEXT NOT NULL,
            pipeline_degraded BOOLEAN NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO pipeline_states (
            id, label, scenario, config, current_step, errors,
            pipeline_degraded
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "state-id",
            "s1_sqlite_completion",
            "s1",
            json.dumps(
                {
                    "execution_lifecycle": {
                        "lifecycle_status": "completed_bounded"
                    }
                }
            ),
            None,
            json.dumps([]),
            False,
        ),
    )
    connection.commit()
    lock = threading.RLock()

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(repository_module, "get_pool", no_pool)
    monkeypatch.setattr(repository_module, "get_sqlite_conn", lambda: connection)
    monkeypatch.setattr(repository_module, "get_sqlite_lock", lambda: lock)
    first_claim = {"version": "pipeline-completion-metric.v1", "outcome": "success"}
    second_claim = {"version": "pipeline-completion-metric.v1", "outcome": "failure"}

    results = await asyncio.gather(
        PipelineStateRepository().claim_pipeline_completion(
            "s1_sqlite_completion",
            first_claim,
        ),
        PipelineStateRepository().claim_pipeline_completion(
            "s1_sqlite_completion",
            second_claim,
        ),
    )

    winners = [result for result in results if type(result) is dict]
    assert len(winners) == 1
    assert results.count(False) == 1
    row = connection.execute(
        "SELECT config FROM pipeline_states WHERE label = ?",
        ("s1_sqlite_completion",),
    ).fetchone()
    assert row is not None
    stored_claim = json.loads(row["config"])["pipeline_completion_metric_v1"]
    assert stored_claim == winners[0]
    assert stored_claim["outcome"] == "success"

    await PipelineStateRepository().update("state-id", {"config": {}})
    stale_row = connection.execute(
        "SELECT config FROM pipeline_states WHERE label = ?",
        ("s1_sqlite_completion",),
    ).fetchone()
    assert stale_row is not None
    assert json.loads(stale_row["config"])["pipeline_completion_metric_v1"] == stored_claim
    assert not await PipelineStateRepository().claim_pipeline_completion(
        "s1_sqlite_completion",
        second_claim,
    )
    connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("durable_failure", [False, True])
async def test_sqlite_stale_claim_is_rebound_to_current_durable_outcome(
    durable_failure: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.storage import repository as repository_module

    connection = sqlite3.connect(
        tmp_path / f"completion-conflict-{durable_failure}.db",
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE pipeline_states (
            id TEXT PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            scenario TEXT,
            config TEXT NOT NULL,
            current_step TEXT,
            errors TEXT NOT NULL,
            pipeline_degraded BOOLEAN NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    lifecycle_status = "running" if durable_failure else "completed_bounded"
    connection.execute(
        """
        INSERT INTO pipeline_states (
            id, label, scenario, config, current_step, errors,
            pipeline_degraded
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "state-id",
            "s1_sqlite_conflict",
            "s1",
            json.dumps(
                {
                    "execution_lifecycle": {
                        "lifecycle_status": lifecycle_status
                    }
                }
            ),
            "strategy" if durable_failure else None,
            json.dumps(["strategy_failed"] if durable_failure else []),
            durable_failure,
        ),
    )
    connection.commit()
    lock = threading.RLock()

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(repository_module, "get_pool", no_pool)
    monkeypatch.setattr(repository_module, "get_sqlite_conn", lambda: connection)
    monkeypatch.setattr(repository_module, "get_sqlite_lock", lambda: lock)
    proposed = {
        "version": "pipeline-completion-metric.v1",
        "outcome": "success" if durable_failure else "failure",
        "claimed_at": "2026-07-22T00:00:00+00:00",
        "duration_ms": 1.0,
        "error_count": 0 if durable_failure else 1,
        "scenario": "stale",
    }

    winning = await PipelineStateRepository().claim_pipeline_completion(
        "s1_sqlite_conflict",
        proposed,
    )

    assert type(winning) is dict
    assert winning["outcome"] == ("failure" if durable_failure else "success")
    assert winning["error_count"] == (1 if durable_failure else 0)
    assert winning["scenario"] == "s1"
    row = connection.execute(
        "SELECT config FROM pipeline_states WHERE label = ?",
        ("s1_sqlite_conflict",),
    ).fetchone()
    assert row is not None
    assert json.loads(row["config"])["pipeline_completion_metric_v1"] == winning
    connection.close()


@pytest.mark.asyncio
async def test_postgres_state_update_query_preserves_existing_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage import repository as repository_module

    queries: list[str] = []
    durable_claim = {
        "version": "pipeline-completion-metric.v1",
        "outcome": "success",
    }

    class FakeConnection:
        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            del args
            queries.append(query)
            return {
                "id": "state-id",
                "config": json.dumps(
                    {"pipeline_completion_metric_v1": durable_claim}
                ),
            }

    class Acquire:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *args: Any) -> None:
            del args

    class FakePool:
        def acquire(self) -> Acquire:
            return Acquire()

    async def fake_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(repository_module, "get_pool", fake_pool)

    updated = await PipelineStateRepository().update(
        "state-id",
        {"config": {}, "scenario": "s1"},
    )

    assert updated is not None
    assert updated["config"]["pipeline_completion_metric_v1"] == durable_claim
    assert len(queries) == 1
    assert "WHEN COALESCE(config, '{}'::jsonb) ? 'pipeline_completion_metric_v1'" in queries[0]
    assert "jsonb_set" in queries[0]
    assert "RETURNING *" in queries[0]


@pytest.mark.asyncio
async def test_configured_postgres_down_cannot_fallback_completion_to_filesystem(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.pipeline import state_manager as state_manager_module

    monkeypatch.setenv("DATABASE_URL", "postgresql://configured.invalid/fixture")
    monkeypatch.setattr(state_manager_module, "HAS_STORAGE", True)
    monkeypatch.setattr(state_manager_module, "is_pg_available", lambda: False)
    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    manager = PipelineStateManager(use_pg=True)
    state = _terminal_state()

    with pytest.raises(RuntimeError, match="pipeline completion store is unavailable"):
        await manager.claim_pipeline_completion(
            state["label"],
            state,
            {"version": "pipeline-completion-metric.v1", "outcome": "success"},
        )

    assert not manager._state_path(state["label"]).exists()


@pytest.mark.asyncio
async def test_postgres_winning_claim_does_not_overwrite_cache_with_stale_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.pipeline import state_manager as state_manager_module

    winning_claim = {
        "version": "pipeline-completion-metric.v1",
        "outcome": "failure",
        "claimed_at": "2026-07-22T00:00:00+00:00",
        "duration_ms": 1.0,
        "error_count": 1,
        "scenario": "s1",
    }

    class FakeRepository:
        async def claim_pipeline_completion(
            self,
            label: str,
            claim: dict[str, Any],
        ) -> dict[str, Any]:
            del label, claim
            return dict(winning_claim)

    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(state_manager_module, "is_pg_available", lambda: True)
    monkeypatch.setattr(
        state_manager_module,
        "PipelineStateRepository",
        FakeRepository,
    )
    manager = PipelineStateManager(use_pg=True)
    durable_failure = _terminal_state(
        lifecycle_status="running",
        degraded=True,
        current_step="strategy",
        errors=["strategy_failed"],
    )
    manager._save_to_fs(durable_failure["label"], durable_failure)
    stale_success = _terminal_state()

    result = await manager.claim_pipeline_completion(
        stale_success["label"],
        stale_success,
        {
            **winning_claim,
            "outcome": "success",
            "error_count": 0,
        },
    )

    assert result == winning_claim
    cached = manager._load_from_fs(durable_failure["label"])
    assert cached is not None
    assert cached["pipeline_degraded"] is True
    assert cached["errors"] == ["strategy_failed"]
    assert cached["config"]["pipeline_completion_metric_v1"] == winning_claim


@pytest.mark.asyncio
async def test_nonterminal_state_is_not_claimed_or_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MemoryStateManager()
    runner = StepRunner(cast(Any, manager))
    state = _terminal_state(lifecycle_status="running", current_step="strategy")
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.pipeline.step_runner.pipeline_metrics.record_pipeline",
        lambda **kwargs: recorded.append(kwargs),
    )

    assert not await runner.finalize_pipeline_completion(
        state,
        started_at=time.perf_counter(),
    )
    assert recorded == []
    assert manager.saved == {}


@pytest.mark.asyncio
async def test_caller_cannot_preseed_terminal_completion_claim() -> None:
    runner = StepRunner(cast(Any, MemoryStateManager()))

    with pytest.raises(ValueError, match="server-owned"):
        await runner.init_state(
            config={
                "pipeline_completion_metric_v1": {
                    "version": "pipeline-completion-metric.v1",
                }
            },
            label="caller-owned-completion-claim",
        )


@pytest.mark.asyncio
async def test_malformed_persisted_completion_claim_fails_closed() -> None:
    runner = StepRunner(cast(Any, MemoryStateManager()))
    state = _terminal_state()
    state["config"]["pipeline_completion_metric_v1"] = {
        "version": "pipeline-completion-metric.v1",
        "outcome": "success",
    }

    with pytest.raises(ValueError, match="pipeline_completion_metric_invalid"):
        await runner.finalize_pipeline_completion(
            state,
            started_at=time.perf_counter(),
        )


def test_all_scenario_wrappers_share_the_terminal_completion_finalizer() -> None:
    for filename in PIPELINES:
        source = (REPO_ROOT / "src" / "pipeline" / filename).read_text()
        assert source.count("await runner.finalize_pipeline_completion(") == 1, filename


def test_stalled_rule_is_absent_until_a_real_inflight_pipeline_signal_exists() -> None:
    rules = (REPO_ROOT / "deploy" / "lighthouse" / "prometheus-alerts.yml").read_text()
    fixtures = (REPO_ROOT / "tests" / "fixtures" / "prometheus-alerts.test.yml").read_text()
    assert "PipelineStalled" not in rules
    assert "PipelineStalled" not in fixtures
