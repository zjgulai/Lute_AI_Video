---
title: Production E2E Token Smoke Runbook
doc_type: workflow
module: ci-cd
topic: production-e2e-token-smoke
status: stable
created: 2026-05-31
updated: 2026-06-13
owner: self
source: human+ai
---

# Production E2E Token Smoke Runbook

## Default Behavior

`.github/workflows/e2e-prod.yml` runs production Playwright checks against `https://video.lute-tlz-dddd.top`, but `web/playwright.prod.config.ts` skips `@token-smoke` tests by default.

Default production E2E must remain non-token:

- `run_token_smoke`: `false`
- `RUN_TOKEN_SMOKE`: `false`
- `@token-smoke`: skipped
- `PLAYWRIGHT_API_KEY`: authenticated production checks require a non-demo production key

If `PLAYWRIGHT_API_KEY` is missing or still equals `ai_video_demo_2026`, authenticated checks skip through `web/e2e/production/helpers.ts`. That result is not a production acceptance gate.

Historical baselines:

- `2026-06-07`: `50 passed, 2 skipped` with a real production API key and `RUN_TOKEN_SMOKE=0`.
- `2026-06-08`: `39 passed, 15 skipped` with no production key; authenticated checks skipped, so this is only a page-level smoke baseline.
- `2026-06-11`: `50 passed, 4 skipped` through `scripts/production_non_token_e2e_check.py --execute` with a non-demo `PLAYWRIGHT_API_KEY` and `RUN_TOKEN_SMOKE=0`. This is the current Phase C production non-token baseline. The `library-portfolio` L4B checks skipped because production currently has no `pending_review` `creation_intermediate` assets; that skip is not L4B acceptance.
- `2026-06-11`: L4A authorized-live provider smoke executed after exact user authorization. Evidence: `tmp/outputs/l4a-authorized-live-provider-smoke-20260611-152953.log`, `tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json`, and `tmp/outputs/pending-review-asset-packet-20260611.json`. Result: 3 poyo `gpt-image-2` images + 1 poyo `seedance-2` 15-second vertical video, all `pending_review`; no publish, no delivery acceptance, no approved brand token write.
- `2026-06-11`: L4B production read-only artifact verification passed after syncing the L4A assets into the tenant-scoped pending-review directory and deploying the portfolio scanner patch. Evidence: `tmp/outputs/l4b-production-readback-20260611-160827.json`; API result `pending_review_count=4`, `final_work_total=0`; Playwright `library-portfolio.prod.spec.ts` result `2 passed` with `RUN_TOKEN_SMOKE=0`.
- `2026-06-11`: L4C-1 Fast Mode minimal token smoke executed after a separate authorization and no-execute plan validation.
  Evidence: `tmp/outputs/l4c-fast-mode-token-smoke-summary-20260611-162852.json`.
  Runtime flags: `RUN_TOKEN_SMOKE=1`, `PLAYWRIGHT_PROD_WORKERS=1`, and `--retries=0`.
  Result: Playwright `fast-mode-submit.prod.spec.ts` returned `3 passed, 1 skipped`; provider tasks `YHUW7BP5TLUHMTC1` and `JPRCUUAFNJTK6MB6` completed with no submit retry observed.
  Boundary note: the spec contained two submit cases and Fast Mode wrote artifacts under `output/fast_mode`, so future L4C slices must enforce `max_submit_count=1` plus pending_review-only disposition or split the spec before execution.
