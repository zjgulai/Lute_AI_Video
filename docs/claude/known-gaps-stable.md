---
title: 已知缺口与待办清单
doc_type: knowledge
module: project
status: stable
created: 2026-05-08
updated: 2026-05-31
owner: self
source: human+ai
---

# 已知缺口与待办清单

最近一次盘点：**2026-05-31** — 已完成 P1-6 全站 UI/UX 无 token 审计与首轮修复：S1-S5/Library 路由白屏 fallback、Home 顶栏移动端挤压、Works/AssetPicker/Admin Logs 弹层可访问性已收口；新增 [`docs/analysis/site-ui-ux-audit-plan-stable-20260531.md`](../analysis/site-ui-ux-audit-plan-stable-20260531.md)。未触发真实 POYO token 消耗。

> 上一次盘点：2026-05-31 — 已完成 P1-5 文档漂移清理：`docs/claude/known-gaps-stable.md` 固化为当前技术债与下一步 TODO 的唯一入口；旧路线图、风险评估、部署计划和早期架构设计已标注历史语境，不再作为当前执行计划来源。

## 当前执行入口

- **唯一当前 TODO 来源**：本文件的“完整 TODO list”。
- **历史计划文档用途**：`docs/workflows/`、`docs/architecture/`、`.kiro/plan/` 中的旧 Sprint / Phase / TODO 只保留为决策背景、事故复盘或历史证据；除非本文件重新引用，否则不作为当前执行计划。
- **POYO 余额约束**：充值前只推进 hermetic / mock / unit / lint / 文档治理；真实 S1-S5 smoke、内容审核样本回灌和生产部署后真流量证据统一归入 P2。

## 0.18 2026-05-31 P1-6 全站 UI/UX 无 token 审计与首轮修复

- **页面加载反馈** — `/s1`-`/s5` 和 `/library` 不再使用 `Suspense fallback={null}`，统一改为 `RoutePageSkeleton`，避免慢设备或 hydration 阻塞时出现无反馈白屏。
- **移动端顶栏** — Home 顶栏对齐 `TopHeader` 的响应式策略：移动端隐藏长标题、压缩间距、保留主导航和管理入口，降低小屏横向挤压。
- **弹层可访问性** — `/works` 预览、`AssetPickerModal`、`Admin Logs` 详情弹层补 `role="dialog"`、`aria-modal`、Escape 关闭和初始焦点；Admin Logs 行补键盘 Enter/Space 打开。
- **关闭按钮语义** — `MaterialsTab`、`InfluencersTab`、`ConfirmModal`、`AssetLibrary` 等关闭按钮改为本地化或更具体 aria label，减少屏幕阅读器中的硬编码英文噪音。
- **审计文档** — 新增 UI/UX 专项方案，记录 5 个 loop 的发现、已完成项、保留债务和后续无 token / 充值后测试边界。
- **验证边界** — 本轮只允许静态页面、只读页面、lint/type/build 与 UI-only 测试；不调用真实生成、Gate candidate 或 POYO 相关接口。

## 0.17 2026-05-31 P1-5 文档漂移清理

- **当前计划入口收口** — 本文件明确为当前技术债 TODO 的唯一入口；后续继续执行时从“完整 TODO list”读取下一项，避免多个历史路线图并行竞争。
- **历史路线图标注** — `2026-05-14-poyo-constrained-optimization-roadmap.md`、`five-scenario-pipeline-risk-assessment-stable-20260513.md`、`2026-05-15-sprint-0-3-review-and-deploy-plan.md`、`2026-05-23-video-speed-optimization-deploy-plan.md` 已标注为历史快照或专项计划，不再作为当前待办来源。
- **架构与类型计划去漂移** — `multi-agent-video-system-design.md` 标注为早期产品/架构蓝图；`pyright-strict-technical-debt-plan-20260507-stable.md` 标注为类型治理历史计划，当前类型边界收口状态以本文件 P1-4 和 `pyproject.toml` 为准。
- **模型矩阵风险提示** — `poyo-model-matrix-stable.md` 明确为 2026-05 快照；真实消耗 POYO token 前需要重新核对 poyo.ai 当前模型目录和价格，不再把旧快照当“最新产品形态”。
- **边界** — 本轮不归档、不删除、不移动旧文档；只补历史语境和当前入口，避免破坏已有链接。

> 更早盘点：2026-05-31 — P1-4 类型边界热区收口。

## 0.16 2026-05-31 P1-4 类型边界热区收口

- **运行时契约集中化** — 新增 `src/models/runtime_contracts.py`，用轻量 `TypedDict` 固化跨模块 shape；不引入 Pydantic runtime validation，不改变现有 API JSON。
- **Fast Mode result 边界** — `FastModeService.generate()` 返回类型改为 `FastModeResult`，`model_info` / `timing` 也有显式结构；移除 `video_result` 上的 `union-attr` ignore，并对非 dict 视频结果显式失败。
- **Seedance result 边界** — `SeedanceClient.text_to_video()` / `image_to_video()` / `_stub_result()` 等返回 `SeedanceVideoResult`，避免调用方继续猜测 `local_path`、`video_url`、`_stub_mode` 字段是否存在。
- **Telemetry response 边界** — `PipelineMetrics.get_summary()`、`ErrorCollector.get_errors()`、`/telemetry/metrics`、`/telemetry/errors` 接入 `TelemetrySummary` / `TelemetryErrorsResponse`；同时修复无 running loop 时错误持久化调度产生的 unawaited coroutine warning。
- **Continuity audit 边界** — `build_continuity_audit_summary()` 返回 `ContinuityAuditSummary`，`build_transitions_from_clip_details()` 返回 `TransitionMetadata`；旧版只有 `micro_shots`、没有 `clip_groups` 的 grid 不再因缺 director metadata 被误降分。
- **防回归测试** — 新增 `tests/test_runtime_contracts.py`，锁定关键函数返回注解、Seedance stub shape、telemetry route annotation，以及 Fast Mode 不再依赖 `union-attr` ignore。
- **验证闭环** — 目标 `ruff` 通过；`pytest tests/test_runtime_contracts.py tests/test_continuity_utils.py tests/test_fast_mode_async.py tests/test_pipeline_degradation_chain.py tests/test_fault_injection.py -q` 通过，结果 `55 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P1-3 S2 deprecated wrapper 去留决策。

## 0.15 2026-05-31 P1-3 S2 deprecated wrapper 去留决策

- **决策：保留但冻结** — `src/pipeline/s2_brand_pipeline.py` 继续作为 backwards-compat shim，只 re-export `S2BrandCampaignPipeline` 并发出 `DeprecationWarning`；不得在旧文件继续添加 pipeline 行为。
- **生产调用面已迁移** — `/scenario/s2` 的生产路由直接导入 `src.pipeline.s2_brand_pipeline_v2`，不经过旧 shim；旧路径仅服务外部脚本、notebook 或历史调用。
- **删除条件明确** — 删除不是本轮默认动作；需要先确认外部调用迁移窗口，且按项目规则单独取得删除确认后再执行。
- **防回归测试** — 新增 `tests/test_s2_deprecated_shim_boundary.py`，锁定生产路由直连 v2、旧 shim warning-only alias、canonical import path 与 removal policy。
- **文档引用去漂移** — 已更新当前路线图与历史计划引用，把“直接删除 wrapper”改为“冻结兼容 shim，删除需迁移窗口 + 单独确认”。
- **验证闭环** — `ruff check src/pipeline/s2_brand_pipeline.py tests/test_s2_deprecated_shim_boundary.py tests/test_s2_e2e.py` 通过；`pytest tests/test_s2_deprecated_shim_boundary.py tests/test_s2_e2e.py -q` 通过，结果 `19 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P1-2 LangGraph proxy 契约收口。

## 0.14 2026-05-31 P1-2 LangGraph proxy 契约收口

