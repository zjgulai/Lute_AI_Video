"""Asset Sourcing Agent — matches shot requirements to asset library.

Supports two layers:
1. AssetLibraryClient (Supabase pgvector) — semantic search against stored assets
2. Mock fallback — deterministic results for dev/testing when library unavailable

Core rule: assets from library → source="library", gaps → source="ai_generated" later.
"""

from __future__ import annotations

import structlog

from src.models import AssetPlan, ShotAssetPlan, Storyboard
from src.tools.asset_library import AssetLibraryClient

logger = structlog.get_logger()


class AssetSourcingAgent:
    """Matches storyboard shot requirements to available assets.

    Uses AssetLibraryClient for real searches when possible,
    falls back to deterministic mock when Supabase unavailable.
    """

    def __init__(
        self,
        asset_library: AssetLibraryClient | None = None,
    ):
        self._library = asset_library or AssetLibraryClient()

    async def run(self, storyboards: list[Storyboard]) -> list[AssetPlan]:
        plans = []
        for sb in storyboards:
            shot_plans = []
            gaps = []
            for shot in sb.shots:
                # Step 1: search the asset library (or mock)
                candidates = self._library.search_assets(
                    query=shot.asset_needed or shot.visual,
                    limit=3,
                )

                # Step 2: narrow candidates to best matches
                # Filter only library-sourced candidates (mock returns "library" too)
                library_candidates = [
                    c
                    for c in candidates
                    if c.source in ("library", "ugc")
                ]

                # Step 3: decide: use library asset or mark gap
                best = library_candidates[0] if library_candidates else None
                gap = best is None

                plan = ShotAssetPlan(
                    shot_id=shot.id,
                    asset_needed=shot.asset_needed,
                    candidates=candidates,
                    selected_asset_id=best.asset_id if best else None,
                    gap=gap,
                )
                shot_plans.append(plan)
                if gap:
                    gaps.append(shot.asset_needed)

            plans.append(
                AssetPlan(
                    storyboard_id=sb.script_id,
                    shot_plans=shot_plans,
                    gaps=gaps,
                )
            )
        logger.info(
            "asset_sourcing: done",
            plan_count=len(plans),
            library_mode="mock" if self._library.is_mock else "supabase",
        )
        return plans
