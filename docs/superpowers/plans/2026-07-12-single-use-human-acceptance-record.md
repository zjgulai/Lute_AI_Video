# Single-Use Human Acceptance Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the W1-22 tenant-bound, final-artifact-bound, idempotently created, revocable, expiring, single-use human acceptance authority for canonical async Fast and S1-S5 final videos.

**Architecture:** A shared output-artifact identity module canonicalizes tenant paths and hashes exact bytes. A dedicated PostgreSQL/SQLite `acceptance_records` ledger owns decision history and atomic state transitions; a source resolver binds records to the existing durable submission ledger. A service and authenticated router expose create/read/revoke while keeping consume internal for W1-23.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, asyncpg, SQLite, Alembic, PostgreSQL 18, pytest/pytest-asyncio, Ruff, Next.js 16 generated OpenAPI types.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-07-12-single-use-human-acceptance-record-design.md`.
- Roadmap scope is W1-22 only; do not modify distribution publish authority in this plan.
- Final authority is limited to exact Fast/S1-S5 final videos under `tenants/<tenant>/pending_review/<resource>/`.
- `tenant_id`, `scenario`, reviewer identity, artifact digest/size, status, expiry, and consume metadata are server-owned.
- Acceptance mutation requires `artifact:accept` or `all`; `provider:submit` alone is insufficient.
- `Idempotency-Key` uses the existing 16-128 character grammar; persist only its SHA-256 hash.
- `expires_in_seconds` is a strict integer from 300 through 86400, default 3600.
- There is no HTTP consume endpoint and no new review UI.
- PostgreSQL production behavior fails closed; SQLite is development/test only.
- `production unchanged`, `provider_call=false`; no production migration, deploy, provider generation, publish, delivery, or `.env` read.
- Preserve the existing dirty Wave 1A worktree. Do not reformat, revert, stage, commit, push, or open a PR without separate authorization.
- Add no dependency. Regenerate OpenAPI TypeScript only through `cd web && npm run typegen:api`.
- Every behavior change follows RED → verify expected failure → minimal GREEN → focused regression → diff checkpoint.

## File Structure

**Create:**

- `src/models/acceptance.py` — strict HTTP/domain models and safe response projections.
- `src/services/artifact_identity.py` — shared canonical output-path ownership and streaming digest logic.
- `src/services/acceptance_source.py` — Fast/Scenario durable final-artifact source projection and eligibility.
- `src/storage/acceptance_repository.py` — atomic PostgreSQL/SQLite acceptance ledger.
- `src/services/artifact_acceptance.py` — header/fingerprint/error/service orchestration and internal consume boundary.
- `src/routers/acceptance_records.py` — create/read/revoke HTTP adapter.
- `migrations/alembic/versions/e8f1a2b3c4d5_add_acceptance_records.py` — additive W1-22 schema.
- `tests/test_artifact_acceptance_contracts.py` — strict models, fingerprint, path, digest, and source projection.
- `tests/test_acceptance_record_repository.py` — real isolated SQLite plus PostgreSQL SQL/concurrency contracts.
- `tests/test_artifact_acceptance_service.py` — Fast/S1-S5 source/service/revoke/consume behavior.
- `tests/test_acceptance_records_router.py` — auth, safe validation, status codes, tenant isolation, and OpenAPI.
- `docs/runbooks/artifact-acceptance-lifecycle.md` — operator lifecycle, recovery, and W1-23 boundary.
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md` — durable local acceptance status and evidence boundary.

**Modify:**

