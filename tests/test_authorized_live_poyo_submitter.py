from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline.authorized_live_poyo_submitter import (
    REQUIRED_VIDEO_REFERENCE_REFS,
    AuthorizedLivePoyoPayload,
    AuthorizedLivePoyoSubmitter,
)


def test_submitter_rejects_out_of_scope_job_before_transport_call():
    transport = FakePoyoTransport()
    submitter = AuthorizedLivePoyoSubmitter(transport=transport, payloads=_payloads())
    spec = _image_spec(provider="runway")

    with pytest.raises(ValueError, match="provider must be poyo"):
        submitter(spec)

    assert transport.calls == []


def test_submitter_maps_authorized_image_job_without_prompt_leakage():
    transport = FakePoyoTransport()
    payloads = _payloads()
    submitter = AuthorizedLivePoyoSubmitter(transport=transport, payloads=payloads)

    response = submitter(_image_spec())

    assert len(transport.calls) == 1
    assert transport.calls[0]["model"] == "gpt-image-2"
    assert transport.calls[0]["input_payload"]["prompt"] == "private prompt for main image"
    assert response["provider_job_id"] == "poyo:job:1"
    assert response["artifact_ref"] == payloads["momcozy_sterilizer_main_45_image_authorized_live_fixture"].artifact_ref
    assert response["media_url"] == "https://cdn.example.test/poyo-job-1.png"
    assert "private prompt" not in str(response)
    assert "input_payload" not in response


def test_submitter_requires_video_to_reference_three_image_assets():
    transport = FakePoyoTransport()
    submitter = AuthorizedLivePoyoSubmitter(transport=transport, payloads=_payloads())
    spec = _video_spec(reference_asset_ids=[REQUIRED_VIDEO_REFERENCE_REFS[0]])

    with pytest.raises(ValueError, match="video job must reference the three authorized image artifacts"):
        submitter(spec)

    assert transport.calls == []


def test_submitter_maps_video_job_with_required_image_refs():
    transport = FakePoyoTransport()
    payloads = _payloads()
    submitter = AuthorizedLivePoyoSubmitter(transport=transport, payloads=payloads)

    response = submitter(_video_spec(reference_asset_ids=list(REQUIRED_VIDEO_REFERENCE_REFS)))

    assert len(transport.calls) == 1
    assert transport.calls[0]["model"] == "seedance-2"
    assert transport.calls[0]["input_payload"]["image_urls"] == list(REQUIRED_VIDEO_REFERENCE_REFS)
    assert response["provider_job_id"] == "poyo:job:1"
    assert response["artifact_ref"] == payloads["momcozy_sterilizer_i2v_15s_authorized_live_fixture"].artifact_ref
    assert response["media_url"] == "https://cdn.example.test/poyo-job-1.mp4"
    assert "private prompt" not in str(response)


def test_submitter_propagates_transport_failure_without_retry():
    transport = FakePoyoTransport(raise_on_submit=True)
    submitter = AuthorizedLivePoyoSubmitter(transport=transport, payloads=_payloads())

    with pytest.raises(RuntimeError, match="fake provider rejection"):
        submitter(_image_spec())

    assert len(transport.calls) == 1


def test_submitter_module_has_no_provider_client_or_env_access():
    source = (REPO_ROOT / "src" / "pipeline" / "authorized_live_poyo_submitter.py").read_text()

    assert "PoyoClient" not in source
    assert "httpx" not in source
    assert "os.environ" not in source
    assert "POYO_API_KEY" not in source


class FakePoyoTransport:
    def __init__(self, *, raise_on_submit: bool = False) -> None:
        self.raise_on_submit = raise_on_submit
        self.calls: list[dict[str, Any]] = []

    def submit_once(self, *, model: str, input_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append({"model": model, "input_payload": dict(input_payload)})
        if self.raise_on_submit:
            raise RuntimeError("fake provider rejection")
        suffix = "mp4" if model == "seedance-2" else "png"
        return {
            "provider_job_id": f"poyo:job:{len(self.calls)}",
            "file_url": f"https://cdn.example.test/poyo-job-{len(self.calls)}.{suffix}",
            "thumbnail_url": f"https://cdn.example.test/poyo-job-{len(self.calls)}-thumb.jpg",
        }


def _payloads() -> dict[str, AuthorizedLivePoyoPayload]:
    return {
        "momcozy_sterilizer_main_45_image_authorized_live_fixture": AuthorizedLivePoyoPayload(
            job_id="momcozy_sterilizer_main_45_image_authorized_live_fixture",
            model="gpt-image-2",
            input_payload={"prompt": "private prompt for main image", "size": "1:1", "quality": "low"},
            artifact_ref="artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
        ),
        "momcozy_sterilizer_i2v_15s_authorized_live_fixture": AuthorizedLivePoyoPayload(
            job_id="momcozy_sterilizer_i2v_15s_authorized_live_fixture",
            model="seedance-2",
            input_payload={
                "prompt": "private prompt for video",
                "image_urls": list(REQUIRED_VIDEO_REFERENCE_REFS),
                "aspect_ratio": "9:16",
                "resolution": "480p",
                "duration": 15,
            },
            artifact_ref="artifact://authorized-live/momcozy-sterilizer-i2v-15s-seedance-2",
        ),
    }


REPO_ROOT = Path(__file__).resolve().parents[1]


def _image_spec(*, provider: str = "poyo") -> MediaJobSpec:
    return MediaJobSpec(
        job_id="momcozy_sterilizer_main_45_image_authorized_live_fixture",
        provider=provider,
        model="gpt-image-2",
        scenario="toolbox",
        step_name="momcozy_sterilizer_main_45_image",
        prompt_hash="sha256:momcozy_sterilizer_main_45_image_fixture",
        prompt_compile_id="pci_momcozy_sterilizer_main_45_image_fixture",
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=2.5,
    )


def _video_spec(*, reference_asset_ids: list[str]) -> MediaJobSpec:
    return MediaJobSpec(
        job_id="momcozy_sterilizer_i2v_15s_authorized_live_fixture",
        provider="poyo",
        model="seedance-2",
        scenario="toolbox",
        step_name="momcozy_sterilizer_asset_video",
        prompt_hash="sha256:momcozy_sterilizer_i2v_15s_fixture",
        prompt_compile_id="pci_momcozy_sterilizer_i2v_15s_fixture",
        reference_asset_ids=reference_asset_ids,
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=2.5,
    )
