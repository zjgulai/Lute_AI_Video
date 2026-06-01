---
title: Poyo model matrix stale warning
doc_type: workflow
module: architecture
topic: poyo-model-matrix
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Poyo Model Matrix Stale Warning

## 1. 适用范围

本 runbook 只处理 poyo 模型矩阵的“旧快照防误用”问题。当前矩阵文件是 [`docs/architecture/poyo-model-matrix-stable.md`](../architecture/poyo-model-matrix-stable.md)，代码对应物是 [`src/pipeline/model_thresholds.py`](../../src/pipeline/model_thresholds.py)。

机器可读契约：[`configs/poyo-model-matrix-stale-warning-contract.json`](../../configs/poyo-model-matrix-stale-warning-contract.json)。

## 2. 强制边界

- 该矩阵只能表达 `2026-05` catalog snapshot 与本项目阈值映射。
- 该矩阵不得被表述为 poyo.ai 当前最新模型目录、价格或审核规则。
- 充值、真实 token smoke、`RUN_TOKEN_SMOKE=1`、部署默认模型切换或成本测算前，先重新核对 poyo.ai 当前产品页面/API 文档。
- 本 runbook 不执行 poyo.ai 请求，不执行 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或任何外部 provider 调用。

## 3. 变更流程

1. 先确认本次改动是否只是文档措辞、阈值映射或 provider catalog 更新。
2. 如果涉及 provider catalog、价格、审核规则或默认模型，先人工核对 poyo.ai 当前产品页面/API 文档。
3. 同步更新 `docs/architecture/poyo-model-matrix-stable.md` 与 `src/pipeline/model_thresholds.py`，不能只改其中一个。
4. 如快照日期变化，同步更新 `configs/poyo-model-matrix-stale-warning-contract.json` 的 `snapshot_date` 和 `snapshot_catalog`。
5. 运行本地静态守卫，不用真实 key，不消耗 token。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_poyo_model_matrix_stale_warning.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_poyo_model_matrix_stale_warning.py tests/test_docs_link_check_scope.py
git diff --check
```

测试入口：[`tests/test_poyo_model_matrix_stale_warning.py`](../../tests/test_poyo_model_matrix_stale_warning.py)。

## 5. 失败处理

- 缺少快照警告：先补矩阵顶部 warning，再更新 contract 中的必需短语。
- link-check scope 失败：把本 runbook 保持在 `configs/docs-link-check-scope.txt` 和 `.github/workflows/ci.yml` 的 lychee 参数中。
- 充值前验证被误跳过：停止真实 smoke，不设置 `RUN_TOKEN_SMOKE=1`，先完成 poyo.ai 当前产品页面/API 文档重验。
