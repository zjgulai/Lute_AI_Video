"""L4D-2 single Seedance video provider smoke harness."""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

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
L4D_VIDEO_INPUT_IMAGE_PATH_ENV = "AI_VIDEO_L4D_VIDEO_INPUT_IMAGE_PATH"
DEMO_API_KEY = "ai_video_demo_2026"

L4D_VIDEO_JOB_ID = "momcozy_sterilizer_i2v_l4d_video_only_fixture"
L4D_VIDEO_SAMPLE_ID = "momcozy-sterilizer-i2v-seedance-2-video-only"
L4D_VIDEO_ARTIFACT_REF = "artifact://l4d-video-only/momcozy-sterilizer-i2v-seedance-2"
L4D_INPUT_IMAGE_TENANT_REF = "tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/main_45.png"
L4D_DEFAULT_INPUT_IMAGE_PATH = (
    Path("output") / "tenants" / "default" / "pending_review" / "l4d_image_only_20260612043209" / "main_45.png"
)
L4D_EXPECTED_INPUT_IMAGE_SHA256 = "8f92d6b1c7dd13300ebf1e77290ec9ee222a10c9f0759844c63657f65af9974d"
L4D_VIDEO_MODEL = "seedance-2"
L4D_PROVIDER = "poyo"
L4D_MAX_VIDEO_JOBS = 1
L4D_VIDEO_DURATION_SECONDS = 15
L4D_VIDEO_RESOLUTION = "480p"
L4D_VIDEO_ASPECT_RATIO = "9:16"
L4D_VIDEO_PROMPT_HASH = "sha256:l4d_video_only_seedance_from_existing_pending_review_image"
L4D_VIDEO_PROMPT_COMPILE_ID = "pci_l4d_video_only_seedance_from_existing_pending_review_image"
L4D_VIDEO_PROVIDER_PROMPT = (
    "Create a quiet vertical product showcase video from the provided product image. "
    "Use a slow push-in, clean studio lighting, premium e-commerce styling, no people, "
    "no text overlays, no medical claims, and no audio."
)

HarnessMode = Literal["disabled", "dry_run", "execute"]
HarnessStatus = Literal["disabled", "dry_run_ready", "blocked", "submitted"]
ProviderSubmitter = Callable[[MediaJobSpec], Mapping[str, Any]]
ProviderSubmitterFactory = Callable[[], ProviderSubmitter | None]


class L4DVideoArtifactRef(BaseModel):
    sample_id: str
    job_id: str
    artifact_ref: str
    asset_type: Literal["video"] = "video"
    tool_id: Literal["seedance-video"] = "seedance-video"
    provider: Literal["poyo"] = "poyo"
    model: Literal["seedance-2"] = "seedance-2"
    review_status: Literal["pending_review"] = "pending_review"
    input_image_ref: str = L4D_INPUT_IMAGE_TENANT_REF
    input_image_sha256: str = L4D_EXPECTED_INPUT_IMAGE_SHA256
    media_url: str | None = None
    thumbnail_ref: str | None = None


class L4DVideoOnlyManifest(BaseModel):
    manifest_id: str = "l4d_video_only_momcozy_sterilizer_pending_review"
    brand: str = "momcozy"
    product: str = "sterilizer"
    asset_status: Literal["pending_review"] = "pending_review"
    image_generation_count: Literal[0] = 0
    image_count: Literal[0] = 0
    video_count: Literal[1] = 1
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    artifacts: list[L4DVideoArtifactRef] = Field(default_factory=list)
    forbidden_chain_steps: list[str] = Field(
        default_factory=lambda: [
            "image_generation",
            "tts",
            "assemble",
            "keyframe",
            "gate_candidate",
            "final_work",
        ]
    )


class L4DVideoOnlyReport(BaseModel):
    harness_id: str
    mode: HarnessMode
    status: HarnessStatus
    provider_call_executed: bool = False
    image_job_count: int = 0
    video_job_count: int = 0
    job_spec: MediaJobSpec | None = None
    job_records: list[MediaJobRecord] = Field(default_factory=list)
    artifact_manifest: L4DVideoOnlyManifest | None = None
    provider_response_refs: dict[str, str] = Field(default_factory=dict)
    provider_media_urls: dict[str, str] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SingleVideoJobSubmitter:
    """Fail closed if caller attempts anything beyond the authorized video job."""

    def __init__(self, submitter: ProviderSubmitter) -> None:
        self._submitter = submitter
        self.image_job_count = 0
        self.video_job_count = 0

    def __call__(self, spec: MediaJobSpec) -> Mapping[str, Any]:
        _validate_l4d_video_spec(spec)
        if self.video_job_count >= L4D_MAX_VIDEO_JOBS:
            raise ValueError("L4D-2 video job count exceeded 1")
        self.video_job_count += 1
        return self._submitter(spec)


