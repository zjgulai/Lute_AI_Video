---
title: Metrics Webhook Analytics 事件链路分段计划
doc_type: workflow
module: metrics
topic: metrics-webhook-analytics-event-chain
status: stable
created: 2026-06-17
updated: 2026-06-17
owner: self
source: human+ai
---

# Metrics Webhook Analytics 事件链路分段计划

## 当前结论

截至 2026-06-17，metrics / webhook / analytics 已具备本地与生产只读基础能力，但真实事件链路仍未执行。

已验证能力：

- `VideoMetricsRepository` 支持 metrics snapshot 写入、读取、dashboard 聚合和 tenant filter。
- `MetricsPoller.pull_all()` 支持 active posts 扫描、bounded concurrency 与单任务失败隔离。
- `/api/dashboard/overview?days=7` 生产 authenticated GET 返回 `data/videos/scenarios/platforms` 合同。
- `/dashboard` 生产前端已可 authenticated read-only 访问，并进入非错误空数据态。
- `/api/metrics/pull` 已默认 fail-closed，生产验证返回 `403 Metrics pull is disabled`，未调用 `MetricsPoller.pull_all`。
- `WebhookManager` 已在本地 fixture 层覆盖 URL 安全、HTTP dispatch failure isolation、in-process listener 和 portfolio hook。

未验证能力：

- `MetricsPoller` 未注册到 `src/api.py` startup scheduler。
- TikTok / Shopify metrics fetcher 仍是 stub，未接真实平台 metrics API。
- 生产 `METRICS_PULL_ENABLED` 未启用，生产 `/api/metrics/pull` 未执行真实 pull。
- `WEBHOOK_URLS` 生产为空，未对 webhook.site 或等价外部接收端做真实 dispatch/readback。
- 没有从真实 publish post_id 到 metrics ingestion，再到 dashboard，再到 webhook/event audit 的端到端证据链。

## 硬边界

默认状态继续 fail-closed：

- 不启用 `METRICS_PULL_ENABLED`。
- 不注册 startup scheduler。
- 不调用真实 TikTok / Shopify platform metrics API。
- 不调用 `/api/metrics/pull`。
- 不配置或触发外部 webhook dispatch。
- 不执行 provider、`/api/scenario/*` submit、Fast Mode submit、publish、delivery acceptance 或 approved brand token write。

任何突破上述边界都必须单独授权，且授权文本必须包含目标 endpoint、数据范围、外部接收端、次数上限、止损条件和收尾动作。

## 分段执行计划

| 阶段 | 目标 | 默认环境 | 是否允许外部调用 | 验收口径 |
|---|---|---|---:|---|
| `P2-1L0` | 固化当前 source map 与计划 | 本地 docs-only | 否 | 本文件存在；GAP 表引用本文件；不改代码、不碰生产 |
| `P2-1L1` | 平台 metrics fetcher contract | 本地 no-provider | 否 | TikTok/Shopify fetcher 通过 fake client 注入测试；真实 connector 仍不调用 |
| `P2-1L2` | poller ingestion contract | 本地 no-provider | 否 | fake active post -> fake metrics -> repository -> dashboard 聚合全链通过；tenant filter 与 idempotency 规则明确 |
| `P2-1L3` | webhook receiver contract | 本地 no-provider | 否 | fake receiver / mocked HTTP 验证 envelope、timeout、failure isolation；不打到外网 |
| `P2-1L4` | 生产 read-only regression | 生产 read-only | 否 | `/api/health`、`/api/dashboard/overview`、`/dashboard` GET 通过；`/api/metrics/pull` 仍 403；日志无真实 pull/webhook 外发 |
| `P2-1L5` | 外部 webhook 单事件 smoke | 生产受控 | 是，仅 webhook receiver | 只注册 1 个临时外部接收端；只触发 1 个非 publish 事件；receiver readback 匹配 envelope；收尾撤销配置 |
| `P2-1L6` | 平台 metrics pull 单次 pilot | 生产受控 | 是，仅指定 platform metrics API | `METRICS_PULL_ENABLED` 只在窗口内启用；只处理 1 条 allowlisted post；pull 次数=1；dashboard 可读；日志无 publish/provider/submit |
| `P2-1L7` | scheduler readiness | 本地/生产 no-execute | 否 | 只设计 scheduler 启停、锁、频率、kill-switch；不自动注册生产 startup |

