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
from typing import Any

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
LIGHTHOUSE_DEPLOY_RUNBOOK = REPO_ROOT / "docs" / "workflows" / "deploy-lighthouse-stable.md"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
RENDERING_DOCKERFILE = REPO_ROOT / "rendering" / "Dockerfile"
RENDERING_SERVER = REPO_ROOT / "rendering" / "server.mjs"
GITHUB_ACTIONS_DEPLOY_RUNBOOK = (
    REPO_ROOT / "docs" / "runbooks" / "github-actions-deploy-secrets.md"
)
LEGACY_GITHUB_DEPLOY_SETUP_RUNBOOK = (
    REPO_ROOT / "docs" / "runbooks" / "github-deploy-secrets-setup.md"
)
REMOTE_DRY_RUN_IF = (
    "${{ github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'remote-dry-run' || "
    "inputs.execution_scope == 'artifact-stage-only' || "
    "inputs.execution_scope == 'deploy' }}"
)
DEPLOY_IF = (
    "${{ github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'deploy' }}"
)
ARTIFACT_STAGE_IF = (
    "${{ github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'artifact-stage-only' || "
    "inputs.execution_scope == 'deploy' }}"
)
CLEANUP_STAGED_RELEASE_IF = (
    "${{ always() && needs.artifact-stage.result != 'skipped' && "
    "needs.artifact-stage.outputs.manifest_sha256 != '' && "
    "needs.deploy.result != 'success' && "
    "(github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'deploy') }}"
)
RELEASE_TRANSFER = REPO_ROOT / "scripts" / "release_transfer.py"
RELEASE_TRANSFER_GATE = (
    REPO_ROOT / "deploy" / "lighthouse" / "release_transfer_gate.py"
)
INSTALL_RELEASE_TRANSFER_GATE = REPO_ROOT / "scripts" / "install_release_transfer_gate.sh"
ARCHIVE_ONLY_JOB_NAMES = ("provenance", "preflight", "build-images")
SCAN_EVIDENCE_REPORTS = (
    "scan-backend.json",
    "scan-frontend.json",
    "scan-rendering.json",
    "trivy-backend.json",
    "trivy-frontend.json",
    "trivy-rendering.json",
)
REMOTE_SHELL_COMMAND = re.compile(
    r"(?:^|[;&|]|\$\()\s*(?:command\s+|sudo\s+)?(?:ssh|rsync)(?=\s|$)"
)

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


def _step_by_name(
    steps: list[dict[str, Any]],
    name: str,
) -> dict[str, Any]:
    matches = [step for step in steps if step.get("name") == name]
    assert matches, f"missing workflow step: {name}"
    return matches[0]


def _assert_hermetic_pytest_env(env: dict[str, str]) -> None:
    for key, expected in HERMETIC_PYTEST_ENV.items():
        assert env.get(key) == expected, f"{key} must be hermetic in CI pytest env"

    for key, value in env.items():
        assert "secrets." not in str(value), f"{key} must not read GitHub secrets in pytest env"


def _assert_archive_only_job_is_local(job_name: str, job: dict[str, Any]) -> None:
    assert job.get("environment") is None, (
        f"archive-only job {job_name} must not enter a GitHub Environment"
    )
    job_text = yaml.safe_dump(job, sort_keys=True)
    for forbidden in ("${{ secrets.", "DRY_RUN_", "DEPLOY_"):
        assert forbidden not in job_text, (
            f"archive-only job {job_name} must not reference {forbidden}"
        )

    for step in job.get("steps") or []:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        for raw_line in run.splitlines():
            executable = raw_line.split("#", 1)[0].strip()
            assert REMOTE_SHELL_COMMAND.search(executable) is None, (
                f"archive-only job {job_name} must not execute a remote command: "
                f"{executable}"
            )


