"""Continuity storyboard grid skill for S1 Product Direct."""

from __future__ import annotations

from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

SUPPORTED_GRID_TYPES = {"auto", "9", "12", "24"}
DEFAULT_GRID_TYPE = "12"
EFFECTIVE_GRID = 12
SAFETY_NOTES = ("no close-up infant face", "no medical claim", "no distress-heavy imagery")


class ContinuityStoryboardGridSkill(SkillCallable):
    """Build a 12-grid director storyboard and four clip groups."""

    name = "continuity-storyboard-grid"
    description = "Builds continuity micro-shots and grouped clip prompts for S1"
    max_retries = 1

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        requested_grid = _requested_grid_type(params.get("storyboard_grid"))
        if requested_grid is None:
            return SkillResult(
                success=False,
                error=f"unsupported storyboard_grid: {params.get('storyboard_grid')}",
            )

        context = _build_story_context(params)
        transition_style = str(params.get("transition_style") or "match_cut")
        video_duration = _coerce_video_duration(params.get("video_duration"))
        micro_shots = _build_micro_shots(context)
        clip_groups = _build_clip_groups(
            context=context,
            micro_shots=micro_shots,
            transition_style=transition_style,
            video_duration=video_duration,
        )

        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": context["product_name"],
                "visual_identity": _build_visual_identity(context),
                "micro_shots": micro_shots,
                "clip_groups": clip_groups,
            },
            metadata={
                "grid_size": 12,
                "clip_group_count": 4,
                "requested_grid": requested_grid,
                "effective_grid": EFFECTIVE_GRID,
            },
        )

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(params, dict):
            return ["params must be a dict"]
        if _requested_grid_type(params.get("storyboard_grid")) is None:
            errors.append(f"unsupported storyboard_grid: {params.get('storyboard_grid')}")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        if not isinstance(data, dict):
            return ["output must be a dict"]

        errors: list[str] = []
        micro_shots = data.get("micro_shots")
        clip_groups = data.get("clip_groups")

        if not isinstance(micro_shots, list) or len(micro_shots) != 12:
            errors.append("micro_shots must contain 12 entries")
        elif not all(isinstance(shot, dict) for shot in micro_shots):
            errors.append("micro_shots entries must be dicts")
        else:
            if [shot.get("index") for shot in micro_shots] != list(range(1, 13)):
                errors.append("micro_shots indices must be 1..12")
            if any(_missing_micro_shot_fields(shot) for shot in micro_shots):
                errors.append("micro_shots missing continuity fields")

        if not isinstance(clip_groups, list) or len(clip_groups) != 4:
            errors.append("clip_groups must contain 4 entries")
        elif not all(isinstance(group, dict) for group in clip_groups):
            errors.append("clip_groups entries must be dicts")
        else:
            invalid_groups = [
                group for group in clip_groups if not isinstance(group.get("shot_indices"), list)
            ]
            if invalid_groups:
                errors.append("clip_groups shot_indices must be lists")
            elif _covered_indices(clip_groups) != list(range(1, 13)):
                errors.append("clip_groups must cover shot indices 1..12 once")

        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        context = _build_story_context(params)
        video_duration = _coerce_video_duration(params.get("video_duration"))
        micro_shots = _build_micro_shots(context)
        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": context["product_name"],
                "visual_identity": _build_visual_identity(context),
                "micro_shots": micro_shots,
                "clip_groups": _build_clip_groups(
                    context=context,
                    micro_shots=micro_shots,
                    transition_style=str(params.get("transition_style") or "match_cut"),
                    video_duration=video_duration,
                ),
            },
            metadata={
                "grid_size": 12,
                "clip_group_count": 4,
                "requested_grid": _requested_grid_type(params.get("storyboard_grid"))
                or DEFAULT_GRID_TYPE,
                "effective_grid": EFFECTIVE_GRID,
            },
        )


def _requested_grid_type(value: Any) -> Any:
    grid_type = str(value or DEFAULT_GRID_TYPE)
    if grid_type not in SUPPORTED_GRID_TYPES:
        return None
    if value is None:
        return DEFAULT_GRID_TYPE
    return value


