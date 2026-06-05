from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_toolbox_tools_endpoint_lists_first_five_tools(auth_headers) -> None:
    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/toolbox/tools", headers=auth_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert {tool["tool_id"] for tool in payload["tools"]} == {
        "product-image",
        "six-view",
        "ecommerce-visual",
        "digital-human",
        "storyboard",
    }


@pytest.mark.asyncio
async def test_toolbox_plan_endpoint_returns_dry_run_plan(auth_headers) -> None:
    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/toolbox/product-image/plan",
            headers=auth_headers,
            json=_product_image_request(),
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tool_id"] == "product-image"
    assert payload["mode"] == "dry_run"
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["provider_call"] is False
    assert payload["delivery_accepted"] is False
    assert payload["prompt_hash"].startswith("sha256:")
    assert payload["required_checks"] == ["product_truth", "claim_evidence", "brand_rights"]


@pytest.mark.asyncio
async def test_toolbox_prompt_preview_is_sanitized(auth_headers) -> None:
    from src.api import app

    body = _ecommerce_visual_request(raw_text="must-not-leak-campaign-brief")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/toolbox/ecommerce-visual/prompt-preview",
            headers=auth_headers,
            json=body,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["tool_id"] == "ecommerce-visual"
    assert payload["prompt_preview_allowed"] is True
    assert payload["prompt_hash"].startswith("sha256:")
    assert "bundle_momcozy_candidate" in serialized
    assert "must-not-leak-campaign-brief" not in serialized
    assert "prompt_payload" not in serialized
    assert '"prompt"' not in serialized


@pytest.mark.asyncio
async def test_toolbox_run_and_get_state_never_submits_provider(auth_headers) -> None:
    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        run_response = await client.post(
            "/toolbox/storyboard/run",
            headers=auth_headers,
            json=_storyboard_request(),
        )
        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        get_response = await client.get(f"/toolbox/runs/{run_payload['run_id']}", headers=auth_headers)

    assert get_response.status_code == 200, get_response.text
    payload = get_response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["tool_id"] == "storyboard"
    assert payload["status"] == "accepted_dry_run"
    assert payload["plan"]["provider_call"] is False
    assert payload["plan"]["delivery_accepted"] is False
    assert payload["job_record"]["status"] == "prepared"
    assert payload["job_record"]["delivery_accepted"] is False
    assert payload["job_record"]["publish_allowed"] is False
    assert "submitted" not in serialized
    assert "provider_job_id" not in serialized


@pytest.mark.asyncio
async def test_toolbox_artifacts_endpoint_returns_refs_only(auth_headers) -> None:
    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        run_response = await client.post(
            "/toolbox/six-view/run",
            headers=auth_headers,
            json=_six_view_request(),
        )
        assert run_response.status_code == 200, run_response.text
        get_response = await client.get(
            f"/toolbox/runs/{run_response.json()['run_id']}/artifacts",
            headers=auth_headers,
        )

    assert get_response.status_code == 200, get_response.text
    payload = get_response.json()
    assert payload["run_id"].startswith("tbx_run_")
    assert payload["artifacts"][0]["artifact_ref"].startswith("artifact://toolbox/six-view/")
    assert payload["artifacts"][0]["delivery_accepted"] is False


@pytest.mark.asyncio
async def test_toolbox_runs_endpoint_lists_recent_refs_without_raw_input(auth_headers) -> None:
    from src.api import app

    ecommerce_body = _ecommerce_visual_request(raw_text="must-not-leak-run-list-brief")
    ecommerce_body["request_id"] = "tbx_req_ecommerce_visual_recent"
    product_body = _product_image_request()
    product_body["request_id"] = "tbx_req_product_image_recent"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post(
            "/toolbox/ecommerce-visual/run",
            headers=auth_headers,
            json=ecommerce_body,
        )
        assert first_response.status_code == 200, first_response.text
        second_response = await client.post(
            "/toolbox/product-image/run",
            headers=auth_headers,
            json=product_body,
        )
        assert second_response.status_code == 200, second_response.text
        list_response = await client.get("/toolbox/runs?limit=2", headers=auth_headers)

    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert [run["tool_id"] for run in payload["runs"]][:2] == ["product-image", "ecommerce-visual"]
    assert payload["runs"][0]["job_record"]["publish_allowed"] is False
    assert payload["runs"][0]["artifacts"][0]["artifact_ref"].startswith("artifact://toolbox/product-image/")
    assert "must-not-leak-run-list-brief" not in serialized
    assert "tool_input" not in serialized
    assert "campaign_brief" not in serialized


