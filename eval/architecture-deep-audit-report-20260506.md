# AI Video Pipeline (v0.2.0) — 三轮深度架构审查报告

**审查日期**: 2026-05-06  
**审查范围**: 全栈（Python后端 23,774+行 / 112个文件，Next.js前端 67个ts/tsx文件，46个测试文件）  
**审查视角**: 产品经理 × 项目经理 × 架构师  
**分析框架**: MECE（Mutually Exclusive, Collectively Exhaustive）  
**审查轮次**: 三轮迭代（架构层 → 微观层+跨层一致性 → 数据流+运营+商业逻辑）  
**代码修改**: 零修改（纯诊断）

---

## 执行摘要（Executive Summary）

该项目是一个技术 ambition 极高的多智能体视频生成系统，但在**架构一致性、并发安全、状态模型治理、成本控制**四个维度存在系统性风险。最突出的反直觉发现是：**项目同时维护了两套互不兼容的管道运行时（LangGraph通用管道 vs Skill-based场景管道），且共享同一个HTTP路由层和状态持久化层，但状态模型完全不兼容**。这在生产环境中是一个定时炸弹。

**关键评级分布**:

| 级别 | 数量 | 代表问题 |
|------|------|----------|
| 🔴 CRITICAL | 14 | 双管道状态冲突、未等待异步任务、速率限制多进程失效、SQLite异步竞争、D10路由覆盖竞态、PG/FS双写一致性窗口、API Key客户端缓存污染、视频时长产品不一致、Gate成本无上限、成本管控完全缺失 |
| 🟠 WARNING | 18 | 状态模型total=False滥用、无静态类型检查、S2-S5成熟度鸿沟、审计评分主观性、未限制CORS子域、Docker root运行、大对象存储无生命周期、CosyVoice多语言语音错误、前端STEP_ORDER与后端错位 |
| 🟡 NOTE | 10 | 前端超时缺失、翻译质量未评估、测试内联导入冗余、Zustand状态未清理、JSON序列化性能 |

**建议首要决策**: 召开架构评审会议，明确 **"是否废弃LangGraph通用管道，全面迁移到StepRunner+SkillRegistry架构"**。这个决策将解锁后续大部分重构工作。

---

## 第一轮审查：架构层（Architecture Layer）

### A1. 🔴 CRITICAL — 双管道运行时共存且状态模型不兼容

**位置**: `src/graph/pipeline.py`（LangGraph） vs `src/pipeline/s1_product_pipeline.py` + `src/pipeline/step_runner.py`（Skill-based）

**现象**:
- LangGraph管道: 16节点，使用 `VideoPipelineState` (TypedDict)，通过 `compile_pipeline()` 编译，checkpoint用 PostgresSaver/MemorySaver
- S1 Skill管道: 12步，使用纯 `dict` 状态（`{"label": ..., "steps": {...}, "config": ...}`），通过 `StepRunner._execute_step()` 顺序执行，gate系统在step_runner中实现
- 两个系统都挂载在 `/scenario/s1` 和 `/pipeline/*` 路由下
- `_state.py` 第26行在**模块导入时**就调用了 `compile_pipeline(db_url=_DB_URL)`，创建了全局 `_pipeline` 实例

**影响**:
1. 内存中同时存在两套状态机，调试时无法确定哪个系统是"真相来源"
2. `VideoPipelineState` 的 `current_step` 字段与 `StepRunner` 的 `current_step` 语义完全不同，但前端可能混淆
3. 模块级全局 `_pipeline` 意味着**所有单元测试共享同一个编译后的图实例**，测试隔离性被破坏
4. S1的gate/audit机制与LangGraph的interrupt_after机制完全独立，产品文档中的"4个审查点"实际上在不同场景下指代不同的实现

**反直觉洞察**: 团队似乎先建了LangGraph原型，发现其checkpoint恢复和人类审查路由有框架级bug（见D10补丁），于是在S1中另起炉灶用StepRunner重写了一套。但LangGraph的代码没有被移除，而是继续挂载在 `/pipeline/*` 下。这造成了**"一个产品，两个引擎"**的隐性债务。

**解决方案**:
- **短期**: 明确路由层的管道选择逻辑——S1请求必须100%路由到StepRunner，LangGraph管道仅用于遗留的 `/pipeline/*` 端点，并在API文档中标记为deprecated
- **中期**: 将LangGraph的16节点图重写为StepRunner的Skill调用序列，统一状态模型。LangGraph的value-add（checkpoint恢复、可视化）在当前的D10补丁下已被削弱
- **长期**: 如果保留LangGraph，需要将其状态序列化格式与 `PipelineStateManager` 的JSON格式统一，实现双向转换层

---

### A2. 🔴 CRITICAL — D10 ContextVar 路由覆盖是一个架构级妥协

**位置**: `src/graph/routing.py` 第28-50行

