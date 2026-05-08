# AI Video Pipeline — Project Guide for Claude

## Overview

**Short Video Agent** (v0.2.0) is a multi-agent AI video creation pipeline for cross-border e-commerce. It automates the full content production workflow: strategy → script → compliance → storyboard → asset sourcing → media generation → edit → audio → caption → thumbnail → distribution → analytics.

The pipeline is built on **LangGraph** with 16 nodes (12 worker + 4 self-audit) and 4 human-in-the-loop review checkpoints. It targets maternal/baby product categories (wearable breast pumps, feeding appliances) with 5 content scenarios.

**Current status:** Production live at `https://101.34.52.232` on Tencent Lighthouse since 2026-05-03. 5 scenarios verified end-to-end in non-demo mode (see `tmp/outputs/non-demo-end-to-end-verification-20260502.md`).

**2026-05-06 更新:**

- UI 主题从暗黑剧场翻转为 **Warm Light Professional Theme** (`#FDF8F6` 暖白底 + `#D75C70` Fortune Red accent)
- Portfolio 完成性能优化: TOP50 高质量素材 + nginx 静态直送 + poster thumbnail
- Footage 页面统一弹窗预览 + Materials 分类过滤(视频/图片/音频)
- **E2E 联调测试** (婴儿暖奶器品类): P0 三场景(Fast Mode/S1/S5)全部执行，报告见
`tmp/outputs/test-report-baby-bottle-warmer-e2e-20260506.md`
- **修复**: S5 strategy LLM 超时 60s → 120s (`s5_brand_vlog_pipeline.py`)
- **修复**: S1 `product_name` 字段读取错误，从 `"name"` 改为优先 `"product_name"`
(`s1_product_pipeline.py:100`)
- **修复**: Footage 页面无 thumbnail fallback icon 在 light 主题下对比度不足
(`text-white/40` → `text-[var(--text-muted)]`)
- CloudBase / Render are documented as alternative deploy paths but are not the canonical target.

**2026-05-07 更新 (Phase 2 架构归一化完成):**

- **双运行时架构统一**: S3/S4/S5 全部接入 `StepRunner` + `run_step()` 接口，与 S1 统一为
StepRunner 主运行时 + LangGraph 兼容运行时。`step_runner.py` 的 `_SCENARIO_CONFIGS`
集中管理 s1/s3/s4/s5 的 step_order 与 pipeline_class 映射。
- `**_pipeline` 延迟初始化**: `compile_pipeline()` 从模块导入时执行改为 `get_pipeline()`
工厂函数首次调用时延迟初始化，避免启动时即建立 PostgresSaver 连接。
- **SkillRegistry 实例隔离**: `_skills` 从类变量改为实例变量，每个 `SkillRegistry()` 实例
拥有独立的 skill 副本，并发/测试场景互不干扰。
- **API key 租户化 (P2-8)**: 新增 `api_keys` 表 + Alembic 迁移，`verify_api_key` 改为 async
函数，支持 PG 查询验证 + 环境变量 fallback。新增 `tenant_id` contextvar。
- **nginx rate limit**: 生产限流从 FastAPI middleware 内存实现迁移到 nginx
`limit_req_zone` + 各 API location 内显式 `limit_req`，前端 / 与 /_next/ 不限流。
- **LLMClient 缓存 TTL**: `_clients` 增加 300s TTL + 20 上限 + `key_hash` 租户维度，防止
死连接池堆积和无界内存增长。
- **target_languages 收口**: 6 处硬编码 `["en"]` 统一改为 `config.DEFAULT_LANGUAGES`。

**2026-05-07 更新 (Phase 4 完成):**

- **pyright 类型检查**: `pyproject.toml` 配置 `[tool.pyright]`，启用
`reportMissingTypeArgument` + `reportPossiblyUnboundVariable`，`src` + `tests` 0 错误。
发现并修复 2 个真实运行时缺陷（test_s1_e2e.py / test_media_clients.py 的 async 调用缺少 await）。
- **Prometheus exporter (T4.2)**: 新增 `src/telemetry_prometheus.py`，暴露 6 个指标
（pipeline_runs_total、pipeline_duration_seconds、step_duration_seconds 等），
`/telemetry/prometheus` 端点返回 Prom exposition 格式。
- **LangGraph 代理层 (T4.4)**: `/pipeline/*` 6 个端点保留 API 契约，内部代理到 StepRunner。
前端 7 个死函数标记 `@deprecated`，指引调用方迁移到 `/scenario/*` 端点。
- **死代码清理 (T4.3)**: 删除 `_try_save_metrics` 静默 ImportError、test_i18n.py ES/FR/DE
死测试、telemetry/cost_tracker 死函数，共 273 行清理。

**2026-05-07 更新 (生产部署修复):**

- **ChunkLoadError 修复**: `/footage` 页面 `Failed to load chunk 12k1vegccjm7k.js`。
根因：浏览器缓存旧 HTML + Turbopack content-hash 变化。修复：nginx `location /`
添加 `Cache-Control: no-store`，`location /_next/` 添加 `max-age=31536000, immutable`；
`deploy.sh` 构建前清理 `.next/standalone/` / `.next/static/` 旧产物。
- **循环导入修复**: `src/graph/nodes.py` 顶层 `from src.routers._state import _register_background_task` 导致 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py`
循环。改为 `nodes.py` 内 `_register_bg()` helper 函数延迟导入。
- **nginx 语法修复**: `limit_req off;` 不是有效 nginx 语法，`location /health` 与
`/api/media/` 改为 `limit_req zone=api_limit burst=100/1000 nodelay;`。
- **nginx 限流误伤前端 (429 风暴) 修复**: `server` 块顶层 `limit_req zone=api_limit burst=20 nodelay` 会被未显式覆盖的 `location` 默认继承，前端 `/` 和 `/_next/` 也跟着
限流。Next.js 首页冷启动 1s 内 30+ 并发请求秒爆 burst=20，浏览器看到 429 风暴。
修复：删除顶层声明，改为 7 个 API location 内部各自显式 `limit_req`，前端 location
不限流。验证：50 并发 `/api/*` → 21×404 + 29×429（限流正常），30 并发 `/` → 全 200。

**2026-05-07 更新 (Admin Panel Phase 1):**

- **Admin Panel 全链路接线**: 新增 `/api/admin/*` 端点群 + `/admin` 前端页面，完成 Phase 1
后台管理系统。包含：Dashboard 概览、Tenant 管理(CRUD + API Key 生命周期)、
System Logs 查看、System Health 状态监控。
- **双层认证架构**: Admin session-cookie 认证(邮箱+密码)与租户 API key 认证完全独立，
零交叉。`verify_admin_session` 依赖注入模式与 `verify_api_key` 对称。
- **CORS credentials 支持**: `allow_credentials=True` 启用，Admin cookie (HttpOnly)
跨域可正常发送。
- **Response wrapper cookie 保留**: 修复中间件重建 JSONResponse 时丢失 Set-Cookie
header 的缺陷（admin login 设置的 session cookie 会被正确传递）。
- **后台任务**: startup 注册 3 个周期性任务 — health check(5min)、session cleanup(1h)、
log cleanup(1h)。
- **error_logs 持久化**: `ErrorCollector.collect()` 自动写入 `error_logs` 表，
Admin Logs 页面可查询。保留 30 天(可配置 `ADMIN_LOG_RETENTION_DAYS`)。
- **Alembic 迁移**: `2d6b8e9c0f1a_admin_panel_phase1.py` 创建 4 张新表
(`admin_accounts`, `admin_sessions`, `tenants`, `error_logs`)。
- **初始管理员脚本**: `scripts/create_admin.py <email> <password>` 创建首个 admin 账号。

**2026-05-08 更新 (4-Option Plan 全面落地):**

- **统一异步执行框架 (A+B 合并)**: 所有场景(S1-S5)统一走 `POST /scenario/{s}/submit`
→ 返回 `{label, status: "queued"}` → 前端指数退避轮询 `GET /scenario/{s}/status/{label}`。
`StageProgress` 组件从 S1 独占泛化为全场景通用，按 scenario 映射到 3 阶段进度条
(writing → visuals → export)。Gate approve 后的后台续跑复用同一框架。
- **S3-S5 Gate 系统配置 (Phase 1C)**: `gate_manager.py` 从 S1-hardcoded 重构为
per-scenario 配置：`SCENARIO_GATE_DEFINITIONS` 定义 s1/s2/s3/s4/s5 各自的 gate 集合
与 after_step 映射；`candidate_scorer.py` 新增 `remix_script`、`character_identity`、
`vlog_strategy` 评分维度。`step_runner.py` 的 gate 触发逻辑也改为按 scenario 读取。
- **POYO Sanitizer Phase 2 (C)**: 新增 7 条英文规则（baby bottle / nipple / areola /
formula milk / baby food / postpartum / bottle feeding）+ 4 条中文规则（奶瓶 / 奶嘴 /
辅食 / 产后）。`poyo_client.py` 在 submit 时存储原始 input，failed 任务中检测
"content" 字样即触发 `poyo_cm_rejection` 结构化日志，保留原始 prompt 用于规则扩展。
新增 `tests/test_poyo_safety.py` 15 个单元测试。
- **监控告警基础设施 (D)**: 新增 `deploy/lighthouse/prometheus-alerts.yml`（6 条规则：
pipeline 错误率 / step p99 / API 5xx / API 延迟 / 后台任务激增 / pipeline 停滞）。
新增 `deploy/lighthouse/grafana-dashboard.json`（8 panel：runs/min、error rate、
step duration p50/p95/p99、API rate+latency、active tasks、runs today、avg duration、5xx count）。

**2026-05-08 更新 (生产部署修复):**

- **page.tsx TypeScript 构建错误** — `useExpertStore` 解构缺少 `setShowStageProgress` /
`currentStepIdx` / `setCurrentStepIdx`，Next.js `npm run build` 失败。补充解构后本地构建通过。
- **nginx `/telemetry/` 路由缺失** — `/telemetry/prometheus` 请求被路由到前端 404。
新增 `/telemetry/` location 转发到 backend。
- **nginx `/api/admin/` 路由前缀被 strip** — `/api/` catch-all `proxy_pass http://backend/`
去掉 `/api` 前缀，backend 收到 `/admin/auth/login` 不匹配 router 注册的 `/api/admin/auth/login`。
新增 `/api/admin/` location 保留完整前缀转发。
- **SSL 证书被 rsync 误删为空目录** — `server.crt` / `server.key` 不在本地 `deploy/lighthouse/`
中，`rsync --delete` 删除远程证书文件后 docker 创建空目录占位，nginx 挂载失败。
修复：重新生成自签名证书；**防御措施**：deploy.sh 前手动备份 SSL 文件，或改用 `rsync --exclude`。
- **prometheus-client 未装进容器** — `requirements.txt` 中已有 `prometheus-client>=0.20`，
但 backend image 未 rebuild（deploy.sh Phase 0 旧逻辑 `mtime` 比较在 `IMG_BUILT_TS=0`
时不触发警告）。已通过 `docker compose build backend` rebuild image 固化。
- **bcrypt 未装进容器** — Admin router 因 `No module named 'bcrypt'` 被跳过，login 500。
已通过 image rebuild 固化，`requirements.txt` 已包含 `bcrypt>=4.2`。
- **Alembic 不在 requirements.txt 中** — `alembic` 用于本地开发迁移，但生产部署也依赖它
执行 `alembic upgrade head`。当前生产表通过手动 SQL 创建。**已修复**：`alembic>=1.13`
已加入 `requirements.txt`，image rebuild 后容器内可直接执行 `alembic upgrade head`。
- **admin_accounts 表未创建** — Admin Panel 表通过 Alembic 迁移 `2d6b8e9c0f1a` 创建，
但生产从未运行过该迁移。直接用 asyncpg 执行 SQL 建表 + 插入初始 admin 账号。

**2026-05-08 更新 (结构简化):**

- **nginx.conf proxy header 提取** — 新增 `deploy/lighthouse/proxy_params.conf` 统一 4 个
proxy header，13 个 location 块全部改为 `include /etc/nginx/proxy_params.conf;`，
消除 ~60 行重复。`docker-compose.prod.yml` 同步挂载该文件。
- `**/telemetry/` burst 提升** — `burst=20` → `burst=100`，避免 Prometheus scraper 被限流。
- **page.tsx store 订阅拆分** — `currentStepIdx` / `showSteps` 从 `useExpertStore` 迁移到
`usePipelineStore`（它们描述的是全局 loading 状态，与 expert 模式无关）。
`useExpertStore` 字段从 10 个减至 6 个，根页面不再因 expert 无关状态变化而重渲染。

**2026-05-08 更新 (Gate 系统 + 上传测试扩展):**

- **Gate manager skill params 扩展** — `gate_manager.py` 新增 `remix_script`（S3）和
`vlog_strategy`（S5）的 `_build_skill_params` 分支，支持非 S1 场景的 gate 候选生成。
- **Gate 全链路测试** — `test_s1_gate_full_flow.py` 扩展 approve 成功路径测试（candidate
选择 + edited_output 写入 + current_step 推进）。新增 `test_gate_scenario_configs.py`
验证 S3/S4/S5 的 per-scenario gate 定义和 step_runner gate 触发逻辑。
- **Assets 上传 E2E** — 新增 `test_upload_e2e.py`，验证 multipart upload → 后端落盘 →
`/api/files` 列出 → `/api/media/` 可访问的完整链路。
- **Brand Packages 上传面板** — `brand-packages/page.tsx` 集成 `AssetUploader` 组件，
支持在品牌资产页面直接上传文件。

**2026-05-08 更新 (代码简化 /simplify 审查修复):**

- `**gate_manager.py` `_extract_step_input` 修复** — `remix_script` 分支原代码直接读取
`state["steps"]["video_analysis"]["output"]`，跳过 `_extract_step_input()` 辅助函数，
导致用户编辑 `video_analysis` 后的 `edited_output` 被忽略。修复后 S3 gate 候选生成
正确优先读取编辑版本 (`_build_skill_params` line ~911)。
- **删除复述代码的 WHAT 注释** — `gate_manager.py` 两处 `# S3: remix-script-skill expects...`
/ `# S5: product-strategy-skill expects...` 注释复述字典字面量内容，已删除。
- `**test_upload_e2e.py` 清理** — 删除 5 处 `from src.config import OUTPUT_DIR` 死导入；
提取 `upload_dir` fixture 统一收口 6 处重复的 `monkeypatch.setattr(...)`；精简
`test_upload_rejects_dotdot_filename` 多行 docstring。
- `**test_gate_scenario_configs.py` 清理** — 删除未使用的 `_get_gate_defs` / `_get_step_order` 导入。
- `**isolated_state_dir` fixture 提取到 conftest.py** — 原在 `test_s1_gate_full_flow.py`
和 `test_gate_scenario_configs.py` 各复制一份，现提取到 `tests/conftest.py` 全局复用。
- **测试验证** — `test_gate_scenario_configs.py`(52) + `test_s1_gate_full_flow.py`(41)
  - `test_upload_e2e.py`(10) 共 103 测试全部通过。

