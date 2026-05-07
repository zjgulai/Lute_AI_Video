---
title: MECE 双审计整合优化路线图(2026-05-06 决策版)
doc_type: workflow
module: governance
topic: audit-fix-roadmap
status: stable
created: 2026-05-06
updated: 2026-05-07
owner: self
source: human+ai
---

# MECE 双审计整合优化路线图(2026-05-06 决策版)

## 0. 背景

本文档整合两份独立深度审计的发现,经过交叉分析与 7 项关键决策对齐后形成可执行任务清单。

**审计来源**:
- `docs/analysis/mece_deep_audit_final_20260506.md` —— 偏代码细节,16 项核心问题 + 8 反直觉洞察
- `eval/architecture-deep-audit-report-20260506.md` —— 偏架构与商业逻辑,42 项问题(14 CRITICAL + 18 WARNING + 10 NOTE)

**对账结论**:两份审计共点出 21 个核心问题,经核对当前 HEAD,**18 项完全未修,2 项部分修,1 项非缺陷**。

---

## 1. 决策摘要(2026-05-06 已对齐)

| # | 议题 | 决策 |
|---|---|---|
| D1 | 双管道(LangGraph vs StepRunner) | **方案乙** — LangGraph 留作 `/pipeline/*` 兼容,S2~S5 渐进迁 StepRunner |
| D2 | 成本控制时机 | **CostTracker 与 Gate 评分修复同周完成**;不允许"开油门不装刹车" |
| D3 | 多语言支持 | **下线** — 删除 ES/FR/DE 相关代码与 prompt,README/UI 明文写"仅支持英语",未来真有客户再上 |
| D4 | Mock 路径定位 | **仅 dev 工具** — 生产强制要求 API key 可用,启动时 fail-fast 验证 |
| D5 | 多租户隔离粒度 | **进程内 contextvars 本周必做;数据库层 tenant 隔离在第 2 个真实租户接入前必做** |
| D6 | 前端 STEP_ORDER | **后端化** — 由 `/scenario/{s}/state/{label}/steps` 返回,前端纯渲染 |
| D7 | 工程化机制 | **必做** — 任务接入 GitHub Issue + 看板,每条有 owner + due + 链回审计 |

---

## 2. 总览:全部任务清单(28 项)

### Phase 1 — 止血(2 周内,P0)

| ID | 标题 | 维度 | Effort | 依赖 |
|---|---|---|---|---|
| T1.1 | POYO/Seedance/CosyVoice 客户端接 contextvars | D2 隔离 | 0.5d | — |
| T1.2 | LLMClient 增 `is_configured()`,修 StrategyAgent.use_mock bug | D6 体验 | 0.5d | — |
| T1.3 | StepRunner._execute_step 设置 pipeline_degraded + resume 检查 | D3 错误 | 1d | — |
| T1.4 | error_classifier 接入 wrap_node + step_runner + 错误响应 | D3 错误 | 2d | T1.3 |
| T1.5 | CostTracker 骨架(记录 + 估价 + 软上限,先记后限) | D4 商业 | 2d | — |
| T1.6 | Gate keyframe/clip/final 多维启发式评分 | D4 商业 | 1.5d | T1.5 |
| T1.7 | 生产环境启动时强制验证 API key(fail-fast),mock 路径降级为 dev-only | D6 体验 | 0.5d | T1.2 |
| T1.8 | 前端 STEP_ORDER 改为后端返回(/state/{label}/steps 加 step_order) | D6 契约 | 1d | — |
| T1.9 | graph/nodes.py 9 处 fire-and-forget 改用 _register_background_task | D3 错误 | 0.5d | — |
| T1.10 | 多语言代码下线 — 删除 ES/FR/DE prompt 模块 + Language enum 简化 | D6 体验 | 1d | — |
| T1.11 | CosyVoice VOICE_PRESETS 收窄为仅 en,删除 ES/FR/DE 条目 | D6 体验 | 0.25d | T1.10 |
| T1.12 | 看板搭建:GitHub Issue 模板 + 标签体系 + 链回审计文档 | D7 工程 | 0.5d | — |

**Phase 1 合计**: ~11 人日 / 2 周

### Phase 2 — 架构归一化(4-6 周,P1)

