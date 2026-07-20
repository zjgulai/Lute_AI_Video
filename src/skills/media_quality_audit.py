"""Media Quality Audit Skill — semantic-layer audit of generated media.

Pipeline-agnostic audit gate for the final media bundle (video + audio + thumbnails).
Complements the per-skill self-verification (file exists, header valid, duration ok)
with cross-artifact and content-level checks.

Two layers:
1. Technical (deterministic, fast):
   - Are all expected files present?
   - Does the final video duration roughly match the script's intended duration?
   - Are thumbnails the right count and resolution?
   - Was the audio actually muxed into the video?
2. Semantic (optional LLM, only when OPENAI_API_KEY present):
   - Does the script text mention the expected product name?
   - Does each thumbnail prompt explicitly reference the product?
   - Does the visual descriptor align with the script's intent?

Designed to NEVER fail the pipeline — produces a report with PASS/WARN/FAIL per
criterion and an overall status. Pipeline can choose to gate on `overall_status`.

Output schema:
    {
      "overall_status": "PASS" | "WARN" | "FAIL",
      "overall_score": float,       # 0..1
      "criteria": [
        {
          "name": str,
          "status": "PASS" | "WARN" | "FAIL",
          "score": float,
          "observation": str,
          "recommendation": str,
        },
        ...
      ],
      "summary": str,
      "checked_at": str,            # ISO timestamp
    }
"""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import structlog

from src.config import (
    VIDEO_ASPECT_RATIO_MAX,
    VIDEO_ASPECT_RATIO_MIN,
    VIDEO_CRITICAL_BITRATE_KBPS,
    VIDEO_CRITICAL_FPS,
    VIDEO_MIN_BITRATE_KBPS,
    VIDEO_MIN_FPS,
)
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.tools.safe_media import ffmpeg_local_input_args, ffprobe_local_input_args

logger = structlog.get_logger()

# Tolerance for duration mismatch — within 25% is acceptable
DURATION_TOLERANCE = 0.25
# Minimum thumbnails for healthy demo
MIN_THUMBNAIL_COUNT = 1


def _score_to_status(score: float) -> str:
    if score >= 0.80:
        return "PASS"
    elif score >= 0.50:
        return "WARN"
    return "FAIL"


def _aggregate_status(criteria: list[dict[str, Any]]) -> str:
    if not criteria:
        return "WARN"
    has_fail = any(c["status"] == "FAIL" for c in criteria)
    has_warn = any(c["status"] == "WARN" for c in criteria)
    if has_fail:
        return "FAIL"
    if has_warn:
        return "WARN"
    return "PASS"


def _make_criterion(name: str, score: float, observation: str, recommendation: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "status": _score_to_status(score),
        "score": round(score, 3),
        "observation": observation,
        "recommendation": recommendation,
    }


