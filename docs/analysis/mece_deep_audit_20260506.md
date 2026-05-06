# AI Video Pipeline — MECE 深度审计报告

**日期:** 2026-05-06  
**审计人:** 产品经理 / 项目经理 / 架构师  
**审计范围:** 全栈（Python 后端 + Next.js 前端 + 部署 + DevOps）  
**方法:** MECE（Mutually Exclusive, Collectively Exhaustive）+ 批判性思维 + 反直觉洞察

---

## 总体评级: B / B+

项目整体架构设计合理，核心路径已通过 5 场景端到端验证。但存在若干结构性脆弱点和中度到高危的工程质量问题，若不修复，会在规模化（多租户、高并发、长周期运营）时集中爆发。

---

## 一、架构与设计 (Architecture & Design)

### 🔴 1.1 两套管线系统并存，状态模型不一致

**问题:** 项目同时存在两套完全不同的管线执行系统：

1. **LangGraph Pipeline** (`src/graph/`) — 16 节点 + 4 中断点 + HITL，使用 `VideoPipelineState` TypedDict
2. **Skill-based StepRunner Pipeline** (`src/pipeline/`) — 12 步技能链 + 4 Gate，使用 `PipelineStateManager` 存储

两套系统：
- 状态字段命名不同（`weekly_calendar` vs `steps.strategy.output`）
- 错误处理不同（`pipeline_degraded` vs `errors` list）
- HITL 机制不同（`interrupt_after` vs Gate approve/resume）
- S2-S5 只走 LangGraph，S1 两套都走

**后果:**
- `/pipeline/start` 端点用 LangGraph + PostgresSaver
- `/scenario/s1` 端点用 StepRunner + PipelineStateManager
- 同一产品概念（"跑一条 S1 管线"）走两条完全不同的代码路径
- 修复一个系统的 bug 不会自动惠及另一个
- 新增场景时必须决定用哪套，产生技术债折旧

**根因:** 历史演进产物。LangGraph 是早期架构，StepRunner 是后来为了"step-by-step + gate"加的，但没替换旧系统。

**建议:** 统一为一套管线引擎。推荐以 StepRunner 体系为基础（因为它支持 gate、regenerate、edited_output 等高级功能），将 LangGraph 的 audit 节点逻辑迁移为 StepRunner 的 audit step。LangGraph 的 HITL interrupt_after 能力可以用 StepRunner 的 Gate 抽象替代。

---

### 🔴 1.2 PostgresSaver 与 PipelineStateManager 的双重持久化

**问题:** 在生产环境中，LangGraph checkpoint state 写入 PostgresSaver（`compile_pipeline(db_url=...)`），而 StepRunner 的 state 写入 PipelineStateManager（先 PG 后 FS 双写）。这意味着同一请求可能触发两套独立的持久化写操作，存在数据不一致窗口。

**LOC 证据:**
- `src/graph/pipeline.py:248-276` — PostgresSaver 连接，fail-fast on error
- `src/pipeline/state_manager.py:57-80` — PG-primary with FS fallback
- `src/routers/_state.py:24-26` — 编译时传入 DATABASE_URL

**后果:**
- 管线中断后恢复时，LangGraph checkpoint 和 PipelineState 可能不同步
- 回滚策略不存在
- 没有跨两套存储的事务保证

**建议:** 选择一套持久化策略。推荐 PipelineStateManager（它已经有 PG+FS 双写和恢复逻辑），LangGraph 仅作为 DAG 编排引擎，不做自己的 checkpoint。

---

### 🟡 1.3 场景管线严重不均衡

**问题:** S1 有完整的 StepRunner + Gate + regenerate + edited_output 体系，S2-S5 只有最基础的 `p.run()` 一步调用。CLAUDE.md 已有记载但仍需强调其严重性：

- S2 (`s2_brand_pipeline.py`): 无 step-by-step，无 gate，无 regenerate
- S3 (`s3_remix_pipeline.py`): 同上，但有翻译支持
- S4 (`s4_live_shoot_pipeline.py`): 最简实现
- S5 (`s5_brand_vlog_pipeline.py`): 有自定义 super-prompts 但无 gate

**后果:** 用户在不同场景间的体验完全不同——S1 可以逐步审阅、修改、重生成，S5 只能一把梭，30 分钟后拿结果或报错。

**建议:** 抽象出 `BaseScenarioPipeline` 基类，统一 step/gate/regenerate 能力，各场景只需实现 step 的 skill mapping。

