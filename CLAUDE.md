# AI Video Pipeline — Project Guide for Claude

## Overview

**Short Video Agent** (v0.2.0) is a multi-agent AI video creation pipeline for cross-border e-commerce. It automates the full content production workflow: strategy → script → compliance → storyboard → asset sourcing → media generation → edit → audio → caption → thumbnail → distribution → analytics.

The pipeline is built on **LangGraph** with 16 nodes (12 worker + 4 self-audit) and 4 human-in-the-loop review checkpoints. It targets maternal/baby product categories (wearable breast pumps, feeding appliances) with 5 content scenarios.

**Current status:** Production live at `https://101.34.52.232` on Tencent Lighthouse since 2026-05-03. 5 scenarios verified end-to-end in non-demo mode (see `tmp/outputs/non-demo-end-to-end-verification-20260502.md`).


> 历史更新记录已提取到 `docs/claude/updates/project-updates-202605-stable.md`。
> 已知缺口与待办已提取到 `docs/claude/known-gaps-stable.md`。

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

**Thresholds:** P0 technical-check thresholds (frame variance, AV sync, video specs) are configurable via environment variables with sensible defaults:
- `FRAME_VARIANCE_MSE_THRESHOLD` (default 50.0) / `FRAME_VARIANCE_BRIGHTNESS_THRESHOLD` (default 20.0)
- `AV_SYNC_MAX_ABS_DIFF` (default 0.5s) / `AV_SYNC_MAX_REL_DIFF` (default 5%)
- `VIDEO_MIN_FPS` (default 25.0) / `VIDEO_CRITICAL_FPS` (default 20.0)
- `VIDEO_MIN_BITRATE_KBPS` (default 1500) / `VIDEO_CRITICAL_BITRATE_KBPS` (default 1000)
- `VIDEO_ASPECT_RATIO_MIN` (default 0.53) / `VIDEO_ASPECT_RATIO_MAX` (default 0.60)

ML-module thresholds (e.g. `CLIP_ALIGN_STRONG = 0.28`, `BLUR_THRESHOLD = 100.0`) remain module-level constants. The `dynamic_thresholds.py` module can suggest adjustments based on A/B test data from `ab_tracker.py`.

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


> 详细生产部署指南已提取到 `docs/workflows/deploy-lighthouse-stable.md`。

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


> Portfolio 与 Asset Library 运营文档已提取到 `docs/workflows/portfolio-ops-stable.md`。

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


> 详细缺口清单与待办已提取到 `docs/claude/known-gaps-stable.md`。

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
