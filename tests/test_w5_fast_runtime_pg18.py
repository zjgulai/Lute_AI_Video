"""Disposable PostgreSQL 18 proof for W5 activation consumption."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest

from src.storage import db
from src.storage.idempotency_repository import SubmissionIdempotencyRepository

_DSN = os.getenv("W5_FAST_PG18_DSN")
_EXPECTED_DSN = (
    "postgresql://postgres@127.0.0.1:55441/ai_video_bootstrap"
)


def _validate_dsn() -> str:
    if _DSN != _EXPECTED_DSN:
        raise ValueError("disposable W5 PostgreSQL 18 lane is not authorized")
    parsed = urlsplit(_DSN)
    if parsed.password or parsed.query or parsed.fragment:
        raise ValueError("disposable W5 PostgreSQL 18 lane is not authorized")
    return _DSN


@pytest.mark.hermetic_slow
@pytest.mark.skipif(not _DSN, reason="requires explicit disposable W5_FAST_PG18_DSN")
@pytest.mark.asyncio
async def test_pg18_activation_reference_allows_one_owner_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = _validate_dsn()
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    tenant = "w5-fast-pg18-" + uuid4().hex[:12]
    activation_ref = "w5fastact:" + uuid4().hex
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    repository = SubmissionIdempotencyRepository(require_postgres=True)

    async def claim(key_hash: str, resource_id: str):
        return await repository.claim(
            tenant_id=tenant,
            key_hash=key_hash,
            trusted_authorization_ref=activation_ref,
            fingerprint_version="submit-fingerprint.v1",
            request_hash="b" * 64,
            operation="fast.submit",
            scenario="fast",
            resource_type="fast",
            resource_id=resource_id,
            effective_policy_version="generation-safety.v2",
            response_status=200,
            response_body={"status": "reserved"},
            owner_instance_id="w5-pg18-fixture",
            lease_seconds=120,
        )

    try:
        first, second = await asyncio.gather(
            claim("a" * 64, "fast_pg18_first"),
            claim("c" * 64, "fast_pg18_second"),
        )
        assert sorted((first.outcome, second.outcome)) == [
            "authorization_conflict",
            "owner",
        ]
        async with pool.acquire() as connection:
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM idempotency_records "
                "WHERE tenant_id = $1 AND trusted_authorization_ref = $2",
                tenant,
                activation_ref,
            )
        assert count == 1
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM idempotency_records WHERE tenant_id = $1",
                tenant,
            )
        await pool.close()
