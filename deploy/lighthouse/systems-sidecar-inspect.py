#!/usr/bin/env python3
"""Read-only inspection for one exact systems.html sidecar transaction."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import NoReturn

SHA256_RE = re.compile(r"[0-9a-f]{64}")


class InspectError(RuntimeError):
    pass


def _fail(message: str) -> NoReturn:
    raise InspectError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory(path: Path, *, owner: bool, mode: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail(f"required directory is missing: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if owner and info.st_uid != os.geteuid():
        _fail(f"directory is not owned by the remote SSH user: {path}")
    permissions = stat.S_IMODE(info.st_mode)
    if mode is not None and permissions != mode:
        _fail(f"directory mode must be {mode:04o}: {path}")
    if mode is None and permissions & 0o022:
        _fail(f"directory must not be group/world writable: {path}")
    return info


def _artifact(path: Path, expected_mode: int) -> dict[str, object]:
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != expected_mode):
        _fail(f"transaction artifact identity is unsafe: {path}")
    return {"sha256": _sha256(path), "size": info.st_size}


def _load_record(path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"record is unreadable or invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "record root must be an object"
    return payload, None


def _record_error(
    payload: dict[str, object], expected: dict[str, object], timestamp: str,
) -> str | None:
    if set(payload) != {*expected, timestamp}:
        return "record fields mismatch"
    for key, value in expected.items():
        if payload.get(key) != value:
            return f"record field mismatch: {key}"
    value = payload.get(timestamp)
    if not isinstance(value, str) or not value.endswith("Z"):
        return f"record UTC timestamp is invalid: {timestamp}"
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"record UTC timestamp is invalid: {timestamp}"
    if parsed.utcoffset() != dt.timedelta(0):
        return f"record UTC timestamp is invalid: {timestamp}"
    return None


def inspect(remote_dir: str, baseline: str, candidate: str) -> dict[str, object]:
    if SHA256_RE.fullmatch(baseline) is None or SHA256_RE.fullmatch(candidate) is None:
        _fail("baseline and candidate SHA must be 64 lowercase hex")
    root = Path(remote_dir)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        _fail("REMOTE_DIR must be an existing normalized non-symlink absolute path")
    lighthouse = root / "deploy" / "lighthouse"
    landing = lighthouse / "landing"
    target = landing / "systems.html"
    _directory(root, owner=False)
    _directory(lighthouse, owner=True)
    _directory(landing, owner=True)
    target_info = target.lstat()
    if (stat.S_ISLNK(target_info.st_mode) or not stat.S_ISREG(target_info.st_mode)
            or target_info.st_uid != os.geteuid() or stat.S_IMODE(target_info.st_mode) != 0o644):
        _fail("active systems.html identity is unsafe")
    active_sha = _sha256(target)
    active_state = "baseline" if active_sha == baseline else "candidate" if active_sha == candidate else "other"
    state_root = lighthouse / ".landing-sidecar-sync"
    product_root = state_root / "systems.html"
    transaction = product_root / f"{baseline}--{candidate}"
    for parent in (state_root, product_root):
        if os.path.lexists(parent):
            _directory(parent, owner=True, mode=0o700)
    result: dict[str, object] = {
        "schema": "lighthouse-systems-inspection.v1",
        "active_sha256": active_sha,
        "active_state": active_state,
        "transaction_exists": os.path.lexists(transaction),
        "artifacts": {},
    }
    if not os.path.lexists(transaction):
        result["transaction_state"] = "no-transaction"
        return result
    _directory(transaction, owner=True, mode=0o700)
    modes = {
        "candidate.partial": 0o644, "baseline.html": 0o644, "candidate.html": 0o644,
        "activation-intent.v1.json": 0o600, "sync-receipt.v1.json": 0o600,
        "rollback-receipt.v1.json": 0o600, "rollback.partial": 0o644,
        ".activation-intent.v1.json.partial": 0o600,
        ".sync-receipt.v1.json.partial": 0o600,
        ".rollback-receipt.v1.json.partial": 0o600,
    }
    artifacts = result["artifacts"]
    assert isinstance(artifacts, dict)
    for name, mode in modes.items():
        path = transaction / name
        if os.path.lexists(path):
            artifacts[name] = _artifact(path, mode)
    unknown = sorted(path.name for path in transaction.iterdir() if path.name not in modes)
    errors = [f"unknown transaction artifact: {name}" for name in unknown]
    names = set(artifacts)
    base: dict[str, object] = {
        "scope": "systems-only", "baseline_sha256": baseline,
        "candidate_sha256": candidate, "target_path": str(target),
        "backup_path": str(transaction / "baseline.html"),
        "candidate_backup_path": str(transaction / "candidate.html"),
    }

    def exact_record(name: str, expected: dict[str, object], timestamp: str) -> bool:
        if name not in artifacts:
            return False
        payload, error = _load_record(transaction / name)
        if error is None and payload is not None:
            error = _record_error(payload, expected, timestamp)
        if error is not None:
            errors.append(f"{name}: {error}")
            return False
        return True

    intent_name = "activation-intent.v1.json"
    receipt_name = "sync-receipt.v1.json"
    rollback_name = "rollback-receipt.v1.json"
    intent = exact_record(
        intent_name,
        {**base, "schema": "lighthouse-systems-activation-intent.v1",
         "status": "activation-authorized"},
        "authorized_at_utc",
    )
    receipt = exact_record(
        receipt_name,
        {**base, "schema": "lighthouse-systems-sync-receipt.v1", "status": "activated",
         "backup_sha256": baseline, "post_sha256": candidate},
        "activated_at_utc",
    )
    rollback_payload, rollback_error = (None, None)
    if rollback_name in artifacts:
        rollback_payload, rollback_error = _load_record(transaction / rollback_name)
    recovery_source = rollback_payload.get("recovery_source") if rollback_payload else None
    if rollback_payload is not None and recovery_source not in {"sync-receipt", "activation-intent"}:
        rollback_error = "rollback recovery source is invalid"
    if rollback_payload is not None and rollback_error is None:
        rollback_error = _record_error(
            rollback_payload,
            {**base, "schema": "lighthouse-systems-rollback-receipt.v1",
             "status": "rolled_back", "pre_rollback_sha256": candidate,
             "post_sha256": baseline, "recovery_source": recovery_source},
            "rolled_back_at_utc",
        )
    if rollback_error is not None:
        errors.append(f"{rollback_name}: {rollback_error}")
    rollback = rollback_payload is not None and rollback_error is None
    baseline_backup = artifacts.get("baseline.html")
    candidate_backup = artifacts.get("candidate.html")
    backups = (
        isinstance(baseline_backup, dict) and baseline_backup.get("sha256") == baseline
        and isinstance(candidate_backup, dict) and candidate_backup.get("sha256") == candidate
    )
    control_present = any(name in artifacts for name in (intent_name, receipt_name, rollback_name))
    if control_present and not backups:
        errors.append("control record requires exact baseline and candidate backups")
    if receipt_name in artifacts and not intent:
        errors.append("sync receipt requires an exact activation intent")
    if rollback_name in artifacts and not intent:
        errors.append("rollback receipt requires an exact activation intent")
    if rollback and recovery_source == "sync-receipt" and not receipt:
        errors.append("rollback receipt references a missing or invalid sync receipt")
    sync_pending = ".sync-receipt.v1.json.partial"
    rollback_record_pending = ".rollback-receipt.v1.json.partial"
    activation_pending = ".activation-intent.v1.json.partial"

    def same_inode(first: str, second: str) -> bool:
        first_info = (transaction / first).lstat()
        second_info = (transaction / second).lstat()
        return (first_info.st_dev, first_info.st_ino) == (second_info.st_dev, second_info.st_ino)

    linked_sync_pending = (
        sync_pending in names and receipt_name in names and same_inode(sync_pending, receipt_name)
    )
    linked_rollback_pending = (
        rollback_record_pending in names and rollback_name in names
        and same_inode(rollback_record_pending, rollback_name)
    )
    if sync_pending in names and receipt_name in names and not linked_sync_pending:
        errors.append("sync receipt pending file is not the published record hard link")
    if rollback_record_pending in names and rollback_name in names and not linked_rollback_pending:
        errors.append("rollback receipt pending file is not the published record hard link")
    if activation_pending in names:
        errors.append("activation intent publication was interrupted")
    if "rollback.partial" in names:
        errors.append("rollback replacement was interrupted")
    if rollback_record_pending in names and rollback_name not in names:
        errors.append("rollback receipt publication was interrupted")
    normalized_names = names - {
        name for name, linked in (
            (sync_pending, linked_sync_pending),
            (rollback_record_pending, linked_rollback_pending),
        ) if linked
    }
    activation_artifacts = {"baseline.html", "candidate.html", intent_name}
    stage = artifacts.get("candidate.partial")
    exact_stage = isinstance(stage, dict) and stage.get("sha256") == candidate
    if errors:
        state = "ambiguous-manual-recovery"
    elif (
        rollback and intent and backups and active_state == "baseline"
        and normalized_names == (
            activation_artifacts | {rollback_name}
            | ({receipt_name} if recovery_source == "sync-receipt" else {sync_pending} & names)
        )
    ):
        state = "rolled-back-receipt-present"
    elif (
        receipt and intent and backups and active_state == "candidate"
        and normalized_names == activation_artifacts | {receipt_name}
    ):
        state = "activated-receipt-present"
    elif (
        intent and backups and not receipt and not rollback and active_state == "candidate"
        and normalized_names in (activation_artifacts, activation_artifacts | {sync_pending})
    ):
        state = "active-candidate-receipt-missing"
    elif (
        intent and backups and not receipt and not rollback and active_state == "baseline"
        and normalized_names in (
            activation_artifacts, activation_artifacts | {"candidate.partial"},
        )
    ):
        state = "active-baseline-with-intent"
    elif exact_stage and len(artifacts) == 1 and active_state == "baseline":
        state = "prepared-exact-stage"
    elif not artifacts and active_state == "baseline":
        state = "prepared-no-stage"
    else:
        state = "ambiguous-manual-recovery"
    result["transaction_state"] = state
    if errors:
        result["validation_errors"] = errors
    pending = sorted(name for name in artifacts if name.startswith("."))
    if pending:
        result["pending_record_writes"] = pending
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-dir", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.remote_dir, args.baseline_sha256, args.candidate_sha256)
    except (InspectError, OSError, ValueError) as exc:
        print(f"ERROR: systems sidecar inspection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
