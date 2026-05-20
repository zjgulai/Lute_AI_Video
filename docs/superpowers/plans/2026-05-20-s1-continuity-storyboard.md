# S1 Continuity Storyboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the S1 bottle-warmer continuity flow: 12-grid director storyboard, four grouped Seedance clips, lightweight Remotion transitions, and split asset/publish audit.

**Architecture:** Add a focused Continuity Director skill between `storyboards` and `keyframe_images`. Keep S1 state shape backward-compatible by persisting a new `continuity_storyboard_grid` step while retaining existing `storyboards`, `keyframe_images`, `seedance_clips`, and `assemble_final` outputs. Use Remotion transitions as an editorial support layer, not as the primary continuity fix.

**Tech Stack:** Python 3.12, FastAPI, Pydantic-style dict contracts, SkillRegistry, pytest, TypeScript, React 19, Remotion.

---

## Scope And Boundaries

This plan implements the accepted design in [2026-05-20-s1-continuity-storyboard-design.md](/Users/pray/project/hermes_evo/AI_vedio/docs/superpowers/specs/2026-05-20-s1-continuity-storyboard-design.md).

First implementation scope:

- S1 Product Direct only.
- Default `storyboard_grid=12`.
- Default `continuity_mode=standard`.
- Default `transition_style=match_cut`.
- Four Seedance clip groups from 12 micro-shots.
- Optional high-quality sequential continuity mode behind config.
- Minimal frontend setting: Standard vs High Quality.

Out of scope:

- S2-S5 behavior changes.
- 24-grid default.
- New external video provider.
- Full computer-vision continuity scoring.
- Redesign of the full settings page.

## File Structure

Create:

- `src/skills/continuity_storyboard_grid.py`: builds the 12-grid director storyboard and clip groups.
- `tests/test_continuity_storyboard_grid.py`: unit tests for 12-grid output and invariants.
- `tests/test_s1_continuity_pipeline.py`: integration-level tests for S1 step order, run_step wiring, grouped prompts, and audit split.

Modify:

- `src/pipeline/step_runner.py`: insert `continuity_storyboard_grid` into S1/S2 shared step maps without enabling it for S2 behavior in tests.
- `src/routers/_state.py`: insert the step into S1 status order and duration metadata.
- `src/pipeline/s1_product_pipeline.py`: add run_step support, config defaults, grouped prompt flow, high-quality mode, transition metadata, and split audit fields.
- `src/skills/seedance_prompt.py`: accept `continuity_storyboard_grid.clip_groups` and emit one prompt per clip group.
- `src/skills/remotion_assemble.py`: include transition metadata in render JSON.
- `rendering/src/VideoComposition.tsx`: apply `match_cut`, `action_cut`, and `soft_crossfade` transitions.
- `web/src/components/SceneForm.tsx`: add the minimal continuity setting to S1 config.
- `web/src/i18n/translations.ts`: add bilingual labels for the setting.

Validation commands:

- Backend targeted tests: `.venv/bin/python -m pytest tests/test_continuity_storyboard_grid.py tests/test_s1_continuity_pipeline.py -q`
- Backend lint on touched Python: `.venv/bin/ruff check src/skills/continuity_storyboard_grid.py src/skills/seedance_prompt.py src/pipeline/s1_product_pipeline.py src/pipeline/step_runner.py src/routers/_state.py tests/test_continuity_storyboard_grid.py tests/test_s1_continuity_pipeline.py`
- Frontend targeted tests/lint: `cd web && npm run lint`

---

### Task 1: Add Continuity Storyboard Grid Skill

**Files:**

- Create: `src/skills/continuity_storyboard_grid.py`
- Create: `tests/test_continuity_storyboard_grid.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_continuity_storyboard_grid.py`:

```python
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
    assert groups[0]["transition_to_next"] == "match cut from cold bottle movement to bottle placement"
    assert groups[1]["transition_to_next"] == "action cut from indicator light to bottle removal"
    assert groups[2]["transition_to_next"] == "soft crossfade from temperature check to product beauty shot"
    assert "transition_to_next" not in groups[3]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_continuity_storyboard_grid.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'src.skills.continuity_storyboard_grid'
```

- [ ] **Step 3: Implement the skill**

Create `src/skills/continuity_storyboard_grid.py`:

```python
"""Continuity storyboard grid skill for S1 Product Direct."""

from __future__ import annotations

from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry


class ContinuityStoryboardGridSkill(SkillCallable):
    """Build a 12-grid director storyboard and four clip groups."""

    name = "continuity-storyboard-grid"
    description = "Builds continuity micro-shots and grouped clip prompts for S1"
    max_retries = 1

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        product_catalog = params.get("product_catalog") or {}
        product_name = (
            product_catalog.get("product_name")
            or product_catalog.get("name")
            or product_catalog.get("products", [{}])[0].get("name")
            or "Product"
        )
        transition_style = params.get("transition_style") or "match_cut"
        grid_type = str(params.get("storyboard_grid") or "12")
        if grid_type not in {"auto", "9", "12", "24"}:
            return SkillResult(success=False, error=f"unsupported storyboard_grid: {grid_type}")
        if grid_type in {"auto", "9", "24"}:
            grid_type = "12"

        micro_shots = _build_bottle_warmer_micro_shots()
        clip_groups = _build_clip_groups(product_name=product_name, transition_style=transition_style)

        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": product_name,
                "visual_identity": {
                    "location": "warm night kitchen and nursery doorway",
                    "lighting": "soft warm low-light",
                    "product_anchor": "same bottle warmer on the same countertop",
                    "color_palette": ["warm white", "soft green indicator", "matte neutral counter"],
                },
                "micro_shots": micro_shots,
                "clip_groups": clip_groups,
            },
            metadata={"grid_size": 12, "clip_group_count": 4},
        )

    def validate_output(self, data: Any) -> list[str]:
        errors: list[str] = []
        if not isinstance(data, dict):
            return ["output must be a dict"]
        micro_shots = data.get("micro_shots")
        clip_groups = data.get("clip_groups")
        if not isinstance(micro_shots, list) or len(micro_shots) != 12:
            errors.append("micro_shots must contain 12 entries")
        if not isinstance(clip_groups, list) or len(clip_groups) != 4:
            errors.append("clip_groups must contain 4 entries")
        if isinstance(micro_shots, list):
            for shot in micro_shots:
                if not shot.get("continuity_in") or not shot.get("continuity_out"):
                    errors.append(f"micro_shot_{shot.get('index', '?')}_missing_continuity")
        return errors


def _build_bottle_warmer_micro_shots() -> list[dict[str, Any]]:
    raw = [
        ("pain_setup", 1.5, "2:00 AM clock in a dim kitchen", "clock ticks as the parent enters frame", "close-up, slow push-in", "dark quiet kitchen", "parent reaches toward a cold bottle", "match cut on hand movement"),
        ("pain_setup", 1.5, "cold bottle on the counter", "parent picks up the cold bottle and checks it", "close-up handheld", "hand reaches from clock shot", "bottle moves toward the warmer", "match cut on bottle movement"),
        ("pain_setup", 1.0, "parent approaches the warmer on the same countertop", "parent sets the bottle beside the warmer", "medium close-up", "same countertop and bottle", "bottle is ready to be placed into warmer", "match cut to placement"),
        ("product_action", 2.0, "bottle placed into the warmer", "parent opens the warmer and places the bottle inside", "over-shoulder", "same bottle enters frame", "hand moves toward control button", "action cut on hand"),
        ("product_action", 2.0, "finger presses the warmer button", "parent presses one button on the warmer", "insert close-up", "hand from placement shot", "indicator light turns on", "action cut to indicator"),
        ("product_action", 2.0, "soft green indicator light on warmer", "indicator glows while the warmer runs", "static close-up", "same control panel", "parent waits calmly nearby", "soft cut to waiting moment"),
        ("result_proof", 2.0, "short waiting moment in warm kitchen light", "parent leans on counter and relaxes", "medium shot", "same kitchen and warmer visible", "parent reaches back to warmer", "match cut on reach"),
        ("result_proof", 2.0, "bottle removed from the warmer", "parent removes the warmed bottle", "over-shoulder", "same warmer and bottle", "parent checks bottle temperature", "action cut to temperature check"),
        ("result_proof", 2.0, "temperature check on wrist", "parent tests the bottle temperature on wrist", "close-up", "same bottle in hand", "parent turns toward nursery doorway", "soft crossfade to doorway"),
        ("emotional_close", 1.5, "calm nursery doorway with warm light", "parent pauses at doorway holding bottle", "medium shot", "same bottle visible", "scene transitions to product beauty shot", "soft crossfade"),
        ("cta", 1.5, "product beauty shot on clean countertop", "warmer sits centered with soft glow", "static beauty shot", "same warmer and counter", "phone enters frame for CTA", "match cut to phone"),
        ("cta", 1.5, "phone shop action beside warmer", "hand taps Shop Now on phone screen", "close-up", "same product remains in background", "end card", "fade out"),
    ]
    return [
        {
            "index": i + 1,
            "beat": beat,
            "duration": duration,
            "visual": visual,
            "action": action,
            "camera": camera,
            "continuity_in": continuity_in,
            "continuity_out": continuity_out,
            "transition_out": transition_out,
            "safety_notes": ["no close-up infant face", "no medical claim", "no distress-heavy imagery"],
        }
        for i, (beat, duration, visual, action, camera, continuity_in, continuity_out, transition_out)
        in enumerate(raw)
    ]


def _build_clip_groups(product_name: str, transition_style: str) -> list[dict[str, Any]]:
    return [
        {
            "clip_index": 1,
            "shot_indices": [1, 2, 3],
            "duration": 4,
            "purpose": "pain setup",
            "seedance_prompt": (
                f"{product_name} night-feed setup: a continuous 2 AM kitchen sequence, "
                "clock close-up, parent picks up a cold bottle, parent moves toward the warmer. "
                "Keep the same warm low-light kitchen, same bottle, and same countertop."
            ),
            "transition_to_next": "match cut from cold bottle movement to bottle placement",
            "transition_type": "match_cut" if transition_style == "match_cut" else transition_style,
        },
        {
            "clip_index": 2,
            "shot_indices": [4, 5, 6],
            "duration": 6,
            "purpose": "product action",
            "seedance_prompt": (
                f"{product_name} product action: parent opens the warmer, places the bottle inside, "
                "presses one button, and the soft green indicator light turns on. "
                "Use the same warmer, same bottle, same countertop, and a smooth close-up sequence."
            ),
            "transition_to_next": "action cut from indicator light to bottle removal",
            "transition_type": "action_cut",
        },
        {
            "clip_index": 3,
            "shot_indices": [7, 8, 9],
            "duration": 6,
            "purpose": "result proof",
            "seedance_prompt": (
                f"{product_name} result proof: parent waits calmly, removes the warmed bottle, "
                "and checks the bottle temperature on wrist. Keep the product visible and avoid infant close-ups."
            ),
            "transition_to_next": "soft crossfade from temperature check to product beauty shot",
            "transition_type": "soft_crossfade",
        },
        {
            "clip_index": 4,
            "shot_indices": [10, 11, 12],
            "duration": 5,
            "purpose": "emotional close and CTA",
            "seedance_prompt": (
                f"{product_name} closing CTA: parent pauses near a warm nursery doorway, "
                "cut to the warmer beauty shot on the countertop, then a phone taps Shop Now. "
                "Keep the scene calm and product-centered."
            ),
            "transition_type": "soft_crossfade",
        },
    ]


SkillRegistry.register(ContinuityStoryboardGridSkill())
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_continuity_storyboard_grid.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Run lint for the new files**

Run:

```bash
.venv/bin/ruff check src/skills/continuity_storyboard_grid.py tests/test_continuity_storyboard_grid.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 6: Commit**

Run:

