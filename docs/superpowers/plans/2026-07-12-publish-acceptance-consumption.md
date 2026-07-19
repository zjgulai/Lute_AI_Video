# W1-23 Publish Acceptance Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox **- [ ]** syntax for tracking.

**Goal:** Make one server-side W1-22 acceptance record authorize at most one tenant-bound, single-platform publish connector invocation through both existing publish routes, with durable attempt truth and zero automatic retry.

**Architecture:** Strict Pydantic contracts and artifact:publish permission protect both HTTP adapters. A specialized PostgreSQL/SQLite PublishAttemptRepository records prepared, consumed, and terminal states; ArtifactAcceptanceService remains the only consume authority and gains a read-only uncertain-outcome inspector. One PublishAttemptService owns readiness, consume, exact artifact resolution, connector call ordering, safe response projection, and typed failure semantics.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, asyncpg, SQLite, Alembic, PostgreSQL 18, pytest/pytest-asyncio, Ruff, Next.js 16, TypeScript, Vitest, OpenAPI TypeScript.

---

## Global Constraints

- Approved specification: docs/superpowers/specs/2026-07-12-publish-acceptance-consumption-design.md.
- Roadmap scope is W1-23 only. W1-24/W1-25 connector-internal credential/receipt truth, W5 acceptance UI, immutable attempt snapshots, W1-26 live publish, delivery, and metrics remain separate.
- One acceptance authorizes one exact platform and one external connector invocation attempt. No batch, platform loop, automatic retry, resume worker, or HTTP consume endpoint.
- Publishing requires artifact:publish or all. artifact:accept-only and provider:submit-only credentials are denied before parsing or side effects.
- Tenant, attempt identity, source identity, artifact path/hash/size, consume state, and terminal truth are server-owned.
- Client video paths, URLs, digest/size, reviewer/human assertions, delivery flags, publish flags, tenant/scenario, and unknown fields are rejected.
- Production persistence requires verified PostgreSQL and the W1-23 publish_logs columns. SQLite is development/test only.
- Preserve the existing dirty Wave 1A/W1-22 worktree. Do not reset, reformat unrelated files, stage, commit, push, open a PR, or switch branches.
- The Superpowers plan template normally recommends frequent commits, but project authorization explicitly forbids them here. Each task ends with a diff checkpoint; version-control actions require a later user instruction.
- Do not read .env or DDDD.pem. Do not print or persist API keys, connector credentials, raw request bodies, connector error text, host absolute paths, or production DSNs.
- Add no dependency. Generate API types only with cd web && npm run typegen:api.
- Every behavior change follows RED → confirm the expected failure → minimal GREEN → focused regression → Ruff/diff checkpoint.
- Local evidence ceiling is L2 fixture/disposable database/build and completed_local. production unchanged, provider_call=false, live_publish=false, and no production database write.

## File Structure

### Create

- src/models/publish_attempt.py — strict request/metadata/success/error models and bounded safe projection helpers.
- src/storage/publish_attempt_repository.py — tenant-bound PostgreSQL/SQLite prepared/CAS/terminal attempt ledger.
- src/services/publish_attempt.py — readiness, W1-22 consume, artifact resolution, connector call, and error orchestration.
- migrations/alembic/versions/f9a2b3c4d5e6_add_publish_acceptance_fields.py — additive publish_logs columns and indexes.
- tests/test_publish_attempt_contracts.py — strict models, permission vocabulary, metadata safety, and response projection.
- tests/test_publish_attempt_repository.py — migration, SQLite lifecycle, fake-PostgreSQL SQL, CAS, and fail-closed contracts.
- tests/test_publish_acceptance_outcome.py — W1-22 uncertain consume result inspection.
- tests/test_publish_attempt_service.py — call order, exact payload, concurrency, failure, crash-window, and no-retry behavior.
- tests/test_publish_connector_log_safety.py — publish-path path/error/response/exception log sanitization without network.
- tests/test_publish_acceptance_routes.py — authenticated canonical/deprecated route, safe 422, tenant, error, header, and OpenAPI contracts.
- tests/test_publish_attempt_pg18.py — explicit disposable-PostgreSQL schema, CAS, and concurrency evidence; skipped outside its exact local gate.
- web/src/components/apiPublishAcceptance.test.ts — frontend acceptance/platform/metadata zero-network guards and one-POST contract.
- docs/runbooks/publish-acceptance-consumption.md — operator state, ambiguity, rollback, and evidence boundary.
- docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md — durable final local status and evidence boundary, updated only after every mandatory gate passes.

### Modify

- src/routers/_deps.py — recognize artifact:publish.
- src/connectors/registry.py — no-network connector readiness projection.
- src/connectors/tiktok_connector.py — sanitize only publish-path failure logs/results; credential and receipt truth remain W1-24.
- src/connectors/shopify_connector.py — sanitize only publish-path failure logs/results; credential SSOT and receipt truth remain W1-25.
- src/services/artifact_acceptance.py — bounded internal consume-outcome inspection; no HTTP surface.
- src/api.py — attach deprecation headers to every controlled legacy publish response without changing the existing router auth mount.
- src/routers/distribution.py — replace body authority and file search with strict shared service adapters.
- src/storage/db.py — fresh/existing SQLite columns/indexes and PostgreSQL column readiness.
- src/storage/migrations/001_init.sql — fresh/reused PostgreSQL publish_logs parity.
- tests/test_auth_context.py — exact new permission normalization.
- tests/test_scenario_generation_safety_policy.py — mixed-known/unknown permission fail-closed regression.
- tests/test_distribution_publish_guard.py — replace unsafe human-body expectations with W1-23 fail-closed regression.
- tests/test_publish_e2e.py — harden live route execution behind exact W1-26 authorization and stop printing bodies.
- tests/test_metrics_poller.py — preserve publish_logs as informational, not active metrics source.
- tests/test_backup_production_contract.py — unchanged 14-table order plus W1-23 publish_logs column recovery contract.
- tests/test_run_alembic_upgrade.py — new head/rollback wording remains dynamic and fail-closed.
- tests/test_backend_route_auth_contract.py — exact artifact:publish route contract and no public consume.
- tests/test_openapi_types_drift_guard.py — unchanged local-only generated-schema governance.
- web/src/components/api.ts — strict publish helpers and acceptance-aware options.
- web/src/types/api.generated.ts — generated output only.
- configs/backend-route-auth-contract.yaml — completed W1-23 publish permission/body/route truth.
- docs/runbooks/backend-route-auth-contract.md — publisher/reviewer/generator separation.
- docs/runbooks/artifact-acceptance-lifecycle.md — internal consume outcome and publish-attempt correlation.
- docs/reference/api-endpoints.md — canonical/deprecated request, response, and error contract.
- docs/runbooks/README.md — new operator runbook index.
- docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md — completed_local only after final evidence.
- docs/runbooks/publish-acceptance-consumption.md and AGENTS.md — state synchronized only from verified results.
- AGENTS.md — concise W1-23 local fact only after final acceptance.

---

### Task 1: Strict Publish Contracts and Permission Vocabulary

**Files:**

- Create: src/models/publish_attempt.py
- Create: tests/test_publish_attempt_contracts.py
- Modify: src/routers/_deps.py
- Modify: tests/test_auth_context.py
- Modify: tests/test_scenario_generation_safety_policy.py

**Interfaces:**

- Produces PublishMetadata, PublishAttemptRequest, PublishAttemptResponse, PublishAttemptErrorDetail, and PublishAttemptErrorResponse.
- Produces exact platform/status aliases and safe UUID/post-result validators used by service, routes, OpenAPI, and frontend type generation.
- Adds artifact:publish without changing all, artifact:accept, or provider:submit behavior.

- [x] **Step 1: Write RED tests for the strict canonical request**

Create tests/test_publish_attempt_contracts.py with the following first contract:

~~~python
from __future__ import annotations

import pytest
from pydantic import ValidationError


VALID_ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"


def _valid_request() -> dict[str, object]:
    return {
        "acceptance_id": VALID_ACCEPTANCE_ID,
        "platform": "tiktok",
        "metadata": {
            "title": "Reviewed campaign video",
            "description": "Final approved creative.",
            "hashtags": ["momlife", "wearablepump"],
            "product_name": "Wearable Breast Pump",
        },
    }


def test_publish_request_is_strict_and_single_platform() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    parsed = PublishAttemptRequest.model_validate(_valid_request())
    assert parsed.platform == "tiktok"
    assert parsed.acceptance_id == VALID_ACCEPTANCE_ID

    for value in ("TIKTOK", "instagram", ["tiktok"], 1):
        with pytest.raises(ValidationError):
            PublishAttemptRequest.model_validate(
                {**_valid_request(), "platform": value}
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platforms", ["tiktok"]),
        ("content", {"title": "legacy"}),
        ("video_path", "/tmp/client.mp4"),
        ("video_url", "https://client.invalid/video.mp4"),
        ("delivery_acceptance", {"source": "human"}),
        ("tenant_id", "attacker"),
        ("reviewer", "self-asserted"),
        ("publish_allowed", True),
    ],
)
def test_publish_request_forbids_legacy_and_server_authority_fields(
    field: str,
    value: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate({**_valid_request(), field: value})
~~~

- [x] **Step 2: Add RED metadata and safe-result tests**

Append exact boundary tests:

~~~python
@pytest.mark.parametrize(
    "metadata",
    [
        {"title": 42},
        {"description": True},
        {"hashtags": "momlife"},
        {"hashtags": ["#momlife"]},
        {"hashtags": ["momlife", "momlife"]},
        {"tags": ["ok", "bad\x00tag"]},
        {"video_path": "/tmp/client.mp4"},
        {"thumbnail_url": "https://client.invalid/thumb.jpg"},
        {"title": "x" * 301},
        {"description": "x" * 5001},
        {"hashtags": [f"tag-{index}" for index in range(31)]},
    ],
)
def test_publish_metadata_rejects_unsafe_or_unbounded_values(
    metadata: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "metadata": metadata}
        )


@pytest.mark.parametrize(
    "acceptance_id",
    [
        "not-a-uuid",
        "7F947625-2898-4E9E-9E71-DCE4309E5F4F",
        "7f947625-2898-1e9e-9e71-dce4309e5f4f",
        True,
        123,
    ],
)
def test_acceptance_id_is_a_strict_lowercase_uuid4(
    acceptance_id: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "acceptance_id": acceptance_id}
        )


def test_success_projection_rejects_credential_shaped_or_unsafe_urls() -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    valid = {
        "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
        "acceptance_id": VALID_ACCEPTANCE_ID,
        "platform": "tiktok",
        "status": "published",
        "success": True,
        "post_id": "fixture-post-1",
        "post_url": "https://example.invalid/posts/fixture-post-1",
        "acceptance_consumed": True,
        "retry_allowed": False,
    }
    assert PublishAttemptResponse.model_validate(valid).status == "published"

    for url in (
        "ftp://example.invalid/post",
        "https://user:secret@example.invalid/post",
        "https://example.invalid/post?token=secret",
        "https://example.invalid/post#secret",
    ):
        with pytest.raises(ValidationError):
            PublishAttemptResponse.model_validate({**valid, "post_url": url})


def test_error_projection_rejects_unknown_code_and_malformed_attempt_id() -> None:
    from src.models.publish_attempt import PublishAttemptErrorDetail

    valid = {
        "code": "publish_connector_failed",
        "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
        "acceptance_consumed": True,
        "retry_allowed": False,
    }
    assert PublishAttemptErrorDetail.model_validate(valid).retry_allowed is False
    for invalid in (
        {**valid, "code": "raw_connector_exception"},
        {**valid, "publish_attempt_id": "/host/path"},
    ):
        with pytest.raises(ValidationError):
            PublishAttemptErrorDetail.model_validate(invalid)
~~~

- [x] **Step 3: Write RED permission normalization tests**

Add artifact:publish cases to tests/test_auth_context.py and tests/test_scenario_generation_safety_policy.py:

~~~python
@pytest.mark.parametrize(
    "raw",
    [
        ["artifact:publish"],
        ["artifact:publish", "artifact:publish"],
        '["artifact:publish"]',
    ],
)
def test_publish_permission_is_recognized(raw: object) -> None:
    from src.routers._deps import _normalize_permissions

    assert _normalize_permissions(raw) == frozenset({"artifact:publish"})


@pytest.mark.parametrize(
    "raw",
    [
        ["artifact:publish", "unknown:permission"],
        ["artifact:publish", ""],
        ["provider:submit", "artifact:publish", "unknown:permission"],
    ],
)
def test_publish_permission_mixed_with_invalid_input_fails_closed(
    raw: object,
) -> None:
    from src.routers._deps import _normalize_permissions

    assert _normalize_permissions(raw) == frozenset()
~~~

- [x] **Step 4: Run RED and confirm only W1-23 gaps fail**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_contracts.py tests/test_auth_context.py tests/test_scenario_generation_safety_policy.py -q
~~~

Expected: collection or assertions fail because src.models.publish_attempt and artifact:publish recognition do not exist; existing all/provider/accept behavior remains green.

- [x] **Step 5: Implement strict Pydantic models**

Create src/models/publish_attempt.py with these exact public contracts and validators:

