"""Phase 0 regression tests — fixes for 3 Oracle-identified critical risks.

Phase 0 ships 3 code fixes pre-deployment:
- #1: PG schema adds 5 runtime-state columns; state_manager save+load round-trip them
- #2: BudgetExceededError moved inside try-catch so it propagates as degraded
       state (was previously raising past handler -> HTTP 500 / stuck pending)
- #3: BrandComplianceSkill reads per-term severity from medical_lexicon,
       so FLAGGED / COMPETITOR tiers produce severity='low' not 'high'

Each fix has at least one assertion test asserting the prior bug is gone.
"""

from __future__ import annotations

import pytest

from src.skills.brand_compliance import BrandComplianceSkill
from src.tools.medical_lexicon import (
    build_severity_map,
    get_term_severity,
    merge_medical_lexicon,
)

# Phase 0 #1: PG round-trip preservation


class TestStateRoundTripFields:
    """Regression: save -> load preserves 5 runtime state fields."""

    @pytest.mark.asyncio
    async def test_fs_roundtrip_preserves_all_runtime_fields(self, tmp_path, monkeypatch):
        from src.pipeline import state_manager
        # OUTPUT_DIR is a class attribute on PipelineStateManager
        monkeypatch.setattr(state_manager.PipelineStateManager, "OUTPUT_DIR", tmp_path)

        mgr = state_manager.PipelineStateManager()
        label = "phase0_roundtrip"
        state = {
            "label": label,
            "scenario": "s1",
            "config": {"product_catalog": {"name": "X"}},
            "steps": {"strategy": {"status": "pending"}},
            "current_step": "strategy",
            "mode": "auto",
            "errors": [],
            "media_synthesis_errors": [],
            "gates": {},
            "schema_version": 1,
            "pipeline_degraded": True,
            "degraded_reason": "test_step",
            "trace_id": "abcdef123",
            "structured_errors": [{"kind": "test"}],
        }
        await mgr.save(label, state)
        loaded = await mgr.load(label)
        assert loaded is not None
        assert loaded["schema_version"] == 1
        assert loaded["pipeline_degraded"] is True
        assert loaded["degraded_reason"] == "test_step"
        assert loaded["trace_id"] == "abcdef123"
        assert loaded["structured_errors"] == [{"kind": "test"}]

    def test_repository_allowed_fields_include_new_columns(self):
        """_ALLOWED_FIELDS must list the 5 new columns so get_by_field
        SELECT validates them. Without this, SQL injection guard rejects
        the new columns."""
        from src.storage.repository import BaseRepository
        allowed = BaseRepository._ALLOWED_FIELDS["pipeline_states"]
        for col in ("schema_version", "pipeline_degraded", "degraded_reason",
                    "trace_id", "structured_errors"):
            assert col in allowed, f"{col} missing from _ALLOWED_FIELDS"


# Phase 0 #2: BudgetExceededError goes through degraded handler


