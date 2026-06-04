from __future__ import annotations

from src.models.commercial_contracts import (
    BrandConstraintBundle,
    PlatformTarget,
    PromptCompileInput,
    ProviderCapability,
    StoryboardShotSchema,
)
from src.pipeline.provider_profiles import get_provider_prompt_profile, list_provider_prompt_profiles
from src.pipeline.provider_prompt_compiler import compile_provider_prompt


def test_all_c4_mock_provider_profiles_are_registered():
    profile_ids = {profile.profile_id for profile in list_provider_prompt_profiles()}

    assert profile_ids == {
        "profile_poyo_seedance_mock_v1",
        "profile_kling_mock_v1",
        "profile_runway_mock_v1",
        "profile_google_veo_mock_v1",
        "profile_openai_sora_mock_v1",
        "profile_wan_mock_v1",
    }


def test_compile_uses_provider_specific_profile_id_and_prompt_style():
    cases = [
        ("poyo", "seedance", "seedance-2", "profile_poyo_seedance_mock_v1"),
        ("kling", "kling", "kling-2", "profile_kling_mock_v1"),
        ("runway", "runway", "gen-3", "profile_runway_mock_v1"),
        ("google", "veo", "veo-3", "profile_google_veo_mock_v1"),
        ("openai", "sora", "sora", "profile_openai_sora_mock_v1"),
        ("wan", "wan", "wan-2.1", "profile_wan_mock_v1"),
    ]

    for provider, family, model, profile_id in cases:
        result = compile_provider_prompt(_compile_input(provider=provider, family=family, model=model))

        assert result.provider_options["profile_id"] == profile_id
        assert result.compiler_id == f"{profile_id}_compiler"
        assert "Provider profile:" in result.prompt
        assert "Motion language:" in result.prompt


def test_unknown_provider_uses_generic_profile_with_warning():
    result = compile_provider_prompt(_compile_input(provider="unknown", family="unknown", model="unknown-model"))

    assert result.provider_options["profile_id"] == "profile_generic_mock_v1"
    assert result.compile_warnings == ["provider prompt profile missing; generic mock profile used"]


def test_profile_lookup_can_match_model_name_when_family_is_blank():
    profile = get_provider_prompt_profile("poyo", "", "seedance-2")

    assert profile.profile_id == "profile_poyo_seedance_mock_v1"


def _compile_input(provider: str, family: str, model: str) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id=f"pci_{provider}_{model}",
        scenario="s2",
        step_name="video_prompts",
        shot=StoryboardShotSchema(
            shot_id="shot_profile_fixture",
            scenario="s2",
            beat="campaign motif",
            visual_description="Warm lifestyle product moment with no numeric claim",
            motion_description="gentle camera move",
            claim_evidence_refs=["claim_fixture"],
        ),
        brand_bundle=BrandConstraintBundle(
            bundle_id="bundle_profile_fixture",
            brand_id="momcozy",
            scenario="s2",
            step="video_prompts",
        ),
        provider_capability=ProviderCapability(
            capability_id=f"cap_{provider}_{model}",
            provider=provider,
            model=model,
            model_family=family,
        ),
        platform_target=PlatformTarget(platform="tiktok", aspect_ratio="9:16"),
    )
