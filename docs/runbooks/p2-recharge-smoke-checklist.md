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

正式执行前先生成一次 no-token 启动包：

```bash
python scripts/build_authorized_live_smoke_packet.py --include-preflight
```

启动包只输出授权语句、私有记录要求、样本计划引用、provider revalidation 引用、命令 preview 和当前 preflight blocked/pass 投影；不读取 API key 原文，不访问 provider，不执行 `smoke.sh` 或 Playwright。启动包证据等级保持 `L2-fixture-or-dry-run`，不能单独作为 L4 授权或真实生成成功证据。

## 充值后执行

确认以下 key 已准备好：

- `API_KEY`
- `PLAYWRIGHT_API_KEY`
- `POYO_API_KEY`
- `DEEPSEEK_API_KEY`
- `SILICONFLOW_API_KEY`
- `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`
- `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`
- `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json>`

同时准备授权记录：

- 模板：`configs/authorized-live-token-smoke-approval-template.json`
- 构建器：`scripts/build_authorized_live_approval_record.py`
- 私有授权记录路径：通过 `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD` 指向，必须放在 `tmp/` 或仓库外
- 授权记录必须将 `template_only` 改为 `false`
- 授权记录必须包含 `provider_revalidation_ref=configs/poyo-current-provider-revalidation-contract.json`
- 授权记录必须包含 `sample_plan_ref=configs/authorized-live-token-smoke-sample-plan-contract.json`
- 授权记录必须包含 `sample_plan` 与 `budget_stop_loss`
- `budget_stop_loss.max_retry_count` 只能是 `0` 或 `1`
- `budget_stop_loss.stop_on_first_failure`、`halt_on_rate_limit`、`halt_on_quota_error`、`halt_on_content_rejection`、`halt_on_missing_artifact` 必须为 `true`

同时准备 provider 账户 readiness 记录：

- 构建器：`scripts/build_provider_account_readiness_record.py`
- 私有账户记录路径：通过 `AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD` 指向，必须放在 `tmp/` 或仓库外
- 账户记录只允许写入人工查看 provider 控制台后的余额/key 配置确认，不得写入 API key 原文
- `available_credit_usd` 必须覆盖 `configs/authorized-live-token-smoke-sample-plan-contract.json` 的总预算

先用构建器打印本轮必须逐字确认的授权句：

```bash
python scripts/build_authorized_live_approval_record.py --print-required-statement \
  --approved-by <operator-name> \
  --approval-statement ignored
```

用户在当前会话提供完全一致的授权句后，再生成私有授权记录：

```bash
python scripts/build_authorized_live_approval_record.py \
  --approved-by <operator-name> \
  --approval-statement '我授权在生产环境 https://video.lute-tlz-dddd.top 使用 poyo image + poyo Seedance 执行 Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频的真实调用 smoke，预算上限 $3.00，自动重试 0，不发布、不写入正式 brand token，产物只进入待审素材库。' \
  --output tmp/outputs/authorized-live-token-smoke-approval.json
```

人工确认 poyo 控制台余额和 key 配置后，再生成私有账户 readiness 记录：

```bash
python scripts/build_provider_account_readiness_record.py \
  --checked-by <operator-name> \
  --available-credit-usd 3.00 \
  --output tmp/outputs/poyo-account-readiness.json
```

执行真实 smoke 必须同时设置两个确认开关：

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD=<private-account-readiness-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

`--execute` 会自动先跑 no-token preflight；preflight blocked 时脚本直接退出，不会启动 `smoke.sh` 或 Playwright。也可以在正式执行前手动演练同一门禁：

```bash
RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD=<private-account-readiness-json> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
python scripts/commercial_token_smoke_preflight.py --pretty
```

脚本会顺序执行：

1. `commercial_token_smoke_preflight` 的 no-token 门禁
2. `scripts/authorized_live_token_smoke_harness.py --execute --enable-poyo-http-submitter --pretty` 的 C21 授权 harness

当前统一入口只在 preflight 通过、`AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`、私有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS` 均存在时接线 provider submitter。本轮授权样本必须严格对应 Momcozy 消毒器 3 张待审图片资产和 1 条 15 秒 9:16 待审图片驱动视频，并保存 job ledger、artifact manifest、quality gate 和 repair plan。

首轮不测试暖奶器、S5 VLOG、数字人、发布链路或完整上市交付。产物只能进入 `pending_review` 素材库，不能自动写入 approved brand token、delivery accepted 或 publish allowed。

## 安全边界

- 没有 `--execute` 时永远只 dry-run。
- 没有 `CONFIRM_P2_TOKEN_SMOKE=1` 时拒绝执行。
- 没有 `RUN_TOKEN_SMOKE=1` 时拒绝执行。
- 没有通过 `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD` 指向授权记录时不得执行。
- 没有通过 `AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD` 指向账户 readiness 记录时不得执行。
- 没有 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1` 时不得进入 harness execute。
- 没有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 时不得接线 poyo HTTP submitter。
- 没有私有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS` 时不得构造 poyo 请求 payload。
- no-token 启动包只证明门禁输入已被列明，不证明用户已经授权、账户已充值或 provider runtime 可用。
- 授权记录必须由构建器或等价校验流程生成；`同意下一步` 这类泛化确认不构成 L4 授权。
- 授权记录模板本身会被 preflight 阻断，不能直接作为正式授权记录。
- 账户 readiness 记录余额不足、仍是模板、或记录了 API key 原文时不得执行。
- 授权记录没有绑定当前 poyo provider revalidation contract 时不得执行。
- 授权记录没有绑定当前 authorized-live sample plan contract 时不得执行。
- preflight blocked 时必须先修复授权、预算、provider capability evidence、job ledger 或 audit bundle，不允许绕过统一入口手动执行 token 命令。
- `API_KEY` 或 `PLAYWRIGHT_API_KEY` 仍是 `ai_video_demo_2026` 时拒绝执行。
- 失败后不要盲目循环重试；先检查 provider 控制台、生产日志和失败 artifact。

## 与现有 Runbook 的关系

- Production Playwright 细节见 `docs/runbooks/production-e2e-token-smoke.md`。
- Lighthouse 部署后基础 smoke 仍由 `deploy/lighthouse/smoke.sh` 负责。
- 本文只定义 P2 充值后的统一入口，避免临时手敲命令绕过确认条件。