- `2026-06-11`: L4C-1R single-submit guard first run executed one authorized backend submit through `fast-mode-single-submit.prod.spec.ts`. Evidence: `tmp/outputs/l4c-1r-fast-mode-single-submit-summary-20260611-170131.json`; result: `submit_count_observed=1`, poyo/Seedance video submit did not execute, task failed before video provider because `/app/output/tenants/default` was not writable by `appuser`. The production volume permission was fixed afterward without another submit.
- `2026-06-11`: L4C-1R retry after the volume-permission fix passed after a new explicit authorization.
  Evidence: `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json`.
  Runtime flags: `RUN_TOKEN_SMOKE=1`, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`, `--retries=0`, and `--workers=1`.
  Result: Playwright `fast-mode-single-submit.prod.spec.ts` returned `1 passed (8.8m)`. Production task `fast_1781169431_7e4af0b5` completed with poyo task `T17OTAHIXMPBNYXX`; filtered backend logs show one `poyo: submitting task`, one `poyo: task submitted`, and zero `poyo: retrying submit`.
  Boundary note: the artifact is `tenant_pending_review`, visible as `creation_intermediate` / `pending_review`, and absent from `final_work`. Actual provider charge must be checked in the provider console.
- `2026-06-11`: L4C-4 S1 no-media clean-log single-submit token smoke executed after a new explicit authorization. Evidence: `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-summary-20260611-230535.json`; Playwright `scenario-s1-no-media-single-submit.prod.spec.ts` result `1 passed (13.4s)` with one authorized submit. The 6-minute backend window showed DeepSeek text calls `2`, zero `api.poyo.ai`, zero `api.siliconflow.cn`, and zero execution-level poyo/Seedance/TTS/assemble/keyframe/gate-candidate logs. Strict clean-log still failed because 8 media skill registration lines contained Seedance/TTS/assemble/keyframe lexemes.
- `2026-06-12`: L4C-4R-prep S1 no-media logging/import hygiene sync passed after a separate explicit authorization. Evidence: `tmp/outputs/l4c-4r-prep-s1-logging-import-hygiene-sync-summary-20260612-000910.json`; only `src/pipeline/__init__.py` and `src/pipeline/s1_product_pipeline.py` were synced, remote originals were backed up under `/opt/ai-video/backups/l4c4r-prep-s1-logging-20260612-000910/`, backend was restarted, `/api/health` returned `ok`, local/remote/container hashes matched, and the 370-second no-submit backend window showed zero `/scenario` submit, zero DeepSeek/poyo/SiliconFlow external HTTP, and zero poyo/Seedance/TTS/assemble/keyframe/gate-candidate/media-skill-registration logs.
- `2026-06-12`: L4C-4R S1 no-media clean-log after-import-hygiene single-submit token smoke passed after a separate explicit authorization. Evidence: `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-summary-20260612-001.json`; Playwright `scenario-s1-no-media-single-submit.prod.spec.ts` result `1 passed (11.7s)` with one spec-observed submit and zero retries. Production label `s1_1781229202_7b5148d1`; 370-second backend window showed DeepSeek text calls `2`, zero `api.poyo.ai`, zero `api.siliconflow.cn`, zero poyo submit, zero Seedance/TTS/assemble/keyframe/gate-candidate logs, and zero media skill registration logs.
- `2026-06-12`: L4C-5 S2 no-media clean-log single-submit token smoke passed after a separate explicit authorization. Evidence: `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-summary-20260612-002.json`; Playwright `scenario-s2-no-media-single-submit.prod.spec.ts` result `1 passed (7.2s)` with one spec-observed submit and zero retries. Production label `s2_momcozy_1781230204`; 370-second backend window showed DeepSeek text calls `2`, zero `api.poyo.ai`, zero `api.siliconflow.cn`, zero poyo submit, zero Seedance/TTS/assemble/keyframe/gate-candidate logs, and zero media skill registration logs.
- `2026-06-12`: L4C-6 S3 no-media clean-log single-submit token smoke passed after prep sync. Playwright `scenario-s3-no-media-single-submit.prod.spec.ts` result `1 passed (23.5s)` with one spec-observed submit and zero retries. The 370-second backend window showed DeepSeek text calls only, zero `api.poyo.ai`, zero `api.siliconflow.cn`, zero poyo submit, zero Seedance/TTS/assemble/keyframe/gate-candidate logs, and zero media skill registration logs.
- `2026-06-12`: L4C-7 S4 no-media clean-log single-submit token smoke passed after prep sync. Playwright `scenario-s4-no-media-single-submit.prod.spec.ts` result `1 passed (7.1s)` with one spec-observed submit and zero retries. Backend showed `POST /scenario/s4 -> 200` and one DeepSeek text call; poyo/SiliconFlow/media forbidden counts were all `0`.
- `2026-06-12`: L4C-8R S5 no-media after-timeout-fix single-submit token smoke passed after prep sync and a local test-timeout harness fix. The first L4C-8 submit timed out at Playwright's 30-second test limit while backend returned 200 with forbidden counts `0`; after `test.setTimeout(120_000)` and a fresh authorization, Playwright `scenario-s5-no-media-single-submit.prod.spec.ts` passed in `33.0s`. Backend showed `POST /scenario/s5 -> 200 (32456ms)`, one DeepSeek text call, and zero poyo/SiliconFlow/media forbidden counts. No third submit was made.
- `2026-06-12`: L4D-2 poyo Seedance video-only single-job media smoke passed after separate explicit authorization. Evidence: `tmp/outputs/l4d-2-video-only-dry-run-20260612-155828.json`, `tmp/outputs/l4d-2-video-only-execute-20260612-155843.json`, `tmp/outputs/l4d-2-video-only-production-sync-20260612-160657.json`, and `tmp/outputs/l4d-2-video-only-production-readback-20260612-160805.json`. Result: exactly one `seedance-2` video job, `image_job_count=0`, `video_job_count=1`, poyo task `7J9FKRVT4FGC4EQH`, output `tenants/momcozy-marketing/pending_review/l4d_video_only_20260612160601/seedance_video.mp4`, size `2474327` bytes, SHA-256 `ebadde1a4385cb8394fd1f2f4a3a169af7102a73818d638a8d24b94904f98a91`; production `/api/portfolio` shows `pending_review` / `creation_intermediate` / `tenant_id=momcozy-marketing`, with matching `final_work` count `0`. No image generation, TTS, assemble, keyframe, gate candidate, publish, delivery acceptance, or approved brand token write occurred.
- `2026-06-12`: L4D-3 poyo image+Seedance paired single-chain media smoke passed after separate explicit authorization. Evidence: `tmp/outputs/l4d-3-paired-dry-run-20260612-161851.json`, `tmp/outputs/l4d-3-paired-execute-20260612-161905.json`, `tmp/outputs/l4d-3-paired-production-sync-20260612-162913.json`, and `tmp/outputs/l4d-3-paired-production-readback-20260612-163016.json`. Result: exactly one `gpt-image-2` image job and one `seedance-2` video job, `image_job_count=1`, `video_job_count=1`, poyo image task `DEBMWQB3WRE6LNBF`, video task `JQB119K0BWYO4360`; outputs `tenants/momcozy-marketing/pending_review/l4d_paired_20260612162837/paired_image.png` (`1667434` bytes, SHA-256 `695c8c0cca9d487c7877d67fab4c530f7cf1823a6b0597ee78beb6417f5cbba9`) and `paired_video.mp4` (`2298916` bytes, SHA-256 `8e953fa9c95c6d1e1b5d84082f634860e3f5ea5fd4a5227b455bb343f79fea9f`). Production `/api/portfolio` shows both assets as `pending_review` / `creation_intermediate` / `tenant_id=momcozy-marketing`, with matching `final_work` counts `0`. No TTS, assemble, keyframe, gate candidate, scenario full media, publish, delivery acceptance, or approved brand token write occurred.
- `2026-06-12`: L4D-4 frontend/library read-only pending_review readback passed after separate explicit authorization.
  Evidence: `tmp/outputs/l4d-4-library-readonly-playwright-20260612-163739.log` and `tmp/outputs/l4d-4-library-readonly-summary-20260612-163833.json`.
  Runtime flags: `RUN_TOKEN_SMOKE=0`, `--retries=0`, and `--workers=1`.
  Result: only `web/e2e/production/library-portfolio.prod.spec.ts` was listed and run; Playwright returned `3 passed (10.3s)`. The spec verified L4D-2 video and L4D-3 image/video exact paths in `pending_review` / `creation_intermediate`, verified matching `final_work` count `0`, and verified `/library?tab=materials` renders pending-review cards without non-GET API calls.
  Boundary note: the backend log window from `2026-06-12T08:37:35Z` had forbidden counts all `0`: provider submit, poyo, Seedance, TTS, assemble, keyframe, gate candidate, publish, and delivery acceptance.
- `2026-06-13`: L4D-5W-R2 frontend/library endpoint-clean read-only regression passed after separate explicit authorization. Evidence: `tmp/debug/l4d5wr2-live-playwright-20260613050712.log`, `tmp/debug/l4d5wr2-live-summary-20260613050712.json`, and `tmp/debug/l4d5wr2-refined-log-gate-20260613050712.json`. Result: only `web/e2e/production/library-portfolio.prod.spec.ts` ran, Playwright `3 passed`, `RUN_TOKEN_SMOKE=0`, `--retries=0`, and `--workers=1`; backend log showed only `/portfolio/` GETs. The temporary non-demo production key for tenant `momcozy-marketing` was revoked and post-revoke authentication returned `401`. The formal log gate is now `scripts/production_readonly_log_gate.py`; it allows local health noise (`127.0.0.1 /health`, `rendering:3001/health`) but continues to fail external health/admin/media requests, scenario/Fast submit, provider, publish, delivery, and approved brand token logs.
- `2026-06-12`: L4D-5-prep S2 bounded media pilot spec/readiness passed without provider or submit.
  Evidence: `tmp/outputs/l4d-5-prep-s2-bounded-media-list-20260612.log`, `tmp/outputs/l4d-5-prep-s2-bounded-media-readiness-playwright-20260612.log`, and `tmp/outputs/l4d-5-prep-s2-bounded-media-readiness-summary-20260612.json`.
  Runtime flags: `RUN_TOKEN_SMOKE=0`, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, and `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`.
  Result: only `web/e2e/production/scenario-s2-bounded-media-pilot-readiness.prod.spec.ts` was listed, `Total: 1 test in 1 file`; the readiness test passed with only `GET /api/health` (`status=ok`).
  Boundary note: no `/api/scenario/s2` submit, provider call, publish, delivery acceptance, approved brand token write, or `final_work` write occurred. At that stage live `L4D-5` was intentionally blocked until S2 explicitly supported scenario-level `artifact_disposition=pending_review` plus a bounded media stop point before `final_work`; later `L4D-5-fix-prep` through `L4D-5Y` resolved and verified that boundary.
- `2026-06-12`: L4D-5-fix-prep S2 artifact disposition + bounded media isolation passed locally without provider or submit. Evidence: `tmp/outputs/l4d-5-fix-prep-s2-bounded-media-list-20260612.log`, `tmp/outputs/l4d-5-fix-prep-s2-bounded-media-readiness-playwright-20260612.log`, and `tmp/outputs/l4d-5-fix-prep-s2-bounded-media-readiness-summary-20260612.json`. Result: `S2BrandCampaignRequest` now accepts `artifact_disposition`, `/api/scenario/s2` passes it into `S2BrandCampaignPipeline`, and `artifact_disposition=pending_review|quarantine` runs a bounded S2 media pilot that stops after `seedance_clips`, sets `final_video_path=""`, and returns `delivery_accepted=false`, `publish_allowed=false`, `approved_brand_token_write=false`. Local tests passed: `tests/test_s2_e2e.py` 20 passed, router/shim tests 8 passed, readiness spec 1 passed, ruff/eslint/token guard/diff-check passed. This did not sync production backend files and did not run `/api/scenario/s2`.
- `2026-06-12`: L4D-5-fix-sync-prep S2 bounded media production sync + no-submit verification passed after separate explicit authorization. Evidence: `tmp/outputs/l4d-5-fix-sync-prep-summary-20260612-174020.json`, plus sync/import/log-window evidence referenced inside that summary. Result: only `src/routers/_state.py`, `src/routers/scenario.py`, and `src/pipeline/s2_brand_pipeline_v2.py` were synced; remote originals were backed up under `/opt/ai-video/backups/l4d5-fix-sync-prep-20260612-173119/`; backend was restarted; `/api/health` returned `ok` after a transient immediate 502 retry; local/remote/container hashes matched for all three files; container import smoke passed for `S2BrandCampaignRequest` and `S2_BOUNDED_MEDIA_STOP_STEP=seedance_clips`; the 370-second backend no-submit window had forbidden counts all `0`: `/scenario/s2`, poyo, SiliconFlow, Seedance, TTS, assemble, keyframe, gate candidate, `final_work`, publish, and approved brand token write. No provider call, scenario submit, Playwright live submit, publish, delivery acceptance, or approved brand token write occurred.
- `2026-06-13`: L4D-5X S2 keyframe cap/fallback isolation production sync and container no-provider contract smoke passed after separate explicit authorization. Evidence: `tmp/debug/l4d5x-final-summary-20260613133623.json` and `tmp/debug/l4d5x-post-sync-contract-summary-20260613135041.json`. Result: only `src/skills/keyframe_images.py` was synced; `/api/health`, hash verify, import/introspection, and 6-minute no-submit/provider log gate passed. Container contract smoke mocked `SkillRegistry.execute` and verified `_max_shots=1`, `provider_max_retries=0`, exactly one keyframe on normal and fallback paths, and no output-volume write from fallback.
- `2026-06-13`: L4D-5Y S2 bounded media keyframe-input verified provider smoke passed after separate explicit authorization. Evidence: `tmp/debug/l4d5y-final-summary-20260613132543.json`, `tmp/debug/l4d5y-live-playwright-20260613132543.log`, `tmp/debug/l4d5y-readback-20260613132543.json`, and `tmp/debug/l4d5y-provider-boundary-gate-20260613132543.json`. Result: only `web/e2e/production/scenario-s2-bounded-media-pilot-live.prod.spec.ts` ran, Playwright `1 passed (10.0m)`, one `/api/scenario/s2` submit, poyo submit count `2` total (`1` image job + `1` Seedance video job), provider/backend retry `0`, and artifact disposition `pending_review`. Label `l4d5s_s2_bounded_keyframe_20260613132543` produced one non-fallback keyframe and one Seedance clip under `tenants/momcozy-marketing/pending_review/...`; `final_work_match_count=0`; no fallback text-to-video, TTS, thumbnail, assemble, media_quality_audit, gate candidate, publish, delivery, approved brand token, provider error, or poyo retry occurred. The temporary production key was revoked and post-revoke auth returned `401`.
- `2026-06-13`: L4D-5Z frontend/library read-only portfolio regression for the L4D-5Y assets passed. Evidence: `tmp/debug/l4d5z-final-summary-20260613135315.json`, `tmp/debug/l4d5z-live-playwright-20260613135315.log`, and `tmp/debug/l4d5z-refined-log-gate-20260613135315.json`. Result: `library-portfolio.prod.spec.ts` is parameterized for bounded-media target labels; the run verified `l4d5s_s2_bounded_keyframe_20260613132543` video/keyframe visibility, poster cache as `thumbnail_path` only, and matching `final_work=0`. Backend log gate observed only `/portfolio/` GETs, non-GET count `0`, and forbidden hits `{}`. The temporary production key was revoked.

The current formal plan is `docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md`. First-wave real-provider E2E is not the full Playwright `@token-smoke` suite. It is split into:

- `L4A`: controlled provider smoke through `scripts/p2_recharge_smoke_checklist.py --execute`.
- `L4B`: frontend read-only artifact verification through `library-portfolio.prod.spec.ts` with `RUN_TOKEN_SMOKE=0`.
- `L4C`: production `@token-smoke` expansion, only by separately authorized slices. `L4C-1R` has the submit-count and artifact-disposition guard in code, and the authorized retry after the output-volume permission fix passed for the minimal Fast Mode single-submit path. `L4C-2` first failed/stopped and exposed the S2 no-media media-generation boundary bug; after root-cause fixes and prep syncs, `L4C-4R` through `L4C-8R` now cover S1-S5 no-media clean-log single-submit with DeepSeek text only and no poyo/Seedance/TTS/assemble/keyframe execution. Any third Fast Mode submit, S1-S5 media run, S1 gate run, or wider `L4C-2+` needs a new plan record and new explicit authorization.
- `L4D`: staged real media provider smoke. Image-only plus tenant readback (`L4D-1/L4D-4R-prep`), video-only (`L4D-2`), image+video paired chain (`L4D-3`), frontend/library read-only readback (`L4D-4`), S2 bounded-media implementation/sync/keyframe isolation (`L4D-5-fix-prep` through `L4D-5X`), S2 bounded media provider smoke (`L4D-5Y`), and frontend/library read-only regression (`L4D-5Z`) have passed. This only proves S2 bounded media through `seedance_clips`, not S2 full media/final assembly, S1/S3/S4/S5 media generation, publish, delivery acceptance, or approved brand token writes.

## Required Secret For Token Smoke

Configure this GitHub Actions repository secret only after recharge and after the POYO account is funded:

| Secret | Purpose |
|---|---|
| `PROD_DEMO_API_KEY` | Non-demo production API key used by `e2e-prod.yml`; the legacy name is misleading, but the value must not be `ai_video_demo_2026` |

The workflow intentionally fails if `run_token_smoke=true` while `PLAYWRIGHT_API_KEY` is still `ai_video_demo_2026`.

## Manual Run

Use GitHub UI for non-token production E2E:

1. Actions → `e2e-prod`
2. Run workflow
3. Set `base_url` to `https://video.lute-tlz-dddd.top`
4. Keep `run_token_smoke` as `false`
5. Review failures before retrying

