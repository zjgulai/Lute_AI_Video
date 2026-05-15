"""Tests for Sprint 3 P3-1, P3-3, P3-4, P3-5 deliverables.

Per-Sprint 3:
- P3-1: C2PA signer (env-gated, graceful degradation)
- P3-3: partial_artifacts summarizer
- P3-4: Expert mode hard budget guard
- P3-5: state schema versioning + load-time mismatch warning
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from src.models.state import STATE_SCHEMA_VERSION
from src.pipeline.partial_artifacts import (
    _DELIVERABLE_STEPS,
    _step_has_output,
    summarize_partial_artifacts,
)
from src.pipeline.state_manager import _check_schema_version
from src.tools.c2pa_signer import build_manifest, is_enabled, sign_video
from src.tools.cost_tracker import (
    HARD_BUDGET_EXPERT_MODE,
    BudgetExceededError,
    check_budget,
    set_thread_id,
    track,
)

# ───────── P3-3 partial_artifacts ─────────


class TestStepHasOutput:
    def test_pending_step_has_no_output(self):
        assert _step_has_output({"status": "pending", "output": None}) is False

    def test_done_with_dict_output(self):
        assert _step_has_output({"status": "done", "output": {"k": "v"}}) is True

    def test_done_with_empty_string_output(self):
        """Empty string output is treated as missing."""
        assert _step_has_output({"status": "done", "output": ""}) is False

    def test_done_with_empty_list_output(self):
        assert _step_has_output({"status": "done", "output": []}) is False

    def test_done_with_empty_string_tuple(self):
        """S1 assemble_final's failure sentinel: ('', '')."""
        assert _step_has_output({"status": "done", "output": ("", "")}) is False

    def test_done_with_partial_string_tuple_is_valid(self):
        """One non-empty element means at least partial output exists."""
        assert _step_has_output({"status": "done", "output": ("/path.mp4", "")}) is True

    def test_edited_output_takes_precedence(self):
        step = {"status": "done", "output": None, "edited": True, "edited_output": [1]}
        assert _step_has_output(step) is True

    def test_seedance_clips_all_stub_treated_as_missing(self):
        step = {
            "status": "done",
            "output": {
                "clip_details": [
                    {"video_path": "/tmp/a.mp4", "is_stub": True, "duration_seconds": 0},
                    {"video_path": "/tmp/b.mp4", "is_stub": True, "duration_seconds": 0},
                    {"video_path": "/tmp/c.mp4", "is_stub": True, "duration_seconds": 0},
                ],
            },
        }
        assert _step_has_output(step) is False

    def test_seedance_clips_mixed_stub_and_real_is_valid(self):
        step = {
            "status": "done",
            "output": {
                "clip_details": [
                    {"video_path": "/tmp/a.mp4", "is_stub": True, "duration_seconds": 0},
                    {"video_path": "/tmp/b.mp4", "is_stub": False, "duration_seconds": 8},
                ],
            },
        }
        assert _step_has_output(step) is True

    def test_seedance_clips_no_clip_details_field_falls_back_to_dict_check(self):
        step = {
            "status": "done",
            "output": {"some_other_field": "value"},
        }
        assert _step_has_output(step) is True


class TestSummarizePartialArtifacts:
    def test_none_state_treated_as_degraded(self):
        result = summarize_partial_artifacts(None)
        assert result["degraded"] is True
        assert result["degraded_reason"] == "no_state"
        assert result["available_artifacts"] == {}
        assert set(result["missing_artifacts"]) == set(_DELIVERABLE_STEPS)

    def test_clean_success_not_degraded(self):
        state = {
            "steps": {
                "scripts": {"status": "done", "output": [{"id": "s1"}]},
                "assemble_final": {"status": "done", "output": {"video_path": "/x.mp4"}},
            },
            "errors": [],
        }
        result = summarize_partial_artifacts(state)
        assert result["degraded"] is False
        assert "scripts" in result["available_artifacts"]
        assert "assemble_final" in result["available_artifacts"]

    def test_explicit_degraded_flag_propagates(self):
        state = {
            "steps": {"scripts": {"status": "done", "output": [{"id": "s1"}]}},
            "errors": ["assemble_failed: timeout"],
            "pipeline_degraded": True,
            "degraded_reason": "assemble_final",
        }
        result = summarize_partial_artifacts(state)
        assert result["degraded"] is True
        assert result["degraded_reason"] == "assemble_final"
        assert "scripts" in result["available_artifacts"]
        assert result["error_summary"] == ["assemble_failed: timeout"]

    def test_implicit_degrade_via_empty_assemble_tuple(self):
        """S1's silent-failure pattern — assemble succeeds with ('', '')."""
        state = {
            "steps": {
                "scripts": {"status": "done", "output": [{"id": "s1"}]},
                "seedance_clips": {"status": "done", "output": {"clip_paths": ["/c.mp4"]}},
                "assemble_final": {"status": "done", "output": ("", "")},
            },
            "errors": ["assemble_failed: stub mode"],
        }
        result = summarize_partial_artifacts(state)
        assert result["degraded"] is True
        assert result["degraded_reason"] == "assemble_final_empty_output"
        assert "assemble_final" in result["missing_artifacts"]
        assert "seedance_clips" in result["available_artifacts"]


# ───────── P3-4 budget guard ─────────


@pytest.fixture(autouse=True)
def _isolate_cost_records():
    """Use a unique thread_id per test so records don't bleed across tests."""
    from src.tools import cost_tracker as ct
    ct._records.clear()
    yield
    ct._records.clear()


