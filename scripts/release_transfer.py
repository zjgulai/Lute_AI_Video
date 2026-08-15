#!/usr/bin/env python3
"""Canonical contracts for COS-backed exact release artifact transfer."""

from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import errno
import hashlib
import hmac
import http.client
import json
import math
import os
import platform
import re
import secrets
import signal
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

TRANSFER_SCHEMA = "release-transfer-manifest.v1"
RECEIPT_SCHEMA = "release-transfer-receipt.v1"
SIGNED_URL_SCHEMA = "release-transfer-urls.v1"
GOVERNANCE_SCHEMA = "cos-release-governance.v1"
GOVERNANCE_CAM_TEMPLATE_SHA256 = (
    "6c2d4c822387b3c231a525521af63b968dd2d1ce56173c94063e2c94bc98c1ee"
)
PROBE_SIZE_BYTES = 64 * 1024 * 1024
MIN_BYTES_PER_SECOND = 2 * 1024 * 1024
MAX_ESTIMATED_SECONDS = 1_800
MAX_VALIDITY_SECONDS = 2 * 60 * 60
MAX_MANIFEST_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 16 * 1024
COS_PART_SIZE_BYTES = 64 * 1024 * 1024
COS_RESPONSE_LIMIT_BYTES = 64 * 1024
COS_AUTH_VALIDITY_SECONDS = 600
MAX_JSON_DEPTH = 64
MAX_CAM_POLICY_BYTES = 64 * 1024
MAX_STS_CREDENTIAL_BYTES = 16 * 1024
OIDC_RESPONSE_LIMIT_BYTES = 64 * 1024
CAM_READBACK_CREDENTIAL_BYTES = 16 * 1024
CAM_API_RESPONSE_LIMIT_BYTES = 256 * 1024
CAM_API_ENDPOINT = "cam.tencentcloudapi.com"
CAM_API_VERSION = "2019-01-16"
CAM_READBACK_RECEIPT_SCHEMA = "cam-effective-role-readback.v1"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]-[0-9]{5,20}$")
COS_REGIONAL_ENDPOINT_RE = re.compile(
    r"^cos\.[a-z0-9]+(?:-[a-z0-9]+)+\.myqcloud\.com$"
)
UTC_TIMESTAMP_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ROLE_ARN_RE = re.compile(
    r"^qcs::cam::uin/[1-9][0-9]{4,19}:roleName/[A-Za-z0-9+=,.@_-]{1,64}$"
)
OIDC_PROVIDER_RE = re.compile(r"^[A-Za-z0-9+=,.@_-]{1,64}$")
REQUEST_ID_RE = re.compile(r"^[0-9a-fA-F-]{16,64}$")

FILE_ROLES = (
    "source_archive",
    "source_checksum",
    "source_manifest",
    "image_archive",
    "image_checksum",
    "image_digests",
)
MAX_FILE_BYTES = {
    "source_archive": 2 * 1024 * 1024 * 1024,
    "source_checksum": 256,
    "source_manifest": 16 * 1024 * 1024,
    "image_archive": 16 * 1024 * 1024 * 1024,
    "image_checksum": 256,
    "image_digests": 256,
}
POLICY = {
    "provider_off": True,
    "provider_call": False,
    "w5_submit": False,
    "publish": False,
    "delivery": False,
}


class TransferContractError(ValueError):
    """A release-transfer identity or evidence contract is invalid."""


def _deadline_from_environment(*, default_seconds: int = MAX_ESTIMATED_SECONDS) -> int:
    raw = os.environ.get("TRANSFER_DEADLINE_MONOTONIC_NS", "")
    if not raw:
        return time.monotonic_ns() + default_seconds * 1_000_000_000
    if not raw.isascii() or not raw.isdigit():
        raise TransferContractError("release transfer deadline is invalid")
    deadline = int(raw)
    remaining = deadline - time.monotonic_ns()
    if remaining <= 0 or remaining > MAX_ESTIMATED_SECONDS * 1_000_000_000:
        raise TransferContractError("release transfer deadline is invalid")
    return deadline


def _remaining_timeout(deadline_ns: int, maximum_seconds: int) -> float:
    remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
    if remaining <= 0:
        raise TransferContractError("release transfer deadline exceeded")
    return max(0.001, min(float(maximum_seconds), remaining))


@contextlib.contextmanager
def _deadline_alarm(deadline_ns: int):
    remaining = _remaining_timeout(deadline_ns, MAX_ESTIMATED_SECONDS)
    if not hasattr(signal, "setitimer"):
        yield
        _remaining_timeout(deadline_ns, MAX_ESTIMATED_SECONDS)
        return
    def deadline_reached(_signum, _frame):
        raise TransferContractError("release transfer deadline exceeded")

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
def _controlled_network_signals():
    handled = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    previous = {item: signal.getsignal(item) for item in handled}

    def interrupted(_signum, _frame):
        raise TransferContractError("release transfer interrupted")

    for item in handled:
        signal.signal(item, interrupted)
    try:
        yield
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


