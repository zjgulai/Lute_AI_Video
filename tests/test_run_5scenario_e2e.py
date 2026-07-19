"""Gated execution contract for the 5-scenario production smoke script."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_5scenario_e2e.py"
DEMO_KEY = "ai_video_demo_2026"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_5scenario_e2e_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"API_KEY", "PLAYWRIGHT_API_KEY", "POYO_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"}
    }
    if env:
        clean_env.update(env)

    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_run_is_dry_run_and_only_prints_plan():
    result = _run_script()
    assert result.returncode == 0
    assert "5-scenario production smoke checker — DRY RUN" in result.stdout
    assert "No commands were executed." in result.stdout
    assert "Planned steps:" in result.stdout
    assert "FAST" in result.stdout
    assert "S1" in result.stdout
    assert "S5" in result.stdout
    assert "Run command:" in result.stdout
    assert "CONFIRM_P2_TOKEN_SMOKE=1" in result.stdout
    assert "RUN_TOKEN_SMOKE=1" in result.stdout


def test_execute_requires_confirmation_and_token_flags():
    base_env = {
        "API_KEY": "prod-api-key",
        "PLAYWRIGHT_API_KEY": "prod-api-key",
        "POYO_API_KEY": "poyo-key",
        "DEEPSEEK_API_KEY": "deepseek-key",
        "SILICONFLOW_API_KEY": "siliconflow-key",
    }

    missing_confirm = _run_script("--execute", env=base_env)
    assert missing_confirm.returncode == 2
    assert "CONFIRM_P2_TOKEN_SMOKE=1 is required" in missing_confirm.stderr

    missing_token = _run_script("--execute", env={**base_env, "CONFIRM_P2_TOKEN_SMOKE": "1"})
    assert missing_token.returncode == 2
    assert "RUN_TOKEN_SMOKE=1 is required" in missing_token.stderr


def test_execute_rejects_demo_key_values():
    env = {
        "CONFIRM_P2_TOKEN_SMOKE": "1",
        "RUN_TOKEN_SMOKE": "1",
        "API_KEY": DEMO_KEY,
        "PLAYWRIGHT_API_KEY": DEMO_KEY,
        "POYO_API_KEY": DEMO_KEY,
        "DEEPSEEK_API_KEY": DEMO_KEY,
        "SILICONFLOW_API_KEY": DEMO_KEY,
    }

    result = _run_script("--execute", env=env)
    assert result.returncode == 2
    assert "must be non-demo key, rejected demo key" in result.stderr


def test_selective_dry_run_respects_scenario_filter():
    result = _run_script("--scenario", "fast", "--scenario", "s2")
    assert result.returncode == 0
    assert "1. FAST" in result.stdout
    assert "2. S2" in result.stdout
    assert "S1" not in result.stdout
    assert "S3" not in result.stdout
    assert "S4" not in result.stdout
    assert "S5" not in result.stdout


def test_invalid_scenario_key_is_rejected_by_parser():
    result = _run_script("--scenario", "unknown")
    assert result.returncode == 2
    assert "invalid choice: 'unknown'" in result.stderr


def test_async_scenario_submit_uses_caller_owned_idempotency_key_once(monkeypatch):
    module = _load_script_module()
    post_calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> _Response:
        post_calls.append({"url": url, **kwargs})
        return _Response(200, {"label": "s1_fixture", "status": "queued"})

    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("readback is unnecessary")),
    )

    key = "scenario-smoke-s1-00000001"
    label = module.submit_scenario(
        api_base="https://example.invalid/api",
        scenario="s1",
        payload={"product_catalog": {}},
        api_key="fixture-api-key",
        idempotency_key=key,
        verify_ssl=True,
    )

    assert label == "s1_fixture"
    assert len(post_calls) == 1
    assert post_calls[0]["headers"]["Idempotency-Key"] == key


def test_ambiguous_submit_recovers_by_readback_without_second_post(monkeypatch):
    module = _load_script_module()
    post_headers: list[dict[str, str]] = []
    readback_headers: list[dict[str, str]] = []
    sleeps: list[float] = []
    readbacks = iter(
        [
            _Response(404, {"detail": {"code": "submission_not_found"}}),
            _Response(
                200,
                {
                    "resource_type": "scenario",
                    "resource_id": "s3_recovered",
                    "scenario": "s3",
                    "status": "queued",
                    "submit_response": {"label": "s3_recovered"},
                },
            ),
        ]
    )

    def fake_post(_url: str, **kwargs: Any) -> _Response:
        post_headers.append(kwargs["headers"])
        raise requests.Timeout("ambiguous fixture")

    def fake_get(_url: str, **kwargs: Any) -> _Response:
        readback_headers.append(kwargs["headers"])
        return next(readbacks)

    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    key = "scenario-smoke-s3-00000001"
    label = module.submit_scenario(
        api_base="https://example.invalid/api",
        scenario="s3",
        payload={"video_url": "https://example.invalid/video"},
        api_key="fixture-api-key",
        idempotency_key=key,
        verify_ssl=True,
    )

    assert label == "s3_recovered"
    assert len(post_headers) == 1
    assert post_headers[0]["Idempotency-Key"] == key
    assert [headers["Idempotency-Key"] for headers in readback_headers] == [key, key]
    assert sleeps == [1.0]
