"""Character Identity Skill — extracts character identity from video frames.

Takes a list of video frame image paths, runs face detection / sharpness
analysis, and selects the top-3 best-quality frames as character references.

Output schema:
    {
      "reference_frames": ["path/to/best_face_1.jpg", ...],
      "attributes": {
        "face_count": 1,
        "face_quality_score": 0.85,
        "dominant_colors": ["#E8C9A0", "#4A3728"],
        "estimated_age_range": "25-35"
      }
    }
"""

from __future__ import annotations

import structlog
from pathlib import Path
from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


class CharacterIdentitySkill(SkillCallable):
    """Extracts character identity attributes from video frame images.

    Uses OpenCV cascade face detection if available; falls back to
    PIL-based sharpness heuristic when cv2 is not installed.
    """

    name = "character-identity"
    description = "Detects faces in video frames and selects best-quality reference images"
    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        frame_paths: list[str] = params["frame_paths"]

        # Attempt to use OpenCV for face detection
        has_cv2, _cv2, _cascade = self._try_load_cv2()

        scored_frames: list[tuple[float, str, dict[str, Any]]] = []

        for fp in frame_paths:
            path = Path(fp)
            if not path.exists():
                continue

            score = 0.0
            face_info: dict[str, Any] = {}

            if has_cv2:
                score, face_info = self._score_with_opencv(path, _cv2, _cascade)
            else:
                score, face_info = self._score_with_pil(path)

            scored_frames.append((score, str(path), face_info))

        # Sort descending by score
        scored_frames.sort(key=lambda x: x[0], reverse=True)

        top_frames = scored_frames[:3]
        reference_frames = [item[1] for item in top_frames]

        # Compute aggregate attributes
        if top_frames:
            avg_score = sum(item[0] for item in top_frames) / len(top_frames)
            face_count = max(item[2].get("face_count", 0) for item in top_frames)
            best_frame_path = Path(top_frames[0][1])
        else:
            avg_score = 0.0
            face_count = 0
            best_frame_path = None
        dominant_colors = self._extract_dominant_colors(best_frame_path)

        return SkillResult(
            success=True,
            data={
                "reference_frames": reference_frames,
                "attributes": {
                    "face_count": max(face_count, 1) if top_frames else 0,
                    "face_quality_score": round(avg_score, 3),
                    "dominant_colors": dominant_colors,
                    "estimated_age_range": "25-35",  # constant; no ML model available
                },
            },
        )

    # ── OpenCV-based scoring ──

    @staticmethod
    def _try_load_cv2() -> tuple[bool, Any, Any]:
        """Try to load OpenCV and a face cascade classifier."""
        try:
            import cv2  # type: ignore[import-not-found]
            # Use the default frontal face cascade
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
            if cascade.empty():
                logger.warning("character_identity: OpenCV cascade empty — falling back to PIL")
                return False, None, None
            return True, cv2, cascade
        except (ImportError, AttributeError, Exception):
            logger.info("character_identity: OpenCV unavailable — using PIL heuristic")
            return False, None, None

    @staticmethod
    def _score_with_opencv(
        path: Path,
        cv2: Any,
        cascade: Any,
    ) -> tuple[float, dict[str, Any]]:
        """Score a frame using OpenCV face detection + Laplacian sharpness.

        Downsamples large images (>2048px dimension) before processing
        to avoid OOM and keep face detection fast.
        """
        img = cv2.imread(str(path))
        if img is None:
            return 0.0, {"face_count": 0, "sharpness": 0.0}

        # Downsample if image is very large to prevent OOM
        h, w = img.shape[:2]
        max_dim = 2048
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            h, w = new_h, new_w

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Detect faces
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30),
        )

        face_count = len(faces)

        # Sharpness via Laplacian variance
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(lap_var / 500.0, 1.0)  # Normalize: 500 is "good"

        if face_count == 0:
            return round(sharpness_score * 0.5, 4), {
                "face_count": 0, "sharpness": round(lap_var, 2),
            }

        # Face size ratio (largest face)
        max_face_ratio = 0.0
        for (x, y, fw, fh) in faces:
            ratio = (fw * fh) / (w * h)
            if ratio > max_face_ratio:
                max_face_ratio = ratio
        face_size_score = min(max_face_ratio / 0.15, 1.0)  # 15% of frame = ideal

        # Combined: sharpness (40%) + face size (40%) + face presence (20%)
        combined = 0.4 * sharpness_score + 0.4 * face_size_score + 0.2 * min(face_count / 3, 1.0)

        return round(combined, 4), {
            "face_count": face_count,
            "sharpness": round(lap_var, 2),
            "max_face_ratio": round(max_face_ratio, 4),
        }

    # ── PIL-only fallback scoring ──

    @staticmethod
    def _score_with_pil(path: Path) -> tuple[float, dict[str, Any]]:
        """Score frame sharpness using PIL (no face detection).

        Downsamples large images (>2048px dimension) before processing
        to avoid OOM on large keyframe images.
        """
        try:
            from PIL import Image, ImageFilter
            import numpy as np

            img = Image.open(path).convert("L")
            # Downsample if image is very large to prevent OOM
            max_dim = 2048
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)  # type: ignore[attr-defined]
            # Laplacian-like edge detection: max-min in 3x3 neighborhood
            edges = img.filter(ImageFilter.Kernel((3, 3), [
                -1, -1, -1,
                -1,  8, -1,
                -1, -1, -1,
            ], scale=1))
            arr = np.array(edges, dtype=np.float64)
            variance = arr.var()
            sharpness = min(variance / 300.0, 1.0)
            return round(sharpness, 4), {"face_count": 0, "sharpness": round(variance, 2)}
        except ImportError:
            # numpy or PIL not available — can't score
            return 0.5, {"face_count": 0, "sharpness": 0.0}
        except Exception:
            # PIL filter or other processing failure — return default score
            return 0.5, {"face_count": 0, "sharpness": 0.0}

    # ── Dominant color extraction ──

    @staticmethod
    def _extract_dominant_colors(path: Path | None, n_colors: int = 5) -> list[str]:
        """Extract dominant colors from an image using simple k-means.

        Falls back to a default palette if the image can't be loaded.
        """
        if not path or not path.exists():
            return ["#E8C9A0", "#4A3728", "#F5F5F5", "#2C2C2C", "#8B7355"]

        try:
            from PIL import Image
            import numpy as np

            img = Image.open(path).convert("RGB")
            img = img.resize((64, 64))  # Downsample for speed
            arr = np.array(img).reshape(-1, 3)

            # Simple k-means with sklearn if available
            try:
                from sklearn.cluster import KMeans  # type: ignore[import-not-found]
                kmeans = KMeans(n_clusters=n_colors, random_state=0, n_init="auto")
                kmeans.fit(arr.astype(np.float64))
                colors = kmeans.cluster_centers_.astype(np.uint8)
            except ImportError:
                # Fallback: uniform grid sampling
                step = max(1, len(arr) // n_colors)
                colors = arr[::step][:n_colors]

            hex_colors = []
            for c in colors[:n_colors]:
                hex_colors.append(f"#{c[0]:02X}{c[1]:02X}{c[2]:02X}")
            return hex_colors
        except Exception:
            return ["#E8C9A0", "#4A3728", "#F5F5F5", "#2C2C2C", "#8B7355"]

    # ── Validation ──

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        frame_paths = params.get("frame_paths")
        if not frame_paths:
            errors.append("missing 'frame_paths' (list[str])")
        elif not isinstance(frame_paths, list):
            errors.append("'frame_paths' must be a list")
        elif len(frame_paths) == 0:
            errors.append("'frame_paths' list is empty")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors: list[str] = []
        if not data:
            return ["output is None"]
        if "reference_frames" not in data:
            errors.append("missing 'reference_frames'")
        if "attributes" not in data:
            errors.append("missing 'attributes'")
        if "attributes" in data:
            if "face_count" not in data["attributes"]:
                errors.append("missing 'attributes.face_count'")
            if "face_quality_score" not in data["attributes"]:
                errors.append("missing 'attributes.face_quality_score'")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Deterministic fallback — return a minimal identity card."""
        from src.config import OUTPUT_DIR

        out_dir = OUTPUT_DIR / "character_identity"
        out_dir.mkdir(parents=True, exist_ok=True)

        frame_paths: list[str] = params.get("frame_paths", [])
        ref_frames = [p for p in frame_paths[:3] if Path(p).exists()]

        return SkillResult(
            success=True,
            data={
                "reference_frames": ref_frames,
                "attributes": {
                    "face_count": 1,
                    "face_quality_score": 0.5,
                    "dominant_colors": ["#E8C9A0", "#4A3728"],
                    "estimated_age_range": "25-35",
                },
                "_fallback": True,
            },
        )


# Auto-register
try:
    SkillRegistry.register(CharacterIdentitySkill())
    logger.info("character_identity_skill: registered")
except ValueError:
    pass
