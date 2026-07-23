"""Shared continuity utilities for S1-S5 video pipelines.

Extracted from S1ProductDirectPipeline to eliminate duplication across:
- _extract_clip_last_frame (S1, S3, S4)
- _all_clips_are_stubs (S1, S5)
- _normalize_continuity_config (S1)
- _build_continuity_audit_summary (S1)
- _collect_shots / _collect_captions (S1)
- _compute_expected_duration (S1)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import structlog

from src.models.runtime_contracts import (
    ContinuityAuditSummary,
    ContinuityDirection,
    TransitionMetadata,
)
from src.tools.safe_media import ffmpeg_local_input_args

logger = structlog.get_logger()

# Default cap for clips per run — matches S1's MAX_CLIPS_PER_DEMO
DEFAULT_MAX_CLIPS = 3


def normalize_continuity_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize continuity options while preserving false as an explicit skip.

    Returns:
        {
            "continuity_mode": bool,
            "continuity_generation_mode": "standard" | "high_quality",
            "storyboard_grid": int,
            "clip_group_size": int,
            "transition_style": str,
        }
    """
    generation_modes = {"standard", "high_quality"}
    raw_mode = config.get("continuity_mode", True)
    continuity_generation_mode = "standard"
    if isinstance(raw_mode, str):
        normalized_mode = raw_mode.strip().lower()
        if normalized_mode in generation_modes:
            continuity_mode = True
            continuity_generation_mode = normalized_mode
        else:
            continuity_mode = normalized_mode not in {"0", "false", "no", "off", "disabled"}
    else:
        continuity_mode = bool(raw_mode)

    raw_generation_mode = config.get("continuity_generation_mode")
    if continuity_mode and isinstance(raw_generation_mode, str):
        normalized_generation_mode = raw_generation_mode.strip().lower()
        if normalized_generation_mode in generation_modes:
            continuity_generation_mode = normalized_generation_mode

    try:
        storyboard_grid = int(config.get("storyboard_grid", 12))
    except (TypeError, ValueError):
        storyboard_grid = 12
    if storyboard_grid not in {9, 12, 24}:
        storyboard_grid = 12

    try:
        clip_group_size = int(config.get("clip_group_size", 3))
    except (TypeError, ValueError):
        clip_group_size = 3
    if clip_group_size <= 0:
        clip_group_size = 3

    transition_style = str(config.get("transition_style") or "match_cut")
    if transition_style not in {"clean", "soft_crossfade", "match_cut"}:
        transition_style = "match_cut"

    return {
        "continuity_mode": continuity_mode,
        "continuity_generation_mode": continuity_generation_mode,
        "storyboard_grid": storyboard_grid,
        "clip_group_size": clip_group_size,
        "transition_style": transition_style,
    }


def extract_clip_last_frame(video_path: str, output_dir: str) -> str | None:
    """Extract the last frame of a video clip as a JPEG for continuity.

    Uses ffmpeg to seek to the last frame: ffmpeg -sseof -1 -i {video_path}
    -frames:v 1 -q:v 2 {output_path}.

    Args:
        video_path: Absolute path to the source .mp4 clip.
        output_dir: Directory to write the extracted frame into.

    Returns:
        Absolute path to the extracted JPEG, or None on any failure (missing
        ffmpeg, corrupt file, etc.).
    """
    src = Path(video_path)
    if not src.exists() or src.stat().st_size < 100:
        return None

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_path = out_dir / f"last_frame_{src.stem}.jpg"

    try:
        cmd = [
            "ffmpeg", "-y",
            "-sseof", "-1",
            *ffmpeg_local_input_args(src),
            "-frames:v", "1",
            "-q:v", "2",
            str(frame_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=15, check=True)
        if frame_path.exists() and frame_path.stat().st_size > 100:
            return str(frame_path)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, Exception) as exc:
        logger.debug(
            "continuity_last_frame_extract_failed",
            path=str(src),
            error=str(exc),
        )
    return None


def build_transitions_from_clip_details(
    clip_details: list[dict[str, Any]],
) -> list[TransitionMetadata]:
    """Build Remotion transitions list from clip_details metadata.

    Input: [{"transition_to_next": "...", "transition_type": "match_cut", ...}, ...]
    Output: [{"from_clip": 1, "to_clip": 2, "type": "match_cut",
              "duration_frames": 8, "description": "..."}, ...]
    """
    transitions: list[TransitionMetadata] = []
    for idx, detail in enumerate(clip_details):
        transition_to_next = detail.get("transition_to_next", "")
        if idx >= len(clip_details) - 1 or not transition_to_next:
            continue
        transition_type = detail.get("transition_type", "clean")
        transitions.append({
            "from_clip": idx + 1,
            "to_clip": idx + 2,
            "type": transition_type,
            "duration_frames": 12 if transition_type == "soft_crossfade" else 8,
            "description": transition_to_next,
        })
    return transitions


