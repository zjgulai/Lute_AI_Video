"""Fail-closed contracts for exact release artifacts relayed through COS."""

from __future__ import annotations

import copy
import hashlib
import http.client
import http.server
import io
import json
import os
import stat
import threading
import urllib.error
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import cast

import pytest

import scripts.release_transfer as transfer_module
from scripts.release_transfer import (
    PROBE_SIZE_BYTES,
    TransferContractError,
    build_transfer_manifest,
    build_transfer_receipt,
    canonical_json_bytes,
    evaluate_probe,
    plan_shared_object_uploads,
    validate_transfer_manifest,
    validate_transfer_receipt,
    verify_bucket_never_versioned,
    verify_shared_object_readback,
)

SOURCE_SHA = "a" * 40
IMAGE_IDS = [f"sha256:{character * 64}" for character in "123"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path) -> None:
    source_archive = root / f"release-source-{SOURCE_SHA}.tar.gz"
    image_archive = root / f"release-images-{SOURCE_SHA}.tar.gz"
    source_archive.write_bytes(b"source-archive")
    image_archive.write_bytes(b"image-archive")
    (root / f"release-source-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{_sha(source_archive)}  {source_archive.name}\n",
        encoding="utf-8",
    )
    (root / f"release-images-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{_sha(image_archive)}  {image_archive.name}\n",
        encoding="utf-8",
    )
    (root / "source-manifest.v1.json").write_text(
        json.dumps(
            {"schema_version": "source-manifest.v1", "git_sha": SOURCE_SHA, "files": []},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "image-digests.txt").write_text("\n".join(IMAGE_IDS) + "\n", encoding="utf-8")


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    _write_bundle(tmp_path)
    return tmp_path


def _manifest(bundle: Path) -> dict[str, object]:
    return build_transfer_manifest(
        bundle_root=bundle,
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        github_artifact_id=98765,
        github_artifact_digest=f"sha256:{'f' * 64}",
        cos_bucket="ai-video-release-1250000000",
        cos_endpoint_host="cos.ap-shanghai.myqcloud.com",
        created_at="2026-08-13T03:00:00Z",
        expires_at="2026-08-13T05:00:00Z",
    )


def test_manifest_is_canonical_content_addressed_and_provider_off(bundle: Path):
    manifest = _manifest(bundle)
    validated = validate_transfer_manifest(manifest, bundle_root=bundle)

    image_sha = _sha(bundle / f"release-images-{SOURCE_SHA}.tar.gz")
    expected_prefix = f"ai-video/releases/{SOURCE_SHA}/{image_sha}"
    cos = cast(dict[str, object], manifest["cos"])
    files = cast(list[dict[str, object]], manifest["files"])
    assert validated == manifest
    assert cos["object_prefix"] == expected_prefix
    assert manifest["manifest_object_key"] == (
        f"{expected_prefix}/transactions/12345/1/"
        "release-transfer-manifest.v1.json"
    )
    assert [entry["role"] for entry in files] == [
        "source_archive",
        "source_checksum",
        "source_manifest",
        "image_archive",
        "image_checksum",
        "image_digests",
    ]
    assert manifest["policy"] == {
        "provider_off": True,
        "provider_call": False,
        "w5_submit": False,
        "publish": False,
        "delivery": False,
    }
    assert canonical_json_bytes(manifest).endswith(b"\n")
    assert canonical_json_bytes(manifest) == canonical_json_bytes(validated)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["files"].reverse(), "file order"),
        (lambda value: value["image_ids"].append(IMAGE_IDS[0]), "image"),
        (lambda value: value["policy"].update({"provider_call": True}), "policy"),
        (lambda value: value["cos"].update({"object_prefix": "latest"}), "prefix"),
        (lambda value: value.update({"unexpected": True}), "fields"),
    ],
)
def test_manifest_rejects_identity_or_authority_mutation(bundle: Path, mutation, message):
    payload = copy.deepcopy(_manifest(bundle))
    mutation(payload)
    with pytest.raises(TransferContractError, match=message):
        validate_transfer_manifest(payload, bundle_root=bundle)


def test_manifest_rejects_artifact_and_checksum_mutation(bundle: Path):
    payload = _manifest(bundle)
    (bundle / f"release-images-{SOURCE_SHA}.tar.gz").write_bytes(b"changed")
    with pytest.raises(TransferContractError, match="checksum"):
        validate_transfer_manifest(payload, bundle_root=bundle)

    _write_bundle(bundle)
    (bundle / f"release-images-{SOURCE_SHA}.tar.gz.sha256").write_text(
        f"{'0' * 64}  release-images-{SOURCE_SHA}.tar.gz\n",
        encoding="utf-8",
    )
    with pytest.raises(TransferContractError, match="detached checksum"):
        build_transfer_manifest(
            bundle_root=bundle,
            source_revision=SOURCE_SHA,
            workflow_run_id=12345,
            workflow_run_attempt=1,
            github_artifact_id=98765,
            github_artifact_digest=f"sha256:{'f' * 64}",
            cos_bucket="ai-video-release-1250000000",
            cos_endpoint_host="cos.ap-shanghai.myqcloud.com",
            created_at="2026-08-13T03:00:00Z",
            expires_at="2026-08-13T05:00:00Z",
        )


def test_manifest_expiry_is_bounded(bundle: Path):
    payload = _manifest(bundle)
    payload["expires_at"] = "2026-08-13T05:00:01Z"
    with pytest.raises(TransferContractError, match="expiry"):
        validate_transfer_manifest(payload)


def test_exclusive_write_interrupt_removes_runner_local_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "manifest.json"
    original_fsync = transfer_module.os.fsync

    def interrupt_fsync(descriptor: int) -> None:
        if output.exists() and transfer_module.os.fstat(descriptor).st_ino == output.stat().st_ino:
            raise TransferContractError("release transfer interrupted")
        original_fsync(descriptor)

    monkeypatch.setattr(transfer_module.os, "fsync", interrupt_fsync)
    with pytest.raises(TransferContractError, match="interrupted"):
        transfer_module.write_exclusive(output, b'{"fixture":true}\n')
    assert not output.exists()


def test_exclusive_write_interrupt_cleanup_failure_requires_manual_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "manifest.json"
    original_fsync = transfer_module.os.fsync
    original_unlink = Path.unlink

    def interrupt_fsync(descriptor: int) -> None:
        if output.exists() and transfer_module.os.fstat(descriptor).st_ino == output.stat().st_ino:
            raise TransferContractError("release transfer interrupted")
        original_fsync(descriptor)

    def fail_output_unlink(path: Path, *args, **kwargs):
        if path.name == "owned" and path.parent.name.startswith(".release-cleanup-"):
            raise OSError("fixture runner output cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(transfer_module.os, "fsync", interrupt_fsync)
    monkeypatch.setattr(Path, "unlink", fail_output_unlink)
    with pytest.raises(TransferContractError, match="manual recovery"):
        transfer_module.write_exclusive(output, b'{"fixture":true}\n')
    assert not output.exists()
    quarantines = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "owned").is_file()


def test_exclusive_write_cleanup_preserves_postcheck_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "manifest.json"
    displaced = tmp_path / "displaced-output"
    original_fsync = transfer_module.os.fsync
    original_rename = transfer_module.os.rename
    swapped = False

    def interrupt_fsync(descriptor: int) -> None:
        if output.exists() and transfer_module.os.fstat(descriptor).st_ino == output.stat().st_ino:
            raise TransferContractError("release transfer interrupted")
        original_fsync(descriptor)

    def swap_before_quarantine(source: Path, destination: Path) -> None:
        nonlocal swapped
        if Path(source) == output and not swapped:
            swapped = True
            os.replace(source, displaced)
            output.write_text("foreign replacement\n")
        original_rename(source, destination)

    monkeypatch.setattr(transfer_module.os, "fsync", interrupt_fsync)
    monkeypatch.setattr(transfer_module.os, "rename", swap_before_quarantine)
    with pytest.raises(TransferContractError, match="manual recovery"):
        transfer_module.write_exclusive(output, b'{"fixture":true}\n')

    assert not output.exists()
    assert displaced.read_bytes() == b'{"fixture":true}\n'
    quarantines = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "owned").read_text() == "foreign replacement\n"


