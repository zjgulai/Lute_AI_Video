"""Brand token-vault intake into candidate-only commercial token ledgers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.models.commercial_contracts import (
    BrandAssetToken,
    CandidateTokenLedger,
    LicenseStatus,
    TokenStatus,
    TokenStrength,
)


class BrandTokenIntakeReport(BaseModel):
    brand_id: str
    source_path: str
    source_schema_version: str | None = None
    evidence_level: str = "L2-fixture-or-dry-run"
    token_count: int
    source_ref_count: int
    approved_token_count: int = 0
    blocked_reasons: list[str] = Field(default_factory=list)
    ledger: CandidateTokenLedger
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def build_candidate_ledger_from_token_vault(
    token_vault_path: str | Path,
    *,
    max_tokens: int | None = None,
) -> BrandTokenIntakeReport:
    """Convert a Brand_Data_Lake token vault into a candidate-only ledger."""
    path = Path(token_vault_path)
    payload = json.loads(path.read_text())
    brand_id = _slug(payload.get("brand") or payload.get("brand_id") or "unknown_brand")
    generated_at = str(payload.get("generated_at") or datetime.now(UTC).isoformat())
    candidate_tokens = _candidate_tokens_from_payload(payload, brand_id=brand_id, max_tokens=max_tokens)
    ledger = CandidateTokenLedger(
        brand_id=brand_id,
        status="draft",
        license_status_default=LicenseStatus.UNKNOWN,
        allowed_uses_default=[],
        approved_token_count=0,
        candidate_tokens=candidate_tokens,
        generated_at=generated_at,
    )
    source_refs = {ref for token in candidate_tokens for ref in token.source_refs}
    return BrandTokenIntakeReport(
        brand_id=brand_id,
        source_path=str(path),
        source_schema_version=_optional_string(payload.get("schema_version")),
        token_count=len(candidate_tokens),
        source_ref_count=len(source_refs),
        ledger=ledger,
        generated_at=generated_at,
    )


def _candidate_tokens_from_payload(
    payload: dict[str, Any],
    *,
    brand_id: str,
    max_tokens: int | None,
) -> list[BrandAssetToken]:
    token_layers = payload.get("token_layers")
    if not isinstance(token_layers, dict):
        raise ValueError("token vault payload must contain token_layers object")

    tokens: list[BrandAssetToken] = []
    used_ids: set[str] = set()
    for layer, items in token_layers.items():
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            token = _candidate_token_from_item(
                item,
                brand_id=brand_id,
                layer=str(layer),
                index=index,
                used_ids=used_ids,
            )
            tokens.append(token)
            if max_tokens is not None and len(tokens) >= max_tokens:
                return tokens
    return tokens


def _candidate_token_from_item(
    item: dict[str, Any],
    *,
    brand_id: str,
    layer: str,
    index: int,
    used_ids: set[str],
) -> BrandAssetToken:
    raw_id = str(item.get("id") or f"{brand_id}.{layer}.{item.get('type', 'token')}.{index}")
    token_id = _dedupe_token_id(f"bat_{_slug(raw_id)}_candidate", used_ids)
    value = item.get("value")
    token_type = str(item.get("type") or layer)
    channels = _string_list(item.get("applicable_channels"))
    source_refs = _source_refs(item)
    return BrandAssetToken(
        token_id=token_id,
        brand_id=brand_id,
        token_type=token_type,
        status=TokenStatus.CANDIDATE,
        strength=_strength_for_layer(layer, token_type),
        priority=_priority(item),
        modality=_modality_for_value(layer, value),
        source_refs=source_refs,
        payload={},
        payload_summary=_payload_summary(value),
        scenario_scope=_scenario_scope(channels),
        step_scope=_step_scope(layer, token_type),
        rights_gate="candidate_only_until_brand_rights_review",
        license_status=LicenseStatus.UNKNOWN,
    )


def _source_refs(item: dict[str, Any]) -> list[str]:
    source_path = _optional_string(item.get("source_path")) or "unknown_source"
    source_field = _optional_string(item.get("source_field"))
    return [f"{source_path}#{source_field}" if source_field else source_path]


def _payload_summary(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [_clip(f"{key}: {_plain_text(val)}") for key, val in list(value.items())[:4]]
    if isinstance(value, list):
        return [_clip(_plain_text(item)) for item in value[:4]]
    return [_clip(_plain_text(value))]


def _plain_text(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={_plain_text(val)}" for key, val in list(value.items())[:3])
    if isinstance(value, list):
        return "; ".join(_plain_text(item) for item in value[:3])
    return re.sub(r"\s+", " ", str(value)).strip()


def _clip(value: str, max_chars: int = 120) -> str:
    return value if len(value) <= max_chars else f"{value[: max_chars - 3]}..."


def _strength_for_layer(layer: str, token_type: str) -> TokenStrength:
    layer_key = layer.lower()
    type_key = token_type.lower()
    if "claim" in type_key or "compliance" in layer_key or "guardrail" in type_key:
        return TokenStrength.HARD_FOR_REVIEW_ONLY
    if "brand" in layer_key or "voice" in layer_key:
        return TokenStrength.HARD_FOR_REVIEW_ONLY
    return TokenStrength.SOFT


def _modality_for_value(layer: str, value: Any) -> str:
    layer_key = layer.lower()
    if "visual" in layer_key:
        return "structured_data" if isinstance(value, dict) else "image"
    if isinstance(value, dict):
        return "structured_data"
    return "text"


def _scenario_scope(channels: list[str]) -> list[str]:
    normalized = {channel.lower() for channel in channels}
    if not normalized or "all" in normalized:
        return ["s1", "s2", "s3", "s4", "s5"]
    scenarios: set[str] = set()
    if normalized & {"pdp", "sales_enablement"}:
        scenarios.update({"s1", "s2"})
    if normalized & {"ads", "social", "video", "email", "cx"}:
        scenarios.update({"s2", "s3", "s5"})
    return sorted(scenarios or {"s1", "s2", "s5"})


def _step_scope(layer: str, token_type: str) -> list[str]:
    layer_key = layer.lower()
    type_key = token_type.lower()
    if "visual" in layer_key:
        return ["storyboards", "video_prompts", "thumbnail_prompts", "audit"]
    if "claim" in type_key or "compliance" in layer_key:
        return ["scripts", "storyboards", "video_prompts", "audit"]
    return ["strategy", "scripts", "caption", "audit"]


def _priority(item: dict[str, Any]) -> int:
    quality = item.get("quality_score")
    confidence = item.get("confidence")
    if isinstance(quality, int | float):
        return max(1, min(100, round(float(quality) * 100)))
    if isinstance(confidence, int | float):
        return max(1, min(100, round(float(confidence) * 100)))
    return 50


def _dedupe_token_id(token_id: str, used_ids: set[str]) -> str:
    candidate = token_id
    suffix = 2
    while candidate in used_ids:
        candidate = f"{token_id}_{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "unknown"


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
