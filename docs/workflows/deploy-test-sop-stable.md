---
title: 生产部署 + 端到端测试标准作业程序 (SOP)
doc_type: workflow
module: deploy
status: stable
created: 2026-05-09
updated: 2026-05-31
owner: self
source: human+ai
---

# 生产部署 + 端到端测试 SOP

本文档记录从代码到生产环境的全流程，包含部署步骤、验证清单、已知问题与 workaround。

**适用范围**：`fix/*` 或 `feature/*` 分支合并到 `main` 后的 Lighthouse 生产部署。

---

## 1. 前置条件

| 检查项 | 命令/方法 | 预期结果 |
|---|---|---|
| 本地测试通过 | `make ci` | ruff + pyright + pytest 全绿 |
| 前端构建通过 | `cd web && npm run build` | `standalone/server.js` 存在 |
| 分支干净 | `git status` | 无未提交改动 |
| SSH 密钥可用 | `ssh -i ai_video.pem ubuntu@101.34.52.232 "echo ok"` | 输出 `ok` |
| `.env.prod` 已更新 | 检查 `deploy/lighthouse/.env.prod` | 含所有必需 env |
| **Re-export 安全检查** | `git diff main..HEAD -- 'src/**/__init__.py' 'src/**/_*.py'` | 无被删除的 `from ... import ... as ...` 行（若有：当面 review，加 `# noqa: E402,F401,I001`）|

> **关键**：文件名以 `_` 开头或路径含 `__init__.py` 的 Python 文件通常是 re-export 聚合点。ruff auto-fix 会把"本文件不用"但"其他文件通过该文件 import"的符号当 unused import 删掉，**触发 production ImportError**。必须在 deploy 前人工审这类文件的 F401 改动。见 §8 的 "2026-05-09 ruff over-fix" 事故。

---

## 2. 部署执行

### 2.1 服务器端代码同步

```bash
# 在本地项目根目录执行
SSH_KEY=/path/to/ai_video.pem DRY_RUN=1 deploy/lighthouse/build-and-deploy.sh
SSH_KEY=/path/to/ai_video.pem deploy/lighthouse/build-and-deploy.sh
```

> **关键：先跑 `DRY_RUN=1`**
> dry-run 输出里不允许出现 `deleting deploy/lighthouse/*.bak*`、`.env.prod`、证书、`web/node_modules`、`web/.next`、`output` 等生产资产。若出现，先修 exclude，不允许继续部署。

> **关键：使用 `deploy/lighthouse/build-and-deploy.sh`**
> 该脚本是 canonical 同步入口，内置 `--chmod=F644,D755`，并从 `deploy/lighthouse/rsync-excludes.txt` 读取生产 secret/cert、缓存、依赖、测试产物和回滚备份排除规则。同步后自动调用远端 `deploy.sh`。不要复制旧的手写 rsync 命令。

> **关键：`--exclude='deploy/lighthouse/server.{crt,key}'`**
> `--delete` 会清理服务器上不存在于本地的文件。SSL 证书 (`server.crt` / `server.key`) 故意 gitignore，**只存在于服务器上**——若不 exclude，rsync 会删掉证书并创建同名空目录，导致 nginx 启动失败、HTTPS 不可达。证书文件 + 任何 `*.pem` 都必须 exclude。见 §8 的 "2026-05-09 SSL cert wipe" 事故。

> **关键：使用 GNU rsync (3.x)，不是 macOS 自带 openrsync**
> macOS 默认 rsync 是 `openrsync 2.6.9` 兼容层，不支持 `--chmod`。需要 `brew install rsync` 后用 `/opt/homebrew/bin/rsync`（Apple Silicon）或 `/usr/local/bin/rsync`（Intel）。

### 2.2 手动补跑 deploy.sh

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 \
  "cd /opt/ai-video/deploy/lighthouse && bash deploy.sh"
