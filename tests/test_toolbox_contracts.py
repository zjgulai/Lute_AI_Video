from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.commercial_contracts import MediaJobRecord, MediaJobSpec, MediaJobStatus, PlatformTarget
from src.models.toolbox_contracts import (
    DigitalHumanInput,
    ProductImageInput,
    SixViewInput,
    StoryboardInput,
    ToolboxArtifact,
    ToolboxAssetRef,
    ToolboxPlan,
    ToolboxRequest,
    ToolboxRunMode,
    ToolboxRunState,
    ToolboxRunStatus,
    ToolboxToolId,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "toolbox"


def test_toolbox_contract_cases_cover_first_five_tools():
    data = json.loads((FIXTURE_ROOT / "toolbox_contract_cases.json").read_text())

    assert data["evidence_level"] == "L2-fixture-or-dry-run"
    assert {case["tool_id"] for case in data["cases"]} == {
        "product-image",
        "six-view",
        "ecommerce-visual",
        "digital-human",
        "storyboard",
    }
    assert all(case["provider_call"] is False for case in data["cases"])
    assert all(case["delivery_accepted"] is False for case in data["cases"])


def test_product_image_request_and_plan_remain_dry_run():
    request = _product_image_request()
    plan = ToolboxPlan(
        plan_id="plan_product_image_001",
        request_id=request.request_id,
        tool_id=ToolboxToolId.PRODUCT_IMAGE,
        required_checks=["product_truth", "claim_evidence", "brand_rights"],
    )

    assert request.tool_input.tool_id == ToolboxToolId.PRODUCT_IMAGE
    assert plan.mode == ToolboxRunMode.DRY_RUN
    assert plan.provider_call is False
    assert plan.delivery_accepted is False
    assert plan.evidence_level == "L2-fixture-or-dry-run"


def test_toolbox_request_rejects_tool_id_payload_mismatch():
    with pytest.raises(ValidationError, match="tool_id must match tool_input.tool_id"):
        ToolboxRequest(
            request_id="tbx_req_bad_tool",
            tool_id=ToolboxToolId.SIX_VIEW,
            brand_id="momcozy",
            platform_target=PlatformTarget(platform="shopify", aspect_ratio="1:1"),
            tool_input=ProductImageInput(
                product_ref="sku://momcozy/m9",
                image_type="main_white_bg",
                aspect_ratio="1:1",
            ),
        )


def test_toolbox_asset_ref_rejects_arbitrary_local_paths():
    with pytest.raises(ValidationError, match="asset_ref must use governed ref scheme"):
        ToolboxAssetRef(asset_ref="/Users/pray/private/product.png", asset_kind="image")


def test_toolbox_inputs_reject_prompt_payload_or_raw_brand_body():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProductImageInput.model_validate({
            "tool_id": "product-image",
            "product_ref": "sku://momcozy/m9",
            "image_type": "main_white_bg",
            "prompt_payload": "raw prompt must not enter contract",
        })

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProductImageInput.model_validate({
            "tool_id": "product-image",
            "product_ref": "sku://momcozy/m9",
            "image_type": "main_white_bg",
            "brand_asset_source_body": "raw brand asset text must not enter contract",
        })


def test_six_view_requires_canonical_views():
    with pytest.raises(ValidationError, match="six-view input requires canonical six views"):
        SixViewInput(
            product_ref="sku://momcozy/m9",
            required_views=["front", "back", "left"],
        )


def test_digital_human_requires_consent_for_avatar_or_voice_clone():
    with pytest.raises(ValidationError, match="digital human avatar requires consent_ref"):
        DigitalHumanInput(
            presenter_policy="brand_demo",
            avatar_ref="avatar://momcozy/demo_presenter",
            voice_policy="tts",
        )

    with pytest.raises(ValidationError, match="voice clone requires consent_ref"):
        DigitalHumanInput(
            presenter_policy="brand_demo",
            voice_policy="voice_clone",
        )


def test_storyboard_longform_requires_timeline_and_review_floor():
    with pytest.raises(ValidationError, match="90s\\+ storyboard requires timeline blocks and review checkpoints"):
        StoryboardInput(
            brief="Build a 120 second product education video",
            duration_target_seconds=120,
            planned_timeline_block_count=0,
            review_checkpoint_refs=[],
        )


def test_toolbox_plan_blocks_provider_call_in_dry_run():
    with pytest.raises(ValidationError, match="dry-run toolbox plan cannot call provider"):
        ToolboxPlan(
            plan_id="plan_bad_provider_call",
            request_id="tbx_req_001",
            tool_id=ToolboxToolId.PRODUCT_IMAGE,
            mode=ToolboxRunMode.DRY_RUN,
            provider_call=True,
        )


def test_toolbox_run_state_rejects_submitted_job_in_dry_run():
    request = _product_image_request()
    plan = ToolboxPlan(
        plan_id="plan_product_image_001",
        request_id=request.request_id,
        tool_id=ToolboxToolId.PRODUCT_IMAGE,
    )
    job_record = MediaJobRecord(
        job_id="job_product_image_001",
        spec=MediaJobSpec(
            job_id="job_product_image_001",
            provider="poyo",
            model="gpt-image-2",
            scenario="toolbox",
            step_name="product-image",
            prompt_hash="sha256:fixture",
            prompt_compile_id="compile_fixture",
        ),
        status=MediaJobStatus.SUBMITTED,
    )

    with pytest.raises(ValidationError, match="dry-run toolbox state cannot include submitted provider job"):
        ToolboxRunState(
            run_id="tbx_run_bad_job",
            request=request,
            plan=plan,
            status=ToolboxRunStatus.PREPARED,
            job_record=job_record,
        )


def test_toolbox_public_projection_keeps_refs_but_not_payload_bodies():
    request = _product_image_request()
    plan = ToolboxPlan(
        plan_id="plan_product_image_001",
        request_id=request.request_id,
        tool_id=ToolboxToolId.PRODUCT_IMAGE,
    )
    run_state = ToolboxRunState(
        run_id="tbx_run_projection",
        request=request,
        plan=plan,
        status=ToolboxRunStatus.ACCEPTED_DRY_RUN,
        artifacts=[
            ToolboxArtifact(
                artifact_id="artifact_product_image_001",
                tool_id=ToolboxToolId.PRODUCT_IMAGE,
                artifact_type="product_image_set",
                artifact_ref="artifact://toolbox/product-image/001",
            )
        ],
    )

    projection = run_state.public_projection()
    serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True)

    assert "bundle_momcozy_candidate" in serialized
    assert "artifact://toolbox/product-image/001" in serialized
    assert "prompt_payload" not in serialized
    assert "brand_asset_source_body" not in serialized
    assert "raw_prompt" not in serialized


def _product_image_request() -> ToolboxRequest:
    return ToolboxRequest(
        request_id="tbx_req_product_image_001",
        tool_id=ToolboxToolId.PRODUCT_IMAGE,
        brand_id="momcozy",
        platform_target=PlatformTarget(platform="shopify", aspect_ratio="1:1"),
        brand_bundle_ref="bundle_momcozy_candidate",
        asset_refs=[
            ToolboxAssetRef(
                asset_ref="asset://brand/momcozy/product/m9-front",
                asset_kind="image",
                rights_ref="rights://candidate/m9",
            )
        ],
        tool_input=ProductImageInput(
            product_ref="sku://momcozy/m9",
            image_type="main_white_bg",
            aspect_ratio="1:1",
            reference_asset_refs=["asset://brand/momcozy/product/m9-front"],
        ),
    )