```bash
git add src/skills/continuity_storyboard_grid.py tests/test_continuity_storyboard_grid.py
git commit -m "新增 S1 连续分镜 skill"
```

---

### Task 2: Wire Continuity Step Into S1 State Flow

**Files:**

- Modify: `src/pipeline/step_runner.py`
- Modify: `src/routers/_state.py`
- Modify: `src/pipeline/s1_product_pipeline.py`
- Create: `tests/test_s1_continuity_pipeline.py`

- [ ] **Step 1: Write failing tests for step order and defaults**

Create `tests/test_s1_continuity_pipeline.py`:

```python
from __future__ import annotations

import pytest


def test_s1_step_order_includes_continuity_before_keyframes():
    from src.pipeline.step_runner import STEP_ORDER
    from src.routers._state import _SCENARIO_STEP_ORDER

    assert "continuity_storyboard_grid" in STEP_ORDER
    assert STEP_ORDER.index("storyboards") < STEP_ORDER.index("continuity_storyboard_grid")
    assert STEP_ORDER.index("continuity_storyboard_grid") < STEP_ORDER.index("keyframe_images")

    s1_order = _SCENARIO_STEP_ORDER["s1"]
    assert "continuity_storyboard_grid" in s1_order
    assert s1_order.index("storyboards") < s1_order.index("continuity_storyboard_grid")
    assert s1_order.index("continuity_storyboard_grid") < s1_order.index("keyframe_images")


def test_s1_config_defaults_for_continuity():
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    config = S1ProductDirectPipeline._normalize_continuity_config({})

    assert config["storyboard_grid"] == "12"
    assert config["continuity_mode"] == "standard"
    assert config["transition_style"] == "match_cut"


@pytest.mark.asyncio
async def test_run_step_continuity_storyboard_grid_calls_skill(monkeypatch):
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    captured: dict[str, object] = {}

    async def fake_execute(self, skill_name: str, params: dict):
        captured["skill_name"] = skill_name
        captured["params"] = params
        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": "Momcozy Nutri Bottle Warmer",
                "visual_identity": {},
                "micro_shots": [{"index": i, "continuity_in": "in", "continuity_out": "out"} for i in range(1, 13)],
                "clip_groups": [
                    {"clip_index": 1, "shot_indices": [1, 2, 3], "duration": 4, "seedance_prompt": "a"},
                    {"clip_index": 2, "shot_indices": [4, 5, 6], "duration": 6, "seedance_prompt": "b"},
                    {"clip_index": 3, "shot_indices": [7, 8, 9], "duration": 6, "seedance_prompt": "c"},
                    {"clip_index": 4, "shot_indices": [10, 11, 12], "duration": 5, "seedance_prompt": "d"},
                ],
            },
        )

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    pipeline = S1ProductDirectPipeline()
    state = {
        "config": {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "storyboard_grid": "12",
            "continuity_mode": "standard",
            "transition_style": "match_cut",
        },
        "errors": [],
        "media_synthesis_errors": [],
        "steps": {
            "storyboards": {"output": [{"script_id": "s", "shots": []}], "edited": False, "edited_output": None},
        },
    }

    result = await pipeline.run_step("continuity_storyboard_grid", state)

    assert captured["skill_name"] == "continuity-storyboard-grid"
    assert result["grid_type"] == "12-grid"
    assert captured["params"]["product_catalog"]["product_name"] == "Momcozy Nutri Bottle Warmer"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py -q
```

Expected:

```text
AssertionError: assert 'continuity_storyboard_grid' in [...]
```

- [ ] **Step 3: Update step order maps**

In `src/pipeline/step_runner.py`, replace `STEP_ORDER` and add the method map entry:

```python
STEP_ORDER = [
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
]

STEP_METHOD_MAP = {
    "strategy": "_step_strategy",
    "scripts": "_step_scripts",
    "compliance": "_step_compliance",
    "storyboards": "_step_storyboards",
    "continuity_storyboard_grid": "_step_continuity_storyboard_grid",
    "keyframe_images": "_step_keyframe_images",
    "video_prompts": "_step_video_prompts",
    "thumbnail_prompts": "_step_thumbnail_prompts",
    "seedance_clips": "_step_seedance_clips",
    "tts_audio": "_step_tts_audio",
    "thumbnail_images": "_step_thumbnail_images",
    "assemble_final": "_step_assemble_final",
    "audit": "_step_audit",
}
```

In `src/routers/_state.py`, update S1 and S2 order lists to include the new step. Keep S2 included because S2 uses the S1 class and order; S2 behavior can keep default standard mode.

```python
"s1": [
    "strategy", "scripts", "compliance", "storyboards",
    "continuity_storyboard_grid", "keyframe_images", "video_prompts",
    "thumbnail_prompts", "seedance_clips", "tts_audio",
    "thumbnail_images", "assemble_final", "audit",
],
"s2": [
    "strategy", "scripts", "compliance", "storyboards",
    "continuity_storyboard_grid", "keyframe_images", "video_prompts",
    "thumbnail_prompts", "seedance_clips", "tts_audio",
    "thumbnail_images", "assemble_final", "audit",
],
```

Add a duration hint in `_STEP_DURATIONS`:

```python
"continuity_storyboard_grid": "~1s",
```

- [ ] **Step 4: Add S1 config defaults and run_step dispatch**

In `src/pipeline/s1_product_pipeline.py`, import the skill near the other skill imports:

```python
import src.skills.continuity_storyboard_grid  # noqa: F401
```

Add this static method inside `S1ProductDirectPipeline`:

```python
@staticmethod
def _normalize_continuity_config(config: dict[str, Any]) -> dict[str, str]:
    storyboard_grid = str(config.get("storyboard_grid") or "12")
    if storyboard_grid not in {"auto", "9", "12", "24"}:
        storyboard_grid = "12"
    if storyboard_grid == "auto":
        storyboard_grid = "12"

    continuity_mode = str(config.get("continuity_mode") or "standard")
    if continuity_mode not in {"standard", "high_quality"}:
        continuity_mode = "standard"

    transition_style = str(config.get("transition_style") or "match_cut")
    if transition_style not in {"clean", "soft_crossfade", "match_cut"}:
        transition_style = "match_cut"

    return {
        "storyboard_grid": storyboard_grid,
        "continuity_mode": continuity_mode,
        "transition_style": transition_style,
    }
```

