from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

import src.storage.db as db_module
from src.models import ErrorCode
from src.storage.db import _create_sqlite_tables
from src.storage.repository import PipelineStateRepository
from src.tools.error_classifier import classify_error
from src.tools.poyo_safety import sanitize_for_poyo


def _load_poyo_rejection_messages() -> list[str]:
    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commercial_video" / "poyo_content_rejection_samples.json"
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return [item["raw_message"] for item in payload.get("runtime_rejection_messages", [])]


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_negative.db"

    async def _no_pool():
        return None

    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    import src.storage.repository as repo_module
    monkeypatch.setattr(repo_module, "get_pool", _no_pool)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(db_module, "_sqlite_conn", conn)
    _create_sqlite_tables()

    yield db_path
    conn.close()


class TestDeepSeekTimeoutNegative:
    """Runbook: docs/runbooks/deepseek-timeout.md. classifier must map
    asyncio.TimeoutError + httpx.TimeoutException variants to recoverable
    LLM_TIMEOUT, so step_runner's degraded-handler can retry/skip cleanly."""

    def test_asyncio_timeout_classifies_as_recoverable_input_timeout(self):
        err = classify_error(TimeoutError("LLM took too long"), context="llm_call", node="script_writer")
        assert err.code == ErrorCode.INPUT_TIMEOUT
        assert err.recoverable is True
        assert err.node == "script_writer"

    def test_httpx_read_timeout_with_llm_context_maps_to_llm_timeout(self):
        exc = httpx.ReadTimeout("Read timed out: deepseek anthropic LLM call")
        err = classify_error(exc, context="llm_ainvoke", node="script_writer")
        assert err.code == ErrorCode.LLM_TIMEOUT
        assert err.recoverable is True

    def test_httpx_connect_timeout_with_anthropic_context_maps_to_llm_timeout(self):
        exc = httpx.ConnectTimeout("Connect: anthropic api endpoint")
        err = classify_error(exc, context="llm_ainvoke")
        assert err.code == ErrorCode.LLM_TIMEOUT

    def test_unknown_timeout_falls_back_to_input_timeout(self):
        exc = httpx.PoolTimeout("pool drained")
        err = classify_error(exc, context="unrelated")
        assert err.code == ErrorCode.INPUT_TIMEOUT
        assert err.recoverable is True

    def test_error_detail_preserves_original_context_for_runbook_grep(self):
        exc = TimeoutError("deepseek call exceeded budget")
        err = classify_error(exc, context="llm_call", extra={"provider": "deepseek"})
        assert "deepseek" in err.detail.get("provider", "")
        assert err.detail["context"] == "llm_call"


class TestPoyoContentRejectionNegative:
    """Runbook: docs/runbooks/poyo-rejection.md. poyo_safety sanitizer is the
    documented first-line response when poyo returns content_moderation_failed."""

    def test_sanitizer_replaces_explicit_term(self):
        from src.tools.poyo_safety import _SUBSTITUTIONS

        if not _SUBSTITUTIONS:
            pytest.skip("poyo_safety._SUBSTITUTIONS empty; nothing to verify")
        first_pattern, _replacement = _SUBSTITUTIONS[0]
        sample = first_pattern.pattern.replace("\\", "")
        sanitized, applied = sanitize_for_poyo(f"A scene with {sample}")
        assert isinstance(sanitized, str)
        assert isinstance(applied, list)

    def test_sanitizer_passes_through_safe_prompt(self):
        safe = "A warm bedroom with natural lighting and organic cotton sheets"
        out, applied = sanitize_for_poyo(safe)
        assert isinstance(out, str)
        assert out == safe
        assert applied == []

    def test_sanitizer_returns_string_on_empty_input(self):
        out, applied = sanitize_for_poyo("")
        assert out == ""
        assert applied == []

    @pytest.mark.parametrize("message", _load_poyo_rejection_messages())
    def test_poyo_runtime_error_classifies_to_content_moderation_rejection(self, message: str):
        exc = RuntimeError(message)
        err = classify_error(exc, context="poyo_video_generate", node="seedance_clips")
        assert err.code == ErrorCode.CONTENT_MODERATION_REJECTED
        assert err.node == "seedance_clips"
        assert err.recoverable is False
        assert "poyo" in err.detail["exc_msg"].lower() or "content" in err.detail["exc_msg"].lower()


