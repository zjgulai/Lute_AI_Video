---
title: 代码质量梳理与测试闭环 — 分波次交付方案 (v2)
doc_type: architecture
module: engineering
topic: code-quality-test-closure
status: review
created: 2026-05-07
updated: 2026-05-07
owner: self
source: human+ai
---

# 代码质量梳理与测试闭环 — 分波次交付方案 (v2)

> **Changelog from v1:** 参考 `2026-05-06-production-readiness-framework.md` 后，新增：安全审计、依赖审计、Admin Panel 单元测试、前端组件测试、故障注入测试扩展、E2E Playwright 回归、P0/P1/P2 路径优先级分类。将 10 条未验证路径按客户信任影响重新分级。

## 1. 概述

Admin Panel Phase 1 和生产部署修复（ChunkLoadError / 循环导入 / nginx 语法）已发布上线。当前项目进入**整合交付阶段**：需要系统性地补齐测试缺口、清理代码质量债、建立可重复的生产验证流程。

**当前基线（来自生产就绪框架审计）：**

| 指标 | 当前值 | 目标 |
|------|--------|------|
| Backend 测试文件 | 42 | 50+ |
| Frontend 测试文件 | 2 | 30+ |
| Admin Panel 测试覆盖 | 0% | ≥ 60% |
| E2E 回归测试 | 0 | 6 个旅程 |
| 未验证交互路径 | 10 (A-J) | 全部验证 |
| Prometheus 指标 | 6 | ≥ 12 |
| 告警规则 | 0 | 4 条 |

本方案覆盖两个核心领域：
- **测试闭环**：CLAUDE.md 中列出的 10 条未验证路径（A-J）+ Admin Panel 测试 + 前端组件测试 + E2E 回归
- **代码质量**：pyright strict 剩余规则、循环导入根治、死代码清理、安全审计、模块边界梳理

## 2. 核心原则

**由内到外、由低风险到高风险、每波都有可验证产出。**

四个波次不是简单的线性顺序，而是有明确的依赖关系。每波结束后产出可独立验证的交付物，前面的波次为后面的波次建立基线。

## 3. 总体架构

```
Wave 1 (基线审计) ──→ Wave 2 (核心测试) ──→ Wave 3 (集成+E2E) ──→ Wave 4 (运维就绪*)
  4 天                  7 天                   5 天                  5 天 (可选扩展)
```

\* Wave 4 为可选扩展波次，取决于是否需要投入运维就绪（监控/告警/备份/Runbook）。

### 3.1 波次分解

| 波次 | 测试任务 | 代码质量/审计任务 | 产出 |
|------|----------|-------------------|------|
| **Wave 1** | i18n(I)、Metrics(D) | 死代码清理、pyright 扫尾、**安全审计**、**依赖审计** | 干净基线 + 审计报告 |
| **Wave 2** | **P0 路径**(A/G/H)、**P1 路径**(B/E)、**Admin 单元测试**、**前端组件测试** | 循环导入根治 | 核心链路测试基线 |
| **Wave 3** | **P2 路径**(C/F)、**E2E 回归**、并发压测(H) | pyright strict 全启 | 生产级验证 |
| **Wave 4**\* | — | Prometheus 扩展、告警规则、Grafana、备份、Runbook | 运维就绪 |

### 3.2 关键决策

1. **Wave 1 放在最前**：死代码清理和类型补全几乎零风险；安全审计和依赖审计是生产就绪的基础，必须在写测试前完成。
2. **10 条路径按 P0/P1/P2 分级执行**：
   - **P0**（客户信任关键）：错误降级(G)、多租户隔离(H)、Human Review 分支(A) — 这些不验证，生产出问题时客户直接流失
   - **P1**（功能关键）：Gate 闭环(B)、Assets 上传(E) — 产品核心卖点
   - **P2**（时间允许）：Distribution(C)、Webhook(F) — 外部依赖，可 mock 验证
