"""Static guard for Lighthouse rsync artifact exclusions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.backup_manifest import build_source_manifest, validate_source_manifest

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
        ".env.local",
        ".env.production",
        ".env.prod",
        "*.pem",
        "*.key",
        "*.crt",
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
        ".playwright-cli",
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
        "deploy/lighthouse/landing/lute-*.html",
        "deploy/lighthouse/landing/voc-zh_messages.json",
        "deploy/lighthouse/landing/.portal.htpasswd",
        "deploy/lighthouse/landing/brand-placeholder.html",
    },
    "remote_only_production_sidecars": {
        "backups",
        "deploy/lighthouse/backups",
        "deploy/lighthouse/portal-auth",
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


def _write_nul_exclude_list(path: Path) -> None:
    entries = sorted(_exclude_entries())
    path.write_bytes(("\0".join(entries) + "\0").encode())


def test_lighthouse_rsync_excludes_generated_artifacts_by_category():
    excludes = _exclude_entries()
    for category, required in REQUIRED_EXCLUDES_BY_CATEGORY.items():
        missing = sorted(required - excludes)
        assert not missing, f"{category} missing rsync excludes: {missing}"


def test_codegraph_workspace_state_is_ignored_and_never_tracked() -> None:
    root_ignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".codegraph"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    present_tracked = [path for path in tracked if (REPO_ROOT / path).exists()]

    assert ".codegraph/" in root_ignore
    assert ".codegraph" in _exclude_entries()
    assert present_tracked == []


def test_release_rsync_tree_preserves_every_tracked_source_manifest_entry(
    tmp_path: Path,
) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    tracked = [path for path in tracked if path]
    manifest = build_source_manifest(REPO_ROOT, "0" * 40, tracked)
    release_root = tmp_path / "release"
    release_root.mkdir()
    file_list = tmp_path / "tracked-files.zlist"
    exclude_list = tmp_path / "release-excludes.zlist"
    file_list.write_bytes(("\0".join(tracked) + "\0").encode())
    _write_nul_exclude_list(exclude_list)

    result = subprocess.run(
        [
            "rsync",
            "-a",
            "--delete",
            "--from0",
            f"--files-from={file_list}",
            f"--exclude-from={exclude_list}",
            f"{REPO_ROOT}/",
            f"{release_root}/",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "discarding over-long filter" not in result.stderr
    validate_source_manifest(manifest, release_root)
    transferred = {
        path.relative_to(release_root).as_posix()
        for path in release_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    assert transferred == set(tracked)


def test_nul_safe_file_list_keeps_secret_excludes_effective(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    release_root = tmp_path / "release"
    source_root.mkdir()
    release_root.mkdir()
    (source_root / "safe.txt").write_text("safe")
    (source_root / ".env.local").write_text("must-not-transfer")
    (source_root / "private.key").write_text("must-not-transfer")
    file_list = tmp_path / "fixture-files.zlist"
    exclude_list = tmp_path / "fixture-excludes.zlist"
    file_list.write_bytes(b"safe.txt\0.env.local\0private.key\0")
    _write_nul_exclude_list(exclude_list)

    result = subprocess.run(
        [
            "rsync",
            "-a",
            "--from0",
            f"--files-from={file_list}",
            f"--exclude-from={exclude_list}",
            f"{source_root}/",
            f"{release_root}/",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "discarding over-long filter" not in result.stderr
    assert (release_root / "safe.txt").read_text() == "safe"
    assert not (release_root / ".env.local").exists()
    assert not (release_root / "private.key").exists()


def test_lighthouse_sync_entrypoints_use_the_shared_exclude_file():
    wrapper = BUILD_AND_DEPLOY.read_text()
    workflow = DEPLOY_WORKFLOW.read_text()

    assert 'EXCLUDE_FILE="${EXCLUDE_FILE:-$SCRIPT_DIR/rsync-excludes.txt}"' in wrapper
    assert 'done < "$EXCLUDE_FILE" > "$RSYNC_EXCLUDE_LIST"' in wrapper
    assert '--exclude-from="$RSYNC_EXCLUDE_LIST"' in wrapper
    assert "RSYNC_BIN" in wrapper
    assert "GNU rsync 3.x is required for --chmod=F644,D755" in wrapper
    assert 'git ls-files -z > "$RSYNC_FILE_LIST"' in wrapper
    assert 'printf \'%s\\0\' "source-manifest.v1.json" >> "$RSYNC_FILE_LIST"' in wrapper
    assert '--from0' in wrapper
    assert '--files-from="$RSYNC_FILE_LIST"' in wrapper
    assert '"$RSYNC_BIN" "${RSYNC_ARGS[@]}"' in wrapper
    assert (
        workflow.count(
            'done < deploy/lighthouse/rsync-excludes.txt > '
            '"$RUNNER_TEMP/release-excludes.zlist"'
        )
        >= 2
    )
    assert (
        workflow.count('--exclude-from="$RUNNER_TEMP/release-excludes.zlist"') >= 2
    )
    assert workflow.count("git ls-files -z > \"$RUNNER_TEMP/release-files.zlist\"") >= 2
    assert workflow.count("--from0") >= 2
    assert workflow.count('--files-from="$RUNNER_TEMP/release-files.zlist"') >= 2

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
        "immutable_release_contains_all_tracked_sources",
        "tracked_sidecar_copies_never_overwrite_shared_root",
    ]:
        assert token in contract

    for token in [
        "pytest tests/test_lighthouse_rsync_artifact_guard.py",
        "deploy/lighthouse/rsync-excludes.txt",
        ".playwright-cli",
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
