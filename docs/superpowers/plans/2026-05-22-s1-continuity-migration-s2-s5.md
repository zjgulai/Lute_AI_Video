---
title: S1 连续分镜能力向 S2-S5 迁移完成报告与后续计划
doc_type: workflow
module: ai-video
topic: continuity-storyboard-migration
status: stable
created: 2026-05-22
updated: 2026-05-22
owner: self
source: human+ai
---

# S1 连续分镜能力向 S2-S5 迁移 — 完成报告与后续计划

## 一、今日完成项

### 1.1 共享抽象层提取

- **新建** `src/pipeline/continuity_utils.py` — 8 个共享函数
  - `normalize_continuity_config()` — 标准化连续性配置
  - `extract_clip_last_frame()` — ffmpeg 提取末帧
  - `build_transitions_from_clip_details()` — 提取 Remotion transitions
  - `build_continuity_audit_summary()` — 泛化审核拆分（支持 continuity_grid=None）
  - `collect_shots()` / `collect_captions()` — 通用 shot/caption 收集
  - `compute_expected_duration()` — 预期时长计算
  - `all_clips_are_stubs()` — 统一 stub 检测
- **测试** `tests/test_continuity_utils.py` — 24 个单元测试全部通过

### 1.2 场景后端适配

| 场景 | 变更 | 状态 |
|------|------|------|
| **S3** | `continuity_storyboard_grid` step 接入、transition metadata、Remotion transitions、audit 拆分 | 代码完成 |
| **S4** | `continuity_storyboard_grid` step 接入（scripts → clip_groups fallback）、transition metadata、Remotion transitions、audit 拆分 | E2E 6/6 通过 |
| **S5** | `vlog_shots_to_clip_groups()`、transition metadata、Remotion transitions、audit 拆分 | 代码完成 |

### 1.3 前端配置

- `web/src/components/SceneForm.tsx` 中 S2/S3/S5 添加 `continuity_mode` 配置
- S1 已有，S4 在 SceneForm 中无独立表单块（已知缺口）

### 1.4 POYO 模型 ID 全量修正

| 模型 | 旧 ID | 新 ID | API 验证 |
|------|-------|-------|---------|
| Kling 3.0 standard | `kling-3-0/standard` | `kling-3.0/standard` | 200 OK |
| Kling 3.0 pro | `kling-3-0/pro` | `kling-3.0/pro` | 200 OK |
| Kling 3.0 4k | `kling-3-0/4k` | `kling-3.0/4k` | 200 OK |
| Kling 2.5 turbo-pro | `kling-2-5-turbo-pro` | `kling-2.5-turbo-pro` | 200 OK |
| Kling 2.6 | `kling-2-6` | `kling-2.6` | 200 OK |
| Kling o3 standard | `kling-o3` | `kling-o3/standard` | 200 OK |
| Kling o3 4k | `kling-o3-4k` | `kling-o3/4k` | 200 OK |
| Wan 2.7 | `wan-2-7-video` | `wan2.7-text-to-video` | 200 OK |
| Wan 2.6 | `wan-2-6` | `wan2.6-text-to-video` | 200 OK |
| Wan 2.5 | `wan-2-5` | `wan2.5-text-to-video` | 200 OK |
| Runway Gen-4.5 | `runway-gen-4-5` | `runway-gen-4.5` | 200 OK |
| Hailuo 2.3 | `hailuo-2-3` | `hailuo-2.3` | 200 OK |
| Seedance 2 | `seedance-2` | `seedance-2` | 200 OK |

### 1.5 参数适配修复

- **Kling 模型**：`seedance_client.py` 自动注入 `sound: True`
- **Wan 模型**：自动使用像素格式 `1080*1920` 替代 `9:16`
- **Hailuo 模型**：自动限制 duration 为 6/10，resolution 为 768p/1080p

### 1.6 审计中发现并修复的问题

- **S2 `run_step` 缺失**：`S2BrandCampaignPipeline` 添加 `run_step` 委托给 `S1ProductDirectPipeline`
- **`kling-2-1` 陈旧阈值**：从 `model_thresholds.py` 删除
- **S2 E2E 模型断言**：测试更新为 `kling-3.0/pro`
- **S5 E2E audit mock**：`_fake_audit` 签名添加 `clip_details` 和 `continuity_grid`

---

## 二、未完成项（阻塞与计划）

### P0 — S3 E2E 全量验证（POYO 余额阻塞）

**状态**：代码完成，等待 API 配额
**阻塞原因**：POYO 账户返回 402 "Your credits are insufficient"
**验证路径**：

```bash
PYTHONPATH=. uv run --extra dev pytest tests/test_s3_e2e.py -q --tb=short
```

