"""Static guards for the Lighthouse apex landing page sidecars."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LANDING_DIR = REPO_ROOT / "deploy" / "lighthouse" / "landing"
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"
SIDECAR_SYNC = REPO_ROOT / "deploy" / "lighthouse" / "sync-landing-sidecars.sh"
NGINX_CONF = REPO_ROOT / "deploy" / "lighthouse" / "nginx.conf"
DOCKER_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"

AUTH_VERSION = "20260606-auth-mail"
APEX_HOST = "lute-tlz-dddd.top"
EXPECTED_SYSTEM_HOSTS = {
    "video",
    "voc",
    "report",
    "shopify",
    "mkt",
    "brand",
    "mas",
    "business",
    "product",
    "kg",
    "person",
    "llm",
}
STATIC_SITE_MOUNTS = {
    "mkt": ("/opt/mkt53/html", "/var/www/mkt53"),
    "shopify": ("/opt/momcozy-audit/html", "/var/www/momcozy-audit"),
    "report": ("/opt/voc-report/html", "/var/www/voc-report"),
    "business": ("/opt/business-insight-hub/html", "/var/www/business-insight-hub"),
    "product": ("/opt/ai-product-select/html", "/var/www/ai-product-select"),
    "person": ("/opt/ai-employ-platform/html", "/var/www/ai-employ-platform"),
    "llm": ("/opt/llm-compare-hub/html", "/var/www/llm-compare-hub"),
}

LANDING_SIDECARS = {
    "login.html",
    "register.html",
    "systems.html",
    "lute-auth.css",
    "lute-auth.js",
}

TRACKED_RELEASE_SIDECARS = {
    f"deploy/lighthouse/landing/{filename}" for filename in LANDING_SIDECARS
}
REMOTE_ONLY_EXCLUDES = {"deploy/lighthouse/landing/lute-*.html"}


def _attribute_urls(text: str) -> list[str]:
    return re.findall(r"""(?:href|src)=["']([^"']+)["']""", text)


def _local_landing_file_from_url(raw_url: str) -> Path | None:
    parsed = urlparse(raw_url)
    if parsed.scheme and parsed.netloc != APEX_HOST:
        return None

    path = unquote(parsed.path.lstrip("/"))
    if path in LANDING_SIDECARS:
        return LANDING_DIR / path
    return None


def _next_landing_file_from_url(raw_url: str) -> Path | None:
    parsed = urlparse(raw_url)
    next_values = parse_qs(parsed.query).get("next", [])
    if not next_values:
        return None

    next_path = next_values[0].lstrip("/")
    if next_path in LANDING_SIDECARS:
        return LANDING_DIR / next_path
    return None


def test_lighthouse_landing_entrypoint_references_existing_sidecars():
    required_files = {"index.html"} | LANDING_SIDECARS
    missing = sorted(
        filename for filename in required_files if not (LANDING_DIR / filename).exists()
    )
    assert not missing, f"landing sidecar files are missing: {missing}"

    for filename in required_files:
        text = (LANDING_DIR / filename).read_text()
        missing_refs = []
        for raw_url in _attribute_urls(text):
            for candidate in (
                _local_landing_file_from_url(raw_url),
                _next_landing_file_from_url(raw_url),
            ):
                if candidate is not None and not candidate.exists():
                    missing_refs.append(f"{filename} -> {raw_url}")
        assert not missing_refs, "landing page references missing local sidecars: " + ", ".join(
            sorted(missing_refs)
        )


def test_lighthouse_cover_enters_the_systems_directory_after_login():
    index_html = (LANDING_DIR / "index.html").read_text()
    systems_html = (LANDING_DIR / "systems.html").read_text()

    assert "next=/systems.html" in index_html
    assert "路特数据科学平台" in systems_html

    missing_hosts = sorted(
        host
        for host in EXPECTED_SYSTEM_HOSTS
        if f"https://{host}.{APEX_HOST}" not in systems_html
    )
    assert not missing_hosts, f"systems directory missing cards: {missing_hosts}"


def test_lighthouse_system_domains_are_routed_before_default_ai_video_fallback():
    nginx_conf = NGINX_CONF.read_text()
    compose = DOCKER_COMPOSE.read_text()

    for host in EXPECTED_SYSTEM_HOSTS:
        assert f"{host}.{APEX_HOST}" in nginx_conf

    for host, (source, target) in STATIC_SITE_MOUNTS.items():
        assert f"server_name {host}.{APEX_HOST};" in nginx_conf
        assert f"root {target};" in nginx_conf
        assert f"{source}:{target}:ro" in compose

    assert f"server_name brand.{APEX_HOST} mas.{APEX_HOST};" in nginx_conf
    assert f"server_name kg.{APEX_HOST};" in nginx_conf
    assert "server promptforge_app:3000;" in nginx_conf


def test_lighthouse_auth_assets_use_one_cache_bust_version():
    auth_js = (LANDING_DIR / "lute-auth.js").read_text()
    assert f'const APP_VERSION = "{AUTH_VERSION}"' in auth_js

    for filename in ["index.html", "login.html", "register.html", "systems.html"]:
        text = (LANDING_DIR / filename).read_text()
        if "lute-auth.css" in text:
            assert f"lute-auth.css?v={AUTH_VERSION}" in text
        if "lute-auth.js" in text:
            assert f"lute-auth.js?v={AUTH_VERSION}" in text


def test_lighthouse_auth_script_uses_publishable_supabase_key_only():
    auth_js = (LANDING_DIR / "lute-auth.js").read_text()
    lower = auth_js.lower()

    assert "sb_publishable_" in auth_js
    for forbidden in ["service_role", "sb_secret_", "supabase_service"]:
        assert forbidden not in lower


def test_lighthouse_landing_sidecar_release_and_shared_root_boundaries():
    excludes = {
        line.strip()
        for line in RSYNC_EXCLUDES.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    missing = sorted(REMOTE_ONLY_EXCLUDES - excludes)
    assert not missing, f"remote-only landing sidecar excludes missing: {missing}"
    assert not (TRACKED_RELEASE_SIDECARS & excludes)


def test_lighthouse_landing_sidecar_sync_is_manual_dry_run_by_default():
    script = SIDECAR_SYNC.read_text()

    subprocess.run(["bash", "-n", str(SIDECAR_SYNC)], check=True)

    assert 'DRY_RUN="${DRY_RUN:-1}"' in script
    assert "REMOTE_LANDING_DIR=\"$REMOTE_DIR/deploy/lighthouse/landing\"" in script
    assert "--delete" not in script
    assert "RUN_TOKEN_SMOKE" not in script
    assert "deploy.sh" not in script
    assert "docker-compose" not in script
    assert "docker compose" not in script
    assert "docker exec ai_video_nginx nginx -t" in script

    for filename in ["index.html", *sorted(LANDING_SIDECARS)]:
        assert filename in script