def build_continuity_audit_summary(
    base_audit: dict[str, Any],
    clip_details: list[dict[str, Any]],
    continuity_grid: dict[str, Any] | None,
    final_video_path: str,
) -> ContinuityAuditSummary:
    """Build a continuity-aware audit summary with asset/publish split.

    When continuity_grid is None (S4/S5 scenarios without micro_shots),
    the micro_shot_continuity check is skipped and scored as True so the
    overall continuity_score reflects only clips + transitions + final video.
    """
    base_audit = base_audit if isinstance(base_audit, dict) else {}
    clip_details = clip_details if isinstance(clip_details, list) else []
    valid_clip_details: list[dict[str, Any]] = [
        detail for detail in clip_details if isinstance(detail, dict)
    ]
    clips_are_valid = bool(clip_details) and len(valid_clip_details) == len(clip_details)
    non_stub_ok = clips_are_valid and all(
        not detail.get("is_stub") for detail in valid_clip_details
    )
    transitions = [
        detail.get("transition_to_next") for detail in valid_clip_details[:-1]
    ]
    transition_ok = clips_are_valid and (
        all(bool(t) for t in transitions)
        if len(valid_clip_details) > 1
        else True
    )

    # Remember whether caller passed None (S4/S5 don't have micro_shots)
    continuity_grid_is_none = continuity_grid is None
    continuity_grid = continuity_grid if isinstance(continuity_grid, dict) else {}
    micro_shots = continuity_grid.get("micro_shots") or []
    micro_shots = micro_shots if isinstance(micro_shots, list) else []
    clip_groups = continuity_grid.get("clip_groups") or []
    clip_groups = clip_groups if isinstance(clip_groups, list) else []
    valid_micro_shots = [
        shot for shot in micro_shots if isinstance(shot, dict)
    ]
    valid_clip_groups = [
        group for group in clip_groups if isinstance(group, dict)
    ]
    # When no micro_shots available (S4/S5), score this check as True
    # so the overall score isn't unfairly penalized.
    if not micro_shots and continuity_grid_is_none:
        micro_continuity_ok = True
    else:
        micro_continuity_ok = (
            bool(micro_shots)
            and len(valid_micro_shots) == len(micro_shots)
            and all(
                shot.get("continuity_in") and shot.get("continuity_out")
                for shot in valid_micro_shots
            )
        )
    if not clip_groups and continuity_grid_is_none:
        director_intent_ok = True
    elif not clip_groups:
        # Legacy grids predate clip_groups. Do not penalize a valid micro-shot
        # grid solely because director metadata did not exist yet.
        director_intent_ok = micro_continuity_ok
    else:
        director_intent_ok = (
            bool(clip_groups)
            and len(valid_clip_groups) == len(clip_groups)
            and all(
                group.get("scene_beat")
                and group.get("beat_summary")
                and group.get("transition_intent")
                for group in valid_clip_groups
            )
        )
    final_video_ok = bool(final_video_path)

    score_parts = [
        1.0 if non_stub_ok else 0.0,
        1.0 if transition_ok else 0.0,
        1.0 if micro_continuity_ok else 0.0,
        1.0 if director_intent_ok else 0.0,
        1.0 if final_video_ok else 0.0,
    ]
    continuity_score = round(sum(score_parts) / len(score_parts), 3)
    asset_status = (
        "PASS"
        if continuity_score >= 0.8 and final_video_ok and non_stub_ok
        else "FAIL"
    )
    publish_status = base_audit.get("overall_status", "WARN")
    publish_score = base_audit.get("overall_score", 0)

    clip_directions: list[ContinuityDirection] = []
    scene_beats: list[str] = []
    transition_intents: list[str] = []
    for group in valid_clip_groups:
        scene_beat = group.get("scene_beat")
        beat_summary = group.get("beat_summary")
        transition_intent = group.get("transition_intent")
        scene_beat = scene_beat if isinstance(scene_beat, str) else ""
        beat_summary = beat_summary if isinstance(beat_summary, str) else ""
        transition_intent = transition_intent if isinstance(transition_intent, str) else ""
        if scene_beat or beat_summary or transition_intent:
            clip_directions.append({
                "scene_beat": scene_beat,
                "beat_summary": beat_summary,
                "transition_intent": transition_intent,
            })
        if scene_beat:
            scene_beats.append(scene_beat)
        if transition_intent:
            transition_intents.append(transition_intent)

    summary = cast(ContinuityAuditSummary, dict(base_audit))
    summary["asset_ready_audit"] = {
            "status": asset_status,
            "checks": {
                "non_stub_clips": non_stub_ok,
                "transition_metadata": transition_ok,
                "micro_shot_continuity": micro_continuity_ok,
                "director_intent_metadata": director_intent_ok,
                "final_video_present": final_video_ok,
            },
        }
    summary["publish_ready_audit"] = {
            "status": publish_status,
            "overall_status": publish_status,
            "overall_score": publish_score,
            "base_score": publish_score,
            "criteria": base_audit.get("criteria", []),
        }
    summary["continuity_direction_summary"] = {
            "clip_directions": clip_directions,
            "scene_beats": scene_beats,
            "transition_intents": transition_intents,
        }
    summary["continuity_score"] = continuity_score
    return summary


