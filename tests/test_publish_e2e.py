"""Separately authorized acceptance-bound live publish evidence.

W1-23 only collects this module. A later W1-26 operator run may execute the
single canonical mutation after supplying every explicit authorization input.
"""

from __future__ import annotations

import os
import re

import pytest

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _live_publish_authorized() -> bool:
    return (
        os.environ.get("RUN_LIVE_PUBLISH") == "1"
        and _UUID4_RE.fullmatch(
            os.environ.get("LIVE_PUBLISH_ACCEPTANCE_ID", "")
        )
        is not None
        and os.environ.get("LIVE_PUBLISH_PLATFORM") in {"tiktok", "shopify"}
        and bool(os.environ.get("LIVE_PUBLISH_API_KEY"))
    )


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _live_publish_authorized(),
        reason=(
            "requires RUN_LIVE_PUBLISH=1, one exact acceptance ID, "
            "one exact platform, and an explicit publish API key"
        ),
    ),
]


@pytest.mark.asyncio
async def test_acceptance_bound_distribution_publish() -> None:
    from httpx import ASGITransport, AsyncClient

    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/distribution/publish",
            headers={"X-API-Key": os.environ["LIVE_PUBLISH_API_KEY"]},
            json={
                "acceptance_id": os.environ[
                    "LIVE_PUBLISH_ACCEPTANCE_ID"
                ],
                "platform": os.environ["LIVE_PUBLISH_PLATFORM"],
                "metadata": {
                    "title": "Authorized publish acceptance test",
                    "description": "Separately authorized W1-26 evidence",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "published"
    assert payload["acceptance_consumed"] is True
    assert payload["retry_allowed"] is False
