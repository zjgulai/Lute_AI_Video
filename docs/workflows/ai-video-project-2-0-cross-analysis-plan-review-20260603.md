---
title: AI Video Project 2.0 交叉分析与优化计划
doc_type: workflow
module: ai-video
topic: project-2-0-cross-analysis-plan
status: review
created: 2026-06-03
updated: 2026-06-04
owner: self
source: human+ai
related:
  - file: ../research/ai-video-commercial-technology-research-review-20260603.md
    relation: synthesizes
  - file: ../research/ai-video-longform-production-research-audit-review-20260603.md
    relation: constrains
  - file: ../research/aihot-image-video-product-technology-research-review-20260604.md
    relation: refines
  - file: ../architecture/ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: plans
  - file: ../architecture/brand-asset-token-contract-review-20260603.md
    relation: plans
  - file: ../architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md
    relation: plans
  - file: ../architecture/quality-contract-brand-rights-audit-review-20260603.md
    relation: plans
  - file: ./ai-video-commercial-toolbox-phase0-backlog-review-20260603.md
    relation: refines
  - file: ./brand-data-asset-directory-intake-review-20260603.md
    relation: waits-for
  - file: ./ai-video-project-2-0-code-readiness-plan-review-20260604.md
    relation: finalized-by
---

# AI Video Project 2.0 交叉分析与优化计划

> 状态边界：本文是 2026-06-03 的 2.0 方案收口计划。它基于已有调研与当前项目结构做交叉分析，不表示相关代码已实现，不授权真实 provider 调用，不改变 S1-S5 的场景定义。品牌数据资产目录到位后，先按只读接入 SOP 生成候选资产与 token 报告，再进入实现设计。

> 代码前执行入口：2026-06-04 的修改代码前自证和实施顺序以 `ai-video-project-2-0-code-readiness-plan-review-20260604.md` 为准。

## 1. 2.0 核心判断

Project 2.0 不应被定义为“接入更多视频模型”。

它应被定义为：

```text
AI 商业视频生产系统
  = Market Signal Intelligence
  + S1-S5 稳定场景
  + Brand Asset Token
  + Creative Contract
  + Provider Prompt Compiler
  + Production Job Ledger
  + Quality / Brand / Rights Gate
  + 商业工具箱
```

关键取舍：

- S1-S5 保持业务场景不变，所有新增能力通过 contract、adapter、gate、toolbox 增量注入。
- 品牌资产目录不是素材仓库搬运任务，而是 Brand Asset Source 与 Brand Asset Token 的生成入口。
- 视频生成能力的核心差距不只在模型质量，还在引用资产控制、任务账本、后期修复、可追溯审计和无 token 回归。
- 长视频自动化不能写成“15s clip × N”已经可交付；2.0 先覆盖长视频约束、账本、gate 和产品控制面，真实长视频商业交付必须等待 `LongformProductionContract`、`SceneLedger`、`TimelineManifest`、`ReviewCheckpoint` 和 `PlatformPackage` 闭环。
- AIHOT 等市场信号只能先进入 `ProviderSignalLedger` 和 `TechniquePatternRegistry`，不能因为单日热点直接改变 S1-S5 provider 或生产默认模型。
- 2.0 第一阶段不做真实生成，先完成可验证的离线合约；否则后续 token 消耗只能得到不可复盘的单次样片。

## 2. 交叉分析结论

