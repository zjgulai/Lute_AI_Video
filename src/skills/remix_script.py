"""Remix script skill — generates influencer-style remix script from analysis + product.

Takes VideoAnalysisSkill output + product information, produces:
  - Remix script skeleton (keeps influencer hook style + language patterns)
  - Video segment descriptions (what to keep from original, what to replace)
  - Production notes for video generation

Auto-registers with SkillRegistry on import as "remix-script-skill".
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.models.provider_cost import ProviderCostContractError
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


# Segment-level replacement rules
SEGMENT_REPLACEMENT = {
    "hook": {
        "keep": "style, pacing, catchphrases, hook structure",
        "replace": "product reference, problem statement, value prop",
    },
    "intro": {
        "keep": "greeting, energy level, personal address style",
        "replace": "new product introduction, relevance setup",
    },
    "body": {
        "keep": "storytelling rhythm, sentence structure, transitions",
        "replace": "product features, use cases, comparison points",
    },
    "transition": {
        "keep": "transition phrases, pacing",
        "replace": "new content bridge",
    },
    "pitch": {
        "keep": "urgency level, offer framing style",
        "replace": "new product pitch, pricing, value",
    },
    "demo": {
        "keep": "demo pacing, reaction style, interaction pattern",
        "replace": "new product demonstration",
    },
    "testimonial": {
        "keep": "storytelling voice, emotional cues",
        "replace": "new product experience story",
    },
    "cta": {
        "keep": "CTA energy, direct-to-camera style, catchphrases",
        "replace": "new link, new offer, new deadline",
    },
    "outro": {
        "keep": "sign-off style, signature phrases, music cue",
        "replace": "new brand mention, new follow prompt",
    },
}


class RemixScriptSegment:
    """A single segment in the remix script."""

    def __init__(
        self,
        segment_type: str = "hook",
        keep_notes: str = "",
        replace_notes: str = "",
        remix_description: str = "",
    ):
        self.segment_type = segment_type
        self.keep_notes = keep_notes
        self.replace_notes = replace_notes
        self.remix_description = remix_description

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_type": self.segment_type,
            "keep_notes": self.keep_notes,
            "replace_notes": self.replace_notes,
            "remix_description": self.remix_description,
        }


class RemixScriptResult:
    """Complete remix script."""

    def __init__(self):
        self.brief_id: str = ""
        self.influencer_name: str = ""
        self.product_name: str = ""
        self.original_style_preserved: str = ""
        self.segments: list[RemixScriptSegment] = []
        self.full_remix_script: str = ""
        self.production_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "influencer_name": self.influencer_name,
            "product_name": self.product_name,
            "original_style_preserved": self.original_style_preserved,
            "segments": [s.to_dict() for s in self.segments],
            "full_remix_script": self.full_remix_script,
            "production_notes": self.production_notes,
        }


class RemixScriptSkill(SkillCallable):
    """Generate remix script from video analysis + product info.

    Input params:
      analysis: dict — output of VideoAnalysisSkill.execute()
      product: dict — product info: {name, category, usps, brand_name, image_url}
      brief_id: str — optional brief ID
      influencer_name: str — optional influencer name for script personalization

    Returns RemixScriptResult as dict.
    """

    name = "remix-script-skill"
    description = (
        "Takes a video analysis (style, hook, segments) and product info, "
        "produces a remix script that keeps the influencer's style skeleton "
        "while replacing content with the company's product. "
        "Used in the influencer remix pipeline (S3)."
    )

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("analysis"):
            errors.append("'analysis' is required")
        if not params.get("product"):
            errors.append("'product' is required")
        return errors

    def validate_output(self, output: dict) -> list[str]:  # type: ignore[override]
        errors = []
        if not output.get("segments"):
            errors.append("'segments' missing from output")
        return errors

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        analysis = params["analysis"]
        product = params["product"]
        brief_id = params.get("brief_id", "")
        influencer_name = params.get("influencer_name", "Influencer")

        # Extract key info
        product_name = product.get("name", "Product Name")
        usps = product.get("usps", [])
        brand_name = product.get("brand_name", "")
        category = product.get("category", "product")

        # Style from analysis
        hook_type = analysis.get("hook_type", "question")
        speech_style = analysis.get("speech_style", "casual")
        catchphrases = analysis.get("catchphrases", [])
        original_segments = analysis.get("segments", [])

        # Product context for LLM-driven remix
        product_context = params.get("product_context", {})
        variant = params.get("variant")
        operation_scope = params.get("operation_scope", "execution")
        if not isinstance(operation_scope, str) or not operation_scope:
            operation_scope = "execution"

        # Build remix segments — try LLM-driven if product context is available
        if product_context.get("pain_points") or product_context.get("target_audience"):
            try:
                segments = await self._build_remix_segments_llm(
                    segments=original_segments,
                    product_name=product_name,
                    usps=usps,
                    brand_name=brand_name,
                    product_context=product_context,
                    speech_style=speech_style,
                    hook_type=hook_type,
                    variant=variant if isinstance(variant, str) else None,
                    operation_scope=operation_scope,
                )
            except ProviderCostContractError:
                raise
            except Exception as e:
                logger.warning("remix_script: LLM path failed, using rules", error=str(e)[:200])
                segments = self._build_remix_segments(
                    original_segments=original_segments,
                    hook_type=hook_type,
                    product_name=product_name,
                    usps=usps,
                    brand_name=brand_name,
                    speech_style=speech_style,
                    catchphrases=catchphrases,
                )
        else:
            # No product context — use rule-based (backward compat)
            segments = self._build_remix_segments(
                original_segments=original_segments,
                hook_type=hook_type,
                product_name=product_name,
                usps=usps,
                brand_name=brand_name,
                speech_style=speech_style,
                catchphrases=catchphrases,
            )

        # Generate full script text
        full_script = self._generate_full_script(
            segments=segments,
            product_name=product_name,
            brand_name=brand_name,
            usps=usps,
            speech_style=speech_style,
            catchphrases=catchphrases,
            influencer_name=influencer_name,
        )

        # Production notes
        production_notes = self._generate_production_notes(
            analysis=analysis,
            product_name=product_name,
            hook_type=hook_type,
            speech_style=speech_style,
        )

        result = RemixScriptResult()
        result.brief_id = brief_id
        result.influencer_name = influencer_name
        result.product_name = product_name
        result.original_style_preserved = (
            f"Kept {speech_style} style, {hook_type} hook structure, "
            f"{len(catchphrases)} catchphrases, "
            f"{len(segments)} segment structure from original"
        )
        result.segments = segments
        result.full_remix_script = full_script
        result.production_notes = production_notes

        return SkillResult(
            success=True,
            data=result.to_dict(),
        )

    def _build_remix_segments(
        self,
        original_segments: list[dict[str, Any]],
        hook_type: str,
        product_name: str,
        usps: list[str],
        brand_name: str,
        speech_style: str,
        catchphrases: list[str],
    ) -> list[RemixScriptSegment]:
        """Build remix segments from original segments + product info."""
        if not original_segments:
            # Create default segments
            return self._create_default_segments(
                hook_type=hook_type,
                product_name=product_name,
                usps=usps,
                brand_name=brand_name,
                catchphrases=catchphrases,
            )

        remix_segments = []
        for seg in original_segments:
            seg_type = seg.get("type", "body")
            replacement = SEGMENT_REPLACEMENT.get(
                seg_type,
                {
                    "keep": "general style",
                    "replace": "content",
                },
            )

            remix_seg = RemixScriptSegment(
                segment_type=seg_type,
                keep_notes=f"Keep {replacement['keep']}. Original: {seg.get('description', '-')[:100]}",
                replace_notes=f"Replace with {product_name} content: {replacement['replace']}",
                remix_description=self._build_segment_description(
                    seg_type=seg_type,
                    product_name=product_name,
                    usps=usps,
                    hook_type=hook_type,
                ),
            )
            remix_segments.append(remix_seg)

        return remix_segments

    async def _build_remix_segments_llm(
        self,
        segments: list[dict[str, Any]],
        product_name: str,
        usps: list[str],
        brand_name: str,
        product_context: dict[str, Any],
        speech_style: str = "",
        hook_type: str = "",
        variant: str | None = None,
        operation_scope: str = "execution",
    ) -> list[RemixScriptSegment]:
        """LLM-driven remix: one call processes all segments with full context.

        Falls back to rule-based _build_remix_segments on LLM failure.
        """
        from src.tools.llm_client import llm

        pain_points = product_context.get("pain_points", [])
        target_audience = product_context.get("target_audience", "")
        competitor_context = product_context.get("competitor_context", [])
        usage_scenario = product_context.get("usage_scenario", "")

        system = """You are a video remix specialist. Given an influencer's original video