In `run_step`, add this branch after `storyboards` and before `keyframe_images`:

```python
if step_name == "continuity_storyboard_grid":
    storyboards = self._get_step_output(steps, "storyboards") or []
    continuity_config = self._normalize_continuity_config(config)
    return await self._step_continuity_storyboard_grid(
        reg=reg,
        product_catalog=config.get("product_catalog", {}),
        storyboards=storyboards,
        errors=errors,
        **continuity_config,
    )
```

Add the step method:

```python
async def _step_continuity_storyboard_grid(
    self,
    reg: SkillRegistry,
    product_catalog: dict[str, Any],
    storyboards: list[dict[str, Any]],
    errors: list[str],
    storyboard_grid: str,
    continuity_mode: str,
    transition_style: str,
) -> dict[str, Any]:
    res = await reg.execute("continuity-storyboard-grid", {
        "product_catalog": product_catalog,
        "storyboards": storyboards,
        "storyboard_grid": storyboard_grid,
        "continuity_mode": continuity_mode,
        "transition_style": transition_style,
    })
    if res.success and res.data:
        return res.data
    errors.append(f"continuity_storyboard_grid_failed: {res.error}")
    return {
        "grid_type": "12-grid",
        "product_name": product_catalog.get("product_name") or product_catalog.get("name") or "Product",
        "visual_identity": {},
        "micro_shots": [],
        "clip_groups": [],
        "degraded": True,
    }
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Run lint**

Run:

```bash
.venv/bin/ruff check src/pipeline/step_runner.py src/routers/_state.py src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Commit**

Run:

```bash
git add src/pipeline/step_runner.py src/routers/_state.py src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
git commit -m "接入 S1 连续分镜步骤"
```

---

### Task 3: Generate Seedance Prompts From Clip Groups

**Files:**

- Modify: `src/skills/seedance_prompt.py`
- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `tests/test_s1_continuity_pipeline.py`

- [ ] **Step 1: Add failing tests for clip group prompt generation**

Append to `tests/test_s1_continuity_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_seedance_prompt_uses_continuity_clip_groups():
    from src.skills.seedance_prompt import SeedancePromptSkill

    skill = SeedancePromptSkill()
    continuity_grid = {
        "product_name": "Momcozy Nutri Bottle Warmer",
        "visual_identity": {
            "location": "warm night kitchen and nursery doorway",
            "lighting": "soft warm low-light",
            "product_anchor": "same bottle warmer on the same countertop",
        },
        "clip_groups": [
            {
                "clip_index": 1,
                "shot_indices": [1, 2, 3],
                "duration": 4,
                "purpose": "pain setup",
                "seedance_prompt": "Clock, cold bottle, parent approaches warmer.",
                "transition_to_next": "match cut from cold bottle movement to bottle placement",
                "transition_type": "match_cut",
            },
            {
                "clip_index": 2,
                "shot_indices": [4, 5, 6],
                "duration": 6,
                "purpose": "product action",
                "seedance_prompt": "Bottle placed into warmer, button press, indicator light.",
                "transition_type": "action_cut",
            },
        ],
    }

    result = await skill.execute({
        "continuity_storyboard_grid": continuity_grid,
        "product_name": "Momcozy Nutri Bottle Warmer",
    })

    assert result.success is True
    prompts = result.data
    assert len(prompts) == 2
    assert prompts[0]["segment_type"] == "clip_group"
    assert prompts[0]["clip_index"] == 1
    assert prompts[0]["duration_seconds"] == 4
    assert prompts[0]["transition_to_next"] == "match cut from cold bottle movement to bottle placement"
    assert "same bottle warmer on the same countertop" in prompts[0]["segment_prompt"]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_seedance_prompt_uses_continuity_clip_groups -q
```

Expected:

```text
AssertionError: assert 1 == 2
```

- [ ] **Step 3: Update `SeedancePromptSkill.execute`**

At the start of `SeedancePromptSkill.execute`, before reading `script_segments`, add:

```python
continuity_grid = params.get("continuity_storyboard_grid") or {}
if isinstance(continuity_grid, dict) and continuity_grid.get("clip_groups"):
    return SkillResult(
        success=True,
        data=self._build_prompts_from_clip_groups(
            continuity_grid=continuity_grid,
            product_name=params.get("product_name", "Product"),
        ),
        metadata={
            "prompt_count": len(continuity_grid.get("clip_groups", [])),
            "source": "continuity_storyboard_grid",
        },
    )
```

Add this method to `SeedancePromptSkill`:

```python
def _build_prompts_from_clip_groups(
    self,
    continuity_grid: dict[str, Any],
    product_name: str,
) -> list[dict[str, Any]]:
    visual_identity = continuity_grid.get("visual_identity") or {}
    product_anchor = visual_identity.get("product_anchor", f"same {product_name} product")
    location = visual_identity.get("location", "same home setting")
    lighting = visual_identity.get("lighting", "consistent warm natural light")

    prompts: list[dict[str, Any]] = []
    for group in continuity_grid.get("clip_groups", []):
        duration = float(group.get("duration", 5))
        base_prompt = group.get("seedance_prompt", "")
        prompt_text = (
            f"{base_prompt} Maintain continuity: {product_anchor}; "
            f"same location: {location}; lighting: {lighting}. "
            "Use a continuous action chain inside this clip. "
            "Avoid infant face close-ups, medical claims, and distress-heavy imagery."
        )
        transition = group.get("transition_to_next", "")
        prompt = {
            "segment_prompt": prompt_text,
            "segment_type": "clip_group",
            "clip_index": int(group.get("clip_index", len(prompts) + 1)),
            "duration_seconds": duration,
            "shot_type": "continuity_group",
            "camera": "smooth continuity handheld",
            "lighting": lighting,
            "has_forbidden_words": False,
            "forbidden_hits": [],
            "product_angle": group.get("purpose", ""),
            "transition_to_next": transition,
            "transition_type": group.get("transition_type", "match_cut"),
            "quality_score": 1.0,
        }
        prompts.append(prompt)
    return prompts
```

