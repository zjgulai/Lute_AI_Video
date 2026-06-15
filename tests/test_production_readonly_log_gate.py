"""Guard the production read-only backend log gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "production_readonly_log_gate.py"


def _write_summary(path: Path, **overrides: object) -> None:
    payload = {
        "stamp": "unit",
        "playwright_exit": 0,
        "scenario_submit_count": 0,
        "fast_submit_count": 0,
        "provider_submit_count": 0,
        "media_generation_count": 0,
        "publish_count": 0,
        "non_get_count": 0,
        "admin_session_count": 0,
        "media_get_count": 0,
        "delivery_count": 0,
        "delivery_acceptance_count": 0,
        "approved_brand_token_write_count": 0,
        "final_work_match_count": 0,
        "final_work_write_count": 0,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_gate(tmp_path: Path, backend_log: str, **summary_overrides: object) -> subprocess.CompletedProcess[str]:
    backend_path = tmp_path / "backend.log"
    summary_path = tmp_path / "summary.json"
    output_path = tmp_path / "report.json"
    backend_path.write_text(backend_log, encoding="utf-8")
    _write_summary(summary_path, **summary_overrides)

    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--backend-log",
            str(backend_path),
            "--summary",
            str(summary_path),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_allows_portfolio_gets_and_local_health_noise(tmp_path: Path):
    result = _run_gate(
        tmp_path,
        "\n".join(
            [
                "GET /portfolio/ \u2192 200 (13ms)",
                'INFO:     172.20.0.3:60404 - "GET /portfolio/?kind=creation_intermediate HTTP/1.1" 200 OK',
                'INFO:     172.20.0.3:60404 - "GET /portfolio/?kind=final_work&limit=500 HTTP/1.1" 200 OK',
                'HTTP Request: GET http://rendering:3001/health "HTTP/1.1 200 OK"',
                "PG: all 6 required tables verified",
                "GET /health \u2192 200 (577ms)",
                'INFO:     127.0.0.1:45754 - "GET /health HTTP/1.1" 200 OK',
            ]
        ),
        forbidden_endpoint_count=3,
        health_get_count=3,
    )

    assert result.returncode == 0
    assert "PRODUCTION_READONLY_LOG_GATE_DECISION=pass" in result.stdout
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["readonly_line_count"] == 3
    assert report["local_health_noise_count"] == 3
    assert report["external_forbidden_count"] == 0
    assert report["legacy_summary_forbidden_endpoint_count_ignored"] is True


def test_blocks_external_health_from_browser_or_proxy(tmp_path: Path):
    result = _run_gate(
        tmp_path,
        "\n".join(
            [
                "GET /portfolio/ \u2192 200 (13ms)",
                'INFO:     172.20.0.3:60404 - "GET /health HTTP/1.1" 200 OK',
            ]
        ),
    )

    assert result.returncode == 20
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["decision"] == "fail"
    assert report["forbidden"][0]["reason"] == "external_forbidden_endpoint"


def test_blocks_provider_generation_and_mutating_summary(tmp_path: Path):
    result = _run_gate(
        tmp_path,
        "\n".join(
            [
                "GET /portfolio/ \u2192 200 (13ms)",
                "poyo: submitting task seedance-2",
            ]
        ),
        scenario_submit_count=1,
    )

    assert result.returncode == 20
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["decision"] == "fail"
    assert report["external_forbidden_count"] == 1
    assert report["summary_violations"] == [
        {
            "reason": "scenario_submit_count_non_zero",
            "value": 1,
        }
    ]


def test_blocks_readonly_summary_forbidden_counters_even_when_log_is_clean(tmp_path: Path):
    result = _run_gate(
        tmp_path,
        "\n".join(
            [
                "GET /portfolio/ \u2192 200 (13ms)",
                'INFO:     172.20.0.3:60404 - "GET /portfolio/?kind=creation_intermediate HTTP/1.1" 200 OK',
            ]
        ),
        admin_session_count=1,
        media_get_count=1,
        delivery_acceptance_count=1,
        approved_brand_token_write_count=1,
        final_work_match_count=1,
    )

    assert result.returncode == 20
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["decision"] == "fail"
    assert report["external_forbidden_count"] == 0
    assert report["summary_violations"] == [
        {
            "reason": "admin_session_count_non_zero",
            "value": 1,
        },
        {
            "reason": "media_get_count_non_zero",
            "value": 1,
        },
        {
            "reason": "delivery_acceptance_count_non_zero",
            "value": 1,
        },
        {
            "reason": "approved_brand_token_write_count_non_zero",
            "value": 1,
        },
        {
            "reason": "final_work_match_count_non_zero",
            "value": 1,
        },
    ]
