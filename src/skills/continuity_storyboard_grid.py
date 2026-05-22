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

        product_name = _extract_product_name(params.get("product_catalog"))
        transition_style = str(params.get("transition_style") or "match_cut")
        video_duration = _coerce_video_duration(params.get("video_duration"))
        micro_shots = _build_bottle_warmer_micro_shots()
        clip_groups = _build_clip_groups(
            product_name=product_name,
            transition_style=transition_style,
            video_duration=video_duration,
        )

        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": product_name,
                "visual_identity": {
                    "location": "warm night kitchen and nursery doorway",
                    "lighting": "soft warm low-light",
                    "product_anchor": "same bottle warmer on the same countertop",
                    "color_palette": [
                        "warm white",
                        "soft green indicator",
                        "matte neutral counter",
                    ],
                },
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
        product_name = _extract_product_name(params.get("product_catalog"))
        video_duration = _coerce_video_duration(params.get("video_duration"))
        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": product_name,
                "visual_identity": {
                    "location": "warm night kitchen and nursery doorway",
                    "lighting": "soft warm low-light",
                    "product_anchor": "same bottle warmer on the same countertop",
                    "color_palette": [
                        "warm white",
                        "soft green indicator",
                        "matte neutral counter",
                    ],
                },
                "micro_shots": _build_bottle_warmer_micro_shots(),
                "clip_groups": _build_clip_groups(
                    product_name=product_name,
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


def _build_bottle_warmer_micro_shots() -> list[dict[str, Any]]:
    raw_shots = [
        (
            "pain_setup",
            1.5,
            "2:00 AM clock in a dim kitchen",
            "clock ticks as the parent enters frame",
            "close-up, slow push-in",
            "dark quiet kitchen",
            "parent reaches toward a cold bottle",
            "match cut on hand movement",
        ),
        (
            "pain_setup",
            1.5,
            "cold bottle on the counter",
            "parent picks up the cold bottle and checks it",
            "close-up handheld",
            "hand reaches from clock shot",
            "bottle moves toward the warmer",
            "match cut on bottle movement",
        ),
        (
            "pain_setup",
            1.0,
            "parent approaches the warmer on the same countertop",
            "parent sets the bottle beside the warmer",
            "medium close-up",
            "same countertop and bottle",
            "bottle is ready to be placed into warmer",
            "match cut to placement",
        ),
        (
            "product_action",
            2.0,
            "bottle placed into the warmer",
            "parent opens the warmer and places the bottle inside",
            "over-shoulder",
            "same bottle enters frame",
            "hand moves toward control button",
            "action cut on hand",
        ),
        (
            "product_action",
            2.0,
            "finger presses the warmer button",
            "parent presses one button on the warmer",
            "insert close-up",
            "hand from placement shot",
            "indicator light turns on",
            "action cut to indicator",
        ),
        (
            "product_action",
            2.0,
            "soft green indicator light on warmer",
            "indicator glows while the warmer runs",
            "static close-up",
            "same control panel",
            "parent waits calmly nearby",
            "soft cut to waiting moment",
        ),
        (
            "result_proof",
            2.0,
            "short waiting moment in warm kitchen light",
            "parent leans on counter and relaxes",
            "medium shot",
            "same kitchen and warmer visible",
            "parent reaches back to warmer",
            "match cut on reach",
        ),
        (
            "result_proof",
            2.0,
            "bottle removed from the warmer",
            "parent removes the warmed bottle",
            "over-shoulder",
            "same warmer and bottle",
            "parent checks bottle temperature",
            "action cut to temperature check",
        ),
        (
            "result_proof",
            2.0,
            "temperature check on wrist",
            "parent tests the bottle temperature on wrist",
            "close-up",
            "same bottle in hand",
            "parent turns toward nursery doorway",
            "soft crossfade to doorway",
        ),
        (
            "emotional_close",
            1.5,
            "calm nursery doorway with warm light",
            "parent pauses at doorway holding bottle",
            "medium shot",
            "same bottle visible",
            "scene transitions to product beauty shot",
            "soft crossfade",
        ),
        (
            "cta",
            1.5,
            "product beauty shot on clean countertop",
            "warmer sits centered with soft glow",
            "static beauty shot",
            "same warmer and counter",
            "phone enters frame for CTA",
            "match cut to phone",
        ),
        (
            "cta",
            1.5,
            "phone shop action beside warmer",
            "hand taps Shop Now on phone screen",
            "close-up",
            "same product remains in background",
            "end card",
            "fade out",
        ),
    ]

    return [
        {
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
        }
        for index, (
            beat,
            duration,
            visual,
            action,
            camera,
            continuity_in,
            continuity_out,
            transition_out,
        ) in enumerate(raw_shots, start=1)
    ]


def _build_clip_groups(
    product_name: str,
    transition_style: str,
    video_duration: int = 30,
) -> list[dict[str, Any]]:
    first_transition_type = (
        "match_cut" if transition_style == "match_cut" else transition_style
    )
    durations = _clip_group_durations(video_duration)
    return [
        {
            "clip_index": 1,
            "shot_indices": [1, 2, 3],
            "duration": durations[0],
            "purpose": "pain setup",
            "seedance_prompt": (
                f"{product_name} night-feed setup: a continuous 2 AM kitchen "
                "sequence, clock close-up, parent picks up a cold bottle, parent "
                "moves toward the warmer. Keep the same warm low-light kitchen, "
                "same bottle, and same countertop."
            ),
            "transition_to_next": (
                "match cut from cold bottle movement to bottle placement"
            ),
            "transition_type": first_transition_type,
        },
        {
            "clip_index": 2,
            "shot_indices": [4, 5, 6],
            "duration": durations[1],
            "purpose": "product action",
            "seedance_prompt": (
                f"{product_name} product action: parent opens the warmer, places "
                "the bottle inside, presses one button, and the soft green "
                "indicator light turns on. Use the same warmer, same bottle, "
                "same countertop, and a smooth close-up sequence."
            ),
            "transition_to_next": "action cut from indicator light to bottle removal",
            "transition_type": "action_cut",
        },
        {
            "clip_index": 3,
            "shot_indices": [7, 8, 9],
            "duration": durations[2],
            "purpose": "result proof",
            "seedance_prompt": (
                f"{product_name} result proof: parent waits calmly, removes the "
                "warmed bottle, and checks the bottle temperature on wrist. Keep "
                "the product visible and avoid infant close-ups."
            ),
            "transition_to_next": (
                "soft crossfade from temperature check to product beauty shot"
            ),
            "transition_type": "soft_crossfade",
        },
        {
            "clip_index": 4,
            "shot_indices": [10, 11, 12],
            "duration": durations[3],
            "purpose": "emotional close and CTA",
            "seedance_prompt": (
                f"{product_name} closing CTA: parent pauses near a warm nursery "
                "doorway, cut to the warmer beauty shot on the countertop, then "
                "a phone taps Shop Now. Keep the scene calm and product-centered."
            ),
            "transition_type": "soft_crossfade",
        },
    ]


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
