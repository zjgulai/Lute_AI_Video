# Production Readiness Framework — Integrated Delivery Plan

**Status:** Approved
**Date:** 2026-05-07
**Author:** Claude (brainstorming with Pray)
**Target:** External-customer-ready (B) — 3-5 paying tenants, 95% availability
**Duration:** 3-4 weeks, phased execution

---

## 0. Executive Summary

This document defines the integrated delivery plan for Short Video Agent v0.2.0, transitioning from a single-operator tool to an external-customer-ready SaaS platform. It follows a MECE 4-phase Production Readiness Framework, with each phase having clear entry criteria, tasks, and exit criteria.

**Delivery standard:** External-customer-ready (B) — 3-5 tenants, 95% uptime, all core paths verified.

**Approach:** 4-phase framework (recommended by senior engineering review) with risk-driven prioritization within each phase.

**Methodology goal:** Reusable AI software development workflow that can be applied to future projects.

---

## 1. Current State Baseline

### 1.1 Project Scale

| Metric | Value |
|--------|-------|
| Backend test files | 42 |
| Frontend test files | 2 (settings panel + smoke) |
| Admin panel test coverage | 0% |
| E2E test suites | 0 |
| Negative/fault-injection tests | 0 |
| Performance/stress tests | 0 |
| Production environment | Tencent Lighthouse (101.34.52.232) |
| Frontend pages | 18 (including 7 admin pages) |
| Backend routers | 10 |
| Alembic migrations | 5 |

### 1.2 Known Gaps (from CLAUDE.md audit 2026-05-07)

**Untested interaction paths (10 items, A-J):**
- A. Human Review 4 checkpoints — never triggered in production
- B. S1 Gate full flow (3-candidate generation + approval + resume) — untested
- C. Distribution/Publish — unit tests only, no real platform credentials
- D. Metrics full chain — unknown if poller runs in production
- E. Asset upload chain — not verified end-to-end
- F. Webhook event dispatch — never triggered
- G. Error degradation paths — never triggered (all green paths)
- H. Multi-tenant concurrent isolation — never stress-tested
- I. i18n full-page consistency — never audited
- J. Alternative deploy targets — stale since Lighthouse became canonical

**Pending fixes (3 items):**
- POYO sanitizer coverage not 100%
- yt-dlp/whisper not installed in backend container
- S1 final_video_path not written to state

**Config/legacy issues (6 items):**
- api_assets.py compat shim (in-memory dicts)
- S3-S5 gate system not connected
- Redis/Celery declared but unused
- LangGraph proxy layer best-effort state conversion
- DEFAULT_LLM_PROVIDER divergence across 4 locations
- pyright strict residual rules (ROI not justified)

### 1.3 Admin Panel (Phase 1 — just deployed)

| Module | Files | Lines | Tests |
|--------|-------|-------|-------|
| Backend auth | `_admin_deps.py` + `admin.py` | 1,271 | 0 |
| Frontend pages | 7 pages + sidebar | 1,646 | 0 |
| Database | 4 new tables | — | untested |
| Background tasks | 3 (health/log/session cleanup) | — | untested |

---

## 2. Phase 1: Architecture Audit & Code Governance

**Duration:** Week 1 (5-7 days, runs in parallel with Phase 2)
**Goal:** Full-stack audit, classify all findings by severity, fix P0/P1 immediately.

### 2.1 Code Quality Audit

| Task | Tool | Target |
|------|------|--------|
| Enable `reportUnusedImport` + `reportUnusedVariable` | pyright | 0 errors |
| Add Ruff rules: `FBT`, `SIM`, `TCH` | ruff | 0 violations |
| Cyclomatic complexity scan | radon or manual | Flag functions > 100 lines, depth > 4 |
| Split large files | manual | Identify candidates: admin.py (1,097 lines) |

### 2.2 Security Audit

| Task | Method | Expected Outcome |
|------|--------|------------------|
| Auth boundary scan | Traverse all router decorators | Confirm every endpoint has correct auth dependency |
| API key leak scan | `git log --all \| grep -E 'sk-[a-zA-Z0-9]{20,}'` | 0 matches |
| SQL injection check | Review all DB queries | Confirm 100% parameterized ($1, $2) |
| Cookie Secure flag | Check production login response headers | Secure; HttpOnly; SameSite=Lax |
| Hardcoded secrets scan | `grep -rE '(password|secret|key)\s*=\s*["\x27][^$]' src/` | 0 matches |

### 2.3 Architecture Debt Inventory

