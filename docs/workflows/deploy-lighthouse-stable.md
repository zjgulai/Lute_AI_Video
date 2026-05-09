---
title: Lighthouse 生产部署指南
doc_type: workflow
module: deploy
status: stable
created: 2026-05-08
updated: 2026-05-08
owner: self
source: human+ai
---

### Production Deployment

The project ships three deploy targets, in priority order:

1. **Tencent Lighthouse (canonical)** — current production at `https://101.34.52.232`.
  `deploy/lighthouse/` contains `docker-compose.prod.yml` (backend + frontend + nginx +
   rendering), `nginx.conf` (with 1500s `proxy_read_timeout` for long-running pipelines),
   and `.env.prod` (live secrets — gitignored). Deploy via `rsync -e "ssh -i ai_video.pem"`
   to `ubuntu@101.34.52.232:/opt/ai-video/` then `docker compose up -d --force-recreate`.
   Note: rsync to bind-mounted nginx.conf needs `--inplace --no-whole-file`. **Do not use**
   `docker restart ai_video_nginx` for volume mount changes (e.g. adding `proxy_params.conf`);
   `restart` reuses the existing container and ignores new volume declarations in
   `docker-compose.prod.yml`. Always use `--force-recreate` for nginx when volumes change.
   Volume 命名:docker compose project = `lighthouse`(因为 compose 文件在
   `deploy/lighthouse/`),所以 backend output volume 是 `lighthouse_backend_output`,
   不是 `ai-video_backend_output`(后者是历史残留 volume,backend 不会读到)。任何
   `docker run -v <volume>:/...` 操作都要用 `lighthouse_backend_output`。
   2026-05-05 部署事故防御:`Dockerfile.backend` 配阿里云 PyPI mirror、`deploy.sh`
   Phase 0 hash 检测（`sha256sum requirements.txt` 本地 hash vs image 内记录 hash）、
   backend `restart: on-failure:5` 限制无限重启。完整时间线 + 紧急恢复三步法见
   `docs/workflows/incident-2026-05-05-postgres-saver-deploy-stable.md`。
   **2026-05-07 deploy.sh 更新**: 构建前清理 `.next/standalone/` `.next/static/`
   `.next/server/` 防止 Turbopack 旧 chunk 残留；构建后验证 `standalone/server.js`
   和 `static/chunks/` 存在；nginx 用 `--force-recreate` 确保 volume 挂载变更生效。
2. **Tencent CloudBase (alternative, China)** — see `deploy/tencent-cloudbase.md` and
  `deploy/CLOUDBASE_STEP_BY_STEP.md`. Container-typed cloud hosting, pay-as-you-go.
   Documented but not the live target.
3. **Render Blueprint (alternative, overseas)** — see `render.yaml`. Auto-deploy from
  GitHub, free tier available. Lands at `https://lute-ai-video-backend.onrender.com`.

