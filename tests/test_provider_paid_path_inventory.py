"""Task 8 paid-path inventory and legacy/provider readiness guards.

These tests are hermetic: provider constructors, sockets, and SDK clients are
forbidden.  A legacy path is acceptable only when it returns the stable
provider-cost block before constructing a client; no paid fallback is allowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from src.models.provider_cost import ProviderCostContractError

REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_legacy_blocked(exc_info: pytest.ExceptionInfo[ProviderCostContractError]) -> None:
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"


def test_dalle_client_blocks_before_http_client_construction(monkeypatch, tmp_path):
    from src.tools import dalle_client

    constructions = 0

    def forbidden_constructor(*_: Any, **__: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("DALL-E legacy client must not be constructed")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_constructor)
    with pytest.raises(ProviderCostContractError) as exc_info:
        dalle_client.DalleClient(api_key="legacy-openai-key", output_dir=tmp_path)

    _assert_legacy_blocked(exc_info)
    assert constructions == 0


@pytest.mark.asyncio
async def test_direct_openai_gpt_image_blocks_before_http_client_construction(
    monkeypatch,
    tmp_path,
):
    from src.tools.gpt_image_client import GPTImageClient

    constructions = 0

    def forbidden_constructor(*_: Any, **__: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("direct OpenAI image client must not be constructed")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_constructor)
    client = GPTImageClient(api_key="legacy-openai-key", output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.generate(prompt="legacy", image_id="legacy")

    _assert_legacy_blocked(exc_info)
    assert constructions == 0
    await client.close()


@pytest.mark.asyncio
async def test_poyo_music_and_lyrics_tts_are_tombstoned(monkeypatch, tmp_path):
    from src.tools import elevenlabs_client

    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no HTTP client")))
    client = elevenlabs_client.ElevenLabsClient(api_key="", output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client._poyo_synthesize("legacy music", "en")

    _assert_legacy_blocked(exc_info)
    await client.close()


def test_native_seedance_blocks_before_http_client_construction(monkeypatch, tmp_path):
    from src.tools import seedance_client

    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no HTTP client")))
    with pytest.raises(ProviderCostContractError) as exc_info:
        seedance_client.SeedanceClient(api_key="native-seedance-key", output_dir=tmp_path)

    _assert_legacy_blocked(exc_info)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "kimi", "anthropic", "unknown"])
async def test_unsupported_llm_provider_is_blocked_before_sdk_construction(monkeypatch, provider):
    from src.tools import llm_client

    monkeypatch.setattr(llm_client, "ChatOpenAI", lambda **_: (_ for _ in ()).throw(AssertionError("no SDK")))
    client = llm_client.LLMClient(provider=provider)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.ainvoke("system", "unsupported", model="claude-sonnet-4")

    assert exc_info.value.code == "provider_cost_rule_unavailable"


@pytest.mark.asyncio
async def test_admin_external_provider_health_is_readiness_only(monkeypatch):
    from src.routers.admin import logs
    from src.tools import llm_client

    def forbidden_llm(*_: Any, **__: Any) -> None:
        raise AssertionError("admin health must not construct an LLM client")

    def forbidden_http(*_: Any, **__: Any) -> None:
        raise AssertionError("admin health must not open a provider socket")

    monkeypatch.setattr(llm_client, "LLMClient", forbidden_llm)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden_http)

    for name in ("deepseek", "poyo", "siliconflow"):
        result = await logs._check_single_service(name)
        assert result["status"] == "disabled"
        assert result["reason"] == "external_provider_health_checks_disabled"
        assert result["service"] == name
        assert result["config_ready"] is False


def test_retired_cost_tracker_has_no_process_local_authority():
    source = (REPO_ROOT / "src/tools/cost_tracker.py").read_text(encoding="utf-8")
    for fragment in ("_records", "_UNIT_COSTS", "track(", "check_budget(", "set_thread_id(", "float"):
        assert fragment not in source

    from src.tools import cost_tracker

    for symbol in ("track", "check_budget", "set_thread_id", "BudgetExceededError"):
        with pytest.raises(ProviderCostContractError) as exc_info:
            getattr(cost_tracker, symbol)
        _assert_legacy_blocked(exc_info)


def test_provider_paid_path_inventory_has_no_legacy_runtime_edges():
    source_files = [path for path in (REPO_ROOT / "src").rglob("*.py") if "__pycache__" not in path.parts]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    assert "from src.tools.cost_tracker import" not in combined
    assert "import src.tools.cost_tracker" not in combined

    dalle_source = (REPO_ROOT / "src/tools/dalle_client.py").read_text(encoding="utf-8")
    eleven_source = (REPO_ROOT / "src/tools/elevenlabs_client.py").read_text(encoding="utf-8")
    poyo_source = (REPO_ROOT / "src/tools/poyo_client.py").read_text(encoding="utf-8")
    admin_source = (REPO_ROOT / "src/routers/admin/logs.py").read_text(encoding="utf-8")

    assert "retry_with_backoff" not in dalle_source
    assert "retry_with_backoff" not in eleven_source
    assert "provider_cost_legacy_path_blocked" in dalle_source
    assert "provider_cost_legacy_path_blocked" in eleven_source
    assert "provider_cost_legacy_path_blocked" in poyo_source
    assert "LLMClient" not in admin_source[admin_source.index("# System Health") :]
    assert "httpx.AsyncClient" not in admin_source[admin_source.index("# System Health") :]

    provider_tool_sources = {
        relative: (REPO_ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "src/tools/gpt_image_client.py",
            "src/tools/seedance_client.py",
            "src/tools/cosyvoice_client.py",
            "src/tools/poyo_client.py",
            "src/tools/llm_client.py",
        )
    }
    for relative, source in provider_tool_sources.items():
        assert "ProviderCostService" in source, relative
        assert "ProviderCostContractError" in source, relative
    assert "httpx.AsyncClient(" not in provider_tool_sources["src/tools/gpt_image_client.py"]
    assert "httpx.AsyncClient(" not in provider_tool_sources["src/tools/seedance_client.py"]
    assert "httpx.AsyncClient(" in provider_tool_sources["src/tools/cosyvoice_client.py"]
    assert "httpx.AsyncClient(" in provider_tool_sources["src/tools/poyo_client.py"]

    retry_users = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in source_files
        if "retry_with_backoff" in path.read_text(encoding="utf-8")
    }
    assert retry_users == {"src/tools/retry.py"}
    assert "_execute_with_retry" not in combined
    assert "submit_poll_download" in poyo_source


def test_cost_tracker_imports_are_not_reintroduced_in_step_runner_or_scenario():
    for relative in ("src/pipeline/step_runner.py", "src/routers/scenario.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "cost_tracker" not in source
