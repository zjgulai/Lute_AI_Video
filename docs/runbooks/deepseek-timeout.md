---
name: runbook-deepseek-timeout
description: Runbook 文档，处理 DeepSeek API 超时 / 不可用 / 限速时的诊断与恢复步骤。当生产流水线大量报 LLM 调用失败、p95 延迟突增、或 DingTalk 告警「LLM API 3 consecutive failures」触发时使用。
---

# Runbook — DeepSeek API Timeout / Unavailable

| | |
|---|---|
| **触发场景** | 后端日志 `deepseek` 调用 timeout / connection refused / 401 / 429 |
| **影响范围** | 流水线 strategy / script / compliance / caption / thumbnail 步骤（全部走文本 LLM） |
| **预期 MTTR** | 5-15 分钟（取决于上游恢复时间） |
| **相关代码** | [`src/tools/llm_client.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/llm_client.py) · [`src/config.py:115`](file:///Users/pray/project/hermes_evo/AI_vedio/src/config.py#L115) |

## 一、症状识别

| 信号源 | 内容 |
|---|---|
| 后端日志 | `httpx.TimeoutException` / `httpx.ConnectError` / `Error code: 401 invalid_request_error` |
| Prometheus | `llm_api_errors_total{provider="deepseek"}` 突增 |
| 流水线 | `state.errors` 出现 `strategy_failed: ...DeepSeek...` |
| 前端 | StatusBar 红色，pipeline.error 显示 `Generation failed` |

## 二、立即诊断（先做这 5 步，2 分钟内）

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232

sudo docker exec ai_video_backend sh -c '
  curl -sS -o /dev/null -w "HTTP=%{http_code} time=%{time_total}s\n" \
       --max-time 10 \
       -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
       -H "Content-Type: application/json" \
       -d "{\"model\":\"deepseek-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}" \
       https://api.deepseek.com/chat/completions'

sudo docker logs --tail 200 ai_video_backend 2>&1 | grep -iE "deepseek|llm" | tail -30

sudo docker exec ai_video_backend printenv DEEPSEEK_API_KEY | head -c 16; echo

curl -sS https://api.deepseek.com/v1/models -o /dev/null -w "HTTP=%{http_code}\n"

sudo docker exec ai_video_backend curl -sS http://localhost:8001/metrics 2>/dev/null | grep -E "llm_api_(errors|duration)" | head
```

## 三、分类响应

### 场景 A: 上游 API 整体不可用（200 都不返）

- **判断**：步骤 4 的 `curl https://api.deepseek.com/v1/models` 也失败
- **响应**：等上游恢复。**不要重启后端**，会丢失 paused 状态。
- **降级**：暂停接受新 pipeline → 在前端 ApiKeyGate 旁边挂维护横幅
- **跟踪**：[DeepSeek Status Page](https://status.deepseek.com/) + 国内备份 Kimi

### 场景 B: API Key 失效（401）

- **判断**：步骤 1 返回 HTTP=401，日志 `Authentication Fails`
- **响应**：
  1. 登录 [DeepSeek 控制台](https://platform.deepseek.com/) 确认 key 状态 / 余额
  2. 生成新 key，更新 `deploy/lighthouse/.env.prod`
  3. `sudo docker compose -f /opt/ai-video/docker-compose.prod.yml up -d backend`（只重启 backend，不动其他）
  4. 验证：再跑一次 curl

### 场景 C: 限速（429）

- **判断**：HTTP=429，日志 `Too many requests`
- **响应**：
  1. 检查并发：`sudo docker logs ai_video_backend | grep -c "deepseek.*POST"` 看每分钟次数
  2. 临时降并发：`OPT-E_SEEDANCE_SEMAPHORE`（注：seedance 是 poyo 不是 deepseek，这里指降低 pipeline 并发提交速率）
  3. 联系 DeepSeek 增加配额，或临时切换备用 provider：`docker exec ai_video_backend sh -c 'export DEFAULT_LLM_PROVIDER=anthropic'`（需要 ANTHROPIC_API_KEY 已配置）
  4. **不要**直接重启容器
- **预防**：在 Prometheus 加 `llm_api_duration_seconds{provider="deepseek"} > P95(5s)` 告警

### 场景 D: 单个 pipeline 卡在某节点（不是全局故障）

- **判断**：步骤 1 curl 成功 + 大部分 pipeline 正常
- **响应**：
  1. 拿到 stuck thread id（前端 URL 里 `label=` 参数）
  2. `sudo docker exec ai_video_backend python3 -c "
     from src.storage.repository import ThreadRepository
     import asyncio
     r = asyncio.run(ThreadRepository.get('label_id'))
     print(r)"`
  3. 看 `errors` 字段：
     - 有 `degraded` 标志 → pipeline 已自动终止，**不需要操作**
     - 没有 degraded → 可能是 LangGraph checkpoint 卡死，参考 [pipeline-stuck.md](./pipeline-stuck.md)

## 四、根因记录

故障恢复后必须：

1. 在 `docs/postmortems/` 新建 `YYYY-MM-DD-deepseek-incident.md`，至少记录：
   - 时间线（首次报错 / 告警 / 介入 / 恢复）
   - 影响 pipeline 数量
   - 上游具体故障（status page 截图 + 引用）
   - 是否需要更新 runbook
2. 如果一周内重复 ≥ 2 次：评估切换主 provider 到 Anthropic / Kimi（注意 ADR #001 + AGENTS.md `DEFAULT_LLM_PROVIDER` SSOT 同步）

## 五、相关 Runbook

- [poyo-rejection.md](./poyo-rejection.md) — POYO 内容审核拒绝
- [pipeline-stuck.md](./pipeline-stuck.md) — pipeline 卡在 running
- [db-pool-exhausted.md](./db-pool-exhausted.md) — 数据库连接池耗尽
