"""No-token contract facade for the authorized-live poyo smoke submitter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.models.commercial_contracts import MediaJobSpec

REQUIRED_VIDEO_REFERENCE_REFS: tuple[str, str, str] = (
    "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2",
    "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2",
    "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2",
)
AUTHORIZED_LIVE_POYO_TRANSPORT_ENV = "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT"
POYO_SUBMIT_ENDPOINT = "/api/generate/submit"
POYO_STATUS_ENDPOINT_PREFIX = "/api/generate/status"

_ALLOWED_JOB_MODELS = {
    "momcozy_sterilizer_main_45_image_authorized_live_fixture": "gpt-image-2",
    "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture": "gpt-image-2",
    "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture": "gpt-image-2",
    "momcozy_sterilizer_i2v_15s_authorized_live_fixture": "seedance-2",
}
_VIDEO_JOB_ID = "momcozy_sterilizer_i2v_15s_authorized_live_fixture"


class AuthorizedLivePoyoPayload(BaseModel):
    job_id: str
    model: str
    input_payload: dict[str, Any] = Field(default_factory=dict, repr=False)
    artifact_ref: str


class PoyoSubmitOnceTransport(Protocol):
    def submit_once(self, *, model: str, input_payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class PoyoSubmitPollHttpClient(Protocol):
    def post_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def get_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
    ) -> Mapping[str, Any]: ...


class AuthorizedLivePoyoSubmitPollTransport:
    """Submit one poyo task through an injected HTTP client and read one finished status."""

    def __init__(self, *, authorization_token: str, http_client: PoyoSubmitPollHttpClient) -> None:
        if not authorization_token:
            raise ValueError("authorization token is required")
        self._authorization_token = authorization_token
        self._http_client = http_client

    def submit_once(self, *, model: str, input_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        headers = self._headers()
        submit_response = self._http_client.post_json(
            path=POYO_SUBMIT_ENDPOINT,
            headers=headers,
            body={"model": model, "input": dict(input_payload)},
        )
        task_id = _required_string(_success_data(submit_response, "submit"), "task_id")

        status_response = self._http_client.get_json(
            path=f"{POYO_STATUS_ENDPOINT_PREFIX}/{task_id}",
            headers=headers,
        )
        task = _success_data(status_response, "status")
        if task.get("status") != "finished":
            raise ValueError("poyo task must be finished before artifact mapping")

        file_url, thumbnail_url = _first_file_refs(task)
        return {
            "provider_job_id": task_id,
            "file_url": file_url,
            "thumbnail_url": thumbnail_url,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._authorization_token}",
            "Content-Type": "application/json",
        }


class AuthorizedLivePoyoSubmitter:
    """Validate the asset-pack job contract before a single poyo submit.

    The facade deliberately takes an injected transport. The default code path
    has no provider client, so tests can prove the contract without network or
    token spending.
    """

    def __init__(
        self,
        *,
        transport: PoyoSubmitOnceTransport,
        payloads: Mapping[str, AuthorizedLivePoyoPayload],
    ) -> None:
        self._transport = transport
        self._payloads = dict(payloads)

    def __call__(self, spec: MediaJobSpec) -> dict[str, str]:
        payload = self._payload_for(spec)
        result = self._transport.submit_once(model=spec.model, input_payload=dict(payload.input_payload))
        return {
            "provider_job_id": _required_string(result, "provider_job_id"),
            "job_id": spec.job_id,
            "provider": spec.provider,
            "model": spec.model,
            "artifact_ref": payload.artifact_ref,
            "media_url": _required_string(result, "file_url"),
            "thumbnail_ref": str(result.get("thumbnail_url") or ""),
        }

    def _payload_for(self, spec: MediaJobSpec) -> AuthorizedLivePoyoPayload:
        _validate_spec(spec)
        payload = self._payloads.get(spec.job_id)
        if payload is None:
            raise ValueError(f"missing private poyo payload for job: {spec.job_id}")
        if payload.job_id != spec.job_id:
            raise ValueError("payload job_id must match media job spec")
        if payload.model != spec.model:
            raise ValueError("payload model must match media job spec")
        if spec.job_id == _VIDEO_JOB_ID:
            payload_refs = payload.input_payload.get("image_urls")
            if payload_refs != list(REQUIRED_VIDEO_REFERENCE_REFS):
                raise ValueError("video payload must carry the three authorized image artifacts")
        return payload


def build_authorized_live_poyo_submitter(
    *,
    env: Mapping[str, str],
    transport: PoyoSubmitOnceTransport | None = None,
    payloads: Mapping[str, AuthorizedLivePoyoPayload] | None = None,
) -> AuthorizedLivePoyoSubmitter | None:
    """Build an injected submitter only after an explicit no-token wiring gate."""
    if env.get(AUTHORIZED_LIVE_POYO_TRANSPORT_ENV) != "1":
        return None
    if transport is None:
        raise ValueError("injected poyo transport is required")
    if payloads is None:
        raise ValueError("private poyo payloads are required")
    return AuthorizedLivePoyoSubmitter(transport=transport, payloads=payloads)


def _validate_spec(spec: MediaJobSpec) -> None:
    if spec.provider != "poyo":
        raise ValueError("provider must be poyo")
    if spec.scenario != "toolbox":
        raise ValueError("scenario must be toolbox")

    expected_model = _ALLOWED_JOB_MODELS.get(spec.job_id)
    if expected_model is None:
        raise ValueError(f"job is outside the authorized-live sample plan: {spec.job_id}")
    if spec.model != expected_model:
        raise ValueError(f"job model must be {expected_model}")
    if spec.job_id == _VIDEO_JOB_ID and spec.reference_asset_ids != list(REQUIRED_VIDEO_REFERENCE_REFS):
        raise ValueError("video job must reference the three authorized image artifacts")


def _required_string(result: Mapping[str, Any], key: str) -> str:
    value = result.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"poyo transport response missing {key}")
    return value


def _success_data(response: Mapping[str, Any], stage: str) -> Mapping[str, Any]:
    if response.get("code") != 200:
        raise ValueError(f"poyo {stage} response must have code=200")
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise ValueError(f"poyo {stage} response missing data")
    return data


def _first_file_refs(task: Mapping[str, Any]) -> tuple[str, str]:
    files = task.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("poyo finished task missing file_url")
    first_file = files[0]
    if not isinstance(first_file, Mapping):
        raise ValueError("poyo finished task missing file_url")
    file_url = first_file.get("file_url") or first_file.get("audio_url")
    if not isinstance(file_url, str) or not file_url:
        raise ValueError("poyo finished task missing file_url")
    thumbnail_url = first_file.get("thumbnail_url") or first_file.get("cover_url") or first_file.get("poster_url") or ""
    return file_url, str(thumbnail_url)
