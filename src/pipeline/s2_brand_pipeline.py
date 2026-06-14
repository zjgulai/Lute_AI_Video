"""Frozen S2 backwards-compat shim.

The canonical import path is ``src.pipeline.s2_brand_pipeline_v2``. This
module exists only so older imports from notebooks, scripts, or external
tooling continue to resolve while emitting ``DeprecationWarning``.

Do not add pipeline behavior here. Removal requires a separate compatibility
decision after internal runtime imports are clean and external callers have a
migration window.
"""

from __future__ import annotations

import warnings

from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline

CANONICAL_IMPORT_PATH = "src.pipeline.s2_brand_pipeline_v2"
REMOVAL_POLICY = (
    "Frozen compatibility shim; delete only after explicit approval and an "
    "external import migration window."
)

warnings.warn(
    "src.pipeline.s2_brand_pipeline is deprecated; "
    f"import S2BrandCampaignPipeline from {CANONICAL_IMPORT_PATH}.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["S2BrandCampaignPipeline"]