- [ ] **Step 4: Pass continuity grid from S1 pipeline into video prompts**

In `S1ProductDirectPipeline.run_step`, update the `video_prompts` branch so it reads the new step output:

```python
if step_name == "video_prompts":
    scripts = self._get_step_output(steps, "scripts") or []
    continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
    return await self._step_video_prompts(
        reg=reg,
        scripts=scripts,
        product_name=product_name,
        errors=errors,
        continuity_storyboard_grid=continuity_grid,
    )
```

Update `_step_video_prompts` signature:

```python
async def _step_video_prompts(
    self,
    reg: SkillRegistry,
    scripts: list[dict[str, Any]],
    product_name: str,
    errors: list[str],
    continuity_storyboard_grid: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
```

Inside `_step_video_prompts`, before segment-based execution, add:

```python
if continuity_storyboard_grid and continuity_storyboard_grid.get("clip_groups"):
    res = await reg.execute("seedance-video-prompt", {
        "continuity_storyboard_grid": continuity_storyboard_grid,
        "product_name": product_name,
    })
    if res.success and res.data:
        return res.data
    errors.append(f"video_prompts_continuity_failed: {res.error}")
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_seedance_prompt_uses_continuity_clip_groups -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run lint**

Run:

```bash
.venv/bin/ruff check src/skills/seedance_prompt.py src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Commit**

Run:

```bash
git add src/skills/seedance_prompt.py src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
git commit -m "让 Seedance prompt 使用连续 clip group"
```

---

### Task 4: Generate Grouped Clips And High-Quality Continuity Mode

**Files:**

- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `tests/test_s1_continuity_pipeline.py`

- [ ] **Step 1: Add failing tests for grouped generation parameters**

Append to `tests/test_s1_continuity_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_seedance_grouped_prompts_keep_transition_metadata(monkeypatch):
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    calls: list[dict] = []

    async def fake_execute(self, skill_name: str, params: dict):
        calls.append({"skill_name": skill_name, "params": params})
        return SkillResult(
            success=True,
            data={
                "video_path": f"/tmp/{params['output_label']}.mp4",
                "duration_seconds": params["duration"],
                "file_size_bytes": 2048,
                "is_stub": False,
                "verification": {"all_ok": True},
                "prompt_used": params["prompt"],
            },
        )

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    pipeline = S1ProductDirectPipeline()
    result = await pipeline._step_seedance_clips(
        reg=SkillRegistry(),
        video_prompts=[
            {
                "segment_prompt": "clip one",
                "duration_seconds": 4,
                "clip_index": 1,
                "transition_to_next": "match cut",
                "transition_type": "match_cut",
            },
            {
                "segment_prompt": "clip two",
                "duration_seconds": 6,
                "clip_index": 2,
                "transition_type": "action_cut",
            },
        ],
        product_name="Momcozy Nutri Bottle Warmer",
        label="test_label",
        errors=[],
        video_duration=15,
        keyframe_images=[],
        continuity_mode="standard",
    )

    assert len(result["clip_paths"]) == 2
    assert result["clip_details"][0]["clip_index"] == 1
    assert result["clip_details"][0]["transition_to_next"] == "match cut"
    assert result["clip_details"][0]["transition_type"] == "match_cut"
    assert calls[0]["params"]["duration"] == 4
    assert calls[1]["params"]["duration"] == 6
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_seedance_grouped_prompts_keep_transition_metadata -q
```

Expected:

```text
TypeError: S1ProductDirectPipeline._step_seedance_clips() got an unexpected keyword argument 'continuity_mode'
```

- [ ] **Step 3: Add continuity mode parameter**

Update `_step_seedance_clips` signature:

```python
async def _step_seedance_clips(
    self,
    reg: SkillRegistry,
    video_prompts: list[dict[str, Any]],
    product_name: str,
    label: str,
    errors: list[str],
    video_duration: int = 30,
    keyframe_images: list[dict[str, Any]] | None = None,
    continuity_mode: str = "standard",
) -> dict[str, Any]:
```

In the `seedance_clips` run_step branch, pass the normalized mode:

```python
continuity_config = self._normalize_continuity_config(config)
return await self._step_seedance_clips(
    reg=reg,
    video_prompts=video_prompts,
    product_name=product_name,
    label=state.get("label", ""),
    errors=errors,
    video_duration=config.get("video_duration", 30),
    keyframe_images=keyframes,
    continuity_mode=continuity_config["continuity_mode"],
)
```

- [ ] **Step 4: Preserve clip group metadata in `clip_details`**

Inside the result processing loop in `_step_seedance_clips`, replace the `clip_details.append({...})` block with:

```python
clip_details.append({
    "path": p,
    "duration": dur,
    "is_stub": skill_result.data.get("is_stub", False),
    "file_size": skill_result.data.get("file_size_bytes", 0),
    "verification": skill_result.data.get("verification", {}),
    "prompt_used": skill_result.data.get("prompt_used", ""),
    "segment_type": video_prompts[i].get("segment_type", "body"),
    "shot_type": video_prompts[i].get("shot_type", ""),
    "clip_index": video_prompts[i].get("clip_index", i + 1),
    "transition_to_next": video_prompts[i].get("transition_to_next", ""),
    "transition_type": video_prompts[i].get("transition_type", "clean"),
    "continuity_frame": False,
})
```

- [ ] **Step 5: Add sequential high-quality generation path**

Before launching concurrent tasks, add:

```python
if continuity_mode == "high_quality":
    raw_results = []
    last_frame_path = None
    for i, vp in enumerate(video_prompts):
        kf_path = kf_image_paths[i] if i < len(kf_image_paths) and kf_image_paths[i] else None
        if last_frame_path:
            vp = {**vp, "_continuity_frame_path": last_frame_path}
        result = await _gen_single_clip(i, vp, kf_path)
        raw_results.append(result)
        if isinstance(result, tuple) and result[1].success and result[1].data:
            generated_path = result[1].data.get("video_path", "")
            last_frame_path = self._extract_clip_last_frame(
                video_path=generated_path,
                output_dir=str(OUTPUT_DIR / "seedance" / "continuity_frames"),
            )
else:
    clip_tasks = []
    for i, vp in enumerate(video_prompts):
        kf_path = kf_image_paths[i] if i < len(kf_image_paths) and kf_image_paths[i] else None
        clip_tasks.append(_gen_single_clip(i, vp, kf_path))
    raw_results = await asyncio.gather(*clip_tasks, return_exceptions=True)
```

Inside `_gen_single_clip`, after setting keyframe path, support the continuity frame:

```python
continuity_frame = vp.get("_continuity_frame_path")
if continuity_frame:
    gen_params["continuity_frame_path"] = continuity_frame
```

Remove the old unconditional `raw_results = await asyncio.gather(...)` block so only one path runs.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_seedance_grouped_prompts_keep_transition_metadata -q
```

Expected:

```text
1 passed
```

- [ ] **Step 7: Run lint**

Run:

```bash
.venv/bin/ruff check src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 8: Commit**

Run:

```bash
git add src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
git commit -m "支持 S1 分组 clip 与高质量连续模式"
```

---

### Task 5: Pass Transition Metadata Into Remotion And Render It

**Files:**

- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `src/skills/remotion_assemble.py`
- Modify: `rendering/src/VideoComposition.tsx`
- Modify: `tests/test_s1_continuity_pipeline.py`

- [ ] **Step 1: Add failing test for render payload transitions**

Append to `tests/test_s1_continuity_pipeline.py`:

```python
def test_remotion_payload_contains_transitions():
    from src.skills.remotion_assemble import RemotionAssembleSkill

    skill = RemotionAssembleSkill()
    payload = skill._build_render_payload(
        shots=[
            {"id": 1, "start_time": 0, "end_time": 4, "visual": "a"},
            {"id": 2, "start_time": 4, "end_time": 10, "visual": "b"},
        ],
        captions=[],
        audio_paths=[],
        lyrics_text="",
        brand_guidelines={},
        total_duration=10,
        label="test",
        clip_paths=["/tmp/a.mp4", "/tmp/b.mp4"],
        transitions=[
            {"from_clip": 1, "to_clip": 2, "type": "match_cut", "duration_frames": 8}
        ],
    )

    assert payload["transitions"] == [
        {"from_clip": 1, "to_clip": 2, "type": "match_cut", "duration_frames": 8}
    ]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_remotion_payload_contains_transitions -q
```

Expected:

```text
TypeError: RemotionAssembleSkill._build_render_payload() got an unexpected keyword argument 'transitions'
```

- [ ] **Step 3: Add transition extraction in S1 assemble step**

In `_step_assemble_final`, add a new parameter:

```python
clip_details: list[dict[str, Any]] | None = None,
```

Before calling `remotion-assemble-skill`, build transitions:

```python
transitions = []
for idx, detail in enumerate(clip_details or []):
    transition_to_next = detail.get("transition_to_next", "")
    if idx < len(clip_paths) - 1 and transition_to_next:
        transitions.append({
            "from_clip": idx + 1,
            "to_clip": idx + 2,
            "type": detail.get("transition_type", "clean"),
            "duration_frames": 8 if detail.get("transition_type") != "soft_crossfade" else 12,
            "description": transition_to_next,
        })
```

Include it in the SkillRegistry call:

```python
"transitions": transitions,
```

In the `assemble_final` run_step branch, pass `clip_details` from `seedance_out`:

```python
clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
```

Then:

```python
clip_details=clip_details,
```

- [ ] **Step 4: Update `RemotionAssembleSkill` render payload**

Update `_build_render_payload` signature:

```python
def _build_render_payload(
    self,
    shots: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    audio_paths: list[str],
    lyrics_text: str,
    brand_guidelines: dict[str, Any],
    total_duration: float,
    label: str,
    clip_paths: list[str] | None = None,
    transitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
```

Add to returned payload:

```python
"transitions": transitions or [],
```

Update the call site inside `execute`:

```python
transitions = params.get("transitions") or []
render_payload = self._build_render_payload(
    shots=shots,
    captions=captions,
    audio_paths=audio_paths,
    lyrics_text=lyrics_text,
    brand_guidelines=brand_guidelines,
    total_duration=total_duration,
    label=output_label,
    clip_paths=clip_paths,
    transitions=transitions,
)
```

- [ ] **Step 5: Add Remotion transition rendering**

In `rendering/src/VideoComposition.tsx`, extend interfaces:

```tsx
interface Transition {
  from_clip: number;
  to_clip: number;
  type: "clean" | "match_cut" | "action_cut" | "soft_crossfade";
  duration_frames: number;
  description?: string;
}
```

Add `transitions?: Transition[];` to `VideoCompositionProps["data"]`.

Inside `ShotSegment`, compute transition opacity:

```tsx
const transition = (shot as Shot & { transition?: Transition }).transition;
const fadeFrames = transition?.type === "soft_crossfade" ? transition.duration_frames : 0;
const fadeOut = fadeFrames > 0
  ? interpolate(localFrame, [shotDurationFrames - fadeFrames, shotDurationFrames], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  : 1;
```

Apply opacity on the root `AbsoluteFill`:

```tsx
opacity: fadeOut,
```

In the `data.shots.map` section, attach transition by index:

```tsx
const transition = data.transitions?.find((t) => t.from_clip === index + 1);
const shotWithTransition = { ...shot, transition };
```

