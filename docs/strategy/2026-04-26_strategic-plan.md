# 战略分析与完整规划 — AI 多场景视频创作平台

> **作者视角**：资深 AI 短视频创作专家 + 系统架构师的联合判断
> **日期**：2026-04-26
> **依据**：四份产品文档 + 当前代码真实状态扫描
> **风格**：直说、强观点、不和稀泥

---

## TL;DR — 三句话核心判断

1. **你以为你在做"AI 视频平台",实际上你在做的是"中小品牌内容生产工作流引擎"**——这两个不是同一件事,前者是工具,后者是流水线。当前代码其实更像后者,但文档和命名都按前者写,这是认知与工程的错位。

2. **你的四份文档之间存在两个核心矛盾**:(a) **垂直内容工厂** vs **通用 SaaS 平台**——多智能体设计文档锁定母婴垂直,roadmap 走通用多场景,你不能同时做;(b) **MVP 应该单语种** vs **多语言核心架构**——phase1 计划是英语单语,但你的 prompt 已铺到 4 语言,代码却没真正跑过非英语 pipeline。

3. **你最大的风险不是缺功能,是缺一条真实跑通的端到端**。553 个测试,9 个 Skill,16 节点 LangGraph,4 个场景 pipeline,但你没有一条"从 brief 到可发布 mp4 视频"的真实路径——所有渲染/TTS/AI 生成在 mock 模式下"成功",真实模式下没人验证过。先把**一条**走通,再扩。

---

## 第一部分:四份文档的诊断与矛盾

### 1.1 文档间的张力

| 维度 | 多智能体设计 (2026-04-24) | brand-asset-template | phase1-plan | multi-scenario-roadmap (2026-04-26) |
|------|--------------------------|----------------------|-------------|-------------------------------------|
| **产品定位** | 母婴垂直内容工厂 | 单品牌资产收集 | MVP 单语英语 | 通用多场景 SaaS |
| **租户模型** | 单一品牌(Hermes 自用) | 单一品牌 | 单一品牌 | 多场景隐含多品牌 |
| **场景数量** | 10 类视频 × 1 品类 | N/A | 1 个端到端 | 4 个独立场景 |
| **语言策略** | 4 语言原生(EN/ES/FR/DE) | 单语品牌 | 单语英语 | 默认英语,多语扩展 |
| **审核节点** | 4 个人审 | N/A | 4 个人审 | 部分场景有,部分场景无 |
| **核心壁垒假设** | 品牌资产 + 多语言 + 合规 | 品牌资产 | LangGraph 编排 | 场景库 + 工作流 |

**关键观察**:这四份文档**不是同一个产品的四个阶段**,而是**四个产品愿景的并存**。

- 多智能体设计文档:你给 Hermes 自己做的内容工厂
- brand-asset-template:让某一个品牌方填的入库表
- phase1-plan:让一个工程师按周交付的 16 task list
- multi-scenario-roadmap:产品经理画给投资人/合伙人的路线图

每一份单看都合理,放一起就**冲突**:你到底要做的是 A、B 还是 C?这件事不解决,所有路线图都是浮沙。

### 1.2 必须解决的产品定位三选一

我直接画给你三条路:

**路径 A:垂直内容工厂(Hermes 自用 / 1-2 家品牌)**
- 价值:每周稳定产出 5-10 条母婴垂直视频,质量稳、合规稳、多语言全
- 商业化:你自己卖产品(Hermes 是品牌主),或 OEM 给 1-2 家母婴品牌
- 复杂度:**最低**——单租户、写死品牌资产、prompt 深度调优一个垂直
- 时间到收入:1-2 个月可见效
- 护城河:垂直深度 + 合规 + 4 语言 + 历史数据反馈
- 风险:天花板低,做不大

**路径 B:通用 SaaS 平台(roadmap 暗示的方向)**
- 价值:任何品牌注册、填资产、选场景、产出
- 商业化:订阅 + 用量计费,SMB 卖给电商/创作者
- 复杂度:**最高**——多租户、Auth、Billing、UGC、白标、客服
- 时间到收入:6-12 个月,要烧钱
- 护城河:**很难找**——HeyGen / Runway / Captions / OpusClip / Sora-as-Service 已挤爆
- 风险:跟巨头撞、做不出差异化

