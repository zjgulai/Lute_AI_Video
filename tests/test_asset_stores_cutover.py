from __future__ import annotations

import sqlite3

import pytest

import src.storage.db as db_module
from src.models.brand import BrandAssetPackage
from src.models.influencer import InfluencerProfile
from src.storage.asset_stores import (
    BrandPackageStore,
    InfluencerStore,
    _pack_brand_row,
    _pack_influencer_row,
    _pg_enabled,
    _unpack_brand_row,
    _unpack_influencer_row,
)
from src.storage.db import _create_sqlite_tables


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_d12_assets.db"

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


def _brand(pid: str = "BPKG-T1", name: str = "Acme") -> BrandAssetPackage:
    return BrandAssetPackage(
        package_id=pid,
        brand_name=name,
        forbidden_content=["claim:cure"],
    )


def _infl(iid: str = "INFL-T1", name: str = "Jane") -> InfluencerProfile:
    return InfluencerProfile(
        influencer_id=iid,
        name=name,
        handle="@jane",
        platforms=["tiktok", "instagram"],
        style_tags=["unboxing", "review"],
    )


def test_pg_enabled_default_off(monkeypatch):
    monkeypatch.delenv("BRAND_PACKAGE_USE_PG", raising=False)
    assert _pg_enabled() is False


@pytest.mark.parametrize("v,expected", [("0", False), ("1", True), ("true", True), ("yes", True), ("no", False)])
def test_pg_enabled_env_parsing(monkeypatch, v, expected):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", v)
    assert _pg_enabled() is expected


def test_pack_unpack_brand_roundtrip():
    package = _brand(pid="BPKG-RT", name="Round")
    row = _pack_brand_row(package)
    assert row["id"] == "BPKG-RT"
    assert row["name"] == "Round"
    assert isinstance(row["brand_guidelines"], dict)

    restored = _unpack_brand_row(row)
    assert restored.package_id == "BPKG-RT"
    assert restored.brand_name == "Round"
    assert restored.forbidden_content == ["claim:cure"]


def test_pack_unpack_influencer_roundtrip():
    profile = _infl(iid="INFL-RT", name="Round")
    row = _pack_influencer_row(profile)
    assert row["id"] == "INFL-RT"
    assert row["name"] == "Round"
    assert row["platform"] == "tiktok"
    assert isinstance(row["profile"], dict)

    restored = _unpack_influencer_row(row)
    assert restored.influencer_id == "INFL-RT"
    assert restored.handle == "@jane"
    assert restored.platforms == ["tiktok", "instagram"]


def test_pack_influencer_with_no_platforms_emits_empty_string():
    profile = InfluencerProfile(influencer_id="INFL-X", name="NoPlat")
    row = _pack_influencer_row(profile)
    assert row["platform"] == ""


def test_unpack_brand_handles_string_jsonb():
    row = {"id": "BPKG-S", "name": "Str", "brand_guidelines": '{"package_id": "BPKG-S", "brand_name": "Str", "forbidden_content": []}'}
    restored = _unpack_brand_row(row)
    assert restored.package_id == "BPKG-S"


def test_unpack_brand_handles_invalid_json_string():
    row = {"id": "BPKG-INV", "name": "Inv", "brand_guidelines": "{not valid json"}
    restored = _unpack_brand_row(row)
    assert restored.package_id == "BPKG-INV"
    assert restored.brand_name == "Inv"


@pytest.mark.asyncio
async def test_brand_store_writes_to_dict_when_flag_off(monkeypatch):
    monkeypatch.delenv("BRAND_PACKAGE_USE_PG", raising=False)
    memory: dict[str, BrandAssetPackage] = {}
    store = BrandPackageStore(memory)
    package = _brand()
    await store.create(package)
    assert "BPKG-T1" in memory
    assert memory["BPKG-T1"].brand_name == "Acme"