| Item | Severity | Action | Phase |
|------|----------|--------|-------|
| LangGraph proxy state conversion gaps | P1 | Audit missing fields, fill gaps | 1 |
| S3-S5 gate system not connected | P2 | Feature gap — document and prioritize for future phase | 3+ |
| api_assets.py compat shim (in-memory) | P2 | Migrate to `src/routers/assets.py` | 3 |
| Redis/Celery in requirements unused | P2 | Remove from requirements.txt | 1 |
| DEFAULT_LLM_PROVIDER divergence (4 locations) | P2 | Align all to `deepseek` | 1 |
| `_safe_error` / `_serialize` duplication | P3 | Extract shared util | 3+ |
| pyright strict residual rules | P3 | No action (ROI not justified) | — |

### 2.4 Performance Baseline

| Task | Method |
|------|--------|
| Collect P50/P95/P99 latency from Prometheus metrics | `pipeline_duration_seconds` histogram |
| Identify slow steps (> 5s) | `step_duration_seconds` by step_name |
| DB query analysis | `pg_stat_statements` or manual EXPLAIN ANALYZE on top queries |
| Nginx access log analysis | `awk` or GoAccess on production access.log |

### 2.5 Dependency & Config Drift

| Task | Method |
|------|--------|
| Audit `requirements.txt` version pinning | `pip list --outdated` |
| Frontend CVE scan | `cd web && npm audit` |
| `.env.prod` vs `.env.example` diff | Manual comparison — document any production-only vars |

### Phase 1 Exit Criteria

- [ ] Audit report complete with all findings classified P0-P3
- [ ] All P0 items resolved (0 remaining)
- [ ] All P1 items resolved (0 remaining)
- [ ] P2/P3 items registered in backlog with target phase
- [ ] ≥ 2 new Architecture Decision Records written
- [ ] pyright + ruff pass with tightened rules

---

## 3. Phase 2: Test Closure

**Duration:** Week 1-3 (largest workload, starts immediately, overlaps with Phase 1)
**Goal:** Elevate test coverage from "quantity without quality" to "core paths guaranteed."

### 3.1 Test Pyramid Baseline & Target

```
                    Current          Target
                    ┌─────┐          ┌─────┐
                    │  0  │ E2E      │  6  │
                   ┌┴─────┴┐        ┌┴─────┴┐
                   │  0  │ Integ    │ 10  │
                  ┌┴───────┴┐      ┌┴───────┴┐
                  │  2  │ Frontend│ 30+ │
                 ┌┴─────────┴┐    ┌┴─────────┴┐
                 │   42  │ Backend│ 50+ │
                 └────────────┘    └────────────┘
```

### 3.2 Layer 1 — Unit Test Completion (3-4 days)

**Backend admin tests (new directory `tests/admin/`):**

| Test File | Scope |
|-----------|-------|
| `tests/admin/test_admin_auth.py` | Login flow, logout, session validation, rate limiting, invalid credentials, bcrypt edge cases |
| `tests/admin/test_admin_tenants.py` | CRUD, disable cascade, status transitions, duplicate tenant_id rejection, format validation |
| `tests/admin/test_admin_keys.py` | Key creation (plaintext once), revocation, revoked key auth rejection, disabled tenant key rejection |
| `tests/admin/test_admin_logs.py` | Listing, pagination, filtering (time/level/scenario/tenant), detail view, empty state |
| `tests/admin/test_admin_health.py` | Status checks, history endpoint, all 5 services reporting, concurrent access safety |

**Regression tests for audit findings:**
- Any boundary condition discovered in Phase 1 gets a regression test.

### 3.3 Layer 2 — Frontend Component Tests (5-7 days)

**Admin pages (6 new test files):**

| Test File | Key Test Cases |
|-----------|---------------|
| `AdminLogin.test.tsx` | Form validation, error display on invalid creds, redirect on success, rate limit display |
| `AdminDashboard.test.tsx` | Data loading state, metric cards display, empty state, error state + retry, refresh button |
| `AdminTenants.test.tsx` | List rendering, search, create modal validation (tenant_id format), pagination |
| `AdminTenantDetail.test.tsx` | Key list, create key modal (plaintext display once), revoke confirmation |
| `AdminLogs.test.tsx` | Filter controls, table rendering, detail modal (traceback display), pagination |
| `AdminHealth.test.tsx` | Service cards (all states), history table, check-now button |

**Creative pages (existing gaps):**

| Test File | Key Test Cases |
|-----------|---------------|
| `GatePanel.test.tsx` | Candidate display, approve/reject/regenerate actions |
| `CandidateSelector.test.tsx` | 3-candidate comparison, score display, selection |
| `S1Workflow.test.tsx` | Step-by-step flow, step execution, progress display |
| Additional pages | S2, S3, S4, S5, Fast Mode, Result pages — at minimum: render without crash + empty state |

