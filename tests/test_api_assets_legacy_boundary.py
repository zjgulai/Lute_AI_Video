from __future__ import annotations

from src import api_assets
from src.routers import assets


def _route_paths(router) -> set[str]:
    return {route.path for route in router.routes}


def test_api_assets_router_stays_on_legacy_api_assets_prefix() -> None:
    assert api_assets.router.prefix == "/api/assets"
    assert {
        "/api/assets/brand-packages",
        "/api/assets/brand-packages/{package_id}",
        "/api/assets/influencers",
        "/api/assets/influencers/{influencer_id}",
        "/api/assets/influencers/{influencer_id}/product-links",
        "/api/assets/remix-brief",
    } <= _route_paths(api_assets.router)


def test_modern_assets_router_does_not_claim_legacy_api_assets_paths() -> None:
    paths = _route_paths(assets.router)
    assert "/api/upload" in paths
    assert "/api/files" in paths
    assert all(not path.startswith("/api/assets") for path in paths)
