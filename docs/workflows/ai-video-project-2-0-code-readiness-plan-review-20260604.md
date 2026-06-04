---
title: AI Video Project 2.0 代码前自证与实施计划
doc_type: workflow
module: ai-video
topic: project-2-0-code-readiness-plan
status: review
created: 2026-06-04
updated: 2026-06-04
owner: self
source: human+ai
related:
  - file: ../research/ai-video-commercial-technology-research-review-20260603.md
    relation: synthesizes
  - file: ../research/ai-video-longform-production-research-audit-review-20260603.md
    relation: constrains
  - file: ../research/aihot-image-video-product-technology-research-review-20260604.md
    relation: constrains
  - file: ../architecture/ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: implements
  - file: ../architecture/brand-asset-token-contract-review-20260603.md
    relation: implements
  - file: ../architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md
    relation: implements
  - file: ../architecture/quality-contract-brand-rights-audit-review-20260603.md
    relation: implements
  - file: ./ai-video-commercial-toolbox-phase0-backlog-review-20260603.md
    relation: operationalizes
  - file: ./brand-data-asset-directory-intake-review-20260603.md
    relation: waits-for
  - file: ./ai-video-project-2-0-cross-analysis-plan-review-20260603.md
    relation: refines
---

# AI Video Project 2.0 代码前自证与实施计划

> 状态边界：本文最初是修改代码前的执行自证和实施计划。2026-06-04 已完成 C1-C5 首轮无 token、hermetic、contract-first 代码化接入，并完成 C6 S1/S2/S5 只读注入 blueprint、state-shape helper、runtime config pass-through 与 StepRunner per-step visibility；它不授权真实 provider 调用，不改变生产默认模型，不生成 approved brand token，不声明长视频商业交付已可用。

## 1. 自证结论

决策问题：

> 当前 2.0 方案是否已经足够清楚，可以进入第一轮代码实现？

Gate 结果：**allowed-with-label**。

允许的标签：

- `方案闭环已完成`
- `代码前 readiness 已完成`
- `可进入无 token contract-first implementation`
- `C1-C5 首轮 contract implementation 已完成`
- `C6 只读 scenario injection blueprint、state-shape helper、runtime config pass-through 与 per-step visibility 已完成`

禁止的标签：

- `2.0 已实现`
- `长视频商业交付已覆盖`
- `provider 已生产验证`
- `品牌资产已 approved`
- `真实生成 smoke 已通过`

证据等级：

| 结论 | 最高支持等级 | 说明 |
|---|---|---|
| 外部技术趋势与产品模式已调研 | `L1-public-or-runtime` | 来自公开产品资料、AIHOT 聚合信号、附件方法和本地只读审计 |
| 2.0 文档合约闭环 | `L2-fixture-or-dry-run` | 文档结构、frontmatter、引用和无 token 约束已通过静态检查 |
| C1-C5 首轮代码化 + C6 blueprint | `L2-fixture-or-dry-run` | 新增 contracts、offline gate、GateDecision、RepairPlan、provider signal registry、provider profile registry、mock compiler、mock job ledger、read-only scenario injection planner、state-shape helper、runtime config pass-through、StepRunner per-step visibility；58 个 targeted hermetic tests 通过 |
| 当前代码已有短/中短视频基础 | `L1-public-or-runtime` | 来自仓库只读审计，未在本轮重跑全量测试 |
| 真实 provider 能力 | `L0-unverified` 到 `L1-public-or-runtime` | AIHOT 条目只算线索，官方文档和供应商后台仍需后续刷新 |
| 品牌数据资产 token | `L1-public-or-runtime` | 用户已提供 `/Users/pray/project/Brand_agent/`，Momcozy 已完成本地候选接入；仍未生成 approved token |
| 商业发布能力 | `L0-unverified` | 未授权真实生成、上传、发布或生产 smoke |

## 2. 迭代目标对齐

