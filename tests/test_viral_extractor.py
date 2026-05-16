from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.skills.base import SkillResult
from src.skills.viral_extractor import HOOK_FORMULAS, ViralExtractorSkill


def _analysis(
    hook_type: str = "pain_point",
    speech_style: str = "punchy",
    segments: list[dict[str, Any]] | None = None,
    emotion_curve: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "hook_type": hook_type,
        "speech_style": speech_style,
        "segments": segments or [
            {"type": "hook", "start": 0.0, "end": 3.0, "description": "Open with pain"},
            {"type": "body", "start": 3.0, "end": 9.0, "description": "Demonstrate fix"},
            {"type": "close", "start": 9.0, "end": 12.0, "description": "CTA"},
        ],
        "emotion_curve": emotion_curve or [
            {"emotion": "frustration", "intensity": 0.8},
            {"emotion": "relief", "intensity": 0.7},
            {"emotion": "excitement", "intensity": 0.9},
        ],
    }


def _run(skill: ViralExtractorSkill, params: dict[str, Any]) -> SkillResult:
    return asyncio.run(skill.execute(params))


def test_validate_params_requires_analysis():
    skill = ViralExtractorSkill()
    errors = skill.validate_params({})
    assert errors and any("analysis" in e for e in errors)


def test_validate_params_passes_with_analysis():
    skill = ViralExtractorSkill()
    assert skill.validate_params({"analysis": {"hook_type": "question"}}) == []


def test_validate_output_rejects_none():
    skill = ViralExtractorSkill()
    assert skill.validate_output(None) == ["output is None"]


def test_execute_returns_4_keys():
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": _analysis()})
    assert result.success is True
    keys = set(result.data.keys())
    assert keys == {"hook_formula", "engagement_pacing", "emotional_triggers", "pattern_signature"}


def test_hook_formula_picks_known_template_for_pain_point():
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": _analysis(hook_type="pain_point")})
    formula = result.data["hook_formula"]
    assert formula["hook_type"] == "pain_point"
    assert formula["formula"] == HOOK_FORMULAS["pain_point"]
    assert formula["reusable"] is True


def test_hook_formula_falls_back_for_unknown_type():
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": _analysis(hook_type="never_seen_before")})
    formula = result.data["hook_formula"]
    assert formula["hook_type"] == "never_seen_before"
    assert formula["formula"] == "Generic → Detail → Action"


def test_pacing_uses_default_when_no_segments():
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": {"hook_type": "data_drop", "segments": []}})
    pacing = result.data["engagement_pacing"]
    assert len(pacing) == 3
    purposes = {p["purpose"] for p in pacing}
    assert purposes == {"hook", "value", "cta"}
    total_pct = sum(p["duration_pct"] for p in pacing)
    assert total_pct == 100


def test_pacing_uses_provided_segments_when_present():
    skill = ViralExtractorSkill()
    segs = [
        {"type": "intro", "start": 0.0, "end": 2.5, "description": "First half"},
        {"type": "outro", "start": 2.5, "end": 5.0, "description": "Second half"},
    ]
    result = _run(skill, {"analysis": _analysis(segments=segs)})
    pacing = result.data["engagement_pacing"]
    assert len(pacing) == 2
    assert pacing[0]["type"] == "intro"
    assert pacing[1]["type"] == "outro"
    assert pacing[0]["start"] == 0.0


def test_pacing_handles_segment_aliases_segment_type_and_start_time():
    skill = ViralExtractorSkill()
    segs = [
        {"segment_type": "aliased_hook", "start_time": 1.0, "end_time": 4.0, "description": "x" * 200},
    ]
    result = _run(skill, {"analysis": {"hook_type": "story_hook", "segments": [], **{"segments": segs}}})
    p = result.data["engagement_pacing"][0]
    assert p["type"] == "aliased_hook"
    assert p["start"] == 1.0
    assert p["end"] == 4.0
    assert len(p["purpose"]) == 80


def test_emotions_default_when_curve_empty():
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": {"hook_type": "question", "segments": [], "emotion_curve": []}})
    triggers = result.data["emotional_triggers"]
    assert len(triggers) == 2
    assert {t["emotion"] for t in triggers} == {"curiosity", "urgency"}


def test_emotions_dedupes_repeats_in_curve():
    skill = ViralExtractorSkill()
    curve = [
        {"emotion": "joy", "intensity": 0.8},
        {"emotion": "joy", "intensity": 0.9},
        {"emotion": "anger", "intensity": 0.6},
    ]
    result = _run(skill, {"analysis": _analysis(emotion_curve=curve)})
    triggers = result.data["emotional_triggers"]
    emotions = [t["emotion"] for t in triggers]
    assert emotions == ["joy", "anger"]


def test_signature_is_deterministic_for_same_input():
    skill = ViralExtractorSkill()
    a1 = _analysis(hook_type="counter_narrative", speech_style="punchy")
    a2 = _analysis(hook_type="counter_narrative", speech_style="punchy")
    r1 = _run(skill, {"analysis": a1})
    r2 = _run(skill, {"analysis": a2})
    assert r1.data["pattern_signature"] == r2.data["pattern_signature"]
    assert len(r1.data["pattern_signature"]) == 12


def test_signature_changes_when_hook_type_changes():
    skill = ViralExtractorSkill()
    r1 = _run(skill, {"analysis": _analysis(hook_type="pain_point")})
    r2 = _run(skill, {"analysis": _analysis(hook_type="data_drop")})
    assert r1.data["pattern_signature"] != r2.data["pattern_signature"]


def test_fallback_returns_success_with_default_analysis():
    skill = ViralExtractorSkill()
    result = skill.fallback({"analysis": {}})
    assert result.success is True
    assert "hook_formula" in result.data
    assert "engagement_pacing" in result.data
    assert "emotional_triggers" in result.data
    assert "pattern_signature" in result.data


def test_fallback_works_without_params():
    skill = ViralExtractorSkill()
    result = skill.fallback({})
    assert result.success is True
    assert result.data["hook_formula"]["hook_type"] == "question"


@pytest.mark.parametrize("hook_type", list(HOOK_FORMULAS.keys()))
def test_all_known_hook_formulas_resolve(hook_type: str):
    skill = ViralExtractorSkill()
    result = _run(skill, {"analysis": _analysis(hook_type=hook_type)})
    assert result.data["hook_formula"]["formula"] == HOOK_FORMULAS[hook_type]


def test_skill_auto_registers_with_registry():
    from src.skills.registry import SkillRegistry
    reg = SkillRegistry()
    assert "viral-extractor-skill" in reg._skills