class TestBudgetGuard:
    def test_auto_mode_never_raises(self):
        set_thread_id("auto1")
        track("poyo_video", units=100)  # $30 — way over cap
        check_budget("auto1", "auto")  # No raise

    def test_expert_mode_under_cap_passes(self):
        set_thread_id("e1")
        track("poyo_video", units=10)  # $3.00
        check_budget("e1", "expert")  # Under $5

    def test_expert_mode_over_cap_raises(self):
        set_thread_id("e2")
        track("poyo_video", units=20)  # $6.00 > $5 cap
        with pytest.raises(BudgetExceededError) as excinfo:
            check_budget("e2", "expert")
        assert excinfo.value.thread_id == "e2"
        assert excinfo.value.cap_usd == HARD_BUDGET_EXPERT_MODE
        assert excinfo.value.total_usd >= HARD_BUDGET_EXPERT_MODE

    def test_expert_mode_at_exact_cap_raises(self):
        """Boundary: at exactly the cap, we raise (>= semantics)."""
        set_thread_id("e3")
        # Track exactly $5.00 (poyo_video=$0.30/unit, need ~17 units)
        from src.tools.cost_tracker import HARD_BUDGET_EXPERT_MODE as cap
        track("poyo_video", units=int(cap / 0.3) + 1)
        with pytest.raises(BudgetExceededError):
            check_budget("e3", "expert")

    def test_unknown_mode_no_enforcement(self):
        """Defensive: only "expert" triggers hard cap. Unknown modes treated
        as auto."""
        set_thread_id("u1")
        track("poyo_video", units=100)
        check_budget("u1", "smart")  # No raise
        check_budget("u1", "")  # No raise
        check_budget("u1", "fast")  # No raise

    def test_budget_exceeded_error_carries_context(self):
        set_thread_id("e4")
        track("poyo_video", units=20)
        with pytest.raises(BudgetExceededError) as excinfo:
            check_budget("e4", "expert")
        msg = str(excinfo.value)
        assert "e4" in msg
        assert "expert" in msg
        assert excinfo.value.mode == "expert"


# ───────── P3-5 schema versioning ─────────


class TestSchemaVersioning:
    def test_runtime_constant_is_positive(self):
        assert STATE_SCHEMA_VERSION >= 1

    def test_check_warns_on_missing_version(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.pipeline.state_manager"):
            _check_schema_version({}, "test_label")
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any("schema version mismatch" in r.message for r in warnings)
        assert any("test_label" in r.message for r in warnings)

    def test_check_warns_on_lower_version(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.pipeline.state_manager"):
            _check_schema_version({"schema_version": 0}, "old_state")
        assert any("persisted=0 runtime=" in r.message for r in caplog.records)

    def test_check_silent_on_match(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.pipeline.state_manager"):
            _check_schema_version({"schema_version": STATE_SCHEMA_VERSION}, "current")
        warnings = [r for r in caplog.records if "schema version mismatch" in r.message]
        assert warnings == []

    def test_check_handles_none_state(self):
        """No-op on None state (load returned nothing); should not raise."""
        _check_schema_version(None, "missing")


# ───────── P3-1 c2pa_signer ─────────


@pytest.fixture
def fake_mp4(tmp_path: Path):
    p = tmp_path / "fake.mp4"
    p.write_bytes(b"fake mp4 bytes" * 100)
    return p


class TestC2PAEnvGate:
    def test_disabled_by_default(self):
        os.environ.pop("C2PA_ENABLED", None)
        assert is_enabled() is False

    def test_enabled_via_truthy_env(self, monkeypatch):
        for val in ("1", "true", "yes", "TRUE"):
            monkeypatch.setenv("C2PA_ENABLED", val)
            assert is_enabled() is True

    def test_disabled_for_falsy_or_unset(self, monkeypatch):
        for val in ("0", "false", "no", ""):
            monkeypatch.setenv("C2PA_ENABLED", val)
            assert is_enabled() is False


class TestC2PAManifest:
    def test_minimum_eu_ai_act_fields_present(self):
        m = build_manifest("Test")
        assert m["format"] == "video/mp4"
        assert m["title"] == "Test"
        assert m["claim_generator_info"][0]["name"] == "AI_Video_Pipeline"
        assert m["assertions"][0]["label"] == "c2pa.actions"
        action = m["assertions"][0]["data"]["actions"][0]
        assert action["action"] == "c2pa.created"
        assert "aiGeneratedContent" in action["digitalSourceType"]

    def test_pipeline_version_overridable(self):
        m = build_manifest("X", pipeline_version="0.4.2")
        assert m["claim_generator_info"][0]["version"] == "0.4.2"


class TestC2PASignVideo:
    def test_disabled_returns_input_unchanged(self, fake_mp4: Path, monkeypatch):
        monkeypatch.delenv("C2PA_ENABLED", raising=False)
        result = sign_video(fake_mp4)
        assert result == str(fake_mp4)

    def test_enabled_without_cert_returns_input_unchanged(self, fake_mp4: Path, monkeypatch):
        """Graceful degradation: missing cert/key env → no-op, no raise."""
        monkeypatch.setenv("C2PA_ENABLED", "1")
        monkeypatch.delenv("C2PA_CERT_PATH", raising=False)
        monkeypatch.delenv("C2PA_KEY_PATH", raising=False)
        result = sign_video(fake_mp4)
        assert result == str(fake_mp4)

    def test_missing_input_file_returns_input_path(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("C2PA_ENABLED", "1")
        nonexistent = tmp_path / "missing.mp4"
        result = sign_video(nonexistent)
        assert result == str(nonexistent)

    def test_empty_input_file_returns_input_path(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("C2PA_ENABLED", "1")
        empty = tmp_path / "empty.mp4"
        empty.touch()
        result = sign_video(empty)
        assert result == str(empty)
