"""Tests for asset_stores.py dual-storage (PG + in-memory dict) behavior.

Verifies that:
- BrandPackageStore and InfluencerStore gracefully handle PG unavailability
- The in-memory dict fallback works correctly for CRUD operations
- The _pg_enabled() flag is properly toggled by BRAND_PACKAGE_USE_PG

Ref: debt-audit-report-2026-06-09.md items E2, D21
"""

import pytest
from unittest.mock import patch

from src.storage.asset_stores import BrandPackageStore, InfluencerStore
from src.models.brand import BrandAssetPackage
from src.models.influencer import InfluencerProfile


# ── BrandPackageStore — In-Memory Dict Fallback ──────────────

class TestBrandPackageStoreMemory:
    """Test BrandPackageStore when PG is disabled (dict-only mode)."""

    @pytest.fixture
    def store(self) -> BrandPackageStore:
        return BrandPackageStore(memory={})

    @pytest.mark.asyncio
    async def test_create_and_get(self, store: BrandPackageStore) -> None:
        package = BrandAssetPackage(
            package_id="test-001",
            brand_name="Test Brand",
        )
        created = await store.create(package)
        assert created.package_id == "test-001"

        retrieved = await store.get("test-001")
        assert retrieved is not None
        assert retrieved.brand_name == "Test Brand"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store: BrandPackageStore) -> None:
        assert await store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_all_returns_list(self, store: BrandPackageStore) -> None:
        packages = await store.list_all()
        assert isinstance(packages, list)

    @pytest.mark.asyncio
    async def test_delete_removes_from_memory(self, store: BrandPackageStore) -> None:
        package = BrandAssetPackage(package_id="test-002", brand_name="To Delete")
        await store.create(package)
        assert await store.get("test-002") is not None

        await store.delete("test-002")
        assert await store.get("test-002") is None

    @pytest.mark.asyncio
    async def test_create_does_not_crash_with_minimal_package(self, store: BrandPackageStore) -> None:
        package = BrandAssetPackage(package_id="minimal")
        created = await store.create(package)
        assert created.package_id == "minimal"


# ── InfluencerStore — In-Memory Dict Fallback ─────────────────

class TestInfluencerStoreMemory:
    """Test InfluencerStore when PG is disabled (dict-only mode)."""

    @pytest.fixture
    def store(self) -> InfluencerStore:
        return InfluencerStore(memory={})

    @pytest.mark.asyncio
    async def test_create_and_get(self, store: InfluencerStore) -> None:
        profile = InfluencerProfile(
            influencer_id="inf-001",
            name="Test Influencer",
            platform="tiktok",
        )
        created = await store.create(profile)
        assert created.influencer_id == "inf-001"

        retrieved = await store.get("inf-001")
        assert retrieved is not None
        assert retrieved.name == "Test Influencer"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store: InfluencerStore) -> None:
        assert await store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_all_returns_list(self, store: InfluencerStore) -> None:
        profiles = await store.list_all()
        assert isinstance(profiles, list)

    @pytest.mark.asyncio
    async def test_delete_removes_from_memory(self, store: InfluencerStore) -> None:
        profile = InfluencerProfile(influencer_id="inf-002", name="To Delete", platform="youtube")
        await store.create(profile)
        assert await store.get("inf-002") is not None

        await store.delete("inf-002")
        assert await store.get("inf-002") is None

    @pytest.mark.asyncio
    async def test_create_does_not_crash_with_minimal_profile(self, store: InfluencerStore) -> None:
        profile = InfluencerProfile(influencer_id="minimal", name="Min", platform="instagram")
        created = await store.create(profile)
        assert created.influencer_id == "minimal"


# ── PG Disabled Flag ─────────────────────────────────────────

def test_pg_enabled_defaults_disabled() -> None:
    """Without BRAND_PACKAGE_USE_PG env var, PG should be disabled."""
    from src.storage.asset_stores import _pg_enabled
    with patch.dict("os.environ", {}, clear=True):
        assert _pg_enabled() is False

def test_pg_enabled_respects_env_var() -> None:
    """BRAND_PACKAGE_USE_PG=1 should enable PG."""
    from src.storage.asset_stores import _pg_enabled
    with patch.dict("os.environ", {"BRAND_PACKAGE_USE_PG": "1"}, clear=True):
        assert _pg_enabled() is True

def test_pg_enabled_false_values() -> None:
    """False-ish values should keep PG disabled."""
    from src.storage.asset_stores import _pg_enabled
    for val in ("", "0", "no", "false"):
        with patch.dict("os.environ", {"BRAND_PACKAGE_USE_PG": val}, clear=True):
            assert _pg_enabled() is False, f"BRAND_PACKAGE_USE_PG={val!r} should disable PG"
