"""Disposable PostgreSQL 18 lifecycle and publish-authority checks for W1-25.

The module is opt-in and only connects to the explicit ``W1_23_PG18_DSN``.
The inherited variable name is retained for the guarded local lane. Tests use
an injected fake publisher; no platform connector or provider is called.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

# Read the immutable pytest-start snapshot before imports that can load src.config.
_PG18_DSN: str | None = getattr(
    importlib.import_module("tests.conftest"),
    "W1_23_PG18_DSN_AT_PYTEST_START",
)

from src.connectors.registry import PublishConnectorReadiness
from src.models.acceptance import AcceptanceCreateRequest
from src.models.publish_attempt import PublishAttemptRequest, PublishReceiptV1
from src.routers._deps import ApiKeyType, AuthContext
from src.services.artifact_acceptance import ArtifactAcceptanceService
from src.services.publish_attempt import PublishAttemptError, PublishAttemptService
from src.storage import db
from src.storage.acceptance_repository import AcceptanceRecordRepository
from src.storage.idempotency_repository import SubmissionIdempotencyRepository
from src.storage.publish_attempt_repository import PublishAttemptRepository

_PG18_DATABASE = "w1_23_migration"
_PG18_HOST = "127.0.0.1"
_PG18_PORT = 55439
_PG18_USERNAME = "postgres"
_PG18_LANE_ERROR = "disposable PostgreSQL 18 lane is not authorized"


def _published_receipt() -> PublishReceiptV1:
    return PublishReceiptV1.model_validate(
        {
            "schema_version": "publish-receipt.v1",
            "platform": "tiktok",
            "protocol_version": "tiktok-content-posting-v2",
            "completion_scope": "tiktok_direct_post",
            "provider_operation_id": "v_pub_file_pg18_fixture",
            "provider_resource_id": "7512345678901234567",
            "target_id": None,
            "provider_status": "PUBLISH_COMPLETE",
            "post_id": "7512345678901234567",
            "post_url": (
                "https://www.tiktok.com/@pg18_fixture/"
                "video/7512345678901234567"
            ),
            "public_visibility_verified": True,
            "observed_at": "2026-07-14T08:00:00Z",
            "verified_by": "video_query",
            "simulated": False,
        }
    )


def _validate_pg18_dsn(dsn: str | None) -> None:
    if not isinstance(dsn, str) or not dsn or dsn != dsn.strip():
        raise ValueError(_PG18_LANE_ERROR)
    try:
        parsed = urlsplit(dsn)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError(_PG18_LANE_ERROR) from None
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != _PG18_HOST
        or port != _PG18_PORT
        or parsed.path != f"/{_PG18_DATABASE}"
        or parsed.username != _PG18_USERNAME
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(_PG18_LANE_ERROR)


def _validate_pg18_server_identity(
    database_name: object,
    server_version_num: object,
) -> None:
    version_text = str(server_version_num)
    if (
        database_name != _PG18_DATABASE
        or not version_text.isascii()
        or not version_text.isdigit()
        or int(version_text) // 10_000 != 18
    ):
        raise ValueError(_PG18_LANE_ERROR)


async def _create_verified_pg18_pool(dsn: str | None) -> asyncpg.Pool:
    _validate_pg18_dsn(dsn)
    assert dsn is not None
    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=24,
        )
    except Exception:
        raise RuntimeError(_PG18_LANE_ERROR) from None
    try:
        async with pool.acquire() as connection:
            identity = await connection.fetchrow(
                """
                SELECT current_database() AS database_name,
                       current_setting('server_version_num') AS server_version_num
                """
            )
        if identity is None:
            raise ValueError(_PG18_LANE_ERROR)
        _validate_pg18_server_identity(
            identity["database_name"],
            identity["server_version_num"],
        )
    except Exception:
        try:
            await pool.close()
        finally:
            raise RuntimeError(_PG18_LANE_ERROR) from None
    return pool

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
    pool = await _create_verified_pg18_pool(_PG18_DSN)
    tenant_prefix = "w1-23-pg18-" + uuid4().hex[:12]
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    try:
        yield PG18Harness(pool=pool, tenant_prefix=tenant_prefix)
    finally:
        try:
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
        finally:
            await pool.close()


def _consumed_content(*, tenant_id: str, resource_id: str) -> dict[str, Any]:
    return {
        "schema_version": "publish-attempt.v1",
        "route_kind": "canonical",
        "source": {
            "resource_type": "scenario",
            "resource_id": resource_id,
            "scenario": "s2",
        },
        "artifact": {
            "path": (
                f"tenants/{tenant_id}/pending_review/{resource_id}/"
                "assemble/final.mp4"
            ),
            "sha256": "a" * 64,
            "size_bytes": 23,
            "kind": "video",
        },
        "metadata": {"title": "PG18 reviewed publish"},
    }


async def _new_prepared(
    repository: PublishAttemptRepository,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    return await repository.create_prepared(
        tenant_id=tenant_id,
        acceptance_id=str(uuid4()),
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "PG18 reviewed publish"},
    )


@pytest.mark.asyncio
async def test_real_pg18_publish_attempt_repository_cas_lifecycle(
    pg18_harness: PG18Harness,
    tmp_path: Path,
) -> None:
    tenant_id = pg18_harness.tenant_prefix + "-cas"
    repository = PublishAttemptRepository(require_postgres=True)
    content = _consumed_content(
        tenant_id=tenant_id,
        resource_id="s2-pg18-cas",
    )

    authorization_failed = await _new_prepared(repository, tenant_id=tenant_id)
    transitioned = await repository.transition(
        tenant_id=tenant_id,
        attempt_id=authorization_failed["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    )
    assert transitioned is not None
    assert transitioned["status"] == "authorization_failed"
    assert await repository.transition(
        tenant_id=tenant_id,
        attempt_id=authorization_failed["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    ) is None

    published = await _new_prepared(repository, tenant_id=tenant_id)
    prepared_content = published["content"]
    route_mismatch = dict(content)
    route_mismatch["route_kind"] = "legacy_adapter"
    with pytest.raises(ValueError, match="prepared content authority is immutable"):
        await repository.transition(
            tenant_id=tenant_id,
            attempt_id=published["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=route_mismatch,
        )
    unchanged = await repository.get_by_id(
        tenant_id=tenant_id,
        attempt_id=published["id"],
    )
    assert unchanged is not None
    assert unchanged["status"] == "prepared"
    assert unchanged["content"] == prepared_content

    metadata_mismatch = dict(content)
    metadata_mismatch["metadata"] = {"title": "Unauthorized replacement"}
    with pytest.raises(ValueError, match="prepared content authority is immutable"):
        await repository.transition(
            tenant_id=tenant_id,
            attempt_id=published["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=metadata_mismatch,
        )
    unchanged = await repository.get_by_id(
        tenant_id=tenant_id,
        attempt_id=published["id"],
    )
    assert unchanged is not None
    assert unchanged["status"] == "prepared"
    assert unchanged["content"] == prepared_content

    consumed = await repository.transition(
        tenant_id=tenant_id,
        attempt_id=published["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=content,
    )
    assert consumed is not None
    assert consumed["status"] == "acceptance_consumed"
    consumed_artifact_path = consumed["content"]["artifact"]["path"]
    assert consumed_artifact_path == content["artifact"]["path"]
    assert PurePosixPath(consumed_artifact_path).is_absolute() is False
    assert str(tmp_path) not in consumed_artifact_path
    terminal = await repository.transition(
        tenant_id=tenant_id,
        attempt_id=published["id"],
        expected_status="acceptance_consumed",
        new_status="published",
        post_id=_published_receipt().post_id,
        url=_published_receipt().post_url,
        receipt=_published_receipt(),
    )
    assert terminal is not None
    assert terminal["status"] == "published"
    assert terminal["content"]["artifact"]["path"] == consumed_artifact_path
    assert PurePosixPath(
        terminal["content"]["artifact"]["path"]
    ).is_absolute() is False
    assert terminal["receipt"] == _published_receipt().model_dump(mode="json")
    durable_receipt = await repository.get_published_receipt_by_post_id(
        tenant_id=tenant_id,
        platform="tiktok",
        post_id="7512345678901234567",
    )
    assert durable_receipt == _published_receipt()

    preflight_failed = await _new_prepared(repository, tenant_id=tenant_id)
    preflight_terminal = await repository.transition(
        tenant_id=tenant_id,
        attempt_id=preflight_failed["id"],
        expected_status="prepared",
        new_status="preflight_failed",
        error_code="publish_preflight_rejected",
    )
    assert preflight_terminal is not None
    assert preflight_terminal["status"] == "preflight_failed"
    assert preflight_terminal["receipt"] is None

    for status, error_code in (
        ("failed", "publish_connector_failed"),
        ("failed", "publish_connector_not_ready_after_consume"),
        ("failed", "publish_connector_simulated"),
        ("ambiguous", "publish_outcome_ambiguous"),
    ):
        prepared = await _new_prepared(repository, tenant_id=tenant_id)
        assert await repository.transition(
            tenant_id=tenant_id,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=content,
        ) is not None
        branch = await repository.transition(
            tenant_id=tenant_id,
            attempt_id=prepared["id"],
            expected_status="acceptance_consumed",
            new_status=status,
            error_code=error_code,
        )
        assert branch is not None
        assert branch["status"] == status
        assert branch["content"]["artifact"]["path"] == consumed_artifact_path
        assert PurePosixPath(
            branch["content"]["artifact"]["path"]
        ).is_absolute() is False

    cross_tenant = await _new_prepared(repository, tenant_id=tenant_id)
    other_tenant = pg18_harness.tenant_prefix + "-other"
    assert await repository.get_by_id(
        tenant_id=other_tenant,
        attempt_id=cross_tenant["id"],
    ) is None
    assert await repository.transition(
        tenant_id=other_tenant,
        attempt_id=cross_tenant["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    ) is None
    assert await repository.transition(
        tenant_id=tenant_id,
        attempt_id=cross_tenant["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    ) is not None

    illegal = await _new_prepared(repository, tenant_id=tenant_id)
    with pytest.raises(ValueError, match="attempt transition is invalid"):
        await repository.transition(
            tenant_id=tenant_id,
            attempt_id=illegal["id"],
            expected_status="prepared",
            new_status="published",
        )
    assert await repository.transition(
        tenant_id=tenant_id,
        attempt_id=illegal["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    ) is not None


async def _seed_source(
    harness: PG18Harness,
    *,
    tenant_id: str,
    resource_id: str,
    artifact_path: str,
) -> None:
    snapshot = {
        "full_media_success": True,
        "is_stub": False,
        "pipeline_degraded": False,
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
        "final_artifact_path": artifact_path,
    }
    async with harness.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO idempotency_records (
                id, tenant_id, key_hash, fingerprint_version, request_hash,
                operation, scenario, resource_type, resource_id, record_status,
                stage, effective_policy_version, response_status, response_body,
                result_snapshot, completed_at
            ) VALUES (
                $1, $2, $3, 'submit-fingerprint.v1', $4,
                'scenario.submit', 's2', 'scenario', $5, 'completed',
                'completed', 'generation-policy.v1', 200, '{}'::jsonb,
                $6::jsonb, NOW()
            )
            """,
            str(uuid4()),
            tenant_id,
            hashlib.sha256(f"source-key:{tenant_id}".encode()).hexdigest(),
            hashlib.sha256(f"source-request:{tenant_id}".encode()).hexdigest(),
            resource_id,
            json.dumps(snapshot, sort_keys=True),
        )