**2026-05-08 更新 (部署流程加固):**

- `**bcrypt` / `prometheus-client` / `alembic` 固化到 backend image** — 之前用
`docker exec pip install` + `docker commit` 临时修复，image rebuild 后丢失。
现 `requirements.txt` 已包含三项依赖，`Dockerfile.backend` rebuild 后全部固化。
Admin router 正常加载（`/api/admin/` 返回 401 而非 404），`alembic upgrade head`
可在容器内直接执行。
- `**Dockerfile.backend` 删除多余 `asyncpg` 安装** — 第 24 行 `pip install asyncpg>=0.29`
与 `requirements.txt` 重复，已删除。节省一层 layer，build 时间减少 ~1s。
- **deploy.sh Phase 0 hash 检测替代 mtime** — 原 `git log mtime` vs `docker inspect Created`
比较在 `IMG_BUILT_TS=0`（首次部署/无法获取 image 时间）时不触发警告。
改为 `sha256sum requirements.txt` 本地 hash vs image 内记录的 hash 比较，
不受 mtime 影响，首次部署也会正确提示 rebuild。
- **nginx `restart` → `--force-recreate`** — `docker-compose restart nginx` 只重启进程，
不重新挂载 volume。新增 `proxy_params.conf` 时 volume 变更不生效，导致 nginx
`[emerg] open() "/etc/nginx/proxy_params.conf" failed`。改为 `--force-recreate`
确保 volume 挂载始终与 `docker-compose.prod.yml` 一致。

**2026-05-08 更新 (第三轮质量提升 — 18 项全部完成):**

本轮将质量体系从 "事后检查" 升级为 "全过程可控"，引入行业框架 (Hook-Retain-Reward-Action, AIDA)
和 ML 算法。所有新 ML 依赖均采用 lazy import，不强制安装。

- **P0 — 生产级紧急修复 (4 项)**:
  - `seedance_video_generate.py`: 新增 `_check_frame_variance()` — ffmpeg 抽 3 帧缩放到 32x32，
    MSE 检测静态图 (阈值 50) + 平均亮度检测黑屏 (阈值 20)。集成到 `_self_verify` 的 `all_ok`。
  - `remotion_assemble.py`: 新增 `_check_av_sync()` — ffprobe 分别读取视频/音频流 duration，
    绝对差异 >0.5s 或相对差异 >5% 报 `av_desync`。集成到 `_self_verify`。
  - `media_quality_audit.py`: 扩展 `_audit_final_video()` — `_get_video_specs()` 提取 width/height/
    fps/bitrate，分辨率非 9:16 / fps<25 / bitrate<1.5Mbps 均扣分。
  - `auditor.py`: Hook Strength 从纯 duration 检查扩展为 duration×0.4 + text×0.6。新增
    `_score_hook_text()` 检测 8 类 curiosity gap + pattern interrupt 信号。

- **P1 — 质量显著提升 (6 项)**:
  - `src/quality/clip_alignment.py`: CLIP `openai/clip-vit-base-patch32` 文本-图像对齐，
    sigmoid 归一化，阈值 0.28(强)/0.18(弱)。lazy import transformers+torch。
  - `src/quality/nr_quality.py`: BRISQUE-like 无参考质量评估。pyiqa BRISQUE 优先，
    fallback 到 OpenCV Laplacian 方差 + Michelson 对比度 + 亮度分布。
  - `auditor.py`: 新增 Information Density criterion — words-per-second 2.5-3.5 optimal。
  - `auditor.py`: 新增 Emotional Arc criterion — `_score_emotional_arc()` 检查 negative→positive
    转换、CTA urgency、hook attention 信号。
  - `seedance_prompt.py`: `_score_prompt_quality()` 检查 action/camera/lighting/shot_type/
    forbidden_words 五项齐全度，返回 per-prompt quality_score。
  - `script_writer.py`: `_self_check_script()` 检查 hook 强度、USP 覆盖、时长合规、
    segment 完整性，结果写入 `_self_check` 字段。

- **P2 — 竞争壁垒 (4 项)**:
  - `src/quality/scene_analysis.py`: PySceneDetect `ContentDetector` 场景边界检测，
    对比 expected_segments 计算 structural_match。
  - `src/quality/face_consistency.py`: DeepFace (Facenet) → MediaPipe face_mesh landmark
    cosine similarity 双层 fallback，替换 histogram 方法。
  - `src/quality/safe_zone.py`: TikTok/YouTube Shorts/Instagram Reels 平台 UI 遮挡区检查，
    drawtext y 表达式解析。
  - `src/quality/ab_tracker.py` + `gate_manager.py`: gate 选择记录 + performance 数据关联。
    `compute_variant_performance()` 按 variant (standard/creative/conservative) 聚合。

- **P3 — 长期规划 (4 项)**:
  - `src/quality/viral_predictor.py`: 8 因子加权 ensemble（hook/density/cta/emotion/
    thumbnail/video），未来可替换为 LightGBM。
  - `src/quality/ctr_estimator.py`: thumbnail CTR + script conversion heuristic 预估。
  - `src/quality/dynamic_thresholds.py`: 读取 ABTracker 数据，按 winning variant 自动调整
    hook_duration_max 等阈值。
  - `src/quality/skill_versioning.py`: SkillMonitor 记录 latency/success/fallback rate，
    SkillVersionRegistry 版本管理。

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────┐
│  web/  (Next.js 16, React 19, TypeScript, Tailwind 3)   │
│  Port 3000 — Review UI, scene config, pipeline monitor   │
│  State: Zustand (useAppStore/usePipelineStore/useExpert) │
│  i18n: zh-CN / en                                       │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP + API Key auth
                         ▼
