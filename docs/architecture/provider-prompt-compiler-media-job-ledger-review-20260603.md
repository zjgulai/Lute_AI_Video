---
title: Provider Prompt Compiler 与 Media Job Ledger 架构规格
doc_type: architecture
module: ai-video
topic: provider-prompt-compiler-media-job-ledger
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
  - file: ./poyo-model-matrix-stable.md
    relation: complements
  - file: ../analysis/video-generation-speed-root-cause-analysis.md
    relation: latency-reference
---

# Provider Prompt Compiler 与 Media Job Ledger 架构规格

> 状态边界：本文定义 provider-specific prompt 编译与媒体生成任务账本的 Phase 0 合约。它不表示相关代码已经实现，不改变当前模型默认值，也不授权真实 token 消耗。

## 1. 目标

当前 S1-S5 已经有视频 prompt、Seedance clips、TTS、thumbnail、assemble 等步骤，但 prompt 和媒体任务还缺少统一合约。Provider Prompt Compiler 与 Media Job Ledger 的目标是：

- 用同一份 `StoryboardShotSchema` 生成不同 provider 的专用 prompt。
- 保证 hard brand token、rights token 和 negative guardrail 不被编译阶段丢弃。
- 记录每次真实媒体任务的输入、provider、模型、成本、耗时、失败原因和 artifact。
- 支持后续 benchmark、降级、重试、复盘和成本控制。
- 把“生成成功”与“商业可用”分开记录。

## 2. 非目标

- 不在 Phase 0 接入新 provider。
- 不把 leaderboards 写成模型选择事实。
- 不直接替换 `model_router.py` 或 `model_thresholds.py`。
- 不在未刷新官方文档和供应商后台前更新生产默认模型。
- 不让 compiler 自动删减 hard token 来换取更短 prompt。

## 3. 当前项目边界

已存在能力：

- `model_router.py` 已有 S1-S5 三层模型链。
- `model_thresholds.py` 已有模型阈值。
- `poyo-model-matrix-stable.md` 记录 2026-05 的 poyo 模型快照。
- S1/S2/S3 已有并发生成基础，S4/S5 的视频生成存在串行耗时风险。
- `seedance_client` 和图像客户端已采用 submit / poll / download 模式。

缺口：

- prompt 仍以 step 内局部自然语言为主，缺少 provider-specific compiler。
- provider 能力字段没有统一结构化记录。
- 真实生成任务没有统一 ledger 合约。
- prompt hash、brand bundle、reference asset、cost、latency、failure reason 没有稳定关联。
- provider error 与业务错误没有统一分类。

## 4. 总体流程

```text
Scenario Step
  -> StoryboardShotSchema
  -> BrandConstraintBundle
  -> ProviderCapability
  -> ProviderPromptCompiler
  -> PromptCompileResult
  -> MediaJobSpec
  -> ProviderAdapter submit / poll / download
  -> MediaJobRecord
  -> ArtifactManifest
  -> QualityContract / Audit
```

规则：

- 场景 step 不直接拼 provider prompt。
- compiler 不直接调用外部 API。
- provider adapter 不理解品牌策略，只执行 job spec。
- ledger 记录必须先于真实任务提交，避免生成失败后无痕。

## 5. ProviderCapability

`ProviderCapability` 描述 provider + model 的已验证能力。

```json
{
  "capability_id": "cap_poyo_seedance_2_20260603",
  "provider": "poyo",
  "model": "seedance-2",
  "model_family": "seedance",
  "modalities": ["text_to_video", "image_to_video"],
  "supports_reference_images": true,
  "supports_reference_video": true,
  "supports_first_frame": "unknown",
  "supports_last_frame": "unknown",
  "supports_native_audio": true,
  "supports_lip_sync": "unknown",
  "supports_seed": "unknown",
  "supports_negative_prompt": "unknown",
  "supports_aspect_ratios": ["9:16", "16:9"],
  "max_duration_seconds": 15,
  "max_reference_assets": 12,
  "async_required": true,
  "retention_days": "unknown",
  "c2pa": "unknown",
  "content_filter_notes": [],
  "cost_model": {
    "unit": "unknown",
    "estimated_usd_per_job": null
  },
  "recommended_scenarios": ["s1", "s5"],
  "known_failure_modes": [],
  "last_verified_at": "2026-06-03",
  "source_urls": ["https://docs.poyo.ai/api-manual/video-series/seedance-2"]
}
```

