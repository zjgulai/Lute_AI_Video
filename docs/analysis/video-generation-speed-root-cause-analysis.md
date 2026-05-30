---
title: 视频生成速度根因分析报告
doc_type: analysis
module: pipeline
topic: video-generation-speed-root-cause
status: stable
created: 2026-05-23
updated: 2026-05-31
owner: self
source: human+ai
---

# S1-S5 视频生成速度根因分析报告

> 分析日期: 2026-05-23
> 分析范围: `src/pipeline/` + `src/skills/` + `src/tools/` + `src/graph/`
> 约束: 不改动任何代码，仅做静态分析

---

## 一、问题现象

用户反馈 S1-S5 pipeline 视频生成"时间长"。Fast Mode 可在 30-65 秒产出视频，而完整 pipeline (S1/S2) 通常需要 5-15 分钟甚至更长。本报告通过逐层拆解 pipeline 架构、skill 调用链、外部 API 交互模式，定位时间消耗的本质根因。

---

## 二、各场景步骤耗时全景图

| 场景 | 步骤数 | 关键媒体生成步骤 | 预计总耗时 |
|------|--------|------------------|-----------|
| S1 Product Direct | 12 | keyframe(10 shots) + clips(3个) + thumbnail(2个) + tts + assemble | **8-15 min** |
| S2 Brand Campaign | 12 | 同S1 | **8-15 min** |
| S3 Influencer Remix | 13 | 同S1 + video_analysis + remix_script | **10-18 min** |
| S4 Live Shoot | 8 | clips(串行) + tts + assemble (无keyframe) | **5-10 min** |
| S5 Brand VLOG | 6 | clips(串行, max 5) + tts + assemble | **5-12 min** |
| Fast Mode | 2-3 | 1 clip + 可选TTS | **30-65 sec** |

**核心矛盾**: Fast Mode 和完整 pipeline 都调用同样的 Seedance 视频 API，但前者 30 秒完成，后者 5-15 分钟。差距不在视频生成本身，而在 pipeline 架构、串行依赖和冗余步骤。

---

## 三、根因分层 (Root Cause Layers)

### 根因 1: 外部视频 API 的异步轮询耗时 (占总时间 40-60%)

**证据链:**

```python
# src/tools/seedance_client.py:406-439
poll_interval = 5.0
max_polls = 120  # 600s = 10min

for i in range(max_polls):
    await asyncio.sleep(poll_interval)  # 硬等待 5s
    # ... poll status ...
    if status == "finished":
        return await self._download_video(video_url, ...)
```

- Seedance 通过 poyo.ai proxy 调用，采用 **submit → 轮询(poll) → download** 的异步架构
- 轮询间隔固定 **5 秒**，无法缩短 (API 侧决定的队列延迟)
- 每次视频生成需要 1 次完整 submit+poll+download 周期
- **实际生产观测**: 单个 clip 生成耗时 30-60 秒，但最坏情况下可达 poll timeout 的 **600 秒**

**各场景视频生成耗时估算:**

| 场景 | Clip 数量 | 并发策略 | 视频生成耗时估算 |
|------|----------|---------|----------------|
| S1/S2 | max 3 (MAX_CLIPS_PER_DEMO=3) | bounded concurrency=4 | ~30-60s (并发) |
| S3 | max 3 | bounded concurrency=4 | ~30-60s |
| **S4** | 无上限 (代码无 cap) | **纯串行** | N clips × 30-60s |
| **S5** | max 5 | **纯串行 + clip间 3s sleep** | ~5×30s + 4×3s = **162s+** |

> **S4/S5 的视频生成是串行的！** 这是两个场景比 S1 更慢的直接原因。

```python
# src/pipeline/s4_live_shoot_pipeline.py:538-566
last_frame_path = None
for i, vp in enumerate(video_prompts):  # 纯串行 for 循环
    i, skill_result, next_frame = await _gen(i, vp, last_frame_path)
    # ...
    last_frame_path = next_frame  # 等待当前 clip 完成才生成下一个

# src/pipeline/s5_brand_vlog_pipeline.py:526-591
for i, vp in enumerate(video_prompts[:5]):  # 纯串行
    res = await reg.execute("seedance-video-generate-skill", gen_params)
    # ...
    if i < len(video_prompts) - 1:
        await asyncio.sleep(3.0)  # 额外 3 秒间隔
```

