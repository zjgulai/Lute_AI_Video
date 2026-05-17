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
    env_override = os.environ.get("APP_VERSION", "").strip()
    if env_override:
        return env_override
    try:
        return version("short-video-agent")
    except PackageNotFoundError:
        pass
    pyproject_version = _read_pyproject_version()
    if pyproject_version:
        return pyproject_version
    return "0.0.0+dev"


APP_VERSION = get_version()