~~~python
from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PublishPlatform = Literal["tiktok", "shopify"]
PublishAttemptStatus = Literal[
    "prepared",
    "authorization_failed",
    "acceptance_consumed",
    "published",
    "failed",
    "ambiguous",
]
PublishAttemptErrorCode = Literal[
    "publish_connector_not_ready",
    "publish_attempt_store_unavailable",
    "acceptance_not_found",
    "acceptance_expired",
    "acceptance_not_available",
    "acceptance_artifact_integrity_mismatch",
    "acceptance_store_unavailable",
    "publish_artifact_unavailable_after_consume",
    "publish_attempt_state_unknown",
    "publish_connector_failed",
    "publish_outcome_ambiguous",
]

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_METADATA_LIMIT_BYTES = 16 * 1024


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class PublishMetadata(_StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    hook: str | None = Field(default=None, min_length=1, max_length=1000)
    product_name: str | None = Field(default=None, min_length=1, max_length=300)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("title", "description", "hook", "product_name")
    @classmethod
    def reject_control_text(cls, value: str | None) -> str | None:
        if value is not None and _CONTROL_RE.search(value):
            raise ValueError("metadata text contains control characters")
        return value

    @field_validator("hashtags", "tags")
    @classmethod
    def validate_tag_list(cls, values: list[str]) -> list[str]:
        if any(
            not value
            or len(value) > 100
            or value.startswith("#")
            or _CONTROL_RE.search(value)
            for value in values
        ):
            raise ValueError("tag values are invalid")
        if len(set(values)) != len(values):
            raise ValueError("tag values must be unique")
        return values

    @model_validator(mode="after")
    def enforce_serialized_size(self) -> "PublishMetadata":
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > _METADATA_LIMIT_BYTES:
            raise ValueError("metadata exceeds 16 KiB")
        return self


class PublishAttemptRequest(_StrictModel):
    acceptance_id: str
    platform: PublishPlatform
    metadata: PublishMetadata

    @field_validator("acceptance_id")
    @classmethod
    def validate_acceptance_id(cls, value: str) -> str:
        if _UUID4_RE.fullmatch(value) is None:
            raise ValueError("acceptance_id is invalid")
        return value


class PublishAttemptResponse(_StrictModel):
    publish_attempt_id: str
    acceptance_id: str
    platform: PublishPlatform
    status: Literal["published"]
    success: Literal[True]
    post_id: str | None = Field(default=None, max_length=256)
    post_url: str | None = Field(default=None, max_length=2048)
    acceptance_consumed: Literal[True]
    retry_allowed: Literal[False]

    @field_validator("publish_attempt_id", "acceptance_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if _UUID4_RE.fullmatch(value) is None:
            raise ValueError("identifier is invalid")
        return value

    @field_validator("post_id")
    @classmethod
    def validate_post_id(cls, value: str | None) -> str | None:
        if value is not None and (_CONTROL_RE.search(value) or not value):
            raise ValueError("post_id is invalid")
        return value

    @field_validator("post_url")
    @classmethod
    def validate_post_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("post_url is invalid")
        return value


class PublishAttemptErrorDetail(_StrictModel):
    code: PublishAttemptErrorCode
    publish_attempt_id: str | None = None
    acceptance_consumed: bool | None
    retry_allowed: bool

    @field_validator("publish_attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str | None) -> str | None:
        if value is not None and _UUID4_RE.fullmatch(value) is None:
            raise ValueError("publish_attempt_id is invalid")
        return value


class PublishAttemptErrorResponse(_StrictModel):
    detail: PublishAttemptErrorDetail
~~~

- [x] **Step 6: Recognize artifact:publish**

Change the recognized permission set in src/routers/_deps.py to:

~~~python
_RECOGNIZED_TENANT_PERMISSIONS = frozenset(
    {"all", "provider:submit", "artifact:accept", "artifact:publish"}
)
~~~

Do not change AuthContext.has_permission; all must continue to authorize through the existing super-permission rule.

- [x] **Step 7: Run GREEN, Ruff, and a no-coercion schema check**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_contracts.py tests/test_auth_context.py tests/test_scenario_generation_safety_policy.py -q
.venv/bin/python -m ruff check src/models/publish_attempt.py src/routers/_deps.py tests/test_publish_attempt_contracts.py tests/test_auth_context.py tests/test_scenario_generation_safety_policy.py
~~~

Expected: all focused tests pass and Ruff exits 0. Inspect PublishAttemptRequest.model_json_schema(mode="validation") and confirm additionalProperties=false, exact platform enum, and metadata required.

- [x] **Step 8: Inspect the Task 1 diff**

Run git diff --check and inspect only the Task 1 files. Confirm there is no route, connector, schema, generated type, or external-call change yet.

---

### Task 2: Additive Schema and Atomic Publish Attempt Repository

**Files:**

- Create: migrations/alembic/versions/f9a2b3c4d5e6_add_publish_acceptance_fields.py
- Create: src/storage/publish_attempt_repository.py
- Create: tests/test_publish_attempt_repository.py
- Modify: src/storage/db.py
- Modify: src/storage/migrations/001_init.sql
- Modify: tests/test_backup_production_contract.py
- Modify: tests/test_metrics_poller.py

**Interfaces:**

- Reuses publish_logs.id as the server UUID publish_attempt_id.
- Adds nullable tenant_id, acceptance_id, and updated_at for legacy compatibility.
- Produces create_prepared(), get_by_id(), and transition() with tenant-bound CAS.
- Preserves publish_logs as informational for metrics; it does not become an active metrics source.

- [x] **Step 1: Write RED migration and SQLite parity tests**

Create tests/test_publish_attempt_repository.py with schema checks:

~~~python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.storage import db as db_module


@pytest.fixture
def sqlite_publish_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(tmp_path / "publish-attempts.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def test_sqlite_publish_logs_has_attempt_columns_and_indexes(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in sqlite_publish_db.execute(
            "PRAGMA table_info(publish_logs)"
        ).fetchall()
    }
    assert {"tenant_id", "acceptance_id", "updated_at"} <= columns

    indexes = {
        row["name"]
        for row in sqlite_publish_db.execute(
            "PRAGMA index_list(publish_logs)"
        ).fetchall()
    }
    assert "idx_publish_logs_tenant_created_at" in indexes
    assert "idx_publish_logs_tenant_acceptance" in indexes
~~~

Add a compatibility case that creates the actual pre-W1-23 SQLite publish_logs shape manually with its existing nullable tenant_id, calls _create_sqlite_tables(), and verifies acceptance_id, updated_at, and both indexes are added without changing the tenant_id or any legacy row value. Keep a second older-shape assertion for a table missing tenant_id so the pre-existing compatibility path remains covered.

- [x] **Step 2: Write RED repository lifecycle and CAS tests**

Append:

~~~python
@pytest.mark.asyncio
async def test_repository_enforces_one_way_tenant_bound_lifecycle(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id="tenant-alpha",
        acceptance_id="7f947625-2898-4e9e-9e71-dce4309e5f4f",
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    attempt_id = prepared["id"]
    assert prepared["status"] == "prepared"
    assert prepared["content"]["route_kind"] == "canonical"
    assert "artifact" not in prepared["content"]

    consumed_content = {
        "schema_version": "publish-attempt.v1",
        "route_kind": "canonical",
        "source": {
            "resource_type": "scenario",
            "resource_id": "s2_fixture",
            "scenario": "s2",
        },
        "artifact": {
            "path": (
                "tenants/tenant-alpha/pending_review/"
                "s2_fixture/assemble/final.mp4"
            ),
            "sha256": "a" * 64,
            "size_bytes": 20,
            "kind": "video",
        },
        "metadata": {"title": "Reviewed campaign"},
    }
    consumed = await repository.transition(
        tenant_id="tenant-alpha",
        attempt_id=attempt_id,
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=consumed_content,
    )
    assert consumed is not None
    assert consumed["status"] == "acceptance_consumed"

    published = await repository.transition(
        tenant_id="tenant-alpha",
        attempt_id=attempt_id,
        expected_status="acceptance_consumed",
        new_status="published",
        post_id="post-fixture",
        url="https://example.invalid/posts/post-fixture",
    )
    assert published is not None
    assert published["status"] == "published"

    assert await repository.transition(
        tenant_id="tenant-alpha",
        attempt_id=attempt_id,
        expected_status="acceptance_consumed",
        new_status="failed",
        error_code="publish_connector_failed",
    ) is None
    assert await repository.get_by_id(
        tenant_id="tenant-beta",
        attempt_id=attempt_id,
    ) is None
~~~

Add parameterized tests for every legal transition and reject every illegal edge:

~~~python
LEGAL_TRANSITIONS = {
    ("prepared", "authorization_failed"),
    ("prepared", "acceptance_consumed"),
    ("acceptance_consumed", "published"),
    ("acceptance_consumed", "failed"),
    ("acceptance_consumed", "ambiguous"),
}
~~~

Add tests that reject raw exceptions, absolute host paths, non-canonical JSON, unknown states, wrong platforms, malformed UUIDs, and content above the repository safety bound. Assert error stores only the stable code.

- [x] **Step 3: Write RED production fail-closed and PostgreSQL SQL tests**

Use a fake verified pool/connection to record SQL and assert:

~~~python
@pytest.mark.asyncio
async def test_production_repository_requires_verified_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: None)
    repository = PublishAttemptRepository(require_postgres=True)

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.create_prepared(
            tenant_id="tenant-alpha",
            acceptance_id="7f947625-2898-4e9e-9e71-dce4309e5f4f",
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )
~~~

The SQL recorder must prove:

- INSERT casts id to UUID and content to JSONB;
- every SELECT/UPDATE includes tenant_id and attempt id;
- transition WHERE includes the exact expected status;
- updated_at uses database time;
- a zero-row RETURNING result becomes None, not a blind success;
- driver/schema exceptions become PublishAttemptStoreUnavailable.

- [x] **Step 4: Run RED**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_repository.py tests/test_backup_production_contract.py tests/test_metrics_poller.py -q
~~~

Expected: new schema/repository assertions fail because the migration, compatibility columns, indexes, and repository do not exist.

- [x] **Step 5: Add the reversible Alembic revision**

Create migrations/alembic/versions/f9a2b3c4d5e6_add_publish_acceptance_fields.py:

~~~python
"""Add W1-23 publish acceptance correlation fields.

Revision ID: f9a2b3c4d5e6
Revises: e8f1a2b3c4d5
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9a2b3c4d5e6"
down_revision: str | None = "e8f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publish_logs",
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "publish_logs",
        sa.Column("acceptance_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "publish_logs",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX idx_publish_logs_tenant_created_at
            ON publish_logs(tenant_id, created_at DESC)
        """
    )
    op.create_index(
        "idx_publish_logs_tenant_acceptance",
        "publish_logs",
        ["tenant_id", "acceptance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_publish_logs_tenant_acceptance",
        table_name="publish_logs",
    )
    op.drop_index(
        "idx_publish_logs_tenant_created_at",
        table_name="publish_logs",
    )
    op.drop_column("publish_logs", "updated_at")
    op.drop_column("publish_logs", "acceptance_id")
    op.drop_column("publish_logs", "tenant_id")
~~~

Render the revision SQL during RED/GREEN and assert it produces exactly the approved two indexes and no table-wide status constraint.

- [x] **Step 6: Synchronize fresh and existing database schema paths**

Update src/storage/migrations/001_init.sql so publish_logs contains the three nullable fields and reused volumes receive them:

~~~sql
CREATE TABLE IF NOT EXISTS publish_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(32) NOT NULL,
    tenant_id VARCHAR(64),
    acceptance_id VARCHAR(36),
    post_id VARCHAR(128),
    content JSONB DEFAULT '{}',
    status VARCHAR(32),
    url TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);
ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS acceptance_id VARCHAR(36);
ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_created_at
    ON publish_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_acceptance
    ON publish_logs(tenant_id, acceptance_id);
~~~

Update the SQLite CREATE TABLE and compatibility tuple in src/storage/db.py:

~~~python
for table, column, column_type in (
    ("pipeline_states", "tenant_id", "TEXT"),
    ("video_metrics", "tenant_id", "TEXT"),
    ("publish_logs", "tenant_id", "TEXT"),
    ("publish_logs", "acceptance_id", "TEXT"),
    ("publish_logs", "updated_at", "TIMESTAMP"),
):
    rows = _sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        continue
    existing = {row["name"] for row in rows}
    if column not in existing:
        _sqlite_conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
        )
~~~

Add both SQLite indexes to the normal executescript.

Extend PostgreSQL readiness after the existing eight-table loop:

~~~python
_REQUIRED_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "publish_logs": frozenset({
        "tenant_id",
        "acceptance_id",
        "updated_at",
    }),
}


