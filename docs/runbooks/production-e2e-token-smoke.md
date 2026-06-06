---
title: Production E2E Token Smoke Runbook
doc_type: workflow
module: ci-cd
topic: production-e2e-token-smoke
status: stable
created: 2026-05-31
updated: 2026-06-06
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

If `PLAYWRIGHT_API_KEY` is missing or still equals `ai_video_demo_2026`, authenticated checks skip through `web/e2e/production/helpers.ts`. That result is not a production acceptance gate. The current non-token acceptance baseline is `50 passed, 2 skipped` with a real production API key and `RUN_TOKEN_SMOKE=0`.

## Required Secret For Token Smoke

Configure this GitHub Actions repository secret only after the POYO account is funded:

| Secret | Purpose |
|---|---|
| `PROD_DEMO_API_KEY` | Non-demo production API key used by `e2e-prod.yml`; the legacy name is misleading, but the value must not be `ai_video_demo_2026` |

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
RUN_TOKEN_SMOKE=0 PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top PLAYWRIGHT_API_KEY=<non-demo-key> npm run e2e:prod
```

Token-smoke local equivalent:

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
Do not add demo-key fallback inside production specs; use `productionApiHeaders()` from `web/e2e/production/helpers.ts`.
