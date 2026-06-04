---
title: AI 商业化视频生成技术调研与项目内化方案
doc_type: analysis
module: ai-video
topic: commercial-generation-technology
status: review
created: 2026-06-03
updated: 2026-06-03
owner: self
source: human+ai
---

# AI 商业化视频生成技术调研与项目内化方案

> 快照边界：本文基于 2026-06-03 的项目状态、外部公开文档与调研结论整理。视频模型、价格、时长、审核策略和 API 能力变化很快，任何真实 token 消耗、生产默认模型切换或成本承诺前，必须重新核对官方文档和当前供应商后台。

## 1. 结论摘要

当前项目不应走“接入更多单点视频模型”的路线。更稳的方向是升级为一个商业 AI 视频生产系统：

- 保留 S1-S5 场景，不重构场景定义。
- 把视频生成拆成短片段生成、参考资产控制、后期合成、质量审计、品牌审计、权利追踪。
- 把图片、故事板、演示视频、数字人、语音克隆、音乐、音效、字幕、海报、C2PA 等能力做成工具箱。
- 把品牌视频和品牌资产先转成可检索、可注入、可审计的 Brand Asset Token，再进入 S1-S5 工作流。

反面方案是“快速接入 Veo、Runway、Kling、HeyGen、ElevenLabs 等更多 provider”。这个方案短期看功能变多，但会放大 prompt 漂移、品牌一致性差、授权不可追踪、质量不可比较、成本不可控的问题。因此它只能作为 adapter 扩展，不应作为架构主线。

## 2. 证据边界

### 2.1 项目内证据

- 当前项目已经有 S1-S5 + Fast Mode，后端为 FastAPI + LangGraph/StepRunner，前端为 Next.js，渲染为 Remotion。
- S1/S2/S3/S4/S5 已有不同 step order，说明项目不是空白生成器，而是多场景生产流水线。
- 项目已有 `model_router.py`、`model_thresholds.py`、`src/quality/`、`media_quality_audit.py`、`c2pa_signer.py` 等基础能力，但它们尚未形成统一的跨场景质量合同。
- `docs/claude/known-gaps-stable.md` 已明确当前 POYO balance 约束：充值前优先做 hermetic/mock/unit/lint/docs，不应直接消耗真实 token 做循环试错。

### 2.2 外部调研证据

- Google Veo、Runway Gen-4、Seedance、Sora 等主流视频生成能力仍以短片段、参考图/参考素材、异步任务、后期组装为主，不适合直接假设“一次生成完整商业广告”。
- Runway、Veo、Sora 等 prompt 指南对 prompt 结构偏好不同，说明项目需要 provider-specific prompt compiler，而不是单一通用 prompt。
- HeyGen、Synthesia 更适合 presenter / avatar / demo video，不应强行用通用 T2V 模型生成稳定 talking-head。
- ElevenLabs 的能力已经覆盖 TTS、voice cloning、dubbing、sound effects、music 等音频工具链，应作为 audio toolbox，而不是仅作为旁白 TTS。

## 3. 行业技术趋势与项目含义

### 3.1 短片段生产仍是主流

主流视频模型常见能力边界仍集中在 4-15 秒片段。商业视频需要稳定品牌表达、节奏控制、字幕、音频、封面、平台适配和合规记录，因此工程形态应是：

```text
strategy
  -> storyboard / shot grid
  -> keyframe / reference asset
  -> provider-specific video prompt
  -> async clip generation
  -> clip QC
  -> Remotion / post production
  -> brand + compliance + quality audit
```

项目含义：继续强化 S1-S5 的 clip-based workflow，不追求 one-shot full video。

### 3.2 品牌一致性从 prompt 文案转向 reference system

高质量商业视频不能只依赖“高级、温暖、母婴、真实感”这类自然语言描述。品牌一致性需要结构化资产：