def extract_continuity_diagnostics(audit_report: dict[str, Any] | None) -> dict[str, Any]:
    """Extract compact continuity diagnostics for status/gate responses."""
    audit_report = audit_report if isinstance(audit_report, dict) else {}
    asset_ready = audit_report.get("asset_ready_audit") or {}
    asset_ready = asset_ready if isinstance(asset_ready, dict) else {}
    checks = asset_ready.get("checks") or {}
    checks = checks if isinstance(checks, dict) else {}
    direction_summary = audit_report.get("continuity_direction_summary") or {}
    direction_summary = direction_summary if isinstance(direction_summary, dict) else {}
    clip_directions = direction_summary.get("clip_directions") or []
    if not isinstance(clip_directions, list):
        clip_directions = []

    return {
        "continuity_score": audit_report.get("continuity_score"),
        "asset_ready_status": asset_ready.get("status"),
        "director_intent_metadata": checks.get("director_intent_metadata"),
        "clip_directions": clip_directions,
        "scene_beats": direction_summary.get("scene_beats", []),
        "transition_intents": direction_summary.get("transition_intents", []),
    }


def collect_shots(
    storyboards: list[dict[str, Any]] | None,
    scripts: list[dict[str, Any]] | None,
    max_clips: int = DEFAULT_MAX_CLIPS,
) -> list[dict[str, Any]]:
    """Flatten storyboards into a single shot list with absolute timing.

    If storyboards is None or empty, derives shots from scripts' segments.
    """
    shots: list[dict[str, Any]] = []
    cursor = 0.0

    if storyboards:
        for board in storyboards:
            for shot in board.get("shots", []):
                duration = float(shot.get("end_time", 0)) - float(shot.get("start_time", 0))
                duration = max(duration, 1.0)
                shots.append({
                    "id": len(shots) + 1,
                    "start_time": cursor,
                    "end_time": cursor + duration,
                    "text_overlay": shot.get("text_overlay", "") or shot.get("description", ""),
                    "visual": shot.get("visual", "") or shot.get("description", ""),
                })
                cursor += duration
    elif scripts:
        for script in (scripts or [])[:max_clips]:
            for seg in script.get("segments", []):
                duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
                duration = max(duration, 1.0)
                shots.append({
                    "id": len(shots) + 1,
                    "start_time": cursor,
                    "end_time": cursor + duration,
                    "text_overlay": seg.get("description", "")[:60],
                    "visual": seg.get("visual_description", "") or seg.get("description", ""),
                })
                cursor += duration
    return shots


def collect_captions(
    scripts: list[dict[str, Any]],
    max_clips: int = DEFAULT_MAX_CLIPS,
) -> list[dict[str, Any]]:
    """Collect captions from scripts' segments with absolute timing."""
    captions: list[dict[str, Any]] = []
    cursor = 0.0
    for script in scripts[:max_clips]:
        for seg in script.get("segments", []):
            duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
            text = seg.get("voiceover", "") or seg.get("description", "")
            if text:
                captions.append({
                    "start_time": cursor,
                    "end_time": cursor + max(duration, 1.0),
                    "text": text[:80],
                })
            cursor += max(duration, 1.0)
    return captions


def compute_expected_duration(
    scripts: list[dict[str, Any]],
    max_clips: int = DEFAULT_MAX_CLIPS,
) -> float:
    """Compute expected video duration from scripts' segments."""
    total = 0.0
    for script in scripts[:max_clips]:
        for seg in script.get("segments", []):
            duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
            total += max(duration, 1.0)
    return total or 30.0


def all_clips_are_stubs(
    clip_paths: list[str],
    clip_details: list[dict[str, Any]] | None = None,
) -> bool:
    """Detect whether every clip is a stub file.

    Uses explicit is_stub metadata from clip_details when available,
    falling back to filename-based detection (stub files start with 'stub_').
    This avoids false positives from legitimate paths containing 'stub'
    as a substring (e.g. '/data/stubborn/product.mp4').
    """
    if not clip_paths:
        return True
    if clip_details and len(clip_details) == len(clip_paths):
        return all(
            (not isinstance(detail, dict)) or detail.get("is_stub", False)
            for detail in clip_details
        )
    # Filename fallback: stub files generated by SeedanceClient._stub_result
    # follow the pattern 'stub_<mode>_<hash>.mp4'
    return all(os.path.basename(str(p)).lower().startswith("stub_") for p in clip_paths)
