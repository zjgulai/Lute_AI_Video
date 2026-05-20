"""Shared utilities for admin sub-routers."""

import logging
import re

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Lowercase alphanumeric + hyphens, 3-32 chars, no leading/trailing hyphens.
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")


def _validate_tenant_id(tenant_id: str) -> None:
    """Validate tenant_id format, raise 422 on mismatch."""
    if not _TENANT_ID_RE.match(tenant_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid tenant_id format. Must be 3-32 characters, "
                "lowercase alphanumeric with optional hyphens, "
                "no leading/trailing hyphens."
            ),
        )
