"""One-shot dry-run workflow for prompt preview audit bundles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.models.commercial_contracts import PromptCompileInput, QualityContract
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult
from src.pipeline.runtime_prompt_preview import build_runtime_prompt_preview
from src.quality.prompt_preview_audit_bundle import (
    PromptPreviewAuditBundle,
    build_prompt_preview_audit_bundle,
)


def build_prompt_preview_audit_workflow(
    *,
    contract: QualityContract,
    compile_input: PromptCompileInput,
    runtime_injection: RuntimeInjectionResult | Mapping[str, Any],
    planned_injection: Mapping[str, Any] | None = None,
) -> PromptPreviewAuditBundle:
    """Build a sanitized L2 audit bundle without provider side effects."""
    preview = build_runtime_prompt_preview(
        compile_input=compile_input,
        runtime_injection=runtime_injection,
        planned_injection=planned_injection,
    )
    return build_prompt_preview_audit_bundle(contract=contract, preview=preview)
