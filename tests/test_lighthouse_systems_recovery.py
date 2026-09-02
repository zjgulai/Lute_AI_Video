"""Crash-recovery and inspection contracts for the systems-only sync helper."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REMOTE_HELPER = REPO_ROOT / "deploy" / "lighthouse" / "systems-sidecar-remote.py"
REMOTE_INSPECTOR = REPO_ROOT / "deploy" / "lighthouse" / "systems-sidecar-inspect.py"


@dataclass(frozen=True)
class RecoveryFixture:
    namespace: dict[str, Any]
    transaction: Any
    target: Path
    baseline_bytes: bytes
    candidate_bytes: bytes
    baseline_sha256: str
    candidate_sha256: str


@pytest.fixture
def recovery_fixture(tmp_path: Path) -> RecoveryFixture:
    root = tmp_path / "remote"
    landing = root / "deploy" / "lighthouse" / "landing"
    landing.mkdir(parents=True)
    baseline_bytes = b"baseline systems\n"
    candidate_bytes = b"candidate systems\n"
    target = landing / "systems.html"
    target.write_bytes(baseline_bytes)
    target.chmod(0o644)
    baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    namespace = runpy.run_path(str(REMOTE_HELPER))
    transaction = namespace["SystemsTransaction"](
        str(root), baseline_sha256, candidate_sha256,
    )
    transaction.prepare()
    transaction.stage.write_bytes(candidate_bytes)
    transaction.stage.chmod(0o644)
    return RecoveryFixture(
        namespace, transaction, target, baseline_bytes, candidate_bytes,
        baseline_sha256, candidate_sha256,
    )


def test_atomic_record_publish_leaves_final_valid_and_no_pending_file(
    recovery_fixture: RecoveryFixture,
) -> None:
    recovery_fixture.transaction.activate()
    receipt = recovery_fixture.transaction.sync_receipt

    assert json.loads(receipt.read_text())["status"] == "activated"
    assert receipt.stat().st_nlink == 1
    assert recovery_fixture.target.stat().st_nlink == 1
    assert not recovery_fixture.target.samefile(recovery_fixture.transaction.candidate_backup)
    assert not receipt.with_name(f".{receipt.name}.partial").exists()


def test_two_sequential_forward_activations_keep_active_file_independent(
    recovery_fixture: RecoveryFixture,
) -> None:
    first = recovery_fixture.transaction
    first.activate()
    second_bytes = b"second candidate systems\n"
    second_sha256 = hashlib.sha256(second_bytes).hexdigest()
    second = recovery_fixture.namespace["SystemsTransaction"](
        str(first.remote_root), recovery_fixture.candidate_sha256, second_sha256,
    )
    second.prepare()
    second.stage.write_bytes(second_bytes)
    second.stage.chmod(0o644)

    second.activate()

    assert recovery_fixture.target.read_bytes() == second_bytes
    assert recovery_fixture.target.stat().st_nlink == 1
    assert not recovery_fixture.target.samefile(second.candidate_backup)


def test_stage_inode_change_after_backup_is_rejected_before_activation(
    recovery_fixture: RecoveryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = recovery_fixture.transaction
    module_globals = transaction.activate.__func__.__globals__
    real_copy = module_globals["_copy_create_only"]

    def swap_stage_after_copy(source: Path, destination: Path) -> None:
        real_copy(source, destination)
        if destination == transaction.candidate_backup:
            # Keep the unlinked file alive until its replacement exists. Linux may
            # otherwise immediately reuse the same inode, making this identity-swap
            # regression nondeterministic despite the pathname being replaced.
            with transaction.stage.open("rb") as original_stage:
                transaction.stage.unlink()
                transaction.stage.write_bytes(recovery_fixture.candidate_bytes)
                transaction.stage.chmod(0o644)
                assert original_stage.fileno() >= 0

    monkeypatch.setitem(module_globals, "_copy_create_only", swap_stage_after_copy)

    with pytest.raises(module_globals["GateError"], match="identity changed immediately"):
        transaction.activate()

    assert recovery_fixture.target.read_bytes() == recovery_fixture.baseline_bytes


def test_rollback_recovers_after_kill_left_only_an_unpublished_receipt(
    recovery_fixture: RecoveryFixture,
) -> None:
    transaction = recovery_fixture.transaction
    transaction.activate()
    transaction.sync_receipt.unlink()
    pending = transaction.sync_receipt.with_name(f".{transaction.sync_receipt.name}.partial")
    pending.write_bytes(b'{"schema":')
    pending.chmod(0o600)

    transaction.rollback()

    assert recovery_fixture.target.read_bytes() == recovery_fixture.baseline_bytes
    receipt = json.loads(transaction.rollback_receipt.read_text())
    assert receipt["recovery_source"] == "activation-intent"
    assert pending.read_bytes() == b'{"schema":'


def test_inspector_treats_corrupt_receipt_without_recovery_chain_as_ambiguous(
    recovery_fixture: RecoveryFixture,
) -> None:
    transaction = recovery_fixture.transaction
    transaction.activate()
    transaction.sync_receipt.write_text("not-json\n")
    transaction.activation_intent.unlink()
    transaction.baseline_backup.unlink()
    transaction.candidate_backup.unlink()
    inspector = runpy.run_path(str(REMOTE_INSPECTOR))

    result = inspector["inspect"](
        str(transaction.remote_root),
        recovery_fixture.baseline_sha256,
        recovery_fixture.candidate_sha256,
    )

    assert result["transaction_state"] == "ambiguous-manual-recovery"
    assert any("invalid JSON" in error for error in result["validation_errors"])


def test_inspector_reports_valid_intent_with_pending_receipt_as_recoverable(
    recovery_fixture: RecoveryFixture,
) -> None:
    transaction = recovery_fixture.transaction
    transaction.activate()
    transaction.sync_receipt.unlink()
    pending = transaction.sync_receipt.with_name(f".{transaction.sync_receipt.name}.partial")
    pending.write_bytes(b"incomplete")
    pending.chmod(0o600)
    inspector = runpy.run_path(str(REMOTE_INSPECTOR))

    result = inspector["inspect"](
        str(transaction.remote_root),
        recovery_fixture.baseline_sha256,
        recovery_fixture.candidate_sha256,
    )

    assert result["transaction_state"] == "active-candidate-receipt-missing"
    assert result["pending_record_writes"] == [pending.name]


def test_inspector_rejects_symlinked_state_parent(
    recovery_fixture: RecoveryFixture,
) -> None:
    transaction = recovery_fixture.transaction
    transaction.activate()
    moved_state = transaction.remote_root / "moved-state"
    transaction.state_root.rename(moved_state)
    transaction.state_root.symlink_to(moved_state, target_is_directory=True)
    inspector = runpy.run_path(str(REMOTE_INSPECTOR))

    with pytest.raises(inspector["InspectError"], match="not a real directory"):
        inspector["inspect"](
            str(transaction.remote_root),
            recovery_fixture.baseline_sha256,
            recovery_fixture.candidate_sha256,
        )


def test_inspector_marks_interrupted_rollback_replacement_as_ambiguous(
    recovery_fixture: RecoveryFixture,
) -> None:
    transaction = recovery_fixture.transaction
    transaction.activate()
    recovery_fixture.namespace["_copy_create_only"](
        transaction.baseline_backup, transaction.rollback_stage,
    )
    inspector = runpy.run_path(str(REMOTE_INSPECTOR))

    result = inspector["inspect"](
        str(transaction.remote_root),
        recovery_fixture.baseline_sha256,
        recovery_fixture.candidate_sha256,
    )

    assert result["transaction_state"] == "ambiguous-manual-recovery"
    assert "rollback replacement was interrupted" in result["validation_errors"]
