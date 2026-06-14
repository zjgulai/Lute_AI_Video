from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline.authorized_live_poyo_submitter import AUTHORIZED_LIVE_POYO_TRANSPORT_ENV
from src.pipeline.l4d_image_only_smoke import (
    L4D_IMAGE_JOB_ID,
    L4D_IMAGE_ONLY_EXECUTE_ENV,
    PLAYWRIGHT_API_KEY_ENV,
    PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV,
    PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV,
    PLAYWRIGHT_PROD_WORKERS_ENV,
    PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV,
    POYO_API_KEY_ENV,
    RUN_TOKEN_SMOKE_ENV,
    run_l4d_image_only_smoke,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "l4d_image_only_smoke.py"
PAYLOADS_ENV = "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS"


def test_l4d_image_only_harness_is_disabled_by_default_without_provider_call() -> None:
    calls: list[str] = []

    report = run_l4d_image_only_smoke(
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"}
    )

    assert report.status == "disabled"
    assert report.provider_call_executed is False
    assert calls == []


def test_l4d_image_only_dry_run_builds_one_pending_review_image_job(tmp_path: Path) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path)

    report = run_l4d_image_only_smoke(
        mode="dry_run",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.job_spec is not None
    assert report.job_spec.job_id == L4D_IMAGE_JOB_ID
    assert report.job_spec.model == "gpt-image-2"
    assert report.job_spec.reference_asset_ids == []
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.image_count == 1
    assert report.artifact_manifest.video_count == 0
    assert report.artifact_manifest.asset_status == "pending_review"
    assert report.artifact_manifest.delivery_accepted is False
    assert report.artifact_manifest.publish_allowed is False
    assert report.artifact_manifest.approved_brand_token_write is False
    assert len(report.artifact_manifest.artifacts) == 1
    assert report.job_records[0].status == "prepared"
    assert calls == []


def test_l4d_image_only_execute_requires_dedicated_execute_gate(tmp_path: Path) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path)

    report = run_l4d_image_only_smoke(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or _provider_response(spec),
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{L4D_IMAGE_ONLY_EXECUTE_ENV}=1 is required" in report.blocked_reasons
    assert calls == []


def test_l4d_image_only_execute_submits_exactly_one_image_and_no_video(tmp_path: Path) -> None:
    calls: list[MediaJobSpec] = []
    env = _ready_env(tmp_path)
    env[L4D_IMAGE_ONLY_EXECUTE_ENV] = "1"

    def submitter(spec: MediaJobSpec) -> Mapping[str, Any]:
        calls.append(spec)
        return _provider_response(spec)

    report = run_l4d_image_only_smoke(mode="execute", env=env, submitter=submitter)

    assert report.status == "submitted"
    assert report.provider_call_executed is True
    assert report.image_job_count == 1
    assert report.video_job_count == 0
    assert [spec.job_id for spec in calls] == [L4D_IMAGE_JOB_ID]
    assert calls[0].model == "gpt-image-2"
    assert calls[0].reference_asset_ids == []
    assert report.provider_response_refs == {L4D_IMAGE_JOB_ID: "poyo_task_image_1"}
    assert report.job_records[0].status == "submitted"
    assert report.job_records[0].delivery_accepted is False
    assert report.job_records[0].publish_allowed is False
    assert report.artifact_manifest is not None
    assert report.artifact_manifest.artifacts[0].media_url == "https://cdn.example.test/l4d-image.png"


def test_l4d_image_only_blocks_legacy_full_asset_pack_execute_gate(tmp_path: Path) -> None:
    env = _ready_env(tmp_path)
    env[L4D_IMAGE_ONLY_EXECUTE_ENV] = "1"
    env["AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"] = "1"

    report = run_l4d_image_only_smoke(mode="execute", env=env, submitter=lambda spec: _provider_response(spec))

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert any("AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 must not be set" in reason for reason in report.blocked_reasons)


def test_l4d_image_only_blocks_bad_submit_count_before_provider_call(tmp_path: Path) -> None:
    calls: list[str] = []
    env = _ready_env(tmp_path)
    env[L4D_IMAGE_ONLY_EXECUTE_ENV] = "1"
    env[PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV] = "2"

    report = run_l4d_image_only_smoke(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or _provider_response(spec),
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert f"{PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV}=1 is required" in report.blocked_reasons
    assert calls == []


def test_l4d_image_only_cli_default_is_disabled_without_provider_call() -> None:
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


def test_l4d_image_only_cli_source_does_not_call_full_asset_pack_harness() -> None:
    source = SCRIPT_PATH.read_text()

    assert "run_authorized_live_harness" not in source
    assert "authorized_live_token_smoke_harness" not in source


def _ready_env(tmp_path: Path) -> dict[str, str]:
    payloads_path = tmp_path / "l4d-poyo-payloads.json"
    payloads_path.write_text(
        json.dumps(
            {
                "payloads": [
                    {
                        "job_id": L4D_IMAGE_JOB_ID,
                        "model": "gpt-image-2",
                        "input_payload": {"prompt": "private image prompt", "size": "1:1", "quality": "low"},
                        "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
                    }
                ]
            }
        )
    )
    return {
        RUN_TOKEN_SMOKE_ENV: "1",
        PLAYWRIGHT_PROD_WORKERS_ENV: "1",
        PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV: "1",
        PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV: "0",
        PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV: "pending_review",
        PLAYWRIGHT_API_KEY_ENV: "prod_key_fixture",
        POYO_API_KEY_ENV: "poyo_key_fixture",
        AUTHORIZED_LIVE_POYO_TRANSPORT_ENV: "1",
        PAYLOADS_ENV: str(payloads_path),
    }


def _provider_response(spec: MediaJobSpec) -> dict[str, str]:
    return {
        "provider_job_id": "poyo_task_image_1",
        "job_id": spec.job_id,
        "provider": spec.provider,
        "model": spec.model,
        "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
        "media_url": "https://cdn.example.test/l4d-image.png",
        "thumbnail_ref": "https://cdn.example.test/l4d-image-thumb.png",
    }
