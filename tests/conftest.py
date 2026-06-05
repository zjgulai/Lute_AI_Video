"""Test fixtures shared across all test modules."""

import os

# 测试环境固定 API_KEY,避免每次 import src.routers._deps 时随机生成
# 导致请求 header 与 verify_api_key 比对失败。设在文件最顶部以保证
# src.api / src.routers 在测试 import 时拿到稳定的 API_KEY。
os.environ.setdefault("API_KEY", "test-api-key-for-pytest")
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_MOCK_MODE"] = "1"
os.environ["RUN_TOKEN_SMOKE"] = "0"

PROVIDER_KEY_ENV_NAMES = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ADMIN_KEY",
    "ANTHROPIC_API_KEY",
    "KIMI_API_KEY",
    "POYO_API_KEY",
    "SEEDANCE_API_KEY",
    "SILICONFLOW_API_KEY",
    "ELEVENLABS_API_KEY",
)

# Pytest must stay hermetic by default. src.config calls load_dotenv(), so these
# empty values intentionally shadow any local .env provider keys before app
# modules import configuration.
for _provider_key in PROVIDER_KEY_ENV_NAMES:
    os.environ[_provider_key] = ""

# ADR-004 Option D: production default is disabled. Tests that need the
# live path either patch the flag explicitly or rely on this default-off.
os.environ.setdefault("S3_VIRAL_EXTRACT_DISABLED", "0")

from unittest.mock import AsyncMock, MagicMock

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Default to the fast hermetic subset unless the caller opts into slow tests.

    `PYTEST_INCLUDE_HERMETIC_SLOW=1` keeps historical behavior for full local
    regression runs. An explicit `-m ...` also wins over this default.
    """
    if os.getenv("PYTEST_INCLUDE_HERMETIC_SLOW") == "1":
        return
    if not config.option.markexpr:
        config.option.markexpr = "not hermetic_slow"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """X-API-Key 请求头,所有需要鉴权的测试用这个 fixture。"""
    return {"X-API-Key": os.environ["API_KEY"]}


@pytest.fixture
def auditor():
    from src.agents.auditor import AuditorAgent
    return AuditorAgent()


@pytest.fixture(autouse=True)
def _isolate_provider_test_context(monkeypatch):
    """Keep provider credentials and request-scoped keys out of default tests."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ALLOW_MOCK_MODE", "1")
    monkeypatch.setenv("RUN_TOKEN_SMOKE", "0")
    for provider_key in PROVIDER_KEY_ENV_NAMES:
        monkeypatch.setenv(provider_key, "")

    request_token = None
    try:
        from src.tools.llm_client import _request_api_keys
    except ImportError:
        _request_api_keys = None
    if _request_api_keys is not None:
        request_token = _request_api_keys.set({})

    yield

    if _request_api_keys is not None and request_token is not None:
        _request_api_keys.reset(request_token)
    for provider_key in PROVIDER_KEY_ENV_NAMES:
        os.environ[provider_key] = ""


@pytest.fixture(autouse=True)
def _reset_asyncpg_pool():
    """每个 test 前重置 asyncpg pool 单例。

    pytest-asyncio 默认给每个 test 新建 event loop,但 src/storage/db.py
    的 _pool 是 module-level 全局,会绑定到旧 event loop,在第二个 test 里
    复用就抛 `RuntimeError: Event loop is closed`。

    用 sync fixture(不要 async),否则会污染所有 sync test 强制要求 event loop。
    test 结束让 GC + asyncpg 自己处理 cleanup。
    """
    try:
        from src.storage import db as _db_mod
    except ImportError:
        yield
        return

    _db_mod._pool = None
    yield
    _db_mod._pool = None


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """每个 test 给 PipelineStateManager 一个独立 tmp 目录,避免污染 output/。"""
    from src.pipeline.state_manager import PipelineStateManager

    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(PipelineStateManager, "__init__", lambda self, use_pg=False: None)
    monkeypatch.setattr(PipelineStateManager, "use_pg", False, raising=False)
    yield tmp_path


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
    from src.models import Brief, Language, Platform, VideoType

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
    from src.models import Language, Platform, Script, ScriptSegment

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


@pytest.fixture
def sample_good_script(sample_script):
    """Alias for sample_script — same structure, used by auditor quality tests."""
    return sample_script


@pytest.fixture(scope="session")
def sample_videos(tmp_path_factory):
    """Generate sample videos for quality-check tests via ffmpeg."""
    out = tmp_path_factory.mktemp("videos")
    import subprocess

    videos = {}

    # Black screen video (3s, 720x1280)
    black = out / "black.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=3",
         "-pix_fmt", "yuv420p", "-an", str(black)],
        capture_output=True, check=True,
    )
    videos["black"] = black

    # Truly static video (3s, all frames identical pure-red)
    static = out / "static.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=720x1280:d=3",
         "-pix_fmt", "yuv420p", "-an", str(static)],
        capture_output=True, check=True,
    )
    videos["static"] = static

    # Normal motion video (3s, 30fps)
    normal = out / "normal.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=720x1280:rate=30",
         "-pix_fmt", "yuv420p", "-an", str(normal)],
        capture_output=True, check=True,
    )
    videos["normal"] = normal

    # Video with audio track (for av_sync test)
    with_audio = out / "with_audio.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=720x1280:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
         "-pix_fmt", "yuv420p", "-shortest", str(with_audio)],
        capture_output=True, check=True,
    )
    videos["with_audio"] = with_audio

    return videos
