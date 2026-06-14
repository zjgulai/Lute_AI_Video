from __future__ import annotations

import pytest

from src.models.commercial_contracts import (
    BrandConstraintBundle,
    MediaJobSpec,
    MediaJobStatus,
    PlatformTarget,
    PromptCompileInput,
    ProviderCapability,
    StoryboardShotSchema,
)
from src.pipeline.production_job_ledger import ProductionJobLedger
from src.pipeline.provider_prompt_compiler import compile_provider_prompt


def test_prepare_blocked_job_records_reasons_before_provider_submit():
    ledger = ProductionJobLedger()
    spec = _job_spec()

    record = ledger.prepare(spec, blocked_reasons=["rights missing"])

    assert record.status == MediaJobStatus.BLOCKED
    assert record.blocked_reasons == ["rights missing"]
    assert record.publish_allowed is False


def test_job_succeeded_is_not_delivery_accepted_or_publish_allowed():
    ledger = ProductionJobLedger()
    spec = _job_spec()

    ledger.prepare(spec)
    record = ledger.mark_succeeded(spec.job_id, {"video": "fixture://video.mp4"})

    assert record.status == MediaJobStatus.SUCCEEDED
    assert record.delivery_accepted is False
    assert record.publish_allowed is False


def test_publish_allowed_requires_delivery_accepted():
    ledger = ProductionJobLedger()
    spec = _job_spec()
    ledger.prepare(spec)
    ledger.mark_succeeded(spec.job_id, {"video": "fixture://video.mp4"})

    with pytest.raises(ValueError, match="publish_allowed requires accepted delivery"):
        ledger.mark_delivery_decision(spec.job_id, accepted=False, publish_allowed=True)


def test_failed_job_clears_delivery_flags():
    ledger = ProductionJobLedger()
    spec = _job_spec()
    ledger.prepare(spec)

    record = ledger.mark_failed(spec.job_id, "provider timeout")

    assert record.status == MediaJobStatus.FAILED
    assert record.failure_reason == "provider timeout"
    assert record.delivery_accepted is False
    assert record.publish_allowed is False


def test_prepare_from_blocked_compile_result_creates_blocked_job_before_submit():
    ledger = ProductionJobLedger()
    compile_input = _compile_input(reference_asset_ids=["asset_missing_capability"])
    compile_result = compile_provider_prompt(compile_input)

    record = ledger.prepare_from_compile_result(
        job_id="job_from_blocked_compile",
        compile_input=compile_input,
        compile_result=compile_result,
    )

    assert compile_result.blocked is True
    assert record.status == MediaJobStatus.BLOCKED
    assert record.blocked_reasons == compile_result.block_reasons
    assert record.spec.prompt_hash == compile_result.prompt_hash
    assert record.spec.brand_bundle_id == compile_input.brand_bundle.bundle_id


def test_prepare_from_compile_result_creates_prepared_job_when_not_blocked():
    ledger = ProductionJobLedger()
    compile_input = _compile_input(reference_asset_ids=[])
    compile_result = compile_provider_prompt(compile_input)

    record = ledger.prepare_from_compile_result(
        job_id="job_from_compile",
        compile_input=compile_input,
        compile_result=compile_result,
    )

    assert compile_result.blocked is False
    assert record.status == MediaJobStatus.PREPARED
    assert record.spec.provider == compile_result.provider
    assert record.spec.model == compile_result.model


def _job_spec() -> MediaJobSpec:
    return MediaJobSpec(
        job_id="job_fixture",
        provider="poyo",
        model="seedance-2",
        scenario="s1",
        step_name="video_prompts",
        prompt_hash="sha256:fixture",
        prompt_compile_id="pci_fixture",
        brand_bundle_id="bundle_fixture",
    )


def _compile_input(reference_asset_ids: list[str]) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_job_ledger_fixture",
        scenario="s1",
        step_name="video_prompts",
        shot=StoryboardShotSchema(
            shot_id="shot_job_ledger",
            scenario="s1",
            beat="product reveal",
            visual_description="Warm product reveal with no claim",
            reference_asset_ids=reference_asset_ids,
            claim_evidence_refs=["claim_fixture"],
        ),
        brand_bundle=BrandConstraintBundle(
            bundle_id="bundle_job_ledger",
            brand_id="momcozy",
            scenario="s1",
            step="video_prompts",
        ),
        provider_capability=ProviderCapability(
            capability_id="cap_job_ledger",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
        ),
        platform_target=PlatformTarget(platform="tiktok"),
    )
