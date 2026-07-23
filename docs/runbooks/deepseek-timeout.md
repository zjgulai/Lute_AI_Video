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
| Prometheus | `pipeline_runs_total{status="failure"}` 比例升高；当前没有伪造的 provider 专属 metric |
| 流水线 | `state.errors` 出现 `strategy_failed: ...DeepSeek...` |
| 前端 | StatusBar 红色，pipeline.error 显示 `Generation failed` |

## 二、立即诊断（先做这 5 步，2 分钟内）

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232

sudo docker logs --tail 200 ai_video_backend 2>&1 | grep -iE "deepseek|llm" | tail -30

sudo docker exec ai_video_backend python -c '
import os
print("DEEPSEEK_API_KEY=present" if os.environ.get("DEEPSEEK_API_KEY") else "DEEPSEEK_API_KEY=missing")'

sudo docker exec ai_video_backend curl -fsS http://localhost:8001/health/ready

sudo docker exec ai_video_backend curl -fsS http://localhost:8001/metrics \
  | grep -E "pipeline_runs_total|pipeline_errors_total" | head
```

以上步骤不调用 provider，也不打印 credential。任何真实 DeepSeek probe 都是 provider
mutation，必须获得一次性的精确授权和预算后另行执行；不得把 runbook 诊断当作授权。

## 三、分类响应

### 场景 A: 上游 API 整体不可用

- **判断**：多条独立 pipeline 同时出现 timeout/connect error，且官方状态页确认异常
- **响应**：等上游恢复。**不要重启后端**，会丢失 paused 状态。
- **降级**：暂停接受新 pipeline → 在前端 ApiKeyGate 旁边挂维护横幅
- **跟踪**：[DeepSeek Status Page](https://status.deepseek.com/) + 国内备份 Kimi

### 场景 B: API Key 失效（401）

- **判断**：日志出现 401/`Authentication Fails`，且 presence-only 检查显示 key 已注入
- **响应**：
  1. 登录 [DeepSeek 控制台](https://platform.deepseek.com/) 确认 key 状态 / 余额
  2. 生成新 key，更新 `deploy/lighthouse/.env.prod`
  3. `sudo docker compose -f /opt/ai-video/docker-compose.prod.yml up -d backend`（只重启 backend，不动其他）
  4. 验证：再跑一次 curl

### 场景 C: 限速（429）

- **判断**：调用方或受控响应证据明确出现 HTTP 429/`Too many requests`；项目日志本身不保证保留 provider 名称或状态码。
- **响应**：
  1. 可查看近一分钟的 best-effort 外部日志信号：`sudo docker logs --since 1m ai_video_backend 2>&1 | grep -ciE "deepseek.*(429|too many requests)"`。项目自有日志会把 provider 异常归一化，因此结果是 0 不能排除 429，也不能作为精确的 provider-call count。
  2. 当前没有运行时暂停开关，也没有已接线的 runtime submit pause/concurrency control。操作员只能先停止人工或上游系统继续发起新任务；如需在 ingress 阻断新 POST，必须使用另行批准且有独立 SOP 的变更。不得把 `deploy maintenance`、停止 backend 或重启容器当作临时限流动作。
  3. 若未来增加运行时暂停或并发控制，必须经过独立设计、代码审查、测试、授权和部署，不能把未接线对象当作操作旋钮。
  4. 联系 DeepSeek 增加配额；provider 切换属于配置与协议变更，必须单独审查和部署
  5. **不要**直接重启容器
- **预防**：使用现有 pipeline failure-rate 告警；在 provider 指标拥有真实 call-site 前不得新增 provider latency panel

### 场景 D: 单个 pipeline 卡在某节点（不是全局故障）

- **判断**：大部分 pipeline 正常，只有一个 label 失败或卡住
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