---

### 🟡 1.4 模型选择器硬编码在业务逻辑中

**问题:** `src/services/fast_mode.py:121` 硬编码了 DeepSeek provider 特殊逻辑：
```python
model="deepseek-chat" if DEFAULT_LLM_PROVIDER == "deepseek" else None
```

这意味着：
- 每个调用方需要自己理解"V4-Pro 推理很慢，快模式要用 V3"
- 如果要切换 provider（如 Kimi），这个逻辑就失效了

**建议:** 在 `LLMClient` 或 config 中引入"purpose → model"映射表：
```python
LLM_MODEL_BY_PURPOSE = {
    "fast": "deepseek-chat",      # 低延迟
    "quality": "deepseek-v4-pro", # 高质量推理
    "default": DEEPSEEK_MODEL,
}
```

---

## 二、安全 (Security)

### 🔴 2.1 API Key 单一全权限，无租户隔离保证

**问题:** 当前 `API_KEY` 是全局单一字符串（硬编码在 `.env.prod` 中为 `ai_video_demo_2026`）。`verify_api_key` 只是字符串匹配：

```python
# src/routers/_deps.py:29-31
if x_api_key != API_KEY:
    raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

虽然有 `contextvars` 注入 `api_keys` 的机制，但：
- **没有** 按 key 做存储隔离（所有 pipeline states 都在同一个 PG schema 里）
- **没有** rate limit 按 key 而非 IP（`rate_limit_middleware` 只按 IP）
- **没有** key 使用量统计或配额限制

**后果:** 一旦给用户 A 一个 key，用户 A 可以：
- 看到/修改用户 B 的 pipeline state（如果知道 label）
- 耗尽 LLM/视频生成 API 配额

**根因:** 项目从单用户 demo 演进而来，多租户是后加的概念，但没有做彻底的权限改造。

**建议:**
1. API key 需绑定 tenant_id，生成时写入 `api_keys` 表
2. 所有 storage 查询加上 `WHERE tenant_id = $current_tenant`
3. rate limit 改为 `per_key` 而非 `per_ip`
4. 给 `ai_video_demo_2026` 加 admin 标记但限制低级操作（或不限制但追加审计日志）

---

### 🟡 2.2 Rate Limit 内存存储无持久化，多进程不生效

**问题:** `src/api.py:99-140` 的 rate limit 使用进程内 OrderedDict 存储，Docker Compose 中如果 backend 有多个 worker（uvicorn workers > 1），每个 worker 有独立的计数器。

**建议:** 换用 Redis（声明在 requirements.txt 但未使用）或 PG 做 rate limit 存储。

---

### 🟡 2.3 CORS 配置过度宽松

**问题:** `src/api.py:88` 中 CORS origins 允许 `https://*.tcloudbaseapp.com` 通配符。虽然是明确配置的，但加上 `allow_credentials` 或允许 `Authorization` header 时会引入 CSRF 风险。

当前还好（没有 `allow_credentials=True`），但应记录清楚部署到新域名时必须更新 CORS 名单。

---

### 🟢 2.4 SSRF 防护做得不错

`webhook_manager.py:51-70` 的 `_is_safe_webhook_url` 检查了 private IP / loopback / link-local / reserved / multicast 地址。这是好的实践。

---

## 三、可靠性与错误处理 (Reliability & Error Handling)

### 🔴 3.1 `timed_node` 装饰器只支持同步函数

**问题:** `src/telemetry.py:275-317` 中 `timed_node` 的实现是同步 `def wrapper(state, ...) -> dict`，但项目中的所有 16 个节点函数都是 `async def`。LangGraph 调用的是 `async for event in pipeline.astream(...)`，这意味着节点必须返回 awaitable。

**后果:** 如果 LangGraph 尝试 `await timed_node(strategy_node)(state)` 会收到 `dict` 而非 coroutine，可能已经被 LangGraph 内部处理（await 非 awaitable 在某些版本中返回原值），但 `timed_node` 的同步签名意味着 `time.time()` 测量的是创建 coroutine 的时间，而非实际执行时间。

**验证:** 需要确认 `timed_node` 装饰后的 async 函数是否真的在执行时才记录时间。如果 `state` 是 dict（实际是 TypedDict），在 `_wrap_node_with_error_handling` 内部被再次包装，那么 `timed_node` 的 start time 早于实际执行，duration 会偏高。

