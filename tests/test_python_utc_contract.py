"""Static guard against deprecated naive UTC timestamp calls."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("src", "scripts", "tests")


def test_project_python_code_does_not_call_datetime_utcnow() -> None:
    offenders: list[str] = []
    forbidden_call = "datetime." + "utcnow("

    for root in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if forbidden_call in text:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert not offenders, (
        "Use timezone-aware datetime.now(UTC) instead of deprecated naive UTC calls: "
        + ", ".join(offenders)
    )
