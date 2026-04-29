# 产品深度讨论 v2 —— 三场景入口、双模式架构、审批节点、决策机制

> 基于 2026-04-28 深夜整轮深度讨论记录
> 包含：三场景入口重设计、专家/量产双模式命名与架构、4 Gate 审批流、3 候选 1 推荐机制、AI 时长推荐

---

## 一、三场景入口重设计

### 1.1 当前问题

当前 SceneSelector 用 2×2 网格平铺三个场景卡片。三个场景视觉权重相同，缺乏引导性，场景差异不直观——用户无法从卡片上感知到"这个场景能给我什么"。

### 1.2 设计原则

- **差异前置：** 用户在选择场景之前就应该感知三个场景的本质不同
- **最近的路径是最短的路径：** 每个场景的输入表单不同，应该在入口就区分开
- **视觉层级：** 产品直拍（使用频率最高、门槛最低）应该获得最大视觉权重

### 1.3 推荐方案：三页签 + 独立表单

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                   Create Videos with AI                      │
│                                                             │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│   │  🎬           │  │  🏷           │  │  👤           │     │
│   │  Product      │  │  Brand       │  │  Influencer   │     │
│   │  Showcase     │  │  Campaign    │  │  Remix        │     │
│   │              │  │              │  │              │     │
│   │  输入产品信息  │  │  上传品牌资产  │  │  粘贴视频链接  │     │
│   │  AI 生成展示  │  │  统一调性输出  │  │  保留人设植入  │     │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│          │                 │                 │              │
│          ▼                 ▼                 ▼              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           动态表单区（根据选中场景切换）               │   │
│   │                                                     │   │
│   │  Product Showcase 模式下:                            │   │
│   │  ┌─────────────────────────────────────────────┐    │   │
│   │  │ Product Name *  [e.g. Maternity Pillow    ] │    │   │
│   │  │ Brand           [Momcozy                  ] │    │   │
│   │  │ Key Features    [每行一个卖点...           ] │    │   │
│   │  └─────────────────────────────────────────────┘    │   │
│   │                                                     │   │
│   │  ┌─ Advanced Options ─────────────────────────┐     │   │
│   │  │ Platform  [TikTok] [Shopify] [Instagram]   │     │   │
│   │  │ Mode      [● Smart Create  ○ Expert Studio]│     │   │
│   │  └────────────────────────────────────────────┘     │   │
│   │                                                     │   │
│   │  [Generate Video →]                                 │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   右侧: 场景预览卡片（静态示例视频 + 典型用例）               │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 三个场景的独立表单设计

**S1 商品直拍 — 输入：纯文本**
```
Product Name *         [                                 ]
Brand (optional)       [                                 ]
Key Features           [                                 ]
                       [                                 ]
                       [                                 ]
Category (optional)    [▼ Home / Baby / Electronics / ...]
```

**S2 品牌宣传 — 输入：品牌资产 + 活动信息**
```
Brand Package *        [▼ Select or Upload New           ]
Campaign Theme         [e.g. 10th Anniversary / New Launch]
Key Message            [                                 ]
Target Audience        [                                 ]
Brand Assets           [📎 Upload logos, fonts, color palette]
```

**S3 网红二创 — 输入：视频链接 + 产品**
```
Influencer Video URL * [https://tiktok.com/@user/video/..]
  or Upload File       [📎 Upload .mp4                    ]
Product to Feature *   [                                 ]
Influencer Name        [                                 ]
Keep Original Audio    [✓] Preserve influencer's voice
```

### 1.5 首页布局方案

```
┌────────────────────────────────────────────────────────────┐
│  Nav  [Home] [Brand Assets] [Influencers] [Library]  [EN]  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│   │  🎬       │ │  🏷       │ │  👤       │                  │
│   │ Product  │ │  Brand   │ │Influencer│                  │
│   │ Showcase │ │ Campaign │ │  Remix   │                  │
│   │          │ │          │ │          │                  │
│   │ 0 videos │ │ 0 videos │ │ 0 videos │                  │
│   │ created  │ │ created  │ │ created  │                  │
│   └──────────┘ └──────────┘ └──────────┘                  │
│                                                            │
│   ┌──────────────────────────────────────────────────┐    │
│   │                                                  │    │
│   │      [动态表单 — 根据选中的场景卡片变化]           │    │
│   │                                                  │    │
│   └──────────────────────────────────────────────────┘    │
│                                                            │
│   ┌──────────────────────────────────────────────────┐    │
│   │  Recent Videos (scroll horizontally)              │    │
│   │  [🎬 Pillow] [🎬 Pump] [🎬 Teether] [New +]       │    │
│   └──────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

---

## 二、双模式架构 —— 命名与深化

### 2.1 命名方案

| 面向用户 | 中文名 | English | 一句话定义 |
|---------|--------|---------|-----------|
| 视频运营达人 / 普通员工 | **智能快创** | Smart Create | 输入产品，一键生成可发布视频。AI 自动完成所有决策。 |
| 资深媒体人 / 内容总监 | **专家工作台** | Expert Studio | 逐步审核每道工序，对比候选方案，精准控制最终产出。 |

### 2.2 切换机制

模式切换不是在首页完成——**是在确认输入之后、开始生成之前**。

```
用户操作流：

