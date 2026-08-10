"""Complete-worktree guard for non-W5 provider mutation entrypoints."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
W5_EXECUTOR = "scripts/w5_fast_one_shot_operator.py"
RETIRED_MARKER = "is retired and cannot execute"

MUTATION_SIGNAL = re.compile(
    r"(?:"
    r"requests\.(?:post|put|patch|delete)\s*\(|"
    r"httpx\.(?:post|put|patch|delete)\s*\(|"
    r"curl[^\n]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)|"
    r"\.submit_poll_download\s*\(|"
    r"await\s+[A-Za-z_][A-Za-z0-9_]*\.submit\s*\(|"
    r"\.text_to_video\s*\(|"
    r"\.synthesize(?:_script)?\s*\(|"
    r"\.generate(?:_variants)?\s*\(|"
    r"/fast/(?:submit|generate)|"
    r"/scenario/[A-Za-z0-9_{}-]+(?:/submit)?|"
    r"api\.poyo\.ai|"
    r"from\s+src\.tools\.(?:poyo_client|gpt_image_client|seedance_client|"
    r"elevenlabs_client|dalle_client|llm_client)\s+import|"
    r"--live\b"
    r")"
)

SHELL_SECRET_OUTPUT = re.compile(
    r"(?:echo|printf)[^\n]*(?:\$\{?[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET)|"
    r"\$[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET))"
)
PYTHON_SECRET_OUTPUT = re.compile(
    r"print\s*\([^\n]*(?:[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET))"
)


def _contract() -> dict[str, object]:
    return json.loads(
        (REPO_ROOT / "configs/scripts-governance-contract.json").read_text(
            encoding="utf-8"
        )
    )


def _worktree_scripts(root: Path = SCRIPTS_DIR) -> dict[str, str]:
    paths: dict[str, str] = {}
    for path in root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix not in {".py", ".sh"}
            or "__pycache__" in path.parts
        ):
            continue
        relative = str(Path("scripts") / path.relative_to(root))
        paths[relative] = path.read_text(encoding="utf-8")
    return paths


def _category_items(category: str) -> list[dict[str, str]]:
    items = _contract()[category]
    assert isinstance(items, list)
    return items


def test_every_worktree_script_has_one_governance_category() -> None:
    categories = (
        "active_reusable_scripts",
        "manual_deploy_scripts",
        "provider_probe_scripts",
        "legacy_one_off_scripts",
        "historical_e2e_scripts",
    )
    category_paths = [
        {item["path"] for item in _category_items(category)}
        for category in categories
    ]
    for index, paths in enumerate(category_paths):
        for other_paths in category_paths[index + 1 :]:
            assert paths.isdisjoint(other_paths)

    governed = set().union(*category_paths)
    assert governed == set(_worktree_scripts())


def test_w5_is_the_only_governed_provider_probe() -> None:
    provider_probes = _category_items("provider_probe_scripts")
    assert [item["path"] for item in provider_probes] == [W5_EXECUTOR]


def test_complete_worktree_mutation_inventory_has_only_w5() -> None:
    scripts = _worktree_scripts()
    mutation_paths = {
        relative for relative, source in scripts.items() if MUTATION_SIGNAL.search(source)
    }
    assert mutation_paths == {W5_EXECUTOR}

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "scripts/test_*.py" not in gitignore
    assert not list(SCRIPTS_DIR.rglob("test_*.py"))
    assert not list((SCRIPTS_DIR / "archive").glob("*.py"))

    policy = _contract()["policy"]
    assert isinstance(policy, dict)
    assert "tracked, untracked, ignored, and nested" in policy["notes"]


def test_filesystem_inventory_detects_ignored_nested_mutation_fixture(
    tmp_path: Path,
) -> None:
    scripts_root = tmp_path / "scripts"
    ignored_archive = scripts_root / "archive"
    ignored_archive.mkdir(parents=True)
    probe = ignored_archive / "hidden_provider_probe.py"
    probe.write_text(
        "import requests\nrequests.post('https://api.poyo.ai/api/generate/submit')\n",
        encoding="utf-8",
    )

    inventory = _worktree_scripts(scripts_root)
    assert set(inventory) == {"scripts/archive/hidden_provider_probe.py"}
    assert MUTATION_SIGNAL.search(inventory["scripts/archive/hidden_provider_probe.py"])


def test_retired_mutation_stubs_are_nonexecutable_and_fail_closed() -> None:
    scripts = _worktree_scripts()
    retired = {
        relative: source
        for relative, source in scripts.items()
        if RETIRED_MARKER in source
    }
    archived_paths = {
        item["path"]
        for item in _category_items("legacy_one_off_scripts")
        if item["status"] == "archive_candidate"
    }
    assert set(retired) == archived_paths

    hostile_env = os.environ.copy()
    hostile_env.update(
        {
            "RUN_TOKEN_SMOKE": "1",
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "CONFIRM_POYO_PROBE": "I_UNDERSTAND_THIS_MAY_CONSUME_CREDITS",
            "API_KEY": "sk_fixture_secret",
            "POYO_API_KEY": "sk_fixture_secret",
            "DEEPSEEK_API_KEY": "sk_fixture_secret",
            "SILICONFLOW_API_KEY": "sk_fixture_secret",
        }
    )
    for relative in sorted(archived_paths):
        source = retired[relative]
        path = REPO_ROOT / relative
        assert path.stat().st_mode & (
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        ) == 0
        assert not MUTATION_SIGNAL.search(source)
        interpreter = "bash" if path.suffix == ".sh" else sys.executable
        result = subprocess.run(
            [interpreter, str(path), "--execute"],
            cwd=REPO_ROOT,
            env=hostile_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert RETIRED_MARKER in result.stderr


def test_active_scripts_never_print_secret_values_or_prefixes() -> None:
    scripts = _worktree_scripts()
    for item in _category_items("active_reusable_scripts"):
        relative = item["path"]
        source = scripts[relative]
        assert not SHELL_SECRET_OUTPUT.search(source), relative
        assert not PYTHON_SECRET_OUTPUT.search(source), relative
        assert not re.search(
            r"\$\{?[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET):\d+", source
        ), relative

    start_backend = scripts["scripts/start_backend.sh"]
    assert "credential_state API_KEY" in start_backend
    assert "credential_state POYO_API_KEY" in start_backend
    assert "${API_KEY}" not in start_backend
    assert "$API_KEY" not in start_backend
