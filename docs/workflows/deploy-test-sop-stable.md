---
title: 生产部署与 provider-off 验收 SOP
doc_type: workflow
module: deploy
status: stable
created: 2026-05-09
updated: 2026-07-20
owner: self
source: human+ai
---

# 生产部署与 provider-off 验收 SOP

本 SOP 只覆盖 exact reviewed image 的 provider-off Lighthouse 发布。真实生成、publish、delivery、生产数据修复和 schema downgrade 都是独立授权路径。

## 1. 发布前门禁

- 当前 checkout 是 clean `main`，`git rev-parse HEAD` 精确等于实时 `git ls-remote origin refs/heads/main`。
- backend `make ci`、S1-S5 hermetic regression、frontend Vitest/ESLint/TypeScript/OpenAPI/build、disposable PostgreSQL migration/recovery gate全部通过。
- CI 已构建 backend/frontend/rendering，输出并保留：revision label、runtime catalog probe、SBOM、Critical vulnerability scan、image ID、`release-images-<SHA>.tar.gz` 与 `.sha256`。扫描例外必须遵循 `docs/runbooks/vulnerability-scan-exceptions.md` 的精确版本绑定与失效规则。
- GitHub remote dry-run artifact 已审阅；没有 secret、certificate、remote-only sidecar 或 live-root deletion。
- `DEPLOY_KNOWN_HOSTS`/`SSH_KNOWN_HOSTS_FILE` 是预先核验的 host identity；禁止部署时 TOFU。
- 明确接受 AI Video 应用维护窗口。共享 nginx 与其他站点保持在线，但 AI Video backend 在备份、恢复演练、migration 和 app switch 期间不可用；这不是 zero-downtime blue/green。
- `RUN_TOKEN_SMOKE=0`、`RUN_DEPLOY_SMOKE=0`、`CLEANUP_AFTER_DEPLOY=0` 固定；canonical deploy 不允许覆盖。

## 2. GitHub canonical 执行

推荐通过 `.github/workflows/deploy.yml` 执行。workflow 必须先生成 source/image/SBOM/scan/dry-run artifacts，后进入 GitHub Environment `production` approval；approval 之后才允许创建远端 release dir、上传 exact archive 和运行 deploy。

GitHub secrets：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`、`DEPLOY_TARGET_DIR`、`DEPLOY_KNOWN_HOSTS`。不得在日志、文档或命令行回显 secret 内容。

## 3. 手工等价路径

```bash
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
DRY_RUN=1 \
deploy/lighthouse/build-and-deploy.sh
```

审阅 dry-run 后，使用同一个 SHA 和 CI exact image archive：

```bash
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
DRY_RUN=0 \
ALLOW_MAINTENANCE_WINDOW=1 \
RELEASE_SOURCE_SHA="$(git rev-parse HEAD)" \
RELEASE_IMAGE_ARCHIVE=/path/to/release-images-<SHA>.tar.gz \
deploy/lighthouse/build-and-deploy.sh
```

不要手写 rsync 到 `/opt/ai-video/`；不要从 server live root 运行旧 `deploy.sh`；不要重用 `releases-<SHA>`；不要在远端重新 build image。

## 4. deploy.sh 必须完成的证据

1. exact archive SHA-256通过，三个 image tag之前不存在，load 后 revision label等于 source SHA。
2. backend image 可读取 `/app/configs/provider-cost-catalog.v1.json` 并成功 `ProviderPriceCatalog.load_default()`。
3. `current` 指向上一 immutable release时，其 compose 与三镜像都存在；首次发布才接受 legacy fallback。
4. 共享 nginx 与 `portal_auth` 保持在线；只停止 AI Video rendering/backend，避免后台 DB 写和 output volume 写。
5. fresh backup 使用当前 release 的 `pg_dump_logical.py` 动态发现所有 public base tables（`alembic_version` 单独核验）；隔离 restore 的表清单、行数和 Alembic revision 精确匹配，并生成与本次 backup 绑定的 `restore_verified.json`。
6. candidate image 执行 schema-first migration；`alembic current` 精确等于唯一 head。
7. 入口关闭时，新 backend/frontend/rendering 健康。backend persistence 必须是 verified PostgreSQL；rendering Remotion/ffmpeg/Chromium 必须全部 ready。
8. 共享 `ai_video_locations.conf` 已备份；reviewed snippet 经 `nginx -t` 后 reload，严格 TLS HTTPS health 仍满足完整 persistence readiness。
9. `/opt/ai-video/current` 只在全部通过后更新；不执行通用 prune。

## 5. 上线后 L3 只读验收

- canonical homepage、`/health`、主要前端路由返回预期状态。
- `/health`：`status=ok`、`persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。
- rendering `/health`：HTTP 200、Remotion version 非空、`ffmpeg=true`、`chromium=true`。
- 无 key 的受保护 mutation route 返回 401/403；不得为了验收提交生成、publish 或 delivery。
- backend/frontend/rendering/nginx container健康；restart count与部署前基线对比，没有新增 crash loop。
- backend/nginx最近日志没有 migration、schema、permission、import、secret 或 provider attempt错误。
- `current` 指向本次 `releases-<SHA>`；三容器 image revision label 与 SHA 一致。

## 6. 失败与回滚

- backup/restore/migration 前后、应用切换前失败：只重新启动之前停止的旧 rendering/backend；不重建共享 nginx 或 `portal_auth`。
- app 或 location snippet 切换后失败：从部署开始前的 `current` 读取 previous SHA，使用 previous release compose/tag 恢复 rendering/backend/frontend；首次发布才使用 legacy compose，并恢复备份的 AI Video snippet 后 `nginx -t` + reload。
- rollback 后必须再次验证 application health、public HTTPS health和 PostgreSQL tables。复验失败必须输出 `ROLLBACK_FAILED`，不得报告上线成功。
- schema migration是 additive 前提；binary rollback不自动 downgrade schema。任何 destructive downgrade另走数据授权。
- 不重建或重启 `portal_auth` 和共享 nginx sidecars；不删除 previous images。

## 7. 历史事故保留的强制规则

- rsync 必须使用共享 `rsync-excludes.txt`、GNU rsync 3.x和 `--chmod=F644,D755`；远端 certificate、`.env.prod`、`portal-auth`、nginx shared configs和 landing assets是 remote-only。
- Python re-export 文件的 Ruff修改必须人工审阅，避免 F401 auto-fix造成 production ImportError。
- `lighthouse_backend_output` 是 canonical volume；uid/permission异常会导致媒体写失败。
- nginx volume声明变化必须 recreate容器，普通 restart不会加载新 mount。
- HTTP 500只是 reachability证据，不是 business success。provider-backed smoke只接受 HTTP 200。

## 8. 完成判定

只有本地/CI门禁、独立六维复核、provider-off deploy exit 0、L3只读生产验收和 rollback evidence均完成，才能声明上线成功。未执行真实 provider mutation时必须明确记录 `provider_call=false`；这不妨碍 provider-off系统发布成功，但不能声称真实 AI 生成已在线通过。
