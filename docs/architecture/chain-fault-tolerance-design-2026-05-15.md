---
name: chain-fault-tolerance-design-2026-05-15
description: 设计文档 — S3/S4/S5 三个场景的链式容错策略。当评估场景失败模式、设计 fallback 行为、决定 stub-vs-genuine 检测时使用。当前提供 1 个具体修复（partial_artifacts stub-aware）+ S3/S4 跟进 PR 路径图。
doc_type: design
module: ai-video
topic: chain-fault-tolerance
status: in-progress
created: 2026-05-15
updated: 2026-05-15
owner: Sisyphus
source: ai
related:
  - file: ../../.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md
    relation: implements-todo-13
---

# 链式容错增强 — S3/S4/S5 设计文档

> **状态**: in-progress. Sprint 4 P4-5。本文档定义三条容错路径 + 落地 1 个 partial_artifacts 增强（stub-aware）。剩 2 条（S3 viral_extractor fallback、S4 footage 降级）作为跟进 PR。

## 一、Context

诊断 R-DEGRADE-L2 + Sprint 3 P3-3 已实施 `partial_artifacts.summarize_partial_artifacts` 提取「半成品」交付物。但三个特定场景仍有静默失败路径：

| 场景 | 失败模式 | 当前行为 | 期望 |
|---|---|---|---|
| **S5** | seedance API 失败 → 20-byte stub mp4 fallback | partial_artifacts 把 stub 当作有效 clip 计入 available | partial_artifacts 检测 is_stub，归入 missing |
| **S3** | viral_extractor LLM 失败 / KOL 视频转录失败 | pipeline 整体 degraded，丢弃后续 remix_script | 用 fallback prompt 继续 remix_script，degraded reason 标 viral_extractor_failed |
| **S4** | footage 上传文件损坏 / 无效 mp4 | keyframe step 静默用空 prompt 跑 | 检测 footage 失败，用 stock footage 兜底（如有 brand_package.stock_assets）|

## 二、本 PR 范围（S5 stub-aware partial_artifacts）

### 修复位置

[src/pipeline/partial_artifacts.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/partial_artifacts.py)
的 `_step_has_output()` 当前只判 dict 非空。增加 stub 检测：

```python
def _step_has_output(step_data):
    # ... existing checks ...
    # NEW: stub-aware check for seedance_clips
    if isinstance(output, dict) and "clip_details" in output:
        details = output.get("clip_details", [])
        if details and all(d.get("is_stub", False) for d in details):
            return False  # all clips are stubs → treat as missing
    return True
```

### 影响范围

- 全 5 场景的 seedance_clips 步骤（不只 S5）—— 任何 pipeline 跑 mock 模式或 API 全失败时
- `final_state.partial_artifacts.missing_artifacts` 现在会正确列出 `seedance_clips`
- `final_state.partial_artifacts.degraded` 会因 implicit_degraded 检测翻 True
- 现存测试 `test_partial_artifacts.py` 需新增 stub case

### 不在本 PR 范围

- 修改 S3/S4/S5 pipeline 类的失败处理（按 fallback policy 设计）—— 后续 PR
- 自动重试 stub clips（用 fallback model）—— 应走 TODO-23 的 feedback_gate

## 三、跟进 PR — S3 viral_extractor fallback

### 触发条件

`src/pipeline/s3_remix_pipeline.py` 的 viral_extractor step 失败：
- LLM API 调用失败 3 次后抛
- KOL 视频转录失败（whisper not installed → mock mode 也没出 viral 片段）

### 当前行为

`step_runner` 把整个 pipeline 标 degraded，`remix_script` 不会执行。

### 期望行为

```python
# s3_remix_pipeline._step_viral_extract failure path
try:
    result = await skill.execute(params)
except Exception as exc:
    logger.warning("viral_extractor failed, using fallback prompt", error=str(exc))
    state["steps"]["viral_extractor"]["status"] = "degraded"
    state["steps"]["viral_extractor"]["output"] = {
        "viral_segments": [],
        "fallback_prompt": "Generic product remix from original creator's segment",
        "_degraded": True,
    }
    state["pipeline_degraded"] = True
    state["degraded_reason"] = "viral_extractor_failed_using_fallback"
    return state  # 继续 remix_script
```

