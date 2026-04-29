# AI_vedio Phase 2 执行计划 — PG持久化 + 系统加固

> 日期: 2026-04-27
> 目标: 完成 PostgreSQL 持久化、系统脆弱点修复、前端生产优化
> 执行方式: 多 Agent 并行

---

## 一、计划总览

| 任务 | 优先级 | 预计时间 | 负责人 | 依赖 |
|------|--------|----------|--------|------|
| **A: PG 持久化** | P0 | 3-4 天 | Backend Core Agent | Docker Desktop 已就绪 |
| **B: S4 素材分析增强** | P1 | 2 天 | Backend Skill Agent | PG 完成后更佳 |
| **C: 前端生产优化** | P1 | 1-2 天 | Frontend Agent | 无 |
| **D: 网红管理 Web UI** | P2 | 2 天 | Frontend Agent | PG 完成后 |
| **E: 系统脆弱点修复** | P0 | 0.5 天 | Auditor Agent | 诊断完成后 |

---

## 二、任务 A: PG 持久化（P0 — 基础设施）

### 目标
将内存 dict 和文件系统存储替换为 PostgreSQL，实现数据持久化和多人协作。

### 新建文件

```
src/storage/__init__.py           # 存储包初始化
src/storage/db.py                 # asyncpg 连接池管理
src/storage/models.py             # SQLAlchemy / 原始 SQL schema
src/storage/repository.py         # Repository pattern CRUD
src/storage/migrations/001_init.sql # 初始建表脚本
docker-compose.yml                # Docker Compose 配置（PG + 可选后端）
```

### 修改文件

```
src/api.py                        # 替换 _active_threads 为 DB repository
src/pipeline/state_manager.py     # 增加 PG 存储后端（保留文件系统作为 fallback）
src/graph/pipeline.py             # pipeline 状态读写改为 DB
```

### Schema 设计

