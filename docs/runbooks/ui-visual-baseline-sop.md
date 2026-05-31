---
title: UI Visual Baseline SOP
doc_type: workflow
module: frontend
topic: ui-visual-baseline
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# UI Visual Baseline SOP

## Purpose

Use this SOP when updating `web/e2e/ui-only/` Playwright screenshot baselines. The goal is to catch layout regressions without hiding real UI breakage behind casual snapshot updates.

## When Updates Are Allowed

Only update baselines when all conditions are true:

- The UI/layout change is intentional and visible in the affected route.
- The diff is limited to expected screenshot files and matching source changes.
- `GENERATION_ENDPOINT_PATTERNS` and the 451 request block remain in `site-ui.visual.spec.ts`.
- No production URL, `PLAYWRIGHT_API_KEY`, `RUN_TOKEN_SMOKE=1`, upload, publish or scenario generation path is introduced.

## Update Procedure

1. Reproduce the failure without updating snapshots:

```bash
cd web
npm run e2e:ui
```

2. Inspect the Playwright report and confirm the change is expected:

```bash
open playwright-report/index.html
```

3. Update baselines only after confirming the source/UI change:

```bash
npm run e2e:ui -- --update-snapshots
```

4. Review the screenshot diff before staging:

```bash
git diff -- web/e2e/ui-only
```

5. Re-run the guard after updating:

```bash
npm run e2e:ui
npm test -- --run src/lib/uiOnlyE2eGuard.test.ts
```

## Rejection Rules

Do not update baselines when:

- The visual diff comes from loading state flicker, animation timing, random data or network leakage.
- The route made a token-consuming or mutating request.
- The only change is to make CI green without a matching product/source change.
- The diff adds full-page screenshots for long forms without a specific reason.

If any rejection rule applies, fix the UI/test stability issue instead of updating snapshots.