3. **Gate 系统(B) 放在 Wave 2**：Expert Studio 是产品核心卖点，如果 Gate 有 bug，所有 checkpoint 逻辑都受影响。
4. **Admin Panel 测试放在 Wave 2**：Phase 1 刚部署，0% 测试覆盖，必须在下一批功能开发前补齐。
5. **Distribution(C) 放在 Wave 3**：需要外部平台 credentials，不控制在我们手里，不能阻塞前面工作。
6. **pyright strict 全启放在 Wave 3**：需要大量 `dict[str, Any]` → 具体类型替换，ROI 低，放在测试保护之后。

## 4. Wave 1 详细设计 — 基线审计与清理（4 天）

### 4.1 i18n 全量走查（I）

**目标**：验证 `zh-CN` / `en` 切换后，所有用户可见文案均从翻译表读取，无硬编码残留。

**执行步骤**：
1. 脚本扫描所有 `t("...")` 调用与 `translations.ts` 中的键做 diff，列出缺失键
2. 逐页走查：`/`、`/s1`、`/s5`、`/fast`、`/footage`、`/settings`、`/admin/*`
3. 重点检查 GatePanel、DistributionView、SettingsPanel、Admin 页面（新开发或近期修改的，最可能有遗漏）

**验收标准**：
- 走查报告中列出所有硬编码中文/英文残留（如有）
- 所有 `t("...")` 调用都能在 `translations.ts` 中找到对应键
- 切换语言后无空白或显示 key 名的情况

**预计时间**：0.5 天

### 4.2 Metrics 全链验证（D）

**目标**：验证 `video_metrics` 表真实可用，`/metrics/*` 端点返回真数据，`metrics_poller.py` 周期任务正常调度。

**执行步骤**：
1. 登录生产 PG，确认 `video_metrics` 表已 `alembic upgrade head`
2. 手动插入一条 mock metrics 数据，调用 `GET /metrics/{video_id}` 验证返回
3. 检查 `metrics_poller.py` 是否被注册为后台任务（`api.py` startup）
4. 前端 `PerformanceDashboard` 对接真数据验证

**验收标准**：
- PG 表存在且有正确 schema
- API 返回的数据与表中数据一致
- 前端 PerformanceDashboard 正确渲染（无 NaN/undefined 显示）

**预计时间**：0.5 天

### 4.3 死代码清理

**目标**：移除已声明但未使用的依赖和代码，降低维护成本。

**执行清单**：
1. **Redis/Celery**：从 `requirements.txt` 移除，检查是否有任何 import 引用
2. **`api_assets.py`**：确认仍为 compat shim 状态，标记为 `@deprecated` 并在 CLAUDE.md 中记录迁移计划
3. 确认 Phase 4 已清理的项无残留：`_try_save_metrics`、test_i18n.py ES/FR/DE、telemetry/cost_tracker 死函数

**验收标准**：
- `requirements.txt` 无 Redis/Celery 依赖
- `make ci` 通过（ruff + pyright + pytest）
- 容器重新 build 后启动正常

**预计时间**：0.5 天

### 4.4 类型补全（pyright 扫尾）

**目标**：处理 Phase 4 未启用的 pyright 规则中**低投入高产出**的部分。

**执行策略**：
- **不启用** `reportUnknownMemberType` / `reportUnknownVariableType`（ROI 低，放在 Wave 3）
- **启用并修复** `reportMissingTypeArgument` 和 `reportPossiblyUnboundVariable` 的剩余漏网之鱼
- **重点扫描**：`src/routers/` 和 `src/graph/`（最近修改最多的模块）

**验收标准**：
- `make typecheck` 0 错误
- 新增的类型注解覆盖最近修改的所有函数签名

**预计时间**：0.5 天

### 4.5 安全审计（新增）

**目标**：验证认证边界、 secrets 管理、cookie 安全标志符合生产要求。

**执行清单**：

| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| Auth boundary scan | 遍历所有 router decorators | 每个 endpoint 都有正确的 auth dependency |
| API key leak scan | `git log --all \| grep -E 'sk-[a-zA-Z0-9]{20,}'` | 0 匹配 |
| SQL injection check | 审查所有 DB queries | 100% parameterized ($1, $2) |
| Cookie Secure flag | 检查生产 login response headers | Secure; HttpOnly; SameSite=Lax |
| Hardcoded secrets scan | `grep -rE '(password\|secret\|key)\s*=\s*["\x27][^$]' src/` | 0 匹配 |

