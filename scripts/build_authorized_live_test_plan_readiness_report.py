#!/usr/bin/env python3
"""Build a no-token report for authorized-live test-plan discussion readiness."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
CONFIRM_ENV = "CONFIRM_P2_TOKEN_SMOKE"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from src.pipeline.token_smoke_preflight import (  # noqa: E402
        ACCOUNT_READINESS_RECORD_ENV,
        APPROVAL_RECORD_ENV,
        APPROVAL_STATEMENT_TEMPLATE,
        DEFAULT_AUTH_BUDGET_LIMIT,
        DEFAULT_AUTH_MODEL,
        DEFAULT_AUTH_PROVIDER,
        DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
        DEFAULT_AUTH_TEST_SCOPE,
        PROVIDER_REVALIDATION_REF,
        REQUIRED_API_KEY_ENVS,
        RUN_TOKEN_SMOKE_ENV,
        SAMPLE_PLAN_REF,
        build_token_smoke_preflight_report,
    )

DISCUSSION_ARTIFACT_REFS = (
    "docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md",
    "docs/runbooks/p2-recharge-smoke-checklist.md",
    "scripts/commercial_token_smoke_preflight.py",
    "scripts/build_authorized_live_approval_record.py",
    "scripts/build_provider_account_readiness_record.py",
    "scripts/build_authorized_live_smoke_packet.py",
    "scripts/p2_recharge_smoke_checklist.py",
    SAMPLE_PLAN_REF,
    PROVIDER_REVALIDATION_REF,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--provider", default=DEFAULT_AUTH_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_AUTH_MODEL)
    parser.add_argument("--provider-model-scope", default=DEFAULT_AUTH_PROVIDER_MODEL_SCOPE)
    parser.add_argument("--test-scope", default=DEFAULT_AUTH_TEST_SCOPE)
    parser.add_argument("--budget-limit", default=DEFAULT_AUTH_BUDGET_LIMIT)
    parser.add_argument(
        "--preflight-env",
        choices=("empty", "current"),
        default="empty",
        help="Use empty env for deterministic blocked proof, or current process env.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path; must be under tmp/ or outside repo.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    return parser.parse_args()


def _validate_private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("test-plan readiness output must be under tmp/ or outside the repository")
    return resolved


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json_ref(ref: str) -> tuple[dict[str, Any] | None, str | None]:
    path = REPO_ROOT / ref
    if not path.exists():
        return None, f"{ref} is missing"
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"{ref} is not valid JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return None, f"{ref} must contain a JSON object"
    return payload, None


def _artifact_checks() -> list[dict[str, str]]:
    checks = []
    for ref in DISCUSSION_ARTIFACT_REFS:
        path = REPO_ROOT / ref
        checks.append({
            "ref": ref,
            "status": "pass" if path.exists() else "block",
            "detail": "available" if path.exists() else "missing",
        })
    return checks


def _compact_sample_plan(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "sample_plan_ref": payload.get("sample_plan_ref"),
        "provider_revalidation_ref": payload.get("provider_revalidation_ref"),
        "limits": payload.get("limits", {}),
        "provider_model_scope": payload.get("provider_model_scope"),
        "test_scope": payload.get("test_scope"),
        "expected_pending_asset_package": payload.get("expected_pending_asset_package"),
        "allowed_provider_models": payload.get("allowed_provider_models", []),
        "allowed_scenarios": payload.get("allowed_scenarios", []),
        "core_asset_samples": payload.get("core_asset_samples", []),
        "core_video_samples": payload.get("core_video_samples", []),
        "stop_loss_policy": payload.get("stop_loss_policy", {}),
    }


def _execution_blockers(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = [
        {
            "name": "exact_c21_authorization_statement",
            "detail": "The user must provide the exact C21 authorization statement in the current discussion.",
            "evidence_refs": ["required_authorization_statement"],
        },
        {
            "name": "production_backend_keys",
            "detail": "API_KEY and PLAYWRIGHT_API_KEY must be non-demo production keys.",
            "evidence_refs": ["API_KEY", "PLAYWRIGHT_API_KEY"],
        },
        {
            "name": "double_execute_flags",
            "detail": "CONFIRM_P2_TOKEN_SMOKE=1 and RUN_TOKEN_SMOKE=1 are required for execute mode.",
            "evidence_refs": [CONFIRM_ENV, RUN_TOKEN_SMOKE_ENV],
        },
    ]
    for check in preflight.get("checks", []):
        if not isinstance(check, dict) or check.get("status") != "block":
            continue
        blockers.append({
            "name": str(check.get("name", "preflight_check")),
            "detail": str(check.get("detail", "")),
            "evidence_refs": check.get("evidence_refs", []),
        })
    return blockers


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    authorization_statement = APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=args.provider_model_scope,
        test_scope=args.test_scope,
        budget_limit=args.budget_limit,
    )
    artifact_checks = _artifact_checks()
    sample_plan, sample_plan_error = _load_json_ref(SAMPLE_PLAN_REF)
    provider_revalidation, provider_revalidation_error = _load_json_ref(PROVIDER_REVALIDATION_REF)
    preflight_env = os.environ if args.preflight_env == "current" else {}
    preflight = build_token_smoke_preflight_report(env=preflight_env).model_dump(mode="json")
    artifact_ready = all(check["status"] == "pass" for check in artifact_checks)
    contract_ready = sample_plan_error is None and provider_revalidation_error is None
    discussion_ready = artifact_ready and contract_ready
    live_execution_ready = discussion_ready and preflight["provider_call_allowed"] is True

    return {
        "report_id": f"authorized_live_test_plan_readiness_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "evidence_level": "L2-fixture-or-dry-run",
        "no_provider_call": True,
        "provider_call_allowed": preflight["provider_call_allowed"],
        "ready_for_test_plan_discussion": discussion_ready,
        "ready_for_live_execution": live_execution_ready,
        "preflight_env_source": args.preflight_env,
        "target_base_url": args.base_url,
        "provider": args.provider,
        "model": args.model,
        "provider_model_scope": args.provider_model_scope,
        "test_scope": args.test_scope,
        "required_authorization_statement": authorization_statement,
        "generic_confirmation_is_not_authorization": True,
        "required_private_records": {
            "approval_record_env": APPROVAL_RECORD_ENV,
            "account_readiness_record_env": ACCOUNT_READINESS_RECORD_ENV,
            "output_location_rule": "private records must stay under tmp/ or outside the repository",
        },
        "required_runtime_env": {
            CONFIRM_ENV: "1",
            RUN_TOKEN_SMOKE_ENV: "1",
            "API_KEY": "non-demo production backend key",
            "PLAYWRIGHT_API_KEY": "non-demo production Playwright key",
            **{env_name: "configured; value is never printed by this report" for env_name in REQUIRED_API_KEY_ENVS},
        },
        "discussion_artifacts": artifact_checks,
        "contract_errors": [error for error in (sample_plan_error, provider_revalidation_error) if error],
        "sample_plan": _compact_sample_plan(sample_plan),
        "provider_revalidation_summary": {
            "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
            "status": provider_revalidation.get("status") if provider_revalidation else None,
            "evidence_level": provider_revalidation.get("evidence_level") if provider_revalidation else None,
        },
        "preflight_projection": preflight,
        "execution_blockers": [] if live_execution_ready else _execution_blockers(preflight),
        "supported_claims": [
            "The project has enough no-token artifacts to discuss the formal authorized-live smoke test plan.",
            "The report itself does not contact provider APIs, validate account balance, or generate media.",
        ],
        "forbidden_claims": [
            "Do not claim L4 authorized-live evidence from this report alone.",
            "Do not claim poyo key validity, balance, runtime success, artifact quality, or commercial delivery completion.",
        ],
    }


def main() -> int:
    args = _parse_args()
    try:
        payload = _build_report(args)
        if args.output is None:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        output_path = _validate_private_output(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote no-token authorized-live test-plan readiness report: {_relative(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
