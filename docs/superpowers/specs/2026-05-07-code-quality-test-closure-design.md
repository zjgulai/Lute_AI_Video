---
title: 代码质量梳理与测试闭环 — 分波次交付方案
doc_type: architecture
module: engineering
module: engineering
topic: code-quality-test-closure
status: review
created: 2026-05-07
updated: 2026-05-07
owner: self
source: human+ai
---

# 代码质量梳理与测试闭环 — 分波次交付方案

## 1. 概述

Admin Panel Phase 1 和生产部署修复（ChunkLoadError / 循环导入 / nginx 语法）已发布上线。当前项目进入**整合交付阶段**：需要系统性地补齐测试缺口、清理代码质量债、建立可重复的生产验证流程。

本方案覆盖两个领域：
- **测试闭环**：CLAUDE.md 中列出的 10 条未验证路径（A-J）
- **代码质量**：pyright strict 剩余规则、循环导入根治、死代码清理、模块边界梳理

## 2. 核心原则

**由内到外、由低风险到高风险、每波都有可验证产出。**

三个波次不是简单的线性顺序，而是有明确的依赖关系。每波结束后产出可独立验证的交付物，前面的波次为后面的波次建立基线。

## 3. 总体架构

```
Wave 1 (基线清理) ──→ Wave 2 (核心链路) ──→ Wave 3 (生产验证)
  3 天                  5 天                  5 天
```

### 3.1 波次分解

| 波次 | 测试任务 | 代码质量任务 | 产出 |
|------|----------|--------------|------|
| **Wave 1** | i18n 全量走查(I)、Metrics 验证(D) | 死代码清理(Redis/Celery)、pyright 扫尾 | 干净代码基线 + 2 份验证报告 |
| **Wave 2** | Gate 系统闭环(B)、Assets 上传(E)、错误降级(G) | 循环导入根治、_state.py 边界重构 | 核心链路测试基线 + 架构债务清理 |
| **Wave 3** | Distribution 真实发布(C)、并发压测(H)、Webhook(F) | pyright strict 全启、模块边界梳理 | 生产级健壮性验证 |

### 3.2 关键决策

1. **Wave 1 放在最前**：死代码清理和类型补全几乎零风险，i18n 和 Metrics 是纯验证任务。这些产出提供"项目在推进"的信心，同时清理出干净的代码基线。
2. **Gate 系统(B) 放在 Wave 2**：Gate 是产品核心卖点（Expert Studio 3-candidate + approval），如果 Gate 有 bug，Admin Panel Phase 1 的 Tenant 管理、所有场景的 checkpoint 逻辑都受影响。
3. **Distribution(C) 放在 Wave 3**：需要外部平台 credentials，这是外部依赖，不控制在我们手里。如果 credentials 拿不到，不能阻塞前面所有工作。
4. **pyright strict 全启放在 Wave 3**：启用 `reportUnknownMemberType` / `reportUnknownVariableType` 需要大量 `dict[str, Any]` → 具体类型的替换，ROI 低且可能引入编译错误。放在最后，前面两波已经建立了测试保护。

## 4. Wave 1 详细设计 — 低风险快速验证（3 天）

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

### 4.5 Wave 1 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| i18n 发现大量遗漏需要大面积改文案 | 低 | 用脚本扫描 diff，遗漏通常只有少量新增页面 |
| Metrics 表 schema 与代码期望不一致 | 中 | 先查 PG schema，不一致时优先改代码对齐 |
| 移除 Redis/Celery 后发现某个隐藏引用 | 低 | `grep -rn "redis\|celery" src/` 全量扫描 |
| pyright 扫尾发现新错误数量超出预期 | 低 | Phase 4 已建立基线，增量通常 < 10 个 |

## 5. Wave 2 详细设计 — 核心链路测试基线（5 天）

### 5.1 Gate 系统全链路闭环（B）