**Test pattern:** Vitest + @testing-library/react. Follow existing `SettingsPanel.test.tsx` pattern.

### 3.4 Layer 3 — Integration Tests: Untested Path Closure (5-7 days)

Priority-ordered execution of the 10 untested paths from CLAUDE.md:

**P0 — Must verify (customer-trust-critical):**

| Id | Path | Risk | Verification Approach |
|----|------|------|----------------------|
| G | Error degradation | Pipeline crashes when LLM fails → customer sees nothing | Fault injection: Mock POYO/DeepSeek returning 500 → verify degrade flag → verify termination → verify error_logs entry |
| H | Multi-tenant isolation | Key mixing = trust-breaking incident | Concurrency test: 2+ threads with different keys → verify contextvars isolation → verify LLM client uses correct key |
| A | Human Review branches | Differentiator feature never validated | Lower audit thresholds to 0.50 → trigger HITL → test APPROVED/CHANGES_REQUESTED/REJECTED branches → verify contextvars routing |

**P1 — Should verify (feature-critical):**

| Id | Path | Verification Approach |
|----|------|----------------------|
| B | S1 Gate full flow | End-to-end: generate 3 candidates → CandidateScorer → select → approve → background resume |
| E | Asset upload chain | Upload file → verify disk write → pipeline reference → appears in final output |
| D | Metrics full chain | Verify alembic migration ran → metrics_poller scheduled → frontend dashboard shows data |

**P2 — Nice to verify (time-permitting):**

| Id | Path | Verification Approach |
|----|------|----------------------|
| C | Distribution/Publish | Mock connector flow validation — mark "needs real credentials" |
| F | Webhook dispatch | webhook.site → trigger pipeline → verify event received |
| I | i18n consistency | Walkthrough all pages in zh-CN/en — catalog hardcoded strings |

**P3 — De-prioritize:**
- J. Alternative deploy targets — verify render.yaml syntax valid only.

### 3.5 Layer 4 — E2E Automated Regression (3-4 days)

Playwright scripts for 6 critical user journeys:

| # | Journey | Steps |
|---|---------|-------|
| 1 | Admin: tenant + key lifecycle | Login → create tenant → create key → copy key → verify in list |
| 2 | S1 Product Direct (auto) | Input product info → auto pipeline → wait for completion → download video |
| 3 | S5 Brand VLOG | Select brand + models → run pipeline → verify output |
| 4 | Fast Mode | Input text → generate → verify video appears |
| 5 | Footage browsing | Open /footage → switch categories → click preview → verify modal |
| 6 | Admin: error visibility | Trigger a pipeline error → navigate to admin logs → verify error appears |

**Execution:** Headless Chromium in CI. Run on every deploy gate.

### 3.6 Negative Testing (Fault Injection)

| Scenario | Method | Expected Behavior |
|----------|--------|-------------------|
| DeepSeek timeout (> 120s) | Mock LLM client with delay | Pipeline retries → degrades → returns structured error |
| POYO content rejection | Mock 400 response | Sanitizer retries → falls back to alternate prompt |
| DB connection pool exhaustion | Acquire all 10 connections | New request queues → 503 after timeout |
| Concurrent state writes | Two pipelines write same state | No corruption, last-write-wins with timestamp |

### Phase 2 Exit Criteria

- [ ] Frontend test files ≥ 30 (from 2)
- [ ] 6 P0/P1 untested paths verified end-to-end
- [ ] E2E regression suite: 6 journeys, all green
- [ ] Backend line coverage > 70%, branch coverage > 50%
- [ ] Admin module test coverage ≥ 60%
- [ ] 4 negative test scenarios verified

---

## 4. Phase 3: Operations Readiness

**Duration:** Week 2-3 (overlaps with Phase 2)
**Goal:** From "it runs" to "it runs reliably, and someone knows when it breaks."

### 4.1 Monitoring — Metrics Expansion (6 → 12+)

**New Prometheus metrics to add:**

| Metric Name | Type | Description |
|-------------|------|-------------|
| `pipeline_active_gauge` | Gauge | Currently running pipelines |
| `llm_api_errors_total` | Counter | LLM API errors by provider (deepseek/poyo/siliconflow) |
| `llm_api_duration_seconds` | Histogram | LLM API call latency by provider |
| `db_pool_available_connections` | Gauge | Database connection pool water level |
| `admin_login_attempts_total` | Counter | Admin login attempts (success/fail) |
| `tenant_active_count` | Gauge | Active tenant count |