- 色彩、字体、构图、镜头距离、运动节奏。
- 产品真实卖点、禁用 claim、合规词表。
- 品牌语气、字幕风格、音乐情绪。
- 授权状态、地域、有效期、来源证明。

项目含义：品牌视频加入项目后，不应直接作为生成参考。先提取 Brand Asset Token，再由场景工作流选择性注入。

### 3.3 Prompt compiler 比 prompt 模板更重要

不同 provider 的 prompt 习惯不同：

- Runway 更偏简单、正向、运动描述清晰的镜头语言。
- Veo 更强调 subject、action、style、camera、composition、lens、audio 等结构化维度。
- Sora 强调 timing、camera、audio intent、remix/editing 语义。
- Seedance / Kling / Wan 需要结合 provider 支持的参考图、首尾帧、原生音频、多镜头能力做裁剪。

项目含义：统一的上游应该是 `StoryboardShotSchema`，而不是直接维护多套自然语言 prompt。

```text
StoryboardShotSchema
  -> RunwayPromptCompiler
  -> VeoPromptCompiler
  -> SeedancePromptCompiler
  -> KlingPromptCompiler
  -> SoraPromptCompiler
```

### 3.4 原生音频不能替代后期音频层

部分视频模型支持 native audio 或 lip sync，但商业视频的音频应拆层：

- voiceover / dialogue
- music bed
- sound effects
- ambient
- native model audio
- captions / forced alignment

项目含义：S1-S5 可以保留 native audio 作为草稿或参考，但最终交付应由 audio toolbox 统一控制。

### 3.5 数字人和演示视频应独立成 presenter lane

品牌讲解、产品演示、客服说明、教程视频更适合 HeyGen/Synthesia 这类 avatar/presenter API。通用 T2V 模型擅长画面生成，不擅长稳定身份、口型、长段口播和企业演示一致性。

项目含义：新增 `presenter-demo` 工具能力，不直接塞入 S1-S5 主链。S1-S5 只在需要时调用 presenter clip。

## 4. 当前 S1-S5 工作流审计

### 4.1 S1 Product Direct

当前能力：

- S1 是最成熟链路，覆盖 strategy、script、compliance、storyboard、keyframe、video prompt、video clips、TTS、thumbnail、assemble、audit。
- 已有连续性 storyboard grid、partial artifacts、stub detection、C2PA signing 等基础。

主要缺口：

- brand constraint 仍偏自然语言字段，缺少 token 化约束。
- video prompt 未完全 provider-specific。
- 质量审计和品牌审计没有形成统一 gate contract。

改良方向：

- 把 product truth、visual reference、tone voice、negative guardrail 注入 strategy/script/storyboard/video prompt/thumbnail/audit。
- 对 keyframe、clip、final video 分别建立质量门槛。
- 使用 fixed benchmark inputs 做 S1 的模型对比，不用生产请求随意试错。

### 4.2 S2 Brand Campaign

当前能力：

- S2 有独立 pipeline contract，但 StepRunner 中仍存在 S1 wrapper 的映射痕迹。
- 品牌战役方向成立，但品牌差异化还没有成为独立能力核心。

主要缺口：

- S2 与 S1 的边界不够清晰。
- 品牌 campaign 的 tone、visual identity、claim substantiation、platform adaptation 没有独立打分。

改良方向：

- 明确 S2 是品牌战役，不是商品直拍的轻微变体。
- 增加 campaign idea、brand memory、visual motif、message hierarchy。
- 把 `brand-token-audit-skill` 作为 S2 gate 的关键指标。

### 4.3 S3 Influencer Remix

当前能力：

- S3 已有 video analysis、character identity、remix script、storyboard、keyframe、clip、TTS、assemble、audit。
- 已有 viral extraction disabled 的政策边界。

主要缺口：

- Remix 场景天然涉及版权、肖像、风格借鉴和素材来源风险。
- 当前链路更像内容改写，缺少权利和风格边界判定。

