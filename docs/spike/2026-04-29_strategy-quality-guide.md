# 内容策略质量提升指南

> 分析：当前策略步骤为什么不稳定 + 需要什么数据才能稳定产出高质量 brief

---

## 一、当前为什么不稳定

你实测的 strategy 步骤：5 条 brief 中 4 条被校验丢弃。表面看是校验太严——但根因是 **LLM 的信息贫乏**。它拿着最少的信息做最大的决策。

当前 strategy 的 LLM prompt 实际传递的内容：

```
产品信息: {"name": "孕妇枕", "usps": ["ergonomic", "breathable"]}
品牌信息: {"brand_name": "Momcozy", "tone_of_voice": {"archetype": "Caregiver"}}
目标平台: ["tiktok", "shopify"]
语言: ["en"]
场景: "product_direct"
```

**就这 5 个字段，要求 LLM 生成 3 条完整的视频策略。**

LLM 不知道：
- 孕妇枕的使用场景是产前还是产后？床上还是沙发？
- Momcozy 的品牌调性"Caregiver"具体是什么语气？温暖如母婴博主还是专业如医生？
- 目标用户是初产妇还是经产妇？年龄多大？在什么平台获取信息？
- 竞争对手是谁？他们的视频怎么做的？凭什么你的视频能赢？

**LLM 只能在黑暗中猜测。** 所以 5 条 brief 中 4 条跑偏——不是校验太严，是 LLM 根本没被给够弹药。

---

## 二、你应该提供什么数据

按影响力从高到低排列。**标 ★ 的是立即可做、投入最小、回报最大的。**

### ★ 第一层：产品上下文（现在就能提供）

| 数据 | 为什么重要 | 当前状态 |
|------|-----------|---------|
| **产品品类 category** | 决定内容策略框架。婴儿用品和电子产品的视频策略完全不同。 | ❌ 缺失 |
| **使用场景 usage_scenario** | 决定视频中的画面、人物、环境。在卧室用 vs 办公室用 → 完全不同的视觉策略。 | ❌ 缺失 |
| **目标用户画像 target_audience** | 决定语气、选题角度。25 岁新手妈妈 vs 35 岁二胎妈妈 → 不同 hook。 | ❌ 只在 brief 输出中要求 LLM 编 |
| **核心痛点 pain_points** | 这是 hook 的原材料。没有真实痛点，hook 只能是泛泛而谈。 | ❌ 缺失 |
| **竞品参考 competitor_context** | 让 LLM 知道"不要做什么"和"怎么差异化"。 | ❌ 只在 brief schema 中有字段但用户不填 |

**建议输入模板：**
```json
{
  "product_catalog": {
    "name": "Maternity Pillow",
    "category": "pregnancy_sleep_aid",
    "usps": [
      {"priority": "P0", "text": "Ergonomic U-shape supports back and belly simultaneously", "visual_demo": "360° rotation shot showing full body support"},
      {"priority": "P1", "text": "Breathable organic cotton cover, machine washable", "visual_demo": "Close-up fabric texture + water droplet test"},
      {"priority": "P2", "text": "Multi-position: sleep, nursing, lounging", "visual_demo": "Three quick cuts showing each position"}
    ],
    "usage_scenario": "Bedroom, third trimester through postpartum. Used during sleep, reading, nursing.",
    "pain_points": [
      "Can't find a comfortable sleeping position after 28 weeks",
      "Wake up with lower back pain every morning",
      "Regular pillows slide around and need constant adjustment",
      "Nursing pillow + sleep pillow = too many pillows cluttering the bed"
    ],
    "target_audience": {
      "primary": {"demographic": "Pregnant women 25-35", "behavior": "Researches products on TikTok and Amazon reviews", "trigger": "Hits third trimester and sleep becomes impossible"},
      "secondary": {"demographic": "Gift buyers (partners, parents, baby shower guests)", "behavior": "Searches 'best gift for pregnant wife' on Google and Amazon"}
    },
    "competitor_context": [
      {"name": "PharMeDoc", "strength": "Cheaper price point, Amazon bestseller badge", "weakness": "Basic C-shape, less versatile, cover not removable"},
      {"name": "Boppy", "strength": "Brand recognition, multi-use marketing", "weakness": "Primarily a nursing pillow, not optimized for sleep"}
    ],
    "price_positioning": "premium_mid",
    "certifications": ["FDA", "CE", "OEKO-TEX certified organic cotton"]
  }
}
```

**有了这些数据，LLM 可以直接生成：**
- "I'm 34 weeks pregnant and haven't slept through the night in 2 months — until I found this" (真实痛点驱动 hook)
- "Stop buying two pillows. This one U-shape replaces both your sleep pillow AND nursing pillow" (竞品差异化)
- "My husband bought this for me at 30 weeks. Here's why it's the best baby shower gift" (次要用户画像)