**预计时间**：0.5 天

### 4.6 依赖审计（新增）

**目标**：检查依赖版本漂移和安全漏洞。

**执行清单**：
1. **Backend**：`pip list --outdated`，检查 `requirements.txt` 版本 pinning 状态
2. **Frontend**：`cd web && npm audit`，修复 moderate 及以上漏洞
3. **Config drift**：对比 `.env.prod` vs `.env.example`，记录 production-only 变量

**预计时间**：0.5 天

### 4.7 Wave 1 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| i18n 发现大量遗漏需要大面积改文案 | 低 | 用脚本扫描 diff，遗漏通常只有少量新增页面 |
| Metrics 表 schema 与代码期望不一致 | 中 | 先查 PG schema，不一致时优先改代码对齐 |
| 移除 Redis/Celery 后发现某个隐藏引用 | 低 | `grep -rn "redis\|celery" src/` 全量扫描 |
| pyright 扫尾发现新错误数量超出预期 | 低 | Phase 4 已建立基线，增量通常 < 10 个 |
| 安全审计发现高危漏洞 | 低 | 立即修复，Wave 1 延期 |

## 5. Wave 2 详细设计 — 核心测试基线（7 天）

### 5.1 P0 路径：客户信任关键（3 天）

P0 路径不验证，生产出问题时客户直接流失。优先执行。

#### 5.1.1 错误降级 + 故障注入（G）

**目标**：验证 `pipeline_degraded = True` 触发后，管线正确终止，错误上报链路通畅。

**执行步骤**：

| 场景 | 注入方法 | 验证点 |
|------|----------|--------|
| DeepSeek 超时 (>120s) | Mock LLM client with delay | Pipeline retries → degrades → returns structured error |
| POYO 内容拒绝 | Mock 400 response | Sanitizer retries → falls back to alternate prompt |
| POYO 完全不可用 | `POYO_API_BASE_URL` → 无效地址 | `pipeline_degraded = True` → routing 终止到 `__end__` |
| DB 连接池耗尽 | 模拟 10 个连接全被占用 | 新请求 queues → 503 after timeout |
| 并发状态写入 | 两个 pipeline 写同一个 state | 无 corruption，last-write-wins with timestamp |

**验收标准**：
- 所有故障场景下 pipeline 均优雅终止（不崩溃、不 hang）
- `error_logs` 表中有正确记录，Admin Logs 页面可见
- `pipeline_degraded = True` 后不再执行后续节点
- 并发写入无状态 corruption

**预计时间**：1.5 天

#### 5.1.2 多租户隔离（H）

**目标**：同时跑 2+ 场景使用不同 API key，验证 `contextvars` 隔离不串。

**执行步骤**：
1. **单场景并发**：同时启动 3 个 S1 pipeline，使用不同 `product_catalog`，验证每个 pipeline 的输出与输入对应
2. **跨场景并发**：同时启动 S1 + S5，S1 使用 key A（有效 POYO），S5 使用 key B（有效 POYO），验证 LLM/POYO/Seedance 三处 contextvars 读取正确
3. **API Key 隔离**：key A 故意设置无效 POYO key，key B 使用有效 POYO key，验证 S1 失败、S5 成功

**验收标准**：
- 并发场景下所有输出与输入一一对应
- API key 隔离生效（一个租户 key 错误不影响其他租户）
- 无 `contextvars` 泄漏或串扰

**工具**：`asyncio.gather` 在 Python 层做并发验证，`locust` 做 HTTP 层并发压测。

**预计时间**：1 天

#### 5.1.3 Human Review 分支（A）

**目标**：验证 4 个 checkpoint 的 HITL 分支（APPROVED / CHANGES_REQUESTED / REJECTED）。

