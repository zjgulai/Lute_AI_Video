"""No-reference image/video quality assessment — optional, lazy-imported.

Provides BRISQUE-like quality scoring without requiring a reference image.
Uses a cascade of checks:
1. Laplacian variance (blur detection)
2. Michelson contrast
3. Brightness distribution (over/under-exposure)

If pyiqa/piq are installed, uses real BRISQUE/NIQE metrics.
Otherwise falls back to OpenCV-based heuristics.

Usage:
    from src.quality.nr_quality import NRQualityChecker
    report = NRQualityChecker().check_image(image_path)
    # report = {"score": 0.82, "blur_ok": True, "contrast_ok": True, ...}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from src.tools.safe_media import ffmpeg_local_input_args, ffprobe_local_input_args

logger = structlog.get_logger()

# Thresholds for OpenCV fallback heuristics
BLUR_THRESHOLD = 100.0       # Laplacian variance < 100 = blurry
CONTRAST_THRESHOLD = 0.15    # Michelson contrast < 0.15 = low contrast
BRIGHTNESS_LOW = 30.0        # mean brightness < 30 = underexposed
BRIGHTNESS_HIGH = 225.0      # mean brightness > 225 = overexposed


class NRQualityChecker:
    """Lazy-loaded no-reference quality checker."""

    def __init__(self):
        self._cv_available: bool | None = None
        self._pyiqa_available: bool | None = None

    def _check_cv(self) -> bool:
        if self._cv_available is not None:
            return self._cv_available
        try:
            self._cv_available = True
        except Exception as e:
            self._cv_available = False
            logger.warning(
                "nr_quality: OpenCV not available — fallback quality checks skipped. "
                "Install with: pip install opencv-python-headless",
                error=str(e),
            )
        return self._cv_available

    def _check_pyiqa(self) -> bool:
        if self._pyiqa_available is not None:
            return self._pyiqa_available
        try:
            self._pyiqa_available = True
            logger.info("nr_quality: pyiqa available — will use real BRISQUE/NIQE")
        except Exception:
            self._pyiqa_available = False
        return self._pyiqa_available

    def check_image(self, image_path: str | Path) -> dict[str, Any]:
        """Assess quality of a single image.

        Returns dict with:
            score: 0-1 overall quality score
            blur_ok, contrast_ok, brightness_ok: bool
            details: dict with raw measurements
            method: "pyiqa_brisque" | "opencv_heuristic"
        """
        path = Path(image_path)
        if not path.exists() or path.stat().st_size < 100:
            return {
                "score": 0.0,
                "blur_ok": False,
                "contrast_ok": False,
                "brightness_ok": False,
                "details": {"error": "file not found or too small"},
                "method": "none",
            }

        # Try real BRISQUE first
        if self._check_pyiqa():
            return self._check_pyiqa_brisque(path)

        # Fall back to OpenCV heuristics
        if self._check_cv():
            return self._check_opencv_heuristic(path)

        return {
            "score": 0.5,
            "blur_ok": True,
            "contrast_ok": True,
            "brightness_ok": True,
            "details": {"note": "no quality library available — skipping checks"},
            "method": "skipped",
        }

    def _check_pyiqa_brisque(self, path: Path) -> dict[str, Any]:
        try:
            import pyiqa
            from PIL import Image

            brisque_model = pyiqa.create_metric("brisque", device="cpu")
            img = Image.open(path).convert("RGB")
            # BRISQUE returns lower = better; typical range 0-100
            raw_score = float(brisque_model(img))
            # Normalize: 0 = perfect, 100 = worst → map to 0-1
            score = max(0.0, 1.0 - raw_score / 100.0)
            return {
                "score": round(score, 3),
                "blur_ok": score >= 0.5,
                "contrast_ok": score >= 0.5,
                "brightness_ok": score >= 0.5,
                "details": {"brisque_raw": round(raw_score, 2)},
                "method": "pyiqa_brisque",
            }
        except Exception as e:
            logger.warning("nr_quality: pyiqa BRISQUE failed", error=str(e))
            if self._check_cv():
                return self._check_opencv_heuristic(path)
            return {
                "score": 0.5,
                "blur_ok": True,
                "contrast_ok": True,
                "brightness_ok": True,
                "details": {"error": str(e)},
                "method": "pyiqa_failed",
            }

    def _check_opencv_heuristic(self, path: Path) -> dict[str, Any]:
        import cv2

        try:
            img = cv2.imread(str(path))
            if img is None:
                raise ValueError("cv2.imread returned None")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 1. Blur: Laplacian variance
            lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_ok = lap_var >= BLUR_THRESHOLD

            # 2. Contrast: Michelson contrast
            cmin, cmax = float(gray.min()), float(gray.max())
            contrast = (cmax - cmin) / (cmax + cmin + 1e-6)
            contrast_ok = contrast >= CONTRAST_THRESHOLD

            # 3. Brightness: mean pixel value
            brightness = float(gray.mean())
            brightness_ok = BRIGHTNESS_LOW <= brightness <= BRIGHTNESS_HIGH

            # Overall score: weighted average of 3 checks
            checks = [blur_ok, contrast_ok, brightness_ok]
            score = sum(checks) / len(checks)
            # Adjust based on severity
            if not blur_ok and lap_var < BLUR_THRESHOLD / 2:
                score *= 0.5  # severely blurry
            if not brightness_ok:
                score *= 0.7  # exposure issue

            return {
                "score": round(score, 3),
                "blur_ok": blur_ok,
                "contrast_ok": contrast_ok,
                "brightness_ok": brightness_ok,
                "details": {
                    "laplacian_variance": round(lap_var, 2),
                    "michelson_contrast": round(contrast, 3),
                    "mean_brightness": round(brightness, 1),
                },
                "method": "opencv_heuristic",
            }
        except Exception as e:
            logger.warning("nr_quality: opencv heuristic failed", error=str(e))
            return {
                "score": 0.5,
                "blur_ok": True,
                "contrast_ok": True,
                "brightness_ok": True,
                "details": {"error": str(e)},
                "method": "opencv_failed",
            }

    def check_video(self, video_path: str | Path, sample_count: int = 5) -> dict[str, Any]:
        """Assess quality of a video by sampling frames.

        Extracts `sample_count` evenly-spaced frames and runs check_image on each.
        Returns aggregate statistics.
        """
        import subprocess

        path = Path(video_path)
        if not path.exists() or path.stat().st_size < 1000:
            return {
                "score": 0.0,
                "frames_checked": 0,
                "details": {"error": "file not found or too small"},
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
                "score": 0.5,
                "frames_checked": 0,
                "details": {"error": "duration unmeasurable"},
            }

        import tempfile

        frame_results = []
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
                    r = self.check_image(frame_path)
                    frame_results.append(r)
                frame_path.unlink(missing_ok=True)
            except Exception:
                continue

        if not frame_results:
            return {
                "score": 0.5,
                "frames_checked": 0,
                "details": {"error": "no frames could be extracted"},
            }

        avg_score = sum(r["score"] for r in frame_results) / len(frame_results)
        all_blur_ok = all(r["blur_ok"] for r in frame_results)
        all_contrast_ok = all(r["contrast_ok"] for r in frame_results)
        all_brightness_ok = all(r["brightness_ok"] for r in frame_results)

        return {
            "score": round(avg_score, 3),
            "frames_checked": len(frame_results),
            "blur_ok": all_blur_ok,
            "contrast_ok": all_contrast_ok,
            "brightness_ok": all_brightness_ok,
            "details": {
                "per_frame_scores": [round(r["score"], 3) for r in frame_results],
                "duration": round(duration, 1),
            },
            "method": frame_results[0].get("method", "unknown"),
        }
