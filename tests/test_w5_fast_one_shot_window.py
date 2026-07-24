from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOW = REPO_ROOT / "deploy" / "lighthouse" / "w5-fast-one-shot-window.sh"
OPERATOR = REPO_ROOT / "scripts" / "w5_fast_one_shot_operator.py"
DEPLOY_WRAPPER = REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "w5-fast-one-shot-operator.md"


def _write_valid_plan(stage: Path, *, budget_limit_usd_nanos: object = 3_150_000_000) -> None:
    (stage / "plan.json").write_text(
        json.dumps(
            {
                "version": "w5-l4-plan-draft.v1",
                "budget_limit_usd_nanos": budget_limit_usd_nanos,
            }
        ),
        encoding="utf-8",
    )


def test_window_shell_syntax_and_restore_contract() -> None:
    result = subprocess.run(
        ["bash", "-n", str(WINDOW)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    source = WINDOW.read_text()
    trap_index = source.index("trap restore_provider_off EXIT")
    mutation_index = source.index("configure_w5_window")
    operation_index = source.index("run_operator")
    assert trap_index < mutation_index < operation_index
    assert "trap - EXIT" not in source
    assert "set -x" not in source
    assert "Idempotency-Key" not in source
    assert "RAW_KEY_FILE" not in source
    assert "verify_provider_off_restore" in source
    assert "W5_FAST_PLAN_PATH" in source
    assert "W5_FAST_ACTIVATION_PATH" in source
    assert "W5_FAST_RUNTIME_BINDING_PATH" in source
    assert "W5_FAST_EVIDENCE_PATH" in source
    assert "EXPECTED_BACKEND_IMAGE_ID" in source
    assert "org.opencontainers.image.revision" in source
    assert "{{.Image}}" in source
    assert "chown -R" not in source
    parent_owner_index = source.index('chown "$2:$3" "$parent"')
    leaf_owner_index = source.index('chown "$2:$3" "$1"', parent_owner_index)
    assert parent_owner_index < leaf_owner_index
    assert "TIKTOK_PUBLISH_ENABLED" in source
    assert "SHOPIFY_PUBLISH_ENABLED" in source
    assert "PROVIDER_JOB_BUDGET_USD" in source


def test_release_mode_safe_window_invocation_is_governed() -> None:
    deploy_source = DEPLOY_WRAPPER.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "--chmod=F644,D755" in deploy_source
    assert "bash deploy/lighthouse/w5-fast-one-shot-window.sh" in runbook


def test_operator_cli_has_fixed_backend_and_separate_execute_gate() -> None:
    source = OPERATOR.read_text()
    assert 'BACKEND_BASE_URL = "http://127.0.0.1:8001"' in source
    assert 'SUBMIT_PATH = "/fast/submit"' in source
    assert 'STATUS_OPENAPI_PATH = "/fast/status/{task_id}"' in source
    assert 'EXECUTE_ENV = "AI_VIDEO_W5_FAST_EXECUTE"' in source
    assert "/api/fast/submit" not in source
    assert "/api/fast/status/" not in source
    assert "PYTHON_DOTENV_DISABLED" in source
    assert "trust_env=False" in source
    assert "max_retries" not in source.lower()


@pytest.mark.parametrize("operator_result", [0, 2, 3, 5])
def test_window_fixture_restores_byte_identical_provider_off_env(
    tmp_path: Path,
    operator_result: int,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage)
    env_file = tmp_path / ".env.prod"
    original = (
        b"POYO_VIDEO_MODEL=happy-horse\n"
        b"TIKTOK_PUBLISH_ENABLED=false\n"
        b"SHOPIFY_PUBLISH_ENABLED=false\n"
        b"UNRELATED_VALUE=preserved-byte-for-byte\n"
    )
    env_file.write_bytes(original)

    environment = {
        **os.environ,
        "EXPECTED_SHA": "a" * 40,
        "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "c" * 64,
        "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "a" * 40,
        "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "c" * 64,
        "REMOTE_STAGE": str(stage),
        "REMOTE_PRIVATE": str(private),
        "AI_VIDEO_ENV_FILE": str(env_file),
        "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
        "AI_VIDEO_W5_FIXTURE_RESULT": str(operator_result),
        "AI_VIDEO_W5_FIXTURE_ASSERT_BUDGET": "3.15",
    }
    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == operator_result, result.stderr
    assert env_file.read_bytes() == original
    assert (stage / "restore-receipt.txt").read_text().strip() == (
        "provider_off_restore=pass"
    )
    assert "provider-off restoration verified" in result.stderr
    assert (stage / "window-budget-receipt.txt").read_text().strip() == "3.15"


def test_window_fixture_restore_failure_overrides_operation_success(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage)
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": "b" * 40,
            "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "d" * 64,
            "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "b" * 40,
            "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "d" * 64,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": str(private),
            "AI_VIDEO_ENV_FILE": str(env_file),
            "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
            "AI_VIDEO_W5_FIXTURE_RESULT": "0",
            "AI_VIDEO_W5_FIXTURE_RESTORE_FAIL": "1",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 90
    assert env_file.read_bytes() == original
    assert not (stage / "restore-receipt.txt").exists()
    assert "provider-off restoration failed" in result.stderr


@pytest.mark.parametrize(
    "plan_payload",
    [
        None,
        "{}",
        '{"budget_limit_usd_nanos":true}',
        '{"budget_limit_usd_nanos":0}',
        '{"budget_limit_usd_nanos":3150000000.0}',
        '{"budget_limit_usd_nanos":9223372036854775808}',
        '{"budget_limit_usd_nanos":3150000000,"budget_limit_usd_nanos":1}',
    ],
)
def test_window_rejects_invalid_plan_budget_before_env_mutation(
    tmp_path: Path,
    plan_payload: str | None,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    if plan_payload is not None:
        (stage / "plan.json").write_text(plan_payload, encoding="utf-8")
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": "b" * 40,
            "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "d" * 64,
            "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "b" * 40,
            "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "d" * 64,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": str(private),
            "AI_VIDEO_ENV_FILE": str(env_file),
            "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert env_file.read_bytes() == original
    assert not list(stage.glob("provider-off-backup.*"))
    assert not (stage / "persistent-evidence").exists()


@pytest.mark.parametrize(
    ("budget_limit_usd_nanos", "expected_display"),
    [
        (1, "0.000000001"),
        (1_000_000_000, "1"),
        (3_150_000_000, "3.15"),
        (2**63 - 1, "9223372036.854775807"),
    ],
)
def test_window_derives_canonical_provider_budget_from_plan(
    tmp_path: Path,
    budget_limit_usd_nanos: int,
    expected_display: str,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage, budget_limit_usd_nanos=budget_limit_usd_nanos)
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": "b" * 40,
            "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "d" * 64,
            "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "b" * 40,
            "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "d" * 64,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": str(private),
            "AI_VIDEO_ENV_FILE": str(env_file),
            "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
            "AI_VIDEO_W5_FIXTURE_ASSERT_BUDGET": expected_display,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_bytes() == original
    assert (stage / "window-budget-receipt.txt").read_text().strip() == expected_display


def test_window_freezes_same_plan_bytes_for_budget_and_runtime_copy(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage, budget_limit_usd_nanos=3_150_000_000)
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": "b" * 40,
            "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "d" * 64,
            "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "b" * 40,
            "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "d" * 64,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": str(private),
            "AI_VIDEO_ENV_FILE": str(env_file),
            "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
            "AI_VIDEO_W5_FIXTURE_ASSERT_BUDGET": "3.15",
            "AI_VIDEO_W5_FIXTURE_SWAP_PLAN_BUDGET_NANOS": "4000000000",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    frozen = stage / ".w5-plan-snapshot.json"
    assert result.returncode == 0, result.stderr
    assert json.loads((stage / "plan.json").read_text())["budget_limit_usd_nanos"] == 4_000_000_000
    assert json.loads(frozen.read_text())["budget_limit_usd_nanos"] == 3_150_000_000
    assert (private / "plan.json").read_bytes() == frozen.read_bytes()
    assert (frozen.stat().st_mode & 0o777) == 0o600
    assert (stage / "window-budget-receipt.txt").read_text().strip() == "3.15"
    assert env_file.read_bytes() == original


@pytest.mark.parametrize(
    "private_path",
    [
        "/",
        "/app",
        "/app/output",
        "/run//ai-video-w5",
        "/run/ai-video-w5/../escape",
    ],
)
def test_window_rejects_destructive_private_paths_before_env_mutation(
    tmp_path: Path,
    private_path: str,
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": "e" * 40,
            "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "f" * 64,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": private_path,
            "AI_VIDEO_ENV_FILE": str(env_file),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert env_file.read_bytes() == original
    assert not list(stage.iterdir())


@pytest.mark.parametrize("drift", ["revision", "image_id"])
def test_window_image_identity_drift_fails_before_env_mutation(
    tmp_path: Path,
    drift: str,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage)
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)
    expected_sha = "1" * 40
    expected_id = "sha256:" + "2" * 64
    actual_sha = "3" * 40 if drift == "revision" else expected_sha
    actual_id = "sha256:" + "4" * 64 if drift == "image_id" else expected_id

    result = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "EXPECTED_SHA": expected_sha,
            "EXPECTED_BACKEND_IMAGE_ID": expected_id,
            "REMOTE_STAGE": str(stage),
            "REMOTE_PRIVATE": str(private),
            "AI_VIDEO_ENV_FILE": str(env_file),
            "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
            "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": actual_sha,
            "AI_VIDEO_W5_FIXTURE_IMAGE_ID": actual_id,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert env_file.read_bytes() == original
    assert not (stage / "provider-off-backup").exists()


@pytest.mark.parametrize("drift", ["revision", "image_id", "configured_ref"])
def test_running_backend_identity_rejects_each_independent_drift(
    drift: str,
) -> None:
    source = WINDOW.read_text()
    start = source.index("_verify_running_backend_identity() {")
    end = source.index("\n}\n\n_derive_evidence_path", start) + 2
    function_source = source[start:end]
    expected_sha = "7" * 40
    expected_id = "sha256:" + "8" * 64
    actual_revision = "9" * 40 if drift == "revision" else expected_sha
    actual_id = "sha256:" + "a" * 64 if drift == "image_id" else expected_id
    actual_ref = (
        "lighthouse-backend:drift"
        if drift == "configured_ref"
        else f"lighthouse-backend:{expected_sha}"
    )
    script = f"""
set -euo pipefail
{function_source}
sudo() {{
  if [[ "$*" == *org.opencontainers.image.revision* ]]; then
    printf '%s\\n' "$ACTUAL_REVISION"
  elif [[ "$*" == *'{{{{.Config.Image}}}}'* ]]; then
    printf '%s\\n' "$ACTUAL_CONFIGURED_REF"
  elif [[ "$*" == *'{{{{.Image}}}}'* ]]; then
    printf '%s\\n' "$ACTUAL_IMAGE_ID"
  else
    printf 'UNEXPECTED_SUDO_CALL: %s\\n' "$*" >&2
    return 111
  fi
}}
_verify_running_backend_identity || exit 17
"""

    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "FIXTURE_MODE": "0",
            "EXPECTED_SHA": expected_sha,
            "EXPECTED_BACKEND_IMAGE_ID": expected_id,
            "ACTUAL_REVISION": actual_revision,
            "ACTUAL_IMAGE_ID": actual_id,
            "ACTUAL_CONFIGURED_REF": actual_ref,
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 17, result.stderr
    assert "UNEXPECTED_SUDO_CALL" not in result.stderr, result.stderr


@pytest.mark.parametrize("operator_result", [0, 2, 3])
def test_persistent_marker_survives_restore_and_blocks_second_post(
    tmp_path: Path,
    operator_result: int,
) -> None:
    stage = tmp_path / "stage"
    private = tmp_path / "private"
    stage.mkdir()
    private.mkdir()
    _write_valid_plan(stage)
    env_file = tmp_path / ".env.prod"
    original = b"TIKTOK_PUBLISH_ENABLED=false\nSHOPIFY_PUBLISH_ENABLED=false\n"
    env_file.write_bytes(original)
    environment = {
        **os.environ,
        "EXPECTED_SHA": "5" * 40,
        "EXPECTED_BACKEND_IMAGE_ID": "sha256:" + "6" * 64,
        "REMOTE_STAGE": str(stage),
        "REMOTE_PRIVATE": str(private),
        "AI_VIDEO_ENV_FILE": str(env_file),
        "AI_VIDEO_W5_WINDOW_FIXTURE": "1",
        "AI_VIDEO_W5_FIXTURE_RESULT": str(operator_result),
        "AI_VIDEO_W5_FIXTURE_IMAGE_REVISION": "5" * 40,
        "AI_VIDEO_W5_FIXTURE_IMAGE_ID": "sha256:" + "6" * 64,
    }

    first = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        ["bash", str(WINDOW)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    evidence = stage / "persistent-evidence" / "w5fastact:fixture"
    assert first.returncode == operator_result
    assert second.returncode != 0
    assert env_file.read_bytes() == original
    assert (evidence / "submit-invoked.json").is_file()
    assert (evidence / "post-count.txt").read_text().strip() == "1"


@pytest.mark.hermetic_slow
def test_evidence_parent_uid_boundary_allows_only_resolved_backend_uid() -> None:
    """Model the root setup/default-user transition used by the real window."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for the explicit UID-boundary lane")
    suffix = uuid4().hex[:12]
    container = "ai-video-w5-evidence-uid-" + suffix
    volume = "ai-video-w5-evidence-uid-" + suffix
    app_uid = "23145"
    app_gid = "23145"
    unrelated_uid = "23146"
    evidence = "/app/output/.w5-one-shot/w5fastact-fixture"
    created = subprocess.run(
        [docker, "volume", "create", volume],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    started = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-d",
            "--name",
            container,
            "-v",
            f"{volume}:/app/output",
            "--entrypoint",
            "sh",
            "postgres:18",
            "-c",
            "sleep 120",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        subprocess.run(
            [docker, "volume", "rm", "-f", volume],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pytest.fail(started.stderr)
    try:
        setup = subprocess.run(
            [
                docker,
                "exec",
                "-u",
                "0",
                container,
                "sh",
                "-c",
                'set -eu; parent=/app/output/.w5-one-shot; mkdir -m 700 "$parent"; '
                'chown "$2:$3" "$parent"; chmod 700 "$parent"; '
                'mkdir -m 700 "$1"; chown "$2:$3" "$1"; chmod 700 "$1"',
                "--",
                evidence,
                app_uid,
                app_gid,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert setup.returncode == 0, setup.stderr

        owner = subprocess.run(
            [
                docker,
                "exec",
                "-u",
                f"{app_uid}:{app_gid}",
                container,
                "sh",
                "-c",
                'set -eu; umask 077; set -C; printf "%s\\n" consumed > '
                '"$1/submit-invoked.json"; test "$(stat -c %a '
                '"$1/submit-invoked.json")" = 600',
                "--",
                evidence,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert owner.returncode == 0, owner.stderr

        unrelated = subprocess.run(
            [
                docker,
                "exec",
                "-u",
                f"{unrelated_uid}:{unrelated_uid}",
                container,
                "sh",
                "-c",
                'test ! -r "$1/submit-invoked.json"',
                "--",
                evidence,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert unrelated.returncode == 0, unrelated.stderr
    finally:
        subprocess.run(
            [docker, "rm", "-f", container],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [docker, "volume", "rm", "-f", volume],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
