"""Authenticated tenant-bound readback for durable async submissions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.routers._deps import AuthContext, verify_api_key
from src.services.submission_idempotency import (
    SubmissionIdempotencyError,
    extract_idempotency_key,
    get_submission_idempotency_service,
)

router = APIRouter()

_IDEMPOTENCY_OPENAPI_EXTRA = {
    "parameters": [
        {
            "name": "Idempotency-Key",
            "in": "header",
            "required": True,
            "schema": {
                "type": "string",
                "minLength": 16,
                "maxLength": 128,
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$",
            },
        }
    ]
}


def _raise_http_error(exc: SubmissionIdempotencyError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.get(
    "/submissions/idempotency",
    openapi_extra=_IDEMPOTENCY_OPENAPI_EXTRA,
)
async def get_submission_by_idempotency_key(
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
) -> dict[str, object]:
    """Read one existing submission in the authenticated tenant namespace."""

    try:
        raw_key = extract_idempotency_key(request)
        return await get_submission_idempotency_service().readback(
            tenant_id=auth.tenant_id,
            raw_key=raw_key,
        )
    except SubmissionIdempotencyError as exc:
        _raise_http_error(exc)

    raise AssertionError("unreachable")
