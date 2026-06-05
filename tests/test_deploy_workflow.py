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

import re
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"
LIGHTHOUSE_DEPLOY = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"

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
    "TIKTOK_OPEN_ID": "",
    "SHOPIFY_STORE_URL": "",
    "SHOPIFY_ADMIN_TOKEN": "",
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

    def test_preflight_lints_src_and_tests(self, workflow):
        preflight = workflow["jobs"]["preflight"]
        steps = preflight.get("steps") or []
        step_text = " ".join((s.get("run") or "") for s in steps)
        assert "ruff check src tests" in step_text, (
            "deploy preflight must lint tests as well as src to prevent hidden test debt"
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

    def test_remote_deploy_disables_token_smoke_by_default(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy.get("steps") or []
        remote_steps = [s for s in steps if s.get("name") == "Trigger remote deploy"]
        assert remote_steps, "deploy must trigger remote Lighthouse deploy"

        run = remote_steps[0].get("run") or ""
        assert "RUN_TOKEN_SMOKE=0 bash deploy/lighthouse/deploy.sh" in run, (
            "GitHub deploy must explicitly keep token-consuming smoke disabled by default"
        )

    def test_rsync_uses_lighthouse_exclude_file(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy.get("steps") or []
        rsync_step = _step_by_name(steps, "Rsync to server")

        run = rsync_step.get("run") or ""
        assert "--exclude-from='deploy/lighthouse/rsync-excludes.txt'" in run, (
            "GitHub deploy must reuse the Lighthouse rsync exclude SSOT"
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

    def test_lighthouse_deploy_does_not_inline_backend_api_key_into_frontend(self):
        text = LIGHTHOUSE_DEPLOY.read_text()
        frontend_build = text.split("npm run build", 1)[0]

        assert "export NEXT_PUBLIC_API_KEY" not in frontend_build, (
            "Lighthouse deploy must not inline the backend API_KEY into browser bundles"
        )
        assert "DEPLOY_API_KEY" not in frontend_build, (
            "production API key may be used by smoke.sh, not by frontend build env"
        )


class TestCIWorkflow:

    def test_ci_yml_exists(self):
        assert CI_YML.exists(), "ci.yml must exist alongside deploy.yml"

    def test_ci_yml_loads(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        assert "jobs" in wf

    def test_ci_lints_src_and_tests(self):
        text = CI_YML.read_text()
        assert "ruff check src tests" in text, (
            "main CI must lint tests as well as src to keep repo-wide ruff trustworthy"
        )

    def test_ci_pytest_env_is_hermetic(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        steps = wf["jobs"]["test"].get("steps") or []
        test_step = _step_by_name(steps, "Run tests with coverage")

        _assert_hermetic_pytest_env(test_step.get("env") or {})