Then pass `shotWithTransition` into `ShotSegment`.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_remotion_payload_contains_transitions -q
```

Expected:

```text
1 passed
```

- [ ] **Step 7: Run frontend lint**

Run:

```bash
cd web && npm run lint
```

Expected:

```text
No ESLint warnings or errors for rendering changes
```

- [ ] **Step 8: Commit**

Run:

```bash
git add src/pipeline/s1_product_pipeline.py src/skills/remotion_assemble.py rendering/src/VideoComposition.tsx tests/test_s1_continuity_pipeline.py
git commit -m "为 S1 合成加入转场元数据"
```

---

### Task 6: Split Asset-Ready And Publish-Ready Audit

**Files:**

- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `tests/test_s1_continuity_pipeline.py`

- [ ] **Step 1: Add failing test for audit split**

Append to `tests/test_s1_continuity_pipeline.py`:

```python
def test_continuity_audit_split_marks_asset_ready_when_publish_warns():
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    pipeline = S1ProductDirectPipeline()
    report = pipeline._build_continuity_audit_summary(
        base_audit={
            "overall_status": "FAIL",
            "overall_score": 0.741,
            "criteria": [
                {"name": "final_video_present", "status": "WARN"},
                {"name": "thumbnail_count", "status": "WARN"},
                {"name": "product_mention", "status": "FAIL"},
            ],
        },
        clip_details=[
            {"is_stub": False, "transition_to_next": "match cut", "verification": {"all_ok": True}},
            {"is_stub": False, "transition_to_next": "action cut", "verification": {"all_ok": True}},
            {"is_stub": False, "transition_to_next": "soft crossfade", "verification": {"all_ok": True}},
            {"is_stub": False, "verification": {"all_ok": True}},
        ],
        continuity_grid={
            "micro_shots": [{"continuity_in": "in", "continuity_out": "out"} for _ in range(12)],
            "clip_groups": [
                {"transition_to_next": "match cut"},
                {"transition_to_next": "action cut"},
                {"transition_to_next": "soft crossfade"},
                {},
            ],
        },
        final_video_path="/tmp/final.mp4",
    )

    assert report["asset_ready_audit"]["status"] == "PASS"
    assert report["publish_ready_audit"]["status"] == "FAIL"
    assert report["continuity_score"] >= 0.8
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_continuity_audit_split_marks_asset_ready_when_publish_warns -q
```

Expected:

```text
AttributeError: 'S1ProductDirectPipeline' object has no attribute '_build_continuity_audit_summary'
```

- [ ] **Step 3: Implement audit summary helper**

Add to `S1ProductDirectPipeline`:

```python
@staticmethod
def _build_continuity_audit_summary(
    base_audit: dict[str, Any],
    clip_details: list[dict[str, Any]],
    continuity_grid: dict[str, Any],
    final_video_path: str,
) -> dict[str, Any]:
    real_clips = [d for d in clip_details if not d.get("is_stub")]
    non_stub_ok = bool(real_clips) and len(real_clips) == len(clip_details)
    transitions = [d.get("transition_to_next") for d in clip_details[:-1]]
    transition_ok = all(bool(t) for t in transitions) if len(clip_details) > 1 else True
    micro_shots = continuity_grid.get("micro_shots") or []
    micro_continuity_ok = bool(micro_shots) and all(
        s.get("continuity_in") and s.get("continuity_out") for s in micro_shots
    )
    final_video_ok = bool(final_video_path)

    score_parts = [
        1.0 if non_stub_ok else 0.0,
        1.0 if transition_ok else 0.0,
        1.0 if micro_continuity_ok else 0.0,
        1.0 if final_video_ok else 0.0,
    ]
    continuity_score = round(sum(score_parts) / len(score_parts), 3)
    asset_status = "PASS" if continuity_score >= 0.8 and final_video_ok and non_stub_ok else "FAIL"
    publish_status = base_audit.get("overall_status", "WARN")

    return {
        **base_audit,
        "asset_ready_audit": {
            "status": asset_status,
            "checks": {
                "non_stub_clips": non_stub_ok,
                "transition_metadata": transition_ok,
                "micro_shot_continuity": micro_continuity_ok,
                "final_video_present": final_video_ok,
            },
        },
        "publish_ready_audit": {
            "status": publish_status,
            "base_score": base_audit.get("overall_score", 0),
            "criteria": base_audit.get("criteria", []),
        },
        "continuity_score": continuity_score,
    }
```

- [ ] **Step 4: Use helper in audit step**

In the `audit` run_step branch, gather:

```python
continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
seedance_out = self._get_step_output(steps, "seedance_clips") or {}
clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
```

After `_step_audit` returns `base_audit`, wrap it:

```python
return self._build_continuity_audit_summary(
    base_audit=base_audit,
    clip_details=clip_details,
    continuity_grid=continuity_grid,
    final_video_path=final_video,
)
```

If the current branch returns directly from `_step_audit`, assign to `base_audit` first.

- [ ] **Step 5: Run targeted test**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_continuity_pipeline.py::test_continuity_audit_split_marks_asset_ready_when_publish_warns -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Run lint**

Run:

```bash
.venv/bin/ruff check src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Commit**

Run:

```bash
git add src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py
git commit -m "拆分 S1 素材级与投放级审核"
```

---

### Task 7: Add Minimal Frontend Continuity Setting

**Files:**

- Modify: `web/src/components/SceneForm.tsx`
- Modify: `web/src/i18n/translations.ts`

- [ ] **Step 1: Add config fields in S1 submit config**

In `web/src/components/SceneForm.tsx`, locate the S1 `product_direct` config block and add:

```tsx
config.storyboard_grid = "12";
config.transition_style = "match_cut";
config.continuity_mode = values.continuity_mode === "high_quality" ? "high_quality" : "standard";
```

Place these fields in the same `if (scene === "product_direct")` block that sets `config.product_catalog` and `config.brand_guidelines`.

- [ ] **Step 2: Add continuity field card**

In the S1 product form card list, add a select/radio-style field with key `continuity_mode`. Use existing `GuidedCard` patterns already used in `SceneForm.tsx`.

Use these option values:

