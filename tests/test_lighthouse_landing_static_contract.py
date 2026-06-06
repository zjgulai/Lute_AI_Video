"""Static guards for the Lighthouse apex landing page sidecars."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LANDING_DIR = REPO_ROOT / "deploy" / "lighthouse" / "landing"
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"

AUTH_VERSION = "20260606-auth-mail"
APEX_HOST = "lute-tlz-dddd.top"

LANDING_SIDECARS = {
    "login.html",
    "register.html",
    "systems.html",
    "lute-auth.css",
    "lute-auth.js",
}

REMOTE_ONLY_EXCLUDES = {
    "deploy/lighthouse/landing/login.html",
    "deploy/lighthouse/landing/register.html",
    "deploy/lighthouse/landing/systems.html",
    "deploy/lighthouse/landing/lute-*.html",
    "deploy/lighthouse/landing/lute-auth.*",
}


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
    assert "https://video.lute-tlz-dddd.top" in systems_html
    assert "https://voc.lute-tlz-dddd.top" in systems_html
    assert "具体业务系统仍由各自子域名和应用权限控制" in systems_html


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


def test_lighthouse_landing_sidecars_remain_remote_only_for_default_deploy():
    excludes = {
        line.strip()
        for line in RSYNC_EXCLUDES.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    missing = sorted(REMOTE_ONLY_EXCLUDES - excludes)
    assert not missing, f"remote-only landing sidecar excludes missing: {missing}"