┌─────────────────────────────────────────────────────────┐
│  src/api.py  (FastAPI, Python 3.11+, Port 8001)          │
│  Routers: pipeline, scenario, distribution, metrics,     │
│           assets, media, health, telemetry, admin        │
│  Middleware: CORS, rate-limit, response-wrapper, logging │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────────┐
│ LangGraph    │ │ StepRunner  │ │ External APIs     │
│ Pipeline     │ │ (S1-S5)     │ │ DeepSeek V4-Pro   │
│ 16 nodes     │ │ run_step()  │ │ poyo.ai (img/vid) │
│ 4 checkpoints│ │ per-scenario│ │ CosyVoice (TTS)   │
└──────────────┘ └─────────────┘ └──────────────────┘
          │              │              │
          │    ┌─────────┴──────────┐   │
          │    ▼                    ▼   │
          │ ┌─────────────┐  ┌──────────┴─────┐
          │ │ Quality     │  │ Quality        │
          │ │ Assessment  │  │ Monitoring     │
          │ │ (CLIP/BRISQ/│  │ (AB tracker /  │
          │ │ face/safe)  │  │ skill version) │
          │ └─────────────┘  └────────────────┘
          │              │
          └──────────────┴──────────────┐
                         ▼              ▼
               ┌─────────────┐  ┌──────────────┐
               │ PostgreSQL  │  │ SQLite       │
               │ (primary)   │  │ (fallback)   │
               └─────────────┘  └──────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  rendering/  (Remotion 4, TypeScript, standalone)        │
