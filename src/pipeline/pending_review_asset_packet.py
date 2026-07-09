"""Review packet for authorized-live pending-review media assets."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.commercial_contracts import EvidenceLevel

ReviewRecommendation = Literal[
    "manual_review_required",
    "regenerate_or_edit_before_brand_use",
]
FindingSeverity = Literal["info", "warning", "blocker"]
MediaType = Literal["image", "video"]

EXPECTED_ASSET_KEYS = {
    "momcozy-sterilizer-main-45-gpt-image-2": "main_45",
    "momcozy-sterilizer-uv-benefit-gpt-image-2": "uv_benefit",
    "momcozy-sterilizer-kitchen-scene-gpt-image-2": "kitchen_scene",
    "momcozy-sterilizer-i2v-15s-seedance-2": "i2v_15s",
}
EXPECTED_FILENAMES = {
    "main_45": "main_45.png",
    "uv_benefit": "uv_benefit.png",
    "kitchen_scene": "kitchen_scene.png",
    "i2v_15s": "i2v_15s.mp4",
}
DISALLOWED_KEY_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "negative_prompt",
    "password",
    "prompt",
    "prompt_payload",
    "raw_payload",
    "raw_prompt",
    "request_body",
    "request_payload",
    "secret",
}


class PendingReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: FindingSeverity
    detail: str


class PendingReviewAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    job_id: str
    artifact_ref: str
    provider_ref: str
    media_type: MediaType
    tool_id: str
    provider: str
    model: str
    review_status: Literal["pending_review"] = "pending_review"
    media_url: str
    local_path: str
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
    review_recommendation: ReviewRecommendation
    findings: list[PendingReviewFinding] = Field(default_factory=list)
    allowed_next_states: list[str] = Field(default_factory=list)
    forbidden_next_states: list[str] = Field(default_factory=list)


class PendingReviewAssetPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    evidence_level: Literal[EvidenceLevel.L4_AUTHORIZED_LIVE] = EvidenceLevel.L4_AUTHORIZED_LIVE
    source_summary_ref: str
    claim_boundary: str
    packet_build_no_provider_call: bool = True
    provider_call_executed: bool
    asset_status: Literal["pending_review"] = "pending_review"
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    approved_for_runtime_injection: bool = False
    commercial_delivery_complete: bool = False
    brand: str
    product: str
    assets: list[PendingReviewAsset] = Field(default_factory=list)
    video_reference_asset_refs: list[str] = Field(default_factory=list)
    supported_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @model_validator(mode="after")
    def _review_packet_must_not_promote_assets(self) -> PendingReviewAssetPacket:
        if self.delivery_accepted or self.publish_allowed or self.approved_brand_token_write:
            raise ValueError("pending-review packet cannot approve delivery, publish, or brand token writes")
        if self.approved_for_runtime_injection or self.commercial_delivery_complete:
            raise ValueError("pending-review packet cannot mark runtime injection or commercial delivery complete")
        if not self.assets:
            raise ValueError("pending-review packet requires at least one asset")
        return self


def build_pending_review_asset_packet(
    summary: Mapping[str, Any],
    *,
    pending_review_dir: str | Path | None = None,
    source_summary_ref: str = "provided-summary-json",
    repo_root: str | Path | None = None,
) -> PendingReviewAssetPacket:
    """Build a no-provider-call review packet from an authorized-live smoke summary."""
    _assert_no_sensitive_payload(summary)
    _validate_summary_boundary(summary)
    manifest = _manifest(summary)
    resolved_dir = _resolve_pending_review_dir(summary, pending_review_dir)
    root = Path.cwd() if repo_root is None else Path(repo_root)
    assets = _build_assets(
        manifest=manifest,
        provider_refs=_mapping(summary, "provider_response_refs"),
        media_validation=_mapping(summary, "media_validation"),
        pending_review_dir=resolved_dir,
        repo_root=root,
    )

    video_refs = _string_list(manifest.get("video_reference_asset_refs"), "video_reference_asset_refs")
    if len(video_refs) != int(manifest.get("image_count", 0)):
        raise ValueError("video_reference_asset_refs must match the manifest image_count")

    return PendingReviewAssetPacket(
        packet_id=f"pending_review_packet_{manifest['manifest_id']}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        source_summary_ref=source_summary_ref,
        claim_boundary=str(summary.get("claim_boundary") or _default_claim_boundary()),
        provider_call_executed=bool(summary.get("provider_call_executed")),
        brand=str(manifest.get("brand") or "unknown"),
        product=str(manifest.get("product") or "unknown"),
        delivery_accepted=bool(manifest.get("delivery_accepted")),
        publish_allowed=bool(manifest.get("publish_allowed")),
        approved_brand_token_write=bool(manifest.get("approved_brand_token_write")),
        assets=assets,
        video_reference_asset_refs=video_refs,
        supported_claims=_supported_claims(),
        forbidden_claims=_forbidden_claims(summary),
        next_actions=_next_actions(),
    )


def _validate_summary_boundary(summary: Mapping[str, Any]) -> None:
    if summary.get("evidence_level") != EvidenceLevel.L4_AUTHORIZED_LIVE:
        raise ValueError("pending-review packet requires L4-authorized-live source summary")
    if summary.get("provider_call_executed") is not True:
        raise ValueError("pending-review packet requires provider_call_executed=true source evidence")
    if summary.get("status") != "submitted":
        raise ValueError("pending-review packet requires submitted authorized-live source status")
    manifest = _manifest(summary)
    if manifest.get("asset_status") != "pending_review":
        raise ValueError("artifact manifest must remain pending_review")
    for key in ("delivery_accepted", "publish_allowed", "approved_brand_token_write"):
        if manifest.get(key) is not False:
            raise ValueError(f"artifact manifest must keep {key}=false")


def _manifest(summary: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(summary, "artifact_manifest")


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return value


def _resolve_pending_review_dir(
    summary: Mapping[str, Any],
    pending_review_dir: str | Path | None,
) -> Path:
    raw_path = pending_review_dir or summary.get("local_pending_review_dir")
    if not raw_path:
        raise ValueError("pending review directory is required")
    path = Path(raw_path)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"pending review directory does not exist: {path}")
    return path


def _build_assets(
    *,
    manifest: Mapping[str, Any],
    provider_refs: Mapping[str, Any],
    media_validation: Mapping[str, Any],
    pending_review_dir: Path,
    repo_root: Path,
) -> list[PendingReviewAsset]:
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("artifact manifest requires artifacts")

    assets: list[PendingReviewAsset] = []
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, Mapping):
            raise ValueError("artifact entries must be objects")
        sample_id = _required_string(raw_artifact, "sample_id")
        job_id = _required_string(raw_artifact, "job_id")
        media_key = _media_key_for_sample(sample_id)
        media_entry = _media_entry(media_validation, media_key)
        local_path = _resolve_local_media_path(media_entry, media_key, pending_review_dir)
        provider_ref = provider_refs.get(job_id)
        if not isinstance(provider_ref, str) or not provider_ref:
            raise ValueError(f"missing provider response ref for {job_id}")

        assets.append(
            PendingReviewAsset(
                sample_id=sample_id,
                job_id=job_id,
                artifact_ref=_required_string(raw_artifact, "artifact_ref"),
                provider_ref=provider_ref,
                media_type=_media_type(raw_artifact),
                tool_id=_required_string(raw_artifact, "tool_id"),
                provider=_required_string(raw_artifact, "provider"),
                model=_required_string(raw_artifact, "model"),
                media_url=_required_string(raw_artifact, "media_url"),
                local_path=_relative_path(local_path, repo_root),
                technical_metadata=_technical_metadata(media_entry),
                review_recommendation=_recommendation_for(media_key),
                findings=_findings_for(media_key),
                allowed_next_states=_allowed_next_states(),
                forbidden_next_states=_forbidden_next_states(),
            )
        )
    return assets


def _media_key_for_sample(sample_id: str) -> str:
    media_key = EXPECTED_ASSET_KEYS.get(sample_id)
    if media_key is None:
        raise ValueError(f"unexpected authorized-live sample_id: {sample_id}")
    return media_key


def _media_entry(media_validation: Mapping[str, Any], media_key: str) -> Mapping[str, Any]:
    value = media_validation.get(media_key)
    if not isinstance(value, Mapping):
        raise ValueError(f"media_validation missing {media_key}")
    return value


def _resolve_local_media_path(
    media_entry: Mapping[str, Any],
    media_key: str,
    pending_review_dir: Path,
) -> Path:
    raw_path = media_entry.get("path")
    filename = Path(str(raw_path)).name if raw_path else EXPECTED_FILENAMES[media_key]
    if filename != EXPECTED_FILENAMES[media_key]:
        filename = EXPECTED_FILENAMES[media_key]
    path = pending_review_dir / filename
    if not path.exists() or not path.is_file():
        raise ValueError(f"pending-review media file missing: {path}")
    return path


def _technical_metadata(media_entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in media_entry.items()
        if key != "path"
    }


def _media_type(raw_artifact: Mapping[str, Any]) -> MediaType:
    value = raw_artifact.get("asset_type")
    if value not in {"image", "video"}:
        raise ValueError("artifact asset_type must be image or video")
    return value


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _recommendation_for(media_key: str) -> ReviewRecommendation:
    if media_key == "uv_benefit":
        return "regenerate_or_edit_before_brand_use"
    return "manual_review_required"


def _findings_for(media_key: str) -> list[PendingReviewFinding]:
    if media_key == "uv_benefit":
        return [
            PendingReviewFinding(
                code="generated_text_risk",
                severity="blocker",
                detail="Benefit graphic contains generated copy risk; text must be removed, edited, or legally reviewed.",
            ),
            PendingReviewFinding(
                code="non_real_product_name_risk",
                severity="blocker",
                detail="Generated product naming must not be treated as Momcozy-approved naming.",
            ),
            PendingReviewFinding(
                code="claim_copy_review_required",
                severity="warning",
                detail="UV and sterilization claims require brand/legal confirmation before reuse.",
            ),
        ]
    if media_key == "i2v_15s":
        return [
            PendingReviewFinding(
                code="temporal_consistency_review_required",
                severity="warning",
                detail="Review motion continuity, CTA clarity, audio, and caption legibility before brand reuse.",
            )
        ]
    if media_key == "main_45":
        return [
            PendingReviewFinding(
                code="product_identity_review_required",
                severity="warning",
                detail="Confirm product shape, material, logo treatment, and packshot proportions against real SKU assets.",
            )
        ]
    return [
        PendingReviewFinding(
            code="lifestyle_realism_review_required",
            severity="warning",
            detail="Confirm household context, product scale, and caregiver interaction are brand-appropriate.",
        )
    ]


def _allowed_next_states() -> list[str]:
    return [
        "rejected",
        "regenerate_requested",
        "candidate_brand_asset_after_human_review",
    ]


def _forbidden_next_states() -> list[str]:
    return [
        "delivery_accepted",
        "published",
        "approved_brand_token",
        "approved_runtime_injection_bundle",
    ]


def _supported_claims() -> list[str]:
    return [
        "authorized-live smoke produced pending-review media artifacts",
        "assets are available for human review and comparison against brand standards",
        "the packet records provider refs, artifact refs, local media refs, and review risks without prompt payloads",
    ]


def _forbidden_claims(summary: Mapping[str, Any]) -> list[str]:
    inherited = [
        str(claim)
        for claim in summary.get("forbidden_claims", [])
        if isinstance(claim, str) and claim.strip()
    ]
    claims = {
        *inherited,
        "not delivery accepted",
        "not published",
        "not written to approved brand token",
        "not approved for runtime injection",
        "not full commercial launch delivery",
        "not customer evidence",
    }
    return sorted(claims)


def _next_actions() -> list[str]:
    return [
        "complete manual brand review for all four pending assets",
        "regenerate or edit the UV benefit graphic before brand reuse",
        "verify video references the three generated image artifact refs",
        "only after human approval, create a separate candidate brand asset/token intake record",
    ]


def _default_claim_boundary() -> str:
    return (
        "authorized live smoke succeeded; assets remain pending_review and are not "
        "delivery_accepted, publish_allowed, or approved brand token"
    )


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _assert_no_sensitive_payload(value: Any, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in DISALLOWED_KEY_NAMES:
                joined = ".".join((*path, key_text))
                raise ValueError(f"source summary contains disallowed payload key: {joined}")
            _assert_no_sensitive_payload(child, path=(*path, key_text))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_sensitive_payload(child, path=(*path, str(index)))
