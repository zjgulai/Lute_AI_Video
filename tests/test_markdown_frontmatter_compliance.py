"""Static guard for tracked Markdown frontmatter compliance."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "markdown-frontmatter-compliance-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "markdown-frontmatter-compliance.md"

SCANNED_GLOBS = ("docs/**/*.md", "drafts/**/*.md")


def _tracked_markdown_paths() -> list[Path]:
    output = subprocess.check_output(("git", "ls-files", "-z", *SCANNED_GLOBS), cwd=REPO_ROOT)
    return [
        REPO_ROOT / path
        for path in output.decode().split("\0")
        if path
    ]


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "Markdown frontmatter contract is missing"
    return json.loads(CONTRACT_PATH.read_text())


def _frontmatter_issue(path: Path, required_fields: set[str]) -> list[str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        return ["missing_frontmatter"]

    end = text.find("\n---", 4)
    if end == -1:
        return ["unterminated_frontmatter"]

    try:
        metadata = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return ["invalid_frontmatter_yaml"]

    if not isinstance(metadata, dict):
        return ["invalid_frontmatter_shape"]

    missing = sorted(
        field
        for field in required_fields
        if field not in metadata or metadata[field] in (None, "")
    )
    return [f"missing:{field}" for field in missing]


def _actual_legacy_issues() -> dict[str, list[str]]:
    required_fields = set(_contract()["required_fields"])
    issues: dict[str, list[str]] = {}
    for path in _tracked_markdown_paths():
        issue = _frontmatter_issue(path, required_fields)
        if issue:
            issues[_relative(path)] = issue
    return issues


def test_all_tracked_docs_and_drafts_are_either_compliant_or_declared_legacy():
    contract = _contract()
    expected = {
        item["path"]: item["issues"]
        for item in contract["legacy_frontmatter_exceptions"]
    }

    assert _actual_legacy_issues() == expected


def test_frontmatter_contract_uses_required_schema_and_explicit_reasons():
    contract = _contract()

    assert contract["scanned_globs"] == list(SCANNED_GLOBS)
    assert contract["required_fields"] == [
        "title",
        "doc_type",
        "module",
        "topic",
        "status",
        "created",
        "updated",
        "owner",
        "source",
    ]

    for item in contract["legacy_frontmatter_exceptions"]:
        assert item["path"].startswith(("docs/", "drafts/"))
        assert item["path"].endswith(".md")
        assert item["status"] == "legacy_backfill_required"
        assert item["reason"].strip()
        assert item["issues"], f"{item['path']} must list exact issues"


def test_fully_compliant_frontmatter_values_use_project_vocab():
    contract = _contract()
    required_fields = set(contract["required_fields"])
    legacy_paths = {
        item["path"] for item in contract["legacy_frontmatter_exceptions"]
    }
    allowed_doc_types = set(contract["allowed_doc_types"])
    allowed_statuses = set(contract["allowed_statuses"])
    allowed_sources = set(contract["allowed_sources"])

    for path in _tracked_markdown_paths():
        if _relative(path) in legacy_paths:
            continue

        text = path.read_text()
        end = text.find("\n---", 4)
        metadata = yaml.safe_load(text[4:end]) or {}

        assert required_fields.issubset(metadata.keys())
        assert metadata["doc_type"] in allowed_doc_types
        assert metadata["status"] in allowed_statuses
        assert metadata["source"] in allowed_sources


def test_frontmatter_runbook_covers_required_fields_and_legacy_boundary():
    runbook_text = RUNBOOK_PATH.read_text()
    contract = _contract()

    assert "markdown-frontmatter-compliance-contract.json" in runbook_text
    assert "legacy_backfill_required" in runbook_text
    assert "不批量改写" in runbook_text

    for field in contract["required_fields"]:
        assert field in runbook_text

    for item in contract["legacy_frontmatter_exceptions"]:
        assert item["path"] in runbook_text
