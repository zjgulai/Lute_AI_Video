"""Shopify connector — publish content to Shopify via the Admin API.

Uses the Shopify Admin API (GraphQL) to upload video files and associate
them with products. Falls back to mock mode when credentials are absent.
"""

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from src.connectors.base import PlatformConnector

logger = logging.getLogger(__name__)

# Shopify Admin GraphQL endpoint (version 2024-07 or later supports fileCreate)
_SHOPIFY_GRAPHQL_URL = "https://{store}/admin/api/2024-07/graphql.json"


def _is_mock_mode() -> bool:
    """Return True when no real Shopify API credentials are available."""
    api_key = os.environ.get("SHOPIFY_API_KEY", "")
    store_url = os.environ.get("SHOPIFY_STORE_URL", "")
    return not api_key or not store_url


def _admin_url() -> str:
    """Return the base admin URL for the configured Shopify store."""
    store = os.environ.get("SHOPIFY_STORE_URL", "mock-store.myshopify.com")
    return f"https://{store}/admin"


def _headers() -> dict[str, Any]:
    """Build headers for Shopify Admin API requests."""
    api_key = os.environ.get("SHOPIFY_API_KEY", "")
    password = os.environ.get("SHOPIFY_API_PASSWORD", "")
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")

    if token:
        return {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        }
    # Fallback to basic auth (API key + password)
    return {
        "Content-Type": "application/json",
    }


