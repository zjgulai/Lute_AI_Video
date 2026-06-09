#!/usr/bin/env bash
# AI Video — Fast deploy script (host build + Docker run)
#
# Usage (run on the server):
#   cd /opt/ai-video/deploy/lighthouse
#   ./deploy.sh
#
# What it does:
#   1. Sync code from local machine (run rsync on your laptop first, see below)
#   2. Build frontend on host (reuses node_modules, ~30s incremental)
#   3. Recreate backend container (picks up new Python code + env_file)
#   4. Restart frontend container (picks up new .next/standalone via volume)
#   5. Health checks
#
# --- First time setup (run on server) ---
#   cd /opt/ai-video/web && npm ci
#
# --- Sync from laptop (run on your local machine) ---
#   rsync -avz --delete --chmod=F644,D755 \
#     -e "ssh -i ~/Downloads/ai_video.pem" \
#     --exclude-from='deploy/lighthouse/rsync-excludes.txt' \
#     ./ ubuntu@101.34.52.232:/opt/ai-video/
#   Or use the canonical wrapper:
#     SSH_KEY=~/Downloads/ai_video.pem DRY_RUN=1 deploy/lighthouse/build-and-deploy.sh
#     SSH_KEY=~/Downloads/ai_video.pem deploy/lighthouse/build-and-deploy.sh
#
# IMPORTANT: --chmod=F644 forces world-readable perms on rsync. Without it,
# any local file with mode 0600 (e.g. src/routers/admin.py historically) gets
# faithfully copied as 0600 to the server, where the backend container runs
# as `appuser` and cannot read it. Symptom: PermissionError: [Errno 13]
# /app/src/routers/admin.py at startup → 502 on /api/health.

set -euo pipefail

cd "$(dirname "$0")"
COMPOSE="sudo docker compose -f docker-compose.prod.yml"
REBUILD_BACKEND="${REBUILD_BACKEND:-0}"

# Deployment root (was hardcoded /opt/ai-video; now configurable)
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/ai-video}"

echo "========================================"
echo "  AI Video Fast Deploy"
echo "========================================"
echo ""

# -- Phase 0: requirements.txt rebuild check (2026-05-05 incident 教训) --
# requirements.txt 改了但 image 没 rebuild → backend 启动 ImportError → restart loop。
# 用 sha256 hash 比较本地 requirements.txt 与 image 中记录的 hash，比 mtime 更可靠。
echo "[0/5] requirements.txt rebuild check..."
cd ../..
LOCAL_REQ_SHA=$(sha256sum requirements.txt 2>/dev/null | awk '{print $1}')
IMG_REQ_SHA=$(sudo docker run --rm lighthouse-backend:latest cat /app/.requirements_sha256 2>/dev/null | awk '{print $1}')
cd deploy/lighthouse
if [ "$LOCAL_REQ_SHA" != "$IMG_REQ_SHA" ]; then
  echo "  ⚠ requirements.txt 与当前 backend image 不一致"
  echo "  ⚠ 本地 hash: ${LOCAL_REQ_SHA:-(无法计算)}"
  echo "  ⚠ 镜像 hash: ${IMG_REQ_SHA:-(首次部署或镜像不存在)}"
  if [ "$REBUILD_BACKEND" = "1" ]; then
    echo "  REBUILD_BACKEND=1 set; rebuilding backend image..."
    $COMPOSE build backend
    IMG_REQ_SHA=$(sudo docker run --rm lighthouse-backend:latest cat /app/.requirements_sha256 2>/dev/null | awk '{print $1}')
    if [ "$LOCAL_REQ_SHA" != "$IMG_REQ_SHA" ]; then
      echo "  ❌ backend rebuild finished but requirements hash still differs"
      echo "  ❌ 镜像 hash: ${IMG_REQ_SHA:-(无法计算)}"
      exit 1
    fi
    echo "  ✓ backend image rebuilt and requirements hash matched"
  else
    echo "  ❌ Aborted before container restart."
    echo "  ❌ Re-run with REBUILD_BACKEND=1 to rebuild backend image automatically."
    exit 1
  fi
else
  echo "  ✓ requirements.txt 与 backend image 一致"
fi
echo ""

# -- Phase 0.5: defensive chmod for backend src/ --
# rsync without --chmod can copy 0600 files (PermissionError 502 — see header).
# Belt-and-suspenders: normalize perms before backend restart so even a forgetful
# rsync survives. Cost: ~50ms. Benefit: never see /app/src/routers/admin.py 502 again.
echo "[0.5/5] Normalizing src/ file permissions..."
sudo find "$DEPLOY_ROOT/src" -type f -name '*.py' ! -perm 644 -exec chmod 644 {} \; 2>/dev/null || true
echo "  ✓ src/**.py normalized to 0644"
echo ""

# -- Phase 0.6: remove stale module files after package split --
# 2026-05-20: src/routers/admin.py was split into src/routers/admin/.
# If an incremental rsync left the old file on the server, Python may import
# the stale module instead of the package. Delete this one known legacy file.
echo "[0.6/5] Removing stale split-module files..."
sudo rm -f "$DEPLOY_ROOT/src/routers/admin.py"
echo "  ✓ stale src/routers/admin.py removed if present"
echo ""

# -- Phase 1: Build frontend on host --
echo "[1/5] Building frontend on host..."
cd ../../web
if [ ! -d "node_modules" ]; then
  echo "  ERROR: node_modules not found. Run 'npm ci' first."
  exit 1
fi

