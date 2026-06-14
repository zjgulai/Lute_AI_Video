---
title: Quality Contract 与 Brand/Rights Audit Gate 架构规格
doc_type: architecture
module: ai-video
topic: quality-contract-brand-rights-audit
status: review
created: 2026-06-03
updated: 2026-06-03
owner: self
source: human+ai
related:
  - file: ./ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: specializes
  - file: ./brand-asset-token-contract-review-20260603.md
    relation: consumes
  - file: ./provider-prompt-compiler-media-job-ledger-review-20260603.md
    relation: consumes
  - file: ./quality-score-feedback-loop-2026-05-15.md
    relation: complements
---

# Quality Contract 与 Brand/Rights Audit Gate 架构规格

> 状态边界：本文定义“商业可交付”判定合约。它不表示相关代码已经实现，不改变当前 S1-S5 场景，也不授权真实 provider 调用。

## 1. 目标

当前项目已经能生成视频 artifact，也有 `media-quality-audit-skill`、`src/quality/` 和上游 `feedback_gate.py`。但这些能力尚未统一回答一个问题：

> 这条视频是否可以作为商业品牌内容交付或发布？

`QualityContract` 的目标是把以下判断统一成可执行 gate：

- 媒体技术质量是否合格。
- 品牌调性是否符合 Brand Asset Token。
- 产品事实和 claim 是否有证据。
- 素材、肖像、声音、音乐、第三方内容是否有权利基础。
- 平台安全区、字幕、比例、C2PA/provenance 是否满足交付要求。
- S3 remix 与 S5 children safety 是否触发硬阻断。

核心原则：

- `job succeeded` 不等于 `delivery accepted`。
- `overall_score` 不得掩盖 blocking failure。
- hard gate 失败时，不得自动发布或标记可交付。
- advisory failure 只能生成优化建议，不能伪装成阻断。

## 2. 非目标

- 不替换现有 `media-quality-audit-skill`。
- 不替换 Expert Studio gate 的人工选择流程。
- 不把所有质量指标压成一个分数。
- 不用视觉质量分数覆盖权利或合规失败。
- 不在无 token 阶段运行真实视觉模型或 provider 调用。

## 3. 概念分层

```text
Generation Quality
  技术产出是否存在、可播放、规格正确

Creative Quality
  分镜、画面、声音、字幕、节奏是否达到内容标准

Brand Quality
  是否符合品牌 token、语气、视觉、产品事实

Rights Quality
  是否拥有素材、肖像、声音、音乐、第三方内容的使用权

Platform Quality
  是否符合平台安全区、比例、禁用内容和发布边界

Delivery Quality
  是否具备最终交付清单、C2PA/provenance、审计记录和发布许可
```

规则：

- 前五层任一 hard gate 失败，Delivery Quality 必须失败。
- advisory score 可以影响排序、重生成建议和人工 review 优先级。
- Delivery Quality 才能决定 `publish_allowed`。

## 4. QualityContract

`QualityContract` 是场景、阶段、平台、品牌组合下的交付门槛。

```json
{
  "contract_id": "qc_s2_final_tiktok_v1",
  "scenario": "s2",
  "stage": "final_video",
  "platform": "tiktok",
  "brand_id": "momcozy",
  "locale": "en-US",
  "blocking_checks": [
    "media_file_exists",
    "rights_pass",
    "hard_brand_token_pass",
    "claim_substantiation_pass",
    "platform_policy_pass",
    "artifact_manifest_complete"
  ],
  "advisory_checks": [
    "visual_quality_score",
    "audio_mix_score",
    "brand_voice_alignment",
    "visual_identity_alignment",
    "safe_zone_score",
    "caption_quality_score",
    "viral_prediction_score"
  ],
  "thresholds": {
    "visual_quality_score": 0.65,
    "audio_mix_score": 0.65,
    "brand_voice_alignment": 0.72,
    "visual_identity_alignment": 0.70,
    "safe_zone_score": 0.90,
    "caption_quality_score": 0.75
  },
  "required_evidence": [
    "brand_bundle_id",
    "source_token_ids",
    "media_job_ids",
    "artifact_manifest_id",
    "rights_evidence_refs"
  ],
  "publish_policy": {
    "publish_allowed_default": false,
    "requires_human_review": true
  }
}
```

