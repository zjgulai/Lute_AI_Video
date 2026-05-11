"""Regression tests for ScriptWriterSkill._self_check_script (bool TypeError fix).

Bug: _self_check_script previously inserted `overall_ok` (bool) into checks dict
BEFORE iterating to compute `overall_score`, causing `c["ok"]` to TypeError on
the bool. Fix snapshots dict_checks before the bool insertion.
"""

from src.skills.script_writer import ScriptWriterSkill


def _passing_script() -> dict:
    return {
        "total_duration": 30,
        "segments": [
            {"segment_type": "hook", "start_time": 0, "end_time": 3, "voiceover": "What if you never had to scrub bottles again?"},
            {"segment_type": "pain_point", "start_time": 3, "end_time": 8, "voiceover": "Tired of scrubbing"},
            {"segment_type": "solution", "start_time": 8, "end_time": 22, "voiceover": "Momcozy KleanPal Pro: 26 jets and steam dry."},
            {"segment_type": "trust_building", "start_time": 22, "end_time": 26, "voiceover": "5 million moms trust Momcozy."},
            {"segment_type": "cta", "start_time": 26, "end_time": 30, "voiceover": "Tap link in bio."},
        ],
    }


def test_self_check_does_not_raise_on_bool() -> None:
    """The fix: previously raised TypeError 'bool object is not subscriptable'."""
    result = ScriptWriterSkill._self_check_script(_passing_script(), brand_guidelines={})
    assert isinstance(result, dict)
    assert result["overall_ok"] is True
    assert 0.0 <= result["overall_score"] <= 1.0


def test_self_check_overall_score_correct() -> None:
    """overall_score must be the fraction of passing checks (over real check dicts only)."""
    result = ScriptWriterSkill._self_check_script(_passing_script(), brand_guidelines={})
    assert result["overall_score"] == 1.0
    assert result["overall_ok"] is True


def test_self_check_partial_failure() -> None:
    """When some checks fail, overall_score reflects fraction; overall_ok is False."""
    bad = {
        "total_duration": 100,
        "segments": [
            {"segment_type": "hook", "start_time": 0, "end_time": 8, "voiceover": "Hello there friends"},
        ],
    }
    result = ScriptWriterSkill._self_check_script(bad, brand_guidelines={})
    assert result["overall_ok"] is False
    assert 0.0 <= result["overall_score"] < 1.0
    assert result["hook_strength"]["ok"] is False
    assert result["duration_compliance"]["ok"] is False
    assert result["segment_completeness"]["ok"] is False


def test_self_check_does_not_corrupt_checks_dict() -> None:
    """overall_ok / overall_score MUST be added, but the 4 check dicts must remain dicts."""
    result = ScriptWriterSkill._self_check_script(_passing_script(), brand_guidelines={})
    for key in ("hook_strength", "usp_coverage", "duration_compliance", "segment_completeness"):
        assert isinstance(result[key], dict), f"{key} should still be a dict, got {type(result[key])}"
        assert "ok" in result[key]
    assert isinstance(result["overall_ok"], bool)
    assert isinstance(result["overall_score"], float)


def test_self_check_empty_segments() -> None:
    """Robust against empty / minimal scripts (zero-division guard)."""
    minimal = {"total_duration": 30, "segments": []}
    result = ScriptWriterSkill._self_check_script(minimal, brand_guidelines={})
    assert isinstance(result, dict)
    assert isinstance(result["overall_score"], float)