- **字段契约显式化** — `src/routers/pipeline.py` 新增 `LEGACY_PROXY_STEP_OUTPUT_MAP` 与 `LEGACY_PROXY_REQUIRED_STATE_FIELDS`，把 StepRunner → legacy `/pipeline/*` 的字段映射从函数内部隐式逻辑提升为可测试契约。
- **兼容 shape 已测试** — 新增 `tests/test_pipeline_proxy_contract.py`，覆盖完整 StepRunner state、半完成 state、not_found state；锁定 `distribution_plans` 默认空列表、`human_reviews` 空 dict、`pipeline_complete` 推导和 legacy step output 字段。
- **review 行为继续冻结为 no-op** — 现有 `tests/test_human_review_deprecated.py` 继续锁定 `/pipeline/{thread_id}/review/{review_node}` 返回 `idempotent_skip`，真实审批入口仍是 `/scenario/{s}/gate/{label}/{gate_id}/approve`。
- **API reference 去漂移** — `docs/reference/api-endpoints.md` 已修正：`/pipeline/start` 返回 synthetic UUID + StepRunner label，review 不再描述 resume/reject，state 字段列出 pinned compatibility fields。
- **验证闭环** — `ruff check src/routers/pipeline.py tests/test_pipeline_proxy_contract.py tests/test_human_review_deprecated.py` 通过；`pytest tests/test_pipeline_proxy_contract.py tests/test_human_review_deprecated.py -q` 通过，结果 `7 passed`。

> 更早盘点：2026-05-31 — P1-1 api_assets.py legacy shim 边界收口。

## 0.13 2026-05-31 P1-1 api_assets.py legacy shim 边界收口

- **兼容面冻结** — `src/api_assets.py` 明确标注为 `/api/assets/*` legacy compatibility surface；brand package / influencer CRUD 保留给现有前端 OpenAPI types 和 library tab，不再承接新业务域。
- **现代 assets 边界明确** — 新上传、文件列表、portfolio、运行时媒体能力继续归 `src/routers/assets.py`、`src/routers/portfolio.py`、`src/routers/media.py`，避免 `/api/assets/*` 与 `/api/upload` / `/api/files` 继续混淆。
- **防回归测试** — 新增 `tests/test_api_assets_legacy_boundary.py`，断言 `api_assets.router.prefix == "/api/assets"`、legacy brand/influencer/remix 路由仍存在，并断言现代 assets router 不抢占 `/api/assets` 前缀。
- **PG cutover 状态修正** — `docs/architecture/api-assets-pg-cutover-2026-05-15.md` 已更新为 stable boundary：`BRAND_PACKAGE_USE_PG=1` adapter 已存在，但生产 PG `id` 仍是 UUID，`BPKG-*` 业务 ID 持久化仍需 staging/restart smoke 验收。
- **验证闭环** — `ruff check src/api_assets.py tests/test_api_assets_legacy_boundary.py tests/test_asset_stores_cutover.py` 通过；`pytest tests/test_api_assets_legacy_boundary.py tests/test_asset_stores_cutover.py -q` 通过，结果 `24 passed`。

> 更早盘点：2026-05-31 — P0-4 前端运行时媒体图片策略。

## 0.12 2026-05-31 P0-4 前端运行时媒体图片策略

- **运行时媒体统一入口** — 新增 `RuntimeMediaImage`，集中承载后端 portfolio、用户上传、缩略图、素材预览等运行时 URL；业务组件不再直接散落原生 `<img>`。
- **静态资产不走运行时入口** — `BrandKitTab` 的 `/brand/momcozy-logo.svg` 改用 `next/image`，避免把可静态优化的 public 资产误归入运行时媒体策略。
- **策略边界** — `RuntimeMediaImage` 内部保留唯一 `@next/next/no-img-element` 例外说明；该组件只用于后端/用户资产 URL，不用于静态 public 图片或已知可 allowlist 的 CDN 图片。
- **验证闭环** — `npm exec eslint src` 无 warning；`npm exec tsc -- --noEmit` 通过；`npm test -- --run src/app/__tests__/page-smoke.test.ts --testTimeout=15000` 通过，结果 `16 passed`；`DirectorPlayback` / `QualityDashboard` / `CompareView` 目标测试通过，结果 `6 passed`。

> 更早盘点：2026-05-31 — P0-3 前端真实 warning 清理。

## 0.11 2026-05-31 P0-3 前端真实 warning 清理

- **admin hook dependency 已收口** — `admin/logs`、`admin/tenants`、`admin/tenants/[tenantId]` 的 load 函数改为 `useCallback`，effect 依赖不再捕获 stale closure。
- **筛选语义保持明确** — logs/tenants 页将输入态与已应用筛选态分离，避免为了修 hook warning 变成输入即请求；Search / Apply 仍是显式触发查询入口。
- **unused warning 已清理** — 删除未使用的 `Link`、`newKeyId`、`detailLoading`、`TAB_IDS`、`VideoListView` 内未使用 `t`，移除过期 `no-console` disable；page smoke mock 的 `isApiError` 不再声明未使用参数。
- **验证闭环** — `npm exec tsc -- --noEmit` 通过；`npm test -- --run src/app/__tests__/page-smoke.test.ts --testTimeout=15000` 通过，结果 `16 passed`；`npm exec eslint src` 仅剩 11 个 `@next/next/no-img-element` warning，全部属于 P0-4。

> 更早盘点：2026-05-31 — P0-2 FastAPI lifespan shutdown 集成测试。

## 0.10 2026-05-31 P0-2 FastAPI lifespan shutdown 集成测试

