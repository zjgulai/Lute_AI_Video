# S2 + S3 深度优化计划 v2

> 对照 S1 优化基准 | 新增视频理解 API 升级 | 完整的 S1 保护审计

---

## 零、S1 保护审计（所有改动的前置验证）

### 0.1 改动影响矩阵

| 改动文件 | S1 路径 | 影响评估 | 保护措施 |
|---------|---------|---------|---------|
| `SceneForm.tsx` +S2/S3 字段 | S1 表单段 | ✅ 无影响 — S2/S3 字段在独立的条件渲染块中 | 新增字段只在 `scene === "brand_campaign"` 或 `scene === "influencer_remix"` 时渲染 |
| `product_strategy.py` +brand_mode 切换 | S1 strategy 步 | ⚠️ 风险 — if 分支逻辑需确保 brand_mode=False 时走原路径 | 加 `assert brand_mode == False` 时 prompt 完全不变的自证；单元测试 |
| `remix_script.py` +LLM 模式 | S1 — 不使用 | ✅ 无影响 — S1 不使用 remix_script | N/A |
| `s3_remix_pipeline.py` +product_context | S1 — 不使用 | ✅ 无影响 | N/A |
| `video_analysis.py` +视觉分析 | S3 — 使用 | ✅ 无影响 — 新功能是可选参数 | 默认 `enable_visual_analysis=False`，不影响现有调用 |
| `translate.py` +嵌套翻译 | S1/S3 共用 | ⚠️ 低风险 — 扩展而非改动 | 新增字段 `pain_points` 等，不存在时跳过 |

### 0.2 S1 不变性验证清单

执行改动后逐条验证：

```
[ ] POST /scenario/s1 auto 模式返回相同结构（briefs, scripts, clip_paths, final_video_path, audit_report）
[ ] POST /scenario/s1/start step_by_step 模式 12 步顺序不变
[ ] S1 SceneForm — 5 个字段（Product Name, Brand, Key Features, Category, Product Details）渲染不变
[ ] S1 SceneForm — onSubmit 返回的 config shape 不变
[ ] S1 strategy — brand_mode=False 时 system prompt 不变（grep 验证无 campaign_context 注入）
[ ] S1 scripts — 并行化执行不变
[ ] S1 所有现有测试用例通过（如可运行）
```

---

## 一、S1 优化基准（已完成，作为对照）

| 层 | S1 做了什么 |
|----|-----------|
| **前端 UI** | +Product Details(usage_scenario, pain_points, target_audience, competitor_context) +Brand Voice(do/dont) |
| **后端 prompt** | +Product Context段 +Data Usage Rules +品牌do/dont指令 |
| **后端逻辑** | 输出5→3 briefs, 校验修复替代丢弃, scripts并行化 |

---

## 二、S2 品牌宣传 — 优化计划

### 2.1 前端：SceneForm S2 Campaign Details

**文件：** `web/src/components/SceneForm.tsx`

在现有 S2 字段（Brand Package*, Campaign Theme, Key Message, Target Audience）下方，新增可折叠 "Campaign Details" 区：

| 字段 | State | 说明 |
|------|-------|------|
| Campaign Goal | `campaignGoal` | textarea — 活动目标 (e.g. "新品上市拉新", "品牌周年庆") |
| Brand Values | `brandValues` | textarea — 品牌核心价值，每行一个 |
| Visual Identity | `visualIdentity` | textarea — 视觉规范 (e.g. "主色#7CB342, 禁冷色调") |
| Competitor Campaigns | `competitorCampaigns` | textarea — 竞品类似活动的参考 |

**onSubmit 注入：**
```typescript
// S2 onSubmit
brand_guidelines: {
  brand_name: brandName,
  campaign_theme: campaignTheme,
  key_message: keyMessage,
  target_audience: targetAudience,
  campaign_goal: campaignGoal,
  brand_values: brandValues.split("\n").filter(Boolean),
  visual_identity: visualIdentity,
  competitor_campaigns: competitorCampaigns.split("\n").filter(Boolean),
  // existing fields preserved
}
```

**S1 保护：** 新增字段全部在 `{scene === "brand_campaign" && (...)}` 块内。S1 渲染路径零改动。

