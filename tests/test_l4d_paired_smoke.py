from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline.authorized_live_poyo_submitter import AUTHORIZED_LIVE_POYO_TRANSPORT_ENV
from src.pipeline.l4d_paired_smoke import (
    L4D_PAIRED_EXECUTE_ENV,
    L4D_PAIRED_IMAGE_ARTIFACT_REF,
    L4D_PAIRED_IMAGE_JOB_ID,
    L4D_PAIRED_VIDEO_JOB_ID,
    PLAYWRIGHT_API_KEY_ENV,
    PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV,
    PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV,
    PLAYWRIGHT_PROD_WORKERS_ENV,
    PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV,
    POYO_API_KEY_ENV,
    RUN_TOKEN_SMOKE_ENV,
    L4DPairedPoyoSubmitter,
    build_l4d_paired_video_provider_payload,
    run_l4d_paired_smoke,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "l4d_paired_smoke.py"


def test_l4d_paired_harness_is_disabled_by_default_without_provider_call() -> None:
    submitter = _FakePairedSubmitter()

    report = run_l4d_paired_smoke(submitter=submitter)

    assert report.status == "disabled"
    assert report.provider_call_executed is False
    assert submitter.calls == []


def test_l4d_paired_dry_run_builds_one_image_and_one_video_job() -> None:
    submitter = _FakePairedSubmitter()

    report = run_l4d_paired_smoke(mode="dry_run", env=_ready_env(), submitter=submitter)

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert [spec.job_id for spec in report.job_specs] == [L4D_PAIRED_IMAGE_JOB_ID, L4D_PAIRED_VIDEO_JOB_ID]
    assert report.job_specs[0].model == "gpt-image-2"
    assert report.job_specs[0].reference_asset_ids == []
    assert report.job_specs[1].model == "seedance-2"
    assert report.job_specs[1].reference_asset_ids == [L4D_PAIRED_IMAGE_ARTIFACT_REF]
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.image_count == 1
    assert report.artifact_manifest.video_count == 1
    assert report.artifact_manifest.asset_status == "pending_review"
    assert report.artifact_manifest.delivery_accepted is False
    assert report.artifact_manifest.publish_allowed is False
    assert report.artifact_manifest.approved_brand_token_write is False
    assert submitter.calls == []


def test_l4d_paired_execute_requires_dedicated_execute_gate() -> None:
    submitter = _FakePairedSubmitter()

    report = run_l4d_paired_smoke(mode="execute", env=_ready_env(), submitter=submitter)

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{L4D_PAIRED_EXECUTE_ENV}=1 is required" in report.blocked_reasons
    assert submitter.calls == []


def test_l4d_paired_execute_submits_exactly_one_image_then_one_video() -> None:
    submitter = _FakePairedSubmitter()
    env = _ready_env()
    env[L4D_PAIRED_EXECUTE_ENV] = "1"

    report = run_l4d_paired_smoke(mode="execute", env=env, submitter=submitter)

    assert report.status == "submitted"
    assert report.provider_call_executed is True
    assert report.image_job_count == 1
    assert report.video_job_count == 1
    assert submitter.calls == [(L4D_PAIRED_IMAGE_JOB_ID, L4D_PAIRED_VIDEO_JOB_ID)]
    assert report.provider_response_refs == {
        L4D_PAIRED_IMAGE_JOB_ID: "poyo_task_image_1",
        L4D_PAIRED_VIDEO_JOB_ID: "poyo_task_video_1",
    }
    assert report.provider_media_urls == {
        L4D_PAIRED_IMAGE_JOB_ID: "https://cdn.example.test/l4d-paired-image.png",
        L4D_PAIRED_VIDEO_JOB_ID: "https://cdn.example.test/l4d-paired-video.mp4",
    }
    assert report.generated_image_sha256 == "sha256-generated-image"
    assert [record.status for record in report.job_records] == ["submitted", "submitted"]
    assert all(record.delivery_accepted is False for record in report.job_records)
    assert all(record.publish_allowed is False for record in report.job_records)


def test_l4d_paired_blocks_legacy_and_single_mode_execute_gates() -> None:
    env = _ready_env()
    env[L4D_PAIRED_EXECUTE_ENV] = "1"
    env["AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"] = "1"
    env["AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE"] = "1"
    env["AI_VIDEO_L4D_VIDEO_ONLY_EXECUTE"] = "1"

    report = run_l4d_paired_smoke(mode="execute", env=env, submitter=_FakePairedSubmitter())

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert any("AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 must not be set" in r for r in report.blocked_reasons)
    assert any("AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE=1 must not be set" in r for r in report.blocked_reasons)
    assert any("AI_VIDEO_L4D_VIDEO_ONLY_EXECUTE=1 must not be set" in r for r in report.blocked_reasons)


def test_l4d_paired_blocks_bad_submit_count_before_provider_call() -> None:
    submitter = _FakePairedSubmitter()
    env = _ready_env()
    env[L4D_PAIRED_EXECUTE_ENV] = "1"
    env[PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV] = "2"

    report = run_l4d_paired_smoke(mode="execute", env=env, submitter=submitter)

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV}=1 is required" in report.blocked_reasons
    assert submitter.calls == []