async def _verify_required_columns(conn: Any) -> bool:
    for table, required in _REQUIRED_TABLE_COLUMNS.items():
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = $1
            """,
            table,
        )
        present = {row["column_name"] for row in rows}
        missing = required - present
        if missing:
            logger.warning(
                "PG table has incomplete required schema: %s",
                table,
            )
            return False
    return True
~~~

Make _verify_pg_tables() return false unless both the existing table loop and `_verify_required_columns(conn)` pass. Add a fake-connection regression for each missing column and a complete-column GREEN case. Keep the 8-table application-readiness set unchanged; the separate backup/restore contract remains 14 ordered tables.

- [x] **Step 7: Implement the specialized repository**

Create src/storage/publish_attempt_repository.py with these exact constants and public methods:

~~~python
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from src.models.publish_attempt import PublishMetadata

from . import db

ALLOWED_PLATFORMS = frozenset({"tiktok", "shopify"})
ALLOWED_ROUTE_KINDS = frozenset({"canonical", "legacy_adapter"})
ALLOWED_STATUSES = frozenset({
    "prepared",
    "authorization_failed",
    "acceptance_consumed",
    "published",
    "failed",
    "ambiguous",
})
ALLOWED_ERROR_CODES = frozenset({
    "publish_connector_not_ready",
    "publish_attempt_store_unavailable",
    "acceptance_not_found",
    "acceptance_expired",
    "acceptance_not_available",
    "acceptance_artifact_integrity_mismatch",
    "acceptance_store_unavailable",
    "publish_artifact_unavailable_after_consume",
    "publish_attempt_state_unknown",
    "publish_connector_failed",
    "publish_outcome_ambiguous",
})
LEGAL_TRANSITIONS = frozenset({
    ("prepared", "authorization_failed"),
    ("prepared", "acceptance_consumed"),
    ("acceptance_consumed", "published"),
    ("acceptance_consumed", "failed"),
    ("acceptance_consumed", "ambiguous"),
})
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class PublishAttemptStoreUnavailable(RuntimeError):
    pass


class PublishAttemptRepository:
    def __init__(self, *, require_postgres: bool | None = None) -> None:
        if require_postgres is None:
            environment = os.getenv("ENVIRONMENT", "development").strip().lower()
            require_postgres = environment in {"prod", "production"}
        self.require_postgres = require_postgres

    async def create_prepared(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        platform: str,
        route_kind: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        attempt_id = str(uuid.uuid4())
        content = {
            "schema_version": "publish-attempt.v1",
            "route_kind": route_kind,
            "metadata": dict(metadata),
        }
        return await self._insert_prepared(
            attempt_id=attempt_id,
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
            platform=platform,
            content_json=self._encode_content(
                content,
                tenant_id=tenant_id,
            ),
        )

    async def get_by_id(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        return await self._fetch_one(
            pg_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = $1 AND id = $2::uuid"
            ),
            sqlite_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = ? AND id = ?"
            ),
            args=(tenant_id, attempt_id),
        )

    async def transition(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_status: str,
        new_status: str,
        content: Mapping[str, Any] | None = None,
        post_id: str | None = None,
        url: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any] | None:
        if (
            not isinstance(expected_status, str)
            or not isinstance(new_status, str)
            or (expected_status, new_status) not in LEGAL_TRANSITIONS
        ):
            raise ValueError("attempt transition is invalid")
        self._validate_transition_projection(
            new_status=new_status,
            post_id=post_id,
            url=url,
            error_code=error_code,
        )
        return await self._transition_backend(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_status=expected_status,
            new_status=new_status,
            content_json=(
                self._encode_content(content, tenant_id=tenant_id)
                if content is not None
                else None
            ),
            post_id=post_id,
            url=url,
            error_code=error_code,
        )
~~~

Define every private method referenced by the public API in the same file:

~~~python
async def _backend(self) -> tuple[Any | None, sqlite3.Connection | None]:
    if self.require_postgres:
        pool = db.get_verified_pg_pool()
        if pool is None:
            raise PublishAttemptStoreUnavailable
        return pool, None
    pool = await db.get_pool()
    if pool is not None and db.is_pg_available():
        return pool, None
    if db._sqlite_conn is None:
        db._init_sqlite()
    return None, db._sqlite_conn


@classmethod
def _encode_content(
    cls,
    content: Mapping[str, Any],
    *,
    tenant_id: str,
) -> str:
    try:
        normalized = cls._normalize_content_projection(
            content,
            tenant_id=tenant_id,
        )
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, ValidationError):
        raise ValueError("attempt content is invalid") from None
    if len(encoded.encode("utf-8")) > 32 * 1024:
        raise ValueError("attempt content exceeds 32 KiB")
    return encoded


@staticmethod
def _normalize_content_projection(
    content: Mapping[str, Any],
    *,
    tenant_id: str,
) -> dict[str, Any]:
    payload = dict(content)
    allowed_top = {
        "schema_version",
        "route_kind",
        "metadata",
        "source",
        "artifact",
    }
    if set(payload) - allowed_top:
        raise ValueError("attempt content has unknown fields")
    if payload.get("schema_version") != "publish-attempt.v1":
        raise ValueError("attempt schema version is invalid")
    route_kind = payload.get("route_kind")
    if not isinstance(route_kind, str) or route_kind not in ALLOWED_ROUTE_KINDS:
        raise ValueError("attempt route kind is invalid")
    metadata = PublishMetadata.model_validate(payload.get("metadata", {}))
    normalized: dict[str, Any] = {
        "schema_version": "publish-attempt.v1",
        "route_kind": route_kind,
        "metadata": metadata.model_dump(mode="json", exclude_none=True),
    }

    source = payload.get("source")
    artifact = payload.get("artifact")
    if (source is None) != (artifact is None):
        raise ValueError("source and artifact must be stored together")
    if source is None:
        return normalized
    if not isinstance(source, Mapping) or set(source) != {
        "resource_type",
        "resource_id",
        "scenario",
    }:
        raise ValueError("attempt source is invalid")
    resource_type = source.get("resource_type")
    resource_id = source.get("resource_id")
    scenario = source.get("scenario")
    if (
        resource_type not in {"fast", "scenario"}
        or not isinstance(resource_id, str)
        or _RESOURCE_ID_RE.fullmatch(resource_id) is None
        or not isinstance(scenario, str)
        or scenario not in {"fast", "s1", "s2", "s3", "s4", "s5"}
        or (resource_type == "fast") != (scenario == "fast")
    ):
        raise ValueError("attempt source is invalid")
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "path",
        "sha256",
        "size_bytes",
        "kind",
    }:
        raise ValueError("attempt artifact is invalid")
    artifact_path = artifact.get("path")
    artifact_sha256 = artifact.get("sha256")
    artifact_size = artifact.get("size_bytes")
    if not isinstance(artifact_path, str):
        raise ValueError("attempt artifact path is invalid")
    canonical_path = str(PurePosixPath(artifact_path))
    expected_prefix = (
        f"tenants/{tenant_id}/pending_review/fast_mode/{resource_id}/"
        if resource_type == "fast"
        else f"tenants/{tenant_id}/pending_review/{resource_id}/"
    )
    if (
        artifact_path != canonical_path
        or artifact_path.startswith("/")
        or "\\" in artifact_path
        or ".." in PurePosixPath(artifact_path).parts
        or not artifact_path.startswith(expected_prefix)
        or not artifact_path.endswith((".mp4", ".webm"))
        or not isinstance(artifact_sha256, str)
        or _SHA256_RE.fullmatch(artifact_sha256) is None
        or not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
        or artifact_size <= 0
        or artifact.get("kind") != "video"
    ):
        raise ValueError("attempt artifact is invalid")
    normalized["source"] = dict(source)
    normalized["artifact"] = dict(artifact)
    return normalized


@classmethod
def _normalize_record(
    cls,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    record = dict(row)
    tenant_id = record.get("tenant_id")
    attempt_id = str(record.get("id") or "")
    acceptance_id = record.get("acceptance_id")
    platform = record.get("platform")
    status = record.get("status")
    if (
        not isinstance(tenant_id, str)
        or not tenant_id
        or _UUID4_RE.fullmatch(attempt_id) is None
        or not isinstance(acceptance_id, str)
        or _UUID4_RE.fullmatch(acceptance_id) is None
        or not isinstance(platform, str)
        or platform not in ALLOWED_PLATFORMS
        or not isinstance(status, str)
        or status not in ALLOWED_STATUSES
        or record.get("updated_at") is None
    ):
        raise PublishAttemptStoreUnavailable
    record["id"] = attempt_id
    try:
        content = record.get("content")
        if isinstance(content, str):
            content = json.loads(content)
        elif isinstance(content, Mapping):
            content = dict(content)
        else:
            raise ValueError("attempt content is missing")
        record["content"] = cls._normalize_content_projection(
            content,
            tenant_id=tenant_id,
        )
    except (TypeError, ValueError, ValidationError):
        raise PublishAttemptStoreUnavailable from None
    try:
        cls._validate_transition_projection(
            new_status=status,
            post_id=record.get("post_id"),
            url=record.get("url"),
            error_code=record.get("error"),
        )
    except ValueError:
        raise PublishAttemptStoreUnavailable from None
    return record


@staticmethod
def _validate_transition_projection(
    *,
    new_status: str,
    post_id: str | None,
    url: str | None,
    error_code: str | None,
) -> None:
    if new_status in {"prepared", "acceptance_consumed"}:
        if post_id is not None or url is not None or error_code is not None:
            raise ValueError("active attempt projection is invalid")
        return
    if new_status == "published":
        if error_code is not None:
            raise ValueError("published attempt cannot carry an error")
    else:
        if post_id is not None or url is not None:
            raise ValueError("failed attempt cannot carry connector success")
        if (
            not isinstance(error_code, str)
            or error_code not in ALLOWED_ERROR_CODES
        ):
            raise ValueError("attempt error code is invalid")
        return
    if post_id is not None and (
        not isinstance(post_id, str)
        or not post_id
        or len(post_id) > 256
        or _CONTROL_RE.search(post_id)
    ):
        raise ValueError("post_id is invalid")
    if url is not None:
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("post URL is invalid")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("post URL is invalid")
~~~

Also define these exact backend methods:

- _insert_prepared(attempt_id, tenant_id, acceptance_id, platform, content_json) inserts status prepared, created_at/updated_at from database time, and returns a normalized row;
- _fetch_one(pg_query, sqlite_query, args) executes a tenant-bound read and returns a normalized row or None;
- _transition_backend(...) executes the approved CAS SQL and returns a normalized row or None;
- _insert_prepared_sqlite(...) and _transition_sqlite(...) run through asyncio.to_thread(), each acquire db.get_sqlite_lock(), execute BEGIN IMMEDIATE, commit once, and roll back on every exception;
- _validate_uuid4(), _require_text(), _validate_platform(), _validate_route_kind(), _validate_transition_projection(), and _raise_store_unavailable() reject malformed inputs and translate only driver/schema failures to PublishAttemptStoreUnavailable.

The PostgreSQL prepared insert is exact:

~~~sql
INSERT INTO publish_logs (
    id, tenant_id, acceptance_id, platform, content, status,
    created_at, updated_at
) VALUES (
    $1::uuid, $2, $3, $4, $5::jsonb, 'prepared', NOW(), NOW()
)
RETURNING *
~~~

The SQLite insert uses the same columns with CURRENT_TIMESTAMP and stores content_json as TEXT.

The PostgreSQL transition uses:

~~~sql
UPDATE publish_logs
SET status = $4,
    content = COALESCE($5::jsonb, content),
    post_id = COALESCE($6, post_id),
    url = COALESCE($7, url),
    error = COALESCE($8, error),
    updated_at = NOW()
WHERE tenant_id = $1
  AND id = $2::uuid
  AND status = $3
RETURNING *
~~~

The SQLite transition executes the equivalent inside BEGIN IMMEDIATE under db.get_sqlite_lock(), commits once, rolls back on every exception, and returns None for a stale status. _normalize_record parses content JSON and validates all new W1-23 rows. Production _backend uses db.get_verified_pg_pool() only.

- [x] **Step 8: Preserve backup and metrics truth**

Update tests/test_backup_production_contract.py to assert the recovery table list remains exactly 14 and that publish_logs schema contains tenant_id, acceptance_id, and updated_at after fresh init/restore.

Update tests/test_metrics_poller.py with:

~~~python
assert summary["publish_logs"]["used_by_metrics_poller"] is False
assert summary["publish_logs"]["reason"] == (
    "publish_logs lacks the full metrics pull candidate contract"
)
~~~

Do not add video_id/scenario/published_at to publish_logs and do not promote it to active metrics source.

- [x] **Step 9: Run GREEN and inspect schema ownership**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_repository.py tests/test_backup_production_contract.py tests/test_metrics_poller.py tests/test_run_alembic_upgrade.py -q
.venv/bin/python -m ruff check src/storage/publish_attempt_repository.py src/storage/db.py tests/test_publish_attempt_repository.py tests/test_backup_production_contract.py tests/test_metrics_poller.py
cd migrations
../.venv/bin/python -m alembic heads
cd ..
~~~

Expected: focused tests and Ruff pass; Alembic reports one head f9a2b3c4d5e6. No production database is contacted.

- [x] **Step 10: Inspect the Task 2 diff**

Run git diff --check and inspect migration downgrade order, fresh-init parity, existing SQLite preservation, and repository SQL. Confirm no connector, route, or frontend behavior changed.

---

### Task 3: Read-Only W1-22 Consume Outcome Inspection

**Files:**

- Create: tests/test_publish_acceptance_outcome.py
- Modify: src/services/artifact_acceptance.py
- Test: tests/test_artifact_acceptance_service.py
- Test: tests/test_acceptance_record_repository.py

**Interfaces:**

- Adds AcceptanceConsumeOutcome and inspect_publish_consume_outcome().
- Uses AcceptanceRecordRepository.get_by_id() only; it never exposes a public route or grants publish authority.
- Converts missing, malformed, database-error, and conflicting evidence to unknown.

- [x] **Step 1: Write RED outcome inspection tests**

Create tests/test_publish_acceptance_outcome.py using isolated SQLite and exact W1-22 rows:

~~~python
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.services.artifact_acceptance import ArtifactAcceptanceService
from src.storage import db as db_module
from src.storage.acceptance_repository import AcceptanceRecordRepository
from src.storage.idempotency_repository import SubmissionIdempotencyRepository

TENANT_ID = "tenant-alpha"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
VIDEO_BYTES = b"publish-outcome-fixture"


@dataclass(slots=True)
class OutcomeHarness:
    connection: sqlite3.Connection
    output_dir: Path
    service: ArtifactAcceptanceService

    def insert_available(self) -> str:
        path = (
            "tenants/tenant-alpha/pending_review/"
            "s2_outcome_fixture/assemble/final.mp4"
        )
        target = self.output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(VIDEO_BYTES)
        self.connection.execute(
            """
            INSERT INTO acceptance_records (
                id, tenant_id, creation_key_hash, fingerprint_version,
                request_hash, source_resource_type, source_resource_id,
                scenario, artifact_path, artifact_sha256,
                artifact_size_bytes, artifact_kind, decision, record_status,
                reviewer_key_id, reviewer_key_type, review_notes,
                expires_at, consumed_at, consumed_by_operation,
                consumed_by_resource_id, created_at, updated_at
            ) VALUES (
                ?, ?, ?, 'acceptance-create.v1', ?, 'scenario',
                's2_outcome_fixture', 's2', ?, ?, ?, 'video',
                'accepted', 'available', 'reviewer-a', 'tenant',
                'Reviewed exact bytes.', datetime('now', '+1 hour'),
                NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (
                ACCEPTANCE_ID,
                TENANT_ID,
                "a" * 64,
                "b" * 64,
                path,
                hashlib.sha256(VIDEO_BYTES).hexdigest(),
                len(VIDEO_BYTES),
            ),
        )
        self.connection.commit()
        return path


