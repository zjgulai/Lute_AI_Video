"""Local asset storage service.

Simple file-based asset storage for video and image assets.
Supports upload, retrieval, listing, and metadata tracking.

Filesystem-backed — upgradeable to S3/MinIO later.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import structlog

from src.config import OUTPUT_DIR

logger = structlog.get_logger()

# Allowed file extensions for upload
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS


class AssetRecord:
    """Metadata record for a stored asset."""

    def __init__(
        self,
        asset_id: str,
        filename: str,
        original_name: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.asset_id = asset_id
        self.filename = filename
        self.original_name = original_name
        self.file_path = file_path
        self.file_size = file_size
        self.mime_type = mime_type
        self.tags = tags or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "filename": self.filename,
            "original_name": self.original_name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AssetRecord:
        return cls(
            asset_id=data["asset_id"],
            filename=data["filename"],
            original_name=data["original_name"],
            file_path=data["file_path"],
            file_size=data["file_size"],
            mime_type=data["mime_type"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class AssetStorage:
    """Local filesystem-backed asset storage.

    Stores uploaded files under OUTPUT_DIR/assets/<asset_id>/.
    Maintains a JSON index for metadata queries.

    Two modes:
    1. Real: stores files on disk with metadata index
    2. Mock: returns synthetic records for testing
    """

    def __init__(self, storage_dir: Path | None = None, use_mock: bool = False):
        self.storage_dir = storage_dir or OUTPUT_DIR / "assets"
        self.index_path = self.storage_dir / "_index.json"
        self.use_mock = use_mock
        self._index: dict[str, dict[str, Any]] = {}

        if not use_mock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._load_index()

    # ── Public API ──

    def store(
        self,
        file_data: bytes,
        original_name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRecord:
        """Store a file and return its asset record.

        Args:
            file_data: Raw file bytes.
            original_name: Original filename (used for extension detection).
            tags: Optional tags for search/filtering.
            metadata: Optional arbitrary metadata.

        Returns:
            AssetRecord with generated asset_id.
        """
        if self.use_mock:
            return self._mock_record(original_name, tags)

        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning("asset_storage: disallowed extension", ext=ext)
            ext = ".bin"  # Fallback

        asset_id = f"ASSET-{uuid.uuid4().hex[:8].upper()}"
        filename = f"{asset_id}{ext}"
        asset_dir = self.storage_dir / asset_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        file_path = asset_dir / filename
        file_path.write_bytes(file_data)

        record = AssetRecord(
            asset_id=asset_id,
            filename=filename,
            original_name=original_name,
            file_path=str(file_path),
            file_size=len(file_data),
            mime_type=self._guess_mime_type(ext),
            tags=tags or [],
            metadata=metadata or {},
        )

        self._index[asset_id] = record.to_dict()
        self._save_index()

        logger.info("asset_storage: stored", asset_id=asset_id, size=len(file_data))
        return record

    def get(self, asset_id: str) -> AssetRecord | None:
        """Retrieve an asset record by ID."""
        if self.use_mock:
            return self._mock_record("mock.mp4", ["mock"])

        data = self._index.get(asset_id)
        if data:
            return AssetRecord.from_dict(data)
        return None

    def get_file_path(self, asset_id: str) -> str | None:
        """Get the local file path for an asset."""
        if self.use_mock:
            return f"[MOCK_PATH — {asset_id}]"

        record = self.get(asset_id)
        if record and Path(record.file_path).exists():
            return record.file_path
        return None

    def list(
        self,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[AssetRecord]:
        """List all assets, optionally filtered by tags.

        Args:
            tags: If provided, only return assets matching ALL tags.
            limit: Maximum number of records to return.

        Returns:
            List of AssetRecord objects.
        """
        if self.use_mock:
            return [self._mock_record(f"mock_{i}.mp4", ["video"]) for i in range(3)]

        records = []
        for data in self._index.values():
            record = AssetRecord.from_dict(data)
            if tags:
                if not all(tag in record.tags for tag in tags):
                    continue
            records.append(record)

        return records[:limit]

    def delete(self, asset_id: str) -> bool:
        """Delete an asset and its file."""
        if self.use_mock:
            return True

        if asset_id not in self._index:
            return False

        # Delete file
        record = self._index[asset_id]
        file_path = Path(record["file_path"])
        if file_path.exists():
            file_path.unlink()

        # Delete asset directory
        asset_dir = file_path.parent
        if asset_dir.exists():
            shutil.rmtree(asset_dir)

        # Remove from index
        del self._index[asset_id]
        self._save_index()

        logger.info("asset_storage: deleted", asset_id=asset_id)
        return True

    def update_tags(self, asset_id: str, new_tags: list[str]) -> AssetRecord | None:
        """Update tags for an existing asset.

        Args:
            asset_id: The asset ID to update.
            new_tags: New list of tags (replaces existing).

        Returns:
            Updated AssetRecord, or None if not found.
        """
        if self.use_mock:
            record = self._mock_record("mock.mp4", new_tags)
            return record

        if asset_id not in self._index:
            return None

        self._index[asset_id]["tags"] = new_tags
        self._save_index()
        return AssetRecord.from_dict(self._index[asset_id])

    def search_by_tags(self, query_tags: list[str]) -> list[AssetRecord]:
        """Search assets by tags (returns assets matching ANY tag)."""
        if self.use_mock:
            return self.list(limit=5)

        results = []
        for data in self._index.values():
            record = AssetRecord.from_dict(data)
            if any(tag in record.tags for tag in query_tags):
                results.append(record)
        return results

    # ── Internal ──

    def _load_index(self):
        if self.index_path.exists():
            try:
                self._index = json.loads(self.index_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._index = {}
        else:
            self._index = {}

    def _save_index(self):
        self.index_path.write_text(json.dumps(self._index, indent=2))

    def _mock_record(self, original_name: str, tags: list[str] | None) -> AssetRecord:
        return AssetRecord(
            asset_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}",
            filename=f"mock_{original_name}",
            original_name=original_name,
            file_path=f"[MOCK_STORAGE — {original_name}]",
            file_size=0,
            mime_type="video/mp4",
            tags=tags or [],
            metadata={"mock": True},
        )

    def _guess_mime_type(self, ext: str) -> str:
        mime_map = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        return mime_map.get(ext, "application/octet-stream")

    @property
    def total_assets(self) -> int:
        return len(self._index)

    @property
    def total_size_bytes(self) -> int:
        return sum(r["file_size"] for r in self._index.values())