1. 选择场景 → 填写表单 → 点击 [Continue →]
2. 系统展示 AI 推荐配置:
   ┌──────────────────────────────────────────────┐
   │  AI Recommendation                           │
   │                                              │
   │  Duration:    30-45s (recommended)           │
   │  Platforms:   TikTok + Shopify               │
   │  Tone:        Warm, empowering, maternal     │
   │  Clips:       3 shots                        │
   │                                              │
   │  [Adjust Manually]  [Looks Good, Start →]    │
   └──────────────────────────────────────────────┘
3. 点击 "Start" 后——这是分叉点:
   - Smart Create 用户 → 直接进入生成等待页面
   - Expert Studio 用户 → 进入专家工作台（见第三章）
```

### 2.3 两种模式的产品差异

| 维度 | 智能快创 Smart Create | 专家工作台 Expert Studio |
|------|----------------------|-------------------------|
| 目标用户 | 运营、达人、批量生产者 | 内容总监、品牌经理、创意负责人 |
| 生成前 | 填写最少信息 → 确认推荐 | 可细调每个参数 |
| 生成中 | 3 阶段进度条，全自动 | 12 步可暂停，每 Gate 审批 |
| 候选方案 | 自动选最优，不可见 | 3 候选展示，人工选 1-2 |
| 视频数量 | 固定 3 clips → 1 final | 每 Gate 可选择保留几条 |
| 产出速度 | 2-5 分钟 / 条 | 10-30 分钟 / 条（含审批） |
| 失败处理 | 自动重试，静默 | 展示失败详情，逐个决策 |
| 使用频率 | 每天 5-20 条 | 每天 1-3 条（重要素材） |

### 2.4 为什么不能合并为一个模式

- 专家工作台暴露的复杂度对量产用户是噪音——他们不需要看到 `keyframe_images` 步骤
- 量产模式的自动化决策对专家用户是失控——他们需要知道"AI 替我做了哪些选择"
- 两条路径的代码复用在于**引擎层**（同样的 12 步管线），但**交互层**（何时暂停、展示什么）完全不同

---

## 三、审批节点设计 —— 4 Gate 专家工作台

### 3.1 Gate 总览

```
智能快创:  start ──────────────────────────────────────────→ finish
              │                                                │
专家工作台:  start → [Gate 1] → [Gate 2] → [Gate 3] → [Gate 4] → finish
                      选脚本      审画面      选片段      终审通过
