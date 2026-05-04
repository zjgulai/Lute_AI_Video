"""Tests for the FastAPI backend — pipeline endpoints, review submission, health check."""

import os

import pytest

# ── Skip all tests if fastapi not installed ──
try:
    from src.api import app
    from httpx import ASGITransport, AsyncClient
    if app is None:
        pytest.skip("fastapi not installed", allow_module_level=True)
except (ImportError, ModuleNotFoundError):
    pytest.skip("fastapi not installed", allow_module_level=True)

# conftest.py 顶部固定了 API_KEY=test-api-key-for-pytest
AUTH_HEADERS = {"X-API-Key": os.environ["API_KEY"]}


@pytest.mark.asyncio
async def test_health_returns_ok():
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "remotion" in data
    assert "persistence" in data


@pytest.mark.asyncio
async def test_health_includes_remotion_report():
    """Health response includes full Remotion environment validation."""
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    data = response.json()
    rem = data["remotion"]
    assert "available" in rem
    assert "node_version" in rem
    assert "issues" in rem


@pytest.mark.asyncio
async def test_start_pipeline_returns_thread_id():
    """Starting a pipeline should return a thread_id immediately."""
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/pipeline/start",
            headers=AUTH_HEADERS,
            json={
                "product_catalog": {"products": [{"name": "TestProduct"}]},
                "brand_guidelines": {"brand_name": "TestBrand"},
                "target_platforms": ["tiktok", "facebook"],
                "target_languages": ["en"],
                "content_calendar_week": "2026-W20",
            },
        )
    data = response.json()
    assert "thread_id" in data
    # P0-B: thread_id 是 str(uuid.uuid4()) 36 字符,不是旧 8 字符短 id
    assert len(data["thread_id"]) == 36


@pytest.mark.asyncio
async def test_get_state_returns_structured_response():
    """State endpoint should return thread_id, status, current_review, state."""
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_resp = await client.post(
            "/pipeline/start",
            headers=AUTH_HEADERS,
            json={"target_platforms": ["tiktok"], "target_languages": ["en"]},
        )
        thread_id = start_resp.json()["thread_id"]

        state_resp = await client.get(
            f"/pipeline/{thread_id}/state",
            headers=AUTH_HEADERS,
        )
    assert state_resp.status_code == 200
    data = state_resp.json()
    assert data["thread_id"] == thread_id
    assert "status" in data
    assert "state" in data
    assert "pipeline_complete" in data


@pytest.mark.asyncio
async def test_submit_approve_returns_resumed():
    """Submitting an approve review should resume the pipeline."""
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_resp = await client.post(
            "/pipeline/start",
            headers=AUTH_HEADERS,
            json={"target_platforms": ["tiktok"], "target_languages": ["en"]},
        )
        thread_id = start_resp.json()["thread_id"]

        review_resp = await client.post(
            f"/pipeline/{thread_id}/review/strategy_review",
            headers=AUTH_HEADERS,
            json={"action": "approve", "reviewer_notes": "Looks good!"},
        )
    assert review_resp.status_code == 200
    data = review_resp.json()
    assert data["action"] == "approve"
    assert data["status"] == "resumed"


@pytest.mark.asyncio
async def test_submit_reject_returns_resumed():
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_resp = await client.post(
            "/pipeline/start",
            headers=AUTH_HEADERS,
            json={"target_platforms": ["tiktok"], "target_languages": ["en"]},
        )
        thread_id = start_resp.json()["thread_id"]

        review_resp = await client.post(
            f"/pipeline/{thread_id}/review/strategy_review",
            headers=AUTH_HEADERS,
            json={"action": "reject", "reviewer_notes": "Not aligned with brand"},
        )
    assert review_resp.status_code == 200
    assert review_resp.json()["action"] == "reject"


@pytest.mark.asyncio
async def test_get_output_returns_pipeline_data():
    from src.api import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_resp = await client.post(
            "/pipeline/start",
            headers=AUTH_HEADERS,
            json={"target_platforms": ["tiktok"], "target_languages": ["en"]},
        )
        thread_id = start_resp.json()["thread_id"]

        for review_node in ["strategy_review", "script_review", "edit_review", "thumbnail_review"]:
            await client.post(
                f"/pipeline/{thread_id}/review/{review_node}",
                headers=AUTH_HEADERS,
                json={"action": "approve"},
            )

        output_resp = await client.get(
            f"/pipeline/{thread_id}/output",
            headers=AUTH_HEADERS,
        )
    assert output_resp.status_code == 200
    data = output_resp.json()
    assert any(k in data for k in ["scripts", "audit_reports", "analytics_reports"])
