---
name: runbook-db-pool-exhausted
description: Runbook 文档，处理 asyncpg 连接池耗尽导致请求挂起 / 503 的诊断与恢复步骤。当后端日志出现「pool exhausted」、API 大量返回 503、或 `db_pool_available_connections` 告警触发时使用。
---

# Runbook — Database Connection Pool Exhausted

| | |
|---|---|
| **触发场景** | asyncpg pool 耗尽（默认 max=10），新请求挂起或超时 |
| **影响范围** | 所有依赖 PG 的 API（绝大多数 `/scenario/*`、`/admin/*`、`/metrics/*`） |
| **预期 MTTR** | 5-10 分钟（如有连接泄漏需要更长时间排查） |
| **相关代码** | [`src/storage/db.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/db.py) |

## 一、症状识别

| 信号源 | 内容 |
|---|---|
| 后端日志 | `asyncpg.exceptions.ConnectionDoesNotExistError` 或 `pool exhausted` 或长时间 hang |
| Prometheus | `db_pool_available_connections == 0` 持续 5 分钟 |
| 前端 | 大量 API 返回 503 / 504，admin 页面也打不开 |
| 用户感受 | "整个系统卡了" |

## 二、立即诊断

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232

sudo docker exec ai_video_backend python3 -c "
import asyncio
from src.storage.db import get_pool
async def main():
    p = await get_pool()
    if p is None:
        print('no pool (SQLite mode?)'); return
    print(f'size={p.get_size()} idle={p.get_idle_size()} max={p.get_max_size()} min={p.get_min_size()}')
asyncio.run(main())"

sudo docker exec ai_video_backend python3 -c "
import asyncpg, asyncio, os
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    rows = await conn.fetch('''
        SELECT pid, state, query_start, now() - query_start AS duration,
               LEFT(query, 100) AS query_preview
        FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
        ORDER BY query_start ASC LIMIT 30''')
    for r in rows: print(dict(r))
    await conn.close()
asyncio.run(main())"

sudo docker logs --tail 500 ai_video_backend 2>&1 | grep -iE "pool|asyncpg|exhausted|connection" | tail -20

sudo docker exec ai_video_backend curl -sS --max-time 5 http://localhost:8001/health 2>&1 | head -20
```

## 三、分类响应

### 场景 A: PG 实例本身故障

- **判断**：步骤 2 直接连不上 PG，或 `pg_isready` 失败
- **响应**：
  1. 看 PG 容器：`sudo docker ps | grep postgres` 是否在跑
  2. 看 PG 日志：`sudo docker logs ai_video_postgres --tail 100`
  3. 重启 PG（**仅在确认无写入中状态**）：`sudo docker compose -f /opt/ai-video/docker-compose.prod.yml restart postgres`
  4. 重启 backend 等 PG ready：`sudo docker compose -f .../docker-compose.prod.yml restart backend`

### 场景 B: 长查询占满连接（"runaway query"）

- **判断**：步骤 2 显示 ≥ 1 个 query 跑了 > 5 分钟，state=active
- **响应**：
  1. 识别 query：通常是 `SELECT * FROM threads WHERE ...` 没用上索引
  2. 强杀该 query（不杀 connection）：
     ```sql
     SELECT pg_cancel_backend(<pid>);
     ```
  3. 如果 cancel 不响应，再 terminate：
     ```sql
     SELECT pg_terminate_backend(<pid>);
     ```
  4. 找到该 query 的代码位置 → 加索引 / 改写
  5. 写复现单测

### 场景 C: 连接泄漏（代码 bug，没正确释放）

- **判断**：步骤 1 显示 `idle=0 size=max`，且 `pg_stat_activity` 里大量 `state=idle in transaction`
- **响应**：
  1. **不要重启** — 先抓证据：`sudo docker logs ai_video_backend > /tmp/backend_$(date +%s).log`
  2. 临时缓解：重启 backend 释放所有连接 `sudo docker compose ... restart backend`
  3. 排查代码：搜索 `acquire()` 没配对 `release()` 的位置，搜索 `pool.acquire` 上下文管理器缺失
  4. 加单测覆盖：`tests/test_postgres.py` 加 connection-leak 检测
  5. **永久 fix**：所有 PG 调用走 `async with pool.acquire() as conn:`，禁止裸 `acquire()`

### 场景 D: 流量激增（合法连接）

- **判断**：步骤 1 显示满载，但 query 都是合理的短 query；并发请求数突增
- **响应**：
  1. 临时提高 pool 上限：环境变量 `DB_POOL_MAX=20`（重启 backend 生效）
  2. 评估 PG 实例规格升级（Tencent RDS 控制台）
  3. 加 Prometheus 告警：`rate(http_requests_total[1m]) > N` 提前预警

## 四、永久 fix

| 触发频率 | 建议措施 |
|---|---|
| 月度 1-2 次 | 加监控告警 |
| 周度 ≥ 2 次 | 升 PG 规格 + 加 pool 上限 |
| 日度 | 强制 code review 所有 PG 调用 + 单测全覆盖 |

## 五、关联指标

部署完 Prometheus 后应有：

- `db_pool_available_connections` — gauge
- `db_pool_total_connections` — gauge
- `db_pool_acquire_duration_seconds` — histogram（获取连接的等待时间）

告警阈值：

- `db_pool_available_connections < 2 for 5m` → DingTalk

## 六、相关 Runbook

- [pipeline-stuck.md](./pipeline-stuck.md)
- [deepseek-timeout.md](./deepseek-timeout.md)
