"""Core configuration — loaded from environment and .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Structlog — configure to render kwargs into strings before stdlib sees them.
# Without this, `logger.error("msg", error=...)` raises `Logger._log() got
# an unexpected keyword argument 'error'` because Python's logging.Logger._log
# does not accept arbitrary kwargs.
import logging
import re

import structlog

# Apply LOG_LEVEL to Python's root logger BEFORE structlog.configure runs.
# structlog's `filter_by_level` defers to stdlib level — without this call,
# the root logger defaults to WARNING and every INFO-level log gets silently
# dropped, making long pipelines look "frozen" in production.
_log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logging.basicConfig(level=_log_level, format="%(message)s")
logging.getLogger().setLevel(_log_level)


class _SanitizeProcessor:
    """Redact sensitive values from log events.

    Matches:
    - OpenAI-style keys: sk-xxxxxxxx...
    - Anthropic-style keys: sk-ant-xxx...
    - Generic long tokens (>32 chars, alphanumeric mix)
    - Keys whose field name contains key/token/secret/password/auth.
    """

    _SK_PATTERN = re.compile(r"\bsk-[a-zA-Z0-9_-]+\b")
    _GENERIC_TOKEN = re.compile(r"\b[a-zA-Z0-9_-]{32,}\b")
    _SENSITIVE_KEYS = {"key", "token", "secret", "password", "auth", "apikey", "api_key"}

    def __call__(self, logger, method_name, event_dict):
        for k, v in list(event_dict.items()):
            if not isinstance(v, str):
                continue
            # redact by key name
            if any(s in k.lower() for s in self._SENSITIVE_KEYS):
                event_dict[k] = "[REDACTED]"
                continue
            # redact by value pattern
            v_redacted = self._SK_PATTERN.sub("[REDACTED]", v)
            v_redacted = self._GENERIC_TOKEN.sub("[REDACTED]", v_redacted)
            if v_redacted != v:
                event_dict[k] = v_redacted
        return event_dict


try:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _SanitizeProcessor(),
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
except Exception:
    # Fallback: use KeyValueRenderer if ConsoleRenderer unavailable
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _SanitizeProcessor(),
            structlog.processors.KeyValueRenderer(key_order=["event", "level"]),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", PROJECT_ROOT / "output"))
OUTPUT_DIR.mkdir(exist_ok=True)

# Video target resolution — single source of truth for the entire pipeline
TARGET_VIDEO_WIDTH = 1080
TARGET_VIDEO_HEIGHT = 1920
TARGET_VIDEO_RESOLUTION = f"{TARGET_VIDEO_WIDTH}x{TARGET_VIDEO_HEIGHT}"
TARGET_ASPECT_RATIO = "9:16"

# Mock theme configuration — parametrize mock data instead of hard-coding breast pump
MOCK_PRODUCT_NAME = os.getenv("MOCK_PRODUCT_NAME", "X1")
MOCK_PRODUCT_CATEGORY = os.getenv("MOCK_PRODUCT_CATEGORY", "wearable breast pump")

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek")  # deepseek | anthropic | openai | kimi
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Platform APIs
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Webhook notifications (comma-separated URLs, all registered to all event types)
WEBHOOK_URLS = os.getenv("WEBHOOK_URLS", "")

# Pipeline
DEFAULT_PLATFORMS = ["tiktok", "facebook", "youtube_shorts", "shopify"]
DEFAULT_LANGUAGES = ["en"]
HUMAN_REVIEW_NODES = [
    "strategy_review",
    "script_review",
    "edit_review",
    "thumbnail_review",
]


# ── DeepSeek V4 Pro (native API) ──
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

# ── SiliconFlow CosyVoice TTS ──
SILICONFLOW_API_KEY: str = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_BASE: str = os.environ.get("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
COSYVOICE_MODEL: str = os.environ.get("COSYVOICE_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
COSYVOICE_VOICE: str = os.environ.get("COSYVOICE_VOICE", "FunAudioLLM/CosyVoice2-0.5B:alex")
COSYVOICE_VOICE_FEMALE: str = os.environ.get("COSYVOICE_VOICE_FEMALE", "FunAudioLLM/CosyVoice2-0.5B:anna")

# ── Seedance 2.0 Video Generation ──
# Supports: native Seedance API, or poyo.ai proxy
SEEDANCE_API_KEY: str = os.environ.get("SEEDANCE_API_KEY", "")
SEEDANCE_API_BASE_URL: str = os.environ.get("SEEDANCE_API_BASE_URL", "https://api.seedance.ai")

# poyo.ai fallback (same API format, different provider)
POYO_API_KEY: str = os.environ.get("POYO_API_KEY", "")
POYO_API_BASE_URL: str = os.environ.get("POYO_API_BASE_URL", "https://api.poyo.ai")

# poyo.ai model names (override if provider changes slugs)
POYO_IMAGE_MODEL: str = os.environ.get("POYO_IMAGE_MODEL", "gpt-image-2")
POYO_VIDEO_MODEL: str = os.environ.get("POYO_VIDEO_MODEL", "happy-horse")
POYO_TTS_MODEL: str = os.environ.get("POYO_TTS_MODEL", "generate-music")

# ── Runtime mode ──
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
ALLOW_MOCK_MODE: bool = os.environ.get("ALLOW_MOCK_MODE", "").lower() in ("1", "true", "yes")

# ── Quality checks mode ──
# off: disable all new quality checks (backward compatible)
# observe: run checks and record results in metadata, but do not block pipeline
# enforce: run checks and block pipeline on failure
_quality_mode = os.environ.get("QUALITY_MODE", "observe").lower()
QUALITY_MODE: str = _quality_mode if _quality_mode in ("off", "observe", "enforce") else "observe"

# ═══════════════════════════════════════════════════════════
# Quality check thresholds (all configurable via env vars)
# ═══════════════════════════════════════════════════════════

# Frame variance (seedance_video_generate._check_frame_variance)
FRAME_VARIANCE_MSE_THRESHOLD = float(os.environ.get("FRAME_VARIANCE_MSE_THRESHOLD", "50.0"))
FRAME_VARIANCE_BRIGHTNESS_THRESHOLD = float(os.environ.get("FRAME_VARIANCE_BRIGHTNESS_THRESHOLD", "20.0"))

# AV sync (remotion_assemble._check_av_sync)
AV_SYNC_MAX_ABS_DIFF = float(os.environ.get("AV_SYNC_MAX_ABS_DIFF", "0.5"))
AV_SYNC_MAX_REL_DIFF = float(os.environ.get("AV_SYNC_MAX_REL_DIFF", "0.05"))

# Video specs (media_quality_audit._audit_final_video)
VIDEO_MIN_FPS = float(os.environ.get("VIDEO_MIN_FPS", "25.0"))
VIDEO_CRITICAL_FPS = float(os.environ.get("VIDEO_CRITICAL_FPS", "20.0"))
VIDEO_MIN_BITRATE_KBPS = float(os.environ.get("VIDEO_MIN_BITRATE_KBPS", "1500.0"))
VIDEO_CRITICAL_BITRATE_KBPS = float(os.environ.get("VIDEO_CRITICAL_BITRATE_KBPS", "1000.0"))
VIDEO_ASPECT_RATIO_MIN = float(os.environ.get("VIDEO_ASPECT_RATIO_MIN", "0.53"))
VIDEO_ASPECT_RATIO_MAX = float(os.environ.get("VIDEO_ASPECT_RATIO_MAX", "0.60"))