```sql
-- threads: LangGraph pipeline 线程
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(16) UNIQUE NOT NULL,
    state JSONB NOT NULL,
    current_step VARCHAR(50),
    pipeline_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- pipeline_states: S1 step-by-step 状态
CREATE TABLE pipeline_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label VARCHAR(64) UNIQUE NOT NULL,
    scenario VARCHAR(32),
    config JSONB,
    steps JSONB,
    current_step VARCHAR(50),
    mode VARCHAR(16),
    errors JSONB DEFAULT '[]',
    media_synthesis_errors JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- brand_packages: 品牌资产包
CREATE TABLE brand_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    brand_guidelines JSONB,
    assets JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- influencers: 网红/员工
CREATE TABLE influencers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    platform VARCHAR(32),
    profile JSONB,
    contact_info JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- publish_logs: 分发发布记录
CREATE TABLE publish_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(32) NOT NULL,
    post_id VARCHAR(128),
    content JSONB,
    status VARCHAR(32),
    url TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 执行步骤

1. **Docker Compose 配置** (0.5h)
   - 创建 `docker-compose.yml`，定义 postgres 服务
   - 使用 postgres:16-alpine 镜像
   - 挂载数据卷到 `./data/postgres`
   - 环境变量: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

2. **DB 连接层** (0.5h)
   - `src/storage/db.py`: asyncpg 连接池，连接字符串从 `.env` 读取
   - 提供 `get_pool()` 和 `close_pool()` 函数
   - 连接失败时回退到 SQLite（开发模式）

3. **Repository 层** (1h)
   - `src/storage/repository.py`: ThreadRepository, PipelineStateRepository, BrandPackageRepository, InfluencerRepository, PublishLogRepository
   - 每个 Repository 提供: `create()`, `get_by_id()`, `update()`, `delete()`, `list_all()`
   - 使用 asyncpg 原生 SQL，不引入 ORM（减少依赖）

4. **API 层改造** (1h)
   - `src/api.py`: `_active_threads` 改为 ThreadRepository
   - `fetchState` 从 DB 读取
   - 保持内存缓存作为热缓存（读取时先查内存，miss 再查 DB）

5. **StateManager 改造** (0.5h)
   - `state_manager.py`: 保留文件系统存储作为 fallback
   - 当 `USE_PG=true` 时，优先写入 PG
   - 提供 `migrate_from_fs_to_pg()` 工具函数

6. **冒烟测试** (0.5h)
   - 启动 Docker Compose
   - 验证前后端正常连接
   - 跑一个完整的 S1 pipeline，确认状态持久化到 PG
   - 重启后端，确认状态不丢失

---

## 三、任务 B: S4 素材分析增强（P1）

### 目标
增强实拍素材上传后的 AI 分析能力：场景检测、质量评分、标签提取。

### 新建文件

```
src/skills/footage_analyzer.py     # 素材分析 Skill
src/skills/footage_prompts.py      # Prompt templates
tests/test_footage_analyzer.py     # 测试
```

### 修改文件

```
src/pipeline/s4_live_shoot_pipeline.py  # 加入 footage_analyzer step
src/api.py                              # 素材上传后触发异步分析
```

### 分析维度

| 维度 | 输出 | 用途 |
|------|------|------|
| 场景类型 | product_demo / testimonial / bts / unboxing | 脚本匹配 |
| 画面质量 | 1-10 分 | 是否可用 |
| 光照评分 | 1-10 分 | 后期提示 |
| 主体清晰度 | 1-10 分 | 是否适合 AI 生成 |
| 自动标签 | ["产品特写", "人物出镜", "室外", "绿色背景"] | 素材库搜索 |
| 时长 | 秒数 | 脚本时序匹配 |
| 关键帧时间戳 | [0.5s, 2.3s, 5.1s] | 剪辑点建议 |

### 执行步骤

1. **Prompt 设计** (0.5h)
   - 针对视频帧截图的多模态分析 prompt
   - 使用 GPT-4o Vision API（通过 poyo.ai 统一接口）

2. **Skill 实现** (0.5h)
   - `footage_analyzer.py`: 接收视频路径，抽帧，调用 vision API，返回结构化分析结果
   - 抽帧策略：每秒 1 帧，或基于场景变化检测

3. **Pipeline 集成** (0.5h)
   - S4 pipeline 第一步改为 `footage_analyzer`
   - 分析结果传给 script_writer 作为上下文

4. **AssetStorage 扩展** (0.5h)
   - `search_by_tags()` 方法
   - `analyze()` 方法保存分析结果到素材元数据

---

## 四、任务 C: 前端生产优化（P1）

### 目标
让前端可以构建为静态文件并部署，不再依赖 dev server。

### 新建文件

```
web/Dockerfile                    # 多阶段构建
web/nginx.conf                    # Nginx 配置
```

### 修改文件

```
web/next.config.js                # 添加 output: 'export' 或 standalone
web/package.json                  # 添加 build 脚本优化
```

### 执行步骤

1. **Next.js 构建配置** (0.5h)
   - `next.config.js`: `output: 'standalone'` 或 `output: 'export'`
   - 处理 API routes 在静态导出时的兼容性问题（如果有）

2. **Docker 多阶段构建** (0.5h)
   - Stage 1: node:20-alpine 构建 Next.js
   - Stage 2: nginx:alpine 服务静态文件
   - 或者使用 Next.js 自带服务器（standalone 模式）

3. **Nginx 配置** (0.5h)
   - 反向代理 `/api/*` 到后端 8001
   - 静态文件缓存
   - gzip 压缩
   - SPA fallback（404 → index.html）

4. **docker-compose.yml 扩展** (0.5h)
   - 添加 `web` 服务
   - 添加 `nginx` 服务（可选，如果前端和后端共用同一个 compose）
   - 配置网络互通

---

## 五、任务 D: 网红管理 Web UI（P2）

### 目标
提供网红/员工的 CRUD 管理界面，支持 CSV 批量导入。

### 新建文件

```
web/src/app/influencers/page.tsx       # 网红列表页
web/src/components/InfluencerForm.tsx   # 新增/编辑表单
web/src/components/InfluencerTable.tsx  # 表格组件
web/src/components/CsvUploader.tsx      # CSV 批量导入
```

### 修改文件

```
web/src/components/api.ts              # +influencer API 函数
src/api.py                             # +influencer CRUD endpoints
```

### 执行步骤

1. **后端 API** (0.5h)
   - `GET /api/influencers` — 列表
   - `POST /api/influencers` — 创建
   - `PUT /api/influencers/{id}` — 更新
   - `DELETE /api/influencers/{id}` — 删除
   - `POST /api/influencers/import` — CSV 批量导入

2. **前端页面** (1h)
   - 列表页：表格展示，搜索过滤
   - 表单：姓名、平台、粉丝数、风格标签、联系方式
   - CSV 导入：拖拽上传，预览，确认导入

3. **与 Pipeline 集成** (0.5h)
   - SceneSelector 中可以选择已保存的网红
   - S3 Influencer Remix 时自动引用网红 profile

---

## 六、任务 E: 系统脆弱点修复（P0）

基于脆弱点诊断 Agent 的发现，修复以下已知问题：

| # | 脆弱点 | 影响 | 修复方式 |
|---|--------|------|----------|
| 1 | 文件上传无大小限制 | DoS 攻击 | 限制 100MB |
| 2 | API 无输入验证 | 注入风险 | Pydantic 模型校验 |
| 3 | CORS allow_origins=["*"] | 安全风险 | 改为前端域名 |
| 4 | 密码/密钥明文存储在 .env | 泄露风险 | 使用环境变量注入 |
| 5 | 无请求限流 | 资源耗尽 | Token bucket 限流 |
| 6 | 错误信息暴露给前端 | 信息泄露 | 统一错误码 |
| 7 | 文件路径遍历风险 | 任意文件读取 | Path 校验 |

---

## 七、Agent 分工

| Agent | 任务 | 范围 |
|-------|------|------|
| **Backend Core** | A: PG 持久化 | `src/storage/`, `docker-compose.yml`, `src/api.py` |
| **Backend Skill** | B: S4 增强 | `src/skills/footage_analyzer.py`, `src/pipeline/s4_*.py` |
| **Frontend** | C + D | `web/Dockerfile`, `web/nginx.conf`, `web/src/app/influencers/` |
| **Auditor** | E: 脆弱点修复 | 全代码库扫描 + 修复 |
| **Planner** | 计划制定 | 本文档 + 协调 |

---

## 八、验收标准

### A: PG 持久化
- [ ] `docker-compose up -d postgres` 成功启动
- [ ] S1 全自动 pipeline 完成后，数据在 PG 中可查
- [ ] 重启后端，`GET /pipeline/{thread_id}/state` 仍能返回正确状态
- [ ] S1 逐步模式编辑的内容重启后不丢失

### B: S4 素材分析
- [ ] 上传视频后自动触发分析
- [ ] 分析结果包含场景类型、质量评分、标签
- [ ] S4 生成的脚本能引用分析结果中的素材标签

### C: 前端生产优化
- [ ] `docker build -t ai-video-web ./web` 成功构建
- [ ] `docker-compose up` 同时启动前端 + 后端 + PG
- [ ] 浏览器访问 `http://localhost` 可正常使用所有功能

### D: 网红管理
- [ ] 可新增/编辑/删除网红
- [ ] 可 CSV 批量导入
- [ ] SceneSelector 可选择已保存网红

### E: 脆弱点修复
- [ ] 文件上传限制 100MB
- [ ] CORS 只允许 `http://localhost:3000`
- [ ] 错误信息不暴露内部堆栈

---

*计划制定时间: 2026-04-27*
*执行开始: 用户确认后立即启动*