@pytest.fixture
def outcome_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> OutcomeHarness:
    connection = sqlite3.connect(
        str(tmp_path / "publish-outcome.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    service = ArtifactAcceptanceService(
        AcceptanceRecordRepository(require_postgres=False),
        SubmissionIdempotencyRepository(require_postgres=False),
        output_dir=output_dir,
    )
    yield OutcomeHarness(connection, output_dir, service)
    connection.close()


@pytest.mark.asyncio
async def test_inspector_distinguishes_available_and_consumed_owner(
    outcome_harness: OutcomeHarness,
) -> None:
    outcome_harness.insert_available()
    available = await outcome_harness.service.inspect_publish_consume_outcome(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        consumer_operation="distribution.publish",
        consumer_resource_id=ATTEMPT_ID,
    )
    assert available == "available_not_consumed"

    await outcome_harness.service.consume_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        consumer_operation="distribution.publish",
        consumer_resource_id=ATTEMPT_ID,
    )
    consumed = await outcome_harness.service.inspect_publish_consume_outcome(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        consumer_operation="distribution.publish",
        consumer_resource_id=ATTEMPT_ID,
    )
    assert consumed == "consumed_by_this_attempt"
~~~

Extend this local fixture; do not import a private fixture from another test module. Add cases for:

- consumed_by_another_attempt;
- rejected/revoked/expired as not_available, plus an `available` row whose expires_at is already past without mutating that row;
- missing row as unknown;
- malformed status, consumer operation, consumer resource ID, source identity, or artifact authority as unknown;
- repository exception as unknown;
- post-CAS response projection failure still inspects as consumed_by_this_attempt.

- [x] **Step 2: Run RED**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_acceptance_outcome.py tests/test_artifact_acceptance_service.py tests/test_acceptance_record_repository.py -q
~~~

Expected: new tests fail because inspect_publish_consume_outcome and AcceptanceConsumeOutcome are absent; all existing consume tests remain green.

- [x] **Step 3: Add the bounded outcome type and inspector**

In src/services/artifact_acceptance.py change the datetime import to `from datetime import UTC, datetime` and add:

~~~python
from datetime import UTC, datetime
from typing import Literal

AcceptanceConsumeOutcome = Literal[
    "available_not_consumed",
    "consumed_by_this_attempt",
    "consumed_by_another_attempt",
    "not_available",
    "unknown",
]

_ACCEPTANCE_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _consume_outcome_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise AcceptanceStoreUnavailable from None
    else:
        raise AcceptanceStoreUnavailable
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
~~~

Add this method to ArtifactAcceptanceService:

~~~python
async def inspect_publish_consume_outcome(
    self,
    *,
    tenant_id: str,
    acceptance_id: str,
    consumer_operation: str,
    consumer_resource_id: str,
) -> AcceptanceConsumeOutcome:
    try:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return "unknown"
        if (
            not isinstance(acceptance_id, str)
            or _ACCEPTANCE_UUID4_RE.fullmatch(acceptance_id) is None
        ):
            return "unknown"
        operation = _validate_consumer_identity(
            consumer_operation,
            max_length=64,
        )
        resource_id = _validate_consumer_identity(
            consumer_resource_id,
            max_length=128,
        )
        record = await self.repository.get_by_id(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        if record is None:
            return "unknown"
        _validate_stored_artifact_authority(
            record,
            expected_tenant_id=tenant_id,
        )
        status = record.get("record_status")
        decision = record.get("decision")
        expires_at = _consume_outcome_timestamp(record.get("expires_at"))
        if status == "available":
            if (
                decision == "accepted"
                and record.get("consumed_at") is None
                and record.get("consumed_by_operation") is None
                and record.get("consumed_by_resource_id") is None
            ):
                return (
                    "not_available"
                    if expires_at <= datetime.now(UTC)
                    else "available_not_consumed"
                )
            return "unknown"
        if status == "consumed":
            if decision != "accepted":
                return "unknown"
            _consume_outcome_timestamp(record.get("consumed_at"))
            stored_operation = _validate_consumer_identity(
                record.get("consumed_by_operation"),
                max_length=64,
            )
            stored_resource = _validate_consumer_identity(
                record.get("consumed_by_resource_id"),
                max_length=128,
            )
            if stored_operation == operation and stored_resource == resource_id:
                return "consumed_by_this_attempt"
            return "consumed_by_another_attempt"
        if status in {"rejected", "expired", "revoked"}:
            if (
                (status == "rejected") != (decision == "rejected")
                or record.get("consumed_at") is not None
                or record.get("consumed_by_operation") is not None
                or record.get("consumed_by_resource_id") is not None
            ):
                return "unknown"
            if status == "revoked":
                _consume_outcome_timestamp(record.get("revoked_at"))
            return "not_available"
        return "unknown"
    except (
        AcceptanceArtifactIntegrityMismatch,
        AcceptanceNotAvailable,
        AcceptanceStoreUnavailable,
        AcceptanceStoreUnavailableError,
        TypeError,
        ValueError,
    ):
        return "unknown"
~~~

Import the repository error explicitly and export AcceptanceConsumeOutcome in __all__. Do not call _project_record(), do not mutate expiry, and do not add an endpoint.

- [x] **Step 4: Add the post-CAS projection-failure regression**

In tests/test_publish_acceptance_outcome.py monkeypatch the response projection to raise AcceptanceStoreUnavailable after repository.consume returns. Assert:

~~~python
with pytest.raises(AcceptanceStoreUnavailable):
    await service.consume_for_publish(
        tenant_id=tenant_id,
        acceptance_id=acceptance_id,
        consumer_operation="distribution.publish",
        consumer_resource_id=attempt_id,
    )

assert await service.inspect_publish_consume_outcome(
    tenant_id=tenant_id,
    acceptance_id=acceptance_id,
    consumer_operation="distribution.publish",
    consumer_resource_id=attempt_id,
) == "consumed_by_this_attempt"
~~~

This is the regression that prevents acceptance_store_unavailable from being misreported as definitely unconsumed.

- [x] **Step 5: Run GREEN and prove no HTTP consume surface**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_acceptance_outcome.py tests/test_artifact_acceptance_service.py tests/test_acceptance_record_repository.py tests/test_acceptance_records_router.py -q
.venv/bin/python -m ruff check src/services/artifact_acceptance.py tests/test_publish_acceptance_outcome.py
~~~

Expected: all pass; acceptance router OpenAPI still has no path ending in /consume.

- [x] **Step 6: Inspect the Task 3 diff**

Run git diff --check. Confirm the change is read-only inspection plus tests, does not change W1-22 consume CAS, and does not add a route, retry, or connector call.

---

### Task 4: Connector Readiness and Shared Publish Attempt Service

**Files:**

- Create: src/services/publish_attempt.py
- Create: tests/test_publish_attempt_service.py
- Create: tests/test_publish_connector_log_safety.py
- Modify: src/connectors/registry.py
- Modify: src/connectors/tiktok_connector.py
- Modify: src/connectors/shopify_connector.py
- Test: tests/test_publish_attempt_repository.py
- Test: tests/test_publish_acceptance_outcome.py

**Interfaces:**

- Produces PublishConnectorReadiness and inspect_publish_readiness().
- Produces PublishAttemptService.execute(auth, request, route_kind).
- Makes actual connector publish-path failure logs/results stable and path/message-free without changing mock selection, credential lookup, request count, or receipt classification.
- Both HTTP routes will depend only on this service in Task 5.
- Connector and readiness functions remain injectable; local tests never inspect real credential values or contact a platform.

- [x] **Step 1: Write RED no-network readiness tests**

At the start of tests/test_publish_attempt_service.py add:

~~~python
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest


def test_readiness_reports_mock_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    monkeypatch.setattr(
        "src.connectors.tiktok_connector._is_mock_mode",
        lambda: True,
    )
    readiness = registry.inspect_publish_readiness("tiktok")
    assert readiness.ready is False
    assert readiness.reason == "missing_credentials_or_mock_mode"
    assert readiness.platform == "tiktok"
    assert "token" not in repr(readiness).lower()


def test_readiness_rejects_unknown_platform() -> None:
    from src.connectors.registry import inspect_publish_readiness

    with pytest.raises(ValueError, match="Unsupported platform"):
        inspect_publish_readiness("instagram")
~~~

Create tests/test_publish_connector_log_safety.py with fake credentials, a temporary local video, monkeypatched connector helpers/HTTP responses, and caplog. Cover both TikTok and Shopify:

~~~python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def configured_connector_with_raising_publish_helper(
    *,
    platform: str,
    sentinel: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    async def raising_helper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError(sentinel)

    if platform == "tiktok":
        from src.connectors.tiktok_connector import TikTokConnector

        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-present")
        connector = TikTokConnector()
        monkeypatch.setattr(connector, "_upload_video", raising_helper)
        return connector

    from src.connectors.shopify_connector import ShopifyConnector

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-present")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store")
    connector = ShopifyConnector()
    monkeypatch.setattr(connector, "_upload_video", raising_helper)
    return connector


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
async def test_publish_failure_never_logs_or_returns_raw_values(
    platform: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "raw-provider-secret-shaped-sentinel"
    video = tmp_path / "private-host-path.mp4"
    video.write_bytes(b"fixture-video")
    connector = configured_connector_with_raising_publish_helper(
        platform=platform,
        sentinel=sentinel,
        monkeypatch=monkeypatch,
    )

    result = await connector.publish({
        "video_path": str(video),
        "title": "Reviewed",
        "product_name": "Reviewed",
    })

    evidence = caplog.text + repr(result)
    assert sentinel not in evidence
    assert str(video) not in evidence
    assert result["success"] is False
    assert result["error"] in {
        "tiktok_publish_failed",
        "shopify_publish_failed",
    }
~~~

Add missing-file, non-200 response-body, remote error-message, upload exception, publish/association exception, and outer exception cases. Every fake is local; no real connector or provider request is allowed.

- [x] **Step 2: Write RED call-order and exact connector-payload tests**

Build a local harness with a fake acceptance service, fake attempt repository, real temporary artifact, injected readiness, and injected publisher. Assert this exact order:

~~~python
assert calls == [
    "readiness:tiktok",
    "attempt:prepared",
    "acceptance:consume",
    "attempt:acceptance_consumed",
    "connector:tiktok",
    "attempt:published",
]
~~~

For TikTok assert:

~~~python
assert connector_content == {
    "video_path": str(absolute_fixture_path),
    "title": "Reviewed campaign",
    "description": "Approved caption\n#momlife #wearablepump",
    "tags": ["momlife", "wearablepump"],
}
~~~

For Shopify assert:

~~~python
assert connector_content == {
    "video_path": str(absolute_fixture_path),
    "title": "Reviewed campaign",
    "product_name": "Wearable Breast Pump",
}
~~~

Assert the prepared projection has no source/artifact; the acceptance_consumed projection contains exact source/resource/scenario/path/hash/size/kind; no stored value contains the absolute fixture path.

- [x] **Step 3: Write RED failure, ambiguity, and concurrency tests**

Add parameterized service cases:

~~~python
@pytest.mark.parametrize(
    ("acceptance_error", "status_code", "code"),
    [
        ("not_found", 404, "acceptance_not_found"),
        ("expired", 409, "acceptance_expired"),
        ("not_available", 409, "acceptance_not_available"),
        (
            "integrity_mismatch",
            409,
            "acceptance_artifact_integrity_mismatch",
        ),
    ],
)
async def test_typed_acceptance_failure_never_calls_connector(
    acceptance_error: str,
    status_code: int,
    code: str,
) -> None:
    result = await run_failure_case(acceptance_error)
    assert result.error.status_code == status_code
    assert result.error.code == code
    assert result.connector_calls == 0
    assert result.attempt_status == "authorization_failed"
~~~

Add explicit tests for:

- readiness false: 503, no prepared row, no consume, no connector;
- prepared insert failure: 503, acceptance untouched;
- consume store error + available_not_consumed: 503, manual retry true, no connector;
- consume store error + consumed_by_this_attempt: 500 state unknown, consumed true, retry false, no connector;
- consume store error + unknown: 500 state unknown, consumed null, retry false, no connector;
- mark acceptance_consumed failure: 500 state unknown, no connector, no restore;
- post-consume path/hash/size mismatch: failed + publish_artifact_unavailable_after_consume, zero connector;
- explicit connector success=false: failed + 502 publish_connector_failed;
- connector timeout/exception/malformed result: ambiguous + 502 publish_outcome_ambiguous;
- terminal persistence failure: 500 publish_attempt_state_unknown and no retry;
- no error response or row contains raw exception text or host absolute path.

Add a 20-coroutine test with one acceptance and one fake connector:

~~~python
results = await asyncio.gather(
    *(service.execute(
        auth=publisher_auth,
        request=request,
        route_kind="canonical",
    ) for _ in range(20)),
    return_exceptions=True,
)

assert connector.call_count == 1
assert acceptance.consume_winners == 1
assert sum(
    isinstance(result, PublishAttemptError)
    and result.code == "acceptance_not_available"
    for result in results
) == 19
~~~

- [x] **Step 4: Run RED**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_service.py tests/test_publish_connector_log_safety.py tests/test_publish_attempt_repository.py tests/test_publish_acceptance_outcome.py -q
~~~

Expected: failures show missing readiness/service interfaces and old connector orchestration; no network call occurs because every dependency is fake.

- [x] **Step 5: Implement connector readiness**

Extend src/connectors/registry.py:

~~~python
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class PublishConnectorReadiness:
    platform: Literal["tiktok", "shopify"]
    ready: bool
    reason: str | None


def inspect_publish_readiness(platform: str) -> PublishConnectorReadiness:
    if platform == "tiktok":
        from src.connectors.tiktok_connector import _is_mock_mode
    elif platform == "shopify":
        from src.connectors.shopify_connector import _is_mock_mode
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    mock_mode = _is_mock_mode()
    return PublishConnectorReadiness(
        platform=platform,
        ready=not mock_mode,
        reason=(
            None if not mock_mode else "missing_credentials_or_mock_mode"
        ),
    )
~~~

Do not return credential names/values and do not make a status/network request.

In both connector files, harden only methods reachable from publish():

- replace missing-file path logs/results with `<platform>_video_unavailable` and no path;
- replace `logger.exception(...)`, raw response body/error-message logging, and product-name/error logging with one stable code plus `error_class=<type(exc).__name__>` when an exception exists;
- return only stable `<platform>_upload_failed`, `<platform>_publish_failed`, or `shopify_association_failed` error codes from publish helpers;
- keep HTTP status as a bounded integer log field if useful, but never include response text;
- do not change credential env names, mock-mode predicates, number/order of connector calls, success receipts, or status/metrics methods.

This is log/result sanitization required by W1-23's evidence invariant, not completion of W1-24/W1-25 connector truth.

- [x] **Step 6: Implement typed service errors and safe builders**

Create src/services/publish_attempt.py with:

~~~python
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from src.config import OUTPUT_DIR
from src.models.publish_attempt import (
    PublishAttemptErrorCode,
    PublishAttemptErrorDetail,
    PublishAttemptRequest,
    PublishAttemptResponse,
    PublishMetadata,
)
from src.routers._deps import AuthContext

logger = logging.getLogger(__name__)
RouteKind = Literal["canonical", "legacy_adapter"]


class PublishAttemptError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: PublishAttemptErrorCode,
        publish_attempt_id: str | None,
        acceptance_consumed: bool | None,
        retry_allowed: bool,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.detail = PublishAttemptErrorDetail(
            code=code,
            publish_attempt_id=publish_attempt_id,
            acceptance_consumed=acceptance_consumed,
            retry_allowed=retry_allowed,
        )


def _source_prefix(
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> str:
    if resource_type == "fast":
        return (
            f"tenants/{tenant_id}/pending_review/fast_mode/"
            f"{resource_id}"
        )
    return f"tenants/{tenant_id}/pending_review/{resource_id}"


def _tiktok_content(metadata: PublishMetadata, video_path: Path) -> dict[str, Any]:
    title = metadata.title or metadata.hook or "AI-generated video"
    description = metadata.description or metadata.hook or title
    tags = metadata.hashtags or metadata.tags
    if tags:
        description = description + "\n" + " ".join(
            f"#{tag}" for tag in tags
        )
    return {
        "video_path": str(video_path),
        "title": title,
        "description": description,
        "tags": tags,
    }


def _shopify_content(
    metadata: PublishMetadata,
    video_path: Path,
) -> dict[str, Any]:
    title = metadata.title or metadata.hook or "AI-generated video"
    return {
        "video_path": str(video_path),
        "title": title,
        "product_name": metadata.product_name or title,
    }
~~~

Define dependency callables for readiness, connector publish, artifact acceptance, artifact resolution, and attempt repository. The service logger records only stable code, attempt ID, platform, trace ID, and exception class name; never str(exc).

- [x] **Step 7: Implement the exact service sequence**

Implement PublishAttemptService.execute() with this public signature:

~~~python
class PublishAttemptService:
    async def execute(
        self,
        *,
        auth: AuthContext,
        request: PublishAttemptRequest,
        route_kind: RouteKind,
    ) -> PublishAttemptResponse:
        tenant_id = self._require_tenant(auth)
        readiness = self.readiness_inspector(request.platform)
        if not readiness.ready:
            raise PublishAttemptError(
                status_code=503,
                code="publish_connector_not_ready",
                publish_attempt_id=None,
                acceptance_consumed=False,
                retry_allowed=True,
            )

        prepared = await self._create_prepared(
            tenant_id=tenant_id,
            request=request,
            route_kind=route_kind,
        )
        attempt_id = prepared["id"]
        consumed = await self._consume_or_fail_closed(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
        )
        content = self._build_consumed_audit_content(
            route_kind=route_kind,
            metadata=request.metadata,
            consumed=consumed,
        )
        await self._mark_consumed_or_stop(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            content=content,
        )
        artifact = self._resolve_consumed_artifact(
            tenant_id=tenant_id,
            consumed=consumed,
        )
        connector_content = (
            _tiktok_content(request.metadata, artifact.absolute_path)
            if request.platform == "tiktok"
            else _shopify_content(request.metadata, artifact.absolute_path)
        )
        return await self._publish_once_and_persist(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
            connector_content=connector_content,
        )
~~~

The private helpers must implement the approved mappings exactly:

- typed W1-22 errors transition prepared → authorization_failed;
- AcceptanceStoreUnavailable performs one inspect_publish_consume_outcome read and never calls connector on that request;
- only proven available_not_consumed returns 503/retry_allowed=true;
- consumed_by_this_attempt and unknown return 500 state unknown with retry false;
- consumed projection is re-resolved with exact tenant/source prefix and .mp4/.webm, then path/hash/size are compared again;
- prepared → acceptance_consumed CAS must succeed before publisher();
- publisher() is awaited exactly once;
- success must validate safe post_id/post_url before published;
- explicit success false becomes failed;
- exceptions and malformed success truth become ambiguous;
- terminal store failure becomes publish_attempt_state_unknown;
- acceptance is never restored and no task/retry is scheduled.

For an explicit connector `success=true`, read only `post_id` and the current connector `url` field, then construct PublishAttemptResponse before terminal persistence. This validates the connector URL as safe `post_url`; persist the normalized `post_id` and `post_url` only after that validation. Ignore connector `error`, `status`, `platform`, `published_at`, and every unknown field. A non-mapping result, missing/non-boolean success, platform contradiction if platform is present, or invalid post projection follows the ambiguous path. Explicit `success=false` stores only `publish_connector_failed`, never the connector's raw error.

Provide get_publish_attempt_service() singleton for route injection, matching the existing acceptance service pattern.

- [x] **Step 8: Run GREEN service tests**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_service.py tests/test_publish_connector_log_safety.py tests/test_publish_attempt_repository.py tests/test_publish_acceptance_outcome.py tests/test_artifact_acceptance_service.py -q
.venv/bin/python -m ruff check src/connectors/registry.py src/connectors/tiktok_connector.py src/connectors/shopify_connector.py src/services/publish_attempt.py tests/test_publish_attempt_service.py tests/test_publish_connector_log_safety.py
~~~

Expected: all call-order, failure, and 20-way concurrency tests pass; connector count is exactly one; Ruff exits 0.

- [x] **Step 9: Inspect the Task 4 diff and logs**

Run git diff --check and inspect service/repository logs. Confirm no raw exception message, connector result body, credential name/value, absolute artifact path, automatic retry, background task, or acceptance restore exists.

---

### Task 5: Authenticated Canonical and Deprecated HTTP Adapters

**Files:**

- Create: tests/test_publish_acceptance_routes.py
- Modify: src/api.py
- Modify: src/routers/distribution.py
- Modify: tests/test_distribution_publish_guard.py
- Test: tests/test_acceptance_records_router.py
- Test: tests/test_backend_route_auth_contract.py

**Interfaces:**

- POST /distribution/publish is canonical and accepts only PublishAttemptRequest.
- POST /publish/{video_id} is deprecated but accepts the same body and returns the same single response.
- Both require artifact:publish or all and call the same PublishAttemptService.
- GET distribution status/platform routes remain authenticated and behavior-compatible.

- [x] **Step 1: Write RED authenticated route fixtures**

Create tests/test_publish_acceptance_routes.py using the DB-backed auth pattern from acceptance route tests. Provide four principals:

~~~python
permissions = {
    "publisher": ["artifact:publish"],
    "reviewer": ["artifact:accept"],
    "generator": ["provider:submit"],
    "all_access": ["all"],
}
tenants = {
    "publisher": "tenant-a",
    "reviewer": "tenant-a",
    "generator": "tenant-a",
    "all_access": "tenant-a",
}
~~~

Inject a fake PublishAttemptService whose execute() records auth tenant, strict body, and route_kind and returns:

~~~python
PublishAttemptResponse(
    publish_attempt_id="91ec3593-cc3c-42bf-99ee-c98655c5826b",
    acceptance_id="7f947625-2898-4e9e-9e71-dce4309e5f4f",
    platform="tiktok",
    status="published",
    success=True,
    post_id="fixture-post-1",
    post_url="https://example.invalid/posts/fixture-post-1",
    acceptance_consumed=True,
    retry_allowed=False,
)
~~~

- [x] **Step 2: Write RED permission and safe-validation tests**

Add ASGI tests that prove:

~~~python
@pytest.mark.asyncio
@pytest.mark.parametrize("principal", ["reviewer", "generator"])
async def test_non_publish_permissions_are_denied_before_body_parse(
    principal: str,
    tenant_auth_headers,
    fake_publish_service,
) -> None:
    response = await post_raw(
        "/distribution/publish",
        headers=tenant_auth_headers[principal],
        content=b'{"credential":"must-not-be-parsed"',
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission"
    assert fake_publish_service.calls == []
~~~

Add missing/invalid key 401 cases and safe 422 cases for invalid JSON, body credential fields, input values containing secret-shaped text, legacy content, delivery_acceptance, metadata.video_path, platforms arrays, and unknown fields. Assert response JSON contains only type/loc/msg validation entries and never input, ctx, url, or raw values. Assert every legacy success/error case, including 401/403/422, carries the deprecation headers.

Assert valid publisher and all_access requests each produce one fake-service call with the authenticated tenant. Cross-tenant identity cannot be supplied in the body.

- [x] **Step 3: Write RED canonical/deprecated parity tests**

For both paths:

~~~python
body = {
    "acceptance_id": "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    "platform": "tiktok",
    "metadata": {"title": "Reviewed campaign"},
}
~~~

Assert canonical passes route_kind=canonical. Assert legacy /publish/client-video-label passes route_kind=legacy_adapter, returns one object rather than a list, and the path value is absent from the service request and audit projection.

Assert the legacy response includes:

~~~python
assert response.headers["Deprecation"] == "true"
assert response.headers["Link"] == (
    '</distribution/publish>; rel="successor-version"'
)
~~~

Add unsafe path-parameter cases and verify no service call. Add a fake PublishAttemptError for every status/code and assert both routes preserve status, stable detail, acceptance_consumed, retry_allowed, and attempt ID without raw exception text.

- [x] **Step 4: Write RED OpenAPI tests**

Assert:

~~~python
paths = app.openapi()["paths"]
canonical = paths["/distribution/publish"]["post"]
legacy = paths["/publish/{video_id}"]["post"]

assert canonical["requestBody"]["required"] is True
assert legacy["requestBody"]["required"] is True
assert legacy["deprecated"] is True
assert canonical["requestBody"] == legacy["requestBody"]
assert canonical["requestBody"]["content"]["application/json"]["schema"] == (
    PublishAttemptRequest.model_json_schema(mode="validation")
)
legacy_path = next(
    parameter
    for parameter in legacy["parameters"]
    if parameter["in"] == "path" and parameter["name"] == "video_id"
)
assert legacy_path["schema"]["minLength"] == 1
assert legacy_path["schema"]["maxLength"] == 128
assert legacy_path["schema"]["pattern"] == "^[A-Za-z0-9_-]+$"
assert not any(path.endswith("/consume") for path in paths)
~~~

Assert both operations declare 200 plus 401/403/404/409/422/500/502/503 and reference the safe success/error models.

- [x] **Step 5: Run RED**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_acceptance_routes.py tests/test_distribution_publish_guard.py tests/test_acceptance_records_router.py -q
~~~

Expected: failures prove current routes still trust body assertions, use verify_api_key only, fan out through PublishEngine, search by video_id, and lack strict OpenAPI bodies.

- [x] **Step 6: Replace the unsafe router authority**

Refactor src/routers/distribution.py imports and add safe parsing:

~~~python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import ValidationError

from src.models.publish_attempt import (
    PublishAttemptErrorResponse,
    PublishAttemptRequest,
    PublishAttemptResponse,
)
from src.routers._deps import AuthContext, require_permission, verify_api_key
from src.services.publish_attempt import (
    PublishAttemptError,
    get_publish_attempt_service,
)

_PUBLISH_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": PublishAttemptRequest.model_json_schema(
                    mode="validation"
                )
            }
        },
    },
}


