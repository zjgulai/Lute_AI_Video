"""Fail-closed contracts for the PR exact-image security review workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "image-security-review.yml"
RAW_GRYPE_POLICY = REPO_ROOT / ".grype-raw.yaml"


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
    assert isinstance(workflow, dict)
    return workflow


def _step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(step for step in steps if step.get("name") == name)


def test_security_review_is_exact_sha_read_only_and_never_deploys() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["env"]["REVIEW_SOURCE_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )

    serialized = WORKFLOW_PATH.read_text()
    for forbidden in (
        "workflow_dispatch",
        "secrets.",
        "docker push",
        "ssh ",
        "rsync ",
    ):
        assert forbidden not in serialized

    steps = workflow["jobs"]["scan"]["steps"]
    checkout = steps[0]
    assert checkout["with"] == {
        "ref": "${{ env.REVIEW_SOURCE_SHA }}",
        "persist-credentials": False,
    }
    identity = _step(steps, "Verify exact image source label")
    assert "org.opencontainers.image.revision" in identity["run"]
    assert 'test "$actual" = "$REVIEW_SOURCE_SHA"' in identity["run"]
    boundary = _step(steps, "Verify vulnerable-tool boundary")
    assert boundary["if"] == "${{ matrix.component != 'frontend' }}"
    assert boundary["continue-on-error"] is True
    assert "--network none" in boundary["run"]
    assert "command -v tiffcrop" in boundary["run"]
    assert "src/tools/safe_media.py" in WORKFLOW_PATH.read_text()
    assert "src/services/safe_media.py" not in WORKFLOW_PATH.read_text()


def test_security_review_matrix_covers_all_release_images_and_policies() -> None:
    workflow = _workflow()
    matrix = workflow["jobs"]["scan"]["strategy"]["matrix"]["include"]
    actual = {
        item["component"]: (
            item["dockerfile"],
            item["grype_policy"],
            item["trivy_policy"],
        )
        for item in matrix
    }
    assert actual == {
        "backend": (
            "./Dockerfile.backend",
            ".grype-backend.yaml",
            ".trivyignore-backend.yaml",
        ),
        "frontend": (
            "./web/Dockerfile",
            ".grype.yaml",
            ".trivyignore.yaml",
        ),
        "rendering": (
            "./rendering/Dockerfile",
            ".grype-rendering.yaml",
            ".trivyignore-rendering.yaml",
        ),
    }
    assert workflow["jobs"]["scan"]["strategy"]["fail-fast"] is False


def test_security_review_retains_raw_and_reviewed_dual_scanner_evidence() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["scan"]["steps"]

    grype_raw = _step(steps, "Capture raw Grype evidence")
    assert grype_raw["with"]["fail-build"] is False
    assert grype_raw["with"]["severity-cutoff"] == "high"
    assert grype_raw["with"]["output-format"] == "json"
    assert grype_raw["with"]["config"] == ".grype-raw.yaml"
    assert yaml.safe_load(RAW_GRYPE_POLICY.read_text()) == {"ignore": []}

    grype_reviewed = _step(steps, "Apply reviewed Grype policy")
    assert grype_reviewed["with"]["config"] == "${{ matrix.grype_policy }}"
    assert grype_reviewed["with"]["fail-build"] is True
    assert grype_reviewed["continue-on-error"] is True

    trivy_raw = _step(steps, "Capture raw Trivy evidence")
    assert trivy_raw["with"]["exit-code"] == 0
    assert trivy_raw["with"]["ignore-unfixed"] is False
    assert trivy_raw["with"]["scanners"] == "vuln"
    assert "env" not in trivy_raw

    trivy_reviewed = _step(steps, "Apply reviewed Trivy policy")
    assert trivy_reviewed["env"] == {
        "TRIVY_IGNOREFILE": "${{ matrix.trivy_policy }}"
    }
    assert trivy_reviewed["with"]["exit-code"] == 1
    assert trivy_reviewed["continue-on-error"] is True

    upload = _step(steps, "Upload exact scanner evidence")
    assert upload["if"] == "always()"
    assert upload["with"]["retention-days"] == 14
    for marker in ("grype-", "trivy-", "-raw.json", "-reviewed.json"):
        assert marker in upload["with"]["path"]

    enforce = _step(steps, "Enforce reviewed High/Critical policy")
    assert enforce["if"] == "always()"
    assert enforce["run"].count('= success') == 8
    assert 'if [ "$COMPONENT" != frontend ]' in enforce["run"]