| 用户目标 | 本轮自证结果 | 下一步实现口径 |
|---|---|---|
| 审计 S1-S5，不改场景 | 已完成。S1-S5 保持业务语义不变，新增能力通过 contract、toolbox、gate 注入 | 先做模型和离线 gate，不重写场景 pipeline |
| 提出完整技术改良方案和技巧 | 已完成。形成 `BrandAssetToken`、`Creative/LongformProductionContract`、`ProviderPromptCompiler`、`ProductionJobLedger`、`QualityContract` | 代码实现按合约优先，不从 provider API 开始 |
| 增量补充 AI 图片、演示视频、故事版、克隆语音、音乐等工具箱 | 已完成。工具箱被归入 Design/Image、Storyboard、Video、Audio、Presenter、PostProduction、Audit | 工具箱必须共享 job ledger 和 gate，不能做孤立功能页 |
| 制定品牌资产 token 计划 | 已完成。品牌目录接入 SOP、token 架构和 Momcozy candidate intake 已形成 | 下一步从 candidate ledger 进入 contract-first implementation，不跳过 rights gate |
| 深挖长视频难点与产品层方案 | 已完成。长视频结论被降级为“约束与审计底座已覆盖，商业交付未实现” | 先补 `SceneLedger`、`TranscriptTimeline`、`TimelineManifest`、`ReviewCheckpoint` |
| 采集 AIHOT 图像/视频市场信号并交叉论证 | 已完成。新增 `Market Signal Intelligence Layer` | AIHOT 条目只进 `ProviderSignalLedger`，不直接改默认 provider |

## 3. 2.0 最终目标形态

2.0 不是“接入更多视频模型”，而是：

```text
AI 商业视频生产系统
  = Market Signal Intelligence Layer
  + S1-S5 稳定场景
  + Brand Data Directory Intake
  + Brand Asset Token
  + Creative / Longform Production Contract
  + Design / Image / Storyboard / Video / Audio / Presenter / PostProduction / Audit Toolbox
  + Provider Prompt Compiler
  + Production Job Ledger
  + Quality / Brand / Rights / Platform / AV Sync Gate
  + Campaign Asset Pack
  + Review UI and Operations Console
```

核心不变量：

- S1-S5 的场景语义不变。
- 所有 provider 都是 adapter，不是业务主线。
- 所有品牌资产先 token 化，不直接投喂生成模型。
- 所有真实生成和后期任务都写入 job ledger。
- 所有可交付判断都经过 quality、brand、rights、platform、AV sync 分层 gate。
- 任何市场信号先进入 evidence level，不直接进入生产默认值。

## 4. 目标架构

```text
Layer -1: Market Signal Intelligence
  ProviderSignalLedger
  CapabilitySnapshot
  TechniquePatternRegistry
  ExperimentBacklog

Layer 0: Brand Data Directory Intake
  readonly inventory
  source classification
  rights / PII / children / music / claim precheck

Layer 1: Brand Asset Tokenization
  BrandAssetSource
  BrandAssetToken
  BrandConstraintBundle
  BrandTokenReview

Layer 2: Creative and Longform Contract
  StrategyBrief
  ScriptSchema
  StoryboardShotSchema
  LongformProductionContract
  SceneLedger
  ShotLedger
  TranscriptTimeline
  TimelineManifest

Layer 3: Toolbox Adapter
  DesignAssetToolbox
  ImageToolbox
  StoryboardToolbox
  VideoToolbox
  AudioToolbox
  PresenterDemoToolbox
  PostProductionToolbox
  AuditToolbox

Layer 4: Provider Compiler and Production Job Ledger
  ProviderCapability
  PromptCompileInput
  PromptCompileResult
  MediaJobSpec
  MediaJobRecord
  ArtifactManifest

Layer 5: Audit and Gate
  QualityContract
  AuditEvidenceBundle
  GateDecision
  RepairPlan

Layer 6: Scenario Orchestration and UI
  S1 Product Direct
  S2 Brand Campaign
  S3 Influencer Remix
  S4 Live Shoot
  S5 Brand VLOG
  Review / Ledger / Gate viewer
```

## 5. 代码实现总原则

第一轮代码只做 contract-first implementation。

禁止从以下事项开始：

- 真实调用 POYO、Runway、Veo、Sora、Kling、HeyGen、ElevenLabs、FAL。
- 修改生产默认 provider。
- 新增数据库 migration。
- 直接接入品牌目录为 approved token。
- 直接改 S1-S5 主流程为大一统 pipeline。
- 用 AIHOT 条目更新 production capability。

允许从以下事项开始：

- Pydantic V2 合约模型。
- 无 token fixture。
- 离线 gate evaluator。
- provider prompt compiler mock。
- job ledger prepared / blocked / failed 记录。
- S1-S5 只读注入 diff。
- 静态和 hermetic 测试。

## 6. 首轮代码包规划

建议第一轮代码集中在正式模型、离线 fixture 和测试，不碰真实 provider。

