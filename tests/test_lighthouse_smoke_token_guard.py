"""Fail-closed guards for the provider-off Lighthouse public smoke."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
SMOKE_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "smoke.sh"
RELEASE_CONTRACT = REPO_ROOT / "configs" / "project-release-governance.json"


def test_lighthouse_smoke_has_no_credential_or_provider_path() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    for forbidden in (
        ".env.prod",
        "grep -E '^API_KEY='",
        "curl -k",
        "curl -sk",
        "/api/fast/generate",
        "/api/fast/submit",
        "/api/scenario/",
        "RUN_TOKEN_SMOKE=1",
        '"X-API-Key:',
    ):
        assert forbidden not in text

    assert 'RUN_TOKEN_SMOKE:-0}" != "0"' in text
    assert "provider/token smoke is available only through an exact authorized executor" in text
    assert "provider_call=false" in text


def test_lighthouse_smoke_requires_tls_and_dual_release_identity() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "https://video.lute-tlz-dddd.top" in text
    assert "--proto '=https'" in text
    assert "--tlsv1.2" in text
    assert "EXPECTED_APP_VERSION is required" in text
    assert "EXPECTED_SOURCE_REVISION must be the reviewed 40-character Git SHA" in text
    assert 'payload.get("version") == sys.argv[1]' in text
    assert 'payload.get("source_revision") == sys.argv[2]' in text


def test_lighthouse_smoke_performs_only_public_readback_and_unauthorized_get() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "$BASE/api/health" in text
    assert "$BASE/api/toolbox/tools" in text
    assert 'check_status "GET /api/toolbox/tools without key" "401"' in text
    assert "-X POST" not in text
    assert "-X PUT" not in text
    assert "-X PATCH" not in text
    assert "-X DELETE" not in text


def test_current_governance_scans_lighthouse_smoke() -> None:
    contract = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))

    assert "deploy/lighthouse/smoke.sh" in contract[
        "active_operations_non_document_surfaces"
    ]


def test_lighthouse_deploy_never_reads_api_key_or_invokes_smoke_script() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "API_KEY" not in text
    assert "bash smoke.sh" not in text