**建议:** 将 `timed_node` 改为支持 async 函数：
```python
@functools.wraps(func)
async def wrapper(state, *args, **kwargs) -> dict:
    start = time.time()
    try:
        result = await func(state, *args, **kwargs)  # await async node
        ...
```

---

### 🟡 3.2 POYO 客户端无 contextvars 隔离

**问题:** `PoyoClient` 在 `__init__` 时从 module-level config 读取 `POYO_API_KEY`：
```python
# src/tools/poyo_client.py:42-43
self.api_key = api_key or POYO_API_KEY
self.base_url = (base_url or POYO_API_BASE_URL).rstrip("/")
```

但 `_inject_api_keys` 只注入了 `POYO_API_KEY` 到 `llm_client` 的 contextvars，而不是到 `PoyoClient`。如果两个并发请求使用不同的 API key，`PoyoClient` 不会感知。

**检查:** `poyo_client.py` 中确实没有 `get_request_api_key()` 调用。

**建议:** PoyoClient 加 contextvars 隔离，与 LLMClient 保持一致。

---

### 🟡 3.3 错误日志中的 "resume" 端点写错了 log 消息

**问题:** `src/routers/scenario.py:392-393`:
```python
logging.error("s1 regenerate failed: %s", e)
```
这是 `resume_s1_pipeline` 函数，但 log 消息写的是 "regenerate"。类似问题存在于 `get_s1_state` (`l.415`) 和 `update_s1_state` (`l.457`)。

这会让运维排查时混淆——看到 "regenerate failed" 但实际是 resume 操作。

---

### 🟡 3.4 `_parse_json` 的回退正则可能导致静默错误

**问题:** `src/tools/llm_client.py:213-233`：
```python
match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
if match:
    try:
        return json.loads(match.group(1))
```

这个正则会贪婪匹配最后一个 `}` 到第一个 `{` 之间的内容。如果 LLM 返回了多段 JSON（如 `{"a": 1} extra text {"b": 2}`），它会匹配整段 `{"a": 1} extra text {"b": 2}`，导致 JSON 解析失败后 raise。但没有 fallback 去尝试匹配第一个 JSON 对象。

**建议:** 使用非贪婪匹配或迭代匹配多个 JSON 块：
```python
match = re.search(r'(\{(?:[^{}]|{[^{}]*})*\})', raw)
```

---

### 🟢 3.5 P0-2 错误降级守卫做得不错

`_degraded_guard` 在每个 routing function 的第一行检查，pipeline_degraded 立即终止。webhook + error_collector 的异常隔离也到位（fire-and-forget，不阻塞管线）。

---

## 四、性能与可扩展性 (Performance & Scalability)

### 🟡 4.1 LLMClient 实例缓存不感知 timeout 变更

**问题:** `_get_client()` 按 `{provider}:{model}:{key_hash}` 缓存，但如果调用方创建了不同的 timeout（如 S5 的 `LLMClient(timeout=120.0)`），缓存的 client 会有错误的 timeout。

**LOC 证据:** `src/tools/llm_client.py:112-113`:
```python
key_hash = hashlib.sha256(key.encode()).hexdigest()[:16] if key else "default"
cache_key = f"{self.provider}:{model}:{key_hash}"
```

没有把 `self.timeout` 纳入 cache key。

**建议:** 将 timeout 纳入 cache key: `f"{self.provider}:{model}:{key_hash}:t{self.timeout}"`

---

### 🟡 4.2 PipelineStateManager 每次都执行 SQL，无连接复用优化

`PipelineStateManager` 的 `load()` 和 `save()` 每次操作都 new `PipelineStateRepository()` 实例，内部通过 `get_pool()` 获取连接。虽然 asyncpg pool 本身有连接复用，但 Repository 实例的重复创建是不必要的开销。

---

### 🟡 4.3 nginx 反向代理未启用 gzip

`deploy/lighthouse/nginx.conf` 中没有 `gzip on`。前端 JS bundle 可能数 MB，不压缩会增加加载时间。

---

### 🟢 4.4 性能优化已做的不错部分

- Portfolio `/api/portfolio/` 使用 30s 内存缓存 + `?limit=50&sort=quality` 截断
- nginx `try_files` 静态直送 `/api/media/` 避免 FastAPI 穿透
- FastAPI `_pipeline_semaphore = asyncio.Semaphore(10)` 限制了并发管线数
- POYO poll interval 5s，max 300s timeout，合理

---

## 五、代码质量与可维护性 (Code Quality & Maintainability)