### ★ 第二层：品牌声音样本（现在就能提供）

| 数据 | 为什么重要 |
|------|-----------|
| **Do's / Don'ts 样本** | "warm and empowering" 太抽象。给 3 对正反例，LLM 立刻理解。 |

**建议输入模板：**
```json
{
  "brand_guidelines": {
    "brand_name": "Momcozy",
    "tone_of_voice": {
      "archetype": "Caregiver",
      "do_examples": [
        "💬 'I didn't believe a pillow could fix my back pain either. Week 32 proved me wrong.'",
        "💬 'Your body is doing something incredible. Let it rest.'",
        "💬 '3am feedings are hard enough. Your pillow shouldn't make them harder.'"
      ],
      "dont_examples": [
        "❌ 'Revolutionary ergonomic design with patented lumbar support technology' — too corporate",
        "❌ 'BUY NOW! 50% OFF! Limited stock!' — too aggressive",
        "❌ 'Doctors hate this one weird pillow trick' — clickbait, damages trust"
      ],
      "forbidden_words": ["cheap", "discount", "miracle", "cure", "guaranteed"]
    }
  }
}
```

### ★ 第三层：成功内容参考（现在就能提供）

| 数据 | 为什么重要 |
|------|-----------|
| **参考视频链接/描述** | LLM 可以模仿成功模式而非从零发明。 |

**建议输入模板：**
```json
{
  "content_references": {
    "good_examples": [
      {"platform": "tiktok", "description": "@momcozyofficial video 'day in life with wearable pump' — 2.3M views. POV format, no talking first 3 seconds, text overlays only, shows product in real use at desk then at park", "why_it_works": "Authentic POV, product demo in context, no hard sell"},
      {"platform": "tiktok", "description": "@babylist 'registry must-haves' series — educational format, host talks directly to camera, product appears at 0:45 mark as solution to stated problem", "why_it_works": "Builds trust first, product is the natural solution not a forced insertion"}
    ],
    "bad_examples": [
      {"platform": "tiktok", "description": "Generic slideshow with stock music and text overlay listing features", "why_it_fails": "No human connection, looks like an ad, zero engagement"}
    ]
  }
}
```

---

## 三、数据驱动 vs 当前状态对比

| 维度 | 当前（给 LLM 的数据） | 建议（给 LLM 的数据） | 质量提升 |
|------|---------------------|---------------------|---------|
| 产品理解 | `{"name": "孕妇枕", "usps": ["ergonomic"]}` | 品类 + 使用场景 + 3 个真实痛点 | **Hook 质量 ↑↑↑** |
| 用户理解 | 无（LLM 自己编） | 主/次要用户画像 + 购买触发点 | **选题精准度 ↑↑** |
| 品牌调性 | `"archetype": "Caregiver"` | 3 个 do 样本 + 3 个 don't 样本 | **文案一致性 ↑↑** |
| 差异化 | 无 | 竞品优劣势对比 + 价格定位 | **USP 说服力 ↑↑** |
| 内容参考 | 无 | 2 个成功案例 + 1 个失败案例 | **格式稳定性 ↑↑↑** |

---

## 四、实施路径

### 今天可做（零代码改动）

1. 为 "孕妇枕" 准备一份完整的产品上下文 JSON（按上面的模板）
2. 为 "Momcozy" 准备品牌声音样本（3 个 do + 3 个 don't）
3. 手工替换进 strategy 的 system prompt，重新跑一次 strategy step
4. 对比 before/after 的 brief 质量

### 明天可做（小代码改动）

1. 在 `strategy_source/product_direct/strategy_prompt.md` 中加入数据注入点
2. 在 SceneForm 中增加 "产品详情" 可选扩展区（category, usage_scenario, pain_points）
3. 让 strategy step 读取这些扩展字段注入 prompt

### 本周可做（产品增强）

1. 品牌资产包增加 "tone_of_voice" 的正反例字段
2. 产品目录增加 "category"、"pain_points"、"competitor_context"
3. 创建内容参考库（品牌方上传成功视频链接）

---

## 五、总结

**你不需要给我更多数据。你需要给 LLM 更多数据。**

当前策略质量不稳定的根因不是 prompt 写得不好，而是 prompt 里注入的产品/品牌/用户信息太少。LLM 不是魔法——它需要燃料。

最低成本验证：拿 "孕妇枕" 产品，手工写一份完整的上下文 JSON，替换进 strategy 调用。对比两次生成的 brief 质量差异。如果显著提升，就证明方向正确——然后我们用代码把数据注入流程自动化。
