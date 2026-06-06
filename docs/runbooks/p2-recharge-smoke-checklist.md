---
title: P2 充值后真实 Smoke Checklist
doc_type: workflow
module: qa
topic: p2-recharge-smoke-checklist
status: stable
created: 2026-05-31
updated: 2026-06-06
owner: self
source: human+ai
---

# P2 充值后真实 Smoke Checklist

## 触发场景

poyo.ai 充值后，首次恢复真实生成 smoke。充值前只能运行 dry-run，不允许触发真实生成、gate candidate、上传或发布。

## Dry-Run

充值前执行：

```bash
python scripts/p2_recharge_smoke_checklist.py
```

默认输出 `dry-run` checklist，只检查本地执行条件和将要运行的命令；不会访问生产站点，不会调用 `/health`，不会触发 provider。

## 充值后执行

确认以下 key 已准备好：

- `API_KEY`
- `PLAYWRIGHT_API_KEY`
- `POYO_API_KEY`
- `DEEPSEEK_API_KEY`
- `SILICONFLOW_API_KEY`

同时准备授权记录：

- 模板：`configs/authorized-live-token-smoke-approval-template.json`
- 私有授权记录路径：通过 `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD` 指向
- 授权记录必须将 `template_only` 改为 `false`
- 授权记录必须包含 `provider_revalidation_ref=configs/poyo-current-provider-revalidation-contract.json`
- 授权记录必须包含 `sample_plan` 与 `budget_stop_loss`
- `budget_stop_loss.max_retry_count` 只能是 `0` 或 `1`
- `budget_stop_loss.stop_on_first_failure`、`halt_on_rate_limit`、`halt_on_quota_error`、`halt_on_content_rejection`、`halt_on_missing_artifact` 必须为 `true`

执行真实 smoke 必须同时设置两个确认开关：

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

`--execute` 会自动先跑 no-token preflight；preflight blocked 时脚本直接退出，不会启动 `smoke.sh` 或 Playwright。也可以在正式执行前手动演练同一门禁：

```bash
RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
python scripts/commercial_token_smoke_preflight.py --pretty
```

脚本会顺序执行：

1. `commercial_token_smoke_preflight` 的 no-token 门禁
2. `deploy/lighthouse/smoke.sh` 的 token path
3. `web` 下的 `npm run e2e:prod`，并通过 `RUN_TOKEN_SMOKE=1` 打开 `@token-smoke`

## 安全边界

- 没有 `--execute` 时永远只 dry-run。
- 没有 `CONFIRM_P2_TOKEN_SMOKE=1` 时拒绝执行。
- 没有 `RUN_TOKEN_SMOKE=1` 时拒绝执行。
- 没有通过 `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD` 指向授权记录时不得执行。
- 授权记录模板本身会被 preflight 阻断，不能直接作为正式授权记录。
- 授权记录没有绑定当前 poyo provider revalidation contract 时不得执行。
- preflight blocked 时必须先修复授权、预算、provider capability evidence、job ledger 或 audit bundle，不允许绕过统一入口手动执行 token 命令。
- `API_KEY` 或 `PLAYWRIGHT_API_KEY` 仍是 `ai_video_demo_2026` 时拒绝执行。
- 失败后不要盲目循环重试；先检查 provider 控制台、生产日志和失败 artifact。

## 与现有 Runbook 的关系

- Production Playwright 细节见 `docs/runbooks/production-e2e-token-smoke.md`。
- Lighthouse 部署后基础 smoke 仍由 `deploy/lighthouse/smoke.sh` 负责。
- 本文只定义 P2 充值后的统一入口，避免临时手敲命令绕过确认条件。
