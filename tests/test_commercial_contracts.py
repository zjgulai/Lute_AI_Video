from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    CandidateTokenLedger,
    CapabilityValue,
    EditDecision,
    EditDecisionList,
    LicenseStatus,
    LongformProductionContract,
    PlatformTarget,
    ProviderCapability,
    PublishPolicy,
    QualityContract,
    ReframeJob,
    SceneLedger,
    ShotLedger,
    StoryboardShotSchema,
    TimelineBlock,
    TimelineManifest,
    TokenReview,
    TokenStatus,
    TokenStrength,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"


def test_b001_b017_fixture_cases_exist():
    data = json.loads((FIXTURE_ROOT / "b001_b017_contract_cases.json").read_text())

    assert len(data["cases"]) == 17
    assert data["cases"][0]["case_id"] == "B-001"
    assert data["cases"][-1]["case_id"] == "B-017"


def test_candidate_ledger_parses_and_contains_no_approved_tokens():
    data = json.loads((FIXTURE_ROOT / "momcozy_candidate_ledger.json").read_text())
    ledger = CandidateTokenLedger.model_validate(data)

    assert ledger.brand_id == "momcozy"
    assert ledger.approved_token_count == 0
    assert {token.status for token in ledger.candidate_tokens} == {TokenStatus.CANDIDATE}
    assert all(token.license_status == LicenseStatus.UNKNOWN for token in ledger.candidate_tokens)


def test_candidate_ledger_rejects_approved_token_claim():
    data = json.loads((FIXTURE_ROOT / "momcozy_candidate_ledger.json").read_text())
    data["approved_token_count"] = 1

    with pytest.raises(ValidationError, match="candidate token ledger"):
        CandidateTokenLedger.model_validate(data)


def test_unknown_rights_tokens_do_not_enter_approved_bundle():
    candidate = BrandAssetToken(
        token_id="bat_candidate",
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.CANDIDATE,
        strength=TokenStrength.HARD_FOR_REVIEW_ONLY,
        scenario_scope=["s1"],
        step_scope=["script"],
    )

    bundle = BrandConstraintBundle.build_approved(
        bundle_id="bundle_s1_script",
        brand_id="momcozy",
        scenario="s1",
        step="script",
        tokens=[candidate],
    )

    assert bundle.hard_tokens == []
    assert bundle.soft_tokens == []
    assert bundle.rejected_token_ids == ["bat_candidate"]


def test_approved_bundle_preserves_hard_and_soft_tokens_ordered_by_priority():
    hard = _approved_token("bat_hard", "claim_guardrail", TokenStrength.HARD, priority=90)
    soft = _approved_token("bat_soft", "visual_identity", TokenStrength.SOFT, priority=40)

    bundle = BrandConstraintBundle.build_approved(
        bundle_id="bundle_s1_script",
        brand_id="momcozy",
        scenario="s1",
        step="script",
        tokens=[soft, hard],
    )

    assert [token.token_id for token in bundle.hard_tokens] == ["bat_hard"]
    assert [token.token_id for token in bundle.soft_tokens] == ["bat_soft"]
    assert bundle.source_token_ids == ["bat_hard", "bat_soft"]


def test_provider_capability_unknown_is_not_supported():
    capability = ProviderCapability(
        capability_id="cap_unknown",
        provider="poyo",
        model="seedance-2",
        supports_reference_images=CapabilityValue.UNKNOWN,
    )

    assert capability.feature_is_supported("supports_reference_images") is False


def test_quality_contract_publish_default_must_fail_closed():
    with pytest.raises(ValidationError, match="publish_allowed"):
        QualityContract(
            contract_id="qc_bad",
            scenario="s2",
            stage="final_video",
            platform="tiktok",
            brand_id="momcozy",
            publish_policy=PublishPolicy(publish_allowed_default=True),
        )


