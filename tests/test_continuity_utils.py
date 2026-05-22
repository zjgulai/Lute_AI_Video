"""Unit tests for src/pipeline/continuity_utils.py."""

from __future__ import annotations

from src.pipeline.continuity_utils import (
    all_clips_are_stubs,
    build_continuity_audit_summary,
    build_transitions_from_clip_details,
    collect_captions,
    collect_shots,
    compute_expected_duration,
    normalize_continuity_config,
)

# ── normalize_continuity_config ──


def test_normalize_defaults():
    result = normalize_continuity_config({})
    assert result["continuity_mode"] is True
    assert result["continuity_generation_mode"] == "standard"
    assert result["storyboard_grid"] == 12
    assert result["clip_group_size"] == 3
    assert result["transition_style"] == "match_cut"


def test_normalize_passthrough_valid():
    result = normalize_continuity_config({
        "continuity_mode": "high_quality",
        "storyboard_grid": 24,
        "clip_group_size": 4,
        "transition_style": "soft_crossfade",
    })
    assert result["continuity_mode"] is True
    assert result["continuity_generation_mode"] == "high_quality"
    assert result["storyboard_grid"] == 24
    assert result["clip_group_size"] == 4
    assert result["transition_style"] == "soft_crossfade"


def test_normalize_invalid_values_fallback():
    result = normalize_continuity_config({
        "continuity_mode": "garbage",
        "storyboard_grid": 999,
        "clip_group_size": -1,
        "transition_style": "invalid",
    })
    assert result["continuity_mode"] is True  # garbage != false-ish
    assert result["continuity_generation_mode"] == "standard"
    assert result["storyboard_grid"] == 12
    assert result["clip_group_size"] == 3
    assert result["transition_style"] == "match_cut"


def test_normalize_disabled_modes():
    for disabled in ("0", "false", "no", "off", "disabled"):
        result = normalize_continuity_config({"continuity_mode": disabled})
        assert result["continuity_mode"] is False, f"failed for {disabled!r}"


def test_normalize_explicit_generation_mode():
    result = normalize_continuity_config({
        "continuity_mode": True,
        "continuity_generation_mode": "high_quality",
    })
    assert result["continuity_generation_mode"] == "high_quality"


# ── build_transitions_from_clip_details ──


def test_build_transitions_basic():
    details = [
        {"transition_to_next": "match cut", "transition_type": "match_cut"},
        {"transition_to_next": "soft fade", "transition_type": "soft_crossfade"},
        {},  # last has no transition
    ]
    transitions = build_transitions_from_clip_details(details)
    assert len(transitions) == 2
    assert transitions[0] == {
        "from_clip": 1, "to_clip": 2,
        "type": "match_cut", "duration_frames": 8,
        "description": "match cut",
    }
    assert transitions[1] == {
        "from_clip": 2, "to_clip": 3,
        "type": "soft_crossfade", "duration_frames": 12,
        "description": "soft fade",
    }


def test_build_transitions_empty():
    assert build_transitions_from_clip_details([]) == []
    assert build_transitions_from_clip_details([{}]) == []


# ── build_continuity_audit_summary ──


def test_audit_summary_with_micro_shots():
    report = build_continuity_audit_summary(
        base_audit={"overall_status": "PASS", "overall_score": 0.9},
        clip_details=[
            {"is_stub": False, "transition_to_next": "cut"},
            {"is_stub": False},
        ],
        continuity_grid={
            "micro_shots": [
                {"continuity_in": "a", "continuity_out": "b"},
                {"continuity_in": "c", "continuity_out": "d"},
            ],
        },
        final_video_path="/tmp/final.mp4",
    )
    assert report["asset_ready_audit"]["status"] == "PASS"
    assert report["asset_ready_audit"]["checks"]["non_stub_clips"] is True
    assert report["asset_ready_audit"]["checks"]["transition_metadata"] is True
    assert report["asset_ready_audit"]["checks"]["micro_shot_continuity"] is True
    assert report["asset_ready_audit"]["checks"]["final_video_present"] is True
    assert report["continuity_score"] == 1.0


def test_audit_summary_without_continuity_grid():
    """S4/S5 scenario: no micro_shots, should skip that check (score as True)."""
    report = build_continuity_audit_summary(
        base_audit={"overall_status": "FAIL", "overall_score": 0.7},
        clip_details=[
            {"is_stub": False, "transition_to_next": "cut"},
            {"is_stub": False},
        ],
        continuity_grid=None,
        final_video_path="/tmp/final.mp4",
    )
    assert report["asset_ready_audit"]["status"] == "PASS"
    assert report["asset_ready_audit"]["checks"]["micro_shot_continuity"] is True
    assert report["publish_ready_audit"]["status"] == "FAIL"


