"""Guards for the FastAPI fallback rate-limit contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from src.api import app

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "configs" / "api-rate-limit-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "api-rate-limit-contract.md"
DOCS_LINK_SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
API_SOURCE = REPO_ROOT / "src" / "api.py"

EXPECTED_WINDOW_SEC = 60
EXPECTED_MAX_REQUESTS = 120
EXPECTED_MAX_IPS = 1000
EXPECTED_SKIP_PATHS = ["/health"]
EXPECTED_SKIP_PREFIXES = ["/api/media/"]


def _assert_meta(meta: dict[str, Any], expected_trace_id: str) -> None:
    assert meta["trace_id"] == expected_trace_id
    assert isinstance(meta["duration_ms"], int | float)
    assert meta["duration_ms"] >= 0
    assert isinstance(meta["timestamp"], str)
    assert meta["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_business_route_returns_wrapped_429_after_rate_limit():
    client_ip = "203.0.113.36"
    final_trace_id = "client-rate-limit-121"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for index in range(EXPECTED_MAX_REQUESTS):
            response = await client.get(
                "/api/files",
                headers={
                    "X-Forwarded-For": client_ip,
                    "X-Client-Trace-Id": f"client-rate-limit-{index:03d}",
                },
            )
            assert response.status_code == 401

        response = await client.get(
            "/api/files",
            headers={
                "X-Forwarded-For": client_ip,
                "X-Client-Trace-Id": final_trace_id,
            },
        )

    body = response.json()

    assert response.status_code == 429
    assert response.headers.get("X-Trace-Id") == final_trace_id
    assert body["detail"] == "Too many requests. Please slow down."
    assert body["retry_after_sec"] == EXPECTED_WINDOW_SEC
    _assert_meta(body["_meta"], final_trace_id)


def test_rate_limit_contract_file_matches_runtime_source():
    assert CONTRACT_FILE.is_file()

    contract = yaml.safe_load(CONTRACT_FILE.read_text())
    assert contract["window_sec"] == EXPECTED_WINDOW_SEC
    assert contract["max_requests_per_ip"] == EXPECTED_MAX_REQUESTS
    assert contract["max_tracked_ips"] == EXPECTED_MAX_IPS
    assert contract["skip_paths"] == EXPECTED_SKIP_PATHS
    assert contract["skip_prefixes"] == EXPECTED_SKIP_PREFIXES
    assert contract["response"] == {
        "status_code": 429,
        "detail": "Too many requests. Please slow down.",
        "retry_after_sec": EXPECTED_WINDOW_SEC,
        "wrapped_with_meta": True,
    }

    source = API_SOURCE.read_text()
    assert "_rate_window_sec = 60" in source
    assert "_rate_max_requests = 120" in source
    assert "_rate_max_ips = 1000" in source
    assert 'request.url.path == "/health"' in source
    assert 'request.url.path.startswith("/api/media/")' in source
    assert '"retry_after_sec": _rate_window_sec' in source


def test_rate_limit_runbook_is_link_checked():
    assert RUNBOOK_FILE.is_file()

    runbook = RUNBOOK_FILE.read_text()
    assert "120" in runbook
    assert "/health" in runbook
    assert "/api/media/" in runbook
    assert "retry_after_sec" in runbook
    assert "tests/test_api_rate_limit_contract.py" in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "docs/runbooks/api-rate-limit-contract.md" in scope_targets
