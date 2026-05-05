#!/usr/bin/env bash
# 把 Lighthouse 服务器 backend_output Docker volume 拉回本地 output/。
#
# 需求:闭环测试在生产跑出来的 mp4 / mp3 / png / wav / keyframe 都是付费产物,
# 必须并入本地 output/ 然后由 make portfolio 重建索引,作品集才完整。
#
# 架构上 backend 容器 mount 的是 named volume(lighthouse_backend_output:/app/output),
# host 路径不直接可读,必须先借临时 alpine 容器把 volume 内容落到 host 路径,
# 再 rsync 回本地。
#
# Usage:
#   ./scripts/sync_lighthouse_to_output.sh --dry-run   # 看要拉哪些文件,不实际跑
#   ./scripts/sync_lighthouse_to_output.sh             # 真实拉取
#   ./scripts/sync_lighthouse_to_output.sh --keep-pulled # 保留服务器侧 output_pulled/
#
# 跑完后默认会自动 make portfolio 重建 assets/portfolio/index.json。
#
# 依赖:
#   - 仓库根 ai_video.pem(.gitignore 已排除),fallback 到 ~/Downloads/

set -euo pipefail

SERVER_IP="101.34.52.232"
SSH_USER="ubuntu"
if [ -f "$(dirname "$0")/../ai_video.pem" ]; then
  SSH_KEY="$(cd "$(dirname "$0")/.." && pwd)/ai_video.pem"
elif [ -f "${HOME}/Downloads/ai_video.pem" ]; then
  SSH_KEY="${HOME}/Downloads/ai_video.pem"
else
  echo "ERROR: ai_video.pem not found in repo root or ~/Downloads/" >&2
  exit 2
fi

# 实际生产 docker compose project 名 = lighthouse (deploy/lighthouse/),
# 所以 volume 命名 lighthouse_backend_output。
# 注:历史 ai-video_backend_output volume 在服务器上还存在但已脱链,不要碰。
DOCKER_VOLUME="lighthouse_backend_output"
REMOTE_HOST_DIR="/opt/ai-video/output_pulled"
LOCAL_OUTPUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/output"

DRY_RUN=""
KEEP_PULLED=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run" ;;
    --keep-pulled) KEEP_PULLED="1" ;;
  esac
done

echo "========================================"
echo "  Pull Lighthouse backend_output → 本地 output/"
echo "  Server:        $SERVER_IP"
echo "  Volume:        $DOCKER_VOLUME"
echo "  Remote stage:  $REMOTE_HOST_DIR"
echo "  Local:         $LOCAL_OUTPUT_DIR"
[ -n "$DRY_RUN" ] && echo "  Mode:          DRY RUN"
echo "========================================"
echo ""

# Phase 1: docker run alpine cp 把 volume 内容落到 host 暂存路径
echo "[1/3] 服务器侧:把 $DOCKER_VOLUME 落到 $REMOTE_HOST_DIR/"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP" \
  "sudo mkdir -p $REMOTE_HOST_DIR && \
   sudo docker run --rm \
     -v $DOCKER_VOLUME:/src:ro \
     -v $REMOTE_HOST_DIR:/dest \
     alpine sh -c 'cp -ru /src/. /dest/ 2>&1 | tail -5; chown -R 1000:1000 /dest' && \
   echo \"    done. files in stage:\" && \
   sudo find $REMOTE_HOST_DIR -type f \( -name '*.mp4' -o -name '*.mp3' -o -name '*.wav' -o -name '*.png' -o -name '*.jpg' -o -name '*.mov' -o -name '*.webm' \) | wc -l"

# Phase 2: rsync 拉回本地。排除 stub_*(本地 fallback 占位,不算资产)+ pipeline_states *.json + .db
echo ""
echo "[2/3] rsync $REMOTE_HOST_DIR/ → $LOCAL_OUTPUT_DIR/"
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
  "$SSH_USER@$SERVER_IP:$REMOTE_HOST_DIR/" "$LOCAL_OUTPUT_DIR/"

if [ -n "$DRY_RUN" ]; then
  echo ""
  echo "Dry run done. Run without --dry-run to actually pull."
  exit 0
fi

# Phase 3: 清理服务器侧暂存(可选)+ 重建本地索引
echo ""
if [ -z "$KEEP_PULLED" ]; then
  echo "[3/3] 清理服务器侧 $REMOTE_HOST_DIR/(--keep-pulled 可跳过)"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP" \
    "sudo rm -rf $REMOTE_HOST_DIR"
else
  echo "[3/3] 保留服务器侧 $REMOTE_HOST_DIR/"
fi

echo ""
echo "[+] 重建本地 portfolio 索引"
cd "$(dirname "$0")/.."
# venv 优先(项目惯例),fallback python3
if [ -x ".venv/bin/python" ]; then
  .venv/bin/python scripts/portfolio_index.py 2>&1 | tail -3
else
  python3 scripts/portfolio_index.py 2>&1 | tail -3
fi

echo ""
echo "========================================"
echo "  Pull complete"
echo "========================================"