segments and a new product, rewrite the script so the influencer promotes the NEW product
naturally while preserving their authentic style, emotional rhythm, and personality.

## Rules
1. PRESERVE the original segment structure and emotional pacing
2. PRESERVE the influencer's speech style and catchphrases
3. REPLACE product mentions naturally — don't force it into every sentence
4. USE the provided pain_points as hook angles
5. DIFFERENTIATE from competitors without naming them
6. Match the NEW product's target audience in voice and references
7. Return JSON with the same number of segments, same timing

Return ONLY valid JSON with this structure:
{"segments": [{"segment_type": "hook", "start_time": 0, "end_time": 5,
  "remix_description": "What to say/show in this segment with the new product",
  "voiceover": "Natural voiceover text", "keep_original": false}]}"""

        user = f"""Original Video Analysis:
- Speech style: {speech_style}
- Hook type: {hook_type}
- Segments: {json.dumps(segments, indent=2)}

New Product: {product_name}
USPs: {", ".join(usps)}
Brand: {brand_name}

Product Context:
- Pain Points: {", ".join(pain_points) if pain_points else "N/A"}
- Target Audience: {target_audience or "N/A"}
- Competitor Context: {", ".join(competitor_context) if competitor_context else "N/A"}
- Usage Scenario: {usage_scenario or "N/A"}

