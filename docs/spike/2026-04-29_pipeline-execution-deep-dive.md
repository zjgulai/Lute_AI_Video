# 12 步管线深度执行分析

> 从用户实测日志追溯每一步的真实耗时和执行逻辑

---

## 一、实测数据（来自你的 18:30 执行日志）

```
18:30:20  POST /scenario/s1/step/strategy
18:31:46  策略完成 — 耗时 86 秒
          期间 strategy_skill 遍历了 5 个 brief，4 个被判定 invalid 跳过
          只剩 1 个有效 brief 返回
```

**86 秒做一次 LLM 策略调用。** 这是整个管线最慢的单点。

---

## 二、完整执行链路（按调用序）

```
Step 1: strategy      ──→ LLM 调用 (1 次)         实测 ~86s
Step 2: scripts       ──→ LLM 调用 (1 次/brief)   3 briefs × ~4s ≈ 12s
Step 3: compliance    ──→ LLM 调用 (1 次/script)   3 scripts × ~4s ≈ 12s  
Step 4: storyboards   ──→ 纯规则计算               ~0.01s
Step 5: keyframe_images──→ GPT-Image API (1 次/shot) 3 shots × ~10s ≈ 30s
Step 6: video_prompts ──→ 规则模板                  ~0.01s
Step 7: thumbnail_prompts──→ 规则模板               ~0.01s
Step 8: seedance_clips───→ Seedance API (3 clips)   3 × 30-60s ≈ 90-180s
Step 9: tts_audio    ──→ ElevenLabs/stub            ~0.5s (stub) 或 ~5s (API)
Step 10: thumbnail_images──→ GPT-Image API          3 × ~10s ≈ 30s
Step 11: assemble_final──→ Remotion/ffmpeg          ~5-30s
Step 12: audit        ──→ 本地检查                  ~1s

─────────────────────────────────────────────────
总计预估（无 API Key 的 stub 模式）:  ~90s
总计预估（真实 API）:               ~250-350s (4-6 分钟)
```

---

## 三、逐个步骤深度剖析

### Step 1: strategy — 为什么这么慢？

**调用链：**
```
StepRunner.resume() 
  → _execute_step("strategy") 
    → S1ProductDirectPipeline.run_step("strategy", state)
      → _step_strategy() 
        → SkillRegistry.execute("product-to-video-strategy")
          → ProductStrategySkill.execute()
            → LLMSkill → llm.invoke() → Kimi API
```

**ProductStrategySkill 做了什么：**
1. 把 product_catalog（JSON 几百字符）、brand_guidelines（JSON）、platforms、languages 拼接成一个 System Prompt
2. 用一个 User Template 问 LLM："生成 5 个 brief"
3. LLM 返回 5 个 brief 的 JSON 数组
4. **然后逐条校验每个 brief**：
   - `brief.video_type` 是否在合法类型列表里
   - `brief.topic` 是否非空
   - `brief.target_platforms` 是否有交集
   - 任何一条不通过 → 跳过（日志里看到 `skipping invalid brief`）
5. 你的实测：5 条 brief 中 4 条被跳过，只剩 1 条有效

**86 秒的构成：**
```
LLM 生成 5 条 brief:          ~80s  (Kimi API 一次请求)
逐条校验 (本地，可忽略):       ~0.01s
4 条被判 invalid 丢弃:         ~0.01s
─────────────────────────────────
总计:                         ~86s
```

**为什么 4 条被判 invalid？** 让我看校验逻辑：

```python
# product_strategy.py 的 validate_briefs
VALID_VIDEO_TYPES = {
    "product_feature", "product_usage", "product_360",
    "social_proof", "comparison", "tutorial",
    "emotional", "trend", "unboxing", "review",
}
# 如果 LLM 返回的 video_type 不在这个集合里 → invalid
# 如果 topic 为空 → invalid
# 如果 target_platforms 和用户选的没交集 → invalid
```

**核心问题：** LLM 生成的内容质量不可控。花 80 秒等 LLM 返回 5 条 brief，然后因为校验规则严格丢弃 4 条，只留 1 条。这是巨大的浪费。

### Step 2-3: scripts + compliance — 串行 LLM 调用

```
Step 2 scripts:
  briefs = [从 Step 1 取]  // 如果 Step 1 只返回 1 条 brief
  for each brief: 调用 script-writer-skill → LLM 生成脚本
  // 1 条 brief → 1 次 LLM ≈ 4s

Step 3 compliance:
  scripts = [从 Step 2 取]
  for each script: 调用 brand-compliance-skill → LLM 审查
  // 1 条 script → 1 次 LLM ≈ 4s
  // brand_mode=False 时跳过
```

