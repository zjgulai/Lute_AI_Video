from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_pyright_ratchet.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_pyright_ratchet", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fingerprint_is_repository_relative_and_location_specific() -> None:
    module = _module()
    diagnostic = {
        "file": str(REPO_ROOT / "tests" / "test_example.py"),
        "severity": "error",
        "rule": "reportArgumentType",
        "message": "first line\n  second line",
        "range": {"start": {"line": 4, "character": 2}},
    }

    assert module.diagnostic_fingerprint(diagnostic) == (
        "tests/test_example.py:5:3|reportArgumentType|first line second line"
    )


def test_fingerprint_rejects_out_of_repository_diagnostics(tmp_path: Path) -> None:
    module = _module()
    diagnostic = {
        "file": str(tmp_path / "foreign.py"),
        "severity": "error",
        "rule": "reportArgumentType",
        "message": "bad",
        "range": {"start": {"line": 0, "character": 0}},
    }

    with pytest.raises(ValueError, match="outside the repository"):
        module.diagnostic_fingerprint(diagnostic)


def test_ratchet_allows_removal_but_rejects_new_fingerprint() -> None:
    module = _module()
    baseline = Counter({"a": 2, "b": 1})

    assert module.unexpected_diagnostics(Counter({"a": 1}), baseline) == Counter()
    assert module.unexpected_diagnostics(Counter({"a": 3}), baseline) == Counter({"a": 1})
    assert module.unexpected_diagnostics(Counter({"a": 1, "c": 1}), baseline) == Counter({"c": 1})


def test_suppression_ratchet_rejects_new_comment_and_allows_removal(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "module.py"
    source.write_text(
        'literal = "# type: ignore[not-a-comment]"\n'
        "first = unknown  # type: ignore[name-defined]\n",
        encoding="utf-8",
    )
    baseline = module.scan_suppressions([source], tmp_path)
    assert baseline.total() == 1

    source.write_text(
        'literal = "# type: ignore[not-a-comment]"\n'
        "first = unknown  # type: ignore[name-defined]\n"
        "second = unknown  # pyright: ignore[reportUndefinedVariable]\n",
        encoding="utf-8",
    )
    current = module.scan_suppressions([source], tmp_path)
    assert (current - baseline).total() == 1

    source.write_text("first = 1\n", encoding="utf-8")
    assert module.scan_suppressions([source], tmp_path) - baseline == Counter()


def test_suppression_ratchet_detects_type_ignore_with_trailing_reason(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "module.py"
    source.write_text(
        "value = unknown  # type: ignore[name-defined]  # runtime fixture\n",
        encoding="utf-8",
    )

    suppressions = module.scan_suppressions([source], tmp_path)

    assert suppressions.total() == 1


def test_make_and_ci_do_not_refresh_the_baseline() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    deploy = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "check_pyright_ratchet.py" in makefile
    assert "--write-baseline" not in makefile
    assert "--write-suppression-baseline" not in makefile
    assert "--write-baseline" not in ci
    assert "--write-suppression-baseline" not in ci
    assert "--write-baseline" not in deploy
    assert "--write-suppression-baseline" not in deploy
