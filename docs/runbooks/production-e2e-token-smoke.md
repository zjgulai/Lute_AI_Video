---
title: Production E2E Token Smoke Runbook
doc_type: workflow
module: ci-cd
topic: production-e2e-token-smoke
status: stable
created: 2026-05-31
updated: 2026-05-31
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
- `PLAYWRIGHT_API_KEY`: falls back to `ai_video_demo_2026` unless `PROD_DEMO_API_KEY` is configured

## Required Secret For Token Smoke

Configure this GitHub Actions repository secret only after the POYO account is funded:

| Secret | Purpose |
|---|---|
| `PROD_DEMO_API_KEY` | Non-demo production API key used by `e2e-prod.yml` when `run_token_smoke=true` |

The workflow intentionally fails if `run_token_smoke=true` while `PLAYWRIGHT_API_KEY` is still `ai_video_demo_2026`.

## Manual Run

Use GitHub UI:

1. Actions → `e2e-prod`
2. Run workflow
3. Set `base_url` to `https://video.lute-tlz-dddd.top`
4. Set `run_token_smoke` to `true` only after recharge
5. Review failures before retrying; do not loop token smoke blindly

Local equivalent:

```bash
cd web
RUN_TOKEN_SMOKE=1 PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top PLAYWRIGHT_API_KEY=<non-demo-key> npm run e2e:prod
```

## Token-Smoke Scope

Current `@token-smoke` specs can create backend tasks or trigger S1/gate orchestration:

- `fast-mode-submit.prod.spec.ts`
- `user-journey.prod.spec.ts`
- `s1-gate.prod.spec.ts`
- `s1-step-by-step.prod.spec.ts`

Do not add new mutating production tests unless their test title contains `@token-smoke`.