**路径 C:工作流插件 / API 服务(被集成方)**
- 价值:卖给 Shopify / TikTok 卖家 / Agency,作为他们的内容生产模块
- 商业化:per-call API 计费 + 包月席位
- 复杂度:中等——核心是 SDK + Webhook + 文档,不需要全套前端
- 时间到收入:3-6 个月
- 护城河:深度集成 + 行业合规模板
- 风险:依赖大平台政策变化

**我的强烈建议**:

> **先走 A,做 4 周。** 用你自己的母婴产品(或邀请 1-2 家熟品牌)作为唯一用户,把流程从头到尾跑通一次真实视频。**这一步如果跑不通,B 和 C 都是空中楼阁。**
>
> 跑通之后,你会看到三件事:(1)真实质量是否可发布;(2)真实成本是多少;(3)用户(你自己/品牌方)真正卡在哪里。然后你才有数据决定走 B 还是 C。

不要在没产出过一条真视频的情况下,讨论"多租户"、"扩展场景"、"反馈回路"——**那都是过度工程化**。

---

## 第二部分:当前代码的真实状态(数据化)

我刚刚扫描了你的代码库,这是真相,不是 roadmap 里的乐观估计:

### 2.1 已建成的真实能力

```
LangGraph 流水线:    16 节点(12 工作 + 4 审计)+ 4 个 interrupt_after
Skill 注册表:        9 个独立 Skill(viral_extractor, remix_script, brand_compliance,
                                  seedance_prompt, video_analysis, product_strategy,
                                  storyboard, thumbnail_prompt, script_writer)
Pipeline 类:         4 个 one-shot(S1/S2/S3/S4)+ 1 个 LangGraph
Agent 类:            12 个(strategy/script_writer/compliance/storyboard/asset_sourcing/
                          media_generation/editor/audio_designer/caption/thumbnail/
                          distribution/analytics + auditor + i18n)
Prompt 模板:         EN/ES/FR/DE 四语全(strategy + script_writer)
模型客户端:          OpenAI / Anthropic / ElevenLabs / DALL-E / Seedance / Whisper / GPT-Image
渲染引擎:            Remotion 客户端代码存在
持久化:              MemorySaver(默认)+ Postgres 代码已写未启用
测试函数:            553 个(分布在 30 个 test_*.py)
前端组件:            7 个(SceneSelector / PipelineMonitor / ReviewPanel / DistributionView /
                         OneShotResultView / AuditScoreCard / api / types)
API 端点:            /pipeline/start /scenario/s1-4 /pipeline/{id}/{state,review,output,distribution,export}
                    /assets/* /health
```

### 2.2 已建成但未真正跑通的能力

| 能力 | 代码状态 | Mock 模式 | 真实模式 |
|------|----------|-----------|----------|
| LangGraph S3 流水线 | 完整 | ✓ 通过 | ⚠ 未验证 |
| ElevenLabs TTS | 客户端齐 | ✓ 通过 | ❌ 未走通 |
| DALL-E / GPT-Image 缩略图 | 客户端齐 | ✓ 通过 | ❌ 未走通 |
| Seedance 视频生成 | 客户端齐 | ✓ 通过 | ❌ 未走通 |
| Remotion 视频渲染 | 客户端齐 | ✓ 通过 | ❌ 未走通 |
| Whisper 字幕生成 | 提到但未集成 | N/A | ❌ |
| 多语言 pipeline 端到端 | Prompt 齐 | ⚠ 单语跑通 | ❌ 多语未验证 |
| Postgres 持久化 | 代码齐 | N/A | ❌ dev 用 MemorySaver |
| 平台分发真发 | 仅生成计划 | ✓ JSON 输出 | ❌ 无平台 API 集成 |
| Analytics 反馈 Strategy | 单向 | ✓ Mock 报告 | ❌ 反馈回路缺失 |
| 多租户/Auth | ❌ 不存在 | N/A | ❌ |
| 品牌资产入库 UI | ❌ 不存在 | N/A | ❌ |

**核心结论**:你的"已完成 R1-R8"在测试模式下属实,但**真实模式下,你没产出过任何一条可发布视频**。这是 R9 的真正起点,不是新增功能。

### 2.3 架构层面的概念混乱