**现象**:
```python
_HUMAN_REVIEW_OVERRIDE: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "human_review_override", default={}
)
```
注释承认: "LangGraph's checkpoint recovery does not preserve `update_state` across the `astream` boundary in `interrupt_after` resume scenarios"

**影响**:
- 这是**对框架核心缺陷的补丁**，但补丁本身引入了新的并发风险：如果同一个asyncio事件循环中同时处理多个review提交（比如用户快速双击），`_HUMAN_REVIEW_OVERRIDE` 可能被后一个请求覆盖
- `_pop_override` 在读取后清除，但如果路由函数因异常未被调用（比如节点执行崩溃），覆盖值会残留，污染下一个经过该checkpoint的管道
- ContextVar在**多线程服务器**（如gunicorn sync workers + threads）中行为不可预期

**解决方案**:
- 将路由状态显式写入Postgres/LangGraph checkpoint，而不是内存覆盖。在 `submit_review` 中直接操作数据库中的管道状态，路由函数从数据库读取
- 或者，放弃LangGraph的 `interrupt_after` + `astream` 组合，改用显式的状态机轮询（类似StepRunner的做法）

---

### A3. 🟠 WARNING — 全局Pipeline实例与并发Semaphore的错配

**位置**: `src/routers/_state.py` 第25-29行

**现象**:
```python
_pipeline = compile_pipeline(db_url=_DB_URL)  # 模块导入时编译
_pipeline_semaphore = asyncio.Semaphore(10)   # 限制10个并发管道
```

**影响**:
- `_pipeline` 是全局单例，但LangGraph的 `CompiledStateGraph` 本身不是线程安全的（它内部使用checkpoint conn的共享状态）
- Semaphore限制的是并发协程数量，但**没有限制并发线程数**。如果使用多进程部署，每个进程有自己的 `_pipeline` 和 Semaphore，总并发数 = 进程数 × 10
- PostgresSaver使用的 `psycopg` 连接是**同步连接**，在async事件循环中通过线程池执行。高并发下可能耗尽连接池

**解决方案**:
- 将 `_pipeline` 的创建移入请求处理上下文（request-scoped factory），而非模块全局
- Semaphore应该基于 `DATABASE_URL` 的连接池 `max_size` 动态计算（如 max_connections // 2）
- 如果保留全局单例，需要明确文档说明部署模式必须是单进程（如 `uvicorn --workers 1`）

---

### A4. 🟠 WARNING — API Key隔离被客户端缓存破坏

**位置**: `src/tools/llm_client.py` 第99-158行

**现象**:
- `_inject_api_keys` 使用contextvars实现了per-request API key隔离
- 但 `LLMClient._get_client()` 使用key的SHA256 hash作为缓存key，相同key的并发请求共享同一个LangChain客户端实例

**影响**:
- 如果多个租户（不同用户）恰好使用相同的API key（如共享的企业key），它们共享同一个httpx client，请求/响应可能交叉污染
- 客户端实例没有生命周期管理，永远不会被清理，长期运行会导致内存泄漏
- 没有连接池超时配置，空闲连接可能占用服务器资源

**解决方案**:
- 为每个请求创建独立的client实例，或至少使用tenant-scoped的client pool
- 为缓存的client添加TTL（如5分钟未使用后关闭）
- 使用 `weakref` 或显式的 `aclose()` 来管理client生命周期

---

## 第二轮审查：微观层 + 跨层一致性（Micro Layer & Cross-Layer Consistency）

### M1. 🔴 CRITICAL — CosyVoice多语言语音预设存在根本性错误

**位置**: `src/tools/cosyvoice_client.py` 第38-44行

**现象**:
```python
VOICE_PRESETS = {
    "en": DEFAULT_VOICE,                       # English — warm male (alex)
    "zh": "FunAudioLLM/CosyVoice2-0.5B:diana", # Chinese — warm female (diana)
    "es": DEFAULT_VOICE,
    "fr": DEFAULT_VOICE,
    "de": DEFAULT_VOICE,
}
```

**影响**:
- 当用户请求西班牙语、法语或德语TTS时，系统使用英语男声alex来朗读这些语言的文本
- CosyVoice2的speaker ID是语言特定的，用英语语音模型读西班牙语会产生**灾难性的发音效果**（如英语口音、音素不匹配）
- 从PM角度，这属于"功能存在但体验不可用"——用户选择了法语，听到的是带英语口音的法语

**解决方案**:
- 为每种语言配置合适的CosyVoice speaker ID，或fallback到该语言的默认语音
- 如果某语言没有合适的speaker，应该在API层拒绝请求并返回明确的错误信息，而不是生成低质量音频
- 考虑使用ElevenLabs的多语言voice（如`eleven_multilingual_v2`）作为ES/FR/DE的fallback

---

### M2. 🔴 CRITICAL — 前端STEP_ORDER与后端不一致

