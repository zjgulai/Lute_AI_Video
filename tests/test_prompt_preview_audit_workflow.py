from __future__ import annotations

import json

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    CapabilityValue,
    CompileOptions,
    LicenseStatus,
    PlatformTarget,
    PromptCompileInput,
    ProviderCapability,
    QualityContract,
    StoryboardShotSchema,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.prompt_preview_audit_workflow import build_prompt_preview_audit_workflow
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult


def test_prompt_preview_audit_workflow_returns_allowed_with_label_bundle():
    bundle = build_prompt_preview_audit_workflow(
        contract=_quality_contract(),
        compile_input=_compile_input(bundle=_bundle(["bat_hard_fixture"])),
        runtime_injection=_runtime_injection(["bat_hard_fixture"]),
        planned_injection={"hard_token_ids": ["bat_hard_fixture"], "soft_token_ids": []},
    )
    payload = bundle.model_dump(mode="json")

    assert bundle.evidence_boundary.decision == "allowed-with-label"
    assert bundle.gate_decision.status == "review_required"
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert bundle.prompt_hash is not None
    assert "provider job submitted" in bundle.evidence_boundary.forbidden_claims
    assert "must-not-leak" not in json.dumps(payload)
    assert "prompt" not in payload["preview"]


def test_prompt_preview_audit_workflow_blocks_runtime_mismatch_without_provider_submission():
    bundle = build_prompt_preview_audit_workflow(
        contract=_quality_contract(),
        compile_input=_compile_input(bundle=_bundle(["bat_compile"])),
        runtime_injection=_runtime_injection(["bat_runtime"]),
        planned_injection={"hard_token_ids": ["bat_runtime"], "soft_token_ids": []},
    )

    assert bundle.evidence_boundary.decision == "blocked"
    assert bundle.gate_decision.status == "blocked"
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert "runtime_prompt_injection_diff_pass" in [
        action.check for action in bundle.repair_plan.actions
    ]
    assert "provider job submitted" in bundle.evidence_boundary.forbidden_claims


def test_prompt_preview_audit_workflow_accepts_runtime_injection_payload_dict():
    bundle = build_prompt_preview_audit_workflow(
        contract=_quality_contract(),
        compile_input=_compile_input(bundle=_bundle(["bat_hard_fixture"])),
        runtime_injection=_runtime_injection(["bat_hard_fixture"]).model_dump(mode="json"),
        planned_injection={"hard_token_ids": ["bat_hard_fixture"], "soft_token_ids": []},
    )

    assert bundle.evidence_boundary.decision == "allowed-with-label"
    assert bundle.preview.hard_token_ids == ["bat_hard_fixture"]


def _quality_contract() -> QualityContract:
    return QualityContract(
        contract_id="qc_s1_prompt_preview_fixture",
        scenario="s1",
        stage="prompt_preview",
        platform="tiktok",
        brand_id="momcozy",
    )


def _compile_input(
    *,
    capability: ProviderCapability | None = None,
    bundle: BrandConstraintBundle | None = None,
    shot: StoryboardShotSchema | None = None,
    compile_options: CompileOptions | None = None,
) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_workflow_fixture",
        scenario="s1",
        step_name="video_prompts",
        shot=shot or _shot(),
        brand_bundle=bundle or _bundle([]),
        provider_capability=capability
        or ProviderCapability(
            capability_id="cap_seedance_fixture",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
            supports_reference_images=CapabilityValue.SUPPORTED,
            supports_negative_prompt=CapabilityValue.SUPPORTED,
            max_duration_seconds=15,
        ),
        platform_target=PlatformTarget(platform="tiktok", aspect_ratio="9:16"),
        compile_options=compile_options or CompileOptions(),
    )


def _shot() -> StoryboardShotSchema:
    return StoryboardShotSchema(
        shot_id="shot_001",
        scenario="s1",
        beat="product reveal",
        visual_description="Momcozy product reveal in warm soft light",
        motion_description="slow push-in",
        claim_evidence_refs=["claim_fixture"],
    )


def _bundle(token_ids: list[str]) -> BrandConstraintBundle:
    tokens = [_approved_token(token_id) for token_id in token_ids]
    return BrandConstraintBundle(
        bundle_id="bundle_prompt_preview_workflow_fixture",
        brand_id="momcozy",
        scenario="s1",
        step="video_prompts",
        hard_tokens=tokens,
        source_token_ids=[token.token_id for token in tokens],
    )


def _approved_token(token_id: str) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.APPROVED,
        strength=TokenStrength.HARD,
        payload={"raw": "must-not-leak"},
        payload_summary=["must-not-leak"],
        scenario_scope=["s1"],
        step_scope=["video_prompts"],
        rights_ref="rights_fixture",
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="self"),
    )


def _runtime_injection(hard_token_ids: list[str]) -> RuntimeInjectionResult:
    return RuntimeInjectionResult(
        scenario="s1",
        step="video_prompts",
        prompt_injection_allowed=True,
        brand_bundle_id="bundle_prompt_preview_workflow_fixture",
        hard_token_ids=hard_token_ids,
        source_token_ids=hard_token_ids,
    )
