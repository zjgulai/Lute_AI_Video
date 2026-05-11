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
#   3. Restart backend container (picks up new Python code via volume)
#   4. Restart frontend container (picks up new .next/standalone via volume)
#   5. Health checks
#
# --- First time setup (run on server) ---
#   cd /opt/ai-video/web && npm ci
#
# --- Sync from laptop (run on your local machine) ---
#   rsync -avz --chmod=F644,D755 -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./web/src/ ubuntu@101.34.52.232:/opt/ai-video/web/src/
#   rsync -avz --chmod=F644,D755 -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./src/ ubuntu@101.34.52.232:/opt/ai-video/src/
#   rsync -avz --chmod=F644,D755 -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./deploy/lighthouse/ ubuntu@101.34.52.232:/opt/ai-video/deploy/lighthouse/
#
# IMPORTANT: --chmod=F644 forces world-readable perms on rsync. Without it,
# any local file with mode 0600 (e.g. src/routers/admin.py historically) gets
# faithfully copied as 0600 to the server, where the backend container runs
# as `appuser` and cannot read it. Symptom: PermissionError: [Errno 13]
# /app/src/routers/admin.py at startup → 502 on /api/health.

set -euo pipefail

cd "$(dirname "$0")"
COMPOSE="sudo docker-compose -f docker-compose.prod.yml"

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
  echo "  ⚠ 强烈建议先 rebuild image,否则可能进 restart loop:"
  echo "      sudo docker compose -f docker-compose.prod.yml build backend"
  echo ""
  read -p "  继续 deploy 不 rebuild? [y/N] " -r REPLY
  if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "  Aborted. Run 'docker compose ... build backend' then re-run deploy.sh"
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
sudo find /opt/ai-video/src -type f -name '*.py' ! -perm 644 -exec chmod 644 {} \; 2>/dev/null || true
echo "  ✓ src/**.py normalized to 0644"
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
rm -rf .next/standalone/ .next/static/ .next/server/ .next/*.json

export NEXT_PUBLIC_API_BASE_URL=/api
# P0-F: Lighthouse 是 canonical 非 demo 生产部署 — 必须设 false,
# 否则 web/src/app/page.tsx 会跳过真实 API 调用进 DEMO_RESULT_*,
# 与已验证的 5 场景非 demo 端到端结果冲突。
# GitHub Pages demo 部署单独构建脚本里设 true。
export NEXT_PUBLIC_IS_DEMO=false
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
$COMPOSE restart backend 2>&1 | tail -3
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
sleep 5

# Check backend
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k https://localhost/api/health || echo "000")
if [ "$BACKEND_STATUS" = "200" ]; then
  echo "  Backend /api/health: 200"
else
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

# Check Fast Mode API
FAST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"user_prompt":"test","duration":10}' \
  https://localhost/api/fast/generate || echo "000")
if [ "$FAST_STATUS" = "200" ]; then
  echo "  Fast Mode API: 200"
else
  echo "  ⚠ Fast Mode API: $FAST_STATUS (200/500 都可,500 = LLM 不可用但路径通)"
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