| 外部能力方向 | 当前项目基础 | 2.0 优化动作 | 不做的事 |
|---|---|---|---|
| 高质量短视频生成 | 已有 POYO / Seedance / Remotion 路径 | 引入 `ProviderPromptCompiler` 与 `MediaJobLedger`，让每次生成有 provider profile、prompt hash、artifact manifest 和 retry lineage | 不在场景代码里直接拼 provider prompt |
| 品牌一致性 | 已有 Brand Kit 与 137 张产品图可见 | 将品牌资产目录转成 `BrandAssetSource`、`BrandAssetToken`、`BrandConstraintBundle` | 不把原始品牌视频直接投喂生成模型 |
| 图像生成与关键帧 | 已有 keyframe、GPT image、thumbnail skill | 补 `ImageToolbox`，输出 seed frame、thumbnail、product hero、style reference，并进入统一质量审计 | 不把图片工具作为孤立功能页堆叠 |
| 故事版与镜头规划 | S1 有成熟 step-by-step 与 gate，S2-S5 较轻 | 把 storyboard 提升为跨场景 `Creative Contract`，用 shot schema 承接视频、图片、后期和配音 | 不让脚本文本直接驱动视频生成 |
| 演示视频与数字人 | 当前未形成稳定 toolbox | 补 `PresenterDemoToolbox`，先用脚本、镜头、音频、字幕合约描述，不急于绑定单一 avatar provider | 不在授权与肖像边界未清前上线克隆人像 |
| 语音克隆与 TTS | 已有 CosyVoice，ElevenLabs 为 legacy | 补 `AudioToolbox`，区分 TTS、voice style、voice clone、music bed、SFX，并以 rights gate 控制 | 不用未知授权声音做 voice clone |
| 音乐与后期 | 当前重心在生成与 Remotion | 补 `PostProductionToolbox`，覆盖 beat map、caption style、resize、poster、platform cutdown | 不把后期当成视频生成失败后的人工补丁 |
| 商业交付质量 | 已有 self-audit、CLIP alignment、thumbnail runbook | 统一为 `QualityContract` 和 `AuditEvidenceBundle`，把 quality、brand、rights、platform 分层判定 | 不用单一分数覆盖授权或儿童安全问题 |
| 长视频生产控制 | 已有短/中短视频分镜、continuity 和 Remotion 基础 | 补 `LongformProductionContract`、`TranscriptTimeline`、`SceneLedger`、`EditDecisionList`、`ReviewCheckpoint`、`ExportVersion` | 不声明当前方案已经 cover 长视频商业交付 |
| AIHOT 市场信号 | 目前只有一次性调研文档 | 补 `ProviderSignalLedger`、`CapabilitySnapshot`、`TechniquePatternRegistry`，把热点模型、产品模式和技巧进入可验证 backlog | 不把 AIHOT 聚合条目当作官方 capability |

## 3. S1-S5 的 2.0 定位

### S1 Product Direct

2.0 定位：商品事实与卖点表达基线。

新增能力：

- 产品图、规格、卖点、禁用 claim 进入 `ProductTruthBundle`。
- 关键帧生成必须引用 approved product token。
- 视频生成前生成 `ShotIntent`，明确镜头要证明的卖点。
- 输出需要包含 product claim evidence、visual consistency score、poster coverage。

验收重点：

- 不能凭生成画面新增未经验证的产品功能。
- 产品细节不清晰时，先回到 image/keyframe 阶段，不直接重跑视频。

### S2 Brand Campaign

2.0 定位：品牌心智、视觉风格与战役叙事。

新增能力：

- 品牌视频、品牌图、slogan、视觉规范进入 `BrandConstraintBundle`。
- 文案、配色、场景、转场、字幕语气统一接受 brand gate。
- 支持 campaign motif、seasonal theme、platform variant。

验收重点：

- 生成结果必须解释使用了哪些 brand token。
- 不能只靠色彩相似度判定品牌一致。

### S3 Influencer Remix

2.0 定位：素材拆解、结构重写与合规二创。

新增能力：

- 源视频先生成 `SourceFingerprint`：镜头结构、口播结构、音乐、字幕、人物、产品露出。
- remix 只继承结构策略，不继承未授权人脸、声音、音乐和第三方品牌元素。
- S3 的 rights gate 优先级高于 quality gate。

验收重点：

- 未知授权素材只能进入分析与改写，不进入生成引用。
- remix 输出必须保留 source transformation evidence。

### S4 Live Shoot

2.0 定位：实拍素材快创、整理、剪辑和平台适配。

新增能力：

- 实拍素材进入 `FootageSource`，记录 resolution、duration、scene tags、audio rights、visible PII。
- 提供 supercut、caption、music bed、resize、poster、platform cutdown 工具链。
- 以后期和剪辑为主，生成模型只用于补镜头或封面，不抢主路径。

验收重点：

- 低质量素材不能通过生成模型掩盖授权问题。
- 含可识别人物、儿童、家庭环境的素材必须先过 PII 与 rights gate。

### S5 Brand VLOG

2.0 定位：品牌人格、生活方式叙事与儿童安全边界。

新增能力：

- 人设、场景、镜头节奏、旁白风格进入 `PersonaSceneBundle`。
- brand vlog 可引用品牌资产的 mood、tone、scene rhythm，但不直接复刻真人身份。
- 儿童相关画面、声音、家庭空间、健康功效 claim 进入 blocking gate。

验收重点：

- persona consistency 不能凌驾于儿童安全、肖像授权和医疗化表达边界。
- 需要把 model selector、六视图选择与 Brand Asset Token 对齐。

## 4. 商业工具箱重组

2.0 的工具箱不按“模型厂商”组织，而按商业生产任务组织。