字段规则：

- 未核实字段必须为 `unknown`，禁止推断成事实。
- `last_verified_at` 必须随真实消耗前刷新。
- `source_urls` 只放官方文档、供应商后台或项目内已验证文档。
- `cost_model` 未核实时不能用于预算承诺，只能用于估算占位。

## 6. PromptCompileInput

Compiler 的输入必须显式包含创意、品牌、provider 能力和平台目标。

```json
{
  "compile_id": "pci_s2_001_003",
  "scenario": "s2",
  "step_name": "video_prompts",
  "shot": {
    "shot_id": "s2_001_003"
  },
  "brand_bundle": {
    "bundle_id": "bcb_momcozy_s2_tiktok_en_001"
  },
  "provider_capability": {
    "capability_id": "cap_poyo_seedance_2_20260603"
  },
  "platform_target": {
    "platform": "tiktok",
    "aspect_ratio": "9:16",
    "locale": "en-US",
    "duration_seconds": 5
  },
  "compile_options": {
    "max_prompt_chars": 1800,
    "allow_native_audio": false,
    "allow_soft_token_compression": true
  }
}
```

规则：

- `shot` 必须引用完整 `StoryboardShotSchema`。
- `brand_bundle` 必须已经通过 hard token 筛选。
- `provider_capability` 必须有核实日期。
- `max_prompt_chars` 是 compiler 约束，不是删除 hard token 的理由。

## 7. PromptCompileResult

```json
{
  "compile_id": "pci_s2_001_003",
  "compiler_id": "seedance_video_prompt_compiler_v1",
  "provider": "poyo",
  "model": "seedance-2",
  "prompt": "A five-second vertical product reveal...",
  "negative_prompt": "No medical claims, no visible children...",
  "reference_asset_ids": ["asset_product_001"],
  "duration_seconds": 5,
  "aspect_ratio": "9:16",
  "provider_options": {
    "native_audio": false
  },
  "hard_token_ids": ["bat_claim_guardrail_001"],
  "soft_token_ids": ["bat_visual_identity_001"],
  "dropped_soft_token_ids": [],
  "compression_notes": [],
  "prompt_hash": "sha256:example",
  "compile_warnings": []
}
```

规则：

- `prompt_hash` 必须由 prompt、negative prompt、provider options、reference asset ids 和 hard token ids 共同生成。
- hard token 不允许进入 `dropped_soft_token_ids`。
- 如果 provider 不支持 negative prompt，compiler 必须把 hard negative constraints 合并进主 prompt，并写入 `compile_warnings`。
- `compile_warnings` 不等于失败；但 hard token 丢失必须失败。

## 8. Compiler 阶段门槛

### 8.1 Blocking

以下情况必须阻断编译：

- brand bundle 中有 expired 或非 approved hard token。
- reference asset 缺少 rights token。
- S5 shot 包含可识别儿童 face/body direct reference。
- product claim 缺少 evidence ref。
- provider capability 与输入要求冲突，例如需要 reference image，但 provider capability 为 false。
- prompt 长度超限且无法只压缩 soft token。

### 8.2 Advisory

以下情况只产生 warning：

- soft token 被压缩。
- provider 不支持 native audio，改由后期 audio toolbox 处理。
- provider 不支持 first/last frame，降级为 text/reference prompt。
- 目标时长超过 provider 推荐值，但可拆分成多个 shot。

## 9. Provider-specific 编译规则

### 9.1 Seedance / PoYo

适用：

- S1 商品直拍。
- S5 Brand VLOG。
- S4 快创。

Prompt 风格：

- 明确短片段时长。
- 明确主体、动作、镜头、场景、风格。
- 参考资产优先放在 provider payload，而不是全写进 prompt。
- 对 native audio 保持显式开关，默认由后期音频层控制。

必须保留：

- 产品外观和 product truth。
- negative guardrail。
- reference asset rights。

### 9.2 Kling

适用：

- S2 品牌战役。
- S3 remix。
- S5 备选。

Prompt 风格：