改良方向：

- 加 `rights_license` 前置硬 gate。
- 加 source fingerprint、creator consent、likeness permission、copyright risk 字段。
- 明确“学习结构和节奏”与“复制具体人物/画面/声音”的边界。
- 输出 audit 时同时给出 brand alignment 与 rights pass。

### 4.4 S4 Live Shoot

当前能力：

- S4 面向 live shoot，适合真实素材、库存素材、口播素材、短视频快创。
- 已有 footage validation、stock fallback、prompt/thumbnail/assemble 方向。

主要缺口：

- 素材 QC、镜头切分、转写、补拍建议、节奏重排还没有变成工具链。
- 部分 skill 注册存在依赖 import 顺序的风险，应在后续代码阶段显式修正。

改良方向：

- 建立 footage intake 工具：清晰度、时长、主体、语音、横竖屏、安全区、可用片段。
- 建立 shot extraction + supercut planner。
- 用 brand token 约束字幕、节奏、片头片尾、CTA。

### 4.5 S5 Brand VLOG

当前能力：

- S5 已有 vlog strategy、clip group、continuity、video prompt、video generation、TTS、assemble、audit。
- 对儿童可识别面部/全身形象已有硬 guardrail。

主要缺口：

- 品牌调性、人物感、场景节奏和产品露出仍需要更强的 token 控制。
- continuity manager 的注册应显式化，避免依赖外部 import。

改良方向：

- 建立 persona token、scene token、rhythm token、product truth token。
- 把儿童安全 guardrail 作为 hard negative token 固定在品牌约束包中。
- 对多 clip 做 continuity audit：人物一致性、场景连贯、产品位置、色彩风格、叙事节奏。

## 5. 目标架构：AI 商业视频工具库

### 5.1 核心层

```text
Scenario Workflow Layer
  S1 Product Direct
  S2 Brand Campaign
  S3 Influencer Remix
  S4 Live Shoot
  S5 Brand VLOG

Creative Schema Layer
  StrategyBrief
  ScriptSchema
  StoryboardShotSchema
  BrandConstraintBundle
  MediaJobSpec
  QualityContract

Toolbox Layer
  Image Toolbox
  Video Provider Toolbox
  Audio Toolbox
  Presenter Toolbox
  Storyboard Toolbox
  Post-production Toolbox
  Audit Toolbox

Provider Adapter Layer
  PoYo / Seedance
  Kling
  Runway
  Veo
  Sora
  LTX / Wan
  ElevenLabs
  HeyGen / Synthesia
```

### 5.2 工具箱清单

| 工具箱 | 核心能力 | 进入 S1-S5 的方式 |
|---|---|---|
| Image Toolbox | keyframe、thumbnail、product render、background replace、inpaint、upscale | S1/S2/S3/S5 keyframe 和 thumbnail |
| Storyboard Toolbox | shot grid、camera、lens、motion、composition、platform variants | 所有场景 video prompt 上游 |
| Video Provider Toolbox | T2V、I2V、reference video、first/last frame、async polling | seedance_clips 等生成节点 |
| Presenter Toolbox | digital twin、avatar video、product demo、training video | S2/S4 作为可选 clip |
| Audio Toolbox | TTS、voice clone、dubbing、SFX、music、alignment | 所有场景 final assemble |
| Post-production Toolbox | captions、poster、aspect variants、intro/outro、C2PA | assemble_final 之后 |
| Audit Toolbox | quality、brand、rights、safe-zone、claim、provenance | gate 和 final audit |

## 6. Brand Asset Token 计划

### 6.1 不直接使用品牌视频

品牌调性视频进入项目后，先执行四步：

1. `intake`：记录来源、授权、地域、有效期、PII、是否含人物肖像、是否含第三方版权素材。
2. `extract`：抽取色彩、镜头、节奏、字幕、音乐、口吻、产品露出、禁用表达。
3. `tokenize`：转成结构化 Brand Asset Token。
4. `review`：人工确认后进入可用 token 池。