**位置**: `web/src/components/VideoWorkflow.tsx` 第19-31行 vs `src/pipeline/step_runner.py` 第27-40行

**现象**:
- 前端 `STEP_ORDER`:
  ```javascript
  ["strategy", "scripts", "compliance", "storyboards", "video_prompts", 
   "thumbnail_prompts", "seedance_clips", "tts_audio", "thumbnail_images", 
   "assemble_final", "audit"]
  ```
- 后端 `STEP_ORDER`:
  ```python
  ["strategy", "scripts", "compliance", "storyboards", "keyframe_images",
   "video_prompts", "thumbnail_prompts", "seedance_clips", "tts_audio",
   "thumbnail_images", "assemble_final", "audit"]
  ```

**影响**:
- 前端缺少 `"keyframe_images"` 步骤。当后端执行完keyframe_images后，前端的`getCurrentStep()`会错误地认为当前步骤是`video_prompts`（因为keyframe_images在前端看来已经"done"——它根本不存在）
- 这会导致前端UI在keyframe_images执行期间显示错误的进度和状态
- 如果keyframe_images失败，前端无法正确显示失败步骤，因为不存在对应的UI状态

**解决方案**:
- 从后端动态获取STEP_ORDER（API返回），或维护一个共享的JSON配置文件
- 在CI中添加一致性检查脚本，比较前后端的步骤顺序

---

### M3. 🔴 CRITICAL — SkillRegistry类级状态在测试中泄漏

**位置**: `src/skills/registry.py` 第20行

**现象**:
```python
class SkillRegistry:
    _skills: dict[str, SkillCallable] = {}
```

**影响**:
- `_skills` 是类变量，所有测试共享同一个dict
- 如果测试A注册了skill X，测试B运行时会看到X（即使B不想让它存在）
- `clear()` 方法存在但依赖测试手动调用，极易遗漏
- 这会导致测试的**非确定性失败**——单个测试通过，整套测试随机失败

**解决方案**:
- 将 `_skills` 改为实例变量，使用registry单例模式管理生命周期
- 或者，在 `conftest.py` 中注册 `pytest.fixture(autouse=True)` 在每个测试后自动 `SkillRegistry.clear()`
- 为register操作添加测试模式隔离（如 `TEST_ISOLATION` 环境变量启用时，使用thread-local存储）

---

### M4. 🟠 WARNING — StrategyAgent的三层fallback链过于复杂

**位置**: `src/agents/strategy.py` 第94-192行

**现象**:
```python
if self.use_mock:
    return mock_data
if self.use_skills:
    result = await SkillRegistry.execute(...)
    if result.success:
        return result
# fallback to LLM
try:
    data = await llm.invoke_json(...)
    return data
except:
    return _MOCK_BRIEFS
```

**影响**:
- 当输出是mock数据时，无法从日志快速判断是哪个层级fallback的（是use_mock=True？还是skill失败？还是LLM失败？）
- 三层fallback使得**故障诊断时间**随层级深度指数增加
- `use_mock` 的判断逻辑 `self.use_mock = use_mock or (not use_skills and not llm._clients)` 依赖 `llm._clients` 的内部状态，这是一个**私有属性访问**，违反封装原则

**解决方案**:
- 简化fallback链为两层：**Skill优先** → **确定性fallback（mock/缓存）**。移除直接LLM调用层，将LLM封装在skill内部
- 为每次fallback添加结构化的 `fallback_reason` 字段到日志和返回元数据中
- 禁止从外部访问 `llm._clients`，改用显式的 `llm.is_available()` 公共方法

---

### M5. 🟠 WARNING — ScriptWriterAgent的mock模板与brief硬耦合

**位置**: `src/agents/script_writer.py` 第125-200+行

**现象**:
- `_SCRIPT_TEMPLATES` 使用 `BRIEF-001` 到 `BRIEF-005` 作为key，与 `_MOCK_BRIEFS` 中的ID一一对应
- 这些模板每个约200词，硬编码在Python源码中

**影响**:
- 如果 `_MOCK_BRIEFS` 被修改（如添加新brief），`_SCRIPT_TEMPLATES` 不会自动同步，导致mock模式下brief与script不匹配
- 从PM角度，mock模式下的输出质量直接代表产品的"最低体验保障"，但当前mock脚本是针对"可穿戴吸奶器"这一单一产品类别硬编码的，无法展示其他品类
- 模板中没有参数化插槽（如`{product_name}`），完全写死为"X1"

**解决方案**:
- 将mock templates提取为JSON/YAML文件，使用Jinja2模板引擎进行参数化渲染
- 建立brief-template的契约测试：每次修改_MOCK_BRIEFS时，自动验证所有brief ID都有对应的template
- 按产品类别组织mock数据（如 `mock_data/baby_care/`, `mock_data/beauty/`）

---

### M6. 🟠 WARNING — AuditorAgent评分算法缺乏业务依据

