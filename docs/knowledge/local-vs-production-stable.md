---
title: 本地开发环境与腾讯云生产环境差异对照表
doc_type: knowledge
module: deploy
topic: local-vs-production-differences
status: stable
created: 2026-04-30
updated: 2026-05-18
owner: self
source: human+ai
---

# 本地开发环境与腾讯云生产环境差异对照表

本文档系统梳理本地开发环境与腾讯云 Lighthouse 生产环境的全部差异。任何在本地验证通过的功能，部署前必须对照此表确认生产环境兼容性。

---

## 差异总览表

| 维度 | 本地开发 | 腾讯云生产 | 影响 |
|------|---------|-----------|------|
| **前端运行模式** | `next dev` (dev server) | `next build` + `node server.js` (standalone) | NEXT_PUBLIC_* 仅构建时生效 |
| **前端访问协议** | HTTP (`http://localhost:3000`) | HTTPS (`https://101.34.52.232`) | 自签名证书，浏览器需接受例外 |
| **API 访问路径** | 直接 `http://localhost:8001` | Nginx 反向代理 `/api` → backend | 前端代码中必须用相对路径或 `/api` |
| **后端绑定地址** | `127.0.0.1:8001` (dev) | `0.0.0.0:8001` (Docker) | 本地无需关心，Docker 必须暴露 |
| **数据库** | PostgreSQL 本地 (`localhost:5432`) | 腾讯云 PostgreSQL (`*.tencentcdb.com:22986`) | 连接字符串完全不同 |
| **环境变量来源** | `.env` 文件 (gitignored) | `deploy/lighthouse/.env.prod` | 本地与生产的 .env 必须分开管理 |
| **媒体文件存储** | `./output/` 本地目录 | Docker Volume `backend_output` | 容器重启后数据是否持久化 |
| **静态资源** | `public/` 目录自动 serve | `public/portfolio/` 预置到镜像 | 新资源必须重新构建镜像 |
| **CORS 策略** | 宽松 (`localhost:3000`, `localhost:3001`) | 严格 (`101.34.52.232`, `localhost:3000`) | 跨域问题只在生产出现 |
| **API Key** | 自动生成随机字符串 | 固定 `ai_video_demo_2026` | 前端硬编码的 key 必须与后端一致 |
| **Demo 数据** | 可能缺失 portfolio 文件 | `/opt/ai-video/web/public/portfolio/` (14个文件) | 演示模式依赖这些文件 |
| **容器化** | 无 | Docker Compose 三容器 | 本地调试无法发现 Docker 特有问题 |
| **SSL 证书** | 无 | 自签名 (`server.crt` / `server.key`) | 外部 API 调用可能因证书问题失败 |
| **日志查看** | 终端直接输出 | `docker logs` | 调试延迟，需要 docker exec |
| **文件上传限制** | 无限制 | 100MB (`MAX_UPLOAD_SIZE`) | 大文件上传在生产可能失败 |

---

## 详细差异说明

### 1. 前端运行模式: dev vs standalone

**本地**
```bash
cd web && npm run dev
# 启动 Next.js dev server，支持 HMR，动态编译
```

**生产**
```dockerfile
# Dockerfile 多阶段构建
RUN npm run build          # 生成 .next/standalone/
CMD ["node", "server.js"]  # 运行预编译产物
```

**关键影响**
- `NEXT_PUBLIC_*` 变量在 `next build` 时被硬编码进 JS 包，运行时无法修改
- standalone 模式下没有 HMR，任何前端代码修改都必须重新构建镜像
- standalone server 默认绑定容器内部 IP，必须设置 `HOSTNAME=0.0.0.0`

### 2. API 访问路径

**本地**
```typescript
// 前端直接访问后端
const API_BASE = "http://localhost:8001";
fetch(API_BASE + "/pipeline/start");
```

