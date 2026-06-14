---
title: Release smoke token opt-in
doc_type: workflow
module: release-management
topic: release-smoke-token-opt-in
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Release Smoke Token Opt-In

## 1. 适用范围

本 runbook 约束历史 release smoke 脚本 [`scripts/release_smoke_v0.4.0.sh`](../../scripts/release_smoke_v0.4.0.sh)。目标是防止 release smoke 默认调用真实生成 endpoint 消耗 poyo.ai 或其他 provider tokens。

机器可读契约：[`configs/release-smoke-token-opt-in-contract.json`](../../configs/release-smoke-token-opt-in-contract.json)。

## 2. 默认边界

- 默认执行 release smoke 时，真实生成检查必须默认跳过。
- `/api/fast/generate`、`/api/fast/submit`、`/api/scenario/`、`/api/pipeline/start` 和 `/gate/` 相关 curl 只能出现在 `RUN_TOKEN_SMOKE=1` 分支内。
- 充值前不设置 `RUN_TOKEN_SMOKE=1`。
- 只读健康检查、schema 检查、Prometheus 指标、admin 401 gate 和日志扫描允许保留在默认 release smoke 中。

## 3. 充值后执行真实生成 smoke

只在 poyo.ai 已充值、生产 API key 已确认、操作者明确要消耗额度时执行：

```bash
RUN_TOKEN_SMOKE=1 ./scripts/release_smoke_v0.4.0.sh
```

不要在 CI、默认 deploy、无 token 阶段或不确定余额时加入 `RUN_TOKEN_SMOKE=1`。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_release_smoke_token_opt_in_guard.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_release_smoke_token_opt_in_guard.py tests/test_docs_link_check_scope.py
git diff --check
```

测试入口：[`tests/test_release_smoke_token_opt_in_guard.py`](../../tests/test_release_smoke_token_opt_in_guard.py)。

## 5. 失败处理

- 如果测试发现 unguarded generation curl，先把该 curl 移入 `RUN_TOKEN_SMOKE=1` 分支，不要把 endpoint 加入 allowlist。
- 如果只是新增只读 smoke，确认它不调用 token-consuming endpoint，再更新 contract。
- 如果需要真实 S1-S5 或 Fast Mode smoke，归入 P2 充值后流程，不并入默认 release smoke。
