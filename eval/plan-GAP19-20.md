# GAP-19: Enhanced Monitoring & Observability

**现状：** telemetry.py 已提供基本的 `PipelineMetrics` + `@timed_node` 装饰器，
记录每个节点的 timing/success/error，但只有这些：
- 单次 pipeline 运行级别的指标（in-memory PipelineMetrics）
- 没有历史汇总、趋势、告警
- 没有指标导出到外部系统
- 没有结构化错误追踪的持久化

**目标：** 建立可在生产环境实际使用的监控体系，允许观察单次运行 +
跨运行趋势 + 异常告警。

---

## Task 1: Persistent Metrics Store

在当前 PipelineMetrics（运行时）基础上，添加 MetricsRepository 层，
支持将运行数据存储到可查询的后端。

**实现：**
- `src/tools/metrics_repository.py` — 可选的持久化层
- 2 种模式：JSON file（无依赖，开发用）和 SQLite（零外部依赖，本地生产用）
- 方法：`save_run()`, `list_runs(limit=20)`, `get_run(run_id)`, `get_summary(hours=24)`
- 完全 mockable / 可降级，不阻塞 pipeline

**新文件：** `src/tools/metrics_repository.py`
**测试文件：** `tests/test_metrics_repository.py` (~15 tests)

---

## Task 2: Cross-Run Summary Aggregation

在 MetricsRepository 上建立聚合查询，回答：
- 过去 24h 运行次数 / 成功次数 / 失败次数
- 最慢节点 Top 5
- 失败率趋势
- 平均重跑次数

**实现：**
- `MetricsRepository.get_summary()` — 返回 SummaryReport dataclass
- 通过 SQLite 聚合查询（GROUP BY, ORDER BY, window functions）
- JSON file 模式：内存聚合（加载所有 run 后计算）

---

## Task 3: Health /metrics Endpoint

在 `src/api.py` 上添加 `/metrics` 端点。

**实现：**
- `GET /api/v1/metrics` — 返回 MetricsRepository.get_summary()
- `GET /api/v1/metrics/runs` — 列出最近运行
- `GET /api/v1/metrics/runs/{run_id}` — 单次运行详情
- 可以 mock metrics_repository（不依赖实际数据库）

**注意：** 这是 fastapi 端点，测试将在 fastapi 不可用时 skip。
和现有 `/health` 端点同一模式。

---

## Task 4: Error Threshold Alerts

在 pipeline 编译时或运行后，检查错误率阈值并触发警告。

**实现：**
- `MetricsRepository.check_health()` — 返回 HealthStatus
- 检查项：
  - 最近 10 次运行中失败次数 > 3 → WARN
  - 连续 5 次运行失败 → CRITICAL
  - 单节点平均耗时 > 30s → WARN
  - 重跑率 > 50% → WARN
- 结果写入 structlog 告警
- 预期通过 webhook（GAP-17 的基础设施）推送警报

---

## Task 5: Test Coverage (~20 tests)

- `tests/test_metrics_repository.py` — 15-18 tests
- `tests/test_monitoring.py` — 5-7 integration tests

---

# GAP-20: Standardized Error Taxonomy

**现状：** 当前错误处理分散在各处：
- `errors: list[str]` 是纯字符串列表
- 节点错误被 `@timed_node` 捕获并追加到 `errors`
- 没有结构化错误码、严重级别、可操作建议
- 无法区分"客户端配置错误" vs "LLM API 超时" vs "输入验证失败"

**目标：** 建立统一的错误分类系统，让每个错误都是结构化对象，
方便 UI 展示、告警、自动恢复和审计。

---

## Task 1: PipelineError Model + ErrorCode Enum

**实现：**
- `src/models/errors.py` — 新模块
- `ErrorCode(str, Enum)` — ~15 个错误码
  - `INPUT_TIMEOUT`, `LLM_TIMEOUT`, `DALLE_TIMEOUT`, `ELEVENLABS_TIMEOUT`
  - `AUDIT_BLOCKED`, `COMPLIANCE_BLOCKED`, `ASSET_NOT_FOUND`, `LANGGRAPH_SERIALIZE`
  - `API_KEY_MISSING`, `CONFIG_ERROR`, `UNKNOWN_NODE_ERROR`
  - `WEBHOOK_FAILED`, `ASSET_LIBRARY_UNAVAILABLE`
- `PipelineError(BaseModel)` — 结构化错误
  - `code: ErrorCode`, `message: str`, `node: str | None`, `recoverable: bool`,
    `detail: dict[str, Any]`, `timestamp: str`
- `type_alias PipelineErrors = list[PipelineError]`
- 放到 `VideoPipelineState` 中替换 `errors: list[str]`

**新文件：** `src/models/errors.py`

