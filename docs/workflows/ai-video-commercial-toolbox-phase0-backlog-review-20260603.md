---
title: AI 商业化视频工具库 Phase 0 Backlog 与无 Token 验证计划
doc_type: workflow
module: ai-video
topic: commercial-toolbox-phase0-backlog
status: review
created: 2026-06-03
updated: 2026-06-04
owner: self
source: human+ai
related:
  - file: ../research/ai-video-commercial-technology-research-review-20260603.md
    relation: derives-from
  - file: ../research/ai-video-longform-production-research-audit-review-20260603.md
    relation: constrains
  - file: ../research/aihot-image-video-product-technology-research-review-20260604.md
    relation: refines
  - file: ../architecture/ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: implements
  - file: ../architecture/brand-asset-token-contract-review-20260603.md
    relation: implements
  - file: ../architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md
    relation: implements
  - file: ../architecture/quality-contract-brand-rights-audit-review-20260603.md
    relation: implements
  - file: ./brand-data-asset-directory-intake-review-20260603.md
    relation: operationalizes
  - file: ./ai-video-project-2-0-cross-analysis-plan-review-20260603.md
    relation: refined-by
  - file: ./ai-video-project-2-0-code-readiness-plan-review-20260604.md
    relation: governed-by
---

# AI 商业化视频工具库 Phase 0 Backlog 与无 Token 验证计划

> 状态边界：本文把 2026-06-03 至 2026-06-04 的技术调研、AIHOT 市场信号、长视频生产审计与四份架构规格拆成可执行 backlog 和离线验收清单。它是 `review` 状态计划，不表示相关代码已实现，不替代 `docs/claude/known-gaps-stable.md` 的待办清单，也不授权真实 provider 调用。

> 代码实现顺序：修改代码前的阶段放行和 C1-C9 顺序以 `ai-video-project-2-0-code-readiness-plan-review-20260604.md` 为准。

## 1. 目标

Phase 0 的目标是完成“可实现前置条件”，不是直接接入更多模型。

必须产出：

- Brand Asset Token 最小闭环。
- Provider Prompt Compiler 合约。
- Media Job Ledger 合约。
- Quality Contract 与 Brand/Rights Audit Gate。
- S1-S5 的首批注入点和 hard gate 边界。
- 不消耗 token 的离线验证用例。

必须避免：

- 真实调用 POYO、DeepSeek、SiliconFlow、Runway、Veo、Sora、HeyGen、ElevenLabs。
- 触发 `/api/fast/*`、`/scenario/*`、gate candidate 生成、上传、发布。
- 把 docs/research 历史资料当作当前部署事实。
- 在未批准前修改生产默认模型或数据库 schema。

## 2. 当前输入资产

| 文档 | 作用 |
|---|---|
| `docs/research/ai-video-commercial-technology-research-review-20260603.md` | 外部技术调研与行业方向 |
| `docs/research/ai-video-longform-production-research-audit-review-20260603.md` | 长视频生产难点、产品层解法与 2.0 覆盖边界 |
| `docs/research/aihot-image-video-product-technology-research-review-20260604.md` | AIHOT 图像/视频生成市场信号、产品模式与 provider capability 校准 |
| `docs/architecture/ai-video-commercial-toolbox-architecture-review-20260603.md` | 总体工具库架构 |
| `docs/architecture/brand-asset-token-contract-review-20260603.md` | 品牌 token 最小闭环 |
| `docs/architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md` | provider prompt 与生成任务账本 |
| `docs/architecture/quality-contract-brand-rights-audit-review-20260603.md` | 商业可交付 gate |
| `docs/design/asset-lifecycle-state-machine.md` | 资产状态边界 |
| `docs/claude/known-gaps-stable.md` | 当前待办唯一入口与无 token 边界 |

## 3. Phase 0 Backlog

### P0-1 文档合约收口

任务：

- 核对七份 research/architecture review 文档的 frontmatter、related 链接和状态边界。
- 确认所有文档都明确“不代表代码已实现”。
- 确认 `known-gaps-stable.md` 引用完整，但仍声明不替代当前待办清单。

验收：

- `git diff --check` 通过。
- 文档无待办残留标记、本地绝对链接协议、模糊版本词和疑似密钥模式。
- 所有新增正式 Markdown 有 frontmatter。

### P0-2 Brand Asset Source 离线样例

任务：

- 按 `brand-data-asset-directory-intake-review-20260603.md` 处理用户提供的新品牌数据资产目录。
- 准备 3 类离线样例：品牌视频、产品规格、合规禁用词。
- 样例只写结构，不引用真实敏感素材。
- 每个样例标记 rights、PII、territory、allowed uses。

验收：

- 未知授权样例只能进入 `candidate`。
- 含儿童可识别画面的样例不能生成 S5 direct reference。
- 含第三方音乐的样例不能生成 approved audio/music token。

