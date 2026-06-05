"""Dry-run toolbox planner.

This module prepares sanitized plans, prompt previews, job records, and artifact
refs for standalone toolbox tools. It does not call generation providers.
"""

from __future__ import annotations

from typing import Any

from src.models.commercial_contracts import MediaJobRecord, MediaJobSpec, stable_prompt_hash
from src.models.toolbox_contracts import (
    DigitalHumanInput,
    EcommerceVisualInput,
    ProductImageInput,
    SixViewInput,
    StoryboardInput,
    ToolboxArtifact,
    ToolboxArtifactType,
    ToolboxInjectionTarget,
    ToolboxPlan,
    ToolboxPromptPreview,
    ToolboxRequest,
    ToolboxRunState,
    ToolboxRunStatus,
    ToolboxToolId,
)
from src.pipeline.production_job_ledger import ProductionJobLedger
from src.pipeline.toolbox.registry import get_toolbox_tool

TOOLBOX_MOCK_PROVIDER = "dry-run"
TOOLBOX_MOCK_MODEL = "toolbox-fixture-planner-v1"
TOOLBOX_PROVIDER_PROFILE_ID = "profile_toolbox_dry_run_v1"

_INJECTION_STEP_BY_TOOL: dict[ToolboxToolId, str] = {
    ToolboxToolId.PRODUCT_IMAGE: "product_assets",
    ToolboxToolId.SIX_VIEW: "reference_manifest",
    ToolboxToolId.ECOMMERCE_VISUAL: "visual_pack",
    ToolboxToolId.DIGITAL_HUMAN: "presenter_plan",
    ToolboxToolId.STORYBOARD: "storyboards",
}


def build_toolbox_plan(request: ToolboxRequest) -> ToolboxPlan:
    tool = get_toolbox_tool(request.tool_id)
    prompt_hash = stable_prompt_hash(_safe_hash_payload(request))
    return ToolboxPlan(
        plan_id=f"tbx_plan_{request.request_id}",
        request_id=request.request_id,
        tool_id=request.tool_id,
        provider_profile_id=TOOLBOX_PROVIDER_PROFILE_ID,
        prompt_hash=prompt_hash,
        required_checks=tool.default_checks,
        artifact_manifest_id=f"manifest://toolbox/{request.tool_id.value}/{request.request_id}",
        injection_target_refs=_injection_target_refs(request),
    )


def build_toolbox_prompt_preview(request: ToolboxRequest, plan: ToolboxPlan | None = None) -> ToolboxPromptPreview:
    plan = plan or build_toolbox_plan(request)
    return ToolboxPromptPreview(
        preview_id=f"tbx_preview_{request.request_id}",
        request_id=request.request_id,
        tool_id=request.tool_id,
        prompt_hash=plan.prompt_hash,
        prompt_preview_allowed=True,
        sanitized_prompt_blocks=[
            f"tool_id={request.tool_id.value}",
            f"brand_id={request.brand_id}",
            f"platform={request.platform_target.platform}",
            f"aspect_ratio={request.platform_target.aspect_ratio}",
            f"brand_bundle_ref={request.brand_bundle_ref or 'none'}",
            f"asset_ref_count={len(request.asset_refs)}",
            "required_checks=" + ",".join(plan.required_checks),
        ],
    )


def build_toolbox_run_state(request: ToolboxRequest) -> ToolboxRunState:
    plan = build_toolbox_plan(request)
    preview = build_toolbox_prompt_preview(request, plan)
    job_record = _build_prepared_job_record(request, plan, preview)
    artifact = _build_artifact(request)
    injection_targets = _build_injection_targets(request, artifact)
    return ToolboxRunState(
        run_id=f"tbx_run_{request.request_id}",
        request=request,
        plan=plan,
        status=ToolboxRunStatus.ACCEPTED_DRY_RUN,
        prompt_preview=preview,
        artifacts=[artifact],
        injection_targets=injection_targets,
        job_record=job_record,
    )


