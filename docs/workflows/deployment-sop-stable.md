---
title: AI Video 腾讯云 Lighthouse 发布流程 SOP
doc_type: workflow
module: deploy
topic: lighthouse-deployment-sop
status: stable
created: 2026-04-30
updated: 2026-04-30
owner: self
source: human+ai
---

# AI Video 腾讯云 Lighthouse 发布流程 SOP

本文档规定从本地代码到腾讯云生产环境的完整发布流程。任何部署操作必须按此 checklist 执行，禁止跳过步骤。

---

## 前置条件

- [ ] 本地 `git status` 确认所有修改已提交（或有明确理由未提交）
- [ ] `git log --oneline -5` 确认提交历史清晰
- [ ] 本地 `npm run build`（前端）和 `python -c "import src.api"`（后端）验证通过
- [ ] SSH 密钥文件已清除 xattr：`xattr -c ~/Downloads/ai_video.pem`

---

## Phase 1: 代码同步到服务器

### 1.1 确认本地代码状态

```bash
git status
git log --oneline -5
```

### 1.2 同步代码到服务器

**方式 A: rsync（当前使用）**
```bash
# 从项目根目录执行
rsync -avz --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  ./ ubuntu@101.34.52.232:/opt/ai-video/
```

**方式 B: git pull（推荐，更可靠）**
```bash
# 在服务器上执行
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
git pull origin main
```

### 1.3 确认同步成功

```bash
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
ls -la /opt/ai-video/
# 确认关键文件存在：
# - deploy/lighthouse/docker-compose.prod.yml
# - deploy/lighthouse/.env.prod
# - deploy/lighthouse/nginx.conf
# - Dockerfile.backend
# - web/Dockerfile
```

---

## Phase 2: 构建与启动

### 2.1 停止现有容器

```bash
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video/deploy/lighthouse
docker-compose -f docker-compose.prod.yml down
```

### 2.2 清理旧镜像（可选，用于完全重建）

```bash
docker-compose -f docker-compose.prod.yml down --rmi all --volumes
docker system prune -f
```

### 2.3 构建并启动

```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

### 2.4 观察启动过程

```bash
# 实时查看日志（约 2-3 分钟构建时间）
docker-compose -f docker-compose.prod.yml logs -f

# 观察关键日志：
# - backend: "Uvicorn running on http://0.0.0.0:8001"
# - frontend: "Ready on http://0.0.0.0:3000"
# - nginx: 无错误
```

---

## Phase 3: 健康检查

### 3.1 容器状态检查

```bash
docker ps

# 期望输出：
# CONTAINER ID  IMAGE           STATUS                   PORTS
# xxx           ai_video_frontend  Up 30s (healthy)      3000/tcp
# xxx           ai_video_backend   Up 30s (healthy)      8001/tcp
# xxx           nginx:alpine       Up 30s                0.0.0.0:80->80, 0.0.0.0:443->443
```

### 3.2 前端环境变量验证

```bash
# 确认 NEXT_PUBLIC_IS_DEMO 已正确设置
docker exec ai_video_frontend env | grep DEMO
# 期望输出: NEXT_PUBLIC_IS_DEMO=true

# 确认 NEXT_PUBLIC_API_BASE_URL 已正确设置
docker exec ai_video_frontend env | grep API_BASE
# 期望输出: NEXT_PUBLIC_API_BASE_URL=https://101.34.52.232/api
```

### 3.3 网络连通性测试

```bash
# 从容器内测试前端服务
docker exec ai_video_frontend wget -qO- http://127.0.0.1:3000 | head -5

# 从容器内测试后端服务
docker exec ai_video_backend python -c "
import urllib.request
r = urllib.request.urlopen('http://localhost:8001/health')
print(r.read().decode())
"
```

### 3.4 外部访问测试

```bash
# 在本地 Mac 上执行