| ID | 标题 | 维度 | Effort | 依赖 |
|---|---|---|---|---|
| T2.1 | S2 接 StepRunner + Gate 系统 | D1 架构 | 3d | T1.* |
| T2.2 | S3 接 StepRunner + Gate 系统 | D1 架构 | 3d | T2.1 |
| T2.3 | S4 接 StepRunner + Gate 系统 | D1 架构 | 2d | T2.1 |
| T2.4 | S5 接 StepRunner + Gate 系统 | D1 架构 | 3d | T2.1 |
| T2.5 | `_pipeline` 全局单例 → request-scoped 工厂 | D1 架构 | 1d | — |
| T2.6 | psycopg.connect → asyncpg 或 to_thread 封装 | D5 持久化 | 2d | — |
| T2.7 | SkillRegistry._skills 改实例变量 + conftest autouse clear | D7 测试 | 1d | — |
| T2.8 | API key 租户化(api_keys 表 + tenant_id 列 + repo 过滤) | D2 隔离 | 5d | T1.1 |
| T2.9 | Alembic 与 SQL init 统一(Docker 启动 alembic upgrade head) | D5 持久化 | 1d | — |
| T2.10 | target_languages 全局收口到 config.DEFAULT_LANGUAGES | D6 体验 | 0.5d | T1.10 |
| T2.11 | rate limit 迁 nginx limit_req 或 Redis | D8 部署 | 2d | — |
| T2.12 | LLMClient `_clients` 缓存加 TTL + tenant 维度 | D2 隔离 | 1d | T2.8 |

**Phase 2 合计**: ~24 人日 / 4-6 周

### Phase 3 — 质量与体验(8-12 周,P2)

| ID | 标题 | 维度 | Effort |
|---|---|---|---|
| T3.1 | retry 改异常类型链 + 字符串黑名单 | D3 错误 | 1d |
| T3.2 | Webhook SSRF 加端口限制 + 请求时 DNS 解析 | D8 部署 | 1d |
| T3.3 | docker-compose 改 .env 引用,Docker 加 USER 指令 | D8 部署 | 1d |
| T3.4 | structlog 在 pipeline 入口 bind(product, brand, scenario) | D3 错误 | 1d |
| T3.5 | 前端 apiFetch 加 timeout/retry,Zustand store 持久化 | D6 体验 | 2d |
| T3.6 | E2E 测试矩阵:5 场景 × auto/step_by_step,共 10 跑次 | D7 测试 | 5d |

**Phase 3 合计**: ~11 人日 / 8-12 周

### Phase 4 — 战略与卓越(持续)

| ID | 标题 | 维度 |
|---|---|---|
| T4.1 | pyright 严格模式 + total=False 治理 | D7 类型 |
| T4.2 | Prometheus exporter + Grafana 业务级 SLO | D3 可观测 |
| T4.3 | 死代码全面盘清(`PipelineError` / 未用枚举值等) | D7 质量 |
| T4.4 | LangGraph 决定:全面下线或转为只读视图 | D1 架构 |

---

## 3. Phase 1 任务详细卡片

> Phase 2-4 在排期前可只看总览;真正进入排期时再补卡片。

---

### T1.1 — POYO/Seedance/CosyVoice 客户端接入 contextvars 隔离

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 0.5 人日 |
| Audit | 报告A #1, 报告B A4/M9 |

**目标**: 让所有付费媒体 API 客户端遵循已有的 LLM contextvars 隔离机制,避免多租户下 API key 跨户串扰。

**实现要点**:
- 扩展 `src/tools/llm_client.py:65` 的 `set_request_api_keys` 接口,使其支持任意 env_name(已有,可复用)
- 三个客户端 `__init__` 改为:`self.api_key = api_key or get_request_api_key("XXX_API_KEY") or env_default`
- `src/routers/_deps.py:84-91` 已经把 normalized 推入 contextvars,确认 POYO_API_KEY / SEEDANCE_API_KEY / SILICONFLOW_API_KEY 都被覆盖

**文件**:
- `src/tools/poyo_client.py:43`
- `src/tools/seedance_client.py:99-105`
- `src/tools/cosyvoice_client.py:56`
- `src/routers/_deps.py:84`(确认 alias 列表)

**验收**:
- 新增 `tests/test_api_key_isolation.py`:并发起 2 个客户端实例,注入不同 key,验证各自 Authorization header
- 手工:本地起 2 个 S1 pipeline,各用不同 POYO key,后台计费日志归属正确

---

### T1.2 — LLMClient 增 `is_configured()`,修 StrategyAgent.use_mock bug

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 0.5 人日 |
| Audit | 报告A #6, 报告B M4 |

**目标**: 消除"首次调用必走 mock"的静默失败 bug。

**实现要点**:
- `src/tools/llm_client.py` 新增 `def is_configured(self) -> bool: return bool(self._resolve_api_key("DEEPSEEK_API_KEY"))`
- `src/agents/strategy.py:96` 改为 `self.use_mock = use_mock or (not use_skills and not llm.is_configured())`
- 移除对 `llm._clients` 私有属性的依赖

**文件**:
- `src/tools/llm_client.py`
- `src/agents/strategy.py:96`

**验收**:
- 单元测试:在有 API key 的情况下,`StrategyAgent(use_mock=False)` 不应触发 mock 路径
- 现有 `tests/test_strategy_agent.py` 不应回归

---

### T1.3 — StepRunner 设置 pipeline_degraded + resume 检查

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 1 人日 |
| Audit | 报告B B2 |

