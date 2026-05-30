"""S5 Brand VLOG Pipeline — material-driven VLOG narrative video generation.

Input: brand_id + product_sku(含六视图) + scene + models + story + duration
Output: full VLOG video via LLM storyboarding → Happy Horse clips → Remotion assembly
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

import src.skills.elevenlabs_tts  # noqa: F401
import src.skills.media_quality_audit  # noqa: F401
import src.skills.remotion_assemble  # noqa: F401

# Import-time skill auto-registration
import src.skills.seedance_prompt  # noqa: F401
import src.skills.seedance_video_generate  # noqa: F401
from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.continuity_utils import (
    all_clips_are_stubs,
    build_continuity_audit_summary,
    build_transitions_from_clip_details,
)
from src.skills.registry import SkillRegistry
from src.telemetry import generate_trace_id, pipeline_metrics

logger = structlog.get_logger()

VIDEO_MAX_DURATION = 15  # Happy Horse API limit

# Decision E (2026-05-13): S5 must NEVER produce identifiable children's
# faces or full-body shots. This block is appended to every clip prompt as
# a final defense-in-depth, in case upstream `vlog_strategy` /
# `seedance-video-prompt` skills strip or paraphrase the constraints.
S5_ABSTRACTION_GUARD = (
    "\n\n[Visual constraints (HARD enforcement, must obey):"
    " do NOT generate identifiable children's faces, full bodies, or clearly"
    " recognizable persons. If a child-related scene is required, only the"
    " following abstracted expressions are allowed: adult-hand product close-up,"
    " empty-environment shot (no people), product close-up, back-view /"
    " silhouette / side-view (no recognizable facial features). All shots"
    " containing people must remain abstracted, never producing a real face"
    " or any individually-identifiable likeness.]"
)

SCENE_MAP = {
    "office": {"name": "职场", "desc": "高效与通勤节奏"},
    "living-room": {"name": "客厅", "desc": "轻松陪伴和家庭氛围"},
    "bedroom": {"name": "卧室", "desc": "安静亲密睡前场景"},
    "outdoor": {"name": "户外", "desc": "日常出行与生活方式"},
    "kitchen": {"name": "厨房", "desc": "高效家务和台面操作"},
}


class S5BrandVlogPipeline:
    """品牌VLOG — 素材装配驱动的叙事视频生成管道 (auto mode)."""

    # ═══ StepRunner interface ═══

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single pipeline step (used by StepRunner)."""
        config = state["config"]
        reg = SkillRegistry()
        steps = state["steps"]
        errors = state["errors"]

        if step_name == "vlog_strategy":
            shots = await self._step_vlog_strategy(
                product_sku=config.get("product_sku", {}),
                models=config.get("selected_models", []),
                scene_id=config.get("scene_id", "living-room"),
                story=config.get("story_description", ""),
                duration=config.get("video_duration", 30),
                errors=errors,
            )
            scripts = self._vlog_shots_to_scripts(shots)
            return {"shots": shots, "scripts": scripts}

        if step_name == "continuity_storyboard_grid":
            strategy_out = self._get_step_output(steps, "vlog_strategy") or {}
            shots = strategy_out.get("shots", [])
            product_name = config.get("product_name", "Product")
            scene_id = config.get("scene_id", "living-room")
            scene_info = SCENE_MAP.get(scene_id, {"name": scene_id, "desc": ""})
            return self._vlog_shots_to_clip_groups(
                shots,
                product_name,
                scene_name=scene_info.get("name", scene_id),
                scene_desc=scene_info.get("desc", ""),
                story_description=config.get("story_description", ""),
                selected_models=config.get("selected_models", []),
            )

        if step_name == "video_prompts":
            strategy_out = self._get_step_output(steps, "vlog_strategy") or {}
            scripts = strategy_out.get("scripts", [])
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
            return await self._step_video_prompts(
                reg, scripts, config.get("product_name", "Product"), errors,
                continuity_storyboard_grid=continuity_grid,
            )

        if step_name == "seedance_clips":
            prompts = self._get_step_output(steps, "video_prompts") or []
            return await self._step_seedance_clips(
                reg, prompts, config.get("product_name", "Product"),
                config.get("output_label", "vlog"), errors,
                config.get("video_duration", 30), config.get("product_sku"),
            )

        if step_name == "tts_audio":
            strategy_out = self._get_step_output(steps, "vlog_strategy") or {}
            scripts = strategy_out.get("scripts", [])
            return await self._step_tts_audio(reg, scripts, errors)

        if step_name == "assemble_final":
            strategy_out = self._get_step_output(steps, "vlog_strategy") or {}
            scripts = strategy_out.get("scripts", [])
            tts_out = self._get_step_output(steps, "tts_audio") or []
            audio_paths = tts_out if isinstance(tts_out, list) else []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            if not clip_paths or all_clips_are_stubs(clip_paths, clip_details):
                errors.append("all_seedance_clips_are_stubs; skipping assembly")
                return "", ""
            return await self._step_assemble_final(
                reg, [], scripts, audio_paths, [], clip_paths, clip_details, {},
                config.get("output_label", "vlog"), errors,
            )

        if step_name == "audit":
            assemble_out = self._get_step_output(steps, "assemble_final")
            final_video, _ = extract_assemble_paths(assemble_out)

            tts_out = self._get_step_output(steps, "tts_audio") or []
            audio_paths = tts_out if isinstance(tts_out, list) else []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}

            if not clip_paths or all_clips_are_stubs(clip_paths, clip_details):
                errors.append("all_seedance_clips_are_stubs; skipping audit")
                return {}

            return await self._step_audit(
                reg, final_video, audio_paths, [], clip_paths, clip_details,
                errors, continuity_grid=continuity_grid,
            )

        raise ValueError(f"Unknown step name: {step_name}")

    @staticmethod
    def _get_step_output(steps: dict[str, Any], step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited."""
        step_data = steps.get(step_name, {})
        if step_data.get("edited") and step_data.get("edited_output") is not None:
            return step_data["edited_output"]
        return step_data.get("output")

    # ═══ Backwards-compatible full pipeline ═══

    async def run(
        self,
        brand_id: str = "momcozy",
        product_sku: dict[str, Any] | None = None,
        scene_id: str = "living-room",
        selected_models: list[dict[str, Any]] | None = None,
        story_description: str = "",
        video_duration: int = 30,
    ) -> dict[str, Any]:
        """Run the full S5 pipeline end-to-end.

        Backwards-compatible: uses StepRunner internally but returns the same
        result dict shape as before.
        """
        product_sku = product_sku or {}
        selected_models = selected_models or []
        product_name = product_sku.get("name", product_sku.get("shortName", "Product"))
        trace_id = generate_trace_id()
        label = f"vlog_{int(time.time())}"

        logger.info("s5_vlog: starting", trace_id=trace_id, product=product_name, duration=video_duration)

        if video_duration > VIDEO_MAX_DURATION:
            logger.warning(
                "s5_vlog: requested duration exceeds per-clip API limit",
                requested=video_duration,
                api_limit=VIDEO_MAX_DURATION,
                note="Video will be split into multiple clips",
            )

        config = {
            "brand_id": brand_id,
            "product_sku": product_sku,
            "scene_id": scene_id,
            "selected_models": selected_models,
            "story_description": story_description,
            "video_duration": video_duration,
            "product_name": product_name,
            "output_label": label,
        }

        from src.pipeline.state_manager import PipelineStateManager
        from src.pipeline.step_runner import StepRunner

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(config=config, mode="auto", label=label, scenario="s5")

        start = time.perf_counter()
        try:
            final_state = await runner.resume(label)
        except Exception as e:
            logger.error("s5_vlog: pipeline failed", error=str(e), trace_id=trace_id)
            return {"success": False, "errors": [str(e)], "scripts": []}

        duration_ms = (time.perf_counter() - start) * 1000
        steps = final_state.get("steps", {})
        errors = final_state.get("errors", [])

        strategy_out = self._get_step_output(steps, "vlog_strategy") or {}
        scripts = strategy_out.get("scripts", [])
        video_prompts = self._get_step_output(steps, "video_prompts") or []
        seedance_out = self._get_step_output(steps, "seedance_clips") or {}
        clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
        audio_paths = self._get_step_output(steps, "tts_audio") or []
        assemble_out = self._get_step_output(steps, "assemble_final")
        final_video, render_json_path = extract_assemble_paths(assemble_out)
        audit_report = self._get_step_output(steps, "audit") or {}

        pipeline_metrics.record_pipeline(
            label=label, scenario="brand_vlog",
            total_duration_ms=duration_ms, success=len(errors) == 0,
            error_count=len(errors),
        )

        return {
            "success": len(errors) == 0 and bool(final_video),
            "label": label,
            "scenario": "brand_vlog",
            "trace_id": trace_id,
            "briefs": [],
            "scripts": scripts,
            "storyboards": [],
            "video_prompts": video_prompts,
            "seedance_output": seedance_out,
            "clip_paths": clip_paths,
            "audio_paths": audio_paths if isinstance(audio_paths, list) else [],
            "final_video_path": final_video,
            "render_json_path": render_json_path,
            "thumbnail_sets": [],
            "thumbnail_image_paths": [],
            "audit_report": audit_report,
            "errors": errors,
            "steps_completed": 6,
        }

    # ═══ Step ①: VLOG Strategy (LLM) ═══

    async def _step_vlog_strategy(
        self, product_sku: dict[str, Any], models: list[dict[str, Any]],
        scene_id: str, story: str, duration: int, errors: list[str],
    ) -> list[dict[str, Any]]:
        """Generate VLOG shot list via DeepSeek-V4-Pro.

        Uses 120s timeout (vs default 60s) because VLOG strategy prompts
        are longer and DeepSeek-V4-Pro reasoning can take 60-90s.
        """
        from src.tools.llm_client import LLMClient

        llm = LLMClient(timeout=120.0)

        views = product_sku.get("views", []) if isinstance(product_sku, dict) else []
        views_text = "\n".join(
            f"- {v.get('label', '?')} ({v.get('title', '?')}): {v.get('usage_note', '')}"
            for v in views if isinstance(v, dict)
        ) if views else "(no view data)"

        normalized_models: list[dict[str, Any]] = []
        for m in models:
            if isinstance(m, dict):
                normalized_models.append(m)
            elif isinstance(m, str):
                normalized_models.append({"name": m, "role": "", "description": ""})
        models_text = "\n".join(
            f"- {m.get('name', '?')} (角色: {m.get('role', '?')}): {m.get('description', '')}"
            for m in normalized_models
        ) if normalized_models else "(no models)"

        scene_info = SCENE_MAP.get(scene_id, {"name": scene_id, "desc": ""})
        scene_context = f"{scene_info['name']} — {scene_info['desc']}"
        tags = ", ".join(product_sku.get("tags", []) if isinstance(product_sku, dict) else [])

        system_prompt = (
            "你是母婴品牌的创意导演，擅长将产品素材转化为 VLOG 叙事分镜。"
            "输出严格的 JSON 数组，不要任何解释文字。"
        )

        if isinstance(product_sku, dict):
            sku_name = product_sku.get('name', 'Product')
            sku_short = product_sku.get('shortName', '')
        elif isinstance(product_sku, str) and product_sku.strip():
            sku_name = product_sku.strip()
            sku_short = ''
        else:
            sku_name = 'Product'
            sku_short = ''

        user_prompt = f"""请生成一个 {duration} 秒的 VLOG 视频分镜脚本。

产品: {sku_name} ({sku_short})
产品标签: {tags or '母婴产品'}
可用产品角度:
{views_text}

拍摄场景: {scene_context}
出镜人物:
{models_text}

故事方向: {story or '突出产品核心卖点，以真实家庭互动串联完整情绪起承转合'}

请输出 JSON 数组，每个镜头包含以下字段:
- "shot_type": close-up | mid-shot | over-shoulder | static beauty
- "duration_seconds": 镜头秒数 (总和为 {duration}s)
- "visual_description": 画面描述 (引用产品角度名，描述具体动作和人物情绪)
- "voiceover": 旁白文案 (自然口语，温柔语气，每镜头10-25字)
- "product_angle": 使用的产品角度 label (如 "主视图")
- "model_in_shot": 出镜人物名 (可空字符串)

叙事节奏:
- 前 20% 时长: 产品六视图建立认知
- 中 60% 时长: 人物使用产品的生活场景
- 后 20% 时长: 品牌收尾 + CTA

重要视觉约束（硬性执行）:
- 禁止生成任何可识别儿童面部、全身或清晰人物形象
- 如需要表现儿童相关场景，仅允许使用以下抽象化表达：成人手部操作特写、空镜环境（无人物）、产品特写、背影/剪影/侧影（无面部特征可辨识）
- 所有含人物的画面必须保持抽象化，避免生成真实人脸或可被识别为特定个体的形象

只输出 JSON 数组，不要任何 markdown 或解释。"""

        try:
            result = await llm.invoke_json(system_prompt, user_prompt)
            if isinstance(result, list) and len(result) > 0:
                logger.info("s5_vlog: strategy generated", shots=len(result))
                return result
            else:
                errors.append(f"vlog_strategy: unexpected LLM output type: {type(result).__name__}")
        except Exception as e:
            logger.error("s5_vlog: strategy LLM failed", error=str(e))
            errors.append(f"vlog_strategy_llm_failed: {e}")

        return self._build_fallback_shots(product_sku, duration)

    def _build_fallback_shots(self, product_sku: Any, duration: int) -> list[dict[str, Any]]:
        """Fallback shot list with structured narrative — not generic rotation."""
        if not isinstance(product_sku, dict):
            product_sku = {"name": str(product_sku).strip()} if isinstance(product_sku, str) and product_sku.strip() else {}
        name = product_sku.get("name", "Product")
        short = product_sku.get("shortName", name)
        views = product_sku.get("views", [])
        view1 = views[0]["label"] if len(views) > 0 else "主视图"
        view2 = views[1]["label"] if len(views) > 1 else "45度视图"
        view_last = views[5]["label"] if len(views) > 5 else (view2 if len(views) > 1 else view1)
        models = product_sku.get("_models_text", "")
        hook_dur = max(3, duration * 0.2)
        body_dur = max(8, duration * 0.55)
        cta_dur = max(3, duration * 0.25)
        return [
            {"shot_type": "close-up", "duration_seconds": hook_dur,
             "visual_description": f"{short} {view1}特写，正面展示产品形态与设计细节，自然光下材质质感清晰，品牌标识突出",
             "voiceover": f"每天陪伴妈妈们的 {short}，今天让我们一起走近它。",
             "product_angle": view1, "model_in_shot": ""},
            {"shot_type": "over-shoulder", "duration_seconds": body_dur,
             "visual_description": f"从{view2}角度展示 {short} 在真实生活场景中的使用过程，镜头跟随手部动作平稳移动，捕捉产品的便捷操作瞬间",
             "voiceover": "无需繁琐准备，轻轻一按即可开始。每一个细节，都为忙碌的妈妈考虑。",
             "product_angle": view2, "model_in_shot": ""},
            {"shot_type": "static beauty", "duration_seconds": cta_dur,
             "visual_description": f"{short} {view_last}完整展示，浅景深干净背景，产品居中摆放，营造高级品牌定妆感，为视频画上圆满句号",
             "voiceover": f"{short}，为妈妈的舒适不断进化。",
             "product_angle": view_last, "model_in_shot": ""},
        ]

    # ═══ Step ②: Shots → Scripts Adapter ═══

    def _vlog_shots_to_scripts(self, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert VLOG shot JSON to scripts format consumable by video_prompts step."""
        if not shots:
            return []
        segments = []
        current_time = 0.0
        for i, shot in enumerate(shots):
            dur = max(1.0, float(shot.get("duration_seconds", 5.0)))
            segments.append({
                "segment_type": "hook" if i == 0 else ("cta" if i == len(shots) - 1 else "body"),
                "start_time": current_time,
                "end_time": current_time + dur,
                "visual_description": shot.get("visual_description", ""),
                "voiceover": shot.get("voiceover", ""),
                "text_overlay": "",
                "product_angle": shot.get("product_angle", ""),
            })
            current_time += dur
        return [{
            "id": "vlog-script-001",
            "brief_id": "VLOG-001",
            "platform": "tiktok",
            "language": "zh",
            "total_duration": current_time,
            "segments": segments,
            "product_name": "",
        }]

    # ═══ Steps ③-⑦: Reused from S1 pattern ═══

    @staticmethod
    def _vlog_shots_to_clip_groups(
        shots: list[dict[str, Any]],
        product_name: str,
        scene_name: str = "",
        scene_desc: str = "",
        story_description: str = "",
        selected_models: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Convert vlog strategy shots to continuity clip_groups."""
        groups: list[dict[str, Any]] = []
        selected_models = selected_models or []
        persona_parts = []
        for model in selected_models:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name", "")).strip()
            role = str(model.get("role", "")).strip()
            description = str(model.get("description", "")).strip()
            fragments = [part for part in (name, role, description) if part]
            if fragments:
                persona_parts.append(" | ".join(fragments))
        persona_summary = "; ".join(persona_parts[:2])

        group_size = 3
        for idx in range(0, len(shots), group_size):
            chunk = shots[idx:idx + group_size]
            group_idx = len(groups) + 1
            shot_indices = list(range(idx + 1, idx + len(chunk) + 1))
            scene_beat = S5BrandVlogPipeline._scene_beat_for_group(group_idx - 1)
            beat_summary = S5BrandVlogPipeline._summarize_vlog_group(chunk)
            transition_intent = S5BrandVlogPipeline._transition_intent_for_group(
                group_idx=group_idx - 1,
                scene_beat=scene_beat,
            )
            prompt_parts = []
            for shot in chunk:
                visual = (shot.get("visual", "") or shot.get("description", "")).strip()
                shot_type = str(shot.get("shot_type", "")).strip()
                product_angle = str(shot.get("product_angle", "")).strip()
                model_name = str(shot.get("model_in_shot", "")).strip()
                fragments = [part for part in (shot_type, product_angle, model_name, visual[:80]) if part]
                if fragments:
                    prompt_parts.append(" | ".join(fragments))
            group = {
                "clip_index": group_idx,
                "shot_indices": shot_indices,
                "duration": sum(s.get("duration_seconds", 5) for s in chunk) or 5.0,
                "purpose": f"group_{group_idx}",
                "scene_beat": scene_beat,
                "beat_summary": beat_summary,
                "transition_intent": transition_intent,
                "seedance_prompt": (
                    f"{product_name} brand vlog scene in {scene_name or 'lifestyle setting'}"
                    f"{f' ({scene_desc})' if scene_desc else ''}: {'; '.join(prompt_parts)}. "
                    f"{f'Story arc: {story_description}. ' if story_description else ''}"
                    f"{f'On-camera persona: {persona_summary}. ' if persona_summary else ''}"
                    f"Narrative beat: {scene_beat}. "
                    f"Beat summary: {beat_summary}. "
                    f"Transition intent: {transition_intent}. "
                    "Warm natural lighting, lifestyle aesthetic, consistent product framing."
                ),
                "transition_type": "soft_crossfade",
            }
            if idx + group_size < len(shots):
                group["transition_to_next"] = "soft crossfade to next scene"
            groups.append(group)
        return {
            "grid_type": "vlog-shots",
            "product_name": product_name,
            "visual_identity": {
                "location": scene_name or "",
                "scene_desc": scene_desc,
                "story_arc": story_description,
                "persona": persona_summary,
            },
            "micro_shots": [],
            "clip_groups": groups,
        }

    @staticmethod
    def _scene_beat_for_group(group_idx: int) -> str:
        beats = [
            "vlog_intro",
            "lifestyle_demo",
            "emotional_payoff",
            "cta_close",
        ]
        return beats[group_idx] if group_idx < len(beats) else "vlog_progression"

    @staticmethod
    def _summarize_vlog_group(chunk: list[dict[str, Any]]) -> str:
        fragments: list[str] = []
        for shot in chunk:
            shot_type = str(shot.get("shot_type", "")).strip()
            product_angle = str(shot.get("product_angle", "")).strip()
            model_name = str(shot.get("model_in_shot", "")).strip()
            summary_bits = [part for part in (shot_type, product_angle, model_name) if part]
            if summary_bits:
                fragments.append(" / ".join(summary_bits))
        return " -> ".join(fragments) if fragments else "vlog continuity progression"

    @staticmethod
    def _transition_intent_for_group(*, group_idx: int, scene_beat: str) -> str:
        intents = [
            "bridge the opening product introduction into lived-in usage",
            "carry lifestyle usage into a warmer emotional payoff",
            "resolve the emotional payoff into a calm brand close",
            "hold the final vlog memory and CTA without visual reset",
        ]
        if group_idx < len(intents):
            return intents[group_idx]
        return f"preserve {scene_beat} continuity through the next vlog beat"

    async def _step_video_prompts(self, reg, scripts, product_name, errors, continuity_storyboard_grid: dict[str, Any] | None = None):
        """Generate per-segment structured video prompts (narrative_shot architecture)."""
        # Priority: continuity_grid clip_groups > segment-based fallback
        if continuity_storyboard_grid and continuity_storyboard_grid.get("clip_groups"):
            result = await reg.execute("seedance-video-prompt", {
                "continuity_storyboard_grid": continuity_storyboard_grid,
                "product_name": product_name,
            })
            if result.success and result.data and isinstance(result.data, list):
                return result.data
            logger.warning("s5: continuity video_prompts failed, falling back", error=result.error)

        all_prompts = []
        for script in scripts[:3]:
            segments = script.get("segments", [])
            if not segments:
                continue
            res = await reg.execute("seedance-video-prompt", {
                "script_segments": [
                    {
                        "segment_type": s.get("segment_type", "body"),
                        "visual_description": s.get("visual_description", ""),
                        "voiceover": s.get("voiceover", ""),
                        "start_time": float(s.get("start_time", 0)),
                        "end_time": float(s.get("end_time", 5)),
                    }
                    for s in segments
                ],
                "product_name": script.get("product_name", product_name),
            })
            if res.success and res.data and isinstance(res.data, list):
                for p in res.data:
                    p["script_id"] = script.get("id", "")
                all_prompts.extend(res.data)
            else:
                errors.append(f"video_prompts_failed: {res.error}")
        return all_prompts

    async def _step_seedance_clips(
        self, reg, video_prompts, product_name, label, errors, video_duration,
        product_sku: dict[str, Any] | None = None,
    ):
        """Generate video clips per segment via Seedance 2 (multi-clip).

        Sprint 1 P1-4: routes through ModelRouter (scenario="s5") and
        delegates last-frame extraction to VideoContinuityManagerSkill
        for visual continuity across the N×15s clip sequence that yields
        S5's 30-90s VLOG durations.

        Continuity priority per segment:
            1. keyframe_image_path (product view, if product_angle matches)
            2. continuity_frame_path (last frame of previous clip)
            3. (text-to-video fallback)
        """

        from src.config import OUTPUT_DIR
        from src.pipeline.model_router import select_model

        s5_model = select_model("s5")
        clip_paths = []
        clip_details = []
        per_clip = min(VIDEO_MAX_DURATION, video_duration)
        last_frame: str | None = None

        # P3: Build keyframe image mapping from product views
        keyframe_map: dict[str, str] = {}
        if product_sku:
            for view in product_sku.get("views", []):
                label_text = view.get("label", "")
                image_path = view.get("imagePath") or view.get("image_path") or view.get("path", "")
                if label_text and image_path:
                    keyframe_map[label_text] = image_path
            if keyframe_map:
                logger.info("s5_vlog: keyframe map built", angles=list(keyframe_map.keys()))

        # P0-1: 检测是否所有 clips 都有 keyframe 覆盖
        _all_have_keyframe = all(
            keyframe_map.get(vp.get("product_angle", ""), "")
            for vp in video_prompts[:5]
        )

        if _all_have_keyframe:
            # ── 并发模式：所有 clip 独立生成（keyframe 已覆盖，无需 last-frame 链）──
            _seedance_sem = asyncio.Semaphore(4)

            async def _gen_one_s5(i: int, vp: dict[str, Any]) -> tuple[int, Any]:
                async with _seedance_sem:
                    prompt_text = vp.get("segment_prompt", "") or vp.get("prompt", "")
                    if isinstance(prompt_text, dict):
                        prompt_text = prompt_text.get("segment_prompt", "") or str(prompt_text)
                    if not prompt_text:
                        prompt_text = f"{product_name} in natural usage scene"

                    seg_dur = float(vp.get("duration_seconds", per_clip))
                    seg_dur = max(4, min(seg_dur, VIDEO_MAX_DURATION))

                    final_prompt = str(prompt_text) + S5_ABSTRACTION_GUARD

                    gen_params: dict[str, Any] = {
                        "prompt": final_prompt,
                        "duration": int(seg_dur),
                        "resolution": "720p",
                        "output_label": f"{label}_seg_{i}",
                        "model": s5_model,
                    }

                    product_angle = vp.get("product_angle", "")
                    kf_path = keyframe_map.get(product_angle, "") if product_angle else ""
                    if kf_path:
                        gen_params["keyframe_image_path"] = kf_path
                        logger.info("s5_vlog: keyframe anchored", seg=i, angle=product_angle)

                    res = await reg.execute("seedance-video-generate-skill", gen_params)
                    return i, res

            tasks = [_gen_one_s5(i, vp) for i, vp in enumerate(video_prompts[:5])]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            for raw in raw_results:
                if isinstance(raw, Exception):
                    errors.append(f"clip_failed_with_exception: {raw}")
                    continue
                i, res = raw
                if res.success and res.data:
                    path = res.data.get("video_path", "")
                    if path:
                        clip_paths.append(path)
                        vp = video_prompts[i]
                        product_angle = vp.get("product_angle", "")
                        kf_path = keyframe_map.get(product_angle, "") if product_angle else ""
                        clip_details.append({
                            "path": path,
                            "duration": res.data.get("duration_seconds", 0),
                            "is_stub": res.data.get("is_stub", False),
                            "file_size": res.data.get("file_size_bytes", 0),
                            "verification": res.data.get("verification", {}),
                            "segment_type": vp.get("segment_type", "body"),
                            "shot_type": vp.get("shot_type", ""),
                            "product_angle": product_angle,
                            "keyframe_used": bool(kf_path),
                            "model": s5_model,
                            "transition_to_next": vp.get("transition_to_next", ""),
                            "transition_type": vp.get("transition_type", "clean"),
                            "scene_beat": vp.get("scene_beat", ""),
                            "beat_summary": vp.get("beat_summary", ""),
                            "transition_intent": vp.get("transition_intent", ""),
                            "clip_index": vp.get("clip_index", i + 1),
                        })
                else:
                    errors.append(f"clip_{i}_failed: {res.error}")

        else:
            # ── 串行 fallback：保留 last-frame 链 ──
            for i, vp in enumerate(video_prompts[:5]):
                prompt_text = vp.get("segment_prompt", "") or vp.get("prompt", "")
                if isinstance(prompt_text, dict):
                    prompt_text = prompt_text.get("segment_prompt", "") or str(prompt_text)
                if not prompt_text:
                    prompt_text = f"{product_name} in natural usage scene"

                seg_dur = float(vp.get("duration_seconds", per_clip))
                seg_dur = max(4, min(seg_dur, VIDEO_MAX_DURATION))

                final_prompt = str(prompt_text) + S5_ABSTRACTION_GUARD

                gen_params: dict[str, Any] = {
                    "prompt": final_prompt,
                    "duration": int(seg_dur),
                    "resolution": "720p",
                    "output_label": f"{label}_seg_{i}",
                    "model": s5_model,
                }

                # P3: Keyframe anchoring — use product view image if available
                product_angle = vp.get("product_angle", "")
                kf_path = keyframe_map.get(product_angle, "") if product_angle else ""
                if kf_path:
                    gen_params["keyframe_image_path"] = kf_path
                    logger.info("s5_vlog: keyframe anchored", seg=i, angle=product_angle)
                elif last_frame:
                    gen_params["continuity_frame_path"] = last_frame

                res = await reg.execute("seedance-video-generate-skill", gen_params)
                if res.success and res.data:
                    path = res.data.get("video_path", "")
                    if path:
                        clip_paths.append(path)
                        clip_details.append({
                            "path": path,
                            "duration": res.data.get("duration_seconds", 0),
                            "is_stub": res.data.get("is_stub", False),
                            "file_size": res.data.get("file_size_bytes", 0),
                            "verification": res.data.get("verification", {}),
                            "segment_type": vp.get("segment_type", "body"),
                            "shot_type": vp.get("shot_type", ""),
                            "product_angle": product_angle,
                            "keyframe_used": bool(kf_path),
                            "model": s5_model,
                            "transition_to_next": vp.get("transition_to_next", ""),
                            "transition_type": vp.get("transition_type", "clean"),
                            "scene_beat": vp.get("scene_beat", ""),
                            "beat_summary": vp.get("beat_summary", ""),
                            "transition_intent": vp.get("transition_intent", ""),
                            "clip_index": vp.get("clip_index", i + 1),
                        })
                        # P1-4: delegate last-frame extraction to skill for
                        # consistent async handling + fallback semantics.
                        cm_params = {
                            "video_path": path,
                            "output_dir": str(OUTPUT_DIR / "seedance" / "continuity_frames"),
                        }
                        cm_res = await reg.execute("video-continuity-manager-skill", cm_params)
                        if cm_res.success and cm_res.data:
                            last_frame = cm_res.data.get("continuity_frame_path")
                        else:
                            last_frame = None
                else:
                    errors.append(f"clip_{i}_failed: {res.error}")
                    last_frame = None

        all_stubs = bool(clip_paths) and all_clips_are_stubs(clip_paths, clip_details)
        return {
            "clip_paths": clip_paths,
            "clip_details": clip_details,
            "total_duration": sum(d.get("duration", 0) for d in clip_details),
            "model": s5_model,
            "_all_stubs": all_stubs,
        }

    async def _step_tts_audio(self, reg, scripts, errors):
        """Generate TTS audio via CosyVoice (REUSE)."""
        voiceover_texts = []
        for script in scripts:
            for seg in script.get("segments", []):
                text = seg.get("voiceover", "")
                if text.strip():
                    voiceover_texts.append(text.strip())
        if not voiceover_texts:
            return []

        full_text = "。".join(voiceover_texts)
        res = await reg.execute("elevenlabs-tts-skill", {
            "text": full_text,
            "language": "zh",
            "output_label": "vlog_tts",
        })
        if res.success and res.data:
            paths = res.data.get("audio_paths", [])
            if isinstance(paths, list):
                return paths
            return [paths] if paths else []
        errors.append(f"tts_failed: {res.error}")
        return []

    async def _step_assemble_final(self, reg, storyboards, scripts, audio_paths, lyrics_paths, clip_paths, clip_details, brand_guidelines, label, errors):
        """Assemble final video via Remotion (REUSE)."""
        shots = []
        for script in scripts:
            for seg in script.get("segments", []):
                shots.append({
                    "id": len(shots),
                    "start_time": seg.get("start_time", 0),
                    "end_time": seg.get("end_time", 5),
                    "visual": seg.get("visual_description", ""),
                    "text_overlay": seg.get("text_overlay", ""),
                    "asset_needed": "",
                })
        captions = []
        for script in scripts:
            for seg in script.get("segments", []):
                captions.append({
                    "index": len(captions),
                    "start_time": seg.get("start_time", 0),
                    "end_time": seg.get("end_time", 5),
                    "text": seg.get("voiceover", ""),
                    "style": "default",
                    "position": "bottom",
                })
        total_dur = max((s.get("end_time", 30) for s in shots), default=30.0)

        transitions = build_transitions_from_clip_details(clip_details or [])

        res = await reg.execute("remotion-assemble-skill", {
            "shots": shots, "captions": captions,
            "audio_paths": audio_paths, "lyrics_paths": lyrics_paths,
            "clip_paths": clip_paths, "brand_guidelines": brand_guidelines,
            "output_label": label, "total_duration": total_dur,
            "transitions": transitions,
        })
        if res.success and res.data:
            return res.data.get("video_path", ""), res.data.get("render_json_path", "")
        errors.append(f"assemble_failed: {res.error}")
        return "", ""

    async def _step_audit(
        self, reg, video_path, audio_paths, thumbnail_paths, clip_paths,
        clip_details, errors, continuity_grid: dict[str, Any] | None = None,
    ):
        """Quality audit (REUSE)."""
        res = await reg.execute("media-quality-audit-skill", {
            "video_path": video_path,
            "audio_paths": audio_paths,
            "thumbnail_paths": thumbnail_paths,
            "clip_paths": clip_paths,
        })
        if res.success and res.data:
            base_audit = res.data if isinstance(res.data, dict) else {}
            return build_continuity_audit_summary(
                base_audit=base_audit,
                clip_details=clip_details or [],
                continuity_grid=continuity_grid,
                final_video_path=video_path or "",
            )
        errors.append(f"audit_failed: {res.error}")
        return {}
