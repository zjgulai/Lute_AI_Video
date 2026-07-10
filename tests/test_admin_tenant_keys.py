"""Regression tests for the Admin tenant key lifecycle contract."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _pool_for(connection: MagicMock) -> MagicMock:
    @asynccontextmanager
    async def acquire():
        yield connection

    pool = MagicMock()
    pool.acquire = acquire
    return pool


@pytest.mark.asyncio
async def test_get_tenant_reads_api_key_description_as_label() -> None:
    from src.routers.admin.tenants import get_tenant

    now = datetime.now(UTC)
    connection = MagicMock()
    connection.fetchrow = AsyncMock(return_value={
        "id": "tenant-uuid",
        "tenant_id": "momcozy-marketing",
        "display_name": "Marketing",
        "contact_email": "",
        "status": "active",
        "created_at": now,
    })
    connection.fetch = AsyncMock(side_effect=[
        [{
            "id": "key-uuid",
            "key_hash": "a" * 64,
            "description": "campaign owner",
            "created_at": now,
            "expires_at": now - timedelta(days=1),
            "revoked_at": now,
            "last_used_at": None,
        }],
        [],
    ])

    async def get_pool():
        return _pool_for(connection)

    with patch("src.storage.db.get_pool", get_pool):
        result = await get_tenant("momcozy-marketing", admin_id="admin")

    key_query = connection.fetch.await_args_list[0].args[0]
    assert "description" in key_query
    assert " label," not in key_query
    assert result["keys"][0]["label"] == "campaign owner"
    assert result["keys"][0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_create_api_key_persists_expiry_and_defaults_to_90_days() -> None:
    from src.routers.admin.tenants import create_api_key

    now = datetime.now(UTC)
    inserted_expiry = (now + timedelta(days=90)).replace(tzinfo=None)
    inserted_row = {
        "id": "key-uuid",
        "created_at": now,
        "expires_at": inserted_expiry,
    }
    connection = MagicMock()
    connection.fetchrow = AsyncMock(side_effect=[
        {"tenant_id": "momcozy-marketing", "status": "active"},
        inserted_row,
    ])
    request = MagicMock()
    request.json = AsyncMock(return_value={"label": "rotation replacement"})

    async def get_pool():
        return _pool_for(connection)

    with patch("src.storage.db.get_pool", get_pool):
        result = await create_api_key(
            "momcozy-marketing",
            request,
            admin_id="admin",
            _csrf=None,
        )

    insert_call = connection.fetchrow.await_args_list[1]
    assert "expires_at" in insert_call.args[0]
    persisted_expiry = insert_call.args[-1]
    assert isinstance(persisted_expiry, datetime)
    assert persisted_expiry.tzinfo is None
    assert (
        timedelta(days=89)
        < persisted_expiry - now.replace(tzinfo=None)
        < timedelta(days=91)
    )
    assert result["expires_at"] == inserted_expiry.replace(tzinfo=UTC).isoformat()


@pytest.mark.asyncio
async def test_create_api_key_rejects_non_string_label() -> None:
    from src.routers.admin.tenants import create_api_key

    request = MagicMock()
    request.json = AsyncMock(return_value={"label": 123})

    with pytest.raises(HTTPException) as error:
        await create_api_key(
            "momcozy-marketing",
            request,
            admin_id="admin",
            _csrf=None,
        )

    assert error.value.status_code == 422
