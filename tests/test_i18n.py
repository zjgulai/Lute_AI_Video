"""Tests for GAP-12: i18n multi-language support."""

from __future__ import annotations

import asyncio
import pytest

from src.models import Brief, VideoType, Platform, Language, Script
from src.agents.i18n import I18nService
from src.agents.script_writer import ScriptWriterAgent


class TestI18nService:
    """Tests for the i18n service."""

    def test_supported_languages_includes_es_fr_de(self):
        """Supported languages include ES, FR, DE."""
        langs = I18nService.supported_languages()
        for code in ("en", "es", "fr", "de"):
            assert code in langs, f"Missing language: {code}"

    def test_get_prompt_english(self):
        """English prompt module loads correctly."""
        mod = I18nService.get_prompt("script_writer", "en")
        assert mod is not None
        assert hasattr(mod, "SCRIPT_WRITER_SYSTEM_PROMPT_EN") or hasattr(mod, "SCRIPT_WRITER_SYSTEM_PROMPT")
        assert hasattr(mod, "SCRIPT_WRITER_USER_MESSAGE_TEMPLATE") or hasattr(mod, "SCRIPT_WRITER_USER_MESSAGE_TEMPLATE_ES")

    def test_get_prompt_spanish(self):
        """Spanish prompt module loads correctly."""
        mod = I18nService.get_prompt("script_writer", "es")
        assert mod is not None
        # Should have Spanish-specific prompts
        assert hasattr(mod, "SCRIPT_WRITER_SYSTEM_PROMPT_ES") or hasattr(mod, "SCRIPT_WRITER_SYSTEM_PROMPT")

    def test_get_prompt_unknown_lang_falls_back(self):
        """Unknown language falls back to English without error."""
        mod = I18nService.get_prompt("script_writer", "pt")
        assert mod is not None

    def test_get_translated_templates_spanish(self):
        """Spanish templates contain translated BRIEF-001."""
        templates = I18nService.get_translated_templates("es")
        assert templates is not None
        assert "BRIEF-001" in templates
        assert "Extraer" in templates["BRIEF-001"]["hook"]

    def test_get_translated_templates_french(self):
        """French templates contain translated BRIEF-001."""
        templates = I18nService.get_translated_templates("fr")
        assert templates is not None
        assert "BRIEF-001" in templates
        assert "Tirer" in templates["BRIEF-001"]["hook"]

    def test_get_translated_templates_german(self):
        """German templates contain translated BRIEF-001."""
        templates = I18nService.get_translated_templates("de")
        assert templates is not None
        assert "BRIEF-001" in templates
        assert "Abpumpen" in templates["BRIEF-001"]["hook"]

    def test_get_translated_templates_english_is_none(self):
        """English returns None (uses built-in templates directly)."""
        templates = I18nService.get_translated_templates("en")
        assert templates is None

    def test_get_translated_templates_unknown_lang(self):
        """Unknown language returns None (falls back to English)."""
        templates = I18nService.get_translated_templates("pt")
        assert templates is None


class TestTranslatedScripts:
    """Tests that translated templates produce correct Script objects."""

    @pytest.fixture
    def agent(self):
        return ScriptWriterAgent(use_mock=True)

    @pytest.fixture
    def briefs(self):
        return [
            Brief(
                id="BRIEF-001",
                video_type=VideoType.TUTORIAL,
                topic="Clean pump at office",
                target_audience="Working moms",
                target_platforms=[Platform.TIKTOK],
                target_languages=[Language.EN],
                key_message="Discreet cleaning",
                usp_priority=["portable"],
            ),
        ]

    async def test_spanish_scripts_have_es_language(self, agent, briefs):
        """Spanish scripts have Language.ES set."""
        scripts = await agent.run(briefs, {}, target_languages=["es"])
        for s in scripts:
            assert s.language == Language.ES, f"Expected ES, got {s.language}"

    async def test_spanish_scripts_id_suffix(self, agent, briefs):
        """Spanish script IDs end with -ES."""
        scripts = await agent.run(briefs, {}, target_languages=["es"])
        for s in scripts:
            assert s.id.endswith("-ES"), f"Script ID {s.id} doesn't end with -ES"

    async def test_spanish_scripts_translated_voiceover(self, agent, briefs):
        """Spanish voiceover is in Spanish, not English."""
        scripts = await agent.run(briefs, {}, target_languages=["es"])
        for s in scripts:
            # At least one segment should contain Spanish text
            any_spanish = any(
                "Extraer" in seg.voiceover or "esconderse" in seg.voiceover
                for seg in s.segments
            )
            assert any_spanish, f"Spanish voiceover not found in {s.id}"

    async def test_french_scripts_translated_voiceover(self, agent, briefs):
        """French voiceover is in French."""
        scripts = await agent.run(briefs, {}, target_languages=["fr"])
        for s in scripts:
            any_french = any(
                "Tirer" in seg.voiceover or "cacher" in seg.voiceover
                for seg in s.segments
            )
            assert any_french, f"French voiceover not found in {s.id}"

    async def test_german_scripts_translated_voiceover(self, agent, briefs):
        """German voiceover is in German."""
        scripts = await agent.run(briefs, {}, target_languages=["de"])
        for s in scripts:
            any_german = any(
                "Abpumpen" in seg.voiceover or "verstecken" in seg.voiceover
                for seg in s.segments
            )
            assert any_german, f"German voiceover not found in {s.id}"

    async def test_multi_language_generates_all(self, agent, briefs):
        """Requesting all 4 languages returns scripts in each."""
        scripts = await agent.run(
            briefs, {}, target_languages=["en", "es", "fr", "de"]
        )
        langs = {s.language for s in scripts}
        expected = {Language.EN, Language.ES, Language.FR, Language.DE}
        assert langs == expected, f"Got languages {langs}, expected {expected}"

    async def test_unknown_lang_falls_back_to_english(self, agent, briefs):
        """Unknown language code falls back to English content."""
        scripts = await agent.run(briefs, {}, target_languages=["pt"])
        for s in scripts:
            assert s.language == Language.EN  # Enum falls back
            assert s.id.endswith("-PT")  # ID uses the requested code as suffix


class TestCaptionsMultiLang:
    """Captions correctly inherit script language."""

    async def test_caption_inherits_script_language(self):
        """CaptionPlan.language matches Script.language."""
        from src.agents.caption import CaptionAgent
        from src.agents.script_writer import ScriptWriterAgent

        agent = ScriptWriterAgent(use_mock=True)
        briefs = [
            Brief(
                id="BRIEF-001",
                video_type=VideoType.TUTORIAL,
                topic="Test",
                target_audience="Moms",
                target_platforms=[Platform.TIKTOK],
                target_languages=[Language.ES],
                key_message="Test",
                usp_priority=["portable"],
            ),
        ]
        scripts = await agent.run(briefs, {}, target_languages=["es"])
        cap_agent = CaptionAgent()
        plans = await cap_agent.run(scripts)
        for plan in plans:
            assert plan.language == Language.ES, (
                f"Caption language {plan.language} doesn't match script"
            )
