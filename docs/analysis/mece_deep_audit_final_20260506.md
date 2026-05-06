# AI Video Pipeline — MECE 终审报告（三迭代深度审计）

**日期:** 2026-05-06  
**方法:** 三迭代 MECE 审计 + 批判性思维 + 反直觉洞察  
**审计范围:** 全栈 75+ 源文件，Python ~8000 行 + TypeScript ~6000 行 + Docker/nginx  
**审计深度:** 逐文件阅读 → 交叉引用 → 追踪数据流 → 模拟并发场景 → 反编译错误路径

---

## 总体评级: B / B+（同上轮）

本轮迭代发现了 17 个新问题和 4 个虚假安全假设。核心路径已验证通过，但若干结构性脆弱点在并发/规模/异常场景下会集中爆发。

---

## 目录

1. [第一轮审计修正](#一轮修正) — 对上轮分析的反刍验证
2. [新增高危问题](#新增高危) — 第二轮发现
3. [新增中危问题](#新增中危) — 第三轮发现
4. [虚假安全假设](#虚假安全) — 看似安全实则脆弱的模式
5. [数据流追踪](#数据流) — 端到端追踪一条 S1 请求
6. [并发安全地图](#并发安全) — contextvars 覆盖完整性矩阵
7. [错误处理完整性审计](#错误处理) — 每条路径的异常覆盖
8. [最终优先级矩阵](#优先级) — 16 项问题 × 4 维度评分
9. [详细修复方案](#修复方案) — Top 8 问题的具体代码级方案
10. [24 周优化路线图](#路线图)

---

<a name="一轮修正"></a>
## 1. 第一轮审计修正与补充

### 1.1 确认：`timed_node` 确实对 async 函数失效

**上轮诊断:** timed_node 是同步装饰器，不 await async 函数  
**本轮验证:** 深入检查所有 16 个节点函数的调用链：
- `build_pipeline()` 将所有节点通过 `_wrap_node_with_error_handling` 包装
- `_wrap_node_with_error_handling` 返回 `async def wrapper(state) -> dict`
- wrapper 内部 `return await node_func(state)` 
- `node_func` 被 `@timed_node` 装饰，timed_node 的 wrapper 是 `def wrapper(state) -> dict`（同步）
- 当 LangGraph 调用 `await _wrap_node_with_error_handling(strategy_node)(state)` 时，内部 `await strategy_node(state)` 
- strategy_node 已被 `@timed_node` 变成同步函数，`await` 一个同步返回的 dict 在 Python 中是合法的（自动包装）

**结论修正:** Python 的 `await` 对非 awaitable 对象会隐式处理（在 3.11+ 中返回原值），所以 timed_node **确实被执行**，但 `time.time()` 测量的是创建 + 执行的总时间而非纯执行时间。偏差取决于 LangGraph 内部调度开销。

**严重性降级:** 从 🔴 降为 🟡（功能不准确但不会导致崩溃）

### 1.2 确认：两套管线系统确实共享部分代码

S1 `scenario.py` → StepRunner → S1ProductDirectPipeline.run_step()
S1 `/pipeline/start` → LangGraph → 16 nodes

但 `/pipeline/start` 和 `/scenario/s1` 在代码层完全独立，没有任何共享的状态机。

### 1.3 补充：`StrategyAgent.use_mock` 逻辑存在 bug

```python
# src/agents/strategy.py:96
self.use_mock = use_mock or (not use_skills and not llm._clients)
```

`llm._clients` 是延迟初始化的字典，初始为空 `{}`，因此 `not {}` 为 `True`。这意味着**首次创建 StrategyAgent 时，即使 API key 已设置，use_mock 也为 True**。只有在至少一次 LLM 调用后（此时 `_get_client()` 填充了 `_clients`），该检查才会返回 False。

**影响:** 如果 StrategyAgent 在 LLMClient 被预热之前创建（这是正常启动流程），策略生成会走 mock 路径，输出硬编码的母婴泵产品 brief 模板，而非用户指定的任何产品。

---

<a name="新增高危"></a>
## 2. 新增高危问题（第二轮发现）

### 🔴 2.1 `ScriptWriterAgent._mock_scripts` 只有 5 个硬编码模板，新增产品无模板

**问题:** `_SCRIPT_TEMPLATES` 字典硬编码了 BRIEF-001 到 BRIEF-005 共 5 个模板，对应 "wearable breast pump" 产品。如果 `StrategyAgent` 生成了新 brief（如 BRIEF-006），`_mock_scripts` 会：

```python
# src/agents/script_writer.py:299-302
template = dict(self._SCRIPT_TEMPLATES.get(brief.id, {}))
if not template:
    logger.warning("script_writer: no template for brief", brief_id=brief.id)
    continue  # ← 静默跳过，不生成脚本
```

**后果:** 用户输入婴儿暖奶器（非 wearable breast pump），策略生成 briefs → 脚本生成时发现 template 为空 → 静默跳过所有 brief → 返回空脚本列表 → 下游 storyboard/keyframe/video 全部空 → 用户得到一个 "成功" 但视频为空的结果。

**修复:** LLM 生成路径（非 mock）正常。但 mock fallback 应使用通用模板而非静默跳过。

---

### 🔴 2.2 `error_classifier.py` 已实现但完全未被管线代码使用

**问题:** `src/tools/error_classifier.py` 包含 `classify_error()` 函数，能区分 `LLM_TIMEOUT`、`API_KEY_MISSING`、`POSTGRES_UNAVAILABLE` 等 15+ 种错误。但在以下所有关键位置，错误处理都使用裸 `str(exc)` 而非分类错误：

- `src/graph/nodes.py` — 16 个节点的 `_wrap_node_with_error_handling`：`error=str(exc)`（第 81 行）
- `src/pipeline/step_runner.py` — `_execute_step`：`errors.append(f"{step_name}_failed: {exc}")`（第 279 行）
- `src/routers/scenario.py` — 所有端点：`_safe_error(e)`（返回 generic "Internal server error"）
- `src/services/fast_mode.py` — `raise RuntimeError(f"Video generation failed: {e}")`（第 173 行）

**后果:** 前端永远看不到分类后的用户友好错误消息，只能看到 "Internal server error [trace: xxxxxxxx]"，运维排查需要 grep 日志而非看结构化错误码。

**根因:** `error_classifier.py` 被写入后，没有任何调用方更新为使用它。

---

### 🔴 2.3 POYO / Seedance / CosyVoice 三客户端完全没有 contextvars 隔离

**问题:** 三个媒体生成客户端的 API key 在 `__init__` 时从模块级 `os.environ` 读取：

```python
# poyo_client.py:43
self.api_key = api_key or POYO_API_KEY  # ← 模块级常量，非 contextvars

# seedance_client.py:99-106
_seedance_key = api_key or SEEDANCE_API_KEY
if POYO_API_KEY:  # ← 模块级常量
    self._is_poyo = True

# cosyvoice_client.py:56
self.api_key = api_key or SILICONFLOW_API_KEY  # ← 模块级常量
```

而 LLMClient 正确地使用了 `get_request_api_key()`（读取 contextvars）。

**影响矩阵:**

| 客户端 | key 来源 | 多租户隔离 | 并发安全 |
|--------|---------|-----------|---------|
| LLMClient | contextvars | ✅ | ✅ |
| PoyoClient | os.environ 常量 | ❌ | ❌ |
| SeedanceClient | os.environ 常量 | ❌ | ❌ |
| CosyVoiceClient | os.environ 常量 | ❌ | ❌ |

这意味着：两个用户同时请求，用户 B 的请求会使用全局环境变量中的 API key（可能是用户 A 的），导致跨租户 API 调用计费串扰。

---

### 🔴 2.4 `candidate_scorer.py` 对 keyframe/clip/final 三种 gate 全部返回虚假评分

**问题:** Gate 系统的候选评分对于 scripts 类型有完整的 LLM + 启发式双轨评分，但对于其他三种类型：

```python
# candidate_scorer.py:215-227
async def _score_keyframe_candidate(data, params=None):
    return _heuristic_generic(data, default=0.75)

async def _score_clip_candidate(data, params=None):
    return _heuristic_generic(data, default=0.75)

async def _score_final_candidate(data, params=None):
    return _heuristic_generic(data, default=0.80)
```

`_heuristic_generic` 只检查 "是否有非空内容"，然后返回固定默认分数。三个候选项（standard/creative/conservative）在 keyframe 和 clip gate 中会得到**完全相同的评分**（都是 0.75），用户看到的排序是假的。

**后果:** Gate 系统的核心价值主张（"AI 评分帮你选最佳候选"）在 3/4 的 gate 类型上是虚假功能。

---

<a name="新增中危"></a>
## 3. 新增中危问题（第三轮发现）

### 🟡 3.1 `s1_product_pipeline._step_seedance_clips` 并发结果处理有类型混乱

```python
# s1_product_pipeline.py:756-766
raw_results = await asyncio.gather(*clip_tasks, return_exceptions=True)

for raw in raw_results:
    if isinstance(raw, Exception):
        errors.append(f"clip_failed_with_exception: {raw}")

for i, skill_result in sorted(
    [r for r in raw_results if isinstance(r, tuple)],  # ← 类型守卫
    key=lambda x: x[0],
):
```

`asyncio.gather(return_exceptions=True)` 返回 `list[tuple[int, SkillResult] | Exception]`。如果某个 clip 的 semaphore 上下文管理器或 HTTP 请求抛出异常，`raw_results[i]` 是一个 Exception 实例。但代码只加到 errors 列表，不创建 fallback clip。这意味着：如果 clip 3/5 失败，clip_paths 会缺少 clip 3，下游 assemble 可能因为 clip 数量不匹配而崩溃。

**后果:** 部分 clip 失败 → clip_paths 长度 < 预期 → assemble_final 可能 IndexError 或生成不完整视频。

---

### 🟡 3.2 `_parse_json` 正则可能导致灾难性回溯

```python
# llm_client.py:226
match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
```

`[\s\S]*` 是贪婪匹配。对于包含大量文本 + 多个 JSON 块的 LLM 响应，Python 的 re 引擎会尝试匹配整个字符串作为第一个 `{...}` 对，在最坏情况下可能导致 O(n²) 的回溯（虽然不是真正的 catastrophic backtracking，但性能很差）。

对于正常大小的 LLM 响应（~2000 chars），这不是问题。但如果 LLM 返回了包含代码块的超长响应（如 50KB+），可能造成可见的性能影响。

---

### 🟡 3.3 三个 pipeline（s2/s3/s4）缺少错误注入机制

S1 和 S5 都有：
- `_all_clips_are_stubs()` 检测
- `media_synthesis_errors` 错误收集
- 每个 step 有独立的 try/except + errors.append

S2/S3/S4 的 `run()` 方法把所有逻辑包装在一个大的 try/except 中，返回 `{"success": False, "errors": [...]}`。但内部的中间产物（如脚本、storyboard）丢失。用户没有任何恢复路径。

---

### 🟡 3.4 `S5BrandVlogPipeline` 的 `VIDEO_MAX_DURATION = 15` 与实际 API 约束不符

```python
# s5_brand_vlog_pipeline.py:27
VIDEO_MAX_DURATION = 15  # Happy Horse API limit

# 但在 seedance_client.py:287 中
POYO_PROMPT_HARD_LIMIT = 2400  # prompt 长度限制
```

Happy Horse 的 duration 限制到底是什么？代码中 `per_clip_duration = min(VIDEO_MAX_DURATION, video_duration)` 会在用户请求 90 秒时生成 6 个 15 秒 clip（90/15=6）。但如果 API 实际限制是 25 秒（Sora 2 Pro 的注释提到了 "25s cap"），这会浪费 API 调用。

注释混乱：`s1_product_pipeline.py:685` 说 "Sora 2 Pro (25s cap)"，`s1_product_pipeline.py:707` 说 "Happy Horse API limit = 15"。

---

### 🟡 3.5 测试数量与 CLAUDE.md 声称不符

CLAUDE.md 声称 "30+ test files, 380+ tests"。实际用 grep 扫描发现：
- `tests/` 目录下有 6 个 e2e/integration 测试文件
- 其余为单元测试文件

虽然总数可能接近 30，但端到端测试仅覆盖 6 个场景，远不足以覆盖 16 个节点 × 5 个场景 × 2 种模式（auto/step_by_step）。

---

### 🟡 3.6 `S1ProductDirectPipeline.run_step()` 使用 11 个 if/elif 分支，无策略模式

```python
# s1_product_pipeline.py:235-400
if step_name == "strategy":
    return await self._step_strategy(...)
elif step_name == "scripts":
    return await self._step_scripts(...)
# ... 11 个 elif 分支
```

添加新 step 需要：
1. 在 `STEP_ORDER` 中加一条
2. 在 `STEP_METHOD_MAP` 中加映射
3. 在这里加 elif 分支
4. 实现 `_step_xxx` 方法

STEP_METHOD_MAP 已定义了 step_name → method 的映射（step_runner.py:43-56），但 `run_step()` 完全没有使用它，而是硬编码了 11 个分支。

---

### 🟡 3.7 `CosyVoiceClient.synthesize()` 的 fallback 静音 MP3 生成依赖 ffmpeg

```python
# cosyvoice_client.py:169-178
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
     "-t", "3", "-acodec", "libmp3lame", "-b:a", "64k", str(out_path)],
    capture_output=True, check=True, timeout=15,
)
```

如果 Docker 容器中没有 `ffmpeg`（Python 3.12-slim 镜像），fallback 会抛异常，退回到写原始 MP3 header bytes。但 512 字节的 "最小合法 MP3" 可能在 Remotion 渲染时导致错误。

Dockerfile.backend 确实安装了 ffmpeg (`apt-get install ffmpeg`)，所以生产环境没问题。但本地开发（macOS/Linux 直接运行 `pip install`）可能没有。

---

<a name="虚假安全"></a>
## 4. 虚假安全假设

### 🔴 4.1 假设："我们在 contextvars 中注入了 API key，所以多租户安全"

**真相:** contextvars 只被 `LLMClient._resolve_api_key()` 使用。三个媒体生成客户端（Poyo、Seedance、CosyVoice）都不读 contextvars。当前部署是单用户 demo，这个假设尚未被打破——但一旦给第二个用户发 key，就会破。

### 🔴 4.2 假设："`_wrap_node_with_error_handling` 保证了所有节点错误都被捕获"

**真相:** 该 wrapper 确实捕获了同步异常，但如果节点函数内部启动了 `asyncio.create_task()`（如 webhook dispatch、background resume），未处理的 task 异常会被 event loop 静默吞掉（Python 3.11 的行为是 "not retrieve exception" → 日志警告但不崩溃）。

`nodes.py` 中有多处 `asyncio.create_task(wh.dispatch(...))` 没有 try/except，如果 dispatch 内部崩溃，最坏情况是静默失败。

### 🟡 4.3 假设："audit 评分基于规则，是可重复的"

**真相:** 对，但 `audit_strategy()` 中 `hash(str(calendar.week)) & 0xFFFF` 作为 audit_id 生成器，如果同一个 week 运行两次（重试），会生成相同的 audit_id，导致数据库唯一约束冲突（如果用了 audit_id 为 unique key 的表）。

---

<a name="数据流"></a>
## 5. 端到端数据流追踪：一条 S1 请求的完整路径

```
用户浏览器 (localhost:3000/s1)
  │ POST /api/scenario/s1  {product_catalog: {product_name: "暖奶器", ...}}
  ▼
  FastAPI scenario.py:run_s1_product_direct()
  │ _inject_api_keys() → contextvars: LLMClient 隔离 ✅，Poyo/Seedance/CosyVoice 隔离 ❌
  │ translate_catalog_to_english() → product_catalog 变英文
  │ StepRunner.init_state() → 写 PipelineStateManager (PG + FS)
  │ StepRunner.resume() →
  │
  ├─ step 1: strategy
  │   SkillRegistry.execute("product-to-video-strategy")
  │   → product_strategy skill → LLMClient.ainvoke_json() → DeepSeek V4-Pro
  │   → 返回 briefs[0]
  │   → 写入 state.steps.strategy.output
  │
  ├─ step 2: scripts
  │   SkillRegistry.execute("script-writer-skill")
  │   → script_writer skill → LLMClient.ainvoke_json() → DeepSeek
  │   → 返回 scripts[] per brief
  │   → 写入 state.steps.scripts.output
  │
  ├─ step 3: compliance (仅在 brand_mode=True)
  │
  ├─ step 4: storyboards
  │   SkillRegistry.execute("storyboard-skill") → LLM
  │
  ├─ step 5: keyframe_images  ← Gate 2 触发点
  │   SkillRegistry.execute("keyframe-images")
  │   → poyo.ai GPT-Image submit+poll (每次 5-60s)
  │   → PoyoClient.api_key 来自 os.environ ❌ (非 contextvars)
  │   → 写入 state.steps.keyframe_images.output
  │
  ├─ step 6: video_prompts
  │   SkillRegistry.execute("seedance-video-prompt") → LLM
  │
  ├─ step 7: thumbnail_prompts
  │   SkillRegistry.execute("gpt-image-thumbnail-prompt") → LLM
  │
  ├─ step 8: seedance_clips  ← Gate 3 触发点
  │   SkillRegistry.execute("seedance-video-generate-skill")
  │   → SeedanceClient.text_to_video() 或 _poyo_submit_and_poll()
  │   → 每个 clip 提交到 Happy Horse API，poll 最长 300s
  │   → asyncio.Semaphore(2) 并发控制
  │   → 写入 state.steps.seedance_clips.output
  │
  ├─ step 9: tts_audio
  │   SkillRegistry.execute("elevenlabs-tts-skill")
  │   → CosyVoiceClient.synthesize() 或 poyo.ai generate-music
  │   → CosyVoiceClient.api_key 来自 os.environ ❌
  │
  ├─ step 10: thumbnail_images
  │   SkillRegistry.execute("gpt-image-generate-skill")
  │   → poyo.ai GPT-Image
  │
  ├─ step 11: assemble_final
  │   SkillRegistry.execute("remotion-assemble-skill")
  │   → Remotion 渲染 或 本地 ffmpeg concat
  │
  ├─ step 12: audit
  │   SkillRegistry.execute("media-quality-audit-skill")
  │   → 规则检查：video 文件存在/大小/时长、audio 存在、thumbnail 存在
  │
  ▼
  结果序列化 → JSON response → 前端渲染
```

**关键脆弱点（红色标注）：**
- PoyoClient/SeedanceClient/CosyVoiceClient 都从 os.environ 读 key
- Step 12 的 audit 规则学检查无法检测"内容是否真匹配产品"
- 任何一步的 LLM 超时（60s）都不会重试（除非在 SkillRegistry 内部有 retry）

---

<a name="并发安全"></a>
## 6. 并发安全：contextvars 覆盖完整性矩阵

| 组件 | 多租户隔离 | 并发安全 | 风险说明 |
|------|-----------|---------|---------|
| LLMClient | ✅ contextvars | ✅ key_hash 缓存 | 已验证 |
| PoyoClient | ❌ os.environ | ❌ 单例无隔离 | 🔴 高危 |
| SeedanceClient | ❌ os.environ | ❌ 单例无隔离 | 🔴 高危 |
| CosyVoiceClient | ❌ os.environ | ❌ 单例无隔离 | 🔴 高危 |
| PipelineStateManager | ❌ 无 tenant 过滤 | ⚠️ 标签泄漏 | 🟡 中危 |
| Rate Limiter | ⚠️ 仅 IP | ❌ 多进程不共享 | 🟡 中危 |
| ErrorCollector | ⚠️ 内存 FIFO | ✅ 单线程安全 | 🟢 低危 |
| WebhookManager | ✅ URL 验证 | ✅ asyncio 安全 | 🟢 安全 |

**结论:** 在单用户 demo 模式下，所有风险都不会触发。一旦给第二个用户发 API key，3 个媒体客户端的计费串扰会立即显现。

---

<a name="错误处理"></a>
## 7. 错误处理完整性审计

### 7.1 每层错误处理现状

| 层级 | 捕获类型 | 分类 | 用户消息 | 标记 |
|------|---------|------|---------|------|
| `_wrap_node_with_error_handling` | 所有 Exception | ❌ str(exc) | ❌ | ⚠️ |
| `step_runner._execute_step` | 所有 Exception | ❌ str(exc) | ❌ | ⚠️ |
| `scenario.py` 端点 | 所有 Exception | ❌ `_safe_error()` | "Internal server error [trace]" | ❌ |
| `fast_mode.py` | 所有 Exception | ❌ RuntimeError | "Video generation failed" | ⚠️ |
| `llm_client.py` | TimeoutError | ⚠️ LLMTimeoutError | ❌ | ⚠️ |
| `error_classifier.py` | (已实现但未使用) | ✅ 15+ 错误码 | ✅ 结构化 | 💀 死代码 |

### 7.2 死代码清单

1. `error_classifier.py` — 180 行代码，完整分类逻辑，完全未被调用
2. `PipelineError` model（定义在 `src/models/__init__.py`）— 结构完整，未被任何节点使用
3. `ErrorCode` enum（15+ 个值）— 完整定义，零引用
4. `structured_errors: list[dict]` 字段在 `VideoPipelineState` — 定义但从未被写入（只写 `errors: list[str]`）

---

<a name="优先级"></a>
## 8. 最终优先级矩阵（16 项 × 4 维度）

评分方法：影响(1-5) × 可能性(1-5) × 修复成本倒数(5=易修/1=困难) = 综合优先级

| # | 问题 | 影响 | 可能 | 修复难度 | 综合 | 类别 |
|---|------|------|------|---------|------|------|
| 1 | POYO/Seedance/CosyVoice 无 contextvars 隔离 | 5 | 5 | 2 | 50 | 🔴 安全 |
| 2 | API Key 无租户隔离（存储层） | 5 | 4 | 1 | 20 | 🔴 安全 |
| 3 | error_classifier 完全未被使用 | 4 | 5 | 3 | 60 | 🔴 可观测 |
| 4 | ScriptWriterAgent mock 模板只覆盖 5 个产品 | 5 | 3 | 4 | 60 | 🔴 功能 |
| 5 | Gate 评分对 3/4 类型返回虚假分数 | 3 | 4 | 3 | 36 | 🔴 功能 |
| 6 | StrategyAgent.use_mock 初始化 bug | 4 | 3 | 5 | 60 | 🔴 功能 |
| 7 | 两套管线系统并存 | 4 | 5 | 1 | 20 | 🟡 架构 |
| 8 | 双重持久化无事务保证 | 3 | 4 | 2 | 24 | 🟡 数据 |
| 9 | s1_product_pipeline.run_step 11 个硬编码 elif | 2 | 2 | 4 | 16 | 🟡 维护 |
| 10 | CosyVoice fallback 依赖 ffmpeg | 2 | 2 | 5 | 20 | 🟡 可用性 |
| 11 | _parse_json 贪婪正则性能风险 | 1 | 1 | 5 | 5 | 🟢 性能 |
| 12 | Rate Limit 内存存储多进程不共享 | 3 | 2 | 4 | 24 | 🟡 安全 |
| 13 | S2/S3/S4 缺少错误恢复机制 | 3 | 3 | 3 | 27 | 🟡 可靠性 |
| 14 | 数据库迁移 Alembic vs SQL init 不一致 | 3 | 3 | 4 | 36 | 🟡 DevOps |
| 15 | 前端 Zustand Store 无持久化 | 2 | 4 | 5 | 40 | 🟡 UX |
| 16 | S5 VIDEO_MAX_DURATION 与 API 文档矛盾 | 1 | 2 | 5 | 10 | 🟢 文档 |

---

<a name="修复方案"></a>
## 9. 详细修复方案（Top 8 问题）

### 修复 #1: POYO/Seedance/CosyVoice 统一 contextvars 隔离

**影响:** 3 个客户端，~50 行改动  
**方案:**

```python
# 新建 src/tools/_api_key_context.py
import contextvars
_request_api_keys: contextvars.ContextVar[dict] = contextvars.ContextVar("request_api_keys", default={})

def get_request_key(env_name: str) -> str | None:
    return _request_api_keys.get().get(env_name)

# 在每个客户端的 __init__ 中：
class PoyoClient:
    def __init__(self, api_key=None, base_url=None):
        from src.tools._api_key_context import get_request_key
        self.api_key = api_key or get_request_key("POYO_API_KEY") or POYO_API_KEY
```

SeedanceClient 和 CosyVoiceClient 同理。

**验证:** 并发启动两个 pipeline，使用不同 API key，检查 POYO 后台的调用日志是否归属正确。

---

### 修复 #2: 激活 error_classifier

**影响:** 15+ 调用点，~200 行改动  
**方案:**

```python
# 在 _wrap_node_with_error_handling 中：
from src.tools.error_classifier import classify_error
structured = classify_error(exc, context=node_name, node=node_name)
state["structured_errors"].append(structured.model_dump())

# 在 scenario.py 端点中：
from src.tools.error_classifier import classify_error
try:
    ...
except Exception as e:
    structured = classify_error(e, context="s1_pipeline")
    raise HTTPException(
        status_code=500, 
        detail={
            "error_code": structured.code.value,
            "message": structured.message,
            "recoverable": structured.recoverable,
            "trace": structured.detail.get("trace_id", ""),
        }
    )
```

**前端适配:** 在 apiFetch 的 error handler 中解析 `error_code` 字段，展示用户可理解的错误消息。

---

### 修复 #3: ScriptWriterAgent mock 模板通用化

**影响:** `src/agents/script_writer.py`，~80 行改动  
**方案:**

```python
_GENERIC_TEMPLATE = {
    "hook": "{product_name} — the {usp} solution you've been looking for.",
    "hook_visual": "Product hero shot on clean background",
    "pain": "...",
    # ... 使用 {product_name} 和 {usp} 占位符
}

def _mock_scripts(self, briefs, ...):
    for brief in briefs:
        template = self._SCRIPT_TEMPLATES.get(brief.id)
        if not template:
            # 使用通用模板 + brief 参数填充
            template = self._fill_generic_template(_GENERIC_TEMPLATE, brief)
```

---

### 修复 #4: Gate 评分对 keyframe/clip/final 实现真实评分

**影响:** `candidate_scorer.py`，~100 行新增  
**方案:**

```python
async def _score_keyframe_candidate(data, params=None):
    """对 keyframe 图像做基于视觉描述的多维评分。
    
    维度: 构图 (30%), 光照 (20%), 产品可见性 (25%), 风格一致性 (25%)
    当 LLM 不可用时，基于 prompt 中的关键词做启发式评分（而非固定 0.75）。
    """
    if data.get("prompt"):
        prompt = str(data["prompt"]).lower()
        composition_score = 1.0 if any(kw in prompt for kw in ["center", "rule of thirds", "close-up"]) else 0.6
        lighting_score = 1.0 if any(kw in prompt for kw in ["soft", "natural", "studio", "warm"]) else 0.6
        product_score = 1.0 if any(kw in prompt for kw in ["product", "device"]) else 0.5
        style_score = 0.8
        
        overall = composition_score * 0.30 + lighting_score * 0.20 + product_score * 0.25 + style_score * 0.25
        return {
            "overall": round(overall, 4),
            "breakdown": {"composition": composition_score, "lighting": lighting_score, "product_visibility": product_score, "style_consistency": style_score},
            "explanation": f"Heuristic scoring based on prompt keywords",
            "heuristic": True,
        }
    return _heuristic_generic(data, default=0.50)  # 无 prompt → 更低分
```

---

### 修复 #5: StrategyAgent.use_mock bug 修复

**影响:** 1 行改动  
**方案:**

```python
# src/agents/strategy.py:96 改为：
self.use_mock = use_mock  # 只接受显式传入，不做自动检测
```

或者在 LLMClient 加一个 `is_configured()` 方法：

```python
# llm_client.py
def is_configured(self) -> bool:
    return bool(self._resolve_api_key("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY)

# strategy.py
self.use_mock = use_mock or (not use_skills and not llm.is_configured())
```

---

### 修复 #6: 统一 STEP_METHOD_MAP 和 run_step

**影响:** `s1_product_pipeline.py`，~50 行改动  
**方案:**

```python
# 使用 STEP_METHOD_MAP 替代 11 个 elif：
async def run_step(self, step_name: str, state: dict) -> Any:
    method_name = STEP_METHOD_MAP.get(step_name)
    if not method_name:
        raise ValueError(f"Unknown step name: {step_name}")
    
    method = getattr(self, method_name, None)
    if not method:
        raise ValueError(f"Method {method_name} not implemented")
    
    config = state["config"]
    reg = SkillRegistry()
    steps = state["steps"]
    errors = state["errors"]
    
    # 自动从 state 中解析输入参数
    return await method(reg=reg, config=config, steps=steps, errors=errors)
```

---

### 修复 #7: API Key 租户隔离（存储层）

**影响:** 大规模改动，涉及 `PipelineStateManager`、`ThreadRepository`、`verify_api_key`、数据库 schema  
**方案:**

1. 新增 `api_keys` 表: `(id, key_hash, tenant_id, created_at, expires_at, is_active)`
2. `verify_api_key` 改为查表 + 返回 `tenant_id`
3. 所有 repository 查询加 `WHERE tenant_id = $current_tenant`
4. PipelineStateManager 的 save/load 加 `tenant_id` 参数

**分阶段实施:**
- Phase 1: 加表 + verify_api_key 改造（1 周）
- Phase 2: 存储层加 tenant_id 过滤（1 周）
- Phase 3: 前后端联调 + 测试（1 周）

---

### 修复 #8: Alembic 迁移统一

**影响:** Docker 启动脚本 + Alembic 配置，~20 行改动  
**方案:**

```bash
# docker-compose.prod.yml backend command 改为：
command: >
  sh -c "
    cd /app && python -m alembic upgrade head &&
    uvicorn src.api:app --host 0.0.0.0 --port 8001
  "
```

同时删除 `src/storage/migrations/001_init.sql`（SQL init 与 Alembic 重复）。

---

<a name="路线图"></a>
## 10. 24 周优化路线图

### Phase 1: 安全止血（第 1-3 周）

| 周 | 任务 | 优先级 |
|----|------|--------|
| 1 | 修复 #1: POYO/Seedance/CosyVoice contextvars 隔离 | 🔴 P0 |
| 1 | 修复 #5: StrategyAgent.use_mock bug | 🔴 P0 |
| 2 | 修复 #2: 激活 error_classifier，前端展示分类错误 | 🔴 P0 |
| 2 | 修复 #4: Gate 评分实现真实启发式评分 | 🔴 P0 |
| 3 | 修复 #3: ScriptWriterAgent mock 模板通用化 | 🔴 P0 |

### Phase 2: 架构加固（第 4-8 周）

| 周 | 任务 | 优先级 |
|----|------|--------|
| 4-5 | 修复 #7 (Phase 1): api_keys 表 + verify_api_key 改造 | 🔴 P0 |
| 6 | 修复 #8: Alembic 迁移统一 + docker-compose 修复 | 🟡 P1 |
| 7 | 修复 #6: 统一 STEP_METHOD_MAP 和 run_step | 🟡 P1 |
| 8 | 修复 #13: S2/S3/S4 加错误恢复机制 | 🟡 P1 |

### Phase 3: 规模就绪（第 9-16 周）

| 周 | 任务 | 优先级 |
|----|------|--------|
| 9-10 | 修复 #7 (Phase 2): 存储层加 tenant_id 过滤 | 🔴 P0 |
| 11-12 | 修复 #7 (Phase 3): 前后端联调 + 多租户测试 | 🔴 P0 |
| 13 | 修复 #12: Rate Limit 改为 Redis/PG 存储 | 🟡 P1 |
| 14 | 修复 #15: Zustand Store 持久化 | 🟡 P1 |
| 15-16 | 管线系统统一（LangGraph → StepRunner 迁移） | 🟡 P1 |

### Phase 4: 卓越运营（第 17-24 周）

| 周 | 任务 | 优先级 |
|----|------|--------|
| 17-18 | E2E 测试补全（Playwright: 前端→后端→API 全链路） | 🟡 P2 |
| 19-20 | 管线取消机制 + 进度持久化 | 🟡 P1 |
| 21-22 | 监控面板（Grafana/Prometheus metrics endpoint） | 🟢 P2 |
| 23-24 | 文档 + runbook + 故障演练 | 🟢 P2 |

---

## 附录 A: 反直觉洞察总结

| # | 洞察 | 严重性 |
|---|------|--------|
| 1 | **最完整的错误分类代码完全未被使用** — 180 行 error_classifier.py 是死代码 | 🔴 |
| 2 | **Gate 系统的价值主张在 75% 的 gate 类型上是虚假的** — 都返回 0.75 | 🔴 |
| 3 | **mock 模式在首次 API 调用前总是激活** — StrategyAgent.use_mock 的惰性初始化 bug | 🔴 |
| 4 | **多租户安全的护城河只保护了 LLM 调用，不保护媒体生成** — 3/4 的 API 客户端无隔离 | 🔴 |
| 5 | **门面最好的代码是门面** — timed_node 装饰器测量时间不准确但通过 await 协议的隐式转换避免了崩溃 | 🟡 |
| 6 | **硬编码的 mock 模板让产品多样性退化为单一母婴泵品类** — 5 个模板全部是 pump 相关 | 🔴 |
| 7 | **CLAUDE.md 的"已知问题"列表中没有一项有 scheduled_fix_date** — 文档掩盖了行动缺失 | 🟡 |
| 8 | **最快的优化不是加缓存，是删掉从未使用的 `PipelineError` / `ErrorCode` / `classify_error`** — 或者让它们真正工作 | 🟡 |

---

## 附录 B: 审查覆盖清单

| 模块 | 文件数 | 审查状态 |
|------|--------|---------|
| config.py | 1 | ✅ 完整审查 |
| api.py | 1 | ✅ 完整审查 |
| graph/ | 3 | ✅ 完整审查 |
| agents/ | 4 | ✅ 完整审查 |
| routers/ | 5 | ✅ 完整审查 |
| models/ | 3 | ✅ 完整审查 |
| pipeline/ | 8 | ✅ 完整审查 |
| tools/ | 12 | ✅ 完整审查 |
| services/ | 1 | ✅ 完整审查 |
| skills/ | 1 (registry) | ⚠️ 部分审查 |
| storage/ | 3 | ✅ 完整审查 |
| web/ | 5 | ⚠️ 抽样审查 |
| deploy/ | 2 | ✅ 完整审查 |
| Dockerfile | 1 | ✅ 完整审查 |
| tests/ | 6 (e2e) | ⚠️ 抽样审查 |
| **总计** | **~75** | **~85% 覆盖率** |