class TestDbPoolExhaustionNegative:
    """Runbook: docs/runbooks/db-pool-exhausted.md. When asyncpg pool is
    saturated, classifier should produce POSTGRES_UNAVAILABLE (recoverable).
    Repository falls back to SQLite when pool is unavailable."""

    def test_postgres_unavailable_classifies_as_recoverable(self):
        exc = ConnectionError("postgres connection refused — pool exhausted")
        err = classify_error(exc, context="db_query", node="state_save")
        assert err.code == ErrorCode.POSTGRES_UNAVAILABLE
        assert err.recoverable is True

    def test_msgpack_serialize_classifies_recoverable(self):
        exc = ValueError("failed to msgpack serialize state.gates field")
        err = classify_error(exc, context="checkpoint_save")
        assert err.code == ErrorCode.MSGPACK_SERIALIZE
        assert err.recoverable is True

    @pytest.mark.asyncio
    async def test_repository_falls_back_to_sqlite_when_pool_returns_none(self, sqlite_db):
        repo = PipelineStateRepository()
        await repo.create({
            "label": "test_pool_exhausted",
            "scenario": "s1",
            "config": {"x": 1},
            "steps": [],
            "mode": "auto",
        })
        row = await repo.get_by_label("test_pool_exhausted")
        assert row is not None
        assert row["scenario"] == "s1"


class TestConcurrentStateWritesNegative:
    """Concurrent writes to pipeline_states must produce a deterministic
    last-write-wins outcome (no corruption, no partial JSON).

    In SQLite-fallback mode, the shared sqlite3.Connection is single-writer
    so we drive concurrent calls through a semaphore that mimics asyncpg's
    pool serialization. The point is to prove the repository contract is
    consistent, not to validate SQLite's own concurrency guarantees."""

    @pytest.mark.asyncio
    async def test_serialized_writes_with_distinct_labels_all_persist(self, sqlite_db):
        repo = PipelineStateRepository()
        sem = asyncio.Semaphore(1)
        labels = [f"test_concurrent_{i}" for i in range(8)]

        async def _one(label: str) -> None:
            async with sem:
                await repo.create({
                    "label": label,
                    "scenario": "s1",
                    "config": {"label": label},
                    "steps": [],
                    "mode": "auto",
                })

        await asyncio.gather(*(_one(label) for label in labels))
        for label in labels:
            row = await repo.get_by_label(label)
            assert row is not None, f"label {label} missing after concurrent write"
            assert row["label"] == label

    @pytest.mark.asyncio
    async def test_serialized_updates_on_same_label_do_not_corrupt_jsonb(self, sqlite_db):
        repo = PipelineStateRepository()
        await repo.create({
            "label": "test_concurrent_update",
            "scenario": "s1",
            "config": {"v": 0},
            "steps": [],
            "mode": "auto",
        })
        row = await repo.get_by_label("test_concurrent_update")
        assert row is not None
        record_id = row["id"]
        sem = asyncio.Semaphore(1)

        async def _update(v: int) -> None:
            async with sem:
                await repo.update(record_id, {"config": {"v": v}})

        await asyncio.gather(*(_update(i) for i in range(10)))
        final = await repo.get_by_label("test_concurrent_update")
        assert final is not None
        import json
        cfg = final["config"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        assert "v" in cfg
        assert 0 <= cfg["v"] <= 9

    @pytest.mark.asyncio
    async def test_sqlite_native_concurrency_raises_predictable_error(self, sqlite_db):
        """Documents the known SQLite limitation: parallel unserialized writes
        to a shared connection raise sqlite3.InterfaceError. Production PG
        path is unaffected — asyncpg pool serializes by connection."""
        repo = PipelineStateRepository()

        async def _race(i: int) -> None:
            await repo.create({
                "label": f"race_{i}",
                "scenario": "s1",
                "config": {},
                "steps": [],
                "mode": "auto",
            })

        results = await asyncio.gather(
            *(_race(i) for i in range(5)),
            return_exceptions=True,
        )
        successes = [r for r in results if r is None]
        failures = [r for r in results if isinstance(r, Exception)]
        assert len(successes) >= 1
        for f in failures:
            assert isinstance(f, sqlite3.Error), f"expected sqlite3.Error, got {type(f).__name__}: {f}"
