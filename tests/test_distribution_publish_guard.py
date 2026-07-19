"""Strict W1-23 regressions for the distribution mutation authority boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.models.publish_attempt import PublishAttemptRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER_SOURCE = (REPO_ROOT / "src" / "routers" / "distribution.py").read_text()
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "acceptance_id": ACCEPTANCE_ID,
        "platform": "tiktok",
        "metadata": {"title": "Reviewed campaign"},
    }
    body.update(overrides)
    return body


def _assert_rejected(body: dict[str, Any], expected_loc: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError) as exc:
        PublishAttemptRequest.model_validate(body)
    assert expected_loc in {tuple(error["loc"]) for error in exc.value.errors()}


def test_missing_acceptance_id_fails_at_strict_contract_before_service() -> None:
    body = _body()
    body.pop("acceptance_id")

    _assert_rejected(body, ("acceptance_id",))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "delivery_acceptance",
            {
                "source": "human",
                "reviewer": "caller-reviewer",
                "delivery_accepted": True,
                "publish_allowed": True,
            },
        ),
        ("content", {"title": "legacy connector content"}),
        ("source", "human"),
        ("reviewer", "caller-reviewer"),
    ],
)
def test_legacy_human_assertions_are_unknown_input(field: str, value: object) -> None:
    _assert_rejected(_body(**{field: value}), (field,))


def test_approved_brand_token_write_claim_is_unknown_input() -> None:
    _assert_rejected(
        _body(approved_brand_token_write=True),
        ("approved_brand_token_write",),
    )


def test_client_video_path_is_rejected_and_filesystem_lookup_is_absent() -> None:
    _assert_rejected(
        _body(
            metadata={
                "title": "Reviewed campaign",
                "video_path": "/tmp/caller-selected.mp4",
            }
        ),
        ("metadata", "video_path"),
    )
    assert "OUTPUT_DIR" not in ROUTER_SOURCE
    assert ".rglob(" not in ROUTER_SOURCE


def test_multi_platform_legacy_array_is_unknown_input() -> None:
    _assert_rejected(
        _body(platforms=["tiktok", "shopify"]),
        ("platforms",),
    )


def test_mutations_use_only_specialized_publish_attempt_service() -> None:
    for forbidden in (
        "PublishEngine",
        "PublishLogRepository",
        "HAS_STORAGE",
        "publish_to_platform",
        "_extract_publish_authorization",
        "_require_human_publish_authorization",
    ):
        assert forbidden not in ROUTER_SOURCE
    assert "get_publish_attempt_service" in ROUTER_SOURCE
    assert ROUTER_SOURCE.count("get_publish_attempt_service().execute(") == 2
