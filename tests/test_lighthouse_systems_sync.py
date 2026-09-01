"""Hermetic behavior tests for the systems.html-only Lighthouse sync gate."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "sync-landing-sidecars.sh"
REMOTE_HELPER = REPO_ROOT / "deploy" / "lighthouse" / "systems-sidecar-remote.py"
REMOTE_INSPECTOR = REPO_ROOT / "deploy" / "lighthouse" / "systems-sidecar-inspect.py"
SYSTEMS_SOURCE = REPO_ROOT / "deploy" / "lighthouse" / "landing" / "systems.html"
OTHER_LANDING_FILES = (
    "index.html",
    "login.html",
    "register.html",
    "lute-auth.css",
    "lute-auth.js",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_executable(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body).lstrip())
    path.chmod(0o755)


@dataclass(frozen=True)
class SyncHarness:
    env: dict[str, str]
    remote_root: Path
    landing_dir: Path
    target: Path
    baseline_bytes: bytes
    baseline_sha256: str
    candidate_bytes: bytes
    candidate_sha256: str
    ssh_log: Path
    rsync_log: Path

    @property
    def transaction_dir(self) -> Path:
        return (
            self.remote_root
            / "deploy"
            / "lighthouse"
            / ".landing-sidecar-sync"
            / "systems.html"
            / f"{self.baseline_sha256}--{self.candidate_sha256}"
        )

    def run(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = self.env | overrides
        return subprocess.run(
            ["bash", str(SYNC_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )


@pytest.fixture
def sync_harness(tmp_path: Path) -> SyncHarness:
    remote_root = tmp_path / "remote"
    landing_dir = remote_root / "deploy" / "lighthouse" / "landing"
    landing_dir.mkdir(parents=True)

    baseline_bytes = b"<!doctype html><title>production baseline</title>\n"
    target = landing_dir / "systems.html"
    target.write_bytes(baseline_bytes)
    target.chmod(0o644)
    for filename in OTHER_LANDING_FILES:
        (landing_dir / filename).write_bytes(f"unchanged:{filename}\n".encode())

    candidate_bytes = SYSTEMS_SOURCE.read_bytes()
    baseline_sha256 = _sha256(baseline_bytes)
    candidate_sha256 = _sha256(candidate_bytes)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    ssh_log = tmp_path / "ssh.log"
    rsync_log = tmp_path / "rsync.log"

    fake_ssh = fake_bin / "ssh"
    _write_executable(
        fake_ssh,
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        : "${FAKE_SSH_LOG:?}"
        printf '<%s>\n' "$@" >> "$FAKE_SSH_LOG"
        while [ "$#" -gt 0 ]; do
          case "$1" in
            -i|-o)
              shift 2
              ;;
            *@*)
              shift
              break
              ;;
            *)
              shift
              ;;
          esac
        done
        [ "$#" -gt 0 ] || { echo "fake ssh: missing remote command" >&2; exit 90; }
        exec "$@"
        """,
    )

    fake_rsync = fake_bin / "rsync"
    _write_executable(
        fake_rsync,
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        if [ "${1:-}" = "--version" ]; then
          echo "rsync  version 3.2.7  protocol version 31"
          exit 0
        fi
        : "${FAKE_RSYNC_LOG:?}"
        printf '<%s>\n' "$@" >> "$FAKE_RSYNC_LOG"
        args=("$@")
        dry_run=0
        for arg in "${args[@]}"; do
          [ "$arg" != "--dry-run" ] || dry_run=1
        done
        [ "${#args[@]}" -ge 2 ] || exit 91
        source_path="${args[${#args[@]}-2]}"
        destination="${args[${#args[@]}-1]}"
        destination_path="${destination#*:}"
        if [ "$dry_run" = "1" ]; then
          exit 0
        fi
        [ -d "$(dirname "$destination_path")" ] || exit 92
        if [ "${FAKE_RSYNC_CORRUPT_STAGE:-0}" = "1" ]; then
          printf 'corrupt-stage\n' > "$destination_path"
        else
          command cp "$source_path" "$destination_path"
        fi
        chmod 0644 "$destination_path"
        if [ -n "${FAKE_RSYNC_RACE_FILE:-}" ]; then
          command cp "$FAKE_RSYNC_RACE_FILE" "${FAKE_REMOTE_TARGET:?}"
          chmod 0644 "${FAKE_REMOTE_TARGET:?}"
        fi
        """,
    )

    _write_executable(
        fake_bin / "docker",
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        [ "$#" -eq 4 ]
        [ "$1" = "exec" ]
        [ "$2" = "ai_video_nginx" ]
        [ "$3" = "nginx" ]
        [ "$4" = "-t" ]
        """,
    )

    host_key = tmp_path / "fixture-host-key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(host_key)],
        check=True,
    )
    key_type, key_data, *_ = host_key.with_suffix(".pub").read_text().split()
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(f"127.0.0.1 {key_type} {key_data}\n")

    ssh_key = tmp_path / "fixture-client-key"
    ssh_key.write_text("fixture only\n")
    ssh_key.chmod(0o600)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SSH_BIN": str(fake_ssh),
            "RSYNC_BIN": str(fake_rsync),
            "FAKE_SSH_LOG": str(ssh_log),
            "FAKE_RSYNC_LOG": str(rsync_log),
            "FAKE_REMOTE_TARGET": str(target),
            "SERVER_IP": "127.0.0.1",
            "SSH_USER": "fixture",
            "REMOTE_DIR": str(remote_root),
            "SSH_KEY": str(ssh_key),
            "SSH_KNOWN_HOSTS_FILE": str(known_hosts),
            "BASELINE_SYSTEMS_SHA256": baseline_sha256,
            "CANDIDATE_SYSTEMS_SHA256": candidate_sha256,
        }
    )
    return SyncHarness(
        env=env,
        remote_root=remote_root,
        landing_dir=landing_dir,
        target=target,
        baseline_bytes=baseline_bytes,
        baseline_sha256=baseline_sha256,
        candidate_bytes=candidate_bytes,
        candidate_sha256=candidate_sha256,
        ssh_log=ssh_log,
        rsync_log=rsync_log,
    )


