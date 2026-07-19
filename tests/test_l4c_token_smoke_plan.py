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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "l4c_token_smoke_plan.py"
TEMPLATE = REPO_ROOT / "configs" / "l4c-token-smoke-plan-template.json"
DEMO_KEY = "ai_video_demo_2026"
WORKFLOW_RUN_REF = "123456789:1"
COMMIT_SHA = "a" * 40

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
        "workflow_run_ref": WORKFLOW_RUN_REF,
        "commit_sha": COMMIT_SHA,
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
            "fast_allowed": True,
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


def _valid_workflow_approval(plan: dict, approval_path: Path) -> dict:
    spec = f"e2e/production/{plan['allowed_specs'][0]}"
    now = datetime.now(UTC).replace(microsecond=0)
    return {
        "template_only": False,
        "scope": "l4c-token-smoke",
        "status": "approved",
        "provider_calls_allowed": True,
        "approved_by": "pray",
        "checked_by": "pray",
        "approved_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workflow_run_ref": plan["workflow_run_ref"],
        "commit_sha": plan["commit_sha"],
        "token_smoke_spec": spec,
        "budget_limit_usd": plan["budget_limit_usd"],
        "max_submit_count": plan["max_submit_count"],
        "provider_max_retries": plan["provider_max_retries"],
        "artifact_disposition": "pending_review",
        "media_synthesis_allowed": spec.endswith(
            "/fast-mode-single-submit.prod.spec.ts"
        ),
        "approval_record_ref": str(approval_path),
    }


def _run_ci_validator(
    plan: Path,
    approval: Path,
    env_file: Path,
    *,
    spec: str = "e2e/production/fast-mode-single-submit.prod.spec.ts",
    plan_ref: str | None = None,
    approval_ref: str | None = None,
    workflow_run_ref: str | None = None,
    commit_sha: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        "--ci-validate",
        "--plan-record",
        str(plan),
        "--approval-record",
        str(approval),
        "--selected-spec",
        spec,
        "--env-file",
        str(env_file),
    ]
    if plan_ref is not None:
        args.extend(("--plan-ref", plan_ref))
    if approval_ref is not None:
        args.extend(("--approval-ref", approval_ref))
    if workflow_run_ref is not None:
        args.extend(("--workflow-run-ref", workflow_run_ref))
    if commit_sha is not None:
        args.extend(("--commit-sha", commit_sha))
    return _run_script(*args, env={"PLAYWRIGHT_API_KEY": "prod-api-key"})


def _write_bound_workflow_records(
    tmp_path: Path,
) -> tuple[dict, dict, Path, Path, str, str]:
    plan_ref = "l4c/2026-07-11/plan-fast-001"
    approval_ref = "l4c/2026-07-11/approval-fast-001"
    payload = _valid_plan()
    payload["plan_record_ref"] = plan_ref
    payload["approval"]["approval_record_ref"] = approval_ref
    approval_path = tmp_path / "runner-secret-approval.json"
    approval_payload = _valid_workflow_approval(payload, approval_path)
    approval_payload["plan_record_ref"] = plan_ref
    approval_payload["approval_record_ref"] = approval_ref
    plan_path = tmp_path / "runner-secret-plan.json"
    plan_path.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    return (
        payload,
        approval_payload,
        plan_path,
        approval_path,
        plan_ref,
        approval_ref,
    )


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


def test_ci_validator_emits_only_validated_single_spec_environment(tmp_path: Path):
    payload = _valid_plan()
    approval = tmp_path / "approval.json"
    payload["approval"]["approval_record_ref"] = str(approval)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(payload))
    approval.write_text(json.dumps(_valid_workflow_approval(payload, approval)))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(plan, approval, env_file)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "npx playwright" not in result.stdout
    assert env_file.read_text().splitlines() == [
        "PLAYWRIGHT_TOKEN_SMOKE_SPEC=e2e/production/fast-mode-single-submit.prod.spec.ts",
        "PLAYWRIGHT_MAX_SUBMIT_COUNT=1",
        "PLAYWRIGHT_PROVIDER_MAX_RETRIES=0",
        "PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review",
        "PLAYWRIGHT_TOKEN_SMOKE_BUDGET_USD=2.0",
    ]