```

`build-and-deploy.sh` 默认已经在同步后执行远端 `deploy.sh`。本节只用于排障、已完成同步后补跑部署，或在服务器上直接验证 deploy 脚本。

deploy.sh 五阶段：

| 阶段 | 内容 | 预期输出 |
|---|---|---|
| Phase 0 | requirements.txt sha256 hash 比对 | "requirements changed, will rebuild" 或 "requirements unchanged" |
| Phase 1 | 前端构建 | `standalone/server.js` 和 `static/chunks/` 存在 |
| Phase 2 | 容器重启/重建 | backend --force-recreate, frontend --force-recreate, nginx --force-recreate |
| Phase 3 | 健康检查 | `/api/health` 最多等待 120 秒到 200, persistence=postgresql |
| Phase 4 | 清理 | `docker system prune -f` |
| Phase 5 | smoke 验证 | `smoke OK — non-demo production verified`；默认跳过真实生成 |

> **注意：** nginx 配置变更（新增 location、volume mount）必须用 `--force-recreate`，`docker restart` 会复用旧容器，忽略新 volume 声明。

---

## 3. 部署后验证

### 3.1 Smoke 测试（必做）

```bash
cd /opt/ai-video/deploy/lighthouse && bash smoke.sh
```

4 个检查点：
1. `GET /api/health` → 200, `persistence.backend=postgresql`
2. `GET /api/health` 无 API key → 200（健康检查免认证）
3. `POST /api/pipeline/start` 无 key → 401
4. `POST /api/fast/generate` 默认跳过，避免部署 smoke 消耗 poyo.ai / LLM 额度

充值后需要验证真实生成链路时，显式开启 token smoke：

```bash
cd /opt/ai-video/deploy/lighthouse
RUN_TOKEN_SMOKE=1 BASE=https://video.lute-tlz-dddd.top bash smoke.sh
```

### 3.2 前端路由 200 检查

```bash
for path in / /s1 /s2 /s3 /s4 /s5 /fast /footage /brand-packages /influencers /settings /admin/login; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://101.34.52.232$path")
  echo "$path: $code"
done
```

全部应为 200。

### 3.3 Volume 权限检查（新增 — 2026-05-09 事故防御）

```bash
sudo docker exec ai_video_backend touch /app/output/fast_mode/test_write
sudo docker exec ai_video_backend rm /app/output/fast_mode/test_write
```

若 `Permission denied`，修复：

```bash
sudo chown -R 999:999 /var/lib/docker/volumes/lighthouse_backend_output/_data
sudo chmod -R u+w /var/lib/docker/volumes/lighthouse_backend_output/_data
```

**根因**：Dockerfile 创建 `appuser` (uid=999)，但 volume 目录 owner 是 uid=1000（ubuntu 用户）。容器内 `appuser` 无写入权限，导致 Fast Mode / S1-S5 的媒体生成步骤 500。

### 3.4 Admin Panel 认证链检查

```bash
# 1. 登录获取 cookie
curl -sk -c /tmp/admin.jar -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"zhoujianaaa123@gmail.com","password":"<ADMIN_PASSWORD>"}' \
  "https://101.34.52.232/api/admin/auth/login"

# 2. 访问 dashboard
curl -sk -b /tmp/admin.jar \
  "https://101.34.52.232/api/admin/dashboard/summary"
# 预期：200，返回租户数、今日运行数、错误率
```

---

## 4. 5 场景非 demo 端到端测试（按需）

### 4.1 测试范围与成本

| 场景 | 端点 | 预估耗时 | 预估费用 |
|---|---|---|---|
| Fast Mode | `/api/fast/generate` | ~3 min | ¥1-2 |
| S1 Product Direct | `/api/scenario/s1/submit` | ~19 min | ¥20-30 |
| S2 Brand Campaign | `/api/scenario/s2/submit` | — | — |
| S3 Influencer Remix | `/api/scenario/s3/submit` | ~24 min | ¥30-40 |
| S4 Live Shoot | `/api/scenario/s4/submit` | ~6 min | ¥10-15 |
| S5 Brand VLOG | `/api/scenario/s5/submit` | ~12 min | ¥15-20 |
| **合计** | | **~65 min** | **¥80-110** |

> S2 已修复（2026-05-09）：submit_scenario 自动从 `brand_package` 构造 `product_catalog`，无需前端额外传递。

### 4.2 执行方式

使用 submit + poll 模式，避免 HTTP 超时：

```bash
API_KEY=$(ssh -i ai_video.pem ubuntu@101.34.52.232 \
  "cd /opt/ai-video/deploy/lighthouse && grep -E '^API_KEY=' .env.prod | head -1 | cut -d= -f2-")

# 1. 提交（立即返回 label）
curl -sk -X POST \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"product_catalog":{...}}' \
  "https://101.34.52.232/api/scenario/s1/submit"
