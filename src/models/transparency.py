"""Strict, content-free provenance sidecars for generated artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

TRANSPARENCY_SIDECAR_VERSION = "transparency-sidecar.v1"
TRANSPARENCY_RECORD_VERSION = "transparency-record.v1"
TRANSPARENCY_PROJECTION_VERSION = "transparency-projection.v1"
TRANSPARENCY_DISCLOSURE_VERSION = "transparency-disclosure.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PROVIDER_FACT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_CREDENTIAL_PREFIX_RE = re.compile(
    r"^(?:sk[-_]|pk[-_]|gh[pousr]_|github_pat_|xox[baprs]-|akia|aiza)",
    re.IGNORECASE,
)

ContentKind = Literal["text", "image", "audio", "video"]
OriginKind = Literal["provider", "local", "simulated", "human_edit"]
C2PAStatus = Literal[
    "not_applicable",
    "unsigned_pending_review",
    "signed_local_readback",
]
SigningMode = Literal["local_draft", "required"]


@dataclass(frozen=True, slots=True)
class ValidatedTransparencySidecar:
    sidecar: TransparencySidecarV1
    sidecar_bytes: bytes
    detached_bytes: bytes


def _canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("transparency content is not canonical JSON") from exc


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InlineContentIdentity(_StrictModel):
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: StrictInt = Field(ge=0)

    @field_validator("byte_length", mode="before")
    @classmethod
    def reject_boolean_length(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("inline byte length must be an exact integer")
        return value


class FileContentIdentity(_StrictModel):
    relative_path: StrictStr
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: StrictInt = Field(ge=1)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not value
            or value != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("artifact path must be canonical and relative")
        return value

    @field_validator("size_bytes", mode="before")
    @classmethod
    def reject_boolean_size(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("artifact size must be an exact integer")
        return value


class TransparencyRecordV1(_StrictModel):
    schema_version: Literal["transparency-record.v1"] = TRANSPARENCY_RECORD_VERSION
    record_id: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: StrictStr
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"]
    resource_id: StrictStr
    producer_step: StrictStr
    content_kind: ContentKind
    origin_kind: OriginKind
    provider: StrictStr | None
    model: StrictStr | None
    generated_at: StrictStr
    ai_generated: Literal[True] = True
    simulated: StrictBool
    inline_content: InlineContentIdentity | None = None
    artifact: FileContentIdentity | None = None
    parent_record_ids: tuple[StrictStr, ...] = ()
    source_record_ids: tuple[StrictStr, ...] = ()
    human_edit_ids: tuple[StrictStr, ...] = ()
    c2pa_status: C2PAStatus = "not_applicable"

    @field_validator("tenant_id", "resource_id", "producer_step")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if _IDENTITY_RE.fullmatch(value) is None:
            raise ValueError("transparency identity is invalid")
        return value

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: str) -> str:
        if _UTC_RE.fullmatch(value) is None:
            raise ValueError("generated_at must be canonical UTC")
        try:
            parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
        except ValueError as exc:
            raise ValueError("generated_at must be canonical UTC") from exc
        if parsed.utcoffset() != timedelta(0):
            raise ValueError("generated_at must be canonical UTC")
        canonical = parsed.astimezone(UTC).isoformat(
            timespec="microseconds" if parsed.microsecond else "seconds"
        ).replace("+00:00", "Z")
        if value != canonical:
            raise ValueError("generated_at must be canonical UTC")
        return value

    @field_validator("provider", "model")
    @classmethod
    def validate_provider_fact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            _PROVIDER_FACT_RE.fullmatch(value) is None
            or _CREDENTIAL_PREFIX_RE.match(value) is not None
        ):
            raise ValueError("provider or model identifier is invalid")
        return value

    @field_validator("simulated", mode="before")
    @classmethod
    def validate_simulated(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("simulated must be an exact boolean")
        return value

    @field_validator("parent_record_ids", "source_record_ids", "human_edit_ids", mode="before")
    @classmethod
    def normalize_digest_tuple(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            raise ValueError("record references must be an array")
        normalized = tuple(value)
        if len(normalized) != len(set(normalized)) or any(
            not isinstance(item, str) or _SHA256_RE.fullmatch(item) is None
            for item in normalized
        ):
            raise ValueError("record references are invalid")
        return normalized

    @model_validator(mode="after")
    def validate_semantics_and_identity(self) -> TransparencyRecordV1:
        if (self.inline_content is None) == (self.artifact is None):
            raise ValueError("record must bind exactly one content identity")
        if self.inline_content is not None and self.content_kind != "text" and not self.simulated:
            raise ValueError("real media records must bind artifact bytes")
        if self.artifact is not None and self.content_kind == "text":
            raise ValueError("text records must bind inline content")
        if self.origin_kind == "provider":
            if not self.provider or not self.model or self.simulated:
                raise ValueError("provider origin facts are incomplete")
        elif self.provider is not None or self.model is not None:
            raise ValueError("non-provider origin must not claim provider facts")
        if self.origin_kind == "simulated" and not self.simulated:
            raise ValueError("simulated origin must be explicit")
        if self.content_kind not in {"image", "video"} and self.c2pa_status != "not_applicable":
            raise ValueError("C2PA status is not applicable to this content kind")
        if self.inline_content is not None and self.c2pa_status != "not_applicable":
            raise ValueError("inline content cannot claim embedded C2PA")
        expected = hashlib.sha256(
            _canonical_json(self.model_dump(mode="json", exclude={"record_id"}))
        ).hexdigest()
        if self.record_id != expected:
            raise ValueError("transparency record identity does not match facts")
        return self


class TransparencySidecarV1(_StrictModel):
    schema_version: Literal["transparency-sidecar.v1"] = TRANSPARENCY_SIDECAR_VERSION
    records: tuple[TransparencyRecordV1, ...]

    @field_validator("records", mode="before")
    @classmethod
    def normalize_records(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("transparency sidecar requires records")
        return tuple(value)

    @model_validator(mode="after")
    def validate_chain(self) -> TransparencySidecarV1:
        seen: set[str] = set()
        identity: tuple[str, str, str] | None = None
        for record in self.records:
            record_identity = (record.tenant_id, record.scenario, record.resource_id)
            if identity is None:
                identity = record_identity
            elif record_identity != identity:
                raise ValueError("transparency sidecar identity is inconsistent")
            if record.record_id in seen:
                raise ValueError("duplicate transparency record")
            if any(parent not in seen for parent in record.parent_record_ids):
                raise ValueError("transparency parent must precede its child")
            if any(source not in seen for source in record.source_record_ids):
                raise ValueError("transparency source must precede its consumer")
            seen.add(record.record_id)
        return self


class TransparencyProjectionV1(_StrictModel):
    """Small durable pointer to one immutable sidecar snapshot."""

    schema_version: Literal["transparency-projection.v1"] = (
        TRANSPARENCY_PROJECTION_VERSION
    )
    sidecar_path: StrictStr
    sidecar_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: StrictInt = Field(ge=1)
    c2pa_signing_mode: SigningMode
    final_artifact_record_id: StrictStr | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    final_artifact_c2pa_status: C2PAStatus | None = None

    @field_validator("sidecar_path")
    @classmethod
    def validate_sidecar_path(cls, value: str) -> str:
        path = _canonical_relative_artifact_path(value)
        if path.suffix != ".json":
            raise ValueError("transparency projection path must reference JSON")
        return path.as_posix()

    @field_validator("record_count", mode="before")
    @classmethod
    def reject_boolean_count(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("transparency record count must be an exact integer")
        return value

    @model_validator(mode="after")
    def validate_final_artifact_projection(self) -> TransparencyProjectionV1:
        if (self.final_artifact_record_id is None) != (
            self.final_artifact_c2pa_status is None
        ):
            raise ValueError("final artifact transparency facts are incomplete")
        return self


class TransparencyDisclosureV1(_StrictModel):
    """Content-free UI/download truth derived from one validated sidecar."""

    schema_version: Literal["transparency-disclosure.v1"] = (
        TRANSPARENCY_DISCLOSURE_VERSION
    )
    ai_generated: Literal[True] = True
    label: Literal["AI-generated"] = "AI-generated"
    verification_scope: Literal[
        "provenance_only",
        "unsigned_pending_review",
        "local_reader_only",
    ]
    independently_validated: Literal[False] = False
    sidecar_path: StrictStr
    sidecar_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: StrictInt = Field(ge=1)
    human_edit_record_count: StrictInt = Field(ge=0)
    source_reference_count: StrictInt = Field(ge=0)
    c2pa_signing_mode: SigningMode
    final_artifact_c2pa_status: C2PAStatus | None
    package_available: Literal[True] = True

    @field_validator(
        "record_count",
        "human_edit_record_count",
        "source_reference_count",
        mode="before",
    )
    @classmethod
    def reject_boolean_disclosure_counts(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("transparency disclosure count must be an exact integer")
        return value

    @field_validator("sidecar_path")
    @classmethod
    def validate_disclosure_sidecar_path(cls, value: str) -> str:
        path = _canonical_relative_artifact_path(value)
        if path.suffix != ".json":
            raise ValueError("transparency disclosure path must reference JSON")
        return path.as_posix()


def _record_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def build_inline_transparency_record(
    *,
    tenant_id: str,
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"],
    resource_id: str,
    producer_step: str,
    content_kind: ContentKind,
    content: object,
    origin_kind: OriginKind,
    provider: str | None,
    model: str | None,
    generated_at: str,
    parent_record_ids: tuple[str, ...],
    source_record_ids: tuple[str, ...] = (),
    human_edit_ids: tuple[str, ...] = (),
    simulated: bool,
) -> TransparencyRecordV1:
    content_bytes = _canonical_json(content)
    payload: dict[str, object] = {
        "schema_version": TRANSPARENCY_RECORD_VERSION,
        "tenant_id": tenant_id,
        "scenario": scenario,
        "resource_id": resource_id,
        "producer_step": producer_step,
        "content_kind": content_kind,
        "origin_kind": origin_kind,
        "provider": provider,
        "model": model,
        "generated_at": generated_at,
        "ai_generated": True,
        "simulated": simulated,
        "inline_content": {
            "sha256": hashlib.sha256(content_bytes).hexdigest(),
            "byte_length": len(content_bytes),
        },
        "artifact": None,
        "parent_record_ids": parent_record_ids,
        "source_record_ids": source_record_ids,
        "human_edit_ids": human_edit_ids,
        "c2pa_status": "not_applicable",
    }
    payload["record_id"] = _record_id(payload)
    return TransparencyRecordV1.model_validate(payload)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_relative_artifact_path(artifact_path: str | Path) -> PurePosixPath:
    raw = str(artifact_path)
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or raw != path.as_posix()
        or "\\" in raw
        or "\x00" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("artifact path must be canonical and relative")
    return path


def _file_identity(
    artifact_path: str | Path,
    artifact_root: Path,
) -> FileContentIdentity:
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise ValueError("artifact root is missing or unsafe")
    relative_input = _canonical_relative_artifact_path(artifact_path)
    candidate = artifact_root.joinpath(*relative_input.parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("artifact is missing or unsafe")
    root = artifact_root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact is outside its scoped root") from exc
    probe = root
    for part in relative.parts:
        probe = probe / part
        if probe.is_symlink():
            raise ValueError("artifact is missing or unsafe")
    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError("artifact is missing or unsafe")
    return FileContentIdentity(
        relative_path=relative.as_posix(),
        sha256=_sha256_path(resolved),
        size_bytes=size,
    )


def build_file_transparency_record(
    *,
    tenant_id: str,
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"],
    resource_id: str,
    producer_step: str,
    content_kind: Literal["image", "audio", "video"],
    artifact_path: str | Path,
    artifact_root: Path,
    origin_kind: OriginKind,
    provider: str | None,
    model: str | None,
    generated_at: str,
    parent_record_ids: tuple[str, ...],
    source_record_ids: tuple[str, ...] = (),
    human_edit_ids: tuple[str, ...] = (),
    simulated: bool,
    c2pa_status: C2PAStatus,
) -> TransparencyRecordV1:
    artifact = _file_identity(artifact_path, artifact_root)
    payload: dict[str, object] = {
        "schema_version": TRANSPARENCY_RECORD_VERSION,
        "tenant_id": tenant_id,
        "scenario": scenario,
        "resource_id": resource_id,
        "producer_step": producer_step,
        "content_kind": content_kind,
        "origin_kind": origin_kind,
        "provider": provider,
        "model": model,
        "generated_at": generated_at,
        "ai_generated": True,
        "simulated": simulated,
        "inline_content": None,
        "artifact": artifact.model_dump(mode="json"),
        "parent_record_ids": parent_record_ids,
        "source_record_ids": source_record_ids,
        "human_edit_ids": human_edit_ids,
        "c2pa_status": c2pa_status,
    }
    payload["record_id"] = _record_id(payload)
    return TransparencyRecordV1.model_validate(payload)


def build_transparency_sidecar(
    records: list[TransparencyRecordV1] | tuple[TransparencyRecordV1, ...],
) -> TransparencySidecarV1:
    return TransparencySidecarV1(records=tuple(records))


def transparency_sidecar_sha256(sidecar: TransparencySidecarV1) -> str:
    """Return the digest used by immutable content-addressed sidecar names."""

    return hashlib.sha256(
        _canonical_json(sidecar.model_dump(mode="json"))
    ).hexdigest()


def _scoped_output_path(path: Path, output_root: Path) -> Path:
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError("transparency output root is missing or unsafe")
    if any(part in {".", ".."} for part in path.parts):
        raise ValueError("transparency sidecar output is unsafe")
    root = output_root.absolute()
    candidate = path.absolute() if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("transparency sidecar output is unsafe") from exc
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise ValueError("transparency sidecar output is unsafe")
    probe = root
    for part in relative.parts[:-1]:
        probe = probe / part
        if probe.is_symlink() or (probe.exists() and not probe.is_dir()):
            raise ValueError("transparency sidecar output is unsafe")
    if candidate.is_symlink():
        raise ValueError("transparency sidecar output is unsafe")
    return candidate


def write_transparency_sidecar(
    path: Path,
    sidecar: TransparencySidecarV1,
    *,
    output_root: Path,
) -> str:
    path = _scoped_output_path(path, output_root)
    if path.exists():
        raise ValueError("transparency sidecar output already exists or is unsafe")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _scoped_output_path(path, output_root)
    payload = _canonical_json(sidecar.model_dump(mode="json"))
    digest = hashlib.sha256(payload).hexdigest()
    detached = _scoped_output_path(path.with_name(path.name + ".sha256"), output_root)
    if detached.exists():
        raise ValueError("transparency detached digest already exists or is unsafe")
    created: list[Path] = []
    try:
        with path.open("xb") as handle:
            created.append(path)
            handle.write(payload)
        with detached.open("x", encoding="ascii") as handle:
            created.append(detached)
            handle.write(f"{digest}  {path.name}\n")
    except Exception:
        for created_path in reversed(created):
            created_path.unlink(missing_ok=True)
        raise
    return digest


def load_validated_transparency_sidecar(
    path: Path,
    *,
    expected_sha256: str | None = None,
    artifact_root: Path | None = None,
) -> ValidatedTransparencySidecar:
    detached = path.with_name(path.name + ".sha256")
    if path.is_symlink() or detached.is_symlink() or not path.is_file() or not detached.is_file():
        raise ValueError("transparency sidecar artifacts are missing or unsafe")
    payload = path.read_bytes()
    detached_payload = detached.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("transparency sidecar checksum does not match expected digest")
    if detached_payload != f"{digest}  {path.name}\n".encode("ascii"):
        raise ValueError("transparency sidecar detached checksum is invalid")
    try:
        raw = json.loads(payload)
        sidecar = TransparencySidecarV1.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("transparency sidecar schema is invalid") from exc
    if payload != _canonical_json(sidecar.model_dump(mode="json")):
        raise ValueError("transparency sidecar serialization is not canonical")
    if artifact_root is not None:
        for record in sidecar.records:
            if record.artifact is None:
                continue
            current = _file_identity(
                record.artifact.relative_path,
                artifact_root,
            )
            if current != record.artifact:
                raise ValueError("transparency artifact bytes do not match sidecar")
    return ValidatedTransparencySidecar(
        sidecar=sidecar,
        sidecar_bytes=payload,
        detached_bytes=detached_payload,
    )


def validate_transparency_sidecar(
    path: Path,
    *,
    expected_sha256: str | None = None,
    artifact_root: Path | None = None,
) -> TransparencySidecarV1:
    return load_validated_transparency_sidecar(
        path,
        expected_sha256=expected_sha256,
        artifact_root=artifact_root,
    ).sidecar


__all__ = [
    "C2PAStatus",
    "TransparencyDisclosureV1",
    "TransparencyRecordV1",
    "TransparencyProjectionV1",
    "TransparencySidecarV1",
    "ValidatedTransparencySidecar",
    "build_file_transparency_record",
    "build_inline_transparency_record",
    "build_transparency_sidecar",
    "transparency_sidecar_sha256",
    "load_validated_transparency_sidecar",
    "validate_transparency_sidecar",
    "write_transparency_sidecar",
]
