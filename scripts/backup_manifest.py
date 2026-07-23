#!/usr/bin/env python3
"""Build and validate canonical AI Video source and backup manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, cast

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALEMBIC_REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BACKUP_TIMESTAMP_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}_\d{6}$")
UTC_TIMESTAMP_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PG_IMAGE_RE = re.compile(r"^postgres@sha256:[0-9a-f]{64}$")
REPO_DIGEST_RE = re.compile(r"^[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$")

SOURCE_SCHEMA = "source-manifest.v1"
BACKUP_SCHEMA = "backup-manifest.v1"
SOURCE_MANIFEST_NAME = "source-manifest.v1.json"
BACKUP_MANIFEST_NAME = "backup-manifest.v1.json"
BACKUP_MANIFEST_SHA_NAME = "backup-manifest.v1.json.sha256"
BACKUP_ARTIFACTS = (
    "media_manifest.json",
    "pg_dump.jsonl",
    "pg_dump_stats.json",
    "pg_schema.dump",
    "pg_schema.list",
    "pg_schema_signature_after.json",
    SOURCE_MANIFEST_NAME,
)
SCHEMA_METADATA_TABLES = frozenset({"alembic_version"})


class BackupManifestError(ValueError):
    """Canonical backup identity or artifact validation failed."""


def _require_backup_root(backup_dir: Path) -> None:
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        raise BackupManifestError("backup root is missing or unsafe")


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except OSError as exc:
        raise BackupManifestError(
            "canonical backup output already exists or is unsafe"
        ) from exc


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupManifestError(f"{label} is not valid JSON") from exc


def _require_exact_keys(payload: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != keys:
        raise BackupManifestError(f"{label} fields are invalid")
    return payload


def _safe_relative_path(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise BackupManifestError(f"{label} path is invalid")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != raw:
        raise BackupManifestError(f"{label} path is invalid")
    if any(part in {"", "."} for part in path.parts):
        raise BackupManifestError(f"{label} path is invalid")
    return raw


def _file_entry(root: Path, relative: str, label: str) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise BackupManifestError(f"{label} is missing or unsafe")
    path = root / relative
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise BackupManifestError(f"{label} is missing or unsafe")
    if not path.is_file():
        raise BackupManifestError(f"{label} is missing or unsafe")
    return {
        "path": relative,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _source_file_entry(
    root: Path,
    relative: str,
) -> tuple[dict[str, object], str | None]:
    if root.is_symlink() or not root.is_dir():
        raise BackupManifestError("source file is missing or unsafe")
    path = root / relative
    current = root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        if not current.is_symlink():
            continue
        if index != len(parts) - 1:
            raise BackupManifestError("source file is missing or unsafe")
        try:
            raw_target = os.readlink(current)
            target_bytes = raw_target.encode("utf-8")
        except (OSError, UnicodeEncodeError) as exc:
            raise BackupManifestError("source file is missing or unsafe") from exc
        target = PurePosixPath(raw_target)
        if (
            target.is_absolute()
            or ".." in target.parts
            or target.as_posix() != raw_target
            or any(component in {"", "."} for component in target.parts)
        ):
            raise BackupManifestError("source file is missing or unsafe")
        parent = PurePosixPath(relative).parent
        target_relative = (
            target.as_posix()
            if parent == PurePosixPath(".")
            else (parent / target).as_posix()
        )
        target_path = root
        for component in PurePosixPath(target_relative).parts:
            target_path = target_path / component
            if target_path.is_symlink():
                raise BackupManifestError("source file is missing or unsafe")
        if not target_path.is_file():
            raise BackupManifestError("source file is missing or unsafe")
        return (
            {
                "path": relative,
                "size_bytes": len(target_bytes),
                "sha256": hashlib.sha256(b"symlink\0" + target_bytes).hexdigest(),
            },
            target_relative,
        )
    if not path.is_file():
        raise BackupManifestError("source file is missing or unsafe")
    return _file_entry(root, relative, "source file"), None


def _resolved_source_root(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise BackupManifestError("source root is missing or unsafe") from exc
    if not resolved.is_dir():
        raise BackupManifestError("source root is missing or unsafe")
    return resolved


def build_source_manifest(
    root: Path,
    git_sha: str,
    files: list[str],
) -> dict[str, object]:
    if not GIT_SHA_RE.fullmatch(git_sha):
        raise BackupManifestError("source manifest Git SHA is invalid")
    normalized = [_safe_relative_path(item, "source file") for item in files]
    if not normalized or len(normalized) != len(set(normalized)):
        raise BackupManifestError("source manifest file set is empty or duplicated")
    source_root = _resolved_source_root(root)
    entries_with_targets = [
        _source_file_entry(source_root, item) for item in sorted(normalized)
    ]
    tracked = set(normalized)
    if any(
        target is not None and target not in tracked
        for _, target in entries_with_targets
    ):
        raise BackupManifestError("source symlink target is not tracked")
    entries = [entry for entry, _ in entries_with_targets]
    return {
        "schema_version": SOURCE_SCHEMA,
        "git_sha": git_sha,
        "files": entries,
    }


def validate_source_manifest(
    payload: object,
    root: Path | None = None,
) -> dict[str, object]:
    manifest = _require_exact_keys(
        payload,
        {"schema_version", "git_sha", "files"},
        "source manifest",
    )
    if manifest["schema_version"] != SOURCE_SCHEMA:
        raise BackupManifestError("source manifest schema version is invalid")
    git_sha = manifest["git_sha"]
    if not isinstance(git_sha, str) or not GIT_SHA_RE.fullmatch(git_sha):
        raise BackupManifestError("source manifest Git SHA is invalid")
    raw_entries = manifest["files"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise BackupManifestError("source manifest file set is empty")

    source_root = _resolved_source_root(root) if root is not None else None
    paths: list[str] = []
    symlink_targets: list[str] = []
    validated_entries: list[dict[str, object]] = []
    for raw_entry in raw_entries:
        entry = _require_exact_keys(
            raw_entry,
            {"path", "size_bytes", "sha256"},
            "source manifest entry",
        )
        relative = _safe_relative_path(entry["path"], "source file")
        size = entry["size_bytes"]
        digest = entry["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BackupManifestError("source file size is invalid")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise BackupManifestError("source file checksum is invalid")
        if source_root is not None:
            actual, symlink_target = _source_file_entry(source_root, relative)
            if actual["size_bytes"] != size or actual["sha256"] != digest:
                raise BackupManifestError("source file checksum or size mismatch")
            if symlink_target is not None:
                symlink_targets.append(symlink_target)
        paths.append(relative)
        validated_entries.append(
            {"path": relative, "size_bytes": size, "sha256": digest}
        )
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise BackupManifestError("source manifest file order or uniqueness is invalid")
    if any(target not in set(paths) for target in symlink_targets):
        raise BackupManifestError("source symlink target is not tracked")
    return {
        "schema_version": SOURCE_SCHEMA,
        "git_sha": git_sha,
        "files": validated_entries,
    }


def _validate_table_stats(payload: object) -> dict[str, dict[str, int]]:
    if not isinstance(payload, dict) or not payload:
        raise BackupManifestError("database table stats are invalid")
    validated: dict[str, dict[str, int]] = {}
    for table in sorted(payload):
        if not isinstance(table, str) or not IDENTIFIER_RE.fullmatch(table):
            raise BackupManifestError("database table identifier is invalid")
        result = _require_exact_keys(payload[table], {"rows"}, "database table stats")
        rows = result["rows"]
        if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
            raise BackupManifestError("database row count is invalid")
        validated[table] = {"rows": rows}
    return validated


def _database_facts(
    stats_payload: object,
    schema_after_payload: object,
    pg_client_source_tag: str,
    pg_client_image: str,
    dump_path: Path,
    schema_list_path: Path,
) -> dict[str, object]:
    if not isinstance(stats_payload, dict):
        raise BackupManifestError("PostgreSQL dump stats are invalid")
    expected_tables = stats_payload.get("expected_tables")
    if (
        not isinstance(expected_tables, list)
        or not expected_tables
        or len(expected_tables) != len(set(expected_tables))
        or any(
            not isinstance(table, str) or not IDENTIFIER_RE.fullmatch(table)
            for table in expected_tables
        )
    ):
        raise BackupManifestError("PostgreSQL expected table set is invalid")
    if set(expected_tables) & SCHEMA_METADATA_TABLES:
        raise BackupManifestError(
            "PostgreSQL business table set includes schema metadata"
        )
    tables = _validate_table_stats(stats_payload.get("tables"))
    if set(tables) & SCHEMA_METADATA_TABLES:
        raise BackupManifestError(
            "PostgreSQL business table stats include schema metadata"
        )
    if set(tables) != set(expected_tables):
        raise BackupManifestError("PostgreSQL stats table set is inconsistent")
    total_rows = stats_payload.get("total_rows")
    if (
        isinstance(total_rows, bool)
        or not isinstance(total_rows, int)
        or total_rows != sum(result["rows"] for result in tables.values())
    ):
        raise BackupManifestError("PostgreSQL total row count is inconsistent")
    dump_counts = {table: 0 for table in tables}
    with dump_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BackupManifestError("PostgreSQL dump JSONL is invalid") from exc
            if not isinstance(record, dict) or set(record) != {"_table", "_data"}:
                raise BackupManifestError("PostgreSQL dump record is invalid")
            table = record.get("_table")
            data = record.get("_data")
            if table not in dump_counts or not isinstance(data, dict) or not data:
                raise BackupManifestError(
                    f"PostgreSQL dump record is invalid at line {line_number}"
                )
            dump_counts[table] += 1
    expected_counts = {table: result["rows"] for table, result in tables.items()}
    if (
        dump_counts != expected_counts
        or stats_payload.get("file_size") != dump_path.stat().st_size
    ):
        raise BackupManifestError("PostgreSQL dump size or row count is inconsistent")

    schema_tables: set[str] = set()
    for line in schema_list_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 7 and parts[3:5] == ["TABLE", "public"]:
            table = parts[5]
            if not IDENTIFIER_RE.fullmatch(table) or table in schema_tables:
                raise BackupManifestError("PostgreSQL schema table set is invalid")
            schema_tables.add(table)
    expected_schema_tables = set(expected_tables) | SCHEMA_METADATA_TABLES
    if schema_tables != expected_schema_tables:
        raise BackupManifestError("PostgreSQL schema table set is inconsistent")

    server_version_num = stats_payload.get("server_version_num")
    server_major = stats_payload.get("server_major")
    if (
        not isinstance(server_version_num, str)
        or not server_version_num.isdigit()
        or isinstance(server_major, bool)
        or not isinstance(server_major, int)
        or server_major < 10
        or int(server_version_num) // 10000 != server_major
    ):
        raise BackupManifestError("PostgreSQL server version facts are inconsistent")
    if pg_client_source_tag != f"postgres:{server_major}":
        raise BackupManifestError("PostgreSQL client source tag is inconsistent")
    if not PG_IMAGE_RE.fullmatch(pg_client_image):
        raise BackupManifestError("PostgreSQL client image is not digest pinned")

    schema_signature = stats_payload.get("schema_signature")
    alembic_head = stats_payload.get("alembic_revision")
    after = _require_exact_keys(
        schema_after_payload,
        {"schema_signature", "alembic_revision"},
        "post-export schema signature",
    )
    if (
        not isinstance(schema_signature, str)
        or not SHA256_RE.fullmatch(schema_signature)
        or after["schema_signature"] != schema_signature
    ):
        raise BackupManifestError("PostgreSQL schema signatures are inconsistent")
    if (
        not isinstance(alembic_head, str)
        or not ALEMBIC_REVISION_RE.fullmatch(alembic_head)
        or after["alembic_revision"] != alembic_head
    ):
        raise BackupManifestError("Alembic head facts are inconsistent")
    return {
        "alembic_head": alembic_head,
        "schema_signature": schema_signature,
        "server_version_num": server_version_num,
        "server_major": server_major,
        "client_source_tag": pg_client_source_tag,
        "client_image": pg_client_image,
        "tables": tables,
        "total_rows": total_rows,
    }


def _validate_media(backup_dir: Path, payload: object) -> dict[str, object]:
    media = _require_exact_keys(
        payload,
        {"file_count", "total_size_bytes", "files"},
        "media manifest",
    )
    raw_files = media["files"]
    if not isinstance(raw_files, list):
        raise BackupManifestError("media manifest file list is invalid")
    validated_files: list[dict[str, object]] = []
    declared_paths: list[str] = []
    total_size = 0
    output_root = backup_dir / "output"
    for raw_entry in raw_files:
        entry = _require_exact_keys(
            raw_entry,
            {"path", "size_bytes", "sha256"},
            "media manifest entry",
        )
        relative = _safe_relative_path(entry["path"], "media file")
        size = entry["size_bytes"]
        digest = entry["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BackupManifestError("media file size is invalid")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise BackupManifestError("media file checksum is invalid")
        actual = _file_entry(output_root, relative, "media file")
        if actual["size_bytes"] != size or actual["sha256"] != digest:
            raise BackupManifestError("media file checksum or size mismatch")
        declared_paths.append(relative)
        total_size += size
        validated_files.append(
            {"path": relative, "size_bytes": size, "sha256": digest}
        )
    if declared_paths != sorted(declared_paths) or len(declared_paths) != len(
        set(declared_paths)
    ):
        raise BackupManifestError("media file set order or uniqueness is invalid")
    actual_paths: set[str] = set()
    if output_root.is_dir():
        for path in output_root.rglob("*"):
            if path.is_symlink():
                raise BackupManifestError("media snapshot contains a symlink")
            if path.is_file():
                actual_paths.add(path.relative_to(output_root).as_posix())
    if actual_paths != set(declared_paths):
        raise BackupManifestError("media exact file set does not match manifest")
    if media["file_count"] != len(validated_files) or media["total_size_bytes"] != total_size:
        raise BackupManifestError("media file count or total bytes is inconsistent")
    return {
        "file_count": len(validated_files),
        "total_size_bytes": total_size,
        "files": validated_files,
    }


def _artifact_facts(backup_dir: Path) -> dict[str, dict[str, object]]:
    facts: dict[str, dict[str, object]] = {}
    for name in BACKUP_ARTIFACTS:
        path = backup_dir / name
        if path.is_symlink() or not path.is_file():
            raise BackupManifestError(f"required backup artifact is missing: {name}")
        facts[name] = {
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_path(path),
        }
    return facts


def create_backup_manifest(
    *,
    backup_dir: Path,
    source_root: Path,
    source_manifest_path: Path,
    backend_image_reference: str,
    backend_image_id: str,
    backend_repo_digest: str | None,
    oci_revision: str,
    pg_client_source_tag: str,
    pg_client_image: str,
    completed_at: str,
    backup_timestamp: str,
) -> dict[str, object]:
    _require_backup_root(backup_dir)
    source_copy = backup_dir / SOURCE_MANIFEST_NAME
    manifest_path = backup_dir / BACKUP_MANIFEST_NAME
    detached_path = backup_dir / BACKUP_MANIFEST_SHA_NAME
    copy_source = source_manifest_path.resolve() != source_copy.resolve()
    output_paths = [manifest_path, detached_path]
    if copy_source:
        output_paths.append(source_copy)
    if any(path.is_symlink() or path.exists() for path in output_paths):
        raise BackupManifestError("canonical backup output already exists or is unsafe")

    source_payload = validate_source_manifest(
        _load_json(source_manifest_path, "source manifest"),
        source_root,
    )
    if source_manifest_path.read_bytes() != _canonical_json(source_payload):
        raise BackupManifestError("source manifest serialization is not canonical")
    git_sha = source_payload["git_sha"]
    if not isinstance(git_sha, str) or git_sha != oci_revision:
        raise BackupManifestError("Git and OCI revision identity does not match")
    if not IMAGE_ID_RE.fullmatch(backend_image_id):
        raise BackupManifestError("backend image ID is invalid")
    if backend_repo_digest is not None and not REPO_DIGEST_RE.fullmatch(
        backend_repo_digest
    ):
        raise BackupManifestError("backend repository digest is invalid")
    if not backend_image_reference or any(
        char.isspace() for char in backend_image_reference
    ):
        raise BackupManifestError("backend image reference is invalid")
    if not BACKUP_TIMESTAMP_RE.fullmatch(backup_timestamp):
        raise BackupManifestError("backup timestamp is invalid")
    if not UTC_TIMESTAMP_RE.fullmatch(completed_at):
        raise BackupManifestError("backup completion timestamp is invalid")

    created_paths: list[Path] = []
    try:
        if copy_source:
            _write_exclusive(source_copy, source_manifest_path.read_bytes())
            created_paths.append(source_copy)
        source_copy_payload = validate_source_manifest(
            _load_json(source_copy, "copied source manifest")
        )
        if source_copy.read_bytes() != _canonical_json(source_copy_payload):
            raise BackupManifestError(
                "copied source manifest serialization is not canonical"
            )
        if source_copy_payload != source_payload:
            raise BackupManifestError("copied source manifest is inconsistent")

        stats = _load_json(backup_dir / "pg_dump_stats.json", "PostgreSQL dump stats")
        schema_after = _load_json(
            backup_dir / "pg_schema_signature_after.json",
            "post-export schema signature",
        )
        database = _database_facts(
            stats,
            schema_after,
            pg_client_source_tag,
            pg_client_image,
            backup_dir / "pg_dump.jsonl",
            backup_dir / "pg_schema.list",
        )
        media_payload = _load_json(backup_dir / "media_manifest.json", "media manifest")
        media = _validate_media(backup_dir, media_payload)
        artifacts = _artifact_facts(backup_dir)
        source_entries = cast(list[dict[str, object]], source_payload["files"])
        source_size = sum(cast(int, entry["size_bytes"]) for entry in source_entries)
        manifest: dict[str, object] = {
            "schema_version": BACKUP_SCHEMA,
            "project": "ai-video",
            "backup_timestamp": backup_timestamp,
            "completed_at": completed_at,
            "git_sha": git_sha,
            "source_manifest": {
                "sha256": artifacts[SOURCE_MANIFEST_NAME]["sha256"],
                "file_count": len(source_entries),
                "total_size_bytes": source_size,
            },
            "backend_image": {
                "reference": backend_image_reference,
                "image_id": backend_image_id,
                "repo_digest": backend_repo_digest,
                "oci_revision": oci_revision,
            },
            "database": database,
            "media": {
                **media,
                "manifest_sha256": artifacts["media_manifest.json"]["sha256"],
            },
            "artifacts": artifacts,
        }
        _write_exclusive(manifest_path, _canonical_json(manifest))
        created_paths.append(manifest_path)
        digest = _sha256_path(manifest_path)
        _write_exclusive(
            detached_path,
            f"{digest}  {BACKUP_MANIFEST_NAME}\n".encode("ascii"),
        )
        created_paths.append(detached_path)
        validate_backup_manifest(backup_dir)
    except Exception:
        for path in reversed(created_paths):
            path.unlink(missing_ok=True)
        raise
    return manifest


def validate_backup_manifest(backup_dir: Path) -> dict[str, object]:
    _require_backup_root(backup_dir)
    manifest_path = backup_dir / BACKUP_MANIFEST_NAME
    detached_path = backup_dir / BACKUP_MANIFEST_SHA_NAME
    if manifest_path.is_symlink() or detached_path.is_symlink():
        raise BackupManifestError("backup manifest artifacts must not be symlinks")
    if not manifest_path.is_file() or not detached_path.is_file():
        raise BackupManifestError("canonical backup manifest or detached checksum is missing")
    expected_detached = f"{_sha256_path(manifest_path)}  {BACKUP_MANIFEST_NAME}\n"
    if detached_path.read_text(encoding="ascii") != expected_detached:
        raise BackupManifestError("detached manifest checksum does not match")
    payload = _load_json(manifest_path, "canonical backup manifest")
    if manifest_path.read_bytes() != _canonical_json(payload):
        raise BackupManifestError("canonical backup manifest serialization is invalid")
    manifest = _require_exact_keys(
        payload,
        {
            "schema_version",
            "project",
            "backup_timestamp",
            "completed_at",
            "git_sha",
            "source_manifest",
            "backend_image",
            "database",
            "media",
            "artifacts",
        },
        "canonical backup manifest",
    )
    if manifest["schema_version"] != BACKUP_SCHEMA or manifest["project"] != "ai-video":
        raise BackupManifestError("canonical backup manifest identity is invalid")
    git_sha = manifest["git_sha"]
    if not isinstance(git_sha, str) or not GIT_SHA_RE.fullmatch(git_sha):
        raise BackupManifestError("canonical backup Git SHA is invalid")
    if not isinstance(manifest["backup_timestamp"], str) or not BACKUP_TIMESTAMP_RE.fullmatch(
        manifest["backup_timestamp"]
    ):
        raise BackupManifestError("canonical backup timestamp is invalid")
    if not isinstance(manifest["completed_at"], str) or not UTC_TIMESTAMP_RE.fullmatch(
        manifest["completed_at"]
    ):
        raise BackupManifestError("canonical completion timestamp is invalid")

    image = _require_exact_keys(
        manifest["backend_image"],
        {"reference", "image_id", "repo_digest", "oci_revision"},
        "backend image facts",
    )
    if image["oci_revision"] != git_sha:
        raise BackupManifestError("Git and OCI revision identity does not match")
    if not isinstance(image["image_id"], str) or not IMAGE_ID_RE.fullmatch(
        image["image_id"]
    ):
        raise BackupManifestError("backend image ID is invalid")
    if image["repo_digest"] is not None and (
        not isinstance(image["repo_digest"], str)
        or not REPO_DIGEST_RE.fullmatch(image["repo_digest"])
    ):
        raise BackupManifestError("backend repository digest is invalid")
    if not isinstance(image["reference"], str) or not image["reference"]:
        raise BackupManifestError("backend image reference is invalid")
    if any(char.isspace() for char in image["reference"]):
        raise BackupManifestError("backend image reference is invalid")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != set(BACKUP_ARTIFACTS):
        raise BackupManifestError("backup artifact set is invalid")
    actual_artifacts = _artifact_facts(backup_dir)
    if artifacts != actual_artifacts:
        raise BackupManifestError("backup artifact checksum or size mismatch")

    source_payload = validate_source_manifest(
        _load_json(backup_dir / SOURCE_MANIFEST_NAME, "copied source manifest")
    )
    if (backup_dir / SOURCE_MANIFEST_NAME).read_bytes() != _canonical_json(
        source_payload
    ):
        raise BackupManifestError("copied source manifest serialization is not canonical")
    source_entries = cast(list[dict[str, object]], source_payload["files"])
    source_facts = _require_exact_keys(
        manifest["source_manifest"],
        {"sha256", "file_count", "total_size_bytes"},
        "source manifest facts",
    )
    expected_source_facts = {
        "sha256": actual_artifacts[SOURCE_MANIFEST_NAME]["sha256"],
        "file_count": len(source_entries),
        "total_size_bytes": sum(
            cast(int, entry["size_bytes"]) for entry in source_entries
        ),
    }
    if source_payload["git_sha"] != git_sha or source_facts != expected_source_facts:
        raise BackupManifestError("source manifest identity is inconsistent")

    database_payload = _require_exact_keys(
        manifest["database"],
        {
            "alembic_head",
            "schema_signature",
            "server_version_num",
            "server_major",
            "client_source_tag",
            "client_image",
            "tables",
            "total_rows",
        },
        "database facts",
    )
    expected_database = _database_facts(
        _load_json(backup_dir / "pg_dump_stats.json", "PostgreSQL dump stats"),
        _load_json(
            backup_dir / "pg_schema_signature_after.json",
            "post-export schema signature",
        ),
        str(database_payload["client_source_tag"]),
        str(database_payload["client_image"]),
        backup_dir / "pg_dump.jsonl",
        backup_dir / "pg_schema.list",
    )
    if database_payload != expected_database:
        raise BackupManifestError("database recovery identity is inconsistent")

    media_payload = _require_exact_keys(
        manifest["media"],
        {"file_count", "total_size_bytes", "files", "manifest_sha256"},
        "media facts",
    )
    expected_media = _validate_media(
        backup_dir,
        _load_json(backup_dir / "media_manifest.json", "media manifest"),
    )
    if media_payload != {
        **expected_media,
        "manifest_sha256": actual_artifacts["media_manifest.json"]["sha256"],
    }:
        raise BackupManifestError("media recovery identity is inconsistent")
    return manifest


def _git_tracked_files(root: Path, git_sha: str) -> list[str]:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BackupManifestError("tracked source discovery failed") from exc
    if head != git_sha:
        raise BackupManifestError("tracked source HEAD does not match requested Git SHA")
    try:
        return [item.decode("utf-8") for item in result.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise BackupManifestError("tracked source path is not UTF-8") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source-create")
    source.add_argument("--root", type=Path, required=True)
    source.add_argument("--git-sha", required=True)
    source.add_argument("--output", type=Path, required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--backup-dir", type=Path, required=True)
    create.add_argument("--source-root", type=Path, required=True)
    create.add_argument("--source-manifest", type=Path, required=True)
    create.add_argument("--backend-image-reference", required=True)
    create.add_argument("--backend-image-id", required=True)
    create.add_argument("--backend-repo-digest")
    create.add_argument("--oci-revision", required=True)
    create.add_argument("--pg-client-source-tag", required=True)
    create.add_argument("--pg-client-image", required=True)
    create.add_argument("--completed-at", required=True)
    create.add_argument("--backup-timestamp", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--backup-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "source-create":
            files = _git_tracked_files(args.root, args.git_sha)
            payload = build_source_manifest(args.root, args.git_sha, files)
            validate_source_manifest(payload, args.root)
            try:
                with args.output.open("xb") as stream:
                    stream.write(_canonical_json(payload))
            except OSError as exc:
                raise BackupManifestError(
                    "source manifest output already exists or is unsafe"
                ) from exc
            print(json.dumps({"status": "passed", "file_count": len(files)}))
        elif args.command == "create":
            manifest = create_backup_manifest(
                backup_dir=args.backup_dir,
                source_root=args.source_root,
                source_manifest_path=args.source_manifest,
                backend_image_reference=args.backend_image_reference,
                backend_image_id=args.backend_image_id,
                backend_repo_digest=args.backend_repo_digest,
                oci_revision=args.oci_revision,
                pg_client_source_tag=args.pg_client_source_tag,
                pg_client_image=args.pg_client_image,
                completed_at=args.completed_at,
                backup_timestamp=args.backup_timestamp,
            )
            print(json.dumps({"status": "passed", "git_sha": manifest["git_sha"]}))
        else:
            manifest = validate_backup_manifest(args.backup_dir)
            print(json.dumps({"status": "passed", "git_sha": manifest["git_sha"]}))
    except BackupManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
