"""Tests for 7 stub agents — all follow the same `async def run(...)` pattern.

Each test verifies:
1. Agent can be instantiated
2. Agent.run() returns the correct type (dict, struct)
3. Agent.run() returns non-empty output for valid input
4. Agent.run() handles empty/missing input gracefully
"""

import pytest

from src.models import (
    AssetPlan,
    Language,
    Platform,
    Script,
    ScriptSegment,
    Storyboard,
)


class TestStoryboardAgent:
    @pytest.mark.asyncio
    async def test_run_returns_storyboard_list(self):
        from src.agents.storyboard import StoryboardAgent
        agent = StoryboardAgent()
        script = Script(
            id="SCRIPT-TEST-001-EN",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=30.0,
            segments=[
                ScriptSegment(segment_type="hook", start_time=0.0, end_time=3.0,
                              voiceover="Test hook", visual_description="Test visual"),
            ],
            hashtags=["#test"],
            cta_text="Buy now",
        )
        result = await agent.run(scripts=[script])
        assert isinstance(result, list)
        assert len(result) >= 1
        assert isinstance(result[0], Storyboard)

    @pytest.mark.asyncio
    async def test_run_empty_scripts_returns_empty(self):
        from src.agents.storyboard import StoryboardAgent
        agent = StoryboardAgent()
        result = await agent.run(scripts=[])
        assert result == []


class TestAssetSourcingAgent:
    @pytest.mark.asyncio
    async def test_run_returns_asset_plan_list(self):
        from src.agents.asset_sourcing import AssetSourcingAgent
        agent = AssetSourcingAgent()
        storyboard = Storyboard(
            script_id="TEST-001",
            total_duration=30.0,
            shots=[],
        )
        result = await agent.run(storyboards=[storyboard])
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_empty_storyboards_returns_empty(self):
        from src.agents.asset_sourcing import AssetSourcingAgent
        agent = AssetSourcingAgent()
        result = await agent.run(storyboards=[])
        assert result == []


class TestMediaGenerationAgent:
    @pytest.mark.asyncio
    async def test_run_returns_generated_list(self):
        from src.agents.media_generation import MediaGenerationAgent
        agent = MediaGenerationAgent()
        asset_plan = AssetPlan(
            storyboard_id="SB-001",
            shot_plans=[],
            gaps=["Missing product shot"],
        )
        result = await agent.run(asset_plans=[asset_plan])
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "gap_description" in result[0]
        assert "generated_path" in result[0]

    @pytest.mark.asyncio
    async def test_run_no_gaps_returns_empty(self):
        from src.agents.media_generation import MediaGenerationAgent
        agent = MediaGenerationAgent()
        asset_plan = AssetPlan(storyboard_id="SB-002", shot_plans=[], gaps=[])
        result = await agent.run(asset_plans=[asset_plan])
        assert result == []


class TestEditingAgent:
    @pytest.mark.asyncio
    async def test_run_returns_edit_compositions(self):
        from src.agents.editor import EditingAgent
        agent = EditingAgent()
        storyboard = Storyboard(script_id="TEST-001", total_duration=30.0, shots=[])
        result = await agent.run(storyboards=[storyboard], asset_plans=[])
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_empty_storyboards_returns_empty(self):
        from src.agents.editor import EditingAgent
        agent = EditingAgent()
        result = await agent.run(storyboards=[], asset_plans=[])
        assert result == []


class TestAudioDesignAgent:
    @pytest.mark.asyncio
    async def test_run_returns_audio_plans(self):
        from src.agents.audio_designer import AudioDesignAgent
        agent = AudioDesignAgent()
        script = Script(
            id="SCRIPT-AUDIO-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=15.0,
            segments=[
                ScriptSegment(segment_type="hook", start_time=0.0, end_time=5.0,
                              voiceover="Hello", visual_description="Visual"),
            ],
            hashtags=[],
            cta_text="",
        )
        result = await agent.run(scripts=[script])
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_run_empty_scripts_returns_empty(self):
        from src.agents.audio_designer import AudioDesignAgent
        agent = AudioDesignAgent()
        result = await agent.run(scripts=[])
        assert result == []


class TestDistributionAgent:
    @pytest.mark.asyncio
    async def test_run_returns_distribution_plans(self):
        from src.agents.distribution import DistributionAgent
        agent = DistributionAgent()
        script = Script(
            id="SCRIPT-DIST-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=30.0,
            segments=[ScriptSegment(segment_type="hook", start_time=0.0, end_time=3.0,
                                    voiceover="Test", visual_description="Test")],
            hashtags=["#test"],
            cta_text="",
        )
        result = await agent.run(scripts=[script], thumbnail_sets=[])
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_empty_scripts_returns_empty(self):
        from src.agents.distribution import DistributionAgent
        agent = DistributionAgent()
        result = await agent.run(scripts=[], thumbnail_sets=[])
        assert result == []


class TestAnalyticsAgent:
    @pytest.mark.asyncio
    async def test_run_returns_analytics_reports(self):
        from src.agents.analytics import AnalyticsAgent
        agent = AnalyticsAgent()
        script = Script(
            id="SCRIPT-ANA-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=15.0,
            segments=[ScriptSegment(segment_type="hook", start_time=0.0, end_time=3.0,
                                    voiceover="Test", visual_description="Test")],
            hashtags=[],
            cta_text="",
        )
        result = await agent.run(scripts=[script], week="2026-W17")
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_run_empty_scripts_returns_baseline_report(self):
        from src.agents.analytics import AnalyticsAgent
        agent = AnalyticsAgent()
        result = await agent.run(scripts=[], week="2026-W17")
        assert isinstance(result, list)
        assert len(result) == 1
        report = result[0]
        assert report.week == "2026-W17"
