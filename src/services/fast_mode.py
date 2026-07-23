"""Fast Mode Service — direct text-to-video generation without pipeline.

Used for testing the LLM + video generation matrix capability.
Completely independent from pipelines, scenarios, and LangGraph.

Flow:
  user_prompt → LLM enhancement → Seedance video → optional TTS → result
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

import structlog
from pydantic import ValidationError

from src.config import DEFAULT_LLM_PROVIDER, OUTPUT_DIR
from src.models.provider_cost import ProviderCostContractError
from src.models.runtime_contracts import FastModeModelInfo, FastModeResult, SeedanceVideoResult
from src.pipeline.generation_policy import (
    GENERATION_POLICY_VERSION,
    EffectiveGenerationPolicy,
    bind_effective_generation_policy,
    reset_effective_generation_policy,
)
from src.pipeline.model_router import select_model
from src.services.provider_execution import (
    bind_provider_operation_scope,
    build_provider_operation_instance,
    get_provider_operation_scope,
    reset_provider_operation_scope,
    resolve_provider_operation_scope,
)
from src.tools.cosyvoice_client import CosyVoiceClient, CosyVoiceSynthesisResult
from src.tools.llm_client import LLMClient, LLMNotConfiguredError
from src.tools.seedance_client import SeedanceClient

logger = structlog.get_logger()

FAST_MODE_OUTPUT_DIR = OUTPUT_DIR / "fast_mode"
FAST_MODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Module-level singleton instance — avoids rebuilding clients per request
_fast_mode_service_instance: FastModeService | None = None

FastModeArtifactDisposition = Literal["default", "pending_review", "quarantine"]


def _safe_path_segment(value: str | None, fallback: str) -> str:
    raw = (value or "").strip()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    cleaned = cleaned.strip("-_")
    return cleaned[:80] or fallback


def _artifact_output_dir(
    disposition: FastModeArtifactDisposition,
    *,
    tenant_id: str | None,
    run_id: str | None,
) -> Path:
    if disposition == "pending_review":
        tenant = _safe_path_segment(tenant_id, "default")
        run = _safe_path_segment(run_id, f"fast_mode_{int(time.time())}")
        return OUTPUT_DIR / "tenants" / tenant / "pending_review" / "fast_mode" / run
    if disposition == "quarantine":
        tenant = _safe_path_segment(tenant_id, "default")
        run = _safe_path_segment(run_id, f"fast_mode_{int(time.time())}")
        return OUTPUT_DIR / "tenants" / tenant / "quarantine" / "fast_mode" / run
    return FAST_MODE_OUTPUT_DIR


def _validate_fast_effective_policy(
    raw_policy: dict[str, Any] | None,
    *,
    tenant_id: str | None,
    artifact_disposition: FastModeArtifactDisposition,
    provider_max_retries: int | None,
    enable_media_synthesis: bool,
) -> EffectiveGenerationPolicy:
    if not isinstance(raw_policy, dict):
        raise ValueError("Fast Mode effective generation policy is required")
    try:
        policy = EffectiveGenerationPolicy.model_validate(raw_policy)
    except ValidationError as exc:
        raise ValueError("Fast Mode effective generation policy is invalid") from exc
    if policy.scenario != "fast":
        raise ValueError("Fast Mode effective generation policy scenario mismatch")
    if tenant_id is not None and tenant_id != policy.tenant_id:
        raise ValueError("Fast Mode effective generation policy tenant mismatch")
    if artifact_disposition != policy.artifact_disposition:
        raise ValueError("Fast Mode effective generation policy disposition mismatch")
    if provider_max_retries is not None and provider_max_retries != policy.provider_max_retries:
        raise ValueError("Fast Mode effective generation policy retry mismatch")
    if enable_media_synthesis is not policy.enable_media_synthesis:
        raise ValueError("Fast Mode effective generation policy media intent mismatch")
    return policy


def _scoped_artifact_path(path: str | Path, *, artifact_root: Path) -> str:
    candidate = Path(path).resolve()
    scoped_root = artifact_root.resolve()
    try:
        candidate.relative_to(scoped_root)
        relative = candidate.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError("Fast Mode provider returned an artifact outside tenant scope") from exc
    return relative.as_posix()


def get_fast_mode_service() -> FastModeService:
    """Return the singleton FastModeService instance."""
    global _fast_mode_service_instance
    if _fast_mode_service_instance is None:
        _fast_mode_service_instance = FastModeService()
    return _fast_mode_service_instance

# System prompt for converting user's simple description into a professional
# Seedance video generation prompt.
_PROMPT_ENHANCE_SYSTEM = """You are an expert AI video generation prompt engineer.
Convert the user's simple description into a high-quality, professional
video prompt optimized for Seedance / Happy Horse AI video models.