def test_audit_summary_fails_when_stub():
    report = build_continuity_audit_summary(
        base_audit={"overall_status": "PASS"},
        clip_details=[{"is_stub": True}],
        continuity_grid=None,
        final_video_path="/tmp/final.mp4",
    )
    assert report["asset_ready_audit"]["status"] == "FAIL"
    assert report["asset_ready_audit"]["checks"]["non_stub_clips"] is False


def test_audit_summary_fails_when_no_final_video():
    report = build_continuity_audit_summary(
        base_audit={"overall_status": "PASS"},
        clip_details=[{"is_stub": False}],
        continuity_grid=None,
        final_video_path="",
    )
    assert report["asset_ready_audit"]["status"] == "FAIL"
    assert report["asset_ready_audit"]["checks"]["final_video_present"] is False


def test_audit_summary_handles_invalid_entries():
    report = build_continuity_audit_summary(
        base_audit={},
        clip_details=[
            {"is_stub": False, "transition_to_next": "match cut"},
            "invalid clip detail",
            {"is_stub": False},
        ],
        continuity_grid={
            "micro_shots": [
                {"continuity_in": "a", "continuity_out": "b"},
                "invalid shot",
                {"continuity_in": "c", "continuity_out": "d"},
            ],
        },
        final_video_path="/tmp/final.mp4",
    )
    # invalid clip_detail (string) causes clips_are_valid = False
    assert report["asset_ready_audit"]["checks"]["non_stub_clips"] is False


# ── all_clips_are_stubs ──


def test_all_stubs_with_metadata():
    assert all_clips_are_stubs(
        ["/a.mp4"],
        [{"is_stub": True}],
    ) is True
    assert all_clips_are_stubs(
        ["/a.mp4", "/b.mp4"],
        [{"is_stub": False}, {"is_stub": True}],
    ) is False


def test_all_stubs_filename_fallback():
    assert all_clips_are_stubs(["stub_abc.mp4"]) is True
    assert all_clips_are_stubs(["/data/stubborn/product.mp4"]) is False
    assert all_clips_are_stubs(["real.mp4"]) is False


def test_all_stubs_empty():
    assert all_clips_are_stubs([]) is True


# ── collect_shots ──


def test_collect_shots_from_storyboards():
    storyboards = [
        {"shots": [
            {"start_time": 0, "end_time": 3, "description": "shot1"},
            {"start_time": 3, "end_time": 5, "description": "shot2"},
        ]},
    ]
    shots = collect_shots(storyboards, None)
    assert len(shots) == 2
    assert shots[0]["start_time"] == 0
    assert shots[0]["end_time"] == 3
    assert shots[1]["start_time"] == 3
    assert shots[1]["end_time"] == 5


def test_collect_shots_from_scripts_fallback():
    scripts = [
        {"segments": [
            {"start_time": 0, "end_time": 2, "description": "seg1"},
            {"start_time": 2, "end_time": 5, "description": "seg2"},
        ]},
    ]
    shots = collect_shots(None, scripts)
    assert len(shots) == 2
    assert shots[0]["start_time"] == 0
    assert shots[0]["end_time"] == 2
    assert shots[1]["start_time"] == 2
    assert shots[1]["end_time"] == 5


def test_collect_shots_prioritizes_storyboards():
    storyboards = [{"shots": [{"start_time": 0, "end_time": 1, "description": "s"}]}]
    scripts = [{"segments": [{"start_time": 0, "end_time": 5, "description": "seg"}]}]
    shots = collect_shots(storyboards, scripts)
    assert len(shots) == 1
    assert shots[0]["end_time"] == 1  # from storyboard, not script


def test_collect_shots_empty():
    assert collect_shots(None, None) == []


# ── collect_captions ──


def test_collect_captions_basic():
    scripts = [
        {"segments": [
            {"start_time": 0, "end_time": 3, "voiceover": "Hello"},
            {"start_time": 3, "end_time": 5, "description": "World"},
        ]},
    ]
    captions = collect_captions(scripts)
    assert len(captions) == 2
    assert captions[0]["text"] == "Hello"
    assert captions[1]["text"] == "World"
    assert captions[0]["start_time"] == 0
    assert captions[1]["start_time"] == 3


def test_collect_captions_skips_empty_text():
    scripts = [
        {"segments": [
            {"start_time": 0, "end_time": 3, "voiceover": ""},
            {"start_time": 3, "end_time": 5, "description": ""},
        ]},
    ]
    assert collect_captions(scripts) == []


# ── compute_expected_duration ──


def test_compute_expected_duration_basic():
    scripts = [
        {"segments": [
            {"start_time": 0, "end_time": 3},
            {"start_time": 3, "end_time": 7},
        ]},
    ]
    assert compute_expected_duration(scripts) == 7.0


def test_compute_expected_duration_empty():
    assert compute_expected_duration([]) == 30.0


def test_compute_expected_duration_negative_protection():
    scripts = [{"segments": [{"start_time": 5, "end_time": 3}]}]
    assert compute_expected_duration(scripts) == 1.0  # max(duration, 1.0)
