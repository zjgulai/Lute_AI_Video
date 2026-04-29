# GAP-17: 管道事件 Webhook 通知系统

> **目标：** 允许用户在 pipeline 关键事件（中断、审批、完成、错误）上注册 webhook URL，
> 管道会自动投递 JSON payload 到这些 URL。零外部依赖——用 httpx（已装）。

---

## 架构概览

```
                    ┌──────────────────────┐
                    │    WebhookManager     │
                    │  ─────────────────    │
                    │  webhooks: dict       │  key=event_type, value=局域列表
                    │  dispatch(event)      │  → httpx.post(url, json=payload)
                    │  └ 失败→日志警告      │
                    │  └ 超时→5s            │
                    └──────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    pipeline.start    audit_node trigger    pipeline.complete
```

### 事件类型

| 事件 | 触发点 | 载荷 |
|---|---|---|
| `pipeline.started` | pipeline 启动 | thread_id, product/平台配置, timestamp |
| `audit.completed` | 每个 audit node 执行完后 | checkpoint名称, 评分, 状态, 摘要 |
| `human_review.required` | pipeline interrupt 时 | thread_id, 节点名称, 审计报告 |
| `human_review.submitted` | 审核更新 resume 后 | thread_id, 节点名称, 审批状态, notes |
| `pipeline.completed` | pipeline 结束（analytics 后） | thread_id, 总耗时, 节点数, PIPELINE 指标 |
| `pipeline.error` | pipeline 有 errors | thread_id, error 列表 |

### 并发和超时
- 每个 webhook POST 使用 asyncio 在 5s 超时内完成
- 失败只记日志警告，不阻塞管道
- 用 `asyncio.gather()` 并行发往同一事件的所有 webhook

---

## 实现任务

### Task 1: `src/tools/webhook_manager.py`（WebhookManager 类）

**核心 API：**

```python
class WebhookManager:
    def __init__(self): 
        self._webhooks: dict[str, list[str]] = defaultdict(list)  # event_type → [urls]
    
    def register(self, event_type: str, url: str) -> None:
        # 验证 URL 格式，去重
    
    def unregister(self, event_type: str, url: str) -> None:
        # 移除
    
    def list_webhooks(self) -> dict[str, list[str]]:
        # 返回当前注册状态
    
    async def dispatch(self, event_type: str, payload: dict) -> None:
        # 并行发 POST，5s 超时，日志警告，不抛异常
        # httpx.AsyncClient(timeout=5.0).post(url, json=event_envelope)
```

**事件信封格式：**

```python
{
    "event_type": "pipeline.started",
    "timestamp": "2026-04-25T12:00:00Z",
    "pipeline_id": "abc123",
    "thread_id": "demo-001",
    "data": { ... }  # 事件专属字段
}
```

### Task 2: nodes.py 中埋点

在 4 个 audit node 末尾和 analytics_node 末尾调用 `webhook_manager.dispatch()`。

需要把 `WebhookManager` 实例挂到 state 中或作为模块级单例。

**方案选择：模块级单例**（最简单，不需要动 state schema）

```python
# src/tools/webhook_manager.py 模块级
_webhook_manager = WebhookManager()

def get_webhook_manager() -> WebhookManager:
    return _webhook_manager
```

**注入点：**

| 位置 | 事件 | 备注 |
|---|---|---|
| `strategy_audit_node` 末尾 | `audit.completed` | checkpoint=strategy |
| `script_audit_node` 末尾 | `audit.completed` | checkpoint=script |
| `editing_audit_node` 末尾 | `audit.completed` | checkpoint=edit |
| `thumbnail_audit_node` 末尾 | `audit.completed` | checkpoint=thumbnail |
| 管道启动时（api.py） | `pipeline.started` | 首次 astream 前 |
| 管道中断时（api.py） | `human_review.required` | 收到 interrupt 事件后 |
| `analytics_node` 末尾 | `pipeline.completed` | 最后 |

### Task 3: config.py + .env 补充（可选）

```python
# 新增
WEBHOOK_URLS = os.getenv("WEBHOOK_URLS", "")  # 逗号分隔的 URL，注册到所有事件
```

.env.example 添加一行。

### Task 4: 测试（14 tests）

**File:** `tests/test_webhook_manager.py`

| 类 | 测试数 | 覆盖 |
|---|---|---|
| `TestWebhookManager` | 9 | 注册、去重、注销、列表、dispatch、超时、错误处理 |
| `TestWebhookIntegration` | 5 | manager 单例、节点注入、事件封包格式 |

### Task 5: 回归

```bash
cd /workspace/projects/hermes_evo/AI_vedio && python3 -m pytest tests/ -v --tb=short
```

期望：284 + 14 = 298 passed, 7 skipped

---

## 质量门槛

- [x] 使用现有 httpx（不引入新依赖）
- [x] 不打断现有测试
- [x] webhook 失败不阻塞管道
- [x] 5s 超时
- [x] 支持注册/注销 API（供前端管理）
- [x] 模块级单例，不需要改 state schema
- [x] 14 个新测试