你现在有四个抽象层并存:

```
┌─────────────────┐     ┌─────────────────┐
│  Pipeline 类    │     │  LangGraph      │   ← 编排层(两套并存)
│  (S1/S2/S3/S4)  │     │  (compile_pipe) │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ↓                       ↓
┌─────────────────┐     ┌─────────────────┐
│  SkillRegistry  │     │  Agent 类       │   ← 执行层(两套并存)
│  (9 个 skill)   │     │  (12 个 agent)  │
└─────────────────┘     └─────────────────┘
```

**问题在于**:
- 同一个能力(比如脚本生成)既有 `ScriptWriterAgent` 又有 `script-writer-skill` Skill,两套都用 LLM,功能重叠
- S3 在 LangGraph 里走的是 `script_node` → `ScriptWriterAgent`,在 one-shot pipeline 里走的是 `SkillRegistry().execute("remix-script-skill")`
- 同一个场景 `influencer_remix`:`/pipeline/start` 走 LangGraph(有审核),`/scenario/s3` 走 one-shot(无审核)——**两条不一致的路径!**

这是技术债。你需要在 R9 做的不只是"加功能",而是**抽象层归并**:

> **建议**:Skill 是原子能力(无状态、单职责、可独立测试)。Agent 是 Skill 的有状态封装(只在需要时存在)。Pipeline 是编排(LangGraph 用于有审核/分支/状态保存的场景,SkillRegistry 顺序调用用于一次性场景)。**不要让 Skill 和 Agent 同时实现同一逻辑。**

---

## 第三部分:场景架构的再设计

你现在有 4 个场景,我的判断:

### S1 — 商品直拍 (product_direct)
- **真实需求**:有产品没素材的卖家,要快速上架
- **现状**:one-shot,无审核,5 个步骤(strategy → script → storyboard → seedance prompt → thumbnails)
- **痛点**:**没有真视频产出**,只到 prompt 就结束,用户拿到 prompt 还要自己丢去 AI 视频工具
- **应该做**:接 Seedance 真实生成 → Remotion 拼接 → 输出 mp4

### S2 — 品牌宣传 (brand_campaign)
- **真实需求**:有品牌资产的成熟品牌,要做品牌曝光视频
- **现状**:LangGraph,有审核
- **痛点**:**和 S1 的差异不清晰**——区别只在 brand_guidelines 字段更全,核心流程一样
- **建议**:**合并到 S1**,用一个 `brand_mode` 标志位区分。两条独立 pipeline 就是浪费。

### S3 — 网红二创 (influencer_remix)
- **真实需求**:看到爆款想抄,但要换成自己产品
- **现状**:LangGraph + one-shot 两套并存(架构债)
- **痛点**:**最有壁垒的场景,但实现深度不够**——视频分析只到结构层面(hook/segments),不分析镜头语言/节奏/情绪曲线;remix 脚本只换台词,不换分镜
- **价值评估**:⭐⭐⭐⭐⭐ **这是你的差异化核心**,因为通用 SaaS 不做这个(版权风险),但中小卖家最需要

### S4 — 实拍生成 (live_shoot_to_video)
- **真实需求**:已经有素材的人,要 AI 帮编辑
- **现状**:one-shot,简单
- **痛点**:**产品定位不清**——已经有素材的人为什么不用 CapCut?
- **建议**:**暂缓**,等 S1+S3 跑通再回头看是否有真实需求

### 重新分组的场景架构

```
                  ┌─────────────────────────────────────┐
                  │  Brief 类型(用户输入)               │
                  └────────────┬────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ↓                    ↓                    ↓
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ 原创路径  │        │ 二创路径  │        │ 编辑路径  │
    │ Original │        │ Remix    │        │ Edit-Only│
    │ (S1∪S2)  │        │ (S3)     │        │ (S4 缓做)│
    └────┬─────┘        └────┬─────┘        └────┬─────┘
         │                   │                   │
         ├───────────────────┴───────────────────┤
         ↓                                       ↓
    ┌──────────────────────────────────────────────┐
    │  共享生成层(SkillRegistry)                  │
    │  • Storyboard  • Seedance  • Remotion 渲染   │
    │  • TTS  • Caption  • Thumbnail  • Distribute │
    └──────────────────────────────────────────────┘
```

