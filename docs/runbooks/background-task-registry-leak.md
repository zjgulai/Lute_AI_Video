---
title: Background Task Registry Leak Contract
doc_type: workflow
module: backend
topic: background-task-registry
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# Background Task Registry Leak Contract

## 触发场景

新增或调整 `asyncio.create_task`、startup background loops、webhook fire-and-forget、S1/S5 background resume、FastAPI lifespan shutdown 时，先检查本契约。

## 影响范围

后台任务如果不注册或完成后不清理，会导致 task 对象、异常、contextvars、tenant/API key 上下文和闭包长期留在进程内。生产上表现为内存慢涨、shutdown 等待异常、重复日志或任务取消不彻底。

## 预期 MTTR

5-10 min。大多数泄漏能通过 registry snapshot 和单测定位。

## 当前契约

机器可读契约：`configs/background-task-registry-contract.yaml`

共享 registry：

- `register_background_task(task, label)` 是通用注册入口。
- `get_background_task_snapshot()` 只返回 metadata，不返回 task 对象。
- `cancel_background_tasks()` 是 FastAPI lifespan shutdown 的统一取消入口。

自动清理规则：

- task 正常 completed 后必须从 registry 移除。
- task failed 后必须从 registry 移除，并记录 `background_task_failed`。
- task externally cancelled 后必须从 registry 移除。
- shutdown cancel 后 done task 必须从 registry 移除。

## 相关代码

- [`src/tasks/bg_registry.py`](../../src/tasks/bg_registry.py) — registry 实现。
- [`src/api.py`](../../src/api.py) — startup background loops 和 lifespan shutdown。
- [`src/graph/nodes.py`](../../src/graph/nodes.py) — webhook fire-and-forget 注册入口。
- [`src/routers/scenario.py`](../../src/routers/scenario.py) — background pipeline run / resume 注册入口。
- [`tests/test_bg_registry.py`](../../tests/test_bg_registry.py) — shutdown cancel 行为。
- [`tests/test_bg_registry_leak_contract.py`](../../tests/test_bg_registry_leak_contract.py) — completed / failed / cancelled 自动清理与文档契约。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_bg_registry.py tests/test_bg_registry_leak_contract.py -q
```

该测试只运行本地 asyncio task，不访问生产，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

手动排查时，在进程内查看：

```python
from src.tasks.bg_registry import get_background_task_snapshot
get_background_task_snapshot()
```

正常 idle 状态应为空；长期存在且 `done=true` 或 `cancelled=true` 的记录表示清理漂移。

## 分类响应

- completed task 残留：检查 `register_background_task()` 是否仍挂 `add_done_callback` 并在 `finally` 中 `pop`。
- failed task 残留：检查 done callback 是否调用 `task.exception()` 后仍进入 `finally`。
- cancelled task 残留：检查 `asyncio.CancelledError` 分支是否重新阻断了 `finally`。
- shutdown 后残留：检查 `cancel_background_tasks()` 是否遍历 snapshot 并移除 done task。
- 新增 fire-and-forget 未注册：不要直接裸用 `asyncio.create_task(...)`；必须立即传给 `register_background_task(...)` 或等价 wrapper。

## 永久 fix

1. 所有长期或 fire-and-forget background task 必须注册。
2. done callback 的清理必须放在 `finally`。
3. snapshot 不返回 task 对象，避免把内部可变 task 暴露给调用方。
4. 新增 background task 后补 label，label 必须能定位业务来源。
5. 不要用真实生成接口验证 registry；用本地 asyncio task 即可。
