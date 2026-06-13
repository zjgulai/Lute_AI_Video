"""L4D-3 paired image plus Seedance provider smoke harness."""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, Protocol
from urllib import request

from pydantic import BaseModel, Field

from src.models.commercial_contracts import MediaJobRecord, MediaJobSpec
from src.pipeline.authorized_live_poyo_runtime import (
    DEFAULT_POYO_API_BASE_URL,
    POYO_API_BASE_URL_ENV,
    AuthorizedLivePoyoHttpClient,
)
from src.pipeline.authorized_live_poyo_submitter import (
    AUTHORIZED_LIVE_POYO_TRANSPORT_ENV,
    AuthorizedLivePoyoSubmitPollTransport,
    PoyoSubmitOnceTransport,
)
from src.pipeline.production_job_ledger import ProductionJobLedger

RUN_TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
PLAYWRIGHT_API_KEY_ENV = "PLAYWRIGHT_API_KEY"
PLAYWRIGHT_PROD_WORKERS_ENV = "PLAYWRIGHT_PROD_WORKERS"
PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV = "PLAYWRIGHT_MAX_SUBMIT_COUNT"
PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV = "PLAYWRIGHT_PROVIDER_MAX_RETRIES"
PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV = "PLAYWRIGHT_ARTIFACT_DISPOSITION"
POYO_API_KEY_ENV = "POYO_API_KEY"
LEGACY_ASSET_PACK_EXECUTE_ENV = "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"
L4D_IMAGE_ONLY_EXECUTE_ENV = "AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE"
L4D_VIDEO_ONLY_EXECUTE_ENV = "AI_VIDEO_L4D_VIDEO_ONLY_EXECUTE"
L4D_PAIRED_EXECUTE_ENV = "AI_VIDEO_L4D_PAIRED_EXECUTE"
DEMO_API_KEY = "ai_video_demo_2026"

L4D_PAIRED_IMAGE_JOB_ID = "momcozy_sterilizer_l4d_paired_image_fixture"
L4D_PAIRED_VIDEO_JOB_ID = "momcozy_sterilizer_l4d_paired_i2v_fixture"
L4D_PAIRED_IMAGE_ARTIFACT_REF = "artifact://l4d-paired/momcozy-sterilizer-image-gpt-image-2"
L4D_PAIRED_VIDEO_ARTIFACT_REF = "artifact://l4d-paired/momcozy-sterilizer-i2v-seedance-2"
L4D_PROVIDER = "poyo"
L4D_IMAGE_MODEL = "gpt-image-2"
L4D_VIDEO_MODEL = "seedance-2"
L4D_MAX_IMAGE_JOBS = 1
L4D_MAX_VIDEO_JOBS = 1
L4D_VIDEO_DURATION_SECONDS = 15
L4D_VIDEO_RESOLUTION = "480p"
L4D_VIDEO_ASPECT_RATIO = "9:16"
L4D_IMAGE_PROMPT_HASH = "sha256:l4d_paired_momcozy_sterilizer_image_fixture"
L4D_IMAGE_PROMPT_COMPILE_ID = "pci_l4d_paired_momcozy_sterilizer_image_fixture"
L4D_VIDEO_PROMPT_HASH = "sha256:l4d_paired_seedance_from_generated_image"
L4D_VIDEO_PROMPT_COMPILE_ID = "pci_l4d_paired_seedance_from_generated_image"
L4D_IMAGE_PROVIDER_PROMPT = (
    "Generate a clean square e-commerce product image of a compact white countertop sterilizer appliance. "
    "Use bright studio lighting, a plain light background, premium product photography, no people, "
    "no text overlays, no logos, and no medical claims."
)
L4D_VIDEO_PROVIDER_PROMPT = (
    "Create a quiet vertical product showcase video from the provided product image. Use a slow push-in, "
    "subtle turntable-style motion, clean studio lighting, no people, no text overlays, no medical claims, "
    "and no audio."
)

HarnessMode = Literal["disabled", "dry_run", "execute"]
HarnessStatus = Literal["disabled", "dry_run_ready", "blocked", "submitted"]


