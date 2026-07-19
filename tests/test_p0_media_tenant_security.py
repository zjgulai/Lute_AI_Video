from __future__ import annotations

import contextlib
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


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


def _tenant_file(root: Path, tenant: str, name: str = "proof.png") -> Path:
    target = root / "tenants" / tenant / "pending_review" / "sample" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"protected")
    return target


def _replace_signed_query(signed: str, **changes: str) -> str:
    parts = urlsplit(signed)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(changes)
    return urlunsplit(parts._replace(query=urlencode(query)))


def test_development_media_secret_never_falls_back_to_api_key(monkeypatch):
    from src.routers import _deps, media

    monkeypatch.delenv("MEDIA_SIGN_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    first = media._load_media_token_secret()
    second = media._load_media_token_secret()

    assert first != _deps.API_KEY
    assert second != _deps.API_KEY
    assert first != second


def test_production_requires_independent_media_sign_secret(monkeypatch):
    from src.routers import media

    monkeypatch.delenv("MEDIA_SIGN_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="MEDIA_SIGN_SECRET"):
        media._load_media_token_secret()


def test_production_rejects_weak_media_sign_secret(monkeypatch):
    from src.routers import media

    monkeypatch.setenv("MEDIA_SIGN_SECRET", "too-short")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="at least 32 UTF-8 bytes"):
        media._load_media_token_secret()


def test_media_sign_rejects_path_traversal(tmp_path, monkeypatch):
    from src.routers import media

    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        media.sign_media_url("../secret.txt", tenant_id="tenant-a")

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
            media.sign_media_url(bad_path, tenant_id="tenant-a")
        assert exc.value.status_code == 400


def test_media_sign_uses_canonical_path_for_nested_file(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "uploads" / "tenant-a" / "clip.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake mp4")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    signed = media.sign_media_url("uploads/tenant-a/clip.mp4", tenant_id="tenant-a")

    assert signed.startswith("/api/media/uploads/tenant-a/clip.mp4?")
    assert set(parse_qs(urlsplit(signed).query)) == {
        "token",
        "expires",
        "tenant",
        "purpose",
    }


def test_protected_media_rejects_unsigned_request(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get(
        "/api/media/tenants/tenant-a/pending_review/sample/proof.png"
    )

    assert response.status_code in {401, 403}


def test_cross_tenant_cannot_sign_protected_media(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with auth_context("tenant-b"), pytest.raises(HTTPException) as exc:
        media.sign_media_url(
            "tenants/tenant-a/pending_review/sample/proof.png",
            tenant_id="tenant-b",
        )

    assert exc.value.status_code == 404


def test_owner_signed_url_serves_protected_media(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    with auth_context("tenant-a"):
        signed = media.sign_media_url(
            "tenants/tenant-a/pending_review/sample/proof.png",
            tenant_id="tenant-a",
        )

    app = FastAPI()
    app.include_router(media.router)
    response = TestClient(app).get(signed)

    assert response.status_code == 200
    assert response.content == b"protected"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("public_root", ["brand_assets", "demo"])
def test_explicit_public_media_allows_unsigned_request(tmp_path, monkeypatch, public_root):
    from src.routers import media

    target = tmp_path / public_root / "brand" / "logo.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"public")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get(f"/api/media/{public_root}/brand/logo.png")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"


@pytest.mark.parametrize(
    "protected_path",
    [
        "renders/proof.png",
        "seedance/proof.png",
        "audio/proof.png",
        "gpt_images/proof.png",
        "fast_mode/proof.png",
        "uploads/proof.png",
    ],
)
def test_non_public_media_roots_reject_unsigned_request(
    tmp_path,
    monkeypatch,
    protected_path,
):
    from src.routers import media

    target = tmp_path / protected_path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"protected")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get(f"/api/media/{protected_path}")

    assert response.status_code in {401, 403}


def test_signed_token_is_bound_to_tenant_path_and_purpose(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
        purpose="view",
    )

    app = FastAPI()
    app.include_router(media.router)
    client = TestClient(app)
    assert client.get(signed.replace("tenant=tenant-a", "tenant=tenant-b")).status_code == 403
    assert client.get(signed.replace("purpose=view", "purpose=download")).status_code == 403


def test_signed_token_rejects_canonical_path_tampering(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    _tenant_file(tmp_path, "tenant-a", name="other.png")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
    )

    app = FastAPI()
    app.include_router(media.router)
    tampered = signed.replace("/proof.png?", "/other.png?")

    assert TestClient(app).get(tampered).status_code == 403


def test_signed_token_rejects_token_tampering(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
    )

    app = FastAPI()
    app.include_router(media.router)

    assert TestClient(app).get(_replace_signed_query(signed, token="tampered")).status_code == 403


def test_signed_token_rejects_expiry_tampering(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
    )
    expires = int(parse_qs(urlsplit(signed).query)["expires"][0])

    app = FastAPI()
    app.include_router(media.router)
    tampered = _replace_signed_query(signed, expires=str(expires + 1))

    assert TestClient(app).get(tampered).status_code == 403


def test_expired_signed_token_is_rejected(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
        expires_in_sec=-1,
    )

    app = FastAPI()
    app.include_router(media.router)

    assert TestClient(app).get(signed).status_code == 403


def test_protected_media_rejects_extra_or_duplicate_signature_params(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
    )
    token = parse_qs(urlsplit(signed).query)["token"][0]

    app = FastAPI()
    app.include_router(media.router)
    client = TestClient(app)

    assert client.get(f"{signed}&redirect=https://evil.example").status_code == 403
    assert client.get(f"{signed}&token={token}").status_code == 403


def test_missing_nested_path_does_not_fall_back_by_basename(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "seedance" / "proof.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"wrong file")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        media.sign_media_url(
            "tenants/tenant-a/pending_review/missing/proof.png",
            tenant_id="tenant-a",
        )

    assert exc.value.status_code == 404


def test_sign_endpoint_uses_authenticated_tenant_not_query_tenant(tmp_path, monkeypatch):
    from src.routers import _deps, media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    ctx = _deps.AuthContext(
        tenant_id="tenant-a",
        permissions=frozenset({"all"}),
        key_type=_deps.ApiKeyType.TENANT,
        key_id="key-tenant-a",
    )

    app = FastAPI()
    app.include_router(media.router)
    app.dependency_overrides[media.verify_api_key] = lambda: ctx
    response = TestClient(app).get(
        "/api/media/sign",
        params={
            "path": "tenants/tenant-a/pending_review/sample/proof.png",
            "tenant": "tenant-b",
        },
    )

    assert response.status_code == 200
    signed = response.json()["url"]
    assert "tenant=tenant-a" in signed
    assert "tenant=tenant-b" not in signed


def test_sign_endpoint_rejects_cross_tenant_path(tmp_path, monkeypatch):
    from src.routers import _deps, media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    ctx = _deps.AuthContext(
        tenant_id="tenant-b",
        permissions=frozenset({"all"}),
        key_type=_deps.ApiKeyType.TENANT,
        key_id="key-tenant-b",
    )

    app = FastAPI()
    app.include_router(media.router)
    app.dependency_overrides[media.verify_api_key] = lambda: ctx
    response = TestClient(app).get(
        "/api/media/sign",
        params={"path": "tenants/tenant-a/pending_review/sample/proof.png"},
    )

    assert response.status_code == 404


def test_sign_endpoint_rejects_unauthenticated_request(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get(
        "/api/media/sign",
        params={"path": "tenants/tenant-a/pending_review/sample/proof.png"},
    )

    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_portfolio_filters_and_caches_by_tenant(tmp_path, monkeypatch):
    import src.routers.portfolio as portfolio

    tenant_a_file = tmp_path / "uploads" / "tenant-a" / "a.mp4"
    tenant_b_file = tmp_path / "uploads" / "tenant-b" / "b.mp4"
    tenant_a_pending = tmp_path / "tenants" / "tenant-a" / "pending_review" / "smoke" / "a.png"
    tenant_b_pending = tmp_path / "tenants" / "tenant-b" / "pending_review" / "smoke" / "b.png"
    default_pending = tmp_path / "pending_review" / "legacy" / "default.png"
    brand_file = tmp_path / "brand_assets" / "momcozy" / "sku" / "images" / "p.png"
    for path in (tenant_a_file, tenant_b_file, tenant_a_pending, tenant_b_pending, default_pending, brand_file):
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
    assert "tenants/tenant-a/pending_review/smoke/a.png" in paths_a
    assert "tenants/tenant-b/pending_review/smoke/b.png" not in paths_a
    assert "pending_review/legacy/default.png" not in paths_a
    assert "brand_assets/momcozy/sku/images/p.png" in paths_a
    assert "uploads/tenant-b/b.mp4" in paths_b
    assert "uploads/tenant-a/a.mp4" not in paths_b
    assert "tenants/tenant-b/pending_review/smoke/b.png" in paths_b
    assert "tenants/tenant-a/pending_review/smoke/a.png" not in paths_b
    assert "pending_review/legacy/default.png" not in paths_b
    pending_a = {f.review_status for f in resp_a.files if f.category == "pending_review"}
    assert pending_a == {"pending_review"}


@pytest.mark.asyncio
async def test_portfolio_poster_inherits_global_and_tenant_source_scope(
    tmp_path,
    monkeypatch,
):
    import src.routers.portfolio as portfolio
    from src.routers import media

    brand_video = (
        tmp_path / "brand_assets" / "momcozy" / "sku" / "images" / "brand.mp4"
    )
    tenant_video = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "pending_review"
        / "run"
        / "tenant.mp4"
    )
    poster_root = tmp_path / "thumbnails" / "portfolio_posters"
    for video in (brand_video, tenant_video):
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"v" * (1024 * 1024 + 1))
    poster_root.mkdir(parents=True)
    brand_poster = poster_root / "brand_assets__momcozy__sku__images__brand.jpg"
    tenant_poster = (
        poster_root / "tenants__tenant-a__pending_review__run__tenant.jpg"
    )
    brand_poster.write_bytes(b"brand-poster")
    tenant_poster.write_bytes(b"tenant-poster")

    monkeypatch.setattr(portfolio, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "THUMBNAIL_DIR", poster_root)
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    portfolio._CACHE.clear()
    portfolio._VIEW_CACHE.clear()

    with auth_context("tenant-b"):
        listed = await portfolio.list_portfolio(limit=100)
    brand_item = next(item for item in listed.files if item.path.endswith("brand.mp4"))
    assert brand_item.thumbnail_path == (
        "thumbnails/portfolio_posters/brand_assets__momcozy__sku__images__brand.jpg"
    )
    assert media.sign_media_url(
        brand_item.thumbnail_path,
        tenant_id="tenant-b",
    ).startswith("/api/media/thumbnails/portfolio_posters/")

    tenant_path = "thumbnails/portfolio_posters/tenants__tenant-a__pending_review__run__tenant.jpg"
    assert media.sign_media_url(tenant_path, tenant_id="tenant-a").startswith(
        "/api/media/thumbnails/portfolio_posters/"
    )
    with pytest.raises(HTTPException) as exc:
        media.sign_media_url(tenant_path, tenant_id="tenant-b")
    assert exc.value.status_code == 404


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
