"""Static guard for Docker/CI dev-tool and lockfile parity."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "docker-dev-tool-parity-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "docker-dev-tool-parity.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_PATH = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
E2E_UI_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-ui.yml"
E2E_PROD_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-prod.yml"
GH_PAGES_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-gh-pages.yml"
WEB_DOCKERFILE = REPO_ROOT / "web" / "Dockerfile"
WEB_PACKAGE_JSON = REPO_ROOT / "web" / "package.json"
WEB_PACKAGE_LOCK = REPO_ROOT / "web" / "package-lock.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "Docker dev-tool parity contract is missing"
    data = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "Docker dev-tool parity contract must be a JSON object"
    return data


def _workflow(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{path} must be a YAML object"
    return data


def _workflow_text(path: Path) -> str:
    return path.read_text()


def _requirement_names(lines: list[str]) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", stripped)
        if match:
            requirements[match.group(1).lower()] = stripped
    return requirements


def _scope_targets() -> set[str]:
    return {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_python_dev_tools_are_declared_in_pyproject_and_requirements() -> None:
    contract = _contract()
    pyproject = tomllib.loads(PYPROJECT.read_text())
    dev_deps = _requirement_names(pyproject["project"]["optional-dependencies"]["dev"])
    req_deps = _requirement_names(REQUIREMENTS.read_text().splitlines())

    for tool in contract["python_dev_tools"]:
        assert tool in dev_deps, f"{tool} missing from pyproject dev dependencies"
        assert tool in req_deps, f"{tool} missing from requirements.txt"
        assert dev_deps[tool] == req_deps[tool], f"{tool} spec differs between pyproject and requirements"


def test_frontend_lockfile_matches_declared_dev_tools() -> None:
    contract = _contract()
    package = json.loads(WEB_PACKAGE_JSON.read_text())
    package_lock = json.loads(WEB_PACKAGE_LOCK.read_text())
    root_lock = package_lock["packages"][""]

    assert package_lock["lockfileVersion"] >= 3
    assert root_lock["name"] == package["name"]
    assert root_lock["version"] == package["version"]

    for tool in contract["frontend_dev_tools"]:
        assert tool in package["devDependencies"], f"{tool} missing from package.json devDependencies"
        assert root_lock["devDependencies"][tool] == package["devDependencies"][tool]


def test_frontend_dockerfile_requires_lockfile_and_never_falls_back_to_npm_install() -> None:
    dockerfile = WEB_DOCKERFILE.read_text()

    assert "COPY package.json package-lock.json ./" in dockerfile
    assert "package-lock.json*" not in dockerfile
    assert "RUN npm ci --ignore-scripts" in dockerfile
    assert "npm install" not in dockerfile
    assert "|| npm install" not in dockerfile


def test_workflow_node_jobs_use_npm_ci_and_package_lock_cache() -> None:
    contract = _contract()

    for workflow_path in contract["node_workflows"]:
        text = _workflow_text(REPO_ROOT / workflow_path)
        workflow = _workflow(REPO_ROOT / workflow_path)

        assert "npm ci" in text, f"{workflow_path} must install from package-lock via npm ci"
        assert "npm install" not in text, f"{workflow_path} must not fall back to npm install"

        jobs = workflow.get("jobs") or {}
        assert jobs, f"{workflow_path} must contain jobs"
        setup_node_steps = [
            step
            for job in jobs.values()
            for step in (job.get("steps") or [])
            if str(step.get("uses", "")).startswith("actions/setup-node@")
        ]
        assert setup_node_steps, f"{workflow_path} must set up Node with npm cache"

        for step in setup_node_steps:
            action_ref = str(step["uses"]).removeprefix("actions/setup-node@")
            assert action_ref == "v6" or (
                len(action_ref) == 40
                and all(character in "0123456789abcdef" for character in action_ref)
            ), f"{workflow_path} setup-node must use v6 or a pinned v6 commit"
            with_config = step.get("with") or {}
            assert with_config.get("cache") == "npm"
            assert with_config.get("cache-dependency-path") == "web/package-lock.json"


def test_docker_dev_tool_parity_contract_is_documented_and_link_checked() -> None:
    contract = _contract()
    runbook_text = RUNBOOK_PATH.read_text()
    scope_targets = _scope_targets()
    ci_text = CI_PATH.read_text()

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert "docker-dev-tool-parity-contract.json" in runbook_text
    assert "tests/test_docker_dev_tool_parity.py" in runbook_text
    assert "npm ci" in runbook_text
    assert "package-lock.json" in runbook_text
    assert "pytest-timeout" in runbook_text
    assert "不启动容器" in runbook_text
    assert "docs/runbooks/docker-dev-tool-parity.md" in scope_targets
    assert "docs/runbooks/docker-dev-tool-parity.md" in ci_text
