#!/usr/bin/env python3
"""Replay production backend logs for read-only Playwright regression gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ACCESS_RE = re.compile(
    r'INFO:\s+(?P<host>[^:\s]+):(?P<port>\d+)\s+-\s+"'
    r"(?P<method>[A-Z]+)\s+(?P<target>\S+)\s+HTTP/[^\" ]+\"\s+"
    r"(?P<status>\d+)"
)
SUMMARY_ENDPOINT_RE = re.compile(
    r"^(?P<method>[A-Z]+)\s+(?P<target>\S+)\s+\u2192\s+(?P<status>\d+)"
)
RENDERING_HEALTH_RE = re.compile(
    r'HTTP Request:\s+GET\s+http://rendering:3001/health\s+"HTTP/[^"]+\s+200\s+OK"'
)

SUMMARY_ZERO_COUNTERS = (
    "scenario_submit_count",
    "fast_submit_count",
    "provider_submit_count",
    "media_generation_count",
    "publish_count",
    "non_get_count",
    "admin_session_count",
    "media_get_count",
    "delivery_count",
    "delivery_acceptance_count",
    "approved_brand_token_write_count",
    "final_work_match_count",
    "final_work_write_count",
)

ALLOWED_READONLY_PATHS = {
    "/portfolio",
    "/portfolio/",
    "/api/portfolio",
    "/api/portfolio/",
}

FORBIDDEN_PATH_FRAGMENTS = (
    "/admin/auth/session",
    "/api/admin/auth/session",
    "/api/health",
    "/api/media",
    "/media",
    "/scenario",
    "/api/scenario",
    "/fast",
    "/api/fast",
    "/api/generate",
    "/generate/submit",
    "/pipeline",
    "/api/pipeline",
    "/distribution",
    "/api/distribution",
    "/publish",
    "/api/publish",
    "/delivery",
    "/api/delivery",
    "/approved_brand_token",
)

FORBIDDEN_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"api\.poyo\.ai",
        r"api\.siliconflow\.cn",
        r"poyo\s*:\s*submitting",
        r"poyo\s*:\s*task submitted",
        r"\bseedance\b",
        r"\btts\b",
        r"tts_audio",
        r"thumbnail_prompts",
        r"thumbnail_images",
        r"assemble_final",
        r"remotion_assemble",
        r"media_quality_audit",
        r"gate candidate",
        r"candidate generation",
        r"keyframe generation",
        r"final_work",
        r"approved_brand_token",
        r"delivery_accepted",
        r"publish_allowed",
    )
)


@dataclass
class LogClassification:
    readonly_access_count: int = 0
    readonly_summary_count: int = 0
    local_health_access_count: int = 0
    rendering_health_count: int = 0
    health_summary_count: int = 0
    pg_health_count: int = 0
    forbidden: list[dict[str, Any]] = field(default_factory=list)
    neutral: list[dict[str, Any]] = field(default_factory=list)

    @property
    def readonly_line_count(self) -> int:
        return self.readonly_access_count + self.readonly_summary_count

    @property
    def local_health_noise_count(self) -> int:
        return self.local_health_access_count + self.rendering_health_count + self.health_summary_count


def _record(line_number: int, reason: str, line: str) -> dict[str, Any]:
    return {
        "line_number": line_number,
        "reason": reason,
        "line": line,
    }


def _path_from_target(target: str) -> str:
    parsed = urlsplit(target)
    return parsed.path or target.split("?", 1)[0]


def _is_allowed_readonly_path(path: str) -> bool:
    return path in ALLOWED_READONLY_PATHS


def _is_forbidden_path(path: str) -> bool:
    return any(fragment in path for fragment in FORBIDDEN_PATH_FRAGMENTS)


def _forbidden_text_reason(line: str) -> str | None:
    for pattern in FORBIDDEN_TEXT_PATTERNS:
        if pattern.search(line):
            return pattern.pattern
    if line.startswith("HTTP Request:") and not RENDERING_HEALTH_RE.search(line):
        return "external_http_request"
    return None


def _summary_violations(summary: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if summary.get("playwright_exit") != 0:
        violations.append(
            {
                "reason": "playwright_exit_non_zero",
                "value": summary.get("playwright_exit"),
            }
        )

    for counter in SUMMARY_ZERO_COUNTERS:
        if summary.get(counter) != 0:
            violations.append(
                {
                    "reason": f"{counter}_non_zero",
                    "value": summary.get(counter),
                }
            )
    return violations


def classify_backend_log(text: str) -> LogClassification:
    classification = LogClassification()
    health_summaries: list[tuple[int, str]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if RENDERING_HEALTH_RE.search(line):
            classification.rendering_health_count += 1
            continue

        if line.startswith("PG: all ") and " required tables verified" in line:
            classification.pg_health_count += 1
            continue

        access_match = ACCESS_RE.search(line)
        if access_match:
            host = access_match.group("host")
            method = access_match.group("method")
            path = _path_from_target(access_match.group("target"))

            if host == "127.0.0.1" and method == "GET" and path == "/health":
                classification.local_health_access_count += 1
                continue

            if method != "GET":
                classification.forbidden.append(_record(line_number, "non_get_access", line))
                continue

            if _is_allowed_readonly_path(path):
                classification.readonly_access_count += 1
                continue

            if path == "/health" or _is_forbidden_path(path):
                classification.forbidden.append(_record(line_number, "external_forbidden_endpoint", line))
                continue

            classification.forbidden.append(_record(line_number, "external_unknown_get", line))
            continue

        summary_match = SUMMARY_ENDPOINT_RE.search(line)
        if summary_match:
            method = summary_match.group("method")
            path = _path_from_target(summary_match.group("target"))

            if method != "GET":
                classification.forbidden.append(_record(line_number, "non_get_summary_endpoint", line))
                continue

            if _is_allowed_readonly_path(path):
                classification.readonly_summary_count += 1
                continue

            if path == "/health":
                health_summaries.append((line_number, line))
                continue

            if _is_forbidden_path(path):
                classification.forbidden.append(_record(line_number, "forbidden_summary_endpoint", line))
                continue

            classification.forbidden.append(_record(line_number, "unknown_summary_endpoint", line))
            continue

        text_reason = _forbidden_text_reason(line)
        if text_reason:
            classification.forbidden.append(_record(line_number, text_reason, line))
            continue

        classification.neutral.append(_record(line_number, "neutral_unclassified", line))

    if classification.local_health_access_count or classification.rendering_health_count:
        classification.health_summary_count = len(health_summaries)
    else:
        for line_number, line in health_summaries:
            classification.forbidden.append(_record(line_number, "unattributed_health_summary", line))

    return classification


def build_report(backend_log: Path, summary_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    classification = classify_backend_log(backend_log.read_text(encoding="utf-8", errors="replace"))
    summary_failures = _summary_violations(summary)
    decision = "pass" if not classification.forbidden and not summary_failures else "fail"

    report: dict[str, Any] = {
        "decision": decision,
        "backend_log": str(backend_log.resolve()),
        "summary": str(summary_path.resolve()),
        "output": str(output_path.resolve()) if output_path else None,
        "playwright_exit": summary.get("playwright_exit"),
        "readonly_line_count": classification.readonly_line_count,
        "readonly_access_count": classification.readonly_access_count,
        "readonly_summary_count": classification.readonly_summary_count,
        "local_health_noise_count": classification.local_health_noise_count,
        "local_health_access_count": classification.local_health_access_count,
        "rendering_health_count": classification.rendering_health_count,
        "health_summary_count": classification.health_summary_count,
        "pg_health_count": classification.pg_health_count,
        "external_forbidden_count": len(classification.forbidden),
        "summary_violations_count": len(summary_failures),
        "summary_violations": summary_failures,
        "forbidden": classification.forbidden,
        "legacy_summary_forbidden_endpoint_count": summary.get("forbidden_endpoint_count"),
        "legacy_summary_health_get_count": summary.get("health_get_count"),
        "legacy_summary_forbidden_endpoint_count_ignored": True,
        "allowed_readonly_paths": sorted(ALLOWED_READONLY_PATHS),
        "notes": [
            "127.0.0.1 /health and rendering:3001/health are classified as local health noise.",
            "External browser/client health, admin session, media, scenario, fast, provider, publish, delivery, and approved brand token paths remain forbidden.",
        ],
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-log", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Print full report JSON to stdout.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.backend_log.is_file():
        print(f"PRODUCTION_READONLY_LOG_GATE_ERROR=missing_backend_log:{args.backend_log}", file=sys.stderr)
        return 2
    if not args.summary.is_file():
        print(f"PRODUCTION_READONLY_LOG_GATE_ERROR=missing_summary:{args.summary}", file=sys.stderr)
        return 2

    report = build_report(args.backend_log, args.summary, args.output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"PRODUCTION_READONLY_LOG_GATE_DECISION={report['decision']}")
        print(f"PRODUCTION_READONLY_LOG_GATE_EXTERNAL_FORBIDDEN_COUNT={report['external_forbidden_count']}")
        print(f"PRODUCTION_READONLY_LOG_GATE_LOCAL_HEALTH_NOISE_COUNT={report['local_health_noise_count']}")
        if report["output"]:
            print(f"PRODUCTION_READONLY_LOG_GATE_OUTPUT={report['output']}")
    return 0 if report["decision"] == "pass" else 20


if __name__ == "__main__":
    raise SystemExit(main())
