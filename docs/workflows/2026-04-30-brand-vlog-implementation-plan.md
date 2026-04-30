# 品牌VLOG 场景 — 可执行实施计划 (v2 · 深度审查修订版)

**制定**: 2026-04-30 · **修订**: 2026-04-30  
**来源**: 业务原型 HTML × S1-S4 架构 × 代码级验证  
**预计**: 5h · **原则**: 新增独立场景, 不修改现有代码, 自动模式先行

---

## 零、审查发现的 5 个问题及修正

| # | 问题 | 原计划 | 修正 |
|---|------|--------|------|
| 1 | S5 管道与 StepRunner 兼容 | 假设自动适配 | **S5 用独立 `run()` 方法, 不走 StepRunner**, S5 不参与现有 STEP_ORDER。自动模式先行, 后续再考虑 step-by-step |
| 2 | vlog_strategy 输出 → video_prompts 输入之间缺少脚本适配层 | 未定义 | 新增 `_vlog_shots_to_scripts()` 适配器: 将分镜 JSON → `[{"segments": [{segment_type, visual_description, voiceover, start_time, end_time}]}]` 格式 |
| 3 | 时长范围 → 整数映射 | 未定义 | "5-15"→15 / "15-30"→30 / "30-45"→45 / "45-60"→60 / "60-90"→90 |
| 4 | 模特数据需前后端共用 | 未定义 | Mock 数据从 `demo-data.ts` 提取为 Python dict, 硬编码在 `s5_brand_vlog_pipeline.py` 中用于 LLM prompt 上下文 |
| 5 | TTS 语音文本来源 | 未明确 | vlog_strategy 产出的分镜中 voiceover 字段拼接 → 传入 `_step_tts_audio` |

---

## 一、修正后的架构

```
┌── 输入层 (前端 SceneForm VLOG 区) ──────────────────────────┐
│ 品牌选择 · 产品SKU+六视图 · 场景 · 模特多选 · 故事 · 时长   │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /scenario/s5
┌──────────────────────────▼──────────────────────────────────┐
│  S5 管道 (auto mode, 不走 StepRunner)                        │
│                                                              │
│  ① vlog_strategy   LLM 生成分镜 JSON                        │
│       ↓                                                      │
│  ② _vlog_shots_to_scripts()   分镜 → scripts 格式适配       │
│       ↓                                                      │
│  ③ video_prompts   叙事镜头 prompt (复用 narrative_shot)     │
│       ↓                                                      │
│  ④ seedance_clips  Happy Horse 视频片段 (复用, 15s/clip)    │
│       ↓                                                      │
│  ⑤ tts_audio       CosyVoice TTS (复用)                     │
│       ↓                                                      │
│  ⑥ assemble_final  Remotion 拼接 + 字幕 (复用)              │
│       ↓                                                      │
│  ⑦ audit           质量评分 (复用)                           │
└──────────────────────────────────────────────────────────────┘
```

**关键**: 步骤②是新增的适配层，确保 vlog_strategy 的 JSON 输出能被现有 `_step_video_prompts` 消费。

---

## 二、数据流契约（每一步的输入/输出）

```
步骤① vlog_strategy
  输入: product + views[] + models[] + scene + story + duration
  输出: List[{
    "shot_index": 0,
    "shot_type": "close-up",
    "duration_seconds": 4.0,
    "visual_description": "手持M5正面特写，客厅自然光...",
    "voiceover": "每天早晨，我只需要三秒钟...",
    "product_angle": "主视图",
    "model_in_shot": "Ava"
  }]

步骤② _vlog_shots_to_scripts
  输入: shots[] (from step ①)
  输出: [{
    "id": "vlog-script-001",
    "segments": [{
      "segment_type": "hook",
      "start_time": 0.0,
      "end_time": 4.0,
      "visual_description": "...",
      "voiceover": "..."
    }, ...]
  }]

步骤③ video_prompts (复用, 无需修改)
  输入: scripts[] (from step ②) + product_name
  输出: List[{"script_id":..., "segment_prompt":..., "shot_type":..., "duration_seconds":...}]

步骤④-⑦ 完全复用现有 S1 逻辑, 无需修改
```

