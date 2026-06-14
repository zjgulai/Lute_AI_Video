from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline import l4d_video_only_smoke as video_smoke
from src.pipeline.authorized_live_poyo_submitter import AUTHORIZED_LIVE_POYO_TRANSPORT_ENV
from src.pipeline.l4d_video_only_smoke import (
    L4D_INPUT_IMAGE_TENANT_REF,
    L4D_VIDEO_INPUT_IMAGE_PATH_ENV,
    L4D_VIDEO_JOB_ID,
    L4D_VIDEO_ONLY_EXECUTE_ENV,
    L4D_VIDEO_PROVIDER_PROMPT,
    PLAYWRIGHT_API_KEY_ENV,
    PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV,
    PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV,
    PLAYWRIGHT_PROD_WORKERS_ENV,
    PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV,
    POYO_API_KEY_ENV,
    RUN_TOKEN_SMOKE_ENV,
    build_l4d_video_provider_payload,
    run_l4d_video_only_smoke,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "l4d_video_only_smoke.py"


def test_l4d_video_only_harness_is_disabled_by_default_without_provider_call() -> None:
    calls: list[str] = []

    report = run_l4d_video_only_smoke(
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"}
    )

    assert report.status == "disabled"
    assert report.provider_call_executed is False
    assert calls == []


def test_l4d_video_only_dry_run_builds_one_pending_review_video_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path, monkeypatch)

    report = run_l4d_video_only_smoke(
        mode="dry_run",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.job_spec is not None
    assert report.job_spec.job_id == L4D_VIDEO_JOB_ID
    assert report.job_spec.model == "seedance-2"
    assert report.job_spec.reference_asset_ids == [L4D_INPUT_IMAGE_TENANT_REF]
    assert report.job_spec.cost_ceiling_usd == 2.0
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.image_generation_count == 0
    assert report.artifact_manifest.image_count == 0
    assert report.artifact_manifest.video_count == 1
    assert report.artifact_manifest.asset_status == "pending_review"
    assert report.artifact_manifest.delivery_accepted is False
    assert report.artifact_manifest.publish_allowed is False
    assert report.artifact_manifest.approved_brand_token_write is False
    assert len(report.artifact_manifest.artifacts) == 1
    assert report.artifact_manifest.artifacts[0].input_image_ref == L4D_INPUT_IMAGE_TENANT_REF
    assert report.job_records[0].status == "prepared"
    assert calls == []


def test_l4d_video_only_execute_requires_dedicated_execute_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path, monkeypatch)

    report = run_l4d_video_only_smoke(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or _provider_response(spec),
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{L4D_VIDEO_ONLY_EXECUTE_ENV}=1 is required" in report.blocked_reasons
    assert calls == []


def test_l4d_video_only_execute_submits_exactly_one_video_and_no_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[MediaJobSpec] = []
    env = _ready_env(tmp_path, monkeypatch)
    env[L4D_VIDEO_ONLY_EXECUTE_ENV] = "1"

    def submitter(spec: MediaJobSpec) -> Mapping[str, Any]:
        calls.append(spec)
        return _provider_response(spec)

    report = run_l4d_video_only_smoke(mode="execute", env=env, submitter=submitter)

    assert report.status == "submitted"
    assert report.provider_call_executed is True
    assert report.image_job_count == 0
    assert report.video_job_count == 1
    assert [spec.job_id for spec in calls] == [L4D_VIDEO_JOB_ID]
    assert calls[0].model == "seedance-2"
    assert calls[0].reference_asset_ids == [L4D_INPUT_IMAGE_TENANT_REF]
    assert report.provider_response_refs == {L4D_VIDEO_JOB_ID: "poyo_task_video_1"}
    assert report.provider_media_urls == {L4D_VIDEO_JOB_ID: "https://cdn.example.test/l4d-video.mp4"}
    assert report.job_records[0].status == "submitted"
    assert report.job_records[0].delivery_accepted is False
    assert report.job_records[0].publish_allowed is False
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.artifacts[0].media_url == "https://cdn.example.test/l4d-video.mp4"


def test_l4d_video_only_blocks_legacy_full_asset_pack_execute_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _ready_env(tmp_path, monkeypatch)
    env[L4D_VIDEO_ONLY_EXECUTE_ENV] = "1"
    env["AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"] = "1"

    report = run_l4d_video_only_smoke(mode="execute", env=env, submitter=lambda spec: _provider_response(spec))

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert any("AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 must not be set" in reason for reason in report.blocked_reasons)


def test_l4d_video_only_blocks_image_only_execute_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _ready_env(tmp_path, monkeypatch)
    env[L4D_VIDEO_ONLY_EXECUTE_ENV] = "1"
    env["AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE"] = "1"

    report = run_l4d_video_only_smoke(mode="execute", env=env, submitter=lambda spec: _provider_response(spec))

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert any("AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE=1 must not be set" in reason for reason in report.blocked_reasons)


def test_l4d_video_only_blocks_bad_submit_count_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path, monkeypatch)
    env[L4D_VIDEO_ONLY_EXECUTE_ENV] = "1"
    env[PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV] = "2"

    report = run_l4d_video_only_smoke(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or _provider_response(spec),
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV}=1 is required" in report.blocked_reasons
    assert calls == []


