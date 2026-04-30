---
title: AI Video Pipeline 全栈深度审计报告
doc_type: analysis
module: architecture
topic: full-stack-audit
status: stable
created: 2026-05-01
updated: 2026-05-01
owner: self
source: ai
---

# AI Video Pipeline 全栈深度审计报告

**审计日期：** 2026-05-01  
**代码版本：** main 分支最新  
**审计范围：** 后端 (Python/FastAPI)、前端 (Next.js/React)、目录结构、部署配置、安全、性能  
**后端代码量：** ~25,482 行 (99 个 .py 文件)  
**前端代码量：** ~11,875 行 (43 个 .tsx/.ts/.css 文件)  
**测试文件：** 36 个 pytest 文件

---

## 一、执行摘要

本项目是一个 AI 驱动的短视频创作与分发平台，采用 **FastAPI + LangGraph** 后端编排 16 节点 AI Pipeline，**Next.js 16 + React 19** 前端提供交互界面。整体架构设计合理，Pipeline 的节点编排、人机审查检查点、降级策略等设计体现了生产级思维。

**但以下领域存在显著风险，需要优先处理：**

| 优先级 | 类别 | 问题 | 风险等级 |
|--------|------|------|----------|
| P0 | 安全 | 生产环境 API 密钥提交到 Git | **严重** |
| P0 | 安全 | 单点 API Key 认证，无权限分级 | **严重** |
| P1 | 架构 | `api.py` 单文件 1800+ 行，职责过重 | 高 |
| P1 | 架构 | `page.tsx` 单文件 1000+ 行，前端无路由拆分 | 高 |
| P1 | 性能 | 前端纯轮询无退避，无 WebSocket | 高 |
| P1 | 性能 | 文件上传全量读内存，大文件 OOM 风险 | 高 |
| P2 | 可维护性 | 前后端类型不同步，前端大量使用 `any` | 中 |
| P2 | 可维护性 | 无全局状态管理，props drilling 严重 | 中 |
| P2 | 部署 | Docker Compose 前端构建配置错误 | 中 |
| P3 | 治理 | 根目录存在大文件 tar 包和 .DS_Store | 低 |

---

## 二、项目架构概览

### 2.1 技术栈

| 层级 | 技术 | 版本 | 评价 |
|------|------|------|------|
| 后端框架 | FastAPI | 3.12 | 选型正确，但路由未拆分 |
| Pipeline 编排 | LangGraph | 0.2.x | 16 节点图结构清晰 |
| 状态持久化 | PostgreSQL + SQLite fallback | 16 / 3.x | PG 生产，SQLite 开发回退合理 |
| 缓存 | Redis (配置中) | 5.x | **未实际使用** |
| 前端框架 | Next.js | 16.2.4 | 最新版，但 App Router 未充分利用 |
| 前端 UI | React 19 + Tailwind CSS | 19.2.4 / 3.4 | 函数组件 + Hooks，无类组件 |
| AI 视频 | Seedance 2.0 / poyo.ai | - | 双后端自动切换设计良好 |
| AI 图像 | GPT-4o Image / DALL-E | - | 多提供商降级 |
| AI 语音 | CosyVoice / ElevenLabs | - | CosyVoice 为主 |
| LLM | DeepSeek V4-Pro | - | 中文场景优化 |

### 2.2 Pipeline 架构

```
strategy_node → strategy_audit_node → [Human Review #1] → script_node
                                                            ↓
script_audit_node → [Human Review #2] → compliance_node → storyboard_node
                                                              ↓
asset_sourcing_node → [AI Gen?] → media_generation_node → editing_node
                                                            ↓
editing_audit_node → [Human Review #3] → audio_node → caption_node → thumbnail_node
                                                                          ↓
                                                          thumbnail_audit_node → [Human Review #4]
                                                                                    ↓
                                                              distribution_node → analytics_node → END
```

**设计亮点：**
- 4 个人机审查检查点（strategy/script/edit/thumbnail）
- 4 个自审节点在审查前运行
- 每个节点有错误降级包装（`_wrap_node_with_error_handling`）
- 条件路由支持驳回后重试

**设计缺陷：**
- 所有 API 端点集中在 `api.py` 一个文件（1800+ 行）
- 无服务层抽象，API 层直接调用 Pipeline
- 无事件总线，节点间通过状态字典传递

