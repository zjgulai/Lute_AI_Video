"""Seedance Video Prompt Skill.

Generates Seedance 2.0-compatible prompts from script segments.
Encapsulates best practices from GitHub seedance prompt repos.

Key patterns:
- Product 360 showcase: @image1 [product] as subject, camera ref @video1
- Comparison: @image1 [scene A], @image2 [scene B]
- Timeline segmentation: 0-3s / 3-6s / 6-9s format
- @material_name reference validation
"""

from __future__ import annotations

from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

# Prompt templates for different shot types
SHOT_TEMPLATES = {
    "product_360": (
        "{product_name} shown in a real usage scene, "
        "a parent quickly finds and grabs what they need from organized compartments, "
        "natural warm lighting through car trunk, handheld camera feel, "
        "cinematic short-form video style, authentic family moment"
    ),
    "product_closeup": (
        "close-up of {product_name} in use, hands interacting with the product, "
        "shallow depth of field, soft natural light, "
        "showing texture and quality details in real context"
    ),
    "lifestyle_usage": (
        "@image1 {product_name} in use, "
        "natural lighting, warm atmosphere, "
        "realistic everyday setting, "
        "cinematic 24fps feel"
    ),
    "comparison": (
        "@image1 {product_a} on the left, @image2 {product_b} on the right, "
        "camera pans slowly from left to right, "
        "split-screen comparison, "
        "clean studio setup"
    ),
    "before_after": (
        "@image1 the before state, "
        "camera transitions smoothly to @image2 the after state, "
        "wipe transition effect, "
        "consistent lighting and framing throughout"
    ),
    "brand_story": (
        "Cinematic brand storytelling sequence:\n"
        "0-3s: @image1 establishing shot, warm golden light, slow push-in\n"
        "3-6s: @image2 product detail, gentle camera pan\n"
        "6-9s: @image3 lifestyle scene with natural motion\n"
        "9-12s: @image4 brand moment, slow fade to text overlay\n"
        "No scene cuts throughout, seamless transitions"
    ),
    "influencer_intro": (
        "@image1 {creator_name} looking at camera, friendly expression, "
        "home setting, natural window lighting, "
        "warm and authentic atmosphere"
    ),
    "demo_step": (
        "@image1 {step_description}, "
        "overhead shot, hands visible, "
        "clear and well-lit workspace, informative pacing"
    ),
    "cta_end": (
        "@image1 {product_name} prominently displayed, "
        "text overlay with {cta_text}, "
        "clean minimal background, brand colors"
    ),
}


class SeedancePromptSkill(SkillCallable):
    """Generates Seedance 2.0-compatible video generation prompts.

    Takes script segments and product assets, returns structured 
    prompts with @material_name references that Seedance API understands.
    """

    name = "seedance-video-prompt"
    description = "Generates Seedance 2.0-compatible video prompts from script segments"

    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Build prompt from script segments using templates."""
        segments = params.get("script_segments", [])
        product_name = params.get("product_name", "Product")
        style_refs = params.get("style_ref_images", [])
        product_images = params.get("product_images", [])

        if not segments:
            return SkillResult(success=True, data=self._build_fallback(product_name))

        # Build prompt from segments
        prompt_parts = []
        total_duration = 0

        for i, seg in enumerate(segments):
            seg_type = self._classify_segment(seg, i, len(segments))
            template = SHOT_TEMPLATES.get(seg_type, SHOT_TEMPLATES["product_closeup"])

            # Build focus_detail from visual_description + voiceover for richer scene context
            visual = seg.get("visual_description", "")
            voice = seg.get("voiceover", "")
            focus_detail = (visual + " " + voice)[:120].strip() if visual else voice[:80]
            step_desc = voice[:60] if voice else visual[:60]

            prompt = template.format(
                product_name=product_name,
                focus_detail=focus_detail,
                step_description=step_desc,
                creator_name=params.get("creator_name", ""),
                cta_text=seg.get("cta", "Learn more"),
                product_a=product_name,
                product_b=f"{product_name} alternative",
            )

            # Add timing prefix
            duration = seg.get("duration_seconds", 3)
            start = total_duration
            end = start + duration
            prompt_parts.append(f"[{start}-{end}s] {prompt}")
            total_duration = end

            # Add @material references if available
            if i < len(style_refs):
                prompt_parts[-1] += f" @image{ref_idx} {product_name} reference"

        full_prompt = " ".join(prompt_parts)

        # Add quality spec at the end
        full_prompt += (
            f" Output duration: {total_duration}s total. "
            f"Resolution: 720p. "
            f"Natural motion, smooth transitions, photorealistic quality."
        )

        return SkillResult(success=True, data={
            "seedance_prompt": full_prompt,
            "material_references": {
                "images": style_refs + product_images,
                "count": len(style_refs) + len(product_images),
            },
            "total_duration_seconds": total_duration,
            "prompt_length": len(full_prompt),
        })

    def _classify_segment(self, seg: dict, index: int, total: int) -> str:
        """Classify a script segment into a shot template type."""
        text = (seg.get("voiceover", "") + seg.get("visual_description", "")).lower()

        # First segment = hook/intro → lifestyle scene with product in context
        if index == 0 and total > 1:
            if any(w in text for w in ["review", "unbox", "try"]):
                return "influencer_intro"
            if any(w in text for w in ["compare", "vs", "versus"]):
                return "comparison"
            # Default: show product in real-life usage scene, not sterile rotation
            return "lifestyle_usage"

        # Last segment often is CTA
        if index == total - 1:
            return "cta_end"

        # Middle segments
        if any(w in text for w in ["compare", "vs", "versus", "difference"]):
            return "comparison"
        if any(w in text for w in ["before", "after", "result"]):
            return "before_after"
        if any(w in text for w in ["step", "how to", "first", "next", "then"]):
            return "demo_step"
        if any(w in text for w in ["close up", "detail", "texture", "zoom"]):
            return "product_closeup"
        if any(w in text for w in ["lifestyle", "everyday", "daily", "home", "mom", "dad", "family", "baby", "using", "grab"]):
            return "lifestyle_usage"

        return "product_360"

    def _build_fallback(self, product_name: str) -> dict:
        """Generate a simple fallback prompt."""
        return {
            "seedance_prompt": (
                f"@image1 {product_name} centered on clean background, "
                f"camera slowly orbits around product, "
                f"professional studio lighting, photorealistic, 10s duration"
            ),
            "material_references": {"images": [], "count": 0},
            "total_duration_seconds": 10,
            "prompt_length": 0,
            "_fallback": True,
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("script_segments"):
            errors.append("missing or empty 'script_segments'")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if "seedance_prompt" not in data:
            errors.append("missing 'seedance_prompt' in output")
        elif len(data["seedance_prompt"]) < 10:
            errors.append("seedance_prompt too short (< 10 chars)")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        product_name = params.get("product_name", "Product")
        return SkillResult(success=True, data=self._build_fallback(product_name))


# Auto-register
import structlog
_logger_sd = structlog.get_logger()
try:
    SkillRegistry.register(SeedancePromptSkill())
    _logger_sd.info("seedance_prompt_skill: registered")
except ValueError:
    pass
