"""Authenticated create/read/revoke HTTP adapter for acceptance records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from src.models.acceptance import AcceptanceCreateRequest, AcceptanceRecordResponse
from src.routers._deps import AuthContext, require_permission
from src.services.artifact_acceptance import (
    ArtifactAcceptanceError,
    extract_acceptance_key,
    get_artifact_acceptance_service,
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
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": AcceptanceCreateRequest.model_json_schema(
                    mode="validation"
                )
            }
        },
    },
}


async def _parse_acceptance_request(request: Request) -> AcceptanceCreateRequest:
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
        return AcceptanceCreateRequest.model_validate(payload)
    except ValidationError as exc:
        safe_errors = [
            {
                "type": str(item.get("type") or "value_error"),
                "loc": list(item.get("loc") or ("body",)),
                "msg": str(item.get("msg") or "Invalid request"),
            }
            for item in exc.errors(include_url=False, include_context=False)
        ]
        raise HTTPException(status_code=422, detail=safe_errors) from None


@router.post(
    "/acceptance-records",
    response_model=AcceptanceRecordResponse,
    status_code=201,
    responses={
        200: {
            "model": AcceptanceRecordResponse,
            "description": "Idempotent replay of the original acceptance record.",
        }
    },
    openapi_extra=_IDEMPOTENCY_OPENAPI_EXTRA,
)
async def create_acceptance_record(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        raw_key = extract_acceptance_key(request)
        body = await _parse_acceptance_request(request)
        record, replay = await get_artifact_acceptance_service().create(
            auth=auth,
            raw_key=raw_key,
            request=body,
        )
        response.status_code = 200 if replay else 201
        return record
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.get(
    "/acceptance-records/{acceptance_id}",
    response_model=AcceptanceRecordResponse,
)
async def read_acceptance_record(
    acceptance_id: str,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        return await get_artifact_acceptance_service().read(
            auth=auth,
            acceptance_id=acceptance_id,
        )
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.post(
    "/acceptance-records/{acceptance_id}/revoke",
    response_model=AcceptanceRecordResponse,
)
async def revoke_acceptance_record(
    acceptance_id: str,
    auth: AuthContext = Depends(require_permission("artifact:accept")),
) -> AcceptanceRecordResponse:
    try:
        return await get_artifact_acceptance_service().revoke(
            auth=auth,
            acceptance_id=acceptance_id,
        )
    except ArtifactAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