class ShopifyConnector(PlatformConnector):
    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Publish content to Shopify.

        Accepts content with fields:
            title        (str) — video title
            video_path   (str) — local file path to the video
            product_name (str) — product name to associate the video with

        Returns dict with keys:
            success, post_id, url, status, error, platform, published_at
        """
        api_key = os.environ.get("SHOPIFY_API_KEY", "")
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")

        if not api_key or not store_url:
            logger.info(
                "SHOPIFY_API_KEY or SHOPIFY_STORE_URL not set — using mock publish"
            )
            return await self._mock_publish(content)

        video_path = content.get("video_path", "")
        title = content.get("title", "AI-generated video")
        product_name = content.get("product_name", "")

        if not video_path or not os.path.isfile(video_path):
            logger.warning("Video file not found at %s", video_path)
            return {
                "success": False,
                "error": f"Video file not found: {video_path}",
                "status": "failed",
                "platform": "shopify",
            }

        try:
            # Step 1: Upload video file via Shopify Files API (fileCreate)
            file_result = await self._upload_video(
                store_url, video_path, title
            )
            if not file_result.get("success"):
                return {
                    "success": False,
                    "error": file_result.get("error", "File upload failed"),
                    "status": "failed",
                    "platform": "shopify",
                }

            media_id = file_result.get("media_id", "")

            # Step 2: If a product name is given, associate the video with it
            post_url = f"{_admin_url()}/products"
            if product_name:
                product_result = await self._associate_with_product(
                    store_url, media_id, product_name
                )
                if product_result.get("success"):
                    product_id = product_result.get("product_id", "")
                    post_url = f"{_admin_url()}/products/{product_id}"
                else:
                    logger.warning(
                        "Failed to associate video with product '%s': %s",
                        product_name,
                        product_result.get("error"),
                    )

            return {
                "success": True,
                "post_id": media_id,
                "url": post_url,
                "status": "published",
                "platform": "shopify",
                "published_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.exception("Shopify API publish error")
            return {
                "success": False,
                "error": str(exc),
                "status": "failed",
                "platform": "shopify",
            }

    async def _upload_video(
        self, store_url: str, video_path: str, title: str
    ) -> dict[str, Any]:
        """Upload a video file to Shopify using the GraphQL fileCreate mutation.

        Returns dict with keys: success, media_id, error.
        """
        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        headers = _headers()
        headers["Content-Type"] = "application/json"

        # Stage 1: Request a staged upload URL
        staging_mutation = """
        mutation StagedUploadsCreate($input: [StagedUploadInput!]!) {
            stagedUploadsCreate(input: $input) {
                stagedTargets {
                    url
                    resourceUrl
                    parameters {
                        name
                        value
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)

        staging_variables = {
            "input": [
                {
                    "resource": "FILE",
                    "filename": filename,
                    "mimeType": "video/mp4",
                    "fileSize": str(file_size),
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Stage 1: Get upload URL
                resp = await client.post(
                    graphql_url,
                    headers=headers,
                    json={
                        "query": staging_mutation,
                        "variables": staging_variables,
                    },
                )

                if resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Shopify staging HTTP {resp.status_code}: {resp.text[:300]}",
                    }

                data = resp.json()
                user_errors = (
                    data.get("data", {})
                    .get("stagedUploadsCreate", {})
                    .get("userErrors", [])
                )
                if user_errors:
                    error_msg = "; ".join(
                        e.get("message", "Unknown error") for e in user_errors
                    )
                    return {"success": False, "error": error_msg}

                targets = (
                    data.get("data", {})
                    .get("stagedUploadsCreate", {})
                    .get("stagedTargets", [])
                )
                if not targets:
                    return {
                        "success": False,
                        "error": "No staged upload targets returned",
                    }

                target = targets[0]
                upload_url = target["url"]
                parameters = target["parameters"]

                # Build multipart form for the actual upload
                files = {}
                for param in parameters:
                    files[param["name"]] = (
                        "blob",
                        param["value"].encode(),
                        "text/plain",
                    )
                files["file"] = (filename, open(video_path, "rb"), "video/mp4")

                # Stage 2: Upload file to the staged URL
                upload_resp = await client.post(upload_url, files=files)

                if upload_resp.status_code not in (200, 201):
                    return {
                        "success": False,
                        "error": f"Shopify file upload HTTP {upload_resp.status_code}: {upload_resp.text[:300]}",
                    }

                # Stage 3: Create the media record with fileCreate mutation
                create_mutation = """
                mutation fileCreate($files: [FileCreateInput!]!) {
                    fileCreate(files: $files) {
                        files {
                            id
                            alt
                            createdAt
                            fileStatus
                            ... on MediaFile {
                                preview {
                                    url
                                }
                            }
                        }
                        userErrors {
                            field
                            message
                        }
                    }
                }
                """

                create_variables = {
                    "files": [
                        {
                            "alt": title,
                            "contentType": "VIDEO",
                            "originalSource": target["resourceUrl"],
                        }
                    ]
                }

                create_resp = await client.post(
                    graphql_url,
                    headers=headers,
                    json={
                        "query": create_mutation,
                        "variables": create_variables,
                    },
                )

                if create_resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Shopify fileCreate HTTP {create_resp.status_code}: {create_resp.text[:300]}",
                    }

                create_data = create_resp.json()
                create_errors = (
                    create_data.get("data", {})
                    .get("fileCreate", {})
                    .get("userErrors", [])
                )
                if create_errors:
                    error_msg = "; ".join(
                        e.get("message", "Unknown error") for e in create_errors
                    )
                    return {"success": False, "error": error_msg}

                created_files = (
                    create_data.get("data", {})
                    .get("fileCreate", {})
                    .get("files", [])
                )
                if not created_files:
                    return {
                        "success": False,
                        "error": "No files returned from fileCreate",
                    }

                file_id = created_files[0].get("id", "")
                return {"success": True, "media_id": file_id}

        except Exception as exc:
            logger.exception("Shopify video upload exception")
            return {"success": False, "error": str(exc)}

    async def _associate_with_product(
        self, store_url: str, media_id: str, product_name: str
    ) -> dict[str, Any]:
        """Search for a product by name and associate the media with it.

        Uses the productCreateMedia mutation to attach the uploaded video.

        Returns dict with keys: success, product_id, error.
        """
        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        headers = _headers()
        headers["Content-Type"] = "application/json"

        # First, search for the product by title
        search_query = """
        query searchProducts($query: String!) {
            products(first: 1, query: $query) {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                search_resp = await client.post(
                    graphql_url,
                    headers=headers,
                    json={
                        "query": search_query,
                        "variables": {"query": f"title:{product_name}"},
                    },
                )

                if search_resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Product search HTTP {search_resp.status_code}",
                    }

                search_data = search_resp.json()
                products = (
                    search_data.get("data", {})
                    .get("products", {})
                    .get("edges", [])
                )

                if not products:
                    logger.warning(
                        "No Shopify product found matching '%s'", product_name
                    )
                    return {
                        "success": False,
                        "error": f"Product '{product_name}' not found",
                    }

                product_id = products[0]["node"]["id"]

                # Now associate the media with the product
                associate_mutation = """
                mutation productCreateMedia($media: [CreateMediaInput!]!) {
                    productCreateMedia(media: $media) {
                        media {
                            ... on MediaFile {
                                id
                                fileStatus
                            }
                        }
                        userErrors {
                            field
                            message
                        }
                    }
                }
                """

                associate_variables = {
                    "media": [
                        {
                            "originalSource": media_id,
                            "mediaContentType": "VIDEO",
                            "productId": product_id,
                        }
                    ]
                }

                assoc_resp = await client.post(
                    graphql_url,
                    headers=headers,
                    json={
                        "query": associate_mutation,
                        "variables": associate_variables,
                    },
                )

                if assoc_resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"productCreateMedia HTTP {assoc_resp.status_code}",
                    }

                assoc_data = assoc_resp.json()
                assoc_errors = (
                    assoc_data.get("data", {})
                    .get("productCreateMedia", {})
                    .get("userErrors", [])
                )
                if assoc_errors:
                    error_msg = "; ".join(
                        e.get("message", "Unknown error") for e in assoc_errors
                    )
                    return {"success": False, "error": error_msg}

                return {"success": True, "product_id": product_id}

        except Exception as exc:
            logger.exception("Shopify product association exception")
            return {"success": False, "error": str(exc)}

    async def get_status(self, post_id: str) -> dict[str, Any]:
        """Get publish status for a Shopify media item.

        Falls back to mock when credentials are absent.
        """
        api_key = os.environ.get("SHOPIFY_API_KEY", "")
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")

        if not api_key or not store_url:
            return self._mock_status(post_id)

        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        headers = _headers()
        headers["Content-Type"] = "application/json"

        query = """
        query mediaStatus($id: ID!) {
            node(id: $id) {
                ... on MediaFile {
                    id
                    fileStatus
                    preview {
                        url
                    }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    graphql_url,
                    headers=headers,
                    json={"query": query, "variables": {"id": post_id}},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    node = data.get("data", {}).get("node", {})
                    return {
                        "post_id": post_id,
                        "status": node.get("fileStatus", "unknown"),
                        "preview_url": (
                            node.get("preview", {}) or {}
                        ).get("url", ""),
                    }

                return {
                    "post_id": post_id,
                    "status": "unknown",
                    "preview_url": "",
                }
        except Exception:
            logger.exception("Shopify status query error")
            return self._mock_status(post_id)

    # ------------------------------------------------------------------
    # Mock fallback
    # ------------------------------------------------------------------

    async def _mock_publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Simulate a Shopify publish (used when credentials are absent)."""
        await asyncio.sleep(1.5)

        if random.random() < 0.1:
            return {
                "success": False,
                "error": "Mock: Shopify API rate limit exceeded",
                "status": "failed",
                "platform": "shopify",
            }

        mock_id = f"sp_mock_{uuid4().hex[:8]}"
        return {
            "success": True,
            "post_id": mock_id,
            "url": "https://mock-store.myshopify.com/blogs/news/mock-post",
            "status": "published",
            "platform": "shopify",
            "published_at": datetime.now().isoformat(),
        }

    def _mock_status(self, post_id: str) -> dict[str, Any]:
        """Return mock publish status."""
        return {
            "post_id": post_id,
            "status": "published",
            "sales": 3,
        }
