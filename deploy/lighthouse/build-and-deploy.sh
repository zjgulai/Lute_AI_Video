#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# AI Video - 本地构建 + 上传到服务器部署
# 在本地 Mac 上执行
# ═══════════════════════════════════════════════════════════════

SERVER_IP="101.34.52.232"
SSH_KEY="/Users/pray/Downloads/ai_video.pem"
SSH_USER="root"
REMOTE_DIR="/opt/ai-video"

echo "========================================"
echo "  AI Video 本地构建 + 上传部署"
echo "========================================"
echo ""
echo "服务器: $SERVER_IP"
echo "用户:   $SSH_USER"
echo ""

# ── 1. 构建后端镜像 ──
echo "[1/5] 构建后端 Docker 镜像..."
docker build -f Dockerfile.backend -t ai-video-backend:latest .

# ── 2. 构建前端镜像 ──
echo "[2/5] 构建前端 Docker 镜像..."
docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://$SERVER_IP/api \
  -f web/Dockerfile \
  -t ai-video-frontend:latest \
  web/

# ── 3. 保存镜像为 tar ──
echo "[3/5] 导出镜像..."
docker save ai-video-backend:latest | gzip > /tmp/ai-video-backend.tar.gz
docker save ai-video-frontend:latest | gzip > /tmp/ai-video-frontend.tar.gz

# ── 4. 上传到服务器 ──
echo "[4/5] 上传镜像到服务器..."
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SSH_USER@$SERVER_IP" "mkdir -p $REMOTE_DIR/deploy/lighthouse"

scp -o StrictHostKeyChecking=no -i "$SSH_KEY" \
  /tmp/ai-video-backend.tar.gz \
  /tmp/ai-video-frontend.tar.gz \
  deploy/lighthouse/docker-compose.prod.yml \
  deploy/lighthouse/.env.prod \
  deploy/lighthouse/nginx.conf \
  deploy/lighthouse/deploy.sh \
  "$SSH_USER@$SERVER_IP:$REMOTE_DIR/"

# ── 5. 在服务器上加载镜像并启动 ──
echo "[5/5] 在服务器上加载并启动..."
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SSH_USER@$SERVER_IP" bash <> 'SCRIPT'
cd $REMOTE_DIR
docker load < ai-video-backend.tar.gz
docker load < ai-video-frontend.tar.gz
mv docker-compose.prod.yml deploy/lighthouse/
mv .env.prod deploy/lighthouse/
mv nginx.conf deploy/lighthouse/
chmod +x deploy.sh
bash deploy.sh
SCRIPT

# ── 清理 ──
rm -f /tmp/ai-video-backend.tar.gz /tmp/ai-video-frontend.tar.gz

echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""
echo "访问地址:"
echo "  http://$SERVER_IP"
echo ""
