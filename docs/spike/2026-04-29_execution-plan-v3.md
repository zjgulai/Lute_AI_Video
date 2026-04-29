# 分层可执行计划 v3 —— Expert Studio 首发

> 基于 2026-04-28 深夜最终产品讨论
> 原则：基于当前产品形态演进，不做彻底重写
> 默认模式：专家工作台 Expert Studio

---

## 零、核心设计决策（已确认）

| # | 决策 | 结论 |
|---|------|------|
| D1 | 默认模式 | Expert Studio（专家工作台） |
| D2 | 双脚本分叉 | 仅 Gate 4 终审时对比，Gate 2-3 仅审执行首选版本 |
| D3 | 三场景入口 | 三个独立 tab，不做智能分流 |
| D4 | 时长策略 | AI 后置推荐，strategy 步骤后展示 |
| D5 | 候选机制 | 3 候选，AI 推荐 ★ 默认选中，同 Gate 最多选 2 |
| D6 | 改造策略 | 演进式：复用现有组件，逐步增强 |

---

## 一、分层架构总览

```
                        ┌─────────────────────────┐
                        │    交互层 (UI Layout)     │
                        │  SceneTabs + DynamicForm  │
                        │  StageProgress / GatePanel │
                        └───────────┬─────────────┘
                                    │
                        ┌───────────▼─────────────┐
                        │    模式层 (Mode Router)   │
                        │  Smart Create: 3-stage    │
                        │  Expert Studio: 4-Gate    │
                        └───────────┬─────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
┌───────────┐               ┌───────────┐               ┌───────────┐
│  Gate 1   │               │  Gate 2   │               │  Gate 3/4 │
│ScriptSelect│              │KeyframeOK │               │Clip+Final │
│3 candidates│              │Approve    │               │Compare    │
│ pick 1-2  │              │ regenerate│               │  publish  │
└─────┬─────┘               └─────┬─────┘               └─────┬─────┘
      │                           │                           │
      └───────────────────────────┼───────────────────────────┘
                                  │
                        ┌─────────▼───────────┐
                        │      引擎层 (不变)    │
                        │  12-step pipeline    │
                        │  StepRunner          │
                        │  SkillRegistry       │
                        │  StateManager        │
                        └─────────────────────┘
```

**关键约束：引擎层不动。所有改动在交互层和模式层。**

---

## 二、Layer 1 — 交互层改造

### 2.1 目标状态 vs 当前状态 对照

```
当前:                                          目标:
┌────────────────────────────┐                 ┌────────────────────────────┐
│ DurationSlider (5 tiers)   │                 │ SceneTabs: Product │ Brand  │
│ SceneSelector (3 cards)    │                 │           │ Influencer      │
│ Product form (inline)      │                 │ ────────────────────────── │
│ API keys (collapsible)     │                 │ DynamicForm (per scene)     │
│ Asset uploader             │                 │   Product: name+USP        │
│ Scene description (right)  │                 │   Brand: package+campaign   │
│ [配置完成 →]               │                 │   Influencer: URL+product  │
│                            │                 │ ────────────────────────── │
│                            │                 │ [Continue →]               │
│                            │                 │ ────────────────────────── │
│                            │                 │ Recent Videos (horizontal)  │
└────────────────────────────┘                 └────────────────────────────┘
```

### 2.2 复用的现有组件

| 现有组件 | 改造方式 |
|---------|---------|
| `SceneSelector.tsx` | **拆分**：场景卡片部分 → `SceneTabs.tsx`；表单部分 → `SceneForm.tsx` |
| `DurationSlider.tsx` | **移位**：从首页移到推荐确认步骤（Step 2），props 不变 |
| `StepByStepView.tsx` | **增强**：加 Gate 暂停点，但保留逐步骤执行能力 |
| `OneShotResultView.tsx` | **增强**：Gate 4 增加双版本对比面板 |
| `QualityDashboard.tsx` | **降级**：从主 tab 移到 Gate 4 展开区 |
| `PipelineMonitor.tsx` | **保留**：用于 Smart Create 的 3 阶段进度条 |
| `Nav.tsx` | **保留**：链接增加 "历史记录" |

### 2.3 新增组件清单