### 🟡 5.1 logger 使用不一致

**问题:** 项目中同时使用三种 logger 获取方式：
1. `import structlog; logger = structlog.get_logger()` — nodes.py, fast_mode.py 等
2. `import logging; logger = logging.getLogger(__name__)` — state_manager.py, db.py
3. `import logging; logging.error(...)` — scenario.py 中多处内联调用

structlog 和 stdlib logging 的 output format 不同，混合使用导致日志格式不一致。特别是 scenario.py 中的内联 `logging.error(...)` 不会被 structlog 的 ConsoleRenderer 美化。

**建议:** 全项目统一使用 structlog。用 eslint/ruff 规则禁止 `logging.getLogger` 的直接 import。

---

### 🟡 5.2 require 的底层实现被注释标记为 stale

**问题:** `src/pipeline/s1_product_pipeline.py:42` 注释中有：
```python
import src.skills.storyboard  # noqa: F401  (best-effort; may not exist in repo)
```

这表明代码中存在"可能会 import 失败但我们不管"的 import。Git blame 可追溯，但对新人来说是困惑点。

---

### 🟡 5.3 Dual import 防护不一致

`src/api.py` 中有大量的 try/except ImportError 防护：
```python
try:
    from fastapi import FastAPI
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
```

但其他模块（如 `src/graph/pipeline.py`）直接 import FastAPI 相关类型，不做防护。如果 FastAPI 没安装，这些模块会在 import 时爆炸，而不是优雅降级。

---

### 🟡 5.4 配置默认值分散在多处

**问题:** `src/config.py` 的 `DEFAULT_LLM_PROVIDER` 默认是 `"deepseek"`，但 `render.yaml` 中有 `DEFAULT_LLM_PROVIDER=kimi`，CLAUDE.md 也记录了其他默认值在不同地方不一致的历史。虽然现在 canonical 是 deepseek，但如果有人 reference 旧文档会配置错误。

**建议:** config.py 应该是唯一真实来源（SSOT）。在 config.py 顶部加注释标明"所有默认值的唯一来源，其他文件不应覆写"，并做 CI lint 检查 render.yaml / docker-compose 中的 DEFAULT_LLM_PROVIDER 值与 config.py 一致。

---

### 🟢 5.5 做得不错的部分

- CLAUDE.md 非常详细，对 AI 辅助开发很有用
- eslint `no-restricted-syntax` 规则禁止 demo key 硬编码
- 较完善的 Pydantic 模型 + TypedDict state
- `_validate_label()` 正则防御路径穿越

---

## 六、前端质量 (Frontend Quality)

### 🟡 6.1 localStorage + cookie 双写，但无加密

**问题:** `web/src/components/api.ts` 中 API key 存储在 localStorage 和 cookie 中，明文。这是标准做法，但如果浏览器有 XSS 漏洞，API key 会被盗。

**建议:** 考虑 HttpOnly cookie（后端设置，前端不可读）或 token 轮换机制。当前的 `SameSite=Lax` 已经减少了 CSRF 风险。

---

### 🟡 6.2 Zustand Store 无持久化

**问题:** 三个 Zustand store（`useAppStore`, `usePipelineStore`, `useExpertStore`）在页面刷新后全部丢失。用户刷新页面后：
- 回到 home 页面
- 丢失正在运行的 pipeline 进度
- 丢失已选择的场景和模式

**建议:** 使用 `zustand/middleware` 的 `persist` 中间件，将关键状态（activeScene, mode, pipelineMode）持久化到 localStorage。

---

### 🟡 6.3 前端没有全局错误边界

Next.js App Router 中缺少 error.tsx 或 global error boundary。如果某个 React 组件渲染崩溃，整个页面可能会白屏而非显示友好的错误 UI。

---

### 🟡 6.4 日志函数 `logStateChange` 在生产环境不打 log

**问题:** `web/src/components/api.ts` 中 `logStateChange` 的实现可能在生产环境被 tree-shake 或静默失败。Zustand store 中的 `loggedSet` 包装器在生产环境仍会执行 state 比较，虽然是 O(1) 但每个 state 变化都触发。

**建议:** 生产环境关闭 state change logging，仅 dev 环境启用。

---

### 🟢 6.5 前端做得不错的

- Warm Light Professional Theme 翻转执行得干净
- i18n 架构（zh-CN/en）设计合理
- `apiFetch()` 封装统一了 HTTP 调用
- MediaPreviewModal 弹窗预览体验一致
- Portfolio thumbnail poster 预生成，避免 `<video preload="metadata">` 的 337 个并行请求

