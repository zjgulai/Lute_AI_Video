---
name: github-actions-deploy-secrets
description: GitHub Actions deploy.yml 必需 secrets 列表与配置说明。当配置 production deploy workflow 或诊断 secret-missing 失败时查阅。
doc_type: runbook
module: ci-cd
topic: deploy-secrets
status: stable
created: 2026-05-17
updated: 2026-07-20
owner: Sisyphus
---

# GitHub Actions deploy.yml — Required Secrets

## 触发方式

`deploy.yml` 在两种条件下运行：

1. **手动触发** (`workflow_dispatch`): GitHub UI → Actions → Deploy to Production → Run workflow，填写 `reason` 字段
2. **Tag 推送**: `git tag v0.2.5 && git push origin v0.2.5` 自动触发

两种方式都先经过无生产凭证的 exact-main provenance gate。远程只读 dry-run 使用独立的 `production-read-only-dry-run` environment；真实部署才经过 GitHub Environment `production` 的 manual approval gate。

## 必需的 production Environment Secrets

在 **Settings → Environments → production → Environment secrets** 配置：

| Secret | 说明 | 示例值 |
|---|---|---|
| `DEPLOY_HOST` | 生产服务器主机/IP | `101.34.52.232` |
| `DEPLOY_USER` | SSH 用户 | `ubuntu` |
| `DEPLOY_SSH_KEY` | SSH 私钥的完整内容（含 `-----BEGIN ... -----END`） | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_TARGET_DIR` | 服务器上的目标目录 | `/opt/ai-video` |
| `DEPLOY_KNOWN_HOSTS` | 预先核验并固定的生产 SSH `known_hosts` 行；禁止运行时 `ssh-keyscan`/TOFU | `<host> <key-type> <public-key>` |

这些 secret 不得配置成 repository-wide secret；它们只能在 `production` 人工批准后进入 deploy job。

## 只读 dry-run Environment Secrets

在独立 Environment `production-read-only-dry-run` 配置：

| Secret | 说明 |
|---|---|
| `DRY_RUN_HOST` | 只读 dry-run SSH 目标 |
| `DRY_RUN_USER` | 服务器端受限账号 |
| `DRY_RUN_SSH_KEY` | 仅允许目标路径存在性检查和 rsync dry-run 的独立私钥 |
| `DRY_RUN_TARGET_DIR` | 只读检查目标根目录 |
| `DRY_RUN_KNOWN_HOSTS` | 预先核验并固定的 SSH host key |

服务端必须用 forced command/权限规则限制该账号，禁止写文件、启动容器、读取 env/secrets 或执行任意 shell。未配置这组独立凭证时，`remote-dry-run` 必须阻断；不得回退复用 `DEPLOY_*`。

## 必需的 GitHub Environment

在 **Settings → Environments** 创建 `production`：

1. Click **New environment** → name: `production`
2. **Required reviewers**: 添加 1+ 个人审批者（manual approval gate）
3. **Wait timer**: 可选，0-30 分钟延迟（默认 0）
4. **Deployment branches**: 限制为 `main` + tags `v*.*.*`

同时创建 `production-read-only-dry-run`，限制为 `main` + tags `v*.*.*`，只放上述 `DRY_RUN_*` secret。它不持有生产写权限。

## Preflight 阶段

`deploy.yml` 在执行 `deploy` job 前会跑：

- `preflight`: ruff check + pytest + frontend `eslint` + `tsc --noEmit` + Vitest + `next build`
- `build-images`: 构建 backend/frontend/rendering 三个 SHA-tagged image，校验 revision label、backend production import、frontend HTTP 和 rendering/ffmpeg/Chromium health；不读取 provider secret
- `remote-dry-run`: 只使用受限 `DRY_RUN_*` 身份生成 rsync dry-run artifact，不读取 `DEPLOY_*`

只要 preflight + build-images 任意 fail，deploy job 不会启动且 GitHub UI 显示明确失败原因。

前端 build 使用 `NEXT_PUBLIC_IS_DEMO=true`，只验证构建完整性，不读取生产 API key 或 POYO key。

## Provider-off acceptance

deploy job 末尾使用正常 TLS 校验访问 canonical `https://video.lute-tlz-dddd.top/api/health`，除 `status=ok` 外还要求 `persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。IP fallback 和 `curl -k` 都不能作为成功证据。

远程 canonical deploy 永久以 `RUN_TOKEN_SMOKE=0`、`RUN_DEPLOY_SMOKE=0` 执行，不读取 API key、不调用生成接口。真实生成验证只能走独立的 exact-authorization harness，不能通过 deploy workflow 解锁。

## Failure Recovery

如果 deploy 后 smoke 失败：

1. 不要立即重新跑 — 先看 `Trigger remote deploy` 步骤的输出
2. SSH 进服务器：`ssh -i ai_video.pem ubuntu@101.34.52.232`
3. 查 docker logs：`docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml logs --tail=200 backend`
4. 修代码后跑新的 tag 推送，避免 amend 旧 commit
