"""scenario router — extracted from api.py (P1-11)."""

from fastapi import APIRouter, HTTPException, Depends

try:
    from src.storage import HAS_STORAGE
except ImportError:
    HAS_STORAGE = False

from src.routers._deps import _safe_error, verify_api_key
from src.routers._state import (
    _SCENARIO_STEP_ORDER,
    _validate_scenario,
    _get_step_deps,
    _get_step_output,
    _register_background_task,
    _background_tasks,
    FastModeRequest,
)


router = APIRouter()

@router.post("/scenario/s1", dependencies=[Depends(verify_api_key)])
async def run_s1_product_direct(body: dict):
    """Run S1 Product Direct pipeline (auto mode via StepRunner for progress visibility).

    Uses StepRunner.init_state() + StepRunner.resume() directly so that
    pipeline state is saved after each step, enabling real-time progress
    monitoring by StageProgress polling.

    Phase 2+3: Translates Chinese product inputs to English before
    pipeline execution and forces target_languages to ``["en"]``.
    Original Chinese values are stored in ``_original_zh`` within
    the product_catalog so the frontend can display them.
    """
    from src.tools.translate import translate_catalog_to_english
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

    product_catalog = body.get("product_catalog", {})
    product_catalog = await translate_catalog_to_english(product_catalog)

    config = {
        "product_catalog": product_catalog,
        "brand_guidelines": body.get("brand_guidelines"),
        "target_platforms": body.get("target_platforms", ["tiktok", "shopify"]),
        "target_languages": ["en"],
        "week": body.get("week", ""),
        "video_duration": body.get("video_duration", 30),
        "brand_mode": body.get("brand_mode", False),
        "enable_media_synthesis": body.get("enable_media_synthesis", True),
    }

    state_manager = PipelineStateManager()
    step_runner = StepRunner(state_manager)

    # Initialize state (saved immediately so polling can see it) and run to completion
    label = await step_runner.init_state(config=config, mode="auto")
    try:
        final_state = await step_runner.resume(label)
    except TypeError as te:
        # structlog kwarg compatibility — fall back to legacy pipeline
        import logging as _log
        _log.warning("auto pipeline: StepRunner resume failed (structlog), falling back to S1ProductDirectPipeline: %s", te)
        from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
        p = S1ProductDirectPipeline()
        final_state = await p.run(
            product_catalog=product_catalog,
            brand_guidelines=body.get("brand_guidelines"),
            target_platforms=body.get("target_platforms", ["tiktok", "shopify"]),
            target_languages=["en"],
            week=body.get("week", ""),
            brand_mode=body.get("brand_mode", False),
            enable_media_synthesis=body.get("enable_media_synthesis", True),
            video_duration=body.get("video_duration", 30),
        )
        # S1ProductDirectPipeline returns a dict differently — extract steps from the state
        return final_state

    # Convert back to the result dict format expected by frontend
    steps = final_state.get("steps", {})
    seedance_raw = _get_step_output(steps, "seedance_clips") or {}
    seedance_output = seedance_raw if isinstance(seedance_raw, dict) else {}
    clip_paths = seedance_output.get("clip_paths", []) if isinstance(seedance_raw, dict) else (seedance_raw if isinstance(seedance_raw, list) else [])

    tts_raw = _get_step_output(steps, "tts_audio") or {}
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
        "errors": final_state.get("errors", []),
        "media_synthesis_errors": final_state.get("media_synthesis_errors", []),
        "briefs": _get_step_output(steps, "strategy") or [],
        "scripts": _get_step_output(steps, "scripts") or [],
        "storyboards": _get_step_output(steps, "storyboards") or [],
        "keyframe_images": _get_step_output(steps, "keyframe_images") or [],
        "video_prompts": _get_step_output(steps, "video_prompts") or [],
        "thumbnail_sets": _get_step_output(steps, "thumbnail_prompts") or [],
        "seedance_output": seedance_output,
        "clip_paths": clip_paths,
        "audio_paths": audio_paths,
        "lyrics_paths": lyrics_paths,
        "thumbnail_image_paths": _get_step_output(steps, "thumbnail_images") or [],
        "steps_completed": len(_SCENARIO_STEP_ORDER.get("s1", [])),
    }

    # Extract assemble_final output (may be tuple or dict)
    assemble = _get_step_output(steps, "assemble_final")
    if isinstance(assemble, tuple):
        result["final_video_path"] = assemble[0] if len(assemble) > 0 else ""
        result["render_json_path"] = assemble[1] if len(assemble) > 1 else ""
    elif isinstance(assemble, dict):
        result["final_video_path"] = assemble.get("video_path", "")
        result["render_json_path"] = assemble.get("render_json_path", "")
    else:
        result["final_video_path"] = ""
        result["render_json_path"] = ""

    result["audit_report"] = _get_step_output(steps, "audit") or {}
    return result


