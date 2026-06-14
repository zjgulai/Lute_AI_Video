from __future__ import annotations

import json

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    LicenseStatus,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.runtime_injection_executor import (
    REVIEWED_BRAND_BUNDLES_CONFIG_KEY,
    RuntimeInjectionResult,
    build_reviewed_brand_bundles_config_patch,
    build_runtime_injection_result,
    find_reviewed_brand_bundle,
    with_reviewed_brand_bundles,
)


def test_runtime_injection_allows_reviewed_generation_bundle_without_payload():
    bundle = _reviewed_bundle("s1", "strategy")
    config = with_reviewed_brand_bundles({}, [bundle])
    planned = _planned_injection("s1", "strategy")

    result = build_runtime_injection_result(
        planned_injection=planned,
        bundle_lookup=find_reviewed_brand_bundle(
            config=config,
            scenario="s1",
            step="strategy",
        ),
    )
    payload = result.model_dump(mode="json")

    assert result.prompt_injection_allowed is True
    assert result.brand_bundle_id == "bundle_s1_strategy"
    assert result.hard_token_ids == ["bat_s1_strategy_hard"]
    assert result.soft_token_ids == ["bat_s1_strategy_soft"]
    assert "payload" not in json.dumps(payload)
    RuntimeInjectionResult.model_validate(payload)


def test_runtime_injection_blocks_missing_reviewed_bundle():
    result = build_runtime_injection_result(
        planned_injection=_planned_injection("s1", "strategy"),
        bundle_lookup=find_reviewed_brand_bundle(
            config={},
            scenario="s1",
            step="strategy",
        ),
    )

    assert result.prompt_injection_allowed is False
    assert result.hard_token_ids == []
    assert result.blocked_reasons == ["reviewed brand bundle missing"]


def test_runtime_injection_blocks_wrong_step_bundle():
    result = build_runtime_injection_result(
        planned_injection=_planned_injection("s1", "strategy"),
        bundle_lookup=find_reviewed_brand_bundle(
            config=with_reviewed_brand_bundles({}, [_reviewed_bundle("s1", "scripts")]),
            scenario="s1",
            step="strategy",
        ),
    )

    assert result.prompt_injection_allowed is False
    assert result.blocked_reasons == ["reviewed brand bundle missing"]


def test_runtime_injection_blocks_unreviewed_or_non_generation_tokens():
    token = _token(
        token_id="bat_review_only",
        scenario="s1",
        step="strategy",
        status=TokenStatus.APPROVED,
        strength=TokenStrength.HARD,
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[],
        review_status="approved",
        rights_ref="rights_fixture",
    )
    bundle = BrandConstraintBundle(
        bundle_id="bundle_s1_strategy_direct",
        brand_id="momcozy",
        scenario="s1",
        step="strategy",
        hard_tokens=[token],
        source_token_ids=[token.token_id],
    )

    result = build_runtime_injection_result(
        planned_injection=_planned_injection("s1", "strategy"),
        bundle_lookup=find_reviewed_brand_bundle(
            config=with_reviewed_brand_bundles({}, [bundle]),
            scenario="s1",
            step="strategy",
        ),
    )

    assert result.prompt_injection_allowed is False
    assert result.hard_token_ids == []
    assert "reviewed brand bundle lacks generation scope" in result.blocked_reasons


def test_reviewed_bundle_config_patch_is_json_safe_and_supports_step_mapping():
    bundle = _reviewed_bundle("s1", "strategy")

    patch = build_reviewed_brand_bundles_config_patch([bundle])
    json.dumps(patch)
    lookup = find_reviewed_brand_bundle(
        config={
            REVIEWED_BRAND_BUNDLES_CONFIG_KEY: {
                "strategy": bundle.model_dump(mode="json"),
            },
        },
        scenario="s1",
        step="strategy",
    )

    assert patch[REVIEWED_BRAND_BUNDLES_CONFIG_KEY][0]["bundle_id"] == "bundle_s1_strategy"
    assert lookup.bundle == bundle


def _planned_injection(scenario: str, step: str) -> dict[str, object]:
    return {
        "scenario": scenario,
        "step": step,
        "hard_token_ids": [f"bat_{scenario}_{step}_hard"],
        "soft_token_ids": [f"bat_{scenario}_{step}_soft"],
        "source_token_ids": [
            f"bat_{scenario}_{step}_hard",
            f"bat_{scenario}_{step}_soft",
        ],
        "bundle_refs": ["BrandConstraintBundle"],
        "toolbox_refs": ["StoryboardToolbox"],
        "contract_refs": ["StrategyBrief"],
        "gate_checks": ["hard_brand_token_pass"],
        "notes": [],
    }


def _reviewed_bundle(scenario: str, step: str) -> BrandConstraintBundle:
    return BrandConstraintBundle.build_approved(
        bundle_id=f"bundle_{scenario}_{step}",
        brand_id="momcozy",
        scenario=scenario,
        step=step,
        tokens=[
            _token(
                token_id=f"bat_{scenario}_{step}_hard",
                scenario=scenario,
                step=step,
                status=TokenStatus.APPROVED,
                strength=TokenStrength.HARD,
                license_status=LicenseStatus.APPROVED,
                allowed_uses=[AllowedUse.GENERATION],
                review_status="approved",
                rights_ref="rights_fixture_hard",
            ),
            _token(
                token_id=f"bat_{scenario}_{step}_soft",
                scenario=scenario,
                step=step,
                status=TokenStatus.APPROVED,
                strength=TokenStrength.SOFT,
                license_status=LicenseStatus.APPROVED,
                allowed_uses=[AllowedUse.GENERATION],
                review_status="approved",
                rights_ref="rights_fixture_soft",
            ),
        ],
    )


def _token(
    *,
    token_id: str,
    scenario: str,
    step: str,
    status: TokenStatus,
    strength: TokenStrength,
    license_status: LicenseStatus,
    allowed_uses: list[AllowedUse],
    review_status: str,
    rights_ref: str | None,
) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=status,
        strength=strength,
        priority=80,
        payload={"raw": "must-not-leak"},
        payload_summary=["sanitized"],
        scenario_scope=[scenario],
        step_scope=[step],
        rights_ref=rights_ref,
        license_status=license_status,
        allowed_uses=allowed_uses,
        review=TokenReview(review_status=review_status),
    )
