#!/usr/bin/env python3
"""Canonical contracts for COS-backed exact release artifact transfer."""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import hmac
import http.client
import json
import math
import os
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

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]-[0-9]{5,20}$")
COS_REGIONAL_ENDPOINT_RE = re.compile(
    r"^cos\.[a-z0-9]+(?:-[a-z0-9]+)+\.myqcloud\.com$"
)
UTC_TIMESTAMP_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

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


def _credentials() -> tuple[str, str, str]:
    values = tuple(
        os.environ.get(name, "")
        for name in ("COS_SECRET_ID", "COS_SECRET_KEY", "COS_SESSION_TOKEN")
    )
    if any(not value or "\n" in value or "\r" in value for value in values):
        raise TransferContractError("COS credentials are missing or invalid")
    return cast(tuple[str, str, str], values)


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
        del exc
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
            "content-md5": base64.b64encode(hashlib.md5(data).digest()).decode(),
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
                            hashlib.md5(chunk).digest()
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
        _deadline_from_environment(default_seconds=30)
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
    if validity_seconds < 60 or validity_seconds > MAX_VALIDITY_SECONDS:
        raise TransferContractError("signed URL validity is invalid")
    manifest = load_canonical_manifest(manifest_path)
    deadline = _deadline_from_environment()
    deadline_seconds_remaining = max(
        1,
        int(_remaining_timeout(deadline, MAX_ESTIMATED_SECONDS)),
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
            validity_seconds=validity_seconds,
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
            url = _signed_object_url(
                bucket=bucket,
                endpoint_host=endpoint,
                object_key=cast(str, entry["object_key"]),
                validity_seconds=validity_seconds,
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
    sign.add_argument("--validity-seconds", type=int, default=MAX_VALIDITY_SECONDS)
    plan = commands.add_parser("shared-object-upload-plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--resume", action="store_true")
    readback = commands.add_parser("shared-object-readback-verify")
    readback.add_argument("--manifest", type=Path, required=True)
    versioning = commands.add_parser("cos-versioning-verify")
    versioning.add_argument("--bucket", required=True)
    versioning.add_argument("--endpoint-host", required=True)
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
    signed.add_argument("--validity-seconds", type=int, default=MAX_VALIDITY_SECONDS)
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
            print(
                _signed_object_url(
                    bucket=args.bucket,
                    endpoint_host=args.endpoint_host,
                    object_key=args.object_key,
                    validity_seconds=args.validity_seconds,
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
