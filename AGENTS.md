# AI Video Pipeline — Project Guide for Codex

## Overview

**Short Video Agent** (v0.2.0) is a multi-agent AI video creation pipeline for cross-border e-commerce. It automates the full content production workflow: strategy → script → compliance → storyboard → asset sourcing → media generation → edit → audio → caption → thumbnail → distribution → analytics.

The pipeline is built on **LangGraph** with 16 nodes (12 worker + 4 self-audit) and 4 human-in-the-loop review checkpoints. It targets maternal/baby product categories (wearable breast pumps, feeding appliances) with 5 content scenarios.

**Current status:** Production live at `https://101.34.52.232` on Tencent Lighthouse since 2026-05-03. 5 scenarios verified end-to-end in non-demo mode (see `tmp/outputs/non-demo-end-to-end-verification-20260502.md`). CloudBase / Render are documented as alternative deploy paths but are not the canonical target.

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
│           assets, media, health, telemetry               │
│  Middleware: CORS, rate-limit, response-wrapper, logging │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────────┐
│ LangGraph    │ │ PostgreSQL  │ │ External APIs     │
│ Pipeline     │ │ (primary)   │ │ DeepSeek V4-Pro   │
│ 16 nodes     │ │ SQLite      │ │ poyo.ai (img/vid) │
│ 4 checkpoints│ │ (fallback)  │ │ CosyVoice (TTS)   │
└──────────────┘ └─────────────┘ └──────────────────┘
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
│   │   ├── script_writer.py    # Multi-language script writer (EN/ES/FR/DE)
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
│   │   ├── _deps.py            # Shared: verify_api_key, _safe_error, _serialize, _inject_api_keys
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
│   │   │   └── footage/page.tsx
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
│   │   │   └── ...              # and more
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
5. **API Key Auth** — `verify_api_key` dependency applied to most routers. Demo key (`ai_video_demo_2026`) is read-only.

Routers are mounted on startup:
- `/health` — no auth
- `/pipeline/*` — API key required
- `/scenario/*` — API key required
- `/distribution/*` — API key required
- `/metrics/*` — API key required
- `/assets/*` — API key required
- `/media/*` — no auth (file serving)
- `/api/assets/*` — API key required (legacy)
- `/telemetry/*` — API key required

On startup, the app also restores active threads from disk and starts periodic cache eviction.

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

S2-S5 have simpler pipeline implementations without step-by-step mode or gates. Each has its own pipeline class in `src/pipeline/`.

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
- `video_metrics` — performance metrics; Alembic migration `1efc41794d64` (2026-05-01) adds the
  PG table. `src/storage/migrations/001_init.sql` does NOT include it, so a fresh Docker
  Compose stack still runs SQLite-only until `alembic upgrade head` runs against the PG.
  Repository (`metrics_repository.py`) is PG-first with SQLite fallback — both paths are
  exercised in tests.

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

### State Management (Zustand)

**useAppStore:** Navigation stage (home/recommend/generate/result), active scene, mode (expert/smart), pipeline mode (auto/step_by_step), video duration, loading/toast/disconnected state.

**usePipelineStore:** Pipeline execution state, thread tracking, review status, step progress, current label, gate state.

**useExpertStore:** Expert mode settings, advanced configuration.

### i18n

Bilingual (zh-CN / en) via `I18nProvider` React context. Translations in `web/src/i18n/translations.ts`. All user-facing strings use translation keys.

### API Client (`web/src/components/api.ts`)

Backend URL and API key stored via `localStorage` with cookie fallback (privacy/incognito mode). Supports demo mode. Build-time env vars (`NEXT_PUBLIC_API_BASE_URL`) provide defaults.

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

**CI:** GitHub Actions on push/PR to main — ruff lint + pytest (Python 3.11 + 3.12) + coverage.

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

### API Design
- All JSON responses wrapped with `_meta` (trace_id, duration_ms, version, timestamp)
- API key required for all mutating endpoints
- Demo key (`ai_video_demo_2026`) is read-only — blocks DELETE/POST/PUT on write paths
- Rate limiting: 120 req/min per IP
- Per-request API key injection via contextvars for multi-tenant safety

### Pipeline State
- Single `VideoPipelineState` TypedDict with 30+ fields
- Nodes add fields incrementally (TypedDict with `total=False`)
- State serialized as JSON for checkpoint persistence
- Export endpoint strips internal fields (retry_counts, self_verifications, etc.)

### Frontend Conventions
- Dark theme by default (`data-theme="dark"`)
- Film grain + vignette overlay on all pages
- Chinese-first i18n with English toggle
- localStorage + cookie dual storage for settings
- Background polling for pipeline progress (StepByStepView, StageProgress)

---

## Known Gaps and TODOs

From the 2026-05-03 production-readiness review:
- **Configuration divergence:** `DEFAULT_LLM_PROVIDER` value differs across `config.py`
  fallback (`anthropic`), `render.yaml` (`kimi`), and `deploy/lighthouse/.env.prod`
  (`deepseek`, the live value). Pick one canonical default and align the rest.
- **video_metrics in Docker init SQL:** Alembic has the PG table; `src/storage/migrations/001_init.sql`
  does not. Fresh `docker compose up` falls back to SQLite until `alembic upgrade head` runs.
- **POYO content-moderation coverage:** `src/tools/poyo_safety.py` substitutes the most
  common maternal/baby trigger phrases, but D5 still hit 1 thumbnail rejection (caught by
  pipeline retry). Add new regex rules as new triggers surface in production logs.
- **Long pipeline UX:** S2/S3/S5 can take 10-30 min. curl/HTTP clients commonly time out
  before the pipeline finishes (backend keeps running). Consider async submit + GET
  /status/{thread_id} polling for the long scenarios.
- **api_assets.py compat shim:** `/api/assets/*` uses in-memory dicts (`_brand_packages`,
  `_influencers`). Frontend OpenAPI types still reference these paths, so don't remove the
  router; do migrate any new asset features to `src/routers/assets.py` instead.
- **S2-S5 lack step-by-step / gate system:** S1 only. Adding gates to S2-S5 is a planned
  follow-up.
- **Remotion rendering integration:** Now runs as a separate `rendering:3001` HTTP service
  (since 2026-05-02). Backend posts pipeline state JSON to `/assemble`, no more
  `npx remotion` shell out.
- **Redis/Celery legacy reference:** Previously mentioned in requirements.txt;
  verified removed as of 2026-05-11. No `import redis`/`import celery` in `src/`
  or `tests/`. If a future feature needs a task queue, add the dep then.

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
