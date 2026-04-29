"""Keyframe Images Skill — generates keyframe images from storyboard shots.

For each shot in the storyboard, builds a composition prompt from:
  shot.visual + shot.camera + shot.shot_type + character identity attributes

Then calls GptImageGenerateSkill (via SkillRegistry) for each shot to produce
a keyframe image. Each shot gets a `keyframe_image_path` field added.

Output: storyboard dict with each shot having keyframe_image_path added.
"""

from __future__ import annotations

import structlog
from pathlib import Path
from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


class KeyframeImagesSkill(SkillCallable):
    """Generates keyframe images for storyboard shots using GPT-Image.

    Builds composition prompts from shot visual + camera + shot_type
    enriched with character identity attributes, then calls GPT-Image
    skill for each shot.
    """

    name = "keyframe-images"
    description = "Generates keyframe images from storyboard shots via GPT-Image"
    max_retries = 2

    # Safety cap to prevent runaway API calls for storyboards with many shots
    MAX_SHOTS_PER_STORYBOARD = 10

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        storyboard: dict = params["storyboard"]
        shots: list[dict] = storyboard.get("shots", [])
        identity_card: dict | None = params.get("identity_card")

        # Build identity enrichment string
        identity_text = self._format_identity(identity_card)

        reg = SkillRegistry()

        # Safety cap: process at most MAX_SHOTS_PER_STORYBOARD shots
        capped_shots = shots[:self.MAX_SHOTS_PER_STORYBOARD]
        if len(shots) > self.MAX_SHOTS_PER_STORYBOARD:
            logger.warning("keyframe: capping shots",
                           total=len(shots), cap=self.MAX_SHOTS_PER_STORYBOARD)

        for i, shot in enumerate(capped_shots):
            comp_prompt = self._build_composition_prompt(
                visual=shot.get("visual", ""),
                camera=shot.get("camera", ""),
                shot_type=shot.get("shot_type", ""),
                identity_text=identity_text,
            )

            image_id = f"keyframe_{storyboard.get('script_id', 'sb')}_{i:03d}"

            result = await reg.execute("gpt-image-generate-skill", {
                "prompt": comp_prompt,
                "size": params.get("size", "1024x1792"),
                "quality": params.get("quality", "high"),
                "image_id": image_id,
            })

            if result.success and result.data:
                image_path = result.data.get("image_path", "")
                shot["keyframe_image_path"] = image_path
                shot["keyframe_prompt"] = comp_prompt
                logger.info("keyframe: generated",
                            shot=i, image_path=image_path)
            else:
                # Fallback: use stitch frame placeholder
                fallback_path = self._write_placeholder_frame(
                    shot, image_id, params,
                )
                shot["keyframe_image_path"] = fallback_path
                shot["keyframe_prompt"] = comp_prompt
                logger.warning("keyframe: fallback for shot",
                               shot=i, error=result.error)

        storyboard["keyframes_generated"] = len(capped_shots)
        return SkillResult(success=True, data=storyboard)

    # ── Prompt composition ──

    @staticmethod
    def _build_composition_prompt(
        visual: str,
        camera: str,
        shot_type: str,
        identity_text: str,
    ) -> str:
        """Build a single composition prompt for GPT-Image.

        Combines visual description + camera movement + shot type +
        optional character identity attributes into a coherent image
        generation prompt.
        """
        parts = [visual] if visual else []
        if camera and camera.lower() != "static":
            parts.append(f"Camera: {camera}")
        if shot_type:
            parts.append(f"Shot: {shot_type}")
        if identity_text:
            parts.append(identity_text)
        parts.append("cinematic lighting, professional photography")

        return ", ".join(parts)

    @staticmethod
    def _format_identity(identity_card: dict | None) -> str:
        """Format character identity attributes as a prompt suffix."""
        if not identity_card:
            return ""
        attrs = identity_card.get("attributes", {})
        parts = []
        colors = attrs.get("dominant_colors", [])
        if colors:
            parts.append(f"Color palette: {', '.join(colors[:3])}")
        age = attrs.get("estimated_age_range", "")
        if age:
            parts.append(f"Subject age: {age}")
        return "; ".join(parts)

    # ── Fallback placeholder ──

    @staticmethod
    def _write_placeholder_frame(
        shot: dict,
        image_id: str,
        params: dict,
    ) -> str:
        """Write a placeholder PNG when GPT-Image call fails."""
        from src.config import OUTPUT_DIR

        out_dir = OUTPUT_DIR / "keyframes"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"fallback_{image_id}.png"

        try:
            from PIL import Image

            img = Image.new("RGB", (1024, 1792), color=(60, 60, 80))
            # Simple text indicator isn't possible with PIL alone in a
            # cross-platform way, but the placeholder is visually distinct.
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path)
        except ImportError:
            # PIL not available — write minimal PNG bytes
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x10IDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        return str(path)

    # ── Validation ──

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        sb = params.get("storyboard")
        if not sb:
            errors.append("missing 'storyboard' dict")
        elif "shots" not in sb:
            errors.append("storyboard missing 'shots' list")
        elif not isinstance(sb["shots"], list):
            errors.append("storyboard.shots must be a list")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors: list[str] = []
        if not data:
            return ["output is None"]
        if "shots" not in data:
            errors.append("missing 'shots' in output")
        else:
            for i, shot in enumerate(data["shots"]):
                if "keyframe_image_path" not in shot:
                    errors.append(f"shot[{i}] missing 'keyframe_image_path'")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Return storyboard with placeholder image paths."""
        storyboard: dict = params.get("storyboard") or {"shots": []}
        shots: list[dict] = storyboard.get("shots", [])
        from src.config import OUTPUT_DIR

        # Safety cap to prevent excessive fallback file writes
        capped_shots = shots[:KeyframeImagesSkill.MAX_SHOTS_PER_STORYBOARD]

        for i, shot in enumerate(capped_shots):
            image_id = f"sb_fallback_{i:03d}"
            path = OUTPUT_DIR / "keyframes" / f"fallback_{image_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x10IDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            shot["keyframe_image_path"] = str(path)
            shot["keyframe_prompt"] = shot.get("visual", "")

        storyboard["keyframes_generated"] = len(capped_shots)
        return SkillResult(
            success=True,
            data=storyboard,
        )


# Auto-register
try:
    SkillRegistry.register(KeyframeImagesSkill())
    logger.info("keyframe_images_skill: registered")
except ValueError:
    pass
