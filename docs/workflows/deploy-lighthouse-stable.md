---
title: Lighthouse 生产部署指南
doc_type: workflow
module: deploy
status: stable
created: 2026-05-08
updated: 2026-07-20
owner: self
source: human+ai
---

# Lighthouse 生产部署指南

生产入口是 `https://video.lute-tlz-dddd.top`。本项目与多个站点共享远端 nginx sidecar；本地同步不得覆盖远端 `docker-compose.prod.yml`、`nginx.conf`、证书、认证配置或 landing 资产。

## 唯一发布模型

- 发布源必须是 clean、实时等于远端 `origin/main` tip 的 `main`，并绑定 40 位 `RELEASE_SOURCE_SHA`。
- CI 构建 backend/frontend/rendering 三个 SHA image，校验 revision label 和 backend runtime catalog，生成 SBOM、漏洞扫描、image ID、精确 image archive 及 SHA-256。服务器只 `docker load` 该 archive，不重新构建。
- source 同步到全新 `/opt/ai-video/releases-<SHA>/`；已存在目录或同 SHA image tag立即失败，禁止覆盖。
- SSH 只接受预先核验的 `known_hosts`。手工 wrapper 必须传 `SSH_KNOWN_HOSTS_FILE`；GitHub 必须配置 `DEPLOY_KNOWN_HOSTS`。禁止 `ssh-keyscan` 和 `StrictHostKeyChecking=accept-new`。
- production compose 使用 `name: lighthouse`、SHA image，backend 只挂载 `lighthouse_backend_output`；不 bind-mount `src/`、`requirements.txt`、`web/.next`。
- canonical deploy 永久为 provider-off：`RUN_TOKEN_SMOKE=0`、`RUN_DEPLOY_SMOKE=0`，不读取 API key，不调用生成、publish 或 delivery。

`ai_video_locations.conf` 仍是 AI Video 路由超时 SSOT：`/api/scenario/`、`/api/fast/`、`/api/pipeline/` 使用 `proxy_read_timeout 1500s`、`proxy_send_timeout 1500s`、`proxy_buffering off`。

## CI / GitHub 路径

`.github/workflows/deploy.yml` 的顺序不可交换：

1. backend/full frontend gate 和 compose config。
2. 三镜像 build、label/content 校验、SBOM、Critical 漏洞扫描、digest/archive artifact。
3. 只读 SSH + rsync `--dry-run --itemize-changes --delete`，上传删除清单 artifact。
4. GitHub Environment `production` 人工批准。
5. 再次确认 release dir 不存在，创建目录，同步 source 与 exact image archive。
6. 远端执行 provider-off `deploy.sh`。
7. HTTPS `/health` 必须同时满足 `status=ok`、`persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。

Tag 和 `workflow_dispatch` 都必须精确等于执行时的 `origin/main` tip；仅“属于 main ancestry”不够。

## 手工路径

手工 live 也必须使用 CI 产出的 exact image archive；不能在服务器重新 build：

```bash
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
DRY_RUN=1 \
deploy/lighthouse/build-and-deploy.sh

SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
DRY_RUN=0 \
ALLOW_MAINTENANCE_WINDOW=1 \
RELEASE_SOURCE_SHA="$(git rev-parse HEAD)" \
RELEASE_IMAGE_ARCHIVE=/path/to/release-images-<SHA>.tar.gz \
deploy/lighthouse/build-and-deploy.sh
```

`DRY_RUN=1` 不创建 release dir。live 前必须审阅 deletion artifact，并明确接受维护窗口；wrapper 会实时执行 `git ls-remote origin refs/heads/main`，不会信任可能陈旧的 local remote-tracking ref。

## 远端八阶段

1. 校验 compose、secrets 引用、exact archive checksum、previous rollback source。
2. 拒绝同 SHA tag，加载 CI-reviewed archive，核对三个 revision label 和 provider catalog。
3. 保持共享 nginx 与 `portal_auth` 在线，只停止 AI Video 的 rendering/backend，进入受控应用维护窗口；这不是 zero-downtime blue/green，不得称为 atomic zero-downtime。
4. 使用 candidate image 的无应用 helper 和 release 自带动态表发现 dump helper 创建 fresh backup，并恢复到 digest-pinned isolated PostgreSQL；表清单、行数和 Alembic revision 必须与 `restore_verified.json` 精确一致。
5. 通过 candidate image 显式执行 `deploy_alembic_gate.sh --apply`，再核对唯一 Alembic head。
6. 入口仍关闭时切 backend/frontend/rendering；backend 必须验证 PostgreSQL、required tables，rendering 必须验证 Remotion/ffmpeg/Chromium。
7. 备份共享 `ai_video_locations.conf`，只替换 AI Video location snippet；`nginx -t` 通过后 reload 共享 nginx，再验证严格 TLS 公网 persistence readiness。失败时恢复该 snippet 并再次 reload，不重建共享 sidecar。
8. 原子更新 `/opt/ai-video/current`。通用 Docker prune 被禁用，保留当前和上一版本镜像供离线回滚。

切换前失败只启动之前停止的旧 rendering/backend，不重建应用或共享 sidecar。切换后失败优先使用 `current` 指向的上一 immutable release；首次发布才 fallback 到 preserved legacy compose。两条 rollback 都不触碰 `portal_auth` 或重建共享 nginx，并必须恢复 AI Video snippet、reload nginx、复验 application/public health。

## 验收边界

部署本身只证明 provider-off 应用、数据库 schema、rendering runtime、路由与认证 guard。真实 AI 生成不属于 deploy smoke；如之后需要，必须使用独立 exact-authorization harness。`smoke.sh` 中任何 provider-backed probe 只有 HTTP 200 才算 business success，HTTP 500 必须失败。

替代目标 Tencent CloudBase 和 Render Blueprint 不是当前 canonical production，未经同等级复验不得代替 Lighthouse 证据。
