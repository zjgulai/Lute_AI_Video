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
- **`_pipeline` 延迟初始化**: `compile_pipeline()` 从模块导入时执行改为 `get_pipeline()`
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
- **循环导入修复**: `src/graph/nodes.py` 顶层 `from src.routers._state import
  _register_background_task` 导致 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py`
  循环。改为 `nodes.py` 内 `_register_bg()` helper 函数延迟导入。
- **nginx 语法修复**: `limit_req off;` 不是有效 nginx 语法，`location /health` 与
  `/api/media/` 改为 `limit_req zone=api_limit burst=100/1000 nodelay;`。
- **nginx 限流误伤前端 (429 风暴) 修复**: `server` 块顶层 `limit_req zone=api_limit
  burst=20 nodelay` 会被未显式覆盖的 `location` 默认继承，前端 `/` 和 `/_next/` 也跟着
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
- `/pipeline/*` — API key required
- `/scenario/*` — API key required
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
| Module | Endpoints | Description |
|--------|-----------|-------------|
| Auth | `/auth/login`, `/auth/logout`, `/auth/session` | Login, logout, session check |
| Dashboard | `/dashboard/summary` | Tenant count, pipeline runs today, error rate, recent errors |
| Tenants | `/tenants`, `/tenants/{id}`, `/tenants/{id}/keys`, `/tenants/{id}/keys/{kid}/revoke` | CRUD + API key lifecycle |
| Logs | `/logs`, `/logs/{id}` | Error log viewer with filters |
| Health | `/health/status`, `/health/history` | Service connectivity checks |

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

### API Key Isolation

Per-request API keys are supported via the `api_keys` field in pipeline start requests. Keys are stored using `contextvars` (not `os.environ`) so concurrent requests don't contaminate each other. The LLM client reads from request context first, then falls back to env vars.

### Chinese→English Translation

S1 and S3 pipelines auto-translate Chinese product inputs to English via `translate_catalog_to_english()`. Original Chinese values are preserved in `_original_zh` within the product catalog dict. Pipeline output language is locked to `["en"]`.

---

## Scenario Pipelines

### Common API Endpoints (`/scenario/{scenario}/...`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/scenario/s1` | Run S1 auto (full pipeline) |
| POST | `/scenario/s2` | Run S2 brand campaign |
| POST | `/scenario/s3` | Run S3 influencer remix |
| POST | `/scenario/s4` | Run S4 live shoot |
| POST | `/scenario/s5` | Run S5 brand VLOG |
| POST | `/fast/generate` | Fast Mode: direct text→video |
| GET | `/scenario/{s}/state/{label}` | Get pipeline state |
| PUT | `/scenario/{s}/state/{label}` | Update pipeline state (user edits) |
| GET | `/scenario/{s}/state/{label}/steps` | List steps with status |
| POST | `/scenario/{s}/step/{step_name}` | Execute single step |
| PUT | `/scenario/{s}/state/{label}` | Edit step output |
| POST | `/scenario/{s}/regenerate/{label}/{step}` | Regenerate step + invalidate downstream |
| GET | `/scenario/{s}/gate/{label}/{gate_id}` | Get gate state |
| POST | `/scenario/{s}/gate/{label}/{gate_id}/generate` | Generate 3 gate candidates |
| POST | `/scenario/{s}/gate/{label}/{gate_id}/approve` | Approve gate (auto-resumes pipeline) |
| POST | `/scenario/{s}/gate/{label}/{gate_id}/regenerate/{candidate}` | Regenerate single candidate |

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

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `page.tsx` | Scene selection home (5 scenario cards + fast mode) |
| `/s1` | `s1/page.tsx` | Product Direct workflow |
| `/s2` | `s2/page.tsx` | Brand Campaign workflow |
| `/s3` | `s3/page.tsx` | Influencer Remix workflow |
| `/s4` | `s4/page.tsx` | Live Shoot workflow |
| `/s5` | `s5/page.tsx` | Brand VLOG workflow |
| `/fast` | `fast/page.tsx` | Fast Mode direct generation |
| `/result` | `result/page.tsx` | Pipeline result + download |
| `/settings` | `settings/page.tsx` | API key + backend URL configuration |
| `/brand-packages` | `brand-packages/page.tsx` | Brand asset management |
| `/influencers` | `influencers/page.tsx` | Influencer management |
| `/footage` | `footage/page.tsx` | Portfolio/footage gallery |
| `/admin` | `admin/page.tsx` | Redirect to `/admin/dashboard` |
| `/admin/login` | `admin/login/page.tsx` | Admin login (email + password) |
| `/admin/dashboard` | `admin/dashboard/page.tsx` | System overview (tenants, pipelines, errors) |
| `/admin/tenants` | `admin/tenants/page.tsx` | Tenant list + create modal |
| `/admin/tenants/[id]` | `admin/tenants/[tenantId]/page.tsx` | Tenant detail + API key management |
| `/admin/logs` | `admin/logs/page.tsx` | Error log viewer with filters |
| `/admin/health` | `admin/health/page.tsx` | Service health status cards |

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
- Used exclusively by `/admin/*` pages

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
   Note: rsync to bind-mounted nginx.conf needs `--inplace --no-whole-file` or an explicit
   `docker restart ai_video_nginx` afterwards (nginx locks the inode at startup, so a
   default rename-based rsync makes `nginx -s reload` a no-op).
   Volume 命名:docker compose project = `lighthouse`(因为 compose 文件在
   `deploy/lighthouse/`),所以 backend output volume 是 `lighthouse_backend_output`,
   不是 `ai-video_backend_output`(后者是历史残留 volume,backend 不会读到)。任何
   `docker run -v <volume>:/...` 操作都要用 `lighthouse_backend_output`。
   2026-05-05 部署事故防御:`Dockerfile.backend` 配阿里云 PyPI mirror、`deploy.sh`
   Phase 0 比 `requirements.txt` mtime vs image 时间提示 rebuild、backend
   `restart: on-failure:5` 限制无限重启。完整时间线 + 紧急恢复三步法见
   `docs/workflows/incident-2026-05-05-postgres-saver-deploy-stable.md`。
   **2026-05-07 deploy.sh 更新**: 构建前清理 `.next/standalone/` `.next/static/`
   `.next/server/` 防止 Turbopack 旧 chunk 残留；构建后验证 `standalone/server.js`
   和 `static/chunks/` 存在；新增 `restart nginx` 确保配置变更生效。
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
- ESLint lock on demo key: `web/eslint.config.mjs` `no-restricted-syntax` 规则禁止
  Literal `'ai_video_demo_2026'` 出现在 fallback / placeholder / i18n 之外的位置;
  `no-restricted-imports` 禁止 import `API_BASE` 常量(必须用 `getApiBase()` /
  `apiFetch()`)。新组件直接调 `apiFetch()`,不要 `fetch(\`${API_BASE}/...\`, ...)`。

---

## Known Gaps and TODOs

最近一次盘点:2026-05-07(生产部署修复 + ChunkLoadError 诊断后)。

### 1. 已知功能缺陷(已修复)

> **2026-05-07 修复:**
> - **ChunkLoadError /footage 页面崩溃** — Turbopack content-hash 变化导致旧 chunk 引用失效。
>   nginx `location /` 添加 `Cache-Control: no-store` 禁止 HTML 缓存，`location /_next/`
>   静态资源长期缓存。`deploy.sh` 构建前清理旧产物避免残留。
> - **循环导入导致 backend 启动失败** — `src/graph/nodes.py` 顶层导入 `_register_background_task`
>   形成 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py` 循环。改为延迟导入 helper。
> - **nginx `limit_req off` 语法错误** — 原配置使用无效语法，`location /health` 和
>   `/api/media/` 改为高 burst 值实现等效豁免。
> - **nginx 顶层 `limit_req` 误伤前端导致首页 429** — `server` 块顶层 `limit_req
>   zone=api_limit burst=20 nodelay` 被前端 `/` 和 `/_next/` 默认继承，Next.js 冷启动
>   30+ 并发请求秒爆 burst=20。修复：删除顶层声明，改为 7 个 API location 内部
>   显式 `limit_req`。生产 rsync `--inplace --no-whole-file` + `nginx -s reload` 落地。

> **2026-05-06 修复:**
> - **Portfolio 加载慢 + 视频无法预览** — 后端 `?limit=50&sort=quality` + nginx `try_files`
>   静态直送 + 144 个 poster thumbnail + 前端 `<img poster>` 替代 337 个 `<video preload="metadata">`。
>   实测 thumbnail 4.8ms / video 32ms(02849c9)。
> - **Footage 页面交互不一致** — 成品/素材统一 `MediaPreviewModal` 弹窗预览,不再
>   `window.open` 或右侧 detail panel;Materials 新增 全部/视频/图片/音频 分类过滤(c4dd6ed)。
> - **UI 主题翻转** — `globals.css` + `tailwind.config.js` + 40+ 组件从暗黑剧场翻转为
>   Warm Light Professional Theme(d3e8bd3)。

> **2026-05-08 4-Option Plan 修复/扩展:**
> - **POYO sanitizer Phase 2** — 新增 11 条替换规则(英 7 + 中 4)，覆盖 baby bottle / nipple /
>   areola / formula milk / baby food / postpartum / 奶瓶 / 奶嘴 / 辅食 / 产后。
>   新增结构化 CM 拒绝日志，生产可通过 `poyo_cm_rejection` 事件抓回原始 prompt 持续补充规则。
> - **S3-S5 Gate 配置** — `gate_manager.py` per-scenario 重构完成，S3/S4/S5 各场景 gate
>   定义与候选评分已就位，但 gate 全链路端到端验证仍待 Phase 1D。
> - **Long pipeline UX** — 统一异步框架已落地，S2/S3/S5 的长链路不再受 HTTP 超时截断。

仍待处理:
- **POYO sanitizer 覆盖率持续提升(F3, P2)** Phase 2 新增 11 条规则后覆盖率大幅提升，
  但仍需在生产日志中持续抓回 `poyo_cm_rejection` 事件中的原始 prompt 文本补充新规则。
- **yt-dlp / whisper 未装进 backend 容器(F4, P3)** D5 KOL 视频分析 skill 走 mock 路径,
  脚本生成不依赖真实 transcribe,管线下游不受影响。要让 video-analysis 真实工作需
  `pip install yt-dlp openai-whisper` 进 `Dockerfile.backend`(whisper 拉 PyTorch ~2GB,
  实施前先确认是否值)。

### 2. 配置/历史遗留(已知)

- **api_assets.py compat shim:** `/api/assets/*` uses in-memory dicts (`_brand_packages`,
  `_influencers`). Frontend OpenAPI types still reference these paths, so don't remove the
  router; do migrate any new asset features to `src/routers/assets.py` instead.
- **S2-S5 step-by-step / gate system:** S3/S4/S5 已完成 StepRunner 迁移 (P2) 与 gate
  配置 (2026-05-08)。`run_step()` 接口已统一，gate 定义与候选评分已 per-scenario 配置。
  gate 全链路端到端验证仍待 Phase 1D。
- **Long pipeline UX:** ✅ 已解决(2026-05-08) — 统一异步执行框架落地，所有场景走
  `POST /submit` → 轮询 `/status`，HTTP 超时不再截断长链路。nginx 1500s 退居兜底。
- **Redis/Celery declared but unused:** Still in `requirements.txt` but no live consumer.
- **LangGraph 代理层 (P4-4):** `/pipeline/*` 端点已代理到 StepRunner，但代理层 state 转换是
  best-effort，某些 legacy 字段可能缺失。保留原始 LangGraph 代码作为兼容层，代理函数可迭代补全。
- **pyright strict 剩余规则:** `reportUnknownMemberType` / `reportUnknownVariableType` 未启用。
  在 `dict[str, Any]` 为主的代码库中，这两项规则噪音远大于价值。如需进一步收紧类型，需先
  将 `dict[str, Any]` 替换为数百个具体类型（ProductCatalog、PipelineConfig 等），ROI 待评估。

### 3. 未做端到端验证的前后端交互路径

Phase D/E 通过的是 5 场景"主路径" + portfolio 优化。以下路径在生产尚未端到端实测:

- **A. Human Review 4 个 checkpoint 的人工分支** Pipeline `strategy_audit` /
  `script_audit` / `editing_audit` / `thumbnail_audit` 的 score 落在 0.60–0.90 区间会触发
  HITL,前端 `GatePanel` + 后端 `POST /scenario/{s}/gate/{label}/{gate_id}/approve` 的
  "APPROVED / CHANGES_REQUESTED / REJECTED" 三个分支以及 D10 contextvars 路由覆写,
  Phase D 没触发到。需要构造低分输入或下调阈值实测。
- **B. S1 step-by-step + Gate 候选生成全链路** `POST /scenario/s1/gate/.../generate` 一次
  生成 3 个候选 + `CandidateScorer` 评分 + 前端 `CandidateSelector` 对比 + `regenerate/{candidate}`
  单候选重生成 + 选定后 `approve` 触发后台续跑。Phase D D2 走的是 auto 模式,gate 系统的
  完整闭环未实测。
- **C. Distribution / Publish** `POST /distribution/publish` + TikTok / Shopify connector
  实际发布。Phase D 没跑过,只有单元测试。需要真实 platform credentials 才能走通。
- **D. Metrics 全链** `GET /metrics/*` 视频性能查询、`src/tasks/metrics_poller.py` 周期任务
  在生产是否被调度、Alembic 的 `video_metrics` 表是否真的 `alembic upgrade head` 过、
  PG 与 SQLite 双路是否在生产生效。前端 `PerformanceDashboard` 显示真数据未验证。
- **E. Assets 上传链路** `/api/upload` + 前端 `GuidedCard` 文件选择(本地 Playwright 验过
  点击触发 filechooser)在生产未走通"上传 → 后端落盘 → 管线引用 → 出现在最终视频"。
  类似的还有 `/brand-packages` / `/influencers` 列表 CRUD 在生产是否真存了 PG。
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
