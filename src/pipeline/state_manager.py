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

import asyncio
import fcntl
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.config import OUTPUT_DIR as _CONFIG_OUTPUT_DIR
from src.models.pipeline_completion import (
    bind_claim_to_facts,
    derive_pipeline_completion_facts,
)
from src.models.transparency import TransparencyProjectionV1

PipelineStateRepository: Any = None
is_pg_available: Any = lambda: False
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
    "transparency",
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
_STATE_AUDIT_ARRAY_FIELDS = ("regenerate_chain", "soft_degraded_reasons")
_MISSING = object()
_PIPELINE_COMPLETION_CLAIM_KEY = "pipeline_completion_metric_v1"
_CUSTOM_COMPLETION_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}


class ScenarioStateIntegrityError(ValueError):
    """Persisted scenario state violates the stable machine contract."""


def _normalize_state_audit_arrays(
    state: Any,
    *,
    materialize_missing: bool = False,
) -> dict[str, Any]:
    """Default missing legacy fields and reject every malformed present value."""

    if not isinstance(state, dict):
        raise ScenarioStateIntegrityError("scenario_state_integrity_error:root")
    normalized = dict(state)
    for field in _STATE_AUDIT_ARRAY_FIELDS:
        if field not in normalized:
            if materialize_missing:
                normalized[field] = []
            continue
        value = normalized[field]
        if type(value) is not list or not all(type(item) is dict for item in value):
            raise ScenarioStateIntegrityError(
                f"scenario_state_integrity_error:{field}"
            )
        normalized[field] = [dict(item) for item in value]
    return normalized


def _normalize_transparency_projection(state: dict[str, Any]) -> dict[str, Any]:
    """Preserve one strict durable sidecar pointer and reject malformed truth."""

    if "transparency" not in state:
        return state
    try:
        projection = TransparencyProjectionV1.model_validate(state["transparency"])
    except ValidationError as exc:
        raise ScenarioStateIntegrityError(
            "scenario_state_integrity_error:transparency"
        ) from exc
    normalized = dict(state)
    normalized["transparency"] = projection.model_dump(mode="json")
    return normalized


def _validate_label(label: str) -> None:
    if not label or not isinstance(label, str) or not _LABEL_PATTERN.match(label):
        raise ValueError(f"Invalid label: {label!r}. Only alphanumeric, hyphen, underscore allowed.")


