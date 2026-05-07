"""S2 E2E pipeline — DEPRECATED: thin wrapper around unified S1 pipeline.

S2 Brand Campaign is now a mode inside S1ProductDirectPipeline (brand_mode=True).
This file is kept for backwards compatibility with:
  - src/api.py   → /scenario/s2 endpoint
  - Any external callers importing S2BrandCampaignPipeline

Migration: replace calls to S2BrandCampaignPipeline with:
    S1ProductDirectPipeline().run(
        product_catalog={"name": brand_name, ...},
        brand_guidelines=brand_package,
        brand_mode=True,
        ...
    )
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class S2BrandCampaignPipeline:
    """Backwards-compat wrapper — delegates 100 % to S1ProductDirectPipeline."""

    async def run(
        self,
        brand_package: dict[str, Any],
        target_platforms: list[str] | None = None,
        target_languages: list[str] | None = None,
        week: str = "",
    ) -> dict[str, Any]:
        from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

        brand_name = brand_package.get("brand_name", "Brand")
        product_catalog = {"name": brand_name, **brand_package}

        logger.info(
            "s2_wrapper: delegating to S1 with brand_mode=True",
            brand=brand_name,
        )

        result = await S1ProductDirectPipeline().run(
            product_catalog=product_catalog,
            brand_guidelines=brand_package,
            target_platforms=target_platforms,
            target_languages=target_languages,
            week=week,
            brand_mode=True,
            enable_media_synthesis=True,
            output_label=f"s2_{brand_name.lower().replace(' ', '_')}",
        )

        # Ensure legacy keys that S2 callers may expect exist
        result.setdefault("brand_package", brand_package)
        result.setdefault("steps_completed", result.get("steps_completed", 11))
        return result