| 包 | 建议位置 | 内容 | 验收 |
|---|---|---|---|
| Commercial contracts | `src/models/commercial_contracts.py` | `ProviderSignalLedger`、`BrandAssetToken`、`LongformProductionContract`、`MediaJobSpec`、`QualityContract` 等 Pydantic model | `tests/test_commercial_contracts.py` 覆盖序列化、状态枚举、hard/soft 规则 |
| Fixture data | `tests/fixtures/commercial_video/` | B-001 到 B-017 的无 token 输入样例 | fixture 不含真实 secret、真实品牌隐私素材 |
| Offline evaluators | `src/quality/commercial_gate.py` | blocking/advisory gate、`GateDecision`、`RepairPlan`、evidence level、publish_allowed fail-closed | `tests/test_commercial_gate.py` 覆盖 rights fail、claim fail、children fail、safe-zone advisory、repair action |
| Prompt compiler mock | `src/pipeline/provider_prompt_compiler.py` | 从 `StoryboardShotSchema + BrandConstraintBundle + ProviderCapability` 编译 mock result | hard token 不丢失，unknown capability 不当作 true |
| Job ledger mock | `src/pipeline/production_job_ledger.py` | prepared、blocked、failed、succeeded 的内存记录结构 | job succeeded 不等于 delivery accepted |
| Scenario injection planner | `src/pipeline/scenario_injection_plan.py` | 只读计算 S1-S5 哪些 step 应接收哪些 bundle | 不执行真实 step，不触发 provider |
| Provider signal registry | `src/pipeline/provider_signal_registry.py` | 将 AIHOT、official_doc、supplier_backend 等信号转为 capability snapshot、technique pattern、experiment backlog | AIHOT 只进入 experiment backlog，不进入 production default |
| Provider profile registry | `src/pipeline/provider_profiles.py` | Seedance/PoYo、Kling、Runway、Veo、Sora、Wan mock profile | prompt compiler 记录 profile_id，unknown provider 退回 generic profile 并给 warning |

如果实现中发现 `commercial_contracts.py` 过大，再拆为 `brand_tokens.py`、`production_contracts.py`、`provider_jobs.py`、`quality_contracts.py`。第一轮不预先拆太细，避免制造无用结构。

## 7. 分阶段实施计划

### C0 代码前冻结

目标：

- 十一份 review 文档和入口引用一致。
- 明确所有 unsupported claims。
- 明确第一轮代码只做 hermetic contracts。

放行：

- `git diff --check` 通过。
- 新增 Markdown 有 frontmatter。
- 文档不声明代码已实现。

### C1 合约模型与 fixture

2026-06-04 状态更新：首轮 C1 已完成。实现位置包括 `src/models/commercial_contracts.py`、`tests/fixtures/commercial_video/` 和 `tests/test_commercial_contracts.py`。

目标：

- 实现 2.0 的最小 Pydantic 合约。
- 建立 B-001 到 B-017 的无 token fixture。

优先对象：

- `ProviderSignalLedger`
- `BrandAssetSource`
- `BrandAssetToken`
- `BrandConstraintBundle`
- `StoryboardShotSchema`
- `LongformProductionContract`
- `TranscriptTimeline`
- `MediaJobSpec`
- `MediaJobRecord`
- `QualityContract`
- `AuditEvidenceBundle`

放行：

- 合约模型单测通过。
- unknown capability 不被当作支持。
- rights unknown 不得进入 approved bundle。

### C2 品牌目录只读接入

2026-06-04 状态更新：Momcozy 首次 candidate intake 已完成，结果写入 `drafts/analysis/brand-momcozy/` 与 `tmp/outputs/brand-momcozy-*`。该结果只支持 `candidate/review`，不支持 `approved`。

2026-06-04 代码化更新：Momcozy candidate ledger 已作为 hermetic fixture 进入 `tests/fixtures/commercial_video/momcozy_candidate_ledger.json`。代码只验证 candidate 状态和 fail-closed 规则，不重新读取外部 `/Users/pray/project/Brand_agent/`，不复制新资产。

触发：

- 用户提供品牌资产目录。

目标：

- 只读盘点。
- 生成 candidate source、candidate token 和风险预检报告。
- 不复制到正式 `assets/` 或 `web/public/`。
- 不移动、不上传、不转码外部源资产。
- 只允许候选区复制、manifest 和风险报告。

放行：

- unknown license 只能是 candidate。
- 含可识别儿童、未知声音、第三方音乐或第三方品牌的资产被标记。
- 不产生 approved token。

### C3 Market Signal Intelligence

