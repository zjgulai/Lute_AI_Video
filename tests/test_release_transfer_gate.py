"""Restricted server-side release staging and promotion gate tests."""

from __future__ import annotations

import hashlib
import http.client
import http.server
import io
import json
import os
import subprocess
import sys
import tarfile
import threading
import time
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import deploy.lighthouse.release_transfer_gate as gate_module
from deploy.lighthouse.release_transfer_gate import (
    GateError,
    GateIdentity,
    cleanup_incoming,
    parse_forced_command,
    promote_incoming,
    read_receipt,
    run_probe,
    safe_extract_source_archive,
    stage_release,
    validate_image_archive,
    write_state_marker,
)
from scripts.release_transfer import (
    PROBE_SIZE_BYTES,
    build_transfer_manifest,
    build_transfer_receipt,
    canonical_json_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_release_transfer_gate.sh"

SOURCE_SHA = "a" * 40
MANIFEST_SHA = "b" * 64


def _identity() -> GateIdentity:
    return GateIdentity(
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        manifest_sha256=MANIFEST_SHA,
    )


def _probe_payload(identity: GateIdentity) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": "release-transfer-probe-url.v1",
            "manifest_sha256": identity.manifest_sha256,
            "release_bytes": 2_200_000_000,
            "deadline_seconds_remaining": 1_800,
            "bucket": "ai-video-release-1250000000",
            "endpoint_host": "cos.ap-shanghai.myqcloud.com",
            "url": (
                "https://ai-video-release-1250000000.cos.ap-shanghai."
                "myqcloud.com/probe?signature=fixture"
            ),
        }
    )


