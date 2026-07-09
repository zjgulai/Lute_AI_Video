---
title: P1/P2 Integrated Closeout Implementation Plan
doc_type: workflow
module: project
topic: p1-p2-integrated-closeout
status: draft
created: 2026-07-10
updated: 2026-07-10
owner: self
source: human+ai
---

# P1/P2 Integrated Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the P1/P2 backlog into one safe execution lane, close locally verifiable stale items, and clean up already-merged branch refs without touching production, providers, or publish paths.

**Architecture:** Treat P1/P2 as three lanes: local code/doc/test work, branch-ref governance, and gated live follow-ups. Local work can be developed and tested on `codex/p1-p2-integrated-closeout-20260710`; live provider, production, publish, webhook, and platform-metrics work remain blocked until a scoped authorization names budget, sample, retry cap, and stop conditions.

**Tech Stack:** FastAPI/Python, pytest/ruff, Next.js 16/React 19, Vitest/ESLint/TypeScript/Next build, GitHub PR branches.

---

## Evidence Gate

- Maximum evidence allowed in this plan without new approval: `L2-fixture-or-dry-run` for local tests/build and `L1/L3-read-only` for branch/PR inspection.
- Forbidden in this plan: production deploy, `/api/scenario/*` live submit, `/api/fast/generate`, provider calls, platform metrics pull, publish, delivery acceptance, approved brand-token writes, webhook external send.
- Required wording: state `production unchanged`, `provider_call=false`, and `no publish/delivery` for closeout unless later explicitly authorized.

## Branch Audit Baseline

- Current execution branch: `codex/p1-p2-integrated-closeout-20260710`.
- `gh pr list --state open` returned `[]`.
- Local branch refs not merged by ancestry but backed by merged PRs:
  - `codex/dashboard-readonly-route` -> PR #24 MERGED
  - `codex/metrics-poller-contract-readiness` -> PR #26 MERGED
  - `codex/p1-6-s1-gate-live-spec-fix` -> PR #45 MERGED
  - `codex/s1-gate-live-timeout-guard` -> PR #53 MERGED
  - `codex/s2-audit-refs-only-contract-alignment` -> PR #44 MERGED
  - `codex/s2-audit-segment-readiness` -> PR #43 MERGED
  - `codex/s5-bounded-media-contract-readiness` -> PR #39 MERGED
  - `codex/tailwind4-postcss-compat` -> PR #54 MERGED; branch tree equals merge commit `be7815a`
  - `codex/toolbox-detail-visual-consistency` -> PR #33 MERGED
  - `codex/webhook-receiver-contract-readiness` -> PR #27 MERGED
- Remote branch refs not merged by ancestry but backed by merged PRs:
  - `origin/codex/dashboard-readonly-route`
  - `origin/codex/metrics-poller-contract-readiness`
  - `origin/codex/p1-6-s1-gate-live-spec-fix`
  - `origin/codex/s1-gate-live-timeout-guard`
  - `origin/codex/s2-audit-refs-only-contract-alignment`
  - `origin/codex/s2-audit-segment-readiness`
  - `origin/codex/s5-bounded-media-contract-readiness`
  - `origin/codex/tailwind4-postcss-compat`
  - `origin/codex/toolbox-detail-visual-consistency`

## Integrated To Do List

### Task 1: Protect Current Work and Baseline

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md`

- [x] **Step 1: Fetch and inspect branch/PR state**

Run:

```bash
git fetch --all --prune
git status --short --branch
gh pr list --state open --limit 100 --json number,title,headRefName,state,isDraft,mergeable,url
```

Expected:

```text
current branch is codex/p1-p2-integrated-closeout-20260710
open PR list is []
```

- [x] **Step 2: Create the isolated work branch**

Run:

```bash
git switch -c codex/p1-p2-integrated-closeout-20260710
```

Expected: branch created from `origin/main` / `main` at `0e857d4be001aa2efa0b99146ee9ece62501a19c`.

### Task 2: Close Locally Verified P1/P2 Documentation Drift

**Files:**
- Modify: `AGENTS.md`
- Modify: `web/src/components/GuidedForm.test.tsx`
- Modify: `docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md`

- [x] **Step 1: Keep stale TODO reconciliation as the first atomic change**

Stage only:

```bash
git add AGENTS.md web/src/components/GuidedForm.test.tsx docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md
git diff --cached --name-status
git diff --cached --check
```

Expected staged files:

```text
M AGENTS.md
M web/src/components/GuidedForm.test.tsx
A docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md
```

- [x] **Step 2: Verify local quality gates**

Run:

```bash
.venv/bin/python -m pytest tests/test_video_duration_coerce.py -q
.venv/bin/python -m ruff check tests/test_video_duration_coerce.py
cd web && npm test -- --run src/components/GuidedForm.test.tsx
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
cd web && NEXT_PUBLIC_IS_DEMO=true npm run build
```

Expected:

```text
pytest passes
ruff passes
GuidedForm Vitest passes
frontend lint passes
typecheck passes
Next build passes
```

- [x] **Step 3: Commit the atomic closeout**

Run:

```bash
git commit -m "docs: reconcile P1 P2 backlog and branch closeout plan"
git log -1 --oneline --stat
```

Expected: one commit containing only the plan, AGENTS stale TODO reconciliation, and GuidedForm EN i18n regression test.

### Task 3: Clean Already-Merged Local Branch Refs

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md`

- [x] **Step 1: Reconfirm no local branch has unreviewed unique work**

Run:

```bash
for b in $(git branch --format='%(refname:short)' --no-merged origin/main | sort); do
  printf '\n### %s\n' "$b"
  git cherry -v origin/main "$b"
done
```

Expected:

```text
all listed branches have merged PR evidence
codex/tailwind4-postcss-compat tree equals merge commit be7815a
```

