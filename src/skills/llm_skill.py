"""LLMSkill — generic LLM-based skill implementation.

Wraps a system prompt + user message template into a SkillCallable.
Used for most content generation skills (strategy, script, prompts).

Provides built-in:
- Parameter injection into prompt templates
- Output format enforcement via output_schema
- Validation and explicit local fallback for unconfigured/non-accounting errors
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.models.provider_cost import ProviderCostContractError
from src.skills.base import SkillCallable, SkillResult

logger = structlog.get_logger()


class LLMSkill(SkillCallable):
    """A skill backed by an LLM call with system prompt + user message template.

    Args:
        name: Unique skill identifier.
        description: Human-readable description.
        system_prompt: System prompt template. Use {param_name} for injection.
        user_message_template: User message template. Use {param_name} for injection.
        output_schema: Optional Pydantic-like dict schema for output validation.
            Format: {"type": "object", "properties": {"field": {"type": "string"}, ...}}
        fallback_data: Static fallback data returned when all retries fail.
        max_retries: Retained compatibility metadata; paid mutations are never
            retried by this skill.
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        user_message_template: str,
        output_schema: dict[str, Any] | None = None,
        fallback_data: Any = None,
        max_retries: int = 3,
    ):
        self.name = name
        self.description = description
        self._system_prompt = system_prompt
        self._user_message_template = user_message_template
        self._output_schema = output_schema
        self._fallback_data = fallback_data
        self.max_retries = max_retries

    # ── SkillCallable interface ──

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Execute by calling LLM with the injected prompt templates."""
        from src.tools.llm_client import llm

        system = self._inject_params(self._system_prompt, params)
        user = self._inject_params(self._user_message_template, params)
        variant = params.get("variant", "primary")
        operation_scope = params.get("operation_scope", "execution")
        if not isinstance(operation_scope, str) or not operation_scope:
            operation_scope = "execution"
        operation_instance = params.get("operation_instance")
        if not isinstance(operation_instance, str) or not operation_instance:
            operation_instance = (
                f"{operation_scope}.variant.{variant}" if variant != "primary" else f"{operation_scope}.primary"
            )

        try:
            if self._output_schema:
                raw_result = await llm.invoke_json(
                    system,
                    user,
                    operation_key="skill.llm",
                    operation_instance=operation_instance,
                )
            else:
                raw_result = await llm.invoke(
                    system,
                    user,
                    operation_key="skill.llm",
                    operation_instance=operation_instance,
                )
                return SkillResult(success=True, data=raw_result)

            # If output_schema is a Pydantic model class
            _schema = self._output_schema
            if isinstance(_schema, type) and hasattr(_schema, "model_validate"):
                validated = _schema.model_validate(raw_result)  # type: ignore[union-attr]
                return SkillResult(success=True, data=validated.model_dump())

            # Plain dict schema — return as-is
            return SkillResult(success=True, data=raw_result)

        except ProviderCostContractError:
            raise
        except Exception as e:
            logger.warning(
                "llm_skill: execution failed",
                name=self.name,
                error=str(e),
            )
            return SkillResult(success=False, error=str(e))

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Check required params exist (can be overridden by subclass)."""
        errors = []
        # All LLMSkills need at least a basic check — non-empty params
        if not params:
            errors.append("params dict is empty")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        """Validate output against schema if one exists."""
        if not self._output_schema:
            return []

        errors = []
        if data is None:
            return ["output is None"]

        _schema = self._output_schema
        if isinstance(_schema, type) and hasattr(_schema, "model_validate"):
            try:
                _schema.model_validate(data)  # type: ignore[union-attr]
            except Exception as e:
                errors.append(str(e))

        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Return pre-defined fallback data."""
        if self._fallback_data is not None:
            return SkillResult(success=True, data=self._fallback_data)
        return SkillResult(
            success=True,
            data={"note": f"[{self.name} fallback] — LLM unavailable"},
        )

    # ── Helpers ──

    def _inject_params(self, template: str, params: dict[str, Any]) -> str:
        """Replace {param_name} placeholders with actual values.

        Falls back to string representation for missing params.
        """
        result = template
        for key, value in params.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                if isinstance(value, (dict, list)):
                    result = result.replace(placeholder, json.dumps(value, ensure_ascii=False))
                else:
                    result = result.replace(placeholder, str(value))
        return result
