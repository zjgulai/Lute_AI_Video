---
title: 服务器资产清单与关键配置
doc_type: other
module: infrastructure
topic: server-inventory
status: stable
created: 2026-04-30
updated: 2026-04-30
owner: self
source: human+ai
---

# 服务器资产清单

## 1. 服务器基础信息

| 项目 | 值 |
|------|-----|
| 提供商 | 腾讯云 Lighthouse |
| 公网 IP | `101.34.52.232` |
| SSH 用户名 | `ubuntu` |
| SSH 端口 | `22` |
| 操作系统 | Ubuntu (VM-0-16-ubuntu) |
| 服务器密码 | `______________` *(请手动填写)* |
| SSH 密钥文件 | `______________` *(请手动填写本地路径)* |

### SSH 连接命令

```bash
# 密码登录
ssh ubuntu@101.34.52.232

# 密钥登录
ssh -i /path/to/your-key.pem ubuntu@101.34.52.232
```

---

## 2. 域名与 SSL

| 项目 | 值 |
|------|-----|
| 主域名 | `lute-tlz-dddd.top` |
| WWW 域名 | `www.lute-tlz-dddd.top` |
| DNS 记录类型 | A 记录 |
| SSL 证书颁发者 | Let's Encrypt |
| SSL 有效期至 | 2026-07-29 |
| 自动续期 | 已启用 (certbot) |

### SSL 证书路径（服务器上）

```
/etc/letsencrypt/live/lute-tlz-dddd.top/fullchain.pem   # 证书
/etc/letsencrypt/live/lute-tlz-dddd.top/privkey.pem     # 私钥
```

### SSL 证书路径（Docker 挂载用副本）

```
/opt/ai-video/deploy/lighthouse/server.crt
/opt/ai-video/deploy/lighthouse/server.key
```

---

## 3. 项目部署信息

| 项目 | 值 |
|------|-----|
| 项目根目录 | `/opt/ai-video/` |
| 部署配置目录 | `/opt/ai-video/deploy/lighthouse/` |
| Docker Compose 文件 | `docker-compose.prod.yml` |
| Nginx 配置 | `nginx.conf` |
| 后端输出目录 | `/app/output` (Docker volume) |

### 服务容器

| 容器名 | 服务 | 内部端口 | 说明 |
|--------|------|----------|------|
| `ai_video_backend` | FastAPI 后端 | `8001` | Python + FastAPI |
| `ai_video_frontend` | Next.js 前端 | `3000` | Node.js standalone |
| `ai_video_nginx` | Nginx 反向代理 | `80`, `443` | SSL 终止 + 路由 |

### 核心文件映射（宿主机 → 容器）

| 宿主机路径 | 容器路径 | 用途 |
|------------|----------|------|
| `/opt/ai-video/src` | `/app/src` | 后端源码 (ro) |
| `/opt/ai-video/web/.next/standalone` | `/app` | 前端构建产物 |
| `/opt/ai-video/web/public` | `/app/public` | 静态资源 |
| `/opt/ai-video/web/.next/static` | `/app/.next/static` | Next.js 静态文件 |
| `/opt/ai-video/deploy/lighthouse/nginx.conf` | `/etc/nginx/nginx.conf` | Nginx 配置 |
| `/opt/ai-video/deploy/lighthouse/server.crt` | `/etc/nginx/ssl/server.crt` | SSL 证书 |
| `/opt/ai-video/deploy/lighthouse/server.key` | `/etc/nginx/ssl/server.key` | SSL 私钥 |

---

## 4. 访问链接

| 用途 | 链接 |
|------|------|
| 首页 (HTTPS) | `https://lute-tlz-dddd.top` |
| 健康检查 | `https://lute-tlz-dddd.top/health` |
| API 文档 (Swagger) | `https://lute-tlz-dddd.top/docs` |

---

## 5. 常用运维命令

```bash
# 进入部署目录
cd /opt/ai-video/deploy/lighthouse

# 查看容器状态
sudo docker-compose -f docker-compose.prod.yml ps

# 重启所有服务
sudo docker-compose -f docker-compose.prod.yml restart

# 重启单个服务
sudo docker-compose -f docker-compose.prod.yml restart nginx
sudo docker-compose -f docker-compose.prod.yml restart backend
sudo docker-compose -f docker-compose.prod.yml restart frontend

# 查看日志
sudo docker-compose -f docker-compose.prod.yml logs -f nginx
sudo docker-compose -f docker-compose.prod.yml logs -f backend

# 查看容器资源占用
sudo docker stats

# 更新前端（宿主机构建后重启）
cd /opt/ai-video/web && npm run build
cd /opt/ai-video/deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml restart frontend
```

---

## 6. 第三方服务密钥 *(请手动填写)*

| 服务 | 环境变量名 | 状态 |
|------|-----------|------|
| DeepSeek API | `DEEPSEEK_API_KEY` | `______________` |
| Seedance / poyo.ai | `SEEDANCE_API_KEY` | `______________` |
| ElevenLabs TTS | `ELEVENLABS_API_KEY` | `______________` |
| CosyVoice TTS | `SILICONFLOW_API_KEY` | `______________` |
| 数据库 (PostgreSQL) | `DATABASE_URL` | `______________` |
| 后端 API Key | `API_KEY` | `______________` |

---

## 7. 备份与回滚

- 代码：Git 仓库管理，提交前本地测试
- 配置文件：修改前手动备份
  ```bash
  cp nginx.conf nginx.conf.bak.$(date +%Y%m%d)
  ```
- SSL 证书：certbot 自动续期，无需手动备份

---

*最后更新：2026-04-30*
