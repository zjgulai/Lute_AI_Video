from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline import authorized_live_poyo_runtime as runtime
from src.pipeline.authorized_live_poyo_submitter import (
    AUTHORIZED_LIVE_POYO_TRANSPORT_ENV,
    REQUIRED_VIDEO_REFERENCE_REFS,
)


def test_runtime_factory_returns_none_without_transport_gate_before_reading_private_inputs(tmp_path: Path):
    calls: list[str] = []

    submitter = runtime.build_authorized_live_poyo_runtime_submitter(
        env={},
        http_client_factory=lambda base_url: calls.append(base_url) or _FakeHttpClient(),
    )

    assert submitter is None
    assert calls == []


def test_runtime_factory_requires_key_and_private_payload_path_when_enabled(tmp_path: Path):
    env = {AUTHORIZED_LIVE_POYO_TRANSPORT_ENV: "1"}

    with pytest.raises(ValueError, match="POYO_API_KEY is required"):
        runtime.build_authorized_live_poyo_runtime_submitter(env=env)

    env[runtime.POYO_API_KEY_ENV] = "sk_fixture_private_token"

    with pytest.raises(ValueError, match="AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS is required"):
        runtime.build_authorized_live_poyo_runtime_submitter(env=env)


def test_http_client_posts_json_with_injected_headers_without_env_access():
    urlopen = _FakeUrlOpen(response={"code": 200, "data": {"task_id": "poyo_task_1"}})
    client = runtime.AuthorizedLivePoyoHttpClient(
        base_url="https://api.poyo.example.test/",
        urlopen=urlopen,
    )

    response = client.post_json(
        path="/api/generate/submit",
        headers={"Authorization": "Bearer sk_fixture_private_token", "Content-Type": "application/json"},
        body={"model": "gpt-image-2", "input": {"prompt": "private prompt"}},
    )

    request = urlopen.requests[0]
    assert response == {"code": 200, "data": {"task_id": "poyo_task_1"}}
    assert request.full_url == "https://api.poyo.example.test/api/generate/submit"
    assert request.get_method() == "POST"
    assert json.loads((request.data or b"").decode("utf-8")) == {
        "model": "gpt-image-2",
        "input": {"prompt": "private prompt"},
    }
    assert request.headers["Authorization"] == "Bearer sk_fixture_private_token"


def test_payload_loader_rejects_formal_repo_path(tmp_path: Path):
    formal_path = REPO_ROOT / "docs" / "poyo-private-payloads.json"

    with pytest.raises(ValueError, match="private poyo payloads must be under tmp/ or outside the repository"):
        runtime.load_authorized_live_poyo_payloads(formal_path)


def test_payload_loader_loads_private_payloads(tmp_path: Path):
    payload_path = _write_payloads(tmp_path)

    payloads = runtime.load_authorized_live_poyo_payloads(payload_path)

    assert sorted(payloads) == sorted(_payload_job_ids())
    assert payloads["momcozy_sterilizer_main_45_image_authorized_live_fixture"].input_payload == {
        "prompt": "private main image prompt",
        "size": "1:1",
        "quality": "low",
    }


def test_runtime_factory_builds_submitter_from_private_payloads_and_injected_http_client(tmp_path: Path):
    payload_path = _write_payloads(tmp_path)
    calls: list[str] = []
    http_client = _FakeHttpClient()
    env = {
        AUTHORIZED_LIVE_POYO_TRANSPORT_ENV: "1",
        runtime.POYO_API_KEY_ENV: "sk_fixture_private_token",
        runtime.AUTHORIZED_LIVE_POYO_PAYLOADS_ENV: str(payload_path),
        runtime.POYO_API_BASE_URL_ENV: "https://api.poyo.example.test/",
    }

    submitter = runtime.build_authorized_live_poyo_runtime_submitter(
        env=env,
        http_client_factory=lambda base_url: calls.append(base_url) or http_client,
    )

    assert submitter is not None
    response = submitter(_image_spec())

    assert calls == ["https://api.poyo.example.test"]
    assert response["provider_job_id"] == "poyo_task_1"
    assert response["media_url"] == "https://cdn.example.test/asset.png"
    assert "sk_fixture_private_token" not in str(response)
    assert "private main image prompt" not in str(response)
    assert http_client.posts[0]["headers"]["Authorization"] == "Bearer sk_fixture_private_token"
    assert http_client.posts[0]["body"]["input"]["prompt"] == "private main image prompt"


class _FakeHttpClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.posts.append({"path": path, "headers": dict(headers), "body": dict(body)})
        return {"code": 200, "data": {"task_id": "poyo_task_1"}}

    def get_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
    ) -> Mapping[str, Any]:
        self.gets.append({"path": path, "headers": dict(headers)})
        return {
            "code": 200,
            "data": {
                "status": "finished",
                "files": [{"file_url": "https://cdn.example.test/asset.png"}],
            },
        }


class _FakeUrlOpen:
    def __init__(self, *, response: Mapping[str, Any]) -> None:
        self.response = response
        self.requests: list[Any] = []

    def __call__(self, http_request: Any, *, timeout: float) -> _FakeUrlOpenResponse:
        self.requests.append(http_request)
        assert timeout == 90.0
        return _FakeUrlOpenResponse(self.response)


class _FakeUrlOpenResponse:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response

    def __enter__(self) -> _FakeUrlOpenResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.response).encode("utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_payloads(tmp_path: Path) -> Path:
    path = tmp_path / "authorized-live-poyo-payloads.json"
    path.write_text(json.dumps({"payloads": _payloads()}, ensure_ascii=False))
    return path


def _payloads() -> list[dict[str, Any]]:
    return [
        {
            "job_id": "momcozy_sterilizer_main_45_image_authorized_live_fixture",
            "model": "gpt-image-2",
            "input_payload": {"prompt": "private main image prompt", "size": "1:1", "quality": "low"},
            "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
        },
        {
            "job_id": "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture",
            "model": "gpt-image-2",
            "input_payload": {"prompt": "private UV benefit prompt", "size": "4:5", "quality": "low"},
            "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
        },
        {
            "job_id": "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture",
            "model": "gpt-image-2",
            "input_payload": {"prompt": "private kitchen scene prompt", "size": "4:5", "quality": "low"},
            "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
        },
        {
            "job_id": "momcozy_sterilizer_i2v_15s_authorized_live_fixture",
            "model": "seedance-2",
            "input_payload": {
                "prompt": "private video prompt",
                "reference_image_urls": list(REQUIRED_VIDEO_REFERENCE_REFS),
                "aspect_ratio": "9:16",
                "resolution": "480p",
                "duration": 15,
            },
            "artifact_ref": "artifact://authorized-live/momcozy-sterilizer-i2v-15s-seedance-2",
        },
    ]


def _payload_job_ids() -> list[str]:
    return [payload["job_id"] for payload in _payloads()]


def _image_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id="momcozy_sterilizer_main_45_image_authorized_live_fixture",
        provider="poyo",
        model="gpt-image-2",
        scenario="toolbox",
        step_name="momcozy_sterilizer_main_45_image",
        prompt_hash="sha256:momcozy_sterilizer_main_45_image_fixture",
        prompt_compile_id="pci_momcozy_sterilizer_main_45_image_fixture",
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=2.5,
    )
