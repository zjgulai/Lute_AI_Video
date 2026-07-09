"""Static guard for Lighthouse nginx long-running route timeouts."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_VIDEO_LOCATIONS = REPO_ROOT / "deploy" / "lighthouse" / "ai_video_locations.conf"
NGINX_CONF = REPO_ROOT / "deploy" / "lighthouse" / "nginx.conf"
DEPLOY_DOC = REPO_ROOT / "docs" / "workflows" / "deploy-lighthouse-stable.md"
CONTRACT_FILE = REPO_ROOT / "configs" / "lighthouse-nginx-timeout-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "lighthouse-nginx-timeout-parity.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

LONG_RUNNING_LOCATIONS = {
    "/api/scenario/": {
        "proxy_pass": "http://ai_video_backend/scenario/",
        "read_timeout": "1500s",
        "send_timeout": "1500s",
        "connect_timeout": "60s",
    },
    "/api/fast/": {
        "proxy_pass": "http://ai_video_backend/fast/",
        "read_timeout": "1500s",
        "send_timeout": "1500s",
        "connect_timeout": "60s",
    },
    "/api/pipeline/": {
        "proxy_pass": "http://ai_video_backend/pipeline/",
        "read_timeout": "1500s",
        "send_timeout": "1500s",
        "connect_timeout": "60s",
    },
}


def _location_body(text: str, location: str) -> str:
    match = re.search(
        rf"location\s+{re.escape(location)}\s*\{{(?P<body>.*?)\n\}}",
        text,
        flags=re.DOTALL,
    )
    assert match, f"{AI_VIDEO_LOCATIONS} must define location {location}"
    return match.group("body")


def _directive_value(body: str, directive: str) -> str:
    match = re.search(rf"\b{re.escape(directive)}\s+([^;]+);", body)
    assert match, f"{directive} must be set in location block"
    return match.group(1).strip()


def test_long_running_ai_video_routes_keep_1500s_nginx_timeouts():
    text = AI_VIDEO_LOCATIONS.read_text()
    for location, expected in LONG_RUNNING_LOCATIONS.items():
        body = _location_body(text, location)

        assert _directive_value(body, "proxy_pass") == expected["proxy_pass"]
        assert _directive_value(body, "proxy_read_timeout") == expected["read_timeout"]
        assert _directive_value(body, "proxy_send_timeout") == expected["send_timeout"]
        assert _directive_value(body, "proxy_connect_timeout") == expected["connect_timeout"]
        assert _directive_value(body, "proxy_buffering") == "off"


def test_canonical_video_and_ip_server_blocks_include_shared_ai_video_locations():
    nginx = NGINX_CONF.read_text()
    for server_name in ("video.lute-tlz-dddd.top", "101.34.52.232 _"):
        match = re.search(
            rf"server\s*\{{(?P<body>.*?server_name\s+{re.escape(server_name)};.*?include\s+/etc/nginx/ai_video_locations\.conf;.*?)\n\s*\}}",
            nginx,
            flags=re.DOTALL,
        )
        assert match, f"{server_name} must include shared ai_video_locations.conf"


def test_lighthouse_deploy_doc_mirrors_timeout_source_and_values():
    doc = DEPLOY_DOC.read_text()
    for token in [
        "ai_video_locations.conf",
        "`/api/scenario/`",
        "`/api/fast/`",
        "`/api/pipeline/`",
        "proxy_read_timeout 1500s",
        "proxy_send_timeout 1500s",
        "proxy_buffering off",
    ]:
        assert token in doc


def test_lighthouse_nginx_timeout_contract_and_runbook_are_documented():
    contract = CONTRACT_FILE.read_text()
    runbook = RUNBOOK_FILE.read_text()
    scope_targets = DOCS_LINK_SCOPE.read_text().splitlines()

    for token in [
        "long_running_locations",
        "proxy_read_timeout: 1500s",
        "proxy_send_timeout: 1500s",
        "proxy_buffering: off",
        "shared_include_required",
    ]:
        assert token in contract

    for token in [
        "pytest tests/test_lighthouse_nginx_timeout_contract.py",
        "ai_video_locations.conf",
        "proxy_read_timeout 1500s",
        "不触发生成接口",
    ]:
        assert token in runbook

    assert "docs/runbooks/lighthouse-nginx-timeout-parity.md" in scope_targets
