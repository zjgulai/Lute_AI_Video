"""Tests for Caption → Thumbnail feature propagation.

Verifies that ThumbnailAgent receives caption_plans and injects visual
emphasis signals (highlighted text, CTA phrases, key phrases) into the
DALL-E prompts it generates.
"""

import pytest
from src.models import (
    Script, ScriptSegment, Platform, Language,
    CaptionPlan, CaptionEntry,
)
from src.agents.thumbnail import _propagate_caption_signals
from typing import Any


# ── Unit: _propagate_caption_signals ──

def _make_caption_plan(
    script_id: str = "SCRIPT-TEST-001",
    entries: list[Any] | None = None,
) -> CaptionPlan:
    if entries is None:
        entries = [
            CaptionEntry(index=0, start_time=0.0, end_time=2.0, text="Hello world", style="default"),
            CaptionEntry(index=1, start_time=2.0, end_time=4.0, text="Focus this word", style="highlight"),
            CaptionEntry(index=2, start_time=4.0, end_time=6.0, text="Shop now", style="cta"),
        ]
    return CaptionPlan(
        script_id=script_id,
        language=Language.EN,
        entries=entries,
    )


class TestPropagateCaptionSignals:
    """Unit tests for _propagate_caption_signals."""

    def test_extracts_highlight_texts(self):
        plans = [_make_caption_plan()]
        signals = _propagate_caption_signals(plans, "SCRIPT-TEST-001")
        assert "Focus this word" in signals["highlight_texts"]
        assert signals["has_visual_emphasis"] is True

    def test_extracts_cta_texts(self):
        plans = [_make_caption_plan()]
        signals = _propagate_caption_signals(plans, "SCRIPT-TEST-001")
        assert "Shop now" in signals["cta_texts"]

    def test_extracts_key_phrases(self):
        plans = [_make_caption_plan()]
        signals = _propagate_caption_signals(plans, "SCRIPT-TEST-001")
        assert "Hello world" in signals["key_phrases"]
        assert "Focus this word" in signals["key_phrases"]

    def test_no_highlight_when_no_caption_plans(self):
        signals = _propagate_caption_signals([], "SCRIPT-TEST-001")
        assert signals["has_visual_emphasis"] is False
        assert signals["highlight_texts"] == []

    def test_ignores_non_matching_script_id(self):
        plans = [_make_caption_plan()]
        signals = _propagate_caption_signals(plans, "SCRIPT-OTHER-999")
        assert signals["has_visual_emphasis"] is False

    def test_skips_empty_text_entries(self):
        plans = [
            _make_caption_plan(
                entries=[
                    CaptionEntry(index=0, start_time=0.0, end_time=1.0, text="", style="highlight"),
                    CaptionEntry(index=1, start_time=1.0, end_time=2.0, text="Real text", style="highlight"),
                    CaptionEntry(index=2, start_time=2.0, end_time=3.0, text="  ", style="cta"),
                ]
            )
        ]
        signals = _propagate_caption_signals(plans, "SCRIPT-TEST-001")
        assert "" not in signals["highlight_texts"]
        assert "Real text" in signals["highlight_texts"]
        assert signals["has_visual_emphasis"] is True

    def test_caps_lists_to_prevent_prompt_overflow(self):
        many_highlights = [
            CaptionEntry(index=i, start_time=float(i), end_time=float(i + 1),
                         text=f"Highlight {i}", style="highlight")
            for i in range(10)
        ]
        plans = [_make_caption_plan(entries=many_highlights)]
        signals = _propagate_caption_signals(plans, "SCRIPT-TEST-001")
        assert len(signals["highlight_texts"]) <= 3
        assert len(signals["key_phrases"]) <= 5

    def test_multiple_caption_plans_only_matches_target(self):
        plans = [
            _make_caption_plan(script_id="SCRIPT-ALPHA-001"),
            _make_caption_plan(script_id="SCRIPT-BETA-001"),
        ]
        signals = _propagate_caption_signals(plans, "SCRIPT-BETA-001")
        assert "Focus this word" in signals["highlight_texts"]


# ── Integration: ThumbnailAgent._build_prompt ──

