from __future__ import annotations

import json
from pathlib import Path

from src.models.commercial_contracts import AuditEvidenceBundle, PlatformTarget, QualityContract
from src.quality.commercial_gate import evaluate_quality_contract

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "commercial_video" / "quality_gate_cases.json"


def test_rights_failure_blocks_delivery_even_with_high_advisory_score():
    contract = _quality_contract(blocking_checks=["rights_pass"], advisory_checks=["brand_voice_alignment"])
    evidence = _evidence_bundle(rights_evidence_refs=[])

    result = evaluate_quality_contract(contract, evidence, advisory_scores={"brand_voice_alignment": 0.99})

    assert result.blocking.passed is False
    assert result.delivery.accepted is False
    assert result.delivery.publish_allowed is False
    assert result.blocking.failures[0].check == "rights_pass"


def test_missing_claim_evidence_blocks_delivery():
    contract = _quality_contract(blocking_checks=["claim_substantiation_pass"])
    evidence = _evidence_bundle(claim_evidence_refs=[])

    result = evaluate_quality_contract(contract, evidence)

    assert result.blocking.passed is False
    assert result.blocking.failures[0].reason == "missing claim evidence"


def test_children_direct_reference_blocks_s5():
    contract = _quality_contract(scenario="s5", blocking_checks=["children_safety_pass"])
    evidence = _evidence_bundle(scenario="s5", children_direct_reference=True)

    result = evaluate_quality_contract(contract, evidence)

    assert result.blocking.passed is False
    assert result.blocking.failures[0].check == "children_safety_pass"


def test_s3_source_fingerprint_is_required_for_remix_boundary():
    contract = _quality_contract(scenario="s3", blocking_checks=["source_fingerprint_pass"])
    evidence = _evidence_bundle(scenario="s3", source_fingerprint_refs=[])

    result = evaluate_quality_contract(contract, evidence)

    assert result.blocking.passed is False
    assert result.blocking.failures[0].reason == "missing source fingerprint evidence"


def test_required_evidence_missing_fails_closed():
    contract = _quality_contract(required_evidence=["brand_bundle_id", "rights_evidence_refs"])
    evidence = _evidence_bundle(brand_bundle_id=None, rights_evidence_refs=[])

    result = evaluate_quality_contract(contract, evidence)

    assert result.blocking.passed is False
    assert {failure.evidence_ref for failure in result.blocking.failures} == {
        "brand_bundle_id",
        "rights_evidence_refs",
    }


def test_blocking_pass_still_requires_human_review_before_publish():
    contract = _quality_contract(blocking_checks=["rights_pass", "claim_substantiation_pass"])
    evidence = _evidence_bundle(
        rights_evidence_refs=["rights_fixture"],
        claim_evidence_refs=["claim_fixture"],
    )

    result = evaluate_quality_contract(contract, evidence)

    assert result.blocking.passed is True
    assert result.delivery.accepted is False
    assert result.delivery.publish_allowed is False
    assert result.delivery.requires_human_review is True


def test_c5_fixture_cases_cover_required_scenario_gates():
    payload = json.loads(FIXTURE_PATH.read_text())
    cases = {case["case_id"]: case for case in payload["cases"]}

    assert set(cases) == {
        "s1_claim_missing_blocks_delivery",
        "s3_source_fingerprint_missing_blocks_remix",
        "s3_longform_missing_timeline_edl_blocks",
        "s4_footage_rights_missing_blocks_cutdown",
        "s4_caption_safe_zone_missing_blocks_reframe",
        "s5_children_direct_reference_blocks_vlog",
        "caption_safe_zone_low_score_requires_review",
    }
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"


def test_blocked_result_includes_gate_decision_and_repair_plan():
    contract = _quality_contract(
        scenario="s1",
        blocking_checks=["claim_substantiation_pass"],
        required_evidence=["claim_evidence_refs"],
    )
    evidence = _evidence_bundle(scenario="s1", claim_evidence_refs=[])

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert result.gate_decision.publish_allowed is False
    assert result.gate_decision.blocking_failure_count == 2
    assert result.gate_decision.repair_plan_id == result.repair_plan.plan_id
    assert [action.check for action in result.repair_plan.actions] == [
        "required_evidence",
        "claim_substantiation_pass",
    ]


def test_s4_missing_footage_rights_has_repair_action():
    contract = _quality_contract(
        scenario="s4",
        blocking_checks=["footage_rights_pass"],
        required_evidence=["rights_evidence_refs"],
    )
    evidence = _evidence_bundle(scenario="s4", rights_evidence_refs=[])

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert any(action.check == "footage_rights_pass" for action in result.repair_plan.actions)
    assert "rights evidence" in result.repair_plan.actions[-1].recommendation


def test_s3_longform_gate_blocks_missing_source_rights_timeline_and_edl():
    contract = _quality_contract(
        scenario="s3",
        blocking_checks=[
            "source_rights_pass",
            "source_fingerprint_pass",
            "timeline_manifest_pass",
            "edl_pass",
        ],
    )
    evidence = _evidence_bundle(
        scenario="s3",
        rights_evidence_refs=[],
        source_fingerprint_refs=[],
        timeline_manifest_refs=[],
        edit_decision_list_refs=[],
    )

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert result.gate_decision.publish_allowed is False
    assert [action.check for action in result.repair_plan.actions] == [
        "source_rights_pass",
        "source_fingerprint_pass",
        "timeline_manifest_pass",
        "edl_pass",
    ]


