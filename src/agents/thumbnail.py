"""Thumbnail Agent — generates 4 thumbnail variant images.

Uses DALL-E 3 for real image generation.
Falls back to stub when API key is absent.

Feature propagation from CaptionAgent: caption_plans carry style signals
(highlight/cta styled entries, key text phrases) that inform what visual
emphasis the thumbnail should carry. Without this, thumbnails only know
the script hook — they miss which words actually got highlighted.
"""

from typing import Any

import structlog

from src.models import CaptionPlan, Script, ThumbnailSet, ThumbnailVariant
from src.tools.dalle_client import DalleClient

logger = structlog.get_logger()

THUMBNAIL_CONCEPTS = {
    "A": {"concept": "Product centered + bold title + price tag", "style": "clean_ecom"},
    "B": {"concept": "Lifestyle scene + before/after split", "style": "emotional"},
    "C": {"concept": "Close-up face expression + problem text", "style": "reaction"},
    "D": {"concept": "Minimal product shot + single hook line", "style": "minimal"},
}


def _propagate_caption_signals(caption_plans: list[CaptionPlan], target_script_id: str) -> dict[str, Any]:
    """Extract caption-level visual signals for a specific script.

    Returns a dict with keywords and emphasis directions that a thumbnail
    prompt can use to make its visual more aligned with the captions.

    Signals extracted:
    - highlight_texts: entries with style='highlight' (the words that pop up)
    - cta_texts: entries with style='cta' (call to action moments)
    - has_visual_emphasis: True if highlights exist
    - key_phrases: deduplicated meaningful caption text fragments
    """
    signals: dict[str, Any] = {
        "highlight_texts": [],
        "cta_texts": [],
        "has_visual_emphasis": False,
        "key_phrases": [],
    }

    for plan in caption_plans:
        if plan.script_id != target_script_id:
            continue
        seen = set()
        for entry in plan.entries:
            if entry.style == "highlight" and entry.text.strip():
                signals["highlight_texts"].append(entry.text.strip())
                signals["has_visual_emphasis"] = True
            if entry.style == "cta" and entry.text.strip():
                signals["cta_texts"].append(entry.text.strip())
            # Collect shorter key phrases (avoid noise from long captions)
            text = entry.text.strip()
            if 3 <= len(text) <= 80 and text not in seen:
                seen.add(text)
                signals["key_phrases"].append(text)

        # Cap lists to avoid overflowing prompt
        signals["highlight_texts"] = signals["highlight_texts"][:3]
        signals["cta_texts"] = signals["cta_texts"][:2]
        signals["key_phrases"] = signals["key_phrases"][:5]
        break  # Only the matching plan

    return signals


