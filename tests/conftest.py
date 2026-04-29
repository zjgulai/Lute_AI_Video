"""Test fixtures shared across all test modules."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """Mock LLM client that returns controlled JSON responses."""
    mock = MagicMock()
    mock.invoke_json = AsyncMock()
    mock.invoke = AsyncMock()
    return mock


@pytest.fixture
def sample_product_catalog():
    """Minimal product catalog for testing."""
    return {
        "products": [
            {
                "name": "Wearable Breast Pump X1",
                "usps": [
                    {"priority": "P0", "text": "Hands-free, fits in bra"},
                    {"priority": "P0", "text": "Hospital-grade suction, 280mmHg"},
                    {"priority": "P1", "text": "Quiet operation, <40dB"},
                    {"priority": "P1", "text": "FDA cleared"},
                ],
                "specs": {
                    "weight": "220g",
                    "battery_life": "2.5 hours",
                    "noise_level": "<40dB",
                    "capacity": "150ml per side",
                },
                "certifications": ["FDA", "CE"],
            }
        ]
    }


@pytest.fixture
def sample_brand_guidelines():
    """Minimal brand guidelines for testing."""
    return {
        "brand_name": "TestBrand",
        "tone_of_voice": {
            "archetype": "Caregiver",
            "keywords": ["warm", "empowering", "real", "professional"],
            "do_examples": [
                "You deserve to pump without being chained to a wall.",
                "Freedom to feed, wherever life takes you.",
            ],
            "dont_examples": [
                "Don't let your baby suffer from formula!",
                "Other pumps are garbage.",
            ],
        },
        "colors": {"primary": "#FF6B9D", "secondary": "#2D3436"},
        "compliance": {
            "forbidden_claims": ["cures", "treats mastitis", "prevents all clogs"],
            "required_disclaimers": ["Individual results may vary."],
        },
    }


@pytest.fixture
def sample_brief():
    """A single brief for unit testing downstream nodes."""
    from src.models import Brief, VideoType, Platform, Language

    return Brief(
        id="BRIEF-001",
        video_type=VideoType.TUTORIAL,
        topic="How to clean wearable pump at the office",
        target_audience="Working moms 25-35",
        target_platforms=[Platform.TIKTOK],
        target_languages=[Language.EN],
        key_message="Discreet cleaning in 2 minutes",
        usp_priority=["portable", "quiet", "easy-clean"],
    )


@pytest.fixture
def sample_script(sample_brief):
    """A sample script for testing downstream nodes."""
    from src.models import Script, ScriptSegment, Platform, Language

    return Script(
        id="SCRIPT-BRIEF-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=45.0,
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0,
                end_time=3.0,
                voiceover="Pumping at work shouldn't feel like hiding in a bathroom stall.",
                visual_description="Split screen: frustrated woman at desk vs bathroom door",
                text_overlay="Pumping at work?",
            ),
            ScriptSegment(
                segment_type="pain_point",
                start_time=3.0,
                end_time=8.0,
                voiceover="3 times a day. 20 minutes each. In a supply closet.",
                visual_description="Woman checking watch, pump bag visible",
                text_overlay="3x a day. 20 min each.",
            ),
            ScriptSegment(
                segment_type="solution",
                start_time=8.0,
                end_time=20.0,
                voiceover="The X1 fits in your bra. Silent. Nobody knows you're pumping.",
                visual_description="Product demo: wearing X1 under blouse at desk",
                text_overlay="100% hands-free",
            ),
            ScriptSegment(
                segment_type="trust_building",
                start_time=20.0,
                end_time=35.0,
                voiceover="Hospital-grade suction. FDA cleared. 2.5 hour battery.",
                visual_description="Specs overlay on product close-up",
                text_overlay="FDA Cleared | 280mmHg",
            ),
            ScriptSegment(
                segment_type="cta",
                start_time=35.0,
                end_time=45.0,
                voiceover="Freedom to feed, wherever you are. Link in bio.",
                visual_description="Product in use, warm lighting, mom smiling",
                text_overlay="Shop Now ↑",
            ),
        ],
        hashtags=["#breastpumping", "#workingmom", "#wearablepump"],
        cta_text="Shop the link in bio",
    )
