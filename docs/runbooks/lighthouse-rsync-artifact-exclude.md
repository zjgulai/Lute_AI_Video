---
title: Lighthouse rsync artifact exclude guard
doc_type: workflow
module: deploy
topic: lighthouse-rsync-artifact-exclude
status: stable
created: 2026-06-01
updated: 2026-07-21
owner: self
source: human+ai
---

# Lighthouse rsync artifact exclude guard

## 目的

锁定 Lighthouse 同步边界，防止本地构建产物、Playwright 报告、截图、临时输出、草稿/归档材料、本地工作态目录、参考截图、生产 secret 和未跟踪的 remote-only production sidecars 进入新的不可变 release 目录。Canonical rsync 目标是发布前必须不存在的 `/opt/ai-video/releases-$SHA`，不是共享根 `/opt/ai-video`。

## 不变量

- 唯一排除清单是 `deploy/lighthouse/rsync-excludes.txt`。
- source manifest 中的每个 tracked 路径都必须被 canonical rsync 传入新的不可变 release 目录；测试必须执行真实 manifest → rsync → validate 闭环。
- canonical rsync 必须使用 NUL-safe `git ls-files -z` 生成的精确 `--files-from --from0` 白名单，并额外加入生成的 `source-manifest.v1.json`。ignored/untracked 文件即使存在于 clean worktree，也不得进入 release。
- `--from0` 会同时改变 `--files-from` 与 `--exclude-from` 的分隔语义；因此 canonical
  wrapper/workflow 必须先把换行格式的共享排除清单转换成 mode-0600 的 NUL-delimited
  临时文件，再通过 `--exclude-from` 传给 rsync。不得把换行格式清单直接与 `--from0`
  混用；测试必须断言无 `discarding over-long filter` 且显式列入 file list 的
  `.env.local`、`private.key` 仍被排除。
- `deploy/lighthouse/build-and-deploy.sh` 必须使用 GNU rsync 3.x 执行 `--chmod=F644,D755`；在 macOS 上优先选择 `/opt/homebrew/bin/rsync` 或 `/usr/local/bin/rsync`，也允许 `RSYNC_BIN=/path/to/rsync` 覆盖。
- `.github/workflows/deploy.yml` 必须从
  `deploy/lighthouse/rsync-excludes.txt` 生成 NUL-delimited 临时排除表，不得维护
  inline exclude 副本。
- 必须排除 frontend build artifacts：`web/.next`、`web/.next.old`、`web/dist`。
- 必须排除 report / trace artifacts：`.playwright-cli`、`web/playwright-report`、`web/test-results`、`web/blob-report`。
- 必须排除 screenshots / tmp outputs：`tmp/screenshots`、`tmp/outputs`、`web/tmp`、`web/tmp/screenshots`、`output_uploaded`。
- 必须排除 local workspace state：`*.sqlite3`、`.codegraph`、`.hermes`、`worktrees`、`drafts`、`archive`、`ref`。本地账本或测试数据库不得进入 release sync。
- 必须排除 production secret / cert：`.env`、`.env.local`、`.env.production`、`.env.prod`、`*.pem`、`*.key`、`*.crt`、`deploy/lighthouse/.env.prod`、`deploy/lighthouse/.portal-auth.env`、`server.crt`、`server.key`。
- `deploy/lighthouse/plugin-hub.htpasswd` 是 remote-only production authentication sidecar，必须由共享 exclude SSOT 保护，不能被 AI Video 发布覆盖或删除。
- 必须排除未跟踪或 secret-bearing 的 remote-only production sidecars：`backups`、`deploy/lighthouse/backups`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/plugin-hub.htpasswd`、`deploy/lighthouse/*.conf.*backup*`、`deploy/lighthouse/*.candidate`。
- tracked 的 `deploy/lighthouse/docker-compose.prod.yml`、`deploy/lighthouse/nginx.conf`、`landing/login.html`、`landing/register.html`、`landing/systems.html`、`landing/lute-auth.css`、`landing/lute-auth.js` 只作为已审查 source copy 进入新的不可变 release 目录。`deploy.sh` 不得把这些副本复制到共享根；真实 shared-root sidecar 仍只由独立入口管理。
- 仍须排除未跟踪的 remote-only landing sidecars：`landing/lute-*.html`、`landing/voc-zh_messages.json`、`landing/.portal.htpasswd`、`landing/brand-placeholder.html`。
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
   Wrapper 只接受 clean、与 `origin/main` 同步的 `main`；默认 dry-run。真实部署必须显式
   `DRY_RUN=0 RELEASE_SOURCE_SHA="$(git rev-parse HEAD)"`，绑定已复核 source SHA。
   - dry-run 若出现 `deploy/lighthouse/plugin-hub.htpasswd`，先修复 exclude 边界，不允许继续部署。
4. dry-run 输出如出现 `.env.local`、`.env.production`、`.env.prod`、证书、私钥、`*.sqlite3`、`.next`、`.playwright-cli`、`web/playwright-report`、`tmp/screenshots`、`output`、`output_uploaded`、`backups`、`.codegraph`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/*.conf.*backup*`、`deploy/lighthouse/*.candidate`、`drafts`、`archive`、`ref` 等路径，先修 file-list/exclude 边界，不允许继续部署。tracked source-copy sidecars 出现在新的 `releases-$SHA` 目录是预期行为，但不得出现在共享根更新命令中。
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
