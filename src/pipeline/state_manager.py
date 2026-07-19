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
_STATE_REPOSITORY_FIELDS = (
    "scenario",
    "config",
    "steps",
    "current_step",
    "mode",
    "errors",
    "media_synthesis_errors",
    "gates",
    "schema_version",
    "pipeline_degraded",
    "degraded_reason",
    "trace_id",
    "structured_errors",
    "tenant_id",
    "regenerate_chain",
    "soft_degraded_reasons",
)

_EXECUTION_LIFECYCLE_FIELDS = (
    "status",
    "lifecycle_status",
    "completion_kind",
    "request_succeeded",
    "success",
    "full_media_success",
    "pipeline_complete",
    "publish_allowed",
    "delivery_accepted",
    "execution_profile_id",
    "provider_job_caps",
)
_CORE_EXECUTION_LIFECYCLE_FIELDS = frozenset(_EXECUTION_LIFECYCLE_FIELDS[:9])


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


def _check_schema_version(state: dict[str, Any] | None, label: str) -> None:
    """Log a warning when persisted state's schema_version differs from runtime.

    Sprint 3 P3-5 contract: observability only. Loading proceeds regardless
    so that pre-versioned states (schema_version absent → treated as 0) still
    open. Callers needing migration logic can inspect state.get(
    'schema_version', 0) directly.
    """
    if state is None:
        return
    from src.models.state import STATE_SCHEMA_VERSION

    persisted = state.get("schema_version", 0)
    if persisted != STATE_SCHEMA_VERSION:
        logger.warning(
            "state schema version mismatch: label=%s persisted=%d runtime=%d "
            "(loading proceeds; consider migration)",
            label, persisted, STATE_SCHEMA_VERSION,
        )


