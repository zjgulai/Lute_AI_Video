---
title: 腾讯云部署错误教训与根因分析
doc_type: knowledge
module: deploy
module: deploy
topic: lighthouse-deployment-mistakes
status: stable
created: 2026-04-30
updated: 2026-04-30
owner: self
source: human+ai
---

# 腾讯云部署错误教训与根因分析

本文档记录 2026-04-29 至 2026-04-30 期间在腾讯云 Lighthouse 服务器部署 AI Video 项目时发生的全部错误、根因和修复方案。所有教训必须作为 checklist 在后续部署中逐项确认。

---

## 错误总览

| # | 错误现象 | 根因 | 修复时间 | 严重程度 |
|---|---------|------|---------|---------|
| 1 | SSH Permission Denied | macOS xattr 隔离 + 未指定密钥路径 | Day 1 | 阻塞 |
| 2 | NEXT_PUBLIC_IS_DEMO 在容器中为空 | Docker 多阶段构建中 ARG/ENV 未跨 stage 传递 | Day 1 | 阻塞 |
| 3 | docker-compose.prod.yml 与本地不同步 | rsync 未包含 prod compose 文件 | Day 1 | 阻塞 |
| 4 | wget healthcheck 失败 (Connection refused) | Next.js standalone 绑定容器 IP 而非 0.0.0.0 | Day 2 | 严重 |
| 5 | wget localhost 解析到 IPv6 ::1 | Alpine Linux wget 优先 IPv6 | Day 2 | 中等 |
| 6 | 容器状态 unhealthy | 上述 4+5 叠加导致 | Day 2 | 严重 |

---

## 错误 1: SSH Permission Denied

### 现象
```
ssh ubuntu@101.34.52.232
Permissions denied (publickey)
```

### 根因
1. **macOS xattr 隔离**: 从浏览器下载的 `.pem` 文件被 macOS 附加了 `com.apple.quarantine` 属性，SSH 客户端拒绝使用该密钥
2. **未指定密钥路径**: 密钥文件不在 `~/.ssh/` 默认搜索路径中，SSH 命令未使用 `-i` 参数指定

### 修复
```bash
# 清除隔离属性
xattr -c ~/Downloads/ai_video.pem

# 显式指定密钥路径
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
```

### 预防 (Checklist)
- [ ] 下载密钥后立即执行 `xattr -c`
- [ ] 始终使用 `-i /path/to/key.pem` 显式指定密钥
- [ ] 或将密钥移入 `~/.ssh/` 并设置权限 `chmod 600`

---

## 错误 2: NEXT_PUBLIC_IS_DEMO 在容器中为空

### 现象
进入前端容器检查环境变量：
```bash
docker exec ai_video_frontend env | grep DEMO
# 输出为空，NEXT_PUBLIC_IS_DEMO 未设置
```

前端页面未进入 demo 模式，调用真实 API 失败。

### 根因链
**表面**: 容器内没有 `NEXT_PUBLIC_IS_DEMO` 环境变量  
**第一层**: Dockerfile 的 runner stage 没有继承 builder stage 的 ENV  
**第二层**: Docker 多阶段构建中，ARG 和 ENV 不会自动跨 stage 传递  
**第三层**: Next.js 的 `NEXT_PUBLIC_*` 变量在 standalone 模式下**仅构建时生效**，构建完成后运行时无法注入

### 修复
在 Dockerfile 的 **runner stage** 中重新声明 ARG 和 ENV：

```dockerfile
# ── Stage 1: Build ──
FROM node:22-alpine AS builder
ARG NEXT_PUBLIC_IS_DEMO=false
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}
# ... build happens here, NEXT_PUBLIC_IS_DEMO is inlined into JS bundles

# ── Stage 2: Runtime ──
FROM node:22-alpine AS runner
# MUST re-declare here — ARG/ENV do NOT cross stage boundaries
ARG NEXT_PUBLIC_IS_DEMO
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}
```

### 关键认知
- `NEXT_PUBLIC_*` 是 Next.js **构建时变量**，不是运行时变量
- 在 standalone 模式下，这些值被硬编码进 `.next/standalone/` 中的 JS 文件
- 即使 runner stage 的 ENV 设置正确，如果 builder stage 没收到正确的 ARG，构建产物仍然是错误的

### 预防 (Checklist)
- [ ] 确认 Dockerfile builder stage 有 `ARG NEXT_PUBLIC_IS_DEMO`
- [ ] 确认 Dockerfile runner stage **重新声明**了 `ARG NEXT_PUBLIC_IS_DEMO`
- [ ] 确认 docker-compose.prod.yml 的 `build.args` 中设置了 `NEXT_PUBLIC_IS_DEMO: "true"`
- [ ] 构建完成后，进入容器执行 `env | grep DEMO` 验证
- [ ] 构建完成后，检查 `strings .next/standalone/server.js | grep DEMO` 确认值被内联

---

## 错误 3: docker-compose.prod.yml 与本地不同步

### 现象
本地修改了 `deploy/lighthouse/docker-compose.prod.yml` 添加 demo build arg，但服务器上的文件仍然是旧版本。