class L4DVideoOnlyPoyoSubmitter:
    """Build one poyo Seedance request from an already-reviewed input image."""

    def __init__(self, *, transport: PoyoSubmitOnceTransport, input_image_path: Path | str) -> None:
        self._transport = transport
        self._input_image_path = Path(input_image_path)

    def __call__(self, spec: MediaJobSpec) -> dict[str, str]:
        _validate_l4d_video_spec(spec)
        payload = build_l4d_video_provider_payload(self._input_image_path)
        result = self._transport.submit_once(model=spec.model, input_payload=payload)
        media_url = _required_provider_string(result, "file_url")
        return {
            "provider_job_id": _required_provider_string(result, "provider_job_id"),
            "job_id": spec.job_id,
            "provider": spec.provider,
            "model": spec.model,
            "artifact_ref": L4D_VIDEO_ARTIFACT_REF,
            "media_url": media_url,
            "thumbnail_ref": str(result.get("thumbnail_url") or ""),
        }


def run_l4d_video_only_smoke(
    *,
    mode: HarnessMode = "disabled",
    env: Mapping[str, str] | None = None,
    submitter: ProviderSubmitter | None = None,
    submitter_factory: ProviderSubmitterFactory | None = None,
) -> L4DVideoOnlyReport:
    env = os.environ if env is None else env
    harness_id = f"l4d_video_only_smoke_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if mode == "disabled":
        return L4DVideoOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="disabled",
            blocked_reasons=["L4D video-only harness is disabled by default"],
        )

    job_spec = _build_l4d_video_job_spec()
    job_record = ProductionJobLedger().prepare(job_spec)
    artifact_manifest = _build_l4d_video_manifest(job_spec)
    blocked_reasons = _preflight_blocked_reasons(env=env, mode=mode)
    if blocked_reasons:
        return L4DVideoOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_records=[job_record],
            artifact_manifest=artifact_manifest,
            blocked_reasons=blocked_reasons,
        )

    if mode == "dry_run":
        return L4DVideoOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="dry_run_ready",
            job_spec=job_spec,
            job_records=[job_record],
            artifact_manifest=artifact_manifest,
        )

    configured_submitter = submitter
    if configured_submitter is None and submitter_factory is not None:
        configured_submitter = submitter_factory()
    if configured_submitter is None:
        return L4DVideoOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_records=[job_record],
            artifact_manifest=artifact_manifest,
            blocked_reasons=["provider submitter is not configured"],
        )

    guarded_submitter = SingleVideoJobSubmitter(configured_submitter)
    ledger = ProductionJobLedger()
    ledger.prepare(job_spec)
    try:
        response = guarded_submitter(job_spec)
        provider_job_id = _required_provider_string(response, "provider_job_id")
        media_url = _required_provider_string(response, "media_url")
    except Exception as exc:
        return L4DVideoOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            provider_call_executed=guarded_submitter.video_job_count > 0,
            image_job_count=guarded_submitter.image_job_count,
            video_job_count=guarded_submitter.video_job_count,
            job_spec=job_spec,
            job_records=[ledger.mark_failed(job_spec.job_id, str(exc))],
            artifact_manifest=artifact_manifest,
            blocked_reasons=[f"L4D-2 provider submit failed: {exc}"],
        )

    artifact_manifest.artifacts[0].media_url = media_url
    artifact_manifest.artifacts[0].thumbnail_ref = str(response.get("thumbnail_ref") or "") or None
    return L4DVideoOnlyReport(
        harness_id=harness_id,
        mode=mode,
        status="submitted",
        provider_call_executed=True,
        image_job_count=guarded_submitter.image_job_count,
        video_job_count=guarded_submitter.video_job_count,
        job_spec=job_spec,
        job_records=[ledger.mark_submitted(job_spec.job_id, provider_job_id)],
        artifact_manifest=artifact_manifest,
        provider_response_refs={job_spec.job_id: provider_job_id},
        provider_media_urls={job_spec.job_id: media_url},
    )


def build_l4d_video_provider_payload(input_image_path: Path | str) -> dict[str, Any]:
    image_path = Path(input_image_path).expanduser()
    _validate_input_image(image_path)
    return {
        "prompt": L4D_VIDEO_PROVIDER_PROMPT,
        "image_urls": [_image_data_uri(image_path)],
        "aspect_ratio": L4D_VIDEO_ASPECT_RATIO,
        "resolution": L4D_VIDEO_RESOLUTION,
        "duration": L4D_VIDEO_DURATION_SECONDS,
        "generate_audio": False,
    }


