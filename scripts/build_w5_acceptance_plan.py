#!/usr/bin/env python3
"""Build a provider-off W5 acceptance plan draft without execution authority."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.w5_acceptance_harness import build_w5_plan_draft  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=("fast", "s1", "s2", "s3", "s4", "s5"))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--sample-ref", required=True)
    parser.add_argument("--budget-usd-nanos", required=True, type=int)
    parser.add_argument("--provider-job-caps", required=True, help="Exact JSON object of positive job caps.")
    parser.add_argument("--created-at", required=True, help="UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format.")
    parser.add_argument("--expires-at", required=True, help="UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format.")
    parser.add_argument(
        "--select-optional-media",
        action="append",
        default=[],
        choices=("tts_audio",),
        help="Select one scenario-supported optional media item.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON path under tmp/ or outside this repository.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing private draft.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def _parse_utc(value: str, name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DDTHH:MM:SSZ") from exc


def _pairs_to_unique_dict(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"provider job cap category is duplicated: {key}")
        result[key] = value
    return result


def _parse_caps(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value, object_pairs_hook=_pairs_to_unique_dict)
    except json.JSONDecodeError as exc:
        raise ValueError("provider job caps must be valid JSON") from exc
    if type(payload) is not dict:
        raise ValueError("provider job caps must be a JSON object")
    return payload


def _validate_output_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_root = REPO_ROOT.resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(repo_root) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("W5 plan draft output must be under tmp/ or outside the repository")
    if resolved.is_dir():
        raise ValueError("output target must be a file")
    return resolved


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    args = _parse_args()
    try:
        plan = build_w5_plan_draft(
            scenario=args.scenario,
            tenant_id=args.tenant_id,
            sample_ref=args.sample_ref,
            budget_limit_usd_nanos=args.budget_usd_nanos,
            provider_job_caps=_parse_caps(args.provider_job_caps),
            selected_optional_media=tuple(args.select_optional_media),
            created_at=_parse_utc(args.created_at, "created-at"),
            expires_at=_parse_utc(args.expires_at, "expires-at"),
        )
        payload = json.dumps(
            plan.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=True,
        )

        if args.output is None:
            print(payload)
            return 0

        output_path = _validate_output_path(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("ERROR: unable to write W5 plan draft", file=sys.stderr)
        return 2

    print(f"Wrote W5 non-authorizing plan draft: {_display_path(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