`remix_script` skill 读 `fallback_prompt` 字段，生成低质量但可用的 remix。

工时：3-4h，包含 fallback prompt 模板设计 + 集成测试 1 case。

## 四、跟进 PR — S4 footage 降级 fallback

### 触发条件

`s4_live_shoot_pipeline._step_footage_analysis` 失败：
- 用户上传 footage 文件损坏（ffprobe 失败）
- footage_assets 列表为空（API 客户端 bug）

### 期望行为

按 `brand_package.fallback_footage` 配置：
- 如果 brand_package 有 `stock_footage_urls`：S4 用 stock footage 继续
- 没有：S4 fallback 到 S1 product_direct pipeline 跑（同一个 product_catalog）

工时：4-5h，包含 brand_package schema 字段 + 兼容性 migration。

## 五、跟进 PR — S5 stub 前置检测

### 触发条件

`s5_brand_vlog_pipeline._step_seedance_clips` 全部返回 stub mp4。

### 当前行为（已部分实现）

s5_brand_vlog_pipeline.py:120 已有 `all_seedance_clips_are_stubs` 检测，跳过 assembly + audit。但**没有**触发 `pipeline_degraded` 字段更新（partial_artifacts 通过 implicit 路径检测但不准确）。

### 期望

```python
# 在 _step_seedance_clips 后立即检查
if all(d.get("is_stub", False) for d in clip_details):
    state["pipeline_degraded"] = True
    state["degraded_reason"] = "all_seedance_clips_are_stubs"
    state["errors"].append("seedance API returned all stub clips; check POYO_API_KEY + content moderation")
```

本 PR 的 partial_artifacts stub-aware fix 给这个跟进 PR 提供检测基础。

## 六、验收标准

### 本 PR

- partial_artifacts._step_has_output 拒绝 all-stub seedance_clips
- 新增 3 case 在 test_partial_artifacts.py:
  1. seedance_clips with all is_stub=True → missing
  2. seedance_clips with mixed (1 stub + 2 real) → available (partial real clips 比无好)
  3. seedance_clips 没 clip_details 字段（向后兼容旧 state）→ 走 dict 非空 fallback

### 跟进 PR

每个跟进 PR 一个集成测试：
- S3: mock viral_extractor raise → 验证 remix_script 仍跑 + state.degraded_reason 正确
- S4: 上传 1 个 0-byte mp4 → 验证 keyframe 跑 stock footage prompt
- S5: 全 stub clips → pipeline_degraded=True + 前端 PartialArtifactsView 渲染 actionable error

## 七、风险

| 风险 | 缓解 |
|---|---|
| **mixed stub clips 怎么算？** 1 real + 2 stub → real 单挑能 assemble，但视频很短 | 当前设计：mixed 算 available。S5 已有 minimum_clips_for_assembly 检查会兜底 |
| **stub 检测误判**: 某些合法极短 clip 文件 size 接近 stub 阈值 | 不依赖 file size，只看 explicit is_stub metadata 字段。skill 自己标对自己负责 |
| **向后兼容**: 旧 PG state 没有 clip_details 字段 | _step_has_output 在 clip_details 缺失时走原 dict 非空 fallback |

## 八、相关代码

- [src/pipeline/partial_artifacts.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/partial_artifacts.py) — 本 PR 改这里
- [src/skills/seedance_video_generate.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_video_generate.py):213 — is_stub 字段定义
- [src/pipeline/s5_brand_vlog_pipeline.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/s5_brand_vlog_pipeline.py):60-66 — all_seedance_clips_are_stubs helper（已有）
- [tests/test_partial_artifacts.py](file:///Users/pray/project/hermes_evo/AI_vedio/tests/test_partial_artifacts.py) — 加 3 case 到这里
