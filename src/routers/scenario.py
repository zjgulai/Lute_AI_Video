"""scenario router — extracted from api.py (P1-11)."""

import asyncio
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = structlog.get_logger()

try:
    from src.storage import HAS_STORAGE
except ImportError:
    HAS_STORAGE = False

from typing import Any

from src.config import DEFAULT_LANGUAGES
from src.models.commercial_contracts import PromptCompileInput, QualityContract
from src.pipeline.prompt_preview_audit_workflow import build_prompt_preview_audit_workflow
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult
from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.scenario_injection_plan import (
    CURRENT_STEP_INJECTION_KEY,
    STEP_INJECTION_DATA_KEY,
    project_state_injection_visibility,
    with_optional_injection_config,
)
from src.routers._deps import (
    _classified_error,
    _inject_api_keys,
    _safe_error,
    get_auth_context,
    verify_api_key,
)
from src.routers._state import (
    _SCENARIO_STEP_ORDER,
    _STEP_DURATIONS,
    FastModeRequest,
    S1StartRequest,
    S2BrandCampaignRequest,
    S3InfluencerRemixRequest,
    S4LiveShootRequest,
    S5BrandVlogRequest,
    _get_step_deps,
    _get_step_output,
    _register_background_task,
    _validate_scenario,
    coerce_video_duration,
)

router = APIRouter()


class PromptPreviewAuditRequest(BaseModel):
    contract: QualityContract
    compile_input: PromptCompileInput
    runtime_injection: RuntimeInjectionResult
    planned_injection: dict[str, Any] | None = None


def _validate_s5_scene_id(scene_id: Any) -> str:
    """Reject scene_id values not present in S5 SCENE_MAP.

    Treats unset/empty as the default "living-room". Raises 422 on unknown
    string values (e.g. "nursery" — removed for child-safety compliance).
    """
    from src.pipeline.s5_brand_vlog_pipeline import SCENE_MAP

    if scene_id is None or scene_id == "":
        return "living-room"
    if not isinstance(scene_id, str) or scene_id not in SCENE_MAP:
        allowed = ", ".join(sorted(SCENE_MAP.keys()))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scene_id: {scene_id!r}. Allowed: {allowed}",
        )
    return scene_id


def _assert_state_access(state: dict[str, Any] | None) -> None:
    """Reject cross-tenant access to persisted pipeline state."""
    if state is None:
        return
    ctx = get_auth_context()
    if ctx is None:
        return
    state_tenant = state.get("tenant_id")
    # Older local/dev states predate tenant ownership. Keep default/test-bundle
    # access compatible, but do not let DB tenant keys inherit orphaned states.
    if not state_tenant:
        if ctx.tenant_id in {"default", "test-bundle"}:
            return
        raise HTTPException(status_code=404, detail="State not found")
    if state_tenant != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="State not found")


