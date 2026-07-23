"""Static guards for repository root directory governance."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "root-directory-governance-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "root-directory-governance.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

CONTRACT_SECTIONS = (
    "allowed_root_files",
    "allowed_root_directories",
    "legacy_tracked_root_directories",
)


def _git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=REPO_ROOT).decode()


def _tracked_paths() -> list[str]:
    output = subprocess.check_output(("git", "ls-files", "-z"), cwd=REPO_ROOT)
    return [path for path in output.decode().split("\0") if path]


def _tracked_root_entries() -> set[str]:
    return {path.split("/", 1)[0] for path in _tracked_paths()}


def _visible_untracked_root_entries() -> set[str]:
    output = subprocess.check_output(
        ("git", "ls-files", "--others", "--exclude-standard", "-z"), cwd=REPO_ROOT
    )
    return {
        path.split("/", 1)[0]
        for path in output.decode().split("\0")
        if path
    }


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "root directory governance contract is missing"
    return json.loads(CONTRACT_PATH.read_text())


def _classified_root_entries() -> set[str]:
    contract = _contract()
    entries: set[str] = set()
    for section in CONTRACT_SECTIONS:
        section_items = contract.get(section)
        assert isinstance(section_items, list), f"{section} must be a list"
        entries.update(item["path"] for item in section_items)
    return entries


def test_every_visible_root_entry_is_classified():
    visible_root_entries = _tracked_root_entries() | _visible_untracked_root_entries()
    assert visible_root_entries == _classified_root_entries()


def test_root_contract_keeps_status_and_reason_for_every_entry():
    allowed_statuses = {
        "entrypoint",
        "config",
        "source_directory",
        "project_asset_directory",
        "deployment_directory",
        "test_directory",
        "legacy_tracked_metadata",
    }

    for section in CONTRACT_SECTIONS:
        for item in _contract()[section]:
            assert "/" not in item["path"]
            assert item["status"] in allowed_statuses
            assert item["reason"].strip()


def test_no_tracked_root_file_uses_temporary_or_screenshot_naming():
    contract = _contract()
    allowed_root_files = {
        item["path"] for item in contract["allowed_root_files"]
    }
    forbidden_markers = tuple(contract["forbidden_root_file_markers"])
    forbidden_suffixes = tuple(contract["forbidden_root_file_suffixes"])

    for path in _tracked_paths():
        if "/" in path:
            continue
        assert path in allowed_root_files
        lower_path = path.lower()
        assert not any(marker in lower_path for marker in forbidden_markers)
        assert not lower_path.endswith(forbidden_suffixes)


def test_local_only_root_artifacts_are_explicitly_gitignored():
    gitignore_text = GITIGNORE_PATH.read_text()

    for item in _contract()["local_only_root_artifacts"]:
        pattern = item["path"]
        assert item["status"] == "gitignored_local_only"
        assert pattern in gitignore_text
        subprocess.check_call(("git", "check-ignore", "-q", pattern), cwd=REPO_ROOT)


def test_root_governance_runbook_covers_contract_and_safe_targets():
    runbook_text = RUNBOOK_PATH.read_text()
    contract = _contract()

    assert "root-directory-governance-contract.json" in runbook_text
    assert "tmp/" in runbook_text
    assert "drafts/" in runbook_text
    assert "archive/" in runbook_text

    for section in CONTRACT_SECTIONS:
        assert section in runbook_text
        for item in contract[section]:
            assert item["path"] in runbook_text
