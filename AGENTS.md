# AI Video Pipeline — Project Guide for Codex

## Overview

**Short Video Agent** (v0.2.7) is a multi-agent AI video creation pipeline for cross-border e-commerce. It automates the full content production workflow: strategy → script → compliance → storyboard → asset sourcing → media generation → edit → audio → caption → thumbnail → distribution → analytics.

The pipeline is built on **LangGraph** with 16 nodes (12 worker + 4 self-audit) and 4 human-in-the-loop review checkpoints. It targets maternal/baby product categories (wearable breast pumps, feeding appliances) with 5 content scenarios.

**Current status (2026-07-11, app version 2.0.0):** Production is live at `https://video.lute-tlz-dddd.top` (Let's Encrypt cert, canonical) on Tencent Lighthouse. The IP endpoint remains a self-signed fallback, and the apex routes to this project or the separate VOC service. The deployed no-token application layer and production read-only health/routes have acceptance evidence. Fast Mode and S1-S5 also have historical no-media or bounded single-submit evidence, but this does not prove enterprise full-chain final assembly, human acceptance, publish/delivery, transparency compliance, or active-post metrics. Production token smoke remains an exact-authorization path and must not be unlocked as a whole suite.

**Active closure program (2026-07-11):** Before changing business behavior, read `docs/superpowers/specs/2026-07-11-enterprise-ai-content-all-scenarios-closure-design.md`, `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`, and the current wave plan under `docs/superpowers/plans/`. The program covers enterprise AI text, image, audio, and video across Fast Mode and S1-S5. Its order is risk-first: tenant/media and provider-cost safety, runtime/data correctness, operations/DR, transparency, then separately authorized all-scenario L4/L5 acceptance.

**Wave 1A local closure (2026-07-12):** Canonical async `/fast/submit` and `/scenario/{scenario}/submit` require tenant-scoped `Idempotency-Key` and use the durable `idempotency_records` ledger plus authenticated readback. Browser ambiguous recovery reuses the same key and never auto-sends a second POST; stale nonterminal work becomes `recovery_required` and is not automatically resumed. This is local/disposable-PG18 evidence only: production has not been migrated or deployed for this change.

**W2-05–W2-08 local closure and W2-09 local boundary (2026-07-22):** Production database startup is PostgreSQL-only and fail-fast; SQLite fallback requires exact development/test opt-in. `/health/live` is process-only, while `/health/ready` and legacy health share current-schema required-table plus single-Alembic-head truth and never migrate. Empty PostgreSQL 18 uses guarded baseline+atomic stamp only after rejecting existing app tables or lineage; historical databases use the reviewed Alembic gate, whose command failures are stable and secret-free. Fresh, old-lineage, historical, idempotent upgrade, HTTP readiness, cleanup, full backend, and independent six-dimension review are green locally (`PASS / APPROVE`, `accepted_actionable_findings=0`). W2-09 remote CI and any new-code deployment remain blocked while GitHub updates are forbidden; production is unchanged.

**W2-10–W2-13 local closure (2026-07-22):** Scenario audit arrays now survive machine contract, filesystem/SQLite/PostgreSQL persistence, async terminal snapshot, and live/durable status readback; one shared validator rejects malformed present values without PG-to-FS fallback. Quality feedback uses a persisted two-attempt rewind envelope, stops the dispatching resume, blocks direct consumer run/regenerate before a new regeneration epoch, derives attempts only from durable server state, and writes the new epoch plus complete rewind in its first durable save; malformed upstream/attempt fails closed. Active DeepSeek/PoYo image/video/SiliconFlow adapters resolve concurrent request-scoped keys without constructor-time transport, while retained ElevenLabs paid routing remains blocked. Independent review pass 1 found four issues; the main thread fixed all with crash/stale-signal/invalid-upstream/corrupt-backend tests, and the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Fresh post-fix local evidence is focused `329 passed`, real guarded PG18 `5 passed`, hermetic S1-S5 `283 passed`, backend `4103 passed`, target Pyright `0 errors`, and Ruff/docs/diff/secret scan green. Production, providers, GitHub, publish, and delivery are unchanged.

**W2-14–W2-17 local closure (2026-07-22):** Live/durable scenario status exposes canonical step order and minimal gate statuses; StageProgress completes only from coherent server terminal truth. Gate resume is scenario-correct, performs one approval mutation, retries by read-only status only, and fails closed on exception, stagnation, timeout, failure states, null cursor, or any contradiction in the complete nine-field lifecycle envelope. S5 requires exactly six ordered product views across upload/library/drop/Enter/Space and preserves partial successes plus filter-hidden library choices. Review/completion layouts are responsive, global focus/reduced-motion contracts are present, and critical admin tables, empty/detail/status/dialog/error/ARIA strings are bilingual without surfacing backend English for login 401/422. Independent review required three passes: four initial findings and one remaining terminal-conservation finding were fixed; the same read-only reviewer returned `PASS / APPROVE`, `accepted_actionable_findings=0`. Fresh local evidence is frontend `69 files / 433 tests`, backend `4103 passed`, affected backend `133 passed`, UI-only mobile Playwright `2 passed`, ESLint/TypeScript/OpenAPI/32-route build, Ruff/docs/diff/secret scans green. Three pre-existing `scenario.py` Pyright diagnostics remain assigned to W3-03 and do not touch Batch D lines. Production, providers, GitHub, publish, and delivery are unchanged.

**W1-22 local closure (2026-07-12):** Authenticated `artifact:accept|all` reviewers can create/read/revoke tenant-bound acceptance records for exact canonical Fast/S1-S5 final-video bytes. Accepted records are expiring and internally single-use; there is no HTTP consume route or new review UI. Disposable PostgreSQL 18, focused/full backend, frontend build, recovery/OpenAPI governance, and independent review are green. Production remains unmigrated/undeployed; W1-23 must wire internal consume into distribution before publish can trust an acceptance ID.

**W1-23 local closure (2026-07-13):** Canonical `POST /distribution/publish` and deprecated `POST /publish/{video_id}` now require `artifact:publish|all`, accept one server-side acceptance ID for one platform, and use the same durable publish-attempt service. The service performs no-network readiness, creates audit evidence, consumes the exact W1-22 acceptance once, revalidates the artifact, invokes at most one connector, and never automatically retries or restores consumed authority. Read `docs/superpowers/specs/2026-07-12-publish-acceptance-consumption-design.md`, `docs/superpowers/plans/2026-07-12-publish-acceptance-consumption.md`, and `docs/runbooks/publish-acceptance-consumption.md` before extending publish behavior. Production remains unmigrated/undeployed and no real publish was run; at that checkpoint W1-24/W1-25 plus W1-26 live publish were still pending, with their current states recorded below.

**W1-24 local closure (2026-07-21):** TikTok/Shopify publish and distribution status reuse strict credential validators, contain no runtime mock fallback, require exact `simulated` truth, and separate deterministic rejection from ambiguous external outcome. `PublishAttemptService` preserves W1-23 single-use/no-retry authority; W1-25 later superseded external status lookup with durable receipt readback. Read `docs/superpowers/specs/2026-07-14-publish-connector-truth-design.md`, `docs/superpowers/plans/2026-07-14-publish-connector-truth.md`, and `docs/runbooks/publish-connector-truth.md` before extending this behavior. A later independent six-dimension review found five source type-contract groups; the main thread fixed them without suppression and the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Fresh evidence is source-only Pyright `0 errors`, focused `580 passed`, Ruff/docs/diff clean. At that review checkpoint the prior W1-24 business behavior was deployed provider-off at production SHA `95c2d0460ccb1566b7a612cee3592cebb3439cef`, while the follow-up type-contract fixes were not yet production evidence; their later release status must be verified against current Git/main/runtime. No credentialed real connector/status call or live publish succeeded; W1-26 remains separate. Two early fixture-only RED network escapes led to the permanent test client-construction guard.

**W1-25 local closure (2026-07-14):** Canonical publish requests now require strict platform-specific options; TikTok follows Content Posting API v2 Direct Post and Shopify follows Admin GraphQL `2026-07` staged VIDEO upload, exact Product GID association, and readback. A read-only preflight occurs before acceptance consume, and every new `published` attempt requires one strict durable `publish-receipt.v1`; tenant-bound attempt readback and legacy receipt-only TikTok status perform no external call. Runtime configuration is default-off and uses only `TIKTOK_ACCESS_TOKEN` or `SHOPIFY_ACCESS_TOKEN` with canonical flags. Read `docs/superpowers/specs/2026-07-14-publish-receipt-protocol-calibration-design.md`, `docs/superpowers/plans/2026-07-14-publish-receipt-protocol-calibration.md`, and `docs/runbooks/publish-receipt-protocol-calibration.md` before changing publish protocols. A later independent Codex review completed with `accepted_actionable_findings=0`; its two frontend suggestions were rejected because acceptance/publish UI is explicitly deferred and one acceptance authorizes only one platform. The status is `completed_local` with `independent_review=true`; `production unchanged`, `provider_call=false`, `provider_attempt_made=false`, `real_connector_call=false`, `external_status_call=false`, `live_publish=false`, and `database_write=local-test-only`. W1-26 real publish/reconciliation remains separately blocked.

**W1-27–W1-30 Task 5 local closure (2026-07-17):** DeepSeek paid LLM mutation now uses only the exact `deepseek-v4-flash`/`deepseek-v4-pro` catalog rules at `https://api.deepseek.com`, reserves the frozen `995904` input plus `4096` output envelope, performs one network mutation with `max_retries=0`, validates all five usage facts and both conservation equations, and settles the durable ledger before returning content. Stable operation keys are separated from bounded server-owned operation instances; trusted workflow regeneration epochs authorize a new ordinal, persist `regeneration_epoch_ref`, and cannot be reused for a second ordinal in the same account + logical-operation slot without blocking legitimate cross-slot fan-out. Script-class Gate generation/regeneration and candidate scoring use the same persisted epoch, so identical prompts receive a new ordinal only under a new epoch while same-epoch replay stays read-only; media/non-ledger Gate paths remain blocked. Active script/storyboard/strategy/remix/gate/candidate/translation/LLMSkill callsites now provide bounded slots and re-raise accounting/outcome contract errors; unsupported aliases/providers fail before SDK construction. Read `docs/runbooks/provider-cost-ledger-per-job-budget.md` and `docs/superpowers/plans/2026-07-15-provider-cost-ledger-per-job-budget.md` before extending this lane. Fresh local/disposable evidence and the same-thread independent review are green (`independent_review=true`): `production unchanged`, `provider_call=false`, `provider_attempt_made=false`, `database_write=local-test-only`, `live_publish=false`, `live_send=false`, `billing_reconciliation=false`.

**W1-27–W1-30 Task 6 local closure (2026-07-17):** SiliconFlow CosyVoice TTS accepts only `FunAudioLLM/CosyVoice2-0.5B`, `https://api.siliconflow.com/v1`, and `siliconflow_global_usd`; it freezes the final provider input as strict UTF-8 bytes, stores only digest/byte facts, reserves and starts one tenant/job-bound attempt, performs one speech POST, settles before artifact staging/probing, and preserves `ambiguous` or `provider_cost_artifact_failed` truth without silent fallback. Missing-key fallback is explicitly pre-submit and zero-attempt. Request-scoped SiliconFlow routing blocks legacy ElevenLabs/PoYo paid paths before client construction; S1/S3/S4/S5 use bounded server-owned operation slots; cleanup failures cannot mask provider outcomes; logs contain stable codes/counts rather than raw text, exceptions, or absolute paths. Fresh fixture/static evidence and the same-thread independent six-dimension review are green (`PASS / APPROVE`, `independent_review=true`): Task6 TTS `21 passed`, provider-cost/context regression `90 passed`, Fast fallback/metadata `2 passed, 11 deselected`, target Pyright `0 errors`, Ruff/compile/diff clean. Native pytest remains blocked by the known macOS `dyld` asyncpg/codec environment issue; no provider, production, external network, or real-database action occurred. Read the provider-cost runbook and approved plan before starting Task 7.

**W1-31 live attempt (2026-07-19):** The exact PoYo `gpt-image-2` low/1K one-image runner binds a `$0.01` hard cap, dual-human/funded evidence, credential presence-only preflight, a canonical durable one-shot marker, the provider-cost SQLite ledger, and three-way official/provider/ledger comparison. Local implementation and six-dimension review passed first. The later exact live packet passed preflight and consumed its authority for exactly one mutation; PoYo returned HTTP `403 Forbidden`, the runner returned `provider_cost_outcome_ambiguous` without retry, and read-only restart evidence shows one ambiguous attempt with `$0.01` reserved, zero settled, no external task ID, and no provider charge fact. Read `docs/superpowers/specs/2026-07-18-w1-31-provider-billing-reconciliation-design.md`, `docs/superpowers/plans/2026-07-18-w1-31-provider-billing-reconciliation.md`, and `docs/runbooks/provider-cost-ledger-per-job-budget.md` before any follow-up. Current checkpoint is `live_attempt_consumed / provider_outcome_ambiguous / reconciliation_failed`: `provider_attempt_made=true`, `billing_reconciliation=false`, `invoice_reconciliation=false`, `production unchanged`. Never claim zero charge, reuse this authority, or retry automatically; any repaired live attempt needs fresh exact authorization and dual-human evidence.

**W1-27–W1-30 Tasks 7–9 local closure (2026-07-18):** PoYo GPT Image 2/Seedance 2 async accounting, legacy/admin paid-path blocking, process-local tracker retirement, and Fast/S1–S5/Gate/regenerate/restart route-wide context closure now use the same tenant/job-bound durable ledger, finite server-owned operation slots, trusted regeneration epochs, no-media/bounded terminal truth, and no provider fallback. The Task 9 independent review returned `PASS / APPROVE` with `accepted_actionable_findings=0`; fresh expanded provider-cost/Task9 evidence is `763 passed, 2 deselected`, the hermetic S1–S5 entrypoint is `280 passed`, target Pyright is `0 errors`, and Ruff/compile/diff are clean. Production, providers, billing, deploy, and Git remain unchanged.

**W1-27–W1-30 Task 10 local closure (2026-07-18):** The full local/disposable verification lane covers the provider/idempotency/generation regression, SQLite parity and restart, 16-table backup/restore, disposable PostgreSQL 18 migration lifecycle and 20-way repository checks, hermetic entrypoint, backend CI, frontend/OpenAPI, catalog/log/secret scans, and synchronized runbooks. Fresh evidence is provider `311 passed`, affected regression `467 passed`, SQLite/backup/Alembic `76 passed, 2 deselected`, backup/restore `24 passed`, PG18 `2 passed`, hermetic `280 passed`, final backend `3883 passed, 9 skipped, 16 deselected, 1 warning`, frontend `67 files/390 tests` plus lint/typecheck/OpenAPI/build, target Pyright `0 errors`, and recovery/document governance `3 passed`/`31 passed`. Independent read-only six-dimension review returned `PASS / APPROVE` with `accepted_actionable_findings=0`; W1-27–W1-30 is `completed_local / independent_review=true`. All evidence is local/fixture/disposable only (`production unchanged`, `provider_call=false`, `provider_attempt_made=false`, `database_write=local-test-only`, `billing_reconciliation=false`); no provider, production, deploy, or Git side effect occurred.

**Provider-off production release closure (2026-07-21):** PR #90 produced exact `main` SHA `95c2d0460ccb1566b7a612cee3592cebb3439cef`. GitHub provenance, preflight, three SHA-tagged image builds/runtime smokes, SBOM/scans and exact release bundle passed; the GitHub restricted remote dry-run failed closed because its Environment has no SSH secrets, so that workflow did not deploy. A separately pinned local SSH canonical dry-run and authorized maintenance-window deployment then passed with verified backup/isolated restore, additive Alembic migration, immutable-image rollout and independent L3 HTTP/browser acceptance. Shared nginx and `portal_auth` remained online. Provider generation, token smoke, publish and delivery stayed disabled and unexecuted. GitHub deployment automation remains externally blocked: `production-read-only-dry-run` has no secrets/protection rules and `production` does not yet exist.

**Clean-clone documentation boundary (2026-07-20):** Tracked roadmap, specifications, plans, and runbooks are the release SSOT. Ignored agent-local execution journals are optional, non-authoritative traces and are never prerequisites for build, test, review, migration, deploy, or rollback.

**W3 E1 local closure (2026-07-22):** CPython `3.12.13`, `pyproject.toml + uv.lock`, locked backend entrypoints, production-source Pyright zero, non-refreshable test/suppression/config ratchets, and blocking pip/npm/Trivy/Grype High+Critical gates are locally closed. The exact final image and expiring scanner exceptions are recorded in `docs/runbooks/vulnerability-scan-exceptions.md`; extensible IMA ADPCM is rejected before FFmpeg. Final backend evidence is `4122 passed`, and the same independent six-dimension reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. GitHub/Dependabot and production deployment remain separate external evidence layers; Batch E2 W3-05-W3-07 is next.

**W3 E2/E3 local closure (2026-07-22):** Repository-owned provider-off monitoring contracts, fixed-digest Prometheus/Alertmanager validation, durable completion metrics, exact dynamic PostgreSQL restore sets, canonical source/backup manifests, and a provider-neutral create-only off-host protocol are locally closed. Final E3 evidence is recovery `71 passed`, disposable PostgreSQL 18 exact dump/restore/parity `1 passed`, full backend `4198 passed`, scoped Pyright `0 errors`, and same-thread independent six-dimension review `PASS / APPROVE` with `accepted_actionable_findings=0`. W3-08 real notifications, W3-12 real object store/KMS, W3-13 host-loss recovery, W3-17 GitHub remote dry-run, and any production deployment remain separate external gates.

**W4 F1 local closure (2026-07-22):** Strict hash-only `transparency-record.v1` / `transparency-sidecar.v1`, scoped artifact identity and no-clobber sidecar publication, and the current pinned `c2pa-python==0.36.0` Signer/Builder/Reader adapter are locally closed. Required signing fails closed; local draft remains `unsigned_pending_review`; a local fixture certificate may produce only `signed_local_readback`, never trusted or independently validated truth. Independent review found and the main thread fixed three Medium timestamp/provider/path findings; same-thread re-verification returned `PASS / APPROVE` with `accepted_actionable_findings=0`. F2/F3 later closed locally; W4-06/W4-07/W4-08 remain external.

**W4 F2 local closure (2026-07-23):** Fast and all canonical S1–S5 producer steps append hash-only provenance, including explicit simulated records for skipped/missing media; regeneration, human edits, and Gate approval extend immutable chains. One server-owned boundary snapshots real media immutably and signs/rebinds image/video outputs when required. `transparency` survives strict filesystem/SQLite/PostgreSQL persistence; S2 external references remain pending source inputs rather than fabricated completed producers. `acceptance-create.v2` binds exact sidecar digest and final `signed_local_readback`; publish inspect/consume revalidate artifact bytes, sidecar truth, and Reader output. Legacy v1 remains readable/revocable/replayable but cannot authorize publish. Independent review round 1 found four issues; reverification found one filesystem normalization gap; the main thread fixed all five and the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Final evidence is backend `4261 passed`, frontend `69 files / 433 tests`, disposable PG18 `7 passed`, source Pyright `0 errors`, and lint/type/OpenAPI/build green. Production/providers/publish/delivery remain unchanged; F3 later closed locally.

**W4 F3 local closure (2026-07-23):** Authenticated tenant-bound transparency inspect/package routes expose strict sidecar, human-edit, source-reference, and local Reader truth; Fast plus S1–S5 result/completion UI always shows the AI-generated label and withholds package download when identity/integrity is unavailable. Acceptance v2 binds transparency and server-owned TikTok/Shopify metadata adds visible AI disclosure before authority consume; inspect/consume drift cannot reach a connector. ADR/runbooks distinguish C2PA as the project engineering choice from legal compliance and independent validation. Independent review found one High validate-to-package TOCTOU; the main thread replaced path rereads with a frozen exact validated-byte snapshot, and the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Final evidence is backend `4273 passed`, frontend `71 files / 438 tests`, UI-only desktop/mobile `4 passed`, reviewer backend `459 passed`, source Pyright `0 errors`, and lint/type/OpenAPI/build/docs/diff/secret gates green. Production, providers, publish, delivery, and GitHub remain unchanged; W4-06/W4-07/W4-08 remain external.

**W5-01–W5-03 local closure (2026-07-23):** Fast plus S1–S5 now have a strict provider-off acceptance contract, deterministic single-submit L4 draft-plan generator, and immutable HU-03 plus scenario-specific human-review records. Drafts bind exact tenant/sample/time/budget/job-cap/step/gate/stop-condition truth but remain `draft_pending_human_review`, do not bind a runtime execution profile, and keep execution/provider/publish/delivery authority false. Independent review round 1 found one High, two Medium, and one Low issue; the main thread added clean-environment, duplicate/unknown JSON cap, half-open review-window, and filesystem-error RED tests, fixed all four, and the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Final main-thread evidence is clean-environment focused `61 passed`, expanded `402 passed`, full backend `4334 passed, 9 skipped, 22 deselected`, source Pyright `0 errors`, and Ruff/ratchet/diff/secret gates green. Evidence is L2 local/fixture/static only; production, providers, publish, delivery, GitHub, stage, and commit remain unchanged. W5-04 Fast live acceptance is the next external gate and requires fresh exact bounded authorization.

**W5-04 readiness local closure (2026-07-23):** One strict private Fast activation record can now be validated against the exact canonical W5 draft, including tenant/sample/plan, USD-nanos budget, finite provider job caps, optional media, exact single-submit/no-retry/pending-review statements, and half-open UTC validity. The provider-off readiness CLI uses the current clock, bounded strict JSON, regular-file-only nonblocking reads, stable path/error normalization, and never grants provider/execution/publish/delivery authority or creates runtime/provider-cost/consume state. Independent review required three passes: the main thread fixed unbounded/non-regular reads, unsafe path failures, and deeply nested JSON recursion escapes; the same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Final evidence is focused `111 passed`, expanded `213 passed`, full backend `4376 passed, 9 skipped, 22 deselected`, source Pyright `0 errors`, and Ruff/ratchet/diff/secret/index gates green. Evidence remains L2 local/fixture/static only; W5-04 live Fast submission is still `blocked_external`, and production/providers/publish/delivery/GitHub/stage/commit are unchanged.

**W5-04 runtime-binding local closure (2026-07-23):** One private `w5-fast-runtime-binding.v1` now binds the complete canonical activation digest, exact credential-free Fast request fingerprint, one raw idempotency-key digest, pending-review/retry-zero policy, fixed DeepSeek/PoYo model envelope, budget, and provider job caps. A new owner atomically consumes the tenant-scoped activation in the durable idempotency insert and initializes the provider-cost account from the provider-neutral plan cap; same-key exact replay is resolved from durable truth before current private files are loaded, so packet removal, rotation, or expiry cannot submit again or break readback. Independent review round 1 found one High, two Medium, and one Low issue; the main thread fixed activation-content substitution, runtime LLM drift, packet-dependent replay, and floating retry JSON with exact RED/GREEN coverage. The same reviewer returned `PASS / APPROVE` with `accepted_actionable_findings=0`. Final evidence is focused `243 passed`, independent expanded `351 passed`, full backend `4400 passed, 9 skipped, 23 deselected`, disposable PG18 bootstrap `6 passed, 1 deselected` plus concurrency `1 passed`, source Pyright `0 errors`, and Ruff/ratchet/diff/secret/index gates green. This is still local/provider-off readiness only: no live W5-04 submit, production migration/deploy, provider, publish, delivery, GitHub, stage, commit, or push occurred.

**Recent releases (v0.2.0 → v0.2.7):** Tier-2 submit-lock + 422/429 error rendering, Tier-3 3 ADRs + 4 runbooks + DEFAULT_LLM_PROVIDER SSOT, HU-05 cardCopyEn 100-string zh→en, Creation Guide 5-tab redesign, Brand Kit tab API wiring (137 momcozy product images now visible), product metadata API (title/price/source URL), `/api/portfolio/brand-presets` endpoint, deploy.sh Phase 0.5 defensive chmod. **2026-05-17 v0.2.5**: ADR-004 Accepted Option D (`S3_VIRAL_EXTRACT_DISABLED=1` default — closes S3 KOL viral extraction by policy), `/health` `media_tools` observability for yt-dlp/whisper/clip availability, transformers+torch+Pillow added to image (~600MB) for `src/quality/clip_alignment.py`, frontend eslint sweep (~245 → ~30 errors via `any → unknown`). **2026-05-17 v0.2.6**: ADR-005 Accepted (poster extraction at every video producer + portfolio router backstop, `src/tools/poster_extractor.py`); /works and /library video thumbnails now reach 100% coverage in production (verified 86/86 final_works); `/api/assets/` nginx burst raised 20→100 to fix 429 on `/library?tab=influencers` after consecutive tab switches; new `docs/runbooks/thumbnail-missing.md`. **2026-05-17 v0.2.7**: ADR-006 Accepted (C2PA Content Credentials for AI-generated videos, EU AI Act 2026-08-02 deadline); S5 `vlog_strategy` `'str' object has no attribute 'get'` bug fix (`selected_models` schema tolerance: str/dict/empty all valid input now); 4 new prod Playwright specs (38 tests across user-journey/s1-gate/i18n/error-paths) + `.github/workflows/e2e-prod.yml` CI; `docs/runbooks/key-rotation.md` precise leak audit (POYO_API_KEY only — DEEPSEEK/SILICONFLOW/API_KEY history-clean); 3 user-action runbooks (c2pa-cert-application / phase1-signoff-checklist / github-deploy-secrets-setup); `CLAUDE.md` SSOT divergence section pruned. **2026-05-31 deployment hardening**: commits `306b86f`, `95c2925`, `d62a3ac` deployed to Lighthouse; `deploy.sh` and `smoke.sh` now skip `/api/fast/generate` unless `RUN_TOKEN_SMOKE=1`; `/works` includes S4 `live_shoot` filtering.

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
│  src/api.py  (FastAPI, Python 3.12.13, Port 8001)        │
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
├── requirements.txt            # Generated compatibility export; not install SSOT
├── uv.lock                     # Canonical Python dependency lock
├── .python-version             # Canonical CPython runtime pin
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
Video:           poyo.ai Seedance 2  https://api.poyo.ai   (model: seedance-2, 15s + native audio + multi-shot; default since 2026-05-14)
                 or Seedance 2.0    https://api.seedance.ai
TTS:             SiliconFlow CosyVoice https://api.siliconflow.com/v1
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
  All sources aligned (2026-05-17): `src/config.py:117` fallback = `deepseek`,
  `render.yaml:25` = `deepseek`, `deploy/tencent-cloudbase.md:59` = `deepseek`,
  `deploy/CLOUDBASE_STEP_BY_STEP.md:67` = `deepseek`. Stale `kimi` / `anthropic`
  references in `drafts/` and `docs/research/` are historical research notes only —
  do not align them, they're not used by any code path.

---

## Database

**Production:** Tencent RDS PostgreSQL 18.4 (read-only verified 2026-07-10) via asyncpg
connection pool (min 1, max 10 connections). Backup schema capture must use the matching
official `postgres:18` client image; `pg_dump` rejects a PostgreSQL 16 client against this
server. Local Docker Compose may still use PostgreSQL 16 for development fixtures.

**Development fallback:** SQLite at `output/ai_video.db`.

**Tables:**
- `threads` — pipeline run threads (id, thread_id, state JSON, current_step)
- `pipeline_states` — scenario pipeline states (label, config, steps JSON, mode)
- `brand_packages` — brand guidelines + assets
- `influencers` — influencer profiles
- `publish_logs` — multi-platform publish history
- `video_metrics` — performance metrics; both Alembic migration `1efc41794d64`
  (2026-05-01) and `src/storage/migrations/001_init.sql` (inlined 2026-05-17) create
  the PG table, so a fresh `docker compose up` lands a complete schema without
  requiring `alembic upgrade head`. Repository (`metrics_repository.py`) is PG-first
  with SQLite fallback — both paths are exercised in tests.

**Migrations:** Alembic in `migrations/`. Docker Compose auto-loads SQL from `src/storage/migrations/`.
For disaster recovery, use the backup's `pg_schema.dump`; the live database contains
historical column types that are not reproduced exactly by the current fresh-init SQL.

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
uv sync --locked --extra dev
uv run --locked uvicorn src.api:app --reload --port 8001

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

1. **Tencent Lighthouse (canonical)** — current production at `https://video.lute-tlz-dddd.top`
   (Let's Encrypt cert, SAN: `lute-tlz-dddd.top, video.lute-tlz-dddd.top, voc.lute-tlz-dddd.top`,
   auto-renew via certbot.timer + deploy-hook). IP `https://101.34.52.232` is the self-signed
   fallback for IP-direct access. The apex `https://lute-tlz-dddd.top` serves a static
   landing page (deploy/lighthouse/landing/index.html) routing to video.lute / voc.lute.
   `deploy/lighthouse/` contains the legacy remote compose plus the tracked immutable
   `docker-compose.release.yml` (backend + frontend + rendering only), `nginx.conf`
   (shared legacy topology), `ai_video_locations.conf` (the only reviewed AI Video routing
   snippet), and `.env.prod` (live secrets — gitignored). Shared nginx and `portal_auth`
   are preserved and only the AI Video snippet is validated/reloaded. Deploy from the local
   clean synchronized `main` with `SSH_KEY=/path/to/ai_video.pem DRY_RUN=1 deploy/lighthouse/build-and-deploy.sh`
   first, then explicitly set `DRY_RUN=0` and bind `RELEASE_SOURCE_SHA` to the reviewed
   `git rev-parse HEAD`. The wrapper defaults to dry-run and rejects dirty/non-main/stale source.
   `deploy/lighthouse/rsync-excludes.txt` is the safe sync SSOT. Canonical deploy is
   permanently provider-off (`RUN_TOKEN_SMOKE=0`, `RUN_DEPLOY_SMOKE=0`); any later real
   generation test must use a separate exact-authorization harness and is not a deploy flag.
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

**CI:** GitHub Actions on push/PR to main — locked CPython 3.12.13 environment, Ruff,
production-source Pyright plus test-diagnostic ratchet, pytest/coverage, dependency audits,
frontend gates, and a locally loaded Critical image scan. `pyproject.toml` plus `uv.lock` are
the dependency authority; `requirements.txt` is generated compatibility output only.

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

Last updated: **2026-07-10** (after stale TODO reconciliation for local-only
quality evidence; comprehensive debt audit baseline remains 2026-06-09 — 221
findings, 33+ remediation tasks completed across config, LLM URL centralization,
step_utils dedup, deploy.sh modernization, nginx security headers, frontend i18n
fixes, except Exception reduction, docs archiving, and standard project files).

### ✅ Resolved since 2026-05-03 baseline

- ~~**Configuration divergence**~~ — Fixed in `4bf096b` (v0.2.1). `src/config.py:115`
  marked as SSOT with comment naming the 4 mirror files; `render.yaml` + `.env.prod` +
  `deploy/CLOUDBASE_STEP_BY_STEP.md` + `deploy/tencent-cloudbase.md` all aligned on
  `deepseek`.
- ~~**Redis/Celery legacy reference**~~ — Verified 2026-05-11: no `import redis` /
  `import celery` anywhere in `src/` or `tests/`, not in `requirements.txt`. AGENTS.md
  line 616 corrected. Was stale since at least 2026-04.
- ~~**Long pipeline UX (HTTP timeout)**~~ — Unified async submit + `/status` polling
  shipped 2026-05-08; nginx 1500s timeout now a safety net only.
- ~~**S2-S5 gate system gap**~~ — `gate_manager.py` per-scenario configuration + 52
  `test_gate_scenario_configs.py` tests + `_build_skill_params` support for
  remix_script / vlog_strategy (2026-05-08). Real-API-key E2E for S3-S5 Gate still
  not run in production (kept in "untested paths" below).
- ~~**admin.py 0600 permission bug**~~ — `5c4d192` (2026-05-11) added `--chmod=F644,D755`
  to all rsync SOPs + Phase 0.5 defensive chmod in `deploy.sh`. Prevents the 502
  PermissionError that bit deploy #1 of Tier-3.
- ~~**Frontend submit-lock (GAP-A)**~~ — `db89079` (v0.2.1) wired `useSubmitting` into
  5 entry points (handleStart / startSmartCreate / FastModePanel / AssetUploader /
  SettingsPanel test connection). Prevents double-click duplicate LLM billing.
- ~~**Frontend 422 inline form error (GAP-B)**~~ — `db89079` + `74f5310` — `FormField` /
  `aria-invalid` threaded into `GuidedCard`, Pydantic loc path auto-mapped to field
  keys.
- ~~**Frontend 422/429 parser (GAP-C)**~~ — `db89079`. `ApiError` class +
  `parseApiError` wired into 4 core helpers. 429 shows `(retry in Ns)` inline.
- ~~**HU-05 card-copy i18n**~~ — `4bf096b` (v0.2.2). `cardCopyEn.ts` 100-string map +
  `GuidedCard` / `CardConnector` use `tCardCopy` at render time. Previously
  `GUIDED_CARD_SEQUENCES` zh-only.
- ~~**Brand assets ingestion gap**~~ — `2238a84` → `74f5310` → `7daadc1` (v0.2.2-v0.2.4).
  BrandKitTab now fetches `/api/portfolio/?kind=brand_kit`; PortfolioFile exposes
  `product_title` / `product_price` / `product_source_url` / `product_description` from
  LRU-cached `info.json`; new `GET /api/portfolio/brand-presets?brand=<brand>`
  endpoint; `QuickTemplate` merges API presets over bundled demo data; refresh script +
  cron runbook. 137 scraped momcozy images now fully wired end-to-end.
- ~~**Missing ADRs / Runbooks**~~ — `4bf096b` added 3 ADRs (dual-runtime / two-layer-auth /
  db-strategy) + 4 runbooks (deepseek-timeout / poyo-rejection / pipeline-stuck /
  db-pool-exhausted). `7daadc1` added brand-assets-refresh runbook. ADR-005 +
  `thumbnail-missing.md` runbook added 2026-05-17 (v0.2.6) alongside the
  poster-extraction refactor. All under `docs/architecture/adr/` and `docs/runbooks/`.
- ~~**Creation Guide UX monolith**~~ — `c52cad8` (v0.2.2) extracted to 5-tab
  `CreationGuide.tsx`; adds Frontend/Backend/Runbooks tabs that didn't exist before.
- ~~**/works and /library video cards show black tile**~~ — fixed 2026-05-17 (v0.2.6,
  ADR-005). `portfolio_hook.rebuild_portfolio_listener` was the only producer of
  `output/thumbnails/portfolio_posters/*.jpg`, fired only on the LangGraph
  `pipeline.completed` webhook. Fast-mode runs and ad-hoc seedance/remotion calls
  never fired that event, so every video produced outside the full pipeline rendered
  as a black `<FilmSlate>` placeholder. New shared helper `src/tools/poster_extractor.py`
  is called inline at every producer (`seedance_video_generate`, `remotion_assemble`,
  `services/fast_mode.py`) plus a router-level backstop in
  `_thumbnail_path_for` that synthesizes a poster on first scan when one is missing.
  Verified 86/86 final_works coverage in production.
- ~~**429 on `/library?tab=influencers` after consecutive tab switches**~~ — fixed
  2026-05-17 (v0.2.6). nginx `/api/assets/` location had `burst=20` while the
  equivalent `/api/portfolio/` listing path had `burst=100`. Library tab switching
  bursts both, exhausting the asset bucket. Raised to `burst=100` to match the sibling
  listing endpoint. Verified 30/30 rapid `GET /api/assets/influencers` return 200.
- ~~**`video_duration: "not-a-number"` accepted by backend**~~ — stale TODO
  reconciled 2026-07-10. `src/routers/_state.py::coerce_video_duration` now rejects
  garbage strings, bools, and unsupported types with field-level 422 details before
  scenario pipelines reach media steps; `tests/test_video_duration_coerce.py` covers
  `"not-a-number"`, numeric strings, clamping, bool, and list inputs. Evidence is
  local unit/lint/CI only; no production submit, provider call, or full media path was
  rerun for this reconciliation.
- ~~**HU-05 `SCENE_VIDEO_TYPES.desc` still Chinese**~~ — stale TODO reconciled
  2026-07-10. `GuidedForm` already renders video-type labels and descriptions through
  `videoType.*` / `videoTypeDesc.*` i18n keys, and EN translations exist for every
  current `SCENE_VIDEO_TYPES` entry. `web/src/components/GuidedForm.test.tsx` now
  locks the EN render path so the brand-campaign selector shows "Convey brand tone
  and values" instead of the Chinese fallback. Evidence is local frontend unit/lint/
  type/build only; no production route, provider call, or scenario submit was run.
- ~~**Frontend eslint 286 errors / CI does not gate frontend lint**~~ — stale TODO
  reconciled 2026-07-10. `.github/workflows/ci.yml` has a `Frontend quality gate`
  job that runs `npx eslint src e2e playwright.ui.config.ts playwright.prod.config.ts`,
  and `.github/workflows/deploy.yml` runs the same frontend lint in preflight. Local
  `npm run lint` also passes. Evidence is local workflow inspection plus frontend
  lint/type/test/build only; no production route, provider call, or deploy was run.

### 🟡 Still open — real technical debt

#### P0 (block next release if left)

None. The v0.2.6 release is clean.

#### P1 (do next sprint)

- **yt-dlp + openai-whisper not in backend image.** S3 KOL video-analysis skill runs
  in mock mode; real transcription requires adding the two packages (~2GB image growth
  for whisper+torch) to `Dockerfile.backend`. Decide image-size vs. feature-value
  trade-off before installing.
- **Untested path A (Human Review branch coverage).** Pipeline's `strategy_audit` /
  `script_audit` / `editing_audit` / `thumbnail_audit` score in `[0.60, 0.90)` triggers
  HITL. D10 `contextvars` routing override + `GatePanel` APPROVE / CHANGES_REQUESTED /
  REJECT branches have unit tests but no real-input production run. Need to lower
  thresholds on a disposable pipeline or craft a low-quality brief.
- **Untested path B (S3-S5 Gate E2E with real API key).** S1 has `test_gate_full_flow_e2e.py`;
  S3/S4/S5 only have mocked unit coverage. Needs a real key + manual run to validate
  front-end `CandidateSelector` state mapping for non-S1 scenarios.
- **Untested path D (Metrics full chain).** `/metrics/*` video-performance endpoints +
  `src/tasks/metrics_poller.py` poller + PG `video_metrics` table + front-end
  `PerformanceDashboard` — never verified end-to-end in production. Init SQL +
  Alembic are both in sync since 2026-05-17, but the poller/dashboard wire has no
  smoke test.
- **Untested path E.2 (Uploaded asset used in final video).** `test_upload_e2e.py`
  covers upload → disk → /api/files → /api/media round-trip. The "uploaded asset gets
  referenced by keyframe/seedance/remotion in the final video" loop is **not** verified.
- **Untested path G (degradation chain).** `pipeline_degraded=True` + `error_collector`
  FIFO + `/telemetry` visibility never exercised in production (all 5 scenarios went
  green). No mock-POYO-500 / mock-DeepSeek-timeout integration test.

#### P2 (nice-to-have)

- **POYO content-moderation coverage expansion.** `poyo_safety.py` now has 11+ rules
  but the universe of triggers is open-ended. Watch the structured `poyo_cm_rejection`
  log events in production and fold new triggers into `_REPLACEMENTS` + unit tests.
- **`api_assets.py` compat shim.** `/api/assets/*` still uses in-memory dicts for
  `_brand_packages` / `_influencers`. Frontend OpenAPI types reference these paths,
  so don't remove the router; do migrate any new asset features to
  `src/routers/assets.py` and/or `src/routers/portfolio.py` instead.
- **Untested path C (Distribution / Publish).** Requires real platform credentials
  (TikTok / Shopify). Mock-only tests today.
- **Untested path F (Webhook dispatch).** `WEBHOOK_URLS` left empty in prod since
  launch. Set `WEBHOOK_URLS` to a `webhook.site` test URL + run any scenario → verify
  `audit.completed` / `pipeline.completed` events arrive.
- **Untested path H (multi-tenant concurrency + API Key isolation).** `contextvars`
  isolation verified in single-request unit tests; never pressure-tested with
  concurrent requests from 2+ tenants using different API keys.
- **Untested path I (i18n walkthrough).** GatePanel / DistributionView / InsightReport
  manual walkthrough in EN mode to catch hardcoded-string leaks. `hu_acceptance.spec.ts`
  HU-05 covers `/` `/works` `/library` but not the three creator-flow pages.
- **Untested path J (alternative deploy targets).** `render.yaml` (overseas) +
  `deploy/tencent-cloudbase.md` (CloudBase) not verified since Lighthouse became
  canonical. Low priority unless someone needs to deploy to one of them.
- **Untested path K (Quality ML real-deps).** `src/quality/` lazy-imports
  transformers / torch / opencv / mediapipe / deepface / pyiqa / scenedetect.
  Production has `ffmpeg` only → `nr_quality.py` runs "skipped" branch. Deciding
  which ML dep to install is a ~600MB-2GB image-size call.
- **Untested path L (quality_score feedback loop).** Upstream skills emit
  `quality_score` / `_self_check`; downstream (`keyframe_images` / `seedance_clips` /
  `remotion_assemble`) do not read and regenerate on sub-threshold scores yet. Design
  exists, implementation doesn't.
- **HU-02 desktop notification + HU-03 script quality.** Left as manual-verify only
  (cannot automate in Playwright: permission gesture + subjective evaluation).

### 🔵 Architecture-level references

- **Remotion rendering integration:** `rendering:3001` HTTP service since 2026-05-02.
  Backend posts pipeline state JSON to `/assemble`.
- **pyright strict:** `reportUnknownMemberType` / `reportUnknownVariableType` not
  enabled. Noise far outweighs value while the codebase is `dict[str, Any]`-heavy.
  Revisit if typed data classes (`ProductCatalog`, `PipelineConfig`, etc.) are
  introduced.
- **LangGraph proxy layer (P4-4):** `/pipeline/*` proxies to StepRunner. State
  conversion is best-effort; some legacy fields may be dropped. Original LangGraph
  code kept as compat layer; proxy can be iteratively filled in if a caller needs
  a specific legacy field.

See also:
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md` — current enterprise-content closure program
- `docs/claude/known-gaps-stable.md` — current backlog plus append-only history
- `docs/claude/updates/project-updates-202605-stable.md` — historical release and remediation context
- `docs/runbooks/README.md` — 5 incident runbooks

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