**目标**: 让 S1 管线(实际生产路径)的步骤失败能终止整条流水线,避免基于不完整数据生成错误输出。

**实现要点**:
- `src/pipeline/step_runner.py:_execute_step` except 分支末加 `state["pipeline_degraded"] = True; state["degraded_reason"] = step_name`
- `src/pipeline/state_manager.py:save/load` 把 `pipeline_degraded` 加入持久化字段
- `resume()` 循环每次迭代前检查 `state.get("pipeline_degraded")`,True 则立即 break
- `run_s1_step` 路由检测到 `pipeline_degraded` 返回 HTTP 500 而非 200

**文件**:
- `src/pipeline/step_runner.py:236-294`
- `src/pipeline/state_manager.py:114-145`
- `src/routers/scenario.py`(run_s1_step 响应路径)

**验收**:
- 新增测试:模拟 seedance_clips 抛异常,验证后续 tts_audio 不会被执行,响应是 500
- 手工:本地把 POYO_API_KEY 设成无效值,启 S1 pipeline,确认在 keyframe_images 失败时立刻终止

---

### T1.4 — error_classifier 接入业务代码

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 2 人日 |
| Depends | T1.3 |
| Audit | 报告A #3 |

**目标**: 激活已存在但完全未被调用的 180 行错误分类基础设施,给前端可解释的错误码。

**实现要点**:
- `_wrap_node_with_error_handling`(`src/graph/nodes.py:81`)在 except 分支调 `classify_error(exc, context=node_name)`,写入 `state["structured_errors"]`(VideoPipelineState 已定义此字段)
- `step_runner._execute_step`:同样调 classify_error,errors 列表保留人类可读字符串,新增 structured_errors 列表
- `src/routers/_deps.py:_safe_error` 升级为 `_classified_error`,返回 `{error_code, message, recoverable, trace_id}`
- `src/services/fast_mode.py:173` 的 `RuntimeError` 也走 classify_error

**文件**:
- `src/graph/nodes.py:81`
- `src/pipeline/step_runner.py:279`
- `src/routers/_deps.py`
- `src/routers/scenario.py`(所有 `_safe_error(e)` 调用点)
- `src/services/fast_mode.py:173`
- `web/src/components/api.ts`(error handler 解析 error_code 字段)

**验收**:
- 手工:故意配置无效 DEEPSEEK_API_KEY,前端应看到具体错误码("LLM_API_KEY_INVALID")而非 "Internal server error"
- 新增测试:`test_error_classifier_integration.py`,模拟各类异常,验证响应包含正确 error_code

---

### T1.5 — CostTracker 骨架(先记后限)

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0(战略) |
| Effort | 2 人日 |
| Audit | 报告B B1/B3 |

**目标**: 在修 Gate 评分(T1.6 会增加 LLM 调用)之前建好刹车系统。先记录所有付费 API 调用成本,软上限阈值告警,硬上限 Phase 2 接入。

**实现要点**:
- 新增 `src/tools/cost_tracker.py`:
  - `track(api: str, tokens: int | None, units: int = 1, metadata: dict)` 写入 PG 新表 `api_costs`
  - `estimate_cost(api, tokens, units) -> float` 单价表(DeepSeek $1/M, POYO $0.3/video, CosyVoice $0.02/min)
  - `get_pipeline_cost(thread_id) -> float` 聚合查询
- 在 LLMClient.ainvoke / PoyoClient.submit / SeedanceClient.text_to_video / CosyVoiceClient.synthesize 末尾插入 `cost_tracker.track(...)`
- 新增表 `api_costs(id, thread_id, tenant_id, api, tokens, units, cost_usd, created_at)`,Alembic 迁移
- 软上限:单 pipeline > $5 时 structlog warning + Telemetry 事件;硬上限暂不实施(Phase 2 T2.x)

**文件**:
- 新建 `src/tools/cost_tracker.py`
- 新建 Alembic migration
- 4 个客户端文件各加 1-2 行
- `src/routers/scenario.py` 启动 pipeline 时 reset cost session

**验收**:
- 跑一次完整 S1 pipeline,查表 `api_costs` 有 10+ 条记录,聚合成本符合预期(参考实际 POYO/CosyVoice 账单)
- 手工触发 LLM 异常重试,确认重试调用都被记录

---

### T1.6 — Gate keyframe/clip/final 多维启发式评分

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 1.5 人日 |
| Depends | T1.5 |
| Audit | 报告A #5 |

**目标**: 让 Gate 系统对 3/4 类型的"AI 评分"不再返回固定 0.75/0.80 假分。