**预期结果**：
- `steps.continuity_storyboard_grid.output.clip_groups` 存在
- `clip_details` 含 `transition_to_next`
- `audit.asset_ready_audit` 存在
- `assemble.transitions` 非空

**解除阻塞条件**：POYO 账户充值后重跑

### P1 — S4 前端 `continuity_mode` 配置

**状态**：后端完成，前端无独立表单块
**说明**：S4 (`live_shoot`) 在 `SceneForm.tsx` 中没有独立的场景配置块。当前 S4 的 `run()` 方法通过 `StepRunner` 执行，但前端无法配置 `continuity_mode`。
**方案**：在 SceneForm.tsx 中添加 S4 配置块，或复用 S1 的配置组件。
**优先级**：低（S4 当前使用率低）

### P2 — `continuity_storyboard_grid` skill 品牌适配

**状态**：S2 硬编码了 bottle warmer 的 12 个 micro_shots
**说明**：`src/skills/continuity_storyboard_grid.py` 当前硬编码 bottle warmer 案例。当 `brand_mode=True`（S2 场景）时，micro_shots 与品牌内容不匹配。
**方案**：
1. skill 接收 `brand_mode` 参数
2. 当 `brand_mode=True` 时，通过 LLM 生成品牌相关的 micro_shots
3. `clip_groups` 的 `seedance_prompt` 中注入品牌元素
**优先级**：中（S2 使用 Kling 3.0 pro，对分镜质量要求高）

### P3 — 生产部署验证

**状态**：代码未部署
**验证清单**：

| 场景 | 验证项 |
|------|--------|
| S1 | `steps.continuity_storyboard_grid.output.clip_groups` 存在 |
| S2 | 同上 + `clip_groups[0].seedance_prompt` 含品牌名 |
| S3 | `steps.continuity_storyboard_grid` 存在；`clip_details` 含 `transition_to_next` |
| S4 | `steps.continuity_storyboard_grid` 存在；`continuity_frame_used` 在 clip N+1 中指向 clip N 末帧 |
| S5 | `steps.continuity_storyboard_grid` 存在；`clip_details` 含 `transition_to_next` |

---

## 三、修改文件清单

**核心代码**：
- `src/pipeline/continuity_utils.py`（新建）
- `src/pipeline/s3_remix_pipeline.py`
- `src/pipeline/s4_live_shoot_pipeline.py`
- `src/pipeline/s5_brand_vlog_pipeline.py`
- `src/pipeline/s1_product_pipeline.py`
- `src/pipeline/s2_brand_pipeline_v2.py`
- `src/pipeline/step_runner.py`
- `src/pipeline/model_router.py`
- `src/pipeline/model_thresholds.py`
- `src/tools/seedance_client.py`
- `src/routers/_state.py`

**前端**：
- `web/src/components/SceneForm.tsx`

**测试**：
- `tests/test_continuity_utils.py`（新建）
- `tests/test_s2_e2e.py`
- `tests/test_s5_e2e.py`

**文档**：
- `docs/architecture/poyo-model-matrix-stable.md`
- `docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md`
- `docs/workflows/2026-05-15-sprint-0-3-review-and-deploy-plan.md`
- `docs/release/v0.4.0.md`

---

## 四、测试验证矩阵

| 测试 | 当前结果 | 阻塞 |
|------|---------|------|
| `test_continuity_utils.py` (24) | ✅ 24/24 | 无 |
| `test_s1_continuity_pipeline.py` (33) | ✅ 33/33 | 无 |
| `test_s4_e2e.py` (6) | ✅ 6/6 | 无 |
| `test_s1_e2e.py` (10) | ⚠️ 8/10 | LLM 不稳定（已有） |
| `test_s2_e2e.py` (10) | ✅ 10/10 | 无 |
| `test_s5_e2e.py` (11) | ✅ 11/11 | 无 |
| `test_s3_e2e.py` (12) | ⏳ 待重跑 | POYO 余额不足 |

---

## 五、回滚方案

若生产部署后出现 regression：

1. **model_router.py 回滚**：将 `kling-3.0/*` 改回 `kling-3-0/*`（但 POYO 已不接受旧格式，回滚会导致 404）
2. **seedance_client.py 回滚**：移除 sound/aspect_ratio/hailuo 参数适配（会导致 Kling 400、Wan 400、Hailuo 400）
3. **实际可回滚项**：`continuity_utils.py` 的引用可从各 pipeline 移除，恢复本地重复方法

**注意**：模型 ID 修正和参数适配是**不可逆**的修复（POYO API 已变更），不应回滚。
