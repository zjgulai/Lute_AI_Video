#!/usr/bin/env python3
"""Fail-closed L4C expanded token-smoke plan validator."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
DEMO_API_KEY = "ai_video_demo_2026"
PLAN_RECORD_ENV = "AI_VIDEO_L4C_TOKEN_SMOKE_PLAN_RECORD"
PLAYWRIGHT_KEY_ENV = "PLAYWRIGHT_API_KEY"
TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"

KNOWN_TOKEN_SMOKE_SPECS = {
    "fast-mode-single-submit.prod.spec.ts",
    "fast-mode-submit.prod.spec.ts",
    "scenario-s1-no-media-single-submit.prod.spec.ts",
    "scenario-s2-no-media-single-submit.prod.spec.ts",
    "scenario-s3-no-media-single-submit.prod.spec.ts",
    "scenario-s4-no-media-single-submit.prod.spec.ts",
    "scenario-s5-no-media-single-submit.prod.spec.ts",
    "user-journey.prod.spec.ts",
    "s1-gate.prod.spec.ts",
    "s1-step-by-step.prod.spec.ts",
    "scenario-multi-submit.prod.spec.ts",
}

WORKFLOW_SINGLE_SPEC_PATHS = frozenset(
    {
        "e2e/production/fast-mode-single-submit.prod.spec.ts",
        "e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts",
        "e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts",
        "e2e/production/scenario-s3-no-media-single-submit.prod.spec.ts",
        "e2e/production/scenario-s4-no-media-single-submit.prod.spec.ts",
        "e2e/production/scenario-s5-no-media-single-submit.prod.spec.ts",
    }
)
_WORKFLOW_SPEC_PATTERN = re.compile(
    r"^e2e/production/[a-z0-9]+(?:-[a-z0-9]+)*\.prod\.spec\.ts$"
)
_WORKFLOW_RUN_REF_PATTERN = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")
_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UTC_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_MAX_APPROVAL_WINDOW = timedelta(hours=4)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _normalize_spec(value: object) -> str:
    raw = str(value).strip()
    return Path(raw).name


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return None, f"plan record does not exist: {path}"
    except json.JSONDecodeError as exc:
        return None, f"plan record is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "plan record must be a JSON object"
    return payload, None


def _same_path(left: object, right: Path) -> bool:
    if not isinstance(left, str) or not left.strip():
        return False
    try:
        return Path(left).expanduser().resolve() == right.expanduser().resolve()
    except (OSError, RuntimeError):
        return False


def _logical_ref_is_valid(value: str | None) -> bool:
    """Accept a stable audit identifier, never a filesystem destination."""

    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= 512
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def _record_ref_matches(
    value: object,
    *,
    logical_ref: str | None,
    record_path: Path,
) -> bool:
    if logical_ref is None:
        return _same_path(value, record_path)
    return _logical_ref_is_valid(logical_ref) and value == logical_ref


def _parse_strict_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _check(name: str, ok: bool, detail: str, *, refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if ok else "block",
        "detail": detail,
        "evidence_refs": refs or [],
    }


def _validate_plan(plan: dict[str, Any] | None, base_url: str) -> tuple[list[dict[str, Any]], list[str]]:
    if plan is None:
        return (
            [
                _check(
                    "l4c_plan_record",
                    False,
                    f"{PLAN_RECORD_ENV} or --plan-record must point to a private L4C plan JSON.",
                    refs=[PLAN_RECORD_ENV, "configs/l4c-token-smoke-plan-template.json"],
                )
            ],
            [],
        )

    allowed_specs = [_normalize_spec(item) for item in plan.get("allowed_specs", []) or []]
    unknown_specs = sorted(set(allowed_specs) - KNOWN_TOKEN_SMOKE_SPECS)
    per_spec_budget = plan.get("per_spec_budget_usd", {})
    artifact_policy = plan.get("artifact_policy", {})
    approval = plan.get("approval", {})
    media_generation = plan.get("media_generation", {})
    budget = _number(plan.get("budget_limit_usd"))
    retries = plan.get("max_auto_retries")
    max_submit_count = plan.get("max_submit_count")
    provider_max_retries = plan.get("provider_max_retries")

    checks = [
        _check(
            "template_promoted_to_real_plan",
            plan.get("template_only") is False,
            "template_only must be false before L4C; template files cannot authorize token smoke.",
            refs=["template_only"],
        ),
        _check(
            "scope",
            plan.get("scope") == "l4c-token-smoke",
            "scope must be l4c-token-smoke.",
            refs=["scope"],
        ),
        _check(
            "approval_status",
            plan.get("status") == "approved",
            "status must be approved by the named checker before L4C.",
            refs=["status", "approval.checked_by"],
        ),
        _check(
            "target_base_url",
            plan.get("target_base_url") == base_url,
            f"target_base_url must match {base_url}.",
            refs=["target_base_url"],
        ),
        _check(
            "allowed_specs",
            bool(allowed_specs) and not unknown_specs,
            (
                "allowed_specs must be a non-empty subset of known @token-smoke production spec files."
                if not unknown_specs
                else f"unknown specs are not allowed: {', '.join(unknown_specs)}"
            ),
            refs=["allowed_specs"],
        ),
        _check(
            "budget_limit",
            budget is not None and budget > 0,
            "budget_limit_usd must be a positive numeric stop-loss.",
            refs=["budget_limit_usd"],
        ),
        _check(
            "per_spec_budget",
            isinstance(per_spec_budget, dict)
            and bool(allowed_specs)
            and all(_number(per_spec_budget.get(spec)) is not None and _number(per_spec_budget.get(spec)) > 0 for spec in allowed_specs),
            "per_spec_budget_usd must include a positive ceiling for every allowed spec.",
            refs=["per_spec_budget_usd"],
        ),
        _check(
            "retry_policy",
            retries == 0,
            "max_auto_retries must be 0; failed L4C specs require human review before any rerun.",
            refs=["max_auto_retries"],
        ),
        _check(
            "submit_count_policy",
            isinstance(max_submit_count, int) and not isinstance(max_submit_count, bool) and max_submit_count > 0,
            "max_submit_count must be a positive integer and must match the authorized submit ceiling.",
            refs=["max_submit_count"],
        ),
        _check(
            "provider_retry_policy",
            provider_max_retries == 0,
            "provider_max_retries must be 0 for L4C token smoke; backend/provider retries require separate authorization.",
            refs=["provider_max_retries"],
        ),
        _check(
            "serial_workers",
            plan.get("serial_workers_required") is True,
            "serial_workers_required must be true; L4C must run with PLAYWRIGHT_PROD_WORKERS=1.",
            refs=["serial_workers_required"],
        ),
        _check(
            "run_token_smoke_flag",
            plan.get("run_token_smoke_required") is True,
            "run_token_smoke_required must be true for an explicit L4C plan.",
            refs=["run_token_smoke_required"],
        ),
        _check(
            "media_generation_boundary",
            isinstance(media_generation.get("fast_allowed"), bool)
            and isinstance(media_generation.get("s1_allowed"), bool)
            and isinstance(media_generation.get("s5_allowed"), bool),
            "media_generation must explicitly state fast_allowed, s1_allowed and s5_allowed booleans.",
            refs=[
                "media_generation.fast_allowed",
                "media_generation.s1_allowed",
                "media_generation.s5_allowed",
            ],
        ),
        _check(
            "pending_review_only",
            artifact_policy.get("asset_status") == "pending_review",
            "artifact_policy.asset_status must remain pending_review.",
            refs=["artifact_policy.asset_status"],
        ),
        _check(
            "artifact_storage_scope",
            artifact_policy.get("storage_scope") in {"tenant_pending_review", "quarantine"},
            "artifact_policy.storage_scope must be tenant_pending_review or quarantine.",
            refs=["artifact_policy.storage_scope"],
        ),
        _check(
            "no_delivery_acceptance",
            artifact_policy.get("delivery_accepted") is False,
            "artifact_policy.delivery_accepted must be false.",
            refs=["artifact_policy.delivery_accepted"],
        ),
        _check(
            "no_publish",
            artifact_policy.get("publish_allowed") is False,
            "artifact_policy.publish_allowed must be false.",
            refs=["artifact_policy.publish_allowed"],
        ),
        _check(
            "no_brand_token_write",
            artifact_policy.get("approved_brand_token_write") is False,
            "artifact_policy.approved_brand_token_write must be false.",
            refs=["artifact_policy.approved_brand_token_write"],
        ),
        _check(
            "approval_refs",
            all(str(approval.get(key, "")).strip() for key in ("approved_by", "checked_by", "approval_record_ref", "provider_account_readiness_record_ref")),
            "approval must include approved_by, checked_by, approval_record_ref, and provider_account_readiness_record_ref.",
            refs=["approval"],
        ),
    ]
    return checks, allowed_specs


def _env_checks(env: dict[str, str]) -> list[dict[str, Any]]:
    key = env.get(PLAYWRIGHT_KEY_ENV, "").strip()
    current_token_smoke = _is_truthy(env.get(TOKEN_SMOKE_ENV))
    return [
        _check(
            "current_shell_token_smoke_disabled",
            not current_token_smoke,
            "Run this validator with RUN_TOKEN_SMOKE unset/false; the command preview sets RUN_TOKEN_SMOKE=1 explicitly.",
            refs=[TOKEN_SMOKE_ENV],
        ),
        _check(
            "playwright_api_key",
            bool(key) and key != DEMO_API_KEY,
            (
                f"PLAYWRIGHT_API_KEY is set ({_mask(key)})."
                if key and key != DEMO_API_KEY
                else "PLAYWRIGHT_API_KEY must be a non-demo production key before L4C."
            ),
            refs=[PLAYWRIGHT_KEY_ENV],
        ),
    ]


def _command_preview(base_url: str, allowed_specs: list[str], max_submit_count: int | None = None) -> str:
    spec_args = " ".join(f"e2e/production/{spec}" for spec in allowed_specs) if allowed_specs else "<selected-token-smoke-specs>"
    submit_count = str(max_submit_count) if max_submit_count and max_submit_count > 0 else "<authorized-submit-count>"
    return (
        "cd web && RUN_TOKEN_SMOKE=1 PLAYWRIGHT_PROD_WORKERS=1 "
        f"PLAYWRIGHT_MAX_SUBMIT_COUNT={submit_count} PLAYWRIGHT_PROVIDER_MAX_RETRIES=0 "
        "PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review "
        f"PLAYWRIGHT_PROD_URL={base_url} PLAYWRIGHT_API_KEY=<non-demo-production-key> "
        f"npx playwright test -c playwright.prod.config.ts {spec_args} --reporter=list,html"
    )


def build_report(
    base_url: str,
    *,
    env: dict[str, str] | None = None,
    plan_record: Path | None = None,
) -> dict[str, Any]:
    current_env = dict(os.environ if env is None else env)
    record_path = plan_record or (Path(current_env[PLAN_RECORD_ENV]) if current_env.get(PLAN_RECORD_ENV) else None)
    plan: dict[str, Any] | None = None
    load_error: str | None = None
    if record_path is not None:
        plan, load_error = _load_json(record_path)

    plan_checks, allowed_specs = _validate_plan(plan, base_url)
    checks = _env_checks(current_env) + plan_checks
    if load_error:
        checks.append(_check("plan_record_load", False, load_error, refs=[str(record_path)]))

    blocked = any(check["status"] == "block" for check in checks)
    max_submit_count = plan.get("max_submit_count") if isinstance(plan, dict) else None
    provider_max_retries = plan.get("provider_max_retries") if isinstance(plan, dict) else None
    return {
        "report_id": f"l4c_token_smoke_plan_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "evidence_level": "L2-fixture-or-dry-run",
        "target_base_url": base_url,
        "plan_record": str(record_path) if record_path else None,
        "provider_call_executed": False,
        "token_smoke_executed": False,
        "token_smoke_allowed_by_this_script": False,
        "ready_for_l4c_operator_review": not blocked,
        "blocked": blocked,
        "allowed_specs": allowed_specs,
        "max_submit_count": max_submit_count,
        "provider_max_retries": provider_max_retries,
        "checks": checks,
        "command_preview": _command_preview(base_url, allowed_specs, max_submit_count if isinstance(max_submit_count, int) else None),
        "supported_claims": [
            "This report can prove that the L4C plan packet is structurally ready for human operator review.",
            "A passed report is still only L2 readiness; it does not prove provider runtime success.",
        ],
        "forbidden_claims": [
            "Do not claim L4C passed until the selected production specs complete under explicit authorization.",
            "Do not claim delivery acceptance, publish allowed, or approved brand token from this report.",
            "Do not treat the template plan as authorization.",
        ],
    }


def _print_human(report: dict[str, Any]) -> None:
    print("L4C expanded token-smoke plan validator")
    print(f"Report: {report['report_id']}")
    print(f"Target base URL: {report['target_base_url']}")
    print(f"Evidence level: {report['evidence_level']}")
    print(f"Ready for L4C operator review: {str(report['ready_for_l4c_operator_review']).lower()}")
    print("")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['status']} — {check['detail']}")
    print("")
    print("Command preview:")
    print(report["command_preview"])


def build_ci_validation_report(
    base_url: str,
    *,
    plan_record: Path,
    approval_record: Path,
    selected_spec: str,
    plan_ref: str | None = None,
    approval_ref: str | None = None,
    workflow_run_ref: str | None = None,
    commit_sha: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate one workflow spec without emitting an executable command."""

    current_env = dict(os.environ if env is None else env)
    plan, plan_error = _load_json(plan_record)
    approval, approval_error = _load_json(approval_record)
    plan_checks, allowed_specs = _validate_plan(plan, base_url)
    checks = _env_checks(current_env) + plan_checks
    if plan_error:
        checks.append(
            _check("plan_record_load", False, plan_error, refs=[str(plan_record)])
        )
    if approval_error:
        checks.append(
            _check(
                "approval_record_load",
                False,
                approval_error.replace("plan record", "approval record"),
                refs=[str(approval_record)],
            )
        )

    local_path_mode = plan_ref is None and approval_ref is None
    logical_refs_valid = local_path_mode or (
        _logical_ref_is_valid(plan_ref) and _logical_ref_is_valid(approval_ref)
    )
    checks.append(
        _check(
            "workflow_logical_refs",
            logical_refs_valid,
            "plan_ref and approval_ref must be supplied together as non-empty audit identifiers.",
            refs=["plan_ref", "approval_ref"],
        )
    )

    local_dispatch_mode = workflow_run_ref is None and commit_sha is None
    dispatch_identity_valid = local_dispatch_mode or (
        isinstance(workflow_run_ref, str)
        and bool(_WORKFLOW_RUN_REF_PATTERN.fullmatch(workflow_run_ref))
        and isinstance(commit_sha, str)
        and bool(_COMMIT_SHA_PATTERN.fullmatch(commit_sha))
    )
    checks.append(
        _check(
            "workflow_dispatch_identity",
            dispatch_identity_valid,
            "workflow_run_ref and commit_sha must be supplied together as current GitHub dispatch identifiers.",
            refs=["workflow_run_ref", "commit_sha"],
        )
    )

    if local_dispatch_mode:
        dispatch_records_match = True
    else:
        dispatch_records_match = (
            isinstance(plan, dict)
            and isinstance(approval, dict)
            and plan.get("workflow_run_ref") == workflow_run_ref
            and approval.get("workflow_run_ref") == workflow_run_ref
            and plan.get("commit_sha") == commit_sha
            and approval.get("commit_sha") == commit_sha
        )
    checks.append(
        _check(
            "workflow_dispatch_binding",
            dispatch_records_match,
            "plan and approval records must exactly match the current workflow run and commit.",
            refs=["workflow_run_ref", "commit_sha"],
        )
    )

    if local_path_mode:
        plan_ref_matches = True
    else:
        plan_ref_matches = (
            isinstance(plan, dict)
            and isinstance(approval, dict)
            and plan.get("plan_record_ref") == plan_ref
            and approval.get("plan_record_ref") == plan_ref
        )
    checks.append(
        _check(
            "workflow_plan_ref",
            plan_ref_matches,
            "plan and approval records must exactly match the supplied logical plan ref.",
            refs=["plan_record_ref", "plan_ref"],
        )
    )

    spec_is_safe = bool(_WORKFLOW_SPEC_PATTERN.fullmatch(selected_spec)) and (
        selected_spec in WORKFLOW_SINGLE_SPEC_PATHS
    )
    selected_basename = Path(selected_spec).name if spec_is_safe else ""
    checks.append(
        _check(
            "workflow_single_spec_allowlist",
            spec_is_safe,
            "token_smoke_spec must be one fixed repository-relative single-submit spec.",
            refs=["token_smoke_spec"],
        )
    )

    plan_budget = _number(plan.get("budget_limit_usd")) if isinstance(plan, dict) else None
    per_spec_budget = plan.get("per_spec_budget_usd") if isinstance(plan, dict) else None
    selected_budget = (
        _number(per_spec_budget.get(selected_basename))
        if isinstance(per_spec_budget, dict) and selected_basename
        else None
    )
    plan_approval = plan.get("approval") if isinstance(plan, dict) else None
    artifact_policy = plan.get("artifact_policy") if isinstance(plan, dict) else None
    media_generation = plan.get("media_generation") if isinstance(plan, dict) else None
    checks.extend(
        [
            _check(
                "workflow_plan_exact_spec",
                spec_is_safe and allowed_specs == [selected_basename],
                "plan.allowed_specs must contain exactly the selected single spec.",
                refs=["allowed_specs", "token_smoke_spec"],
            ),
            _check(
                "workflow_submit_cap",
                isinstance(plan, dict)
                and type(plan.get("max_submit_count")) is int
                and plan.get("max_submit_count") == 1,
                "workflow token smoke requires max_submit_count=1.",
                refs=["max_submit_count"],
            ),
            _check(
                "workflow_provider_retry",
                isinstance(plan, dict)
                and type(plan.get("provider_max_retries")) is int
                and plan.get("provider_max_retries") == 0,
                "workflow token smoke requires provider_max_retries=0.",
                refs=["provider_max_retries"],
            ),
            _check(
                "workflow_pending_review",
                isinstance(artifact_policy, dict)
                and artifact_policy.get("asset_status") == "pending_review"
                and artifact_policy.get("storage_scope") == "tenant_pending_review",
                "workflow artifacts must remain tenant_pending_review.",
                refs=["artifact_policy"],
            ),
            _check(
                "workflow_budget_exact",
                plan_budget is not None
                and selected_budget is not None
                and plan_budget == selected_budget,
                "plan total budget and selected-spec budget must match exactly.",
                refs=["budget_limit_usd", "per_spec_budget_usd"],
            ),
            _check(
                "workflow_approval_ref",
                isinstance(plan_approval, dict)
                and _record_ref_matches(
                    plan_approval.get("approval_record_ref"),
                    logical_ref=approval_ref,
                    record_path=approval_record,
                ),
                "plan approval_record_ref must match the supplied approval ref.",
                refs=["approval.approval_record_ref", "approval_ref"],
            ),
        ]
    )

    approval_budget = (
        _number(approval.get("budget_limit_usd")) if isinstance(approval, dict) else None
    )
    approval_shape_ok = (
        isinstance(approval, dict)
        and approval.get("template_only") is False
        and approval.get("scope") == "l4c-token-smoke"
        and approval.get("status") == "approved"
        and approval.get("provider_calls_allowed") is True
        and all(
            isinstance(approval.get(key), str) and approval[key].strip()
            for key in ("approved_by", "checked_by", "approved_at", "expires_at")
        )
    )
    approved_at = (
        _parse_strict_utc_timestamp(approval.get("approved_at"))
        if isinstance(approval, dict)
        else None
    )
    expires_at = (
        _parse_strict_utc_timestamp(approval.get("expires_at"))
        if isinstance(approval, dict)
        else None
    )
    now = datetime.now(UTC)
    approval_window_valid = (
        approved_at is not None
        and expires_at is not None
        and approved_at <= now < expires_at
        and timedelta(0) < expires_at - approved_at <= _MAX_APPROVAL_WINDOW
    )
    fast_media_spec_selected = (
        selected_basename == "fast-mode-single-submit.prod.spec.ts"
    )
    fast_media_authority_matches = not fast_media_spec_selected or (
        isinstance(media_generation, dict)
        and media_generation.get("fast_allowed") is True
        and isinstance(approval, dict)
        and approval.get("media_synthesis_allowed") is True
    )
    checks.extend(
        [
            _check(
                "workflow_approval_status",
                approval_shape_ok,
                "approval record must be non-template, approved, and identify approvers/time.",
                refs=["approval_record_path"],
            ),
            _check(
                "workflow_approval_window",
                approval_window_valid,
                "approval requires strict UTC timestamps with approved_at<=now<expires_at and a maximum four-hour window.",
                refs=["approved_at", "expires_at"],
            ),
            _check(
                "workflow_approval_exact_spec",
                isinstance(approval, dict)
                and approval.get("token_smoke_spec") == selected_spec,
                "approval token_smoke_spec must exactly match the selected spec.",
                refs=["token_smoke_spec"],
            ),
            _check(
                "workflow_fast_media_authority",
                fast_media_authority_matches,
                "Fast media token smoke requires plan fast_allowed=true and approval media_synthesis_allowed=true.",
                refs=[
                    "media_generation.fast_allowed",
                    "media_synthesis_allowed",
                ],
            ),
            _check(
                "workflow_approval_limits",
                isinstance(approval, dict)
                and type(approval.get("max_submit_count")) is int
                and approval.get("max_submit_count") == 1
                and type(approval.get("provider_max_retries")) is int
                and approval.get("provider_max_retries") == 0
                and approval.get("artifact_disposition") == "pending_review",
                "approval must fix submit=1, provider retries=0, disposition=pending_review.",
                refs=["max_submit_count", "provider_max_retries", "artifact_disposition"],
            ),
            _check(
                "workflow_approval_budget_match",
                approval_budget is not None
                and plan_budget is not None
                and approval_budget == plan_budget,
                "approval and plan budget_limit_usd must match exactly.",
                refs=["budget_limit_usd"],
            ),
            _check(
                "workflow_approval_self_ref",
                isinstance(approval, dict)
                and _record_ref_matches(
                    approval.get("approval_record_ref"),
                    logical_ref=approval_ref,
                    record_path=approval_record,
                ),
                "approval_record_ref must match the supplied approval ref.",
                refs=["approval_record_ref", "approval_ref"],
            ),
        ]
    )

    blocked = any(check["status"] == "block" for check in checks)
    return {
        "blocked": blocked,
        "checks": checks,
        "validated_environment": (
            {
                "PLAYWRIGHT_TOKEN_SMOKE_SPEC": selected_spec,
                "PLAYWRIGHT_MAX_SUBMIT_COUNT": "1",
                "PLAYWRIGHT_PROVIDER_MAX_RETRIES": "0",
                "PLAYWRIGHT_ARTIFACT_DISPOSITION": "pending_review",
                "PLAYWRIGHT_TOKEN_SMOKE_BUDGET_USD": str(plan_budget),
            }
            if not blocked
            else {}
        ),
        "provider_call_executed": False,
        "token_smoke_executed": False,
    }


