# S2 + S3 深度优化计划

> 对标 S1 已完成的优化层级，逐层分析 S2/S3 的差异化需求

---

## 一、S1 优化清单（对照基准）

| 层 | S1 做了什么 | 对应文件 |
|----|-----------|---------|
| **前端 UI** | +Product Details(usage_scenario, pain_points, target_audience, competitor_context) +Brand Voice(do/dont) | `SceneForm.tsx` |
| **后端 prompt** | +Product Context段 +Data Usage Rules +品牌do/dont指令 | `product_strategy.py` |
| **后端逻辑** | 输出5→3 briefs, 校验修复替代丢弃, scripts并行化 | `product_strategy.py`, `script_writer.py` |

---

## 二、S2 品牌宣传 — 优化计划

### 2.1 当前问题诊断

**代码路径：** `S2BrandCampaignPipeline` → `S1ProductDirectPipeline.run(brand_mode=True)`

```
product_catalog = {"name": "Momcozy", **brand_package}
# brand_package = {brand_name, campaign_theme, key_message, target_audience, ...}
```

**概念错配：** strategy prompt 新增的 "Product Context" 段面向产品语义（pain_points、competitor_context），但 S2 的输入是品牌活动语义（campaign_theme、brand_values、campaign_goal）。LLM 用产品思维处理品牌活动 → brief 偏功能展示而非品牌叙事。

**SceneForm S2 现状：** Brand Package select*, Campaign Theme, Key Message, Target Audience。缺：Campaign Goal、Brand Values、Visual Identity。

### 2.2 前端改动

**文件：** `web/src/components/SceneForm.tsx`（S2 表单段）

新增 "Campaign Details" 可折叠区：

| 字段 | 类型 | 说明 |
|------|------|------|
| Campaign Goal | textarea | 活动目标(e.g. "新品上市拉新", "周年庆品牌好感度") |
| Brand Values | textarea | 品牌核心价值主张，每行一个(e.g. "Empowerment", "Sustainability") |
| Visual Identity | textarea | 视觉规范(e.g. "主色#7CB342, 女性向, 温暖自然光, 禁冷色调") |
| Competitor Campaigns | textarea | 竞品类似活动的参考(e.g. "飞利浦周年庆用了用户证言+产品时间线") |

**State 变量：**
```typescript
const [campaignGoal, setCampaignGoal] = useState("");
const [brandValues, setBrandValues] = useState("");
const [visualIdentity, setVisualIdentity] = useState("");
const [competitorCampaigns, setCompetitorCampaigns] = useState("");
```

**onSubmit 注入：**
```typescript
brand_package: {
  ...existing,
  campaign_goal: campaignGoal,
  brand_values: brandValues.split("\n").filter(Boolean),
  visual_identity: visualIdentity,
  competitor_campaigns: competitorCampaigns.split("\n").filter(Boolean),
}
```

### 2.3 后端改动

**文件：** `src/skills/product_strategy.py`

**改动：** brand_mode=True 时，动态替换 "Product Context" 段为 "Campaign Context" 段。

**实现方式：** 在 `ProductStrategySkill.execute()` 方法中（约 line 174），构建 injected 参数时检查 scenario：

```python
scenario = params.get("content_scenario", "product_direct")
is_brand_campaign = (scenario == "brand_campaign" or params.get("brand_mode"))

system = STRATEGY_SYSTEM_PROMPT

if is_brand_campaign:
    # Replace Product Context with Campaign Context
    system = system.replace(
        "### Product Context (provided by user — USE THIS DATA)",
        "### Campaign Context (brand_mode — USE THIS DATA)"
    )
    # Also swap the detailed product instructions for campaign instructions
    campaign_context = """
- **campaign_goal**: The specific objective of this brand campaign (launch, awareness, loyalty).
  → Every brief's key_message MUST directly support this goal.
  → Match video type to goal: awareness → emotional/story; launch → product_feature.

- **brand_values**: What the brand stands for beyond product features.
  → Every brief must embody at least ONE brand value in its topic or key_message.
  → Don't just mention the value — show it through storytelling.

- **target_audience**: The campaign's target demographic (not just product buyers).
  → Voice, references, and platform choice should match this audience.
  → Campaign content should make the audience FEEL something about the brand.

- **visual_identity**: Color palette, style, visual constraints.
  → Briefs should note any visual requirements (e.g., "use warm natural light").
  → Ensure the storyboard visual_description reflects brand colors/style.

- **competitor_campaigns**: What similar brands have done for similar campaigns.
  → Use as inspiration AND differentiation. What did they do? What can we do BETTER?
  → NEVER mention competitor names in the brief.
"""
    system = system.replace(
        "- **usage_scenario**: The physical/social context where the product is used.",
        campaign_context
    )
```

