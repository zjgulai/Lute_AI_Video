"""S2 Brand Campaign E2E test (Sprint 2 P2-3).

Verifies the new independent ``S2BrandCampaignPipeline`` (introduced
in Sprint 2 P2-1) end-to-end in mock mode — no real LLM / poyo calls.

Coverage areas (per diagnostic P0-3 requirement):
- run() returns the documented S2 result shape including
  scenario="brand_campaign" and always-populated compliance_reports key
- Brand identity correctly threaded into product_catalog
- Model routing resolves to S2's preferred model (kling-3-0/pro)
- Backwards-compat shim still exposes the class but emits DeprecationWarning
- Extreme inputs: empty brand_package, invalid video_duration, missing
  brand_name
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

import src.skills.brand_compliance  # noqa: F401
import src.skills.elevenlabs_tts  # noqa: F401
import src.skills.media_quality_audit  # noqa: F401
import src.skills.remotion_assemble  # noqa: F401
import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.seedance_video_generate  # noqa: F401
import src.skills.storyboard  # noqa: F401
from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    SkillRegistry.clear_global()
    import src.skills.brand_compliance  # noqa: F401
    import src.skills.elevenlabs_tts  # noqa: F401
    import src.skills.media_quality_audit  # noqa: F401
    import src.skills.remotion_assemble  # noqa: F401
    import src.skills.script_writer  # noqa: F401
    import src.skills.seedance_prompt  # noqa: F401
    import src.skills.seedance_video_generate  # noqa: F401
    import src.skills.storyboard  # noqa: F401
    yield
    SkillRegistry.clear_global()


BRAND_PACKAGE_FIXTURE: dict[str, Any] = {
    "brand_name": "MomCozy",
    "values": ["safety", "comfort", "modern motherhood"],
    "voice_guidelines": "warm, supportive, never preachy",
    "visual_constraints": "soft natural light; pastel palette",
    "competitor_context": "competitor X focuses on tech specs only",
}


class TestS2RunContract:
    @pytest.mark.asyncio
    async def test_run_returns_brand_campaign_scenario(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=30,
            enable_media_synthesis=False,
        )
        assert result["scenario"] == "brand_campaign"
        assert result["brand_name"] == "MomCozy"

    @pytest.mark.asyncio
    async def test_compliance_reports_key_always_present(self):
        """Diagnostic R-S2-ARCH: brand_mode compliance path must be observable
        in the result. Even when empty, the key must exist so consumers don't
        need to do .get() with a default."""
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert "compliance_reports" in result
        assert isinstance(result["compliance_reports"], list)

    @pytest.mark.asyncio
    async def test_run_routes_to_kling_3_0_pro(self):
        """S2 must route to its preferred model (kling-3-0/pro) per
        ModelRouter Sprint 1 contract — NOT seedance-2 (S1's preferred)."""
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert result["model_id"] == "kling-3-0/pro"

    @pytest.mark.asyncio
    async def test_run_brand_package_threaded_through(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert result["brand_package"] == BRAND_PACKAGE_FIXTURE


class TestS2RunResultShape:
    @pytest.mark.asyncio
    async def test_skip_media_returns_briefs_only(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        for key in [
            "briefs", "scripts", "storyboards", "compliance_reports",
            "errors", "media_synthesis_errors",
        ]:
            assert key in result, f"missing top-level key: {key}"
        assert "final_video_path" not in result

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_media_keys(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
        )
        for key in [
            "clip_paths", "audio_paths", "lyrics_paths",
            "thumbnail_image_paths", "final_video_path", "audit_report",
        ]:
            assert key in result, f"missing media key: {key}"

    def test_build_result_preserves_persisted_assemble_list_paths(self):
        result = S2BrandCampaignPipeline()._build_result(
            final_state={
                "steps": {
                    "assemble_final": {
                        "output": ["/tmp/s2-final.mp4", "/tmp/s2-render.json"],
                    },
                },
                "errors": [],
                "media_synthesis_errors": [],
            },
            brand_name="MomCozy",
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
            model_id="kling-3-0/pro",
            label="s2-test",
        )

        assert result["final_video_path"] == "/tmp/s2-final.mp4"
        assert result["render_json_path"] == "/tmp/s2-render.json"


class TestS2ExtremeInputs:
    @pytest.mark.asyncio
    async def test_empty_brand_package_uses_default_brand_name(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package={},
            enable_media_synthesis=False,
        )
        assert result["brand_name"] == "Brand"
        assert result["scenario"] == "brand_campaign"

    @pytest.mark.asyncio
    async def test_invalid_video_duration_falls_back_to_60(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=999,
            enable_media_synthesis=False,
        )
        assert result["video_duration"] == 60

    @pytest.mark.asyncio
    @pytest.mark.parametrize("duration", [15, 30, 45, 60, 90])
    async def test_valid_durations_preserved(self, duration):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=duration,
            enable_media_synthesis=False,
        )
        assert result["video_duration"] == duration

    @pytest.mark.asyncio
    async def test_brand_name_missing_does_not_crash(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package={"values": ["x"], "voice_guidelines": ""},
            enable_media_synthesis=False,
        )
        assert result["success"] is True


class TestS2DeprecationShim:
    def test_old_import_path_emits_deprecation_warning(self):
        """src.pipeline.s2_brand_pipeline import path triggers
        DeprecationWarning per Sprint 2 P2-2 contract."""
        import importlib
        import sys

        # Force re-import to trigger the warning fresh
        sys.modules.pop("src.pipeline.s2_brand_pipeline", None)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            importlib.import_module("src.pipeline.s2_brand_pipeline")
            deprecation_warnings = [
                w for w in captured if issubclass(w.category, DeprecationWarning)
            ]
            assert deprecation_warnings, "shim must emit DeprecationWarning"
            assert "s2_brand_pipeline_v2" in str(deprecation_warnings[0].message)

    def test_shim_re_exports_v2_class(self):
        """Same class object via both import paths — no diverged copies."""
        import sys

        sys.modules.pop("src.pipeline.s2_brand_pipeline", None)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.pipeline.s2_brand_pipeline import (
                S2BrandCampaignPipeline as Old,
            )
        from src.pipeline.s2_brand_pipeline_v2 import (
            S2BrandCampaignPipeline as V2,
        )
        assert Old is V2