class PairedProviderSubmitter(Protocol):
    image_job_count: int
    video_job_count: int

    def __call__(self, image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> Mapping[str, Any]: ...


ProviderSubmitterFactory = Callable[[], PairedProviderSubmitter | None]
GeneratedImageDownloader = Callable[[str], bytes]


class L4DPairedArtifactRef(BaseModel):
    sample_id: str
    job_id: str
    artifact_ref: str
    asset_type: Literal["image", "video"]
    tool_id: Literal["product-image", "seedance-video"]
    provider: Literal["poyo"] = "poyo"
    model: Literal["gpt-image-2", "seedance-2"]
    review_status: Literal["pending_review"] = "pending_review"
    media_url: str | None = None
    thumbnail_ref: str | None = None
    input_image_artifact_ref: str | None = None
    input_image_sha256: str | None = None


class L4DPairedManifest(BaseModel):
    manifest_id: str = "l4d_paired_momcozy_sterilizer_pending_review"
    brand: str = "momcozy"
    product: str = "sterilizer"
    asset_status: Literal["pending_review"] = "pending_review"
    image_count: Literal[1] = 1
    video_count: Literal[1] = 1
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    artifacts: list[L4DPairedArtifactRef] = Field(default_factory=list)
    forbidden_chain_steps: list[str] = Field(
        default_factory=lambda: [
            "tts",
            "assemble",
            "keyframe",
            "gate_candidate",
            "scenario_full_media",
            "final_work",
        ]
    )


class L4DPairedReport(BaseModel):
    harness_id: str
    mode: HarnessMode
    status: HarnessStatus
    provider_call_executed: bool = False
    image_job_count: int = 0
    video_job_count: int = 0
    job_specs: list[MediaJobSpec] = Field(default_factory=list)
    job_records: list[MediaJobRecord] = Field(default_factory=list)
    artifact_manifest: L4DPairedManifest | None = None
    provider_response_refs: dict[str, str] = Field(default_factory=dict)
    provider_media_urls: dict[str, str] = Field(default_factory=dict)
    generated_image_sha256: str | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SinglePairedChainSubmitter:
    """Fail closed if a paired runner exceeds the authorized 1+1 chain."""

    def __init__(self, submitter: PairedProviderSubmitter) -> None:
        self._submitter = submitter

    @property
    def image_job_count(self) -> int:
        return self._submitter.image_job_count

    @property
    def video_job_count(self) -> int:
        return self._submitter.video_job_count

    def __call__(self, image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> Mapping[str, Any]:
        _validate_l4d_paired_specs(image_spec, video_spec)
        if self.image_job_count >= L4D_MAX_IMAGE_JOBS:
            raise ValueError("L4D-3 image job count exceeded 1")
        if self.video_job_count >= L4D_MAX_VIDEO_JOBS:
            raise ValueError("L4D-3 video job count exceeded 1")
        response = self._submitter(image_spec, video_spec)
        if self.image_job_count != 1:
            raise ValueError("L4D-3 must execute exactly one image job")
        if self.video_job_count != 1:
            raise ValueError("L4D-3 must execute exactly one video job")
        return response


class BrowserUaImageDownloader:
    """Download the generated image for the chained video input without provider retry."""

    def __init__(self, *, timeout_seconds: float = 180.0) -> None:
        self._timeout_seconds = timeout_seconds

    def __call__(self, media_url: str) -> bytes:
        http_request = request.Request(
            media_url,
            headers={"User-Agent": "Mozilla/5.0 L4D-3 paired pending-review materializer"},
        )
        with request.urlopen(http_request, timeout=self._timeout_seconds) as response:
            payload = response.read()
        if not payload:
            raise ValueError("generated image download returned empty payload")
        return payload


class L4DPairedPoyoSubmitter:
    """Submit one image job, then use only that generated image for one video job."""

    def __init__(
        self,
        *,
        transport: PoyoSubmitOnceTransport,
        generated_image_downloader: GeneratedImageDownloader | None = None,
    ) -> None:
        self._transport = transport
        self._generated_image_downloader = generated_image_downloader or BrowserUaImageDownloader()
        self.image_job_count = 0
        self.video_job_count = 0

    def __call__(self, image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> dict[str, str]:
        _validate_l4d_paired_specs(image_spec, video_spec)
        if self.image_job_count >= L4D_MAX_IMAGE_JOBS:
            raise ValueError("L4D-3 image job count exceeded 1")
        self.image_job_count += 1
        image_result = self._transport.submit_once(
            model=image_spec.model,
            input_payload=build_l4d_paired_image_provider_payload(),
        )
        image_media_url = _required_provider_string(image_result, "file_url")
        generated_image_bytes = self._generated_image_downloader(image_media_url)
        generated_image_sha256 = hashlib.sha256(generated_image_bytes).hexdigest()

        if self.video_job_count >= L4D_MAX_VIDEO_JOBS:
            raise ValueError("L4D-3 video job count exceeded 1")
        self.video_job_count += 1
        video_result = self._transport.submit_once(
            model=video_spec.model,
            input_payload=build_l4d_paired_video_provider_payload(generated_image_bytes),
        )
        video_media_url = _required_provider_string(video_result, "file_url")
        return {
            "image_provider_job_id": _required_provider_string(image_result, "provider_job_id"),
            "video_provider_job_id": _required_provider_string(video_result, "provider_job_id"),
            "image_media_url": image_media_url,
            "video_media_url": video_media_url,
            "image_thumbnail_ref": str(image_result.get("thumbnail_url") or ""),
            "video_thumbnail_ref": str(video_result.get("thumbnail_url") or ""),
            "generated_image_sha256": generated_image_sha256,
        }


def run_l4d_paired_smoke(
    *,
    mode: HarnessMode = "disabled",
    env: Mapping[str, str] | None = None,
    submitter: PairedProviderSubmitter | None = None,
    submitter_factory: ProviderSubmitterFactory | None = None,
) -> L4DPairedReport:
    env = os.environ if env is None else env
    harness_id = f"l4d_paired_smoke_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if mode == "disabled":
        return L4DPairedReport(
            harness_id=harness_id,
            mode=mode,
            status="disabled",
            blocked_reasons=["L4D paired harness is disabled by default"],
        )

    image_spec = _build_l4d_paired_image_job_spec()
    video_spec = _build_l4d_paired_video_job_spec()
    ledger = ProductionJobLedger()
    job_records = [ledger.prepare(image_spec), ledger.prepare(video_spec)]
    artifact_manifest = _build_l4d_paired_manifest(image_spec, video_spec)
    blocked_reasons = _preflight_blocked_reasons(env=env, mode=mode)
    if blocked_reasons:
        return L4DPairedReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_specs=[image_spec, video_spec],
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=blocked_reasons,
        )

    if mode == "dry_run":
        return L4DPairedReport(
            harness_id=harness_id,
            mode=mode,
            status="dry_run_ready",
            job_specs=[image_spec, video_spec],
            job_records=job_records,
            artifact_manifest=artifact_manifest,
        )

    configured_submitter = submitter
    if configured_submitter is None and submitter_factory is not None:
        configured_submitter = submitter_factory()
    if configured_submitter is None:
        return L4DPairedReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_specs=[image_spec, video_spec],
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=["provider submitter is not configured"],
        )

    guarded_submitter = SinglePairedChainSubmitter(configured_submitter)
    try:
        response = guarded_submitter(image_spec, video_spec)
        image_provider_job_id = _required_provider_string(response, "image_provider_job_id")
        video_provider_job_id = _required_provider_string(response, "video_provider_job_id")
        image_media_url = _required_provider_string(response, "image_media_url")
        video_media_url = _required_provider_string(response, "video_media_url")
    except Exception as exc:
        failed_records = [
            ledger.mark_failed(image_spec.job_id, str(exc)),
            ledger.mark_failed(video_spec.job_id, str(exc)),
        ]
        return L4DPairedReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            provider_call_executed=guarded_submitter.image_job_count > 0 or guarded_submitter.video_job_count > 0,
            image_job_count=guarded_submitter.image_job_count,
            video_job_count=guarded_submitter.video_job_count,
            job_specs=[image_spec, video_spec],
            job_records=failed_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=[f"L4D-3 provider submit failed: {exc}"],
        )

    artifact_manifest.artifacts[0].media_url = image_media_url
    artifact_manifest.artifacts[0].thumbnail_ref = str(response.get("image_thumbnail_ref") or "") or None
    artifact_manifest.artifacts[1].media_url = video_media_url
    artifact_manifest.artifacts[1].thumbnail_ref = str(response.get("video_thumbnail_ref") or "") or None
    generated_image_sha256 = str(response.get("generated_image_sha256") or "") or None
    artifact_manifest.artifacts[1].input_image_sha256 = generated_image_sha256
    return L4DPairedReport(
        harness_id=harness_id,
        mode=mode,
        status="submitted",
        provider_call_executed=True,
        image_job_count=guarded_submitter.image_job_count,
        video_job_count=guarded_submitter.video_job_count,
        job_specs=[image_spec, video_spec],
        job_records=[
            ledger.mark_submitted(image_spec.job_id, image_provider_job_id),
            ledger.mark_submitted(video_spec.job_id, video_provider_job_id),
        ],
        artifact_manifest=artifact_manifest,
        provider_response_refs={
            image_spec.job_id: image_provider_job_id,
            video_spec.job_id: video_provider_job_id,
        },
        provider_media_urls={
            image_spec.job_id: image_media_url,
            video_spec.job_id: video_media_url,
        },
        generated_image_sha256=generated_image_sha256,
    )


