from __future__ import annotations

import builtins
import json
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO

import pytest

from src.tools.c2pa_signer import (
    C2PASigningError,
    C2PASigningPolicy,
    sign_and_verify_media,
)


def test_source_uses_current_signer_builder_reader_api() -> None:
    source = (Path(__file__).parents[1] / "src" / "tools" / "c2pa_signer.py").read_text()

    assert "Signer.from_info" in source
    assert "C2paSignerInfo" in source
    assert "Reader(" in source
    assert "create_signer(" not in source
    assert "sign_file(str(src), str(dest), signer=signer)" not in source


def test_local_draft_never_imports_sdk_or_reads_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fixture-video")
    real_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        if name == "c2pa" or name.startswith("c2pa."):
            raise AssertionError("local draft must not import C2PA")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    result = sign_and_verify_media(
        source,
        output_path=tmp_path / "signed.mp4",
        title="fixture",
        policy=C2PASigningPolicy(mode="local_draft"),
    )

    assert result.status == "unsigned_pending_review"
    assert result.output_path == source
    assert not (tmp_path / "signed.mp4").exists()


def test_required_signing_missing_credentials_fails_without_output(tmp_path: Path) -> None:
    source = tmp_path / "input.mp4"
    output = tmp_path / "signed.mp4"
    source.write_bytes(b"fixture-video")

    with pytest.raises(C2PASigningError, match="c2pa_credentials_missing"):
        sign_and_verify_media(
            source,
            output_path=output,
            title="fixture",
            policy=C2PASigningPolicy(mode="required"),
        )

    assert not output.exists()


def test_required_signing_rejects_same_input_and_output(tmp_path: Path) -> None:
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fixture-video")

    with pytest.raises(C2PASigningError, match="c2pa_output_unsafe"):
        sign_and_verify_media(
            source,
            output_path=source,
            title="fixture",
            policy=C2PASigningPolicy(mode="required"),
            certificate_path=tmp_path / "cert.pem",
            private_key_path=tmp_path / "key.pem",
        )


def _install_fake_c2pa(
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_ai_action: bool,
    failure_code: str = "signingCredential.untrusted",
) -> None:
    module = types.ModuleType("c2pa")

    class SigningAlg:
        ES256 = "es256"

    class Signer:
        @classmethod
        def from_info(cls, _info: object) -> Signer:
            return cls()

        def __enter__(self) -> Signer:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Builder:
        def __init__(self, _manifest: str) -> None:
            pass

        def __enter__(self) -> Builder:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def sign(
            self,
            _signer: object,
            _media_format: str,
            source: BinaryIO,
            destination: BinaryIO,
        ) -> None:
            destination.write(b"signed:" + source.read())

    class Reader:
        def __init__(self, _media_format: str, _stream: object) -> None:
            pass

        def __enter__(self) -> Reader:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def json(self) -> str:
            actions = (
                [
                    {
                        "label": "c2pa.actions.v2",
                        "data": {
                            "actions": [
                                {
                                    "action": "c2pa.created",
                                    "digitalSourceType": (
                                        "http://cv.iptc.org/newscodes/"
                                        "digitalsourcetype/aiGeneratedContent"
                                    ),
                                }
                            ]
                        },
                    }
                ]
                if include_ai_action
                else []
            )
            return json.dumps(
                {
                    "active_manifest": "fixture",
                    "manifests": {"fixture": {"assertions": actions}},
                    "validation_results": {
                        "activeManifest": {
                            "success": [
                                {"code": "claimSignature.validated"},
                                {"code": "assertion.dataHash.match"},
                            ],
                            "failure": [{"code": failure_code}],
                        }
                    },
                    "validation_status": [
                        {"code": failure_code}
                    ],
                }
            )

    setattr(module, "Builder", Builder)
    setattr(module, "C2paSignerInfo", lambda **kwargs: kwargs)
    setattr(module, "C2paSigningAlg", SigningAlg)
    setattr(module, "Reader", Reader)
    setattr(module, "Signer", Signer)
    monkeypatch.setitem(sys.modules, "c2pa", module)


def test_required_signing_publishes_only_after_reader_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_c2pa(monkeypatch, include_ai_action=True)
    source = tmp_path / "input.mp4"
    output = tmp_path / "signed.mp4"
    certificate = tmp_path / "cert.pem"
    private_key = tmp_path / "key.pem"
    source.write_bytes(b"fixture-video")
    certificate.write_bytes(b"fixture-cert")
    private_key.write_bytes(b"fixture-key")

    result = sign_and_verify_media(
        source,
        output_path=output,
        title="fixture",
        policy=C2PASigningPolicy(mode="required"),
        certificate_path=certificate,
        private_key_path=private_key,
    )

    assert result.status == "signed_local_readback"
    assert result.output_path == output
    assert result.manifest_sha256 is not None
    assert output.read_bytes() == b"signed:fixture-video"


def test_required_signing_reader_failure_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_c2pa(monkeypatch, include_ai_action=False)
    source = tmp_path / "input.mp4"
    output = tmp_path / "signed.mp4"
    certificate = tmp_path / "cert.pem"
    private_key = tmp_path / "key.pem"
    source.write_bytes(b"fixture-video")
    certificate.write_bytes(b"fixture-cert")
    private_key.write_bytes(b"fixture-key")

    with pytest.raises(C2PASigningError, match="c2pa_readback_ai_label_missing"):
        sign_and_verify_media(
            source,
            output_path=output,
            title="fixture",
            policy=C2PASigningPolicy(mode="required"),
            certificate_path=certificate,
            private_key_path=private_key,
        )

    assert not output.exists()
    assert list(tmp_path.glob("*.partial")) == []


def test_required_signing_rejects_reader_integrity_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_c2pa(
        monkeypatch,
        include_ai_action=True,
        failure_code="assertion.dataHash.mismatch",
    )
    source = tmp_path / "input.mp4"
    output = tmp_path / "signed.mp4"
    certificate = tmp_path / "cert.pem"
    private_key = tmp_path / "key.pem"
    source.write_bytes(b"fixture-video")
    certificate.write_bytes(b"fixture-cert")
    private_key.write_bytes(b"fixture-key")

    with pytest.raises(C2PASigningError, match="c2pa_readback_validation_failed"):
        sign_and_verify_media(
            source,
            output_path=output,
            title="fixture",
            policy=C2PASigningPolicy(mode="required"),
            certificate_path=certificate,
            private_key_path=private_key,
        )

    assert not output.exists()