未确认的品牌视频不得直接作为生产 reference。

### 6.2 Token 类型

| Token 类型 | 作用 | 硬/软约束 |
|---|---|---|
| `visual_identity` | 色彩、字体、构图、质感 | soft |
| `tone_voice` | 语言风格、句式、情绪 | soft |
| `product_truth` | 产品事实、卖点、规格、禁用 claim | hard |
| `visual_reference` | 产品图、场景图、人物/手部/环境参考 | hard/soft |
| `motion_editing` | 镜头运动、剪辑节奏、转场 | soft |
| `caption_style` | 字幕位置、大小、语气、emoji 禁用 | soft |
| `persona_audience` | 目标人群、角色抽象、使用场景 | soft |
| `platform_compliance` | TikTok/Reels/YouTube Shorts 合规偏好 | hard |
| `rights_license` | 授权、地域、期限、来源证明 | hard |
| `negative_guardrail` | 禁止画面、禁止 claim、儿童安全、肖像限制 | hard |
| `performance_signal` | 历史表现好的节奏/卖点/封面模式 | soft |

### 6.3 Runtime Bundle

运行时不要把所有 token 全塞给模型，而是按场景、步骤、平台筛选成 `BrandConstraintBundle`：

```json
{
  "brand_id": "momcozy",
  "scenario": "s2",
  "platform": "tiktok",
  "positive_prompt_blocks": [],
  "negative_prompt_blocks": [],
  "asset_refs": [],
  "claim_rules": [],
  "audit_rubric": [],
  "token_ids": []
}
```

### 6.4 场景注入策略

| 场景 | 注入重点 |
|---|---|
| S1 | product truth、visual reference、thumbnail style、negative claim |
| S2 | visual identity、tone voice、campaign motif、claim substantiation |
| S3 | rights_license、style boundary、brand constraint、source fingerprint |
| S4 | footage QC、caption style、CTA、live shoot rhythm |
| S5 | persona audience、scene rhythm、children safety、vlog tone |

## 7. Autoresearch 后续任务

正式执行 autoresearch 前，先定义 mission 和 evaluator，避免调研发散。

### 7.1 Mission

验证“Brand Asset Token + Provider Prompt Compiler + 多工具箱后期链路”是否能提升 S1-S5 的商业视频可用率，同时控制成本、失败率和合规风险。

### 7.2 Evaluator 输出

```json
{
  "pass": false,
  "score": 0.0,
  "scenario_scores": {
    "s1": 0.0,
    "s2": 0.0,
    "s3": 0.0,
    "s4": 0.0,
    "s5": 0.0
  },
  "brand_alignment": 0.0,
  "rights_pass": false,
  "quality_score": 0.0,
  "cost": 0.0,
  "latency_seconds": 0,
  "failure_rate": 0.0,
  "evidence": []
}
```

### 7.3 研究任务

1. Provider capability matrix refresh：只核对官方文档，不消耗 token。
2. Prompt compiler A/B：同一 storyboard 编译到不同 provider prompt，先做离线审计。
3. Brand token extraction benchmark：用 10 条品牌视频抽 token，评估一致性和可解释性。
4. Audio toolbox benchmark：比较 TTS、voice clone、music、SFX、alignment 的生产可用性。
5. Rights/compliance stress test：针对 S3 remix、S5 children safety、product claim 做红队测试。

## 8. 实施计划

### Phase 0：规格固化与风险校准

状态：不消耗真实 token；不改生产默认模型。

任务：

- 固化 `BrandAssetToken`、`BrandConstraintBundle`、`StoryboardShotSchema`、`MediaJobSpec`、`QualityContract` 的文档规格。
- 校准 S2 与 S1 的边界。
- 后续允许代码修改时，优先修正 S4/S5 skill 显式 import 和 brand_guidelines 传递。

