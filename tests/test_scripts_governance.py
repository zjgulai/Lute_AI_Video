"""Static guards for scripts/ naming and location governance."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
CONTRACT_PATH = REPO_ROOT / "configs" / "scripts-governance-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "scripts-governance.md"

SCRIPT_CATEGORIES = (
    "active_reusable_scripts",
    "manual_deploy_scripts",
    "provider_probe_scripts",
    "legacy_one_off_scripts",
    "historical_e2e_scripts",
)

ALLOWED_STATUSES = {
    "active_reusable",
    "manual_deploy_only",
    "provider_probe",
    "archive_candidate",
    "historical_e2e",
}

AMBIGUOUS_NAME_MARKERS = (
    "apply_fix",
    "bugfix",
    "fix_",
    "overwrite",
    "patch_",
    "phase",
    "_now",
    "_v2",
    "sync_",
    "test_",
)


def _script_paths() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in SCRIPTS_DIR.iterdir()
        if path.is_file()
    }


def _contract() -> dict:
    assert CONTRACT_PATH.exists(), "scripts governance contract is missing"
    return json.loads(CONTRACT_PATH.read_text())


def _contract_items() -> list[dict]:
    contract = _contract()
    items: list[dict] = []
    for category in SCRIPT_CATEGORIES:
        category_items = contract.get(category)
        assert isinstance(category_items, list), f"{category} must be a list"
        items.extend(category_items)
    return items


def _classified_paths() -> set[str]:
    return {item["path"] for item in _contract_items()}


def test_every_top_level_script_is_classified_in_governance_contract():
    script_paths = _script_paths()
    classified_paths = _classified_paths()

    assert script_paths == classified_paths


def test_script_contract_uses_explicit_statuses_and_project_paths():
    for item in _contract_items():
        assert item["path"].startswith("scripts/")
        assert item["path"].count("/") == 1
        assert item["status"] in ALLOWED_STATUSES
        assert item["reason"].strip()


def test_ambiguous_script_names_are_not_marked_active_reusable():
    for item in _contract_items():
        filename = Path(item["path"]).name
        has_ambiguous_marker = any(marker in filename for marker in AMBIGUOUS_NAME_MARKERS)

        if has_ambiguous_marker:
            assert item["status"] != "active_reusable", (
                f"{item['path']} has an ambiguous or one-off name and must not be "
                "classified as active_reusable"
            )


def test_provider_probe_scripts_are_not_called_by_default_entrypoints():
    provider_probe_names = {
        Path(item["path"]).name
        for item in _contract().get("provider_probe_scripts", [])
    }
    entrypoints = (
        REPO_ROOT / "Makefile",
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
        REPO_ROOT / ".github" / "workflows" / "deploy.yml",
        REPO_ROOT / ".github" / "workflows" / "e2e-prod.yml",
        REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh",
        REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh",
        REPO_ROOT / "scripts" / "run_s1_s5_hermetic_regression.sh",
    )

    for entrypoint in entrypoints:
        text = entrypoint.read_text()
        for script_name in provider_probe_names:
            assert script_name not in text, f"{entrypoint} must not run {script_name} by default"


def test_generated_script_artifacts_have_cleanup_policy_without_implicit_delete():
    generated_artifacts = list(SCRIPTS_DIR.rglob("__pycache__/*")) + list(SCRIPTS_DIR.rglob("*.pyc"))
    contract = _contract()
    policies = contract.get("generated_artifact_policies", [])

    if generated_artifacts:
        assert {
            "pattern": "scripts/__pycache__/**",
            "status": "cleanup_requires_confirmation",
        } in policies


def test_scripts_governance_runbook_covers_contract_and_cleanup_boundary():
    runbook_text = RUNBOOK_PATH.read_text()
    contract = _contract()

    assert "scripts-governance-contract.json" in runbook_text
    assert "cleanup_requires_confirmation" in runbook_text
    assert "不直接删除" in runbook_text

    for category in SCRIPT_CATEGORIES:
        assert category in runbook_text
        for item in contract[category]:
            assert item["path"] in runbook_text
