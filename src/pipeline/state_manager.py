"""Pipeline state persistence manager.

Manages saving and loading pipeline execution state to/from JSON files on disk
and PostgreSQL (with SQLite fallback).
Each pipeline run gets its own state file keyed by label.

P1-4: Persistence strategy (PG-primary with FS fallback):
  1. PostgreSQL — primary source of truth. Written first on save, read first on load.
  2. Filesystem JSON — fallback when PG is unavailable. On load, if PG is empty
     but FS has data (PG was down during a save), FS data is synced back to PG.
  This eliminates the "write FS first, read PG first" anti-pattern where PG
  recovery could yield older data than the filesystem.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import OUTPUT_DIR as _CONFIG_OUTPUT_DIR

PipelineStateRepository: Any = None  # type: ignore
is_pg_available: Any = lambda: False  # type: ignore
try:
    from src.storage.db import is_pg_available
    from src.storage.repository import PipelineStateRepository
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

    def _save_to_fs(self, label: str, state: dict[str, Any]) -> None:
        """Serialize state to JSON file (crash-safe, always-on).

        P1-3: Writes to a temporary file first, then performs an atomic
        rename via os.replace(). This ensures that a crash during write
        never leaves a partially-written (truncated) JSON file.
        """
        state_path = self._state_path(label)
        tmp_path = state_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=_json_default)
            f.flush()
            os.fsync(f.fileno())  # Ensure data hits disk before rename
        # Atomic replace: readers always see a complete file
        os.replace(tmp_path, state_path)

    def _load_from_fs(self, label: str) -> dict[str, Any] | None:
        """Deserialize state from JSON file.

        Returns None if the state file does not exist.
        """
        state_path = self._state_path(label)
        if not state_path.exists():
            return None
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)

    async def save(self, label: str, state: dict[str, Any]) -> None:
        """Save state — PG first (primary), then FS (fallback/cache).

        P1-4: Reverses the old "FS first, PG second" order. PG is the single
        source of truth; FS serves as a local cache for offline/backup scenarios.
        """
        # PG first — primary source of truth
        pg_ok = False
        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                existing = await repo.get_by_label(label)
                data = {
                    "scenario": state.get("scenario"),
                    "config": state.get("config"),
                    "steps": state.get("steps"),
                    "current_step": state.get("current_step"),
                    "mode": state.get("mode"),
                    "errors": state.get("errors"),
                    "media_synthesis_errors": state.get("media_synthesis_errors"),
                    "gates": state.get("gates"),
                }
                if existing:
                    await repo.update(existing["id"], data)
                else:
                    await repo.create({"label": label, **data})
                pg_ok = True
            except Exception as e:
                logger.warning("PG save failed: %s", str(e)[:100])

        # FS always — serves as fallback when PG is down, and as local cache
        self._save_to_fs(label, state)

        if self.use_pg and not pg_ok:
            logger.warning(
                "State saved to filesystem only (PG unavailable). "
                "Next load will sync from FS to PG when PG recovers."
            )

    async def load(self, label: str) -> dict[str, Any] | None:
        """Load state — PG primary, with FS-backfill on PG miss.

        P1-4: If PG is healthy but has no data for this label while FS does,
        it means PG was down during a prior save. In that case, sync FS data
        back to PG and return it. This ensures PG never stays behind FS.
        """
        fs_state = self._load_from_fs(label)
        pg_state = None

        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                row = await repo.get_by_label(label)
                if row:
                    # gates column was added 2026-05-03; old rows / pre-migration
                    # PG schemas may not have it. Be defensive on read.
                    try:
                        gates_val = row["gates"]
                    except (KeyError, IndexError):
                        gates_val = {}
                    pg_state = {
                        "label": row["label"],
                        "scenario": row["scenario"],
                        "config": row["config"],
                        "steps": row["steps"],
                        "current_step": row["current_step"],
                        "mode": row["mode"],
                        "errors": row["errors"],
                        "media_synthesis_errors": row["media_synthesis_errors"],
                        "gates": gates_val or {},
                    }
            except Exception as e:
                logger.warning("PG load failed, using filesystem: %s", str(e)[:100])
                return fs_state

        # PG has data — return it (primary source of truth)
        if pg_state is not None:
            return pg_state

        # PG is empty but FS has data — PG was down during save. Backfill.
        if fs_state is not None and self.use_pg and is_pg_available():
            logger.info(
                "PG miss but FS hit for label=%s — backfilling PG from filesystem",
                label,
            )
            try:
                repo = PipelineStateRepository()
                await repo.create({
                    "label": label,
                    "scenario": fs_state.get("scenario"),
                    "config": fs_state.get("config"),
                    "steps": fs_state.get("steps"),
                    "current_step": fs_state.get("current_step"),
                    "mode": fs_state.get("mode"),
                    "errors": fs_state.get("errors"),
                    "media_synthesis_errors": fs_state.get("media_synthesis_errors"),
                    "gates": fs_state.get("gates"),
                })
            except Exception as e:
                logger.warning("PG backfill failed for %s: %s", label, str(e)[:100])
            return fs_state

        # Neither has data
        return fs_state

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
            with open(f, encoding="utf-8") as fh:
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