def _install_fast_probe_download(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(
        _url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
        intent: Any = None,
    ):
        del deadline_ns
        assert maximum_bytes == PROBE_SIZE_BYTES
        destination.write_bytes(b"probe")
        if intent is not None:
            gate_module._record_created_path(intent, destination.lstat())
        return PROBE_SIZE_BYTES, 16_000_000_000

    monkeypatch.setattr(gate_module, "_download", fake_download)
    monkeypatch.setattr(gate_module, "sha256_path", lambda _path: gate_module.PROBE_SHA256)


def _verified_transaction(root: Path) -> tuple[GateIdentity, Path]:
    staging = root / ".fixture"
    staging.mkdir()
    source_archive = staging / f"release-source-{SOURCE_SHA}.tar.gz"
    image_archive = staging / f"release-images-{SOURCE_SHA}.tar.gz"
    app_bytes = b"print('ok')\n"
    app_member = tarfile.TarInfo("app.py")
    app_member.mode = 0o644
    app_member.size = len(app_bytes)
    with tarfile.open(source_archive, "w:gz") as archive:
        archive.addfile(app_member, io.BytesIO(app_bytes))
    image_archive.write_bytes(b"images")
    source_sha = hashlib.sha256(source_archive.read_bytes()).hexdigest()
    image_sha = hashlib.sha256(image_archive.read_bytes()).hexdigest()
    (staging / f"release-source-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{source_sha}  {source_archive.name}\n"
    )
    (staging / f"release-images-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{image_sha}  {image_archive.name}\n"
    )
    (staging / "source-manifest.v1.json").write_text(
        json.dumps(
            {
                "schema_version": "source-manifest.v1",
                "git_sha": SOURCE_SHA,
                "files": [
                    {
                        "path": "app.py",
                        "size_bytes": len(app_bytes),
                        "sha256": hashlib.sha256(app_bytes).hexdigest(),
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    image_ids = [f"sha256:{character * 64}" for character in "123"]
    (staging / "image-digests.txt").write_text("\n".join(image_ids) + "\n")
    now = datetime.now(UTC).replace(microsecond=0)
    expires = now + timedelta(hours=1)
    manifest = build_transfer_manifest(
        bundle_root=staging,
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        github_artifact_id=98765,
        github_artifact_digest=f"sha256:{'f' * 64}",
        cos_bucket="ai-video-release-1250000000",
        cos_endpoint_host="cos.ap-shanghai.myqcloud.com",
        created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    identity = GateIdentity(SOURCE_SHA, 12345, 1, manifest_sha)
    incoming = root / identity.incoming_directory
    incoming.mkdir()
    (staging / "app.py").write_bytes(app_bytes)
    (staging / "app.py").chmod(0o644)
    for path in staging.iterdir():
        os.replace(path, incoming / path.name)
    staging.rmdir()
    (incoming / "release-transfer-manifest.v1.json").write_bytes(manifest_bytes)
    receipt = build_transfer_receipt(
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        manifest_sha256=manifest_sha,
        incoming_directory=identity.incoming_directory,
        completed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        probe=gate_module.evaluate_probe(
            transferred_bytes=PROBE_SIZE_BYTES,
            elapsed_nanoseconds=16_000_000_000,
            release_bytes=sum(
                cast(int, entry["size_bytes"])
                for entry in cast(list[dict[str, object]], manifest["files"])
            )
            + len(manifest_bytes),
        ),
        manifest=manifest,
    )
    (incoming / "release-transfer-receipt.v1.json").write_bytes(
        canonical_json_bytes(receipt)
    )
    write_state_marker(incoming, identity, "verified")
    return identity, incoming


@pytest.mark.parametrize("action", ["probe", "stage", "receipt", "cleanup"])
def test_staging_role_accepts_only_exact_nonpromotion_commands(action: str):
    command = f"{action} {SOURCE_SHA} 12345 1 {MANIFEST_SHA}"
    parsed = parse_forced_command(command, role="staging")
    assert parsed.action == action
    assert parsed.identity == _identity()


@pytest.mark.parametrize(
    "command",
    [
        f"promote {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
        f"stage {SOURCE_SHA} 12345 1 {MANIFEST_SHA}; id",
        f"stage {SOURCE_SHA} 12345 1 {MANIFEST_SHA} extra",
        f"stage {'A' * 40} 12345 1 {MANIFEST_SHA}",
        f"stage {SOURCE_SHA} 0 1 {MANIFEST_SHA}",
        f"stage {SOURCE_SHA} 12345 0 {MANIFEST_SHA}",
    ],
)
def test_staging_role_rejects_promotion_shell_and_identity_drift(command: str):
    with pytest.raises(GateError):
        parse_forced_command(command, role="staging")


def test_production_role_accepts_only_promote():
    parsed = parse_forced_command(
        f"promote {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
        role="production",
    )
    assert parsed.action == "promote"
    with pytest.raises(GateError):
        parse_forced_command(
            f"stage {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
            role="production",
        )


def _tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for info, payload in members:
            archive.addfile(info, io.BytesIO(payload))


def test_source_extract_rejects_traversal_devices_and_untracked_symlinks(tmp_path: Path):
    for name, info in (
        ("traversal", tarfile.TarInfo("../escape")),
        ("device", tarfile.TarInfo("device")),
        ("symlink", tarfile.TarInfo("link")),
    ):
        if name == "device":
            info.type = tarfile.CHRTYPE
        elif name == "symlink":
            info.type = tarfile.SYMTYPE
            info.linkname = "missing-target"
        else:
            info.size = 1
        archive = tmp_path / f"{name}.tar.gz"
        _tar(archive, [(info, b"x" if info.size else b"")])
        with pytest.raises(GateError):
            safe_extract_source_archive(
                archive,
                tmp_path / f"out-{name}",
                declared_entries={
                    "link": (1, "0" * 64),
                    "device": (0, "0" * 64),
                    "../escape": (1, "0" * 64),
                },
            )
    assert not (tmp_path.parent / "escape").exists()


def test_source_extract_allows_only_safe_manifest_bound_relative_symlink(tmp_path: Path):
    target = tarfile.TarInfo("Dockerfile.backend")
    target.size = 7
    link = tarfile.TarInfo("Dockerfile")
    link.type = tarfile.SYMTYPE
    link.linkname = "Dockerfile.backend"
    archive = tmp_path / "source.tar.gz"
    _tar(archive, [(target, b"content"), (link, b"")])

    destination = tmp_path / "source"
    safe_extract_source_archive(
        archive,
        destination,
        declared_entries={
            "Dockerfile": (
                len(b"Dockerfile.backend"),
                hashlib.sha256(b"symlink\0Dockerfile.backend").hexdigest(),
            ),
            "Dockerfile.backend": (7, hashlib.sha256(b"content").hexdigest()),
        },
    )
    assert (destination / "Dockerfile").is_symlink()
    assert os.readlink(destination / "Dockerfile") == "Dockerfile.backend"


def test_source_extract_rejects_manifest_size_or_digest_before_acceptance(tmp_path: Path):
    member = tarfile.TarInfo("large.bin")
    member.size = 1024
    archive = tmp_path / "source.tar.gz"
    _tar(archive, [(member, b"x" * member.size)])

    for suffix, entry in (
        ("size", (1, hashlib.sha256(b"x").hexdigest())),
        ("digest", (1024, "0" * 64)),
    ):
        with pytest.raises(GateError, match="identity|size"):
            safe_extract_source_archive(
                archive,
                tmp_path / f"source-{suffix}",
                declared_entries={"large.bin": entry},
            )


@pytest.mark.parametrize("ambient_umask", [0o077, 0o027])
def test_source_modes_are_deterministic_under_hostile_umask(
    tmp_path: Path,
    ambient_umask: int,
):
    regular = tarfile.TarInfo("pkg/app.py")
    regular.mode = 0o600
    regular.size = 3
    executable = tarfile.TarInfo("deploy.sh")
    executable.mode = 0o751
    executable.size = 4
    archive = tmp_path / f"source-{ambient_umask:o}.tar.gz"
    _tar(archive, [(regular, b"app"), (executable, b"exec")])
    destination = tmp_path / f"source-{ambient_umask:o}"
    previous = os.umask(ambient_umask)
    try:
        safe_extract_source_archive(
            archive,
            destination,
            declared_entries={
                "deploy.sh": (4, hashlib.sha256(b"exec").hexdigest()),
                "pkg/app.py": (3, hashlib.sha256(b"app").hexdigest()),
            },
        )
    finally:
        os.umask(previous)

    assert destination.stat().st_mode & 0o777 == 0o755
    assert (destination / "pkg").stat().st_mode & 0o777 == 0o755
    assert (destination / "pkg/app.py").stat().st_mode & 0o777 == 0o644
    assert (destination / "deploy.sh").stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("unsafe_mode", [0o4755, 0o2755, 0o1755, 0o666])
def test_source_extract_rejects_privileged_or_world_writable_modes(
    tmp_path: Path,
    unsafe_mode: int,
):
    member = tarfile.TarInfo("unsafe.sh")
    member.mode = unsafe_mode
    member.size = 1
    archive = tmp_path / f"unsafe-{unsafe_mode:o}.tar.gz"
    _tar(archive, [(member, b"x")])
    with pytest.raises(GateError, match="mode is unsafe"):
        safe_extract_source_archive(
            archive,
            tmp_path / f"out-{unsafe_mode:o}",
            declared_entries={"unsafe.sh": (1, hashlib.sha256(b"x").hexdigest())},
        )


@pytest.mark.parametrize("member_kind", ["regular", "symlink"])
def test_source_extract_rejects_excessive_path_depth_before_creating_tree(
    tmp_path: Path,
    member_kind: str,
):
    relative = "/".join(
        ["d"] * (gate_module.MAX_ARCHIVE_PATH_COMPONENTS + 1) + ["payload"]
    )
    member = tarfile.TarInfo(relative)
    archive = tmp_path / f"deep-{member_kind}.tar.gz"
    if member_kind == "regular":
        payload = b"x"
        member.size = len(payload)
        declared = {relative: (1, hashlib.sha256(payload).hexdigest())}
        _tar(archive, [(member, payload)])
    else:
        member.type = tarfile.SYMTYPE
        member.linkname = "target"
        declared = {
            relative: (
                len(member.linkname),
                hashlib.sha256(b"symlink\0" + member.linkname.encode()).hexdigest(),
            ),
            "target": (1, hashlib.sha256(b"x").hexdigest()),
        }
        target = tarfile.TarInfo("target")
        target.size = 1
        _tar(archive, [(target, b"x"), (member, b"")])
    destination = tmp_path / "out"

    with pytest.raises(GateError, match="path is unsafe"):
        safe_extract_source_archive(
            archive,
            destination,
            declared_entries=declared,
        )

    assert destination.is_dir()
    assert list(destination.iterdir()) == []


def test_source_extract_rejects_oversized_utf8_path_components(tmp_path: Path):
    relative = f"{'界' * 86}/payload"
    member = tarfile.TarInfo(relative)
    member.size = 1
    archive = tmp_path / "wide.tar.gz"
    _tar(archive, [(member, b"x")])

    with pytest.raises(GateError, match="path is unsafe"):
        safe_extract_source_archive(
            archive,
            tmp_path / "out",
            declared_entries={relative: (1, hashlib.sha256(b"x").hexdigest())},
        )


def test_cleanup_recursion_failure_is_stable_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity = _identity()
    incoming = tmp_path / identity.incoming_directory
    incoming.mkdir()
    write_state_marker(incoming, identity, "downloading")
    original_rglob = Path.rglob

    def fail_deep_walk(path: Path, pattern: str):
        if path == incoming or path.name.startswith(".release-cleanup-"):
            raise RecursionError("fixture deep tree")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", fail_deep_walk)
    with pytest.raises(GateError, match="ownership"):
        cleanup_incoming(tmp_path, identity)

    assert incoming.is_dir()


def test_gate_main_normalizes_recursion_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        gate_module,
        "run_probe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RecursionError("fixture deep tree")
        ),
    )
    monkeypatch.setattr(
        gate_module.sys,
        "argv",
        [
            "release_transfer_gate.py",
            "--role",
            "staging",
            "--command",
            f"probe {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
        ],
    )

    assert gate_module.main() == 126
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert json.loads(stderr)["code"] == "server_probe_failed"


def test_image_archive_rejects_unsafe_members_and_bounds(tmp_path: Path):
    safe = tarfile.TarInfo("manifest.json")
    safe.size = 2
    archive = tmp_path / "images.tar.gz"
    _tar(archive, [(safe, b"{}")])
    facts = validate_image_archive(archive)
    assert facts["member_count"] == 1

    unsafe = tarfile.TarInfo("../../etc/shadow")
    unsafe.size = 1
    bad = tmp_path / "bad-images.tar.gz"
    _tar(bad, [(unsafe, b"x")])
    with pytest.raises(GateError, match="unsafe"):
        validate_image_archive(bad)


def test_cleanup_requires_exact_marker_and_never_removes_final_or_current(tmp_path: Path):
    identity, incoming = _verified_transaction(tmp_path)
    final = tmp_path / identity.final_directory
    current = tmp_path / "current"
    current.symlink_to(incoming.name)

    with pytest.raises(GateError, match="current"):
        cleanup_incoming(tmp_path, identity)
    assert incoming.exists()

    current.unlink()
    cleanup_incoming(tmp_path, identity)
    assert not incoming.exists()

    final.mkdir()
    with pytest.raises(GateError, match="final"):
        cleanup_incoming(tmp_path, identity)


def test_promotion_is_atomic_verified_only_and_create_only(tmp_path: Path):
    identity, incoming = _verified_transaction(tmp_path)

    promoted = promote_incoming(tmp_path, identity)
    assert promoted == tmp_path / identity.final_directory
    assert promoted.is_dir()
    assert not incoming.exists()
    marker = json.loads((promoted / ".release-transfer-state.v1.json").read_text())
    assert marker["state"] == "promoted"
    assert promoted.stat().st_mode & 0o777 == 0o755
    assert (
        promoted / f"release-images-{SOURCE_SHA}.tar.gz"
    ).stat().st_mode & 0o777 == 0o644

    incoming.mkdir()
    write_state_marker(incoming, identity, "verified")
    with pytest.raises(GateError, match="final"):
        promote_incoming(tmp_path, identity)
    assert incoming.exists()


@pytest.mark.parametrize("mode", [0o700, 0o775, 0o777])
def test_promotion_and_cleanup_reject_unsafe_release_root_mode(
    tmp_path: Path,
    mode: int,
):
    identity, incoming = _verified_transaction(tmp_path)
    release = tmp_path / "release-root"
    release.mkdir(mode=mode)
    release.chmod(mode)

    with pytest.raises(GateError, match="release root ownership or mode"):
        promote_incoming(tmp_path, identity, release_root=release)
    with pytest.raises(GateError, match="release root ownership or mode"):
        cleanup_incoming(tmp_path, identity, release_root=release)

    assert incoming.is_dir()
    assert not (release / identity.final_directory).exists()


def test_promotion_rejects_release_root_symlink(tmp_path: Path):
    identity, incoming = _verified_transaction(tmp_path)
    real_release = tmp_path / "real-release"
    real_release.mkdir()
    release = tmp_path / "release-root"
    release.symlink_to(real_release)

    with pytest.raises(GateError, match="release root is missing or unsafe"):
        promote_incoming(tmp_path, identity, release_root=release)

    assert incoming.is_dir()
    assert not (real_release / identity.final_directory).exists()


def test_promotion_rechecks_release_root_identity_immediately_before_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    release = tmp_path / "release-root"
    displaced = tmp_path / "displaced-release-root"
    release.mkdir()
    original_prepare = gate_module._prepare_promoted_permissions

    def swap_release_root(
        directory: Path,
        manifest: dict[str, object],
    ) -> None:
        original_prepare(directory, manifest)
        os.replace(release, displaced)
        release.mkdir()

    monkeypatch.setattr(
        gate_module,
        "_prepare_promoted_permissions",
        swap_release_root,
    )
    with pytest.raises(GateError, match="release root identity changed"):
        promote_incoming(tmp_path, identity, release_root=release)

    assert incoming.is_dir()
    assert incoming.stat().st_mode & 0o777 == 0o700
    assert not (release / identity.final_directory).exists()
    assert not (displaced / identity.final_directory).exists()


def test_promotion_rejects_source_mode_drift_before_final_rename(tmp_path: Path):
    identity, incoming = _verified_transaction(tmp_path)
    (incoming / "app.py").chmod(0o600)

    with pytest.raises(GateError, match="mode contract"):
        promote_incoming(tmp_path, identity)

    assert incoming.is_dir()
    assert not (tmp_path / identity.final_directory).exists()


@pytest.mark.parametrize(
    "mutation",
    ("content", "added", "missing", "symlink"),
)
def test_promotion_revalidates_exact_source_bytes_and_file_set(
    tmp_path: Path,
    mutation: str,
):
    identity, incoming = _verified_transaction(tmp_path)
    app = incoming / "app.py"
    if mutation == "content":
        app.write_text("print('drift')\n")
    elif mutation == "added":
        (incoming / "unexpected.py").write_text("drift = True\n")
    elif mutation == "missing":
        app.unlink()
    else:
        app.unlink()
        app.symlink_to("source-manifest.v1.json")

    with pytest.raises(GateError, match="source"):
        promote_incoming(tmp_path, identity)

    assert incoming.is_dir()
    assert not (tmp_path / identity.final_directory).exists()


def test_promotion_rechecks_expiry_after_prepare_and_restores_staging_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    final = tmp_path / identity.final_directory
    original_expiry = gate_module._assert_receipt_not_expired
    expiry_checks = 0
    rename_called = False

    def expire_after_prepare(receipt: dict[str, object]) -> None:
        nonlocal expiry_checks
        expiry_checks += 1
        if expiry_checks == 2:
            raise GateError("verified incoming release receipt has expired")
        original_expiry(receipt)

    def forbidden_rename(_source: Path, _destination: Path) -> None:
        nonlocal rename_called
        rename_called = True
        raise AssertionError("expired release must not be promoted")

    monkeypatch.setattr(
        gate_module,
        "_assert_receipt_not_expired",
        expire_after_prepare,
    )
    monkeypatch.setattr(gate_module, "_rename_noreplace", forbidden_rename)
    with pytest.raises(GateError, match="expired"):
        promote_incoming(tmp_path, identity)

    assert expiry_checks == 2
    assert rename_called is False
    assert incoming.is_dir()
    assert incoming.stat().st_mode & 0o777 == 0o700
    marker = json.loads((incoming / gate_module.STATE_FILE).read_text())
    assert marker["state"] == "verified"
    assert not final.exists()


def test_promotion_final_expiry_check_failure_restores_staging_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    checks = 0

    def fail_final_check(_receipt: dict[str, object]) -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise GateError("fixture final expiry check failed")

    monkeypatch.setattr(
        gate_module,
        "_assert_receipt_not_expired",
        fail_final_check,
    )
    with pytest.raises(GateError, match="final expiry"):
        promote_incoming(tmp_path, identity)

    assert checks == 2
    assert incoming.is_dir()
    assert incoming.stat().st_mode & 0o777 == 0o700
    assert not (tmp_path / identity.final_directory).exists()


@pytest.mark.parametrize("operation", ["receipt", "cleanup", "promote"])
def test_every_gate_callsite_rejects_equal_length_manifest_digest_drift(
    tmp_path: Path,
    operation: str,
):
    identity, incoming = _verified_transaction(tmp_path)
    manifest_path = incoming / "release-transfer-manifest.v1.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["workflow"]["artifact_digest"] = f"sha256:{'e' * 64}"
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises((GateError, gate_module.TransferContractError), match="manifest"):
        if operation == "receipt":
            read_receipt(tmp_path, identity)
        elif operation == "cleanup":
            cleanup_incoming(tmp_path, identity)
        else:
            promote_incoming(tmp_path, identity)
    assert incoming.is_dir()


def test_promotion_marker_failure_rolls_final_back_to_retryable_incoming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    original_replace_marker = gate_module._replace_state_marker

    def fail_promoted_marker(directory: Path, actual: GateIdentity, state: str):
        if state == "promoted":
            raise GateError("fixture promoted marker failure")
        return original_replace_marker(directory, actual, state)

    monkeypatch.setattr(gate_module, "_replace_state_marker", fail_promoted_marker)
    with pytest.raises(GateError, match="rolled back"):
        promote_incoming(tmp_path, identity)

    final = tmp_path / identity.final_directory
    assert incoming.is_dir()
    assert not final.exists()
    assert incoming.stat().st_mode & 0o777 == 0o700
    marker = json.loads((incoming / ".release-transfer-state.v1.json").read_text())
    assert marker["state"] == "verified"


def test_promotion_atomic_noreplace_rejects_destination_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    final = tmp_path / identity.final_directory
    original = gate_module._rename_noreplace

    def create_race_then_rename(source: Path, destination: Path):
        destination.mkdir()
        return original(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", create_race_then_rename)
    with pytest.raises(GateError, match="rename failed"):
        promote_incoming(tmp_path, identity)
    assert incoming.is_dir()
    assert final.is_dir()


def test_probe_cleanup_failure_prevents_irreversible_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    probe = tmp_path / identity.probe_file
    probe.write_bytes(b"probe")
    original_unlink = Path.unlink

    def fail_probe(path: Path, *args, **kwargs):
        if path == probe:
            raise OSError("fixture probe cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_probe)
    with pytest.raises(GateError, match="probe cleanup"):
        promote_incoming(tmp_path, identity)
    assert incoming.is_dir()
    assert not (tmp_path / identity.final_directory).exists()


def test_promotion_marker_and_rename_back_double_failure_reports_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    final = tmp_path / identity.final_directory
    original_rename = gate_module._rename_noreplace

    def fail_promoted_marker(directory: Path, actual: GateIdentity, state: str):
        del directory, actual
        if state == "promoted":
            raise GateError("fixture promoted marker failure")
        raise AssertionError("unexpected marker state")

    def fail_rename_back(source: Path, destination: Path):
        if source == final and destination == incoming:
            raise GateError("fixture rename-back failure")
        return original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_replace_state_marker", fail_promoted_marker)
    monkeypatch.setattr(gate_module, "_rename_noreplace", fail_rename_back)
    with pytest.raises(GateError, match="manual recovery"):
        promote_incoming(tmp_path, identity)

    assert final.is_dir()
    assert not incoming.exists()


def test_marker_is_exclusive_canonical_and_rejects_symlink(tmp_path: Path):
    identity = _identity()
    incoming = tmp_path / identity.incoming_directory
    incoming.mkdir()
    marker = write_state_marker(incoming, identity, "downloading")
    assert marker.stat().st_mode & 0o777 == 0o600
    assert marker.read_bytes().endswith(b"\n")
    with pytest.raises(GateError, match="already exists"):
        write_state_marker(incoming, identity, "downloading")


def test_state_replace_interrupt_removes_owned_temporary_and_preserves_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    marker = tmp_path / "state.json"
    marker.write_bytes(b"old\n")
    original_fsync = gate_module.os.fsync

    def interrupt_temporary_fsync(descriptor: int) -> None:
        if gate_module.os.fstat(descriptor).st_ino != marker.stat().st_ino:
            raise SystemExit(143)
        original_fsync(descriptor)

    monkeypatch.setattr(gate_module.os, "fsync", interrupt_temporary_fsync)
    with pytest.raises(GateError, match="interrupted"):
        gate_module._atomic_write(marker, b"new\n", exclusive=False)

    assert marker.read_bytes() == b"old\n"
    assert list(tmp_path.glob(".state.json.*")) == []
    assert list(tmp_path.glob(".release-cleanup-*")) == []


@pytest.mark.parametrize("failure_point", ["fchmod", "fdopen"])
def test_state_temporary_setup_failure_closes_and_cleans_owned_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
):
    marker = tmp_path / "state.json"
    marker.write_bytes(b"old\n")

    if failure_point == "fchmod":
        monkeypatch.setattr(
            gate_module.os,
            "fchmod",
            lambda *_args: (_ for _ in ()).throw(OSError("fixture fchmod failure")),
        )
    else:
        monkeypatch.setattr(
            gate_module.os,
            "fdopen",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OSError("fixture fdopen failure")
            ),
        )

    with pytest.raises(GateError, match="state update failed"):
        gate_module._atomic_write(marker, b"new\n", exclusive=False)

    assert marker.read_bytes() == b"old\n"
    assert list(tmp_path.glob(".state.json.*")) == []
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_state_temporary_setup_cleanup_double_fault_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    marker = tmp_path / "state.json"
    marker.write_bytes(b"old\n")
    original_unlink = Path.unlink

    monkeypatch.setattr(
        gate_module.os,
        "fchmod",
        lambda *_args: (_ for _ in ()).throw(OSError("fixture fchmod failure")),
    )

    def fail_quarantine_unlink(path: Path, *args, **kwargs):
        if path.parent == tmp_path and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture quarantine unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_quarantine_unlink)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._atomic_write(marker, b"new\n", exclusive=False)

    assert marker.read_bytes() == b"old\n"
    assert list(tmp_path.glob(".state.json.*")) == []
    quarantines = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantines) == 1
    assert quarantines[0].is_file()


def test_state_temporary_cleanup_preserves_postcheck_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    marker = tmp_path / "state.json"
    marker.write_bytes(b"old\n")
    displaced = tmp_path / "displaced-temporary"
    original_fsync = gate_module.os.fsync
    original_rename = gate_module._rename_noreplace
    replacement: Path | None = None

    def interrupt_temporary_fsync(descriptor: int) -> None:
        if gate_module.os.fstat(descriptor).st_ino != marker.stat().st_ino:
            raise GateError("fixture state write interruption")
        original_fsync(descriptor)

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal replacement
        if source.name.startswith(".state.json."):
            replacement = source
            os.replace(source, displaced)
            source.write_bytes(b"foreign temporary\n")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module.os, "fsync", interrupt_temporary_fsync)
    monkeypatch.setattr(gate_module, "_rename_noreplace", swap_before_quarantine)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._atomic_write(marker, b"new\n", exclusive=False)

    assert marker.read_bytes() == b"old\n"
    assert replacement is not None
    assert replacement.read_bytes() == b"foreign temporary\n"
    assert displaced.read_bytes() == b"new\n"
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_installer_creates_fixed_role_wrapper_without_authorized_keys_mutation():
    text = INSTALLER.read_text()
    assert "--staging-forward" in text
    assert "--staging-command" in text
    assert 'sudo -n "$0" --staging-command "$SSH_ORIGINAL_COMMAND"' in text
    assert '--role staging --command "$1"' in text
    assert "--role production --command" in text
    assert text.count('[ "$(id -u)" -eq 0 ] || exit 126') >= 2
    assert "root:root" in text
    assert "0755" in text
    assert "/var/lib/ai-video-release-transfer" in text
    assert 'ensure_root_directory_exact "$STAGING_ROOT" 700 || fail' in text
    assert 'cmp -s "$SOURCE_ROOT/scripts/release_transfer.py"' in text
    assert 'cmp -s "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py"' in text
    assert 'cmp -s "$runtime/release-transfer-gate" <(render_wrapper)' in text
    assert 'SELF=$(readlink -f "$0") || exit 126' in text
    assert 'RUNTIME_DIR=$(dirname "$SELF")' in text
    assert 'GATE="$RUNTIME_DIR/release_transfer_gate.py"' in text
    assert 'VERSIONS_ROOT="$INSTALL_ROOT/versions"' in text
    assert 'os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK' in text
    assert 'flags | os.O_CREAT | os.O_EXCL' in text
    assert 'info.st_nlink != 1' in text
    assert 'flock -n "$descriptor" || return 1' in text
    assert 'exec 9>"$INSTALL_ROOT/.install.lock"' not in text
    assert 'verify_root_directory "$INSTALL_ROOT" 755 || return 1' in text
    assert 'verify_root_directory "$VERSIONS_ROOT" 755 || return 1' in text
    assert 'verify_root_directory "$runtime" 755 || return 1' in text
    assert 'verify_regular_root_file "$INSTALL_ROOT/.install.lock" 600 || return 1' in text
    assert '''[ "$(stat -c '%h' "$path")" = "1" ] || return 1''' in text
    assert text.count('verify_runtime_roots "$runtime" || fail') >= 1
    assert text.count("verify_source_bundle_inputs || fail") >= 3
    assert 'atomic_replace "$pointer" "$WRAPPER_PATH" || fail' in text
    assert 'rollback_pointer "$runtime/release-transfer-gate"' in text
    assert "verify_atomic_rename_compatibility" in text
    assert "contract_sha256" in text
    assert "gate_sha256" in text
    assert "wrapper_sha256" in text
    assert "stat -c '%d'" not in text
    assert "grep -F" not in text
    assert "print-authorized-command" in text
    assert "authorized_keys" not in text
    assert "DEPLOY_" not in text


def test_installer_verifies_complete_bundle_before_atomic_pointer_switch():
    text = INSTALLER.read_text()

    def assert_install_transaction(payload: str) -> None:
        candidate_verify = payload.index('verify_bundle "$candidate" || fail')
        candidate_digest = payload.index(
            'candidate_version=$(runtime_bundle_sha256 "$candidate")'
        )
        candidate_digest_gate = payload.index(
            '[ "$candidate_version" = "$version" ] || fail'
        )
        version_publish = payload.index('mv "$candidate" "$runtime"')
        runtime_roots = payload.index(
            'verify_runtime_roots "$runtime" || fail',
            version_publish,
        )
        runtime_bundle = payload.index('verify_bundle "$runtime" || fail', runtime_roots)
        runtime_digest = payload.index(
            '[ "$(runtime_bundle_sha256 "$runtime")" = "$version" ] || fail',
            runtime_bundle,
        )
        previous_snapshot = payload.index('cp -P "$WRAPPER_PATH" "$previous"')
        pointer_intent = payload.index("switch_started=1")
        pointer_switch = payload.index(
            'atomic_replace "$pointer" "$WRAPPER_PATH" || fail'
        )
        post_verify = payload.index('verify_installation "$version" || fail')
        assert candidate_verify < candidate_digest < candidate_digest_gate
        assert candidate_digest_gate < version_publish < runtime_roots < runtime_bundle
        assert runtime_bundle < runtime_digest < previous_snapshot
        assert previous_snapshot < pointer_intent < pointer_switch < post_verify
        assert "cleanup_install" in payload
        trap_install = payload.index("trap cleanup_install EXIT")
        candidate_create = payload.index('mkdir -m 0700 "$candidate" || fail')
        assert trap_install < candidate_create
        assert (
            'if [ "$rc" -ne 0 ] && [ "$switch_started" -eq 1 ]'
            in payload
        )
        assert 'rollback_pointer "$runtime/release-transfer-gate"' in payload

    assert_install_transaction(text)


def test_installer_runtime_digest_detects_source_swap_after_version_freeze(
    tmp_path: Path,
):
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    (source / "scripts").mkdir(parents=True)
    (source / "deploy" / "lighthouse").mkdir(parents=True)
    candidate.mkdir()
    contract = source / "scripts" / "release_transfer.py"
    gate = source / "deploy" / "lighthouse" / "release_transfer_gate.py"
    contract.write_text("contract-old\n")
    gate.write_text("gate-old\n")

    prefix = INSTALLER.read_text().split('\ncase "$ACTION" in\n', 1)[0]
    command = prefix + r'''
SOURCE_ROOT="$1"
candidate="$2"
version=$(bundle_sha256)
printf 'contract-new\n' > "$SOURCE_ROOT/scripts/release_transfer.py"
printf 'gate-new\n' > "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py"
cp "$SOURCE_ROOT/scripts/release_transfer.py" "$candidate/release_transfer.py"
cp "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py" \
  "$candidate/release_transfer_gate.py"
render_wrapper > "$candidate/release-transfer-gate"
candidate_version=$(runtime_bundle_sha256 "$candidate")
[ "$candidate_version" != "$version" ]
'''
    result = subprocess.run(
        ["bash", "-c", command, "installer-test", str(source), str(candidate)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SOURCE_ROOT": str(source)},
    )

    assert result.returncode == 0, result.stderr


def _run_installer_lock_helper(
    lock_path: Path,
    child: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    text = INSTALLER.read_text()
    helper = text.split("<<'PY_LOCK'\n", 1)[1].split("\nPY_LOCK\n", 1)[0]
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(os.getuid()),
            str(os.getgid()),
            str(lock_path),
            str(child),
            str(tmp_path := lock_path.parent),
            str(tmp_path / "install-root"),
            str(tmp_path / "wrapper"),
            sys.executable,
        ],
        input=helper,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def test_installer_lock_open_is_no_follow_no_truncate_and_single_link(
    tmp_path: Path,
):
    child = tmp_path / "child.sh"
    child.write_text("#!/bin/sh\nexit 0\n")
    child.chmod(0o755)
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"do-not-change\n")
    sentinel.chmod(0o640)
    before = (sentinel.read_bytes(), sentinel.stat().st_mode & 0o777)

    symlink = tmp_path / "symlink.lock"
    symlink.symlink_to(sentinel)
    hardlink = tmp_path / "hardlink.lock"
    os.link(sentinel, hardlink)

    for unsafe in (symlink, hardlink):
        result = _run_installer_lock_helper(unsafe, child)
        assert result.returncode != 0
        assert "release_transfer_gate_install_failed" in result.stderr
        assert (sentinel.read_bytes(), sentinel.stat().st_mode & 0o777) == before


def test_installer_lock_open_rejects_wrong_mode_and_non_regular_paths(
    tmp_path: Path,
):
    child = tmp_path / "child.sh"
    child.write_text("#!/bin/sh\nexit 0\n")
    child.chmod(0o755)
    wrong_mode = tmp_path / "wrong-mode.lock"
    wrong_mode.write_bytes(b"preserve\n")
    wrong_mode.chmod(0o644)
    directory = tmp_path / "directory.lock"
    directory.mkdir()
    fifo = tmp_path / "fifo.lock"
    os.mkfifo(fifo)

    for unsafe in (wrong_mode, directory, fifo):
        result = _run_installer_lock_helper(unsafe, child)
        assert result.returncode != 0
        assert "release_transfer_gate_install_failed" in result.stderr
    assert wrong_mode.read_bytes() == b"preserve\n"
    assert wrong_mode.stat().st_mode & 0o777 == 0o644


def test_installer_lock_open_creates_reuses_and_holds_exclusive_lock(
    tmp_path: Path,
):
    child = tmp_path / "child.sh"
    result_file = tmp_path / "ran"
    child.write_text(f'#!/bin/sh\nprintf "ran\\n" >> {str(result_file)!r}\n')
    child.chmod(0o755)
    lock = tmp_path / "install.lock"
    env: dict[str, str] = {}

    first = _run_installer_lock_helper(lock, child, env=env)
    second = _run_installer_lock_helper(lock, child, env=env)
    assert first.returncode == second.returncode == 0
    assert lock.is_file() and not lock.is_symlink()
    assert lock.stat().st_nlink == 1
    assert lock.stat().st_mode & 0o777 == 0o600
    assert result_file.read_text().splitlines() == ["ran", "ran"]

    ready = tmp_path / "holder-ready"
    child.write_text(f'#!/bin/sh\n: > {str(ready)!r}\nsleep 0.4\n')
    holder = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-",
            str(os.getuid()),
            str(os.getgid()),
            str(lock),
            str(child),
            str(tmp_path),
            str(tmp_path / "install-root"),
            str(tmp_path / "wrapper"),
            sys.executable,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    helper = INSTALLER.read_text().split("<<'PY_LOCK'\n", 1)[1].split(
        "\nPY_LOCK\n", 1
    )[0]
    assert holder.stdin is not None
    holder.stdin.write(helper)
    holder.stdin.close()
    for _ in range(100):
        if ready.exists():
            break
        time.sleep(0.01)
    else:
        pytest.fail("installer lock holder did not become ready")
    contender = _run_installer_lock_helper(lock, child)
    assert contender.returncode != 0
    assert "release_transfer_gate_install_failed" in contender.stderr
    assert holder.wait(timeout=2) == 0


def test_installer_lock_reexec_drops_bash_and_python_injection_environment(
    tmp_path: Path,
):
    sentinel = tmp_path / "sentinel"
    bash_env = tmp_path / "bash-env"
    bash_env.write_text(f'printf hacked > {str(sentinel)!r}\n')
    child = tmp_path / "child.sh"
    child.write_text("#!/bin/sh\nexit 0\n")
    child.chmod(0o755)

    result = _run_installer_lock_helper(
        tmp_path / "install.lock",
        child,
        env={
            "BASH_ENV": str(bash_env),
            "ENV": str(bash_env),
            "PYTHONPATH": str(tmp_path),
            "PYTHONHOME": str(tmp_path),
        },
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


def test_installer_python_helpers_and_runtime_gate_use_isolated_mode(
    tmp_path: Path,
):
    text = INSTALLER.read_text()
    logical_lines = text.replace("\\\n", " ").splitlines()
    helper_invocations = [
        line.strip()
        for line in logical_lines
        if line.lstrip().startswith(('"$PYTHON_BIN"', 'exec "$PYTHON_BIN"'))
    ]
    assert helper_invocations
    assert all('"$PYTHON_BIN" -I ' in line for line in helper_invocations)
    assert "PYTHONPATH=" not in text
    assert 'exec "$PYTHON_BIN" -I "$GATE"' in text

    malicious_cwd = tmp_path / "malicious-cwd"
    malicious_cwd.mkdir()
    sentinel = tmp_path / "sentinel"
    for name in ("pathlib.py", "release_transfer_gate.py"):
        (malicious_cwd / name).write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed')\n"
        )
    helper = text.split("<<'PY_LOCK'\n", 1)[1].split("\nPY_LOCK\n", 1)[0]
    lock = tmp_path / "safe.lock"
    child = tmp_path / "child.sh"
    child.write_text("#!/bin/sh\nexit 0\n")
    child.chmod(0o755)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(os.getuid()),
            str(os.getgid()),
            str(lock),
            str(child),
            str(tmp_path),
            str(tmp_path / "install-root"),
            str(tmp_path / "wrapper"),
            sys.executable,
        ],
        input=helper,
        cwd=malicious_cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


def test_installed_gate_loads_exact_sibling_contract_not_cwd_or_pythonpath(
    tmp_path: Path,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    gate = runtime / "release_transfer_gate.py"
    contract = runtime / "release_transfer.py"
    gate.write_bytes((REPO_ROOT / "deploy/lighthouse/release_transfer_gate.py").read_bytes())
    contract.write_bytes((REPO_ROOT / "scripts/release_transfer.py").read_bytes())
    malicious = tmp_path / "malicious"
    (malicious / "scripts").mkdir(parents=True)
    sentinel = tmp_path / "sentinel"
    (malicious / "scripts" / "__init__.py").write_text("")
    (malicious / "scripts" / "release_transfer.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
        "raise RuntimeError('malicious contract imported')\n"
    )

    result = subprocess.run(
        [sys.executable, "-I", str(gate), "--help"],
        cwd=malicious,
        env={**os.environ, "PYTHONPATH": str(malicious)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


def test_installed_gate_fails_stably_when_exact_sibling_contract_is_missing(
    tmp_path: Path,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    gate = runtime / "release_transfer_gate.py"
    gate.write_bytes((REPO_ROOT / "deploy/lighthouse/release_transfer_gate.py").read_bytes())

    result = subprocess.run(
        [sys.executable, "-I", str(gate), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 126
    assert "release_transfer_runtime_invalid" in result.stderr
    assert "Traceback" not in result.stderr


def test_versioned_wrapper_pointer_observes_only_complete_old_or_new_bundle(
    tmp_path: Path,
):
    versions = tmp_path / "versions"
    versions.mkdir()
    observed: set[tuple[str, str]] = set()
    for version in ("old", "new"):
        runtime = versions / version
        runtime.mkdir()
        (runtime / "release_transfer.py").write_text(f"contract-{version}\n")
        (runtime / "release_transfer_gate.py").write_text(f"gate-{version}\n")
        (runtime / "release-transfer-gate").write_text("wrapper\n")
    pointer = tmp_path / "gate"
    pointer.symlink_to(versions / "old" / "release-transfer-gate")

    stop = threading.Event()

    def observe() -> None:
        while not stop.is_set():
            runtime = pointer.resolve(strict=True).parent
            observed.add(
                (
                    (runtime / "release_transfer.py").read_text().strip(),
                    (runtime / "release_transfer_gate.py").read_text().strip(),
                )
            )

    worker = threading.Thread(target=observe)
    worker.start()
    replacement = tmp_path / ".pointer"
    replacement.symlink_to(versions / "new" / "release-transfer-gate")
    os.replace(replacement, pointer)
    time.sleep(0.01)
    rollback = tmp_path / ".rollback"
    rollback.symlink_to(versions / "old" / "release-transfer-gate")
    os.replace(rollback, pointer)
    stop.set()
    worker.join(timeout=1)

    assert observed <= {
        ("contract-old", "gate-old"),
        ("contract-new", "gate-new"),
    }
    assert ("contract-new", "gate-new") in observed
    assert pointer.resolve(strict=True).parent == versions / "old"


def test_atomic_rename_compatibility_probe_is_real_and_self_cleaning(tmp_path: Path):
    staging = tmp_path / "staging"
    release = tmp_path / "release"
    staging.mkdir(mode=0o700)
    release.mkdir()

    gate_module.verify_atomic_rename_compatibility(staging, release)

    assert list(staging.iterdir()) == []
    assert list(release.iterdir()) == []


def test_atomic_rename_compatibility_rejects_cross_mount_or_unknown_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    staging = tmp_path / "staging"
    release = tmp_path / "release"
    staging.mkdir(mode=0o700)
    release.mkdir()

    original_rename = gate_module._rename_noreplace
    failed = False

    def fail_contract_move_once(source: Path, destination: Path) -> None:
        nonlocal failed
        if not failed and source.parent == staging and destination.parent == release:
            failed = True
            raise GateError("fixture EXDEV")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", fail_contract_move_once)
    with pytest.raises(GateError, match="fixture EXDEV"):
        gate_module.verify_atomic_rename_compatibility(staging, release)
    assert list(staging.iterdir()) == []
    assert list(release.iterdir()) == []


@pytest.mark.parametrize("foreign_kind", ["directory", "file", "symlink"])
def test_atomic_rename_compatibility_preserves_destination_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    foreign_kind: str,
):
    staging = tmp_path / "staging"
    release = tmp_path / "release"
    staging.mkdir(mode=0o700)
    release.mkdir()
    foreign: Path | None = None

    original_rename = gate_module._rename_noreplace

    def create_foreign_then_fail(source: Path, destination: Path) -> None:
        nonlocal foreign
        if source.parent == staging and destination.parent == release:
            foreign = destination
            if foreign_kind == "directory":
                destination.mkdir()
            elif foreign_kind == "file":
                destination.write_text("foreign\n")
            else:
                destination.symlink_to(tmp_path / "outside")
            raise GateError("release promotion destination already exists")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", create_foreign_then_fail)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module.verify_atomic_rename_compatibility(staging, release)
    assert foreign is not None
    if foreign_kind == "directory":
        assert foreign.is_dir()
    elif foreign_kind == "file":
        assert foreign.read_text() == "foreign\n"
    else:
        assert foreign.is_symlink()
    assert list(staging.iterdir()) == []


def test_atomic_rename_compatibility_commit_then_exception_cleans_owned_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    staging = tmp_path / "staging"
    release = tmp_path / "release"
    staging.mkdir(mode=0o700)
    release.mkdir()
    original_rename = gate_module._rename_noreplace

    def rename_then_interrupt(source: Path, destination: Path) -> None:
        original_rename(source, destination)
        if source.parent == staging and destination.parent == release:
            raise GateError("release transfer interrupted")

    monkeypatch.setattr(gate_module, "_rename_noreplace", rename_then_interrupt)
    with pytest.raises(GateError, match="interrupted"):
        gate_module.verify_atomic_rename_compatibility(staging, release)
    assert list(staging.iterdir()) == []
    assert list(release.iterdir()) == []


def test_owned_file_cleanup_preserves_replacement_created_before_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    owned = tmp_path / "owned"
    displaced = tmp_path / "displaced-owned"
    owned.write_bytes(b"owned bytes")
    intent = gate_module._PathMutationIntent(attempted=True)
    gate_module._record_created_path(intent, owned.lstat())
    original_rename = gate_module._rename_noreplace
    swapped = False

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal swapped
        if source == owned and not swapped:
            swapped = True
            os.replace(source, displaced)
            source.write_bytes(b"foreign replacement")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", swap_before_quarantine)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._unlink_owned_file(owned, intent, label="fixture")

    assert owned.read_bytes() == b"foreign replacement"
    assert displaced.read_bytes() == b"owned bytes"
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_owned_file_postquarantine_validation_interrupt_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    owned = tmp_path / "owned"
    owned.write_bytes(b"owned bytes")
    intent = gate_module._PathMutationIntent(attempted=True)
    gate_module._record_created_path(intent, owned.lstat())

    monkeypatch.setattr(
        gate_module,
        "_matches_created_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            GateError("release transfer interrupted")
        ),
    )
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._unlink_owned_file(owned, intent, label="fixture")

    assert not owned.exists()
    quarantined = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"owned bytes"
    assert intent.cleanup_failed is True


def test_owned_file_postquarantine_read_fault_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    owned = tmp_path / "owned"
    owned.write_bytes(b"owned bytes")
    intent = gate_module._PathMutationIntent(attempted=True)
    gate_module._record_created_path(intent, owned.lstat())
    original_read = Path.read_bytes

    def fail_quarantine_read(path: Path) -> bytes:
        if path.parent == tmp_path and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture quarantine read failure")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", fail_quarantine_read)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._unlink_owned_file(
            owned,
            intent,
            label="fixture",
            expected_bytes=b"owned bytes",
        )

    assert not owned.exists()
    quarantined = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_file()
    assert intent.cleanup_failed is True


def test_owned_directory_cleanup_preserves_replacement_created_before_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    owned = tmp_path / "owned"
    displaced = tmp_path / "displaced-owned"
    owned.mkdir()
    intent = gate_module._PathMutationIntent(attempted=True)
    gate_module._record_created_path(intent, owned.lstat())
    original_rename = gate_module._rename_noreplace
    swapped = False

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal swapped
        if source == owned and not swapped:
            swapped = True
            os.replace(source, displaced)
            source.mkdir()
            (source / "foreign").write_text("replacement\n")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", swap_before_quarantine)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._remove_owned_directory(
            owned,
            intent,
            label="fixture",
            validator=lambda directory: not any(directory.iterdir()),
        )

    assert (owned / "foreign").read_text() == "replacement\n"
    assert displaced.is_dir()
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_owned_directory_postquarantine_validation_interrupt_restores_and_fails_manual(
    tmp_path: Path,
):
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "evidence").write_text("owned\n")
    intent = gate_module._PathMutationIntent(attempted=True)
    gate_module._record_created_path(intent, owned.lstat())

    with pytest.raises(GateError, match="manual recovery"):
        gate_module._remove_owned_directory(
            owned,
            intent,
            label="fixture",
            validator=lambda _directory: (_ for _ in ()).throw(SystemExit(143)),
        )

    assert (owned / "evidence").read_text() == "owned\n"
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_atomic_rename_verifier_cleanup_preserves_postcheck_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    staging = tmp_path / "staging"
    release = tmp_path / "release"
    staging.mkdir(mode=0o700)
    release.mkdir()
    displaced = release / "displaced-owned"
    replacement: Path | None = None
    original_rename = gate_module._rename_noreplace

    def swap_verifier_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal replacement
        if (
            source.parent == release
            and source.name.startswith(".rename-contract-")
            and destination.name.startswith(".release-cleanup-")
        ):
            replacement = source
            os.replace(source, displaced)
            source.mkdir()
            (source / "foreign").write_text("replacement\n")
        original_rename(source, destination)

    monkeypatch.setattr(
        gate_module,
        "_rename_noreplace",
        swap_verifier_before_quarantine,
    )
    with pytest.raises(GateError, match="manual recovery"):
        gate_module.verify_atomic_rename_compatibility(staging, release)

    assert replacement is not None
    assert (replacement / "foreign").read_text() == "replacement\n"
    assert displaced.is_dir()
    assert list(release.glob(".release-cleanup-*")) == []


def test_cleanup_is_idempotent_and_can_remove_exact_partial_transaction(tmp_path: Path):
    identity = _identity()
    cleanup_incoming(tmp_path, identity)
    incoming = tmp_path / identity.incoming_directory
    incoming.mkdir()
    write_state_marker(incoming, identity, "downloading")
    (incoming / "partial").write_bytes(b"partial")
    cleanup_incoming(tmp_path, identity)
    assert not incoming.exists()


def test_cleanup_fails_if_concurrent_promotion_wins_after_entry_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    final = tmp_path / identity.final_directory
    original_remove = gate_module._remove_owned_directory
    raced = False

    def promote_before_cleanup_remove(*args, **kwargs):
        nonlocal raced
        directory = args[0]
        if directory == incoming and not raced:
            raced = True
            promote_incoming(tmp_path, identity)
        return original_remove(*args, **kwargs)

    monkeypatch.setattr(
        gate_module,
        "_remove_owned_directory",
        promote_before_cleanup_remove,
    )
    with pytest.raises(GateError, match="final release path exists"):
        cleanup_incoming(tmp_path, identity)

    assert raced is True
    assert final.is_dir()
    assert not incoming.exists()


def test_idempotent_cleanup_rechecks_final_after_probe_cleanup_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity = _identity()
    final = tmp_path / identity.final_directory
    original_remove_probe = gate_module._remove_probe_receipt

    def create_final_during_probe_cleanup(root: Path, actual: GateIdentity) -> None:
        original_remove_probe(root, actual)
        final.mkdir()

    monkeypatch.setattr(
        gate_module,
        "_remove_probe_receipt",
        create_final_during_probe_cleanup,
    )
    with pytest.raises(GateError, match="final release path exists"):
        cleanup_incoming(tmp_path, identity)

    assert final.is_dir()


def test_cleanup_incoming_preserves_postvalidation_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity = _identity()
    incoming = tmp_path / identity.incoming_directory
    displaced = tmp_path / "displaced-incoming"
    incoming.mkdir()
    write_state_marker(incoming, identity, "downloading")
    (incoming / "partial").write_bytes(b"owned partial")
    original_rename = gate_module._rename_noreplace
    swapped = False

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal swapped
        if source == incoming and not swapped:
            swapped = True
            os.replace(source, displaced)
            source.mkdir()
            (source / "foreign").write_text("replacement\n")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", swap_before_quarantine)
    with pytest.raises(GateError, match="manual recovery"):
        cleanup_incoming(tmp_path, identity)

    assert (incoming / "foreign").read_text() == "replacement\n"
    assert (displaced / "partial").read_bytes() == b"owned partial"
    assert list(tmp_path.glob(".release-cleanup-*")) == []


def test_probe_receipt_cleanup_preserves_postvalidation_file_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    _install_fast_probe_download(monkeypatch)
    run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    receipt = root / identity.probe_file
    displaced = root / "displaced-probe-receipt"
    original_rename = gate_module._rename_noreplace
    swapped = False

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal swapped
        if source == receipt and not swapped:
            swapped = True
            os.replace(source, displaced)
            source.write_text("foreign replacement\n")
        original_rename(source, destination)

    monkeypatch.setattr(gate_module, "_rename_noreplace", swap_before_quarantine)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._remove_probe_receipt(root, identity)

    assert receipt.read_text() == "foreign replacement\n"
    assert displaced.is_file()
    assert list(root.glob(".release-cleanup-*")) == []


def test_staging_root_and_transaction_ownership_boundaries_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    tmp_path.chmod(0o777)
    with pytest.raises(GateError, match="ownership or mode"):
        cleanup_incoming(tmp_path, _identity())
    tmp_path.chmod(0o700)

    identity, incoming = _verified_transaction(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"shared")
    os.link(outside, incoming / "unexpected-hardlink")
    with pytest.raises(GateError, match="hard link"):
        promote_incoming(tmp_path, identity)

    (incoming / "unexpected-hardlink").unlink()

    def fail_process_reference(*args):
        del args
        raise GateError("fixture process reference")

    monkeypatch.setattr(
        gate_module,
        "_assert_no_process_references",
        fail_process_reference,
    )
    with pytest.raises(GateError, match="process reference"):
        promote_incoming(tmp_path, identity)
    assert incoming.is_dir()


def test_cleanup_mount_ambiguity_never_enters_destructive_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    identity, incoming = _verified_transaction(tmp_path)
    calls = 0

    def reject_mount(_directory: Path):
        nonlocal calls
        calls += 1
        raise GateError("fixture mount boundary")

    monkeypatch.setattr(gate_module, "_assert_no_mount_boundaries", reject_mount)
    with pytest.raises(GateError, match="mount boundary"):
        cleanup_incoming(tmp_path, identity)
    assert calls == 1
    assert incoming.is_dir()
    assert "shutil.rmtree(incoming)" not in Path(gate_module.__file__).read_text()


def test_gate_main_emits_bounded_phase_specific_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        gate_module,
        "run_probe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(GateError("secret fixture")),
    )
    monkeypatch.setattr(
        gate_module.sys,
        "argv",
        [
            "release_transfer_gate.py",
            "--role",
            "staging",
            "--command",
            f"probe {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
        ],
    )
    assert gate_module.main() == 126
    terminal = json.loads(capsys.readouterr().err)
    assert terminal == {
        "schema_version": "release-transfer-gate-terminal.v1",
        "status": "failed",
        "code": "server_probe_failed",
    }


def _stage_fixture(tmp_path: Path) -> tuple[Path, GateIdentity, bytes, dict[str, Path]]:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    source_archive = bundle / f"release-source-{SOURCE_SHA}.tar.gz"
    app = tarfile.TarInfo("app.py")
    app.mode = 0o644
    app.size = len(b"print('ok')\n")
    _tar(source_archive, [(app, b"print('ok')\n")])
    source_digest = hashlib.sha256(source_archive.read_bytes()).hexdigest()
    (bundle / f"release-source-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{source_digest}  {source_archive.name}\n"
    )
    app_digest = hashlib.sha256(b"print('ok')\n").hexdigest()
    (bundle / "source-manifest.v1.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "source-manifest.v1",
                "git_sha": SOURCE_SHA,
                "files": [
                    {
                        "path": "app.py",
                        "size_bytes": len(b"print('ok')\n"),
                        "sha256": app_digest,
                    }
                ],
            }
        )
    )
    image_archive = bundle / f"release-images-{SOURCE_SHA}.tar.gz"
    manifest_member = tarfile.TarInfo("manifest.json")
    manifest_member.size = 2
    _tar(image_archive, [(manifest_member, b"{}")])
    image_digest = hashlib.sha256(image_archive.read_bytes()).hexdigest()
    (bundle / f"release-images-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{image_digest}  {image_archive.name}\n"
    )
    (bundle / "image-digests.txt").write_text(
        "\n".join(f"sha256:{character * 64}" for character in "123") + "\n"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    manifest = build_transfer_manifest(
        bundle_root=bundle,
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        github_artifact_id=98765,
        github_artifact_digest=f"sha256:{'f' * 64}",
        cos_bucket="ai-video-release-1250000000",
        cos_endpoint_host="cos.ap-shanghai.myqcloud.com",
        created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    identity = GateIdentity(
        SOURCE_SHA,
        12345,
        1,
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    (root / identity.probe_file).write_bytes(
        canonical_json_bytes(
            {
                "status": "passed",
                "transferred_bytes": PROBE_SIZE_BYTES,
                "elapsed_nanoseconds": 16_000_000_000,
                "bytes_per_second": 4_194_304,
                "estimated_release_seconds": 525,
                "bucket": "ai-video-release-1250000000",
                "endpoint_host": "cos.ap-shanghai.myqcloud.com",
            }
        )
    )
    files = {path.name: path for path in bundle.iterdir()}
    urls = {
        name: f"https://ai-video-release-1250000000.cos.ap-shanghai.myqcloud.com/{name}?signature=fixture"
        for name in files
    }
    payload = canonical_json_bytes(
        {
            "schema_version": "release-transfer-urls.v1",
            "manifest_sha256": identity.manifest_sha256,
            "deadline_seconds_remaining": 1_800,
            "urls": urls,
        }
    )
    return root, identity, payload, files


def test_stage_release_downloads_verifies_extracts_and_emits_secret_free_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, files = _stage_fixture(tmp_path)

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
        intent: Any = None,
    ):
        del deadline_ns, intent
        name = Path(url.split("?", 1)[0]).name
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_download", fake_download)
    receipt = stage_release(root, identity, io.BytesIO(payload))
    incoming = root / identity.incoming_directory
    assert receipt["state"] == "verified"
    assert (incoming / "app.py").read_text() == "print('ok')\n"
    assert json.loads((incoming / ".release-transfer-state.v1.json").read_text())[
        "state"
    ] == "verified"
    all_bytes = b"".join(
        path.read_bytes()
        for path in incoming.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    assert b"signature=fixture" not in all_bytes
    assert b"https://" not in all_bytes


@pytest.mark.parametrize("ambient_umask", [0o077, 0o027])
def test_stage_and_promotion_preserve_source_modes_under_hostile_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambient_umask: int,
):
    root, identity, payload, files = _stage_fixture(tmp_path)

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_download", fake_download)
    previous = os.umask(ambient_umask)
    try:
        stage_release(root, identity, io.BytesIO(payload))
        promoted = promote_incoming(root, identity)
    finally:
        os.umask(previous)

    assert promoted.stat().st_mode & 0o777 == 0o755
    assert (promoted / "app.py").stat().st_mode & 0o777 == 0o644


def test_stage_failure_removes_partial_incoming_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, files = _stage_fixture(tmp_path)
    request = json.loads(payload)
    request["urls"].pop("image-digests.txt")

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        source = files[name]
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_download", fake_download)
    with pytest.raises(GateError, match="exact file set"):
        stage_release(root, identity, io.BytesIO(canonical_json_bytes(request)))
    assert not (root / identity.incoming_directory).exists()


def test_stage_rejects_manifest_url_for_another_valid_bucket_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _files = _stage_fixture(tmp_path)
    request = json.loads(payload)
    request["urls"]["release-transfer-manifest.v1.json"] = (
        "https://other-release-1250000000.cos.ap-shanghai.myqcloud.com/"
        "release-transfer-manifest.v1.json?signature=fixture"
    )
    called = False

    def forbidden_download(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("download must not be reached")

    monkeypatch.setattr(gate_module, "_download", forbidden_download)
    with pytest.raises(GateError, match="signed URL"):
        stage_release(root, identity, io.BytesIO(canonical_json_bytes(request)))
    assert called is False
    assert not (root / identity.incoming_directory).exists()


def test_stage_system_exit_is_normalized_and_removes_incoming_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _files = _stage_fixture(tmp_path)

    def interrupted_download(
        _url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del maximum_bytes, deadline_ns
        destination.write_bytes(b"partial")
        raise SystemExit(143)

    monkeypatch.setattr(gate_module, "_download", interrupted_download)
    with pytest.raises(GateError, match="interrupted"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not (root / identity.incoming_directory).exists()


def test_stage_deadline_covers_post_download_validation_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, files = _stage_fixture(tmp_path)
    downloads = 0
    deadline_expired = False

    def fake_remaining(_deadline: int, _maximum: int) -> float:
        if deadline_expired:
            raise GateError("release transfer deadline exceeded")
        return 60.0

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        nonlocal downloads, deadline_expired
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        downloads += 1
        if downloads == len(files):
            deadline_expired = True
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_remaining_timeout", fake_remaining)
    monkeypatch.setattr(gate_module, "_download", fake_download)
    with pytest.raises(GateError, match="deadline"):
        stage_release(root, identity, io.BytesIO(payload))
    assert downloads == len(files)
    assert not (root / identity.incoming_directory).exists()


def test_stage_deadline_context_exit_failure_cleans_verified_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, files = _stage_fixture(tmp_path)

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    @gate_module.contextlib.contextmanager
    def fail_on_context_exit(_deadline_ns: int):
        yield
        raise GateError("release transfer deadline exceeded")

    monkeypatch.setattr(gate_module, "_download", fake_download)
    monkeypatch.setattr(gate_module, "_deadline_alarm", fail_on_context_exit)
    with pytest.raises(GateError, match="deadline exceeded"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not (root / identity.incoming_directory).exists()


def test_gate_download_rejects_redirect_without_contacting_target(tmp_path: Path):
    contacts = {"target": 0}

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            contacts["target"] += 1
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Target)

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target.server_address[1]}/capture",
            )
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    redirect = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    for server in (target, redirect):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    destination = tmp_path / "probe.part"
    try:
        with pytest.raises(GateError, match="download failed"):
            gate_module._download(
                f"http://127.0.0.1:{redirect.server_address[1]}/signed?secret=fixture",
                destination,
                maximum_bytes=32,
            )
        assert contacts["target"] == 0
        assert not destination.exists()
    finally:
        redirect.shutdown()
        target.shutdown()


def test_gate_download_framing_error_removes_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        gate_module._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            http.client.BadStatusLine("fixture")
        ),
    )
    destination = tmp_path / "download.part"
    with pytest.raises(GateError, match="download failed"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
        )
    assert not destination.exists()


def test_gate_download_shared_deadline_cleans_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls = 0

    def bounded_remaining(_deadline: int, _maximum: int) -> float:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise GateError("release transfer deadline exceeded")
        return 1.0

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int) -> bytes:
            return b"slow"

    monkeypatch.setattr(gate_module, "_deadline_alarm", lambda _deadline: nullcontext())
    monkeypatch.setattr(gate_module, "_remaining_timeout", bounded_remaining)
    monkeypatch.setattr(
        gate_module._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: Response(),
    )
    destination = tmp_path / "deadline.part"
    with pytest.raises(GateError, match="deadline"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
            deadline_ns=gate_module.time.monotonic_ns() + 1_000_000_000,
        )
    assert not destination.exists()