def test_systems_sync_defaults_to_exact_dry_run_without_remote_writes(
    sync_harness: SyncHarness,
) -> None:
    before = _tree_snapshot(sync_harness.remote_root)

    result = sync_harness.run()

    assert result.returncode == 0, result.stderr
    assert _tree_snapshot(sync_harness.remote_root) == before
    assert not sync_harness.transaction_dir.exists()
    assert "scope:          systems-only" in result.stdout
    assert "dry run:        1" in result.stdout
    assert "Dry run complete; no remote files were changed." in result.stdout
    rsync_log = sync_harness.rsync_log.read_text()
    assert "<--dry-run>" in rsync_log
    assert f"<{SYSTEMS_SOURCE}>" in rsync_log
    for filename in OTHER_LANDING_FILES:
        assert filename not in rsync_log
    ssh_log = sync_harness.ssh_log.read_text()
    assert "<StrictHostKeyChecking=yes>" in ssh_log
    assert "accept-new" not in ssh_log


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SYNC_SCOPE": "all"}, "SYNC_SCOPE must be systems-only"),
        ({"ACTION": "delete"}, "ACTION must be sync, rollback, or inspect"),
        ({"DRY_RUN": "yes"}, "DRY_RUN must be 1 or 0"),
        ({"BASELINE_SYSTEMS_SHA256": "bad"}, "BASELINE_SYSTEMS_SHA256 must be 64 lowercase hex"),
        ({"CANDIDATE_SYSTEMS_SHA256": "A" * 64}, "CANDIDATE_SYSTEMS_SHA256 must be 64 lowercase hex"),
    ],
)
def test_invalid_control_inputs_fail_before_any_remote_command(
    sync_harness: SyncHarness,
    overrides: dict[str, str],
    message: str,
) -> None:
    result = sync_harness.run(**overrides)

    assert result.returncode != 0
    assert message in result.stderr
    assert not sync_harness.ssh_log.exists()
    assert not sync_harness.rsync_log.exists()


def test_remote_baseline_mismatch_fails_without_remote_writes(
    sync_harness: SyncHarness,
) -> None:
    before = _tree_snapshot(sync_harness.remote_root)

    result = sync_harness.run(BASELINE_SYSTEMS_SHA256="0" * 64)

    assert result.returncode != 0
    assert "remote systems.html baseline SHA mismatch" in result.stderr
    assert _tree_snapshot(sync_harness.remote_root) == before
    assert not sync_harness.rsync_log.exists()


