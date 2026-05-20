from __future__ import annotations

import pytest

from src.skills.continuity_storyboard_grid import ContinuityStoryboardGridSkill


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
async def test_micro_shots_have_continuity_fields(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    for shot in result.data["micro_shots"]:
        assert shot["continuity_in"]
        assert shot["continuity_out"]
        assert shot["transition_out"]
        assert "no close-up infant face" in shot["safety_notes"]


@pytest.mark.asyncio
async def test_clip_groups_cover_all_micro_shots_once(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()

    result = await skill.execute(bottle_warmer_params)

    groups = result.data["clip_groups"]
    assert len(groups) == 4
    covered = [idx for group in groups for idx in group["shot_indices"]]
    assert covered == list(range(1, 13))
    assert (
        groups[0]["transition_to_next"]
        == "match cut from cold bottle movement to bottle placement"
    )
    assert (
        groups[1]["transition_to_next"]
        == "action cut from indicator light to bottle removal"
    )
    assert (
        groups[2]["transition_to_next"]
        == "soft crossfade from temperature check to product beauty shot"
    )
    assert "transition_to_next" not in groups[3]
