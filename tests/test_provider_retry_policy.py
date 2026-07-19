from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.models.provider_cost import ProviderCostContractError
from src.pipeline.generation_policy import (
    EffectiveGenerationPolicy,
    bind_effective_generation_policy,
)
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.tools.llm_client import LLMClient, LLMNotConfiguredError, _request_api_keys
from src.tools.retry import MaxRetriesExceededError, retry_with_backoff


def _bind_zero_retry_policy() -> None:
    bind_effective_generation_policy(
        EffectiveGenerationPolicy(
            tenant_id="tenant-a",
            scenario="s1",
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=0,
        )
    )


@pytest.mark.asyncio
async def test_retry_helper_caps_mutation_to_one_attempt_from_bound_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_zero_retry_policy()
    attempts = 0

    async def no_sleep(_: float) -> None:
        return None

    async def failing_transport() -> str:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("transient")

    monkeypatch.setattr("src.tools.retry.asyncio.sleep", no_sleep)
    with pytest.raises(MaxRetriesExceededError):
        await retry_with_backoff(failing_transport, max_retries=3)

    assert attempts == 1


class _FailingLLMTransport:
    def __init__(self) -> None:
        self.attempts = 0

    async def ainvoke(self, messages: list[Any]) -> Any:
        del messages
        self.attempts += 1
        raise ConnectionError("llm transport failed")


@pytest.mark.asyncio
async def test_bound_retry_policy_alone_cannot_authorize_llm_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_zero_retry_policy()
    transport = _FailingLLMTransport()
    client = LLMClient(provider="deepseek", timeout=1)
    monkeypatch.setattr(client, "_get_client", lambda model=None: transport)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.tools.retry.asyncio.sleep", no_sleep)

    with pytest.raises(LLMNotConfiguredError):
        await client.ainvoke("system", "user")

    assert transport.attempts == 0


class _LLMBackedSkill(SkillCallable):
    name = "task4-llm-backed-skill"
    max_retries = 3

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        del params
        data = await self.client.ainvoke("system", "user")
        return SkillResult(success=True, data={"text": data})

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        del params
        return []

    def validate_output(self, data: Any) -> list[str]:
        del data
        return []

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        del params
        return SkillResult(success=True, data={"text": "fallback"})


@pytest.mark.asyncio
async def test_skill_registry_outer_retry_cannot_authorize_llm_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_zero_retry_policy()
    transport = _FailingLLMTransport()
    client = LLMClient(provider="deepseek", timeout=1)
    monkeypatch.setattr(client, "_get_client", lambda model=None: transport)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.tools.retry.asyncio.sleep", no_sleep)
    registry = SkillRegistry()
    registry._skills[_LLMBackedSkill.name] = _LLMBackedSkill(client)

    key_token = _request_api_keys.set({"DEEPSEEK_API_KEY": "fixture-key-never-sent"})
    try:
        with pytest.raises(ProviderCostContractError) as exc_info:
            await registry.execute(_LLMBackedSkill.name, {})
    finally:
        _request_api_keys.reset(key_token)

    assert exc_info.value.code == "provider_execution_context_missing"
    assert transport.attempts == 0


@pytest.mark.asyncio
async def test_skill_callable_injects_bound_cap_without_mutating_caller() -> None:
    _bind_zero_retry_policy()
    seen: list[dict[str, Any]] = []

    class CapturingSkill(SkillCallable):
        name = "task4-capturing-skill"

        async def execute(self, params: dict[str, Any]) -> SkillResult:
            seen.append(dict(params))
            return SkillResult(success=True, data={"ok": True})

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            seen.append({"validated": params.get("provider_max_retries")})
            return []

        def validate_output(self, data: Any) -> list[str]:
            del data
            return []

        def fallback(self, params: dict[str, Any]) -> SkillResult:
            del params
            return SkillResult(success=True, data={"fallback": True})

    caller_params = {"provider_max_retries": 3, "nested": {"value": 1}}
    result = await CapturingSkill().safe_execute(caller_params)

    assert result.success is True
    assert seen[0]["validated"] == 0
    assert seen[1]["provider_max_retries"] == 0
    assert caller_params == {"provider_max_retries": 3, "nested": {"value": 1}}


@pytest.mark.asyncio
async def test_seedance_native_path_is_blocked_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools.seedance_client import SeedanceClient

    _bind_zero_retry_policy()
    del monkeypatch
    with pytest.raises(ProviderCostContractError) as exc_info:
        SeedanceClient(
            api_key="fixture-key-not-used",
            base_url="https://fixture.invalid",
            output_dir=tmp_path,
            max_retries=3,
        )
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"


@pytest.mark.parametrize("provider", ["openai", "deepseek", "kimi", "anthropic"])
def test_llm_sdk_client_construction_requires_durable_submission_permit(
    provider: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.tools import llm_client as llm_module

    captured: list[dict[str, Any]] = []

    class FakeSDKClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeSDKClient)

    with pytest.raises(ProviderCostContractError) as exc_info:
        LLMClient(provider=provider)._get_client()

    assert exc_info.value.code == "provider_execution_context_missing"
    assert captured == []


@pytest.mark.asyncio
async def test_gpt_image_native_path_is_blocked_before_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools.gpt_image_client import GPTImageClient

    _bind_zero_retry_policy()
    client = GPTImageClient(
        api_key="fixture-key-not-used",
        output_dir=tmp_path,
        max_retries=3,
    )
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.generate(prompt="fixture", image_id="task4")
    await client.close()
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"


@pytest.mark.asyncio
async def test_candidate_scorer_direct_vision_path_is_zero_network_tombstone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import candidate_scorer

    monkeypatch.setattr(
        "builtins.open",
        lambda *_args, **_kwargs: pytest.fail("blocked vision path must not read a local file"),
    )
    with pytest.raises(ProviderCostContractError) as exc_info:
        await candidate_scorer._llm_score_keyframe_image("/etc/hosts", "fixture prompt")
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"
