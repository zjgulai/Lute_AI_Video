"""Scan output/ and emit assets/portfolio/index.json.

闭环测试中通过真实外部 API 跑出来的 mp4 / mp3 / png / wav 都是付费产物,作为
作品集 + 数据资产保留。这个脚本扫描 output/ 下所有媒体文件,生成可程序化读取
的索引(scenario / label / category / 时间戳 / 大小 / 关联 pipeline state)。

设计文档:drafts/analysis/portfolio-mechanism-design-draft-20260504.md

Usage:
    python scripts/portfolio_index.py            # full scan + write index.json
    python scripts/portfolio_index.py --quiet    # silent unless error
    python scripts/portfolio_index.py --check    # rebuild + diff against existing

也可以从 Python 调用:
    from scripts.portfolio_index import rebuild_index
    rebuild_index()
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
PIPELINE_STATES_DIR = OUTPUT_DIR / "pipeline_states"
PORTFOLIO_DIR = PROJECT_ROOT / "assets" / "portfolio"
INDEX_PATH = PORTFOLIO_DIR / "index.json"

SCHEMA_VERSION = "1.0"

# 只索引"已生成的真实媒体" —— pipeline_states/*.json 是过程数据,不入索引(用作
# linked_state 反查源)。.db / 一次性元数据 json 同样跳过。
MEDIA_EXTS = {".mp4", ".mp3", ".wav", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif"}

# subdir → (category, source-skill identifier)
CATEGORIES: dict[str, tuple[str, str]] = {
    "renders": ("renders", "remotion_assemble"),
    "seedance": ("seedance", "seedance_video_generate"),
    "gpt_images": ("gpt_images", "poyo_image_generate"),
    "audio": ("audio", "tts_synthesis"),
    "fast_mode": ("fast_mode", "fast_mode_pipeline"),
    "keyframes": ("keyframes", "keyframe_extract"),
    "character_identity": ("character_identity", "character_identity"),
    "quality-test": ("quality-test", "quality_test"),
    "demo": ("demo", "demo"),
    "assets": ("assets", "asset_storage"),
    "thumbnails": ("thumbnails", "thumbnail_generate"),
    "uploads": ("uploads", "user_uploads"),
}

# scenario_label 识别 "s1_1777208949" / "s3_xxx" 这种命名;seedance 单片段类似
# "seedance_2PZLYNR0_f932.mp4" 不带 scenario,scenario / label 留 null。
LABEL_RE = re.compile(r"^(s\d)_(\d+)")


def _match_scenario_and_label(stem: str) -> tuple[str | None, str | None]:
    m = LABEL_RE.match(stem)
    if not m:
        return None, None
    scenario = m.group(1)
    label = f"{scenario}_{m.group(2)}"
    return scenario, label


def _linked_state(label: str | None) -> str | None:
    """返回 output/pipeline_states/<label>.json 相对路径,文件不存在则 None。"""
    if label is None:
        return None
    path = PIPELINE_STATES_DIR / f"{label}.json"
    if path.exists():
        return str(path.relative_to(PROJECT_ROOT))
    return None


def _produced_at(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC).isoformat(timespec="seconds")


def _scan_category(subdir: Path, category: str, source: str) -> list[dict[str, Any]]:
    if not subdir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(subdir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in MEDIA_EXTS:
            continue
        scenario, label = _match_scenario_and_label(path.stem)
        entries.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "category": category,
                "scenario": scenario,
                "label": label,
                "produced_at": _produced_at(path),
                "size_bytes": path.stat().st_size,
                "sha256": None,  # v1 不算,OSS 同步阶段再补
                "source": source,
                "linked_state": _linked_state(label),
            }
        )
    return entries


def build_index() -> dict[str, Any]:
    """Walk output/ and build the index dict (in-memory, no I/O write)."""
    files: list[dict[str, Any]] = []
    by_category: dict[str, dict[str, int]] = {}
    for subdir_name, (category, source) in CATEGORIES.items():
        subdir = OUTPUT_DIR / subdir_name
        cat_files = _scan_category(subdir, category, source)
        if not cat_files:
            continue
        files.extend(cat_files)
        by_category[category] = {
            "count": len(cat_files),
            "bytes": sum(f["size_bytes"] for f in cat_files),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "summary": {
            "total_files": len(files),
            "total_bytes": sum(f["size_bytes"] for f in files),
            "by_category": by_category,
        },
        "files": files,
    }


def write_index(index: dict[str, Any], path: Path | None = None) -> None:
    """原子写入 index.json,避免读到半截文件。

    path=None 时读取模块级 INDEX_PATH(允许测试 monkeypatch 注入)。
    """
    if path is None:
        path = INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def rebuild_index() -> dict[str, Any]:
    """Build + persist portfolio index. Returns the written index dict.

    Idempotent. Safe to call from webhook handlers, atexit, or CLI.
    """
    index = build_index()
    write_index(index)
    summary = index["summary"]
    logger.info(
        "portfolio: rebuilt index — %d files, %.1f MB → %s",
        summary["total_files"],
        summary["total_bytes"] / 1024 / 1024,
        INDEX_PATH.relative_to(PROJECT_ROOT) if INDEX_PATH.is_relative_to(PROJECT_ROOT) else INDEX_PATH,
    )
    return index


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build assets/portfolio/index.json from output/")
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出 warning+ 级别")
    parser.add_argument(
        "--check",
        action="store_true",
        help="构建索引但不覆盖磁盘文件;打印新旧 summary 差异(用于 CI)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
    )

    if args.check:
        new_index = build_index()
        if INDEX_PATH.exists():
            old_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            old_summary = old_index.get("summary", {})
            new_summary = new_index["summary"]
            print(
                f"old: {old_summary.get('total_files')} files / "
                f"{old_summary.get('total_bytes', 0) / 1024 / 1024:.1f} MB"
            )
            print(
                f"new: {new_summary['total_files']} files / "
                f"{new_summary['total_bytes'] / 1024 / 1024:.1f} MB"
            )
            return 0 if old_summary.get("total_files") == new_summary["total_files"] else 1
        print(f"new: {new_index['summary']['total_files']} files (no existing index)")
        return 1

    rebuild_index()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