def project_toolbox_run_state(state: ToolboxRunState) -> dict[str, Any]:
    request = state.request
    return {
        "run_id": state.run_id,
        "request_id": request.request_id,
        "tool_id": request.tool_id.value,
        "brand_id": request.brand_id,
        "brand_bundle_ref": request.brand_bundle_ref,
        "target_scenario": request.target_scenario,
        "asset_refs": [
            asset.model_dump(mode="json", exclude_none=True)
            for asset in request.asset_refs
        ],
        "status": state.status.value,
        "plan": state.plan.model_dump(mode="json", exclude_none=True),
        "prompt_preview": (
            state.prompt_preview.model_dump(mode="json", exclude_none=True)
            if state.prompt_preview is not None
            else None
        ),
        "job_record": (
            state.job_record.model_dump(mode="json", exclude_none=True)
            if state.job_record is not None
            else None
        ),
        "artifacts": [
            artifact.model_dump(mode="json", exclude_none=True)
            for artifact in state.artifacts
        ],
        "injection_targets": [
            target.model_dump(mode="json", exclude_none=True)
            for target in state.injection_targets
        ],
    }


def project_toolbox_artifacts(state: ToolboxRunState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "tool_id": state.request.tool_id.value,
        "artifacts": [
            artifact.model_dump(mode="json", exclude_none=True)
            for artifact in state.artifacts
        ],
    }


def _build_prepared_job_record(
    request: ToolboxRequest,
    plan: ToolboxPlan,
    preview: ToolboxPromptPreview,
) -> MediaJobRecord:
    spec = MediaJobSpec(
        job_id=f"tbx_job_{request.request_id}",
        provider=TOOLBOX_MOCK_PROVIDER,
        model=TOOLBOX_MOCK_MODEL,
        scenario="toolbox",
        step_name=request.tool_id.value,
        prompt_hash=plan.prompt_hash or "sha256:missing",
        prompt_compile_id=preview.preview_id,
        reference_asset_ids=_reference_asset_ids(request),
        brand_bundle_id=request.brand_bundle_ref,
    )
    return ProductionJobLedger().prepare(spec)


def _build_artifact(request: ToolboxRequest) -> ToolboxArtifact:
    artifact_type = _artifact_type_for_tool(request.tool_id)
    return ToolboxArtifact(
        artifact_id=f"tbx_artifact_{request.request_id}",
        tool_id=request.tool_id,
        artifact_type=artifact_type,
        artifact_ref=f"artifact://toolbox/{request.tool_id.value}/{request.request_id}",
        source_job_id=f"tbx_job_{request.request_id}",
        manifest_ref=f"manifest://toolbox/{request.tool_id.value}/{request.request_id}",
    )


def _build_injection_targets(request: ToolboxRequest, artifact: ToolboxArtifact) -> list[ToolboxInjectionTarget]:
    manifest_ref = artifact.manifest_ref or f"manifest://toolbox/{request.tool_id.value}/{request.request_id}"
    bundle_refs = [request.brand_bundle_ref] if request.brand_bundle_ref else []
    return [
        ToolboxInjectionTarget(
            target_ref=_target_ref(request, scenario),
            scenario=scenario,
            step_name=_INJECTION_STEP_BY_TOOL[request.tool_id],
            artifact_refs=[artifact.artifact_ref],
            contract_refs=[manifest_ref, f"job://toolbox/{request.request_id}"],
            bundle_refs=bundle_refs,
        )
        for scenario in get_toolbox_tool(request.tool_id).injectable_scenarios
    ]


def _injection_target_refs(request: ToolboxRequest) -> list[str]:
    return [
        _target_ref(request, scenario)
        for scenario in get_toolbox_tool(request.tool_id).injectable_scenarios
    ]


def _target_ref(request: ToolboxRequest, scenario: str) -> str:
    return f"artifact://toolbox/{request.tool_id.value}/{request.request_id}/inject/{scenario}"


