"""Fail on new Pyright test diagnostics, suppressions, or config downgrades."""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = REPO_ROOT / "configs" / "pyright-test-baseline.json"
DEFAULT_SUPPRESSION_BASELINE = REPO_ROOT / "configs" / "pyright-suppression-baseline.json"
SCHEMA_VERSION = "pyright-test-baseline.v1"
SUPPRESSION_SCHEMA_VERSION = "pyright-suppression-baseline.v1"
TYPE_IGNORE_COMMENT = re.compile(
    r"^#\s*type:\s*ignore(?:\[[^\]\r\n]+\])?(?=$|\s)",
    re.IGNORECASE,
)
PYRIGHT_COMMENT = re.compile(r"^#\s*pyright:\s*", re.IGNORECASE)


def _is_suppression_comment(comment: str) -> bool:
    return bool(TYPE_IGNORE_COMMENT.match(comment) or PYRIGHT_COMMENT.match(comment))


def _pyright_executable() -> str:
    executable = Path(sys.executable).parent / "pyright"
    if not executable.is_file():
        raise RuntimeError("Pyright is not installed beside the active Python interpreter")
    return str(executable)


def _relative_file(raw_path: str) -> str:
    path = Path(raw_path)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("Pyright diagnostic is outside the repository") from exc


def diagnostic_fingerprint(diagnostic: dict[str, Any]) -> str:
    severity = diagnostic.get("severity")
    rule = diagnostic.get("rule")
    message = diagnostic.get("message")
    start = (diagnostic.get("range") or {}).get("start") or {}
    line = start.get("line")
    character = start.get("character")
    raw_file = diagnostic.get("file")
    if (
        severity != "error"
        or not isinstance(rule, str)
        or not rule
        or not isinstance(message, str)
        or not message
        or not isinstance(line, int)
        or line < 0
        or not isinstance(character, int)
        or character < 0
        or not isinstance(raw_file, str)
        or not raw_file
    ):
        raise ValueError("Pyright returned a malformed error diagnostic")
    compact_message = " ".join(message.split())
    return f"{_relative_file(raw_file)}:{line + 1}:{character + 1}|{rule}|{compact_message}"


def fingerprint_counts(diagnostics: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        diagnostic_fingerprint(item)
        for item in diagnostics
        if item.get("severity") == "error"
    )


def unexpected_diagnostics(
    current: Counter[str], baseline: Counter[str]
) -> Counter[str]:
    return current - baseline


