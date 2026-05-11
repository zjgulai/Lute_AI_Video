---
name: runbook-pipeline-stuck
description: Runbook 文档，处理 pipeline 卡在 running 状态超过预期阈值的诊断与恢复步骤。当用户反馈「pipeline 跑了 1 小时不动」、StatusBar 长时间不更新、或后台运行的 pipeline 在数据库中 `current_step` 不变化时使用。
---

# Runbook — Pipeline Stuck in "running" State

| | |
|---|---|
| **触发场景** | pipeline.current_step 超过 30 分钟无变化（或符合该步骤 P95 × 3 的阈值） |
| **影响范围** | 单个或一批 pipeline，前端永远转圈，资源持续占用 |
| **预期 MTTR** | 10-20 分钟 |
| **相关代码** | [`src/graph/pipeline.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/pipeline.py) · [`src/graph/routing.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/routing.py) · [`src/pipeline/state_manager.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/state_manager.py) |

## 一、症状识别

| 信号源 | 内容 |
|---|---|
| 前端 | StatusBar 显示 `current_step=X` 长时间不更新 |
| 数据库 | `threads.state['current_step']` 30+ 分钟没动；`updated_at` 落后 |
| 日志 | 没有该 thread 的新日志输出 |
| 进程 | `ps aux | grep uvicorn` 显示 worker 仍在跑（不是进程死了） |

## 二、立即诊断

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232

LABEL="s1_1778394550_xxxxxxx"

sudo docker exec ai_video_backend python3 -c "
import asyncio, json
from src.storage.repository import ThreadRepository
async def main():
    t = await ThreadRepository.get('$LABEL')
    state = t['state'] if t else {}
    print(json.dumps({
        'current_step': state.get('current_step'),
        'errors': state.get('errors', []),
        'degraded': state.get('pipeline_degraded'),
        'updated_at': str(t.get('updated_at')) if t else None,
        'gates': state.get('gates', {}),
    }, indent=2, ensure_ascii=False, default=str))
asyncio.run(main())"

sudo docker logs --tail 1000 ai_video_backend 2>&1 | grep -E "$LABEL|thread_id=$LABEL" | tail -30

sudo docker exec ai_video_backend python3 -c "
import asyncpg, asyncio, os
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    rows = await conn.fetch(
        '''SELECT thread_id, last_checkpoint, created_at FROM checkpoints
           WHERE thread_id LIKE \$1 ORDER BY created_at DESC LIMIT 5''',
        '%${LABEL}%')
    for r in rows: print(dict(r))
    await conn.close()
asyncio.run(main())" 2>&1 | head -30
```

## 三、分类响应

### 场景 A: pipeline_degraded=True 但前端还在转圈

- **判断**：state 里 `pipeline_degraded=True` 且 `errors` 非空
- **响应**：后端已正确终止 pipeline，前端 polling bug 导致 UI 不更新
  1. 标记 thread 完成：
     ```python
     docker exec ai_video_backend python3 -c "
       import asyncio
       from src.storage.repository import ThreadRepository
       async def f():
           await ThreadRepository.update('$LABEL', {'status': 'failed'})
       asyncio.run(f())"
     ```
  2. 提交前端 bug：[StatusBar.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/PipelineStatusBar.tsx) 应轮询 `pipeline_degraded` 字段并立即停止

### 场景 B: paused gate 但前端没显示 GatePanel

- **判断**：state 里 `gates.<gate_id>.status = pending_review` 但 `current_step` 是 `paused`
- **响应**：
  1. 检查 gate URL 是否能直接打开：`https://101.34.52.232/s1?mode=expert&label=$LABEL`
  2. 如果浏览器 console 报 401 → 用户 API Key 失效，让用户重新登录
  3. 如果浏览器能打开但 GatePanel 不显示 → 可能是 [GatePanel.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/GatePanel.tsx) 的 demo-data fallback 路径 bug

### 场景 C: 真正卡死（无 degraded、无 paused、无新日志）

- **判断**：30+ 分钟无任何变化，日志完全静默
- **响应**：
  1. **不要直接重启容器** — LangGraph checkpoint 可能在写中间状态
  2. 确认 worker 进程存活：`sudo docker exec ai_video_backend ps aux | grep -v grep | grep uvicorn`
  3. 抓栈：`sudo docker exec ai_video_backend py-spy dump --pid <PID>` （需要 py-spy 已安装）
     - 如果卡在 `httpx.read` / `asyncio.sleep` → 上游 API 卡死，看 [deepseek-timeout.md](./deepseek-timeout.md) / [poyo-rejection.md](./poyo-rejection.md)
     - 如果卡在 `asyncpg.fetch` → 看 [db-pool-exhausted.md](./db-pool-exhausted.md)
     - 其他 → 升级 oracle 排查
  4. 标记 thread 失败 + 通知用户重启：
     ```python
     await ThreadRepository.update('$LABEL', {
         'status': 'failed',
         'state': {**old_state, 'pipeline_degraded': True,
                   'errors': old_state.get('errors', []) + ['manually_terminated_stuck']}
     })
     ```

### 场景 D: 整批 pipeline 都卡（5+ thread 同时不动）

- **判断**：步骤 1 显示多个 thread 同时停滞
- **响应**：
  1. 资源耗尽？`sudo docker stats ai_video_backend` 看 CPU / Memory
  2. 数据库连接池？看 [db-pool-exhausted.md](./db-pool-exhausted.md)
  3. 网络？所有 pipeline 都依赖 deepseek / poyo，curl 验证上游

## 四、永久 fix

如果某种 stuck 形态在一周内重复 ≥ 2 次：

1. 加 timeout 哨兵：每个 LangGraph 节点应有 `asyncio.wait_for(..., timeout=N)` 包裹
2. 在 [`src/graph/pipeline.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/pipeline.py) 加全局 pipeline 超时（默认 60 分钟）
3. 加 Prometheus 告警：`pipeline_active_count > 0 AND rate(pipeline_step_complete_total[15m]) == 0`

## 五、相关 Runbook

- [deepseek-timeout.md](./deepseek-timeout.md)
- [poyo-rejection.md](./poyo-rejection.md)
- [db-pool-exhausted.md](./db-pool-exhausted.md)