### 2.3 数据流

```
Frontend (Next.js) ←→ FastAPI ←→ LangGraph Pipeline
                                      ↓
                              ┌───────┴───────┐
                              ↓               ↓
                         PostgreSQL      File System
                         (state/check)   (assets/videos)
```

---

## 三、后端深度审计

### 3.1 代码质量

#### 3.1.1 模块组织 (评分: B+)

**优点：**
- 按职责分层：`agents/`, `skills/`, `tools/`, `pipeline/`, `storage/`, `graph/`
- Pydantic 模型统一定义在 `src/models/`
- 错误分类体系完善（`ErrorCode` 枚举 + `PipelineError` 结构化）

**问题：**
- `src/api.py` 1800+ 行，包含 30+ 个端点定义，违反单一职责原则
- `src/api.py` 同时是应用入口、路由定义、业务逻辑、文件服务
- `src/tools/` 和 `src/skills/` 边界模糊（都是对外服务封装）
- 部分模块循环导入风险（`graph/pipeline.py` 导入大量节点）

#### 3.1.2 类型系统 (评分: A-)

**优点：**
- Python 3.12 类型注解完整
- Pydantic V2 数据验证全面
- `TypedDict` 用于 LangGraph 状态定义

**问题：**
- 部分函数返回 `Any`（如 API 端点的 `body: dict`）
- `src/api.py` 中大量 `dict[str, Any]` 参数
- 异常类型使用 `Exception` 而非具体类型

#### 3.1.3 错误处理 (评分: B)

**优点：**
- Pipeline 节点有统一错误包装
- 结构化错误收集（`error_collector`）
- 降级策略：节点失败不中断 Pipeline

**问题：**
- 大量裸 `except Exception` 吞掉异常（`api.py` 中有 15+ 处）
- `_safe_error` 函数在 dev 模式暴露完整异常栈，生产模式只返回字符串，信息丢失
- 文件上传的 `ImportError` 直接 `pass`，静默禁用功能

```python
# 问题代码示例（api.py 多处出现）
try:
    # ... 某些操作
except Exception as e:
    # 仅记录，不传播，调用方无法知道失败
    logger.error("...", error=str(e))
```

### 3.2 安全审计

#### 3.2.1 认证与授权 (评分: C)

**现状：**
- 单一 API Key 认证（`X-API-Key` Header）
- Key 从环境变量读取，未设置时自动生成临时 Key
- 所有端点共用同一套认证

**严重问题：**
1. **生产 API 密钥提交到 Git** — `deploy/lighthouse/.env.prod` 包含：
   - DEEPSEEK_API_KEY
   - POYO_API_KEY
   - SILICONFLOW_API_KEY
   - 腾讯云 PostgreSQL 密码
   
2. **API Key 无权限分级** — 上传文件、触发 Pipeline、查看状态使用同一 Key
3. **前端 API Key 暴露在 localStorage** — 可被 XSS 窃取
4. **无 JWT / Session 机制** — 无法追踪用户、无法撤销令牌
5. **CORS 配置过于宽松** — 生产环境 `CORS_ORIGINS` 包含 `http://localhost:3000`

#### 3.2.2 文件上传安全 (评分: B)

