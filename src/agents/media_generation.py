"""Media Generation Agent — fills asset gaps with AI-generated content.

MVP: pure stub. Returns placeholder entries.
Phase 2+: Flux, Runway Gen-3, Kling integration.
"""

import structlog

from src.models import AssetPlan

logger = structlog.get_logger()


class MediaGenerationAgent:
    """Generates AI assets for gaps in the asset plan."""

    async def run(self, asset_plans: list[AssetPlan]) -> list[dict]:
        generated = []
        for plan in asset_plans:
            for gap_desc in plan.gaps:
                generated.append({
                    "gap_description": gap_desc,
                    "generated_path": f"[AI-GENERATED-PLACEHOLDER] {gap_desc}",
                    "source": "ai_generated",
                    "status": "placeholder",
                })
        logger.info("media_generation: stub done", count=len(generated))
        return generated