def _assert_scan_evidence_verifier_is_fail_closed(step: dict[str, Any]) -> None:
    expected_lines = ["for report in \\"]
    expected_lines.extend(f"  {report} \\" for report in SCAN_EVIDENCE_REPORTS[:-1])
    expected_lines.extend(
        (
            f"  {SCAN_EVIDENCE_REPORTS[-1]}; do",
            '  test -s "$report"',
            '  python3 -m json.tool "$report" >/dev/null',
            "done",
        )
    )
    assert (step.get("run") or "").splitlines() == expected_lines


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

    def test_workflow_dispatch_has_exact_execution_scope_choices(self, workflow):
        on = workflow.get(True) or workflow.get("on")
        dispatch = (on.get("workflow_dispatch") or {}).get("inputs") or {}
        execution_scope = dispatch.get("execution_scope") or {}

        assert execution_scope.get("required") is True
        assert execution_scope.get("type") == "choice"
        assert execution_scope.get("default") == "archive-only"
        assert execution_scope.get("options") == [
            "archive-only",
            "remote-dry-run",
            "artifact-stage-only",
            "deploy",
        ]

    def test_artifact_stage_job_is_approval_gated_and_precedes_deploy(self, workflow):
        jobs = workflow["jobs"]
        stage = jobs["artifact-stage"]
        deploy = jobs["deploy"]
        assert stage["if"] == ARTIFACT_STAGE_IF
        assert stage["environment"] == {"name": "production-artifact-staging"}
        assert stage["permissions"] == {"actions": "read", "contents": "read"}
        assert workflow.get("permissions") == {"contents": "read"}
        assert set(stage["needs"]) == {
            "provenance",
            "preflight",
            "build-images",
            "remote-dry-run",
        }
        assert "artifact-stage" in deploy["needs"]

    def test_external_release_jobs_have_exact_read_only_token_permissions(self, workflow):
        for name in ("remote-dry-run", "deploy", "cleanup-staged-release"):
            assert workflow["jobs"][name].get("permissions") == {"contents": "read"}
        assert workflow["jobs"]["artifact-stage"].get("permissions") == {
            "actions": "read",
            "contents": "read",
        }

    def test_secret_bearing_release_jobs_do_not_persist_checkout_credentials(
        self, workflow
    ):
        for job_name in ("remote-dry-run", "artifact-stage", "deploy"):
            checkout = next(
                step
                for step in workflow["jobs"][job_name]["steps"]
                if str(step.get("uses", "")).startswith("actions/checkout@")
            )
            assert checkout.get("with", {}).get("persist-credentials") is False

    def test_failed_or_rejected_deploy_has_exact_staging_cleanup_compensation(
        self, workflow
    ):
        jobs = workflow["jobs"]
        cleanup = jobs["cleanup-staged-release"]
        assert cleanup["if"] == CLEANUP_STAGED_RELEASE_IF
        assert cleanup["needs"] == ["artifact-stage", "deploy"]
        assert cleanup["environment"] == {"name": "production-artifact-staging"}
        assert cleanup["permissions"] == {"contents": "read"}
        assert cleanup["timeout-minutes"] == 5
        assert jobs["artifact-stage"]["timeout-minutes"] == 40

        cleanup_text = yaml.safe_dump(cleanup, sort_keys=True)
        for name in (
            "TRANSFER_HOST",
            "TRANSFER_USER",
            "TRANSFER_SSH_KEY",
            "TRANSFER_KNOWN_HOSTS",
        ):
            assert f"secrets.{name}" in cleanup_text
        for forbidden in (
            "secrets.COS_",
            "secrets.DEPLOY_",
            "DRY_RUN_",
            "provider",
            "W5",
            "publish",
            "delivery",
        ):
            assert forbidden.lower() not in cleanup_text.lower()

        steps = cleanup["steps"]
        attempt = _step_by_name(steps, "Cleanup exact unpromoted incoming release")
        run = attempt["run"]
        exact_identity = (
            "cleanup ${GITHUB_SHA} ${GITHUB_RUN_ID} ${GITHUB_RUN_ATTEMPT} "
            "${{ needs.artifact-stage.outputs.manifest_sha256 }}"
        )
        assert exact_identity in run
        assert "sudo" not in run
        assert "rm -rf" not in run
        assert "cleanup_status=failed" in run
        assert "cleanup_status=passed" in run
        assert "release-transfer-cleanup-terminal.v1.json" in run
        assert "trap finish EXIT" in run

        upload = _step_by_name(steps, "Upload staged release cleanup evidence")
        assert upload["if"] == "${{ always() }}"
        assert upload["with"]["if-no-files-found"] == "error"
        assert "release-transfer-cleanup-terminal.v1.json" in upload["with"]["path"]

    def test_artifact_stage_has_exact_one_attempt_transfer_safety_contract(
        self, workflow
    ):
        stage = workflow["jobs"]["artifact-stage"]
        text = yaml.safe_dump(stage, sort_keys=False)
        for fragment in (
            "cos-versioning-verify",
            "cos-object-upload",
            "cos-object-delete",
            "cos-signed-url",
            "shared-object-upload-plan",
            "shared-object-readback-verify",
            "release-transfer-manifest.v1.json",
            "release-transfer-receipt.v1.json",
            "probe",
            "stage",
            "cleanup",
        ):
            assert fragment in text
        transfer_run = next(
            step["run"] for step in stage["steps"] if step.get("id") == "transfer"
        )
        assert "coscli" not in transfer_run.lower()
        assert "--retry" not in transfer_run
        assert 'if [ "$RESUME_TRANSFER" = true ]' in transfer_run
        assert "--resume" in transfer_run
        assert "read -r -u 3 path object_key object_sha object_size" in transfer_run
        assert 'done 3< "$upload_plan"' in transfer_run
        assert '"bucket":sys.argv[4]' in transfer_run
        assert '"endpoint_host":sys.argv[5]' in transfer_run
        assert "DEPLOY_" not in text
        assert "provider" not in text.lower()
        assert "publish" not in text.lower()
        assert "delivery" not in text.lower()

    def test_transfer_manifest_normalizes_upload_artifact_digest_output(self, workflow):
        build = workflow["jobs"]["build-images"]
        assert build["outputs"]["release_artifact_digest"] == (
            "${{ steps.release-bundle.outputs.artifact-digest }}"
        )
        packet = _step_by_name(
            workflow["jobs"]["artifact-stage"]["steps"],
            "Build exact source bundle and transfer manifest",
        )
        run = packet["run"]
        assert '--github-artifact-digest "sha256:${{ steps.artifact.outputs.sha256 }}"' in run
        artifact = _step_by_name(
            workflow["jobs"]["artifact-stage"]["steps"],
            "Download and verify exact reviewed release artifact",
        )
        artifact_run = artifact["run"]
        assert "actions/artifacts/${{ needs.build-images.outputs.release_artifact_id }}/zip" in artifact_run
        assert 'expected_digest="${expected_digest#sha256:}"' in artifact_run
        assert artifact_run.index("sha256sum -c -") < artifact_run.index("unzip -q")
        assert "--location" in artifact_run
        assert "--location-trusted" not in artifact_run
        assert "--proto-redir '=https'" in artifact_run
        assert "--max-redirs 3" in artifact_run

    def test_explicit_resume_reuses_only_shared_objects_and_always_creates_manifest(self, workflow):
        steps = workflow["jobs"]["artifact-stage"]["steps"]
        step = _step_by_name(steps, "Upload, probe and stage exact release")
        run = step["run"]
        resume_gate = run.index('if [ "$RESUME_TRANSFER" = true ]; then')
        resume_end = run.index("\nfi\n", resume_gate)
        plan = run.index("python3 scripts/release_transfer.py shared-object-upload-plan")
        upload = run.index('done 3< "$upload_plan"')
        readback = run.index("shared-object-readback-verify")
        manifest_upload = run.index('--object-key "$manifest_object_key"')
        assert resume_gate < resume_end < plan < upload < readback < manifest_upload
        assert "cos-object-upload" in run
        assert "transactions/${workflow_run_id}/${workflow_run_attempt}" not in run
        assert "manifest_object_key" in run
        assert "inputs.resume_transfer" not in run
        assert step["env"]["RESUME_TRANSFER"] == "${{ inputs.resume_transfer || false }}"

    def test_two_leg_probe_and_versioning_gate_precede_all_release_object_mutation(
        self, workflow
    ):
        run = _step_by_name(
            workflow["jobs"]["artifact-stage"]["steps"],
            "Upload, probe and stage exact release",
        )["run"]
        versioning = run.index("cos-versioning-verify")
        probe_upload = run.index('--object-key "$probe_object_key"', versioning)
        runner_gate = run.index("probe-evaluate", probe_upload)
        server_gate = run.index(
            '> "${transfer_root}/server-probe-receipt.json"', runner_gate
        )
        upload_plan = run.index("shared-object-upload-plan", server_gate)
        release_upload = run.index('done 3< "$upload_plan"', upload_plan)
        manifest_upload = run.index('--object-key "$manifest_object_key"', release_upload)
        assert versioning < probe_upload < runner_gate < server_gate
        assert server_gate < upload_plan < release_upload < manifest_upload
        assert "runner_probe_failed" in run
        assert "server_probe_failed" in run
        assert "TRANSFER_DEADLINE_MONOTONIC_NS" in run
        assert "1800 * 1_000_000_000" in run
        assert '"deadline_seconds_remaining":int(sys.argv[3])' in run
        assert "deadline_remaining()" in run
        assert run.count("timeout --foreground --signal=TERM --kill-after=5s") >= 3
        assert "env -u TRANSFER_DEADLINE_MONOTONIC_NS" in run
        assert "cos_release_upload_failed" in run

    def test_transfer_terminal_uses_phase_specific_stable_codes(self, workflow):
        run = _step_by_name(
            workflow["jobs"]["artifact-stage"]["steps"],
            "Upload, probe and stage exact release",
        )["run"]
        for code in (
            "transfer_initialization_failed",
            "cos_versioning_gate_failed",
            "runner_probe_failed",
            "server_probe_failed",
            "cos_release_upload_failed",
            "cos_identity_readback_failed",
            "cos_manifest_upload_failed",
            "incoming_stage_failed",
            "incoming_cleanup_failed",
            "cos_probe_cleanup_failed",
            "transfer_passed",
        ):
            assert f"transfer_status={code}" in run

    def test_transfer_failure_attempts_exact_incoming_cleanup_before_evidence(self, workflow):
        steps = workflow["jobs"]["artifact-stage"]["steps"]
        run = _step_by_name(steps, "Upload, probe and stage exact release")["run"]
        assert "remote_state_may_exist=0" in run
        assert "remote_state_may_exist=1" in run
        assert "probe_uploaded" not in run
        probe_intent_index = run.index("probe_mutation_may_exist=1")
        probe_upload_index = run.index(
            "python3 scripts/release_transfer.py cos-object-upload",
            probe_intent_index,
        )
        probe_cleanup_index = run.index('if [ "$probe_mutation_may_exist" = 1 ]')
        cleanup_index = run.index(
            'if [ "$status" -ne 0 ] && [ "$remote_state_may_exist" = 1 ]'
        )
        secret_removal_index = run.index('rm -f "$ssh_key" "$known_hosts"')
        assert probe_intent_index < probe_upload_index
        assert probe_cleanup_index < cleanup_index < secret_removal_index
        assert "transfer_status=incoming_cleanup_failed" in run
        assert "transfer_status=cleanup_failed" not in run
        assert "trap cleanup EXIT" in run
        assert "trap 'exit 129' HUP" in run
        assert "trap 'exit 130' INT" in run
        assert "trap 'exit 143' TERM" in run

    def test_late_stage_failure_compensation_is_not_success_only(self, workflow):
        stage = workflow["jobs"]["artifact-stage"]
        cleanup = workflow["jobs"]["cleanup-staged-release"]
        transfer = _step_by_name(stage["steps"], "Upload, probe and stage exact release")[
            "run"
        ]

        assert "needs.artifact-stage.result == 'success'" not in cleanup["if"]
        assert "needs.artifact-stage.result != 'skipped'" in cleanup["if"]
        assert "needs.artifact-stage.outputs.manifest_sha256 != ''" in cleanup["if"]
        assert transfer.index("remote_state_may_exist=1") < transfer.index(
            '> "${transfer_root}/server-probe-receipt.json"'
        )
        assert transfer.index('if [ "$probe_mutation_may_exist" = 1 ]') < transfer.index(
            'if [ "$status" -ne 0 ] && [ "$remote_state_may_exist" = 1 ]'
        )
        assert _step_by_name(stage["steps"], "Upload bounded transfer evidence")["if"] == (
            "${{ always() }}"
        )

    def test_artifact_stage_separates_cos_staging_and_production_credentials(self, workflow):
        stage_text = yaml.safe_dump(workflow["jobs"]["artifact-stage"], sort_keys=True)
        deploy_text = yaml.safe_dump(workflow["jobs"]["deploy"], sort_keys=True)
        for name in (
            "COS_SECRET_ID",
            "COS_SECRET_KEY",
            "COS_SESSION_TOKEN",
            "TRANSFER_HOST",
            "TRANSFER_USER",
            "TRANSFER_SSH_KEY",
            "TRANSFER_KNOWN_HOSTS",
        ):
            assert f"secrets.{name}" in stage_text
            assert f"secrets.{name}" not in deploy_text
        for name in ("COS_BUCKET", "COS_ENDPOINT", "TRANSFER_TARGET_DIR"):
            assert f"vars.{name}" in stage_text
        assert "secrets.DEPLOY_" not in stage_text

    def test_signed_urls_flow_only_over_ssh_stdin_and_never_into_artifacts(self, workflow):
        stage = workflow["jobs"]["artifact-stage"]
        transfer = _step_by_name(stage["steps"], "Upload, probe and stage exact release")
        transfer_run = transfer["run"]
        assert "signed-url-payload" in transfer_run
        assert "--validity-seconds 7200" not in transfer_run
        assert "| timeout --foreground --signal=TERM --kill-after=5s" in transfer_run
        assert "ssh -i \"$ssh_key\"" in transfer_run
        assert "https://" not in transfer_run
        for step in stage["steps"]:
            if step.get("uses", "").startswith("actions/upload-artifact@"):
                artifact_text = yaml.safe_dump(step, sort_keys=True).lower()
                assert "url" not in artifact_text
                assert "cos.yaml" not in artifact_text

    def test_deploy_promotes_verified_incoming_before_existing_deploy_script(self, workflow):
        deploy = workflow["jobs"]["deploy"]
        steps = deploy["steps"]
        names = [step.get("name") for step in steps]
        required = _step_by_name(steps, "Verify required secrets")
        promote = _step_by_name(steps, "Promote verified incoming release")
        trigger = _step_by_name(steps, "Trigger remote deploy")
        assert names.index(required["name"]) < names.index(promote["name"])
        assert names.index(promote["name"]) < names.index(trigger["name"])
        assert required["env"]["DEPLOY_TARGET_DIR"] == (
            "${{ secrets.DEPLOY_TARGET_DIR }}"
        )
        assert '[ "$DEPLOY_TARGET_DIR" = /opt/ai-video ]' in required["run"]
        assert "deploy_target_root_invalid" in required["run"]
        assert "secrets.DEPLOY_TARGET_DIR" not in required["run"]
        assert "promote" in promote["run"]
        assert "release-transfer-gate" in promote["run"]
        assert "Rsync reviewed release to server" not in names
        assert "Upload exact reviewed image archive" not in names
        assert "Prepare reviewed release directory" not in names

    def test_transfer_contract_and_gate_are_repository_owned_and_executable(self):
        for executable in (
            RELEASE_TRANSFER,
            RELEASE_TRANSFER_GATE,
            INSTALL_RELEASE_TRANSFER_GATE,
        ):
            assert executable.is_file()
            assert executable.stat().st_mode & 0o111

        result = subprocess.run(
            [str(INSTALL_RELEASE_TRANSFER_GATE), "print-authorized-command"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={
                "HOME": str(REPO_ROOT),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
        )
        assert result.stderr == ""
        assert result.stdout.splitlines() == [
            'command="/usr/local/sbin/ai-video-release-transfer-gate '
            '--staging-forward",restrict',
            '{"status":"passed","action":"print-authorized-command"}',
        ]

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
        assert node_step["with"]["cache-dependency-path"].splitlines() == [
            "web/package-lock.json",
            "rendering/package-lock.json",
        ]
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
        dry_run = workflow["jobs"]["remote-dry-run"]
        steps = dry_run.get("steps") or []
        rsync_step = _step_by_name(steps, "Capture rsync dry-run deletion artifact")

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
        assert backend_mounts == [
            "backend_output:/app/output",
            "renderer_socket:/run/rendering",
        ]
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
        assert "snapshot_backup_schedule" in text
        assert "install_and_verify_backup_schedule" in text
        assert "verify_no_backup_in_progress" in text
        assert "activate_backup_schedule" in text
        assert "disable_backup_schedule_for_rollback" in text
        assert "restore_backup_schedule" in text
        assert "commit_backup_schedule" in text
        assert "restore_release_pointer" in text
        assert "CURRENT_POINTER_UPDATED" in text
        assert 'sudo ln -sfn "$PREVIOUS_RELEASE_ROOT" "$rollback_link"' in text
        assert 'sudo python3 - "$rollback_link" "$CURRENT_LINK"' in text
        assert 'sudo python3 - "$CURRENT_LINK" "$RELEASE_ROOT"' in text
        assert 'sudo ln -sfn "$RELEASE_ROOT" "$NEXT_LINK"' in text
        assert 'sudo python3 - "$NEXT_LINK" "$CURRENT_LINK"' in text
        assert "install_backup_cron.sh" in text
        assert "MIGRATE_LEGACY=1" in text
        assert "MODE=install" in text
        assert "MODE=verify" in text
        assert "CRON_ENABLED=0" in text
        assert "CRON_ENABLED=1" in text
        assert 'CURRENT_RELEASE_ROOT="$CURRENT_LINK"' in text
        assert 'SOURCE_MANIFEST_PATH="$CURRENT_LINK/source-manifest.v1.json"' in text
        handler = text[
            text.index("release_exit_handler() {") : text.index(
                "trap release_exit_handler EXIT"
            )
        ]
        assert handler.index("disable_backup_schedule_for_rollback") < handler.index(
            "restore_release_pointer"
        ) < handler.index("rollback_release") < handler.index(
            "restore_backup_schedule"
        )
        disabled_call = text.rindex("\ninstall_and_verify_backup_schedule\n")
        backup_lock_probe = text.rindex("\nverify_no_backup_in_progress\n")
        maintenance_start = text.index('MAINTENANCE_BEGUN="1"')
        stop_call = text.index('"${ACTIVE_COMMAND[@]}" stop rendering backend')
        assert disabled_call < backup_lock_probe < maintenance_start < stop_call
        assert 'BACKUP_LOCK_FILE="$BACKUP_ROOT/.backup.lock"' in text
        assert '"$BACKUP_FLOCK_BIN" -n "$BACKUP_LOCK_FILE" true' in text
        activate_call = text.rindex("\nactivate_backup_schedule\n")
        assert text.index(
            'verify_release_health "$APP_VERSION" "$RELEASE_SOURCE_SHA" 1 strict'
        ) < activate_call
        assert 'BACKUP_RUNTIME_DIR="${BACKUP_RUNTIME_DIR:-/usr/local/libexec/ai-video-backup}"' in text
        assert 'DUMP_SCRIPT="$BACKUP_RUNTIME_DIR/pg_dump_logical.py"' in text
        assert 'BACKUP_MANIFEST_SCRIPT="$BACKUP_RUNTIME_DIR/backup_manifest.py"' in text
        assert '"$latest/pg_dump_stats.json"' in text
        assert "scheduled backup table coverage differs from isolated restore" in text
        assert 'PROJECT_ROOT="$RELEASE_ROOT"' in text
        assert 'DUMP_SCRIPT="$BACKUP_RUNTIME_DIR/pg_dump_logical.py"' in text
        assert 'CONTAINER_NAME="$BACKUP_HELPER_ID"' in text
        assert (
            'BACKUP_MANIFEST_SCRIPT="$BACKUP_RUNTIME_DIR/backup_manifest.py"'
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
        runner = dockerfile.split("FROM ${NODE_IMAGE} AS runner", 1)[1]
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
            "FROM ${NODE_IMAGE} AS runner", 1
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

        assert "COPY rendering/package.json rendering/package-lock.json" in text
        assert "RUN npm ci --omit=dev --no-audit --no-fund" in text
        assert "npm install --omit=dev" not in text

    def test_rendering_health_fails_closed_when_required_runtime_is_missing(self):
        text = RENDERING_SERVER.read_text()

        assert "&& ffmpegOk" in text
        assert "&& ffprobeOk" in text
        assert "&& chromiumOk" in text
        assert "response.status(ready ? 200 : 503)" in text
        assert 'status: ready ? "ok" : "unready"' in text

        smoke = (REPO_ROOT / "deploy/lighthouse/smoke.sh").read_text()
        assert "200|500" not in smoke
        assert "provider_call=false" in smoke
        assert "/api/fast/generate" not in smoke

    def test_lighthouse_rendering_build_pins_fixed_google_chrome(self):
        dockerfile = RENDERING_DOCKERFILE.read_text()
        deploy_script = LIGHTHOUSE_DEPLOY.read_text()

        assert "GOOGLE_CHROME_VERSION=150.0.7871.186-1" in dockerfile
        assert (
            "ADD --checksum=sha256:"
            "4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00"
            in dockerfile
        )
        assert "google-chrome-stable_150.0.7871.186-1_amd64.deb" in dockerfile
        assert "RENDERING_ALPINE_MIRROR" not in deploy_script

    def test_lighthouse_deploy_manages_rendering_service_explicitly(self):
        text = LIGHTHOUSE_DEPLOY.read_text()

        assert "sudo docker load -i" in text
        assert '"${COMPOSE[@]}" up -d --no-deps --force-recreate rendering backend frontend' in text
        assert "docker exec ai_video_rendering" in text
        assert "node /app/healthcheck.mjs" in text
        candidate_health = text.split(
            'verify_release_health "$APP_VERSION" "$RELEASE_SOURCE_SHA" 1 strict',
            1,
        )
        assert len(candidate_health) == 2
        assert "active-compatible" in text
        legacy_probe = text.split("verify_legacy_renderer_health()", 1)[1].split(
            "verify_renderer_health()", 1
        )[0]
        assert "http://127.0.0.1:3001/health" in legacy_probe
        assert 'payload.status === "ok"' in legacy_probe
        assert 'typeof payload.remotion === "string"' in legacy_probe
        assert "payload.ffmpeg === true" in legacy_probe
        assert "payload.chromium === true" in legacy_probe

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

        assert "[3/9] Entering AI Video maintenance while preserving shared ingress" in text
        assert '"${ACTIVE_COMMAND[@]}" stop nginx' not in text
        assert "docker exec ai_video_nginx nginx -t" in text
        app_health_index = text.index(
            'verify_release_health "$APP_VERSION" "$RELEASE_SOURCE_SHA" 1'
        )
        nginx_reload_index = text.rindex("docker exec ai_video_nginx nginx -s reload")
        assert app_health_index < nginx_reload_index
        assert '"${COMPOSE[@]}" up -d --no-deps --force-recreate nginx' not in text

    def test_lighthouse_deploy_stage_banners_match_ten_stage_runbook(self):
        text = LIGHTHOUSE_DEPLOY.read_text()
        banners = re.findall(r'^echo "\[([0-9]+)/([0-9]+)\]', text, re.MULTILINE)

        assert banners == [(str(index), "9") for index in range(10)]
        runbook = LIGHTHOUSE_DEPLOY_RUNBOOK.read_text()
        assert "## 远端十阶段" in runbook
        stage_heading = runbook.index("## 远端十阶段")
        acceptance_heading = runbook.index("## 验收边界")
        stage_section = runbook[stage_heading:acceptance_heading]
        assert re.findall(r"^([0-9]+)\. ", stage_section, re.MULTILINE) == [
            str(index) for index in range(1, 11)
        ]

    def test_lighthouse_deploy_backend_health_verifies_postgres_schema_and_fails_closed(self):
        text = LIGHTHOUSE_DEPLOY.read_text()
        assert "persistence" in text
        assert "tables_verified" in text
        assert 'persistence.get("backend") != "postgresql"' in text
        assert 'persistence.get("status") != "healthy"' in text
        assert 'payload.get("version") != sys.argv[1]' in text
        assert 'payload.get("source_revision") != sys.argv[2]' in text
        assert 'org.opencontainers.image.version' in text
        assert 'image semantic version mismatch' in text
        assert 'ACTIVE_IDENTITY_REQUIRED="1"' in text
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
        promote_step = _step_by_name(deploy_steps, "Promote verified incoming release")
        ssh_step = _step_by_name(deploy_steps, "Setup pinned SSH identity")
        trigger = _step_by_name(deploy_steps, "Trigger remote deploy")

        assert "origin refs/heads/main" in (provenance.get("run") or "")
        assert "github.sha" in (provenance.get("run") or "")
        assert "github.sha" in (promote_step.get("run") or "")
        assert "release-transfer-gate" in (promote_step.get("run") or "")
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
        assert "org.opencontainers.image.version" in text
        assert text.count("APP_VERSION=${{ steps.project-version.outputs.value }}") >= 3
        for component in ("backend", "frontend", "rendering"):
            assert f"Generate {component} SBOM" in text
            assert f"Scan {component} image" in text
            assert f"Scan {component} image with Trivy" in text
        assert "Package exact reviewed release images and digests" in text
        assert "Upload reviewed release bundle" in text
        assert "docker save" in text
        assert "import src.api" in text
        assert "Smoke exact frontend and rendering image runtimes" in text
        assert "release-smoke-frontend" in text
        assert "release-smoke-rendering" in text

    def test_deploy_smoke_binds_public_health_to_both_release_identities(self, workflow):
        steps = workflow["jobs"]["deploy"].get("steps") or []
        smoke = _step_by_name(steps, "Smoke test /health")
        run = smoke.get("run") or ""

        assert "scripts/project_version.py --check" in run
        assert 'payload.get("version")==sys.argv[1]' in run
        assert 'payload.get("source_revision")==sys.argv[2]' in run
        assert '"$expected_version" "$GITHUB_SHA"' in run

    def test_renderer_release_smoke_uses_production_security_boundary(self, workflow):
        steps = workflow["jobs"]["build-images"].get("steps") or []
        smoke = _step_by_name(steps, "Smoke exact frontend and rendering image runtimes")
        run = smoke.get("run") or ""

        for required in (
            "--network none",
            "--read-only",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            "--cpus 2",
            "--memory 4g",
            "--pids-limit 256",
            "--tmpfs /tmp:rw,noexec,nosuid,nodev,size=512m",
            "release-smoke-renderer-output:/app/output",
            "release-smoke-renderer-socket:/run/rendering",
        ):
            assert required in run

    def test_image_scan_failures_upload_evidence_before_failing_closed(self, workflow):
        steps = workflow["jobs"]["build-images"].get("steps") or []
        step_names = [step.get("name") for step in steps]

        trivy_policies = {
            "backend": ".trivyignore-backend.yaml",
            "frontend": ".trivyignore.yaml",
            "rendering": ".trivyignore-rendering.yaml",
        }

        for component in ("backend", "frontend", "rendering"):
            scan = _step_by_name(steps, f"Scan {component} image")
            assert scan["id"] == f"scan-{component}"
            assert scan["continue-on-error"] is True
            assert scan["with"]["fail-build"] is True
            assert scan["with"]["severity-cutoff"] == "high"

            trivy = _step_by_name(steps, f"Scan {component} image with Trivy")
            assert trivy["id"] == f"trivy-{component}"
            assert trivy["continue-on-error"] is True
            assert trivy["uses"] == (
                "aquasecurity/trivy-action@b6643a29fecd7f34b3597bc6acb0a98b03d33ff8"
            )
            assert trivy["env"] == {
                "TRIVY_IGNOREFILE": trivy_policies[component],
            }
            assert trivy["with"] == {
                "version": "v0.69.3",
                "image-ref": f"lighthouse-{component}:${{{{ github.sha }}}}",
                "scanners": "vuln",
                "severity": "HIGH,CRITICAL",
                "ignore-unfixed": False,
                "format": "json",
                "output": f"trivy-{component}.json",
                "exit-code": 1,
            }

        verify = _step_by_name(steps, "Verify vulnerability scan evidence is complete")
        upload = _step_by_name(steps, "Upload vulnerability scan evidence")
        enforce = _step_by_name(steps, "Enforce High/Critical vulnerability scan results")
        release_upload = _step_by_name(steps, "Upload reviewed release bundle")
        assert verify["if"] == "always()"
        assert verify["id"] == "scan-evidence"
        assert verify["continue-on-error"] is True
        _assert_scan_evidence_verifier_is_fail_closed(verify)
        assert upload["if"] == "always()"
        assert upload["uses"] == (
            "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f"
        )
        assert upload["with"]["if-no-files-found"] == "error"
        for component in ("backend", "frontend", "rendering"):
            assert f"scan-{component}.json" in upload["with"]["path"]
            assert f"trivy-{component}.json" in upload["with"]["path"]
            assert f"scan-{component}.json" in verify["run"]
            assert f"trivy-{component}.json" in verify["run"]
        assert "scan-*.json" in release_upload["with"]["path"]
        assert "trivy-*.json" in release_upload["with"]["path"]
        assert enforce["if"] == "always()"
        assert enforce["env"] == {
            "BACKEND_GRYPE_OUTCOME": "${{ steps.scan-backend.outcome }}",
            "FRONTEND_GRYPE_OUTCOME": "${{ steps.scan-frontend.outcome }}",
            "RENDERING_GRYPE_OUTCOME": "${{ steps.scan-rendering.outcome }}",
            "BACKEND_TRIVY_OUTCOME": "${{ steps.trivy-backend.outcome }}",
            "FRONTEND_TRIVY_OUTCOME": "${{ steps.trivy-frontend.outcome }}",
            "RENDERING_TRIVY_OUTCOME": "${{ steps.trivy-rendering.outcome }}",
            "SCAN_EVIDENCE_OUTCOME": "${{ steps.scan-evidence.outcome }}",
        }
        assert enforce["run"].splitlines() == [
            'test "$BACKEND_GRYPE_OUTCOME" = success',
            'test "$FRONTEND_GRYPE_OUTCOME" = success',
            'test "$RENDERING_GRYPE_OUTCOME" = success',
            'test "$BACKEND_TRIVY_OUTCOME" = success',
            'test "$FRONTEND_TRIVY_OUTCOME" = success',
            'test "$RENDERING_TRIVY_OUTCOME" = success',
            'test "$SCAN_EVIDENCE_OUTCOME" = success',
        ]
        assert step_names.index("Verify vulnerability scan evidence is complete") < (
            step_names.index("Upload vulnerability scan evidence")
        )
        assert step_names.index("Upload vulnerability scan evidence") < step_names.index(
            "Enforce High/Critical vulnerability scan results"
        )
        assert step_names.index("Enforce High/Critical vulnerability scan results") < (
            step_names.index("Package exact reviewed release images and digests")
        )

    def test_scan_evidence_verifier_rejects_noop_mutations(self, workflow):
        steps = workflow["jobs"]["build-images"].get("steps") or []
        verify = _step_by_name(steps, "Verify vulnerability scan evidence is complete")

        _assert_scan_evidence_verifier_is_fail_closed(verify)
        for required_command in (
            'test -s "$report"',
            'python3 -m json.tool "$report" >/dev/null',
        ):
            mutated = {
                **verify,
                "run": verify["run"].replace(required_command, 'echo "$report"'),
            }
            with pytest.raises(AssertionError):
                _assert_scan_evidence_verifier_is_fail_closed(mutated)

    def test_deploy_requires_remote_dry_run_artifact_before_environment_approval(self, workflow):
        jobs = workflow["jobs"]
        assert "remote-dry-run" in jobs
        dry_text = str(jobs["remote-dry-run"])
        assert "--dry-run --itemize-changes" in dry_text
        assert "Upload rsync dry-run evidence" in dry_text
        deploy_needs = jobs["deploy"]["needs"]
        assert "remote-dry-run" in deploy_needs
        assert "artifact-stage" in deploy_needs
        deploy_text = str(jobs["deploy"])
        stage_text = str(jobs["artifact-stage"])
        assert "Download and verify exact reviewed release artifact" in stage_text
        assert "release-transfer-receipt.v1.json" in stage_text
        assert "Promote verified incoming release" in deploy_text
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

    def test_execution_scope_gates_only_external_jobs(self, workflow):
        jobs = workflow["jobs"]

        for job_name in ARCHIVE_ONLY_JOB_NAMES:
            assert jobs[job_name].get("if") is None
            _assert_archive_only_job_is_local(job_name, jobs[job_name])

        assert jobs["remote-dry-run"].get("if") == REMOTE_DRY_RUN_IF
        assert jobs["artifact-stage"].get("if") == ARTIFACT_STAGE_IF
        assert jobs["deploy"].get("if") == DEPLOY_IF
        assert jobs["cleanup-staged-release"].get("if") == CLEANUP_STAGED_RELEASE_IF
        assert jobs["remote-dry-run"]["needs"] == [
            "provenance",
            "preflight",
            "build-images",
        ]
        assert jobs["deploy"]["needs"] == [
            "preflight",
            "build-images",
            "remote-dry-run",
            "artifact-stage",
        ]
        assert jobs["cleanup-staged-release"]["needs"] == [
            "artifact-stage",
            "deploy",
        ]

    def test_build_images_has_exact_read_only_token_permissions(self, workflow):
        assert workflow["jobs"]["build-images"].get("permissions") == {
            "contents": "read"
        }

    def test_deploy_runbook_documents_execution_scope_boundaries(self):
        text = GITHUB_ACTIONS_DEPLOY_RUNBOOK.read_text()

        for scope in (
            "archive-only",
            "remote-dry-run",
            "artifact-stage-only",
            "deploy",
        ):
            assert f"`{scope}`" in text
        assert "默认选择 `archive-only`" in text
        assert "PR head" in text
        assert "exact `origin/main`" in text
        assert "不会进入任何 GitHub Environment" in text
        assert "不构成生产部署证据" in text

    def test_legacy_deploy_setup_runbook_is_an_explicit_safe_redirect(self):
        text = LEGACY_GITHUB_DEPLOY_SETUP_RUNBOOK.read_text()
        frontmatter, body = text.split("---", 2)[1:]

        assert "status: deprecated" in frontmatter
        assert "github-actions-deploy-secrets.md" in body
        assert "archive-only" in body
        assert "remote-dry-run" in body
        assert "DEPLOY_KNOWN_HOSTS" in body
        assert "v*.*.*" in body
        for stale_claim in (
            "所需 4 个 secrets",
            "4 个 secrets 未配置",
            "添加 4 个 secrets",
            "tags `v*`",
            "approve 后：rsync + remote deploy",
        ):
            assert stale_claim not in text

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
        assert node_step["with"]["cache-dependency-path"].splitlines() == [
            "web/package-lock.json",
            "rendering/package-lock.json",
        ]
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