## 关键设计要求

### Platform fetcher contract

真实 TikTok / Shopify metrics 接入前，先把 fetcher 设计成可注入依赖：

- `MetricsPoller` 不直接在方法内部硬编码真实 SDK 或 HTTP client。
- fetcher 必须返回标准 metrics dict，至少包含 `views`、`watch_rate`、`ctr`、`cvr`、`followers_gained`、`sales` 可选字段。
- 真实平台错误必须分类为 auth、rate_limit、not_found、transient、schema_drift，不得静默返回 `{}` 后声明成功。
- 单 post 失败不得影响其他 post，但 summary 必须记录失败数量和原因。

### Ingestion / idempotency contract

当前 repository 每次 `save_metrics()` 都插入新 snapshot。真实 pull 前必须明确：

- 同一 `(tenant_id, video_id, platform, post_id, pulled_at window)` 是否允许重复 snapshot。
- dashboard 使用 latest snapshot 的规则是否满足业务判断。
- active post 来源是否只依赖现有 `video_metrics` 历史行，还是需要从 `publish_logs` 建立待拉取队列。
- 无 `post_id`、无 `tenant_id`、过期 post、未知 platform 必须计数并跳过。

### Webhook contract

外部 webhook pilot 前必须明确：

- 接收端只允许 HTTPS public URL。
- 不允许 private IP、localhost、内网地址或危险端口。
- 每次 smoke 只注册 1 个 event type 和 1 个 URL。
- receiver readback 必须验证 `event_type`、`event_id`、`timestamp`、`data`。
- dispatch 失败不得阻塞主流程，但必须进入日志和 summary。

### Scheduler contract

生产 scheduler 不是下一步默认动作。真实注册前必须先完成：

- kill-switch：`METRICS_PULL_ENABLED=false` 时 scheduler 不启动。
- 单实例锁：避免多容器或重启导致重复 pull。
- 频率上限：按 post age 计算后仍要有全局最小间隔。
- dry-run mode：只列出 due posts，不调用 platform API。
- 观测：每轮 pulled/skipped/failed/unknown_platform/post_missing_id 计数可读。

## 未来授权模板

### P2-1L4 read-only regression

```text
我授权在生产环境 https://video.lute-tlz-dddd.top 执行 P2-1L4 metrics/dashboard read-only regression。
只允许创建 1 个临时 non-demo production X-API-Key，tenant=momcozy-marketing，有效期 2 小时。
只允许 GET /api/health、GET /api/dashboard/overview?days=7、只读访问 /dashboard。
允许确认 POST /api/metrics/pull 仍返回 403，但不得启用 METRICS_PULL_ENABLED，不得调用 MetricsPoller.pull_all。
验证后撤销临时 key，post-revoke 只读认证检查期望 401。
不允许 provider、scenario submit、Fast Mode submit、publish、delivery acceptance、approved brand token write、webhook 外发。
```

### P2-1L5 external webhook single-event smoke

```text
我授权在生产环境 https://video.lute-tlz-dddd.top 执行 P2-1L5 external webhook single-event smoke。
只允许使用一个临时 HTTPS webhook receiver URL。
只允许注册一个非 publish event type。
只允许触发一次受控测试事件。
必须 receiver readback 验证 event_type/event_id/timestamp/data。
完成后必须撤销 webhook 配置。
不允许 metrics pull、provider、scenario submit、Fast Mode submit、publish、delivery acceptance、approved brand token write。
```

### P2-1L6 platform metrics pull single-post pilot

```text
我授权在生产环境 https://video.lute-tlz-dddd.top 执行 P2-1L6 platform metrics pull single-post pilot。
只允许临时启用 METRICS_PULL_ENABLED，窗口结束后必须恢复 false。
只允许处理 1 条 allowlisted tenant/post/platform 记录。
只允许调用指定 platform metrics API 1 次。
不允许 startup scheduler。
不允许 webhook 外发。
不允许 provider、scenario submit、Fast Mode submit、publish、delivery acceptance、approved brand token write。
验证 dashboard readback 后撤销临时 key并生成 sanitized summary。
```

## 下一步

默认下一步是 `P2-1L1 + P2-1L2`：在本地 no-provider 模式下补平台 fetcher contract、poller ingestion contract 与 idempotency 测试。该阶段只允许 fake client 和 SQLite/fixture，不允许真实平台 API、生产写入或 webhook 外发。
