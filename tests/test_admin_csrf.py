"""Tests for CSRF double-submit token verification on admin endpoints (TODO-E1).

VULNERABILITIES-AND-PENDING V-7: admin POST/PUT/DELETE endpoints previously
relied solely on SameSite=Lax cookies. This commit adds defense-in-depth
via double-submit CSRF token. These tests pin the contract.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.routers._admin_deps import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    generate_csrf_token,
    verify_csrf_token,
)


class _FakeRequest:
    def __init__(self, method: str = "POST"):
        self.method = method


class TestGenerateCsrfToken:
    def test_returns_url_safe_string(self):
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) >= 32
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_each_call_returns_unique_token(self):
        a = generate_csrf_token()
        b = generate_csrf_token()
        assert a != b


class TestVerifyCsrfToken:
    @pytest.mark.asyncio
    async def test_get_skips_csrf_check(self):
        """GET requests are read-only and bypass CSRF verification."""
        req = _FakeRequest(method="GET")
        result = await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_head_skips_csrf_check(self):
        req = _FakeRequest(method="HEAD")
        result = await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_options_skips_csrf_check(self):
        req = _FakeRequest(method="OPTIONS")
        result = await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_post_missing_cookie_403(self):
        req = _FakeRequest(method="POST")
        with pytest.raises(HTTPException) as exc:
            await verify_csrf_token(req, admin_csrf=None, x_csrf_token="some-token")
        assert exc.value.status_code == 403
        assert "cookie" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_post_missing_header_403(self):
        req = _FakeRequest(method="POST")
        with pytest.raises(HTTPException) as exc:
            await verify_csrf_token(req, admin_csrf="cookie-val", x_csrf_token=None)
        assert exc.value.status_code == 403
        assert "header" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_post_mismatched_token_403(self):
        req = _FakeRequest(method="POST")
        with pytest.raises(HTTPException) as exc:
            await verify_csrf_token(
                req,
                admin_csrf="cookie-secret",
                x_csrf_token="different-header",
            )
        assert exc.value.status_code == 403
        assert "mismatch" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_post_matching_token_succeeds(self):
        req = _FakeRequest(method="POST")
        token = generate_csrf_token()
        result = await verify_csrf_token(req, admin_csrf=token, x_csrf_token=token)
        assert result is None

    @pytest.mark.asyncio
    async def test_put_requires_csrf(self):
        req = _FakeRequest(method="PUT")
        with pytest.raises(HTTPException):
            await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)

    @pytest.mark.asyncio
    async def test_delete_requires_csrf(self):
        req = _FakeRequest(method="DELETE")
        with pytest.raises(HTTPException):
            await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)

    @pytest.mark.asyncio
    async def test_patch_requires_csrf(self):
        req = _FakeRequest(method="PATCH")
        with pytest.raises(HTTPException):
            await verify_csrf_token(req, admin_csrf=None, x_csrf_token=None)


class TestCsrfConstants:
    def test_cookie_name(self):
        assert CSRF_COOKIE_NAME == "admin_csrf"

    def test_header_name(self):
        assert CSRF_HEADER_NAME == "x-csrf-token"
