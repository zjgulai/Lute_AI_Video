"""Asset management API endpoints.

Provides REST endpoints for:
- Uploading video/image assets
- Managing brand asset packages
- Managing influencer profiles
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.models.brand import BrandAssetPackage
from src.models.influencer import InfluencerProfile, InfluencerRemixBrief
from src.tools.asset_storage import AssetStorage

logger = structlog.get_logger()

router = APIRouter(prefix="/api/assets", tags=["assets"])


# ── In-memory storage for brand packages and influencers ──
# (Replace with database in production)
_brand_packages: dict[str, BrandAssetPackage] = {}
_influencers: dict[str, InfluencerProfile] = {}

# Initialize asset storage with default data dir
_asset_storage = AssetStorage()


@router.post("/upload")
async def upload_asset(
    file: UploadFile = File(...),
    tags: str = Form(""),
    metadata: str = Form("{}"),
):
    """Upload a video or image asset.

    Stores the file and returns an asset_id for pipeline use.

    Args:
        file: Video (.mp4, .mov, .webm) or image (.jpg, .png, .gif) file.
        tags: Comma-separated tags for search (e.g., "product,demo,lifestyle").
        metadata: JSON string with arbitrary metadata.

    Returns:
        {asset_id, filename, file_size, mime_type, tags, metadata}
    """
    import json

    data = await file.read()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    meta_dict = json.loads(metadata) if metadata != "{}" else {}

    record = _asset_storage.store(
        file_data=data,
        original_name=file.filename or "upload.bin",
        tags=tag_list,
        metadata=meta_dict,
    )

    logger.info("api: asset uploaded", asset_id=record.asset_id, size=record.file_size)
    return record.to_dict()


@router.post("/brand-packages", tags=["brand"])
async def create_brand_package(package: BrandAssetPackage):
    """Create a brand asset package.

    The package bundles logo, colors, fonts, intro/outro templates,
    and selected footage IDs for a brand campaign.
    """
    if not package.package_id:
        import uuid
        package.package_id = f"BPKG-{uuid.uuid4().hex[:8].upper()}"
    from datetime import datetime
    package.created_at = datetime.utcnow().isoformat()
    package.updated_at = package.created_at
    _brand_packages[package.package_id] = package
    logger.info("api: brand package created", id=package.package_id)
    return package.to_dict()


@router.get("/brand-packages/{package_id}", tags=["brand"])
async def get_brand_package(package_id: str):
    """Get a brand asset package by ID."""
    package = _brand_packages.get(package_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Brand package '{package_id}' not found")
    return package.to_dict()


@router.get("/brand-packages", tags=["brand"])
async def list_brand_packages():
    """List all brand asset packages."""
    return {"packages": [p.to_dict() for p in _brand_packages.values()], "total": len(_brand_packages)}


@router.delete("/brand-packages/{package_id}", tags=["brand"])
async def delete_brand_package(package_id: str):
    """Delete a brand asset package."""
    if package_id not in _brand_packages:
        raise HTTPException(status_code=404)
    del _brand_packages[package_id]
    return {"deleted": True}


# ── Influencer Profile Endpoints ──


@router.post("/influencers", tags=["influencer"])
async def create_influencer(profile: InfluencerProfile):
    """Register a new influencer profile."""
    if not profile.influencer_id:
        import uuid
        profile.influencer_id = f"INFL-{uuid.uuid4().hex[:8].upper()}"
    from datetime import datetime
    profile.created_at = datetime.utcnow().isoformat()
    profile.updated_at = profile.created_at
    _influencers[profile.influencer_id] = profile
    logger.info("api: influencer created", id=profile.influencer_id)
    return profile.to_dict()


@router.get("/influencers/{influencer_id}", tags=["influencer"])
async def get_influencer(influencer_id: str):
    """Get influencer profile."""
    profile = _influencers.get(influencer_id)
    if not profile:
        raise HTTPException(status_code=404)
    return profile.to_dict()


@router.get("/influencers", tags=["influencer"])
async def list_influencers():
    """List all influencers."""
    return {"influencers": [p.to_dict() for p in _influencers.values()], "total": len(_influencers)}


@router.put("/influencers/{influencer_id}/product-links", tags=["influencer"])
async def update_influencer_product_links(
    influencer_id: str,
    links: list[dict],
):
    """Update an influencer's product links.

    Args:
        influencer_id: Influencer to update.
        links: List of {product_id, product_name, platform_specific_urls, commission_rate}

    Returns:
        Updated influencer profile.
    """
    profile = _influencers.get(influencer_id)
    if not profile:
        raise HTTPException(status_code=404)
    from src.models.influencer import InfluencerProductLink
    profile.product_links = [InfluencerProductLink(**l) for l in links]
    from datetime import datetime
    profile.updated_at = datetime.utcnow().isoformat()
    logger.info("api: influencer links updated", id=influencer_id, count=len(links))
    return profile.to_dict()


@router.delete("/influencers/{influencer_id}", tags=["influencer"])
async def delete_influencer(influencer_id: str):
    """Delete an influencer profile."""
    if influencer_id not in _influencers:
        raise HTTPException(status_code=404)
    del _influencers[influencer_id]
    return {"deleted": True}


@router.post("/remix-brief", tags=["influencer"])
async def create_remix_brief(brief: InfluencerRemixBrief):
    """Create an influencer remix brief.

    This triggers the S3 pipeline for a specific influencer + product.
    The brief is stored and can be picked up by the pipeline.
    """
    if not brief.brief_id:
        import uuid
        brief.brief_id = f"RMX-{uuid.uuid4().hex[:8].upper()}"
    logger.info("api: remix brief created", id=brief.brief_id, influencer=brief.influencer_id)
    return brief.model_dump()

@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    """Get asset metadata by ID.

    Returns:
        Asset record with file_path (local) or error.
    """
    record = _asset_storage.get(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    return record.to_dict()


@router.get("/")
async def list_assets(tags: str = "", limit: int = 100):
    """List all assets, optionally filtered by tags.

    Args:
        tags: Comma-separated tags to filter by (AND logic).
        limit: Max results.

    Returns:
        {assets: list[AssetRecord], total: int}
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    records = _asset_storage.list(tags=tag_list, limit=limit)
    return {"assets": [r.to_dict() for r in records], "total": len(records)}


@router.put("/{asset_id}/tags")
async def update_asset_tags(asset_id: str, body: dict):
    """Update tags for an asset.

    Args:
        asset_id: Asset ID to update.
        body: {tags: list[str]}

    Returns:
        Updated asset record or 404.
    """
    new_tags = body.get("tags", [])
    record = _asset_storage.update_tags(asset_id, new_tags)
    if not record:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    logger.info("api: asset tags updated", asset_id=asset_id, tags=new_tags)
    return record.to_dict()


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete an asset by ID.

    Returns:
        {deleted: true} or 404.
    """
    if not _asset_storage.delete(asset_id):
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    return {"deleted": True}


# ── Brand Asset Package Endpoints ──

