---
name: sprint-0-3-pr-review-and-deploy-plan
description: Sprint 0/1/2/3 累计 17 commits / +4726 行成果的 PR-grade 审查与部署计划。包含 Oracle 架构 review 发现的 4 项隐藏回归风险、3 阶段渐进部署、回滚触发器、上线后监控指标。
doc_type: workflow
module: ai-video
topic: sprint-rollout
status: stable
created: 2026-05-15
updated: 2026-05-15
owner: Sisyphus
source: ai
related:
  - file: ./2026-05-14-poyo-constrained-optimization-roadmap.md
    relation: implements
  - file: ./five-scenario-pipeline-risk-assessment-stable-20260513.md
    relation: derived-from
---

# Sprint 0-3 PR Review + 部署计划

> **范围**: 17 commits (5905958 → fd9b236), 36 files, +4726/-142 行。覆盖诊断 R-GATE-SCORE / R-VENDOR-LOCK / R-S5-DURA / R-S2-ARCH / R-S1/S2/S3-COMP / R-DEGRADE-L2 / R-COST-EXP / R-SCHEMA-VERSION / EU AI Act 9 个 P0/P1 风险。
>
> **审查机制**: 本文档由 Oracle (`bg_42d1915f`, 5m32s) 架构审查 + explore agent 部署面 mapping + 代码侧手工核查（grep / 直接读取关键文件）三方合证。

---

## 一、Sprint 0-3 整体地图

### Commit 序列

```
fd9b236 test(sprint3): coverage for P3-1, P3-3, P3-4, P3-5 (31 cases)
3089b6d feat(resilience,compliance): partial artifacts + C2PA signing (P3-3, P3-1)
2cbed0f feat(cost): Expert mode hard budget guard (P3-4)
0cbf960 feat(state): schema versioning + load-time mismatch warning (P3-5)
c136f21 feat(compliance): medical-claim lexicon + BrandCompliance auto-merge (P3-2)
bb5ea5b docs(scorer): document Decision D scope boundary for vision evaluation
ae934c5 feat(scorer): gpt-4o vision keyframe scoring + scenario-aware weights (P2-4/5)
7a5de3e test(s2): e2e regression suite for S2 Brand Campaign v2 (Sprint 2 P2-3)
132cb95 refactor(s2): route /scenario/s2 to v2 + deprecation shim (Sprint 2 P2-2)
b0e5133 feat(s2): independent S2 Brand Campaign pipeline (Sprint 2 P2-1)
7a6cc5f feat(s5,gate): integrate ModelRouter, VideoContinuityManager, abstraction guard (P1-4/5/6)
bfc901b feat(skill): VideoContinuityManager for cross-clip last-frame anchoring (P1-3)
9e9566a refactor(seedance): per-call model param + drop happy-horse-only comments (P1-2)
df1057f feat(router): scenario-aware ModelRouter (Sprint 1 P1-1)
a53f97e docs(roadmap): poyo-constrained Sprint 0-4 optimization plan + model matrix
c09ab46 feat(gate): model-aware score thresholds (Decision F, Sprint 0 S0-3)
3b3b57a feat(model): default POYO_VIDEO_MODEL happy-horse -> seedance-2 (Sprint 0 S0-1)
5905958 fix: address Codex review findings (baby-safety, scene_id, YAML)
```

### 新增模块（13 个文件）

| 路径 | 行数 | Sprint | 职责 |
|---|---|---|---|
| `src/pipeline/model_thresholds.py` | 103 | 0 | 25+ 模型 × 7 阈值，Decision F |
| `src/pipeline/model_router.py` | 126 | 1 | 5 场景 × (preferred/fallback/budget) chain |
| `src/pipeline/partial_artifacts.py` | 130 | 3 | degraded-state salvage summarizer |
| `src/pipeline/s2_brand_pipeline_v2.py` | 258 | 2 | 独立 S2 pipeline 类 |
| `src/skills/video_continuity_manager.py` | 188 | 1 | 跨片段 last-frame 锚定 skill |
| `src/tools/c2pa_signer.py` | 165 | 3 | EU AI Act C2PA 签名（env-gated） |
| `src/tools/medical_lexicon.py` | 257 | 3 | 244 EN+ZH 医疗禁用词 |
| `src/tools/cost_tracker.py`（+50） | 50 | 3 | BudgetExceededError + check_budget |
| 5 个新测试文件 | +887 | 0-3 | 196 case 覆盖 |

