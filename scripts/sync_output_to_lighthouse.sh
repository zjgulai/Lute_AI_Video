#!/usr/bin/env bash
# 一次性把本地 output/ 镜像到 Lighthouse 服务器的 backend_output Docker volume。
#
# 架构上 backend 容器 mount 的是 named volume(backend_output:/app/output),
# host 路径不直接通向 nginx /api/media。所以:
#   1. rsync 把本地 output/ 上传到 host /opt/ai-video/output_uploaded/
#   2. ssh 到服务器 docker cp 把内容复制进 backend_output volume
#   3. 验证 GET /api/media/<sample> 返回 200
#
# Usage:
#   ./scripts/sync_output_to_lighthouse.sh --dry-run  # 看要同步哪些文件,不实际跑
#   ./scripts/sync_output_to_lighthouse.sh           # 真实同步
#
# 依赖:
#   - ~/Downloads/ai_video.pem (与 deploy/lighthouse/build-and-deploy.sh 一致)
#   - 本地 output/ 已有要上传的文件

set -euo pipefail

SERVER_IP="101.34.52.232"
SSH_USER="ubuntu"
# 先看仓库根 ./ai_video.pem(.gitignore 已排除),fallback 到 ~/Downloads/
if [ -f "$(dirname "$0")/../ai_video.pem" ]; then
  SSH_KEY="$(cd "$(dirname "$0")/.." && pwd)/ai_video.pem"
elif [ -f "${HOME}/Downloads/ai_video.pem" ]; then
  SSH_KEY="${HOME}/Downloads/ai_video.pem"
else
  echo "ERROR: ai_video.pem not found in repo root or ~/Downloads/" >&2
  exit 2
fi
REMOTE_HOST_DIR="/opt/ai-video/output_uploaded"
DOCKER_VOLUME="ai-video_backend_output"  # docker compose 的 volume 命名规则:<project>_<volume>
CONTAINER="ai_video_backend"

DRY_RUN=""
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN="--dry-run"
fi

echo "========================================"
echo "  Sync output/ → Lighthouse backend_output volume"
echo "  Server:    $SERVER_IP"
echo "  Remote:    $REMOTE_HOST_DIR"
echo "  Container: $CONTAINER"
[ -n "$DRY_RUN" ] && echo "  Mode:      DRY RUN"
echo "========================================"
echo ""

# Phase 1: rsync to host (不动 docker volume)
# --include / --exclude:只同步媒体二进制,跳过 .json / .db / .DS_Store
echo "[1/3] rsync output/ → $SSH_USER@$SERVER_IP:$REMOTE_HOST_DIR/"
# rsync include/exclude 按顺序匹配,第一个命中胜出。
# stub 排除必须放在 *.mp4/*.png include 之前,否则 stub_*.mp4 会先命中 include。
rsync -avz $DRY_RUN \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  --exclude="*.DS_Store" \
  --exclude="*.json" \
  --exclude="*.db" \
  --exclude="*stub*" \
  --include="*/" \
  --include="*.mp4" --include="*.mov" --include="*.webm" \
  --include="*.png" --include="*.jpg" --include="*.jpeg" \
  --include="*.mp3" --include="*.wav" --include="*.m4a" \
  --include="*.gif" \
  --exclude="*" \
  output/ "$SSH_USER@$SERVER_IP:$REMOTE_HOST_DIR/"

if [ -n "$DRY_RUN" ]; then
  echo ""
  echo "Dry run done. Run without --dry-run to actually upload."
  exit 0
fi

# Phase 2: docker cp 把内容复制进 backend_output volume
# 用临时容器 mount 同一 volume,然后 docker cp 注入文件
echo ""
echo "[2/3] Copy files from host into backend_output volume"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP" \
  "sudo docker run --rm \
    -v $DOCKER_VOLUME:/dest \
    -v $REMOTE_HOST_DIR:/src:ro \
    alpine sh -c 'cp -rn /src/. /dest/ && chown -R 1000:1000 /dest'"

# Phase 3: 验证
echo ""
echo "[3/3] Verify nginx /api/media/<sample> returns 200"
SAMPLE_FILE=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP" \
  "sudo docker exec $CONTAINER ls /app/output/renders 2>/dev/null | head -1" || true)
if [ -n "$SAMPLE_FILE" ]; then
  STATUS=$(curl -sk -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: ${API_KEY:-ai_video_demo_2026}" \
    "https://$SERVER_IP/api/media/renders/$SAMPLE_FILE")
  echo "  GET /api/media/renders/$SAMPLE_FILE → $STATUS"
  if [ "$STATUS" = "200" ]; then
    echo "  ✓ verify OK"
  else
    echo "  ⚠ unexpected status, manual check needed"
  fi
else
  echo "  ⚠ no renders/ in container,backend 未重启或同步失败"
fi

echo ""
echo "========================================"
echo "  Sync complete"
echo "========================================"
