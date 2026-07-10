---
title: Lighthouse 生产部署指南
doc_type: workflow
module: deploy
status: stable
created: 2026-05-08
updated: 2026-07-10
owner: self
source: human+ai
---

### Production Deployment

The project ships three deploy targets, in priority order:

1. **Tencent Lighthouse (canonical)** — current production at `https://video.lute-tlz-dddd.top`.
   IP fallback is `https://101.34.52.232`. `deploy/lighthouse/` contains
   `docker-compose.prod.yml` (backend + frontend + nginx +
   rendering), `nginx.conf` (server blocks) and `ai_video_locations.conf`
   (shared AI Video route rules; `/api/scenario/`, `/api/fast/`, and `/api/pipeline/`
   keep `proxy_read_timeout 1500s`, `proxy_send_timeout 1500s`, and
   `proxy_buffering off` for long-running pipelines),
   `.env.prod` (live secrets — gitignored), `rsync-excludes.txt` (single source of truth for
   safe sync exclusions), `build-and-deploy.sh` (local safe sync wrapper), and `deploy.sh`
   (remote host build + container restart). Deploy from the local repo root via
   `SSH_KEY=/path/to/ai_video.pem DRY_RUN=1 deploy/lighthouse/build-and-deploy.sh`, confirm the
   dry-run has no unsafe `deleting ...` lines, then run
   `SSH_KEY=/path/to/ai_video.pem deploy/lighthouse/build-and-deploy.sh`.
   Note: rsync to bind-mounted nginx.conf needs `--inplace --no-whole-file`. **Do not use**
   `docker restart ai_video_nginx` for volume mount changes (e.g. adding `proxy_params.conf`);
   `restart` reuses the existing container and ignores new volume declarations in
   `docker-compose.prod.yml`. Always use `--force-recreate` for nginx when volumes change.
   Volume 命名:docker compose project = `lighthouse`(因为 compose 文件在
   `deploy/lighthouse/`),所以 backend output volume 是 `lighthouse_backend_output`,
   不是 `ai-video_backend_output`(后者是历史残留 volume,backend 不会读到)。任何
   `docker run -v <volume>:/...` 操作都要用 `lighthouse_backend_output`。
	   2026-05-05 部署事故防御:`Dockerfile.backend` 配阿里云 PyPI mirror、`deploy.sh`
	   Phase 0 semantic hash 检测（忽略 `requirements.txt` 注释/空行后比较依赖内容）、
	   backend `restart: on-failure:5` 限制无限重启。完整时间线 + 紧急恢复三步法见
	   `docs/workflows/incident-2026-05-05-postgres-saver-deploy-stable.md`。
   **2026-05-07 deploy.sh 更新**: 构建前清理 `.next/standalone/` `.next/static/`
   `.next/server/` 防止 Turbopack 旧 chunk 残留；构建后验证 `standalone/server.js`
   和 `static/chunks/` 存在；nginx 用 `--force-recreate` 确保 volume 挂载变更生效。
   **2026-05-20 admin 拆包更新**: `src/routers/admin.py` 已拆为 `src/routers/admin/`
   包。部署同步必须带 `--delete`，且 `deploy.sh` 会额外删除服务器上的旧
   `/opt/ai-video/src/routers/admin.py`，防止 stale module 抢占 import。
   **2026-05-27 部署同步治理**: `build-and-deploy.sh` 成为唯一推荐的手工同步入口；
   安全排除规则集中在 `deploy/lighthouse/rsync-excludes.txt`，覆盖 `.env.prod`、证书、
   pem、根层 `node_modules`、缓存目录、测试报告、`web/dist`、`web/.next`、`output` 和
   `*.bak*`。`deploy.sh` 的 backend health check 改为最多 120 秒轮询，避免启动窗口内的
   502 误报。
   **2026-05-31 部署安全更新**: `deploy.sh` 和 `smoke.sh` 默认不调用
   `/api/fast/generate`，避免未充值或不希望消耗外部额度时触发真实生成。充值后如需验证
   真实生成链路，显式执行
   `RUN_TOKEN_SMOKE=1 API_KEY=... BASE=https://video.lute-tlz-dddd.top bash smoke.sh`。
   **2026-07-09 部署硬化**: `Dockerfile.backend` 通过 `TORCH_WHEEL_VERSION`
   和 `TORCH_WHEEL_INDEX_URL` build args 将生产镜像默认收敛到 torch CPU wheel；
   `deploy.sh` 在 nginx `--force-recreate` 后先等待 `nginx -t` 和
   `https://localhost/` 200，再进入 backend/frontend/rendering health checks 和
   `smoke.sh`。同日发现 Lighthouse 共享入口还承载 `flowise`、BOS、Reddit
   等跨项目路由；默认 `build-and-deploy.sh` 已排除远端
   `docker-compose.prod.yml` 和 `nginx.conf`，避免 AI Video 发布覆盖共享入口。
   如需同步这两个文件，必须单独 dry-run、diff 审核并确认跨项目路由影响。
   最近一次部署验证：`/` 200、`/api/health` 200、`persistence.backend=postgresql`、
   `POST /api/pipeline/start` 无 key 返回 401。
   **2026-07-10 rendering 构建韧性**: `rendering/Dockerfile` 保留官方 Alpine 源
   作为默认值，并接受 `ALPINE_MIRROR` build arg；Lighthouse `deploy.sh` 仅在
   `REBUILD_RENDERING=1` 时传入 `RENDERING_ALPINE_MIRROR`（默认
   `https://mirrors.cloud.tencent.com/alpine`）。该设置只影响构建时系统包下载，
   不修改宿主机 Docker 配置、不读取生产 secret，也不触发 provider 调用。
2. **Tencent CloudBase (alternative, China)** — see `deploy/tencent-cloudbase.md` and
  `deploy/CLOUDBASE_STEP_BY_STEP.md`. Container-typed cloud hosting, pay-as-you-go.
   Documented but not the live target.
3. **Render Blueprint (alternative, overseas)** — see `render.yaml`. Auto-deploy from
  GitHub, free tier available. Lands at `https://lute-ai-video-backend.onrender.com`.