def test_gate_download_open_race_preserves_concurrent_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "race.part"
    original_open = gate_module.os.open

    def create_winner_then_fail(path, flags, mode=0o777, *args, **kwargs):
        if Path(path) == destination:
            descriptor = original_open(path, flags, mode, *args, **kwargs)
            gate_module.os.write(descriptor, b"concurrent winner")
            gate_module.os.close(descriptor)
            raise FileExistsError("fixture concurrent winner")
        return original_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(gate_module.os, "open", create_winner_then_fail)
    with pytest.raises(GateError, match="already exists"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
        )
    assert destination.read_bytes() == b"concurrent winner"


def test_gate_download_inode_swap_preserves_foreign_and_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "swap.part"

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int) -> bytes:
            destination.unlink()
            destination.write_bytes(b"foreign replacement")
            raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(
        gate_module._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: Response(),
    )
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
        )
    assert destination.read_bytes() == b"foreign replacement"


def test_gate_download_system_exit_removes_owned_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "interrupt.part"

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int) -> bytes:
            raise SystemExit(143)

    monkeypatch.setattr(
        gate_module._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: Response(),
    )
    with pytest.raises(GateError, match="interrupted"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
        )
    assert not destination.exists()


def test_gate_download_cleanup_double_fault_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "cleanup.part"
    original_unlink = Path.unlink

    def fail_destination_unlink(path: Path, *args, **kwargs):
        if path.parent == tmp_path and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture download cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        gate_module._NO_REDIRECT_OPENER,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            http.client.BadStatusLine("fixture")
        ),
    )
    monkeypatch.setattr(Path, "unlink", fail_destination_unlink)
    with pytest.raises(GateError, match="manual recovery"):
        gate_module._download(
            "https://bucket.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            destination,
            maximum_bytes=32,
        )
    assert not destination.exists()
    quarantined = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_file()


