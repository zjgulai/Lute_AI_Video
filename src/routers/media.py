"""media router — extracted from api.py (P1-11)."""

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from src.config import OUTPUT_DIR
from src.models.transparency import TransparencyDisclosureV1
from src.routers._deps import AuthContext, verify_api_key
from src.services.artifact_identity import (
    PUBLIC_OUTPUT_ROOTS,
    ArtifactIdentityError,
    ArtifactNotFoundError,
    canonicalize_output_artifact_path,
    classify_output_scope,
    validate_output_reference,
)
from src.services.transparency_disclosure import (
    TransparencyDisclosureIntegrityError,
    TransparencyDisclosureNotFound,
    TransparencyDisclosureService,
    TransparencyDisclosureStoreUnavailable,
    get_transparency_disclosure_service,
)


def _load_media_token_secret() -> str:
    """Load an independent server-only signing secret, failing closed in production."""
    production = os.environ.get("ENVIRONMENT", "development").lower() == "production"
    configured = os.environ.get("MEDIA_SIGN_SECRET")
    if configured:
        if production and len(configured.encode("utf-8")) < 32:
            raise RuntimeError("MEDIA_SIGN_SECRET must be at least 32 UTF-8 bytes")
        return configured
    if production:
        raise RuntimeError("MEDIA_SIGN_SECRET is required in production")
    return secrets.token_urlsafe(32)


_MEDIA_TOKEN_SECRET = _load_media_token_secret()
_MEDIA_TOKEN_TTL = 900  # 15 minutes
_ALLOWED_MEDIA_EXTS = {
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
}
PUBLIC_MEDIA_ROOTS = PUBLIC_OUTPUT_ROOTS
MediaPurpose = Literal["view", "download"]