---

## 七、DevOps & 部署 (DevOps & Deployment)

### 🔴 7.1 数据库迁移策略存在缺口

**问题:** Alembic migration `1efc41794d64` 添加了 `video_metrics` 表到 PG，但 Docker Compose 启动时用的是 `src/storage/migrations/001_init.sql`（不包含 `video_metrics`）。也就是说：

- Docker Compose 启动 → SQL init script 跑 → 无 video_metrics 表
- 需要手动 `alembic upgrade head` → 补齐 video_metrics
- 如果某次重启后 PG volume 丢失但 SQLite 还在，数据会不一致

CLAUDE.md 已记录此问题，但未解决。

**建议:** 统一使用 Alembic 做所有迁移。Docker Compose 启动时自动跑 `alembic upgrade head`（在 backend entrypoint 或 docker-compose command 中）。

---

### 🟡 7.2 前端 Docker 部署使用 bind mount 源代码

**问题:** `docker-compose.prod.yml:81-83`：
```yaml
volumes:
  - ../../web/.next/standalone:/app
  - ../../web/public:/app/public
  - ../../web/.next/static:/app/.next/static
```

这是"在 host 上 build，在容器中 run"的模式。优点是 container image 小，缺点是：
- host 上的 Node 版本必须与 container 兼容
- 部署脚本必须记得先 `npm ci && npm run build`
- `.next` 目录必须在 host 上存在

**建议:** 使用 multi-stage Docker build，将 Next.js build 放在 Dockerfile 中。`node:22-alpine` → build stage → production stage 是成熟模式。

---

### 🟡 7.3 环境变量管理分散

- `.env.example` — 本地开发模板
- `deploy/lighthouse/.env.prod` — 生产环境（gitignored）
- `render.yaml` — Render 部署环境
- `src/config.py` — 默认值 fallback

四层 fallback 链：request contextvars → .env → config.py default → hardcoded。如果某层被意外覆盖，很难追溯。

**建议:** 用 `pydantic-settings` 做环境变量管理，集中定义 schema、验证、和默认值，去掉 config.py 中的手动 `os.getenv`。

---

### 🟡 7.4 Backend healthcheck 依赖 Python / urllib

**问题:** `docker-compose.prod.yml:31`:
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8001/health')\""]
```

每次 healthcheck 都启动一个 Python 进程。更高效的方式是用 `wget`（rendering 和 frontend 的 healthcheck 已经这样做了）。

**建议:** 改为 `wget -qO- http://localhost:8001/health || exit 1`。

---

### 🟢 7.5 DevOps 做得不错的

- `restart: on-failure:5` 防止无限重启（2026-05-05 事故后改进）
- backend_output volume 以 `:ro` 挂载到 nginx，安全性好
- nginx `proxy_read_timeout 1500s` 支持长管线
- 有 deploy.sh 脚本

---

## 八、产品与用户体验 (Product & UX)

### 🔴 8.1 管线失败时用户得不到有效反馈

**问题:** 当 POYO 内容审核拒绝 prompt（特别是母婴类敏感词）时：
- 后端重试一次，如果仍失败，返回 generic error
- 用户看到的是 "Internal server error [trace: xxxxxxxx]"
- 用户不知道是 prompt 问题、API key 问题还是系统 bug

**建议:** 错误分类器 (`error_classifier.py`) 应区分 "用户可操作的错误" 和 "系统错误"：
- 用户可操作: prompt 被拒 → "Please rephrase your prompt to avoid restricted terms"
- 系统错误: API key 无效 / 外部 API 宕机 → 显示具体原因 + 建议重试时间

前端也应展示分类后的错误，而非 raw trace。

---

### 🟡 8.2 没有任务取消机制

**问题:** 一旦启动 pipeline（特别是 S5 的 20-30 分钟 VLOG 生成），没有取消按钮。用户关闭页面后后端继续跑，消耗 API 配额但没人会看结果。

**建议:**
- 前端加 Cancel 按钮
- 后端在关键步骤间检查 `cancellation_requested` flag
- 超时自动取消（如 30 分钟无进展）

---

### 🟡 8.3 Portfolio / Footage 页面缺少搜索和分页

当前 `?limit=50` 只取前 50 个，但没有翻页。素材 > 50 条时用户无法浏览全部。也没有搜索/过滤（仅在 Materials 子 tab 有 视频/图片/音频 分类）。

