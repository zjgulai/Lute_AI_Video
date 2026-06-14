#!/usr/bin/env python3
"""Build a dry-run brand token review audit bundle."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "tmp" / "outputs"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(sys.stderr):
    from src.models.commercial_contracts import CandidateTokenLedger
    from src.pipeline.brand_review_audit_bundle import build_brand_review_audit_bundle
    from src.pipeline.brand_token_review import BrandTokenReviewDecision, apply_brand_token_review


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_json", help="Candidate ledger JSON, or full intake report JSON containing `ledger`.")
    parser.add_argument("--decisions", help="Optional review decisions JSON list or object with `decisions`.")
    parser.add_argument("--output", help="Optional report filename; writes under tmp/outputs/.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def _load_ledger(path: str | Path) -> CandidateTokenLedger:
    payload = _read_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("ledger"), dict):
        payload = payload["ledger"]
    return CandidateTokenLedger.model_validate(payload)


def _load_decisions(path: str | Path | None) -> list[BrandTokenReviewDecision]:
    if path is None:
        return []
    payload = _read_json(path)
    if isinstance(payload, dict):
        payload = payload.get("decisions", [])
    if not isinstance(payload, list):
        raise ValueError("review decisions JSON must be a list or contain a decisions list")
    return [BrandTokenReviewDecision.model_validate(item) for item in payload]


def _resolve_output_path(raw_output: str) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    requested = Path(raw_output)
    if requested.is_absolute():
        return OUTPUT_ROOT / requested.name
    if requested.parts[:2] == ("tmp", "outputs"):
        return REPO_ROOT / requested
    return OUTPUT_ROOT / requested.name


def main() -> int:
    args = _parse_args()
    ledger = _load_ledger(args.ledger_json)
    decisions = _load_decisions(args.decisions)
    review_report = apply_brand_token_review(ledger, decisions) if decisions else None
    audit_bundle = build_brand_review_audit_bundle(ledger, review_report=review_report)
    text = json.dumps(audit_bundle.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None)

    if args.output:
        output_path = _resolve_output_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text)

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