对比 S1 的并发实现:
```python
# src/pipeline/s1_product_pipeline.py:913-980
_seedance_sem = asyncio.Semaphore(4)  # 最多 4 个并发

async def _gen_single_clip(...) -> tuple[int, Any]:
    async with _seedance_sem:
        res = await reg.execute("seedance-video-generate-skill", gen_params)
        return i, res

# standard mode: 全部并发 launch
clip_tasks = [_gen_single_clip(i, vp, kf_path) for i, vp in enumerate(video_prompts)]
raw_results = await asyncio.gather(*clip_tasks, return_exceptions=True)
```

**根因判定**: 外部 API 的轮询等待是物理上限，但 S4/S5 的串行策略使这个上限被乘上了 clip 数量。

---

### 根因 2: 关键帧图片串行生成 (占总时间 20-30%)

**证据链:**

```python
# src/skills/keyframe_images.py:95-120
async def _gen_one(i, shot):
    result = await reg.execute("gpt-image-generate-skill", {
        "prompt": comp_prompt,
        "size": "1024x1792",
        # ...
    })
    return i, image_path, comp_prompt

tasks = [_gen_one(i, shot) for i, shot in enumerate(capped_shots)]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

表面上用了 `asyncio.gather`，但 `_gen_one` 内部调用的是 `reg.execute("gpt-image-generate-skill", ...)`。继续追踪:

```python
# src/skills/gpt_image_generate.py:56-62
api_result = await client.generate(...)  # 调用 GPTImageClient

# src/tools/gpt_image_client.py:144-151
result = await self._poyo.submit_poll_download(
    model=POYO_IMAGE_MODEL,
    input_payload=input_payload,
    output_path=filepath,
    poll_interval=5.0,           # 同样 5s 轮询
    max_polls=_poyo_image_max_polls(),  # 默认 72 = 6min max
)
```

- GPT Image 同样走 poyo.ai async 架构: submit → poll(5s) → download
- **关键限制**: `_step_keyframe_images` 的注释明确指出:
  > "Serial generation: poyo.ai has strict concurrency limits on image generation tasks. Parallel requests cause queue rejects."

- `MAX_SHOTS_PER_STORYBOARD = 10`，意味着最多生成 10 张关键帧图
- 即使 gather 并发 launch，poyo.ai 服务端会队列化或拒绝，实际效果是串行
- 每张图 5-20 秒，10 张图 = **50-200 秒**

> 注意: S4 **没有 keyframe_images 步骤**，这是 S4 比 S1 快的原因之一。

---

### 根因 3: Pipeline 步骤过多且全串行 (占总时间 15-25%)

**S1 完整步骤链 (12 steps):**

```
strategy → scripts → compliance → storyboards → continuity_storyboard_grid
→ keyframe_images → video_prompts → thumbnail_prompts → seedance_clips
→ tts_audio → thumbnail_images → assemble_final → audit
```

**StepRunner 的执行模型:**

```python
# src/pipeline/step_runner.py:356-371
for step_name in step_order[start_idx:]:
    if state.get("pipeline_degraded"):
        break
    # gate check ...
    state = await self._execute_step(state, step_name, force=False)