- `src/routers/media.py` — delegate existing path resolution/scope checks to the shared identity module without changing public behavior.
- `src/routers/_deps.py` — recognize `artifact:accept`.
- `src/routers/scenario.py` — persist canonical Scenario final-artifact source projection.
- `src/api.py` — mount the acceptance router; existing CORS header remains unchanged.
- `src/storage/db.py` — SQLite schema and PostgreSQL required-table readiness.
- `src/storage/migrations/001_init.sql` — fresh PostgreSQL acceptance table/indexes.
- `scripts/pg_dump_logical.py`, `scripts/pg_restore_logical.py`, `scripts/verify_restored_database.py` — 14-table recovery contract.
- `tests/test_auth_context.py`, `tests/test_scenario_generation_safety_policy.py` — permission normalization.
- `tests/test_p0_media_tenant_security.py` — media behavior remains unchanged after extraction.
- `tests/test_backup_production_contract.py`, `tests/test_run_alembic_upgrade.py` — schema/recovery governance.
- `web/src/types/api.generated.ts` — generated API contract only.
- `configs/backend-route-auth-contract.yaml`, `docs/runbooks/backend-route-auth-contract.md`, `docs/reference/api-endpoints.md`, `docs/runbooks/README.md` — route/permission/operator truth.
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`, `docs/runbooks/artifact-acceptance-lifecycle.md`, and `AGENTS.md` — only after fresh verification supports the durable fact.

---

### Task 1: Strict Acceptance Contracts and Shared Artifact Identity

**Files:**

- Create: `src/models/acceptance.py`
- Create: `src/services/artifact_identity.py`
- Create: `tests/test_artifact_acceptance_contracts.py`
- Modify: `src/routers/media.py`
- Test: `tests/test_p0_media_tenant_security.py`

**Interfaces:**

- Produces `AcceptanceCreateRequest`, `AcceptanceArtifactProjection`, `AcceptanceReviewerProjection`, and `AcceptanceRecordResponse`.
- Produces `CanonicalOutputPath`, `canonicalize_output_artifact_path`, `ResolvedOutputArtifact`, and `resolve_output_artifact` for media serving, source projection, and consume integrity checks.
- Preserves `media.sign_media_url()`, `classify_media_scope()`, `authorize_media_path()`, and all existing `/api/media/*` behavior.

- [x] **Step 1: Write RED tests for strict request models**

Add the following behavioral skeleton to `tests/test_artifact_acceptance_contracts.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError


def _valid_request() -> dict[str, object]:
    return {
        "source_resource_type": "scenario",
        "source_resource_id": "s2_1783830000_abcdef12",
        "artifact_path": (
            "tenants/tenant-alpha/pending_review/"
            "s2_1783830000_abcdef12/assemble/final.mp4"
        ),
        "decision": "accepted",
        "review_notes": "Reviewed exact final render.",
        "expires_in_seconds": 3600,
    }


def test_acceptance_request_is_strict_and_forbids_server_authority_fields() -> None:
    from src.models.acceptance import AcceptanceCreateRequest

    parsed = AcceptanceCreateRequest.model_validate(_valid_request())
    assert parsed.expires_in_seconds == 3600

    for field, value in {
        "tenant_id": "attacker-tenant",
        "scenario": "s5",
        "reviewer_id": "self-asserted",
        "artifact_sha256": "a" * 64,
        "publish_allowed": True,
    }.items():
        with pytest.raises(ValidationError):
            AcceptanceCreateRequest.model_validate({**_valid_request(), field: value})


@pytest.mark.parametrize("value", [True, 299, 86401, 3600.0, "3600"])
def test_acceptance_expiry_is_a_bounded_strict_integer(value: object) -> None:
    from src.models.acceptance import AcceptanceCreateRequest

    with pytest.raises(ValidationError):
        AcceptanceCreateRequest.model_validate(
            {**_valid_request(), "expires_in_seconds": value}
        )
```

- [x] **Step 2: Write RED path and digest tests**

Add tests that create a real file under `tmp_path/tenants/tenant-alpha/pending_review/<resource>/assemble/final.mp4`, then assert:

```python
def test_resolver_returns_canonical_tenant_file_and_digest(tmp_path: Path) -> None:
    from src.services.artifact_identity import resolve_output_artifact

    relative = (
        "tenants/tenant-alpha/pending_review/"
        "s2_1783830000_abcdef12/assemble/final.mp4"
    )
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"final-video-fixture")

    resolved = resolve_output_artifact(
        relative,
        output_dir=tmp_path,
        tenant_id="tenant-alpha",
        required_prefix=(
            "tenants/tenant-alpha/pending_review/"
            "s2_1783830000_abcdef12"
        ),
        allowed_suffixes={".mp4", ".webm"},
    )

    assert resolved.canonical_path == relative
    assert resolved.size_bytes == len(b"final-video-fixture")
    assert len(resolved.sha256) == 64
```

Parameterize traversal, encoded traversal, URL schemes, query/fragment, cross-tenant paths, `quarantine`, intermediate paths, unsupported suffix, empty file, and symlink escape. Each must raise a typed path error without exposing the host path.

Add two absolute-path boundary assertions: a client/media-style call using the
default `allow_absolute_under_root=False` rejects an absolute path even when the
file is below `output_dir`; the server-owned Scenario projection path succeeds
only when it explicitly passes `allow_absolute_under_root=True` and still
returns the canonical tenant-relative path.

- [x] **Step 3: Run RED and confirm missing modules are the only failures**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_p0_media_tenant_security.py -q
```

Expected: new tests fail with `ModuleNotFoundError` for `src.models.acceptance` or `src.services.artifact_identity`; existing media tests remain collectable.

- [x] **Step 4: Implement strict models**

Create `src/models/acceptance.py` with this public shape:

```python
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AcceptanceCreateRequest(_StrictModel):
    source_resource_type: Literal["fast", "scenario"]
    source_resource_id: str = Field(min_length=1, max_length=128)
    artifact_path: str = Field(min_length=1, max_length=1024)
    decision: Literal["accepted", "rejected"]
    review_notes: str = Field(min_length=1, max_length=2000)
    expires_in_seconds: int = Field(default=3600, strict=True, ge=300, le=86400)

    @field_validator("source_resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        if _RESOURCE_ID_RE.fullmatch(value) is None:
            raise ValueError("source_resource_id is invalid")
        return value


class AcceptanceArtifactProjection(_StrictModel):
    path: str
    sha256: str
    size_bytes: int
    kind: Literal["text", "image", "audio", "video"]


class AcceptanceReviewerProjection(_StrictModel):
    key_id: str
    key_type: Literal["tenant", "test_bundle", "env_fallback"]


class AcceptanceRecordResponse(_StrictModel):
    acceptance_id: str
    tenant_id: str
    source_resource_type: Literal["fast", "scenario"]
    source_resource_id: str
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"]
    artifact: AcceptanceArtifactProjection
    decision: Literal["accepted", "rejected"]
    status: Literal["available", "rejected", "consumed", "expired", "revoked"]
    reviewer: AcceptanceReviewerProjection
    review_notes: str
    expires_at: str
    consumed_at: str | None
    revoked_at: str | None
    idempotent_replay: bool
    created_at: str
    updated_at: str
```

- [x] **Step 5: Implement shared artifact identity and keep media compatibility**

Create `src/services/artifact_identity.py` with:

```python
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
    if parts[0] == "tenants" and len(parts) >= 3:
        return parts[1]
    if parts[0] == "uploads" and len(parts) >= 3:
        return parts[1]
    return "default"


def canonicalize_output_artifact_path(
    value: str,
    *,
    output_dir: Path,
    tenant_id: str,
    required_prefix: str,
    allowed_suffixes: set[str],
    allow_absolute_under_root: bool = False,
) -> CanonicalOutputPath:
    root = output_dir.resolve()
    raw_path = Path(value)
    if raw_path.is_absolute():
        if not allow_absolute_under_root:
            raise ArtifactIdentityError("invalid artifact path")
        candidate = raw_path.resolve()
    else:
        reference = validate_output_reference(value)
        candidate = (root / reference).resolve()
    try:
        canonical = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ArtifactIdentityError("invalid artifact path") from exc
    if classify_output_scope(canonical) != tenant_id:
        raise ArtifactNotFoundError("artifact not found")
    prefix = required_prefix.rstrip("/") + "/"
    if not canonical.startswith(prefix):
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
```

Move the media router's path validation/scope logic behind imports from this module while keeping small compatibility wrappers with the existing function names. Media calls `canonicalize_output_artifact_path` with `allow_absolute_under_root=False` and does not hash a file merely to sign or serve it. Do not change response codes, signatures, token payloads, public roots, or cache headers.

- [x] **Step 6: Run GREEN and focused Ruff**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_p0_media_tenant_security.py -q
.venv/bin/python -m ruff check \
  src/models/acceptance.py \
  src/services/artifact_identity.py \
  src/routers/media.py \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_p0_media_tenant_security.py
```

Expected: all selected tests pass and Ruff exits `0`.

- [x] **Step 7: Inspect the task diff without staging or committing**

Run:

```bash
git diff --check
git diff -- src/models/acceptance.py src/services/artifact_identity.py \
  src/routers/media.py tests/test_artifact_acceptance_contracts.py \
  tests/test_p0_media_tenant_security.py
```

Expected: no whitespace errors; every changed line belongs to Task 1.

---

### Task 2: Durable Schema and Atomic Acceptance Repository

**Files:**

- Create: `migrations/alembic/versions/e8f1a2b3c4d5_add_acceptance_records.py`
- Create: `src/storage/acceptance_repository.py`
- Create: `tests/test_acceptance_record_repository.py`
- Modify: `src/storage/db.py`
- Modify: `src/storage/migrations/001_init.sql`
- Test: `tests/test_submission_idempotency_repository.py`

**Interfaces:**

- Consumes the existing `idempotency_records` source row.
- Produces `CreateAcceptanceResult`, `AcceptanceRecordRepository`, and typed storage errors.
- Produces schema head `e8f1a2b3c4d5`, with production readiness requiring `acceptance_records`.

- [x] **Step 1: Write RED schema and SQLite repository tests**

Create an isolated SQLite fixture matching `tests/test_submission_idempotency_repository.py`, seed one completed source row, then assert:

```python
@pytest.mark.asyncio
async def test_create_owner_replay_conflict_and_one_available_per_path(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceAlreadyAvailableError,
        AcceptancePayloadConflictError,
        AcceptanceRecordRepository,
    )

    repo = AcceptanceRecordRepository(require_postgres=False)
    owner = await repo.create_or_replay(**_record_kwargs())
    replay = await repo.create_or_replay(**_record_kwargs())
    assert owner.outcome == "owner"
    assert replay.outcome == "replay"
    assert owner.record["id"] == replay.record["id"]

    with pytest.raises(AcceptancePayloadConflictError):
        await repo.create_or_replay(**_record_kwargs(request_hash="c" * 64))

    with pytest.raises(AcceptanceAlreadyAvailableError):
        await repo.create_or_replay(
            **_record_kwargs(creation_key_hash="d" * 64, artifact_sha256="e" * 64)
        )
```

Add tests for rejected decision revoking the previous available row with `revoked_by_record_id`, accepted-after-rejected creating a new available row, expiry reconciliation, idempotent explicit revoke, consume one-winner behavior, digest/path mismatch, tenant isolation, close/reopen reconstruction, and production no-fallback.

- [x] **Step 2: Run RED and verify the missing table/repository failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_acceptance_record_repository.py -q
```

Expected: collection or first test fails because the repository/table does not exist; the source idempotency fixture itself succeeds.

- [x] **Step 3: Add the additive Alembic and fresh PostgreSQL schema**

Create revision `e8f1a2b3c4d5` descending from `d5e6f7a8b9c0`. The migration and `001_init.sql` must create this contract:

```sql
CREATE TABLE IF NOT EXISTS acceptance_records (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    creation_key_hash VARCHAR(64) NOT NULL,
    fingerprint_version VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    source_resource_type VARCHAR(16) NOT NULL
        CHECK (source_resource_type IN ('fast', 'scenario')),
    source_resource_id VARCHAR(128) NOT NULL,
    scenario VARCHAR(16) NOT NULL
        CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
    artifact_path TEXT NOT NULL,
    artifact_sha256 VARCHAR(64) NOT NULL,
    artifact_size_bytes BIGINT NOT NULL CHECK (artifact_size_bytes > 0),
    artifact_kind VARCHAR(16) NOT NULL
        CHECK (artifact_kind IN ('text', 'image', 'audio', 'video')),
    decision VARCHAR(16) NOT NULL
        CHECK (decision IN ('accepted', 'rejected')),
    record_status VARCHAR(16) NOT NULL
        CHECK (record_status IN ('available', 'rejected', 'consumed', 'expired', 'revoked')),
    reviewer_key_id VARCHAR(128) NOT NULL,
    reviewer_key_type VARCHAR(32) NOT NULL
        CHECK (reviewer_key_type IN ('tenant', 'test_bundle', 'env_fallback')),
    review_notes TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    consumed_by_operation VARCHAR(64),
    consumed_by_resource_id VARCHAR(128),
    revoked_at TIMESTAMPTZ,
    revoked_by_key_id VARCHAR(128),
    revoked_by_record_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_acceptance_records_tenant_creation_key
        UNIQUE (tenant_id, creation_key_hash),
    CONSTRAINT ck_acceptance_records_decision_status CHECK (
        (decision = 'accepted' AND record_status IN ('available', 'consumed', 'expired', 'revoked'))
        OR (decision = 'rejected' AND record_status = 'rejected')
    ),
    CONSTRAINT ck_acceptance_records_consumed_fields CHECK (
        (record_status = 'consumed' AND consumed_at IS NOT NULL
            AND consumed_by_operation IS NOT NULL
            AND consumed_by_resource_id IS NOT NULL)
        OR (record_status <> 'consumed' AND consumed_at IS NULL
            AND consumed_by_operation IS NULL
            AND consumed_by_resource_id IS NULL)
    ),
    CONSTRAINT ck_acceptance_records_revoked_fields CHECK (
        (record_status = 'revoked' AND revoked_at IS NOT NULL
            AND revoked_by_key_id IS NOT NULL)
        OR (record_status <> 'revoked' AND revoked_at IS NULL
            AND revoked_by_key_id IS NULL AND revoked_by_record_id IS NULL)
    ),
    CONSTRAINT ck_acceptance_records_expiry CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_acceptance_records_tenant_available_path
    ON acceptance_records(tenant_id, artifact_path)
    WHERE record_status = 'available';
CREATE INDEX IF NOT EXISTS idx_acceptance_records_source
    ON acceptance_records(tenant_id, source_resource_type, source_resource_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_records_status
    ON acceptance_records(tenant_id, record_status);
CREATE INDEX IF NOT EXISTS idx_acceptance_records_expiry
    ON acceptance_records(expires_at)
    WHERE record_status = 'available';
```

Use SQLite-compatible `TEXT`, `INTEGER`, and `CURRENT_TIMESTAMP` equivalents in `src/storage/db.py`, preserving identical constraints and partial indexes. Add `acceptance_records` to `_REQUIRED_TABLES`.

- [x] **Step 4: Implement repository types and backend selection**

Create these public types in `src/storage/acceptance_repository.py`; the class must expose the exact signatures listed after the code block:

```python
from dataclasses import dataclass
from typing import Any, Literal


class AcceptanceStoreUnavailableError(RuntimeError):
    pass


class AcceptancePayloadConflictError(ValueError):
    pass


class AcceptanceAlreadyAvailableError(ValueError):
    pass


class AcceptanceSourceNotFoundError(LookupError):
    pass


class AcceptanceNotRevocableError(ValueError):
    pass


class AcceptanceNotAvailableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateAcceptanceResult:
    outcome: Literal["owner", "replay"]
    record: dict[str, Any]


```

Exact `AcceptanceRecordRepository` methods:

- `__init__(self, *, require_postgres: bool | None = None) -> None`;
- `get_by_creation_key_hash(self, *, tenant_id: str, creation_key_hash: str) -> dict[str, Any] | None`;
- `get_by_id(self, *, tenant_id: str, acceptance_id: str) -> dict[str, Any] | None`;
- `create_or_replay(self, *, tenant_id: str, creation_key_hash: str, fingerprint_version: str, request_hash: str, source_resource_type: str, source_resource_id: str, scenario: str, artifact_path: str, artifact_sha256: str, artifact_size_bytes: int, artifact_kind: str, decision: str, reviewer_key_id: str, reviewer_key_type: str, review_notes: str, expires_in_seconds: int) -> CreateAcceptanceResult`;
- `reconcile_expired(self, *, tenant_id: str, acceptance_id: str | None = None, artifact_path: str | None = None) -> int`;
- `revoke(self, *, tenant_id: str, acceptance_id: str, reviewer_key_id: str) -> dict[str, Any]`;
- `consume(self, *, tenant_id: str, acceptance_id: str, artifact_path: str, artifact_sha256: str, consumer_operation: str, consumer_resource_id: str) -> dict[str, Any]`.

Backend selection must mirror `SubmissionIdempotencyRepository`: `db.get_verified_pg_pool()` is mandatory in production; development/test may use `await db.get_pool()` and then the isolated SQLite connection.

- [x] **Step 5: Implement transactional owner/replay/reject ordering**

PostgreSQL `create_or_replay` must execute, in one transaction and in this order:

```sql
SELECT id FROM idempotency_records
WHERE tenant_id = $1 AND resource_type = $2 AND resource_id = $3
FOR UPDATE;

SELECT * FROM acceptance_records
WHERE tenant_id = $1 AND creation_key_hash = $4;

UPDATE acceptance_records
SET record_status = 'expired', updated_at = NOW()
WHERE tenant_id = $1 AND artifact_path = $5
  AND record_status = 'available' AND expires_at <= NOW();
```

For `decision='rejected'`, preallocate the rejection ID, revoke an available row for the same path with `revoked_by_record_id=<new rejection id>`, then insert the rejection. For `accepted`, insert `available`. On creation-key collision, compare exact fingerprint version/request hash before any rejection/availability side effect. Map the partial unique violation to `AcceptanceAlreadyAvailableError` without returning another record's details.

SQLite performs the same sequence under `db.get_sqlite_lock()` and `BEGIN IMMEDIATE`.

- [x] **Step 6: Implement database-time reconcile, revoke, and consume**

Use compare-and-set updates. PostgreSQL consume must be equivalent to:

```sql
UPDATE acceptance_records
SET record_status = 'consumed',
    consumed_at = NOW(),
    consumed_by_operation = $5,
    consumed_by_resource_id = $6,
    updated_at = NOW()
WHERE tenant_id = $1 AND id = $2
  AND decision = 'accepted'
  AND record_status = 'available'
  AND expires_at > NOW()
  AND artifact_path = $3
  AND artifact_sha256 = $4
RETURNING *;
```

If no row updates, tenant-read the current row and raise `AcceptanceNotAvailableError` without changing it. Revoke is idempotent for an already revoked row and rejects consumed/expired/rejected records. Reconcile changes only expired available rows.

- [x] **Step 7: Run repository GREEN and migration contracts**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_acceptance_record_repository.py \
  tests/test_submission_idempotency_repository.py \
  tests/test_run_alembic_upgrade.py -q
.venv/bin/python -m ruff check \
  src/storage/acceptance_repository.py src/storage/db.py \
  migrations/alembic/versions/e8f1a2b3c4d5_add_acceptance_records.py \
  tests/test_acceptance_record_repository.py
```

Expected: repository/schema suites and Ruff pass; no router/service exists yet.

- [x] **Step 8: Inspect Task 2 diff without staging or committing**

Run `git diff --check` and inspect only the migration, schema, repository, and repository-test files.

---

### Task 3: Durable Fast/S1-S5 Acceptance Source Projection

**Files:**

- Create: `src/services/acceptance_source.py`
- Extend: `tests/test_artifact_acceptance_contracts.py`
- Modify: `src/routers/scenario.py`
- Test: `tests/test_submit_idempotency_router.py`

**Interfaces:**

- Produces immutable `AcceptanceSource`.
- Produces `project_scenario_acceptance_source(final_state, tenant_id, label, artifact_disposition, output_dir) -> dict[str, object]` for the safe submission snapshot.
- Produces `resolve_acceptance_source(record, tenant_id, requested_resource_type, requested_resource_id) -> AcceptanceSource` for Fast and Scenario records.

- [x] **Step 1: Write RED parameterized source tests**

Use real temporary final files and injected durable records:

```python
@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
def test_scenario_projection_is_canonical_and_tenant_bound(
    scenario: str, tmp_path: Path
) -> None:
    from src.services.acceptance_source import project_scenario_acceptance_source

    label = f"{scenario}_source_fixture"
    relative = f"tenants/tenant-alpha/pending_review/{label}/assemble/final.mp4"
    final_path = tmp_path / relative
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"video")
    state = {
        "pipeline_degraded": False,
        "steps": {"assemble_final": {"status": "done", "output": [str(final_path), "render.json"]}},
    }

    assert project_scenario_acceptance_source(
        state,
        tenant_id="tenant-alpha",
        label=label,
        artifact_disposition="pending_review",
        output_dir=tmp_path,
    ) == {
        "final_artifact_path": relative,
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
    }
```

Add RED cases proving host paths never persist, invalid/outside/quarantine/missing/intermediate outputs project `{}`, and Fast/Scenario eligibility derives scenario/resource from the durable record rather than request fields.

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_artifact_acceptance_contracts.py -q
```

Expected: failures identify the missing `acceptance_source` module/helper.

- [x] **Step 3: Implement source dataclass and Scenario projector**

Create:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Any


@dataclass(frozen=True, slots=True)
class AcceptanceSource:
    tenant_id: str
    resource_type: Literal["fast", "scenario"]
    resource_id: str
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"]
    record_status: str
    artifact_path: str
    artifact_disposition: str
    artifact_kind: Literal["video"]
    full_media_success: bool
    is_stub: bool
    pipeline_degraded: bool


```

Implement these exact functions below the dataclass:

- `project_scenario_acceptance_source(final_state: Mapping[str, Any], *, tenant_id: str, label: str, artifact_disposition: str, output_dir: Path) -> dict[str, object]`;
- `resolve_acceptance_source(record: Mapping[str, Any], *, tenant_id: str, requested_resource_type: str, requested_resource_id: str) -> AcceptanceSource`.

Use `get_step_output_from_state()` and `extract_assemble_paths()`. Require `steps.assemble_final.status == "done"`. Projection validates the exact tenant/resource prefix through `canonicalize_output_artifact_path` with `allow_absolute_under_root=True` and stores only the returned relative path without hashing the whole video. Request/serve/consume paths keep the default `False`. Resolver rejects resource/scenario mismatches, truly nonterminal or `recovery_required` states, and missing structural projections with typed errors; it retains `record_status`, `full_media_success`, `is_stub`, and `pipeline_degraded` so Task 4 can apply the specification's decision-specific accepted/rejected eligibility.

- [x] **Step 4: Persist the allowlisted Scenario source projection**

In the unified async Scenario background path, build a projection before `_safe_result_snapshot`:

```python
source_projection = project_scenario_acceptance_source(
    final_state,
    tenant_id=tenant_id,
    label=label,
    artifact_disposition=policy.artifact_disposition,
    output_dir=OUTPUT_DIR,
)
snapshot_input = {**final_state, **source_projection}
result_snapshot = _safe_result_snapshot(
    snapshot_input,
    allowed_keys=_SCENARIO_RESULT_SNAPSHOT_KEYS,
)
```

Add `final_artifact_path`, `artifact_disposition`, and `artifact_kind` to `_SCENARIO_RESULT_SNAPSHOT_KEYS`. Do not add them to public generation success flags and do not change provider execution.

- [x] **Step 5: Run source GREEN and neighboring submit regression**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_submit_idempotency_router.py -q
.venv/bin/python -m ruff check \
  src/services/acceptance_source.py src/routers/scenario.py \
  tests/test_artifact_acceptance_contracts.py
```

Expected: parameterized Fast/S1-S5 projection tests and existing async-submit contracts pass with zero provider calls.

- [x] **Step 6: Inspect Task 3 diff without staging or committing**

Run `git diff --check` and inspect `acceptance_source.py`, `scenario.py`, and focused tests.

---

### Task 4: Acceptance Service, Idempotent Create, Revoke, and Internal Consume

**Files:**

- Create: `src/services/artifact_acceptance.py`
- Create: `tests/test_artifact_acceptance_service.py`
- Consume: `src/models/acceptance.py`, `src/services/artifact_identity.py`, `src/services/acceptance_source.py`, `src/storage/acceptance_repository.py`

**Interfaces:**

- Produces stable `ArtifactAcceptanceError` subclasses and safe detail codes.
- Produces `ArtifactAcceptanceService.create/read/revoke/consume_for_publish`.
- Produces `get_artifact_acceptance_service()` for dependency injection.
- Produces `extract_acceptance_key(request: Request) -> str`, which rejects duplicate raw headers and maps the shared key grammar to acceptance-specific error codes.

- [x] **Step 1: Write RED fingerprint and same-action replay tests**

Add:

```python
def test_fingerprint_includes_reviewer_and_excludes_credentials() -> None:
    from src.models.acceptance import AcceptanceCreateRequest
    from src.services.artifact_acceptance import build_acceptance_fingerprint

    request = AcceptanceCreateRequest.model_validate(_valid_request())
    first = build_acceptance_fingerprint(
        request,
        tenant_id="tenant-alpha",
        reviewer_key_id="reviewer-a",
        reviewer_key_type="tenant",
    )
    second = build_acceptance_fingerprint(
        request,
        tenant_id="tenant-alpha",
        reviewer_key_id="reviewer-b",
        reviewer_key_type="tenant",
    )
    assert first.request_hash != second.request_hash
    assert "reviewer-a" not in first.request_hash
```

Add async tests that prove a same-key record found by the preflight lookup returns the original current record without touching the source or file resolver, changed payload/reviewer conflicts, and raw keys never appear in repository rows/errors. For requests that race before any acceptance row exists, require one durable owner plus replay losers and no duplicate authority; W1-22 does not introduce a distributed reservation or hold a database lock across whole-video hashing, so those initial contenders may repeat read-only source/file verification.

- [x] **Step 2: Write RED service eligibility/state tests**

Parameterize Fast/S1-S5 accepted success and these failures: bounded/no-media, Fast stub, quarantine, degraded accepted Scenario, `recovery_required`, intermediate requested path, cross-tenant path, absent assembly, missing/empty file, symlink escape, and changed bytes at consume. Add rejected-decision tests that revoke an older available record and never become consumable.

- [x] **Step 3: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_artifact_acceptance_service.py -q
```

Expected: failures identify the missing service, not provider/environment setup.

- [x] **Step 4: Implement stable errors and fingerprint**

Create:

```python
ACCEPTANCE_FINGERPRINT_VERSION = "acceptance-create.v1"


class ArtifactAcceptanceError(Exception):
    status_code = 500
    code = "artifact_acceptance_error"

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code}


class AcceptanceKeyRequired(ArtifactAcceptanceError):
    status_code = 400
    code = "acceptance_key_required"


class AcceptanceKeyInvalid(ArtifactAcceptanceError):
    status_code = 400
    code = "acceptance_key_invalid"


class AcceptancePayloadConflict(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_payload_conflict"


class AcceptanceNotFound(ArtifactAcceptanceError):
    status_code = 404
    code = "acceptance_not_found"


class AcceptanceSourceNotTerminal(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_source_not_terminal"


class AcceptanceSourceNotEligible(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_source_not_eligible"


class AcceptanceArtifactMismatch(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_artifact_mismatch"


class AcceptanceAlreadyAvailable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_already_available"


class AcceptanceNotRevocable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_not_revocable"


class AcceptanceStoreUnavailable(ArtifactAcceptanceError):
    status_code = 503
    code = "acceptance_store_unavailable"


class AcceptanceNotAvailable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_not_available"


class AcceptanceExpired(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_expired"


class AcceptanceArtifactIntegrityMismatch(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_artifact_integrity_mismatch"
```

Reuse `validate_idempotency_key_headers()` and `hash_idempotency_key()` internally, mapping their error classes to acceptance-specific codes. Canonicalize with sorted compact JSON and SHA-256; include the reviewer principal and strict validated request, never raw credentials or the raw key.

The internal consume path uses `AcceptanceNotFound` for unknown/cross-tenant records, `AcceptanceExpired` after database-time reconciliation proves expiry, `AcceptanceNotAvailable` for consumed/revoked/rejected/non-available records, and `AcceptanceArtifactIntegrityMismatch` for changed/missing/moved/empty/symlink-invalid stored bytes. These are service-level typed errors only; W1-22 still exposes no HTTP consume route.

- [x] **Step 5: Implement service orchestration**

Implement `ArtifactAcceptanceService` with this exact public surface:

- `__init__(self, repository: AcceptanceRecordRepository | None = None, submission_repository: SubmissionIdempotencyRepository | None = None, *, output_dir: Path | None = None) -> None`;
- `create(self, *, auth: AuthContext, raw_key: str, request: AcceptanceCreateRequest) -> tuple[AcceptanceRecordResponse, bool]`;
- `read(self, *, auth: AuthContext, acceptance_id: str) -> AcceptanceRecordResponse`;
- `revoke(self, *, auth: AuthContext, acceptance_id: str) -> AcceptanceRecordResponse`;
- `consume_for_publish(self, *, tenant_id: str, acceptance_id: str, consumer_operation: str, consumer_resource_id: str) -> AcceptanceRecordResponse`.

Order `create` exactly: validate reviewer identity → fingerprint → tenant/key replay lookup → tenant source lookup → source eligibility → exact artifact resolve/hash → repository create/replay → safe projection. Replays skip source/file access. `consume_for_publish` tenant-loads the stored record, re-resolves stored path, compares digest and size, then invokes atomic repository consume. It has no HTTP route.

- [x] **Step 6: Run service GREEN and no-provider assertions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_artifact_acceptance_service.py \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_acceptance_record_repository.py -q
.venv/bin/python -m ruff check \
  src/services/artifact_acceptance.py \
  tests/test_artifact_acceptance_service.py
```

Expected: all service/storage/identity tests pass; fake provider/translator/connector sentinels remain at zero calls.

- [x] **Step 7: Inspect Task 4 diff without staging or committing**

Run `git diff --check` and inspect the service plus its tests.

---

### Task 5: Authenticated Create/Read/Revoke HTTP API

**Files:**

- Create: `src/routers/acceptance_records.py`
- Create: `tests/test_acceptance_records_router.py`
- Modify: `src/routers/_deps.py`
- Modify: `src/api.py`
- Modify: `tests/test_auth_context.py`
- Modify: `tests/test_scenario_generation_safety_policy.py`

**Interfaces:**

- Produces `POST /acceptance-records`, `GET /acceptance-records/{acceptance_id}`, and `POST /acceptance-records/{acceptance_id}/revoke`.
- Does not produce `/consume` and does not modify distribution routes.

- [x] **Step 1: Write RED auth and HTTP tests**

Use `httpx.AsyncClient`/ASGI transport and an injected fake service. Assert:

```python
@pytest.mark.asyncio
async def test_create_returns_201_and_replay_returns_200(client, auth_headers) -> None:
    key = "acceptance-action-key-0001"
    first = await client.post(
        "/acceptance-records",
        headers={**auth_headers, "Idempotency-Key": key},
        json=_valid_request(),
    )
    replay = await client.post(
        "/acceptance-records",
        headers={**auth_headers, "Idempotency-Key": key},
        json=_valid_request(),
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["acceptance_id"] == replay.json()["acceptance_id"]
    assert replay.json()["idempotent_replay"] is True
```

Cover missing/invalid/duplicate key, `provider:submit`-only `403`, safe 422 with a credential-shaped extra field and no `input`, tenant read/revoke `404`, revoke replay, store `503`, response wrapper, and `GET/POST /consume` returning `404/405` without calling the service.

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_acceptance_records_router.py \
  tests/test_auth_context.py \
  tests/test_scenario_generation_safety_policy.py -q
```

Expected: route/permission tests fail because `artifact:accept` and router mounting are absent.

- [x] **Step 3: Recognize the new permission without rewriting keys**

Change only the recognized set:

```python
_RECOGNIZED_TENANT_PERMISSIONS = frozenset(
    {"all", "provider:submit", "artifact:accept"}
)
```

Add normalization tests for `artifact:accept`, duplicates, and mixed unknown permissions. Do not migrate existing JSON permission values or change their fail-closed empty default.

- [x] **Step 4: Implement raw-body-safe router**

Create the router with `response_model=AcceptanceRecordResponse`, explicit `Idempotency-Key` OpenAPI header, and these adapters:

```python
async def _parse_acceptance_request(request: Request) -> AcceptanceCreateRequest:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=[{"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON"}],
        ) from None
    try:
        return AcceptanceCreateRequest.model_validate(payload)
    except ValidationError as exc:
        safe_errors = [
            {
                "type": str(item.get("type") or "value_error"),
                "loc": list(item.get("loc") or ("body",)),
                "msg": str(item.get("msg") or "Invalid request"),
            }
            for item in exc.errors(include_url=False, include_context=False)
        ]
        raise HTTPException(status_code=422, detail=safe_errors) from None


@router.post("/acceptance-records", response_model=AcceptanceRecordResponse)
async def create_acceptance_record(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        raw_key = extract_acceptance_key(request)
        body = await _parse_acceptance_request(request)
        record, replay = await get_artifact_acceptance_service().create(
            auth=auth, raw_key=raw_key, request=body
        )
        response.status_code = 200 if replay else 201
        return record
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.get("/acceptance-records/{acceptance_id}", response_model=AcceptanceRecordResponse)
async def read_acceptance_record(
    acceptance_id: str,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        return await get_artifact_acceptance_service().read(
            auth=auth, acceptance_id=acceptance_id
        )
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.post("/acceptance-records/{acceptance_id}/revoke", response_model=AcceptanceRecordResponse)
async def revoke_acceptance_record(
    acceptance_id: str,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        return await get_artifact_acceptance_service().revoke(
            auth=auth, acceptance_id=acceptance_id
        )
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
```

Mount the router in `src/api.py` with the same outer `verify_api_key` convention as other domain routers. Do not add another CORS header because `Idempotency-Key` is already allowed.

- [x] **Step 5: Run HTTP GREEN and route regression**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_acceptance_records_router.py \
  tests/test_auth_context.py \
  tests/test_scenario_generation_safety_policy.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_submit_idempotency_router.py -q
.venv/bin/python -m ruff check \
  src/routers/acceptance_records.py src/routers/_deps.py src/api.py \
  tests/test_acceptance_records_router.py tests/test_auth_context.py
```

Expected: focused API/auth suites pass; canonical submit behavior is unchanged.

- [x] **Step 6: Inspect Task 5 diff without staging or committing**

Run `git diff --check` and inspect router/auth/app/test files. Confirm no distribution connector file changed.

---

### Task 6: Recovery Governance, OpenAPI, and Operator Documentation

**Files:**

- Modify: `scripts/pg_dump_logical.py`
- Modify: `scripts/pg_restore_logical.py`
- Modify: `scripts/verify_restored_database.py`
- Modify: `tests/test_backup_production_contract.py`
- Modify: `tests/test_run_alembic_upgrade.py`
- Modify: `configs/backend-route-auth-contract.yaml`
- Modify: `docs/runbooks/backend-route-auth-contract.md`
- Modify: `docs/reference/api-endpoints.md`
- Create: `docs/runbooks/artifact-acceptance-lifecycle.md`
- Modify: `docs/runbooks/README.md`
- Generate: `web/src/types/api.generated.ts`

**Interfaces:**

- Produces the 14-table logical recovery contract.
- Produces local OpenAPI TypeScript definitions for create/read/revoke.
- Produces an operator runbook that does not imply publish integration or production acceptance.

- [x] **Step 1: Write RED recovery/auth/OpenAPI assertions**

Update tests first to require `acceptance_records` in every dump/restore/verify/schema fixture and require `artifact:accept` plus the three routes in the auth contract. Add assertions that the route contract has no public consume endpoint and that distribution still remains W1-23 pending.

- [x] **Step 2: Run RED governance tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_backup_production_contract.py \
  tests/test_run_alembic_upgrade.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_openapi_types_drift_guard.py -q
```

Expected: failures name the missing 14th table, route contract, runbook, or stale generated types.

- [x] **Step 3: Update the 14-table backup/restore contract**

Append `acceptance_records` after `idempotency_records` in all three scripts and hermetic fixture lists. Keep order identical. Update assertions from 13 to 14 only where they describe the current post-W1-22 schema; do not rewrite historical evidence prose.

- [x] **Step 4: Regenerate and verify OpenAPI types**

Run:

```bash
cd web
npm run typegen:api
npm run check:api-types
```

Expected: generated types include acceptance request/response models and three routes; drift check exits `0`.

- [x] **Step 5: Write operator and reference documentation**

The runbook must include:

- eligible final path and reviewer permission prerequisites;
- create/replay/conflict/read/revoke status codes;
- expiry and changed-file integrity behavior;
- single-use internal consume semantics;
- rejection revokes an older available record;
- no UI and no public consume endpoint;
- explicit `production unchanged`, `provider_call=false` local evidence boundary;
- W1-23 still required before any publish route can trust the record.

Update API reference and auth contract with the exact same names/codes. Add the runbook to `docs/runbooks/README.md`.

- [x] **Step 6: Run governance GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_backup_production_contract.py \
  tests/test_run_alembic_upgrade.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_openapi_types_drift_guard.py -q
cd web && npm run check:api-types
```

Expected: all governance/drift checks pass.

- [x] **Step 7: Inspect Task 6 diff without staging or committing**

Run `git diff --check` and inspect scripts, contracts, docs, and generated types. Confirm generated output came only from the project command.

---

### Task 7: Disposable PostgreSQL 18, Full Regression, Independent Review, and State Sync

**Files:**

- Modify after verification: `docs/runbooks/artifact-acceptance-lifecycle.md`
- Modify after verification: `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- Modify only after durable fact is verified: `AGENTS.md`

**Interfaces:**

- Consumes all prior task outputs.
- Produces fresh local evidence and the `completed_local` verdict only if every gate passes.
- Leaves W1-23/W1-24/W1-25/W5 and all production actions explicitly pending.

- [x] **Step 1: Run the complete focused acceptance suite**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_artifact_acceptance_contracts.py \
  tests/test_acceptance_record_repository.py \
  tests/test_artifact_acceptance_service.py \
  tests/test_acceptance_records_router.py \
  tests/test_auth_context.py \
  tests/test_p0_media_tenant_security.py \
  tests/test_submit_idempotency_router.py \
  tests/test_backup_production_contract.py \
  tests/test_run_alembic_upgrade.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_openapi_types_drift_guard.py -q
```

Expected: zero failures/skips caused by W1-22; exact counts are recorded from fresh output rather than predicted.

- [x] **Step 2: Verify disposable PostgreSQL 18 upgrade, schema, concurrency, downgrade, and fresh init**

Use an isolated Docker PostgreSQL 18 database with no production DSN. Execute:

1. migrate from `d5e6f7a8b9c0` to `e8f1a2b3c4d5`;
2. inspect columns, checks, unique/partial indexes, and single Alembic head;
3. run concurrent same-key create, accepted/rejected ordering, and 20-way consume with exactly one winner;
4. downgrade to `d5e6f7a8b9c0` and verify table removal;
5. re-upgrade and compare against `001_init.sql` fresh bootstrap.

Store only sanitized counts/schema metadata in the report. Do not print DSNs or credentials.

- [x] **Step 3: Run full backend quality gate**

Run:

```bash
make ci
```

Expected: Ruff exits `0`; pytest exits `0`. Record exact passed/skipped/deselected counts and warnings.

- [x] **Step 4: Run complete frontend quality gate**

Run:

```bash
cd web
npm test -- --run
npm run lint
npx tsc --noEmit
npm run check:api-types
npm run build
```

Expected: Vitest, ESLint, TypeScript, drift check, and Next production build exit `0`.

- [x] **Step 5: Run repository hygiene and secret-safe review**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Then inspect the complete changed/untracked W1-22 manifest and run the project secret-pattern scan without reading `.env`. Confirm no raw action key, API key, token, password, private key, production DSN, or host absolute artifact path appears in implementation/log/doc outputs.

- [x] **Step 6: Request independent spec and security review**

Provide the approved spec, implementation plan, complete W1-22 diff, and fresh focused evidence to an independent reviewer. Require classification as Critical/Important/Minor. Resolve every accepted Critical or Important finding with a new RED/GREEN cycle and rerun all affected gates. Reviewer output is not accepted without local diff/test verification.

- [x] **Step 7: Synchronize state only from verified evidence**

If all gates pass:

- mark W1-22 `completed_local` in the roadmap;
- update the tracked roadmap and acceptance lifecycle runbook with exact commands/results and residual boundaries;
- add one concise durable W1-22 local-closure fact to `AGENTS.md`;
- state explicitly that distribution still trusts the old body until W1-23 and that production has not been migrated/deployed.

If any required gate remains unavailable or failing, keep W1-22 `in_progress` and list the exact blocker instead of upgrading the verdict.

- [x] **Step 8: Final verification after documentation synchronization**

Rerun the focused documentation/governance tests, `make ci` if code changed during review, frontend drift/build if generated types changed, `git diff --check`, and the secret scan. The final report may claim only the last complete fresh run.

## Completion Handoff

When Task 7 is green, report:

- actual files changed;
- exact focused/full/PG18/frontend evidence;
- independent review disposition;
- `completed_local` or precise incomplete state;
- `production unchanged`, `provider_call=false`;
- W1-23 publish consumption as the next separately approved roadmap item.

Do not stage, commit, push, create a PR, migrate production, deploy, call providers, publish, or deliver in this handoff.
