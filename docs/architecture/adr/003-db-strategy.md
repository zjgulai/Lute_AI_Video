---
name: adr-003-db-strategy
description: ADR #003 文档，记录"PostgreSQL 主 + SQLite 回退"数据库策略的决策依据、fail-fast 触发条件、迁移工具链与回退路径。当评估持久化需求、调试连接池问题、添加新表、或决定本地开发是否需要起 PG 时使用。
---

# ADR #003 — PostgreSQL First, SQLite Fallback

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-05-11（追溯记录 P0-E LangGraph checkpoint 持久化决策） |
| **决策者** | 工程团队 |
| **影响** | 部署 dependency、本地开发体验、CI 矩阵、迁移流程 |

## 一、Context

系统的持久化需求分两层：

1. **业务数据**（threads、tenants、api_keys、admin_sessions、video_metrics、publish_logs、audit_logs）：CRUD 频繁，并发读写，需要事务，**生产必须 Postgres**。
2. **LangGraph checkpoint**（pipeline 中间状态，HITL 等待用户审批时持久化）：跨重启恢复 pipeline，**生产必须 Postgres**（PostgresSaver），否则容器重启所有 paused pipeline 全部丢失。

但本地开发 + CI 跑测试时：
- 起 docker compose 总是慢，开发者抗拒
- CI runner 起 PG 服务也要 30s+
- 大部分单测/集成测不需要真 PG 行为，只要个能 commit/rollback 的 SQL store

如果**强制只支持 PG**，开发体验差；如果**默认 SQLite**，生产要么没 PG 可用、要么静默 fall back 到 SQLite，发现问题时已经丢数据。

## 二、Decision

**PG 是 first-class，SQLite 是开发/CI fallback，生产模式 fail-fast**。

| 场景 | DB 后端 | 触发条件 |
|---|---|---|
| 生产（设置 `DATABASE_URL=postgresql://...`） | PostgreSQL | env 里有 `DATABASE_URL` |
| 本地 dev（无 `DATABASE_URL`） | SQLite at `output/ai_video.db` | env 里没 `DATABASE_URL` |
| CI 跑 pytest | SQLite（除非 workflow 显式起 PG） | 默认 |
| LangGraph checkpoint | PostgresSaver only | `db_url` 传给 build_pipeline |

**Fail-fast 条款**：
- 如果设置了 `DATABASE_URL` 但连接失败 → 启动直接报错退出，**不静默 fallback 到 SQLite**
- LangGraph 没有 PostgresSaver 包时 → `src/graph/pipeline.py:251` 抛 ModuleNotFoundError，不退化为 MemorySaver
- 这两条是 **P0-E** 修复的核心：之前的「静默退化」导致过生产事故

## 三、当前实现

### 业务数据层（[`src/storage/db.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/db.py)）
```
get_db_url() 读 env → 如果有 → asyncpg pool（min=1, max=10）
                  → 如果没 → SQLite at VIDEO_OUTPUT_DIR/ai_video.db
                  → SQLite 启动时执行 src/storage/migrations/001_init.sql
check_pg_health() → SELECT 1 + 校验关键表存在
is_pg_available() → 全局 flag，让 router 在 PG 不健康时跳过 PG 调用
```

### LangGraph checkpoint（[`src/graph/pipeline.py:212`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/pipeline.py#L212)）
```python
def build_pipeline(checkpointer=None, db_url=None):
    """
    1. No arguments        → MemorySaver (dev/test, in-memory)
    2. db_url + psycopg    → PostgresSaver (production, persistent)
    3. db_url 但连不上 PG  → 抛异常，不退化为 MemorySaver
    """
```