### 2.2 后端：strategy prompt 品牌段动态切换

**文件：** `src/skills/product_strategy.py`

**实现：** 在 `execute()` 方法中，检测 scenario：

```python
scenario = params.get("content_scenario", "product_direct")
is_brand = (scenario == "brand_campaign")

if is_brand:
    system = STRATEGY_SYSTEM_PROMPT_BRAND  # 独立的品牌版 prompt
else:
    system = STRATEGY_SYSTEM_PROMPT  # 原有的产品版 prompt（不改）
```

**品牌版 prompt（`STRATEGY_SYSTEM_PROMPT_BRAND`）：**

```
### Campaign Context (brand_mode — USE THIS DATA)
The brand campaign brief includes rich campaign context. USE it in every brief:

- **campaign_goal**: The specific objective (launch, awareness, loyalty, anniversary).
  → Every brief's key_message MUST directly support this goal.
  → Match video type to goal: awareness → emotional/story; launch → product_feature.

- **brand_values**: What the brand stands for beyond product features.
  → Every brief must embody at least ONE brand value.
  → Show the value through storytelling, not just mentioning it.

- **target_audience**: The campaign's demographic (not just product buyers).
  → Voice, references, platform should match this audience.

- **visual_identity**: Color palette, style constraints.
  → Storyboard visual_description must reflect these.

- **competitor_campaigns**: What similar brands have done.
  → Inspire BUT differentiate. Never name competitors.
```

**S1 保护：** `STRATEGY_SYSTEM_PROMPT`（原版）完全不动。`STRATEGY_SYSTEM_PROMPT_BRAND` 是新增独立变量。`execute()` 中的分支逻辑确保 `brand_mode=False` 时走原路径。

### 2.3 改动清单

| 文件 | 改动 | 保护 S1? |
|------|------|---------|
| `SceneForm.tsx` | +4 个 campaign 字段 | ✅ scene 条件守卫 |
| `product_strategy.py` | +STRATEGY_SYSTEM_PROMPT_BRAND, +is_brand 分支 | ✅ 原 prompt 不动 |
| `translations.ts` | +10 个 campaign.* 键 | ✅ 新增不影响 |

---

## 三、S3 网红二创 — 优化计划

### 3.1 前端：SceneForm S3 Product Details

**文件：** `web/src/components/SceneForm.tsx`

S3 表单现有字段：Video URL*, Product Name*, Influencer Name, Keep Audio。

在下方新增 "Product Details" 可折叠区（**与 S1 共享相同的字段结构和 state 变量**）：

| 字段 | 说明 |
|------|------|
| Usage Scenario | 产品使用场景 |
| Pain Points | 真实用户痛点，每行一个 |
| Target Audience | 目标用户画像 |
| Competitor Context | 竞品差异化，每行一个 |

**实现方式：** 提取为共享子组件 `ProductDetailsFields`，S1 和 S3 都渲染它。避免代码重复，同时保证 S1 不受 S3 改动影响。

**onSubmit 注入：**
```typescript
// S3 onSubmit — product 扩展
product: {
  name: productName,
  usps: usps,
  usage_scenario: usageScenario,
  pain_points: painPoints.split("\n").filter(Boolean),
  target_audience: productTargetAudience,
  competitor_context: competitorContext.split("\n").filter(Boolean),
}
```

### 3.2 后端：remix_script LLM 化

**文件：** `src/skills/remix_script.py`

**核心改动：** `_build_remix_segments()` 方法。

- **当前：** 纯规则模板，逐 segment 做字符串替换
- **改为：** 默认 LLM 驱动（一次 LLM 调用处理所有 segments），规则模板作为 fallback

**LLM prompt 设计：**