def _artifact_type_for_tool(tool_id: ToolboxToolId) -> ToolboxArtifactType:
    if tool_id == ToolboxToolId.PRODUCT_IMAGE:
        return ToolboxArtifactType.PRODUCT_IMAGE_SET
    if tool_id == ToolboxToolId.SIX_VIEW:
        return ToolboxArtifactType.SIX_VIEW_REFERENCE_MANIFEST
    if tool_id == ToolboxToolId.ECOMMERCE_VISUAL:
        return ToolboxArtifactType.ECOMMERCE_VISUAL_PACK
    if tool_id == ToolboxToolId.DIGITAL_HUMAN:
        return ToolboxArtifactType.PRESENTER_PLAN
    return ToolboxArtifactType.STORYBOARD_PACKAGE


def _reference_asset_ids(request: ToolboxRequest) -> list[str]:
    refs = [asset.asset_ref for asset in request.asset_refs]
    tool_input = request.tool_input
    if isinstance(tool_input, ProductImageInput):
        refs.extend(tool_input.reference_asset_refs)
    if isinstance(tool_input, SixViewInput):
        refs.extend(tool_input.seed_image_refs)
    if isinstance(tool_input, EcommerceVisualInput):
        refs.extend(tool_input.product_image_refs)
    if isinstance(tool_input, StoryboardInput):
        refs.extend(tool_input.asset_refs)
    if isinstance(tool_input, DigitalHumanInput):
        refs.extend(ref for ref in (tool_input.avatar_ref, tool_input.script_ref, tool_input.voice_ref) if ref)
    return sorted(set(refs))


def _safe_hash_payload(request: ToolboxRequest) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "tool_id": request.tool_id.value,
        "brand_id": request.brand_id,
        "brand_bundle_ref": request.brand_bundle_ref,
        "platform": request.platform_target.model_dump(mode="json"),
        "asset_refs": [asset.asset_ref for asset in request.asset_refs],
        "tool_input": _safe_tool_input_summary(request),
    }


def _safe_tool_input_summary(request: ToolboxRequest) -> dict[str, Any]:
    tool_input = request.tool_input
    if isinstance(tool_input, ProductImageInput):
        return {
            "product_ref": tool_input.product_ref,
            "image_type": tool_input.image_type,
            "aspect_ratio": tool_input.aspect_ratio,
            "reference_asset_refs": tool_input.reference_asset_refs,
            "claim_evidence_refs": tool_input.claim_evidence_refs,
        }
    if isinstance(tool_input, SixViewInput):
        return {
            "product_ref": tool_input.product_ref,
            "seed_image_refs": tool_input.seed_image_refs,
            "required_views": tool_input.required_views,
            "consistency_level": tool_input.consistency_level,
        }
    if isinstance(tool_input, EcommerceVisualInput):
        return {
            "channel": tool_input.channel,
            "visual_format": tool_input.visual_format,
            "copy_block_refs": tool_input.copy_block_refs,
            "product_image_refs": tool_input.product_image_refs,
            "aspect_ratio": tool_input.aspect_ratio,
        }
    if isinstance(tool_input, DigitalHumanInput):
        return {
            "presenter_policy": tool_input.presenter_policy,
            "avatar_ref": tool_input.avatar_ref,
            "script_ref": tool_input.script_ref,
            "voice_policy": tool_input.voice_policy,
            "voice_ref": tool_input.voice_ref,
            "consent_ref": tool_input.consent_ref,
        }
    if isinstance(tool_input, StoryboardInput):
        return {
            "script_ref": tool_input.script_ref,
            "duration_target_seconds": tool_input.duration_target_seconds,
            "platform": tool_input.platform,
            "storyboard_grid": tool_input.storyboard_grid,
            "asset_refs": tool_input.asset_refs,
            "planned_timeline_block_count": tool_input.planned_timeline_block_count,
            "review_checkpoint_refs": tool_input.review_checkpoint_refs,
            "source_fingerprint_refs": tool_input.source_fingerprint_refs,
        }
    return {}
