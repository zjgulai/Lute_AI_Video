"""Tests for auditor P1 quality criteria: hook text, emotional arc, information density."""


from src.agents.auditor import AuditorAgent


class TestHookTextScoring:
    def test_empty_text_zero(self):
        assert AuditorAgent._score_hook_text("") == 0.0
        assert AuditorAgent._score_hook_text("ab") == 0.0

    def test_curiosity_gap_signals(self):
        assert AuditorAgent._score_hook_text("What if I told you...") >= 0.5
        assert AuditorAgent._score_hook_text("Did you know 3 out of 4 moms...") >= 0.5

    def test_pattern_interrupt_signals(self):
        assert AuditorAgent._score_hook_text("Stop scrolling right now") >= 0.5
        assert AuditorAgent._score_hook_text("You are making a mistake") >= 0.5

    def test_strong_hook_max_score(self):
        text = "Stop! What if I told you 3 mistakes every new mom makes?"
        assert AuditorAgent._score_hook_text(text) >= 0.8

    def test_weak_hook_low_score(self):
        text = "This product is very good and you should buy it."
        assert AuditorAgent._score_hook_text(text) <= 0.5


class TestEmotionalArc:
    def test_complete_arc_high_score(self):
        segments = [
            {"segment_type": "hook", "voiceover": "What if..."},
            {"segment_type": "pain_point", "voiceover": "struggling..."},
            {"segment_type": "solution", "voiceover": "The answer is..."},
            {"segment_type": "cta", "voiceover": "Buy now!"},
        ]
        result = AuditorAgent._score_emotional_arc(segments)
        assert result["score"] >= 0.5

    def test_no_segments_low_score(self):
        result = AuditorAgent._score_emotional_arc([])
        assert result["score"] <= 0.3

    def test_missing_cta_urgency(self):
        segments = [
            {"segment_type": "hook", "voiceover": "hello"},
            {"segment_type": "pain_point", "voiceover": "problem"},
            {"segment_type": "solution", "voiceover": "answer"},
            {"segment_type": "cta", "voiceover": "thank you"},
        ]
        result = AuditorAgent._score_emotional_arc(segments)
        # No urgency words in CTA
        assert result["score"] < 1.0


class TestInformationDensity:
    def test_optimal_wps(self, auditor, sample_good_script):
        # sample_good_script has 45s duration and ~9 words/segment
        report = auditor.audit_script(sample_good_script)
        density = next(c for c in report.criteria if c.name == "Information Density")
        assert density is not None
        assert density.score <= 1.0

    def test_criterion_present(self, auditor, sample_good_script):
        report = auditor.audit_script(sample_good_script)
        names = {c.name for c in report.criteria}
        assert "Information Density" in names
        assert "Emotional Arc" in names

    def test_overall_score_uses_core_criteria_only(self, auditor, sample_good_script):
        report = auditor.audit_script(sample_good_script)
        # overall_score should be computed from 7 core criteria, not 9
        core_names = {
            "Hook Strength", "Segment Completeness", "Duration Fit",
            "Voiceover Clarity", "Brand Voice", "CTA Clarity", "Compliance Pre-check",
        }
        core_scores = [c.score for c in report.criteria if c.name in core_names]
        expected = round(sum(core_scores) / len(core_scores), 2)
        assert report.overall_score == expected
