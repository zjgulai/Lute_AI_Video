#!/usr/bin/env python3
"""Fail-closed L4C expanded token-smoke plan validator."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
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


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
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
            isinstance(media_generation.get("s1_allowed"), bool) and isinstance(media_generation.get("s5_allowed"), bool),
            "media_generation must explicitly state s1_allowed and s5_allowed booleans.",
            refs=["media_generation.s1_allowed", "media_generation.s5_allowed"],
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--plan-record", type=Path, help=f"Private L4C plan JSON. Defaults to {PLAN_RECORD_ENV}.")
    parser.add_argument("--json", action="store_true", help="Print the plan report as JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report(args.base_url, plan_record=args.plan_record)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
