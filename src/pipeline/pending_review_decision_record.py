"""Human decision record for pending-review authorized-live assets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.pipeline.pending_review_asset_packet import (
    PendingReviewAsset,
    PendingReviewAssetPacket,
    PendingReviewFinding,
)

AssetReviewDecision = Literal["keep_as_candidate", "reject", "request_regeneration"]


class PendingReviewAssetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    decision: AssetReviewDecision
    reviewed_by: str
    reviewed_at: str
    review_notes: str
    resolved_finding_codes: list[str] = Field(default_factory=list)
    resolution_ref: str | None = None

    @model_validator(mode="after")
    def _requires_explicit_human_review_context(self) -> PendingReviewAssetDecision:
        if not self.sample_id.strip():
            raise ValueError("asset review decision requires sample_id")
        if not self.reviewed_by.strip():
            raise ValueError("asset review decision requires reviewed_by")
        if not self.reviewed_at.strip():
            raise ValueError("asset review decision requires reviewed_at")
        if not self.review_notes.strip():
            raise ValueError("asset review decision requires review_notes")
        return self


class CandidatePendingReviewAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    artifact_ref: str
    provider_ref: str
    media_type: Literal["image", "video"]
    tool_id: str
    media_url: str
    local_path: str
    decision: Literal["candidate_asset_after_human_review"] = "candidate_asset_after_human_review"
    rights_status: Literal["not_approved_brand_token"] = "not_approved_brand_token"


class PendingReviewDecisionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    decision: AssetReviewDecision
    finding_codes: list[str] = Field(default_factory=list)
    unresolved_blocker_codes: list[str] = Field(default_factory=list)


class PendingReviewDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_record_id: str
    source_packet_ref: str
    source_packet_id: str
    source_evidence_level: str
    record_build_no_provider_call: bool = True
    brand: str
    product: str
    candidate_asset_count: int
    candidate_assets: list[CandidatePendingReviewAsset] = Field(default_factory=list)
    regeneration_requested_ids: list[str] = Field(default_factory=list)
    rejected_asset_ids: list[str] = Field(default_factory=list)
    skipped_asset_ids: list[str] = Field(default_factory=list)
    outcomes: list[PendingReviewDecisionOutcome] = Field(default_factory=list)
    asset_status: Literal["pending_review"] = "pending_review"
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    approved_for_runtime_injection: bool = False
    commercial_delivery_complete: bool = False
    requires_separate_brand_token_intake: bool = True
    supported_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @model_validator(mode="after")
    def _decision_record_must_not_promote_assets(self) -> PendingReviewDecisionRecord:
        if self.delivery_accepted or self.publish_allowed or self.approved_brand_token_write:
            raise ValueError("decision record cannot approve delivery, publish, or brand token writes")
        if self.approved_for_runtime_injection or self.commercial_delivery_complete:
            raise ValueError("decision record cannot approve runtime injection or commercial delivery")
        if self.candidate_asset_count != len(self.candidate_assets):
            raise ValueError("candidate_asset_count must match candidate_assets")
        return self


def build_pending_review_decision_record(
    packet: PendingReviewAssetPacket | Mapping[str, object],
    decisions: Sequence[PendingReviewAssetDecision | Mapping[str, object]],
    *,
    source_packet_ref: str = "provided-pending-review-packet-json",
) -> PendingReviewDecisionRecord:
    """Apply explicit human review decisions without writing brand tokens."""
    parsed_packet = (
        packet if isinstance(packet, PendingReviewAssetPacket) else PendingReviewAssetPacket.model_validate(packet)
    )
    parsed_decisions = [
        decision
        if isinstance(decision, PendingReviewAssetDecision)
        else PendingReviewAssetDecision.model_validate(decision)
        for decision in decisions
    ]
    if not parsed_decisions:
        raise ValueError("pending-review decision record requires at least one explicit asset decision")
    _validate_packet_boundary(parsed_packet)
    decision_by_sample_id = _decision_by_sample_id(parsed_decisions)
    assets_by_sample_id = {asset.sample_id: asset for asset in parsed_packet.assets}
    _validate_decision_scope(decision_by_sample_id, assets_by_sample_id)

    candidate_assets: list[CandidatePendingReviewAsset] = []
    regeneration_requested_ids: list[str] = []
    rejected_asset_ids: list[str] = []
    outcomes: list[PendingReviewDecisionOutcome] = []

    for asset in parsed_packet.assets:
        decision = decision_by_sample_id.get(asset.sample_id)
        if decision is None:
            continue
        unresolved = _unresolved_blocker_codes(asset.findings, decision.resolved_finding_codes)
        if decision.decision == "keep_as_candidate":
            if unresolved:
                raise ValueError(
                    f"{asset.sample_id} cannot be kept as candidate with unresolved blocker findings: "
                    f"{', '.join(unresolved)}"
                )
            if _blocker_codes(asset.findings) and not decision.resolution_ref:
                raise ValueError(f"{asset.sample_id} keep_as_candidate requires resolution_ref")
            candidate_assets.append(_candidate_asset(asset))
        elif decision.decision == "request_regeneration":
            regeneration_requested_ids.append(asset.sample_id)
        else:
            rejected_asset_ids.append(asset.sample_id)
        outcomes.append(
            PendingReviewDecisionOutcome(
                sample_id=asset.sample_id,
                decision=decision.decision,
                finding_codes=[finding.code for finding in asset.findings],
                unresolved_blocker_codes=unresolved,
            )
        )

    skipped_asset_ids = [
        asset.sample_id
        for asset in parsed_packet.assets
        if asset.sample_id not in decision_by_sample_id
    ]
    return PendingReviewDecisionRecord(
        decision_record_id=f"pending_review_decision_{parsed_packet.packet_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        source_packet_ref=source_packet_ref,
        source_packet_id=parsed_packet.packet_id,
        source_evidence_level=parsed_packet.evidence_level,
        brand=parsed_packet.brand,
        product=parsed_packet.product,
        candidate_asset_count=len(candidate_assets),
        candidate_assets=candidate_assets,
        regeneration_requested_ids=regeneration_requested_ids,
        rejected_asset_ids=rejected_asset_ids,
        skipped_asset_ids=skipped_asset_ids,
        outcomes=outcomes,
        supported_claims=_supported_claims(candidate_assets),
        forbidden_claims=_forbidden_claims(parsed_packet),
        next_actions=_next_actions(candidate_assets),
    )


def _validate_packet_boundary(packet: PendingReviewAssetPacket) -> None:
    if packet.asset_status != "pending_review":
        raise ValueError("decision record requires pending_review packet")
    if packet.approved_brand_token_write or packet.delivery_accepted or packet.publish_allowed:
        raise ValueError("decision record cannot consume a packet that already promotes assets")
    if packet.approved_for_runtime_injection or packet.commercial_delivery_complete:
        raise ValueError("decision record cannot consume a packet marked complete")


def _decision_by_sample_id(decisions: Sequence[PendingReviewAssetDecision]) -> dict[str, PendingReviewAssetDecision]:
    decision_by_id: dict[str, PendingReviewAssetDecision] = {}
    for decision in decisions:
        if decision.sample_id in decision_by_id:
            raise ValueError(f"duplicate decision for sample_id: {decision.sample_id}")
        decision_by_id[decision.sample_id] = decision
    return decision_by_id


def _validate_decision_scope(
    decisions: Mapping[str, PendingReviewAssetDecision],
    assets: Mapping[str, PendingReviewAsset],
) -> None:
    unknown_ids = sorted(set(decisions) - set(assets))
    if unknown_ids:
        raise ValueError(f"decision references unknown pending-review assets: {', '.join(unknown_ids)}")


def _candidate_asset(asset: PendingReviewAsset) -> CandidatePendingReviewAsset:
    return CandidatePendingReviewAsset(
        sample_id=asset.sample_id,
        artifact_ref=asset.artifact_ref,
        provider_ref=asset.provider_ref,
        media_type=asset.media_type,
        tool_id=asset.tool_id,
        media_url=asset.media_url,
        local_path=asset.local_path,
    )


def _unresolved_blocker_codes(
    findings: Sequence[PendingReviewFinding],
    resolved_finding_codes: Sequence[str],
) -> list[str]:
    resolved = set(resolved_finding_codes)
    return [code for code in _blocker_codes(findings) if code not in resolved]


def _blocker_codes(findings: Sequence[PendingReviewFinding]) -> list[str]:
    return [finding.code for finding in findings if finding.severity == "blocker"]


def _supported_claims(candidate_assets: Sequence[CandidatePendingReviewAsset]) -> list[str]:
    claims = ["explicit per-asset human review decisions were recorded"]
    if candidate_assets:
        claims.append("selected assets may move to candidate brand asset intake")
    return claims


def _forbidden_claims(packet: PendingReviewAssetPacket) -> list[str]:
    claims = {
        *packet.forbidden_claims,
        "not delivery accepted",
        "not published",
        "not written to approved brand token",
        "not approved for runtime injection",
        "not a final brand asset approval",
    }
    return sorted(claims)


def _next_actions(candidate_assets: Sequence[CandidatePendingReviewAsset]) -> list[str]:
    actions = [
        "execute requested regenerations with a separate exact provider-call authorization if needed",
        "reject assets that fail brand/product/legal review",
    ]
    if candidate_assets:
        actions.append("create a separate candidate brand asset intake record before any token review")
    return actions
