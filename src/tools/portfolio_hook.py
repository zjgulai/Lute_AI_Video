"""Portfolio index auto-rebuild hook.

闭环测试结束后(LangGraph `pipeline.completed` 事件触发时)自动重建 portfolio
索引。把扫描放到 threadpool 里跑,不阻塞 asyncio 事件循环。

Hook 注册见 `src/api.py` startup;手动重建用 `make portfolio` 或
`python scripts/portfolio_index.py`。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


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


def register_portfolio_hook() -> None:
    """Idempotent registration of the rebuild listener on pipeline.completed."""
    from src.tools.webhook_manager import EVENT_PIPELINE_COMPLETED, get_webhook_manager

    wm = get_webhook_manager()
    wm.subscribe(EVENT_PIPELINE_COMPLETED, rebuild_portfolio_listener)
