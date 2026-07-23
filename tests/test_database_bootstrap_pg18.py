"""Guarded fresh and historical bootstrap checks on disposable PostgreSQL 18."""

# ruff: noqa: E402

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

# Capture operator authority before importing application modules.
_PG18_DSN = os.getenv("DATABASE_BOOTSTRAP_PG18_DSN")
_PG18_DATABASE = "ai_video_bootstrap"
_PG18_HOST = "127.0.0.1"
_PG18_PORT = 55441
_PG18_USERNAME = "postgres"
_LANE_ERROR = "disposable database bootstrap PostgreSQL 18 lane is not authorized"

REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_postgres.py"
ALEMBIC_CWD = REPO_ROOT / "migrations"

from src.storage import db


def _load_script_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_pg18_dsn(dsn: str | None) -> None:
    if not isinstance(dsn, str) or not dsn or dsn != dsn.strip():
        raise ValueError(_LANE_ERROR)
    try:
        parsed = urlsplit(dsn)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError(_LANE_ERROR) from None
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != _PG18_HOST
        or port != _PG18_PORT
        or parsed.path != f"/{_PG18_DATABASE}"
        or parsed.username != _PG18_USERNAME
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(_LANE_ERROR)


async def _verified_connection(dsn: str | None) -> asyncpg.Connection:
    _validate_pg18_dsn(dsn)
    assert dsn is not None
    try:
        connection = await asyncpg.connect(dsn)
    except Exception:
        raise RuntimeError(_LANE_ERROR) from None
    try:
        identity = await connection.fetchrow(
            "SELECT current_database() AS database_name, "
            "current_setting('server_version_num') AS server_version_num"
        )
        if (
            identity is None
            or identity["database_name"] != _PG18_DATABASE
            or int(identity["server_version_num"]) // 10_000 != 18
        ):
            raise ValueError(_LANE_ERROR)
    except Exception:
        await connection.close()
        raise RuntimeError(_LANE_ERROR) from None
    return connection


async def _reset_disposable_schema() -> None:
    connection = await _verified_connection(_PG18_DSN)
    try:
        await connection.execute("DROP SCHEMA public CASCADE")
        await connection.execute("CREATE SCHEMA public")
    finally:
        await connection.close()


def _safe_environment() -> dict[str, str]:
    _validate_pg18_dsn(_PG18_DSN)
    assert _PG18_DSN is not None
    env = os.environ.copy()
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["DATABASE_URL"] = _PG18_DSN
    env.pop("POSTGRES_BOOTSTRAP_AUTH", None)
    return env


def _run_bootstrap() -> subprocess.CompletedProcess[str]:
    env = _safe_environment()
    env["POSTGRES_BOOTSTRAP_AUTH"] = "APPLY_EMPTY_DATABASE_BASELINE"
    return subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), str(BOOTSTRAP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            *args,
        ],
        cwd=ALEMBIC_CWD,
        env=_safe_environment(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


async def _assert_schema_at_head(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _PG18_DSN is not None
    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", False)
    try:
        readiness = await db.check_database_readiness()
        assert readiness == {
            "ready": True,
            "backend": "postgresql",
            "status": "ready",
            "tables_verified": True,
            "migration": {
                "ready": True,
                "status": "at_head",
                "current_revision": db._code_alembic_head(),
                "head_revision": db._code_alembic_head(),
            },
        }
        from src.api import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
    finally:
        monkeypatch.setattr(db, "_pool", None)
        monkeypatch.setattr(db, "_pg_available", False)
        await pool.close()


def test_pg18_lane_rejects_every_non_disposable_dsn() -> None:
    for dsn in (
        None,
        "postgresql://postgres@localhost:55441/ai_video_bootstrap",
        "postgresql://postgres@127.0.0.1:5432/ai_video_bootstrap",
        "postgresql://postgres:secret@127.0.0.1:55441/ai_video_bootstrap",
        "postgresql://postgres@127.0.0.1:55441/production",
        "postgresql://postgres@127.0.0.1:55441/ai_video_bootstrap?sslmode=disable",
    ):
        with pytest.raises(ValueError, match="not authorized"):
            _validate_pg18_dsn(dsn)


@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_empty_pg18_bootstrap_is_atomic_guarded_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_disposable_schema()
    assert _PG18_DSN is not None

    result = _run_bootstrap()
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("postgres_bootstrap=passed head=")
    assert _PG18_DSN not in result.stdout + result.stderr
    await _assert_schema_at_head(monkeypatch)

    replay = _run_bootstrap()
    assert replay.returncode != 0
    assert replay.stderr.strip() == "ERROR: database_not_empty_use_alembic_upgrade"
    assert _PG18_DSN not in replay.stdout + replay.stderr


@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_bootstrap_refuses_existing_alembic_lineage_without_application_tables() -> None:
    await _reset_disposable_schema()
    connection = await _verified_connection(_PG18_DSN)
    try:
        await connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        )
        await connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ($1)",
            "42eb2682e54b",
        )
    finally:
        await connection.close()

    result = _run_bootstrap()

    assert result.returncode != 0
    assert result.stderr.strip() == "ERROR: database_has_alembic_lineage_use_upgrade"
    assert _PG18_DSN is not None
    assert _PG18_DSN not in result.stdout + result.stderr

    connection = await _verified_connection(_PG18_DSN)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == (
            "42eb2682e54b"
        )
    finally:
        await connection.close()


