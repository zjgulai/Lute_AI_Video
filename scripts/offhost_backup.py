#!/usr/bin/env python3
"""Provider-neutral, create-only off-host backup protocol and dry-run planner."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backup_manifest import (
    BACKUP_MANIFEST_NAME,
    BACKUP_MANIFEST_SHA_NAME,
    BackupManifestError,
    validate_backup_manifest,
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")


class OffHostBackupError(RuntimeError):
    """The off-host protocol failed closed with a stable local classification."""


class OffHostOutcomeAmbiguous(OffHostBackupError):
    """A remote operation may have happened and must never be retried automatically."""


@dataclass(frozen=True)
class ObjectReceipt:
    key: str
    version_id: str
    sha256: str
    size_bytes: int
    encryption: dict[str, str]


class CreateOnlyObjectStore(Protocol):
    def head(self, key: str) -> ObjectReceipt | None: ...

    def put(
        self,
        key: str,
        source: Path,
        *,
        sha256: str,
        create_only: bool,
    ) -> ObjectReceipt: ...

    def download(
        self,
        key: str,
        version_id: str,
        destination: Path,
    ) -> ObjectReceipt: ...


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_prefix(prefix: str) -> str:
    if not PREFIX_RE.fullmatch(prefix):
        raise OffHostBackupError("offhost_prefix_invalid")
    path = PurePosixPath(prefix)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != prefix:
        raise OffHostBackupError("offhost_prefix_invalid")
    return prefix.rstrip("/")


def _snapshot_files(backup_dir: Path) -> list[dict[str, object]]:
    try:
        manifest = validate_backup_manifest(backup_dir)
    except BackupManifestError as exc:
        raise OffHostBackupError("offhost_local_manifest_invalid") from exc

    artifacts = manifest.get("artifacts")
    media = manifest.get("media")
    if not isinstance(artifacts, dict) or not isinstance(media, dict):
        raise OffHostBackupError("offhost_local_manifest_invalid")
    media_files = media.get("files")
    if not isinstance(media_files, list):
        raise OffHostBackupError("offhost_local_manifest_invalid")
    expected_paths = {
        BACKUP_MANIFEST_NAME,
        BACKUP_MANIFEST_SHA_NAME,
        *(str(name) for name in artifacts),
    }
    for entry in media_files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise OffHostBackupError("offhost_local_manifest_invalid")
        expected_paths.add(f"output/{entry['path']}")

    actual_paths: set[str] = set()
    ignored_compatibility_paths = {"manifest.txt", "restore_verified.json"}
    for path in backup_dir.rglob("*"):
        if path.is_symlink():
            raise OffHostBackupError("offhost_local_symlink_rejected")
        if path.is_file():
            actual_paths.add(path.relative_to(backup_dir).as_posix())
    if actual_paths - expected_paths - ignored_compatibility_paths:
        raise OffHostBackupError("offhost_local_file_set_invalid")
    if expected_paths - actual_paths:
        raise OffHostBackupError("offhost_local_manifest_invalid")

    files: list[dict[str, object]] = []
    for relative in sorted(expected_paths):
        path = backup_dir / relative
        files.append(
            {
                "relative": relative,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_path(path),
            }
        )
    if not files:
        raise OffHostBackupError("offhost_local_backup_empty")
    return files


def build_dry_run_plan(backup_dir: Path, prefix: str) -> dict[str, object]:
    normalized_prefix = _validated_prefix(prefix)
    files = _snapshot_files(backup_dir)
    backup_name = backup_dir.name
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}_\d{6}", backup_name):
        raise OffHostBackupError("offhost_backup_name_invalid")
    objects = [
        {
            "key": f"{normalized_prefix}/{backup_name}/{entry['relative']}",
            "size_bytes": entry["size_bytes"],
            "sha256": entry["sha256"],
        }
        for entry in files
    ]
    manifest_path = backup_dir / BACKUP_MANIFEST_NAME
    return {
        "mode": "dry-run",
        "protocol": "offhost-backup.v1",
        "create_only": True,
        "object_count": len(objects),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in objects),
        "backup_manifest_sha256": _sha256_path(manifest_path),
        "objects": objects,
    }


def _validate_receipt(
    receipt: object,
    *,
    key: str,
    sha256: str,
    size_bytes: int,
) -> ObjectReceipt:
    if not isinstance(receipt, ObjectReceipt):
        raise OffHostBackupError("offhost_receipt_invalid")
    if (
        receipt.key != key
        or not receipt.version_id
        or len(receipt.version_id) > 512
        or receipt.sha256 != sha256
        or not SHA256_RE.fullmatch(receipt.sha256)
        or receipt.size_bytes != size_bytes
    ):
        raise OffHostBackupError("offhost_receipt_identity_invalid")
    if set(receipt.encryption) != {"mode", "key_ref", "algorithm"} or any(
        not isinstance(value, str) or not value or len(value) > 512
        for value in receipt.encryption.values()
    ):
        raise OffHostBackupError("offhost_receipt_encryption_invalid")
    return receipt


def _stable_call[T](code: str, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except OffHostBackupError:
        raise
    except Exception:
        raise OffHostOutcomeAmbiguous(code) from None


def upload_backup_create_only(
    store: CreateOnlyObjectStore,
    backup_dir: Path,
    prefix: str,
) -> dict[str, object]:
    plan = build_dry_run_plan(backup_dir, prefix)
    objects = plan["objects"]
    if not isinstance(objects, list):
        raise OffHostBackupError("offhost_plan_invalid")

    for item in objects:
        if not isinstance(item, dict):
            raise OffHostBackupError("offhost_plan_invalid")
        key = str(item["key"])
        existing = _stable_call(
            "offhost_head_outcome_ambiguous",
            lambda key=key: store.head(key),
        )
        if existing is not None:
            raise OffHostBackupError("offhost_object_already_exists")

    uploaded = 0
    key_root = f"{_validated_prefix(prefix)}/{backup_dir.name}/"
    with tempfile.TemporaryDirectory(prefix="ai-video-offhost-readback-") as temp_dir:
        readback_root = Path(temp_dir)
        for index, item in enumerate(objects):
            if not isinstance(item, dict):
                raise OffHostBackupError("offhost_plan_invalid")
            key = str(item["key"])
            sha256 = str(item["sha256"])
            size_bytes = int(item["size_bytes"])
            if not key.startswith(key_root):
                raise OffHostBackupError("offhost_plan_invalid")
            relative = key[len(key_root) :]
            source = backup_dir / relative
            put_receipt = _stable_call(
                "offhost_put_outcome_ambiguous",
                lambda: store.put(
                    key,
                    source,
                    sha256=sha256,
                    create_only=True,
                ),
            )
            try:
                validated = _validate_receipt(
                    put_receipt,
                    key=key,
                    sha256=sha256,
                    size_bytes=size_bytes,
                )
                head_receipt = _stable_call(
                    "offhost_readback_outcome_ambiguous",
                    lambda: store.head(key),
                )
                if head_receipt != validated:
                    raise OffHostBackupError("offhost_readback_receipt_mismatch")
                destination = readback_root / f"object-{index}"
                download_receipt = _stable_call(
                    "offhost_download_outcome_ambiguous",
                    lambda: store.download(key, validated.version_id, destination),
                )
                if download_receipt != validated:
                    raise OffHostBackupError("offhost_download_receipt_mismatch")
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or destination.stat().st_size != size_bytes
                    or _sha256_path(destination) != sha256
                ):
                    raise OffHostBackupError("offhost_download_checksum_mismatch")
            except OffHostOutcomeAmbiguous:
                raise
            except OffHostBackupError as exc:
                raise OffHostOutcomeAmbiguous(str(exc)) from exc
            uploaded += 1
    return {
        "status": "passed",
        "protocol": "offhost-backup.v1",
        "create_only": True,
        "object_count": uploaded,
        "total_size_bytes": plan["total_size_bytes"],
        "backup_manifest_sha256": plan["backup_manifest_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    try:
        plan = build_dry_run_plan(args.backup_dir, args.prefix)
    except OffHostBackupError as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)}))
        return 1
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
