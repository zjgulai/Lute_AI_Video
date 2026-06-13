---
title: AI Video Pipeline 技术债务修复执行计划
doc_type: workflow
module: project
topic: technical-debt-remediation
status: stable
created: 2026-06-09
updated: 2026-06-09
owner: self
source: human+ai
---

# AI Video Pipeline — 技术债务修复执行计划

**日期**: 2026-06-09
**基于**: [debt-audit-report-2026-06-09.md](./debt-audit-report-2026-06-09.md)
**总工时估算**: ~78.5h（约 2 周全职）
**发现总数**: 221 项（P0: 12 / P1: 94 / P2: 97 / P3: 18）

---

## 目录

1. [Phase 1: 立即安全与仓库卫生（Day 1-2, 8.5h）](#phase-1)
2. [Phase 2: 关键基础设施修复（Day 3-5, 13h）](#phase-2)
3. [Phase 3: 债务减少（Week 2, 34h）](#phase-3)
4. [Phase 4: 长期卫生（Week 3-4, 23h）](#phase-4)
5. [依赖关系图](#依赖关系图)
6. [风险管理](#风险管理)
7. [验收标准总览](#验收标准总览)

---

## Phase 1: 立即安全与仓库卫生 <a id="phase-1"></a>

**时间**: Day 1-2 | **工时**: 8.5h | **目标**: 消除 P0 安全风险，清理仓库污染

### Task 1.1 — 从 git 追踪中移除生产密钥文件

| 属性 | 值 |
|------|-----|
| 关联项 | SEC-1, V1 |
| 严重程度 | P0 |
| 工时 | 3h |
| 前置依赖 | 无 |
| 阻塞后续 | Task 1.4（需要先确认密钥轮换后再更新 .env.example） |

**背景**: `deploy/lighthouse/.env.prod`（36 行）被 git 追踪，包含明文 `DEEPSEEK_API_KEY`、`POYO_API_KEY`、`SILICONFLOW_API_KEY`、`DATABASE_URL`（含密码）、`API_KEY`。`.gitignore` 已有规则但文件在规则添加前已提交。

**执行步骤**:

1. **确认 `.gitignore` 规则有效**
   ```bash
   grep -n "\.env\.prod" /Users/pray/project/hermes_evo/AI_vedio/.gitignore
   ```
   确认存在 `deploy/lighthouse/.env.prod` 或通配规则。

2. **从 git 索引移除（保留本地文件）**
   ```bash
   cd /Users/pray/project/hermes_evo/AI_vedio
   git rm --cached deploy/lighthouse/.env.prod
   git commit -m "chore: remove tracked production secrets from git index

   deploy/lighthouse/.env.prod contained plaintext API keys and DB
   credentials. Removed from git tracking. The file remains on the
   production server via manual deployment.

   Ref: SEC-1 from debt-audit-report-2026-06-09.md"
   ```

3. **轮换所有已泄露的密钥**
   - DeepSeek: 登录 https://platform.deepseek.com → 生成新 API key → 更新服务器 `.env.prod`
   - POYO: 登录 https://poyo.ai → 重新生成 key → 更新服务器 `.env.prod`
   - SiliconFlow: 登录 https://siliconflow.cn → 重新生成 key → 更新服务器 `.env.prod`
   - Database: 在 PostgreSQL 中 `ALTER USER ai_video WITH PASSWORD 'new_password'` → 更新服务器 `.env.prod` 中的 `DATABASE_URL`
   - `API_KEY`: 生成新的随机 key → 更新服务器 `.env.prod`

4. **部署更新后的 `.env.prod` 到生产服务器**
   ```bash
   # 不要通过 git push！直接 scp 到服务器
   scp deploy/lighthouse/.env.prod root@101.34.52.232:/opt/ai-video/deploy/lighthouse/.env.prod
   ssh root@101.34.52.232 "cd /opt/ai-video && docker compose -f docker-compose.prod.yml up -d --force-recreate"
   ```

5. **验证**: 执行 `deploy/lighthouse/smoke.sh` 确认所有服务正常启动

**验证标准**:
- [ ] `git ls-files deploy/lighthouse/.env.prod` 返回空（文件不再被追踪）
- [ ] 旧密钥已在各平台撤销
- [ ] 生产服务器 smoke test 通过
- [ ] `deploy/lighthouse/.env.prod` 仍存在于服务器本地，但不在仓库历史中

**风险**: 密钥轮换期间服务短暂不可用（约 5-10 分钟）。建议在低流量时段执行。

---

### Task 1.2 — 从 git 历史中清除 Docker 镜像压缩包

| 属性 | 值 |
|------|-----|
| 关联项 | SEC-2, M1 |
| 严重程度 | P0 |
| 工时 | 1h |
| 前置依赖 | 无 |

**背景**: `archive/lute-ai-video-backend.tar`（168MB）在 git 历史中，每次 clone 都要下载。使用 `git filter-repo` 或 `BFG Repo-Cleaner` 清除。

**执行步骤**:

1. **确认文件存在且需要清除**
   ```bash
   ls -lh /Users/pray/project/hermes_evo/AI_vedio/archive/lute-ai-video-backend.tar
   git log --oneline -- archive/lute-ai-video-backend.tar | head -5
   ```

2. **使用 git filter-branch 清除（保守方案，不改变其他历史）**
   ```bash
   cd /Users/pray/project/hermes_evo/AI_vedio
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch archive/lute-ai-video-backend.tar' \
     --prune-empty --tag-name-filter cat -- --all
   ```

3. **添加 `.gitignore` 规则防止再次提交**
   在 `.gitignore` 中添加：
   ```
   # Large binary archives
   archive/*.tar
   archive/*.tar.gz
   ```

4. **清理引用并压缩**
   ```bash
   git for-each-ref --format="%(refname)" refs/original/ | xargs -n 1 git update-ref -d
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   ```

**验证标准**:
- [ ] `git log --oneline -- archive/lute-ai-video-backend.tar` 返回空
- [ ] `du -sh .git` 显著减小
- [ ] `.gitignore` 包含 `archive/*.tar` 规则

**风险**: `git filter-branch` 会重写历史。如果有多人协作，需要协调 force push。鉴于这是私有项目（单开发者），风险较低。

---

### Task 1.3 — 清理百度网盘同步产物

| 属性 | 值 |
|------|-----|
| 关联项 | SEC-3, M5 |
| 严重程度 | P0 |
| 工时 | 0.5h |
| 前置依赖 | 无 |

**背景**: 30+ 个 `*.baiduyun.uploading.cfg` 文件散布在 `deploy/lighthouse/`、`docs/runbooks/`、`docs/workflows/`、`scripts/` 等目录中，已被 git 追踪。

**执行步骤**:

1. **查找所有文件**
   ```bash
   cd /Users/pray/project/hermes_evo/AI_vedio
   find . -name "*.baiduyun.uploading.cfg" -not -path "./.git/*" | sort
   ```

2. **批量从 git 移除并删除**
   ```bash
   find . -name "*.baiduyun.uploading.cfg" -not -path "./.git/*" -exec git rm --cached {} \;
   # 文件仍保留在磁盘上，但不再被追踪
   ```

3. **验证 `.gitignore` 规则**
   确认 `.gitignore` 包含：
   ```
   *.baiduyun.uploading.cfg
   .*.baiduyun.uploading.cfg
   ```

4. **提交**
   ```bash
   git commit -m "chore: remove baiduyun sync artifacts from git tracking
   
   30+ *.baiduyun.uploading.cfg files scattered across deploy/, docs/,
   and scripts/. .gitignore rules verified.

   Ref: SEC-3 from debt-audit-report-2026-06-09.md"
   ```

**验证标准**:
- [ ] `find . -name "*.baiduyun.uploading.cfg" -not -path "./.git/*" | wc -l` = 0（已从 git 移除）
- [ ] `.gitignore` 规则覆盖该模式
- [ ] `git status` 干净

**风险**: 极低。`*.baiduyun.uploading.cfg` 是百度网盘同步锁文件，删除对代码无影响。

---

### Task 1.4 — 对齐 .env.example 与代码实际使用的环境变量

| 属性 | 值 |
|------|-----|
| 关联项 | CFG-1, CFG-2, D82 |
| 严重程度 | P1 |
| 工时 | 2h |
| 前置依赖 | Task 1.1（密钥轮换后更新文档更安全） |

**背景**: `src/config.py` 及多个模块使用 30+ 个环境变量，这些变量未在 `.env.example` 中记录。特别是 `SHOPIFY_ACCESS_TOKEN`（代码用） vs `SHOPIFY_API_KEY`（`.env.example` 用）存在名称不匹配。

**执行步骤**:

1. **列出所有代码中使用的环境变量**
   基于 `grep -roh 'os\.getenv\|os\.environ\.get' src/` 的结果，已确认以下变量缺文档：

   | 变量名 | 使用位置 | 默认值 | 必须 |
   |--------|----------|--------|------|
   | `LOG_LEVEL` | `config.py:23` | `INFO` | 否 |
   | `RENDERING_SERVICE_URL` | `skills/remotion_assemble.py:121`, `routers/health.py:135` | `""` | 否 |
   | `APP_VERSION` | `_version.py:22` | 自动 | 否 |
   | `MEDIA_SIGN_SECRET` | `routers/media.py:18` | API_KEY | 否 |
   | `ADMIN_LOG_RETENTION_DAYS` | `routers/admin/logs.py:178` | `30` | 否 |
   | `POYO_IMAGE_MAX_POLLS` | `tools/gpt_image_client.py:35` | `72` | 否 |
   | `SKIP_THUMBNAIL_IN_AUTO` | `pipeline/step_runner.py:426` | `""` | 否 |
   | `BRAND_PACKAGE_USE_PG` | `storage/asset_stores.py:38` | `""` | 否 |
   | `TIKTOK_USERNAME` | `connectors/tiktok_connector.py:95,186` | `user` | 否 |
   | `SHOPIFY_ACCESS_TOKEN` | `config.py:132`, `connectors/shopify_connector.py:42` | `""` | 否 |
   | `SHOPIFY_API_PASSWORD` | `connectors/shopify_connector.py:41` | `""` | 否 |
   | `SUPABASE_URL` | `config.py:121` | `""` | 否 |
   | `SUPABASE_ANON_KEY` | `config.py:122` | `""` | 否 |
   | `SUPABASE_SERVICE_KEY` | `config.py:123` | `""` | 否 |
   | `FACEBOOK_ACCESS_TOKEN` | `config.py:131` | `""` | 否 |
   | `SEEDANCE_API_KEY` | `config.py:165` | `""` | 否 |
   | `SEEDANCE_API_BASE_URL` | `config.py:166` | `https://api.seedance.ai` | 否 |
   | `COSYVOICE_VOICE_FEMALE` | `config.py:161` | TTS female voice | 否 |
   | `POYO_TTS_MODEL` | `config.py:175` | `generate-music` | 否 |
   | `ALLOW_MOCK_MODE` | `config.py:179` | `""` | 否 |
   | `S3_VIRAL_EXTRACT_DISABLED` | `config.py:183` | `1` | 否 |
   | `MOCK_PRODUCT_NAME` | `config.py:109` | `X1` | 否 |
   | `MOCK_PRODUCT_CATEGORY` | `config.py:110` | `wearable breast pump` | 否 |
   | `KIMI_MODEL` | `config.py:118` | `kimi-k2-0905-preview` | 否 |
   | `ENVIRONMENT` | `config.py:178` | `development` | 否 |
   | `C2PA_ENABLED` | `tools/c2pa_signer.py:46` | `""` | 否 |
   | `C2PA_CERT_PATH` | `tools/c2pa_signer.py:121` | `""` | 否 |
   | `C2PA_KEY_PATH` | `tools/c2pa_signer.py:122` | `""` | 否 |
   | `C2PA_TSA_URL` | `tools/c2pa_signer.py:139` | `http://timestamp.digicert.com` | 否 |

2. **修复名称不匹配**
   - `.env.example` 第 76 行的 `SHOPIFY_API_KEY=` 保持不变（Shopify connector 同时使用 `SHOPIFY_API_KEY` 和 `SHOPIFY_ACCESS_TOKEN`）
   - 新增 `SHOPIFY_ACCESS_TOKEN=` 和 `SHOPIFY_API_PASSWORD=` 到 Shopify section
   - 在 `src/connectors/shopify_connector.py` 中统一使用 `SHOPIFY_ACCESS_TOKEN`（优先）降级到 `SHOPIFY_API_KEY`（兼容）

3. **更新 `.env.example`**
   将上述 30 个变量追加到 `.env.example` 末尾，按功能分组并附文档注释。

4. **验证一致性**: 运行 `tests/test_env_config_ssot.py`（P1-30 已有的 guard）确认对齐。

**验证标准**:
- [ ] `diff <(grep -roh 'os\.getenv(".*")\|os\.environ\.get(".*")' src/ | sort -u) <(grep -o '^[A-Z_]*=' .env.example | tr -d '=' | sort -u)` 无遗漏
- [ ] `tests/test_env_config_ssot.py` 通过
- [ ] Shopify connector 同时支持 `SHOPIFY_API_KEY` 和 `SHOPIFY_ACCESS_TOKEN`

**风险**: 低。仅文档更新，不改变运行时行为。

---

### Task 1.5 — 删除已知死代码：api_assets.py 和 s2_brand_pipeline.py shim

| 属性 | 值 |
|------|-----|
| 关联项 | D9, D10 |
| 严重程度 | P1 |
| 工时 | 1h |
| 前置依赖 | 无 |

**背景**:
- `src/api_assets.py` 是 `/api/assets/*` 的遗产 in-memory shim。所有功能在 `src/routers/assets.py` 和 `src/routers/portfolio.py` 中已重复实现。
- `src/pipeline/s2_brand_pipeline.py` 是弃用包装器，仅从 `_v2` 重新导出并发出弃用警告。无内部调用者。

**执行步骤**:

1. **确认 api_assets.py 无活跃调用者**
   ```bash
   grep -r "api_assets" src/ --include="*.py" | grep -v "api_assets.py"
   ```
   预期结果：仅在 `src/api.py:362` 的 try/except mount 中找到引用。

2. **移除 api_assets.py**
   - 从 `src/api.py` 中移除 try/except mount 块（约第 360-370 行）
   - `git rm src/api_assets.py`
   - 验证 `/api/assets/legacy/*` 端点不再被挂载

3. **确认 s2_brand_pipeline.py 无活跃调用者**
   ```bash
   grep -r "s2_brand_pipeline\b" src/ --include="*.py" | grep -v "_v2\|s2_brand_pipeline.py"
   ```
   预期结果：空（仅 `_v2` 被使用）。

4. **移除 s2_brand_pipeline.py shim**
   - 更新 `src/routers/scenario.py` 中任何直接引用旧 shim 的路径 → 指向 `s2_brand_pipeline_v2`
   - `git rm src/pipeline/s2_brand_pipeline.py`

5. **提交**
   ```bash
   git commit -m "chore: remove dead legacy shim code
   
   - Removed src/api_assets.py: all functionality duplicated in
     routers/assets.py and routers/portfolio.py
   - Removed src/pipeline/s2_brand_pipeline.py: frozen deprecation
     shim, zero internal callers remain
   
   Ref: D9, D10 from debt-audit-report-2026-06-09.md"
   ```

**验证标准**:
- [ ] `ruff check src tests --statistics` 通过
- [ ] `pytest tests/test_api_assets_legacy_boundary.py` 调整为不再断言旧路由存在（或删除该测试）
- [ ] `pytest tests/test_s2_deprecated_shim_boundary.py` 调整为不再断言旧文件存在（或删除该测试）
- [ ] S1-S5 hermetic 回归通过：`make test-hermetic-scenarios`

**风险**: 低。两者都是已确认的死代码。但 `api_assets.py` 被前端 OpenAPI types 引用（`web/src/types/api.generated.ts`），**不能同时删除后端路由**——只是移除文件本身，路由实现已迁移到 `routers/assets.py`。

---

### Task 1.6 — 修复测试中长达 60 秒的硬性 sleep

| 属性 | 值 |
|------|-----|
| 关联项 | TST-1 |
| 严重程度 | P0 |
| 工时 | 1h |
| 前置依赖 | 无 |

**背景**: `tests/test_bg_registry.py:22,63` 和 `test_bg_registry_leak_contract.py:69` 使用 `asyncio.sleep(60)`，导致这些测试耗时极长且在 CI 中脆弱。

**执行步骤**:

1. **重构 test_bg_registry.py**
   ```python
   # Before:
   await asyncio.sleep(60)
   assert task.done()
   
   # After:
   try:
       await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
   except asyncio.TimeoutError:
       pass  # Task is expected to still be running
   # For "task should complete" assertions, use:
   await asyncio.wait_for(task, timeout=5.0)
   ```

2. **重构 test_bg_registry_leak_contract.py**
   同上模式，将 60s 替换为 5s timeout + proper async patterns。

3. **运行测试确认修复**
   ```bash
   python -m pytest tests/test_bg_registry.py tests/test_bg_registry_leak_contract.py -v --timeout=30
   ```

**验证标准**:
- [ ] 两个测试文件在 30 秒内完成（vs 之前的 120+ 秒）
- [ ] 所有测试断言仍然通过
- [ ] `ruff check tests/test_bg_registry.py tests/test_bg_registry_leak_contract.py` 通过

**风险**: 低。降低 sleep 时间可能与原始测试意图冲突（测试取消语义的 race condition）。使用 `wait_for` + `shield` 模式更安全地表达测试意图。

---

### Phase 1 完成检查清单

- [ ] 生产密钥已从 git 移除且已轮换
- [ ] Docker 压缩包已从 git 历史清除
- [ ] 百度网盘产物已清理
- [ ] `.env.example` 包含全部 30 个缺失变量
- [ ] 死代码 shim 已移除
- [ ] 测试不再有 60 秒硬 sleep
- [ ] `ruff check src tests --statistics` 通过
- [ ] S1-S5 hermetic 回归通过

---

## Phase 2: 关键基础设施修复 <a id="phase-2"></a>

**时间**: Day 3-5 | **工时**: 13h | **目标**: 修复部署和安全基础设施缺口

### Task 2.1 — 修复渲染服务 deploy.sh 管理

| 属性 | 值 |
|------|-----|
| 关联项 | DEP-1, E8, E9, E10, E11 |
| 严重程度 | P1 |
| 工时 | 2h |
| 前置依赖 | Task 1.1（密钥已轮换） |

**背景**: `docker-compose.prod.yml` 定义了 `rendering` 服务，但 `deploy.sh` 从未管理它。此外 deploy.sh 有多个遗留问题：硬编码路径、使用旧版 `docker-compose`（v1）、Phase 0.6 hack。

**执行步骤**:

1. **审查当前 deploy.sh 状态**
   ```bash
   wc -l /Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/deploy.sh
   ```

2. **关键修复项**:
   - **a) 渲染服务管理**: 在 `deploy.sh` 中添加 `rendering` 容器的 stop/rebuild/start。如果渲染服务当前在生产中不使用，添加注释解释原因并添加 `--profile rendering` flag。
   - **b) docker-compose v1 → v2**: 将 `sudo docker-compose` 替换为 `sudo docker compose`（无连字符）。
   - **c) Phase 0.6 hack 移除**: 将 `sudo rm -f /opt/ai-video/src/routers/admin.py` 替换为实际的 Dockerfile 修复（确保 `admin.py` 有正确的 chmod）。
   - **d) 路径变量化**: 将 `/opt/ai-video/` 提取为 `DEPLOY_ROOT` 变量。
   - **e) IP 变量化**: 将 `101.34.52.232` 提取为 `SERVER_HOST` 变量，从环境或参数中读取。

3. **同步更新 smoke.sh**
   - 将 `BASE="${BASE:-https://101.34.52.232}"` 提取为变量
   - 将 `curl -k` 替换为 `curl --cacert /path/to/ca.pem` 或添加注释解释为何需要 `-k`

4. **验证**
   ```bash
   bash -n /Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/deploy.sh
   bash -n /Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/smoke.sh
   ```

**验证标准**:
- [ ] deploy.sh 语法检查通过（`bash -n`）
- [ ] 所有硬编码路径和 IP 已变量化
- [ ] `docker-compose` → `docker compose` 已替换
- [ ] 渲染服务状态明确（管理或不管理，有文档说明）
- [ ] `tests/test_lighthouse_smoke_token_guard.py` 通过

**风险**: 中等。部署脚本的更改需要保守处理。先在本地验证语法，备好回滚方案。

---

### Task 2.2 — 为 nginx 添加安全头部

| 属性 | 值 |
|------|-----|
| 关联项 | V2, V3 |
| 严重程度 | P0 |
| 工时 | 1h |
| 前置依赖 | 无（纯 nginx 配置更改） |

**背景**: `deploy/lighthouse/nginx.conf` 缺少基础安全头部。同时 `render.yaml:31` 的 `CORS_ORIGINS` 包含过时的 `https://zjgulai.github.io`。

**执行步骤**:

1. **在 nginx.conf 的 server 块中添加安全头部**
   ```nginx
   # Security headers — add inside each server block
   add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
   add_header X-Frame-Options "SAMEORIGIN" always;
   add_header X-Content-Type-Options "nosniff" always;
   add_header Referrer-Policy "strict-origin-when-cross-origin" always;
   add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
   ```

2. **修复 render.yaml 中的 CORS 配置**
   将 `render.yaml:31` 的 `CORS_ORIGINS: "https://zjgulai.github.io"` 替换为占位符或当前生产域名。

3. **部署并验证**
   ```bash
   ssh root@101.34.52.232 "nginx -t && nginx -s reload"
   curl -I https://101.34.52.232 2>/dev/null | grep -E "strict-transport|frame-options|content-type-options"
   ```

**验证标准**:
- [ ] `curl -I` 确认所有安全头部存在
- [ ] SSL Labs 或类似工具评分提升
- [ ] 现有功能未受影响（页面正常加载）

**风险**: 低。安全头部添加是纯增强。但 `Strict-Transport-Security` 有持久效应——一旦设置，浏览器会记住并拒绝 HTTP 连接。确认 HTTPS 配置正常后再添加。

---

### Task 2.3 — 统一双 schema 管理为 Alembic-only

| 属性 | 值 |
|------|-----|
| 关联项 | E22 |
| 严重程度 | P1 |
| 工时 | 3h |
| 前置依赖 | 无 |

**背景**: SQL schema 同时在 `src/storage/migrations/001_init.sql` 和 `migrations/alembic/versions/*.py` 中维护。`001_init.sql` 包含 ALTER TABLE 语句，与 Alembic 迁移重复。新 `docker compose up` 使用 SQL init 但不运行 Alembic，导致 schema 不一致。

**执行步骤**:

1. **分析当前状态**
   ```bash
   # 查看 Alembic 当前版本
   cd /Users/pray/project/hermes_evo/AI_vedio
   alembic current  # 需要 DATABASE_URL
   
   # 对比两个 schema 源
   diff <(grep -o 'CREATE TABLE\|ALTER TABLE' src/storage/migrations/001_init.sql | sort) \
        <(grep -o 'CREATE TABLE\|ALTER TABLE' migrations/alembic/versions/*.py | sort)
   ```

2. **决策**: 选择 Alembic 作为唯一的 schema 管理工具
   - 将 `001_init.sql` 中独有的 ALTER/CREATE 语句迁移到新的 Alembic 版本文件
   - 修改 `src/storage/db.py`：在 PG 连接时自动运行 `alembic upgrade head`（带 try/except 保护）
   - 在 `docker-compose.yml` 的 backend entrypoint 中添加 `alembic upgrade head`

3. **修改 001_init.sql**
   将其缩减为仅包含初始 CREATE TABLE 语句（与 Alembic 的 head revision 匹配），添加注释指向 Alembic 为真实来源。

4. **验证**
   ```bash
   # 清理数据库并重新运行迁移
   docker compose down -v
   docker compose up -d
   # 确认所有表都存在
   docker compose exec backend python -c "from src.storage.db import check_pg_health; print(check_pg_health())"
   ```

**验证标准**:
- [ ] Fresh `docker compose up` 通过 Alembic 正确创建所有表
- [ ] `001_init.sql` 仅包含初始模式，有到 Alembic 的指针注释
- [ ] 现有的生产数据库不受影响（Alembic 检测到已应用的迁移，跳过它们）

**风险**: 中等。Schema 迁移始终存在风险。在生产上运行 Alembic 之前，先在 staging 或本地 Docker 中彻底测试。

---

### Task 2.4 — 修复前端 i18n 硬编码字符串

| 属性 | 值 |
|------|-----|
| 关联项 | D67, D68 |
| 严重程度 | P1 |
| 工时 | 2h |
| 前置依赖 | 无 |

**背景**: `ExecutionBar.tsx` 和 `FastModePanel.tsx` 包含绕过 `t()` 函数的硬编码英文字符串。

**执行步骤**:

1. **ExecutionBar.tsx 修复**
   - 第 26 行：`"Generating..."` → `t("execution.generating")`
   - 第 39 行：`"Cancel"` → `t("execution.cancel")`
   - 在 `translations.ts` 中添加对应的中英文翻译

2. **FastModePanel.tsx 修复**
   - 第 208 行：`"Submitting..."` → `t("fastMode.submitting")`
   - 第 209 行：`"Enhancing prompt..."` → `t("fastMode.enhancingPrompt")`
   - 第 210 行：`"Generating video..."` → `t("fastMode.generatingVideo")`
   - 第 211 行：`"Synthesizing voiceover..."` → `t("fastMode.synthesizingVoiceover")`

3. **验证**
   ```bash
   cd web && npx tsc --noEmit -p tsconfig.json
   cd web && npm run lint
   cd web && npm test -- --run
   ```

**验证标准**:
- [ ] `grep -r '"[A-Z][a-z].*\.\.\."' web/src/components/ExecutionBar.tsx web/src/components/FastModePanel.tsx` 无硬编码字符串
- [ ] `translationCompleteness.test.ts` 通过（新 key 在 zh 和 en 中都存在）
- [ ] TypeScript + ESLint 通过

**风险**: 低。纯前端更改，不影响后端。

---

### Task 2.5 — 将弃用的前端 API 函数迁移为新的

| 属性 | 值 |
|------|-----|
| 关联项 | D13, D62 |
| 严重程度 | P1 |
| 工时 | 2h |
| 前置依赖 | 无 |

**背景**: `api.ts` 中 8 个标记为 `@deprecated` 的函数仍可导入。其中 `fetchState` 和 `submitReview` 仍在 `app/page.tsx` 中被活跃导入，将前端耦合到已弃用的 LangGraph 端点。

**执行步骤**:

1. **审计 app/page.tsx 中的使用情况**
   ```bash
   grep -n "fetchState\|submitReview" web/src/app/page.tsx
   ```

2. **迁移 fetchState 调用**
   - 如果当前使用 StepRunner 的 `/scenario/{s}/state/{label}` 端点，将 `fetchState` 调用替换为 `fetchS1State` 或对应的场景函数
   - 如果引用的是遗留的 `/pipeline/{thread_id}/state` 端点，请确认该路径仍需要，然后使用 Scenario API 包装器

3. **迁移 submitReview 调用**
   - 真正的审批流程现在通过 Gate API（`/scenario/{s}/gate/{label}/{gate_id}/approve`）
   - 将 `submitReview` 替换为 gate approve 调用

4. **移除弃用导出**
   - 从 `api.ts` 中删除 8 个弃用函数中的 6 个（保留 2 个活跃的直到迁移完成）
   - 一旦迁移完成，删除最后 2 个

**验证标准**:
- [ ] `app/page.tsx` 不再导入 `fetchState` 或 `submitReview`
- [ ] S1-S5 用户旅程在 demo 模式下正常工作
- [ ] `npm run build` 成功（无未使用导入警告）

**风险**: 中等。`fetchState` 可能在页面中有隐藏的使用模式。在 demo 模式下彻底测试主页流程。

---

### Task 2.6 — 修复硬编码的生产 IP——使用变量

| 属性 | 值 |
|------|-----|
| 关联项 | E11 |
| 严重程度 | P1 |
| 工时 | 1h |
| 前置依赖 | Task 2.1（与 deploy.sh 重构重叠） |

**背景**: `deploy/lighthouse/smoke.sh`、`build-and-deploy.sh`、`sync-landing-sidecars.sh` 和 `docker-compose.prod.yml` 中硬编码了 `101.34.52.232`。

**执行步骤**:

1. **统一使用环境变量**
   ```bash
   # 在每个脚本顶部：
   SERVER_HOST="${SERVER_HOST:-101.34.52.232}"
   ```
   然后使用 `$SERVER_HOST` 替换所有硬编码出现。

2. **更新 docker-compose.prod.yml**
   使用 `${SERVER_HOST:-101.34.52.232}` 替代直接 IP。

3. **验证**
   ```bash
   bash -n deploy/lighthouse/smoke.sh
   bash -n deploy/lighthouse/build-and-deploy.sh
   bash -n deploy/lighthouse/sync-landing-sidecars.sh
   ```

**验证标准**:
- [ ] `grep -r "101\.34\.52\.232" deploy/lighthouse/` 仅出现在变量默认值和注释中
- [ ] 所有脚本语法检查通过

**风险**: 低。纯重构，无逻辑更改。

---

### Task 2.7 — 将硬编码的 LLM URL 迁移到 config.py

| 属性 | 值 |
|------|-----|
| 关联项 | D36-D45 |
| 严重程度 | P1 |
| 工时 | 2h |
| 前置依赖 | Task 1.4（.env.example 已对齐） |

**背景**: 多个工具客户端硬编码了 API URL 和模型名称，本应从 `config.py` 读取。

**执行步骤**:

1. **在 config.py 中添加缺失的配置常量**
   ```python
   # ── LLM Client URLs (centralize from tools/llm_client.py) ──
   KIMI_API_BASE = os.environ.get("KIMI_API_BASE", "https://api.moonshot.cn/v1")
   ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
   OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
   
   # ── Image generation URLs ──
   OPENAI_IMAGE_API_BASE = os.environ.get("OPENAI_IMAGE_API_BASE", "https://api.openai.com/v1")
   ELEVENLABS_API_BASE = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1")
   
   # ── Connector URLs ──
   TIKTOK_API_UPLOAD_URL = os.environ.get("TIKTOK_API_UPLOAD_URL", "https://open-api.tiktok.com")
   SHOPIFY_GRAPHQL_URL_TEMPLATE = os.environ.get("SHOPIFY_GRAPHQL_URL_TEMPLATE", "https://{store}/admin/api/2024-07/graphql.json")
   ```

2. **更新工具客户端以从 config 读取**
   - `tools/llm_client.py:173`: `base_url=KIMI_API_BASE`（而不是硬编码 Moonshot URL）
   - `tools/llm_client.py:161`: 使用 `ANTHROPIC_MODEL` 而不是硬编码 Claude 名称
   - `tools/llm_client.py:194`: 使用 `OPENAI_MODEL`
   - `tools/gpt_image_client.py:78`: 使用 `OPENAI_IMAGE_API_BASE`
   - `tools/dalle_client.py:39`: 使用 `OPENAI_IMAGE_API_BASE`
   - `tools/elevenlabs_client.py:28`: 使用 `ELEVENLABS_API_BASE`
   - `connectors/tiktok_connector.py:22-25`: 使用 `TIKTOK_API_UPLOAD_URL`
   - `connectors/shopify_connector.py:22`: 使用 `SHOPIFY_GRAPHQL_URL_TEMPLATE`
   - `routers/admin/logs.py:239,248`: 使用 `POYO_API_BASE_URL` 和 `SILICONFLOW_API_BASE`
   - `services/fast_mode.py:159`: 使用 `DEEPSEEK_MODEL` 而不是硬编码 `deepseek-chat`
   - `pipeline/s1_product_pipeline.py:65-67`: `MAX_CLIPS_PER_DEMO` / `MAX_THUMBNAILS_PER_DEMO` 改为 env-configurable

3. **验证**
   ```bash
   ruff check src --statistics
   pytest tests/test_env_config_ssot.py -v
   ```

**验证标准**:
- [ ] `grep -r 'https://api\.' src/ | grep -v config.py | grep -v '#\|"""' | wc -l` 最小化
- [ ] 所有 LLM/API URL 硬编码已迁移
- [ ] 现有测试通过（默认值向后兼容）
- [ ] `tests/test_env_config_ssot.py` 通过

**风险**: 低。保留与原始硬编码值相同的默认值。仅将配置源切换到 config.py。

---

### Phase 2 完成检查清单

- [ ] 渲染服务明确有文档且（托管或不托管）
- [ ] Nginx 安全头部就位
- [ ] Schema 管理通过 Alembic 统一
- [ ] 前端 i18n 硬编码字符串已修复
- [ ] 弃用的前端 API 函数已迁移
- [ ] 部署脚本中的硬编码 IP 已变量化
- [ ] LLM/API URL 已从 config.py 集中化
- [ ] 生产部署烟雾测试通过

---

## Phase 3: 债务减少 <a id="phase-3"></a>

**时间**: Week 2 | **工时**: 34h | **目标**: 减少核心代码和架构债务

### Task 3.1 — 将重复的 _get_step_output() 重构为共享工具函数

| 关联项 | D1 | 工时 | 2h | 前置依赖 | 无 |

**执行步骤**:

1. 在 `src/pipeline/step_utils.py`（新文件）中创建规范的 `get_step_output(state, step_name) -> dict`
2. 更新 4 个调用位置以导入共享版本：
   - `pipeline/gate_manager.py:888`
   - `pipeline/step_runner.py:189`
   - `routers/_state.py:260`
   - `pipeline/s1_product_pipeline.py:238`
3. 在 `tests/test_step_utils.py` 中编写单元测试覆盖 4 个场景

**验证**: `pytest tests/test_step_utils.py tests/test_gate_scenario_configs.py tests/test_scenario_state_persistence_schema_contract.py -v`

---

### Task 3.2 — 将审计节点和路由函数去重

| 关联项 | D2, D3 | 工时 | 4h | 前置依赖 | Task 3.1 |

**执行步骤**:

1. 在 `graph/nodes.py` 中创建 `_build_audit_node(checkpoint_key, input_field)` 工厂函数
2. 从工厂调用替换 4 个审计节点定义
3. 在 `graph/routing.py` 中创建 `_build_routing_function(checkpoint_key, targets)` 工厂函数
4. 从工厂调用替换 4 个路由函数
5. 验证现有审计测试通过

**验证**: `pytest tests/test_auditor.py tests/test_auditor_quality_v2.py tests/test_routing.py tests/test_graph.py -v`

---

### Task 3.3 — 修复异步事件循环阻塞

| 关联项 | D54 | 工时 | 1h | 前置依赖 | 无 |

**执行步骤**:

1. 在 `connectors/tiktok_connector.py:224` 中将 `time.sleep(0.5)` 替换为 `await asyncio.sleep(0.5)`
2. 检查 `src/` 中是否还有其他 `time.sleep` 在 async 函数中
3. 如果无法立即测试（需要真实的 TikTok API），添加注释并标记为 P2

**验证**: `ruff check src/connectors/tiktok_connector.py`；代码审查确认无剩余同步阻塞

---

### Task 3.4 — 为连接器添加最小测试

| 关联项 | E1 | 工时 | 4h | 前置依赖 | 无 |

**执行步骤**:

1. 为 `connectors/tiktok_connector.py` 创建 `tests/test_tiktok_connector.py`：mock HTTP 响应，覆盖 3 个核心方法
2. 为 `connectors/shopify_connector.py` 创建 `tests/test_shopify_connector.py`：mock GraphQL 响应，覆盖 4 个核心方法
3. 两个测试文件均不发起真实 HTTP 请求

**验证**: `pytest tests/test_tiktok_connector.py tests/test_shopify_connector.py -v --cov=src/connectors`

---

### Task 3.5 — 拆分超大 SceneForm 组件

| 关联项 | D56 | 工时 | 6h | 前置依赖 | 无 |

**执行步骤**:

1. 提取每个场景的部分为单独的文件：
   - `web/src/components/scene-forms/ProductDirectForm.tsx`
   - `web/src/components/scene-forms/BrandCampaignForm.tsx`
   - `web/src/components/scene-forms/InfluencerRemixForm.tsx`
   - `web/src/components/scene-forms/LiveShootToVideoForm.tsx`
   - `web/src/components/scene-forms/BrandVlogForm.tsx`
2. 提取共享的表单原语（`CategorySelector`、`ProductDetails`）为共享组件
3. 更新 `SceneForm.tsx` 仅根据 `scene` prop 延迟加载正确的子组件
4. 在保持渲染输出的情况下，将 `CATEGORIES` 和 `BRAND_PACKAGES` 常量提升到组件外部

**验证**: `cd web && npx tsc --noEmit && npm run lint && npm test -- --run`

---

### Task 3.6 — 拆分超大 page.tsx 主页

| 关联项 | D55 | 工时 | 6h | 前置依赖 | Task 2.5（弃用 API 迁移完成） |

**执行步骤**:

1. 提取自定义 hooks：
   - `web/src/hooks/useSceneFlow.ts` — 场景选择/转换逻辑
   - `web/src/hooks/usePipelineSession.ts` — 会话恢复 + 轮询
   - `web/src/hooks/useGalleryManager.ts` — 作品集画廊状态
   - `web/src/hooks/useSmartCreate.ts` — Smart Create 提交 + 错误处理
2. 提取子组件：
   - `web/src/components/home/HomeGallery.tsx` — 最近作品网格
   - `web/src/components/home/SmartCreateSection.tsx` — Smart Create UI
3. 将 `GATE_SEQUENCE` 常量提升到组件外部（修复重新创建问题）
4. 将 `handleStart` 拆分为更小的函数（验证 → 构建配置 → 提交 → 过渡）

**验证**: `cd web && npx tsc --noEmit && npm run lint && npm test -- --run && npm run e2e:ui`

---

### Task 3.7 — 当 GuidedForm 活跃时移除遗留表单 DOM

| 关联项 | D14, D72 | 工时 | 3h | 前置依赖 | Task 3.5（SceneForm 已拆分） |

**执行步骤**:

1. 在 `SceneForm.tsx` 中添加条件渲染：当 `USE_GUIDED_FORM` 为真时，根本不渲染遗留表单部分
2. 从 DOM 中移除 `data-legacy-form` div 及其所有 760+ 个子节点
3. 确保 `aria-hidden` 的移除不会给屏幕阅读器引入问题

**验证**: `cd web && npx tsc --noEmit && npm run lint && npm run e2e:ui`

---

### Task 3.8 — 将 Record<string, unknown> 替换为类型化接口

| 关联项 | D31, D32, D33 | 工时 | 8h | 前置依赖 | Task 3.5, 3.6（组件已拆分） |

**执行步骤**:

1. **定义核心接口**（`web/src/types/pipeline.ts`）：
   ```typescript
   interface PipelineScript { segments: ScriptSegment[]; hooks: string[]; ... }
   interface PipelineStoryboard { shots: StoryboardShot[]; ... }
   interface GateCandidate { id: string; score: GateScore; output: Record<string, unknown>; ... }
   interface ContinuityDirection { sceneBeat: string; beatSummary: string; transitionIntent: string; }
   ```

2. **热路径优先替换**（按使用频率排序）：
   - `CandidateSelector.tsx`：5 个不安全的 `as Record<string, unknown>` 强制转换
   - `DirectorPlayback.tsx`：4 个不安全的强制转换
   - `GatePanel.tsx`：gate 候选 + 连续性诊断类型
   - `StepByStepView.tsx`：步骤输出类型
   - `OneShotResultView.tsx`：`ResultItem` 接口（使字段非可选）
   - `usePipelineStore.ts`：将 `unknown | null` 字段替换为实际的类型化接口

3. 在每个组件中逐步替换，在每个步骤后验证 TypeScript 编译

**验证**: `cd web && npx tsc --noEmit && npm run lint && npm test -- --run`

---

### Phase 3 完成检查清单

- [ ] 4 个重复的 `_get_step_output()` 变为 1 个共享工具函数
- [ ] 审计节点通过工厂模式去重
- [ ] 无异步事件循环阻塞残留
- [ ] TikTok 和 Shopify 连接器具有最小 mock 测试
- [ ] SceneForm 拆分为每个场景的组件，无遗留 DOM 渲染
- [ ] 主页通过 hooks 合理拆分
- [ ] 热路径的 `Record<string, unknown>` 减少 50%+

---

## Phase 4: 长期卫生 <a id="phase-4"></a>

**时间**: Week 3-4 | **工时**: 23h | **目标**: 清理、文档化和建立持续保护措施

### Task 4.1 — 清理 scripts/ 目录

| 关联项 | M2 | 工时 | 3h | 前置依赖 | 无 |

**执行步骤**:

1. 将 10 个一次性迁移脚本（`sync_bugfix.py`、`sync_bugfix_v2.py` 等）移至 `scripts/archive/`
2. 合并 4 个重复的 `run_s1_*` 脚本：保留 1 个规范的，删除 3 个重复的
3. 为 7 个 POYO 探测脚本添加大的注释块，解释其用途和风险
4. 从 git 中删除 11 个被 gitignore 的 `scripts/test_*.py` 文件

**验证**: `ruff check scripts/ --statistics`；`find scripts/ -name "*.py" | wc -l` 从 110+ 减少

---

### Task 4.2 — 归档历史文档

| 关联项 | D85-D93 | 工时 | 2h | 前置依赖 | 无 |

**执行步骤**:

1. 将自标记为历史的文档移至 `docs/archive/`：
   - `docs/workflows/five-scenario-pipeline-risk-assessment-stable-20260513.md`
   - `docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md`
   - `docs/workflows/2026-05-15-sprint-0-3-review-and-deploy-plan.md`
   - `docs/workflows/2026-05-23-video-speed-optimization-deploy-plan.md`
2. 将 `.kiro/plan/` 中 6+ 个已完成计划文件移至 `docs/archive/plans/`
3. 将 `docs/release/v0.4.0*.md` 移至 `docs/archive/releases/`
4. 在 `docs/archive/README.md` 中创建索引，解释归档内容
5. 将 `drafts/analysis/brand-momcozy/` 标记为 PENDING（如果有活跃工作）或移入 archive

**验证**: `find docs/ -name "*.md" | wc -l` 显著减少；文档导航仍然正常

---

### Task 4.3 — 统一 configs/ 与 runbooks/ 单一真相来源

| 关联项 | M3 | 工时 | 4h | 前置依赖 | Task 4.2 |

**执行步骤**:

1. 审计 `configs/`（35 个契约 YAML/JSON 文件）vs `docs/runbooks/` 的内容重叠
2. 决策框架：
   - **纯机器可读**（CI 测试使用）→ 保留在 `configs/`
   - **纯人类可读**（操作员使用）→ 移入 `docs/runbooks/`
   - **两者都需要**（契约 + 运行手册对）→ 建立清晰的交叉引用
3. 为每个重复对记录关系。示例：
   ```
   configs/admin-csrf-contract.yaml  ←→  docs/runbooks/admin-csrf-contract.md
   目的：合约是机器可验证的断言；运行手册是人类可读的流程
   ```
4. 在 `docs/runbooks/README.md` 中添加索引，将每个运行手册链接到其契约文件

**验证**: 无孤立文件；每个契约文件都有文档化的目的

---

### Task 4.4 — 通过 fail_under 加强 CI 覆盖率

| 关联项 | E5, E19 | 工时 | 2h | 前置依赖 | Task 3.4（连接器测试已添加） |

**执行步骤**:

1. 在 `pyproject.toml` 中添加 `fail_under = 40`（当前基线 ~35%，连接器测试会提升）
2. 从 `ci.yml` 的 coverage upload 步骤中移除 `continue-on-error: true`
3. 将 CI 中的 `coverage` 目标设为所需检查
4. 考虑添加 `coverage` 到 `make ci` 目标

**验证**: CI 在覆盖率低于阈值时失败；本地 `make coverage` 显示当前百分比

---

### Task 4.5 — 添加 LICENSE、CHANGELOG.md、SECURITY.md

| 关联项 | M6, V8 | 工时 | 1h | 前置依赖 | 无 |

**执行步骤**:

1. 创建 `LICENSE`（MIT 或根据业务偏好）
2. 从 `docs/release/` 条目引导 `CHANGELOG.md`
3. 创建 `SECURITY.md`，包含：报告电子邮件、范围、响应 SLA
4. 在 README 中添加 CI 状态徽章

**验证**: 三个文件均存在；README 徽章正确渲染

---

### Task 4.6 — 减少 except Exception 的使用

| 关联项 | D19-D26 | 工时 | 8h | 前置依赖 | Phase 3 完成 |

**执行步骤**:

1. 按影响优先级排序前 20 个最严重违规者：
   - `routers/scenario.py`（18 次出现）— 最高影响
   - `storage/asset_stores.py`（11 次出现）— PG 失败静默吞掉
   - `services/fast_mode.py`（5 次出现）— 用户可见
   - `connectors/shopify_connector.py`（4 次出现）— 错误静默
   - `connectors/tiktok_connector.py`（4 次出现）
   - `connectors/publish_engine.py`（2 次出现）
   - `routers/_deps.py`（2 次出现）
   - `pipeline/state_manager.py`（4 次出现）

2. **修复模式**（按文件）：
   - **Fast Mode**：将静默 `logger.warning` 替换为结构化错误传播，以便用户可以看到阶段失败
   - **Connectors**：将 `except Exception → return {"error": ...}` 替换为 `except SomeSpecificError`，并让意外错误传播
   - **Asset Stores**：保留 PG→dict 回退，但记录警告（已有），并为调用者添加 `_warnings` 属性以检查持久化失败

3. 一般规则：不捕获你无法处理的异常。记录并重新抛出，或将失败传播给调用者。

**验证**: `grep -c "except Exception" src/` 显著减少；现有测试仍然通过；S1-S5 hermetic 回归通过

---

### Task 4.7 — 审查并更新已知缺口文档

| 关联项 | D81, D84 | 工时 | 2h | 前置依赖 | Phase 1-3 完成 |

**执行步骤**:

1. 在 `docs/claude/known-gaps-stable.md` 中，将从本次审计中已修复的项目标记为完成
2. 将已完成的 P1-16 到 P1-65 项目折叠为摘要部分
3. 将 P2 项目重新排序，将基础设施和安全项目提升到功能项目之上
4. 更新 `AGENTS.md:606` 的 "Last updated" 日期为 2026-06-09
5. 添加指向本债务审计报告的指针

**验证**: `known-gaps-stable.md` 准确反映当前状态；无已解决的 TODO 项

---

### Task 4.8 — 设置 Dependabot 配置

| 关联项 | E18 | 工时 | 1h | 前置依赖 | 无 |

**执行步骤**:

1. 创建 `.github/dependabot.yml`：
   ```yaml
   version: 2
   updates:
     - package-ecosystem: "pip"
       directory: "/"
       schedule:
         interval: "weekly"
     - package-ecosystem: "npm"
       directory: "/web"
       schedule:
         interval: "weekly"
     - package-ecosystem: "docker"
       directory: "/"
       schedule:
         interval: "monthly"
   ```

**验证**: GitHub Dependabot 选项卡显示已配置的更新

---

### Phase 4 完成检查清单

- [ ] Scripts/ 目录从 110+ 个文件清理完毕
- [ ] 历史文档已归档
- [ ] Configs/ ↔ Runbooks/ 关系已文档化
- [ ] CI 强制执行覆盖率阈值
- [ ] LICENSE + CHANGELOG + SECURITY 文件存在
- [ ] `except Exception` 的使用减少 50%+
- [ ] Known-gaps 文档已更新
- [ ] Dependabot 活跃并正在运行

---

## 依赖关系图 <a id="依赖关系图"></a>

```
Phase 1 (8.5h, Day 1-2)
├── T1.1 移除密钥 ─────────────────────────────────────┐
├── T1.2 清除 Docker tar                                │
├── T1.3 清理百度网盘产物                                │
├── T1.4 对齐 .env.example ─── depends on: T1.1 ────────┤
├── T1.5 删除死代码 shim                                 │
└── T1.6 修复 60s sleep                                 │
                                                        │
Phase 2 (13h, Day 3-5)                                  │
├── T2.1 修复 deploy.sh ───── depends on: T1.1 ─────────┤
├── T2.2 nginx 安全头部                                  │
├── T2.3 统一 schema 管理                                │
├── T2.4 修复前端 i18n                                   │
├── T2.5 迁移弃用 API ────── blocks: T3.6 ──────────────┤
├── T2.6 变量化 IP ──────── depends on: T2.1 ───────────┤
└── T2.7 集中化 LLM URL ── depends on: T1.4 ────────────┤
                                                        │
Phase 3 (34h, Week 2)                                   │
├── T3.1 去重 step_output                               │
├── T3.2 去重审计节点 ───── depends on: T3.1 ───────────┤
├── T3.3 修复异步阻塞                                    │
├── T3.4 添加连接器测试 ─── blocks: T4.4 ───────────────┤
├── T3.5 拆分 SceneForm ─── blocks: T3.7, T3.8 ────────┤
├── T3.6 拆分 page.tsx ─── depends on: T2.5 ────────────┤
│                          blocks: T3.8                  │
├── T3.7 移除遗留 DOM ──── depends on: T3.5 ────────────┤
└── T3.8 类型化接口 ────── depends on: T3.5, T3.6 ──────┤
                                                        │
Phase 4 (23h, Week 3-4)                                 │
├── T4.1 清理 scripts/                                   │
├── T4.2 归档历史文档 ──── blocks: T4.3 ────────────────┤
├── T4.3 统一 configs/runbooks ─ depends on: T4.2 ──────┤
├── T4.4 CI 覆盖率门禁 ─── depends on: T3.4 ────────────┤
├── T4.5 标准文件                                       │
├── T4.6 减少 except Exception ─ depends on: Phase 3 ───┤
├── T4.7 更新 known-gaps ── depends on: Phase 1-3 ──────┤
└── T4.8 Dependabot                                    │
```

---

## 风险管理 <a id="风险管理"></a>

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 密钥轮换中断生产 | 中 | 高 | 安排低流量时段；准备回滚 .env.prod |
| Schema 迁移破坏数据库 | 中 | 高 | 先在 Docker 中彻底测试；先在 staging 上运行 Alembic |
| 弃用的 API 迁移破坏用户旅程 | 中 | 中 | 在 demo 模式下手动测试 S1-S5 |
| SceneForm 拆分引入回归 | 低 | 中 | 保留完整的 UI Playwright 视觉基线套件 |
| 类型更改破坏前端构建 | 低 | 低 | TypeScript 编译器捕获所有破坏；增量替换 |
| Git filter-branch 破坏协作 | 低 | 高 | 仓库为单开发者；与其他工作协调 |

---

## 验收标准总览 <a id="验收标准总览"></a>

### 每个 Phase 都必须通过的质量门:

| 检查项 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------|---------|---------|---------|---------|
| `ruff check src tests --statistics` | ✅ | ✅ | ✅ | ✅ |
| `cd web && npx tsc --noEmit` | ✅ | ✅ | ✅ | ✅ |
| `cd web && npm run lint` | ✅ | ✅ | ✅ | ✅ |
| `cd web && npm test -- --run` | ✅ | ✅ | ✅ | ✅ |
| Backend hermetic regression | ✅ | ✅ | ✅ | ✅ |
| `bash -n` on deploy scripts | — | ✅ | ✅ | ✅ |
| `npm run build` | ✅ | ✅ | ✅ | ✅ |
| UI Playwright visual baselines | — | — | ✅ | ✅ |
| Production smoke (`RUN_TOKEN_SMOKE=0`) | ✅ | ✅ | ✅ | ✅ |

### 最终交付物:

1. 所有 P0 项已修复（12/12）
2. 所有 P1 项已修复或已记录为已知且有缓解措施（至少 70/94 已修复）
3. 新贡献者可以在 1 小时内使用 `.env.example` 启动项目
4. CI 管道强制执行覆盖率、lint 和类型检查
5. 部署脚本提供有文档的变量，无硬编码密钥或 IP
6. 生产服务器具有安全头部，无硬编码凭证

---

*本执行计划与 [debt-audit-report-2026-06-09.md](./debt-audit-report-2026-06-09.md) 交叉引用。每次任务完成后，更新该报告中的状态。*