@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_historical_pg18_upgrade_and_idempotent_reupgrade_reach_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_disposable_schema()
    baseline = _run_bootstrap()
    assert baseline.returncode == 0, baseline.stderr

    downgrade = _run_alembic("downgrade", "-1")
    assert downgrade.returncode == 0, downgrade.stderr

    assert _PG18_DSN is not None
    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", False)
    try:
        readiness = await db.check_database_readiness()
        assert readiness["ready"] is False
        assert readiness["status"] == "migration_not_ready"
        assert readiness["migration"]["status"] == "behind_head"
    finally:
        monkeypatch.setattr(db, "_pool", None)
        monkeypatch.setattr(db, "_pg_available", False)
        await pool.close()

    upgrade = _run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    reupgrade = _run_alembic("upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr
    assert _PG18_DSN not in (
        upgrade.stdout + upgrade.stderr + reupgrade.stdout + reupgrade.stderr
    )
    await _assert_schema_at_head(monkeypatch)


@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_dynamic_logical_dump_restore_and_exact_parity_on_pg18(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _reset_disposable_schema()
    connection = await _verified_connection(_PG18_DSN)
    try:
        await connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(128) PRIMARY KEY)"
        )
        await connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('c8d9e0f1a2b3')"
        )
        await connection.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
        await connection.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL "
            "REFERENCES tenants(id))"
        )
        await connection.execute("CREATE TABLE empty_events (id TEXT PRIMARY KEY)")
        await connection.execute("INSERT INTO tenants (id) VALUES ('tenant-1')")
        await connection.execute(
            "INSERT INTO jobs (id, tenant_id) VALUES ('job-1', 'tenant-1')"
        )
    finally:
        await connection.close()

    assert _PG18_DSN is not None
    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    dump_module = _load_script_module(
        "pg18_dynamic_dump",
        REPO_ROOT / "scripts" / "pg_dump_logical.py",
    )
    restore_module = _load_script_module(
        "pg18_dynamic_restore",
        REPO_ROOT / "scripts" / "pg_restore_logical.py",
    )
    verifier_module = _load_script_module(
        "pg18_dynamic_verify",
        REPO_ROOT / "scripts" / "verify_restored_database.py",
    )
    dump_path = tmp_path / "pg_dump.jsonl"
    stats = await dump_module.dump_to_jsonl(dump_path)
    await pool.close()
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_pg_available", False)

    assert stats["expected_tables"] == ["empty_events", "tenants", "jobs"]
    assert stats["tables"] == {
        "empty_events": {"rows": 0},
        "tenants": {"rows": 1},
        "jobs": {"rows": 1},
    }
    stats_path = tmp_path / "pg_dump_stats.json"
    stats_path.write_text(json.dumps(stats) + "\n")

    await _reset_disposable_schema()
    connection = await _verified_connection(_PG18_DSN)
    try:
        await connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(128) PRIMARY KEY)"
        )
        await connection.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
        await connection.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL "
            "REFERENCES tenants(id))"
        )
        await connection.execute("CREATE TABLE empty_events (id TEXT PRIMARY KEY)")
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    try:
        restored = await restore_module.restore(dump_path, stats_path=stats_path)
        assert restored["tables"] == {
            "empty_events": {"available": 0, "inserted": 0},
            "tenants": {"available": 1, "inserted": 1},
            "jobs": {"available": 1, "inserted": 1},
        }
        verified = await verifier_module.verify_restored_database(stats_path)
        assert verified["status"] == "passed"
        assert verified["table_count"] == 3
        assert verified["total_rows"] == 2
    finally:
        monkeypatch.setattr(db, "_pool", None)
        monkeypatch.setattr(db, "_pg_available", False)
        await pool.close()