def build_l4d_video_only_poyo_submitter_from_env(
    *,
    env: Mapping[str, str],
    transport: PoyoSubmitOnceTransport | None = None,
) -> L4DVideoOnlyPoyoSubmitter | None:
    if env.get(AUTHORIZED_LIVE_POYO_TRANSPORT_ENV) != "1":
        return None
    input_image_path = _input_image_path_from_env(env)
    _validate_input_image(input_image_path)
    if transport is None:
        authorization_token = env.get(POYO_API_KEY_ENV, "")
        if not authorization_token:
            raise ValueError(f"{POYO_API_KEY_ENV} is required for L4D-2 video-only poyo submitter")
        base_url = (env.get(POYO_API_BASE_URL_ENV) or DEFAULT_POYO_API_BASE_URL).rstrip("/")
        http_client = AuthorizedLivePoyoHttpClient(base_url=base_url)
        transport = AuthorizedLivePoyoSubmitPollTransport(
            authorization_token=authorization_token,
            http_client=http_client,
        )
    return L4DVideoOnlyPoyoSubmitter(transport=transport, input_image_path=input_image_path)


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
        checks.append(_requires(env, L4D_VIDEO_ONLY_EXECUTE_ENV, "1"))
    if env.get(LEGACY_ASSET_PACK_EXECUTE_ENV) == "1":
        checks.append(f"{LEGACY_ASSET_PACK_EXECUTE_ENV}=1 must not be set for L4D-2 video-only smoke")
    if env.get(L4D_IMAGE_ONLY_EXECUTE_ENV) == "1":
        checks.append(f"{L4D_IMAGE_ONLY_EXECUTE_ENV}=1 must not be set for L4D-2 video-only smoke")
    if not env.get(PLAYWRIGHT_API_KEY_ENV) or env.get(PLAYWRIGHT_API_KEY_ENV) == DEMO_API_KEY:
        checks.append(f"{PLAYWRIGHT_API_KEY_ENV} must be a non-demo production key")
    if not env.get(POYO_API_KEY_ENV):
        checks.append(f"{POYO_API_KEY_ENV} is required for poyo video-only smoke")

    input_image_path = _input_image_path_from_env(env)
    try:
        _validate_input_image(input_image_path)
    except ValueError as exc:
        checks.append(str(exc))
    return [check for check in checks if check]


def _requires(env: Mapping[str, str], name: str, expected: str) -> str:
    if env.get(name) != expected:
        return f"{name}={expected} is required"
    return ""


def _input_image_path_from_env(env: Mapping[str, str]) -> Path:
    configured = env.get(L4D_VIDEO_INPUT_IMAGE_PATH_ENV)
    return Path(configured).expanduser() if configured else L4D_DEFAULT_INPUT_IMAGE_PATH


def _validate_input_image(path: Path) -> None:
    resolved = path.expanduser()
    if not resolved.is_file():
        raise ValueError(f"L4D-2 input image not found: {resolved}")
    if _sha256_file(resolved) != L4D_EXPECTED_INPUT_IMAGE_SHA256:
        raise ValueError("L4D-2 input image sha256 mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_data_uri(path: Path) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def _build_l4d_video_job_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id=L4D_VIDEO_JOB_ID,
        provider=L4D_PROVIDER,
        model=L4D_VIDEO_MODEL,
        scenario="toolbox",
        step_name="momcozy_sterilizer_video_only_seedance",
        prompt_hash=L4D_VIDEO_PROMPT_HASH,
        prompt_compile_id=L4D_VIDEO_PROMPT_COMPILE_ID,
        reference_asset_ids=[L4D_INPUT_IMAGE_TENANT_REF],
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=2.0,
    )


def _build_l4d_video_manifest(job_spec: MediaJobSpec) -> L4DVideoOnlyManifest:
    _validate_l4d_video_spec(job_spec)
    return L4DVideoOnlyManifest(
        artifacts=[
            L4DVideoArtifactRef(
                sample_id=L4D_VIDEO_SAMPLE_ID,
                job_id=job_spec.job_id,
                artifact_ref=L4D_VIDEO_ARTIFACT_REF,
            )
        ]
    )


def _validate_l4d_video_spec(spec: MediaJobSpec) -> None:
    if spec.job_id != L4D_VIDEO_JOB_ID:
        raise ValueError("L4D-2 only allows the Seedance video-only job")
    if spec.provider != L4D_PROVIDER:
        raise ValueError("L4D-2 provider must be poyo")
    if spec.model != L4D_VIDEO_MODEL:
        raise ValueError("L4D-2 model must be seedance-2")
    if spec.reference_asset_ids != [L4D_INPUT_IMAGE_TENANT_REF]:
        raise ValueError("L4D-2 video-only smoke must reference the authorized pending_review image")


def _required_provider_string(response: Mapping[str, Any], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider response missing {key}")
    return value
