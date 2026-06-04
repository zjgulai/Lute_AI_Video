---
title: Brand Asset Token 最小闭环架构规格
doc_type: architecture
module: ai-video
topic: brand-asset-token
status: review
created: 2026-06-03
updated: 2026-06-03
owner: self
source: human+ai
related:
  - file: ./ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: specializes
  - file: ../design/asset-lifecycle-state-machine.md
    relation: maps-to
  - file: ../product/brand-asset-template.md
    relation: operational-input
  - file: ../workflows/brand-data-asset-directory-intake-review-20260603.md
    relation: operationalized-by
---

# Brand Asset Token 最小闭环架构规格

> 状态边界：本文定义品牌资产进入 S1-S5 生产链路前的 token 化、审核、注入和审计最小闭环。它是架构规格，不表示相关代码已经实现，也不改变现有资产五态定义。

## 1. 目标

Brand Asset Token 的目标不是保存更多品牌资料，而是把品牌资料转成可执行约束：

- 可检索：按品牌、场景、平台、步骤取用。
- 可注入：进入 strategy、script、storyboard、prompt、audio、thumbnail、assemble、audit。
- 可审计：能解释某个输出是否符合品牌、授权、平台和产品事实。
- 可回滚：错误 token 可以禁用，不污染已审核 token 池。
- 可追踪：每个 token 都能回到原始资产、抽取方式、审核记录和适用范围。

## 2. 非目标

- 不把原始品牌视频直接作为所有模型的 reference。
- 不把 Brand Asset Token 设计成新的文件资产状态。
- 不在 Phase 1 强制引入 pgvector。
- 不让 token 绕过素材授权、肖像授权、音乐授权或产品 claim 证据。
- 不用历史表现数据自动覆盖品牌安全约束。

## 3. 与现有资产状态机的关系

现有资产状态机保持五态：

- `brand_kit`
- `uploaded`
- `intermediate`
- `final_work`
- `published`

Brand Asset Token 是这些资产之上的逻辑约束层，不新增文件状态。

| token 逻辑阶段 | 对应资产状态 | 含义 |
|---|---|---|
| `candidate` | `brand_kit` / `uploaded` | 已从品牌资产抽取，但未审核 |
| `review` | `brand_kit` / `uploaded` | 待人工确认适用范围和权利 |
| `approved` | `brand_kit` | 可进入 BrandConstraintBundle |
| `rejected` | `brand_kit` / `uploaded` | 保留记录，但不得进入 bundle |
| `deprecated` | `brand_kit` | 历史可追踪，不再用于新生成 |
| `expired` | `brand_kit` | 授权过期，不得用于生产 |

规则：

- `approved` token 才能进入生产生成。
- `candidate` token 只能用于离线预览和人工审核。
- `expired` token 不能被 prompt compiler 读取。
- token 状态不改变原始文件状态；原始文件仍按资产状态机管理。

## 4. 最小闭环流程

```text
brand asset intake
  -> source classification
  -> rights / pii pre-check
  -> token extraction
  -> candidate token set
  -> human review
  -> approved token pool
  -> bundle builder
  -> S1-S5 injection
  -> brand / rights / quality audit
  -> feedback to token pool
```

### 4.1 Intake

输入可以来自：

- 品牌视频。
- Logo、色板、字体、品牌书。
- 产品图、场景图、操作视频。
- 产品规格、USP、FAQ、合规词表。
- 历史高表现视频和低表现视频。
- UGC / KOL 授权素材。

Intake 必须记录：

- 来源。
- 上传人或来源系统。
- 授权状态。
- 地域。
- 有效期。
- 是否含人物、声音、儿童、第三方品牌、音乐。
- 是否可用于训练、参考、生成、发布。

### 4.2 Rights / PII Pre-check

进入抽取前先做硬检查：

| 检查项 | 失败处理 |
|---|---|
| 未知授权 | 只能生成 `candidate`，不得进入 `approved` |
| 肖像未授权 | 禁止生成 `visual_reference` hard token |
| voice clone 未授权 | 禁止生成 voice token |
| 音乐/音效未知授权 | 禁止生成 music / SFX token |
| 第三方品牌露出 | 标记 copyright risk，不进入 hard reference |
| 儿童可识别形象 | S5 只允许抽象 persona，不允许可识别 reference |

### 4.3 Token Extraction

抽取分两类：

- rule-based extraction：从结构化表单、品牌 brief、产品规格中直接抽取。
- analysis-based extraction：从视频、图片、历史表现中抽取镜头、节奏、色彩、构图和语气。

Phase 1 默认使用 rule-based extraction；analysis-based extraction 进入 review，不直接自动 approved。

### 4.4 Human Review

人工审核不只是“通过/不通过”，必须确认：

