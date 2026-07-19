"""Immutable, reviewed provider price catalog and integer billing arithmetic."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.provider_cost import (
    MAX_SIGNED_BIGINT,
    BillingFactKind,
    CatalogOperation,
    MediaType,
    ProviderBillingFacts,
    ProviderBillingRegion,
    ProviderCostContractError,
)

CATALOG_ID = "provider-cost-catalog.2026-07-15.v1"
CATALOG_CHECKED_AT_UTC = datetime(2026, 7, 15, 17, 1, 24, tzinfo=UTC)
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "provider-cost-catalog.v1.json"
)

_CANONICAL_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_SAFE_DIMENSION_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

PositiveBigInt = Annotated[int, Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT)]


def _parse_utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("catalog datetime must be timezone-aware UTC")
        normalized = value.astimezone(UTC)
        if normalized != value:
            raise ValueError("catalog datetime must be expressed in UTC")
        return normalized
    if not isinstance(value, str) or _CANONICAL_UTC_RE.fullmatch(value) is None:
        raise ValueError("catalog datetime must use canonical second-precision UTC")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CatalogDimension(_StrictFrozenModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_dimension(self) -> CatalogDimension:
        if _SAFE_NAME_RE.fullmatch(self.name) is None or self.name == "wildcard":
            raise ValueError("catalog dimension name is invalid")
        if (
            _SAFE_DIMENSION_VALUE_RE.fullmatch(self.value) is None
            or "*" in self.value
        ):
            raise ValueError("catalog dimension value is invalid")
        return self


class PriceComponent(_StrictFrozenModel):
    component_name: str = Field(min_length=1, max_length=128)
    quantity_field: str = Field(min_length=1, max_length=128)
    unit_price_usd_nanos: PositiveBigInt
    unit_size: PositiveBigInt
    provider_credit_micro_units_per_unit: PositiveBigInt | None = None

    @model_validator(mode="after")
    def validate_names(self) -> PriceComponent:
        if _SAFE_NAME_RE.fullmatch(self.component_name) is None:
            raise ValueError("component name is invalid")
        if _SAFE_NAME_RE.fullmatch(self.quantity_field) is None:
            raise ValueError("component quantity field is invalid")
        return self


class DeepSeekModelContract(_StrictFrozenModel):
    provider: Literal["deepseek"]
    canonical_model: Literal["deepseek-v4-flash", "deepseek-v4-pro"]
    provider_billing_region: Literal["deepseek_global_usd"]
    context_window_tokens: PositiveBigInt
    provider_max_output_tokens: PositiveBigInt
    application_max_output_tokens: PositiveBigInt
    input_reservation_ceiling_tokens: PositiveBigInt
    evidence_urls: tuple[str, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_frozen_envelope(self) -> DeepSeekModelContract:
        if self.context_window_tokens != 1_000_000:
            raise ValueError("DeepSeek context window drift")
        if self.provider_max_output_tokens != 384_000:
            raise ValueError("DeepSeek provider output maximum drift")
        if self.application_max_output_tokens != 4_096:
            raise ValueError("DeepSeek application output maximum drift")
        if self.application_max_output_tokens > self.provider_max_output_tokens:
            raise ValueError("application output maximum exceeds provider maximum")
        expected_input = self.context_window_tokens - self.application_max_output_tokens
        if self.input_reservation_ceiling_tokens != expected_input:
            raise ValueError("DeepSeek input reservation ceiling drift")
        _validate_evidence_urls(self.evidence_urls)
        return self


class PriceRule(_StrictFrozenModel):
    price_rule_id: str = Field(min_length=1, max_length=160)
    catalog_version: Literal["provider-cost-catalog.2026-07-15.v1"]
    rule_version: Literal["v1"]
    provider: str = Field(min_length=1, max_length=64)
    canonical_model: str = Field(min_length=1, max_length=128)
    provider_billing_region: ProviderBillingRegion
    catalog_operation: CatalogOperation
    media_type: MediaType
    billing_fact_kind: BillingFactKind
    dimensions: tuple[CatalogDimension, ...] = Field(default_factory=tuple, max_length=8)
    components: tuple[PriceComponent, ...] = Field(min_length=1, max_length=8)
    reservation_formula: Literal["component_ceil_sum.v1"]
    settlement_dimension: BillingFactKind
    effective_from_utc: datetime
    effective_to_utc: datetime | None
    evidence_urls: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("components", mode="before")
    @classmethod
    def parse_component_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("effective_from_utc", "effective_to_utc", mode="before")
    @classmethod
    def parse_datetimes(cls, value: object) -> datetime | None:
        if value is None:
            return None
        return _parse_utc_datetime(value)

    @model_validator(mode="after")
    def validate_rule(self) -> PriceRule:
        if _SAFE_NAME_RE.fullmatch(self.price_rule_id) is None:
            raise ValueError("price rule ID is invalid")
        if _SAFE_NAME_RE.fullmatch(self.provider) is None or "*" in self.provider:
            raise ValueError("provider is invalid")
        if _SAFE_MODEL_RE.fullmatch(self.canonical_model) is None or "*" in self.canonical_model:
            raise ValueError("canonical model is invalid")
        dimension_names = [dimension.name for dimension in self.dimensions]
        if len(dimension_names) != len(set(dimension_names)):
            raise ValueError("duplicate catalog dimension")
        if tuple(dimension_names) != tuple(sorted(dimension_names)):
            raise ValueError("catalog dimensions must be sorted")
        component_names = [component.component_name for component in self.components]
        quantity_fields = [component.quantity_field for component in self.components]
        if len(component_names) != len(set(component_names)):
            raise ValueError("duplicate price component name")
        if len(quantity_fields) != len(set(quantity_fields)):
            raise ValueError("duplicate price component quantity field")
        if self.settlement_dimension != self.billing_fact_kind:
            raise ValueError("settlement dimension must match billing fact kind")
        if self.effective_to_utc is not None and self.effective_to_utc <= self.effective_from_utc:
            raise ValueError("effective price window is invalid")
        _validate_operation_shape(self)
        _validate_evidence_urls(self.evidence_urls)
        return self

    def selector_key(self) -> tuple[object, ...]:
        return (
            self.provider,
            self.canonical_model,
            self.provider_billing_region,
            self.catalog_operation,
            self.media_type,
            self.billing_fact_kind,
            tuple((dimension.name, dimension.value) for dimension in self.dimensions),
        )


class PriceCatalogDocument(_StrictFrozenModel):
    catalog_id: Literal["provider-cost-catalog.2026-07-15.v1"]
    checked_at_utc: datetime
    model_contracts: tuple[DeepSeekModelContract, ...] = Field(min_length=1, max_length=8)
    rules: tuple[PriceRule, ...] = Field(min_length=1, max_length=128)

    @field_validator("checked_at_utc", mode="before")
    @classmethod
    def parse_checked_at(cls, value: object) -> datetime:
        return _parse_utc_datetime(value)

    @model_validator(mode="after")
    def validate_catalog(self) -> PriceCatalogDocument:
        if self.checked_at_utc != CATALOG_CHECKED_AT_UTC:
            raise ValueError("catalog evidence timestamp drift")

        contract_keys = [
            (contract.provider, contract.canonical_model)
            for contract in self.model_contracts
        ]
        if len(contract_keys) != len(set(contract_keys)):
            raise ValueError("duplicate model contract")
        if set(contract_keys) != {
            ("deepseek", "deepseek-v4-flash"),
            ("deepseek", "deepseek-v4-pro"),
        }:
            raise ValueError("model contract set drift")

        rule_ids = [rule.price_rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("duplicate price rule ID")
        selector_keys = [rule.selector_key() for rule in self.rules]
        if len(selector_keys) != len(set(selector_keys)):
            raise ValueError("duplicate price rule selector")

        for rule in self.rules:
            if rule.effective_from_utc != self.checked_at_utc:
                raise ValueError("rule effective time differs from evidence time")
            if rule.effective_to_utc is not None:
                raise ValueError("first catalog version must remain open-ended")

        actual_signatures = {_rule_signature(rule) for rule in self.rules}
        expected_signatures = _expected_rule_signatures()
        if actual_signatures != expected_signatures:
            raise ValueError("frozen provider price rule set drift")
        return self


def _validate_evidence_urls(urls: tuple[str, ...]) -> None:
    if any(not isinstance(url, str) or not url.startswith("https://") or len(url) > 512 for url in urls):
        raise ValueError("catalog evidence URL is invalid")


def _validate_operation_shape(rule: PriceRule) -> None:
    expected = {
        "chat_completion": ("text", "llm_tokens.v1"),
        "speech_synthesis": ("audio", "tts_utf8_bytes.v1"),
        "image_generation": ("image", "image_count.v1"),
        "text_to_video": ("video", "video_duration.v1"),
        "image_to_video": ("video", "video_duration.v1"),
    }[rule.catalog_operation]
    if (rule.media_type, rule.billing_fact_kind) != expected:
        raise ValueError("catalog operation shape is invalid")


def _component_signature(component: PriceComponent) -> tuple[object, ...]:
    return (
        component.component_name,
        component.quantity_field,
        component.unit_price_usd_nanos,
        component.unit_size,
        component.provider_credit_micro_units_per_unit,
    )


def _rule_signature(rule: PriceRule) -> tuple[object, ...]:
    return (
        rule.price_rule_id,
        rule.provider,
        rule.canonical_model,
        rule.provider_billing_region,
        rule.catalog_operation,
        rule.media_type,
        rule.billing_fact_kind,
        tuple((dimension.name, dimension.value) for dimension in rule.dimensions),
        tuple(_component_signature(component) for component in rule.components),
    )


def _expected_rule_signatures() -> set[tuple[object, ...]]:
    signatures: set[tuple[object, ...]] = set()
    for model, prices in {
        "deepseek-v4-flash": (2_800_000, 140_000_000, 280_000_000),
        "deepseek-v4-pro": (3_625_000, 435_000_000, 870_000_000),
    }.items():
        signatures.add(
            (
                f"deepseek.{model}.chat-completion.v1",
                "deepseek",
                model,
                "deepseek_global_usd",
                "chat_completion",
                "text",
                "llm_tokens.v1",
                (),
                (
                    ("cache-hit-input", "input_cache_hit_tokens", prices[0], 1_000_000, None),
                    ("cache-miss-input", "input_cache_miss_tokens", prices[1], 1_000_000, None),
                    ("output", "output_tokens", prices[2], 1_000_000, None),
                ),
            )
        )

    signatures.add(
        (
            "siliconflow.cosyvoice2-0.5b.speech-synthesis.v1",
            "siliconflow",
            "FunAudioLLM/CosyVoice2-0.5B",
            "siliconflow_global_usd",
            "speech_synthesis",
            "audio",
            "tts_utf8_bytes.v1",
            (),
            (("input-utf8-bytes", "input_utf8_bytes", 7_150_000_000, 1_000_000, None),),
        )
    )

    image_prices = {
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
    for (quality, resolution), (nanos, microcredits) in image_prices.items():
        signatures.add(
            (
                f"poyo.gpt-image-2.{quality}.{resolution.lower()}.v1",
                "poyo",
                "gpt-image-2",
                "poyo_global_usd",
                "image_generation",
                "image",
                "image_count.v1",
                (("effective_resolution", resolution), ("quality", quality)),
                (("image-count", "image_count", nanos, 1, microcredits),),
            )
        )

    video_prices = {
        ("seedance-2", "480p"): (100_000_000, 20_000_000),
        ("seedance-2", "720p"): (200_000_000, 40_000_000),
        ("seedance-2", "1080p"): (450_000_000, 90_000_000),
        ("seedance-2-fast", "480p"): (70_000_000, 14_000_000),
        ("seedance-2-fast", "720p"): (140_000_000, 28_000_000),
    }
    for operation, reference_kind in (
        ("text_to_video", "none"),
        ("image_to_video", "image"),
    ):
        for (model, resolution), (nanos, microcredits) in video_prices.items():
            signatures.add(
                (
                    f"poyo.{model}.{operation.replace('_', '-')}.{resolution}.v1",
                    "poyo",
                    model,
                    "poyo_global_usd",
                    operation,
                    "video",
                    "video_duration.v1",
                    (("reference_input_kind", reference_kind), ("resolution", resolution)),
                    (("duration", "duration_ms", nanos, 1_000, microcredits),),
                )
            )
    return signatures


def _reject_non_integer_json_number(value: str) -> int:
    raise ValueError(f"non-integer catalog JSON number is forbidden: {value}")


def load_provider_price_catalog(path: str | Path) -> PriceCatalogDocument:
    """Load one strict catalog without network, float, alias, or fallback behavior."""

    catalog_path = Path(path)
    raw = catalog_path.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("provider price catalog exceeds 2 MiB")
    json.loads(
        raw,
        parse_float=_reject_non_integer_json_number,
        parse_constant=_reject_non_integer_json_number,
    )
    # JSON arrays and canonical timestamp strings are the wire representation of
    # immutable tuples and UTC datetimes. Pydantic's strict JSON mode accepts only
    # those JSON-native conversions while retaining strict scalar validation.
    return PriceCatalogDocument.model_validate_json(raw, strict=True)


class ProviderPriceCatalog:
    """Exact rule lookup over an already validated immutable catalog document."""

    def __init__(self, document: PriceCatalogDocument) -> None:
        self._document = document
        self._rules_by_selector = {rule.selector_key(): rule for rule in document.rules}
        self._contracts = {
            (contract.provider, contract.canonical_model): contract
            for contract in document.model_contracts
        }

    @classmethod
    def load_default(cls) -> ProviderPriceCatalog:
        return cls(load_provider_price_catalog(DEFAULT_CATALOG_PATH))

    @property
    def catalog_id(self) -> str:
        return self._document.catalog_id

    @property
    def checked_at_utc(self) -> datetime:
        return self._document.checked_at_utc

    @property
    def rules(self) -> tuple[PriceRule, ...]:
        return self._document.rules

    def require_model_contract(
        self,
        provider: str,
        canonical_model: str,
    ) -> DeepSeekModelContract:
        contract = self._contracts.get((provider, canonical_model))
        if contract is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "exact provider model contract is unavailable",
            )
        return contract

    def require_rule(
        self,
        *,
        provider: object,
        canonical_model: object,
        provider_billing_region: object,
        catalog_operation: object,
        media_type: object,
        billing_fact_kind: object,
        dimensions: object,
        at: datetime | None = None,
    ) -> PriceRule:
        if not isinstance(dimensions, dict) or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or "*" in name
            or "*" in value
            for name, value in dimensions.items()
        ):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "exact catalog dimensions are unavailable",
            )
        dimension_key = tuple(sorted(dimensions.items()))
        key = (
            provider,
            canonical_model,
            provider_billing_region,
            catalog_operation,
            media_type,
            billing_fact_kind,
            dimension_key,
        )
        rule = self._rules_by_selector.get(key)
        if rule is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "exact provider price rule is unavailable",
            )

        instant = at or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "catalog lookup time must be timezone-aware",
            )
        normalized = instant.astimezone(UTC)
        if normalized < rule.effective_from_utc or (
            rule.effective_to_utc is not None and normalized >= rule.effective_to_utc
        ):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider price rule is outside its effective window",
            )
        return rule

    def calculate_cost_usd_nanos(
        self,
        rule: PriceRule,
        facts: ProviderBillingFacts,
    ) -> int:
        self._validate_fact_shape(rule, facts)
        total = 0
        for component in rule.components:
            quantity = self._quantity(facts, component.quantity_field)
            product = self._checked_product(quantity, component.unit_price_usd_nanos)
            cost = (product + component.unit_size - 1) // component.unit_size
            if cost > MAX_SIGNED_BIGINT - total:
                raise self._usage_error("provider cost sum overflows signed-64-bit nanos")
            total += cost
        if total <= 0:
            raise self._usage_error("provider cost must be positive")
        return total

    def calculate_expected_provider_credit_micro_units(
        self,
        rule: PriceRule,
        facts: ProviderBillingFacts,
    ) -> int | None:
        self._validate_fact_shape(rule, facts)
        credit_components = [
            component
            for component in rule.components
            if component.provider_credit_micro_units_per_unit is not None
        ]
        if not credit_components:
            return None
        if len(credit_components) != len(rule.components):
            raise self._usage_error("provider credit components are incomplete")

        total = 0
        for component in credit_components:
            credit_rate = component.provider_credit_micro_units_per_unit
            assert credit_rate is not None
            quantity = self._quantity(facts, component.quantity_field)
            product = self._checked_product(quantity, credit_rate)
            if product % component.unit_size != 0:
                raise self._usage_error("provider credit calculation has a remainder")
            credits = product // component.unit_size
            if credits > MAX_SIGNED_BIGINT - total:
                raise self._usage_error("provider credit sum overflows signed-64-bit")
            total += credits
        return total

    @staticmethod
    def _validate_fact_shape(rule: PriceRule, facts: ProviderBillingFacts) -> None:
        if facts.schema_version != rule.billing_fact_kind:
            raise ProviderPriceCatalog._usage_error("billing fact kind does not match rule")
        if facts.schema_version == "video_duration.v1" and facts.task_count != 1:
            raise ProviderPriceCatalog._usage_error(
                "video duration rule requires exactly one provider task"
            )

    @staticmethod
    def _quantity(facts: ProviderBillingFacts, field_name: str) -> int:
        value = getattr(facts, field_name, None)
        if type(value) is not int or value < 0 or value > MAX_SIGNED_BIGINT:
            raise ProviderPriceCatalog._usage_error("billing quantity is invalid")
        return value

    @staticmethod
    def _checked_product(left: int, right: int) -> int:
        if left != 0 and right > MAX_SIGNED_BIGINT // left:
            raise ProviderPriceCatalog._usage_error("billing multiplication overflows")
        return left * right

    @staticmethod
    def _usage_error(detail: str) -> ProviderCostContractError:
        return ProviderCostContractError("provider_cost_usage_invalid", detail)
