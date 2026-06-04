from __future__ import annotations

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
    StoryboardShotSchema,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.provider_prompt_compiler import compile_provider_prompt


def test_unknown_reference_image_capability_blocks_compile():
    compile_input = _compile_input(
        capability=ProviderCapability(
            capability_id="cap_unknown_ref",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
            supports_reference_images=CapabilityValue.UNKNOWN,
        ),
        shot=_shot(reference_asset_ids=["asset_product_001"]),
    )

    result = compile_provider_prompt(compile_input)

    assert result.blocked is True
    assert "provider does not have verified reference image support" in result.block_reasons


def test_hard_tokens_are_preserved_and_included_in_prompt_hash():
    hard = _approved_token(
        token_id="bat_claim_guardrail_001",
        token_type="claim_guardrail",
        strength=TokenStrength.HARD,
        payload_summary=["claim must cite SKU specs"],
    )
    compile_input = _compile_input(bundle=_bundle([hard]))

    result = compile_provider_prompt(compile_input)

    assert result.hard_token_ids == ["bat_claim_guardrail_001"]
    assert result.dropped_soft_token_ids == []
    assert "bat_claim_guardrail_001" not in result.dropped_soft_token_ids
    assert result.prompt_hash.startswith("sha256:")


def test_negative_prompt_unknown_support_is_merged_into_main_prompt_with_warning():
    hard = _approved_token(
        token_id="bat_negative_001",
        token_type="negative_guardrail",
        strength=TokenStrength.HARD,
        payload={"negative_constraints": ["no clinical tone", "no visible children"]},
    )
    compile_input = _compile_input(
        bundle=_bundle([hard]),
        capability=ProviderCapability(
            capability_id="cap_no_negative",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
            supports_reference_images=CapabilityValue.SUPPORTED,
            supports_negative_prompt=CapabilityValue.UNKNOWN,
        ),
    )

    result = compile_provider_prompt(compile_input)

    assert result.negative_prompt == ""
    assert "no clinical tone" in result.prompt
    assert result.compile_warnings == [
        "negative prompt unsupported or unknown; hard negatives merged into main prompt"
    ]


def test_claim_like_shot_without_claim_evidence_blocks_compile():
    compile_input = _compile_input(
        shot=_shot(visual_description="Product is 28% faster and quieter under 45db")
    )

    result = compile_provider_prompt(compile_input)

    assert result.blocked is True
    assert "claim-like shot lacks claim evidence refs" in result.block_reasons


def test_soft_token_compression_never_drops_hard_tokens():
    hard = _approved_token(
        token_id="bat_hard_001",
        token_type="claim_guardrail",
        strength=TokenStrength.HARD,
        payload_summary=["hard claim guardrail"],
    )
    soft = _approved_token(
        token_id="bat_soft_001",
        token_type="visual_identity",
        strength=TokenStrength.SOFT,
        payload_summary=["very long soft style guidance " * 20],
    )
    compile_input = _compile_input(
        bundle=_bundle([hard, soft]),
        compile_options=CompileOptions(max_prompt_chars=600, allow_soft_token_compression=True),
    )

    result = compile_provider_prompt(compile_input)

    assert result.hard_token_ids == ["bat_hard_001"]
    assert result.dropped_soft_token_ids == ["bat_soft_001"]
    assert "bat_hard_001" not in result.dropped_soft_token_ids


def _compile_input(
    *,
    capability: ProviderCapability | None = None,
    bundle: BrandConstraintBundle | None = None,
    shot: StoryboardShotSchema | None = None,
    compile_options: CompileOptions | None = None,
) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_fixture",
        scenario="s1",
        step_name="video_prompts",
        shot=shot or _shot(claim_evidence_refs=["claim_fixture"]),
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


def _shot(
    *,
    reference_asset_ids: list[str] | None = None,
    claim_evidence_refs: list[str] | None = None,
    visual_description: str = "Momcozy product reveal in warm soft light",
) -> StoryboardShotSchema:
    return StoryboardShotSchema(
        shot_id="shot_001",
        scenario="s1",
        beat="product reveal",
        visual_description=visual_description,
        motion_description="slow push-in",
        reference_asset_ids=reference_asset_ids or [],
        claim_evidence_refs=claim_evidence_refs or [],
    )


def _bundle(tokens: list[BrandAssetToken]) -> BrandConstraintBundle:
    return BrandConstraintBundle(
        bundle_id="bundle_fixture",
        brand_id="momcozy",
        scenario="s1",
        step="video_prompts",
        hard_tokens=[token for token in tokens if token.is_hard()],
        soft_tokens=[token for token in tokens if not token.is_hard()],
        source_token_ids=[token.token_id for token in tokens],
    )


def _approved_token(
    *,
    token_id: str,
    token_type: str,
    strength: TokenStrength,
    payload_summary: list[str] | None = None,
    payload: dict[str, object] | None = None,
) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type=token_type,
        status=TokenStatus.APPROVED,
        strength=strength,
        payload_summary=payload_summary or [],
        payload=payload or {},
        scenario_scope=["s1"],
        step_scope=["video_prompts"],
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="self"),
    )