def _extract_product_name(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return "Product"

    product_name = product_catalog.get("product_name") or product_catalog.get("name")
    if isinstance(product_name, str) and product_name:
        return product_name

    products = product_catalog.get("products")
    if isinstance(products, list) and products:
        first_product = products[0]
        if isinstance(first_product, dict):
            product_name = first_product.get("product_name") or first_product.get("name")
            if isinstance(product_name, str) and product_name:
                return product_name

    return "Product"


def _coerce_video_duration(value: Any) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return 30
    return duration if duration in {15, 30, 45, 60, 90} else 30


def _build_story_context(params: dict[str, Any]) -> dict[str, Any]:
    product_catalog = params.get("product_catalog")
    shots = _extract_storyboard_shots(params.get("storyboards"))
    product_name = _extract_product_name(product_catalog)
    brand_name = _extract_brand_name(product_catalog)
    usage_scenario = _extract_usage_scenario(product_catalog, shots)
    shot_hints = _extract_shot_hints(shots, usage_scenario, product_name)
    context = {
        "product_name": product_name,
        "brand_name": brand_name,
        "category": _extract_category(product_catalog),
        "usage_scenario": usage_scenario,
        "usps": _extract_usps(product_catalog),
        "shot_hints": shot_hints,
        "colors": _extract_color_palette(product_catalog),
        "brand_values": _extract_brand_values(product_catalog),
        "tone_keywords": _extract_tone_keywords(product_catalog),
        "visual_constraints": _extract_visual_constraints(product_catalog),
        "target_audience": _extract_target_audience(product_catalog),
        "creator_name": _extract_creator_name(product_catalog),
        "source_platform": _extract_source_platform(product_catalog),
        "distribution_platforms": _extract_distribution_platforms(product_catalog),
        "creator_style": _extract_creator_style(product_catalog),
    }
    context["director_profile"] = _build_director_profile(context)
    return context


def _extract_storyboard_shots(storyboards: Any) -> list[dict[str, Any]]:
    if not isinstance(storyboards, list):
        return []
    shots: list[dict[str, Any]] = []
    for board in storyboards:
        if not isinstance(board, dict):
            continue
        for shot in board.get("shots", []):
            if isinstance(shot, dict):
                shots.append(shot)
    return shots


def _extract_brand_name(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return ""
    brand_name = product_catalog.get("brand_name")
    return brand_name.strip() if isinstance(brand_name, str) else ""


def _extract_category(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return "product"
    category = product_catalog.get("category")
    if isinstance(category, str) and category.strip():
        return category.strip()
    return "product"


def _extract_usage_scenario(product_catalog: Any, shots: list[dict[str, Any]]) -> str:
    if isinstance(product_catalog, dict):
        usage_scenario = product_catalog.get("usage_scenario")
        if isinstance(usage_scenario, str) and usage_scenario.strip():
            return usage_scenario.strip()
    for shot in shots:
        visual = shot.get("visual") or shot.get("visual_description") or shot.get("description")
        if isinstance(visual, str) and visual.strip():
            return visual.strip()
    return "everyday lifestyle use"


def _extract_usps(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []
    raw_usps = product_catalog.get("usps") or []
    normalized: list[str] = []
    if isinstance(raw_usps, list):
        for item in raw_usps:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    normalized.append(text.strip())
    return normalized[:4]


def _extract_color_palette(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []

    palette: list[str] = []
    explicit_palette = product_catalog.get("color_palette")
    if isinstance(explicit_palette, list):
        for item in explicit_palette:
            if isinstance(item, str) and item.strip():
                palette.append(item.strip())

    colors = product_catalog.get("colors")
    if isinstance(colors, dict):
        for value in colors.values():
            if isinstance(value, str) and value.strip():
                palette.append(value.strip())
    elif isinstance(colors, list):
        for value in colors:
            if isinstance(value, str) and value.strip():
                palette.append(value.strip())

    seen: set[str] = set()
    deduped: list[str] = []
    for item in palette:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:4]


def _extract_brand_values(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []

    values = product_catalog.get("brand_values")
    if not isinstance(values, list):
        values = product_catalog.get("values")
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
    return normalized[:4]


def _extract_tone_keywords(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []

    keywords: list[str] = []
    tone = product_catalog.get("tone_of_voice")
    if isinstance(tone, dict):
        raw_keywords = tone.get("keywords") or []
        if isinstance(raw_keywords, list):
            for item in raw_keywords:
                if isinstance(item, str) and item.strip():
                    keywords.append(item.strip())
    elif isinstance(tone, str) and tone.strip():
        keywords.extend(_split_hint_text(tone))

    voice_guidelines = product_catalog.get("voice_guidelines")
    if isinstance(voice_guidelines, str) and voice_guidelines.strip():
        keywords.extend(_split_hint_text(voice_guidelines))

    seen: set[str] = set()
    deduped: list[str] = []
    for item in keywords:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:4]


def _extract_visual_constraints(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []

    constraints = product_catalog.get("visual_constraints")
    if isinstance(constraints, str) and constraints.strip():
        return _split_hint_text(constraints)[:4]
    if isinstance(constraints, list):
        normalized = []
        for item in constraints:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
        return normalized[:4]
    return []


def _extract_creator_name(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return ""
    creator_name = product_catalog.get("creator_name")
    return creator_name.strip() if isinstance(creator_name, str) else ""


def _extract_source_platform(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return ""
    source_platform = product_catalog.get("source_platform")
    return source_platform.strip() if isinstance(source_platform, str) else ""


def _extract_distribution_platforms(product_catalog: Any) -> list[str]:
    if not isinstance(product_catalog, dict):
        return []
    platforms = product_catalog.get("distribution_platforms")
    if not isinstance(platforms, list):
        return []
    normalized: list[str] = []
    for item in platforms:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
    return normalized[:3]


def _extract_creator_style(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return ""
    creator_style = product_catalog.get("creator_style")
    return creator_style.strip() if isinstance(creator_style, str) else ""


def _extract_target_audience(product_catalog: Any) -> str:
    if not isinstance(product_catalog, dict):
        return ""
    target_audience = product_catalog.get("target_audience")
    return target_audience.strip() if isinstance(target_audience, str) else ""


def _split_hint_text(value: str) -> list[str]:
    normalized = value.replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _extract_shot_hints(
    shots: list[dict[str, Any]],
    usage_scenario: str,
    product_name: str,
) -> list[str]:
    hints: list[str] = []
    for shot in shots:
        visual = shot.get("visual") or shot.get("visual_description") or shot.get("description")
        if isinstance(visual, str) and visual.strip():
            hints.append(visual.strip())
    if not hints:
        hints.append(f"{product_name} in {usage_scenario}")
    return hints[:6]


def _build_visual_identity(context: dict[str, Any]) -> dict[str, Any]:
    usage_scenario = context["usage_scenario"]
    shot_hints = context["shot_hints"]
    product_name = context["product_name"]
    category = context["category"]
    colors = list(context["colors"])
    if not colors:
        colors = _fallback_palette_for_context(usage_scenario, category)
    return {
        "location": usage_scenario,
        "lighting": _infer_lighting(usage_scenario, shot_hints[0] if shot_hints else ""),
        "product_anchor": f"same {product_name} remains the anchor across every clip",
        "color_palette": colors,
        "tone": ", ".join(context["tone_keywords"]) if context["tone_keywords"] else "",
        "constraints": context["visual_constraints"],
        "audience": context["target_audience"],
        "creator_reference": context["creator_name"],
        "platform": context["source_platform"],
        "director_profile": context["director_profile"],
    }


def _build_director_profile(context: dict[str, Any]) -> dict[str, str]:
    usage_scenario = context["usage_scenario"]
    product_name = context["product_name"]
    target_audience = context["target_audience"] or "the viewer"
    usps = context["usps"]
    brand_values = context["brand_values"]
    source_platform = context["source_platform"]
    distribution_platforms = context["distribution_platforms"]
    creator_style = context["creator_style"]

    primary_usp = usps[0] if usps else "everyday ease"
    brand_promise = brand_values[0] if brand_values else primary_usp
    platform_pacing = _director_platform_pacing(source_platform, distribution_platforms)
    creator_cadence = (
        creator_style
        if creator_style
        else "steady product-first pacing with clear cause-and-effect continuity"
    )
    return {
        "story_arc": (
            f"{usage_scenario} need -> hands-on {product_name} use -> visible proof -> CTA memory"
        ),
        "audience_tension": f"resolve {target_audience}'s {usage_scenario} need",
        "brand_promise": brand_promise,
        "platform_pacing": platform_pacing,
        "creator_cadence": creator_cadence,
    }


def _director_platform_pacing(source_platform: str, distribution_platforms: list[str]) -> str:
    platforms = [source_platform, *distribution_platforms]
    normalized = {platform.lower() for platform in platforms if platform}
    if normalized & {"tiktok", "instagram", "reels"}:
        return "vertical short-form pacing with a fast hook and readable proof beat"
    if normalized & {"amazon", "shopify"}:
        return "retail proof pacing that keeps product benefits legible"
    if normalized & {"youtube", "youtube shorts"}:
        return "creator-led pacing with a clear setup and payoff"
    return "balanced lifestyle pacing with visible product continuity"


def _infer_lighting(usage_scenario: str, first_hint: str) -> str:
    combined = f"{usage_scenario} {first_hint}".lower()
    if any(token in combined for token in ("night", "2 am", "evening", "bedroom")):
        return "soft warm low-light"
    if any(token in combined for token in ("office", "desk", "work", "studio")):
        return "clean daylight with soft contrast"
    if any(token in combined for token in ("outdoor", "sun", "park")):
        return "natural daylight with soft highlights"
    if any(token in combined for token in ("kitchen", "counter")):
        return "bright countertop lighting with warm practicals"
    return "clean lifestyle lighting"


def _fallback_palette_for_context(usage_scenario: str, category: str) -> list[str]:
    combined = f"{usage_scenario} {category}".lower()
    if "night" in combined or "bedroom" in combined:
        return ["warm white", "muted beige", "soft shadow"]
    if "office" in combined or "desk" in combined:
        return ["soft white", "cool neutral", "subtle matte gray"]
    if "outdoor" in combined:
        return ["daylight white", "leaf green", "sky blue"]
    return ["warm white", "neutral matte", "soft accent color"]


def _missing_micro_shot_fields(shot: Any) -> bool:
    if not isinstance(shot, dict):
        return True
    return not all(
        [
            shot.get("continuity_in"),
            shot.get("continuity_out"),
            shot.get("transition_out"),
            "no close-up infant face" in (shot.get("safety_notes") or []),
        ]
    )


def _covered_indices(clip_groups: list[Any]) -> list[int]:
    return [
        index
        for group in clip_groups
        if isinstance(group, dict)
        for index in group.get("shot_indices", [])
    ]


def _build_micro_shots(context: dict[str, Any]) -> list[dict[str, Any]]:
    product_name = context["product_name"]
    category = context["category"]
    usage_scenario = context["usage_scenario"]
    brand_name = context["brand_name"]
    usps = context["usps"] or [f"everyday {category} ease"]
    shot_hints = context["shot_hints"]

    templates = [
        ("context_setup", 1.5, "close-up, slow push-in", "setup need", "user reaches toward the product", "match cut into product introduction"),
        ("context_setup", 1.5, "close-up handheld", "same user motion continues", "product enters active use", "match cut into first interaction"),
        ("product_intro", 1.0, "medium close-up", "same product remains centered", "hands prepare the product for use", "match cut to product interaction"),
        ("product_action", 2.0, "over-shoulder", "hands stay aligned across the cut", "first feature interaction starts", "action cut on product interaction"),
        ("product_action", 2.0, "insert close-up", "same feature detail remains framed", "usp proof becomes visible", "action cut to feedback detail"),
        ("product_action", 2.0, "static close-up", "same product control surface remains visible", "usage settles into a repeatable rhythm", "soft cut to payoff"),
        ("result_proof", 2.0, "medium shot", "same location and product stay visible", "user reaction softens as the usp lands", "match cut on reach to detail"),
        ("result_proof", 2.0, "over-shoulder", "same product remains in hand", "second benefit is demonstrated", "action cut to proof detail"),
        ("result_proof", 2.0, "close-up", "same framing preserves product continuity", "proof detail resolves into a calm payoff", "soft crossfade to emotional close"),
        ("emotional_close", 1.5, "medium shot", "same scene holds steady", "brand mood closes the lifestyle arc", "soft crossfade to hero shot"),
        ("cta", 1.5, "static beauty shot", "same product remains the hero anchor", "product beauty shot holds for CTA", "match cut to CTA interaction"),
        ("cta", 1.5, "close-up", "same hero framing remains in background", "CTA gesture or end card finishes the sequence", "fade out"),
    ]

    shots: list[dict[str, Any]] = []
    for index, (beat, duration, camera, continuity_in, continuity_out, transition_out) in enumerate(templates, start=1):
        hint = shot_hints[(index - 1) % len(shot_hints)]
        usp = usps[(index - 1) % len(usps)]
        visual = _compose_micro_shot_visual(
            beat=beat,
            hint=hint,
            product_name=product_name,
            brand_name=brand_name,
            usage_scenario=usage_scenario,
            usp=usp,
        )
        action = _compose_micro_shot_action(
            beat=beat,
            product_name=product_name,
            usp=usp,
        )
        shots.append({
            "index": index,
            "beat": beat,
            "duration": duration,
            "visual": visual,
            "action": action,
            "camera": camera,
            "continuity_in": continuity_in,
            "continuity_out": continuity_out,
            "transition_out": transition_out,
            "safety_notes": list(SAFETY_NOTES),
        })
    return shots


def _compose_micro_shot_visual(
    *,
    beat: str,
    hint: str,
    product_name: str,
    brand_name: str,
    usage_scenario: str,
    usp: str,
) -> str:
    brand_prefix = f"{brand_name} " if brand_name else ""
    if beat == "context_setup":
        return f"{hint} in {usage_scenario}, with {brand_prefix}{product_name} entering the frame naturally"
    if beat == "product_intro":
        return f"{brand_prefix}{product_name} is introduced clearly against the same scene, highlighting {usp}"
    if beat == "product_action":
        return f"{brand_prefix}{product_name} in active use, focusing on {usp} while preserving the same environment"
    if beat == "result_proof":
        return f"{hint} resolves into visible payoff for {usp}, keeping {product_name} centered"
    if beat == "emotional_close":
        return f"{usage_scenario} calms down around {product_name}, carrying a warm brand payoff"
    return f"{brand_prefix}{product_name} hero shot with a clear CTA-ready composition"


def _compose_micro_shot_action(*, beat: str, product_name: str, usp: str) -> str:
    if beat == "context_setup":
        return f"user need becomes clear before touching {product_name}"
    if beat == "product_intro":
        return f"hands position {product_name} to set up {usp}"
    if beat == "product_action":
        return f"product interaction demonstrates {usp}"
    if beat == "result_proof":
        return f"user payoff confirms {usp}"
    if beat == "emotional_close":
        return f"scene breathes after using {product_name}"
    return f"CTA closes on {product_name} with a direct purchase cue"


def _build_clip_groups(
    context: dict[str, Any],
    micro_shots: list[dict[str, Any]],
    transition_style: str,
    video_duration: int = 30,
) -> list[dict[str, Any]]:
    product_name = context["product_name"]
    usage_scenario = context["usage_scenario"]
    usps = context["usps"] or ["everyday ease"]
    brand_values = context["brand_values"]
    tone_keywords = context["tone_keywords"]
    visual_constraints = context["visual_constraints"]
    creator_name = context["creator_name"]
    source_platform = context["source_platform"]
    distribution_platforms = context["distribution_platforms"]
    creator_style = context["creator_style"]
    target_audience = context["target_audience"]
    director_profile = context["director_profile"]
    first_transition_type = (
        "match_cut" if transition_style == "match_cut" else transition_style
    )
    durations = _clip_group_durations(video_duration)
    groups: list[dict[str, Any]] = []
    prompt_suffix = [
        "Keep the same location, same product anchor, and seamless hand continuity.",
        f"Focus on the product interaction and land the usp: {usps[0]}.",
        "Show visible user payoff while keeping the framing calm and product-centered.",
        "Close with a clean hero shot and direct CTA-ready composition.",
    ]
    transition_notes = [
        "match cut from setup to first product interaction",
        "action cut from feature interaction to user payoff",
        "soft crossfade from proof detail to hero close",
        None,
    ]
    transition_types = [
        first_transition_type,
        "action_cut",
        "soft_crossfade",
        "soft_crossfade",
    ]

    for group_idx in range(4):
        chunk = micro_shots[group_idx * 3:(group_idx + 1) * 3]
        scene_beat = _scene_beat_for_group(group_idx)
        beat_summary = _summarize_group_beats(chunk)
        transition_intent = _transition_intent_for_group(
            group_idx=group_idx,
            scene_beat=scene_beat,
            transition_type=transition_types[group_idx],
            director_profile=director_profile,
        )
        seedance_prompt = " ".join(
            f"Shot {shot['index']}: {shot['visual']} Action: {shot['action']}."
            for shot in chunk
        )
        brand_tone_clause = ""
        if tone_keywords:
            brand_tone_clause = f" Brand tone: {', '.join(tone_keywords)}."
        brand_values_clause = ""
        if brand_values:
            brand_values_clause = f" Brand values to preserve: {', '.join(brand_values)}."
        visual_constraints_clause = ""
        if visual_constraints:
            visual_constraints_clause = (
                f" Visual constraints: {', '.join(visual_constraints)}."
            )
        creator_clause = ""
        if creator_name:
            creator_clause = f" Keep {creator_name}'s creator-facing delivery authentic."
        platform_clause = ""
        if source_platform:
            platform_clause = f" Native to {source_platform} vertical short-form pacing."
        distribution_clause = ""
        if distribution_platforms:
            distribution_clause = (
                f" Final continuity should still travel well to {', '.join(distribution_platforms)}."
            )
        creator_style_clause = ""
        if creator_style:
            creator_style_clause = f" Preserve creator style: {creator_style}."
        audience_clause = ""
        if target_audience:
            audience_clause = f" Keep the lifestyle cues relevant to {target_audience}."
        director_profile_clause = (
            f" Director story arc: {director_profile['story_arc']}."
            f" Audience tension: {director_profile['audience_tension']}."
            f" Brand promise: {director_profile['brand_promise']}."
            f" Platform pacing: {director_profile['platform_pacing']}."
            f" Creator cadence: {director_profile['creator_cadence']}."
        )
        group = {
            "clip_index": group_idx + 1,
            "shot_indices": [shot["index"] for shot in chunk],
            "duration": durations[group_idx],
            "purpose": ["context setup", "product action", "result proof", "emotional close and CTA"][group_idx],
            "scene_beat": scene_beat,
            "beat_summary": beat_summary,
            "transition_intent": transition_intent,
            "director_profile": director_profile,
            "seedance_prompt": (
                f"{product_name} continuity sequence in {usage_scenario}. "
                f"{seedance_prompt} {prompt_suffix[group_idx]}"
                f" Narrative beat: {scene_beat}. Beat summary: {beat_summary}."
                f" Transition intent: {transition_intent}."
                f"{brand_tone_clause}{brand_values_clause}{visual_constraints_clause}"
                f"{creator_clause}{platform_clause}{distribution_clause}{creator_style_clause}"
                f"{audience_clause} {director_profile_clause}"
            ),
            "transition_type": transition_types[group_idx],
        }
        if transition_notes[group_idx]:
            group["transition_to_next"] = transition_notes[group_idx]
        groups.append(group)
    return groups


def _scene_beat_for_group(group_idx: int) -> str:
    beats = [
        "context_setup",
        "product_interaction",
        "proof_payoff",
        "cta_close",
    ]
    return beats[group_idx]


def _summarize_group_beats(chunk: list[dict[str, Any]]) -> str:
    beats: list[str] = []
    for shot in chunk:
        beat = shot.get("beat")
        if isinstance(beat, str) and beat:
            beats.append(beat)
    if not beats:
        return "continuity progression"
    return " -> ".join(beats)


def _transition_intent_for_group(
    *,
    group_idx: int,
    scene_beat: str,
    transition_type: str,
    director_profile: dict[str, str],
) -> str:
    intents = [
        "bridge the setup into first hands-on product contact",
        "carry feature interaction into visible user payoff",
        "resolve proof into an emotional hero close",
        "hold the final brand memory and CTA without breaking continuity",
    ]
    if group_idx < len(intents):
        base_intent = intents[group_idx]
    else:
        base_intent = f"preserve {scene_beat} continuity through {transition_type}"
    if group_idx == 0:
        return f"{base_intent} while {director_profile['audience_tension']}"
    if group_idx == 1:
        return f"{base_intent} around {director_profile['brand_promise']}"
    if group_idx == 2:
        return f"{base_intent} using {director_profile['platform_pacing']}"
    return f"{base_intent} with {director_profile['creator_cadence']}"


def _clip_group_durations(video_duration: int) -> list[int]:
    base = [4, 6, 6, 5]
    if video_duration >= sum(base):
        return base
    clip_count = len(base)
    min_duration = 4
    if video_duration <= min_duration * clip_count:
        return [min_duration] * clip_count

    remaining = video_duration - min_duration * clip_count
    durations = [min_duration] * clip_count
    index = 0
    while remaining > 0:
        durations[index % clip_count] += 1
        remaining -= 1
        index += 1
    return durations


SkillRegistry.register(ContinuityStoryboardGridSkill())