- **新增真实 lifespan 测试** — `tests/test_bg_registry.py` 通过 monkeypatch `src.api._run_startup()` 注入一个无外部依赖的长任务，再使用 `TestClient(api.app)` 触发真实 FastAPI lifespan enter/exit。
- **验证 shutdown 行为** — context 退出后测试断言长任务收到 cancellation，并且 `get_background_task_snapshot()` 返回空 dict，覆盖 `src.api._lifespan()` → `cancel_background_tasks()` 的真实调用链。
- **边界** — fake startup 只替换启动副作用，不替换 lifespan cleanup；不会触发 DB、admin loop、外部 API 或 POYO token。
- **验证闭环** — `ruff check tests/test_bg_registry.py` 通过；`pytest tests/test_bg_registry.py -q` 结果 `3 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归集合通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P0 本地质量门第一批执行结果。

## 0.9 2026-05-31 P0 本地质量门第一批执行结果

- **repo-wide ruff 已恢复可用** — `ruff check tests --fix` 清理历史测试文件中的 import 顺序、未使用 import、无占位符 f-string、`datetime.UTC` 迁移等机械噪音；剩余 `tests/test_api.py` 顶层未使用 `httpx` import 改为 `importlib.util.find_spec("httpx")` 可用性检测。
- **质量门结果** — `ruff check tests --statistics` 通过；`ruff check src tests --statistics` 通过。后续可以把 `ruff check src tests` 重新作为本地质量门使用。
- **目标测试结果** — `pytest tests/test_api.py tests/test_bg_registry.py -q` 通过，结果 `9 passed`；S1-S5 无 token hermetic 回归集合通过，结果 `137 passed, 12 deselected`。
- **边界** — 本轮只做 ruff 可自动修复和一个 import 检测手工修复，不改变 API 语义、不触发外部服务、不消费 POYO token。

### 完整 TODO list

- [x] **P0-1：恢复 Python repo-wide lint 可信度** — 清理 `src tests` ruff 噪音，使 `ruff check src tests` 重新可作为质量门。
- [x] **P0-2：补 FastAPI lifespan shutdown 集成测试** — 构造无外部依赖的注册任务，验证 app 退出时 registry 会取消、等待并清理后台任务。
- [x] **P0-3：清理前端真实 hook warning** — 优先处理 admin 页 `react-hooks/exhaustive-deps`、未使用变量；保留 `<img>` 策略 warning 到单独决策。
- [x] **P0-4：建立前端运行时媒体图片策略** — 明确后端运行时 URL 哪些必须原生 `<img>`，哪些可迁移 `next/image`，避免一边 suppress 一边新增债务。
- [x] **P1-1：收口 `api_assets.py` legacy shim 边界** — 明确 `/api/assets/*` in-memory shim 的冻结规则、迁移条件和删除前置测试。
- [x] **P1-2：收口 LangGraph proxy 契约** — 明确 `/pipeline/*` best-effort state 转换字段，补最小兼容测试，避免 legacy 字段缺失隐性回归。
- [x] **P1-3：确认 S2 deprecated wrapper 去留** — 检索调用面与文档引用，已冻结为 warning-only alias；删除前需要外部迁移窗口与单独确认。
- [x] **P1-4：类型边界热区收口** — 已补运行时 `TypedDict` 契约，覆盖 `fast_mode` result、telemetry endpoint、continuity audit、Seedance result，不做全仓 `Any` 大重构。
- [x] **P1-5：文档漂移清理** — 已将当前执行入口固定到本文件，历史探索/路线图/部署计划文档已标注历史语境，不再作为当前计划来源。
- [x] **P1-6：全站 UI/UX 无 token 审计与首轮修复** — 完成 5 loop 审计，修复路由白屏 fallback、Home 顶栏移动端挤压和关键弹层可访问性。
- [ ] **P1-7：前端布局与弹层单一化** — 抽象 Home header/`TopHeader`，统一 `QuickTemplate`、`AssetLibrary` 与 Library/Works 的弹层键盘行为。
- [ ] **P1-8：UI-only Playwright 视觉回归** — 基于已恢复 Chromium 补桌面/移动端截图和交互 smoke，确保默认不触发真实生成接口。
- [ ] **P2-1：充值后执行 S1-S5 真实 smoke** — 覆盖 Fast Mode、S1-S5 auto、gate approve/regenerate、media/poster/quality、admin/library 关键路径。
- [ ] **P2-2：POYO 内容审核样本回灌** — 将真实失败 prompt / response 分类写入 hermetic fixture 或 sanitizer 规则，避免只靠生产人工观察。
- [ ] **P2-3：生产部署后回归证据固化** — Lighthouse 部署、健康检查、关键页面、API smoke、日志异常统一形成可复跑 checklist。

> 更早盘点：2026-05-31 — 遗留技术债深度汇总与执行计划。

## 0.8 2026-05-31 遗留技术债深度汇总与执行计划

### 证据基线

- **后端局部质量门已通过** — `ruff check src/tasks/bg_registry.py tests/test_bg_registry.py` 通过；`tests/test_bg_registry.py` 通过；S1-S5 无 token hermetic 回归集合通过，结果 `137 passed, 12 deselected`。
- **后端全量 lint 仍不可作为 CI 门禁** — `ruff check src tests` 当前仍有 `176 errors`，其中 `174` 项可自动修复，主要集中在历史测试文件的 import 顺序、未使用 import、无占位符 f-string、`datetime.UTC` 迁移和少量疑似 stale import。
- **前端无 error 但仍有 warning 债** — `npm exec eslint src --quiet` 无 error；完整 `npm exec eslint src` 仍有 `21 warnings`，主要是 admin 页 hook dependency、未使用变量，以及运行时媒体 `<img>` 策略未统一。
- **工作区变更量大** — 当前存在大量 modified / untracked 文件。继续推进前必须按主题分批验证和提交，避免把已完成修复、文档计划、历史探索和后续实验混成一个不可回滚变更包。
- **真实生产验证仍受 POYO 余额约束** — 当前阶段继续只做 hermetic / mock / unit / lint / 类型收口；S2-S5 真实生成、gate 真 API key 路径和质量评分生产闭环留到充值后执行。

### 债务分层

- **P0：本地质量门债务** — repo-wide Python lint 失败会让 CI 口径失真；必须先把 `tests/` 中可自动修复的 ruff 噪音分批清掉，再处理少量真实 stale import 或路径漂移。
- **P0：前端 hook warning 债务** — admin 页 `react-hooks/exhaustive-deps` warning 属于真实 stale closure 风险，不应和 `<img>` 性能策略 warning 混放处理。
- **P0：生命周期验证债务** — registry 现在有 shutdown cleanup 和公开 snapshot helper，但还缺一个更接近 FastAPI lifespan 的集成测试，验证 app 退出时真实注册任务会被取消并清理。
- **P1：兼容层边界债务** — `src/api_assets.py` 仍是 `/api/assets/*` legacy in-memory shim；`/pipeline/*` LangGraph proxy 仍是 best-effort state 转换；S2 deprecated wrapper 清理仍需先确认调用面和文档。
- **P1：类型边界债务** — 后端仍大量使用 `dict[str, Any]`，但不适合全仓一次性重写；应优先收口 `fast_mode` result、telemetry endpoint、continuity diagnostics、Seedance clip detail 这些跨模块热输出。
- **P1：文档漂移债务** — 2026-05-31 已完成首轮收口：当前执行入口固定为本文件；高风险旧路线图、风险评估、部署计划和早期架构设计已补历史语境。
- **P2：生产验证债务** — S2-S5 真实 API key gate、POYO 内容审核、thumbnail/quality/media 工具链和部署后 smoke 都不能在无余额阶段闭环，只能先准备 checklist 与 mock 证据。

### 执行计划

1. **先稳定质量门** — 以 `tests/` 为第一批，运行 ruff auto-fix 能覆盖的 import/order/f-string/datetime 规则；每批只处理一个规则族，避免把行为变更混入格式修复。
2. **再清前端真实 warning** — 优先修 admin 页 hook dependency 和未使用变量；`<img>` warning 单独建立运行时媒体策略，确认哪些必须保留原生 `<img>`，哪些可迁移 `next/image`。
3. **补生命周期集成测试** — 在不触发外部服务的前提下构造注册任务，覆盖 lifespan shutdown 对 registry 的取消、等待和清理语义。
4. **收口热路径类型边界** — 只处理跨前后端或跨 pipeline 的输出结构，避免在低 ROI 的内部 `dict[str, Any]` 上做大规模重构。
5. **整理兼容层决策** — 为 `api_assets.py`、LangGraph proxy、S2 wrapper 分别给出保留、冻结、迁移或删除条件；删除或批量移动前单独确认。
6. **文档去漂移** — 将仍有效的 TODO 汇入 stable 文档；把只描述历史探索的内容标注为历史背景，不再作为执行计划来源。
7. **充值后执行生产 smoke** — 按 S1-S5、Fast Mode、gate approve/regenerate、media/poster/quality、admin/library 关键路径分批实测，并把失败样本回灌到 hermetic 测试。

## 0.7 2026-05-31 bg_registry 测试封装收口

- **新增公开只读 snapshot helper** — `src/tasks/bg_registry.py` 新增 `get_background_task_snapshot()`，只返回 `label`、`started_at`、`done`、`cancelled` 等测试和诊断需要的元数据，不暴露内部 task registry dict 本体。
- **测试不再读取私有 dict** — `tests/test_bg_registry.py` 已改为通过 snapshot 断言注册、完成和取消状态；fixture 通过 `cancel_background_tasks(timeout=1.0)` 做前后清理，减少测试间残留。
- **边界** — `_background_tasks` 仍保留为模块内部实现细节；业务调用仍通过 `register_background_task()` 和兼容 re-export，不改变 runtime 行为。
- **验证闭环** — 已通过 `ruff check src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`，以及完整无 token hermetic 集合 `137 passed, 12 deselected`。

> 更早盘点：2026-05-31 — background task registry 单一化。

## 0.6 2026-05-31 background task registry 单一化

- **删除失活重复定义** — `src/routers/_state.py` 中旧 `_background_tasks` dict 已删除；该变量自 registry 迁移后没有真实引用，继续保留会误导维护者以为存在两个任务注册源。
- **保留兼容 re-export** — `_state.py` 继续 re-export `_register_background_task`，现有 `scenario.py` / `pipeline.py` 调用路径不变。
- **验证闭环** — 已通过 `ruff check src/routers/_state.py src/routers/scenario.py src/routers/pipeline.py src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`、`tests/test_scenario_step_regenerate_router.py`，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-31 — background task shutdown cleanup。

## 0.5 2026-05-31 background task shutdown cleanup

- **registry 增加集中 shutdown helper** — `src/tasks/bg_registry.py` 新增 `cancel_background_tasks(timeout=5.0)`，会取消 registry 内未完成任务、等待有限时间，并清理已完成/已取消记录。
- **lifespan 退出时调用 cleanup** — `src/api.py` 的 lifespan 在 `finally` 中调用 `cancel_background_tasks()`；启动逻辑不变，只补退出路径。
- **边界** — 本轮不改变请求期间 background task 注册、完成 callback、失败日志和业务任务执行语义；只处理 app shutdown 时原本缺失的集中清理。
- **验证闭环** — 已通过 `ruff check src/api.py src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`、`tests/test_scenario_step_regenerate_router.py`、`no_on_event_deprecation` import 检查，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-30 — FastAPI lifespan 迁移。

## 0.4 2026-05-30 FastAPI lifespan 迁移

- **`on_event` deprecation warning 已关闭** — `src/api.py` 将原 `@app.on_event("startup")` 启动逻辑迁移为 `FastAPI(lifespan=...)`，启动内容保持原样：DB 初始化、thread index restore、cache eviction、生产 API key 检查、portfolio hook、admin background tasks。
- **shutdown cleanup 后续已补** — 初始迁移不顺手改后台任务取消逻辑；2026-05-31 已在 background task registry 增加集中 shutdown cleanup。
- **验证闭环** — 已通过 `ruff check src/api.py`、`tests/test_scenario_step_regenerate_router.py`、`no_on_event_deprecation` import 检查，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-30 — S1-S5 前端降级提示口径收口。

## 0.3 2026-05-30 soft degraded 展示口径收口

- **reason 不再直出内部码值** — `getSoftDegradedReasonLabel()` 改为 reason 白名单映射；未知 reason 统一显示 `degraded.reason.unknown`，不再把 `internal_backend_code` 这类字符串替换下划线后展示给用户。
- **detail 不再直出后端 `_degraded_detail`** — `getSoftDegradedSummary()` 改为按 reason 读取 `degraded.detail.*` 翻译；未知 reason 或未配置 detail 时不展示 detail，避免 fallback_reason、异常文本、内部字段名泄漏到 UI。
- **三条热路径自动复用** — `StageProgress`、`StepByStepView`、`VideoWorkflow` 都已通过共享 `softDegraded` helper 继承新口径，无需分别维护展示逻辑。
- **验证闭环** — 已通过 `vitest src/lib/softDegraded.test.ts`、目标 `eslint` 与 `tsc --noEmit`。

> 更早盘点：2026-05-28 — S1-S5 前端工作流技术债本地收口，目标 lint、`tsc --noEmit` 和目标 Vitest 验证通过。

## 0.2 2026-05-29 前端热路径 lint 收口

- **Fast Mode 面板** — `FastModePanel` 移除未使用的 `getMediaUrl` import，避免 lint 噪音掩盖真实改动。
- **S1-S5 Expert 表单** — `SceneForm` 删除未使用的 `SCENE_ICON_MAP`，保留实际渲染仍在使用的平台 icon map 和场景标题 icon。
- **首页场景入口** — `SceneSelector` recent works 缩略图保留原生 `<img>`，并补精确 `@next/next/no-img-element` 例外说明；这些缩略图来自后端运行时媒体路径，不引入 Next image allowlist 配置债。
- **验证闭环** — 已通过 `eslint src/components/FastModePanel.tsx src/components/SceneForm.tsx src/components/SceneSelector.tsx` 与 `tsc --noEmit`。
- **后端 hermetic 回归** — 已通过 `tests/test_scenario_step_regenerate_router.py`、`tests/test_gate_scenario_configs.py`、`tests/test_continuity_storyboard_grid.py`、`tests/test_candidate_scorer_continuity.py`、`tests/test_s1_continuity_pipeline.py`、`tests/test_s3_e2e.py`、`tests/test_s4_e2e.py`、`tests/test_s5_e2e.py`，结果 `135 passed, 12 deselected`；FastAPI `on_event` deprecation warning 已在 2026-05-30 lifespan 迁移中关闭。

> 更早盘点：2026-05-22 — S1 连续分镜能力向 S2-S5 抽象迁移完成，13 个 POYO 模型 ID 修正，Kling/Wan/Hailuo 参数适配。详见 [`docs/superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md`](../../superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md)。

## 0.1 2026-05-28 本地技术债收口

下列项已完成本地验证，作为 S1-S5 工作流继续实测前的稳定性基线：

- **GuidedForm 连续性参数传递** — `buildGuidedScenarioConfig()` 抽出 S1-S5 共享配置合成逻辑，`continuity_required`、`reference_image_url`、`source_video_url`、`character_reference_url` 不再只停留在前端表单态；目标单测覆盖 S1-S5 配置输出。
- **Smart Create 场景路由与连续性透传** — `buildSmartCreatePayload()` 和 `getScenarioPagePath()` 收口前端 payload 与跳转映射，`live_shoot_to_video` 明确路由到 `/s4`，避免 S4 误落回 S1 默认链路。
- **结果/分发/作品/审核展示类型债** — `api.ts`、`OneShotResultView`、`DistributionView`、`PublishPanel`、`works/page.tsx`、`ReviewPanel` 已移除本轮目标显式 `any`，用局部宽类型、类型守卫和边界归一化替代直接结构假设。
- **Step-by-step 与工作流编排类型债** — `AssetCard`、`types.ts`、`StepByStepView`、`VideoWorkflow` 已完成目标 lint；`VideoWorkflow` 保留 backend-runtime thumbnail 原生 `<img>`，并用精确 lint 例外说明原因，避免 Next image allowlist 与运行时媒体路径耦合。
- **验证闭环** — 已通过目标 `eslint`、`tsc --noEmit`、`guidedScenarioConfig` / `scenarioContinuity` / `scenarioRouting` Vitest；真实 POYO 余额相关端到端仍保留为后续人工实测项。

> 更早盘点：2026-05-11 (v0.2.4) — Tier-2/Tier-3/HU-05/Brand Assets Phase 1-4 全部上线。

## 0. 2026-05-11 / v0.2.4 关闭项总览

下列项已在 v0.2.0 → v0.2.4 区间被实际修复并上线生产，从未闭项中移除：

- **配置漂移 `DEFAULT_LLM_PROVIDER`** — `4bf096b` (v0.2.1) — `src/config.py:115` 标注为
  SSOT，4 个镜像文件（render.yaml / .env.prod / 2 篇 deploy 文档）全部对齐 `deepseek`。
- **Redis/Celery legacy** — `4bf096b` 验证 src/ 与 tests/ 完全无引用，requirements 也无；
  AGENTS.md 历史描述已修订。
- **Long pipeline UX (HTTP 超时)** — 异步 submit + `/status` 轮询已在 2026-05-08 上线，
  nginx 1500s 退居兜底。
- **S2-S5 Gate 系统** — `gate_manager.py` per-scenario + 52 个 `test_gate_scenario_configs.py`
  + `_build_skill_params` 扩展（`remix_script` / `vlog_strategy`）。
- **admin.py 0600 → backend 502** — `5c4d192` (v0.2.1) 在 `deploy.sh` 加 Phase 0.5
  防御 chmod + 头部注释带 `--chmod=F644,D755`。
- **GAP-A 防双击** — `db89079` (v0.2.1) `useSubmitting` 接入 5 个 submit 入口。
- **GAP-B 422 inline error** — `db89079` + `74f5310` 字段级红框 + `aria-invalid` +
  Pydantic `loc` 自动映射。
- **GAP-C `parseApiError` + ApiError class + 429 retry** — `db89079`，4 个 API helper
  改为抛 `ApiError`，前端展示 `(retry in Ns)` 后缀。
- **HU-05 `cardCopyEn` 100 条 zh→en 映射** — `4bf096b` (v0.2.2)，`GuidedCard` /
  `CardConnector` 渲染时 `tCardCopy(text, locale)`。
- **Creation Guide 重构** — `c52cad8` (v0.2.2) 抽取独立 `CreationGuide.tsx`，5-tab
  导航（Overview / Scenes / Frontend / Admin / Runbooks），加 ~120 i18n 翻译。
- **Brand Kit Tab 数据流断链** — `2238a84` (v0.2.3) `BrandKitTab.tsx` 改为 fetch
  `/api/portfolio/?kind=brand_kit`，137 张 momcozy 抓取图全部可见。
- **品牌资产 product 元信息** — `74f5310` (v0.2.4) `PortfolioFile` 增加 6 个产品字段
  （title / slug / brand / source_url / description / price），LRU 读 info.json。
- **QuickTemplate 抓取数据流** — `7daadc1` (v0.2.4) 新增 `/api/portfolio/brand-presets`
  endpoint，前端 fetch + merge over demo-data，刷新 scraper 不需重新部署 frontend。
- **3 篇 ADR + 5 篇 Runbook** — `4bf096b` + `7daadc1` 落入 `docs/architecture/adr/`
  + `docs/runbooks/`。

详细内容见下文。

### 1. 已知功能缺陷(已修复)

> **2026-05-09 修复 (S2/S4 生产缺陷):**
>
> - **S2 `strategy_failed: 'product_catalog'`** — `submit_scenario` S2 分支的 config 缺少
> `product_catalog`，StepRunner fallback 到 s1 pipeline 后 `_step_strategy` 需要
> `config["product_catalog"]` → KeyError。修复：`scenario.py` S2 分支从 `brand_package`
> 自动构造 `product_catalog` + `brand_mode=True`；`step_runner.py:_SCENARIO_CONFIGS`
> 显式添加 `s2` 条目复用 S1 pipeline class。验证：非 demo E2E 通过，生成 9.9MB 真实视频。
> 前端无需额外传递 `product_catalog`。
> - **S4 `clip_0_failed: 'prompt' must be a string`** — `s4_live_shoot_pipeline.py:_step_video_prompts`
> 将 `seedance-video-prompt` 返回的 `list[dict]` 整体嵌套进 `"prompt": vp.data`，下游
> `_step_seedance_clips` 传入 `list` 而非 `string` 给 `seedance-video-generate-skill`，
> `validate_params` 检查 `isinstance(prompt, str)` 失败。修复：改为扁平化模式（与 S1 一致），
> 直接 `all_prompts.extend(vp.data)`。验证：非 demo E2E 通过，`clip_details=[False, False, False]`，
> 视频 `s4_with_audio.mp4` = 5.8MB（之前 12KB stub）。

> **2026-05-07 修复:**
>
> - **ChunkLoadError /footage 页面崩溃** — Turbopack content-hash 变化导致旧 chunk 引用失效。
> nginx `location /` 添加 `Cache-Control: no-store` 禁止 HTML 缓存，`location /_next/`
> 静态资源长期缓存。`deploy.sh` 构建前清理旧产物避免残留。
> - **循环导入导致 backend 启动失败** — `src/graph/nodes.py` 顶层导入 `_register_background_task`
> 形成 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py` 循环。改为延迟导入 helper。
> - **nginx `limit_req off` 语法错误** — 原配置使用无效语法，`location /health` 和
> `/api/media/` 改为高 burst 值实现等效豁免。
> - **nginx 顶层 `limit_req` 误伤前端导致首页 429** — `server` 块顶层 `limit_req zone=api_limit burst=20 nodelay` 被前端 `/` 和 `/_next/` 默认继承，Next.js 冷启动
> 30+ 并发请求秒爆 burst=20。修复：删除顶层声明，改为 7 个 API location 内部
> 显式 `limit_req`。生产 rsync `--inplace --no-whole-file` + `nginx -s reload` 落地。

> **2026-05-06 修复:**
>
> - **Portfolio 加载慢 + 视频无法预览** — 后端 `?limit=50&sort=quality` + nginx `try_files`
> 静态直送 + 144 个 poster thumbnail + 前端 `<img poster>` 替代 337 个 `<video preload="metadata">`。
> 实测 thumbnail 4.8ms / video 32ms(02849c9)。
> - **Footage 页面交互不一致** — 成品/素材统一 `MediaPreviewModal` 弹窗预览,不再
> `window.open` 或右侧 detail panel;Materials 新增 全部/视频/图片/音频 分类过滤(c4dd6ed)。
> - **UI 主题翻转** — `globals.css` + `tailwind.config.js` + 40+ 组件从暗黑剧场翻转为
> Warm Light Professional Theme(d3e8bd3)。

> **2026-05-08 4-Option Plan 修复/扩展:**
>
> - **POYO sanitizer Phase 2** — 新增 11 条替换规则(英 7 + 中 4)，覆盖 baby bottle / nipple /
> areola / formula milk / baby food / postpartum / 奶瓶 / 奶嘴 / 辅食 / 产后。
> 新增结构化 CM 拒绝日志，生产可通过 `poyo_cm_rejection` 事件抓回原始 prompt 持续补充规则。
> - **S3-S5 Gate 配置** — `gate_manager.py` per-scenario 重构完成，`SCENARIO_GATE_DEFINITIONS`
> 定义 s1-s5 各场景 gate 集合与 after_step 映射；`candidate_scorer.py` 新增 `remix_script` /
> `character_identity` / `vlog_strategy` 评分维度。`step_runner.py` gate 触发按 scenario 读取。
> `_build_skill_params` 补充 `remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py`
> 52 个测试验证配置正确性。step-by-step gate 暂停对 S3/S4/S5 均已 mock 验证通过。
> - **Long pipeline UX** — 统一异步框架已落地，S2/S3/S5 的长链路不再受 HTTP 超时截断。

> **2026-05-08 修复:**
>
> - **Admin Panel 登录不可用** — `bcrypt` 未安装导致 admin router 启动跳过；nginx `/api/`
> catch-all strip `/api` 前缀导致 admin 端点 404；`admin_accounts` 表未创建（Alembic
> 迁移未执行）。修复：`pip install bcrypt` + `docker commit`；新增 `/api/admin/` nginx
> location 保留前缀；手动 SQL 建表并插入初始 admin 账号。登录验证通过。
> - **page.tsx 构建失败** — `useExpertStore` 解构缺少 `setShowStageProgress` /
> `currentStepIdx` / `setCurrentStepIdx`。补充解构后 `npm run build` 通过。
> - **nginx `/telemetry/` 404** — 缺少 `/telemetry/` location，请求被路由到前端。
> 新增 location 转发到 backend，`/telemetry/prometheus` 返回 Prometheus 格式指标。

仍待处理:

- **POYO sanitizer 覆盖率持续提升(F3, P2)** Phase 2 新增 11 条规则后覆盖率大幅提升，
但仍需在生产日志中持续抓回 `poyo_cm_rejection` 事件中的原始 prompt 文本补充新规则。
- **yt-dlp / whisper 未装进 backend 容器(F4, P3)** D5 KOL 视频分析 skill 走 mock 路径,
脚本生成不依赖真实 transcribe,管线下游不受影响。要让 video-analysis 真实工作需
`pip install yt-dlp openai-whisper` 进 `Dockerfile.backend`(whisper 拉 PyTorch ~2GB,
实施前先确认是否值)。

### 2. 配置/历史遗留(已知)

- **api_assets.py compat shim:** `/api/assets/`* uses in-memory dicts (`_brand_packages`,
`_influencers`). Frontend OpenAPI types still reference these paths, so don't remove the
router; do migrate any new asset features to `src/routers/assets.py` instead.
- **S2-S5 step-by-step / gate system:** S3/S4/S5 已完成 StepRunner 迁移 (P2)、gate
配置、skill params 扩展与非 S1 场景 mock 验证。`_build_skill_params` 新增
`remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py` 52 测试验证
配置正确性。仍待: 前端 `CandidateSelector` 在非 S1 场景下的状态映射未实测；
S3-S5 gate 真实 API key 端到端（类似 `test_gate_full_flow_e2e.py` 对 S1 gate_1 的验证）。
- **Long pipeline UX:** ✅ 已解决(2026-05-08) — 统一异步执行框架落地，所有场景走
`POST /submit` → 轮询 `/status`，HTTP 超时不再截断长链路。nginx 1500s 退居兜底。
- **Redis/Celery declared but unused:** Still in `requirements.txt` but no live consumer.
- **LangGraph 代理层 (P4-4):** `/pipeline/`* 端点已代理到 StepRunner，但代理层 state 转换是
best-effort，某些 legacy 字段可能缺失。保留原始 LangGraph 代码作为兼容层，代理函数可迭代补全。
- **pyright strict 剩余规则:** `reportUnknownMemberType` / `reportUnknownVariableType` 未启用。
在 `dict[str, Any]` 为主的代码库中，这两项规则噪音远大于价值。如需进一步收紧类型，需先
将 `dict[str, Any]` 替换为数百个具体类型（ProductCatalog、PipelineConfig 等），ROI 待评估。
- **deploy.sh Phase 0 逻辑缺陷:** ✅ 已修复。`mtime` 比较 → `sha256sum` hash 比较，
Dockerfile 构建时记录 `sha256sum requirements.txt > /app/.requirements_sha256`，
deploy.sh 直接对比本地 hash 与镜像内 hash。不受 `IMG_BUILT_TS=0` 影响，首次部署也正确提示。
- **alembic 不在 requirements.txt 中:** ✅ 已修复。`alembic>=1.13` 已加入 `requirements.txt`，
backend image 已 rebuild 固化，容器内可直接执行 `alembic upgrade head`。
- **Quality 模块 lazy import 设计:** `src/quality/` 下 10 个模块全部采用 lazy import。
transformers/torch/opencv/mediapipe/deepface/pyiqa/scenedetect 均不在 `requirements.txt`
中强制要求。运行时会检测可用性，不可用则 graceful skip 并记录 warning。生产如需启用
CLIP/BRISQUE/场景分析/人脸一致性，需手动安装对应依赖并确认 Docker image 体积可接受
(CLIP+torch CPU ~600MB, DeepFace ~200MB)。

### 3. 未做端到端验证的前后端交互路径

Phase D/E 通过的是 5 场景"主路径" + portfolio 优化。以下路径在生产尚未端到端实测:

- **A. Human Review 4 个 checkpoint 的人工分支** Pipeline `strategy_audit` /
`script_audit` / `editing_audit` / `thumbnail_audit` 的 score 落在 0.60–0.90 区间会触发
HITL,前端 `GatePanel` + 后端 `POST /scenario/{s}/gate/{label}/{gate_id}/approve` 的
"APPROVED / CHANGES_REQUESTED / REJECTED" 三个分支以及 D10 contextvars 路由覆写,
Phase D 没触发到。需要构造低分输入或下调阈值实测。
- **B. S1 step-by-step + Gate 候选生成全链路** ✅ 后端单元测试已覆盖（`test_s1_gate_full_flow.py`
41 测试：approve 成功路径包括 candidate 选择 → edited_output 写入 → current_step 推进；
step_runner gate 暂停/恢复 4 个测试验证 pre-step + post-step 检查点）。
真实 API key e2e 在 `test_gate_full_flow_e2e.py` 中覆盖 gate_1 generate + score + approve
  - regenerate。生产端到端未实测（Phase D D2 走的是 auto 模式）。
- **C. Distribution / Publish** `POST /distribution/publish` + TikTok / Shopify connector
实际发布。Phase D 没跑过,只有单元测试。需要真实 platform credentials 才能走通。
- **D. Metrics 全链** `GET /metrics/`* 视频性能查询、`src/tasks/metrics_poller.py` 周期任务
在生产是否被调度、Alembic 的 `video_metrics` 表是否真的 `alembic upgrade head` 过、
PG 与 SQLite 双路是否在生产生效。前端 `PerformanceDashboard` 显示真数据未验证。
- **E. Assets 上传链路** ✅ 后端单元测试已覆盖（`test_upload_e2e.py` 10 测试验证
multipart → 落盘 → `/api/files` 列出 → `/api/media/` 访问完整链路；含认证/扩展名/大小限制
负向测试）。前端 `brand-packages/page.tsx` 已集成 `AssetUploader` 上传面板（Header 右侧
上传按钮 + 可折叠上传区域，上传完成后自动刷新列表）。仍待: 生产未走通"上传 → 管线
引用 → 出现在最终视频"的闭环（uploaded 文件尚未被 keyframe/seedance 步骤实际引用验证）。
`/influencers` 列表 CRUD 在生产是否真存了 PG 未验证。
- **F. Webhook 事件分发** `src/tools/webhook_manager.py` 的 `audit.completed` /
`pipeline.completed` 事件,Phase D 期间生产 `WEBHOOK_URLS` 为空,从未触发。需要配上
接收端(可临时用 webhook.site)再跑任一场景验证。
- **G. 错误降级路径** `pipeline_degraded = True` 在 5 场景中未被触发(都走绿)。Mock POYO /
DeepSeek 故障下的"降级 + 终止 + 错误上报"链路、`error_collector` FIFO、`/telemetry`
端点的可见性,均未做负向测试。
- **H. 多用户并发 + API Key 隔离** `contextvars` 隔离机制在单机单请求 OK。同时跑 2+ 场景
使用不同 API key 时是否真的不串(尤其 LLM client + POYO client + Seedance client 三处
contextvars 读取),没压测过。
- **I. i18n 切换** `zh-CN` / `en` 在生产页面切换后,所有按钮 / 表单 / 报错 / SettingsPanel /
GatePanel / DistributionView 文案是否都从翻译表读取(无硬编码中文/英文残留),未走查。
- **J. 备用部署目标** `render.yaml`(海外)与 `deploy/tencent-cloudbase.md`(国内 CloudBase)
这两条 alternative 路径的现状,自从 Lighthouse 成为 canonical 后没人再验过。`render.yaml`
里 `DEFAULT_LLM_PROVIDER=kimi` 是否还能正常生成内容,未知。
- **K. Quality 模块真实 ML 依赖验证** `src/quality/` 下 CLIP、BRISQUE、PySceneDetect、
MediaPipe/DeepFace 均只在代码层面验证通过（lazy import + fallback 路径）。真实安装
transformers+torch / opencv-python / mediapipe 后的端到端验证尚未执行。`nr_quality.py`
的 OpenCV fallback 在现有生产环境（有 ffmpeg 无 opencv-python）中走的是 "skipped" 路径。
- **L. 质量评分传递链闭环** seedance_prompt / script_writer 已输出 `quality_score` /
`_self_check`，但下游 skill（keyframe_images → seedance_clips → remotion_assemble）尚未
读取上游 quality_score 并在低于阈值时触发 regenerate。"下游读取上游 quality_score，
低于阈值主动请求 regenerate" 机制仍是设计文档中的概念，未实现。

### 4. 2026-05-06 新增未验证路径 → 已验证/已修复

- **K. Footage 弹窗预览在三场景下的素材生成验证** ✅ 已验证 — S1/S5/Fast Mode 新产物均
正确出现在 `/footage`，弹窗视频 controls + autoplay 正常，portfolio TOP50 截断正确。
- **L. 主题翻转后全页面一致性走查** ✅ 已走查 — `/fast` `/s1` `/s5` `/footage` 无暗色残留。
发现并修复: footage 页面 grid item 无 thumbnail fallback 的 `text-white/40` icon 在
`#FCF5F2` 浅色背景上不可见 → 改为 `text-[var(--text-muted)]`。

### 5. 2026-05-06 测试中发现的新问题

- **S1 `final_video_path` 未回写** — Remotion 组装后最终视频路径未写入 pipeline state，
`final_video_path` 为空字符串。audit 报告视频存在(13.5MB)但 state 无法引用。需检查
`remotion_assemble.py` 是否正确更新 state。
- **S5 strategy 节点 LLM 超时** — 已修复: `LLM_TIMEOUT_SECONDS=60s` 对 VLOG strategy 长
prompt 不足，改为 `_step_vlog_strategy` 内创建 `LLMClient(timeout=120.0)` 专用实例。
- **S1 `product_name` 字段读取错误** — 已修复: `s1_product_pipeline.py:100` 原代码读取
`product_catalog.get("name", "Product")`，但 API 请求传的是 `"product_name"` 字段，
导致 audit `product_mention` 检查使用 "Product" 占位符。改为
`product_catalog.get("product_name") or product_catalog.get("name", "Product")`。

### 6. 2026-05-22 新增（S1 连续分镜向 S2-S5 迁移）

> 详见 [`docs/superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md`](../../superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md)。

**已完成：**
- S3/S4/S5 后端 `continuity_storyboard_grid` step 接入
- `src/pipeline/continuity_utils.py` 共享抽象层（8 函数，24 测试）
- 13 个 POYO 模型 ID 修正（`kling-3-0` → `kling-3.0` 等）
- Kling sound / Wan aspect_ratio / Hailuo duration+resolution 参数适配
- S2/S3/S5 前端 `continuity_mode` 配置
- S2 `run_step` 缺失修复

**仍待完成：**
- **P0 — S3 E2E 全量验证**：代码完成，POYO 账户 402 insufficient credits，充值后重跑
- **P1 — S4 前端 `continuity_mode`**：SceneForm.tsx 中 S4 (`live_shoot`) 无独立表单块
- **P2 — `continuity_storyboard_grid` skill 品牌适配**：S2 `brand_mode=True` 时 micro_shots 硬编码 bottle warmer，需 LLM 驱动品牌分镜生成
- **P3 — 生产部署验证**：5 场景各跑一次 mock-mode 验证 continuity 产物存在

### 7. 2026-05-23 新增（视频生成速度优化）

> 详见 [`docs/analysis/video-generation-speed-root-cause-analysis.md`](../../analysis/video-generation-speed-root-cause-analysis.md) + [`docs/analysis/video-generation-speed-optimization-plan.md`](../../analysis/video-generation-speed-optimization-plan.md)。

**已完成（6 项全部实施）：**

| 编号 | 优化项 | 文件 | 预估收益 | 状态 |
|------|--------|------|----------|------|
| P0-3 | frame_variance 在 observe/off 模式下跳过 | `seedance_video_generate.py` | 15-30s/3clips | 已上线 |
| P0-2 | S4 clips 并发化（Semaphore(4) + gather） | `s4_live_shoot_pipeline.py` | 60s | 已上线 |
| P0-1 | S5 移除 sleep + 条件并发化 | `s5_brand_vlog_pipeline.py` | 100-130s | 已上线 |
| P1-1 | auto 模式减少 step-started state save | `step_runner.py` | 2-5s | 已上线 |
| P1-2 | auto 模式可选跳过 thumbnail_images | `step_runner.py` | 15-30s | 已上线（默认关闭）|
| P2-1 | keyframe 数量按 clips 需求限制 | `keyframe_images.py` + `s1_product_pipeline.py` | 30-120s | 已上线 |

**累计预估收益**：
- S1 典型场景：244s -> ~152s（提速 38%）
- S4 典型场景：210s -> ~155s（提速 26%）
- S5 典型场景：312s -> ~185s（提速 41%）

**验证结果**：16/16 相关测试通过，ruff lint 全通过。

**仍待完成：**
- **生产部署验证**：`.env.prod` 追加 `SKIP_THUMBNAIL_IN_AUTO=1`（如需要启用缩略图跳过）
- **收益实测**：同一组输入在优化前后跑时间对比，确认实际收益符合预期
- **质量非回归**：优化前后 audit_report 评分差异 < 0.05

### 8. 2026-05-25 新增（S1-S5 工作流阶段 3/4 收敛）

**已完成：**
- `S4/S5` gate step order 已与真实执行链路对齐，不再跳过 `continuity_storyboard_grid`
- `S4 gate_3_thumbnails`、`S5 gate_3_final` 已支持 state-assembled candidate，Gate Direct 契约已修正
- `S3/S4` continuity step 改为显式 skill 注册，不再依赖隐式 import 顺序
- continuity fallback 现在会写出 `_soft_degraded`、`_degraded_reason`、`_degraded_detail`，不再静默伪装成正常成功
- `status` API 与前端 `StageProgress` / `VideoWorkflow` / `StepByStepView` 已可显示 `soft_degraded_reasons` 摘要，continuity fallback 不再只存在于后端 state
- 前端已把 `soft_degraded_reasons.reason` 从内部码值映射为稳定用户文案，避免直接展示 `continuity_skill_fallback` 这类实现细节
- `tests/test_s3_e2e.py`、`tests/test_s5_e2e.py` 已改为 hermetic 回归：默认 patch `VideoDownloader`、`LLMClient`、`SeedanceClient`、`GPTImageClient`、TTS、audit，不再依赖外网、额度或内容审核状态
- hermetic 回归已分层：默认 `pytest` 仅跑 fast 集；完整慢集通过 `PYTEST_INCLUDE_HERMETIC_SLOW=1 pytest ...` 或 `make test-hermetic-full` 触发
- `continuity_storyboard_grid` 已从 bottle-warmer 硬编码模板收口为输入驱动：会吸收 `usage_scenario`、storyboard 文本、USP、品牌色，S5 本地 `clip_groups` 也会保留 `shot_type / product_angle / model_in_shot`
- `S2` 的品牌包语义已接入 continuity：`values`、`voice_guidelines`/`tone_of_voice`、`visual_constraints` 现在会进入 continuity prompt 和 `visual_identity`
- `S3` 的 creator/platform 语义已接入 continuity：`influencer_name`、source/target platform、`original_style_preserved` 与 remix `keep_notes` 现在会进入 continuity prompt；S3 fallback `clip_groups` 也会保留 creator pacing 和平台语境
- `S5` 的 vlog scene/persona 语义已接入 continuity：`scene_id` 对应的场景名称/描述、`story_description`、`selected_models` persona 现在会进入本地 continuity `clip_groups` 和 `visual_identity`
- `S1` 的 platform / brand narrative 语义已接入 continuity：`target_platforms`、brand tone、brand colors、`target_audience` 现在会进入共享 continuity prompt 与 `visual_identity`
- shared continuity 已补稳定导演意图结构：`clip_groups` 现在会产出 `scene_beat`、`beat_summary`、`transition_intent`，并透传到 `seedance-video-prompt`
- `S5` 本地 continuity 也已对齐这套结构：`_vlog_shots_to_clip_groups()` 现在同样会输出 `scene_beat`、`beat_summary`、`transition_intent`
- continuity audit 已开始消费这套结构：`asset_ready_audit` 新增 `director_intent_metadata` 检查，`continuity_score` 与 `continuity_direction_summary` 也已纳入 `scene_beat / transition_intent`
- gate 评分已开始消费导演意图元数据：`candidate_scorer._score_clip_candidate()` 现在会识别 `Narrative beat / Beat summary / Transition intent`，将其计入 `director_intent` 维度
- `video_prompts / vlog_strategy` 评分也已开始消费导演意图：`video_prompts` 新增专用 scorer，`vlog_strategy` scorer 也已从旧的 `title/hook/segments` 假设收口到当前真实的 `shots` 结构
- `S1/S3/S4/S5` 的 `seedance_clips.clip_details` 已开始直接透传 `scene_beat`、`beat_summary`、`transition_intent`，下游评分、audit 和诊断不再只能从 prompt 文本反推导演意图
- `candidate_scorer` 已进一步收口到结构化优先：`seedance_clips` 评分现在先读 `clip_details` 内的 `scene_beat / beat_summary / transition_intent`，只有结构化字段缺失时才回退到 prompt 文本解析
- `video_prompts` 评分也已收口到同一优先级：现在先读结构化 `scene_beat / beat_summary / transition_intent`，文本里的 `Narrative beat / Beat summary / Transition intent` 只保留为 fallback
- status / gate 诊断输出也已接入 continuity 导演意图：`/scenario/{scenario}/status/{label}` 与 `get_gate_state()` 现在都会返回 `continuity_diagnostics`，其中包含 `continuity_score`、`director_intent_metadata` 和逐段 `clip_directions`
- 前端 status / gate 面板也已接入这份诊断：`StageProgress` 与 `GatePanel` 现在会展示 `continuity_score`、`director_intent_metadata` 和前两段 `clip_directions`
- 候选比较卡片也已开始消费 continuity 摘要：`CandidateSelector` 现在会从 `continuity_direction_summary` / `clip_details` / 单条导演意图字段中抽取前两段 `scene_beat + transition_intent` 直接展示
- 候选卡片的 continuity 可解释性也已补齐：当 `score.breakdown.director_intent` 存在时，`CandidateSelector` 会直接显示导演意图得分，和卡片里的 `scene_beat / transition_intent` 摘要对齐
- 候选卡片 explanation 也已按 continuity 优先重排：当 explanation 文本包含 `director_intent=...` 时，`CandidateSelector` 会把它提到最前面；若文本里没有但 breakdown 有该维度，也会自动补到 explanation 前缀
- gate/status 顶部诊断摘要也已统一顺序：`StageProgress` 与 `GatePanel` 现在都通过同一个 helper 按“director_intent 状态优先，continuity score 次之”的顺序展示
- 结果页/质量视图 continuity 解释也已对齐：`DirectorPlayback` 与 `QualityDashboard` 现在复用同一份 continuity diagnostics helper，并展示逐段 `scene_beat / transition_intent`
- 版本对比卡片 continuity 解释也已接入：`CompareView` 现在会在版本卡片里直接展示 `director_intent` 摘要、`continuity score` 和首段 `scene_beat / transition_intent`
- 已选版本决策区 continuity verdict 已接入：`CompareView` 底部 action 区现在会对当前选中版本重复展示同一份 continuity diagnostics，下载/发布前无需再回看卡片
- continuity 已进入统一对比表：`CompareView` 的 quality comparison table 现在新增 `Director intent` 与 `Continuity score` 两行，版本间 continuity 差异不再只存在于卡片摘要
- continuity 已补表格解释行：`CompareView` 的 quality comparison table 现在还会显示 `Continuity verdict`，直接给出每个版本的 continuity 摘要与首段导演意图
- `CompareView` 的 continuity 信息已做轻量去重：版本卡片现在只保留 continuity 摘要，逐段 `scene_beat / transition_intent` 细节下沉到统一对比表和已选版本 verdict
- `CompareView` 的 `Continuity verdict` 已加长度控制：长 `transition_intent` 会在表格中软截断，完整内容保留在 hover `title`
- `CompareView` 的统一对比表已做视觉分组：continuity 三行现在归入独立 `Continuity diagnostics` section，与普通 `Quality criteria` 分区显示
- `CompareView` 的 continuity section 已压成 compact summary：`Director intent` 与 `Continuity score` 现在合并为一行 `Continuity summary`，继续压缩纵向高度
- `CompareView` 的 `Continuity summary` 已改成 badge/pill 形态：状态与分数用紧凑标签显示，进一步降低表格文本密度
- `CompareView` 的 `Continuity verdict` 已从原生 `title` 升级为可 focus tooltip：截断预览之外，完整文案现在可通过 hover/focus 稳定查看
- `CompareView` 的 verdict tooltip 已抽成轻量复用组件：`InlineTooltip` 现已接管 continuity verdict 的 hover/focus 展示，避免 tooltip 逻辑继续内嵌增长
- `InlineTooltip` 已在 `GatePanel` continuity diagnostics 复用：长 `beatSummary` / `transitionIntent` 不再直接撑开审批面板，完整文案通过 hover/focus 查看
- `InlineTooltip` 已在 `StageProgress` continuity diagnostics 复用：运行中视图里的长 `beatSummary` / `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 已在 `QualityDashboard` continuity diagnostics 复用：结果页质量面板里的长 `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 已在 `DirectorPlayback` continuity diagnostics 复用：结果页导演回放视图里的长 `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 本身已收口为轻量可配组件：现支持 `placement`、默认移动端安全宽度，以及 `focus/active` 下的稳定显示
- continuity 相关截断逻辑已抽成共享 util：`truncateDiagnosticText()` 现收口到 `web/src/lib/diagnosticText.ts`，`GatePanel` / `StageProgress` / `QualityDashboard` / `DirectorPlayback` 不再各自维护一份副本
- `StageProgress` 的历史 hook warning 已清理：stage completion tracking 改用 `ref + stageCompletionKey`，不再在 effect dependency 内嵌复杂表达式
- `StageProgress` polling 启动 effect 的 `exhaustive-deps` suppress 已移除：初始 timer 现在通过 `pollRef.current()` 调用最新 poll callback，不再捕获 stale callback
- `StageProgress` 的卸载安全已补齐：poll response、completion delay、celebration reset 都会检查 mounted 状态并在 unmount cleanup 中清理 timer
- `StageProgress` 轮询失败阈值路径已补测试：连续 status 请求失败达到阈值后会停止继续 schedule poll，并显示连接中断提示
- `StageProgress` 服务端错误态已停止 elapsed timer：status 返回 `error` / `pipeline_degraded` 后不再继续后台计时
- `StageProgress` timer cleanup 已收口为内部 helper：poll timeout、elapsed interval、completion delay、celebration reset 不再分散手写清理逻辑
- `StageProgress` 服务端错误通知已去重：同一错误签名只触发一次 `onError`，避免重复 status/error 路径重复通知父组件
- `StageProgress` gate pause 通知已去重：同一 `current_step` 的 `paused/awaiting_approval` 只触发一次 `onGatePause`
- `StageProgress` paused 语义已补回归：等待 gate 审核期间继续 elapsed 计时与 status polling，用于保留总等待时间并感知审批后的恢复
- `StageProgress` paused polling 已降频：进入 `paused/awaiting_approval` 后 status polling 从 2s 调整为 10s，elapsed 仍按秒计时
- `StageProgress` polling cadence 常量已提升到模块级：base/paused/max/failure threshold 不再在组件 render 内重复声明
- `StageProgress` stage definitions 命名已收口：局部 `STAGES` 改为 `stageDefs`，避免把模块级稳定定义误读成 render 内新建常量；未引入无收益 `useMemo`
- `StageProgress` stage runtime 派生逻辑已抽为纯函数：progress、active stage、completion key 可直接单测，不再完全埋在组件 render 内
- `StageProgress` 剩余时间估算已抽为纯函数：`estimateRemainingSeconds()` 覆盖 early elapsed、complete、同类型平均耗时 fallback 边界
- `StageProgress` 总进度计算已抽为纯函数：`deriveTotalProgress()` 统一产出 total steps/done/progress，并覆盖空 stage 边界
- `StageProgress` 初始 polling timer cleanup 已复用内部 helper：首次 status 请求前 unmount 不会再触发后台 status 请求
- Smart Create 的 `StageProgress` 父级错误消费已接入：`page.tsx` 现在传入 `onError`，status 返回 `error` / `pipeline_degraded` 时会停止 execution bar、清理 active pipeline 并弹页面级 toast，同时保留进度面板内的错误详情
- Smart Create 错误恢复逻辑已补行为级回归：`handleSmartCreateStageError()` 覆盖停止生成、清理 active pipeline、toast 展示和空错误 fallback
- continuity 规则导演层已增强：`continuity_storyboard_grid` 现在会派生 `director_profile`，把 `story_arc`、`audience_tension`、`brand_promise`、`platform_pacing`、`creator_cadence` 注入 `visual_identity`、`clip_groups` 和 Seedance prompt
- continuity 组合回归已通过：`tests/test_continuity_storyboard_grid.py`、`test_candidate_scorer_continuity.py`、`test_s1_continuity_pipeline.py`、`test_s3_e2e.py`、`test_s4_e2e.py`、`test_s5_e2e.py` 共 `75 passed, 12 deselected`
- LLM director planner 评估已落 ADR-007：当前不在默认 continuity 热路径引入 LLM，未来如实现必须 feature-flagged、schema-validated，并保留 deterministic fallback
- 非 S1 推荐阶段已收口：`RecommendPanel` 不再为 S2-S5 调用 `startS1StepByStep()`，改用本地 config 摘要，避免“其他场景 auto + gate”口径下仍误触发 S1 逐步接口
- GuidedForm continuity 配置已从 S1-only 扩展到 S1-S5：`product_direct`、`brand_campaign`、`influencer_remix`、`live_shoot_to_video`、`brand_vlog` 都会提交 `continuity_mode`、`storyboard_grid`、`transition_style`
- Smart Create async submit 已统一透传 continuity 参数，S2-S5 不再因为前端 payload 裁剪而丢失 continuity 配置；S5 专用 endpoint 类型也已补齐这些字段
- S4 前端场景路由已修正：`live_shoot_to_video` 现在会映射到 `/scenario/s4/submit` 与 `/s4` 页面，不再回退到 S1
- 前端 API wrapper 类型债已收口一层：`web/src/components/api.ts` 不再使用显式 `any` 返回类型，场景运行、StepRunner、发布、dashboard wrapper 已改为结构化宽类型，`eslint src/components/api.ts` 与 `tsc --noEmit` 均通过
- 首页编排层 lint 债已清零：`web/src/app/page.tsx` 移除未使用 import/store setter，并补齐实际依赖的 hook dependency，`eslint src/app/page.tsx` 已无 warning
- 结果/分发链路类型债已收口一层：`DistributionView`、`PublishPanel`、`OneShotResultView` 已移除显式 `any`，改用 distribution plan、publish result、one-shot result 的局部结构化宽类型；`tsc --noEmit` 通过，目标 lint 仅剩 `OneShotResultView` 两处 Next.js `<img>` 性能 warning
- 结果/作品/审批展示链路 lint 已进一步清零：`OneShotResultView` 对后端运行时媒体 URL 保留原生 `<img>` 并补精确 lint 例外，`works/page.tsx` 与 `ReviewPanel` 已移除显式 `any` 和未用表达式；目标 lint、`tsc --noEmit`、continuity/routing 单测均通过
- Step-by-step 展示链路类型债已收口：`AssetCard`、`components/types.ts`、`StepByStepView` 已移除显式 `any`；`AssetCard` 的 render-time `Math.random()` 已替换为确定性波形高度，避免 React purity warning；目标 lint、`tsc --noEmit`、continuity/routing 单测均通过

**当前剩余缺口：**
- **P0 — S2-S5 step-by-step 已收口为产品选择**：后端通用 `step/regenerate` 已接到 `StepRunner`，前端入口和推荐阶段现在都明确为“仅 `S1` 开放 step-by-step，其他场景走 auto + gate”。剩余问题只是不确定未来是否要补真正的多场景逐步交互
- **P1 — hermetic 测试提速已基本达标**：`S3/S4/S5` 三套回归已从约 74s 降到约 25s，`S3+S5` 组合约 15s。当前问题已从“过慢影响本地回归”收缩为“后续可按需继续做增量优化”
- **P2 — LLM director planner 已决策延后**：ADR-007 明确默认保留 deterministic `director_profile`，不在无 poyo token 阶段扩展默认热路径
- **P3 — 生产侧 continuity / gate 真流量验证未完成**：本轮修的是本地正确性，不是生产 API 真流量验收

**建议下一步顺序：**
1. 继续清理无 poyo token 也能验证的前端/文档口径不一致
2. 保持 continuity 产物质量增强在 hermetic / mock / unit 层推进
3. 充值后再做生产 smoke

---