| Toolbox | 输入 | 输出 | 首批接入场景 |
|---|---|---|---|
| `ImageToolbox` | product token、brand style token、shot intent | keyframe、thumbnail、hero image、reference frame | S1、S2、S5 |
| `StoryboardToolbox` | strategy brief、script schema、brand bundle | shot list、camera plan、motion cue、asset requirement | S1-S5 |
| `VideoToolbox` | provider prompt、reference bundle、job profile | video artifact、poster、provider metadata | S1、S2、S5 |
| `AudioToolbox` | script、voice style、rights profile | TTS、music bed、SFX、caption timing | S2、S4、S5 |
| `PresenterDemoToolbox` | demo script、avatar policy、brand tone | presenter video plan、demo shot contract | S1、S2 |
| `PostProductionToolbox` | video artifact、caption plan、platform target | cutdown、resize、subtitle burn-in、poster | S1-S5 |
| `AuditToolbox` | source tokens、job ledger、artifacts | audit bundle、gate result、repair recommendation | S1-S5 |

工具箱必须共享三类底座：

- `BrandAssetToken`：回答“这次创作依据了哪些品牌资产”。
- `MediaJobLedger`：回答“这次生成或后期任务如何执行、失败、重试、产出”。
- `QualityContract`：回答“这个结果是否可商业交付，不能交付时卡在哪一层”。

## 5. 2.0 目标架构

```text
Layer -1: Market Signal Intelligence
  -> ProviderSignalLedger
  -> CapabilitySnapshot
  -> TechniquePatternRegistry
  -> ExperimentBacklog

Layer 0: Brand Data Directory Intake
  -> readonly inventory
  -> source classification
  -> rights / PII / children / music / claim precheck

Layer 1: Brand Asset Tokenization
  -> BrandAssetSource
  -> BrandAssetToken
  -> BrandConstraintBundle

Layer 2: Creative Contract
  -> StrategyBrief
  -> ScriptSchema
  -> StoryboardShotSchema
  -> AssetRequirement

Layer 3: Toolbox Adapter
  -> ImageToolbox
  -> StoryboardToolbox
  -> VideoToolbox
  -> AudioToolbox
  -> PresenterDemoToolbox
  -> PostProductionToolbox

Layer 4: Provider Compiler and Job Ledger
  -> ProviderProfile
  -> CompiledPrompt
  -> MediaJob
  -> ArtifactManifest

Layer 5: Audit and Gate
  -> QualityContract
  -> BrandAudit
  -> RightsAudit
  -> PlatformAudit
  -> RepairPlan

Layer 6: Scenario Orchestration
  -> S1 Product Direct
  -> S2 Brand Campaign
  -> S3 Influencer Remix
  -> S4 Live Shoot
  -> S5 Brand VLOG
```

## 6. 阶段计划

### 2.0-P0 文档与合约冻结

目标：

- 确认现有十一份 review 文档形成闭环。
- 确认 2.0 只通过合约、adapter、gate 和 toolbox 扩展 S1-S5。
- 确认 AIHOT 市场信号只作为 capability 线索，不作为生产 provider 事实。
- 保持无 token 边界。

产出：

- 本文。
- `known-gaps-stable.md` 入口引用。
- 现有 Phase 0 backlog 的 2.0 依赖补充。
- 长视频生产覆盖边界和必补对象清单。
- AIHOT 图像/视频产品信号的 2.0 校准文档。

验收：

- `git diff --check` 通过。
- 新增正式 Markdown 有 frontmatter。
- 文档不声明未实现代码已经实现。

### 2.0-P1 品牌目录只读接入

触发条件：

- 用户提供新的品牌数据资产目录。

执行：

- 按 `brand-data-asset-directory-intake-review-20260603.md` 只读盘点。
- 不复制、不移动、不上传、不转码原始资产。
- 生成目录清单、资产分类、授权预检、候选 source、候选 token、S1/S2/S5 注入建议。

默认规则：

- 授权未知的资产只能进入 candidate。
- 含儿童可识别画面的资产不能作为 S5 direct reference。
- 含未知授权声音的资产不能用于 voice clone。

### 2.0-P2 离线数据模型与 fixture

目标：

- 把 `BrandAssetSource`、`BrandAssetToken`、`BrandConstraintBundle`、`CreativeContract`、`MediaJob`、`QualityContract` 做成可测试的本地模型。
- 为长视频补 `LongformProductionContract`、`TranscriptTimeline`、`SceneLedger`、`ShotLedger`、`TimelineManifest`、`ExportVersion` 的离线 fixture。

验收：

- fixture 能覆盖 S1-S5。
- S3 unknown rights 被 blocking gate 拦截。
- S5 children safety 被 blocking gate 拦截。
- S1 product claim 必须能追溯到 source token。
- 超过 60 秒的 fixture 必须有 chapter、scene、shot、timeline、review marker 和 platform package。

### 2.0-P3 Prompt Compiler 与 Job Ledger mock 闭环

目标：

- 不调用 provider，先验证 provider prompt 编译和 job ledger 生命周期。

验收：

- 同一个 creative contract 能编译出不同 provider profile 的 prompt。
- 编译结果记录 prompt hash、reference token、provider limits 和 fallback plan。
- mock job 能记录 pending、running、succeeded、failed、repaired 状态。

