#!/usr/bin/env python3
"""Restricted COS release staging gate for Tencent Lighthouse.

The forced-command staging role can only probe, stage, read a receipt, or
remove its own verified incoming transaction.  Promotion is a separate
production-only command and never invokes Docker, migration, backup, cron,
nginx, provider, publish, or delivery operations.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import http.client
import importlib.util
import json
import os
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

_contract_path = Path(__file__).resolve().with_name("release_transfer.py")
if _contract_path.is_file() and not _contract_path.is_symlink():
    _contract_spec = importlib.util.spec_from_file_location(
        "_ai_video_release_transfer_contract",
        _contract_path,
    )
    if _contract_spec is None or _contract_spec.loader is None:
        raise ImportError("installed release transfer contract is unavailable")
    _contract_module = importlib.util.module_from_spec(_contract_spec)
    sys.modules[_contract_spec.name] = _contract_module
    _contract_spec.loader.exec_module(_contract_module)
    MAX_MANIFEST_BYTES = _contract_module.MAX_MANIFEST_BYTES
    PROBE_SIZE_BYTES = _contract_module.PROBE_SIZE_BYTES
    SIGNED_URL_SCHEMA = _contract_module.SIGNED_URL_SCHEMA
    TransferContractError = _contract_module.TransferContractError
    build_transfer_receipt = _contract_module.build_transfer_receipt
    canonical_json_bytes = _contract_module.canonical_json_bytes
    cos_object_host = _contract_module.cos_object_host
    evaluate_probe = _contract_module.evaluate_probe
    load_canonical_manifest = _contract_module.load_canonical_manifest
    parse_json_bytes = _contract_module.parse_json_bytes
    sha256_path = _contract_module.sha256_path
    validate_transfer_receipt = _contract_module.validate_transfer_receipt
elif __package__:
    from scripts.release_transfer import (
        MAX_MANIFEST_BYTES,
        PROBE_SIZE_BYTES,
        SIGNED_URL_SCHEMA,
        TransferContractError,
        build_transfer_receipt,
        canonical_json_bytes,
        cos_object_host,
        evaluate_probe,
        load_canonical_manifest,
        parse_json_bytes,
        sha256_path,
        validate_transfer_receipt,
    )
else:
    print(
        '{"schema_version":"release-transfer-gate-terminal.v1",'
        '"status":"failed","code":"release_transfer_runtime_invalid"}',
        file=sys.stderr,
    )
    raise SystemExit(126)

STATE_FILE = ".release-transfer-state.v1.json"
RECEIPT_FILE = "release-transfer-receipt.v1.json"
MANIFEST_FILE = "release-transfer-manifest.v1.json"
MAX_URL_PAYLOAD_BYTES = 64 * 1024
MAX_SOURCE_MEMBERS = 20_000
MAX_SOURCE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_IMAGE_MEMBERS = 100_000
MAX_IMAGE_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
MAX_ARCHIVE_PATH_COMPONENTS = 64
MAX_ARCHIVE_PATH_BYTES = 4096
MAX_ARCHIVE_COMPONENT_BYTES = 255
DEFAULT_STAGING_ROOT = Path("/var/lib/ai-video-release-transfer")
DEFAULT_RELEASE_ROOT = Path("/opt/ai-video")
PROBE_SHA256 = "3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
POSITIVE_INT_RE = re.compile(r"^[1-9][0-9]{0,19}$")


class GateError(RuntimeError):
    """A restricted release-transfer operation failed closed."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


@dataclass(frozen=True)
class GateIdentity:
    source_revision: str
    workflow_run_id: int
    workflow_run_attempt: int
    manifest_sha256: str

    @property
    def incoming_directory(self) -> str:
        return (
            f".incoming-{self.source_revision}-{self.workflow_run_id}-"
            f"{self.workflow_run_attempt}"
        )

    @property
    def final_directory(self) -> str:
        return f"releases-{self.source_revision}"

    @property
    def probe_file(self) -> str:
        return (
            f".release-transfer-probe-{self.source_revision}-"
            f"{self.workflow_run_id}-{self.workflow_run_attempt}.json"
        )


@dataclass(frozen=True)
class GateCommand:
    action: str
    identity: GateIdentity


@dataclass
class _PathMutationIntent:
    attempted: bool = False
    created: bool = False
    device: int | None = None
    inode: int | None = None
    cleanup_failed: bool = False


def _exact_dict(payload: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != keys:
        raise GateError(f"{label} fields are invalid")
    return payload


def _deadline_from_remaining(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > 1_800
    ):
        raise GateError("release transfer deadline is invalid")
    return time.monotonic_ns() + value * 1_000_000_000


def _remaining_timeout(deadline_ns: int, maximum_seconds: int) -> float:
    remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
    if remaining <= 0:
        raise GateError("release transfer deadline exceeded")
    return max(0.001, min(float(maximum_seconds), remaining))


@contextlib.contextmanager
def _deadline_alarm(deadline_ns: int):
    remaining = _remaining_timeout(deadline_ns, 1_800)
    if not hasattr(signal, "setitimer"):
        yield
        _remaining_timeout(deadline_ns, 1_800)
        return

    def deadline_reached(_signum, _frame):
        raise GateError("release transfer deadline exceeded")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, deadline_reached)
    started = time.monotonic()
    previous_timer = signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            elapsed = time.monotonic() - started
            restored = max(0.000001, previous_timer[0] - elapsed)
            signal.setitimer(signal.ITIMER_REAL, restored, previous_timer[1])


@contextlib.contextmanager
def _controlled_signals():
    handled = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    previous = {item: signal.getsignal(item) for item in handled}

    def interrupted(_signum, _frame):
        raise GateError("release transfer interrupted")

    for item in handled:
        signal.signal(item, interrupted)
    try:
        yield
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


@contextlib.contextmanager
def _blocked_transaction_signals():
    """Delay handled signals until an ownership intent records the new inode."""

    if not hasattr(signal, "pthread_sigmask"):
        yield
        return
    blocked = {signal.SIGHUP, signal.SIGINT, signal.SIGTERM}
    if hasattr(signal, "SIGALRM"):
        blocked.add(signal.SIGALRM)
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _record_created_path(intent: _PathMutationIntent, facts: os.stat_result) -> None:
    intent.created = True
    intent.device = facts.st_dev
    intent.inode = facts.st_ino


def _matches_created_path(
    path: Path,
    intent: _PathMutationIntent,
    *,
    directory: bool,
) -> bool:
    if not intent.created or intent.device is None or intent.inode is None:
        return False
    try:
        facts = path.lstat()
    except OSError:
        return False
    expected_kind = stat.S_ISDIR(facts.st_mode) if directory else stat.S_ISREG(facts.st_mode)
    return (
        expected_kind
        and not path.is_symlink()
        and facts.st_uid == os.geteuid()
        and facts.st_dev == intent.device
        and facts.st_ino == intent.inode
        and (directory or facts.st_nlink == 1)
    )


def _unlink_owned_file(
    path: Path,
    intent: _PathMutationIntent,
    *,
    label: str,
    expected_bytes: bytes | None = None,
) -> None:
    if not path.exists() and not path.is_symlink():
        return
    isolated = _quarantine_owned_path(
        path,
        intent,
        directory=False,
        label=label,
    )
    try:
        if (
            not _matches_created_path(isolated, intent, directory=False)
            or (
                expected_bytes is not None
                and isolated.read_bytes() != expected_bytes
            )
        ):
            _restore_quarantined_path(
                isolated,
                path,
                label=label,
            )
        isolated.unlink()
    except (OSError, GateError, KeyboardInterrupt, SystemExit) as exc:
        intent.cleanup_failed = True
        raise GateError(f"{label} cleanup requires manual recovery") from exc


def _quarantine_owned_path(
    path: Path,
    intent: _PathMutationIntent,
    *,
    directory: bool,
    label: str,
) -> Path:
    for _ in range(4):
        isolated = path.parent / f".release-cleanup-{secrets.token_hex(16)}"
        try:
            _rename_noreplace(path, isolated)
        except (GateError, KeyboardInterrupt, SystemExit) as exc:
            if _matches_created_path(isolated, intent, directory=directory):
                if isinstance(exc, GateError):
                    return isolated
                raise GateError(f"{label} cleanup requires manual recovery") from exc
            if isolated.exists() or isolated.is_symlink():
                continue
            raise GateError(f"{label} cleanup requires manual recovery") from exc
        return isolated
    raise GateError(f"{label} cleanup requires manual recovery")