def test_ci_validator_exactly_binds_logical_plan_and_approval_refs(
    tmp_path: Path,
):
    plan_ref = "l4c/2026-07-11/plan-fast-001"
    approval_ref = "l4c/2026-07-11/approval-fast-001"
    payload = _valid_plan()
    payload["plan_record_ref"] = plan_ref
    payload["approval"]["approval_record_ref"] = approval_ref
    approval_path = tmp_path / "runner-secret-approval.json"
    approval_payload = _valid_workflow_approval(payload, approval_path)
    approval_payload["plan_record_ref"] = plan_ref
    approval_payload["approval_record_ref"] = approval_ref
    plan_path = tmp_path / "runner-secret-plan.json"
    plan_path.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "npx playwright" not in result.stdout
    assert env_file.exists()


def test_ci_validator_exactly_binds_current_workflow_run_and_commit(
    tmp_path: Path,
):
    (
        _plan_payload,
        _approval_payload,
        plan_path,
        approval_path,
        plan_ref,
        approval_ref,
    ) = _write_bound_workflow_records(tmp_path)
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
        workflow_run_ref=WORKFLOW_RUN_REF,
        commit_sha=COMMIT_SHA,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert env_file.exists()


@pytest.mark.parametrize(
    "record_mutation",
    [
        pytest.param(
            lambda plan, approval: plan.update(workflow_run_ref="987654321:1"),
            id="plan-workflow-run-ref",
        ),
        pytest.param(
            lambda plan, approval: approval.update(workflow_run_ref="987654321:1"),
            id="approval-workflow-run-ref",
        ),
        pytest.param(
            lambda plan, approval: plan.update(commit_sha="b" * 40),
            id="plan-commit-sha",
        ),
        pytest.param(
            lambda plan, approval: approval.update(commit_sha="b" * 40),
            id="approval-commit-sha",
        ),
    ],
)
def test_ci_validator_rejects_current_dispatch_binding_drift(
    tmp_path: Path,
    record_mutation,
):
    (
        plan_payload,
        approval_payload,
        plan_path,
        approval_path,
        plan_ref,
        approval_ref,
    ) = _write_bound_workflow_records(tmp_path)
    record_mutation(plan_payload, approval_payload)
    plan_path.write_text(json.dumps(plan_payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
        workflow_run_ref=WORKFLOW_RUN_REF,
        commit_sha=COMMIT_SHA,
    )

    assert result.returncode != 0
    assert not env_file.exists()


@pytest.mark.parametrize(
    ("workflow_run_ref", "commit_sha"),
    [
        pytest.param("not-a-run-ref", COMMIT_SHA, id="invalid-run-ref"),
        pytest.param(WORKFLOW_RUN_REF, "abc123", id="invalid-commit-sha"),
        pytest.param(WORKFLOW_RUN_REF, None, id="missing-commit-sha"),
        pytest.param(None, COMMIT_SHA, id="missing-workflow-run-ref"),
    ],
)
def test_ci_validator_rejects_invalid_or_unpaired_dispatch_identity(
    tmp_path: Path,
    workflow_run_ref: str | None,
    commit_sha: str | None,
):
    (
        _plan_payload,
        _approval_payload,
        plan_path,
        approval_path,
        plan_ref,
        approval_ref,
    ) = _write_bound_workflow_records(tmp_path)
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
        workflow_run_ref=workflow_run_ref,
        commit_sha=commit_sha,
    )

    assert result.returncode != 0
    assert not env_file.exists()


