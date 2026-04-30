# CloudBase 部署指南

## 架构

```
腾讯云 CloudBase 环境: lute-ai-video
├─ 云托管（容器型）: FastAPI 后端 (port 8001)
├─ 静态网站托管: Next.js 前端
└─ 腾讯云独立 PostgreSQL: 数据持久化
```

## 环境变量

后端云托管需要配置以下环境变量：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `PYTHONPATH` | `/app` | Python 模块搜索路径 |
| `DATABASE_URL` | `postgresql://ai_video:密码@10.0.0.15:5432/ai_video` | PostgreSQL 连接 |
| `API_KEY` | `ai_video_demo_2026` | 前端鉴权密钥 |
| `CORS_ORIGINS` | `https://lute-ai-video.tcloudbaseapp.com` | CORS 白名单 |
| `VIDEO_OUTPUT_DIR` | `/app/output` | 视频输出目录 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DEFAULT_LLM_PROVIDER` | `deepseek` | 默认 LLM 提供商 |
| `DEEPSEEK_API_KEY` | `sk-...` | DeepSeek API Key |
| `SILICONFLOW_API_KEY` | `sk-...` | 硅基流动 API Key |
| `POYO_API_KEY` | `sk-...` | poyo.ai API Key |

## 部署步骤

### 1. 构建 Docker 镜像

```bash
docker build -f Dockerfile.backend -t lute-ai-video-backend:latest .
```

### 2. 推送到 CloudBase 镜像仓库

```bash
# 登录 CloudBase 镜像仓库
docker login ccr.ccs.tencentyun.com --username=腾讯云账号ID

# 打标签
docker tag lute-ai-video-backend:latest \
  ccr.ccs.tencentyun.com/lute-ai-video/backend:latest

# 推送
docker push ccr.ccs.tencentyun.com/lute-ai-video/backend:latest
```

### 3. 前端构建

```bash
cd web
npm install
DEPLOY_TARGET=cloudbase npm run build
# 输出到 web/dist/
```

### 4. 部署前端到静态托管

在 CloudBase 控制台 → 静态网站托管 → 上传 `web/dist/` 目录。

## 域名

- 前端默认域名：`https://lute-ai-video.tcloudbaseapp.com`
- 后端默认域名：创建云托管服务后生成

前端 SettingsPanel 中配置后端域名。
