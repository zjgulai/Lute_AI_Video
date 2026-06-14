---
title: Workflow trigger path audit
doc_type: workflow
module: ci
topic: workflow-trigger-paths
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Workflow Trigger Path Audit

## 1. 适用范围

本 runbook 约束 GitHub Actions 中带 `paths` 过滤的专项 workflow。当前机器可读契约是 [`configs/workflow-trigger-path-audit-contract.json`](../../configs/workflow-trigger-path-audit-contract.json)，测试入口是 [`tests/test_workflow_trigger_path_audit.py`](../../tests/test_workflow_trigger_path_audit.py)。

## 2. 当前判断

- `.github/workflows/ci.yml` 是主质量门，不使用 `paths` 或 `paths-ignore`。
- `.github/workflows/e2e-ui.yml` 是 path-filtered workflow，必须覆盖 UI source、UI-only specs、`web/playwright.ui.config.ts`、`web/package.json` 和 `web/package-lock.json`。
- `.github/workflows/e2e-prod.yml` 是 path-filtered workflow，必须覆盖 production specs、`web/playwright.prod.config.ts`、`web/package.json` 和 `web/package-lock.json`。
- 不允许用 `web/**` 或 `**` 粗暴扩大专项 workflow；这会把高成本远程或视觉测试变成噪音。

## 3. 变更规则

1. 新增 path-filtered workflow 前，先在 contract 中登记 workflow、事件、required paths 和 forbidden paths。
2. 修改 Playwright config、E2E spec 目录或 package lock 位置时，同步更新 workflow paths 和 contract。
3. 主 CI 不加 path filter；它负责兜底所有代码、测试和配置变更。
4. 本守卫只做本地 YAML/JSON/Markdown 静态检查，不触发生产、不运行 Playwright、不消耗 poyo.ai tokens。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_workflow_trigger_path_audit.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_workflow_trigger_path_audit.py tests/test_docs_link_check_scope.py
git diff --check
```

## 5. 失败处理

- 缺 required path：先补 workflow，再补 contract；不要只放宽测试。
- 出现 forbidden path：改回精确目录或文件，避免专项 workflow 被无关变更触发。
- 如果确实需要扩大范围，先说明原因并在 contract 的 `reason` 中写清楚。