Local equivalent:

```bash
.venv/bin/python scripts/production_non_token_e2e_check.py --json
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<non-demo-key> \
.venv/bin/python scripts/production_non_token_e2e_check.py --execute
```

The helper blocks missing/demo `PLAYWRIGHT_API_KEY`, blocks truthy `RUN_TOKEN_SMOKE`, and forces the Playwright child process to `RUN_TOKEN_SMOKE=0`.

## First-Wave Real Provider Path

Use this path only after recharge, after the user gives the exact live authorization, poyo is funded, private approval/account-readiness records exist, and private poyo payload JSON is available.

`L4A` controlled provider smoke:

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD=<private-account-readiness-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

`L4A` scope is fixed to the Momcozy sterilizer sample pack: 3 `gpt-image-2` images + 1 `seedance-2` 15-second vertical image-to-video. Automatic retries are `0`. Output must remain `pending_review`, with `delivery_accepted=false`, `publish_allowed=false`, and `approved_brand_token_write=false`.

After L4A, do not claim L4B until the generated assets are visible through production `/api/portfolio`. For tenant keys, place reviewed smoke artifacts under the tenant-scoped pending-review path:

```text
output/tenants/<tenant-id>/pending_review/momcozy_sterilizer_smoke_YYYYMMDD/
```

