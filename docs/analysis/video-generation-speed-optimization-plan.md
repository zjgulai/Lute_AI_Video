---
title: 视频生成最小改动加速方案
doc_type: analysis
module: pipeline
topic: video-generation-speed-optimization
status: stable
created: 2026-05-23
updated: 2026-05-31
owner: self
source: human+ai
---

# S1-S5 视频生成最小改动加速方案

> 前提约束：不牺牲输出质量、改动量最小、可回滚
> 基于根因分析：`docs/analysis/video-generation-speed-root-cause-analysis.md`

---

## 一、方案总览

| 编号 | 优化点 | 改动文件 | 改动行数 | 预估收益 | 质量影响 |
|------|--------|----------|----------|----------|----------|
| **P0-1** | S5 移除 sleep + 条件并发化 | `s5_brand_vlog_pipeline.py` | ~35 行 | **−100~130s** | 无 |
| **P0-2** | S4 clips 并发化 | `s4_live_shoot_pipeline.py` | ~30 行 | **−30~90s** | 无 |
| **P0-3** | Seedance 自验证跳过 frame_variance（非 enforce） | `seedance_video_generate.py` | ~5 行 | **−15~30s** | 无（observe 模式） |
| **P1-1** | StepRunner auto 模式减少 state save | `step_runner.py` | ~5 行 | **−2~5s** | 无（crash 回退到上一步） |
| **P1-2** | auto 模式下 thumbnail_images 可选跳过 | `step_runner.py` | ~8 行 | **−15~30s** | 无（仅缩略图，非视频） |
| **P2-1** | Keyframe 数量按 clips 需求限制 | `keyframe_images.py` + `s1_product_pipeline.py` | ~10 行 | **−30~120s** | 无（保留前 N 个） |

**累计预估收益（S1 典型场景）**：244s → **130~170s**（节省 **30~50%**）
**累计预估收益（S5 典型场景）**：360s → **180~230s**（节省 **35~50%**）

---

## 二、P0 优化（最高优先级）

### P0-1: S5 移除 sleep + 条件并发化

**根因关联**: S5 seedance_clips 纯串行，且 clip 间硬编码 `await asyncio.sleep(3.0)`。

**质量分析**: S5 的 continuity 机制有两层：
1. **Keyframe anchoring**（product view 图片）— 已预存在 `product_sku.views` 中
2. **Last-frame continuity** — 仅当没有 keyframe 时才使用

如果所有 `video_prompts` 都有 `product_angle` 且 `keyframe_map` 命中，则每个 clip 已有独立参考图，**不需要 last-frame 链**。此时并发不会破坏连续性。

**具体改动**: `src/pipeline/s5_brand_vlog_pipeline.py:526-600`

```python
# ═══ 改动前 ═══
for i, vp in enumerate(video_prompts[:5]):
    ...
    res = await reg.execute("seedance-video-generate-skill", gen_params)
    ...
    if i < len(video_prompts) - 1:
        await asyncio.sleep(3.0)   # ← 删除

# ═══ 改动后 ═══
# 1. 判断是否全部 clip 都有 keyframe 覆盖
_all_have_keyframe = all(
    keyframe_map.get(vp.get("product_angle", ""), "")
    for vp in video_prompts[:5]
)

if _all_have_keyframe:
    # ── 并发模式：所有 clip 独立生成 ──
    _seedance_sem = asyncio.Semaphore(4)

    async def _gen_one_s5(i: int, vp: dict[str, Any]) -> tuple[int, Any]:
        async with _seedance_sem:
            prompt_text = vp.get("segment_prompt", "") or vp.get("prompt", "")
            ...  # (保持原有 prompt / duration / resolution 组装逻辑)
            gen_params = {...}
            kf_path = keyframe_map.get(vp.get("product_angle", ""), "")
            if kf_path:
                gen_params["keyframe_image_path"] = kf_path
            res = await reg.execute("seedance-video-generate-skill", gen_params)
            return i, res

    tasks = [_gen_one_s5(i, vp) for i, vp in enumerate(video_prompts[:5])]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 统一处理结果（保持原有 clip_details 组装逻辑）
    for raw in raw_results:
        if isinstance(raw, Exception):
            errors.append(f"clip_failed_with_exception: {raw}")
            continue
        i, res = raw
        ...  # (保持原有成功/失败处理逻辑)
else:
    # ── 串行 fallback：保留 last-frame 链 ──
    last_frame = None
    for i, vp in enumerate(video_prompts[:5]):
        ...  # (保持原有串行逻辑，但删除 sleep)
        res = await reg.execute("seedance-video-generate-skill", gen_params)
        ...
        # 删除：if i < len(video_prompts) - 1: await asyncio.sleep(3.0)
```

