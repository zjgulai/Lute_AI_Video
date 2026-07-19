"""Static guard for the S1-S5 hermetic regression entrypoint."""

from __future__ import annotations

import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "s1-s5-hermetic-regression.md"
SCRIPT = REPO_ROOT / "scripts" / "run_s1_s5_hermetic_regression.sh"

REQUIRED_TEST_FILES = (
    "tests/test_s1_e2e.py",
    "tests/test_s2_e2e.py",
    "tests/test_s2_deprecated_shim_boundary.py",
    "tests/test_s3_e2e.py",
    "tests/test_s4_e2e.py",
    "tests/test_s5_e2e.py",
    "tests/test_gate_scenario_configs.py",
    "tests/test_scenario_step_regenerate_router.py",
    "tests/test_continuity_storyboard_grid.py",
    "tests/test_candidate_scorer_continuity.py",
    "tests/test_s1_continuity_pipeline.py",
    "tests/test_pipeline_degradation_chain.py",
    "tests/test_fault_injection.py",
)

REQUIRED_ENV_VALUES = {
    "DEEPSEEK_API_KEY": "",
    "POYO_API_KEY": "",
    "SEEDANCE_API_KEY": "",
    "SILICONFLOW_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "TIKTOK_ACCESS_TOKEN": "",
    "TIKTOK_PUBLISH_ENABLED": "false",
    "SHOPIFY_STORE_URL": "",
    "SHOPIFY_ACCESS_TOKEN": "",
    "SHOPIFY_PUBLISH_ENABLED": "false",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_KEY": "",
}

FORBIDDEN_TOKENS = (
    "RUN_TOKEN_SMOKE=1",
    "curl ",
    "PLAYWRIGHT_PROD_URL",
    "/api/fast/generate",
    "/api/fast/submit",
    "/api/scenario/",
    "https://video.lute-tlz-dddd.top",
)


def test_scenario_hermetic_script_is_executable_and_covers_s1_s5():
    script_text = SCRIPT.read_text()
    script_mode = SCRIPT.stat().st_mode

    assert script_mode & stat.S_IXUSR, "scenario hermetic regression script must be executable"
    assert "PYTEST_INCLUDE_HERMETIC_SLOW" in script_text
    assert '"$PYTHON_BIN" -m pytest' in script_text
    assert 'PYTHON_BIN="${PYTHON:-.venv/bin/python}"' in script_text

    for test_file in REQUIRED_TEST_FILES:
        assert test_file in script_text
        assert (REPO_ROOT / test_file).exists(), f"missing covered test file: {test_file}"


def test_scenario_hermetic_script_clears_external_credentials():
    script_text = SCRIPT.read_text()

    for env_var, value in REQUIRED_ENV_VALUES.items():
        assert f'export {env_var}="{value}"' in script_text

    for forbidden in FORBIDDEN_TOKENS:
        assert forbidden not in script_text


def test_makefile_and_runbook_point_to_scenario_hermetic_entrypoint():
    makefile = MAKEFILE.read_text()
    runbook = RUNBOOK.read_text()

    assert "test-hermetic-scenarios:" in makefile
    assert "bash scripts/run_s1_s5_hermetic_regression.sh" in makefile

    assert "make test-hermetic-scenarios" in runbook
    assert "scripts/run_s1_s5_hermetic_regression.sh" in runbook
    assert "Real generation remains P2 after POYO recharge" in runbook