def _with_commercial_injection_config(
    config: dict[str, Any],
    plan_payload: dict[str, Any] | None,
    *,
    expected_scenario: str,
) -> dict[str, Any]:
    try:
        return with_optional_injection_config(
            config,
            plan_payload,
            expected_scenario=expected_scenario,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _resume_s1_without_media_synthesis(step_runner: Any, label: str) -> dict[str, Any]:
    """Run S1 only through pre-media steps; stop before provider-backed generation."""
    final_state: dict[str, Any] = {}
    for step_name in get_scenario_step_order("s1"):
        if step_name == "keyframe_images":
            break
        final_state = await step_runner.run_step(label, step_name)
        if final_state.get("pipeline_degraded"):
            break
    if final_state and not final_state.get("pipeline_degraded"):
        final_state["current_step"] = None
        save = getattr(step_runner.state_manager, "save", None)
        if callable(save):
            await save(label, final_state)
    return final_state


S1_BOUNDED_MEDIA_STOP_STEP = "seedance_clips"
S1_BOUNDED_MEDIA_STEP_ORDER = [
    "strategy",
    "scripts",
    "storyboards",
    "continuity_storyboard_grid",
    "keyframe_images",
    "video_prompts",
    "seedance_clips",
]
S1_BOUNDED_MEDIA_PROVIDER_JOB_CAPS = {"image": 1, "video": 1}


def _artifact_storage_scope(disposition: str) -> str:
    if disposition == "pending_review":
        return "tenant_pending_review"
    if disposition == "quarantine":
        return "tenant_quarantine"
    return "default"


async def _resume_s1_bounded_media_pilot(
    step_runner: Any,
    label: str,
    artifact_disposition: str,
    provider_max_retries: int | None,
) -> dict[str, Any]:
    """Run S1 only through bounded image/video generation and stop before publishable work."""
    final_state: dict[str, Any] = {}
    for step_name in S1_BOUNDED_MEDIA_STEP_ORDER:
        final_state = await step_runner.run_step(label, step_name)
        if final_state.get("pipeline_degraded"):
            break
        if step_name == S1_BOUNDED_MEDIA_STOP_STEP:
            final_state["current_step"] = None
            final_state["bounded_media_pilot"] = True
            final_state["bounded_media_stop_step"] = S1_BOUNDED_MEDIA_STOP_STEP
            final_state["artifact_disposition"] = artifact_disposition
            final_state["artifact_storage_scope"] = _artifact_storage_scope(artifact_disposition)
            final_state["provider_max_retries"] = provider_max_retries
            final_state["provider_job_caps"] = dict(S1_BOUNDED_MEDIA_PROVIDER_JOB_CAPS)
            final_state.setdefault("config", {})
            final_state["config"]["provider_max_retries"] = provider_max_retries
            final_state["config"]["provider_job_caps"] = dict(S1_BOUNDED_MEDIA_PROVIDER_JOB_CAPS)
            final_state["config"]["seedance_quality_gate_enabled"] = False
            save = getattr(step_runner.state_manager, "save", None)
            if callable(save):
                await save(label, final_state)
            break
    return final_state


def _assert_prompt_preview_scenario_match(
    scenario: str,
    body: PromptPreviewAuditRequest,
) -> None:
    mismatches: list[str] = []
    if body.contract.scenario != scenario:
        mismatches.append(f"contract.scenario={body.contract.scenario}")
    if body.compile_input.scenario != scenario:
        mismatches.append(f"compile_input.scenario={body.compile_input.scenario}")
    if body.runtime_injection.scenario != scenario:
        mismatches.append(f"runtime_injection.scenario={body.runtime_injection.scenario}")
    if mismatches:
        raise HTTPException(
            status_code=422,
            detail=f"prompt preview audit scenario mismatch: expected {scenario}; "
            + ", ".join(mismatches),
        )


@router.post("/scenario/s1", dependencies=[Depends(verify_api_key)])
async def run_s1_product_direct(body: S1StartRequest | dict[str, Any]):
    """Run S1 Product Direct pipeline (auto mode via StepRunner for progress visibility).

    Uses StepRunner.init_state() + StepRunner.resume() directly so that
    pipeline state is saved after each step, enabling real-time progress
    monitoring by StageProgress polling.

    Phase 2+3: Translates Chinese product inputs to English before
    pipeline execution and forces target_languages to ``["en"]``.
    Original Chinese values are stored in ``_original_zh`` within
    the product_catalog so the frontend can display them.
    """
    raw_body_data = body if isinstance(body, dict) else body.model_dump()
    if isinstance(body, dict):
        body = S1StartRequest(**body)

    # P1-C: 把用户填的多供应商 key 注入 contextvars,LLM/POYO/CosyVoice 客户端
    # 优先读 contextvars,实现按租户隔离,不污染 process-wide os.environ。
    _inject_api_keys(body.api_keys)
    body_data = body.model_dump()
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.tools.translate import translate_catalog_to_english

    product_catalog = body.product_catalog
    product_name = product_catalog.get("product_name", product_catalog.get("name", "unknown"))

    # P3-4: Bind pipeline context to all downstream structlog calls
    structlog.contextvars.bind_contextvars(
        product_name=product_name,
        brand_name=product_catalog.get("brand_name", ""),
        scenario="s1",
        mode="auto",
    )
    product_catalog = await translate_catalog_to_english(product_catalog)
    bounded_media_pilot = body.enable_media_synthesis and body.artifact_disposition in {
        "pending_review",
        "quarantine",
    }
    effective_provider_max_retries = 0 if bounded_media_pilot else body.provider_max_retries
    label = body.output_label

    config = {
        "product_catalog": product_catalog,
        "brand_guidelines": body.brand_guidelines,
        "target_platforms": body.target_platforms or ["tiktok", "shopify"],
        "target_languages": DEFAULT_LANGUAGES,
        "week": body.week,
        "video_duration": coerce_video_duration(body_data),
        "brand_mode": body.brand_mode,
        "enable_media_synthesis": body.enable_media_synthesis,
        "output_label": label,
        "continuity_mode": body.continuity_mode,
        "continuity_generation_mode": body.continuity_generation_mode,
        "storyboard_grid": raw_body_data.get("storyboard_grid", body.storyboard_grid),
        "clip_group_size": body.clip_group_size,
        "transition_style": body.transition_style,
        "artifact_disposition": body.artifact_disposition,
        "provider_max_retries": effective_provider_max_retries,
    }
    if bounded_media_pilot:
        config.update({
            "provider_job_caps": {"image": 1, "video": 1},
            "seedance_quality_gate_enabled": False,
        })
    config = _with_commercial_injection_config(
        config,
        body.commercial_injection_plan,
        expected_scenario="s1",
    )

    state_manager = PipelineStateManager()
    step_runner = StepRunner(state_manager)

    # Initialize state (saved immediately so polling can see it) and run to completion
    label = await step_runner.init_state(config=config, mode="auto", label=label)
    from src.tools.cost_tracker import set_thread_id
    set_thread_id(label)
    try:
        if config["enable_media_synthesis"]:
            if bounded_media_pilot:
                final_state = await _resume_s1_bounded_media_pilot(
                    step_runner,
                    label,
                    body.artifact_disposition,
                    effective_provider_max_retries,
                )
            else:
                final_state = await step_runner.resume(label)
        else:
            final_state = await _resume_s1_without_media_synthesis(step_runner, label)
    except TypeError as te:
        # structlog kwarg compatibility — fall back to legacy pipeline
        import logging as _log
        _log.warning("auto pipeline: StepRunner resume failed (structlog), falling back to S1ProductDirectPipeline: %s", te)
        from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
        p = S1ProductDirectPipeline()
        final_state = await p.run(
            product_catalog=product_catalog,
            brand_guidelines=body.brand_guidelines,
            target_platforms=body.target_platforms or ["tiktok", "shopify"],
            target_languages=DEFAULT_LANGUAGES,
            week=body.week,
            brand_mode=body.brand_mode,
            enable_media_synthesis=body.enable_media_synthesis,
            output_label=body.output_label,
            video_duration=coerce_video_duration(body_data),
            continuity_mode=body.continuity_mode,
            continuity_generation_mode=body.continuity_generation_mode,
            storyboard_grid=raw_body_data.get("storyboard_grid", body.storyboard_grid),
            clip_group_size=body.clip_group_size,
            transition_style=body.transition_style,
            commercial_injection_plan=body.commercial_injection_plan,
            artifact_disposition=body.artifact_disposition,
            provider_max_retries=body.provider_max_retries,
        )
        # S1ProductDirectPipeline returns a dict differently — extract steps from the state
        return final_state

    # Convert back to the result dict format expected by frontend
    seedance_raw = _get_step_output(final_state, "seedance_clips") or {}
    seedance_output = seedance_raw if isinstance(seedance_raw, dict) else {}
    clip_paths = seedance_output.get("clip_paths", []) if isinstance(seedance_raw, dict) else (seedance_raw if isinstance(seedance_raw, list) else [])

    tts_raw = _get_step_output(final_state, "tts_audio") or {}
    if isinstance(tts_raw, dict):
        audio_paths = tts_raw.get("audio_paths", [])
        lyrics_paths = tts_raw.get("lyrics_paths", [])
    else:
        audio_paths = tts_raw if isinstance(tts_raw, list) else []
        lyrics_paths = []

    result = {
        "success": True,
        "label": label,
        "scenario": final_state.get("scenario", "product_direct"),
        "video_duration": config["video_duration"],
        "artifact_disposition": body.artifact_disposition,
        "artifact_storage_scope": _artifact_storage_scope(body.artifact_disposition),
        "provider_max_retries": effective_provider_max_retries,
        "provider_job_caps": dict(S1_BOUNDED_MEDIA_PROVIDER_JOB_CAPS) if bounded_media_pilot else None,
        "bounded_media_pilot": bounded_media_pilot,
        "bounded_media_stop_step": S1_BOUNDED_MEDIA_STOP_STEP if bounded_media_pilot else None,
        "errors": final_state.get("errors", []),
        "media_synthesis_errors": final_state.get("media_synthesis_errors", []),
        "briefs": _get_step_output(final_state, "strategy") or [],
        "scripts": _get_step_output(final_state, "scripts") or [],
        "storyboards": _get_step_output(final_state, "storyboards") or [],
        "keyframe_images": _get_step_output(final_state, "keyframe_images") or [],
        "video_prompts": _get_step_output(final_state, "video_prompts") or [],
        "thumbnail_sets": _get_step_output(final_state, "thumbnail_prompts") or [],
        "seedance_output": seedance_output,
        "clip_paths": clip_paths,
        "audio_paths": audio_paths,
        "lyrics_paths": lyrics_paths,
        "thumbnail_image_paths": _get_step_output(final_state, "thumbnail_images") or [],
        "steps_completed": len(_SCENARIO_STEP_ORDER.get("s1", [])),
    }

    # Extract assemble_final output (may be tuple or dict)
    assemble = _get_step_output(final_state, "assemble_final")
    if isinstance(assemble, (list, tuple)):
        result["final_video_path"] = assemble[0] if len(assemble) > 0 else ""
        result["render_json_path"] = assemble[1] if len(assemble) > 1 else ""
    elif isinstance(assemble, dict):
        result["final_video_path"] = assemble.get("video_path", "")
        result["render_json_path"] = assemble.get("render_json_path", "")
    else:
        result["final_video_path"] = ""
        result["render_json_path"] = ""

    result["audit_report"] = _get_step_output(final_state, "audit") or {}
    if bounded_media_pilot:
        result["final_video_path"] = ""
        result["render_json_path"] = ""
        result["thumbnail_sets"] = []
        result["thumbnail_image_paths"] = []
        result["audio_paths"] = []
        result["lyrics_paths"] = []
        result["audit_report"] = {}
        result["delivery_accepted"] = False
        result["publish_allowed"] = False
        result["approved_brand_token_write"] = False
        result["provider_job_caps"] = dict(S1_BOUNDED_MEDIA_PROVIDER_JOB_CAPS)
        result["steps_completed"] = S1_BOUNDED_MEDIA_STEP_ORDER.index(S1_BOUNDED_MEDIA_STOP_STEP) + 1
    return result


@router.post("/scenario/s2", dependencies=[Depends(verify_api_key)])
async def run_s2_brand_campaign(body: S2BrandCampaignRequest):
    """Run S2 Brand Campaign pipeline."""
    _inject_api_keys(body.api_keys)  # P1-C: 用户 key 注入 contextvars
    body_data = body.model_dump()
    commercial_injection_plan = _with_commercial_injection_config(
        {},
        body.commercial_injection_plan,
        expected_scenario="s2",
    ).get("commercial_injection_plan")

    brand_package = body.brand_package
    # P3-4: Bind pipeline context to all downstream structlog calls
    structlog.contextvars.bind_contextvars(
        product_name=brand_package.get("brand_name", "unknown"),
        brand_name=brand_package.get("brand_name", ""),
        scenario="s2",
        mode="auto",
    )

    from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline
    p = S2BrandCampaignPipeline()
    r = await p.run(
        brand_package=body.brand_package,
        target_platforms=body.target_platforms,
        target_languages=body.target_languages,
        week=body.week,
        video_duration=coerce_video_duration(body_data, default=60),
        enable_media_synthesis=body.enable_media_synthesis,
        artifact_disposition=body.artifact_disposition,
        provider_max_retries=body.provider_max_retries,
        output_label=body.output_label,
        media_stop_step=body.media_stop_step,
        media_refs=body.media_refs,
        commercial_injection_plan=commercial_injection_plan,
    )
    return r


@router.post("/scenario/s3", dependencies=[Depends(verify_api_key)])
async def run_s3_influencer_remix(body: S3InfluencerRemixRequest | dict[str, Any]):
    """Run S3 Influencer Remix pipeline.

    Phase 2+3: Translates Chinese product inputs to English before
    pipeline execution and forces target_languages to ``["en"]``.
    Original Chinese values are stored in ``_original_zh`` within
    the product dict so the frontend can display them.

    Request body:
        video_url: str
        product: dict (with name, usps, etc.)
        influencer_name: str (optional)
        brief_id: str (optional)
        video_duration: int (optional, default 30, valid: 15/30/45/60/90)
    """
    body_data = body if isinstance(body, dict) else body.model_dump()
    if isinstance(body, dict):
        body = S3InfluencerRemixRequest(**body)

    _inject_api_keys(body.api_keys)  # P1-C: 用户 key 注入 contextvars
    from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline
    from src.tools.translate import translate_catalog_to_english

    product = body.product
    if isinstance(product, dict):
        product = await translate_catalog_to_english(product)

    # P3-4: Bind pipeline context to all downstream structlog calls
    structlog.contextvars.bind_contextvars(
        product_name=product.get("name", "unknown") if isinstance(product, dict) else "unknown",
        brand_name="",
        scenario="s3",
        video_url=body.video_url[:50],
    )

    bounded_media_pilot = body.enable_media_synthesis and body.artifact_disposition in {
        "pending_review",
        "quarantine",
    }
    effective_provider_max_retries = 0 if bounded_media_pilot else body.provider_max_retries
    commercial_injection_plan = _with_commercial_injection_config(
        {},
        body.commercial_injection_plan,
        expected_scenario="s3",
    ).get("commercial_injection_plan")

    p = S3InfluencerRemixPipeline()
    r = await p.run(
        video_url=body.video_url,
        product=product,
        influencer_name=body.influencer_name,
        brief_id=body.brief_id,
        target_platforms=body.target_platforms,
        video_duration=coerce_video_duration(body_data),
        enable_media_synthesis=body.enable_media_synthesis,
        output_label=body.output_label,
        artifact_disposition=body.artifact_disposition,
        provider_max_retries=effective_provider_max_retries,
        commercial_injection_plan=commercial_injection_plan,
    )
    return r.to_dict()


@router.post("/scenario/s4", dependencies=[Depends(verify_api_key)])
async def run_s4_live_shoot(body: S4LiveShootRequest | dict[str, Any]):
    """Run S4 Live Shoot to Video pipeline."""
    body_data = body if isinstance(body, dict) else body.model_dump()
    if isinstance(body, dict):
        body = S4LiveShootRequest(**body)

    _inject_api_keys(body.api_keys)  # P1-C: 用户 key 注入 contextvars
    from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
    product_info = body.product_info
    # P3-4: Bind pipeline context
    structlog.contextvars.bind_contextvars(
        product_name=product_info.get("name", "unknown"),
        brand_name=product_info.get("brand_name", ""),
        scenario="s4",
        topic=body.topic[:50],
    )
    bounded_media_pilot = body.enable_media_synthesis and body.artifact_disposition in {
        "pending_review",
        "quarantine",
    }
    effective_provider_max_retries = 0 if bounded_media_pilot else body.provider_max_retries
    commercial_injection_plan = _with_commercial_injection_config(
        {},
        body.commercial_injection_plan,
        expected_scenario="s4",
    ).get("commercial_injection_plan")
    p = S4LiveShootPipeline()
    r = await p.run(
        footage_assets=body.footage_assets,
        product_info=product_info,
        topic=body.topic,
        target_platforms=body.target_platforms,
        brand_guidelines=body.brand_guidelines,
        video_duration=coerce_video_duration(body_data),
        enable_media_synthesis=body.enable_media_synthesis,
        output_label=body.output_label,
        artifact_disposition=body.artifact_disposition,
        provider_max_retries=effective_provider_max_retries,
        commercial_injection_plan=commercial_injection_plan,
    )
    return r


@router.post("/scenario/s5", dependencies=[Depends(verify_api_key)])
async def run_s5_brand_vlog(body: S5BrandVlogRequest, request: Request = None):
    """Run S5 Brand VLOG pipeline.

    Request body:
        brand_id: str — brand identifier (e.g. "momcozy")
        product_sku: dict — product SKU with views[] (six-view angles)
        scene_id: str — scene identifier (office/living-room/bedroom/outdoor/kitchen)
        selected_models: list[dict] — model profiles with name/role/description
        story_description: str — user's story direction (max 300 chars)
        video_duration: int — target video seconds (15/30/45/60/90)
    """
    _inject_api_keys(body.api_keys)  # P1-C: 用户 key 注入 contextvars
    body_data = body.model_dump()
    raw_body = await request.json() if request is not None else {}
    enable_media_synthesis = True
    if isinstance(raw_body, dict):
        enable_media_synthesis = raw_body.get("enable_media_synthesis", True) is not False
    bounded_media_pilot = enable_media_synthesis and body.artifact_disposition in {
        "pending_review",
        "quarantine",
    }
    effective_provider_max_retries = 0 if bounded_media_pilot else body.provider_max_retries
    commercial_injection_plan = _with_commercial_injection_config(
        {},
        body.commercial_injection_plan,
        expected_scenario="s5",
    ).get("commercial_injection_plan")
    product_sku = body.product_sku
    brand_id = body.brand_id
    scene_id = _validate_s5_scene_id(body.scene_id)
    structlog.contextvars.bind_contextvars(
        product_name=product_sku.get("name", "unknown") if isinstance(product_sku, dict) else "unknown",
        brand_name=brand_id,
        scenario="s5",
        scene_id=scene_id,
    )
    from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
    p = S5BrandVlogPipeline()
    r = await p.run(
        brand_id=body.brand_id,
        product_sku=body.product_sku,
        scene_id=scene_id,
        selected_models=body.selected_models,
        story_description=body.story_description,
        video_duration=coerce_video_duration(body_data),
        commercial_injection_plan=commercial_injection_plan,
        enable_media_synthesis=enable_media_synthesis,
        output_label=body.output_label,
        artifact_disposition=body.artifact_disposition,
        provider_max_retries=effective_provider_max_retries,
    )
    return r


@router.post("/fast/generate", dependencies=[Depends(verify_api_key)])
async def fast_generate(req: FastModeRequest):
    """Fast Mode: direct text-to-video generation without pipeline.

    Uses LLM to enhance user prompt, then calls Seedance directly.
    No LangGraph, no steps, no gates. Returns video + debug info.

    Request:
        user_prompt: Simple text description (any language)
        duration: 10 or 15 seconds (default 15)
        enable_tts: Whether to generate CosyVoice voiceover

    Returns:
        {
            success: bool,
            video_path: str,
            video_url: str,
            filename: str,
            llm_prompt: str,
            scene_description: str,
            duration_seconds: int,
            file_size_bytes: int,
            generation_time_ms: int,
            timing: { llm_ms, video_ms, tts_ms },
            model_info: { llm, video, tts },
            is_stub: bool,
            tts_path: str | null,
        }
    """
    _inject_api_keys(req.api_keys)  # P1-C: 用户 key 注入 contextvars
    from src.services.fast_mode import get_fast_mode_service

    service = get_fast_mode_service()
    ctx = get_auth_context()
    tenant_id = ctx.tenant_id if ctx is not None else "default"
    try:
        result = await service.generate(
            user_prompt=req.user_prompt,
            duration=max(10, min(15, req.duration)),
            enable_tts=req.enable_tts,
            artifact_disposition=req.artifact_disposition,
            tenant_id=tenant_id,
            artifact_run_id=f"fast_generate_{int(time.time())}",
            provider_max_retries=req.provider_max_retries,
        )
        return result
    except Exception as e:
        logger.error("fast_mode failed", error=str(e))
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/fast/submit", dependencies=[Depends(verify_api_key)])
async def fast_submit(req: FastModeRequest):
    """Fast Mode async submit — returns task_id immediately, status polled separately.

    Companion to /fast/generate (sync, blocks 5-10 min). This endpoint kicks off
    generation in a background task and returns within ~50ms with a task_id.
    Frontend polls GET /fast/status/{task_id} to track progress.

    Returns:
        { task_id, status: "queued", started_at_unix }
    """
    _inject_api_keys(req.api_keys)
    from src.services.fast_mode import get_fast_mode_service
    from src.tasks.fast_task_registry import (
        register_fast_task,
        update_fast_task_stage,
    )

    service = get_fast_mode_service()
    ctx = get_auth_context()
    tenant_id = ctx.tenant_id if ctx is not None else "default"
    duration = max(10, min(15, req.duration))
    enable_tts = req.enable_tts
    user_prompt = req.user_prompt
    artifact_disposition = req.artifact_disposition
    provider_max_retries = req.provider_max_retries

    task_id_holder: dict[str, str] = {}

    async def _run() -> dict[str, Any]:
        tid = task_id_holder.get("id", "")

        def _on_stage(stage: str) -> None:
            if tid:
                update_fast_task_stage(tid, stage)

        return await service.generate(
            user_prompt=user_prompt,
            duration=duration,
            enable_tts=enable_tts,
            on_stage=_on_stage,
            artifact_disposition=artifact_disposition,
            tenant_id=tenant_id,
            artifact_run_id=tid or None,
            provider_max_retries=provider_max_retries,
        )

    task = asyncio.create_task(_run())
    task_id = register_fast_task(task)
    task_id_holder["id"] = task_id

    return {
        "task_id": task_id,
        "status": "queued",
        "started_at_unix": int(time.time()),
    }


@router.get("/fast/status/{task_id}", dependencies=[Depends(verify_api_key)])
async def fast_status(task_id: str):
    """Poll Fast Mode async task progress.

    Returns:
        { task_id, status: "running"|"done"|"failed",
          stage: "queued"|"llm"|"video"|"tts",
          elapsed_sec, result?, error? }

    HTTP semantics:
        200 OK — task exists; check status field
        404 Not Found — task_id unknown or expired (>10min after completion)
    """
    from src.tasks.fast_task_registry import get_fast_task

    snapshot = get_fast_task(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Unknown or expired task_id: {task_id}")
    return snapshot


@router.post("/scenario/s1/start", dependencies=[Depends(verify_api_key)])
async def start_s1_pipeline(body: S1StartRequest):
    """Start a new S1 pipeline run in either "auto" or "step_by_step" mode.

    Request body:
        product_catalog: dict (required)
        brand_guidelines: dict
        target_platforms: list[str]
        target_languages: list[str]
        week: str
        video_duration: int
        mode: "auto" | "step_by_step" (default: "auto")
        brand_mode: bool (default: false)

    Returns:
        Initialized state dict with label, mode, status, and current_step.
        If mode is "auto", runs to completion and returns final state.
    """
    _inject_api_keys(body.api_keys)  # P1-C: 用户 key 注入 contextvars
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    # P3-4: Bind pipeline context to all downstream structlog calls
    product = body.product_catalog.get("product_name") or body.product_catalog.get("name", "unknown")
    brand = body.brand_guidelines.get("brand_name", "") if body.brand_guidelines else ""
    structlog.contextvars.bind_contextvars(
        product_name=product,
        brand_name=brand,
        scenario="s1",
        mode=body.mode,
    )

    try:
        step_runner = StepRunner(PipelineStateManager())
        config = _with_commercial_injection_config(
            body.model_dump(),
            body.commercial_injection_plan,
            expected_scenario="s1",
        )
        bounded_media_pilot = body.enable_media_synthesis and body.artifact_disposition in {
            "pending_review",
            "quarantine",
        }
        effective_provider_max_retries = 0 if bounded_media_pilot else body.provider_max_retries
        config["provider_max_retries"] = effective_provider_max_retries
        if bounded_media_pilot:
            config.update({
                "provider_job_caps": {"image": 1, "video": 1},
                "seedance_quality_gate_enabled": False,
            })
        label = await step_runner.init_state(config=config, mode=body.mode, label=body.output_label)

        if body.mode == "auto":
            if body.enable_media_synthesis:
                if bounded_media_pilot:
                    return await _resume_s1_bounded_media_pilot(
                        step_runner,
                        label,
                        body.artifact_disposition,
                        effective_provider_max_retries,
                    )
                return await step_runner.resume(label)
            return await _resume_s1_without_media_synthesis(step_runner, label)

        return {
            "label": label,
            "mode": body.mode,
            "status": "initialized",
            "current_step": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("s1 pipeline failed", error=str(e))
        raise HTTPException(status_code=500, detail=_classified_error(e))


@router.post("/scenario/s1/step/{step_name}", dependencies=[Depends(verify_api_key)])
async def run_s1_step(step_name: str, body: dict[str, Any]):
    """Execute a single step of the S1 pipeline.

    Args:
        step_name: One of the valid pipeline step names.
        body: dict with "label" key.

    Returns:
        Updated pipeline state dict after executing the step.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(body["label"])
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {body['label']}")
        _assert_state_access(state)

        step_runner = StepRunner(state_manager)
        result = await step_runner.run_step(body["label"], step_name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("s1 step failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/regenerate", dependencies=[Depends(verify_api_key)])
async def regenerate_s1_step(body: dict[str, Any]):
    """Force re-execution of a specific step and invalidate all downstream.

    Request body:
        label: str — pipeline run label
        step: str — step name to regenerate

    Invalidates all downstream steps (marking them as pending) so they
    are re-executed with the updated input.

    Returns:
        Updated pipeline state dict with regenerated step done and
        downstream steps pending.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_editor import invalidate_downstream
    from src.pipeline.step_runner import StepRunner

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(body["label"])
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {body['label']}")
        _assert_state_access(state)

        await invalidate_downstream(body["label"], body["step"], state_manager)
        step_runner = StepRunner(state_manager)
        result = await step_runner.regenerate_step(body["label"], body["step"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/resume", dependencies=[Depends(verify_api_key)])
async def resume_s1_pipeline(body: dict[str, Any]):
    """Resume execution from current_step to completion.

    Request body:
        label: str — pipeline run label

    Returns:
        Final pipeline state dict.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(body["label"])
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {body['label']}")
        _assert_state_access(state)

        step_runner = StepRunner(state_manager)
        result = await step_runner.resume(body["label"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("s1 regenerate failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/scenario/s1/state/{label}", dependencies=[Depends(verify_api_key)])
async def get_s1_state(label: str):
    """Get the current pipeline state for a given label.

    Returns:
        Pipeline state dict, or 404 if not found.
    """
    from src.pipeline.state_manager import PipelineStateManager

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)
        result = project_state_injection_visibility(state)
        result["meta"] = {
            "step_order": _SCENARIO_STEP_ORDER.get("s1", []),
            "step_durations": _STEP_DURATIONS,
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("s1 resume failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.put("/scenario/s1/state/{label}", dependencies=[Depends(verify_api_key)])
async def update_s1_state(label: str, body: dict[str, Any]):
    """Update the pipeline state (used after user edits a step output).

    Request body:
        Partial or full state updates. Common use case:
        { "steps": { "scripts": { "edited_output": {...}, "edited": true } } }

    Logic:
        Loads existing state, deep-merges request body, saves back.

    Returns:
        Updated pipeline state dict.
    """
    from src.pipeline.state_manager import PipelineStateManager

    def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        for key, value in updates.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        updated_state = deep_merge(state, body)
        await state_manager.save(label, updated_state)
        return updated_state
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("s1 state update failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/scenario/{scenario}/state/{label}/steps", dependencies=[Depends(verify_api_key)])
async def list_steps(scenario: str, label: str):
    """List all pipeline steps with status and brief output preview.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label.

    Returns:
        Array of {step_name, status, preview, has_output, completed_at}.
    """
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        projected_state = project_state_injection_visibility(state)
        steps_data = projected_state.get("steps", {})
        order = _SCENARIO_STEP_ORDER[scenario]
        result = []
        for step_name in order:
            sd = steps_data.get(step_name, {})
            status = sd.get("status", "pending")
            output = sd.get("output")
            edited_output = sd.get("edited_output") if sd.get("edited") else None

            # Generate a text preview from the output
            preview = ""
            display_output = edited_output if edited_output is not None else output
            if display_output:
                if isinstance(display_output, list):
                    preview = f"[{len(display_output)} items]"
                elif isinstance(display_output, dict):
                    if "overall_status" in display_output:
                        preview = str(display_output.get("overall_status", ""))
                    elif "summary" in display_output:
                        preview = str(display_output.get("summary", ""))[:80]
                    else:
                        preview = str(list(display_output.keys())[:3])
                elif isinstance(display_output, str):
                    preview = display_output[:80]
                else:
                    preview = str(display_output)[:80]

            item = {
                "step_name": step_name,
                "status": status,
                "preview": preview,
                "has_output": output is not None,
                "is_edited": sd.get("edited", False),
                "completed_at": sd.get("completed_at", ""),
            }
            commercial_injection = sd.get(STEP_INJECTION_DATA_KEY)
            if commercial_injection is not None:
                item[STEP_INJECTION_DATA_KEY] = commercial_injection
            result.append(item)

        return {
            "label": label,
            "scenario": scenario,
            "current_step": projected_state.get("current_step"),
            CURRENT_STEP_INJECTION_KEY: projected_state.get(CURRENT_STEP_INJECTION_KEY),
            "steps": result,
            "meta": {
                "step_order": _SCENARIO_STEP_ORDER.get(scenario, []),
                "step_durations": _STEP_DURATIONS,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("list_steps failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/step/{step_name}", dependencies=[Depends(verify_api_key)])
async def execute_step(scenario: str, step_name: str, body: dict[str, Any]):
    """Execute a SINGLE step of the pipeline.

    If the step has already completed, returns cached result.
    If prior steps are not complete, returns 400 with listing of incomplete deps.

    Request body:
        label: str — pipeline run label

    Returns:
        { step, status, data } or error details.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    _validate_scenario(scenario)
    label = body.get("label", "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Missing required field: label")

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        steps_data = state.get("steps", {})
        deps = _get_step_deps(scenario, step_name)
        missing_deps: list[dict[str, Any]] = []
        for dep in deps:
            sd = steps_data.get(dep, {})
            if sd.get("status") != "done":
                missing_deps.append({"step": dep, "status": sd.get("status", "pending")})

        if missing_deps:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Cannot execute '{step_name}': prior steps not complete",
                    "missing_deps": missing_deps,
                },
            )

        # If step already done, return cached result
        step_data = steps_data.get(step_name, {})
        if step_data.get("status") == "done":
            output = step_data.get("edited_output") if step_data.get("edited") else step_data.get("output")
            return {
                "step": step_name,
                "status": "completed",
                "cached": True,
                "data": output,
            }

        step_runner = StepRunner(state_manager)
        updated_state = await step_runner.run_step(label, step_name)
        updated_step = updated_state.get("steps", {}).get(step_name, {})
        output = updated_step.get("edited_output") if updated_step.get("edited") else updated_step.get("output")
        step_status = updated_step.get("status", "failed")
        return {
            "step": step_name,
            "status": "completed" if step_status == "done" else "failed",
            "data": output,
        }

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("execute_step failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/prompt-preview/audit", dependencies=[Depends(verify_api_key)])
async def audit_prompt_preview(scenario: str, body: PromptPreviewAuditRequest):
    """Build a dry-run prompt preview audit bundle without exposing prompt payload."""
    _validate_scenario(scenario)
    _assert_prompt_preview_scenario_match(scenario, body)

    try:
        bundle = build_prompt_preview_audit_workflow(
            contract=body.contract,
            compile_input=body.compile_input,
            runtime_injection=body.runtime_injection,
            planned_injection=body.planned_injection,
        )
        return bundle.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.error("audit_prompt_preview failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.put("/scenario/{scenario}/state/{label}", dependencies=[Depends(verify_api_key)])
async def edit_step_output(scenario: str, label: str, body: dict[str, Any]):
    """Update the state for a step's output (allows user editing).

    Request body:
        step_name: str — the step to update
        updates: any — the updated step output data

    Returns:
        { label, updated_step, state }.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_editor import update_step_output

    _validate_scenario(scenario)
    step_name = body.get("step_name", "").strip()
    updates = body.get("updates")
    if not step_name:
        raise HTTPException(status_code=400, detail="Missing required field: step_name")
    if updates is None:
        raise HTTPException(status_code=400, detail="Missing required field: updates")

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        result = await update_step_output(label, step_name, updates)
        return {
            "label": label,
            "updated_step": step_name,
            "state": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import logging
        logging.error("edit_step_output failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/regenerate/{label}/{step_name}", dependencies=[Depends(verify_api_key)])
async def regenerate_step(scenario: str, label: str, step_name: str):
    """Re-run a specific step (e.g., after user edited its input).

    Invalidates all downstream steps by marking them as "pending"
    so they will be re-executed.

    Returns:
        { label, regenerated_step, invalidated: [...] }
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_editor import invalidate_downstream
    from src.pipeline.step_runner import StepRunner

    _validate_scenario(scenario)
    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        order = _SCENARIO_STEP_ORDER[scenario]
        try:
            step_idx = order.index(step_name)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown step: {step_name}")

        downstream = order[step_idx + 1:]

        step_runner = StepRunner(state_manager)
        # invalidate_downstream marks steps as pending
        await invalidate_downstream(label, step_name, state_manager)
        # Then regenerate the specified step
        await step_runner.regenerate_step(label, step_name)

        return {
            "label": label,
            "regenerated_step": step_name,
            "invalidated": downstream,
        }

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("regenerate_step failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/scenario/{scenario}/gate/{label}/{gate_id}", dependencies=[Depends(verify_api_key)])
async def get_gate(scenario: str, label: str, gate_id: str):
    """Get gate state and candidates for Expert Studio approval.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label.
        gate_id: Gate identifier (e.g., "gate_1_script").

    Returns:
        Gate state dict with candidates, status, selections.
    """
    from src.pipeline.gate_manager import get_gate_state as _get_gate_state
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    state = await PipelineStateManager().load(label)
    if state is None:
        raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
    _assert_state_access(state)

    result = await _get_gate_state(label, gate_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/scenario/{scenario}/gate/{label}/{gate_id}/generate", dependencies=[Depends(verify_api_key)])
async def generate_gate_candidates(scenario: str, label: str, gate_id: str):
    """Generate 3 candidates (standard/creative/conservative) for a gate.

    Each candidate is generated via the corresponding pipeline skill,
    scored by the AI evaluator, and ranked with a recommendation.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label.
        gate_id: Gate identifier (e.g., "gate_1_script").

    Returns:
        dict with candidates array, gate_id, label.
    """
    from src.pipeline.gate_manager import generate_candidates as _generate_candidates
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    try:
        state = await PipelineStateManager().load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        result = await _generate_candidates(label, gate_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("generate_gate_candidates failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/gate/{label}/{gate_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_gate_decision(scenario: str, label: str, gate_id: str, body: dict[str, Any]):
    """Approve a gate with selected candidate IDs.

    Request body:
        selected_ids: list[str] — candidate IDs the user selected.

    Records the approval, sets the selected candidate's output as the
    step output for downstream steps, and advances the pipeline.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label.
        gate_id: Gate identifier (e.g., "gate_1_script").

    Returns:
        Approval result with selected_ids and next_step.
    """
    from src.pipeline.gate_manager import approve_gate as _approve_gate
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    selected_ids = body.get("selected_ids", [])
    if not selected_ids or not isinstance(selected_ids, list):
        raise HTTPException(status_code=400, detail="Missing or invalid required field: selected_ids (list[str])")

    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        result = await _approve_gate(label, gate_id, selected_ids)
        if "error" in result:
            status_code = 400
            if "already approved" in result.get("error", ""):
                status_code = 409
            raise HTTPException(status_code=status_code, detail=result["error"])
        if result.get("idempotent") is True:
            result["resumed"] = False
            result["resuming"] = False
            return result

        # Auto-resume pipeline after gate approval (step-by-step mode)
        # Resume runs from current_step until the next gate or completion.
        # Resume can take 5-30 minutes (keyframe generation + video synthesis).
        # Run in background to avoid HTTP 504 Gateway Timeout.
        async def _background_resume() -> None:
            import structlog

            log = structlog.get_logger()
            try:
                from src.pipeline.step_runner import StepRunner

                step_runner = StepRunner(state_manager)
                await step_runner.resume(label)
                log.info(
                    "background_resume_complete",
                    label=label,
                    gate_id=gate_id,
                )
            except Exception as resume_err:
                log.warning(
                    "background_resume_failed",
                    label=label,
                    gate_id=gate_id,
                    error=str(resume_err)[:200],
                )
                raise  # Re-raise so _register_background_task logs it

        task = asyncio.create_task(_background_resume())
        task_id = _register_background_task(task, label)
        result["resumed"] = True
        result["resuming"] = True
        result["background_task_id"] = task_id

        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("approve_gate_decision failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/gate/{label}/{gate_id}/regenerate/{candidate_id}", dependencies=[Depends(verify_api_key)])
async def regenerate_gate_candidate(scenario: str, label: str, gate_id: str, candidate_id: str):
    """Regenerate a single candidate for a gate.

    Re-executes the skill for the candidate's variant, re-scores it,
    and updates the candidate in place. Re-computes the recommendation.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label.
        gate_id: Gate identifier (e.g., "gate_1_script").
        candidate_id: The specific candidate ID to regenerate.

    Returns:
        Updated candidate dict with new data and score.
    """
    from src.pipeline.gate_manager import regenerate_candidate as _regenerate_candidate
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    try:
        state = await PipelineStateManager().load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        result = await _regenerate_candidate(label, gate_id, candidate_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("regenerate_gate_candidate failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ── Unified Async Execution (Phase 1A) ──


@router.post("/scenario/{scenario}/submit", dependencies=[Depends(verify_api_key)])
async def submit_scenario(scenario: str, body: dict[str, Any]):
    """Submit a scenario for async execution.

    Initializes pipeline state and immediately returns a label.
    The pipeline runs in the background — use GET /status/{label} to poll.

    Args:
        scenario: "s1", "s2", "s3", "s4", or "s5"
        body: Scenario-specific config dict (same as /scenario/{s} endpoints)

    Returns:
        { label, status: "queued", trace_id }
    """
    _validate_scenario(scenario)
    _inject_api_keys(body.get("api_keys", {}))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.tools.cost_tracker import set_thread_id

    step_runner = StepRunner(PipelineStateManager())

    # Build config per-scenario (same logic as blocking endpoints)
    if scenario == "s1":
        from src.tools.translate import translate_catalog_to_english
        product_catalog = body.get("product_catalog", {})
        product_catalog = await translate_catalog_to_english(product_catalog)
        config = {
            "product_catalog": product_catalog,
            "brand_guidelines": body.get("brand_guidelines"),
            "target_platforms": body.get("target_platforms", ["tiktok", "shopify"]),
            "target_languages": DEFAULT_LANGUAGES,
            "week": body.get("week", ""),
            "video_duration": coerce_video_duration(body),
            "brand_mode": body.get("brand_mode", False),
            "enable_media_synthesis": body.get("enable_media_synthesis", True),
            "continuity_mode": body.get("continuity_mode", True),
            "continuity_generation_mode": body.get("continuity_generation_mode", "standard"),
            "storyboard_grid": body.get("storyboard_grid", 12),
            "clip_group_size": body.get("clip_group_size", 3),
            "transition_style": body.get("transition_style", "match_cut"),
        }
        config = _with_commercial_injection_config(
            config,
            body.get("commercial_injection_plan"),
            expected_scenario="s1",
        )
    elif scenario == "s2":
        brand_package = body.get("brand_package", {})
        brand_name = brand_package.get("brand_name", "Brand")
        # S2 is an S1 wrapper in brand_mode — construct a minimal product_catalog
        # so S1's _step_strategy can run without KeyError.
        product_catalog = {
            "product_name": brand_name,
            "name": brand_name,
            "brand_name": brand_name,
            "category": "brand_campaign",
            "usps": brand_package.get("product_lines", ["quality"]),
        }
        config = {
            "product_catalog": product_catalog,
            "brand_guidelines": brand_package,
            "brand_mode": True,
            "target_platforms": body.get("target_platforms", ["tiktok", "shopify"]),
            "target_languages": body.get("target_languages", DEFAULT_LANGUAGES),
            "week": body.get("week", ""),
            "enable_media_synthesis": True,
        }
        config = _with_commercial_injection_config(
            config,
            body.get("commercial_injection_plan"),
            expected_scenario="s2",
        )
    elif scenario == "s3":
        from src.tools.translate import translate_catalog_to_english
        product = body.get("product", {})
        if isinstance(product, dict):
            product = await translate_catalog_to_english(product)
        config = {
            "video_url": body.get("video_url", ""),
            "product": product,
            "influencer_name": body.get("influencer_name", "Influencer"),
            "brief_id": body.get("brief_id", ""),
            "video_duration": coerce_video_duration(body),
        }
    elif scenario == "s4":
        config = {
            "footage_assets": body.get("footage_assets", []),
            "product_info": body.get("product_info", {}),
            "topic": body.get("topic", ""),
            "target_platforms": body.get("target_platforms", ["tiktok"]),
        }
    elif scenario == "s5":
        config = {
            "brand_id": body.get("brand_id", "momcozy"),
            "product_sku": body.get("product_sku", {}),
            "scene_id": _validate_s5_scene_id(body.get("scene_id")),
            "selected_models": body.get("selected_models", []),
            "story_description": body.get("story_description", ""),
            "video_duration": coerce_video_duration(body),
        }
        config = _with_commercial_injection_config(
            config,
            body.get("commercial_injection_plan"),
            expected_scenario="s5",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario}")

    label = await step_runner.init_state(config=config, mode="auto", scenario=scenario)
    set_thread_id(label)

    # Start pipeline in background so HTTP returns immediately
    async def _background_run() -> None:
        try:
            if scenario == "s1" and config.get("enable_media_synthesis") is False:
                await _resume_s1_without_media_synthesis(step_runner, label)
            else:
                await step_runner.resume(label)
        except Exception as e:
            logger.error("background_run_failed", label=label, scenario=scenario, error=str(e)[:200])

    task = asyncio.create_task(_background_run())
    _register_background_task(task, label)

    return {
        "label": label,
        "status": "queued",
        "trace_id": label.split("_")[-1] if "_" in label else "",
    }


@router.get("/scenario/{scenario}/status/{label}", dependencies=[Depends(verify_api_key)])
async def get_scenario_status(scenario: str, label: str):
    """Get current execution status for a pipeline run.

    Args:
        scenario: Scenario identifier (e.g., "s1").
        label: Pipeline run label from /submit.

    Returns:
        {
            label, status, current_step, progress, pipeline_degraded,
            gate_status, result, errors
        }
    """
    from src.pipeline.continuity_utils import extract_continuity_diagnostics
    from src.pipeline.state_manager import PipelineStateManager

    _validate_scenario(scenario)
    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
        _assert_state_access(state)

        projected_state = project_state_injection_visibility(state)
        step_order = _SCENARIO_STEP_ORDER.get(scenario, [])
        current_step = projected_state.get("current_step", "")
        steps = projected_state.get("steps", {})
        audit_report = steps.get("audit", {}).get("output") or {}

        # Calculate progress: done steps / total steps
        done_count = sum(1 for s in steps.values() if s.get("status") == "done")
        total = len(step_order)
        progress = round(done_count / total, 2) if total > 0 else 0.0

        # Determine overall status
        if state.get("pipeline_degraded"):
            status = "error"
        elif current_step is None or current_step == "":
            status = "completed"
        elif steps.get(current_step, {}).get("status") == "error":
            status = "error"
        else:
            gate_status = state.get("gate_status")
            if gate_status == "awaiting_approval":
                status = "paused"
            else:
                status = "running"

        return {
            "label": label,
            "scenario": scenario,
            "status": status,
            "current_step": current_step,
            CURRENT_STEP_INJECTION_KEY: projected_state.get(CURRENT_STEP_INJECTION_KEY),
            "progress": progress,
            "pipeline_degraded": projected_state.get("pipeline_degraded", False),
            "soft_degraded_reasons": projected_state.get("soft_degraded_reasons", []),
            "continuity_diagnostics": extract_continuity_diagnostics(audit_report),
            "gate_status": projected_state.get("gate_status"),
            "errors": projected_state.get("errors", []),
            "result": projected_state.get("result"),
            "steps": steps,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_scenario_status failed", label=label, error=str(e)[:200])
        raise HTTPException(status_code=500, detail=_safe_error(e))
