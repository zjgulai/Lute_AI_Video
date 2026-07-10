---
title: P1/P2 Production Readiness Acceptance 2026-07-10
doc_type: workflow
module: project
topic: p1-p2-production-readiness
status: stable
created: 2026-07-10
updated: 2026-07-10
owner: self
source: human+ai
---

# P1/P2 Production Readiness Acceptance

## Decision Target

Determine whether the current P1/P2 branch is safe to merge and deploy to the canonical Tencent Lighthouse target with token smoke disabled.

This record does not authorize or claim provider generation, publish, delivery acceptance, approved brand-token writes, or a real production deploy.

## Current Verdict

`deploy_ready_after_merge`: implementation, final local gates, deploy dry-run, production read-only checks, and the initial PR #67 check suite pass. The only remaining repository-state gate is merging the current green PR head and verifying synchronized `main`.

Maximum current evidence is `L3-production-read-only`. Production is unchanged, `provider_call=false`, `scenario_submit=false`, `fast_submit=false`, `publish=false`, and `delivery_acceptance=false`.

## Evidence Boundary

- Local unit/integration/UI/build and deployment dry-run: `L2-fixture-or-dry-run`.
- Production health/route/container/log inspection: `L3-production-read-only`.
- Provider generation, publish, delivery acceptance, and production mutation: `L4-authorized-live` only, outside this deploy-readiness decision.

## Reconciled P1/P2 Inventory

| Item | Deploy-readiness state | Remaining boundary |
|---|---|---|
| yt-dlp / faster-whisper / Quality ML | Covered by dependency, health, fallback, and CPU-only image contracts | Real model-quality evaluation is operational evidence |
| Human Review branches | Hermetic approve/reject/changes-requested coverage complete | Live branch smoke is L4-only |
| S3/S4/S5 Gate mapping | Backend definitions, frontend sequence tests, and Chromium direct-route checks complete | Real candidate generation/approval is L4-only |
| Metrics active-post source | Source and dry-run contracts complete | A real published active post is required for live pull |
| S4 uploaded footage | Path/url/asset identity is preserved into `@material` prompt references | Uploaded video frames are not final-video conditioning; that is a separate feature |
| Degradation chain | Fault injection, telemetry, persistence, and fail-fast routing covered | Production fault injection is optional L4 evidence |
| Distribution/Publish | Human acceptance gate and mock connector flow covered | Real TikTok/Shopify publish remains blocked |
| Webhook | Injected receiver, timeout, and failure isolation covered | External receiver send remains blocked |
| API-key isolation | Bounded concurrent request/tenant context tests covered | Deployed load pressure is optional operations evidence |
| Critical-view i18n | GatePanel, DistributionView, and InsightReport English assertions covered | Production read-only walkthrough remains L3 evidence |
| CloudBase / Render | Retained as non-canonical references | Lighthouse remains the only release target |
| quality_score feedback | Keyframe pilot implemented and documented | Seedance/Remotion consumers remain out of pilot |
| HU-02 desktop notification | Permission request now requires an explicit Bell-button user gesture; mocked dispatch covered | OS notification display requires manual browser acceptance |
| HU-03 script quality | Objective rubric retained | Brand voice and creative quality require manual reviewer judgment |

## HU-03 Manual Rubric

Review one representative script before a provider-enabled production run:

- Hook establishes tension or benefit within the first 3 seconds.
- At least two product USPs are concrete and non-duplicative.
- Brand voice is consistent with the selected brand package.
- CTA is explicit, platform-appropriate, and does not make unsupported claims.
- Reviewer records `pass`, `revise`, or `reject` with a short reason.

An agent or fixture review can validate structure, but it is not customer acceptance and must not be reported as such.

## Acceptance Gates

Current gate state:

- [x] Focused backend/frontend tests pass: backend `132 passed, 1 deselected`; component Vitest `22/22`; Gate Chromium `5/5`.
- [x] Final full backend and frontend gates passed: backend `2048 passed, 10 skipped, 12 deselected`; frontend `59` files / `255` tests plus lint, typecheck, and Next production build.
- [x] UI-only Playwright passed `14/14` across desktop and mobile.
- [x] Rendering clean install, TypeScript compile, production dependency dry-run, Docker image build, and container `/health` passed. The local image reports Remotion `4.0.451`, ffmpeg and Chromium available.
- [x] Docker Compose and deployment shell syntax checks passed.
- [x] Lighthouse `DRY_RUN=1` completed with `RUN_TOKEN_SMOKE=0` and `REBUILD_RENDERING=1`. The first preview exposed three remote `*.candidate` deletions; the exclude contract was fixed and the second preview contained zero deletion entries.
- [x] Production read-only checks passed: 12 routes returned `200`; `/api/health` reported PostgreSQL and media/rendering dependencies healthy; backend/frontend/rendering/nginx were running with restart count `0`; `nginx -t` passed; the observation window had zero 5xx, generation submit, provider submit, publish, or delivery-acceptance events.
- [x] Final full local gates were rerun after document and deploy-guard edits; `git diff --check` and the changed-file secret scan also passed.
- [x] PR #67 initial head checks passed: Python 3.11, Python 3.12, Ruff, frontend quality, Docker build, docs links, and UI-only visual regression.
- [ ] The current PR head must remain green at merge time; merge and `main == origin/main` verification are recorded in GitHub and the execution closeout rather than back-written into this pre-deploy artifact.

## Production Deployment Plan

The first production deployment after merge must use the canonical Lighthouse lane:

1. Record the pre-deploy `origin/main` SHA and run the production backup procedure from `scripts/backup_production.sh`; retain the created backup directory.
2. From a clean, synchronized `main`, rerun `DRY_RUN=1 RUN_TOKEN_SMOKE=0 REBUILD_BACKEND=0 REBUILD_RENDERING=1 deploy/lighthouse/build-and-deploy.sh` and reject any unexpected delete entry.
3. Run the same wrapper with `DRY_RUN=0`; keep `RUN_TOKEN_SMOKE=0` and `REBUILD_RENDERING=1` because `rendering/Dockerfile` and its lockfile changed.
4. Require `deploy/lighthouse/deploy.sh` health checks and `smoke.sh` to pass before declaring deployment complete.
5. Run the production post-deploy read-only checklist and observe container restart counts and 5xx/provider-submit logs.

Rollback trigger: any failed image build, unhealthy container, failed nginx validation, persistent 5xx, or unexpected provider/publish activity. Stop token/provider work, restore the pre-deploy source SHA through the same dry-run-first sync lane, rebuild rendering, and use the recorded database/media backup only if state restoration is actually required.
