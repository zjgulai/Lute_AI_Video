#!/usr/bin/env python3
"""Dry-run thumbnail coverage reporter for portfolio video assets.

This script only scans OUTPUT_DIR and existing poster files. It never calls
ffmpeg, never creates poster directories, and never triggers provider work.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import OUTPUT_DIR
from src.routers import portfolio

VIDEO_EXTS = {".mp4", ".mov", ".webm"}
MIN_VIDEO_BYTES = 1024 * 1024
COVERAGE_CATEGORIES = {
    "renders",
    "fast_mode",
    "seedance",
    "keyframes",
    "demo",
    "quality-test",
    "uploads",
    "assets",
}


def _empty_bucket() -> dict[str, Any]:
    return {
        "total_videos": 0,
        "with_thumbnail": 0,
        "missing_thumbnail": 0,
        "coverage_pct": 100.0,
    }


def _finish_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    total = int(bucket["total_videos"])
    with_thumbnail = int(bucket["with_thumbnail"])
    bucket["missing_thumbnail"] = total - with_thumbnail
    bucket["coverage_pct"] = round((with_thumbnail / total) * 100, 2) if total else 100.0
    return bucket


def _poster_path_for(output_dir: Path, rel_path: str) -> Path:
    flat = rel_path.replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    return output_dir / "thumbnails" / "portfolio_posters" / flat


def _iter_portfolio_videos(output_dir: Path):
    for subdir_name, (category, _source) in portfolio.CATEGORIES.items():
        if category not in COVERAGE_CATEGORIES:
            continue
        subdir = output_dir / subdir_name
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size <= MIN_VIDEO_BYTES:
                continue
            mime = portfolio._guess_mime(path.suffix.lower())
            kind = portfolio._derive_kind(category, mime)
            rel = path.relative_to(output_dir).as_posix()
            yield {
                "path": rel,
                "category": category,
                "kind": kind,
                "size_bytes": size,
                "poster_path": _poster_path_for(output_dir, rel),
            }


def build_thumbnail_coverage_report(*, output_dir: str | Path = OUTPUT_DIR, missing_limit: int = 50) -> dict[str, Any]:
    output = Path(output_dir)
    by_kind: defaultdict[str, dict[str, Any]] = defaultdict(_empty_bucket)
    by_category: defaultdict[str, dict[str, Any]] = defaultdict(_empty_bucket)
    missing: list[dict[str, Any]] = []
    total = 0
    with_thumbnail = 0

    for item in _iter_portfolio_videos(output):
        total += 1
        kind = str(item["kind"])
        category = str(item["category"])
        poster_exists = Path(item["poster_path"]).is_file()
        by_kind[kind]["total_videos"] += 1
        by_category[category]["total_videos"] += 1
        if poster_exists:
            with_thumbnail += 1
            by_kind[kind]["with_thumbnail"] += 1
            by_category[category]["with_thumbnail"] += 1
        elif len(missing) < missing_limit:
            missing.append({
                "path": item["path"],
                "category": category,
                "kind": kind,
                "expected_thumbnail_path": Path(item["poster_path"]).relative_to(output).as_posix(),
                "size_bytes": item["size_bytes"],
            })

    return {
        "dry_run": True,
        "output_dir": str(output),
        "total_videos": total,
        "with_thumbnail": with_thumbnail,
        "missing_thumbnail": total - with_thumbnail,
        "coverage_pct": round((with_thumbnail / total) * 100, 2) if total else 100.0,
        "by_kind": {key: _finish_bucket(value) for key, value in sorted(by_kind.items())},
        "by_category": {key: _finish_bucket(value) for key, value in sorted(by_category.items())},
        "missing": missing,
        "missing_truncated": max(0, total - with_thumbnail - len(missing)),
    }


def format_text_report(report: dict[str, Any]) -> str:
    lines = [
        "Portfolio thumbnail coverage dry-run",
        "-" * 40,
        f"OUTPUT_DIR       : {report['output_dir']}",
        "MODE             : DRY RUN (no thumbnails generated)",
        f"TOTAL VIDEOS     : {report['total_videos']}",
        f"WITH THUMBNAIL   : {report['with_thumbnail']}",
        f"MISSING THUMBNAIL: {report['missing_thumbnail']}",
        f"COVERAGE         : {report['coverage_pct']}%",
        "",
        "By kind:",
    ]
    for key, bucket in report["by_kind"].items():
        lines.append(
            f"  {key:22s} {bucket['with_thumbnail']:4d}/{bucket['total_videos']:<4d} "
            f"{bucket['coverage_pct']:6.2f}%"
        )
    if report["missing"]:
        lines.extend(["", "Missing examples:"])
        for item in report["missing"]:
            lines.append(f"  - {item['path']} -> {item['expected_thumbnail_path']}")
    if report["missing_truncated"]:
        lines.append(f"  ... {report['missing_truncated']} more omitted")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run portfolio thumbnail coverage reporter")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Path to OUTPUT_DIR")
    parser.add_argument("--format", choices={"text", "json"}, default="text")
    parser.add_argument("--missing-limit", type=int, default=50)
    parser.add_argument("--min-coverage", type=float, default=None, help="Fail with exit 2 below this percent")
    args = parser.parse_args(argv)

    report = build_thumbnail_coverage_report(output_dir=args.output_dir, missing_limit=max(0, args.missing_limit))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text_report(report))

    if args.min_coverage is not None and float(report["coverage_pct"]) < args.min_coverage:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