Requirements:
- Output MUST be in English
- Include: scene, camera angle, lighting, movement, atmosphere
- Be vivid and specific
- Length: STRICTLY 80-150 words, MAX 1000 characters total
- No product showcase / 360 rotation / turntable patterns
- Focus on cinematic, lifestyle, or narrative shots

CONTENT SAFETY (POYO/Seedance content filter rejects prompts that imply):
- Real human faces, especially children, public figures, or recognizable identities
- Brand logos, trademarked characters, or copyrighted IP
- Violence, blood, weapons, gore, war scenes
- Explicit/sexual content, nudity, suggestive poses
- Drugs, alcohol abuse, smoking
- Political figures, religious symbols, cultural sensitive topics
- Medical procedures, surgical content, injuries

If the user prompt is borderline (e.g. mentions a person, child, or product),
REWRITE to remove these elements: replace people with abstract figures or
silhouettes, products with generic stand-ins, brand names with neutral terms.
Default to nature/landscape/abstract/object-focused safe imagery.

HARD CONSTRAINT: video_prompt MUST be <= 1000 characters.
The downstream POYO API rejects prompts > 2500 chars.

Respond in strict JSON:
{
  "video_prompt": "the professional prompt (80-150 words, <= 1000 chars)",
  "scene_description": "1-sentence summary"
}
"""


class FastModeService:
    """Fast Mode: text → LLM prompt → video (10-15s).

    Completely independent from pipelines, scenarios, and LangGraph.
    """

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        seedance_client: Any | None = None,
        cosyvoice_client: Any | None = None,
        seedance_client_factory: Callable[..., Any] | None = None,
        cosyvoice_client_factory: Callable[..., Any] | None = None,
    ):
        if seedance_client_factory is not None:
            self._seedance_client_factory = seedance_client_factory
        elif seedance_client is not None:
            self._seedance_client_factory = lambda **_kwargs: seedance_client
        else:
            self._seedance_client_factory = SeedanceClient

        if cosyvoice_client_factory is not None:
            self._cosyvoice_client_factory = cosyvoice_client_factory
        elif cosyvoice_client is not None:
            self._cosyvoice_client_factory = lambda **_kwargs: cosyvoice_client
        else:
            self._cosyvoice_client_factory = CosyVoiceClient

        self.llm = llm_client or LLMClient()
        # P2: Cache model metadata once at init — avoids per-request reflection
        self._llm_model = self._resolve_llm_model()
        # Do not instantiate a request-key-bearing media client just to expose
        # debug metadata. The concrete backend is reported after per-run client
        # construction; no-media exposes only the routed model candidate.
        self._video_model = str(select_model("s1"))

    def _resolve_llm_model(self) -> str:
        """Resolve model metadata without constructing a provider SDK client."""

        for attr in ("model_name", "model", "model_id"):
            value = getattr(self.llm, attr, None)
            if isinstance(value, str) and value:
                return value
        if isinstance(self.llm, LLMClient) and self.llm.provider == "deepseek":
            return "deepseek-v4-flash"
        return DEFAULT_LLM_PROVIDER

    async def generate(
        self,
        user_prompt: str,
        duration: int = 15,
        enable_tts: bool = False,
        on_stage: Callable[[str], object] | None = None,
        artifact_disposition: FastModeArtifactDisposition = "pending_review",
        tenant_id: str | None = None,
        artifact_run_id: str | None = None,
        provider_max_retries: int | None = None,
        enable_media_synthesis: bool = False,
        effective_generation_policy: dict[str, Any] | None = None,
    ) -> FastModeResult:
        """Validate server authority, then execute one policy-bound Fast run."""

        policy = _validate_fast_effective_policy(
            effective_generation_policy,
            tenant_id=tenant_id,
            artifact_disposition=artifact_disposition,
            provider_max_retries=provider_max_retries,
            enable_media_synthesis=enable_media_synthesis,
        )
        resolved_run_id = _safe_path_segment(
            artifact_run_id,
            f"fast_mode_{int(time.time())}",
        )
        token = bind_effective_generation_policy(policy)
        operation_scope_token = None
        try:
            operation_scope_token = bind_provider_operation_scope(
                resolve_provider_operation_scope("fast", "generate")
            )
            result = await self._generate_with_policy(
                user_prompt=user_prompt,
                duration=duration,
                enable_tts=enable_tts,
                on_stage=on_stage,
                artifact_disposition=policy.artifact_disposition,
                tenant_id=policy.tenant_id,
                artifact_run_id=resolved_run_id,
                provider_max_retries=policy.provider_max_retries,
                enable_media_synthesis=policy.enable_media_synthesis,
            )
            from src.services.transparency_provenance import record_fast_provenance

            return cast(
                FastModeResult,
                record_fast_provenance(
                    result=result,
                    tenant_id=policy.tenant_id,
                    run_id=resolved_run_id,
                    artifact_disposition=policy.artifact_disposition,
                    c2pa_signing_mode=policy.c2pa_signing_mode,
                    output_dir=OUTPUT_DIR,
                ),
            )
        finally:
            if operation_scope_token is not None:
                reset_provider_operation_scope(operation_scope_token)
            reset_effective_generation_policy(token)

    async def _generate_with_policy(
        self,
        user_prompt: str,
        duration: int,
        enable_tts: bool,
        on_stage: Callable[[str], object] | None,
        artifact_disposition: Literal["pending_review", "quarantine"],
        tenant_id: str,
        artifact_run_id: str | None,
        provider_max_retries: int,
        enable_media_synthesis: bool,
    ) -> FastModeResult:
        """Generate a short video from simple text input.

        Args:
            user_prompt: User's simple description (can be any language).
            duration: Video duration in seconds (10 or 15).
            enable_tts: Whether to generate voiceover with CosyVoice.
            enable_media_synthesis: Validated server-resolved media intent.

        Returns:
            Dict with video_path, debug info, and timing.
        """
        total_start = time.perf_counter()
        duration = max(10, min(15, duration))

        def _stage(s: str) -> None:
            if on_stage is not None:
                try:
                    on_stage(s)
                except (TypeError, RuntimeError):
                    # Callback failures should not crash the pipeline —
                    # the callback is a progress indicator, not a critical path.
                    logger.warning(
                        "fast_mode: stage callback failed",
                        stage=s,
                        error_code="stage_callback_failed",
                    )

        _stage("llm")
        llm_start = time.perf_counter()
        logger.info("fast_mode: enhancing prompt", prompt_length=len(user_prompt))

        operation_scope = get_provider_operation_scope()
        if operation_scope is None:
            operation_scope = resolve_provider_operation_scope("fast", "generate")

        try:
            # Fast Mode uses the exact reviewed low-latency V4 model contract.
            enhanced = await self.llm.invoke_json(
                system_prompt=_PROMPT_ENHANCE_SYSTEM,
                user_message=f"User description:\n{user_prompt}\n\nGenerate a professional video prompt in English.",
                model="deepseek-v4-flash" if DEFAULT_LLM_PROVIDER == "deepseek" else None,
                operation_key="fast.prompt_enhance",
                operation_instance=build_provider_operation_instance(operation_scope, slot="prompt"),
            )
            video_prompt = enhanced.get("video_prompt", "")
            scene_description = enhanced.get("scene_description", "")
        except ProviderCostContractError:
            raise
        except (LLMNotConfiguredError, TimeoutError, ValueError, KeyError, TypeError):
            logger.info("fast_mode: local LLM fallback selected")
            video_prompt = user_prompt
            scene_description = user_prompt

        llm_time_ms = int((time.perf_counter() - llm_start) * 1000)
        logger.info(
            "fast_mode: prompt enhanced",
            llm_time_ms=llm_time_ms,
            prompt_length=len(video_prompt),
        )

        artifact_review_status = (
            "pending_review" if artifact_disposition == "pending_review" else None
        )
        artifact_storage_scope = (
            "tenant_pending_review"
            if artifact_disposition == "pending_review"
            else "tenant_quarantine"
        )
        if not enable_media_synthesis:
            total_time_ms = int((time.perf_counter() - total_start) * 1000)
            return {
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "completion_kind": "no_media",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "video_path": "",
                "video_url": "",
                "filename": "",
                "llm_prompt": video_prompt,
                "scene_description": scene_description,
                "user_prompt": user_prompt,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "generation_time_ms": total_time_ms,
                "timing": {
                    "llm_ms": llm_time_ms,
                    "video_ms": 0,
                    "tts_ms": 0,
                },
                "model_info": {
                    "llm": DEFAULT_LLM_PROVIDER,
                    "llm_model": self._llm_model,
                    "video": self._video_model,
                    "tts": None,
                },
                "is_stub": False,
                "simulated": False,
                "tts_path": None,
                "tts_is_fallback": False,
                "tts_fallback_reason": None,
                "artifact_disposition": artifact_disposition,
                "artifact_review_status": artifact_review_status,
                "artifact_storage_scope": artifact_storage_scope,
                "artifact_run_id": artifact_run_id,
                "effective_policy_version": GENERATION_POLICY_VERSION,
            }

        artifact_output_dir = _artifact_output_dir(
            artifact_disposition,
            tenant_id=tenant_id,
            run_id=artifact_run_id,
        )
        video_start = time.perf_counter()
        seedance_client: Any | None = None
        cosyvoice_client: Any | None = None
        tts_path: str | None = None
        tts_time_ms = 0
        tts_is_fallback = False
        tts_fallback_reason: str | None = None

        try:
            seedance_client = self._seedance_client_factory(
                output_dir=artifact_output_dir,
                max_retries=provider_max_retries,
            )
            if seedance_client is None:
                raise RuntimeError("Seedance client factory returned no client")
            active_seedance_client: Any = seedance_client

            # Build every required client/coroutine before constructing the
            # video coroutine. A synchronous TTS-client failure must not leave
            # an unawaited provider submit behind.
            tts_future: Awaitable[Any] | None = None
            if enable_tts and scene_description:
                cosyvoice_client = self._cosyvoice_client_factory(
                    output_dir=artifact_output_dir / "audio"
                )
                if cosyvoice_client is None:
                    raise RuntimeError("CosyVoice client factory returned no client")
                active_cosyvoice_client: Any = cosyvoice_client
                synthesize_with_metadata = getattr(
                    active_cosyvoice_client,
                    "synthesize_with_metadata",
                    None,
                )
                if callable(synthesize_with_metadata):
                    tts_future = cast(
                        Awaitable[Any],
                        synthesize_with_metadata(
                            text=scene_description,
                            language="en",
                            operation_instance=build_provider_operation_instance(operation_scope, slot="tts"),
                        ),
                    )
                else:
                    # Compatibility for injected legacy clients that still
                    # expose only synthesize() -> Path.
                    tts_future = active_cosyvoice_client.synthesize(
                        text=scene_description,
                        language="en",
                        operation_instance=build_provider_operation_instance(operation_scope, slot="tts"),
                    )

            # ── Step 2: Video + optional TTS in parallel ──
            _stage("video")
            logger.info(
                "fast_mode: generating video",
                duration=duration,
                enable_tts=enable_tts,
            )
            video_future: Awaitable[Any] = active_seedance_client.text_to_video(
                prompt=video_prompt,
                duration=duration,
                resolution="720p",
                operation_instance=(
                    build_provider_operation_instance(operation_scope, slot="video")
                ),
                model=(
                    select_model("s1")
                    if bool(getattr(active_seedance_client, "_is_poyo", False))
                    else None
                ),
            )

            if tts_future is not None:
                _stage("tts")
                results = await asyncio.gather(video_future, tts_future, return_exceptions=True)
                video_result = results[0]
                tts_result = results[1]

                # TTS failure is non-fatal — log and continue
                if isinstance(tts_result, Exception):
                    candidate_error_code = getattr(tts_result, "code", None)
                    tts_fallback_reason = (
                        candidate_error_code
                        if isinstance(candidate_error_code, str)
                        and candidate_error_code.startswith("provider_cost_")
                        else "synthesis_error"
                    )
                    logger.warning(
                        "fast_mode: TTS generation failed",
                        error_code=tts_fallback_reason,
                        is_fallback=False,
                    )
                elif isinstance(tts_result, CosyVoiceSynthesisResult):
                    tts_path = str(tts_result.path)
                    tts_is_fallback = tts_result.is_fallback
                    tts_fallback_reason = tts_result.reason
                    tts_time_ms = int((time.perf_counter() - video_start) * 1000)
                    logger.info(
                        "fast_mode: TTS artifact ready",
                        attempt_id=tts_result.attempt_id,
                        input_utf8_bytes=tts_result.input_utf8_bytes,
                        output_size_bytes=(
                            tts_result.artifact_metadata.get("size_bytes")
                            if tts_result.artifact_metadata
                            else None
                        ),
                        is_fallback=tts_is_fallback,
                    )
                elif tts_result:
                    tts_path = str(tts_result)
                    tts_time_ms = int((time.perf_counter() - video_start) * 1000)
                    logger.info("fast_mode: TTS generated", is_fallback=False)
            else:
                try:
                    video_result = await video_future
                except (TimeoutError, RuntimeError, ConnectionError) as e:
                    from src.tools.error_classifier import classify_error
                    structured = classify_error(e, context="fast_mode.video")
                    logger.error(
                        "fast_mode: video generation failed",
                        error_code=structured.code.value,
                        recoverable=structured.recoverable,
                    )
                    raise RuntimeError("Video generation failed") from None
        finally:
            clients = [
                client
                for client in (cosyvoice_client, seedance_client)
                if client is not None and callable(getattr(client, "close", None))
            ]
            if clients:
                close_results = await asyncio.gather(
                    *(client.close() for client in clients),
                    return_exceptions=True,
                )
                for close_error in close_results:
                    if isinstance(close_error, BaseException):
                        logger.warning(
                            "fast_mode: media client close failed",
                            error_code="media_client_close_failed",
                        )

        video_time_ms = int((time.perf_counter() - video_start) * 1000)
        assert seedance_client is not None

        # Video failure is fatal
        if isinstance(video_result, BaseException):
            logger.error("fast_mode: video generation failed", error_code="video_generation_failed")
            raise RuntimeError("Video generation failed") from None

        if not isinstance(video_result, dict):
            logger.error("fast_mode: video generation returned invalid result", result_type=type(video_result).__name__)
            raise RuntimeError("Video generation failed: invalid result shape")

        video_data = cast(SeedanceVideoResult, video_result)
        local_path = video_data.get("local_path", "")
        is_stub = bool(video_data.get("_stub_mode"))

        # Get file info
        file_size = 0
        if local_path and Path(local_path).exists():
            file_size = Path(local_path).stat().st_size

        logger.info(
            "fast_mode: video generated",
            video_time_ms=video_time_ms,
            is_stub=is_stub,
            file_size=file_size,
        )

        # ── Step 3: Build result ──
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        tts_model = None
        if enable_tts:
            tts_model = "silent-fallback" if tts_is_fallback else "cosyvoice2"
        model_info: FastModeModelInfo = {
            "llm": DEFAULT_LLM_PROVIDER,
            "llm_model": self._llm_model,
            "video": f"poyo-{select_model('s1')}" if seedance_client._is_poyo else "seedance-2.0",
            "tts": tts_model,
        }
        # If stub mode (video generation failed), mark as failure and do not
        # return a non-existent filename that would cause a 404 on media fetch.
        if is_stub:
            stub_mode = video_data.get("_stub_mode", "unknown")
            logger.warning(
                "fast_mode: video generation failed (stub mode)",
                mode=stub_mode,
                total_time_ms=total_time_ms,
            )
            return {
                "status": "error",
                "lifecycle_status": "error",
                "completion_kind": "execution_failed",
                "request_succeeded": False,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "error": f"Video generation failed: {stub_mode}",
                "video_path": "",
                "video_url": "",
                "filename": "",
                "llm_prompt": video_prompt,
                "scene_description": scene_description,
                "user_prompt": user_prompt,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "generation_time_ms": total_time_ms,
                "timing": {
                    "llm_ms": llm_time_ms,
                    "video_ms": video_time_ms,
                    "tts_ms": tts_time_ms,
                },
                "model_info": model_info,
                "is_stub": True,
                "simulated": True,
                "tts_path": None,
                "tts_is_fallback": tts_is_fallback,
                "tts_fallback_reason": tts_fallback_reason,
                "artifact_disposition": artifact_disposition,
                "artifact_review_status": artifact_review_status,
                "artifact_storage_scope": artifact_storage_scope,
                "artifact_run_id": artifact_run_id,
                "effective_policy_version": GENERATION_POLICY_VERSION,
            }

        if not local_path or not Path(local_path).is_file() or file_size <= 0:
            raise RuntimeError("Video generation failed: local artifact is missing")

        # Only tenant-scoped, server-servable relative paths leave the service.
        filename = Path(local_path).name
        scoped_video_path = _scoped_artifact_path(
            local_path,
            artifact_root=artifact_output_dir,
        )
        scoped_tts_path = (
            _scoped_artifact_path(tts_path, artifact_root=artifact_output_dir)
            if tts_path
            else None
        )
        full_media_success = not enable_tts or (
            scoped_tts_path is not None and not tts_is_fallback
        )
        result_status = "completed_full" if full_media_success else "completed_bounded"
        completion_kind = "full_media" if full_media_success else "bounded_media"

        result: FastModeResult = {
            "status": result_status,
            "lifecycle_status": result_status,
            "completion_kind": completion_kind,
            "request_succeeded": True,
            "success": full_media_success,
            "full_media_success": full_media_success,
            "pipeline_complete": full_media_success,
            "publish_allowed": False,
            "delivery_accepted": False,
            "video_path": scoped_video_path,
            "video_url": scoped_video_path,
            "filename": filename,
            "llm_prompt": video_prompt,
            "scene_description": scene_description,
            "user_prompt": user_prompt,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "generation_time_ms": total_time_ms,
            "timing": {
                "llm_ms": llm_time_ms,
                "video_ms": video_time_ms,
                "tts_ms": tts_time_ms,
            },
            "model_info": model_info,
            "is_stub": False,
            "simulated": False,
            "tts_path": scoped_tts_path,
            "tts_is_fallback": tts_is_fallback,
            "tts_fallback_reason": tts_fallback_reason,
            "artifact_disposition": artifact_disposition,
            "artifact_review_status": artifact_review_status,
            "artifact_storage_scope": artifact_storage_scope,
            "artifact_run_id": artifact_run_id,
            "effective_policy_version": GENERATION_POLICY_VERSION,
        }

        if local_path:
            try:
                from src.tools.poster_extractor import ensure_poster
                ensure_poster(local_path)
            except (AttributeError, TypeError, ValueError):
                logger.warning(
                    "fast_mode: poster extraction failed",
                    error_code="poster_extraction_failed",
                )

        logger.info(
            "fast_mode: complete",
            total_time_ms=total_time_ms,
            is_stub=False,
            filename=filename,
        )
        return result