- token 类型是否正确。
- hard / soft 强度是否正确。
- 场景范围是否正确。
- 平台范围是否正确。
- 过期时间和地域是否正确。
- 是否需要写入 negative guardrail。

### 4.5 Bundle Build

运行时按以下顺序构建 BrandConstraintBundle：

1. 按 `brand_id` 过滤。
2. 排除非 `approved` token。
3. 排除 expired token。
4. 先加载 `rights_license` 和 `negative_guardrail`。
5. 按 `scenario_scope`、`step_scope`、`platform_scope` 筛选。
6. 按 `priority` 和 `strength` 排序。
7. 输出 hard token、soft token 和来源 token id。

### 4.6 Injection

BrandConstraintBundle 不能只注入 prompt。它必须注入：

- strategy：选题、目标人群、核心信息。
- script：语气、claim、禁用表达。
- storyboard：镜头语言、构图、产品露出。
- video prompt：视觉、动作、负向约束。
- audio：声音、音乐、节奏、禁用声音。
- thumbnail：品牌色、CTA、字幕安全区。
- assemble：片头片尾、字幕、比例、C2PA。
- audit：品牌一致性、授权、claim、平台合规。

## 5. 核心对象

### 5.1 BrandAssetSource

`BrandAssetSource` 描述 token 的来源资产。

```json
{
  "source_asset_id": "asset_brand_video_001",
  "brand_id": "momcozy",
  "asset_state": "brand_kit",
  "asset_kind": "brand_video",
  "source_path": "brand/videos/momcozy-tone-sample.mp4",
  "media_type": "video",
  "uploaded_at": "2026-06-03T00:00:00Z",
  "source_owner": "self",
  "rights": {
    "license_status": "approved",
    "territory": ["US"],
    "expires_at": null,
    "allowed_uses": ["reference", "generation", "publishing"],
    "consent_required": false,
    "consent_ref": null
  },
  "risk_flags": {
    "pii": false,
    "minor_visible": false,
    "third_party_brand": false,
    "third_party_music": false,
    "medical_claim": false
  }
}
```

规则：

- `source_asset_id` 必须稳定。
- `allowed_uses` 必须明确，不允许默认全开。
- `risk_flags` 为 true 时，不能自动 approved。

### 5.2 BrandAssetToken

```json
{
  "token_id": "bat_momcozy_visual_identity_001",
  "brand_id": "momcozy",
  "source_asset_id": "asset_brand_video_001",
  "token_type": "visual_identity",
  "status": "review",
  "strength": "soft",
  "priority": 80,
  "payload": {
    "color_palette": ["warm white", "muted rose", "soft gray"],
    "lighting": "soft natural household",
    "composition": "clean product-centered close-up"
  },
  "scenario_scope": ["s1", "s2", "s5"],
  "step_scope": ["storyboard", "video_prompts", "thumbnail_prompts", "audit"],
  "platform_scope": ["tiktok", "youtube_shorts", "shopify"],
  "locale_scope": ["en-US"],
  "rights_ref": "asset_brand_video_001:rights",
  "review": {
    "review_status": "pending",
    "reviewed_by": null,
    "reviewed_at": null,
    "review_notes": null
  },
  "provenance": {
    "extraction_method": "analysis-assisted",
    "extracted_at": "2026-06-03T00:00:00Z",
    "extractor_version": "spec-only"
  }
}
```

字段规则：

- `status=approved` 必须有 `reviewed_by` 和 `reviewed_at`。
- `strength=hard` 的 token 必须有明确失败后果。
- `payload` 必须是结构化对象，禁止只写长段自然语言。
- `rights_ref` 必须能回到来源资产。

### 5.3 BrandTokenReview

```json
{
  "review_id": "btr_001",
  "token_id": "bat_momcozy_visual_identity_001",
  "decision": "approved",
  "reviewed_by": "self",
  "reviewed_at": "2026-06-03T00:00:00Z",
  "changes": {
    "status": "approved",
    "scenario_scope": ["s1", "s2", "s5"],
    "strength": "soft"
  },
  "notes": "视觉调性可用于品牌和商品展示，但不作为强制参考图。"
}
```

规则：

- 审核记录 append-only。
- 修改 token 关键字段时必须生成新 review 记录。
- 被 rejected 的 token 不删除，保留作为反例。

### 5.4 BrandConstraintBundle

```json
{
  "bundle_id": "bcb_momcozy_s2_tiktok_en_001",
  "brand_id": "momcozy",
  "scenario": "s2",
  "step_name": "video_prompts",
  "platform": "tiktok",
  "locale": "en-US",
  "hard_constraints": {
    "rights_license": [],
    "negative_guardrails": [],
    "claim_rules": []
  },
  "soft_constraints": {
    "visual_identity": [],
    "tone_voice": [],
    "motion_editing": [],
    "caption_style": []
  },
  "asset_refs": [],
  "audit_rubric": [],
  "source_token_ids": [],
  "excluded_token_ids": []
}
```

