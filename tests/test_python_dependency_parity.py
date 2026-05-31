"""Static dependency parity checks for Python developer tooling."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
UV_LOCK = REPO_ROOT / "uv.lock"


def _dependency_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~;\s]", requirement.strip(), maxsplit=1)[0].replace("_", "-").lower()


def _requirements_names() -> set[str]:
    names: set[str] = set()
    for line in REQUIREMENTS.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.add(_dependency_name(stripped))
    return names


def _pyproject_dev_dependency_names() -> set[str]:
    pyproject = tomllib.loads(PYPROJECT.read_text())
    return {
        _dependency_name(dep)
        for dep in pyproject["project"]["optional-dependencies"]["dev"]
    }


def test_requirements_includes_all_pyproject_dev_dependencies():
    missing = _pyproject_dev_dependency_names() - _requirements_names()

    assert not missing, (
        "requirements.txt development section must include pyproject dev dependencies: "
        + ", ".join(sorted(missing))
    )


def test_uv_lock_contains_all_pyproject_dev_dependencies():
    lock_text = UV_LOCK.read_text()
    missing = [
        dep
        for dep in sorted(_pyproject_dev_dependency_names())
        if f'name = "{dep}"' not in lock_text
    ]

    assert not missing, (
        "uv.lock must contain pyproject dev dependencies: " + ", ".join(missing)
    )
