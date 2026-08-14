"""Fail-closed contracts for exact release artifacts relayed through COS."""

from __future__ import annotations

import copy
import hashlib
import http.client
import http.server
import json
import os
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