def _restore_quarantined_path(
    isolated: Path,
    original: Path,
    *,
    label: str,
) -> None:
    try:
        _rename_noreplace(isolated, original)
    except (OSError, GateError, KeyboardInterrupt, SystemExit) as exc:
        raise GateError(f"{label} cleanup requires manual recovery") from exc
    raise GateError(f"{label} cleanup requires manual recovery")


def _remove_owned_directory(
    path: Path,
    intent: _PathMutationIntent,
    *,
    label: str,
    validator: Callable[[Path], bool],
) -> None:
    if not path.exists() and not path.is_symlink():
        return
    isolated = _quarantine_owned_path(
        path,
        intent,
        directory=True,
        label=label,
    )
    try:
        owned = _matches_created_path(isolated, intent, directory=True)
        valid = owned and validator(isolated)
    except (OSError, GateError, KeyboardInterrupt, SystemExit):
        valid = False
    if not valid:
        _restore_quarantined_path(
            isolated,
            path,
            label=label,
        )
    try:
        if any(isolated.iterdir()):
            _remove_tree_fd(isolated)
        else:
            isolated.rmdir()
    except (OSError, GateError, KeyboardInterrupt, SystemExit) as exc:
        raise GateError(f"{label} cleanup requires manual recovery") from exc


def parse_forced_command(command: str, *, role: str) -> GateCommand:
    parts = command.split(" ")
    if len(parts) != 5 or any(not part for part in parts):
        raise GateError("release transfer command is invalid")
    action, source_revision, raw_run_id, raw_attempt, manifest_sha = parts
    allowed = {
        "staging": {"probe", "stage", "receipt", "cleanup"},
        "production": {"promote"},
    }
    if role not in allowed or action not in allowed[role]:
        raise GateError("release transfer command is not authorized")
    if not GIT_SHA_RE.fullmatch(source_revision):
        raise GateError("release transfer source revision is invalid")
    if not POSITIVE_INT_RE.fullmatch(raw_run_id) or not POSITIVE_INT_RE.fullmatch(
        raw_attempt
    ):
        raise GateError("release transfer workflow identity is invalid")
    if not SHA256_RE.fullmatch(manifest_sha):
        raise GateError("release transfer manifest checksum is invalid")
    identity = GateIdentity(
        source_revision=source_revision,
        workflow_run_id=int(raw_run_id),
        workflow_run_attempt=int(raw_attempt),
        manifest_sha256=manifest_sha,
    )
    return GateCommand(action=action, identity=identity)


def _path_under(root: Path, name: str) -> Path:
    if not name or PurePosixPath(name).name != name or "/" in name or "\x00" in name:
        raise GateError("release transfer path is invalid")
    if root.is_symlink() or not root.is_dir():
        raise GateError("release transfer root is missing or unsafe")
    path = root / name
    try:
        if path.parent.resolve(strict=True) != root.resolve(strict=True):
            raise GateError("release transfer path escapes the root")
    except OSError as exc:
        raise GateError("release transfer root is missing or unsafe") from exc
    return path


