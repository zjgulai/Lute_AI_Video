from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.pipeline.w5_acceptance_harness import build_w5_plan_draft
from src.pipeline.w5_fast_activation import (
    W5_FAST_AUTHORIZATION_STATEMENT,
    W5FastActivationRecordV1,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_w5_fast_runtime_binding.py"


def test_cli_builds_hash_only_private_binding_without_execution(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    plan = build_w5_plan_draft(
        scenario="fast",
        tenant_id="tenant-alpha",
        sample_ref="sample:fast:001",
        budget_limit_usd_nanos=3_150_000_000,
        provider_job_caps={"llm": 1, "video": 1},
        selected_optional_media=(),
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=2),
    )
    activation = W5FastActivationRecordV1(
        activation_id="w5fastact:cli-fixture-001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        sample_ref=plan.sample_ref,
        approved_by="reviewer:ll",
        approved_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        authorization_statement=W5_FAST_AUTHORIZATION_STATEMENT,
        budget_limit_usd_nanos=plan.budget_limit_usd_nanos,
        provider_job_caps=plan.provider_job_caps,
    )
    prompt = "private prompt must not enter binding"
    plan_path = tmp_path / "plan.json"
    activation_path = tmp_path / "activation.json"
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "binding.json"
    plan_path.write_text(plan.model_dump_json())
    activation_path.write_text(activation.model_dump_json())
    request_path.write_text(
        json.dumps(
            {
                "user_prompt": prompt,
                "duration": 15,
                "enable_tts": False,
                "api_keys": {},
                "enable_media_synthesis": True,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
            }
        )
    )
    environment = os.environ.copy()
    environment.pop("API_KEY", None)
    environment.pop("TEST_BUNDLE_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--plan",
            str(plan_path),
            "--activation",
            str(activation_path),
            "--request",
            str(request_path),
            "--idempotency-key-sha256",
            "a" * 64,
            "--c2pa-signing-mode",
            "required",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    binding = json.loads(output_path.read_text())
    assert binding["activation_id"] == activation.activation_id
    assert binding["idempotency_key_sha256"] == "a" * 64
    assert prompt not in output_path.read_text()
    assert "provider_call" not in output_path.read_text()

    request_path.write_text(
        request_path.read_text().replace(
            '"provider_max_retries": 0',
            '"provider_max_retries": 0.0',
        )
    )
    invalid_output = tmp_path / "invalid-binding.json"
    invalid = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--plan",
            str(plan_path),
            "--activation",
            str(activation_path),
            "--request",
            str(request_path),
            "--idempotency-key-sha256",
            "a" * 64,
            "--c2pa-signing-mode",
            "required",
            "--output",
            str(invalid_output),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2
    assert not invalid_output.exists()
