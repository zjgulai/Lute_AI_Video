from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
PUBLIC_OUTPUT_ROOTS = frozenset({"brand_assets", "demo"})


class ArtifactIdentityError(ValueError):
    pass


class ArtifactNotFoundError(ArtifactIdentityError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalOutputPath:
    canonical_path: str
    absolute_path: Path


@dataclass(frozen=True, slots=True)
class ResolvedOutputArtifact:
    canonical_path: str
    absolute_path: Path
    sha256: str
    size_bytes: int


def validate_output_reference(value: str) -> str:
    normalized = value.replace("\\", "/")
    decoded = normalized
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    for candidate in {normalized, decoded}:
        if (
            not candidate
            or "\x00" in candidate
            or "?" in candidate
            or "#" in candidate
            or candidate.startswith(("/", "//"))
            or _SCHEME_RE.match(candidate)
            or any(part in {"", ".", ".."} for part in candidate.split("/"))
        ):
            raise ArtifactIdentityError("invalid artifact path")
    return decoded


def classify_output_scope(canonical_path: str) -> str | None:
    parts = Path(canonical_path).parts
    if not parts:
        raise ArtifactIdentityError("invalid artifact path")
    if parts[0] in PUBLIC_OUTPUT_ROOTS:
        return None
    if (
        len(parts) == 3
        and parts[:2] == ("thumbnails", "portfolio_posters")
        and parts[2].lower().endswith(".jpg")
    ):
        source_parts = Path(parts[2]).stem.split("__")
        if source_parts[0] in PUBLIC_OUTPUT_ROOTS:
            return None
        if source_parts[0] in {"tenants", "uploads"} and len(source_parts) >= 3:
            return source_parts[1]
        return "default"
    if parts[0] == "tenants" and len(parts) >= 3:
        return parts[1]
    if parts[0] == "uploads" and len(parts) >= 3:
        return parts[1]
    return "default"


def _resolve_path(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        raise ArtifactIdentityError("invalid artifact path") from None


def canonicalize_output_artifact_path(
    value: str,
    *,
    output_dir: Path,
    tenant_id: str,
    required_prefix: str,
    allowed_suffixes: set[str],
    allow_absolute_under_root: bool = False,
) -> CanonicalOutputPath:
    root = _resolve_path(output_dir)
    raw_path = Path(value)
    if raw_path.is_absolute():
        if not allow_absolute_under_root:
            raise ArtifactIdentityError("invalid artifact path")
        candidate = _resolve_path(raw_path)
    else:
        reference = validate_output_reference(value)
        candidate = _resolve_path(root / reference)
    try:
        canonical = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ArtifactIdentityError("invalid artifact path") from exc
    if classify_output_scope(canonical) != tenant_id:
        raise ArtifactNotFoundError("artifact not found")
    prefix = required_prefix.rstrip("/")
    if canonical != prefix and not canonical.startswith(prefix + "/"):
        raise ArtifactIdentityError("artifact does not match source resource")
    if candidate.suffix.lower() not in allowed_suffixes or not candidate.is_file():
        raise ArtifactNotFoundError("artifact not found")
    return CanonicalOutputPath(canonical, candidate)


def resolve_output_artifact(
    value: str,
    *,
    output_dir: Path,
    tenant_id: str,
    required_prefix: str,
    allowed_suffixes: set[str],
    allow_absolute_under_root: bool = False,
) -> ResolvedOutputArtifact:
    canonical = canonicalize_output_artifact_path(
        value,
        output_dir=output_dir,
        tenant_id=tenant_id,
        required_prefix=required_prefix,
        allowed_suffixes=allowed_suffixes,
        allow_absolute_under_root=allow_absolute_under_root,
    )
    digest = hashlib.sha256()
    size = 0
    with canonical.absolute_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size <= 0:
        raise ArtifactIdentityError("artifact is empty")
    return ResolvedOutputArtifact(
        canonical.canonical_path,
        canonical.absolute_path,
        digest.hexdigest(),
        size,
    )
