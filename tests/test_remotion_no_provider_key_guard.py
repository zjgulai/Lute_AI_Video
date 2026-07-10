"""Static guard for Remotion rendering no-provider-key boundary."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "remotion-no-provider-key-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "remotion-no-provider-key.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_PATH = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
PROD_COMPOSE_PATH = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"
LOCAL_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "Remotion no-provider-key contract is missing"
    data = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "Remotion no-provider-key contract must be a JSON object"
    return data


def _tracked_rendering_paths() -> list[Path]:
    output = subprocess.check_output(("git", "ls-files", "-z", "rendering"), cwd=REPO_ROOT)
    return [
        REPO_ROOT / path
        for path in output.decode().split("\0")
        if path
    ]


def _scope_targets() -> set[str]:
    return {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _workflow(path: Path) -> dict[str, Any]:
    workflow = yaml.safe_load(path.read_text())
    assert isinstance(workflow, dict), f"{path} must be a YAML object"
    return workflow


def _workflow_steps(path: Path) -> list[dict[str, Any]]:
    jobs = (_workflow(path).get("jobs") or {}).values()
    return [
        step
        for job in jobs
        for step in (job.get("steps") or [])
        if isinstance(step, dict)
    ]


def _env_entries(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        return {f"{key}={val}" for key, val in value.items()}
    if isinstance(value, list):
        return {str(item) for item in value}
    raise AssertionError(f"unexpected environment shape: {type(value).__name__}")


def _docker_runtime_env_assignments(dockerfile: str) -> set[str]:
    """Return ENV names without treating build-only ARG values as runtime env."""

    logical_lines: list[str] = []
    pending = ""
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip() if pending else line
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical_lines.append(pending)
        pending = ""

    assert not pending, "Dockerfile must not end with an incomplete instruction"
    return {
        name
        for line in logical_lines
        if line.startswith("ENV ")
        for name in re.findall(r"\b([A-Z][A-Z0-9_]*)=", line)
    }


def test_docker_runtime_env_parser_excludes_build_args() -> None:
    env_names = _docker_runtime_env_assignments(
        """
        ARG ALPINE_MIRROR=https://example.invalid/alpine
        ENV PORT=3001 \\
            OUTPUT_DIR=/tmp/output
        """
    )

    assert env_names == {"PORT", "OUTPUT_DIR"}


def test_tracked_rendering_files_do_not_reference_provider_credentials_or_apis() -> None:
    contract = _contract()
    forbidden_markers = tuple(
        contract["forbidden_provider_env_names"] + contract["forbidden_provider_markers"]
    )

    for path in _tracked_rendering_paths():
        text = path.read_text()
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for marker in forbidden_markers:
            assert marker not in text, f"{rel_path} must not reference provider marker {marker}"


def test_rendering_env_reads_are_limited_to_local_runtime_controls() -> None:
    contract = _contract()
    allowed_env_names = set(contract["allowed_env_names"])
    text = "\n".join(path.read_text() for path in _tracked_rendering_paths())

    js_env_reads = set(re.findall(r"process\.env\.([A-Z0-9_]+)", text))
    docker_env_assignments = _docker_runtime_env_assignments(
        (REPO_ROOT / "rendering" / "Dockerfile").read_text()
    )

    assert js_env_reads <= allowed_env_names
    assert docker_env_assignments <= allowed_env_names


def test_lighthouse_rendering_service_receives_only_local_runtime_env() -> None:
    contract = _contract()
    compose = yaml.safe_load(PROD_COMPOSE_PATH.read_text())
    service = compose["services"]["rendering"]

    assert service["build"]["context"] == "../../rendering"
    assert service["build"]["dockerfile"] == "Dockerfile"
    assert _env_entries(service.get("environment")) == set(contract["rendering_compose_env"])
    assert "env_file" not in service


def test_local_compose_does_not_define_a_provider_enabled_rendering_service() -> None:
    compose = yaml.safe_load(LOCAL_COMPOSE_PATH.read_text())
    services = compose.get("services") or {}

    assert "rendering" not in services
    backend = services["backend"]
    backend_volumes = set(backend.get("volumes") or [])
    assert "./rendering:/app/rendering" in backend_volumes


def test_ci_and_deploy_do_not_run_rendering_with_provider_env() -> None:
    contract = _contract()
    forbidden_env = set(contract["forbidden_provider_env_names"])

    for workflow_path in (CI_PATH, DEPLOY_PATH):
        for step in _workflow_steps(workflow_path):
            working_directory = step.get("working-directory")
            run = step.get("run") or ""
            env = step.get("env") or {}

            if working_directory == "rendering" or "cd rendering" in run:
                assert forbidden_env.isdisjoint(env)
                assert "RUN_TOKEN_SMOKE=1" not in run


def test_remotion_no_provider_contract_is_documented_and_link_checked() -> None:
    contract = _contract()
    runbook_text = RUNBOOK_PATH.read_text()
    scope_targets = _scope_targets()
    ci_text = CI_PATH.read_text()

    assert contract["status"] == "stable"
    assert contract["no_token_boundary"] is True
    assert "remotion-no-provider-key-contract.json" in runbook_text
    assert "tests/test_remotion_no_provider_key_guard.py" in runbook_text
    assert "PORT" in runbook_text
    assert "OUTPUT_DIR" in runbook_text
    assert "POYO_API_KEY" in runbook_text
    assert "不执行 Docker build" in runbook_text
    assert "docs/runbooks/remotion-no-provider-key.md" in scope_targets
    assert "docs/runbooks/remotion-no-provider-key.md" in ci_text