**两条核心路径(原创 + 二创)+ 一组共享 Skill** 比四条平行 pipeline 干净得多。

---

## 第四部分:七大缺口(对照 roadmap G1-G7 的我的版本)

按**优先级排序**,不是按 roadmap 的 G1-G7 编号:

### G1(P0): 真实视频产出闭环 ❗❗❗ 必须本周解决
- **现状**:Remotion / Seedance / ElevenLabs 客户端代码齐,真实模式从未跑通
- **影响**:整个产品的核心承诺无法兑现
- **解决**:本周 spike 一次,从 brief 到 mp4 全程不开 mock,记录所有失败点
- **不是缺什么,是缺验证**

### G2(P0): 品牌资产入库 UI ❗❗
- **现状**:brand-asset-template.md 是 markdown,没有 UI 让品牌填
- **影响**:工厂模式下,新品牌入库要工程师手写 JSON——产品形态不成立
- **解决**:Next.js 表单(分品牌资产/语调/产品/合规四 tab),保存到 brand_packages 表
- **预期投入**:5-7 天

### G3(P0): 持久化 ❗
- **现状**:MemorySaver 默认,uvicorn 重启丢线程
- **影响**:任何线上验证都不可能(用户开了一半视频,断电就废)
- **解决**:dev 也用 Postgres(已有代码,只需切默认),docker-compose 起 PG
- **预期投入**:1 天

### G4(P1): 多语言端到端验证
- **现状**:4 语 prompt 齐,但单语 pipeline 跑过,多语没验证
- **影响**:多语是核心卖点之一,不验证等于不存在
- **解决**:Sprint 6 时,每个语言至少跑一条真视频,EN/DE/ES/FR 各 1 条
- **预期投入**:7 天

### G5(P1): Analytics → Strategy 反馈回路
- **现状**:Analytics 输出 mock 报告,Strategy 不读取
- **影响**:产品的"自学习"承诺不存在
- **解决**:metrics_repository 已有,加一层"上周表现 → 本周选题权重"读取
- **预期投入**:3-5 天

### G6(P2): 平台真发布
- **现状**:仅生成 distribution_plans JSON,不接平台 API
- **影响**:用户拿到计划还要手发,自动化不彻底
- **解决**:接 1 个平台(推荐 TikTok 或 YouTube Shorts),其它仍生成计划
- **预期投入**:7-10 天(每个平台)

### G7(P3): 多租户 + Auth
- **现状**:单租户假设,没有 user/org 概念
- **影响**:走 SaaS 路径才需要,走垂直工厂路径**不需要**
- **解决**:SaaS 路径下,用 Supabase Auth + RLS,7-10 天
- **建议**:**先不做**,等 A 路径验证后再说

---

## 第五部分:完整 8 周路线图(替代 roadmap 的 R9a/b/c)

> **前提假设**:你接受我的"先走 A 路径"建议。如果坚持 B 路径,把 Sprint 7-8 替换为多租户 + Billing。

### Sprint 0:决策与真相(本周,4 月 27 日 - 5 月 3 日)

**目标**:在写新代码之前,把现状摸清,把决策做完

| 任务 | 负责 | 验收 |
|------|------|------|
| 决定走 A / B / C 路径 | 你 | 一句话写下来,贴在 README |
| 真实模式 spike S3:一条 EN 视频从 brief → mp4 | 你 / 工程师 | 拿到一个真的 mp4 文件,即使丑 |
| 列出 spike 中所有失败点 | 工程师 | failures.md 文件 |
| docker-compose 起 PG,把默认 checkpointer 切到 PG | 工程师 | uvicorn 重启后线程仍在 |
| 决定 S2 是否合并到 S1 | 你 | RFC 或 issue 写下决策 |

**这周不写新功能,只验证 + 决策**。

### Sprint 1:基建拉直(第 2 周,5 月 4-10 日)

**目标**:把"无 mock 也能跑"作为默认,持久化稳

| 任务 | 验收 |
|------|------|
| Remotion 真实渲染走通 | 一条 30s mp4 输出到 outputs/ |
| ElevenLabs TTS 真实集成 | 一段 EN 配音 mp3 |
| DALL-E 真实缩略图 | 4 张 png 输出 |
| Postgres 默认 + LangGraph 持久化 | docker-compose up 后,start_api.sh 自动连 PG |
| `/pipeline/start` 真实模式可选(env 切换) | 真实模式跑一次完整 S3 |