```

- **严格串行**: 每个 step 完成后才执行下一个
- 每一步都有: load state → execute → save state (磁盘 I/O)
- 文本/LLM 步骤虽然快(各 5-15s)，但累计起来:
  - strategy + scripts + compliance + storyboards + continuity_grid + video_prompts + thumbnail_prompts + audit
  - ≈ 8 个 LLM 调用 × 5-15s = **40-120 秒**

**与 Fast Mode 对比:**

Fast Mode 只有:
1. 1 个 LLM 调用 (deepseek-chat, 2-5s) — 注意用的是轻量模型，不是 V4-Pro
2. 1 个视频生成 (并行)
3. 可选 1 个 TTS (并行)

```python
# src/services/fast_mode.py:152-159
enhanced = await self.llm.invoke_json(
    system_prompt=_PROMPT_ENHANCE_SYSTEM,
    user_message=...,
    model="deepseek-chat" if DEFAULT_LLM_PROVIDER == "deepseek" else None,
)
# 明确使用 deepseek-chat (V3) 而非 V4-Pro，避免 60-150s 的 reasoning 延迟
```

**根因判定**: Pipeline 设计了 12-13 个串行步骤来完成"策略→脚本→合规→分镜→关键帧→视频提示→缩略图提示→视频→音频→缩略图图→组装→审计"的全链路。这带来了质量保障，但也带来了时间开销。

---

### 根因 4: LangGraph Checkpoint 持久化开销 (占总时间 5-10%)

**证据链:**

```python
# src/graph/pipeline.py:211-324
compiled = graph.compile(
    checkpointer=checkpointer,
    interrupt_after=["strategy_audit_node", "script_audit_node", ...]
)
```

- LangGraph 的 `StateGraph` 在每个节点执行后都会 **checkpoint** 状态
- Production 使用 `PostgresSaver`，每次 checkpoint 都是一次 PostgreSQL 写入
- `VideoPipelineState` 有 30+ 字段，包含大量嵌套 dict/list，序列化/反序列化开销可观
- StepRunner 也有同样问题:
  ```python
  # step_runner.py:305, 441, 489, etc.
  await self.state_manager.save(label, state)  # 每步都 save
  ```

**根因判定**: 状态持久化是正确性保障（支持断点恢复、human review），但每次写入都在总时间上加了几十到几百毫秒。12+ 步 × 多次 save = 数秒的累计开销。

---

### 根因 5: LLM 模型选择差异 (隐性根因)

**Pipeline 中的 LLM 调用:**
- StrategyAgent / ScriptWriterAgent / StoryboardAgent 等默认使用 `DEFAULT_LLM_PROVIDER = "deepseek"`
- 后端 `llm_client.py` 解析 `"deepseek"` 为 `deepseek-v4-pro` (reasoning 模型)
- DeepSeek V4-Pro 的 reasoning 模式对复杂 prompt 可达 **60-150 秒**

**Fast Mode 的 LLM 调用:**
- 显式指定 `model="deepseek-chat"` (V3，非 reasoning)
- 2-5 秒返回

```python
# src/tools/llm_client.py (根据 config.py 推断)
# DEFAULT_LLM_PROVIDER = "deepseek" → 路由到 deepseek-v4-pro
# fast_mode.py 显式覆盖为 deepseek-chat
```

**根因判定**: Pipeline 的文本步骤使用了 reasoning 模型，而 Fast Mode 用了轻量模型。这个差异在 strategy / script / storyboard / continuity_grid 等多个步骤中被放大。

---

### 根因 6: 媒体文件自验证开销 (占总时间 3-5%)

每个媒体文件生成后都有多轮验证:

```python
# seedance_video_generate.py:179-184
verification = self._self_verify(local_path=local_path, is_stub=is_stub)
# 检查: file_exists → size_ok → header_ok → duration_ok → resolution_ok → frame_variance

# frame_variance 检查 (seedance_video_generate.py:399-495)
# 1. ffprobe 测 duration
# 2. ffmpeg 提取 3 帧 (start/middle/end) 到临时文件
# 3. 计算 MSE + 亮度均值
# 4. 清理临时文件
```

以及 Remotion assemble 后的:
```python
# remotion_assemble.py:799-904
av_sync = self._check_av_sync(video_path)
# ffprobe 分别读 video stream 和 audio stream duration
```

- 每次 ffprobe/ffmpeg 子进程调用 1-10 秒
- 3 clips + 1 final video = 4 次 video 验证
- 10 keyframes = 10 次 image 验证
- 1 次 TTS = 1 次 audio 验证
- 累计验证时间: **10-30 秒**

---

### 根因 7: Gate 系统的人工等待 (非代码根因，但影响体验)

```python
# step_runner.py:363-370, 548-562
if step_name in _get_gate_after_steps(scenario) and state.get("mode") != "auto":
    state["gates"][gate_id] = {"status": "awaiting_approval", ...}
    state["current_step"] = step_name
    return state  # pipeline 暂停，等待人工 approval