class ThumbnailAgent:
    """Generates thumbnail variants — concepts + actual images via DALL-E.

    Accepts optional caption_plans to propagate visual emphasis signals
    from the caption layer into thumbnail generation prompts.
    """

    def __init__(self, use_mock: bool = False, dalle_api_key: str | None = None, quality_level: str = "perfect", use_skills: bool = False):
        self.use_mock = use_mock
        self.dalle = DalleClient(api_key=dalle_api_key)
        self.use_skills = use_skills
        self.quality_level = quality_level

    async def run(
        self,
        scripts: list[Script],
        caption_plans: list[CaptionPlan] | None = None,
    ) -> list[ThumbnailSet]:
        # Mock mode: use degrade_thumbnails for deterministic test data
        # (skips DALL-E calls, no caption propagation, fixed prompts)
        if self.use_mock:
            from src.data.mock_quality import QualityLevel, degrade_thumbnails
            try:
                level = QualityLevel(self.quality_level)
            except ValueError:
                level = QualityLevel.PERFECT
            mock_sets = degrade_thumbnails(level)
            if len(mock_sets) >= len(scripts):
                return mock_sets[:len(scripts)]
            from copy import deepcopy
            result = []
            for i, script in enumerate(scripts):
                base = deepcopy(mock_sets[i % len(mock_sets)])
                base.script_id = script.id
                result.append(base)
            return result

        sets = []
        for script in scripts:
            hook = script.segments[0].voiceover[:60] if script.segments else script.cta_text
            variants = []

            # Extract caption signals if available
            caption_signals = {}
            if caption_plans:
                caption_signals = _propagate_caption_signals(caption_plans, script.id)

            if self.use_skills:
                import src.skills.thumbnail_prompt  # noqa: F401
                from src.skills.registry import SkillRegistry

                skill_result = await SkillRegistry().execute("gpt-image-thumbnail-prompt", {
                    "hook_text": hook or "",
                    "product_name": "Product",
                    "brand_name": "",
                    "product_usp": "",
                    "mood": "lifestyle",
                    "brand_primary_color": "#D75C70",
                    "brand_secondary_color": "#2D2D2D",
                    "scenario": "general",
                })
                if skill_result.success and skill_result.data:
                    variants_data = skill_result.data.get("variants", [])
                    for v_data in variants_data:
                        variants.append({
                            "variant_id": v_data.get("style", "default"),
                            "style": v_data.get("style", "default"),
                            "prompt": v_data.get("prompt", ""),
                            "aspect_ratio": v_data.get("aspect_ratio", "9:16"),
                        })
                    continue  # Skip the old loop below

            for variant_id, concept in THUMBNAIL_CONCEPTS.items():
                prompt = self._build_prompt(concept, hook, caption_signals)

                # Generate actual image
                result = await self.dalle.generate(
                    prompt=prompt,
                    variant_id=variant_id,
                )

                variants.append(
                    ThumbnailVariant(
                        variant_id=variant_id,
                        concept=concept["concept"],
                        prompt=prompt,
                        image_url=result.get("image_url", ""),
                    )
                )

            sets.append(ThumbnailSet(script_id=script.id, variants=variants))
            logger.info(
                "thumbnail: set generated",
                script_id=script.id,
                images=len(variants),
                has_caption_signals=bool(caption_signals),
            )

        return sets

    def _build_prompt(
        self,
        concept: dict[str, str],
        hook: str,
        caption_signals: dict[str, Any],
    ) -> str:
        """Build a DALL-E prompt incorporating caption propagation signals."""
        # Determine text overlay description based on variant concept style
        text_overlay_descriptions = {
            "clean_ecom": "Text overlay at the top: bold product name in serif font, price badge at bottom right corner in pink highlight box",
            "emotional": "Text overlay across center: emotional headline in handwritten-style font, thin semitransparent bar behind text",
            "reaction": "Text overlay at bottom third: bold reaction quote in all-caps with exclamation mark, yellow highlight behind text",
            "minimal": "Text overlay at bottom left: single hook line in minimal sans-serif, small brand logo top left",
        }
        text_desc = text_overlay_descriptions.get(concept["style"], "Text overlay on image with product name and hook")

        prompt = (
            f"{concept['style']} thumbnail for wearable breast pump video. "
            f"Hook: '{hook}'. Brand colors: warm pink and charcoal. Vertical 9:16. "
            f"Clean, modern, high-end product photography style. "
            f"No nipples, no exposed breasts, no babies. "
            f"{text_desc}"
        )

        # Inject caption-driven visual emphasis
        if caption_signals.get("has_visual_emphasis"):
            highlights = caption_signals["highlight_texts"]
            cta_texts = caption_signals["cta_texts"]
            key_phrases = caption_signals["key_phrases"]

            emphasis_parts = []
            if highlights:
                emphasis_parts.append(f"Caption highlights: {', '.join(highlights)}")
            if cta_texts:
                emphasis_parts.append(f"CTA: {', '.join(cta_texts)}")
            if key_phrases:
                emphasis_parts.append(f"Key phrases: {', '.join(key_phrases)}")

            if emphasis_parts:
                prompt += " " + " | ".join(emphasis_parts)

            logger.debug(
                "thumbnail: caption signals injected into prompt",
                highlight_count=len(highlights),
                cta_count=len(cta_texts),
            )

        return prompt