def test_exclusive_write_postquarantine_validation_interrupt_is_manual(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "manifest.json"
    original_fsync = transfer_module.os.fsync
    original_lstat = Path.lstat

    def interrupt_fsync(descriptor: int) -> None:
        if output.exists() and transfer_module.os.fstat(descriptor).st_ino == output.stat().st_ino:
            raise TransferContractError("release transfer interrupted")
        original_fsync(descriptor)

    def interrupt_quarantine_validation(path: Path):
        if path.name == "owned" and path.parent.name.startswith(".release-cleanup-"):
            raise SystemExit(143)
        return original_lstat(path)

    monkeypatch.setattr(transfer_module.os, "fsync", interrupt_fsync)
    monkeypatch.setattr(Path, "lstat", interrupt_quarantine_validation)
    with pytest.raises(TransferContractError, match="manual recovery"):
        transfer_module.write_exclusive(output, b'{"fixture":true}\n')

    assert not output.exists()
    quarantines = list(tmp_path.glob(".release-cleanup-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "owned").is_file()


def test_exclusive_write_preserves_preexisting_output(tmp_path: Path):
    output = tmp_path / "manifest.json"
    output.write_text("foreign\n")
    with pytest.raises(TransferContractError, match="already exists"):
        transfer_module.write_exclusive(output, b'{"fixture":true}\n')
    assert output.read_text() == "foreign\n"


@pytest.mark.parametrize(
    "endpoint",
    [
        "attacker-controlled.myqcloud.com",
        "bucket-1250000000.cos.ap-shanghai.myqcloud.com",
        "cos.ap-shanghai.example.com",
        "cos.accelerate.myqcloud.com",
        "cos..myqcloud.com",
    ],
)
def test_manifest_requires_one_strict_regional_cos_endpoint(
    bundle: Path,
    endpoint: str,
):
    payload = _manifest(bundle)
    cast(dict[str, object], payload["cos"])["endpoint_host"] = endpoint
    with pytest.raises(TransferContractError, match="endpoint"):
        validate_transfer_manifest(payload)


def test_manifest_rejects_role_specific_download_size_expansion(bundle: Path):
    payload = _manifest(bundle)
    files = cast(list[dict[str, object]], payload["files"])
    source_manifest = next(entry for entry in files if entry["role"] == "source_manifest")
    source_manifest["size_bytes"] = 16 * 1024 * 1024 + 1
    with pytest.raises(TransferContractError, match="role limit"):
        validate_transfer_manifest(payload)


def test_probe_gate_uses_exact_bytes_monotonic_duration_and_both_thresholds():
    passed = evaluate_probe(
        transferred_bytes=PROBE_SIZE_BYTES,
        elapsed_nanoseconds=16_000_000_000,
        release_bytes=2_200_000_000,
    )
    assert passed["bytes_per_second"] == 4_194_304
    assert passed["estimated_release_seconds"] == 525
    assert passed["status"] == "passed"

    with pytest.raises(TransferContractError, match="throughput"):
        evaluate_probe(
            transferred_bytes=PROBE_SIZE_BYTES,
            elapsed_nanoseconds=33_000_000_000,
            release_bytes=2_200_000_000,
        )
    with pytest.raises(TransferContractError, match="estimated duration"):
        evaluate_probe(
            transferred_bytes=PROBE_SIZE_BYTES,
            elapsed_nanoseconds=32_000_000_000,
            release_bytes=4_000_000_000,
        )


def test_probe_rejects_wrong_size_and_nonpositive_duration():
    with pytest.raises(TransferContractError, match="size"):
        evaluate_probe(
            transferred_bytes=PROBE_SIZE_BYTES - 1,
            elapsed_nanoseconds=1,
            release_bytes=1,
        )
    with pytest.raises(TransferContractError, match="duration"):
        evaluate_probe(
            transferred_bytes=PROBE_SIZE_BYTES,
            elapsed_nanoseconds=0,
            release_bytes=1,
        )


def test_receipt_is_bounded_canonical_and_contains_no_secret_or_url(bundle: Path):
    manifest = _manifest(bundle)
    manifest_sha = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    now = datetime(2026, 8, 13, 3, tzinfo=UTC)
    receipt = build_transfer_receipt(
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        manifest_sha256=manifest_sha,
        incoming_directory=f".incoming-{SOURCE_SHA}-12345-1",
        completed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        probe={
            "status": "passed",
            "transferred_bytes": PROBE_SIZE_BYTES,
            "elapsed_nanoseconds": 16_000_000_000,
            "bytes_per_second": 4_194_304,
            "estimated_release_seconds": 525,
        },
    )
    assert validate_transfer_receipt(receipt) == receipt
    encoded = canonical_json_bytes(receipt)
    assert len(encoded) < 16 * 1024
    for forbidden in (b"https://", b"secret", b"token", b"/home/runner"):
        assert forbidden not in encoded.lower()


def test_receipt_rejects_nonverified_or_path_drift(bundle: Path):
    manifest = _manifest(bundle)
    manifest_sha = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    receipt = build_transfer_receipt(
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        manifest_sha256=manifest_sha,
        incoming_directory=f".incoming-{SOURCE_SHA}-12345-1",
        completed_at="2026-08-13T03:30:00Z",
        expires_at="2026-08-13T05:00:00Z",
        probe={
            "status": "passed",
            "transferred_bytes": PROBE_SIZE_BYTES,
            "elapsed_nanoseconds": 16_000_000_000,
            "bytes_per_second": 4_194_304,
            "estimated_release_seconds": 525,
        },
    )
    receipt["state"] = "downloaded"
    with pytest.raises(TransferContractError, match="state"):
        validate_transfer_receipt(receipt)

    receipt["state"] = "verified"
    receipt["incoming_directory"] = "../escape"
    with pytest.raises(TransferContractError, match="incoming"):
        validate_transfer_receipt(receipt)


def test_resume_plan_reuses_only_exact_readback_and_uploads_missing(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest = _manifest(bundle)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    signed: list[str] = []
    missing_sha = cast(list[dict[str, object]], manifest["files"])[2]["sha256"]

    def fake_sign(**kwargs):
        object_key = cast(str, kwargs["object_key"])
        signed.append(object_key)
        return f"https://ai-video-release-1250000000.cos.ap-shanghai.myqcloud.com/{object_key}?sig=fixture"

    def fake_readback(**kwargs):
        return kwargs["expected_sha256"] != missing_sha

    monkeypatch.setattr(transfer_module, "_signed_object_url", fake_sign)
    monkeypatch.setattr(transfer_module, "_object_readback_matches", fake_readback)
    planned = plan_shared_object_uploads(
        manifest_path=manifest_path,
        resume=True,
    )
    files = cast(list[dict[str, object]], manifest["files"])
    assert planned == [files[2]]
    assert len(signed) == len(files)


@pytest.mark.parametrize(
    "operation",
    [plan_shared_object_uploads, verify_shared_object_readback],
)
def test_resume_readback_urls_are_clamped_to_explicit_remaining_deadline(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(_manifest(bundle)))
    signed: list[int] = []

    def fake_sign(**kwargs):
        signed.append(cast(int, kwargs["validity_seconds"]))
        return (
            f"https://{kwargs['bucket']}.{kwargs['endpoint_host']}/"
            f"{kwargs['object_key']}?sig=fixture"
        )

    monkeypatch.setattr(transfer_module, "_signed_object_url", fake_sign)
    monkeypatch.setattr(
        transfer_module,
        "_object_readback_matches",
        lambda **_kwargs: True,
    )
    deadline = transfer_module.time.monotonic_ns() + 120 * 1_000_000_000

    kwargs = {"manifest_path": manifest_path, "deadline_ns": deadline}
    if operation is plan_shared_object_uploads:
        kwargs["resume"] = True
    result = operation(**kwargs)

    if operation is plan_shared_object_uploads:
        assert result == []
    assert signed
    assert all(60 <= validity <= 120 for validity in signed)


@pytest.mark.parametrize(
    "operation",
    [plan_shared_object_uploads, verify_shared_object_readback],
)
def test_resume_readback_rejects_less_than_one_minute_before_signing(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(_manifest(bundle)))
    monkeypatch.setattr(
        transfer_module,
        "_signed_object_url",
        lambda **_kwargs: pytest.fail("resume signer must not run"),
    )
    monkeypatch.setattr(
        transfer_module,
        "_object_readback_matches",
        lambda **_kwargs: pytest.fail("resume readback must not run"),
    )
    deadline = transfer_module.time.monotonic_ns() + 59 * 1_000_000_000

    with pytest.raises(TransferContractError, match="validity"):
        kwargs = {"manifest_path": manifest_path, "deadline_ns": deadline}
        if operation is plan_shared_object_uploads:
            kwargs["resume"] = True
        operation(**kwargs)


def test_shared_object_readback_fails_when_any_object_is_missing(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(_manifest(bundle)))
    monkeypatch.setattr(
        transfer_module,
        "plan_shared_object_uploads",
        lambda **kwargs: [{"path": "missing"}],
    )
    with pytest.raises(TransferContractError, match="incomplete"):
        verify_shared_object_readback(
            manifest_path=manifest_path,
        )


def test_one_byte_readback_requires_exact_range_size_metadata_and_endpoint(
    monkeypatch: pytest.MonkeyPatch,
):
    endpoint = "cos.ap-shanghai.myqcloud.com"
    url = f"https://bucket-1250000000.{endpoint}/object?sig=fixture"

    class Response:
        status = 206
        headers = {
            "Content-Range": "bytes 0-0/123",
            "x-cos-meta-ai-video-sha256": "a" * 64,
            "x-cos-meta-ai-video-size": "123",
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self):
            return url

        def read(self, size: int):
            assert size == 2
            return b"x"

    monkeypatch.setattr(transfer_module, "_open_no_redirect", lambda *args, **kwargs: Response())
    assert transfer_module._object_readback_matches(
        url=url,
        bucket="bucket-1250000000",
        endpoint_host=endpoint,
        expected_size=123,
        expected_sha256="a" * 64,
    )

    Response.headers = {**Response.headers, "x-cos-meta-ai-video-size": "124"}
    with pytest.raises(TransferContractError, match="identity"):
        transfer_module._object_readback_matches(
            url=url,
            bucket="bucket-1250000000",
            endpoint_host=endpoint,
            expected_size=123,
            expected_sha256="a" * 64,
        )

    def missing(*args, **kwargs):
        del args, kwargs
        raise urllib.error.HTTPError(url, 404, "missing", Message(), None)

    monkeypatch.setattr(transfer_module, "_open_no_redirect", missing)
    assert not transfer_module._object_readback_matches(
        url=url,
        bucket="bucket-1250000000",
        endpoint_host=endpoint,
        expected_size=123,
        expected_sha256="a" * 64,
    )


def test_cos_readback_rejects_redirect_without_contacting_target():
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
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (target, redirect)
    ]
    for thread in threads:
        thread.start()
    try:
        request = transfer_module.urllib.request.Request(
            f"http://127.0.0.1:{redirect.server_address[1]}/signed?secret=fixture"
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            transfer_module._open_no_redirect(request, timeout=2)
        assert caught.value.code == 302
        assert contacts["target"] == 0
    finally:
        redirect.shutdown()
        target.shutdown()
        for thread in threads:
            thread.join(timeout=5)
        redirect.server_close()
        target.server_close()


def test_cos_readback_http_framing_error_is_stable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        transfer_module,
        "_open_no_redirect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            http.client.IncompleteRead(b"x", 2)
        ),
    )
    with pytest.raises(TransferContractError, match="readback failed"):
        transfer_module._object_readback_matches(
            url="https://bucket-1250000000.cos.ap-shanghai.myqcloud.com/object?fixture=1",
            bucket="bucket-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            expected_size=2,
            expected_sha256="a" * 64,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://bucket-1250000000.cos.ap-shanghai.myqcloud.com:8443/object?fixture=1",
        "https://bucket-1250000000.cos.ap-shanghai.myqcloud.com:invalid/object?fixture=1",
    ],
)
def test_cos_readback_rejects_nonstandard_or_malformed_port(url: str):
    with pytest.raises(TransferContractError, match="URL is invalid"):
        transfer_module._validate_readback_url(
            url,
            bucket="bucket-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
        )


def test_bucket_must_have_never_enabled_versioning(monkeypatch: pytest.MonkeyPatch):
    responses = [
        b'<VersioningConfiguration xmlns="http://www.qcloud.com/"/>',
        b'<VersioningConfiguration xmlns="http://www.qcloud.com/"><Status>Suspended</Status></VersioningConfiguration>',
        b'<VersioningConfiguration xmlns="http://www.qcloud.com/"><Status>Enabled</Status></VersioningConfiguration>',
    ]

    def response(*_args, **_kwargs):
        return responses.pop(0), {}, 200

    monkeypatch.setattr(transfer_module, "_cos_request", response)
    verify_bucket_never_versioned(
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
    )
    for _ in range(2):
        with pytest.raises(TransferContractError, match="never enabled"):
            verify_bucket_never_versioned(
                bucket="ai-video-release-1250000000",
                endpoint_host="cos.ap-shanghai.myqcloud.com",
            )


def test_tracked_release_governance_contract_and_cam_policy_are_exact():
    contract_path = (
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    contract = transfer_module.load_release_governance_contract(contract_path)
    policy = transfer_module.build_expected_cam_policy(
        contract=contract,
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
    )
    assert any(
        statement["action"]
        == [
            "name/cos:GetBucketACL",
            "name/cos:GetBucketLifecycle",
            "name/cos:GetBucketPolicy",
            "name/cos:GetBucketVersioning",
        ]
        for statement in cast(list[dict[str, object]], policy["statement"])
    )
    assert transfer_module.validate_cam_policy_readback(
        policy,
        contract=contract,
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
    ) == policy
    assert hashlib.sha256(canonical_json_bytes(policy)).hexdigest() == (
        transfer_module.expected_cam_policy_sha256(
            contract=contract,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            source_revision=SOURCE_SHA,
            workflow_run_id=12345,
            workflow_run_attempt=1,
        )
    )

    mutated_contract = copy.deepcopy(contract)
    cast(
        list[dict[str, object]],
        cast(dict[str, object], mutated_contract["cam_policy"])["statement_templates"],
    )[1]["actions"] = ["name/cos:*"]
    with pytest.raises(TransferContractError, match="CAM policy"):
        transfer_module.validate_release_governance_contract(mutated_contract)

    for section, field, replacement, message in (
        ("privacy", "acl", "public-read", "privacy"),
        ("privacy", "bucket_policy", "present", "privacy"),
        ("sts", "audience", "attacker.invalid", "STS"),
        ("sts", "github_repository", "attacker/repo", "STS"),
    ):
        mutated_contract = copy.deepcopy(contract)
        cast(dict[str, object], mutated_contract[section])[field] = replacement
        with pytest.raises(TransferContractError, match=message):
            transfer_module.validate_release_governance_contract(mutated_contract)

    for field, replacement in (
        ("action", ["name/cos:*"]),
        ("resource", ["*"]),
        ("condition", {"ip_equal": {"qcs:ip": "0.0.0.0/0"}}),
    ):
        mutated = copy.deepcopy(policy)
        cast(list[dict[str, object]], mutated["statement"])[1][field] = replacement
        with pytest.raises(TransferContractError, match="CAM policy"):
            transfer_module.validate_cam_policy_readback(
                mutated,
                contract=contract,
                bucket="ai-video-release-1250000000",
                endpoint_host="cos.ap-shanghai.myqcloud.com",
                source_revision=SOURCE_SHA,
                workflow_run_id=12345,
                workflow_run_attempt=1,
            )


def test_cos_lifecycle_readback_requires_exact_three_rules(
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    exact = b"""<LifecycleConfiguration xmlns="http://www.qcloud.com/">
      <Rule><ID>ai-video-probes-expire-v1</ID><Filter><Prefix>ai-video/probes/</Prefix></Filter><Status>Enabled</Status><Expiration><Days>1</Days></Expiration></Rule>
      <Rule><ID>ai-video-release-multipart-abort-v1</ID><Filter><Prefix>ai-video/releases/</Prefix></Filter><Status>Enabled</Status><AbortIncompleteMultipartUpload><DaysAfterInitiation>1</DaysAfterInitiation></AbortIncompleteMultipartUpload></Rule>
      <Rule><ID>ai-video-releases-expire-v1</ID><Filter><Prefix>ai-video/releases/</Prefix></Filter><Status>Enabled</Status><Expiration><Days>14</Days></Expiration></Rule>
    </LifecycleConfiguration>"""
    payloads = [
        exact,
        exact.replace(b"<Days>14</Days>", b"<Days>15</Days>"),
        exact.replace(
            b"</LifecycleConfiguration>",
            b"<Rule><ID>extra</ID><Filter><Prefix>other/</Prefix></Filter><Status>Enabled</Status><Expiration><Days>1</Days></Expiration></Rule></LifecycleConfiguration>",
        ),
        exact.replace(
            b"<Expiration><Days>14</Days></Expiration>",
            b"<Expiration><Days>14</Days><Date>2026-08-15T00:00:00Z</Date></Expiration>",
        ),
    ]

    def response(*_args, **_kwargs):
        return payloads.pop(0), {}, 200

    monkeypatch.setattr(transfer_module, "_cos_request", response)
    assert transfer_module.verify_bucket_lifecycle_governance(
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        contract=contract,
    ) == cast(dict[str, object], contract["lifecycle"])["rules"]
    for _ in range(3):
        with pytest.raises(TransferContractError, match="lifecycle"):
            transfer_module.verify_bucket_lifecycle_governance(
                bucket="ai-video-release-1250000000",
                endpoint_host="cos.ap-shanghai.myqcloud.com",
                contract=contract,
            )


def test_jit_sts_window_is_exact_and_has_cleanup_margin():
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    result = transfer_module.validate_sts_window(
        duration_seconds=7200,
        expires_at="2026-08-14T03:00:00Z",
        now=datetime(2026, 8, 14, 2, 0, 0, tzinfo=UTC),
        contract=contract,
    )
    assert result["duration_seconds"] == 7200
    assert result["remaining_seconds"] == 3600
    assert result["cleanup_reserve_seconds"] == 300

    for duration_seconds, expires_at, now in (
        (
            7199,
            "2026-08-14T02:59:59Z",
            datetime(2026, 8, 14, 2, 0, 0, tzinfo=UTC),
        ),
        (
            7200,
            "2026-08-14T03:00:00Z",
            datetime(2026, 8, 14, 2, 0, 1, tzinfo=UTC),
        ),
    ):
        with pytest.raises(TransferContractError, match="STS"):
            transfer_module.validate_sts_window(
                duration_seconds=duration_seconds,
                expires_at=expires_at,
                now=now,
                contract=contract,
            )


class _FixtureHTTPResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.status = status
        self.headers = Message()
        self._stream = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: object) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return transfer_module.base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{encode({'alg': 'RS256', 'kid': 'fixture'})}.{encode(payload)}.signature"


def test_github_oidc_is_exchanged_once_for_exact_tencent_role_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    token = _jwt(
        {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "sts.tencentcloudapi.com",
            "sub": "repo:zjgulai/Lute_AI_Video:environment:production-artifact-staging",
            "repository": "zjgulai/Lute_AI_Video",
            "sha": SOURCE_SHA,
            "run_id": "12345",
            "run_attempt": "1",
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp()) + 300,
        }
    )
    expiration = now + timedelta(seconds=7200)
    responses = [
        _FixtureHTTPResponse(
            canonical_json_bytes({"count": len(token), "value": token})
        ),
        _FixtureHTTPResponse(
            canonical_json_bytes(
                {
                    "Response": {
                        "Credentials": {
                            "Token": "SESSION_TOKEN_FIXTURE",
                            "TmpSecretId": "AKID_FIXTURE",
                            "TmpSecretKey": "SECRET_KEY_FIXTURE",
                        },
                        "ExpiredTime": int(expiration.timestamp()),
                        "Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "RequestId": "12345678-1234-1234-1234-1234567890ab",
                    }
                }
            )
        ),
    ]
    requests: list[transfer_module.urllib.request.Request] = []

    def open_once(request, **_kwargs):
        requests.append(request)
        return responses.pop(0)

    monkeypatch.setattr(transfer_module, "_open_no_redirect", open_once)
    credential_path = tmp_path / "cos-sts-credentials.json"
    receipt = transfer_module.assume_github_oidc_role(
        contract=contract,
        provider_id="GitHubActions",
        role_arn="qcs::cam::uin/1234567890:roleName/ai-video-release",
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        credentials_output=credential_path,
        request_url=(
            "https://pipelinesghubeus9.actions.githubusercontent.com/opaque/"
            "_apis/distributedtask/hubs/build/plans/p/jobs/j/idtoken?api-version=2.0"
        ),
        request_token="GITHUB_REQUEST_TOKEN_FIXTURE",
        now=now,
        deadline_ns=transfer_module.time.monotonic_ns() + 60_000_000_000,
    )

    assert len(requests) == 2
    assert requests[0].full_url.endswith(
        "api-version=2.0&audience=sts.tencentcloudapi.com"
    )
    assert requests[0].get_header("Authorization") == (
        "Bearer GITHUB_REQUEST_TOKEN_FIXTURE"
    )
    assert requests[1].full_url == "https://sts.tencentcloudapi.com/"
    assert requests[1].get_header("Authorization") == "SKIP"
    request_body = json.loads(cast(bytes, requests[1].data))
    assert request_body == {
        "DurationSeconds": 7200,
        "ProviderId": "GitHubActions",
        "RoleArn": "qcs::cam::uin/1234567890:roleName/ai-video-release",
        "RoleSessionName": "ai-video-12345-1",
        "WebIdentityToken": token,
    }
    assert stat.S_IMODE(credential_path.stat().st_mode) == 0o600
    assert receipt["request_id"] == "12345678-1234-1234-1234-1234567890ab"
    assert "credentials" not in receipt
    assert "SESSION_TOKEN_FIXTURE" not in canonical_json_bytes(receipt).decode()
    verified = transfer_module.validate_sts_credentials_file(
        path=credential_path,
        contract=contract,
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        provider_id="GitHubActions",
        role_arn="qcs::cam::uin/1234567890:roleName/ai-video-release",
        now=now + timedelta(seconds=1),
    )
    assert cast(int, verified["remaining_seconds"]) >= 7198


@pytest.mark.parametrize(
    "request_url",
    [
        "http://pipelines.actions.githubusercontent.com/opaque/_apis/token",
        "https://actions.githubusercontent.com.evil.example/_apis/token",
        "https://user@pipelines.actions.githubusercontent.com/opaque/_apis/token",
        "https://pipelines.actions.githubusercontent.com:bad/opaque/_apis/token",
        "https://[::1]/_apis/token",
        "https://pipelines.actions.githubusercontent.com/opaque/token",
    ],
)
def test_github_oidc_transport_rejects_non_github_or_malformed_endpoint(
    request_url: str,
):
    with pytest.raises(TransferContractError, match="OIDC request configuration"):
        transfer_module._github_oidc_token(
            request_url=request_url,
            request_token="fixture",
            audience="sts.tencentcloudapi.com",
            deadline_ns=transfer_module.time.monotonic_ns() + 10_000_000_000,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"count": True, "value": "token"},
        {"count": -1, "value": "token"},
        {"count": 1},
        {"value": 1},
        {"extra": "metadata", "value": "token"},
    ],
)
def test_github_oidc_response_envelope_rejects_unsafe_variants(
    payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        transfer_module,
        "_open_no_redirect",
        lambda *_args, **_kwargs: _FixtureHTTPResponse(canonical_json_bytes(payload)),
    )
    with pytest.raises(TransferContractError, match="OIDC"):
        transfer_module._github_oidc_token(
            request_url="https://pipelines.actions.githubusercontent.com/x/_apis/token",
            request_token="fixture",
            audience="sts.tencentcloudapi.com",
            deadline_ns=transfer_module.time.monotonic_ns() + 10_000_000_000,
        )