# → {"label":"s1_xxxx", "status":"queued"}

# 2. 轮询状态（每 30s）
curl -sk -H "X-API-Key: $API_KEY" \
  "https://101.34.52.232/api/scenario/s1/status/{label}"
# → 关注 "status" 字段：running / paused / completed / error
```

### 4.3 通过标准

- `status=completed` 且 `progress=1.0`
- `/app/output/renders/` 下存在对应 mp4 文件（S1: `s1.mp4`, S3: `s3.mp4`, S4: `s4.mp4`, S5: `vlog.mp4`）
- 文件大小 > 1MB（stub 文件通常 < 100KB）

---

## 5. 已知问题与 Workaround

### 5.1 S2 `product_catalog` 缺失（已修复 2026-05-09）

**症状**：`strategy_failed: 'product_catalog'`
**根因**：`submit_scenario` S2 分支的 config 缺少 `product_catalog`，StepRunner fallback 到 s1 pipeline 后 `_step_strategy` 需要 `config["product_catalog"]`。
**修复**：
1. `scenario.py:submit_scenario` S2 分支从 `brand_package` 自动构造 `product_catalog` + `brand_mode=True`。
2. `step_runner.py:_SCENARIO_CONFIGS` 显式添加 `s2` 条目，复用 S1 pipeline。
**验证**：非 demo E2E 通过，生成 9.9MB 真实视频。前端无需额外传递 `product_catalog`。

### 5.2 S4 `clip_0_failed: 'prompt' must be a string`（已修复 2026-05-09）

**症状**：S4 完成但视频仅 12KB，错误日志显示 prompt 参数类型错误。
**根因**：S4 `_step_video_prompts` 将 `seedance-video-prompt` 返回的 `list[dict]` 整体嵌套进 `"prompt": vp.data`，导致 `_step_seedance_clips` 传入 `list` 而非 `string` 给 `seedance-video-generate-skill`，触发 `validate_params` 失败。
**修复**：`s4_live_shoot_pipeline.py:_step_video_prompts` 改为扁平化模式（与 S1 一致），直接 `all_prompts.extend(vp.data)`，每个元素保留 `segment_prompt` 字符串字段。
**验证**：非 demo E2E 通过，生成 5.8MB 真实视频，clip_details 全部 `is_stub=False`。

### 5.3 `final_video_path` 未回写 state（已知缺口）

**症状**：pipeline 完成后 `state.result.final_video_path` 为空字符串。
**根因**：Remotion 组装后未将视频路径写入 pipeline state。
**影响**：前端和 API 无法直接引用最终视频路径；需通过文件系统搜索确认视频存在。

### 5.4 `api_keys` 表未创建（已知缺口）

**症状**：`verify_api_key` 回退到 env `API_KEY`，多租户隔离未生效。
**根因**：Alembic 迁移 `1ffe98505ace` 未在生产执行。
**修复**：容器内执行 `alembic upgrade head`（需确认 `alembic` 已安装，当前 `requirements.txt` 已包含）。

### 5.5 `scripts/` 和 `migrations/` 不在容器内

**症状**：无法执行 `scripts/create_admin.py` 或 `alembic upgrade head`。
**根因**：`Dockerfile.backend` 未 `COPY scripts/` 和 `migrations/`。
**Workaround**：通过 `docker exec` 直接进入容器执行 Python 代码，或修改 Dockerfile 增加 COPY 指令。

### 5.6 ruff over-fix 删除 re-export 导致 ImportError（已修复 2026-05-09，已写入 prevention）

**症状**：`docker logs ai_video_backend` 报 `ImportError: cannot import name 'X' from 'src.routers._state'`，backend 无法启动。
**根因**：ruff `--fix` 会把"本文件不引用"的 import 当 unused 删除（F401），但部分 import 是**给其他文件 re-export 用的**。例如 `src/routers/_state.py:182` 的 `from src.tasks.bg_registry import register_background_task as _register_background_task` —— 本文件不用，但 `src/routers/scenario.py` 通过 `from src.routers._state import _register_background_task` 引用。
**修复**：恢复被删的 import，加 `# noqa: E402,F401,I001` 让 ruff 知道这是故意的：

```python
# Background task registry moved to src.tasks.bg_registry to break circular import.
# Re-export for backward compatibility (used by src.routers.scenario).
from src.tasks.bg_registry import register_background_task as _register_background_task  # noqa: E402,F401,I001
```