**执行步骤**：
- 使用 mock auditor 返回固定 score 0.75，触发 strategy_audit HITL
- 测试三个分支：APPROVED（pipeline 继续）、CHANGES_REQUESTED（retry + D10 路由覆写）、REJECTED（pipeline 终止）
- 对 script_audit、editing_audit、thumbnail_audit 重复相同流程

**验收标准**：
- 4 个 checkpoint × 3 个分支 = 12 个场景全部通过
- 每个分支至少验证一次完整的端到端流程

**预计时间**：0.5 天

### 5.2 P1 路径：功能关键（2.5 天）

#### 5.2.1 Gate 系统全链路闭环（B）

**目标**：验证 `POST /scenario/s1/gate/.../generate` → 3 候选生成 → `CandidateScorer` 评分 → 前端 `CandidateSelector` 对比 → `regenerate/{candidate}` → `approve` 触发后台续跑。

**执行步骤**：
1. `POST .../generate` → 验证 3 个 candidate（standard/creative/conservative），每个都有 score
2. 前端 `CandidateSelector` 正确渲染 3 个候选
3. `POST .../regenerate/1` → 验证新候选与旧候选不同
4. `POST .../approve` (APPROVED) → 验证后台任务启动，pipeline 继续执行
5. 重新触发 Gate，`approve` (REJECTED) → 验证 pipeline 终止到 `__end__`
6. `approve` (CHANGES_REQUESTED) → 验证 retry count 增加，D10 contextvars 路由覆写生效

**验收标准**：
- 三个分支全部通过，每个分支至少一次完整端到端
- 后台续跑后 pipeline 成功到达 `__end__` 或下一个 checkpoint

**预计时间**：1.5 天

#### 5.2.2 Assets 上传全链路（E）

**目标**：验证"上传 → 后端落盘 → 管线引用 → 出现在最终视频"完整链路。

**执行步骤**：
1. 在 `/brand-packages` 或 `/footage` 页面通过 `GuidedCard` 文件选择上传，验证后端 `/api/upload` 返回 200
2. 验证文件写入 `OUTPUT_DIR`，PG `brand_packages` 表有记录
3. 验证文件可通过 `/api/media/` 访问
4. 在 S1 pipeline 中引用上传的资产，验证资产出现在 storyboard / media_generation 输出中
5. 验证 Remotion 组装时正确引用了上传资产，最终视频文件存在且可播放

**验收标准**：
- 上传文件在 `OUTPUT_DIR` 中存在且大小正确
- PG 表中有正确记录
- Pipeline 输出中引用路径正确
- 最终视频包含上传资产（视觉确认或 hash 比对）

**预计时间**：1 天

### 5.3 Admin Panel 单元测试（新增，1 天）

**目标**：补齐 Phase 1 部署的 Admin Panel 测试覆盖（当前 0%）。

**新增测试文件**：

| 测试文件 | 覆盖范围 |
|----------|----------|
| `tests/admin/test_admin_auth.py` | Login flow, logout, session validation, rate limiting, invalid credentials, bcrypt edge cases |
| `tests/admin/test_admin_tenants.py` | CRUD, disable cascade, status transitions, duplicate tenant_id rejection, format validation |
| `tests/admin/test_admin_keys.py` | Key creation (plaintext once), revocation, revoked key auth rejection, disabled tenant key rejection |
| `tests/admin/test_admin_logs.py` | Listing, pagination, filtering (time/level/scenario/tenant), detail view, empty state |
| `tests/admin/test_admin_health.py` | Status checks, history endpoint, all 5 services reporting, concurrent access safety |

**验收标准**：
- Admin 模块测试覆盖率 ≥ 60%
- `make test` 全部通过

**预计时间**：1 天

### 5.4 前端组件测试（新增，0.5 天）

**目标**：补齐前端组件测试（当前只有 2 个文件）。

**新增测试文件**：

| 测试文件 | 关键测试用例 |
|----------|-------------|
| `GatePanel.test.tsx` | Candidate display, approve/reject/regenerate actions |
| `CandidateSelector.test.tsx` | 3-candidate comparison, score display, selection |
| `AdminLogin.test.tsx` | Form validation, error display, redirect on success |
| `AdminDashboard.test.tsx` | Data loading state, metric cards display, empty state, error state + retry |

