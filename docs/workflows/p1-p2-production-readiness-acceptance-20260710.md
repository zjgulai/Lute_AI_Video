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

`deployment_pending_plugin_hub_exclude_merge`: PR #70 merged the schema-archive remediation as part of current `main` (`5bf22c4` behind merge `8447fec`). Authorized production operations then produced backup `2026-07-10_112359` with PostgreSQL 18 schema artifacts, 12 logical tables / 185 rows, 1617 media files, no partial directory, and `restore_verified=passed`. Sanitized tenant metadata also showed the incident replacement key active and the affected legacy key revoked. The current local Lighthouse rsync guard adds `deploy/lighthouse/plugin-hub.htpasswd` to the shared exclude boundary; it is tested and dry-run verified but remains uncommitted, so a clean-main dry-run must be rerun after that change is merged before any real deploy.

Maximum current evidence is mixed: repository work and the rsync preview remain `L2-fixture-or-dry-run`, read-only inspection is `L3-production-read-only`, and the cron migration, complete backup creation, schema probe, key rotation, and isolated restore are `L4-authorized-live` operations. Production application containers were not deployed or restarted; `provider_call=false`, `scenario_submit=false`, `fast_submit=false`, `publish=false`, and `delivery_acceptance=false`. The schema-backed restore and key-rotation blockers are closed; the remaining gate is merge plus clean-main dry-run of the rsync sidecar exclusion change.

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
| Tenant key lifecycle | Admin detail uses the current `description` schema; create requests persist explicit expiry or a 90-day default | Suspected production key rotation/revoke remains L4-only |
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
- [x] PR #67 remained green, merged as `5985c5cd1eee8ccd4f1dd53790c6d8112563cd3b`, and local `main == origin/main` was verified clean.
- [x] Backup/security remediation local gates passed: focused `29/29`; Ruff plus full backend `2065 passed, 10 skipped, 12 deselected`; frontend `60` files / `256` tests, ESLint, TypeScript, and Next production build.
- [x] Disposable PostgreSQL 16 created all `12/12` logical-backup tables and completed a six-row dump -> truncate -> restore round-trip for UUID, TIMESTAMP, TIMESTAMPTZ, JSONB, INET, and Admin FK data.
- [x] Independent security and critic audits were cross-checked; the accepted fresh-schema, restore, cron, retention, Admin expiry, and DR ordering findings were fixed and locally reverified.
- [x] PR #68 passed Python 3.11/3.12, Ruff, frontend quality, Docker build, docs links, and UI-only visual regression; it merged as `c05ac4ecb41034bc9d2b45cdfb974a9cb3a243e8`, and synchronized clean `main` was verified.
- [x] The root cron now invokes the root-owned runtime backup through `/bin/bash`, with exactly one marked AI Video entry and unrelated cron content preserved.
- [x] Backup `2026-07-10_161607` passed 12-table/185-row data validation plus full rehash of all 1617 media files; no partial directory remained. This backup does not satisfy restore acceptance because it predates schema-archive capture.
- [x] Restore diagnosis verified production PostgreSQL 18.4, the remote 7-table fresh-init drift, the live 12-table schema, and a secret-safe `postgres:18` custom schema archive probe containing all required tables.
- [x] The current candidate restore wrapper completed a real PostgreSQL 18 isolated restore on the production host with exact parity for all 12 tables / 185 rows; production database writes, application restarts, and provider calls remained false. This is candidate validation, not a new complete scheduled backup recovery point.
- [x] The suspected tenant key is replaced and revoked with sanitized evidence; no historical plaintext is used for verification.
- [x] The schema-archive remediation passes review/CI, merges, is minimally synced, and produces a new backup containing digest-pinned `pg_schema.dump`, `pg_schema.list`, matching before/after column signatures, and manifest checksums.
- [x] The new schema-backed backup completes an isolated restore drill with exact row-count parity for all 12 tables.

## Production Deployment Plan

The first production deployment after the new blockers close must use the canonical Lighthouse lane:

1. Completed: PR #68 merged the backup/security remediation as `c05ac4ecb41034bc9d2b45cdfb974a9cb3a243e8`.
2. Completed for the PR #68 version: backup tools were minimally synced, the root cron was migrated, and the pre-change files/crontab were retained without application restart.
3. Completed: PR #70 merged the backup tools; backup `2026-07-10_112359` contains the PostgreSQL 18 schema/data artifacts, media checksums, and a passed isolated restore marker.
4. Completed: sanitized production metadata confirmed the incident replacement key active and the affected legacy key revoked.
5. Pending after the rsync guard change merges: from a clean synchronized `main`, rerun `DRY_RUN=1 RUN_TOKEN_SMOKE=0 REBUILD_BACKEND=0 REBUILD_RENDERING=1 deploy/lighthouse/build-and-deploy.sh` and reject any unexpected delete entry.
6. Run the same wrapper with `DRY_RUN=0`; keep `RUN_TOKEN_SMOKE=0` and `REBUILD_RENDERING=1`.
7. Require deploy health checks, no-token smoke, the post-deploy read-only checklist, stable restart counts, and a clean provider/publish log gate before declaring deployment complete.

Rollback trigger: any failed image build, unhealthy container, failed nginx validation, persistent 5xx, or unexpected provider/publish activity. Stop token/provider work, restore the pre-deploy source SHA through the same dry-run-first sync lane, rebuild rendering, and use the recorded database/media backup only if state restoration is actually required.