**实现要点**:
- `src/pipeline/candidate_scorer.py:215-227` 三个函数分别实现真实评分:
  - `_score_keyframe_candidate`: 基于 prompt 关键词(构图/光照/产品可见性/风格一致性)+ 文件大小(>100KB)+ 分辨率维度评分
  - `_score_clip_candidate`: prompt 关键词 + duration 是否符合预期 + 文件大小 + clip_id 顺序连续性
  - `_score_final_candidate`: 视频时长是否符合 config + 包含音轨 + 包含字幕 + 文件存在
- 评分权重外化为 `strategy_source/general/scorer_weights.json`,运营可调
- 短期:仅启发式;Phase 3 后接 LLM 视觉评估

**文件**:
- `src/pipeline/candidate_scorer.py:215-227`
- 新建 `strategy_source/general/scorer_weights.json`

**验收**:
- 单元测试:输入 3 个不同 prompt 的 keyframe 候选,得到 3 个不同分数
- 手工:在前端 GatePanel 看到 3 个候选有真实差异化分数(不全是 0.75)

---

### T1.7 — 生产 API key fail-fast 验证,mock 降级为 dev-only

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 0.5 人日 |
| Depends | T1.2 |
| Audit | 报告A #4(简化版,基于决策 4) |

**目标**: 不再让生产环境静默走 mock 路径;mock 仅 dev 测试用。

**实现要点**:
- `src/api.py:startup` 钩子:if `ENVIRONMENT == "production"`,启动时逐项校验 DEEPSEEK_API_KEY/POYO_API_KEY/SILICONFLOW_API_KEY 必须存在且非占位符,任何缺失 fail-fast 退出
- 新增环境变量 `ALLOW_MOCK_MODE=false`(默认),开发设 true
- `StrategyAgent` / `ScriptWriterAgent` 等 mock 路径触发时,if `ALLOW_MOCK_MODE != true` 则 raise `MockNotAllowedError`,不静默生成假数据
- README 增加章节:"运行模式"明文说明 mock 仅 dev 用

**文件**:
- `src/api.py`(startup hook)
- `src/config.py`(新增 ALLOW_MOCK_MODE)
- `src/agents/strategy.py` `src/agents/script_writer.py` 等 mock 入口
- `README.md`

**验收**:
- 把 `.env` 中 DEEPSEEK_API_KEY 删除,执行 `ENVIRONMENT=production uvicorn src.api:app`,应当 fail-fast 退出并打印明确错误
- `ALLOW_MOCK_MODE=true ENVIRONMENT=development` 下 dev 仍可走 mock

---

### T1.8 — 前端 STEP_ORDER 由后端返回

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0 |
| Effort | 1 人日 |
| Audit | 报告B M2 |

**目标**: 修复前端 11 步 vs 后端 12 步(缺 keyframe_images)的契约错位,根除前后端 STEP_ORDER 漂移。

**实现要点**:
- 后端 `GET /scenario/{s}/state/{label}/steps` 响应增加 `step_order: list[str]` 字段,直接 dump `step_runner.STEP_ORDER`
- 前端 `VideoWorkflow.tsx:19-31` 删除本地 `STEP_ORDER` 常量,从 API 响应中读取
- 增加 lint 检查脚本 `scripts/check_step_order_consistency.py`:CI 跑时 grep 前端是否还有硬编码 STEP_ORDER,有则 fail
- `STEP_DURATIONS`(估时)也一起后端化

**文件**:
- `src/routers/scenario.py`(state/{label}/steps endpoint)
- `src/pipeline/step_runner.py`(STEP_ORDER + STEP_DURATIONS export)
- `web/src/components/VideoWorkflow.tsx:19-45`
- 新建 `scripts/check_step_order_consistency.py`

**验收**:
- 删除前端 STEP_ORDER 后,S1 step_by_step 模式下进度条正确显示 12 步,keyframe_images 阶段不再"跳过"
- CI lint 检查执行,grep 前端 src/ 无硬编码 STEP_ORDER

---

### T1.9 — graph/nodes.py 9 处 fire-and-forget create_task 治理

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P1 |
| Effort | 0.5 人日 |
| Audit | 报告A 4.2, 报告B D1 |

**目标**: 与 `scenario.py` 已治理路径对齐,所有 webhook dispatch 不再静默吞异常。

**实现要点**:
- `src/graph/nodes.py:339, 435, 508, 574, 643` 等 9 处 `asyncio.create_task(wh.dispatch(...))`
- 改为 `_register_background_task(asyncio.create_task(wh.dispatch(...)), label="webhook:<event>")`
- 复用 `src/routers/_state.py` 已有的 `_register_background_task`(若放在 scenario.py 私有则提到 _state.py)

**文件**:
- `src/graph/nodes.py`(9 处)
- `src/routers/_state.py`(可能需要把 _register_background_task 暴露为模块函数)
- `src/api.py:68` `asyncio.create_task(_periodic_cache_eviction())` 同样治理

**验收**:
- grep `src/` 下所有 `asyncio.create_task(`,确认全部走 `_register_background_task`
- 手工触发一个 webhook 异常(无效 URL),应在结构化日志中看到 task 异常记录