**位置**: `src/agents/auditor.py` 第126-141行（diversity_score）

**现象**:
```python
diversity_score = min(1.0, len(types_used) / 4.0)
```

**影响**:
- diversity满分只需要4种视频类型，但VideoType总共有10种。这意味着即使全部brief都是同一种类型，也能得0.25分（高于auto-reject阈值0.60的下方区间）
- USP Mapping的默认分数是0.7，无论brand_guidelines是否提供USPs
- 这些分数阈值直接影响auto-approve/auto-reject决策，但它们的设定没有A/B测试或业务分析支撑

**解决方案**:
- 将评分权重外化为配置文件（`strategy_source/<scenario>/audit_weights.json`），允许运营团队调整
- 添加评分解释性输出：不仅返回分数，还返回"如果增加1种视频类型，分数将提升X"
- 对评分逻辑进行敏感性分析（monte carlo simulation），量化输入变化对最终决策的影响

---

### M7. 🟠 WARNING — retry.py的字符串匹配脆弱

**位置**: `src/tools/retry.py` 第39-67行

**现象**:
```python
def is_retryable(exception: Exception) -> bool:
    msg = str(exception).lower()
    if any(x in msg for x in ["connection", "timeout", "timed out", ...]):
        return True
```

**影响**:
- 依赖异常消息中的子串匹配来判断是否可重试。如果DeepSeek将"timeout"改为"request timed out"，重试逻辑仍然工作（因为"timed out"在列表中），但如果改为"deadline exceeded"就不工作了
- 没有检查异常类型（如 `httpx.ConnectError`, `asyncio.TimeoutError`），纯粹依赖字符串匹配
- 某些4xx错误（如401 Unauthorized）如果消息中恰好包含"connection"子串，会被错误地重试

**解决方案**:
- 优先检查异常类型链：`isinstance(exc, (httpx.NetworkError, asyncio.TimeoutError))`
- 对HTTP状态码使用结构化访问：如果异常包含 `response.status_code`，直接检查状态码数字
- 字符串匹配作为fallback，但维护一个明确的**非重试黑名单**（如401, 403）

---

### M8. 🟠 WARNING — WebhookManager的SSRF防护不完整

**位置**: `src/tools/webhook_manager.py` 第51-71行

**现象**:
- `_is_safe_webhook_url` 检查URL scheme和hostname是否为私有IP
- 但没有检查DNS解析后的IP（DNS rebinding攻击）
- 没有限制端口（如 `http://example.com:22/` 或 `:6379`）
- 没有限制URL长度（可能导致日志注入）

**影响**:
- 攻击者可以注册 `http://attacker.com:22/` 作为webhook，利用服务器的httpx client扫描内网Redis或SSH端口
- DNS rebinding攻击：注册时解析到公网IP，随后将DNS记录改为内网IP，服务器在重试时访问内网服务

**解决方案**:
- 限制允许的端口为80/443
- 在请求时（而不仅是注册时）解析DNS并验证IP地址
- 使用httpx的 `mounts` 限制允许的协议和端口
- 考虑使用专门的SSRF防护库（如 `ssrf-protect`）

---

### M9. 🟡 NOTE — FastModeService的模块级单例与key隔离冲突

**位置**: `src/services/fast_mode.py` 第30-38行

**现象**:
```python
_fast_mode_service_instance: FastModeService | None = None

def get_fast_mode_service() -> FastModeService:
    global _fast_mode_service_instance
    if _fast_mode_service_instance is None:
        _fast_mode_service_instance = FastModeService()
    return _fast_mode_service_instance
```

**影响**:
- FastModeService内部持有 `LLMClient` 实例，而 `LLMClient` 的 `_clients` 缓存是per-key的
- 如果请求A使用key1，请求B使用key2，由于FastModeService是单例，两个请求共享同一个 `LLMClient` 实例
- 虽然 `LLMClient._get_client` 使用key hash来区分缓存，但 `_clients` dict本身没有并发保护（多线程下可能竞态）

**解决方案**:
- 移除FastModeService的单例模式，改为per-request实例化（FastModeService很轻量，主要是client引用）
- 或者，将 `LLMClient._clients` 改为 `threading.RLock` 保护的字典

---

### M10. 🟡 NOTE — SeedanceClient的poyo优先逻辑造成配置歧义

**位置**: `src/tools/seedance_client.py` 第98-111行

**现象**:
```python
if POYO_API_KEY:
    self._is_poyo = True
    _seedance_key = POYO_API_KEY
    _seedance_url = POYO_API_BASE_URL
```

**影响**:
- 当用户同时设置了 `SEEDANCE_API_KEY` 和 `POYO_API_KEY` 时，POYO无条件优先
- 用户可能期望使用原生Seedance API（如为了更高质量或更低成本），但系统静默切换到poyo
- 没有日志告知用户"虽然你配置了Seedance，但我们用了poyo"