class TestBudgetExceededDegradesNotRaises:
    """Regression: Expert mode budget overflow must produce degraded state,
    not bubble out as raw exception. Pre-Phase-0 placement was outside try,
    causing HTTP 500 / stuck pending state."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_sets_pipeline_degraded(self, tmp_path, monkeypatch):
        from src.pipeline import state_manager, step_runner
        from src.tools import cost_tracker

        monkeypatch.setattr(state_manager.PipelineStateManager, "OUTPUT_DIR", tmp_path)
        cost_tracker._records.clear()

        label = "phase0_budget_test"
        cost_tracker.set_thread_id(label)
        # Pre-load $6 cost > $5 cap
        cost_tracker.track("poyo_video", units=20)

        mgr = state_manager.PipelineStateManager()
        runner = step_runner.StepRunner(mgr)
        await runner.init_state(
            config={"product_catalog": {"name": "Test"}, "target_platforms": ["tiktok"]},
            mode="expert",
            label=label,
            scenario="s1",
        )
        final_state = await runner.run_step(label, "strategy")

        # Pipeline degraded handler caught the BudgetExceededError
        assert final_state.get("pipeline_degraded") is True
        assert final_state.get("degraded_reason") == "strategy"
        errors = final_state.get("errors", [])
        assert any("budget" in str(e).lower() for e in errors)
        cost_tracker._records.clear()


# Phase 0 #3: severity-aware lexicon


class TestSeverityAwareLexicon:
    """Regression: FLAGGED + COMPETITOR tiers must produce severity='low',
    not 'high'. Pre-Phase-0, BrandCompliance hard-coded severity='high' for
    every forbidden_content match, so benign phrases like 'natural lighting'
    were incorrectly BLOCKED."""

    def test_get_term_severity_high_for_banned(self):
        assert get_term_severity("cures cancer") == "high"
        assert get_term_severity("治疗癌症") == "high"

    def test_get_term_severity_low_for_flagged(self):
        assert get_term_severity("boosts immunity") == "low"
        assert get_term_severity("natural") == "low"
        assert get_term_severity("organic") == "low"
        assert get_term_severity("doctor recommended") == "low"
        assert get_term_severity("增强免疫力") == "low"

    def test_get_term_severity_low_for_competitor(self):
        assert get_term_severity("best on the market") == "low"
        # Verify a second COMPETITOR-tier phrase is detected as low too
        assert get_term_severity("award winning") == "low"

    def test_unknown_term_defaults_to_high(self):
        """Back-compat: caller-provided custom forbidden_content entries
        keep their pre-Phase-0 high-severity default."""
        assert get_term_severity("brand-specific-custom-rule") == "high"

    def test_severity_map_size_matches_lexicon(self):
        sm = build_severity_map()
        assert len(sm) >= 200

    def test_merge_writes_severity_map(self):
        result = merge_medical_lexicon({"brand_name": "X"})
        assert "_medical_lexicon_severity" in result
        assert result["_medical_lexicon_severity"]["cures cancer"] == "high"
        assert result["_medical_lexicon_severity"]["natural"] == "low"

    @pytest.mark.asyncio
    async def test_flagged_word_in_benign_context_not_blocked(self):
        """The Oracle-flagged false-positive case: 'natural lighting' in
        a benign S5 prompt-style script must NOT be BLOCKED."""
        skill = BrandComplianceSkill()
        r = await skill.execute({
            "scripts": [{"id": "s1", "segments": [{
                "voiceover": "Soft natural lighting with organic cotton packaging."
            }]}],
            "brand_guidelines": {"brand_name": "Brand"},
        })
        assert r.success
        report = r.data["reports"][0]
        # Status is FLAGGED, not BLOCKED
        assert report["status"] == "FLAGGED", f"Expected FLAGGED, got {report['status']}"
        # All forbidden_content flags from lexicon should be 'low'
        forbidden_flags = [f for f in report["flags"] if f["rule"] == "forbidden_content"]
        assert all(f["severity"] == "low" for f in forbidden_flags)

    @pytest.mark.asyncio
    async def test_banned_word_still_blocks(self):
        """Regression: BANNED tier must still produce BLOCKED status."""
        skill = BrandComplianceSkill()
        r = await skill.execute({
            "scripts": [{"id": "s1", "segments": [{
                "voiceover": "Our miracle bottle cures cancer in babies."
            }]}],
            "brand_guidelines": {"brand_name": "Brand"},
        })
        assert r.data["reports"][0]["status"] == "BLOCKED"

    @pytest.mark.asyncio
    async def test_custom_forbidden_content_still_blocks(self):
        """Back-compat: caller-provided forbidden_content entries (not in
        lexicon) keep their pre-Phase-0 high-severity behavior."""
        skill = BrandComplianceSkill()
        r = await skill.execute({
            "scripts": [{"id": "s1", "segments": [{
                "voiceover": "Contains brand-X-forbidden-phrase example."
            }]}],
            "brand_guidelines": {
                "brand_name": "Brand",
                "forbidden_content": ["brand-X-forbidden-phrase"],
            },
        })
        # Custom rule -> still high severity -> BLOCKED
        report = r.data["reports"][0]
        custom_flags = [f for f in report["flags"]
                        if "brand-X" in f.get("message", "")]
        assert custom_flags
        assert custom_flags[0]["severity"] == "high"
        assert report["status"] == "BLOCKED"