| 新组件 | 职责 | 行数预期 |
|--------|------|---------|
| `SceneTabs.tsx` | 3 个场景 tab + 每个 tab 下显示该场景已创建视频数 | ~60 |
| `SceneForm.tsx` | 根据 scene props 渲染不同表单字段 | ~120 |
| `StageProgress.tsx` | Smart Create 的 3 阶段进度条（文案/画面/导出） | ~80 |
| `GatePanel.tsx` | Gate 1-4 的通用审批框架（标题 + 进度 + 内容区 + 操作栏） | ~100 |
| `CandidateSelector.tsx` | 3 候选对比卡片（★ 推荐高亮 + 选中 + 编辑） | ~150 |
| `CompareView.tsx` | Gate 4 双版本并排对比 | ~80 |

### 2.4 Page 改造方案（page.tsx）

```
当前 page.tsx 状态：
  - SplashScreen → DurationSlider → SceneSelector → OneShotResultView

改造后 page.tsx 状态：
  - 顶层始终渲染：Nav + SceneTabs
  - Step 0（首页）：SceneTabs + SceneForm + RecentVideos
  - Step 1（推荐确认）：AI 推荐面板（时长/平台/策略摘要） + [Start →]
  - Step 2（生成中）：StageProgress（Smart Create）或 GatePanel（Expert Studio）
  - Step 3（结果）：OneShotResultView（增强版）
```

实现方式：`page.tsx` 用 `pipelineStage` 状态管理 4 个阶段，每个阶段渲染对应组件。不删现有代码——逐步包裹。

---

## 三、Layer 2 — 模式层

### 3.1 模式路由

```typescript
// page.tsx
const [mode, setMode] = useState<"smart" | "expert">("expert");

// Step 1 确认推荐后：
if (mode === "smart") {
  // Smart Create: 全自动执行，展示 3 阶段进度
  startAutoPipeline(config, label);
} else {
  // Expert Studio: Gate-by-Gate 执行
  startExpertPipeline(config, label);
}
```

### 3.2 智能快创（Smart Create）实现

复用现有自动模式 + 新增 `StageProgress` 组件。

**前端：**
```typescript
const STAGES = [
  { id: "writing", label: "Writing Script", steps: ["strategy","scripts","compliance"] },
  { id: "visuals", label: "Generating Visuals", steps: ["storyboards","keyframe_images","video_prompts","seedance_clips"] },
  { id: "export",  label: "Rendering & Export", steps: ["tts_audio","thumbnail_images","assemble_final","audit"] },
];
```

`StageProgress` 轮询 `/scenario/s1/state/{label}`，根据 `current_step` 和 `steps` 的状态计算当前阶段。阶段完成时高亮，当前阶段脉冲动画。

**后端：** 零改动。现有 auto 模式已支持全自动执行。

### 3.3 专家工作台（Expert Studio）实现

在现有逐步模式基础上增加 Gate 暂停点。

**后端新增：Gate 状态管理**

在 `state_manager` 保存的 state 中增加：
```python
{
  "gates": {
    "gate_1_script": {"status": "pending", "candidates": [...]},
    "gate_2_keyframe": {"status": "pending", "approvals": [...]},
    "gate_3_clips": {"status": "pending", "selections": [...]},
    "gate_4_final": {"status": "pending", "comparison": {...}},
  }
}
```

**后端新增：候选生成 API**

```
POST /scenario/s1/candidates/{step_name}
  → 对指定步骤生成 3 个候选（调用 Skill 3 次，每次不同 variant 参数）
  → 返回: { candidates: [{id, data, score, recommended: bool}] }

POST /scenario/s1/gate/{gate_id}/approve
  → 记录 Gate 审批结果，selected 候选 ID，继续执行

POST /scenario/s1/gate/{gate_id}/regenerate/{candidate_id}
  → 重新生成某个候选
```

**前端：GatePanel 状态机**

```
GatePanel 状态:
  LOADING → 展示 "Generating 3 candidates..."
  READY   → 展示 CandidateSelector (3 候选卡片)
  SELECTED → 用户已选，[Approve & Continue] 可用
  ERROR   → 某个候选生成失败，可重新生成
```

---

## 四、Layer 3 — 审批 Gate 详细设计

### 4.1 Gate 数据流