def _assert_secure_staging_root(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise GateError("release transfer staging root is missing or unsafe")
    try:
        facts = root.stat()
    except OSError as exc:
        raise GateError("release transfer staging root is missing or unsafe") from exc
    if facts.st_uid != os.geteuid() or facts.st_mode & 0o777 != 0o700:
        raise GateError("release transfer staging root ownership or mode is unsafe")


def _assert_secure_release_root(
    root: Path,
    *,
    allow_private_staging_mode: bool = False,
) -> tuple[int, int]:
    if root.is_symlink() or not root.is_dir():
        raise GateError("release transfer release root is missing or unsafe")
    try:
        facts = root.stat()
    except OSError as exc:
        raise GateError("release transfer release root is missing or unsafe") from exc
    allowed_modes = {0o755}
    if allow_private_staging_mode:
        allowed_modes.add(0o700)
    if (
        facts.st_uid != os.geteuid()
        or facts.st_gid != os.getegid()
        or facts.st_mode & 0o777 not in allowed_modes
    ):
        raise GateError("release transfer release root ownership or mode is unsafe")
    return facts.st_dev, facts.st_ino


def _assert_owned_transaction_tree(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise GateError("release transfer transaction is unsafe")
    expected_uid = os.geteuid()
    try:
        expected_device = directory.stat().st_dev
    except (OSError, RecursionError) as exc:
        raise GateError("release transfer transaction ownership is unsafe") from exc
    try:
        paths = (directory, *directory.rglob("*"))
    except (OSError, RecursionError) as exc:
        raise GateError("release transfer transaction ownership is unsafe") from exc
    for path in paths:
        try:
            facts = path.lstat()
        except OSError as exc:
            raise GateError("release transfer transaction ownership is unsafe") from exc
        if facts.st_uid != expected_uid:
            raise GateError("release transfer transaction ownership is unsafe")
        if facts.st_dev != expected_device:
            raise GateError("release transfer transaction crosses a filesystem")
        if path.is_file() and not path.is_symlink() and facts.st_nlink != 1:
            raise GateError("release transfer transaction hard link is unsafe")
    _assert_no_mount_boundaries(directory)


def _decode_mount_path(value: str) -> str:
    for encoded, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(encoded, decoded)
    return value


def _assert_no_mount_boundaries(directory: Path) -> None:
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        if platform.system() == "Linux":
            raise GateError("release transfer mount state is unavailable")
        return
    try:
        root = os.path.realpath(directory)
        prefix = root + os.sep
        for line in mountinfo.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 6:
                raise GateError("release transfer mount state is invalid")
            mount_path = os.path.realpath(_decode_mount_path(fields[4]))
            if mount_path == root or mount_path.startswith(prefix):
                raise GateError("release transfer transaction contains a mount boundary")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError("release transfer mount state is unavailable") from exc


def _remove_tree_fd(directory: Path) -> None:
    """Delete one validated transaction without following directory symlinks."""

    _assert_owned_transaction_tree(directory)
    parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_fd = os.open(
            directory.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )

        def remove_contents(descriptor: int) -> None:
            for name in os.listdir(descriptor):
                facts = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISDIR(facts.st_mode):
                    child_fd = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                    try:
                        remove_contents(child_fd)
                    finally:
                        os.close(child_fd)
                    os.rmdir(name, dir_fd=descriptor)
                else:
                    os.unlink(name, dir_fd=descriptor)

        try:
            _assert_no_mount_boundaries(directory)
            remove_contents(root_fd)
        finally:
            os.close(root_fd)
        os.rmdir(directory.name, dir_fd=parent_fd)
    except (OSError, RecursionError) as exc:
        raise GateError("release transfer transaction deletion failed") from exc
    finally:
        os.close(parent_fd)


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    exclusive: bool,
    intent: _PathMutationIntent | None = None,
) -> None:
    if path.is_symlink():
        raise GateError("release transfer output is unsafe")
    if exclusive:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor: int | None = None
        stream = None
        active_intent = intent if intent is not None else _PathMutationIntent()
        active_intent.attempted = True
        try:
            with _blocked_transaction_signals():
                descriptor = os.open(path, flags, 0o600)
                facts = os.fstat(descriptor)
                _record_created_path(active_intent, facts)
                stream = os.fdopen(descriptor, "wb")
                descriptor = None
            with stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, GateError, KeyboardInterrupt, SystemExit) as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
            if active_intent.created:
                try:
                    _unlink_owned_file(
                        path,
                        active_intent,
                        label="release transfer output",
                    )
                except GateError as cleanup_exc:
                    active_intent.cleanup_failed = True
                    raise GateError(
                        "release transfer output cleanup requires manual recovery"
                    ) from cleanup_exc
            if isinstance(exc, (GateError, KeyboardInterrupt, SystemExit)):
                raise
            raise GateError("release transfer output already exists or is unsafe") from exc
        return
    temporary: Path | None = None
    temporary_intent = _PathMutationIntent(attempted=True)
    descriptor: int | None = None
    stream = None
    committed = False
    try:
        with _blocked_transaction_signals():
            descriptor, raw_temporary = tempfile.mkstemp(
                prefix=f".{path.name}.",
                dir=path.parent,
            )
            temporary = Path(raw_temporary)
            _record_created_path(temporary_intent, os.fstat(descriptor))
            os.fchmod(descriptor, 0o600)
            stream = os.fdopen(descriptor, "wb")
            descriptor = None
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        committed = True
    except (OSError, GateError, KeyboardInterrupt, SystemExit) as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if stream is not None and not stream.closed:
            try:
                stream.close()
            except OSError:
                pass
        if temporary is not None and not committed and temporary_intent.created:
            try:
                _unlink_owned_file(
                    temporary,
                    temporary_intent,
                    label="release transfer state temporary output",
                )
            except GateError as cleanup_exc:
                raise GateError(
                    "release transfer state cleanup requires manual recovery"
                ) from cleanup_exc
        if isinstance(exc, GateError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise GateError("release transfer state update was interrupted") from exc
        raise GateError("release transfer state update failed") from exc


def _state_payload(identity: GateIdentity, state: str) -> dict[str, object]:
    if state not in {"downloading", "verified", "promoted"}:
        raise GateError("release transfer state is invalid")
    return {
        "schema_version": "release-transfer-state.v1",
        "state": state,
        "source_revision": identity.source_revision,
        "workflow_run_id": identity.workflow_run_id,
        "workflow_run_attempt": identity.workflow_run_attempt,
        "manifest_sha256": identity.manifest_sha256,
    }


def write_state_marker(directory: Path, identity: GateIdentity, state: str) -> Path:
    if directory.is_symlink() or not directory.is_dir():
        raise GateError("release transfer incoming directory is unsafe")
    marker = directory / STATE_FILE
    _atomic_write(marker, canonical_json_bytes(_state_payload(identity, state)), exclusive=True)
    return marker


def _replace_state_marker(directory: Path, identity: GateIdentity, state: str) -> None:
    _load_state_marker(directory, identity)
    _atomic_write(
        directory / STATE_FILE,
        canonical_json_bytes(_state_payload(identity, state)),
        exclusive=False,
    )


def _load_json_file(path: Path, *, maximum_bytes: int, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise GateError(f"{label} is missing or unsafe")
    try:
        raw = path.read_bytes()
        if len(raw) > maximum_bytes:
            raise GateError(f"{label} exceeds its size limit")
        return parse_json_bytes(raw, label=label)
    except (OSError, TransferContractError) as exc:
        raise GateError(f"{label} is not valid JSON") from exc


def _load_state_marker(directory: Path, identity: GateIdentity) -> dict[str, object]:
    payload = _exact_dict(
        _load_json_file(directory / STATE_FILE, maximum_bytes=4096, label="state marker"),
        {
            "schema_version",
            "state",
            "source_revision",
            "workflow_run_id",
            "workflow_run_attempt",
            "manifest_sha256",
        },
        "state marker",
    )
    expected = _state_payload(identity, cast(str, payload["state"]))
    if payload != expected:
        raise GateError("release transfer state marker identity is invalid")
    if (directory / STATE_FILE).read_bytes() != canonical_json_bytes(payload):
        raise GateError("release transfer state marker is not canonical")
    return payload


def _safe_member_path(raw: object) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise GateError("archive member path is unsafe")
    normalized = raw[:-1] if raw.endswith("/") else raw
    path = PurePosixPath(normalized)
    try:
        normalized_bytes = normalized.encode("utf-8")
        component_bytes = [part.encode("utf-8") for part in path.parts]
    except UnicodeEncodeError as exc:
        raise GateError("archive member path is unsafe") from exc
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != normalized
        or any(part in {"", "."} for part in path.parts)
        or len(path.parts) > MAX_ARCHIVE_PATH_COMPONENTS
        or len(normalized_bytes) > MAX_ARCHIVE_PATH_BYTES
        or any(len(part) > MAX_ARCHIVE_COMPONENT_BYTES for part in component_bytes)
    ):
        raise GateError("archive member path is unsafe")
    return path


def _symlink_target_path(member_path: PurePosixPath, raw_target: str) -> str:
    target = PurePosixPath(raw_target)
    try:
        target_bytes = raw_target.encode("utf-8")
        component_bytes = [part.encode("utf-8") for part in target.parts]
    except UnicodeEncodeError as exc:
        raise GateError("archive symlink target is unsafe") from exc
    if (
        not raw_target
        or target.is_absolute()
        or ".." in target.parts
        or target.as_posix() != raw_target
        or any(part in {"", "."} for part in target.parts)
        or len(target.parts) > MAX_ARCHIVE_PATH_COMPONENTS
        or len(target_bytes) > MAX_ARCHIVE_PATH_BYTES
        or any(len(part) > MAX_ARCHIVE_COMPONENT_BYTES for part in component_bytes)
    ):
        raise GateError("archive symlink target is unsafe")
    resolved = member_path.parent / target
    if ".." in resolved.parts:
        raise GateError("archive symlink target is unsafe")
    return resolved.as_posix()


def _canonical_source_member_mode(member: tarfile.TarInfo) -> int | None:
    forbidden = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | stat.S_IWOTH
    if member.mode & forbidden:
        raise GateError("source archive member mode is unsafe")
    if member.isdir():
        return 0o755
    if member.isreg():
        return 0o755 if member.mode & 0o111 else 0o644
    if member.issym():
        return None
    raise GateError("source archive contains an unsafe member type")


def _source_mode_contract(
    archive_path: Path,
) -> tuple[dict[str, int | None], set[str]]:
    modes: dict[str, int | None] = {}
    directories: set[str] = {"."}
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                relative = _safe_member_path(member.name)
                name = relative.as_posix()
                mode = _canonical_source_member_mode(member)
                if member.isdir():
                    directories.add(name)
                else:
                    modes[name] = mode
                parent = relative.parent
                while parent.as_posix() != ".":
                    directories.add(parent.as_posix())
                    parent = parent.parent
    except (OSError, RecursionError, tarfile.TarError) as exc:
        raise GateError("source archive mode contract is invalid") from exc
    return modes, directories


def _verify_source_tree_modes(
    source_root: Path,
    archive_path: Path,
    *,
    verify_root: bool = True,
) -> None:
    modes, directories = _source_mode_contract(archive_path)
    try:
        for relative, expected_mode in modes.items():
            path = source_root / relative
            facts = path.lstat()
            if expected_mode is None:
                if not stat.S_ISLNK(facts.st_mode):
                    raise GateError("source symlink mode contract is invalid")
            elif not stat.S_ISREG(facts.st_mode) or stat.S_IMODE(facts.st_mode) != expected_mode:
                raise GateError("source file mode contract is invalid")
        for relative in directories:
            if relative == "." and not verify_root:
                continue
            path = source_root if relative == "." else source_root / relative
            facts = path.lstat()
            if not stat.S_ISDIR(facts.st_mode) or stat.S_IMODE(facts.st_mode) != 0o755:
                raise GateError("source directory mode contract is invalid")
    except (OSError, RecursionError) as exc:
        raise GateError("source mode verification failed") from exc


def safe_extract_source_archive(
    archive_path: Path,
    destination: Path,
    *,
    declared_entries: dict[str, tuple[int, str]],
) -> None:
    if destination.exists() or destination.is_symlink():
        raise GateError("source extraction destination already exists or is unsafe")
    destination.mkdir(mode=0o700)
    created: set[str] = set()
    symlinks: list[tuple[PurePosixPath, str]] = []
    extracted_bytes = 0
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_SOURCE_MEMBERS:
                raise GateError("source archive member count is invalid")
            for member in members:
                _safe_member_path(member.name)
                _canonical_source_member_mode(member)
                if member.issym():
                    _symlink_target_path(
                        _safe_member_path(member.name),
                        member.linkname,
                    )
            for member in members:
                relative = _safe_member_path(member.name)
                canonical_mode = _canonical_source_member_mode(member)
                relative_name = relative.as_posix()
                if relative_name in created:
                    raise GateError("source archive contains duplicate members")
                created.add(relative_name)
                output = destination.joinpath(*relative.parts)
                if member.isdir():
                    if not any(
                        path == relative_name or path.startswith(f"{relative_name}/")
                        for path in declared_entries
                    ):
                        raise GateError("source archive directory is not manifest-bound")
                    output.mkdir(parents=True, exist_ok=True, mode=0o755)
                    os.chmod(output, 0o755)
                    continue
                if relative_name not in declared_entries:
                    raise GateError("source archive member is not manifest-bound")
                expected_size, expected_digest = declared_entries[relative_name]
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if member.isreg():
                    assert canonical_mode is not None
                    extracted_bytes += member.size
                    if (
                        member.size != expected_size
                        or extracted_bytes > MAX_SOURCE_UNCOMPRESSED_BYTES
                    ):
                        raise GateError("source archive member size is not manifest-bound")
                    source = archive.extractfile(member)
                    if source is None:
                        raise GateError("source archive member is unreadable")
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    descriptor = os.open(output, flags, 0o600)
                    with os.fdopen(descriptor, "wb") as stream:
                        shutil.copyfileobj(source, stream, length=1024 * 1024)
                        os.fchmod(stream.fileno(), canonical_mode)
                    if (
                        output.stat().st_size != expected_size
                        or sha256_path(output) != expected_digest
                    ):
                        raise GateError("source archive member identity is inconsistent")
                elif member.issym():
                    target = _symlink_target_path(relative, member.linkname)
                    try:
                        target_bytes = member.linkname.encode("utf-8")
                    except UnicodeEncodeError as exc:
                        raise GateError("source archive symlink identity is unsafe") from exc
                    if target not in declared_entries:
                        raise GateError("source archive symlink target is not manifest-bound")
                    if (
                        len(target_bytes) != expected_size
                        or hashlib.sha256(b"symlink\0" + target_bytes).hexdigest()
                        != expected_digest
                    ):
                        raise GateError("source archive symlink identity is inconsistent")
                    symlinks.append((relative, member.linkname))
                else:
                    raise GateError("source archive contains an unsafe member type")
        for relative, target in symlinks:
            output = destination.joinpath(*relative.parts)
            if output.exists() or output.is_symlink():
                raise GateError("source archive symlink output is unsafe")
            os.symlink(target, output)
        actual = {
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if actual != set(declared_entries):
            raise GateError("source archive exact file set does not match manifest")
        for directory in (
            destination,
            *(path for path in destination.rglob("*") if path.is_dir() and not path.is_symlink()),
        ):
            os.chmod(directory, 0o755)
        _verify_source_tree_modes(destination, archive_path)
    except (OSError, RecursionError, tarfile.TarError) as exc:
        raise GateError("source archive extraction failed") from exc


def validate_image_archive(path: Path) -> dict[str, int]:
    if path.is_symlink() or not path.is_file():
        raise GateError("image archive is missing or unsafe")
    count = 0
    total = 0
    seen: set[str] = set()
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                relative = _safe_member_path(member.name).as_posix()
                if relative in seen:
                    raise GateError("image archive contains duplicate members")
                seen.add(relative)
                count += 1
                if count > MAX_IMAGE_MEMBERS:
                    raise GateError("image archive member count exceeds the limit")
                if not (member.isdir() or member.isreg()):
                    raise GateError("image archive contains an unsafe member type")
                if member.isreg():
                    total += member.size
                    if total > MAX_IMAGE_UNCOMPRESSED_BYTES:
                        raise GateError("image archive expands beyond the limit")
    except (OSError, tarfile.TarError) as exc:
        raise GateError("image archive validation failed") from exc
    if count == 0:
        raise GateError("image archive is empty")
    return {"member_count": count, "uncompressed_bytes": total}


def _source_entry_digest(path: Path) -> tuple[int, str]:
    if path.is_symlink():
        try:
            target = os.readlink(path).encode("utf-8")
        except (OSError, UnicodeEncodeError) as exc:
            raise GateError("source symlink is unsafe") from exc
        return len(target), hashlib.sha256(b"symlink\0" + target).hexdigest()
    if not path.is_file():
        raise GateError("source file is missing or unsafe")
    return path.stat().st_size, sha256_path(path)


def _validate_source_tree(source_root: Path, source_manifest_path: Path, revision: str) -> None:
    payload = _exact_dict(
        _load_json_file(
            source_manifest_path,
            maximum_bytes=16 * 1024 * 1024,
            label="source manifest",
        ),
        {"schema_version", "git_sha", "files"},
        "source manifest",
    )
    if payload["schema_version"] != "source-manifest.v1" or payload["git_sha"] != revision:
        raise GateError("source manifest identity is invalid")
    entries = payload["files"]
    if not isinstance(entries, list) or not entries:
        raise GateError("source manifest file set is invalid")
    declared: list[str] = []
    for raw in entries:
        entry = _exact_dict(raw, {"path", "size_bytes", "sha256"}, "source entry")
        relative = _safe_member_path(cast(str, entry["path"])).as_posix()
        size, digest = _source_entry_digest(source_root / relative)
        if size != entry["size_bytes"] or digest != entry["sha256"]:
            raise GateError("source file identity is invalid")
        declared.append(relative)
    if declared != sorted(declared) or len(declared) != len(set(declared)):
        raise GateError("source manifest file order is invalid")
    actual = sorted(
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    if actual != declared:
        raise GateError("source tree exact file set is invalid")


def _validate_promotable_source_tree(
    incoming: Path,
    manifest: dict[str, object],
) -> None:
    source_revision = cast(str, manifest["source_revision"])
    source_archive = incoming / f"release-source-{source_revision}.tar.gz"
    _, source_directories = _source_mode_contract(source_archive)
    source_manifest_path = incoming / "source-manifest.v1.json"
    payload = _exact_dict(
        _load_json_file(
            source_manifest_path,
            maximum_bytes=16 * 1024 * 1024,
            label="source manifest",
        ),
        {"schema_version", "git_sha", "files"},
        "source manifest",
    )
    if payload["schema_version"] != "source-manifest.v1" or payload["git_sha"] != source_revision:
        raise GateError("source manifest identity is invalid")
    raw_entries = payload["files"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise GateError("source manifest file set is invalid")
    declared: list[str] = []
    for raw_entry in raw_entries:
        entry = _exact_dict(raw_entry, {"path", "size_bytes", "sha256"}, "source entry")
        relative = _safe_member_path(cast(str, entry["path"])).as_posix()
        size, digest = _source_entry_digest(incoming / relative)
        if size != entry["size_bytes"] or digest != entry["sha256"]:
            raise GateError("source file identity is invalid")
        declared.append(relative)
    if declared != sorted(declared) or len(declared) != len(set(declared)):
        raise GateError("source manifest file order is invalid")
    evidence_files = {
        cast(str, entry["path"])
        for entry in cast(list[dict[str, object]], manifest["files"])
    }
    evidence_files.update({MANIFEST_FILE, RECEIPT_FILE, STATE_FILE})
    actual_files = {
        path.relative_to(incoming).as_posix()
        for path in incoming.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != set(declared) | evidence_files:
        raise GateError("source tree exact file set is invalid")
    actual_directories = {
        path.relative_to(incoming).as_posix()
        for path in incoming.rglob("*")
        if path.is_dir() and not path.is_symlink()
    }
    if actual_directories != source_directories - {"."}:
        raise GateError("source tree exact directory set is invalid")
    for path in incoming.rglob("*"):
        facts = path.lstat()
        if not (
            stat.S_ISREG(facts.st_mode)
            or stat.S_ISDIR(facts.st_mode)
            or stat.S_ISLNK(facts.st_mode)
        ):
            raise GateError("source tree contains an unsafe entry type")


def _validate_url(url: object, *, expected_host: str) -> str:
    if not isinstance(url, str) or len(url) > 8192 or "\n" in url or "\r" in url:
        raise GateError("signed URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise GateError("signed URL is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
        or host != expected_host
    ):
        raise GateError("signed URL is invalid")
    return url


def _download(
    url: str,
    destination: Path,
    *,
    maximum_bytes: int,
    deadline_ns: int | None = None,
    intent: _PathMutationIntent | None = None,
) -> tuple[int, int]:
    if destination.exists() or destination.is_symlink():
        raise GateError("download destination already exists or is unsafe")
    request = urllib.request.Request(url, headers={"User-Agent": "ai-video-release-gate/1"})
    started = time.monotonic_ns()
    operation_deadline = (
        started + 1_800 * 1_000_000_000 if deadline_ns is None else deadline_ns
    )
    written = 0
    descriptor: int | None = None
    output = None
    active_intent = intent if intent is not None else _PathMutationIntent()
    active_intent.attempted = True
    try:
        with _deadline_alarm(operation_deadline):
            with _blocked_transaction_signals():
                descriptor = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                _record_created_path(active_intent, os.fstat(descriptor))
                output = os.fdopen(descriptor, "wb")
                descriptor = None
            with output, _NO_REDIRECT_OPENER.open(
                request,
                timeout=_remaining_timeout(operation_deadline, 60),
            ) as response:
                if response.status != 200:
                    raise GateError("release transfer download status is invalid")
                while True:
                    _remaining_timeout(operation_deadline, 1_800)
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > maximum_bytes:
                        raise GateError("download exceeds its manifest-bound size")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
    except (
        GateError,
        OSError,
        TimeoutError,
        urllib.error.URLError,
        http.client.HTTPException,
        KeyboardInterrupt,
        SystemExit,
    ) as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if output is not None and not output.closed:
            try:
                output.close()
            except OSError:
                pass
        if active_intent.created:
            _unlink_owned_file(
                destination,
                active_intent,
                label="release transfer download",
            )
        if isinstance(exc, FileExistsError):
            raise GateError("download destination already exists or is unsafe") from exc
        if isinstance(exc, GateError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise GateError("release transfer download was interrupted") from exc
        raise GateError("release transfer download failed") from exc
    elapsed = time.monotonic_ns() - started
    return written, elapsed


def _read_stdin_json(stream: BinaryIO, *, label: str) -> dict[str, Any]:
    raw = stream.read(MAX_URL_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_URL_PAYLOAD_BYTES:
        raise GateError(f"{label} exceeds its size limit")
    try:
        return cast(dict[str, Any], parse_json_bytes(raw, label=label))
    except TransferContractError as exc:
        raise GateError(f"{label} is not valid JSON") from exc


def run_probe(root: Path, identity: GateIdentity, stream: BinaryIO) -> dict[str, object]:
    _assert_secure_staging_root(root)
    payload = _exact_dict(
        _read_stdin_json(stream, label="probe request"),
        {
            "schema_version",
            "manifest_sha256",
            "release_bytes",
            "deadline_seconds_remaining",
            "bucket",
            "endpoint_host",
            "url",
        },
        "probe request",
    )
    if payload["schema_version"] != "release-transfer-probe-url.v1":
        raise GateError("probe request schema is invalid")
    if payload["manifest_sha256"] != identity.manifest_sha256:
        raise GateError("probe request identity is invalid")
    release_bytes = payload["release_bytes"]
    if isinstance(release_bytes, bool) or not isinstance(release_bytes, int) or release_bytes <= 0:
        raise GateError("probe release size is invalid")
    deadline_ns = _deadline_from_remaining(payload["deadline_seconds_remaining"])
    bucket = payload["bucket"]
    endpoint_host = payload["endpoint_host"]
    if not isinstance(bucket, str) or not isinstance(endpoint_host, str):
        raise GateError("probe endpoint is invalid")
    try:
        expected_host = cos_object_host(bucket, endpoint_host)
    except TransferContractError as exc:
        raise GateError("probe endpoint is invalid") from exc
    url = _validate_url(payload["url"], expected_host=expected_host)
    probe_path = _path_under(root, f".probe-{identity.source_revision}-{identity.workflow_run_id}-{identity.workflow_run_attempt}.part")
    receipt_path = _path_under(root, identity.probe_file)
    if probe_path.exists() or probe_path.is_symlink():
        raise GateError("probe transaction already exists")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise GateError("probe receipt already exists")
    probe_intent = _PathMutationIntent(attempted=True)
    receipt_intent = _PathMutationIntent(attempted=True)
    receipt_bytes: bytes | None = None
    completed = False
    try:
        with _deadline_alarm(deadline_ns):
            size, elapsed = _download(
                url,
                probe_path,
                maximum_bytes=PROBE_SIZE_BYTES,
                deadline_ns=deadline_ns,
                intent=probe_intent,
            )
            if sha256_path(probe_path) != PROBE_SHA256:
                raise GateError("release transfer probe checksum is invalid")
            probe = evaluate_probe(
                transferred_bytes=size,
                elapsed_nanoseconds=elapsed,
                release_bytes=release_bytes,
            )
            probe["endpoint_host"] = endpoint_host
            probe["bucket"] = bucket
            _unlink_owned_file(
                probe_path,
                probe_intent,
                label="release transfer probe",
            )
            receipt_bytes = cast(bytes, canonical_json_bytes(probe))
            _atomic_write(
                receipt_path,
                receipt_bytes,
                exclusive=True,
                intent=receipt_intent,
            )
            _remaining_timeout(deadline_ns, 1_800)
        completed = True
        return probe
    except (GateError, KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, GateError):
            raise
        raise GateError("release transfer probe was interrupted") from exc
    except (OSError, TransferContractError) as exc:
        raise GateError("release transfer bandwidth probe failed") from exc
    finally:
        if not completed:
            cleanup_failed = False
            if probe_intent.created:
                try:
                    _unlink_owned_file(
                        probe_path,
                        probe_intent,
                        label="release transfer probe",
                    )
                except GateError:
                    cleanup_failed = True
            if receipt_intent.cleanup_failed:
                cleanup_failed = True
            elif receipt_path.exists() or receipt_path.is_symlink():
                try:
                    if (
                        receipt_bytes is None
                        or not _matches_created_path(
                        receipt_path,
                        receipt_intent,
                        directory=False,
                    )
                    ):
                        raise OSError("probe receipt ownership is ambiguous")
                    _unlink_owned_file(
                        receipt_path,
                        receipt_intent,
                        label="release transfer probe receipt",
                        expected_bytes=receipt_bytes,
                    )
                except (OSError, GateError):
                    cleanup_failed = True
            if cleanup_failed:
                raise GateError(
                    "release transfer probe cleanup requires manual recovery"
                )


def _load_probe(root: Path, identity: GateIdentity) -> dict[str, object]:
    path = _path_under(root, identity.probe_file)
    payload = _exact_dict(
        _load_json_file(path, maximum_bytes=4096, label="probe receipt"),
        {
            "status",
            "transferred_bytes",
            "elapsed_nanoseconds",
            "bytes_per_second",
            "estimated_release_seconds",
            "bucket",
            "endpoint_host",
        },
        "probe receipt",
    )
    if path.read_bytes() != canonical_json_bytes(payload) or payload["status"] != "passed":
        raise GateError("probe receipt is invalid")
    return payload


def _remove_probe_receipt(root: Path, identity: GateIdentity) -> None:
    path = _path_under(root, identity.probe_file)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_file():
        raise GateError("probe receipt cleanup requires manual recovery")
    try:
        payload = _load_probe(root, identity)
        facts = path.lstat()
    except (OSError, GateError) as exc:
        raise GateError("probe receipt cleanup requires manual recovery") from exc
    if facts.st_uid != os.geteuid() or facts.st_nlink != 1:
        raise GateError("probe receipt cleanup requires manual recovery")
    intent = _PathMutationIntent(attempted=True)
    _record_created_path(intent, facts)
    _unlink_owned_file(
        path,
        intent,
        label="probe receipt",
        expected_bytes=canonical_json_bytes(payload),
    )


def _move_source_tree(source: Path, incoming: Path) -> None:
    for child in source.iterdir():
        target = incoming / child.name
        if target.exists() or target.is_symlink():
            raise GateError("source tree collides with transfer evidence")
        os.replace(child, target)
    source.rmdir()


def _assert_manifest_not_expired(manifest: dict[str, object]) -> None:
    try:
        expires = datetime.strptime(
            cast(str, manifest["expires_at"]), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise GateError("release transfer manifest expiry is invalid") from exc
    if datetime.now(UTC) >= expires:
        raise GateError("release transfer manifest has expired")


def _create_transaction_directory(path: Path, intent: _PathMutationIntent) -> None:
    intent.attempted = True
    with _blocked_transaction_signals():
        os.mkdir(path, 0o700)
        _record_created_path(intent, path.lstat())


def _cleanup_transaction_directory(
    path: Path,
    identity: GateIdentity,
    intent: _PathMutationIntent,
) -> None:
    if not path.exists() and not path.is_symlink():
        return

    def valid_transaction(directory: Path) -> bool:
        if not any(directory.iterdir()):
            return True
        _load_state_marker(directory, identity)
        return True

    _remove_owned_directory(
        path,
        intent,
        label="release staging",
        validator=valid_transaction,
    )


def stage_release(root: Path, identity: GateIdentity, stream: BinaryIO) -> dict[str, object]:
    _assert_secure_staging_root(root)
    probe = _load_probe(root, identity)
    request = _exact_dict(
        _read_stdin_json(stream, label="signed URL request"),
        {
            "schema_version",
            "manifest_sha256",
            "deadline_seconds_remaining",
            "urls",
        },
        "signed URL request",
    )
    if request["schema_version"] != SIGNED_URL_SCHEMA:
        raise GateError("signed URL request schema is invalid")
    if request["manifest_sha256"] != identity.manifest_sha256:
        raise GateError("signed URL request identity is invalid")
    deadline_ns = _deadline_from_remaining(request["deadline_seconds_remaining"])
    urls = request["urls"]
    if not isinstance(urls, dict):
        raise GateError("signed URL set is invalid")

    incoming = _path_under(root, identity.incoming_directory)
    if incoming.exists() or incoming.is_symlink():
        raise GateError("incoming release transaction already exists")
    artifacts = incoming / ".artifacts"
    source_tree = incoming / ".source"
    incoming_intent = _PathMutationIntent(attempted=True)
    deadline_stack = contextlib.ExitStack()
    try:
        deadline_stack.enter_context(_deadline_alarm(deadline_ns))
        _create_transaction_directory(incoming, incoming_intent)
        write_state_marker(incoming, identity, "downloading")
        artifacts.mkdir(mode=0o700)
        expected_names = {MANIFEST_FILE}
        probe_bucket = cast(str, probe["bucket"])
        probe_endpoint = cast(str, probe["endpoint_host"])
        try:
            expected_cos_host = cos_object_host(probe_bucket, probe_endpoint)
        except TransferContractError as exc:
            raise GateError("probe endpoint is invalid") from exc
        manifest_url = _validate_url(
            urls.get(MANIFEST_FILE), expected_host=expected_cos_host
        )
        manifest_part = artifacts / f"{MANIFEST_FILE}.part"
        size, _ = _download(
            manifest_url,
            manifest_part,
            maximum_bytes=MAX_MANIFEST_BYTES,
            deadline_ns=deadline_ns,
        )
        if size <= 0 or sha256_path(manifest_part) != identity.manifest_sha256:
            raise GateError("transfer manifest download identity is invalid")
        manifest_path = artifacts / MANIFEST_FILE
        os.replace(manifest_part, manifest_path)
        manifest = load_canonical_manifest(manifest_path)
        _assert_manifest_not_expired(manifest)
        workflow = cast(dict[str, object], manifest["workflow"])
        if (
            manifest["source_revision"] != identity.source_revision
            or workflow["run_id"] != identity.workflow_run_id
            or workflow["run_attempt"] != identity.workflow_run_attempt
        ):
            raise GateError("transfer manifest workflow identity is invalid")
        cos_identity = cast(dict[str, object], manifest["cos"])
        bucket = cast(str, cos_identity["bucket"])
        endpoint = cast(str, cos_identity["endpoint_host"])
        files = cast(list[dict[str, object]], manifest["files"])
        if probe["bucket"] != bucket or probe["endpoint_host"] != endpoint:
            raise GateError("probe endpoint is inconsistent with the transfer manifest")
        probe = evaluate_probe(
            transferred_bytes=cast(int, probe["transferred_bytes"]),
            elapsed_nanoseconds=cast(int, probe["elapsed_nanoseconds"]),
            release_bytes=sum(cast(int, entry["size_bytes"]) for entry in files)
            + manifest_path.stat().st_size,
        )
        expected_names.update(cast(str, entry["path"]) for entry in files)
        if set(urls) != expected_names:
            raise GateError("signed URL exact file set is invalid")
        for entry in files:
            _remaining_timeout(deadline_ns, 1_800)
            _assert_manifest_not_expired(manifest)
            name = cast(str, entry["path"])
            url = _validate_url(urls[name], expected_host=expected_cos_host)
            part = artifacts / f"{name}.part"
            expected_size = cast(int, entry["size_bytes"])
            actual_size, _ = _download(
                url,
                part,
                maximum_bytes=expected_size,
                deadline_ns=deadline_ns,
            )
            if actual_size != expected_size or sha256_path(part) != entry["sha256"]:
                raise GateError("downloaded release file identity is invalid")
            os.replace(part, artifacts / name)
        _assert_manifest_not_expired(manifest)
        load_canonical_manifest(manifest_path, bundle_root=artifacts)

        source_manifest = _exact_dict(
            _load_json_file(
                artifacts / "source-manifest.v1.json",
                maximum_bytes=16 * 1024 * 1024,
                label="source manifest",
            ),
            {"schema_version", "git_sha", "files"},
            "source manifest",
        )
        raw_entries = source_manifest["files"]
        if not isinstance(raw_entries, list):
            raise GateError("source manifest file set is invalid")
        declared_entries: dict[str, tuple[int, str]] = {}
        declared_order: list[str] = []
        declared_total = 0
        for raw_entry in raw_entries:
            entry = _exact_dict(
                raw_entry,
                {"path", "size_bytes", "sha256"},
                "source entry",
            )
            path = _safe_member_path(cast(str, entry["path"])).as_posix()
            size = entry["size_bytes"]
            digest = entry["sha256"]
            if (
                isinstance(size, bool)
                or not isinstance(size, int)
                or size < 0
                or not isinstance(digest, str)
                or SHA256_RE.fullmatch(digest) is None
                or path in declared_entries
            ):
                raise GateError("source manifest file identity is invalid")
            declared_total += size
            if declared_total > MAX_SOURCE_UNCOMPRESSED_BYTES:
                raise GateError("source manifest expands beyond the limit")
            declared_entries[path] = (size, digest)
            declared_order.append(path)
        if declared_order != sorted(declared_order):
            raise GateError("source manifest file order is invalid")
        source_archive = artifacts / f"release-source-{identity.source_revision}.tar.gz"
        safe_extract_source_archive(
            source_archive,
            source_tree,
            declared_entries=declared_entries,
        )
        _validate_source_tree(
            source_tree,
            artifacts / "source-manifest.v1.json",
            identity.source_revision,
        )
        validate_image_archive(
            artifacts / f"release-images-{identity.source_revision}.tar.gz"
        )
        _move_source_tree(source_tree, incoming)
        for artifact in sorted(artifacts.iterdir(), key=lambda item: item.name):
            destination = incoming / artifact.name
            if destination.exists() or destination.is_symlink():
                raise GateError("release evidence collides with source tree")
            os.replace(artifact, destination)
        artifacts.rmdir()
        _verify_source_tree_modes(
            incoming,
            incoming / f"release-source-{identity.source_revision}.tar.gz",
            verify_root=False,
        )
        _remaining_timeout(deadline_ns, 1_800)
        completed = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        receipt = build_transfer_receipt(
            source_revision=identity.source_revision,
            workflow_run_id=identity.workflow_run_id,
            workflow_run_attempt=identity.workflow_run_attempt,
            manifest_sha256=identity.manifest_sha256,
            incoming_directory=identity.incoming_directory,
            completed_at=completed,
            expires_at=cast(str, manifest["expires_at"]),
            probe=probe,
            manifest=manifest,
        )
        _atomic_write(
            incoming / RECEIPT_FILE,
            canonical_json_bytes(receipt),
            exclusive=True,
        )
        _replace_state_marker(incoming, identity, "verified")
        _assert_owned_transaction_tree(incoming)
        _remaining_timeout(deadline_ns, 1_800)
        deadline_stack.close()
        return receipt
    except (
        GateError,
        TransferContractError,
        OSError,
        RecursionError,
        KeyboardInterrupt,
        SystemExit,
    ) as exc:
        effective_exc: BaseException = exc
        try:
            deadline_stack.close()
        except (
            GateError,
            TransferContractError,
            OSError,
            RecursionError,
            KeyboardInterrupt,
            SystemExit,
        ) as close_exc:
            effective_exc = close_exc
        if incoming_intent.attempted:
            _cleanup_transaction_directory(incoming, identity, incoming_intent)
        if isinstance(effective_exc, GateError):
            raise effective_exc
        if isinstance(effective_exc, (KeyboardInterrupt, SystemExit)):
            raise GateError("release staging was interrupted") from effective_exc
        raise GateError("release staging failed") from effective_exc


def _assert_not_current(root: Path, candidate: Path) -> None:
    for name in ("current", "previous"):
        pointer = root / name
        if not pointer.exists() and not pointer.is_symlink():
            continue
        try:
            resolved = pointer.resolve(strict=False)
            candidate_resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise GateError("release pointer is unsafe") from exc
        if resolved == candidate_resolved:
            raise GateError("incoming release is referenced by current or previous")


def cleanup_incoming(
    root: Path,
    identity: GateIdentity,
    *,
    release_root: Path | None = None,
) -> None:
    _assert_secure_staging_root(root)
    final_root = root if release_root is None else release_root
    release_identity = _assert_secure_release_root(
        final_root,
        allow_private_staging_mode=final_root == root,
    )
    incoming = _path_under(root, identity.incoming_directory)
    final = _path_under(final_root, identity.final_directory)
    if final.exists() or final.is_symlink():
        raise GateError("final release path exists; cleanup is forbidden")
    if not incoming.exists() and not incoming.is_symlink():
        _remove_probe_receipt(root, identity)
        if _assert_secure_release_root(
            final_root,
            allow_private_staging_mode=final_root == root,
        ) != release_identity:
            raise GateError("release transfer release root identity changed")
        if final.exists() or final.is_symlink():
            raise GateError("final release path exists; cleanup is forbidden")
        return
    if incoming.is_symlink() or not incoming.is_dir():
        raise GateError("incoming release is unsafe")
    incoming_intent = _PathMutationIntent(attempted=True)
    _record_created_path(incoming_intent, incoming.lstat())
    _assert_owned_transaction_tree(incoming)
    _assert_not_current(final_root, incoming)
    _assert_runtime_not_using_candidate(final_root, identity)
    _assert_no_process_references(final_root, incoming)
    marker = _load_state_marker(incoming, identity)
    if marker["state"] == "verified":
        manifest = load_canonical_manifest(
            incoming / MANIFEST_FILE,
            bundle_root=incoming,
        )
        receipt = validate_transfer_receipt(
            _load_json_file(
                incoming / RECEIPT_FILE,
                maximum_bytes=16 * 1024,
                label="transfer receipt",
            ),
            manifest=manifest,
            expected_source_revision=identity.source_revision,
            expected_workflow_run_id=identity.workflow_run_id,
            expected_workflow_run_attempt=identity.workflow_run_attempt,
            expected_manifest_sha256=identity.manifest_sha256,
        )
        del receipt
    elif marker["state"] != "downloading":
        raise GateError("incoming release cleanup state is invalid")

    def validate_cleanup_target(directory: Path) -> bool:
        _assert_owned_transaction_tree(directory)
        isolated_marker = _load_state_marker(directory, identity)
        if isolated_marker["state"] == "verified":
            isolated_manifest = load_canonical_manifest(
                directory / MANIFEST_FILE,
                bundle_root=directory,
            )
            validate_transfer_receipt(
                _load_json_file(
                    directory / RECEIPT_FILE,
                    maximum_bytes=16 * 1024,
                    label="transfer receipt",
                ),
                manifest=isolated_manifest,
                expected_source_revision=identity.source_revision,
                expected_workflow_run_id=identity.workflow_run_id,
                expected_workflow_run_attempt=identity.workflow_run_attempt,
                expected_manifest_sha256=identity.manifest_sha256,
            )
        elif isolated_marker["state"] != "downloading":
            raise GateError("incoming release cleanup state is invalid")
        return True

    _remove_owned_directory(
        incoming,
        incoming_intent,
        label="incoming release",
        validator=validate_cleanup_target,
    )
    _remove_probe_receipt(root, identity)
    if _assert_secure_release_root(
        final_root,
        allow_private_staging_mode=final_root == root,
    ) != release_identity:
        raise GateError("release transfer release root identity changed")
    if final.exists() or final.is_symlink():
        raise GateError("final release path exists; cleanup is forbidden")


def _assert_runtime_not_using_candidate(root: Path, identity: GateIdentity) -> None:
    if root.resolve() != Path("/opt/ai-video").resolve():
        return
    try:
        result = subprocess.run(
            ["docker", "ps", "--no-trunc", "--format", "{{.Image}} {{.Mounts}} {{.Names}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError("candidate runtime-use check failed") from exc
    if result.returncode != 0:
        raise GateError("candidate runtime-use check failed")
    if identity.source_revision in result.stdout or identity.incoming_directory in result.stdout:
        raise GateError("candidate release is already referenced by a container")


def _assert_no_process_references(release_root: Path, candidate: Path) -> None:
    if release_root.resolve() != DEFAULT_RELEASE_ROOT.resolve() or not Path("/proc").is_dir():
        return
    candidate_text = str(candidate.resolve(strict=True))
    prefix = f"{candidate_text}/"
    try:
        process_paths = list(Path("/proc").glob("[0-9]*"))
    except OSError as exc:
        raise GateError("candidate process-use check failed") from exc
    for process in process_paths:
        references = (process / "cwd", process / "root")
        try:
            references = (*references, *(process / "fd").iterdir())
        except FileNotFoundError:
            pass
        except PermissionError as exc:
            raise GateError("candidate process-use check is ambiguous") from exc
        except OSError as exc:
            raise GateError("candidate process-use check failed") from exc
        for reference in references:
            try:
                target = os.readlink(reference)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise GateError("candidate process-use check is ambiguous") from exc
            if target == candidate_text or target.startswith(prefix):
                raise GateError("candidate release is already referenced by a process")


def _prepare_promoted_permissions(
    incoming: Path,
    manifest: dict[str, object],
) -> None:
    files = cast(list[dict[str, object]], manifest["files"])
    try:
        source_revision = cast(str, manifest["source_revision"])
        _validate_promotable_source_tree(incoming, manifest)
        _verify_source_tree_modes(
            incoming,
            incoming / f"release-source-{source_revision}.tar.gz",
            verify_root=False,
        )
        for entry in files:
            path = incoming / cast(str, entry["path"])
            if path.is_symlink() or not path.is_file():
                raise GateError("promoted release file is missing or unsafe")
            os.chmod(path, 0o644)
        os.chmod(incoming, 0o755)
    except OSError as exc:
        raise GateError("promoted release permissions could not be prepared") from exc


def _assert_receipt_not_expired(receipt: dict[str, object]) -> None:
    try:
        expires = datetime.strptime(
            cast(str, receipt["expires_at"]),
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise GateError("verified incoming release receipt expiry is invalid") from exc
    if datetime.now(UTC) >= expires:
        raise GateError("verified incoming release receipt has expired")


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename one directory without replacing a race winner."""

    system = platform.system()
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if system == "Linux":
        operation = getattr(library, "renameat2", None)
        if operation is None:
            raise GateError("atomic no-replace rename is unavailable")
        result = operation(
            ctypes.c_int(-100),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(-100),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(1),
        )
    elif system == "Darwin":
        operation = getattr(library, "renamex_np", None)
        if operation is None:
            raise GateError("atomic no-replace rename is unavailable")
        result = operation(
            ctypes.c_char_p(source_bytes),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(0x00000004),
        )
    else:
        raise GateError("atomic no-replace rename is unavailable")
    if result != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise GateError("release promotion destination already exists")
        if error in (errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP):
            raise GateError("atomic no-replace rename is unavailable")
        raise GateError("atomic no-replace rename failed") from OSError(error, os.strerror(error))


def verify_atomic_rename_compatibility(staging_root: Path, release_root: Path) -> None:
    """Prove an empty directory can atomically move between the configured roots."""

    _assert_secure_staging_root(staging_root)
    release_identity = _assert_secure_release_root(
        release_root,
        allow_private_staging_mode=release_root == staging_root,
    )
    intent = _PathMutationIntent(attempted=True)
    source: Path | None = None
    destination: Path | None = None
    try:
        with _blocked_transaction_signals():
            source = Path(
                tempfile.mkdtemp(prefix=".rename-contract-", dir=staging_root)
            )
            _record_created_path(intent, source.lstat())
        destination = release_root / source.name
        if _assert_secure_release_root(
            release_root,
            allow_private_staging_mode=release_root == staging_root,
        ) != release_identity:
            raise GateError("release transfer release root identity changed")
        _rename_noreplace(source, destination)
        if source.exists() or not destination.is_dir() or destination.is_symlink():
            raise GateError("atomic no-replace rename verification failed")
    finally:
        foreign_state = False
        for path in (source, destination):
            if path is None or (not path.exists() and not path.is_symlink()):
                continue
            if not _matches_created_path(path, intent, directory=True):
                foreign_state = True
                continue
            try:
                _remove_owned_directory(
                    path,
                    intent,
                    label="atomic rename verification",
                    validator=lambda directory: not any(directory.iterdir()),
                )
            except (OSError, GateError) as exc:
                raise GateError(
                    "atomic rename verification cleanup requires manual recovery"
                ) from exc
        if foreign_state:
            raise GateError(
                "atomic rename verification cleanup requires manual recovery"
            )


def promote_incoming(
    root: Path,
    identity: GateIdentity,
    *,
    release_root: Path | None = None,
) -> Path:
    _assert_secure_staging_root(root)
    final_root = root if release_root is None else release_root
    release_identity = _assert_secure_release_root(
        final_root,
        allow_private_staging_mode=final_root == root,
    )
    incoming = _path_under(root, identity.incoming_directory)
    final = _path_under(final_root, identity.final_directory)
    if incoming.is_symlink() or not incoming.is_dir():
        raise GateError("incoming release is missing or unsafe")
    if final.exists() or final.is_symlink():
        raise GateError("final release path already exists")
    _assert_owned_transaction_tree(incoming)
    _assert_not_current(final_root, incoming)
    _assert_runtime_not_using_candidate(final_root, identity)
    _assert_no_process_references(final_root, incoming)
    if root.stat().st_dev != final_root.stat().st_dev:
        raise GateError("release transfer roots are not on the same filesystem")
    marker = _load_state_marker(incoming, identity)
    if marker["state"] != "verified":
        raise GateError("incoming release is not verified")
    manifest = load_canonical_manifest(
        incoming / MANIFEST_FILE,
        bundle_root=incoming,
    )
    if sha256_path(incoming / MANIFEST_FILE) != identity.manifest_sha256:
        raise GateError("incoming transfer manifest identity is invalid")
    if manifest["source_revision"] != identity.source_revision:
        raise GateError("incoming source revision is invalid")
    receipt = validate_transfer_receipt(
        _load_json_file(
            incoming / RECEIPT_FILE,
            maximum_bytes=16 * 1024,
            label="transfer receipt",
        ),
        manifest=manifest,
        expected_source_revision=identity.source_revision,
        expected_workflow_run_id=identity.workflow_run_id,
        expected_workflow_run_attempt=identity.workflow_run_attempt,
        expected_manifest_sha256=identity.manifest_sha256,
    )
    _assert_receipt_not_expired(receipt)
    try:
        _remove_probe_receipt(root, identity)
    except GateError as exc:
        raise GateError("release promotion probe cleanup failed") from exc
    try:
        _prepare_promoted_permissions(incoming, manifest)
        _assert_receipt_not_expired(receipt)
        if _assert_secure_release_root(
            final_root,
            allow_private_staging_mode=final_root == root,
        ) != release_identity:
            raise GateError("release transfer release root identity changed")
    except GateError as exc:
        try:
            os.chmod(incoming, 0o700)
        except OSError as recovery_exc:
            raise GateError(
                "release promotion preparation requires manual recovery"
            ) from recovery_exc
        raise exc
    try:
        _rename_noreplace(incoming, final)
    except GateError as exc:
        try:
            os.chmod(incoming, 0o700)
        except OSError as recovery_exc:
            raise GateError(
                "release promotion permissions require manual recovery"
            ) from recovery_exc
        raise GateError("release promotion rename failed and was rolled back") from exc
    try:
        _replace_state_marker(final, identity, "promoted")
    except (GateError, OSError) as exc:
        try:
            _rename_noreplace(final, incoming)
            os.chmod(incoming, 0o700)
            _replace_state_marker(incoming, identity, "verified")
        except (GateError, OSError) as recovery_exc:
            raise GateError(
                "release promotion requires manual recovery after marker failure"
            ) from recovery_exc
        raise GateError("release promotion marker failed and was rolled back") from exc
    return final


def read_receipt(root: Path, identity: GateIdentity) -> bytes:
    _assert_secure_staging_root(root)
    incoming = _path_under(root, identity.incoming_directory)
    marker = _load_state_marker(incoming, identity)
    if marker["state"] != "verified":
        raise GateError("incoming release is not verified")
    path = incoming / RECEIPT_FILE
    manifest = load_canonical_manifest(incoming / MANIFEST_FILE, bundle_root=incoming)
    receipt = validate_transfer_receipt(
        _load_json_file(path, maximum_bytes=16 * 1024, label="transfer receipt"),
        manifest=manifest,
        expected_source_revision=identity.source_revision,
        expected_workflow_run_id=identity.workflow_run_id,
        expected_workflow_run_attempt=identity.workflow_run_attempt,
        expected_manifest_sha256=identity.manifest_sha256,
    )
    raw = canonical_json_bytes(receipt)
    if path.read_bytes() != raw:
        raise GateError("transfer receipt is not canonical")
    return raw


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("staging", "production"), required=True)
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--command")
    parser.add_argument("--forced-command", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.forced_command == (args.command is not None):
        print("ERROR: release_transfer_invocation_invalid", file=sys.stderr)
        return 126
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "") if args.forced_command else args.command
    action = "invocation"
    try:
        with _controlled_signals():
            parsed = parse_forced_command(command, role=args.role)
            action = parsed.action
            if parsed.action == "probe":
                result = run_probe(args.staging_root, parsed.identity, sys.stdin.buffer)
                sys.stdout.buffer.write(canonical_json_bytes(result))
            elif parsed.action == "stage":
                result = stage_release(args.staging_root, parsed.identity, sys.stdin.buffer)
                sys.stdout.buffer.write(canonical_json_bytes(result))
            elif parsed.action == "receipt":
                sys.stdout.buffer.write(read_receipt(args.staging_root, parsed.identity))
            elif parsed.action == "cleanup":
                cleanup_incoming(
                    args.staging_root,
                    parsed.identity,
                    release_root=args.release_root,
                )
                print('{"status":"cleaned"}')
            else:
                promoted = promote_incoming(
                    args.staging_root,
                    parsed.identity,
                    release_root=args.release_root,
                )
                print(
                    json.dumps(
                        {"status": "promoted", "release": promoted.name},
                        sort_keys=True,
                    )
                )
    except (GateError, TransferContractError, OSError, RecursionError, ValueError):
        codes = {
            "invocation": "transfer_invocation_invalid",
            "probe": "server_probe_failed",
            "stage": "incoming_stage_failed",
            "receipt": "receipt_readback_failed",
            "cleanup": "incoming_cleanup_failed",
            "promote": "incoming_promotion_failed",
        }
        print(
            json.dumps(
                {
                    "schema_version": "release-transfer-gate-terminal.v1",
                    "status": "failed",
                    "code": codes[action],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 126
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