**注意：** 这要求 `product_strategy.py` 的 STRATEGY_SYSTEM_PROMPT 中 "Product Context" 和 "Campaign Context" 段有明确的切换锚点。最简单的实现是：把 Product Context 段独立为一个变量，根据 scenario 拼接不同的 prompt 段。

**改动量：** ~30 行（在 prompt 构建逻辑中加一个 if 分支）。

### 2.4 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `SceneForm.tsx` | S2 表单新增 4 个字段 + state + onSubmit | ~40 行 |
| `product_strategy.py` | brand_mode 动态切换 Product→Campaign Context | ~30 行 |
| `translations.ts` | 10 个新 i18n key (campaign.*) | ~20 行 |

**总改动量：~90 行。预期效果：Brand Campaign briefs 从产品思维切换为品牌叙事思维。**

---

## 三、S3 网红二创 — 优化计划

### 3.1 当前问题诊断

**代码路径：** S3 不走 strategy 步骤。流程是：

```
video_analysis (LLM: 分析原视频转录文本)
    → character_identity (CV: 人脸检测)
    → remix_script (规则模板: 替换产品名和 USP)
```

**核心问题：**

1. **remix_script 是规则模板，不是 LLM 生成的。** 核心逻辑在 `src/skills/remix_script.py`，遍历原视频的 segments，对每个 segment 做模板字符串替换：

```python
# 当前逻辑 (约 line 246)
"replace": f"Replace with {product_name} content: {replacement['replace']}"
```

这导致替换文本千篇一律——不同原视频、不同产品，替换逻辑完全一样。没有感知原视频的语境、情感基调、语言风格。

2. **video_analysis 只看转录文本。** 不知道原视频是好评还是差评，不知道原视频的用户画像，不知道评论区的反馈。

3. **产品上下文缺失。** S3 的 `product` 参数只有 `name`、`usps`、`brand_name`——没有 pain_points、target_audience 等。但 S3 更需要这些：因为 LLM 需要用新产品替换原视频中的产品，而替换的质量取决于 LLM 对新产品目标用户和使用场景的理解。

### 3.2 前端改动

**文件：** `web/src/components/SceneForm.tsx`（S3 表单段）

在 S3 表单（Video URL*, Product Name*, Influencer Name, Keep Audio）下方新增 "Product Details" 可折叠区，**与 S1 共享相同字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| Usage Scenario | textarea | 产品的使用场景，用于替换原视频中的场景描述 |
| Pain Points | textarea | 产品解决的真实痛点，用于 remix 时的 hook 重写 |
| Target Audience | textarea | 产品目标用户，确保替换后的语音匹配受众 |
| Competitor Context | textarea | 原视频可能提及的竞品，以及差异化点 |

**实现方式：** 提取 S1 的 Product Details 段为一个共享子组件或在 S3 段中复用相同代码。

### 3.3 后端改动

#### 3.3.1 remix_script.py — 从规则模板升级为 LLM 驱动

**文件：** `src/skills/remix_script.py`

**改动：** 将 `_build_remix_segments()` 从纯规则函数改为 LLM 驱动：