```
                Gate 1                           Gate 2-3                   Gate 4
                  │                                 │                         │
生成 3 候选 ←── scripts ×3            keyframe ×3/shot      clip ×3/shot
                  │                    AI 评分/推荐 ★          AI 评分/推荐 ★
                  ▼                                 │                         │
用户选 1-2 个 ──→ 若选 2:             用户审批首选版本 ──→ 生成首选版本 ──→ 双版本对比
                  │  下游 fork ×2           │               完整视频           │
                  ▼                         │                    │            │
             继续执行 ────────────→ Gate 暂停 ────→ Gate 暂停 ──→ 选最终版本  │
                                                                              │
                                                                     [Publish]
```

### 4.2 Gate 后端实现要点

**候选生成器（`src/pipeline/candidate_generator.py`）：**

```python
CANDIDATE_VARIANTS = [
    {"variant": "standard",    "temperature": 0.7},
    {"variant": "creative",    "temperature": 0.9},
    {"variant": "conservative","temperature": 0.5},
]

async def generate_candidates(step_name, params, count=3):
    candidates = []
    for i in range(count):
        variant = CANDIDATE_VARIANTS[i]
        result = await run_step_with_variant(step_name, params, variant)
        score = await score_candidate(step_name, result)
        candidates.append({
            "id": f"{step_name}_c{i}",
            "variant": variant["variant"],
            "data": result,
            "score": score,
            "recommended": (i == 0),  # will be updated after scoring
        })
    # Re-sort by score, mark top as recommended
    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates[0]["recommended"] = True
    return candidates
```

**StepRunner 增强（`src/pipeline/step_runner.py`）：**

在 `_execute_step` 中添加 Gate 检测：
```python
GATE_STEPS = {"scripts", "storyboards", "seedance_clips", "assemble_final"}

async def _execute_step(self, state, step_name, force=False):
    # ... existing logic ...
    result = await pipeline.run_step(step_name, state)
    
    if step_name in GATE_STEPS and state.get("mode") == "expert":
        # Don't auto-advance — pause at gate
        state["current_step"] = step_name  # stay at this step
        state["gate_status"] = "awaiting_approval"
    
    # ... save state ...
```

### 4.3 候选评分器（`src/pipeline/candidate_scorer.py`）

```python
async def score_candidate(step_name: str, candidate_data: dict) -> dict:
    """Score a candidate using LLM-based evaluation."""
    if step_name == "scripts":
        return await _score_script(candidate_data)
    elif step_name in ("storyboards", "keyframe_images"):
        return await _score_visual(candidate_data)
    elif step_name == "seedance_clips":
        return await _score_clip(candidate_data)
    return {"overall": 0.8, "details": "default"}

async def _score_script(script: dict) -> dict:
    """Score: text quality(30%) + strategy fit(25%) + USP coverage(20%) 
       + platform fit(15%) + brand tone(10%)"""
    # Use LLM to evaluate, or use deterministic heuristics
    ...
```

---

## 五、文件级改动清单

### 新建文件（7 个）

| 文件 | 职责 | 层 |
|------|------|----|
| `web/src/components/SceneTabs.tsx` | 3 场景 tab 切换 | 交互 |
| `web/src/components/SceneForm.tsx` | 每场景独立表单 | 交互 |
| `web/src/components/StageProgress.tsx` | Smart Create 3 阶段进度 | 交互 |
| `web/src/components/GatePanel.tsx` | Gate 审批通用框架 | 交互 |
| `web/src/components/CandidateSelector.tsx` | 3 候选对比选择 | 交互 |
| `src/pipeline/gate_manager.py` | Gate 状态、候选生成、审批记录 | 模式 |
| `src/pipeline/candidate_scorer.py` | AI 候选评分 | 模式 |

### 修改文件（6 个）

| 文件 | 改动 | 层 |
|------|------|----|
| `web/src/app/page.tsx` | 重构为 4 阶段状态机，集成新组件 | 交互 |
| `web/src/components/StepByStepView.tsx` | 嵌入 GatePanel 暂停点 | 交互 |
| `web/src/components/OneShotResultView.tsx` | Gate 4 增加双版本对比 | 交互 |
| `src/api.py` | 新增候选生成、Gate 审批端点 | 模式 |
| `src/pipeline/step_runner.py` | Gate 暂停逻辑 + 候选生成调用 | 模式 |
| `src/skills/script_writer.py` | 增加 variant 参数，支持多温度生成 | 引擎 |

### 不动文件（其余全部）

