#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# AI Video - Lighthouse 一键部署脚本
# 在腾讯云轻量服务器上执行
# ═══════════════════════════════════════════════════════════════

PROJECT_DIR="/opt/ai-video"
COMPOSE_FILE="$PROJECT_DIR/deploy/lighthouse/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/deploy/lighthouse/.env.prod"

echo "========================================"
echo "  AI Video 部署脚本"
echo "========================================"

# ── 1. 检查 Docker ──
if ! command -v docker &> /dev/null; then
    echo "[1/6] 安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker "$USER"
else
    echo "[1/6] Docker 已安装 ✓"
fi

# ── 2. 检查 Docker Compose ──
if ! docker compose version &> /dev/null; then
    echo "[2/6] 安装 Docker Compose plugin..."
    apt-get update && apt-get install -y docker-compose-plugin
else
    echo "[2/6] Docker Compose 已安装 ✓"
fi

# ── 3. 创建项目目录 ──
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# ── 4. 拉取代码（如果通过git）或解压代码包 ──
if [ -d "$PROJECT_DIR/.git" ]; then
    echo "[3/6] 拉取最新代码..."
    git pull origin main
else
    echo "[3/6] 代码已放置 ✓（跳过git拉取）"
fi

# ── 5. 构建并启动 ──
echo "[4/6] 构建 Docker 镜像..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

echo "[5/6] 启动服务..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# ── 6. 验证 ──
echo "[6/6] 等待服务启动..."
sleep 5

HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/health || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
    echo ""
    echo "========================================"
    echo "  部署成功！"
    echo "========================================"
    echo ""
    echo "访问地址："
    echo "  前端: http://101.34.52.232"
    echo "  API:  http://101.34.52.232/api"
    echo "  健康检查: http://101.34.52.232/api/health"
    echo ""
    echo "查看日志："
    echo "  docker compose -f $COMPOSE_FILE logs -f"
    echo ""
else
    echo ""
    echo "⚠️  健康检查失败 (HTTP $HEALTH_STATUS)"
    echo "查看日志排查问题："
    echo "  docker compose -f $COMPOSE_FILE logs"
    exit 1
fi