def test_github_oidc_response_accepts_large_nonnegative_count_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    token = "x" * 1390
    monkeypatch.setattr(
        transfer_module,
        "_open_no_redirect",
        lambda *_args, **_kwargs: _FixtureHTTPResponse(
            canonical_json_bytes({"count": len(token), "value": token})
        ),
    )
    assert transfer_module._github_oidc_token(
        request_url="https://pipelines.actions.githubusercontent.com/x/_apis/token",
        request_token="fixture",
        audience="sts.tencentcloudapi.com",
        deadline_ns=transfer_module.time.monotonic_ns() + 10_000_000_000,
    ) == token


def test_oidc_identity_mutation_fails_before_tencent_sts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    token = _jwt(
        {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "sts.tencentcloudapi.com",
            "sub": "repo:attacker/repo:environment:production-artifact-staging",
            "repository": "attacker/repo",
            "sha": SOURCE_SHA,
            "run_id": "12345",
            "run_attempt": "1",
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp()) + 300,
        }
    )
    requests = 0

    def open_once(*_args, **_kwargs):
        nonlocal requests
        requests += 1
        return _FixtureHTTPResponse(canonical_json_bytes({"value": token}))

    monkeypatch.setattr(transfer_module, "_open_no_redirect", open_once)
    with pytest.raises(TransferContractError, match="OIDC token identity"):
        transfer_module.assume_github_oidc_role(
            contract=contract,
            provider_id="GitHubActions",
            role_arn="qcs::cam::uin/1234567890:roleName/ai-video-release",
            source_revision=SOURCE_SHA,
            workflow_run_id=12345,
            workflow_run_attempt=1,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            credentials_output=tmp_path / "credentials.json",
            request_url=(
                "https://token.actions.githubusercontent.com/_apis/fixture?api-version=2.0"
            ),
            request_token="fixture",
            now=now,
            deadline_ns=transfer_module.time.monotonic_ns() + 60_000_000_000,
        )
    assert requests == 1
    assert not (tmp_path / "credentials.json").exists()


