from __future__ import annotations

import contextlib

import pytest
from fastapi import HTTPException


@contextlib.contextmanager
def auth_context(tenant_id: str):
    from src.routers import _deps

    token = _deps._auth_context_var.set(
        _deps.AuthContext(
            tenant_id=tenant_id,
            permissions=frozenset({"all"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id=f"key-{tenant_id}",
        )
    )
    try:
        yield
    finally:
        _deps._auth_context_var.reset(token)


def test_media_sign_rejects_path_traversal(tmp_path, monkeypatch):
    from src.routers import media

    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        media.sign_media_url("../secret.txt")

    assert exc.value.status_code == 400


def test_media_sign_rejects_url_schemes_and_encoded_traversal(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "renders" / "secret.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake mp4")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    for bad_path in (
        "https://evil.example/secret.mp4",
        "//evil.example/secret.mp4",
        "javascript:alert(1)",
        "renders/%2e%2e/secret.mp4",
        "renders/%252e%252e/secret.mp4",
    ):
        with pytest.raises(HTTPException) as exc:
            media.sign_media_url(bad_path)
        assert exc.value.status_code == 400


def test_media_sign_uses_canonical_path_for_nested_file(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "uploads" / "tenant-a" / "clip.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake mp4")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    signed = media.sign_media_url("uploads/tenant-a/clip.mp4")

    assert signed.startswith("/api/media/uploads/tenant-a/clip.mp4?")
    assert "token=" in signed
    assert "expires=" in signed


@pytest.mark.asyncio
async def test_portfolio_filters_and_caches_by_tenant(tmp_path, monkeypatch):
    import src.routers.portfolio as portfolio

    tenant_a_file = tmp_path / "uploads" / "tenant-a" / "a.mp4"
    tenant_b_file = tmp_path / "uploads" / "tenant-b" / "b.mp4"
    brand_file = tmp_path / "brand_assets" / "momcozy" / "sku" / "images" / "p.png"
    for path in (tenant_a_file, tenant_b_file, brand_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1024 * 1024 + 1))

    monkeypatch.setattr(portfolio, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "THUMBNAIL_DIR", tmp_path / "thumbnails" / "portfolio_posters")
    portfolio._CACHE.clear()
    portfolio._VIEW_CACHE.clear()
    portfolio._load_brand_info.cache_clear()

    with auth_context("tenant-a"):
        resp_a = await portfolio.list_portfolio(limit=20)
    with auth_context("tenant-b"):
        resp_b = await portfolio.list_portfolio(limit=20)

    paths_a = {f.path for f in resp_a.files}
    paths_b = {f.path for f in resp_b.files}
    assert "uploads/tenant-a/a.mp4" in paths_a
    assert "uploads/tenant-b/b.mp4" not in paths_a
    assert "brand_assets/momcozy/sku/images/p.png" in paths_a
    assert "uploads/tenant-b/b.mp4" in paths_b
    assert "uploads/tenant-a/a.mp4" not in paths_b


def test_assets_file_listing_rejects_other_tenant_paths():
    from pathlib import Path

    from src.routers import assets

    with auth_context("tenant-a"):
        assert assets._can_list_media(Path("uploads/tenant-a/a.mp4"))
        assert assets._can_list_media(Path("tenants/tenant-a/renders/a.mp4"))
        assert assets._can_list_media(Path("brand_assets/momcozy/x.png"))
        assert not assets._can_list_media(Path("uploads/tenant-b/b.mp4"))
        assert not assets._can_list_media(Path("renders/legacy.mp4"))


@pytest.mark.asyncio
async def test_metrics_repository_filters_by_tenant(tmp_path, monkeypatch):
    import src.storage.metrics_repository as mr_module
    from src.storage import db as db_module
    from src.storage.metrics_repository import VideoMetricsRepository

    db_path = tmp_path / "metrics.db"
    db_module._sqlite_conn = None

    def _init_at_test_path():
        import sqlite3

        db_module._sqlite_conn = sqlite3.connect(str(db_path))
        db_module._sqlite_conn.row_factory = sqlite3.Row
        db_module._create_sqlite_tables()

    async def _no_pool():
        return None

    monkeypatch.setattr(db_module, "_init_sqlite", _init_at_test_path)
    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(mr_module, "get_pool", _no_pool)
    _init_at_test_path()

    try:
        repo = VideoMetricsRepository()
        await repo.save_metrics("video-1", "s1", "tiktok", tenant_id="tenant-a", metrics_dict={"views": 10})
        await repo.save_metrics("video-1", "s1", "tiktok", tenant_id="tenant-b", metrics_dict={"views": 20})

        rows_a = await repo.get_metrics("video-1", tenant_id="tenant-a")
        rows_b = await repo.get_metrics("video-1", tenant_id="tenant-b")
        overview_a = await repo.get_dashboard_overview(tenant_id="tenant-a")
    finally:
        if db_module._sqlite_conn is not None:
            db_module._sqlite_conn.close()
            db_module._sqlite_conn = None

    assert len(rows_a) == 1
    assert rows_a[0]["tenant_id"] == "tenant-a"
    assert rows_a[0]["metrics"]["views"] == 10
    assert len(rows_b) == 1
    assert rows_b[0]["tenant_id"] == "tenant-b"
    assert len(overview_a) == 1
    assert overview_a[0]["tenant_id"] == "tenant-a"