def test_live_sync_requires_a_second_explicit_confirmation(
    sync_harness: SyncHarness,
) -> None:
    before = _tree_snapshot(sync_harness.remote_root)

    result = sync_harness.run(DRY_RUN="0")

    assert result.returncode != 0
    assert "CONFIRM_SYSTEMS_LIVE must be 1" in result.stderr
    assert _tree_snapshot(sync_harness.remote_root) == before
    assert not sync_harness.ssh_log.exists()


def test_live_sync_is_atomic_receipted_and_does_not_touch_other_sidecars(
    sync_harness: SyncHarness,
) -> None:
    other_before = {
        filename: (sync_harness.landing_dir / filename).read_bytes()
        for filename in OTHER_LANDING_FILES
    }

    result = sync_harness.run(DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")

    assert result.returncode == 0, result.stderr
    assert sync_harness.target.read_bytes() == sync_harness.candidate_bytes
    for filename, expected in other_before.items():
        assert (sync_harness.landing_dir / filename).read_bytes() == expected

    transaction = sync_harness.transaction_dir
    assert (transaction / "baseline.html").read_bytes() == sync_harness.baseline_bytes
    assert (transaction / "candidate.html").read_bytes() == sync_harness.candidate_bytes
    assert (transaction / "activation-intent.v1.json").is_file()
    receipt = json.loads((transaction / "sync-receipt.v1.json").read_text())
    assert receipt == {
        "schema": "lighthouse-systems-sync-receipt.v1",
        "status": "activated",
        "scope": "systems-only",
        "baseline_sha256": sync_harness.baseline_sha256,
        "candidate_sha256": sync_harness.candidate_sha256,
        "backup_sha256": sync_harness.baseline_sha256,
        "post_sha256": sync_harness.candidate_sha256,
        "target_path": str(sync_harness.target),
        "backup_path": str(transaction / "baseline.html"),
        "candidate_backup_path": str(transaction / "candidate.html"),
        "activated_at_utc": receipt["activated_at_utc"],
    }
    assert result.stdout.count("systems.html") >= 1
    assert "Sidecar sync complete" in result.stdout


def test_corrupt_stage_fails_before_active_file_is_replaced(
    sync_harness: SyncHarness,
) -> None:
    result = sync_harness.run(
        DRY_RUN="0",
        CONFIRM_SYSTEMS_LIVE="1",
        FAKE_RSYNC_CORRUPT_STAGE="1",
    )

    assert result.returncode != 0
    assert "staged candidate SHA mismatch" in result.stderr
    assert sync_harness.target.read_bytes() == sync_harness.baseline_bytes
    assert not (sync_harness.transaction_dir / "sync-receipt.v1.json").exists()


def test_receipt_commit_failure_compensates_back_to_the_baseline(
    sync_harness: SyncHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = runpy.run_path(str(REMOTE_HELPER))
    transaction = namespace["SystemsTransaction"](
        str(sync_harness.remote_root),
        sync_harness.baseline_sha256,
        sync_harness.candidate_sha256,
    )
    transaction.prepare()
    transaction.stage.write_bytes(sync_harness.candidate_bytes)
    transaction.stage.chmod(0o644)
    module_globals = transaction.activate.__func__.__globals__
    real_writer = module_globals["_write_json_create_only"]

    def fail_final_receipt(path: Path, payload: dict[str, object]) -> None:
        if path.name == "sync-receipt.v1.json":
            raise OSError("fixture receipt write failure")
        real_writer(path, payload)

    monkeypatch.setitem(module_globals, "_write_json_create_only", fail_final_receipt)

    with pytest.raises(module_globals["GateError"], match="active baseline restored"):
        transaction.activate()

    assert sync_harness.target.read_bytes() == sync_harness.baseline_bytes
    assert sync_harness.target.stat().st_nlink == 1
    assert not sync_harness.target.samefile(transaction.baseline_backup)
    assert (sync_harness.transaction_dir / "activation-intent.v1.json").is_file()
    assert not (sync_harness.transaction_dir / "sync-receipt.v1.json").exists()


def test_second_cas_blocks_a_race_without_overwriting_the_race_winner(
    sync_harness: SyncHarness,
    tmp_path: Path,
) -> None:
    race_file = tmp_path / "race-winner.html"
    race_bytes = b"external race winner\n"
    race_file.write_bytes(race_bytes)

    result = sync_harness.run(
        DRY_RUN="0",
        CONFIRM_SYSTEMS_LIVE="1",
        FAKE_RSYNC_RACE_FILE=str(race_file),
    )

    assert result.returncode != 0
    assert "active systems.html changed after preflight" in result.stderr
    assert sync_harness.target.read_bytes() == race_bytes
    assert not (sync_harness.transaction_dir / "baseline.html").exists()
    assert not (sync_harness.transaction_dir / "sync-receipt.v1.json").exists()


def test_rollback_dry_run_is_read_only_and_live_rollback_is_cas_guarded(
    sync_harness: SyncHarness,
) -> None:
    activated = sync_harness.run(DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")
    assert activated.returncode == 0, activated.stderr
    before = _tree_snapshot(sync_harness.remote_root)

    dry_run = sync_harness.run(ACTION="rollback")

    assert dry_run.returncode == 0, dry_run.stderr
    assert "Rollback dry run complete; no remote files were changed." in dry_run.stdout
    assert _tree_snapshot(sync_harness.remote_root) == before

    rolled_back = sync_harness.run(
        ACTION="rollback",
        DRY_RUN="0",
        CONFIRM_SYSTEMS_LIVE="1",
    )

    assert rolled_back.returncode == 0, rolled_back.stderr
    assert sync_harness.target.read_bytes() == sync_harness.baseline_bytes
    rollback_receipt = json.loads(
        (sync_harness.transaction_dir / "rollback-receipt.v1.json").read_text()
    )
    assert rollback_receipt["schema"] == "lighthouse-systems-rollback-receipt.v1"
    assert rollback_receipt["status"] == "rolled_back"
    assert rollback_receipt["pre_rollback_sha256"] == sync_harness.candidate_sha256
    assert rollback_receipt["post_sha256"] == sync_harness.baseline_sha256


def test_rollback_refuses_active_sha_drift(
    sync_harness: SyncHarness,
) -> None:
    activated = sync_harness.run(DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")
    assert activated.returncode == 0, activated.stderr
    drift_bytes = b"newer independent active version\n"
    sync_harness.target.write_bytes(drift_bytes)

    result = sync_harness.run(
        ACTION="rollback",
        DRY_RUN="0",
        CONFIRM_SYSTEMS_LIVE="1",
    )

    assert result.returncode != 0
    assert "active systems.html no longer matches the candidate SHA" in result.stderr
    assert sync_harness.target.read_bytes() == drift_bytes
    assert not (sync_harness.transaction_dir / "rollback-receipt.v1.json").exists()


def test_read_only_inspection_reports_absent_and_activated_transaction(
    sync_harness: SyncHarness,
) -> None:
    before = _tree_snapshot(sync_harness.remote_root)
    initial = sync_harness.run(ACTION="inspect")

    assert initial.returncode == 0, initial.stderr
    assert '"transaction_state": "no-transaction"' in initial.stdout
    assert _tree_snapshot(sync_harness.remote_root) == before

    activated = sync_harness.run(DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")
    assert activated.returncode == 0, activated.stderr
    after_activation = _tree_snapshot(sync_harness.remote_root)
    inspected = sync_harness.run(ACTION="inspect")

    assert inspected.returncode == 0, inspected.stderr
    assert '"transaction_state": "activated-receipt-present"' in inspected.stdout
    assert _tree_snapshot(sync_harness.remote_root) == after_activation


def test_rollback_can_recover_from_valid_intent_when_final_receipt_is_missing(
    sync_harness: SyncHarness,
) -> None:
    activated = sync_harness.run(DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")
    assert activated.returncode == 0, activated.stderr
    (sync_harness.transaction_dir / "sync-receipt.v1.json").unlink()

    result = sync_harness.run(ACTION="rollback", DRY_RUN="0", CONFIRM_SYSTEMS_LIVE="1")

    assert result.returncode == 0, result.stderr
    assert sync_harness.target.read_bytes() == sync_harness.baseline_bytes
    receipt = json.loads((sync_harness.transaction_dir / "rollback-receipt.v1.json").read_text())
    assert receipt["recovery_source"] == "activation-intent"


def test_sync_wrapper_and_remote_helper_are_syntax_valid() -> None:
    subprocess.run(["bash", "-n", str(SYNC_SCRIPT)], check=True)
    compile(REMOTE_HELPER.read_text(), str(REMOTE_HELPER), "exec")
    compile(REMOTE_INSPECTOR.read_text(), str(REMOTE_INSPECTOR), "exec")
    assert "python3 -I -" in SYNC_SCRIPT.read_text()
