from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.pending_review_asset_packet import PendingReviewAssetPacket
from src.pipeline.pending_review_decision_record import (
    build_pending_review_decision_record,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pending_review_decision_record.py"


def test_decision_record_keeps_candidates_without_promoting_brand_token():
    record = build_pending_review_decision_record(
        _packet(),
        [
            _decision("momcozy-sterilizer-main-45-gpt-image-2", "keep_as_candidate"),
            _decision("momcozy-sterilizer-uv-benefit-gpt-image-2", "request_regeneration"),
            _decision("momcozy-sterilizer-kitchen-scene-gpt-image-2", "keep_as_candidate"),
            _decision("momcozy-sterilizer-i2v-15s-seedance-2", "reject"),
        ],
        source_packet_ref="tmp/outputs/momcozy-sterilizer-pending-review-packet-20260607.json",
    )
    payload = record.model_dump(mode="json")

    assert payload["source_evidence_level"] == "L4-authorized-live"
    assert payload["record_build_no_provider_call"] is True
    assert payload["candidate_asset_count"] == 2
    assert {asset["sample_id"] for asset in payload["candidate_assets"]} == {
        "momcozy-sterilizer-main-45-gpt-image-2",
        "momcozy-sterilizer-kitchen-scene-gpt-image-2",
    }
    assert payload["regeneration_requested_ids"] == ["momcozy-sterilizer-uv-benefit-gpt-image-2"]
    assert payload["rejected_asset_ids"] == ["momcozy-sterilizer-i2v-15s-seedance-2"]
    assert payload["skipped_asset_ids"] == []
    assert payload["delivery_accepted"] is False
    assert payload["publish_allowed"] is False
    assert payload["approved_brand_token_write"] is False
    assert payload["approved_for_runtime_injection"] is False
    assert payload["commercial_delivery_complete"] is False
    assert payload["requires_separate_brand_token_intake"] is True
    assert "not written to approved brand token" in payload["forbidden_claims"]
    assert "not a final brand asset approval" in payload["forbidden_claims"]


def test_partial_decisions_leave_unreviewed_assets_skipped():
    record = build_pending_review_decision_record(
        _packet(),
        [_decision("momcozy-sterilizer-main-45-gpt-image-2", "keep_as_candidate")],
    )

    assert record.candidate_asset_count == 1
    assert record.skipped_asset_ids == [
        "momcozy-sterilizer-uv-benefit-gpt-image-2",
        "momcozy-sterilizer-kitchen-scene-gpt-image-2",
        "momcozy-sterilizer-i2v-15s-seedance-2",
    ]


def test_uv_benefit_cannot_be_kept_with_unresolved_blockers():
    with pytest.raises(ValueError, match="unresolved blocker findings"):
        build_pending_review_decision_record(
            _packet(),
            [_decision("momcozy-sterilizer-uv-benefit-gpt-image-2", "keep_as_candidate")],
        )


def test_uv_benefit_can_be_candidate_only_after_resolution_ref_and_blocker_codes():
    record = build_pending_review_decision_record(
        _packet(),
        [
            _decision(
                "momcozy-sterilizer-uv-benefit-gpt-image-2",
                "keep_as_candidate",
                resolved_finding_codes=["generated_text_risk", "non_real_product_name_risk"],
                resolution_ref="review://momcozy/sterilizer/uv-benefit-copy-cleaned",
            )
        ],
    )

    assert record.candidate_asset_count == 1
    assert record.candidate_assets[0].sample_id == "momcozy-sterilizer-uv-benefit-gpt-image-2"
    assert record.candidate_assets[0].rights_status == "not_approved_brand_token"


def test_keep_asset_with_blockers_requires_resolution_ref():
    with pytest.raises(ValueError, match="requires resolution_ref"):
        build_pending_review_decision_record(
            _packet(),
            [
                _decision(
                    "momcozy-sterilizer-uv-benefit-gpt-image-2",
                    "keep_as_candidate",
                    resolved_finding_codes=["generated_text_risk", "non_real_product_name_risk"],
                )
            ],
        )


def test_duplicate_or_unknown_decisions_fail_closed():
    with pytest.raises(ValueError, match="duplicate decision"):
        build_pending_review_decision_record(
            _packet(),
            [
                _decision("momcozy-sterilizer-main-45-gpt-image-2", "reject"),
                _decision("momcozy-sterilizer-main-45-gpt-image-2", "request_regeneration"),
            ],
        )

    with pytest.raises(ValueError, match="unknown pending-review assets"):
        build_pending_review_decision_record(
            _packet(),
            [_decision("unknown-sample", "reject")],
        )


def test_empty_or_generic_decision_input_is_not_enough():
    with pytest.raises(ValueError, match="at least one explicit asset decision"):
        build_pending_review_decision_record(_packet(), [])

    with pytest.raises(ValueError, match="requires review_notes"):
        build_pending_review_decision_record(
            _packet(),
            [
                {
                    "sample_id": "momcozy-sterilizer-main-45-gpt-image-2",
                    "decision": "keep_as_candidate",
                    "reviewed_by": "operator",
                    "reviewed_at": "2026-06-07T00:00:00Z",
                    "review_notes": "",
                }
            ],
        )


def test_cli_writes_private_decision_record_and_blocks_formal_repo_output(tmp_path: Path):
    packet_path = tmp_path / "packet.json"
    decisions_path = tmp_path / "decisions.json"
    output_path = tmp_path / "decision-record.json"
    packet_path.write_text(json.dumps(_packet().model_dump(mode="json")))
    decisions_path.write_text(
        json.dumps({
            "decisions": [
                _decision("momcozy-sterilizer-main-45-gpt-image-2", "keep_as_candidate"),
                _decision("momcozy-sterilizer-uv-benefit-gpt-image-2", "request_regeneration"),
            ]
        })
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--output",
            str(output_path),
            "--pretty",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text())
    assert payload["candidate_asset_count"] == 1
    assert payload["regeneration_requested_ids"] == ["momcozy-sterilizer-uv-benefit-gpt-image-2"]

    blocked_path = REPO_ROOT / "configs" / "should-not-write-pending-review-decision-record.json"
    blocked = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--output",
            str(blocked_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert blocked.returncode == 2
    assert "under tmp/ or outside the repository" in blocked.stderr
    assert not blocked_path.exists()


def test_cli_source_has_no_provider_execution_path():
    source = SCRIPT_PATH.read_text()

    assert "subprocess.run" not in source
    assert "urlopen" not in source
    assert "requests." not in source
    assert "PoyoClient" not in source
    assert "build_pending_review_decision_record" in source


def _decision(
    sample_id: str,
    decision: str,
    *,
    resolved_finding_codes: list[str] | None = None,
    resolution_ref: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sample_id": sample_id,
        "decision": decision,
        "reviewed_by": "brand_reviewer",
        "reviewed_at": "2026-06-07T00:00:00Z",
        "review_notes": f"{sample_id} reviewed for controlled smoke follow-up.",
    }
    if resolved_finding_codes is not None:
        payload["resolved_finding_codes"] = resolved_finding_codes
    if resolution_ref is not None:
        payload["resolution_ref"] = resolution_ref
    return payload


def _packet() -> PendingReviewAssetPacket:
    return PendingReviewAssetPacket.model_validate({
        "packet_id": "pending_review_packet_momcozy_sterilizer_asset_pack_pending_review_fixture",
        "evidence_level": "L4-authorized-live",
        "source_summary_ref": "tmp/outputs/authorized-live-poyo-smoke-rerun-20260607-summary.json",
        "claim_boundary": (
            "authorized live smoke succeeded; assets remain pending_review and are not "
            "delivery_accepted, publish_allowed, or approved brand token"
        ),
        "packet_build_no_provider_call": True,
        "provider_call_executed": True,
        "asset_status": "pending_review",
        "delivery_accepted": False,
        "publish_allowed": False,
        "approved_brand_token_write": False,
        "approved_for_runtime_injection": False,
        "commercial_delivery_complete": False,
        "brand": "momcozy",
        "product": "sterilizer",
        "assets": [
            _asset("momcozy-sterilizer-main-45-gpt-image-2", "image", "product-image", ["product_identity_review_required"]),
            _asset(
                "momcozy-sterilizer-uv-benefit-gpt-image-2",
                "image",
                "ecommerce-visual",
                ["generated_text_risk", "non_real_product_name_risk", "claim_copy_review_required"],
                blocker_codes=["generated_text_risk", "non_real_product_name_risk"],
            ),
            _asset("momcozy-sterilizer-kitchen-scene-gpt-image-2", "image", "ecommerce-visual", ["lifestyle_realism_review_required"]),
            _asset("momcozy-sterilizer-i2v-15s-seedance-2", "video", "storyboard", ["temporal_consistency_review_required"]),
        ],
        "video_reference_asset_refs": [
            "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
            "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
            "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
        ],
        "supported_claims": [
            "authorized-live smoke produced pending-review media artifacts",
            "assets are available for human review and comparison against brand standards",
        ],
        "forbidden_claims": [
            "not delivery accepted",
            "not published",
            "not written to approved brand token",
            "not full commercial launch delivery",
        ],
        "next_actions": ["complete manual brand review for all four pending assets"],
    })


def _asset(
    sample_id: str,
    media_type: str,
    tool_id: str,
    finding_codes: list[str],
    *,
    blocker_codes: list[str] | None = None,
) -> dict[str, Any]:
    blocker_codes = blocker_codes or []
    model = "seedance-2" if media_type == "video" else "gpt-image-2"
    return {
        "sample_id": sample_id,
        "job_id": f"{sample_id.replace('-', '_')}_job",
        "artifact_ref": f"artifact://authorized-live/{sample_id}",
        "provider_ref": f"provider-ref-{sample_id}",
        "media_type": media_type,
        "tool_id": tool_id,
        "provider": "poyo",
        "model": model,
        "review_status": "pending_review",
        "media_url": f"https://cdn.example.test/{sample_id}",
        "local_path": f"output/pending_review/momcozy_sterilizer_smoke_20260607/{sample_id}",
        "technical_metadata": {},
        "review_recommendation": "regenerate_or_edit_before_brand_use"
        if blocker_codes
        else "manual_review_required",
        "findings": [
            {
                "code": code,
                "severity": "blocker" if code in blocker_codes else "warning",
                "detail": f"{code} detail",
            }
            for code in finding_codes
        ],
        "allowed_next_states": [
            "rejected",
            "regenerate_requested",
            "candidate_brand_asset_after_human_review",
        ],
        "forbidden_next_states": [
            "delivery_accepted",
            "published",
            "approved_brand_token",
            "approved_runtime_injection_bundle",
        ],
    }