async def _parse_publish_request(request: Request) -> PublishAttemptRequest:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "json_invalid",
                    "loc": ["body"],
                    "msg": "Invalid JSON",
                }
            ],
        ) from None
    try:
        return PublishAttemptRequest.model_validate(payload)
    except ValidationError as exc:
        safe_errors = [
            {
                "type": str(item.get("type") or "value_error"),
                "loc": list(item.get("loc") or ("body",)),
                "msg": str(item.get("msg") or "Invalid request"),
            }
            for item in exc.errors(
                include_url=False,
                include_context=False,
            )
        ]
        raise HTTPException(status_code=422, detail=safe_errors) from None
~~~

Always construct the three-field projection shown above. Never return the original Pydantic error dict or its input value.

Remove _extract_publish_authorization(), _require_human_publish_authorization(), PublishLogRepository, HAS_STORAGE, PublishEngine, client metadata mutation, and OUTPUT_DIR.rglob() from the mutation routes. Keep the two GET routes unchanged.

Keep the existing distribution router mount and its outer verify_api_key dependency unchanged. Both mutations also own require_permission("artifact:publish"), and the two GET routes retain their explicit verify_api_key dependencies. This preserves FastAPI dependency caching/overrides and the established route-auth boundary.

In src/api.py, after response_wrapper_middleware and before router mounts, add one narrow response-header middleware:

~~~python
_LEGACY_PUBLISH_HEADERS = {
    "Deprecation": "true",
    "Link": '</distribution/publish>; rel="successor-version"',
}


@app.middleware("http")
async def legacy_publish_deprecation_middleware(request, call_next):
    response = await call_next(request)
    parts = request.url.path.split("/")
    is_legacy_publish = (
        request.method == "POST"
        and len(parts) == 3
        and parts[1] == "publish"
        and bool(parts[2])
    )
    if is_legacy_publish:
        response.headers.update(_LEGACY_PUBLISH_HEADERS)
    return response
~~~

This middleware adds no body, authority, or error translation. It only preserves the approved deprecation metadata across outer auth, FastAPI path/body validation, route success, and typed service errors. Add route tests proving all four distribution routes still reject missing/invalid keys and that unrelated routes receive no deprecation headers.

- [x] **Step 7: Implement the canonical route**

Use:

~~~python
@router.post(
    "/distribution/publish",
    response_model=PublishAttemptResponse,
    responses={
        401: {"description": "Invalid API key"},
        403: {"description": "Insufficient permission"},
        404: {"model": PublishAttemptErrorResponse},
        409: {"model": PublishAttemptErrorResponse},
        422: {"description": "Safe validation projection"},
        500: {"model": PublishAttemptErrorResponse},
        502: {"model": PublishAttemptErrorResponse},
        503: {"model": PublishAttemptErrorResponse},
    },
    openapi_extra=_PUBLISH_OPENAPI_EXTRA,
)
async def distribution_publish(
    request: Request,
    auth: AuthContext = Depends(require_permission("artifact:publish")),
) -> PublishAttemptResponse:
    body = await _parse_publish_request(request)
    try:
        return await get_publish_attempt_service().execute(
            auth=auth,
            request=body,
            route_kind="canonical",
        )
    except PublishAttemptError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail.model_dump(mode="json"),
        ) from None
~~~

- [x] **Step 8: Implement the deprecated adapter**

Use the same parser/service and standard dependency path:

~~~python
@router.post(
    "/publish/{video_id}",
    response_model=PublishAttemptResponse,
    deprecated=True,
    openapi_extra=_PUBLISH_OPENAPI_EXTRA,
)
async def publish_video(
    request: Request,
    video_id: Annotated[
        str,
        Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    auth: AuthContext = Depends(require_permission("artifact:publish")),
) -> PublishAttemptResponse:
    del video_id
    body = await _parse_publish_request(request)
    try:
        return await get_publish_attempt_service().execute(
            auth=auth,
            request=body,
            route_kind="legacy_adapter",
        )
    except PublishAttemptError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail.model_dump(mode="json"),
        ) from None
~~~

Declare the same error responses as the canonical route. FastAPI emits the bounded minLength/maxLength/pattern path schema and performs safe path validation; the app middleware adds deprecation headers after auth, validation, parser, or service handling. Every controlled legacy response advertises deprecation, and normal dependency overrides remain effective.

- [x] **Step 9: Rewrite obsolete guard tests as strict regressions**

Replace each old assertion in tests/test_distribution_publish_guard.py with the corresponding W1-23 invariant:

- no acceptance ID fails before connector;
- LLM/human body assertions are extra fields and return 422;
- approved_brand_token_write is rejected as unknown input;
- client video_path and filesystem lookup are never reached;
- multi-platform arrays are rejected;
- PublishEngine is never constructed;
- specialized service is the only mutation target.

Do not delete the file or reduce the number of behavioral branches.

- [x] **Step 10: Run GREEN and route regression**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_acceptance_routes.py tests/test_distribution_publish_guard.py tests/test_acceptance_records_router.py tests/test_p0_bcgh_fixes.py -q
.venv/bin/python -m ruff check src/api.py src/routers/distribution.py tests/test_publish_acceptance_routes.py tests/test_distribution_publish_guard.py
~~~

Expected: all pass; platform/status GET regression stays green; Ruff exits 0.

- [x] **Step 11: Inspect the Task 5 diff**

Run git diff --check and repository-wide search for _require_human_publish_authorization, metadata.video_path, OUTPUT_DIR.rglob, and PublishEngine usage inside distribution routes. The old authority helpers and route fan-out must be absent; no public consume route may exist.

Implementation note: FastAPI's merge removed explicit `default: null` values from the manual request schema, while embedding Pydantic's raw `#/$defs/...` form made the OpenAPI document unresolvable by the pinned `openapi-typescript 7.13.0`. The reviewed implementation preserves the exact validation semantics, promotes definitions into `components.schemas`, rewrites local references, fails before mutation on component collisions, and keeps the canonical and deprecated request bodies identical and required.

---

### Task 6: Frontend Zero-Network Guards and Generated OpenAPI Contract

**Files:**

- Create: web/src/components/apiPublishAcceptance.test.ts
- Modify: web/src/components/api.ts
- Modify generated: web/src/types/api.generated.ts
- Test: web/src/components/CriticalViews.i18n.test.tsx
- Test: web/src/components/OneShotResultView.test.tsx
- Test: tests/test_openapi_types_drift_guard.py

**Interfaces:**

- publishContent and publishVideo accept acceptanceId only through their options object.
- Existing UI callers compile unchanged but fail locally before apiFetch because they do not have acceptance IDs.
- Valid helper calls send exactly one strict POST and never send path/URL/human authority fields.

- [x] **Step 1: Write RED frontend helper tests**

Create web/src/components/apiPublishAcceptance.test.ts:

~~~typescript
import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApi() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({
      publish_attempt_id: "91ec3593-cc3c-42bf-99ee-c98655c5826b",
      acceptance_id: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
      platform: "tiktok",
      status: "published",
      success: true,
      post_id: "fixture-post",
      post_url: "https://example.invalid/posts/fixture-post",
      acceptance_consumed: true,
      retry_allowed: false,
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  api.setApiLogging(false);
  return { api, fetchMock };
}

describe("publish acceptance helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.resetModules();
    localStorage.clear();
  });

  it("makes zero requests without acceptance", async () => {
    const { api, fetchMock } = await loadApi();

    await expect(
      api.publishContent("tiktok", { title: "Reviewed" }),
    ).rejects.toThrow("Publish acceptance is required");
    await expect(
      api.publishVideo("client-video", ["tiktok"], { title: "Reviewed" }),
    ).rejects.toThrow("Publish acceptance is required");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects zero or multiple platforms before network", async () => {
    const { api, fetchMock } = await loadApi();
    const options = {
      acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    };

    await expect(
      api.publishVideo("client-video", [], {}, options),
    ).rejects.toThrow("Exactly one publish platform is required");
    await expect(
      api.publishVideo(
        "client-video",
        ["tiktok", "shopify"],
        {},
        options,
      ),
    ).rejects.toThrow("Exactly one publish platform is required");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects unsafe metadata before network", async () => {
    const { api, fetchMock } = await loadApi();

    await expect(
      api.publishContent(
        "tiktok",
        { title: "Reviewed", video_path: "/tmp/client.mp4" },
        {
          acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
        },
      ),
    ).rejects.toThrow("Publish metadata is invalid");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects invalid ids, platforms, and bounded metadata before network", async () => {
    const { api, fetchMock } = await loadApi();
    const validOptions = {
      acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    };
    const attempts = [
      () => api.publishContent(
        "tiktok",
        {},
        { acceptanceId: "7F947625-2898-4E9E-9E71-DCE4309E5F4F" },
      ),
      () => api.publishContent("instagram", {}, validOptions),
      () => api.publishContent(
        "tiktok",
        { title: "bad\u0000title" },
        validOptions,
      ),
      () => api.publishContent(
        "tiktok",
        { tags: ["momlife", " momlife "] },
        validOptions,
      ),
      () => api.publishContent(
        "tiktok",
        { tags: Array.from({ length: 31 }, (_, index) => `tag-${index}`) },
        validOptions,
      ),
      () => api.publishContent(
        "tiktok",
        { description: "界".repeat(5000), hook: "界".repeat(1000) },
        validOptions,
      ),
      () => api.publishContent(
        "tiktok",
        { title: "Reviewed", credential: "not-allowed" },
        validOptions,
      ),
    ];

    for (const attempt of attempts) {
      await expect(attempt()).rejects.toThrow();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
~~~

- [x] **Step 2: Add RED one-POST/body tests**

Append:

~~~typescript
it("sends one canonical strict request", async () => {
  const { api, fetchMock } = await loadApi();

  await api.publishContent(
    "tiktok",
    {
      title: "Reviewed",
      hashtags: ["momlife"],
    },
    {
      acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    },
  );

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toContain("/distribution/publish");
  expect(JSON.parse(String(init?.body))).toEqual({
    acceptance_id: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    platform: "tiktok",
    metadata: {
      title: "Reviewed",
      hashtags: ["momlife"],
    },
  });
});

it("legacy helper sends one platform and no client path authority", async () => {
  const { api, fetchMock } = await loadApi();

  await api.publishVideo(
    "client-video",
    ["shopify"],
    {
      title: "Reviewed",
      product_name: "Wearable Breast Pump",
    },
    {
      acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    },
  );

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toContain("/publish/client-video");
  const body = JSON.parse(String(init?.body));
  expect(body.platform).toBe("shopify");
  expect(body).not.toHaveProperty("platforms");
  expect(body).not.toHaveProperty("videoId");
  expect(body.metadata).not.toHaveProperty("video_path");
});

it("never previews publish request or response bodies in debug logs", async () => {
  const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
  const { api } = await loadApi();
  api.setApiLogging(true);

  await api.publishContent(
    "tiktok",
    { title: "Reviewed private campaign" },
    {
      acceptanceId: "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    },
  );

  const logs = JSON.stringify(logSpy.mock.calls);
  expect(logs).toContain("[body omitted]");
  expect(logs).not.toContain("7f947625-2898-4e9e-9e71-dce4309e5f4f");
  expect(logs).not.toContain("91ec3593-cc3c-42bf-99ee-c98655c5826b");
  expect(logs).not.toContain("Reviewed private campaign");
});
~~~

- [x] **Step 3: Run frontend RED**

Run:

~~~bash
cd web
npm test -- --run src/components/apiPublishAcceptance.test.ts
~~~

Expected: tests fail because options lack acceptanceId, helpers send old bodies immediately, and multi-platform requests are still allowed.

- [x] **Step 4: Implement strict runtime helper guards**

In web/src/components/api.ts add:

~~~typescript
type PublishPlatform = "tiktok" | "shopify";

type PublishMetadata = {
  title?: string;
  description?: string;
  hook?: string;
  product_name?: string;
  hashtags?: string[];
  tags?: string[];
};

type PublishRequestOptions = {
  signal?: AbortSignal;
  acceptanceId?: string;
};

type PublishTextKey = "title" | "description" | "hook" | "product_name";

const ACCEPTANCE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PUBLISH_METADATA_KEYS = new Set([
  "title",
  "description",
  "hook",
  "product_name",
  "hashtags",
  "tags",
]);

function requireAcceptanceId(value: string | undefined): string {
  if (!value || !ACCEPTANCE_ID_RE.test(value)) {
    throw new Error("Publish acceptance is required");
  }
  return value;
}

function requirePublishPlatform(value: string): PublishPlatform {
  if (value !== "tiktok" && value !== "shopify") {
    throw new Error("Unsupported publish platform");
  }
  return value;
}

function isPublishMutationUrl(url: string, method: string): boolean {
  if (method !== "POST") return false;
  try {
    const pathname = new URL(url).pathname;
    return (
      pathname === "/distribution/publish"
      || pathname.startsWith("/publish/")
    );
  } catch {
    return false;
  }
}

function requirePublishMetadata(value: unknown): PublishMetadata {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Publish metadata is invalid");
  }
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !PUBLISH_METADATA_KEYS.has(key))) {
    throw new Error("Publish metadata is invalid");
  }
  const normalized: PublishMetadata = {};
  const stringLimits: Record<PublishTextKey, number> = {
    title: 300,
    description: 5000,
    hook: 1000,
    product_name: 300,
  };
  const control = /[\u0000-\u001f\u007f]/;
  for (const key of Object.keys(stringLimits) as PublishTextKey[]) {
    const limit = stringLimits[key];
    const field = record[key];
    if (field === undefined) continue;
    if (typeof field !== "string") {
      throw new Error("Publish metadata is invalid");
    }
    const text = field.trim();
    if (!text || text.length > limit || control.test(text)) {
      throw new Error("Publish metadata is invalid");
    }
    normalized[key] = text;
  }
  for (const key of ["hashtags", "tags"] as const) {
    const field = record[key];
    if (field === undefined) continue;
    if (!Array.isArray(field) || field.length > 30) {
      throw new Error("Publish metadata is invalid");
    }
    const values = field.map((item) => {
      if (typeof item !== "string") {
        throw new Error("Publish metadata is invalid");
      }
      const text = item.trim();
      if (
        !text
        || text.length > 100
        || text.startsWith("#")
        || control.test(text)
      ) {
        throw new Error("Publish metadata is invalid");
      }
      return text;
    });
    if (new Set(values).size !== values.length) {
      throw new Error("Publish metadata is invalid");
    }
    normalized[key] = values;
  }
  const encoded = new TextEncoder().encode(
    JSON.stringify(normalized),
  ).byteLength;
  if (encoded > 16 * 1024) {
    throw new Error("Publish metadata is invalid");
  }
  return normalized;
}
~~~

The helper returns only the normalized allowlist shown above; it does not spread the caller object or retain unknown fields. In apiFetch(), split `mediaBody = isMediaUrl(absUrl)` and `publishBody = isPublishMutationUrl(absUrl, method)`, set `skipBody = mediaBody || publishBody`, and use `[body omitted]` for publish request, success-response, and error-response logging. Keep the existing `[media/binary]` label for media. Never call safeBodyPreview() or clone/read a response body when publishBody is true.

- [x] **Step 5: Rewrite the two helpers**

Use:

~~~typescript
export async function publishContent(
  platform: string,
  metadata: unknown,
  options?: PublishRequestOptions,
): Promise<Record<string, unknown>> {
  const acceptanceId = requireAcceptanceId(options?.acceptanceId);
  const strictPlatform = requirePublishPlatform(platform);
  const strictMetadata = requirePublishMetadata(metadata);
  const res = await apiFetch("/distribution/publish", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      acceptance_id: acceptanceId,
      platform: strictPlatform,
      metadata: strictMetadata,
    }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function publishVideo(
  videoId: string,
  platforms: string[],
  metadata: unknown,
  options?: PublishRequestOptions,
): Promise<PublishResult> {
  const acceptanceId = requireAcceptanceId(options?.acceptanceId);
  if (platforms.length !== 1) {
    throw new Error("Exactly one publish platform is required");
  }
  const strictPlatform = requirePublishPlatform(platforms[0]);
  const strictMetadata = requirePublishMetadata(metadata);
  const res = await apiFetch("/publish/" + encodeURIComponent(videoId), {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      acceptance_id: acceptanceId,
      platform: strictPlatform,
      metadata: strictMetadata,
    }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}
~~~

Do not add an acceptance fallback, localStorage acceptance search, path inference, second POST, or UI state.

- [x] **Step 6: Run frontend GREEN and component regression**

Run:

~~~bash
cd web
npm test -- --run src/components/apiPublishAcceptance.test.ts src/components/CriticalViews.i18n.test.tsx src/components/OneShotResultView.test.tsx
npx eslint src/components/api.ts src/components/apiPublishAcceptance.test.ts
npx tsc --noEmit
~~~

Expected: helper tests pass, existing components compile, and their lack of acceptance remains a local error path with zero POST.

- [x] **Step 7: Regenerate and verify OpenAPI TypeScript**

Run:

~~~bash
cd web
npm run typegen:api
npm run check:api-types
~~~

Expected: generated types contain required acceptance_id, one platform enum, strict metadata, one success object, legacy deprecated marker, and no requestBody?: never. Only web/src/types/api.generated.ts changes from generation.

- [x] **Step 8: Inspect the Task 6 diff**

Run git diff --check. Inspect generated types and frontend bodies. Confirm no component received a fake acceptance ID, no UI was added, and no helper can send zero/multiple platforms or client path authority.

Implementation note: review-driven cross-layer tests tightened the metadata source contract to optional, non-null strings; aligned frontend size checks with the backend's six-field canonical projection; aligned JavaScript code-point and surrogate handling with Python Unicode behavior; validated legacy IDs before network; and made publish log omission robust to base-path prefixes, query strings, and trailing slashes. Generated types were regenerated only from the corrected OpenAPI source. The existing broad helper response types remain a documented nonblocking quality Minor because narrowing them would require a separate caller compatibility change.

---

### Task 7: Live-E2E Safety, Recovery Governance, and Operator Documentation

**Files:**

- Modify: tests/test_publish_e2e.py
- Modify: tests/test_backend_route_auth_contract.py
- Modify: tests/test_backup_production_contract.py
- Modify: tests/test_run_alembic_upgrade.py
- Modify: configs/backend-route-auth-contract.yaml
- Create: docs/runbooks/publish-acceptance-consumption.md
- Modify: docs/runbooks/backend-route-auth-contract.md
- Modify: docs/runbooks/artifact-acceptance-lifecycle.md
- Modify: docs/reference/api-endpoints.md
- Modify: docs/runbooks/README.md

**Interfaces:**

- Converts W1-23 pending governance into exact completed-local route/permission/error truth.
- Keeps every real publish test blocked without an exact W1-26 authorization switch and acceptance ID.
- Preserves 14-table recovery order while validating the new publish_logs column set.

- [x] **Step 1: Write RED governance assertions**

Update tests/test_backend_route_auth_contract.py to require:

~~~python
publish = contract["publish_acceptance_routes"]
assert publish["required_any_permission"] == ["artifact:publish", "all"]
assert publish["artifact_accept_only_allowed"] is False
assert publish["provider_submit_only_allowed"] is False
assert publish["single_platform_only"] is True
assert publish["client_artifact_path_allowed"] is False
assert publish["body_human_assertion_allowed"] is False
assert publish["public_consume_endpoint"] is False
assert publish["routes"] == [
    {
        "name": "canonical",
        "method": "POST",
        "path": "/distribution/publish",
        "deprecated": False,
    },
    {
        "name": "legacy_adapter",
        "method": "POST",
        "path": "/publish/{video_id}",
        "deprecated": True,
    },
]
assert contract["acceptance_record_routes"]["distribution_integration"] == (
    "W1-23 completed_local"
)
~~~

Add docs token checks for all stable publish codes, artifact:publish, acceptance_consumed, retry_allowed, production unchanged, provider_call=false, live_publish=false, and the no-restore/no-auto-retry rule.

- [x] **Step 2: Write RED live-E2E authorization guards and remove bypass paths**

First add a source-governance assertion in tests/test_backend_route_auth_contract.py:

~~~python
live_test = Path("tests/test_publish_e2e.py").read_text(encoding="utf-8")
assert "get_connector(" not in live_test
assert ".publish({" not in live_test
assert "print(" not in live_test
assert '"video_path"' not in live_test
assert '"delivery_acceptance"' not in live_test
assert '"acceptance_id"' in live_test
assert '"/distribution/publish"' in live_test
~~~

Then replace the two direct TikTok/Shopify connector mutation tests in tests/test_publish_e2e.py with one acceptance-bound HTTP route test. Do not retain a credential-only direct connector call. Require the entire module to satisfy:

~~~python
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _live_publish_authorized() -> bool:
    return (
        os.environ.get("RUN_LIVE_PUBLISH") == "1"
        and _UUID4_RE.fullmatch(
            os.environ.get("LIVE_PUBLISH_ACCEPTANCE_ID", "")
        ) is not None
        and os.environ.get("LIVE_PUBLISH_PLATFORM") in {"tiktok", "shopify"}
        and bool(os.environ.get("LIVE_PUBLISH_API_KEY"))
    )


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _live_publish_authorized(),
        reason=(
            "requires RUN_LIVE_PUBLISH=1, one exact acceptance ID, "
            "one exact platform, and an explicit publish API key"
        ),
    ),
]
~~~

The sole mutation test must call the canonical HTTP route with this shape:

~~~python
@pytest.mark.asyncio
async def test_acceptance_bound_distribution_publish() -> None:
    from httpx import ASGITransport, AsyncClient

    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/distribution/publish",
            headers={"X-API-Key": os.environ["LIVE_PUBLISH_API_KEY"]},
            json={
                "acceptance_id": os.environ[
                    "LIVE_PUBLISH_ACCEPTANCE_ID"
                ],
                "platform": os.environ["LIVE_PUBLISH_PLATFORM"],
                "metadata": {
                    "title": "Authorized publish acceptance test",
                    "description": "Separately authorized W1-26 evidence",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert payload["acceptance_consumed"] is True
    assert payload["retry_allowed"] is False
~~~

Never include video_path, delivery_acceptance, a default API key, credential-only mutation authority, or body/result printing. Keep this entire file unexecuted in W1-23 local acceptance; it belongs to a separately authorized W1-26 run and consumes a real acceptance if authorized later.

- [x] **Step 3: Run RED governance tests only**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_backend_route_auth_contract.py tests/test_backup_production_contract.py tests/test_run_alembic_upgrade.py -q
~~~

Expected: governance assertions fail because contracts/docs still state W1-23 pending. tests/test_publish_e2e.py is not executed.

- [x] **Step 4: Update the machine-readable route contract**

Add to configs/backend-route-auth-contract.yaml:

~~~yaml
publish_acceptance_routes:
  required_any_permission:
    - artifact:publish
    - all
  artifact_accept_only_allowed: false
  provider_submit_only_allowed: false
  single_platform_only: true
  client_artifact_path_allowed: false
  body_human_assertion_allowed: false
  public_consume_endpoint: false
  routes:
    - name: canonical
      method: POST
      path: /distribution/publish
      deprecated: false
    - name: legacy_adapter
      method: POST
      path: /publish/{video_id}
      deprecated: true
~~~

Change acceptance_record_routes.distribution_integration to W1-23 completed_local only after focused route/service tests are green.

- [x] **Step 5: Write the operator runbook**

Create docs/runbooks/publish-acceptance-consumption.md with frontmatter matching current runbooks and these exact sections:

1. trigger conditions and scope;
2. artifact:publish versus artifact:accept/provider:submit;
3. canonical/deprecated request and response;
4. prepared → authorization_failed|acceptance_consumed → published|failed|ambiguous;
5. acceptance error and attempt error table;
6. uncertain consume outcome and acceptance_consumed=true|false|null;
7. no automatic retry/no restore;
8. stale prepared/acceptance_consumed manual correlation;
9. rollback: block both mutation routes before old code;
10. immutable-snapshot, W1-24/W1-25, UI, W1-26, production migration residuals;
11. local commands and exact boundary tags.

The runbook must say that connector-internal exceptions can still collapse to success=false until W1-24 and that completed_local is not live publish evidence.

- [x] **Step 6: Synchronize existing docs without changing historical evidence**

Update:

- backend route auth runbook with artifact:publish separation;
- artifact acceptance lifecycle with consumed_by_resource_id attempt correlation and uncertain-store inspection;
- API reference with strict canonical/deprecated bodies and stable responses;
- runbook index with the new file;
- migration/rollback wording: future upgrade is backup → schema → app; rollback is route block → safe app → optional schema downgrade;
- historical 12/13/14-table evidence remains dated truth; current recovery order remains 14 tables.

Do not mark W1-23 roadmap or AGENTS complete in Task 7.

- [x] **Step 7: Run GREEN governance and live-test collection safety**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_backend_route_auth_contract.py tests/test_backup_production_contract.py tests/test_run_alembic_upgrade.py tests/test_openapi_types_drift_guard.py -q
.venv/bin/python -m pytest tests/test_publish_e2e.py --collect-only -q
~~~

Expected: governance tests pass. Collection succeeds without connector calls; no live test body is printed or executed.

- [x] **Step 8: Inspect the Task 7 diff**

Run git diff --check and search active docs for W1-23 pending, source=human body authorization, metadata.video_path authority, multi-platform publish, or retry advice. Remaining matches must be explicitly historical or deferred-context text, not active instructions.

Implementation note: Task 7 closed after governance-focused RED/GREEN and two independent review loops. The final local evidence is `44` governance tests passed, `12` documentation tests passed, one live test collected without executing its body, scoped Ruff/diff checks clean, and independent specification plus quality verdicts of Critical=0, Important=0, Minor=0. The live gate now locks the exact module marker, four-input authorization predicate, canonical request authority, and no-connector-import boundary; active docs lock all 11 error rows and the durable `distribution.publish` correlation value.

---

### Task 8: Disposable PostgreSQL 18, Full Regression, Independent Review, and State Sync

**Files:**

- Create for explicit local DB gate: tests/test_publish_attempt_pg18.py
- Modify after verification: docs/runbooks/publish-acceptance-consumption.md
- Modify after verification: docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md
- Modify only after durable fact is verified: AGENTS.md

**Interfaces:**

- Consumes all prior task outputs.
- Produces real disposable-PostgreSQL lifecycle/concurrency evidence plus full backend/frontend evidence.
- Upgrades W1-23 to completed_local only if every mandatory gate passes.
- Leaves production migration/deploy, real publish/delivery, immutable snapshot, connector truth, and UI explicitly pending.

- [x] **Step 1: Run the complete focused acceptance suite**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_contracts.py tests/test_publish_attempt_repository.py tests/test_publish_acceptance_outcome.py tests/test_publish_attempt_service.py tests/test_publish_connector_log_safety.py tests/test_publish_acceptance_routes.py tests/test_distribution_publish_guard.py tests/test_artifact_acceptance_contracts.py tests/test_acceptance_record_repository.py tests/test_artifact_acceptance_service.py tests/test_acceptance_records_router.py tests/test_auth_context.py tests/test_scenario_generation_safety_policy.py tests/test_metrics_poller.py tests/test_backup_production_contract.py tests/test_run_alembic_upgrade.py tests/test_backend_route_auth_contract.py tests/test_openapi_types_drift_guard.py -q
~~~

Expected: zero failures/skips caused by W1-23. Record actual counts from fresh output rather than predicting them.

- [x] **Step 2: Add the explicit real-PostgreSQL test**

Create tests/test_publish_attempt_pg18.py with this environment/fixture boundary:

~~~python
from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from src.storage import db

_PG18_DSN = os.environ.get("W1_23_PG18_DSN")

pytestmark = [
    pytest.mark.hermetic_slow,
    pytest.mark.skipif(
        not _PG18_DSN,
        reason="requires explicit disposable W1_23_PG18_DSN",
    ),
]


@dataclass(frozen=True)
class PG18Harness:
    pool: asyncpg.Pool
    tenant_prefix: str


@pytest_asyncio.fixture
async def pg18_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> PG18Harness:
    assert _PG18_DSN is not None
    pool = await asyncpg.create_pool(
        _PG18_DSN,
        min_size=1,
        max_size=24,
    )
    tenant_prefix = "w1-23-pg18-" + uuid4().hex[:12]
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    try:
        yield PG18Harness(pool=pool, tenant_prefix=tenant_prefix)
    finally:
        async with pool.acquire() as connection:
            async with connection.transaction():
                pattern = tenant_prefix + "%"
                await connection.execute(
                    "DELETE FROM publish_logs WHERE tenant_id LIKE $1",
                    pattern,
                )
                await connection.execute(
                    "DELETE FROM acceptance_records WHERE tenant_id LIKE $1",
                    pattern,
                )
                await connection.execute(
                    "DELETE FROM idempotency_records WHERE tenant_id LIKE $1",
                    pattern,
                )
        await pool.close()
~~~

The test module must:

- create an asyncpg pool only from that explicit variable;
- set db._pool and db._pg_available for the test, close only the disposable pool, then let monkeypatch restore the prior globals;
- use PublishAttemptRepository(require_postgres=True);
- create one prepared row, perform every legal CAS, and prove illegal/stale/cross-tenant CAS returns no authority;
- seed one tenant source/acceptance, run 20 concurrent PublishAttemptService calls with injected ready/fake connector, and assert one consume winner, one connector, one terminal connector-bearing attempt, and 19 authorization failures;
- persist no raw DSN, credential, exception text, or absolute path in output;
- delete only rows bearing its generated tenant prefix during teardown, in dependent-row order.

Core final assertion:

~~~python
assert connector_calls == 1
assert statuses.count("published") == 1
assert statuses.count("authorization_failed") == 19
assert acceptance_status == "consumed"
assert acceptance_consumer_resource_id == published_attempt_id
~~~

This test never calls TikTok/Shopify; the connector is an injected fake.

- [x] **Step 3: Start disposable PostgreSQL 18 and verify migration lifecycle**

Use an isolated local container bound to loopback:

~~~bash
docker rm -f ai-video-w1-23-pg18 2>/dev/null || true
docker run --rm -d --name ai-video-w1-23-pg18 -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55439:5432 postgres:18
~~~

Poll `docker exec ai-video-w1-23-pg18 pg_isready -U postgres -d postgres` at most 30 times with one-second intervals; fail if it never reports ready. Create two disposable databases:

~~~bash
docker exec ai-video-w1-23-pg18 createdb -U postgres w1_23_migration
docker exec ai-video-w1-23-pg18 createdb -U postgres w1_23_fresh
~~~

Establish the pre-W1-23 migration database from the repository's frozen pre-W1-22 baseline, then advance it to the approved W1-22 head before applying W1-23:

~~~bash
# Historical local execution used an untracked W1-22 snapshot. It is not a
# current clean-clone command; current migration gates use tracked schema inputs.
cd migrations
DATABASE_URL=postgresql://postgres@127.0.0.1:55439/w1_23_migration ../.venv/bin/python -m alembic stamp d5e6f7a8b9c0
DATABASE_URL=postgresql://postgres@127.0.0.1:55439/w1_23_migration ../.venv/bin/python -m alembic upgrade e8f1a2b3c4d5
DATABASE_URL=postgresql://postgres@127.0.0.1:55439/w1_23_migration ../.venv/bin/python -m alembic upgrade f9a2b3c4d5e6
cd ..
~~~

Verify with psql metadata only:

- single head f9a2b3c4d5e6;
- tenant_id VARCHAR(64), acceptance_id VARCHAR(36), updated_at TIMESTAMPTZ, all nullable;
- idx_publish_logs_tenant_created_at and idx_publish_logs_tenant_acceptance;
- 14 required tables;
- no status constraint or acceptance unique index.

Inspect version, columns, and indexes without row data:

~~~bash
docker exec ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -At -U postgres -d w1_23_migration -c "SELECT version_num FROM alembic_version"
docker exec ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -At -U postgres -d w1_23_migration -c "SELECT column_name || ':' || data_type || ':' || is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='publish_logs' ORDER BY ordinal_position"
docker exec ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -At -U postgres -d w1_23_migration -c "SELECT indexname || ':' || indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='publish_logs' ORDER BY indexname"
~~~

Downgrade and re-upgrade from the required Alembic working directory:

~~~bash
cd migrations
DATABASE_URL=postgresql://postgres@127.0.0.1:55439/w1_23_migration ../.venv/bin/python -m alembic downgrade e8f1a2b3c4d5
cd ..
docker exec ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -At -U postgres -d w1_23_migration -c "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='publish_logs' AND column_name IN ('tenant_id','acceptance_id','updated_at') ORDER BY column_name"
docker exec ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -At -U postgres -d w1_23_migration -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='publish_logs' AND indexname IN ('idx_publish_logs_tenant_created_at','idx_publish_logs_tenant_acceptance') ORDER BY indexname"
cd migrations
DATABASE_URL=postgresql://postgres@127.0.0.1:55439/w1_23_migration ../.venv/bin/python -m alembic upgrade f9a2b3c4d5e6
cd ..
~~~

Expected after downgrade: both metadata queries print nothing; existing rows and all non-W1-23 columns remain. Repeat the three metadata queries after re-upgrade and require exact parity with the first result. Then bootstrap the second database from current fresh-init SQL:

~~~bash
docker exec -i ai-video-w1-23-pg18 psql -v ON_ERROR_STOP=1 -U postgres -d w1_23_fresh < src/storage/migrations/001_init.sql
~~~

Compare the two databases' publish_logs column/index sets and all 14 required table names. Do not compare row data, print connection environment, or touch any non-disposable database.

- [x] **Step 4: Run real PostgreSQL repository and concurrency tests**

Run:

~~~bash
W1_23_PG18_DSN=postgresql://postgres@127.0.0.1:55439/w1_23_migration PYTEST_INCLUDE_HERMETIC_SLOW=1 .venv/bin/python -m pytest tests/test_publish_attempt_pg18.py -m hermetic_slow -q
~~~

Expected: real asyncpg lifecycle and 20-way authority test pass; exact sanitized counts are recorded. Then stop the disposable container and verify it is absent:

~~~bash
docker rm -f ai-video-w1-23-pg18
docker ps -a --filter name=ai-video-w1-23-pg18 --format '{{.Names}}'
~~~

Expected: the final command prints nothing.

- [x] **Step 5: Run full backend quality gate**

Run:

~~~bash
make ci
~~~

Expected: Ruff exits 0 and pytest exits 0. Record exact passed/skipped/deselected counts and warnings. The default run must deselect the hermetic_slow PG18 test and skip all credential-gated external tests.

- [x] **Step 6: Run complete frontend quality gate**

Run:

~~~bash
cd web
npm test -- --run
npm run lint
npx tsc --noEmit
npm run check:api-types
npm run build
~~~

Expected: Vitest, ESLint, TypeScript, OpenAPI drift check, and Next production build all exit 0.

- [x] **Step 7: Run repository hygiene and secret-safe review**

Run:

~~~bash
git diff --check
git status --short
git diff --stat
~~~

Inspect the complete W1-23 manifest without reading .env or DDDD.pem. Run the repository changed-file secret-pattern scan and confirm:

- no API key/token/password/private-key/production DSN value;
- no raw connector error or response body;
- no host absolute artifact path in rows, logs, docs, or fixtures;
- no provider/network call;
- no production database write;
- no accidental unrelated formatting or cleanup.

- [x] **Step 8: Request independent spec, security, concurrency, and migration review**

Provide the approved spec, this plan, complete W1-23 diff, and fresh focused/PG18 evidence to an independent reviewer. Require Critical/Important/Minor classification and explicit checks for:

- consume-store uncertain outcome;
- one connector under concurrency;
- no retry/restore;
- tenant/path authority;
- pre/post-consume persistence failures;
- migration downgrade ownership and lock boundary;
- deprecated route non-authority;
- frontend zero-network;
- evidence ceiling.

Resolve every accepted Critical or Important finding with a new RED/GREEN cycle and rerun every affected gate. A reviewer statement is not accepted without local diff/test verification.

- [x] **Step 9: Synchronize state only from verified evidence**

If and only if all mandatory gates pass:

- mark W1-23 completed_local in the enterprise roadmap;
- update the tracked roadmap and publish-acceptance runbook with exact commands/results and residual boundaries;
- add one concise W1-23 local-closure paragraph to AGENTS.md;
- retain W1-24/W1-25, immutable snapshot, W5 UI, W1-26 live publish, production migration/deploy, delivery, and metrics as pending.

If any gate is unavailable or failing, keep W1-23 in_progress and record the exact blocker; do not upgrade the verdict from partial evidence.

- [x] **Step 10: Final verification after state synchronization**

Rerun:

~~~bash
.venv/bin/python -m pytest tests/test_publish_acceptance_routes.py tests/test_publish_attempt_service.py tests/test_backend_route_auth_contract.py tests/test_backup_production_contract.py tests/test_openapi_types_drift_guard.py -q
cd web
npm run check:api-types
cd ..
git diff --check
~~~

If review corrections changed shared backend/frontend behavior, rerun make ci and the complete frontend gate. The final report may cite only the last complete fresh run.

- [x] **Step 11: Final no-side-effect acceptance statement**

Report:

- actual files changed;
- exact focused/full/PG18/frontend evidence;
- independent review disposition;
- completed_local or precise incomplete state;
- production unchanged;
- provider_call=false;
- live_publish=false;
- no production database write;
- no SSH/deploy/stage/commit/push/PR;
- explicit TOCTOU, connector truth, UI, live publish/delivery, and metrics residuals.

## Specification Traceability

| Approved specification sections | Executable plan coverage |
|---|---|
| §§1-5 problem, scope, authority, permission | Tasks 1, 4, 5 |
| §§6-7 strict HTTP and connector payload | Tasks 1, 4, 5, 6 |
| §§8-11 service order, readiness, artifact/TOCTOU | Tasks 3, 4 |
| §§12-15 persistence, state, errors, concurrency/crash | Tasks 2, 3, 4, 8 |
| §§16-17 legacy and frontend compatibility | Tasks 5, 6, 7 |
| §18 migration/schema parity | Tasks 2, 8 |
| §§19-23 tests, governance, rollout/rollback, completion, deferrals | Tasks 7, 8 |

## Completion Handoff

When Task 8 is green, W1-23 is locally complete but not production-live. The next roadmap choice must be separately approved; the recommended order remains W1-24/W1-25 connector truth before any W1-26 live publish authorization.

Do not stage, commit, push, create a PR, migrate production, use DDDD.pem, SSH, deploy, call a real connector/provider, publish, deliver, or pull live metrics in this handoff.