def test_cos_privacy_requires_owner_only_acl_and_no_bucket_policy(
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    owner = "qcs::cam::uin/1234567890:uin/1234567890"
    private_acl = f"""<AccessControlPolicy xmlns=\"http://www.qcloud.com/\">
      <Owner><ID>{owner}</ID><DisplayName>{owner}</DisplayName></Owner>
      <AccessControlList><Grant><Grantee xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:type=\"CanonicalUser\"><ID>{owner}</ID><DisplayName>{owner}</DisplayName></Grantee><Permission>FULL_CONTROL</Permission></Grant></AccessControlList>
    </AccessControlPolicy>""".encode()
    no_policy = b"<Error><Code>NoSuchBucketPolicy</Code><RequestId>fixture</RequestId></Error>"
    responses = [(private_acl, {}, 200), (no_policy, {}, 404)]
    monkeypatch.setattr(
        transfer_module,
        "_cos_request",
        lambda **_kwargs: responses.pop(0),
    )
    result = transfer_module.verify_bucket_privacy_governance(
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        contract=contract,
    )
    assert result == {
        "acl": "owner-full-control-only",
        "bucket_policy": "absent",
        "owner_id": owner,
    }

    for public_uri in (
        "http://cam.qcloud.com/groups/global/AllUsers",
        "http://cam.qcloud.com/groups/global/AuthenticatedUsers",
    ):
        public_acl = private_acl.replace(
            f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="CanonicalUser"><ID>{owner}</ID><DisplayName>{owner}</DisplayName></Grantee><Permission>FULL_CONTROL</Permission>'.encode(),
            f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Group"><URI>{public_uri}</URI></Grantee><Permission>READ</Permission>'.encode(),
        )
        responses[:] = [(public_acl, {}, 200)]
        with pytest.raises(TransferContractError, match="must be private"):
            transfer_module.verify_bucket_privacy_governance(
                bucket="ai-video-release-1250000000",
                endpoint_host="cos.ap-shanghai.myqcloud.com",
                contract=contract,
            )

    extra_grant = private_acl.replace(
        b"</AccessControlList>",
        b"<Grant><Grantee xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:type=\"CanonicalUser\"><ID>qcs::cam::uin/9999999999:uin/9999999999</ID><DisplayName>other</DisplayName></Grantee><Permission>READ</Permission></Grant></AccessControlList>",
    )
    responses[:] = [(extra_grant, {}, 200)]
    with pytest.raises(TransferContractError, match="must be private"):
        transfer_module.verify_bucket_privacy_governance(
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            contract=contract,
        )

    responses[:] = [(private_acl, {}, 200), (b'{"public":true}', {}, 200)]
    with pytest.raises(TransferContractError, match="policy must be absent"):
        transfer_module.verify_bucket_privacy_governance(
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            contract=contract,
        )
    responses[:] = [
        (private_acl, {}, 200),
        (b"<Error><Code>AccessDenied</Code></Error>", {}, 404),
    ]
    with pytest.raises(TransferContractError, match="policy must be absent"):
        transfer_module.verify_bucket_privacy_governance(
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            contract=contract,
        )


def test_cos_request_preserves_exact_expected_404_body(
    monkeypatch: pytest.MonkeyPatch,
):
    payload = b"<Error><Code>NoSuchBucketPolicy</Code></Error>"
    headers = Message()
    headers["Content-Type"] = "application/xml"

    def missing(request, **_kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "not found",
            headers,
            io.BytesIO(payload),
        )

    monkeypatch.setattr(transfer_module, "_credentials", lambda: ("id", "key", "token"))
    monkeypatch.setattr(transfer_module, "_open_no_redirect", missing)
    body, response_headers, status = transfer_module._cos_request(
        method="GET",
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        query={"policy": ""},
        expected_status={200, 404},
    )
    assert (body, status) == (payload, 404)
    assert response_headers["content-type"] == "application/xml"


def _cam_readback_responses(contract: dict[str, object]) -> dict[str, dict[str, object]]:
    policy = transfer_module.build_expected_cam_policy(
        contract=contract,
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
    )
    trust = {
        "version": "2.0",
        "statement": [
            {
                "action": "name/sts:AssumeRoleWithWebIdentity",
                "effect": "allow",
                "principal": {
                    "federated": [
                        "qcs::cam::uin/1234567890:oidc-provider/GitHubActions"
                    ]
                },
                "condition": {
                    "string_equal": {
                        "oidc:iss": ["https://token.actions.githubusercontent.com"],
                        "oidc:aud": ["sts.tencentcloudapi.com"],
                        "oidc:sub": [
                            "repo:zjgulai/Lute_AI_Video:environment:"
                            "production-artifact-staging"
                        ],
                    }
                },
            }
        ],
    }
    request_ids = {
        action: f"12345678-1234-1234-1234-{index:012d}"
        for index, action in enumerate(
            (
                "DescribeOIDCConfig",
                "GetRole",
                "ListAttachedRolePolicies",
                "ListPolicyVersions",
                "GetPolicyVersion",
                "GetRolePermissionBoundary",
            ),
            start=1,
        )
    }
    return {
        "DescribeOIDCConfig": {
            "ProviderType": 11,
            "IdentityUrl": "https://token.actions.githubusercontent.com",
            "IdentityKey": "eyJrZXlzIjpbXX0=",
            "ClientId": ["sts.tencentcloudapi.com"],
            "Status": 11,
            "Name": "GitHubActions",
            "AutoRotateKey": 1,
            "RequestId": request_ids["DescribeOIDCConfig"],
        },
        "GetRole": {
            "RoleInfo": {
                "RoleId": "4611686018427844696",
                "RoleName": "ai-video-release",
                "RoleArn": "qcs::cam::uin/1234567890:roleName/ai-video-release",
                "PolicyDocument": json.dumps(trust, separators=(",", ":")),
                "ConsoleLogin": 0,
                "RoleType": "user",
                "SessionDuration": 7200,
            },
            "RequestId": request_ids["GetRole"],
        },
        "ListAttachedRolePolicies": {
            "List": [
                {
                    "PolicyId": 10001,
                    "PolicyName": "ai-video-release-exact",
                    "PolicyType": "User",
                    "Deactived": 0,
                    "DeactivedDetail": [],
                }
            ],
            "TotalNum": 1,
            "RequestId": request_ids["ListAttachedRolePolicies"],
        },
        "ListPolicyVersions": {
            "Versions": [
                {"VersionId": 1, "IsDefaultVersion": 0},
                {"VersionId": 2, "IsDefaultVersion": 1},
            ],
            "RequestId": request_ids["ListPolicyVersions"],
        },
        "GetPolicyVersion": {
            "PolicyVersion": {
                "VersionId": 2,
                "IsDefaultVersion": 1,
                "Document": json.dumps(policy, separators=(",", ":")),
            },
            "RequestId": request_ids["GetPolicyVersion"],
        },
        "GetRolePermissionBoundary": {
            "PolicyId": None,
            "PolicyName": None,
            "PolicyDocument": None,
            "PolicyType": None,
            "CreateMode": None,
            "RequestId": request_ids["GetRolePermissionBoundary"],
        },
    }


def _cam_readback_credentials(path: Path, now: datetime) -> None:
    path.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "cam-readback-credentials.v1",
                "expiration": (now + timedelta(seconds=7200)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "credentials": {
                    "secret_id": "AKID_READBACK_FIXTURE",
                    "secret_key": "SECRET_READBACK_FIXTURE",
                    "session_token": "TOKEN_READBACK_FIXTURE",
                },
            }
        )
    )
    path.chmod(0o600)


