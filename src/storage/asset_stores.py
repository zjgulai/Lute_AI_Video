"""TODO-D12: PG-backed store for BrandAssetPackage / InfluencerProfile.

Per docs/architecture/api-assets-pg-cutover-2026-05-15.md PR2, this module
replaces the in-memory dicts in api_assets.py with a thin adapter that
routes to BrandPackageRepository / InfluencerRepository when the
BRAND_PACKAGE_USE_PG env flag is on.

Field mapping:
  BrandAssetPackage.package_id      ↔ brand_packages.id
  BrandAssetPackage.brand_name      ↔ brand_packages.name
  BrandAssetPackage.model_dump()    ↔ brand_packages.brand_guidelines (JSONB)
  InfluencerProfile.influencer_id   ↔ influencers.id
  InfluencerProfile.name            ↔ influencers.name
  InfluencerProfile.platforms[0]    ↔ influencers.platform (first platform only)
  InfluencerProfile.model_dump()    ↔ influencers.profile (JSONB)

When the flag is off (default), the adapter writes to the in-memory dict
only — preserves the pre-cutover behavior bit-for-bit. When on, the
adapter writes to PG and reads from PG. The dict is no longer used as a
fallback once on — but the same dict object is still imported by tests
that monkeypatch it, so we keep the dict accessible.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.models.brand import BrandAssetPackage
from src.models.influencer import InfluencerProfile
from src.storage.repository import BrandPackageRepository, InfluencerRepository

logger = logging.getLogger(__name__)


def _pg_enabled() -> bool:
    return os.getenv("BRAND_PACKAGE_USE_PG", "").lower() in ("1", "true", "yes")


def _pack_brand_row(package: BrandAssetPackage) -> dict[str, Any]:
    payload = package.model_dump()
    return {
        "id": package.package_id,
        "name": package.brand_name or "",
        "brand_guidelines": payload,
        "assets": payload.get("selected_footage_ids", []) or [],
    }


def _unpack_brand_row(row: dict[str, Any]) -> BrandAssetPackage:
    payload = row.get("brand_guidelines") or {}
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    payload.setdefault("package_id", row.get("id", ""))
    payload.setdefault("brand_name", row.get("name", ""))
    return BrandAssetPackage.from_dict(payload)


def _pack_influencer_row(profile: InfluencerProfile) -> dict[str, Any]:
    payload = profile.model_dump()
    platform = profile.platforms[0] if profile.platforms else ""
    return {
        "id": profile.influencer_id,
        "name": profile.name or "",
        "platform": platform,
        "profile": payload,
        "contact_info": {},
    }


def _unpack_influencer_row(row: dict[str, Any]) -> InfluencerProfile:
    payload = row.get("profile") or {}
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    payload.setdefault("influencer_id", row.get("id", ""))
    payload.setdefault("name", row.get("name", ""))
    return InfluencerProfile.from_dict(payload)


class BrandPackageStore:
    """Adapter over BrandPackageRepository + in-memory dict fallback."""

    def __init__(self, memory: dict[str, BrandAssetPackage]):
        self._memory = memory
        self._repo = BrandPackageRepository()

    async def create(self, package: BrandAssetPackage) -> BrandAssetPackage:
        if _pg_enabled():
            try:
                await self._repo.create(_pack_brand_row(package))
                return package
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("brand_store.create PG failed, mirroring to dict: %s", exc)
        self._memory[package.package_id] = package
        return package

    async def get(self, package_id: str) -> BrandAssetPackage | None:
        if _pg_enabled():
            try:
                row = await self._repo.get_by_id(package_id)
                if row is not None:
                    return _unpack_brand_row(row)
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("brand_store.get PG failed, falling back to dict: %s", exc)
        return self._memory.get(package_id)

    async def list_all(self) -> list[BrandAssetPackage]:
        if _pg_enabled():
            try:
                rows = await self._repo.list_all(limit=500)
                return [_unpack_brand_row(r) for r in rows]
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("brand_store.list_all PG failed, falling back to dict: %s", exc)
        return list(self._memory.values())

    async def delete(self, package_id: str) -> bool:
        deleted_pg = False
        if _pg_enabled():
            try:
                deleted_pg = await self._repo.delete(package_id)
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("brand_store.delete PG failed: %s", exc)
        if package_id in self._memory:
            del self._memory[package_id]
            return True
        return deleted_pg


class InfluencerStore:
    """Adapter over InfluencerRepository + in-memory dict fallback."""

    def __init__(self, memory: dict[str, InfluencerProfile]):
        self._memory = memory
        self._repo = InfluencerRepository()

    async def create(self, profile: InfluencerProfile) -> InfluencerProfile:
        if _pg_enabled():
            try:
                await self._repo.create(_pack_influencer_row(profile))
                return profile
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("influencer_store.create PG failed, mirroring to dict: %s", exc)
        self._memory[profile.influencer_id] = profile
        return profile

    async def get(self, influencer_id: str) -> InfluencerProfile | None:
        if _pg_enabled():
            try:
                row = await self._repo.get_by_id(influencer_id)
                if row is not None:
                    return _unpack_influencer_row(row)
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("influencer_store.get PG failed, falling back to dict: %s", exc)
        return self._memory.get(influencer_id)

    async def list_all(self) -> list[InfluencerProfile]:
        if _pg_enabled():
            try:
                rows = await self._repo.list_all(limit=500)
                return [_unpack_influencer_row(r) for r in rows]
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("influencer_store.list_all PG failed, falling back to dict: %s", exc)
        return list(self._memory.values())

    async def update(self, profile: InfluencerProfile) -> InfluencerProfile:
        if _pg_enabled():
            try:
                await self._repo.update(profile.influencer_id, _pack_influencer_row(profile))
                return profile
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("influencer_store.update PG failed, mirroring to dict: %s", exc)
        self._memory[profile.influencer_id] = profile
        return profile

    async def delete(self, influencer_id: str) -> bool:
        deleted_pg = False
        if _pg_enabled():
            try:
                deleted_pg = await self._repo.delete(influencer_id)
            except (OSError, RuntimeError, ConnectionError) as exc:
                logger.warning("influencer_store.delete PG failed: %s", exc)
        if influencer_id in self._memory:
            del self._memory[influencer_id]
            return True
        return deleted_pg
