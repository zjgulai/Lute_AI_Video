---
title: Lighthouse 生产部署指南
doc_type: workflow
module: deploy
topic: lighthouse-exact-image-deployment
status: stable
created: 2026-05-08
updated: 2026-08-13
owner: self
source: human+ai
---

# Lighthouse 生产部署指南

生产入口是 `https://video.lute-tlz-dddd.top`。本项目与多个站点共享远端 nginx sidecar；本地同步不得覆盖远端 `docker-compose.prod.yml`、`nginx.conf`、证书、认证配置或 landing 资产。

## 唯一发布模型

- 发布源必须是 clean、实时等于远端 `origin/main` tip 的 `main`，并绑定 40 位 `RELEASE_SOURCE_SHA`。
- `pyproject.toml` 是 semantic version SSOT；CI 先运行 `scripts/project_version.py --check`，再把 `APP_VERSION` 和 40 位 `RELEASE_SOURCE_SHA` 分别写入三个 image 的 OCI version/revision label。二者不能互相替代。
- CI 构建 backend/frontend/rendering 三个 SHA image，校验 version/revision label 和 backend runtime catalog，生成 SBOM、漏洞扫描、image ID、精确 image archive 及 SHA-256。服务器只 `docker load` 该 archive，不重新构建。
- exact source/image bundle 先经 private COS 中继下载到 run-bound `.incoming-<SHA>-<run>-<attempt>`；全量身份与 receipt 通过后，production approval 才允许原子 promotion 为 `/opt/ai-video/releases-<SHA>/`。已存在 final 目录或同 SHA image tag立即失败，禁止覆盖。
- SSH 只接受预先核验的 `known_hosts`。手工 wrapper 必须传 `SSH_KNOWN_HOSTS_FILE`；GitHub 必须配置 `DEPLOY_KNOWN_HOSTS`。禁止 `ssh-keyscan` 和 `StrictHostKeyChecking=accept-new`。
- production compose 使用 `name: lighthouse`、SHA image，backend 只挂载 `lighthouse_backend_output`；不 bind-mount `src/`、`requirements.txt`、`web/.next`。
- canonical deploy 永久为 provider-off：`RUN_TOKEN_SMOKE=0`、`RUN_DEPLOY_SMOKE=0`，不读取 API key，不调用生成、publish 或 delivery。

`ai_video_locations.conf` 仍是 AI Video 路由超时 SSOT：`/api/scenario/`、`/api/fast/`、`/api/pipeline/` 使用 `proxy_read_timeout 1500s`、`proxy_send_timeout 1500s`、`proxy_buffering off`。

## CI / GitHub 路径

`.github/workflows/deploy.yml` 的顺序不可交换：

