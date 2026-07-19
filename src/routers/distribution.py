"""Authenticated distribution and acceptance-backed publish adapters."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BeforeValidator, ValidationError

from src.models.publish_attempt import (
    DurableTikTokStatusResponse,
    PublishAttemptErrorResponse,
    PublishAttemptReadbackResponse,
    PublishAttemptRequest,
    PublishAttemptResponse,
)
from src.routers._deps import (
    AuthContext,
    require_permission,
    verify_api_key,
)
from src.services.publish_attempt import (
    PublishAttemptError,
    get_publish_attempt_service,
)
from src.storage.publish_attempt_repository import PublishAttemptStoreUnavailable

router = APIRouter()

_LEGACY_VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
_LEGACY_VIDEO_ID_RE = re.compile(_LEGACY_VIDEO_ID_PATTERN)
_PUBLISH_PERMISSION = require_permission("artifact:publish")
_ATTEMPT_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TIKTOK_POST_ID_PATTERN = r"^[1-9][0-9]*$"

_PUBLISH_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": PublishAttemptRequest.model_json_schema(
                    mode="validation"
                )
            }
        },
    },
}

_PUBLISH_RESPONSES = {
    401: {"description": "Invalid API key"},
    403: {"description": "Insufficient permission"},
    404: {"model": PublishAttemptErrorResponse},
    409: {"model": PublishAttemptErrorResponse},
    422: {"description": "Safe validation projection"},
    500: {"model": PublishAttemptErrorResponse},
    502: {"model": PublishAttemptErrorResponse},
    503: {"model": PublishAttemptErrorResponse},
}


def _validate_legacy_video_id(value: object) -> object:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or _LEGACY_VIDEO_ID_RE.fullmatch(value) is None
    ):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["path", "video_id"],
                    "msg": "Invalid path parameter",
                }
            ],
        )
    return value


async def _parse_publish_request(request: Request) -> PublishAttemptRequest:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=[
                {"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON"}
            ],
        ) from None

    try:
        return PublishAttemptRequest.model_validate(payload)
    except ValidationError as exc:
        safe_errors = [
            {
                "type": str(item.get("type") or "value_error"),
                "loc": list(item.get("loc") or ("body",)),
                "msg": str(item.get("msg") or "Invalid request"),
            }
            for item in exc.errors(
                include_url=False,
                include_context=False,
            )
        ]
        raise HTTPException(status_code=422, detail=safe_errors) from None


@router.post(
    "/distribution/publish",
    response_model=PublishAttemptResponse,
    responses=_PUBLISH_RESPONSES,
    openapi_extra=_PUBLISH_OPENAPI_EXTRA,
)
async def distribution_publish(
    request: Request,
    auth: AuthContext = Depends(_PUBLISH_PERMISSION),
) -> PublishAttemptResponse:
    """Execute one canonical acceptance-backed publish attempt."""
    body = await _parse_publish_request(request)
    try:
        return await get_publish_attempt_service().execute(
            auth=auth,
            request=body,
            route_kind="canonical",
        )
    except PublishAttemptError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail.model_dump(mode="json"),
        ) from None


@router.get(
    "/distribution/publish-attempts/{attempt_id}",
    response_model=PublishAttemptReadbackResponse,
    responses={
        401: {"description": "Invalid API key"},
        403: {"description": "Insufficient permission"},
        404: {"description": "Publish attempt not found"},
        503: {"description": "Publish attempt store unavailable"},
    },
)
async def distribution_publish_attempt(
    attempt_id: Annotated[
        str,
        Path(
            min_length=36,
            max_length=36,
            pattern=_ATTEMPT_ID_PATTERN,
        ),
    ],
    auth: AuthContext = Depends(_PUBLISH_PERMISSION),
) -> PublishAttemptReadbackResponse:
    """Return one safe tenant-bound durable publish-attempt projection."""
    try:
        readback = await get_publish_attempt_service().get_attempt_readback(
            auth=auth,
            attempt_id=attempt_id,
        )
    except PublishAttemptStoreUnavailable:
        raise HTTPException(
            status_code=503,
            detail={"code": "publish_attempt_store_unavailable"},
        ) from None
    if readback is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "publish_attempt_not_found"},
        )
    return readback


@router.get(
    "/distribution/status/{platform}/{post_id}",
    response_model=DurableTikTokStatusResponse,
    deprecated=True,
)
async def distribution_status(
    platform: str,
    post_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=128,
            pattern=_TIKTOK_POST_ID_PATTERN,
        ),
    ],
    auth: AuthContext = Depends(_PUBLISH_PERMISSION),
) -> DurableTikTokStatusResponse:
    """Read one trusted persisted TikTok receipt without a provider call."""
    if platform == "shopify":
        raise HTTPException(
            status_code=410,
            detail={"code": "distribution_status_route_deprecated"},
        )
    if platform != "tiktok":
        raise HTTPException(
            status_code=400,
            detail={"code": "distribution_status_platform_unsupported"},
        )
    try:
        status = await get_publish_attempt_service().get_durable_tiktok_status(
            auth=auth,
            post_id=post_id,
        )
    except PublishAttemptStoreUnavailable:
        raise HTTPException(
            status_code=503,
            detail={"code": "publish_attempt_store_unavailable"},
        )
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "distribution_status_not_found"},
        )
    return status


@router.get("/distribution/platforms", dependencies=[Depends(verify_api_key)])
async def distribution_platforms():
    """List available distribution platforms and their connection status.

    Returns:
        Array of platform metadata dicts.
    """
    from src.connectors.registry import inspect_publish_readiness

    return [
        {
            "id": "tiktok",
            "name": "TikTok",
            "connected": inspect_publish_readiness("tiktok").ready,
        },
        {
            "id": "shopify",
            "name": "Shopify",
            "connected": inspect_publish_readiness("shopify").ready,
        },
    ]


@router.post(
    "/publish/{video_id}",
    response_model=PublishAttemptResponse,
    responses=_PUBLISH_RESPONSES,
    deprecated=True,
    openapi_extra=_PUBLISH_OPENAPI_EXTRA,
)
async def publish_video(
    request: Request,
    video_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=128,
            pattern=_LEGACY_VIDEO_ID_PATTERN,
        ),
        BeforeValidator(_validate_legacy_video_id),
    ],
    auth: AuthContext = Depends(_PUBLISH_PERMISSION),
) -> PublishAttemptResponse:
    """Execute one publish attempt through the deprecated path adapter."""
    del video_id
    body = await _parse_publish_request(request)
    try:
        return await get_publish_attempt_service().execute(
            auth=auth,
            request=body,
            route_kind="legacy_adapter",
        )
    except PublishAttemptError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail.model_dump(mode="json"),
        ) from None