def _cam_readback_call(
    contract: dict[str, object],
    credentials: Path,
    now: datetime,
) -> dict[str, object]:
    return transfer_module.readback_cam_effective_role(
        contract=contract,
        credentials_path=credentials,
        provider_id="GitHubActions",
        role_arn="qcs::cam::uin/1234567890:roleName/ai-video-release",
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        now=now,
        deadline_ns=transfer_module.time.monotonic_ns() + 60_000_000_000,
    )


def test_cam_effective_role_readback_is_live_complete_and_run_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    _cam_readback_credentials(credentials, now)
    responses = _cam_readback_responses(contract)
    calls: list[tuple[str, dict[str, object]]] = []

    def request(**kwargs):
        action = cast(str, kwargs["action"])
        calls.append((action, cast(dict[str, object], kwargs["body"])))
        return copy.deepcopy(responses[action])

    monkeypatch.setattr(transfer_module, "_tencent_cam_request", request)
    receipt = _cam_readback_call(contract, credentials, now)
    assert [action for action, _ in calls] == [
        "DescribeOIDCConfig",
        "GetRole",
        "ListAttachedRolePolicies",
        "ListPolicyVersions",
        "GetPolicyVersion",
        "GetRolePermissionBoundary",
    ]
    assert receipt["status"] == "passed"
    assert receipt["permission_boundary"] == "absent"
    assert receipt["workflow_run_id"] == 12345
    assert set(cast(dict[str, str], receipt["request_ids"])) == set(responses)
    encoded = canonical_json_bytes(receipt).decode()
    assert "SECRET_READBACK_FIXTURE" not in encoded
    assert "TOKEN_READBACK_FIXTURE" not in encoded
    assert not credentials.exists()