规则：

- `excluded_token_ids` 要记录为什么排除。
- hard constraints 为空时，不能默认通过；必须说明该 step 不需要。
- bundle builder 不做创意生成，只做筛选、压缩和排序。

## 6. Token 类型细则

### 6.1 `visual_identity`

用途：

- 画面质感。
- 色彩。
- 构图。
- 光线。
- 产品摆放。

示例 payload：

```json
{
  "color_palette": ["warm white", "muted rose", "soft gray"],
  "lighting": "soft natural household",
  "surface_material": "clean matte countertop",
  "composition": "product centered, low clutter",
  "avoid": ["harsh neon", "clinical blue cast", "busy discount layout"]
}
```

### 6.2 `tone_voice`

用途：

- 脚本语言。
- CTA。
- 字幕文案。
- 多语言本地化。

示例 payload：

```json
{
  "voice": ["warm", "empowering", "practical"],
  "say": ["hands-free", "quiet routine", "built for real days"],
  "avoid": ["miracle cure", "perfect motherhood", "fear-based pressure"],
  "sentence_style": "short, direct, supportive"
}
```

### 6.3 `product_truth`

用途：

- 产品事实。
- 规格。
- 功效边界。
- 禁用 claim。

默认 hard。

示例 payload：

```json
{
  "allowed_claims": [
    {
      "claim": "hands-free pumping",
      "evidence_ref": "product_spec_001"
    }
  ],
  "forbidden_claims": [
    "guaranteed more milk",
    "medical treatment",
    "pain-free for everyone"
  ],
  "required_disclaimers": []
}
```

### 6.4 `visual_reference`

用途：

- 产品外观参考。
- 场景参考。
- 手部操作参考。

规则：

- 含真实人物或儿童时默认 hard review。
- 可作为 reference asset，但不能默认允许训练或二次发布。
- 第三方品牌可见时不得作为 hard reference。

### 6.5 `motion_editing`

用途：

- 剪辑节奏。
- 转场。
- 镜头运动。
- 平台节奏。

示例 payload：

```json
{
  "pace": "calm but concise",
  "shot_duration_range_seconds": [2, 5],
  "transitions": ["hard cut", "soft dissolve"],
  "camera_motion": ["slow push-in", "static close-up"],
  "avoid": ["hyperactive zoom spam"]
}
```

### 6.6 `caption_style`

用途：

- 字幕位置。
- 字号。
- 语气。
- CTA 格式。

规则：

- 必须兼容 safe-zone。
- 平台字幕规则优先于品牌偏好。

### 6.7 `persona_audience`

用途：

- 目标用户。
- 使用场景。
- 角色抽象。

S5 规则：

- 可描述 caregiver、parent、family routine。
- 不生成可识别儿童脸部或身体 reference。

### 6.8 `platform_compliance`

用途：

- TikTok、YouTube Shorts、Meta、Shopify 的平台边界。

默认 hard。

### 6.9 `rights_license`

用途：

- 授权状态。
- 地域。
- 有效期。
- 允许用途。

默认 hard。没有 rights token 的资产不能作为生产 reference。

### 6.10 `negative_guardrail`

用途：

- 禁止画面。
- 禁止表述。
- 儿童安全。
- 肖像安全。
- 医疗/健康 claim 安全。

默认 hard。

### 6.11 `performance_signal`

用途：

- 历史高表现 hook。
- 封面模式。
- 节奏模式。
- CTA 模式。

规则：

- 只能影响排序和建议。
- 不得覆盖 hard guardrail。

## 7. 首批场景注入点

### 7.1 S1 Product Direct

首批注入：

| step | token |
|---|---|
| `strategy` | `product_truth`, `persona_audience`, `performance_signal` |
| `scripts` | `tone_voice`, `product_truth`, `negative_guardrail` |
| `storyboards` | `visual_identity`, `visual_reference`, `caption_style` |
| `video_prompts` | `visual_identity`, `visual_reference`, `negative_guardrail` |
| `thumbnail_prompts` | `visual_identity`, `caption_style`, `performance_signal` |
| `assemble_final` | `caption_style`, `platform_compliance`, `rights_license` |
| `audit` | `product_truth`, `rights_license`, `negative_guardrail` |

### 7.2 S2 Brand Campaign

首批注入：

| step | token |
|---|---|
| `strategy` | `tone_voice`, `persona_audience`, `performance_signal` |
| `scripts` | `tone_voice`, `product_truth`, `negative_guardrail` |
| `continuity_storyboard_grid` | `visual_identity`, `motion_editing`, `caption_style` |
| `video_prompts` | `visual_identity`, `motion_editing`, `visual_reference` |
| `thumbnail_prompts` | `visual_identity`, `caption_style`, `performance_signal` |
| `assemble_final` | `caption_style`, `platform_compliance`, `rights_license` |
| `audit` | `tone_voice`, `visual_identity`, `rights_license`, `product_truth` |