**耗时：** 如果策略返回 3 条 brief，每条生成 + 审查约 8s，总计 24s。但策略只返回 1 条 → 8s。

### Step 4: storyboards — 秒过

纯规则计算。读取 scripts[].segments，按模板生成 shot 分镜。不做 API 调用。

```
耗时: < 0.1s
```

### Step 5: keyframe_images — GPT-Image 生成

```
for each shot in storyboard (最多 3 shots):
  → 调用 GPT-Image (via poyo.ai proxy)
  → 等待生成图片 (poyo 提交 + 轮询)
  → 写回 shot["keyframe_image_path"]
```

```
3 shots × ~10s = 30s (poyo 代理模式)
```

如果没有 POYO_API_KEY，GPT-Image 不可用，这步生成占位图 → < 1s。

### Step 6-7: video_prompts + thumbnail_prompts — 秒过

纯规则模板生成。把 shot 的 description 转为 Seedance 提示词格式。

```
耗时: < 0.1s (每个)
```

### Step 8: seedance_clips — 最慢的步

```
for each clip (最多 3 clips):
  → 调用 Seedance video generation API
    → 如果有 keyframe_image: image_to_video (图片锚定)
    → 否则: text_to_video (纯文字)
  → 等待视频生成 (poyo 异步提交 + 轮询结果)
  → 本地保存 mp4
  → 自检: 文件存在、大小、时长、MP4 头
  → 提取 last_frame 用于下一 clip 连续性
```

```
3 clips × 30-60s = 90-180s (poyo 代理模式)
```

这是管线中最慢的单步。如果不配置真实 Seedance API（只有 stub），这步生成 stub 视频 → < 3s。

### Step 9: tts_audio — 语音合成

```
for each script:
  → 提取 voiceover 文本
  → ElevenLabs TTS API (或 stub 静音 mp3)
```

```
每次 ~5s (API) 或 ~0.5s (stub)
```

### Step 10: thumbnail_images — 缩略图生成

```
for each thumbnail prompt:
  → 调用 GPT-Image API
```

```
3 thumbnails × ~10s = 30s
```

### Step 11: assemble_final — 合成

```
所有 clip + 音频 + 缩略图
  → Remotion renderMedia() 或 ffmpeg concat
  → 输出最终 mp4
```

```
~5s (ffmpeg) ~30s (Remotion with transitions)
```

### Step 12: audit — 质量审计

本地检查，不做 API 调用。
```
~1s
```

---

## 四、耗时热力图

```
strategy           ████████████████████████████ 86s
scripts            ████████████ 12s
compliance         ████ 4s (brand_mode=False 时跳过)
storyboards        ░ 0.1s
keyframe_images    ██████████ 30s
video_prompts      ░ 0.1s
thumbnail_prompts  ░ 0.1s
seedance_clips     ██████████████████████████████████████████████ 90-180s
tts_audio          ██ 5s
thumbnail_images   ██████████ 30s
assemble_final     ██████ 20s
audit              ░ 1s
─────────────────────────────────────────
总计 (真实 API):    280-370s  ≈ 5-6 分钟
总计 (stub 模式):   86 + 12 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 5 + 1 ≈ 104s
```

**你的实际体验（18:30 测试）：strategy 86s，然后 scripts/compliance/storyboards 各几秒，keyframe/video/seedance 这些因为 API 不可用而秒过。后续步骤没跑到。**

---

## 五、为什么 strategy 最慢？深层原因

### 原因 1: LLM 输入 token 量巨大

看 `ProductStrategySkill.execute()`：
```python
system = STRATEGY_SYSTEM_PROMPT  # ~2000 tokens 的英文提示词
# 然后字符串替换注入参数:
injected = {
    "product_catalog": json.dumps(pc, indent=2),    # product JSON, ~300 tokens
    "brand_guidelines": json.dumps(bg, indent=2),   # brand JSON, ~200 tokens
    "target_platforms": json.dumps(platforms),       # 很小
    "target_languages": json.dumps(languages),       # 很小
}
```

每次 strategy 调用，给 LLM 发送约 **2500 tokens 的系统提示词 + 500 tokens 产品数据 = 3000 tokens 输入**。Kimi API 的响应速度随输入长度线性下降。

### 原因 2: LLM 输出 5 条 brief 的 JSON