```

### 3.2 Gate 1：选脚本 📝

**上游步骤：** strategy → scripts (×3 candidates) → compliance

**展示内容：**
```
┌──────────────────────────────────────────────────────────────┐
│  Gate 1: Select Script                    [2 of 12 complete] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Candidate A (Recommended) ──────────────────────────┐    │
│  │  Score: 92%  |  Hook: Pain Point  |  30s TikTok      │    │
│  │                                                       │    │
│  │  [Hook] "Pumping at work is awkward. But what if      │    │
│  │   your pump was so quiet, nobody noticed?"             │    │
│  │  [Body] "The X1 wearable pump runs at 40dB — quieter  │    │
│  │   than a whisper. Slip it in, pump hands-free during   │    │
│  │   your Zoom meeting, and nobody knows..."              │    │
│  │  [CTA] "Try the X1. Your coworkers will never know."   │    │
│  │                                                       │    │
│  │  [✓ Select] [✎ Edit]                                 │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─ Candidate B ────────────────────────────────────────┐    │
│  │  Score: 85%  |  Hook: Data Drop  |  30s TikTok       │    │
│  │  "85% of working moms say pumping is the #1 stress..." │   │
│  │  [✓ Select] [✎ Edit]                                 │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─ Candidate C ────────────────────────────────────────┐    │
│  │  Score: 78%  |  Hook: Emotional  |  30s TikTok       │    │
│  │  "I cried in the lactation room. Then I found this..."│    │
│  │  [✓ Select] [✎ Edit]                                 │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                              │
│  Selected: 0/2 max    AI recommends: Candidate A             │
│                                                              │
│  [Back]                           [Continue with Selected →] │
└──────────────────────────────────────────────────────────────┘
```

**交互规则：**
- AI 推荐那个用绿色边框 + "Recommended" 标签标示
- 用户可选择最多 2 个（如果选 2 个，下游生成 2 个版本的分镜、视频等）
- 点击 "✎ Edit" 打开内联编辑器，可修改 segment 的 voiceover 和 visual_description
- 选择后点击 Continue，选中的脚本进入下游

### 3.3 Gate 2：审画面 🎬

**上游步骤：** storyboards → keyframe_images（每个选中脚本 × 3 候选关键帧）

**展示内容：**
```
┌──────────────────────────────────────────────────────────────┐
│  Gate 2: Review Keyframes                  [5 of 12 complete]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Script A — 3 shots                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Shot 1      │  │  Shot 2      │  │  Shot 3      │         │
│  │  [Keyframe]  │  │  [Keyframe]  │  │  [Keyframe]  │         │
│  │  ★ Recommended│  │             │  │             │         │
│  │  Hook: pain  │  │  Solution    │  │  CTA: shop   │         │
│  └──────✓──────┘  └──────✓──────┘  └──────✓──────┘         │
│                                                              │
│  [Regenerate Shot 2]  [Edit Prompt]                         │
│                                                              │
│  ─────────────────────────────────────────────               │
│  Quality Check: Face Score 0.87 ✅ | Product Shape 0.91 ✅   │
│                                                              │
│  [Back]                           [Approve & Continue →]     │
└──────────────────────────────────────────────────────────────┘
```

**交互规则：**
- 每个 shot 展示最优关键帧，默认已选中（绿色勾）
- 点击单个 shot → 展开，可看到 3 个候选关键帧，可换选
- "Regenerate" 按钮针对单个 shot 重新生成关键帧
- 质量分数实时展示（人脸一致性、产品形态），低分数 shot 红色警告

### 3.4 Gate 3：选片段 🎥

**上游步骤：** video_prompts → seedance_clips（每个 shot × 3 候选 clip）→ tts_audio → thumbnail_images

**展示内容：**
```
┌──────────────────────────────────────────────────────────────┐
│  Gate 3: Select Final Clips                [9 of 12 complete]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Script A — 3 shots, 3 clips each = 9 total candidates       │
│                                                              │
│  ┌─ Shot 1: Hook ──────────────────────────────────────┐     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │     │
│  │  │ Clip 1A  │  │ Clip 1B  │  │ Clip 1C  │          │     │
│  │  │ ★ Rec    │  │          │  │          │          │     │
│  │  │ [▶ Play] │  │ [▶ Play] │  │ [▶ Play] │          │     │
│  │  │ Motion ✓ │  │ Motion ✓ │  │ Motion ⚠ │          │     │
│  │  └────✓────┘  └──────────┘  └──────────┘          │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
│  ... (Shot 2, Shot 3 below, scrollable)                      │
│                                                              │
│  Final video will contain 3 clips                            │
│  [✓ Keep audio sync]  [✓ Auto-transition 1s fade]           │
│                                                              │
│  [Back]                           [Approve & Export →]       │
└──────────────────────────────────────────────────────────────┘
```

**交互规则：**
- 每个 shot 最多展示 3 个候选 clip，AI 推荐的那个带 ★ + 绿色边框
- 点击 clip 播放预览（2-3s loop）
- 可对单个 shot 选择不同候选（选 1 个必选）
- 全局设置：淡入淡出、保留音轨

### 3.5 Gate 4：终审 ✅

**上游步骤：** assemble_final → audit

**展示内容：**
```
┌──────────────────────────────────────────────────────────────┐
│  Gate 4: Final Review                     [12 of 12 complete]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────┐                    │
│  │                                     │                    │
│  │         [▶ 30s Video Preview]        │                    │
│  │                                     │                    │
│  └─────────────────────────────────────┘                    │
│                                                              │
│  Duration: 28s  |  Format: 9:16  |  Size: 12.4 MB           │
│  Platforms: TikTok-ready, Shopify-ready                      │
│                                                              │
│  Quality Summary:                                            │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ✅ Face Consistency   0.87    ✅ Motion Smoothness    │    │
│  │ ✅ Product Shape      0.91    ✅ Audio Sync           │    │
│  │ ⚠️ Duration vs Target 28/30s (acceptable)             │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Actions:                                                    │
│  [Download .mp4]  [Copy Script]  [Regenerate with edits]     │
│  [Publish to TikTok]  [Publish to Shopify]  [New Creation]   │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、3 候选 × 选 2 上限 × AI 推荐机制