**生产**
```typescript
// 通过 Nginx 反向代理
const API_BASE = "/api";  // 相对路径
// Nginx: location /api/ { proxy_pass http://backend:8001/; }
fetch(API_BASE + "/pipeline/start");
// 实际请求: https://101.34.52.232/api/pipeline/start
```

**关键影响**
- 前端代码中使用相对路径 `/api`，在本地和生产都能工作
- 绝对路径 `http://localhost:8001` 在生产会失败（CORS + 协议不匹配）

### 3. 数据库连接

**本地** (`src/config.py`)
```python
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ai_video:ai_video_dev_2026@localhost:5432/ai_video")
```

**生产** (`deploy/lighthouse/.env.prod`)
```bash
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
```

**关键影响**
- 本地数据库是空的或只有测试数据
- 生产数据库有持久化数据（线程索引、发布日志、指标）
- 生产数据库连接需要网络可达（安全组开放 22986 端口）

### 4. Demo 模式数据来源

**本地**
- `web/public/portfolio/` 可能为空或不存在
- Demo 模式可能无法显示视频/图片预览

**生产**
- `/opt/ai-video/web/public/portfolio/` 包含 14 个真实 AI 生成文件
- 5 个视频文件 (seedance_*.mp4)
- 9 个图片文件 (poyo_img_*.png)
- 所有文件在 `web/src/demo-data.ts` 中有精确引用

### 5. 环境变量管理

| 变量 | 本地 .env | 生产 .env.prod | 说明 |
|------|----------|---------------|------|
| `DEEPSEEK_API_KEY` | `sk-your-deepseek-key` | `<redacted>` | 真实 API key |
| `POYO_API_KEY` | `sk-your-poyo-key` | `<redacted>` | 真实 API key |
| `SILICONFLOW_API_KEY` | `sk-your-siliconflow-key` | `<redacted>` | 真实 API key |
| `DATABASE_URL` | `localhost:5432` | `tencentcdb.com:22986` | 完全不同 |
| `API_KEY` | 自动生成 | `<tenant-or-test-bundle-key>` | API 认证 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8001` | `https://101.34.52.232/api` | 构建时注入 |
| `NEXT_PUBLIC_IS_DEMO` | `false` | `"true"` | 构建时注入 |
| `VIDEO_OUTPUT_DIR` | `./output` | `/app/output` | Docker 内路径 |
| `LOG_LEVEL` | `INFO` | `INFO` | 相同 |

---

## 兼容性检查清单

任何新功能在本地验证后，部署前必须确认：

### 前端代码检查
- [ ] 没有硬编码 `http://localhost` 或 `https://localhost`
- [ ] API 调用使用 `getApiBase()` 或相对路径 `/api`
- [ ] 媒体文件路径使用 `getMediaUrl()` 函数
- [ ] `NEXT_PUBLIC_*` 变量在构建时已正确设置
- [ ] Demo 数据引用的文件在 `public/portfolio/` 中存在

### 后端代码检查
- [ ] 数据库连接字符串从环境变量读取，没有硬编码
- [ ] 文件路径使用 `OUTPUT_DIR` 环境变量，不是相对路径
- [ ] API Key 验证兼容固定 key 和自动生成 key
- [ ] CORS origins 包含生产域名

### 配置检查
- [ ] `deploy/lighthouse/.env.prod` 包含所有需要的 API keys
- [ ] `deploy/lighthouse/docker-compose.prod.yml` 的 build args 正确
- [ ] `deploy/lighthouse/nginx.conf` 的 upstream 配置正确
- [ ] SSL 证书未过期

### 部署后验证
- [ ] `docker ps` 所有容器状态为 `(healthy)`
- [ ] `https://101.34.52.232/` 首页返回 200
- [ ] `https://101.34.52.232/api/health` 返回 200 + JSON
- [ ] Demo 模式下视频预览正常播放
- [ ] Expert Studio 流程的 4 个 Gate 都能正常展示