**目标**：验证 `POST /scenario/s1/gate/.../generate` → 3 候选生成 → `CandidateScorer` 评分 → 前端 `CandidateSelector` 对比 → `regenerate/{candidate}` 单候选重生成 → `approve` 触发后台续跑。

**为什么放在 Wave 2**：Gate 是产品核心卖点（Expert Studio），如果 Gate 有 bug，Phase 1 的所有 checkpoint 逻辑都受影响。

**执行步骤**：

**Step 1 — 构造触发条件**
- 使用 mock `auditor.py` 返回固定 score（如 0.75），确保 score 落在 0.60-0.90 区间触发 HITL
- 不动生产 `quality_thresholds.json`

**Step 2 — 3 候选生成**
- `POST /scenario/s1/gate/{label}/strategy_audit/generate`
- 验证返回 3 个 candidate（standard/creative/conservative）
- 验证 `CandidateScorer` 每个候选都有 score

**Step 3 — 前端对比 + 单候选重生成**
- 前端 `CandidateSelector` 正确渲染 3 个候选
- `POST /scenario/s1/gate/.../regenerate/1` 重生成第 2 个候选
- 验证新候选与旧候选不同

**Step 4 — 选定 + 批准 + 后台续跑**
- `POST /scenario/s1/gate/.../approve` with `APPROVED`
- 验证后台任务启动（pipeline 继续执行到下一个 checkpoint）
- 验证 `pipeline_degraded` 不为 True

**Step 5 — 拒绝分支**
- 重新触发 Gate，`approve` with `REJECTED`
- 验证 pipeline 终止到 `__end__`

**Step 6 — CHANGES_REQUESTED 分支**
- `approve` with `CHANGES_REQUESTED`
- 验证 retry count 增加，D10 contextvars 路由覆写生效

**验收标准**：
- 三个分支（APPROVED / CHANGES_REQUESTED / REJECTED）全部通过
- 每个分支至少验证一次完整的端到端流程
- 后台续跑后 pipeline 成功到达 `__end__` 或下一个 checkpoint

**预计时间**：2 天

### 5.2 Assets 上传全链路（E）

**目标**：验证"上传 → 后端落盘 → 管线引用 → 出现在最终视频"完整链路。

**执行步骤**：
1. 在 `/brand-packages` 或 `/footage` 页面通过 `GuidedCard` 文件选择上传，验证后端 `/api/upload` 返回 200
2. 验证文件写入 `OUTPUT_DIR`，PG `brand_packages` / 相关表有记录
3. 验证文件可通过 `/api/media/` 访问
4. 在 S1 pipeline 中引用上传的资产，验证资产出现在 storyboard / media_generation 输出中
5. 验证 Remotion 组装时正确引用了上传资产，最终视频文件存在且可播放

**验收标准**：
- 上传文件在 `OUTPUT_DIR` 中存在且大小正确
- PG 表中有正确记录
- Pipeline 输出中引用路径正确
- 最终视频包含上传资产（视觉确认或 hash 比对）

**预计时间**：1 天

### 5.3 错误降级路径（G）

**目标**：验证 `pipeline_degraded = True` 触发后，管线正确终止，错误上报链路通畅。

**执行步骤**：
1. **Mock POYO 故障**：临时将 `POYO_API_BASE_URL` 改为无效地址，运行 S1 pipeline，验证 media_generation 节点失败后 `pipeline_degraded = True`，routing 函数检查 `_degraded_guard` 后终止到 `__end__`
2. **Mock DeepSeek 故障**：类似步骤 1，但故障点在 strategy 节点
3. **错误上报链路**：验证 `ErrorCollector.collect()` 自动写入 `error_logs` 表，Admin Logs 页面可查询

**验收标准**：
- 两种 mock 故障下 pipeline 均优雅终止（不崩溃、不 hang）
- `error_logs` 表中有正确记录
- Admin Logs 页面可见
- `pipeline_degraded = True` 后不再执行后续节点

**预计时间**：1 天

### 5.4 循环导入根治

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

**预计时间**：1 天

