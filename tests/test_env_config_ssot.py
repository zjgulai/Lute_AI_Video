"""Static guard for canonical provider configuration defaults."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_CONFIG = REPO_ROOT / "src" / "config.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
RENDER_YAML = REPO_ROOT / "render.yaml"
CONTRACT_FILE = REPO_ROOT / "configs" / "env-example-no-secret-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "env-example-no-secret-drift.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CLOUDBASE_DOCS = [
    REPO_ROOT / "deploy" / "tencent-cloudbase.md",
    REPO_ROOT / "deploy" / "CLOUDBASE_STEP_BY_STEP.md",
]
ACTIVE_ENV_DOCS = [
    ENV_EXAMPLE,
    REPO_ROOT / "deploy" / "tencent-cloudbase.md",
    REPO_ROOT / "deploy" / "CLOUDBASE_STEP_BY_STEP.md",
    REPO_ROOT / "deploy" / "local-run.md",
    REPO_ROOT / "docs" / "knowledge" / "local-vs-production-stable.md",
    REPO_ROOT / "docs" / "workflows" / "deploy-lighthouse-stable.md",
    REPO_ROOT / "docs" / "workflows" / "deploy-test-sop-stable.md",
    REPO_ROOT / "docs" / "runbooks" / "p2-recharge-smoke-checklist.md",
    REPO_ROOT / "docs" / "runbooks" / "production-e2e-token-smoke.md",
]

CANONICAL_DEFAULTS = {
    "DEFAULT_LLM_PROVIDER": "deepseek",
    "DEEPSEEK_API_BASE": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-pro",
    "POYO_API_BASE_URL": "https://api.poyo.ai",
    "POYO_IMAGE_MODEL": "gpt-image-2",
    "POYO_VIDEO_MODEL": "seedance-2",
}
SENSITIVE_NAME_RE = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD)\b|(?:KEY|TOKEN|SECRET|PASSWORD)_")
SECRET_LIKE_VALUE_RE = re.compile(
    r"\b(?:"
    r"sk-(?!your-|test\b|ant-test\b)[A-Za-z0-9_-]{12,}|"
    r"poyo_[A-Za-z0-9_-]{16,}|"
    r"sf-[A-Za-z0-9_-]{12,}|"
    r"[A-Za-z0-9_-]{40,}"
    r")\b"
)
ALLOWED_EXAMPLE_SECRET_VALUES = {
    "",
    "0",
    "sk-your-deepseek-key",
    "sk-your-poyo-key",
    "sk-your-siliconflow-key",
    "local-dev-api-key-change-me",
    "ai_video_demo_2026",
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


def _config_sensitive_fallbacks() -> dict[str, str]:
    text = SRC_CONFIG.read_text()
    fallbacks: dict[str, str] = {}
    pattern = re.compile(
        r'([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)'
        r'(?:\s*:\s*str)?\s*=\s*os\.(?:getenv|environ\.get)'
        r'\("([A-Z][A-Z0-9_]*)",\s*"([^"]*)"\)'
    )
    for variable_name, env_name, fallback in pattern.findall(text):
        assert variable_name == env_name, f"{variable_name} should read same-named env var"
        fallbacks[env_name] = fallback
    return fallbacks


def _strip_allowed_placeholders(text: str) -> str:
    stripped = text
    placeholder_patterns = [
        r"<[^>\n]*(?:key|token|secret)[^>\n]*>",
        r"\$[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*",
        r"\$\{[^}\n]*(?:KEY|TOKEN|SECRET|PASSWORD)[^}\n]*\}",
        r"sk-your-[A-Za-z0-9_-]+",
        r"sk-test\b",
        r"sk-ant-test\b",
        r"ai_video_demo_2026",
        r"local-dev-api-key-change-me",
        r"test-api-key-for-pytest",
        r"prod-api-key",
        r"poyo-key",
        r"deepseek-key",
        r"siliconflow-key",
        r"\[redacted\]",
        r"_{8,}",
    ]
    for pattern in placeholder_patterns:
        stripped = re.sub(pattern, "[placeholder]", stripped, flags=re.IGNORECASE)
    return stripped


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


def test_env_example_sensitive_values_are_placeholders_only():
    env_values = _env_example_values()
    sensitive_items = {
        key: value
        for key, value in env_values.items()
        if SENSITIVE_NAME_RE.search(key)
    }
    assert sensitive_items, ".env.example must expose expected sensitive placeholders"

    for key, value in sensitive_items.items():
        assert value in ALLOWED_EXAMPLE_SECRET_VALUES, (
            f".env.example {key} must be empty, demo/test, or placeholder-only; got {value!r}"
        )
        assert not SECRET_LIKE_VALUE_RE.search(value), (
            f".env.example {key} looks like a real secret: {value!r}"
        )


def test_src_config_sensitive_env_fallbacks_are_empty():
    sensitive_fallbacks = _config_sensitive_fallbacks()
    assert sensitive_fallbacks, "src/config.py sensitive env fallbacks should be discoverable"
    for key, fallback in sensitive_fallbacks.items():
        assert fallback == "", f"src/config.py {key} fallback must be empty, got {fallback!r}"


def test_active_env_docs_do_not_embed_real_secrets():
    for doc_path in ACTIVE_ENV_DOCS:
        sensitive_lines = [
            line
            for line in doc_path.read_text().splitlines()
            if SENSITIVE_NAME_RE.search(line)
        ]
        text = _strip_allowed_placeholders("\n".join(sensitive_lines))
        matches = SECRET_LIKE_VALUE_RE.findall(text)
        assert not matches, f"{doc_path} appears to contain real secret-like values: {matches[:3]}"


def test_env_no_secret_contract_and_runbook_are_documented():
    contract = CONTRACT_FILE.read_text()
    runbook = RUNBOOK_FILE.read_text()
    scope_targets = DOCS_LINK_SCOPE.read_text().splitlines()

    for token in [
        "env_example_sensitive_values_placeholder_only",
        "src_config_sensitive_fallbacks_empty",
        "active_deploy_env_docs_no_real_secrets",
        "no_gitignored_prod_env_scan",
    ]:
        assert token in contract

    for token in [
        "pytest tests/test_env_config_ssot.py",
        ".env.example",
        "deploy/lighthouse/.env.prod",
        "不读取真实生产 secret",
    ]:
        assert token in runbook

    assert "docs/runbooks/env-example-no-secret-drift.md" in scope_targets
