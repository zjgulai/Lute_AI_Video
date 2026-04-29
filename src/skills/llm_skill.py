"""LLMSkill — generic LLM-based skill implementation.

Wraps a system prompt + user message template into a SkillCallable.
Used for most content generation skills (strategy, script, prompts).

Provides built-in:
- Parameter injection into prompt templates
- Output format enforcement via output_schema
- Retry + validation + fallback
"""

from __future__ import annotations

import json
from typing import Any

import structlog

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
        max_retries: Number of LLM call retries before fallback.
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        user_message_template: str,
        output_schema: dict | None = None,
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

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        try:
            if self._output_schema:
                raw_result = await llm.invoke_json(messages)
            else:
                raw_result = await llm.invoke(messages)
                return SkillResult(success=True, data=raw_result)

            # If output_schema is a Pydantic model class
            if isinstance(self._output_schema, type) and hasattr(self._output_schema, "model_validate"):
                validated = self._output_schema.model_validate(raw_result)
                return SkillResult(success=True, data=validated.model_dump())
            
            # Plain dict schema — return as-is
            return SkillResult(success=True, data=raw_result)

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

        if isinstance(self._output_schema, type) and hasattr(self._output_schema, "model_validate"):
            try:
                self._output_schema.model_validate(data)
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