### 测试覆盖

- **Sprint 0-3 新增**: 196 cases, 全部 pass
- **仓库总测试**: 1049 collected
- **新代码覆盖率**: 196 / 1049 = 18.7% of total test suite
- **0 LSP errors** 跨所有 Sprint 0-3 新建 / 修改文件
- **ruff lint**: 0 violations on 8 new src/ files

---

## 二、Oracle 审查发现的 4 项隐藏回归风险（已代码核证）

> 这 4 项是 Oracle (5m32s) 提出的、我用 grep + 文件读取**逐项核证为真**的回归风险。**部署计划必须按这 4 项设计 phase + 回滚触发器**，不能直接全量上线。

### 🔴 风险 #1: PG 持久化丢字段（最高优先级）

**Oracle 论断**: PG-primary load 后 `schema_version`、`pipeline_degraded`、`degraded_reason`、`trace_id`、`structured_errors` 字段全部丢失。

**核证**: `grep "schema_version\|pipeline_degraded\|degraded_reason\|trace_id\|structured_errors" src/storage/repository.py` 返回 **空** — PG schema 不持久化这些字段。`state_manager.load()` 的 PG 路径只读 `scenario/config/steps/current_step/mode/errors/media_synthesis_errors/gates`。

**影响范围**:
- **degraded 状态 round-trip 后丢失** — `partial_artifacts.summarize_partial_artifacts()` 对显式 degraded 的检测失效（只能靠 implicit empty-tuple sentinel）
- **schema_version 告警形同虚设** — load 后 schema_version=0（缺失），永远触发"mismatch"警告
- **trace_id 丢失** — 跨 step 调试链断裂
- **structured_errors 丢失** — Sprint 0 GAP-20 的结构化错误链断了

**何时引爆**: 生产是 PG-primary（`is_pg_available()=True`）+ pipeline 跨多步执行 + 中间步骤失败。

### 🔴 风险 #2: BudgetExceededError 未被降级链捕获

**Oracle 论断**: `check_budget()` 在 `try:` **之前**，`BudgetExceededError` 不会进入现有 except 降级处理。

**核证**: `step_runner.py:47-48` 显示 `check_budget(...)` 在 line 47，`try:` 在 line 48。Exception 会冒泡到 `step_runner.resume()` 调用方（router 或 background task），返回 500 或卡在 pending 状态。

**影响范围**:
- Expert mode 用户超预算 → HTTP 500，前端看到模糊错误
- `pipeline_degraded` 没被打上
- `degraded_reason` 没写
- Step 状态已被标 `pending`/`started`，**无收尾**
- 看起来像"卡住"而非"超预算停止"

**何时引爆**: 任何 Expert mode + 跨多个 Gate 重新生成的运行。

### 🟡 风险 #3: 医疗词典 severity 收敛到 BLOCKED

**Oracle 论断**: `MEDICAL_FLAGGED_CLAIMS`（48 EN 软警告词）+ `MEDICAL_COMPETITOR_CLAIMS`（13 EN 比较级词）被 BrandCompliance 一律按 `severity=high` 处理，全部触发 BLOCKED。

**核证**: `brand_compliance.py:109-110` 硬编码 `severity: "high"` for every `forbidden_content` match。`merge_medical_lexicon` 把 3 tier 全部塞进同一个 `forbidden_content` list，下游无法区分。

