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
    ToolboxInjectionAuditCheck,
    ToolboxInjectionAuditSummary,
    ToolboxInjectionDraft,
    ToolboxInjectionTarget,
    ToolboxPlan,
    ToolboxRequest,
    ToolboxRunMode,
    ToolboxRunState,
    ToolboxRunStatus,
    ToolboxToolId,
)
from src.pipeline.toolbox.planner import build_toolbox_run_state, project_toolbox_run_state

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


def test_momcozy_toolbox_l2_matrix_covers_s5_and_image_tools_without_provider_calls():
    data = json.loads((FIXTURE_ROOT / "momcozy_toolbox_l2_fixture_matrix.json").read_text())
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)

    assert data["evidence_level"] == "L2-fixture-or-dry-run"
    assert data["brand_id"] == "momcozy"
    assert data["brand_bundle_ref"] == "bundle_momcozy_candidate"
    assert data["approved_token_count"] == 0
    assert data["provider_calls_allowed"] is False
    assert data["delivery_accepted"] is False
    assert {case["scenario"] for case in data["scenario_cases"]} == {"s5"}
    assert {case["tool_id"] for case in data["toolbox_image_cases"]} == {
        "product-image",
        "six-view",
        "ecommerce-visual",
    }
    assert all(case["provider_call"] is False for case in data["scenario_cases"])
    assert all(case["provider_call"] is False for case in data["toolbox_image_cases"])
    assert all(case["delivery_accepted"] is False for case in data["toolbox_image_cases"])
    assert all(case["approved_brand_token"] is False for case in data["toolbox_image_cases"])
    assert "prompt_payload" not in serialized
    assert "brand_asset_source_body" not in serialized


def test_momcozy_toolbox_image_matrix_projects_s5_refs_only_in_dry_run():
    data = json.loads((FIXTURE_ROOT / "momcozy_toolbox_l2_fixture_matrix.json").read_text())

    for case in data["toolbox_image_cases"]:
        request = ToolboxRequest.model_validate(case["request"])
        state = build_toolbox_run_state(request)
        projection = project_toolbox_run_state(state)
        serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True)

        assert request.brand_bundle_ref == "bundle_momcozy_candidate"
        assert "s5" in case["target_scenarios"]
        assert state.status == ToolboxRunStatus.ACCEPTED_DRY_RUN
        assert state.plan.provider_call is False
        assert state.plan.delivery_accepted is False
        assert state.job_record is not None
        assert state.job_record.status == MediaJobStatus.PREPARED
        assert state.job_record.provider_job_id is None
        assert state.job_record.delivery_accepted is False
        assert state.job_record.publish_allowed is False
        assert any(target.scenario == "s5" for target in state.injection_targets)
        assert all(target.bundle_refs == ["bundle_momcozy_candidate"] for target in state.injection_targets)
        assert "fixture brief must stay out of public projections" not in serialized
        assert "provider_job_id" not in serialized
        assert "submitted" not in serialized


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


def test_toolbox_injection_draft_rejects_state_write_or_publish_boundary():
    target = ToolboxInjectionTarget(
        target_ref="artifact://toolbox/product-image/001/inject/s1",
        scenario="s1",
        step_name="product_assets",
        artifact_refs=["artifact://toolbox/product-image/001"],
        contract_refs=["manifest://toolbox/product-image/001", "job://toolbox/tbx_req_product_image_001"],
        bundle_refs=["bundle_momcozy_candidate"],
    )

    with pytest.raises(ValidationError, match="cannot write scenario state"):
        ToolboxInjectionDraft(
            draft_id="tbx_injection_draft_product_image_001",
            draft_ref="artifact://toolbox/product-image/001/injection-draft",
            run_id="tbx_run_product_image_001",
            tool_id=ToolboxToolId.PRODUCT_IMAGE,
            state_write=True,
            injection_targets=[target],
        )

    with pytest.raises(ValidationError, match="cannot allow publish"):
        ToolboxInjectionDraft(
            draft_id="tbx_injection_draft_product_image_001",
            draft_ref="artifact://toolbox/product-image/001/injection-draft",
            run_id="tbx_run_product_image_001",
            tool_id=ToolboxToolId.PRODUCT_IMAGE,
            publish_allowed=True,
            injection_targets=[target],
        )


def test_toolbox_injection_audit_summary_rejects_boundary_crossing_or_false_ready():
    check = ToolboxInjectionAuditCheck(
        check_id="artifact_refs",
        label="Artifact refs",
        status="blocked",
        evidence_refs=[],
        message="missing artifact refs",
    )

    with pytest.raises(ValidationError, match="cannot call provider"):
        ToolboxInjectionAuditSummary(
            summary_id="tbx_injection_audit_product_image_001",
            run_id="tbx_run_product_image_001",
            tool_id=ToolboxToolId.PRODUCT_IMAGE,
            provider_call=True,
            checks=[check],
        )

    with pytest.raises(ValidationError, match="requires no blocking reasons"):
        ToolboxInjectionAuditSummary(
            summary_id="tbx_injection_audit_product_image_001",
            run_id="tbx_run_product_image_001",
            tool_id=ToolboxToolId.PRODUCT_IMAGE,
            ready_for_scenario_injection=True,
            checks=[check],
            blocking_reasons=["missing artifact refs"],
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
