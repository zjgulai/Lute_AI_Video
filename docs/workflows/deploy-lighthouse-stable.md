---
title: Lighthouse 生产部署指南
doc_type: workflow
module: deploy
topic: lighthouse-exact-image-deployment
status: stable
created: 2026-05-08
updated: 2026-08-12
owner: self
source: human+ai
---

# Lighthouse 生产部署指南

生产入口是 `https://video.lute-tlz-dddd.top`。本项目与多个站点共享远端 nginx sidecar；本地同步不得覆盖远端 `docker-compose.prod.yml`、`nginx.conf`、证书、认证配置或 landing 资产。

## 唯一发布模型

- 发布源必须是 clean、实时等于远端 `origin/main` tip 的 `main`，并绑定 40 位 `RELEASE_SOURCE_SHA`。
- `pyproject.toml` 是 semantic version SSOT；CI 先运行 `scripts/project_version.py --check`，再把 `APP_VERSION` 和 40 位 `RELEASE_SOURCE_SHA` 分别写入三个 image 的 OCI version/revision label。二者不能互相替代。
- CI 构建 backend/frontend/rendering 三个 SHA image，校验 version/revision label 和 backend runtime catalog，生成 SBOM、漏洞扫描、image ID、精确 image archive 及 SHA-256。服务器只 `docker load` 该 archive，不重新构建。
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
7. HTTPS `/health` 必须同时满足 `status=ok`、`version` 等于候选 semantic version、`source_revision` 等于候选 SHA、`persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。

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

## 远端十阶段

1. 校验 compose、secrets 引用、exact archive checksum、previous rollback source。
2. 拒绝同 SHA tag，加载 CI-reviewed archive，核对三个 image 的 semantic-version 与 revision label 和 provider catalog。
3. 保存 root crontab 与 root-owned backup runtime，迁移为 disabled managed cron，并取得真实 backup lock，证明没有在途 scheduled job。
4. 保持共享 nginx 与 `portal_auth` 在线，只停止 AI Video 的 rendering/backend，进入受控应用维护窗口；这不是 zero-downtime blue/green，不得称为 atomic zero-downtime。
5. 使用 candidate image 的无应用 helper 和 release 自带动态表发现 dump helper 创建 fresh backup，并恢复到 digest-pinned isolated PostgreSQL；表清单、行数和 Alembic revision 必须与 `restore_verified.json` 精确一致。
6. 通过 candidate image 显式执行 `deploy_alembic_gate.sh --apply`，再核对唯一 Alembic head。
7. 入口仍关闭时切 backend/frontend/rendering；backend 必须验证 PostgreSQL、required tables，rendering 必须验证 Remotion/ffmpeg/Chromium。
8. 备份共享 `ai_video_locations.conf`，只替换 AI Video location snippet；`nginx -t` 通过后 reload 共享 nginx，再验证严格 TLS 公网 persistence readiness。失败时恢复该 snippet 并再次 reload，不重建共享 sidecar。
9. 原子更新 `/opt/ai-video/current`，启用并验证以该指针为 SSOT 的 managed backup schedule，再提交 schedule rollback transaction。
10. 禁止通用 Docker prune，保留当前和上一版本镜像供离线回滚。

候选 application/public health 必须同时匹配 `APP_VERSION` 与
`RELEASE_SOURCE_SHA`。由本规则发布的上一 immutable release 在 rollback
时执行同样的双身份复验；首次升级前的 legacy release 没有
`source_revision` 字段，只能走明确标记的过渡兼容 rollback 健康检查，
不能据此声称旧 release 已具备双身份闭环。

切换前失败只启动之前停止的旧 rendering/backend，不重建应用或共享 sidecar。切换后失败优先使用 `current` 指向的上一 immutable release；首次发布才 fallback 到 preserved legacy compose。新候选始终执行严格的 `/app/healthcheck.mjs`；只有已冻结的 ACTIVE rollback 镜像缺少该能力时，才允许使用结构化 legacy `/health` 探针，并同时核验 `status=ok`、Remotion 版本以及 ffmpeg/Chromium readiness。两条 rollback 都不触碰 `portal_auth` 或重建共享 nginx，并必须恢复 AI Video snippet、reload nginx、复验 application/public health。

进入维护窗口并停止 backend 前，部署会先保存 root crontab 与 root-owned backup runtime，再用当前 exact release 的 `install_backup_cron.sh` 显式迁移 legacy job、执行 `MODE=verify`。managed cron 成为 `CRON_ENABLED=0` 后，部署还必须对实际备份脚本的 `${BACKUP_ROOT}/.backup.lock` 执行非阻塞 `flock` 探针；只有取得锁并证明没有在途 job 后才可停止 backend，从而避免 03:00 并发。部署通过已安装 runtime 创建 scheduled-style canonical backup；动态业务表集合必须与隔离恢复 `actual_counts` 完全一致。只有候选 application/public health 和 `current` 指针原子切换成功后，才允许以 `/opt/ai-video/current` 为 SSOT 执行 `CRON_ENABLED=1` 的 install+verify。任何安装、备份、恢复、migration、切换、schedule 激活或事务提交失败都会恢复原应用、指针、crontab/runtime。post-pointer 回滚必须先把候选 schedule 重新置为 disabled，再恢复 current 和原应用；恢复原 schedule 时还必须先校验 snapshot marker 与 runtime source，将 runtime 复制到同文件系统 staging 并逐字节校验，保留 candidate runtime 作为回退，安全切换并复验成功后，最后才恢复和逐字节验证原 crontab。任何 runtime source/copy/swap/verify、原 runtime 缺失分支的竞争检查或 crontab restore/verify 失败，都必须显式核验清理与 candidate runtime 回迁、保持 managed cron disabled 并保留事务 snapshot。只有 runtime 回迁和 disabled schedule 的 install+verify 均确认成功，日志才允许声明 disabled candidate 已保留；主 swap/verify 早退或任一后续补偿再次失败都必须报告 `BACKUP_SCHEDULE_STATE_UNKNOWN`，不得推断 cron/runtime 安全状态，必须保留 snapshot、停止自动处置并进入人工恢复。schedule 静默化或 current 恢复失败时不得切回原应用或重新启用原任务，必须保持候选应用/current 一致、尽可能保持 schedule disabled，并保留事务快照供人工处置。原应用回滚健康检查失败时同样不得重新启用 schedule。成功后才删除事务快照；因此一次标记为 complete 但缺 canonical manifest、detached checksum、restore marker 或完整动态表覆盖的旧日备不能充当发布恢复证据。

## 验收边界

部署本身只证明 provider-off 应用、数据库 schema、rendering runtime、路由与认证 guard。`smoke.sh` 只允许无 key、严格 TLS 的 public health/identity/401 检查，不含任何 provider POST。真实 AI 生成必须使用独立的 W5/exact-authorization executor。

替代目标 Tencent CloudBase 和 Render Blueprint 不是当前 canonical production，未经同等级复验不得代替 Lighthouse 证据。