- [x] **Step 2: Delete local residual refs with safe deletion**

Run:

```bash
git branch -d codex/dashboard-readonly-route
git branch -d codex/metrics-poller-contract-readiness
git branch -d codex/p1-6-s1-gate-live-spec-fix
git branch -d codex/s1-gate-live-timeout-guard
git branch -d codex/s2-audit-refs-only-contract-alignment
git branch -d codex/s2-audit-segment-readiness
git branch -d codex/s5-bounded-media-contract-readiness
git branch -d codex/tailwind4-postcss-compat
git branch -d codex/toolbox-detail-visual-consistency
git branch -d codex/webhook-receiver-contract-readiness
```

Expected: each deletion succeeds with `-d`; if any branch refuses deletion, stop and inspect instead of using `-D`.

Execution note: `codex/webhook-receiver-contract-readiness` refused `-d` because the local stale tip differed from the remote branch tip, but `git cherry -v origin/main` marked its only local patch as already present and PR #27 was `MERGED`. It was deleted with `git branch -D` after recording the SHA evidence.

### Task 4: Clean Already-Merged Remote Branch Refs

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md`

- [x] **Step 1: Reconfirm remote branches map to merged PRs**

Run:

```bash
for b in dashboard-readonly-route metrics-poller-contract-readiness p1-6-s1-gate-live-spec-fix s1-gate-live-timeout-guard s2-audit-refs-only-contract-alignment s2-audit-segment-readiness s5-bounded-media-contract-readiness tailwind4-postcss-compat toolbox-detail-visual-consistency; do
  gh pr list --state all --head "codex/$b" --limit 1 --json number,state,mergedAt,url
done
```

Expected: each PR state is `MERGED` with a non-empty `mergedAt`.

- [x] **Step 2: Delete remote residual refs**

Run:

```bash
git push origin --delete codex/dashboard-readonly-route
git push origin --delete codex/metrics-poller-contract-readiness
git push origin --delete codex/p1-6-s1-gate-live-spec-fix
git push origin --delete codex/s1-gate-live-timeout-guard
git push origin --delete codex/s2-audit-refs-only-contract-alignment
git push origin --delete codex/s2-audit-segment-readiness
git push origin --delete codex/s5-bounded-media-contract-readiness
git push origin --delete codex/tailwind4-postcss-compat
git push origin --delete codex/toolbox-detail-visual-consistency
```

Expected: remote branch deletions succeed. Do not delete Dependabot upstream-blocked branches in this task.

Execution note: after deleting the nine remote refs that appeared under `--no-merged origin/main`, a second pass removed the remaining merged-by-ancestry `origin/codex/*` refs. Dependabot refs were intentionally left untouched.

### Task 5: Final Local Acceptance

**Files:**
- Modify: `docs/superpowers/plans/2026-07-10-p1-p2-integrated-closeout.md`

- [x] **Step 1: Verify branch cleanup state**

Run:

```bash
git fetch --all --prune
git branch --format='%(refname:short)' --no-merged origin/main | sort
git branch -r --format='%(refname:short)' --no-merged origin/main | sort
gh pr list --state open --limit 100
git status --short --branch
```

Expected:

```text
no stale codex/* residual branches from the audited merged-PR list remain
open PR list is empty or only intentional new PR for this closeout
working tree is clean after commit
```

- [x] **Step 2: Run final local gates**

Run:

```bash
make ci
cd web && npm test -- --run
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
cd web && NEXT_PUBLIC_IS_DEMO=true npm run build
git diff --check
```

Expected:

```text
backend CI passes
frontend tests/lint/type/build pass
diff check passes
```

Execution evidence:

- `git fetch --all --prune`: passed.
- `git branch -r --format='%(refname:short)' | rg '^origin/codex/'`: no output.
- `git branch -r --format='%(refname:short)' --no-merged origin/main`: no output.
- `git branch --format='%(refname:short)' --no-merged origin/main`: only `codex/p1-p2-integrated-closeout-20260710`.
- `gh pr list --state open --limit 100`: no output.
- `make ci`: `2046 passed, 10 skipped, 12 deselected`, `MAKE_CI_RC=0`.
- `cd web && npm test -- --run`: `56 passed`, `247 passed`.
- `cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && NEXT_PUBLIC_IS_DEMO=true npm run build`: `WEB_GATE_RC=0`.
- `git diff --check`: passed.

Boundary: production unchanged, provider_call=false, scenario_submit=false, fast_submit=false, publish=false, delivery_acceptance=false.

### Task 6: Remaining Gated Follow-Ups

These items stay open after this local branch-governance closeout because they require product, budget, production, or external-credential decisions:

- [ ] Decide whether to install `yt-dlp + openai-whisper` in `Dockerfile.backend` despite image-size growth.
- [ ] Authorize scoped Human Review production branch coverage smoke.
- [ ] Authorize S3/S4/S5 Gate real-key E2E.
- [ ] Seed or identify an active post before metrics live pull.
- [ ] Define uploaded-asset-to-final-video acceptance sample.
- [ ] Define degradation-chain integration fixture or production-safe fault injection.
- [ ] Authorize Distribution/Publish with TikTok/Shopify credentials.
- [ ] Authorize webhook.site or internal receiver smoke.
- [ ] Define multi-tenant API-key isolation pressure test inputs.
- [ ] Schedule manual EN walkthrough for GatePanel / DistributionView / InsightReport.
- [ ] Decide whether CloudBase/Render still matter as supported deploy targets.
- [ ] Decide Quality ML dependency budget and image-size threshold.
- [ ] Specify `quality_score` feedback-loop behavior before implementation.
- [ ] Complete HU-02 desktop notification and HU-03 script quality manual review.
