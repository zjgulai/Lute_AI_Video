---
title: Lighthouse rsync artifact exclude guard
doc_type: workflow
module: deploy
topic: lighthouse-rsync-artifact-exclude
status: stable
created: 2026-06-01
updated: 2026-07-09
owner: self
source: human+ai
---

# Lighthouse rsync artifact exclude guard

## 目的

锁定 Lighthouse 同步边界，防止本地构建产物、Playwright 报告、截图、临时输出、草稿/归档材料、本地工作态目录、参考截图、生产 secret、远端备份和 remote-only production sidecars 被 `rsync --delete` 同步或删除到 `/opt/ai-video`。

## 不变量

- 唯一排除清单是 `deploy/lighthouse/rsync-excludes.txt`。
- `deploy/lighthouse/build-and-deploy.sh` 必须使用 `--exclude-from="$EXCLUDE_FILE"`。
- `deploy/lighthouse/build-and-deploy.sh` 必须使用 GNU rsync 3.x 执行 `--chmod=F644,D755`；在 macOS 上优先选择 `/opt/homebrew/bin/rsync` 或 `/usr/local/bin/rsync`，也允许 `RSYNC_BIN=/path/to/rsync` 覆盖。
- `.github/workflows/deploy.yml` 必须使用 `--exclude-from='deploy/lighthouse/rsync-excludes.txt'`，不得维护 inline exclude 副本。
- 必须排除 frontend build artifacts：`web/.next`、`web/.next.old`、`web/dist`。
- 必须排除 report / trace artifacts：`web/playwright-report`、`web/test-results`、`web/blob-report`。
- 必须排除 screenshots / tmp outputs：`tmp/screenshots`、`tmp/outputs`、`web/tmp`、`web/tmp/screenshots`、`output_uploaded`。
- 必须排除 local workspace state：`.codegraph`、`.hermes`、`worktrees`、`drafts`、`archive`、`ref`。
- 必须排除 production secret / cert：`*.pem`、`deploy/lighthouse/.env.prod`、`deploy/lighthouse/.portal-auth.env`、`server.crt`、`server.key`。
- 必须保护 remote-only production sidecars：`backups`、`deploy/lighthouse/backups`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/*.conf.*backup*`。这些路径可能承载跨产品入口、认证服务或远端回滚证据，不能被 AI Video 发布默认清理。
- 必须保护 remote-only landing sidecars：`landing/login.html`、`landing/register.html`、`landing/systems.html`、`landing/lute-*.html`、`landing/lute-auth.*`、`landing/voc-zh_messages.json`、`landing/.portal.htpasswd`、`landing/brand-placeholder.html`。这些文件是否删除属于单独的远端静态资产清理决策，不能被 AI Video 发布默认清理。
- apex landing sidecar 的唯一手动同步入口是 `deploy/lighthouse/sync-landing-sidecars.sh`。该脚本默认 `DRY_RUN=1`，只同步 `index.html`、`login.html`、`register.html`、`systems.html`、`lute-auth.css`、`lute-auth.js`，不使用 `--delete`，不调用 `deploy.sh`，不重启容器，不触发生成接口。
- 该检查只读取本地脚本和配置，不触发生成接口、不访问生产、不消耗 poyo.ai tokens。

## 验证命令

```bash
.venv/bin/python -m pytest tests/test_lighthouse_rsync_artifact_guard.py -q
.venv/bin/python -m pytest tests/test_lighthouse_landing_static_contract.py -q
```

## 修改流程

1. 新增本地产物目录时，先更新 `deploy/lighthouse/rsync-excludes.txt`。
2. 同步更新 `configs/lighthouse-rsync-artifact-exclude-contract.yaml` 和测试里的分类清单。
3. 手工部署前先执行 `DRY_RUN=1 SSH_KEY=/path/to/ai_video.pem deploy/lighthouse/build-and-deploy.sh`。
4. dry-run 输出如出现 `.env.prod`、证书、`ai_video.pem`、`.next`、`web/playwright-report`、`tmp/screenshots`、`output`、`output_uploaded`、`backups`、`.codegraph`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/*.conf.*backup*`、`drafts`、`archive`、`ref`、`landing/login.html` 等路径，先修 exclude，不允许继续部署。
5. 如需同步 apex landing sidecar，不要取消默认发布排除项；改用：

```bash
SSH_KEY=/path/to/ai_video.pem DRY_RUN=1 deploy/lighthouse/sync-landing-sidecars.sh
SSH_KEY=/path/to/ai_video.pem DRY_RUN=0 deploy/lighthouse/sync-landing-sidecars.sh
```

该脚本只同步 landing 文件。运行后必须检查 `https://lute-tlz-dddd.top/`、`/systems.html`、`/login.html`、`/register.html`，并确认 `video.lute-tlz-dddd.top` 与 `voc.lute-tlz-dddd.top` 仍可访问。

## 相关文件

- `deploy/lighthouse/rsync-excludes.txt`
- `deploy/lighthouse/build-and-deploy.sh`
- `deploy/lighthouse/sync-landing-sidecars.sh`
- `.github/workflows/deploy.yml`
- `configs/lighthouse-rsync-artifact-exclude-contract.yaml`
- `tests/test_lighthouse_rsync_artifact_guard.py`
- `tests/test_lighthouse_landing_static_contract.py`
