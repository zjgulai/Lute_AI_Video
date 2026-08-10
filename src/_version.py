from __future__ import annotations

import os
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_pyproject_version() -> str | None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def get_version() -> str:
    pyproject_version = _read_pyproject_version()
    package_version: str | None = None
    try:
        package_version = version("short-video-agent")
    except PackageNotFoundError:
        pass

    if pyproject_version and package_version and package_version != pyproject_version:
        raise RuntimeError("installed package version does not match pyproject authority")

    canonical = pyproject_version or package_version
    env_override = os.environ.get("APP_VERSION", "").strip()
    if env_override:
        if canonical and env_override != canonical:
            raise RuntimeError("APP_VERSION does not match pyproject authority")
        return env_override
    if canonical:
        return canonical
    return "0.0.0+dev"


def get_source_revision() -> str:
    """Return a public, non-secret release revision without trusting free text."""

    value = os.environ.get("RELEASE_SOURCE_SHA", "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", value):
        return value
    if value == "local-dev-dirty":
        return value
    return "unavailable"


APP_VERSION = get_version()
APP_SOURCE_REVISION = get_source_revision()
