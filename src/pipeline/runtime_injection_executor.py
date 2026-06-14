"""Runtime-safe projection for reviewed commercial injection bundles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.models.commercial_contracts import AllowedUse, BrandConstraintBundle

REVIEWED_BRAND_BUNDLES_CONFIG_KEY = "commercial_reviewed_brand_bundles"
CURRENT_RUNTIME_INJECTION_KEY = "current_runtime_injection"
STEP_RUNTIME_INJECTION_DATA_KEY = "runtime_injection"
RUNTIME_INJECTION_MODE = "reviewed_bundle_runtime_check"
RUNTIME_INJECTION_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


class ReviewedBrandBundleLookup(BaseModel):
    bundle: BrandConstraintBundle | None = None
    errors: list[str] = Field(default_factory=list)


class RuntimeInjectionResult(BaseModel):
    """Sanitized runtime result; token prompt payloads are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    scenario: str
    step: str
    mode: Literal["reviewed_bundle_runtime_check"] = RUNTIME_INJECTION_MODE
    evidence_level: str = RUNTIME_INJECTION_EVIDENCE_LEVEL
    prompt_injection_allowed: bool = False
    brand_bundle_id: str | None = None
    hard_token_ids: list[str] = Field(default_factory=list)
    soft_token_ids: list[str] = Field(default_factory=list)
    source_token_ids: list[str] = Field(default_factory=list)
    bundle_refs: list[str] = Field(default_factory=list)
    toolbox_refs: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    gate_checks: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def build_reviewed_brand_bundles_config_patch(
    bundles: Iterable[BrandConstraintBundle],
) -> dict[str, Any]:
    """Attach reviewed bundles as JSON-safe config without changing provider behavior."""
    return {
        REVIEWED_BRAND_BUNDLES_CONFIG_KEY: [
            bundle.model_dump(mode="json") for bundle in bundles
        ],
    }


def with_reviewed_brand_bundles(
    config: Mapping[str, Any],
    bundles: Iterable[BrandConstraintBundle],
) -> dict[str, Any]:
    return {
        **dict(config),
        **build_reviewed_brand_bundles_config_patch(bundles),
    }


def find_reviewed_brand_bundle(
    *,
    config: Mapping[str, Any],
    scenario: str,
    step: str,
) -> ReviewedBrandBundleLookup:
    """Resolve one reviewed bundle from config; invalid payloads fail closed."""
    raw_payload = config.get(REVIEWED_BRAND_BUNDLES_CONFIG_KEY)
    if raw_payload is None:
        return ReviewedBrandBundleLookup()

    errors: list[str] = []
    for candidate in _iter_bundle_payloads(raw_payload):
        try:
            bundle = (
                candidate
                if isinstance(candidate, BrandConstraintBundle)
                else BrandConstraintBundle.model_validate(candidate)
            )
        except ValidationError:
            errors.append("reviewed brand bundle payload invalid")
            continue

        if bundle.scenario == scenario and bundle.step == step:
            return ReviewedBrandBundleLookup(bundle=bundle, errors=errors)

    return ReviewedBrandBundleLookup(errors=errors)


def build_runtime_injection_result(
    *,
    planned_injection: Mapping[str, Any],
    bundle_lookup: ReviewedBrandBundleLookup,
) -> RuntimeInjectionResult:
    """Build a fail-closed runtime result from a planned step injection."""
    scenario = _required_str(planned_injection, "scenario")
    step = _required_str(planned_injection, "step")
    blocked_reasons = list(dict.fromkeys(bundle_lookup.errors))
    bundle = bundle_lookup.bundle

    if bundle is None:
        blocked_reasons.append("reviewed brand bundle missing")
        return _blocked_result(
            planned_injection=planned_injection,
            scenario=scenario,
            step=step,
            blocked_reasons=blocked_reasons,
        )

    if bundle.scenario != scenario or bundle.step != step:
        blocked_reasons.append("reviewed brand bundle scenario or step mismatch")
        return _blocked_result(
            planned_injection=planned_injection,
            scenario=scenario,
            step=step,
            blocked_reasons=blocked_reasons,
        )

    invalid_token_ids = [
        token.token_id for token in bundle.all_tokens if not token.is_approved_for_bundle()
    ]
    non_generation_token_ids = [
        token.token_id
        for token in bundle.all_tokens
        if AllowedUse.GENERATION not in token.allowed_uses
    ]
    missing_rights_token_ids = [
        token.token_id for token in bundle.all_tokens if not token.rights_ref
    ]

    if invalid_token_ids:
        blocked_reasons.append("reviewed brand bundle contains non-approved tokens")
    if non_generation_token_ids:
        blocked_reasons.append("reviewed brand bundle lacks generation scope")
    if missing_rights_token_ids:
        blocked_reasons.append("reviewed brand bundle lacks rights refs")
    if not bundle.source_token_ids:
        blocked_reasons.append("reviewed brand bundle has no approved tokens")

    if blocked_reasons:
        return _blocked_result(
            planned_injection=planned_injection,
            scenario=scenario,
            step=step,
            blocked_reasons=blocked_reasons,
            brand_bundle_id=bundle.bundle_id,
        )

    return RuntimeInjectionResult(
        scenario=scenario,
        step=step,
        prompt_injection_allowed=True,
        brand_bundle_id=bundle.bundle_id,
        hard_token_ids=[token.token_id for token in bundle.hard_tokens],
        soft_token_ids=[token.token_id for token in bundle.soft_tokens],
        source_token_ids=bundle.source_token_ids,
        bundle_refs=_string_list(planned_injection.get("bundle_refs")),
        toolbox_refs=_string_list(planned_injection.get("toolbox_refs")),
        contract_refs=_string_list(planned_injection.get("contract_refs")),
        gate_checks=_string_list(planned_injection.get("gate_checks")),
        notes=_string_list(planned_injection.get("notes")),
    )


def _blocked_result(
    *,
    planned_injection: Mapping[str, Any],
    scenario: str,
    step: str,
    blocked_reasons: Sequence[str],
    brand_bundle_id: str | None = None,
) -> RuntimeInjectionResult:
    return RuntimeInjectionResult(
        scenario=scenario,
        step=step,
        brand_bundle_id=brand_bundle_id,
        bundle_refs=_string_list(planned_injection.get("bundle_refs")),
        toolbox_refs=_string_list(planned_injection.get("toolbox_refs")),
        contract_refs=_string_list(planned_injection.get("contract_refs")),
        gate_checks=_string_list(planned_injection.get("gate_checks")),
        blocked_reasons=list(dict.fromkeys(blocked_reasons)),
        notes=_string_list(planned_injection.get("notes")),
    )


def _iter_bundle_payloads(raw_payload: Any) -> Iterable[Any]:
    if isinstance(raw_payload, BrandConstraintBundle):
        yield raw_payload
        return
    if isinstance(raw_payload, list | tuple):
        yield from raw_payload
        return
    if isinstance(raw_payload, Mapping):
        if {"bundle_id", "brand_id", "scenario", "step"}.issubset(raw_payload.keys()):
            yield raw_payload
            return
        yield from raw_payload.values()


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"planned injection requires {key}")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