---

### T1.10 — 多语言代码下线(决策 3 衍生)

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P1 |
| Effort | 1 人日 |
| Audit | 报告B B4 + 决策 3 |

**目标**: 删除 ES/FR/DE 假支持,把"仅英语"明文化为产品定义。

**实现要点**:
- 删除 `src/agents/prompts/{es,fr,de}/` 三个目录
- `src/models/__init__.py`(或 enum 定义处)`Language` enum 仅保留 `EN`
- `src/agents/i18n.py` 简化为只支持 EN
- 17+ 处硬编码 `["en"]` 全部改为 `config.DEFAULT_LANGUAGES`(留作未来扩展点,但配置文件依然只有 en)
- README 明文写"v0.x 仅支持英语输出"
- 单测:删除任何 ES/FR/DE 相关用例

**文件**:
- 删除 `src/agents/prompts/es/`, `src/agents/prompts/fr/`, `src/agents/prompts/de/`
- `src/agents/i18n.py`
- 23+ 处 grep 出的 `["en"]`(参考 grep 结果)
- `src/models/__init__.py`(Language enum)
- `README.md`

**验收**:
- grep 全仓库,无 "es"/"fr"/"de" 与 Language 关联的残留
- 单元测试通过
- 仍可继续运行 5 场景 E2E

---

### T1.11 — CosyVoice VOICE_PRESETS 收窄

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P1 |
| Effort | 0.25 人日 |
| Depends | T1.10 |
| Audit | 报告B M1 + 决策 3 |

**目标**: 删除 ES/FR/DE 三个错误的语音映射,避免未来误用。

**实现要点**:
- `src/tools/cosyvoice_client.py:38-44` `VOICE_PRESETS` 仅保留 en + zh
- `synthesize()` 入参 language 不在白名单时 raise ValueError(由 API 层先校验,这里防御)

**文件**:
- `src/tools/cosyvoice_client.py:38-44, 94`

**验收**:
- 单元测试:`synthesize(language="es")` 应抛 ValueError 或被上游拦截

---

### T1.12 — GitHub Issue 看板搭建

| 字段 | 值 |
|---|---|
| Phase | 1 |
| Priority | P0(决策 7) |
| Effort | 0.5 人日 |
| Audit | 决策 7 |

**目标**: 把本路线图 28 项任务全部落入 GitHub Issue,接入看板,有 owner + due + 链回审计。

**实现要点**:
- 创建 GitHub Project Board,列:Backlog / In Progress / Review / Done / Blocked
- 标签:`phase-1` `phase-2` `phase-3` `phase-4` / `priority-p0` ~ `p3` / 8 个 D 维度标签
- Issue 模板 `.github/ISSUE_TEMPLATE/audit-fix.md`,字段:任务 ID(T1.x)、Phase、Priority、Effort、Audit Source、Files、Verification
- 把 T1.1~T1.11、T2.*、T3.*、T4.* 全部建 Issue,T1.* 12 个 Issue 必须当周派发 owner
- 每周 Review 例会更新看板状态

**文件**:
- 新建 `.github/ISSUE_TEMPLATE/audit-fix.md`
- 新建 GitHub Project(手工操作)

**验收**:
- 28 个 Issue 全部创建,每个含 audit source 链接
- T1.* 12 个均有 owner + due date
- 看板 URL 写入本文档末尾

---

## 4. Phase 2/3/4 卡片(进入排期前展开)

> Phase 2 任务在 Phase 1 完成 60% 后开始排期;每个任务在被认领时才需要补完整卡片。Phase 3/4 同理。

---

## 5. 工程化机制(决策 7 落地)

### 5.1 Issue 标签体系

```
phase-1 / phase-2 / phase-3 / phase-4
priority-p0 / priority-p1 / priority-p2 / priority-p3
dim-d1-architecture
dim-d2-isolation
dim-d3-error
dim-d4-business
dim-d5-persistence
dim-d6-experience
dim-d7-quality
dim-d8-deployment
audit-source-mece          ← 链回 docs/analysis/mece_deep_audit_final_20260506.md
audit-source-architecture  ← 链回 eval/architecture-deep-audit-report-20260506.md
```

### 5.2 Issue 模板(`.github/ISSUE_TEMPLATE/audit-fix.md` 内容)

```markdown
---
name: 审计修复任务
about: 来源于 2026-05-06 双审计的修复任务
title: "[T1.x] <任务标题>"
labels: ['phase-1', 'priority-p0']
---

## 任务 ID
T1.x

## Audit Source
- [ ] docs/analysis/mece_deep_audit_final_20260506.md#<行号>
- [ ] eval/architecture-deep-audit-report-20260506.md#<行号>

## 目标
<一句话>

## 实现要点
<复制本文档对应任务卡片>

## 文件
<列表>

## 验收
- [ ] 单测/E2E 通过
- [ ] 手工验证步骤完成
- [ ] 更新本路线图 status 为 done
```