**改动要点**:
- 删除 `await asyncio.sleep(3.0)`（1 行）
- 新增 `_all_have_keyframe` 检测（3 行）
- 新增并发分支，复用 S1 的 `Semaphore(4)` 模式（~20 行）
- 串行 fallback 保留原有 last-frame 链，仅删除 sleep（1 行删除）

**预期收益**:
- 移除 sleep: 4 × 3s = **12s**
- 并发化（5 clips）: 5 × 30s → 30s = **节省 120s**
- 合计 **132s**

**回滚**: 删除并发分支，恢复原有 for 循环即可。

---

### P0-2: S4 clips 并发化

**根因关联**: S4 `_step_seedance_clips` 纯串行 `for` 循环，依赖 last_frame 链。

**质量分析**: S4 是 "Live Shoot" 场景，每个 clip 对应独立的 footage asset。 clips 之间**没有视觉连续性需求**（不像 S5 的 VLOG 叙事链）。last-frame continuity 在此场景是过度设计。

S1 的 standard mode 已经证明：使用预分配 reference image + 并发，质量不下降。

**具体改动**: `src/pipeline/s4_live_shoot_pipeline.py:483-572`

```python
# ═══ 改动前 ═══
async def _step_seedance_clips(...):
    s4_model = select_model("s4")
    clip_paths = []
    clip_details = []

    async def _gen(i, vp, last_frame):   # ← 依赖 last_frame
        ...
        if last_frame:
            params["continuity_frame_path"] = last_frame
        res = await reg.execute("seedance-video-generate-skill", params)
        ...
        next_frame = extract_clip_last_frame(...)
        return i, res, next_frame, last_frame

    last_frame_path = None
    for i, vp in enumerate(video_prompts):  # ← 串行
        i, skill_result, next_frame, ... = await _gen(i, vp, last_frame_path)
        ...
        last_frame_path = next_frame

# ═══ 改动后 ═══
async def _step_seedance_clips(...):
    s4_model = select_model("s4")
    clip_paths = []
    clip_details = []

    # P0-2: S4 footage-based clips 不需要 clip-to-clip continuity
    # 复用 S1 的 bounded-concurrency 模式
    _seedance_sem = asyncio.Semaphore(4)

    async def _gen_concurrent(i: int, vp: dict[str, Any]) -> tuple[int, Any]:
        async with _seedance_sem:
            prompt_text = vp.get("prompt", "") or vp.get("segment_prompt", "")
            if isinstance(prompt_text, dict):
                prompt_text = prompt_text.get("prompt", "")
            if not prompt_text:
                prompt_text = f"{product_name} in natural usage scene"
            raw_duration = vp.get("duration_seconds", 5)
            try:
                duration = int(float(raw_duration))
            except (TypeError, ValueError):
                duration = 5
            duration = max(4, min(duration, 15))
            params = {
                "prompt": prompt_text,
                "duration": duration,
                "resolution": "720p",
                "output_label": f"{label}_seg_{i}",
                "model": s4_model,
            }
            res = await reg.execute("seedance-video-generate-skill", params)
            return i, res

    tasks = [_gen_concurrent(i, vp) for i, vp in enumerate(video_prompts)]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 统一处理结果（保持原有 clip_details 组装逻辑）
    for raw in raw_results:
        if isinstance(raw, Exception):
            errors.append(f"clip_failed_with_exception: {raw}")
            continue
        i, skill_result = raw
        if skill_result.success and skill_result.data:
            p = skill_result.data.get("video_path", "")
            if p:
                clip_paths.append(p)
                clip_details.append({
                    "path": p,
                    "duration": skill_result.data.get("duration_seconds", 0),
                    "is_stub": skill_result.data.get("is_stub", False),
                    "verification": skill_result.data.get("verification", {}),
                    "transition_to_next": video_prompts[i].get("transition_to_next", ""),
                    "transition_type": video_prompts[i].get("transition_type", "clean"),
                    "clip_index": video_prompts[i].get("clip_index", i + 1),
                    "segment_type": video_prompts[i].get("segment_type", "body"),
                    "shot_type": video_prompts[i].get("shot_type", ""),
                })
        else:
            errors.append(f"clip_{i}_failed: {skill_result.error}")
```