def _append_github_env(path: Path, values: dict[str, str]) -> None:
    lines = []
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\n" in value or "\r" in value:
            raise ValueError("unsafe workflow environment value")
        lines.append(f"{key}={value}\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--plan-record", type=Path, help=f"Private L4C plan JSON. Defaults to {PLAN_RECORD_ENV}.")
    parser.add_argument("--approval-record", type=Path)
    parser.add_argument(
        "--plan-ref",
        help="Logical audit ref bound inside plan and approval records; defaults to local path mode.",
    )
    parser.add_argument(
        "--approval-ref",
        help="Logical audit ref bound inside both records; defaults to local path mode.",
    )
    parser.add_argument(
        "--workflow-run-ref",
        help="Current GitHub workflow run id and attempt as RUN_ID:RUN_ATTEMPT.",
    )
    parser.add_argument(
        "--commit-sha",
        help="Current 40-character lowercase Git commit SHA.",
    )
    parser.add_argument("--selected-spec")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--ci-validate",
        action="store_true",
        help="Fail closed and emit validated GitHub environment values only.",
    )
    parser.add_argument("--json", action="store_true", help="Print the plan report as JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.ci_validate:
        if not all(
            (
                args.plan_record,
                args.approval_record,
                args.selected_spec,
                args.env_file,
            )
        ):
            print(
                "CI validation requires plan, approval, selected spec, and env file.",
                file=sys.stderr,
            )
            return 2
        report = build_ci_validation_report(
            args.base_url,
            plan_record=args.plan_record,
            approval_record=args.approval_record,
            selected_spec=args.selected_spec,
            plan_ref=args.plan_ref,
            approval_ref=args.approval_ref,
            workflow_run_ref=args.workflow_run_ref,
            commit_sha=args.commit_sha,
        )
        if report["blocked"]:
            for check in report["checks"]:
                if check["status"] == "block":
                    print(f"{check['name']}: {check['detail']}", file=sys.stderr)
            return 2
        _append_github_env(args.env_file, report["validated_environment"])
        print("Validated one token-smoke spec; provider_call_executed=false.")
        return 0

    report = build_report(args.base_url, plan_record=args.plan_record)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