**影响范围（具体 benign 文案被误封）**:
- `"natural lighting"` (S5 prompt 常用) → BLOCKED（"natural" in FLAGGED）
- `"natural usage scene"` (skill fallback prompt 默认值) → BLOCKED
- `"organic cotton packaging"` → BLOCKED（"organic" in FLAGGED）
- `"doctor recommended"` (营销常见) → BLOCKED
- `"lab tested"` → BLOCKED

**何时引爆**: 任何包含上述 FLAGGED 词的 script 进入 compliance step。

### 🟡 风险 #4: ModelRouter 未完全收敛

**Oracle 论断**: 只有 S2、S5、gate_manager 走 `select_model()`。S1 / S3 / S4 / fast_mode 还在用 env 默认 `POYO_VIDEO_MODEL`。

**核证**: `grep select_model src/` 显示 3 个调用点（gate_manager:447/462/815/824, s2_v2:105, s5:449）。`fast_mode.py:77` 仍直接读 `POYO_VIDEO_MODEL`。S1/S3/S4 pipeline 没有 ModelRouter import。

**影响范围**:
- 生产 `.env.prod=happy-horse` + ModelRouter 部分启用 = **混合状态**：
  - S2 → kling-3-0/pro ✅
  - S5 → seedance-2 ✅
  - S1/S3/S4 → happy-horse（8s 限制）⚠️
  - Fast mode → happy-horse ⚠️
- 这本身不是 bug（向后兼容），但**用户预期可能不一致**

**何时引爆**: 部署后，用户对 S1/S3/S4 期望也升级到 seedance-2，发现没升级。

---

## 三、部署面 mapping（来自 explore agent）

### 生产 env (`deploy/lighthouse/.env.prod`)

| Key | 当前值 | Sprint 0-3 期望 |
|---|---|---|
| `POYO_VIDEO_MODEL` | `happy-horse` (Sprint 0 已 rollback) | 阶段性切换 → `seedance-2`（Phase 2） |
| `C2PA_ENABLED` | **缺失** | 留空保持 disabled（默认） |
| `C2PA_CERT_PATH` | **缺失** | EU launch 前补 |
| `C2PA_KEY_PATH` | **缺失** | EU launch 前补 |
| `C2PA_TSA_URL` | **缺失** | 可选 |

### Dockerfile.backend

- ✅ `ffmpeg` 已安装（apt-get line 9-11） — Sprint 1 VideoContinuityManager + Sprint 3 C2PA 都需要
- ❌ `c2pa-python` 未安装 — Sprint 3 P3-1 prod activation 前需加入 requirements.txt
- ✅ 其他 Sprint 0-3 模块**无新二进制依赖**

### requirements.txt

**当前 24 个包** — Sprint 0-3 没引入新依赖（c2pa-python 当前是 lazy import，缺失会降级到 no-op）。如果 EU 启用 C2PA，需 `pip install c2pa-python==0.32.x`。

### .env.example

- 列出 35 个 key
- **未文档化 C2PA_\* 4 个 key** — 应在 Phase 0 之前补到 `.env.example` 提示团队

---

## 四、3 阶段部署计划

> 设计原则：**每个 phase 都有明确 prereq + smoke test + rollback trigger**。任一回滚触发器命中即回到上一阶段（最差回 Sprint 2 tag）。

### Phase 0 — Sprint 0-3 代码上线，保守配置（内部 canary，1-3 天）

**范围**:
- 代码：全部 17 commits 部署到 lighthouse
- env：**保持 `POYO_VIDEO_MODEL=happy-horse`**（不动），**不设 C2PA_\***（默认 disabled）
- 不对外开放 Expert mode

**Prereq**（必做）:

1. 把 4 个 C2PA_\* key 占位加到 `.env.example`（即使为空）
2. 验证生产 PG 状态：`is_pg_available()` 返回 True / False?
   - 若 True → 风险 #1 引爆概率高，必须做 PG round-trip smoke
   - 若 False（FS-only）→ 风险 #1 不引爆，跳过
3. 部署前在测试环境跑 3 条 smoke

