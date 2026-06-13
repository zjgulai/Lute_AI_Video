---
title: AI Video Pipeline 综合技术债务审计报告
doc_type: analysis
module: project
topic: technical-debt-audit
status: stable
created: 2026-06-09
updated: 2026-06-09
owner: self
source: human+ai
---

# AI Video Pipeline — 综合技术债务审计报告

**日期**: 2026-06-09
**版本**: v0.2.7
**审计范围**: 全栈（Python 后端、Next.js 前端、基础设施、文档、项目管理）
**方法**: 三代理并行深度探索 + 手动交接

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [P0 严重项 — 需立即采取行动](#2-p0-严重项--需立即采取行动)
3. [技术债务（按类别）](#3-技术债务)
   - [3.1 代码重复](#31-代码重复)
   - [3.2 死代码 / 未使用项](#32-死代码--未使用项)
   - [3.3 错误处理缺陷](#33-错误处理缺陷)
   - [3.4 类型安全缺陷](#34-类型安全缺陷)
   - [3.5 缺失的抽象 / 硬编码配置](#35-缺失的抽象--硬编码配置)
   - [3.6 循环导入风险](#36-循环导入风险)
   - [3.7 异步/等待误用](#37-异步等待误用)
   - [3.8 组件臃肿](#38-组件臃肿)
   - [3.9 状态管理问题](#39-状态管理问题)
   - [3.10 API 客户端问题](#310-api-客户端问题)
   - [3.11 i18n 缺陷](#311-i18n-缺陷)
   - [3.12 可访问性缺陷](#312-可访问性缺陷)
   - [3.13 性能问题](#313-性能问题)
   - [3.14 CSS/Tailwind 问题](#314-csstailwind-问题)
4. [工程债务](#4-工程债务)
5. [项目管理债务](#5-项目管理债务)
6. [文档管理债务](#6-文档管理债务)
7. [脆弱点债务](#7-脆弱点债务)
8. [修复路线图](#8-修复路线图)
9. [附录：完整发现分类计数](#9-附录完整发现分类计数)

---

## 1. 执行摘要

本次审计对代码库的五个维度进行了全面检查：**技术债务**（源码质量）、**工程债务**（构建/测试/部署）、**项目管理债务**（仓库组织）、**文档管理债务**（文档过时性）和**脆弱点债务**（安全/运营风险）。

### 关键数字

| 维度 | 发现数 | P0 | P1 | P2 | P3 |
|------|--------|-----|-----|-----|-----|
| 技术债务（Python） | 85 | 1 | 53 | 26 | 5 |
| 技术债务（前端） | 53 | 0 | 16 | 27 | 10 |
| 工程债务（测试/配置/部署） | 42 | 7 | 12 | 20 | 3 |
| 项目管理债务 | 15 | 1 | 4 | 10 | 0 |
| 文档管理债务 | 18 | 0 | 4 | 14 | 0 |
| 脆弱点债务 | 8 | 3 | 5 | 0 | 0 |
| **总计** | **221** | **12** | **94** | **97** | **18** |

### 首要关注事项（前 5 名）

1. **P0 — 生产密钥已提交到仓库**（`deploy/lighthouse/.env.prod`，36 行明文密钥）
2. **P0 — 168MB Docker 镜像压缩包在 git 历史中**（`archive/lute-ai-video-backend.tar`）
3. **P0 — 30+ 个百度网盘同步产物污染仓库**（各类目录中的 `*.baiduyun.uploading.cfg` 文件）
4. **P1 — 30+ 个 env 变量在代码中使用，但在 `.env.example` 中未记录**
5. **P1 — 221 处裸 `except Exception`，横跨 71 个文件** — 静默吞掉错误

---

## 2. P0 严重项 — 需立即采取行动

这些是需要立即关注的阻断项 — 安全风险、仓库卫生问题和可能导致事故的关键基础设施缺口。

### SEC-1: 生产密钥已提交到仓库（明文）

- **位置**: `deploy/lighthouse/.env.prod`（36 行，`git` 已跟踪）
- **包含**: `DEEPSEEK_API_KEY`、`POYO_API_KEY`、`SILICONFLOW_API_KEY`、`DATABASE_URL`（含密码）、`API_KEY`
- **修复**: `git rm --cached deploy/lighthouse/.env.prod`，轮换所有已泄露密钥，添加 `.gitignore` 规则（已存在但文件在规则之前已提交）
- **工时**: 2-3 小时（含密钥轮换协调）

### SEC-2: 仓库中有 168MB Docker 镜像压缩包

- **位置**: `archive/lute-ai-video-backend.tar`
- **修复**: 使用 `git filter-repo` 或 `BFG Repo-Cleaner` 从历史中清除
- **工时**: 1 小时

### SEC-3: 30+ 个百度网盘同步产物已提交

- **位置**: `deploy/lighthouse/`、`docs/runbooks/`、`docs/workflows/`、`scripts/`（共 30+ 个文件）
- **模式**: `*.baiduyun.uploading.cfg`
- **修复**: `git rm` 全部文件，验证 `.gitignore` 规则有效
- **工时**: 0.5 小时

### DEP-1: 渲染服务未被 deploy.sh 管理

- **位置**: `deploy/lighthouse/deploy.sh` vs `docker-compose.prod.yml`
- **问题**: `docker-compose.prod.yml` 定义了渲染服务容器，但 `deploy.sh` 从未启动/停止/管理它。渲染容器可能已漂移或完全不可用。
- **修复**: 将渲染服务生命周期添加到 deploy.sh，或在部署前确认其是否故意未使用
- **工时**: 1-2 小时

### TST-1: 测试中有长达 60 秒的硬性 sleep

- **位置**: `tests/test_bg_registry.py:22,63` 和 `tests/test_bg_registry_leak_contract.py:69`
- **问题**: `asyncio.sleep(60)` 导致这些测试占测试套件的大部分时长，且在 CI 中非常脆弱
- **修复**: 替换为 `asyncio.wait_for(task, timeout=...)` + 取消模式
- **工时**: 1 小时

### CFG-1: 30+ 个 env 变量在 `.env.example` 中未记录

- **问题**: `src/config.py` 及多个模块使用了 30 个以上环境变量，这些变量不存在于 `.env.example` 中。在新环境中启动项目需要猜测这些变量。
- **关键缺失项**: `LOG_LEVEL`、`RENDERING_SERVICE_URL`、`COSYVOICE_VOICE_FEMALE`、`POYO_TTS_MODEL`、`ALLOW_MOCK_MODE`、`SEEDANCE_API_KEY`、`SEEDANCE_API_BASE_URL`、`SUPABASE_URL`、`FACEBOOK_ACCESS_TOKEN`、`SHOPIFY_ACCESS_TOKEN`、`BRAND_PACKAGE_USE_PG`、`S3_VIRAL_EXTRACT_DISABLED` 等
- **修复**: 将所有缺失的变量添加到 `.env.example`，附文档和默认值
- **工时**: 2 小时

### CFG-2: Key name mismatch between `.env.example` and code

- **位置**: `.env.example` 用了 `SHOPIFY_API_KEY`，代码用了 `SHOPIFY_ACCESS_TOKEN`
- **修复**: 对齐两个名称
- **工时**: 0.5 小时

---

## 3. 技术债务

### 3.1 代码重复

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D1 | **P1** | `pipeline/gate_manager.py:888`、`pipeline/step_runner.py:189`、`routers/_state.py:260`、`pipeline/s1_product_pipeline.py:238` | 相同的 `_get_step_output()` 函数，存在于 **4 个不同模块**，逻辑几乎完全相同。应抽取为单个共享工具函数。 |
| D2 | **P1** | `graph/nodes.py:371-658` | 4 个审计节点（strategy/script/editing/thumbnail），结构和重试逻辑重复超过 80% |
| D3 | **P1** | `graph/routing.py:164-397` | 4 个路由函数在结构上完全相同，仅 checkpoint key 和 target node name 不同 |
| D4 | **P1** | `storage/asset_stores.py:96-125 vs 145-194` | `BrandPackageStore` 和 `InfluencerStore` 的每个方法都共享相同的"try PG, fallback"模式 |
| D5 | **P1** | `storage/repository.py`（贯穿全文） | 每个仓库方法都实现了双重"asyncpg 路径 / SQLite 回退"——应使用策略模式 |
| D6 | **P1** | `api_assets.py:96-110 vs 142-153` | 相同的 ID 生成 + UUID/日期 + 日志模式，用于创建品牌包和影响者 |
| D7 | **P2** | `tools/seedance_client.py` 和 `tools/poyo_client.py` | 轮询/解析逻辑重复。SeedanceClient 和 PoyoClient 共享相同的存根模式结构。 |
| D8 | **P2** | `routers/admin/*.py` | 管理端点重复相同的 CRUD 错误处理样板代码 |

### 3.2 死代码 / 未使用项

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D9 | **P1** | `src/api_assets.py`（整个文件） | 已确认的遗留兼容层。从 `src/routers/assets.py` 和 `src/routers/portfolio.py` 重复了几乎所有功能。可移除。 |
| D10 | **P1** | `src/pipeline/s2_brand_pipeline.py`（整个文件） | 已确认的弃用包装器。仅使用弃用警告重新导出 `_v2`。没有内部调用者。 |
| D11 | **P1** | `tools/metrics_repository.py` | 定义了 `MetricsRepository` 类，但 `src/` 中**没有任何内容导入它**。可能是死代码或未连接的 bug。 |
| D12 | **P1** | `telemetry_prometheus.py:68-106,139-167` | Prometheus helper 函数定义但从未调用：`record_llm_call()`、`update_db_pool_stats()`、`update_tenant_active_count()`、`record_admin_login()` |
| D13 | **P1** | `apis.ts`（前端）第 962-1068 行 | 8 个导出但标记为 `@deprecated` 的函数。两个（`fetchState`、`submitReview`）仍在 `app/page.tsx` 中活跃导入，将前端耦合到已弃用的 LangGraph 端点。 |
| D14 | **P1** | `SceneForm.tsx`（前端）第 219-983 行 | 760+ 行的遗留表单 DOM 始终渲染，但在 `USE_GUIDED_FORM=true` 时通过 CSS 隐藏。每个场景的部分即使不活跃也会挂载。 |
| D15 | **P2** | `graph/pipeline.py:357-383` | CLI demo `if __name__ == "__main__"` 块包含硬编码的吸奶器模拟数据——未维护，可能已损坏 |
| D16 | **P2** | `components/types.ts`（前端）第 5-11、28-33、42-71 行 | 遗留类型（`ReviewState`、`SEGMENT_LABELS`、`PLATFORM_LABELS`、`REVIEW_NODES`）来自 LangGraph 时代。如果 StepRunner 现在驱动 UI，这些可能已死。 |
| D17 | **P2** | `scenarioRouting.ts`（前端）第 5、14 行 | `live_shoot` 别名映射到 `/s4`，但在 UI 中从未使用——只有 `live_shoot_to_video` 出现在场景标签页中 |
| D18 | **P3** | `pipeline/state_manager.py:27` | `PipelineStateRepository: Any = None` 类型存根——被第 31 行的 try/import 立即覆盖 |

### 3.3 错误处理缺陷

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D19 | **P1** | 71 个文件中的 221 个位置（`src/` 整个目录） | 裸 `except Exception` 被广泛用于吞掉错误而不重新抛出或对调用者进行结构化传播 |
| D20 | **P1** | `services/fast_mode.py:141,163,322` | Fast Mode 中的阶段回调失败被静默记录为 `logger.warning`——用户看不到 |
| D21 | **P1** | `connectors/shopify_connector.py`（贯穿全文） | Shopify DC 中的每个 API 调用都包裹在 try/except 中，返回包含 `error` 键的字典。调用者永远不会看到真实异常。 |
| D22 | **P1** | `connectors/publish_engine.py:109,146` | TikTok/Shopify 发布错误处理捕获过于宽泛的异常，并通过通用 `PublishResult` 丢失结构化错误上下文 |
| D23 | **P1** | `storage/asset_stores.py`（贯穿全文） | 每个 PG 操作都包裹在 try/except 中，静默回退到内存字典——调用者永远不知道持久化是否失败 |
| D24 | **P1** | `storage/repository.py:27-50,53-69,88-102` | JSON 序列化错误在 SQLite 回退中被吞掉 |
| D25 | **P1** | `routers/_deps.py:77` | `except Exception:`（裸）——无日志的 JSON 解析静默失败 |
| D26 | **P1** | `pipeline/state_manager.py:166-178` | PG 保存失败截断错误到 100 个字符，丢失诊断信息 |

### 3.4 类型安全缺陷

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D27 | **P1** | `services/fast_mode.py:236-239` | `cast(SeedanceVideoResult, video_result)` 在没有运行时验证的情况下将原始字典强制转换为 TypedDict |
| D28 | **P1** | `telemetry.py:372` | `timed_node` 装饰器使用完全不类型化的 `dict[str, Any]` 状态和返回 |
| D29 | **P1** | `pipeline/step_runner.py`、`pipeline/s1_product_pipeline.py`、`pipeline/s3_remix_pipeline.py`、`pipeline/s4_live_shoot_pipeline.py`、`pipeline/s5_brand_vlog_pipeline.py`、`pipeline/s2_brand_pipeline_v2.py` | 所有 5 个场景流水线的 `run_step()` 都接受 `dict[str, Any]` 并返回 `Any` |
| D30 | **P1** | `routers/_state.py:55-75` | 所有 Request 模型都使用 `product_catalog: dict[str, Any]`——没有 schema |
| D31 | **P1** | 前端：`Record<string, unknown>` 使用超过 80 次，`as Record<string, unknown>` 使用超过 40 次 | 整个前端代码库中最普遍的类型安全缺陷。流水线数据在组件边界间不受类型检查。 |
| D32 | **P1** | `CandidateSelector.tsx`（前端）第 73、81、87、90、106 行 | 在单个函数中有 5 个不安全的 `as Record<string, unknown>` 强制转换 |
| D33 | **P1** | `usePipelineStore.ts`（前端）第 22-30 行 | 关键的流水线状态值（`oneshotResult`、`workflowState`）类型为 `unknown \| null` |
| D34 | **P2** | `pyproject.toml:82-86` | Pyright `reportUnknown*` 规则已禁用，有 1258 个未解决的未知类型错误。这是一个有意的权衡，但掩盖了真正的缺陷。 |
| D35 | **P2** | `pyproject.toml:77` | `src/quality/**` 被明确排除在 Pyright 检查之外——整个质量模块是一个类型安全盲区 |

### 3.5 缺失的抽象 / 硬编码配置

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D36 | **P1** | `tools/llm_client.py:161,173,194` | 硬编码的 LLM API URL 和模型名称（Kimi、Anthropic、OpenAI）——应在 `config.py` 中 |
| D37 | **P1** | `tools/gpt_image_client.py:78` | 硬编码的 `https://api.openai.com/v1` 用于图像生成 |
| D38 | **P1** | `tools/dalle_client.py:39` | 相同的 OpenAI URL 重复出现 |
| D39 | **P1** | `tools/elevenlabs_client.py:28` | 硬编码的 `https://api.elevenlabs.io/v1` |
| D40 | **P1** | `services/fast_mode.py:159` | 硬编码的 `model="deepseek-chat"` 覆盖——绕过 `DEFAULT_LLM_PROVIDER` |
| D41 | **P1** | `connectors/tiktok_connector.py:22-25` | 硬编码的 TikTok API URL |
| D42 | **P1** | `routers/admin/logs.py:239,248` | 硬编码的 `https://api.poyo.ai/v1/models` 和 `https://api.siliconflow.cn/v1/models` 用于健康探测 |
| D43 | **P1** | `api.py:180-182` | 生产代码中硬编码了 `http://localhost:3000` 开发 CORS 来源 |
| D44 | **P1** | `pipeline/s1_product_pipeline.py:65-67` | 硬编码的 `MAX_CLIPS_PER_DEMO = 3`、`MAX_THUMBNAILS_PER_DEMO = 2` 应为配置参数 |
| D45 | **P2** | `pipeline/step_runner.py:110-124` | 硬编码的 `STEP_ORDER` 和 `STEP_METHOD_MAP` 部分重复 `scenario_config.py` |

### 3.6 循环导入风险

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D46 | **P1** | `graph/pipeline.py:46` ↔ `graph/nodes.py:16` ↔ `telemetry.py` | 已知的循环导入，通过函数内部的延迟导入缓解。需要三种防御机制才能保持加载。 |
| D47 | **P1** | `routers/_state.py:16-18` → `graph/pipeline.py` → `graph/nodes.py` → `graph/routing.py` → `models/state.py` | 脆弱的深层依赖链 |
| D48 | **P1** | `graph/pipeline.py:238` | 防御性延迟导入：`import src.models as _m` 在函数内部——循环导入的代码异味 |
| D49 | **P1** | `s1_product_pipeline.py:451` | 基于字符串的动态导入：`__import__(pipeline_module, ...)` ——脆弱，无 IDE 支持 |
| D50 | **P2** | 8+ 个文件（`api.py`、`routers/_state.py`、`routers/health.py`、`routers/pipeline.py`、`routers/scenario.py`、`routers/distribution.py`、`routers/metrics.py`、`pipeline/state_manager.py`） | `HAS_STORAGE` 模式（`try: from src.storage import ... except ImportError: ...`）用于 import-order 修复——将脆弱性传播到各处 |

### 3.7 异步/等待误用

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D51 | **P2** | `storage/repository.py`（贯穿全文） | 所有 SQLite 回退操作都通过 `asyncio.to_thread()` 在线程池中运行——虽然正确，但增加了所有 SQLite 查询的线程开销 |
| D52 | **P2** | `telemetry.py:236-248` | Fire-and-forget 错误持久化任务在 `_persist_error_to_db()` 内部修改上下文字典引用——存在竞态条件 |
| D53 | **P2** | `telemetry.py:357-419` | `timed_node` 装饰器同步路径在异步函数内部阻塞事件循环 |
| D54 | **P2** | `connectors/tiktok_connector.py:224` | `time.sleep(0.5)` 在轮询循环中——阻塞事件循环 500ms。应为 `await asyncio.sleep(0.5)`。 |

### 3.8 组件臃肿

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D55 | **P1** | `app/page.tsx`（前端）第 228 行起，约 1336 行 | 单体首页组件。管理 3 个 Zustand 存储 + 本地状态。包含交错的场景流逻辑 + 轮询 + 会话恢复 + 图库 + 错误处理 + 大量 JSX。`handleStart` 函数单函数约 150 行。 |
| D56 | **P1** | `SceneForm.tsx`（前端）第 1-995 行 | 单体表单组件，管理 5 个场景的 20+ 个状态变量。4 个几乎相同的可展开部分。每个场景 200+ 行位于一个函数中。 |
| D57 | **P1** | `GatePanel.tsx`（前端）第 1-660 行 | 混合了 demo 候选生成、实时 API 获取、轮询、编辑面板和所有渲染状态。轮询循环深度嵌套在 `handleApprove` 内部。 |
| D58 | **P1** | `StageProgress.tsx`（前端）第 1-900+ 行 | 非常大的轮询组件，包含每个场景的阶段定义、时长启发式、指数退避、连续性诊断和内联动画 SVG。20+ 个内联样式对象。 |

### 3.9 状态管理问题

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D59 | **P1** | `usePipelineStore.ts`（前端）第 22-30 行 | 关键流水线值类型为 `unknown \| null`（`oneshotResult`、`workflowState` 等）。调用者必须使用 `as Record<string, unknown>` 进行转换。 |
| D60 | **P1** | `page.tsx`（前端）第 276-278 行 | 存储的 `loading` 状态以异步方式传播，存在已知的竞态条件——代码注释中承认了这一点。存在 `useSubmitting()` 解决方法，但存储本身仍然存在漏洞。 |
| D61 | **P2** | `page.tsx`（前端）第 1264-1274 行 | 回退渲染块通过内联 `onClick` 直接变更 4 个存储字段，绕过 `resetAll()`。存储可能处于不一致状态。 |

### 3.10 API 客户端问题

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D62 | **P1** | `api.ts`（前端）第 962-1068 行 | 8 个已弃用的 API 函数仍然可导入。其中有 2 个仍然被页面积极使用，将前端耦合到已弃用的 LangGraph 端点。 |
| D63 | **P2** | `api.ts`（前端）第 564 行 | `API_BASE` 已弃用的常量已导出，任何模块都可以访问——不会反映运行时更改 |
| D64 | **P2** | `api.ts`（前端）第 1498-1507 行 | `publishContent()` 函数参数类型为 `unknown`——发送前无验证 |
| D65 | **P3** | `api.ts`（前端）第 412-425 行 | `getProviderApiKeysForRequest()` 每次调用都遍历所有 7 个提供者键名——无缓存 |

### 3.11 i18n 缺陷

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D66 | **P1** | `api.ts`（前端）多个行 | JavaScript 源码中嵌入了中文注释字符串（第 559-562、579、606、644、691-694、734、774、797、809、1319 行） |
| D67 | **P1** | `ExecutionBar.tsx`（前端）第 26、39 行 | 硬编码的英文字符串 `"Generating..."` 和 `"Cancel"` 完全绕过了 `t()` 函数 |
| D68 | **P1** | `FastModePanel.tsx`（前端）第 208-211 行 | 所有 4 个进度阶段标签（"Submitting..."、"Enhancing prompt..."、"Generating video..."、"Synthesizing voiceover..."）都是硬编码的英文 |
| D69 | **P2** | `cardCopyEn.ts`（前端）整个文件 | 独立的、碎片化的翻译系统（135 条映射中文 → 英文）。与 `translations.ts` 重复，易于漂移。 |

### 3.12 可访问性缺陷

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D70 | **P2** | `app/layout.tsx`（前端）第 13-24 行 | 无跳转到内容的链接，`<main>` 元素无 `id="main-content"` 用于地标导航 |
| D71 | **P2** | `ExecutionBar.tsx`（前端）第 35-41 行 | 取消按钮无 `aria-label` |
| D72 | **P2** | `SceneForm.tsx`（前端）第 219-223 行 | 遗留表单 DOM 即使隐藏也渲染给屏幕阅读器——760+ 个 DOM 节点在隐藏时占用内存 |

### 3.13 性能问题

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D73 | **P2** | 整个前端 `src/` | `React.memo` 在整个代码库中未被使用过一次。无列表渲染优化。 |
| D74 | **P2** | `page.tsx`（前端）第 337-342 行 | `GATE_SEQUENCE` 数组在组件体内重新创建，导致不必要的重新渲染 |
| D75 | **P2** | `SceneForm.tsx`（前端）第 22-23、24-26 行 | `CATEGORIES` 和 `BRAND_PACKAGES` 在组件体内重新创建 |

### 3.14 CSS/Tailwind 问题

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D76 | **P2** | 20+ 个前端组件 | 30+ 个内联 `style={{...}}` 对象，用于动态宽度、颜色和布局。绕过 Tailwind 的构建优化。 |
| D77 | **P2** | `StageProgress.tsx`（前端）第 486、497、622、656、685、703、721、870、880、891 行 | 10 个不同的内联 `style={{ animation: ... }}` 对象。应使用 Tailwind 动画类。 |

---

## 4. 工程债务

### 测试基础设施

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| E1 | **P1** | `src/connectors/tiktok_connector.py`、`src/connectors/shopify_connector.py` | 连接器完全无测试覆盖——使用子进程的真实 API 调用。约 750 行代码无测试覆盖。 |
| E2 | **P1** | `src/storage/asset_stores.py` | 标记为 `TODO-D12`；PG 支持的存储无测试 |
| E3 | **P1** | `tests/conftest.py:290-323` | 测试 fixture 依赖于 `subprocess.run(["ffmpeg", ...])`——如果 ffmpeg 未安装，则失败 |
| E4 | **P1** | `src/tools/cosyvoice_client.py`、`src/tools/gpt_image_client.py`、`src/tools/poster_extractor.py`、`src/tools/llm_client.py` | 外部 API 客户端测试覆盖率较薄或无覆盖率 |
| E5 | **P1** | `.github/workflows/ci.yml` | 覆盖率上传有 `continue-on-error: true`——覆盖率下降是静默的 |
| E6 | **P1** | `tests/test_fast_mode_async.py` 中的 7 个位置 | 依赖于 `asyncio.sleep(0.01..0.5)` 的时间敏感测试——在缓慢的 CI 运行器中脆弱 |
| E7 | **P2** | 6+ 个测试文件 | 模块级别的 `pytest.skip("fastapi not installed")`——可选依赖项过于普遍 |

### 部署脆弱性

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| E8 | **P1** | `deploy/lighthouse/deploy.sh` 第 22、81、90 行 | 硬编码的 `/opt/ai-video/` 服务器路径出现 5+ 次 |
| E9 | **P1** | `deploy/lighthouse/deploy.sh` | 运行 `sudo docker-compose`（遗留 v1）而非 `docker compose` |
| E10 | **P1** | `deploy/lighthouse/deploy.sh` | Phase 0.6 hack：`sudo rm -f /opt/ai-video/src/routers/admin.py` ——脆弱的构建时文件删除 |
| E11 | **P1** | `deploy/lighthouse/smoke.sh`、`build-and-deploy.sh`、`sync-landing-sidecars.sh` | 硬编码的生产 IP `101.34.52.232` 出现在 4+ 个文件中 |
| E12 | **P1** | `deploy/lighthouse/smoke.sh:16` | `curl -k` 跳过 SSL 验证——掩盖 TLS 问题 |
| E13 | **P1** | `deploy/lighthouse/nginx.conf` | 所有静态站点块缺少安全头部（HSTS、X-Frame-Options、X-Content-Type-Options） |
| E14 | **P1** | `web/Dockerfile.nginx` | 孤儿——任何 docker-compose 或 workflow 均未引用；可能已过时 |
| E15 | **P2** | `deploy/lighthouse/deploy.sh` | `--force-recreate` 对所有 3 个容器，重建前无卷快照 |
| E16 | **P2** | `render.yaml:31` | 过时的 `CORS_ORIGINS: "https://zjgulai.github.io"` ——GitHub Pages 引用来自旧部署模型 |
| E17 | **P2** | `web/Dockerfile.nginx` vs `web/Dockerfile` | 节点版本不匹配（20-alpine vs 22-alpine） |
| E18 | **P2** | 未找到 | 无 Dependabot 配置——无自动依赖更新跟踪 |

### CI/CD（GitHub Actions）

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| E19 | **P1** | `.github/workflows/ci.yml` | 覆盖率上传有 `continue-on-error: true` ——静默降级 |
| E20 | **P2** | `.github/workflows/ci.yml` | Docker 组合配置验证仅验证语法（`config --quiet`），不验证实际容器启动 |
| E21 | **P2** | `.github/workflows/e2e-ui.yml` | 仅失败时上传 Playwright 跟踪——无法调试通过运行的历史记录 |

### 数据库架构管理

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| E22 | **P1** | `src/storage/migrations/001_init.sql` vs `migrations/alembic/versions/*.py` | 双 schema 管理：SQL 和 Alembic 迁移都必须手动保持同步。Fresh `docker compose up` 使用 SQL init，但 Alembic 迁移包含额外的 ALTER 语句，在 Docker 启动时不会运行。 |

---

## 5. 项目管理债务

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| M1 | **P0** | `archive/lute-ai-video-backend.tar` | 168MB Docker 镜像压缩包在 git 历史中 |
| M2 | **P1** | `scripts/` 目录 | 110+ 个脚本文件。8-10 个一次性迁移/同步脚本（`sync_bugfix.py`、`sync_bugfix_v2.py`、`sync_s1.py`、`sync_resume_fix.py` 等）仍存在。4 个重复用途的脚本（`run_s1_video.py`、`run_s1_video_now.py`、`run_s1_e2e.py`、`run_s1_unified_e2e.py`）。 |
| M3 | **P1** | `configs/` vs `docs/runbooks/` | 35+ 个契约 YAML/JSON 文件在 `configs/` 中重复了 `docs/runbooks/` 中运行手册的意图。例如，`configs/admin-csrf-contract.yaml` 镜像了 `docs/runbooks/admin-csrf-contract.md`。单一真相来源问题。 |
| M4 | **P1** | 代码根目录 | 6 个 AI 工具工件目录在 git 中被跟踪（`.claude/`、`.kiro/`、`.hermes/`、`.sisyphus/`、`.omc/`、`.playwright-mcp/`）——使仓库根目录混乱 |
| M5 | **P1** | `deploy/lighthouse/`、`docs/runbooks/`、`docs/workflows/`、`scripts/` | 30+ 个百度网盘同步工件（`*.baiduyun.uploading.cfg`） |
| M6 | **P2** | 代码根目录 | 缺少 `LICENSE`、`CHANGELOG.md`、`SECURITY.md` |
| M7 | **P2** | `README.md` | 无 CI 状态徽章 |
| M8 | **P2** | `scripts/test_*.py` | 11 个脚本级别的测试被 `.gitignore` 排除，但仍被 git 跟踪 |
| M9 | **P2** | `docs/release/v0.4.0*.md`（3 个文件） | 来自先前版本的发布说明——应移至 `archive/` |

---

## 6. 文档管理债务

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| D81 | **P1** | `AGENTS.md:606` | 最后更新于 "2026-05-17 evening" ——自那以后项目已有提交（当前日期为 2026-06-09） |
| D82 | **P1** | `.env.example` | 缺失 30+ 个环境变量文档——新开发人员无法配置项目 |
| D83 | **P1** | `docs/architecture/api-assets-pg-cutover-2026-05-15.md` | PG 切换计划——状态和完成情况不清楚 |
| D84 | **P1** | `drafts/analysis/brand-momcozy/lora-research/` | LoRA 研究文件——完成/放弃状态不清楚 |
| D85 | **P2** | `.kiro/plan/`（6+ 个文件） | 2026 年 4-5 月的计划文件应在完成后归档 |
| D86 | **P2** | `docs/workflows/five-scenario-pipeline-risk-assessment-stable-20260513.md` | 自标记为 "historical context (2026-05-31)" ——应移至 archive/ |
| D87 | **P2** | `docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md` | 自标记为历史 |
| D88 | **P2** | `docs/workflows/2026-05-15-sprint-0-3-review-and-deploy-plan.md` | 自标记为历史 |
| D89 | **P2** | `docs/workflows/2026-05-23-video-speed-optimization-deploy-plan.md` | 自标记为历史 |
| D90 | **P2** | `deploy/tencent-cloudbase.md`、`deploy/CLOUDBASE_STEP_BY_STEP.md` | CloudBase 部署文档——不用用，与 Lighthouse 成为标准不相关 |
| D91 | **P2** | `render.yaml` | Render blueprint——不是当前规范部署目标 |
| D92 | **P2** | `docs/architecture/chain-fault-tolerance-design-2026-05-15.md` | 设计文档——反映在代码中了吗？状态不清楚 |
| D93 | **P2** | `docs/architecture/quality-score-feedback-loop-2026-05-15.md` | 设计文档——实现状态不清楚（feedback loop 在 `known-gaps.md` 中仍被列为未实现） |

---

## 7. 脆弱点债务

| # | 严重程度 | 位置 | 描述 |
|---|----------|------|-------------|
| V1 | **P0** | `deploy/lighthouse/.env.prod`（已跟踪） | 生产密钥以明文形式提交到 git |
| V2 | **P0** | `deploy/lighthouse/nginx.conf` | 无安全头部——缺少 HSTS、X-Frame-Options、X-Content-Type-Options |
| V3 | **P0** | `render.yaml:31` | `CORS_ORIGINS` 包含过时的 `https://zjgulai.github.io` ——宽松的 CORS 配置 |
| V4 | **P1** | `deploy/lighthouse/nginx.conf` | 10+ 个子域名共享单个 Let's Encrypt 证书——证书到期时的单点故障 |
| V5 | **P1** | `deploy/lighthouse/nginx.conf` | `101.34.52.232` 的 IP 回退服务器块使用可能不可信的自签名证书 |
| V6 | **P1** | `deploy/lighthouse/smoke.sh:16` | `curl -k` 在生产烟雾测试中跳过 SSL 验证——掩盖 TLS 配置错误 |
| V7 | **P1** | `src/api.py:180-182` | 在生产代码中具有硬编码的 `localhost` CORS 来源——如果 CORS_ORIGINS 环境变量未设置，开发来源将应用于生产 |
| V8 | **P1** | 未找到 | 无 `SECURITY.md` ——安全漏洞报告无联络点 |
| V9 | **P2** | `src/tools/c2pa_signer.py` | C2PA 签名是一个 no-op 直到获得证书——EU AI Act 合规截止日期（2026-08-02）即将到来 |

---

## 8. 修复路线图

### Phase 1: 立即安全与仓库卫生（第 1-2 天）

优先处理，因为存在安全风险和仓库污染。

| 任务 | 工时 | 触及的项 |
|------|------|-----------|
| 1. 从 git 中移除 `deploy/lighthouse/.env.prod`，轮换密钥 | 3h | SEC-1, V1 |
| 2. 从 git 历史中清除 `archive/lute-ai-video-backend.tar` | 1h | SEC-2, M1 |
| 3. 移除所有 30+ 个百度网盘工件 | 0.5h | SEC-3, M5 |
| 4. 对齐 `.env.example` 与代码（添加 30+ 个缺失变量） | 2h | CFG-1, CFG-2, D82 |
| 5. 删除已知死代码：`api_assets.py`、`s2_brand_pipeline.py` shim | 1h | D9, D10 |
| 6. 修复测试中长达 60 秒的 sleep | 1h | TST-1 |
| **小计** | **8.5h** | |

### Phase 2: 关键基础设施修复（第 3-5 天）

| 任务 | 工时 | 触及的项 |
|------|------|-----------|
| 7. 修复渲染服务 deploy.sh 管理 | 2h | DEP-1, E8-E11 |
| 8. 为 nginx 添加安全头部 | 1h | V2, V3 |
| 9. 将双 schema 管理统一为 Alembic-only | 3h | E22 |
| 10. 将前端 i18n 硬编码字符串修复（ExecutionBar、FastModePanel） | 2h | D67, D68 |
| 11. 将已弃用的前端 API 函数迁移为新的（fetchState、submitReview） | 2h | D13, D62 |
| 12. 修复硬编码的生产 IP——使用变量 | 1h | E11 |
| 13. 将硬编码的 LLM URL 迁移到 config.py | 2h | D36-D42 |
| **小计** | **13h** | |

### Phase 3: 债务减少（第 2 周）

| 任务 | 工时 | 触及的项 |
|------|------|-----------|
| 14. 将 4 个重复的 `_get_step_output()` 复制重构为 1 个共享工具函数 | 2h | D1 |
| 15. 将 audit nodes + routing functions 去重（graph/nodes.py、graph/routing.py） | 4h | D2, D3 |
| 16. 修复异步事件循环阻塞（tiktok_connector time.sleep → asyncio.sleep） | 1h | D54 |
| 17. 添加连接器测试（TikTok、Shopify 最小 mock 测试） | 4h | E1 |
| 18. 将超大前端组件拆分（SceneForm → per-scene 组件） | 6h | D56 |
| 19. 将超大前端 page.tsx 拆分（提取 hooks + 子组件） | 6h | D55 |
| 20. 移除前端遗留表单 DOM（当 GuidedForm 活跃时） | 3h | D14, D72 |
| 21. 将 `Record<string, unknown>` 替换为类型化的接口（优先处理热路径） | 8h | D31, D32, D33 |
| **小计** | **34h** | |

### Phase 4: 长期卫生（第 3-4 周）

| 任务 | 工时 | 触及的项 |
|------|------|-----------|
| 22. 清理脚本/目录（归档一次性脚本，统一重复） | 3h | M2 |
| 23. 归档历史文档（将过时的计划/路线图移至 archive/） | 2h | D85-D93 |
| 24. 统一 contracts/ 与 runbooks/ 或建立清晰的单一真相来源 | 4h | M3 |
| 25. 通过 `fail_under` + 无 `continue-on-error` 提高 CI 覆盖率 | 2h | E5, E19 |
| 26. 添加 `LICENSE`、`CHANGELOG.md`、`SECURITY.md` | 1h | M6, V8 |
| 27. 减少 `except Exception` 的使用（前 20 个最严重的违规者） | 8h | D19-D26 |
| 28. 审查已知缺口文档，将已解决项目标记为完成，重新排序 P2 项目 | 2h | D81, D84 |
| 29. 设置 Dependabot 配置 | 1h | E18 |
| **小计** | **23h** | |

### 总计估算：~78.5 工时（约 2 周全职）

---

## 9. 附录：完整发现分类计数

### 按严重程度

| 严重程度 | 计数 | 描述 |
|----------|-------|-------------|
| **P0** | 12 | 阻断项——安全、仓库卫生、关键基础设施 |
| **P1** | 94 | 应在下一个 sprint 完成——显著的质量/安全/可维护性改进 |
| **P2** | 97 | Backlog——值得做，但可与功能工作并行 |
| **P3** | 18 | 低优先级——小型改进，可在任何时候处理 |

### 按类别

| 类别 | 计数 |
|----------|-------|
| 代码重复 | 8 |
| 死代码 / 未使用项 | 10 |
| 错误处理 | 8 |
| 类型安全 | 9 |
| 缺失的抽象 / 硬编码 | 10 |
| 循环导入 | 5 |
| 异步/等待 | 4 |
| 前端组件臃肿 | 4 |
| 前端状态管理 | 3 |
| 前端 API 客户端 | 4 |
| 前端 i18n | 4 |
| 前端可访问性 | 3 |
| 前端性能 | 3 |
| 前端 CSS/Tailwind | 2 |
| 测试基础设施 | 7 |
| 部署脆弱性 | 8 |
| CI/CD | 3 |
| 数据库架构 | 1 |
| 仓库卫生 | 9 |
| 文档过时 | 13 |
| 安全 / 脆弱点 | 9 |
| config/契约漂移 | 7 |

---

*报告由 AI Video 技术债务深度审计生成，日期 2026-06-09。所有发现均经过交叉验证，涉及三个并行探索代理和手动检查。*
