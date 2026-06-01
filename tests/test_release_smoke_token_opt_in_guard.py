"""Static guard for release smoke token-consuming endpoints."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SMOKE_SCRIPT = REPO_ROOT / "scripts" / "release_smoke_v0.4.0.sh"
CONTRACT_PATH = REPO_ROOT / "configs" / "release-smoke-token-opt-in-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "release-smoke-token-opt-in.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

TOKEN_CONSUMING_ENDPOINTS = (
    "/api/fast/generate",
    "/api/fast/submit",
    "/api/scenario/",
    "/api/pipeline/start",
    "/gate/",
)


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "release smoke token opt-in contract is missing"
    data = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "release smoke token opt-in contract must be a JSON object"
    return data


def _join_line_continuations(text: str) -> list[str]:
    logical_lines: list[str] = []
    pending = ""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue

        logical_lines.append((pending + stripped).strip())
        pending = ""

    if pending:
        logical_lines.append(pending.strip())

    return logical_lines


def _token_guard_spans(text: str) -> list[tuple[int, int]]:
    pattern = re.compile(
        r'if \[ "\$\{RUN_TOKEN_SMOKE:-0\}" = "1" \]; then.*?(?:^else$.*?^fi$|^fi$)',
        re.MULTILINE | re.DOTALL,
    )
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    output = []
    cursor = 0
    for start, end in spans:
        output.append(text[cursor:start])
        cursor = end
    output.append(text[cursor:])
    return "".join(output)


def _curl_calls_to_token_endpoints(text: str) -> list[str]:
    calls = []
    for line in _join_line_continuations(text):
        if "curl" not in line and "$CURL" not in line:
            continue
        if any(endpoint in line for endpoint in TOKEN_CONSUMING_ENDPOINTS):
            calls.append(line)
    return calls


def _scope_targets() -> set[str]:
    return {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_release_smoke_script_keeps_generation_curls_inside_token_gate() -> None:
    text = RELEASE_SMOKE_SCRIPT.read_text()
    spans = _token_guard_spans(text)
    guarded_text = "\n".join(text[start:end] for start, end in spans)
    unguarded_text = _remove_spans(text, spans)

    assert "${RUN_TOKEN_SMOKE:-0}" in text
    assert "RUN_TOKEN_SMOKE=1" in text
    assert spans, "release smoke must keep an explicit RUN_TOKEN_SMOKE=1 gate"
    assert _curl_calls_to_token_endpoints(guarded_text), (
        "release smoke should keep any generation probe inside RUN_TOKEN_SMOKE=1"
    )
    assert _curl_calls_to_token_endpoints(unguarded_text) == []


def test_release_smoke_token_opt_in_contract_is_machine_readable() -> None:
    contract = _contract()

    assert contract["status"] == "stable"
    assert contract["script"] == "scripts/release_smoke_v0.4.0.sh"
    assert contract["runbook"] == "docs/runbooks/release-smoke-token-opt-in.md"
    assert contract["default_token_smoke"] == "disabled"
    assert contract["opt_in_env"] == "RUN_TOKEN_SMOKE=1"
    assert contract["no_token_boundary"] is True
    assert contract["token_consuming_endpoints"] == list(TOKEN_CONSUMING_ENDPOINTS)

    for endpoint in contract["token_consuming_endpoints"]:
        assert endpoint in TOKEN_CONSUMING_ENDPOINTS


def test_release_smoke_runbook_documents_default_skip_and_recharge_boundary() -> None:
    contract = _contract()
    runbook_text = RUNBOOK_PATH.read_text()

    assert "release-smoke-token-opt-in-contract.json" in runbook_text
    assert contract["script"] in runbook_text
    assert "tests/test_release_smoke_token_opt_in_guard.py" in runbook_text
    assert "RUN_TOKEN_SMOKE=1" in runbook_text
    assert "默认跳过" in runbook_text
    assert "充值后" in runbook_text
    assert "/api/fast/generate" in runbook_text


def test_release_smoke_runbook_is_in_docs_link_scope_and_ci() -> None:
    scope_targets = _scope_targets()
    ci_text = CI_PATH.read_text()

    assert "docs/runbooks/release-smoke-token-opt-in.md" in scope_targets
    assert "docs/runbooks/release-smoke-token-opt-in.md" in ci_text