**Prevention**（已加入 §1 前置条件）：deploy 前跑 `git diff main..HEAD -- 'src/**/__init__.py' 'src/**/_*.py'`，对任何被删除的 import **人工 review**。

### 5.7 rsync `--delete` 删除生产 SSL 证书（已修复 2026-05-09，已写入 prevention）

**症状**：nginx 启动失败 `cannot load certificate "/etc/nginx/ssl/server.crt": no start line`，HTTPS 全部 `connection refused`。
**根因**：SSL 证书 (`deploy/lighthouse/server.crt` / `server.key`) gitignore 不在仓库里，但**确实存在于服务器**。`rsync -avz --delete` 同步时把它们当"多余文件"删了，并且因为 nginx mount path 已经存在，rsync 还把它们重建成**同名空目录**——nginx 试图 load 一个目录当证书。
**修复（紧急）**：从服务器上 Let's Encrypt 备份恢复：

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 'set -e
sudo rmdir /opt/ai-video/deploy/lighthouse/server.crt
sudo rmdir /opt/ai-video/deploy/lighthouse/server.key
sudo cp /etc/letsencrypt/live/lute-tlz-dddd.top/fullchain.pem /opt/ai-video/deploy/lighthouse/server.crt
sudo cp /etc/letsencrypt/live/lute-tlz-dddd.top/privkey.pem /opt/ai-video/deploy/lighthouse/server.key
sudo chmod 644 /opt/ai-video/deploy/lighthouse/server.crt
sudo chmod 600 /opt/ai-video/deploy/lighthouse/server.key
sudo docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml up -d --force-recreate nginx
'
```

**Prevention**（已加入 §2.1 rsync 命令）：rsync 必须加 `--exclude='deploy/lighthouse/server.crt' --exclude='deploy/lighthouse/server.key' --exclude='deploy/lighthouse/*.pem'`。

---

## 6. 回滚方案

### 6.1 5 分钟回滚

```bash
# 回滚代码（如本地有上一版本备份）
rsync -avz --delete ... ubuntu@101.34.52.232:/opt/ai-video/

# 重启服务
ssh ubuntu@101.34.52.232 "cd /opt/ai-video/deploy/lighthouse && docker compose restart backend && docker compose up -d --force-recreate frontend nginx"

# 验证 smoke
bash smoke.sh
```

### 6.2 仅回滚 nginx（配置错误）

```bash
# 恢复上一版 nginx.conf
git checkout HEAD~1 -- deploy/lighthouse/nginx.conf
rsync -avz deploy/lighthouse/nginx.conf ubuntu@101.34.52.232:/opt/ai-video/deploy/lighthouse/

# 强制重建 nginx 容器
ssh ubuntu@101.34.52.232 \
  "cd /opt/ai-video/deploy/lighthouse && docker compose up -d --force-recreate nginx"
```

### 6.3 紧急停止所有场景

```bash
# 停止 backend 容器（中断所有正在运行的 pipeline）
ssh ubuntu@101.34.52.232 "docker stop ai_video_backend"

# 如需彻底停止，同时停止 POYO 相关网络请求（已在容器内，停止容器即可）
```

---

## 7. 部署检查清单（Checklist）

- [ ] 本地 `make ci` 通过
- [ ] `web/.next/standalone/server.js` 存在
- [ ] **Re-export safety**: `git diff main..HEAD -- 'src/**/__init__.py' 'src/**/_*.py'` 无被删除的 `from ... import` 行（若有：人工 review，加 `# noqa`）
- [ ] **rsync 命令**：使用 GNU rsync 3.x（不是 macOS openrsync 2.6.9）
- [ ] **rsync 命令**：包含 `--chmod=F644,D755`
- [ ] **rsync 命令**：包含 `--exclude='deploy/lighthouse/server.crt' --exclude='deploy/lighthouse/server.key' --exclude='deploy/lighthouse/*.pem'`
- [ ] deploy.sh Phase 0-3 全绿
- [ ] smoke.sh 4/4 PASS（默认不执行真实生成）
- [ ] 如需真实生成验证：充值后显式设置 `RUN_TOKEN_SMOKE=1`
- [ ] 前端 12 个路由 200
- [ ] volume 可写测试通过
- [ ] Admin Panel 登录 → dashboard 链通过
- [ ] 如需：5 场景非 demo E2E 通过
- [ ] 部署后观察 30 分钟 error_collector 无新增 critical 错误