- 强化动作、角色一致性、镜头连续性。
- 对品牌 campaign 使用 visual motif 和 motion editing token。
- S3 只允许学习结构和节奏，不复制具体人物、声音或独特画面。

### 9.3 Runway

适用：

- S2 高质感品牌 shot 备选。

Prompt 风格：

- 简洁、正向、运动清晰。
- 避免过长约束堆叠。
- hard negative 不能删除；如果 provider 不支持 negative prompt，则改写为正向约束和禁止项。

### 9.4 Veo

适用：

- 短 hero shot。
- 高质量 product reveal。

Prompt 风格：

- subject / action / style / camera / composition / lens / audio intent 分层。
- 明确 4-8 秒级片段，不把它当长视频生成器。

### 9.5 Sora

适用：

- Storyboard / remix / edit 方向的高端实验。

Prompt 风格：

- 强调 timing、camera、audio intent、edit intent。
- 对 likeness、肖像和第三方素材执行更严格的 rights gate。

### 9.6 Wan / budget models

适用：

- 降级生成。
- 草稿预览。

Prompt 风格：

- 更短、更直接。
- 降低复杂镜头和多对象要求。
- quality threshold 使用预算模型阈值，但不降低 rights 和 hard token 门槛。

## 10. MediaJobSpec

`MediaJobSpec` 是 provider adapter 的唯一输入。

```json
{
  "job_id": "mj_s2_001_003_video",
  "job_type": "video_generation",
  "scenario": "s2",
  "step_name": "seedance_clips",
  "thread_id": "thread_001",
  "label": "momcozy_campaign_a",
  "provider": "poyo",
  "model": "seedance-2",
  "capability_id": "cap_poyo_seedance_2_20260603",
  "compile_id": "pci_s2_001_003",
  "prompt_hash": "sha256:example",
  "brand_bundle_id": "bcb_momcozy_s2_tiktok_en_001",
  "reference_asset_ids": ["asset_product_001"],
  "expected_outputs": [
    {
      "kind": "creation_intermediate",
      "category": "seedance",
      "media_type": "video",
      "extension": ".mp4"
    }
  ],
  "budget": {
    "max_usd": 1.5,
    "max_latency_seconds": 1500
  },
  "retry_policy": {
    "max_attempts": 2,
    "retry_on": ["rate_limit", "provider_transient", "poll_timeout_recoverable"],
    "do_not_retry_on": ["rights_blocked", "content_policy_blocked", "invalid_prompt"]
  },
  "idempotency_key": "sha256:job-input-example"
}
```

规则：

- `idempotency_key` 必须由稳定输入生成，避免重复扣费。
- `expected_outputs.kind` 必须遵守 asset lifecycle。
- `budget.max_usd` 未核实时可为空，但真实 token benchmark 前必须补齐。
- `do_not_retry_on` 优先级高于 `retry_on`。

## 11. MediaJobRecord

`MediaJobRecord` 是真实或模拟任务的账本记录。

```json
{
  "job_id": "mj_s2_001_003_video",
  "job_type": "video_generation",
  "status": "succeeded",
  "provider": "poyo",
  "model": "seedance-2",
  "provider_task_id": "external_task_id",
  "attempt": 1,
  "submitted_at": "2026-06-03T00:00:00Z",
  "started_at": "2026-06-03T00:00:05Z",
  "finished_at": "2026-06-03T00:01:02Z",
  "latency_seconds": 62,
  "poll_count": 12,
  "cost_estimated_usd": null,
  "cost_actual_usd": null,
  "artifact_ids": ["artifact_clip_001"],
  "artifact_paths": ["output/seedance/clip_001.mp4"],
  "quality_contract_id": "qc_s2_clip_v1",
  "audit_summary": {
    "blocking_pass": true,
    "advisory_score": 0.74
  },
  "error": null,
  "raw_response_ref": "private/job-responses/mj_s2_001_003_video.json"
}
```

规则：

- 任务提交前记录 `status=prepared`。
- provider 返回 task id 后记录 `status=submitted`。
- 下载完成并写入 artifact 后才允许 `status=succeeded`。
- raw response 如果含敏感字段，只能存 private ref，不能进 public artifact。
- `artifact_paths` 必须指向资产生命周期允许的目录。

## 12. Job 状态机