**解决方案**:
- 添加显式的 `VIDEO_BACKEND` 环境变量（`seedance|poyo|auto`），默认auto
- 当backend选择发生override时，记录warning日志

---

## 第三轮审查：数据流 + 运营 + 商业逻辑（Data Flow + Operations + Business Logic）

### B1. 🔴 CRITICAL — 成本控制机制完全缺失

**位置**: 全局

**现象**:
- 项目调用多个付费API：DeepSeek（$0.5-2/M tokens）、Seedance/poyo（$0.1-0.5/视频）、CosyVoice（$0.01-0.05/音频）、ElevenLabs、DALL-E/GPT-Image
- 代码中没有：每用户配额、每日/每月预算上限、成本估算预警、API调用计数器
- 仅有 `elevenlabs_client.py:342` 和 `dalle_client.py:150` 有 `cost_estimate()` 方法，但从未被调用

**影响**:
- 一个恶意用户或bug可以无限生成视频，导致数千美元的API账单
- Gate系统的3候选生成意味着**每个审查点的LLM成本是普通步骤的3倍**，且用户可以无限regenerate
- 没有成本数据，产品团队无法计算unit economics（如"每个视频的平均生成成本"）

**反直觉洞察**: 大多数AI SaaS在MVP阶段都忽视了成本控制，但这恰恰是最应该在早期建立的机制——因为后期的成本追溯和配额追加非常困难，且容易引发用户投诉（"为什么我的账户突然欠费$500？"）。

**解决方案**:
- 引入 **CostTracker** 中间件，为每个pipeline run、每个gate、每个regenerate记录API调用次数和估算成本
- 实现硬配额和软配额：硬配额在API层拦截（返回429），软配额发送告警但允许继续（用于trusted users）
- 为不同场景设置不同的成本上限：Fast Mode <$0.1, S1 Auto <$2.0, S5 VLOG <$5.0
- 每日预算告警：当单日成本超过阈值时，通知运维团队并自动降级为mock模式

---

### B2. 🔴 CRITICAL — pipeline_degraded在S1管道中未设置

**位置**: `src/pipeline/step_runner.py` 第236-294行（`_execute_step`）

**现象**:
- 在LangGraph管道中，`_wrap_node_with_error_handling` 设置了 `pipeline_degraded = True`
- 在StepRunner的 `_execute_step` 中，错误只被记录到 `state["errors"]`，**没有设置 `pipeline_degraded`**
- `state_manager.py` 的load/save只传递 `errors` 字段，不传递 `pipeline_degraded`

**影响**:
- S1管道（实际生产路径）中的节点失败不会触发与LangGraph管道相同的终止逻辑
- 如果一个关键步骤（如seedance_clips）失败，resume会继续执行后续步骤（如tts_audio、assemble_final），导致基于不完整数据的错误输出
- 用户可能收到"成功"的HTTP响应，但视频文件实际上不存在或已损坏

**解决方案**:
- 在 `_execute_step` 的except块中设置 `state["pipeline_degraded"] = True`
- 在 `resume()` 的循环中，每次迭代前检查 `pipeline_degraded`，如果为True则立即终止并返回错误状态
- 在 `run_s1_step` 路由中，如果返回的状态包含 `pipeline_degraded`，返回HTTP 500而非200

---

### B3. 🔴 CRITICAL — Gate系统的3候选生成成本无上限

**位置**: `src/routers/scenario.py` 第719-748行（`generate_gate_candidates`）

**现象**:
- 每个gate生成3个候选（standard/creative/conservative），每个候选都调用LLM或媒体生成API
- 用户可以对单个candidate无限次调用 `regenerate_gate_candidate`
- 没有成本限制、没有速率限制、没有每日上限

**影响**:
- 一个用户在单个gate上regenerate 10次，成本可能是普通pipeline的30倍
- 如果用户编写脚本自动化调用regenerate，可以造成显著的财务损失
- 从PM角度，"无限regenerate"虽然提升了用户体验，但没有与成本模型匹配

**解决方案**:
- 为每个gate设置 **regenerate预算上限**（如最多5次/用户/天）
- 引入 **candidate缓存**：相同输入的regenerate返回缓存结果，不重复调用API
- 实现 **渐进式质量衰减**：多次regenerate后，从cheaper的模型生成（如从deepseek-v4-pro降级到deepseek-chat）

---

### B4. 🟠 WARNING — target_languages硬编码遍布17处

**位置**: 全局（grep结果17处）

**现象**:
- 虽然 `config.py` 定义了 `DEFAULT_LANGUAGES = ["en"]`，但各路由器直接硬编码 `["en"]` 而不是引用常量
- `src/routers/scenario.py` 中S2甚至允许 `body.get("target_languages", ["en"])` 透传，但S1强制覆盖

**影响**:
- 如果未来要支持多语言，需要修改17个分散的位置，极易遗漏
- S2和S1对target_languages的处理不一致，产品体验碎片化
- 硬编码值使得A/B测试不同语言默认设置变得困难

