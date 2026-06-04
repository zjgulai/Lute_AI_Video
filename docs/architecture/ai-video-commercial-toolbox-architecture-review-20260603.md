---
title: AI 商业化视频工具库架构规格
doc_type: architecture
module: ai-video
topic: commercial-video-toolbox
status: review
created: 2026-06-03
updated: 2026-06-04
owner: self
source: human+ai
related:
  - file: ../research/ai-video-commercial-technology-research-review-20260603.md
    relation: derives-from
  - file: ../research/ai-video-longform-production-research-audit-review-20260603.md
    relation: constrained-by
  - file: ../research/aihot-image-video-product-technology-research-review-20260604.md
    relation: refined-by
  - file: ../design/asset-lifecycle-state-machine.md
    relation: extends
  - file: ./brand-asset-token-contract-review-20260603.md
    relation: specialized-by
  - file: ./provider-prompt-compiler-media-job-ledger-review-20260603.md
    relation: specialized-by
  - file: ./quality-contract-brand-rights-audit-review-20260603.md
    relation: specialized-by
  - file: ../workflows/ai-video-commercial-toolbox-phase0-backlog-review-20260603.md
    relation: implemented-by
  - file: ../workflows/ai-video-project-2-0-cross-analysis-plan-review-20260603.md
    relation: planned-by
  - file: ../workflows/ai-video-project-2-0-code-readiness-plan-review-20260604.md
    relation: implementation-sequenced-by
---

# AI 商业化视频工具库架构规格

> 状态边界：本文是 Phase 0 架构合约，定义后续实现的对象、边界、注入点和验收方式。它不表示相关代码已经实现，也不改变当前 S1-S5 的场景定义。

> 代码前执行顺序：后续实现阶段以 `docs/workflows/ai-video-project-2-0-code-readiness-plan-review-20260604.md` 的 C1-C9 放行顺序为准。

## 1. 目标

把当前 AI Video Pipeline 从“多场景视频生成流水线”升级为“商业 AI 视频生产系统 + 工具库”。

核心目标：

- S1-S5 场景保持不变。
- 新增能力通过工具箱、adapter、contract 注入，不改写场景语义。
- AIHOT 等市场信号先进入 `ProviderSignalLedger` 和 `TechniquePatternRegistry`，不直接改变生产默认 provider。
- 品牌资产进入工作流前先 token 化，避免把原始品牌视频直接丢给生成模型。
- 视频、图片、音频、数字人、故事板、后期、审计都使用统一作业账本和质量合同。
- 长视频能力先以 `LongformProductionContract`、`SceneLedger`、`TimelineManifest`、`ReviewCheckpoint` 和 `ExportVersion` 进入合约层，不能用短 clip 拼接直接宣称商业交付覆盖。
- 后续真实 token 测试必须可追踪、可复盘、可比较。

非目标：

- 不把所有 provider 能力硬编码进一个 pipeline。
- 不把 leaderboards 当作业务质量结论。
- 不把市场热点当作官方 capability。
- 不把品牌资产和临时中间产物混成同一类文件。
- 不在 Phase 0 直接改生产默认模型。
- 不把 `15s clip × N` 当作长视频生产闭环。

## 2. 总体架构

```text
Market Signal Intelligence Layer
  -> ProviderSignalLedger
  -> CapabilitySnapshot
  -> TechniquePatternRegistry
  -> ExperimentBacklog
  -> Provider Prompt Compiler / Toolbox planning

S1-S5 Scenario Workflow Layer
  -> Creative Contract Layer
  -> Brand Constraint Layer
  -> Toolbox Adapter Layer
  -> Provider Adapter Layer
  -> Media Job Ledger
  -> Quality / Brand / Rights Audit Layer
```

### 2.1 Scenario Workflow Layer

场景层只表达业务意图：

- S1 Product Direct：商品直拍与卖点展示。
- S2 Brand Campaign：品牌战役与品牌心智表达。
- S3 Influencer Remix：素材分析、结构重写、合规 remix。
- S4 Live Shoot：实拍/库存素材快创。
- S5 Brand VLOG：品牌 VLOG、生活方式叙事、儿童安全硬约束。

场景层不直接理解 provider 差异，也不直接拼接 provider prompt。

### 2.1.1 Market Signal Intelligence Layer

市场信号层只处理外部趋势和 provider 线索：

