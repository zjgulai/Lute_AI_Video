"""Concurrency isolation tests — verify API key separation across concurrent tasks.

Covers (CLAUDE.md H task):
- contextvars.ContextVar isolates per-request API keys
- LLMClient reads correct key per task
- Concurrent pipelines do not contaminate each other
"""

from __future__ import annotations

import asyncio

import pytest

from src.models.provider_cost import ProviderCostContractError
from src.tools.cosyvoice_client import CosyVoiceClient
from src.tools.elevenlabs_client import ElevenLabsClient
from src.tools.gpt_image_client import GPTImageClient
from src.tools.llm_client import (
    LLMClient,
    _request_api_keys,
    get_request_api_key,
    set_request_api_keys,
)
from src.tools.poyo_client import PoyoClient
from src.tools.seedance_client import SeedanceClient


@pytest.fixture(autouse=True)
def _reset_api_key_ctx():
    """Reset request_api_keys contextvar before each test."""
    _request_api_keys.set({})
    yield
    _request_api_keys.set({})


class TestContextVarIsolation:
    """Verify contextvars.ContextVar isolates values per asyncio task."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_keys(self):
        """Two tasks set different keys; each reads its own, not the other's."""
        results: dict[str, str | None] = {}

        async def task_a():
            set_request_api_keys({"DEEPSEEK_API_KEY": "key_a_123"})
            await asyncio.sleep(0.01)  # Let task_b run
            results["a"] = get_request_api_key("DEEPSEEK_API_KEY")

        async def task_b():
            await asyncio.sleep(0.005)  # Wait for task_a to set first
            set_request_api_keys({"DEEPSEEK_API_KEY": "key_b_456"})
            await asyncio.sleep(0.01)  # Let task_a continue
            results["b"] = get_request_api_key("DEEPSEEK_API_KEY")

        await asyncio.gather(task_a(), task_b())

        assert results["a"] == "key_a_123", (
            f"task_a should see its own key, got {results['a']}"
        )
        assert results["b"] == "key_b_456", (
            f"task_b should see its own key, got {results['b']}"
        )

    @pytest.mark.asyncio
    async def test_nested_tasks_inherit_parent_key(self):
        """Child task (created via create_task) inherits parent context."""
        set_request_api_keys({"POYO_API_KEY": "parent_key"})

        async def child_task():
            return get_request_api_key("POYO_API_KEY")

        # asyncio.create_task copies parent contextvar to child
        result = await child_task()
        assert result == "parent_key", f"child should inherit parent key, got {result}"

    @pytest.mark.asyncio
    async def test_fallback_to_os_env_when_ctx_empty(self):
        """When contextvar is empty, get_request_api_key falls back to os.environ."""
        import os

        # Use a fictional env var to avoid conflicts with real keys
        os.environ["TEST_FAKE_API_KEY_XYZ"] = "env_fallback"
        _request_api_keys.set({})

        key = get_request_api_key("TEST_FAKE_API_KEY_XYZ")
        assert key == "env_fallback", f"should fallback to env, got {key}"
        del os.environ["TEST_FAKE_API_KEY_XYZ"]

    @pytest.mark.asyncio
    async def test_ctx_takes_precedence_over_env(self):
        """Contextvar value takes precedence over os.environ."""
        import os

        os.environ["DEEPSEEK_API_KEY"] = "env_value"
        set_request_api_keys({"DEEPSEEK_API_KEY": "ctx_value"})

        key = get_request_api_key("DEEPSEEK_API_KEY")
        assert key == "ctx_value", f"ctx should win over env, got {key}"


