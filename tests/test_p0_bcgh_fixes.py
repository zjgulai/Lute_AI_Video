"""Regression tests for the 3 P0 production bugs found 2026-05-03.

See tmp/outputs/task-bcgh-verification-20260503.md for context.

- Task H: src/pipeline/step_runner.py:100 — same-second concurrent collision
- Task G: src/routers/scenario.py:267 — missing Pydantic validation
- Task C: src/routers/distribution.py:78-81 — hardcoded connected:true
"""

import asyncio

import pytest

try:
    from httpx import ASGITransport, AsyncClient

    from src.api import app
    from src.routers._deps import verify_api_key
    if app is None:
        pytest.skip("fastapi not installed", allow_module_level=True)
except (ImportError, ModuleNotFoundError):
    pytest.skip("fastapi not installed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _bypass_auth():
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.pop(verify_api_key, None)


@pytest.mark.asyncio
async def test_step_runner_init_state_unique_labels_under_concurrency():
    """Task H: 5 concurrent init_state calls in the same second must produce 5 distinct labels."""
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    runner = StepRunner(PipelineStateManager())
    cfg = {"product_catalog": {"products": [{"name": "P"}]}}
    labels = await asyncio.gather(
        *(runner.init_state(config=cfg, mode="step_by_step") for _ in range(5))
    )
    assert len(set(labels)) == 5, f"label collision: {labels}"


@pytest.mark.asyncio
async def test_s1_start_empty_body_returns_422():
    """Task G: missing product_catalog must be rejected at request layer with 422, not crash to 500."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/scenario/s1/start", json={})
    assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_distribution_platforms_reflects_env(monkeypatch):
    """Task C: when platform tokens are absent, connected must be False."""
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TIKTOK_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_API_KEY", raising=False)
    monkeypatch.delenv("SHOPIFY_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_API_PASSWORD", raising=False)
    monkeypatch.delenv("SHOPIFY_GRAPHQL_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("SHOPIFY_STORE_URL", raising=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/distribution/platforms")

    assert resp.status_code == 200
    # Response wrapper middleware wraps list payloads as {"data": [...], "_meta": {...}}
    payload = resp.json()
    items = payload["data"] if isinstance(payload, dict) and "data" in payload else payload
    by_id = {p["id"]: p for p in items}
    assert by_id["tiktok"]["connected"] is False
    assert by_id["shopify"]["connected"] is False
