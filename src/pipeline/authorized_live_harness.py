"""Gated authorized-live harness entrypoint for C21 token smoke."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.commercial_contracts import MediaJobSpec
from src.pipeline.token_smoke_preflight import (
    TokenSmokePreflightReport,
    build_token_smoke_preflight_report,
)

EXECUTE_ENV = "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE"

HarnessMode = Literal["disabled", "dry_run", "execute"]
HarnessStatus = Literal["disabled", "dry_run_ready", "blocked", "submitted"]
ProviderSubmitter = Callable[[MediaJobSpec], Mapping[str, Any]]


class AuthorizedLiveHarnessReport(BaseModel):
    harness_id: str
    mode: HarnessMode
    status: HarnessStatus
    provider_call_executed: bool = False
    job_spec: MediaJobSpec | None = None
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
    env = env or os.environ
    harness_id = f"authorized_live_harness_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    if mode == "disabled":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="disabled",
            blocked_reasons=["authorized-live harness is disabled by default"],
        )

    preflight = build_token_smoke_preflight_report(env=env, approval_record_path=approval_record_path)
    job_spec = _build_sample_job_spec(preflight)
    if preflight.blocked:
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            blocked_reasons=[check.detail for check in preflight.checks if check.status == "block"],
            preflight=preflight,
        )

    if mode == "dry_run":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="dry_run_ready",
            job_spec=job_spec,
            preflight=preflight,
        )

    if env.get(EXECUTE_ENV) != "1":
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            blocked_reasons=[f"{EXECUTE_ENV}=1 is required for execute mode"],
            preflight=preflight,
        )

    if submitter is None:
        return AuthorizedLiveHarnessReport(
            harness_id=harness_id,
            mode=mode,
            status="blocked",
            job_spec=job_spec,
            blocked_reasons=["provider submitter is not configured"],
            preflight=preflight,
        )

    response = submitter(job_spec)
    return AuthorizedLiveHarnessReport(
        harness_id=harness_id,
        mode=mode,
        status="submitted",
        provider_call_executed=True,
        job_spec=job_spec,
        provider_response_refs={key: str(value) for key, value in response.items()},
        preflight=preflight,
    )


def _build_sample_job_spec(preflight: TokenSmokePreflightReport | None = None) -> MediaJobSpec:
    provider = preflight.approved_provider if preflight and preflight.approved_provider else "poyo"
    model = preflight.approved_model if preflight and preflight.approved_model else "seedance-2"
    cost_ceiling_usd = (
        preflight.approved_budget_limit_usd
        if preflight and preflight.approved_budget_limit_usd is not None
        else 1.0
    )
    return MediaJobSpec(
        job_id="authorized_live_sample_fixture",
        provider=provider,
        model=model,
        scenario="s1",
        step_name="video_prompts",
        prompt_hash="sha256:authorized_live_sample_fixture",
        prompt_compile_id="pci_authorized_live_sample_fixture",
        brand_bundle_id="bundle_authorized_live_sample_fixture",
        cost_ceiling_usd=cost_ceiling_usd,
    )
