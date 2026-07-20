"""Face consistency checker — optional MediaPipe wrapper for identity verification.

Replaces histogram-based face comparison with embedding-based cosine similarity
when MediaPipe or deepface is available.

Usage:
    from src.quality.face_consistency import FaceConsistencyChecker
    score = checker.compare(video_frame_path, reference_image_path)
    # score = 0.0-1.0 float or None
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from src.tools.safe_media import ffmpeg_local_input_args, ffprobe_local_input_args

logger = structlog.get_logger()

# Cosine similarity thresholds for face matching
FACE_MATCH_STRONG = 0.65
FACE_MATCH_WEAK = 0.40


class FaceConsistencyChecker:
    """Lazy-loaded face embedding comparison using MediaPipe or deepface."""

    def __init__(self):
        self._mediapipe_available: bool | None = None
        self._deepface_available: bool | None = None

    def _check_mediapipe(self) -> bool:
        if self._mediapipe_available is not None:
            return self._mediapipe_available
        try:
            self._mediapipe_available = True
            logger.info("face_consistency: MediaPipe available")
        except Exception:
            self._mediapipe_available = False
        return self._mediapipe_available

    def _check_deepface(self) -> bool:
        if self._deepface_available is not None:
            return self._deepface_available
        try:
            self._deepface_available = True
            logger.info("face_consistency: DeepFace available")
        except Exception:
            self._deepface_available = False
        return self._deepface_available

    def compare(self, image_a: str | Path, image_b: str | Path) -> float | None:
        """Compare two face images and return similarity score.

        Returns:
            float in [0, 1] — higher = more similar.
            None if no face library available or no face detected.
        """
        path_a = Path(image_a)
        path_b = Path(image_b)
        if not path_a.exists() or not path_b.exists():
            return None

        # Try DeepFace first (more accurate)
        if self._check_deepface():
            return self._compare_deepface(path_a, path_b)

        # Fall back to MediaPipe
        if self._check_mediapipe():
            return self._compare_mediapipe(path_a, path_b)

        logger.warning(
            "face_consistency: no face library available — "
            "install with: pip install deepface or pip install mediapipe"
        )
        return None

    def _compare_deepface(self, path_a: Path, path_b: Path) -> float | None:
        try:
            from deepface import DeepFace

            result = DeepFace.verify(
                img1_path=str(path_a),
                img2_path=str(path_b),
                model_name="Facenet",
                detector_backend="opencv",
                enforce_detection=False,
            )
            # result["distance"] is L2 distance; map to 0-1 similarity
            distance = result.get("distance", 1.0)
            # Facenet typical threshold ~0.4 for same person
            similarity = max(0.0, 1.0 - distance / 0.6)
            return round(similarity, 3)
        except Exception as e:
            logger.warning("face_consistency: DeepFace comparison failed", error=str(e))
            return None

    def _compare_mediapipe(self, path_a: Path, path_b: Path) -> float | None:
        try:
            import mediapipe as mp
            import numpy as np
            from PIL import Image

            mp_face = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
            )

            def _get_embedding(img_path: Path) -> np.ndarray | None:
                img = Image.open(img_path).convert("RGB")
                arr = np.array(img)
                results = mp_face.process(arr)
                if not results.multi_face_landmarks:
                    return None
                # Use 468 landmarks as embedding
                landmarks = results.multi_face_landmarks[0].landmark
                return np.array([[lm.x, lm.y, lm.z] for lm in landmarks]).flatten()

            emb_a = _get_embedding(path_a)
            emb_b = _get_embedding(path_b)
            mp_face.close()

            if emb_a is None or emb_b is None:
                return None

            # Cosine similarity
            dot = np.dot(emb_a, emb_b)
            norm = np.linalg.norm(emb_a) * np.linalg.norm(emb_b)
            if norm == 0:
                return None
            similarity = float(dot / norm)
            # MediaPipe landmarks are very stable — threshold is higher
            return round((similarity + 1) / 2, 3)  # map [-1, 1] → [0, 1]
        except Exception as e:
            logger.warning("face_consistency: MediaPipe comparison failed", error=str(e))
            return None

    def check_video_consistency(
        self,
        video_path: str | Path,
        reference_image_path: str | Path,
        sample_count: int = 3,
    ) -> dict[str, Any]:
        """Check face consistency across sampled video frames vs reference.

        Returns dict with overall score, per-frame results, and recommendation.
        """
        import subprocess
        import tempfile

        path = Path(video_path)
        ref = Path(reference_image_path)
        if not path.exists() or not ref.exists():
            return {
                "score": None,
                "consistent": None,
                "frames_checked": 0,
                "recommendation": "video or reference image not found",
            }

        # Get duration
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    *ffprobe_local_input_args(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(result.stdout.strip() or "0")
        except Exception:
            duration = 0.0

        if duration <= 0:
            return {
                "score": None,
                "consistent": None,
                "frames_checked": 0,
                "recommendation": "could not measure video duration",
            }

        scores = []
        for i in range(sample_count):
            ts = duration * (i + 1) / (sample_count + 1)
            try:
                fd, frame_path_str = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                frame_path = Path(frame_path_str)
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", str(ts),
                        *ffmpeg_local_input_args(path), "-vframes", "1",
                        "-q:v", "2", str(frame_path),
                    ],
                    capture_output=True, timeout=10, check=True,
                )
                if frame_path.exists():
                    score = self.compare(frame_path, ref)
                    if score is not None:
                        scores.append(score)
                frame_path.unlink(missing_ok=True)
            except Exception:
                continue

        if not scores:
            return {
                "score": None,
                "consistent": None,
                "frames_checked": 0,
                "recommendation": "no faces detected or comparison library unavailable",
            }

        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        consistent = avg_score >= FACE_MATCH_STRONG and min_score >= FACE_MATCH_WEAK

        return {
            "score": round(avg_score, 3),
            "min_score": round(min_score, 3),
            "consistent": consistent,
            "frames_checked": len(scores),
            "per_frame_scores": [round(s, 3) for s in scores],
            "recommendation": (
                "" if consistent
                else "Identity drift detected — regenerate clips with stronger identity preservation"
            ),
        }