def _postgres_persistence_configured() -> bool:
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    return bool(os.getenv("DATABASE_URL", "").strip()) or environment in {
        "prod",
        "production",
    }


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
    state_for_pg = _normalize_transparency_projection(
        _normalize_state_audit_arrays(state, materialize_missing=True)
    )
    lifecycle_status = state.get("lifecycle_status")
    has_terminal_lifecycle = (
        lifecycle_status in {"completed_bounded", "completed_full", "policy_blocked"}
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


def _lifecycle_profile_matches(
    state: dict[str, Any],
    lifecycle: dict[str, Any],
    persisted_profile: Any,
) -> bool:
    from src.pipeline.generation_policy import (
        BOUNDED_MEDIA_STEP_PROFILES,
        GENERATION_EXECUTION_PROFILE_VERSION,
        NO_MEDIA_STEP_PROFILES,
        S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS,
        S2_SEGMENTED_MEDIA_STEP_PROFILES,
    )
    from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS

    required_fields = {
        "version",
        "profile_id",
        "scenario",
        "allowed_steps",
        "provider_job_caps",
        "completion_kind",
        "refs_only",
    }
    if type(persisted_profile) is not dict or set(persisted_profile) != required_fields:
        return False
    scenario = state.get("scenario")
    completion_kind = lifecycle.get("completion_kind")
    profile_id = lifecycle.get("execution_profile_id")
    provider_caps = lifecycle.get("provider_job_caps")
    if (
        scenario not in SCENARIO_STEP_ORDERS
        or persisted_profile.get("version") != GENERATION_EXECUTION_PROFILE_VERSION
        or persisted_profile.get("scenario") != scenario
        or persisted_profile.get("profile_id") != profile_id
        or persisted_profile.get("completion_kind") != completion_kind
        or type(persisted_profile.get("refs_only")) is not bool
        or type(persisted_profile.get("allowed_steps")) is not list
        or type(provider_caps) is not dict
        or any(
            type(key) is not str or type(cap) is not int or cap < 0
            for key, cap in provider_caps.items()
        )
        or not _strict_json_equal(persisted_profile.get("provider_job_caps"), provider_caps)
    ):
        return False

    expected_profile_id: str
    expected_steps: list[str]
    expected_refs_only = False
    expected_caps: dict[str, int] | None = None
    if completion_kind == "full_media":
        expected_profile_id = f"{GENERATION_EXECUTION_PROFILE_VERSION}:{scenario}:full-media"
        expected_steps = list(SCENARIO_STEP_ORDERS[scenario])
    elif completion_kind == "no_media":
        expected_profile_id = f"{GENERATION_EXECUTION_PROFILE_VERSION}:{scenario}:no-media"
        expected_steps = list(NO_MEDIA_STEP_PROFILES[scenario])
        expected_caps = {}
    elif completion_kind == "bounded_media" and scenario == "s2":
        stop_step = str(profile_id).removeprefix(
            f"{GENERATION_EXECUTION_PROFILE_VERSION}:s2:"
        )
        if stop_step not in S2_SEGMENTED_MEDIA_STEP_PROFILES:
            return False
        expected_profile_id = f"{GENERATION_EXECUTION_PROFILE_VERSION}:s2:{stop_step}"
        expected_steps = list(S2_SEGMENTED_MEDIA_STEP_PROFILES[stop_step])
        expected_caps = dict(S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS[stop_step])
        expected_refs_only = stop_step in {"assemble_final", "audit"}
    elif completion_kind == "bounded_media" and scenario in BOUNDED_MEDIA_STEP_PROFILES:
        expected_profile_id = (
            f"{GENERATION_EXECUTION_PROFILE_VERSION}:{scenario}:bounded-seedance"
        )
        expected_steps = list(BOUNDED_MEDIA_STEP_PROFILES[scenario])
        expected_caps = {"image": 1, "video": 1}
    else:
        return False

    return (
        profile_id == expected_profile_id
        and persisted_profile["allowed_steps"] == expected_steps
        and persisted_profile["refs_only"] is expected_refs_only
        and (
            expected_caps is None
            or _strict_json_equal(provider_caps, expected_caps)
        )
    )


def _hydrate_execution_lifecycle(state: dict[str, Any]) -> dict[str, Any]:
    """Restore and validate terminal lifecycle fields stored in PG config JSON."""

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
    assert isinstance(config, dict)
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
    if status not in {"completed_bounded", "completed_full", "policy_blocked"}:
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
    expected_request_succeeded = status in {"completed_bounded", "completed_full"}
    if lifecycle["request_succeeded"] is not expected_request_succeeded:
        raise ValueError("execution lifecycle request_succeeded invariant failed")
    if status == "completed_full":
        if lifecycle["completion_kind"] != "full_media" or any(
            lifecycle[key] is not True
            for key in ("success", "full_media_success", "pipeline_complete")
        ):
            raise ValueError("execution lifecycle full completion invariant failed")
        if lifecycle["publish_allowed"] or lifecycle["delivery_accepted"]:
            raise ValueError("generation completion cannot grant publish or delivery")
        if (
            state.get("pipeline_degraded") is True
            or bool(state.get("errors"))
            or bool(state.get("media_synthesis_errors"))
            or bool(state.get("soft_degraded_reasons"))
            or state.get("current_step") is not None
        ):
            raise ValueError("full execution lifecycle cannot be degraded or errored")
    else:
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

    if status in {"completed_bounded", "completed_full"}:
        profile_id = lifecycle.get("execution_profile_id")
        provider_caps = lifecycle.get("provider_job_caps")
        persisted_profile = config.get("effective_generation_execution_profile")
        persisted_caps = config.get("provider_job_caps")
        if (
            type(profile_id) is not str
            or type(provider_caps) is not dict
            or not _lifecycle_profile_matches(state, lifecycle, persisted_profile)
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

    def _save_to_fs_unlocked(self, label: str, state: dict[str, Any]) -> None:
        """Serialize state while the caller owns the per-label lock.

        P1-3: Writes to a temporary file first, then performs an atomic
        rename via os.replace(). This ensures that a crash during write
        never leaves a partially-written (truncated) JSON file.
        """
        normalized_state = _normalize_transparency_projection(
            _normalize_state_audit_arrays(state)
        )
        state_path = self._state_path(label)
        tmp_path = state_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(normalized_state, f, indent=2, ensure_ascii=False, default=_json_default)
            f.flush()
            os.fsync(f.fileno())  # Ensure data hits disk before rename
        # Atomic replace: readers always see a complete file
        os.replace(tmp_path, state_path)

    def _save_to_fs(self, label: str, state: dict[str, Any]) -> None:
        """Save state while preserving an existing server-owned claim."""

        lock_path = self._state_path(label).with_suffix(".completion.lock")
        with open(lock_path, "a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                current = self._load_from_fs(label)
                current_config = current.get("config") if current is not None else None
                if type(current_config) is dict and _PIPELINE_COMPLETION_CLAIM_KEY in current_config:
                    config = dict(state.get("config") or {})
                    config[_PIPELINE_COMPLETION_CLAIM_KEY] = current_config[
                        _PIPELINE_COMPLETION_CLAIM_KEY
                    ]
                    state["config"] = config
                self._save_to_fs_unlocked(label, state)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _cache_pipeline_completion_claim(
        self,
        label: str,
        claim: dict[str, Any],
    ) -> None:
        """Merge only the PG-winning claim into the existing filesystem cache."""

        lock_path = self._state_path(label).with_suffix(".completion.lock")
        with open(lock_path, "a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                current = self._load_from_fs(label)
                if current is None:
                    return
                current_config = current.get("config")
                if type(current_config) is not dict:
                    raise RuntimeError("pipeline completion config is invalid")
                updated_config = dict(current_config)
                updated_config[_PIPELINE_COMPLETION_CLAIM_KEY] = claim
                current["config"] = updated_config
                self._save_to_fs_unlocked(label, current)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_from_fs(self, label: str) -> dict[str, Any] | None:
        """Deserialize state from JSON file.

        Returns None if the state file does not exist.
        """
        state_path = self._state_path(label)
        if not state_path.exists():
            return None
        with open(state_path, encoding="utf-8") as f:
            return _normalize_transparency_projection(
                _normalize_state_audit_arrays(json.load(f))
            )

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
                    saved = await repo.update(existing["id"], data)
                    saved_config = saved.get("config") if isinstance(saved, dict) else None
                    if type(saved_config) is dict:
                        state["config"] = dict(saved_config)
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

    async def claim_pipeline_completion(
        self,
        label: str,
        state: dict[str, Any],
        claim: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Persist and return one claim bound to current durable terminal truth."""

        _validate_label(label)
        if self.use_pg and is_pg_available():
            repo = PipelineStateRepository()
            winning_claim = await repo.claim_pipeline_completion(label, claim)
            if winning_claim is None:
                raise RuntimeError("pipeline completion store is unavailable")
            if winning_claim is False:
                return None
            config = dict(state.get("config") or {})
            config[_PIPELINE_COMPLETION_CLAIM_KEY] = winning_claim
            state["config"] = config
            await asyncio.to_thread(
                self._cache_pipeline_completion_claim,
                label,
                winning_claim,
            )
            return winning_claim
        if self.use_pg and _postgres_persistence_configured():
            raise RuntimeError("pipeline completion store is unavailable")

        def _claim_filesystem() -> dict[str, Any] | None:
            lock_path = self._state_path(label).with_suffix(".completion.lock")
            with open(lock_path, "a+b") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    current = self._load_from_fs(label)
                    if current is None:
                        raise RuntimeError("pipeline completion state is missing")
                    current_config = current.get("config")
                    if type(current_config) is not dict:
                        raise RuntimeError("pipeline completion config is invalid")
                    if _PIPELINE_COMPLETION_CLAIM_KEY in current_config:
                        return None
                    durable_facts = derive_pipeline_completion_facts(current)
                    if durable_facts is None:
                        return None
                    winning_claim = bind_claim_to_facts(claim, durable_facts)
                    updated_config = dict(current_config)
                    updated_config[_PIPELINE_COMPLETION_CLAIM_KEY] = winning_claim
                    current["config"] = updated_config
                    self._save_to_fs_unlocked(label, current)
                    return winning_claim
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        winning_claim = await asyncio.to_thread(_claim_filesystem)
        if winning_claim is not None:
            config = dict(state.get("config") or {})
            config[_PIPELINE_COMPLETION_CLAIM_KEY] = winning_claim
            state["config"] = config
        return winning_claim

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

                    transparency_value = _safe_get("transparency", _MISSING)

                    pg_state = _normalize_transparency_projection(
                        _normalize_state_audit_arrays({
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
                        **(
                            {"regenerate_chain": _safe_get("regenerate_chain")}
                            if _safe_get("regenerate_chain", _MISSING) is not _MISSING
                            else {}
                        ),
                        **(
                            {"soft_degraded_reasons": _safe_get("soft_degraded_reasons")}
                            if _safe_get("soft_degraded_reasons", _MISSING) is not _MISSING
                            else {}
                        ),
                        **(
                            {"transparency": transparency_value}
                            if transparency_value is not _MISSING
                            and transparency_value is not None
                            else {}
                        ),
                    }, materialize_missing=True)
                    )
            except ScenarioStateIntegrityError:
                raise
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


async def claim_pipeline_completion(
    state_manager: Any,
    *,
    label: str,
    state: dict[str, Any],
    claim: dict[str, Any],
) -> dict[str, Any] | None:
    """Use durable truth plus storage atomicity for the winning claim."""

    if isinstance(state_manager, PipelineStateManager):
        return await state_manager.claim_pipeline_completion(label, state, claim)

    lock_key = (id(asyncio.get_running_loop()), label)
    lock = _CUSTOM_COMPLETION_LOCKS.setdefault(lock_key, asyncio.Lock())
    async with lock:
        current = await state_manager.load(label)
        durable = current if current is not None else state
        config = durable.get("config")
        if type(config) is not dict:
            raise RuntimeError("pipeline completion config is invalid")
        if _PIPELINE_COMPLETION_CLAIM_KEY in config:
            return None
        durable_facts = derive_pipeline_completion_facts(durable)
        if durable_facts is None:
            return None
        winning_claim = bind_claim_to_facts(claim, durable_facts)
        updated_config = dict(config)
        updated_config[_PIPELINE_COMPLETION_CLAIM_KEY] = winning_claim
        durable["config"] = updated_config
        await state_manager.save(label, durable)
        state["config"] = dict(updated_config)
        return winning_claim
