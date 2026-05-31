"""Static guards for tracked poyo.ai probe scripts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

POYO_PROBE_SCRIPTS = (
    REPO_ROOT / "scripts" / "debug_poyo_403.py",
    REPO_ROOT / "scripts" / "diagnose_poyo.py",
    REPO_ROOT / "scripts" / "discover_poyo_models.py",
    REPO_ROOT / "scripts" / "probe_sora2pro.py",
)

DEFAULT_ENTRYPOINTS = (
    REPO_ROOT / "Makefile",
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "deploy.yml",
    REPO_ROOT / ".github" / "workflows" / "e2e-prod.yml",
    REPO_ROOT / "scripts" / "run_s1_s5_hermetic_regression.sh",
)


def test_poyo_probe_scripts_require_key_and_explicit_credit_confirmation():
    for script_path in POYO_PROBE_SCRIPTS:
        text = script_path.read_text()

        assert "POYO_API_KEY" in text
        assert "CONFIRM_POYO_PROBE" in text
        assert "may consume credits" in text
        assert "api.poyo.ai" in text or "PoyoClient" in text


def test_default_ci_make_and_hermetic_entrypoints_do_not_call_poyo_probes():
    probe_names = {path.name for path in POYO_PROBE_SCRIPTS}

    for entrypoint in DEFAULT_ENTRYPOINTS:
        text = entrypoint.read_text()
        for probe_name in probe_names:
            assert probe_name not in text, f"{entrypoint} must not run {probe_name} by default"


def test_poyo_diagnose_script_does_not_print_long_key_prefix():
    diagnose_text = (REPO_ROOT / "scripts" / "diagnose_poyo.py").read_text()
    probe_text = (REPO_ROOT / "scripts" / "probe_sora2pro.py").read_text()

    assert "POYO_API_KEY[:20]" not in diagnose_text
    assert "mask_key(POYO_API_KEY)" in diagnose_text
    assert "POYO_API_KEY[:12]" not in probe_text
    assert "mask_key(POYO_API_KEY)" in probe_text