# HTTP → HTTPS 重定向
curl -I http://101.34.52.232/
# 期望: HTTP/1.1 301 Moved Permanently

# HTTPS 首页
curl -Ik https://101.34.52.232/
# 期望: HTTP/2 200

# API 健康检查
curl -k https://101.34.52.232/api/health
# 期望: {"status":"ok","version":"0.2.0",...}

# 静态资源（Demo 模式视频文件）
curl -Ik https://101.34.52.232/portfolio/seedance_W85PPT60_bff4.mp4
# 期望: HTTP/2 200
```

---

## Phase 4: Demo 模式验证

### 4.1 浏览器验证

1. 打开 `https://101.34.52.232/`
2. 接受自签名 SSL 证书例外
3. 确认页面加载无报错（DevTools Console 无红色错误）
4. 确认 `isDemoMode()` 返回 `true`（可在 Console 执行验证）

### 4.2 Smart Create 模式验证

1. 选择 **Smart Create** 模式
2. 选择 **Product Direct** scenario
3. 点击 **Start Pipeline**
4. 期望行为：立即显示预置的 Demo 结果（不调用后端 API）
5. 确认视频预览可播放
6. 确认所有 12 个步骤显示为完成状态

### 4.3 Expert Studio 模式验证

1. 选择 **Expert Studio** 模式
2. 输入产品信息，点击 **Start**
3. 期望行为：显示 Step-by-Step 流程，4 个 Gate 节点可点击
4. 依次点击每个 Gate，确认 3 个候选方案正常显示
5. 选择一个候选，点击 **Approve**
6. 确认流程继续到下一个 Gate

### 4.4 关键 Demo 数据验证

```bash
# 确认 portfolio 文件全部存在
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232 \
  "ls -la /opt/ai-video/web/public/portfolio/"

# 期望看到 14 个文件（5 视频 + 9 图片）
```

---

## Phase 5: 回滚预案

### 如果部署失败

```bash
# 查看失败容器日志
docker logs ai_video_frontend --tail 100
docker logs ai_video_backend --tail 100
docker logs ai_video_nginx --tail 50

# 快速回滚到上一版本
cd /opt/ai-video
git log --oneline -5
git checkout <previous-commit-hash>
docker-compose -f deploy/lighthouse/docker-compose.prod.yml up --build -d

# 如果完全无法恢复，重建容器
docker-compose -f deploy/lighthouse/docker-compose.prod.yml down --rmi all --volumes
docker system prune -a -f
docker-compose -f deploy/lighthouse/docker-compose.prod.yml up --build -d
```

---

## 发布频率建议

| 变更类型 | 发布方式 | 验证范围 |
|---------|---------|---------|
| 前端 UI 调整 | 重新构建 frontend 镜像 | Phase 3 + 4.1 |
| 后端 API 变更 | 重新构建 backend 镜像 | Phase 3 + 4.2 |
| Demo 数据更新 | 同步 public/portfolio/ + 重建 | Phase 4 全部 |
| 环境变量变更 | 修改 .env.prod + 重建 | Phase 3.2 + 4 |
| Nginx 配置变更 | 修改 nginx.conf + 重建 nginx | Phase 3.4 |
| 全量重构 | 全部重建 | Phase 1-4 全部 |

---

## 关键文件清单

| 文件 | 用途 | 修改频率 |
|------|------|---------|
| `deploy/lighthouse/docker-compose.prod.yml` | 容器编排 | 低 |
| `deploy/lighthouse/.env.prod` | 生产环境变量 | 中 |
| `deploy/lighthouse/nginx.conf` | 反向代理配置 | 低 |
| `Dockerfile.backend` | 后端镜像构建 | 低 |
| `web/Dockerfile` | 前端镜像构建 | 中 |
| `web/next.config.ts` | Next.js 构建设置 | 低 |
| `web/src/demo-data.ts` | Demo 数据定义 | 中 |
| `web/public/portfolio/` | Demo 媒体文件 | 中 |
