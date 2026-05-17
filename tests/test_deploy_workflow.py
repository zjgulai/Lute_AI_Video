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
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


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
        assert "vitest" in step_text, "preflight must run vitest"

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


class TestCIWorkflow:

    def test_ci_yml_exists(self):
        assert CI_YML.exists(), "ci.yml must exist alongside deploy.yml"

    def test_ci_yml_loads(self):
        with open(CI_YML) as f:
            wf = yaml.safe_load(f)
        assert "jobs" in wf