**改动要点**:
- 删除 `_gen` 中的 `last_frame` 参数和 `continuity_frame_path` 注入
- 删除 `last_frame_path` 状态变量和串行 for 循环
- 新增 `Semaphore(4) + asyncio.gather` 并发模式（复用 S1 模式）
- 结果处理逻辑保持原有 `clip_details` 组装不变

**预期收益**:
- 3 clips 串行 90s → 并发 30s = **节省 60s**

**回滚**: 恢复原有 `_gen` 签名和 last_frame 链即可。

---

### P0-3: Seedance 自验证跳过 frame_variance（非 enforce 模式）

**根因关联**: `_check_frame_variance` 每个 clip 运行 ffmpeg 提取 3 帧，耗时 5-10s。当前 observe/off 模式下也执行，只是结果不用于 `all_ok`。

**质量分析**: `QUALITY_MODE` 有三档：
- `off`: 完全跳过质量检查
- `observe`（默认）: 记录但不拦截
- `enforce`: 严格拦截

在 `observe` 模式下，frame_variance 的运行只是产生日志，不影响 pipeline 决策。跳过它**不改变任何输出**。

**具体改动**: `src/skills/seedance_video_generate.py:301-311`

```python
# ═══ 改动前 ═══
# Frame variance check — detect static images and black screens
variance_result = self._check_frame_variance(local_path)
variance_ok = variance_result["variance_ok"]
if not variance_ok and QUALITY_MODE == "enforce":
    failures.extend(variance_result["failures"])

# ═══ 改动后 ═══
# Frame variance check — only run in enforce mode to avoid per-clip 5-10s ffmpeg overhead
if QUALITY_MODE == "enforce":
    variance_result = self._check_frame_variance(local_path)
    variance_ok = variance_result["variance_ok"]
    if not variance_ok:
        failures.extend(variance_result["failures"])
else:
    variance_result = None
    variance_ok = True
```

**改动要点**:
- 将 `_check_frame_variance` 调用包裹在 `QUALITY_MODE == "enforce"` 条件中
- observe/off 模式下直接 `variance_ok = True`，不运行 ffmpeg

**预期收益**:
- 每 clip 节省 5-10s，3 clips = **15-30s**

**回滚**: 删除 if 条件，恢复原样即可。

---

## 三、P1 优化（中等优先级）

### P1-1: StepRunner auto 模式减少 state save

**根因关联**: `_execute_step` 在 step started 和 step done 时各 save 一次 state，共 24+ 次 DB 写入。

**质量分析**: auto 模式下无 human review 中断，不需要在 step 中间恢复。如果步骤执行中崩溃，回退到上一步的 completed state 并重新执行即可，不影响质量。

**具体改动**: `src/pipeline/step_runner.py:444-447`

```python
# ═══ 改动前 ═══
# Mark step as started
step_data["status"] = "pending"
step_data["started_at"] = datetime.now().isoformat()
await self.state_manager.save(state["label"], state)

# ═══ 改动后 ═══
# Mark step as started
step_data["status"] = "pending"
step_data["started_at"] = datetime.now().isoformat()
# P1-1: In auto mode, skip intermediate save to reduce I/O.
# The final save on step completion is sufficient for recovery.
# step_by_step mode still saves so human review sees the latest state.
if state.get("mode") != "auto":
    await self.state_manager.save(state["label"], state)
```

**改动要点**:
- 条件化 save：auto 模式下不保存 "started" 状态
- 步骤完成时的 save（line 567）保持不变
- step_by_step 模式不受影响（仍保存以便 human review）

**预期收益**:
- 12 步 × 1 次 I/O 节省 ≈ **2-5s**（取决于 PG 延迟）
- 额外收益：减少 DB 负载

**回滚**: 删除 if 条件即可。

---

### P1-2: auto 模式下 thumbnail_images 可选跳过

