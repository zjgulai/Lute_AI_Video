from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def reset_auth_context():
    from src.routers import _deps

    auth_token = _deps._auth_context_var.set(None)
    tenant_token = _deps._tenant_id_var.set(None)
    yield
    _deps._auth_context_var.reset(auth_token)
    _deps._tenant_id_var.reset(tenant_token)


@pytest.mark.asyncio
async def test_verify_api_key_returns_dev_env_auth_context(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    monkeypatch.setattr(db, "is_pg_available", lambda: False)
    monkeypatch.setattr(_deps, "API_KEY", "local-key")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "development")
    monkeypatch.setattr(_deps, "ALLOW_TEST_BUNDLE_KEY", False)

    ctx = await _deps.verify_api_key(None, "local-key")

    assert ctx.tenant_id == "default"
    assert ctx.key_type == _deps.ApiKeyType.ENV_FALLBACK
    assert ctx.has_permission("all")
    assert _deps.get_auth_context() == ctx


@pytest.mark.asyncio
async def test_verify_api_key_blocks_default_test_bundle_env_key_in_production(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    monkeypatch.setattr(db, "is_pg_available", lambda: False)
    monkeypatch.setattr(_deps, "API_KEY", "ai_video_demo_2026")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")
    monkeypatch.setattr(_deps, "ALLOW_TEST_BUNDLE_KEY", False)

    with pytest.raises(HTTPException) as exc:
        await _deps.verify_api_key(None, "ai_video_demo_2026")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_accepts_private_env_key_in_production(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    monkeypatch.setattr(db, "is_pg_available", lambda: False)
    monkeypatch.setattr(_deps, "API_KEY", "private-prod-key")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")
    monkeypatch.setattr(_deps, "ALLOW_TEST_BUNDLE_KEY", False)

    ctx = await _deps.verify_api_key(None, "private-prod-key")

    assert ctx.tenant_id == "default"
    assert ctx.key_type == _deps.ApiKeyType.ENV_FALLBACK


@pytest.mark.asyncio
async def test_verify_api_key_accepts_explicit_test_bundle_key(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    monkeypatch.setattr(db, "is_pg_available", lambda: False)
    monkeypatch.setattr(_deps, "API_KEY", "local-key")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "ai_video_demo_2026")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")
    monkeypatch.setattr(_deps, "ALLOW_TEST_BUNDLE_KEY", True)

    ctx = await _deps.verify_api_key(None, "ai_video_demo_2026")

    assert ctx.tenant_id == "test-bundle"
    assert ctx.key_type == _deps.ApiKeyType.TEST_BUNDLE
    assert ctx.has_permission("scenario:run")


class _FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


class _FakeAuthConn:
    def __init__(self, row):
        self.row = row
        self.last_used_updated = False

    async def fetchrow(self, *_args, **_kwargs):
        return self.row

    async def execute(self, *_args, **_kwargs):
        self.last_used_updated = True
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_verify_api_key_accepts_db_key_with_naive_future_expires_at(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    conn = _FakeAuthConn(
        {
            "id": "key-id",
            "tenant_id": "momcozy-marketing",
            "permissions": ["all"],
            "revoked_at": None,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None),
        }
    )

    async def fake_get_pool():
        return _FakePool(conn)

    monkeypatch.setattr(db, "is_pg_available", lambda: True)
    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    monkeypatch.setattr(_deps, "API_KEY", "")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")

    ctx = await _deps.verify_api_key(None, "db-key")

    assert ctx.tenant_id == "momcozy-marketing"
    assert ctx.key_type == _deps.ApiKeyType.TENANT
    assert conn.last_used_updated is True


@pytest.mark.asyncio
async def test_verify_api_key_rejects_db_key_with_naive_expired_expires_at(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    conn = _FakeAuthConn(
        {
            "id": "key-id",
            "tenant_id": "momcozy-marketing",
            "permissions": ["all"],
            "revoked_at": None,
            "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None),
        }
    )

    async def fake_get_pool():
        return _FakePool(conn)

    monkeypatch.setattr(db, "is_pg_available", lambda: True)
    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    monkeypatch.setattr(_deps, "API_KEY", "")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")

    with pytest.raises(HTTPException) as exc:
        await _deps.verify_api_key(None, "db-key")

    assert exc.value.status_code == 401
    assert conn.last_used_updated is False


@pytest.mark.asyncio
async def test_verify_api_key_accepts_db_key_with_aware_future_expires_at(monkeypatch):
    from src.routers import _deps
    from src.storage import db

    conn = _FakeAuthConn(
        {
            "id": "key-id",
            "tenant_id": "momcozy-marketing",
            "permissions": ["all"],
            "revoked_at": None,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
    )

    async def fake_get_pool():
        return _FakePool(conn)

    monkeypatch.setattr(db, "is_pg_available", lambda: True)
    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    monkeypatch.setattr(_deps, "API_KEY", "")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "production")

    ctx = await _deps.verify_api_key(None, "db-key")

    assert ctx.tenant_id == "momcozy-marketing"
    assert ctx.key_type == _deps.ApiKeyType.TENANT


@pytest.mark.asyncio
async def test_step_runner_persists_auth_tenant_id(isolated_state_dir):
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.routers import _deps

    token = _deps._auth_context_var.set(
        _deps.AuthContext(
            tenant_id="tenant-a",
            permissions=frozenset({"all"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id="key-a",
        )
    )
    try:
        state_manager = PipelineStateManager()
        label = await StepRunner(state_manager).init_state(
            config={"product_catalog": {"name": "Test"}},
            mode="step_by_step",
            label="tenant_state_test",
        )
        state = await state_manager.load(label)
    finally:
        _deps._auth_context_var.reset(token)

    assert state is not None
    assert state["tenant_id"] == "tenant-a"


def test_scenario_state_access_rejects_cross_tenant():
    from src.routers import _deps, scenario

    token = _deps._auth_context_var.set(
        _deps.AuthContext(
            tenant_id="tenant-a",
            permissions=frozenset({"all"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id="key-a",
        )
    )
    try:
        with pytest.raises(HTTPException) as exc:
            scenario._assert_state_access({"tenant_id": "tenant-b"})
    finally:
        _deps._auth_context_var.reset(token)

    assert exc.value.status_code == 404