2026-06-04 状态更新：首轮 C3 已完成。实现位置包括 `ProviderSignalLedger` 扩展、`src/pipeline/provider_signal_registry.py`、`tests/fixtures/commercial_video/provider_market_signals.json` 和 `tests/test_provider_signal_registry.py`。

目标：

- 将 AIHOT、官方文档、供应商后台、benchmark 证据分级。
- 建立 provider capability refresh 的输入格式。

放行：

- AIHOT 条目默认 `evidence_level=aihot_signal`。
- 未达到 `official_doc` 的 capability 不能进入 production default。
- 热点模型只能进入 experiment backlog。

### C4 Provider Prompt Compiler 与 Production Job Ledger

2026-06-04 状态更新：首轮 C4 已完成。实现位置包括 `src/pipeline/provider_profiles.py`、`src/pipeline/provider_prompt_compiler.py`、`src/pipeline/production_job_ledger.py`、`tests/test_provider_profiles.py`、`tests/test_provider_prompt_compiler.py` 和 `tests/test_production_job_ledger.py`。

目标：

- mock 编译 Seedance/PoYo、Kling、Runway、Veo、Sora、Wan 风格 prompt。
- 生成 prepared / blocked / failed job record。

放行：

- hard token 不丢失。
- prompt hash、provider profile、reference asset、capability warning 可追踪。
- job succeeded 与 delivery accepted 分离。

### C5 Quality / Brand / Rights Gate

2026-06-04 状态更新：首轮 C5 已完成。实现位置包括 `GateDecision`、`RepairPlan`、`src/quality/commercial_gate.py`、`tests/fixtures/commercial_video/quality_gate_cases.json` 和 `tests/test_commercial_gate.py`。

目标：

- 实现离线 `QualityContract` evaluator。
- 输出 `GateDecision` 与 `RepairPlan`。

放行：

- S1 claim 无证据 blocked。
- S3 source fingerprint 缺失 blocked。
- S4 footage rights 缺失 blocked。
- S5 children direct reference blocked。
- safe-zone 低分按规则 advisory 或 blocked，不被默默忽略。

### C6 S1/S2/S5 首批注入

2026-06-04 状态更新：首轮 C6 只读 blueprint 已完成。实现位置是 `src/pipeline/scenario_injection_plan.py` 和 `tests/test_scenario_injection_plan.py`；它只返回 bundle/toolbox/contract/gate refs，不修改 `s1_product_pipeline.py`、`s2_brand_pipeline.py` 或 `s5_brand_vlog_pipeline.py` 执行路径。

2026-06-04 审计修正：C6 接入前审计发现早期 blueprint 使用了规划命名 `script`、`storyboard`、`image_prompts`、`caption`，与 runtime `SCENARIO_STEP_ORDERS` 不一致。已改为从 `src/pipeline/scenario_config.py` 读取真实 step order，并补充兼容性测试，防止只读注入计划与运行时步骤再次漂移。

2026-06-04 state-shape 修正：C6 blueprint 已可通过 `build_injection_config_patch()` / `with_injection_config()` 写成 JSON-safe config patch，并可通过 `get_step_injection_from_state()` 从持久化 state 读取单步注入信息。该 helper 只提供读取能力，不让 StepRunner 自动执行注入。

2026-06-04 runtime config pass-through 修正：`S1ProductDirectPipeline.run()`、`S2BrandCampaignPipeline.run()`、`S5BrandVlogPipeline.run()` 已接受可选 `commercial_injection_plan`，并通过 `with_optional_injection_config()` fail-closed 写入 StepRunner config。测试使用 fake runner 验证 config 透传，不执行真实 step，不调用 provider。

2026-06-04 per-step visibility 修正：`StepRunner._execute_step()` 在真正执行 step 前调用 `attach_step_injection_visibility()`，把当前 step 的只读注入元数据暴露到 `state["current_step_injection"]` 和 `state["steps"][step]["commercial_injection"]`。该元数据只供读取和审计，不改变 step output、prompt、provider 或 gate 逻辑。

目标：

- 先接风险最低、业务价值最高的三条线。

顺序：

1. S1：`ProductTruthBundle`、`DesignAssetToolbox`、`ImageToolbox`、product claim gate。
2. S2：`BrandConstraintBundle`、`StoryboardToolbox`、`CampaignAssetPack`、brand audit。
3. S5：`PersonaSceneBundle`、`AudioCueLedger`、children safety gate。

放行：

