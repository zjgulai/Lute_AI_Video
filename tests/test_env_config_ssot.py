"""Static guard for canonical provider configuration defaults."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_CONFIG = REPO_ROOT / "src" / "config.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
RENDER_YAML = REPO_ROOT / "render.yaml"
CLOUDBASE_DOCS = [
    REPO_ROOT / "deploy" / "tencent-cloudbase.md",
    REPO_ROOT / "deploy" / "CLOUDBASE_STEP_BY_STEP.md",
]

CANONICAL_DEFAULTS = {
    "DEFAULT_LLM_PROVIDER": "deepseek",
    "DEEPSEEK_API_BASE": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-pro",
    "POYO_API_BASE_URL": "https://api.poyo.ai",
    "POYO_IMAGE_MODEL": "gpt-image-2",
    "POYO_VIDEO_MODEL": "seedance-2",
}


def _config_fallbacks() -> dict[str, str]:
    text = SRC_CONFIG.read_text()
    fallbacks: dict[str, str] = {}

    for key in CANONICAL_DEFAULTS:
        pattern = rf'{key}\s*(?::\s*str)?\s*=\s*os\.(?:getenv|environ\.get)\("{key}",\s*"([^"]+)"\)'
        match = re.search(pattern, text)
        assert match, f"{key} must have an explicit fallback in src/config.py"
        fallbacks[key] = match.group(1)

    return fallbacks


def _env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.split("#", 1)[0].strip()
    return values


def _render_env_values() -> dict[str, str]:
    render = yaml.safe_load(RENDER_YAML.read_text())
    services = render.get("services") or []
    assert services, "render.yaml must define at least one service"
    env_vars = services[0].get("envVars") or []
    return {
        item["key"]: item.get("value", "")
        for item in env_vars
        if isinstance(item, dict) and "key" in item
    }


def test_src_config_fallbacks_are_canonical():
    assert _config_fallbacks() == CANONICAL_DEFAULTS


def test_env_example_matches_src_config_provider_defaults():
    env_values = _env_example_values()
    for key, expected in CANONICAL_DEFAULTS.items():
        assert env_values.get(key) == expected, f".env.example {key} drifted from src/config.py"


def test_render_blueprint_declares_non_secret_provider_defaults():
    render_values = _render_env_values()
    for key, expected in CANONICAL_DEFAULTS.items():
        assert render_values.get(key) == expected, f"render.yaml {key} must mirror src/config.py"


def test_cloudbase_docs_mirror_provider_defaults():
    for doc_path in CLOUDBASE_DOCS:
        text = doc_path.read_text()
        for key, expected in CANONICAL_DEFAULTS.items():
            assert f"`{key}`" in text, f"{doc_path} must document {key}"
            assert f"`{expected}`" in text, f"{doc_path} must document {key}={expected}"