**解决方案**:
- 统一使用 `config.DEFAULT_LANGUAGES`，禁止在业务代码中硬编码语言列表
- 在Pydantic请求模型中添加语言验证（如 `Language` enum），在API入口层统一处理

---

### B5. 🟠 WARNING — 视频时长限制产品逻辑不一致

**位置**:
- S1: `{15, 30, 45, 60, 90}`（`s1_product_pipeline.py:93`）
- S3: `VIDEO_MAX_DURATION = 15`（`s3_remix_pipeline.py:580`）
- S5: `VIDEO_MAX_DURATION = 15`（`s5_brand_vlog_pipeline.py:27`）

**影响**:
- 同一个平台（Happy Horse/poyo）在不同场景下有不同的时长限制。S1允许90秒，S3/S5只允许15秒
- 从产品角度，用户无法理解"为什么Brand VLOG只能15秒，但Product Direct可以90秒"
- 实际上这是因为S1使用了Remotion组装多个clip，而S3/S5直接生成单clip，但这一点没有在UI中解释

**解决方案**:
- 在UI中明确标注每个场景的时长限制及原因（如"VLOG场景使用单段AI生成，上限15秒"）
- 考虑为S3/S5也引入Remotion组装，解除15秒限制
- 将时长验证集中到统一的 `VideoDurationValidator` 中，按场景返回允许的时长集合

---

### B6. 🟠 WARNING — 运营日志缺乏业务维度

**位置**: `src/telemetry.py`, 各agent的structlog调用

**现象**:
- 日志包含 `trace_id`, `node_name`, `duration_ms`，但缺少：
  - `product_name` / `brand_name`
  - `content_scenario`
  - `video_duration`
  - `target_platforms`
  - `estimated_cost`

**影响**:
- 当运营团队需要分析"Momcozy品牌的视频生成成功率"时，现有日志无法直接支持
- 故障排查时无法快速过滤"某品牌某场景"的日志
- 无法建立业务级SLO（如"S1 Product Direct的端到端成功率 > 95%"）

**解决方案**:
- 在pipeline启动时，将业务上下文（product_name, brand, scenario, duration）绑定到trace context
- 使用structlog的 `bind()` 在每次日志调用中自动注入这些字段
- 在telemetry dashboard中按业务维度聚合（而非仅按技术维度）

---

### B7. 🟡 NOTE — JSON序列化存在重复计算

**位置**: `src/pipeline/state_manager.py` 第114-145行

**现象**:
- 每次 `save()` 将state序列化为JSON，先尝试PG写入，再FS写入
- 但PG写入使用的是 `repo.create/update`，它将dict转为SQL参数——**不需要JSON字符串**
- FS写入才需要JSON序列化
- 当前代码没有对PG路径做特殊处理，而是让repo内部再次序列化（如果repo使用JSONB字段）

**影响**:
- 每步save至少2次完整序列化（PG一次、FS一次），state越大开销越大
- 如果state中包含大量媒体元数据（如base64图片预览），序列化可能成为瓶颈

**解决方案**:
- 延迟序列化：FS路径需要时再进行JSON序列化，PG路径传递原始dict
- 对大型字段（如keyframes的base64数据）使用引用存储（存储文件路径而非数据本身）

---

### B8. 🟡 NOTE — S1 pipeline的并发限制与实际不符

**位置**: `src/pipeline/s1_product_pipeline.py` 第506行, 第713行

**现象**:
- 注释说明"poyo.ai has strict concurrency limits on queue = 2"
- 代码中使用 `asyncio.Semaphore(2)` 限制并发clip生成

**影响**:
- 但 `_state.py` 中 `_pipeline_semaphore = asyncio.Semaphore(10)` 限制的是整个pipeline的并发数
- 这意味着10个pipeline可以并发运行，每个pipeline可能生成2个clip，总并发clip生成 = 20，远超poyo的限制
- 这会导致poyo返回429或队列等待时间显著增加

**解决方案**:
- 将媒体生成的并发限制提升为**全局级别**（跨所有pipeline共享的Semaphore），而非per-pipeline级别
- 或者，使用有界队列（如Redis分布式锁）来全局限制对poyo的并发调用数

---

## 综合优化路线图（Integrated Optimization Roadmap）

### Phase 1 — 生产安全加固（1-2周）

| 优先级 | 问题ID | 影响 | 验收标准 |
|--------|--------|------|----------|
| P0 | B2 | S1错误未终止管道 | StepRunner错误时设置pipeline_degraded，resume循环检查并终止 |
| P0 | D2(首轮) | SQLite阻塞事件循环 | 引入aiosqlite或asyncio.to_thread封装所有SQLite调用 |
| P0 | D1(首轮) | 后台任务静默失败 | 所有asyncio.create_task统一使用_register_background_task |
| P0 | G1(首轮) | Docker root运行 | Dockerfile添加非特权用户，CI验证镜像不以root运行 |
| P1 | G2(首轮) | 密码硬编码 | docker-compose使用.env引用，删除所有硬编码凭据 |
| P1 | C2(首轮) | 响应包装中间件OOM | 对>1MB响应跳过包装，使用bytearray替代字节拼接 |