建议落盘位置：

- 未确认样例：`drafts/analysis/`
- 一次性抽取输出：`tmp/outputs/`
- 稳定 schema：`docs/architecture/`

### P0-3 Brand Asset Token 最小 schema

任务：

- 固化 `BrandAssetSource`、`BrandAssetToken`、`BrandTokenReview`。
- 明确 token 状态：`candidate`、`review`、`approved`、`rejected`、`deprecated`、`expired`。
- 明确 hard token 与 soft token 的处理规则。

验收：

- `status=approved` 必须有 review record。
- `license_status != approved` 不得进入生产 bundle。
- hard token 必须有失败后果。

### P0-4 BrandConstraintBundle builder 规则

任务：

- 按 `brand_id`、`scenario_scope`、`step_scope`、`platform_scope` 筛选 token。
- 先处理 `rights_license` 和 `negative_guardrail`。
- 输出 `source_token_ids` 和 `excluded_token_ids`。

验收：

- hard token 不会被压缩或丢弃。
- soft token 可压缩，但必须保留来源。
- expired token 不会进入 bundle。

### P0-5 ProviderCapability 快照

任务：

- 为现有路由中的模型建立能力快照字段。
- 未核实字段统一写 `unknown`。
- 只引用官方文档、供应商后台或项目内已验证文档。

验收：

- 不能把 unknown 当作 true。
- 真实 token benchmark 前必须刷新 `last_verified_at`。
- 不直接修改 `model_router.py` 或生产默认模型。

### P0-6 Provider Prompt Compiler mock

任务：

- 用同一份 `StoryboardShotSchema` mock 编译 Seedance/PoYo、Kling、Runway、Veo、Sora、Wan 风格 prompt。
- 注入 BrandConstraintBundle。
- 记录 `PromptCompileInput`、`PromptCompileResult`、`prompt_hash`。

验收：

- hard negative token 不丢失。
- provider 不支持 negative prompt 时，hard negative 进入主 prompt 并记录 warning。
- prompt 超长时只压缩 soft token。
- reference asset 无 rights 时 blocking fail。

### P0-7 Media Job Ledger prepared / blocked 记录

任务：

- 不提交 provider，只生成 `MediaJobSpec` 与 `MediaJobRecord`。
- 覆盖 `prepared`、`blocked`、`failed` 三类离线状态。
- 记录 `idempotency_key`、`prompt_hash`、`brand_bundle_id`、`reference_asset_ids`。

验收：

- rights blocked case 生成 `blocked` record。
- insufficient credits 不进入 retry。
- `job succeeded` 不等于 `delivery accepted` 的规则写入验收。

### P0-8 QualityContract 离线 gate

任务：

- 固化 `QualityContract`、`AuditEvidenceBundle`、`AuditResult`。
- 区分 blocking 和 advisory。
- 建立 S1-S5 scenario matrix 与 stage gate matrix。

验收：

- final video 存在但缺音乐 license 时必须 blocked。
- S1 claim 无 evidence ref 必须 blocked。
- S3 source fingerprint 缺失必须 blocked。
- S5 儿童 direct reference 必须 blocked。
- safe-zone 低分只 advisory，不单独阻断。

### P0-9 S1/S2/S5 首批注入矩阵

任务：

- S1：product truth、visual reference、negative guardrail。
- S2：visual identity、tone voice、campaign motif、claim evidence。
- S5：persona、scene rhythm、children safety、vlog tone。

验收：

- 每个场景至少覆盖 strategy/script 或 vlog_strategy、storyboard/video_prompts、assemble_final、audit。
- S5 children safety 是 hard gate。
- S2 brand alignment 是独立 audit 维度，不再只复用 S1 质量概念。

### P0-10 S3/S4 hard gate 边界

任务：

- S3 先只做 rights、source fingerprint、likeness、remix boundary。
- S4 先只做 footage rights、人物授权、caption/platform compliance。

验收：

- S3 不因品牌调性分数高而绕过 rights gate。
- S4 不因素材可播放而绕过人物/声音授权。

### P0-11 无 token 回归命令清单

任务：

- 固化后续实现时的低成本验证命令。
- 明确 full pytest 不是唯一 oracle。
- 明确 hermetic regression 的 Python PATH 注意事项。

验收命令：

```bash
ruff check src tests --statistics
```

```bash
cd web
npm run lint
npx tsc --noEmit -p tsconfig.json
npm test
NEXT_PUBLIC_IS_DEMO=true npm run build
```

```bash
python scripts/check_openapi_types_drift.py
```

S1-S5 hermetic regression 运行前必须确保 `.venv/bin` 在 PATH 中，避免把 `python: command not found` 误判为业务工作流坏掉。

### P0-12 长视频生产对象离线检查

任务：

