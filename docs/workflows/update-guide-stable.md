---
title: AI Video 项目后续更新与功能增加操作指南
doc_type: workflow
module: project
topic: update-and-feature-addition-guide
status: stable
created: 2026-04-30
updated: 2026-04-30
owner: self
source: human+ai
---

# AI Video 项目后续更新与功能增加操作指南

本文档规定在现有项目基础上进行功能更新、Bug 修复、配置调整时的标准操作流程。目标是在保证生产环境稳定的前提下，高效交付变更。

---

## 核心原则

1. **本地先行**: 所有变更先在本地开发环境验证，确认无误后再部署到生产
2. **变更分类**: 根据变更影响范围选择不同的发布策略
3. **快速回滚**: 每次发布必须能在 5 分钟内回滚到上一版本
4. **验证清单**: 发布前必须逐项通过健康检查 checklist

---

## 变更类型分类与对应策略

### Type A: 纯前端 UI 变更（不涉及 API 接口）

**示例**: 调整按钮样式、修改文案、优化布局、新增页面组件

**影响范围**: 仅 frontend 容器

**操作流程**:
```bash
# 1. 本地修改代码
# 2. 本地验证
npm run build

# 3. 提交代码
git add .
git commit -m "调整XX页面布局"

# 4. 同步到服务器并重建前端
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
git pull origin main
cd deploy/lighthouse
docker-compose -f docker-compose.prod.yml up --build -d frontend

# 5. 验证
docker ps  # 确认 frontend healthy
curl -Ik https://101.34.52.232/  # 确认首页 200
```

**注意事项**:
- 如果变更涉及 `NEXT_PUBLIC_*` 变量 → 升级为 Type B
- 如果变更涉及 `demo-data.ts` → 确认 portfolio 文件存在 → 升级为 Type C

---

### Type B: 前端配置或构建相关变更

**示例**: 修改 `next.config.ts`、调整 `NEXT_PUBLIC_API_BASE_URL`、切换 Demo 模式开关

**影响范围**: frontend 容器，需要完整重建

**操作流程**:
```bash
# 1. 修改相关文件
#    - web/next.config.ts
#    - deploy/lighthouse/docker-compose.prod.yml (build args)
#    - deploy/lighthouse/.env.prod (如果需要)

# 2. 本地验证构建
cd web
npm run build
# 确认 .next/standalone/ 目录生成

# 3. 提交代码
git add deploy/lighthouse/docker-compose.prod.yml web/
git commit -m "调整前端构建配置: XXX"

# 4. 同步并全量重建（不能只重建 frontend，因为 builder stage 变了）
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
git pull origin main
cd deploy/lighthouse
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up --build -d

# 5. 完整健康检查（参照 deployment-sop-stable.md Phase 3-4）
```

**关键检查点**:
- [ ] `docker exec ai_video_frontend env | grep NEXT_PUBLIC` 确认值正确
- [ ] 浏览器 Console 无红色错误
- [ ] Demo 模式行为符合预期

---

### Type C: Demo 数据或静态资源变更

**示例**: 添加新的 Demo 视频、修改 Demo 文案、更新 portfolio 文件

**影响范围**: frontend 容器 + `web/public/portfolio/`

**操作流程**:
```bash
# 1. 准备新资源
#    将新的视频/图片文件放入 web/public/portfolio/
#    注意：文件名不要重复，使用语义化命名

# 2. 更新 demo-data.ts（如果需要引用新资源）
#    添加新的 REAL_VIDEOS / REAL_IMAGES 条目
#    更新 DEMO_RESULT_* 中的引用
#    更新 DEMO_ASSETS 数组

# 3. 本地验证
#    启动前端 dev server，确认新资源可正常显示
#    npm run dev

# 4. 提交代码
#    注意：大文件（>10MB）不要提交到 git
#    使用 scp 直接传到服务器的 portfolio 目录
git add web/src/demo-data.ts
git commit -m "更新 Demo 数据: 添加XXX场景"

# 5. 同步代码 + 传输资源文件
#    方式 1: 如果资源已提交到 git
git push origin main
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232 "cd /opt/ai-video && git pull"

#    方式 2: 如果资源未提交（大文件），直接 scp
scp -i ~/Downloads/ai_video.pem \
  ./web/public/portfolio/new_video.mp4 \
  ubuntu@101.34.52.232:/opt/ai-video/web/public/portfolio/

# 6. 重建前端镜像（因为 public/ 目录被 COPY 进镜像）
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video/deploy/lighthouse
docker-compose -f docker-compose.prod.yml up --build -d frontend

# 7. 验证新资源可访问
curl -Ik https://101.34.52.232/portfolio/new_video.mp4
```

**关于大文件的管理建议**:
- `web/public/portfolio/` 中的文件**不应提交到 git**（已存在于 .gitignore 中）
- 使用 `rsync` 或 `scp` 直接同步到服务器
- 考虑使用对象存储（腾讯云 COS）替代本地文件，避免镜像膨胀

---

### Type D: 后端 API 变更

**示例**: 新增接口、修改现有接口响应格式、调整 pipeline 逻辑

**影响范围**: backend 容器

**操作流程**:
```bash
# 1. 本地修改 src/ 下的 Python 代码
# 2. 本地验证
python -c "from src.api import app; print('OK')"

# 3. 如果修改了数据库模型，需要迁移（当前项目使用 asyncpg 直连，无 ORM 迁移）
#    确认数据库 schema 兼容

# 4. 提交代码
git add src/
git commit -m "后端: 新增XXX接口 / 调整XXX逻辑"

# 5. 同步并重建后端
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
git pull origin main
cd deploy/lighthouse
docker-compose -f docker-compose.prod.yml up --build -d backend

# 6. 验证后端健康
docker ps  # 确认 backend healthy
curl -k https://101.34.52.232/api/health
# 测试修改的接口
curl -k -H "X-API-Key: ai_video_demo_2026" \
  https://101.34.52.232/api/xxx
```

