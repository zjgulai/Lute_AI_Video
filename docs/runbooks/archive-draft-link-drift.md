---
title: Archive and draft link drift
doc_type: workflow
module: project
topic: archive-draft-link-drift
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Archive and draft link drift

## 1. 目标

当前正式文档不得把 `archive/`、`drafts/`、`tmp/`、`.kiro/`、`docs/research/`、`docs/superpowers/plans/`、`docs/superpowers/specs/` 等历史或临时位置误导为当前执行入口。

治理契约在 `configs/archive-draft-link-drift-contract.json`，测试入口是 `tests/test_archive_draft_link_drift.py`。扫描范围来自 `configs/docs-link-check-scope.txt`，也就是当前阻断式文档链接检查范围。

## 2. 判定规则

- Markdown link 指向历史/草稿/临时路径时，必须在相邻语境中标明“历史”或“不作为当前执行入口”。
- Frontmatter `file:` 指向历史计划时，只能作为 provenance，不作为当前 TODO 或 SOP 入口。
- 新增当前计划必须写入 `docs/claude/known-gaps-stable.md` 的 TODO list，不得链接到 `.kiro/plan`、`drafts/` 或 `archive/` 作为执行入口。
- `historical_reference_only` 表示只保留审计追溯价值，不作为当前执行入口。

## 3. 当前允许的历史引用

| source | target | kind |
| --- | --- | --- |
| `docs/architecture/adr/004-s3-copyright-fingerprint.md` | `.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md` | markdown_link |
| `docs/architecture/api-assets-pg-cutover-2026-05-15.md` | `.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md` | frontmatter_file |
| `docs/claude/known-gaps-stable.md` | `superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md` | markdown_link |
| `docs/claude/updates/project-updates-202605-stable.md` | `.kiro/plan/BRAND-ASSETS-DIAGNOSIS-2026-05-11.md` | markdown_link |
| `docs/claude/updates/project-updates-202605-stable.md` | `.kiro/plan/DEPLOY-CHECKLIST-2026-05-12.md` | markdown_link |
| `docs/claude/updates/project-updates-202605-stable.md` | `.kiro/plan/NEXT-STEPS-2026-05-11.md` | markdown_link |
| `docs/claude/updates/project-updates-202605-stable.md` | `.kiro/plan/RECONCILIATION-2026-05-11.md` | markdown_link |
| `docs/claude/updates/project-updates-202605-stable.md` | `tmp/outputs/production-qa-2026-05-11` | markdown_link |
| `docs/runbooks/key-rotation.md` | `.kiro/plan/VULNERABILITIES-AND-PENDING-2026-05-15.md` | frontmatter_file |
| `docs/runbooks/phase1-signoff-checklist.md` | `.kiro/plan/MASTER-PLAN-STATUS-2026-05-17.md` | frontmatter_file |

这些引用全部是 `historical_reference_only`。如果后续 backfill、迁移或删除对应历史文档，先更新契约，再运行测试。

## 4. 修复流程

发现新增 drift 时先判断引用目的：

- 当前执行计划：改为链接 `docs/claude/known-gaps-stable.md` 或当前 runbook。
- 历史证据：保留链接，但补“历史 / 不作为当前执行入口”语境，并加入契约。
- 临时输出：优先迁移到正式证据文档；不能迁移时只允许作为历史证据引用。
- 草稿方案：晋升到正式文档后再从当前文档引用。

验证命令：

```bash
.venv/bin/python -m pytest tests/test_archive_draft_link_drift.py -q
```
