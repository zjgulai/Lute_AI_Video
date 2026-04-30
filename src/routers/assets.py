"""assets router — extracted from api.py (P1-11)."""

import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends

from src.routers._deps import verify_api_key
from src.config import OUTPUT_DIR

router = APIRouter()


def _sanitize_filename(filename: str | None) -> str:
    """Sanitize and validate upload filename.

    Rejects path traversal attempts, enforces extension allowlist,
    and returns a UUID-based stored name.
    """
    if not filename:
        return "upload"
    safe = Path(filename).name
    if ".." in safe or "/" in safe or "\\" in safe or "\x00" in safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = Path(safe).suffix.lower()
    allowed = {
        ".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg",
        ".webp", ".mp3", ".wav", ".m4a", ".pdf", ".txt", ".md",
    }
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="File type not allowed")
    return f"{uuid.uuid4().hex}{ext}"


MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB


try:
    from fastapi import UploadFile, File

    @router.post("/api/upload", dependencies=[Depends(verify_api_key)])
    async def upload_file(file: UploadFile = File(...)):
        """Upload an asset file (video, image, audio, document) to uploads dir."""
        uploads_dir = OUTPUT_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        unique_name = _sanitize_filename(file.filename)
        original_name = Path(file.filename or "upload").name
        dest = uploads_dir / unique_name

        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large. Max size: {MAX_UPLOAD_SIZE // (1024*1024)}MB")

        dest.write_bytes(content)

        rel_upload = (uploads_dir / unique_name).relative_to(OUTPUT_DIR.resolve())
        media_suffix = "/".join(quote(p, safe="") for p in rel_upload.parts)

        return {
            "filename": unique_name,
            "original_name": original_name,
            "path": f"/api/media/{media_suffix}",
            "size": len(content),
            "content_type": file.content_type,
        }
except ImportError:
    pass  # python-multipart not installed


@router.get("/api/files", dependencies=[Depends(verify_api_key)])
async def list_files():
    """List media files under OUTPUT_DIR (recursive).

    Video/image: strictly larger than 1 MiB. Audio: any positive size (no floor).
    Documents (pdf, txt, etc.) are excluded — not treated as portfolio works.
    """
    from typing import Any

    min_bytes = 1024 * 1024  # video / image only
    root = OUTPUT_DIR.resolve()
    files: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"files": []}

    for f in root.rglob("*"):
        try:
            if not f.is_file():
                continue
            rel = f.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_size <= 0:
            continue
        ext = f.suffix.lower()
        file_type = "document"
        if ext in {".mp4", ".mov", ".webm", ".avi", ".mkv"}:
            file_type = "video"
        elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            file_type = "image"
        elif ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
            file_type = "audio"
        if file_type == "document":
            continue
        if file_type != "audio" and st.st_size <= min_bytes:
            continue
        media_suffix = "/".join(quote(p, safe="") for p in rel.parts)
        path_tags = [str(p) for p in rel.parts[:-1]]
        files.append({
            "filename": f.name,
            "path": f"/api/media/{media_suffix}",
            "size": st.st_size,
            "type": file_type,
            "created": st.st_ctime,
            "tags": path_tags,
        })

    files.sort(key=lambda x: x["created"], reverse=True)
    return {"files": files}
