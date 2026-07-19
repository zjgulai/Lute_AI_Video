"""Static guard for Lighthouse rsync artifact exclusions."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"
BUILD_AND_DEPLOY = REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CONTRACT_FILE = REPO_ROOT / "configs" / "lighthouse-rsync-artifact-exclude-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "lighthouse-rsync-artifact-exclude.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

REQUIRED_EXCLUDES_BY_CATEGORY = {
    "source_control_and_env": {
        ".git",
        ".env",
        "*.pem",
        "deploy/lighthouse/.env.prod",
        "deploy/lighthouse/.portal-auth.env",
        "deploy/lighthouse/server.crt",
        "deploy/lighthouse/server.key",
        "deploy/lighthouse/*.pem",
    },
    "dependencies_and_caches": {
        "node_modules",
        "web/node_modules",
        "rendering/node_modules",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".playwright-mcp",
    },
    "frontend_build_artifacts": {
        "web/.next",
        "web/.next.old",
        "web/dist",
        "web/tsconfig.tsbuildinfo",
    },
    "test_reports_and_traces": {
        "web/playwright-report",
        "web/test-results",
        "web/blob-report",
        "coverage",
        "htmlcov",
        ".coverage",
    },
    "runtime_outputs_and_screenshots": {
        "output",
        "output_uploaded",
        "tmp",
        "tmp/outputs",
        "tmp/screenshots",
        "web/tmp",
        "web/tmp/screenshots",
    },
    "local_workspace_state": {
        "*.sqlite3",
        ".codegraph",
        ".hermes",
        "worktrees",
        "drafts",
        "archive",
        "ref",
    },
    "remote_only_landing_sidecars": {
        "deploy/lighthouse/landing/login.html",
        "deploy/lighthouse/landing/register.html",
        "deploy/lighthouse/landing/systems.html",
        "deploy/lighthouse/landing/lute-*.html",
        "deploy/lighthouse/landing/lute-auth.*",
        "deploy/lighthouse/landing/voc-zh_messages.json",
        "deploy/lighthouse/landing/.portal.htpasswd",
        "deploy/lighthouse/landing/brand-placeholder.html",
    },
    "remote_only_production_sidecars": {
        "backups",
        "deploy/lighthouse/backups",
        "deploy/lighthouse/portal-auth",
        "deploy/lighthouse/docker-compose.prod.yml",
        "deploy/lighthouse/nginx.conf",
        "deploy/lighthouse/skills.conf",
        "deploy/lighthouse/auth_gate.conf",
        "deploy/lighthouse/momcozy-platform.conf",
        "deploy/lighthouse/plugin-hub.htpasswd",
        "deploy/lighthouse/*.conf.*backup*",
        "deploy/lighthouse/*.candidate",
    },
}


def _exclude_entries() -> set[str]:
    return {
        line.strip()
        for line in RSYNC_EXCLUDES.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_lighthouse_rsync_excludes_generated_artifacts_by_category():
    excludes = _exclude_entries()
    for category, required in REQUIRED_EXCLUDES_BY_CATEGORY.items():
        missing = sorted(required - excludes)
        assert not missing, f"{category} missing rsync excludes: {missing}"


def test_lighthouse_sync_entrypoints_use_the_shared_exclude_file():
    wrapper = BUILD_AND_DEPLOY.read_text()
    workflow = DEPLOY_WORKFLOW.read_text()

    assert 'EXCLUDE_FILE="${EXCLUDE_FILE:-$SCRIPT_DIR/rsync-excludes.txt}"' in wrapper
    assert '--exclude-from="$EXCLUDE_FILE"' in wrapper
    assert "RSYNC_BIN" in wrapper
    assert "GNU rsync 3.x is required for --chmod=F644,D755" in wrapper
    assert '"$RSYNC_BIN" "${RSYNC_ARGS[@]}"' in wrapper
    assert "--exclude-from='deploy/lighthouse/rsync-excludes.txt'" in workflow

    for forbidden_inline in ("--exclude='.next'", "--exclude='output'", "--exclude='tmp'"):
        assert forbidden_inline not in workflow


def test_lighthouse_rsync_artifact_contract_and_runbook_are_documented():
    contract = CONTRACT_FILE.read_text()
    runbook = RUNBOOK_FILE.read_text()
    scope_targets = DOCS_LINK_SCOPE.read_text().splitlines()

    for token in [
        "frontend_build_artifacts",
        "test_reports_and_traces",
        "runtime_outputs_and_screenshots",
        "local_workspace_state",
        "remote_only_landing_sidecars",
        "remote_only_production_sidecars",
        "landing_sidecar_sync_wrapper",
        "landing_sidecar_sync_defaults_to_dry_run",
        "landing_sidecar_sync_must_not_delete_remote_files",
        "production_secrets_and_certificates",
        "shared_exclude_file_required",
        "gnu_rsync_3_required_for_chmod",
    ]:
        assert token in contract

    for token in [
        "pytest tests/test_lighthouse_rsync_artifact_guard.py",
        "deploy/lighthouse/rsync-excludes.txt",
        "web/playwright-report",
        "tmp/screenshots",
        "output_uploaded",
        "*.sqlite3",
        "drafts",
        "ref",
        ".codegraph",
        "landing/login.html",
        "portal-auth",
        "docker-compose.prod.yml",
        "nginx.conf",
        "skills.conf",
        "auth_gate.conf",
        "momcozy-platform.conf",
        "plugin-hub.htpasswd",
        "*.candidate",
        "sync-landing-sidecars.sh",
        "DRY_RUN=1",
        "DRY_RUN=0",
        "GNU rsync 3.x",
        "不触发生成接口",
    ]:
        assert token in runbook

    assert "docs/runbooks/lighthouse-rsync-artifact-exclude.md" in scope_targets