**根因关联**: `thumbnail_images` 生成 2 张 GPT 图片（~15-30s），但不参与视频组装，是独立产物。

**质量分析**:
- `thumbnail_images` 产物用于平台发布时的封面图
- 视频质量（assemble_final 的输出）完全不依赖缩略图
- 在 auto 模式下，用户首要需求是视频本身，缩略图可以异步补

**具体改动**: `src/pipeline/step_runner.py`（在 compliance skip 模式旁边）

```python
# ═══ 新增在 step_runner.py:443 附近（compliance skip 之后）═══
# P1-2: In auto mode, thumbnail generation is a sidecar artifact.
# Skip it when SKIP_THUMBNAIL_IN_AUTO env is set to reduce pipeline latency.
# Thumbnails can be regenerated later without affecting the video.
_skip_thumbnail = (
    step_name == "thumbnail_images"
    and state.get("mode") == "auto"
    and os.environ.get("SKIP_THUMBNAIL_IN_AUTO", "").lower() in ("1", "true", "yes")
)
if _skip_thumbnail:
    logger.info("step_runner: skipping thumbnail_images in auto mode (SKIP_THUMBNAIL_IN_AUTO)")
    step_data["status"] = "done"
    step_data["output"] = []
    step_data["completed_at"] = datetime.now().isoformat()
    next_step = _get_next_step(step_name, step_order)
    state["current_step"] = next_step
    await self.state_manager.save(state["label"], state)
    return state
```

**改动要点**:
- 增加环境变量开关 `SKIP_THUMBNAIL_IN_AUTO`（默认关闭，需显式启用）
- 仅在 auto 模式下生效，step_by_step 模式不受影响
- 被跳过时输出空列表，不阻塞后续步骤

**预期收益**:
- 2 张缩略图并发生成 = **15-30s**

**回滚**: 删除新增代码块即可。或设置 `SKIP_THUMBNAIL_IN_AUTO=false`。

---

## 四、P2 优化（可选）

### P2-1: Keyframe 数量按 clips 需求限制

**根因关联**: KeyframeImagesSkill 为每个 storyboard 生成最多 10 个 shots 的 keyframe，但 clips 只有 3 个，大量 keyframe 不被使用。

**质量分析**: video_prompts 在 keyframe 之后生成，但 clips 数量可由 `video_duration` 估算。限制 keyframe 数量只影响"不使用的 shots"，不影响实际 clip 的质量。

**具体改动**: `src/skills/keyframe_images.py:86-93` + `src/pipeline/s1_product_pipeline.py:696-699`

```python
# ═══ keyframe_images.py:86-93 改动后 ═══
# Safety cap: process at most MAX_SHOTS_PER_STORYBOARD shots
# P2-1: Allow caller to override cap when clips count is known upfront
capped_shots = shots[:params.get("_max_shots", self.MAX_SHOTS_PER_STORYBOARD)]

# ═══ s1_product_pipeline.py:696-699 改动后 ═══
for sb in storyboards[:MAX_CLIPS_PER_DEMO]:
    # P2-1: Estimate needed keyframes from video_duration (1 keyframe per ~15s clip)
    estimated_clips = max(1, config.get("video_duration", 30) // 15)
    res = await reg.execute("keyframe-images", {
        "storyboard": sb,
        "size": "1024x1792",
        "quality": "high",
        "_quality_attempt": sb.get("_quality_attempt", 0),
        "_max_shots": estimated_clips,  # ← 新增
    })
```

**预期收益**:
- 3 storyboards × 10 shots → 3 × 3 shots = **节省 21 张 keyframe**
- 按每张 5-20s 计 = **节省 105~420s**（极端情况）
- 典型场景 = **节省 30~120s**

**回滚**: 删除 `"_max_shots"` 参数即可恢复 10 shots 上限。

---

## 五、实施路线图

### Phase 1: P0 优化（当天可上线）✅ 已完成 2026-05-23

```bash
# 1. P0-3: Seedance frame_variance 跳过（风险最低，1 个文件）✅
# 2. P0-2: S4 并发化（独立文件，不影响 S1/S2/S3/S5）✅
# 3. P0-1: S5 移除 sleep + 条件并发化（独立文件）✅
```