- 不改变场景定义。
- 每个注入点有 source token、contract ref、audit result。
- UI/API 不允许 publish blocking fail 的结果。

### C7 S3/S4 与长视频生产对象

目标：

- S3/S4 进入源视频理解、长素材整理和后期剪辑路径。

对象：

- `SourceIngest`
- `TranscriptTimeline`
- `SceneLedger`
- `EditDecisionList`
- `CutdownPlan`
- `ReframeJob`
- `CaptionSafeZoneAudit`

放行：

- 源视频无 rights evidence blocked。
- 90s 以上输出缺 timeline blocked。
- 单镜头 300s 结构 blocked。
- cutdown 输出保留 source transformation evidence。

### C8 产品控制面

目标：

- 把 2.0 能力做成可操作产品，不藏在脚本里。

界面：

- Brand Asset Intake Review。
- Token Bundle Builder。
- Creative Contract Editor。
- Media / Production Job Ledger Viewer。
- Quality Audit Report。
- Scenario Injection Diff。
- Campaign Asset Pack Export。

放行：

- 用户能看到每个视频引用了哪些 token。
- 用户能看到 provider、prompt hash、job status、artifact、gate decision。
- 用户能区分 preview、review、approved、blocked。

### C9 真实 token 小样本 benchmark

触发：

- C1-C8 的 no-token gate 通过。
- 用户明确充值并设置真实 smoke 开关。

放行：

- 每个真实生成写 job ledger。
- 每个 artifact 写 manifest。
- 每个结果进入 audit evidence bundle。
- benchmark 只作为技术验证，不自动升级为生产质量结论。

## 8. S1-S5 最终注入计划

| 场景 | 首批注入 | 延后注入 | hard gate |
|---|---|---|---|
| S1 Product Direct | Product truth、DesignAssetToolbox、keyframe reference、claim evidence | platform PDP variants、infographic | claim substantiation、product visual truth、reference rights |
| S2 Brand Campaign | BrandConstraintBundle、StoryboardToolbox、CampaignAssetPack | campaign motif library、performance signal token | brand hard token、claim evidence、platform compliance |
| S3 Influencer Remix | SourceFingerprint、TranscriptTimeline、RightsAudit | DubbingPlan、voice isolation、remix style scorer | source rights、likeness、third-party music、remix boundary |
| S4 Live Shoot | FootageSource、CutdownPlan、ReframeJob、CaptionSafeZoneAudit | FoleyJob、multi-platform batch export | footage rights、visible PII、voice/music rights |
| S5 Brand VLOG | PersonaSceneBundle、AudioCueLedger、ContinuityBible、children safety | GestureCameraPlan、longform vlog timeline | children safety、voice rights、medicalized claim、persona misuse |

## 9. 修改代码前必须保留的硬约束

- 只要没有用户明确授权，不触发真实生成、上传、发布。
- 只要品牌资产未完成人工授权与 rights review，不生成 approved token。
- 只要 provider capability 未官方复核，不进入 production default。
- 只要 job ledger 缺失，不允许真实 token benchmark。
- 只要 rights / brand / platform / AV sync 任一 blocking fail，不允许 publish。
- 只要 longform 缺 timeline / scene / shot / review marker，不允许宣称长视频交付闭环。
- 只要测试不通过，不进入下一阶段。

## 10. 首轮验收命令

当前 C1-C5 + C6 blueprint 已验证命令：

```bash
.venv/bin/python -m pytest tests/test_provider_signal_registry.py tests/test_provider_profiles.py tests/test_provider_prompt_compiler.py tests/test_production_job_ledger.py tests/test_commercial_contracts.py tests/test_commercial_gate.py tests/test_scenario_injection_plan.py
```

```bash
.venv/bin/python -m ruff check src/models/commercial_contracts.py src/pipeline/provider_signal_registry.py src/pipeline/provider_profiles.py src/pipeline/provider_prompt_compiler.py src/pipeline/production_job_ledger.py src/quality/commercial_gate.py src/pipeline/scenario_injection_plan.py tests/test_provider_signal_registry.py tests/test_provider_profiles.py tests/test_provider_prompt_compiler.py tests/test_production_job_ledger.py tests/test_commercial_contracts.py tests/test_commercial_gate.py tests/test_scenario_injection_plan.py
```

后续涉及 API 或前端控制面时再追加：

```bash
.venv/bin/python scripts/check_openapi_types_drift.py
```

如果涉及前端控制面，再追加：

