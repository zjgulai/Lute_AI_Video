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
    assert visual_identity["location"] == "warm night kitchen and nursery doorway"
    assert visual_identity["lighting"] == "soft warm low-light"
    assert visual_identity["product_anchor"] == (
        "same bottle warmer on the same countertop"
    )
    assert "soft green indicator" in visual_identity["color_palette"]


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


@pytest.mark.asyncio
async def test_illegal_grid_returns_error(bottle_warmer_params):
    skill = ContinuityStoryboardGridSkill()
    bottle_warmer_params["storyboard_grid"] = "8"

    result = await skill.execute(bottle_warmer_params)

    assert result.success is False
    assert "unsupported storyboard_grid" in result.error


@pytest.mark.asyncio
async def test_registry_execute_uses_safe_execute_path(bottle_warmer_params):
    result = await SkillRegistry().execute(
        "continuity-storyboard-grid",
        bottle_warmer_params,
    )

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
