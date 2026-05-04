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
#   rsync -avz -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./web/src/ ubuntu@101.34.52.232:/opt/ai-video/web/src/
#   rsync -avz -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./src/ ubuntu@101.34.52.232:/opt/ai-video/src/
#   rsync -avz -e "ssh -i ~/Downloads/ai_video.pem" \
#     ./deploy/lighthouse/ ubuntu@101.34.52.232:/opt/ai-video/deploy/lighthouse/

set -euo pipefail

cd "$(dirname "$0")"
COMPOSE="sudo docker-compose -f docker-compose.prod.yml"

echo "========================================"
echo "  AI Video Fast Deploy"
echo "========================================"
echo ""

# -- Phase 1: Build frontend on host --
echo "[1/4] Building frontend on host..."
cd ../../web
if [ ! -d "node_modules" ]; then
  echo "  ERROR: node_modules not found. Run 'npm ci' first."
  exit 1
fi
export NEXT_PUBLIC_API_BASE_URL=/api
# P0-F: Lighthouse 是 canonical 非 demo 生产部署 — 必须设 false,
# 否则 web/src/app/page.tsx 会跳过真实 API 调用进 DEMO_RESULT_*,
# 与已验证的 5 场景非 demo 端到端结果冲突。
# GitHub Pages demo 部署单独构建脚本里设 true。
export NEXT_PUBLIC_IS_DEMO=false
npm run build 2>&1 | tail -5
echo "  Frontend build complete"
echo ""

# -- Phase 2: Restart containers --
echo "[2/4] Restarting containers..."
cd ../deploy/lighthouse
$COMPOSE restart backend 2>&1 | tail -3
$COMPOSE up -d --force-recreate frontend 2>&1 | tail -3
echo "  Containers restarted"
echo ""

# -- Phase 3: Health checks --
echo "[3/4] Health checks..."
sleep 3

# Check backend
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k https://localhost/api/health || echo "000")
if [ "$BACKEND_STATUS" = "200" ]; then
  echo "  Backend /api/health: 200"
else
  echo "  Backend /api/health: $BACKEND_STATUS"
fi

# Check frontend
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -k https://localhost/ || echo "000")
if [ "$FRONTEND_STATUS" = "200" ]; then
  echo "  Frontend /: 200"
else
  echo "  Frontend /: $FRONTEND_STATUS"
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
  echo "  Fast Mode API: $FAST_STATUS"
fi
echo ""

# -- Phase 4: Cleanup (optional) --
echo "[4/4] Cleanup..."
sudo docker system prune -f 2>&1 | tail -1
sudo docker builder prune -f 2>&1 | tail -1
echo "  Cleanup done"
echo ""

echo "========================================"
echo "  Deploy complete!"
echo "========================================"