字段规则：

- `blocking_checks` 只能放 true/false 判定，不放软分数。
- `advisory_checks` 可以是分数或建议。
- `required_evidence` 缺失时，即使分数高也不能标记可交付。
- `publish_allowed_default` 必须为 false。

## 5. AuditEvidenceBundle

审计必须基于 evidence bundle，而不是直接读散落的 state 字段。

```json
{
  "evidence_bundle_id": "aeb_s2_final_001",
  "scenario": "s2",
  "stage": "final_video",
  "brand_bundle_id": "bcb_momcozy_s2_tiktok_en_001",
  "source_token_ids": [],
  "media_job_ids": [],
  "prompt_hashes": [],
  "artifact_manifest_id": "afm_s2_001_final",
  "artifact_paths": {
    "final_video": "output/renders/s2_final.mp4",
    "poster": "output/thumbnails/s2_poster.jpg",
    "captions": []
  },
  "rights_evidence_refs": [],
  "claim_evidence_refs": [],
  "platform_target": {
    "platform": "tiktok",
    "aspect_ratio": "9:16",
    "locale": "en-US"
  },
  "c2pa_status": "pending"
}
```

规则：

- 缺少 `artifact_manifest_id` 时不能进行 final delivery audit。
- 缺少 `rights_evidence_refs` 时，rights gate 默认失败。
- `prompt_hashes` 用于复盘，不用于判断质量高低。

## 6. AuditResult

```json
{
  "audit_id": "audit_s2_final_001",
  "contract_id": "qc_s2_final_tiktok_v1",
  "evidence_bundle_id": "aeb_s2_final_001",
  "blocking": {
    "pass": false,
    "failures": [
      {
        "check": "rights_pass",
        "severity": "blocker",
        "reason": "missing music license evidence",
        "evidence_ref": null
      }
    ]
  },
  "advisory": {
    "score": 0.74,
    "checks": [
      {
        "check": "brand_voice_alignment",
        "score": 0.80,
        "status": "pass",
        "recommendation": ""
      }
    ]
  },
  "delivery": {
    "accepted": false,
    "publish_allowed": false,
    "requires_human_review": true,
    "reason": "blocking checks failed"
  },
  "checked_at": "2026-06-03T00:00:00Z"
}
```

规则：

- `delivery.accepted` 必须由 blocking + required evidence 决定。
- advisory score 不得把 blocking failure 覆盖为通过。
- `requires_human_review=true` 不等于通过；只是进入人工判定。

## 7. Blocking Checks

### 7.1 通用 blocking

| check | 失败条件 |
|---|---|
| `media_file_exists` | final video 缺失、空文件、不可读 |
| `artifact_manifest_complete` | final video、poster、caption/provenance 必要清单缺失 |
| `rights_pass` | 素材、肖像、声音、音乐、第三方品牌缺少授权证据 |
| `hard_brand_token_pass` | hard brand token 被违反或被丢弃 |
| `claim_substantiation_pass` | 产品 claim 缺少 evidence ref |
| `platform_policy_pass` | 平台禁用内容或尺寸/安全区硬规则失败 |
| `c2pa_provenance_ready` | 要求 C2PA 的交付包缺少签名或 provenance 记录 |

### 7.2 S3 blocking

S3 是 remix 场景，额外 blocking：

- 未授权 creator likeness。
- 未授权原视频片段直接复用。
- 未授权声音克隆。
- 复制具体画面、脸、声音、独特表演，而不是学习结构。
- source fingerprint 缺失。

### 7.3 S5 blocking