- `ProviderSignalLedger`：记录 AIHOT、官方文档、供应商后台、真实 benchmark 的来源、日期、证据等级和影响范围。
- `CapabilitySnapshot`：把 provider 的图像、视频、音频、编辑、异步任务、参考资产能力记录为可复核快照。
- `TechniquePatternRegistry`：记录 storyboard-first、image-as-code、dubbing、foley、ad asset pack、ComfyUI workflow 等可迁移方法。
- `ExperimentBacklog`：只保存待验证 provider 或技巧，不改变 S1-S5 默认模型。

规则：

- AIHOT 条目默认 `evidence_level=aihot_signal`。
- capability 未达到 `official_doc` 或更高证据等级前，不得进入 production default。
- 真实 token benchmark 必须写入 Media Job Ledger 和 AuditEvidenceBundle。

### 2.2 Creative Contract Layer

创意合约层把业务语义转成结构化中间表示：

- `StrategyBrief`
- `ScriptSchema`
- `StoryboardShotSchema`
- `BrandConstraintBundle`
- `MediaJobSpec`
- `QualityContract`

Provider prompt、图片生成、音频生成、后期渲染都从这些结构化对象派生。

### 2.3 Toolbox Adapter Layer

工具箱层提供可组合能力：

- `image-toolbox`
- `video-provider-toolbox`
- `storyboard-toolbox`
- `audio-toolbox`
- `presenter-toolbox`
- `post-production-toolbox`
- `audit-toolbox`

工具箱不直接持有场景状态，只接收 contract object 并返回规范化 artifact。

### 2.4 Provider Adapter Layer

Provider adapter 只负责供应商差异：

- 鉴权。
- prompt 编译结果发送。
- 异步任务提交、轮询、回调。
- artifact 下载和保存。
- provider error 结构化。
- 成本、耗时、模型、任务 id 记录。

业务层不直接调用 provider SDK。

## 3. 核心数据合约

### 3.1 BrandAssetToken

`BrandAssetToken` 是品牌资产进入生成链路的最小约束单位。

```json
{
  "token_id": "bat_momcozy_visual_001",
  "brand_id": "momcozy",
  "source_asset_id": "asset_123",
  "source_path": "brand/videos/momcozy-tone-sample.mp4",
  "token_type": "visual_identity",
  "modality": "video",
  "payload": {},
  "embedding_ref": null,
  "scenario_scope": ["s1", "s2", "s5"],
  "step_scope": ["storyboard", "video_prompts", "thumbnail_prompts", "audit"],
  "platform_scope": ["tiktok", "youtube_shorts", "shopify"],
  "priority": 80,
  "strength": "soft",
  "license_status": "approved",
  "expires_at": null,
  "territory": ["US"],
  "pii_flag": false,
  "copyright_risk": "low",
  "provenance": {
    "created_from": "human_uploaded_brand_video",
    "reviewed_by": "self",
    "reviewed_at": "2026-06-03"
  }
}
```

字段规则：

- `token_id` 必须全局唯一。
- `brand_id` 必须稳定，不使用展示名。
- `token_type` 必须来自固定枚举。
- `strength=hard` 的 token 不能被 prompt compiler 丢弃。
- `license_status != approved` 的 token 不得进入生产生成。
- `pii_flag=true` 的 token 必须经过权限和使用场景检查。

### 3.2 Token 类型枚举

| token_type | 含义 | 默认强度 |
|---|---|---|
| `visual_identity` | 色彩、字体、构图、材质、光线 | soft |
| `tone_voice` | 语言风格、句式、语气、情绪 | soft |
| `product_truth` | 产品事实、规格、卖点、证据 | hard |
| `visual_reference` | 产品图、场景图、包装、手部演示 | hard/soft |
| `motion_editing` | 镜头运动、剪辑节奏、转场 | soft |
| `caption_style` | 字幕位置、大小、语气、禁用符号 | soft |
| `persona_audience` | 人群、角色、生活场景 | soft |
| `platform_compliance` | 平台规则、尺寸、禁用表达 | hard |
| `rights_license` | 授权、地域、期限、来源证明 | hard |
| `negative_guardrail` | 禁止画面、禁止 claim、安全限制 | hard |
| `performance_signal` | 历史高表现结构、hook、封面模式 | soft |

### 3.3 BrandConstraintBundle

`BrandConstraintBundle` 是运行时从 token 池中筛选出的上下文包。

```json
{
  "bundle_id": "bcb_momcozy_s2_tiktok_001",
  "brand_id": "momcozy",
  "scenario": "s2",
  "platform": "tiktok",
  "locale": "en-US",
  "positive_prompt_blocks": [],
  "negative_prompt_blocks": [],
  "asset_refs": [],
  "claim_rules": [],
  "caption_rules": [],
  "audio_rules": [],
  "audit_rubric": [],
  "hard_token_ids": [],
  "soft_token_ids": [],
  "source_token_ids": []
}
```

