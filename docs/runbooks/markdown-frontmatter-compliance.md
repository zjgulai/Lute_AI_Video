---
title: Markdown frontmatter compliance
doc_type: workflow
module: project
topic: markdown-frontmatter-compliance
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Markdown frontmatter compliance

## 1. 目标

正式区和草稿区 Markdown 必须有结构化 frontmatter，避免文档状态、来源、主题和归属不可检索。扫描契约在 `configs/markdown-frontmatter-compliance-contract.json`，测试入口是 `tests/test_markdown_frontmatter_compliance.py`。

本轮不批量改写历史文档正文。已有缺口全部标记为 `legacy_backfill_required`，后续按文档域分批补齐。

## 2. 扫描范围

- `docs/**/*.md`
- `drafts/**/*.md`

测试只扫描 git-tracked 文件，不扫描本地未跟踪草稿，避免 CI 和个人工作区状态耦合。

## 3. 必填字段

- `title`
- `doc_type`
- `module`
- `topic`
- `status`
- `created`
- `updated`
- `owner`
- `source`

允许值：

- `doc_type`：`prd`、`workflow`、`api`、`architecture`、`knowledge`、`analysis`、`other`
- `status`：`draft`、`review`、`stable`、`deprecated`、`archived`
- `source`：`human`、`ai`、`human+ai`

## 4. 当前 legacy_frontmatter_exceptions

以下文件是已登记的历史缺口。新增文件不得加入此列表，除非它本身是历史迁移对象且有明确 backfill 计划。

- `docs/architecture/adr/001-dual-runtime.md`
- `docs/architecture/adr/002-two-layer-auth.md`
- `docs/architecture/adr/003-db-strategy.md`
- `docs/architecture/adr/004-s3-copyright-fingerprint.md`
- `docs/architecture/adr/005-poster-extraction-everywhere.md`
- `docs/architecture/adr/006-c2pa-content-credentials.md`
- `docs/architecture/adr/007-defer-llm-director-planner.md`
- `docs/architecture/adr/README.md`
- `docs/architecture/api-assets-pg-cutover-2026-05-15.md`
- `docs/architecture/chain-fault-tolerance-design-2026-05-15.md`
- `docs/architecture/multi-agent-video-system-design.md`
- `docs/architecture/poyo-model-matrix-stable.md`
- `docs/architecture/product-architecture.md`
- `docs/architecture/quality-score-feedback-loop-2026-05-15.md`
- `docs/claude/known-gaps-stable.md`
- `docs/claude/project-standard-stable.md`
- `docs/claude/updates/project-updates-202605-stable.md`
- `docs/demo/run-book.md`
- `docs/deploy/cloudbase.md`
- `docs/design/asset-lifecycle-state-machine.md`
- `docs/design/information-architecture-v2.md`
- `docs/guide/M9/product_calibration.md`
- `docs/guide/UI_design_info/Fortune_Red_Cinema_Design_System.md`
- `docs/guide/quick-start.md`
- `docs/guide/从计划表到复盘-端到端-业务工作流.md`
- `docs/knowledge/user-guide.md`
- `docs/product/2026-04-30-momcozy-brand-ui-plan.md`
- `docs/product/brand-asset-template.md`
- `docs/product/momcozy-brand-brief.md`
- `docs/reference/api-endpoints.md`
- `docs/release/v0.4.0-NO-GO-procedure.md`
- `docs/release/v0.4.0-announcement-templates.md`
- `docs/release/v0.4.0-day-by-day-checklist.md`
- `docs/release/v0.4.0.md`
- `docs/research/api-platform-comparison-2026-04-29.md`
- `docs/research/dual-architecture-plan.md`
- `docs/research/pro-architecture-final.md`
- `docs/research/three-tier-architecture-western-video.md`
- `docs/runbooks/README.md`
- `docs/runbooks/brand-assets-refresh.md`
- `docs/runbooks/c2pa-cert-application.md`
- `docs/runbooks/db-pool-exhausted.md`
- `docs/runbooks/deepseek-timeout.md`
- `docs/runbooks/github-actions-deploy-secrets.md`
- `docs/runbooks/github-deploy-secrets-setup.md`
- `docs/runbooks/key-rotation.md`
- `docs/runbooks/phase1-signoff-checklist.md`
- `docs/runbooks/pipeline-stuck.md`
- `docs/runbooks/poyo-rejection.md`
- `docs/runbooks/thumbnail-missing.md`
- `docs/superpowers/plans/2026-05-20-s1-continuity-storyboard.md`
- `docs/superpowers/specs/2026-04-30-layer5-distribution-design.md`
- `docs/superpowers/specs/2026-04-30-layer5-implementation-plan.md`
- `docs/superpowers/specs/2026-05-06-admin-panel-design.md`
- `docs/superpowers/specs/2026-05-06-production-readiness-framework.md`
- `docs/workflows/2026-05-01-integration-test-report-stable.md`
- `docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md`
- `docs/workflows/2026-05-15-sprint-0-3-review-and-deploy-plan.md`
- `docs/workflows/brand-story-workflow.md`
- `docs/workflows/deploy-lighthouse-stable.md`
- `docs/workflows/deploy-test-sop-stable.md`
- `docs/workflows/portfolio-ops-stable.md`

## 5. 修复流程

先更新目标文档 frontmatter，再从 `legacy_frontmatter_exceptions` 删除该路径，并运行：

```bash
.venv/bin/python -m pytest tests/test_markdown_frontmatter_compliance.py -q
```

如果新增 Markdown 文档失败，不要把新文件加入 legacy 例外；直接补齐 frontmatter。
