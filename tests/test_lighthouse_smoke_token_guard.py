"""Static guards for Lighthouse smoke scripts.

These tests intentionally avoid executing deploy scripts. They verify that
curl calls to token-consuming generation endpoints remain behind the explicit
RUN_TOKEN_SMOKE=1 opt-in gate.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
SMOKE_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "smoke.sh"

TOKEN_CONSUMING_ENDPOINTS = (
    "/api/fast/generate",
    "/api/fast/submit",
    "/api/scenario/",
    "/api/pipeline/start",
    "/gate/",
)

AUTH_REQUIRED_MUTATING_ENDPOINTS = (
    "/api/fast/generate",
    "/api/fast/submit",
    "/api/scenario/",
    "/api/pipeline/start",
)


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
            if "X-API-Key" not in line and any(
                endpoint in line for endpoint in AUTH_REQUIRED_MUTATING_ENDPOINTS
            ):
                continue
            calls.append(line)
    return calls


def test_lighthouse_smoke_scripts_use_explicit_token_smoke_gate():
    for script_path in (DEPLOY_SCRIPT, SMOKE_SCRIPT):
        text = script_path.read_text()

        assert "${RUN_TOKEN_SMOKE:-0}" in text
        assert 'RUN_TOKEN_SMOKE=1' in text
        assert _token_guard_spans(text), f"{script_path} must keep an explicit token smoke gate"


def test_token_consuming_curl_calls_are_only_inside_token_smoke_gate():
    for script_path in (DEPLOY_SCRIPT, SMOKE_SCRIPT):
        text = script_path.read_text()
        spans = _token_guard_spans(text)
        guarded_text = "\n".join(text[start:end] for start, end in spans)
        unguarded_text = _remove_spans(text, spans)

        assert _curl_calls_to_token_endpoints(guarded_text), (
            f"{script_path} should keep real generation smoke inside RUN_TOKEN_SMOKE=1"
        )
        assert _curl_calls_to_token_endpoints(unguarded_text) == []


def test_lighthouse_smoke_checks_toolbox_read_only_endpoints():
    text = SMOKE_SCRIPT.read_text()
    for endpoint in (
        "/api/toolbox/tools",
        "/api/toolbox/runs?limit=1",
        "/api/toolbox/runs/audit-summaries?limit=1",
    ):
        assert endpoint in text

    assert "L2-fixture-or-dry-run" in text

    mutating_toolbox_calls = [
        line
        for line in _join_line_continuations(text)
        if "/api/toolbox/" in line
        and any(method in line for method in ("-X POST", "-X PUT", "-X PATCH", "-X DELETE"))
    ]
    assert mutating_toolbox_calls == []
