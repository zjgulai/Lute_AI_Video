#!/usr/bin/env python3
"""Remote fail-closed state machine for the Lighthouse systems.html sidecar."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn

SHA256_RE = re.compile(r"[0-9a-f]{64}")
STATE_DIR_NAME, SIDECAR_NAME = ".landing-sidecar-sync", "systems.html"
SYNC_RECEIPT_NAME = "sync-receipt.v1.json"
ROLLBACK_RECEIPT_NAME = "rollback-receipt.v1.json"
ACTIVATION_INTENT_NAME = "activation-intent.v1.json"


class GateError(RuntimeError):
    """Expected fail-closed validation error."""
def _fail(message: str) -> NoReturn:
    raise GateError(message)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
def _require_sha256(name: str, value: str) -> None:
    if SHA256_RE.fullmatch(value) is None:
        _fail(f"{name} must be 64 lowercase hex")
def _require_real_directory(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail(f"required directory is missing: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required path is not a real directory: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode is not None and mode != exact_mode:
        _fail(f"directory mode must be {exact_mode:04o}: {path}")
    if exact_mode is None and mode & 0o022:
        _fail(f"directory must not be group/world writable: {path}")
    return info

def _require_owned_directory(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    info = _require_real_directory(path, exact_mode=exact_mode)
    if info.st_uid != os.geteuid():
        _fail(f"directory is not owned by the remote SSH user: {path}")
    return info

def _require_owned_regular(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail(f"required file is missing: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"required path is not a real regular file: {path}")
    if info.st_uid != os.geteuid():
        _fail(f"file is not owned by the remote SSH user: {path}")
    if info.st_nlink < 1:
        _fail(f"file has invalid link count: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode is not None and mode != exact_mode:
        _fail(f"file mode must be {exact_mode:04o}: {path}")
    if exact_mode is None and mode & 0o022:
        _fail(f"file must not be group/world writable: {path}")
    return info

def _create_secure_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        _fail(f"transaction path already exists; read back state before retry: {path}")
    _require_owned_directory(path, exact_mode=0o700)
    _fsync_dir(path.parent)

def _ensure_state_parent(path: Path) -> None:
    if path.exists():
        _require_owned_directory(path, exact_mode=0o700)
        return
    path.mkdir(mode=0o700)
    _require_owned_directory(path, exact_mode=0o700)
    _fsync_dir(path.parent)

def _write_json_create_only(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    try:
        os.link(temporary, path, follow_symlinks=False)
        _fsync_dir(path.parent)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()
            _fsync_dir(path.parent)

def _read_json_regular(path: Path) -> dict[str, Any]:
    _require_owned_regular(path, exact_mode=0o600)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"receipt is unreadable or invalid JSON: {path}: {exc}")
    if not isinstance(payload, dict):
        _fail(f"receipt root must be an object: {path}")
    return payload

def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017

def _run_nginx_check() -> None:
    try:
        result = subprocess.run(
            ["docker", "exec", "ai_video_nginx", "nginx", "-t"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False, timeout=15,
        )
    except subprocess.TimeoutExpired:
        _fail("remote nginx configuration check timed out")
    if result.returncode != 0:
        _fail("remote nginx configuration check failed")

@contextlib.contextmanager
def _exclusive_lock(product_root: Path) -> Iterator[None]:
    lock_path = product_root / ".systems-sync.lock"
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
        created = True
    except FileExistsError:
        fd = os.open(lock_path, os.O_RDWR | nofollow)
    try:
        if created:
            os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            _fail("systems sync lock identity is unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail("another systems sync transaction holds the lock")
        yield
    finally:
        os.close(fd)

def _copy_create_only(source: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o600)
    try:
        with source.open("rb") as reader, os.fdopen(fd, "wb", closefd=False) as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        os.fchmod(fd, 0o644)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(destination.parent)

def _verify_and_fsync_candidate(path: Path, expected_sha256: str) -> os.stat_result:
    expected = _require_owned_regular(path, exact_mode=0o644)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino) or info.st_nlink != 1:
            _fail("staged candidate identity is unsafe")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            _fail("staged candidate SHA mismatch")
        os.fsync(fd)
    finally:
        os.close(fd)
    current = path.lstat()
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        _fail("staged candidate identity changed during verification")
    return expected

class SystemsTransaction:
    def __init__(self, remote_dir: str, baseline_sha256: str, candidate_sha256: str) -> None:
        _require_sha256("BASELINE_SYSTEMS_SHA256", baseline_sha256)
        _require_sha256("CANDIDATE_SYSTEMS_SHA256", candidate_sha256)
        if baseline_sha256 == candidate_sha256:
            _fail("baseline and candidate SHA must differ")
        raw_root = Path(remote_dir)
        if not raw_root.is_absolute():
            _fail("REMOTE_DIR must be an absolute path")
        try:
            resolved_root = raw_root.resolve(strict=True)
        except OSError as exc:
            _fail(f"REMOTE_DIR cannot be resolved: {exc}")
        if resolved_root != raw_root:
            _fail("REMOTE_DIR and its existing parents must not use symlinks")
        self.remote_root = raw_root
        self.baseline_sha256 = baseline_sha256
        self.candidate_sha256 = candidate_sha256
        self.landing_dir = raw_root / "deploy" / "lighthouse" / "landing"
        self.lighthouse_dir = raw_root / "deploy" / "lighthouse"
        self.target = self.landing_dir / SIDECAR_NAME
        self.state_root = self.lighthouse_dir / STATE_DIR_NAME
        self.product_root = self.state_root / SIDECAR_NAME
        self.transaction = self.product_root / f"{baseline_sha256}--{candidate_sha256}"
        self.stage = self.transaction / "candidate.partial"
        self.baseline_backup = self.transaction / "baseline.html"
        self.candidate_backup = self.transaction / "candidate.html"
        self.sync_receipt = self.transaction / SYNC_RECEIPT_NAME
        self.rollback_receipt = self.transaction / ROLLBACK_RECEIPT_NAME
        self.activation_intent = self.transaction / ACTIVATION_INTENT_NAME
        self.rollback_stage = self.transaction / "rollback.partial"
        _require_real_directory(self.remote_root)
        _require_owned_directory(self.lighthouse_dir)
        _require_owned_directory(self.landing_dir)
        _require_owned_regular(self.target, exact_mode=0o644)

    def _require_active(self, expected_sha256: str, error: str) -> None:
        _require_owned_regular(self.target, exact_mode=0o644)
        if _sha256(self.target) != expected_sha256:
            _fail(error)

    def _base_record(self) -> dict[str, Any]:
        return {
            "scope": "systems-only", "baseline_sha256": self.baseline_sha256,
            "candidate_sha256": self.candidate_sha256, "target_path": str(self.target),
            "backup_path": str(self.baseline_backup),
            "candidate_backup_path": str(self.candidate_backup),
        }

    def _require_record(self, path: Path, expected: dict[str, Any], timestamp: str) -> dict[str, Any]:
        payload = _read_json_regular(path)
        if set(payload) != {*expected, timestamp}:
            _fail(f"record fields mismatch: {path}")
        for key, value in expected.items():
            if payload.get(key) != value:
                _fail(f"record field mismatch: {key}")
        value = payload.get(timestamp)
        if not isinstance(value, str):
            _fail(f"record UTC timestamp is invalid: {timestamp}")
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            _fail(f"record UTC timestamp is invalid: {timestamp}")
        if not value.endswith("Z") or parsed.utcoffset() != dt.timedelta(0):
            _fail(f"record UTC timestamp is invalid: {timestamp}")
        return payload

    def _require_sync_receipt(self) -> dict[str, Any]:
        expected = {**self._base_record(), "schema": "lighthouse-systems-sync-receipt.v1",
                    "status": "activated", "backup_sha256": self.baseline_sha256,
                    "post_sha256": self.candidate_sha256}
        return self._require_record(self.sync_receipt, expected, "activated_at_utc")

    def _require_activation_intent(self) -> dict[str, Any]:
        expected = {**self._base_record(), "schema": "lighthouse-systems-activation-intent.v1",
                    "status": "activation-authorized"}
        return self._require_record(self.activation_intent, expected, "authorized_at_utc")

    def _require_recovery_record(self) -> str:
        self._require_activation_intent()
        if os.path.lexists(self.sync_receipt):
            self._require_sync_receipt()
            return "sync-receipt"
        return "activation-intent"

    def _require_backups(self, prefix: str) -> None:
        _require_owned_regular(self.baseline_backup, exact_mode=0o644)
        _require_owned_regular(self.candidate_backup, exact_mode=0o644)
        if _sha256(self.baseline_backup) != self.baseline_sha256:
            _fail(f"{prefix} baseline backup SHA mismatch")
        if _sha256(self.candidate_backup) != self.candidate_sha256:
            _fail(f"{prefix} candidate backup SHA mismatch")

    def check(self) -> None:
        self._require_active(
            self.baseline_sha256,
            "remote systems.html baseline SHA mismatch",
        )
        _run_nginx_check()
        self._print("preflight-ok", active_sha256=self.baseline_sha256)

    def prepare(self) -> None:
        _ensure_state_parent(self.state_root)
        _ensure_state_parent(self.product_root)
        with _exclusive_lock(self.product_root):
            self._require_active(
                self.baseline_sha256,
                "remote systems.html baseline SHA mismatch",
            )
            _create_secure_directory(self.transaction)
        self._print("prepared", stage_path=str(self.stage))

    def activate(self) -> None:
        _require_owned_directory(self.state_root, exact_mode=0o700)
        _require_owned_directory(self.product_root, exact_mode=0o700)
        _require_owned_directory(self.transaction, exact_mode=0o700)
        stage_info = _verify_and_fsync_candidate(self.stage, self.candidate_sha256)
        if stage_info.st_dev != self.target.stat().st_dev:
            _fail("staged candidate is not on the active file filesystem")
        with _exclusive_lock(self.product_root):
            self._require_active(
                self.baseline_sha256,
                "active systems.html changed after preflight",
            )
            target_info = self.target.lstat()
            if target_info.st_nlink != 1:
                _fail("active systems.html must have exactly one link before activation")
            locked_stage = _verify_and_fsync_candidate(self.stage, self.candidate_sha256)
            if (locked_stage.st_dev, locked_stage.st_ino) != (stage_info.st_dev, stage_info.st_ino):
                _fail("staged candidate identity changed after preflight")
            try:
                os.link(self.target, self.baseline_backup)
            except FileExistsError:
                _fail("baseline backup already exists")
            _fsync_dir(self.transaction)
            if _sha256(self.baseline_backup) != self.baseline_sha256:
                _fail("baseline backup SHA mismatch")
            _copy_create_only(self.stage, self.candidate_backup)
            if _sha256(self.candidate_backup) != self.candidate_sha256:
                _fail("candidate backup SHA mismatch")
            _write_json_create_only(
                self.activation_intent,
                {
                    **self._base_record(), "schema": "lighthouse-systems-activation-intent.v1",
                    "status": "activation-authorized",
                    "authorized_at_utc": _utc_now(),
                },
            )
            self._require_activation_intent()
            self._require_active(
                self.baseline_sha256,
                "active systems.html changed immediately before activation",
            )
            current_target = self.target.lstat()
            backup_info = self.baseline_backup.lstat()
            if (current_target.st_dev, current_target.st_ino) != (backup_info.st_dev, backup_info.st_ino):
                _fail("active systems.html identity changed immediately before activation")
            final_stage = _verify_and_fsync_candidate(self.stage, self.candidate_sha256)
            if (final_stage.st_dev, final_stage.st_ino) != (locked_stage.st_dev, locked_stage.st_ino):
                _fail("staged candidate identity changed immediately before activation")
            os.replace(self.stage, self.target)
            _fsync_dir(self.landing_dir)
            self._require_active(
                self.candidate_sha256,
                "post-activation systems.html SHA mismatch",
            )
            try:
                _write_json_create_only(
                    self.sync_receipt,
                    {
                        **self._base_record(), "schema": "lighthouse-systems-sync-receipt.v1",
                        "status": "activated",
                        "backup_sha256": self.baseline_sha256,
                        "post_sha256": self.candidate_sha256,
                        "activated_at_utc": _utc_now(),
                    },
                )
            except OSError as receipt_error:
                try:
                    _copy_create_only(self.baseline_backup, self.rollback_stage)
                    os.replace(self.rollback_stage, self.target)
                    _fsync_dir(self.landing_dir)
                    self._require_active(self.baseline_sha256, "receipt-failure compensation SHA mismatch")
                except OSError as rollback_error:
                    _fail(f"receipt commit failed and compensation failed: {receipt_error}; {rollback_error}")
                _fail(f"activation receipt commit failed; active baseline restored: {receipt_error}")
        self._print("activated", post_sha256=self.candidate_sha256)

    def readback(self) -> None:
        self._require_active(
            self.candidate_sha256,
            "post-activation systems.html SHA mismatch",
        )
        self._require_backups("readback")
        self._require_sync_receipt()
        _run_nginx_check()
        self._print("readback-ok", post_sha256=self.candidate_sha256)

    def rollback_check(self) -> None:
        self._require_active(
            self.candidate_sha256,
            "active systems.html no longer matches the candidate SHA",
        )
        self._require_backups("rollback")
        self._require_recovery_record()
        _run_nginx_check()
        self._print("rollback-preflight-ok", active_sha256=self.candidate_sha256)

    def rollback(self) -> None:
        _require_owned_directory(self.state_root, exact_mode=0o700)
        _require_owned_directory(self.product_root, exact_mode=0o700)
        _require_owned_directory(self.transaction, exact_mode=0o700)
        with _exclusive_lock(self.product_root):
            self._require_active(
                self.candidate_sha256,
                "active systems.html no longer matches the candidate SHA",
            )
            recovery_source = self._require_recovery_record()
            self._require_backups("rollback")
            _copy_create_only(self.baseline_backup, self.rollback_stage)
            if self.rollback_stage.stat().st_dev != self.target.stat().st_dev:
                _fail("rollback candidate is not on the active file filesystem")
            if _sha256(self.rollback_stage) != self.baseline_sha256:
                _fail("rollback candidate SHA mismatch")
            os.replace(self.rollback_stage, self.target)
            _fsync_dir(self.landing_dir)
            self._require_active(
                self.baseline_sha256,
                "post-rollback systems.html SHA mismatch",
            )
            _write_json_create_only(
                self.rollback_receipt,
                {
                    **self._base_record(), "schema": "lighthouse-systems-rollback-receipt.v1",
                    "status": "rolled_back",
                    "pre_rollback_sha256": self.candidate_sha256,
                    "post_sha256": self.baseline_sha256,
                    "recovery_source": recovery_source,
                    "rolled_back_at_utc": _utc_now(),
                },
            )
        self._print("rolled-back", post_sha256=self.baseline_sha256)

    def rollback_readback(self) -> None:
        self._require_active(
            self.baseline_sha256,
            "post-rollback systems.html SHA mismatch",
        )
        source = _read_json_regular(self.rollback_receipt).get("recovery_source")
        if source not in {"sync-receipt", "activation-intent"}:
            _fail("rollback receipt recovery source is invalid")
        expected = {**self._base_record(), "schema": "lighthouse-systems-rollback-receipt.v1",
                    "status": "rolled_back", "pre_rollback_sha256": self.candidate_sha256,
                    "post_sha256": self.baseline_sha256,
                    "recovery_source": source}
        self._require_record(self.rollback_receipt, expected, "rolled_back_at_utc")
        _run_nginx_check()
        self._print("rollback-readback-ok", post_sha256=self.baseline_sha256)

    def _print(self, status: str, **fields: str) -> None:
        print(json.dumps({"status": status, **fields}, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    modes = ("check", "prepare", "activate", "readback", "rollback-check", "rollback", "rollback-readback")
    parser.add_argument("--mode", required=True, choices=modes)
    parser.add_argument("--remote-dir", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        transaction = SystemsTransaction(args.remote_dir, args.baseline_sha256, args.candidate_sha256)
        method_name = args.mode.replace("-", "_")
        getattr(transaction, method_name)()
    except GateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: systems sidecar transaction failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
