"""Guard the Phase C production non-token E2E readiness runner."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "production_non_token_e2e_check.py"
DEMO_KEY = "ai_video_demo_2026"

ENV_KEYS = {
    "API_KEY",
    "PLAYWRIGHT_API_KEY",
    "PLAYWRIGHT_PROD_URL",
    "RUN_TOKEN_SMOKE",
}


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
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


def test_dry_run_blocks_missing_playwright_key_without_running_playwright():
    result = _run_script()

    assert result.returncode == 0
    assert "Ready for Phase C execution: false" in result.stdout
    assert "playwright_api_key: block" in result.stdout
    assert "Running Phase C" not in result.stdout
    assert "RUN_TOKEN_SMOKE=0" in result.stdout
    assert "PLAYWRIGHT_API_KEY=<non-demo-production-key>" in result.stdout


def test_json_report_rejects_demo_key_and_token_smoke_enabled():
    result = _run_script(
        "--json",
        env={
            "RUN_TOKEN_SMOKE": "1",
            "PLAYWRIGHT_API_KEY": DEMO_KEY,
        },
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["blocked"] is True
    assert report["provider_call_allowed"] is False
    assert report["token_smoke_allowed"] is False
    assert {check["name"]: check["status"] for check in report["checks"]}["run_token_smoke_disabled"] == "block"
    assert {check["name"]: check["status"] for check in report["checks"]}["playwright_api_key"] == "block"


def test_execute_refuses_to_run_when_blocked():
    result = _run_script("--execute")

    assert result.returncode == 2
    assert "blocked; not running Playwright" in result.stderr
    assert "Running Phase C" not in result.stdout


def test_execute_uses_fake_npm_with_run_token_smoke_forced_to_zero(tmp_path: Path):
    npm_log = tmp_path / "npm-env.json"
    fake_npm = tmp_path / "npm"
    fake_npm.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['PHASE_C_FAKE_NPM_LOG']).write_text(json.dumps({\n"
        "  'argv': sys.argv,\n"
        "  'cwd': os.getcwd(),\n"
        "  'RUN_TOKEN_SMOKE': os.environ.get('RUN_TOKEN_SMOKE'),\n"
        "  'PLAYWRIGHT_PROD_URL': os.environ.get('PLAYWRIGHT_PROD_URL'),\n"
        "  'PLAYWRIGHT_API_KEY_PRESENT': bool(os.environ.get('PLAYWRIGHT_API_KEY')),\n"
        "}))\n"
    )
    fake_npm.chmod(fake_npm.stat().st_mode | stat.S_IXUSR)

    result = _run_script(
        "--execute",
        "--base-url",
        "https://video.lute-tlz-dddd.top",
        env={
            "PLAYWRIGHT_API_KEY": "prod-api-key",
            "RUN_TOKEN_SMOKE": "0",
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "PHASE_C_FAKE_NPM_LOG": str(npm_log),
        },
    )

    assert result.returncode == 0
    assert "Running Phase C production non-token E2E" in result.stdout
    payload = json.loads(npm_log.read_text())
    assert payload["argv"] == [str(fake_npm), "run", "e2e:prod"]
    assert payload["cwd"] == str(REPO_ROOT / "web")
    assert payload["RUN_TOKEN_SMOKE"] == "0"
    assert payload["PLAYWRIGHT_PROD_URL"] == "https://video.lute-tlz-dddd.top"
    assert payload["PLAYWRIGHT_API_KEY_PRESENT"] is True


def test_source_has_no_provider_or_token_smoke_execution_path():
    source = SCRIPT.read_text()

    assert "POYO_API_KEY" not in source
    assert "DEEPSEEK_API_KEY" not in source
    assert "SILICONFLOW_API_KEY" not in source
    assert "RUN_TOKEN_SMOKE=1" not in source
    assert "npm run e2e:prod" in source
    assert "env[TOKEN_SMOKE_ENV] = \"0\"" in source