@pytest.mark.parametrize(
    "time_case",
    [
        "approved-offset-not-z",
        "approved-in-future",
        "expires-missing",
        "expires-offset-not-z",
        "expires-not-future",
        "window-over-four-hours",
    ],
)
def test_ci_validator_rejects_invalid_or_replayable_approval_window(
    tmp_path: Path,
    time_case: str,
):
    (
        plan_payload,
        approval_payload,
        plan_path,
        approval_path,
        plan_ref,
        approval_ref,
    ) = _write_bound_workflow_records(tmp_path)
    now = datetime.now(UTC).replace(microsecond=0)
    if time_case == "approved-offset-not-z":
        approval_payload["approved_at"] = now.isoformat()
    elif time_case == "approved-in-future":
        approval_payload["approved_at"] = (now + timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    elif time_case == "expires-missing":
        approval_payload.pop("expires_at")
    elif time_case == "expires-offset-not-z":
        approval_payload["expires_at"] = (now + timedelta(hours=1)).isoformat()
    elif time_case == "expires-not-future":
        approval_payload["expires_at"] = (now - timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    elif time_case == "window-over-four-hours":
        approval_payload["approved_at"] = (now - timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        approval_payload["expires_at"] = (now + timedelta(hours=4)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:  # pragma: no cover - parameter list is exhaustive
        raise AssertionError(time_case)
    plan_path.write_text(json.dumps(plan_payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
        workflow_run_ref=WORKFLOW_RUN_REF,
        commit_sha=COMMIT_SHA,
    )

    assert result.returncode != 0
    assert not env_file.exists()


@pytest.mark.parametrize(
    "record_mutation",
    [
        pytest.param(
            lambda plan, approval: plan["media_generation"].pop("fast_allowed"),
            id="plan-fast-media-missing",
        ),
        pytest.param(
            lambda plan, approval: plan["media_generation"].update(
                fast_allowed=False
            ),
            id="plan-fast-media-denied",
        ),
        pytest.param(
            lambda plan, approval: approval.pop("media_synthesis_allowed"),
            id="approval-fast-media-missing",
        ),
        pytest.param(
            lambda plan, approval: approval.update(media_synthesis_allowed=False),
            id="approval-fast-media-denied",
        ),
    ],
)
def test_ci_validator_requires_exact_fast_media_authority(
    tmp_path: Path,
    record_mutation,
):
    plan_ref = "l4c/2026-07-11/plan-fast-001"
    approval_ref = "l4c/2026-07-11/approval-fast-001"
    payload = _valid_plan()
    payload["plan_record_ref"] = plan_ref
    payload["approval"]["approval_record_ref"] = approval_ref
    approval_path = tmp_path / "runner-secret-approval.json"
    approval_payload = _valid_workflow_approval(payload, approval_path)
    approval_payload["plan_record_ref"] = plan_ref
    approval_payload["approval_record_ref"] = approval_ref
    record_mutation(payload, approval_payload)
    plan_path = tmp_path / "runner-secret-plan.json"
    plan_path.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
    )

    assert result.returncode != 0
    assert "npx playwright" not in result.stdout
    assert not env_file.exists()


@pytest.mark.parametrize(
    "record_mutation",
    [
        pytest.param(
            lambda plan, approval: plan.update(plan_record_ref="wrong-plan-ref"),
            id="plan-record-plan-ref",
        ),
        pytest.param(
            lambda plan, approval: approval.update(plan_record_ref="wrong-plan-ref"),
            id="approval-record-plan-ref",
        ),
        pytest.param(
            lambda plan, approval: plan["approval"].update(
                approval_record_ref="wrong-approval-ref"
            ),
            id="plan-record-approval-ref",
        ),
        pytest.param(
            lambda plan, approval: approval.update(
                approval_record_ref="wrong-approval-ref"
            ),
            id="approval-record-self-ref",
        ),
    ],
)
def test_ci_validator_rejects_logical_audit_ref_drift(
    tmp_path: Path,
    record_mutation,
):
    plan_ref = "l4c/2026-07-11/plan-fast-001"
    approval_ref = "l4c/2026-07-11/approval-fast-001"
    payload = _valid_plan()
    payload["plan_record_ref"] = plan_ref
    payload["approval"]["approval_record_ref"] = approval_ref
    approval_path = tmp_path / "runner-secret-approval.json"
    approval_payload = _valid_workflow_approval(payload, approval_path)
    approval_payload["plan_record_ref"] = plan_ref
    approval_payload["approval_record_ref"] = approval_ref
    record_mutation(payload, approval_payload)
    plan_path = tmp_path / "runner-secret-plan.json"
    plan_path.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref=plan_ref,
        approval_ref=approval_ref,
    )

    assert result.returncode != 0
    assert "npx playwright" not in result.stdout
    assert not env_file.exists()


def test_ci_validator_requires_both_logical_refs_or_neither(tmp_path: Path):
    payload = _valid_plan()
    approval_path = tmp_path / "approval.json"
    payload["approval"]["approval_record_ref"] = str(approval_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(_valid_workflow_approval(payload, approval_path)))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(
        plan_path,
        approval_path,
        env_file,
        plan_ref="l4c/2026-07-11/plan-fast-001",
    )

    assert result.returncode != 0
    assert not env_file.exists()


def test_ci_validator_blocks_missing_approval_before_emitting_playwright_command(tmp_path: Path):
    payload = _valid_plan()
    missing_approval = tmp_path / "missing-approval.json"
    payload["approval"]["approval_record_ref"] = str(missing_approval)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(plan, missing_approval, env_file)

    assert result.returncode != 0
    assert "npx playwright" not in result.stdout
    assert not env_file.exists()


def test_ci_validator_rejects_non_finite_budget_even_when_records_match(
    tmp_path: Path,
):
    payload = _valid_plan()
    approval_path = tmp_path / "approval.json"
    payload["approval"]["approval_record_ref"] = str(approval_path)
    payload["budget_limit_usd"] = float("inf")
    payload["per_spec_budget_usd"] = {
        "fast-mode-single-submit.prod.spec.ts": float("inf")
    }
    approval_payload = _valid_workflow_approval(payload, approval_path)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(plan, approval_path, env_file)

    assert result.returncode != 0
    assert "npx playwright" not in result.stdout
    assert not env_file.exists()


@pytest.mark.parametrize(
    ("mutator", "spec"),
    [
        pytest.param(
            lambda plan, approval: plan.update(max_submit_count=2),
            "e2e/production/fast-mode-single-submit.prod.spec.ts",
            id="submit-cap-above-one",
        ),
        pytest.param(
            lambda plan, approval: plan.update(provider_max_retries=1),
            "e2e/production/fast-mode-single-submit.prod.spec.ts",
            id="provider-retry-above-zero",
        ),
        pytest.param(
            lambda plan, approval: plan["artifact_policy"].update(asset_status="approved"),
            "e2e/production/fast-mode-single-submit.prod.spec.ts",
            id="non-pending-review",
        ),
        pytest.param(
            lambda plan, approval: approval.update(budget_limit_usd=99.0),
            "e2e/production/fast-mode-single-submit.prod.spec.ts",
            id="budget-mismatch",
        ),
        pytest.param(
            lambda plan, approval: None,
            "e2e/production/scenario-multi-submit.prod.spec.ts",
            id="spec-not-single-submit-allowlist",
        ),
        pytest.param(
            lambda plan, approval: None,
            "e2e/production/fast-mode-single-submit.prod.spec.ts --workers=4",
            id="spec-option-injection",
        ),
    ],
)
def test_ci_validator_blocks_unsafe_workflow_inputs(
    tmp_path: Path,
    mutator,
    spec: str,
):
    payload = _valid_plan()
    approval_path = tmp_path / "approval.json"
    payload["approval"]["approval_record_ref"] = str(approval_path)
    approval_payload = _valid_workflow_approval(payload, approval_path)
    mutator(payload, approval_payload)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(payload))
    approval_path.write_text(json.dumps(approval_payload))
    env_file = tmp_path / "github-env"

    result = _run_ci_validator(plan, approval_path, env_file, spec=spec)

    assert result.returncode != 0
    assert "npx playwright" not in result.stdout
    assert not env_file.exists()
