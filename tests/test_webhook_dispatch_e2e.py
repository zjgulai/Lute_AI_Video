"""e2e: 真实 webhook URL 触发链路验证。

CLAUDE.md「Known Gaps」F 任务的 e2e 部分。

要跑这个测试:
    1. 去 webhook.site 拿一个唯一 URL,例如 https://webhook.site/abc-def-ghi
    2. export WEBHOOK_TEST_URL=https://webhook.site/abc-def-ghi
    3. pytest tests/test_webhook_dispatch_e2e.py -m e2e -v

测试会:
    1. 注册 WEBHOOK_TEST_URL 为 audit.completed + pipeline.completed 的接收器
    2. dispatch 这两个事件
    3. 你打开 webhook.site 应该能看到 2 条 POST 请求

不在本测试范围:
    - 不验证 webhook.site 端的 HTTP 数据(无 API 自动 verify)
    - 用户人工确认 webhook.site 收到事件即算通过
"""

from __future__ import annotations

import os

import pytest

# 默认 skip 整个文件;用户配 WEBHOOK_TEST_URL 后跑 -m e2e 才执行
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("WEBHOOK_TEST_URL"),
        reason="需要 export WEBHOOK_TEST_URL=https://webhook.site/<your-id>",
    ),
]


@pytest.mark.asyncio
async def test_dispatch_audit_completed_to_real_url():
    from src.tools.webhook_manager import (
        EVENT_AUDIT_COMPLETED,
        WebhookManager,
    )

    url = os.environ["WEBHOOK_TEST_URL"]
    wm = WebhookManager()
    wm.register(EVENT_AUDIT_COMPLETED, url)

    payload = {
        "checkpoint": "strategy",
        "score": 0.92,
        "thread_id": "e2e-test-thread",
        "trace_id": "e2e-trace-xyz",
    }
    # dispatch 内部 5s timeout,失败不抛
    await wm.dispatch(EVENT_AUDIT_COMPLETED, payload)

    # 用户去 webhook.site 看 POST 是否到达 + payload 是否正确
    print(f"\n[e2e] 已 POST audit.completed 到 {url}")
    print(f"      payload={payload}")
    print("      去 webhook.site 验证")


@pytest.mark.asyncio
async def test_dispatch_pipeline_completed_to_real_url():
    from src.tools.webhook_manager import (
        EVENT_PIPELINE_COMPLETED,
        WebhookManager,
    )

    url = os.environ["WEBHOOK_TEST_URL"]
    wm = WebhookManager()
    wm.register(EVENT_PIPELINE_COMPLETED, url)

    payload = {
        "thread_id": "e2e-test-thread",
        "trace_id": "e2e-trace-xyz",
        "status": "completed",
        "duration_seconds": 123,
    }
    await wm.dispatch(EVENT_PIPELINE_COMPLETED, payload)

    print(f"\n[e2e] 已 POST pipeline.completed 到 {url}")
    print(f"      payload={payload}")


@pytest.mark.asyncio
async def test_register_all_dispatches_to_each_event():
    """register_all(url) 让一个 URL 接收所有 ALL_EVENTS。"""
    from src.tools.webhook_manager import (
        ALL_EVENTS,
        EVENT_AUDIT_COMPLETED,
        EVENT_PIPELINE_COMPLETED,
        WebhookManager,
    )

    url = os.environ["WEBHOOK_TEST_URL"]
    wm = WebhookManager()
    wm.register_all(url)

    # dispatch 几个不同事件
    await wm.dispatch(EVENT_AUDIT_COMPLETED, {"checkpoint": "edit", "score": 0.7})
    await wm.dispatch(EVENT_PIPELINE_COMPLETED, {"status": "ok"})

    print(f"\n[e2e] 已 POST {len(ALL_EVENTS)} 个事件类型到 {url}")
