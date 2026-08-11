"""W4-09-W4-13 release identity and operator-safety governance."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONTRACT = REPO_ROOT / "configs" / "project-release-governance.json"
AUTH_CONTRACT = REPO_ROOT / "configs" / "auth-permission-contract.json"


def _json(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing governance contract: {path.relative_to(REPO_ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


def _recognized_permissions_from_source() -> set[str]:
    path = REPO_ROOT / "src" / "routers" / "_deps.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_RECOGNIZED_TENANT_PERMISSIONS"
            for target in node.targets
        ):
            continue
        call = node.value
        assert isinstance(call, ast.Call) and len(call.args) == 1
        value = ast.literal_eval(call.args[0])
        return set(value)
    raise AssertionError("recognized tenant permission set is missing")


def test_project_version_check_uses_pyproject_authority() -> None:
    contract = _json(RELEASE_CONTRACT)
    assert contract["semantic_version_source"] == "pyproject.toml"
    assert contract["semantic_version"] == "2.0.0"
    assert contract["expected_tag"] == "v2.0.0"
    assert contract["expected_tag_exists"] is False

    result = subprocess.run(
        [sys.executable, "scripts/project_version.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "2.0.0"


def test_project_version_has_dependency_free_python39_fallback(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "project_version_compat", REPO_ROOT / "scripts" / "project_version.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_tomllib", None)

    assert module.check() == "2.0.0"


def test_images_and_release_compose_bind_both_release_identities() -> None:
    contract = _json(RELEASE_CONTRACT)
    for relative in contract["image_dockerfiles"]:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "ARG APP_VERSION" in text, relative
        assert 'org.opencontainers.image.version="${APP_VERSION}"' in text, relative
        assert 'org.opencontainers.image.revision="${RELEASE_SOURCE_SHA}"' in text, relative

    compose = (REPO_ROOT / "deploy/lighthouse/docker-compose.release.yml").read_text(
        encoding="utf-8"
    )
    assert compose.count("APP_VERSION: ${APP_VERSION:?APP_VERSION is required}") == 3
    assert "- APP_VERSION=${APP_VERSION:?APP_VERSION is required}" in compose
    assert "- RELEASE_SOURCE_SHA=${RELEASE_SOURCE_SHA:?RELEASE_SOURCE_SHA is required}" in compose


def test_health_reports_semantic_version_and_source_revision_separately() -> None:
    version_source = (REPO_ROOT / "src" / "_version.py").read_text(encoding="utf-8")
    health_source = (REPO_ROOT / "src" / "routers" / "health.py").read_text(encoding="utf-8")
    assert "APP_SOURCE_REVISION" in version_source
    assert "APP_SOURCE_REVISION" in health_source
    assert health_source.count('"source_revision": APP_SOURCE_REVISION') >= 3


def test_auth_permission_contract_matches_code_and_documents_all_planes() -> None:
    contract = _json(AUTH_CONTRACT)
    assert set(contract["tenant_api_key"]["recognized_permissions"]) == (
        _recognized_permissions_from_source()
    )
    assert contract["environment_fallback"]["permissions"] == ["all"]
    assert contract["test_bundle"]["production_default"] == "rejected"
    assert contract["test_bundle"]["explicit_enable_permissions"] == ["all"]
    assert contract["admin"]["authentication"] == "session_cookie"
    assert contract["admin"]["write_protection"] == "csrf"

    for relative in contract["active_documentation"]:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for marker in contract["required_document_markers"]:
            assert marker in text, f"{relative} is missing auth marker {marker!r}"
        assert "demo key (`ai_video_demo_2026`) is read-only" not in text.lower()

    production_e2e = contract["production_e2e"]
    assert production_e2e["public_readonly_job_has_api_key"] is False
    assert production_e2e["authenticated_readonly_workflow"] is False
    workflow = (REPO_ROOT / production_e2e["workflow"]).read_text(encoding="utf-8")
    readonly_job = workflow.split("  e2e-prod-readonly:", 1)[1].split(
        "  e2e-prod-token-smoke:", 1
    )[0]
    assert "PLAYWRIGHT_API_KEY" not in readonly_job
    assert "secrets." not in readonly_job
    documentation = (REPO_ROOT / production_e2e["documentation"]).read_text(
        encoding="utf-8"
    )
    assert "public read-only job intentionally receives no API key" in documentation
    assert "partial public evidence" in documentation


def test_one_canonical_operations_entrypoint_owns_deploy_dr_and_token_smoke() -> None:
    contract = _json(RELEASE_CONTRACT)
    owners = contract["canonical_operations"]
    assert owners == {
        "entrypoint": "docs/runbooks/production-operations.md",
        "deploy": "docs/workflows/deploy-lighthouse-stable.md",
        "disaster_recovery": "docs/disaster_recovery_runbook.md",
        "token_smoke": "docs/runbooks/production-e2e-token-smoke.md",
    }
    for relative in owners.values():
        assert (REPO_ROOT / relative).is_file(), relative

    for relative in contract["historical_operations_docs"]:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "status: historical" in text
        assert "不作为当前执行入口" in text
        assert "```bash" not in text


def test_active_operations_surfaces_reject_copyable_dangerous_patterns() -> None:
    contract = _json(RELEASE_CONTRACT)
    patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in contract["forbidden_patterns"]]
    scope_file = REPO_ROOT / contract["active_operations_document_scope"]
    document_surfaces = [
        line.strip()
        for line in scope_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    surfaces = document_surfaces + contract["active_operations_non_document_surfaces"]
    assert "docs/workflows/update-guide-stable.md" not in document_surfaces
    assert "deploy/lighthouse/PHASE0-DEPLOY-SOP-2026-05-15.md" not in document_surfaces
    for relative in surfaces:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for pattern in patterns:
            assert not pattern.search(text), f"{relative} matches forbidden pattern {pattern.pattern!r}"

    for relative in contract["historical_evidence_docs"]:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "status: historical" in text
        assert relative not in document_surfaces


def test_archive_candidate_scripts_are_unreachable_from_current_entrypoints() -> None:
    scripts = _json(REPO_ROOT / "configs" / "scripts-governance-contract.json")
    archive_names = {
        Path(item["path"]).name
        for item in scripts["legacy_one_off_scripts"]
        if item["status"] == "archive_candidate"
    }
    entrypoints = [
        REPO_ROOT / "Makefile",
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
        REPO_ROOT / ".github" / "workflows" / "deploy.yml",
        REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh",
        REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh",
        REPO_ROOT / "docs" / "runbooks" / "production-operations.md",
    ]
    for entrypoint in entrypoints:
        text = entrypoint.read_text(encoding="utf-8")
        for name in archive_names:
            assert name not in text, f"{entrypoint.relative_to(REPO_ROOT)} calls archive candidate {name}"


def test_current_docs_do_not_offer_legacy_provider_execution_semantics() -> None:
    contract = _json(RELEASE_CONTRACT)
    scope_file = REPO_ROOT / contract["active_operations_document_scope"]
    current_docs = [
        line.strip()
        for line in scope_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    forbidden = (
        "p2_recharge_smoke_checklist.py --execute",
        "authorized_live_token_smoke_harness.py --execute",
        "Real generation remains P2",
        "真 provider smoke 只能留在 P2",
        "真实生成 smoke 继续走 P2",
    )
    for relative in current_docs:
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{relative} retains legacy provider instruction {token}"


def test_current_backlog_is_tracked_and_history_is_not_an_active_owner() -> None:
    contract = _json(RELEASE_CONTRACT)
    current = contract["current_backlog"]
    history = contract["historical_backlog"]
    assert current == "docs/backlog/current.md"
    assert history == "docs/claude/known-gaps-stable.md"
    current_text = (REPO_ROOT / current).read_text(encoding="utf-8")
    history_text = (REPO_ROOT / history).read_text(encoding="utf-8")
    assert "status: active" in current_text
    assert "status: historical" in history_text
    assert "append-only" in history_text
    assert ".kiro/" not in current_text

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", current],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    # A newly created candidate is not in the index yet; git ls-files --others
    # proves it is a non-ignored tracked candidate without staging it.
    if tracked.returncode != 0:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", current],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert untracked.stdout.strip() == current
