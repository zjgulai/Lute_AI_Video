from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

import src.routers.distribution as distribution


def _human_acceptance(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "human",
        "reviewer": "pray",
        "delivery_accepted": True,
        "publish_allowed": True,
        "approved_brand_token_write": False,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_distribution_publish_blocks_without_human_delivery_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(platform: str, content: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("connector must not be called before human acceptance")

    monkeypatch.setattr("src.connectors.registry.publish_to_platform", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        await distribution.distribution_publish({
            "platform": "tiktok",
            "content": {"title": "LLM suggested publish"},
        })

    assert exc.value.status_code == 403
    assert "Human delivery acceptance" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_distribution_publish_ignores_llm_suggestion_as_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(platform: str, content: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("connector must not be called for LLM-sourced approval")

    monkeypatch.setattr("src.connectors.registry.publish_to_platform", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        await distribution.distribution_publish({
            "platform": "tiktok",
            "content": {
                "title": "AI suggested publish",
                "delivery_acceptance": _human_acceptance(source="llm"),
            },
        })

    assert exc.value.status_code == 403
    assert "human decision source" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_distribution_publish_rejects_approved_brand_token_write_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(platform: str, content: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("connector must not be called for token-write claims")

    monkeypatch.setattr("src.connectors.registry.publish_to_platform", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        await distribution.distribution_publish({
            "platform": "tiktok",
            "content": {
                "title": "Unsafe publish",
                "delivery_acceptance": _human_acceptance(approved_brand_token_write=True),
            },
        })

    assert exc.value.status_code == 403
    assert "approved brand token" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_distribution_publish_calls_connector_after_human_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_publish(platform: str, content: dict[str, Any]) -> dict[str, Any]:
        calls.append((platform, content))
        return {"success": True, "post_id": "post_fixture", "url": "https://example.test/post"}

    monkeypatch.setattr("src.connectors.registry.publish_to_platform", fake_publish)
    monkeypatch.setattr(distribution, "HAS_STORAGE", False)

    result = await distribution.distribution_publish({
        "platform": "tiktok",
        "content": {
            "title": "Human approved publish",
            "delivery_acceptance": _human_acceptance(),
        },
    })

    assert result["success"] is True
    assert calls == [("tiktok", {"title": "Human approved publish", "delivery_acceptance": _human_acceptance()})]


@pytest.mark.asyncio
async def test_publish_video_blocks_before_file_lookup_without_human_acceptance() -> None:
    with pytest.raises(HTTPException) as exc:
        await distribution.publish_video(
            "missing_video",
            {
                "platforms": ["tiktok"],
                "metadata": {"video_path": "/tmp/does-not-exist.mp4"},
            },
        )

    assert exc.value.status_code == 403
    assert "Human delivery acceptance" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_publish_video_calls_engine_after_human_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any], list[str]]] = []

    class FakePublishEngine:
        async def publish(
            self,
            video_path: str,
            metadata: dict[str, Any],
            platforms: list[str],
        ) -> list[SimpleNamespace]:
            calls.append((video_path, metadata, platforms))
            return [
                SimpleNamespace(
                    platform="tiktok",
                    success=True,
                    post_id="post_fixture",
                    post_url="https://example.test/post",
                    error="",
                )
            ]

    monkeypatch.setattr("src.connectors.publish_engine.PublishEngine", FakePublishEngine)
    monkeypatch.setattr(distribution, "HAS_STORAGE", False)

    result = await distribution.publish_video(
        "video_fixture",
        {
            "platforms": ["tiktok"],
            "metadata": {
                "video_path": "/tmp/video_fixture.mp4",
                "delivery_acceptance": _human_acceptance(),
            },
        },
    )

    assert result == [
        {
            "platform": "tiktok",
            "success": True,
            "post_id": "post_fixture",
            "post_url": "https://example.test/post",
            "error": "",
        }
    ]
    assert calls == [
        (
            "/tmp/video_fixture.mp4",
            {
                "video_path": "/tmp/video_fixture.mp4",
                "delivery_acceptance": _human_acceptance(),
            },
            ["tiktok"],
        )
    ]
