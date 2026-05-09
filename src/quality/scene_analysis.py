"""Scene analysis — optional PySceneDetect wrapper for video structure understanding.

Detects shot boundaries and scene changes in a video. Used by media_quality_audit
to upgrade video structure analysis from text-based to visual-based.

Usage:
    from src.quality.scene_analysis import SceneAnalyzer
    scenes = SceneAnalyzer().detect_scenes(video_path)
    # scenes = [{"start": 0.0, "end": 5.2, "duration": 5.2}, ...]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Minimum scene duration — anything shorter is likely a false positive
MIN_SCENE_DURATION = 1.0


class SceneAnalyzer:
    """Lazy-loaded scene detector using PySceneDetect (optional)."""

    def __init__(self):
        self._available: bool | None = None

    def _check(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            self._available = True
            logger.info("scene_analyzer: PySceneDetect available")
        except Exception as e:
            self._available = False
            logger.warning(
                "scene_analyzer: PySceneDetect not available — scene analysis skipped. "
                "Install with: pip install scenedetect",
                error=str(e),
            )
        return self._available

    def detect_scenes(self, video_path: str | Path) -> list[dict[str, float]]:
        """Detect scene boundaries in a video.

        Returns list of scene dicts: [{"start": float, "end": float, "duration": float}, ...]
        Returns empty list if PySceneDetect unavailable or video invalid.
        """
        path = Path(video_path)
        if not path.exists() or path.stat().st_size < 1000:
            return []

        if not self._check():
            return []

        try:
            from scenedetect import ContentDetector, SceneManager, open_video

            video = open_video(str(path))
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=27.0))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            scenes = []
            for start, end in scene_list:
                start_sec = start.get_seconds()
                end_sec = end.get_seconds()
                dur = end_sec - start_sec
                if dur >= MIN_SCENE_DURATION:
                    scenes.append({
                        "start": round(start_sec, 2),
                        "end": round(end_sec, 2),
                        "duration": round(dur, 2),
                    })

            logger.info(
                "scene_analyzer: detected scenes",
                path=str(path),
                count=len(scenes),
            )
            return scenes
        except Exception as e:
            logger.warning("scene_analyzer: detection failed", error=str(e))
            return []

    def analyze_structure(self, video_path: str | Path, expected_segments: int = 3) -> dict[str, Any]:
        """Analyze video scene structure and compare to expected segment count.

        Returns dict with scene count, avg duration, structural_match score.
        """
        scenes = self.detect_scenes(video_path)
        if not scenes:
            return {
                "scene_count": 0,
                "avg_duration": 0.0,
                "structural_match": 0.5,
                "details": "scene detection unavailable or failed",
            }

        total_dur = sum(s["duration"] for s in scenes)
        avg_dur = total_dur / len(scenes) if scenes else 0

        # Structural match: how close is scene count to expected segments?
        diff = abs(len(scenes) - expected_segments)
        if diff == 0:
            match_score = 1.0
        elif diff == 1:
            match_score = 0.8
        elif diff <= 2:
            match_score = 0.5
        else:
            match_score = 0.2

        return {
            "scene_count": len(scenes),
            "avg_duration": round(avg_dur, 2),
            "structural_match": match_score,
            "scenes": scenes,
            "details": f"{len(scenes)} scenes detected, expected {expected_segments}",
        }
