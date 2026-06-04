from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.commercial_contracts import (
    AuditEvidenceBundle,
    EditDecision,
    EditDecisionList,
    LongformProductionContract,
    PlatformTarget,
    QualityContract,
    SceneLedger,
    ShotLedger,
    StoryboardShotSchema,
    TimelineBlock,
    TimelineManifest,
)
from src.pipeline.longform_audit_bundle import build_longform_audit_bundle

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "commercial_video" / "longform_audit_bundle_cases.json"


def test_longform_audit_blocks_90s_output_without_timeline_blocks():
    contract = LongformProductionContract.model_construct(
        contract_id="lfc_missing_timeline_blocks",
        scenario="s3",
        brand_id="momcozy",
        target_duration_seconds=120,
        scene_ledger_id="scene_fixture",
        timeline_manifest=None,
        shot_ledger=_shot_ledger("s3", shot_count=3),
        review_checkpoint_ids=["review_longform_fixture"],
    )

    bundle = build_longform_audit_bundle(
        longform_contract=contract,
        quality_contract=_quality_contract("s3"),
        evidence=_evidence("s3"),
    )

    assert bundle.gate_decision.status == "blocked"
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert "longform_timeline_blocks_present" in [action.check for action in bundle.repair_plan.actions]
    assert "provider job submitted" in bundle.forbidden_claims


def test_longform_audit_blocks_single_shot_300s_structure():
    contract = LongformProductionContract.model_construct(
        contract_id="lfc_single_shot_300s",
        scenario="s3",
        brand_id="momcozy",
        target_duration_seconds=300,
        scene_ledger=_scene_ledger("s3"),
        timeline_manifest=_timeline_manifest("s3", duration=300),
        shot_ledger=_shot_ledger("s3", shot_count=1, duration=300),
        edit_decision_list=_edl(),
        review_checkpoint_ids=["review_longform_fixture"],
    )

    bundle = build_longform_audit_bundle(
        longform_contract=contract,
        quality_contract=_quality_contract("s3"),
        evidence=_evidence("s3"),
    )

    assert bundle.gate_decision.status == "blocked"
    assert "longform_shot_structure_pass" in [action.check for action in bundle.repair_plan.actions]
    assert any("single-shot" in reason for reason in bundle.gate_decision.reasons)


def test_longform_audit_blocks_missing_source_fingerprint_edl_and_caption_safe_zone():
    bundle = build_longform_audit_bundle(
        longform_contract=_longform_contract("s3"),
        quality_contract=_quality_contract("s3"),
        evidence=_evidence(
            "s3",
            rights_evidence_refs=[],
            source_fingerprint_refs=[],
            edit_decision_list_refs=[],
            caption_safe_zone_refs=[],
        ),
    )

    checks = [action.check for action in bundle.repair_plan.actions]
    assert bundle.gate_decision.status == "blocked"
    assert "source_rights_pass" in checks
    assert "source_fingerprint_pass" in checks
    assert "edl_pass" in checks
    assert "caption_safe_zone_pass" in checks
    assert bundle.gate_decision.publish_allowed is False


def test_longform_audit_passing_gate_requires_review_not_delivery_acceptance():
    bundle = build_longform_audit_bundle(
        longform_contract=_longform_contract("s4"),
        quality_contract=_quality_contract("s4"),
        evidence=_evidence("s4"),
    )

    assert bundle.evidence_level == "L2-fixture-or-dry-run"
    assert bundle.gate_decision.status == "review_required"
    assert bundle.gate_decision.requires_human_review is True
    assert bundle.gate_decision.publish_allowed is False
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert bundle.repair_plan.actions == []
    assert "delivery accepted" in bundle.forbidden_claims


@pytest.mark.parametrize("case", json.loads(FIXTURE_PATH.read_text())["cases"], ids=lambda case: case["case_id"])
def test_longform_audit_bundle_fixture_cases(case: dict[str, object]):
    payload = json.loads(FIXTURE_PATH.read_text())
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    scenario = str(case["scenario"])
    evidence_overrides = case.get("evidence_overrides")
    assert isinstance(evidence_overrides, dict)

    bundle = build_longform_audit_bundle(
        longform_contract=_longform_contract(
            scenario,
            target_duration_seconds=int(case["target_duration_seconds"]),
        ),
        quality_contract=_quality_contract(scenario),
        evidence=_evidence(scenario, **evidence_overrides),
    )

    checks = [action.check for action in bundle.repair_plan.actions]
    assert bundle.gate_decision.status == case["expected_status"]
    assert bundle.gate_decision.publish_allowed == case["expected_publish_allowed"]
    assert bundle.publish_allowed is False
    for expected_check in case["expected_checks"]:
        assert expected_check in checks


