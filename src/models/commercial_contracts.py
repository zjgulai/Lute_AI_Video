"""Commercial AI video 2.0 contract models.

These models are intentionally provider-agnostic. They let the 2.0 work enter
code without calling real generation providers or promoting candidate brand
assets into approved production bundles.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvidenceLevel(StrEnum):
    L0_UNVERIFIED = "L0-unverified"
    AIHOT_SIGNAL = "aihot_signal"
    OFFICIAL_DOC = "official_doc"
    SUPPLIER_BACKEND = "supplier_backend"
    L1_PUBLIC_OR_RUNTIME = "L1-public-or-runtime"
    L2_FIXTURE_OR_DRY_RUN = "L2-fixture-or-dry-run"
    L3_PRODUCTION_READ_ONLY = "L3-production-read-only"
    L4_AUTHORIZED_LIVE = "L4-authorized-live"


class LicenseStatus(StrEnum):
    UNKNOWN = "unknown"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AllowedUse(StrEnum):
    REFERENCE = "reference"
    GENERATION = "generation"
    PUBLISHING = "publishing"
    TRAINING = "training"


class TokenStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    EXPIRED = "expired"


class TokenStrength(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    HARD_FOR_REVIEW_ONLY = "hard_for_review_only"


class CapabilityValue(StrEnum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class MediaJobStatus(StrEnum):
    PREPARED = "prepared"
    BLOCKED = "blocked"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class RiskFlags(BaseModel):
    pii: bool = False
    minor_visible: bool = False
    third_party_brand: bool = False
    third_party_music: bool = False
    medical_claim: bool = False
    voice_clone: bool = False
    visible_likeness: bool = False

    def has_blocking_risk(self) -> bool:
        return any(
            (
                self.pii,
                self.minor_visible,
                self.third_party_brand,
                self.third_party_music,
                self.medical_claim,
                self.voice_clone,
                self.visible_likeness,
            )
        )


class RightsProfile(BaseModel):
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    territory: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    allowed_uses: list[AllowedUse] = Field(default_factory=list)
    consent_required: bool = False
    consent_ref: str | None = None

    def is_approved_for(self, required_use: AllowedUse) -> bool:
        if self.license_status != LicenseStatus.APPROVED:
            return False
        if self.consent_required and not self.consent_ref:
            return False
        return required_use in self.allowed_uses


class BrandAssetSource(BaseModel):
    source_asset_id: str
    brand_id: str
    asset_state: str = "external_source"
    asset_kind: str
    source_path: str
    media_type: Literal["text", "image", "video", "audio", "structured_data", "mixed"]
    uploaded_at: str | None = None
    source_owner: str | None = None
    rights: RightsProfile = Field(default_factory=RightsProfile)
    risk_flags: RiskFlags = Field(default_factory=RiskFlags)

    def can_be_approved_for(self, required_use: AllowedUse) -> bool:
        return self.rights.is_approved_for(required_use) and not self.risk_flags.has_blocking_risk()


class TokenReview(BaseModel):
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_notes: str | None = None


class TokenProvenance(BaseModel):
    extraction_method: str = "rule-based"
    extracted_at: str | None = None
    extractor_version: str = "spec-only"


class BrandAssetToken(BaseModel):
    token_id: str
    brand_id: str
    token_type: str
    status: TokenStatus = TokenStatus.CANDIDATE
    strength: TokenStrength = TokenStrength.SOFT
    priority: int = 50
    modality: str = "text"
    source_asset_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_summary: list[str] = Field(default_factory=list)
    scenario_scope: list[str] = Field(default_factory=list)
    step_scope: list[str] = Field(default_factory=list)
    platform_scope: list[str] = Field(default_factory=list)
    locale_scope: list[str] = Field(default_factory=list)
    rights_ref: str | None = None
    rights_gate: str | None = None
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    allowed_uses: list[AllowedUse] = Field(default_factory=list)
    review: TokenReview = Field(default_factory=TokenReview)
    provenance: TokenProvenance = Field(default_factory=TokenProvenance)

    def is_hard(self) -> bool:
        return self.strength in {TokenStrength.HARD, TokenStrength.HARD_FOR_REVIEW_ONLY}

    def is_approved_for_bundle(self) -> bool:
        return (
            self.status == TokenStatus.APPROVED
            and self.license_status == LicenseStatus.APPROVED
            and self.review.review_status == "approved"
        )

    def applies_to(self, *, scenario: str, step: str, platform: str | None = None) -> bool:
        if self.scenario_scope and scenario not in self.scenario_scope:
            return False
        if self.step_scope and step not in self.step_scope:
            return False
        if platform is not None and self.platform_scope and platform not in self.platform_scope:
            return False
        return True


class CandidateTokenLedger(BaseModel):
    brand_id: str
    status: str = "draft"
    license_status_default: LicenseStatus = LicenseStatus.UNKNOWN
    allowed_uses_default: list[AllowedUse] = Field(default_factory=list)
    approved_token_count: int = 0
    candidate_tokens: list[BrandAssetToken] = Field(default_factory=list)
    generated_at: str | None = None

    @model_validator(mode="after")
    def _candidate_ledger_must_not_claim_approved_tokens(self) -> CandidateTokenLedger:
        approved = [token for token in self.candidate_tokens if token.status == TokenStatus.APPROVED]
        if self.approved_token_count != 0 or approved:
            raise ValueError("candidate token ledger must not contain approved tokens")
        return self


class BrandConstraintBundle(BaseModel):
    bundle_id: str
    brand_id: str
    scenario: str
    step: str
    platform: str | None = None
    hard_tokens: list[BrandAssetToken] = Field(default_factory=list)
    soft_tokens: list[BrandAssetToken] = Field(default_factory=list)
    source_token_ids: list[str] = Field(default_factory=list)
    rejected_token_ids: list[str] = Field(default_factory=list)

    @classmethod
    def build_approved(
        cls,
        *,
        bundle_id: str,
        brand_id: str,
        scenario: str,
        step: str,
        tokens: list[BrandAssetToken],
        platform: str | None = None,
    ) -> BrandConstraintBundle:
        hard_tokens: list[BrandAssetToken] = []
        soft_tokens: list[BrandAssetToken] = []
        rejected_token_ids: list[str] = []

        for token in tokens:
            if token.brand_id != brand_id or not token.applies_to(scenario=scenario, step=step, platform=platform):
                continue
            if not token.is_approved_for_bundle():
                rejected_token_ids.append(token.token_id)
                continue
            if token.is_hard():
                hard_tokens.append(token)
            else:
                soft_tokens.append(token)

        ordered_tokens = sorted(hard_tokens + soft_tokens, key=lambda token: token.priority, reverse=True)
        return cls(
            bundle_id=bundle_id,
            brand_id=brand_id,
            scenario=scenario,
            step=step,
            platform=platform,
            hard_tokens=sorted(hard_tokens, key=lambda token: token.priority, reverse=True),
            soft_tokens=sorted(soft_tokens, key=lambda token: token.priority, reverse=True),
            source_token_ids=[token.token_id for token in ordered_tokens],
            rejected_token_ids=rejected_token_ids,
        )

    @property
    def all_tokens(self) -> list[BrandAssetToken]:
        return [*self.hard_tokens, *self.soft_tokens]


class ProviderSignalLedger(BaseModel):
    signal_id: str
    provider: str
    model: str
    capability_hint: str
    evidence_level: EvidenceLevel = EvidenceLevel.AIHOT_SIGNAL
    source_url: str | None = None
    observed_at: str | None = None
    notes: str = ""
    impact_scope: list[str] = Field(default_factory=list)
    production_default_eligible: bool = False

    @model_validator(mode="after")
    def _market_signal_cannot_be_production_default(self) -> ProviderSignalLedger:
        if self.production_default_eligible and not evidence_allows_production_default(self.evidence_level):
            raise ValueError("provider signal evidence is too weak for production default")
        return self


class CapabilitySnapshot(BaseModel):
    snapshot_id: str
    provider: str
    model: str
    capability: ProviderCapability
    evidence_level: EvidenceLevel = EvidenceLevel.L0_UNVERIFIED
    source_signal_ids: list[str] = Field(default_factory=list)
    captured_at: str | None = None
    production_default_eligible: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _snapshot_production_default_requires_strong_evidence(self) -> CapabilitySnapshot:
        if self.production_default_eligible and not evidence_allows_production_default(self.evidence_level):
            raise ValueError("capability snapshot evidence is too weak for production default")
        return self


class TechniquePattern(BaseModel):
    pattern_id: str
    name: str
    source_signal_ids: list[str] = Field(default_factory=list)
    applicable_scenarios: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.AIHOT_SIGNAL
    description: str = ""
    implementation_status: Literal["candidate", "fixture", "implemented"] = "candidate"


class ExperimentBacklogItem(BaseModel):
    experiment_id: str
    provider: str
    model: str
    hypothesis: str
    source_signal_ids: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.AIHOT_SIGNAL
    target_scenarios: list[str] = Field(default_factory=list)
    allowed_actions: list[Literal["fixture", "dry_run", "token_smoke"]] = Field(default_factory=lambda: ["fixture"])
    production_default_candidate: bool = False

    @model_validator(mode="after")
    def _weak_evidence_stays_out_of_production_default(self) -> ExperimentBacklogItem:
        if self.production_default_candidate and not evidence_allows_production_default(self.evidence_level):
            raise ValueError("experiment evidence is too weak for production default")
        return self


class ProviderCapability(BaseModel):
    capability_id: str
    provider: str
    model: str
    model_family: str = ""
    modalities: list[str] = Field(default_factory=list)
    supports_reference_images: CapabilityValue = CapabilityValue.UNKNOWN
    supports_reference_video: CapabilityValue = CapabilityValue.UNKNOWN
    supports_first_frame: CapabilityValue = CapabilityValue.UNKNOWN
    supports_last_frame: CapabilityValue = CapabilityValue.UNKNOWN
    supports_native_audio: CapabilityValue = CapabilityValue.UNKNOWN
    supports_lip_sync: CapabilityValue = CapabilityValue.UNKNOWN
    supports_seed: CapabilityValue = CapabilityValue.UNKNOWN
    supports_negative_prompt: CapabilityValue = CapabilityValue.UNKNOWN
    supports_aspect_ratios: list[str] = Field(default_factory=list)
    max_duration_seconds: int | None = None
    max_reference_assets: int | None = None
    async_required: bool = True
    retention_days: int | None = None
    c2pa: CapabilityValue = CapabilityValue.UNKNOWN
    content_filter_notes: list[str] = Field(default_factory=list)
    recommended_scenarios: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    last_verified_at: str | None = None
    source_urls: list[str] = Field(default_factory=list)

    def feature_is_supported(self, feature_name: str) -> bool:
        value = getattr(self, feature_name)
        return value == CapabilityValue.SUPPORTED


class PlatformTarget(BaseModel):
    platform: str
    aspect_ratio: str = "9:16"
    locale: str = "en-US"
    duration_seconds: int = 5


class StoryboardShotSchema(BaseModel):
    shot_id: str
    scenario: str
    beat: str
    visual_description: str
    motion_description: str = ""
    camera: str = "static"
    duration_seconds: int = 5
    aspect_ratio: str = "9:16"
    reference_asset_ids: list[str] = Field(default_factory=list)
    claim_evidence_refs: list[str] = Field(default_factory=list)
    contains_children_direct_reference: bool = False
    negative_constraints: list[str] = Field(default_factory=list)


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptTimeline(BaseModel):
    timeline_id: str
    source_asset_id: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    source_rights_status: LicenseStatus = LicenseStatus.UNKNOWN
    research_only: bool = True


class LongformProductionContract(BaseModel):
    contract_id: str
    scenario: str
    brand_id: str
    target_duration_seconds: int
    scene_ledger_id: str | None = None
    timeline_manifest_id: str | None = None
    review_checkpoint_ids: list[str] = Field(default_factory=list)

    def has_longform_delivery_floor(self) -> bool:
        return bool(self.scene_ledger_id and self.timeline_manifest_id and self.review_checkpoint_ids)


class CompileOptions(BaseModel):
    max_prompt_chars: int = 1800
    allow_native_audio: bool = False
    allow_soft_token_compression: bool = True


class PromptCompileInput(BaseModel):
    compile_id: str
    scenario: str
    step_name: str
    shot: StoryboardShotSchema
    brand_bundle: BrandConstraintBundle
    provider_capability: ProviderCapability
    platform_target: PlatformTarget
    compile_options: CompileOptions = Field(default_factory=CompileOptions)


class PromptCompileResult(BaseModel):
    compile_id: str
    compiler_id: str
    provider: str
    model: str
    prompt: str
    negative_prompt: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)
    duration_seconds: int
    aspect_ratio: str
    provider_options: dict[str, Any] = Field(default_factory=dict)
    hard_token_ids: list[str] = Field(default_factory=list)
    soft_token_ids: list[str] = Field(default_factory=list)
    dropped_soft_token_ids: list[str] = Field(default_factory=list)
    compression_notes: list[str] = Field(default_factory=list)
    prompt_hash: str
    compile_warnings: list[str] = Field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)


class MediaJobSpec(BaseModel):
    job_id: str
    provider: str
    model: str
    scenario: str
    step_name: str
    prompt_hash: str
    prompt_compile_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    brand_bundle_id: str | None = None
    cost_ceiling_usd: float | None = None


class MediaJobRecord(BaseModel):
    job_id: str
    spec: MediaJobSpec
    status: MediaJobStatus = MediaJobStatus.PREPARED
    provider_job_id: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    failure_reason: str | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    delivery_accepted: bool = False
    publish_allowed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @model_validator(mode="after")
    def _generation_success_is_not_delivery_acceptance(self) -> MediaJobRecord:
        if self.status == MediaJobStatus.SUCCEEDED and self.publish_allowed and not self.delivery_accepted:
            raise ValueError("publish_allowed requires delivery_accepted")
        return self


class PublishPolicy(BaseModel):
    publish_allowed_default: bool = False
    requires_human_review: bool = True


class RepairAction(BaseModel):
    action_id: str
    check: str
    severity: Literal["blocker", "advisory"] = "blocker"
    evidence_ref: str | None = None
    recommendation: str
    required_before: Literal["delivery_acceptance", "publish", "next_review"] = "delivery_acceptance"


class RepairPlan(BaseModel):
    plan_id: str
    contract_id: str
    evidence_bundle_id: str
    actions: list[RepairAction] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class GateDecision(BaseModel):
    decision_id: str
    contract_id: str
    evidence_bundle_id: str
    status: Literal["blocked", "review_required", "accepted"] = "blocked"
    publish_allowed: bool = False
    requires_human_review: bool = True
    blocking_failure_count: int = 0
    advisory_warning_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    repair_plan_id: str | None = None

    @model_validator(mode="after")
    def _publish_allowed_requires_finished_gate(self) -> GateDecision:
        if self.publish_allowed and self.status != "accepted":
            raise ValueError("publish_allowed requires an accepted gate decision")
        if self.publish_allowed and self.requires_human_review:
            raise ValueError("publish_allowed requires completed human review")
        return self


class QualityContract(BaseModel):
    contract_id: str
    scenario: str
    stage: str
    platform: str
    brand_id: str
    locale: str = "en-US"
    blocking_checks: list[str] = Field(default_factory=list)
    advisory_checks: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    required_evidence: list[str] = Field(default_factory=list)
    publish_policy: PublishPolicy = Field(default_factory=PublishPolicy)

    @model_validator(mode="after")
    def _publish_defaults_fail_closed(self) -> QualityContract:
        if self.publish_policy.publish_allowed_default:
            raise ValueError("quality contracts must default publish_allowed to false")
        return self


class AuditEvidenceBundle(BaseModel):
    evidence_bundle_id: str
    scenario: str
    stage: str
    brand_bundle_id: str | None = None
    source_token_ids: list[str] = Field(default_factory=list)
    media_job_ids: list[str] = Field(default_factory=list)
    prompt_hashes: list[str] = Field(default_factory=list)
    artifact_manifest_id: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    rights_evidence_refs: list[str] = Field(default_factory=list)
    claim_evidence_refs: list[str] = Field(default_factory=list)
    source_fingerprint_refs: list[str] = Field(default_factory=list)
    platform_target: PlatformTarget | None = None
    c2pa_status: str = "pending"
    hard_brand_token_violations: list[str] = Field(default_factory=list)
    platform_policy_violations: list[str] = Field(default_factory=list)
    children_direct_reference: bool = False


def stable_prompt_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def evidence_allows_production_default(evidence_level: EvidenceLevel) -> bool:
    """Return whether evidence is strong enough to even be considered for production default.

    This is a capability-evidence gate, not live approval. A true result still
    does not authorize provider calls, provider default changes, or publishing.
    """
    return evidence_level in {
        EvidenceLevel.OFFICIAL_DOC,
        EvidenceLevel.SUPPLIER_BACKEND,
        EvidenceLevel.L2_FIXTURE_OR_DRY_RUN,
        EvidenceLevel.L3_PRODUCTION_READ_ONLY,
        EvidenceLevel.L4_AUTHORIZED_LIVE,
    }
