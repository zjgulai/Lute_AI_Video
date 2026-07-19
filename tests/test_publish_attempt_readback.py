"""W1-25 tenant-bound attempt and durable receipt readback contracts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.models.publish_attempt import PublishReceiptV1
from src.storage import db as db_module
from src.storage.publish_attempt_repository import (
    PublishAttemptRepository,
    PublishAttemptStoreUnavailable,
)

TENANT_ID = "tenant-readback"
ACCEPTANCE_IDS = (
    "7f947625-2898-4e9e-9e71-dce4309e5f4f",
    "91ec3593-cc3c-42bf-99ee-c98655c5826b",
)
POST_ID = "7512345678901234567"


def _receipt(*, operation_id: str = "v_pub_file_readback_123") -> PublishReceiptV1:
    return PublishReceiptV1.model_validate(
        {
            "schema_version": "publish-receipt.v1",
            "platform": "tiktok",
            "protocol_version": "tiktok-content-posting-v2",
            "completion_scope": "tiktok_direct_post",
            "provider_operation_id": operation_id,
            "provider_resource_id": POST_ID,
            "target_id": None,
            "provider_status": "PUBLISH_COMPLETE",
            "post_id": POST_ID,
            "post_url": f"https://www.tiktok.com/@fixture/video/{POST_ID}",
            "public_visibility_verified": True,
            "observed_at": "2026-07-14T08:00:00Z",
            "verified_by": "video_query",
            "simulated": False,
        }
    )


def _consumed_content(*, resource_id: str) -> dict[str, object]:
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
                f"tenants/{TENANT_ID}/pending_review/{resource_id}/"
                "assemble/final.mp4"
            ),
            "sha256": "a" * 64,
            "size_bytes": 20,
            "kind": "video",
        },
        "metadata": {"title": "Reviewed"},
    }


@pytest.fixture
def readback_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "publish-readback.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_pg_available", False)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


async def _publish(
    repository: PublishAttemptRepository,
    *,
    acceptance_id: str,
    resource_id: str,
    receipt: PublishReceiptV1,
) -> str:
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=acceptance_id,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed"},
    )
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(resource_id=resource_id),
    )
    assert consumed is not None
    published = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="acceptance_consumed",
        new_status="published",
        post_id=receipt.post_id,
        url=receipt.post_url,
        receipt=receipt,
    )
    assert published is not None
    return prepared["id"]


@pytest.mark.asyncio
async def test_attempt_readback_is_tenant_bound(
    readback_db: sqlite3.Connection,
) -> None:
    del readback_db
    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_IDS[0],
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )

    assert await repository.get_by_id(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
    ) == prepared
    assert await repository.get_by_id(
        tenant_id="tenant-other",
        attempt_id=prepared["id"],
    ) is None


@pytest.mark.asyncio
async def test_exact_published_receipt_lookup_is_tenant_platform_and_post_bound(
    readback_db: sqlite3.Connection,
) -> None:
    del readback_db
    repository = PublishAttemptRepository(require_postgres=False)
    receipt = _receipt()
    await _publish(
        repository,
        acceptance_id=ACCEPTANCE_IDS[0],
        resource_id="s2_readback_one",
        receipt=receipt,
    )

    assert await repository.get_published_receipt_by_post_id(
        tenant_id=TENANT_ID,
        platform="tiktok",
        post_id=POST_ID,
    ) == receipt
    assert await repository.get_published_receipt_by_post_id(
        tenant_id="tenant-other",
        platform="tiktok",
        post_id=POST_ID,
    ) is None
    assert await repository.get_published_receipt_by_post_id(
        tenant_id=TENANT_ID,
        platform="shopify",
        post_id=POST_ID,
    ) is None
    assert await repository.get_published_receipt_by_post_id(
        tenant_id=TENANT_ID,
        platform="tiktok",
        post_id="7512345678901234568",
    ) is None


@pytest.mark.asyncio
async def test_contradictory_duplicate_receipts_fail_closed(
    readback_db: sqlite3.Connection,
) -> None:
    del readback_db
    repository = PublishAttemptRepository(require_postgres=False)
    await _publish(
        repository,
        acceptance_id=ACCEPTANCE_IDS[0],
        resource_id="s2_readback_first",
        receipt=_receipt(operation_id="v_pub_file_readback_first"),
    )
    await _publish(
        repository,
        acceptance_id=ACCEPTANCE_IDS[1],
        resource_id="s2_readback_second",
        receipt=_receipt(operation_id="v_pub_file_readback_second"),
    )

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.get_published_receipt_by_post_id(
            tenant_id=TENANT_ID,
            platform="tiktok",
            post_id=POST_ID,
        )
