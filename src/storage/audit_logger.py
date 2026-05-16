"""Audit logger for business-critical events (TODO-C10 / task_plan 3.15).

Captures admin lifecycle events (login/logout/tenant CRUD/api_key revoke)
and pipeline lifecycle events into the audit_logs table. Non-blocking by
design: failures here MUST NOT break the calling endpoint. Caller logs
the event AFTER the business operation succeeds.

Usage:

    from src.storage.audit_logger import audit_log

    await audit_log(
        actor_type="admin",
        actor_id=admin_id,
        action="tenant.create",
        resource_type="tenant",
        resource_id=new_tenant_id,
        payload={"display_name": display_name},
        success=True,
        client_ip=request.client.host,
        trace_id=request.headers.get("x-trace-id"),
    )

Event taxonomy (extensible):
- admin.login.success / admin.login.failure / admin.logout
- tenant.create / tenant.update / tenant.disable
- api_key.create / api_key.revoke
- pipeline.start / pipeline.complete / pipeline.fail
- (more added as needed)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.storage.db import get_pool, get_sqlite_conn

logger = logging.getLogger(__name__)


async def audit_log(
    *,
    actor_type: str,
    action: str,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
    success: bool = True,
    client_ip: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Log a business event to audit_logs. Non-blocking: never raises."""
    record_id = str(uuid.uuid4())
    payload_json = json.dumps(payload or {}, default=str)

    try:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_logs
                        (id, actor_type, actor_id, action, resource_type,
                         resource_id, payload, success, client_ip, trace_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
                    """,
                    record_id, actor_type, actor_id, action, resource_type,
                    resource_id, payload_json, success, client_ip, trace_id,
                )
                return

        sqlite_conn = get_sqlite_conn()
        if sqlite_conn is not None:
            sqlite_conn.execute(
                """
                INSERT INTO audit_logs
                    (id, actor_type, actor_id, action, resource_type,
                     resource_id, payload, success, client_ip, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id, actor_type, actor_id, action, resource_type,
                    resource_id, payload_json, 1 if success else 0,
                    client_ip, trace_id,
                ),
            )
            sqlite_conn.commit()
    except Exception as exc:
        logger.warning(
            "audit_log: persistence failed action=%s actor=%s err=%s",
            action, actor_id, str(exc)[:200],
        )
