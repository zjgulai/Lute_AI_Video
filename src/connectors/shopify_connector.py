"""Shopify connector — publish content to Shopify via the Admin API.

Uses the Shopify Admin API (GraphQL) to upload video files and associate
them with products. Falls back to mock mode when credentials are absent.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from src.config import SHOPIFY_GRAPHQL_URL_TEMPLATE, SHOPIFY_METRICS_SHOPIFYQL_QUERY
from src.connectors.base import PlatformConnector
from src.tasks.metrics_poller import PlatformMetricsError, classify_platform_http_status

logger = logging.getLogger(__name__)

# Shopify Admin GraphQL endpoint (version 2024-07 or later supports fileCreate)
_SHOPIFY_GRAPHQL_URL = SHOPIFY_GRAPHQL_URL_TEMPLATE


def _is_mock_mode() -> bool:
    """Return True when no real Shopify API credentials are available.

    Checks SHOPIFY_ACCESS_TOKEN (canonical), falls back to SHOPIFY_API_KEY (legacy).
    Ref: debt-audit-report-2026-06-09.md item CFG-2.
    """
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN") or os.environ.get("SHOPIFY_API_KEY", "")
    store_url = os.environ.get("SHOPIFY_STORE_URL", "")
    return not token or not store_url


def _admin_url() -> str:
    """Return the base admin URL for the configured Shopify store."""
    store = os.environ.get("SHOPIFY_STORE_URL", "mock-store.myshopify.com")
    return f"https://{store}/admin"


def _headers() -> dict[str, Any]:
    """Build headers for Shopify Admin API requests."""
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN") or os.environ.get(
        "SHOPIFY_API_KEY", ""
    )

    if token:
        return {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        }
    # Fallback to basic auth (API key + password)
    return {
        "Content-Type": "application/json",
    }


def _shopify_metrics_query(post_id: str) -> str:
    template = os.environ.get(
        "SHOPIFY_METRICS_SHOPIFYQL_QUERY",
        SHOPIFY_METRICS_SHOPIFYQL_QUERY,
    )
    safe_post_id = str(post_id).replace("\\", "\\\\").replace("'", "\\'")
    return template.replace("{post_id}", safe_post_id)


def _summarize_graphql_errors(errors: Any) -> str:
    if not isinstance(errors, list):
        return str(errors)
    messages = [
        str(error.get("message", error)) if isinstance(error, dict) else str(error)
        for error in errors
    ]
    return "; ".join(messages)


def _classify_shopify_error(errors: Any) -> str:
    value = _summarize_graphql_errors(errors).lower()
    if any(marker in value for marker in ("access denied", "scope", "permission", "protected customer", "token")):
        return "auth"
    if any(marker in value for marker in ("throttle", "rate limit", "too many")):
        return "rate_limit"
    if "not found" in value:
        return "not_found"
    if any(marker in value for marker in ("parse", "syntax", "field", "schema")):
        return "schema_drift"
    return "transient"


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        amount = value.get("amount")
        return _to_number(amount)
    if isinstance(value, str):
        normalized = value.replace(",", "").replace("$", "").strip()
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _iter_shopifyql_rows(table_data: Any) -> list[dict[str, Any]]:
    if not isinstance(table_data, dict):
        raise PlatformMetricsError("schema_drift", "ShopifyQL tableData is missing")
    columns = table_data.get("columns")
    rows = table_data.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise PlatformMetricsError(
            "schema_drift",
            "ShopifyQL tableData missing columns or rows list",
        )
    column_names = [
        str(column.get("name") or column.get("displayName") or "")
        for column in columns
        if isinstance(column, dict)
    ]
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized_rows.append(row)
            continue
        if isinstance(row, list):
            normalized_rows.append(
                {
                    column_names[index]: value
                    for index, value in enumerate(row)
                    if index < len(column_names) and column_names[index]
                }
            )
    return normalized_rows


def _normalize_shopifyql_metrics(table_data: Any) -> dict[str, Any]:
    rows = _iter_shopifyql_rows(table_data)
    if not rows:
        raise PlatformMetricsError("not_found", "ShopifyQL returned no metric rows")

    totals: dict[str, float] = {}
    for row in rows:
        for key, value in row.items():
            number = _to_number(value)
            if number is not None:
                totals[str(key)] = totals.get(str(key), 0.0) + number

    metrics: dict[str, Any] = {}
    revenue = (
        totals.get("total_sales")
        or totals.get("gross_sales")
        or totals.get("net_sales")
        or totals.get("revenue")
    )
    orders = totals.get("orders")
    sessions = totals.get("sessions")
    if revenue is not None:
        metrics["revenue"] = revenue
    if orders is not None:
        metrics["orders"] = int(orders)
        metrics["sales"] = int(orders)
    if sessions is not None:
        metrics["views"] = int(sessions)
    if orders is not None and sessions:
        metrics["cvr"] = orders / sessions
    return metrics


class ShopifyConnector(PlatformConnector):
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def fetch_metrics(self, post_id: str) -> dict[str, Any]:
        """Fetch performance metrics for a Shopify media/post id.

        Uses Shopify Admin GraphQL `shopifyqlQuery`. The default query returns
        store/reporting analytics rather than media-file analytics; deployments
        that need stricter post-level filtering should set
        `SHOPIFY_METRICS_SHOPIFYQL_QUERY` with a `{post_id}` placeholder once
        the selected Shopify dimension is confirmed for the pilot.
        """
        token = os.environ.get("SHOPIFY_ACCESS_TOKEN") or os.environ.get(
            "SHOPIFY_API_KEY", ""
        )
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")
        if not token or not store_url:
            raise PlatformMetricsError(
                "auth",
                "SHOPIFY_ACCESS_TOKEN/SHOPIFY_API_KEY and SHOPIFY_STORE_URL are required for Shopify metrics",
            )

        query = _shopify_metrics_query(post_id)
        resp = await self._post_shopifyql_query(store_url, query)
        if resp.status_code != 200:
            raise PlatformMetricsError(
                classify_platform_http_status(resp.status_code),
                f"Shopify metrics HTTP {resp.status_code}",
            )

        data = resp.json()
        errors = data.get("errors")
        if errors:
            raise PlatformMetricsError(
                _classify_shopify_error(errors),
                f"Shopify metrics GraphQL errors: {_summarize_graphql_errors(errors)}",
            )
        response = data.get("data", {}).get("shopifyqlQuery")
        if not isinstance(response, dict):
            raise PlatformMetricsError(
                "schema_drift",
                "Shopify metrics response missing data.shopifyqlQuery",
            )
        parse_errors = response.get("parseErrors") or []
        if parse_errors:
            raise PlatformMetricsError(
                "schema_drift",
                f"ShopifyQL parse errors: {parse_errors}",
            )
        table_data = response.get("tableData")
        metrics = _normalize_shopifyql_metrics(table_data)
        if not metrics:
            raise PlatformMetricsError(
                "schema_drift",
                "ShopifyQL tableData has no supported metric columns",
            )
        return metrics

    async def _post_shopifyql_query(self, store_url: str, shopifyql: str) -> httpx.Response:
        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        graphql_query = """
        query ShopifyMetrics($query: String!) {
            shopifyqlQuery(query: $query) {
                tableData {
                    columns {
                        name
                        dataType
                        displayName
                    }
                    rows
                }
                parseErrors
            }
        }
        """
        payload = {"query": graphql_query, "variables": {"query": shopifyql}}
        if self._http_client is not None:
            return await self._http_client.post(
                graphql_url,
                headers=_headers(),
                json=payload,
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                graphql_url,
                headers=_headers(),
                json=payload,
            )

    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Publish content to Shopify.

        Accepts content with fields:
            title        (str) — video title
            video_path   (str) — local file path to the video
            product_name (str) — product name to associate the video with

        Returns dict with keys:
            success, post_id, url, status, error, platform, published_at
        """
        token = os.environ.get("SHOPIFY_ACCESS_TOKEN") or os.environ.get(
            "SHOPIFY_API_KEY", ""
        )
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")

        if not token or not store_url:
            logger.info(
                "SHOPIFY_ACCESS_TOKEN/SHOPIFY_API_KEY or SHOPIFY_STORE_URL not set — using mock publish"
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
        token = os.environ.get("SHOPIFY_ACCESS_TOKEN") or os.environ.get(
            "SHOPIFY_API_KEY", ""
        )
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")

        if not token or not store_url:
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
