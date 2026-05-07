"""Admin Panel Phase 1 unit tests.

Covers (CLAUDE.md D task — Admin Panel verification):
- Auth: login rate limit, session validation helpers
- Tenant: ID validation
- Admin deps: _safe_error, _serialize
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


class TestLoginRateLimiter:
    """Admin login rate limiting — 5 attempts per 60s per IP."""

    def test_under_limit_allowed(self):
        from src.routers._admin_deps import _check_login_rate_limit, _record_login_attempt

        _record_login_attempt("ip_1")
        _record_login_attempt("ip_1")
        _record_login_attempt("ip_1")
        _check_login_rate_limit("ip_1")

    def test_exceeding_limit_raises_429(self):
        from fastapi import HTTPException
        from src.routers._admin_deps import _check_login_rate_limit, _record_login_attempt

        for _ in range(5):
            _record_login_attempt("ip_2")
        with pytest.raises(HTTPException) as exc_info:
            _check_login_rate_limit("ip_2")
        assert exc_info.value.status_code == 429

    def test_different_ips_isolated(self):
        from src.routers._admin_deps import _check_login_rate_limit, _record_login_attempt

        for _ in range(5):
            _record_login_attempt("ip_a")
        _check_login_rate_limit("ip_b")

    def test_old_attempts_expired(self):
        from src.routers._admin_deps import _check_login_rate_limit, _login_attempts

        _login_attempts["ip_3"] = [time.time() - 120]
        _check_login_rate_limit("ip_3")


class TestVerifyAdminSession:
    """Session cookie validation."""

    @pytest.mark.asyncio
    async def test_missing_cookie_raises_401(self):
        from fastapi import HTTPException
        from src.routers._admin_deps import verify_admin_session

        mock_request = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_session(mock_request, None)
        assert exc_info.value.status_code == 401
        assert "Missing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from src.routers._admin_deps import verify_admin_session

        mock_request = AsyncMock()

        with patch("src.storage.db.is_pg_available", return_value=True):
            with patch("src.storage.db.get_pool") as mock_get_pool:
                mock_conn = AsyncMock()
                mock_conn.fetchrow = AsyncMock(return_value=None)

                # Properly mock async context manager for pool.acquire()
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def mock_acquire():
                    yield mock_conn

                mock_pool = AsyncMock()
                mock_pool.acquire = mock_acquire
                mock_get_pool.return_value = mock_pool

                with pytest.raises(HTTPException) as exc_info:
                    await verify_admin_session(mock_request, "invalid_token")
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_session_raises_401(self):
        from fastapi import HTTPException
        from src.routers._admin_deps import verify_admin_session

        mock_request = AsyncMock()
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)

        with patch("src.storage.db.is_pg_available", return_value=True):
            with patch("src.storage.db.get_pool") as mock_get_pool:
                mock_conn = AsyncMock()
                mock_conn.fetchrow = AsyncMock(return_value={
                    "admin_id": "admin_1",
                    "expires_at": expired_time,
                })

                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def mock_acquire():
                    yield mock_conn

                mock_pool = AsyncMock()
                mock_pool.acquire = mock_acquire
                mock_get_pool.return_value = mock_pool

                with pytest.raises(HTTPException) as exc_info:
                    await verify_admin_session(mock_request, "some_token")
                assert exc_info.value.status_code == 401
                assert "expired" in exc_info.value.detail.lower()


class TestTenantIdValidation:
    """Tenant ID format validation — ^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$."""

    def test_valid_tenant_ids(self):
        from src.routers.admin import _validate_tenant_id

        _validate_tenant_id("tenant-123")
        _validate_tenant_id("a1b2c3")
        _validate_tenant_id("acme-corp-v2")

    def test_invalid_tenant_id_too_short(self):
        from fastapi import HTTPException
        from src.routers.admin import _validate_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_tenant_id("ab")
        assert exc_info.value.status_code == 422

    def test_invalid_tenant_id_bad_chars(self):
        from fastapi import HTTPException
        from src.routers.admin import _validate_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_tenant_id("tenant@123!")
        assert exc_info.value.status_code == 422

    def test_invalid_tenant_id_underscore(self):
        from fastapi import HTTPException
        from src.routers.admin import _validate_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_tenant_id("acme_corp")
        assert exc_info.value.status_code == 422

    def test_invalid_tenant_id_leading_hyphen(self):
        from fastapi import HTTPException
        from src.routers.admin import _validate_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_tenant_id("-tenant")
        assert exc_info.value.status_code == 422


class TestAdminHelpers:
    """Misc admin helper functions."""

    def test_safe_error_generic_in_production(self):
        from src.routers._admin_deps import _safe_error

        result = _safe_error(RuntimeError("secret"), is_dev=False)
        assert "Internal server error" in result
        assert "secret" not in result

    def test_safe_error_verbose_in_dev(self):
        from src.routers._admin_deps import _safe_error

        result = _safe_error(RuntimeError("debug info"), is_dev=True)
        assert "debug info" in result

    def test_serialize_datetime(self):
        from src.routers._admin_deps import _serialize

        dt = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        result = _serialize(dt)
        assert "2026-05-07T12:00:00" in result

    def test_serialize_nested_dict(self):
        from src.routers._admin_deps import _serialize

        data = {"user": {"name": "test", "created": datetime(2026, 1, 1, tzinfo=timezone.utc)}}
        result = _serialize(data)
        assert result["user"]["name"] == "test"
        assert "2026-01-01" in result["user"]["created"]