@pytest.mark.parametrize(
    "mutation",
    ["extra-policy", "broad-trust", "wrong-version", "deactivated", "boolean-active"],
)
def test_cam_effective_role_readback_rejects_extra_authority_or_wrong_version(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    _cam_readback_credentials(credentials, now)
    responses = _cam_readback_responses(contract)
    if mutation == "extra-policy":
        response = responses["ListAttachedRolePolicies"]
        response["TotalNum"] = 2
        cast(list[object], response["List"]).append(
            {"PolicyId": 10002, "PolicyName": "extra", "PolicyType": "User"}
        )
    elif mutation == "broad-trust":
        role = cast(dict[str, object], responses["GetRole"]["RoleInfo"])
        trust = json.loads(cast(str, role["PolicyDocument"]))
        trust["statement"][0]["condition"]["string_equal"]["oidc:sub"] = ["*"]
        role["PolicyDocument"] = json.dumps(trust)
    elif mutation == "wrong-version":
        version = cast(
            dict[str, object], responses["GetPolicyVersion"]["PolicyVersion"]
        )
        version["VersionId"] = 1
    elif mutation == "deactivated":
        policy = cast(
            dict[str, object],
            cast(list[object], responses["ListAttachedRolePolicies"]["List"])[0],
        )
        policy["Deactived"] = 1
        policy["DeactivedDetail"] = ["cos"]
    else:
        policy = cast(
            dict[str, object],
            cast(list[object], responses["ListAttachedRolePolicies"]["List"])[0],
        )
        policy["Deactived"] = False

    monkeypatch.setattr(
        transfer_module,
        "_tencent_cam_request",
        lambda **kwargs: copy.deepcopy(responses[cast(str, kwargs["action"])]),
    )
    with pytest.raises(TransferContractError, match="CAM"):
        _cam_readback_call(contract, credentials, now)
    assert not credentials.exists()


def test_cam_readback_consumes_credentials_before_request_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    _cam_readback_credentials(credentials, now)

    def interrupted(**_kwargs):
        assert not credentials.exists()
        raise TransferContractError("release transfer interrupted")

    monkeypatch.setattr(transfer_module, "_tencent_cam_request", interrupted)
    with pytest.raises(TransferContractError, match="interrupted"):
        _cam_readback_call(contract, credentials, now)
    assert not credentials.exists()


def test_cam_readback_cleanup_failure_blocks_api_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    _cam_readback_credentials(credentials, now)
    calls = 0
    original_unlink = transfer_module.os.unlink

    def fail_credential_unlink(path, *args, **kwargs):
        if str(path).startswith(".cam-readback-consume-"):
            raise OSError("fixture cleanup failure")
        return original_unlink(path, *args, **kwargs)

    def request(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("CAM request must not run")

    monkeypatch.setattr(transfer_module.os, "unlink", fail_credential_unlink)
    monkeypatch.setattr(transfer_module, "_tencent_cam_request", request)
    with pytest.raises(TransferContractError, match="manual recovery"):
        _cam_readback_call(contract, credentials, now)
    assert calls == 0
    assert not credentials.exists()
    quarantine = list(tmp_path.glob(".cam-readback-consume-*"))
    assert len(quarantine) == 1
    assert quarantine[0].read_bytes() == b""


@pytest.mark.parametrize("foreign_kind", ["file", "symlink"])
def test_cam_readback_quarantine_preserves_swap_winner_and_blocks_api(
    foreign_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    moved_original = tmp_path / "consumed-original"
    foreign_target = tmp_path / "foreign-target"
    _cam_readback_credentials(credentials, now)
    original_rename = transfer_module._atomic_rename_noreplace_at
    calls = 0

    def swap_then_rename(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        transfer_module.os.rename(credentials, moved_original)
        if foreign_kind == "file":
            credentials.write_bytes(b"FOREIGN")
            credentials.chmod(0o600)
        else:
            foreign_target.write_bytes(b"FOREIGN")
            credentials.symlink_to(foreign_target.name)
        original_rename(parent_descriptor, source_name, destination_name)

    def request(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("CAM request must not run")

    monkeypatch.setattr(
        transfer_module, "_atomic_rename_noreplace_at", swap_then_rename
    )
    monkeypatch.setattr(transfer_module, "_tencent_cam_request", request)
    with pytest.raises(TransferContractError, match="manual recovery"):
        _cam_readback_call(contract, credentials, now)

    assert calls == 0
    assert moved_original.read_bytes() == b""
    quarantine = list(tmp_path.glob(".cam-readback-consume-*"))
    assert len(quarantine) == 1
    if foreign_kind == "file":
        assert quarantine[0].read_bytes() == b"FOREIGN"
    else:
        assert quarantine[0].is_symlink()
        assert quarantine[0].readlink() == Path(foreign_target.name)


def test_cam_readback_recovers_committed_quarantine_move_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    contract = transfer_module.load_release_governance_contract(
        Path(__file__).parents[1] / "configs" / "cos-release-governance.v1.json"
    )
    now = datetime.now(UTC).replace(microsecond=0)
    credentials = tmp_path / "cam-readback-credentials.json"
    _cam_readback_credentials(credentials, now)
    responses = _cam_readback_responses(contract)
    original_rename = transfer_module._atomic_rename_noreplace_at

    def committed_then_interrupted(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        original_rename(parent_descriptor, source_name, destination_name)
        raise TransferContractError("release transfer interrupted")

    monkeypatch.setattr(
        transfer_module, "_atomic_rename_noreplace_at", committed_then_interrupted
    )
    monkeypatch.setattr(
        transfer_module,
        "_tencent_cam_request",
        lambda **kwargs: copy.deepcopy(responses[cast(str, kwargs["action"])]),
    )
    receipt = _cam_readback_call(contract, credentials, now)
    assert receipt["status"] == "passed"
    assert not credentials.exists()
    assert list(tmp_path.glob(".cam-readback-consume-*")) == []


def test_cam_readback_api_requires_service_request_id(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        transfer_module,
        "_open_no_redirect",
        lambda *_args, **_kwargs: _FixtureHTTPResponse(b'{"Response":{"List":[]}}'),
    )
    with pytest.raises(TransferContractError, match="provenance"):
        transfer_module._tencent_cam_request(
            action="ListAttachedRolePolicies",
            body={"RoleId": "1", "Page": 1, "Rp": 200},
            credentials={
                "secret_id": "id",
                "secret_key": "key",
                "session_token": "token",
            },
            deadline_ns=transfer_module.time.monotonic_ns() + 10_000_000_000,
            now=datetime.now(UTC),
        )


def test_cam_authorization_matches_official_tc3_algorithm_fixed_vector(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[transfer_module.urllib.request.Request] = []

    def capture(request, **_kwargs):
        requests.append(request)
        return _FixtureHTTPResponse(
            canonical_json_bytes(
                {
                    "Response": {
                        "RoleInfo": {},
                        "RequestId": "12345678-1234-1234-1234-1234567890ab",
                    }
                }
            )
        )

    monkeypatch.setattr(transfer_module, "_open_no_redirect", capture)
    transfer_module._tencent_cam_request(
        action="GetRole",
        body={"RoleName": "ai-video-release"},
        credentials={
            "secret_id": "AKIDEXAMPLE",
            "secret_key": "SECRETKEY",
            "session_token": "TOKEN",
        },
        deadline_ns=transfer_module.time.monotonic_ns() + 10_000_000_000,
        now=datetime.fromtimestamp(1_551_113_065, UTC),
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://cam.tencentcloudapi.com/"
    assert request.data == b'{"RoleName":"ai-video-release"}\n'
    assert request.get_header("Content-type") == "application/json; charset=utf-8"
    assert request.get_header("Host") == "cam.tencentcloudapi.com"
    assert request.get_header("X-tc-action") == "GetRole"
    assert request.get_header("X-tc-timestamp") == "1551113065"
    assert request.get_header("X-tc-token") == "TOKEN"
    assert request.get_header("X-tc-version") == "2019-01-16"
    assert request.get_header("Authorization") == (
        "TC3-HMAC-SHA256 "
        "Credential=AKIDEXAMPLE/2019-02-25/cam/tc3_request, "
        "SignedHeaders=content-type;host;x-tc-action, "
        "Signature=da622c9389ecfd959f0951685685c0c3"
        "bfb87d80490ed031d84c930314885299"
    )


def test_local_cam_policy_file_is_not_a_live_provenance_gate():
    parser = transfer_module._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["cam-policy-verify"])


def test_cos_authorization_matches_official_go_sdk_fixed_vector():
    authorization = transfer_module._cos_authorization(
        method="PUT",
        path="/ai-video/releases/test.bin",
        query={"partNumber": "1", "uploadId": "u1"},
        headers={
            "host": "ai-video-release-1250000000.cos.ap-shanghai.myqcloud.com",
            "content-length": "3",
            "content-md5": "kAFQmDzST7DWlj99KOF/cg==",
            "x-cos-forbid-overwrite": "true",
            "x-cos-meta-ai-video-sha256": "a" * 64,
            "x-cos-security-token": "TOKENVALUE",
        },
        secret_id="AKIDTEST",
        secret_key="SECRETKEY",
        now=1_700_000_000,
        validity_seconds=600,
    )
    assert authorization == (
        "q-sign-algorithm=sha1&q-ak=AKIDTEST&"
        "q-sign-time=1699999940;1700000600&"
        "q-key-time=1699999940;1700000600&"
        "q-header-list=content-length;content-md5;host;"
        "x-cos-forbid-overwrite;x-cos-meta-ai-video-sha256;"
        "x-cos-security-token&q-url-param-list=partnumber;uploadid&"
        "q-signature=15ef7e900515ac64adbe6a933f4395d9764a55cb"
    )


def test_single_object_request_has_no_automatic_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "probe.bin"
    source.write_bytes(b"probe")
    attempts = 0

    def fail_once(**_kwargs):
        nonlocal attempts
        attempts += 1
        raise TransferContractError("fixture network failure")

    monkeypatch.setattr(transfer_module, "_cos_request", fail_once)
    with pytest.raises(TransferContractError, match="fixture network failure"):
        transfer_module.upload_object_once(
            path=source,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            object_key="probe.bin",
            expected_sha256=hashlib.sha256(b"probe").hexdigest(),
            expected_size=5,
        )
    assert attempts == 1


def test_probe_delete_uses_one_fresh_bounded_cleanup_attempt_after_parent_expiry(
    monkeypatch: pytest.MonkeyPatch,
):
    attempts = 0

    def fail_once(**kwargs):
        nonlocal attempts
        attempts += 1
        assert kwargs["method"] == "DELETE"
        assert kwargs["timeout"] == 30
        assert kwargs["deadline_ns"] > transfer_module.time.monotonic_ns()
        raise TransferContractError("fixture delete failed")

    monkeypatch.setenv(
        "TRANSFER_DEADLINE_MONOTONIC_NS",
        str(transfer_module.time.monotonic_ns() - 1),
    )
    monkeypatch.setattr(transfer_module, "_cos_request", fail_once)

    with pytest.raises(TransferContractError, match="fixture delete failed"):
        transfer_module.delete_object_once(
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            object_key="ai-video/probes/run/probe.bin",
        )

    assert attempts == 1


def test_signed_url_payload_is_clamped_to_remaining_transfer_authority(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(_manifest(bundle)))
    signed: list[dict[str, object]] = []

    def fake_signed_object_url(**kwargs):
        signed.append(kwargs)
        return (
            f"https://{kwargs['bucket']}.{kwargs['endpoint_host']}/"
            f"{kwargs['object_key']}?fixture=1"
        )

    monkeypatch.setenv(
        "TRANSFER_DEADLINE_MONOTONIC_NS",
        str(transfer_module.time.monotonic_ns() + 1_800 * 1_000_000_000),
    )
    monkeypatch.setattr(transfer_module, "_signed_object_url", fake_signed_object_url)

    payload = json.loads(
        transfer_module._signed_urls(
            manifest_path=manifest_path,
            validity_seconds=transfer_module.MAX_VALIDITY_SECONDS,
        )
    )

    remaining = cast(int, payload["deadline_seconds_remaining"])
    assert 60 <= remaining <= transfer_module.MAX_ESTIMATED_SECONDS
    assert signed
    assert {entry["validity_seconds"] for entry in signed} == {remaining}
    assert set(cast(dict[str, str], payload["urls"])) == {
        Path(cast(str, entry["object_key"])).name
        for entry in cast(list[dict[str, object]], _manifest(bundle)["files"])
    } | {"release-transfer-manifest.v1.json"}


def test_signed_url_commands_default_and_clamp_to_transfer_window(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    calls: list[dict[str, object]] = []

    def fake_signed_object_url(**kwargs):
        calls.append(kwargs)
        return "https://fixture.invalid/object?fixture=1"

    parser = transfer_module._parser()
    args = parser.parse_args(
        [
            "cos-signed-url",
            "--bucket",
            "ai-video-release-1250000000",
            "--endpoint-host",
            "cos.ap-shanghai.myqcloud.com",
            "--object-key",
            "ai-video/probes/run/probe.bin",
        ]
    )
    payload_args = parser.parse_args(
        ["signed-url-payload", "--manifest", "fixture.json"]
    )
    assert args.validity_seconds == transfer_module.MAX_ESTIMATED_SECONDS
    assert payload_args.validity_seconds == transfer_module.MAX_ESTIMATED_SECONDS

    monkeypatch.setenv(
        "TRANSFER_DEADLINE_MONOTONIC_NS",
        str(transfer_module.time.monotonic_ns() + 1_800 * 1_000_000_000),
    )
    monkeypatch.setattr(transfer_module, "_signed_object_url", fake_signed_object_url)

    assert transfer_module._execute(args) == 0
    assert capsys.readouterr().out.strip() == "https://fixture.invalid/object?fixture=1"
    assert len(calls) == 1
    assert 60 <= cast(int, calls[0]["validity_seconds"]) <= 1_800


def test_signed_url_fails_closed_when_less_than_one_minute_remains(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    manifest_path = bundle / "release-transfer-manifest.v1.json"
    manifest_path.write_bytes(canonical_json_bytes(_manifest(bundle)))
    monkeypatch.setenv(
        "TRANSFER_DEADLINE_MONOTONIC_NS",
        str(transfer_module.time.monotonic_ns() + 59 * 1_000_000_000),
    )
    monkeypatch.setattr(
        transfer_module,
        "_signed_object_url",
        lambda **_kwargs: pytest.fail("signer must not run with an expired authority"),
    )

    with pytest.raises(TransferContractError, match="validity"):
        transfer_module._signed_urls(
            manifest_path=manifest_path,
            validity_seconds=transfer_module.MAX_ESTIMATED_SECONDS,
        )


def test_cos_content_md5_is_explicitly_non_security():
    source = (Path(__file__).parents[1] / "scripts" / "release_transfer.py").read_text()
    assert source.count("usedforsecurity=False") == 2


def test_expired_shared_deadline_fails_before_any_cos_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "probe.bin"
    source.write_bytes(b"probe")
    calls = 0

    def forbidden_request(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("COS request must not start after the shared deadline")

    monkeypatch.setattr(transfer_module, "_cos_request", forbidden_request)
    deadline = transfer_module.time.monotonic_ns() - 1
    with pytest.raises(TransferContractError, match="deadline"):
        transfer_module.upload_object_once(
            path=source,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            object_key="probe.bin",
            expected_sha256=hashlib.sha256(b"probe").hexdigest(),
            expected_size=5,
            deadline_ns=deadline,
        )
    assert calls == 0


def test_multipart_part_failure_is_not_retried_and_abort_is_single_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "archive.bin"
    source.write_bytes(b"12345")
    calls: list[str] = []

    def fixture_request(**kwargs):
        method = cast(str, kwargs["method"])
        calls.append(method)
        if calls == ["POST"]:
            return b"<InitiateMultipartUploadResult><UploadId>u1</UploadId></InitiateMultipartUploadResult>", {}, 200
        if method == "PUT":
            raise TransferContractError("fixture part failed")
        assert method == "DELETE"
        return b"", {}, 204

    monkeypatch.setattr(transfer_module, "COS_PART_SIZE_BYTES", 4)
    monkeypatch.setattr(transfer_module, "_cos_request", fixture_request)
    with pytest.raises(TransferContractError, match="fixture part failed"):
        transfer_module.upload_object_once(
            path=source,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            object_key="archive.bin",
            expected_sha256=hashlib.sha256(b"12345").hexdigest(),
            expected_size=5,
        )
    assert calls == ["POST", "PUT", "DELETE"]


def test_multipart_create_and_complete_are_create_only_with_one_long_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "archive.bin"
    source.write_bytes(b"12345")
    calls: list[dict[str, object]] = []

    def fixture_request(**kwargs):
        calls.append(kwargs)
        method = cast(str, kwargs["method"])
        query = cast(dict[str, str], kwargs.get("query", {}))
        if method == "POST" and query == {"uploads": ""}:
            return (
                b"<InitiateMultipartUploadResult><UploadId>u1</UploadId></InitiateMultipartUploadResult>",
                {},
                200,
            )
        if method == "PUT":
            return b"", {"etag": f'"{"a" * 32}"'}, 200
        assert method == "POST" and query == {"uploadId": "u1"}
        return b"<CompleteMultipartUploadResult/>", {}, 200

    monkeypatch.setattr(transfer_module, "COS_PART_SIZE_BYTES", 4)
    monkeypatch.setattr(transfer_module, "_cos_request", fixture_request)
    transfer_module.upload_object_once(
        path=source,
        bucket="ai-video-release-1250000000",
        endpoint_host="cos.ap-shanghai.myqcloud.com",
        object_key="archive.bin",
        expected_sha256=hashlib.sha256(b"12345").hexdigest(),
        expected_size=5,
    )
    assert [call["method"] for call in calls] == ["POST", "PUT", "PUT", "POST"]
    create_headers = cast(dict[str, str], calls[0]["headers"])
    complete_headers = cast(dict[str, str], calls[-1]["headers"])
    assert create_headers["x-cos-forbid-overwrite"] == "true"
    assert complete_headers["x-cos-forbid-overwrite"] == "true"
    assert calls[-1]["timeout"] == 1_800
    deadlines = {cast(int, call["deadline_ns"]) for call in calls}
    assert len(deadlines) == 1


def test_multipart_interruption_performs_one_bounded_abort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "archive.bin"
    source.write_bytes(b"12345")
    calls: list[str] = []

    def fixture_request(**kwargs):
        method = cast(str, kwargs["method"])
        calls.append(method)
        if calls == ["POST"]:
            return (
                b"<InitiateMultipartUploadResult><UploadId>u1</UploadId></InitiateMultipartUploadResult>",
                {},
                200,
            )
        if method == "PUT":
            raise SystemExit(143)
        assert method == "DELETE"
        return b"", {}, 204

    monkeypatch.setattr(transfer_module, "COS_PART_SIZE_BYTES", 4)
    monkeypatch.setattr(transfer_module, "_cos_request", fixture_request)
    with pytest.raises(TransferContractError, match="interrupted"):
        transfer_module.upload_object_once(
            path=source,
            bucket="ai-video-release-1250000000",
            endpoint_host="cos.ap-shanghai.myqcloud.com",
            object_key="archive.bin",
            expected_sha256=hashlib.sha256(b"12345").hexdigest(),
            expected_size=5,
        )
    assert calls == ["POST", "PUT", "DELETE"]


def test_receipt_context_rejects_identity_and_probe_conservation_drift(bundle: Path):
    manifest = _manifest(bundle)
    manifest_bytes = canonical_json_bytes(manifest)
    files = cast(list[dict[str, object]], manifest["files"])
    release_bytes = sum(cast(int, item["size_bytes"]) for item in files) + len(
        manifest_bytes
    )
    probe = evaluate_probe(
        transferred_bytes=PROBE_SIZE_BYTES,
        elapsed_nanoseconds=16_000_000_000,
        release_bytes=release_bytes,
    )
    receipt = build_transfer_receipt(
        source_revision=SOURCE_SHA,
        workflow_run_id=12345,
        workflow_run_attempt=1,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        incoming_directory=f".incoming-{SOURCE_SHA}-12345-1",
        completed_at="2026-08-13T03:30:00Z",
        expires_at="2026-08-13T05:00:00Z",
        probe=probe,
        manifest=manifest,
    )
    validate_transfer_receipt(
        receipt,
        manifest=manifest,
        expected_source_revision=SOURCE_SHA,
        expected_workflow_run_id=12345,
        expected_workflow_run_attempt=1,
        expected_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )

    drift = copy.deepcopy(receipt)
    cast(dict[str, object], drift["probe"])["bytes_per_second"] = 1
    with pytest.raises(TransferContractError, match="conservation"):
        validate_transfer_receipt(drift, manifest=manifest)
    with pytest.raises(TransferContractError, match="run ID"):
        validate_transfer_receipt(
            receipt,
            manifest=manifest,
            expected_workflow_run_id=999,
        )

    self_consistent_drift = copy.deepcopy(receipt)
    self_consistent_drift["source_revision"] = "b" * 40
    self_consistent_drift["workflow_run_id"] = 999
    self_consistent_drift["incoming_directory"] = f".incoming-{'b' * 40}-999-1"
    with pytest.raises(TransferContractError, match="manifest"):
        validate_transfer_receipt(self_consistent_drift, manifest=manifest)

    equal_length_manifest_drift = copy.deepcopy(manifest)
    cast(dict[str, object], equal_length_manifest_drift["workflow"])[
        "artifact_digest"
    ] = f"sha256:{'e' * 64}"
    with pytest.raises(TransferContractError, match="manifest checksum"):
        validate_transfer_receipt(
            receipt,
            manifest=equal_length_manifest_drift,
            expected_manifest_sha256=cast(str, receipt["manifest_sha256"]),
        )


def test_deep_json_is_normalized_to_bounded_contract_failure(tmp_path: Path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")
    with pytest.raises(TransferContractError, match="not valid JSON|depth limit"):
        transfer_module.load_canonical_manifest(path)