def _longform_contract(scenario: str, *, target_duration_seconds: int = 120) -> LongformProductionContract:
    return LongformProductionContract(
        contract_id=f"lfc_{scenario}_ready_fixture",
        scenario=scenario,
        brand_id="momcozy",
        target_duration_seconds=target_duration_seconds,
        scene_ledger=_scene_ledger(scenario),
        timeline_manifest=_timeline_manifest(scenario, duration=target_duration_seconds),
        shot_ledger=_shot_ledger(scenario, shot_count=3),
        edit_decision_list=_edl(),
        review_checkpoint_ids=["review_longform_fixture"],
    )


def _quality_contract(scenario: str) -> QualityContract:
    return QualityContract(
        contract_id=f"qc_{scenario}_longform_fixture",
        scenario=scenario,
        stage="longform_delivery",
        platform="tiktok",
        brand_id="momcozy",
    )


def _evidence(
    scenario: str,
    *,
    rights_evidence_refs: list[str] | None = None,
    source_fingerprint_refs: list[str] | None = None,
    timeline_manifest_refs: list[str] | None = None,
    edit_decision_list_refs: list[str] | None = None,
    caption_safe_zone_refs: list[str] | None = None,
    caption_safe_zone_violations: list[str] | None = None,
) -> AuditEvidenceBundle:
    return AuditEvidenceBundle(
        evidence_bundle_id=f"aeb_{scenario}_longform_fixture",
        scenario=scenario,
        stage="longform_delivery",
        brand_bundle_id="bundle_longform_fixture",
        source_token_ids=["bat_longform_fixture"],
        artifact_manifest_id="artifact_longform_fixture",
        rights_evidence_refs=rights_evidence_refs if rights_evidence_refs is not None else ["rights_longform_fixture"],
        source_fingerprint_refs=source_fingerprint_refs
        if source_fingerprint_refs is not None
        else ["fingerprint_longform_fixture"],
        timeline_manifest_refs=timeline_manifest_refs if timeline_manifest_refs is not None else ["timeline_manifest_fixture"],
        edit_decision_list_refs=edit_decision_list_refs if edit_decision_list_refs is not None else ["edl_fixture"],
        caption_safe_zone_refs=caption_safe_zone_refs if caption_safe_zone_refs is not None else ["caption_safe_fixture"],
        caption_safe_zone_violations=caption_safe_zone_violations or [],
        platform_target=PlatformTarget(platform="tiktok", duration_seconds=120),
    )


def _scene_ledger(scenario: str) -> SceneLedger:
    return SceneLedger(
        scene_ledger_id=f"scene_{scenario}_fixture",
        scenario=scenario,
        scene_ids=["scene_001", "scene_002"],
        narrative_beats=["setup", "payoff"],
        target_duration_seconds=120,
    )


def _timeline_manifest(scenario: str, *, duration: int = 120) -> TimelineManifest:
    return TimelineManifest(
        timeline_manifest_id=f"timeline_{scenario}_fixture",
        scenario=scenario,
        duration_seconds=duration,
        timeline_blocks=[
            TimelineBlock(
                block_id="block_001",
                start_seconds=0,
                end_seconds=duration / 2,
                scene_ref="scene_001",
                shot_refs=["shot_001"],
            ),
            TimelineBlock(
                block_id="block_002",
                start_seconds=duration / 2,
                end_seconds=duration,
                scene_ref="scene_002",
                shot_refs=["shot_002"],
            ),
        ],
    )


def _shot_ledger(scenario: str, *, shot_count: int, duration: int = 120) -> ShotLedger:
    shot_duration = max(1, duration // max(shot_count, 1))
    return ShotLedger(
        shot_ledger_id=f"shots_{scenario}_{shot_count}_fixture",
        scenario=scenario,
        shots=[
            StoryboardShotSchema(
                shot_id=f"shot_{index:03d}",
                scenario=scenario,
                beat=f"beat {index}",
                visual_description="fixture longform shot",
                duration_seconds=shot_duration,
            )
            for index in range(1, shot_count + 1)
        ],
    )


def _edl() -> EditDecisionList:
    return EditDecisionList(
        edl_id="edl_longform_fixture",
        source_timeline_manifest_id="timeline_s3_fixture",
        decisions=[
            EditDecision(
                edit_id="edit_001",
                source_block_id="block_001",
                action="keep",
            )
        ],
    )
