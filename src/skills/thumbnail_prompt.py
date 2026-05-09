"""GPT Image Thumbnail Prompt Skill.

Generates gpt-image-2 compatible thumbnail prompts from script hooks.
Encapsulates best practices from GitHub gpt4o-images repo (7.9k stars):
- Product-centered + bold text + price tag (ecom style)
- Lifestyle scene + before/after split (emotional)
- Close-up emotion + problem text (reaction)
- Minimal product + single hook line (minimal)

Supports brand color/font injection and platform-specific aspect ratios.
"""

from __future__ import annotations

from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

# 4 thumbnail concept templates derived from top e-com prompts
THUMBNAIL_CONCEPTS = {
    "A": {
        "style": "clean_ecom",
        "template": (
            "Professional product photography style. "
            + "{product_name} prominently centered on clean white background. "
            + "Bold text overlay in {brand_color} reading: "
            + chr(34) + "{hook_text}" + chr(34) + ". "
            + "Price tag {price} displayed bottom-right. "
            + "High-end e-commerce product shot, studio lighting, crisp focus."
        ),
    },
    "B": {
        "style": "lifestyle_emotional",
        "template": (
            "Lifestyle photography, warm natural light. "
            + "{product_name} shown in use in a real home setting. "
            + "Split-scene: before on left (problem) and after on right (solution). "
            + "Empathetic, warm mood, relatable everyday moment. "
            + "Text: " + chr(34) + "{hook_text}" + chr(34) + " in soft serif font."
        ),
    },
    "C": {
        "style": "reaction",
        "template": (
            "Close-up shot showing genuine surprise/delight reaction. "
            + "{product_name} held in hands, slightly out of focus in foreground. "
            + "Facial expression of pleasant surprise, genuine emotion. "
            + "Bold attention-grabbing text: " + chr(34) + "{hook_text}" + chr(34) + " in yellow/white contrast. "
            + "High contrast, punchy colors, scroll-stopping composition."
        ),
    },
    "D": {
        "style": "minimal_hook",
        "template": (
            "Minimalist composition. Single {product_name} shot from low angle. "
            + "Dramatic lighting, dark background with rim light on product. "
            + "One line of text only: " + chr(34) + "{hook_text}" + chr(34) + " in thin white font at top. "
            + "Clean, premium, Apple-style product photography. "
            + "High-end minimal aesthetic."
        ),
    },
}

PLATFORM_SIZES = {
    "tiktok": "1024x1792",
    "youtube_shorts": "1024x1792",
    "shopify": "1536x1024",
    "amazon": "1536x1024",
    "facebook": "1536x1024",
    "reddit": "1024x1024",
}


class ThumbnailPromptSkill(SkillCallable):
    """Generates gpt-image-2 compatible thumbnail prompts.

    Produces 4 variant prompts (A/B/C/D) covering different styles.
    Injects brand colors, product info, and hook text.
    Platform-specific aspect ratios.
    """

    name = "gpt-image-thumbnail-prompt"
    description = "Generates gpt-image-2 thumbnail prompts from script hooks"

    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Generate 4 thumbnail variant prompts."""
        hook_text = params.get("hook_text", "")
        product_name = params.get("product_name", "Product")
        brand_color = params.get("brand_color", "#000000")
        price = params.get("price", "")
        platform = params.get("platform", "tiktok")

        # Truncate hook text for thumbnail readability
        hook_short = hook_text[:60] if hook_text else "Discover the difference"

        variants = []
        for vid, concept in THUMBNAIL_CONCEPTS.items():
            prompt = concept["template"].format(
                product_name=product_name,
                hook_text=hook_short,
                brand_color=brand_color,
                price=f"${price:.2f}" if isinstance(price, (int, float)) else str(price),
            )
            variants.append({
                "variant_id": vid,
                "style": concept["style"],
                "prompt": prompt,
                "size": PLATFORM_SIZES.get(platform, "1024x1792"),
            })

        return SkillResult(success=True, data={
            "variants": variants,
            "platform": platform,
            "product_name": product_name,
            "recommended_quality": "high",
        })

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("hook_text") and not params.get("product_name"):
            errors.append("either 'hook_text' or 'product_name' required")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        variants = data.get("variants", [])
        if len(variants) != 4:
            errors.append(f"expected 4 variants, got {len(variants)}")
        for v in variants:
            if "prompt" not in v:
                errors.append("variant missing 'prompt'")
                break
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Return minimal fallback thumbnail prompts."""
        hook = params.get("hook_text", "Product")[:40]
        name = params.get("product_name", "Product")
        fallback_variants = [
            {"variant_id": "A", "style": "clean_ecom",
             "prompt": f"{name} on white background. Text: " + chr(34) + hook + chr(34),
             "size": "1024x1792"},
            {"variant_id": "B", "style": "lifestyle",
             "prompt": f"{name} in lifestyle setting. " + chr(34) + hook + chr(34),
             "size": "1024x1792"},
        ]
        return SkillResult(success=True, data={
            "variants": fallback_variants,
            "platform": params.get("platform", "tiktok"),
            "product_name": name,
            "recommended_quality": "medium",
            "_fallback": True,
        })


# Auto-register
import structlog

_logger_tp = structlog.get_logger()
try:
    SkillRegistry.register(ThumbnailPromptSkill())
except ValueError:
    pass