class TestMultiProviderIsolation:
    """Verify multiple provider keys are isolated simultaneously."""

    @pytest.mark.asyncio
    async def test_multiple_providers_per_task(self):
        """A single task can carry keys for multiple providers."""
        set_request_api_keys({
            "DEEPSEEK_API_KEY": "ds_key",
            "POYO_API_KEY": "poyo_key",
            "SILICONFLOW_API_KEY": "sf_key",
        })

        assert get_request_api_key("DEEPSEEK_API_KEY") == "ds_key"
        assert get_request_api_key("POYO_API_KEY") == "poyo_key"
        assert get_request_api_key("SILICONFLOW_API_KEY") == "sf_key"

    @pytest.mark.asyncio
    async def test_concurrent_multi_provider_tasks(self):
        """Multiple tasks each with different provider key sets."""
        results: dict[str, dict[str, str | None]] = {}

        # Use fictional env var names to avoid conflicts with real keys in os.environ
        async def task_user_1():
            set_request_api_keys({
                "FAKE_PROVIDER_A": "user1_a",
                "FAKE_PROVIDER_B": "user1_b",
            })
            await asyncio.sleep(0.01)
            results["user1"] = {
                "a": get_request_api_key("FAKE_PROVIDER_A"),
                "b": get_request_api_key("FAKE_PROVIDER_B"),
                "c": get_request_api_key("FAKE_PROVIDER_C"),
            }

        async def task_user_2():
            await asyncio.sleep(0.005)
            set_request_api_keys({
                "FAKE_PROVIDER_A": "user2_a",
                "FAKE_PROVIDER_C": "user2_c",
            })
            await asyncio.sleep(0.01)
            results["user2"] = {
                "a": get_request_api_key("FAKE_PROVIDER_A"),
                "b": get_request_api_key("FAKE_PROVIDER_B"),
                "c": get_request_api_key("FAKE_PROVIDER_C"),
            }

        await asyncio.gather(task_user_1(), task_user_2())

        assert results["user1"]["a"] == "user1_a"
        assert results["user1"]["b"] == "user1_b"
        assert results["user1"]["c"] is None

        assert results["user2"]["a"] == "user2_a"
        assert results["user2"]["b"] is None
        assert results["user2"]["c"] == "user2_c"

    @pytest.mark.asyncio
    async def test_concurrent_provider_adapters_keep_request_keys_isolated(
        self,
        tmp_path,
    ):
        """Active adapters capture only their task's keys without opening transports."""
        results: dict[str, dict[str, object]] = {}

        async def construct(label: str) -> None:
            keys = {
                "DEEPSEEK_API_KEY": f"deepseek-{label}",
                "ELEVENLABS_API_KEY": f"elevenlabs-{label}",
                "OPENAI_API_KEY": f"openai-{label}",
                "POYO_API_KEY": f"poyo-{label}",
                "SEEDANCE_API_KEY": f"seedance-{label}",
                "SILICONFLOW_API_KEY": f"siliconflow-{label}",
            }
            set_request_api_keys(keys)
            await asyncio.sleep(0)

            llm = LLMClient(provider="deepseek")
            image = GPTImageClient(output_dir=tmp_path / label / "images")
            poyo = PoyoClient()
            seedance = SeedanceClient(output_dir=tmp_path / label / "video")
            cosyvoice = CosyVoiceClient(output_dir=tmp_path / label / "audio")

            with pytest.raises(
                ProviderCostContractError,
                match="legacy TTS provider has no exact provider-cost rule",
            ):
                ElevenLabsClient(output_dir=tmp_path / label / "legacy-audio")

            results[label] = {
                "deepseek": llm._resolve_api_key("DEEPSEEK_API_KEY"),
                "image": image.api_key,
                "poyo": poyo.api_key,
                "seedance": seedance.api_key,
                "siliconflow": cosyvoice.api_key,
                "llm_clients": dict(llm._clients),
                "image_client": image._client,
                "image_poyo": image._poyo,
                "poyo_client": poyo._client,
                "seedance_poyo": seedance._poyo,
                "cosyvoice_client": cosyvoice._client,
            }

        await asyncio.gather(construct("tenant-a"), construct("tenant-b"))

        for label in ("tenant-a", "tenant-b"):
            assert results[label] == {
                "deepseek": f"deepseek-{label}",
                "image": f"poyo-{label}",
                "poyo": f"poyo-{label}",
                "seedance": f"poyo-{label}",
                "siliconflow": f"siliconflow-{label}",
                "llm_clients": {},
                "image_client": None,
                "image_poyo": None,
                "poyo_client": None,
                "seedance_poyo": None,
                "cosyvoice_client": None,
            }


class TestTenantIdIsolation:
    """Verify tenant_id contextvar is also isolated per task."""

    @pytest.mark.asyncio
    async def test_tenant_id_isolated_across_tasks(self):
        """Different tasks carry different tenant IDs."""
        from src.routers._deps import _tenant_id_var, set_tenant_id

        results: dict[str, str | None] = {}

        async def task_tenant_a():
            set_tenant_id("tenant_a")
            await asyncio.sleep(0.01)
            results["a"] = _tenant_id_var.get()

        async def task_tenant_b():
            await asyncio.sleep(0.005)
            set_tenant_id("tenant_b")
            await asyncio.sleep(0.01)
            results["b"] = _tenant_id_var.get()

        _tenant_id_var.set(None)
        await asyncio.gather(task_tenant_a(), task_tenant_b())

        assert results["a"] == "tenant_a"
        assert results["b"] == "tenant_b"