```tsx
[
  { value: "standard", label: t("continuity.standard"), description: t("continuity.standardDesc") },
  { value: "high_quality", label: t("continuity.highQuality"), description: t("continuity.highQualityDesc") },
]
```

Default value:

```tsx
const [continuityMode, setContinuityMode] = useState("standard");
```

When the existing form is value-map based, store it as:

```tsx
values.continuity_mode || "standard"
```

- [ ] **Step 3: Add translations**

In `web/src/i18n/translations.ts`, add Chinese labels in the zh-CN map:

```ts
"continuity.label": "视频连贯性",
"continuity.standard": "标准",
"continuity.standardDesc": "12格导演分镜，平衡速度和质量",
"continuity.highQuality": "高质量",
"continuity.highQualityDesc": "12格分镜加上一段末帧连续，耗时更长",
```

Add English labels in the en map:

```ts
"continuity.label": "Video continuity",
"continuity.standard": "Standard",
"continuity.standardDesc": "12-grid director storyboard, balanced speed and quality",
"continuity.highQuality": "High quality",
"continuity.highQualityDesc": "12-grid storyboard plus previous-clip end-frame continuity, slower",
```

- [ ] **Step 4: Run frontend lint**

Run:

```bash
cd web && npm run lint
```

Expected:

```text
No ESLint errors
```

- [ ] **Step 5: Commit**

Run:

```bash
git add web/src/components/SceneForm.tsx web/src/i18n/translations.ts
git commit -m "增加 S1 视频连贯性设置"
```

---

### Task 8: End-To-End Verification And Production Warm Bottle Run

**Files:**

- Modify only if needed after test failures:
  - `src/pipeline/s1_product_pipeline.py`
  - `src/skills/continuity_storyboard_grid.py`
  - `src/skills/seedance_prompt.py`
  - `src/skills/remotion_assemble.py`
  - `rendering/src/VideoComposition.tsx`
  - `web/src/components/SceneForm.tsx`

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_continuity_storyboard_grid.py tests/test_s1_continuity_pipeline.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run backend lint**

Run:

```bash
.venv/bin/ruff check src/skills/continuity_storyboard_grid.py src/skills/seedance_prompt.py src/pipeline/s1_product_pipeline.py src/pipeline/step_runner.py src/routers/_state.py tests/test_continuity_storyboard_grid.py tests/test_s1_continuity_pipeline.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd web && npm run lint
```

Expected:

```text
No ESLint errors
```

- [ ] **Step 4: Run local S1 mock smoke if available**

Run:

```bash
.venv/bin/python -m pytest tests/test_s1_e2e.py::TestS1E2EVideoPrompt -q
```

Expected:

```text
all selected tests pass
```

If this legacy test expects the old `seedance_prompt` dict shape, update the test to assert the current list-of-prompts shape:

```python
assert isinstance(data, list)
assert len(data) >= 1
assert "segment_prompt" in data[0]
```

- [ ] **Step 5: Commit final test alignment if any test files changed**

Run only if Step 4 required test updates:

```bash
git add tests/test_s1_e2e.py
git commit -m "对齐 S1 prompt 测试结构"
```

- [ ] **Step 6: Deploy to Tencent Lighthouse after all tests pass**

Use the existing deploy flow and current production key handling. Do not print secrets.

Run:

```bash
./deploy/lighthouse/deploy.sh
```

Expected:

```text
backend, frontend, rendering, nginx containers recreate or remain healthy
```

- [ ] **Step 7: Submit production bottle-warmer S1 run**

Submit the same warm-bottle scenario with these explicit fields:

```json
{
  "storyboard_grid": "12",
  "continuity_mode": "standard",
  "transition_style": "match_cut",
  "video_duration": 15,
  "enable_media_synthesis": true,
  "target_platforms": ["tiktok"],
  "product_catalog": {
    "product_name": "Momcozy Nutri Bottle Warmer",
    "name": "Momcozy Nutri Bottle Warmer",
    "brand_name": "Momcozy",
    "category": "baby bottle warmer",
    "usage_scenario": "2 AM night feeds at home",
    "usps": [
      "quick night-feed warming",
      "precise temperature control",
      "gentle keep-warm mode"
    ]
  }
}
```

- [ ] **Step 8: Verify production output**

Check the final state and assert:

```text
status = completed
errors = []
steps.continuity_storyboard_grid.status = done
len(steps.continuity_storyboard_grid.output.micro_shots) = 12
len(steps.seedance_clips.output.clip_details) = 4
all clip_details[].is_stub = false
steps.audit.output.asset_ready_audit.status = PASS
steps.audit.output.continuity_score >= 0.8
```

- [ ] **Step 9: Human visual review**

Watch the final video and answer:

```text
1. Does Clip A -> B feel like the bottle action continues?
2. Does Clip B -> C feel like the warming result follows from the button/indicator?
3. Does Clip C -> D feel like a deliberate close rather than a random jump?
4. Is the product still recognizable as a bottle warmer?
```

If any answer is `no`, capture the failing boundary by clip index and fix only that boundary's prompt or transition.

- [ ] **Step 10: Commit verification notes if code or docs changed**

If production findings require a doc update, update the existing spec or runbook rather than creating a root-level note.

Run:

```bash
git status --short
git add <changed-files>
git commit -m "记录 S1 连续分镜验证结果"
```

## Self-Review

Spec coverage:

- 12-grid director storyboard: Task 1 and Task 2.
- Four grouped Seedance clips: Task 3 and Task 4.
- Lightweight transitions: Task 5.
- Asset vs publish audit split: Task 6.
- Minimal frontend control: Task 7.
- Production bottle-warmer verification: Task 8.

Placeholder scan:

- No incomplete markers are present.
- Each code-changing task includes concrete file paths, snippets, commands, and expected results.

Type consistency:

- The plan consistently uses `continuity_storyboard_grid`, `micro_shots`, `clip_groups`, `transition_to_next`, `transition_type`, `storyboard_grid`, `continuity_mode`, and `transition_style`.
- The plan keeps S1 state compatible by adding a new step rather than replacing existing `storyboards`.
