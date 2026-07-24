from __future__ import annotations

import importlib
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest

from scripts import w5_fast_one_shot_operator as operator
from src.operations.w5_fast_one_shot import OperatorBlocked

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "w5_fast_one_shot_operator.py"


class ExplodingStdin:
    def read(self, _size: int = -1) -> NoReturn:
        raise AssertionError("stdin must not be read while execute gate is disabled")


def test_submit_execute_gate_blocks_before_stdin_or_runtime_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(operator.EXECUTE_ENV, raising=False)
    monkeypatch.setattr(sys, "stdin", ExplodingStdin())
    monkeypatch.setattr(
        operator,
        "_load_authority",
        lambda _key: pytest.fail("runtime authority must not load"),
    )

    with pytest.raises(OperatorBlocked, match="w5_fast_execute_gate_disabled"):
        operator.submit()


def test_raw_key_reader_rejects_trailing_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("a" * 64 + "\nextra"))

    with pytest.raises(OperatorBlocked, match="w5_fast_transient_key_invalid"):
        operator._read_raw_key()


def test_dotenv_disablement_overrides_inherited_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "0")

    reloaded = importlib.reload(operator)

    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert reloaded.EXECUTE_ENV == "AI_VIDEO_W5_FAST_EXECUTE"


def test_evidence_path_must_be_absolute_distinct_and_private(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = (tmp_path / "private" / "plan", tmp_path / "private" / "a", tmp_path / "private" / "b")
    monkeypatch.delenv(operator.EVIDENCE_PATH_ENV, raising=False)
    with pytest.raises(OperatorBlocked, match="w5_fast_evidence_path_unavailable"):
        operator._evidence_store(paths)

    monkeypatch.setenv(operator.EVIDENCE_PATH_ENV, str(tmp_path / "private" / "evidence"))
    with pytest.raises(OperatorBlocked, match="w5_fast_evidence_path_invalid"):
        operator._evidence_store(paths)

    evidence = tmp_path / "persistent-evidence"
    monkeypatch.setenv(operator.EVIDENCE_PATH_ENV, str(evidence))
    store = operator._evidence_store(paths)
    assert store.path("safe.json").parent == evidence
    assert evidence.stat().st_mode & 0o777 == 0o700


def test_openapi_failure_precedes_marker_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(operator.EXECUTE_ENV, "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO("a" * 64))
    monkeypatch.setattr(
        operator,
        "_load_authority",
        lambda _key: ({"fixture": True}, object(), object()),
    )
    monkeypatch.setattr(
        operator,
        "_assert_contract",
        lambda _gateway: (_ for _ in ()).throw(
            OperatorBlocked("backend_route_contract_unavailable")
        ),
    )
    monkeypatch.setattr(
        operator,
        "_runtime_paths",
        lambda: (tmp_path / "plan", tmp_path / "activation", tmp_path / "binding"),
    )

    with pytest.raises(OperatorBlocked, match="backend_route_contract_unavailable"):
        operator.submit()

    assert not (tmp_path / "submit-invoked.json").exists()


def test_cli_disabled_submit_emits_only_stable_json() -> None:
    environment = dict(os.environ)
    environment.pop(operator.EXECUTE_ENV, None)
    result = subprocess.run(
        [str(SCRIPT), "submit"],
        cwd=REPO_ROOT,
        env=environment,
        input="secret-that-must-not-be-read",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == (
        '{"status": "blocked", '
        '"safe_error_code": "w5_fast_execute_gate_disabled"}'
    )
    assert "secret-that-must-not-be-read" not in result.stderr