### 7.3 S5 Brand VLOG

首批注入：

| step | token |
|---|---|
| `vlog_strategy` | `persona_audience`, `tone_voice`, `negative_guardrail` |
| `continuity_storyboard_grid` | `visual_identity`, `motion_editing`, `persona_audience` |
| `video_prompts` | `visual_identity`, `negative_guardrail`, `visual_reference` |
| `seedance_clips` | `rights_license`, `negative_guardrail` |
| `tts_audio` | `tone_voice`, `rights_license` |
| `assemble_final` | `caption_style`, `platform_compliance`, `rights_license` |
| `audit` | `negative_guardrail`, `persona_audience`, `visual_identity`, `product_truth` |

S5 hard guardrail：

- 不生成可识别儿童面部。
- 不生成可识别儿童全身。
- 不把真实儿童视频作为 direct visual reference。
- 只允许生活方式场景的抽象表达。

### 7.4 S3 / S4 延后策略

S3 和 S4 风险更高，Phase 1 不做深度注入，只做 hard gate：

- S3：`rights_license`、`negative_guardrail`、`platform_compliance`。
- S4：`rights_license`、`caption_style`、`platform_compliance`。

原因：

- S3 remix 涉及版权、肖像、风格边界。
- S4 live shoot 涉及真实素材质量、人物授权、环境音和平台安全。

## 8. 审计规则

### 8.1 Brand Token Audit

输出字段：

```json
{
  "brand_voice_alignment": 0.0,
  "visual_identity_alignment": 0.0,
  "constraint_coverage": 0.0,
  "hard_token_pass": false,
  "negative_token_violations": [],
  "claim_substantiation_pass": false,
  "rights_pass": false,
  "prompt_brand_drift": [],
  "render_brand_presence": [],
  "recommendations": []
}
```

### 8.2 Blocking Checks

以下失败即不可交付：

- `rights_pass=false`
- `hard_token_pass=false`
- `claim_substantiation_pass=false`
- 出现未授权肖像、声音、音乐或第三方品牌。
- S5 出现儿童可识别形象。

### 8.3 Advisory Checks

以下只生成改进建议：

- `brand_voice_alignment` 低于阈值。
- `visual_identity_alignment` 低于阈值。
- `constraint_coverage` 不完整。
- `performance_signal` 未命中。

## 9. 存储策略

Phase 1 优先不做重数据库设计。

推荐演进：

1. 规则和 schema 先在架构文档固化。
2. 最小实现可使用 JSON sidecar 或现有 brand package metadata。
3. 稳定后进入 PostgreSQL JSONB。
4. 只有当 token 检索需要语义相似度时再引入 pgvector。

禁止：

- 把 token 混入临时输出目录。
- 把候选 token 当作正式品牌资产。
- 把未经审核 token 写入生产默认 bundle。

## 10. 文件与命名建议

后续如果需要落盘样例，按状态选择位置：

| 内容 | 位置 |
|---|---|
| token schema 文档 | `docs/architecture/` |
| 品牌资产收集表 | `docs/product/` 或 `drafts/docs/` |
| 未确认抽取结果 | `drafts/analysis/` |
| 一次性抽取输出 | `tmp/outputs/` |
| 过期但有参考价值的 token 样例 | `archive/docs/` |

Markdown 正式文档必须有 frontmatter。

## 11. 无 token 验证计划

充值前只做离线验证：

- 用人工编写的品牌输入样例生成 candidate token。
- 检查 rights pre-check 是否阻止未知授权。
- 检查 hard token 是否被 bundle builder 保留。
- 检查 S1/S2/S5 注入矩阵是否完整。
- 检查 audit rubric 是否能发现 hard token violation。

建议验收用例：

| case | 预期 |
|---|---|
| 缺少授权的品牌视频 | 只生成 candidate，不进入 approved |
| 含儿童可识别画面的素材 | S5 direct reference 被阻断 |
| 产品 claim 无证据 | `product_truth` audit blocking fail |
| soft 视觉偏好过多 | bundle builder 压缩但保留 source token ids |
| hard negative guardrail | prompt compiler 不得丢弃 |

## 12. Phase 1 验收标准

Phase 1 完成时必须满足：

- 有稳定 token schema。
- 有 token 状态流转规则。
- 有 rights / PII pre-check 规则。
- 有 S1/S2/S5 首批注入矩阵。
- 有 BrandConstraintBundle 生成规则。
- 有 blocking / advisory audit 区分。
- 有无 token 离线验收用例。

不要求：

- 接真实 provider。
- 消耗 POYO token。
- 完成 UI。
- 完成 pgvector。
- 完成所有 S3/S4 深度注入。