### 迁移工具链
- **业务表**：Alembic in [`migrations/`](file:///Users/pray/project/hermes_evo/AI_vedio/migrations)，生产部署前 `alembic upgrade head`
- **SQLite 初始化**：[`src/storage/migrations/001_init.sql`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/migrations/001_init.sql)，启动时自动加载
- **已知断层**：`video_metrics` 表只在 Alembic `1efc41794d64` 里有，`001_init.sql` 没有；fresh `docker compose up` 在没跑 alembic 之前 SQLite 没这张表。详见 AGENTS.md "Known Gaps"。

## 四、Consequences

### 好处
- **本地开发零依赖**：clone + `pip install` + `uvicorn` 直接跑，不用 docker compose
- **CI 快**：pytest 不起 PG，全套 800+ 测试 8 分钟以内
- **生产严格**：fail-fast 保证「该有 PG 时一定有」，不会半夜偷偷退化丢数据
- **迁移路径清晰**：本地用完 SQLite，部署前 alembic 一键迁移到 PG

### 代价
- **行为差异**：SQLite 的 `INTEGER PRIMARY KEY AUTOINCREMENT` vs PG 的 `SERIAL`、JSON 字段、DATETIME 时区处理都有微妙不同，必须靠抽象层 + 测试覆盖
- **双套 SQL**：[`src/storage/migrations/001_init.sql`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/migrations/001_init.sql) 给 SQLite，Alembic 给 PG，**容易漂移**（已经发生过 `video_metrics` 漂移事件）
- **新表流程繁琐**：加表要同时改 alembic + 001_init.sql + repository CRUD 函数
- **测试覆盖压力**：repository 层必须有 PG-first / SQLite-fallback 双路径的单测

## 五、Alternatives Considered

### A. 强制只支持 PG（删 SQLite fallback）
- 本地 dev 必须起 docker compose 才能跑后端 → 接受度低
- CI 慢，且每个 fork 仓库都要配置 PG service
- **拒绝**：DX 太差

### B. 强制只支持 SQLite（删 PG）
- 并发性能差，多 worker 写入会锁
- LangGraph PostgresSaver 没有 SQLite 等价物（社区有人写过 `langgraph-checkpoint-sqlite` 但不官方维护）
- **拒绝**：生产不可接受

### C. 用 Supabase（managed PG + 内置 auth）
- 把整套部署绑死在 Supabase 上
- 自托管能力（Tencent Lighthouse / 国内合规）丧失
- **拒绝**：vendor lock-in

### D. 静默退化（设了 `DATABASE_URL` 但 PG 不可达就跳回 SQLite）
- **历史教训**：2026-04 之前是这么做的，导致生产 PG 误删后系统继续 "正常运行" 写到 SQLite，直到 24h 后才发现数据全丢
- 这是 P0-E 修复的反面教材
- **拒绝**：永远不允许

## 六、Rollback Plan

如果未来需要换 DB（比如迁移到 CockroachDB / TiDB / Spanner）：
1. **抽象层是 [`src/storage/db.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/db.py) + [`src/storage/repository.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/repository.py)**，理论上换实现即可
2. **Alembic 迁移文件可重用**（CRDB/TiDB 都兼容 PG 协议）
3. **LangGraph checkpoint 需要等待社区适配**（langgraph-checkpoint-cockroach 是否存在）

如果未来需要彻底删 SQLite fallback：
1. 在所有 dev / CI 文档里强制要求起 PG（最好用 `services` 在 GitHub Actions 跑）
2. 删 SQLite 路径 + 简化 [`src/storage/db.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/db.py)
3. **不建议**：DX 损失大于收益

## 七、相关代码

- [`src/storage/db.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/db.py) — 双路径 connection 管理
- [`src/storage/repository.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/repository.py) — ThreadRepository / PipelineStateRepository
- [`src/storage/metrics_repository.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/metrics_repository.py) — PG-first / SQLite-fallback 双路径示范
- [`src/graph/pipeline.py:212`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/pipeline.py#L212) — checkpoint fail-fast
- [`src/storage/migrations/001_init.sql`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/migrations/001_init.sql) — SQLite 初始化
- [`migrations/alembic/versions/`](file:///Users/pray/project/hermes_evo/AI_vedio/migrations/alembic/versions) — PG 迁移
