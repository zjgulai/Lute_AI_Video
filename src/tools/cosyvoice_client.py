"""SiliconFlow CosyVoice TTS with exact UTF-8-byte cost accounting.

The configured path is admitted only after a tenant-bound execution context has
reserved the exact provider-input byte count.  It performs one speech mutation,
settles the durable ledger before touching local artifacts, and never converts a
post-submit failure into silent audio.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import httpx
import structlog

from src.config import (
    COSYVOICE_MODEL as CONFIG_COSYVOICE_MODEL,
)
from src.config import (
    COSYVOICE_VOICE,
    COSYVOICE_VOICE_FEMALE,
    OUTPUT_DIR,
    SILICONFLOW_API_BASE,
    SILICONFLOW_API_KEY,
)
from src.models.provider_cost import (
    ProviderCostContractError,
    TTSUtf8BytesBillingFacts,
)
from src.services.provider_cost import (
    ProviderCostOperationDefinition,
    ProviderCostService,
    build_provider_cost_service,
)
from src.services.provider_execution import (
    ProviderExecutionContext,
    get_provider_execution_context,
)
from src.services.provider_price_catalog import ProviderPriceCatalog

logger = structlog.get_logger()

COSYVOICE_GLOBAL_ENDPOINT = "https://api.siliconflow.com/v1"
COSYVOICE_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
COSYVOICE_REGION = "siliconflow_global_usd"
COSYVOICE_OPERATION_KEY = "tts.cosyvoice.speech"
COSYVOICE_RESERVATION_TTL_SECONDS = 300
TTS_MAX_INPUT_CHARS = 128_000
TTS_TIMEOUT_SECONDS = 60.0

BASE_URL = SILICONFLOW_API_BASE or COSYVOICE_GLOBAL_ENDPOINT
DEFAULT_MODEL = CONFIG_COSYVOICE_MODEL or COSYVOICE_MODEL
DEFAULT_VOICE = COSYVOICE_VOICE or f"{COSYVOICE_MODEL}:alex"
DEFAULT_VOICE_FEMALE = COSYVOICE_VOICE_FEMALE or f"{COSYVOICE_MODEL}:anna"

VOICE_PRESETS = MappingProxyType(
    {
        "en": DEFAULT_VOICE,
        "female_en": DEFAULT_VOICE_FEMALE,
    }
)
_SUPPORTED_RESPONSE_FORMATS = frozenset({"mp3", "opus", "wav", "pcm"})
_SAFE_OPERATION_INSTANCE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_SAFE_VOICE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,512}$")
_SAFE_LANGUAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

ProviderCostServiceFactory = Callable[
    [Mapping[str, ProviderCostOperationDefinition]],
    ProviderCostService,
]


@dataclass(frozen=True, slots=True)
class FrozenTTSInput:
    """Transient final provider input facts; raw text never enters the ledger."""

    text: str
    input_utf8_bytes: int
    input_sha256: str


@dataclass(frozen=True, slots=True)
class CosyVoiceSynthesisResult:
    """Truthful TTS artifact metadata while preserving the legacy Path API."""

    path: Path
    is_fallback: bool
    reason: str | None = None
    input_utf8_bytes: int | None = None
    attempt_id: str | None = None
    artifact_metadata: Mapping[str, Any] | None = None


def freeze_tts_input(text: object) -> FrozenTTSInput:
    """Freeze exact final text and strict UTF-8 billing facts before reservation."""

    if type(text) is not str or not text or len(text) > TTS_MAX_INPUT_CHARS:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS input must be a non-empty string within the provider character limit",
        )
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS input cannot be encoded as strict UTF-8",
        ) from None
    return FrozenTTSInput(
        text=text,
        input_utf8_bytes=len(encoded),
        input_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _validate_voice(voice: object) -> str:
    """Keep the existing voice surface open while rejecting unsafe shapes."""

    if not isinstance(voice, str) or _SAFE_VOICE_RE.fullmatch(voice) is None:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS voice must be a bounded non-empty provider voice identifier",
        )
    return voice


def _validate_response_format(response_format: object) -> str:
    if not isinstance(response_format, str) or response_format not in _SUPPORTED_RESPONSE_FORMATS:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS response format is unsupported",
        )
    return response_format


def _validate_speed(speed: object) -> float:
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS speed must be a finite number",
        )
    value = float(speed)
    if not math.isfinite(value) or value < 0.25 or value > 4.0:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS speed is outside the provider range",
        )
    return value


def _validate_language(language: object) -> str:
    if not isinstance(language, str) or _SAFE_LANGUAGE_RE.fullmatch(language) is None:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "TTS language must be a bounded identifier",
        )
    return language


class CosyVoiceClient:
    """CosyVoice2 adapter with durable reserve/start/settle semantics."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        output_dir: Path | None = None,
        *,
        model: str | None = None,
        provider_billing_region: str = COSYVOICE_REGION,
        price_catalog: ProviderPriceCatalog | None = None,
        cost_service_factory: ProviderCostServiceFactory | None = None,
    ) -> None:
        configured_base_url = base_url if base_url is not None else BASE_URL
        configured_model = model if model is not None else DEFAULT_MODEL
        if (
            configured_base_url != COSYVOICE_GLOBAL_ENDPOINT
            or configured_model != COSYVOICE_MODEL
            or provider_billing_region != COSYVOICE_REGION
        ):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "SiliconFlow CosyVoice provider contract is not exact",
            )
        if price_catalog is not None and not isinstance(price_catalog, ProviderPriceCatalog):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider price catalog injection is invalid",
            )
        if cost_service_factory is not None and not callable(cost_service_factory):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service factory is invalid",
            )

        if api_key is not None:
            self.api_key = api_key
        else:
            from src.tools.llm_client import get_request_api_key

            self.api_key = get_request_api_key("SILICONFLOW_API_KEY") or SILICONFLOW_API_KEY
        self.base_url = configured_base_url
        self.model = configured_model
        self.provider_billing_region = provider_billing_region
        self.output_dir = output_dir or OUTPUT_DIR / "audio"
        self._price_catalog = price_catalog or ProviderPriceCatalog.load_default()
        self._cost_service_factory = cost_service_factory or self._build_cost_service
        self._client: httpx.AsyncClient | None = None

    def _build_cost_service(
        self,
        registry: Mapping[str, ProviderCostOperationDefinition],
    ) -> ProviderCostService:
        return build_provider_cost_service(
            operation_registry=registry,
            price_catalog=self._price_catalog,
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        key = self.api_key if isinstance(self.api_key, str) else ""
        if not key.strip():
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "SiliconFlow credential disappeared before client construction",
            )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "AI-Video-Agent/1.0",
            },
            timeout=TTS_TIMEOUT_SECONDS,
        )
        return self._client

    @staticmethod
    def _request_fingerprint(
        *,
        frozen_input: FrozenTTSInput,
        voice: str,
        response_format: str,
        speed: float,
        operation_instance: str,
        regeneration_epoch_ref: str | None,
    ) -> str:
        payload = {
            "version": "tts-mutation-intent.v1",
            "operation_key": COSYVOICE_OPERATION_KEY,
            "operation_instance": operation_instance,
            "regeneration_epoch_ref": regeneration_epoch_ref,
            "provider": "siliconflow",
            "canonical_model": COSYVOICE_MODEL,
            "provider_billing_region": COSYVOICE_REGION,
            "input_sha256": frozen_input.input_sha256,
            "input_utf8_bytes": frozen_input.input_utf8_bytes,
            "voice_sha256": hashlib.sha256(voice.encode("utf-8")).hexdigest(),
            "response_format": response_format,
            "speed": speed,
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _validate_operation_instance(operation_instance: object) -> str:
        if not isinstance(operation_instance, str) or _SAFE_OPERATION_INSTANCE_RE.fullmatch(operation_instance) is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "TTS operation instance is invalid",
            )
        return operation_instance

    @staticmethod
    def _raise_replay(attempt: Mapping[str, object]) -> None:
        state = attempt.get("state")
        if state == "ambiguous":
            code = "provider_cost_outcome_ambiguous"
        elif state == "accounting_error":
            code = "provider_cost_accounting_error"
        else:
            code = "provider_cost_attempt_conflict"
        raise ProviderCostContractError(
            code,
            "durable TTS attempt cannot be resubmitted",
        )

    def _definition(
        self,
        *,
        frozen_input: FrozenTTSInput,
        operation_instance: str,
    ) -> ProviderCostOperationDefinition:
        logical_operation = f"{COSYVOICE_OPERATION_KEY}.{operation_instance}"
        if len(logical_operation) > 160:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "TTS paid logical operation is too long",
            )
        return ProviderCostOperationDefinition(
            registry_key=COSYVOICE_OPERATION_KEY,
            logical_operation=logical_operation,
            provider="siliconflow",
            canonical_model=COSYVOICE_MODEL,
            provider_billing_region=COSYVOICE_REGION,
            catalog_operation="speech_synthesis",
            media_type="audio",
            billing_fact_kind="tts_utf8_bytes.v1",
            dimensions=(),
            reservation_billing_facts=TTSUtf8BytesBillingFacts(
                schema_version="tts_utf8_bytes.v1",
                input_utf8_bytes=frozen_input.input_utf8_bytes,
            ),
            reservation_ttl_seconds=COSYVOICE_RESERVATION_TTL_SECONDS,
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str = "en",
        response_format: str = "mp3",
        speed: float = 1.0,
        *,
        operation_instance: str = "primary",
    ) -> Path:
        result = await self.synthesize_with_metadata(
            text=text,
            voice=voice,
            language=language,
            response_format=response_format,
            speed=speed,
            operation_instance=operation_instance,
        )
        return result.path

    async def synthesize_with_metadata(
        self,
        text: str,
        voice: str | None = None,
        language: str = "en",
        response_format: str = "mp3",
        speed: float = 1.0,
        *,
        operation_instance: str = "primary",
    ) -> CosyVoiceSynthesisResult:
        """Synthesize once; only a pre-submit missing-key branch may fallback."""

        frozen_input = freeze_tts_input(text)
        selected_language = _validate_language(language)
        selected_voice = _validate_voice(
            voice or VOICE_PRESETS.get(selected_language, VOICE_PRESETS["en"])
        )
        selected_format = _validate_response_format(response_format)
        selected_speed = _validate_speed(speed)
        selected_instance = self._validate_operation_instance(operation_instance)

        if not isinstance(self.api_key, str) or not self.api_key.strip():
            return CosyVoiceSynthesisResult(
                path=self._build_silent_mp3(output_label=f"tts_{selected_language}_fallback"),
                is_fallback=True,
                reason="missing_api_key",
                input_utf8_bytes=frozen_input.input_utf8_bytes,
            )

        context = get_provider_execution_context()
        if not isinstance(context, ProviderExecutionContext):
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid TTS mutation requires a bound execution context",
            )
        if context.provider_max_retries != 0:
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid TTS mutation retry authority is invalid",
            )

        definition = self._definition(
            frozen_input=frozen_input,
            operation_instance=selected_instance,
        )
        service = self._cost_service_factory({COSYVOICE_OPERATION_KEY: definition})
        if not isinstance(service, ProviderCostService):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service injection is invalid",
            )
        reservation = await service.reserve_or_replay(
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            operation_key=COSYVOICE_OPERATION_KEY,
            attempt_fingerprint=self._request_fingerprint(
                frozen_input=frozen_input,
                voice=selected_voice,
                response_format=selected_format,
                speed=selected_speed,
                operation_instance=selected_instance,
                regeneration_epoch_ref=(
                    context.regeneration_epoch.epoch_ref
                    if context.regeneration_epoch is not None
                    else None
                ),
            ),
            regeneration_epoch=context.regeneration_epoch,
        )
        if reservation.outcome != "owner":
            self._raise_replay(reservation.attempt)
        attempt_id = str(reservation.attempt["attempt_id"])
        await service.mark_submission_started(
            tenant_id=context.tenant_id,
            attempt_id=attempt_id,
        )

        try:
            client = self._get_client()
        except Exception as exc:
            await service.release(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
            )
            if isinstance(exc, ProviderCostContractError):
                raise
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "TTS provider client construction failed before submit",
            ) from None

        payload = {
            "model": COSYVOICE_MODEL,
            "input": frozen_input.text,
            "voice": selected_voice,
            "response_format": selected_format,
            "speed": selected_speed,
        }
        try:
            async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
                response = await client.post("/audio/speech", json=payload)
                response.raise_for_status()
                audio_bytes = response.content
        except asyncio.CancelledError:
            await asyncio.shield(
                service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submission_started",
                )
            )
            raise
        except Exception:
            await service.mark_ambiguous(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
            )
            raise ProviderCostContractError(
                "provider_cost_outcome_ambiguous",
                "SiliconFlow TTS acknowledgement is uncertain",
            ) from None

        if not isinstance(audio_bytes, bytes):
            transition = await service.mark_accounting_error(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submission_started",
            )
            del transition
            raise ProviderCostContractError(
                "provider_cost_accounting_error",
                "SiliconFlow TTS success payload is not audio bytes",
            )

        facts = TTSUtf8BytesBillingFacts(
            schema_version="tts_utf8_bytes.v1",
            input_utf8_bytes=frozen_input.input_utf8_bytes,
        )
        transition = await service.settle(
            tenant_id=context.tenant_id,
            attempt_id=attempt_id,
            expected_state="submission_started",
            settlement_billing_facts=facts,
        )
        if transition["attempt"].get("state") != "settled":
            if transition["attempt"].get("state") == "accounting_error":
                raise ProviderCostContractError(
                    "provider_cost_accounting_error",
                    "TTS input bytes could not be settled",
                )
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "TTS cost transition did not settle",
            )

        filename = f"cosyvoice_{selected_language}_{attempt_id[:16]}.{selected_format}"
        filepath = self.output_dir / filename
        staging_path = self.output_dir / f".{filename}.staging"
        artifact_metadata: Mapping[str, Any]
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            staging_path.write_bytes(audio_bytes)
            staging_path.replace(filepath)
            artifact_metadata = self._probe_audio_artifact(filepath, selected_format)
        except Exception as exc:
            for path in (staging_path, filepath):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "cosyvoice: artifact cleanup failed",
                        artifact_name=path.name,
                        error_code="provider_cost_artifact_cleanup_failed",
                    )
            raise ProviderCostContractError(
                "provider_cost_artifact_failed",
                "settled TTS audio failed local artifact verification",
            ) from exc

        logger.info(
            "cosyvoice: synthesized",
            artifact_name=filename,
            input_utf8_bytes=frozen_input.input_utf8_bytes,
            output_size_bytes=len(audio_bytes),
            response_format=selected_format,
        )
        return CosyVoiceSynthesisResult(
            path=filepath,
            is_fallback=False,
            input_utf8_bytes=frozen_input.input_utf8_bytes,
            attempt_id=attempt_id,
            artifact_metadata=artifact_metadata,
        )

    @staticmethod
    def _probe_audio_artifact(path: Path, response_format: str) -> dict[str, Any]:
        """Run a deterministic local format/duration probe after settlement."""

        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("audio artifact is empty or missing")
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        parsed = json.loads(completed.stdout)
        format_info = parsed.get("format") if isinstance(parsed, dict) else None
        format_name = format_info.get("format_name") if isinstance(format_info, dict) else None
        duration = format_info.get("duration") if isinstance(format_info, dict) else None
        if not isinstance(format_name, str) or not isinstance(duration, str):
            raise ValueError("ffprobe returned incomplete audio metadata")
        if response_format != "pcm" and response_format not in format_name.split(","):
            raise ValueError("audio artifact format does not match request")
        duration_seconds = float(duration)
        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError("audio artifact duration is invalid")
        return {
            "format": response_format,
            "duration_ms": int(round(duration_seconds * 1000)),
            "size_bytes": path.stat().st_size,
        }

    async def synthesize_script(
        self,
        segments: list[dict[str, Any]],
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Synthesize bounded script segments with server-owned operation slots."""

        results = []
        for index, seg in enumerate(segments):
            path = await self.synthesize(
                text=seg.get("text", ""),
                language=language,
                operation_instance=f"segment.{index}",
            )
            results.append(
                {
                    "start_time": seg.get("start_time", 0.0),
                    "end_time": seg.get("end_time", 0.0),
                    "file_path": str(path),
                }
            )
        return results

    def _build_silent_mp3(self, output_label: str = "tts") -> Path:
        """Produce a marked local fallback only for the pre-submit no-key branch."""

        out_dir = self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{output_label}.mp3"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                    "-t",
                    "3",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    "64k",
                    str(out_path),
                ],
                capture_output=True,
                check=True,
                timeout=15,
            )
        except Exception:
            out_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 512)
        return out_path

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