```python
# 当前: 规则模板
def _build_remix_segments(self, segments, product_name, usps, ...):
    for seg in segments:
        seg_type = seg.get("segment_type")
        replacement = SEGMENT_REPLACEMENT_TEMPLATES.get(seg_type, ...)
        remix_segments.append({
            "replace": f"Replace with {product_name} content: {replacement['replace']}"
        })

# 优化: LLM 驱动
async def _build_remix_segments(self, segments, product_name, usps, 
                                  pain_points, target_audience, competitor_context, ...):
    # Build a prompt that gives the LLM FULL context
    prompt = f"""You are remixing an influencer video to feature a new product.
    
    Original video structure: {json.dumps(segments)}
    New product: {product_name}
    Product USPs: {usps}
    Pain points it solves: {pain_points}
    Target audience: {target_audience}
    Competitor differentiation: {competitor_context}
    
    For each segment, generate a remix that:
    1. Preserves the original video's emotional rhythm and pacing
    2. Replaces product mentions naturally within the influencer's style
    3. Addresses the actual pain points the new product solves
    4. Differentiates from competitors without naming them
    
    Return JSON with remixed segments."""
    
    # Call LLM
    remix_result = await llm.invoke_json(prompt)
    return remix_result["segments"]
```

**回退机制：** LLM 不可用时，回退到当前的规则模板。这是 SkillCallable 已有的 fallback 机制。

#### 3.3.2 video_analysis.py — 跳过（本次不改）

video_analysis 的增强（多维输入：画面标签、评论区情感）需要视频理解模型升级，不在本次 scope。

#### 3.3.3 S3 Pipeline — 传递产品上下文

**文件：** `src/pipeline/s3_remix_pipeline.py`

**改动：** 在 `_step_remix_script` 中，将 product context 字段传递给 remix-script-skill：

```python
# 当前 (约 line 288)
result = await self._registry.execute("remix-script-skill", {
    "analysis": analysis.data,
    "product": product,
    "target_language": target_language,
})

# 优化
result = await self._registry.execute("remix-script-skill", {
    "analysis": analysis.data,
    "product": product,
    "target_language": target_language,
    "product_context": {
        "pain_points": product.get("pain_points", []),
        "target_audience": product.get("target_audience", ""),
        "competitor_context": product.get("competitor_context", []),
        "usage_scenario": product.get("usage_scenario", ""),
    },
})
```

#### 3.3.4 S3 API — 中文翻译穿透

**文件：** `src/api.py`

**改动：** S3 endpoint（`POST /scenario/s3`）已调用 `translate_catalog_to_english()`。验证它处理嵌套的 `products[0]` 字段（如 pain_points, target_audience）。当前 `translate.py` 只翻译 top-level `name`/`usps`，需扩展。

### 3.4 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `SceneForm.tsx` | S3 表单新增 Product Details 区（复用 S1 字段） | ~30 行 |
| `remix_script.py` | `_build_remix_segments` 规则→LLM，fallback 保留 | ~50 行 |
| `s3_remix_pipeline.py` | `_step_remix_script` 传递 product_context | ~10 行 |
| `api.py` | S3 endpoint product 字段传递完整 | ~5 行 |
| `translate.py` | 扩展嵌套 product fields 翻译 | ~15 行 |
| `translations.ts` | 复用已有 key，新增少量 S3 特定 | ~5 行 |

**总改动量：~115 行。预期效果：S3 替换文本从机械模板升级为语境感知的 LLM 生成。**

---

## 四、执行优先级

| # | 场景 | 改动 | 文件数 | 预估 |
|---|------|------|--------|------|
| 1 | **S2** | 前端 Campaign Details + 后端 Prompt 品牌段切换 | 3 | 90 行 / 1h |
| 2 | **S3** | 前端 Product Details + remix_script LLM 化 + Pipeline 穿透 | 5 | 115 行 / 1.5h |
| 3 | **S3** | translate.py 嵌套字段翻译 | 1 | 15 行 / 0.3h |

**总计：~220 行，约 2.5 小时。三轨并行执行可压缩到 1 小时。**

### S3 的已知硬边界（本次不改）

- **通道 B 产品替换（SAM 分割 + 泊松融合）：** 需要视频处理模型，工程量大，不在本次 scope
- **video_analysis 多维输入（画面标签 + 评论区）：** 需要视频理解 API 升级
- **人脸一致性保证：** AI 模型硬限制，character_identity + continuity_chain 已是当前最优方案

---

*计划制定：2026-04-29 凌晨 | 下一步：用户确认后启动执行*
