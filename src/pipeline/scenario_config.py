"""Shared scenario step-order definitions for pipeline/runtime/UI metadata."""

from __future__ import annotations

SCENARIO_STEP_ORDERS: dict[str, list[str]] = {
    "s1": [
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "thumbnail_prompts",
        "seedance_clips",
        "tts_audio",
        "thumbnail_images",
        "assemble_final",
        "audit",
    ],
    "s2": [
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "thumbnail_prompts",
        "seedance_clips",
        "tts_audio",
        "thumbnail_images",
        "assemble_final",
        "audit",
    ],
    "s3": [
        "video_analysis",
        "character_identity",
        "remix_script",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "thumbnail_prompts",
        "seedance_clips",
        "tts_audio",
        "thumbnail_images",
        "assemble_final",
        "audit",
    ],
    "s4": [
        "scripts",
        "continuity_storyboard_grid",
        "video_prompts",
        "thumbnails",
        "seedance_clips",
        "tts_audio",
        "assemble_final",
        "audit",
    ],
    "s5": [
        "vlog_strategy",
        "continuity_storyboard_grid",
        "video_prompts",
        "seedance_clips",
        "tts_audio",
        "assemble_final",
        "audit",
    ],
}


def get_scenario_step_order(scenario: str) -> list[str]:
    """Return the canonical step order for a scenario, falling back to S1."""
    return list(SCENARIO_STEP_ORDERS.get(scenario, SCENARIO_STEP_ORDERS["s1"]))
