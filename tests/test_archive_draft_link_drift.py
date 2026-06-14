"""Static guard for historical archive/draft link drift in active docs."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CONTRACT_PATH = REPO_ROOT / "configs" / "archive-draft-link-drift-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "archive-draft-link-drift.md"

REPO_ABSOLUTE_PREFIX = "/Users/pray/project/hermes_evo/AI_vedio/"
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "archive/draft link drift contract is missing"
    return json.loads(CONTRACT_PATH.read_text())


def _active_markdown_docs() -> list[Path]:
    targets = [
        line.strip()
        for line in SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return [
        REPO_ROOT / target
        for target in targets
        if target.endswith(".md")
    ]


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _normalize_target(source_path: Path, raw_target: str) -> str:
    target = raw_target.strip("<>").split("#", 1)[0]
    from_repo_root = False
    if not target:
        return ""

    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) and not target.startswith("file://"):
        return ""

    if target.startswith("file://"):
        target = target.removeprefix("file://")
        if target.startswith(REPO_ABSOLUTE_PREFIX):
            target = target.removeprefix(REPO_ABSOLUTE_PREFIX)
            from_repo_root = True
        elif target.startswith("/"):
            return ""

    if target.startswith(REPO_ABSOLUTE_PREFIX):
        target = target.removeprefix(REPO_ABSOLUTE_PREFIX)
        from_repo_root = True
    elif target.startswith("/"):
        return ""

    target_path = PurePosixPath(target)
    if not from_repo_root and not target_path.is_absolute():
        target_path = PurePosixPath(_relative(source_path).rsplit("/", 1)[0]) / target_path

    parts: list[str] = []
    for part in target_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _is_historical_target(raw_target: str, normalized_target: str, contract: dict[str, Any]) -> bool:
    prefixes = tuple(contract["historical_target_prefixes"])
    fragments = tuple(contract["historical_raw_target_fragments"])
    return normalized_target.startswith(prefixes) or any(
        fragment in raw_target for fragment in fragments
    )


def _frontmatter_file_targets(path: Path) -> list[str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---", 4)
    if end == -1:
        return []
    try:
        metadata = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return []

    targets: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "file" and isinstance(nested, str):
                    targets.append(nested)
                else:
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(metadata)
    return targets


def _historical_references() -> list[dict[str, Any]]:
    contract = _contract()
    references: list[dict[str, Any]] = []

    for path in _active_markdown_docs():
        text = path.read_text()
        lines = text.splitlines()

        for line_number, line in enumerate(lines, start=1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                raw_target = match.group(1)
                normalized_target = _normalize_target(path, raw_target)
                if _is_historical_target(raw_target, normalized_target, contract):
                    references.append(
                        {
                            "source_path": _relative(path),
                            "kind": "markdown_link",
                            "target_path": normalized_target,
                            "raw_target": raw_target,
                            "line": line_number,
                        }
                    )

        for raw_target in _frontmatter_file_targets(path):
            normalized_target = _normalize_target(path, raw_target)
            if _is_historical_target(raw_target, normalized_target, contract):
                references.append(
                    {
                        "source_path": _relative(path),
                        "kind": "frontmatter_file",
                        "target_path": normalized_target,
                        "raw_target": raw_target,
                    }
                )

    return sorted(references, key=lambda item: (item["source_path"], item["kind"], item["target_path"]))


def test_active_docs_historical_links_are_explicitly_classified():
    identity_keys = ("source_path", "kind", "target_path", "raw_target")
    expected = sorted(
        {
            tuple(item[key] for key in identity_keys)
            for item in _contract()["allowed_historical_references"]
        }
    )
    actual = sorted(
        {
            tuple(item[key] for key in identity_keys)
            for item in _historical_references()
        }
    )

    assert [dict(zip(identity_keys, item, strict=True)) for item in actual] == [
        dict(zip(identity_keys, item, strict=True)) for item in expected
    ]


def test_markdown_historical_links_include_non_current_context():
    contract = _contract()
    markers = tuple(contract["required_context_markers"])

    for reference in _historical_references():
        if reference["kind"] != "markdown_link":
            continue
        source_path = REPO_ROOT / reference["source_path"]
        lines = source_path.read_text().splitlines()
        line_number = reference["line"]
        context = "\n".join(lines[max(0, line_number - 4) : min(len(lines), line_number + 2)])
        assert any(marker in context for marker in markers), reference


def test_historical_reference_contract_documents_scope_and_reason():
    contract = _contract()

    assert contract["active_docs_source"] == "configs/docs-link-check-scope.txt"
    assert ".kiro/" in contract["historical_target_prefixes"]
    assert "drafts/" in contract["historical_target_prefixes"]
    assert "archive/" in contract["historical_target_prefixes"]

    for item in contract["allowed_historical_references"]:
        assert item["status"] == "historical_reference_only"
        assert item["current_entrypoint"] is False
        assert item["reason"].strip()


def test_archive_draft_link_drift_runbook_covers_allowed_references():
    runbook_text = RUNBOOK_PATH.read_text()
    contract = _contract()

    assert "archive-draft-link-drift-contract.json" in runbook_text
    assert "historical_reference_only" in runbook_text
    assert "不作为当前执行入口" in runbook_text

    for item in contract["allowed_historical_references"]:
        assert item["source_path"] in runbook_text
        assert item["target_path"] in runbook_text