**结束时你应该有**:一个真实的 EN 母婴示范视频,可以放给任何人看。

### Sprint 2-3:S3 生产级(第 3-4 周,5 月 11-24 日)

**目标**:把 S3 从"能跑"变成"生产可用"

| 任务 | 验收 |
|------|------|
| 视频分析深度升级:加镜头节奏 + 情绪曲线分析 | analysis JSON 包含 shot_pace_secs, emotion_curve |
| Remix 脚本升级:不只换台词,换分镜 | remix 输出包含 storyboard 调整 |
| 字幕(Whisper)集成 | 自动 SRT,3 语言 |
| 自动 BGM 选曲 | Epidemic Sound API 接入 |
| S3 真实端到端 e2e 测试 | 5 条不同 niche 的 remix 视频成功产出 |
| 缩略图 A/B 多版本 | 4 版各异化,人审选 1 |

### Sprint 4-5:S1 落地 + S2 合并(第 5-6 周,5 月 25 日 - 6 月 7 日)

**目标**:S1 (含合并后的 S2) 也达到 S3 同等生产标准

| 任务 | 验收 |
|------|------|
| S2 代码合并到 S1,加 brand_mode 字段 | 单 Pipeline 类 |
| S1 接通 LangGraph 审核(目前 S1 是 one-shot) | 4 个审核节点也走 |
| 品牌资产 UI v0(前端表单 + 后端持久化) | 可以新增/编辑/删除品牌包 |
| S1 真实端到端 e2e 测试 | 3 个不同品牌的 product_direct 成功 |

### Sprint 6:多语言垂直闭环(第 7 周,6 月 8-14 日)

**目标**:验证多语言不是 prompt 而已,而是真的端到端

| 任务 | 验收 |
|------|------|
| Pipeline 按 target_languages 分流(语言路由器) | 同一个 brief 产出 4 个语言版本 |
| 每个语言真实跑一条产出 | EN/ES/FR/DE 各 1 条 mp4 |
| 文化适配 prompt 调优 | 每语言至少有 native 校对反馈一轮 |

### Sprint 7:分发与反馈(第 8 周,6 月 15-21 日)

**目标**:闭环数据,接通至少一个平台

| 任务 | 验收 |
|------|------|
| TikTok Business API 接入 | 真发一条到测试账号 |
| Analytics → Strategy 反馈 | 上周表现影响下周选题权重 |
| 7 日数据回收 | metrics_repository 写回 PG |

### Sprint 8+:路径分叉

- **A 路径**:扩展更多品牌品类,深化合规库,母婴外探索新垂直
- **B 路径**:抽出多租户层,Auth(Supabase)+ Billing(Stripe)+ 客户成功
- **C 路径**:封装 SDK,出 API 文档,接 1-2 个 Agency 试点

**8 周后,你有一个真实可演示的产品 + 数据决定走哪条路。**

---

## 第六部分:本周(Sprint 0)的 7 个具体动作

可以今天/明天就开始:

1. **周一上午**:把这份分析读完,在文档底部写下你的反应——同意/不同意/补充什么
2. **周一下午**:决定 A/B/C 三选一,写在 `docs/strategy/positioning.md`
3. **周二**:Spike S3 真实模式
   ```bash
   cd ~/project/hermes_evo/AI_vedio
   # .env 填真实 OPENAI_API_KEY / ELEVENLABS_API_KEY / SEEDANCE_API_KEY
   ./scripts/start_api.sh
   curl -X POST localhost:8001/scenario/s3 -d '{
     "video_url": "https://www.tiktok.com/@momcozy/video/...",
     "product": {"name": "Wearable Pump M5", "usps": [...]},
     "influencer_name": "Sarah",
     "brief_id": "TEST-001"
   }'
   ```
   记录每一个失败点到 `docs/spike/2026-04-28_s3-real-failures.md`
