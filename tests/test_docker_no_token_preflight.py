"""Static guard for Docker build and compose no-token preflight.

Docker validation in CI must prove image/compose configuration integrity
without starting services or passing provider credentials into build steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "docker-no-token-preflight.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

PROVIDER_SECRET_NAMES = {
    "API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "POYO_API_KEY",
    "SEEDANCE_API_KEY",
    "SILICONFLOW_API_KEY",
    "ELEVENLABS_API_KEY",
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_PUBLISH_ENABLED",
    "SHOPIFY_STORE_URL",
    "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_PUBLISH_ENABLED",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "RUN_TOKEN_SMOKE",
}

FORBIDDEN_COMPOSE_PREVIEW_COMMANDS = (
    "docker compose up",
    "docker-compose up",
    "docker compose run",
    "docker-compose run",
    "docker compose exec",
    "docker-compose exec",
    "curl ",
    "/api/fast",
    "/api/scenario",
    "/api/pipeline",
    "/gate/",
    "RUN_TOKEN_SMOKE=1",
)


def _load_workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _step_by_name(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [step for step in steps if step.get("name") == name]
    assert matches, f"missing workflow step: {name}"
    return matches[0]


def _build_args_map(step: dict[str, Any]) -> dict[str, str]:
    raw_args = step.get("with", {}).get("build-args") or ""
    build_args: dict[str, str] = {}
    for line in raw_args.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("=")
        build_args[key.strip()] = value.strip()
    return build_args


def _job_text(job: dict[str, Any]) -> str:
    return yaml.safe_dump(job, sort_keys=True)


def test_ci_and_deploy_docker_builds_are_secret_free():
    ci_job = _load_workflow(CI_YML)["jobs"]["docker-build"]
    build_step = _step_by_name(
        ci_job.get("steps") or [], "Build backend image (validate, no push)"
    )
    build_with = build_step.get("with") or {}
    assert build_with.get("push") is False
    assert build_with.get("load") is True
    assert set(_build_args_map(build_step)) == {"APT_MIRROR", "RELEASE_SOURCE_SHA"}
    assert _build_args_map(build_step)["RELEASE_SOURCE_SHA"] == "${{ github.sha }}"
    scan_step = _step_by_name(ci_job.get("steps") or [], "Scan backend image")
    assert scan_step.get("with", {}).get("image-ref") == "ai-video-backend:ci-${{ github.sha }}"

    deploy_job = _load_workflow(DEPLOY_YML)["jobs"]["build-images"]
    for step_name in ("Build backend image", "Build frontend image", "Build rendering image"):
        job = deploy_job
        build_step = _step_by_name(job.get("steps") or [], step_name)
        build_with = build_step.get("with") or {}

        assert build_step.get("uses") == (
            "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"
        )
        assert build_with.get("push") is False
        assert build_with.get("load") is True

        build_args = _build_args_map(build_step)
        assert build_args.get("RELEASE_SOURCE_SHA") == "${{ github.sha }}"
        assert not (set(build_args) & PROVIDER_SECRET_NAMES)

    for job in (ci_job, deploy_job):
        job_text = _job_text(job)
        assert "secrets." not in job_text
        for secret_name in PROVIDER_SECRET_NAMES:
            assert f"secrets.{secret_name}" not in job_text


def test_ci_and_deploy_validate_compose_config_without_starting_services():
    workflow_jobs = [
        _load_workflow(CI_YML)["jobs"]["docker-build"],
        _load_workflow(DEPLOY_YML)["jobs"]["preflight"],
    ]

    for job in workflow_jobs:
        step = _step_by_name(job.get("steps") or [], "Docker compose config validation (no start)")
        run = step.get("run") or ""

        assert ": > .env" in run
        assert "docker compose -f docker-compose.yml config --quiet" in run
        assert (
            "docker compose -f deploy/lighthouse/docker-compose.release.yml config --quiet"
            in run
        )
        assert "RELEASE_SOURCE_SHA=" in run
        assert "RELEASE_IMAGE_TAG=" in run
        assert "AI_VIDEO_ENV_FILE=/dev/null" in run
        assert "PORTAL_AUTH_ENV_FILE=/dev/null" in run

        for forbidden in FORBIDDEN_COMPOSE_PREVIEW_COMMANDS:
            assert forbidden not in run
        for secret_name in PROVIDER_SECRET_NAMES:
            assert f"{secret_name}=" not in run


def test_docker_no_token_preflight_runbook_documents_boundaries():
    assert RUNBOOK.exists(), "Docker no-token preflight runbook is missing"

    text = RUNBOOK.read_text()
    required_phrases = [
        "docker compose config --quiet",
        "docker/build-push-action@v7",
        "push: false",
        "load: false",
        "不启动容器",
        "不调用 `/health`",
        "不读取生产 secret",
        "不触发 provider",
    ]
    for phrase in required_phrases:
        assert phrase in text

    forbidden_phrases = [
        "docker compose up",
        "docker compose run",
        "RUN_TOKEN_SMOKE=1",
        "POYO_API_KEY=sk-",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in text


def test_docker_no_token_preflight_runbook_is_link_checked():
    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "docs/runbooks/docker-no-token-preflight.md" in scope_targets