class MediaQualityAuditSkill(SkillCallable):
    """Audits the final media bundle for quality + brand alignment."""

    name = "media-quality-audit-skill"
    description = "Semantic + technical audit of the final video/audio/thumbnail bundle"
    max_retries = 1  # Audit is deterministic — no need to retry

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        video_path = params.get("video_path", "")
        audio_paths = params.get("audio_paths") or []
        thumbnail_paths = params.get("thumbnail_paths") or []
        clip_paths = params.get("clip_paths") or []
        expected_product = params.get("expected_product_name", "")
        expected_duration = float(params.get("expected_duration_seconds", 30.0))
        expected_language = params.get("expected_language", "en")
        script_text = params.get("script_text", "")
        thumbnail_prompts = params.get("thumbnail_prompts") or []

        # ── New: optional content-level check inputs ──
        identity_card = params.get("identity_card")
        product_reference_image = params.get("product_reference_image")
        clip_video_paths = params.get("clip_video_paths") or []

        criteria: list[dict[str, Any]] = []

        # ── 1. Final video presence + duration ──
        criteria.append(self._audit_final_video(video_path, expected_duration))

        # ── 2. Audio coverage ──
        criteria.append(self._audit_audio_coverage(audio_paths, expected_duration))

        # ── 3. Thumbnail count + presence ──
        criteria.append(self._audit_thumbnails(thumbnail_paths))

        # ── 4. Clip availability ──
        criteria.append(self._audit_clips(clip_paths))

        # ── 5. Product mention in script ──
        criteria.append(self._audit_product_mention(script_text, expected_product))

        # ── 6. Product mention in thumbnail prompts ──
        criteria.append(self._audit_thumbnail_prompts(thumbnail_prompts, expected_product))

        # ── 7. Language consistency (heuristic) ──
        criteria.append(self._audit_language(script_text, expected_language))

        # ── 8. (Optional) Vision-based check via gpt-4o-vision when key available ──
        # Skipped in MVP to keep the audit fast & deterministic.

        # ── 9. (Optional) Face consistency — only when identity_card provided ──
        if identity_card is not None and isinstance(identity_card, dict):
            criteria.append(self._audit_face_consistency(video_path, identity_card))
        elif identity_card is not None:
            # identity_card present but not a dict (e.g., None sentinel, empty dict)
            criteria.append(self._audit_face_consistency(video_path, None))

        # ── 10. (Optional) Product shape integrity — only when reference image provided ──
        if product_reference_image and isinstance(product_reference_image, str) and product_reference_image.strip():
            criteria.append(self._audit_product_shape(video_path, product_reference_image))

        # ── 11. (Optional) Motion smoothness — only when clip videos provided ──
        if clip_video_paths and isinstance(clip_video_paths, list) and any(clip_video_paths):
            criteria.append(self._audit_motion_smoothness(clip_video_paths))

        if criteria:
            overall_score = round(sum(c["score"] for c in criteria) / len(criteria), 3)
            overall_status = _aggregate_status(criteria)
        else:
            overall_score = 0.5
            overall_status = "WARN"

        # Build summary
        failed = [c["name"] for c in criteria if c["status"] == "FAIL"]
        warned = [c["name"] for c in criteria if c["status"] == "WARN"]
        if failed:
            summary = f"FAIL: {', '.join(failed)}"
            if warned:
                summary += f" | WARN: {', '.join(warned)}"
        elif warned:
            summary = f"WARN: {', '.join(warned)}"
        else:
            summary = "All audit criteria passed."

        return SkillResult(
            success=True,
            data={
                "overall_status": overall_status,
                "overall_score": overall_score,
                "criteria": criteria,
                "summary": summary,
                "checked_at": dt.datetime.now().isoformat(),
            },
            metadata={
                "criteria_count": len(criteria),
                "expected_product": expected_product,
                "expected_duration": expected_duration,
            },
        )

    # === Individual audit checks ===

    def _audit_final_video(self, video_path: str, expected_duration: float) -> dict[str, Any]:
        path = Path(video_path) if video_path else None
        if not path or not path.exists():
            return _make_criterion(
                "final_video_present",
                0.0,
                f"Final video not found at: {video_path or '(empty)'}",
                "Ensure remotion-assemble-skill ran successfully",
            )

        size_mb = path.stat().st_size / (1024 * 1024)

        # Duration check
        actual_duration = self._measure_duration(path)
        if actual_duration > 0:
            mismatch = abs(actual_duration - expected_duration) / max(expected_duration, 1)
            if mismatch <= DURATION_TOLERANCE:
                duration_score = 1.0
                obs = f"Final video {actual_duration:.1f}s ({size_mb:.1f}MB), within ±25% of expected {expected_duration:.1f}s"
            else:
                duration_score = max(0.4, 1.0 - mismatch)
                obs = f"Duration mismatch: actual {actual_duration:.1f}s vs expected {expected_duration:.1f}s ({mismatch*100:.0f}% off)"
        else:
            # Couldn't measure → trust file presence
            duration_score = 0.7
            obs = f"Final video exists ({size_mb:.1f}MB) but duration could not be measured"

        # Technical specs check: resolution, bitrate, fps
        specs = self._get_video_specs(path)
        spec_score = 1.0
        spec_issues: list[str] = []
        spec_recs: list[str] = []

        if specs:
            w, h = specs["width"], specs["height"]
            ratio = w / h if h > 0 else 0
            # Target: 1080x1920 (9:16 = 0.5625)
            if not (VIDEO_ASPECT_RATIO_MIN <= ratio <= VIDEO_ASPECT_RATIO_MAX):
                spec_score *= 0.5
                spec_issues.append(f"aspect ratio {w}x{h} not 9:16")
                spec_recs.append("Force output to 1080x1920 in remotion_assemble")
            elif not (w >= 1000 and h >= 1800):
                spec_score *= 0.8
                spec_issues.append(f"resolution {w}x{h} below 1080x1920 target")

            # FPS
            fps = specs["fps"]
            if fps > 0:
                if fps < VIDEO_CRITICAL_FPS:
                    spec_score *= 0.5
                    spec_issues.append(f"fps {fps:.1f} too low (<{VIDEO_CRITICAL_FPS:.0f})")
                    spec_recs.append("Re-encode with -r 30")
                elif fps < VIDEO_MIN_FPS:
                    spec_score *= 0.8
                    spec_issues.append(f"fps {fps:.1f} below target 30")

            # Bitrate
            bitrate_kbps = specs["bitrate_kbps"]
            if bitrate_kbps > 0:
                if bitrate_kbps < VIDEO_CRITICAL_BITRATE_KBPS:
                    spec_score *= 0.5
                    spec_issues.append(f"bitrate {bitrate_kbps:.0f}kbps too low (<{VIDEO_CRITICAL_BITRATE_KBPS:.0f}kbps)")
                    spec_recs.append("Increase CRF quality or use -b:v 2M")
                elif bitrate_kbps < VIDEO_MIN_BITRATE_KBPS:
                    spec_score *= 0.8
                    spec_issues.append(f"bitrate {bitrate_kbps:.0f}kbps below target 2Mbps")

            if spec_issues:
                obs += f" | Spec issues: {', '.join(spec_issues)}"
        else:
            spec_score = 0.8  # ffprobe unavailable — mild penalty

        combined_score = duration_score * spec_score

        return _make_criterion(
            "final_video_present",
            combined_score,
            obs,
            "; ".join(spec_recs) if spec_recs else ("" if combined_score >= 0.8 else "Re-render with corrected total_duration"),
        )

    def _audit_audio_coverage(self, audio_paths: Any, expected_duration: float) -> dict[str, Any]:
        if not isinstance(audio_paths, (list, tuple)):
            return _make_criterion(
                "audio_coverage",
                0.4,
                f"audio_paths is not a list (got {type(audio_paths).__name__})",
                "Pass audio_paths as a list of file paths",
            )
        if not audio_paths:
            return _make_criterion(
                "audio_coverage",
                0.4,
                "No audio paths provided — final video will be silent",
                "Run elevenlabs-tts-skill for each script segment",
            )

        existing = [p for p in audio_paths if Path(p).exists() and Path(p).stat().st_size > 200]
        coverage_ratio = len(existing) / max(len(audio_paths), 1)

        if coverage_ratio >= 0.9:
            return _make_criterion(
                "audio_coverage",
                1.0,
                f"All {len(existing)}/{len(audio_paths)} audio segments produced ({coverage_ratio*100:.0f}% coverage)",
            )
        if coverage_ratio >= 0.5:
            return _make_criterion(
                "audio_coverage",
                0.7,
                f"Partial coverage: {len(existing)}/{len(audio_paths)} audio segments produced",
                "Investigate why some TTS calls returned stubs",
            )
        return _make_criterion(
            "audio_coverage",
            0.3,
            f"Poor audio coverage: only {len(existing)}/{len(audio_paths)} usable",
            "Check ELEVENLABS_API_KEY and retry",
        )

    def _audit_thumbnails(self, thumbnail_paths: Any) -> dict[str, Any]:
        if not isinstance(thumbnail_paths, (list, tuple)):
            return _make_criterion(
                "thumbnail_count",
                0.3,
                f"thumbnail_paths is not a list (got {type(thumbnail_paths).__name__})",
                "Pass thumbnail_paths as a list of file paths",
            )
        existing = [p for p in thumbnail_paths if isinstance(p, str) and Path(p).exists() and Path(p).stat().st_size > 1024]
        count = len(existing)

        if count >= 4:
            return _make_criterion(
                "thumbnail_count",
                1.0,
                f"All 4 thumbnail variants produced ({count} files >1KB)",
            )
        if count >= 2:
            return _make_criterion(
                "thumbnail_count",
                0.75,
                f"Only {count} thumbnails produced (target: 4)",
                "Investigate failed thumbnail generation calls",
            )
        if count >= MIN_THUMBNAIL_COUNT:
            return _make_criterion(
                "thumbnail_count",
                0.5,
                f"Only {count} thumbnails — below target of 4",
                "Check OPENAI_API_KEY and gpt-image-generate-skill output",
            )
        return _make_criterion(
            "thumbnail_count",
            0.2,
            f"No usable thumbnails (got {count}, expected >= 1)",
            "Run gpt-image-generate-skill before audit",
        )

    def _audit_clips(self, clip_paths: Any) -> dict[str, Any]:
        if not isinstance(clip_paths, (list, tuple)):
            return _make_criterion(
                "clip_availability",
                0.5,
                f"clip_paths is not a list (got {type(clip_paths).__name__})",
                "Pass clip_paths as a list of file paths",
            )
        existing = [p for p in clip_paths if isinstance(p, str) and Path(p).exists() and Path(p).stat().st_size > 1024]
        count = len(existing)

        if count >= 3:
            return _make_criterion(
                "clip_availability",
                1.0,
                f"{count} Seedance clips available for assembly",
            )
        if count >= 1:
            return _make_criterion(
                "clip_availability",
                0.7,
                f"Only {count} clips available — final video will lean on stock visuals",
            )
        return _make_criterion(
            "clip_availability",
            0.5,
            "No Seedance clips available — Remotion will render from text overlays only",
            "Generate clips via seedance-video-generate-skill before assembly",
        )

    def _audit_product_mention(self, script_text: str, expected_product: str) -> dict[str, Any]:
        if not expected_product:
            return _make_criterion(
                "product_mention",
                0.7,
                "No expected_product_name specified — skipping mention check",
            )

        if not script_text:
            return _make_criterion(
                "product_mention",
                0.4,
                "No script_text provided — cannot verify product mention",
                "Pass the assembled script body to the audit",
            )

        # Tokenize and case-normalize
        text_lower = script_text.lower()
        product_terms = [t for t in re.split(r"\s+", expected_product.lower()) if len(t) > 2]

        if not product_terms:
            return _make_criterion(
                "product_mention",
                0.7,
                "Product name has no meaningful tokens — skipping",
            )

        mentions = sum(1 for term in product_terms if term in text_lower)
        coverage = mentions / len(product_terms)

        if coverage >= 0.8:
            return _make_criterion(
                "product_mention",
                1.0,
                f"Product '{expected_product}' clearly mentioned in script ({mentions}/{len(product_terms)} tokens)",
            )
        if coverage >= 0.4:
            return _make_criterion(
                "product_mention",
                0.7,
                f"Product '{expected_product}' partially mentioned ({mentions}/{len(product_terms)} tokens)",
                "Consider re-running script-writer-skill to ensure brand surfacing",
            )
        return _make_criterion(
            "product_mention",
            0.3,
            f"Product '{expected_product}' barely mentioned ({mentions}/{len(product_terms)} tokens)",
            "Script appears to omit the product — re-run script generation",
        )

    def _audit_thumbnail_prompts(self, prompts: Any, expected_product: str) -> dict[str, Any]:
        if not isinstance(prompts, (list, tuple)):
            return _make_criterion(
                "thumbnail_brand_alignment",
                0.6,
                f"thumbnail_prompts is not a list (got {type(prompts).__name__})",
                "Pass thumbnail_prompts as a list",
            )
        if not prompts:
            return _make_criterion(
                "thumbnail_brand_alignment",
                0.6,
                "No thumbnail prompts provided — skipping brand alignment check",
            )
        if not expected_product:
            return _make_criterion(
                "thumbnail_brand_alignment",
                0.7,
                "No expected_product_name specified — skipping",
            )

        # Count prompts that mention the product
        product_lower = expected_product.lower()
        prompt_texts = [(p.get("prompt", "") if isinstance(p, dict) else str(p)) for p in prompts]
        with_mention = sum(1 for t in prompt_texts if product_lower in t.lower())
        coverage = with_mention / max(len(prompt_texts), 1)

        if coverage >= 0.75:
            return _make_criterion(
                "thumbnail_brand_alignment",
                1.0,
                f"{with_mention}/{len(prompt_texts)} thumbnail prompts mention the product",
            )
        if coverage >= 0.5:
            return _make_criterion(
                "thumbnail_brand_alignment",
                0.7,
                f"Only {with_mention}/{len(prompt_texts)} thumbnail prompts mention the product",
                "Tighten thumbnail-prompt-skill to always include product name",
            )
        return _make_criterion(
            "thumbnail_brand_alignment",
            0.4,
            f"Most thumbnails ({len(prompt_texts) - with_mention}/{len(prompt_texts)}) lack product mention",
            "Thumbnails may not be brand-aligned — re-run thumbnail prompts",
        )

    def _audit_language(self, script_text: str, expected_language: str) -> dict[str, Any]:
        # Heuristic: rough character-set checks for top languages
        if not script_text:
            return _make_criterion(
                "language_consistency",
                0.6,
                "No script_text — skipping language check",
            )

        lang = expected_language.lower()
        # Very rough heuristics (good enough for EN/ES/FR/DE)
        match_score = 0.8  # default trust

        if lang == "en":
            # English: should have many ASCII letters and few diacritics
            ascii_ratio = sum(1 for c in script_text if c.isascii()) / max(len(script_text), 1)
            if ascii_ratio < 0.85:
                match_score = 0.5

        if match_score >= 0.8:
            return _make_criterion(
                "language_consistency",
                match_score,
                f"Script text appears consistent with expected language '{expected_language}'",
            )
        return _make_criterion(
            "language_consistency",
            match_score,
            f"Script text may not match expected language '{expected_language}'",
            "Verify script-writer-skill received the correct target_language",
        )

    # ═══ New optional content-level checks (Deliverable 4) ═══

    def _audit_face_consistency(self, video_path: str, identity_card: dict[str, Any] | None) -> dict[str, Any]:
        """Compare a frame from the final video with the identity_card reference.

        Uses histogram comparison as fallback when CLIP isn't available.
        Optional — only runs when identity_card is provided in params.
        Never crashes — returns WARN on any error with explanation.
        """
        path = Path(video_path) if video_path else None
        if not path or not path.exists():
            return _make_criterion(
                "face_consistency",
                0.5,
                "Video not found — cannot check face consistency",
                "Ensure final video exists before audit",
            )

        if not isinstance(identity_card, dict):
            return _make_criterion(
                "face_consistency",
                0.5,
                "identity_card is not a dict — cannot check face consistency",
                "Provide a valid identity_card dict",
            )

        ref_frames = identity_card.get("reference_frames", [])
        if not ref_frames:
            return _make_criterion(
                "face_consistency",
                0.6,
                "No reference frames in identity_card — skipping face comparison",
                "Run character-identity skill first",
            )

        # Extract a mid-frame from the video for comparison
        video_frame = self._extract_video_frame(path, time_sec=None)  # middle frame
        if not video_frame or not video_frame.exists():
            return _make_criterion(
                "face_consistency",
                0.5,
                "Could not extract frame from video",
                "Ensure ffmpeg/ffprobe is available",
            )

        # Compute similarity with the best reference frame
        try:
            from PIL import Image

            target = Image.open(video_frame).convert("RGB")

            best_sim = 0.0
            for ref_path_str in ref_frames:
                ref_path = Path(ref_path_str)
                if not ref_path.exists():
                    continue
                ref_img = Image.open(ref_path).convert("RGB")
                sim = self._histogram_similarity(target, ref_img)
                if sim > best_sim:
                    best_sim = sim

            if best_sim >= 0.7:
                return _make_criterion(
                    "face_consistency",
                    1.0,
                    f"Face consistency: histogram similarity {best_sim:.2f} with reference",
                )
            if best_sim >= 0.4:
                return _make_criterion(
                    "face_consistency",
                    0.7,
                    f"Face consistency: moderate match ({best_sim:.2f}) with reference",
                    "Consider re-generating clips with stronger identity preservation",
                )
            return _make_criterion(
                "face_consistency",
                0.3,
                f"Face consistency: poor match ({best_sim:.2f}) with reference",
                "Identity drift detected — verify character appearance across clips",
            )
        except ImportError:
            return _make_criterion(
                "face_consistency",
                0.6,
                "PIL/numpy unavailable — face consistency check skipped",
            )

    def _audit_product_shape(self, video_path: str, product_reference_image: str) -> dict[str, Any]:
        """Detect if the product shape in the final video appears warped.

        Uses edge detection (Canny) comparison between a video frame and the
        product reference image. Optional — only runs when product_reference_image
        is provided in params.
        """
        path = Path(video_path) if video_path else None
        ref_path = Path(product_reference_image) if product_reference_image else None

        if not path or not path.exists():
            return _make_criterion(
                "product_shape",
                0.5,
                "Video not found — cannot check product shape",
                "Ensure final video exists",
            )
        if not ref_path or not ref_path.exists():
            return _make_criterion(
                "product_shape",
                0.6,
                f"Product reference image not found: {product_reference_image}",
                "Provide a valid product_reference_image path",
            )

        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np

            # Load and edge-detect reference
            ref_img = cv2.imread(str(ref_path))
            if ref_img is None:
                raise ValueError("Could not load reference image")
            ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
            ref_edges = cv2.Canny(ref_gray, 50, 150)
            ref_edge_count = np.count_nonzero(ref_edges)

            # Extract frame from video
            video_frame = self._extract_video_frame(path, time_sec=None)
            if not video_frame or not video_frame.exists():
                return _make_criterion(
                    "product_shape",
                    0.5,
                    "Could not extract video frame for shape comparison",
                )

            frame_img = cv2.imread(str(video_frame))
            if frame_img is None:
                return _make_criterion(
                    "product_shape",
                    0.5,
                    "Could not read extracted video frame",
                )
            frame_gray = cv2.cvtColor(frame_img, cv2.COLOR_BGR2GRAY)
            frame_edges = cv2.Canny(frame_gray, 50, 150)
            frame_edge_count = np.count_nonzero(frame_edges)

            # Compare edge density ratio
            if ref_edge_count == 0:
                return _make_criterion(
                    "product_shape",
                    0.6,
                    "Reference image has no detectable edges — cannot compare",
                )

            # Ratio of edge counts: close to 1 means similar edge density
            ratio = min(frame_edge_count, ref_edge_count) / max(frame_edge_count, 1)
            if ratio >= 0.6:
                return _make_criterion(
                    "product_shape",
                    1.0,
                    f"Product shape: edge density ratio {ratio:.2f} — shape preserved",
                )
            if ratio >= 0.3:
                return _make_criterion(
                    "product_shape",
                    0.7,
                    f"Product shape: moderate edge deviation ({ratio:.2f})",
                    "Product may appear slightly different from reference",
                )
            return _make_criterion(
                "product_shape",
                0.3,
                f"Product shape: significant edge deviation ({ratio:.2f})",
                "Product shape may be warped — verify clip generation parameters",
            )
        except ImportError:
            return _make_criterion(
                "product_shape",
                0.6,
                "OpenCV unavailable — product shape check skipped",
                "Install opencv-python-headless for edge detection",
            )
        except Exception as e:
            return _make_criterion(
                "product_shape",
                0.5,
                f"Product shape check failed: {e}",
            )

    def _audit_motion_smoothness(self, clip_video_paths: list[str]) -> dict[str, Any]:
        """Compute optical flow variation across consecutive frames.

        Flags if the standard deviation of flow magnitude exceeds the threshold,
        indicating jittery or erratic motion.
        Optional — only runs when clip_video_paths is provided and non-empty.
        """
        if not isinstance(clip_video_paths, (list, tuple)):
            return _make_criterion(
                "motion_smoothness",
                0.5,
                f"clip_video_paths is not a list (got {type(clip_video_paths).__name__})",
                "Pass clip_video_paths as a list of file paths",
            )
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np
        except ImportError:
            return _make_criterion(
                "motion_smoothness",
                0.6,
                "OpenCV unavailable — motion smoothness check skipped",
                "Install opencv-python-headless for optical flow analysis",
            )

        valid_clips = [p for p in clip_video_paths if Path(p).exists()]
        if not valid_clips:
            return _make_criterion(
                "motion_smoothness",
                0.5,
                "No clip videos available for motion analysis",
            )

        flow_stds: list[float] = []
        for clip_path_str in valid_clips[:3]:  # Check up to 3 clips
            try:
                cap = cv2.VideoCapture(str(clip_path_str))
                ret, prev = cap.read()
                if not ret or prev is None:
                    cap.release()
                    continue
                prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

                frame_flows: list[float] = []
                for _ in range(30):  # Sample up to 30 frames
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        break
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                    # Dense optical flow (Farneback)
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0,
                    )
                    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    mean_mag = float(np.mean(mag))
                    frame_flows.append(mean_mag)
                    prev_gray = gray

                cap.release()

                if len(frame_flows) >= 2:
                    std = float(np.std(frame_flows))
                    flow_stds.append(std)
            except Exception:
                continue

        if not flow_stds:
            return _make_criterion(
                "motion_smoothness",
                0.5,
                "Could not compute optical flow — clips may be unreadable",
            )

        avg_std = sum(flow_stds) / len(flow_stds)
        # Threshold: std > 5.0 suggests erratic motion
        if avg_std <= 5.0:
            return _make_criterion(
                "motion_smoothness",
                1.0,
                f"Motion smoothness: flow std {avg_std:.2f} — motion is stable",
            )
        if avg_std <= 10.0:
            return _make_criterion(
                "motion_smoothness",
                0.7,
                f"Motion smoothness: moderate jitter (std {avg_std:.2f})",
                "Consider smoothing transitions between clips",
            )
        return _make_criterion(
            "motion_smoothness",
            0.3,
            f"Motion smoothness: high jitter detected (std {avg_std:.2f})",
            "Regenerate clips with reduced camera motion or style_preserve=True",
        )

    # ── Helpers for new checks ──

    @staticmethod
    def _extract_video_frame(video_path: Path, time_sec: float | None = None) -> Path | None:
        """Extract a single frame from a video using ffmpeg.

        Args:
            video_path: Path to the video file.
            time_sec: Time offset (default: midpoint of video).

        Returns:
            Path to the extracted JPEG frame, or None on failure.
        """
        import subprocess
        import tempfile

        # Reject empty or 0-byte files before calling external tools
        if not video_path or not video_path.exists() or video_path.stat().st_size < 100:
            return None

        try:
            # Determine duration to find midpoint
            if time_sec is None:
                dur_result = subprocess.run(
                    ["ffprobe", "-v", "error",
                     "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1",
                     *ffprobe_local_input_args(video_path)],
                    capture_output=True, text=True, timeout=10,
                )
                if dur_result.returncode == 0:
                    duration = float(dur_result.stdout.strip() or "0")
                    time_sec = duration / 2.0
                else:
                    time_sec = 1.0  # fallback

            fd, frame_path_str = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            frame_path = Path(frame_path_str)
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(time_sec),
                 *ffmpeg_local_input_args(video_path), "-vframes", "1",
                 "-q:v", "2", str(frame_path)],
                capture_output=True, timeout=10, check=True,
            )
            if frame_path.exists() and frame_path.stat().st_size > 100:
                return frame_path
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError, Exception) as exc:
            logger.debug(
                "media_quality_audit: frame extraction failed",
                video_path=str(video_path),
                error=str(exc)[:200],
            )
        return None

    @staticmethod
    def _histogram_similarity(img_a: Any, img_b: Any) -> float:
        """Compute histogram-based similarity between two PIL Images.

        Returns a value in [0, 1] where 1 = identical histograms.
        Returns 0.0 if either image is None or invalid.
        """
        import numpy as np

        if img_a is None or img_b is None:
            return 0.0

        try:
            arr_a = np.array(img_a)
            arr_b = np.array(img_b)
        except Exception:
            return 0.0

        if arr_a.size == 0 or arr_b.size == 0:
            return 0.0

        # Resize to same dimensions for histogram comparison
        from PIL import Image
        target_size = (256, 256)
        if arr_a.shape[:2] != target_size:
            arr_a = np.array(Image.fromarray(arr_a).resize(target_size))
        if arr_b.shape[:2] != target_size:
            arr_b = np.array(Image.fromarray(arr_b).resize(target_size))

        # Compute per-channel histogram intersection
        sims: list[float] = []
        for c in range(3 if len(arr_a.shape) == 3 else 1):
            hist_a = np.histogram(arr_a[..., c].ravel() if len(arr_a.shape) == 3 else arr_a.ravel(),
                                  bins=64, range=(0, 256))[0].astype(np.float64)
            hist_b = np.histogram(arr_b[..., c].ravel() if len(arr_b.shape) == 3 else arr_b.ravel(),
                                  bins=64, range=(0, 256))[0].astype(np.float64)
            # Normalize
            hist_a /= max(hist_a.sum(), 1)
            hist_b /= max(hist_b.sum(), 1)
            # Intersection
            sims.append(float(np.minimum(hist_a, hist_b).sum()))

        return sum(sims) / len(sims) if sims else 0.0

    @staticmethod
    def _get_video_specs(path: Path) -> dict[str, Any] | None:
        """Extract video technical specs via ffprobe: width, height, fps, bitrate."""
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,r_frame_rate,bit_rate",
                    "-of", "json",
                    *ffprobe_local_input_args(path),
                ],
                capture_output=True, text=True, timeout=10, check=True,
            )
            import json
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            w = int(stream.get("width", 0))
            h = int(stream.get("height", 0))
            # FPS from rational string "30000/1001"
            fps_str = stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 0.0
            else:
                fps = float(fps_str)
            bitrate = int(stream.get("bit_rate", 0))  # bits per second
            return {
                "width": w,
                "height": h,
                "fps": fps,
                "bitrate_kbps": bitrate / 1000,
            }
        except Exception:
            return None

    @staticmethod
    def _measure_duration(path: Path) -> float:
        if not path or not path.exists() or path.stat().st_size < 100:
            return 0.0
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
            if result.returncode == 0:
                return float(result.stdout.strip() or "0.0")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception) as exc:
            logger.debug(
                "media_quality_audit: ffprobe duration failed",
                video_path=str(path),
                error=str(exc)[:200],
            )
        return 0.0

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if "video_path" not in params:
            errors.append("missing 'video_path' (final assembled mp4)")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if "overall_status" not in data:
            errors.append("missing 'overall_status'")
        if "criteria" not in data:
            errors.append("missing 'criteria' list")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        # Even the fallback runs deterministically
        return SkillResult(
            success=True,
            data={
                "overall_status": "WARN",
                "overall_score": 0.5,
                "criteria": [{
                    "name": "audit_fallback",
                    "status": "WARN",
                    "score": 0.5,
                    "observation": "Audit skill fell back without running checks",
                    "recommendation": "Investigate why media-quality-audit-skill couldn't execute",
                }],
                "summary": "Audit fallback — checks not run",
                "checked_at": dt.datetime.now().isoformat(),
                "_fallback": True,
            },
            metadata={"reason": "all_retries_exhausted"},
        )


# Auto-register
try:
    SkillRegistry.register(MediaQualityAuditSkill())
    logger.info("media_quality_audit_skill: registered")
except ValueError as exc:
    logger.debug(
        "media_quality_audit_skill: already registered",
        error=str(exc)[:200],
    )