### 5.5 Wave 2 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| Gate 系统测试需要构造低分输入，mock auditor 失效 | 低 | 使用固定 score mock，不动生产阈值 |
| Assets 上传链路涉及文件系统 + PG + Remotion，任一环节失败难定位 | 中 | 每步单独验证，失败时检查对应环节日志 |
| 错误降级测试可能污染 production error_logs | 低 | 使用 test tenant + 测试后清理 |
| _state.py 拆分引入新的导入问题 | 中 | 每步修改后运行 `python -c "import src.api"` 验证 |

## 6. Wave 3 详细设计 — 生产级健壮性验证（5 天）

### 6.1 Distribution 真实发布（C）

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

**预计时间**：2 天

### 6.2 并发压测（H）

**目标**：同时跑 2+ 场景使用不同 API key，验证 `contextvars` 隔离不串。

**执行步骤**：
1. **单场景并发**：同时启动 3 个 S1 pipeline，使用不同 `product_catalog`，验证每个 pipeline 的输出与输入对应
2. **跨场景并发**：同时启动 S1 + S5，S1 使用 key A，S5 使用 key B，验证 LLM client、POYO client、Seedance client 三处 contextvars 读取正确
3. **API Key 隔离**：key A 故意设置无效 POYO key，key B 使用有效 POYO key，验证 S1 失败、S5 成功

**验收标准**：
- 并发场景下所有输出与输入一一对应
- API key 隔离生效
- 无 `contextvars` 泄漏或串扰

**工具**：`locust` 或 `wrk` 做并发请求，`asyncio.gather` 在 Python 层做并发验证。

**预计时间**：1 天

### 6.3 Webhook 事件分发（F）

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

### 6.4 pyright strict 全启

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

### 6.5 Wave 3 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| TikTok/Shopify credentials 拿不到 | 高 | 降级为 mock connector 验证 orchestration 逻辑 |
| 并发压测触发 rate limit | 中 | 使用不同 IP 或降低并发数 |
| pyright strict 全启错误数远超预期 | 中 | 不追求 100% 零错误，P0 模块 0 错误即可 |
| Webhook 临时接收端不稳定 | 低 | 使用 webhook.site，或本地自建简单 HTTP 服务器 |

## 7. 总体验收标准

| 维度 | 验收项 | 通过标准 |
|------|--------|----------|
| **测试覆盖** | 10 条未验证路径 | A-J 全部有验证报告，其中 B/C/D 必须有真实端到端通过 |
| **代码质量** | pyright 类型检查 | P0 模块 0 错误，全项目增量错误 ≤ 20 |
| **代码质量** | 死代码清理 | `requirements.txt` 无 Redis/Celery，`make ci` 通过 |
| **架构** | 循环导入 | `python -c "import src.api"` 成功，导入图无循环 |
| **运维** | 部署流程 | deploy.sh 无需手动干预，nginx 重启自动生效 |

## 8. 总体风险与回退策略

| 风险 | 影响 | 回退 |
|------|------|------|
| Wave 2 的 _state.py 拆分引入 regression | 高 | 回滚到拆分前的 commit，重新设计拆分方案 |
| Distribution 真实测试 credentials 拿不到 | 中 | 用 mock connector 替代，不阻塞整体交付 |
| 并发压测发现 contextvars 隔离 bug | 高 | 修复 bug 后重新压测，Wave 3 延期 |
| pyright strict 错误数太多 | 低 | 缩小范围到 P0 模块，其余延后 |

## 9. 时间线

| 波次 | 时间 | 关键产出 |
|------|------|----------|
| Wave 1 | 第 1-3 天 | i18n 报告、Metrics 验证报告、清理后的 requirements.txt、`make ci` 通过 |
| Wave 2 | 第 4-8 天 | Gate 闭环验证报告、Assets 上传验证报告、错误降级验证报告、无循环导入 |
| Wave 3 | 第 9-13 天 | Distribution 验证报告、并发压测报告、Webhook 验证报告、pyright P0 0 错误 |

**总计 13 天**，可根据实际进度调整。
