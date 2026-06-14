from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.pending_review_asset_packet import build_pending_review_asset_packet

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_pending_review_asset_packet.py"


def test_packet_preserves_pending_review_boundary_without_prompt_payload(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    summary = _summary(pending_dir)

    packet = build_pending_review_asset_packet(
        summary,
        source_summary_ref="tmp/outputs/authorized-live-poyo-smoke-rerun-20260607-summary.json",
        repo_root=REPO_ROOT,
    )
    payload = packet.model_dump(mode="json")
    payload_text = json.dumps(payload)

    assert payload["evidence_level"] == "L4-authorized-live"
    assert payload["packet_build_no_provider_call"] is True
    assert payload["provider_call_executed"] is True
    assert payload["asset_status"] == "pending_review"
    assert payload["delivery_accepted"] is False
    assert payload["publish_allowed"] is False
    assert payload["approved_brand_token_write"] is False
    assert payload["approved_for_runtime_injection"] is False
    assert payload["commercial_delivery_complete"] is False
    assert len(payload["assets"]) == 4
    assert {asset["review_status"] for asset in payload["assets"]} == {"pending_review"}
    assert {asset["provider_ref"] for asset in payload["assets"]} == {
        "RVEVGSYDJD19SAN3",
        "HAGP37JYEC2VH8SI",
        "P3LDHS0SZL1IGQIE",
        "P4FK7ES9NEAXM4TP",
    }
    assert payload["video_reference_asset_refs"] == [
        "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
        "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
        "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
    ]
    assert "not delivery accepted" in payload["forbidden_claims"]
    assert "not written to approved brand token" in payload["forbidden_claims"]
    assert "prompt_payload" not in payload_text
    assert "api_key" not in payload_text.lower()


def test_uv_benefit_asset_is_marked_for_regeneration_or_edit(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    packet = build_pending_review_asset_packet(_summary(pending_dir), repo_root=REPO_ROOT)

    uv_asset = _asset_by_sample(packet.model_dump(mode="json"), "momcozy-sterilizer-uv-benefit-gpt-image-2")

    assert uv_asset["review_recommendation"] == "regenerate_or_edit_before_brand_use"
    assert {finding["code"] for finding in uv_asset["findings"]} == {
        "generated_text_risk",
        "non_real_product_name_risk",
        "claim_copy_review_required",
    }
    assert "approved_brand_token" in uv_asset["forbidden_next_states"]


def test_non_uv_assets_still_require_manual_review(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    packet = build_pending_review_asset_packet(_summary(pending_dir), repo_root=REPO_ROOT)
    payload = packet.model_dump(mode="json")

    for sample_id in (
        "momcozy-sterilizer-main-45-gpt-image-2",
        "momcozy-sterilizer-kitchen-scene-gpt-image-2",
        "momcozy-sterilizer-i2v-15s-seedance-2",
    ):
        asset = _asset_by_sample(payload, sample_id)
        assert asset["review_recommendation"] == "manual_review_required"
        assert asset["findings"]


def test_packet_fails_closed_if_source_summary_promotes_assets(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    summary = _summary(pending_dir)
    summary["artifact_manifest"]["approved_brand_token_write"] = True

    with pytest.raises(ValueError, match="approved_brand_token_write=false"):
        build_pending_review_asset_packet(summary, repo_root=REPO_ROOT)


def test_packet_rejects_prompt_or_secret_payload_keys(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    summary = _summary(pending_dir)
    summary["artifact_manifest"]["artifacts"][0]["prompt"] = "raw prompt body must not enter review packet"

    with pytest.raises(ValueError, match="disallowed payload key"):
        build_pending_review_asset_packet(summary, repo_root=REPO_ROOT)

    summary = _summary(pending_dir)
    summary["api_key"] = "sk_live_secret"

    with pytest.raises(ValueError, match="disallowed payload key"):
        build_pending_review_asset_packet(summary, repo_root=REPO_ROOT)


def test_cli_writes_private_packet_and_blocks_formal_repo_output(tmp_path: Path):
    pending_dir = _write_pending_media(tmp_path)
    summary_path = tmp_path / "summary.json"
    output_path = tmp_path / "pending-review-packet.json"
    summary_path.write_text(json.dumps(_summary(pending_dir)))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(summary_path),
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
    assert output_path.exists()
    payload = json.loads(output_path.read_text())
    assert payload["asset_status"] == "pending_review"
    assert payload["assets"][0]["provider_ref"] == "RVEVGSYDJD19SAN3"

    blocked_path = REPO_ROOT / "configs" / "should-not-write-pending-review-packet.json"
    blocked = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(summary_path), "--output", str(blocked_path)],
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
    assert "build_pending_review_asset_packet" in source


def _write_pending_media(tmp_path: Path) -> Path:
    pending_dir = tmp_path / "pending_review" / "momcozy_sterilizer_smoke_20260607"
    pending_dir.mkdir(parents=True)
    for filename in ("main_45.png", "uv_benefit.png", "kitchen_scene.png", "i2v_15s.mp4"):
        (pending_dir / filename).write_bytes(b"fixture-media")
    return pending_dir


def _asset_by_sample(payload: dict[str, Any], sample_id: str) -> dict[str, Any]:
    for asset in payload["assets"]:
        if asset["sample_id"] == sample_id:
            return asset
    raise AssertionError(f"missing asset {sample_id}")


def _summary(pending_dir: Path) -> dict[str, Any]:
    return {
        "evidence_level": "L4-authorized-live",
        "claim_boundary": (
            "authorized live smoke succeeded; assets remain pending_review and are not "
            "delivery_accepted, publish_allowed, or approved brand token"
        ),
        "report_ref": "tmp/outputs/authorized-live-poyo-smoke-rerun-20260607.log",
        "harness_id": "authorized_live_harness_20260606163347",
        "status": "submitted",
        "provider_call_executed": True,
        "blocked_reasons": [],
        "provider_response_refs": {
            "momcozy_sterilizer_main_45_image_authorized_live_fixture": "RVEVGSYDJD19SAN3",
            "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture": "HAGP37JYEC2VH8SI",
            "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture": "P3LDHS0SZL1IGQIE",
            "momcozy_sterilizer_i2v_15s_authorized_live_fixture": "P4FK7ES9NEAXM4TP",
        },
        "artifact_manifest": {
            "manifest_id": "momcozy_sterilizer_asset_pack_pending_review",
            "brand": "momcozy",
            "product": "sterilizer",
            "asset_status": "pending_review",
            "image_count": 3,
            "video_count": 1,
            "delivery_accepted": False,
            "publish_allowed": False,
            "approved_brand_token_write": False,
            "artifacts": [
                {
                    "sample_id": "momcozy-sterilizer-main-45-gpt-image-2",
                    "job_id": "momcozy_sterilizer_main_45_image_authorized_live_fixture",
                    "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
                    "asset_type": "image",
                    "tool_id": "product-image",
                    "provider": "poyo",
                    "model": "gpt-image-2",
                    "review_status": "pending_review",
                    "media_url": "https://cdn.example.test/main_45.png",
                    "thumbnail_ref": None,
                },
                {
                    "sample_id": "momcozy-sterilizer-uv-benefit-gpt-image-2",
                    "job_id": "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture",
                    "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
                    "asset_type": "image",
                    "tool_id": "ecommerce-visual",
                    "provider": "poyo",
                    "model": "gpt-image-2",
                    "review_status": "pending_review",
                    "media_url": "https://cdn.example.test/uv_benefit.png",
                    "thumbnail_ref": None,
                },
                {
                    "sample_id": "momcozy-sterilizer-kitchen-scene-gpt-image-2",
                    "job_id": "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture",
                    "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
                    "asset_type": "image",
                    "tool_id": "ecommerce-visual",
                    "provider": "poyo",
                    "model": "gpt-image-2",
                    "review_status": "pending_review",
                    "media_url": "https://cdn.example.test/kitchen_scene.png",
                    "thumbnail_ref": None,
                },
                {
                    "sample_id": "momcozy-sterilizer-i2v-15s-seedance-2",
                    "job_id": "momcozy_sterilizer_i2v_15s_authorized_live_fixture",
                    "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-i2v-15s-seedance-2",
                    "asset_type": "video",
                    "tool_id": "storyboard",
                    "provider": "poyo",
                    "model": "seedance-2",
                    "review_status": "pending_review",
                    "media_url": "https://cdn.example.test/i2v_15s.mp4",
                    "thumbnail_ref": None,
                },
            ],
            "video_reference_asset_refs": [
                "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
                "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
                "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
            ],
            "evidence_refs": [
                "configs/authorized-live-token-smoke-sample-plan-contract.json",
                "configs/poyo-current-provider-revalidation-contract.json",
            ],
        },
        "local_pending_review_dir": str(pending_dir),
        "media_validation": {
            "main_45": {"path": str(pending_dir / "main_45.png"), "dimensions": [1254, 1254]},
            "uv_benefit": {"path": str(pending_dir / "uv_benefit.png"), "dimensions": [1122, 1402]},
            "kitchen_scene": {"path": str(pending_dir / "kitchen_scene.png"), "dimensions": [1122, 1402]},
            "i2v_15s": {
                "path": str(pending_dir / "i2v_15s.mp4"),
                "duration_seconds": 15.009002,
                "video_stream": {"width": 496, "height": 864, "codec": "h264"},
                "audio_stream": {"codec": "aac", "duration_seconds": 15.009002},
            },
        },
        "forbidden_claims": [
            "not delivery accepted",
            "not published",
            "not written to approved brand token",
            "not full commercial launch delivery",
        ],
    }
