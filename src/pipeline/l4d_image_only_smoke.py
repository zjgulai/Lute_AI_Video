"""L4D-1 single image provider smoke harness."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.commercial_contracts import MediaJobRecord, MediaJobSpec
from src.pipeline.authorized_live_poyo_submitter import AUTHORIZED_LIVE_POYO_TRANSPORT_ENV
from src.pipeline.production_job_ledger import ProductionJobLedger

RUN_TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
PLAYWRIGHT_API_KEY_ENV = "PLAYWRIGHT_API_KEY"
PLAYWRIGHT_PROD_WORKERS_ENV = "PLAYWRIGHT_PROD_WORKERS"
PLAYWRIGHT_MAX_SUBMIT_COUNT_ENV = "PLAYWRIGHT_MAX_SUBMIT_COUNT"
PLAYWRIGHT_PROVIDER_MAX_RETRIES_ENV = "PLAYWRIGHT_PROVIDER_MAX_RETRIES"
PLAYWRIGHT_ARTIFACT_DISPOSITION_ENV = "PLAYWRIGHT_ARTIFACT_DISPOSITION"
POYO_API_KEY_ENV = "POYO_API_KEY"
AUTHORIZED_LIVE_POYO_PAYLOADS_ENV = "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS"
LEGACY_ASSET_PACK_EXECUTE_ENV = "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"
L4D_IMAGE_ONLY_EXECUTE_ENV = "AI_VIDEO_L4D_IMAGE_ONLY_EXECUTE"
DEMO_API_KEY = "ai_video_demo_2026"

L4D_IMAGE_JOB_ID = "momcozy_sterilizer_main_45_image_authorized_live_fixture"
L4D_IMAGE_SAMPLE_ID = "momcozy-sterilizer-main-45-gpt-image-2"
L4D_IMAGE_ARTIFACT_REF = "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2"
L4D_IMAGE_MODEL = "gpt-image-2"
L4D_PROVIDER = "poyo"
L4D_MAX_IMAGE_JOBS = 1

HarnessMode = Literal["disabled", "dry_run", "execute"]
HarnessStatus = Literal["disabled", "dry_run_ready", "blocked", "submitted"]
ProviderSubmitter = Callable[[MediaJobSpec], Mapping[str, Any]]
ProviderSubmitterFactory = Callable[[], ProviderSubmitter | None]


class L4DImageArtifactRef(BaseModel):
    sample_id: str
    job_id: str
    artifact_ref: str
    asset_type: Literal["image"] = "image"
    tool_id: Literal["product-image"] = "product-image"
    provider: Literal["poyo"] = "poyo"
    model: Literal["gpt-image-2"] = "gpt-image-2"
    review_status: Literal["pending_review"] = "pending_review"
    media_url: str | None = None
    thumbnail_ref: str | None = None


class L4DImageOnlyManifest(BaseModel):
    manifest_id: str = "l4d_image_only_momcozy_sterilizer_pending_review"
    brand: str = "momcozy"
    product: str = "sterilizer"
    asset_status: Literal["pending_review"] = "pending_review"
    image_count: Literal[1] = 1
    video_count: Literal[0] = 0
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    artifacts: list[L4DImageArtifactRef] = Field(default_factory=list)
    forbidden_chain_steps: list[str] = Field(
        default_factory=lambda: ["seedance", "tts", "assemble", "keyframe", "gate_candidate", "final_work"]
    )


class L4DImageOnlyReport(BaseModel):
    harness_id: str
    mode: HarnessMode
    status: HarnessStatus
    provider_call_executed: bool = False
    image_job_count: int = 0
    video_job_count: int = 0
    job_spec: MediaJobSpec | None = None
    job_records: list[MediaJobRecord] = Field(default_factory=list)
    artifact_manifest: L4DImageOnlyManifest | None = None
    provider_response_refs: dict[str, str] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SingleImageJobSubmitter:
    """Fail closed if caller attempts anything beyond the authorized image job."""

    def __init__(self, submitter: ProviderSubmitter) -> None:
        self._submitter = submitter
        self.image_job_count = 0
        self.video_job_count = 0

    def __call__(self, spec: MediaJobSpec) -> Mapping[str, Any]:
        _validate_l4d_image_spec(spec)
        if self.image_job_count >= L4D_MAX_IMAGE_JOBS:
            raise ValueError("L4D-1 image job count exceeded 1")
        self.image_job_count += 1
        return self._submitter(spec)


def run_l4d_image_only_smoke(
    *,
    mode: HarnessMode = "disabled",
    env: Mapping[str, str] | None = None,
    submitter: ProviderSubmitter | None = None,
    submitter_factory: ProviderSubmitterFactory | None = None,
) -> L4DImageOnlyReport:
    env = os.environ if env is None else env
    harness_id = f"l4d_image_only_smoke_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if mode == "disabled":
        return L4DImageOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="disabled",
            blocked_reasons=["L4D image-only harness is disabled by default"],
        )

    job_spec = _build_l4d_image_job_spec()
    job_record = ProductionJobLedger().prepare(job_spec)
    artifact_manifest = _build_l4d_image_manifest(job_spec)
    blocked_reasons = _preflight_blocked_reasons(env=env, mode=mode)
    if blocked_reasons:
        return L4DImageOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_records=[job_record],
            artifact_manifest=artifact_manifest,
            blocked_reasons=blocked_reasons,
        )

    if mode == "dry_run":
        return L4DImageOnlyReport(
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
        return L4DImageOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_records=[job_record],
            artifact_manifest=artifact_manifest,
            blocked_reasons=["provider submitter is not configured"],
        )

    guarded_submitter = SingleImageJobSubmitter(configured_submitter)
    ledger = ProductionJobLedger()
    ledger.prepare(job_spec)
    try:
        response = guarded_submitter(job_spec)
        provider_job_id = _required_provider_string(response, "provider_job_id")
        media_url = _required_provider_string(response, "media_url")
    except Exception as exc:
        return L4DImageOnlyReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            provider_call_executed=guarded_submitter.image_job_count > 0,
            image_job_count=guarded_submitter.image_job_count,
            video_job_count=guarded_submitter.video_job_count,
            job_spec=job_spec,
            job_records=[ledger.mark_failed(job_spec.job_id, str(exc))],
            artifact_manifest=artifact_manifest,
            blocked_reasons=[f"L4D-1 provider submit failed: {exc}"],
        )

    artifact_manifest.artifacts[0].media_url = media_url
    artifact_manifest.artifacts[0].thumbnail_ref = str(response.get("thumbnail_ref") or "") or None
    return L4DImageOnlyReport(
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
        checks.append(_requires(env, L4D_IMAGE_ONLY_EXECUTE_ENV, "1"))
    if env.get(LEGACY_ASSET_PACK_EXECUTE_ENV) == "1":
        checks.append(f"{LEGACY_ASSET_PACK_EXECUTE_ENV}=1 must not be set for L4D-1 image-only smoke")
    if not env.get(PLAYWRIGHT_API_KEY_ENV) or env.get(PLAYWRIGHT_API_KEY_ENV) == DEMO_API_KEY:
        checks.append(f"{PLAYWRIGHT_API_KEY_ENV} must be a non-demo production key")
    if not env.get(POYO_API_KEY_ENV):
        checks.append(f"{POYO_API_KEY_ENV} is required for poyo image-only smoke")
    payloads_path = env.get(AUTHORIZED_LIVE_POYO_PAYLOADS_ENV)
    if not payloads_path:
        checks.append(f"{AUTHORIZED_LIVE_POYO_PAYLOADS_ENV} is required for poyo image-only smoke")
    else:
        try:
            _validate_payload_path(payloads_path)
        except ValueError as exc:
            checks.append(str(exc))
    return [check for check in checks if check]


def _requires(env: Mapping[str, str], name: str, expected: str) -> str:
    if env.get(name) != expected:
        return f"{name}={expected} is required"
    return ""


def _validate_payload_path(path: str) -> None:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{AUTHORIZED_LIVE_POYO_PAYLOADS_ENV} file not found")


def _build_l4d_image_job_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id=L4D_IMAGE_JOB_ID,
        provider=L4D_PROVIDER,
        model=L4D_IMAGE_MODEL,
        scenario="toolbox",
        step_name="momcozy_sterilizer_main_45_image",
        prompt_hash="sha256:momcozy_sterilizer_main_45_image_fixture",
        prompt_compile_id="pci_l4d_momcozy_sterilizer_main_45_image_fixture",
        brand_bundle_id="bundle_momcozy_candidate",
        cost_ceiling_usd=1.0,
    )


def _build_l4d_image_manifest(job_spec: MediaJobSpec) -> L4DImageOnlyManifest:
    _validate_l4d_image_spec(job_spec)
    return L4DImageOnlyManifest(
        artifacts=[
            L4DImageArtifactRef(
                sample_id=L4D_IMAGE_SAMPLE_ID,
                job_id=job_spec.job_id,
                artifact_ref=L4D_IMAGE_ARTIFACT_REF,
            )
        ]
    )


def _validate_l4d_image_spec(spec: MediaJobSpec) -> None:
    if spec.job_id != L4D_IMAGE_JOB_ID:
        raise ValueError("L4D-1 only allows the main 45-degree image job")
    if spec.provider != L4D_PROVIDER:
        raise ValueError("L4D-1 provider must be poyo")
    if spec.model != L4D_IMAGE_MODEL:
        raise ValueError("L4D-1 model must be gpt-image-2")
    if spec.reference_asset_ids:
        raise ValueError("L4D-1 image-only smoke must not reference video or image-chain assets")


def _required_provider_string(response: Mapping[str, Any], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider response missing {key}")
    return value
