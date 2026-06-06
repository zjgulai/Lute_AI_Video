"""Gated authorized-live harness entrypoint for C21 token smoke."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.commercial_contracts import MediaJobRecord, MediaJobSpec
from src.pipeline.production_job_ledger import ProductionJobLedger
from src.pipeline.token_smoke_preflight import (
    DEFAULT_AUTH_MODEL,
    DEFAULT_AUTH_PROVIDER,
    PROVIDER_REVALIDATION_REF,
    SAMPLE_PLAN_REF,
    TokenSmokePreflightReport,
    build_token_smoke_preflight_report,
)

EXECUTE_ENV = "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"

HarnessMode = Literal["disabled", "dry_run", "execute"]
HarnessStatus = Literal["disabled", "dry_run_ready", "blocked", "submitted"]
ProviderSubmitter = Callable[[MediaJobSpec], Mapping[str, Any]]


class AuthorizedLiveArtifactRef(BaseModel):
    sample_id: str
    job_id: str
    artifact_ref: str
    asset_type: Literal["image", "video"]
    tool_id: str
    provider: str
    model: str
    review_status: Literal["pending_review"] = "pending_review"
    media_url: str | None = None
    thumbnail_ref: str | None = None


class AuthorizedLiveAssetPackManifest(BaseModel):
    manifest_id: str
    brand: str = "momcozy"
    product: str = "sterilizer"
    asset_status: Literal["pending_review"] = "pending_review"
    image_count: int = 3
    video_count: int = 1
    delivery_accepted: bool = False
    publish_allowed: bool = False
    approved_brand_token_write: bool = False
    artifacts: list[AuthorizedLiveArtifactRef] = Field(default_factory=list)
    video_reference_asset_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class AuthorizedLiveHarnessReport(BaseModel):
    harness_id: str
    mode: HarnessMode
    status: HarnessStatus
    provider_call_executed: bool = False
    job_spec: MediaJobSpec | None = None
    job_specs: list[MediaJobSpec] = Field(default_factory=list)
    job_records: list[MediaJobRecord] = Field(default_factory=list)
    artifact_manifest: AuthorizedLiveAssetPackManifest | None = None
    provider_response_refs: dict[str, str] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    preflight: TokenSmokePreflightReport | None = None
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def run_authorized_live_harness(
    *,
    mode: HarnessMode = "disabled",
    env: Mapping[str, str] | None = None,
    approval_record_path: str | Path | None = None,
    submitter: ProviderSubmitter | None = None,
) -> AuthorizedLiveHarnessReport:
    """Run the C9 harness gate without implicit provider calls."""
    env = os.environ if env is None else env
    harness_id = f"authorized_live_harness_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if mode == "disabled":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="disabled",
            blocked_reasons=["authorized-live harness is disabled by default"],
        )

    preflight = build_token_smoke_preflight_report(env=env, approval_record_path=approval_record_path)
    job_specs = _build_asset_pack_job_specs(preflight)
    job_spec = _primary_video_job(job_specs)
    job_records = _prepare_job_records(job_specs)
    artifact_manifest = _build_asset_pack_manifest(job_specs)
    if preflight.blocked:
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_specs=job_specs,
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=[check.detail for check in preflight.checks if check.status == "block"],
            preflight=preflight,
        )

    if mode == "dry_run":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="dry_run_ready",
            job_spec=job_spec,
            job_specs=job_specs,
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            preflight=preflight,
        )

    if env.get(EXECUTE_ENV) != "1":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_specs=job_specs,
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=[f"{EXECUTE_ENV}=1 is required for execute mode"],
            preflight=preflight,
        )

    if submitter is None:
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            job_specs=job_specs,
            job_records=job_records,
            artifact_manifest=artifact_manifest,
            blocked_reasons=["provider submitter is not configured"],
            preflight=preflight,
        )

    submitted_records, response_refs = _submit_job_specs(job_specs, submitter)
    return AuthorizedLiveHarnessReport(
        harness_id=harness_id,
        mode=mode,
        status="submitted",
        provider_call_executed=True,
        job_spec=job_spec,
        job_specs=job_specs,
        job_records=submitted_records,
        artifact_manifest=artifact_manifest,
        provider_response_refs=response_refs,
        preflight=preflight,
    )


def _build_sample_job_spec(preflight: TokenSmokePreflightReport | None = None) -> MediaJobSpec:
    return _primary_video_job(_build_asset_pack_job_specs(preflight))


def _build_asset_pack_job_specs(preflight: TokenSmokePreflightReport | None = None) -> list[MediaJobSpec]:
    provider = preflight.approved_provider if preflight and preflight.approved_provider else DEFAULT_AUTH_PROVIDER
    video_model = preflight.approved_model if preflight and preflight.approved_model else DEFAULT_AUTH_MODEL
    cost_ceiling_usd = _approved_job_cost_ceiling(preflight)
    image_model = "gpt-image-2"
    image_specs = [
        MediaJobSpec(
            job_id="momcozy_sterilizer_main_45_image_authorized_live_fixture",
            provider=provider,
            model=image_model,
            scenario="toolbox",
            step_name="momcozy_sterilizer_main_45_image",
            prompt_hash="sha256:momcozy_sterilizer_main_45_image_fixture",
            prompt_compile_id="pci_momcozy_sterilizer_main_45_image_fixture",
            brand_bundle_id="bundle_momcozy_candidate",
            cost_ceiling_usd=cost_ceiling_usd,
        ),
        MediaJobSpec(
            job_id="momcozy_sterilizer_uv_benefit_image_authorized_live_fixture",
            provider=provider,
            model=image_model,
            scenario="toolbox",
            step_name="momcozy_sterilizer_uv_benefit_image",
            prompt_hash="sha256:momcozy_sterilizer_uv_benefit_image_fixture",
            prompt_compile_id="pci_momcozy_sterilizer_uv_benefit_image_fixture",
            brand_bundle_id="bundle_momcozy_candidate",
            cost_ceiling_usd=cost_ceiling_usd,
        ),
        MediaJobSpec(
            job_id="momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture",
            provider=provider,
            model=image_model,
            scenario="toolbox",
            step_name="momcozy_sterilizer_kitchen_scene_image",
            prompt_hash="sha256:momcozy_sterilizer_kitchen_scene_image_fixture",
            prompt_compile_id="pci_momcozy_sterilizer_kitchen_scene_image_fixture",
            brand_bundle_id="bundle_momcozy_candidate",
            cost_ceiling_usd=cost_ceiling_usd,
        ),
    ]
    return [
        *image_specs,
        MediaJobSpec(
            job_id="momcozy_sterilizer_i2v_15s_authorized_live_fixture",
            provider=provider,
            model=video_model,
            scenario="toolbox",
            step_name="momcozy_sterilizer_asset_video",
            prompt_hash="sha256:momcozy_sterilizer_i2v_15s_fixture",
            prompt_compile_id="pci_momcozy_sterilizer_i2v_15s_fixture",
            reference_asset_ids=_image_artifact_refs(),
            brand_bundle_id="bundle_momcozy_candidate",
            cost_ceiling_usd=cost_ceiling_usd,
        ),
    ]


def _approved_job_cost_ceiling(preflight: TokenSmokePreflightReport | None = None) -> float:
    return (
        preflight.approved_per_job_cost_ceiling_usd
        if preflight and preflight.approved_per_job_cost_ceiling_usd is not None
        else preflight.approved_budget_limit_usd
        if preflight and preflight.approved_budget_limit_usd is not None
        else 3.0
    )


def _primary_video_job(job_specs: list[MediaJobSpec]) -> MediaJobSpec:
    for spec in job_specs:
        if spec.step_name == "momcozy_sterilizer_asset_video":
            return spec
    raise ValueError("authorized-live asset pack requires a video job")


def _prepare_job_records(job_specs: list[MediaJobSpec]) -> list[MediaJobRecord]:
    ledger = ProductionJobLedger()
    return [ledger.prepare(spec) for spec in job_specs]


def _submit_job_specs(
    job_specs: list[MediaJobSpec],
    submitter: ProviderSubmitter,
) -> tuple[list[MediaJobRecord], dict[str, str]]:
    ledger = ProductionJobLedger()
    submitted_records: list[MediaJobRecord] = []
    response_refs: dict[str, str] = {}
    for spec in job_specs:
        ledger.prepare(spec)
        response = submitter(spec)
        provider_job_id = str(response.get("provider_job_id") or response.get("job_id") or spec.job_id)
        response_refs[spec.job_id] = provider_job_id
        submitted_records.append(ledger.mark_submitted(spec.job_id, provider_job_id))
    return submitted_records, response_refs


def _build_asset_pack_manifest(job_specs: list[MediaJobSpec]) -> AuthorizedLiveAssetPackManifest:
    artifact_refs_by_job_id = _artifact_refs_by_job_id()
    return AuthorizedLiveAssetPackManifest(
        manifest_id="momcozy_sterilizer_asset_pack_pending_review",
        artifacts=[
            AuthorizedLiveArtifactRef(
                sample_id=_sample_id_for_job(spec),
                job_id=spec.job_id,
                artifact_ref=artifact_refs_by_job_id[spec.job_id],
                asset_type="video" if spec.step_name == "momcozy_sterilizer_asset_video" else "image",
                tool_id="storyboard" if spec.step_name == "momcozy_sterilizer_asset_video" else _image_tool_id(spec),
                provider=spec.provider,
                model=spec.model,
            )
            for spec in job_specs
        ],
        video_reference_asset_refs=_image_artifact_refs(),
        evidence_refs=[SAMPLE_PLAN_REF, PROVIDER_REVALIDATION_REF],
    )


def _image_tool_id(spec: MediaJobSpec) -> Literal["product-image", "ecommerce-visual"]:
    if spec.step_name == "momcozy_sterilizer_main_45_image":
        return "product-image"
    return "ecommerce-visual"


def _sample_id_for_job(spec: MediaJobSpec) -> str:
    return {
        "momcozy_sterilizer_main_45_image_authorized_live_fixture": "momcozy-sterilizer-main-45-gpt-image-2",
        "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture": "momcozy-sterilizer-uv-benefit-gpt-image-2",
        "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture": (
            "momcozy-sterilizer-kitchen-scene-gpt-image-2"
        ),
        "momcozy_sterilizer_i2v_15s_authorized_live_fixture": "momcozy-sterilizer-i2v-15s-seedance-2",
    }[spec.job_id]


def _image_artifact_refs() -> list[str]:
    artifact_refs = _artifact_refs_by_job_id()
    return [
        artifact_refs["momcozy_sterilizer_main_45_image_authorized_live_fixture"],
        artifact_refs["momcozy_sterilizer_uv_benefit_image_authorized_live_fixture"],
        artifact_refs["momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture"],
    ]


def _artifact_refs_by_job_id() -> dict[str, str]:
    return {
        "momcozy_sterilizer_main_45_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-main-45-gpt-image-2"
        ),
        "momcozy_sterilizer_uv_benefit_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-uv-benefit-gpt-image-2"
        ),
        "momcozy_sterilizer_kitchen_scene_image_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-kitchen-scene-gpt-image-2"
        ),
        "momcozy_sterilizer_i2v_15s_authorized_live_fixture": (
            "artifact://authorized-live/momcozy-sterilizer-i2v-15s-seedance-2"
        ),
    }
