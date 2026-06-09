# Changelog

## [0.2.7] — 2026-05-14

### Added
- C2PA dry-run checklist (P1-64): `docs/runbooks/c2pa-dry-run-checklist.md`
- P2-2 content moderation sample fixtures and regression tests
- P2-3 production post-deploy regression checklist

### Changed
- CI hermetic env guard (P1-16): external provider keys zeroed in CI
- Docker build no-token preflight (P1-32)
- S1-S5 hermetic regression command (P1-23)

### Fixed
- Deploy pytest timeout dependency (P1-14)
- README package-manager drift cleanup (P1-18)

---

## [0.2.4] — 2026-05-11

### Added
- Brand assets Phase 2-4: rich product metadata via `/api/portfolio/`
- `/api/portfolio/brand-presets?brand=X` endpoint
- `QuickTemplate` dynamic data consumption
- Brand assets refresh script + cron runbook
- 3 ADRs + 5 runbooks + deploy checklist

### Changed
- Brand Kit tab now fetches 137 Momcozy product images from API
- Creation Guide redesigned as 5-tab `CreationGuide.tsx`

### Fixed
- Admin panel 0600 permissions issue (Phase 0.5 defensive chmod)
- S2/S4 production crashes resolved

---

## [0.2.1] — 2026-05-11

### Added
- Tier-2: submit-lock, 422 inline error, 429 retry
- Tier-3: 3 ADRs, 4 runbooks, DEFAULT_LLM_PROVIDER SSOT
- HU-05: cardCopyEn 100-string zh→en map

### Fixed
- Deploy SOP: admin.py 0600 → Phase 0.5 defensive chmod
- Admin/Gate vitest coverage

---

## [0.2.0] — 2026-05-09

### Added
- 6 scenarios end-to-end verified
- Frontend UX v2: 4-tab navigation, `/works` + `/library`
- PipelineStatusBar, EmptyState, FormFieldGroup, TagInput, StickyActionBar components

### Fixed
- S2/S4 production crashes
- Various nginx and frontend build issues

---

## [0.1.0] — 2026-04

### Added
- Initial multi-agent AI video creation pipeline
- LangGraph-based with 16 nodes (12 worker + 4 self-audit)
- 4 human-in-the-loop review checkpoints
- DeepSeek V4-Pro + poyo.ai + CosyVoice provider chain
- FastAPI backend + Next.js frontend + Remotion rendering
- S1-S5 scenario pipelines
