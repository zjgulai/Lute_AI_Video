"""SkillCallable abstract base — the contract every skill must fulfill."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class SkillResult:
    """Standardized output envelope for all skill executions.

    Attributes:
        success: Whether the skill executed successfully.
        data: Structured output data (validated, ready to use).
        error: Error message if success=False.
        metadata: Execution metadata (latency, retries, token count).
    """

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error})"
        return f"<SkillResult {status} data_type={type(self.data).__name__}>"


class SkillCallable(ABC):
    """Abstract base class for all pipeline skills.

    Subclasses must implement:
    - execute(params) -> SkillResult: The core logic.
    - validate_params(params) -> list[str]: Parameter validation.
    - validate_output(data) -> list[str]: Output validation.
    - fallback(params) -> SkillResult: Deterministic fallback when all retries fail.

    Subclasses should set:
    - name: Unique skill identifier.
    - description: Human-readable description of what this skill does.
    """

    name: str = ""
    description: str = ""
    max_retries: int = 3

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Execute the skill with given parameters.

        Args:
            params: Skill-specific parameters (validated by validate_params).

        Returns:
            SkillResult with data containing the skill's structured output.
        """
        ...

    @abstractmethod
    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate input parameters.

        Returns:
            List of validation error messages. Empty list = valid.
        """
        ...

    @abstractmethod
    def validate_output(self, data: Any) -> list[str]:
        """Validate the output data before returning.

        Returns:
            List of validation error messages. Empty list = valid.
        """
        ...

    @abstractmethod
    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Deterministic fallback when all retry attempts fail.

        Must return a SkillResult with success=True and valid data.
        No external calls (LLM, API, network) allowed in fallback.

        P0-3: safe_execute marks the returned SkillResult with
        metadata["is_fallback"] = True so callers can distinguish
        real success from degraded fallback data.
        """
        ...

    async def safe_execute(self, params: dict[str, Any]) -> SkillResult:
        """Execute with retry + validation + fallback.

        This is the primary entry point for pipeline nodes.
        Subclasses should override max_retries or retry_delay_seconds
        for different behavior.

        Args:
            params: Skill-specific parameters.

        Returns:
            SkillResult guaranteed (never raises).
        """
        # 1. Validate params
        param_errors = self.validate_params(params)
        if param_errors:
            return SkillResult(
                success=False,
                error=f"Parameter validation failed: {'; '.join(param_errors)}",
            )

        start_time = time.time()
        last_error = None

        # 2. Attempt execution with retries
        for attempt in range(self.max_retries):
            try:
                result = await self.execute(params)
                if not result.success:
                    last_error = result.error
                    if attempt < self.max_retries - 1:
                        import asyncio
                        await asyncio.sleep(2.0 ** attempt)
                    continue

                # 3. Validate output
                output_errors = self.validate_output(result.data)
                if output_errors:
                    last_error = f"Output validation: {'; '.join(output_errors)}"
                    if attempt < self.max_retries - 1:
                        import asyncio
                        await asyncio.sleep(2.0 ** attempt)
                    continue

                # Success!
                result.metadata["latency_seconds"] = time.time() - start_time
                result.metadata["retries"] = attempt
                return result

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2.0 ** attempt)

        # 4. All retries exhausted — use fallback
        fallback_result = self.fallback(params)
        fallback_result.metadata["latency_seconds"] = time.time() - start_time
        fallback_result.metadata["retries"] = self.max_retries
        fallback_result.metadata["fallback_reason"] = last_error
        # P0-3: Explicitly mark fallback so callers can distinguish real
        # success from degraded data. Previously this was indistinguishable
        # from a genuine success, causing silent production of stub videos.
        fallback_result.metadata["is_fallback"] = True
        return fallback_result
