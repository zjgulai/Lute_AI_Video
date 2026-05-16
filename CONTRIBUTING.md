# Contributing to AI Video Pipeline

> **30-minute new developer onboarding** — task_plan 4.10 / MASTER-PLAN TODO-E17.

This guide gets you from `git clone` to passing CI in 30 minutes. For deeper docs, see `AGENTS.md` (project-wide standards), `docs/architecture/adr/` (architectural decisions), and `docs/runbooks/` (incident playbooks).

---

## 1. Prerequisites

- Python 3.11 or 3.12
- Node.js 22+
- Docker + Docker Compose (optional, for local PG)
- macOS / Linux (Windows: use WSL2)

Verify:

```bash
python3 --version
node --version
docker --version  # optional
```

---

## 2. Setup (5 min)

```bash
git clone https://github.com/zjgulai/Lute_AI_Video.git
cd Lute_AI_Video

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd web && npm ci && cd ..

# Optional: copy env template (no real keys needed for testing)
cp .env.example .env
```

---

## 3. Run tests (5 min)

**Backend** (1127 tests collected, ~30s on M-series Mac):

```bash
source .venv/bin/activate
python -m pytest tests/ -q --tb=short
```

**Frontend** (5 files, 19 tests, ~3s):

```bash
cd web && npx vitest run
```

**Linters** (must be clean before PR):

```bash
ruff check src/ tests/
cd web && npm run lint  # informational; not a CI gate yet
```

**Type checks**:

```bash
cd web && npx tsc --noEmit -p tsconfig.json
```

---

## 4. Run the app locally (10 min)

**Backend**:

```bash
source .venv/bin/activate
uvicorn src.api:app --reload --port 8001
```

In another terminal — **frontend**:

```bash
cd web && npm run dev
```

Open http://localhost:3000.

**Without API keys**, the pipeline runs in **mock mode** — produces placeholder content instead of calling DeepSeek / POYO / SiliconFlow. To use real APIs, set the keys in `.env` (see `.env.example`).

---

## 5. Make your first change (10 min)

### Pick a task

- Look in `.kiro/plan/MASTER-PLAN-2026-05-16.md` for the active TODO list
- "Phase α" items are 5-30 min trivial fixes — good first issues
- Check open GitHub issues

### Branch + commit conventions

```bash
git checkout -b fix/TODO-X-short-description
# ... make changes ...
git add <files>
git commit -m "type(scope): one-line summary

Body explains the WHY (not the WHAT). Reference TODO ID + audit
findings. Note any tradeoffs taken.

Verified:
- ruff clean / pytest <count> PASS / vitest 19/19 PASS / etc."
```

Commit `type` values: `feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `i18n`.

### PR checklist

- [ ] Tests added or updated (every behavior change needs a test)
- [ ] `pytest tests/ -q` passes (or note pre-existing failures)
- [ ] `ruff check` clean
- [ ] `npx vitest run` passes (if frontend changes)
- [ ] `npx tsc --noEmit` clean (frontend; pre-existing SettingsPanel.test error allowed)
- [ ] Commit message body explains tradeoffs / non-obvious decisions
- [ ] Linked to a TODO ID from MASTER-PLAN if applicable

---

## 6. Project structure cheat sheet

```
src/                Python backend
  api.py            FastAPI app entry
  routers/          HTTP endpoints (per-domain)
  agents/           LangGraph nodes
  pipeline/         Scenario pipelines (S1-S5 + Fast Mode)
  skills/           Reusable steps (LLM, image, video, TTS)
  tools/            External API clients
  storage/          PG + SQLite repository layer
  models/           Pydantic + TypedDict
  telemetry*.py     Logging + Prometheus metrics

web/src/            Next.js 16 frontend (TypeScript)
  app/              App Router pages (s1-s5, fast, admin/*)
  components/       40+ React components + api.ts client
  i18n/             zh-CN + en translations
  lib/              utilities (errors.ts, etc)

tests/              30+ pytest files (1127 tests)
rendering/          Standalone Remotion 4 video renderer
docs/               Architecture, runbooks, workflows
.kiro/plan/         Active execution plans (UNIFIED + MASTER + audit reports)
deploy/             Lighthouse + alternative deploy artifacts
migrations/         Alembic SQL migrations
```

---

## 7. Where to ask

- **Architecture**: read `docs/architecture/adr/` index first
- **Operations**: `docs/runbooks/` covers known incident patterns
- **Code patterns**: search `AGENTS.md` for "## Key Patterns and Conventions"
- **Project status**: `.kiro/plan/MASTER-PLAN-2026-05-16.md` (current sprint)
- **Stuck**: open a GitHub issue with `question:` prefix

---

## 8. Common pitfalls

### "Why is my catch block typed `unknown`?"

Per TODO-25 cleanup. Use `errorMessage(err, "fallback")` from `web/src/lib/errors.ts`. Don't add `e: any` — eslint blocks it.

### "Why does `t(key, fallback)` work but `t(key) || fallback` doesn't?"

`t()` returns the last segment of `key` when missing (truthy), so `||` short-circuits incorrectly. Use the explicit `fallback` parameter. See `web/src/i18n/I18nProvider.tsx:86-96`.

### "alembic upgrade fails with 'no alembic_version'"

If running against a fresh PG that was provisioned via `001_init.sql` rather than alembic, you need `alembic stamp 2d6b8e9c0f1a` first to mark baseline. See `deploy/lighthouse/PHASE0-DEPLOY-SOP-2026-05-15.md` step 5.

### "docker build hangs at apt-get install"

China network → deb.debian.org is slow. Aliyun apt mirror is already configured in `Dockerfile.backend`. Verify with:

```bash
grep APT_MIRROR Dockerfile.backend
```

### "I cat'd .env.prod and now keys are leaked"

Run `docs/runbooks/key-rotation.md` immediately. Don't push the keys to a debug PR.

---

## 9. Security checklist (pre-PR)

- No `print()` of API keys / tokens / passwords / cookies
- No `console.log()` of user input or secrets
- No new `os.environ.get` outside `src/config.py` (use `from src.config import settings`)
- No `as any` / `@ts-ignore` / `@ts-expect-error` (TypeScript)
- No `except Exception: pass` without logging the exception
- No SQL string concatenation; use `$1` / `?` parameterized queries
- Admin POST/PUT/DELETE endpoints MUST `Depends(verify_csrf_token)` (see `src/routers/_admin_deps.py`)

---

## 10. After your PR merges

- Watch CI: `lint` + `test` + `frontend-test` + `docs-link-check` must all pass
- Production deploy is **manual** to lighthouse `101.34.52.232` (no auto-deploy yet — task_plan 4.4 backlog)
- Phase 0 watchdog (`/etc/cron.d/phase0_watchdog` on lighthouse) hourly checks 3 SLI buckets

---

*Last updated: 2026-05-16. Maintained as part of MASTER-PLAN-2026-05-16. PRs welcome to keep this guide accurate.*
