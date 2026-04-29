# Phase 1 实施计划 — 短视频Agent系统 MVP

> **目标**：跑通英语单语种12节点完整流水线，产出第一条全流程视频
> **工期**：3-4周
> **策略**：先骨架后血肉，每个Agent先用LLM Prompt实现核心逻辑，API集成（Remotion/ElevenLabs等）用stub或mock先行，后续替换为真实API

---

## 任务清单

### Task 1: 项目脚手架搭建
**Objective**: 创建Python项目结构、依赖管理、目录布局
**Files**:
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `src/models/state.py` (LangGraph State定义)
- Create: `src/agents/__init__.py`
- Create: `src/tools/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.env.example`
- Create: `Makefile`

**Step 1**: 创建 pyproject.toml
```toml
[project]
name = "short-video-agent"
version = "0.1.0"
description = "Multi-agent short video creation system for cross-border e-commerce"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-anthropic>=0.3.0",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
    "supabase>=2.0",
    "httpx>=0.27",
    "redis>=5.0",
    "celery>=5.3",
]
```

**Step 2**: 创建 State 模型
**Step 3**: 验证 `pip install -e . && python -c "from src.models.state import VideoPipelineState; print('OK')"`

---

### Task 2: LangGraph 流水线骨架
**Objective**: 搭建12节点的状态图，包含4个人审checkpoint
**Files**:
- Create: `src/graph/__init__.py`
- Create: `src/graph/pipeline.py` (主流水线定义)
- Create: `src/graph/nodes.py` (12个占位节点函数)
- Create: `src/graph/routing.py` (条件路由：合规检查/语言路由)

**Step 1**: 定义12个占位节点，每个返回固定mock数据
**Step 2**: 实现 compile() 函数，连接节点 + 条件边
**Step 3**: 实现人审checkpoint（interrupt_before=["human_review_1", ...]）
**Step 4**: 测试 `pytest tests/test_graph.py -v` — 验证图可以编译并执行到第一个checkpoint

---

### Task 3: Node 1 — 选题策略师 (Strategy Agent)
**Objective**: 实现选题Agent，输入产品信息+趋势数据 → 输出周选题日历
**Files**:
- Create: `src/agents/strategy.py`
- Create: `src/agents/prompts/strategy_en.py`
- Create: `tests/test_strategy.py`

**核心Prompt结构**:
- Role: Senior content strategist for baby-feeding e-commerce brand
- Input: Product catalog, platform trends, competitor analysis, seasonal calendar
- Output: JSON with weekly briefs (topic, video_type, target_audience, platforms, key_message, usp_priority)
- Constraints: Avoid medical claims, match brand tone

**Step 1**: 写Prompt模板（带few-shot示例）
**Step 2**: 实现 agent.run() 调用LLM
**Step 3**: 测试输出JSON格式+字段完整性

---

### Task 4: Node 2 — 脚本编剧 (Script Writer Agent)
**Objective**: 把Brief变成45秒平台适配脚本
**Files**:
- Create: `src/agents/script_writer.py`
- Create: `src/agents/prompts/script_writer_en.py`
- Create: `tests/test_script_writer.py`

**核心Prompt结构**:
- Role: Award-winning short video copywriter
- Input: Brief JSON from Node 1
- Output: Structured script with timing [0-3s hook, 3-8s pain, 8-20s solution, 20-35s trust, 35-45s CTA]
- Platform adaptation: TikTok (fast pace) / YouTube Shorts (search intent) / Facebook (emotional)
- Constraints: Natural English, no corporate speak, must pass compliance review

**Step 1**: 写Prompt + 多平台变体模板
**Step 2**: 实现 agent.run()
**Step 3**: 测试脚本结构+时长估算

---

### Task 5: Node 3 — 合规审核官 (Compliance Agent)
**Objective**: 自动检测脚本中的合规风险
**Files**:
- Create: `src/agents/compliance.py`
- Create: `src/agents/prompts/compliance_en.py`
- Create: `src/data/compliance_rules.yaml` (敏感词/禁止声明清单)
- Create: `tests/test_compliance.py`

**双层检测**:
1. 规则引擎：YAML规则库 + 正则匹配（快速，确定性）
2. LLM审核：GPT-4o structured output（语义理解，模糊边界）

**检测项**: 医疗声明 / 裸露暗示 / 未证实对比 / 平台敏感词 / 儿童合规

**Step 1**: 创建compliance_rules.yaml
**Step 2**: 实现规则引擎扫描
**Step 3**: 实现LLM审核 + JSON output parsing
**Step 4**: 测试 FLAGGED / BLOCKED 场景

---

### Task 6: Node 4 — 视觉分镜师 (Storyboard Agent)
**Objective**: 脚本 → 镜头序列（shot list）
**Files**:
- Create: `src/agents/storyboard.py`
- Create: `src/agents/prompts/storyboard.py`
- Create: `tests/test_storyboard.py`