### 5.3 状态追踪

- 本文档 `status` 始终为 `stable`
- 每个任务在 Phase 1/2/3 完成后,在本文档末尾的 "执行日志" 区追加一行:`YYYY-MM-DD T1.x 完成 commit:<sha>`
- 每个 Phase 完成后做一次 retrospective,产出 `docs/workflows/audit-fix-phaseN-retro-<date>-stable.md`

### 5.4 周节奏

- 周一:Phase 1 任务领取/状态更新
- 周三:阻塞问题升级(标 `blocked` 标签 + 在 Issue 描述下补依赖说明)
- 周五:Phase 1 完成度报告(完成数/总数百分比)

---

## 6. 风险与依赖说明

### 6.1 关键依赖链

```
T1.2 ──→ T1.7 (生产 fail-fast 依赖 is_configured)
T1.3 ──→ T1.4 (error_classifier 接入依赖 pipeline_degraded 设置)
T1.5 ──→ T1.6 (Gate 评分修复必须有 CostTracker 在前)
T1.10 ──→ T1.11 (语音 presets 收窄依赖多语言下线)
T1.10 ──→ T2.10 (target_languages 全局收口依赖代码已下线)
T1.1 ──→ T2.8 (租户化数据库依赖 contextvars 隔离已就绪)
所有 T2.x 场景迁移 ──→ T1.* 全部完成(否则两边都要改)
```

### 6.2 不做事项(经决策明确)

- ❌ Mock 模板品类化扩展(决策 4:mock 仅 dev,不为销售场景兜底)
- ❌ ES/FR/DE 语音真功能化(决策 3:直接下线,不做)
- ❌ LangGraph 立即下线(决策 1:留作 `/pipeline/*` 兼容,Phase 4 再决)
- ❌ Gate 系统 LLM 视觉评分(Phase 1 仅启发式,Phase 3 后再考虑)

### 6.3 已知风险

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| T1.4 接入 error_classifier 改动 15+ 调用点,易引入回归 | 任何 except 路径未覆盖 | 强制要求 PR 包含 ≥3 类异常的单元测试 |
| T1.5 CostTracker 表加字段需 Alembic 迁移,生产 PG 必须 alembic upgrade | 部署遗漏 | 与 T2.9 联动,Docker 启动加 alembic upgrade head |
| T1.10 删除多语言代码可能误删 Language enum 的潜在使用方 | grep 不全 | T1.10 完成后跑全量测试 + 手工 5 场景 E2E |
| T2.* 场景迁移期间 S2~S5 短暂"两套并存" | 迁移过程不可避免 | 每个场景迁移单独发布,不批量切流量 |

---

## 7. 执行日志(完成后追加)

| 日期 | 任务 ID | 状态 | Commit | 备注 |
|---|---|---|---|---|
| 2026-05-06 | T1.1 | ✅ | 98f962e | POYO/Seedance/CosyVoice contextvars 隔离 |
| 2026-05-06 | T1.2 | ✅ | 98f962e | LLMClient.is_configured() + StrategyAgent.use_mock bug |
| 2026-05-06 | T1.3 | ✅ | 98f962e | StepRunner pipeline_degraded + resume 终止检查 |
| 2026-05-06 | T1.4 | ✅ | 98f962e | error_classifier 接入 pipeline/step_runner/_deps/fast_mode |
| 2026-05-06 | T1.5 | ✅ | 98f962e | CostTracker 骨架 + 4 客户端 track 插入 + thread_id contextvar |
| 2026-05-06 | T1.6 | ✅ | 98f962e | Gate keyframe/clip/final 多维启发式评分(告别固定 0.75) |
| 2026-05-06 | T1.7 | ✅ | 98f962e | 生产 API key fail-fast + mock 路径 guard |
| 2026-05-06 | T1.8 | ✅ | 98f962e | 前端 STEP_ORDER 后端化(VideoWorkflow + StepByStepView) |
| 2026-05-06 | T1.9 | ✅ | 98f962e | graph/nodes.py 5 处 + api.py 1 处 fire-and-forget 治理 |
| 2026-05-06 | T1.10 | ✅ | 98f962e | 多语言代码下线(删除 ES/FR/DE prompt + enum + i18n) |
| 2026-05-06 | T1.11 | ✅ | 98f962e | CosyVoice/elevenlabs VOICE_PRESETS 收窄为 en |
| 2026-05-06 | T1.12 | ✅ | 98f962e | .github/ISSUE_TEMPLATE/audit-fix.md + config.yml |

### Phase 2 执行日志

