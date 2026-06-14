"""Tests for poyo_safety content moderation sanitizer."""

from __future__ import annotations

import json
from pathlib import Path

from src.tools.poyo_safety import sanitize_for_poyo


def _load_poyo_sanity_samples() -> list[dict]:
    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commercial_video" / "poyo_content_rejection_samples.json"
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return list(payload.get("sanitization_cases", []))


class TestSanitizeForPoyo:
    """Test POYO content moderation substitutions."""

    # ── Core maternal/baby terms (original coverage) ──

    def test_breast_pump_replaced(self):
        text = "A wearable breast pump for moms"
        out, subs = sanitize_for_poyo(text)
        assert "breast pump" not in out.lower()
        assert "wearable wellness device" in out.lower()
        assert len(subs) > 0

    def test_breastfeeding_replaced(self):
        text = "Breastfeeding guide for new mothers"
        out, subs = sanitize_for_poyo(text)
        assert "breastfeeding" not in out.lower()
        assert "feeding" in out.lower()

    def test_lactation_replaced(self):
        text = "Lactation support products"
        out, subs = sanitize_for_poyo(text)
        assert "lactation" not in out.lower()
        assert "wellness" in out.lower()

    # ── Phase 2: Baby bottles / feeding ──

    def test_baby_bottle_replaced(self):
        text = "Baby bottles with anti-colic design"
        out, subs = sanitize_for_poyo(text)
        assert "baby bottle" not in out.lower()
        assert "infant feeding container" in out.lower()

    def test_nipple_replaced(self):
        text = "Soft silicone nipples for bottles"
        out, subs = sanitize_for_poyo(text)
        assert "nipple" not in out.lower()
        assert "feeding tip" in out.lower()

    def test_formula_replaced(self):
        text = "Baby formula milk preparation"
        out, subs = sanitize_for_poyo(text)
        assert "formula milk" not in out.lower()
        assert "prepared nutrition" in out.lower()

    # ── Phase 2: Postpartum / body parts ──

    def test_postpartum_replaced(self):
        text = "Postpartum recovery kit"
        out, subs = sanitize_for_poyo(text)
        assert "postpartum" not in out.lower()
        assert "new parent" in out.lower()

    def test_areola_replaced(self):
        text = "Areola measurement guide"
        out, subs = sanitize_for_poyo(text)
        assert "areola" not in out.lower()
        assert "surface area" in out.lower()

    # ── Chinese terms ──

    def test_chinese_breast_pump_replaced(self):
        text = "便携式吸奶器，适合职场妈妈"
        out, subs = sanitize_for_poyo(text)
        assert "吸奶器" not in out
        assert "可穿戴设备" in out

    def test_chinese_bottle_replaced(self):
        text = "防胀气奶瓶，带硅胶奶嘴"
        out, subs = sanitize_for_poyo(text)
        assert "奶瓶" not in out
        assert "婴儿容器" in out
        assert "奶嘴" not in out
        assert "喂养配件" in out

    def test_chinese_postpartum_replaced(self):
        text = "产后恢复护理套装"
        out, subs = sanitize_for_poyo(text)
        assert "产后" not in out
        assert "恢复期" in out

    # ── Edge cases ──

    def test_empty_string(self):
        out, subs = sanitize_for_poyo("")
        assert out == ""
        assert subs == []

    def test_none_input(self):
        out, subs = sanitize_for_poyo(None)  # type: ignore[arg-type]
        assert out is None
        assert subs == []

    def test_no_triggers_passthrough(self):
        text = "A beautiful sunset over the mountains"
        out, subs = sanitize_for_poyo(text)
        assert out == text
        assert subs == []

    def test_multiple_triggers(self):
        text = "Breast pump and baby bottles for postpartum care"
        out, subs = sanitize_for_poyo(text)
        assert "breast pump" not in out.lower()
        assert "baby bottle" not in out.lower()
        assert "postpartum" not in out.lower()
        assert len(subs) >= 3

    def test_fixture_terms_are_replaced(self):
        for sample in _load_poyo_sanity_samples():
            raw = sample["raw"]
            expected = sample["expected_replacement"]
            out, applied = sanitize_for_poyo(raw)
            assert expected.lower() in out.lower()
            assert sample["trigger"].lower() not in out.lower()
            assert applied
