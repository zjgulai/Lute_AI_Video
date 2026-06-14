from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_admin_health_skips_external_provider_probes_by_default(monkeypatch):
    from src import config
    from src.routers.admin import logs

    async with logs._health_lock:
        logs._health_history.clear()

    calls: list[str] = []

    async def fake_check(name: str) -> dict[str, object]:
        calls.append(name)
        return {"status": "healthy", "latency_ms": 1}

    monkeypatch.setattr(config, "ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED", False)
    monkeypatch.setattr(logs, "_check_single_service", fake_check)

    await logs.run_health_checks()

    assert calls == ["postgres", "remotion"]
    latest = logs._health_history[-1]
    services = latest["services"]
    assert services["postgres"]["status"] == "healthy"
    assert services["remotion"]["status"] == "healthy"
    for name in ("deepseek", "poyo", "siliconflow"):
        assert services[name]["status"] == "skipped"
        assert services[name]["reason"] == "external_provider_health_checks_disabled"


@pytest.mark.asyncio
async def test_admin_health_can_opt_in_to_external_provider_probes(monkeypatch):
    from src import config
    from src.routers.admin import logs

    async with logs._health_lock:
        logs._health_history.clear()

    calls: list[str] = []

    async def fake_check(name: str) -> dict[str, object]:
        calls.append(name)
        return {"status": "healthy", "latency_ms": 1}

    monkeypatch.setattr(config, "ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED", True)
    monkeypatch.setattr(logs, "_check_single_service", fake_check)

    await logs.run_health_checks()

    assert calls == ["postgres", "deepseek", "poyo", "siliconflow", "remotion"]
    services = logs._health_history[-1]["services"]
    assert all(services[name]["status"] == "healthy" for name in calls)