**测试模式**：Vitest + @testing-library/react，遵循现有 `SettingsPanel.test.tsx` 模式。

**验收标准**：
- 4 个新测试文件全部通过
- `cd web && npm test` 通过

**预计时间**：0.5 天

### 5.5 循环导入根治

**目标**：不只是 patch `nodes.py`，而是全量排查并建立防循环机制。

**执行步骤**：
1. **全量扫描**：`python -c "import src.api"` 验证无循环导入；`pytest tests/ --collect-only` 验证所有测试模块可导入
2. **根因分析**：`_state.py` 同时承担"共享状态"和"pipeline 初始化"两个职责，这是循环的根源
3. **边界重构**：
   - `_state.py` 拆分为 `_state.py`（纯数据结构）和 `_pipeline_init.py`（pipeline 初始化逻辑）
   - `routers/pipeline.py` 和 `routers/scenario.py` 从 `_pipeline_init.py` 导入
   - `graph/nodes.py` 只从 `_state.py` 导入（已通过延迟导入解决）

**验收标准**：
- `python -c "import src.api"` 成功
- `make test` 全部通过
- 新增模块的导入关系图无循环

**预计时间**：0.5 天

### 5.6 Wave 2 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| Gate 系统测试需要构造低分输入，mock auditor 失效 | 低 | 使用固定 score mock，不动生产阈值 |
| Assets 上传链路涉及文件系统 + PG + Remotion，任一环节失败难定位 | 中 | 每步单独验证，失败时检查对应环节日志 |
| 故障注入测试可能污染 production error_logs | 低 | 使用 test tenant + 测试后清理 |
| Admin 测试需要 mock bcrypt/PG 依赖，环境搭建复杂 | 中 | 复用现有测试 fixtures 和 mock 模式 |
| _state.py 拆分引入新的导入问题 | 中 | 每步修改后运行 `python -c "import src.api"` 验证 |

## 6. Wave 3 详细设计 — 集成验证与 E2E（5 天）

### 6.1 P2 路径：时间允许（1.5 天）

#### 6.1.1 Distribution 真实发布（C）

**目标**：验证 `POST /distribution/publish` + TikTok / Shopify connector 实际发布。

**执行步骤**：
1. **TikTok 发布**：准备测试账号和 sandbox 环境，调用发布接口，验证视频成功上传（或 sandbox 返回正确响应）
2. **Shopify 发布**：准备测试店铺和产品，调用发布接口，验证产品/视频正确关联
3. **多平台同时发布**：一次请求同时发布到 TikTok + Shopify，验证 `publish_engine.py` 的并行 orchestration 正确工作，部分平台失败时错误隔离

**验收标准**：
- 至少一个平台真实发布成功
- `publish_logs` 表记录完整
- 部分失败时错误信息准确，成功平台不受影响

**外部依赖**：TikTok/Shopify sandbox credentials。**如果拿不到，降级为 mock connector 验证 orchestration 逻辑。**

**预计时间**：1 天

#### 6.1.2 Webhook 事件分发（F）

**目标**：验证 `audit.completed` / `pipeline.completed` 事件正确触发和投递。

**执行步骤**：
1. 使用 `webhook.site` 或本地 `nc -l` 作为临时接收端，配置 `WEBHOOK_URLS`
2. 运行完整 S1 pipeline，验证 `pipeline.completed` 事件触发；如果 Gate 被触发，验证 `audit.completed` 事件触发
3. 检查接收端收到的 payload 结构正确（包含 `thread_id`、`total_duration_ms`、`error_count` 等字段）

**验收标准**：
- 事件在正确时机触发
- Payload 结构符合预期
- 投递失败时重试机制工作（如有配置）

**预计时间**：0.5 天

### 6.2 E2E 自动化回归（新增，2 天）

**目标**：建立 6 个关键用户旅程的 Playwright 自动化回归测试。

**新增 E2E 脚本**：