# Clean old build outputs to prevent stale chunk references.
# Turbopack content-hash filenames change on every build; leftover
# files from previous builds can confuse the deploy and lead to
# ChunkLoadError if an old HTML cached in a browser references them.
echo "  Cleaning old build artifacts..."
sudo rm -rf .next/standalone/ .next/static/ .next/server/ .next/*.json
# .next.old/ accumulates from previous deploys (next.js renames the prev
# .next to .next.old during build). Without explicit cleanup, eslint runs
# from CI pick up thousands of .next.old/ files. Disk + speed cost both.
sudo rm -rf .next.old/

export NEXT_PUBLIC_API_BASE_URL=/api
# P0-F: Lighthouse 是 canonical 非 demo 生产部署 — 必须设 false,
# 否则 web/src/app/page.tsx 会跳过真实 API 调用进 DEMO_RESULT_*,
# 与已验证的 5 场景非 demo 端到端结果冲突。
# GitHub Pages demo 部署单独构建脚本里设 true。
export NEXT_PUBLIC_IS_DEMO=false
unset NEXT_PUBLIC_API_KEY
npm run build 2>&1 | tail -5

# Verify build succeeded — critical files must exist
if [ ! -f ".next/standalone/server.js" ]; then
  echo "  ERROR: Build failed — .next/standalone/server.js not found"
  exit 1
fi
if [ ! -d ".next/static/chunks" ]; then
  echo "  ERROR: Build failed — .next/static/chunks/ not found"
  exit 1
fi
CHUNK_COUNT=$(ls .next/static/chunks/*.js 2>/dev/null | wc -l)
echo "  Build OK: $CHUNK_COUNT JS chunks generated"
echo "  Frontend build complete"
echo ""

# -- Phase 2: Restart containers --
echo "[2/5] Restarting containers..."
cd ../deploy/lighthouse
$COMPOSE up -d --force-recreate backend 2>&1 | tail -3
$COMPOSE up -d --force-recreate frontend 2>&1 | tail -3
# Recreate nginx to pick up nginx.conf changes AND volume mount changes.
# nginx locks inode at startup, so a file edit alone is not enough.
# --force-recreate is required when new volumes (e.g. proxy_params.conf)
# are added to docker-compose.prod.yml.
$COMPOSE up -d --force-recreate nginx 2>&1 | tail -3
echo "  Containers restarted"
echo ""

# -- Phase 3: Health checks --
echo "[3/5] Health checks..."

# Check backend
BACKEND_STATUS="000"
for attempt in $(seq 1 24); do
  BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --cacert /etc/letsencrypt/live/lute-tlz-dddd.top/fullchain.pem https://localhost/api/health || echo "000")
  if [ "$BACKEND_STATUS" = "200" ]; then
    echo "  Backend /api/health: 200 (attempt $attempt/24)"
    break
  fi
  if [ "$attempt" != "24" ]; then
    sleep 5
  fi
done
if [ "$BACKEND_STATUS" != "200" ]; then
  echo "  ❌ Backend /api/health: $BACKEND_STATUS"
  echo "  --- 最近 30 行 backend logs (定位启动失败原因) ---"
  sudo docker logs --tail 30 ai_video_backend 2>&1 | tail -30
  echo "  ----"
  echo "  ⚠ 如果是 ImportError → 跑 'docker compose build backend' 重 build"
  echo "  ⚠ 如果是 RuntimeError: PostgreSQL → 检查 .env.prod DATABASE_URL"
fi

# Check frontend
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k https://localhost/ || echo "000")
if [ "$FRONTEND_STATUS" = "200" ]; then
  echo "  Frontend /: 200"
else
  echo "  ❌ Frontend /: $FRONTEND_STATUS"
fi

# Check Fast Mode API only when explicitly requested.
# The generate endpoint can consume external provider credits, so deployment
# defaults to non-token health checks.
if [ "${RUN_TOKEN_SMOKE:-0}" = "1" ]; then
  DEPLOY_API_KEY="${API_KEY:-}"
  if [ -z "$DEPLOY_API_KEY" ] && [ -f ".env.prod" ]; then
    DEPLOY_API_KEY="$(grep -E '^API_KEY=' .env.prod | head -1 | cut -d= -f2- || true)"
  fi
  if [ -z "$DEPLOY_API_KEY" ]; then
    echo "  ❌ Fast Mode API token smoke requested but API_KEY is missing"
    FAST_STATUS="000"
  else
    FAST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k -X POST \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $DEPLOY_API_KEY" \
      -d '{"user_prompt":"test","duration":10}' \
      https://localhost/api/fast/generate || echo "000")
  fi
  if [ "$FAST_STATUS" = "200" ]; then
    echo "  Fast Mode API: 200"
  else
    echo "  ⚠ Fast Mode API: $FAST_STATUS (200/500 都可,500 = LLM 不可用但路径通)"
  fi
else
  echo "  Fast Mode API: skipped (set RUN_TOKEN_SMOKE=1 to run token smoke)"
fi
echo ""

# -- Phase 4: Cleanup (optional) --
echo "[4/5] Cleanup..."
sudo docker system prune -f 2>&1 | tail -1
sudo docker builder prune -f 2>&1 | tail -1
echo "  Cleanup done"
echo ""

# -- Phase 5: Run smoke.sh for full verification --
echo "[5/5] Running smoke.sh for full verification..."
if [ -f smoke.sh ]; then
  bash smoke.sh
else
  echo "  ⚠ smoke.sh not found,跳过"
fi
echo ""

echo "========================================"
echo "  Deploy complete!"
echo "========================================"