### Phase 2 — 架构债务清理（2-4周）

| 优先级 | 问题ID | 影响 | 验收标准 |
|--------|--------|------|----------|
| P0 | A1 | 双管道冲突 | 明确LangGraph仅用于遗留端点，S1 100%路由到StepRunner |
| P1 | A2 | D10路由竞态 | 将review状态写入DB checkpoint，路由函数从DB读取 |
| P1 | B1 | 成本失控 | CostTracker上线，每pipeline/gate/regenerate记录估算成本 |
| P1 | B3 | Gate成本无上限 | 每个用户每日regenerate上限5次，超限时返回429 |
| P1 | C1(首轮) | 速率限制多进程失效 | 使用Redis实现全局速率限制，或迁移到Nginx层 |
| P2 | B4 | 语言硬编码 | 统一使用config.DEFAULT_LANGUAGES，引入Language enum验证 |
| P2 | B2(首轮) | PG/FS双写一致性 | 实现FS→PG的后台补偿任务，或降级为单主模式 |

### Phase 3 — 产品体验统一（4-6周）

| 优先级 | 问题ID | 影响 | 验收标准 |
|--------|--------|------|----------|
| P1 | M2 | 前后端步骤不一致 | 前端从API动态获取STEP_ORDER，CI添加一致性检查 |
| P1 | M1 | CosyVoice多语言错误 | 为ES/FR/DE配置正确speaker，或拒绝不支持的组合 |
| P1 | F1(首轮) | S2-S5无step-by-step | 统一使用StepRunner基础设施，所有场景支持gate |
| P2 | B5 | 时长限制不一致 | 统一时长验证器，UI中解释各场景限制原因 |
| P2 | D3(首轮) | 审计评分主观性 | 评分权重外化为配置，添加评分解释性输出 |
| P2 | F2(首轮) | 翻译质量未评估 | 翻译后LLM自检，低质量时标记人工确认 |

### Phase 4 — 工程卓越（持续）

| 优先级 | 问题ID | 影响 | 验收标准 |
|--------|--------|------|----------|
| P2 | E1(首轮) | 无静态类型检查 | pyright通过，零类型错误 |
| P2 | M3 | SkillRegistry测试泄漏 | conftest自动clear，所有测试隔离通过 |
| P2 | H1(首轮) | 前端请求无超时 | apiFetch添加AbortSignal.timeout，GET重试3次 |
| P3 | B6 | 日志缺业务维度 | trace context绑定product/brand/scenario，dashboard按业务聚合 |
| P3 | B7 | JSON序列化重复 | PG路径传递原始dict，FS路径延迟序列化 |

---

## 附录A：MECE分类总览

```
审查维度
├── 架构设计 (Architecture)
│   ├── 运行时一致性 ── A1 双管道冲突, A2 D10补丁, A3 Semaphore错配
│   └── 资源隔离 ── A4 API Key缓存污染
├── 数据与状态 (Data & State)
│   ├── 类型安全 ── B1(首轮) total=False滥用, B3(首轮) 序列化器隐式扫描
│   ├── 持久化一致性 ── B2(首轮) PG/FS双写, B7 JSON重复序列化
│   └── 状态传播 ── B2 pipeline_degraded缺失
├── 安全与合规 (Security)
│   ├── 访问控制 ── C1(首轮) 速率限制失效, C3(首轮) API Key明文存储
│   ├── 请求安全 ── C2(首轮) 响应包装OOM, M8 Webhook SSRF
│   └── 权限模型 ── C4(首轮) Demo Key全开
├── 可靠性工程 (Reliability)
│   ├── 异步治理 ── D1(首轮) fire-and-forget, D2(首轮) SQLite阻塞
│   ├── 外部API韧性 ── M7 retry字符串匹配, M10 Seedance配置歧义
│   └── 降级链 ── M4 StrategyAgent三层fallback
├── 商业逻辑 (Business Logic)
│   ├── 成本控制 ── B1 完全缺失, B3 Gate无上限
│   ├── 配额管理 ── B4 语言硬编码17处, B5 时长不一致
│   └── 定价策略 ── 无（待建立）
├── 产品体验 (Product Experience)
│   ├── 场景一致性 ── F1(首轮) S2-S5成熟度鸿沟, M2 STEP_ORDER错位
│   ├── 本地化 ── M1 CosyVoice语音错误, F2(首轮) 翻译质量
│   └── 可预测性 ── M6 审计评分主观性
├── 基础设施 (Infrastructure)
│   ├── 容器安全 ── G1(首轮) root运行, G2(首轮) 密码硬编码
│   ├── 存储治理 ── G4(首轮) 大对象无生命周期
│   └── 部署模式 ── G3(首轮) --reload在容器
└── 前端工程 (Frontend)
    ├── 网络层 ── H1(首轮) 超时缺失
    ├── 状态管理 ── H2(首轮) Zustand未持久化
    └── 类型系统 ── H3(首轮) OpenAPI断裂
```

