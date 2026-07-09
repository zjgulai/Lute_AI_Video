"""No-token preflight gate before any authorized live token smoke."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.commercial_contracts import (
    AuditEvidenceBundle,
    MediaJobSpec,
    PlatformTarget,
    QualityContract,
)
from src.pipeline.production_job_ledger import ProductionJobLedger
from src.pipeline.provider_profiles import ProviderPromptProfile, list_provider_prompt_profiles
from src.quality.commercial_gate import evaluate_quality_contract

RUN_TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
APPROVAL_RECORD_ENV = "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD"
ACCOUNT_READINESS_RECORD_ENV = "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD"
APPROVAL_SCOPE = "c21-token-smoke"
ACCOUNT_READINESS_SCOPE = "c21-token-smoke-provider-account-readiness"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_REVALIDATION_REF = "configs/poyo-current-provider-revalidation-contract.json"
PROVIDER_REVALIDATION_PATH = REPO_ROOT / PROVIDER_REVALIDATION_REF
SAMPLE_PLAN_REF = "configs/authorized-live-token-smoke-sample-plan-contract.json"
SAMPLE_PLAN_PATH = REPO_ROOT / SAMPLE_PLAN_REF
DEFAULT_AUTH_PROVIDER = "poyo"
DEFAULT_AUTH_MODEL = "seedance-2"
DEFAULT_AUTH_PROVIDER_MODEL_SCOPE = "poyo/gpt-image-2 + poyo/seedance-2"
DEFAULT_AUTH_TEST_SCOPE = "Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频"
DEFAULT_AUTH_BUDGET_LIMIT = "$3.00"
DEFAULT_AUTH_BUDGET_LIMIT_USD = 3.0
APPROVAL_STATEMENT_TEMPLATE = (
    "我授权在生产环境 https://video.lute-tlz-dddd.top 使用 poyo image + poyo Seedance "
    "执行 {test_scope}的真实调用 smoke，预算上限 {budget_limit}，自动重试 0，"
    "不发布、不写入正式 brand token，产物只进入待审素材库。"
)
REQUIRED_API_KEY_ENVS = ("POYO_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY")


class PreflightCheck(BaseModel):
    name: str
    status: Literal["pass", "block"]
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)


class TokenSmokePreflightReport(BaseModel):
    report_id: str
    evidence_level: Literal["L2-fixture-or-dry-run"] = "L2-fixture-or-dry-run"
    run_token_smoke: bool
    approval_record_ref: str | None = None
    account_readiness_record_ref: str | None = None
    provider_revalidation_ref: str | None = None
    sample_plan_ref: str | None = None
    approved_provider: str | None = None
    approved_model: str | None = None
    approved_provider_model_scope: str | None = None
    approved_test_scope: str | None = None
    approved_budget_limit_usd: float | None = None
    approved_max_sample_count: int | None = None
    approved_max_provider_calls: int | None = None
    approved_max_total_cost_usd: float | None = None
    approved_per_job_cost_ceiling_usd: float | None = None
    approved_max_retry_count: int | None = None
    provider_call_allowed: bool = False
    blocked: bool = True
    checks: list[PreflightCheck] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def build_token_smoke_preflight_report(
    *,
    env: Mapping[str, str] | None = None,
    approval_record_path: str | Path | None = None,
) -> TokenSmokePreflightReport:
    """Evaluate local readiness without contacting any provider."""
    env = os.environ if env is None else env
    record_path_raw = approval_record_path or env.get(APPROVAL_RECORD_ENV, "")
    record_path = Path(record_path_raw).expanduser() if record_path_raw else None
    account_readiness_path_raw = env.get(ACCOUNT_READINESS_RECORD_ENV, "")
    account_readiness_path = Path(account_readiness_path_raw).expanduser() if account_readiness_path_raw else None
    approval_check, approval_payload = _check_approval_record(record_path)
    checks = [
        _check_run_token_smoke(env),
        *_check_api_keys(env),
        approval_check,
        _check_sample_plan_contract(approval_payload),
        _check_budget_stop_loss(approval_payload),
        _check_provider_account_readiness(account_readiness_path, approval_payload),
        _check_provider_capability_evidence(approval_payload),
        _check_job_ledger_readiness(),
        _check_audit_bundle_readiness(),
    ]
    blocked = any(check.status == "block" for check in checks)

    return TokenSmokePreflightReport(
        report_id=f"token_smoke_preflight_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        run_token_smoke=env.get(RUN_TOKEN_SMOKE_ENV) == "1",
        approval_record_ref=str(record_path) if record_path else None,
        account_readiness_record_ref=str(account_readiness_path) if account_readiness_path else None,
        provider_revalidation_ref=_approval_string(approval_payload, "provider_revalidation_ref"),
        sample_plan_ref=_approval_string(approval_payload, "sample_plan_ref"),
        approved_provider=_approval_string(approval_payload, "provider"),
        approved_model=_approval_string(approval_payload, "model"),
        approved_provider_model_scope=_approval_string(approval_payload, "provider_model_scope"),
        approved_test_scope=_approval_string(approval_payload, "test_scope"),
        approved_budget_limit_usd=_approval_budget_limit_usd(approval_payload),
        approved_max_sample_count=_approval_nested_int(approval_payload, "sample_plan", "max_sample_count"),
        approved_max_provider_calls=_approval_nested_int(approval_payload, "sample_plan", "max_provider_calls"),
        approved_max_total_cost_usd=_approval_nested_float(approval_payload, "budget_stop_loss", "max_total_cost_usd"),
        approved_per_job_cost_ceiling_usd=_approval_nested_float(
            approval_payload,
            "budget_stop_loss",
            "per_job_cost_ceiling_usd",
        ),
        approved_max_retry_count=_approval_nested_int(approval_payload, "budget_stop_loss", "max_retry_count"),
        provider_call_allowed=not blocked,
        blocked=blocked,
        checks=checks,
    )


def build_authorized_live_approval_payload(
    *,
    approved_by: str,
    approval_statement: str,
    approved_at: str | None = None,
    provider: str = DEFAULT_AUTH_PROVIDER,
    model: str = DEFAULT_AUTH_MODEL,
    provider_model_scope: str = DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
    test_scope: str = DEFAULT_AUTH_TEST_SCOPE,
    budget_limit: str = DEFAULT_AUTH_BUDGET_LIMIT,
    budget_limit_usd: float = DEFAULT_AUTH_BUDGET_LIMIT_USD,
) -> dict[str, Any]:
    """Build a private approval record payload without inspecting keys or calling providers."""
    approved_by = approved_by.strip()
    provider = provider.strip()
    model = model.strip()
    provider_model_scope = provider_model_scope.strip()
    test_scope = test_scope.strip()
    budget_limit = budget_limit.strip()
    approved_at = approved_at.strip() if approved_at else _utc_now_z()

    if _looks_like_template_placeholder(approved_by) or _looks_like_template_placeholder(approved_at):
        raise ValueError("approved_by and approved_at must be concrete non-template values")

    budget_value = _positive_finite_number(budget_limit_usd)
    if budget_value is None:
        raise ValueError("budget_limit_usd must be a positive finite number")

    expected_statement = APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=provider_model_scope,
        test_scope=test_scope,
        budget_limit=budget_limit,
    )
    if approval_statement != expected_statement:
        raise ValueError("approval_statement must exactly match the C21 authorization statement")

    contract_error, contract = _load_sample_plan_contract()
    if contract_error or contract is None:
        raise ValueError(contract_error or "sample plan contract is unavailable")
    if not _contract_allows_provider_model(contract, provider, model):
        raise ValueError(f"sample plan contract does not allow {provider}/{model}")
    if _contract_string(contract, "provider_model_scope") != provider_model_scope:
        raise ValueError("provider_model_scope must match the sample plan contract")
    if _contract_string(contract, "test_scope") != test_scope:
        raise ValueError("test_scope must match the sample plan contract")

    limits = contract["limits"]
    max_total_cost = _positive_finite_number(limits.get("max_total_cost_usd"))
    if max_total_cost is None:
        raise ValueError("sample plan contract max_total_cost_usd must be positive")
    if budget_value < max_total_cost:
        raise ValueError("budget_limit_usd must cover the sample plan max_total_cost_usd")

    stop_loss_policy = contract.get("stop_loss_policy")
    if not isinstance(stop_loss_policy, Mapping):
        raise ValueError("sample plan contract requires stop_loss_policy")

    scenarios = _core_sample_scenarios(contract)
    if not scenarios:
        raise ValueError("sample plan contract has no core samples")
    toolbox_tool_ids = _core_toolbox_tool_ids(contract)
    sample_ids = _core_sample_ids(contract)
    asset_package = contract.get("expected_pending_asset_package")

    return {
        "template_only": False,
        "approval_id": _approval_id(approved_by, approved_at, provider, model, budget_limit),
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "provider": provider,
        "model": model,
        "provider_model_scope": provider_model_scope,
        "test_scope": test_scope,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "budget_limit": budget_limit,
        "budget_limit_usd": budget_value,
        "sample_plan": {
            "max_sample_count": int(limits["max_sample_count"]),
            "max_provider_calls": int(limits["max_provider_calls"]),
            "scenarios": scenarios,
            "toolbox_tool_ids": toolbox_tool_ids,
            "sample_ids": sample_ids,
            "asset_package": asset_package if isinstance(asset_package, Mapping) else {},
            "s5_requires_separate_confirmation": True,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": float(limits["max_total_cost_usd"]),
            "per_job_cost_ceiling_usd": float(limits["per_job_cost_ceiling_usd"]),
            "max_retry_count": int(limits["max_retry_count"]),
            "stop_on_first_failure": stop_loss_policy.get("stop_on_first_failure") is True,
            "halt_on_rate_limit": stop_loss_policy.get("halt_on_rate_limit") is True,
            "halt_on_quota_error": stop_loss_policy.get("halt_on_quota_error") is True,
            "halt_on_content_rejection": stop_loss_policy.get("halt_on_content_rejection") is True,
            "halt_on_missing_artifact": stop_loss_policy.get("halt_on_missing_artifact") is True,
        },
        "approval_statement": approval_statement,
        "approval_origin": "operator_supplied_exact_statement",
    }


def build_provider_account_readiness_payload(
    *,
    checked_by: str,
    available_credit_usd: float,
    checked_at: str | None = None,
    provider: str = "poyo",
) -> dict[str, Any]:
    """Build a private provider account readiness record without storing API keys."""
    checked_by = checked_by.strip()
    provider = provider.strip()
    checked_at = checked_at.strip() if checked_at else _utc_now_z()
    if _looks_like_template_placeholder(checked_by) or _looks_like_template_placeholder(checked_at):
        raise ValueError("checked_by and checked_at must be concrete non-template values")

    credit = _positive_finite_number(available_credit_usd)
    if credit is None:
        raise ValueError("available_credit_usd must be a positive finite number")

    contract_error, contract = _load_sample_plan_contract()
    if contract_error or contract is None:
        raise ValueError(contract_error or "sample plan contract is unavailable")
    minimum_required = _positive_finite_number(contract["limits"].get("max_total_cost_usd"))
    if minimum_required is None:
        raise ValueError("sample plan contract max_total_cost_usd must be positive")
    if credit < minimum_required:
        raise ValueError("available_credit_usd must cover the authorized-live sample plan budget")

    return {
        "template_only": False,
        "readiness_id": _account_readiness_id(checked_by, checked_at, provider, credit),
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider": provider,
        "checked_by": checked_by,
        "checked_at": checked_at,
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "available_credit_usd": credit,
        "minimum_required_credit_usd": minimum_required,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "account_readiness_origin": "operator_observed_provider_dashboard",
    }


def _check_run_token_smoke(env: Mapping[str, str]) -> PreflightCheck:
    if env.get(RUN_TOKEN_SMOKE_ENV) == "1":
        return PreflightCheck(
            name="run_token_smoke",
            status="pass",
            detail="RUN_TOKEN_SMOKE=1 is explicitly set",
            evidence_refs=[RUN_TOKEN_SMOKE_ENV],
        )
    return PreflightCheck(
        name="run_token_smoke",
        status="block",
        detail="RUN_TOKEN_SMOKE=1 is required before any authorized live token smoke",
        evidence_refs=[RUN_TOKEN_SMOKE_ENV],
    )


def _check_api_keys(env: Mapping[str, str]) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    for key_name in REQUIRED_API_KEY_ENVS:
        present = bool(env.get(key_name))
        checks.append(PreflightCheck(
            name=f"api_key:{key_name}",
            status="pass" if present else "block",
            detail=f"{key_name} is {'set' if present else 'missing'}; value is not inspected or printed",
            evidence_refs=[key_name],
        ))
    return checks


def _check_approval_record(path: Path | None) -> tuple[PreflightCheck, dict[str, Any] | None]:
    if path is None:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail=f"{APPROVAL_RECORD_ENV} must point to an explicit approval record",
            evidence_refs=[APPROVAL_RECORD_ENV],
        ), None
    if not path.exists():
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record path does not exist",
            evidence_refs=[str(path)],
        ), None
    if not path.is_file():
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record path must be a JSON file",
            evidence_refs=[str(path)],
        ), None

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record must be valid JSON",
            evidence_refs=[str(path)],
        ), None
    if not isinstance(payload, dict):
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record must be a JSON object",
            evidence_refs=[str(path)],
        ), None

    if payload.get("template_only") is True:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record template_only must be false after explicit user approval",
            evidence_refs=[str(path)],
        ), None

    required = {
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
    }
    missing_or_wrong = [key for key, expected in required.items() if payload.get(key) != expected]
    if missing_or_wrong:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail=f"approval record missing required fields: {', '.join(missing_or_wrong)}",
            evidence_refs=[str(path)],
        ), None

    if not payload.get("approved_by") or not payload.get("approved_at"):
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record requires approved_by and approved_at",
            evidence_refs=[str(path)],
        ), None
    if _looks_like_template_placeholder(payload.get("approved_by")) or _looks_like_template_placeholder(payload.get("approved_at")):
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record approved_by and approved_at must be concrete non-template values",
            evidence_refs=[str(path)],
        ), None

    detail_missing = _missing_detail_fields(payload)
    if detail_missing:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail=f"approval record missing live-smoke details: {', '.join(detail_missing)}",
            evidence_refs=[str(path)],
        ), None

    budget_limit_usd = _approval_budget_limit_usd(payload)
    if budget_limit_usd is None or budget_limit_usd <= 0:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record budget_limit_usd must be a positive number",
            evidence_refs=[str(path)],
        ), None

    provider = str(payload["provider"]).strip()
    model = str(payload["model"]).strip()
    provider_model_scope = str(payload["provider_model_scope"]).strip()
    test_scope = str(payload["test_scope"]).strip()
    budget_limit = str(payload["budget_limit"]).strip()
    expected_statement = APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=provider_model_scope,
        test_scope=test_scope,
        budget_limit=budget_limit,
    )
    if payload.get("approval_statement") != expected_statement:
        return PreflightCheck(
            name="authorized_live_approval",
            status="block",
            detail="approval record must include the exact C21 user authorization statement",
            evidence_refs=[str(path)],
        ), None

    return PreflightCheck(
        name="authorized_live_approval",
        status="pass",
        detail="explicit authorized-live approval record is present",
        evidence_refs=[str(path), str(payload.get("approval_id", "")), f"{provider}/{model}", provider_model_scope],
    ), payload


def _check_budget_stop_loss(approval_payload: Mapping[str, Any] | None) -> PreflightCheck:
    if approval_payload is None:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="passing approval record is required before budget stop-loss can be evaluated",
        )

    sample_plan = approval_payload.get("sample_plan")
    if not isinstance(sample_plan, Mapping):
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="approval record requires sample_plan object",
        )
    budget_stop_loss = approval_payload.get("budget_stop_loss")
    if not isinstance(budget_stop_loss, Mapping):
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="approval record requires budget_stop_loss object",
        )

    max_sample_count = _positive_int(sample_plan.get("max_sample_count"))
    max_provider_calls = _positive_int(sample_plan.get("max_provider_calls"))
    max_total_cost_usd = _positive_finite_number(budget_stop_loss.get("max_total_cost_usd"))
    per_job_cost_ceiling_usd = _positive_finite_number(budget_stop_loss.get("per_job_cost_ceiling_usd"))
    max_retry_count = _nonnegative_int(budget_stop_loss.get("max_retry_count"))
    missing = []
    if max_sample_count is None:
        missing.append("sample_plan.max_sample_count")
    if max_provider_calls is None:
        missing.append("sample_plan.max_provider_calls")
    if max_total_cost_usd is None:
        missing.append("budget_stop_loss.max_total_cost_usd")
    if per_job_cost_ceiling_usd is None:
        missing.append("budget_stop_loss.per_job_cost_ceiling_usd")
    if max_retry_count is None:
        missing.append("budget_stop_loss.max_retry_count")
    if missing:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail=f"approval record missing positive budget stop-loss fields: {', '.join(missing)}",
        )

    budget_limit_usd = _approval_budget_limit_usd(approval_payload)
    if budget_limit_usd is None or max_total_cost_usd > budget_limit_usd:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="budget_stop_loss.max_total_cost_usd must not exceed budget_limit_usd",
        )
    if per_job_cost_ceiling_usd > max_total_cost_usd:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="budget_stop_loss.per_job_cost_ceiling_usd must not exceed max_total_cost_usd",
        )
    if max_provider_calls < max_sample_count:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="sample_plan.max_provider_calls must cover sample_plan.max_sample_count",
        )
    if max_retry_count > 1:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail="budget_stop_loss.max_retry_count must be 0 or 1 for tiny token smoke",
        )

    boolean_requirements = [
        "stop_on_first_failure",
        "halt_on_rate_limit",
        "halt_on_quota_error",
        "halt_on_content_rejection",
        "halt_on_missing_artifact",
    ]
    disabled = [key for key in boolean_requirements if budget_stop_loss.get(key) is not True]
    if disabled:
        return PreflightCheck(
            name="budget_stop_loss",
            status="block",
            detail=f"budget stop-loss must explicitly enable: {', '.join(disabled)}",
        )

    return PreflightCheck(
        name="budget_stop_loss",
        status="pass",
        detail=(
            "budget stop-loss is explicit: "
            f"samples<={max_sample_count}, provider_calls<={max_provider_calls}, "
            f"total<=${max_total_cost_usd:.2f}, per_job<=${per_job_cost_ceiling_usd:.2f}, "
            f"retries<={max_retry_count}"
        ),
        evidence_refs=["sample_plan", "budget_stop_loss"],
    )


def _check_sample_plan_contract(approval_payload: Mapping[str, Any] | None) -> PreflightCheck:
    if approval_payload is None:
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail="passing approval record is required before sample plan can be evaluated",
        )

    sample_plan_ref = _approval_string(approval_payload, "sample_plan_ref")
    if sample_plan_ref is None:
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail="approval record requires sample_plan_ref before authorized-live provider calls",
        )
    if sample_plan_ref != SAMPLE_PLAN_REF:
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail=f"sample_plan_ref must equal {SAMPLE_PLAN_REF}",
            evidence_refs=[sample_plan_ref],
        )

    contract_error, contract = _load_sample_plan_contract()
    if contract_error or contract is None:
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail=contract_error or "sample plan contract is unavailable",
            evidence_refs=[SAMPLE_PLAN_REF],
        )

    sample_plan = approval_payload.get("sample_plan")
    if not isinstance(sample_plan, Mapping):
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail="approval record requires sample_plan object",
            evidence_refs=[SAMPLE_PLAN_REF],
        )
    budget_stop_loss = approval_payload.get("budget_stop_loss")
    if not isinstance(budget_stop_loss, Mapping):
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail="approval record requires budget_stop_loss object",
            evidence_refs=[SAMPLE_PLAN_REF],
        )

    provider = _approval_string(approval_payload, "provider")
    model = _approval_string(approval_payload, "model")
    if not _contract_allows_provider_model(contract, provider, model):
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail=f"sample plan contract does not allow {provider}/{model}",
            evidence_refs=[SAMPLE_PLAN_REF],
        )

    contract_limits = contract["limits"]
    violations = [
        *_sample_plan_binding_violations(approval_payload, contract),
        *_sample_plan_limit_violations(sample_plan, budget_stop_loss, contract_limits),
    ]
    scenario_violations = _sample_plan_scope_violations(sample_plan, contract)
    if violations or scenario_violations:
        return PreflightCheck(
            name="sample_plan_contract",
            status="block",
            detail="; ".join([*violations, *scenario_violations]),
            evidence_refs=[SAMPLE_PLAN_REF],
        )

    return PreflightCheck(
        name="sample_plan_contract",
        status="pass",
        detail=f"authorized-live sample plan is bound to {SAMPLE_PLAN_REF}",
        evidence_refs=[SAMPLE_PLAN_REF, PROVIDER_REVALIDATION_REF],
    )


def _check_provider_account_readiness(
    path: Path | None,
    approval_payload: Mapping[str, Any] | None,
) -> PreflightCheck:
    if approval_payload is None:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="passing approval record is required before provider account readiness can be evaluated",
        )
    if path is None:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail=f"{ACCOUNT_READINESS_RECORD_ENV} must point to a private provider account readiness record",
            evidence_refs=[ACCOUNT_READINESS_RECORD_ENV],
        )
    if not path.exists():
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness record path does not exist",
            evidence_refs=[str(path)],
        )
    if not path.is_file():
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness record path must be a JSON file",
            evidence_refs=[str(path)],
        )

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness record must be valid JSON",
            evidence_refs=[str(path)],
        )
    if not isinstance(payload, Mapping):
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness record must be a JSON object",
            evidence_refs=[str(path)],
        )
    if payload.get("template_only") is True:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness template_only must be false after manual dashboard check",
            evidence_refs=[str(path)],
        )

    expected = {
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
    }
    missing_or_wrong = [key for key, value in expected.items() if payload.get(key) != value]
    if missing_or_wrong:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail=f"provider account readiness record missing required fields: {', '.join(missing_or_wrong)}",
            evidence_refs=[str(path)],
        )

    provider = _approval_string(approval_payload, "provider")
    if _approval_string(payload, "provider") != provider:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail=f"provider account readiness record must match approved provider {provider}",
            evidence_refs=[str(path)],
        )

    if _looks_like_template_placeholder(payload.get("checked_by")) or _looks_like_template_placeholder(payload.get("checked_at")):
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness requires concrete checked_by and checked_at",
            evidence_refs=[str(path)],
        )

    available_credit = _positive_finite_number(payload.get("available_credit_usd"))
    required_credit = _positive_finite_number(payload.get("minimum_required_credit_usd"))
    approved_max_total = _approval_nested_float(approval_payload, "budget_stop_loss", "max_total_cost_usd")
    if available_credit is None or required_credit is None or approved_max_total is None:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness requires positive credit fields and approved max total cost",
            evidence_refs=[str(path)],
        )
    if available_credit < required_credit or available_credit < approved_max_total:
        return PreflightCheck(
            name="provider_account_readiness",
            status="block",
            detail="provider account readiness available_credit_usd must cover required and approved smoke budget",
            evidence_refs=[str(path)],
        )

    return PreflightCheck(
        name="provider_account_readiness",
        status="pass",
        detail=f"provider account readiness is manually confirmed for {provider} with no API key recorded",
        evidence_refs=[str(path), str(payload.get("readiness_id", "")), ACCOUNT_READINESS_RECORD_ENV],
    )


def _check_provider_capability_evidence(approval_payload: Mapping[str, Any] | None) -> PreflightCheck:
    profiles = list_provider_prompt_profiles()
    provider = _approval_string(approval_payload, "provider")
    model = _approval_string(approval_payload, "model")
    provider_model_scope = _approval_string(approval_payload, "provider_model_scope")
    revalidation_ref = _approval_string(approval_payload, "provider_revalidation_ref")
    if provider is None or model is None:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail="passing approval record with provider/model is required before capability evidence can be bound",
        )

    if revalidation_ref is None:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail="approval record requires provider_revalidation_ref before authorized-live provider calls",
        )
    if revalidation_ref != PROVIDER_REVALIDATION_REF:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=f"provider_revalidation_ref must equal {PROVIDER_REVALIDATION_REF}",
            evidence_refs=[revalidation_ref],
        )

    contract_error, contract = _load_provider_revalidation_contract()
    if contract_error or contract is None:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=contract_error or "provider revalidation contract is unavailable",
            evidence_refs=[PROVIDER_REVALIDATION_REF],
        )
    if str(contract.get("provider", "")).lower() != provider.lower():
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=f"provider revalidation contract is for {contract.get('provider')}, not {provider}/{model}",
            evidence_refs=[PROVIDER_REVALIDATION_REF],
        )
    if not _contract_supports_model(contract, model):
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=f"provider revalidation contract does not list {provider}/{model}",
            evidence_refs=[PROVIDER_REVALIDATION_REF],
        )

    sample_plan_error, sample_plan_contract = _load_sample_plan_contract()
    if sample_plan_error or sample_plan_contract is None:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=sample_plan_error or "sample plan contract is unavailable",
            evidence_refs=[SAMPLE_PLAN_REF],
        )
    unsupported_required_models = [
        f"{item['provider']}/{item['model']}"
        for item in _contract_required_provider_models(sample_plan_contract)
        if str(item["provider"]).lower() != provider.lower() or not _contract_supports_model(contract, str(item["model"]))
    ]
    if unsupported_required_models:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="block",
            detail=(
                "provider revalidation contract does not cover required sample plan models: "
                + ", ".join(unsupported_required_models)
            ),
            evidence_refs=[PROVIDER_REVALIDATION_REF, SAMPLE_PLAN_REF],
        )

    profile = _match_provider_profile(profiles, provider, model)
    if profile is not None:
        return PreflightCheck(
            name="provider_capability_evidence",
            status="pass",
            detail=(
                f"fixture provider profile is bound for primary {provider}/{model}; "
                f"public-doc revalidation covers {provider_model_scope or f'{provider}/{model}'}"
            ),
            evidence_refs=[
                profile.profile_id,
                PROVIDER_REVALIDATION_REF,
                SAMPLE_PLAN_REF,
                *[str(url) for url in contract.get("source_urls", [])],
            ],
        )
    return PreflightCheck(
        name="provider_capability_evidence",
        status="block",
        detail=f"no fixture provider prompt profile is registered for {provider}/{model}",
    )


def _missing_detail_fields(payload: Mapping[str, Any]) -> list[str]:
    required = [
        "provider",
        "model",
        "provider_model_scope",
        "test_scope",
        "provider_revalidation_ref",
        "sample_plan_ref",
        "budget_limit",
        "budget_limit_usd",
        "approval_statement",
    ]
    return [key for key in required if not str(payload.get(key, "")).strip()]


def _load_provider_revalidation_contract() -> tuple[str | None, dict[str, Any] | None]:
    if not PROVIDER_REVALIDATION_PATH.exists():
        return "provider revalidation contract is missing", None
    try:
        payload = json.loads(PROVIDER_REVALIDATION_PATH.read_text())
    except json.JSONDecodeError:
        return "provider revalidation contract must be valid JSON", None
    if not isinstance(payload, dict):
        return "provider revalidation contract must be a JSON object", None
    if payload.get("status") != "stable":
        return "provider revalidation contract must be stable", None
    if payload.get("no_provider_call") is not True:
        return "provider revalidation contract must preserve the no-provider-call boundary", None
    if payload.get("evidence_level") != "L1-public-doc-revalidation":
        return "provider revalidation contract must stay labeled as public-doc evidence", None
    if not isinstance(payload.get("models"), list) or not payload["models"]:
        return "provider revalidation contract requires model entries", None
    return None, payload


def _load_sample_plan_contract() -> tuple[str | None, dict[str, Any] | None]:
    if not SAMPLE_PLAN_PATH.exists():
        return "sample plan contract is missing", None
    try:
        payload = json.loads(SAMPLE_PLAN_PATH.read_text())
    except json.JSONDecodeError:
        return "sample plan contract must be valid JSON", None
    if not isinstance(payload, dict):
        return "sample plan contract must be a JSON object", None
    if payload.get("status") != "stable":
        return "sample plan contract must be stable", None
    if payload.get("no_provider_call") is not True:
        return "sample plan contract must preserve the no-provider-call boundary", None
    if payload.get("evidence_level") != "L2-fixture-or-dry-run":
        return "sample plan contract must stay labeled as fixture/dry-run evidence", None
    if payload.get("provider_revalidation_ref") != PROVIDER_REVALIDATION_REF:
        return "sample plan contract must bind the current provider revalidation ref", None
    if payload.get("approval_scope") != APPROVAL_SCOPE:
        return "sample plan contract must bind the C21 approval scope", None
    if not isinstance(payload.get("limits"), Mapping):
        return "sample plan contract requires limits object", None
    return None, payload


def _contract_allows_provider_model(contract: Mapping[str, Any], provider: str | None, model: str | None) -> bool:
    if provider is None or model is None:
        return False
    provider_key = provider.lower()
    model_key = model.lower()
    for item in contract.get("allowed_provider_models", []):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("provider", "")).lower() == provider_key and str(item.get("model", "")).lower() == model_key:
            return True
    return False


def _contract_string(contract: Mapping[str, Any], key: str) -> str | None:
    value = str(contract.get(key, "")).strip()
    return value or None


def _contract_required_provider_models(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    required: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in contract.get("required_provider_models", contract.get("allowed_provider_models", [])):
        if not isinstance(item, Mapping):
            continue
        provider = str(item.get("provider", "")).strip()
        model = str(item.get("model", "")).strip()
        if not provider or not model:
            continue
        key = (provider.lower(), model.lower())
        if key in seen:
            continue
        required.append({"provider": provider, "model": model})
        seen.add(key)
    return required


def _sample_plan_binding_violations(
    approval_payload: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> list[str]:
    violations = []
    expected_provider_model_scope = _contract_string(contract, "provider_model_scope")
    expected_test_scope = _contract_string(contract, "test_scope")
    if expected_provider_model_scope and _approval_string(approval_payload, "provider_model_scope") != expected_provider_model_scope:
        violations.append("approval record provider_model_scope must match sample plan contract")
    if expected_test_scope and _approval_string(approval_payload, "test_scope") != expected_test_scope:
        violations.append("approval record test_scope must match sample plan contract")
    for item in _contract_required_provider_models(contract):
        if not _contract_allows_provider_model(contract, item["provider"], item["model"]):
            violations.append(f"sample plan required model is not allowed: {item['provider']}/{item['model']}")
    return violations


def _sample_plan_limit_violations(
    sample_plan: Mapping[str, Any],
    budget_stop_loss: Mapping[str, Any],
    contract_limits: Mapping[str, Any],
) -> list[str]:
    checks = [
        ("sample_plan.max_sample_count", sample_plan.get("max_sample_count"), contract_limits.get("max_sample_count")),
        (
            "sample_plan.max_provider_calls",
            sample_plan.get("max_provider_calls"),
            contract_limits.get("max_provider_calls"),
        ),
        (
            "budget_stop_loss.max_total_cost_usd",
            budget_stop_loss.get("max_total_cost_usd"),
            contract_limits.get("max_total_cost_usd"),
        ),
        (
            "budget_stop_loss.per_job_cost_ceiling_usd",
            budget_stop_loss.get("per_job_cost_ceiling_usd"),
            contract_limits.get("per_job_cost_ceiling_usd"),
        ),
        (
            "budget_stop_loss.max_retry_count",
            budget_stop_loss.get("max_retry_count"),
            contract_limits.get("max_retry_count"),
        ),
    ]
    violations = []
    for label, actual_raw, ceiling_raw in checks:
        actual = _nonnegative_float(actual_raw)
        ceiling = _nonnegative_float(ceiling_raw)
        if actual is None or ceiling is None or actual > ceiling:
            violations.append(f"{label} must be <= {ceiling_raw}")
    return violations


def _sample_plan_scope_violations(sample_plan: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    allowed_scenarios = {str(value) for value in contract.get("allowed_scenarios", [])}
    scenarios = [str(value) for value in sample_plan.get("scenarios", [])]
    invalid_scenarios = [value for value in scenarios if value not in allowed_scenarios]
    violations = []
    if not scenarios:
        violations.append("sample_plan.scenarios must not be empty")
    if invalid_scenarios:
        violations.append(f"sample_plan.scenarios contains unsupported values: {', '.join(invalid_scenarios)}")

    allowed_tool_ids = {str(value) for value in contract.get("allowed_toolbox_tool_ids", [])}
    toolbox_tool_ids = [str(value) for value in sample_plan.get("toolbox_tool_ids", [])]
    invalid_tool_ids = [value for value in toolbox_tool_ids if value not in allowed_tool_ids]
    if invalid_tool_ids:
        violations.append(f"sample_plan.toolbox_tool_ids contains unsupported values: {', '.join(invalid_tool_ids)}")

    allowed_sample_ids = set(_core_sample_ids(contract))
    sample_ids = [str(value) for value in sample_plan.get("sample_ids", [])]
    invalid_sample_ids = [value for value in sample_ids if value not in allowed_sample_ids]
    if not sample_ids:
        violations.append("sample_plan.sample_ids must not be empty")
    if invalid_sample_ids:
        violations.append(f"sample_plan.sample_ids contains unsupported values: {', '.join(invalid_sample_ids)}")

    expected_asset_package = contract.get("expected_pending_asset_package")
    if isinstance(expected_asset_package, Mapping):
        asset_package = sample_plan.get("asset_package")
        if not isinstance(asset_package, Mapping):
            violations.append("sample_plan.asset_package must be present for this sample plan")
        else:
            for key, expected in expected_asset_package.items():
                if asset_package.get(key) != expected:
                    violations.append(f"sample_plan.asset_package.{key} must equal {expected}")
    return violations


def _iter_core_samples(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    samples: list[Mapping[str, Any]] = []
    for section in ("core_asset_samples", "core_video_samples"):
        for sample in contract.get(section, []):
            if isinstance(sample, Mapping):
                samples.append(sample)
    return samples


def _core_sample_scenarios(contract: Mapping[str, Any]) -> list[str]:
    scenarios = []
    seen = set()
    for sample in _iter_core_samples(contract):
        scenario = str(sample.get("scenario", "")).strip()
        if scenario and scenario not in seen:
            scenarios.append(scenario)
            seen.add(scenario)
    return scenarios


def _core_toolbox_tool_ids(contract: Mapping[str, Any]) -> list[str]:
    tool_ids = []
    seen = set()
    for sample in _iter_core_samples(contract):
        tool_id = str(sample.get("tool_id", "")).strip()
        if tool_id and tool_id not in seen:
            tool_ids.append(tool_id)
            seen.add(tool_id)
    return tool_ids


def _core_sample_ids(contract: Mapping[str, Any]) -> list[str]:
    sample_ids = []
    seen = set()
    for sample in _iter_core_samples(contract):
        sample_id = str(sample.get("sample_id", "")).strip()
        if sample_id and sample_id not in seen:
            sample_ids.append(sample_id)
            seen.add(sample_id)
    return sample_ids


def _contract_supports_model(contract: Mapping[str, Any], model: str) -> bool:
    model_key = model.lower()
    for item in contract.get("models", []):
        if not isinstance(item, Mapping):
            continue
        listed = {str(item.get("model", "")).lower()}
        listed.update(str(value).lower() for value in item.get("available_model_ids", []) if value)
        if model_key in listed:
            return True
    return False


def _looks_like_template_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized.startswith("<")
        or "replace_me" in normalized
        or "example" in normalized
    )


def _utc_now_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _approval_budget_limit_usd(payload: Mapping[str, Any] | None) -> float | None:
    if payload is None:
        return None
    try:
        value = float(payload.get("budget_limit_usd"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _approval_string(payload: Mapping[str, Any] | None, key: str) -> str | None:
    if payload is None:
        return None
    value = str(payload.get(key, "")).strip()
    return value or None


def _approval_nested_int(payload: Mapping[str, Any] | None, section: str, key: str) -> int | None:
    if payload is None or not isinstance(payload.get(section), Mapping):
        return None
    return _nonnegative_int(payload[section].get(key))


def _approval_nested_float(payload: Mapping[str, Any] | None, section: str, key: str) -> float | None:
    if payload is None or not isinstance(payload.get(section), Mapping):
        return None
    return _positive_finite_number(payload[section].get(key))


def _positive_int(value: Any) -> int | None:
    parsed = _nonnegative_int(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive_finite_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _nonnegative_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _match_provider_profile(
    profiles: list[ProviderPromptProfile],
    provider: str,
    model: str,
) -> ProviderPromptProfile | None:
    provider_key = provider.lower()
    model_key = model.lower()
    for profile in profiles:
        if profile.provider.lower() == provider_key and profile.model_family.lower() in model_key:
            return profile
    return None


def _approval_id(approved_by: str, approved_at: str, provider: str, model: str, budget_limit: str) -> str:
    digest = hashlib.sha256(
        f"{approved_by}|{approved_at}|{provider}|{model}|{budget_limit}".encode(),
    ).hexdigest()[:12]
    return f"c21-token-smoke-approval-{digest}"


def _account_readiness_id(checked_by: str, checked_at: str, provider: str, available_credit_usd: float) -> str:
    digest = hashlib.sha256(
        f"{checked_by}|{checked_at}|{provider}|{available_credit_usd:.2f}".encode(),
    ).hexdigest()[:12]
    return f"c21-token-smoke-account-readiness-{digest}"


def _check_job_ledger_readiness() -> PreflightCheck:
    ledger = ProductionJobLedger()
    spec = MediaJobSpec(
        job_id="preflight_job_fixture",
        provider="poyo",
        model="seedance-2",
        scenario="s1",
        step_name="video_prompts",
        prompt_hash="sha256:preflight_fixture",
        prompt_compile_id="pci_preflight_fixture",
        brand_bundle_id="bundle_preflight_fixture",
    )
    record = ledger.prepare(spec)
    if record.publish_allowed or record.delivery_accepted:
        return PreflightCheck(
            name="job_ledger_readiness",
            status="block",
            detail="job ledger must not mark prepared jobs as delivered or publishable",
            evidence_refs=[record.job_id],
        )
    return PreflightCheck(
        name="job_ledger_readiness",
        status="pass",
        detail="fixture production job ledger separates prepared job from delivery acceptance",
        evidence_refs=[record.job_id],
    )


def _check_audit_bundle_readiness() -> PreflightCheck:
    contract = QualityContract(
        contract_id="qc_preflight_fixture",
        scenario="s1",
        stage="final_video",
        platform="tiktok",
        brand_id="momcozy",
        blocking_checks=["rights_pass", "claim_substantiation_pass", "media_file_exists"],
        required_evidence=["rights_evidence_refs", "claim_evidence_refs", "artifact_manifest_id"],
    )
    evidence = AuditEvidenceBundle(
        evidence_bundle_id="aeb_preflight_fixture",
        scenario="s1",
        stage="final_video",
        brand_bundle_id="bundle_preflight_fixture",
        source_token_ids=["bat_preflight_fixture"],
        media_job_ids=["preflight_job_fixture"],
        prompt_hashes=["sha256:preflight_fixture"],
        artifact_manifest_id="artifact_preflight_fixture",
        artifact_paths={"final_video": "fixture://final.mp4"},
        rights_evidence_refs=["rights_preflight_fixture"],
        claim_evidence_refs=["claim_preflight_fixture"],
        platform_target=PlatformTarget(platform="tiktok"),
    )
    result = evaluate_quality_contract(contract, evidence)
    if not result.blocking.passed or result.delivery.publish_allowed:
        return PreflightCheck(
            name="audit_bundle_readiness",
            status="block",
            detail="fixture audit bundle is not ready or incorrectly allows publishing",
            evidence_refs=[result.audit_id],
        )
    return PreflightCheck(
        name="audit_bundle_readiness",
        status="pass",
        detail="fixture audit bundle passes blocking checks while publishing remains locked",
        evidence_refs=[result.audit_id, result.gate_decision.decision_id],
    )