def _repository_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical PG projection for persisted scenario state."""
    state_for_pg = dict(state)
    lifecycle_status = state.get("lifecycle_status")
    has_terminal_lifecycle = (
        lifecycle_status in {"completed_bounded", "policy_blocked"}
        and state.get("status") == lifecycle_status
    )
    if has_terminal_lifecycle:
        lifecycle = {
            field: state[field]
            for field in _EXECUTION_LIFECYCLE_FIELDS
            if field in state
        }
        config = dict(state.get("config") or {})
        config["execution_lifecycle"] = lifecycle
        state_for_pg["config"] = config
    payload = {field: state_for_pg.get(field) for field in _STATE_REPOSITORY_FIELDS}
    trace_id = payload.get("trace_id")
    if trace_id is not None and not isinstance(trace_id, str):
        payload["trace_id"] = str(trace_id)
    return payload


def _strict_json_equal(left: Any, right: Any) -> bool:
    """JSON comparison that does not treat booleans as integers."""

    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _strict_json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _hydrate_execution_lifecycle(state: dict[str, Any]) -> dict[str, Any]:
    """Restore bounded lifecycle fields stored inside the PG config JSON."""

    config = state.get("config")
    lifecycle = config.get("execution_lifecycle") if isinstance(config, dict) else None
    top_level_fields = {
        field for field in _EXECUTION_LIFECYCLE_FIELDS if field in state
    }
    if not isinstance(lifecycle, dict):
        if top_level_fields & _CORE_EXECUTION_LIFECYCLE_FIELDS:
            raise ValueError(
                "top-level execution lifecycle requires a complete config envelope"
            )
        return state
    required = {
        "status",
        "lifecycle_status",
        "completion_kind",
        "request_succeeded",
        "success",
        "full_media_success",
        "pipeline_complete",
        "publish_allowed",
        "delivery_accepted",
    }
    allowed = required | {"execution_profile_id", "provider_job_caps"}
    if set(lifecycle) - allowed or not required.issubset(lifecycle):
        raise ValueError("execution lifecycle envelope has invalid fields")
    status = lifecycle["status"]
    if status not in {"completed_bounded", "policy_blocked"}:
        raise ValueError("execution lifecycle status is invalid")
    if lifecycle["lifecycle_status"] != status:
        raise ValueError("execution lifecycle status mismatch")
    for key in (
        "request_succeeded",
        "success",
        "full_media_success",
        "pipeline_complete",
        "publish_allowed",
        "delivery_accepted",
    ):
        if type(lifecycle[key]) is not bool:
            raise ValueError(f"execution lifecycle {key} must be boolean")
    expected_request_succeeded = status == "completed_bounded"
    if lifecycle["request_succeeded"] is not expected_request_succeeded:
        raise ValueError("execution lifecycle request_succeeded invariant failed")
    if any(
        lifecycle[key]
        for key in (
            "success",
            "full_media_success",
            "pipeline_complete",
            "publish_allowed",
            "delivery_accepted",
        )
    ):
        raise ValueError("execution lifecycle cannot escalate bounded success")
    if status == "completed_bounded" and lifecycle["completion_kind"] not in {
        "no_media",
        "bounded_media",
    }:
        raise ValueError("execution lifecycle completion_kind is invalid")
    if status == "policy_blocked" and lifecycle["completion_kind"] != "legacy_no_policy_blocked":
        raise ValueError("execution lifecycle blocked completion_kind is invalid")

    if status == "completed_bounded":
        profile_id = lifecycle.get("execution_profile_id")
        provider_caps = lifecycle.get("provider_job_caps")
        persisted_profile = config.get("effective_generation_execution_profile")
        persisted_caps = config.get("provider_job_caps")
        if (
            type(profile_id) is not str
            or type(provider_caps) is not dict
            or type(persisted_profile) is not dict
            or persisted_profile.get("profile_id") != profile_id
            or not _strict_json_equal(
                persisted_profile.get("provider_job_caps"),
                provider_caps,
            )
            or not _strict_json_equal(persisted_caps, provider_caps)
        ):
            raise ValueError("execution lifecycle profile/caps mismatch")

    for field in top_level_fields:
        if field not in lifecycle or not _strict_json_equal(state[field], lifecycle[field]):
            raise ValueError(f"execution lifecycle top-level mismatch: {field}")
    hydrated = dict(state)
    for field in _EXECUTION_LIFECYCLE_FIELDS:
        if field in lifecycle:
            hydrated[field] = lifecycle[field]
    return hydrated


async def persist_background_failure(
    state_manager: Any,
    *,
    label: str,
    reason: str,
    error: Exception,
) -> None:
    """Persist a fail-closed terminal state for escaped background failures."""

    state = await state_manager.load(label)
    if state is None:
        return
    for field in _CORE_EXECUTION_LIFECYCLE_FIELDS:
        state.pop(field, None)
    config = state.get("config")
    if isinstance(config, dict):
        config.pop("execution_lifecycle", None)
    state["pipeline_degraded"] = True
    state["degraded_reason"] = reason
    state["current_step"] = None
    errors = state.setdefault("errors", [])
    message = f"{reason}: {type(error).__name__}"
    if message not in errors:
        errors.append(message)
    await state_manager.save(label, state)


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
                data = _repository_payload(state)
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

        Sprint 3 P3-5: Logs a warning when persisted state's schema_version
        differs from runtime STATE_SCHEMA_VERSION (missing == 0). Loading
        proceeds — callers decide whether to migrate. This is observability,
        not enforcement: the goal is to detect drift before it bites.
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
                    # Phase 0 #1 (2026-05-15): runtime state columns added by
                    # Alembic 7a2f4b8c9d12. Pre-migration PG schemas may not
                    # have them — degrade gracefully to defaults so load
                    # never crashes on an un-migrated DB.
                    def _safe_get(col: str, default: Any = None) -> Any:
                        try:
                            return row[col]
                        except (KeyError, IndexError):
                            return default

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
                        "schema_version": _safe_get("schema_version", 0),
                        "pipeline_degraded": _safe_get("pipeline_degraded", False),
                        "degraded_reason": _safe_get("degraded_reason"),
                        "trace_id": _safe_get("trace_id"),
                        "structured_errors": _safe_get("structured_errors", []) or [],
                        "tenant_id": _safe_get("tenant_id"),
                        "regenerate_chain": _safe_get("regenerate_chain", []) or [],
                        "soft_degraded_reasons": _safe_get("soft_degraded_reasons", []) or [],
                    }
            except Exception as e:
                logger.warning("PG load failed, using filesystem: %s", str(e)[:100])
                fs_state = _hydrate_execution_lifecycle(fs_state) if fs_state is not None else None
                _check_schema_version(fs_state, label)
                return fs_state

        # PG has data — return it (primary source of truth)
        if pg_state is not None:
            pg_state = _hydrate_execution_lifecycle(pg_state)
            _check_schema_version(pg_state, label)
            return pg_state

        # PG is empty but FS has data — PG was down during save. Backfill.
        if fs_state is not None and self.use_pg and is_pg_available():
            logger.info(
                "PG miss but FS hit for label=%s — backfilling PG from filesystem",
                label,
            )
            try:
                repo = PipelineStateRepository()
                await repo.create({"label": label, **_repository_payload(fs_state)})
            except Exception as e:
                logger.warning("PG backfill failed for %s: %s", label, str(e)[:100])
            fs_state = _hydrate_execution_lifecycle(fs_state)
            _check_schema_version(fs_state, label)
            return fs_state

        # Neither has data
        fs_state = _hydrate_execution_lifecycle(fs_state) if fs_state is not None else None
        _check_schema_version(fs_state, label)
        return fs_state

    async def exists(self, label: str) -> bool:
        """Check if state exists (PG or filesystem)."""
        if self.use_pg and is_pg_available():
            try:
                repo = PipelineStateRepository()
                row = await repo.get_by_label(label)
                if row:
                    return True
            except Exception as exc:
                logger.warning(
                    "PG state existence check failed for %s: %s",
                    label,
                    str(exc)[:100],
                )
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
            data = _repository_payload(state)
            existing = await repo.get_by_label(label)
            if existing:
                await repo.update(existing["id"], data)
            else:
                await repo.create({"label": label, **data})
            count += 1
        return count