@pytest.mark.parametrize(
    "url",
    [
        "https://bucket.cos.ap-shanghai.myqcloud.com:8443/object?fixture=1",
        "https://bucket.cos.ap-shanghai.myqcloud.com:invalid/object?fixture=1",
    ],
)
def test_gate_rejects_nonstandard_or_malformed_signed_url_port(url: str):
    with pytest.raises(GateError, match="signed URL is invalid"):
        gate_module._validate_url(
            url,
            expected_host="bucket.cos.ap-shanghai.myqcloud.com",
        )


def test_stage_initialization_failures_leave_no_bare_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _ = _stage_fixture(tmp_path)
    monkeypatch.setattr(
        gate_module,
        "write_state_marker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(GateError("marker failed")),
    )
    with pytest.raises(GateError, match="marker failed"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not (root / identity.incoming_directory).exists()


def test_stage_directory_commit_then_exception_removes_owned_empty_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _ = _stage_fixture(tmp_path)
    original_create = gate_module._create_transaction_directory

    def create_then_interrupt(path: Path, intent: Any) -> None:
        original_create(path, intent)
        raise GateError("release transfer interrupted")

    monkeypatch.setattr(gate_module, "_create_transaction_directory", create_then_interrupt)
    with pytest.raises(GateError, match="interrupted"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not (root / identity.incoming_directory).exists()


def test_stage_directory_race_is_preserved_for_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _ = _stage_fixture(tmp_path)
    incoming = root / identity.incoming_directory

    def create_foreign_then_interrupt(path: Path, _intent: Any) -> None:
        path.mkdir(mode=0o700)
        (path / "foreign").write_text("not this transaction\n")
        raise GateError("release transfer interrupted")

    monkeypatch.setattr(
        gate_module,
        "_create_transaction_directory",
        create_foreign_then_interrupt,
    )
    with pytest.raises(GateError, match="manual recovery"):
        stage_release(root, identity, io.BytesIO(payload))
    assert (incoming / "foreign").read_text() == "not this transaction\n"


def test_stage_directory_cleanup_double_failure_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _ = _stage_fixture(tmp_path)
    incoming = root / identity.incoming_directory
    original_create = gate_module._create_transaction_directory
    original_rmdir = Path.rmdir

    def create_then_interrupt(path: Path, intent: Any) -> None:
        original_create(path, intent)
        raise GateError("release transfer interrupted")

    def fail_incoming_rmdir(path: Path, *args, **kwargs):
        if path.parent == root and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture incoming cleanup failure")
        return original_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(gate_module, "_create_transaction_directory", create_then_interrupt)
    monkeypatch.setattr(Path, "rmdir", fail_incoming_rmdir)
    with pytest.raises(GateError, match="manual recovery"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not incoming.exists()
    quarantined = list(root.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_dir()


def test_stage_artifact_directory_failure_cleans_initialized_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, _ = _stage_fixture(tmp_path)
    original_mkdir = Path.mkdir

    def fail_artifacts(path: Path, *args, **kwargs):
        if path.name == ".artifacts":
            raise OSError("fixture artifacts mkdir failure")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_artifacts)
    with pytest.raises(GateError, match="staging failed"):
        stage_release(root, identity, io.BytesIO(payload))
    assert not (root / identity.incoming_directory).exists()


def test_stage_expired_manifest_stops_before_any_large_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, old_identity, payload, files = _stage_fixture(tmp_path)
    manifest_path = files["release-transfer-manifest.v1.json"]
    manifest = json.loads(manifest_path.read_text())
    now = datetime.now(UTC).replace(microsecond=0)
    manifest["created_at"] = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["expires_at"] = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    identity = GateIdentity(
        SOURCE_SHA,
        old_identity.workflow_run_id,
        old_identity.workflow_run_attempt,
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    (root / old_identity.probe_file).rename(root / identity.probe_file)
    request = json.loads(payload)
    request["manifest_sha256"] = identity.manifest_sha256
    downloaded: list[str] = []

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        downloaded.append(name)
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_download", fake_download)
    with pytest.raises(GateError, match="expired"):
        stage_release(root, identity, io.BytesIO(canonical_json_bytes(request)))
    assert downloaded == ["release-transfer-manifest.v1.json"]
    assert not (root / identity.incoming_directory).exists()


def test_stage_rechecks_expiry_between_large_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, identity, payload, files = _stage_fixture(tmp_path)
    expiry_checks = 0
    downloaded: list[str] = []
    original_expiry = gate_module._assert_manifest_not_expired

    def cross_expiry(manifest: dict[str, object]):
        nonlocal expiry_checks
        expiry_checks += 1
        if expiry_checks == 3:
            raise GateError("fixture manifest has expired")
        original_expiry(manifest)

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        downloaded.append(name)
        source = files[name]
        assert source.stat().st_size <= maximum_bytes
        destination.write_bytes(source.read_bytes())
        return source.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_assert_manifest_not_expired", cross_expiry)
    monkeypatch.setattr(gate_module, "_download", fake_download)
    with pytest.raises(GateError, match="expired"):
        stage_release(root, identity, io.BytesIO(payload))
    assert len(downloaded) == 2
    assert downloaded[0] == "release-transfer-manifest.v1.json"
    assert not (root / identity.incoming_directory).exists()


def test_stage_recomputes_manifest_bound_duration_before_large_file_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root, old_identity, payload, files = _stage_fixture(tmp_path)
    manifest_path = files["release-transfer-manifest.v1.json"]
    manifest = json.loads(manifest_path.read_text())
    image_entry = next(
        entry for entry in manifest["files"] if entry["role"] == "image_archive"
    )
    image_entry["size_bytes"] = 8 * 1024 * 1024 * 1024
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    identity = GateIdentity(
        SOURCE_SHA,
        12345,
        1,
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    os.replace(root / old_identity.probe_file, root / identity.probe_file)
    request = json.loads(payload)
    request["manifest_sha256"] = identity.manifest_sha256
    calls: list[str] = []

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
    ):
        del deadline_ns
        name = Path(url.split("?", 1)[0]).name
        calls.append(name)
        assert name == "release-transfer-manifest.v1.json"
        assert manifest_path.stat().st_size <= maximum_bytes
        destination.write_bytes(manifest_path.read_bytes())
        return manifest_path.stat().st_size, 1

    monkeypatch.setattr(gate_module, "_download", fake_download)
    with pytest.raises(GateError, match="staging failed"):
        stage_release(root, identity, io.BytesIO(canonical_json_bytes(request)))
    assert calls == ["release-transfer-manifest.v1.json"]
    assert not (root / identity.incoming_directory).exists()


@pytest.mark.parametrize("corrupt", [False, True])
def test_probe_requires_exact_zero_filled_sha_before_speed_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: bool,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    payload = canonical_json_bytes(
        {
            "schema_version": "release-transfer-probe-url.v1",
            "manifest_sha256": identity.manifest_sha256,
            "release_bytes": 2_200_000_000,
            "deadline_seconds_remaining": 1_800,
            "bucket": "ai-video-release-1250000000",
            "endpoint_host": "cos.ap-shanghai.myqcloud.com",
            "url": "https://ai-video-release-1250000000.cos.ap-shanghai.myqcloud.com/probe?signature=fixture",
        }
    )

    def fake_download(
        url: str,
        destination: Path,
        *,
        maximum_bytes: int,
        deadline_ns: int | None = None,
        intent: Any = None,
    ):
        del deadline_ns
        del url
        assert maximum_bytes == PROBE_SIZE_BYTES
        with destination.open("wb") as stream:
            if corrupt:
                stream.write(b"x")
            stream.seek(PROBE_SIZE_BYTES - 1)
            stream.write(b"\0")
        if intent is not None:
            gate_module._record_created_path(intent, destination.lstat())
        return PROBE_SIZE_BYTES, 16_000_000_000

    monkeypatch.setattr(gate_module, "_download", fake_download)
    if corrupt:
        with pytest.raises(GateError, match="checksum"):
            run_probe(root, identity, io.BytesIO(payload))
        assert not (root / identity.probe_file).exists()
        assert not (
            root
            / f".probe-{identity.source_revision}-{identity.workflow_run_id}-"
            f"{identity.workflow_run_attempt}.part"
        ).exists()
    else:
        result = run_probe(root, identity, io.BytesIO(payload))
        assert result["status"] == "passed"
        assert (root / identity.probe_file).is_file()


def test_probe_outer_cleanup_preserves_concurrent_download_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    probe_path = root / (
        f".probe-{identity.source_revision}-{identity.workflow_run_id}-"
        f"{identity.workflow_run_attempt}.part"
    )

    def create_winner_then_fail(*_args, **_kwargs):
        probe_path.write_bytes(b"concurrent winner")
        raise GateError("download destination already exists or is unsafe")

    monkeypatch.setattr(gate_module, "_download", create_winner_then_fail)
    with pytest.raises(GateError, match="already exists"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert probe_path.read_bytes() == b"concurrent winner"


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_probe_rejects_existing_receipt_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_kind: str,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    if existing_kind == "file":
        receipt_path.write_text("existing\n")
    else:
        receipt_path.symlink_to(tmp_path / "outside")
    called = False

    def forbidden_download(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("download must not be reached")

    monkeypatch.setattr(gate_module, "_download", forbidden_download)
    with pytest.raises(GateError, match="probe receipt already exists"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert called is False
    if existing_kind == "file":
        assert receipt_path.read_text() == "existing\n"
    else:
        assert receipt_path.is_symlink()


def test_probe_deadline_after_receipt_commit_rolls_back_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)
    original_remaining = gate_module._remaining_timeout

    def expire_after_receipt(deadline_ns: int, maximum_seconds: int) -> float:
        if receipt_path.exists():
            raise GateError("release transfer deadline exceeded")
        return original_remaining(deadline_ns, maximum_seconds)

    monkeypatch.setattr(gate_module, "_remaining_timeout", expire_after_receipt)
    with pytest.raises(GateError, match="deadline exceeded"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()
    with pytest.raises(GateError, match="probe receipt"):
        gate_module._load_probe(root, identity)


def test_probe_signal_after_receipt_commit_rolls_back_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)

    @gate_module.contextlib.contextmanager
    def interrupted_after_body(_deadline_ns: int):
        yield
        raise GateError("release transfer interrupted")

    monkeypatch.setattr(gate_module, "_deadline_alarm", interrupted_after_body)
    with pytest.raises(GateError, match="interrupted"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()
    with pytest.raises(GateError, match="probe receipt"):
        gate_module._load_probe(root, identity)


def test_probe_receipt_rollback_failure_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)
    original_remaining = gate_module._remaining_timeout
    original_unlink = Path.unlink

    def expire_after_receipt(deadline_ns: int, maximum_seconds: int) -> float:
        if receipt_path.exists():
            raise GateError("release transfer deadline exceeded")
        return original_remaining(deadline_ns, maximum_seconds)

    def fail_receipt_unlink(path: Path, *args, **kwargs):
        if path.parent == root and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture receipt rollback failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(gate_module, "_remaining_timeout", expire_after_receipt)
    monkeypatch.setattr(Path, "unlink", fail_receipt_unlink)
    with pytest.raises(GateError, match="manual recovery"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()
    quarantined = list(root.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_file()


def test_probe_receipt_commit_then_exception_rolls_back_owned_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)
    original_write = gate_module._atomic_write

    def commit_then_interrupt(path: Path, payload: bytes, **kwargs) -> None:
        original_write(path, payload, **kwargs)
        if path == receipt_path:
            raise GateError("release transfer interrupted")

    monkeypatch.setattr(gate_module, "_atomic_write", commit_then_interrupt)
    with pytest.raises(GateError, match="interrupted"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()
    with pytest.raises(GateError, match="probe receipt"):
        gate_module._load_probe(root, identity)


def test_probe_mid_write_interrupt_removes_owned_partial_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)
    original_fsync = gate_module.os.fsync

    def interrupt_receipt_fsync(descriptor: int) -> None:
        if (
            receipt_path.exists()
            and gate_module.os.fstat(descriptor).st_ino == receipt_path.stat().st_ino
        ):
            raise SystemExit(143)
        original_fsync(descriptor)

    monkeypatch.setattr(gate_module.os, "fsync", interrupt_receipt_fsync)
    with pytest.raises(GateError, match="interrupted"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()


def test_probe_mid_write_cleanup_failure_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)
    original_fsync = gate_module.os.fsync
    original_unlink = Path.unlink

    def interrupt_receipt_fsync(descriptor: int) -> None:
        if (
            receipt_path.exists()
            and gate_module.os.fstat(descriptor).st_ino == receipt_path.stat().st_ino
        ):
            raise SystemExit(143)
        original_fsync(descriptor)

    def fail_receipt_unlink(path: Path, *args, **kwargs):
        if path.parent == root and path.name.startswith(".release-cleanup-"):
            raise OSError("fixture partial receipt cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(gate_module.os, "fsync", interrupt_receipt_fsync)
    monkeypatch.setattr(Path, "unlink", fail_receipt_unlink)
    with pytest.raises(GateError, match="manual recovery"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert not receipt_path.exists()
    quarantined = list(root.glob(".release-cleanup-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_file()


def test_probe_receipt_race_is_not_deleted_and_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    receipt_path = root / identity.probe_file
    _install_fast_probe_download(monkeypatch)

    def create_foreign_receipt(path: Path, _payload: bytes, **_kwargs) -> None:
        assert path == receipt_path
        path.write_text("foreign receipt\n")
        raise GateError("release transfer output already exists or is unsafe")

    monkeypatch.setattr(gate_module, "_atomic_write", create_foreign_receipt)
    with pytest.raises(GateError, match="manual recovery"):
        run_probe(root, identity, io.BytesIO(_probe_payload(identity)))
    assert receipt_path.read_text() == "foreign receipt\n"


def test_probe_rejects_nonregional_or_wrong_bucket_host_before_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    identity = _identity()
    called = False

    def forbidden_download(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("download must not be reached")

    monkeypatch.setattr(gate_module, "_download", forbidden_download)
    payload = canonical_json_bytes(
        {
            "schema_version": "release-transfer-probe-url.v1",
            "manifest_sha256": identity.manifest_sha256,
            "release_bytes": 2_200_000_000,
            "deadline_seconds_remaining": 1_800,
            "bucket": "ai-video-release-1250000000",
            "endpoint_host": "attacker-controlled.myqcloud.com",
            "url": "https://attacker-controlled.myqcloud.com/probe?fixture=1",
        }
    )
    with pytest.raises(GateError, match="probe endpoint"):
        run_probe(root, identity, io.BytesIO(payload))
    assert called is False


def test_gate_deep_json_emits_canonical_terminal_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    deep = ("[" * 10_000 + "0" + "]" * 10_000).encode()
    monkeypatch.setattr(gate_module.sys, "stdin", io.TextIOWrapper(io.BytesIO(deep)))
    monkeypatch.setattr(
        gate_module.sys,
        "argv",
        [
            "release_transfer_gate.py",
            "--role",
            "staging",
            "--command",
            f"probe {SOURCE_SHA} 12345 1 {MANIFEST_SHA}",
            "--staging-root",
            str(root),
        ],
    )
    assert gate_module.main() == 126
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert json.loads(stderr)["code"] == "server_probe_failed"
