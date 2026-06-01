"""Static guard for GitHub Actions path-filter trigger coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "workflow-trigger-path-audit-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "workflow-trigger-path-audit.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "workflow trigger path audit contract is missing"
    data = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "workflow trigger path audit contract must be a JSON object"
    return data


def _workflow(path: str) -> dict[str, Any]:
    workflow = yaml.safe_load((REPO_ROOT / path).read_text())
    assert isinstance(workflow, dict), f"{path} must be a YAML object"
    return workflow


def _trigger(workflow: dict[str, Any]) -> dict[str, Any]:
    trigger = workflow.get(True) or workflow.get("on")
    assert isinstance(trigger, dict), "workflow trigger must be a YAML mapping"
    return trigger


def _scope_targets() -> set[str]:
    return {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_path_filtered_workflows_cover_required_sources_configs_and_locks() -> None:
    contract = _contract()

    for item in contract["path_filtered_workflows"]:
        workflow_path = item["path"]
        workflow = _workflow(workflow_path)
        trigger = _trigger(workflow)

        for event in item["events"]:
            event_config = trigger.get(event)
            assert isinstance(event_config, dict), f"{workflow_path} {event} must be configured"

            actual_paths = event_config.get("paths")
            assert isinstance(actual_paths, list), f"{workflow_path} {event} must use paths"

            missing = sorted(set(item["required_paths"]) - set(actual_paths))
            assert missing == [], f"{workflow_path} {event} missing path filters: {missing}"

            for forbidden in item.get("forbidden_paths", []):
                assert forbidden not in actual_paths, (
                    f"{workflow_path} {event} should not use broad/noisy path filter: {forbidden}"
                )


def test_unfiltered_workflows_do_not_hide_source_changes_with_paths() -> None:
    contract = _contract()

    for item in contract["unfiltered_workflows"]:
        workflow_path = item["path"]
        workflow = _workflow(workflow_path)
        trigger = _trigger(workflow)

        for event in item["events"]:
            event_config = trigger.get(event)
            assert event_config is not None, f"{workflow_path} missing {event} trigger"
            if isinstance(event_config, dict):
                assert "paths" not in event_config
                assert "paths-ignore" not in event_config


def test_workflow_trigger_path_contract_is_documented_and_no_token() -> None:
    contract = _contract()
    runbook_text = RUNBOOK_PATH.read_text()

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert "workflow-trigger-path-audit-contract.json" in runbook_text
    assert "tests/test_workflow_trigger_path_audit.py" in runbook_text
    assert "web/package-lock.json" in runbook_text
    assert "path-filtered workflow" in runbook_text
    assert "不触发生产" in runbook_text


def test_workflow_trigger_path_runbook_is_link_checked() -> None:
    scope_targets = _scope_targets()
    ci_text = CI_PATH.read_text()

    assert "docs/runbooks/workflow-trigger-path-audit.md" in scope_targets
    assert "docs/runbooks/workflow-trigger-path-audit.md" in ci_text
