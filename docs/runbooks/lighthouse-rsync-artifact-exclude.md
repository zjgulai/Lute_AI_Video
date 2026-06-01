---
title: Lighthouse rsync artifact exclude guard
doc_type: workflow
module: deploy
topic: lighthouse-rsync-artifact-exclude
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Lighthouse rsync artifact exclude guard

## 目的

锁定 Lighthouse 同步边界，防止本地构建产物、Playwright 报告、截图、临时输出、coverage 和生产 secret 被 `rsync --delete` 同步到 `/opt/ai-video`。

## 不变量

- 唯一排除清单是 `deploy/lighthouse/rsync-excludes.txt`。
- `deploy/lighthouse/build-and-deploy.sh` 必须使用 `--exclude-from="$EXCLUDE_FILE"`。
- `.github/workflows/deploy.yml` 必须使用 `--exclude-from='deploy/lighthouse/rsync-excludes.txt'`，不得维护 inline exclude 副本。
- 必须排除 frontend build artifacts：`web/.next`、`web/.next.old`、`web/dist`。
- 必须排除 report / trace artifacts：`web/playwright-report`、`web/test-results`、`web/blob-report`。
- 必须排除 screenshots / tmp outputs：`tmp/screenshots`、`tmp/outputs`、`web/tmp`、`web/tmp/screenshots`。
- 必须排除 production secret / cert：`deploy/lighthouse/.env.prod`、`server.crt`、`server.key`、`*.pem`。
- 该检查只读取本地脚本和配置，不触发生成接口、不访问生产、不消耗 poyo.ai tokens。

## 验证命令

```bash
.venv/bin/python -m pytest tests/test_lighthouse_rsync_artifact_guard.py -q
```

## 修改流程

1. 新增本地产物目录时，先更新 `deploy/lighthouse/rsync-excludes.txt`。
2. 同步更新 `configs/lighthouse-rsync-artifact-exclude-contract.yaml` 和测试里的分类清单。
3. 手工部署前先执行 `DRY_RUN=1 SSH_KEY=/path/to/ai_video.pem deploy/lighthouse/build-and-deploy.sh`。
4. dry-run 输出如出现 `.env.prod`、证书、`.next`、`web/playwright-report`、`tmp/screenshots`、`output` 等路径，先修 exclude，不允许继续部署。

## 相关文件

- `deploy/lighthouse/rsync-excludes.txt`
- `deploy/lighthouse/build-and-deploy.sh`
- `.github/workflows/deploy.yml`
- `configs/lighthouse-rsync-artifact-exclude-contract.yaml`
- `tests/test_lighthouse_rsync_artifact_guard.py`