@contextlib.contextmanager
def _blocked_output_commit_signals():
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


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _assert_json_depth(payload: object, *, label: str) -> None:
    stack: list[tuple[object, int]] = [(payload, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise TransferContractError(f"{label} exceeds the structural depth limit")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)


def parse_json_bytes(raw: bytes, *, label: str) -> object:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise TransferContractError(f"{label} is not valid JSON") from exc
    _assert_json_depth(payload, label=label)
    return payload


def cos_object_host(bucket: str, endpoint_host: str) -> str:
    if not BUCKET_RE.fullmatch(bucket):
        raise TransferContractError("COS bucket is invalid")
    if not COS_REGIONAL_ENDPOINT_RE.fullmatch(endpoint_host):
        raise TransferContractError("COS endpoint is invalid")
    return f"{bucket}.{endpoint_host}"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TransferContractError("release transfer file is missing or unsafe") from exc
    return digest.hexdigest()


def _regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise TransferContractError(f"{label} is missing or unsafe")
    return path


def _read_bounded_regular_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    allowed_modes: set[int],
) -> bytes:
    """Read one exact inode without following links or reopening its path."""
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        facts = os.fstat(descriptor)
        if (
            not stat.S_ISREG(facts.st_mode)
            or facts.st_uid != os.geteuid()
            or facts.st_nlink != 1
            or stat.S_IMODE(facts.st_mode) not in allowed_modes
        ):
            raise TransferContractError(f"{label} is missing or unsafe")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum_bytes:
                raise TransferContractError(f"{label} exceeds its size limit")
        return b"".join(chunks)
    except TransferContractError:
        raise
    except OSError as exc:
        raise TransferContractError(f"{label} is missing or unsafe") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _atomic_rename_noreplace_at(
    parent_descriptor: int,
    source_name: str,
    destination_name: str,
) -> None:
    """Atomically rename two entries inside one already-verified directory."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    if platform.system() == "Linux":
        operation = getattr(library, "renameat2", None)
        if operation is None:
            raise OSError(errno.ENOSYS, "atomic no-replace rename is unavailable")
        operation.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        operation.restype = ctypes.c_int
        result = operation(
            ctypes.c_int(parent_descriptor),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(parent_descriptor),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(1),
        )
    elif platform.system() == "Darwin":
        operation = getattr(library, "renameatx_np", None)
        if operation is None:
            raise OSError(errno.ENOSYS, "atomic no-replace rename is unavailable")
        operation.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        operation.restype = ctypes.c_int
        result = operation(
            ctypes.c_int(parent_descriptor),
            ctypes.c_char_p(source_bytes),
            ctypes.c_int(parent_descriptor),
            ctypes.c_char_p(destination_bytes),
            ctypes.c_uint(0x00000004),
        )
    else:
        raise OSError(errno.ENOSYS, "atomic no-replace rename is unavailable")
    if result != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(error, os.strerror(error), destination_name)
        raise OSError(error, os.strerror(error), source_name)


def _matches_private_file(facts: os.stat_result, expected: os.stat_result) -> bool:
    return (
        facts.st_dev == expected.st_dev
        and facts.st_ino == expected.st_ino
        and stat.S_ISREG(facts.st_mode)
        and facts.st_uid == expected.st_uid
        and facts.st_nlink == 1
        and stat.S_IMODE(facts.st_mode) == 0o600
    )


def _consume_bounded_private_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    """Read and unlink one private inode before returning its secret bytes."""
    parent_descriptor: int | None = None
    descriptor: int | None = None
    facts: os.stat_result | None = None
    read_error: TransferContractError | None = None
    raw = b""
    with _blocked_output_commit_signals():
        try:
            parent_descriptor = os.open(
                path.parent,
                os.O_RDONLY
                | os.O_CLOEXEC
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            parent_facts = os.fstat(parent_descriptor)
            if (
                not stat.S_ISDIR(parent_facts.st_mode)
                or parent_facts.st_uid != os.geteuid()
                or stat.S_IMODE(parent_facts.st_mode) != 0o700
                or path.name in ("", ".", "..")
            ):
                raise TransferContractError(f"{label} directory is missing or unsafe")
            descriptor = os.open(
                path.name,
                os.O_RDWR | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            facts = os.fstat(descriptor)
            if (
                not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != os.geteuid()
                or facts.st_nlink != 1
                or stat.S_IMODE(facts.st_mode) != 0o600
            ):
                raise TransferContractError(f"{label} is missing or unsafe")
            chunks: list[bytes] = []
            size = 0
            try:
                while True:
                    chunk = os.read(
                        descriptor,
                        min(64 * 1024, maximum_bytes + 1 - size),
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > maximum_bytes:
                        raise TransferContractError(f"{label} exceeds its size limit")
                raw = b"".join(chunks)
            except TransferContractError as exc:
                read_error = exc
            except OSError as exc:
                read_error = TransferContractError(f"{label} is missing or unsafe")
                read_error.__cause__ = exc

            try:
                os.ftruncate(descriptor, 0)
                os.fsync(descriptor)
            except OSError as exc:
                raise TransferContractError(
                    f"{label} cleanup failed; manual recovery is required"
                ) from exc

            quarantine: Path | None = None
            for _ in range(4):
                candidate = path.parent / f".cam-readback-consume-{secrets.token_hex(16)}"
                try:
                    _atomic_rename_noreplace_at(
                        parent_descriptor,
                        path.name,
                        candidate.name,
                    )
                except FileExistsError:
                    continue
                except (OSError, TransferContractError, KeyboardInterrupt, SystemExit) as exc:
                    try:
                        candidate_facts = os.stat(
                            candidate.name,
                            dir_fd=parent_descriptor,
                            follow_symlinks=False,
                        )
                    except OSError:
                        raise TransferContractError(
                            f"{label} cleanup failed; manual recovery is required"
                        ) from exc
                    if not _matches_private_file(candidate_facts, facts):
                        raise TransferContractError(
                            f"{label} cleanup failed; manual recovery is required"
                        ) from exc
                    quarantine = candidate
                    break
                quarantine = candidate
                break
            if quarantine is None:
                raise TransferContractError(
                    f"{label} cleanup failed; manual recovery is required"
                )
            try:
                isolated_facts = os.stat(
                    quarantine.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if not _matches_private_file(isolated_facts, facts):
                    raise OSError("credential quarantine identity changed")
                os.unlink(quarantine.name, dir_fd=parent_descriptor)
            except OSError as exc:
                raise TransferContractError(
                    f"{label} cleanup failed; manual recovery is required"
                ) from exc
            if read_error is not None:
                raise read_error
            return raw
        except TransferContractError:
            raise
        except OSError as exc:
            raise TransferContractError(f"{label} is missing or unsafe") from exc
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if parent_descriptor is not None:
                try:
                    os.close(parent_descriptor)
                except OSError:
                    pass


def _exact_dict(payload: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != keys:
        raise TransferContractError(f"{label} fields are invalid")
    return payload


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TransferContractError(f"{label} is invalid")
    return value


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        raise TransferContractError(f"{label} is invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise TransferContractError(f"{label} is invalid") from exc
    return parsed


def validate_release_governance_contract(payload: object) -> dict[str, object]:
    contract = _exact_dict(
        payload,
        {"schema_version", "sts", "lifecycle", "privacy", "cam_policy"},
        "release governance contract",
    )
    if contract["schema_version"] != GOVERNANCE_SCHEMA:
        raise TransferContractError("release governance schema is invalid")

    sts = _exact_dict(
        contract["sts"],
        {
            "api_endpoint",
            "api_version",
            "audience",
            "duration_seconds",
            "environment",
            "github_repository",
            "issuer",
            "minimum_remaining_seconds_before_mutation",
            "transfer_deadline_seconds",
            "cleanup_reserve_seconds",
            "setup_and_evidence_reserve_seconds",
        },
        "release governance STS policy",
    )
    duration = _positive_int(sts["duration_seconds"], "STS duration")
    minimum_remaining = _positive_int(
        sts["minimum_remaining_seconds_before_mutation"],
        "STS minimum remaining duration",
    )
    transfer_deadline = _positive_int(
        sts["transfer_deadline_seconds"], "transfer deadline"
    )
    cleanup_reserve = _positive_int(
        sts["cleanup_reserve_seconds"], "cleanup reserve"
    )
    setup_and_evidence_reserve = _positive_int(
        sts["setup_and_evidence_reserve_seconds"], "setup and evidence reserve"
    )
    if (
        sts["api_endpoint"] != "sts.tencentcloudapi.com"
        or sts["api_version"] != "2018-08-13"
        or sts["audience"] != "sts.tencentcloudapi.com"
        or sts["environment"] != "production-artifact-staging"
        or sts["github_repository"] != "zjgulai/Lute_AI_Video"
        or sts["issuer"] != "https://token.actions.githubusercontent.com"
        or
        duration != MAX_VALIDITY_SECONDS
        or transfer_deadline != MAX_ESTIMATED_SECONDS
        or cleanup_reserve != 300
        or setup_and_evidence_reserve != 1500
        or minimum_remaining
        != transfer_deadline + cleanup_reserve + setup_and_evidence_reserve
        or minimum_remaining >= duration
    ):
        raise TransferContractError("release governance STS policy is invalid")

    lifecycle = _exact_dict(
        contract["lifecycle"],
        {"additional_rules_allowed", "rules"},
        "release governance lifecycle policy",
    )
    if lifecycle["additional_rules_allowed"] is not False:
        raise TransferContractError("release governance lifecycle policy is invalid")

    privacy = _exact_dict(
        contract["privacy"],
        {"acl", "bucket_policy"},
        "release governance privacy policy",
    )
    if privacy != {
        "acl": "owner-full-control-only",
        "bucket_policy": "absent",
    }:
        raise TransferContractError("release governance privacy policy is invalid")
    raw_rules = lifecycle["rules"]
    if not isinstance(raw_rules, list) or len(raw_rules) != 3:
        raise TransferContractError("release governance lifecycle policy is invalid")
    rules: list[dict[str, object]] = []
    for raw_rule in raw_rules:
        rule = _exact_dict(
            raw_rule,
            {
                "id",
                "prefix",
                "status",
                "expiration_days",
                "abort_incomplete_multipart_upload_days",
            },
            "release governance lifecycle rule",
        )
        if (
            not isinstance(rule["id"], str)
            or not isinstance(rule["prefix"], str)
            or rule["status"] != "Enabled"
        ):
            raise TransferContractError("release governance lifecycle rule is invalid")
        expiration = rule["expiration_days"]
        abort = rule["abort_incomplete_multipart_upload_days"]
        if (expiration is None) == (abort is None):
            raise TransferContractError("release governance lifecycle rule is invalid")
        if expiration is not None:
            _positive_int(expiration, "lifecycle expiration")
        if abort is not None:
            _positive_int(abort, "multipart abort interval")
        rules.append(dict(rule))
    expected_rules = [
        {
            "id": "ai-video-probes-expire-v1",
            "prefix": "ai-video/probes/",
            "status": "Enabled",
            "expiration_days": 1,
            "abort_incomplete_multipart_upload_days": None,
        },
        {
            "id": "ai-video-release-multipart-abort-v1",
            "prefix": "ai-video/releases/",
            "status": "Enabled",
            "expiration_days": None,
            "abort_incomplete_multipart_upload_days": 1,
        },
        {
            "id": "ai-video-releases-expire-v1",
            "prefix": "ai-video/releases/",
            "status": "Enabled",
            "expiration_days": 14,
            "abort_incomplete_multipart_upload_days": None,
        },
    ]
    if rules != expected_rules:
        raise TransferContractError("release governance lifecycle policy is invalid")

    cam_policy = _exact_dict(
        contract["cam_policy"],
        {"version", "statement_templates"},
        "release governance CAM policy",
    )
    if cam_policy["version"] != "2.0":
        raise TransferContractError("release governance CAM policy is invalid")
    templates = cam_policy["statement_templates"]
    if not isinstance(templates, list) or len(templates) != 3:
        raise TransferContractError("release governance CAM policy is invalid")
    normalized_templates: list[dict[str, object]] = []
    for raw_template in templates:
        template = _exact_dict(
            raw_template,
            {"id", "effect", "actions", "resources", "condition"},
            "release governance CAM statement",
        )
        actions = template["actions"]
        resources = template["resources"]
        if (
            not isinstance(template["id"], str)
            or template["effect"] != "allow"
            or not isinstance(actions, list)
            or not actions
            or any(not isinstance(item, str) or not item.startswith("name/cos:") for item in actions)
            or len(set(cast(list[str], actions))) != len(actions)
            or not isinstance(resources, list)
            or not resources
            or any(not isinstance(item, str) or not item.startswith("qcs::cos:") for item in resources)
            or template["condition"] != {}
        ):
            raise TransferContractError("release governance CAM statement is invalid")
        normalized_templates.append(dict(template))
    if [item["id"] for item in normalized_templates] != [
        "bucket-readback",
        "run-bound-probe",
        "exact-release",
    ]:
        raise TransferContractError("release governance CAM policy is invalid")
    normalized_cam = {
        "version": "2.0",
        "statement_templates": normalized_templates,
    }
    if (
        hashlib.sha256(canonical_json_bytes(normalized_cam)).hexdigest()
        != GOVERNANCE_CAM_TEMPLATE_SHA256
    ):
        raise TransferContractError("release governance CAM policy is invalid")

    return {
        "schema_version": GOVERNANCE_SCHEMA,
        "sts": dict(sts),
        "lifecycle": {
            "additional_rules_allowed": False,
            "rules": rules,
        },
        "privacy": dict(privacy),
        "cam_policy": {
            **normalized_cam,
        },
    }


def load_release_governance_contract(path: Path) -> dict[str, object]:
    source = _regular_file(path, "release governance contract")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise TransferContractError("release governance contract is unreadable") from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise TransferContractError("release governance contract is too large")
    return validate_release_governance_contract(
        parse_json_bytes(raw, label="release governance contract")
    )


def validate_sts_window(
    *,
    duration_seconds: int,
    expires_at: str,
    contract: dict[str, object],
    now: datetime | None = None,
) -> dict[str, int | str]:
    validated = validate_release_governance_contract(contract)
    sts = cast(dict[str, object], validated["sts"])
    expires = _parse_utc(expires_at, "STS expiry timestamp")
    current = datetime.now(UTC) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise TransferContractError("STS current timestamp is invalid")
    remaining = int((expires - current.astimezone(UTC)).total_seconds())
    expected_duration = cast(int, sts["duration_seconds"])
    minimum_remaining = cast(
        int, sts["minimum_remaining_seconds_before_mutation"]
    )
    if (
        isinstance(duration_seconds, bool)
        or duration_seconds != expected_duration
    ):
        raise TransferContractError("STS duration is invalid")
    if remaining < minimum_remaining or remaining > duration_seconds:
        raise TransferContractError("STS remaining validity is insufficient")
    return {
        "status": "passed",
        "duration_seconds": duration_seconds,
        "remaining_seconds": remaining,
        "cleanup_reserve_seconds": cast(int, sts["cleanup_reserve_seconds"]),
    }


def _decode_oidc_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise TransferContractError("GitHub OIDC token is invalid")
    encoded = parts[1]
    if len(encoded) > OIDC_RESPONSE_LIMIT_BYTES:
        raise TransferContractError("GitHub OIDC token is invalid")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as exc:
        raise TransferContractError("GitHub OIDC token is invalid") from exc
    payload = parse_json_bytes(raw, label="GitHub OIDC token")
    if not isinstance(payload, dict):
        raise TransferContractError("GitHub OIDC token is invalid")
    return cast(dict[str, object], payload)


def _validate_github_oidc_claims(
    token: str,
    *,
    contract: dict[str, object],
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    now: datetime,
) -> None:
    validated = validate_release_governance_contract(contract)
    sts = cast(dict[str, object], validated["sts"])
    claims = _decode_oidc_claims(token)
    repository = cast(str, sts["github_repository"])
    environment = cast(str, sts["environment"])
    expected = {
        "iss": sts["issuer"],
        "aud": sts["audience"],
        "sub": f"repo:{repository}:environment:{environment}",
        "repository": repository,
        "sha": source_revision,
        "run_id": str(workflow_run_id),
        "run_attempt": str(workflow_run_attempt),
    }
    if any(str(claims.get(key, "")) != str(value) for key, value in expected.items()):
        raise TransferContractError("GitHub OIDC token identity is invalid")
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
    ):
        raise TransferContractError("GitHub OIDC token validity is invalid")
    timestamp = int(now.timestamp())
    if issued_at > timestamp + 60 or expires_at <= timestamp + 60 or expires_at > timestamp + 600:
        raise TransferContractError("GitHub OIDC token validity is invalid")


def _github_oidc_token(
    *,
    request_url: str,
    request_token: str,
    audience: str,
    deadline_ns: int,
) -> str:
    try:
        parsed = urllib.parse.urlsplit(request_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise TransferContractError("GitHub OIDC request configuration is invalid") from exc
    github_transport_host = (
        hostname == "actions.githubusercontent.com"
        or (
            isinstance(hostname, str)
            and hostname.endswith(".actions.githubusercontent.com")
            and hostname.removesuffix(".actions.githubusercontent.com")
            and all(
                re.fullmatch(r"[a-z0-9-]{1,63}", label)
                and not label.startswith("-")
                and not label.endswith("-")
                for label in hostname.removesuffix(
                    ".actions.githubusercontent.com"
                ).split(".")
            )
        )
    )
    if (
        parsed.scheme != "https"
        or not github_transport_host
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path.startswith("/")
        or "/_apis/" not in parsed.path
        or not request_token
        or "\n" in request_token
        or "\r" in request_token
    ):
        raise TransferContractError("GitHub OIDC request configuration is invalid")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if any(key == "audience" for key, _ in query):
        raise TransferContractError("GitHub OIDC request configuration is invalid")
    query.append(("audience", audience))
    url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), "")
    )
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
        method="GET",
    )
    try:
        with _open_no_redirect(
            request,
            timeout=_remaining_timeout(deadline_ns, 30),
        ) as response:
            if response.status != 200:
                raise TransferContractError("GitHub OIDC token request failed")
            payload = parse_json_bytes(
                _read_bounded(
                    response,
                    deadline_ns=deadline_ns,
                    maximum_bytes=OIDC_RESPONSE_LIMIT_BYTES,
                ),
                label="GitHub OIDC response",
            )
    except urllib.error.HTTPError:
        raise TransferContractError("GitHub OIDC token request failed") from None
    except (OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise TransferContractError("GitHub OIDC token request failed") from exc
    if not isinstance(payload, dict) or set(payload) not in (
        {"value"},
        {"count", "value"},
    ):
        raise TransferContractError("GitHub OIDC response fields are invalid")
    response_payload = cast(dict[str, object], payload)
    if "count" in response_payload:
        count = response_payload["count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TransferContractError("GitHub OIDC token response is invalid")
    token = response_payload["value"]
    if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
        raise TransferContractError("GitHub OIDC token response is invalid")
    return token


def _tencent_sts_response(
    *,
    oidc_token: str,
    provider_id: str,
    role_arn: str,
    role_session_name: str,
    duration_seconds: int,
    region: str,
    contract: dict[str, object],
    deadline_ns: int,
    now: datetime,
) -> dict[str, object]:
    validated = validate_release_governance_contract(contract)
    sts = cast(dict[str, object], validated["sts"])
    if not OIDC_PROVIDER_RE.fullmatch(provider_id) or not ROLE_ARN_RE.fullmatch(role_arn):
        raise TransferContractError("Tencent STS role configuration is invalid")
    if not re.fullmatch(r"ai-video-[1-9][0-9]*-[1-9][0-9]*", role_session_name):
        raise TransferContractError("Tencent STS role session is invalid")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", region):
        raise TransferContractError("Tencent STS region is invalid")
    if duration_seconds != sts["duration_seconds"]:
        raise TransferContractError("Tencent STS duration is invalid")
    request_timestamp = int(now.timestamp())
    body = canonical_json_bytes(
        {
            "DurationSeconds": duration_seconds,
            "ProviderId": provider_id,
            "RoleArn": role_arn,
            "RoleSessionName": role_session_name,
            "WebIdentityToken": oidc_token,
        }
    )
    request = urllib.request.Request(
        f"https://{sts['api_endpoint']}/",
        data=body,
        headers={
            "Authorization": "SKIP",
            "Content-Type": "application/json; charset=utf-8",
            "Host": cast(str, sts["api_endpoint"]),
            "X-TC-Action": "AssumeRoleWithWebIdentity",
            "X-TC-Region": region,
            "X-TC-Timestamp": str(request_timestamp),
            "X-TC-Version": cast(str, sts["api_version"]),
        },
        method="POST",
    )
    try:
        with _open_no_redirect(
            request,
            timeout=_remaining_timeout(deadline_ns, 30),
        ) as response:
            if response.status != 200:
                raise TransferContractError("Tencent STS request failed")
            payload = parse_json_bytes(
                _read_bounded(
                    response,
                    deadline_ns=deadline_ns,
                    maximum_bytes=OIDC_RESPONSE_LIMIT_BYTES,
                ),
                label="Tencent STS response",
            )
    except urllib.error.HTTPError:
        raise TransferContractError("Tencent STS request failed") from None
    except (OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise TransferContractError("Tencent STS request failed") from exc
    outer = _exact_dict(payload, {"Response"}, "Tencent STS response")
    response_payload = _exact_dict(
        outer["Response"],
        {"Credentials", "ExpiredTime", "Expiration", "RequestId"},
        "Tencent STS response",
    )
    credentials = _exact_dict(
        response_payload["Credentials"],
        {"Token", "TmpSecretId", "TmpSecretKey"},
        "Tencent STS credentials",
    )
    values = [credentials["TmpSecretId"], credentials["TmpSecretKey"], credentials["Token"]]
    if any(not isinstance(value, str) or not value or "\n" in value or "\r" in value for value in values):
        raise TransferContractError("Tencent STS credentials are invalid")
    expiration = _parse_utc(response_payload["Expiration"], "Tencent STS expiration")
    expired_time = response_payload["ExpiredTime"]
    request_id = response_payload["RequestId"]
    if (
        isinstance(expired_time, bool)
        or not isinstance(expired_time, int)
        or int(expiration.timestamp()) != expired_time
        or expired_time - request_timestamp < cast(int, sts["minimum_remaining_seconds_before_mutation"])
        or expired_time - request_timestamp > duration_seconds + 300
        or not isinstance(request_id, str)
        or not REQUEST_ID_RE.fullmatch(request_id)
    ):
        raise TransferContractError("Tencent STS response validity is invalid")
    return {
        "credentials": {
            "secret_id": credentials["TmpSecretId"],
            "secret_key": credentials["TmpSecretKey"],
            "session_token": credentials["Token"],
        },
        "expiration": response_payload["Expiration"],
        "expired_time": expired_time,
        "request_id": request_id,
        "requested_at": datetime.fromtimestamp(request_timestamp, UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }


def assume_github_oidc_role(
    *,
    contract: dict[str, object],
    provider_id: str,
    role_arn: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    bucket: str,
    endpoint_host: str,
    credentials_output: Path,
    request_url: str,
    request_token: str,
    now: datetime | None = None,
    deadline_ns: int | None = None,
) -> dict[str, object]:
    if not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("Tencent STS source revision is invalid")
    _positive_int(workflow_run_id, "Tencent STS workflow run ID")
    _positive_int(workflow_run_attempt, "Tencent STS workflow run attempt")
    validated = validate_release_governance_contract(contract)
    sts = cast(dict[str, object], validated["sts"])
    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    operation_deadline = (
        _deadline_from_environment(default_seconds=60)
        if deadline_ns is None
        else deadline_ns
    )
    with _deadline_alarm(operation_deadline):
        oidc_token = _github_oidc_token(
            request_url=request_url,
            request_token=request_token,
            audience=cast(str, sts["audience"]),
            deadline_ns=operation_deadline,
        )
        _validate_github_oidc_claims(
            oidc_token,
            contract=validated,
            source_revision=source_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
            now=current,
        )
        region = _cos_policy_context(
            bucket=bucket,
            endpoint_host=endpoint_host,
            source_revision=source_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
        )["region"]
        issued = _tencent_sts_response(
            oidc_token=oidc_token,
            provider_id=provider_id,
            role_arn=role_arn,
            role_session_name=f"ai-video-{workflow_run_id}-{workflow_run_attempt}",
            duration_seconds=cast(int, sts["duration_seconds"]),
            region=region,
            contract=validated,
            deadline_ns=operation_deadline,
            now=current,
        )
    credential_payload = {
        "schema_version": "cos-sts-credentials.v1",
        "source_revision": source_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "provider_id": provider_id,
        "role_arn": role_arn,
        "duration_seconds": sts["duration_seconds"],
        "expiration": issued["expiration"],
        "expired_time": issued["expired_time"],
        "request_id": issued["request_id"],
        "credentials": issued["credentials"],
    }
    write_exclusive(credentials_output, canonical_json_bytes(credential_payload))
    return {
        "schema_version": "cos-sts-issuance-receipt.v1",
        "status": "issued",
        "source_revision": source_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "provider_id": provider_id,
        "role_arn": role_arn,
        "duration_seconds": sts["duration_seconds"],
        "requested_at": issued["requested_at"],
        "expiration": issued["expiration"],
        "expired_time": issued["expired_time"],
        "request_id": issued["request_id"],
    }


def _cos_policy_context(
    *,
    bucket: str,
    endpoint_host: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> dict[str, str]:
    cos_object_host(bucket, endpoint_host)
    if not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("CAM policy source revision is invalid")
    _positive_int(workflow_run_id, "CAM policy workflow run ID")
    _positive_int(workflow_run_attempt, "CAM policy workflow run attempt")
    bucket_name, separator, appid = bucket.rpartition("-")
    if not separator or not bucket_name or not appid.isdigit():
        raise TransferContractError("CAM policy bucket identity is invalid")
    region = endpoint_host.removeprefix("cos.").removesuffix(".myqcloud.com")
    return {
        "region": region,
        "appid": appid,
        "bucket": bucket,
        "source_revision": source_revision,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_attempt": str(workflow_run_attempt),
    }


def build_expected_cam_policy(
    *,
    contract: dict[str, object],
    bucket: str,
    endpoint_host: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> dict[str, object]:
    validated = validate_release_governance_contract(contract)
    context = _cos_policy_context(
        bucket=bucket,
        endpoint_host=endpoint_host,
        source_revision=source_revision,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    cam = cast(dict[str, object], validated["cam_policy"])
    statements: list[dict[str, object]] = []
    for template in cast(list[dict[str, object]], cam["statement_templates"]):
        statements.append(
            {
                "effect": template["effect"],
                "action": sorted(cast(list[str], template["actions"])),
                "resource": sorted(
                    item.format_map(context)
                    for item in cast(list[str], template["resources"])
                ),
                "condition": template["condition"],
            }
        )
    statements.sort(key=canonical_json_bytes)
    return {"version": cam["version"], "statement": statements}


def _normalize_cam_policy(payload: object) -> dict[str, object]:
    policy = _exact_dict(payload, {"version", "statement"}, "CAM policy")
    if policy["version"] != "2.0" or not isinstance(policy["statement"], list):
        raise TransferContractError("CAM policy readback is invalid")
    statements: list[dict[str, object]] = []
    for raw_statement in policy["statement"]:
        statement = _exact_dict(
            raw_statement,
            {"effect", "action", "resource", "condition"},
            "CAM policy statement",
        )
        actions = statement["action"]
        resources = statement["resource"]
        if (
            statement["effect"] != "allow"
            or not isinstance(actions, list)
            or not actions
            or any(not isinstance(item, str) for item in actions)
            or len(set(cast(list[str], actions))) != len(actions)
            or not isinstance(resources, list)
            or not resources
            or any(not isinstance(item, str) for item in resources)
            or len(set(cast(list[str], resources))) != len(resources)
            or statement["condition"] != {}
        ):
            raise TransferContractError("CAM policy readback is invalid")
        statements.append(
            {
                "effect": "allow",
                "action": sorted(cast(list[str], actions)),
                "resource": sorted(cast(list[str], resources)),
                "condition": {},
            }
        )
    statements.sort(key=canonical_json_bytes)
    return {"version": "2.0", "statement": statements}


def validate_cam_policy_readback(
    payload: object,
    *,
    contract: dict[str, object],
    bucket: str,
    endpoint_host: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> dict[str, object]:
    actual = _normalize_cam_policy(payload)
    expected = build_expected_cam_policy(
        contract=contract,
        bucket=bucket,
        endpoint_host=endpoint_host,
        source_revision=source_revision,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    if actual != expected:
        raise TransferContractError("CAM policy readback does not match the contract")
    return actual


def expected_cam_policy_sha256(
    *,
    contract: dict[str, object],
    bucket: str,
    endpoint_host: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            build_expected_cam_policy(
                contract=contract,
                bucket=bucket,
                endpoint_host=endpoint_host,
                source_revision=source_revision,
                workflow_run_id=workflow_run_id,
                workflow_run_attempt=workflow_run_attempt,
            )
        )
    ).hexdigest()


def _load_cam_readback_credentials(
    path: Path,
    *,
    now: datetime,
) -> dict[str, str]:
    payload = parse_json_bytes(
        _consume_bounded_private_file(
            path,
            label="CAM readback credentials",
            maximum_bytes=CAM_READBACK_CREDENTIAL_BYTES,
        ),
        label="CAM readback credentials",
    )
    document = _exact_dict(
        payload,
        {"schema_version", "expiration", "credentials"},
        "CAM readback credentials",
    )
    if document["schema_version"] != "cam-readback-credentials.v1":
        raise TransferContractError("CAM readback credentials are invalid")
    expiration = _parse_utc(document["expiration"], "CAM readback credential expiration")
    remaining = int((expiration - now.astimezone(UTC)).total_seconds())
    if not 600 <= remaining <= MAX_VALIDITY_SECONDS + 300:
        raise TransferContractError("CAM readback credential validity is invalid")
    credentials = _exact_dict(
        document["credentials"],
        {"secret_id", "secret_key", "session_token"},
        "CAM readback credentials",
    )
    values = [credentials["secret_id"], credentials["secret_key"], credentials["session_token"]]
    if any(
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\n" in value
        or "\r" in value
        for value in values
    ):
        raise TransferContractError("CAM readback credentials are invalid")
    return cast(dict[str, str], credentials)


def _tc3_hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def _tencent_cam_request(
    *,
    action: str,
    body: dict[str, object],
    credentials: dict[str, str],
    deadline_ns: int,
    now: datetime,
) -> dict[str, object]:
    allowed_actions = {
        "DescribeOIDCConfig",
        "GetRole",
        "GetRolePermissionBoundary",
        "GetPolicyVersion",
        "ListAttachedRolePolicies",
        "ListPolicyVersions",
    }
    if action not in allowed_actions:
        raise TransferContractError("CAM readback action is invalid")
    timestamp = int(now.astimezone(UTC).timestamp())
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    payload = canonical_json_bytes(body)
    content_type = "application/json; charset=utf-8"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{CAM_API_ENDPOINT}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join(
        (
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            hashlib.sha256(payload).hexdigest(),
        )
    )
    scope = f"{date}/cam/tc3_request"
    string_to_sign = "\n".join(
        (
            "TC3-HMAC-SHA256",
            str(timestamp),
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        )
    )
    secret_date = _tc3_hmac(("TC3" + credentials["secret_key"]).encode(), date)
    secret_service = _tc3_hmac(secret_date, "cam")
    secret_signing = _tc3_hmac(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "TC3-HMAC-SHA256 "
        f"Credential={credentials['secret_id']}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    request = urllib.request.Request(
        f"https://{CAM_API_ENDPOINT}/",
        data=payload,
        headers={
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": CAM_API_ENDPOINT,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Token": credentials["session_token"],
            "X-TC-Version": CAM_API_VERSION,
        },
        method="POST",
    )
    try:
        with _open_no_redirect(
            request,
            timeout=_remaining_timeout(deadline_ns, 30),
        ) as response:
            if response.status != 200:
                raise TransferContractError("CAM readback request failed")
            raw = _read_bounded(
                response,
                deadline_ns=deadline_ns,
                maximum_bytes=CAM_API_RESPONSE_LIMIT_BYTES,
            )
    except urllib.error.HTTPError:
        raise TransferContractError("CAM readback request failed") from None
    except (OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise TransferContractError("CAM readback request failed") from exc
    outer = parse_json_bytes(raw, label="CAM readback response")
    if not isinstance(outer, dict) or not isinstance(outer.get("Response"), dict):
        raise TransferContractError("CAM readback response is invalid")
    result = cast(dict[str, object], outer["Response"])
    if "Error" in result:
        raise TransferContractError("CAM readback request failed")
    request_id = result.get("RequestId")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise TransferContractError("CAM readback response provenance is invalid")
    return result


def _cam_api_json(value: object, label: str) -> object:
    if not isinstance(value, str) or len(value.encode()) > MAX_CAM_POLICY_BYTES:
        raise TransferContractError(f"{label} is invalid")
    return parse_json_bytes(value.encode(), label=label)


def _normalized_string_values(value: object, label: str) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(item, str) or not item for item in values)
        or len(set(cast(list[str], values))) != len(values)
    ):
        raise TransferContractError(f"{label} is invalid")
    return sorted(cast(list[str], values))


def _validate_cam_oidc_trust(
    payload: object,
    *,
    role_arn: str,
    provider_id: str,
    issuer: str,
    audience: str,
    subject: str,
) -> None:
    policy = _exact_dict(payload, {"version", "statement"}, "CAM role trust")
    if policy["version"] != "2.0" or not isinstance(policy["statement"], list):
        raise TransferContractError("CAM role trust is invalid")
    statements = cast(list[object], policy["statement"])
    if len(statements) != 1:
        raise TransferContractError("CAM role trust is invalid")
    statement = _exact_dict(
        statements[0],
        {"action", "effect", "principal", "condition"},
        "CAM role trust statement",
    )
    principal = _exact_dict(statement["principal"], {"federated"}, "CAM role trust principal")
    condition = _exact_dict(statement["condition"], {"string_equal"}, "CAM role trust condition")
    string_equal = _exact_dict(
        condition["string_equal"],
        {"oidc:iss", "oidc:aud", "oidc:sub"},
        "CAM role trust condition",
    )
    owner_uin = role_arn.split("uin/", 1)[1].split(":", 1)[0]
    expected_principal = f"qcs::cam::uin/{owner_uin}:oidc-provider/{provider_id}"
    if (
        statement["effect"] != "allow"
        or _normalized_string_values(statement["action"], "CAM role trust action")
        != ["name/sts:AssumeRoleWithWebIdentity"]
        or _normalized_string_values(principal["federated"], "CAM role trust principal")
        != [expected_principal]
        or _normalized_string_values(string_equal["oidc:iss"], "CAM OIDC issuer")
        != [issuer]
        or _normalized_string_values(string_equal["oidc:aud"], "CAM OIDC audience")
        != [audience]
        or _normalized_string_values(string_equal["oidc:sub"], "CAM OIDC subject")
        != [subject]
    ):
        raise TransferContractError("CAM role trust is invalid")


def readback_cam_effective_role(
    *,
    contract: dict[str, object],
    credentials_path: Path,
    provider_id: str,
    role_arn: str,
    bucket: str,
    endpoint_host: str,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    now: datetime | None = None,
    deadline_ns: int | None = None,
) -> dict[str, object]:
    validated = validate_release_governance_contract(contract)
    sts = cast(dict[str, object], validated["sts"])
    if not OIDC_PROVIDER_RE.fullmatch(provider_id) or not ROLE_ARN_RE.fullmatch(role_arn):
        raise TransferContractError("CAM readback target is invalid")
    if not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("CAM readback source revision is invalid")
    _positive_int(workflow_run_id, "CAM readback workflow run ID")
    _positive_int(workflow_run_attempt, "CAM readback workflow run attempt")
    role_name = role_arn.rsplit("/", 1)[1]
    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    operation_deadline = (
        _deadline_from_environment(default_seconds=120)
        if deadline_ns is None
        else deadline_ns
    )
    credentials = _load_cam_readback_credentials(credentials_path, now=current)
    request_ids: dict[str, str] = {}

    def request(action: str, body: dict[str, object]) -> dict[str, object]:
        result = _tencent_cam_request(
            action=action,
            body=body,
            credentials=credentials,
            deadline_ns=operation_deadline,
            now=current,
        )
        request_ids[action] = cast(str, result["RequestId"])
        return result

    with _deadline_alarm(operation_deadline):
        provider = request("DescribeOIDCConfig", {"Name": provider_id})
        identity_key = provider.get("IdentityKey")
        if (
            provider.get("ProviderType") != 11
            or provider.get("Status") != 11
            or provider.get("Name") != provider_id
            or provider.get("IdentityUrl") != sts["issuer"]
            or provider.get("ClientId") != [sts["audience"]]
            or provider.get("AutoRotateKey") != 1
            or not isinstance(identity_key, str)
            or not identity_key
            or len(identity_key.encode()) > MAX_CAM_POLICY_BYTES
        ):
            raise TransferContractError("CAM OIDC provider readback is invalid")

        role = request("GetRole", {"RoleName": role_name})
        role_info = role.get("RoleInfo")
        if not isinstance(role_info, dict):
            raise TransferContractError("CAM role readback is invalid")
        role_info = cast(dict[str, object], role_info)
        role_id = role_info.get("RoleId")
        if (
            not isinstance(role_id, str)
            or not role_id.isdigit()
            or role_info.get("RoleName") != role_name
            or role_info.get("RoleArn") != role_arn
            or role_info.get("ConsoleLogin") != 0
            or role_info.get("RoleType") != "user"
            or role_info.get("SessionDuration") != sts["duration_seconds"]
        ):
            raise TransferContractError("CAM role readback is invalid")
        _validate_cam_oidc_trust(
            _cam_api_json(role_info.get("PolicyDocument"), "CAM role trust"),
            role_arn=role_arn,
            provider_id=provider_id,
            issuer=cast(str, sts["issuer"]),
            audience=cast(str, sts["audience"]),
            subject=(
                f"repo:{sts['github_repository']}:environment:{sts['environment']}"
            ),
        )

        attached = request(
            "ListAttachedRolePolicies",
            {"RoleId": role_id, "Page": 1, "Rp": 200},
        )
        policies = attached.get("List")
        if attached.get("TotalNum") != 1 or not isinstance(policies, list) or len(policies) != 1:
            raise TransferContractError("CAM attached policy set is invalid")
        policy = policies[0]
        if not isinstance(policy, dict):
            raise TransferContractError("CAM attached policy set is invalid")
        policy = cast(dict[str, object], policy)
        policy_id = policy.get("PolicyId")
        policy_name = policy.get("PolicyName")
        deactived = policy.get("Deactived")
        if (
            isinstance(policy_id, bool)
            or not isinstance(policy_id, int)
            or policy_id <= 0
            or not isinstance(policy_name, str)
            or not policy_name
            or policy.get("PolicyType") != "User"
            or isinstance(deactived, bool)
            or not isinstance(deactived, int)
            or deactived != 0
            or policy.get("DeactivedDetail") not in (None, [])
        ):
            raise TransferContractError("CAM attached policy set is invalid")

        versions_result = request("ListPolicyVersions", {"PolicyId": policy_id})
        versions = versions_result.get("Versions")
        if not isinstance(versions, list) or not versions:
            raise TransferContractError("CAM policy version set is invalid")
        version_ids: list[int] = []
        defaults: list[int] = []
        for item in versions:
            if not isinstance(item, dict):
                raise TransferContractError("CAM policy version set is invalid")
            version_id = item.get("VersionId")
            is_default = item.get("IsDefaultVersion")
            if (
                isinstance(version_id, bool)
                or not isinstance(version_id, int)
                or version_id <= 0
                or is_default not in (0, 1)
            ):
                raise TransferContractError("CAM policy version set is invalid")
            version_ids.append(version_id)
            if is_default == 1:
                defaults.append(version_id)
        if len(set(version_ids)) != len(version_ids) or len(defaults) != 1:
            raise TransferContractError("CAM policy version set is invalid")
        default_version = defaults[0]
        policy_version_result = request(
            "GetPolicyVersion",
            {"PolicyId": policy_id, "VersionId": default_version},
        )
        version = policy_version_result.get("PolicyVersion")
        if not isinstance(version, dict):
            raise TransferContractError("CAM effective policy version is invalid")
        version = cast(dict[str, object], version)
        if (
            version.get("VersionId") != default_version
            or version.get("IsDefaultVersion") != 1
        ):
            raise TransferContractError("CAM effective policy version is invalid")
        effective_policy = _cam_api_json(version.get("Document"), "CAM effective policy")
        normalized_policy = validate_cam_policy_readback(
            effective_policy,
            contract=validated,
            bucket=bucket,
            endpoint_host=endpoint_host,
            source_revision=source_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_attempt=workflow_run_attempt,
        )

        boundary = request("GetRolePermissionBoundary", {"RoleId": role_id})
        if any(
            boundary.get(field) not in (None, "")
            for field in (
                "PolicyId",
                "PolicyName",
                "PolicyDocument",
                "PolicyType",
                "CreateMode",
            )
        ):
            raise TransferContractError("CAM role permission boundary is unexpected")

    return {
        "schema_version": CAM_READBACK_RECEIPT_SCHEMA,
        "status": "passed",
        "source_revision": source_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "observed_at": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_endpoint": CAM_API_ENDPOINT,
        "provider_id": provider_id,
        "provider_key_sha256": hashlib.sha256(cast(str, identity_key).encode()).hexdigest(),
        "role_arn": role_arn,
        "role_id": role_id,
        "permission_boundary": "absent",
        "attached_policy": {
            "policy_id": policy_id,
            "policy_name": policy_name,
            "version_ids": sorted(version_ids),
            "default_version_id": default_version,
            "document_sha256": hashlib.sha256(
                canonical_json_bytes(normalized_policy)
            ).hexdigest(),
        },
        "request_ids": request_ids,
    }


def _artifact_names(source_revision: str) -> dict[str, str]:
    return {
        "source_archive": f"release-source-{source_revision}.tar.gz",
        "source_checksum": f"release-source-{source_revision}.tar.gz.sha256",
        "source_manifest": "source-manifest.v1.json",
        "image_archive": f"release-images-{source_revision}.tar.gz",
        "image_checksum": f"release-images-{source_revision}.tar.gz.sha256",
        "image_digests": "image-digests.txt",
    }


def _validate_detached_checksum(root: Path, archive_name: str, checksum_name: str) -> None:
    archive = _regular_file(root / archive_name, "release archive")
    checksum = _regular_file(root / checksum_name, "detached checksum")
    expected = f"{sha256_path(archive)}  {archive_name}\n"
    try:
        actual = checksum.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise TransferContractError("detached checksum is invalid") from exc
    if actual != expected:
        raise TransferContractError("detached checksum is invalid")


def _read_image_ids(path: Path) -> list[str]:
    _regular_file(path, "image digest file")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TransferContractError("image digest file is invalid") from exc
    if len(lines) != 3 or len(set(lines)) != 3 or any(
        not IMAGE_ID_RE.fullmatch(line) for line in lines
    ):
        raise TransferContractError("image digest set is invalid")
    return lines


def _validate_source_manifest_identity(path: Path, source_revision: str) -> None:
    _regular_file(path, "source manifest")
    try:
        payload = parse_json_bytes(path.read_bytes(), label="source manifest")
    except (OSError, TransferContractError) as exc:
        raise TransferContractError("source manifest is invalid") from exc
    manifest = _exact_dict(
        payload,
        {"schema_version", "git_sha", "files"},
        "source manifest",
    )
    if manifest["schema_version"] != "source-manifest.v1":
        raise TransferContractError("source manifest schema is invalid")
    if manifest["git_sha"] != source_revision:
        raise TransferContractError("source manifest revision is invalid")
    if not isinstance(manifest["files"], list):
        raise TransferContractError("source manifest file set is invalid")


def build_transfer_manifest(
    *,
    bundle_root: Path,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    github_artifact_id: int,
    github_artifact_digest: str,
    cos_bucket: str,
    cos_endpoint_host: str,
    created_at: str,
    expires_at: str,
) -> dict[str, object]:
    if not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("source revision is invalid")
    names = _artifact_names(source_revision)
    _validate_detached_checksum(
        bundle_root, names["source_archive"], names["source_checksum"]
    )
    _validate_detached_checksum(
        bundle_root, names["image_archive"], names["image_checksum"]
    )
    _validate_source_manifest_identity(bundle_root / names["source_manifest"], source_revision)
    image_ids = _read_image_ids(bundle_root / names["image_digests"])
    image_sha = sha256_path(bundle_root / names["image_archive"])
    prefix = f"ai-video/releases/{source_revision}/{image_sha}"

    payload: dict[str, object] = {
        "schema_version": TRANSFER_SCHEMA,
        "source_revision": source_revision,
        "workflow": {
            "run_id": workflow_run_id,
            "run_attempt": workflow_run_attempt,
            "artifact_id": github_artifact_id,
            "artifact_digest": github_artifact_digest,
        },
        "cos": {
            "bucket": cos_bucket,
            "endpoint_host": cos_endpoint_host,
            "object_prefix": prefix,
        },
        "created_at": created_at,
        "expires_at": expires_at,
        "files": [
            {
                "role": role,
                "path": names[role],
                "object_key": f"{prefix}/{names[role]}",
                "size_bytes": _regular_file(
                    bundle_root / names[role], "release transfer file"
                ).stat().st_size,
                "sha256": sha256_path(bundle_root / names[role]),
            }
            for role in FILE_ROLES
        ],
        "image_ids": image_ids,
        "manifest_object_key": (
            f"{prefix}/transactions/{workflow_run_id}/{workflow_run_attempt}/"
            "release-transfer-manifest.v1.json"
        ),
        "policy": dict(POLICY),
    }
    return validate_transfer_manifest(payload, bundle_root=bundle_root)


def validate_transfer_manifest(
    payload: object,
    *,
    bundle_root: Path | None = None,
) -> dict[str, object]:
    manifest = _exact_dict(
        payload,
        {
            "schema_version",
            "source_revision",
            "workflow",
            "cos",
            "created_at",
            "expires_at",
            "files",
            "image_ids",
            "manifest_object_key",
            "policy",
        },
        "transfer manifest",
    )
    if manifest["schema_version"] != TRANSFER_SCHEMA:
        raise TransferContractError("transfer manifest schema is invalid")
    source_revision = manifest["source_revision"]
    if not isinstance(source_revision, str) or not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("source revision is invalid")

    workflow = _exact_dict(
        manifest["workflow"],
        {"run_id", "run_attempt", "artifact_id", "artifact_digest"},
        "workflow identity",
    )
    _positive_int(workflow["run_id"], "workflow run ID")
    _positive_int(workflow["run_attempt"], "workflow run attempt")
    _positive_int(workflow["artifact_id"], "GitHub artifact ID")
    artifact_digest = workflow["artifact_digest"]
    if not isinstance(artifact_digest, str) or not ARTIFACT_DIGEST_RE.fullmatch(
        artifact_digest
    ):
        raise TransferContractError("GitHub artifact digest is invalid")

    cos = _exact_dict(
        manifest["cos"],
        {"bucket", "endpoint_host", "object_prefix"},
        "COS identity",
    )
    bucket = cos["bucket"]
    endpoint = cos["endpoint_host"]
    if not isinstance(bucket, str) or not isinstance(endpoint, str):
        raise TransferContractError("COS identity is invalid")
    cos_object_host(bucket, endpoint)

    created = _parse_utc(manifest["created_at"], "creation timestamp")
    expires = _parse_utc(manifest["expires_at"], "expiry timestamp")
    validity = int((expires - created).total_seconds())
    if validity <= 0 or validity > MAX_VALIDITY_SECONDS:
        raise TransferContractError("transfer expiry is outside the allowed window")

    raw_files = manifest["files"]
    if not isinstance(raw_files, list) or len(raw_files) != len(FILE_ROLES):
        raise TransferContractError("transfer file set is invalid")
    names = _artifact_names(source_revision)
    validated_files: list[dict[str, object]] = []
    roles: list[str] = []
    image_sha: str | None = None
    for raw_entry in raw_files:
        entry = _exact_dict(
            raw_entry,
            {"role", "path", "object_key", "size_bytes", "sha256"},
            "transfer file",
        )
        role = entry["role"]
        path = entry["path"]
        digest = entry["sha256"]
        if not isinstance(role, str) or role not in FILE_ROLES:
            raise TransferContractError("transfer file role is invalid")
        if path != names[role]:
            raise TransferContractError("transfer file path is invalid")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise TransferContractError("transfer file checksum is invalid")
        size = _positive_int(entry["size_bytes"], "transfer file size")
        if size > MAX_FILE_BYTES[role]:
            raise TransferContractError("transfer file size exceeds the role limit")
        roles.append(role)
        if role == "image_archive":
            image_sha = digest
        validated_files.append(
            {
                "role": role,
                "path": path,
                "object_key": entry["object_key"],
                "size_bytes": size,
                "sha256": digest,
            }
        )
    if tuple(roles) != FILE_ROLES:
        raise TransferContractError("transfer file order is invalid")
    assert image_sha is not None
    expected_prefix = f"ai-video/releases/{source_revision}/{image_sha}"
    if cos["object_prefix"] != expected_prefix:
        raise TransferContractError("COS object prefix is invalid")
    for entry in validated_files:
        if entry["object_key"] != f"{expected_prefix}/{entry['path']}":
            raise TransferContractError("transfer object key is invalid")
    expected_manifest_key = (
        f"{expected_prefix}/transactions/{workflow['run_id']}/"
        f"{workflow['run_attempt']}/release-transfer-manifest.v1.json"
    )
    if manifest["manifest_object_key"] != expected_manifest_key:
        raise TransferContractError("transfer manifest object key is invalid")

    image_ids = manifest["image_ids"]
    if (
        not isinstance(image_ids, list)
        or len(image_ids) != 3
        or len(set(cast(list[str], image_ids))) != 3
        or any(not isinstance(item, str) or not IMAGE_ID_RE.fullmatch(item) for item in image_ids)
    ):
        raise TransferContractError("image digest set is invalid")
    if manifest["policy"] != POLICY:
        raise TransferContractError("transfer policy is invalid")

    if bundle_root is not None:
        _validate_detached_checksum(
            bundle_root, names["source_archive"], names["source_checksum"]
        )
        _validate_detached_checksum(
            bundle_root, names["image_archive"], names["image_checksum"]
        )
        _validate_source_manifest_identity(
            bundle_root / names["source_manifest"], source_revision
        )
        if _read_image_ids(bundle_root / names["image_digests"]) != image_ids:
            raise TransferContractError("image digest set is inconsistent")
        for entry in validated_files:
            path = _regular_file(
                bundle_root / cast(str, entry["path"]), "release transfer file"
            )
            if path.stat().st_size != entry["size_bytes"] or sha256_path(path) != entry[
                "sha256"
            ]:
                raise TransferContractError("release transfer checksum or size mismatch")

    canonical = {
        "schema_version": TRANSFER_SCHEMA,
        "source_revision": source_revision,
        "workflow": workflow,
        "cos": cos,
        "created_at": manifest["created_at"],
        "expires_at": manifest["expires_at"],
        "files": validated_files,
        "image_ids": image_ids,
        "manifest_object_key": manifest["manifest_object_key"],
        "policy": dict(POLICY),
    }
    if len(canonical_json_bytes(canonical)) > MAX_MANIFEST_BYTES:
        raise TransferContractError("transfer manifest exceeds the size limit")
    return canonical


def evaluate_probe(
    *,
    transferred_bytes: int,
    elapsed_nanoseconds: int,
    release_bytes: int,
    min_bytes_per_second: int = MIN_BYTES_PER_SECOND,
    max_estimated_seconds: int = MAX_ESTIMATED_SECONDS,
) -> dict[str, object]:
    if transferred_bytes != PROBE_SIZE_BYTES:
        raise TransferContractError("probe size is invalid")
    if isinstance(elapsed_nanoseconds, bool) or elapsed_nanoseconds <= 0:
        raise TransferContractError("probe duration is invalid")
    _positive_int(release_bytes, "release size")
    _positive_int(min_bytes_per_second, "minimum throughput")
    _positive_int(max_estimated_seconds, "maximum estimated duration")
    bytes_per_second = (transferred_bytes * 1_000_000_000) // elapsed_nanoseconds
    if bytes_per_second < min_bytes_per_second:
        raise TransferContractError("probe throughput is below the release gate")
    estimated = math.ceil(release_bytes / bytes_per_second)
    if estimated > max_estimated_seconds:
        raise TransferContractError("estimated duration exceeds the release gate")
    return {
        "status": "passed",
        "transferred_bytes": transferred_bytes,
        "elapsed_nanoseconds": elapsed_nanoseconds,
        "bytes_per_second": bytes_per_second,
        "estimated_release_seconds": estimated,
    }


def build_transfer_receipt(
    *,
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    manifest_sha256: str,
    incoming_directory: str,
    completed_at: str,
    expires_at: str,
    probe: dict[str, object],
    manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA,
        "state": "verified",
        "source_revision": source_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "manifest_sha256": manifest_sha256,
        "incoming_directory": incoming_directory,
        "completed_at": completed_at,
        "expires_at": expires_at,
        "probe": probe,
        "policy": dict(POLICY),
    }
    return validate_transfer_receipt(payload, manifest=manifest)


def validate_transfer_receipt(
    payload: object,
    *,
    manifest: dict[str, object] | None = None,
    expected_source_revision: str | None = None,
    expected_workflow_run_id: int | None = None,
    expected_workflow_run_attempt: int | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, object]:
    receipt = _exact_dict(
        payload,
        {
            "schema_version",
            "state",
            "source_revision",
            "workflow_run_id",
            "workflow_run_attempt",
            "manifest_sha256",
            "incoming_directory",
            "completed_at",
            "expires_at",
            "probe",
            "policy",
        },
        "transfer receipt",
    )
    if receipt["schema_version"] != RECEIPT_SCHEMA:
        raise TransferContractError("transfer receipt schema is invalid")
    if receipt["state"] != "verified":
        raise TransferContractError("transfer receipt state is invalid")
    source_revision = receipt["source_revision"]
    if not isinstance(source_revision, str) or not GIT_SHA_RE.fullmatch(source_revision):
        raise TransferContractError("receipt source revision is invalid")
    run_id = _positive_int(receipt["workflow_run_id"], "receipt run ID")
    run_attempt = _positive_int(receipt["workflow_run_attempt"], "receipt run attempt")
    manifest_sha = receipt["manifest_sha256"]
    if not isinstance(manifest_sha, str) or not SHA256_RE.fullmatch(manifest_sha):
        raise TransferContractError("receipt manifest checksum is invalid")
    expected_incoming = f".incoming-{source_revision}-{run_id}-{run_attempt}"
    if receipt["incoming_directory"] != expected_incoming:
        raise TransferContractError("receipt incoming directory is invalid")
    completed = _parse_utc(receipt["completed_at"], "receipt completion timestamp")
    expires = _parse_utc(receipt["expires_at"], "receipt expiry timestamp")
    if expires <= completed or int((expires - completed).total_seconds()) > MAX_VALIDITY_SECONDS:
        raise TransferContractError("receipt expiry is invalid")
    probe = _exact_dict(
        receipt["probe"],
        {
            "status",
            "transferred_bytes",
            "elapsed_nanoseconds",
            "bytes_per_second",
            "estimated_release_seconds",
        },
        "probe receipt",
    )
    if probe["status"] != "passed" or probe["transferred_bytes"] != PROBE_SIZE_BYTES:
        raise TransferContractError("probe receipt status is invalid")
    for key in (
        "elapsed_nanoseconds",
        "bytes_per_second",
        "estimated_release_seconds",
    ):
        _positive_int(probe[key], f"probe {key}")
    expected_bps = (
        cast(int, probe["transferred_bytes"]) * 1_000_000_000
    ) // cast(int, probe["elapsed_nanoseconds"])
    if probe["bytes_per_second"] != expected_bps:
        raise TransferContractError("probe receipt conservation is invalid")
    if expected_source_revision is not None and source_revision != expected_source_revision:
        raise TransferContractError("receipt source revision is inconsistent")
    if expected_workflow_run_id is not None and run_id != expected_workflow_run_id:
        raise TransferContractError("receipt run ID is inconsistent")
    if expected_workflow_run_attempt is not None and run_attempt != expected_workflow_run_attempt:
        raise TransferContractError("receipt run attempt is inconsistent")
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise TransferContractError("receipt manifest checksum is inconsistent")
    if manifest is not None:
        validated_manifest = validate_transfer_manifest(manifest)
        canonical_manifest_sha = hashlib.sha256(
            canonical_json_bytes(validated_manifest)
        ).hexdigest()
        if manifest_sha != canonical_manifest_sha:
            raise TransferContractError("receipt manifest checksum is inconsistent")
        workflow = cast(dict[str, object], validated_manifest["workflow"])
        files = cast(list[dict[str, object]], validated_manifest["files"])
        if (
            source_revision != validated_manifest["source_revision"]
            or run_id != workflow["run_id"]
            or run_attempt != workflow["run_attempt"]
            or receipt["expires_at"] != validated_manifest["expires_at"]
        ):
            raise TransferContractError("receipt identity is inconsistent with manifest")
        created = _parse_utc(validated_manifest["created_at"], "creation timestamp")
        if completed < created:
            raise TransferContractError("receipt completion timestamp is inconsistent")
        release_bytes = sum(cast(int, entry["size_bytes"]) for entry in files) + len(
            canonical_json_bytes(validated_manifest)
        )
        expected_probe = evaluate_probe(
            transferred_bytes=cast(int, probe["transferred_bytes"]),
            elapsed_nanoseconds=cast(int, probe["elapsed_nanoseconds"]),
            release_bytes=release_bytes,
        )
        if probe != expected_probe:
            raise TransferContractError("probe receipt conservation is invalid")
    if receipt["policy"] != POLICY:
        raise TransferContractError("receipt policy is invalid")
    canonical = {
        "schema_version": RECEIPT_SCHEMA,
        "state": "verified",
        "source_revision": source_revision,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "manifest_sha256": manifest_sha,
        "incoming_directory": expected_incoming,
        "completed_at": receipt["completed_at"],
        "expires_at": receipt["expires_at"],
        "probe": probe,
        "policy": dict(POLICY),
    }
    encoded = canonical_json_bytes(canonical)
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise TransferContractError("transfer receipt exceeds the size limit")
    lowered = encoded.lower()
    if any(value in lowered for value in (b"https://", b"secret", b"token", b"/home/runner")):
        raise TransferContractError("transfer receipt contains forbidden material")
    return canonical


def load_canonical_manifest(path: Path, *, bundle_root: Path | None = None) -> dict[str, object]:
    _regular_file(path, "transfer manifest")
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise TransferContractError("transfer manifest exceeds the size limit")
        payload = parse_json_bytes(raw, label="transfer manifest")
    except (OSError, TransferContractError) as exc:
        raise TransferContractError("transfer manifest is not valid JSON") from exc
    validated = validate_transfer_manifest(payload, bundle_root=bundle_root)
    if raw != canonical_json_bytes(validated):
        raise TransferContractError("transfer manifest serialization is not canonical")
    return validated


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor: int | None = None
    stream = None
    created_identity: tuple[int, int] | None = None
    try:
        with _blocked_output_commit_signals():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            facts = os.fstat(descriptor)
            created_identity = (facts.st_dev, facts.st_ino)
            stream = os.fdopen(descriptor, "wb")
            descriptor = None
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, TransferContractError, KeyboardInterrupt, SystemExit) as exc:
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
        if created_identity is not None:
            try:
                _cleanup_created_output(path, created_identity)
            except TransferContractError as cleanup_exc:
                raise TransferContractError(
                    "release transfer output cleanup requires manual recovery"
                ) from cleanup_exc
        if isinstance(exc, TransferContractError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise TransferContractError("release transfer interrupted") from exc
        raise TransferContractError("release transfer output already exists or is unsafe") from exc


def _cleanup_created_output(
    path: Path,
    created_identity: tuple[int, int],
) -> None:
    quarantine: Path | None = None
    for _ in range(4):
        candidate = path.parent / f".release-cleanup-{secrets.token_hex(16)}"
        try:
            with _blocked_output_commit_signals():
                os.mkdir(candidate, 0o700)
                quarantine = candidate
            break
        except FileExistsError:
            continue
        except (OSError, KeyboardInterrupt, SystemExit) as exc:
            if quarantine is not None:
                try:
                    quarantine.rmdir()
                except OSError:
                    pass
            raise TransferContractError(
                "release transfer output cleanup requires manual recovery"
            ) from exc
    if quarantine is None:
        raise TransferContractError(
            "release transfer output cleanup requires manual recovery"
        )
    isolated = quarantine / "owned"
    try:
        os.rename(path, isolated)
    except (OSError, KeyboardInterrupt, SystemExit) as exc:
        try:
            quarantine.rmdir()
        except OSError:
            pass
        raise TransferContractError(
            "release transfer output cleanup requires manual recovery"
        ) from exc
    try:
        facts = isolated.lstat()
        if (
            not stat.S_ISREG(facts.st_mode)
            or isolated.is_symlink()
            or facts.st_uid != os.geteuid()
            or facts.st_nlink != 1
            or (facts.st_dev, facts.st_ino) != created_identity
        ):
            raise TransferContractError(
                "release transfer output cleanup requires manual recovery"
            )
        isolated.unlink()
        quarantine.rmdir()
    except (OSError, TransferContractError, KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, TransferContractError):
            raise
        raise TransferContractError(
            "release transfer output cleanup requires manual recovery"
        ) from exc


def _load_sts_credentials(path: Path) -> dict[str, object]:
    payload = parse_json_bytes(
        _read_bounded_regular_file(
            path,
            label="COS STS credential file",
            maximum_bytes=MAX_STS_CREDENTIAL_BYTES,
            allowed_modes={0o600},
        ),
        label="COS STS credential file",
    )
    document = _exact_dict(
        payload,
        {
            "schema_version",
            "source_revision",
            "workflow_run_id",
            "workflow_run_attempt",
            "provider_id",
            "role_arn",
            "duration_seconds",
            "expiration",
            "expired_time",
            "request_id",
            "credentials",
        },
        "COS STS credential file",
    )
    credentials = _exact_dict(
        document["credentials"],
        {"secret_id", "secret_key", "session_token"},
        "COS STS credential file",
    )
    values = [credentials["secret_id"], credentials["secret_key"], credentials["session_token"]]
    expiration = _parse_utc(document["expiration"], "COS STS credential expiration")
    source_revision = document["source_revision"]
    provider_id = document["provider_id"]
    role_arn = document["role_arn"]
    request_id = document["request_id"]
    if (
        document["schema_version"] != "cos-sts-credentials.v1"
        or not isinstance(source_revision, str)
        or not GIT_SHA_RE.fullmatch(source_revision)
        or isinstance(document["workflow_run_id"], bool)
        or not isinstance(document["workflow_run_id"], int)
        or cast(int, document["workflow_run_id"]) <= 0
        or isinstance(document["workflow_run_attempt"], bool)
        or not isinstance(document["workflow_run_attempt"], int)
        or cast(int, document["workflow_run_attempt"]) <= 0
        or not isinstance(provider_id, str)
        or not OIDC_PROVIDER_RE.fullmatch(provider_id)
        or not isinstance(role_arn, str)
        or not ROLE_ARN_RE.fullmatch(role_arn)
        or document["duration_seconds"] != MAX_VALIDITY_SECONDS
        or isinstance(document["expired_time"], bool)
        or not isinstance(document["expired_time"], int)
        or int(expiration.timestamp()) != document["expired_time"]
        or expiration <= datetime.now(UTC)
        or not isinstance(request_id, str)
        or not REQUEST_ID_RE.fullmatch(request_id)
        or any(not isinstance(value, str) or not value or "\n" in value or "\r" in value for value in values)
    ):
        raise TransferContractError("COS STS credential file is invalid")
    return document


def validate_sts_credentials_file(
    *,
    path: Path,
    contract: dict[str, object],
    source_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    provider_id: str,
    role_arn: str,
    now: datetime | None = None,
) -> dict[str, int | str]:
    document = _load_sts_credentials(path)
    if (
        document["source_revision"] != source_revision
        or document["workflow_run_id"] != workflow_run_id
        or document["workflow_run_attempt"] != workflow_run_attempt
        or document["provider_id"] != provider_id
        or document["role_arn"] != role_arn
    ):
        raise TransferContractError("COS STS credential identity is invalid")
    return validate_sts_window(
        duration_seconds=cast(int, document["duration_seconds"]),
        expires_at=cast(str, document["expiration"]),
        contract=contract,
        now=now,
    )


def _credentials() -> tuple[str, str, str]:
    raw_path = os.environ.get("COS_STS_CREDENTIALS_FILE", "")
    if not raw_path or "\n" in raw_path or "\r" in raw_path:
        raise TransferContractError("COS STS credential file is missing")
    document = _load_sts_credentials(Path(raw_path))
    credentials = cast(dict[str, object], document["credentials"])
    return (
        cast(str, credentials["secret_id"]),
        cast(str, credentials["secret_key"]),
        cast(str, credentials["session_token"]),
    )


def _quote(value: str, *, safe: str = "-_.~") -> str:
    return urllib.parse.quote(value, safe=safe)


def _canonical_pairs(values: dict[str, str]) -> tuple[str, str]:
    encoded = [(_quote(key).lower(), _quote(value)) for key, value in values.items()]
    encoded.sort()
    return (
        "&".join(f"{key}={value}" for key, value in encoded),
        ";".join(key for key, _ in encoded),
    )


def _cos_authorization(
    *,
    method: str,
    path: str,
    query: dict[str, str],
    headers: dict[str, str],
    secret_id: str,
    secret_key: str,
    now: int | None = None,
    validity_seconds: int = COS_AUTH_VALIDITY_SECONDS,
) -> str:
    if validity_seconds <= 0 or validity_seconds > MAX_VALIDITY_SECONDS:
        raise TransferContractError("COS signature validity is invalid")
    timestamp = int(time.time()) if now is None else now
    key_time = f"{timestamp - 60};{timestamp + validity_seconds}"
    signed_headers = {
        key.lower(): value.strip()
        for key, value in headers.items()
        if key.lower() == "host"
        or key.lower().startswith("x-cos-")
        or key.lower()
        in {
            "cache-control",
            "content-disposition",
            "content-encoding",
            "content-type",
            "content-md5",
            "content-length",
            "expect",
            "expires",
            "if-match",
            "if-modified-since",
            "if-none-match",
            "if-unmodified-since",
            "origin",
            "range",
            "transfer-encoding",
        }
    }
    canonical_query, query_list = _canonical_pairs(query)
    canonical_headers, header_list = _canonical_pairs(signed_headers)
    canonical_path = _quote(path, safe="/-_.~")
    request_text = (
        f"{method.lower()}\n{canonical_path}\n{canonical_query}\n"
        f"{canonical_headers}\n"
    )
    string_to_sign = (
        f"sha1\n{key_time}\n"
        f"{hashlib.sha1(request_text.encode()).hexdigest()}\n"
    )
    sign_key = hmac.new(secret_key.encode(), key_time.encode(), hashlib.sha1).hexdigest()
    signature = hmac.new(
        sign_key.encode(), string_to_sign.encode(), hashlib.sha1
    ).hexdigest()
    return "&".join(
        (
            "q-sign-algorithm=sha1",
            f"q-ak={secret_id}",
            f"q-sign-time={key_time}",
            f"q-key-time={key_time}",
            f"q-header-list={header_list}",
            f"q-url-param-list={query_list}",
            f"q-signature={signature}",
        )
    )


def _cos_url(host: str, object_key: str, query: dict[str, str]) -> str:
    path = "/" + _quote(object_key, safe="/-_.~") if object_key else "/"
    suffix = urllib.parse.urlencode(query, quote_via=urllib.parse.quote, safe="-_.~")
    return f"https://{host}{path}" + (f"?{suffix}" if suffix else "")


def _open_no_redirect(request: urllib.request.Request, *, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def _read_bounded(
    response,
    *,
    deadline_ns: int,
    maximum_bytes: int = COS_RESPONSE_LIMIT_BYTES,
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        _remaining_timeout(deadline_ns, MAX_ESTIMATED_SECONDS)
        chunk = response.read(min(64 * 1024, maximum_bytes + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > maximum_bytes:
            raise TransferContractError("COS response exceeds its size limit")
    return b"".join(chunks)


def _cos_request(
    *,
    method: str,
    bucket: str,
    endpoint_host: str,
    object_key: str = "",
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected_status: set[int],
    timeout: int = 120,
    deadline_ns: int | None = None,
) -> tuple[bytes, dict[str, str], int]:
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    secret_id, secret_key, session_token = _credentials()
    host = cos_object_host(bucket, endpoint_host)
    request_query = {} if query is None else dict(query)
    request_headers = {} if headers is None else dict(headers)
    request_headers["host"] = host
    request_headers["x-cos-security-token"] = session_token
    if body is not None:
        request_headers["content-length"] = str(len(body))
    path = "/" + object_key if object_key else "/"
    request_headers["Authorization"] = _cos_authorization(
        method=method,
        path=path,
        query=request_query,
        headers=request_headers,
        secret_id=secret_id,
        secret_key=secret_key,
    )
    request = urllib.request.Request(
        _cos_url(host, object_key, request_query),
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with _open_no_redirect(
            request,
            timeout=_remaining_timeout(operation_deadline, timeout),
        ) as response:
            if response.status not in expected_status:
                raise TransferContractError("COS request returned an unexpected status")
            payload = _read_bounded(response, deadline_ns=operation_deadline)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return payload, response_headers, response.status
    except urllib.error.HTTPError as exc:
        if exc.code in expected_status:
            try:
                payload = _read_bounded(exc, deadline_ns=operation_deadline)
                response_headers = {
                    key.lower(): value for key, value in exc.headers.items()
                }
                return payload, response_headers, exc.code
            except (OSError, TimeoutError, http.client.HTTPException) as read_exc:
                raise TransferContractError("COS request failed") from read_exc
        raise TransferContractError("COS request failed") from None
    except (OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise TransferContractError("COS request failed") from exc


def verify_bucket_never_versioned(
    *,
    bucket: str,
    endpoint_host: str,
    deadline_ns: int | None = None,
) -> None:
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    with _deadline_alarm(operation_deadline):
        payload, _, _ = _cos_request(
            method="GET",
            bucket=bucket,
            endpoint_host=endpoint_host,
            query={"versioning": ""},
            expected_status={200},
            timeout=30,
            deadline_ns=operation_deadline,
        )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise TransferContractError("COS bucket versioning response is invalid") from exc
    if root.tag.rsplit("}", 1)[-1] != "VersioningConfiguration" or list(root):
        raise TransferContractError("COS bucket must have never enabled versioning")


def _xml_children_are(parent: ET.Element, names: list[str]) -> bool:
    return [_xml_local_name(child) for child in parent] == names


def normalize_private_bucket_acl(payload: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, RecursionError) as exc:
        raise TransferContractError("COS bucket ACL readback is invalid") from exc
    if _xml_local_name(root) != "AccessControlPolicy" or not _xml_children_are(
        root, ["Owner", "AccessControlList"]
    ):
        raise TransferContractError("COS bucket ACL readback is invalid")
    owner, access_list = list(root)
    if not _xml_children_are(owner, ["ID", "DisplayName"]):
        raise TransferContractError("COS bucket ACL readback is invalid")
    owner_id = (owner[0].text or "").strip()
    owner_display = (owner[1].text or "").strip()
    match = re.fullmatch(r"qcs::cam::uin/([1-9][0-9]{4,19}):uin/\1", owner_id)
    if match is None or not owner_display:
        raise TransferContractError("COS bucket ACL readback is invalid")
    if not _xml_children_are(access_list, ["Grant"]):
        raise TransferContractError("COS bucket ACL must be private")
    grant = access_list[0]
    if not _xml_children_are(grant, ["Grantee", "Permission"]):
        raise TransferContractError("COS bucket ACL must be private")
    grantee, permission = list(grant)
    xsi_type = grantee.attrib.get(
        "{http://www.w3.org/2001/XMLSchema-instance}type", ""
    )
    if (
        set(grantee.attrib)
        != {"{http://www.w3.org/2001/XMLSchema-instance}type"}
        or xsi_type != "CanonicalUser"
        or not _xml_children_are(grantee, ["ID", "DisplayName"])
        or (grantee[0].text or "").strip() != owner_id
        or not (grantee[1].text or "").strip()
        or (permission.text or "").strip() != "FULL_CONTROL"
    ):
        raise TransferContractError("COS bucket ACL must be private")
    return {"acl": "owner-full-control-only", "owner_id": owner_id}


def _is_no_bucket_policy_error(payload: bytes) -> bool:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, RecursionError):
        return False
    codes = [
        (child.text or "").strip()
        for child in root
        if _xml_local_name(child) == "Code"
    ]
    return _xml_local_name(root) == "Error" and codes == ["NoSuchBucketPolicy"]


def verify_bucket_privacy_governance(
    *,
    bucket: str,
    endpoint_host: str,
    contract: dict[str, object],
    deadline_ns: int | None = None,
) -> dict[str, str]:
    validated = validate_release_governance_contract(contract)
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    with _deadline_alarm(operation_deadline):
        acl_payload, _, _ = _cos_request(
            method="GET",
            bucket=bucket,
            endpoint_host=endpoint_host,
            query={"acl": ""},
            expected_status={200},
            timeout=30,
            deadline_ns=operation_deadline,
        )
        normalized = normalize_private_bucket_acl(acl_payload)
        policy_payload, _, policy_status = _cos_request(
            method="GET",
            bucket=bucket,
            endpoint_host=endpoint_host,
            query={"policy": ""},
            expected_status={200, 404},
            timeout=30,
            deadline_ns=operation_deadline,
        )
    if policy_status != 404 or not _is_no_bucket_policy_error(policy_payload):
        raise TransferContractError("COS bucket policy must be absent")
    privacy = cast(dict[str, object], validated["privacy"])
    if normalized["acl"] != privacy["acl"] or privacy["bucket_policy"] != "absent":
        raise TransferContractError("COS bucket privacy does not match the contract")
    return {
        "acl": "owner-full-control-only",
        "bucket_policy": "absent",
        "owner_id": normalized["owner_id"],
    }


def _xml_local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml_exact_child(parent: ET.Element, name: str) -> ET.Element:
    matches = [child for child in parent if _xml_local_name(child) == name]
    if len(matches) != 1:
        raise TransferContractError("COS lifecycle readback is invalid")
    return matches[0]


def _xml_positive_int(parent: ET.Element, name: str) -> int:
    raw = (_xml_exact_child(parent, name).text or "").strip()
    if not raw.isascii() or not raw.isdigit():
        raise TransferContractError("COS lifecycle readback is invalid")
    return _positive_int(int(raw), "COS lifecycle interval")


def normalize_bucket_lifecycle(payload: bytes) -> list[dict[str, object]]:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, RecursionError) as exc:
        raise TransferContractError("COS lifecycle readback is invalid") from exc
    if _xml_local_name(root) != "LifecycleConfiguration":
        raise TransferContractError("COS lifecycle readback is invalid")
    rules: list[dict[str, object]] = []
    for rule in root:
        if _xml_local_name(rule) != "Rule":
            raise TransferContractError("COS lifecycle readback is invalid")
        child_names = [_xml_local_name(child) for child in rule]
        if len(child_names) != len(set(child_names)) or not set(child_names) <= {
            "ID",
            "Filter",
            "Status",
            "Expiration",
            "AbortIncompleteMultipartUpload",
        }:
            raise TransferContractError("COS lifecycle readback is invalid")
        identifier = (_xml_exact_child(rule, "ID").text or "").strip()
        status = (_xml_exact_child(rule, "Status").text or "").strip()
        filter_element = _xml_exact_child(rule, "Filter")
        if [_xml_local_name(child) for child in filter_element] != ["Prefix"]:
            raise TransferContractError("COS lifecycle readback is invalid")
        prefix = (_xml_exact_child(filter_element, "Prefix").text or "").strip()
        expiration_nodes = [
            child for child in rule if _xml_local_name(child) == "Expiration"
        ]
        abort_nodes = [
            child
            for child in rule
            if _xml_local_name(child) == "AbortIncompleteMultipartUpload"
        ]
        if len(expiration_nodes) + len(abort_nodes) != 1:
            raise TransferContractError("COS lifecycle readback is invalid")
        if expiration_nodes and [
            _xml_local_name(child) for child in expiration_nodes[0]
        ] != ["Days"]:
            raise TransferContractError("COS lifecycle readback is invalid")
        if abort_nodes and [
            _xml_local_name(child) for child in abort_nodes[0]
        ] != ["DaysAfterInitiation"]:
            raise TransferContractError("COS lifecycle readback is invalid")
        expiration_days = (
            _xml_positive_int(expiration_nodes[0], "Days")
            if expiration_nodes
            else None
        )
        abort_days = (
            _xml_positive_int(abort_nodes[0], "DaysAfterInitiation")
            if abort_nodes
            else None
        )
        if not identifier or not prefix or status != "Enabled":
            raise TransferContractError("COS lifecycle readback is invalid")
        rules.append(
            {
                "id": identifier,
                "prefix": prefix,
                "status": status,
                "expiration_days": expiration_days,
                "abort_incomplete_multipart_upload_days": abort_days,
            }
        )
    rules.sort(key=lambda item: cast(str, item["id"]))
    return rules


def verify_bucket_lifecycle_governance(
    *,
    bucket: str,
    endpoint_host: str,
    contract: dict[str, object],
    deadline_ns: int | None = None,
) -> list[dict[str, object]]:
    validated = validate_release_governance_contract(contract)
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    with _deadline_alarm(operation_deadline):
        payload, _, _ = _cos_request(
            method="GET",
            bucket=bucket,
            endpoint_host=endpoint_host,
            query={"lifecycle": ""},
            expected_status={200},
            timeout=30,
            deadline_ns=operation_deadline,
        )
    rules = normalize_bucket_lifecycle(payload)
    expected = list(
        cast(list[dict[str, object]], cast(dict[str, object], validated["lifecycle"])["rules"])
    )
    expected.sort(key=lambda item: cast(str, item["id"]))
    if rules != expected:
        raise TransferContractError("COS lifecycle readback does not match the contract")
    return rules


def _upload_simple(
    *,
    path: Path,
    bucket: str,
    endpoint_host: str,
    object_key: str,
    sha256: str,
    deadline_ns: int,
) -> int:
    data = path.read_bytes()
    started = time.monotonic_ns()
    _cos_request(
        method="PUT",
        bucket=bucket,
        endpoint_host=endpoint_host,
        object_key=object_key,
        headers={
            "content-md5": base64.b64encode(
                hashlib.md5(data, usedforsecurity=False).digest()
            ).decode(),
            "x-cos-forbid-overwrite": "true",
            "x-cos-meta-ai-video-sha256": sha256,
            "x-cos-meta-ai-video-size": str(len(data)),
        },
        body=data,
        expected_status={200},
        deadline_ns=deadline_ns,
    )
    return time.monotonic_ns() - started


def _xml_value(payload: bytes, name: str) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise TransferContractError("COS multipart response is invalid") from exc
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name and element.text:
            return element.text
    raise TransferContractError("COS multipart response is invalid")


def _upload_multipart(
    *,
    path: Path,
    bucket: str,
    endpoint_host: str,
    object_key: str,
    sha256: str,
    deadline_ns: int,
) -> int:
    create_payload, _, _ = _cos_request(
        method="POST",
        bucket=bucket,
        endpoint_host=endpoint_host,
        object_key=object_key,
        query={"uploads": ""},
        headers={
            "x-cos-forbid-overwrite": "true",
            "x-cos-meta-ai-video-sha256": sha256,
            "x-cos-meta-ai-video-size": str(path.stat().st_size),
        },
        body=b"",
        expected_status={200},
        deadline_ns=deadline_ns,
    )
    upload_id = _xml_value(create_payload, "UploadId")
    parts: list[tuple[int, str]] = []
    started = time.monotonic_ns()
    try:
        with path.open("rb") as stream:
            part_number = 1
            while chunk := stream.read(COS_PART_SIZE_BYTES):
                _, response_headers, _ = _cos_request(
                    method="PUT",
                    bucket=bucket,
                    endpoint_host=endpoint_host,
                    object_key=object_key,
                    query={"partNumber": str(part_number), "uploadId": upload_id},
                    headers={
                        "content-md5": base64.b64encode(
                            hashlib.md5(chunk, usedforsecurity=False).digest()
                        ).decode()
                    },
                    body=chunk,
                    expected_status={200},
                    deadline_ns=deadline_ns,
                )
                etag = response_headers.get("etag", "")
                if not re.fullmatch(r'"[0-9a-fA-F-]{16,128}"', etag):
                    raise TransferContractError("COS multipart ETag is invalid")
                parts.append((part_number, etag))
                part_number += 1
        complete = ET.Element("CompleteMultipartUpload")
        for number, etag in parts:
            item = ET.SubElement(complete, "Part")
            ET.SubElement(item, "PartNumber").text = str(number)
            ET.SubElement(item, "ETag").text = etag
        complete_payload, _, _ = _cos_request(
            method="POST",
            bucket=bucket,
            endpoint_host=endpoint_host,
            object_key=object_key,
            query={"uploadId": upload_id},
            headers={
                "content-type": "application/xml",
                "x-cos-forbid-overwrite": "true",
            },
            body=ET.tostring(complete, encoding="utf-8", xml_declaration=False),
            expected_status={200},
            timeout=MAX_ESTIMATED_SECONDS,
            deadline_ns=deadline_ns,
        )
        if ET.fromstring(complete_payload).tag.rsplit("}", 1)[-1] == "Error":
            raise TransferContractError("COS multipart completion failed")
    except (
        OSError,
        ET.ParseError,
        TransferContractError,
        KeyboardInterrupt,
        SystemExit,
    ) as exc:
        try:
            cleanup_deadline = time.monotonic_ns() + 30 * 1_000_000_000
            _cos_request(
                method="DELETE",
                bucket=bucket,
                endpoint_host=endpoint_host,
                object_key=object_key,
                query={"uploadId": upload_id},
                expected_status={204},
                timeout=30,
                deadline_ns=cleanup_deadline,
            )
        except TransferContractError:
            raise TransferContractError(
                "COS multipart upload failed and abort requires manual recovery"
            ) from exc
        if isinstance(exc, TransferContractError):
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise TransferContractError("COS multipart upload was interrupted") from exc
        raise TransferContractError("COS multipart upload failed") from exc
    return time.monotonic_ns() - started


def upload_object_once(
    *,
    path: Path,
    bucket: str,
    endpoint_host: str,
    object_key: str,
    expected_sha256: str,
    expected_size: int,
    deadline_ns: int | None = None,
) -> int:
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    file_path = _regular_file(path, "COS upload source")
    if file_path.stat().st_size != expected_size or sha256_path(file_path) != expected_sha256:
        raise TransferContractError("COS upload source identity is invalid")
    with _deadline_alarm(operation_deadline):
        if expected_size <= COS_PART_SIZE_BYTES:
            return _upload_simple(
                path=file_path,
                bucket=bucket,
                endpoint_host=endpoint_host,
                object_key=object_key,
                sha256=expected_sha256,
                deadline_ns=operation_deadline,
            )
        return _upload_multipart(
            path=file_path,
            bucket=bucket,
            endpoint_host=endpoint_host,
            object_key=object_key,
            sha256=expected_sha256,
            deadline_ns=operation_deadline,
        )


def delete_object_once(
    *,
    bucket: str,
    endpoint_host: str,
    object_key: str,
    deadline_ns: int | None = None,
) -> None:
    operation_deadline = (
        time.monotonic_ns() + 30 * 1_000_000_000
        if deadline_ns is None
        else deadline_ns
    )
    with _deadline_alarm(operation_deadline):
        _cos_request(
            method="DELETE",
            bucket=bucket,
            endpoint_host=endpoint_host,
            object_key=object_key,
            expected_status={204},
            timeout=30,
            deadline_ns=operation_deadline,
        )


def _signed_urls(*, manifest_path: Path, validity_seconds: int) -> bytes:
    manifest = load_canonical_manifest(manifest_path)
    effective_validity, deadline_seconds_remaining = _bounded_signed_url_validity(
        validity_seconds
    )
    cos = cast(dict[str, object], manifest["cos"])
    bucket = cast(str, cos["bucket"])
    endpoint = cast(str, cos["endpoint_host"])
    object_keys = [
        cast(str, entry["object_key"])
        for entry in cast(list[dict[str, object]], manifest["files"])
    ]
    object_keys.append(cast(str, manifest["manifest_object_key"]))
    urls: dict[str, str] = {}
    for object_key in object_keys:
        url = _signed_object_url(
            bucket=bucket,
            endpoint_host=endpoint,
            object_key=object_key,
            validity_seconds=effective_validity,
        )
        _validate_readback_url(url, bucket=bucket, endpoint_host=endpoint)
        urls[PurePosixPath(object_key).name] = url
    return canonical_json_bytes(
        {
            "schema_version": SIGNED_URL_SCHEMA,
            "manifest_sha256": sha256_path(manifest_path),
            "deadline_seconds_remaining": deadline_seconds_remaining,
            "urls": urls,
        }
    )


def _bounded_signed_url_validity(
    requested_seconds: int,
    *,
    deadline_ns: int | None = None,
) -> tuple[int, int]:
    if requested_seconds < 60 or requested_seconds > MAX_VALIDITY_SECONDS:
        raise TransferContractError("signed URL validity is invalid")
    deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    remaining = max(
        1,
        int(_remaining_timeout(deadline, MAX_ESTIMATED_SECONDS)),
    )
    if remaining < 60:
        raise TransferContractError("signed URL validity is invalid")
    return min(requested_seconds, remaining), remaining


def _signed_object_url(
    *,
    bucket: str,
    endpoint_host: str,
    object_key: str,
    validity_seconds: int,
) -> str:
    secret_id, secret_key, session_token = _credentials()
    host = cos_object_host(bucket, endpoint_host)
    query = {"x-cos-security-token": session_token}
    authorization = _cos_authorization(
        method="GET",
        path=f"/{object_key}",
        query=query,
        headers={"host": host},
        secret_id=secret_id,
        secret_key=secret_key,
        validity_seconds=validity_seconds,
    )
    return _cos_url(host, object_key, {**query, **dict(urllib.parse.parse_qsl(authorization))})


def _validate_readback_url(url: str, *, bucket: str, endpoint_host: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise TransferContractError("COS readback URL is invalid") from exc
    host = parsed.hostname
    expected_host = cos_object_host(bucket, endpoint_host)
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
        or host != expected_host
    ):
        raise TransferContractError("COS readback URL is invalid")


def _object_readback_matches(
    *,
    url: str,
    bucket: str,
    endpoint_host: str,
    expected_size: int,
    expected_sha256: str,
    deadline_ns: int | None = None,
) -> bool:
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    _validate_readback_url(url, bucket=bucket, endpoint_host=endpoint_host)
    request = urllib.request.Request(
        url,
        headers={"Range": "bytes=0-0", "User-Agent": "ai-video-transfer-readback/1"},
    )
    try:
        with _open_no_redirect(
            request,
            timeout=_remaining_timeout(operation_deadline, 30),
        ) as response:
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes 0-0/([1-9][0-9]*)", content_range)
            if (
                response.status != 206
                or match is None
                or int(match.group(1)) != expected_size
                or response.headers.get("x-cos-meta-ai-video-sha256")
                != expected_sha256
                or response.headers.get("x-cos-meta-ai-video-size")
                != str(expected_size)
                or len(response.read(2)) != 1
            ):
                raise TransferContractError("COS shared object identity is invalid")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise TransferContractError("COS shared object readback failed") from None
    except (OSError, TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise TransferContractError("COS shared object readback failed") from exc
    return True


def plan_shared_object_uploads(
    *,
    manifest_path: Path,
    resume: bool,
    validity_seconds: int = 600,
    deadline_ns: int | None = None,
) -> list[dict[str, object]]:
    if validity_seconds < 60 or validity_seconds > 600:
        raise TransferContractError("COS readback validity is invalid")
    manifest = load_canonical_manifest(manifest_path)
    operation_deadline = (
        _deadline_from_environment() if deadline_ns is None else deadline_ns
    )
    files = cast(list[dict[str, object]], manifest["files"])
    if not resume:
        return files
    cos = cast(dict[str, object], manifest["cos"])
    bucket = cast(str, cos["bucket"])
    endpoint = cast(str, cos["endpoint_host"])
    planned: list[dict[str, object]] = []
    with _deadline_alarm(operation_deadline):
        for entry in files:
            effective_validity, _ = _bounded_signed_url_validity(
                validity_seconds,
                deadline_ns=operation_deadline,
            )
            url = _signed_object_url(
                bucket=bucket,
                endpoint_host=endpoint,
                object_key=cast(str, entry["object_key"]),
                validity_seconds=effective_validity,
            )
            if not _object_readback_matches(
                url=url,
                bucket=bucket,
                endpoint_host=endpoint,
                expected_size=cast(int, entry["size_bytes"]),
                expected_sha256=cast(str, entry["sha256"]),
                deadline_ns=operation_deadline,
            ):
                planned.append(entry)
    return planned


def verify_shared_object_readback(
    *,
    manifest_path: Path,
    validity_seconds: int = 600,
    deadline_ns: int | None = None,
) -> None:
    missing = plan_shared_object_uploads(
        manifest_path=manifest_path,
        resume=True,
        validity_seconds=validity_seconds,
        deadline_ns=deadline_ns,
    )
    if missing:
        raise TransferContractError("COS shared object set is incomplete")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("manifest-create")
    create.add_argument("--bundle-root", type=Path, required=True)
    create.add_argument("--source-revision", required=True)
    create.add_argument("--workflow-run-id", type=int, required=True)
    create.add_argument("--workflow-run-attempt", type=int, required=True)
    create.add_argument("--github-artifact-id", type=int, required=True)
    create.add_argument("--github-artifact-digest", required=True)
    create.add_argument("--cos-bucket", required=True)
    create.add_argument("--cos-endpoint-host", required=True)
    create.add_argument("--created-at", required=True)
    create.add_argument("--expires-at", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("manifest-verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--bundle-root", type=Path)
    probe = commands.add_parser("probe-evaluate")
    probe.add_argument("--transferred-bytes", type=int, required=True)
    probe.add_argument("--elapsed-nanoseconds", type=int, required=True)
    probe.add_argument("--release-bytes", type=int, required=True)
    sign = commands.add_parser("signed-url-payload")
    sign.add_argument("--manifest", type=Path, required=True)
    sign.add_argument("--validity-seconds", type=int, default=MAX_ESTIMATED_SECONDS)
    plan = commands.add_parser("shared-object-upload-plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--resume", action="store_true")
    readback = commands.add_parser("shared-object-readback-verify")
    readback.add_argument("--manifest", type=Path, required=True)
    versioning = commands.add_parser("cos-versioning-verify")
    versioning.add_argument("--bucket", required=True)
    versioning.add_argument("--endpoint-host", required=True)
    lifecycle = commands.add_parser("cos-lifecycle-verify")
    lifecycle.add_argument("--bucket", required=True)
    lifecycle.add_argument("--endpoint-host", required=True)
    lifecycle.add_argument("--governance-contract", type=Path, required=True)
    privacy = commands.add_parser("cos-privacy-verify")
    privacy.add_argument("--bucket", required=True)
    privacy.add_argument("--endpoint-host", required=True)
    privacy.add_argument("--governance-contract", type=Path, required=True)
    sts = commands.add_parser("sts-window-verify")
    sts.add_argument("--duration-seconds", type=int, required=True)
    sts.add_argument("--expires-at", required=True)
    sts.add_argument("--governance-contract", type=Path, required=True)
    assume = commands.add_parser("sts-assume-github-oidc")
    assume.add_argument("--provider-id", required=True)
    assume.add_argument("--role-arn", required=True)
    assume.add_argument("--source-revision", required=True)
    assume.add_argument("--workflow-run-id", type=int, required=True)
    assume.add_argument("--workflow-run-attempt", type=int, required=True)
    assume.add_argument("--bucket", required=True)
    assume.add_argument("--endpoint-host", required=True)
    assume.add_argument("--credentials-output", type=Path, required=True)
    assume.add_argument("--governance-contract", type=Path, required=True)
    credentials_verify = commands.add_parser("sts-credentials-verify")
    credentials_verify.add_argument("--credentials", type=Path, required=True)
    credentials_verify.add_argument("--provider-id", required=True)
    credentials_verify.add_argument("--role-arn", required=True)
    credentials_verify.add_argument("--source-revision", required=True)
    credentials_verify.add_argument("--workflow-run-id", type=int, required=True)
    credentials_verify.add_argument("--workflow-run-attempt", type=int, required=True)
    credentials_verify.add_argument("--governance-contract", type=Path, required=True)
    policy_digest = commands.add_parser("cam-policy-digest")
    policy_digest.add_argument("--bucket", required=True)
    policy_digest.add_argument("--endpoint-host", required=True)
    policy_digest.add_argument("--source-revision", required=True)
    policy_digest.add_argument("--workflow-run-id", type=int, required=True)
    policy_digest.add_argument("--workflow-run-attempt", type=int, required=True)
    policy_digest.add_argument("--governance-contract", type=Path, required=True)
    cam_readback = commands.add_parser("cam-effective-role-readback")
    cam_readback.add_argument("--credentials", type=Path, required=True)
    cam_readback.add_argument("--provider-id", required=True)
    cam_readback.add_argument("--role-arn", required=True)
    cam_readback.add_argument("--bucket", required=True)
    cam_readback.add_argument("--endpoint-host", required=True)
    cam_readback.add_argument("--source-revision", required=True)
    cam_readback.add_argument("--workflow-run-id", type=int, required=True)
    cam_readback.add_argument("--workflow-run-attempt", type=int, required=True)
    cam_readback.add_argument("--governance-contract", type=Path, required=True)
    upload = commands.add_parser("cos-object-upload")
    upload.add_argument("--path", type=Path, required=True)
    upload.add_argument("--bucket", required=True)
    upload.add_argument("--endpoint-host", required=True)
    upload.add_argument("--object-key", required=True)
    upload.add_argument("--sha256", required=True)
    upload.add_argument("--size-bytes", type=int, required=True)
    delete = commands.add_parser("cos-object-delete")
    delete.add_argument("--bucket", required=True)
    delete.add_argument("--endpoint-host", required=True)
    delete.add_argument("--object-key", required=True)
    signed = commands.add_parser("cos-signed-url")
    signed.add_argument("--bucket", required=True)
    signed.add_argument("--endpoint-host", required=True)
    signed.add_argument("--object-key", required=True)
    signed.add_argument("--validity-seconds", type=int, default=MAX_ESTIMATED_SECONDS)
    return parser


def _execute(args: argparse.Namespace) -> int:
    try:
        if args.command == "manifest-create":
            payload = build_transfer_manifest(
                bundle_root=args.bundle_root,
                source_revision=args.source_revision,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                github_artifact_id=args.github_artifact_id,
                github_artifact_digest=args.github_artifact_digest,
                cos_bucket=args.cos_bucket,
                cos_endpoint_host=args.cos_endpoint_host,
                created_at=args.created_at,
                expires_at=args.expires_at,
            )
            write_exclusive(args.output, canonical_json_bytes(payload))
            print(json.dumps({"status": "passed", "sha256": sha256_path(args.output)}))
        elif args.command == "manifest-verify":
            payload = load_canonical_manifest(args.manifest, bundle_root=args.bundle_root)
            print(json.dumps({"status": "passed", "source_revision": payload["source_revision"]}))
        elif args.command == "probe-evaluate":
            print(
                json.dumps(
                    evaluate_probe(
                        transferred_bytes=args.transferred_bytes,
                        elapsed_nanoseconds=args.elapsed_nanoseconds,
                        release_bytes=args.release_bytes,
                    ),
                    sort_keys=True,
                )
            )
        elif args.command == "signed-url-payload":
            sys.stdout.buffer.write(
                _signed_urls(
                    manifest_path=args.manifest,
                    validity_seconds=args.validity_seconds,
                )
            )
        elif args.command == "shared-object-upload-plan":
            entries = plan_shared_object_uploads(
                manifest_path=args.manifest,
                resume=args.resume,
            )
            for entry in entries:
                print(
                    f"{entry['path']}\t{entry['object_key']}\t"
                    f"{entry['sha256']}\t{entry['size_bytes']}"
                )
        elif args.command == "shared-object-readback-verify":
            verify_shared_object_readback(
                manifest_path=args.manifest,
            )
            print('{"status":"passed"}')
        elif args.command == "cos-versioning-verify":
            verify_bucket_never_versioned(
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
            )
            print('{"status":"passed","versioning":"never-enabled"}')
        elif args.command == "cos-lifecycle-verify":
            contract = load_release_governance_contract(args.governance_contract)
            rules = verify_bucket_lifecycle_governance(
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                contract=contract,
            )
            print(json.dumps({"status": "passed", "rules": rules}, sort_keys=True))
        elif args.command == "cos-privacy-verify":
            contract = load_release_governance_contract(args.governance_contract)
            result = verify_bucket_privacy_governance(
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                contract=contract,
            )
            print(json.dumps({"status": "passed", **result}, sort_keys=True))
        elif args.command == "sts-window-verify":
            contract = load_release_governance_contract(args.governance_contract)
            print(
                json.dumps(
                    validate_sts_window(
                        duration_seconds=args.duration_seconds,
                        expires_at=args.expires_at,
                        contract=contract,
                    ),
                    sort_keys=True,
                )
            )
        elif args.command == "sts-assume-github-oidc":
            contract = load_release_governance_contract(args.governance_contract)
            receipt = assume_github_oidc_role(
                contract=contract,
                provider_id=args.provider_id,
                role_arn=args.role_arn,
                source_revision=args.source_revision,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                credentials_output=args.credentials_output,
                request_url=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""),
                request_token=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
            )
            sys.stdout.buffer.write(canonical_json_bytes(receipt))
        elif args.command == "sts-credentials-verify":
            contract = load_release_governance_contract(args.governance_contract)
            result = validate_sts_credentials_file(
                path=args.credentials,
                contract=contract,
                source_revision=args.source_revision,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                provider_id=args.provider_id,
                role_arn=args.role_arn,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "cam-policy-digest":
            contract = load_release_governance_contract(args.governance_contract)
            expected_digest = expected_cam_policy_sha256(
                contract=contract,
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                source_revision=args.source_revision,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
            )
            print(expected_digest)
        elif args.command == "cam-effective-role-readback":
            contract = load_release_governance_contract(args.governance_contract)
            receipt = readback_cam_effective_role(
                contract=contract,
                credentials_path=args.credentials,
                provider_id=args.provider_id,
                role_arn=args.role_arn,
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                source_revision=args.source_revision,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
            )
            sys.stdout.buffer.write(canonical_json_bytes(receipt))
        elif args.command == "cos-object-upload":
            elapsed = upload_object_once(
                path=args.path,
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                object_key=args.object_key,
                expected_sha256=args.sha256,
                expected_size=args.size_bytes,
            )
            print(json.dumps({"status": "passed", "elapsed_nanoseconds": elapsed}))
        elif args.command == "cos-object-delete":
            delete_object_once(
                bucket=args.bucket,
                endpoint_host=args.endpoint_host,
                object_key=args.object_key,
            )
            print('{"status":"deleted"}')
        else:
            effective_validity, _ = _bounded_signed_url_validity(
                args.validity_seconds
            )
            print(
                _signed_object_url(
                    bucket=args.bucket,
                    endpoint_host=args.endpoint_host,
                    object_key=args.object_key,
                    validity_seconds=effective_validity,
                )
            )
    except TransferContractError:
        code = "release_transfer_contract_failed"
        print(f"ERROR: {code}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = _parser().parse_args()
    with _controlled_network_signals():
        return _execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