4. **周三**:把 docker-compose.yml 写出来,PG 跑起来,默认改 PG
5. **周三**:S2 是否合并到 S1 — 30 分钟决策会(你一个人开),写决策 doc
6. **周四**:列 Remotion 渲染缺什么——asset library 缺数据?字体缺?LUT 缺?写一份缺口表
7. **周五**:把这 8 周路线图填到你们的 issue tracker(Linear / GitHub Projects),每个 Sprint 一个 epic

---

## 第七部分:几个不会让你舒服但必须听的话

我以资深视角说几个**你可能不爱听但躲不掉**的事:

1. **你的"12 Agent"叙事是营销话术,不是技术现实。** 你的代码本质是 LangGraph + SkillRegistry 的混合工作流引擎。把它叫"多智能体系统"听起来高大上,但会误导工程决策(比如想给每个 agent 都加 memory、加 tool),实际上你需要的是工作流稳定性、合规一致性、产出质量。**用工作流引擎的思维管理它**。

2. **Mock 模式正在毒害你的判断力。** 553 个测试通过、4 个场景"成功",但**你产出过几条真实可发布的视频?** 这个数字才是诚实的进度。在你回答这个数字之前,讨论"Phase R10 计划"是无效的。

3. **多语言对你不是核心竞争力,是品类要求。** 母婴垂直如果不做 ES/FR/DE,等于不做美国之外。但**它不会让你赢**——HeyGen 也支持 30 多语言。你赢在垂直深度 + 合规精度,语言只是入场券。

4. **品牌资产入库是你被低估的护城河。** brand-asset-template.md 是金矿——这是别人没花心思做的差异化。如果你能做到"输入 100 个 brand 字段,产出和这个品牌真实视频 80% 像",这是 SaaS 时代的 picks-and-shovels。**优先级应该比新场景高**。

5. **你不需要现在就有数据反馈回路。** Analytics → Strategy 听起来很 fancy,但**前 3 个月你产出的视频不会多到形成统计意义的反馈**。先把生产质量做到能用,数据回路是 Q3 的事。

6. **"audit / self-verification" 是你架构里的一个微小亮点,但不要过度抽象。** 当前 audit 节点设计是合理的(每个工作节点配审计),但 4 个 audit_node 都用 LLM 是浪费成本。考虑:轻量场景(strategy/thumbnail) 用规则引擎,重量场景(script/edit) 用 LLM。

7. **不要再加新场景了。** 你已经有 4 个,实际跑通 0 个。再加 S5/S6 是逃避——逃避把现有跑通的痛苦。**这个产品的死亡风险不是不够大,是不够深**。

---

## 总结:决策矩阵

| 问题 | 我的强建议 |
|------|-----------|
| 路径 A/B/C 选哪个? | **A**(垂直工厂),3 个月后再考虑 B |
| S2 是否合并到 S1? | **是**,brand_mode 标志位区分 |
| S4 是否暂缓? | **是**,先专注 S1+S3 |
| Postgres 何时启用? | **本周**(Sprint 0) |
| 真实模式何时验证? | **本周**(Sprint 0 的 spike) |
| 多语言何时全闭环? | **第 7 周**(Sprint 6) |
| 多租户/Auth 何时做? | A 路径**不做**,B 路径第 9 周 |
| 平台真发布何时做? | **第 8 周**(Sprint 7) |
| 新场景何时加? | **3 个月后**或**永远不**(取决于 A 验证结果) |

---

## 附录:认知校准 — 关于你 roadmap 中的"乐观估计"

你的 multi-scenario-roadmap 里写"R1-R8 已完成,~20 源文件,~197 测试"。我刚扫描的真实数字:

- 源文件:**60+ 个 .py 文件**(不是 20)
- 测试函数:**553 个**(不是 197)
- 但**真实可发布产出:0 条**

这种乐观估计在每个 startup 都常见,但它会让你**误判产品成熟度**。你的实际状态是:

> **"基建过剩,产出不足"**——拖久了会变成"工程师博物馆"。

最大的风险不是某个功能缺失,是**路线图本身在自我安慰**。我这份分析的价值,如果能让你重新思考"完成了什么 vs 还差什么"的定义,就值了。

---

**结束**

下一步:你读完这份后告诉我,
1. 你最不同意的一段是什么?(我们辩一辩)
2. 你最想立刻做的一件事是什么?(我帮你拆任务)
3. 走 A / B / C 哪条路?(影响后续所有决策)
