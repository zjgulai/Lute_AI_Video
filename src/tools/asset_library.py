"""Asset Library Client — Supabase + pgvector asset search.

Two modes:
1. Production: connects to Supabase for real pgvector similarity search
2. Mock fallback: returns simulated results when Supabase unavailable

Graceful degradation at every level — no hard dependencies.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.models import AssetCandidate

logger = structlog.get_logger()


class AssetLibraryClient:
    """Searchable asset library backed by Supabase (pgvector).

    Falls back to mock mode when:
    - supabase-py package not installed
    - SUPABASE_URL or SUPABASE_SERVICE_KEY empty
    - create_client() fails
    """

    def __init__(
        self,
        supabase_url: str = "",
        service_key: str = "",
    ):
        self._ready = False
        self._client: Any = None
        self._mock = True  # default to mock until proven otherwise

        if not supabase_url or not service_key:
            logger.info(
                "asset_library: mock mode (no Supabase credentials)",
            )
            return

        try:
            from supabase import create_client

            self._client = create_client(supabase_url, service_key)
            self._ready = True
            self._mock = False
            logger.info("asset_library: connected to Supabase")
        except Exception as e:
            logger.warning(
                "asset_library: mock mode (Supabase init failed)",
                error=str(e),
            )

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_mock(self) -> bool:
        return self._mock

    def search_assets(self, query: str, limit: int = 5) -> list[AssetCandidate]:
        """Search assets by semantic query. Falls back to mock on failure."""
        if self._ready and not self._mock:
            try:
                return self._supabase_search(query, limit)
            except Exception as e:
                logger.warning(
                    "asset_library: search failed, falling back to mock",
                    error=str(e),
                )
        return self._mock_search(query, limit)

    def store_asset(
        self,
        file_path: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store an asset in the library. Returns asset_id."""
        if self._ready and not self._mock:
            try:
                return self._supabase_store(file_path, description, metadata or {})
            except Exception as e:
                logger.warning(
                    "asset_library: store failed, falling back to mock",
                    error=str(e),
                )
        return self._mock_store(file_path, description)

    def get_asset(self, asset_id: str) -> AssetCandidate | None:
        """Retrieve a single asset by ID."""
        if self._ready and not self._mock:
            try:
                return self._supabase_get(asset_id)
            except Exception as e:
                logger.warning(
                    "asset_library: get failed, falling back to mock",
                    error=str(e),
                )
        return self._mock_get(asset_id)

    # ── Supabase implementations ──

    def _supabase_search(self, query: str, limit: int = 5) -> list[AssetCandidate]:
        """pgvector similarity search via Supabase RPC."""
        # Expects a Postgres function: search_assets(query_text, match_limit)
        result = self._client.rpc(
            "search_assets",
            {"query_text": query, "match_limit": limit},
        ).execute()
        candidates = []
        for row in result.data or []:
            candidates.append(
                AssetCandidate(
                    asset_id=row.get("asset_id", ""),
                    file_path=row.get("file_path", ""),
                    description=row.get("description", ""),
                    match_score=row.get("match_score", 0.0),
                    source=row.get("source", "library"),
                )
            )
        return candidates

    def _supabase_store(
        self,
        file_path: str,
        description: str,
        metadata: dict[str, Any],
    ) -> str:
        """Store asset metadata in Supabase table."""
        import uuid

        asset_id = f"ASSET-{uuid.uuid4().hex[:8].upper()}"
        self._client.table("assets").insert(
            {
                "asset_id": asset_id,
                "file_path": file_path,
                "description": description,
                **metadata,
            }
        ).execute()
        return asset_id

    def _supabase_get(self, asset_id: str) -> AssetCandidate | None:
        """Fetch one asset from Supabase."""
        result = (
            self._client.table("assets")
            .select("*")
            .eq("asset_id", asset_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        return AssetCandidate(
            asset_id=row.get("asset_id", ""),
            file_path=row.get("file_path", ""),
            description=row.get("description", ""),
            match_score=row.get("match_score", 0.0),
            source=row.get("source", "library"),
        )

    # ── Mock implementations ──

    def _mock_search(self, query: str, limit: int = 5) -> list[AssetCandidate]:
        """Simulate search results for development/testing."""
        # Return deterministic mock results based on query keywords
        candidates = []
        mock_assets = {
            "product": ("ASSET-PROD-001", "/assets/library/product_demo.mp4"),
            "lifestyle": ("ASSET-LIFE-001", "/assets/library/lifestyle_clip.mp4"),
            "demo": ("ASSET-DEMO-001", "/assets/library/feature_demo.mp4"),
            "hook": ("ASSET-HOOK-001", "/assets/library/hook_intro.mp4"),
            "testimonial": ("ASSET-TEST-001", "/assets/library/customer_quote.mp4"),
            "default": ("ASSET-DEF-001", "/assets/library/generic_clip.mp4"),
        }

        query_lower = query.lower()
        for keyword, (aid, fpath) in mock_assets.items():
            if len(candidates) >= limit:
                break
            if keyword in query_lower:
                candidates.append(
                    AssetCandidate(
                        asset_id=aid,
                        file_path=fpath,
                        description=f"Mock asset matching '{keyword}'",
                        match_score=0.85,
                        source="library",
                    )
                )

        # Always pad with generic assets to fill the limit
        generic_id = 1
        while len(candidates) < limit:
            candidates.append(
                AssetCandidate(
                    asset_id=f"ASSET-GEN-{generic_id:03d}",
                    file_path=f"/assets/library/generic_{generic_id}.mp4",
                    description=f"Generic mock asset {generic_id}",
                    match_score=max(0.3, 0.7 - (generic_id * 0.1)),
                    source="library",
                )
            )
            generic_id += 1

        return candidates

    def _mock_store(
        self,
        file_path: str,
        description: str,
    ) -> str:
        """Simulate storing an asset."""
        import uuid

        asset_id = f"ASSET-MOCK-{uuid.uuid4().hex[:8].upper()}"
        logger.info(
            "asset_library: mock store",
            asset_id=asset_id,
            file_path=file_path,
        )
        return asset_id

    def _mock_get(self, asset_id: str) -> AssetCandidate | None:
        """Simulate fetching a single asset."""
        return AssetCandidate(
            asset_id=asset_id,
            file_path=f"/assets/library/{asset_id.lower()}.mp4",
            description=f"Mock asset {asset_id}",
            match_score=0.9,
            source="library",
        )