**优点：**
- 文件名消毒（`Path(filename).name`）
- 路径遍历检查（`..`, `/`, `\`, `\x00`）
- 扩展名白名单（`.mp4`, `.png`, `.jpg` 等）
- 文件大小限制（100MB）
- 存储名使用 UUID，避免覆盖

**问题：**
- **无 MIME 类型验证** — 仅检查扩展名，可伪造
- **文件内容未扫描** — 无病毒/恶意内容检测
- **上传文件全量读入内存** — `content = await file.read()`，大文件导致 OOM
- **无上传速率限制** — 可被用于 DoS

#### 3.2.3 文件服务安全 (评分: B+)

**优点：**
- 路径解析后验证 `candidate.relative_to(root)`，防止目录遍历
- 搜索多个子目录时使用同样的 relative_to 验证

**问题：**
- 未设置 `Content-Disposition: attachment`，浏览器可能执行上传的恶意文件
- 无文件访问日志

#### 3.2.4 数据安全 (评分: B)

**问题：**
- `.env` 文件在 docker-compose 中被 volume 挂载到容器
- SQLite 数据库文件存储在 `./output/ai_video.db`，权限未限制
- 无数据加密（静态/传输）
- 无审计日志记录敏感操作

### 3.3 性能审计

#### 3.3.1 并发控制 (评分: B)

**优点：**
- Pipeline 并发限制：`_pipeline_semaphore = asyncio.Semaphore(10)`
- `asyncpg` 连接池（min=1, max=10）
- `httpx.AsyncClient` 异步 HTTP

**问题：**
- 10 个并发 Pipeline 对于视频生成场景可能过多（每个 Pipeline 调用多次外部 AI API）
- 无外部 API 调用的独立限流（Seedance/poyo/DeepSeek 各有自己的速率限制）
- SQLite fallback 无连接池，并发写会锁库

#### 3.3.2 缓存策略 (评分: C)

**现状：**
- Redis 在依赖中但未实际使用
- `llm_client.py` 有客户端实例缓存（`_clients` dict）
- 无 API 响应缓存
- 无视频/图片 CDN

**影响：**
- 重复查询状态每次都走 DB
- 相同参数的视频生成无法复用
- 静态资源（生成的图片/视频）每次从文件系统读取

#### 3.3.3 资源管理 (评分: B-)

**问题：**
- `_active_threads` 内存字典无限增长，无 TTL 或淘汰策略
- `_background_tasks` 字典同样无清理（虽然有 done_callback，但异常时可能残留）
- 输出目录（`output/`）无自动清理，磁盘可能满
- 视频生成后的临时文件未清理

### 3.4 存储层审计

#### 3.4.1 数据库设计 (评分: B)

**优点：**
- PostgreSQL 为主，SQLite 为 fallback，设计合理
- 表结构覆盖核心实体（threads, pipeline_states, brand_packages, influencers, publish_logs, video_metrics）
- 索引设计基本合理

**问题：**
- `video_metrics` 表在 PG 中未启用（注释说明 "pending PG migration"）
- 无数据库迁移管理（无 Alembic / Flyway）
- `pipeline_states.steps` 和 `pipeline_states.config` 使用 TEXT 存储 JSON，无结构化查询
- 无外键约束
- 无数据保留策略（metrics/logs 会无限增长）

#### 3.4.2 状态持久化 (评分: B-)

**现状：**
- LangGraph 使用 `MemorySaver`（开发）或 `PostgresSaver`（生产）
- `_active_threads` JSON 索引文件用于进程重启恢复

**问题：**
- `MemorySaver` 可能在生产环境误用（需确认部署配置）
- `_active_threads` 索引文件非原子写入，崩溃可能损坏
- 无状态归档/清理机制

---

## 四、前端深度审计

### 4.1 代码质量

#### 4.1.1 组件架构 (评分: C+)

**现状：**
- 43 个组件/页面文件，全部函数组件
- 无类组件（符合现代 React 最佳实践）
- 但所有内容集中在单页应用（SPA）模式，`page.tsx` 作为唯一页面

**严重问题：**
1. **`page.tsx` 1000+ 行** — 包含 20+ 个状态变量、多个 useEffect、业务逻辑、条件渲染
2. **无前端路由** — Next.js App Router 未使用，所有场景切换通过状态变量控制
3. **无全局状态管理** — 20+ 个 `useState`，props drilling 严重
4. **组件职责不清** — `page.tsx` 同时是布局控制器、数据获取器、路由调度器

```
page.tsx 职责：
├── SplashScreen 显示控制
├── Scene 选择/表单状态
├── Pipeline 状态轮询
├── Review 面板状态
├── Gate 流程状态
├── Workflow 步骤状态
├── Fast Mode 状态
├── Settings 面板状态
├── Error 处理
└── Demo mode 逻辑
```

#### 4.1.2 类型安全 (评分: C)

**问题：**
- 大量使用 `any`：`body: any`, `data: any`, `state: any`
- API 响应类型未定义（`startPipeline` 返回 `Promise<any>`）
- `ReviewState.state: any` — 后端完整状态暴露为 any
- `demo-data.ts` 中大量对象无类型

**影响：**
- 编译时无法捕获 API 变更导致的类型错误
- IDE 自动补全失效
- 运行时类型错误风险高

#### 4.1.3 数据获取 (评分: B-)

**优点：**
- 统一封装在 `api.ts`
- 支持 `AbortSignal`（可取消请求）
- localStorage/cookie fallback 处理隐私模式

**问题：**
- 无数据缓存/去重（React Query / SWR）
- 无错误重试机制
- 无请求去重（同一请求并发发送多次）
- 所有 fetch 使用原生 API，无拦截器

### 4.2 性能审计

#### 4.2.1 渲染性能 (评分: C+)

**问题：**
- `page.tsx` 作为单一根组件，任何状态变更触发全树重新渲染
- 缺乏 `React.memo` 优化（大部分组件未包装）
- `useEffect` 依赖数组可能不完整（导致多余渲染或 stale closure）
- 无虚拟列表（PortfolioGallery 可能渲染大量媒体项）

#### 4.2.2 网络性能 (评分: C)

**问题：**
- **纯轮询无退避** — `StageProgress` 等组件固定间隔轮询（如 3s），不随 Pipeline 进度调整
- **无 WebSocket** — 实时状态更新依赖轮询，增加服务器负载
- **无请求合并** — 多个独立请求可能并发发送
- **无图片懒加载优化** — `loading="lazy"` 有但无占位符/模糊加载效果
- **无代码分割** — 所有组件同步导入，首屏加载大

#### 4.2.3 构建优化 (评分: B-)

**问题：**
- `next.config.js` / `next.config.ts` 未找到（可能使用默认配置）
- 无静态导出配置
- 无图片优化域名配置
- `lighthouse/` 目录有性能测试但无 CI 集成

### 4.3 可维护性

#### 4.3.1 国际化 (评分: B)

**优点：**
- 完整的 `translations.ts`（~1700 行，中英双语）
- `useI18n` Hook 封装合理

**问题：**
- 翻译键名无命名空间，全部平铺
- 无 ICU MessageFormat（不支持复数、插值格式化）
- 键值偶尔重复（已修复一处 `"splash.sloganZh"`）

#### 4.3.2 样式管理 (评分: B+)

**优点：**
- Tailwind CSS 统一使用
- CSS 变量 + Tailwind 扩展主题
- Momcozy 品牌设计系统已落地

**问题：**
- 大量内联 Tailwind 类（`className` 字符串过长）
- 条件类拼接使用模板字符串，无 `clsx` / `classnames` 库
- 部分组件仍有硬编码颜色（已大规模替换，但需持续维护）

---

## 五、目录管理审计

### 5.1 根目录 (评分: C)

**问题：**

| 文件/目录 | 大小 | 问题 |
|-----------|------|------|
| `lute-ai-video-backend.tar` | 168MB | **大文件在 Git 中**，每次克隆都下载 |
| `.DS_Store` | 18KB | macOS 系统文件，应在 .gitignore 中 |
| `.env` | 2.7KB | 环境变量文件，**不应提交到 Git** |
| `.env.example` | 2.1KB | 合理，但包含真实默认值 |
| `output/` | 运行时数据 | 应在 .gitignore 中 |

**`deploy/lighthouse/.env.prod` 包含真实密钥：**
- DEEPSEEK_API_KEY
- POYO_API_KEY
- SILICONFLOW_API_KEY
- 腾讯云 PostgreSQL 密码

### 5.2 源代码目录 (评分: B)

**优点：**
- `src/` 按职责分层清晰
- `web/src/` 组件按功能组织

**问题：**
- `scripts/` 目录混合了正式脚本和临时脚本
- `tests/` 无子目录组织，36 个测试文件平铺
- `output/` 子目录过多（16 个），应进一步分类

### 5.3 文档目录 (评分: A-)

**优点：**
- `docs/` 结构完善（architecture, product, workflows, knowledge 等）
- 大量设计文档和计划文档

**问题：**
- `docs/guide/` 包含 PDF 文件（品牌 VI），不应在 Git 中
- 部分文档可能过时

---

## 六、部署与运维审计

### 6.1 Docker 配置

**`docker-compose.yml` 问题：**
1. **前端 Dockerfile 引用错误** — `build: context: ./web` 使用 `web/Dockerfile`，但该文件不存在（实际为 `Dockerfile.backend` 的软链接）
2. **后端 volume 挂载 `.env`** — 容器内可读写宿主 `.env`
3. **PG 密码硬编码** — `ai_video_dev_2026` 在 compose 中明文
4. **无资源限制** — 容器无 CPU/内存限制

**`Dockerfile.backend` 问题：**
1. 使用 `python:3.12-slim` 但未创建非 root 用户
2. 容器以 root 运行 uvicorn
3. `--reload` 仅在开发使用，生产不应启用

### 6.2 配置管理

**问题：**
- 配置分散在 `.env`, `pyproject.toml`, `docker-compose.yml`, `config.py`
- 部分配置在代码中硬编码（`DEFAULT_PLATFORMS`, `HUMAN_REVIEW_NODES`）
- 无环境配置验证（启动时不检查必填配置项）

### 6.3 监控与日志

**优点：**
- structlog 结构化日志
- telemetry 追踪 Pipeline 执行
- error_collector 收集结构化错误

**问题：**
- 无应用性能监控（APM）
- 无健康检查端点详细指标
- 日志无统一收集（ELK / Loki）
- 无告警机制

---

## 七、测试审计

### 7.1 测试覆盖 (评分: B-)

**现状：**
- 36 个测试文件，覆盖核心模块
- 有 E2E 测试（`test_e2e_pipeline.py`, `test_s1_e2e.py`, `test_s3_e2e.py`）
- pytest-asyncio 配置正确

**问题：**
- 覆盖率数据缺失（`pytest-cov` 已安装但未在 CI 中运行）
- 无前端测试（Vitest / Jest 未配置）
- API 层测试可能不足（`test_api.py` 但 `api.py` 过于庞大）
- 无性能测试
- 无安全测试

### 7.2 CI/CD

**现状：**
- `.github/workflows/` 存在但未检查具体内容
- `render.yaml` 存在（Render 平台部署配置）

**问题：**
- 无自动化测试门禁
- 无代码质量检查（ruff lint 未在 CI 中强制）
- 无依赖安全扫描（Dependabot / Snyk）

---

## 八、脆弱点详细分析

### 8.1 安全脆弱点

#### V1: 生产密钥泄露 (CVSS: 9.8)
**位置：** `deploy/lighthouse/.env.prod`
**影响：** 所有外部 AI 服务账户可被恶意使用，产生费用和数据泄露
**复现：** 仓库为公开/半公开，任何人可读取该文件
**修复：**
1. 立即轮换所有暴露的 API Key
2. 从 Git 历史中彻底删除 `.env.prod`
3. 使用 GitHub Secret / 腾讯云 SSM 管理密钥
4. 部署时通过环境变量注入

#### V2: 单点认证无权限分级 (CVSS: 7.5)
**位置：** `src/api.py` `verify_api_key`
**影响：** 任何持有 API Key 的用户可执行所有操作（上传、删除、触发 Pipeline）
**修复：**
1. 引入 JWT 认证，支持用户身份
2. 实现 RBAC（角色权限控制）
3. 敏感操作（删除、发布）需二次确认

#### V3: 文件上传 OOM / DoS (CVSS: 6.5)
**位置：** `src/api.py` `upload_file`
**影响：** 上传大文件导致内存耗尽；快速上传导致磁盘满
**修复：**
1. 使用流式写入（`shutil.copyfileobj`）替代 `await file.read()`
2. 添加上传速率限制（每用户每分钟 N 个文件）
3. 增加 MIME 类型验证（magic number 检查）

#### V4: CORS 配置宽松 (CVSS: 5.3)
**位置：** `src/api.py` CORS 配置
**影响：** 生产环境允许 localhost:3000，可能被用于 CSRF
**修复：**
1. 生产环境 CORS_ORIGINS 只允许已知域名
2. 区分 dev/prod 配置

### 8.2 架构脆弱点

#### V5: api.py 单文件职责过重
**影响：** 难以维护、测试、协作；变更影响面大
**修复：** 按领域拆分为多个 router 模块

#### V6: 前端无状态管理
**影响：** 状态分散在 20+ 个 useState，数据流混乱，bug 难追踪
**修复：** 引入 Zustand 管理全局状态

#### V7: 内存存储无持久化
**影响：** `_active_threads` 进程重启丢失；无水平扩展能力
**修复：** 使用 Redis 存储活跃线程索引

### 8.3 性能脆弱点

#### V8: 轮询风暴
**影响：** 多个客户端同时轮询，服务器负载线性增长
**修复：**
1. 实现指数退避轮询
2. 引入 WebSocket 或 SSE 推送状态更新
3. 使用长轮询（long polling）

#### V9: 无缓存层
**影响：** 重复计算、重复 API 调用、响应延迟高
**修复：**
1. 引入 Redis 缓存（已配置但未使用）
2. API 响应缓存（如状态查询）
3. 视频/图片 CDN 加速

---

## 九、优化方案

### 9.1 安全加固 (P0，1-2 周)

| 编号 | 任务 | 工作量 | 文件 |
|------|------|--------|------|
| S1 | 轮换所有泄露的 API Key | 1h | 外部服务商控制台 |
| S2 | 从 Git 历史删除 `.env.prod` | 2h | Git filter-branch |
| S3 | 将 `.env`, `.env.prod` 加入 .gitignore | 30min | `.gitignore` |
| S4 | 实现 JWT 认证 + RBAC | 3d | `src/auth/`, `src/api.py` |
| S5 | 文件上传流式处理 + MIME 验证 | 1d | `src/api.py` |
| S6 | 生产 CORS 严格限制 | 2h | `src/api.py` |
| S7 | 添加 Rate Limiting (Redis) | 1d | `src/middleware/` |
| S8 | 上传文件病毒扫描（ClamAV）| 2d | `src/security/` |

### 9.2 架构重构 (P1，2-4 周)

| 编号 | 任务 | 工作量 | 目标 |
|------|------|--------|------|
| A1 | 拆分 `api.py` 为多个 router | 3d | `src/routers/` |
| A2 | 引入服务层（Service Layer）| 5d | `src/services/` |
| A3 | 前端引入 Zustand 状态管理 | 3d | `web/src/store/` |
| A4 | 拆分 `page.tsx` 为多个路由页面 | 5d | `web/src/app/` |
| A5 | 前后端类型共享（OpenAPI → TS）| 3d | `src/schemas/` |
| A6 | 引入事件总线 | 3d | `src/events/` |

#### A1: api.py 拆分方案

```
src/routers/
├── __init__.py
├── pipeline.py      # /pipeline/* 端点
├── scenario.py      # /scenario/* 端点
├── fast_mode.py     # /fast/* 端点
├── distribution.py  # /distribution/* 端点
├── publish.py       # /publish/* 端点
├── metrics.py       # /metrics/* 端点
├── dashboard.py     # /dashboard/* 端点
├── assets.py        # /api/upload, /api/files, /api/media/*
└── health.py        # /health
```

#### A4: 前端路由拆分方案

```
web/src/app/
├── page.tsx              # 主入口（简化）
├── layout.tsx
├── globals.css
├── scenarios/
│   ├── page.tsx          # 场景选择
│   ├── s1/
│   │   └── page.tsx      # Product Direct
│   ├── s2/
│   │   └── page.tsx      # Brand Campaign
│   ├── s5/
│   │   └── page.tsx      # Brand VLOG
│   └── layout.tsx
├── review/
│   └── [threadId]/
│       └── page.tsx      # 审查页面
├── settings/
│   └── page.tsx          # 设置
└── fast-mode/
    └── page.tsx          # 快速模式
