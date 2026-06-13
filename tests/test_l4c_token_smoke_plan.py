"""Guard the L4C token-smoke plan validator.

The validator is intentionally no-execute: it turns the expanded token-smoke
authorization requirements into a machine-checkable packet without launching
Playwright or provider-backed production work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "l4c_token_smoke_plan.py"
TEMPLATE = REPO_ROOT / "configs" / "l4c-token-smoke-plan-template.json"
DEMO_KEY = "ai_video_demo_2026"

ENV_KEYS = {
    "AI_VIDEO_L4C_TOKEN_SMOKE_PLAN_RECORD",
    "PLAYWRIGHT_API_KEY",
    "RUN_TOKEN_SMOKE",
}


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
    if env:
        clean_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )


def _valid_plan() -> dict:
    return {
        "template_only": False,
        "scope": "l4c-token-smoke",
        "status": "approved",
        "created": "2026-06-11",
        "updated": "2026-06-11",
        "owner": "self",
        "target_base_url": "https://video.lute-tlz-dddd.top",
        "allowed_specs": [
            "fast-mode-single-submit.prod.spec.ts",
        ],
        "budget_limit_usd": 2.0,
        "per_spec_budget_usd": {
            "fast-mode-single-submit.prod.spec.ts": 2.0,
        },
        "max_auto_retries": 0,
        "max_submit_count": 1,
        "provider_max_retries": 0,
        "serial_workers_required": True,
        "run_token_smoke_required": True,
        "media_generation": {
            "s1_allowed": False,
            "s5_allowed": False,
            "notes": "S1/S5 media generation is explicitly denied in this sample plan.",
        },
        "artifact_policy": {
            "asset_status": "pending_review",
            "storage_scope": "tenant_pending_review",
            "delivery_accepted": False,
            "publish_allowed": False,
            "approved_brand_token_write": False,
        },
        "approval": {
            "approved_by": "pray",
            "checked_by": "pray",
            "approval_record_ref": "tmp/outputs/private-l4c-approval.json",
            "provider_account_readiness_record_ref": "tmp/outputs/private-provider-readiness.json",
        },
    }


def test_default_run_blocks_without_plan_or_key():
    result = _run_script()

    assert result.returncode == 0
    assert "Ready for L4C operator review: false" in result.stdout
    assert "l4c_plan_record: block" in result.stdout
    assert "playwright_api_key: block" in result.stdout
    assert "Command preview" in result.stdout
    assert "RUN_TOKEN_SMOKE=1" in result.stdout
    assert "npx playwright test" in result.stdout


def test_template_plan_is_present_and_blocked_by_default():
    result = _run_script(
        "--json",
        "--plan-record",
        str(TEMPLATE),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["blocked"] is True
    assert report["provider_call_executed"] is False
    assert report["token_smoke_executed"] is False
    statuses = {check["name"]: check["status"] for check in report["checks"]}
    assert statuses["template_promoted_to_real_plan"] == "block"
    assert statuses["submit_count_policy"] == "block"
    assert statuses["budget_limit"] == "block"
    assert statuses["per_spec_budget"] == "block"


def test_valid_plan_still_blocks_without_non_demo_playwright_key(tmp_path: Path):
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(_valid_plan()))

    result = _run_script("--json", "--plan-record", str(plan))

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["blocked"] is True
    assert report["ready_for_l4c_operator_review"] is False
    assert {check["name"]: check["status"] for check in report["checks"]}["playwright_api_key"] == "block"


def test_valid_plan_with_non_demo_key_is_l2_ready_without_executing(tmp_path: Path):
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(_valid_plan()))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["ready_for_l4c_operator_review"] is True
    assert report["evidence_level"] == "L2-fixture-or-dry-run"
    assert report["provider_call_executed"] is False
    assert report["token_smoke_executed"] is False
    assert report["token_smoke_allowed_by_this_script"] is False
    assert report["allowed_specs"] == ["fast-mode-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "PLAYWRIGHT_PROD_WORKERS=1" in report["command_preview"]
    assert "PLAYWRIGHT_MAX_SUBMIT_COUNT=1" in report["command_preview"]
    assert "PLAYWRIGHT_PROVIDER_MAX_RETRIES=0" in report["command_preview"]
    assert "PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review" in report["command_preview"]
    assert "e2e/production/fast-mode-single-submit.prod.spec.ts" in report["command_preview"]


def test_valid_s2_no_media_single_submit_plan_is_l2_ready(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["scenario-s2-no-media-single-submit.prod.spec.ts"]
    payload["per_spec_budget_usd"] = {"scenario-s2-no-media-single-submit.prod.spec.ts": 1.0}
    payload["budget_limit_usd"] = 1.0
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["allowed_specs"] == ["scenario-s2-no-media-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts" in report["command_preview"]


def test_valid_s1_no_media_single_submit_plan_is_l2_ready(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["scenario-s1-no-media-single-submit.prod.spec.ts"]
    payload["per_spec_budget_usd"] = {"scenario-s1-no-media-single-submit.prod.spec.ts": 1.0}
    payload["budget_limit_usd"] = 1.0
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["allowed_specs"] == ["scenario-s1-no-media-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts" in report["command_preview"]


def test_valid_s3_no_media_single_submit_plan_is_l2_ready(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["scenario-s3-no-media-single-submit.prod.spec.ts"]
    payload["per_spec_budget_usd"] = {"scenario-s3-no-media-single-submit.prod.spec.ts": 1.0}
    payload["budget_limit_usd"] = 1.0
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["allowed_specs"] == ["scenario-s3-no-media-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "e2e/production/scenario-s3-no-media-single-submit.prod.spec.ts" in report["command_preview"]


def test_valid_s4_no_media_single_submit_plan_is_l2_ready(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["scenario-s4-no-media-single-submit.prod.spec.ts"]
    payload["per_spec_budget_usd"] = {"scenario-s4-no-media-single-submit.prod.spec.ts": 1.0}
    payload["budget_limit_usd"] = 1.0
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["allowed_specs"] == ["scenario-s4-no-media-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "e2e/production/scenario-s4-no-media-single-submit.prod.spec.ts" in report["command_preview"]


def test_valid_s5_no_media_single_submit_plan_is_l2_ready(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["scenario-s5-no-media-single-submit.prod.spec.ts"]
    payload["per_spec_budget_usd"] = {"scenario-s5-no-media-single-submit.prod.spec.ts": 1.0}
    payload["budget_limit_usd"] = 1.0
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert report["blocked"] is False
    assert report["allowed_specs"] == ["scenario-s5-no-media-single-submit.prod.spec.ts"]
    assert report["max_submit_count"] == 1
    assert report["provider_max_retries"] == 0
    assert "e2e/production/scenario-s5-no-media-single-submit.prod.spec.ts" in report["command_preview"]


def test_plan_rejects_demo_key_unknown_specs_and_retries(tmp_path: Path):
    payload = _valid_plan()
    payload["allowed_specs"] = ["unknown.prod.spec.ts"]
    payload["max_auto_retries"] = 1
    payload["max_submit_count"] = 0
    payload["provider_max_retries"] = 1
    payload["per_spec_budget_usd"] = {"unknown.prod.spec.ts": 1.0}
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": DEMO_KEY},
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    statuses = {check["name"]: check["status"] for check in report["checks"]}
    assert statuses["playwright_api_key"] == "block"
    assert statuses["allowed_specs"] == "block"
    assert statuses["retry_policy"] == "block"
    assert statuses["submit_count_policy"] == "block"
    assert statuses["provider_retry_policy"] == "block"


def test_plan_rejects_non_pending_review_storage_scope(tmp_path: Path):
    payload = _valid_plan()
    payload["artifact_policy"]["storage_scope"] = "fast_mode"
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(payload))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={"PLAYWRIGHT_API_KEY": "prod-api-key"},
    )

    report = json.loads(result.stdout)
    assert {check["name"]: check["status"] for check in report["checks"]}["artifact_storage_scope"] == "block"


def test_current_shell_run_token_smoke_must_not_be_enabled_for_validation(tmp_path: Path):
    plan = tmp_path / "l4c-plan.json"
    plan.write_text(json.dumps(_valid_plan()))

    result = _run_script(
        "--json",
        "--plan-record",
        str(plan),
        env={
            "PLAYWRIGHT_API_KEY": "prod-api-key",
            "RUN_TOKEN_SMOKE": "1",
        },
    )

    report = json.loads(result.stdout)
    assert {check["name"]: check["status"] for check in report["checks"]}["current_shell_token_smoke_disabled"] == "block"


def test_source_is_no_execute_and_contains_no_provider_secret_requirements():
    source = SCRIPT.read_text()

    assert "subprocess" not in source
    assert "--execute" not in source
    assert "POYO_API_KEY" not in source
    assert "DEEPSEEK_API_KEY" not in source
    assert "SILICONFLOW_API_KEY" not in source
    assert "AI_VIDEO_L4C_TOKEN_SMOKE_PLAN_RECORD" in source
    assert "token_smoke_allowed_by_this_script" in source
