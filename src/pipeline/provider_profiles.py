"""Mock provider prompt profiles for C4 compiler fixtures."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderPromptProfile(BaseModel):
    profile_id: str
    provider: str
    model_family: str
    prompt_style: str
    motion_language: str
    recommended_scenarios: list[str] = Field(default_factory=list)
    negative_prompt_policy: str = "capability_driven"


_PROFILES: dict[tuple[str, str], ProviderPromptProfile] = {
    ("poyo", "seedance"): ProviderPromptProfile(
        profile_id="profile_poyo_seedance_mock_v1",
        provider="poyo",
        model_family="seedance",
        prompt_style="short structured shot prompt with explicit subject, camera, motion, setting, and mood",
        motion_language="use concise camera verbs such as slow push-in, locked macro, orbit, handheld follow",
        recommended_scenarios=["s1", "s4", "s5"],
    ),
    ("kling", "kling"): ProviderPromptProfile(
        profile_id="profile_kling_mock_v1",
        provider="kling",
        model_family="kling",
        prompt_style="continuity-oriented prompt emphasizing action, character consistency, and cinematic transitions",
        motion_language="describe body action, scene continuity, and camera movement in the same sentence",
        recommended_scenarios=["s2", "s3", "s5"],
    ),
    ("runway", "runway"): ProviderPromptProfile(
        profile_id="profile_runway_mock_v1",
        provider="runway",
        model_family="runway",
        prompt_style="director-style prompt with shot type, lens feel, scene texture, and edit intent",
        motion_language="use production terms like dolly, pan, rack focus, match cut, speed ramp",
        recommended_scenarios=["s2", "s3", "s4"],
    ),
    ("google", "veo"): ProviderPromptProfile(
        profile_id="profile_google_veo_mock_v1",
        provider="google",
        model_family="veo",
        prompt_style="scene-level cinematic prompt emphasizing physical plausibility and coherent action",
        motion_language="describe camera path, subject action, and environmental motion separately",
        recommended_scenarios=["s2", "s4", "s5"],
    ),
    ("openai", "sora"): ProviderPromptProfile(
        profile_id="profile_openai_sora_mock_v1",
        provider="openai",
        model_family="sora",
        prompt_style="rich natural-language scene prompt with narrative context and temporal continuity",
        motion_language="state beginning, middle, and end action beats without copying source likeness",
        recommended_scenarios=["s2", "s3", "s5"],
    ),
    ("wan", "wan"): ProviderPromptProfile(
        profile_id="profile_wan_mock_v1",
        provider="wan",
        model_family="wan",
        prompt_style="compact multilingual-friendly prompt with clear subject, action, style, and constraints",
        motion_language="use direct motion verbs and keep visual constraints explicit",
        recommended_scenarios=["s1", "s4"],
    ),
}


GENERIC_PROVIDER_PROFILE = ProviderPromptProfile(
    profile_id="profile_generic_mock_v1",
    provider="generic",
    model_family="generic",
    prompt_style="generic structured video prompt",
    motion_language="describe camera and subject motion explicitly",
)


def get_provider_prompt_profile(provider: str, model_family: str, model: str = "") -> ProviderPromptProfile:
    provider_key = provider.lower()
    family_key = (model_family or model).lower()
    direct = _PROFILES.get((provider_key, family_key))
    if direct is not None:
        return direct

    for (known_provider, known_family), profile in _PROFILES.items():
        if provider_key == known_provider and (known_family in family_key or known_family in model.lower()):
            return profile
    return GENERIC_PROVIDER_PROFILE


def list_provider_prompt_profiles() -> list[ProviderPromptProfile]:
    return list(_PROFILES.values())