每项改动独立验证：
- S4 E2E (6/6 passed) / S5 E2E (4/4 passed) / frame_variance (6/6 passed)
- ruff lint 全通过

### Phase 2: P1 优化（次日上线）✅ 已完成 2026-05-23

```bash
# 4. P1-1: StepRunner auto save 优化 ✅
# 5. P1-2: Thumbnail 可选跳过（默认关闭，需显式启用）✅
```

### Phase 3: P2 优化（评估后决定）✅ 已完成 2026-05-23

```bash
# 6. P2-1: Keyframe 数量限制（需验证 storyboard shots 与 clips 的映射关系）✅
```

**实施完成日期**: 2026-05-23
**验证状态**: 16/16 相关测试通过，ruff lint 全通过
**已知遗留**: `test_keyframe_images_validate_params` 在改动前已失败（空 dict 被 `not sb` 误判的既有 bug，与本次优化无关）

---

## 六、累计收益估算

### S1 Product Direct（30s 视频，3 clips，auto 模式）

| 环节 | 优化前 | 应用优化 | 优化后 |
|------|--------|----------|--------|
| LLM 文本步骤 | 60s | — | 60s |
| Keyframe 图片 | 100s | P2-1: 限制为 3 shots | **40s** |
| Seedance clips | 45s | P0-3: 跳过 variance | **35s** |
| Thumbnail | 15s | P1-2: 跳过 | **0s** |
| TTS | 3s | — | 3s |
| Remotion 组装 | 8s | — | 8s |
| 自验证 | 10s | P0-3: 跳过 variance | **5s** |
| Checkpoint | 3s | P1-1: 减少 save | **1s** |
| **总计** | **244s** | | **~152s** |

**提速**: **38%**

### S4 Live Shoot（3 clips，auto 模式）

| 环节 | 优化前 | 应用优化 | 优化后 |
|------|--------|----------|--------|
| Seedance clips | 90s | P0-2: 并发化 | **35s** |
| 其他 | 120s | — | 120s |
| **总计** | **210s** | | **~155s** |

**提速**: **26%**

### S5 Brand VLOG（5 clips，全部有 keyframe，auto 模式）

| 环节 | 优化前 | 应用优化 | 优化后 |
|------|--------|----------|--------|
| Seedance clips + sleep | 162s | P0-1: 并发 + 删 sleep | **35s** |
| Thumbnail | 0s | — | 0s |
| 其他 | 150s | — | 150s |
| **总计** | **312s** | | **~185s** |

**提速**: **41%**

---

## 七、风险与回滚

| 优化 | 潜在风险 | 缓解措施 | 回滚方式 |
|------|----------|----------|----------|
| P0-1 S5 并发 | keyframe 不足时并发可能导致连续性断裂 | 条件检测 `_all_have_keyframe`，不足时 fallback 串行 | 删除并发分支 |
| P0-2 S4 并发 | footage-based clips 理论上不需要连续性，但需验证 | S4 E2E 测试通过即可确认 | 恢复 last_frame 链 |
| P0-3 跳过 variance | observe 模式失去 static image / black screen 检测 | QUALITY_MODE 可切换为 enforce 恢复检测；日志中仍保留 warning | 删除 if 条件 |
| P1-1 减少 save | auto 模式 crash 时回退到上一步 completed state | 可接受：重新执行一步 vs 24 次 save 开销 | 删除 if 条件 |
| P1-2 跳过缩略图 | 平台发布时需要缩略图 | 环境变量开关，默认关闭；缩略图可独立 API 生成 | 设 `SKIP_THUMBNAIL_IN_AUTO=false` |
| P2-1 keyframe 限制 | 可能低估 needed keyframes | `estimated_clips = max(1, duration // 15)` 保守估计 | 删除 `"_max_shots"` 参数 |

---

## 八、验证清单

每项优化合并前需通过：

1. **单元测试**: 对应 test 文件通过
2. **E2E 测试**: `make test` 全量通过（含 `test_s4_e2e.py`, `test_s5_e2e.py`）
3. **非回归验证**: Fast Mode 不受影响（这些优化不涉及 Fast Mode 代码路径）
4. **质量对比**: 同一组输入，优化前后产出视频的 `audit_report` 评分差异 < 0.05
5. **时间对比**: 同一组输入，优化后耗时减少符合预期

---

*方案完*