**Smoke test（3 条，必做）**:

```
1) S2 auto 一单：
   curl POST /scenario/s2 with minimal brand_package
   断言 result.model_id == "kling-3-0/pro"
   断言 result.scenario == "brand_campaign"

2) PG round-trip (若 PG 启用):
   init_state -> save -> load (强制走 PG)
   断言 reloaded.get("schema_version") == 1
   断言 reloaded.get("trace_id") 仍存在
   ⚠️ 当前会失败 — 风险 #1 — 必须在 Phase 0 修

3) Expert 预算超限注入:
   set_thread_id("test"); track("poyo_video", units=20)  # $6
   POST /scenario/s5 ?mode=expert
   断言返回的不是 HTTP 500
   断言 result.errors 包含 "budget_exceeded"
   ⚠️ 当前会返回 500 — 风险 #2 — 必须在 Phase 0 修
```

**Rollback trigger（任一命中回 Sprint 2）**:

- ❌ Smoke #2 失败（PG round-trip 字段丢失）
- ❌ Smoke #3 返回 500 而非可解释错误
- ❌ 生产 S1/S3/S4 默认行为有任何回归（看 24h 日志 `errors` 比例）

**Phase 0 必修项（在 prod 切换前）**:

| 修复 | 文件 | 工作量 |
|---|---|---|
| 风险 #1：PG schema 加 schema_version / pipeline_degraded / degraded_reason 列 + alembic migration + repository.py 读写支持 | `src/storage/repository.py` + `src/storage/migrations/` + alembic | 1 天 |
| 风险 #2：把 `check_budget()` 移到 try 内部，让 `BudgetExceededError` 走 degraded 链 | `src/pipeline/step_runner.py` 行 47 | 30 分钟 |
| 风险 #3：BrandCompliance 改读 `forbidden_content_severity_map`，FLAGGED 词标 low、COMPETITOR 标 low、BANNED 标 high | `src/skills/brand_compliance.py` + `medical_lexicon.py` 新增 severity-aware export | 2-3 小时 |
| 风险 #4：暂不做（架构决策，留 Phase 2） | — | — |

### Phase 1 — 受控开放 S2 / S5 新路由（Phase 0 24h 后无异常，3-7 天）

**范围**:
- 风险 #1/#2/#3 已修复
- 仍保持 `POYO_VIDEO_MODEL=happy-horse`（S1/S3/S4 用旧模型）
- S2/S5 通过 ModelRouter 用 kling-3-0/pro 和 seedance-2
- Expert mode 仍限内部用户

**Prereq**:
- Phase 0 全部 smoke pass
- 监控 24h 无 stuck run / 无 heuristic scoring 比例飙升

**Smoke**:
- S2 + S5 各跑 1 单完整流程
- 检查 `final_video_path` 非空 + Gate 推荐符合预期

**Rollback trigger**:
- ❌ `final_video_path=""` 但 `clip_paths` 非空 比例 > 5%
- ❌ medical lexicon BLOCKED 比例 > 10%（误封）
- ❌ Phase 0 修复的任一回归

### Phase 2 — POYO_VIDEO_MODEL 切换 + ModelRouter 收敛 + C2PA 启用（EU 8/2 前，1-2 周）

**范围**:
- `POYO_VIDEO_MODEL=seedance-2`（默认路径升级）
- S1/S3/S4/fast_mode 也通过 ModelRouter（风险 #4 修复）
- C2PA 启用（生产 cert 准备好后）

**Prereq**:
- 风险 #4 修复：S1/S3/S4 pipeline + fast_mode 改走 ModelRouter
- C2PA cert：从 CAI-trusted issuer 获取 X.509 cert
- `pip install c2pa-python==0.32.x` 加入 requirements.txt
- `.env.prod` 加 `C2PA_ENABLED=1` + `C2PA_CERT_PATH` + `C2PA_KEY_PATH`
- 至少 1 条端到端验证：signed mp4 通过 Adobe CAI Content Credentials inspector