| # | 旅程 | 步骤 |
|---|------|------|
| 1 | Admin: tenant + key lifecycle | Login → create tenant → create key → copy key → verify in list |
| 2 | S1 Product Direct (auto) | Input product info → auto pipeline → wait for completion → download video |
| 3 | S5 Brand VLOG | Select brand + models → run pipeline → verify output |
| 4 | Fast Mode | Input text → generate → verify video appears |
| 5 | Footage browsing | Open /footage → switch categories → click preview → verify modal |
| 6 | Admin: error visibility | Trigger a pipeline error → navigate to admin logs → verify error appears |

**执行方式**：Headless Chromium in CI。每次 deploy gate 运行。

**验收标准**：
- 6 个旅程全部 green
- 在 CI 中自动运行（每次 push 到 main）

**预计时间**：2 天

### 6.3 pyright strict 全启

**目标**：启用 `reportUnknownMemberType` / `reportUnknownVariableType`，将 `dict[str, Any]` 替换为具体类型。

**执行策略**：

**不追求 100% 零错误**。策略是：

1. **扫描影响面**：运行 `pyright --outputjson src/ | jq '.generalDiagnostics | length'` 统计错误数量
2. **优先级排序**：
   - P0：`src/routers/`、`src/graph/` — 核心链路
   - P1：`src/pipeline/`、`src/skills/` — 业务逻辑
   - P2：`src/agents/`、`src/tools/` — 工具层，可延后
3. **分批修复**：每次修复一个模块，确保 `make typecheck` 通过后再继续
4. **建立类型基线**：为高频数据结构（`ProductCatalog`、`PipelineConfig`、`AuditReport`）创建 TypedDict / Pydantic model

**验收标准**：
- P0 模块 0 错误
- P1 模块错误数 ≤ 10
- 新增具体类型定义 ≥ 5 个

**预计时间**：1.5 天

### 6.4 Wave 3 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| TikTok/Shopify credentials 拿不到 | 高 | 降级为 mock connector 验证 orchestration 逻辑 |
| E2E 测试不稳定（前端加载时间波动） | 中 | 增加 wait 策略和重试机制 |
| pyright strict 全启错误数远超预期 | 中 | 不追求 100% 零错误，P0 模块 0 错误即可 |
| Webhook 临时接收端不稳定 | 低 | 使用 webhook.site，或本地自建简单 HTTP 服务器 |

## 7. Wave 4（可选扩展）— 运维就绪（5 天）

> Wave 4 不在用户当前选择的 1+2（测试 + 代码质量）范围内，但作为生产就绪的完整闭环列出，供后续决策。

### 7.1 监控扩展

**Prometheus 新增指标**：

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `pipeline_active_gauge` | Gauge | 当前运行中的 pipeline 数 |
| `llm_api_errors_total` | Counter | LLM API 错误按 provider 分 |
| `llm_api_duration_seconds` | Histogram | LLM API 调用延迟 |
| `db_pool_available_connections` | Gauge | 数据库连接池水位 |
| `admin_login_attempts_total` | Counter | Admin 登录尝试（成功/失败）|
| `tenant_active_count` | Gauge | 活跃租户数 |

### 7.2 告警规则（4 条）

| 告警 | 条件 | 严重度 | 通知 |
|------|------|--------|------|
| Pipeline 失败率飙升 | > 30% failure in 15 min | P0 | DingTalk webhook |
| LLM API 不可用 | 3 次连续健康检查失败 | P0 | DingTalk webhook |
| DB 连接池耗尽 | Available < 2 持续 5 min | P1 | DingTalk webhook |
| 磁盘空间不足 | Output 目录 > 80% | P2 | 仅日志 |

### 7.3 Grafana Dashboard（3 面板）

1. **Service Health** — 5 个状态卡片（PG/DeepSeek/POYO/SiliconFlow/Remotion），带延迟
2. **Pipeline Overview** — 24h 运行量、成功率、按场景/错误码分错误分布
3. **Tenant Overview** — 活跃数、Top 10 API 调用量、受影响租户

### 7.4 备份策略

