"""Tests for candidate_scorer scenario-aware weights (Sprint 2 P2-5)."""

from __future__ import annotations

import math

import pytest

from src.pipeline.candidate_scorer import (
    _SCRIPT_WEIGHTS,
    _heuristic_score_script,
    _resolve_script_weights,
)


class TestWeightsTable:
    @pytest.mark.parametrize("scenario", ["default", "s1", "s2", "s3", "s4", "s5"])
    def test_each_row_sums_to_one(self, scenario):
        """Diagnostic §8.2: weight rows must be probability distributions."""
        total = sum(_SCRIPT_WEIGHTS[scenario].values())
        assert math.isclose(total, 1.0, abs_tol=0.001), f"{scenario} sums to {total}"

    def test_all_rows_have_same_keys(self):
        ref_keys = set(_SCRIPT_WEIGHTS["default"].keys())
        for sc, w in _SCRIPT_WEIGHTS.items():
            assert set(w.keys()) == ref_keys, f"{sc} keys diverge"


class TestResolveWeights:
    def test_s1_resolves_to_s1_row(self):
        assert _resolve_script_weights("s1") == _SCRIPT_WEIGHTS["s1"]

    def test_uppercase_normalized(self):
        assert _resolve_script_weights("S2") == _SCRIPT_WEIGHTS["s2"]

    def test_none_returns_default(self):
        assert _resolve_script_weights(None) == _SCRIPT_WEIGHTS["default"]

    def test_unknown_returns_default(self):
        """Unknown scenarios MUST NOT regress to weight-0 — must mirror default."""
        assert _resolve_script_weights("s99") == _SCRIPT_WEIGHTS["default"]


class TestScenarioTilt:
    """Same script, different scenarios -> different overall (per design).

    Note: the heuristic path uses constants for ``brand_tone`` (0.75) and
    ``platform_fit`` (0.75), so the **direction** of scenario tilts is best
    observed via differential analysis, not absolute ranking. Real differen-
    tiation only kicks in once the LLM path replaces those constants with
    actual scoring (Sprint 3 work). See test_default_matches_pre_p2_5_behavior
    for the absolute regression contract.
    """

    SCRIPT_FIXTURE = {
        "segments": [
            {"voiceover": "Sustainable brand for modern moms. Eco-friendly. Click to shop."}
        ]
    }

    def _score(self, scenario):
        return _heuristic_score_script(
            self.SCRIPT_FIXTURE,
            ["eco-friendly"],
            None,
            scenario=scenario,
        )["overall"]

    def test_each_scenario_produces_different_overall(self):
        """Differential check: 5 scenarios should produce 5 distinct
        overall scores (allowing for ties only between scenarios with
        identical weights, which currently is none)."""
        scores = {sc: self._score(sc) for sc in ("s1", "s2", "s3", "s4", "s5")}
        assert len(set(scores.values())) == 5, f"All distinct: {scores}"

    def test_s1_differs_from_s2(self):
        """S1 (USP-heavy: 0.30) vs S2 (brand_tone-heavy: 0.35) -> different."""
        assert self._score("s1") != self._score("s2")

    def test_default_matches_pre_p2_5_behavior(self):
        """Regression: scenario=None must yield identical behavior to the
        original hardcoded weights (text 30% / strategy 25% / usp 20% /
        platform 15% / brand 10%). The default row exists exactly to
        preserve this invariant."""
        result = _heuristic_score_script(
            self.SCRIPT_FIXTURE, ["eco-friendly"], None, scenario=None,
        )
        breakdown = result["breakdown"]
        expected = (
            breakdown["text_quality"] * 0.30
            + breakdown["strategy_fit"] * 0.25
            + breakdown["usp_coverage"] * 0.20
            + breakdown["platform_fit"] * 0.15
            + breakdown["brand_tone"] * 0.10
        )
        assert math.isclose(result["overall"], expected, abs_tol=0.001)

    def test_high_usp_script_favors_s1_weighting(self):
        """When USP coverage is 100% (fixture mentions 'eco-friendly'),
        S1 (usp_coverage=0.30) should rank higher than S2/S5 which weight
        usp_coverage at 0.10."""
        s1 = self._score("s1")
        s2 = self._score("s2")
        s5 = self._score("s5")
        assert s1 > s2
        assert s1 > s5


class TestEmptyScriptPath:
    def test_empty_script_returns_zero_regardless_of_scenario(self):
        """Edge case: empty script short-circuits to overall=0 before
        weights apply. This was the pre-P2-5 behavior; preserved as
        invariant — empty input is zero quality, scenario weights cannot
        recover it."""
        for scenario in (None, "s1", "s2", "s3", "s4", "s5"):
            result = _heuristic_score_script({}, [], None, scenario=scenario)
            assert result["overall"] == 0.0, f"{scenario}: should still 0"


class TestBabySafetyComposition:
    """Composability: scenario weights compose with baby-safety multiplier
    (Sprint 0 wiring). Both effects apply; neither is short-circuited."""

    def test_s5_baby_no_safety_lang_gets_low_overall(self):
        """S5 (brand_tone-heavy) + baby catalog + no safety lang →
        weighted overall × safety penalty 0.3 → low score."""
        baby_catalog = {"product_name": "Baby Bottle"}
        result = _heuristic_score_script(
            {"segments": [{"voiceover": "Best baby bottle. Buy now!"}]},
            ["leak-proof"],
            baby_catalog,
            scenario="s5",
        )
        assert "baby_safety" in result["breakdown"]
        assert result["overall"] < 0.30