The portfolio router scans this tenant path and keeps top-level `output/pending_review/...` isolated to the default/test context. This avoids making pending-review assets globally visible across tenants.

`L4B` frontend read-only artifact verification:

```bash
cd web
RUN_TOKEN_SMOKE=0 \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<non-demo-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/library-portfolio.prod.spec.ts \
  --reporter=list,html
```

`L4B` may only perform read-only API calls. It verifies that `creation_intermediate` / `pending_review` assets are visible in `/library?tab=materials` and not promoted into `final_work`.
If no `pending_review` assets exist, the spec must skip rather than fail. That preserves Phase C as a non-token production baseline and keeps L4B blocked until fresh L4A evidence exists. The 2026-06-11 L4B run satisfied this condition with 4 pending-review assets and zero matching final-work assets.

After any production frontend/library read-only run, replay the captured backend log through the fixed read-only log gate:

```bash
python scripts/production_readonly_log_gate.py \
  --backend-log tmp/debug/<run>-backend.log \
  --summary tmp/debug/<run>-summary.json \
  --output tmp/debug/<run>-readonly-log-gate.json
```

The gate allows only portfolio readback plus local health-check noise. It must fail on external browser/proxy `/api/admin/auth/session`, `/api/health`, `/health`, `/api/media`, scenario/Fast submit, provider generation, publish, delivery, `final_work`, or approved brand token logs. Do not use the older raw `forbidden_endpoint_count` summary alone for endpoint-clean acceptance; classify the backend log by request source.

## L4D Real Media Provider Staging

Use `L4D` only after S1-S5 no-media clean-log baselines are already understood. `L4D` validates provider-backed media generation in isolation; it is not a shortcut to S1-S5 full media, gate, publish, delivery acceptance, or approved brand token writes.

| Stage | Scope | Submit ceiling | Default budget ceiling | Required evidence |
|---|---|---:|---:|---|
| `L4D-0` readiness gate | no provider call | 0 | `$0` | `/api/health=ok`, current hashes known, pending_review path writable, plan/approval/account readiness records ready |
| `L4D-1` image-only | one poyo `gpt-image-2` job | 1 | `$1.00` | executed once; `L4D-1R` diagnosed CDN access; `L4D-4R-prep` production readback passed under tenant `momcozy-marketing` |
| `L4D-2` video-only | one poyo `seedance-2` job | 1 | `$2.00` | passed: video artifact in tenant-scoped `pending_review`; no image/TTS/assemble/final_work |
| `L4D-3` image+video | one poyo image job plus one Seedance job | 2 total | `$3.00` | passed: generated image is the video input; both artifacts stay `pending_review` |
| `L4D-4` frontend readback | no new provider call | 0 | `$0` | passed: `/api/portfolio` and `/library?tab=materials` see artifacts as `creation_intermediate` / `pending_review`; matching `final_work` count is 0 |
| `L4D-5-prep` S2 bounded media readiness | no provider call | 0 | `$0` | passed: one S2 readiness spec listed and passed; it exposed the disposition/bounded-media blocker that later stages resolved |
| `L4D-5-fix-prep` S2 bounded media implementation | no provider call | 0 | `$0` | passed locally: S2 accepts artifact disposition and stops at `seedance_clips` before `final_work` |
| `L4D-5-fix-sync-prep` production sync | no provider call | 0 | `$0` | passed: three backend files synced; hash/import/health/no-submit log window verified |
| `L4D-5-post-sync-readiness` S2 bounded media readiness | no provider call | 0 | `$0` | passed: single spec readiness/list path stayed no-submit/no-provider |
| `L4D-5X` keyframe cap/fallback isolation | no provider call | 0 | `$0` | passed: production sync plus container contract smoke proves `_max_shots=1` and fallback isolation |
| `L4D-5Y` S2 bounded media provider smoke | one scenario, one bounded media chain | 1 scenario submit, 1 image job, 1 video job | `$3.00` | passed: one S2 bounded media run reached `seedance_clips`; artifacts stayed tenant-scoped `pending_review`; no forbidden downstream steps |
| `L4D-5Z` frontend/library read-only regression | no provider call | 0 | `$0` | passed: bounded media video/keyframe visible; poster cache is thumbnail-only; matching `final_work` count is 0 |

Rules:

- Do not skip from `L4D-1` to `L4D-5`.
- Do not combine image, video, TTS, assemble, and scenario orchestration in one first media smoke.
- `L4D-1` forbids Seedance, TTS, assemble, gate candidate, publish, `final_work`, and delivery acceptance.
- `L4D-2` forbids image generation; use an existing pending-review/static input if the video endpoint requires an image.
- `L4D-3` is the first stage allowed to chain image output into video input, still limited to 1 image + 1 video.
- `L4D-4` must run with `RUN_TOKEN_SMOKE=0` or an equivalent no-provider read-only path.
- `L4D-5Y` is the only passed scenario media pilot. It validates S2 bounded media through `seedance_clips`; it does not validate S2 full media/final assembly or any other scenario's media path.
- Every failed stage stops the ladder; reruns need fresh authorization.

`2026-06-12 L4D-1` execution record: use `scripts/l4d_image_only_smoke.py`, not the older full asset-pack harness. The run submitted exactly one `gpt-image-2` image job and wrote `tmp/outputs/l4d-1-image-only-execute-20260612-122336.json` with `status=submitted`, `provider_call_executed=true`, `image_job_count=1`, `video_job_count=0`, and `blocked_reasons=[]`. The provider media URL was present, but local material download returned HTTP 403, so the result is quarantined in `tmp/outputs/l4d-1-image-only-quarantine-20260612042615.json` and `output/tenants/default/quarantine/l4d_image_only_20260612042615/l4d_image_only_quarantine_manifest.json`. This is not `L4D-4` readback evidence and does not prove frontend library visibility.