def test_s4_longform_gate_blocks_missing_footage_rights_edl_and_caption_safe_zone():
    contract = _quality_contract(
        scenario="s4",
        blocking_checks=["footage_rights_pass", "edl_pass", "caption_safe_zone_pass"],
    )
    evidence = _evidence_bundle(
        scenario="s4",
        rights_evidence_refs=[],
        edit_decision_list_refs=[],
        caption_safe_zone_refs=[],
    )

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert result.gate_decision.publish_allowed is False
    assert [action.check for action in result.repair_plan.actions] == [
        "footage_rights_pass",
        "edl_pass",
        "caption_safe_zone_pass",
    ]


def test_caption_safe_zone_violation_blocks_even_with_evidence_ref():
    contract = _quality_contract(scenario="s4", blocking_checks=["caption_safe_zone_pass"])
    evidence = _evidence_bundle(
        scenario="s4",
        caption_safe_zone_refs=["caption_safe_fixture"],
        caption_safe_zone_violations=["caption_overlap_lower_third"],
    )

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert result.blocking.failures[0].evidence_ref == "caption_overlap_lower_third"
    assert result.repair_plan.actions[0].check == "caption_safe_zone_pass"


def test_caption_safe_zone_low_score_is_not_silent():
    contract = _quality_contract(
        scenario="s4",
        advisory_checks=["caption_safe_zone_score"],
        thresholds={"caption_safe_zone_score": 0.8},
    )
    evidence = _evidence_bundle(scenario="s4")

    result = evaluate_quality_contract(contract, evidence, advisory_scores={"caption_safe_zone_score": 0.55})

    assert result.blocking.passed is True
    assert result.gate_decision.status == "review_required"
    assert result.gate_decision.advisory_warning_count == 1
    assert result.repair_plan.actions[0].severity == "advisory"
    assert result.repair_plan.actions[0].check == "caption_safe_zone_score"


def test_unknown_blocking_check_fails_closed_with_repair_action():
    contract = _quality_contract(blocking_checks=["unsupported_quality_probe"])
    evidence = _evidence_bundle()

    result = evaluate_quality_contract(contract, evidence)

    assert result.gate_decision.status == "blocked"
    assert result.repair_plan.actions[0].check == "unsupported_quality_probe"
    assert "blocking check" in result.repair_plan.actions[0].recommendation


def _quality_contract(
    *,
    scenario: str = "s2",
    blocking_checks: list[str] | None = None,
    advisory_checks: list[str] | None = None,
    required_evidence: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
) -> QualityContract:
    return QualityContract(
        contract_id=f"qc_{scenario}_fixture",
        scenario=scenario,
        stage="final_video",
        platform="tiktok",
        brand_id="momcozy",
        blocking_checks=blocking_checks or [],
        advisory_checks=advisory_checks or [],
        thresholds=thresholds or {"brand_voice_alignment": 0.72},
        required_evidence=required_evidence or [],
    )


def _evidence_bundle(
    *,
    scenario: str = "s2",
    brand_bundle_id: str | None = "bundle_fixture",
    rights_evidence_refs: list[str] | None = None,
    claim_evidence_refs: list[str] | None = None,
    source_fingerprint_refs: list[str] | None = None,
    timeline_manifest_refs: list[str] | None = None,
    edit_decision_list_refs: list[str] | None = None,
    caption_safe_zone_refs: list[str] | None = None,
    caption_safe_zone_violations: list[str] | None = None,
    children_direct_reference: bool = False,
) -> AuditEvidenceBundle:
    return AuditEvidenceBundle(
        evidence_bundle_id=f"aeb_{scenario}_fixture",
        scenario=scenario,
        stage="final_video",
        brand_bundle_id=brand_bundle_id,
        source_token_ids=["bat_fixture"],
        media_job_ids=["job_fixture"],
        prompt_hashes=["sha256:fixture"],
        artifact_manifest_id="artifact_fixture",
        artifact_paths={"final_video": "fixture://final.mp4"},
        rights_evidence_refs=rights_evidence_refs if rights_evidence_refs is not None else ["rights_fixture"],
        claim_evidence_refs=claim_evidence_refs if claim_evidence_refs is not None else ["claim_fixture"],
        source_fingerprint_refs=source_fingerprint_refs if source_fingerprint_refs is not None else ["source_fixture"],
        timeline_manifest_refs=timeline_manifest_refs
        if timeline_manifest_refs is not None
        else ["timeline_fixture"],
        edit_decision_list_refs=edit_decision_list_refs
        if edit_decision_list_refs is not None
        else ["edl_fixture"],
        caption_safe_zone_refs=caption_safe_zone_refs
        if caption_safe_zone_refs is not None
        else ["caption_safe_fixture"],
        platform_target=PlatformTarget(platform="tiktok"),
        caption_safe_zone_violations=caption_safe_zone_violations
        if caption_safe_zone_violations is not None
        else [],
        children_direct_reference=children_direct_reference,
    )
