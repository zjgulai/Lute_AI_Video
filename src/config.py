"""Core configuration — loaded from environment and .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Structlog — configure to render kwargs into strings before stdlib sees them.
# Without this, `logger.error("msg", error=...)` raises `Logger._log() got
# an unexpected keyword argument 'error'` because Python's logging.Logger._log
# does not accept arbitrary kwargs.
import structlog

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

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "anthropic")  # anthropic | openai | kimi
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Redis / Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

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


# ── Seedance 2.0 Video Generation ──
# Supports: native Seedance API, or poyo.ai proxy
SEEDANCE_API_KEY: str = os.environ.get("SEEDANCE_API_KEY", "")
SEEDANCE_API_BASE_URL: str = os.environ.get("SEEDANCE_API_BASE_URL", "https://api.seedance.ai")

# poyo.ai fallback (same API format, different provider)
POYO_API_KEY: str = os.environ.get("POYO_API_KEY", "")
POYO_API_BASE_URL: str = os.environ.get("POYO_API_BASE_URL", "https://api.poyo.ai")

# poyo.ai model names (override if provider changes slugs)
POYO_IMAGE_MODEL: str = os.environ.get("POYO_IMAGE_MODEL", "gpt-image-2")
POYO_TTS_MODEL: str = os.environ.get("POYO_TTS_MODEL", "generate-music")