验收：

- S1-S5 每个场景都有明确 token 注入点。
- 每个 provider 能力只记录已核实字段，未知字段标 `unknown`。
- 不把 leaderboards 当业务质量结论。

### Phase 1：品牌 token 最小闭环

任务：

- 建立规则型 tokenizer。
- 建立 rights/license hard gate。
- 建立 brand-token-audit rubric。

验收：

- 一组品牌资产能生成可审计 token。
- S1/S2/S5 能读取同一份 brand bundle。
- hard negative token 不会被 prompt compiler 丢失。

### Phase 2：Provider compiler 与异步账本

任务：

- 用统一 storyboard schema 生成 provider-specific prompt。
- 建立 media job ledger。
- 记录 prompt hash、provider、model、reference asset、cost、latency、failure reason。

验收：

- 同一 storyboard 可生成至少 3 种 provider prompt。
- 所有真实生成任务可追踪、可复盘、可清理。

### Phase 3：工具箱扩展

任务：

- 接入 image、audio、presenter、music、post-production 工具箱。
- 将工具箱作为 adapter，不直接破坏 S1-S5 的场景定义。

验收：

- S1-S5 可以按需调用工具箱。
- 工具箱输出统一进入 MediaJobSpec 和 QualityContract。

### Phase 4：质量和品牌 gate

任务：

- 将 CLIP、safe-zone、face consistency、scene quality、brand alignment、rights pass、claim substantiation 汇入统一评分。
- 区分 blocking gate 与 advisory report。

验收：

- 每个 final video 都有质量证据、品牌证据、权利证据。
- S3/S5 的安全和合规 gate 是硬门槛。

### Phase 5：真实 token 小样本 benchmark

前置条件：

- 供应商余额已确认。
- 测试资产、品牌 token、输入 brief、评分表固定。
- 生产真实请求开关明确打开。

任务：

- 对 S1-S5 各跑小样本。
- 比较成本、耗时、失败率、品牌一致性、最终可用率。
- 把结果回写 capability matrix 和 model routing 策略。

验收：

- 不以“生成成功”作为唯一成功标准。
- 必须同时满足品牌一致性、素材权利、质量门槛、成本边界。

## 9. 验证门槛

充值前：

- `ruff check src tests --statistics`
- frontend ESLint / TypeScript / Vitest / demo build
- OpenAPI drift check
- S1-S5 hermetic regression，必要时确保 `.venv/bin` 在 PATH 中
- docs/spec review

充值后：

- 固定 benchmark prompt
- 固定 brand token set
- 固定 reference assets
- 固定 evaluator
- 小批量真实生成
- 输出 prompt hash、artifact path、provider job id、cost、latency、audit score

不要把 full pytest 单独当最终 oracle；它在当前仓库历史上混有真实问题和 stale test drift。

## 10. 外部参考

- Google Veo API / prompt guide: <https://ai.google.dev/gemini-api/docs/video>
- Runway Gen-4 prompting guide: <https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide>
- OpenAI Sora Help: <https://help.openai.com/en/articles/12460853>
- PoYo Seedance 2 docs: <https://docs.poyo.ai/api-manual/video-series/seedance-2>
- Seedance 2 model card: <https://arxiv.org/abs/2604.14148>
- ElevenLabs overview: <https://elevenlabs.io/docs/overview/intro/>
- ElevenLabs sound generation: <https://elevenlabs.io/docs/api-reference/sound-generation>
- ElevenLabs music: <https://elevenlabs.io/docs/capabilities/music/>
- HeyGen avatar video API: <https://developers.heygen.com/generate-avatar-video>
- Synthesia API: <https://docs.synthesia.io/reference/introduction>
- Artificial Analysis video leaderboard: <https://artificialanalysis.ai/video/leaderboard/text-to-video>
- Arena text-to-video leaderboard: <https://arena.ai/leaderboard/text-to-video>
