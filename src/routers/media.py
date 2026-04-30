"""media router — extracted from api.py (P1-11)."""

import os
import hmac
import hashlib
import base64
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse

from src.routers._deps import API_KEY, verify_api_key
from src.config import OUTPUT_DIR

_MEDIA_TOKEN_SECRET = os.environ.get("MEDIA_SIGN_SECRET") or API_KEY
_MEDIA_TOKEN_TTL = 900  # 15 minutes


def _sign_media_token(media_path: str, expires_at: int) -> str:
    """Generate a short-lived signed token for media access."""
    payload = f"{media_path}:{expires_at}"
    sig = hmac.new(
        _MEDIA_TOKEN_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _verify_media_token(media_path: str, token: str, expires_at: int) -> bool:
    """Verify a media access token."""
    if time.time() > expires_at:
        return False
    expected = _sign_media_token(media_path, expires_at)
    return hmac.compare_digest(expected, token)


def sign_media_url(media_path: str, expires_in_sec: int = _MEDIA_TOKEN_TTL) -> str:
    """Generate a signed media URL with query token."""
    expires_at = int(time.time()) + expires_in_sec
    token = _sign_media_token(media_path, expires_at)
    return f"/api/media/{media_path}?token={token}&expires={expires_at}"


router = APIRouter()


@router.get("/api/media/sign", dependencies=[Depends(verify_api_key)])
async def get_signed_media_url(request: Request):
    """Generate a short-lived signed URL for a media file.

    P1-8: Returns a signed URL with token + expires query params.
    The token is valid for 15 minutes and binds to the specific path.
    """
    media_path = request.query_params.get("path", "")
    if not media_path:
        raise HTTPException(status_code=400, detail="path is required")
    signed_url = sign_media_url(media_path)
    return {"url": signed_url, "expires_in": _MEDIA_TOKEN_TTL}


@router.get("/api/media/{media_path:path}")
async def serve_media(request: Request, media_path: str):
    """Serve files from OUTPUT_DIR; media_path is relative to OUTPUT_DIR (posix subpaths allowed).

    P1-8: Supports optional signed-token access. Anonymous access is allowed,
    but signed URLs with ?token=&expires= provide path-level integrity.
    """
    from fastapi.responses import FileResponse
    from src.config import OUTPUT_DIR

    # P1-8: Validate signed token if present
    token = request.query_params.get("token")
    expires = request.query_params.get("expires")
    if token is not None and expires is not None:
        try:
            expires_at = int(expires)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid token")
        if not _verify_media_token(media_path, token, expires_at):
            raise HTTPException(status_code=403, detail="Invalid or expired token")
    # If no token: allow anonymous access (threat model documented in P1-8)

    root = OUTPUT_DIR.resolve()
    if not media_path or media_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    rel = Path(media_path)
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid path")

    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not candidate.is_file():
        safe_name = rel.name
        search_roots = [
            OUTPUT_DIR,
            OUTPUT_DIR / "seedance",
            OUTPUT_DIR / "audio",
            OUTPUT_DIR / "gpt_images",
            OUTPUT_DIR / "renders",
            OUTPUT_DIR / "demo",
            OUTPUT_DIR / "uploads",
            OUTPUT_DIR / "fast_mode",
            OUTPUT_DIR / "fast_mode" / "audio",
        ]
        found: Path | None = None
        for sr in search_roots:
            cand2 = (sr / safe_name).resolve()
            try:
                cand2.relative_to(root)
            except ValueError:
                continue
            if cand2.is_file():
                found = cand2
                break
        if found is None:
            raise HTTPException(status_code=404, detail="File not found")
        candidate = found

    ext = candidate.suffix.lower()
    content_type = {
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
    }.get(ext, "application/octet-stream")
    return FileResponse(
        str(candidate),
        media_type=content_type,
        filename=candidate.name,
    )