@router.post("/scenario/s2", dependencies=[Depends(verify_api_key)])
async def run_s2_brand_campaign(body: dict):
    """Run S2 Brand Campaign pipeline."""
    from src.pipeline.s2_brand_pipeline import S2BrandCampaignPipeline
    p = S2BrandCampaignPipeline()
    r = await p.run(
        brand_package=body.get("brand_package", {}),
        target_platforms=body.get("target_platforms", ["tiktok", "shopify"]),
        target_languages=body.get("target_languages", ["en"]),
        week=body.get("week", ""),
    )
    return r


@router.post("/scenario/s3", dependencies=[Depends(verify_api_key)])
async def run_s3_influencer_remix(body: dict):
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
    from src.tools.translate import translate_catalog_to_english
    from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline

    product = body.get("product", {})
    if isinstance(product, dict):
        product = await translate_catalog_to_english(product)
        body["product"] = product

    p = S3InfluencerRemixPipeline()
    r = await p.run(
        video_url=body.get("video_url", ""),
        product=product,
        influencer_name=body.get("influencer_name", "Influencer"),
        brief_id=body.get("brief_id", ""),
        video_duration=body.get("video_duration", 30),
    )
    return r.to_dict()


@router.post("/scenario/s4", dependencies=[Depends(verify_api_key)])
async def run_s4_live_shoot(body: dict):
    """Run S4 Live Shoot to Video pipeline."""
    from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
    p = S4LiveShootPipeline()
    r = await p.run(
        footage_assets=body.get("footage_assets", []),
        product_info=body.get("product_info", {}),
        topic=body.get("topic", ""),
        target_platforms=body.get("target_platforms", ["tiktok"]),
    )
    return r


