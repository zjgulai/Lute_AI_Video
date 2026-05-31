"""Guards for the backend JSON response metadata contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from src._version import APP_VERSION
from src.api import app

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "configs" / "api-response-metadata-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "api-response-metadata-contract.md"
DOCS_LINK_SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

META_REQUIRED_KEYS = {"trace_id", "duration_ms", "version", "timestamp"}


def _assert_response_meta(meta: dict[str, Any], expected_trace_id: str) -> None:
    assert META_REQUIRED_KEYS.issubset(meta)
    assert meta["trace_id"] == expected_trace_id
    assert isinstance(meta["duration_ms"], int | float)
    assert meta["duration_ms"] >= 0
    assert meta["version"] == APP_VERSION
    assert isinstance(meta["timestamp"], str)
    assert meta["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_json_response_includes_meta_and_echoes_trace_id(auth_headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/files",
            headers={**auth_headers, "X-Client-Trace-Id": "client-json-meta-001"},
        )

    body = response.json()

    assert response.status_code == 200
    assert response.headers.get("X-Trace-Id") == "client-json-meta-001"
    assert isinstance(body["files"], list)
    _assert_response_meta(body["_meta"], "client-json-meta-001")


@pytest.mark.asyncio
async def test_health_keeps_trace_header_but_skips_meta():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"X-Client-Trace-Id": "client-health-meta-001"},
        )

    body = response.json()

    assert response.status_code == 200
    assert response.headers.get("X-Trace-Id") == "client-health-meta-001"
    assert "_meta" not in body


@pytest.mark.asyncio
async def test_error_response_preserves_detail_and_includes_meta():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/files",
            headers={"X-Client-Trace-Id": "client-error-meta-001"},
        )

    body = response.json()

    assert response.status_code == 401
    assert response.headers.get("X-Trace-Id") == "client-error-meta-001"
    assert body["detail"] == "Missing API key"
    _assert_response_meta(body["_meta"], "client-error-meta-001")


def test_response_metadata_contract_is_documented_and_link_checked():
    assert CONTRACT_FILE.is_file()
    assert RUNBOOK_FILE.is_file()

    contract = yaml.safe_load(CONTRACT_FILE.read_text())
    assert set(contract["json_meta"]["required_keys"]) == META_REQUIRED_KEYS
    assert contract["json_meta"]["skip_meta_paths"] == ["/health"]
    assert contract["trace_header"] == {
        "request_header": "X-Client-Trace-Id",
        "response_header": "X-Trace-Id",
        "echo_client_trace_id": True,
    }
    assert contract["error_responses"]["http_exception_required_keys"] == [
        "detail",
        "_meta",
    ]
    assert contract["error_responses"]["rate_limit_429_required_keys"] == [
        "detail",
        "retry_after_sec",
        "_meta",
    ]

    runbook = RUNBOOK_FILE.read_text()
    assert "X-Trace-Id" in runbook
    assert "_meta" in runbook
    assert "retry_after_sec" in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "docs/runbooks/api-response-metadata-contract.md" in scope_targets