---

## 8. 历史部署事故

### 2026-05-31：部署 smoke 默认触发真实生成

- **症状**：部署后 `smoke.sh` 自动调用 `POST /api/fast/generate`，在未准备好 poyo.ai 充值测试时仍触发一次真实生成。
- **根因**：`deploy.sh` 已改为跳过 Fast Mode token smoke，但 Phase 5 调用的 `smoke.sh` 仍保留默认真实生成检查。
- **修复**：`deploy.sh` 和 `smoke.sh` 均改为仅在 `RUN_TOKEN_SMOKE=1` 时调用 `/api/fast/generate`。
- **影响**：发生一次非预期真实生成请求；第二次部署验证已确认默认跳过。
- **预防**：所有部署 smoke 的 token-consuming 检查必须使用显式 opt-in 环境变量。

### 2026-05-09：ruff over-fix 删除 re-export，backend 启动 ImportError

- **症状**：deploy.sh Phase 3 健康检查 `curl http://localhost:8001/health` 返回 000；`docker logs ai_video_backend` 报 `ImportError: cannot import name '_register_background_task' from 'src.routers._state'`
- **根因**：commit `1fd1a5d` 用 `ruff --fix` 批量清理 226 个 violations，期间把 `src/routers/_state.py` 第 184 行的 re-export 当 unused import 删了。该 import 本文件不引用，但 `src/routers/scenario.py` 通过它接入 `bg_registry`
- **修复**：hotfix commit `f02e749` 恢复 import + `# noqa: E402,F401,I001`
- **影响时间**：~5 分钟（backend 502 → 用户访问失败）
- **预防**：deploy 前 review `'src/**/__init__.py' 'src/**/_*.py'` 的 F401 改动；ruff `--fix` 不再 fire-and-forget。已加入 §1 前置条件 + §7 checklist

### 2026-05-09：rsync `--delete` 删除生产 SSL 证书

- **症状**：nginx 启动失败 `cannot load certificate "/etc/nginx/ssl/server.crt": no start line`；HTTPS 全部 `connection refused`
- **根因**：rsync 命令带 `--delete`，但本地仓库 gitignore 不含 `deploy/lighthouse/server.crt` / `server.key`。同步时这两个文件被当"多余"删除，且由于 nginx mount path 已存在，被重建为**同名空目录**
- **修复**：从 `/etc/letsencrypt/live/lute-tlz-dddd.top/{fullchain,privkey}.pem` 复制 + `force-recreate nginx`
- **影响时间**：~3 分钟（HTTPS 全站不可达）
- **预防**：rsync 必须 `--exclude='deploy/lighthouse/server.crt' --exclude='deploy/lighthouse/server.key' --exclude='deploy/lighthouse/*.pem'`。已加入 §2.1 rsync 命令 + §7 checklist

### 2026-05-09：volume 权限导致 Fast Mode / S1-S5 500

- **症状**：部署后 Fast Mode 返回 500，`Permission denied: '/app/output/fast_mode/...'`
- **根因**：rsync 保留源文件权限，部分文件为 600；同时 volume owner (uid=1000) 与容器 user (uid=999) 不匹配
- **修复**：`chmod 644` 所有 src 文件 + `chown -R 999:999` volume 目录
- **预防**：rsync 加 `--chmod=F644,D755`，部署后执行 volume 可写测试

### 2026-05-08：admin.py 600 权限导致 backend 启动失败

- **症状**：deploy.sh Phase 3 健康检查 502
- **根因**：`admin.py` 文件权限为 600，容器非 root 用户无法读取
- **修复**：`find /opt/ai-video/src -type f -exec chmod 644 {} \;`
- **预防**：rsync `--chmod=F644,D755`

### 2026-05-07：nginx `limit_req` 顶层声明误伤前端

- **症状**：Next.js 冷启动 30+ 并发请求秒爆 burst=20，首页 429
- **根因**：`server` 块顶层 `limit_req` 被所有 location 继承，包括前端 `/` 和 `/_next/`
- **修复**：删除顶层声明，改为 7 个 API location 内部显式 `limit_req`
- **预防**：新增 location 时必须明确判断是否需限流，不依赖顶层兜底

---

*本文档随每次部署迭代更新。最后验证日期：2026-05-31。*
