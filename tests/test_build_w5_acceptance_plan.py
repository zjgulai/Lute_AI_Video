from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_w5_acceptance_plan.py"


def _command(*extra: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--scenario",
        "s3",
        "--tenant-id",
        "tenant-alpha",
        "--sample-ref",
        "sample:s3:001",
        "--budget-usd-nanos",
        "25000000",
        "--provider-job-caps",
        '{"llm":2,"image":3,"video":3,"tts":1,"thumbnail":2}',
        "--created-at",
        "2026-07-23T08:00:00Z",
        "--expires-at",
        "2026-07-23T10:00:00Z",
        *extra,
    ]


def _environment_without_api_keys() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("API_KEY", None)
    environment.pop("TEST_BUNDLE_KEY", None)
    return environment


def test_cli_help_has_no_api_key_environment_dependency() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        env=_environment_without_api_keys(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_prints_draft_without_api_key_environment_dependency() -> None:
    result = subprocess.run(
        _command(),
        cwd=REPO_ROOT,
        env=_environment_without_api_keys(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "draft_pending_human_review"
    assert "Traceback" not in result.stderr


def test_cli_prints_non_authorizing_draft_json_without_writing() -> None:
    result = subprocess.run(
        _command(),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "draft_pending_human_review"
    assert payload["template_only"] is True
    assert payload["provider_calls_allowed"] is False
    assert payload["execution_authorized"] is False
    assert payload["runtime_profile_bound"] is False
    assert payload["provider_job_caps"] == {
        "llm": 2,
        "image": 3,
        "video": 3,
        "tts": 1,
        "thumbnail": 2,
    }


def test_cli_writes_only_under_repo_tmp_and_refuses_overwrite(tmp_path: Path) -> None:
    repo_tmp = REPO_ROOT / "tmp" / "w5-cli-tests"
    repo_tmp.mkdir(parents=True, exist_ok=True)
    output = repo_tmp / f"{os.getpid()}-{tmp_path.name}.json"
    output.unlink(missing_ok=True)

    first = subprocess.run(
        _command("--output", str(output)),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        _command("--output", str(output)),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    try:
        assert first.returncode == 0, first.stderr
        assert json.loads(output.read_text())["scenario"] == "s3"
        assert second.returncode == 2
        assert "already exists" in second.stderr
    finally:
        output.unlink(missing_ok=True)


def test_cli_force_overwrites_private_draft(tmp_path: Path) -> None:
    output = tmp_path / "draft.json"
    output.write_text("stale")

    result = subprocess.run(
        _command("--output", str(output), "--force"),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["plan_id"].startswith("w5plan:")


def test_cli_rejects_tracked_repository_output() -> None:
    output = REPO_ROOT / "docs" / "w5-live-plan.json"
    result = subprocess.run(
        _command("--output", str(output)),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "under tmp/ or outside" in result.stderr
    assert not output.exists()


def test_cli_rejects_directory_output_with_stable_secret_free_error() -> None:
    result = subprocess.run(
        _command("--output", str(REPO_ROOT / "tmp"), "--force"),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("ERROR: ")
    assert "output target must be a file" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_rejects_bad_caps_with_stable_secret_free_error() -> None:
    command = _command()
    index = command.index("--provider-job-caps") + 1
    command[index] = '{"llm":1,"video":1}'

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("ERROR: ")
    assert "provider job cap categories" in result.stderr


def test_cli_fast_optional_tts_requires_explicit_selection_and_cap() -> None:
    command = _command()
    replacements = {
        "s3": "fast",
        "sample:s3:001": "sample:fast:001",
        '{"llm":2,"image":3,"video":3,"tts":1,"thumbnail":2}': '{"llm":1,"video":1,"tts":1}',
    }
    command = [replacements.get(item, item) for item in command]
    command.extend(("--select-optional-media", "tts_audio"))

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_optional_media"] == ["tts_audio"]
    assert payload["provider_job_caps"]["tts"] == 1


def test_cli_source_has_no_network_provider_environment_or_execute_surface() -> None:
    tree = ast.parse(SCRIPT.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden_import_fragments = (
        "requests",
        "httpx",
        "urllib",
        "poyo",
        "seedance",
        "provider_execution",
        "provider_cost",
    )
    assert not any(
        fragment in module
        for module in imported
        for fragment in forbidden_import_fragments
    )
    source = SCRIPT.read_text()
    assert "os.environ" not in source
    assert "--execute" not in source
    assert "--approve" not in source
