"""No-secret guard for the public /health endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "configs" / "health-endpoint-no-secret-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "health-endpoint-no-secret.md"
DOCS_LINK_SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

SECRET_VALUES = {
    "POYO_API_KEY": "poyo_live_secret_for_health_guard",
    "DEEPSEEK_API_KEY": "deepseek_live_secret_for_health_guard",
    "SILICONFLOW_API_KEY": "siliconflow_live_secret_for_health_guard",
    "MEDIA_SIGN_SECRET": "media_sign_secret_for_health_guard",
    "DATABASE_URL": "postgresql://prod_user:prod_password@db.internal:5432/ai_video",
}


@pytest.mark.asyncio
async def test_health_payload_sanitizes_secret_values_and_internal_paths(monkeypatch):
    import src.tools.remotion_renderer as remotion_module
    from src.routers import health as health_router
    from src.storage import db as db_module

    for key, value in SECRET_VALUES.items():
        monkeypatch.setenv(key, value)

    async def fake_check_pg_health():
        return {
            "backend": "postgresql",
            "status": "connection_error",
            "error": (
                f"failed dsn {SECRET_VALUES['DATABASE_URL']} "
                f"key {SECRET_VALUES['POYO_API_KEY']} "
                f"path {REPO_ROOT}/output/ai_video.db"
            ),
        }

    class FakeRemotionRenderer:
        def validate_environment(self):
            return {
                "available": False,
                "node_version": None,
                "remotion_version": None,
                "render_script_exists": False,
                "node_modules_exist": False,
                "issues": [
                    f"Render script not found at {REPO_ROOT}/rendering/src/render.ts",
                    f"DEEPSEEK_API_KEY={SECRET_VALUES['DEEPSEEK_API_KEY']}",
                    f"MEDIA_SIGN_SECRET={SECRET_VALUES['MEDIA_SIGN_SECRET']}",
                ],
            }

    monkeypatch.setattr(db_module, "check_pg_health", fake_check_pg_health)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    monkeypatch.setattr(remotion_module, "RemotionRenderer", FakeRemotionRenderer)
    monkeypatch.setattr(health_router, "_check_clip_imports_only", lambda: False)

    result = await health_router.health()
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    for secret_value in SECRET_VALUES.values():
        assert secret_value not in serialized

    assert str(REPO_ROOT) not in serialized
    assert "prod_password" not in serialized
    assert "postgresql://" not in serialized
    assert "[redacted]" in serialized
    assert "[internal-path]" in serialized


def test_health_no_secret_contract_is_documented_and_link_checked():
    assert CONTRACT_FILE.is_file()
    assert RUNBOOK_FILE.is_file()

    contract = yaml.safe_load(CONTRACT_FILE.read_text())
    assert contract["public_endpoint"] == "/health"
    assert contract["skip_response_meta"] is True
    assert contract["forbidden_value_classes"] == [
        "provider_api_keys",
        "database_urls",
        "passwords",
        "tokens",
        "signing_secrets",
        "absolute_internal_paths",
    ]
    assert contract["allowed_top_level_keys"] == [
        "status",
        "version",
        "remotion",
        "persistence",
        "media_tools",
    ]

    runbook = RUNBOOK_FILE.read_text()
    assert "tests/test_health_endpoint_no_secret_guard.py" in runbook
    assert "DATABASE_URL" in runbook
    assert "POYO_API_KEY" in runbook
    assert "[redacted]" in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "docs/runbooks/health-endpoint-no-secret.md" in scope_targets