生成规则：

- 先过滤 `rights_license` 和 `platform_compliance`。
- 再按 `scenario_scope`、`step_scope`、`platform_scope` 取 token。
- hard token 优先进入 `negative_prompt_blocks`、`claim_rules`、`asset_refs` 或 `audit_rubric`。
- soft token 可被压缩，但必须在 `source_token_ids` 中保留可追踪关系。

### 3.4 StoryboardShotSchema

`StoryboardShotSchema` 是 provider prompt compiler 的唯一上游。

```json
{
  "shot_id": "s2_001_003",
  "duration_seconds": 5,
  "purpose": "product_reveal",
  "subject": "wearable breast pump on a bedside table",
  "action": "soft morning light reveals the compact product shape",
  "camera": {
    "shot_size": "medium_close_up",
    "movement": "slow_push_in",
    "angle": "eye_level",
    "lens": "50mm"
  },
  "composition": {
    "aspect_ratio": "9:16",
    "safe_zone": "caption_lower_third",
    "foreground": [],
    "background": []
  },
  "style": {
    "lighting": "soft natural morning",
    "color_palette": ["warm white", "muted rose", "soft gray"],
    "texture": "clean premium household"
  },
  "audio_intent": {
    "voiceover": true,
    "native_audio_allowed": false,
    "music_mood": "calm_confident"
  },
  "reference_assets": [],
  "brand_bundle_id": "bcb_momcozy_s2_tiktok_001",
  "negative_constraints": []
}
```

规则：

- Shot schema 不包含 provider 专属字段。
- provider 专属字段只能在 compiler 输出中出现。
- `reference_assets` 必须来自已通过 license gate 的 asset。
- `negative_constraints` 必须包含对应场景的 hard guardrail。

### 3.5 ProviderCapability

Provider 能力必须被结构化记录，不能靠代码注释或模型名推断。

```json
{
  "provider": "poyo",
  "model": "seedance-2",
  "modalities": ["text_to_video", "image_to_video"],
  "supports_reference_images": true,
  "supports_reference_video": true,
  "supports_first_last_frame": "unknown",
  "supports_native_audio": true,
  "max_duration_seconds": 15,
  "async_required": true,
  "retention_days": "unknown",
  "c2pa": "unknown",
  "recommended_scenarios": ["s1", "s5"],
  "known_failure_modes": [],
  "last_verified_at": "2026-06-03",
  "source_url": "https://docs.poyo.ai/api-manual/video-series/seedance-2"
}
```

规则：

- 未核实字段必须写 `unknown`，禁止猜测。
- `last_verified_at` 必须随文档或代码更新。
- 任何真实 token benchmark 前，必须刷新 capability matrix。

### 3.6 ProviderPromptCompiler

Compiler 输入：

- `StoryboardShotSchema`
- `BrandConstraintBundle`
- `ProviderCapability`
- `PlatformTarget`

Compiler 输出：

```json
{
  "compiler": "seedance_prompt_compiler",
  "provider": "poyo",
  "model": "seedance-2",
  "prompt": "string",
  "negative_prompt": "string",
  "reference_asset_ids": [],
  "duration_seconds": 5,
  "aspect_ratio": "9:16",
  "provider_options": {},
  "dropped_soft_token_ids": [],
  "hard_token_ids": [],
  "prompt_hash": "sha256:..."
}
```

规则：

- hard token 不能出现在 `dropped_soft_token_ids`。
- `prompt_hash` 用于复盘、去重和 benchmark。
- provider prompt 中禁止出现未经授权的肖像、第三方品牌、未证实功效 claim。

### 3.7 MediaJobSpec

`MediaJobSpec` 描述一次媒体生成或后期处理任务。

```json
{
  "job_id": "mj_s2_001_003",
  "job_type": "video_generation",
  "scenario": "s2",
  "step_name": "seedance_clips",
  "provider": "poyo",
  "model": "seedance-2",
  "input_contract_refs": {
    "shot_id": "s2_001_003",
    "brand_bundle_id": "bcb_momcozy_s2_tiktok_001",
    "prompt_hash": "sha256:..."
  },
  "reference_asset_ids": [],
  "expected_outputs": [
    {
      "kind": "creation_intermediate",
      "category": "seedance",
      "media_type": "video"
    }
  ],
  "cost_budget": {
    "max_usd": 1.5
  },
  "timeout_seconds": 1500,
  "retry_policy": {
    "max_attempts": 2,
    "retry_on": ["rate_limit", "transient_provider_error"]
  }
}
```

