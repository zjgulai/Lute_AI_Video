---
name: github-deploy-secrets-setup
description: GitHub Actions deploy workflow 所需 4 个 secrets 配置 + workflow_dispatch dry-run 步骤。user 在 repo Settings → Environments → "production" 添加 secrets 后可触发 workflow 验证 SSH 联通。约 30min 配置 + 30min dry-run。
doc_type: runbook
module: deployment
topic: github-actions-secrets
status: stable
created: 2026-05-17
updated: 2026-05-17
owner: User
related:
  - file: ../../.github/workflows/deploy.yml
    relation: enables-workflow
---

# GitHub Actions Deploy — Secrets Setup Runbook

## Why

`.github/workflows/deploy.yml` 已编写完毕，含 preflight + build + rsync + smoke。但 4 个 secrets 未配置时 workflow 会 fail 在 "Verify required secrets" step。

## User actions

### Step 1: 在 GitHub repo 创建 Production environment

1. 打开 https://github.com/{org}/{repo}/settings/environments
2. 点 **New environment** → name = `production`
3. **Required reviewers**: 添加至少 2 人（user 本人 + 1 个团队成员）
4. **Deployment branches**: 仅 `main` + tags `v*`

### Step 2: 添加 4 个 secrets

在 production environment 页面，点 **Add environment secret**:

| Secret name | Value | 备注 |
|---|---|---|
| `DEPLOY_HOST` | `101.34.52.232` 或 `video.lute-tlz-dddd.top` | 生产 host |
| `DEPLOY_USER` | `ubuntu` | SSH user |
| `DEPLOY_SSH_KEY` | 完整 PEM 内容（含 `-----BEGIN` ... `-----END` 头尾） | `cat ~/ai_video.pem` 复制 |
| `DEPLOY_TARGET_DIR` | `/opt/ai-video` | 生产代码目录 |

### Step 3: dry-run 验证 SSH 联通

```
# 在 GitHub Actions 页面手动触发：
# Workflow: Deploy to Production
# Run workflow → 输入 reason: "P1-5 dry-run probe"
```

**期望流程**:
1. ✅ Preflight: lint + pytest + frontend type check + vitest 全 PASS
2. ✅ Build images: backend Docker image 构建 + GHA cache
3. ⏸️ Deploy: 等 production environment 的 **required reviewers approve**
4. ✅ approve 后：rsync + remote deploy + smoke test /health

### Step 4: 验收

- workflow 在 deploy 任务下展示 SSH 连接 / rsync / `/health` 200 三段绿
- production env 显示 deployment record + reviewer approval log

## Failure modes

| 报错 | 原因 | 修复 |
|---|---|---|
| `Missing required secret: DEPLOY_HOST` | secrets 未添加 | Step 2 |
| `Permission denied (publickey)` | SSH_KEY 格式错或权限错 | 确认 PEM 包含完整 BEGIN/END 头尾 |
| `rsync: target permission denied` | DEPLOY_USER 不能写 TARGET_DIR | 在 host `chown -R ubuntu:ubuntu /opt/ai-video` |
| `/health did not return ok` | deploy.sh 失败 | 看 GitHub Actions 日志 + SSH 到 host 看 `docker logs ai_video_backend` |

## 完成验收

User 跑一次 dry-run 后：
- [ ] preflight 全绿
- [ ] approval gate 触发（验证 required reviewers 起作用）
- [ ] approve 后 deploy + smoke PASS
- [ ] 生产 /health 仍返 200（确认无副作用）