S5 是 Brand VLOG，额外 blocking：

- 出现可识别儿童面部。
- 出现可识别儿童全身作为 direct reference。
- 使用真实儿童视频作为生成参考。
- 暗示医疗、育儿结果保证或恐惧型营销。

### 7.4 Audio blocking

音频相关 blocking：

- voice clone 缺少 consent。
- music / SFX 缺少 license。
- 音频中出现未授权第三方素材。
- 字幕与旁白内容冲突，导致 claim 失真。

## 8. Advisory Checks

| check | 含义 | 默认阈值 |
|---|---|---|
| `visual_quality_score` | 清晰度、曝光、运动稳定、画面完整度 | 0.65 |
| `clip_alignment_score` | 画面与 prompt / shot intent 对齐 | 0.65 |
| `brand_voice_alignment` | 文案语气与 tone token 对齐 | 0.72 |
| `visual_identity_alignment` | 色彩、构图、风格与 visual token 对齐 | 0.70 |
| `safe_zone_score` | 字幕/文字是否避开平台 UI | 0.90 |
| `caption_quality_score` | 字幕可读性、时序、语言一致性 | 0.75 |
| `audio_mix_score` | 旁白、音乐、环境声混音可用性 | 0.65 |
| `continuity_score` | 多 clip 的人物、场景、产品、色彩连续性 | 0.65 |
| `viral_prediction_score` | hook、节奏、封面潜力 | advisory only |

规则：

- advisory 低分不自动阻断，但必须写 recommendation。
- 当 advisory 低于阈值且真实 token 可用时，可建议 regenerate。
- 无 token 阶段只产出离线建议。

## 9. Scenario Quality Matrix

| 场景 | blocking 重点 | advisory 重点 |
|---|---|---|
| S1 | 产品事实、产品图授权、claim 证据、final media | 产品露出、缩略图、safe-zone、clip alignment |
| S2 | 品牌 hard token、claim 证据、平台政策、交付清单 | 品牌语气、视觉一致性、campaign motif |
| S3 | rights、likeness、source fingerprint、remix boundary | remix 结构质量、品牌融合度、节奏 |
| S4 | footage rights、人物授权、平台政策、素材可用性 | live shoot 节奏、字幕、supercut 完成度 |
| S5 | children safety、persona guardrail、product claim | vlog 连续性、生活方式温度、音频/字幕 |

## 10. Stage Gate Matrix

| stage | gate 类型 | 目的 |
|---|---|---|
| `pre_generation` | blocking | 在消耗 token 前阻止无授权素材、非法 claim、hard token 冲突 |
| `prompt_compile` | blocking + advisory | 确保 hard token 未丢失，provider 能力匹配 |
| `clip_generated` | advisory + selective blocking | 检查文件、时长、清晰度、内容越界 |
| `assemble_final` | blocking + advisory | final artifact、字幕、音频、poster、manifest |
| `pre_publish` | blocking | rights、platform、C2PA/provenance、human review |

规则：

- `pre_generation` 阻断优先于成本优化。
- `pre_publish` 是最后发布边界，不能因为前面通过就自动通过。
- `clip_generated` 允许保存失败 artifact 作为证据，但不能进入 final work。

## 11. 与现有能力的映射

| 现有能力 | 在 Quality Contract 中的角色 |
|---|---|
| `media-quality-audit-skill` | final media 技术/内容审计 producer |
| `src/quality/safe_zone.py` | safe-zone advisory producer |
| `src/quality/clip_alignment.py` | prompt/visual alignment producer |
| `src/quality/face_consistency.py` | identity consistency producer，S3/S5 需谨慎使用 |
| `src/quality/nr_quality.py` | no-reference visual quality producer |
| `src/quality/viral_predictor.py` | advisory performance signal producer |
| `src/pipeline/feedback_gate.py` | upstream score 消费与 regenerate 决策，不等于 delivery gate |
| `gate_manager.py` | 人工 candidate approval，不等于 rights/commercial gate |
| `c2pa_signer.py` | provenance producer |