@pytest.mark.asyncio
async def test_brand_store_get_returns_none_for_missing(monkeypatch):
    monkeypatch.delenv("BRAND_PACKAGE_USE_PG", raising=False)
    store = BrandPackageStore({})
    assert await store.get("BPKG-MISSING") is None


@pytest.mark.asyncio
async def test_brand_store_pg_path_writes_to_pg_when_flag_on(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    memory: dict[str, BrandAssetPackage] = {}
    store = BrandPackageStore(memory)
    package = _brand(pid="BPKG-PG", name="PGOnly")
    await store.create(package)
    assert "BPKG-PG" not in memory
    fetched = await store.get("BPKG-PG")
    assert fetched is not None
    assert fetched.brand_name == "PGOnly"


@pytest.mark.asyncio
async def test_brand_store_list_all_pg(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    store = BrandPackageStore({})
    await store.create(_brand(pid="BPKG-A", name="A"))
    await store.create(_brand(pid="BPKG-B", name="B"))
    listed = await store.list_all()
    names = {p.brand_name for p in listed}
    assert {"A", "B"} <= names


@pytest.mark.asyncio
async def test_brand_store_delete_pg(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    store = BrandPackageStore({})
    await store.create(_brand(pid="BPKG-D"))
    assert await store.delete("BPKG-D") is True
    assert await store.get("BPKG-D") is None


@pytest.mark.asyncio
async def test_brand_store_pg_failure_falls_back_to_dict(monkeypatch):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    memory: dict[str, BrandAssetPackage] = {}
    store = BrandPackageStore(memory)

    async def _broken_create(self, data):
        raise RuntimeError("PG offline")

    from src.storage import repository as repo_module
    monkeypatch.setattr(repo_module.BaseRepository, "create", _broken_create, raising=True)
    package = _brand(pid="BPKG-FB")
    await store.create(package)
    assert "BPKG-FB" in memory


@pytest.mark.asyncio
async def test_influencer_store_create_get_pg(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    store = InfluencerStore({})
    profile = _infl(iid="INFL-PG", name="PGJane")
    await store.create(profile)
    fetched = await store.get("INFL-PG")
    assert fetched is not None
    assert fetched.name == "PGJane"
    assert fetched.platforms == ["tiktok", "instagram"]


@pytest.mark.asyncio
async def test_influencer_store_update_pg(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    store = InfluencerStore({})
    profile = _infl(iid="INFL-U", name="Before")
    await store.create(profile)
    profile.name = "After"
    await store.update(profile)
    fetched = await store.get("INFL-U")
    assert fetched is not None
    assert fetched.name == "After"


@pytest.mark.asyncio
async def test_influencer_store_delete_pg(monkeypatch, sqlite_db):
    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    store = InfluencerStore({})
    await store.create(_infl(iid="INFL-D"))
    assert await store.delete("INFL-D") is True
    assert await store.get("INFL-D") is None


@pytest.mark.asyncio
async def test_influencer_store_dict_path_when_flag_off(monkeypatch):
    monkeypatch.delenv("BRAND_PACKAGE_USE_PG", raising=False)
    memory: dict[str, InfluencerProfile] = {}
    store = InfluencerStore(memory)
    profile = _infl(iid="INFL-DICT")
    await store.create(profile)
    assert "INFL-DICT" in memory
    fetched = await store.get("INFL-DICT")
    assert fetched is profile


@pytest.mark.asyncio
async def test_dict_entries_survive_flag_flip_via_fallback(monkeypatch, sqlite_db):
    monkeypatch.delenv("BRAND_PACKAGE_USE_PG", raising=False)
    memory: dict[str, BrandAssetPackage] = {}
    store = BrandPackageStore(memory)
    await store.create(_brand(pid="BPKG-DICT"))

    monkeypatch.setenv("BRAND_PACKAGE_USE_PG", "1")
    fallback_lookup = await store.get("BPKG-DICT")
    assert fallback_lookup is not None
    assert fallback_lookup.package_id == "BPKG-DICT"