def _sign_media_token(
    canonical_path: str,
    tenant_id: str,
    purpose: str,
    expires_at: int,
) -> str:
    """Generate a short-lived signed token for media access."""
    payload = "\x00".join((canonical_path, tenant_id, purpose, str(expires_at)))
    sig = hmac.new(
        _MEDIA_TOKEN_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _verify_media_token(
    canonical_path: str,
    tenant_id: str,
    purpose: str,
    token: str,
    expires_at: int,
) -> bool:
    """Verify a media access token."""
    if time.time() > expires_at:
        return False
    expected = _sign_media_token(canonical_path, tenant_id, purpose, expires_at)
    return hmac.compare_digest(expected, token)


def _validated_media_request_path(media_path: str) -> str:
    try:
        return validate_output_reference(media_path)
    except ArtifactIdentityError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc


def classify_media_scope(canonical_path: str) -> str | None:
    """Return the owning tenant, or ``None`` for an explicit public root."""
    try:
        return classify_output_scope(canonical_path)
    except ArtifactIdentityError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc


def authorize_media_path(canonical_path: str, tenant_id: str) -> None:
    """Fail closed when ``tenant_id`` does not own a protected media path."""
    owner = classify_media_scope(canonical_path)
    if owner is not None and owner != tenant_id:
        raise HTTPException(status_code=404, detail="File not found")


def sign_media_url(
    media_path: str,
    *,
    tenant_id: str,
    purpose: MediaPurpose = "view",
    expires_in_sec: int = _MEDIA_TOKEN_TTL,
) -> str:
    """Generate a tenant-bound signed media URL for an exact media path."""
    if purpose not in {"view", "download"}:
        raise HTTPException(status_code=400, detail="Invalid purpose")
    canonical_path, _ = _resolve_media_path(media_path)
    authorize_media_path(canonical_path, tenant_id)
    expires_at = int(time.time()) + expires_in_sec
    token = _sign_media_token(canonical_path, tenant_id, purpose, expires_at)
    quoted = "/".join(quote(p, safe="") for p in canonical_path.split("/"))
    query = urlencode(
        {
            "token": token,
            "expires": expires_at,
            "tenant": tenant_id,
            "purpose": purpose,
        }
    )
    return f"/api/media/{quoted}?{query}"


def _resolve_media_path(media_path: str) -> tuple[str, Path]:
    """Validate and resolve a requested media path under OUTPUT_DIR."""
    reference = _validated_media_request_path(media_path)
    owner = classify_media_scope(reference)
    required_prefix = reference.split("/", maxsplit=1)[0]
    try:
        canonical = canonicalize_output_artifact_path(
            media_path,
            output_dir=OUTPUT_DIR,
            tenant_id=owner,
            required_prefix=required_prefix,
            allowed_suffixes={Path(reference).suffix.lower()},
            allow_absolute_under_root=False,
        )
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    except ArtifactIdentityError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc
    return canonical.canonical_path, canonical.absolute_path


router = APIRouter()


def _raise_transparency_http_error(exc: Exception) -> None:
    if isinstance(exc, TransparencyDisclosureNotFound):
        raise HTTPException(status_code=404, detail="transparency_not_found") from None
    if isinstance(exc, TransparencyDisclosureIntegrityError):
        raise HTTPException(status_code=409, detail="transparency_integrity_error") from None
    raise HTTPException(status_code=503, detail="transparency_store_unavailable") from None


@router.get(
    "/api/transparency/{resource_type}/{resource_id}",
    response_model=TransparencyDisclosureV1,
)
async def get_transparency_disclosure(
    resource_type: Literal["fast", "scenario"],
    resource_id: str,
    ctx: AuthContext = Depends(verify_api_key),
    service: TransparencyDisclosureService = Depends(
        get_transparency_disclosure_service
    ),
) -> TransparencyDisclosureV1:
    try:
        return await service.inspect(
            tenant_id=ctx.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except (
        TransparencyDisclosureIntegrityError,
        TransparencyDisclosureNotFound,
        TransparencyDisclosureStoreUnavailable,
    ) as exc:
        _raise_transparency_http_error(exc)
    raise AssertionError("unreachable")


@router.get("/api/transparency/{resource_type}/{resource_id}/package")
async def get_transparency_package(
    resource_type: Literal["fast", "scenario"],
    resource_id: str,
    ctx: AuthContext = Depends(verify_api_key),
    service: TransparencyDisclosureService = Depends(
        get_transparency_disclosure_service
    ),
) -> Response:
    try:
        package = await service.build_package(
            tenant_id=ctx.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except (
        TransparencyDisclosureIntegrityError,
        TransparencyDisclosureNotFound,
        TransparencyDisclosureStoreUnavailable,
    ) as exc:
        _raise_transparency_http_error(exc)
        raise AssertionError("unreachable")
    return Response(
        content=package.payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/api/media/sign")
async def get_signed_media_url(
    request: Request,
    ctx: AuthContext = Depends(verify_api_key),
):
    """Generate a short-lived signed URL for a media file.

    Returns a 15-minute signed URL bound to path, tenant, purpose, and expiry.
    Tenant identity comes only from the verified API-key context.
    """
    media_path = request.query_params.get("path", "")
    if not media_path:
        raise HTTPException(status_code=400, detail="path is required")
    purpose = request.query_params.get("purpose", "view")
    if purpose not in {"view", "download"}:
        raise HTTPException(status_code=400, detail="Invalid purpose")
    signed_url = sign_media_url(
        media_path,
        tenant_id=ctx.tenant_id,
        purpose=cast(MediaPurpose, purpose),
    )
    return {"url": signed_url, "expires_in": _MEDIA_TOKEN_TTL}


@router.get("/api/media/{media_path:path}")
async def serve_media(request: Request, media_path: str):
    """Serve files from OUTPUT_DIR; media_path is relative to OUTPUT_DIR (posix subpaths allowed).

    Explicit public roots are anonymous. Every protected path requires a valid
    tenant-bound signature.
    """

    canonical_path, candidate = _resolve_media_path(media_path)

    owner = classify_media_scope(canonical_path)
    if owner is None:
        cache_control = "public, max-age=86400"
    else:
        required_params = {"token", "expires", "tenant", "purpose"}
        if set(request.query_params) != required_params or any(
            len(request.query_params.getlist(name)) != 1 for name in required_params
        ):
            raise HTTPException(status_code=403, detail="Invalid token")

        token = request.query_params["token"]
        expires = request.query_params["expires"]
        tenant_id = request.query_params["tenant"]
        purpose = request.query_params["purpose"]
        try:
            expires_at = int(expires)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid token")
        if purpose not in {"view", "download"} or not _verify_media_token(
            canonical_path,
            tenant_id,
            purpose,
            token,
            expires_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid or expired token")
        authorize_media_path(canonical_path, tenant_id)
        cache_control = "private, no-store"

    ext = candidate.suffix.lower()
    content_type = _ALLOWED_MEDIA_EXTS.get(ext)
    if content_type is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(candidate),
        media_type=content_type,
        filename=candidate.name,
        headers={"Cache-Control": cache_control},
    )
