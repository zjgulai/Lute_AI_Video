from __future__ import annotations

import pytest

from src.pipeline.candidate_scorer import score_candidate


@pytest.mark.asyncio
async def test_clip_candidate_scores_director_intent_metadata_from_prompt() -> None:
    result = await score_candidate(
        step_name="seedance_clips",
        candidate_data={
            "prompt_used": (
                "Warm bottle scene. Narrative beat: context_setup. "
                "Beat summary: context_setup -> product_intro. "
                "Transition intent: bridge setup into product interaction."
            ),
            "duration": 5,
            "target_duration": 5,
            "file_size": 4096,
            "continuity_frame": True,
        },
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0
    assert result["overall"] > 0.8
    assert "director_intent=1.00" in result["explanation"]


@pytest.mark.asyncio
async def test_clip_candidate_prefers_structured_director_intent_metadata() -> None:
    result = await score_candidate(
        step_name="seedance_clips",
        candidate_data={
            "prompt_used": "Warm bottle scene with soft natural lighting.",
            "scene_beat": "context_setup",
            "beat_summary": "context_setup -> product_intro",
            "transition_intent": "bridge setup into product interaction",
            "duration": 5,
            "target_duration": 5,
            "file_size": 4096,
            "continuity_frame": True,
        },
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0
    assert result["overall"] > 0.8


@pytest.mark.asyncio
async def test_clip_candidate_penalizes_missing_director_intent_metadata() -> None:
    result = await score_candidate(
        step_name="seedance_clips",
        candidate_data={
            "prompt_used": "Warm bottle scene with soft natural lighting.",
            "duration": 5,
            "target_duration": 5,
            "file_size": 4096,
            "continuity_frame": True,
        },
        params={},
    )
    full_intent = await score_candidate(
        step_name="seedance_clips",
        candidate_data={
            "prompt_used": (
                "Warm bottle scene. Narrative beat: context_setup. "
                "Beat summary: context_setup -> product_intro. "
                "Transition intent: bridge setup into product interaction."
            ),
            "duration": 5,
            "target_duration": 5,
            "file_size": 4096,
            "continuity_frame": True,
        },
        params={},
    )

    assert result["breakdown"]["director_intent"] == 0.4
    assert result["overall"] < full_intent["overall"]


@pytest.mark.asyncio
async def test_clip_candidate_uses_prompt_text_as_director_intent_fallback() -> None:
    result = await score_candidate(
        step_name="seedance_clips",
        candidate_data={
            "prompt_used": (
                "Warm bottle scene. Narrative beat: context_setup. "
                "Beat summary: context_setup -> product_intro. "
                "Transition intent: bridge setup into product interaction."
            ),
            "scene_beat": "",
            "beat_summary": "",
            "transition_intent": "",
            "duration": 5,
            "target_duration": 5,
            "file_size": 4096,
            "continuity_frame": True,
        },
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0


@pytest.mark.asyncio
async def test_video_prompts_candidate_scores_director_intent_metadata() -> None:
    result = await score_candidate(
        step_name="video_prompts",
        candidate_data=[
            {
                "segment_prompt": (
                    "Bottle warmer clip. Narrative beat: context_setup. "
                    "Beat summary: context_setup -> product_intro. "
                    "Transition intent: bridge setup into product interaction."
                ),
                "shot_type": "continuity_group",
                "camera": "smooth continuity handheld",
                "lighting": "soft warm low-light",
                "transition_type": "match_cut",
                "transition_to_next": "match cut to product contact",
                "clip_index": 1,
                "duration_seconds": 4,
            }
        ],
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0
    assert result["breakdown"]["transition_metadata"] == 1.0


@pytest.mark.asyncio
async def test_video_prompts_candidate_prefers_structured_director_intent_metadata() -> None:
    result = await score_candidate(
        step_name="video_prompts",
        candidate_data=[
            {
                "segment_prompt": "Bottle warmer clip in soft low light.",
                "scene_beat": "context_setup",
                "beat_summary": "context_setup -> product_intro",
                "transition_intent": "bridge setup into product interaction",
                "shot_type": "continuity_group",
                "camera": "smooth continuity handheld",
                "lighting": "soft warm low-light",
                "transition_type": "match_cut",
                "transition_to_next": "match cut to product contact",
                "clip_index": 1,
                "duration_seconds": 4,
            }
        ],
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0


@pytest.mark.asyncio
async def test_video_prompts_candidate_uses_prompt_text_as_director_intent_fallback() -> None:
    result = await score_candidate(
        step_name="video_prompts",
        candidate_data=[
            {
                "segment_prompt": (
                    "Bottle warmer clip. Narrative beat: context_setup. "
                    "Beat summary: context_setup -> product_intro. "
                    "Transition intent: bridge setup into product interaction."
                ),
                "scene_beat": "",
                "beat_summary": "",
                "transition_intent": "",
                "shot_type": "continuity_group",
                "camera": "smooth continuity handheld",
                "lighting": "soft warm low-light",
                "transition_type": "match_cut",
                "transition_to_next": "match cut to product contact",
                "clip_index": 1,
                "duration_seconds": 4,
            }
        ],
        params={},
    )

    assert result["breakdown"]["director_intent"] == 1.0


@pytest.mark.asyncio
async def test_vlog_strategy_candidate_scores_shot_plan_director_intent() -> None:
    result = await score_candidate(
        step_name="vlog_strategy",
        candidate_data={
            "shots": [
                {
                    "shot_type": "close-up",
                    "visual_description": "Front view close-up in soft daylight",
                    "product_angle": "主视图",
                    "voiceover": "轻松开启一天的节奏。",
                },
                {
                    "shot_type": "mid-shot",
                    "visual_description": "Hands using the product in a calm home scene",
                    "product_angle": "佩戴图",
                    "voiceover": "忙碌时也能保持从容。",
                },
            ]
        },
        params={"brand_guidelines": "warm family-first tiktok brand"},
    )

    assert result["breakdown"]["director_intent"] == 1.0
    assert result["breakdown"]["structure"] >= 0.6