class TestBuildPromptWithCaptionSignals:
    """Tests that ThumbnailAgent._build_prompt injects caption signals properly."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.agents.thumbnail import ThumbnailAgent
        self.agent = ThumbnailAgent(use_mock=True)
        self.base_concept = {"concept": "Test", "style": "test_style"}
        self.hook = "Best pump ever"
        self.concept = {"concept": "Product centered + bold title", "style": "clean_ecom"}

    def test_no_signals_prompt_is_unchanged(self):
        prompt = self.agent._build_prompt(self.concept, self.hook, {})
        assert "Caption highlights" not in prompt
        assert "Key phrases" not in prompt
        assert "Best pump ever" in prompt
        assert "clean_ecom" in prompt

    def test_highlight_signals_injected(self):
        signals = {
            "has_visual_emphasis": True,
            "highlight_texts": ["Focus on comfort"],
            "cta_texts": [],
            "key_phrases": ["Best pump ever", "Comfort matters"],
        }
        prompt = self.agent._build_prompt(self.concept, self.hook, signals)
        assert "Focus on comfort" in prompt
        assert "Comfort matters" in prompt

    def test_cta_signals_injected(self):
        signals = {
            "has_visual_emphasis": True,
            "highlight_texts": [],
            "cta_texts": ["Shop now at link"],
            "key_phrases": [],
        }
        prompt = self.agent._build_prompt(self.concept, self.hook, signals)
        assert "Shop now at link" in prompt

    def test_full_signals_in_prompt(self):
        signals = {
            "has_visual_emphasis": True,
            "highlight_texts": ["Quiet as a whisper", "Hands-free design"],
            "cta_texts": ["Get yours today"],
            "key_phrases": ["Best pump ever", "No more pain"],
        }
        prompt = self.agent._build_prompt(self.concept, self.hook, signals)
        assert "Quiet as a whisper" in prompt
        assert "Hands-free design" in prompt
        assert "Get yours today" in prompt
        assert "No more pain" in prompt
        assert "Caption highlights:" in prompt
        assert "CTA:" in prompt
        assert "Key phrases:" in prompt


# ── E2E: thumbnail_node with caption_plans ──

class TestThumbnailNodeCaptionPropagation:
    """E2E test: thumbnail_node receives caption_plans and propagates them."""

    @pytest.fixture
    def script(self):
        return Script(
            id="SCRIPT-PROP-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=30.0,
            segments=[
                ScriptSegment(
                    segment_type="hook", start_time=0.0, end_time=3.0,
                    voiceover="This pump changes everything.",
                    visual_description="Hook", text_overlay="",
                ),
                ScriptSegment(
                    segment_type="pain_point", start_time=3.0, end_time=8.0,
                    voiceover="Tired of leaking.",
                    visual_description="Pain", text_overlay="",
                ),
                ScriptSegment(
                    segment_type="solution", start_time=8.0, end_time=20.0,
                    voiceover="Our pump is hands-free.",
                    visual_description="Demo", text_overlay="",
                ),
                ScriptSegment(
                    segment_type="trust_building", start_time=20.0, end_time=25.0,
                    voiceover="Trusted by 10k moms.",
                    visual_description="Trust", text_overlay="",
                ),
                ScriptSegment(
                    segment_type="cta", start_time=25.0, end_time=30.0,
                    voiceover="Link in bio.",
                    visual_description="CTA", text_overlay="",
                ),
            ],
            hashtags=["#parenting"],
            cta_text="Link in bio",
        )

    @pytest.fixture
    def caption_plans(self):
        return [
            CaptionPlan(
                script_id="SCRIPT-PROP-001",
                language=Language.EN,
                entries=[
                    CaptionEntry(index=0, start_time=0.0, end_time=2.0,
                                 text="This pump changes everything", style="highlight"),
                    CaptionEntry(index=1, start_time=2.0, end_time=3.0,
                                 text="changes everything", style="highlight"),
                    CaptionEntry(index=2, start_time=25.0, end_time=30.0,
                                 text="Link in bio", style="cta"),
                ],
            )
        ]

    # @pytest.mark.skip - reactivated for P0-C fix
    @pytest.mark.asyncio
    async def test_thumbnail_propagation_with_mock_returns_4_variants(self, script, caption_plans):
        """ThumbnailAgent(use_mock=True) 接收 caption_plans 不报错,返回 4 个 variants。

        mock 模式下产出固定模板,不会真把 caption 内容塞进 prompt。
        真实 caption signal 注入的端到端验证在 use_mock=False 模式,
        需要真 POYO/DALL-E key,放到 manual e2e。
        本测试只验证 propagation 入参不破坏管线。
        """
        from src.agents.thumbnail import ThumbnailAgent

        agent = ThumbnailAgent(use_mock=True)
        sets = await agent.run(scripts=[script], caption_plans=caption_plans)

        assert len(sets) == 1
        assert len(sets[0].variants) == 4

        for variant in sets[0].variants:
            assert variant.prompt, "mock 模板不应该返回空 prompt"

    # @pytest.mark.skip - reactivated
    @pytest.mark.asyncio
    async def test_no_caption_plans_does_not_inject_caption_markers(self, script):
        """不传 caption_plans 时,prompt 内不应该出现 'Caption highlights:' / 'CTA:' 注入标记。"""
        from src.agents.thumbnail import ThumbnailAgent

        agent = ThumbnailAgent(use_mock=True)
        sets = await agent.run(scripts=[script])

        assert len(sets) == 1
        for variant in sets[0].variants:
            prompt = variant.prompt
            # 不传 caption_plans 时,注入标记不应该出现
            assert "Caption highlights:" not in prompt
            assert "CTA:" not in prompt
            # mock 模板有稳定 style 关键词
            assert any(kw in prompt for kw in ["minimalist", "clean ecom", "9:16", "text overlay"]), (
                f"mock 模板字段缺失: {prompt[:100]}"
            )
