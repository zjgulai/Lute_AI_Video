"""Keyframe Images Skill — generates keyframe images from storyboard shots.

For each shot in the storyboard, builds a composition prompt from:
  shot.visual + shot.camera + shot.shot_type + character identity attributes

Then calls GptImageGenerateSkill (via SkillRegistry) for each shot to produce
a keyframe image. Each shot gets a `keyframe_image_path` field added.

Output: storyboard dict with each shot having keyframe_image_path added.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.pipeline.feedback_gate import evaluate_upstream_quality
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
        storyboard: dict[str, Any] = params["storyboard"]
        output_dir = params.get("output_dir")
        provider_max_retries = params.get("provider_max_retries")

        gate_attempt = int(params.get("_quality_attempt", 0))
        gate_decision, gate_score, gate_reason = evaluate_upstream_quality(
            upstream_data=storyboard,
            consumer="keyframe_images",
            attempt=gate_attempt,
        )
        if gate_decision == "regenerate":
            logger.info(
                "keyframe: feedback_gate regenerate",
                score=gate_score,
                attempt=gate_attempt,
                reason=gate_reason,
            )
            return SkillResult(
                success=False,
                data={
                    "regenerate_upstream": "storyboard",
                    "reason": gate_reason,
                    "score": gate_score,
                    "consumer": "keyframe_images",
                    "attempt": gate_attempt,
                },
                error=gate_reason,
                metadata={
                    "regenerate_upstream": "storyboard",
                    "feedback_gate_score": gate_score,
                    "feedback_gate_attempt": gate_attempt,
                },
            )
        if gate_decision == "warn":
            params["_quality_warning"] = gate_reason
            logger.warning(
                "keyframe: feedback_gate warn",
                score=gate_score,
                reason=gate_reason,
            )

        shots: list[dict[str, Any]] = storyboard.get("shots", [])
        identity_card: dict[str, Any] | None = params.get("identity_card")

        # Build identity enrichment string
        identity_text = self._format_identity(identity_card)

        reg = SkillRegistry()

        # Safety cap: process at most MAX_SHOTS_PER_STORYBOARD shots
        # P2-1: Allow caller to override cap when clips count is known upfront
        cap = self._resolve_shot_cap(params)
        capped_shots = shots[:cap]
        if len(shots) > cap:
            logger.warning("keyframe: capping shots",
                           total=len(shots), cap=cap)

        import asyncio

        async def _gen_one(
            i: int, shot: dict[str, Any]
        ) -> tuple[int, str, str, bool | None]:
            comp_prompt = self._build_composition_prompt(
                visual=shot.get("visual", ""),
                camera=shot.get("camera", ""),
                shot_type=shot.get("shot_type", ""),
                identity_text=identity_text,
            )
            image_id = f"keyframe_{storyboard.get('script_id', 'sb')}_{i:03d}"
            generate_params: dict[str, Any] = {
                "prompt": comp_prompt,
                "size": params.get("size", "1024x1792"),
                "quality": params.get("quality", "high"),
                "image_id": image_id,
            }
            if output_dir:
                generate_params["output_dir"] = output_dir
            if provider_max_retries is not None:
                generate_params["provider_max_retries"] = provider_max_retries
            result = await reg.execute("gpt-image-generate-skill", generate_params)
            if result.success and result.data:
                image_path = result.data.get("image_path", "")
                logger.info("keyframe: generated", shot=i, image_path=image_path)
                simulated = result.data.get("simulated")
                return (
                    i,
                    image_path,
                    comp_prompt,
                    simulated if type(simulated) is bool else None,
                )
            # Fallback
            fallback_path = self._write_placeholder_frame(shot, image_id, params)
            logger.warning("keyframe: fallback for shot", shot=i, error=result.error)
            return i, fallback_path, comp_prompt, True

        tasks = [_gen_one(i, shot) for i, shot in enumerate(capped_shots)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        simulation_truth: list[bool | None] = []
        for raw in results:
            if isinstance(raw, Exception):
                logger.error("keyframe: generation exception", error=str(raw))
                continue
            if not isinstance(raw, tuple):
                continue
            i, image_path, comp_prompt, simulated = raw
            capped_shots[i]["keyframe_image_path"] = image_path
            capped_shots[i]["keyframe_prompt"] = comp_prompt
            if simulated is not None:
                capped_shots[i]["simulated"] = simulated
            simulation_truth.append(simulated)

        storyboard["shots"] = capped_shots
        storyboard["keyframes_generated"] = len(capped_shots)
        if simulation_truth and all(value is not None for value in simulation_truth):
            storyboard["simulated"] = any(value is True for value in simulation_truth)
        if params.get("_quality_warning"):
            storyboard["_quality_warning"] = params["_quality_warning"]
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
    def _format_identity(identity_card: dict[str, Any] | None) -> str:
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

    @classmethod
    def _resolve_shot_cap(cls, params: dict[str, Any]) -> int:
        raw_cap = params.get("_max_shots", cls.MAX_SHOTS_PER_STORYBOARD)
        try:
            return max(0, int(raw_cap))
        except (TypeError, ValueError):
            return cls.MAX_SHOTS_PER_STORYBOARD

    # ── Fallback placeholder ──

    @staticmethod
    def _write_placeholder_frame(
        shot: dict[str, Any],
        image_id: str,
        params: dict[str, Any],
    ) -> str:
        """Write a placeholder PNG when GPT-Image call fails."""
        output_dir = params.get("output_dir")
        if output_dir:
            out_dir = Path(output_dir)
        else:
            from src.config import OUTPUT_DIR
            out_dir = OUTPUT_DIR / "keyframes"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"fallback_{image_id}.png"

        try:
            from PIL import Image

            img = Image.new("RGB", (1024, 1792), color=(60, 60, 80))  # type: ignore[arg-type]
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
        if sb is None:
            errors.append("missing 'storyboard' dict")
        elif not isinstance(sb, dict):
            errors.append("storyboard must be a dict")
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
        storyboard: dict[str, Any] = params.get("storyboard") or {"shots": []}
        shots: list[dict[str, Any]] = storyboard.get("shots", [])
        output_dir = params.get("output_dir")
        if output_dir:
            out_dir = Path(output_dir)
        else:
            from src.config import OUTPUT_DIR
            out_dir = OUTPUT_DIR / "keyframes"

        # Safety cap to prevent excessive fallback file writes
        cap = KeyframeImagesSkill._resolve_shot_cap(params)
        capped_shots = shots[:cap]

        for i, shot in enumerate(capped_shots):
            image_id = f"sb_fallback_{i:03d}"
            path = out_dir / f"fallback_{image_id}.png"
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
            shot["simulated"] = True

        storyboard["shots"] = capped_shots
        storyboard["keyframes_generated"] = len(capped_shots)
        storyboard["simulated"] = True
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
