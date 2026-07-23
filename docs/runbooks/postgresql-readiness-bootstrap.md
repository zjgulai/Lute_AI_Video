---
title: PostgreSQL Readiness and Bootstrap
doc_type: workflow
module: backend-operations
topic: postgresql-readiness-bootstrap
status: stable
created: 2026-07-22
updated: 2026-07-22
owner: self
source: human+ai
---

# PostgreSQL Readiness and Bootstrap

## 触发场景与影响范围

当 `/health/ready` 返回 503、required schema 不完整、Alembic revision 不在唯一 code head，
或需要初始化一个全新的 PostgreSQL 18 数据库时使用本 runbook。liveness 仍为 200 只代表
进程存活，不代表数据库、migration 或业务读写可用。

影响范围是 backend readiness、Docker rollout healthcheck 和所有依赖 PostgreSQL 的持久化
流程。预期诊断时间 2–5 分钟；空库 bootstrap 或历史库 migration 预期 5–30 分钟。

本 runbook 不授权生产变更。生产 apply 必须另有维护窗口、已验证备份/恢复、冻结 release
provenance 和精确 migration 授权。

## 相关代码

- `src/storage/db.py`
- `src/routers/health.py`
- `scripts/bootstrap_postgres.py`
- `scripts/deploy_alembic_gate.sh`
- `src/storage/migrations/001_init.sql`
- `migrations/alembic/versions/`
- `deploy/lighthouse/docker-compose.release.yml`

## 立即诊断

以下探针均为只读：

```bash
curl -fsS http://127.0.0.1:8001/health/live
curl -sS -o /tmp/ai-video-readiness.json -w '%{http_code}\n' \
  http://127.0.0.1:8001/health/ready
cd migrations && python -m alembic heads && python -m alembic current
```

期望只有一个 code head。`/health/ready` 的稳定数据库状态包括：

- `ready`：required tables/columns 完整且 current revision 等于唯一 head；
- `migration_not_ready`：revision missing、behind、multiple 或 code head 无法解析；
- `schema_not_ready`：revision 已在 head，但 required schema 不完整；
- `connection_error` / `not_initialized`：连接或启动配置不可用。

响应和日志不得包含 DSN、密码或原始数据库异常。

## 空库与历史库必须分流

最早的 Alembic revision `42eb2682e54b` 是“existing schema”基线且 `upgrade()` 为空，
因此一个真正空的数据库不能直接靠 `alembic upgrade head` 构建完整 schema。

### 已验证空库 PostgreSQL 18

仅当目标数据库通过人工确认没有 application tables，且已取得该环境的精确写授权时：

```bash
POSTGRES_BOOTSTRAP_AUTH=APPLY_EMPTY_DATABASE_BASELINE \
  DATABASE_URL='postgresql://USER@HOST/DATABASE' \
  python scripts/bootstrap_postgres.py
```

脚本在一个事务中完成：核验 PostgreSQL 主版本 18、拒绝非空 schema、执行 head 镜像
`001_init.sql`、核验 required tables/columns、stamp 唯一 Alembic head。任一步失败都会回滚，
且只输出稳定错误码。不得对历史库或不确定是否为空的库运行该命令。

### 历史数据库

历史库只走 release image 内的部署 gate：

```bash
ENVIRONMENT=production \
DEPLOY_MIGRATION_AUTH=APPLY_REVIEWED_RELEASE \
DATABASE_URL='postgresql://USER@HOST/DATABASE' \
scripts/deploy_alembic_gate.sh --apply
```

该 gate 必须先解析唯一 head/current，只有精确授权才执行 `alembic upgrade head`，然后再次
验证 current=head。应用 startup 和 `/health/ready` 永远不创建表、不 stamp、不 migration。

## 失败分类与响应

| 观察 | 含义 | 响应 |
|---|---|---|
| `bootstrap_authority_required` | 空库写权限未显式授予 | 停止，不连接数据库 |
| `bootstrap_postgres18_required` | 目标不是 PostgreSQL 18 | 停止，修正隔离目标 |
| `database_not_empty_use_alembic_upgrade` | 检测到历史/非空库 | 改走 reviewed Alembic gate |
| `database_has_alembic_lineage_use_upgrade` | 无应用表但已有 Alembic revision | 保留 lineage，改走历史库恢复/upgrade；禁止 stamp 覆盖 |
| `bootstrap_required_schema_missing` | baseline 镜像与 required contract 漂移 | 回滚事务，修复源码并重新评审 |
| `alembic_heads_failed` / `alembic_current_failed` / `alembic_upgrade_failed` | deploy gate 的 Alembic 子命令失败 | 保持服务关闭，使用受控数据库日志诊断；HTTP/标准输出不透传原始异常 |
| `behind_head` | 历史库需要 reviewed upgrade | 先验证备份/恢复，再申请 apply 授权 |
| `version_missing` / multiple revision | migration lineage 不可信 | 停止 rollout，人工恢复 lineage |
| `schema_not_ready` 且 `at_head` | schema 与 stamped revision 矛盾 | 停止服务，按数据事故处理，不重 stamp |

## 本地 disposable PostgreSQL 18 复验

只接受无密码的精确本机 DSN
`postgresql://postgres@127.0.0.1:55441/ai_video_bootstrap`：

```bash
DATABASE_BOOTSTRAP_PG18_DSN=postgresql://postgres@127.0.0.1:55441/ai_video_bootstrap \
PYTHON_DOTENV_DISABLED=1 PYTEST_INCLUDE_HERMETIC_SLOW=1 \
.venv/bin/python -m pytest tests/test_database_bootstrap_pg18.py \
  -m hermetic_slow -q
```

测试在任何 schema mutation 前核验 host、port、database、username、无密码、无 query、
数据库 identity 和 PostgreSQL 18，然后只 drop/recreate 该 disposable database 的 `public`
schema。它覆盖空库 bootstrap、非空拒绝、历史 downgrade/upgrade、重复 upgrade、required
schema 和 readiness。该结果只属于 local/disposable L2，不是 remote CI 或生产证据。

## 永久修复与回滚纪律

- 新 schema 变更先写可逆 Alembic revision，再同步 `001_init.sql` head 镜像和 required contract。
- 新 release 必须让 backend Docker healthcheck 指向 `/health/ready`。
- 不以手工 `ALTER TABLE`、应用启动 migration、忽略 Alembic exception 或重 stamp 掩盖故障。
- migration 前验证逻辑备份与隔离恢复；失败时保持 provider、publish、delivery 关闭，按已评审
  migration 的 downgrade/forward-fix 策略处理，不删除业务记录。