def suppression_fingerprint(path: Path, line: int, comment: str, repo_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("suppression source is outside the repository") from exc
    normalized = " ".join(comment.split())
    return f"{relative}:{line}|{normalized}"


def scan_suppressions(paths: list[Path], repo_root: Path = REPO_ROOT) -> Counter[str]:
    suppressions: Counter[str] = Counter()
    for root in paths:
        candidates = sorted(root.rglob("*.py")) if root.is_dir() else [root]
        for path in candidates:
            try:
                tokens = tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
                for token in tokens:
                    if token.type == tokenize.COMMENT and _is_suppression_comment(token.string):
                        suppressions[suppression_fingerprint(path, token.start[0], token.string, repo_root)] += 1
            except (OSError, UnicodeDecodeError, tokenize.TokenError) as exc:
                raise RuntimeError(f"unable to scan Pyright suppressions: {path}") from exc
    return suppressions


def _current_pyright_config() -> dict[str, Any]:
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    config = payload.get("tool", {}).get("pyright")
    if not isinstance(config, dict):
        raise RuntimeError("pyproject.toml is missing [tool.pyright]")
    return config


def _pyright_version() -> str:
    result = subprocess.run(
        [_pyright_executable(), "--version"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip()
    if not version.startswith("pyright "):
        raise RuntimeError("unable to determine Pyright version")
    return version.removeprefix("pyright ")


def _run_pyright() -> dict[str, Any]:
    result = subprocess.run(
        [
            _pyright_executable(),
            "--pythonpath",
            sys.executable,
            "tests",
            "--outputjson",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            f"Pyright execution failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Pyright did not return valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("generalDiagnostics"), list):
        raise RuntimeError("Pyright JSON is missing generalDiagnostics")
    return payload


def _load_baseline(path: Path, expected_version: str) -> Counter[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read Pyright baseline: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Pyright baseline schema is invalid")
    if payload.get("pyright_version") != expected_version:
        raise RuntimeError("Pyright version differs from the reviewed baseline")
    entries = payload.get("diagnostics")
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise RuntimeError("Pyright baseline diagnostics are invalid")
    return Counter(entries)


def _write_baseline(
    path: Path, version: str, diagnostics: Counter[str]
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pyright_version": version,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "scope": "tests",
        "diagnostic_count": diagnostics.total(),
        "diagnostics": sorted(diagnostics.elements()),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_suppression_baseline(path: Path) -> tuple[Counter[str], dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read Pyright suppression baseline: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SUPPRESSION_SCHEMA_VERSION:
        raise RuntimeError("Pyright suppression baseline schema is invalid")
    entries = payload.get("suppressions")
    config = payload.get("pyright_config")
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise RuntimeError("Pyright suppression baseline entries are invalid")
    if not isinstance(config, dict):
        raise RuntimeError("Pyright suppression baseline config is invalid")
    return Counter(entries), config


def _write_suppression_baseline(
    path: Path, suppressions: Counter[str], config: dict[str, Any]
) -> None:
    payload = {
        "schema_version": SUPPRESSION_SCHEMA_VERSION,
        "scope": ["src", "tests", "scripts"],
        "suppression_count": suppressions.total(),
        "suppressions": sorted(suppressions.elements()),
        "pyright_config": config,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--suppression-baseline", type=Path, default=DEFAULT_SUPPRESSION_BASELINE
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Explicit maintainer action; never used by make typecheck or CI.",
    )
    parser.add_argument(
        "--write-suppression-baseline",
        action="store_true",
        help="Explicit maintainer action; never used by make typecheck or CI.",
    )
    args = parser.parse_args()

    version = _pyright_version()
    payload = _run_pyright()
    current = fingerprint_counts(payload["generalDiagnostics"])
    current_suppressions = scan_suppressions(
        [REPO_ROOT / "src", REPO_ROOT / "tests", REPO_ROOT / "scripts"]
    )
    current_config = _current_pyright_config()
    if args.write_baseline:
        _write_baseline(args.baseline, version, current)
        print(f"wrote {current.total()} reviewed diagnostics to {args.baseline}")
    if args.write_suppression_baseline:
        _write_suppression_baseline(
            args.suppression_baseline, current_suppressions, current_config
        )
        print(
            f"wrote {current_suppressions.total()} reviewed suppressions "
            f"to {args.suppression_baseline}"
        )
    if args.write_baseline or args.write_suppression_baseline:
        return 0

    baseline = _load_baseline(args.baseline, version)
    suppression_baseline, config_baseline = _load_suppression_baseline(
        args.suppression_baseline
    )
    unexpected_suppressions = current_suppressions - suppression_baseline
    if unexpected_suppressions:
        print(
            f"Pyright suppression ratchet failed: "
            f"{unexpected_suppressions.total()} new suppression(s)",
            file=sys.stderr,
        )
        for fingerprint, count in sorted(unexpected_suppressions.items())[:50]:
            print(f"{count}x {fingerprint}", file=sys.stderr)
        return 1
    if current_config != config_baseline:
        print(
            "Pyright suppression ratchet failed: [tool.pyright] differs from the reviewed baseline",
            file=sys.stderr,
        )
        return 1
    unexpected = unexpected_diagnostics(current, baseline)
    if unexpected:
        print(
            f"Pyright test ratchet failed: {unexpected.total()} new diagnostic(s)",
            file=sys.stderr,
        )
        for fingerprint, count in sorted(unexpected.items())[:50]:
            print(f"{count}x {fingerprint}", file=sys.stderr)
        return 1

    removed = baseline.total() - current.total()
    removed_suppressions = suppression_baseline.total() - current_suppressions.total()
    print(
        f"Pyright test ratchet passed: {current.total()} current, "
        f"{removed} diagnostics removed; {current_suppressions.total()} suppressions current, "
        f"{removed_suppressions} suppressions removed from reviewed baselines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