| 目标 | 方法 | 频率 | 保留 |
|------|------|------|------|
| PostgreSQL | `pg_dump` → `/backups/` → rsync | 每天 03:00 | 7 天 |
| Output assets | `rsync`（现有脚本）| 手动/按需 | — |
| `.env.prod` | 手动备份 | 每次变更后 | 永久 |

### 7.5 Runbook（5 个事件手册）

| # | 事件 | 位置 |
|---|------|------|
| 1 | DeepSeek API 超时/不可用 | `docs/guide/runbook/01-deepseek-outage.md` |
| 2 | POYO 内容审核拒绝 | `docs/guide/runbook/02-poyo-rejection.md` |
| 3 | Pipeline 卡在 running 状态 | `docs/guide/runbook/03-pipeline-stuck.md` |
| 4 | 数据库连接池耗尽 | `docs/guide/runbook/04-db-pool-exhausted.md` |
| 5 | Nginx 配置不生效 | `docs/guide/runbook/05-nginx-config.md` |

每个 runbook：≤ 300 字，覆盖 symptoms → diagnosis → mitigation → recovery verification。

## 8. 总体验收标准

| 维度 | 验收项 | 通过标准 |
|------|--------|----------|
| **测试覆盖** | 10 条未验证路径 | A-J 全部有验证报告，P0 路径(A/G/H)必须真实端到端通过 |
| **测试覆盖** | Admin Panel | 测试覆盖率 ≥ 60%，5 个测试文件全部通过 |
| **测试覆盖** | 前端组件 | ≥ 4 个新测试文件，Vitest 全部通过 |
| **测试覆盖** | E2E 回归 | 6 个旅程全部 green，CI 自动运行 |
| **代码质量** | pyright 类型检查 | P0 模块 0 错误，全项目增量错误 ≤ 20 |
| **代码质量** | 死代码清理 | `requirements.txt` 无 Redis/Celery，`make ci` 通过 |
| **代码质量** | 安全审计 | 5 项安全检查全部通过，0 高危漏洞 |
| **架构** | 循环导入 | `python -c "import src.api"` 成功，导入图无循环 |
| **运维** | 部署流程 | deploy.sh 无需手动干预，nginx 重启自动生效 |
| **运维**\* | 监控告警 | Prometheus ≥ 12 指标，4 条告警规则，Grafana 有数据 |
| **运维**\* | 备份恢复 | 备份脚本 + cron 配置，1 次成功全量备份 |

\* Wave 4 相关项，可选。

## 9. 总体风险与回退策略

| 风险 | 影响 | 回退 |
|------|------|------|
| Wave 2 的 _state.py 拆分引入 regression | 高 | 回滚到拆分前的 commit，重新设计拆分方案 |
| Distribution 真实测试 credentials 拿不到 | 中 | 用 mock connector 替代，不阻塞整体交付 |
| 并发压测发现 contextvars 隔离 bug | 高 | 修复 bug 后重新压测，Wave 3 延期 |
| pyright strict 错误数太多 | 低 | 缩小范围到 P0 模块，其余延后 |
| E2E 测试在 CI 中不稳定 | 中 | 增加重试机制，必要时降级为手动执行 |

## 10. 时间线

| 波次 | 时间 | 关键产出 |
|------|------|----------|
| Wave 1 | 第 1-4 天 | i18n 报告、Metrics 验证报告、安全审计报告、清理后的 requirements.txt、`make ci` 通过 |
| Wave 2 | 第 5-11 天 | P0/P1 路径验证报告、5 个 Admin 测试文件、4 个前端测试文件、无循环导入 |
| Wave 3 | 第 12-16 天 | P2 路径验证报告、6 个 E2E 旅程 green、pyright P0 0 错误 |
| Wave 4\* | 第 17-21 天 | Prometheus 扩展、4 条告警规则、Grafana Dashboard、5 个 Runbook |

**Wave 1-3 总计 16 天**（含新增的安全审计、Admin 测试、前端测试、E2E、故障注入扩展）。

**Wave 1-4 总计 21 天**（含运维就绪）。

可根据实际进度调整。P2 路径和 Wave 4 为可裁剪项，不影响核心交付。