---

### 🟡 8.4 S5 VLOG 场景的用户输入为自由文本，无引导

`story_description: str — user's story direction (max 300 chars)` — 用户不知道应该写什么。没有模板、示例或提示。

**建议:** 加 3-5 个 story starter 模板（如 "Morning routine with baby", "Product unboxing and first use"），加内联提示。

---

## 九、测试覆盖 (Test Coverage)

### 🟡 9.1 测试分布不均衡

CLAUDE.md 声称 30+ test files, 380+ tests，但：
- 前端测试很少（用 Vitest + jsdom，但实际 test 文件很少）
- 无集成测试覆盖 Docker Compose 全栈
- 无端到端测试覆盖前端→后端→API 的完整用户旅程
- `timed_node` 装饰器的 async 行为似乎未被测试

**建议:** 加关键路径的 e2e 测试（Playwright 或 Selenium），至少覆盖：首页加载 → 场景选择 → S1 启动 → 查看结果。

---

### 🟢 9.2 测试基础设施较好

- GitHub Actions CI（push/PR）
- ruff lint + pytest (3.11 + 3.12) + coverage
- Makefile 提供统一的 test/lint/ci 入口

---

## 十、优先级排序

按"影响 × 可能性 × 修复成本"排序的前 10 个问题：

| 优先级 | ID | 问题 | 风险等级 | 修复成本 |
|--------|-----|------|----------|----------|
| P0 | 2.1 | API Key 无租户隔离 | 🔴 高危 | 高 |
| P0 | 1.1 | 两套管线系统并存 | 🔴 高危 | 高 |
| P1 | 1.2 | 双重持久化不一致窗口 | 🔴 高危 | 中 |
| P1 | 3.2 | POYO 无 contextvars 隔离 | 🟡 中危 | 低 |
| P1 | 7.1 | 数据库迁移缺口 | 🔴 高危 | 低 |
| P1 | 8.1 | 管线失败无有效用户反馈 | 🔴 高危 | 中 |
| P2 | 1.3 | 场景管线不均衡 | 🟡 中危 | 高 |
| P2 | 3.1 | timed_node 无 async 支持 | 🟡 中危 | 低 |
| P2 | 4.1 | LLMClient cache 不感知 timeout | 🟡 中危 | 低 |
| P2 | 8.2 | 无任务取消机制 | 🟡 中危 | 中 |

---

## 十一、反直觉洞察

### Insight 1: "多租户安全"的最大威胁不是外部攻击者，而是合法用户 A 误看到用户 B 的数据

当前架构下，如果用户 A 在浏览器 console 改了 localStorage 中的 `label` 参数，可能拉取到其他用户的 pipeline state（因为 API 没有 `WHERE tenant_id = ...` 过滤）。这不是安全漏洞——用户需要知道 label——但在操作上非常脆弱。

### Insight 2: 门面最好的代码可能是最脆弱的

`timed_node` 装饰器写得精致，但它对所有 16 个 async 节点无效——时间测量不准确，错误收集重复（因为 `_wrap_node_with_error_handling` 也做错误收集）。两个装饰器的叠加产生了静默降级而非明确的错误。

### Insight 3: "有文档记录的问题"不等于"不需要修复的问题"

CLAUDE.md 记录了 11 个"已知未验证路径"和"已知功能缺陷"。记录是好的，但如果所有团队成员都默认"CLAUDE 说还在，那就不修"，问题会累积。建议：给每个已知问题加 `scheduled_fix_date` 或 `will_not_fix` 标签。

### Insight 4: 最快的性能优化不是加缓存，而是删掉不用的路径

Redis/Celery 声明在 requirements.txt 但从未运行。`DEFAULT_LLM_PROVIDER` 的 "anthropic"/"kimi" fallback 路径在 config.py 中仍有代码但实际不用。这些"可能有用的代码"增加了认知负荷和 import 依赖。

---

## 结论

这是一个在核心功能上运行良好、但在工程健壮性上有显著技术债的项目。当前的 B/B+ 评级意味着它适合 1-3 个用户的 demo 或 pilot 使用，但要在生产环境中稳定服务 10+ 用户，需要优先解决：

1. 多租户安全隔离
2. 管线系统统一
3. 数据库迁移一致性
4. 用户可见的错误反馈
5. 跨 API client 的 contextvars 一致性

这五个问题的修复成本合计约 2-3 周（一个工程师全职），但能为后续的规模化运营铺平道路。