边界：

- 现有 producer 可以进入 AuditEvidenceBundle。
- `QualityContract` 是 consumer 和裁决层，不重复实现每个检测算法。

## 12. Gate Decision

```json
{
  "decision": "blocked",
  "stage": "pre_publish",
  "scenario": "s3",
  "blocking_failures": [
    "rights_pass",
    "source_fingerprint_present"
  ],
  "advisory_score": 0.81,
  "allowed_next_actions": [
    "replace_source_asset",
    "attach_rights_evidence",
    "human_review"
  ],
  "disallowed_actions": [
    "publish",
    "auto_regenerate_with_same_source"
  ]
}
```

允许的 decision：

| decision | 含义 |
|---|---|
| `accepted` | blocking 全过，达到交付条件 |
| `accepted_with_warnings` | blocking 全过，但 advisory 有风险 |
| `human_review_required` | blocking 未失败，但证据不足或风险高 |
| `blocked` | hard failure，不得交付或发布 |
| `regenerate_recommended` | advisory 低分，建议重生成 |
| `regenerate_blocked` | 不能用同一来源重生成，需换素材或补证据 |

## 13. Evidence Retention

每次 audit 必须保留：

- `contract_id`
- `evidence_bundle_id`
- `brand_bundle_id`
- `source_token_ids`
- `media_job_ids`
- `prompt_hashes`
- `artifact_manifest_id`
- blocking failures
- advisory scores
- decision
- checked_at

规则：

- 审计记录 append-only。
- 重新生成不覆盖旧 audit，只生成新 audit。
- rejected artifact 可以保留在 intermediate 或 private evidence，不得进入 published。

## 14. 无 token 验证计划

充值前只做离线验证：

- 缺 rights evidence 的 source asset 必须被 `pre_generation` blocked。
- hard negative token 被 prompt compiler 丢弃时必须 blocked。
- final video 缺失时 `media_file_exists` blocked。
- advisory 低分不能覆盖 blocking pass/fail。
- S3 缺 source fingerprint 时 `pre_publish` blocked。
- S5 儿童 direct reference 必须 blocked。
- `job succeeded` 但 `rights_pass=false` 时 delivery accepted 必须 false。

验收用例：

| case | 预期 |
|---|---|
| final video 存在但缺音乐 license | `blocked`, `publish_allowed=false` |
| S2 视觉风格偏离但授权齐全 | `accepted_with_warnings` 或 `regenerate_recommended` |
| S1 claim 无 evidence ref | `blocked` |
| S3 remix source 无 fingerprint | `blocked` |
| S5 真实儿童 reference | `blocked` |
| safe-zone 低分 | advisory warning，不单独阻断 |

## 15. Phase 3 验收标准

Phase 3 完成时必须满足：

- 有 `QualityContract` schema。
- 有 `AuditEvidenceBundle` schema。
- 有 `AuditResult` schema。
- 有 blocking/advisory check 清单。
- 有 S1-S5 scenario matrix。
- 有 stage gate matrix。
- 有 gate decision 枚举。
- 有无 token 离线验收用例。

不要求：

- 接真实 provider。
- 完成所有视觉模型检测。
- 完成 UI。
- 完成自动 regenerate。
- 改变当前 Expert Studio 人工 gate。

## 16. 后续实现优先级

建议顺序：

1. Final artifact 的 `AuditEvidenceBundle` 聚合。
2. `rights_pass`、`hard_brand_token_pass`、`claim_substantiation_pass` 三个 blocking check。
3. S5 children safety hard gate。
4. S3 rights/source fingerprint hard gate。
5. `media-quality-audit-skill` 输出适配为 advisory producer。
6. pre-publish gate 统一输出 `publish_allowed`。
7. C2PA/provenance readiness 纳入 final manifest。