`2026-06-12 L4D-1R` diagnostic record: no submit and no new generation. `tmp/outputs/l4d-1r-media-url-diagnostic-20260612-123136.json` shows the poyo status endpoint returned HTTP 200, task `finished`, and a `.png` file URL on `cdn.doculator.org`. HEAD and default GET returned 403, while browser `User-Agent` GET returned 200 `image/png` with `1431644` bytes. The same existing image was then downloaded to `output/tenants/default/pending_review/l4d_image_only_20260612043209/main_45.png`, with summary `tmp/outputs/l4d-1r-pending-review-materialized-20260612043209.json`. Local portfolio scan recognizes it as `category=pending_review`, `kind=creation_intermediate`, `tenant_id=default`, and `review_status=pending_review`. Production file sync and production `/api/portfolio` readback are still separate steps.

`2026-06-12 L4D-4-prep corrected volume` execution record: files were synced to the real backend output volume under `/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/default/pending_review/l4d_image_only_20260612043209/`; local and remote hashes matched, `/api/health` returned ok, and `final_work` matched count was `0`. The production readback still failed because the available non-demo production key is scoped to tenant `momcozy-marketing`, while the authorized target was `tenant_id=default`. Evidence: `tmp/outputs/l4d-4-prep-corrected-volume-readback-failed-20260612151907.json`. This is a tenant-scope mismatch, not a file sync or provider failure.

`2026-06-12 L4D-4R-prep momcozy-marketing tenant` execution record: the same two existing files were synced to `/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/`; hashes matched and `/api/health` returned ok. Production `/api/portfolio` readback passed with `match_count=1`, `final_work_match_count=0`, `category=pending_review`, `kind=creation_intermediate`, `review_status=pending_review`, `tenant_id=momcozy-marketing`, and `size_bytes=1431644`. Evidence: `tmp/outputs/l4d-4r-prep-momcozy-marketing-production-readback-20260612-1520.json`.

`2026-06-12 L4D-2 video-only` execution record: `scripts/l4d_video_only_smoke.py` dry-run passed first, then execute mode submitted exactly one poyo `seedance-2` video job from the existing pending-review image `tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/main_45.png`. Evidence `tmp/outputs/l4d-2-video-only-execute-20260612-155843.json` shows `provider_call_executed=true`, `image_job_count=0`, `video_job_count=1`, and `blocked_reasons=[]`. The video was materialized and synced to `/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/momcozy-marketing/pending_review/l4d_video_only_20260612160601/`; production readback evidence `tmp/outputs/l4d-2-video-only-production-readback-20260612-160805.json` passed with `match_count=1`, `final_work_match_count=0`, `category=pending_review`, `kind=creation_intermediate`, `review_status=pending_review`, `tenant_id=momcozy-marketing`, `mime_type=video/mp4`, and `size_bytes=2474327`.

`2026-06-12 L4D-3 image+video paired` execution record: `scripts/l4d_paired_smoke.py` dry-run passed first, then execute mode submitted exactly one poyo `gpt-image-2` image job and one poyo `seedance-2` video job. The video job used only this run's generated image artifact as input. Evidence `tmp/outputs/l4d-3-paired-execute-20260612-161905.json` shows `provider_call_executed=true`, `image_job_count=1`, `video_job_count=1`, and `blocked_reasons=[]`. The image and video were materialized and synced to `/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/momcozy-marketing/pending_review/l4d_paired_20260612162837/`; production readback evidence `tmp/outputs/l4d-3-paired-production-readback-20260612-163016.json` passed with image/video `match_count=1`, image/video `final_work_match_count=0`, `category=pending_review`, `kind=creation_intermediate`, `review_status=pending_review`, and `tenant_id=momcozy-marketing`.

`2026-06-12 L4D-4 frontend/library read-only` execution record: only `web/e2e/production/library-portfolio.prod.spec.ts` was allowed.

- Runtime flags: `RUN_TOKEN_SMOKE=0`, `PLAYWRIGHT_PROD_WORKERS=1`, `--retries=0`, and `--workers=1`.
- Result: `--list` enumerated 3 tests in that single file, and Playwright returned `3 passed (10.3s)`. The spec verified exact L4D-2/L4D-3 pending-review paths and matching `final_work` count `0`, then verified `/library?tab=materials` renders pending-review media cards without non-GET API calls.
- Evidence: `tmp/outputs/l4d-4-library-readonly-summary-20260612-163833.json`.
- Boundary note: the backend log evidence shows no provider submit, poyo, Seedance, TTS, assemble, keyframe, gate candidate, publish, or delivery acceptance logs in the L4D-4 window.

`2026-06-12 L4D-5-prep S2 bounded media readiness` execution record: only `web/e2e/production/scenario-s2-bounded-media-pilot-readiness.prod.spec.ts` was added.

