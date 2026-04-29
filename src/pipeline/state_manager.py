"""Pipeline state persistence manager.

Manages saving and loading pipeline execution state to/from JSON files on disk
and PostgreSQL (with SQLite fallback).
Each pipeline run gets its own state file keyed by label.

Persistence strategy (dual-write):
  1. Filesystem JSON — always written; always available (crash-safe).
  2. PostgreSQL — written when PG is healthy; takes priority on reads.
  If PG is unavailable, the filesystem JSON serves as the sole source of truth.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from src.config import OUTPUT_DIR as _CONFIG_OUTPUT_DIR

try:
    from src.storage import get_pool, init_db
    from src.storage.repository import PipelineStateRepository
    from src.storage.db import is_pg_available
    HAS_STORAGE = True
except ImportError:
    HAS_STORAGE = False

logger = logging.getLogger(__name__)

_LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_label(label: str) -> None:
    if not label or not isinstance(label, str) or not _LABEL_PATTERN.match(label):
        raise ValueError(f"Invalid label: {label!r}. Only alphanumeric, hyphen, underscore allowed.")


def _json_default(obj):
    """JSON encoder fallback for datetime, Pydantic, and other custom types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


class PipelineStateManager:
    """Manages pipeline state persistence to the filesystem and PG.

    Uses dual-write: filesystem JSON always, PG when healthy.
    On reads, PG takes priority (faster, more robust), with filesystem fallback.
    """

    # Use the same OUTPUT_DIR as the rest of the app (absolute path from config).
    # Falls back to ./output if config fails to load (e.g. during testing).
    OUTPUT_DIR: Path = Path(os.getenv("VIDEO_OUTPUT_DIR", str(_CONFIG_OUTPUT_DIR)))

    def __init__(self, use_pg: bool = True):
        self.use_pg = use_pg and HAS_STORAGE
        if not self.use_pg:
            logger.info("PipelineStateManager: PG persistence disabled, filesystem only")

    def _state_dir(self) -> Path:
        """Return the directory where state files are stored (creates if needed)."""
        d = self.OUTPUT_DIR / "pipeline_states"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_path(self, label: str) -> Path:
        """Return the file path for a given state label.

        Validates label to prevent path traversal attacks.
        """
        _validate_label(label)
        return self._state_dir() / f"{label}.json"

    def _save_to_fs(self, label: str, state: dict) -> None:
        """Serialize state to JSON file (crash-safe, always-on)."""
        state_path = self._state_path(label)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=_json_default)

    def _load_from_fs(self, label: str) -> dict | None:
        """Deserialize state from JSON file.

        Returns None if the state file does not exist.
        """
        state_path = self._state_path(label)
        if not state_path.exists():
            return None
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def save(self, label: str, state: dict) -> None:
        """Save state to filesystem (always) + PG (when healthy)."""
        # Filesystem always — crash-safe, works even if PG is completely down
        self._save_to_fs(label, state)
        # PG best-effort — skip if PG is known unhealthy to avoid wasted retries
        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                existing = await repo.get_by_label(label)
                if existing:
                    await repo.update(existing["id"], {
                        "scenario": state.get("scenario"),
                        "config": state.get("config"),
                        "steps": state.get("steps"),
                        "current_step": state.get("current_step"),
                        "mode": state.get("mode"),
                        "errors": state.get("errors"),
                        "media_synthesis_errors": state.get("media_synthesis_errors"),
                    })
                else:
                    await repo.create({
                        "label": label,
                        "scenario": state.get("scenario"),
                        "config": state.get("config"),
                        "steps": state.get("steps"),
                        "current_step": state.get("current_step"),
                        "mode": state.get("mode"),
                        "errors": state.get("errors"),
                        "media_synthesis_errors": state.get("media_synthesis_errors"),
                    })
            except Exception as e:
                logger.warning("PG save failed, filesystem fallback in use: %s", str(e)[:100])

    async def load(self, label: str) -> dict | None:
        """Load state — PG first (when healthy), filesystem fallback."""
        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                row = await repo.get_by_label(label)
                if row:
                    return {
                        "label": row["label"],
                        "scenario": row["scenario"],
                        "config": row["config"],
                        "steps": row["steps"],
                        "current_step": row["current_step"],
                        "mode": row["mode"],
                        "errors": row["errors"],
                        "media_synthesis_errors": row["media_synthesis_errors"],
                    }
            except Exception as e:
                logger.warning("PG load failed, falling back to filesystem: %s", str(e)[:100])
        return self._load_from_fs(label)

    async def exists(self, label: str) -> bool:
        """Check if state exists (PG or filesystem)."""
        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                row = await repo.get_by_label(label)
                if row:
                    return True
            except Exception:
                pass  # fall through to filesystem check
        return self._state_path(label).exists()

    @classmethod
    async def migrate_from_fs_to_pg(cls) -> int:
        """Read all JSON files and write them to PG. Returns count migrated."""
        if not HAS_STORAGE:
            logger.warning("Storage not available, migration skipped")
            return 0
        instance = cls(use_pg=False)
        state_dir = instance._state_dir()
        if not state_dir.exists():
            return 0
        repo = PipelineStateRepository()
        count = 0
        for f in state_dir.glob("*.json"):
            label = f.stem
            with open(f, "r", encoding="utf-8") as fh:
                state = json.load(fh)
            existing = await repo.get_by_label(label)
            if existing:
                await repo.update(existing["id"], {
                    "scenario": state.get("scenario"),
                    "config": state.get("config"),
                    "steps": state.get("steps"),
                    "current_step": state.get("current_step"),
                    "mode": state.get("mode"),
                    "errors": state.get("errors"),
                    "media_synthesis_errors": state.get("media_synthesis_errors"),
                })
            else:
                await repo.create({
                    "label": label,
                    "scenario": state.get("scenario"),
                    "config": state.get("config"),
                    "steps": state.get("steps"),
                    "current_step": state.get("current_step"),
                    "mode": state.get("mode"),
                    "errors": state.get("errors"),
                    "media_synthesis_errors": state.get("media_synthesis_errors"),
                })
            count += 1
        return count
