"""Static guard for docs link-check scope.

The lychee job should protect current formal docs, not every historical note.
This test keeps the CI job blocking and ties its target list to a reviewed
allowlist so archived/research/planning docs do not create noisy failures.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

HISTORICAL_PREFIXES = (
    ".kiro/",
    "docs/research/",
    "docs/superpowers/plans/",
    "docs/superpowers/specs/",
)

REQUIRED_SCOPE_TARGETS = {
    "README.md",
    "AGENTS.md",
    "docs/claude/known-gaps-stable.md",
    "docs/claude/project-standard-stable.md",
    "docs/reference/api-endpoints.md",
    "docs/runbooks/README.md",
    "docs/runbooks/production-e2e-token-smoke.md",
    "docs/runbooks/s1-s5-hermetic-regression.md",
    "deploy/local-run.md",
    "deploy/tencent-cloudbase.md",
}


def _ci_workflow() -> dict:
    return yaml.safe_load(CI_YML.read_text())


def _docs_link_check_job() -> dict:
    workflow = _ci_workflow()
    jobs = workflow.get("jobs") or {}
    assert "docs-link-check" in jobs, "ci.yml must keep the docs link-check job"
    return jobs["docs-link-check"]


def _lychee_step() -> dict:
    steps = _docs_link_check_job().get("steps") or []
    matches = [
        step
        for step in steps
        if step.get("uses", "").startswith("lycheeverse/lychee-action@")
    ]
    assert matches, "docs-link-check must run lychee-action"
    return matches[0]


def _lychee_args() -> list[str]:
    args = _lychee_step().get("with", {}).get("args") or ""
    return shlex.split(args)


def _scope_targets() -> list[str]:
    assert SCOPE_FILE.exists(), "docs link-check scope file is missing"
    targets = [
        line.strip()
        for line in SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert targets, "docs link-check scope file must list at least one target"
    return targets


def test_docs_link_check_is_blocking():
    step = _lychee_step()
    job = _docs_link_check_job()

    assert step.get("with", {}).get("fail") is True
    assert step.get("continue-on-error") is not True
    assert job.get("continue-on-error") is not True


def test_docs_link_check_keeps_offline_mode_and_local_excludes():
    args = _lychee_args()

    assert "--offline" in args
    assert "--no-progress" in args
    assert "--exclude" in args
    assert "^https?://(localhost|127\\.0\\.0\\.1|101\\.34\\.52\\.232)" in args
    assert "^file://" in args


def test_docs_link_check_uses_curated_scope_instead_of_broad_globs():
    args = _lychee_args()
    forbidden_patterns = {
        "docs/**/*.md",
        ".kiro/plan/*.md",
        "docs/**",
        ".kiro/**",
    }

    for pattern in forbidden_patterns:
        assert pattern not in args

    scope_targets = _scope_targets()
    arg_targets = [
        arg for arg in args if arg.endswith(".md") and not arg.startswith("http")
    ]
    assert arg_targets == scope_targets


def test_docs_link_check_scope_is_current_formal_docs_only():
    scope_targets = _scope_targets()

    assert REQUIRED_SCOPE_TARGETS.issubset(set(scope_targets))

    for target in scope_targets:
        assert "*" not in target, f"scope target must be explicit, got glob: {target}"
        assert not target.startswith(HISTORICAL_PREFIXES), (
            f"historical docs must stay out of the blocking link check: {target}"
        )
        assert (REPO_ROOT / target).is_file(), f"scope target does not exist: {target}"