def test_l4d_video_only_blocks_wrong_input_image_hash_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_image = tmp_path / "main_45.png"
    input_image.write_bytes(b"wrong image")
    expected_sha256 = _sha256_bytes(b"expected image")
    monkeypatch.setattr(video_smoke, "L4D_EXPECTED_INPUT_IMAGE_SHA256", expected_sha256)
    env = _ready_env(tmp_path, monkeypatch, input_image=input_image)
    env[L4D_VIDEO_ONLY_EXECUTE_ENV] = "1"

    report = run_l4d_video_only_smoke(mode="execute", env=env, submitter=lambda spec: _provider_response(spec))

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert "L4D-2 input image sha256 mismatch" in report.blocked_reasons


def test_l4d_video_provider_payload_uses_existing_image_data_uri_without_reporting_secret_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_image = _write_fixture_image(tmp_path, monkeypatch)

    payload = build_l4d_video_provider_payload(input_image)

    assert payload["prompt"] == L4D_VIDEO_PROVIDER_PROMPT
    assert payload["image_urls"][0].startswith("data:image/png;base64,")
    assert payload["duration"] == 15
    assert payload["resolution"] == "480p"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["generate_audio"] is False


def test_l4d_video_only_cli_default_is_disabled_without_provider_call() -> None:
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


def test_l4d_video_only_cli_source_does_not_call_image_or_full_asset_pack_harness() -> None:
    source = SCRIPT_PATH.read_text()

    assert "run_authorized_live_harness" not in source
    assert "authorized_live_token_smoke_harness" not in source
    assert "run_l4d_image_only_smoke" not in source


def _ready_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    input_image: Path | None = None,
) -> dict[str, str]:
    input_image = input_image or _write_fixture_image(tmp_path, monkeypatch)
    return {
        RUN_TOKEN_SMOKE_ENV: "1",
        PLAYWRIGHT_PROD_WORKERS_ENV: "1",
        PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV: "1",
        PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV: "0",
        PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV: "pending_review",
        PLAYWRIGHT_API_KEY_ENV: "prod_key_fixture",
        POYO_API_KEY_ENV: "poyo_key_fixture",
        AUTHORIZED_LIVE_POYO_TRANSPORT_ENV: "1",
        L4D_VIDEO_INPUT_IMAGE_PATH_ENV: str(input_image),
    }


def _write_fixture_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    input_image = tmp_path / "main_45.png"
    payload = b"fixture existing pending review image"
    input_image.write_bytes(payload)
    monkeypatch.setattr(video_smoke, "L4D_EXPECTED_INPUT_IMAGE_SHA256", _sha256_bytes(payload))
    return input_image


def _sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _provider_response(spec: MediaJobSpec) -> dict[str, str]:
    return {
        "provider_job_id": "poyo_task_video_1",
        "job_id": spec.job_id,
        "provider": spec.provider,
        "model": spec.model,
        "artifact_ref": "artifact://l4d-video-only/momcozy-sterilizer-i2v-seedance-2",
        "media_url": "https://cdn.example.test/l4d-video.mp4",
        "thumbnail_ref": "https://cdn.example.test/l4d-video-thumb.jpg",
    }
