"""W1-28 frozen provider price catalog and integer arithmetic."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

CHECKED_AT = datetime(2026, 7, 15, 17, 1, 24, tzinfo=UTC)


def _load_default():
    from src.services.provider_price_catalog import ProviderPriceCatalog

    return ProviderPriceCatalog.load_default()


def _selector(**overrides: object) -> dict[str, object]:
    selector: dict[str, object] = {
        "provider": "deepseek",
        "canonical_model": "deepseek-v4-flash",
        "provider_billing_region": "deepseek_global_usd",
        "catalog_operation": "chat_completion",
        "media_type": "text",
        "billing_fact_kind": "llm_tokens.v1",
        "dimensions": {},
    }
    selector.update(overrides)
    return selector


def test_default_catalog_identity_window_and_rule_count_are_frozen() -> None:
    catalog = _load_default()

    assert catalog.catalog_id == "provider-cost-catalog.2026-07-15.v1"
    assert catalog.checked_at_utc == CHECKED_AT
    assert len(catalog.rules) == 22
    assert all(rule.effective_from_utc == CHECKED_AT for rule in catalog.rules)
    assert all(rule.effective_to_utc is None for rule in catalog.rules)


def test_deepseek_rules_and_model_envelopes_are_exact() -> None:
    catalog = _load_default()
    expected = {
        "deepseek-v4-flash": (2_800_000, 140_000_000, 280_000_000),
        "deepseek-v4-pro": (3_625_000, 435_000_000, 870_000_000),
    }

    for model, prices in expected.items():
        rule = catalog.require_rule(
            **_selector(canonical_model=model),
            at=CHECKED_AT,
        )
        assert tuple(component.unit_price_usd_nanos for component in rule.components) == prices
        assert tuple(component.quantity_field for component in rule.components) == (
            "input_cache_hit_tokens",
            "input_cache_miss_tokens",
            "output_tokens",
        )
        assert all(component.unit_size == 1_000_000 for component in rule.components)

        contract = catalog.require_model_contract("deepseek", model)
        assert contract.context_window_tokens == 1_000_000
        assert contract.provider_max_output_tokens == 384_000
        assert contract.application_max_output_tokens == 4_096
        assert contract.input_reservation_ceiling_tokens == 995_904


def test_siliconflow_tts_rule_is_exact_utf8_byte_pricing() -> None:
    catalog = _load_default()
    rule = catalog.require_rule(
        **_selector(
            provider="siliconflow",
            canonical_model="FunAudioLLM/CosyVoice2-0.5B",
            provider_billing_region="siliconflow_global_usd",
            catalog_operation="speech_synthesis",
            media_type="audio",
            billing_fact_kind="tts_utf8_bytes.v1",
        ),
        at=CHECKED_AT,
    )
    assert len(rule.components) == 1
    assert rule.components[0].quantity_field == "input_utf8_bytes"
    assert rule.components[0].unit_price_usd_nanos == 7_150_000_000
    assert rule.components[0].unit_size == 1_000_000


def test_poyo_gpt_image_matrix_is_exact() -> None:
    catalog = _load_default()
    expected = {
        ("low", "1K"): (10_000_000, 2_000_000),
        ("low", "2K"): (20_000_000, 4_000_000),
        ("low", "4K"): (40_000_000, 8_000_000),
        ("medium", "1K"): (42_400_000, 8_480_000),
        ("medium", "2K"): (44_800_000, 8_960_000),
        ("medium", "4K"): (80_800_000, 16_160_000),
        ("high", "1K"): (168_800_000, 33_760_000),
        ("high", "2K"): (177_600_000, 35_520_000),
        ("high", "4K"): (320_800_000, 64_160_000),
    }
    for (quality, resolution), (usd_nanos, microcredits) in expected.items():
        rule = catalog.require_rule(
            **_selector(
                provider="poyo",
                canonical_model="gpt-image-2",
                provider_billing_region="poyo_global_usd",
                catalog_operation="image_generation",
                media_type="image",
                billing_fact_kind="image_count.v1",
                dimensions={"quality": quality, "effective_resolution": resolution},
            ),
            at=CHECKED_AT,
        )
        assert rule.components[0].unit_price_usd_nanos == usd_nanos
        assert rule.components[0].provider_credit_micro_units_per_unit == microcredits
        assert rule.components[0].unit_size == 1


def test_poyo_seedance_no_video_input_matrix_is_exact_for_both_operations() -> None:
    catalog = _load_default()
    expected = {
        ("seedance-2", "480p"): (100_000_000, 20_000_000),
        ("seedance-2", "720p"): (200_000_000, 40_000_000),
        ("seedance-2", "1080p"): (450_000_000, 90_000_000),
        ("seedance-2-fast", "480p"): (70_000_000, 14_000_000),
        ("seedance-2-fast", "720p"): (140_000_000, 28_000_000),
    }
    for operation in ("text_to_video", "image_to_video"):
        for (model, resolution), (usd_nanos, microcredits) in expected.items():
            rule = catalog.require_rule(
                **_selector(
                    provider="poyo",
                    canonical_model=model,
                    provider_billing_region="poyo_global_usd",
                    catalog_operation=operation,
                    media_type="video",
                    billing_fact_kind="video_duration.v1",
                    dimensions={
                        "resolution": resolution,
                        "reference_input_kind": (
                            "none" if operation == "text_to_video" else "image"
                        ),
                    },
                ),
                at=CHECKED_AT,
            )
            assert rule.components[0].unit_price_usd_nanos == usd_nanos
            assert rule.components[0].provider_credit_micro_units_per_unit == microcredits
            assert rule.components[0].unit_size == 1_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"canonical_model": "deepseek-chat"},
        {"canonical_model": "*"},
        {"provider": "openai"},
        {"provider_billing_region": "custom"},
        {"catalog_operation": "fast.script.primary"},
        {"billing_fact_kind": "llm_tokens.v0"},
        {"dimensions": {"wildcard": "*"}},
    ],
)
def test_lookup_has_no_alias_wildcard_or_default_fallback(
    overrides: dict[str, object],
) -> None:
    from src.models.provider_cost import ProviderCostContractError

    catalog = _load_default()
    with pytest.raises(ProviderCostContractError) as exc_info:
        catalog.require_rule(**_selector(**overrides), at=CHECKED_AT)
    assert exc_info.value.code == "provider_cost_rule_unavailable"


def test_rule_is_unavailable_outside_its_declared_window() -> None:
    from src.models.provider_cost import ProviderCostContractError

    catalog = _load_default()
    with pytest.raises(ProviderCostContractError):
        catalog.require_rule(**_selector(), at=CHECKED_AT - timedelta(microseconds=1))


def test_component_arithmetic_uses_independent_ceil_and_sum() -> None:
    from src.models.provider_cost import LLMTokensBillingFacts

    catalog = _load_default()
    rule = catalog.require_rule(**_selector(), at=CHECKED_AT)
    facts = LLMTokensBillingFacts(
        schema_version="llm_tokens.v1",
        input_tokens=2,
        input_cache_hit_tokens=1,
        input_cache_miss_tokens=1,
        output_tokens=1,
        total_tokens=3,
    )
    assert catalog.calculate_cost_usd_nanos(rule, facts) == 423


def test_seedance_cost_and_expected_microcredits_share_exact_quantity() -> None:
    from src.models.provider_cost import VideoDurationBillingFacts

    catalog = _load_default()
    rule = catalog.require_rule(
        **_selector(
            provider="poyo",
            canonical_model="seedance-2",
            provider_billing_region="poyo_global_usd",
            catalog_operation="text_to_video",
            media_type="video",
            billing_fact_kind="video_duration.v1",
            dimensions={"resolution": "720p", "reference_input_kind": "none"},
        ),
        at=CHECKED_AT,
    )
    facts = VideoDurationBillingFacts(
        schema_version="video_duration.v1",
        task_count=1,
        duration_ms=5_000,
    )
    assert catalog.calculate_cost_usd_nanos(rule, facts) == 1_000_000_000
    assert catalog.calculate_expected_provider_credit_micro_units(rule, facts) == 200_000_000


def test_arithmetic_rejects_kind_mismatch_overflow_and_credit_remainder() -> None:
    from src.models.provider_cost import (
        ImageCountBillingFacts,
        LLMTokensBillingFacts,
        ProviderCostContractError,
    )
    from src.services.provider_price_catalog import PriceComponent, PriceRule

    catalog = _load_default()
    deepseek = catalog.require_rule(**_selector(), at=CHECKED_AT)

    with pytest.raises(ProviderCostContractError):
        catalog.calculate_cost_usd_nanos(
            deepseek,
            ImageCountBillingFacts(schema_version="image_count.v1", image_count=1),
        )
    with pytest.raises(ProviderCostContractError):
        catalog.calculate_cost_usd_nanos(
            deepseek,
            LLMTokensBillingFacts(
                schema_version="llm_tokens.v1",
                input_tokens=2**63 - 1,
                input_cache_hit_tokens=0,
                input_cache_miss_tokens=2**63 - 1,
                output_tokens=0,
                total_tokens=2**63 - 1,
            ),
        )

    bad_component = PriceComponent(
        component_name="duration",
        quantity_field="duration_ms",
        unit_price_usd_nanos=1,
        unit_size=3,
        provider_credit_micro_units_per_unit=1,
    )
    bad_rule = PriceRule.model_validate(
        {
            **catalog.rules[-1].model_dump(mode="python"),
            "price_rule_id": "fixture.credit-remainder.v1",
            "components": [bad_component.model_dump(mode="python")],
        }
    )
    with pytest.raises(ProviderCostContractError):
        catalog.calculate_expected_provider_credit_micro_units(
            bad_rule,
            ImageCountBillingFacts(schema_version="image_count.v1", image_count=1),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update({"catalog_id": "*"}),
        lambda data: data.update({"unknown": True}),
        lambda data: data["rules"][0].update({"catalog_operation": "*"}),
        lambda data: data["rules"][0].update({"effective_from_utc": "2026-07-15T03:34:02Z"}),
        lambda data: data["rules"][0]["components"][0].update({"unit_size": 1.0}),
        lambda data: data["rules"][0]["components"][0].update({"unit_price_usd_nanos": True}),
        lambda data: data["rules"][0]["components"].append(
            dict(data["rules"][0]["components"][0])
        ),
        lambda data: data["model_contracts"][0].update(
            {"input_reservation_ceiling_tokens": 995_905}
        ),
    ],
)
def test_loader_rejects_malformed_drift_unknown_float_and_duplicates(
    tmp_path: Path,
    mutation,
) -> None:
    from src.services.provider_price_catalog import load_provider_price_catalog

    source = json.loads(Path("configs/provider-cost-catalog.v1.json").read_text())
    mutation(source)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises((ValueError, ValidationError)):
        load_provider_price_catalog(path)


def test_loader_rejects_malformed_json_nan_and_duplicate_selector(tmp_path: Path) -> None:
    from src.services.provider_price_catalog import load_provider_price_catalog

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        load_provider_price_catalog(malformed)

    nan = tmp_path / "nan.json"
    nan.write_text('{"catalog_id": NaN}', encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        load_provider_price_catalog(nan)

    source = json.loads(Path("configs/provider-cost-catalog.v1.json").read_text())
    source["rules"].append(dict(source["rules"][0]))
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises((ValueError, ValidationError), match="duplicate"):
        load_provider_price_catalog(duplicate)


def test_loaded_rules_are_frozen_and_catalog_update_cannot_reprice_existing_rule() -> None:
    catalog = _load_default()
    rule = catalog.require_rule(**_selector(), at=CHECKED_AT)
    original = rule.components[0].unit_price_usd_nanos

    with pytest.raises(ValidationError, match="frozen"):
        rule.components[0].unit_price_usd_nanos = 1  # type: ignore[misc]
    assert rule.components[0].unit_price_usd_nanos == original