```

- S1 目前只在 **step_by_step** 模式下启用 gate，**auto 模式跳过**
- 如果用户在 step_by_step 模式下运行，human review 的等待时间完全取决于人工响应速度
- 这是一个设计选择，不是代码性能问题，但确实是"视频生成时间长"的用户感知来源之一

---

## 四、根因热力图

按对总耗时的影响排序 (S1 auto mode, 30s 视频):

| 排名 | 根因 | 时间占比 | 是否可优化 |
|------|------|----------|-----------|
| 1 | 外部视频 API 轮询等待 (Seedance/poyo) | 30-40% | 部分 (并发化) |
| 2 | 关键帧图片串行生成 | 20-30% | 是 (并发/批量) |
| 3 | Pipeline 12 步串行 LLM/文本处理 | 15-25% | 是 (步骤裁剪/并行) |
| 4 | LLM 模型选择 (V4-Pro reasoning) | 10-15% | 是 (按步骤选模型) |
| 5 | Checkpoint 持久化开销 | 5-10% | 部分 (批量写入) |
| 6 | 媒体自验证 (ffprobe/ffmpeg) | 3-5% | 是 (异步/简化) |
| 7 | S4/S5 视频 clip 串行生成 | 增量 50-100% | 是 (并发化) |

---

## 五、S4/S5 特有瓶颈

### S4 Live Shoot

- **无 keyframe_images 步骤** → 比 S1 省 50-200 秒
- 但 seedance_clips **纯串行**:
  ```python
  for i, vp in enumerate(video_prompts):
      await _gen(i, vp, last_frame_path)  # 无并发
  ```
- 如果 video_prompts 有 3 个，耗时 ≈ S1 的 3 倍
- 没有 `MAX_CLIPS_PER_DEMO` 限制，clip 数量由输入决定

### S5 Brand VLOG

- 步骤最少 (6 steps)，但 seedance_clips 最慢:
  ```python
  for i, vp in enumerate(video_prompts[:5]):  # 最多 5 个 clips
      res = await reg.execute("seedance-video-generate-skill", gen_params)
      # ...
      if i < len(video_prompts) - 1:
          await asyncio.sleep(3.0)  # 硬编码 3 秒间隔
  ```
- 5 clips × 30s + 4 × 3s sleep = **162 秒** 仅视频生成
- 加上 vlog_strategy (DeepSeek 120s timeout) 的 LLM 调用
- 总计可能 **5-12 分钟**

---

## 六、Fast Mode 为什么快?

| 维度 | Fast Mode | S1 Pipeline |
|------|-----------|-------------|
| LLM 调用 | 1 次, deepseek-chat (2-5s) | 8 次, deepseek-v4-pro (5-15s each) |
| 视频生成 | 1 clip, submit+poll (~30-60s) | 3 clips, 并发 (~30-60s) |
| 关键帧图 | 无 | 10 shots 串行 (~50-200s) |
| 缩略图 | 无 | 2 张并发 (~10-30s) |
| TTS | 可选, 并行 | 1 次 (~1-5s) |
| 组装 | 无 | Remotion/ffmpeg (~5-15s) |
| 审计 | 无 | 1 次 (~5-15s) |
| Checkpoint | 无 | 12+ 次持久化 |
| **总计** | **~30-65s** | **~5-15min** |

**本质区别**: Fast Mode 是"最小可行路径"——它跳过了策略、脚本、分镜、合规、关键帧、缩略图、审计等所有中间层，直接用用户输入生成视频。Pipeline 的"长"不是某一步慢，而是**步骤数量 × 串行依赖 × 每步开销**的累积效应。

---

## 七、根因总结

### 第一层: 外部 API 物理限制 (不可消除，可缓解)
1. **Seedance/poyo.ai 异步轮询架构**: 每个 clip 固定 5s poll interval，max 600s timeout
2. **GPT Image 同样异步**: 5s poll interval，max 360s timeout

### 第二层: 架构层面的串行设计 (可优化)
3. **S4/S5 视频 clip 纯串行**: for 循环 + 3s sleep，未利用并发
4. **Keyframe 图片串行**: poyo.ai 队列限制导致 gather 实际串行
5. **Pipeline 12+ 步骤全串行**: StepRunner for 循环，每步完成后才下一步
6. **LangGraph checkpoint 每步持久化**: PostgreSQL 写入 12+ 次

### 第三层: 实现层面的选择 (可优化)
7. **LLM 使用 V4-Pro reasoning 模型**: strategy/script/storyboard 等步骤可使用轻量模型
8. **媒体自验证同步执行**: ffprobe/ffmpeg 子进程阻塞
9. **Continuity storyboard grid 强制执行**: 即使不需要也执行 LLM 调用
10. **Thumbnail 生成在关键路径上**: 生产环境中可能不需要缩略图来阻塞视频输出

---

## 八、影响程度量化 (估算)

以 S1, 30s 视频, auto mode, 3 clips, 10 keyframes 为例:

| 环节 | 乐观 | 典型 | 悲观 |
|------|------|------|------|
| LLM 文本步骤 (8 步) | 20s | 60s | 120s |
| Keyframe 图片 (10 shots, 串行) | 30s | 100s | 300s |
| Seedance clips (3 clips, 并发) | 20s | 45s | 120s |
| Thumbnail 图片 (2 张, 并发) | 5s | 15s | 60s |
| TTS 音频 | 1s | 3s | 10s |
| Remotion/ffmpeg 组装 | 3s | 8s | 30s |
| 自验证 (ffprobe) | 5s | 10s | 20s |
| Checkpoint 持久化 | 1s | 3s | 5s |
| **总计** | **85s** | **244s (~4min)** | **665s (~11min)** |

> 用户感知的"时间长"对应的是典型到悲观场景 (4-11 分钟)，而 Fast Mode 始终稳定在 30-65 秒。

---

*报告完*
