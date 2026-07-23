"""W3 runtime, lock, typecheck, and vulnerability gate contracts."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
PYTHON_VERSION = REPO_ROOT / ".python-version"
BACKEND_DOCKERFILES = (REPO_ROOT / "Dockerfile", REPO_ROOT / "Dockerfile.backend")
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
MAKEFILE = REPO_ROOT / "Makefile"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
LEGACY_PROD_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"
RENDER_BLUEPRINT = REPO_ROOT / "render.yaml"
VULNERABILITY_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "vulnerability-scan-exceptions.md"

PINNED_PYTHON = "3.12.13"
RUNTIME_MEDIA_DEPENDENCIES = {
    "faster-whisper",
    "pillow",
    "torch",
    "transformers",
    "yt-dlp",
}

FINAL_E1_IMAGE_ID = "sha256:01b2e4bc18f59ba14032a696405ec0263c9cc5ff30add4b666fb26fff7a5e5c4"
FINAL_E1_REVISION = "local-w3-e1-review-fix-3"


def _dependency_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~;\s]", requirement.strip(), maxsplit=1)[0].replace("_", "-").lower()


def _workflow(path: Path) -> dict[str, Any]:
    parsed = yaml.safe_load(path.read_text())
    assert isinstance(parsed, dict)
    return parsed


def _all_run_commands(workflow: dict[str, Any]) -> str:
    return "\n".join(
        str(step.get("run") or "")
        for job in (workflow.get("jobs") or {}).values()
        for step in (job.get("steps") or [])
    )


def test_python_31213_is_the_single_project_tool_and_ci_version() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text())
    assert PYTHON_VERSION.read_text().strip() == PINNED_PYTHON
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["pyright"]["pythonVersion"] == "3.12"

    for path in (CI, DEPLOY):
        workflow = _workflow(path)
        versions = {
            str((step.get("with") or {}).get("python-version"))
            for job in (workflow.get("jobs") or {}).values()
            for step in (job.get("steps") or [])
            if str(step.get("uses") or "").startswith("actions/setup-python@")
        }
        assert versions == {PINNED_PYTHON}, f"{path.name} Python versions drifted: {versions}"


def test_pyproject_and_uv_lock_cover_the_full_production_dependency_set() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text())
    runtime = {_dependency_name(item) for item in pyproject["project"]["dependencies"]}
    assert RUNTIME_MEDIA_DEPENDENCIES <= runtime
    assert not (RUNTIME_MEDIA_DEPENDENCIES - {"pillow"}) & {
        _dependency_name(item)
        for item in pyproject["project"]["optional-dependencies"]["dev"]
    }

    lock_text = UV_LOCK.read_text()
    for dependency in RUNTIME_MEDIA_DEPENDENCIES:
        assert f'name = "{dependency}"' in lock_text

    torch_source = pyproject["tool"]["uv"]["sources"]["torch"]
    assert torch_source == {"index": "pytorch-cpu"}
    pytorch_index = next(
        item for item in pyproject["tool"]["uv"]["index"] if item["name"] == "pytorch-cpu"
    )
    assert pytorch_index == {
        "name": "pytorch-cpu",
        "url": "https://download.pytorch.org/whl/cpu",
        "explicit": True,
    }


def test_backend_images_use_digest_pinned_python_and_locked_uv_sync() -> None:
    expected_prefix = f"FROM python:{PINNED_PYTHON}-slim-trixie@sha256:"
    for path in BACKEND_DOCKERFILES:
        text = path.read_text()
        assert text.startswith(expected_prefix), path.name
        assert re.search(r"^FROM python:.*@sha256:[0-9a-f]{64}$", text, re.MULTILINE)
        assert "COPY pyproject.toml uv.lock ./" in text
        assert "uv sync --locked --no-dev" in text
        assert 'ENV PATH="/app/.venv/bin:$PATH"' in text
        assert "pip install" not in text
        assert "-r requirements.txt" not in text
        assert "gcc libpq-dev" not in text
        assert text.index("uv sync --locked --no-dev") < text.index(
            "ARG RELEASE_SOURCE_SHA"
        )


def test_all_documented_backend_container_entrypoints_use_the_canonical_locked_image() -> None:
    for path in (LOCAL_COMPOSE, LEGACY_PROD_COMPOSE):
        compose = _workflow(path)
        backend = compose["services"]["backend"]
        build = backend["build"]
        assert build["dockerfile"] == "Dockerfile.backend"
        serialized = path.read_text()
        assert "python:3.12-slim" not in serialized
        assert "requirements.txt" not in serialized
        assert "pip install" not in serialized

    render = _workflow(RENDER_BLUEPRINT)
    backend = render["services"][0]
    assert backend["dockerfilePath"] == "./Dockerfile.backend"
    paths = set(backend["buildFilter"]["paths"])
    assert {"Dockerfile.backend", "pyproject.toml", "uv.lock"} <= paths
    assert "requirements.txt" not in paths


def test_ci_and_deploy_preflight_sync_the_same_locked_environment() -> None:
    for path in (CI, DEPLOY):
        commands = _all_run_commands(_workflow(path))
        assert "uv sync --locked --extra dev" in commands, path.name
        assert 'pip install -e ".[dev]"' not in commands, path.name
        assert "pip install ruff" not in commands, path.name


def test_typecheck_is_a_real_make_and_ci_gate() -> None:
    makefile = MAKEFILE.read_text()
    ci_commands = _all_run_commands(_workflow(CI))
    assert re.search(r"^typecheck:", makefile, re.MULTILINE)
    assert "pyright" in makefile
    assert "check_pyright_ratchet.py" in makefile
    assert "make typecheck" in ci_commands


def test_ci_has_blocking_python_node_and_image_vulnerability_gates() -> None:
    workflow = _workflow(CI)
    commands = _all_run_commands(workflow)
    assert "pip-audit" in commands
    assert "npm audit --omit=dev --audit-level=high" in commands
    assert "web/package-lock.json" in CI.read_text()
    assert "rendering/package-lock.json" in CI.read_text()

    image_scan_steps = [
        step
        for job in (workflow.get("jobs") or {}).values()
        for step in (job.get("steps") or [])
        if "trivy" in str(step.get("uses") or "").lower()
        or "grype" in str(step.get("uses") or "").lower()
    ]
    assert image_scan_steps, "CI must block on a backend image vulnerability scan"
    serialized = "\n".join(str(step) for step in image_scan_steps).lower()
    assert "high" in serialized
    assert "critical" in serialized
    for step in image_scan_steps:
        with_config = step.get("with") or {}
        assert with_config.get("ignore-unfixed") is False
        assert with_config.get("exit-code") == 1
        assert with_config.get("scanners") == "vuln"
        assert "trivyignores" not in with_config
        assert (step.get("env") or {}).get("TRIVY_IGNOREFILE") == ".trivyignore.yaml"
        assert with_config.get("severity") == "HIGH,CRITICAL"


def test_vulnerability_runbook_records_the_final_e1_image_evidence() -> None:
    text = VULNERABILITY_RUNBOOK.read_text()

    assert FINAL_E1_IMAGE_ID in text
    assert FINAL_E1_REVISION in text
    assert "local-w3-e1-review-fix-2" not in text