│  Compose .mp4 from pipeline state JSON                   │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AI_vedio/
├── src/                        # Python backend
│   ├── api.py                  # FastAPI app entrypoint (startup, middleware, router mounts)
│   ├── api_assets.py           # Legacy /api/assets/* compat shim — in-memory dict storage,
│                               #   referenced by frontend OpenAPI types; do not add new
│                               #   features here. Canonical path is src/routers/assets.py
│   ├── config.py               # All env-var config + structlog setup + sensitive-data sanitizer
│   ├── telemetry.py            # TraceContext, PipelineMetrics, ErrorCollector
│   ├── telemetry_endpoint.py   # Telemetry HTTP endpoints
│   ├── agents/                 # 12 worker + 4 audit agent implementations
│   │   ├── strategy.py         # Content calendar generation
│   │   ├── script_writer.py    # English-only script writer (ES/FR/DE removed)
│   │   ├── auditor.py          # Self-audit scoring (4 checkpoints)
│   │   ├── compliance.py       # Brand compliance pre-check
│   │   ├── storyboard.py       # Visual shot planning
│   │   ├── asset_sourcing.py   # Asset library search (Supabase/pgvector or mock)
│   │   ├── media_generation.py # Image generation
│   │   ├── editor.py           # Video editing composition plan
│   │   ├── audio_designer.py   # Audio plan + TTS
│   │   ├── caption.py          # Caption plan generation
│   │   ├── thumbnail.py        # Thumbnail variant generation
│   │   ├── distribution.py     # Platform distribution plan
│   │   ├── analytics.py        # Performance analytics report
│   │   ├── i18n.py             # Internationalization service
│   │   └── prompts/            # Language-specific prompt templates (en/es/fr/de)
│   ├── graph/                  # LangGraph pipeline definition
│   │   ├── pipeline.py         # Graph assembly, compilation, checkpoint config
│   │   ├── nodes.py            # 16 node function implementations
│   │   └── routing.py          # Conditional routing + retry guard + audit guard + D10 override
│   ├── pipeline/               # Scenario-specific pipeline implementations
│   │   ├── s1_product_pipeline.py    # S1: Product Direct
│   │   ├── s2_brand_pipeline.py      # S2: Brand Campaign
│   │   ├── s3_remix_pipeline.py      # S3: Influencer Remix
│   │   ├── s4_live_shoot_pipeline.py # S4: Live Shoot
│   │   ├── s5_brand_vlog_pipeline.py # S5: Brand VLOG
│   │   ├── step_runner.py            # Step-by-step execution engine
│   │   ├── step_editor.py            # Step output editing + downstream invalidation
│   │   ├── state_manager.py          # Pipeline state persistence
│   │   ├── gate_manager.py           # Expert Studio 3-candidate generation + approval
│   │   └── candidate_scorer.py       # AI evaluator for gate candidates
│   ├── routers/                # FastAPI domain routers (mounted in api.py)
│   │   ├── pipeline.py         # /pipeline/* — start, state, review, output, export
│   │   ├── scenario.py         # /scenario/* — s1-s5 runs, steps, gates, regenerate, fast-mode
│   │   ├── distribution.py     # /distribution/* — publish, platforms
│   │   ├── metrics.py          # /metrics/* — video performance data
│   │   ├── assets.py           # /assets/* — brand assets, uploads
│   │   ├── media.py            # /media/* — media file serving
│   │   ├── health.py           # /health — health check + persistence status + Remotion env
│   │   ├── admin.py            # /api/admin/* — Dashboard/Tenants/Logs/Health/Auth
│   │   ├── _deps.py            # Shared: verify_api_key, _safe_error, _serialize, _inject_api_keys
│   │   ├── _admin_deps.py      # Shared: verify_admin_session, login rate limit, admin contextvar
│   │   └── _state.py           # Shared: pipeline instances, thread cache, request models
│   ├── models/                 # Pydantic models + TypedDict state
│   │   ├── state.py            # VideoPipelineState (30+ fields)
│   │   ├── __init__.py         # All data models: Script, Storyboard, AuditReport, etc.
│   │   ├── brand.py            # Brand guidelines models
│   │   └── influencer.py       # Influencer profile models
│   ├── connectors/             # External platform API connectors
│   │   ├── base.py             # Abstract connector interface
│   │   ├── registry.py         # Connector registry + factory
│   │   ├── publish_engine.py   # Multi-platform publish orchestrator
│   │   ├── tiktok_connector.py # TikTok API
│   │   └── shopify_connector.py# Shopify API
│   ├── tools/                  # Shared utilities and external API clients
│   │   ├── llm_client.py       # Multi-provider LLM with contextvars-based key isolation
│   │   ├── poyo_client.py      # poyo.ai image/video API
│   │   ├── seedance_client.py  # Seedance video generation API
│   │   ├── cosyvoice_client.py # SiliconFlow CosyVoice TTS
│   │   ├── dalle_client.py     # DALL-E 3 (legacy)
│   │   ├── elevenlabs_client.py# ElevenLabs TTS (legacy)
│   │   ├── gpt_image_client.py # GPT-4o image via poyo
│   │   ├── remotion_renderer.py# Remotion environment validation
│   │   ├── retry.py            # Exponential backoff (3 attempts)
│   │   ├── error_classifier.py # Structured error classification
│   │   ├── webhook_manager.py  # Event dispatch (audit.completed, pipeline.completed)
│   │   ├── asset_library.py    # Supabase + pgvector asset search
│   │   ├── asset_storage.py    # Asset file storage
│   │   ├── translate.py        # Chinese→English product catalog translation
│   │   ├── video_downloader.py # Video download from URLs
│   │   └── product_catalog.py  # Product data helpers
│   ├── skills/                 # Pipeline step skill implementations
│   │   ├── base.py             # Abstract skill interface
│   │   ├── registry.py         # Skill registry
│   │   ├── script_writer.py    # Script generation skill
│   │   ├── storyboard.py       # Storyboard skill
│   │   ├── keyframe_images.py  # Keyframe generation
│   │   ├── seedance_prompt.py  # Seedance prompt construction
│   │   ├── seedance_video_generate.py # Seedance video generation
│   │   ├── remotion_assemble.py# Remotion video assembly
│   │   ├── thumbnail_prompt.py # Thumbnail generation
│   │   ├── gpt_image_generate.py # GPT image generation
│   │   ├── elevenlabs_tts.py   # ElevenLabs TTS skill
│   │   ├── video_analysis.py   # Video content analysis
│   │   ├── viral_extractor.py  # Viral clip extraction
│   │   ├── product_strategy.py # Product strategy skill
│   │   ├── brand_compliance.py # Brand compliance skill
│   │   ├── media_quality_audit.py # Media quality auditing
│   │   ├── character_identity.py  # Character identity for VLOG
│   │   ├── remix_script.py     # Remix script generation
│   │   └── llm_skill.py        # Generic LLM-powered skill
│   ├── storage/                # Database layer
│   │   ├── db.py               # asyncpg pool + SQLite fallback + health checks
│   │   ├── repository.py       # ThreadRepository, PipelineStateRepository
│   │   ├── metrics_repository.py # Video metrics CRUD
│   │   └── migrations/         # SQL init scripts for Docker
│   ├── data/                   # Mock data and test fixtures
│   │   └── mock_quality.py     # Quality level simulation
│   ├── quality/                # ML-powered quality assessment modules (P0-P3)
│   │   ├── clip_alignment.py   # CLIP text-image alignment (P1-5)
│   │   ├── nr_quality.py       # No-reference quality: BRISQUE / OpenCV heuristics (P1-6)
│   │   ├── safe_zone.py        # Platform UI safe zone checker (P2-13)
│   │   ├── ab_tracker.py       # A/B test tracking for gate variants (P2-14)
│   │   ├── scene_analysis.py   # PySceneDetect video scene analysis (P2-11)
│   │   ├── face_consistency.py # MediaPipe/DeepFace identity verification (P2-12)
│   │   ├── viral_predictor.py  # Viral potential scoring ensemble (P3-15)
│   │   ├── ctr_estimator.py    # CTR / conversion estimation (P3-16)
│   │   ├── dynamic_thresholds.py # Auto-tune thresholds from feedback (P3-17)
│   │   └── skill_versioning.py # Skill performance monitoring (P3-18)
│   ├── services/               # Service layer
│   │   └── fast_mode.py        # Fast Mode: direct text→video without pipeline
│   └── tasks/                  # Background tasks
│       └── metrics_poller.py   # Video metrics polling
├── web/                        # Next.js 16 frontend
│   ├── src/
│   │   ├── app/                # App Router pages
│   │   │   ├── page.tsx        # Home / scene selection
│   │   │   ├── layout.tsx      # Root layout (dark theme, film grain, i18n provider)
│   │   │   ├── s1/page.tsx     # S1 Product Direct UI
│   │   │   ├── s2/page.tsx     # S2 Brand Campaign UI
│   │   │   ├── s3/page.tsx     # S3 Influencer Remix UI
│   │   │   ├── s4/page.tsx     # S4 Live Shoot UI
│   │   │   ├── s5/page.tsx     # S5 Brand VLOG UI
│   │   │   ├── fast/page.tsx   # Fast Mode UI
│   │   │   ├── result/page.tsx # Pipeline result view
│   │   │   ├── settings/page.tsx# Settings panel
│   │   │   ├── brand-packages/page.tsx
│   │   │   ├── influencers/page.tsx
│   │   │   ├── footage/page.tsx
│   │   │   └── admin/              # Admin Panel (Phase 1)
│   │   │       ├── layout.tsx      # AdminLayout + auth guard + sidebar
│   │   │       ├── page.tsx        # Redirect to /admin/dashboard
│   │   │       ├── login/page.tsx  # Admin login (email + password)
│   │   │       ├── dashboard/page.tsx  # System overview metrics
│   │   │       ├── tenants/page.tsx    # Tenant list + create modal
│   │   │       ├── tenants/[tenantId]/page.tsx  # Tenant detail + API keys
│   │   │       ├── logs/page.tsx       # Error log viewer + filters
│   │   │       └── health/page.tsx     # Service health status cards
│   │   ├── components/         # 40+ React components
│   │   │   ├── api.ts          # Backend HTTP client (localStorage + cookie fallback)
│   │   │   ├── types.ts        # Frontend type definitions
│   │   │   ├── Nav.tsx         # Navigation bar
│   │   │   ├── SceneSelector.tsx # Home page scene cards
│   │   │   ├── StepByStepView.tsx # Step-by-step pipeline view
│   │   │   ├── StageProgress.tsx  # Pipeline step progress
│   │   │   ├── VideoWorkflow.tsx  # S1 workflow orchestrator
│   │   │   ├── GatePanel.tsx   # Expert Studio gate UI
│   │   │   ├── CandidateSelector.tsx # Gate candidate comparison
│   │   │   ├── ExecutionBar.tsx # Pipeline execution controls
│   │   │   ├── DistributionView.tsx # Distribution plan view
│   │   │   ├── PublishPanel.tsx # Multi-platform publish
│   │   │   ├── QualityDashboard.tsx # Quality metrics dashboard
│   │   │   ├── PerformanceDashboard.tsx # Performance analytics
│   │   │   ├── AssetLibrary.tsx # Asset browser
│   │   │   ├── AssetUploader.tsx # Asset upload
│   │   │   ├── SettingsPanel.tsx # API key + backend URL config
│   │   │   ├── SplashScreen.tsx # Loading splash
│   │   │   ├── VlogSixView.tsx  # S5 six-view model selector
│   │   │   ├── VlogModelSelector.tsx # S5 model selection
│   │   │   ├── InsighReport.tsx # Analytics insights
│   │   │   ├── CompareView.tsx  # Comparison view
│   │   │   ├── OneShotResultView.tsx # Fast mode result
│   │   │   └── admin/
│   │   │       └── AdminSidebar.tsx  # Admin nav sidebar (Dashboard/Tenants/Logs/Health)
│   │   ├── stores/             # Zustand stores
│   │   ├── stores/             # Zustand stores
│   │   │   ├── useAppStore.ts  # Navigation, UI state, toast
│   │   │   ├── usePipelineStore.ts # Pipeline execution state
│   │   │   └── useExpertStore.ts   # Expert mode state
│   │   ├── hooks/
│   │   │   └── useExecutionBar.ts # Pipeline execution hook
│   │   ├── i18n/
│   │   │   ├── I18nProvider.tsx # React context provider
│   │   │   └── translations.ts # zh-CN / en translation map
│   │   └── types/
│   │       └── api.generated.ts # OpenAPI-generated types
│   ├── public/
│   │   ├── brand/              # Brand assets
│   │   └── portfolio/          # Portfolio images
│   ├── Dockerfile              # Multi-stage production build
│   ├── Dockerfile.nginx        # Nginx reverse proxy variant
│   ├── nginx.conf              # Nginx config
│   └── package.json            # Dependencies + scripts
├── rendering/                  # Remotion 4 video renderer (standalone)
│   └── src/
│       ├── Root.tsx            # Remotion composition root
│       ├── VideoComposition.tsx# Video composition component
│       └── render.ts           # CLI render script
├── tests/                      # Python backend tests (30+ files, 380+ tests)
├── migrations/                 # Alembic database migrations
│   ├── alembic.ini
│   └── alembic/versions/
├── configs/                    # Configuration files
├── strategy_source/            # Per-scenario strategy configs + quality thresholds
│   ├── general/
│   ├── product_direct/
│   ├── brand_campaign/
│   └── influencer_remix/
├── prompts/                    # Prompt templates
│   └── brand_story/            # Brand story prompts (script/visual/motion)
├── templates/                  # Template files
│   ├── motion_presets/
│   └── visual_style/
├── docs/                       # Project documentation
│   ├── architecture/           # Architecture decision records
│   ├── strategy/               # Strategic planning docs
│   ├── guide/                  # User guides
│   ├── superpowers/specs/      # Distribution layer specs
│   └── ...
├── deploy/                     # Deployment guides
│   ├── local-run.md
│   ├── tencent-cloudbase.md
│   └── lighthouse/
├── scripts/                    # Utility scripts
├── output/                     # Generated assets (gitignored)
├── docker-compose.yml          # Local dev: postgres + backend + frontend
├── Dockerfile.backend          # Production backend image (single source of truth)
├── Dockerfile                  # → Dockerfile.backend (symlink, no separate file)
├── render.yaml                 # Render Blueprint (alternative deploy, not canonical)
├── pyproject.toml              # Python project metadata + tool config
├── requirements.txt            # Python dependencies
├── Makefile                    # install, test, lint, coverage, clean, ci
└── .env.example                # Environment variable template
```

---

## Backend Architecture

### FastAPI Entrypoint (`src/api.py`)

The app is created at module level with 5 middleware layers:

1. **CORS** — configured from `CORS_ORIGINS` env var, defaults allow localhost:3000/3001 + tcloudbaseapp.com
2. **Rate Limiting** (P3-1) — 120 requests per 60s per IP, skips `/health`
3. **Request Logging** — logs method, path, status, duration for every request
4. **Response Wrapper** (P-TEST) — injects `_meta` {trace_id, duration_ms, version, timestamp} into all JSON responses, echoes `X-Client-Trace-Id` as `X-Trace-Id`
5. **API Key Auth** — `verify_api_key` dependency applied to most routers. `API_KEY` 是按用户分发的全权限凭证(每个开通的租户/用户拿一组独立 key),没有"低权限只读 key"的概念。生产 `.env.prod` 当前 `API_KEY=ai_video_demo_2026`,这就是真实 key 字符串、不是 demo 限制标记;以后随着租户开通会变更。模型矩阵(DeepSeek + POYO + SiliconFlow CosyVoice)由后端环境统一管理,不随 key 切换。

Routers are mounted on startup:

- `/health` — no auth
- `/pipeline/`* — API key required
- `/scenario/`* — API key required
- `/distribution/*` — API key required
- `/metrics/*` — API key required
- `/assets/*` — API key required
- `/media/*` — no auth (file serving)
- `/api/assets/*` — API key required (legacy)
- `/telemetry/*` — API key required (metrics / errors / prometheus)
- `/api/admin/*` — session-cookie auth (admin panel, independent of API key)

On startup, the app also restores active threads from disk and starts periodic cache eviction.

### Admin Panel (`/api/admin/*`)

Phase 1 operational control plane for the platform operator. Completely separate auth layer
from the creative API.

**Auth model:**

- Login: `POST /api/admin/auth/login` → bcrypt verify → session cookie (`admin_session`, HttpOnly, Secure, SameSite=Lax, 24h)
- Session validation: `verify_admin_session` dependency reads cookie → SHA-256 → query `admin_sessions` table
- Rate limit: 5 login attempts per minute per IP (in-memory, separate from general 120r/m)

**Modules:**


| Module    | Endpoints                                                                            | Description                                                  |
| --------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| Auth      | `/auth/login`, `/auth/logout`, `/auth/session`                                       | Login, logout, session check                                 |
| Dashboard | `/dashboard/summary`                                                                 | Tenant count, pipeline runs today, error rate, recent errors |
| Tenants   | `/tenants`, `/tenants/{id}`, `/tenants/{id}/keys`, `/tenants/{id}/keys/{kid}/revoke` | CRUD + API key lifecycle                                     |
| Logs      | `/logs`, `/logs/{id}`                                                                | Error log viewer with filters                                |
| Health    | `/health/status`, `/health/history`                                                  | Service connectivity checks                                  |


**Data model:** 4 new tables via Alembic migration `2d6b8e9c0f1a`:

- `admin_accounts` — email + bcrypt password_hash
- `admin_sessions` — token_hash (SHA-256 of 64 random bytes) + expires_at
- `tenants` — tenant_id (regex validated), display_name, status (active/disabled)
- `error_logs` — tenant_id, scenario, error_code, message, traceback

**Background tasks (registered in `api.py` startup):**

1. Health check loop — every 5 min, checks postgres/deepseek/poyo/siliconflow/remotion
2. Session cleanup — every 1h, `DELETE FROM admin_sessions WHERE expires_at < NOW()`
3. Log cleanup — every 1h, batch-delete `error_logs` older than `ADMIN_LOG_RETENTION_DAYS` (default 30)

**Initial setup:**

```bash
python scripts/create_admin.py <email> <password>
```

### LangGraph Pipeline (`src/graph/`)

**Pipeline flow:**

```
strategy → strategy_audit → [Human Review #1] → script → script_audit → [Human Review #2]
    → compliance → storyboard → asset_sourcing → media_generation (if gaps) → editing
    → editing_audit → [Human Review #3] → audio → caption → thumbnail
    → thumbnail_audit → [Human Review #4] → distribution → analytics → END
```

**Key design decisions:**

- **Error handling (P0-2):** Every node is wrapped with `_wrap_node_with_error_handling`. On exception, sets `pipeline_degraded = True`. All routing functions check `_degraded_guard` FIRST and terminate to `__end__` — no more cascading failures.
- **Human review routing (D10):** Uses `contextvars.ContextVar` for per-request routing overrides. This exists because LangGraph checkpoint recovery does not preserve `update_state` across `astream` boundaries during `interrupt_after` resume. The override is set by `submit_review` in the router before resuming.
- **Self-audit auto-decisions:** Score > 0.90 → auto-approve (skip human review). Score < 0.60 → auto-reject (terminate pipeline). Thresholds are per-scenario configurable via `strategy_source/<scenario>/quality_thresholds.json`.
- **Retry guard:** Max 3 retries per checkpoint. After exhaustion, `CHANGES_REQUESTED` is treated as `APPROVED`.
- **Checkpoint persistence:** PostgresSaver for production (requires psycopg connection). MemorySaver for dev/test. Fails fast if `db_url` is set but PG is unreachable — no silent fallback.

### Quality Assessment (`src/quality/`)

10 optional ML-powered quality modules, all using lazy import to avoid heavy dependencies.

**Three layers:**

1. **Skill Self-Verify (technical)** — `seedance_video_generate` (frame variance), `remotion_assemble` (av sync), `media_quality_audit` (resolution/bitrate/fps)
2. **Audit Agent (rule-based)** — `auditor.py` expanded from 7 to 9 criteria: Hook Strength (duration+text), Segment Completeness, Duration Fit, Voiceover Clarity, Brand Voice, CTA Clarity, Compliance, Information Density, Emotional Arc
3. **ML Assessment (optional)** — CLIP alignment, BRISQUE/NIQE, scene analysis, face consistency, safe zone, viral prediction, CTR estimation

**Lazy import policy:** All `src/quality/` modules import heavy libraries (transformers, torch, opencv, mediapipe, deepface, pyiqa, scenedetect) inside try/except at call time. If unavailable, the check returns `None` or a skipped result with a warning log. This keeps the Docker image small while allowing production operators to opt-in to advanced checks.

**Thresholds:** All quality thresholds are module-level constants (e.g. `CLIP_ALIGN_STRONG = 0.28`, `BLUR_THRESHOLD = 100.0`). The `dynamic_thresholds.py` module can suggest adjustments based on A/B test data from `ab_tracker.py`.

### API Key Isolation

Per-request API keys are supported via the `api_keys` field in pipeline start requests. Keys are stored using `contextvars` (not `os.environ`) so concurrent requests don't contaminate each other. The LLM client reads from request context first, then falls back to env vars.

### Chinese→English Translation

S1 and S3 pipelines auto-translate Chinese product inputs to English via `translate_catalog_to_english()`. Original Chinese values are preserved in `_original_zh` within the product catalog dict. Pipeline output language is locked to `["en"]`.

---

## Scenario Pipelines

### Common API Endpoints (`/scenario/{scenario}/...`)


| Method | Path                                                          | Description                             |
| ------ | ------------------------------------------------------------- | --------------------------------------- |
| POST   | `/scenario/s1`                                                | Run S1 auto (full pipeline)             |
| POST   | `/scenario/s2`                                                | Run S2 brand campaign                   |
| POST   | `/scenario/s3`                                                | Run S3 influencer remix                 |
| POST   | `/scenario/s4`                                                | Run S4 live shoot                       |
| POST   | `/scenario/s5`                                                | Run S5 brand VLOG                       |
| POST   | `/fast/generate`                                              | Fast Mode: direct text→video            |
| GET    | `/scenario/{s}/state/{label}`                                 | Get pipeline state                      |
| PUT    | `/scenario/{s}/state/{label}`                                 | Update pipeline state (user edits)      |
| GET    | `/scenario/{s}/state/{label}/steps`                           | List steps with status                  |
| POST   | `/scenario/{s}/step/{step_name}`                              | Execute single step                     |
| PUT    | `/scenario/{s}/state/{label}`                                 | Edit step output                        |
| POST   | `/scenario/{s}/regenerate/{label}/{step}`                     | Regenerate step + invalidate downstream |
| GET    | `/scenario/{s}/gate/{label}/{gate_id}`                        | Get gate state                          |
| POST   | `/scenario/{s}/gate/{label}/{gate_id}/generate`               | Generate 3 gate candidates              |
| POST   | `/scenario/{s}/gate/{label}/{gate_id}/approve`                | Approve gate (auto-resumes pipeline)    |
| POST   | `/scenario/{s}/gate/{label}/{gate_id}/regenerate/{candidate}` | Regenerate single candidate             |


### S1: Product Direct (商品直拍)

The most mature scenario. Supports two modes:

- **auto:** Full pipeline execution with gate checkpoints
- **step_by_step:** Manual step execution with gate approval at each checkpoint

Uses `StepRunner` + `PipelineStateManager` for progress tracking. Gate system generates 3 candidates (standard/creative/conservative) per checkpoint, scored by `CandidateScorer`.

Gate approval triggers background task resume to avoid HTTP 504 on long-running steps (keyframe generation + video synthesis can take 5-30 minutes).

### S2-S5: Other Scenarios

**Phase 2 (2026-05-07) 已全部接入 StepRunner:**

- S3/S4/S5 实现 `run_step(step_name, state)` 接口，`run()` 内部委托给 StepRunner 以保持向后兼容
- `step_runner.py:_SCENARIO_CONFIGS` 集中定义各场景的 step_order：
  - s1: 12 steps (strategy → audit)
  - s3: 12 steps (video_analysis → audit)
  - s4: 3 steps (scripts → video_prompts → thumbnails)
  - s5: 6 steps (vlog_strategy → audit)
- S2 是 S1 的 wrapper (`brand_mode=True`)，无需单独迁移

Gate 系统目前仅在 S1 启用，S3-S5 的 gate 接入是后续迭代方向。

---

## LLM Provider Chain

```
Primary (text):  DeepSeek V4-Pro    https://api.deepseek.com
Image:           poyo.ai GPT-4o     https://api.poyo.ai    (model: gpt-image-2)
Video:           poyo.ai Happy Horse https://api.poyo.ai   (model: happy-horse)
                 or Seedance 2.0    https://api.seedance.ai
TTS:             SiliconFlow CosyVoice https://api.siliconflow.cn/v1
                                          (model: FunAudioLLM/CosyVoice2-0.5B)
Legacy/fallback: OpenAI, Anthropic, Kimi, ElevenLabs
```

Configured via `.env`:

- `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL`
- `POYO_API_KEY`, `POYO_API_BASE_URL`, `POYO_IMAGE_MODEL`, `POYO_VIDEO_MODEL`
- `SILICONFLOW_API_KEY`, `COSYVOICE_MODEL`, `COSYVOICE_VOICE`
- `DEFAULT_LLM_PROVIDER` — canonical value is `deepseek`. Live in `deploy/lighthouse/.env.prod`,
and `src/services/fast_mode.py:121` special-cases `"deepseek"` to switch the V4-Pro reasoning
model down to `deepseek-chat` (V3) for sub-5s latency on simple text-to-video.
**Known divergence (待统一):** `src/config.py:105` fallback is `"anthropic"`, `render.yaml`
sets `"kimi"`, `deploy/tencent-cloudbase.md` documents `"kimi"`. When updating any of these,
align the others or update this section.

---

## Database

**Production:** PostgreSQL 16 via asyncpg connection pool (min 1, max 10 connections).

**Development fallback:** SQLite at `output/ai_video.db`.

**Tables:**

- `threads` — pipeline run threads (id, thread_id, state JSON, current_step)
- `pipeline_states` — scenario pipeline states (label, config, steps JSON, mode)
- `brand_packages` — brand guidelines + assets
- `influencers` — influencer profiles
- `publish_logs` — multi-platform publish history
- `api_keys` — per-tenant API key management (P2-8); tenant_id, key_hash(SHA-256),
permissions JSONB, expires_at, revoked_at. Added via Alembic migration `1ffe98505ace`.
`verify_api_key` queries this table first, falls back to env `API_KEY`.
- `video_metrics` — performance metrics; Alembic migration `1efc41794d64` (2026-05-01) adds the
PG table. `src/storage/migrations/001_init.sql` now includes it inline so a fresh Docker
Compose stack gets a complete schema without requiring a separate `alembic upgrade head` step.
Repository (`metrics_repository.py`) is PG-first with SQLite fallback — both paths are
exercised in tests.
- `admin_accounts` — admin operator credentials (email, bcrypt password_hash); no registration UI in Phase 1
- `admin_sessions` — session token hashes (SHA-256 of 64 random bytes), 24h expiry, hourly cleanup
- `tenants` — tenant registry (tenant_id regex validated, display_name, contact_email, status active/disabled)
- `error_logs` — persistent error storage from `ErrorCollector`; 30-day retention (configurable via `ADMIN_LOG_RETENTION_DAYS`)

Admin Panel tables added via Alembic migration `2d6b8e9c0f1a` (2026-05-07).

**Migrations:** Alembic in `migrations/`. Docker Compose auto-loads SQL from `src/storage/migrations/`.

**Health check:** `check_pg_health()` verifies connection + required tables exist. `is_pg_available()` used throughout app to skip PG calls when unhealthy.

---

## Frontend Architecture

### Tech Stack

- **Framework:** Next.js 16 (App Router)
- **UI:** React 19, Tailwind CSS 3
- **State:** Zustand (3 stores)
- **Icons:** Lucide React, Phosphor Icons
- **Testing:** Vitest + Playwright
- **Build:** Multi-stage Docker (node:22-alpine), standalone output mode

### Page Routes


| Route                 | Component                           | Purpose                                             |
| --------------------- | ----------------------------------- | --------------------------------------------------- |
| `/`                   | `page.tsx`                          | Scene selection home (5 scenario cards + fast mode) |
| `/s1`                 | `s1/page.tsx`                       | Product Direct workflow                             |
| `/s2`                 | `s2/page.tsx`                       | Brand Campaign workflow                             |
| `/s3`                 | `s3/page.tsx`                       | Influencer Remix workflow                           |
| `/s4`                 | `s4/page.tsx`                       | Live Shoot workflow                                 |
| `/s5`                 | `s5/page.tsx`                       | Brand VLOG workflow                                 |
| `/fast`               | `fast/page.tsx`                     | Fast Mode direct generation                         |
| `/result`             | `result/page.tsx`                   | Pipeline result + download                          |
| `/settings`           | `settings/page.tsx`                 | API key + backend URL configuration                 |
| `/brand-packages`     | `brand-packages/page.tsx`           | Brand asset management                              |
| `/influencers`        | `influencers/page.tsx`              | Influencer management                               |
| `/footage`            | `footage/page.tsx`                  | Portfolio/footage gallery                           |
| `/admin`              | `admin/page.tsx`                    | Redirect to `/admin/dashboard`                      |
| `/admin/login`        | `admin/login/page.tsx`              | Admin login (email + password)                      |
| `/admin/dashboard`    | `admin/dashboard/page.tsx`          | System overview (tenants, pipelines, errors)        |
| `/admin/tenants`      | `admin/tenants/page.tsx`            | Tenant list + create modal                          |
| `/admin/tenants/[id]` | `admin/tenants/[tenantId]/page.tsx` | Tenant detail + API key management                  |
| `/admin/logs`         | `admin/logs/page.tsx`               | Error log viewer with filters                       |
| `/admin/health`       | `admin/health/page.tsx`             | Service health status cards                         |


### State Management (Zustand)

**useAppStore:** Navigation stage (home/recommend/generate/result), active scene, mode (expert/smart), pipeline mode (auto/step_by_step), video duration, loading/toast/disconnected state.

**usePipelineStore:** Pipeline execution state, thread tracking, review status, step progress, current label, gate state.

**useExpertStore:** Expert mode settings, advanced configuration.

### i18n

Bilingual (zh-CN / en) via `I18nProvider` React context. Translations in `web/src/i18n/translations.ts`. All user-facing strings use translation keys.

### API Client (`web/src/components/api.ts`)

Backend URL and API key stored via `localStorage` with cookie fallback (privacy/incognito mode). Build-time env vars (`NEXT_PUBLIC_API_BASE_URL`) provide defaults.

**Admin API client** (`adminFetch` / `adminFetchJson`):

- Session-cookie auth (no `X-API-Key` header)
- `credentials: 'include'` for HttpOnly cookie
- On 401 → auto-redirect to `/admin/login`
- Used exclusively by `/admin/`* pages

`isDemoMode()`(`web/src/components/api.ts:97`)按 hostname 判定(`github.io` / `.vercel.app`),
是给"静态前端无后端"演示页用的纯前端降级标志,与后端 `API_KEY` 字符串无关 —— 后端不再
对任何 key 做权限分级。

---

## Rendering (Remotion)

Standalone Node.js package at `rendering/`. Takes pipeline state JSON as input and composes `.mp4` video output.

**Key files:**

- `src/Root.tsx` — Remotion composition registration
- `src/VideoComposition.tsx` — Actual video layout/animation
- `src/render.ts` — CLI render entry

**Usage:**

```bash
cd rendering
npm install
npx tsx src/render.ts --input ../output/renders/<run>_state.json --output ../output/video.mp4
```

---

## Development Workflow

### Local Dev (Docker Compose)

```bash
# Start all services
docker compose up -d

# Backend: http://localhost:8001
# Frontend: http://localhost:3000
# PostgreSQL: localhost:5432
```

### Local Dev (Manual)

```bash
# Backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api:app --reload --port 8001

# Frontend (separate terminal)
cd web
npm install
npm run dev

# Tests
make test          # Backend tests
make lint          # Ruff check
make ci            # Lint + test
cd web && npm test # Frontend tests
```

### Production Deployment

The project ships three deploy targets, in priority order:

1. **Tencent Lighthouse (canonical)** — current production at `https://101.34.52.232`.
  `deploy/lighthouse/` contains `docker-compose.prod.yml` (backend + frontend + nginx +
   rendering), `nginx.conf` (with 1500s `proxy_read_timeout` for long-running pipelines),
   and `.env.prod` (live secrets — gitignored). Deploy via `rsync -e "ssh -i ai_video.pem"`
   to `ubuntu@101.34.52.232:/opt/ai-video/` then `docker compose up -d --force-recreate`.
   Note: rsync to bind-mounted nginx.conf needs `--inplace --no-whole-file`. **Do not use**
   `docker restart ai_video_nginx` for volume mount changes (e.g. adding `proxy_params.conf`);
   `restart` reuses the existing container and ignores new volume declarations in
   `docker-compose.prod.yml`. Always use `--force-recreate` for nginx when volumes change.
   Volume 命名:docker compose project = `lighthouse`(因为 compose 文件在
   `deploy/lighthouse/`),所以 backend output volume 是 `lighthouse_backend_output`,
   不是 `ai-video_backend_output`(后者是历史残留 volume,backend 不会读到)。任何
   `docker run -v <volume>:/...` 操作都要用 `lighthouse_backend_output`。
   2026-05-05 部署事故防御:`Dockerfile.backend` 配阿里云 PyPI mirror、`deploy.sh`
   Phase 0 hash 检测（`sha256sum requirements.txt` 本地 hash vs image 内记录 hash）、
   backend `restart: on-failure:5` 限制无限重启。完整时间线 + 紧急恢复三步法见
   `docs/workflows/incident-2026-05-05-postgres-saver-deploy-stable.md`。
   **2026-05-07 deploy.sh 更新**: 构建前清理 `.next/standalone/` `.next/static/`
   `.next/server/` 防止 Turbopack 旧 chunk 残留；构建后验证 `standalone/server.js`
   和 `static/chunks/` 存在；nginx 用 `--force-recreate` 确保 volume 挂载变更生效。
2. **Tencent CloudBase (alternative, China)** — see `deploy/tencent-cloudbase.md` and
  `deploy/CLOUDBASE_STEP_BY_STEP.md`. Container-typed cloud hosting, pay-as-you-go.
   Documented but not the live target.
3. **Render Blueprint (alternative, overseas)** — see `render.yaml`. Auto-deploy from
  GitHub, free tier available. Lands at `https://lute-ai-video-backend.onrender.com`.

### Environment Variables

Copy `.env.example` to `.env` and configure:

- **API keys:** `DEEPSEEK_API_KEY`, `POYO_API_KEY`, `SILICONFLOW_API_KEY` (required for real generation)
- **Database:** `DATABASE_URL=postgresql://...` (optional, falls back to SQLite)
- **Auth:** `API_KEY` (generated automatically if not set)
- **CORS:** `CORS_ORIGINS=...` (comma-separated)
- **Output:** `VIDEO_OUTPUT_DIR=./output`
- **Webhook:** `WEBHOOK_URLS=...` (comma-separated URLs)

Without API keys, the pipeline runs in **mock mode** — produces natural-language placeholder content without external API calls.

---

## Testing

**Backend:** 30+ test files in `tests/` (run `find tests -name 'test_*.py' | wc -l` for the
current count — avoid hardcoding the number here, it goes stale fast). Pytest with asyncio
auto mode. Coverage targets `src/`.

Key test areas:

- Pipeline e2e (`test_e2e_pipeline.py`, `test_s1_e2e.py`, `test_s3_e2e.py`)
- Routing logic (`test_routing.py`)
- Graph compilation (`test_graph.py`)
- API endpoints (`test_api.py`)
- Media clients (`test_media_clients.py`)
- State management (`test_state.py`)
- Quality gates (`test_quality_gate.py`)
- Compliance (`test_compliance.py`)
- Individual agents (strategy, script, auditor, caption, thumbnail)
- Database (`test_postgres.py`)
- Webhook (`test_webhook_manager.py`)
- Asset management (`test_asset_models.py`, `test_asset_library.py`)

**Frontend:** Vitest with jsdom. Component tests in `web/src/components/*.test.tsx`.

**CI:** GitHub Actions on push/PR to main — ruff lint + pyright type check + pytest (Python 3.11 + 3.12) + coverage.

---

## Portfolio / Asset Library

闭环测试通过真实外部 API 跑出的 mp4 / mp3 / png / wav / keyframe 都是付费产物,作为
作品集 + 数据资产保留。

### `/api/portfolio/` 端点 (`src/routers/portfolio.py`)

- **扫描范围**: `OUTPUT_DIR` 下 12 个固定子目录,`rglob` 全量递归扫描
- **过滤**: 扩展名白名单 + 视频/图片 > 1 MiB(过滤 stub) + 音频任意正大小
- **缓存**: 30s 进程内存缓存(`_CACHE`),单 key `"all"`
- **排序**: `?sort=quality` — renders(0) > fast_mode(1) > 其他(99),同类按 `produced_at` desc
- **截断**: `?limit=50` — 前端 footage 页面只展示 TOP50,`by_category` 仍聚合全量
- **Poster**: `thumbnail_path` 字段指向预生成 jpg(`output/thumbnails/portfolio_posters/`)

### nginx 静态直送 (`deploy/lighthouse/nginx.conf:54-70`)

`/api/media/` 走 `try_files` 先读本地文件,未命中再 fallback backend:

```nginx
location /api/media/ {
    alias /var/www/media/;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri @backend_media;
}
```

- `backend_output` volume 以 `:ro` 挂载到 nginx 容器 `/var/www/media/`
- 生产实测: thumbnail 2.6KB → 4.8ms, video 12.6MB → 32ms(均走 nginx,不穿透 FastAPI)

### Thumbnail 生成 (`scripts/generate_portfolio_thumbnails.py`)

- ffmpeg 抽帧: `-ss 00:00:02 -vf scale=480:-2 -q:v 3`
- 输出: `output/thumbnails/portfolio_posters/<category>__<filename_stem>.jpg`
- 增量: 已存在且 mtime >= source mtime 则跳过
- 本地生成后 `rsync` → 生产 `output_uploaded/` → `docker cp` 进 `lighthouse_backend_output`

### Footage 页面 (`web/src/app/footage/page.tsx`)

- **成品(finished)**: `GalleryGrid` 展示 renders 类目视频,点击弹出 `MediaPreviewModal`
- **素材(materials)**: grid 展示 50 个 item,支持 全部/视频/图片/音频 分类过滤
- **预览**: 统一弹窗 overlay — 视频 autoPlay + controls,图片居中,音频 controls + 文件名
- 不再 `window.open(..., "_blank")`,不再有右侧 detail panel

### 索引与 sync(遗留)

**索引** (`assets/portfolio/index.json`,gitignored):

- `scripts/portfolio_index.py` 扫 12 子目录输出 JSON(供离线/CI 使用)
- `/api/portfolio/` 端点**不读此 JSON**,运行时直接扫文件系统

**双向 sync 脚本**:

- `scripts/sync_output_to_lighthouse.sh`:本地 output/ → 生产 volume
- `scripts/sync_lighthouse_to_output.sh`:生产 volume → 本地 output/

---

## Key Patterns and Conventions

### Error Handling

- All LangGraph nodes wrapped in try/catch that sets `pipeline_degraded = True`
- Routing functions check degraded guard FIRST before any other logic
- Structured errors collected via `error_collector` (FIFO, last 100)
- API errors return generic messages in production with internal trace IDs

### Logging

- structlog throughout backend with ISO timestamps
- Sensitive values (API keys, tokens) automatically redacted by `_SanitizeProcessor`
- Request logging middleware captures method/path/status/duration

### Type Checking

- `pyproject.toml` 配置 `[tool.pyright]`，`make typecheck` 可运行（`pyright src tests`）
- 已启用规则：`reportMissingTypeArgument` + `reportPossiblyUnboundVariable` → 0 错误
- 未启用规则：`reportUnknownMemberType` / `reportUnknownVariableType` — 在 `dict[str, Any]`
为主的代码库中噪音远大于价值，暂不启用（详见 `docs/workflows/pyright-strict-technical-debt-plan-20260507-stable.md`）

### API Design

- All JSON responses wrapped with `_meta` (trace_id, duration_ms, version, timestamp)
- API key required for all mutating endpoints
- Per-tenant `API_KEY`:每个开通用户拿一组独立全权限 token,后端不做"低权限只读"分级
- Rate limiting: **nginx** `limit_req_zone` 120r/m per IP (P2-11)。**location-only**：
限流 `limit_req` 只写在 7 个 API location 内（`/api/`、`/api/scenario/`、`/api/fast/`、
`/api/pipeline/`、`/api/assets/`、`/api/files`、`/api/upload`），各自 burst=20。
`/health` burst=100、`/api/media/` burst=1000 高 burst 兜住高频健康检查与画廊批量加载。
前端 `/` 和 `/_next/` **不限流**（Next.js 冷启动会 30+ 并发拉取 chunks/RSC/favicon）。
FastAPI middleware 内存限流降级为 fallback（直接访问 backend 不走 nginx 时生效）。
⚠ 历史教训 1：nginx 不支持 `limit_req off`，旧配置中的 `off` 参数会触发 `[emerg]`
导致 nginx 无法启动。
⚠ 历史教训 2：`server` 块顶层 `limit_req` 会被未显式覆盖的 `location` 继承，
前端会被误伤；新增 location 必须明确判断是否需要限流，不能依赖顶层兜底（已废除）。
- **nginx proxy header 统一**: `deploy/lighthouse/proxy_params.conf` 提取 4 个公共 proxy
header（Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto），13 个 location 共用。
新增 location 时优先复用该 include，避免复制粘贴。`docker-compose.prod.yml` 需挂载
该文件到 `/etc/nginx/proxy_params.conf`。
- Per-request API key injection via contextvars for multi-tenant safety
- Tenant ID: `verify_api_key` 解析 API key 后通过 `set_tenant_id()` 写入 contextvar，
下游 cost tracking / audit log 可读取（P2-8）

### Pipeline State

- Single `VideoPipelineState` TypedDict with 30+ fields
- Nodes add fields incrementally (TypedDict with `total=False`)
- State serialized as JSON for checkpoint persistence
- Export endpoint strips internal fields (retry_counts, self_verifications, etc.)

### Frontend Conventions

- **Theme:** Warm Light Professional (`data-theme="light"`),2026-05-06 从暗黑剧场翻转。
核心色: `#FDF8F6` 暖白底 + `#D75C70` Fortune Red accent + `#FCF5F2` 暖白阴影。
- Film grain + vignette overlay on all pages
- Chinese-first i18n with English toggle
- localStorage + cookie dual storage for settings
- Background polling for pipeline progress (StepByStepView, StageProgress)
- **Store 职责分离**: `usePipelineStore` 管理 pipeline/loading 状态（threadId、
step progress、currentStepIdx、showSteps）；`useExpertStore` 只保留 expert 模式
特有状态（currentGate、showStageProgress、compareVersions、showCompare）。
避免 God Component 过度订阅导致不必要的重渲染。
- ESLint lock on demo key: `web/eslint.config.mjs` `no-restricted-syntax` 规则禁止
Literal `'ai_video_demo_2026'` 出现在 fallback / placeholder / i18n 之外的位置;
`no-restricted-imports` 禁止 import `API_BASE` 常量(必须用 `getApiBase()` /
`apiFetch()`)。新组件直接调 `apiFetch()`,不要 `fetch(\`${API_BASE}/..., ...)`。

---

## Known Gaps and TODOs

最近一次盘点:2026-05-08(第三轮质量提升 18 项全部完成，质量体系从 "事后检查" 升级为 "全过程可控")。

### 1. 已知功能缺陷(已修复)

> **2026-05-07 修复:**
>
> - **ChunkLoadError /footage 页面崩溃** — Turbopack content-hash 变化导致旧 chunk 引用失效。
> nginx `location /` 添加 `Cache-Control: no-store` 禁止 HTML 缓存，`location /_next/`
> 静态资源长期缓存。`deploy.sh` 构建前清理旧产物避免残留。
> - **循环导入导致 backend 启动失败** — `src/graph/nodes.py` 顶层导入 `_register_background_task`
> 形成 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py` 循环。改为延迟导入 helper。
> - **nginx `limit_req off` 语法错误** — 原配置使用无效语法，`location /health` 和
> `/api/media/` 改为高 burst 值实现等效豁免。
> - **nginx 顶层 `limit_req` 误伤前端导致首页 429** — `server` 块顶层 `limit_req zone=api_limit burst=20 nodelay` 被前端 `/` 和 `/_next/` 默认继承，Next.js 冷启动
> 30+ 并发请求秒爆 burst=20。修复：删除顶层声明，改为 7 个 API location 内部
> 显式 `limit_req`。生产 rsync `--inplace --no-whole-file` + `nginx -s reload` 落地。

> **2026-05-06 修复:**
>
> - **Portfolio 加载慢 + 视频无法预览** — 后端 `?limit=50&sort=quality` + nginx `try_files`
> 静态直送 + 144 个 poster thumbnail + 前端 `<img poster>` 替代 337 个 `<video preload="metadata">`。
> 实测 thumbnail 4.8ms / video 32ms(02849c9)。
> - **Footage 页面交互不一致** — 成品/素材统一 `MediaPreviewModal` 弹窗预览,不再
> `window.open` 或右侧 detail panel;Materials 新增 全部/视频/图片/音频 分类过滤(c4dd6ed)。
> - **UI 主题翻转** — `globals.css` + `tailwind.config.js` + 40+ 组件从暗黑剧场翻转为
> Warm Light Professional Theme(d3e8bd3)。

> **2026-05-08 4-Option Plan 修复/扩展:**
>
> - **POYO sanitizer Phase 2** — 新增 11 条替换规则(英 7 + 中 4)，覆盖 baby bottle / nipple /
> areola / formula milk / baby food / postpartum / 奶瓶 / 奶嘴 / 辅食 / 产后。
> 新增结构化 CM 拒绝日志，生产可通过 `poyo_cm_rejection` 事件抓回原始 prompt 持续补充规则。
> - **S3-S5 Gate 配置** — `gate_manager.py` per-scenario 重构完成，`SCENARIO_GATE_DEFINITIONS`
> 定义 s1-s5 各场景 gate 集合与 after_step 映射；`candidate_scorer.py` 新增 `remix_script` /
> `character_identity` / `vlog_strategy` 评分维度。`step_runner.py` gate 触发按 scenario 读取。
> `_build_skill_params` 补充 `remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py`
> 52 个测试验证配置正确性。step-by-step gate 暂停对 S3/S4/S5 均已 mock 验证通过。
> - **Long pipeline UX** — 统一异步框架已落地，S2/S3/S5 的长链路不再受 HTTP 超时截断。

> **2026-05-08 修复:**
>
> - **Admin Panel 登录不可用** — `bcrypt` 未安装导致 admin router 启动跳过；nginx `/api/`
> catch-all strip `/api` 前缀导致 admin 端点 404；`admin_accounts` 表未创建（Alembic
> 迁移未执行）。修复：`pip install bcrypt` + `docker commit`；新增 `/api/admin/` nginx
> location 保留前缀；手动 SQL 建表并插入初始 admin 账号。登录验证通过。
> - **page.tsx 构建失败** — `useExpertStore` 解构缺少 `setShowStageProgress` /
> `currentStepIdx` / `setCurrentStepIdx`。补充解构后 `npm run build` 通过。
> - **nginx `/telemetry/` 404** — 缺少 `/telemetry/` location，请求被路由到前端。
> 新增 location 转发到 backend，`/telemetry/prometheus` 返回 Prometheus 格式指标。

仍待处理:

- **POYO sanitizer 覆盖率持续提升(F3, P2)** Phase 2 新增 11 条规则后覆盖率大幅提升，
但仍需在生产日志中持续抓回 `poyo_cm_rejection` 事件中的原始 prompt 文本补充新规则。
- **yt-dlp / whisper 未装进 backend 容器(F4, P3)** D5 KOL 视频分析 skill 走 mock 路径,
脚本生成不依赖真实 transcribe,管线下游不受影响。要让 video-analysis 真实工作需
`pip install yt-dlp openai-whisper` 进 `Dockerfile.backend`(whisper 拉 PyTorch ~2GB,
实施前先确认是否值)。

### 2. 配置/历史遗留(已知)

- **api_assets.py compat shim:** `/api/assets/`* uses in-memory dicts (`_brand_packages`,
`_influencers`). Frontend OpenAPI types still reference these paths, so don't remove the
router; do migrate any new asset features to `src/routers/assets.py` instead.
- **S2-S5 step-by-step / gate system:** S3/S4/S5 已完成 StepRunner 迁移 (P2)、gate
配置、skill params 扩展与非 S1 场景 mock 验证。`_build_skill_params` 新增
`remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py` 52 测试验证
配置正确性。仍待: 前端 `CandidateSelector` 在非 S1 场景下的状态映射未实测；
S3-S5 gate 真实 API key 端到端（类似 `test_gate_full_flow_e2e.py` 对 S1 gate_1 的验证）。
- **Long pipeline UX:** ✅ 已解决(2026-05-08) — 统一异步执行框架落地，所有场景走
`POST /submit` → 轮询 `/status`，HTTP 超时不再截断长链路。nginx 1500s 退居兜底。
- **Redis/Celery declared but unused:** Still in `requirements.txt` but no live consumer.
- **LangGraph 代理层 (P4-4):** `/pipeline/`* 端点已代理到 StepRunner，但代理层 state 转换是
best-effort，某些 legacy 字段可能缺失。保留原始 LangGraph 代码作为兼容层，代理函数可迭代补全。
- **pyright strict 剩余规则:** `reportUnknownMemberType` / `reportUnknownVariableType` 未启用。
在 `dict[str, Any]` 为主的代码库中，这两项规则噪音远大于价值。如需进一步收紧类型，需先
将 `dict[str, Any]` 替换为数百个具体类型（ProductCatalog、PipelineConfig 等），ROI 待评估。
- **deploy.sh Phase 0 逻辑缺陷:** ✅ 已修复。`mtime` 比较 → `sha256sum` hash 比较，
Dockerfile 构建时记录 `sha256sum requirements.txt > /app/.requirements_sha256`，
deploy.sh 直接对比本地 hash 与镜像内 hash。不受 `IMG_BUILT_TS=0` 影响，首次部署也正确提示。
- **alembic 不在 requirements.txt 中:** ✅ 已修复。`alembic>=1.13` 已加入 `requirements.txt`，
backend image 已 rebuild 固化，容器内可直接执行 `alembic upgrade head`。
- **Quality 模块 lazy import 设计:** `src/quality/` 下 10 个模块全部采用 lazy import。
transformers/torch/opencv/mediapipe/deepface/pyiqa/scenedetect 均不在 `requirements.txt`
中强制要求。运行时会检测可用性，不可用则 graceful skip 并记录 warning。生产如需启用
CLIP/BRISQUE/场景分析/人脸一致性，需手动安装对应依赖并确认 Docker image 体积可接受
(CLIP+torch CPU ~600MB, DeepFace ~200MB)。

### 3. 未做端到端验证的前后端交互路径

Phase D/E 通过的是 5 场景"主路径" + portfolio 优化。以下路径在生产尚未端到端实测:

- **A. Human Review 4 个 checkpoint 的人工分支** Pipeline `strategy_audit` /
`script_audit` / `editing_audit` / `thumbnail_audit` 的 score 落在 0.60–0.90 区间会触发
HITL,前端 `GatePanel` + 后端 `POST /scenario/{s}/gate/{label}/{gate_id}/approve` 的
"APPROVED / CHANGES_REQUESTED / REJECTED" 三个分支以及 D10 contextvars 路由覆写,
Phase D 没触发到。需要构造低分输入或下调阈值实测。
- **B. S1 step-by-step + Gate 候选生成全链路** ✅ 后端单元测试已覆盖（`test_s1_gate_full_flow.py`
41 测试：approve 成功路径包括 candidate 选择 → edited_output 写入 → current_step 推进；
step_runner gate 暂停/恢复 4 个测试验证 pre-step + post-step 检查点）。
真实 API key e2e 在 `test_gate_full_flow_e2e.py` 中覆盖 gate_1 generate + score + approve
  - regenerate。生产端到端未实测（Phase D D2 走的是 auto 模式）。
- **C. Distribution / Publish** `POST /distribution/publish` + TikTok / Shopify connector
实际发布。Phase D 没跑过,只有单元测试。需要真实 platform credentials 才能走通。
- **D. Metrics 全链** `GET /metrics/`* 视频性能查询、`src/tasks/metrics_poller.py` 周期任务
在生产是否被调度、Alembic 的 `video_metrics` 表是否真的 `alembic upgrade head` 过、
PG 与 SQLite 双路是否在生产生效。前端 `PerformanceDashboard` 显示真数据未验证。
- **E. Assets 上传链路** ✅ 后端单元测试已覆盖（`test_upload_e2e.py` 10 测试验证
multipart → 落盘 → `/api/files` 列出 → `/api/media/` 访问完整链路；含认证/扩展名/大小限制
负向测试）。前端 `brand-packages/page.tsx` 已集成 `AssetUploader` 上传面板（Header 右侧
上传按钮 + 可折叠上传区域，上传完成后自动刷新列表）。仍待: 生产未走通"上传 → 管线
引用 → 出现在最终视频"的闭环（uploaded 文件尚未被 keyframe/seedance 步骤实际引用验证）。
`/influencers` 列表 CRUD 在生产是否真存了 PG 未验证。
- **F. Webhook 事件分发** `src/tools/webhook_manager.py` 的 `audit.completed` /
`pipeline.completed` 事件,Phase D 期间生产 `WEBHOOK_URLS` 为空,从未触发。需要配上
接收端(可临时用 webhook.site)再跑任一场景验证。
- **G. 错误降级路径** `pipeline_degraded = True` 在 5 场景中未被触发(都走绿)。Mock POYO /
DeepSeek 故障下的"降级 + 终止 + 错误上报"链路、`error_collector` FIFO、`/telemetry`
端点的可见性,均未做负向测试。
- **H. 多用户并发 + API Key 隔离** `contextvars` 隔离机制在单机单请求 OK。同时跑 2+ 场景
使用不同 API key 时是否真的不串(尤其 LLM client + POYO client + Seedance client 三处
contextvars 读取),没压测过。
- **I. i18n 切换** `zh-CN` / `en` 在生产页面切换后,所有按钮 / 表单 / 报错 / SettingsPanel /
GatePanel / DistributionView 文案是否都从翻译表读取(无硬编码中文/英文残留),未走查。
- **J. 备用部署目标** `render.yaml`(海外)与 `deploy/tencent-cloudbase.md`(国内 CloudBase)
这两条 alternative 路径的现状,自从 Lighthouse 成为 canonical 后没人再验过。`render.yaml`
里 `DEFAULT_LLM_PROVIDER=kimi` 是否还能正常生成内容,未知。
- **K. Quality 模块真实 ML 依赖验证** `src/quality/` 下 CLIP、BRISQUE、PySceneDetect、
MediaPipe/DeepFace 均只在代码层面验证通过（lazy import + fallback 路径）。真实安装
transformers+torch / opencv-python / mediapipe 后的端到端验证尚未执行。`nr_quality.py`
的 OpenCV fallback 在现有生产环境（有 ffmpeg 无 opencv-python）中走的是 "skipped" 路径。
- **L. 质量评分传递链闭环** seedance_prompt / script_writer 已输出 `quality_score` /
`_self_check`，但下游 skill（keyframe_images → seedance_clips → remotion_assemble）尚未
读取上游 quality_score 并在低于阈值时触发 regenerate。"下游读取上游 quality_score，
低于阈值主动请求 regenerate" 机制仍是设计文档中的概念，未实现。

### 4. 2026-05-06 新增未验证路径 → 已验证/已修复

- **K. Footage 弹窗预览在三场景下的素材生成验证** ✅ 已验证 — S1/S5/Fast Mode 新产物均
正确出现在 `/footage`，弹窗视频 controls + autoplay 正常，portfolio TOP50 截断正确。
- **L. 主题翻转后全页面一致性走查** ✅ 已走查 — `/fast` `/s1` `/s5` `/footage` 无暗色残留。
发现并修复: footage 页面 grid item 无 thumbnail fallback 的 `text-white/40` icon 在
`#FCF5F2` 浅色背景上不可见 → 改为 `text-[var(--text-muted)]`。

### 5. 2026-05-06 测试中发现的新问题

- **S1 `final_video_path` 未回写** — Remotion 组装后最终视频路径未写入 pipeline state，
`final_video_path` 为空字符串。audit 报告视频存在(13.5MB)但 state 无法引用。需检查
`remotion_assemble.py` 是否正确更新 state。
- **S5 strategy 节点 LLM 超时** — 已修复: `LLM_TIMEOUT_SECONDS=60s` 对 VLOG strategy 长
prompt 不足，改为 `_step_vlog_strategy` 内创建 `LLMClient(timeout=120.0)` 专用实例。
- **S1 `product_name` 字段读取错误** — 已修复: `s1_product_pipeline.py:100` 原代码读取
`product_catalog.get("name", "Product")`，但 API 请求传的是 `"product_name"` 字段，
导致 audit `product_mention` 检查使用 "Product" 占位符。改为
`product_catalog.get("product_name") or product_catalog.get("name", "Product")`。

---

## Quick Reference

### Start backend dev server

```bash
source .venv/bin/activate && uvicorn src.api:app --reload --port 8001
```

### Start frontend dev server

```bash
cd web && npm run dev
```

### Run backend tests

```bash
make test
```

### Run frontend tests

```bash
cd web && npm test
```

### Lint + type check

```bash
make lint                # Backend (ruff)
make typecheck           # Backend (pyright)
cd web && npm run lint   # Frontend (eslint)
```

### Generate API types for frontend

```bash
cd web && npm run typegen:api
```

### Docker Compose (full stack)

```bash
docker compose up -d
```

