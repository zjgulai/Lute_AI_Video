"""Tests for src/tools/medical_lexicon.py + BrandComplianceSkill auto-merge.

Sprint 3 P3-2 — closes diagnostic R-S1-COMP / R-S2-COMP / R-S3-COMP.
"""

from __future__ import annotations

import pytest

from src.tools.medical_lexicon import (
    MEDICAL_BANNED_CLAIMS,
    MEDICAL_BANNED_CLAIMS_ZH,
    MEDICAL_COMPETITOR_CLAIMS,
    MEDICAL_FLAGGED_CLAIMS,
    MEDICAL_FLAGGED_CLAIMS_ZH,
    get_all_medical_terms,
    merge_medical_lexicon,
)


class TestLexiconCoverage:
    """Diagnostic P3-2 mandates 200+ terms baseline."""

    def test_total_count_meets_200_minimum(self):
        assert len(get_all_medical_terms()) >= 200

    def test_banned_includes_canonical_disease_claims(self):
        for term in (
            "cures cancer", "cures autism", "treats covid",
            "replaces breastfeeding", "alternative to vaccines",
        ):
            assert term in MEDICAL_BANNED_CLAIMS, f"missing canonical: {term}"

    def test_chinese_banned_present(self):
        for term in ("治疗癌症", "替代疫苗", "比母乳更好"):
            assert term in MEDICAL_BANNED_CLAIMS_ZH, f"missing zh: {term}"

    def test_flagged_distinct_from_banned(self):
        """No term should appear in both BANNED and FLAGGED — severity must
        be unambiguous per term."""
        en_overlap = set(MEDICAL_BANNED_CLAIMS) & set(MEDICAL_FLAGGED_CLAIMS)
        zh_overlap = set(MEDICAL_BANNED_CLAIMS_ZH) & set(MEDICAL_FLAGGED_CLAIMS_ZH)
        assert not en_overlap, f"EN BANNED/FLAGGED overlap: {en_overlap}"
        assert not zh_overlap, f"ZH BANNED/FLAGGED overlap: {zh_overlap}"

    def test_competitor_tier_distinct(self):
        en_set = set(MEDICAL_COMPETITOR_CLAIMS)
        banned_set = set(MEDICAL_BANNED_CLAIMS)
        assert not (en_set & banned_set)


class TestMergeContract:
    def test_none_input_returns_dict_with_lexicon(self):
        merged = merge_medical_lexicon(None)
        assert "forbidden_content" in merged
        assert "cures cancer" in merged["forbidden_content"]

    def test_empty_dict_input_preserved(self):
        merged = merge_medical_lexicon({})
        assert "cures cancer" in merged["forbidden_content"]

    def test_caller_entries_preserved_first(self):
        """Brand-specific entries must come BEFORE lexicon defaults so
        per-brand overrides are detected first by downstream matchers."""
        merged = merge_medical_lexicon({"forbidden_content": ["custom-rule-A", "custom-rule-B"]})
        fc = merged["forbidden_content"]
        assert fc[0] == "custom-rule-A"
        assert fc[1] == "custom-rule-B"
        assert "cures cancer" in fc

    def test_dedupe_caller_entries_against_lexicon(self):
        """If caller already provided a term that's also in the lexicon,
        do not duplicate it."""
        merged = merge_medical_lexicon({"forbidden_content": ["cures cancer"]})
        fc = merged["forbidden_content"]
        assert fc.count("cures cancer") == 1

    def test_other_guidelines_fields_preserved(self):
        merged = merge_medical_lexicon({"brand_name": "X", "tone": "warm"})
        assert merged["brand_name"] == "X"
        assert merged["tone"] == "warm"

    def test_input_not_mutated(self):
        original = {"forbidden_content": ["caller-rule"]}
        merge_medical_lexicon(original)
        assert original["forbidden_content"] == ["caller-rule"]


class TestMergeFlags:
    def test_include_flagged_false_excludes_flagged_tier(self):
        merged = merge_medical_lexicon(None, include_flagged=False, include_chinese=False)
        fc = merged["forbidden_content"]
        assert "cures cancer" in fc  # BANNED still in
        assert "boosts immunity" not in fc  # FLAGGED excluded

    def test_include_competitor_false_excludes_competitor(self):
        merged = merge_medical_lexicon(None, include_competitor=False, include_chinese=False)
        fc = merged["forbidden_content"]
        assert "cures cancer" in fc
        assert "best on the market" not in fc

    def test_include_chinese_false_excludes_zh_tiers(self):
        merged = merge_medical_lexicon(None, include_chinese=False)
        fc = merged["forbidden_content"]
        assert "cures cancer" in fc
        assert "治疗癌症" not in fc

    def test_only_banned_minimal_mode(self):
        """For low-noise compliance reports, can scope to only BANNED."""
        merged = merge_medical_lexicon(
            None, include_flagged=False, include_competitor=False, include_chinese=False,
        )
        assert merged["forbidden_content"] == MEDICAL_BANNED_CLAIMS


class TestBrandComplianceAutoMerge:
    """Verify BrandComplianceSkill calls merge_medical_lexicon transparently
    (Sprint 3 P3-2 wiring)."""

    @pytest.mark.asyncio
    async def test_blocked_status_triggered_by_medical_claim(self):
        """A script claiming "cures cancer" must hit BLOCKED status even
        when the caller's brand_guidelines didn't include forbidden_content."""
        from src.skills.brand_compliance import BrandComplianceSkill

        skill = BrandComplianceSkill()
        result = await skill.execute({
            "scripts": [{
                "id": "s1",
                "segments": [{"voiceover": "Our miracle product cures cancer in babies!"}],
            }],
            "brand_guidelines": {"brand_name": "X"},
        })
        assert result.success
        reports = result.data["reports"]
        assert reports[0]["status"] == "BLOCKED"
        # Forbidden_content rule fired
        rules = [f["rule"] for f in reports[0]["flags"]]
        assert "forbidden_content" in rules

    @pytest.mark.asyncio
    async def test_clean_script_passes(self):
        from src.skills.brand_compliance import BrandComplianceSkill

        skill = BrandComplianceSkill()
        result = await skill.execute({
            "scripts": [{
                "id": "s1",
                "segments": [{"voiceover": "X bottle for daily comfort. Click to shop."}],
            }],
            "brand_guidelines": {"brand_name": "X"},
        })
        assert result.success
        assert result.data["reports"][0]["status"] == "PASS"

    @pytest.mark.asyncio
    async def test_chinese_medical_claim_blocked(self):
        """Validate ZH tier wired correctly via auto-merge."""
        from src.skills.brand_compliance import BrandComplianceSkill

        skill = BrandComplianceSkill()
        result = await skill.execute({
            "scripts": [{
                "id": "s1",
                "segments": [{"voiceover": "本产品可以治疗癌症"}],
            }],
            "brand_guidelines": {"brand_name": "X"},
        })
        assert result.data["reports"][0]["status"] == "BLOCKED"