**Smoke**:
- 全 5 场景跑 1 单
- 1 条 C2PA signed video 发布到测试 TikTok 沙盒账号 + Adobe CAI inspector 验证

**Rollback trigger**:
- ❌ C2PA 签名 mp4 无法被平台上传/播放
- ❌ 任一场景 model_id 不符合预期
- ❌ S1/S3/S4 因 ModelRouter 收敛出现新错误

---

## 五、上线后监控指标（3 个）

按 Oracle 推荐，部署后实时盯：

| 指标 | 条件 | 告警阈值 | 抓什么风险 |
|---|---|---|---|
| **空 final_video 比例** | `final_video_path == ""` AND `clip_paths` 或 `audio_paths` 非空 | > 5% | silent assemble failure / partial_artifacts 误判 / 风险 #1 引爆 |
| **heuristic scoring 比例** | gate score 中 `heuristic == true`，特别是 keyframe gate | > 30% baseline，飙升即告警 | gpt-4o vision 失效后的静默退化 |
| **stuck run 比例** | `current_step` 长时间不变 / step status=pending 超阈值 | > 2% | 预算异常 (#2) / 状态丢失 (#1) / 后台中断 |

**埋点位置建议**:
- `partial_artifacts.summarize_partial_artifacts()` 出口 → 加 `pipeline_metrics.record_degraded()`
- `_score_keyframe_candidate()` 出口 → `breakdown["heuristic"]=True` 时发 telemetry
- `state_manager.load()` 出口 → 状态字段缺失时发 telemetry

---

## 六、回滚路径

**回到 Sprint 2 tag**（最差情况）:

```bash
# 1. 在 lighthouse 上回滚 docker image
ssh -i ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
git checkout bb5ea5b  # 最后一个 Sprint 2 commit
docker compose down
docker compose up -d --build

# 2. 数据库回滚（如果 Phase 0 修复 #1 已经跑了 alembic）
alembic downgrade -1

# 3. 通知团队 + 抓 24h 日志做事后分析
```

**回到 Sprint 0/1**: 不推荐 — Sprint 2 已经修了 codex review 发现的 baby-safety + scene_id + YAML 三个 P2 bug，回到 Sprint 0/1 会重新引入。

---

## 七、推荐时间线

| 时间 | 行动 |
|---|---|
| **Day 0 (今天)** | Phase 0 必修 4 项（PG schema + budget try-catch + severity map + .env.example） |
| **Day 1** | Phase 0 测试环境 smoke 3 条全 pass，准备部署到 lighthouse canary |
| **Day 2-3** | Phase 0 lighthouse 部署 + 24h 监控 |
| **Day 4-10** | Phase 1 开放 S2/S5 流量 + 7 天监控 |
| **Day 10-15** | Phase 2 C2PA cert 准备 + ModelRouter 收敛 + 全量切换 |
| **EU AI Act deadline (2026-08-02)** | Phase 2 必须完成 |

---

## 八、决策项需用户确认

1. **是否做 Phase 0 4 项必修**（含 PG schema migration）？还是接受当前风险直接上 Phase 1？
   - 推荐：做。PG 字段丢失是真实生产 bug（Oracle 已核证 + grep 确认）。
2. **C2PA 生产 cert 是否已对接 CAI**？
   - 如未启动 → 立即启动（X.509 cert 流程 1-2 周）。
3. **ModelRouter 收敛 (S1/S3/S4) 排哪个 sprint**？
   - 当前 roadmap 未排，建议作为 Phase 2 prereq 或单独 0.5 sprint。
4. **回滚演练**是否在 Phase 0 之前做一次？
   - 推荐：是。回滚未演练 = 回滚不可信。

---

*文档版本 v1.0 | 基于 Oracle bg_42d1915f 5m32s 审查 + explore bg_68d8ca47 1m35s 部署面 mapping + 代码侧 grep 核证 | 下一次更新: Phase 0 完工后*
