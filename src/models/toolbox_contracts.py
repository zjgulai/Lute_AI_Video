"""Toolbox productization contracts for AI video 2.0.

The toolbox contracts model standalone creative tools without calling providers.
They carry refs, checks, and ledger/audit state, not raw prompt payloads or
brand asset source bodies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.commercial_contracts import (
    AuditEvidenceBundle,
    EvidenceLevel,
    GateDecision,
    MediaJobRecord,
    MediaJobStatus,
    PlatformTarget,
    RepairPlan,
)


class ToolboxToolId(StrEnum):
    PRODUCT_IMAGE = "product-image"
    SIX_VIEW = "six-view"
    ECOMMERCE_VISUAL = "ecommerce-visual"
    DIGITAL_HUMAN = "digital-human"
    STORYBOARD = "storyboard"


class ToolboxRunMode(StrEnum):
    DRY_RUN = "dry_run"
    AUTHORIZED_LIVE = "authorized_live"


class ToolboxRunStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    PREPARED = "prepared"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    ACCEPTED_DRY_RUN = "accepted_dry_run"
    AUTHORIZED_LIVE_READY = "authorized_live_ready"
    FAILED = "failed"


class ToolboxArtifactType(StrEnum):
    PRODUCT_IMAGE_SET = "product_image_set"
    SIX_VIEW_REFERENCE_MANIFEST = "six_view_reference_manifest"
    ECOMMERCE_VISUAL_PACK = "ecommerce_visual_pack"
    PRESENTER_PLAN = "presenter_plan"
    STORYBOARD_PACKAGE = "storyboard_package"
    INJECTION_DRAFT = "injection_draft"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_GOVERNED_REF_PREFIXES = (
    "asset://",
    "artifact://",
    "avatar://",
    "brand://",
    "bundle://",
    "claim://",
    "consent://",
    "edl://",
    "fixture://",
    "job://",
    "manifest://",
    "product://",
    "rights://",
    "script://",
    "sku://",
    "storyboard://",
    "voice://",
)

_CANONICAL_SIX_VIEWS = {"front", "back", "left", "right", "top", "detail"}


def _is_governed_ref(value: str) -> bool:
    return value.startswith(_GOVERNED_REF_PREFIXES)


def _validate_governed_ref(value: str, *, field_name: str) -> str:
    if not _is_governed_ref(value):
        raise ValueError(f"{field_name} must use governed ref scheme")
    return value


def _validate_governed_refs(values: list[str], *, field_name: str) -> list[str]:
    return [_validate_governed_ref(value, field_name=field_name) for value in values]


class ToolboxAssetRef(_StrictModel):
    asset_ref: str
    asset_kind: Literal["image", "video", "audio", "text", "structured_data", "mixed"]
    rights_ref: str | None = None
    source_token_ids: list[str] = Field(default_factory=list)

    @field_validator("asset_ref")
    @classmethod
    def _asset_ref_must_be_governed(cls, value: str) -> str:
        return _validate_governed_ref(value, field_name="asset_ref")

    @field_validator("rights_ref")
    @classmethod
    def _rights_ref_must_be_governed(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_governed_ref(value, field_name="rights_ref")


class ProductImageInput(_StrictModel):
    tool_id: Literal[ToolboxToolId.PRODUCT_IMAGE] = ToolboxToolId.PRODUCT_IMAGE
    product_ref: str
    image_type: Literal["main_white_bg", "lifestyle", "detail", "comparison", "thumbnail"]
    aspect_ratio: str = "1:1"
    platform: str = "shopify"
    reference_asset_refs: list[str] = Field(default_factory=list)
    claim_evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("product_ref")
    @classmethod
    def _product_ref_must_be_governed(cls, value: str) -> str:
        return _validate_governed_ref(value, field_name="product_ref")

    @field_validator("reference_asset_refs")
    @classmethod
    def _reference_refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="reference_asset_refs")


class SixViewInput(_StrictModel):
    tool_id: Literal[ToolboxToolId.SIX_VIEW] = ToolboxToolId.SIX_VIEW
    product_ref: str
    seed_image_refs: list[str] = Field(default_factory=list)
    required_views: list[Literal["front", "back", "left", "right", "top", "detail"]] = Field(
        default_factory=lambda: ["front", "back", "left", "right", "top", "detail"]
    )
    consistency_level: Literal["standard", "strict"] = "strict"

    @field_validator("product_ref")
    @classmethod
    def _product_ref_must_be_governed(cls, value: str) -> str:
        return _validate_governed_ref(value, field_name="product_ref")

    @field_validator("seed_image_refs")
    @classmethod
    def _seed_refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="seed_image_refs")

    @model_validator(mode="after")
    def _requires_canonical_six_views(self) -> SixViewInput:
        if set(self.required_views) != _CANONICAL_SIX_VIEWS:
            raise ValueError("six-view input requires canonical six views")
        return self


class EcommerceVisualInput(_StrictModel):
    tool_id: Literal[ToolboxToolId.ECOMMERCE_VISUAL] = ToolboxToolId.ECOMMERCE_VISUAL
    campaign_brief: str
    channel: Literal["shopify", "amazon", "tiktok", "reels", "youtube_shorts"]
    visual_format: Literal["banner", "a_plus", "social_ad", "detail_module"]
    copy_block_refs: list[str] = Field(default_factory=list)
    product_image_refs: list[str] = Field(default_factory=list)
    aspect_ratio: str = "1:1"

    @field_validator("copy_block_refs", "product_image_refs")
    @classmethod
    def _refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="ecommerce_visual_refs")


class DigitalHumanInput(_StrictModel):
    tool_id: Literal[ToolboxToolId.DIGITAL_HUMAN] = ToolboxToolId.DIGITAL_HUMAN
    presenter_policy: str
    avatar_ref: str | None = None
    script_ref: str | None = None
    voice_policy: Literal["none", "tts", "voice_clone"] = "none"
    voice_ref: str | None = None
    consent_ref: str | None = None

    @field_validator("avatar_ref", "script_ref", "voice_ref", "consent_ref")
    @classmethod
    def _optional_refs_must_be_governed(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_governed_ref(value, field_name="digital_human_ref")

    @model_validator(mode="after")
    def _avatar_and_voice_clone_require_consent(self) -> DigitalHumanInput:
        if self.avatar_ref and not self.consent_ref:
            raise ValueError("digital human avatar requires consent_ref")
        if self.voice_policy == "voice_clone" and not self.consent_ref:
            raise ValueError("voice clone requires consent_ref")
        return self


class StoryboardInput(_StrictModel):
    tool_id: Literal[ToolboxToolId.STORYBOARD] = ToolboxToolId.STORYBOARD
    brief: str
    script_ref: str | None = None
    duration_target_seconds: int = 30
    platform: str = "tiktok"
    storyboard_grid: Literal[6, 9, 12, 24] = 12
    asset_refs: list[str] = Field(default_factory=list)
    planned_timeline_block_count: int = 0
    review_checkpoint_refs: list[str] = Field(default_factory=list)
    source_fingerprint_refs: list[str] = Field(default_factory=list)

    @field_validator("script_ref")
    @classmethod
    def _script_ref_must_be_governed(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_governed_ref(value, field_name="script_ref")

    @field_validator("asset_refs", "review_checkpoint_refs", "source_fingerprint_refs")
    @classmethod
    def _refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="storyboard_refs")

    @model_validator(mode="after")
    def _longform_requires_timeline_and_review_floor(self) -> StoryboardInput:
        if self.duration_target_seconds >= 90 and (
            self.planned_timeline_block_count <= 0 or not self.review_checkpoint_refs
        ):
            raise ValueError("90s+ storyboard requires timeline blocks and review checkpoints")
        return self


ToolboxToolInput = ProductImageInput | SixViewInput | EcommerceVisualInput | DigitalHumanInput | StoryboardInput


class ToolboxTool(_StrictModel):
    tool_id: ToolboxToolId
    label: str
    description: str = ""
    output_types: list[ToolboxArtifactType] = Field(default_factory=list)
    injectable_scenarios: list[str] = Field(default_factory=list)
    default_checks: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN


class ToolboxRequest(_StrictModel):
    request_id: str
    tool_id: ToolboxToolId
    brand_id: str
    platform_target: PlatformTarget
    brand_bundle_ref: str | None = None
    asset_refs: list[ToolboxAssetRef] = Field(default_factory=list)
    target_scenario: str | None = None
    tool_input: ToolboxToolInput

    @model_validator(mode="after")
    def _tool_id_must_match_payload(self) -> ToolboxRequest:
        if self.tool_id != self.tool_input.tool_id:
            raise ValueError("tool_id must match tool_input.tool_id")
        return self


class ToolboxPromptPreview(_StrictModel):
    preview_id: str
    request_id: str
    tool_id: ToolboxToolId
    prompt_hash: str | None = None
    prompt_preview_allowed: bool = False
    sanitized_prompt_blocks: list[str] = Field(default_factory=list)
    compile_warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)


class ToolboxPlan(_StrictModel):
    plan_id: str
    request_id: str
    tool_id: ToolboxToolId
    mode: ToolboxRunMode = ToolboxRunMode.DRY_RUN
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN
    provider_call: bool = False
    delivery_accepted: bool = False
    provider_profile_id: str | None = None
    prompt_hash: str | None = None
    required_checks: list[str] = Field(default_factory=list)
    artifact_manifest_id: str | None = None
    injection_target_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dry_run_is_no_provider_and_no_delivery(self) -> ToolboxPlan:
        if self.mode == ToolboxRunMode.DRY_RUN and self.provider_call:
            raise ValueError("dry-run toolbox plan cannot call provider")
        if self.mode == ToolboxRunMode.DRY_RUN and self.evidence_level != EvidenceLevel.L2_FIXTURE_OR_DRY_RUN:
            raise ValueError("dry-run toolbox plan must remain L2-fixture-or-dry-run")
        if self.delivery_accepted:
            raise ValueError("toolbox plan cannot mark delivery accepted")
        if self.mode != ToolboxRunMode.AUTHORIZED_LIVE and self.evidence_level == EvidenceLevel.L4_AUTHORIZED_LIVE:
            raise ValueError("L4-authorized-live requires authorized_live mode")
        return self


class ToolboxArtifact(_StrictModel):
    artifact_id: str
    tool_id: ToolboxToolId
    artifact_type: ToolboxArtifactType | str
    artifact_ref: str
    source_job_id: str | None = None
    manifest_ref: str | None = None
    delivery_accepted: bool = False
    publish_allowed: bool = False

    @field_validator("artifact_ref", "manifest_ref")
    @classmethod
    def _artifact_refs_must_be_governed(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_governed_ref(value, field_name="artifact_ref")

    @model_validator(mode="after")
    def _publish_requires_delivery(self) -> ToolboxArtifact:
        if self.publish_allowed and not self.delivery_accepted:
            raise ValueError("publish_allowed requires delivery_accepted")
        return self


class ToolboxInjectionTarget(_StrictModel):
    target_ref: str
    scenario: str
    step_name: str
    artifact_refs: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    bundle_refs: list[str] = Field(default_factory=list)

    @field_validator("target_ref")
    @classmethod
    def _target_ref_must_be_governed(cls, value: str) -> str:
        return _validate_governed_ref(value, field_name="target_ref")

    @field_validator("artifact_refs", "contract_refs")
    @classmethod
    def _refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="injection_refs")


class ToolboxInjectionDraft(_StrictModel):
    draft_id: str
    draft_ref: str
    run_id: str
    tool_id: ToolboxToolId
    mode: Literal["read_only"] = "read_only"
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN
    state_write: bool = False
    provider_call: bool = False
    delivery_accepted: bool = False
    publish_allowed: bool = False
    injection_targets: list[ToolboxInjectionTarget] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    bundle_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("draft_ref")
    @classmethod
    def _draft_ref_must_be_governed(cls, value: str) -> str:
        return _validate_governed_ref(value, field_name="draft_ref")

    @field_validator("artifact_refs", "contract_refs")
    @classmethod
    def _refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="injection_draft_refs")

    @model_validator(mode="after")
    def _draft_cannot_cross_read_only_boundary(self) -> ToolboxInjectionDraft:
        if self.evidence_level != EvidenceLevel.L2_FIXTURE_OR_DRY_RUN:
            raise ValueError("toolbox injection draft must remain L2-fixture-or-dry-run")
        if self.state_write:
            raise ValueError("toolbox injection draft cannot write scenario state")
        if self.provider_call:
            raise ValueError("toolbox injection draft cannot call provider")
        if self.delivery_accepted:
            raise ValueError("toolbox injection draft cannot mark delivery accepted")
        if self.publish_allowed:
            raise ValueError("toolbox injection draft cannot allow publish")
        return self


class ToolboxInjectionAuditCheck(_StrictModel):
    check_id: str
    label: str
    status: Literal["passed", "advisory", "blocked"]
    evidence_refs: list[str] = Field(default_factory=list)
    message: str | None = None

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_must_be_governed(cls, values: list[str]) -> list[str]:
        return _validate_governed_refs(values, field_name="audit_evidence_refs")


class ToolboxInjectionAuditSummary(_StrictModel):
    summary_id: str
    run_id: str
    tool_id: ToolboxToolId
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN
    ready_for_scenario_injection: bool = False
    state_write: bool = False
    provider_call: bool = False
    delivery_accepted: bool = False
    publish_allowed: bool = False
    injection_draft_ref: str | None = None
    target_count: int = 0
    artifact_ref_count: int = 0
    contract_ref_count: int = 0
    bundle_ref_count: int = 0
    checks: list[ToolboxInjectionAuditCheck] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    advisory_reasons: list[str] = Field(default_factory=list)

    @field_validator("injection_draft_ref")
    @classmethod
    def _draft_ref_must_be_governed(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_governed_ref(value, field_name="injection_draft_ref")

    @model_validator(mode="after")
    def _summary_cannot_cross_read_only_boundary(self) -> ToolboxInjectionAuditSummary:
        if self.evidence_level != EvidenceLevel.L2_FIXTURE_OR_DRY_RUN:
            raise ValueError("toolbox injection audit summary must remain L2-fixture-or-dry-run")
        if self.state_write:
            raise ValueError("toolbox injection audit summary cannot write scenario state")
        if self.provider_call:
            raise ValueError("toolbox injection audit summary cannot call provider")
        if self.delivery_accepted:
            raise ValueError("toolbox injection audit summary cannot mark delivery accepted")
        if self.publish_allowed:
            raise ValueError("toolbox injection audit summary cannot allow publish")
        if self.ready_for_scenario_injection and self.blocking_reasons:
            raise ValueError("ready_for_scenario_injection requires no blocking reasons")
        return self


class ToolboxInjectionAuditSummaryList(_StrictModel):
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN
    summaries: list[ToolboxInjectionAuditSummary] = Field(default_factory=list)

    @model_validator(mode="after")
    def _list_must_remain_dry_run_evidence(self) -> ToolboxInjectionAuditSummaryList:
        if self.evidence_level != EvidenceLevel.L2_FIXTURE_OR_DRY_RUN:
            raise ValueError("toolbox injection audit summary list must remain L2-fixture-or-dry-run")
        return self


class ToolboxProviderReadiness(_StrictModel):
    readiness_id: str
    tool_id: ToolboxToolId
    evidence_level: EvidenceLevel = EvidenceLevel.L2_FIXTURE_OR_DRY_RUN
    provider_profile_id: str | None = None
    ready_for_dry_run: bool = True
    ready_for_authorized_live: bool = False
    provider_call_allowed: bool = False
    approval_record_ref: str | None = None
    approved_provider: str | None = None
    approved_model: str | None = None
    approved_budget_limit_usd: float | None = None
    preflight_report_id: str | None = None
    blocker_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _authorized_live_requires_approval_record(self) -> ToolboxProviderReadiness:
        if self.evidence_level != EvidenceLevel.L2_FIXTURE_OR_DRY_RUN:
            raise ValueError("toolbox provider readiness preflight must remain L2-fixture-or-dry-run")
        if self.ready_for_authorized_live and not self.approval_record_ref:
            raise ValueError("authorized live readiness requires approval_record_ref")
        if self.provider_call_allowed and not self.ready_for_authorized_live:
            raise ValueError("provider_call_allowed requires ready_for_authorized_live")
        return self


class ToolboxAudit(_StrictModel):
    audit_id: str
    plan_id: str
    tool_id: ToolboxToolId
    evidence_bundle: AuditEvidenceBundle | None = None
    gate_decision: GateDecision | None = None
    repair_plan: RepairPlan | None = None
    blocking_checks: list[str] = Field(default_factory=list)
    advisory_checks: list[str] = Field(default_factory=list)


class ToolboxRunState(_StrictModel):
    run_id: str
    request: ToolboxRequest
    plan: ToolboxPlan
    status: ToolboxRunStatus = ToolboxRunStatus.PREPARED
    prompt_preview: ToolboxPromptPreview | None = None
    audit: ToolboxAudit | None = None
    artifacts: list[ToolboxArtifact] = Field(default_factory=list)
    injection_targets: list[ToolboxInjectionTarget] = Field(default_factory=list)
    job_record: MediaJobRecord | None = None

    @model_validator(mode="after")
    def _run_state_must_match_plan_and_dry_run_boundary(self) -> ToolboxRunState:
        if self.request.request_id != self.plan.request_id:
            raise ValueError("toolbox run request_id must match plan request_id")
        if self.request.tool_id != self.plan.tool_id:
            raise ValueError("toolbox run tool_id must match plan tool_id")
        if self.plan.mode == ToolboxRunMode.DRY_RUN and self.job_record is not None:
            if self.job_record.status in {
                MediaJobStatus.SUBMITTED,
                MediaJobStatus.SUCCEEDED,
            }:
                raise ValueError("dry-run toolbox state cannot include submitted provider job")
        return self

    def public_projection(self) -> dict[str, object]:
        return self.model_dump(mode="json")