### 3.8 MediaJobRecord

`MediaJobRecord` 是任务完成后的账本记录。

```json
{
  "job_id": "mj_s2_001_003",
  "provider_task_id": "external_task_id",
  "status": "succeeded",
  "started_at": "2026-06-03T10:00:00Z",
  "finished_at": "2026-06-03T10:06:12Z",
  "latency_seconds": 372,
  "cost_actual_usd": 0.75,
  "artifact_ids": [],
  "artifact_paths": [],
  "error_type": null,
  "error_message": null,
  "raw_response_ref": null
}
```

规则：

- provider 原始返回如果包含敏感字段，只能存 sidecar 安全引用，不能直接进入公开资产。
- 失败必须结构化，不能只写自然语言错误。
- 任务结果必须关联到 artifact。

### 3.9 QualityContract

`QualityContract` 定义每个场景和步骤的最低可接受条件。

```json
{
  "contract_id": "qc_s2_final_v1",
  "scenario": "s2",
  "stage": "final_video",
  "blocking_checks": [
    "rights_pass",
    "hard_negative_token_pass",
    "claim_substantiation_pass",
    "media_file_exists"
  ],
  "advisory_checks": [
    "brand_alignment_score",
    "visual_quality_score",
    "safe_zone_score",
    "audio_mix_score",
    "viral_prediction_score"
  ],
  "thresholds": {
    "brand_alignment_score": 0.72,
    "visual_quality_score": 0.65,
    "safe_zone_score": 0.9
  }
}
```

规则：

- blocking check 失败时不得自动标记为可交付。
- advisory check 失败可以生成修改建议，但不能伪装成通过。
- S3/S5 的 rights 和 safety 必须是 blocking。

## 4. 场景注入矩阵

| 场景 | 核心 bundle | hard token | soft token | audit 重点 |
|---|---|---|---|---|
| S1 | product truth + visual reference | 产品事实、禁用 claim、授权产品图 | 色彩、字幕、节奏 | 商品真实性、缩略图可用性、产品露出 |
| S2 | brand identity + campaign motif | claim 证据、平台合规 | 情绪、镜头、品牌语气 | 品牌一致性、信息层级、campaign 记忆点 |
| S3 | rights + remix boundary | 授权、肖像、第三方版权 | 节奏学习、结构学习 | 风格越界、来源风险、品牌融合 |
| S4 | footage rights + live shoot rhythm | 素材授权、人物权限、平台合规 | 字幕、节奏、CTA | 素材质量、镜头可用性、剪辑完成度 |
| S5 | persona + safety + lifestyle tone | 儿童安全、产品 claim、授权 | vlog 语气、生活方式、场景节奏 | 人物/场景连续性、安全约束、品牌温度 |

## 5. 工具箱契约

### 5.1 统一 Adapter 接口

每个工具箱 adapter 遵循同一输入输出原则：

```text
Contract Object + Context
  -> validate
  -> execute / submit
  -> poll / collect
  -> normalize artifact
  -> write MediaJobRecord
  -> return structured result
```

禁止：

- adapter 直接读取全局场景状态。
- adapter 静默吞 provider 错误。
- adapter 直接写最终结果而不生成 job record。

### 5.2 Image Toolbox

能力：

- keyframe generation
- thumbnail generation
- image edit / inpaint
- background replace
- product render
- upscaling
- text safe-zone validation

输入：

- `StoryboardShotSchema`
- `BrandConstraintBundle`
- `ImageGenerationSpec`

输出：

- image artifact
- prompt hash
- quality report

### 5.3 Video Provider Toolbox

能力：

- text-to-video
- image-to-video
- reference video guided generation
- first/last frame guided generation
- async task polling
- clip continuity handoff

输入：

- compiler output
- `MediaJobSpec`

输出：

- clip artifact
- provider task record
- clip quality report

### 5.4 Audio Toolbox

能力：

- TTS
- voice clone
- dubbing
- forced alignment
- sound effects
- music bed
- ducking / mix plan

硬约束：

- voice clone 必须有 consent token。
- music / SFX 必须有 license token。
- native video audio 只能作为输入层之一，不自动成为最终音频。

### 5.5 Presenter Toolbox

能力：

- avatar presenter video
- product demo narration
- training / explain video
- multilingual presenter variants

规则：

- presenter identity 必须绑定 consent 和 license。
- presenter clip 作为中间片段进入 assemble，不替代 S1-S5 场景。

### 5.6 Post-production Toolbox

能力：

- Remotion assembly
- captions
- poster extraction
- multi-aspect export
- intro / outro
- watermark / C2PA
- final package manifest

