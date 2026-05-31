"""Static README checks for frontend package-manager instructions."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
WEB_PACKAGE_LOCK = REPO_ROOT / "web" / "package-lock.json"
WEB_PNPM_LOCK = REPO_ROOT / "web" / "pnpm-lock.yaml"


def test_readme_uses_npm_for_frontend_commands():
    text = README.read_text()

    assert WEB_PACKAGE_LOCK.exists(), "frontend uses npm package-lock.json"
    assert not WEB_PNPM_LOCK.exists(), "pnpm lockfile must not coexist with npm package-lock.json"
    assert "pnpm" not in text, "README frontend commands must use npm, not pnpm"

    for command in [
        "npm ci",
        "npm run dev",
        "npm test -- --run",
        "npm run lint",
        "npm run e2e:ui",
        "npm run e2e:prod",
    ]:
        assert command in text
