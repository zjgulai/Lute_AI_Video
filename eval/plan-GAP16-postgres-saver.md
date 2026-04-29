# GAP-16: PostgresSaver 持久化改造

> **目标：** 将管道检查点从 MemorySaver（进程内，测试用）替换为 PostgresSaver（持久化，生产可用）。
> 同时新增 `pipeline_history` API 端点和 E2E 验证测试。

---

## 架构

### 分层替换

```
当前: compile_pipeline(checkpointer=None) → MemorySaver
目标: compile_pipeline(checkpointer=None, db_url=None) → MemorySaver fallback 或 PostgresSaver
```

### 从 db_url 到 PostgresSaver

`PostgresSaver.from_conn_string(dsn)` 自动建立连接池，`await saver.setup()` 运行迁移。`serde` 通过 `saver.serde` 属性使用 `with_msgpack_allowlist` 设置——与 MemorySaver 模式一致。

### 回退策略

- 无 `db_url` → MemorySaver（开发/测试，不变）
- 有 `db_url` 但连接失败 → 日志警告 + MemorySaver（优雅降级，不崩溃）
- 有 `db_url` + 连接成功 → PostgresSaver

---

## 实现任务

### Task 1: compile_pipeline() 增加 db_url 参数 + PostgresSaver 分支

**Files:**
- Modify: `src/graph/pipeline.py:140-189`

```python
def compile_pipeline(checkpointer=None, db_url: str | None = None):
    # ... existing serializer setup ...

    if checkpointer is None:
        if db_url:
            from langgraph.checkpoint.postgres import PostgresSaver
            try:
                checkpointer = PostgresSaver.from_conn_string(db_url)
                checkpointer.serde = serializer
            except Exception as e:
                logger.warning("PostgresSaver init failed, falling back to MemorySaver", error=str(e))
                checkpointer = MemorySaver(serde=serializer)
        else:
            checkpointer = MemorySaver(serde=serializer)
    # ... rest unchanged ...
```

**验证：**
```bash
cd /workspace/projects/hermes_evo/AI_vedio
python3 -c "from src.graph.pipeline import compile_pipeline; c=compile_pipeline(); print('Memory fallback OK')"
python3 -c "from src.graph.pipeline import compile_pipeline; c=compile_pipeline(db_url='postgresql://localhost:5432/nonexistent'); print('Graceful fallback OK')"
```

### Task 2: 新增 `pipeline_history` API 端点

**Files:**
- Modify: `src/api.py`（追加端点）

```python
@app.get("/pipeline/{thread_id}/history")
async def get_pipeline_history(thread_id: str):
    """Get full checkpoint history for a pipeline run (PostgresSaver only)."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshots = []
    try:
        async for state in _pipeline.astream(None, config, stream_mode="values"):
            snapshots.append(state)
    except Exception:
        pass
    return {"thread_id": thread_id, "snapshots": snapshots}
```

**验证：** 通过 `test_api.py` 集成。

### Task 3: 测试

**Files:**
- Create: `tests/test_postgres.py`

**测试范围（5 tests）：**

| # | 测试 | 场景 | 验证 |
|---|---|---|---|
| 1 | `test_compile_fallback_no_db_url` | 不传 db_url | MemorySaver 被使用 |
| 2 | `test_compile_fallback_bad_db_url` | 传无效 db_url | 不抛异常，走 MemorySaver fallback |
| 3 | `test_compile_with_db_url_config` | 从 config 读 db_url | 配置正确传递 |
| 4 | `test_api_history_endpoint` | GET /pipeline/{id}/history | 返回快照列表（即使为空） |
| 5 | `test_custom_checkpointer_still_works` | 传自定义 checkpointer | 不走 Postgres 分支 |

### Task 4: 完整回归

```bash
cd /workspace/projects/hermes_evo/AI_vedio && python3 -m pytest tests/ -v --tb=short
```

期望：260+ 仍然通过，新增 5 个测试 = 265+。

---

## 质量门槛

- ✅ PostgresSaver 可导入（`langgraph-checkpoint-postgres>=3.0.5`）
- ✅ 无 db_url → MemorySaver（行为不变）
- ✅ 坏 db_url → MemorySaver 优雅降级（不崩溃，有日志）
- ✅ 好 db_url → PostgresSaver（生产持久化）
- ✅ 自定义 checkpointer 优先级高于 db_url
- ✅ 现有 260 个测试全部通过
