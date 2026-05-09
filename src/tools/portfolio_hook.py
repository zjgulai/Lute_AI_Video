"""Portfolio index auto-rebuild hook.

闭环测试结束后(LangGraph `pipeline.completed` 事件触发时)自动重建 portfolio
索引。把扫描放到 threadpool 里跑,不阻塞 asyncio 事件循环。

Hook 注册见 `src/api.py` startup;手动重建用 `make portfolio` 或
`python scripts/portfolio_index.py`。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

_MEDIA_EXTS = {".mp4", ".mov", ".webm"}
_THUMB_CATEGORIES = [
    "renders",
    "seedance",
    "fast_mode",
    "keyframes",
    "demo",
    "quality-test",
]
_POSTER_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"


def _poster_path(rel: str) -> Path:
    flat = rel.replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    return _POSTER_DIR / flat


def _extract_poster(source: Path, dest: Path) -> bool:
    """Use ffmpeg to grab a single frame at 2 s, scale to 480 px wide."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", "00:00:02",
                "-i", str(source),
                "-vframes", "1",
                "-vf", "scale=480:-2",
                "-q:v", "3",
                str(dest),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return dest.is_file()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False


def _ensure_thumbnails() -> dict[str, int]:
    """Generate missing poster JPEGs for video files in OUTPUT_DIR.

    Called automatically after portfolio index rebuild so new pipeline outputs
    always have a visible poster in gallery UIs.
    """
    stats = {"created": 0, "skipped": 0, "failed": 0}
    if not shutil.which("ffmpeg"):
        logger.warning("thumbnail: ffmpeg not found, skipping poster generation")
        return stats

    _POSTER_DIR.mkdir(parents=True, exist_ok=True)

    for cat in _THUMB_CATEGORIES:
        subdir = OUTPUT_DIR / cat
        if not subdir.is_dir():
            continue
        for path in subdir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _MEDIA_EXTS:
                continue
            rel = path.relative_to(OUTPUT_DIR)
            poster = _poster_path(str(rel))
            src_mtime = path.stat().st_mtime
            if poster.is_file() and poster.stat().st_mtime >= src_mtime:
                stats["skipped"] += 1
                continue
            if _extract_poster(path, poster):
                stats["created"] += 1
            else:
                stats["failed"] += 1

    if stats["created"] or stats["failed"]:
        logger.info(
            "thumbnail: created=%d skipped=%d failed=%d",
            stats["created"],
            stats["skipped"],
            stats["failed"],
        )
    return stats


async def rebuild_portfolio_listener(payload: dict[str, Any]) -> None:
    """Async listener that triggers a portfolio index rebuild in a worker thread.

    Wired to `pipeline.completed` via WebhookManager.subscribe(). 扫描包含 stat()
    一百多个文件,放到 threadpool 防止偶发 I/O 抖动卡住事件循环。
    """
    try:
        # 用完整 package path,与 tests/test_portfolio_mechanism.py 的
        # `import scripts.portfolio_index` 拿到同一模块对象,monkeypatch 才生效。
        from scripts.portfolio_index import rebuild_index

        index = await asyncio.to_thread(rebuild_index)
        logger.info(
            "portfolio: auto-rebuild on pipeline.completed → %d files (thread_id=%s)",
            index["summary"]["total_files"],
            payload.get("thread_id", "unknown"),
        )
    except Exception as exc:
        # 决不让 portfolio 失败拖累管线 —— 仅记录,不抛出
        logger.warning("portfolio: auto-rebuild failed: %s", exc)

    # Generate posters for any new videos so gallery UIs never show black screen.
    try:
        await asyncio.to_thread(_ensure_thumbnails)
    except Exception as exc:
        logger.warning("thumbnail: auto-generation failed: %s", exc)


def register_portfolio_hook() -> None:
    """Idempotent registration of the rebuild listener on pipeline.completed."""
    from src.tools.webhook_manager import EVENT_PIPELINE_COMPLETED, get_webhook_manager

    wm = get_webhook_manager()
    wm.subscribe(EVENT_PIPELINE_COMPLETED, rebuild_portfolio_listener)
