"""Static validation of GitHub Actions workflows (NEXT-4 code-side).

Verifies that .github/workflows/deploy.yml is syntactically valid AND
structurally sound. Catches regressions a real `actionlint` run would catch:
- Missing required keys (jobs / runs-on / steps)
- Undeclared secret references
- Broken environment / approval gate setup
- Smoke test step actually checks /health

Does NOT exercise GitHub Actions runtime — that requires a real PR/push.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WORKFLOW_YMLS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"
LIGHTHOUSE_DEPLOY = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
LIGHTHOUSE_BUILD_AND_DEPLOY = REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh"
LIGHTHOUSE_RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
RENDERING_DOCKERFILE = REPO_ROOT / "rendering" / "Dockerfile"
RENDERING_SERVER = REPO_ROOT / "rendering" / "server.mjs"

HERMETIC_PYTEST_ENV = {
    "API_KEY": "test-api-key-for-pytest",
    "OPENAI_API_KEY": "sk-test",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "DEEPSEEK_API_KEY": "",
    "POYO_API_KEY": "",
    "SEEDANCE_API_KEY": "",
    "SILICONFLOW_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "TIKTOK_ACCESS_TOKEN": "",
    "TIKTOK_PUBLISH_ENABLED": "false",
    "SHOPIFY_STORE_URL": "",
    "SHOPIFY_ACCESS_TOKEN": "",
    "SHOPIFY_PUBLISH_ENABLED": "false",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_KEY": "",
}


def _step_by_name(steps: list[dict], name: str) -> dict:
    matches = [step for step in steps if step.get("name") == name]
    assert matches, f"missing workflow step: {name}"
    return matches[0]


def _assert_hermetic_pytest_env(env: dict[str, str]) -> None:
    for key, expected in HERMETIC_PYTEST_ENV.items():
        assert env.get(key) == expected, f"{key} must be hermetic in CI pytest env"

    for key, value in env.items():
        assert "secrets." not in str(value), f"{key} must not read GitHub secrets in pytest env"


class TestDeployWorkflow:

    @pytest.fixture
    def workflow(self):
        with open(DEPLOY_YML) as f:
            return yaml.safe_load(f)

    def test_file_exists(self):
        assert DEPLOY_YML.exists()

    def test_has_workflow_dispatch_trigger(self, workflow):
        on = workflow.get(True) or workflow.get("on")
        assert on is not None, "workflow has no 'on' trigger"
        assert "workflow_dispatch" in on, "workflow_dispatch trigger required for manual deploy"

    def test_workflow_dispatch_requires_reason_input(self, workflow):
        on = workflow.get(True) or workflow.get("on")
        wd = on.get("workflow_dispatch") or {}
        inputs = wd.get("inputs") or {}
        assert "reason" in inputs, "workflow_dispatch must require 'reason' input for audit trail"
        assert inputs["reason"].get("required") is True

    def test_has_concurrency_lock(self, workflow):
        assert "concurrency" in workflow, "deploy must use concurrency to prevent parallel runs"
        c = workflow["concurrency"]
        assert "group" in c
        assert c.get("cancel-in-progress") is False, (
            "deploy must NOT cancel in-progress run (data integrity)"
        )

    def test_has_required_jobs(self, workflow):
        jobs = workflow.get("jobs") or {}
        for required in ("preflight", "deploy"):
            assert required in jobs, f"missing required job: {required}"

    def test_deploy_job_depends_on_preflight(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        needs = deploy.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        assert "preflight" in needs, "deploy must run after preflight"

    def test_deploy_uses_production_environment(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        env = deploy.get("environment") or {}
        if isinstance(env, str):
            assert env == "production"
        else:
            assert env.get("name") == "production", (
                "deploy must use 'production' environment for approval gate"
            )

    def test_deploy_has_smoke_test_step(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy.get("steps") or []
        smoke_steps = [
            s for s in steps
            if "/health" in (s.get("run") or "") or "smoke" in (s.get("name") or "").lower()
        ]
        assert smoke_steps, "deploy must include a /health smoke test step"

    def test_referenced_secrets_are_documented(self, workflow):
        text = DEPLOY_YML.read_text()
        secret_refs = set(re.findall(r"secrets\.(\w+)", text))

        runbook = REPO_ROOT / "docs" / "runbooks" / "github-actions-deploy-secrets.md"
        if not runbook.exists():
            pytest.skip("Secrets runbook not present (acceptable if T9 still partial)")

        runbook_text = runbook.read_text()
        for secret in secret_refs:
            assert secret in runbook_text, (
                f"secret '{secret}' referenced in deploy.yml but not in runbook"
            )

    def test_preflight_runs_both_python_and_frontend_tests(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        step_text = " ".join((s.get("run") or "") for s in steps)
        assert "pytest" in step_text, "preflight must run pytest"
        assert "npm test -- --run" in step_text, "preflight must run frontend Vitest"

    def test_preflight_pytest_env_is_hermetic(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        test_step = _step_by_name(steps, "Test")

        _assert_hermetic_pytest_env(test_step.get("env") or {})

    def test_preflight_lints_full_python_surface(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        step_text = " ".join((s.get("run") or "") for s in steps)
        assert "ruff check src tests scripts" in step_text, (
            "deploy preflight must lint src, tests, and scripts to prevent hidden Python debt"
        )

    def test_preflight_pytest_timeout_dependency_is_declared(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        step_text = " ".join((s.get("run") or "") for s in steps)
        assert "--timeout=60" in step_text, "deploy preflight should keep a pytest timeout guard"

        pyproject = tomllib.loads(PYPROJECT.read_text())
        dev_deps = pyproject["project"]["optional-dependencies"]["dev"]
        assert any(dep.startswith("pytest-timeout") for dep in dev_deps), (
            "deploy preflight uses pytest --timeout, so pytest-timeout must be in project dev deps"
        )

        requirements = REQUIREMENTS.read_text().splitlines()
        assert any(line.startswith("pytest-timeout") for line in requirements), (
            "requirements.txt development install path must also include pytest-timeout"
        )

    def test_preflight_installs_media_tools_before_pytest(self, workflow):
        steps = workflow["jobs"]["preflight"].get("steps") or []
        step_names = [step.get("name") for step in steps]
        install_step = _step_by_name(steps, "Install media test tools")
        pytest_step = _step_by_name(steps, "Test")
        run = install_step.get("run") or ""

        assert "apt-get update" in run
        assert "apt-get install -y --no-install-recommends ffmpeg" in run
        assert step_names.index(install_step["name"]) < step_names.index(pytest_step["name"])

    def test_preflight_installs_openapi_typegen_dependencies_before_pytest(self, workflow):
        steps = workflow["jobs"]["preflight"].get("steps") or []
        step_names = [step.get("name") for step in steps]
        node_step = _step_by_name(steps, "Set up Node.js for OpenAPI type drift guard")
        install_step = _step_by_name(steps, "Install frontend deps")
        pytest_step = _step_by_name(steps, "Test")

        assert node_step["with"]["node-version"] == "22"
        assert node_step["with"]["cache"] == "npm"
        assert node_step["with"]["cache-dependency-path"] == "web/package-lock.json"
        assert install_step["working-directory"] == "web"
        assert install_step["run"] == "npm ci"
        assert step_names.index(node_step["name"]) < step_names.index(install_step["name"])
        assert step_names.index(install_step["name"]) < step_names.index(pytest_step["name"])

    def test_preflight_frontend_matches_ci_quality_gate(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        step_text = "\n".join((s.get("run") or "") for s in steps)

        required_commands = [
            "npm ci",
            "npx eslint src e2e playwright.ui.config.ts playwright.prod.config.ts",
            "npx tsc --noEmit -p tsconfig.json",
            "npm test -- --run",
            "npm run build",
        ]
        for command in required_commands:
            assert command in step_text, f"deploy preflight must run frontend quality gate: {command}"

        build_steps = [s for s in steps if s.get("name") == "Frontend build"]
        assert build_steps, "deploy preflight must build the frontend"
        assert build_steps[0].get("env", {}).get("NEXT_PUBLIC_IS_DEMO") == "true", (
            "frontend deploy preflight build must not depend on production token state"
        )

    def test_remote_deploy_disables_token_smoke_and_binds_reviewed_sha(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy.get("steps") or []
        remote_steps = [s for s in steps if s.get("name") == "Trigger remote deploy"]
        assert remote_steps, "deploy must trigger remote Lighthouse deploy"

        run = remote_steps[0].get("run") or ""
        assert "RELEASE_SOURCE_SHA=${{ github.sha }}" in run
        assert "RUN_TOKEN_SMOKE=0" in run
        assert "releases-${{ github.sha }}/deploy/lighthouse" in run
        assert "bash deploy.sh" in run

    def test_rsync_uses_lighthouse_exclude_file(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy.get("steps") or []
        rsync_step = _step_by_name(steps, "Rsync reviewed release to server")

        run = rsync_step.get("run") or ""
        assert '--exclude-from="$RUNNER_TEMP/release-excludes.zlist"' in run, (
            "GitHub deploy must use the NUL-converted Lighthouse rsync exclude SSOT"
        )
        assert "--exclude='.next'" not in run
        assert "--exclude='output'" not in run
        assert "--exclude='.pytest_cache'" not in run

    def test_lighthouse_rsync_exclude_file_covers_generated_and_secret_artifacts(self):
        excludes = set(RSYNC_EXCLUDES.read_text().splitlines())
        required_excludes = {
            ".env",
            ".git",
            ".venv",
            ".pytest_cache",
            "__pycache__",
            "node_modules",
            "output",
            "tmp",
            "web/.next",
            "web/.next.old",
            "web/node_modules",
            "web/playwright-report",
            "web/test-results",
            "rendering/node_modules",
            "deploy/lighthouse/.env.prod",
            "deploy/lighthouse/server.crt",
            "deploy/lighthouse/server.key",
            "deploy/lighthouse/*.pem",
        }

        assert required_excludes.issubset(excludes)

    def test_lighthouse_wrapper_defaults_to_dry_run_and_rejects_invalid_mode_first(self):
        text = LIGHTHOUSE_BUILD_AND_DEPLOY.read_text()

        assert 'DRY_RUN="${DRY_RUN:-1}"' in text
        invalid = subprocess.run(
            ["bash", str(LIGHTHOUSE_BUILD_AND_DEPLOY)],
            cwd=REPO_ROOT,
            env={**os.environ, "DRY_RUN": "invalid", "SSH_KEY": "/missing-key"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert invalid.returncode != 0
        assert "DRY_RUN must be 0 or 1" in invalid.stderr
        assert "SSH_KEY" not in invalid.stderr

    def test_lighthouse_wrapper_requires_clean_synchronized_main_and_exact_live_sha(self):
        text = LIGHTHOUSE_BUILD_AND_DEPLOY.read_text()

        required_fragments = [
            "symbolic-ref --quiet --short HEAD",
            "SOURCE_BRANCH",
            'SOURCE_BRANCH" != "main"',
            "status --porcelain --untracked-files=all",
            "SOURCE_SHA",
            "ls-remote --exit-code origin refs/heads/main",
            "RELEASE_SOURCE_SHA",
            'DRY_RUN" = "0"',
        ]
        for fragment in required_fragments:
            assert fragment in text

        validation_index = text.index("DRY_RUN must be 0 or 1")
        source_gate_index = text.index("symbolic-ref --quiet --short HEAD")
        rsync_index = text.index('"$RSYNC_BIN" "${RSYNC_ARGS[@]}"')
        assert validation_index < source_gate_index < rsync_index

    def test_lighthouse_wrapper_requires_pinned_ssh_identity_and_provider_off_mode(self):
        text = LIGHTHOUSE_BUILD_AND_DEPLOY.read_text()

        assert 'SSH_KNOWN_HOSTS_FILE="${SSH_KNOWN_HOSTS_FILE:-}"' in text
        assert "StrictHostKeyChecking=yes" in text
        assert 'UserKnownHostsFile="$SSH_KNOWN_HOSTS_FILE"' in text
        assert "StrictHostKeyChecking=accept-new" not in text
        assert "ssh-keyscan" not in text
        assert 'RUN_TOKEN_SMOKE="${RUN_TOKEN_SMOKE:-0}"' in text
        assert 'RUN_TOKEN_SMOKE" != "0"' in text
        assert "RUN_TOKEN_SMOKE=0" in text
        assert "RUN_TOKEN_SMOKE=${RUN_TOKEN_SMOKE" not in text

    def test_lighthouse_wrapper_syncs_to_reviewed_release_not_live_root(self):
        text = LIGHTHOUSE_BUILD_AND_DEPLOY.read_text()

        assert 'REMOTE_RELEASE_DIR="$REMOTE_DIR/releases-$SOURCE_SHA"' in text
        assert '"$SSH_USER@$SERVER_IP:$REMOTE_RELEASE_DIR/"' in text
        assert "cd '$REMOTE_RELEASE_DIR/deploy/lighthouse'" in text
        assert "AI_VIDEO_SHARED_ROOT='$REMOTE_DIR'" in text
        assert '"$SSH_USER@$SERVER_IP:$REMOTE_DIR/"' not in text
        assert '"test ! -e \'$REMOTE_RELEASE_DIR\'"' in text
        assert '"mkdir \'$REMOTE_RELEASE_DIR\'"' in text
        assert 'RELEASE_IMAGE_ARCHIVE="${RELEASE_IMAGE_ARCHIVE:-}"' in text
        assert "live deploy requires the CI-reviewed image archive and checksum" in text

    def test_release_compose_uses_sha_tagged_images_without_live_source_mounts(self):
        with open(LIGHTHOUSE_RELEASE_COMPOSE) as file:
            compose = yaml.safe_load(file)

        services = compose["services"]
        for service_name in ("backend", "frontend", "rendering"):
            service = services[service_name]
            assert "${RELEASE_IMAGE_TAG:?" in service["image"]
            assert service["build"]["args"]["RELEASE_SOURCE_SHA"].startswith(
                "${RELEASE_SOURCE_SHA:?"
            )

        backend_mounts = services["backend"].get("volumes") or []
        frontend_mounts = services["frontend"].get("volumes") or []
        assert backend_mounts == ["backend_output:/app/output"]
        assert frontend_mounts == []

        compose_text = LIGHTHOUSE_RELEASE_COMPOSE.read_text()
        assert compose["name"] == "lighthouse"
        assert "../../src:/app/src" not in compose_text
        assert "../../requirements.txt:/app/requirements.txt" not in compose_text
        assert "web/.next" not in compose_text
        assert set(services) == {"backend", "frontend", "rendering"}
        assert "portal_auth:" not in compose_text
        assert "nginx:" not in compose_text
        assert "nginx:alpine" not in compose_text

        assert services["backend"]["env_file"] == [
            "${AI_VIDEO_ENV_FILE:?AI_VIDEO_ENV_FILE is required}"
        ]

    def test_remote_deploy_loads_exact_reviewed_images_before_switching_services(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert 'COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.release.yml}"' in text
        assert 'RELEASE_SOURCE_SHA="${RELEASE_SOURCE_SHA:-}"' in text
        assert "RELEASE_IMAGE_TAG" in text
        assert "sudo docker load -i" in text
        assert "sha256sum -c" in text
        assert '"${COMPOSE[@]}" build' not in text
        assert "backend frontend" in text
        assert "rendering" in text
        assert "npm run build" not in text
        assert "rm -rf .next" not in text
        assert "../../src" not in text

        build_index = text.index("sudo docker load -i")
        switch_index = text.index('"${COMPOSE[@]}" up -d')
        assert build_index < switch_index

    def test_remote_deploy_validates_media_sign_secret_before_loading_images(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        secret_check = text.index("MEDIA_SIGN_SECRET")
        image_load = text.index("sudo docker load -i")
        maintenance = text.index("Entering AI Video maintenance")
        assert secret_check < image_load < maintenance
        assert "at least 32 UTF-8 bytes" in text

    def test_remote_deploy_rolls_back_first_migration_and_marks_successful_release(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert 'AI_VIDEO_SHARED_ROOT="${AI_VIDEO_SHARED_ROOT:-/opt/ai-video}"' in text
        assert 'ROLLBACK_COMPOSE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/docker-compose.prod.yml"' in text
        assert 'AI_VIDEO_ENV_FILE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.env.prod"' in text
        assert "configure_active_release" in text
        assert "PREVIOUS_RELEASE_SHA" in text
        assert 'lighthouse-backend:$PREVIOUS_RELEASE_SHA' in text
        assert "legacy-first-release" in text
        assert "rollback_release" in text
        assert "trap release_exit_handler EXIT" in text
        assert "verify_release_health" in text
        assert "ROLLBACK_FAILED" in text
        assert "run_verified_backup" in text
        assert 'PROJECT_ROOT="$RELEASE_ROOT"' in text
        assert 'DUMP_SCRIPT="$RELEASE_ROOT/scripts/pg_dump_logical.py"' in text
        assert 'CONTAINER_NAME="$BACKUP_HELPER_ID"' in text
        assert (
            'BACKUP_MANIFEST_SCRIPT="$RELEASE_ROOT/scripts/backup_manifest.py"'
            in text
        )
        assert "restore_verified.json" in text
        assert "deploy_alembic_gate.sh --apply" in text
        assert "ALLOW_MAINTENANCE_WINDOW" in text
        assert '"${ACTIVE_COMMAND[@]}" stop nginx' not in text
        assert '"${ACTIVE_COMMAND[@]}" stop rendering backend' in text
        assert "MAINTENANCE_BEGUN" in text
        assert "APP_SWITCH_STARTED" in text
        assert "restore_preswitch_services" in text
        assert '"${ACTIVE_COMMAND[@]}" start rendering backend' in text
        preswitch = text.split("restore_preswitch_services()", 1)[1].split(
            "release_exit_handler()", 1
        )[0]
        assert "force-recreate rendering backend frontend" not in preswitch
        assert 'CURRENT_LINK="$AI_VIDEO_SHARED_ROOT/current"' in text
        assert "ln -sfn" in text
        assert "os.replace(sys.argv[1], sys.argv[2])" in text
        assert 'DEPLOY_COMPLETE="1"' in text

    def test_release_images_embed_reviewed_source_sha_label(self):
        for dockerfile in (BACKEND_DOCKERFILE, REPO_ROOT / "web/Dockerfile", RENDERING_DOCKERFILE):
            text = dockerfile.read_text()
            assert "ARG RELEASE_SOURCE_SHA" in text
            assert "org.opencontainers.image.revision" in text

    def test_frontend_release_image_binds_its_loopback_health_probe(self):
        dockerfile = (REPO_ROOT / "web/Dockerfile").read_text()
        runner = dockerfile.split("FROM node:22-alpine AS runner", 1)[1]
        runtime = runner.split("\nFROM ", 1)[0]

        assert "\nENV HOSTNAME=0.0.0.0\n" in f"\n{runtime}\n"
        assert "HEALTHCHECK" in runtime
        assert "CMD wget" in runtime
        assert "http://127.0.0.1:3000" in runtime

    def test_node_release_images_remove_the_runtime_npm_toolchain(self):
        removal = (
            "rm -rf /usr/local/lib/node_modules/npm "
            "/usr/local/bin/npm /usr/local/bin/npx"
        )
        frontend_runner = (REPO_ROOT / "web/Dockerfile").read_text().split(
            "FROM node:22-alpine AS runner", 1
        )[1]
        rendering = RENDERING_DOCKERFILE.read_text()

        assert removal in frontend_runner
        assert removal in rendering
        assert rendering.index("npm ci --omit=dev --no-audit --no-fund") < rendering.index(
            removal
        )

    def test_no_inline_plaintext_secrets(self, workflow):
        text = DEPLOY_YML.read_text()
        forbidden_patterns = [
            r"-----BEGIN RSA PRIVATE KEY-----",
            r"-----BEGIN OPENSSH PRIVATE KEY-----",
            r"-----BEGIN PRIVATE KEY-----",
            r'API_KEY:\s*"sk-[a-zA-Z0-9]{40,}"',
            r'API_KEY:\s*"sk-ant-[a-zA-Z0-9]{40,}"',
        ]
        for pattern in forbidden_patterns:
            assert not re.search(pattern, text), (
                f"deploy.yml must not contain plaintext secret matching: {pattern}"
            )

    def test_workflow_dispatch_reason_is_not_interpolated_into_shell(self, workflow):
        step = _step_by_name(workflow["jobs"]["deploy"]["steps"], "Log deploy event")
        run = step.get("run") or ""

        assert "inputs.reason" not in run
        assert "${DEPLOY_REASON}" in run
        assert (step.get("env") or {}).get("DEPLOY_REASON") == "${{ inputs.reason || 'tag push' }}"

    def test_lighthouse_deploy_does_not_inline_backend_api_key_into_frontend(self):
        text = LIGHTHOUSE_DEPLOY.read_text()
        with open(LIGHTHOUSE_RELEASE_COMPOSE) as file:
            compose = yaml.safe_load(file)
        frontend_args = compose["services"]["frontend"]["build"]["args"]

        assert "NEXT_PUBLIC_API_KEY" not in text, (
            "Lighthouse deploy must not inline the backend API_KEY into browser bundles"
        )
        assert frontend_args["NEXT_PUBLIC_API_KEY"] == ""

    def test_lighthouse_deploy_release_build_is_non_interactive(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert "read -p" not in text, "deploy.sh must not block non-interactive deploy sessions"
        assert "sudo docker load -i" in text
        assert "REBUILD_BACKEND" not in text
        assert "REBUILD_RENDERING" not in text
        assert "RELEASE_SOURCE_SHA must be the reviewed" in text

    def test_backend_dockerfile_consumes_the_canonical_uv_lock(self):
        text = BACKEND_DOCKERFILE.read_text()

        assert "COPY pyproject.toml uv.lock ./" in text
        assert "uv sync --locked --no-dev --no-install-project" in text
        assert "requirements.txt" not in text
        assert "pip install" not in text

    def test_backend_release_image_contains_provider_catalog_runtime_dependency(self):
        text = BACKEND_DOCKERFILE.read_text()

        assert "COPY configs ./configs" in text
        assert "/app/configs/provider-cost-catalog.v1.json" in LIGHTHOUSE_DEPLOY.read_text()
        assert "ProviderPriceCatalog.load_default()" in LIGHTHOUSE_DEPLOY.read_text()

    def test_rendering_dockerfile_uses_reproducible_production_install(self):
        text = RENDERING_DOCKERFILE.read_text()

        assert "COPY package.json package-lock.json" in text
        assert "RUN npm ci --omit=dev --no-audit --no-fund" in text
        assert "npm install --omit=dev" not in text

    def test_rendering_health_fails_closed_when_required_runtime_is_missing(self):
        text = RENDERING_SERVER.read_text()

        assert "Boolean(remotionVersion) && ffmpegOk && chromiumOk" in text
        assert "res.status(ready ? 200 : 503)" in text
        assert 'status: ready ? "ok" : "unready"' in text

        smoke = (REPO_ROOT / "deploy/lighthouse/smoke.sh").read_text()
        assert "200|500" not in smoke
        assert "expected 200, got" in smoke

    def test_lighthouse_rendering_build_uses_an_overrideable_alpine_mirror(self):
        dockerfile = RENDERING_DOCKERFILE.read_text()
        deploy_script = LIGHTHOUSE_DEPLOY.read_text()

        assert "ARG ALPINE_MIRROR=https://dl-cdn.alpinelinux.org/alpine" in dockerfile
        assert (
            'sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR%/}|g" '
            "/etc/apk/repositories"
        ) in dockerfile
        assert (
            'RENDERING_ALPINE_MIRROR="${RENDERING_ALPINE_MIRROR:-'
            'https://mirrors.cloud.tencent.com/alpine}"'
        ) in deploy_script
        assert "export RENDERING_ALPINE_MIRROR" in deploy_script

    def test_lighthouse_deploy_manages_rendering_service_explicitly(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert "sudo docker load -i" in text
        assert '"${COMPOSE[@]}" up -d --no-deps --force-recreate rendering backend frontend' in text
        assert "docker exec ai_video_rendering" in text
        assert "http://127.0.0.1:3001/health" in text

    def test_lighthouse_cleanup_is_explicit_and_canonical_deploy_is_provider_off(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert 'CLEANUP_AFTER_DEPLOY="${CLEANUP_AFTER_DEPLOY:-0}"' in text
        assert 'CLEANUP_AFTER_DEPLOY" != "0"' in text
        assert "sudo docker system prune -f" not in text
        assert "sudo docker builder prune -f" not in text
        assert "Cleanup skipped." in text
        assert "RUN_TOKEN_SMOKE=1" not in text
        assert "/api/fast/generate" not in text
        assert "bash smoke.sh" not in text

    def test_lighthouse_deploy_keeps_ingress_stopped_until_application_health_passes(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert "[2/8] Entering AI Video maintenance while preserving shared ingress" in text
        assert '"${ACTIVE_COMMAND[@]}" stop nginx' not in text
        assert "docker exec ai_video_nginx nginx -t" in text
        app_health_index = text.index('verify_release_health || fail')
        nginx_reload_index = text.rindex("docker exec ai_video_nginx nginx -s reload")
        assert app_health_index < nginx_reload_index
        assert '"${COMPOSE[@]}" up -d --no-deps --force-recreate nginx' not in text

    def test_lighthouse_deploy_backend_health_verifies_postgres_schema_and_fails_closed(self):
        text = LIGHTHOUSE_DEPLOY.read_text()
        assert "persistence" in text
        assert "tables_verified" in text
        assert 'persistence.get("backend") != "postgresql"' in text
        assert 'persistence.get("status") != "healthy"' in text
        assert "alembic current" in text or "deploy_alembic_gate.sh --check" in text

    def test_backend_dockerfile_pins_torch_cpu_wheel(self):
        text = BACKEND_DOCKERFILE.read_text()
        pyproject = PYPROJECT.read_text()

        assert 'torch = { index = "pytorch-cpu" }' in pyproject
        assert 'name = "pytorch-cpu"' in pyproject
        assert 'url = "https://download.pytorch.org/whl/cpu"' in pyproject
        assert "explicit = true" in pyproject
        assert "TORCH_WHEEL_INDEX_URL" not in text
        assert "--extra-index-url" not in text

    def test_lighthouse_build_wrapper_forwards_deploy_control_flags(self):
        text = LIGHTHOUSE_BUILD_AND_DEPLOY.read_text()

        assert "RELEASE_SOURCE_SHA='$SOURCE_SHA'" in text
        assert "RUN_TOKEN_SMOKE=0" in text
        assert "CLEANUP_AFTER_DEPLOY=0" in text
        assert 'CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-180}"' in text
        assert "RUN_DEPLOY_SMOKE=0" in text
        assert "SSH_OPTIONS=(" in text
        assert "BatchMode=yes" in text
        assert "ConnectTimeout=\"$SSH_CONNECT_TIMEOUT\"" in text
        assert "ServerAliveInterval=\"$SSH_SERVER_ALIVE_INTERVAL\"" in text
        assert "ServerAliveCountMax=\"$SSH_SERVER_ALIVE_COUNT_MAX\"" in text
        assert "printf -v RSYNC_SSH_COMMAND" in text
        assert '-e "$RSYNC_SSH_COMMAND"' in text
        assert 'ssh "${SSH_OPTIONS[@]}"' in text

    def test_deploy_workflow_requires_main_tip_release_dir_and_pinned_known_hosts(self, workflow):
        text = DEPLOY_YML.read_text()
        provenance_steps = workflow["jobs"]["provenance"]["steps"]
        deploy_steps = workflow["jobs"]["deploy"]["steps"]
        provenance = _step_by_name(
            provenance_steps,
            "Verify workflow SHA is the exact origin main tip",
        )
        rsync_step = _step_by_name(deploy_steps, "Rsync reviewed release to server")
        ssh_step = _step_by_name(deploy_steps, "Setup pinned SSH identity")
        trigger = _step_by_name(deploy_steps, "Trigger remote deploy")

        assert "origin refs/heads/main" in (provenance.get("run") or "")
        assert "github.sha" in (provenance.get("run") or "")
        assert "releases-${{ github.sha }}" in (rsync_step.get("run") or "")
        assert "releases-${{ github.sha }}" in (trigger.get("run") or "")
        assert "DEPLOY_KNOWN_HOSTS" in text
        assert "ssh-keyscan" not in text
        assert "StrictHostKeyChecking=yes" in text
        assert "StrictHostKeyChecking=accept-new" not in text

    def test_deploy_workflow_pins_all_actions_to_full_commit_sha(self, workflow):
        for job in workflow["jobs"].values():
            for step in job.get("steps") or []:
                action = step.get("uses")
                if action:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action

    def test_deploy_ci_builds_and_inspects_all_release_images(self, workflow):
        steps = workflow["jobs"]["build-images"].get("steps") or []
        text = "\n".join(str(step) for step in steps)

        for component in ("backend", "frontend", "rendering"):
            assert f"Build {component} image" in text
        assert text.count("RELEASE_SOURCE_SHA=${{ github.sha }}") >= 3
        assert "Verify release image revision labels" in text
        assert "org.opencontainers.image.revision" in text
        for component in ("backend", "frontend", "rendering"):
            assert f"Generate {component} SBOM" in text
            assert f"Scan {component} image" in text
        assert "Package exact reviewed release images and digests" in text
        assert "Upload reviewed release bundle" in text
        assert "docker save" in text
        assert "import src.api" in text
        assert "Smoke exact frontend and rendering image runtimes" in text
        assert "release-smoke-frontend" in text
        assert "release-smoke-rendering" in text

    def test_image_scan_failures_upload_evidence_before_failing_closed(self, workflow):
        steps = workflow["jobs"]["build-images"].get("steps") or []
        step_names = [step.get("name") for step in steps]

        for component in ("backend", "frontend", "rendering"):
            scan = _step_by_name(steps, f"Scan {component} image")
            assert scan["id"] == f"scan-{component}"
            assert scan["continue-on-error"] is True
            assert scan["with"]["fail-build"] is True
            assert scan["with"]["severity-cutoff"] == "high"

        upload = _step_by_name(steps, "Upload vulnerability scan evidence")
        enforce = _step_by_name(steps, "Enforce High/Critical vulnerability scan results")
        assert upload["if"] == "always()"
        assert upload["uses"] == (
            "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f"
        )
        assert upload["with"]["if-no-files-found"] == "error"
        for component in ("backend", "frontend", "rendering"):
            assert f"scan-{component}.json" in upload["with"]["path"]
        assert enforce["if"] == "always()"
        assert enforce["env"] == {
            "BACKEND_SCAN_OUTCOME": "${{ steps.scan-backend.outcome }}",
            "FRONTEND_SCAN_OUTCOME": "${{ steps.scan-frontend.outcome }}",
            "RENDERING_SCAN_OUTCOME": "${{ steps.scan-rendering.outcome }}",
        }
        assert enforce["run"].splitlines() == [
            'test "$BACKEND_SCAN_OUTCOME" = success',
            'test "$FRONTEND_SCAN_OUTCOME" = success',
            'test "$RENDERING_SCAN_OUTCOME" = success',
        ]
        assert step_names.index("Upload vulnerability scan evidence") < step_names.index(
            "Enforce High/Critical vulnerability scan results"
        )
        assert step_names.index("Enforce High/Critical vulnerability scan results") < (
            step_names.index("Package exact reviewed release images and digests")
        )

    def test_deploy_requires_remote_dry_run_artifact_before_environment_approval(self, workflow):
        jobs = workflow["jobs"]
        assert "remote-dry-run" in jobs
        dry_text = str(jobs["remote-dry-run"])
        assert "--dry-run --itemize-changes" in dry_text
        assert "Upload rsync dry-run evidence" in dry_text
        deploy_needs = jobs["deploy"]["needs"]
        assert "remote-dry-run" in deploy_needs
        deploy_text = str(jobs["deploy"])
        assert "Download exact reviewed release bundle" in deploy_text
        assert "RELEASE_IMAGE_ARCHIVE=" in deploy_text
        assert jobs["preflight"]["needs"] == "provenance"
        assert "provenance" in jobs["build-images"]["needs"]
        assert "provenance" in jobs["remote-dry-run"]["needs"]
        assert "DEPLOY_SSH_KEY" not in dry_text
        assert "DEPLOY_HOST" not in dry_text
        assert "DRY_RUN_SSH_KEY" in dry_text
        assert jobs["remote-dry-run"]["environment"]["name"] == (
            "production-read-only-dry-run"
        )

    def test_deploy_acceptance_uses_canonical_hostname_and_valid_tls(self, workflow):
        deploy_text = str(workflow["jobs"]["deploy"])
        remote_text = LIGHTHOUSE_DEPLOY.read_text()

        assert "https://video.lute-tlz-dddd.top/api/health" in deploy_text
        assert "curl -fsSk" not in deploy_text
        assert "https://${{ secrets.DEPLOY_HOST }}/health" not in deploy_text
        assert "--resolve video.lute-tlz-dddd.top:443:127.0.0.1" in remote_text
        assert "https://video.lute-tlz-dddd.top/api/health" in remote_text
        assert "curl -fsSk" not in remote_text
        assert workflow["jobs"]["deploy"]["environment"]["url"] == (
            "https://video.lute-tlz-dddd.top"
        )


class TestCIWorkflow:

    def test_ci_yml_exists(self):
        assert CI_YML.exists(), "ci.yml must exist alongside deploy.yml"

    def test_ci_yml_loads(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        assert "jobs" in wf

    def test_ci_lints_full_python_surface(self):
        text = CI_YML.read_text()
        assert "ruff check src tests scripts" in text, (
            "main CI must lint src, tests, and scripts to keep repo-wide ruff trustworthy"
        )

    def test_workflows_do_not_reintroduce_node20_action_pins(self):
        blocked_patterns = [
            "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24",
            "actions/checkout@v4",
            "actions/setup-node@v4",
            "actions/setup-python@v5",
            "docker/setup-buildx-action@v3",
            "docker/build-push-action@v5",
            "codecov/codecov-action@v4",
            "actions/upload-artifact@v4",
            "actions/upload-pages-artifact@v3",
            "actions/deploy-pages@v4",
        ]

        for workflow in WORKFLOW_YMLS:
            text = workflow.read_text()
            for pattern in blocked_patterns:
                assert pattern not in text, (
                    f"{workflow.relative_to(REPO_ROOT)} must not pin Node 20-era "
                    f"GitHub Actions runtime via {pattern}"
                )

    def test_ci_installs_media_tools_for_video_quality_tests(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        steps = wf["jobs"]["test"].get("steps") or []
        install_step = _step_by_name(steps, "Install media test tools")
        run = install_step.get("run") or ""

        assert "apt-get update" in run
        assert "apt-get install -y --no-install-recommends ffmpeg" in run

    def test_ci_installs_openapi_typegen_dependencies_before_pytest(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        steps = wf["jobs"]["test"].get("steps") or []
        step_names = [step.get("name") for step in steps]
        node_step = _step_by_name(steps, "Set up Node.js for OpenAPI type drift guard")
        install_step = _step_by_name(steps, "Install OpenAPI typegen dependencies")
        pytest_step = _step_by_name(steps, "Run tests with coverage")

        assert node_step["uses"] == "actions/setup-node@v6"
        assert node_step["with"]["node-version"] == "22"
        assert node_step["with"]["cache"] == "npm"
        assert node_step["with"]["cache-dependency-path"] == "web/package-lock.json"
        assert install_step["run"] == "cd web && npm ci"
        assert step_names.index(node_step["name"]) < step_names.index(install_step["name"])
        assert step_names.index(install_step["name"]) < step_names.index(pytest_step["name"])

    def test_ci_pytest_env_is_hermetic(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        steps = wf["jobs"]["test"].get("steps") or []
        test_step = _step_by_name(steps, "Run tests with coverage")

        _assert_hermetic_pytest_env(test_step.get("env") or {})

    def test_ci_codecov_v7_upload_uses_explicit_files_input(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        steps = wf["jobs"]["test"].get("steps") or []
        codecov_step = _step_by_name(steps, "Upload coverage to Codecov")
        with_config = codecov_step.get("with") or {}

        assert codecov_step["uses"] == "codecov/codecov-action@v7"
        assert with_config.get("files") == "./coverage.xml"
        assert with_config.get("disable_search") is True
        assert "file" not in with_config
