# W2-14–W2-17 Frontend Scenario Correctness Plan

**Scope:** Local-only closure for canonical scenario completion, fail-closed Gate polling,
S5 six-view asset input, responsive review/completion layouts, keyboard/focus/reduced-motion
accessibility, and critical admin i18n. No GitHub update, deployment, provider mutation, publish,
delivery, notification, or external endpoint is allowed.

**Completion truth:** Each behavior starts with a failing contract, receives the smallest compatible
implementation, passes focused and full frontend gates plus affected backend/OpenAPI contracts, and
then enters the existing independent six-dimension review/reverification loop. Browser evidence is
reported separately and may not be inferred from jsdom or build success.

## Task 1 — Canonical StageProgress completion (W2-14)

**RED:** live and durable scenario status expose the server-owned canonical `step_order`.
`StageProgress` must not call `onComplete` because its local visual stage map happens to be done;
S4 remains nonterminal until the backend returns a coherent terminal status after `thumbnails`.
Unknown canonical steps must remain visible in progress rather than disappearing.

**GREEN:** add `step_order` to both status projections and the typed frontend response. Use the
server order to derive visual/progress membership, retaining local stage metadata only for labels
and duration estimates. Trigger completion only from the backend terminal status/lifecycle truth;
failed, recovery, degraded, paused, invalid, and running responses never complete.

## Task 2 — Fail-closed Gate resume polling (W2-15)

**RED:** a stagnant state, the bounded poll timeout, and any polling exception must stop without
calling `onApprove`. The UI must show a stable reason and an explicit retry/continue-checking
control. Valid next-Gate, final-step, or pipeline-terminal evidence still advances exactly once.

**GREEN:** separate the one-time approval mutation from a reusable read-only resume poller. Retry
only restarts canonical scenario `getScenarioStatus`; it must never repeat the approval POST. Clear
timers on every terminal, error, retry, and unmount path, and prevent duplicate callbacks.

## Task 3 — S5 exact six-view input (W2-16)

**RED:** the `product_views` GuidedCard accepts up to six image files or six library assets,
supports real drag/drop plus Enter/Space activation, preserves successful selections when one upload
fails, and exposes upload/count errors visibly and accessibly. S5 submit remains disabled until
exactly six nonempty paths exist; the request contains exactly six `product_views` and six
`product_sku.views` entries in stable selection order.

**GREEN:** specialize only the `product_views` image card while preserving all existing single-file
upload behavior. Reuse `AssetPickerModal` multiple selection, the existing upload endpoint, and the
current comma/newline serialization boundary. Do not create a second upload service or silently
truncate an invalid seventh persisted value.

## Task 4 — Responsive and accessible UI (W2-17)

**RED:** Review/Completion use one column below the desktop breakpoint and a bounded two-column
layout above it; interactive controls have a visible keyboard focus indicator; reduced-motion
preference suppresses nonessential animation/transition. A UI-only bilingual gate covers the admin
shell/login/sidebar plus primary headings, actions, forms, empty/error labels, and ARIA names for
dashboard, logs, health, tenants, and tenant detail. Provider names, IDs, codes, and user data remain
literal technical content.

**GREEN:** use responsive Tailwind layout classes, one global `:focus-visible` rule and one
`prefers-reduced-motion` rule, then route the bounded admin string set through the existing
`I18nProvider`/`translations.ts` SSOT. Do not change admin API behavior or authorization.

## Task 5 — Integration, browser attempt, and independent review

Run focused StageProgress/GatePanel/GuidedForm/admin/accessibility tests first, then all frontend
Vitest, ESLint, TypeScript, OpenAPI drift, and production build. Run affected backend status/router
tests plus Ruff/Pyright if the response contract changes. Attempt the existing local browser fixture
without external endpoints; if Chromium still cannot start, preserve that as an environment blocker
rather than an application pass. Send the complete Batch D diff and fresh evidence to the existing
read-only reviewer across requirements, logic, edge cases, quality, coverage, and actual results;
fix every accepted finding and reverify with the same reviewer until `PASS / APPROVE` or a concrete
blocker remains.

**External boundary:** Remote CI and deployment of this new SHA remain blocked while GitHub updates
are forbidden. Local success is not production, provider, publish, delivery, or browser evidence.

### Review loop status

Independent pass 1 returned `FAIL / CHANGES_REQUIRED` with four accepted findings: Gate polling was
hard-coded to S1, a null cursor could advance without coherent terminal truth, AssetPicker returned
filtered library order instead of click order and dropped hidden selections, and admin i18n/ARIA
plus login error localization were incomplete. Main-thread repairs now use scenario-specific status,
advance a null cursor only for exact bounded/full lifecycle truth, preserve ordered IDs against the
full asset list, and localize the remaining critical admin table/empty/detail/status/dialog controls.

Fresh repair evidence: focused frontend `9 files / 57 tests`; full frontend `69 files / 427 tests`;
ESLint, TypeScript, OpenAPI drift, 32-route build, affected backend `133 passed`, full backend
`4103 passed, 9 skipped, 20 deselected, 1 warning`, canonical Ruff, docs governance `12 passed`,
diff/strong-secret scans, and actual UI-only mobile Playwright `2 passed` are green. Pyright with the
project venv still reports the same three tracked `scenario.py` diagnostics outside the Batch D
response fields. Same-reviewer re-verification remains mandatory before completion.

Same-reviewer pass 2 closed findings 1, 3, and 4 but kept finding 2 open: Gate terminal coherence
omitted `pipeline_complete`, `publish_allowed`, and `delivery_accepted`. The repaired predicate now
checks all nine lifecycle fields and immediately fails closed when either status claims terminal but
the full envelope is contradictory. Six field-flip cases assert zero callback, zero repeated approval
POST, and the explicit read-only retry state. Fresh Gate evidence is `29 passed`; full frontend is
`69 files / 433 tests`, with ESLint, TypeScript, OpenAPI, and 32-route build green. Pass 3 remains
required.

Same-reviewer pass 3 returned `PASS / APPROVE` with `accepted_actionable_findings=0`. The reviewer
independently reran GatePanel `29 passed`, scoped ESLint, TypeScript, and diff checks. Batch D is
therefore `completed_local / independent_review=true`; this does not change the external boundary.