---

## 附录B：关键代码片段索引

| 问题ID | 文件路径 | 行号范围 | 问题类型 |
|--------|----------|----------|----------|
| A1 | `src/routers/_state.py` | 25-26 | 模块级全局pipeline |
| A1 | `src/graph/pipeline.py` | 102-198 | LangGraph图定义 |
| A1 | `src/pipeline/step_runner.py` | 27-40 | Skill-based步骤定义 |
| A2 | `src/graph/routing.py` | 28-50 | ContextVar路由覆盖 |
| A3 | `src/routers/_state.py` | 29 | Semaphore(10) |
| A4 | `src/tools/llm_client.py` | 99-158 | 客户端缓存 |
| B1 | `src/models/state.py` | 30 | total=False |
| B2 | `src/pipeline/state_manager.py` | 114-145 | PG/FS双写 |
| B3 | `src/routers/scenario.py` | 719-748 | Gate候选生成 |
| C1 | `src/api.py` | 99-140 | 内存速率限制 |
| C2 | `src/api.py` | 160-219 | 响应包装中间件 |
| D1 | `src/graph/nodes.py` | 339, 435, 508, 574, 643 | fire-and-forget webhook |
| D2 | `src/storage/db.py` | 45-53 | SQLite同步连接 |
| M1 | `src/tools/cosyvoice_client.py` | 38-44 | VOICE_PRESETS |
| M2 | `web/src/components/VideoWorkflow.tsx` | 19-31 | STEP_ORDER缺失keyframe_images |
| M3 | `src/skills/registry.py` | 20 | 类级_skills字典 |
| M4 | `src/agents/strategy.py` | 94-192 | 三层fallback链 |
| M7 | `src/tools/retry.py` | 39-67 | 字符串匹配重试 |
| M8 | `src/tools/webhook_manager.py` | 51-71 | SSRF防护缺失 |
| B1 | 全局 | - | 成本控制缺失 |
| B2 | `src/pipeline/step_runner.py` | 236-294 | pipeline_degraded未设置 |
| B4 | 全局 | 17处 | target_languages硬编码 |
| B5 | `src/pipeline/s1_product_pipeline.py` | 93 | 时长valid集合 |
| B5 | `src/pipeline/s3_remix_pipeline.py` | 580 | VIDEO_MAX_DURATION=15 |
| B5 | `src/pipeline/s5_brand_vlog_pipeline.py` | 27 | VIDEO_MAX_DURATION=15 |

---

## 附录C：反直觉洞察汇总

1. **"好的并发隔离设计被坏的缓存设计抵消"**: API key的contextvars隔离是一个精妙的并发设计，但LLMClient的 `_clients` 缓存使用key hash作为索引，使得相同key的并发请求共享同一个LangChain客户端——如果该客户端内部有可变状态（如连接池），隔离就被破坏了。

2. **"防御性编程变成了隐蔽的bug来源"**: `total=False` 本是为了"防御"（避免节点未设置字段时出错），但实际上它剥夺了类型检查器发现"节点A忘记写入必需字段"的能力。真正需要防御的是**节点契约**，而不是**状态定义**。

3. **"测试覆盖率与系统可靠性不成正比"**: 项目有46个测试文件，但没有一个测试覆盖"两个并发S1 pipeline使用不同的API key"这一核心场景。测试集中在路由逻辑和状态转换，但对并发、持久化、外部API降级等生产关键路径缺乏覆盖。

4. **"技术债的隐藏成本不在代码中，在决策记录中"**: D10补丁的注释清楚地记录了"LangGraph checkpoint recovery有bug"，但这个知识只存在于代码注释中。如果团队将来升级LangGraph版本，没有人会记得去验证这个bug是否已修复，D10补丁可能会永远留在代码中。

5. **"Gate系统的用户体验越好，财务风险越高"**: 3候选生成+无限regenerate提供了极致的用户控制，但每一次regenerate都是直接的API成本。在没有成本上限的情况下，"好的UX"与"可持续的商业模式"之间存在根本冲突。

6. **"多语言支持存在于类型签名中，但不在运行时行为中"**: 代码中有 `target_languages: list[str]`、`Language` enum、ES/FR/DE的prompt模块，但实际运行时所有路径都被强制覆盖为 `["en"]`。这是典型的"架构支持但产品禁用"——最危险的债务形式，因为未来的开发者会误以为多语言已经实现。

---

*报告生成完毕。未修改任何源代码。*
