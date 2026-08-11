#!/usr/bin/env python3
"""Read and verify the project semantic-version projections."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib as _tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 production-host compatibility.
    _tomllib = None

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_toml(path: Path) -> dict[str, Any]:
    if _tomllib is None:
        raise RuntimeError("stdlib TOML parser is unavailable")
    with path.open("rb") as handle:
        return _tomllib.load(handle)


def _quoted_assignment(line: str, key: str):
    match = re.fullmatch(rf"{re.escape(key)}\s*=\s*([\"'])([^\"']+)\1", line.strip())
    return match.group(2) if match else None


def _fallback_project_version(path: Path) -> str:
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line
            continue
        if section == "[project]":
            value = _quoted_assignment(line, "version")
            if value is not None:
                return value
    raise ValueError("pyproject [project].version is missing or not a quoted string")


def _fallback_uv_project_versions(path: Path) -> list[str]:
    matches: list[str] = []
    package: dict[str, str] = {}

    def record() -> None:
        if package.get("name") == "short-video-agent" and "version" in package:
            matches.append(package["version"])

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "[[package]]":
            record()
            package = {}
            continue
        if not package and not line.startswith(("name", "version")):
            continue
        for key in ("name", "version"):
            value = _quoted_assignment(line, key)
            if value is not None:
                package[key] = value
                break
    record()
    return matches


def project_version() -> str:
    path = REPO_ROOT / "pyproject.toml"
    value = (
        _read_toml(path)["project"]["version"]
        if _tomllib is not None
        else _fallback_project_version(path)
    )
    if not isinstance(value, str) or not value.strip():
        raise ValueError("pyproject project.version must be a non-empty string")
    return value


def _uv_project_version() -> str:
    path = REPO_ROOT / "uv.lock"
    if _tomllib is not None:
        packages = _read_toml(path).get("package", [])
        matches = [
            item.get("version")
            for item in packages
            if item.get("name") == "short-video-agent"
        ]
    else:
        matches = _fallback_uv_project_versions(path)
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise ValueError("uv.lock must contain exactly one short-video-agent package")
    return matches[0]


def _release_doc_version() -> str:
    for line in (REPO_ROOT / "docs/release/current.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("semantic_version: "):
            return line.split(":", 1)[1].strip().strip('"')
    raise ValueError("docs/release/current.md is missing semantic_version")


def projection_versions() -> dict[str, str]:
    package = json.loads((REPO_ROOT / "web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((REPO_ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
    return {
        "web/package.json": package["version"],
        "web/package-lock.json": lock["version"],
        "uv.lock": _uv_project_version(),
        "docs/release/current.md": _release_doc_version(),
    }


def check() -> str:
    version = project_version()
    mismatches = {
        path: value for path, value in projection_versions().items() if value != version
    }
    if mismatches:
        details = ", ".join(f"{path}={value}" for path, value in sorted(mismatches.items()))
        raise ValueError(f"semantic version drift: expected {version}; {details}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail on projection drift")
    args = parser.parse_args()
    toml_decode_errors = (
        (_tomllib.TOMLDecodeError,) if _tomllib is not None else ()
    )
    expected_errors = (
        OSError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) + toml_decode_errors
    try:
        value = check() if args.check else project_version()
    except expected_errors as exc:
        print(f"project_version_error: {exc}", file=sys.stderr)
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
