---
name: github-actions-deploy-secrets
description: GitHub Actions deploy.yml 必需 secrets 列表与配置说明。当配置 production deploy workflow 或诊断 secret-missing 失败时查阅。
doc_type: runbook
module: ci-cd
topic: deploy-secrets
status: stable
created: 2026-05-17
updated: 2026-05-31
owner: Sisyphus
---

# GitHub Actions deploy.yml — Required Secrets

## 触发方式

`deploy.yml` 在两种条件下运行：

1. **手动触发** (`workflow_dispatch`): GitHub UI → Actions → Deploy to Production → Run workflow，填写 `reason` 字段
2. **Tag 推送**: `git tag v0.2.5 && git push origin v0.2.5` 自动触发

两种方式都会经过 GitHub Environment `production` 的 manual approval gate（在 Settings → Environments → production → Required reviewers 配置）。

## 必需的 GitHub Repository Secrets

在 **Settings → Secrets and variables → Actions → Repository secrets** 配置：

| Secret | 说明 | 示例值 |
|---|---|---|
| `DEPLOY_HOST` | 生产服务器主机/IP | `101.34.52.232` |
| `DEPLOY_USER` | SSH 用户 | `ubuntu` |
| `DEPLOY_SSH_KEY` | SSH 私钥的完整内容（含 `-----BEGIN ... -----END`） | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_TARGET_DIR` | 服务器上的目标目录 | `/opt/ai-video` |

## 必需的 GitHub Environment

在 **Settings → Environments** 创建 `production`：

1. Click **New environment** → name: `production`
2. **Required reviewers**: 添加 1+ 个人审批者（manual approval gate）
3. **Wait timer**: 可选，0-30 分钟延迟（默认 0）
4. **Deployment branches**: 限制为 `main` + tags `v*.*.*`

## Preflight 阶段

`deploy.yml` 在执行 `deploy` job 前会跑：

- `preflight`: ruff check + pytest + frontend `eslint` + `tsc --noEmit` + Vitest + `next build`
- `build-images`: Docker build (cache only, no push)

只要 preflight + build-images 任意 fail，deploy job 不会启动且 GitHub UI 显示明确失败原因。

前端 build 使用 `NEXT_PUBLIC_IS_DEMO=true`，只验证构建完整性，不读取生产 API key 或 POYO key。

## Smoke Test

deploy job 末尾自动 curl `https://${DEPLOY_HOST}/health` 验证 `"status":"ok"`。失败会标记整体 workflow 失败但不会回滚（需要人工处理）。

远程 `deploy/lighthouse/deploy.sh` 由 GitHub Actions 显式以 `RUN_TOKEN_SMOKE=0` 调用。真实生成 smoke 只能在充值后人工 SSH 到服务器或手动运行脚本时显式设置 `RUN_TOKEN_SMOKE=1`。

## Failure Recovery

如果 deploy 后 smoke 失败：

1. 不要立即重新跑 — 先看 `Trigger remote deploy` 步骤的输出
2. SSH 进服务器：`ssh -i ai_video.pem ubuntu@101.34.52.232`
3. 查 docker logs：`docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml logs --tail=200 backend`
4. 修代码后跑新的 tag 推送，避免 amend 旧 commit
