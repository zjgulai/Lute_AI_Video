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
    StoryboardShotSchema,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult
from src.pipeline.runtime_prompt_preview import (
    RuntimePromptPreviewResult,
    build_runtime_prompt_preview,
)


def test_runtime_prompt_preview_compiles_sanitized_dry_run_when_injection_allowed():
    bundle = _bundle([_approved_token("bat_hard_001", TokenStrength.HARD)])
    runtime = _runtime_injection(hard_token_ids=["bat_hard_001"])

    preview = build_runtime_prompt_preview(
        compile_input=_compile_input(bundle=bundle),
        runtime_injection=runtime,
        planned_injection={"hard_token_ids": ["bat_hard_001"], "soft_token_ids": []},
    )
    payload = preview.model_dump(mode="json")

    assert preview.prompt_preview_allowed is True
    assert preview.compile_blocked is False
    assert preview.prompt_hash is not None
    assert preview.hard_token_ids == ["bat_hard_001"]
    assert preview.injection_diff.missing_runtime_hard_token_ids == []
    assert "must-not-leak" not in json.dumps(payload)
    assert "prompt" not in payload
    RuntimePromptPreviewResult.model_validate(payload)


def test_runtime_prompt_preview_blocks_before_compile_when_runtime_not_allowed(monkeypatch):
    called = False

    def fake_compile_provider_prompt(compile_input):
        nonlocal called
        called = True
        raise AssertionError("compiler should not run when runtime injection is blocked")

    monkeypatch.setattr(
        "src.pipeline.runtime_prompt_preview.compile_provider_prompt",
        fake_compile_provider_prompt,
    )

    preview = build_runtime_prompt_preview(
        compile_input=_compile_input(bundle=_bundle([])),
        runtime_injection=RuntimeInjectionResult(
            scenario="s1",
            step="video_prompts",
            prompt_injection_allowed=False,
            blocked_reasons=["reviewed brand bundle missing"],
        ),
    )

    assert called is False
    assert preview.prompt_preview_allowed is False
    assert preview.compile_blocked is True
    assert preview.prompt_hash is None
    assert preview.block_reasons == [
        "runtime injection is not allowed",
        "reviewed brand bundle missing",
    ]


def test_runtime_prompt_preview_blocks_when_compile_bundle_differs_from_runtime_ids():
    bundle = _bundle([_approved_token("bat_hard_compile", TokenStrength.HARD)])
    runtime = _runtime_injection(hard_token_ids=["bat_hard_runtime"])

    preview = build_runtime_prompt_preview(
        compile_input=_compile_input(bundle=bundle),
        runtime_injection=runtime,
    )

    assert preview.prompt_preview_allowed is False
    assert preview.compile_blocked is True
    assert "runtime injection token ids do not match compile bundle" in preview.block_reasons
    assert preview.injection_diff.missing_runtime_hard_token_ids == ["bat_hard_compile"]
    assert preview.injection_diff.compile_extra_hard_token_ids == ["bat_hard_runtime"]


def test_runtime_prompt_preview_returns_compiler_block_without_prompt_body():
    hard = _approved_token("bat_hard_001", TokenStrength.HARD)
    preview = build_runtime_prompt_preview(
        compile_input=_compile_input(
            bundle=_bundle([hard]),
            shot=_shot(
                reference_asset_ids=["asset_product_001"],
                claim_evidence_refs=["claim_fixture"],
            ),
            capability=ProviderCapability(
                capability_id="cap_unknown_ref",
                provider="poyo",
                model="seedance-2",
                model_family="seedance",
                supports_reference_images=CapabilityValue.UNKNOWN,
            ),
        ),
        runtime_injection=_runtime_injection(hard_token_ids=["bat_hard_001"]),
    )
    payload = preview.model_dump(mode="json")

    assert preview.prompt_preview_allowed is False
    assert preview.compile_blocked is True
    assert "provider does not have verified reference image support" in preview.block_reasons
    assert preview.prompt_hash is not None
    assert "must-not-leak" not in json.dumps(payload)
    assert "negative_prompt" not in payload


def _compile_input(
    *,
    capability: ProviderCapability | None = None,
    bundle: BrandConstraintBundle | None = None,
    shot: StoryboardShotSchema | None = None,
    compile_options: CompileOptions | None = None,
) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_runtime_preview_fixture",
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
) -> StoryboardShotSchema:
    return StoryboardShotSchema(
        shot_id="shot_001",
        scenario="s1",
        beat="product reveal",
        visual_description="Momcozy product reveal in warm soft light",
        motion_description="slow push-in",
        reference_asset_ids=reference_asset_ids or [],
        claim_evidence_refs=claim_evidence_refs or [],
    )


def _bundle(tokens: list[BrandAssetToken]) -> BrandConstraintBundle:
    return BrandConstraintBundle(
        bundle_id="bundle_runtime_preview_fixture",
        brand_id="momcozy",
        scenario="s1",
        step="video_prompts",
        hard_tokens=[token for token in tokens if token.is_hard()],
        soft_tokens=[token for token in tokens if not token.is_hard()],
        source_token_ids=[token.token_id for token in tokens],
    )


def _approved_token(token_id: str, strength: TokenStrength) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.APPROVED,
        strength=strength,
        payload={"raw": "must-not-leak"},
        payload_summary=["must-not-leak"],
        scenario_scope=["s1"],
        step_scope=["video_prompts"],
        rights_ref="rights_fixture",
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="self"),
    )


def _runtime_injection(
    *,
    hard_token_ids: list[str] | None = None,
    soft_token_ids: list[str] | None = None,
) -> RuntimeInjectionResult:
    return RuntimeInjectionResult(
        scenario="s1",
        step="video_prompts",
        prompt_injection_allowed=True,
        brand_bundle_id="bundle_runtime_preview_fixture",
        hard_token_ids=hard_token_ids or [],
        soft_token_ids=soft_token_ids or [],
        source_token_ids=[*(hard_token_ids or []), *(soft_token_ids or [])],
    )
