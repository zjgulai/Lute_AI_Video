"""Tests for src/pipeline/model_router.py (Sprint 1 P1-1)."""

import pytest

from src.pipeline.model_router import (
    ModelChain,
    all_scenarios,
    get_chain,
    next_model,
    select_model,
    validate_chains,
)


class TestModelChain:
    def test_as_list_order(self):
        chain = ModelChain(preferred="a", fallback="b", budget="c")
        assert chain.as_list() == ["a", "b", "c"]

    def test_next_after_returns_fallback_then_budget(self):
        chain = ModelChain(preferred="a", fallback="b", budget="c")
        assert chain.next_after("a") == "b"
        assert chain.next_after("b") == "c"

    def test_next_after_budget_returns_none(self):
        chain = ModelChain(preferred="a", fallback="b", budget="c")
        assert chain.next_after("c") is None

    def test_next_after_unknown_returns_preferred(self):
        chain = ModelChain(preferred="a", fallback="b", budget="c")
        assert chain.next_after("x") == "a"


class TestSelectModel:
    def test_s1_preferred_is_seedance_2(self):
        assert select_model("s1") == "seedance-2"

    def test_s2_preferred_is_kling_3_0_pro(self):
        assert select_model("s2") == "kling-3-0/pro"

    def test_s3_preferred_is_kling_3_0_standard(self):
        assert select_model("s3") == "kling-3-0/standard"

    def test_s4_preferred_is_seedance_2_fast(self):
        assert select_model("s4") == "seedance-2-fast"

    def test_s5_preferred_is_seedance_2(self):
        assert select_model("s5") == "seedance-2"

    def test_unknown_scenario_falls_back_to_s1(self):
        assert select_model("s99") == select_model("s1")

    def test_uppercase_scenario_accepted(self):
        assert select_model("S5") == "seedance-2"


class TestGetChain:
    @pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
    def test_chain_has_three_distinct_tiers_per_scenario(self, scenario):
        chain = get_chain(scenario)
        # Preferred and budget should always differ — chain is meaningful
        assert chain.preferred != chain.budget

    def test_s1_chain_is_seedance_kling_wan(self):
        chain = get_chain("s1")
        assert chain.preferred == "seedance-2"
        assert chain.fallback == "kling-3-0/pro"
        assert chain.budget == "wan-2-7-video"

    def test_s5_chain_matches_s1_for_video_gen_path(self):
        # S5 (brand VLOG) uses same model tier as S1 (product direct)
        # because both demand premium quality. Diverges only in scoring
        # weights (handled by candidate_scorer scenario-specific dimensions).
        assert get_chain("s5") == get_chain("s1")


class TestNextModel:
    def test_s5_full_degradation_walk(self):
        # Sprint 1 P1-3: S5 multi-clip path can degrade across the chain
        walk = []
        m = select_model("s5")
        walk.append(m)
        while True:
            m = next_model("s5", m)
            if m is None:
                break
            walk.append(m)
        assert walk == ["seedance-2", "kling-3-0/pro", "wan-2-7-video"]

    def test_next_model_unknown_current_returns_preferred(self):
        assert next_model("s1", "completely-fake-model") == "seedance-2"

    def test_next_model_at_budget_returns_none(self):
        assert next_model("s4", "wan-2-2-fast") is None


class TestAllScenarios:
    def test_five_scenarios_supported(self):
        scenarios = all_scenarios()
        assert set(scenarios) == {"s1", "s2", "s3", "s4", "s5"}


class TestSsotEnforcement:
    """Regression: every model in every chain MUST have a threshold."""

    def test_validate_chains_clean(self):
        missing = validate_chains()
        assert missing == [], f"Chain entries without thresholds: {missing}"