- 定义 `LongformProductionContract`、`SceneLedger`、`ShotLedger`、`TranscriptTimeline`、`TimelineManifest`、`ExportVersion` 的最小字段。
- 准备 60 秒、180 秒和 10 分钟源素材三类无 token fixture。
- 明确长视频当前只进入 contract gate，不进入真实商业交付宣称。

验收：

- 超过 60 秒的 fixture 缺 chapter、scene、shot、timeline、review marker 或 platform package 时必须失败。
- S3/S4 的源视频 fixture 必须有 transcript、scene boundary、rights status 和 source evidence。
- 后期裁剪 fixture 必须输出 `EditDecisionList`、caption safe-zone 结果和 platform package。
- 任一 blocking gate fail 时，`publish_allowed=false`。

### P0-13 Market Signal Intelligence 离线闭环

任务：

- 定义 `ProviderSignalLedger`、`CapabilitySnapshot`、`TechniquePatternRegistry`、`ExperimentBacklog` 的最小字段。
- 将 AIHOT 条目映射到 toolbox、provider capability、gate 和 experiment backlog。
- 为 capability 设置 evidence level：`aihot_signal`、`official_doc`、`vendor_console`、`local_mock`、`token_benchmark`。

验收：

- AIHOT 条目默认只能是 `evidence_level=aihot_signal`。
- 未经官方文档或供应商后台复核的 provider capability 不得进入 production default。
- 热点 provider 只能进入 experiment backlog，不得直接修改 S1-S5 默认 provider。
- 任一市场信号必须能追溯到 source URL、capture date、topic 和 affected toolbox。

## 4. 无 Token 验收矩阵

| case | 输入 | 预期 |
|---|---|---|
| B-001 | 品牌视频授权未知 | 只生成 candidate token |
| B-002 | 品牌视频含儿童可识别画面 | S5 direct reference blocked |
| B-003 | 产品 claim 无证据 | `claim_substantiation_pass=false` |
| B-004 | hard negative token 超长 | prompt compiler 不得丢弃 hard token |
| B-005 | provider capability 字段 unknown | 不得当作支持能力使用 |
| B-006 | reference asset 无 rights | compile blocking fail |
| B-007 | 生成 job 因 rights blocked | `MediaJobRecord.status=blocked` |
| B-008 | safe-zone 低分 | advisory warning，不单独阻断 |
| B-009 | S3 source fingerprint 缺失 | pre-publish blocked |
| B-010 | job succeeded 但 rights failed | delivery accepted=false |
| B-011 | 90s 输出缺 `TimelineManifest` | longform gate blocked |
| B-012 | 源视频 transcript 缺 rights evidence | source ingest blocked |
| B-013 | 16:9 master 派生 9:16 但字幕遮挡 | platform package advisory 或 blocked，按安全区级别判定 |
| B-014 | 单镜头 300s 输出 | structure gate blocked |
| B-015 | AIHOT 条目缺官方复核 | capability remains `aihot_signal` |
| B-016 | 热点模型要求进入默认 provider | blocked until official evidence and token benchmark |
| B-017 | 技巧条目无法映射 toolbox/gate | stays in technique backlog |

## 5. 后续代码实现顺序

仅当用户明确允许代码实现后，按以下顺序推进：

1. 新增 contract dataclass / Pydantic model，先不接数据库。
2. 建立离线 fixture 和 unit tests。
3. 实现 BrandConstraintBundle builder。
4. 实现 ProviderPromptCompiler mock。
5. 实现 MediaJobRecord prepared / blocked ledger。
6. 实现 QualityContract offline evaluator。
7. 接入 S1/S2/S5 的只读注入点。
8. 接入 S3/S4 hard gate。
9. 实现 ProviderSignalLedger 与 TechniquePatternRegistry 离线记录。
10. 再评估是否需要 PostgreSQL JSONB 或 pgvector。
11. 最后才进入真实 token benchmark。

## 6. 禁止动作

Phase 0 禁止：

- 改生产默认模型。
- 写入或读取真实 provider secret。
- 触发真实生成、上传、发布。
- 自动消耗 POYO / DeepSeek / SiliconFlow / HeyGen / ElevenLabs 额度。
- 把候选 token 写入 approved bundle。
- 用 full pytest 红绿直接决定业务链路好坏。
- 修改根目录结构或新增非标准顶层目录。

## 7. 完成定义

Phase 0 完成时必须满足：

- 七份 research/architecture review 规格均可从当前入口找到。
- 本 backlog 的 P0-1 到 P0-13 都有对应实现或离线验收计划。
- 每个 S1-S5 场景都有至少一个 hard gate 和一个 advisory quality path。
- 真实 token benchmark 的前置条件已写清楚。
- 文档状态仍为 review，直到完成首轮离线实现和验收后再考虑转 stable。
