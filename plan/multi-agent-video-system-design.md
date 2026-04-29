# 多智能体短视频创作系统 — 完整设计

> **状态**：架构设计完成，等待审批后进入技术实施阶段
> **设计者**：Hermes（模拟10年经验视频创作者+系统架构师视角）
> **日期**：2026-04-24

---

## 目录

1. [系统目标与边界](#1)
2. [Agent矩阵：角色 × 视频类型](#2)
3. [12节点流水线详解](#3)
4. [人机审批节点设计](#4)
5. [多语言架构策略](#5)
6. [技术栈推荐](#6)
7. [执行路径与里程碑](#7)
8. [风险与缓解](#8)

---

## 1. 系统目标与边界 {#1}

### 目标
构建一个12-Agent协作的短视频内容工厂，服务于跨境电商母婴品类（可穿戴吸奶器+喂养电器），覆盖TikTok / Facebook / YouTube Shorts / Shopify 四大平台，产出英语/西语/法语/德语原生内容。

### 边界
- **做**：从选题到发布的全链路Agent化，人仅在4个关键节点审批
- **不做**：KOL管理、直播带货、付费广告投放优化（属于独立系统）
- **产量**：每人每周5条精工细作型视频（量产型架构可后续扩展）

---

## 2. Agent矩阵：12角色 × 10视频类型 × 4语言 {#2}

```
                        商品使用  品牌  短视频  商品  教程  开箱  客户  行业  热点  对比
                        介绍类  推广类  带货类  测评类  HowTo  Unboxing  证言  洞察  借势  评测
                        ─────────────────────────────────────────────────────────────
1. 选题策略师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
2. 脚本编剧              ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
3. 合规审核官            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
4. 视觉分镜师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
5. 素材采编师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
6. AI素材生成师          ✓       ✓      ✓      ✓     ✓     ✓       ✓     ―     ―     ✓
7. 视频剪辑师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
8. 音频设计师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
9. 字幕/文案包装师       ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
10. 封面/缩略图设计师     ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
11. 平台分发运营师        ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
12. 数据分析师            ✓       ✓      ✓      ✓     ✓     ✓       ✓     ✓     ✓     ✓
```

**图例**：✓ 全自动 | ⧖ 需人工审批 | ― 不适用（热点借势和对比评测通常用实拍素材，AI生成较少）

---

## 3. 12节点流水线详解 {#3}

### Node 1：选题策略师 (Strategy Agent)

**职责**：决定这周拍什么、为什么拍、拍给谁看

**输入**：
- 各平台趋势数据（TikTok Trends、YouTube热门、Amazon热销）
- 竞品内容分析（Momcozy/Elvie/Willow 最近在发什么）
- 季节性事件日历（母亲节/Prime Day/Black Friday/World Breastfeeding Week）
- 历史视频数据复盘（什么类型在什么平台表现好）
- 产品上新/库存促销计划

**输出**：周选题日历
```json
{
  "week": "2026-W17",
  "briefs": [
    {
      "id": "BRIEF-001",
      "video_type": "tutorial",
      "topic": "How to clean wearable pump at the office",
      "target_audience": "Working moms 25-35",
      "target_platforms": ["tiktok", "youtube_shorts"],
      "target_languages": ["en", "es", "fr", "de"],
      "key_message": "Discreet cleaning in 2 minutes",
      "usp_priority": ["portable", "quiet", "easy-clean"],
      "competitor_reference": "Elvie Stride cleaning video (2.3M views)",
      "seasonal_hook": "Back-to-office pumping tips"
    }
  ]
}
```

**⧖ 人工审批节点 #1**：审核选题日历，确认方向/驳回/调整

---

### Node 2：脚本编剧 (Script Writer Agent)

**职责**：把选题brief变成平台适配的可拍摄脚本

**核心结构**（商业短视频黄金模板，按平台适配）：

```
[0–3s]  Hook（钩子）
  策略：痛点共鸣 / 反常识 / 数据冲击 / 场景代入
  例："Pumping at work shouldn't feel like hiding in a bathroom stall."

[3–8s]  Pain Point Expansion（痛点展开）
  策略：具体化场景，让观众"这是我"

[8–20s] Solution Introduction（产品登场）
  策略：产品如何解决上述痛点，实物展示

[20–35s] Trust Building（信任构建）
  策略：认证/数据/真实用户反馈/"FDA cleared"等

[35–45s] CTA（行动号召）
  策略：明确下一步 — "Shop the link in bio" / "Save this for your return to office"
```

**平台差异化**：
| 平台 | 时长 | 节奏 | 字幕 | Hook风格 |
|------|------|------|------|----------|
| TikTok | 15–60s | 快 | 必须 | 强钩子，前1.5s决定命运 |
| YouTube Shorts | 15–60s | 中等 | 必须 | 搜索意图+钩子 |
| Facebook | 30–90s | 中等 | 必须 | 情感共鸣型 |
| Shopify (产品页) | 30–120s | 慢 | 可选 | 功能展示型 |

**语言处理**：4个语言各独立产出脚本，不做翻译（你选的B方案）。每个语言Agent注入该市场的文化适配逻辑：
- **EN**：Empowerment叙事 + 功能性细节
- **ES**：家庭感 + 社区认同（abuela/amiga视角）
- **FR**：优雅 + 女性自主权（liberté叙事）
- **DE**：技术严谨 + 认证背书（TÜV/CE/质量叙事）

**⧖ 人工审批节点 #2**：审核脚本，确保品牌调性和合规性

---

### Node 3：合规审核官 (Compliance Agent)

**职责**：在脚本进入制作前拦截风险

**自动检测项**：
- [ ] 母乳喂养裸露画面（任何乳头/乳晕轮廓的暗示）
- [ ] 医疗声明（"cures"、"treats"、"prevents mastitis"）
- [ ] 未证实的比较广告（"better than Elvie" — 需数据支撑）
- [ ] 平台敏感词检测（按Meta/TikTok/YouTube政策库）
- [ ] FDA/CE声明正确性（是否在认证范围内）
- [ ] 儿童出现合规（是否有Child Privacy合规风险）

**输出**：合规报告
```json
{
  "script_id": "SCRIPT-001-EN",
  "status": "PASS" | "FLAGGED" | "BLOCKED",
  "flags": [
    {
      "severity": "HIGH",
      "line": 12,
      "text": "prevents clogged ducts",
      "issue": "Unsubstantiated medical claim",
      "suggestion": "Replace with: 'helps maintain milk flow during the workday'"
    }
  ]
}
```

**规则**：FLAGGED → 自动发回脚本Agent改写。BLOCKED → 人工介入。

---

### Node 4：视觉分镜师 (Visual Storyboard Agent)

**职责**：把脚本转为可执行的镜头列表

**输出格式**：
```json
{
  "script_id": "SCRIPT-001-EN",
  "total_duration": "45s",
  "aspect_ratio": "9:16",
  "shots": [
    {
      "id": 1,
      "start": "0.0s", "end": "2.5s",
      "type": "hook",
      "visual": "Split screen: left=woman at desk looking frustrated, right=bathroom stall door",
      "text_overlay": "Pumping at work?",
      "camera": "Static",
      "asset_needed": "B-Roll: office desk scene"
    },
    {
      "id": 2,
      "start": "2.5s", "end": "8.0s",
      "type": "pain_point",
      "visual": "Medium shot: woman checking watch, pump bag visible",
      "text_overlay": "3x a day. 20 minutes each. In a supply closet.",
      "camera": "Slow zoom in",
      "asset_needed": "UGC: mom at workplace"
    }
  ]
}
```

---

### Node 5：素材采编师 (Asset Sourcing Agent)

**职责**：根据分镜需求的asset_needed字段，从素材库自动匹配

**匹配逻辑**：
```
分镜需求 → 向量搜索素材库 → 返回Top3候选 → 最优匹配 → 素材就位
                                                    ↓
                                            无合适匹配 → 生成Gap Report
```

**Gap Report** 触发 Node 6（AI素材生成）。

---

### Node 6：AI素材生成师 (AI Media Generation Agent)

**职责**：填补素材库缺口

**生成能力**：
- 产品场景图：产品3D模型 + 场景描述 → AI渲染（Flux + ControlNet）
- B-roll空镜：办公室/家庭/户外环境 → AI视频生成（Runway Gen-3 / Kling）
- 信息图/对比表：数据可视化 → Python + Pillow 渲染

**重要约束**：AI生成的素材必须打水印标签 `[AI-GENERATED]`，人审时决定是否替换为实拍。

---

### Node 7：视频剪辑师 (Video Editing Agent)

**职责**：组装素材 + 分镜指令 → 第一版剪辑

**技术方案**：首选 **Remotion**（React程序化视频编辑），备选 Shotstack API

**自动化剪辑逻辑**：
1. 按Shot List排布素材时间线
2. 应用转场（匹配品牌偏好）
3. 关键帧动画（Zoom/Pan以保持画面动感 — TikTok算法偏好高动态内容）
4. 调色：LUT预设（品牌色一致）
5. 画面留出字幕区域（底部20%安全区）

**输出**：无声第一版（音频在Node 8处理，字幕在Node 9）

**⧖ 人工审批节点 #3**：审核第一版剪辑（节奏、画面、整体感觉），可要求修改

---

### Node 8：音频设计师 (Audio Design Agent)

**职责**：配音 + BGM + 音效

**技术方案**：
- **TTS配音**：ElevenLabs（多语言质量最好，Natural/Conversational风格）
  - EN: ElevenLabs "Sarah" / "Rachel" (warm, maternal, professional)
  - ES: Custom voice matching brand warmth
  - FR: Elegant, calm tone
  - DE: Precise, trustworthy tone
- **BGM选曲**：Epidemic Sound / Artlist API → 按视频情绪自动匹配
- **音效**：关键动作音效（产品click声、环境音）

**输出**：配音+BGM+音效 混音文件，与无声视频合成 → 有声版本

---

### Node 9：字幕/文案包装师 (Caption & Graphics Agent)

**职责**：字幕 + 花字 + 强调文字 + CTA按钮

**技术方案**：Whisper (transcription) → 时间轴对齐 → Remotion渲染字幕

**多语言处理**：
- EN/ES/FR/DE 各自的语言Agent处理该语种字幕
- 字幕样式遵循品牌视觉规范
- 关键卖点词自动加粗/高亮/弹跳动画

---

### Node 10：封面/缩略图设计师 (Thumbnail Agent)

**职责**：生成4版缩略图候选

**技术方案**：DALL-E 3 或 Flux + 品牌模板叠加

**输出格式**：
```
Thumbnail-001-A: 产品居中 + 大标题 + 价格标签
Thumbnail-001-B: 使用场景 + Before/After对比
Thumbnail-001-C: 人物表情 + 问题大字
Thumbnail-001-D: 极简产品 + 单句钩子
```

**⧖ 人工审批节点 #4**：从4版中选1版，或要求重新生成

---

### Node 11：平台分发运营师 (Distribution Agent)

**职责**：多平台发布 + 元数据优化

**各平台适配**：
| 平台 | 标题长度 | 标签数量 | 发布时间窗口 |
|------|----------|----------|-------------|
| TikTok | 150字符 | 3-5个 | 美东7-9PM / 周末 |
| YouTube Shorts | 100字符(标题) | 3-5个 | 美东12-2PM |
| Facebook | 无硬限制 | 2-3个 | 美东1-4PM |
| Shopify | 产品描述风格 | N/A | 配合促销节奏 |

**自动化**：
- 标题生成（每个平台版本）
- 话题标签推荐（trending + 品类标签）
- 发布时间调度
- 跨平台视频规格自动转换（9:16 → 1:1 for Shopify）

---

### Node 12：数据分析师 (Analytics Agent)

**职责**：收据回收 → 分析 → 反馈给策略Agent

**监控指标**：
- 完播率（按平台/视频类型/语言）
- 互动率（点赞/评论/分享/收藏）
- 转化率（Bio点击 → Shopify流量 → 加购/下单）
- 7日衰减曲线

**输出**：周报 + 优化建议
```
上周表现：教程类视频完播率 52%（↑8% vs 前周）
         品牌推广类 CVR 3.2%（↓0.5%）
建议：增加"How to"类选题比例，减少纯品牌曝光类
     DE市场完播率最低 → 检查DE脚本节奏是否需要加快
```

**反馈回路**：数据 → Node 1 选题策略师 → 下周选题日历自动调整权重

---

## 4. 人机审批节点设计 {#4}

```
流水线：
  [选题]──⧖人审1──→[脚本]──⧖人审2──→[合规(自动)]──→[分镜(自动)]
  ──→[素材(自动)]──→[AI生成(自动)]──→[剪辑]──⧖人审3──→[音频(自动)]
  ──→[字幕(自动)]──→[封面]──⧖人审4──→[分发(自动)]──→[数据(自动)]

总计：4个人审节点，其余7个自动
平均人工耗时/条：约15-20分钟（选题2min + 脚本5min + 剪辑5min + 封面1min + 上下文切换）
5条/周/人 → 人均投入约1.5-2小时/周
```

**审批界面设计要点**：每个审批节点提供"通过/修改/驳回"三态，修改时自动Markdown批注模式。

---

## 5. 多语言架构策略 {#5}

你选了B方案（目标语言原创），这是对的——母婴品类的文化敏感性决定了翻译不够。

**架构实现**：不是4套独立系统，而是 **1套流水线框架 + 语言适配层**：

```
                    ┌─────────────────────────────┐
                    │   Language Router (调度器)    │
                    │   根据Brief.target_languages  │
                    │   路由到对应语言Agent集群      │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ EN集群    │        │ ES集群    │        │ FR集群    │        │ DE集群    │
    │           │        │           │        │           │        │           │
    │ 策略Agent │        │ 策略Agent │        │ 策略Agent │        │ 策略Agent │
    │ 脚本Agent │        │ 脚本Agent │        │ 脚本Agent │        │ 脚本Agent │
    │ 合规Agent │        │ 合规Agent │        │ 合规Agent │        │ 合规Agent │
    │ 音频Agent │        │ 音频Agent │        │ 音频Agent │        │ 音频Agent │
    │ 字幕Agent │        │ 字幕Agent │        │ 字幕Agent │        │ 字幕Agent │
    │ 封面Agent │        │ 封面Agent │        │ 封面Agent │        │ 封面Agent │
    └──────────┘        └──────────┘        └──────────┘        └──────────┘

          └────────────────────┬────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  共享Agent (语言无关) │
                    │  • 分镜师             │
                    │  • 素材采编           │
                    │  • AI素材生成         │
                    │  • 视频剪辑           │
                    │  • 分发运营           │
                    │  • 数据分析           │
                    └─────────────────────┘
```

**关键设计决策**：
- 策略/脚本/合规/音频/字幕/封面 = **语言相关Agent**，每个语种独立实例
- 分镜/素材/剪辑/分发/数据 = **语言无关Agent**，全局共享
- 封面Agent虽是语言相关（封面文字），但视觉模板全局共享

---

## 6. 技术栈推荐 {#6}

### 总体架构

```
┌──────────────────────────────────────────────────────┐
│                     LangGraph                         │
│              (Agent编排 + 状态管理 + 人机交互)          │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Node 1  │→ │ Node 2  │→ │ Node 3  │→ │ Node 4  │→│
│  │ 策略    │  │ 脚本    │  │ 合规    │  │ 分镜    │  │
│  └─────────┘  └────⧖────┘  └─────────┘  └─────────┘  │
│                      ↑ 人审                           │
└──────────────────────────────────────────────────────┘
```

### 逐层技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| **Agent编排** | **LangGraph** | 状态图+条件分支+checkpoint人机交互，最适合12节点流水线 |
| **LLM底座** | Claude 3.5 Sonnet (脚本/策略) + GPT-4o (合规/结构化输出) | 分任务用最佳模型 |
| **语音合成** | **ElevenLabs** | 多语言质量第一，Natural风格适合母婴品类 |
| **语音识别** | **Whisper Large v3** | 多语言字幕生成 |
| **视频编辑** | **Remotion** (React编程式) | 比Shotstack灵活，可精确控制每一帧；支持程序化批量渲染 |
| **图片生成** | **Flux Pro** (产品场景) + **DALL-E 3** (缩略图) | Flux可控性强，DALL-E创造性好 |
| **视频生成** | **Runway Gen-3** / **Kling** | B-roll和场景补充 |
| **素材管理** | **Supabase Storage** + **pgvector** | 素材库存储+向量搜索匹配 |
| **数据存储** | **Supabase (Postgres)** | 选题/脚本/视频元数据、分析数据 |
| **任务队列** | **Celery + Redis** | Remotion渲染、视频处理等长任务 |
| **前端审批界面** | **Next.js + Tailwind** | 4个人审节点的Web界面 |
| **平台分发** | **Buffer API** + 各平台原生API | 统一发布调度 |

### 为什么不选CrewAI / AutoGen？
CrewAI适合"对话式Agent协作"，但你是**流水线式有状态工作流**，每个节点有明确的输入/输出、有人审暂停、有分支（合规失败→回退脚本）。LangGraph的状态图模型天生匹配这个场景。

---

## 7. 执行路径与里程碑 {#7}

### Phase 0：资产就绪（1-2周，你现在在这）
- [ ] 完成品牌资产模板收集
- [ ] 素材库建立 + 元数据标注
- [ ] 合规清单各平台政策汇总
- [ ] 历史视频数据导入

### Phase 1：流水线MVP（3-4周）
目标：跑通英语单语种的4节点最小闭环

```
选题 → 脚本 → 合规 → 分镜 → 素材 → 剪辑 → 音频 → 字幕 → 封面 → 分发 → 数据
                                                    ↑
                              MVP范围（英语单语种，人审简化）
```

- [ ] LangGraph骨架搭建
- [ ] Node 1-2-3（策略/脚本/合规）英语版
- [ ] Node 4-5-6-7（分镜/素材/剪辑）
- [ ] Node 8-9-10（音频/字幕/封面）
- [ ] Node 11-12（分发/数据）
- [ ] 人审Web界面 v0
- [ ] **产出第一条全流程视频**

### Phase 2：多语言扩展（2-3周）
- [ ] ES/FR/DE 语言Agent集群
- [ ] 多语言TTS集成
- [ ] 文化适配Prompt模板（每个语种的脚本/合规/封面）

### Phase 3：智能化增强（2-3周）
- [ ] 数据分析回流（Node 12 → Node 1 自动优化选题权重）
- [ ] A/B缩略图自动测试
- [ ] 竞品监控自动化
- [ ] 热点实时触发（突发话题→自动生成Brief）

### Phase 4：量产工具链（1-2周）
- [ ] 批量生产模式（一选题多改编）
- [ ] 素材库自动扩充（AI生成预缓存）
- [ ] 多平台A/B发布测试
- [ ] 运营Dashboard

---

## 8. 风险与缓解 {#8}

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| **合规误判导致封号** | 🔴 Critical | Node 3合规Agent双重检测：规则引擎+LLM二次确认；人审脚本时必须看到合规报告 |
| **多语言质量不一致** | 🟠 High | 每种语言配备native reviewer的prompt模板；建立语言质量标准库 |
| **AI生成画面诡异** | 🟠 High | AI素材强制打水印；人审剪辑时可见素材来源标识；优先用实拍+UGC |
| **Remotion渲染性能瓶颈** | 🟡 Medium | 使用服务器端渲染 + 渲染农场；单个视频控制在60s内 |
| **平台API变更** | 🟡 Medium | 分发Agent使用抽象层，平台适配隔离 |
| **ElevenLabs成本** | 🟡 Medium | 预生成常用配音模板缓存；单条视频成本预估$0.5-1.5 |

---

## 附录：Agent Prompt设计原则

每个Agent的System Prompt必须包含：
1. **角色定义**：你是谁，你的专业领域
2. **输入/输出格式**：严格的JSON Schema
3. **品牌约束**：品牌语调、视觉规范、合规红线（注入到每层）
4. **平台约束**：目标平台的规格要求
5. **失败模式**：什么情况下返回ERROR而非勉强产出