**Step 1**: Prompt设计（脚本行→镜头画面描述+时长+文字叠加+素材需求）
**Step 2**: 实现 agent.run()
**Step 3**: 测试shot list JSON schema

---

### Task 7: Node 5 — 素材采编师 (Asset Sourcing Agent)
**Objective**: 根据shot list的asset_needed从素材库匹配
**Files**:
- Create: `src/agents/asset_sourcing.py`
- Create: `src/tools/asset_search.py` (Supabase pgvector查询)
- Create: `tests/test_asset_sourcing.py`

**MVP策略**: 先用本地文件系统mock，后续接Supabase pgvector

**Step 1**: 实现向量搜索stub（返回固定mock结果）
**Step 2**: 实现匹配逻辑（需求→候选→最优→Gap Report）
**Step 3**: 测试匹配+缺素材场景

---

### Task 8: Node 6 — AI素材生成师 (stub)
**Objective**: 占位实现，返回"需要AI生成"标记
**Files**:
- Create: `src/agents/media_generation.py`
- Create: `tests/test_media_gen.py`

**MVP策略**: 纯stub，标记gap assets为`[AI-GENERATED-PLACEHOLDER]`

---

### Task 9: Node 7 — 视频剪辑师 (Editing Agent)
**Objective**: 素材+分镜 → 视频时间线描述（先不实际渲染）
**Files**:
- Create: `src/agents/editor.py`
- Create: `src/tools/remotion_client.py` (stub)
- Create: `tests/test_editor.py`

**MVP策略**: 产出Remotion Composition JSON描述文件，不实际渲染。Phase 1末尾再接入真实Remotion渲染。

---

### Task 10: Node 8 — 音频设计师 (Audio Agent)
**Objective**: 脚本 → TTS配音+BGM选曲方案
**Files**:
- Create: `src/agents/audio_designer.py`
- Create: `src/tools/elevenlabs_client.py` (stub)
- Create: `tests/test_audio.py`

**MVP策略**: ElevenLabs stub返回mock音频路径

---

### Task 11: Node 9 — 字幕/文案包装师 (Caption Agent)
**Objective**: 脚本 → 字幕时间轴+花字方案
**Files**:
- Create: `src/agents/caption.py`
- Create: `tests/test_caption.py`

**MVP策略**: 产出SRT格式字幕+花字配置JSON

---

### Task 12: Node 10 — 封面设计师 (Thumbnail Agent)
**Objective**: 视频元数据 → 4版缩略图候选描述
**Files**:
- Create: `src/agents/thumbnail.py`
- Create: `tests/test_thumbnail.py`

**MVP策略**: 产出4版缩略图的prompt描述，DALL-E/Flux调用stub

---

### Task 13: Node 11 — 平台分发运营师 (Distribution Agent)
**Objective**: 视频+元数据 → 各平台发布计划
**Files**:
- Create: `src/agents/distribution.py`
- Create: `src/tools/platform_api.py` (stub)
- Create: `tests/test_distribution.py`

**MVP策略**: 产出发布schedule JSON，不实际调用平台API

---

### Task 14: Node 12 — 数据分析师 (Analytics Agent)
**Objective**: 回收数据 → 分析报告
**Files**:
- Create: `src/agents/analytics.py`
- Create: `tests/test_analytics.py`

**MVP策略**: 产出mock分析报告模板

---

### Task 15: 人审Web界面 v0
**Objective**: Next.js审批界面，4个审批节点
**Files**:
- Create: `web/` (Next.js项目)
- Create: `web/src/app/page.tsx`
- Create: `web/src/components/ReviewCard.tsx`

**MVP范围**: 显示待审批内容 + 通过/驳回按钮

---

### Task 16: 端到端集成测试
**Objective**: 跑通完整流水线，产出第一条视频的所有中间产物
**Files**:
- Create: `tests/test_e2e_pipeline.py`
- Create: `scripts/run_pipeline.py`

**Step 1**: 写E2E测试（mock所有外部API）
**Step 2**: 验证12节点全部执行
**Step 3**: 验证4个人审checkpoint触发
**Step 4**: 验证输出完整性

---

## 执行顺序

```
Task 1 (脚手架) → Task 2 (骨架)
    ↓
Task 3 (策略) → Task 4 (脚本) → Task 5 (合规) → Task 6 (分镜)
    ↓
Task 7 (素材) → Task 8 (AI生成) → Task 9 (剪辑)
    ↓
Task 10 (音频) → Task 11 (字幕) → Task 12 (封面)
    ↓
Task 13 (分发) → Task 14 (数据)
    ↓
Task 15 (界面) → Task 16 (E2E测试)
```

---

## 验证标准

每条视频产出的中间产物链：
```
brief.json → script.json → compliance_report.json → storyboard.json
→ asset_plan.json → edit_composition.json → audio_plan.json
→ captions.srt → thumbnails.json → distribution_plan.json → analytics_report.json
```

所有JSON必须通过Pydantic schema验证。
