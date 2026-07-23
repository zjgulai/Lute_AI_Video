from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_w5_fast_readiness.py"
AUTHORIZATION_STATEMENT = (
    "I authorize exactly one W5 Fast provider submission bound to this plan; "
    "retry, publish, and delivery remain disabled."
)


def _files(tmp_path: Path, *, valid: bool = True) -> tuple[Path, Path]:
    from src.pipeline.w5_acceptance_harness import build_w5_plan_draft

    created_at = datetime.now(UTC) - timedelta(minutes=30)
    plan = build_w5_plan_draft(
        scenario="fast",
        tenant_id="tenant-alpha",
        sample_ref="sample:fast:001",
        budget_limit_usd_nanos=25_000_000,
        provider_job_caps={"llm": 1, "video": 1},
        created_at=created_at,
        expires_at=created_at + timedelta(hours=2),
    )
    payload: dict[str, Any] = {
        "version": "w5-fast-activation.v1",
        "scope": "w5-fast-activation",
        "activation_id": "w5fastact:fixture-cli",
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id if valid else "tenant-other",
        "scenario": "fast",
        "sample_ref": plan.sample_ref,
        "approved_by": "reviewer:ll",
        "approved_at": (created_at + timedelta(minutes=30)).isoformat(),
        "expires_at": (created_at + timedelta(hours=1, minutes=30)).isoformat(),
        "authorization_statement": AUTHORIZATION_STATEMENT,
        "template_only": False,
        "budget_limit_usd_nanos": plan.budget_limit_usd_nanos,
        "selected_optional_media": [],
        "provider_job_caps": {"llm": 1, "video": 1},
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "provider_mutation_approved": True,
        "runtime_binding_required": True,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    plan_path = tmp_path / "plan.json"
    activation_path = tmp_path / "activation.json"
    plan_path.write_text(plan.model_dump_json())
    activation_path.write_text(json.dumps(payload))
    return plan_path, activation_path


def _command(plan_path: Path, activation_path: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--plan",
        str(plan_path),
        "--activation",
        str(activation_path),
    ]


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("API_KEY", None)
    environment.pop("TEST_BUNDLE_KEY", None)
    environment.pop("POYO_API_KEY", None)
    environment.pop("DEEPSEEK_API_KEY", None)
    environment.pop("SILICONFLOW_API_KEY", None)
    return environment


def test_cli_prints_ready_report_without_keys_or_writes(tmp_path: Path) -> None:
    plan_path, activation_path = _files(tmp_path)
    before = {path: path.read_bytes() for path in (plan_path, activation_path)}

    result = subprocess.run(
        _command(plan_path, activation_path),
        cwd=REPO_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_private_binding"
    assert payload["ready_for_private_binding"] is True
    assert payload["provider_call_allowed"] is False
    assert payload["execution_authorized"] is False
    assert result.stderr == ""
    assert {path: path.read_bytes() for path in before} == before


def test_cli_returns_stable_json_block_and_exit_two(tmp_path: Path) -> None:
    plan_path, activation_path = _files(tmp_path, valid=False)

    result = subprocess.run(
        _command(plan_path, activation_path),
        cwd=REPO_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["provider_call_allowed"] is False
    assert "Traceback" not in result.stderr


def test_cli_requires_explicit_paths() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "required" in result.stderr


def test_cli_normalizes_unresolvable_home_path_to_secret_free_block(
    tmp_path: Path,
) -> None:
    _, activation_path = _files(tmp_path)

    result = subprocess.run(
        _command(
            Path("~codex_w5_missing_user_7f4d/plan.json"),
            activation_path,
        ),
        cwd=REPO_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["provider_call_allowed"] is False
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    assert str(REPO_ROOT) not in result.stdout


def test_cli_blocks_bounded_deep_json_without_traceback(tmp_path: Path) -> None:
    plan_path, activation_path = _files(tmp_path)
    plan_path.write_text(("[" * 15_000) + "0" + ("]" * 15_000))

    result = subprocess.run(
        _command(plan_path, activation_path),
        cwd=REPO_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["provider_call_allowed"] is False
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_cli_source_has_no_env_network_provider_database_or_execute_surface() -> None:
    tree = ast.parse(SCRIPT.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("requests", "httpx", "urllib", "provider", "storage", "database")
    assert not any(fragment in module for module in imported for fragment in forbidden)
    source = SCRIPT.read_text()
    assert "os.environ" not in source
    assert "--now" not in source
    assert "--execute" not in source
    assert "--approve" not in source
    assert "write_text" not in source