- 所有其他 skills
- Pipeline 核心（S1ProductDirectPipeline, S3InfluencerRemixPipeline）
- StateManager, storage
- 资产 API, translate, 诊断脚本
- Nav, DurationSlider, QualityDashboard（移位不重写）

---

## 六、执行顺序 —— 4 个 Sprint

### Sprint 1：交互层重构（3-4h）

```
Agent A: SceneTabs + SceneForm (新组件)
  → 输入: 现有 SceneSelector 代码
  → 输出: 3 场景 tab + 独立表单
  → 自证: 3 个场景的表单正确渲染，切换 tab 表单切换

Agent B: page.tsx 重构为 4 阶段
  → 输入: 现有 page.tsx
  → 输出: Step0(首页) / Step1(推荐) / Step2(生成) / Step3(结果)
  → 自证: 4 阶段可切换，现有 start 逻辑不破坏

Agent C: AI 推荐面板 + DurationSlider 移位
  → 输入: 现有 DurationSlider + strategy step 输出
  → 输出: Step1 推荐面板（时长/平台/策略摘要）
  → 自证: strategy 执行后推荐正确展示，DurationSlider 联动
```

### Sprint 2：专家工作台模式（4-5h）

```
Agent A: gate_manager.py + candidate_scorer.py (后端)
  → 输入: StepRunner + SkillRegistry
  → 输出: 候选生成 + AI 评分 + Gate 状态存储
  → 自证: 3 候选生成成功，AI 评分合理

Agent B: GatePanel + CandidateSelector (前端)
  → 输入: StepByStepView + 新后端 API
  → 输出: Gate 1-4 审批 UI
  → 自证: Gate 暂停 → 展示候选 → 选择 → 继续执行

Agent C: api.py 新端点 + step_runner Gate 集成
  → 输入: 现有 api.py + step_runner.py
  → 输出: candidates/approve/regenerate 端点
  → 自证: curl 测试所有新端点
```

### Sprint 3：智能快创模式（2-3h）

```
Agent A: StageProgress (前端)
  → 输入: PipelineMonitor 参考
  → 输出: 3 阶段进度条（文案/画面/导出）
  → 自证: 阶段随 pipeline 状态正确推进

Agent B: Smart Create 模式路由
  → 输入: page.tsx 模式状态
  → 输出: Smart Create 全自动流程
  → 自证: 输入产品 → 自动执行 → 结果展示
```

### Sprint 4：Gate 4 终审 + 发布（2h）

```
Agent A: CompareView 双版本对比
  → 输入: OneShotResultView + 双脚本结果
  → 输出: 并排对比面板
  → 自证: 两个视频可同时播放，可单选最终版

Agent B: script_writer variant 参数
  → 输入: 现有 script_writer
  → 输出: 支持 variant + temperature 参数
  → 自证: standard/creative/conservative 三种输出有明显差异
```

---

## 七、验收标准（每个 Sprint 结束检查）

| Sprint | 验收条件 |
|--------|---------|
| 1 | 首页展示 3 场景 tab，每个场景独立表单，点击 Continue 进入推荐步骤，AI 推荐时长正确 |
| 2 | Gate 1 展示 3 个候选脚本，AI 推荐 ★ 标示，可选 1-2 个，选后继续执行到 Gate 2 暂停 |
| 3 | 切换到 Smart Create，输入产品 → 一键生成 → 3 阶段进度条 → 拿到结果 |
| 4 | Gate 4 双版本并排对比，可选最终版，一键下载/重新生成 |

### 关键不破坏验证

- `POST /scenario/s1` auto 模式仍然工作（向后兼容）
- `POST /scenario/s1/start` step_by_step 模式仍然工作
- 现有测试用例的调用路径不受影响
- 资产 API、诊断脚本、docker-compose 不变

---

## 八、总工时估算

| Sprint | 工时 | 并行轨数 |
|--------|------|---------|
| 1 — 交互层 | 3-4h | 3 轨 |
| 2 — 专家工作台 | 4-5h | 3 轨 |
| 3 — 智能快创 | 2-3h | 2 轨 |
| 4 — 终审 + 发布 | 2h | 2 轨 |
| **总计** | **11-14h** | 约 2 个完整工作日 |

---

*计划制定：2026-04-28 深夜 | 下一次修订：Sprint 1 完成后*
