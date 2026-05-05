"""Unit tests for CaptionAgent — degradation guards and output quality."""

import pytest

from src.agents.caption import CaptionAgent
from src.models import Script, ScriptSegment, CaptionPlan, Platform, Language, Script


@pytest.fixture
def caption_agent():
    return CaptionAgent()


@pytest.fixture
def clean_script():
    """Script with natural language voiceover — should generate captions."""
    return Script(
        id="SCRIPT-CLEAN-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=10.0,
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0, end_time=3.0,
                voiceover="Pumping at work doesn't have to mean hiding in a supply closet.",
                visual_description="Woman at desk",
                text_overlay="Clean in 2 min?",
            ),
        ],
    )


@pytest.fixture
def placeholder_script():
    """Script with bracketed placeholder voiceover — should be skipped by caption."""
    return Script(
        id="SCRIPT-PLACEHOLDER-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=10.0,
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0, end_time=3.0,
                voiceover="[HOOK for: How to clean wearable pump at office]",
                visual_description="Opening hook shot",
                text_overlay="",
            ),
            ScriptSegment(
                segment_type="pain_point",
                start_time=3.0, end_time=8.0,
                voiceover="[Pain point expansion — describe the struggle]",
                visual_description="Pain point visual scene",
                text_overlay="",
            ),
        ],
    )


@pytest.fixture
def mixed_script():
    """Mixed: first segment is placeholder, second is natural language."""
    return Script(
        id="SCRIPT-MIXED-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=10.0,
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0, end_time=3.0,
                voiceover="[HOOK: placeholder text]",
                visual_description="Placeholder",
                text_overlay="",
            ),
            ScriptSegment(
                segment_type="solution",
                start_time=3.0, end_time=10.0,
                voiceover="The X1 fits in your bra and nobody knows you're pumping.",
                visual_description="Product demo",
                text_overlay="100% hands-free",
            ),
        ],
    )


class TestCaptionDegradationGuard:
    """Tests for L2.5: caption agent should not generate subtitles from placeholder text."""

    @pytest.mark.asyncio
    async def test_clean_script_generates_captions(self, caption_agent, clean_script):
        """Natural language voiceover should produce caption entries normally."""
        plans = await caption_agent.run([clean_script])
        assert len(plans) == 1
        assert len(plans[0].entries) > 0
        # Entries should be actual words, not brackets
        assert all(not e.text.startswith("[") for e in plans[0].entries)
        assert all(len(e.text.strip()) > 0 for e in plans[0].entries)

    @pytest.mark.asyncio
    async def test_placeholder_script_skips_bracketed_segments(self, caption_agent, placeholder_script):
        """ALL segments are bracketed placeholders → zero caption entries."""
        plans = await caption_agent.run([placeholder_script])
        assert len(plans) == 1
        # Every segment is a bracketed placeholder, so captions should be empty
        assert len(plans[0].entries) == 0, (
            f"Expected 0 caption entries for bracketed voiceover, got {len(plans[0].entries)}"
        )

    @pytest.mark.asyncio
    async def test_mixed_script_skips_only_placeholder(self, caption_agent, mixed_script):
        """Only bracketed segments are skipped; natural segments still produce captions."""
        plans = await caption_agent.run([mixed_script])
        assert len(plans) == 1
        entries = plans[0].entries
        assert len(entries) > 0, "Should have captions from the natural-language segment"
        # Verify no caption entry contains bracket syntax
        for entry in entries:
            assert "[" not in entry.text, f"Caption contains bracket: {entry.text}"
            assert "]" not in entry.text, f"Caption contains bracket: {entry.text}"
        # Verify time ranges fall within the non-placeholder segment (3.0–10.0s)
        for entry in entries:
            assert entry.start_time >= 3.0, f"Caption starts before natural segment: {entry.start_time}"
            assert entry.end_time <= 10.0, f"Caption ends after natural segment: {entry.end_time}"

    @pytest.mark.asyncio
    async def test_clean_output_has_complete_sentences(self, caption_agent, clean_script):
        """Captions should be natural word sequences, not '[HOOK' fragments."""
        plans = await caption_agent.run([clean_script])
        entries = plans[0].entries
        all_text = " ".join(e.text for e in entries)
        # No leftover bracket artifacts
        assert "[" not in all_text and "]" not in all_text
        # At least one entry should be a multi-word phrase
        assert any(len(e.text.split()) >= 3 for e in entries), "No multi-word captions"