def test_l4d_paired_runtime_submitter_uses_generated_image_bytes_for_video() -> None:
    transport = _FakeTransport()
    submitter = L4DPairedPoyoSubmitter(
        transport=transport,
        generated_image_downloader=lambda media_url: b"generated image bytes from " + media_url.encode(),
    )
    env = _ready_env()
    env[L4D_PAIRED_EXECUTE_ENV] = "1"

    report = run_l4d_paired_smoke(mode="execute", env=env, submitter=submitter)

    assert report.status == "submitted"
    assert [call["model"] for call in transport.calls] == ["gpt-image-2", "seedance-2"]
    assert transport.calls[0]["input_payload"]["prompt"]
    assert transport.calls[1]["input_payload"]["image_urls"][0].startswith("data:image/png;base64,")
    assert "reference_image_urls" not in transport.calls[1]["input_payload"]
    assert transport.calls[1]["input_payload"]["generate_audio"] is False
    assert submitter.image_job_count == 1
    assert submitter.video_job_count == 1


def test_l4d_paired_video_payload_requires_generated_image_bytes() -> None:
    payload = build_l4d_paired_video_provider_payload(b"generated-image")

    assert payload["image_urls"][0].startswith("data:image/png;base64,")
    assert payload["duration"] == 15
    assert payload["resolution"] == "480p"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["generate_audio"] is False


def test_l4d_paired_cli_default_is_disabled_without_provider_call() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--pretty"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "disabled"
    assert payload["provider_call_executed"] is False


def test_l4d_paired_cli_source_does_not_call_single_mode_or_full_asset_pack_harness() -> None:
    source = SCRIPT_PATH.read_text()

    assert "run_authorized_live_harness" not in source
    assert "authorized_live_token_smoke_harness" not in source
    assert "run_l4d_image_only_smoke" not in source
    assert "run_l4d_video_only_smoke" not in source


class _FakePairedSubmitter:
    def __init__(self) -> None:
        self.image_job_count = 0
        self.video_job_count = 0
        self.calls: list[tuple[str, str]] = []

    def __call__(self, image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> Mapping[str, Any]:
        self.calls.append((image_spec.job_id, video_spec.job_id))
        self.image_job_count += 1
        self.video_job_count += 1
        return {
            "image_provider_job_id": "poyo_task_image_1",
            "video_provider_job_id": "poyo_task_video_1",
            "image_media_url": "https://cdn.example.test/l4d-paired-image.png",
            "video_media_url": "https://cdn.example.test/l4d-paired-video.mp4",
            "image_thumbnail_ref": "https://cdn.example.test/l4d-paired-image-thumb.png",
            "video_thumbnail_ref": "https://cdn.example.test/l4d-paired-video-thumb.jpg",
            "generated_image_sha256": "sha256-generated-image",
        }


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def submit_once(self, *, model: str, input_payload: Mapping[str, Any]) -> Mapping[str, str]:
        self.calls.append({"model": model, "input_payload": dict(input_payload)})
        if model == "gpt-image-2":
            return {
                "provider_job_id": "poyo_task_image_1",
                "file_url": "https://cdn.example.test/generated-image.png",
                "thumbnail_url": "https://cdn.example.test/generated-image-thumb.png",
            }
        return {
            "provider_job_id": "poyo_task_video_1",
            "file_url": "https://cdn.example.test/generated-video.mp4",
            "thumbnail_url": "https://cdn.example.test/generated-video-thumb.jpg",
        }


def _ready_env() -> dict[str, str]:
    return {
        RUN_TOKEN_SMOKE_ENV: "1",
        PLAYWRIGHT_PROD_WORKERS_ENV: "1",
        PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV: "1",
        PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV: "0",
        PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV: "pending_review",
        PLAYWRIGHT_API_KEY_ENV: "prod_key_fixture",
        POYO_API_KEY_ENV: "poyo_key_fixture",
        AUTHORIZED_LIVE_POYO_TRANSPORT_ENV: "1",
    }