### 2.0-P4 Quality / Brand / Rights Gate 离线闭环

目标：

- 把质量分、品牌一致性、授权边界、平台边界拆成独立 gate。

验收：

- quality pass 不能覆盖 rights fail。
- brand advisory 不阻断 preview，但阻断 publish。
- platform fail 能返回明确 repair recommendation。

### 2.0-P5 S1-S5 场景注入

目标：

- 在不改变 S1-S5 场景语义的前提下接入 toolbox 与 gate。

优先级：

1. S1：ProductTruthBundle、ImageToolbox、QualityContract。
2. S2：BrandConstraintBundle、StoryboardToolbox、BrandAudit。
3. S5：PersonaSceneBundle、AudioToolbox、children safety gate。
4. S3：SourceFingerprint、RightsAudit、remix transformation evidence。
5. S4：FootageSource、PostProductionToolbox、platform cutdown。

### 2.0-P6 真实 token 小样本基准

触发条件：

- 明确充值完成。
- 显式设置真实 smoke 开关。
- 离线合约与无 token gate 全部通过。

执行：

- 每个场景只跑最小样本。
- 每次真实生成必须写入 MediaJobLedger。
- 每个 artifact 必须进入 AuditEvidenceBundle。
- 样本结果只能作为技术验证，不自动升级为生产质量结论。

### 2.0-P7 UI 与运营面

目标：

- 把 2.0 能力变成可操作界面，而不是隐藏在脚本里。

候选界面：

- Brand Asset Intake Review。
- Token Bundle Builder。
- Media Job Ledger Viewer。
- Quality Audit Report。
- Toolbox Studio。
- Scenario Injection Diff。

验收：

- 用户能看到每个视频引用了哪些品牌 token。
- 用户能看到每个生成任务的 provider、prompt hash、artifact 和 gate 结果。
- 用户能区分 preview、review、approved、blocked。

## 7. 决策门

| 决策 | 放行条件 | 不放行表现 |
|---|---|---|
| 品牌目录进入候选 token | 只读盘点完成，资产类别与授权状态可见 | 目录来源不明、授权缺失、含敏感个人信息未标记 |
| 候选 token 进入 approved bundle | rights、PII、children、music、claim 预检通过 | 未知授权、第三方品牌露出、未授权声音 |
| Toolbox 进入 S1-S5 | fixture 与 mock job 通过 | 只能在单场景硬编码运行 |
| 真实 provider 小样本 | no-token gate 全绿，充值与开关明确 | 账本缺失、prompt 不可追溯、gate 无证据 |
| 结果进入商业交付 | quality、brand、rights、platform 均满足发布条件 | 任一 blocking gate fail |

## 8. 等待品牌目录期间的工作安排

在品牌目录到达前，优先完成：

- 收口 2.0 计划和相关引用。
- 确认品牌目录接入后只读、离线、candidate-first。
- 准备后续读取目录时的输出位置：`tmp/outputs/` 放盘点结果，`drafts/analysis/` 放待确认分析。

品牌目录到达后，第一轮只要求用户提供：

```text
BRAND_ASSET_DIR=/absolute/path/to/brand-assets
brand_id=<stable-brand-id>
source_owner=<owner-or-source>
default_territory=<country-or-region>
default_allowed_uses=<reference|generation|publishing|training>
```

如果只提供路径，则默认：

- `license_status=unknown`
- `allowed_uses=[]`
- 只做只读盘点与 candidate token 抽取
- 不进入 approved bundle
- 不触发真实 provider

## 9. 2.0 验收标准

Project 2.0 进入实现阶段前，必须满足：

- 每个 S1-S5 输出都能追溯到 source token、creative contract、media job 和 audit result。
- 每个真实生成 artifact 都有 provider profile、compiled prompt hash、job status、artifact manifest。
- 每个商业交付结果都有 quality、brand、rights、platform 四类 gate 证据。
- S3 和 S5 的授权、肖像、儿童安全 gate 不能被质量分覆盖。
- 品牌资产目录不会被复制进仓库，不会被上传到外部服务，不会默认进入 approved。
- 无 token 测试先通过，再跑真实小样本。

## 10. 实施顺序

推荐顺序：

1. 完成本计划与入口引用。
2. 等待品牌目录。
3. 对品牌目录做只读盘点。
4. 生成 candidate source 与 candidate token 报告。
5. 根据目录结果修订 `BrandAssetToken` 与 `QualityContract`。
6. 再进入代码实现设计。

不推荐顺序：

- 先接 provider，再补品牌资产边界。
- 先跑真实样片，再补 MediaJobLedger。
- 先做 UI，再定义 source token 与 gate。
- 把 S1-S5 重写成一个大一统 pipeline。