---

## Task 2: Error Classifier Utility

**实现：**
- `src/tools/error_classifier.py` — 将异常映射到 ErrorCode
- `classify_error(exception: Exception, context: str) -> PipelineError`
- 启发式规则：
  - `asyncio.TimeoutError` / `TimeoutError` → `INPUT_TIMEOUT`
  - `httpx.TimeoutException` → `LLM_TIMEOUT` / `DALLE_TIMEOUT` / `ELEVENLABS_TIMEOUT`
  - Exception message 含 "API key" / "api_key" → `API_KEY_MISSING`
  - Audit BLOCKED → `AUDIT_BLOCKED`
  - 对未知异常降级到 `UNKNOWN_NODE_ERROR`

**新文件：** `src/tools/error_classifier.py`

---

## Task 3: Integrate into Pipeline State

**实现：**
- 更新 `VideoPipelineState`：添加 `structured_errors: list[PipelineError]`
- 保留 `errors: list[str]` 向后兼容
- `@timed_node` 中捕获异常时，调用 `classify_error()` 生成 PipelineError
- 自动填充 `node` 字段（来自装饰器上下文）
- 被 BLOCKED 的 audit 节点、compliance 节点也生成结构化错误

**修改文件：** `src/models/state.py`, `src/telemetry.py`

---

## Task 4: Test Coverage (~15 tests)

- `tests/test_errors.py` — 测试 ErrorCode, PipelineError, classify_error
- `tests/test_error_integration.py` — 集成测试，验证节点错误被正确分类

---

# 选做：MEDIUM 优先级优化项

以下是从 GAP-18 之前的 deep audit 中记下的 MEDIUM 级别问题，
不做专题 GAP，顺手修掉即可：

| # | 问题 | 文件 | 修复方式 |
|---|------|------|----------|
| M1 | `routing.py` 中 `ComplianceStatus` / `ApprovalStatus` 未使用的导入 | `src/graph/routing.py` | 删除 |
| M2 | `state.py` 中 `Platform` / `Language` / `ApprovalStatus` 未使用的导入 | `src/models/state.py` | 删除 |
| M3 | `strategy.py` 中 `datetime` 未使用的导入 | `src/agents/strategy.py` | 删除 |
| M4 | `storyboard.py` 中 `json` 未使用的导入 | `src/agents/storyboard.py` | 删除 |
| M5 | `analytics.py` 中 `Platform` 未使用的导入 | `src/agents/analytics.py` | 删除 |
| M6 | `distribution.py` 中 `Platform` 未使用的导入 | `src/agents/distribution.py` | 删除 |
| M7 | `asset_sourcing.py` 中 `AssetCandidate` 未使用的导入 | `src/agents/asset_sourcing.py` | 删除 |
| M8 | `i18n.py` 中 `Language` 未使用的导入 | `src/agents/i18n.py` | 删除 |
| M9 | `audio_designer.py` 中 `pathlib.Path` 未使用的导入 | `src/agents/audio_designer.py` | 删除 |
| M10 | `dalle_client.py` 中 `Optional` 未使用的导入 | `src/tools/dalle_client.py` | 删除 |
| M11 | `elevenlabs_client.py` 中 `Optional` 未使用的导入 | `src/tools/elevenlabs_client.py` | 删除 |
| M12 | `api.py` 中 `asyncio` / `json` 未使用的导入 | `src/api.py` | 删除 |
| M13 | 模型名 `claude-sonnet-4-20250514` 将在 2026-06-15 弃用 | `src/tools/llm_client.py` | 改为 `claude-sonnet-4-20250514` → latest stable |
| M14 | GAP-2 residual: msgpack 反序列化警告依然出现 | `src/graph/pipeline.py` | MemorySaver 的 serde 没有正确传递给 `with_msgpack_allowlist` |

---

# 执行优先级建议

| 优先级 | GAP | 理由 |
|--------|-----|------|
| P0 | M14 (msgpack) | 42 条 Deserializing unregistered type 警告，长期隐患 |
| P0 | GAP-20 Task 1 + 2 | 错误分类是最基础的基础设施，别的都依赖它 |
| P0 | M1-M12 (import cleanup) | 免费 clean up，5 分钟搞定 |
| P1 | GAP-19 Task 1 + 2 (metrics store) | 监控的历史数据基座，但没有错误分类也能做 |
| P2 | M13 (model deprecation) | 6 月 15 才弃用，但 warning 有 50+ 条，修不修都行 |
| P3 | GAP-19 Task 3 + 4 (metrics APIs + alerts) | 依赖 fastapi，当前不可安装 |
| P3 | GAP-20 Task 3 + 4 (集成 + 测试) | 依赖 Task 1 完成 |