```bash
cd web
npm run lint
npx tsc --noEmit -p tsconfig.json
npm test
NEXT_PUBLIC_IS_DEMO=true npm run build
```

无 token 边界：

- 不运行 `/api/fast/*`。
- 不运行 `/scenario/*` 真实生成。
- 不运行 gate candidate 真实生成。
- 不上传、不发布、不调用 provider probe。

## 11. 代码阶段进入判定

允许继续 C6 的 scenario pipeline 接入前审计与 fixture-first integration 设计。

不允许跳到 C7、C8 或 C9。

原因：

- C1-C5 已在 fixture 层通过 targeted tests，C6 当前完成只读 blueprint、runtime step-order compatibility、state-shape helper、runtime config pass-through 和 StepRunner per-step visibility。
- C6 下一步仍只能做 API/UI 只读可见性设计，不触发真实 provider，不让 StepRunner 自动执行注入，不改变 S1-S5 场景语义。
- C7 依赖 S1/S2/S5 的最小运行时接入边界明确后再推进。
- C8 依赖稳定的后端对象。
- C9 依赖充值、显式开关、job ledger 和 audit bundle。

## 12. 本轮交付物

本轮形成的修改代码前依据：

- 技术调研：`ai-video-commercial-technology-research-review-20260603.md`
- 长视频生产审计：`ai-video-longform-production-research-audit-review-20260603.md`
- AIHOT 市场信号：`aihot-image-video-product-technology-research-review-20260604.md`
- 总体架构：`ai-video-commercial-toolbox-architecture-review-20260603.md`
- Brand Asset Token：`brand-asset-token-contract-review-20260603.md`
- Provider Compiler / Job Ledger：`provider-prompt-compiler-media-job-ledger-review-20260603.md`
- Quality / Rights Gate：`quality-contract-brand-rights-audit-review-20260603.md`
- Phase 0 backlog：`ai-video-commercial-toolbox-phase0-backlog-review-20260603.md`
- 品牌目录 SOP：`brand-data-asset-directory-intake-review-20260603.md`
- Momcozy 接入风险审计：`../../drafts/analysis/brand-momcozy-intake-risk-review-draft-20260604.md`
- Momcozy token 候选方案：`../../drafts/analysis/brand-momcozy-token-candidates-draft-20260604.md`
- C1-C5 首轮代码 + C6 blueprint：`src/models/commercial_contracts.py`、`src/quality/commercial_gate.py`、`src/pipeline/provider_signal_registry.py`、`src/pipeline/provider_profiles.py`、`src/pipeline/provider_prompt_compiler.py`、`src/pipeline/production_job_ledger.py`、`src/pipeline/scenario_injection_plan.py`、`src/pipeline/s1_product_pipeline.py`、`src/pipeline/s2_brand_pipeline_v2.py`、`src/pipeline/s5_brand_vlog_pipeline.py`、`src/pipeline/step_runner.py`
- C1-C5 测试 + C6 blueprint 测试：`tests/test_commercial_contracts.py`、`tests/test_commercial_gate.py`、`tests/test_provider_signal_registry.py`、`tests/test_provider_profiles.py`、`tests/test_provider_prompt_compiler.py`、`tests/test_production_job_ledger.py`、`tests/test_scenario_injection_plan.py`
- 2.0 交叉分析计划：`ai-video-project-2-0-cross-analysis-plan-review-20260603.md`
- 代码前自证与实施计划：本文

## 13. 最终执行判断

当前 2.0 已完成修改代码前的方案闭环，已完成 C1-C5 首轮 contract-first 代码化接入，并完成 C6 只读 scenario injection blueprint、state-shape helper、runtime config pass-through 与 StepRunner per-step visibility。

已完成：

```text
Pydantic contracts
  -> no-token fixtures
  -> offline gate evaluator
  -> provider signal evidence grading
  -> provider profile registry
  -> mock compiler
  -> mock job ledger
  -> GateDecision and RepairPlan
  -> read-only scenario injection planner
  -> S1/S2/S5 first-pass injection blueprint
  -> JSON-safe injection config patch
  -> state-level step injection reader
  -> S1/S2/S5 run() optional config pass-through
  -> StepRunner current-step read-only visibility
```

下一步不是继续扩展研究，也不是进入真实生成，而是继续 C6 的 API/UI 只读可见性：

```text
state exposure contract
  -> API response read-only projection
  -> UI review panel visibility
  -> no provider call, no publish path
```

C6 仍保持无 token、fixture-first，不改变生产默认 provider。