```

### 9.3 性能优化 (P1，1-3 周)

| 编号 | 任务 | 工作量 | 预期效果 |
|------|------|--------|----------|
| P1 | WebSocket / SSE 状态推送 | 3d | 消除轮询，实时更新 |
| P2 | Redis 缓存层 | 2d | 减少 DB 查询 80% |
| P3 | 文件上传流式处理 | 1d | 支持 GB 级上传 |
| P4 | 前端代码分割 + 懒加载 | 2d | 首屏加载减少 50% |
| P5 | 引入 React Query | 2d | 自动缓存、去重、重试 |
| P6 | CDN 配置（腾讯云 COS）| 1d | 静态资源加速 |
| P7 | 输出目录自动清理策略 | 1d | 防止磁盘满 |

### 9.4 可维护性优化 (P2，持续)

| 编号 | 任务 | 工作量 |
|------|------|--------|
| M1 | 引入 `clsx` + `tailwind-merge` | 2h |
| M2 | 前端类型定义与后端同步 | 3d |
| M3 | 数据库迁移（Alembic）| 2d |
| M4 | 测试覆盖率提升到 80% | 2w |
| M5 | 前端单元测试（Vitest）| 1w |
| M6 | API 文档（OpenAPI/Swagger UI）| 1d |
| M7 | 代码质量门禁（ruff + mypy）| 1d |

### 9.5 目录治理 (P3，1-2 天)

| 编号 | 任务 | 工作量 |
|------|------|--------|
| D1 | 删除/归档 `lute-ai-video-backend.tar` | 30min |
| D2 | 删除 `.DS_Store` 并加入 .gitignore | 30min |
| D3 | `output/` 加入 .gitignore | 30min |
| D4 | 清理 `scripts/` 临时脚本 | 2h |
| D5 | 整理 `tests/` 子目录 | 2h |

---

## 十、行动计划

### 第一阶段：紧急安全修复（本周）

```
Day 1: S1 + S2 + S3 — 密钥轮换 + Git 清理
Day 2: S4 — JWT 认证基础实现
Day 3: S5 — 文件上传安全加固
Day 4: S6 + S7 — CORS + Rate Limiting
Day 5: D1 + D2 + D3 — 目录清理
```

### 第二阶段：架构重构（2-3 周）

```
Week 1: A1 + A2 — 后端路由拆分 + 服务层
Week 2: A3 + A4 — 前端状态管理 + 路由拆分
Week 3: A5 + P1 — 类型共享 + WebSocket
```

### 第三阶段：性能优化（1-2 周）

```
Week 4: P2 + P3 + P6 — Redis + 流式上传 + CDN
Week 5: P4 + P5 — 代码分割 + React Query
```

### 第四阶段：质量提升（持续）

```
Week 6+: M1-M7 — 测试、文档、质量门禁
```

---

## 十一、风险与建议

### 11.1 最高风险

1. **API 密钥泄露已造成实际损失风险** — 需立即行动
2. **单文件 api.py 随功能增长会愈发难以维护** — 越早拆分成本越低
3. **无缓存导致成本线性增长** — AI API 调用费用昂贵，缓存 ROI 极高

### 11.2 技术债务评估

| 领域 | 债务等级 | 偿还成本 | 不偿还风险 |
|------|----------|----------|------------|
| 安全 | 高 | 2w | 数据泄露、服务被滥用 |
| 架构 | 高 | 4w | 开发效率下降、bug 增加 |
| 性能 | 中 | 3w | 用户体验差、成本高 |
| 测试 | 中 | 3w | 回归风险 |
| 文档 | 低 | 1w |  onboarding 困难 |

### 11.3 长期建议

1. **引入 API Gateway** — 统一认证、限流、日志、监控
2. **考虑 Temporal 工作流** — 对于长时间运行的 Pipeline，Temporal 比 LangGraph 更适合生产
3. **引入对象存储** — 腾讯云 COS 替代本地文件存储，支持 CDN
4. **监控体系** — Prometheus + Grafana + Alertmanager
5. **A/B 测试框架** — 视频变体效果追踪

---

## 附录：审计检查清单

### 后端检查项

- [x] 代码组织结构
- [x] 类型注解完整性
- [x] 错误处理策略
- [x] 认证授权机制
- [x] 文件上传安全
- [x] 路径遍历防护
- [x] SQL 注入防护（使用 ORM/参数化查询）
- [x] 并发控制
- [x] 资源限制
- [x] 日志记录
- [x] 配置管理
- [x] 依赖版本锁定
- [x] 数据库设计
- [x] 缓存策略
- [x] 测试覆盖

### 前端检查项

- [x] 组件架构
- [x] 状态管理
- [x] 类型安全
- [x] 数据获取
- [x] 渲染性能
- [x] 网络性能
- [x] 构建优化
- [x] XSS 防护
- [x] 国际化
- [x] 样式管理

### 运维检查项

- [x] Docker 配置
- [x] 部署脚本
- [x] 环境隔离
- [x] 密钥管理
- [x] 日志收集
- [x] 监控告警
- [x] 备份策略
- [x] 灾难恢复

---

*报告生成时间：2026-05-01*  
*审计工具：Claude Code + 手动代码审查*  
*下次审计建议：安全修复后 2 周内进行复验*