```text
prepared
  -> blocked
  -> submitted
  -> polling
  -> downloading
  -> succeeded
  -> audit_failed
  -> failed
  -> cancelled
```

状态含义：

| status | 含义 |
|---|---|
| `prepared` | 已生成 job spec，尚未提交 provider |
| `blocked` | rights、budget、prompt、policy 等前置阻断 |
| `submitted` | provider 已接收，已有 task id 或同步响应 |
| `polling` | 异步任务等待中 |
| `downloading` | provider 已完成，正在保存 artifact |
| `succeeded` | artifact 已保存，基础审计通过 |
| `audit_failed` | artifact 存在，但 blocking audit 失败 |
| `failed` | provider 或本地执行失败 |
| `cancelled` | 人工或系统取消 |

规则：

- `succeeded` 不代表商业可用，只代表 job 成功产出 artifact。
- 商业可用必须看 QualityContract 和 Brand Token Audit。
- `audit_failed` 的 artifact 可保留为中间证据，但不得发布。

## 13. Error Taxonomy

| error_type | 是否重试 | 含义 |
|---|---|---|
| `rights_blocked` | 否 | 授权或 consent 不通过 |
| `brand_guardrail_blocked` | 否 | hard brand token 被违反 |
| `invalid_prompt` | 否 | prompt 超限或结构非法 |
| `content_policy_blocked` | 否 | provider 内容安全拒绝 |
| `insufficient_credits` | 否 | 余额不足 |
| `rate_limit` | 是 | provider 限流 |
| `provider_transient` | 是 | provider 临时错误 |
| `poll_timeout_recoverable` | 是 | 轮询超时但 provider 任务可能仍存在 |
| `download_failed` | 是 | artifact 下载失败 |
| `artifact_validation_failed` | 否 | 文件缺失、空文件、格式错误 |
| `audit_blocking_failed` | 否 | 质量或品牌硬审计失败 |

规则：

- `insufficient_credits` 不得自动重试。
- `content_policy_blocked` 不得通过弱化 safety 约束重试。
- `rate_limit` 可按 backoff 重试，但要计入 attempt。

## 14. 成本与延迟记录

每个 job record 至少记录：

- `latency_seconds`
- `poll_count`
- `attempt`
- `model`
- `provider`
- `cost_estimated_usd`
- `cost_actual_usd`
- `budget.max_usd`
- `budget.max_latency_seconds`

聚合指标：

| 指标 | 用途 |
|---|---|
| cost per scenario | 判断 S1-S5 成本边界 |
| cost per accepted final video | 判断商业可用成本 |
| latency per clip | 定位 provider 队列和轮询瓶颈 |
| failure rate by model | 调整 model router |
| audit failure rate | 判断 prompt compiler 和 quality contract 是否有效 |

## 15. ArtifactManifest

一个 final work 不只是一条 mp4。交付清单应包含：

```json
{
  "manifest_id": "afm_s2_001_final",
  "scenario": "s2",
  "label": "momcozy_campaign_a",
  "final_video_path": "output/renders/s2_final.mp4",
  "poster_path": "output/thumbnails/s2_poster.jpg",
  "caption_paths": [],
  "source_job_ids": ["mj_s2_001_003_video"],
  "source_artifact_ids": ["artifact_clip_001"],
  "brand_bundle_ids": ["bcb_momcozy_s2_tiktok_en_001"],
  "prompt_hashes": ["sha256:example"],
  "quality_reports": [],
  "c2pa_status": "pending",
  "publish_allowed": false
}
```

规则：

- `publish_allowed=false` 是默认值。
- 只有 blocking audit 全通过后才能改为 true。
- manifest 应保存生成链路，而不是只保存最终文件路径。

## 16. Concurrency 与队列策略

当前项目已有外部 API 轮询耗时风险，因此任务层需要显式队列策略。

建议规则：

- 同一 provider 设置并发上限。
- 同一 source asset 的 reference-heavy job 限流。
- S4/S5 若需要连续性，可拆成并发组和串行依赖组。
- `first_last_frame` 依赖存在时，后一个 clip 必须等前一个 artifact 验证完成。
- 无连续依赖的 clip 可并发提交。

JobSpec 增加可选字段：