def build_l4d_paired_image_provider_payload() -> dict[str, Any]:
    return {
        "prompt": L4D_IMAGE_PROVIDER_PROMPT,
        "aspect_ratio": "1:1",
        "size": "1024x1024",
        "quality": "low",
    }


def build_l4d_paired_video_provider_payload(generated_image_bytes: bytes) -> dict[str, Any]:
    if not generated_image_bytes:
        raise ValueError("generated image bytes are required for L4D-3 video input")
    return {
        "prompt": L4D_VIDEO_PROVIDER_PROMPT,
        "image_urls": [_image_data_uri(generated_image_bytes)],
        "aspect_ratio": L4D_VIDEO_ASPECT_RATIO,
        "resolution": L4D_VIDEO_RESOLUTION,
        "duration": L4D_VIDEO_DURATION_SECONDS,
        "generate_audio": False,
    }


def build_l4d_paired_poyo_submitter_from_env(
    *,
    env: Mapping[str, str],
    transport: PoyoSubmitOnceTransport | None = None,
    generated_image_downloader: GeneratedImageDownloader | None = None,
) -> L4DPairedPoyoSubmitter | None:
    if env.get(AUTHORIZED_LIVE_POYO_TRANSPORT_ENV) != "1":
        return None
    if transport is None:
        authorization_token = env.get(POYO_API_KEY_ENV, "")
        if not authorization_token:
            raise ValueError(f"{POYO_API_KEY_ENV} is required for L4D-3 paired poyo submitter")
        base_url = (env.get(POYO_API_BASE_URL_ENV) or DEFAULT_POYO_API_BASE_URL).rstrip("/")
        http_client = AuthorizedLivePoyoHttpClient(base_url=base_url)
        transport = AuthorizedLivePoyoSubmitPollTransport(
            authorization_token=authorization_token,
            http_client=http_client,
        )
    return L4DPairedPoyoSubmitter(
        transport=transport,
        generated_image_downloader=generated_image_downloader,
    )