要求 LLM 输出一个包含 5 条 brief 的大型 JSON 结构，每条 brief 包含 7 个字段。这导致输出 token 数高达 **1000-1500 tokens**。LLM 生成 JSON 比生成纯文本慢。

### 原因 3: 校验规则丢弃率高

5 条 brief 中 4 条因 `video_type` 不在白名单或 `target_platforms` 不匹配被丢弃。这意味着花了 86 秒只得到了 20% 的有效产出。

---

## 六、优化建议

### 优化 1: 策略输出从 5 条降为 3 条（立即见效）

**改动：** `PROMPT_TEMPLATE` 的 "Generate exactly 5 briefs" → "Generate exactly 3 briefs"
**预期效果：** LLM 输出从 1500 tokens 降为 900 tokens，耗时从 ~80s 降为 ~45s

### 优化 2: 放宽 video_type 校验（降低丢弃率）

**改动：** 不因 `video_type` 不在白名单而丢弃 brief——对于不在白名单的类型，用"默认值"替代而非丢弃。
**预期效果：** 5 条 brief 从丢弃 4 条变为全部保留。单次 strategy 调用的有效产出从 1 条变为 5 条。

### 优化 3: strategy + scripts 并行化（架构优化）

**当前：** strategy → scripts（串行依赖）
**可改为：** strategy 返回后，scripts 不需要等 compliance 完成。实际上第 3 步（compliance）跟第 2 步（scripts）可以并行，因为 compliance 审查的是 scripts。

更激进：用 strategy 输出的每条 brief 并行调 LLM 生成脚本。3 条 brief 不是串行生成脚本（3×4s），而是 3 次 LLM 并行调用（~4s total）。

### 优化 4: keyframe_images 和 video_prompts 并行

keyframe_images（GPT-Image 调图）和 video_prompts（规则生成提示词）互不依赖——video_prompts 只需要 scripts，不需要 keyframe_images。这两个可以并行。

同样，thumbnail_prompts 也不需要等 keyframe_images 完成。所以 Step 5/6/7 可以三路并行：

```
storyboards
    ├── keyframe_images  (API: ~30s)
    ├── video_prompts    (规则: ~0.1s)
    └── thumbnail_prompts(规则: ~0.1s)
         ↓
    seedance_clips + thumbnail_images (依赖各自的 prompts)
```

**这是最大的时间优化——从串行 60s 变为并行 30s。**

---

## 七、优化后的预估耗时

```
当前串行:                                   优化后并行:

strategy          86s                     strategy          45s (3 briefs)
scripts           12s (3×4s 串行)         scripts            4s (3 briefs 并行)
compliance         4s                     compliance          4s
storyboards        0.1s                   storyboards         0.1s
                                        ┌─────────────────────────┐
keyframe_images   30s                   │ keyframe    │ video    │ 30s (三路并行)
video_prompts      0.1s                  │ images      │ prompts  │
thumbnail_prompts  0.1s                  │ ~30s        │ ~0.1s    │
                                        └─────────────────────────┘
seedance_clips   180s                    seedance_clips    180s 
tts_audio          5s                    tts_audio           5s (与 seedance 并行)
thumbnail_images  30s                    thumbnail_images   30s (与 seedance 并行)  
assemble_final    20s                    assemble_final     20s
audit              1s                    audit               1s
────────────────────────                ────────────────────────
总计:             ~368s (6 分钟)          总计:              ~270s (4.5 分钟)
```

**预期提速 27%。** 最大收益来自 strategy 输出量减半 + scripts 并行化 + keyframe/video/thumbnail 三路并行。

---

## 八、总结

| 问题 | 根因 | 优化方向 | 预期效果 |
|------|------|---------|---------|
| strategy 86s | 5 条 brief 输出 token 多 + 检验丢弃率高 | 降为 3 条 + 放宽校验 | 45s + 100% 保留率 |
| scripts 12s 串行 | 逐条 brief 串行调 LLM | 3 briefs 并行 | 4s |
| 5/6/7 步串行 | 互不依赖却排队执行 | 三路并行 | 30s (原来 30+0.1+0.1≈30s，但关键是解锁后续步) |
| seedance 180s | API 限制，不可优化 | 缩短 clip 时长、预缓存 | N/A |

**立即可做的（不改架构）：** 策略输出降为 3 条、放宽校验。这两项就能让 strategy 步骤从 86s → 45s，且不丢数据。

要我开始实施优化吗？
