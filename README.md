# Short Video Agent v0.2.7

Multi-agent AI video creation pipeline for cross-border e-commerce.
Automates the full content production workflow: strategy → script → compliance → storyboard → asset sourcing → media generation → edit → audio → caption → thumbnail → distribution → analytics.

Built on **LangGraph** with 16 nodes (12 worker + 4 self-audit) and 4 human-in-the-loop review checkpoints.

**Live:** [https://video.lute-tlz-dddd.top](https://video.lute-tlz-dddd.top) (Tencent Lighthouse canonical domain). IP fallback: [https://101.34.52.232](https://101.34.52.232).

---

## Prerequisites

- **Python 3.12+**
- **Node.js 22+** with pnpm (for WebUI + Remotion rendering)

```bash
python3 --version  # >= 3.12
node --version     # >= 22
pnpm --version
```

---

## Quick Start

### 1. Clone & Setup

```bash
git clone <repo>
cd AI_vedio

# Python backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd web
pnpm install
```

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your API keys:
#   DEEPSEEK_API_KEY, POYO_API_KEY, SILICONFLOW_API_KEY
```

### 3. Run

```bash
# Terminal 1: Backend
source .venv/bin/activate
uvicorn src.api:app --reload --port 8001

# Terminal 2: Frontend
cd web
pnpm dev
```

Backend: http://localhost:8001<br>
Frontend: http://localhost:3000

### 4. Docker Compose (all services)

```bash
docker compose up -d
```

---

## Architecture

```
web/                    Next.js 16 — Review UI (React 19 + TypeScript + Tailwind CSS 3)
rendering/              Remotion 4 — .mp4 video renderer (standalone)
src/
  api.py                FastAPI app — middleware, router mounts
  config.py             Environment config + structlog + sensitive-data sanitizer
  graph/
    pipeline.py         LangGraph 16-node pipeline compilation + checkpoint config
    nodes.py            12 worker + 4 audit node implementations
    routing.py          Conditional routing + retry guard + audit guard + D10 override
  agents/               14 agent implementations (strategy, script, compliance, ...)
  pipeline/
    step_runner.py      Step-by-step execution engine (S1-S5)
    state_manager.py    Pipeline state persistence
    gate_manager.py     Expert Studio 3-candidate generation
  routers/              FastAPI domain routers
    pipeline.py, scenario.py, distribution.py, metrics.py,
    assets.py, media.py, health.py, admin/ (auth/tenants/dashboard/logs/health)
  models/               Pydantic models (split by domain: enums, pipeline, media, audit, ...)
  tools/                External API clients (llm_client, poyo_client, cosyvoice_client, ...)
  quality/              ML-powered quality assessment (CLIP, BRISQUE, face, safe-zone, ...)
  storage/              Database layer (asyncpg + SQLite fallback)
tests/                  380+ tests across 112 files
docs/                   Project documentation (ADR, runbooks, workflows, guides)
```

### LLM Provider Chain

| Role | Model | Provider |
|------|-------|----------|
| Text (LLM) | DeepSeek-V4-Pro | DeepSeek |
| Image | GPT-4o Image | poyo.ai |
| Video | Seedance 2 | poyo.ai |
| TTS | CosyVoice2-0.5B | SiliconFlow |

---

## Key Endpoints

### Pipeline & Scenarios

| Method | Path | Description |
|--------|------|-------------|
| POST | `/scenario/s1` | S1: Product Direct |
| POST | `/scenario/s2` | S2: Brand Campaign |
| POST | `/scenario/s3` | S3: Influencer Remix |
| POST | `/scenario/s4` | S4: Live Shoot |
| POST | `/scenario/s5` | S5: Brand VLOG |
| POST | `/fast/generate` | Fast Mode: direct text→video |
| GET | `/scenario/{s}/state/{label}` | Get pipeline state |
| POST | `/scenario/{s}/step/{step}` | Execute single step |
| POST | `/scenario/{s}/regenerate/{label}/{step}` | Regenerate step |

### Admin Panel

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/auth/login` | Admin login (session cookie) |
| GET | `/api/admin/dashboard/summary` | System overview |
| GET | `/api/admin/tenants` | Tenant list |
| POST | `/api/admin/tenants/{id}/keys` | Create API key |
| GET | `/api/admin/logs` | Error log viewer |
| GET | `/api/admin/health/status` | Service health |

See [docs/reference/api-endpoints.md](docs/reference/api-endpoints.md) for full API reference.

---

## Running Tests

```bash
# Backend
make test           # pytest
make lint           # ruff
make typecheck      # pyright
make ci             # lint + test

# Frontend
cd web
pnpm test           # vitest
pnpm lint           # eslint

# E2E
cd web
pnpm e2e            # Playwright local
pnpm e2e:ui         # UI-only visual/interaction regression, no poyo.ai token usage
pnpm e2e:prod       # Playwright production, skips @token-smoke by default
RUN_TOKEN_SMOKE=1 pnpm e2e:prod  # Explicit real task / provider-credit smoke
```

---

## Project Status

- **v0.2.7** — Brand assets Phase 2-4, portfolio API, quick templates
- **2026-05-31 production deploy** — Lighthouse live at `https://video.lute-tlz-dddd.top`; latest deployed commits include `306b86f`, `95c2925`, and `d62a3ac`
- 6 scenarios (Fast Mode + S1-S5) verified end-to-end in production; real token-consuming generation smoke is opt-in via `RUN_TOKEN_SMOKE=1`
- Quality system in observe mode (frame variance, AV sync, video specs)
- Admin Panel Phase 1 operational (tenants, logs, health, auth)
- 380+ tests, CI/CD via GitHub Actions

See [docs/claude/updates/project-updates-202605-stable.md](docs/claude/updates/project-updates-202605-stable.md) for release history.

See [docs/workflows/deploy-lighthouse-stable.md](docs/workflows/deploy-lighthouse-stable.md) for production deployment guide.
