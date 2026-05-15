"""Tests for BrandPackageRepository + InfluencerRepository (TODO-16 PR1).

Exercises the existing skeleton repositories against SQLite fallback to
prove the inherited BaseRepository CRUD works for these table shapes.

Does NOT modify src/api_assets.py — that cutover is deferred per
docs/architecture/api-assets-pg-cutover-2026-05-15.md.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import src.storage.db as db_module
from src.storage.db import _create_sqlite_tables
from src.storage.repository import BrandPackageRepository, InfluencerRepository


def _maybe_json(v):
    """SQLite serializes JSONB to TEXT; PG returns dict directly. Normalize."""
    return json.loads(v) if isinstance(v, str) else v


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """Fresh SQLite DB per test, check_same_thread=False for async/to_thread compat.

    BaseRepository.create() uses asyncio.to_thread() which executes the
    SQLite query in a worker thread distinct from the one that opened the
    connection. Default sqlite3.connect raises ProgrammingError under that
    pattern. Tests must connect with check_same_thread=False to mirror what
    the running asgi server does in practice.

    Critical: src/storage/repository.py imports `get_pool` and `get_sqlite_conn`
    via `from .db import get_pool, get_sqlite_conn`, which creates module-local
    bindings. Monkeypatching only db_module.get_pool is NOT enough — the cached
    repository.py reference still points to the original. We patch BOTH.
    """
    db_path = tmp_path / "test_brand_influencer.db"

    async def _no_pool():
        return None

    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    import src.storage.repository as repo_module
    monkeypatch.setattr(repo_module, "get_pool", _no_pool)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(db_module, "_sqlite_conn", conn)
    _create_sqlite_tables()

    yield db_path

    conn.close()


class TestBrandPackageRepository:
    @pytest.mark.asyncio
    async def test_create_then_get_by_id(self, sqlite_db):
        repo = BrandPackageRepository()
        created = await repo.create({
            "name": "Momcozy",
            "brand_guidelines": {"tone": "warm", "colors": ["#FF6B6B"]},
            "assets": ["asset-1", "asset-2"],
        })
        assert created["id"]
        assert created["name"] == "Momcozy"
        loaded = await repo.get_by_id(created["id"])
        assert loaded is not None
        assert loaded["name"] == "Momcozy"
        assert _maybe_json(loaded["brand_guidelines"])["tone"] == "warm"
        assert _maybe_json(loaded["assets"]) == ["asset-1", "asset-2"]

    @pytest.mark.asyncio
    async def test_update_brand_guidelines(self, sqlite_db):
        repo = BrandPackageRepository()
        created = await repo.create({
            "name": "TestBrand",
            "brand_guidelines": {"tone": "casual"},
            "assets": [],
        })
        updated = await repo.update(created["id"], {
            "brand_guidelines": {"tone": "professional", "tagline": "Built for moms"},
        })
        assert updated is not None
        guidelines = _maybe_json(updated["brand_guidelines"])
        assert guidelines["tone"] == "professional"
        assert guidelines["tagline"] == "Built for moms"

    @pytest.mark.asyncio
    async def test_delete_brand_package(self, sqlite_db):
        repo = BrandPackageRepository()
        created = await repo.create({"name": "ToDelete", "brand_guidelines": {}, "assets": []})
        deleted = await repo.delete(created["id"])
        assert deleted is True
        loaded = await repo.get_by_id(created["id"])
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_all_returns_created_packages(self, sqlite_db):
        repo = BrandPackageRepository()
        await repo.create({"name": "Brand1", "brand_guidelines": {}, "assets": []})
        await repo.create({"name": "Brand2", "brand_guidelines": {}, "assets": []})
        await repo.create({"name": "Brand3", "brand_guidelines": {}, "assets": []})
        results = await repo.list_all(limit=10)
        names = sorted(r["name"] for r in results)
        assert names == ["Brand1", "Brand2", "Brand3"]


class TestInfluencerRepository:
    @pytest.mark.asyncio
    async def test_create_then_get_by_id(self, sqlite_db):
        repo = InfluencerRepository()
        created = await repo.create({
            "name": "Jane Doe",
            "platform": "tiktok",
            "profile": {"followers": 50000, "niche": "parenting"},
            "contact_info": {"email": "jane@example.com"},
        })
        assert created["id"]
        loaded = await repo.get_by_id(created["id"])
        assert loaded is not None
        assert loaded["name"] == "Jane Doe"
        assert loaded["platform"] == "tiktok"
        assert _maybe_json(loaded["profile"])["followers"] == 50000

    @pytest.mark.asyncio
    async def test_get_by_field_platform(self, sqlite_db):
        repo = InfluencerRepository()
        await repo.create({
            "name": "Tina",
            "platform": "instagram",
            "profile": {},
            "contact_info": {},
        })
        await repo.create({
            "name": "Bob",
            "platform": "tiktok",
            "profile": {},
            "contact_info": {},
        })
        found_ig = await repo.get_by_field("platform", "instagram")
        assert found_ig is not None
        assert found_ig["name"] == "Tina"

    @pytest.mark.asyncio
    async def test_profile_jsonb_roundtrip(self, sqlite_db):
        repo = InfluencerRepository()
        nested_profile = {
            "style": {"hook_type": "pain_point", "speech_speed": 2.4},
            "stats": {"avg_engagement": 0.082, "post_count": 412},
            "tags": ["parenting", "lifestyle"],
        }
        created = await repo.create({
            "name": "ComplexProfile",
            "platform": "tiktok",
            "profile": nested_profile,
            "contact_info": {},
        })
        loaded = await repo.get_by_id(created["id"])
        assert loaded is not None
        assert _maybe_json(loaded["profile"]) == nested_profile