```python
REIX_SYSTEM_PROMPT = """You are a video remix specialist. Given an influencer's original video
structure and a new product, rewrite the video script so the influencer promotes the NEW product
while preserving their authentic style, emotional rhythm, and personality.

## Data You Receive
- Original video segments (with type, timing, original content description)
- New product info (name, USPs, pain points it solves, target audience)
- Competitor differentiation points

## Rules
1. PRESERVE the original video's segment structure and emotional pacing
2. PRESERVE the influencer's speech style and catchphrases
3. REPLACE product mentions naturally — don't force it
4. USE the provided pain_points as hook angles
5. DIFFERENTIATE from competitors without naming them
6. Return JSON with remixed segments matching the original count and timing

Return ONLY valid JSON."""

REIX_USER_TEMPLATE = """Original Video Analysis:
{analysis_json}

New Product:
{product_json}

Product Context:
- Pain Points: {pain_points}
- Target Audience: {target_audience}
- Competitor Context: {competitor_context}
- Usage Scenario: {usage_scenario}

Remix this video for the new product. Return {segment_count} segments."""

async def _build_remix_segments_llm(self, analysis, product, product_context):
    """LLM-driven remix — one call handles all segments."""
    result = await llm.invoke_json(system, user)
    return result["segments"]
```

**保险机制：**
- LLM 调用失败 → 回退到 `_build_remix_segments_rules()`（当前规则模板）
- 保留当前的 `SEGMENT_REPLACEMENT_TEMPLATES` 作为 fallback
- `execute()` 方法中：先尝试 LLM，失败则走 fallback

### 3.3 后端：视频理解 API 升级

**文件：** `src/skills/video_analysis.py`

**当前状态：** `_analyze_transcription()` 只看 Whisper 转录文本。不知道视频画面内容。

**升级方案：** 新增 `_analyze_frames()` 方法，提取关键帧并调用视觉 LLM：

```python
async def _analyze_frames(self, video_path: str, transcription_text: str) -> dict:
    """Extract key frames and analyze them with a vision model.
    
    Returns visual context: products visible, setting, lighting, camera style,
    influencer appearance, visual transitions.
    """
    import subprocess
    from pathlib import Path
    
    # 1. Extract frames at 20% intervals (5 frames for a 30s video)
    # ffmpeg -i video.mp4 -vf "select=not(mod(n\,60))" -frames:v 5 frames/frame_%03d.jpg
    frame_dir = Path(video_path).parent / "frames"
    frame_dir.mkdir(exist_ok=True)
    
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vf", "fps=1/6",  # 1 frame every 6 seconds
        "-frames:v", "5",
        f"{frame_dir}/frame_%03d.jpg",
        "-y"
    ], capture_output=True)
    
    # 2. Send frames to vision model (Kimi/Moonshot vision)
    frames = sorted(frame_dir.glob("frame_*.jpg"))
    
    # Build a vision prompt with frame descriptions
    vision_prompt = f"""Analyze these frames from an influencer product review video.
    Transcript: {transcription_text[:500]}...
    
    Describe: 
    1. Products visible in frame (brands, types, positions)
    2. Setting/environment (indoor/outdoor, lighting, room type)
    3. Camera style (angles, shot types, movement)
    4. Influencer appearance (clothing, expression, body language)
    5. Visual transitions between frames
    
    Return JSON."""
    
    # Call Kimi vision API
    vision_result = await llm.invoke_json(vision_prompt, images=frames)
    return vision_result
```

**注入到 execute()：**
```python
async def execute(self, params: dict) -> SkillResult:
    ...
    transcription = await self._downloader.transcribe(video_url)
    
    # NEW: Visual analysis (optional, controlled by param)
    enable_visual = params.get("enable_visual_analysis", False)
    visual_context = None
    if enable_visual and download.local_path:
        try:
            visual_context = await self._analyze_frames(
                download.local_path, 
                transcription_text
            )
        except Exception:
            logger.warning("visual analysis failed, continuing with text-only")
    
    # Pass visual context into analysis
    result = self._analyze_transcription(
        transcription=transcription,
        video_url=video_url,
        visual_context=visual_context,
        ...
    )
```

**S1 保护：** `enable_visual_analysis` 默认 `False`。S1 不调用 video_analysis — 零影响。

### 3.4 后端：S3 Pipeline 穿透 product_context

**文件：** `src/pipeline/s3_remix_pipeline.py`

**改动：** `_step_remix_script` 传递扩展后的 product 参数：