def _preflight_blocked_reasons(*, env: Mapping[str, str], mode: HarnessMode) -> list[str]:
    checks = [
        _requires(env, RUN_TOKEN_SMOKE_ENV, "1"),
        _requires(env, PLAYWRIGHT_PROD_WORKERS_ENV, "1"),
        _requires(env, PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV, "1"),
        _requires(env, PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV, "0"),
        _requires(env, PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV, "pending_review"),
        _requires(env, AUTHORIZED_LIVE_POYO_TRANSPORT_ENV, "1"),
    ]
    if mode == "execute":
        checks.append(_requires(env, L4D_PAIRED_EXECUTE_ENV, "1"))
    if env.get(LEGACY_ASSET_PACK_EXECUTE_ENV) == "1":
        checks.append(f"{LEGACY_ASSET_PACK_EXECUTE_ENV}=1 must not be set for L4D-3 paired smoke")
    if env.get(L4D_IMAGE_ONLY_EXECUTE_ENV) == "1":
        checks.append(f"{L4D_IMAGE_ONLY_EXECUTE_ENV}=1 must not be set for L4D-3 paired smoke")
    if env.get(L4D_VIDEO_ONLY_EXECUTE_ENV) == "1":
        checks.append(f"{L4D_VIDEO_ONLY_EXECUTE_ENV}=1 must not be set for L4D-3 paired smoke")
    if not env.get(PLAYWRIGHT_API_KEY_ENV) or env.get(PLAYWRIGHT_API_KEY_ENV) == DEMO_API_KEY:
        checks.append(f"{PLAYWRIGHT_API_KEY_ENV} must be a non-demo production key")
    if not env.get(POYO_API_KEY_ENV):
        checks.append(f"{POYO_API_KEY_ENV} is required for poyo paired smoke")
    return [check for check in checks if check]