---

## 三、文件清单 & 执行顺序

### Phase 1: 类型 + 数据 + 端点 (40min)

| # | 文件 | 操作 | 内容 |
|---|------|------|------|
| 1.1 | `web/src/components/types.ts` | 修改 | + `brand_vlog` 常量 · + `ProductViewAngle` `ProductSku` `ModelProfile` 接口 |
| 1.2 | `web/src/i18n/translations.ts` | 修改 | + 15 个 zh key + 15 个 en key |
| 1.3 | `web/src/demo-data.ts` | 修改 | + `VLOG_BRANDS` (momcozy/cozycare/lullabloom, 各含 SKU+六视图) · + `VLOG_MODELS` (6 个角色) |
| 1.4 | `web/src/components/api.ts` | 修改 | + `runS5BrandVlog()` 函数 |
| 1.5 | `src/api.py` | 修改 | + `POST /scenario/s5` 端点 (20 行) |

### Phase 2: 后端管道 (1.5h)

| # | 文件 | 操作 | 内容 |
|---|------|------|------|
| 2.1 | `src/pipeline/s5_brand_vlog_pipeline.py` | **新建** | `S5BrandVlogPipeline` 类 |

```python
class S5BrandVlogPipeline:
    """品牌VLOG — 自动模式管道 (不走 StepRunner)"""

    async def run(self, brand_id, product_sku, scene_id,
                  selected_models, story_description, video_duration) -> dict:
        """
        执行全部 7 步, 返回结果 dict (兼容前端 OneShotResultView 的消费格式)。
        """
        reg = SkillRegistry()
        errors = []
        product_name = product_sku.get("name", "Product")

        # ① vlog_strategy: LLM 生成分镜
        shots = await self._step_vlog_strategy(
            product_sku, selected_models, scene_id,
            story_description, video_duration, errors,
        )

        # ② 适配: 分镜 → scripts 格式
        scripts = self._vlog_shots_to_scripts(shots)

        # ③ video_prompts (复用)
        video_prompts = await self._step_video_prompts(
            reg, scripts, product_name, errors,
        )

        # ④ seedance_clips (复用)
        seedance_out = await self._step_seedance_clips(
            reg, video_prompts, product_name, "vlog", errors, video_duration,
        )

        # ⑤ tts_audio (复用)
        audio_paths, lyrics_paths = await self._step_tts_audio(
            reg, scripts, errors,
        )

        # ⑥ assemble (复用)
        clip_paths = seedance_out.get("clip_paths", [])
        final_video, render_json = await self._step_assemble_final(
            reg, [], scripts, audio_paths, lyrics_paths,
            clip_paths, {}, "vlog", errors,
        )

        # ⑦ audit (复用)
        audit_report = await self._step_audit(
            reg, final_video, audio_paths, [], clip_paths, errors,
        )

        return {
            "success": len(errors) == 0,
            "scenario": "brand_vlog",
            "scripts": scripts,
            "video_prompts": video_prompts,
            "clip_paths": clip_paths,
            "final_video_path": final_video,
            "render_json_path": render_json,
            "audio_paths": audio_paths,
            "audit_report": audit_report,
            "errors": errors,
        }
```

**关键方法**:

```python
async def _step_vlog_strategy(self, product_sku, models, scene_id,
                               story, duration, errors) -> list[dict]:
    """LLM 生成 VLOG 分镜脚本。

    Prompt 模板 (通过 llm_client 调用 DeepSeek-V4-Pro):
    """
    from src.tools.llm_client import llm

    scene_map = { ... }  # 6 个场景 name/desc
    views_text = "\n".join(
        f"- {v['label']}({v['title']}): {v['usage_note']}"
        for v in product_sku.get("views", [])
    )
    models_text = "\n".join(
        f"- {m['name']}({m['role']}): {m['description']}"
        for m in models
    )

    system = "你是母婴品牌的创意导演, 擅长将产品素材转化为 VLOG 叙事分镜。输出严格的 JSON 数组。"
    user = f"""请生成一个 {duration} 秒的 VLOG 视频分镜脚本。

产品: {product_sku.get('name')}
产品标签: {', '.join(product_sku.get('tags', []))}
可用产品角度:
{views_text}

拍摄场景: {scene_map.get(scene_id, {}).get('name', scene_id)}
出镜人物:
{models_text}

故事方向: {story or '突出产品核心卖点, 以真实家庭互动串联完整情绪起承转合'}

请输出 JSON 数组, 每个镜头包含:
- "shot_type": close-up | mid-shot | over-shoulder | static beauty
- "duration_seconds": 秒数 (总时长为 {duration}s)
- "visual_description": 画面描述 (引用产品角度名, 描述人物动作和情绪)
- "voiceover": 旁白文案 (自然口语, <30字/镜头)
- "product_angle": 使用的产品角度 label
- "model_in_shot": 出镜人物名 (可为空)

叙事节奏: 前 20% 建立产品认知 → 中 60% 人物使用场景 → 后 20% 品牌收尾CTA

只输出 JSON 数组, 不要任何解释。"""

    result = await llm.invoke_json(system, user)
    # result 预期为 list[dict]
    if not isinstance(result, list):
        errors.append("vlog_strategy: LLM output not a list")
        return self._build_fallback_shots(product_sku, duration)
    return result


def _vlog_shots_to_scripts(self, shots: list[dict]) -> list[dict]:
    """适配: LLM 分镜 → scripts 格式 (兼容 video_prompts 步骤)"""
    if not shots:
        return []
    segments = []
    current_time = 0.0
    for i, shot in enumerate(shots):
        dur = float(shot.get("duration_seconds", 5))
        segments.append({
            "segment_type": "hook" if i == 0 else ("cta" if i == len(shots)-1 else "body"),
            "start_time": current_time,
            "end_time": current_time + dur,
            "visual_description": shot.get("visual_description", ""),
            "voiceover": shot.get("voiceover", ""),
            "text_overlay": "",
        })
        current_time += dur
    return [{
        "id": "vlog-script-001",
        "brief_id": "VLOG-001",
        "platform": "tiktok",
        "language": "en",
        "total_duration": current_time,
        "segments": segments,
    }]


def _build_fallback_shots(self, product_sku, duration) -> list[dict]:
    """LLM 调用失败时的兜底分镜"""
    name = product_sku.get("name", "Product")
    return [
        {"shot_type": "close-up", "duration_seconds": duration*0.2,
         "visual_description": f"{name} 正面特写, 自然光", "voiceover": "", "product_angle": "主视图", "model_in_shot": ""},
        {"shot_type": "mid-shot", "duration_seconds": duration*0.6,
         "visual_description": f"{name} 日常使用场景", "voiceover": "", "product_angle": "45度视图", "model_in_shot": ""},
        {"shot_type": "static beauty", "duration_seconds": duration*0.2,
         "visual_description": f"{name} 品牌收尾, 干净背景", "voiceover": "", "product_angle": "包装视图", "model_in_shot": ""},
    ]
```

### Phase 3: 前端组件 (1.5h)

| # | 文件 | 操作 | 内容 |
|---|------|------|------|
| 3.1 | `SceneTabs.tsx` | 修改 | `SCENE_IDS` + `"brand_vlog"`, `SCENE_ICON_MAP` + `Camera` |
| 3.2 | `SceneForm.tsx` | 修改 | 新增 `scene === "brand_vlog"` 条件渲染块 |
| 3.3 | `VlogSixView.tsx` | **新建** | 六视图展示组件 |
| 3.4 | `VlogModelSelector.tsx` | **新建** | 模特多选组件 |

#### 3.2 SceneForm.tsx — VLOG 区域结构

```tsx
{/* 品牌VLOG 场景专属表单 */}
{scene === "brand_vlog" && (
  <div className="space-y-4">
    {/* 基础配置: 品牌 + 产品SKU (grid-2) */}
    {/* 场景选择: 6 chips (grid-3/6) */}
    {/* 产品六视图: VlogSixView (自动展示, grid-3) */}
    {/* 模特选择: VlogModelSelector (grid-4, 多选) */}
    {/* 故事描述: textarea (300字限制 + 计数器) */}
    {/* 视频参数: 5-pill duration toggle */}
    {/* 提交按钮 */}
  </div>
)}
```

