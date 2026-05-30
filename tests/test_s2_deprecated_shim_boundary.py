"""Contract tests for the frozen S2 deprecated import shim."""

from __future__ import annotations

import importlib
import inspect
import sys
import warnings

from src.routers import scenario


def test_s2_route_imports_v2_directly():
    """Production route must not depend on the deprecated shim."""
    source = inspect.getsource(scenario.run_s2_brand_campaign)

    assert "src.pipeline.s2_brand_pipeline_v2" in source
    assert "src.pipeline.s2_brand_pipeline import" not in source


def test_deprecated_shim_is_warning_only_alias():
    sys.modules.pop("src.pipeline.s2_brand_pipeline", None)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        shim = importlib.import_module("src.pipeline.s2_brand_pipeline")

    from src.pipeline.s2_brand_pipeline_v2 import (
        S2BrandCampaignPipeline as CanonicalPipeline,
    )

    deprecation_warnings = [
        warning for warning in captured if issubclass(warning.category, DeprecationWarning)
    ]
    assert deprecation_warnings
    assert shim.S2BrandCampaignPipeline is CanonicalPipeline
    assert shim.CANONICAL_IMPORT_PATH == "src.pipeline.s2_brand_pipeline_v2"
    assert "Frozen compatibility shim" in shim.REMOVAL_POLICY