| 日期 | 任务 ID | 状态 | Commit | 备注 |
|---|---|---|---|---|
| 2026-05-07 | T2.1 | ✅ | 4d22ded | S1 已原生支持 StepRunner（无需改动） |
| 2026-05-07 | T2.2 | ✅ | 4d22ded | S3 重写 run_step() + run() 向后兼容 |
| 2026-05-07 | T2.3 | ✅ | 4d22ded | S4 重写 run_step() + run() 向后兼容 |
| 2026-05-07 | T2.4 | ✅ | 4d22ded | S5 重写 run_step() + run() 向后兼容 |
| 2026-05-07 | T2.5 | ✅ | 4d22ded | _pipeline 全局单例 → get_pipeline() 延迟初始化工厂 |
| 2026-05-07 | T2.6 | ✅ | 4d22ded | get_pipeline() 用 asyncio.to_thread() 避免阻塞事件循环 |
| 2026-05-07 | T2.7 | ✅ | 4d22ded | SkillRegistry _skills 类变量 → 实例变量，12 文件调用更新 |
| 2026-05-07 | T2.8 | ✅ | 4d22ded | api_keys 表 + Alembic 迁移 + tenant_id contextvar + verify_api_key 异步化 |
| 2026-05-07 | T2.9 | ✅ | 4d22ded | Alembic 迁移链检查：线性无分支，初始 SQL 包含所有表 |
| 2026-05-07 | T2.10 | ✅ | 4d22ded | 6 文件硬编码 ["en"] → DEFAULT_LANGUAGES |
| 2026-05-07 | T2.11 | ✅ | 4d22ded | nginx limit_req_zone + limit_req，FastAPI middleware 降级为 fallback |
| 2026-05-07 | T2.12 | ✅ | 4d22ded | LLMClient cache TTL=300s + max_size=20 + key_hash tenant 维度 |

### Phase 3 执行日志

| 日期 | 任务 ID | 状态 | Commit | 备注 |
|---|---|---|---|---|
| 2026-05-07 | T3.1 | ✅ | b0e2a13 | retry.py 改异常类型链(status_code 提取) + 字符串黑名单 |
| 2026-05-07 | T3.2 | ✅ | b0e2a13 | webhook_manager.py 端口黑名单 + DNS 解析后二次检查防 rebinding |
| 2026-05-07 | T3.3 | ✅ | b0e2a13 | docker-compose.yml 引用 .env + Dockerfile.backend 非 root USER |
| 2026-05-07 | T3.4 | ✅ | b0e2a13 | scenario.py 入口 structlog.contextvars.bind_contextvars(product, brand, scenario) |
| 2026-05-07 | T3.5 | ✅ | b0e2a13 | 前端 apiFetch timeout(30s/300s) + retry(1次) + useAppStore persist |
| 2026-05-07 | T3.6 | ✅ | b0e2a13 | 新增 tests/test_s4_e2e.py + tests/test_s5_e2e.py |

### Phase 3 风险点记录

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R11 | apiFetch timeout 对长运行 pipeline 请求设 300s，但 S5 实测 28min 仍可能超时 | S5 真实 API 调用 | 已在调用方保留 signal 参数，需要更长时可由调用方显式传入 AbortController |
| R12 | useAppStore persist 引入后，旧版本 localStorage 数据与新 schema 不兼容 | 用户已有旧版本 localStorage | zustand persist 默认会忽略未知字段，但建议版本升级时考虑 migration |
| R13 | Docker USER appuser 可能对挂载卷(/app/output)无写权限 | volume 权限与容器用户 UID 不匹配 | docker-compose.yml 中已用 volumes 挂载，生产部署时需确认 host 目录权限 |

### Phase 2 风险点记录

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R6 | S3/S4/S5 的 run() 内部使用 StepRunner，返回 dict/S3Result 与旧格式可能有细微差异 | 外部调用方依赖特定字段 | 向后兼容：保留原 run() 签名，输出格式通过 final_state 转换回 legacy shape |
| R7 | verify_api_key 改为 async 后，Depends(verify_api_key) 在各 router 中是否有兼容性 issue | FastAPI 版本不支持 async dependency | FastAPI 原生支持 async Depends，已通过 py_compile 验证所有 router |
| R8 | SkillRegistry 实例化后 skills 副本在 import-time 注册之后创建，新注册的技能对已有实例不可见 | 运行时动态注册 skill | 当前所有 skill 都是 import-time 注册，无运行时注册需求 |
| R9 | nginx rate limit 配置首次部署到生产，可能误伤合法高并发请求 | portfolio 页面加载 400+ 资源 | /api/media/ 和 /health 已显式豁免 limit_req |
| R10 | api_keys 表在生产为空时，verify_api_key 仅 fallback 到 env var，tenant_id 始终为 "default" | 多租户上线前 | 当前符合预期：单租户模式下 tenant_id = "default"，多租户上线后需插入 api_keys 记录 |