def test_longform_contract_floor_requires_scene_timeline_and_review_markers():
    incomplete = LongformProductionContract(
        contract_id="lf_incomplete",
        scenario="s2",
        brand_id="momcozy",
        target_duration_seconds=60,
        scene_ledger_id="scene_001",
    )
    complete = LongformProductionContract(
        contract_id="lf_complete",
        scenario="s2",
        brand_id="momcozy",
        target_duration_seconds=180,
        scene_ledger=SceneLedger(
            scene_ledger_id="scene_001",
            scenario="s2",
            scene_ids=["scene_intro", "scene_demo"],
        ),
        timeline_manifest=TimelineManifest(
            timeline_manifest_id="timeline_001",
            scenario="s2",
            duration_seconds=180,
            timeline_blocks=[
                TimelineBlock(
                    block_id="block_intro",
                    start_seconds=0,
                    end_seconds=90,
                    scene_ref="scene_intro",
                    shot_refs=["shot_intro"],
                ),
                TimelineBlock(
                    block_id="block_demo",
                    start_seconds=90,
                    end_seconds=180,
                    scene_ref="scene_demo",
                    shot_refs=["shot_demo"],
                ),
            ],
        ),
        review_checkpoint_ids=["review_001"],
    )

    assert incomplete.has_longform_delivery_floor() is False
    assert complete.has_longform_delivery_floor() is True


def test_timeline_manifest_blocks_90s_plus_without_timeline_blocks():
    with pytest.raises(ValidationError, match="timeline blocks"):
        TimelineManifest(
            timeline_manifest_id="timeline_missing_blocks",
            scenario="s2",
            duration_seconds=120,
            timeline_blocks=[],
        )


def test_longform_contract_blocks_90s_plus_without_structured_timeline():
    with pytest.raises(ValidationError, match="timeline manifest"):
        LongformProductionContract(
            contract_id="lf_missing_timeline",
            scenario="s2",
            brand_id="momcozy",
            target_duration_seconds=120,
            scene_ledger=SceneLedger(
                scene_ledger_id="scene_001",
                scenario="s2",
                scene_ids=["scene_intro", "scene_demo"],
            ),
            timeline_manifest_id="timeline_id_without_blocks",
            review_checkpoint_ids=["review_001"],
        )


def test_longform_contract_blocks_single_shot_300s_structure():
    with pytest.raises(ValidationError, match="single-shot 300s"):
        LongformProductionContract(
            contract_id="lf_single_shot_300",
            scenario="s2",
            brand_id="momcozy",
            target_duration_seconds=300,
            scene_ledger=SceneLedger(
                scene_ledger_id="scene_single",
                scenario="s2",
                scene_ids=["scene_single"],
            ),
            shot_ledger=ShotLedger(
                shot_ledger_id="shot_ledger_single",
                scenario="s2",
                shots=[
                    StoryboardShotSchema(
                        shot_id="shot_single",
                        scenario="s2",
                        beat="single sustained scene",
                        visual_description="One uninterrupted product scene",
                        duration_seconds=300,
                    )
                ],
            ),
            timeline_manifest=TimelineManifest(
                timeline_manifest_id="timeline_single",
                scenario="s2",
                duration_seconds=300,
                timeline_blocks=[
                    TimelineBlock(
                        block_id="block_single",
                        start_seconds=0,
                        end_seconds=300,
                        scene_ref="scene_single",
                        shot_refs=["shot_single"],
                    )
                ],
            ),
            review_checkpoint_ids=["review_001"],
        )


def test_longform_auxiliary_objects_are_fixture_ready_without_provider_calls():
    edl = EditDecisionList(
        edl_id="edl_fixture",
        source_timeline_manifest_id="timeline_001",
        decisions=[
            EditDecision(
                edit_id="edit_trim_intro",
                source_block_id="block_intro",
                action="trim",
                target_start_seconds=0,
                target_end_seconds=42,
            )
        ],
    )
    reframe = ReframeJob(
        reframe_job_id="reframe_9x16",
        source_artifact_ref="fixture://final.mp4",
        target_aspect_ratio="9:16",
    )

    assert edl.generated_from == "fixture"
    assert reframe.status == "planned"
    assert reframe.caption_safe_zone_required is True
    assert PlatformTarget(platform="tiktok").aspect_ratio == "9:16"


def _approved_token(token_id: str, token_type: str, strength: TokenStrength, priority: int) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type=token_type,
        status=TokenStatus.APPROVED,
        strength=strength,
        priority=priority,
        scenario_scope=["s1"],
        step_scope=["script"],
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="self"),
    )