All added to `src/telemetry_prometheus.py`, exposed at `/telemetry/prometheus`.

### 4.2 Grafana Dashboard

3-panel minimal dashboard (JSON file, version-controlled at `deploy/grafana/dashboards/`):

1. **Service Health** — 5 status cards (PG/DeepSeek/POYO/SiliconFlow/Remotion), color-coded, with latency
2. **Pipeline Overview** — 24h run volume, success rate, error distribution by scenario/error_code
3. **Tenant Overview** — Active count, API call volume top 10, error-affected tenants

### 4.3 Alerting Rules (4 core rules)

| Alert | Condition | Severity | Notification |
|-------|-----------|----------|-------------|
| Pipeline failure rate spike | > 30% failure in 15 min window | P0 | DingTalk webhook |
| LLM API unavailable | 3 consecutive health check failures | P0 | DingTalk webhook |
| DB connection pool exhausted | Available connections < 2 for 5 min | P1 | DingTalk webhook |
| Disk space low | Output directory > 80% | P2 | Log only |

**DingTalk integration:** AlertManager → webhook → DingTalk bot. Webhook URL configured via `DINGTALK_WEBHOOK_URL` env var.

### 4.4 Logging Architecture

**Current:** structlog → stdout → Docker logs (ephemeral) + `error_logs` table (30-day retention).

**Phase 3 enhancements:**
- Add `audit_logs` table for business events (tenant created, key generated, key revoked, pipeline completed)
- Docker daemon log rotation: `max-size=100m, max-file=3` (prevents disk fill)
- `error_logs` retention already configurable via `ADMIN_LOG_RETENTION_DAYS`

### 4.5 Backup Strategy

| Target | Method | Frequency | Retention |
|--------|--------|-----------|-----------|
| PostgreSQL | `pg_dump` → `/backups/` → rsync | Daily 03:00 | 7 days |
| Output assets | `rsync` (existing scripts) | Manual / on-demand | — |
| `.env.prod` | Manual backup | After each change | Permanent |

**Backup script:** `scripts/backup_db.sh`
**Recovery drill:** Monthly restore to staging environment, verify pipeline runs.

### 4.6 Runbook (5 Incident Playbooks)

| # | Incident | Location |
|---|----------|----------|
| 1 | DeepSeek API timeout/unavailable | `docs/guide/runbook/01-deepseek-outage.md` |
| 2 | POYO content moderation rejection | `docs/guide/runbook/02-poyo-rejection.md` |
| 3 | Pipeline stuck in "running" state | `docs/guide/runbook/03-pipeline-stuck.md` |
| 4 | Database connection pool exhausted | `docs/guide/runbook/04-db-pool-exhausted.md` |
| 5 | Nginx config not taking effect | `docs/guide/runbook/05-nginx-config.md` |

Each runbook: ≤ 300 words, covers symptoms → diagnosis → mitigation → recovery verification.

### Phase 3 Exit Criteria

- [ ] Prometheus metrics ≥ 12 (from 6)
- [ ] 4 alert rules configured and tested (triggered at least once)
- [ ] Grafana dashboard shows live data
- [ ] Backup script + cron configured; 1 successful full backup executed
- [ ] 5 runbooks written and verified (someone followed the steps successfully)

---

## 5. Phase 4: Continuous Delivery & Methodology

**Duration:** Week 3 (1 week)
**Goal:** From "can deploy" to "repeatable delivery pipeline" + reusable methodology.

### 5.1 CI/CD Pipeline

```
Git Push → GitHub Actions
              ├── ruff lint          ── 2 min
              ├── pyright typecheck  ── 1 min
              ├── pytest (3.11+3.12) ── 5 min
              ├── vitest (frontend)  ── 3 min
              ├── docker build       ── 4 min
              └── deploy (manual)    ── 3 min
                   ↑ Requires Approval in GitHub Environments
```

- CI (lint + typecheck + test): automatic on every push, blocks merge on failure
- CD (deploy): manual gate via GitHub Environment protection — operator clicks Approve
- Deploy uses SSH action to run `deploy/lighthouse/deploy.sh` on the production host

### 5.2 Documentation System

| Document | Content | Location |
|----------|---------|----------|
| Deployment guide | 10-step Lighthouse deploy from scratch | `docs/guide/deploy-lighthouse.md` |
| ADR #1: Dual runtime strategy | Why LangGraph + StepRunner coexist | `docs/architecture/adr/001-dual-runtime.md` |
| ADR #2: Two-layer auth | Why admin session ≠ API key | `docs/architecture/adr/002-two-layer-auth.md` |
| ADR #3: DB strategy | Why PG-first with SQLite fallback | `docs/architecture/adr/003-db-strategy.md` |
| Runbook (5 playbooks) | Incident response procedures | `docs/guide/runbook/*.md` |
| Contributing guide | New developer onboarding in 30 min | `CONTRIBUTING.md` |