输出必须包含：

- final video artifact
- poster artifact
- caption artifact
- provenance manifest

### 5.7 Audit Toolbox

能力：

- media quality audit
- brand token audit
- rights audit
- claim substantiation audit
- safe-zone audit
- continuity audit
- cost/latency audit

审计结果分两类：

- blocking：决定是否可交付。
- advisory：生成优化建议和降级解释。

## 6. Asset Lifecycle 扩展

现有资产状态机保留：

- `brand_kit`
- `uploaded`
- `intermediate`
- `final_work`
- `published`

新增逻辑状态，不改变现有文件状态枚举：

| 逻辑状态 | 映射资产状态 | 含义 |
|---|---|---|
| `brand_token_candidate` | `brand_kit` 或 `uploaded` | 已上传但未确认的品牌 token 候选 |
| `brand_token_approved` | `brand_kit` | 可进入生产 bundle 的品牌 token |
| `job_artifact` | `intermediate` | 由 MediaJobRecord 管理的中间产物 |
| `deliverable_manifest` | `final_work` | 成片、海报、字幕、C2PA、审计报告的交付清单 |

规则：

- 逻辑状态不必立即改数据库枚举。
- UI 可先通过 metadata 展示 token 审核状态。
- 原始品牌视频和 token 结果必须保留 provenance 关联。

## 7. 权利与合规边界

### 7.1 硬门槛

以下失败时禁止自动进入生产生成：

- `rights_license` 未通过。
- 素材含未授权肖像。
- voice clone 缺少 consent。
- 音乐/音效缺少 license。
- 产品功效 claim 无证据。
- S5 违反儿童可识别形象安全边界。
- S3 复制具体创作者脸、声音、独特画面，而不是学习结构。

### 7.2 软门槛

以下失败时允许生成 advisory report：

- 品牌色彩偏离。
- 字幕风格不一致。
- 镜头节奏不符合历史高表现模式。
- 音乐情绪偏离。
- 缩略图吸引力不足。

## 8. Autoresearch 接入方式

Autoresearch 不直接改 pipeline。它只产出可验证证据：

- provider capability matrix 更新建议。
- prompt compiler A/B 结果。
- brand token extraction benchmark。
- audio toolbox benchmark。
- rights/compliance red-team case。

每个研究任务必须输出：

```json
{
  "pass": false,
  "score": 0.0,
  "evidence": [],
  "recommended_contract_change": null,
  "requires_code_change": false,
  "requires_token_spend": false
}
```

只有当 `recommended_contract_change` 被人工接受后，才进入架构规格或实现 backlog。

## 9. 实施顺序

### 9.1 Phase 0：文档合约

交付物：

- 本架构规格。
- provider capability matrix 更新计划。
- brand token extraction spec。
- quality contract spec。

验收：

- S1-S5 注入点明确。
- hard/soft token 规则明确。
- provider 未知能力标记为 `unknown`。

### 9.2 Phase 1：最小 brand token 闭环

交付物：

- token schema。
- bundle builder。
- rights/license hard gate。
- brand-token-audit rubric。

验收：

- 不接真实 provider 也能完成 token 生成、筛选和审计。

### 9.3 Phase 2：compiler 与 ledger

交付物：

- storyboard schema。
- provider prompt compiler。
- media job ledger。

验收：

- 同一 shot 可编译为多个 provider prompt。
- 每个真实媒体任务有 job record。

### 9.4 Phase 3：工具箱接入

交付物：

- image toolbox。
- audio toolbox。
- presenter toolbox。
- post-production toolbox。

验收：

- 工具箱能力通过 adapter 被 S1-S5 调用。
- 工具箱输出进入统一 artifact 和 quality contract。

### 9.5 Phase 4：真实 benchmark

交付物：

- 固定测试 brief。
- 固定 brand token set。
- 固定评分表。
- 小样本真实生成报告。

验收：

- 不用“生成成功”替代“商业可用”。
- 结果同时记录质量、品牌、权利、成本、失败率。

## 10. 后续代码实现前检查

进入代码实现前必须确认：

- 当前需求仍是 S1-S5 场景不变。
- 供应商余额和真实 token 开关已明确。
- 本文 review 状态是否需要转 stable。
- 是否先修正 S2 StepRunner 边界、S4/S5 skill 显式 import、brand_guidelines 传递。
- 是否需要新增数据库表，或先用 JSON 文件/sidecar 完成最小闭环。

## 11. 验证命令建议

代码实现前后的低成本 gate：

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

S1-S5 hermetic regression 需要确保可用 Python 在 PATH 中，必要时先使用 `.venv/bin`。