```json
{
  "queue_policy": {
    "provider_concurrency_key": "poyo:video",
    "max_concurrent": 4,
    "dependency_job_ids": [],
    "continuity_group_id": "s5_scene_001"
  }
}
```

## 17. 与 S1-S5 的首批接入点

| 场景 | step | compiler / ledger 重点 |
|---|---|---|
| S1 | `video_prompts` | 从 storyboard + product truth + visual reference 编译 prompt |
| S1 | `seedance_clips` | 记录 clip job、reference keyframe、prompt hash、成本 |
| S2 | `continuity_storyboard_grid` | 输出 campaign visual motif 到 shot schema |
| S2 | `video_prompts` | 编译品牌战役 provider prompt |
| S2 | `seedance_clips` | 对 Kling/Runway/Seedance 做可比较 job record |
| S3 | `video_analysis` / `remix_script` | 写入 rights boundary，避免复制原作者形象 |
| S3 | `seedance_clips` | ledger 必须记录 source fingerprint / consent |
| S4 | `video_prompts` | 将 live shoot footage 约束写入 shot schema |
| S4 | `seedance_clips` | 记录素材来源、串行依赖、clip 可用性 |
| S5 | `vlog_strategy` | 输出 persona / scene / safety token |
| S5 | `seedance_clips` | 记录 continuity group、last-frame dependency、儿童安全 hard gate |

Phase 1 接入顺序：

1. S1/S2 的 compiler 合约。
2. S1/S2 的 media job record。
3. S5 的 safety-aware compiler。
4. S4/S5 的 queue policy。
5. S3 的 rights-aware ledger。

## 18. Benchmark 记录

真实 token benchmark 必须固定：

- scenario。
- input brief。
- brand bundle。
- storyboard shot。
- provider capability snapshot。
- model。
- prompt hash。
- evaluator。

Benchmark 输出：

```json
{
  "benchmark_id": "bench_s2_provider_prompt_001",
  "scenario": "s2",
  "provider": "poyo",
  "model": "seedance-2",
  "prompt_hash": "sha256:example",
  "job_id": "mj_s2_001_003_video",
  "quality_score": 0.0,
  "brand_alignment_score": 0.0,
  "rights_pass": false,
  "cost_actual_usd": null,
  "latency_seconds": 0,
  "accepted_for_delivery": false,
  "notes": []
}
```

规则：

- 同一个 benchmark 不允许中途换 brand bundle。
- 同一个 provider 对比必须使用同一 shot schema。
- accepted_for_delivery 必须由 audit 决定，不由生成是否成功决定。

## 19. 无 token 验证计划

充值前只做离线验证：

- 同一 `StoryboardShotSchema` 编译出 Seedance / Runway / Veo 风格的 prompt mock。
- hard negative token 不会被丢弃。
- soft token 超量时可压缩，并记录 `dropped_soft_token_ids`。
- `ProviderCapability` 为 `unknown` 的字段不会被当作 true 使用。
- `MediaJobSpec` 能在不提交 provider 的情况下生成 `prepared` record。
- rights blocked case 能生成 `blocked` record。
- insufficient credits 不进入 retry。

验收样例：

| case | 预期 |
|---|---|
| provider 不支持 negative prompt | hard negative 被合并进主 prompt，并写 warning |
| prompt 超长 | 只压缩 soft token；hard token 仍保留 |
| reference asset 无 rights | compile blocking fail |
| S5 儿童 direct reference | compile blocking fail |
| 余额不足 | job failed，error_type=`insufficient_credits`，不重试 |
| provider 限流 | job failed 或 retry，error_type=`rate_limit`，记录 attempt |

## 20. Phase 2 验收标准

Phase 2 完成时必须满足：

- 有 `ProviderCapability` schema。
- 有 `PromptCompileInput` 和 `PromptCompileResult` schema。
- 有 provider-specific compiler 规则。
- 有 `MediaJobSpec` 和 `MediaJobRecord` schema。
- 有 job 状态机和 error taxonomy。
- 有成本、延迟、prompt hash、artifact manifest 记录规则。
- 有无 token 离线验收用例。

不要求：

- 接入所有 provider。
- 完成 UI。
- 完成真实 token benchmark。
- 更改生产默认模型。
- 替换现有 poyo model matrix。
