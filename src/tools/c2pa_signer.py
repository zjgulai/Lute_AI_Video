"""Fail-closed C2PA signing and local Reader verification boundary."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


class C2PASigningError(RuntimeError):
    """Stable, secret-free C2PA boundary error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class C2PASigningPolicy:
    mode: Literal["local_draft", "required"]

    def __post_init__(self) -> None:
        if self.mode not in {"local_draft", "required"}:
            raise ValueError("c2pa signing policy is invalid")


@dataclass(frozen=True, slots=True)
class C2PASigningResult:
    status: Literal["unsigned_pending_review", "signed_local_readback"]
    output_path: Path
    manifest_sha256: str | None


def is_enabled() -> bool:
    """Compatibility projection; only exact truthy values request required signing."""

    return os.environ.get("C2PA_ENABLED", "").lower() in {"1", "true", "yes"}


def build_manifest(
    title: str,
    *,
    pipeline_version: str = "2.0.0",
    pipeline_name: str = "AI_Video_Pipeline",
    media_format: str = "video/mp4",
) -> dict[str, Any]:
    """Build the exact AI-generated C2PA manifest definition."""

    if (
        not title
        or len(title) > 300
        or any(ord(character) < 32 for character in title)
        or not pipeline_version
        or not pipeline_name
    ):
        raise C2PASigningError("c2pa_manifest_invalid")
    if media_format not in {"video/mp4", "image/jpeg", "image/png", "image/webp"}:
        raise C2PASigningError("c2pa_media_format_unsupported")
    return {
        "claim_generator_info": [{"name": pipeline_name, "version": pipeline_version}],
        "format": media_format,
        "title": title,
        "assertions": [
            {
                "label": "c2pa.actions",
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
        ],
    }


def _validate_readback(store: object) -> str:
    if not isinstance(store, dict):
        raise C2PASigningError("c2pa_readback_invalid")
    active_id = store.get("active_manifest")
    manifests = store.get("manifests")
    if not isinstance(active_id, str) or not isinstance(manifests, dict):
        raise C2PASigningError("c2pa_readback_invalid")
    active = manifests.get(active_id)
    if not isinstance(active, dict):
        raise C2PASigningError("c2pa_readback_invalid")
    assertions = active.get("assertions")
    if not isinstance(assertions, list):
        raise C2PASigningError("c2pa_readback_invalid")
    actions_assertion = next(
        (
            assertion
            for assertion in assertions
            if isinstance(assertion, dict)
            and assertion.get("label") in {"c2pa.actions", "c2pa.actions.v2"}
        ),
        None,
    )
    data = actions_assertion.get("data") if isinstance(actions_assertion, dict) else None
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list) or not any(
        isinstance(action, dict)
        and action.get("action") == "c2pa.created"
        and action.get("digitalSourceType")
        == "http://cv.iptc.org/newscodes/digitalsourcetype/aiGeneratedContent"
        for action in actions
    ):
        raise C2PASigningError("c2pa_readback_ai_label_missing")
    validation_results = store.get("validation_results")
    active_results = (
        validation_results.get("activeManifest")
        if isinstance(validation_results, dict)
        else None
    )
    success_results = (
        active_results.get("success") if isinstance(active_results, dict) else None
    )
    failure_results = (
        active_results.get("failure") if isinstance(active_results, dict) else None
    )
    if not isinstance(success_results, list) or not isinstance(failure_results, list):
        raise C2PASigningError("c2pa_readback_validation_missing")
    success_codes = {
        result.get("code") for result in success_results if isinstance(result, dict)
    }
    if not {"claimSignature.validated", "assertion.dataHash.match"}.issubset(
        success_codes
    ):
        raise C2PASigningError("c2pa_readback_validation_missing")
    failure_codes = {
        result.get("code") for result in failure_results if isinstance(result, dict)
    }
    validation_status = store.get("validation_status", [])
    if not isinstance(validation_status, list):
        raise C2PASigningError("c2pa_readback_validation_failed")
    status_codes = {
        result.get("code") for result in validation_status if isinstance(result, dict)
    }
    if (failure_codes | status_codes) - {"signingCredential.untrusted"}:
        raise C2PASigningError("c2pa_readback_validation_failed")
    encoded = json.dumps(
        active,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_and_verify_media(
    input_path: str | Path,
    *,
    output_path: str | Path,
    title: str,
    policy: C2PASigningPolicy,
    certificate_path: str | Path | None = None,
    private_key_path: str | Path | None = None,
    timestamp_authority_url: str | None = "http://timestamp.digicert.com",
    media_format: str = "video/mp4",
) -> C2PASigningResult:
    """Sign one file and require successful local Reader readback when policy demands it."""

    source = Path(input_path)
    destination = Path(output_path)
    if policy.mode == "local_draft":
        return C2PASigningResult("unsigned_pending_review", source, None)
    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size <= 0:
            raise C2PASigningError("c2pa_input_invalid")
    except OSError as exc:
        raise C2PASigningError("c2pa_input_invalid") from exc

    try:
        if source.resolve() == destination.resolve() or destination.is_symlink() or destination.exists():
            raise C2PASigningError("c2pa_output_unsafe")
        if destination.parent.is_symlink():
            raise C2PASigningError("c2pa_output_unsafe")
    except OSError as exc:
        raise C2PASigningError("c2pa_input_invalid") from exc

    if certificate_path is None or private_key_path is None:
        raise C2PASigningError("c2pa_credentials_missing")
    if not isinstance(timestamp_authority_url, str) or not timestamp_authority_url:
        raise C2PASigningError("c2pa_timestamp_authority_missing")
    if timestamp_authority_url not in {
        "http://timestamp.digicert.com",
        "https://timestamp.digicert.com",
    }:
        raise C2PASigningError("c2pa_timestamp_authority_invalid")
    certificate = Path(certificate_path)
    private_key = Path(private_key_path)
    if (
        certificate.is_symlink()
        or private_key.is_symlink()
        or not certificate.is_file()
        or not private_key.is_file()
    ):
        raise C2PASigningError("c2pa_credentials_missing")

    try:
        from c2pa import (
            Builder,
            C2paSignerInfo,
            C2paSigningAlg,
            Reader,
            Signer,
        )
    except ImportError as exc:
        raise C2PASigningError("c2pa_sdk_missing") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".partial",
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(temp_name)
    linked = False
    try:
        signer_info = C2paSignerInfo(
            alg=C2paSigningAlg.ES256,
            sign_cert=certificate.read_bytes(),
            private_key=private_key.read_bytes(),
            ta_url=timestamp_authority_url.encode("utf-8"),
        )
        manifest_json = json.dumps(
            build_manifest(title, media_format=media_format),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        with Signer.from_info(signer_info) as signer:
            with Builder(manifest_json) as builder:
                with source.open("rb") as source_stream, temporary.open("w+b") as output_stream:
                    builder.sign(signer, media_format, source_stream, output_stream)
        if temporary.stat().st_size <= 0:
            raise C2PASigningError("c2pa_signed_output_missing")
        with temporary.open("rb") as signed_stream:
            with Reader(media_format, signed_stream) as reader:
                readback = json.loads(reader.json())
        manifest_sha256 = _validate_readback(readback)
        os.link(temporary, destination)
        linked = True
        temporary.unlink()
        return C2PASigningResult("signed_local_readback", destination, manifest_sha256)
    except C2PASigningError:
        raise
    except FileExistsError as exc:
        raise C2PASigningError("c2pa_output_unsafe") from exc
    except Exception as exc:
        raise C2PASigningError("c2pa_sign_or_verify_failed") from exc
    finally:
        temporary.unlink(missing_ok=True)
        if linked and not destination.is_file():
            destination.unlink(missing_ok=True)


def verify_signed_media_readback(
    path: str | Path,
    *,
    media_format: str = "video/mp4",
) -> str:
    """Perform a Reader-only local verification without signing or TSA access."""

    source = Path(path)
    if media_format not in {"video/mp4", "image/jpeg", "image/png", "image/webp"}:
        raise C2PASigningError("c2pa_media_format_unsupported")
    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size <= 0:
            raise C2PASigningError("c2pa_input_invalid")
    except OSError as exc:
        raise C2PASigningError("c2pa_input_invalid") from exc
    try:
        from c2pa import Reader
    except ImportError as exc:
        raise C2PASigningError("c2pa_sdk_missing") from exc
    try:
        with source.open("rb") as signed_stream:
            with Reader(media_format, signed_stream) as reader:
                readback = json.loads(reader.json())
        return _validate_readback(readback)
    except C2PASigningError:
        raise
    except Exception as exc:
        raise C2PASigningError("c2pa_readback_invalid") from exc


def sign_video(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> str:
    """Compatibility wrapper used by current S1/S2 until the F2 shared boundary lands."""

    source = Path(input_path)
    policy = C2PASigningPolicy(mode="required" if is_enabled() else "local_draft")
    destination = (
        Path(output_path)
        if output_path is not None
        else source.with_name(f"{source.stem}_signed{source.suffix}")
    )
    result = sign_and_verify_media(
        source,
        output_path=destination,
        title=title or source.stem,
        policy=policy,
        certificate_path=os.environ.get("C2PA_CERT_PATH"),
        private_key_path=os.environ.get("C2PA_KEY_PATH"),
        timestamp_authority_url=os.environ.get(
            "C2PA_TSA_URL",
            "http://timestamp.digicert.com",
        ),
    )
    return str(result.output_path)


__all__ = [
    "C2PASigningError",
    "C2PASigningPolicy",
    "C2PASigningResult",
    "build_manifest",
    "is_enabled",
    "sign_and_verify_media",
    "sign_video",
    "verify_signed_media_readback",
]