@pytest.mark.asyncio
async def test_real_pg18_publish_service_has_one_consume_and_connector_winner(
    pg18_harness: PG18Harness,
    tmp_path: Path,
) -> None:
    tenant_id = pg18_harness.tenant_prefix + "-service"
    resource_id = "s2-pg18-concurrency"
    artifact_path = (
        f"tenants/{tenant_id}/pending_review/{resource_id}/assemble/final.mp4"
    )
    output_dir = tmp_path / "output"
    artifact = output_dir / artifact_path
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"w1-23-pg18-reviewed-video")
    await _seed_source(
        pg18_harness,
        tenant_id=tenant_id,
        resource_id=resource_id,
        artifact_path=artifact_path,
    )

    acceptance_service = ArtifactAcceptanceService(
        AcceptanceRecordRepository(require_postgres=True),
        SubmissionIdempotencyRepository(require_postgres=True),
        output_dir=output_dir,
    )
    reviewer_auth = AuthContext(
        tenant_id=tenant_id,
        permissions=frozenset({"artifact:accept"}),
        key_type=ApiKeyType.TENANT,
        key_id="pg18-reviewer",
    )
    acceptance, replayed = await acceptance_service.create(
        auth=reviewer_auth,
        raw_key="pg18-acceptance-" + uuid4().hex,
        request=AcceptanceCreateRequest.model_validate(
            {
                "source_resource_type": "scenario",
                "source_resource_id": resource_id,
                "artifact_path": artifact_path,
                "decision": "accepted",
                "review_notes": "Reviewed disposable PG18 fixture.",
                "expires_in_seconds": 3600,
            }
        ),
    )
    assert replayed is False
    assert acceptance.status == "available"

    connector_calls: list[str] = []

    def ready(platform: str) -> PublishConnectorReadiness:
        assert platform == "tiktok"
        return PublishConnectorReadiness(
            platform="tiktok",
            ready=True,
            reason=None,
        )

    async def fake_publisher(
        platform: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        assert platform == "tiktok"
        assert content["video_path"] == str(artifact)
        connector_calls.append(platform)
        await asyncio.sleep(0)
        return {
            "success": True,
            "simulated": False,
            "platform": platform,
            "status": "published",
            "post_id": _published_receipt().post_id,
            "url": _published_receipt().post_url,
            "receipt": _published_receipt().model_dump(mode="json"),
        }

    service = PublishAttemptService(
        PublishAttemptRepository(require_postgres=True),
        acceptance_service,
        output_dir=output_dir,
        readiness_inspector=ready,
        publisher=fake_publisher,
    )
    publisher_auth = AuthContext(
        tenant_id=tenant_id,
        permissions=frozenset({"artifact:publish"}),
        key_type=ApiKeyType.TENANT,
        key_id="pg18-publisher",
    )
    request = PublishAttemptRequest.model_validate(
        {
            "acceptance_id": acceptance.acceptance_id,
            "platform": "tiktok",
            "platform_options": {
                "platform": "tiktok",
                "privacy_level": "SELF_ONLY",
                "disable_comment": True,
                "disable_duet": True,
                "disable_stitch": True,
                "brand_content_toggle": False,
                "brand_organic_toggle": False,
            },
            "metadata": {
                "title": "PG18 reviewed publish",
                "description": "Disposable PostgreSQL concurrency fixture",
            },
        }
    )

    results = await asyncio.gather(
        *(
            service.execute(
                auth=publisher_auth,
                request=request,
                route_kind="canonical",
            )
            for _ in range(20)
        ),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert all(
        isinstance(result, PublishAttemptError)
        and result.code == "acceptance_not_available"
        for result in failures
    )

    async with pg18_harness.pool.acquire() as connection:
        attempts = await connection.fetch(
            """
            SELECT id::text, status, post_id, url, receipt, content
            FROM publish_logs
            WHERE tenant_id = $1
            ORDER BY created_at, id
            """,
            tenant_id,
        )
        consumed = await connection.fetchrow(
            """
            SELECT record_status, consumed_by_operation,
                   consumed_by_resource_id
            FROM acceptance_records
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id,
            acceptance.acceptance_id,
        )

    statuses = [row["status"] for row in attempts]
    published_rows = [row for row in attempts if row["status"] == "published"]
    assert len(attempts) == 20
    assert connector_calls == ["tiktok"]
    assert statuses.count("published") == 1
    assert statuses.count("authorization_failed") == 19
    assert len(published_rows) == 1
    assert published_rows[0]["post_id"] == _published_receipt().post_id
    assert published_rows[0]["url"] == _published_receipt().post_url
    published_receipt_raw = published_rows[0]["receipt"]
    published_receipt = (
        json.loads(published_receipt_raw)
        if isinstance(published_receipt_raw, str)
        else dict(published_receipt_raw)
    )
    assert published_receipt == _published_receipt().model_dump(mode="json")
    published_content_raw = published_rows[0]["content"]
    published_content = (
        json.loads(published_content_raw)
        if isinstance(published_content_raw, str)
        else dict(published_content_raw)
    )
    published_artifact_path = published_content["artifact"]["path"]
    assert published_artifact_path == artifact_path
    assert PurePosixPath(published_artifact_path).is_absolute() is False
    assert str(tmp_path) not in published_artifact_path
    assert consumed is not None
    assert consumed["record_status"] == "consumed"
    assert consumed["consumed_by_operation"] == "distribution.publish"
    assert consumed["consumed_by_resource_id"] == published_rows[0]["id"]