新增 state 变量 (追加到 SceneForm 现有 state):
```tsx
const [vlogBrand, setVlogBrand] = useState("momcozy");
const [vlogProductId, setVlogProductId] = useState("m5");
const [vlogScene, setVlogScene] = useState("living-room");
const [vlogModels, setVlogModels] = useState<string[]>([]);
const [vlogStory, setVlogStory] = useState("");
const [vlogDuration, setVlogDuration] = useState("15-30");
```

提交时构造 payload:
```tsx
const handleVlogSubmit = () => {
  const brand = VLOG_BRANDS.find(b => b.id === vlogBrand);
  const product = brand?.products.find(p => p.id === vlogProductId);
  const models = VLOG_MODELS.filter(m => vlogModels.includes(m.id));
  const durationMap = {"5-15":15, "15-30":30, "30-45":45, "45-60":60, "60-90":90};

  onSubmit({
    content_scenario: "brand_vlog",
    brand_id: vlogBrand,
    product_sku: product,
    scene_id: vlogScene,
    selected_models: models,
    story_description: vlogStory,
    video_duration: durationMap[vlogDuration] || 30,
    mode: "auto",
  });
};
```

#### 3.3 VlogSixView.tsx

```tsx
// Props: views: ProductViewAngle[], brandAccent?: string
// Render: grid grid-cols-3 gap-3
// Each card: gradient header (view.color) + label badge + title + usage_note
// Read-only display — no interaction needed
```

#### 3.4 VlogModelSelector.tsx

```tsx
// Props: models: ModelProfile[], selected: string[], onChange: (ids: string[]) => void
// Render: grid grid-cols-4 gap-3
// Each card: gradient portrait + name + role pill + description
// Click toggles selection
// Below grid: selected models list with remove button
```

### Phase 4: 联调验证 (1h)

| # | 测试 | 验证点 |
|---|------|--------|
| 4.1 | `python3 -c "from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline; print('import ok')"` | 模块可导入 |
| 4.2 | `curl -X POST localhost:8001/scenario/s5 -H "X-API-Key: ai_video_demo_2026" -H "Content-Type: application/json" -d '{...}'` | 端点返回 200 + 含 scripts/clip_paths/errors |
| 4.3 | 前端: 选 Momcozy M5 + 客厅 + Ava + 故事 + 15-30s → 点生成 | StageProgress 完成 + 产物 mp4 可播放 + 无 console.error |
| 4.4 | `grep -r "product showcase\|product rotation\|360 rotation" output/pipeline_states/vlog_*.json` | 返回空 (分镜 prompt 不含禁用词) |
| 4.5 | S1/S3 回退测试 | `pytest tests/test_s1_e2e.py tests/test_s3_e2e.py` 0 fail |

---

## 四、改动文件汇总 (修订后)

| 文件 | 操作 | 净增行数 |
|------|------|---------|
| `web/src/components/types.ts` | 修改 | +55 |
| `web/src/i18n/translations.ts` | 修改 | +30 |
| `web/src/demo-data.ts` | 修改 | +90 |
| `web/src/components/api.ts` | 修改 | +15 |
| `web/src/components/SceneTabs.tsx` | 修改 | +3 |
| `web/src/components/SceneForm.tsx` | 修改 | +100 |
| `web/src/components/VlogSixView.tsx` | **新建** | +50 |
| `web/src/components/VlogModelSelector.tsx` | **新建** | +70 |
| `src/pipeline/s5_brand_vlog_pipeline.py` | **新建** | +220 |
| `src/api.py` | 修改 | +20 |

**合计**: 10 文件 (3 新建 + 7 修改), ~650 行净增。

---

## 五、执行顺序

```
Phase 1 (40min): 1.1→1.2→1.3→1.4→1.5  类型+数据+端点
Phase 2 (1.5h): 2.1                      后端管道 (全部在一个文件中)
Phase 3 (1.5h): 3.1→3.3→3.4→3.2        前端 (先建子组件, 再集成到 SceneForm)
Phase 4 (1h):   4.1→4.2→4.3→4.4→4.5    联调+回退
```