### 5.3 AI Development Workflow Methodology (Reusable Artifacts)

Three files that capture the entire workflow for reuse on future projects:

**File 1: `docs/methodology/ai-dev-workflow.md`**

7-stage methodology document:
1. Requirement Clarification (brainstorming → spec → user approval)
2. Technical Design (spec template, ADR template)
3. Development Execution (planning-with-files → phased development → isolated integration)
4. Code Review (checklist: route prefixes, auth boundaries, concurrency safety, memory leaks)
5. Test Closure (test pyramid template, untested-path checklist)
6. Production Operations (deploy guide template, runbook template)
7. Continuous Improvement (audit dimension checklist, tech debt registry template)

**File 2: `docs/methodology/phase-gate-checklist.md`**

Operational checklist for each phase gate. Example:
```
Phase 1 Exit:
- [ ] Audit report complete with P0-P3 classification
- [ ] P0 items resolved (0 remaining)
- [ ] P1 items resolved (0 remaining)
- [ ] P2/P3 items registered in backlog
- [ ] ≥ 2 new ADRs written
```

**File 3: `docs/methodology/spec-template.md`**

Standardized spec document template based on this project's spec structure. Sections: Overview, Auth Model, Feature Modules, API Design, Data Model, Data Flows, Security, Testing Strategy, Implementation Sequence, Open Decisions, Revision History.

### Phase 4 Exit Criteria

- [ ] CI/CD pipeline: push → auto lint + typecheck + test → manual approve → deploy
- [ ] 7 documentation files complete
- [ ] 3 methodology templates complete
- [ ] Full workflow verified: Admin Panel Phase 1 is the first case study

---

## 6. Timeline & Sequencing

```
Week 1         Week 2         Week 3         Week 4
├──────────────┼──────────────┼──────────────┼──────────────┤
│ Phase 1      │              │              │              │
│ Arch Audit   │              │              │              │
├──────────────┼──────────────┼──────────────┤              │
│ Phase 2 — Test Closure                     │              │
│ ├ Layer 1: Unit tests    │              │              │
│ ├ Layer 2: Frontend tests│              │              │
│ ├────────── Layer 3: Integration tests ──┤              │
│ ├────────────────── Layer 4: E2E ────────┤              │
├──────────────┼──────────────┼──────────────┤              │
│              │ Phase 3 — Ops Readiness    │              │
│              │ ├ Monitoring  │            │              │
│              │ ├ Alerts      │            │              │
│              │ ├── Backup/Runbook ────────┤              │
├──────────────┼──────────────┼──────────────┼──────────────┤
│              │              │ Phase 4 — CD + Methodology │
│              │              │ ├ CI/CD      │              │
│              │              │ ├ Docs       │              │
│              │              │ ├──────── Methodology ─────┤
└──────────────┴──────────────┴──────────────┴──────────────┘
```

Parallel opportunities:
- Phase 1 (audit) and Phase 2 Layer 1 (unit tests) can run simultaneously
- Phase 2 Layer 3-4 and Phase 3 can overlap — tests run while monitoring is set up
- Phase 4 is the lightest phase and can start as soon as Phase 3 mid-point is reached

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| External API rate limits block testing | Medium | Low | Use mock mode for bulk tests, real API for smoke tests only |
| Production DB migration fails | Low | High | Test migration on staging first; have rollback plan |
| Phase 2 scope too large for timeline | Medium | Medium | Strict priority ordering; P2/P3 items can slip to post-launch |
| New tests break existing functionality | Low | Medium | Run full regression on every commit; fix before proceeding |

---

## 8. Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Frontend test files | 2 | ≥ 30 |
| Backend line coverage | ~55% (est.) | > 70% |
| Untested interaction paths | 10 | 0 (all verified) |
| E2E regression journeys | 0 | 6 |
| Prometheus metrics | 6 | ≥ 12 |
| Alert rules | 0 | 4 (tested) |
| Runbook playbooks | 0 | 5 |
| CI/CD automated steps | 3 (lint+typecheck+test) | 5 (+frontend test + docker build) |
| Documentation files | ~5 (existing) | ≥ 12 |
| ADR records | 0 | ≥ 3 |
| Methodology templates | 0 | 3 |

---

## 9. Revision History

| Date | Change |
|------|--------|
| 2026-05-07 | Initial draft — 4-phase Production Readiness Framework |
