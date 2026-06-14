"""Dry-run prompt preview gated by runtime commercial injection checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.commercial_contracts import PromptCompileInput
from src.pipeline.provider_prompt_compiler import compile_provider_prompt
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult

RUNTIME_PROMPT_PREVIEW_MODE = "dry_run_prompt_preview"
RUNTIME_PROMPT_PREVIEW_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


class RuntimePromptInjectionDiff(BaseModel):
    planned_hard_token_ids: list[str] = Field(default_factory=list)
    planned_soft_token_ids: list[str] = Field(default_factory=list)
    runtime_hard_token_ids: list[str] = Field(default_factory=list)
    runtime_soft_token_ids: list[str] = Field(default_factory=list)
    compile_hard_token_ids: list[str] = Field(default_factory=list)
    compile_soft_token_ids: list[str] = Field(default_factory=list)
    missing_runtime_hard_token_ids: list[str] = Field(default_factory=list)
    missing_runtime_soft_token_ids: list[str] = Field(default_factory=list)
    compile_extra_hard_token_ids: list[str] = Field(default_factory=list)
    compile_extra_soft_token_ids: list[str] = Field(default_factory=list)

    @property
    def has_blocking_diff(self) -> bool:
        return any(
            (
                self.missing_runtime_hard_token_ids,
                self.compile_extra_hard_token_ids,
                self.compile_extra_soft_token_ids,
            )
        )


class RuntimePromptPreviewResult(BaseModel):
    """Sanitized preview result; prompt body and brand payloads are absent."""

    model_config = ConfigDict(extra="forbid")

    compile_id: str
    scenario: str
    step: str
    mode: Literal["dry_run_prompt_preview"] = RUNTIME_PROMPT_PREVIEW_MODE
    evidence_level: str = RUNTIME_PROMPT_PREVIEW_EVIDENCE_LEVEL
    provider: str
    model: str
    prompt_preview_allowed: bool = False
    compile_blocked: bool = False
    prompt_hash: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    duration_seconds: int
    aspect_ratio: str
    hard_token_ids: list[str] = Field(default_factory=list)
    soft_token_ids: list[str] = Field(default_factory=list)
    dropped_soft_token_ids: list[str] = Field(default_factory=list)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    compile_warnings: list[str] = Field(default_factory=list)
    block_reasons: list[str] = Field(default_factory=list)
    injection_diff: RuntimePromptInjectionDiff = Field(default_factory=RuntimePromptInjectionDiff)


def build_runtime_prompt_preview(
    *,
    compile_input: PromptCompileInput,
    runtime_injection: RuntimeInjectionResult | Mapping[str, Any],
    planned_injection: Mapping[str, Any] | None = None,
) -> RuntimePromptPreviewResult:
    """Build a dry-run prompt preview without exposing prompt text or calling providers."""
    runtime = (
        runtime_injection
        if isinstance(runtime_injection, RuntimeInjectionResult)
        else RuntimeInjectionResult.model_validate(runtime_injection)
    )
    diff = _build_injection_diff(
        compile_input=compile_input,
        runtime=runtime,
        planned_injection=planned_injection or {},
    )
    block_reasons = _pre_compile_block_reasons(
        compile_input=compile_input,
        runtime=runtime,
        diff=diff,
    )
    if block_reasons:
        return _blocked_preview(
            compile_input=compile_input,
            runtime=runtime,
            diff=diff,
            block_reasons=block_reasons,
        )

    compile_result = compile_provider_prompt(compile_input)
    return RuntimePromptPreviewResult(
        compile_id=compile_input.compile_id,
        scenario=compile_input.scenario,
        step=compile_input.step_name,
        provider=compile_result.provider,
        model=compile_result.model,
        prompt_preview_allowed=not compile_result.blocked,
        compile_blocked=compile_result.blocked,
        prompt_hash=compile_result.prompt_hash,
        reference_asset_ids=compile_result.reference_asset_ids,
        duration_seconds=compile_result.duration_seconds,
        aspect_ratio=compile_result.aspect_ratio,
        hard_token_ids=compile_result.hard_token_ids,
        soft_token_ids=compile_result.soft_token_ids,
        dropped_soft_token_ids=compile_result.dropped_soft_token_ids,
        provider_options=compile_result.provider_options,
        compile_warnings=compile_result.compile_warnings,
        block_reasons=compile_result.block_reasons,
        injection_diff=diff,
    )


def _pre_compile_block_reasons(
    *,
    compile_input: PromptCompileInput,
    runtime: RuntimeInjectionResult,
    diff: RuntimePromptInjectionDiff,
) -> list[str]:
    reasons: list[str] = []
    if runtime.scenario != compile_input.scenario or runtime.step != compile_input.step_name:
        reasons.append("runtime injection scenario or step mismatch")
    if not runtime.prompt_injection_allowed:
        reasons.append("runtime injection is not allowed")
        reasons.extend(runtime.blocked_reasons)
    if diff.has_blocking_diff:
        reasons.append("runtime injection token ids do not match compile bundle")
    return list(dict.fromkeys(reasons))


def _blocked_preview(
    *,
    compile_input: PromptCompileInput,
    runtime: RuntimeInjectionResult,
    diff: RuntimePromptInjectionDiff,
    block_reasons: list[str],
) -> RuntimePromptPreviewResult:
    return RuntimePromptPreviewResult(
        compile_id=compile_input.compile_id,
        scenario=compile_input.scenario,
        step=compile_input.step_name,
        provider=compile_input.provider_capability.provider,
        model=compile_input.provider_capability.model,
        prompt_preview_allowed=False,
        compile_blocked=True,
        duration_seconds=compile_input.shot.duration_seconds,
        aspect_ratio=compile_input.platform_target.aspect_ratio,
        hard_token_ids=runtime.hard_token_ids,
        soft_token_ids=runtime.soft_token_ids,
        block_reasons=block_reasons,
        injection_diff=diff,
    )


def _build_injection_diff(
    *,
    compile_input: PromptCompileInput,
    runtime: RuntimeInjectionResult,
    planned_injection: Mapping[str, Any],
) -> RuntimePromptInjectionDiff:
    compile_hard_token_ids = [token.token_id for token in compile_input.brand_bundle.hard_tokens]
    compile_soft_token_ids = [token.token_id for token in compile_input.brand_bundle.soft_tokens]
    planned_hard_token_ids = _string_list(planned_injection.get("hard_token_ids"))
    planned_soft_token_ids = _string_list(planned_injection.get("soft_token_ids"))

    return RuntimePromptInjectionDiff(
        planned_hard_token_ids=planned_hard_token_ids,
        planned_soft_token_ids=planned_soft_token_ids,
        runtime_hard_token_ids=runtime.hard_token_ids,
        runtime_soft_token_ids=runtime.soft_token_ids,
        compile_hard_token_ids=compile_hard_token_ids,
        compile_soft_token_ids=compile_soft_token_ids,
        missing_runtime_hard_token_ids=[
            token_id for token_id in compile_hard_token_ids if token_id not in runtime.hard_token_ids
        ],
        missing_runtime_soft_token_ids=[
            token_id for token_id in compile_soft_token_ids if token_id not in runtime.soft_token_ids
        ],
        compile_extra_hard_token_ids=[
            token_id for token_id in runtime.hard_token_ids if token_id not in compile_hard_token_ids
        ],
        compile_extra_soft_token_ids=[
            token_id for token_id in runtime.soft_token_ids if token_id not in compile_soft_token_ids
        ],
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
