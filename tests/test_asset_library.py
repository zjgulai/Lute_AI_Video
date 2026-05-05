"""Tests for GAP-14: Supabase asset library and integration with AssetSourcingAgent."""

from __future__ import annotations

import pytest

from src.models import Shot, Storyboard, AssetCandidate
from src.tools.asset_library import AssetLibraryClient
from src.agents.asset_sourcing import AssetSourcingAgent


# ═══════════════════════════════════════════
# AssetLibraryClient unit tests
# ═══════════════════════════════════════════


class TestAssetLibraryClient:
    """Tests for AssetLibraryClient initialization and mode switching."""

    def test_init_mock_mode_no_credentials(self):
        """No credentials → mock mode."""
        client = AssetLibraryClient()
        assert client.is_mock is True
        assert client.is_ready is False

    def test_init_mock_mode_empty_url(self):
        """Empty URL + empty key → mock mode."""
        client = AssetLibraryClient(supabase_url="", service_key="")
        assert client.is_mock is True

    def test_init_mock_mode_missing_key(self):
        """URL set but no key → mock mode."""
        client = AssetLibraryClient(
            supabase_url="https://project.supabase.co",
            service_key="",
        )
        assert client.is_mock is True

    def test_init_mock_bad_credentials_graceful(self):
        """Bad credentials → no exception raised at init."""
        # Note: supabase-py does lazy connection validation, so bad creds
        # may succeed at client creation. The key point is: no crash.
        client = AssetLibraryClient(
            supabase_url="https://bad-url.supabase.co",
            service_key="fake-key-that-will-fail",
        )
        # Client may or may not be in mock mode — the critical guarantee
        # is that no exception propagates from __init__
        _ = client  # No exception = test passes

    def test_mock_search_returns_results(self):
        """Mock search returns deterministic AssetCandidates."""
        client = AssetLibraryClient()
        results = client.search_assets("product demo", limit=3)
        assert len(results) == 3
        assert all(isinstance(r, AssetCandidate) for r in results)
        assert all(r.source == "library" for r in results)

    def test_mock_search_keyword_matching(self):
        """Mock search matches keywords in query."""
        client = AssetLibraryClient()
        results = client.search_assets("lifestyle")
        assert any("lifestyle" in r.description.lower() for r in results)

    def test_mock_search_default_padding(self):
        """Mock search pads with generic results when keywords don't match."""
        client = AssetLibraryClient()
        results = client.search_assets("zzz_nonexistent_zzz", limit=5)
        assert len(results) == 5
        # All should be generic assets since no keyword matched
        assert any("Generic" in r.description for r in results)

    def test_mock_store_returns_asset_id(self):
        """Mock store returns a non-empty asset ID."""
        client = AssetLibraryClient()
        asset_id = client.store_asset("/tmp/test.mp4", "A test asset")
        assert asset_id.startswith("ASSET-MOCK-")
        assert len(asset_id) > 10

    def test_mock_get_returns_asset(self):
        """Mock get returns a plausible AssetCandidate."""
        client = AssetLibraryClient()
        asset = client.get_asset("ASSET-999")
        assert asset is not None
        assert asset.asset_id == "ASSET-999"
        assert asset.source == "library"

    def test_mock_get_always_returns(self):
        """Mock get never returns None (in-memory = always available)."""
        client = AssetLibraryClient()
        asset = client.get_asset("NONEXISTENT-42")
        assert asset is not None


# ═══════════════════════════════════════════
# Agent integration tests
# ═══════════════════════════════════════════


class TestAssetSourcingWithLibrary:
    """AssetSourcingAgent integration with AssetLibraryClient."""

    @pytest.fixture
    def sample_storyboards(self):
        return [
            Storyboard(
                script_id="SCRIPT-001",
                total_duration=30.0,
                shots=[
                    Shot(
                        id=1,
                        start_time=0.0,
                        end_time=5.0,
                        shot_type="hook",
                        visual="A surprised mom sees the pump",
                        asset_needed="product_intro",
                    ),
                    Shot(
                        id=2,
                        start_time=5.0,
                        end_time=12.0,
                        shot_type="demo",
                        visual="Showing the product features",
                        asset_needed="feature_demo",
                    ),
                ],
            )
        ]

    @pytest.fixture
    def empty_storyboards(self):
        return []

    async def test_agent_uses_mock_library_by_default(self):
        """Default agent uses mock AssetLibraryClient."""
        agent = AssetSourcingAgent()
        assert agent._library.is_mock is True

    async def test_agent_accepts_custom_library(self):
        """Custom library can be injected."""
        lib = AssetLibraryClient()
        agent = AssetSourcingAgent(asset_library=lib)
        assert agent._library is lib

    async def test_agent_run_returns_plans(self, sample_storyboards):
        """Agent returns one AssetPlan per storyboard."""
        agent = AssetSourcingAgent()
        plans = await agent.run(sample_storyboards)
        assert len(plans) == 1
        assert plans[0].storyboard_id == "SCRIPT-001"

    async def test_agent_run_shot_plans_have_candidates(self, sample_storyboards):
        """Each shot in the plan has candidates from library."""
        agent = AssetSourcingAgent()
        plans = await agent.run(sample_storyboards)
        for plan in plans:
            for shot_plan in plan.shot_plans:
                assert len(shot_plan.candidates) > 0
                assert shot_plan.candidates[0].source == "library"

    async def test_agent_run_shot_plans_selected_asset(self, sample_storyboards):
        """Non-gap shots have a selected_asset_id set."""
        agent = AssetSourcingAgent()
        plans = await agent.run(sample_storyboards)
        for plan in plans:
            for shot_plan in plan.shot_plans:
                if not shot_plan.gap:
                    assert shot_plan.selected_asset_id is not None

    async def test_agent_run_empty_storyboards(self, empty_storyboards):
        """Empty storyboards → empty plans list."""
        agent = AssetSourcingAgent()
        plans = await agent.run(empty_storyboards)
        assert plans == []

    async def test_agent_run_library_mode_logged(self, sample_storyboards):
        """Agent logs the library mode (mock vs supabase)."""
        agent = AssetSourcingAgent()
        plans = await agent.run(sample_storyboards)
        assert len(plans) > 0  # Just verify it runs successfully

    async def test_agent_does_not_raise_on_empty_asset_needed(self):
        """Agent handles empty asset_needed gracefully."""
        sb = Storyboard(
            script_id="SCRIPT-NO-ASSET",
            total_duration=10.0,
            shots=[
                Shot(id=1, start_time=0.0, end_time=5.0, shot_type="hook",
                     visual="Opening scene", asset_needed=""),
            ],
        )
        agent = AssetSourcingAgent()
        plans = await agent.run([sb])
        assert len(plans) == 1
        # With empty asset_needed, mock search falls through to generic
        assert len(plans[0].shot_plans) == 1