@router.post("/scenario/s5", dependencies=[Depends(verify_api_key)])
async def run_s5_brand_vlog(body: dict):
    """Run S5 Brand VLOG pipeline.

    Request body:
        brand_id: str — brand identifier (e.g. "momcozy")
        product_sku: dict — product SKU with views[] (six-view angles)
        scene_id: str — scene identifier (office/living-room/bedroom/nursery/outdoor/kitchen)
        selected_models: list[dict] — model profiles with name/role/description
        story_description: str — user's story direction (max 300 chars)
        video_duration: int — target video seconds (15/30/45/60/90)
    """
    from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
    p = S5BrandVlogPipeline()
    r = await p.run(
        brand_id=body.get("brand_id", "momcozy"),
        product_sku=body.get("product_sku", {}),
        scene_id=body.get("scene_id", "living-room"),
        selected_models=body.get("selected_models", []),
        story_description=body.get("story_description", ""),
        video_duration=body.get("video_duration", 30),
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
    from src.services.fast_mode import get_fast_mode_service

    service = get_fast_mode_service()
    try:
        result = await service.generate(
            user_prompt=req.user_prompt,
            duration=max(10, min(15, req.duration)),
            enable_tts=req.enable_tts,
        )
        return result
    except Exception as e:
        logger.error("fast_mode failed", error=str(e))
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/start", dependencies=[Depends(verify_api_key)])
async def start_s1_pipeline(body: dict):
    """Start a new S1 pipeline run in either "auto" or "step_by_step" mode.

    Request body:
        product_catalog: dict
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
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

    try:
        step_runner = StepRunner(PipelineStateManager())
        mode = body.get("mode", "auto")
        label = await step_runner.init_state(config=body, mode=mode)

        if mode == "auto":
            result = await step_runner.resume(label)
            return result

        return {
            "label": label,
            "mode": mode,
            "status": "initialized",
            "current_step": None,
        }
    except Exception as e:
        import logging
        logging.error("s1 pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/step/{step_name}", dependencies=[Depends(verify_api_key)])
async def run_s1_step(step_name: str, body: dict):
    """Execute a single step of the S1 pipeline.

    Args:
        step_name: One of the valid pipeline step names.
        body: dict with "label" key.

    Returns:
        Updated pipeline state dict after executing the step.
    """
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

    try:
        step_runner = StepRunner(PipelineStateManager())
        result = await step_runner.run_step(body["label"], step_name)
        return result
    except Exception as e:
        import logging
        logging.error("s1 step failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/regenerate", dependencies=[Depends(verify_api_key)])
async def regenerate_s1_step(body: dict):
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
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_editor import invalidate_downstream

    try:
        state_manager = PipelineStateManager()
        await invalidate_downstream(body["label"], body["step"], state_manager)
        step_runner = StepRunner(state_manager)
        result = await step_runner.regenerate_step(body["label"], body["step"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/s1/resume", dependencies=[Depends(verify_api_key)])
async def resume_s1_pipeline(body: dict):
    """Resume execution from current_step to completion.

    Request body:
        label: str — pipeline run label

    Returns:
        Final pipeline state dict.
    """
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

    try:
        step_runner = StepRunner(PipelineStateManager())
        result = await step_runner.resume(body["label"])
        return result
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
        return state
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("s1 resume failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.put("/scenario/s1/state/{label}", dependencies=[Depends(verify_api_key)])
async def update_s1_state(label: str, body: dict):
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

    def deep_merge(base: dict, updates: dict) -> dict:
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

        steps_data = state.get("steps", {})
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

            result.append({
                "step_name": step_name,
                "status": status,
                "preview": preview,
                "has_output": output is not None,
                "is_edited": sd.get("edited", False),
                "completed_at": sd.get("completed_at", ""),
            })

        return {
            "label": label,
            "scenario": scenario,
            "current_step": state.get("current_step"),
            "steps": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("list_steps failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/scenario/{scenario}/step/{step_name}", dependencies=[Depends(verify_api_key)])
async def execute_step(scenario: str, step_name: str, body: dict):
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

        steps_data = state.get("steps", {})
        deps = _get_step_deps(scenario, step_name)
        missing_deps: list[dict] = []
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

        # For S1, use StepRunner; other scenarios can be extended
        if scenario == "s1":
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

        raise HTTPException(status_code=501, detail=f"Step execution not implemented for scenario: {scenario}")

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error("execute_step failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.put("/scenario/{scenario}/state/{label}", dependencies=[Depends(verify_api_key)])
async def edit_step_output(scenario: str, label: str, body: dict):
    """Update the state for a step's output (allows user editing).

    Request body:
        step_name: str — the step to update
        updates: any — the updated step output data

    Returns:
        { label, updated_step, state }.
    """
    from src.pipeline.step_editor import update_step_output

    _validate_scenario(scenario)
    step_name = body.get("step_name", "").strip()
    updates = body.get("updates")
    if not step_name:
        raise HTTPException(status_code=400, detail="Missing required field: step_name")
    if updates is None:
        raise HTTPException(status_code=400, detail="Missing required field: updates")

    try:
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
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.step_editor import invalidate_downstream

    _validate_scenario(scenario)
    try:
        state_manager = PipelineStateManager()
        state = await state_manager.load(label)
        if state is None:
            raise HTTPException(status_code=404, detail=f"State not found for label: {label}")

        order = _SCENARIO_STEP_ORDER[scenario]
        try:
            step_idx = order.index(step_name)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown step: {step_name}")

        downstream = order[step_idx + 1:]

        # For S1, use StepRunner's regenerate_step
        if scenario == "s1":
            step_runner = StepRunner(state_manager)
            # invalidate_downstream marks steps as pending
            await invalidate_downstream(label, step_name, state_manager)
            # Then regenerate the specified step
            await step_runner.regenerate_step(label, step_name)
        else:
            raise HTTPException(status_code=501, detail=f"Regeneration not implemented for scenario: {scenario}")

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

    _validate_scenario(scenario)
    result = await _get_gate_state(label, gate_id)
    if "error" in result:
        from fastapi import HTTPException
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

    _validate_scenario(scenario)
    try:
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
async def approve_gate_decision(scenario: str, label: str, gate_id: str, body: dict):
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

    _validate_scenario(scenario)
    selected_ids = body.get("selected_ids", [])
    if not selected_ids or not isinstance(selected_ids, list):
        raise HTTPException(status_code=400, detail="Missing or invalid required field: selected_ids (list[str])")

    try:
        result = await _approve_gate(label, gate_id, selected_ids)
        if "error" in result:
            status_code = 400
            if "already approved" in result.get("error", ""):
                status_code = 409
            raise HTTPException(status_code=status_code, detail=result["error"])

        # Auto-resume pipeline after gate approval (step-by-step mode)
        # Resume runs from current_step until the next gate or completion.
        # Resume can take 5-30 minutes (keyframe generation + video synthesis).
        # Run in background to avoid HTTP 504 Gateway Timeout.
        async def _background_resume() -> None:
            import structlog

            log = structlog.get_logger()
            try:
                from src.pipeline.step_runner import StepRunner
                from src.pipeline.state_manager import PipelineStateManager

                step_runner = StepRunner(PipelineStateManager())
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

    _validate_scenario(scenario)
    try:
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


