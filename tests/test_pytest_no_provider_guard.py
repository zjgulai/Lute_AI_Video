"""Guards that pytest cannot inherit provider keys from local .env files."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "tests" / "conftest.py"

PROVIDER_KEYS = (
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


def test_pytest_conftest_shadows_provider_keys_before_dotenv_load():
    text = CONFTEST.read_text()

    assert "Pytest must stay hermetic by default" in text
    for key in PROVIDER_KEYS:
        assert f'"{key}"' in text
    assert 'os.environ[_provider_key] = ""' in text


def test_pytest_runtime_provider_keys_default_empty():
    assert os.environ.get("ALLOW_MOCK_MODE") == "1"
    assert os.environ.get("RUN_TOKEN_SMOKE") == "0"
    for key in PROVIDER_KEYS:
        assert os.environ.get(key, "") == ""
