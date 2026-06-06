from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_RECORD_ENV,
    ACCOUNT_READINESS_SCOPE,
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    PROVIDER_REVALIDATION_REF,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
)
from src.pipeline.toolbox.provider_readiness import TOOLBOX_TOOL_SCOPE_FIELD


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
async def test_toolbox_provider_readiness_endpoint_is_blocked_by_default(auth_headers, monkeypatch) -> None:
    from src.api import app

    monkeypatch.setenv(RUN_TOKEN_SMOKE_ENV, "0")
    monkeypatch.delenv(APPROVAL_RECORD_ENV, raising=False)
    monkeypatch.delenv(ACCOUNT_READINESS_RECORD_ENV, raising=False)
    for key_name in REQUIRED_API_KEY_ENVS:
        monkeypatch.delenv(key_name, raising=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/toolbox/product-image/provider-readiness", headers=auth_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["ready_for_dry_run"] is True
    assert payload["ready_for_authorized_live"] is False
    assert payload["provider_call_allowed"] is False
    assert payload.get("approval_record_ref") is None
    assert any("RUN_TOKEN_SMOKE=1" in reason for reason in payload["blocker_reasons"])


@pytest.mark.asyncio
async def test_toolbox_provider_readiness_endpoint_passes_only_for_tool_scoped_approval(
    auth_headers,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.api import app

    approval_record = _write_toolbox_approval_record(tmp_path, toolbox_tool_ids=["product-image"])
    _set_ready_toolbox_env(monkeypatch, approval_record)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        product_response = await client.get("/toolbox/product-image/provider-readiness", headers=auth_headers)
        digital_human_response = await client.get("/toolbox/digital-human/provider-readiness", headers=auth_headers)

    assert product_response.status_code == 200, product_response.text
    product_payload = product_response.json()
    assert product_payload["ready_for_authorized_live"] is True
    assert product_payload["provider_call_allowed"] is True
    assert product_payload["approved_provider"] == "poyo"
    assert product_payload["approved_model"] == "seedance-2"
    assert product_payload["approved_budget_limit_usd"] == 1.0
    assert product_payload["blocker_reasons"] == []
    assert "sk_fixture_secret" not in json.dumps(product_payload, ensure_ascii=False)

    assert digital_human_response.status_code == 200, digital_human_response.text
    digital_human_payload = digital_human_response.json()
    assert digital_human_payload["ready_for_authorized_live"] is False
    assert digital_human_payload["provider_call_allowed"] is False
    assert digital_human_payload["blocker_reasons"] == [
        f"approval record sample_plan.{TOOLBOX_TOOL_SCOPE_FIELD} must include digital-human"
    ]


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
    assert payload["plan"]["injection_target_refs"]
    assert payload["job_record"]["status"] == "prepared"
    assert payload["job_record"]["delivery_accepted"] is False
    assert payload["job_record"]["publish_allowed"] is False
    assert payload["injection_targets"]
    assert payload["injection_targets"][0]["artifact_refs"][0].startswith("artifact://toolbox/storyboard/")
    assert payload["injection_targets"][0]["contract_refs"][0].startswith("manifest://toolbox/storyboard/")
    assert payload["injection_targets"][0]["bundle_refs"] == ["bundle_momcozy_candidate"]
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
async def test_toolbox_injection_draft_endpoint_is_read_only_and_refs_only(auth_headers) -> None:
    from src.api import app

    body = _ecommerce_visual_request(raw_text="must-not-leak-injection-brief")
    body["request_id"] = "tbx_req_ecommerce_visual_injection"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        run_response = await client.post(
            "/toolbox/ecommerce-visual/run",
            headers=auth_headers,
            json=body,
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]
        before_response = await client.get(f"/toolbox/runs/{run_id}", headers=auth_headers)
        draft_response = await client.post(f"/toolbox/runs/{run_id}/inject", headers=auth_headers)
        after_response = await client.get(f"/toolbox/runs/{run_id}", headers=auth_headers)

    assert before_response.status_code == 200, before_response.text
    assert draft_response.status_code == 200, draft_response.text
    assert after_response.status_code == 200, after_response.text
    draft = draft_response.json()
    serialized = json.dumps(draft, ensure_ascii=False, sort_keys=True)
    assert draft["draft_id"] == "tbx_injection_draft_tbx_req_ecommerce_visual_injection"
    assert draft["mode"] == "read_only"
    assert draft["state_write"] is False
    assert draft["provider_call"] is False
    assert draft["delivery_accepted"] is False
    assert draft["publish_allowed"] is False
    assert draft["injection_targets"]
    assert draft["artifact_refs"][0].startswith("artifact://toolbox/ecommerce-visual/")
    assert draft["contract_refs"][0].startswith("job://toolbox/") or draft["contract_refs"][0].startswith("manifest://toolbox/")
    assert draft["bundle_refs"] == ["bundle_momcozy_candidate"]
    assert "must-not-leak-injection-brief" not in serialized
    assert "tool_input" not in serialized
    assert "campaign_brief" not in serialized
    before_payload = before_response.json()
    after_payload = after_response.json()
    before_payload.pop("_meta", None)
    after_payload.pop("_meta", None)
    assert before_payload == after_payload


@pytest.mark.asyncio
async def test_toolbox_injection_audit_summary_explains_readiness_without_state_write(auth_headers) -> None:
    from src.api import app

    body = _ecommerce_visual_request(raw_text="must-not-leak-audit-summary-brief")
    body["request_id"] = "tbx_req_ecommerce_visual_audit_summary"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        run_response = await client.post(
            "/toolbox/ecommerce-visual/run",
            headers=auth_headers,
            json=body,
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]
        summary_response = await client.get(f"/toolbox/runs/{run_id}/audit-summary", headers=auth_headers)
        after_response = await client.get(f"/toolbox/runs/{run_id}", headers=auth_headers)

    assert summary_response.status_code == 200, summary_response.text
    assert after_response.status_code == 200, after_response.text
    payload = summary_response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["summary_id"] == "tbx_injection_audit_tbx_req_ecommerce_visual_audit_summary"
    assert payload["ready_for_scenario_injection"] is True
    assert payload["state_write"] is False
    assert payload["provider_call"] is False
    assert payload["delivery_accepted"] is False
    assert payload["publish_allowed"] is False
    assert payload["target_count"] > 0
    assert payload["artifact_ref_count"] > 0
    assert payload["contract_ref_count"] > 0
    assert payload["bundle_ref_count"] == 1
    assert payload["blocking_reasons"] == []
    assert {check["check_id"] for check in payload["checks"]} == {
        "dry_run_status",
        "provider_boundary",
        "artifact_refs",
        "contract_refs",
        "injection_targets",
        "delivery_boundary",
        "bundle_refs",
    }
    assert all(check["status"] == "passed" for check in payload["checks"])
    assert "must-not-leak-audit-summary-brief" not in serialized
    assert "campaign_brief" not in serialized
    assert "tool_input" not in serialized
    assert after_response.json()["job_record"]["status"] == "prepared"


@pytest.mark.asyncio
async def test_toolbox_run_audit_summaries_endpoint_lists_recent_readiness(auth_headers) -> None:
    from src.api import app

    ecommerce_body = _ecommerce_visual_request(raw_text="must-not-leak-summary-list-brief")
    ecommerce_body["request_id"] = "tbx_req_ecommerce_visual_summary_list"
    product_body = _product_image_request()
    product_body["request_id"] = "tbx_req_product_image_summary_list"
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
        list_response = await client.get("/toolbox/runs/audit-summaries?limit=2", headers=auth_headers)
        product_only_response = await client.get(
            "/toolbox/runs/audit-summaries?limit=5&tool_id=product-image",
            headers=auth_headers,
        )

    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert [summary["tool_id"] for summary in payload["summaries"]][:2] == ["product-image", "ecommerce-visual"]
    assert all(summary["ready_for_scenario_injection"] is True for summary in payload["summaries"])
    assert all(summary["state_write"] is False for summary in payload["summaries"])
    assert all(summary["provider_call"] is False for summary in payload["summaries"])
    assert all(summary["delivery_accepted"] is False for summary in payload["summaries"])
    assert all(summary["publish_allowed"] is False for summary in payload["summaries"])
    assert payload["summaries"][0]["target_count"] > 0
    assert payload["summaries"][0]["artifact_ref_count"] > 0
    assert payload["summaries"][0]["contract_ref_count"] > 0
    assert "must-not-leak-summary-list-brief" not in serialized
    assert "campaign_brief" not in serialized
    assert "tool_input" not in serialized
    assert product_only_response.status_code == 200, product_only_response.text
    product_only_payload = product_only_response.json()
    assert product_only_payload["summaries"]
    assert all(summary["tool_id"] == "product-image" for summary in product_only_payload["summaries"])


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
        product_only_response = await client.get(
            "/toolbox/runs?limit=5&tool_id=product-image",
            headers=auth_headers,
        )

    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert [run["tool_id"] for run in payload["runs"]][:2] == ["product-image", "ecommerce-visual"]
    assert payload["runs"][0]["job_record"]["publish_allowed"] is False
    assert payload["runs"][0]["artifacts"][0]["artifact_ref"].startswith("artifact://toolbox/product-image/")
    assert payload["runs"][0]["injection_targets"][0]["scenario"] in {"s1", "s2", "s5"}
    assert payload["runs"][0]["injection_targets"][0]["artifact_refs"][0].startswith("artifact://toolbox/product-image/")
    assert "must-not-leak-run-list-brief" not in serialized
    assert "tool_input" not in serialized
    assert "campaign_brief" not in serialized
    assert product_only_response.status_code == 200, product_only_response.text
    product_only_payload = product_only_response.json()
    assert product_only_payload["runs"]
    assert all(run["tool_id"] == "product-image" for run in product_only_payload["runs"])
    assert product_only_payload["runs"][0]["run_id"] == "tbx_run_tbx_req_product_image_recent"


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


def _set_ready_toolbox_env(monkeypatch: pytest.MonkeyPatch, approval_record: Path) -> None:
    account_readiness = _write_account_readiness_record(approval_record.parent)
    monkeypatch.setenv(RUN_TOKEN_SMOKE_ENV, "1")
    monkeypatch.setenv(APPROVAL_RECORD_ENV, str(approval_record))
    monkeypatch.setenv(ACCOUNT_READINESS_RECORD_ENV, str(account_readiness))
    for key_name in REQUIRED_API_KEY_ENVS:
        monkeypatch.setenv(key_name, f"sk_fixture_secret_{key_name.lower()}")


def _write_toolbox_approval_record(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "authorized-live-toolbox-approval.json"
    provider = str(overrides.get("provider", "poyo"))
    model = str(overrides.get("model", "seedance-2"))
    budget_limit = str(overrides.get("budget_limit", "$1.00"))
    toolbox_tool_ids = overrides.pop("toolbox_tool_ids", ["product-image"])
    payload: dict[str, Any] = {
        "approval_id": "approval_toolbox_router_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-06T00:00:00Z",
        "provider": provider,
        "model": model,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "budget_limit": budget_limit,
        "budget_limit_usd": 1.0,
        "sample_plan": {
            "max_sample_count": 2,
            "max_provider_calls": 2,
            "scenarios": ["toolbox"],
            "s5_requires_separate_confirmation": True,
            TOOLBOX_TOOL_SCOPE_FIELD: toolbox_tool_ids,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": 1.0,
            "per_job_cost_ceiling_usd": 0.5,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
        "approval_statement": APPROVAL_STATEMENT_TEMPLATE.format(
            provider=provider,
            model=model,
            budget_limit=budget_limit,
        ),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _write_account_readiness_record(tmp_path: Path) -> Path:
    path = tmp_path / "provider-account-readiness.json"
    payload: dict[str, Any] = {
        "template_only": False,
        "readiness_id": "account_readiness_toolbox_router_fixture",
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider": "poyo",
        "checked_by": "user",
        "checked_at": "2026-06-06T00:00:00Z",
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "available_credit_usd": 1.0,
        "minimum_required_credit_usd": 1.0,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path