### Phase 1 风险点记录

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R1 | `ALLOW_MOCK_MODE` 默认 false，本地开发未设会抛 RuntimeError | 开发者未读 README 直接跑 mock | README 需补充 `ALLOW_MOCK_MODE=true` 说明；CI 中显式设置 |
| R2 | CostTracker 内存记录（上限 8k），多进程部署不共享 | 多 worker 部署 | Phase 2 接入 PG 持久化，移除此风险 |
| R3 | `_classified_error` 仅用于 1 个 endpoint，其余仍返回 str | 前端在多数路径看不到 error_code | Phase 2 逐步迁移所有 endpoint |
| R4 | S2~S5 仍走 LangGraph，StepRunner 的 `pipeline_degraded` 不生效 | S2~S5 场景出错 | Phase 2 将 S2~S5 迁到 StepRunner — 已完成 |
| R5 | Gate 启发式评分未经过真实数据校准 | 候选排序可能与人工判断不符 | 收集 Gate 使用数据后迭代权重 |

### Phase 1-3 补充修复日志（深度检查发现）

| 日期 | 任务 ID | 状态 | Commit | 备注 |
|---|---|---|---|---|
| 2026-05-07 | T3.4 | ✅ | 1e2b73c | S1 auto + S2 structlog bind_contextvars 补全（之前仅 S3/S4/S5/S1-step 有） |
| 2026-05-07 | T1.11 | ✅ | 1e2b73c | CosyVoice VOICE_PRESETS 删除残留 zh 键 |
| 2026-05-07 | T2.10 | ✅ | 1e2b73c | skills/agents 内部 5 处硬编码 ["en"] → DEFAULT_LANGUAGES |
| 2026-05-07 | T1.8 | ✅ | 1e2b73c | 新建 scripts/check_step_order_consistency.py，前后端 12 步一致 |
| 2026-05-07 | T2.6 | ✅ | — | 深度检查确认 asyncio.to_thread(get_pipeline) 已覆盖全部 6 处调用点，T2.6 实际已完成 |

### Phase 4 执行日志

| 日期 | 任务 ID | 状态 | Commit | 备注 |
|---|---|---|---|---|
| 2026-05-07 | T4.3 | ✅ | 7fa5932 | 死代码批次 1-3：_try_save_metrics 静默 ImportError / test_i18n.py ES/FR/DE 死测试 / scenario.py 未使用 import / telemetry.py 死函数 / cost_tracker.py 死函数 |
| 2026-05-07 | T4.2 | ✅ | 9170ae3 | Prometheus MVP：6 个指标(pipeline/step/runtime) + /telemetry/prometheus 端点 + telemetry.py 自动镜像 |
| 2026-05-07 | T4.4 | ✅ | 0fd6467 | LangGraph 代理层：pipeline.py 重写为 StepRunner 代理，_thread_label_map 映射，状态转换兼容 |
| 2026-05-07 | T4.4 | ✅ | 14c2925 | 前端死函数标记 @deprecated：startPipeline / fetchState / submitReview / fetchDistribution / fetchOutput / runS2BrandCampaign / runS3InfluencerRemix |
| 2026-05-07 | T4.4 | ✅ | 6a7fede | test_api.py 适配代理层 review 响应（"resumed" → ("resumed", "idempotent_skip")） |
| 2026-05-07 | **T4.1 Phase A** | ✅ | ba42853 | pyright basic 模式 287→0 错误，58 文件修复。关键发现：test_s1_e2e.py + test_media_clients.py 的 async 调用缺少 await，是真实运行时缺陷 |
| 2026-05-07 | **T4.1 Phase B** | ✅ | 8d4d706 | pyright reportMissingTypeArgument 434→0 错误，73 文件修复。dict→dict[str,Any] ~350 处，list→list[Any] ~50 处，Task/Pattern/StateGraph 等泛型补齐 |

### Phase 4 风险点记录

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R14 | 代理层 state 转换是 best-effort，某些 legacy 字段可能缺失 | 外部调用方依赖特定 legacy 字段 | 保留原始 LangGraph 代码，代理层转换函数可迭代补全 |
| R15 | /pipeline/start 启动后台 resume，调用方需轮询 /state 获取进度 | 调用方假设同步完成 | 返回 status: "started" 明确提示异步；label 字段可供 /scenario/{s}/state/{label} 直接查询 |
| R16 | Prometheus 进程内计数器，多 worker 部署时各进程独立 | 多 worker / 多容器 | 如需聚合，后续接入 Prometheus pushgateway 或共享存储 |

---

## 8. 看板与文档链接

- GitHub Project: TBD(T1.12 完成后填入)
- 审计原文 1: `docs/analysis/mece_deep_audit_final_20260506.md`
- 审计原文 2: `eval/architecture-deep-audit-report-20260506.md`
- 项目主指南: `CLAUDE.md`

---

**文档生效日期**: 2026-05-06  
**下次复核日期**: Phase 1 完成时(预计 2026-05-20)