@pytest.mark.asyncio
async def test_toolbox_path_and_body_tool_mismatch_fails_closed(auth_headers) -> None:
    from src.api import app

    body = _product_image_request()
    body["tool_id"] = "six-view"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/toolbox/product-image/plan", headers=auth_headers, json=body)

    assert response.status_code == 422
    assert "toolbox path/body mismatch" in response.text


@pytest.mark.asyncio
async def test_toolbox_run_projection_does_not_leak_raw_tool_input(auth_headers) -> None:
    from src.api import app

    body = _ecommerce_visual_request(raw_text="must-not-leak-raw-brief")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/toolbox/ecommerce-visual/run", headers=auth_headers, json=body)

    assert response.status_code == 200, response.text
    serialized = json.dumps(response.json(), ensure_ascii=False, sort_keys=True)
    assert "must-not-leak-raw-brief" not in serialized
    assert "campaign_brief" not in serialized
    assert "tool_input" not in serialized


def _product_image_request() -> dict[str, object]:
    return {
        "request_id": "tbx_req_product_image_router",
        "tool_id": "product-image",
        "brand_id": "momcozy",
        "platform_target": {"platform": "shopify", "aspect_ratio": "1:1"},
        "brand_bundle_ref": "bundle_momcozy_candidate",
        "asset_refs": [
            {
                "asset_ref": "asset://brand/momcozy/product/m9-front",
                "asset_kind": "image",
                "rights_ref": "rights://candidate/m9",
            }
        ],
        "tool_input": {
            "tool_id": "product-image",
            "product_ref": "sku://momcozy/m9",
            "image_type": "main_white_bg",
            "aspect_ratio": "1:1",
            "reference_asset_refs": ["asset://brand/momcozy/product/m9-front"],
        },
    }


def _six_view_request() -> dict[str, object]:
    return {
        "request_id": "tbx_req_six_view_router",
        "tool_id": "six-view",
        "brand_id": "momcozy",
        "platform_target": {"platform": "shopify", "aspect_ratio": "1:1"},
        "brand_bundle_ref": "bundle_momcozy_candidate",
        "tool_input": {
            "tool_id": "six-view",
            "product_ref": "sku://momcozy/m9",
            "seed_image_refs": ["asset://brand/momcozy/product/m9-front"],
            "required_views": ["front", "back", "left", "right", "top", "detail"],
        },
    }


def _ecommerce_visual_request(raw_text: str) -> dict[str, object]:
    return {
        "request_id": "tbx_req_ecommerce_visual_router",
        "tool_id": "ecommerce-visual",
        "brand_id": "momcozy",
        "platform_target": {"platform": "tiktok", "aspect_ratio": "9:16"},
        "brand_bundle_ref": "bundle_momcozy_candidate",
        "tool_input": {
            "tool_id": "ecommerce-visual",
            "campaign_brief": raw_text,
            "channel": "tiktok",
            "visual_format": "social_ad",
            "copy_block_refs": ["asset://copy/momcozy/hook-001"],
            "product_image_refs": ["asset://brand/momcozy/product/m9-front"],
            "aspect_ratio": "9:16",
        },
    }


def _storyboard_request() -> dict[str, object]:
    return {
        "request_id": "tbx_req_storyboard_router",
        "tool_id": "storyboard",
        "brand_id": "momcozy",
        "platform_target": {"platform": "tiktok", "aspect_ratio": "9:16", "duration_seconds": 120},
        "brand_bundle_ref": "bundle_momcozy_candidate",
        "tool_input": {
            "tool_id": "storyboard",
            "brief": "Plan a product education video",
            "duration_target_seconds": 120,
            "planned_timeline_block_count": 3,
            "review_checkpoint_refs": ["storyboard://review/checkpoint-001"],
            "storyboard_grid": 12,
        },
    }
