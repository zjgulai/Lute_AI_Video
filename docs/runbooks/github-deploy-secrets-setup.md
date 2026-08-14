---
name: github-deploy-secrets-setup
description: 已废弃的 GitHub Actions deploy secrets 配置入口；当前协议统一转到 github-actions-deploy-secrets.md。
doc_type: runbook
module: deployment
topic: github-actions-secrets
status: deprecated
created: 2026-05-17
updated: 2026-08-13
owner: User
related:
  - file: ../../.github/workflows/deploy.yml
    relation: enables-workflow
  - file: ./github-actions-deploy-secrets.md
    relation: deprecated-by
---

# GitHub Actions Deploy — Deprecated Setup Entry

> 本文已废弃，不再是配置或执行依据。请使用
> [`github-actions-deploy-secrets.md`](./github-actions-deploy-secrets.md)。

当前协议把 `archive-only`、`remote-dry-run`、`artifact-stage-only` 和 `deploy` 作为四个独立证据边界：

- `archive-only` 不进入 GitHub Environment，也不读取远端凭据；
- `remote-dry-run` 只使用 `production-read-only-dry-run` 的五项 `DRY_RUN_*`；
- `artifact-stage-only` 只使用 `production-artifact-staging` 的临时 `COS_*` 和受限 `TRANSFER_*`，验证并清理 incoming；
- `deploy` 只有在 COS stage 和 receipt 成功后才进入 `production` 人工审批门禁。

真实生产 Environment 必须限制为 `main` 与 tags `v*.*.*`，并且仅配置五项
Environment-scoped `DEPLOY_*`：`DEPLOY_HOST`、`DEPLOY_USER`、
`DEPLOY_SSH_KEY`、`DEPLOY_TARGET_DIR`、`DEPLOY_KNOWN_HOSTS`。禁止把这些值配置为
repository-wide secrets，也禁止复用只读 dry-run 身份。

任何凭据配置、workflow dispatch 或生产部署都需要单独、精确授权；阅读本文不构成授权。
