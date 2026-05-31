---
title: P2 充值后真实 Smoke Checklist
doc_type: workflow
module: qa
topic: p2-recharge-smoke-checklist
status: stable
created: 2026-05-31
updated: 2026-05-31
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

执行真实 smoke 必须同时设置两个确认开关：

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

脚本会顺序执行：

1. `deploy/lighthouse/smoke.sh` 的 token path
2. `web` 下的 `npm run e2e:prod`，并通过 `RUN_TOKEN_SMOKE=1` 打开 `@token-smoke`

## 安全边界

- 没有 `--execute` 时永远只 dry-run。
- 没有 `CONFIRM_P2_TOKEN_SMOKE=1` 时拒绝执行。
- 没有 `RUN_TOKEN_SMOKE=1` 时拒绝执行。
- `API_KEY` 或 `PLAYWRIGHT_API_KEY` 仍是 `ai_video_demo_2026` 时拒绝执行。
- 失败后不要盲目循环重试；先检查 provider 控制台、生产日志和失败 artifact。

## 与现有 Runbook 的关系

- Production Playwright 细节见 `docs/runbooks/production-e2e-token-smoke.md`。
- Lighthouse 部署后基础 smoke 仍由 `deploy/lighthouse/smoke.sh` 负责。
- 本文只定义 P2 充值后的统一入口，避免临时手敲命令绕过确认条件。