### 根因
1. **rsync 脚本未包含该文件**: 部署脚本使用 rsync 同步代码，但 `docker-compose.prod.yml` 在 `deploy/lighthouse/` 子目录中，可能被遗漏
2. **手动修改未同步**: 通过 SSH 在服务器上直接修改，但本地也有修改，造成冲突

### 修复
在服务器上直接用 `sed` 修改已部署的文件：
```bash
sed -i 's/NEXT_PUBLIC_IS_DEMO:.*/NEXT_PUBLIC_IS_DEMO: "true"/' /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml
```

### 更优方案
统一使用 `docker-compose -f deploy/lighthouse/docker-compose.prod.yml up --build` 部署，确保文件唯一来源是本地仓库。

### 预防 (Checklist)
- [ ] 部署前确认 `git diff` 中所有修改都已提交
- [ ] 使用 `rsync -avz --delete` 确保服务器与本地完全一致
- [ ] 或者使用 CI/CD 流水线从 git 拉取，避免 rsync 遗漏

---

## 错误 4: Next.js Standalone 绑定容器 IP

### 现象
```bash
# 容器内
docker exec ai_video_frontend netstat -tlnp
# 显示: tcp  0.0.0.0:3000  172.18.0.3:3000  LISTEN

# healthcheck 失败
wget http://127.0.0.1:3000
# Connection refused
```

容器状态为 **unhealthy**。

### 根因
Next.js 16 standalone server (`server.js`) 默认绑定到容器的主机名 IP（即容器的内部 IP，如 `172.18.0.3`），而不是 `0.0.0.0`（所有接口）。

这意味着：
- 从容器外部（宿主机）无法访问 `172.18.0.3:3000`
- 容器内的 `127.0.0.1:3000` healthcheck 也无法访问
- nginx `proxy_pass http://frontend:3000` 解析的是容器 IP，可以访问，但 healthcheck 不行

### 修复
在 docker-compose.prod.yml 中设置 `HOSTNAME=0.0.0.0`：

```yaml
frontend:
  environment:
    - NODE_ENV=production
    - HOSTNAME=0.0.0.0   # 强制 Next.js standalone 绑定所有接口
```

### 预防 (Checklist)
- [ ] 所有 Docker 部署的 Node.js 服务必须设置 `HOSTNAME=0.0.0.0`
- [ ] 健康检查使用 `127.0.0.1`（见错误 5）
- [ ] 部署后执行 `docker ps` 确认所有容器状态为 **healthy**

---

## 错误 5: Alpine wget 优先解析 IPv6

### 现象
```bash
# Dockerfile 中的 HEALTHCHECK
HEALTHCHECK CMD wget --spider http://localhost:3000 || exit 1
# 失败，报错: wget: can't connect to remote host: Network is unreachable
```

但 `wget http://127.0.0.1:3000` 成功。

### 根因
Alpine Linux 的 `wget` (busybox 版本) 解析 `localhost` 时优先尝试 IPv6 `::1`，如果容器没有 IPv6 支持就会失败。而 Next.js standalone 只监听 IPv4 `0.0.0.0:3000`。

### 修复
将所有 healthcheck 中的 `localhost` 替换为 `127.0.0.1`：

```dockerfile
# Dockerfile
HEALTHCHECK CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1
```

```yaml
# docker-compose.prod.yml
healthcheck:
  test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1"]
```

### 预防 (Checklist)
- [ ] 所有 Dockerfile HEALTHCHECK 使用 `127.0.0.1`，绝不用 `localhost`
- [ ] 所有 docker-compose healthcheck 使用 `127.0.0.1`
- [ ] 所有 curl/wget 测试命令使用 `127.0.0.1`

---

## 综合诊断流程

当容器状态异常时，按以下顺序排查：

```bash
# 1. 查看容器状态
docker ps

# 2. 查看容器日志
docker logs ai_video_frontend --tail 50

# 3. 检查环境变量
docker exec ai_video_frontend env | sort

# 4. 检查端口绑定
docker exec ai_video_frontend netstat -tlnp

# 5. 从容器内测试连通性
docker exec ai_video_frontend wget -O- http://127.0.0.1:3000

# 6. 从宿主机测试连通性
curl -k https://101.34.52.232/
curl http://localhost:8001/health
```

---

## 教训总结

1. **Docker 多阶段构建中 ARG/ENV 不跨 stage 传递** — 每个 stage 必须显式重新声明
2. **NEXT_PUBLIC_* 是构建时变量** — 必须在 `docker build` 时通过 `--build-arg` 传入，运行时无法修改
3. **Next.js standalone 默认绑定容器 IP** — 必须设置 `HOSTNAME=0.0.0.0`
4. **Alpine wget localhost 优先 IPv6** — 容器内健康检查必须使用 `127.0.0.1`
5. **部署前必须验证容器健康状态** — `docker ps` 中状态必须是 `(healthy)`，不是 `(health: starting)` 或 `(unhealthy)`
6. **SSH 密钥必须清除 xattr 并显式指定路径** — 不要依赖默认搜索路径