@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_pipeline_state_roundtrip_preserves_cursor_and_audit_fields_on_pg18(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import state_manager as state_manager_module

    await _reset_disposable_schema()
    baseline = _run_bootstrap()
    assert baseline.returncode == 0, baseline.stderr
    assert _PG18_DSN is not None
    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    monkeypatch.setattr(state_manager_module.PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(state_manager_module, "HAS_STORAGE", True)
    state = {
        "schema_version": 1,
        "label": "pg18-audit-roundtrip",
        "scenario": "s1",
        "tenant_id": "tenant-pg18",
        "config": {
            "tenant_id": "tenant-pg18",
            "artifact_disposition": "pending_review",
            "c2pa_signing_mode": "local_draft",
            "quality_rewind": {
                "upstream_step": "storyboards",
                "consumer_step": "keyframe_images",
                "attempt": 1,
                "status": "awaiting_upstream",
            },
        },
        "steps": {"strategy": {"status": "pending"}},
        "current_step": "strategy",
        "mode": "step_by_step",
        "trace_id": "trace-pg18-roundtrip",
        "errors": [],
        "media_synthesis_errors": [],
        "gates": {},
        "pipeline_degraded": False,
        "degraded_reason": None,
        "structured_errors": [],
        "regenerate_chain": [
            {"consumer": "keyframe_images", "upstream_step": "storyboards", "attempt": 1}
        ],
        "soft_degraded_reasons": [{"step": "continuity", "reason": "fixture"}],
    }
    from src.services.transparency_provenance import record_step_provenance

    _, projection = record_step_provenance(
        state=state,
        step_name="strategy",
        output={"brief": "pg18 provenance fixture"},
        output_dir=tmp_path,
    )
    state["transparency"] = projection
    manager = state_manager_module.PipelineStateManager(use_pg=True)
    try:
        await manager.save(state["label"], state)
        manager._state_path(state["label"]).unlink()
        loaded = await manager.load(state["label"])
        from src.pipeline.state_manager import ScenarioStateIntegrityError

        assert loaded is not None
        assert loaded == state
        _, next_projection = record_step_provenance(
            state=loaded,
            step_name="scripts",
            output={"scripts": [{"text": "next producer"}]},
            output_dir=tmp_path,
        )
        loaded["transparency"] = next_projection
        await manager.save(state["label"], loaded)
        manager._state_path(state["label"]).unlink()
        reloaded = await manager.load(state["label"])
        assert reloaded is not None
        assert reloaded["transparency"] == next_projection

        async with pool.acquire() as connection:
            for field in ("regenerate_chain", "soft_degraded_reasons"):
                for invalid_json in ("{}", '""', "[1]"):
                    await connection.execute(
                        f"UPDATE pipeline_states SET {field} = $1::jsonb WHERE label = $2",
                        invalid_json,
                        state["label"],
                    )
                    with pytest.raises(ScenarioStateIntegrityError, match=f":{field}"):
                        await manager.load(state["label"])
                await connection.execute(
                    f"UPDATE pipeline_states SET {field} = '[]'::jsonb WHERE label = $1",
                    state["label"],
                )
            for invalid_json in ("{}", '""', "[]", '{"record_count": true}'):
                await connection.execute(
                    "UPDATE pipeline_states SET transparency = $1::jsonb WHERE label = $2",
                    invalid_json,
                    state["label"],
                )
                with pytest.raises(
                    ScenarioStateIntegrityError,
                    match=":transparency",
                ):
                    await manager.load(state["label"])
            await connection.execute(
                "UPDATE pipeline_states SET transparency = $1::jsonb WHERE label = $2",
                json.dumps(next_projection),
                state["label"],
            )
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM pipeline_states WHERE label = $1",
                state["label"],
            )
        monkeypatch.setattr(db, "_pool", None)
        monkeypatch.setattr(db, "_pg_available", False)
        await pool.close()

    assert reloaded["transparency"]["record_count"] == 2


@pytest.mark.hermetic_slow
@pytest.mark.skipif(
    not _PG18_DSN,
    reason="requires explicit disposable DATABASE_BOOTSTRAP_PG18_DSN",
)
@pytest.mark.asyncio
async def test_pg18_pipeline_completion_claim_survives_stale_state_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal stale update cannot remove the server-owned claim."""

    assert _PG18_DSN is not None
    from src.storage.repository import PipelineStateRepository

    await _reset_disposable_schema()
    baseline = _run_bootstrap()
    assert baseline.returncode == 0, baseline.stderr
    pool = await asyncpg.create_pool(_PG18_DSN, min_size=1, max_size=2)
    monkeypatch.setattr(db, "_pool", pool)
    labels = (
        "pg18-completion-stale-success",
        "pg18-completion-stale-failure",
    )
    repository = PipelineStateRepository()
    try:
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM pipeline_states WHERE label = ANY($1)", labels)
        created = await repository.create(
            {
                "label": labels[0],
                "scenario": "s1",
                "config": {
                    "execution_lifecycle": {
                        "lifecycle_status": "completed_bounded"
                    }
                },
                "current_step": None,
                "errors": [],
                "pipeline_degraded": False,
            }
        )
        stale_failure_claim = {
            "version": "pipeline-completion-metric.v1",
            "outcome": "failure",
            "claimed_at": "2026-07-22T00:00:00+00:00",
            "duration_ms": 1.0,
            "error_count": 1,
            "scenario": "stale",
        }

        winning_success = await repository.claim_pipeline_completion(
            labels[0],
            stale_failure_claim,
        )
        assert type(winning_success) is dict
        assert winning_success["outcome"] == "success"
        assert winning_success["error_count"] == 0
        assert winning_success["scenario"] == "s1"
        await repository.update(created["id"], {"config": {}, "scenario": "s1"})
        persisted = await repository.get_by_label(labels[0])
        assert persisted is not None
        assert (
            persisted["config"]["pipeline_completion_metric_v1"]
            == winning_success
        )
        assert not await repository.claim_pipeline_completion(
            labels[0],
            stale_failure_claim,
        )

        await repository.create(
            {
                "label": labels[1],
                "scenario": "s1",
                "config": {},
                "current_step": "strategy",
                "errors": ["strategy_failed"],
                "pipeline_degraded": True,
            }
        )
        stale_success_claim = {
            **stale_failure_claim,
            "outcome": "success",
            "error_count": 0,
        }
        winning_failure = await repository.claim_pipeline_completion(
            labels[1],
            stale_success_claim,
        )
        assert type(winning_failure) is dict
        assert winning_failure["outcome"] == "failure"
        assert winning_failure["error_count"] == 1
        assert winning_failure["scenario"] == "s1"
    finally:
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM pipeline_states WHERE label = ANY($1)", labels)
        monkeypatch.setattr(db, "_pool", None)
        await pool.close()
