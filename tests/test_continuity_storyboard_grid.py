from __future__ import annotations

import pytest

from src.skills.continuity_storyboard_grid import ContinuityStoryboardGridSkill
from src.skills.registry import SkillRegistry


@pytest.fixture
def bottle_warmer_params() -> dict:
    return {
        "product_catalog": {
            "product_name": "Momcozy Nutri Bottle Warmer",
            "brand_name": "Momcozy",
            "category": "baby bottle warmer",
            "usage_scenario": "2 AM night feeds at home",
            "usps": [
                "quick night-feed warming",
                "precise temperature control",
                "gentle keep-warm mode",
            ],
            "colors": {
                "primary": "sage green",
                "secondary": "warm white",
            },
        },
        "storyboards": [
            {
                "script_id": "script-BRIEF-001-en",
                "total_duration": 30,
                "shots": [
                    {
                        "id": 1,
                        "start_time": 0,
                        "end_time": 3,
                        "visual": "A tired parent holds a cold bottle at 2 AM.",
                    }
                ],
            }
        ],
        "storyboard_grid": "12",
        "transition_style": "match_cut",
    }


@pytest.mark.asyncio
async def test_generates_12_grid_for_bottle_warmer(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    assert result.success is True
    data = result.data
    assert data["grid_type"] == "12-grid"
    assert data["product_name"] == "Momcozy Nutri Bottle Warmer"
    assert len(data["micro_shots"]) == 12
    assert [s["index"] for s in data["micro_shots"]] == list(range(1, 13))


@pytest.mark.asyncio
async def test_grid_24_is_explicitly_downgraded_to_12(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()
    bottle_warmer_params["storyboard_grid"] = "24"

    result = await skill.execute(bottle_warmer_params)

    assert result.success is True
    assert result.metadata["requested_grid"] == "24"
    assert result.metadata["effective_grid"] == 12
    assert result.data["grid_type"] == "12-grid"


@pytest.mark.asyncio
async def test_grid_auto_is_explicitly_downgraded_to_12(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()
    bottle_warmer_params["storyboard_grid"] = "auto"

    result = await skill.execute(bottle_warmer_params)

    assert result.success is True
    assert result.metadata["requested_grid"] == "auto"
    assert result.metadata["effective_grid"] == 12
    assert result.data["grid_type"] == "12-grid"


@pytest.mark.asyncio
async def test_grid_9_is_explicitly_downgraded_to_12(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()
    bottle_warmer_params["storyboard_grid"] = 9

    result = await skill.execute(bottle_warmer_params)

    assert result.success is True
    assert result.metadata["requested_grid"] == 9
    assert result.metadata["effective_grid"] == 12
    assert result.data["grid_type"] == "12-grid"


@pytest.mark.asyncio
async def test_output_includes_visual_identity(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    visual_identity = result.data["visual_identity"]
    assert visual_identity["location"] == "2 AM night feeds at home"
    assert visual_identity["lighting"] == "soft warm low-light"
    assert "Momcozy Nutri Bottle Warmer" in visual_identity["product_anchor"]
    assert "sage green" in visual_identity["color_palette"]


@pytest.mark.asyncio
async def test_micro_shots_have_continuity_fields(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    for shot in result.data["micro_shots"]:
        assert shot["continuity_in"]
        assert shot["continuity_out"]
        assert shot["transition_out"]
        assert "no close-up infant face" in shot["safety_notes"]


@pytest.mark.asyncio
async def test_micro_shots_do_not_share_safety_notes_list(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    first, second = result.data["micro_shots"][:2]
    assert first["safety_notes"] == second["safety_notes"]
    assert first["safety_notes"] is not second["safety_notes"]


@pytest.mark.asyncio
async def test_clip_groups_cover_all_micro_shots_once(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    groups = result.data["clip_groups"]
    assert len(groups) == 4
    covered = [idx for group in groups for idx in group["shot_indices"]]
    assert covered == list(range(1, 13))
    assert groups[0]["transition_to_next"] == "match cut from setup to first product interaction"
    assert groups[1]["transition_to_next"] == "action cut from feature interaction to user payoff"
    assert groups[2]["transition_to_next"] == "soft crossfade from proof detail to hero close"
    assert "transition_to_next" not in groups[3]
    assert groups[0]["scene_beat"] == "context_setup"
    assert groups[1]["scene_beat"] == "product_interaction"
    assert groups[2]["scene_beat"] == "proof_payoff"
    assert groups[3]["scene_beat"] == "cta_close"
    assert groups[0]["beat_summary"] == "context_setup -> context_setup -> product_intro"
    assert groups[0]["transition_intent"].startswith("bridge the setup into first hands-on product contact")
    assert "resolve the viewer's 2 AM night feeds at home need" in groups[0]["transition_intent"]
    assert groups[0]["director_profile"]["brand_promise"] == "quick night-feed warming"
    assert "Momcozy Nutri Bottle Warmer" in groups[0]["seedance_prompt"]
    assert "2 AM night feeds at home" in groups[0]["seedance_prompt"]


@pytest.mark.asyncio
async def test_semantics_follow_usage_scenario_and_usps():
    skill = ContinuityStoryboardGridSkill()
    result = await skill.execute(
        {
            "product_catalog": {
                "product_name": "LactFit Wearable Breast Pump X1",
                "brand_name": "LactFit",
                "category": "wearable breast pump",
                "usage_scenario": "office commute and desk pumping routine",
                "usps": ["hands-free pumping", "quiet operation"],
                "colors": ["soft ivory", "muted rose"],
            },
            "storyboards": [
                {
                    "shots": [
                        {
                            "id": 1,
                            "start_time": 0,
                            "end_time": 3,
                            "visual": "A mother adjusts the pump under a blazer at her desk.",
                        }
                    ]
                }
            ],
            "storyboard_grid": "12",
            "transition_style": "match_cut",
        }
    )

    assert result.success is True
    assert result.data["visual_identity"]["location"] == "office commute and desk pumping routine"
    assert result.data["visual_identity"]["lighting"] == "clean daylight with soft contrast"
    assert "soft ivory" in result.data["visual_identity"]["color_palette"]
    assert "hands-free pumping" in result.data["micro_shots"][2]["visual"]
    assert "office commute and desk pumping routine" in result.data["clip_groups"][0]["seedance_prompt"]
    assert "quiet operation" in result.data["clip_groups"][1]["seedance_prompt"]


@pytest.mark.asyncio
async def test_brand_campaign_semantics_follow_brand_package():
    skill = ContinuityStoryboardGridSkill()
    result = await skill.execute(
        {
            "product_catalog": {
                "product_name": "MomCozy",
                "brand_name": "MomCozy",
                "category": "brand_campaign",
                "usage_scenario": "living room family routine",
                "values": ["safety", "comfort", "modern motherhood"],
                "voice_guidelines": "warm, supportive, never preachy",
                "visual_constraints": "soft natural light; pastel palette",
                "colors": ["pastel peach", "warm white"],
            },
            "storyboards": [
                {
                    "shots": [
                        {
                            "id": 1,
                            "start_time": 0,
                            "end_time": 3,
                            "visual": "A calm family moment around the sofa with product nearby.",
                        }
                    ]
                }
            ],
            "storyboard_grid": "12",
            "transition_style": "match_cut",
        }
    )

    assert result.success is True
    identity = result.data["visual_identity"]
    prompt = result.data["clip_groups"][0]["seedance_prompt"]

    assert identity["tone"] == "warm, supportive, never preachy"
    assert "soft natural light" in identity["constraints"]
    assert "pastel palette" in identity["constraints"]
    assert "pastel peach" in identity["color_palette"]
    assert identity["director_profile"]["brand_promise"] == "safety"
    assert "Brand tone: warm, supportive, never preachy." in prompt
    assert "Brand values to preserve: safety, comfort, modern motherhood." in prompt
    assert "Visual constraints: soft natural light, pastel palette." in prompt
    assert "Director story arc: living room family routine need -> hands-on MomCozy use -> visible proof -> CTA memory." in prompt
    assert "Brand promise: safety." in prompt


@pytest.mark.asyncio
async def test_influencer_remix_semantics_follow_creator_platform_and_style():
    skill = ContinuityStoryboardGridSkill()
    result = await skill.execute(
        {
            "product_catalog": {
                "product_name": "LactFit X1",
                "brand_name": "LactFit",
                "category": "influencer_remix",
                "usage_scenario": "desk-side wearable pump demo",
                "usps": ["quiet pumping"],
                "creator_name": "Jess",
                "source_platform": "instagram",
                "distribution_platforms": ["instagram", "tiktok"],
                "creator_style": "Kept energetic style and direct creator pacing",
                "voice_guidelines": "Keep creator reaction rhythm and short punchlines",
            },
            "storyboards": [
                {
                    "shots": [
                        {
                            "id": 1,
                            "start_time": 0,
                            "end_time": 3,
                            "visual": "Creator points at the pump while leaning toward the camera.",
                        }
                    ]
                }
            ],
            "storyboard_grid": "12",
            "transition_style": "match_cut",
        }
    )

    assert result.success is True
    identity = result.data["visual_identity"]
    prompt = result.data["clip_groups"][0]["seedance_prompt"]

    assert identity["creator_reference"] == "Jess"
    assert identity["platform"] == "instagram"
    assert identity["director_profile"]["platform_pacing"] == "vertical short-form pacing with a fast hook and readable proof beat"
    assert identity["director_profile"]["creator_cadence"] == "Kept energetic style and direct creator pacing"
    assert "Brand tone: Keep creator reaction rhythm and short punchlines." in prompt
    assert "Keep Jess's creator-facing delivery authentic." in prompt
    assert "Native to instagram vertical short-form pacing." in prompt
    assert "Final continuity should still travel well to instagram, tiktok." in prompt
    assert "Preserve creator style: Kept energetic style and direct creator pacing." in prompt
    assert "Platform pacing: vertical short-form pacing with a fast hook and readable proof beat." in prompt
    assert "Creator cadence: Kept energetic style and direct creator pacing." in prompt


@pytest.mark.asyncio
async def test_product_direct_semantics_follow_platform_tone_and_audience():
    skill = ContinuityStoryboardGridSkill()
    result = await skill.execute(
        {
            "product_catalog": {
                "product_name": "LactFit X1",
                "brand_name": "LactFit",
                "category": "breast_pumps",
                "usage_scenario": "morning desk-side pumping routine",
                "usps": ["hands-free pumping"],
                "distribution_platforms": ["tiktok", "amazon"],
                "tone_of_voice": "warm, empowering, practical",
                "target_audience": "working mothers 25-40",
                "color_palette": ["sage green", "warm cream"],
            },
            "storyboards": [
                {
                    "shots": [
                        {
                            "id": 1,
                            "start_time": 0,
                            "end_time": 3,
                            "visual": "A mother reaches for the pump beside a laptop and coffee.",
                        }
                    ]
                }
            ],
            "storyboard_grid": "12",
            "transition_style": "match_cut",
        }
    )

    assert result.success is True
    identity = result.data["visual_identity"]
    prompt = result.data["clip_groups"][0]["seedance_prompt"]

    assert identity["audience"] == "working mothers 25-40"
    assert "sage green" in identity["color_palette"]
    assert identity["director_profile"]["audience_tension"] == "resolve working mothers 25-40's morning desk-side pumping routine need"
    assert "Brand tone: warm, empowering, practical." in prompt
    assert "Final continuity should still travel well to tiktok, amazon." in prompt
    assert "Keep the lifestyle cues relevant to working mothers 25-40." in prompt
    assert "Audience tension: resolve working mothers 25-40's morning desk-side pumping routine need." in prompt


@pytest.mark.asyncio
async def test_illegal_grid_returns_error(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()
    bottle_warmer_params["storyboard_grid"] = "8"

    result = await skill.execute(bottle_warmer_params)

    assert result.success is False
    assert "unsupported storyboard_grid" in result.error


@pytest.mark.asyncio
async def test_registry_execute_uses_safe_execute_path(bottle_warmer_params):
    previous_global_skills = dict(SkillRegistry._global_skills)
    try:
        SkillRegistry.clear_global()
        SkillRegistry.register(ContinuityStoryboardGridSkill())

        result = await SkillRegistry().execute(
            "continuity-storyboard-grid",
            bottle_warmer_params,
        )
    finally:
        SkillRegistry._global_skills = previous_global_skills

    assert result.success is True
    assert result.metadata["requested_grid"] == "12"
    assert result.metadata["effective_grid"] == 12
    assert result.metadata["retries"] == 0


def test_validate_output_collects_type_errors_without_raising():
    skill = ContinuityStoryboardGridSkill()

    errors = skill.validate_output(
        {
            "micro_shots": [None] * 12,
            "clip_groups": [
                {"shot_indices": None},
                {"shot_indices": [4, 5, 6]},
                {"shot_indices": [7, 8, 9]},
                {"shot_indices": [10, 11, 12]},
            ],
        }
    )

    assert "micro_shots entries must be dicts" in errors
    assert "clip_groups shot_indices must be lists" in errors