1. backend/full frontend gate 和 compose config。
2. 三镜像 build、label/content 校验、SBOM、Critical 漏洞扫描、digest/archive artifact。
3. 只读 SSH + rsync `--dry-run --itemize-changes --delete`，上传删除清单 artifact。
4. GitHub Environment `production-artifact-staging` 人工批准；先硬校验 GitHub artifact ZIP digest，再启动一个 runner-monotonic 1,800 秒总期限，以临时 STS 核验 bucket 从未启用 versioning，并在任何完整 release object 上传前通过 64 MiB runner→COS 与 COS→Lighthouse 两腿探针。
5. 受限 forced-command gate 仅从 stdin 接收 signed GET URL；URL host 必须精确等于 manifest 中 `<bucket>.<regional-endpoint>`。runner remaining time 硬限制 probe/stage/receipt SSH pipeline，server deadline 继续覆盖下载后的 hash、archive/source 验证和 receipt commit。gate 拒绝既有 probe receipt/symlink；receipt、incoming mkdir 与 `.part` download 在 mutation 前建立 intent 并在受控 signal 屏蔽区记录 inode，提交后的失败只回滚同 inode、同身份状态，EEXIST winner 保留并稳定失败，foreign race、所有权不明或删除失败进入 manual recovery。随后 gate 在同文件系统 incoming transaction 下载并校验 canonical manifest bytes、source manifest、archives、image digests、SHA/size、archive member safety 和独立于 root umask 的 source mode contract，产生 canonical receipt。
6. `artifact-stage-only` 删除 verified incoming 并停止；`deploy` 则继续等待独立的 `production` 人工批准。
7. production job 复核未过期 receipt，把 verified incoming 原子 promotion 为 immutable final path；不从 GitHub runner 再次 rsync 2.28 GB archive。
8. 远端执行 provider-off `deploy.sh`。
9. HTTPS `/health` 必须同时满足 `status=ok`、`version` 等于候选 semantic version、`source_revision` 等于候选 SHA、`persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。
10. transfer step 的 EXIT handler 先删 probe 并补偿可能存在的 remote transaction；若 stage 的 evidence upload 随后失败，或 deploy job 未成功完成，独立 `cleanup-staged-release` job 仍会重新经过 staging Environment，只用受限 `TRANSFER_*` 身份清理精确未 promotion incoming 并上传终态证据；若 final 已存在或状态不明则以 `incoming_cleanup_failed` 失败关闭，不做广泛删除。

Tag 和 `workflow_dispatch` 都必须精确等于执行时的 `origin/main` tip；仅“属于 main ancestry”不够。

COS 只替换数据面，不替换 exact-image 审查。六个共享对象的 prefix 固定为 `ai-video/releases/<SHA>/<image-archive-sha256>/`，run-bound manifest 位于 `transactions/<run>/<attempt>/`；禁止 `latest`、branch alias 和 overwrite。bucket 必须从未启用 versioning；endpoint 必须精确为 `cos.<region>.myqcloud.com`，全部 signed URL 精确绑定 `<bucket>.<endpoint>`。仓库自有 Python client 使用 serial 64 MiB parts、Content-MD5/ETag、create-only completion，每个 HTTP request 恰一次 attempt，拒绝全部 redirect，失败时最多发一次 multipart abort。probe mutation intent 在 PUT 前设置，故 ambiguous response 也会触发 exact DELETE。一个 1,800 秒 monotonic 总期限贯穿 versioning/probe/upload/readback/stage/download 及下载后验证/receipt，runner timeout 防止 SSH 延迟重新获得预算；40 分钟 job limit 只预留补偿与 evidence 余量，信号和超时不得绕开清理。显式 resume 也必须先对每个共享对象做一字节 signed-range readback并核对总大小与 SHA-256/size metadata；只补传缺失对象，任何不一致都失败关闭。incoming 位于 root-owned `0700` `/var/lib/ai-video-release-transfer`；安装器在 immutable content-addressed version 目录中逐字节复验 contract/gate/canonical wrapper并实际做一次跨 staging/release roots 的 atomic no-replace 探针，全部通过后只以一次原子 pointer 替换对外生效，失败恢复旧 pointer，forced-command 不可观察 mixed runtime。installer 锁文件用 no-follow/no-truncate 方式打开并精确为单链接 `root:root:0600`；所有 root Python 辅助与运行 gate 使用 `-I`，installed gate 只加载同一 runtime 的 sibling contract，candidate 与 published runtime 从自身三份字节重算 content address。`/opt/ai-video` 必须保持非 symlink `root:root:0755`，并在 promotion 的 no-replace rename 紧邻前复验 device/inode。source path 还受 UTF-8 字节、单组件及 64 级深度硬上限约束；source file/dir mode 由 archive contract 规范化，promotion 前重算 source bytes、symlink target 和精确文件/目录集合，并在不可逆 rename 紧邻前再次验证 expiry。服务器 staging 身份不能 promotion，production 身份不能凭空创建 incoming。任何 URL、STS token 或 runner absolute path 都不得进入 receipt/evidence。

补偿 cleanup 不是无条件垃圾回收。GitHub 整体取消可能阻止后续 job 启动，同一 staging Environment 也可能要求再次人工批准；这两种情况必须保留 exact transaction 并明确报告“未清理”，随后只允许按 SHA/run/attempt/manifest 调受限 gate。COS lifecycle 只处理 bucket object，不能替代服务器 incoming cleanup。

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