### 4.1 候选生成策略

每个 Gate 上游的步骤并行生成 **3 个候选方案**，使用不同的参数：
- **候选 A：** 系统提示词标准版本
- **候选 B：** 系统提示词 + variant = "creative"（更具创意、更大胆）
- **候选 C：** 系统提示词 + variant = "conservative"（更保守、更安全）

这是通过 `SkillCallable.execute(params)` 的 `params["variant"]` 参数实现的。

### 4.2 AI 推荐的评分逻辑

```
每个候选的 score = 
  文本质量分 (30%) + 
  策略匹配度 (25%) + 
  USP 覆盖率 (20%) + 
  平台适配度 (15%) + 
  品牌调性匹配 (10%)
```

AI 推荐的候选通过 `★ Recommended` 标签标示，并在 Gate UI 中默认选中。用户可以不接受推荐——但推荐的总是第一个展示、视觉层级最高。

### 4.3 选 2 个的上限逻辑

用户可以在 Gate 1（选脚本）中选择最多 2 个脚本。如果选了 2 个：
- 下游运行两次（两个版本并行），生成两套完整视频
- Gate 4 终审时展示两个版本的对比，用户选最终保留的 1 个

```
用户选了 Script A + Script B
  → storyboards × 2  →  keyframe × 2  →  seedance × 2  →  ...
  → Gate 4: Compare Version A vs Version B → Keep one
```

**成本考虑：** 选 2 个会让下游 API 调用翻倍，但通常只有专家工作台用户会这么做（低频），且这些是重要素材，值得投入。

---

## 五、AI 时长推荐 —— 后置决策流

### 5.1 推荐生成逻辑

在 strategy 步骤执行时，LLM 同时分析：
1. **产品类型：** 功能性产品（需要展示使用场景）→ 长视频；快消品（视觉冲击力足）→ 短视频
2. **USP 数量：** 1-2 个 USPs → 15-30s；3-5 个 USPs → 45-60s
3. **目标平台：** TikTok → 15-45s；Shopify PDP → 30-60s
4. **内容复杂度：** 简单功能展示 → 短；情感叙事 → 长

### 5.2 用户交互流

```
Step 1: 用户输入产品名 "Baby Monitor with AI Cry Detection"
Step 2: 点击 [Continue →]
Step 3: 后端执行 strategy 步骤 → 返回推荐
Step 4: 前端展示 ────────────────────────────────┐
│                                                │
│  🤖 AI Recommendation                          │
│                                                │
│  Based on "Baby Monitor" features:             │
│  • 3 USPs (technical product)                  │
│  • Best platform: Shopify PDP + YouTube Shorts │
│  • Recommended duration: 45-60s medium-long    │
│    ┌──────────────────────────────────────┐    │
│    │ [5-15s] [15-30s] [30-45s] [45-60s] [60-90s]│
│    │                  ★ AI Rec             │    │
│    └──────────────────────────────────────┘    │
│                                                │
│  Why 45-60s?                                   │
│  • Enough time to demo 3 features              │
│  • Matches Shopify product page best practices │
│  • YouTube Shorts max is 60s                   │
│                                                │
│  [Accept]  [I'll choose: ▾45-60s]             │
│                                                │
└────────────────────────────────────────────────┘
```

### 5.3 关键交互细节

- AI 推荐的档位用 ★ 标示，默认选中
- "Why this duration?" 折叠区解释推荐理由（建立信任）
- 用户可下拉选择其他档位，但 AI 推荐始终视觉突出
- 如果用户选了与推荐不同的档位，不需要二次确认——用户应该有最终决定权

---

## 六、实现优先级

| 优先级 | 功能 | 依赖 | 预估 |
|--------|------|------|------|
| **P0** | 三场景独立入口（Page 级重构） | 无 | 3-4h |
| **P0** | 智能快创模式（3 阶段 + 全自动） | 12 步管线已有 | 2-3h |
| **P1** | AI 时长推荐（后置） | strategy step | 1-2h |
| **P1** | Gate 1：选脚本（3 候选 × 选 2） | script_writer 生成变体 | 3-4h |
| **P1** | 专家工作台模式（Gate 暂停 + 审批 UI） | 逐步 API 已有 | 4-6h |
| **P2** | Gate 2：审画面 + Gate 3：选片段 | Gate 1 | 各 3-4h |
| **P2** | Gate 4：终审 + 对比 | Gate 1-3 | 2-3h |

---

*以上为整轮深度讨论的完整记录和深化方案。*
