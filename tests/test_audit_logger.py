"""Tests for src.storage.audit_logger (TODO-C10)."""
from __future__ import annotations

import sqlite3

import pytest

import src.storage.db as db_module
from src.storage.audit_logger import audit_log
from src.storage.db import _create_sqlite_tables


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """Fresh SQLite per test, force PG-pool to return None."""
    db_path = tmp_path / "test_audit.db"

    async def _no_pool():
        return None
    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    import src.storage.audit_logger as audit_module
    monkeypatch.setattr(audit_module, "get_pool", _no_pool)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(db_module, "_sqlite_conn", conn)
    _create_sqlite_tables()
    yield conn
    conn.close()


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_minimal_event_persists(self, sqlite_db):
        await audit_log(actor_type="admin", action="test.minimal")
        rows = sqlite_db.execute("SELECT * FROM audit_logs").fetchall()
        assert len(rows) == 1
        assert rows[0]["actor_type"] == "admin"
        assert rows[0]["action"] == "test.minimal"
        assert rows[0]["success"] == 1

    @pytest.mark.asyncio
    async def test_full_event_persists(self, sqlite_db):
        await audit_log(
            actor_type="admin",
            actor_id="admin-uuid-123",
            action="tenant.create",
            resource_type="tenant",
            resource_id="acme-corp",
            payload={"display_name": "ACME", "plan": "enterprise"},
            success=True,
            client_ip="1.2.3.4",
            trace_id="trace-abc-789",
        )
        row = sqlite_db.execute("SELECT * FROM audit_logs").fetchone()
        assert row["actor_id"] == "admin-uuid-123"
        assert row["action"] == "tenant.create"
        assert row["resource_type"] == "tenant"
        assert row["resource_id"] == "acme-corp"
        assert row["client_ip"] == "1.2.3.4"
        assert row["trace_id"] == "trace-abc-789"
        assert row["success"] == 1
        import json
        payload = json.loads(row["payload"])
        assert payload["display_name"] == "ACME"
        assert payload["plan"] == "enterprise"

    @pytest.mark.asyncio
    async def test_failure_recorded_as_zero(self, sqlite_db):
        await audit_log(actor_type="admin", action="admin.login.failure", success=False)
        row = sqlite_db.execute("SELECT * FROM audit_logs").fetchone()
        assert row["success"] == 0

    @pytest.mark.asyncio
    async def test_audit_log_never_raises_on_db_failure(self, sqlite_db):
        """Even when DB write throws, audit_log must not propagate the error.

        Calling code (e.g. admin login endpoint) trusts that audit_log won't
        break the response cycle.
        """
        sqlite_db.close()
        await audit_log(actor_type="admin", action="post.close")

    @pytest.mark.asyncio
    async def test_multiple_events_inserted_separately(self, sqlite_db):
        await audit_log(actor_type="admin", action="event.1")
        await audit_log(actor_type="admin", action="event.2")
        await audit_log(actor_type="admin", action="event.3")
        count = sqlite_db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        assert count == 3

    @pytest.mark.asyncio
    async def test_each_event_gets_unique_id(self, sqlite_db):
        await audit_log(actor_type="admin", action="id.1")
        await audit_log(actor_type="admin", action="id.2")
        rows = sqlite_db.execute("SELECT id FROM audit_logs").fetchall()
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids))