def _requires(env: Mapping[str, str], name: str, expected: str) -> str:
    if env.get(name) != expected:
        return f"{name}={expected} is required"
    return ""


def _build_l4d_paired_image_job_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id=L4D_PAIRED_IMAGE_JOB_ID,
        provider=L4D_PROVIDER,
        model=L4D_IMAGE_MODEL,
        scenario="toolbox",
        step_name="momcozy_sterilizer_l4d_paired_image",
        prompt_hash=L4D_IMAGE_PROMPT_HASH,
        prompt_compile_id=L4D_IMAGE_PROMPT_COMPILE_ID,
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=1.0,
    )


def _build_l4d_paired_video_job_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id=L4D_PAIRED_VIDEO_JOB_ID,
        provider=L4D_PROVIDER,
        model=L4D_VIDEO_MODEL,
        scenario="toolbox",
        step_name="momcozy_sterilizer_l4d_paired_i2v",
        prompt_hash=L4D_VIDEO_PROMPT_HASH,
        prompt_compile_id=L4D_VIDEO_PROMPT_COMPILE_ID,
        reference_asset_ids=[L4D_PAIRED_IMAGE_ARTIFACT_REF],
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=2.0,
    )


def _build_l4d_paired_manifest(image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> L4DPairedManifest:
    _validate_l4d_paired_specs(image_spec, video_spec)
    return L4DPairedManifest(
        artifacts=[
            L4DPairedArtifactRef(
                sample_id="momcozy-sterilizer-l4d-paired-image",
                job_id=image_spec.job_id,
                artifact_ref=L4D_PAIRED_IMAGE_ARTIFACT_REF,
                asset_type="image",
                tool_id="product-image",
                model="gpt-image-2",
            ),
            L4DPairedArtifactRef(
                sample_id="momcozy-sterilizer-l4d-paired-i2v",
                job_id=video_spec.job_id,
                artifact_ref=L4D_PAIRED_VIDEO_ARTIFACT_REF,
                asset_type="video",
                tool_id="seedance-video",
                model="seedance-2",
                input_image_artifact_ref=L4D_PAIRED_IMAGE_ARTIFACT_REF,
            ),
        ]
    )


def _validate_l4d_paired_specs(image_spec: MediaJobSpec, video_spec: MediaJobSpec) -> None:
    if image_spec.job_id != L4D_PAIRED_IMAGE_JOB_ID:
        raise ValueError("L4D-3 only allows the paired image job")
    if image_spec.provider != L4D_PROVIDER:
        raise ValueError("L4D-3 image provider must be poyo")
    if image_spec.model != L4D_IMAGE_MODEL:
        raise ValueError("L4D-3 image model must be gpt-image-2")
    if image_spec.reference_asset_ids:
        raise ValueError("L4D-3 image job must not use pre-existing image references")
    if video_spec.job_id != L4D_PAIRED_VIDEO_JOB_ID:
        raise ValueError("L4D-3 only allows the paired video job")
    if video_spec.provider != L4D_PROVIDER:
        raise ValueError("L4D-3 video provider must be poyo")
    if video_spec.model != L4D_VIDEO_MODEL:
        raise ValueError("L4D-3 video model must be seedance-2")
    if video_spec.reference_asset_ids != [L4D_PAIRED_IMAGE_ARTIFACT_REF]:
        raise ValueError("L4D-3 video job must reference only this run's generated image artifact")


def _image_data_uri(payload: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(payload).decode('ascii')}"


def _required_provider_string(response: Mapping[str, Any], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider response missing {key}")
    return value