**注意事项**:
- 后端变更**不应**破坏前端兼容性（接口契约稳定）
- 如果修改了数据库 schema，需要手动在腾讯云 PostgreSQL 上执行 ALTER 语句
- 新增依赖必须在 `requirements.txt` 中声明

---

### Type E: 环境变量或配置变更

**示例**: 更换 API Key、调整超时时间、修改 CORS 配置

**影响范围**: 取决于变量用途

**操作流程**:
```bash
# 1. 修改 deploy/lighthouse/.env.prod
#    注意：该文件不在 git 中（检查 .gitignore）
#    如果希望版本控制，需要手动同步

# 2. 如果修改了 .env.prod 且希望版本控制
git add deploy/lighthouse/.env.prod
git commit -m "更新生产环境变量: XXX"

# 3. 如果变量影响前端构建（NEXT_PUBLIC_*）
#    还需要修改 docker-compose.prod.yml 的 build.args

# 4. 同步到服务器
rsync -avz deploy/lighthouse/.env.prod \
  ubuntu@101.34.52.232:/opt/ai-video/deploy/lighthouse/

# 5. 重建受影响的容器
#    后端变量 → 重建 backend
#    前端构建变量 → 重建 frontend
#    两者都有 → 全部重建
docker-compose -f docker-compose.prod.yml up --build -d
```

---

### Type F: Nginx 配置变更

**示例**: 新增路由、调整 SSL 配置、修改代理超时

**影响范围**: nginx 容器

**操作流程**:
```bash
# 1. 修改 deploy/lighthouse/nginx.conf
# 2. 本地语法检查（如果有 nginx）
nginx -t -c /path/to/nginx.conf

# 3. 提交代码
git add deploy/lighthouse/nginx.conf
git commit -m "调整 Nginx 配置: XXX"

# 4. 同步并重启 nginx
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video/deploy/lighthouse
docker-compose -f docker-compose.prod.yml up -d --build nginx
# 或仅重启（如果配置通过 volume mount）
docker-compose -f docker-compose.prod.yml restart nginx

# 5. 验证
curl -Ik https://101.34.52.232/
curl -Ik https://101.34.52.232/api/health
```

---

### Type G: 全量重构或大版本升级

**示例**: Next.js 大版本升级、Python 版本升级、架构重构

**影响范围**: 全部

**操作流程**:
1. **在分支上完成所有修改**
   ```bash
   git checkout -b feature/major-refactor
   # ... 开发 ...
   ```

2. **本地完整验证**
   - 前端 build 成功
   - 后端启动成功
   - Demo 模式工作正常
   - 端到端流程通过

3. **在服务器 staging 环境验证**（如果有）

4. **生产部署**
   ```bash
   # 备份当前状态
   ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
   cd /opt/ai-video
git log --oneline -1 > /tmp/pre-deploy-commit.txt

   # 全量重建
   cd deploy/lighthouse
   docker-compose -f docker-compose.prod.yml down --rmi all --volumes
   docker system prune -f
   docker-compose -f docker-compose.prod.yml up --build -d
   ```

5. **完整验证**（参照 deployment-sop-stable.md 全部 checklist）

6. **保留回滚能力**
   ```bash
   # 如果发现问题，立即回滚
   cd /opt/ai-video
   git checkout <previous-commit>
   cd deploy/lighthouse
   docker-compose -f docker-compose.prod.yml up --build -d
   ```

---

## 数据库 Schema 变更特别说明

当前项目使用 asyncpg 直接执行 SQL，没有 Alembic/SQLAlchemy ORM 迁移工具。

**如果修改了数据库 schema**:

1. **在本地 PostgreSQL 测试变更脚本**
   ```sql
   -- 示例：新增表
   CREATE TABLE IF NOT EXISTS new_table (...);
   ```

2. **编写变更脚本并存入 `sql/` 目录**
   ```bash
   # sql/2026-04-30-add-new-table.sql
   ```

3. **在生产数据库手动执行**
   ```bash
   ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
   psql "$DATABASE_URL" < /opt/ai-video/sql/2026-04-30-add-new-table.sql
   ```

4. **考虑引入迁移工具**（如果 schema 变更频繁）
   - 推荐: `alembic` 或 `asyncpg-migrate`

---

## 常见操作速查表

| 操作 | 命令 |
|------|------|
| 查看容器状态 | `docker ps` |
| 查看容器日志 | `docker logs <container> --tail 100` |
| 进入容器 | `docker exec -it <container> sh` |
| 重启单个容器 | `docker-compose restart <service>` |
| 重建单个容器 | `docker-compose up --build -d <service>` |
| 查看资源使用 | `docker stats` |
| 清理未使用镜像 | `docker system prune -f` |
| 备份数据库 | `pg_dump "$DATABASE_URL" > backup.sql` |
| 恢复数据库 | `psql "$DATABASE_URL" < backup.sql` |
| 查看 nginx 日志 | `docker logs ai_video_nginx --tail 50` |

---

## 禁止事项

1. **禁止在生产环境直接修改代码** — 所有修改必须在本地完成，通过 git 同步
2. **禁止跳过健康检查** — 每次部署后必须确认所有容器 healthy
3. **禁止在没有备份的情况下执行 `docker system prune -a`** — 可能删除可回滚的旧镜像
4. **禁止在演示前 1 小时内进行部署** — 演示前应保持环境稳定
5. **禁止将生产 API keys 提交到 git** — `.env.prod` 必须保持在 .gitignore 中
