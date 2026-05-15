"""S2 backwards-compat shim — re-exports S2BrandCampaignPipeline from the
independent v2 implementation introduced in Sprint 2 P2-1/P2-2.

The canonical import path is now ``src.pipeline.s2_brand_pipeline_v2``.
This module is retained so older imports (notebooks, scripts/, external
tooling) continue to work without changes.

Will be removed in a future sprint once all known callers migrate. New
code should import from ``s2_brand_pipeline_v2`` directly.
"""

from __future__ import annotations

import warnings

from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline

warnings.warn(
    "src.pipeline.s2_brand_pipeline is deprecated; "
    "import S2BrandCampaignPipeline from src.pipeline.s2_brand_pipeline_v2.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["S2BrandCampaignPipeline"]