Remix {len(segments)} segments for the new product."""

        try:
            raw = await llm.invoke_json(
                system,
                user,
                operation_key="skill.remix_script",
                operation_instance=(
                    f"{operation_scope}.variant.{variant}" if variant else f"{operation_scope}.primary"
                ),
            )
            if isinstance(raw, dict) and "segments" in raw:
                llm_segments = raw["segments"]
                # Convert LLM output dicts to RemixScriptSegment objects
                return [
                    RemixScriptSegment(
                        segment_type=s.get("segment_type", "body"),
                        keep_notes=s.get("keep_notes", ""),
                        replace_notes=s.get("replace_notes", ""),
                        remix_description=s.get("remix_description", ""),
                    )
                    for s in llm_segments
                ]
        except ProviderCostContractError:
            raise
        except Exception as e:
            logger.warning(
                "remix_script: LLM failed, falling back to rule-based", error=str(e)[:200], product_name=product_name
            )

        # Fallback to rule-based
        return self._build_remix_segments(
            original_segments=segments,
            hook_type=hook_type,
            product_name=product_name,
            usps=usps,
            brand_name=brand_name,
            speech_style=speech_style,
            catchphrases=[],
        )

    def _create_default_segments(
        self,
        hook_type: str,
        product_name: str,
        usps: list[str],
        brand_name: str,
        catchphrases: list[str],
    ) -> list[RemixScriptSegment]:
        """Create default 5-segment structure when no original segments available."""
        catchphrase_str = ", ".join(catchphrases[:3]) if catchphrases else ""
        style_tag = catchphrase_str or f"'{hook_type}' hook style"

        hook_desc = (
            f"Open with {hook_type.replace('_', ' ')} hook style. "
            f"Product: {product_name}. Problem or curiosity-piquing angle."
        )
        if catchphrases:
            hook_desc += f" Use signature opener: '{catchphrases[0]}'."

        return [
            RemixScriptSegment(
                segment_type="hook",
                keep_notes=f"Keep {hook_type} hook structure, pacing, and {style_tag}",
                replace_notes=f"Replace original hook topic with {product_name} pain point",
                remix_description=hook_desc,
            ),
            RemixScriptSegment(
                segment_type="body",
                keep_notes=f"Keep {style_tag} storytelling rhythm and transitions",
                replace_notes=f"Replace with {product_name}: {', '.join(usps[:2])}",
                remix_description=(
                    f"Feature highlight for {product_name}. "
                    f"Use benefit-driven language. "
                    f"Show or describe USP: {', '.join(usps[:3])}"
                ),
            ),
            RemixScriptSegment(
                segment_type="demo",
                keep_notes=f"Keep demo pacing, reaction style, and {style_tag}",
                replace_notes=f"Replace with {product_name} demonstration",
                remix_description=(
                    f"Visual demonstration of {product_name}. Highlight ease of use, results, or quality."
                ),
            ),
            RemixScriptSegment(
                segment_type="pitch",
                keep_notes="Keep urgency level and offer framing from original",
                replace_notes=f"Replace with {product_name} offer and value proposition",
                remix_description=(f"Pitch {product_name} with urgency. Mention value: {', '.join(usps[:2])}"),
            ),
            RemixScriptSegment(
                segment_type="cta",
                keep_notes=f"Keep CTA energy and {style_tag} sign-off",
                replace_notes=f"Replace with {product_name} link and new offer CTA",
                remix_description=(
                    f"Clear call to action with {product_name} link. Include urgency or scarcity element."
                ),
            ),
        ]

    def _build_segment_description(
        self,
        seg_type: str,
        product_name: str,
        usps: list[str],
        hook_type: str,
    ) -> str:
        """Build a single segment description."""
        base_mapping = {
            "hook": f"Opening with {hook_type.replace('_', ' ')} angle for {product_name}",
            "intro": f"Introduce {product_name} in personal, relatable way",
            "body": f"Main content: {product_name} features — {', '.join(usps[:3])}",
            "transition": f"Bridge to {product_name} value proposition",
            "pitch": f"Sell {product_name}: {', '.join(usps[:2])}",
            "demo": f"Show {product_name} in action / results",
            "testimonial": f"Personal experience with {product_name}",
            "cta": f"Send to {product_name} link with urgency",
            "outro": f"Sign off with {product_name} brand mention",
        }
        return base_mapping.get(seg_type, f"{seg_type} segment for {product_name}")

    def _generate_full_script(
        self,
        segments: list[RemixScriptSegment],
        product_name: str,
        brand_name: str,
        usps: list[str],
        speech_style: str,
        catchphrases: list[str],
        influencer_name: str,
    ) -> str:
        """Generate full remix script text."""
        lines = [f"# Remix Script: {product_name}", f"# Style: {speech_style}", ""]

        catchphrase_str = f" ({', '.join(catchphrases[:2])})" if catchphrases else ""

        for seg in segments:
            lines.append(f"## [{seg.segment_type.upper()}]")
            lines.append(f"{seg.remix_description}")
            lines.append(f"  [Keep] {seg.keep_notes}")
            lines.append(f"  [Replace] {seg.replace_notes}")
            lines.append("")

        # Influencer-style full script draft
        usp_text = ", ".join(usps[:2]) if usps else "great quality"

        # Hook
        if segments and segments[0].segment_type == "hook":
            hook_desc = segments[0].remix_description
        else:
            hook_desc = f"Opening with attention-grabbing hook about {product_name}"

        lines.append("## [FULL SCRIPT DRAFT]")
        lines.append("")
        lines.append(f"Hook ({speech_style} tone{catchphrase_str}):")
        lines.append(f"  {hook_desc}")
        lines.append("")
        lines.append("Body:")
        lines.append(f"  Introduce {product_name} — what it is and why it matters.")
        lines.append(f"  Key points: {usp_text}")
        lines.append(f"  Use {influencer_name}'s signature pacing and transitions.")
        lines.append("")
        lines.append("Pitch:")
        lines.append(f"  Why {product_name} is the solution. Urgency + value.")
        lines.append("")
        lines.append("CTA:")
        lines.append(f"  Direct audience to link. {brand_name + ' ' if brand_name else ''}Offer hook.")
        lines.append("")

        return "\n".join(lines)

    def _generate_production_notes(
        self,
        analysis: dict[str, Any],
        product_name: str,
        hook_type: str,
        speech_style: str,
    ) -> str:
        """Generate production notes for video generation."""
        return (
            f"Style: '{speech_style}' tone with '{hook_type}' hook. "
            f"Video duration suggestion: ~{analysis.get('duration_seconds', 30)} seconds. "
            f"Audio: Match original speech pace ({analysis.get('avg_speech_wpm', 150):.0f} wpm). "
            f"Visual: Replace original product visuals with {product_name} footage. "
            f"Keep same aspect ratio and editing rhythm as original."
        )

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Fallback remix script."""
        product = params.get("product", {})
        product_name = product.get("name", "Product Name")
        usps = product.get("usps", [])

        result = RemixScriptResult()
        result.brief_id = params.get("brief_id", "")
        result.influencer_name = params.get("influencer_name", "Influencer")
        result.product_name = product_name
        result.segments = [
            RemixScriptSegment(
                segment_type="body",
                keep_notes="Keep general influencer style",
                replace_notes=f"Replace with {product_name} content",
                remix_description=f"Remix with {product_name}: product showcase",
            )
        ]
        result.full_remix_script = (
            f"[REMIX SCRIPT - FALLBACK]\n"
            f"Product: {product_name}\n"
            f"Style: Follow influencer's original hook and delivery.\n"
            f"Replacement: Product showcase with USP: {', '.join(usps[:2]) if usps else 'quality'}\n"
        )
        result.production_notes = (
            f"Fallback mode — keep original video structure, overlay {product_name} visuals and audio"
        )
        return SkillResult(
            success=True,
            data=result.to_dict(),
            error="Used fallback script (partial params)",
        )


# Auto-register
SkillRegistry().register(RemixScriptSkill())
logger.info("skill registered", name=RemixScriptSkill.name)
