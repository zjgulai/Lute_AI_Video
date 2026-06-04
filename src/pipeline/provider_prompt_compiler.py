"""Offline provider prompt compiler mock for AI video 2.0."""

from __future__ import annotations

from src.models.commercial_contracts import (
    CapabilityValue,
    PromptCompileInput,
    PromptCompileResult,
    TokenStrength,
    stable_prompt_hash,
)
from src.pipeline.provider_profiles import GENERIC_PROVIDER_PROFILE, get_provider_prompt_profile


def compile_provider_prompt(compile_input: PromptCompileInput) -> PromptCompileResult:
    """Compile a provider-specific prompt without calling the provider.

    The mock compiler preserves hard token ids, treats unknown capabilities as
    unsupported, and returns a blocked result instead of silently dropping
    constraints.
    """
    capability = compile_input.provider_capability
    profile = get_provider_prompt_profile(capability.provider, capability.model_family, capability.model)
    shot = compile_input.shot
    bundle = compile_input.brand_bundle
    options = compile_input.compile_options
    warnings: list[str] = []
    block_reasons: list[str] = []

    if profile.profile_id == GENERIC_PROVIDER_PROFILE.profile_id:
        warnings.append("provider prompt profile missing; generic mock profile used")

    if shot.reference_asset_ids and capability.supports_reference_images != CapabilityValue.SUPPORTED:
        block_reasons.append("provider does not have verified reference image support")

    if capability.max_duration_seconds is not None and shot.duration_seconds > capability.max_duration_seconds:
        block_reasons.append("shot duration exceeds provider capability")

    if shot.contains_children_direct_reference:
        block_reasons.append("children direct reference is blocked")

    if shot.claim_evidence_refs == [] and _shot_mentions_claim_like_content(shot.visual_description):
        block_reasons.append("claim-like shot lacks claim evidence refs")

    hard_tokens = bundle.hard_tokens
    soft_tokens = bundle.soft_tokens
    hard_token_ids = [token.token_id for token in hard_tokens]
    soft_token_ids = [token.token_id for token in soft_tokens]

    hard_constraints = _token_summaries(hard_tokens)
    soft_constraints = _token_summaries(soft_tokens)
    negative_constraints = [*shot.negative_constraints, *_negative_constraints_from_tokens(hard_tokens)]

    prompt_parts = [
        f"Provider profile: {profile.prompt_style}.",
        f"Motion language: {profile.motion_language}.",
        f"{shot.duration_seconds}-second {compile_input.platform_target.aspect_ratio} shot.",
        f"Scenario {compile_input.scenario}; beat: {shot.beat}.",
        f"Visual: {shot.visual_description}",
    ]
    if shot.motion_description:
        prompt_parts.append(f"Motion: {shot.motion_description}")
    if hard_constraints:
        prompt_parts.append("Hard brand constraints: " + "; ".join(hard_constraints))
    if soft_constraints:
        prompt_parts.append("Soft style guidance: " + "; ".join(soft_constraints))

    negative_prompt = "; ".join(negative_constraints)
    if negative_prompt and capability.supports_negative_prompt != CapabilityValue.SUPPORTED:
        prompt_parts.append("Do not violate: " + negative_prompt)
        warnings.append("negative prompt unsupported or unknown; hard negatives merged into main prompt")
        negative_prompt = ""

    prompt = " ".join(prompt_parts)
    dropped_soft_token_ids: list[str] = []
    compression_notes: list[str] = []
    if len(prompt) > options.max_prompt_chars:
        prompt, dropped_soft_token_ids, compression_notes = _compress_soft_tokens(
            prompt_parts=prompt_parts,
            hard_token_ids=hard_token_ids,
            soft_token_ids=soft_token_ids,
            max_prompt_chars=options.max_prompt_chars,
            allow_soft_token_compression=options.allow_soft_token_compression,
        )
        if not prompt:
            block_reasons.append("prompt exceeds max length and cannot compress soft tokens safely")
            prompt = " ".join(prompt_parts)

    payload_for_hash = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "provider_options": {"native_audio": options.allow_native_audio, "profile_id": profile.profile_id},
        "reference_asset_ids": shot.reference_asset_ids,
        "hard_token_ids": hard_token_ids,
    }

    return PromptCompileResult(
        compile_id=compile_input.compile_id,
        compiler_id=f"{profile.profile_id}_compiler",
        provider=capability.provider,
        model=capability.model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        reference_asset_ids=shot.reference_asset_ids,
        duration_seconds=shot.duration_seconds,
        aspect_ratio=compile_input.platform_target.aspect_ratio,
        provider_options={"native_audio": options.allow_native_audio, "profile_id": profile.profile_id},
        hard_token_ids=hard_token_ids,
        soft_token_ids=soft_token_ids,
        dropped_soft_token_ids=dropped_soft_token_ids,
        compression_notes=compression_notes,
        prompt_hash=stable_prompt_hash(payload_for_hash),
        compile_warnings=warnings,
        blocked=bool(block_reasons),
        block_reasons=block_reasons,
    )


def _shot_mentions_claim_like_content(text: str) -> bool:
    lowered = text.lower()
    claim_markers = ("faster", "quieter", "stronger", "certified", "patented", "%", "db", "fda", "ce")
    return any(marker in lowered for marker in claim_markers)


def _token_summaries(tokens: list[object]) -> list[str]:
    summaries: list[str] = []
    for token in tokens:
        payload_summary = getattr(token, "payload_summary", [])
        if payload_summary:
            summaries.extend(str(item) for item in payload_summary[:3])
            continue
        payload = getattr(token, "payload", {})
        if isinstance(payload, dict):
            summaries.extend(f"{key}={value}" for key, value in list(payload.items())[:3])
    return summaries


def _negative_constraints_from_tokens(tokens: list[object]) -> list[str]:
    constraints: list[str] = []
    for token in tokens:
        payload = getattr(token, "payload", {})
        if isinstance(payload, dict):
            raw_constraints = payload.get("negative_constraints") or payload.get("forbidden_terms") or []
            if isinstance(raw_constraints, list):
                constraints.extend(str(item) for item in raw_constraints)
        if getattr(token, "strength", None) == TokenStrength.HARD_FOR_REVIEW_ONLY:
            constraints.append("review-only hard token cannot be used for production approval")
    return constraints


def _compress_soft_tokens(
    *,
    prompt_parts: list[str],
    hard_token_ids: list[str],
    soft_token_ids: list[str],
    max_prompt_chars: int,
    allow_soft_token_compression: bool,
) -> tuple[str, list[str], list[str]]:
    if not allow_soft_token_compression:
        return "", [], []

    kept_parts = [part for part in prompt_parts if not part.startswith("Soft style guidance:")]
    compressed = " ".join(kept_parts)
    if len(compressed) <= max_prompt_chars:
        return (
            compressed,
            soft_token_ids,
            [f"dropped {len(soft_token_ids)} soft tokens; preserved hard tokens {hard_token_ids}"],
        )
    return "", [], []