```python
# 约 line 288
product_context = {
    "pain_points": product.get("pain_points", []),
    "target_audience": product.get("target_audience", ""),
    "competitor_context": product.get("competitor_context", []),
    "usage_scenario": product.get("usage_scenario", ""),
}

result = await self._registry.execute("remix-script-skill", {
    "analysis": analysis.data,
    "product": product,
    "product_context": product_context,
    "target_language": target_language,
})
```

### 3.5 后端：translate.py 嵌套字段扩展

**文件：** `src/tools/translate.py`

**当前：** `translate_catalog_to_english()` 只处理 top-level `name` 和 `usps`。

**扩展：** 处理 `products[0]` 下的嵌套字段：

```python
async def translate_catalog_to_english(catalog: dict) -> dict:
    """Translate Chinese product fields to English. Handles nested products[0]."""
    if not isinstance(catalog, dict):
        return catalog
    
    # Top level
    if has_chinese(catalog.get("name", "")):
        catalog["name"] = await translate_to_english(catalog["name"])
    
    # Nested products[0]
    products = catalog.get("products", [])
    if products and isinstance(products, list):
        p = dict(products[0])
        for field in ["name", "usage_scenario", "target_audience"]:
            if has_chinese(p.get(field, "")):
                p[field] = await translate_to_english(p[field])
        # Translate pain_points (list of strings)
        if "pain_points" in p and isinstance(p["pain_points"], list):
            p["pain_points"] = [
                await translate_to_english(pp) if has_chinese(pp) else pp
                for pp in p["pain_points"]
            ]
        # Translate competitor_context (list of strings)
        if "competitor_context" in p and isinstance(p["competitor_context"], list):
            p["competitor_context"] = [
                await translate_to_english(cc) if has_chinese(cc) else cc
                for cc in p["competitor_context"]
            ]
        catalog["products"][0] = p
    
    return catalog
```

**S1 保护：** 新增字段检查 `has_chinese()` — 纯英文输入直接跳过。S1 的翻译行为不变。

---

## 四、执行计划（三轨并行）

### Track A: S2 品牌宣传优化（~90 行, ~1h）

| 文件 | 改动 |
|------|------|
| `SceneForm.tsx` | +Campaign Details 可折叠区(4 字段) + 10 i18n keys |
| `product_strategy.py` | +STRATEGY_SYSTEM_PROMPT_BRAND + is_brand 分支 |

### Track B: S3 remix_script LLM 化（~100 行, ~1h）

| 文件 | 改动 |
|------|------|
| `SceneForm.tsx` | S3 Product Details 区(复用 S1 字段) |
| `remix_script.py` | +LLM prompt + _build_remix_segments_llm + fallback |
| `s3_remix_pipeline.py` | _step_remix_script 传递 product_context |
| `translations.ts` | 复用已有 key |

### Track C: 视频理解 + 翻译扩展（~80 行, ~1h）

| 文件 | 改动 |
|------|------|
| `video_analysis.py` | +_analyze_frames + execute 集成 |
| `translate.py` | +嵌套 product fields 翻译 |

### S1 保护验证（三轨完成后统一执行）

```bash
# S1 auto 模式不变
curl -X POST localhost:8001/scenario/s1 -d '{...}' | python3 -c "assert 'briefs' in ..., 'S1 shape broken'"

# S1 strategy prompt 在 brand_mode=False 时不注入 campaign_context
grep -c "campaign_context" src/skills/product_strategy.py | grep -v "is_brand"

# 后端全量编译
python3 -m py_compile src/skills/product_strategy.py src/skills/remix_script.py src/skills/video_analysis.py src/tools/translate.py src/pipeline/s3_remix_pipeline.py

# 前端类型检查
npx tsc --noEmit
```

---

## 五、总改动量

| Track | 场景 | 文件数 | 行数 |
|-------|------|--------|------|
| A | S2 品牌 | 2 | ~90 行 |
| B | S3 remix | 4 | ~100 行 |
| C | 视频理解 | 2 | ~80 行 |
| **总计** | **S2+S3** | **8** | **~270 行** |

---

*计划制定：2026-04-29 凌晨 v2 | 新增视频理解 API 升级 + 完整 S1 保护审计 + 三轨并行执行架构*