- Runtime flags: `RUN_TOKEN_SMOKE=0`, `PLAYWRIGHT_PROD_WORKERS=1`, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`, `--retries=0`, and `--workers=1`.
- Result: `--list` enumerated exactly 1 test in that single file, and Playwright returned `1 passed (1.1s)`. The spec only checked local readiness guards and `GET /api/health=ok`; it did not call `/api/scenario/s2`, provider APIs, publish, delivery acceptance, or brand-token writes.
- Evidence summary: `tmp/outputs/l4d-5-prep-s2-bounded-media-readiness-summary-20260612.json`.
- Readiness decision: `prep_passed_live_submit_blocked_before_provider_call`.
- Boundary note: the blocker was explicit at that point: `/api/scenario/s2` did not yet expose or enforce `artifact_disposition`, and `enable_media_synthesis=true` was not yet proven to be a bounded pending-review-only media path.

`2026-06-12 L4D-5-fix-prep S2 bounded media implementation` execution record: local code now adds `artifact_disposition` to `S2BrandCampaignRequest`, passes it through `run_s2_brand_campaign`, and makes `S2BrandCampaignPipeline` run `pending_review` / `quarantine` media pilots only through `seedance_clips`. The bounded result forces `final_video_path=""`, clears `render_json_path`, skips TTS/thumbnail/final assembly/audit, and emits `delivery_accepted=false`, `publish_allowed=false`, `approved_brand_token_write=false`. Verification: `tests/test_s2_e2e.py` 20 passed, `tests/test_scenario_commercial_injection_router.py tests/test_s2_deprecated_shim_boundary.py` 8 passed, ruff passed, eslint passed, token guard 7 passed, `git diff --check` passed, and the single readiness spec listed and ran 1 test with only `GET /api/health=ok`. Evidence summary: `tmp/outputs/l4d-5-fix-prep-s2-bounded-media-readiness-summary-20260612.json`. Production backend files were not synced in this stage.

`2026-06-12 L4D-5-fix-sync-prep S2 bounded media production sync` execution record: only the three authorized backend files were synced to production. Remote originals were backed up under `/opt/ai-video/backups/l4d5-fix-sync-prep-20260612-173119/`; local/remote/container SHA-256 hashes matched (`_state.py` `c985ea4b0e8326e6eed1285531bce9a1215cd98d24a42c1c1b8f5ab5deee44e9`, `scenario.py` `7332d51dbd6c2fb37f4c6a4bd795f8577d0b0693f8ba4d4ea306907e22bdb588`, `s2_brand_pipeline_v2.py` `fad623e529d59e99c8d5eff68a9b10cb4ecd6d3c3f0294425a6dfa6cb8381f8e`). Backend restart succeeded; an immediate `/api/health` returned transient 502, then the first retry returned `ok`. Container import smoke confirmed `artifact_disposition=pending_review` and `S2_BOUNDED_MEDIA_STOP_STEP=seedance_clips`. The 370-second no-submit backend log window had `forbidden_total=0`, including zero `/scenario/s2`, poyo, SiliconFlow, Seedance, TTS, assemble, keyframe, gate candidate, `final_work`, publish, and approved brand token write. Evidence summary: `tmp/outputs/l4d-5-fix-sync-prep-summary-20260612-174020.json`.

`2026-06-13 L4D-5X keyframe cap/fallback isolation` execution record: only `src/skills/keyframe_images.py` was synced to production, then backend health, hash verify, import smoke, and introspection passed. The 6-minute no-submit log gate had no `/api/scenario/*`, poyo, SiliconFlow, Seedance, TTS, thumbnail, assemble, media_quality_audit, gate candidate, `final_work`, publish, delivery, or approved brand token hits. Evidence: `tmp/debug/l4d5x-final-summary-20260613133623.json`. The follow-up container contract smoke mocked provider execution and verified `_max_shots=1`, exactly one keyframe on normal and fallback paths, non-fallback metadata on the safe path, and fallback writes only under `/tmp`. Evidence: `tmp/debug/l4d5x-post-sync-contract-summary-20260613135041.json`.

`2026-06-13 L4D-5Y S2 bounded media keyframe-input verified provider smoke` execution record: only `web/e2e/production/scenario-s2-bounded-media-pilot-live.prod.spec.ts` was allowed.

- Runtime flags: `RUN_TOKEN_SMOKE=1`, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`, `PLAYWRIGHT_EXPLICIT_SPEC=scenario-s2-bounded-media-pilot-live.prod.spec.ts`, and `PLAYWRIGHT_S2_BOUNDED_SUBMIT_TIMEOUT_MS=600000`.
- Evidence: `tmp/debug/l4d5y-final-summary-20260613132543.json`.
- Result: Playwright passed in `10.0m` with one `/api/scenario/s2` submit; `poyo_http_submit_count=2`, `image_job_count_by_readback=1`, `video_job_count_by_readback=1`, `final_work_match_count=0`, and all forbidden downstream counts `0`.
- Label: `l4d5s_s2_bounded_keyframe_20260613132543`.
- Keyframe: `tenants/momcozy-marketing/pending_review/l4d5s_s2_bounded_keyframe_20260613132543/keyframes/poyo_img_keyframe_script-BRIEF-001-en_000_8511.png`.
- Clip: `tenants/momcozy-marketing/pending_review/l4d5s_s2_bounded_keyframe_20260613132543/clips/seedance_DDMO5J2C_28df.mp4`.
- Cleanup: the temporary non-demo production key was revoked after the run.

`2026-06-13 L4D-5Z frontend/library read-only regression` execution record: only `web/e2e/production/library-portfolio.prod.spec.ts` was allowed with `RUN_TOKEN_SMOKE=0`. The spec now supports bounded-media target parameterization via environment variables so the same read-only regression can target a specific L4D run label without editing the test each time. Playwright result was `3 passed`; it verified the L4D-5Y pending-review video/keyframe are visible, the poster cache is only `thumbnail_path` and not an independent portfolio asset, and matching `final_work` count is `0`. Refined backend log gate observed only `/portfolio/` GETs, non-GET count `0`, and forbidden hits `{}`. Evidence: `tmp/debug/l4d5z-final-summary-20260613135315.json` and `tmp/debug/l4d5z-refined-log-gate-20260613135315.json`.

Current default stop condition: do not run more provider calls just to strengthen this rung. The next default action is documentation, CI/read-only guard consolidation, and evidence indexing. Any future S2 full media, S1/S3/S4/S5 media, TTS, thumbnail, assemble, media_quality_audit, publish, delivery acceptance, or approved brand token write requires a new stage definition, budget, stop-loss wording, and exact authorization.

Formal closeout evidence index: [L4D Real Media Provider Evidence Index](../workflows/l4d-real-media-provider-evidence-index-stable.md).

## Token-Smoke Scope

Full `RUN_TOKEN_SMOKE=1 npm run e2e:prod` is `L4C`, not the first-wave path. Current `@token-smoke` specs can create backend tasks or trigger scenario orchestration:

- `fast-mode-single-submit.prod.spec.ts`
- `fast-mode-submit.prod.spec.ts`
- `scenario-s1-no-media-single-submit.prod.spec.ts`
- `scenario-s2-no-media-single-submit.prod.spec.ts`
- `scenario-s3-no-media-single-submit.prod.spec.ts`
- `scenario-s4-no-media-single-submit.prod.spec.ts`
- `scenario-s5-no-media-single-submit.prod.spec.ts`
- `user-journey.prod.spec.ts`
- `s1-gate.prod.spec.ts`
- `s1-step-by-step.prod.spec.ts`
- `scenario-multi-submit.prod.spec.ts`

Do not add new mutating production tests unless their test title contains `@token-smoke`.
Do not add demo-key fallback inside production specs; use `productionApiHeaders()` from `web/e2e/production/helpers.ts`.

Before any `L4C` run, define the exact specs, total budget, per-spec ceiling, retry policy, whether S1/S5 may enter media generation, and serial worker settings. Review failures before retrying; do not loop token smoke blindly.

Use the no-execute L4C plan validator before copying any token-smoke command:

```bash
cp configs/l4c-token-smoke-plan-template.json tmp/outputs/private-l4c-token-smoke-plan.json
# Fill the private plan: template_only=false, status=approved, allowed_specs, budget,
# per_spec_budget_usd, media_generation, artifact_policy, and approval refs.

AI_VIDEO_L4C_TOKEN_SMOKE_PLAN_RECORD=tmp/outputs/private-l4c-token-smoke-plan.json \
PLAYWRIGHT_API_KEY=<non-demo-key> \
python scripts/l4c_token_smoke_plan.py --json \
  > tmp/outputs/l4c-token-smoke-plan-readiness-YYYYMMDD.json
```

The validator is intentionally no-execute. A passed report means the L4C packet is structurally ready for operator review; it is not provider runtime evidence and it is not delivery acceptance.

Historical L4C-1 command actually used on 2026-06-11:

```bash
cd web
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<non-demo-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/fast-mode-submit.prod.spec.ts \
  --reporter=list --retries=0 --workers=1
```

Do not generalize this command to the full suite. Any next `L4C` slice needs a new plan record, new explicit authorization, a `max_submit_count=1` guard or single-submit spec split, and a pending_review-only artifact-disposition guard.

Historical L4C-1R command actually used on 2026-06-11:

```bash
cd web
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_MAX_SUBMIT_COUNT=1 \
PLAYWRIGHT_PROVIDER_MAX_RETRIES=0 \
PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/fast-mode-single-submit.prod.spec.ts \
  --reporter=list --retries=0 --workers=1
```

The first guarded run failed before video-provider submit because the production output volume did not allow `appuser` to create `tenants/default/pending_review`. After the permission fix, the same single-submit command was rerun only after a new explicit authorization and passed. Do not run it again without another explicit authorization.

Passed L4C-1R retry evidence:

- Summary: `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json`
- Playwright log: `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-playwright-20260611-171600.log`
- Production status: `tmp/outputs/l4c-1r-retry-fast-mode-status-20260611-171600.json`
- Backend submit/retry evidence: `tmp/outputs/l4c-1r-retry-production-backend-evidence-20260611-171600.log`
- Portfolio read-only evidence: `tmp/outputs/l4c-1r-retry-portfolio-creation-intermediate-20260611-171600.json` and `tmp/outputs/l4c-1r-retry-portfolio-final-work-20260611-171600.json`

`L4C-2` status: the first authorized run of `scenario-s2-no-media-single-submit.prod.spec.ts` failed and was stopped. Evidence: `tmp/outputs/l4c-2-s2-no-media-single-submit-summary-20260611-174120.json`. The test timed out at 30s, and production logs showed that `/api/scenario/s2` with `enable_media_synthesis=false` still entered poyo image generation with 3 `gpt-image-2` task ids: `78BSCUGXZADGMCUH`, `83WVI2HST7TOLZF0`, `E48NL40OIALQV82N`. No Seedance video log was observed. The backend was restarted to stop the active request.

Root-cause fix: `src/pipeline/s2_brand_pipeline_v2.py` now runs only pre-`keyframe_images` steps when `enable_media_synthesis=false`. The fix was minimally deployed to production and health returned `ok`; the previous production file was backed up as `/opt/ai-video/src/pipeline/s2_brand_pipeline_v2.py.bak-l4c2-20260611174814`. Do not claim the failed first L4C-2 run passed.

`L4C-2R` status: the authorized after-fix single-submit rerun passed. Evidence: `tmp/outputs/l4c-2r-s2-no-media-single-submit-summary-20260611-095826.json`. Playwright showed `1 passed (11.1s)`, with `max_submit_count=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, and `--retries=0`. Production logs after `s2: starting brand campaign` showed `poyo_http_request_count=0`, `poyo_submit_execution_count=0`, `seedance_execution_count=0`, `tts_execution_count=0`, `assemble_execution_count=0`, `keyframe_execution_count=0`, `deepseek_http_request_count=2`, and `s2_complete_no_media_count=1`. Remote output only added `/app/output/pipeline_states/s2_momcozy_1781172006.json`; media fields remained empty. Do not rerun without a fresh authorization, a new L4C plan record, and the same `max_submit_count=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `--retries=0` boundary.

`L4C-3` status: `scenario-s1-no-media-single-submit.prod.spec.ts` was executed once after exact user authorization and after the minimal two-file production sync/hash gate. Evidence: `tmp/outputs/l4c-3-s1-no-media-single-submit-summary-20260611-102747.json`. The local S1 no-media implementation stops before `keyframe_images` for `S1ProductDirectPipeline.run()`, `/scenario/s1`, `/scenario/s1/start` auto, and unified `/scenario/s1/submit`. The pre-submit sync only touched the two authorized files, backed up remote originals under `/opt/ai-video/backups/l4c3-s1-no-media-20260611-102747/`, restarted backend, and verified hash match for `src/pipeline/s1_product_pipeline.py` plus `src/routers/scenario.py`.

The live submit failed and was stopped: Playwright expected HTTP 200 but received HTTP 500. Production logs show `ImportError: cannot import name 'MAX_CLIPS_PER_DEMO' from 'src.config' (/app/src/config.py)`, meaning the two-file sync introduced a dependency on local `src/config.py` constants that were not yet present in production. Provider execution did not start: `tmp/outputs/l4c-3-s1-no-media-production-provider-counts-20260611-102747.json` shows poyo, Seedance, TTS, assemble, keyframe, and DeepSeek execution counts all `0`. Do not rerun without a fresh authorization.

`L4C-3R-prep` status: config sync and import smoke passed after a separate authorization. Evidence: `tmp/outputs/l4c-3r-prep-config-sync-import-smoke-summary-20260611-183914.json`. Only `src/config.py` was synced, remote original was backed up under `/opt/ai-video/backups/l4c3r-prep-config-20260611-183914/`, backend was restarted, `/api/health` returned `ok`, and local/remote/container `src/config.py` hashes all matched `e54498c02e1d0ad3ca5f7c26bebf17e7f3bf985fe75a8aaee85a215a5306669a`. Container import smoke for `src.pipeline.s1_product_pipeline` returned `import_ok=true` and confirmed `MAX_CLIPS_PER_DEMO=3`, `MAX_THUMBNAILS_PER_DEMO=2`. The post-restart prep log window showed zero DeepSeek/poyo/SiliconFlow external HTTP and zero poyo/Seedance/TTS/assemble/keyframe execution. A broader pre-prep window contains admin health-check provider probes; do not attribute those to the config sync/import smoke.

`L4C-3R` status: the authorized S1 no-media after-config-sync single-submit smoke passed with a caveat. Evidence: `tmp/outputs/l4c-3r-s1-no-media-single-submit-summary-20260611-184923.json`. Plan validator passed with `allowed_specs=["scenario-s1-no-media-single-submit.prod.spec.ts"]`, `max_submit_count=1`, and `provider_max_retries=0`; Playwright `--list` showed one test; the live run showed `1 passed (8.3s)` with `--retries=0` and `--workers=1`. Production label was `s1_1781175031_a8117a86`; `/scenario/s1` returned 200.

State evidence: `tmp/outputs/l4c-3r-s1-no-media-state-summary-20260611-184923.json` shows `enable_media_synthesis=false`, completed text/pre-media steps only, `keyframe_images` and downstream media steps pending, all media paths empty, `errors_len=0`, and `media_synthesis_errors_len=0`. `tmp/outputs/l4c-3r-s1-no-media-remote-artifact-search-20260611-184923.txt` found no label artifacts or recent media files.

Provider evidence: `tmp/outputs/l4c-3r-s1-no-media-production-provider-counts-refined-20260611-184923.json` shows DeepSeek text requests `3`, while poyo image/video submit, Seedance generation, TTS generation, assemble generation, keyframe generation, and gate candidate generation are all `0`. Caveat: after `/scenario/s1` returned 200, the admin health loop emitted GET probes to poyo `/v1/models` and SiliconFlow `/v1/models`; these are not media generation, but they mean the runbook must not claim a fully provider-log-clean backend window.

Admin health probe guard: production now defaults `ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED=0`, so `run_health_checks()` marks DeepSeek, poyo, and SiliconFlow as `skipped` instead of issuing external HTTP probes. Postgres and Remotion health checks still run. Evidence: `tests/test_admin_health_provider_probe_guard.py` plus `tests/test_admin_endpoints_smoke.py` passed locally; production sync evidence is `tmp/outputs/l4c-3h-prep-admin-provider-health-probe-sync-summary-20260611-222821.json`.

`L4C-3H-prep` status: passed. Only `src/config.py` and `src/routers/admin/logs.py` were synced, remote originals were backed up under `/opt/ai-video/backups/l4c3h-admin-health-probe-20260611-222821/`, backend was restarted, `/api/health` returned `ok`, and local/remote/container hashes matched for both files. The no-submit observation window ran for 370 seconds from `2026-06-11T14:31:16Z`; `tmp/outputs/l4c-3h-prep-observation-counts-20260611-222821.json` shows DeepSeek/poyo/SiliconFlow external HTTP counts `0`, `/scenario` submit count `0`, and poyo submit / Seedance / TTS / assemble / keyframe / gate candidate counts all `0`; `tmp/outputs/l4c-3h-prep-observation-matches-20260611-222821.txt` has 0 lines.

`L4C-4` status: strict clean-log failed, business path passed. Evidence: `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-summary-20260611-230535.json`. The no-execute plan validator passed, Playwright `--list` showed exactly one test, and the single live run of `scenario-s1-no-media-single-submit.prod.spec.ts` showed `1 passed (13.4s)`. The zsh wrapper failed only after Playwright completed because `PIPESTATUS` was unavailable; the spec was not rerun.

`L4C-4` state evidence: label `s1_1781190534_6dcf8877`; `tmp/outputs/l4c-4-s1-no-media-clean-log-state-summary-20260611-230535.json` shows `enable_media_synthesis=false`, all media path lists length `0`, `final_video_path=""`, `delivery_accepted=false`, `publish_allowed=false`, and `approved_brand_token_write=false`. `tmp/outputs/l4c-4-s1-no-media-clean-log-remote-artifact-search-20260611-230535.txt` found no matching media or recent final_work output.

`L4C-4` log evidence: `tmp/outputs/l4c-4-s1-no-media-clean-log-production-provider-counts-20260611-230535.json` shows DeepSeek text calls `2`, `api.poyo.ai=0`, `api.siliconflow.cn=0`, and execution-level poyo submit / Seedance / TTS / assemble / keyframe / gate candidate counts all `0`. However, `tmp/outputs/l4c-4-s1-no-media-clean-log-registration-noise-matches-20260611-230535.txt` contains 8 media skill `registered` lines with TTS/keyframe/assemble/Seedance lexemes. These are not provider generation, but they violate the strict clean-log authorization wording. Do not claim L4C-4 clean-log passed.

Previous minimal action after `L4C-4`: run `L4C-4R-prep` only after explicit authorization to sync a small import/logging hygiene fix that prevents no-media S1 from registering or logging media skills during the submit window. That prep has now passed; any S1 clean-log rerun, S2-S5, gate, media/poster/quality, or full-suite run still needs a new L4C plan, validator pass, and exact authorization.

`L4C-4R-prep` status: passed. Evidence: `tmp/outputs/l4c-4r-prep-s1-logging-import-hygiene-sync-summary-20260612-000910.json`. Only `src/pipeline/__init__.py` and `src/pipeline/s1_product_pipeline.py` were synced, remote originals were backed up under `/opt/ai-video/backups/l4c4r-prep-s1-logging-20260612-000910/`, backend was restarted, and `/api/health` returned `ok` before sync, after restart, and after observation.

Hash evidence: `tmp/outputs/l4c-4r-prep-hash-verify-20260612-000910.txt` shows local/remote/container hashes matched for both synced files. Log evidence: `tmp/outputs/l4c-4r-prep-observation-counts-20260612-000910.json` shows the 370-second no-submit backend window had zero `/scenario` submit, zero DeepSeek/poyo/SiliconFlow external HTTP, zero poyo submit, zero Seedance/TTS/assemble/keyframe/gate-candidate logs, and zero media skill `registered` logs.

Previous minimal action after `L4C-4R-prep`: request `L4C-4R` authorization for the same single spec only: `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`, `RUN_TOKEN_SMOKE=1`, `PLAYWRIGHT_PROD_WORKERS=1`, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`, `--retries=0`, and `--workers=1`. That run has now passed; do not widen to S2-S5, gate, media/poster/quality, or the full token suite without a new plan and exact authorization.

`L4C-4R` status: passed. Evidence: `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-summary-20260612-001.json`. The no-execute validator report `tmp/outputs/l4c-4r-s1-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-001.json` passed with `allowed_specs=["scenario-s1-no-media-single-submit.prod.spec.ts"]`, `max_submit_count=1`, and `provider_max_retries=0`; Playwright `--list` showed exactly one test.

Execution evidence: `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-playwright-20260612-001.log` shows `1 passed (11.7s)`, `--retries=0`, and `--workers=1`; production label was `s1_1781229202_7b5148d1`. Log evidence: `tmp/outputs/l4c-4r-s1-no-media-clean-log-observation-counts-20260612-001.json` shows DeepSeek text calls `2`, `api.poyo.ai=0`, `api.siliconflow.cn=0`, and poyo submit / Seedance / TTS / assemble / keyframe / gate candidate / media skill registered counts all `0`. `scenario_s1_submit=2` is the application log plus uvicorn access log for the same HTTP 200 request; the spec observed one submit.

Previous minimal action after `L4C-4R`: do not run the full token suite. Pick the next smallest authorized slice, such as S2 no-media clean-log rerun or an explicitly read-only post-submit evidence check, then create a new L4C plan record and require exact authorization before execution. The S2 no-media clean-log slice has now passed as `L4C-5`.

`L4C-5` status: passed. Evidence: `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-summary-20260612-002.json`. The no-execute validator report `tmp/outputs/l4c-5-s2-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-002.json` passed with `allowed_specs=["scenario-s2-no-media-single-submit.prod.spec.ts"]`, `max_submit_count=1`, and `provider_max_retries=0`; Playwright `--list` showed exactly one test.

Execution evidence: `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-playwright-20260612-002.log` shows `1 passed (7.2s)`, `--retries=0`, and `--workers=1`; production label was `s2_momcozy_1781230204`. Log evidence: `tmp/outputs/l4c-5-s2-no-media-clean-log-observation-counts-20260612-002.json` shows DeepSeek text calls `2`, `api.poyo.ai=0`, `api.siliconflow.cn=0`, and poyo submit / Seedance / TTS / assemble / keyframe / gate candidate / media skill registered counts all `0`. `scenario_s2_submit=2` is the application log plus uvicorn access log for the same HTTP 200 request; the spec observed one submit.

`L4C-6` / `L4C-7` / `L4C-8R` status: passed. S3, S4, and S5 no-media clean-log single-submit paths were each executed only after separate explicit authorization and prep sync when needed. Each run used one spec, `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`, `--retries=0`, and `--workers=1`. S3 passed in `23.5s`; S4 passed in `7.1s`; S5 first exposed a Playwright 30-second timeout while backend returned 200, then passed as `L4C-8R` after adding a local `test.setTimeout(120_000)` and obtaining fresh authorization. All three runs showed DeepSeek text only and zero poyo/SiliconFlow/media forbidden counts.

Current minimal action after `L4D-5Z`: do not run the full token suite, do not run multiple S1-S5 media scenarios, and do not run another provider submit merely to strengthen the same rung. Default next work is documentation, CI/read-only guard consolidation, and evidence indexing. Any future full-media or publish/delivery stage must start with a new scope and exact authorization.

## Evidence Requirements

Every real-provider run must produce a private evidence record under `tmp/outputs/` or outside the repo. The record must include:

- actor and timestamp
- approval record path without secrets
- account readiness record path without secrets
- provider job ids / task ids
- backend trace ids / response `_meta.trace_id`
- artifact refs / media URLs
- Playwright summary or screenshots for `L4B`
- L4C plan readiness report when expanded token Playwright is used
- L4D stage name, submit ceiling, budget ceiling, retry policy, and artifact disposition when staged media provider smoke is used
- cost estimate and actual charge note
- explicit `delivery_accepted=false`, `publish_allowed=false`, `approved_brand_token_write=false`
