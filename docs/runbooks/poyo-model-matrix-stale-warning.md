---
title: Poyo model matrix stale warning
doc_type: workflow
module: architecture
topic: poyo-model-matrix
status: stable
created: 2026-06-01
updated: 2026-06-06
owner: self
source: human+ai
---

# Poyo Model Matrix Stale Warning

## 1. 适用范围

本 runbook 只处理 poyo 模型矩阵的“旧快照防误用”问题。当前矩阵文件是 [`docs/architecture/poyo-model-matrix-stable.md`](../architecture/poyo-model-matrix-stable.md)，代码对应物是 [`src/pipeline/model_thresholds.py`](../../src/pipeline/model_thresholds.py)。

机器可读契约：[`configs/poyo-model-matrix-stale-warning-contract.json`](../../configs/poyo-model-matrix-stale-warning-contract.json)。

当前公开文档重验契约：[`configs/poyo-current-provider-revalidation-contract.json`](../../configs/poyo-current-provider-revalidation-contract.json)。

真实 smoke 最小样本计划契约：[`configs/authorized-live-token-smoke-sample-plan-contract.json`](../../configs/authorized-live-token-smoke-sample-plan-contract.json)。

## 2. 强制边界

- 该矩阵只能表达 `2026-05` catalog snapshot 与本项目阈值映射。
- 该矩阵不得被表述为 poyo.ai 当前最新模型目录、价格或审核规则。
- 充值、真实 token smoke、`RUN_TOKEN_SMOKE=1`、部署默认模型切换或成本测算前，先重新核对 poyo.ai 当前产品页面/API 文档。
- 本 runbook 不执行 poyo.ai 请求，不执行 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或任何外部 provider 调用。
- 2026-06-06 的公开文档重验只支持 `L1-public-doc-revalidation`，不得表述为 key 可用、余额充足、provider runtime 成功或商业交付完成。

## 3. 2026-06-06 公开文档重验摘要

来源：

- `https://docs.poyo.ai/api-manual/overview`
- `https://docs.poyo.ai/api-manual/video-series/seedance-2`
- `https://poyo.ai/models/seedance-2`
- `https://docs.poyo.ai/api-manual/image-series/gpt-image-2`
- `https://poyo.ai/models/gpt-image-2`
- `https://poyo.ai/changelog`

结论：

- API 仍采用 `https://api.poyo.ai`，统一异步提交和状态查询路径为 `/api/generate/submit` 与 `/api/generate/status/{task_id}`。
- `seedance-2` / `seedance-2-fast` 当前公开文档仍列为可用模型；`seedance-2` 支持 480p、720p、1080p，`seedance-2-fast` 支持 480p、720p。
- `seedance-2` 当前公开价格边界：720p text/image-to-video 为 `$0.20/sec`，1080p text/image-to-video 为 `$0.45/sec`；最低 video-input 档为 `$0.05/sec`。
- `gpt-image-2` / `gpt-image-2-edit` 当前公开文档仍列为可用；低质量 1K 为 `$0.01/gen`，高质量 4K 为 `$0.321/gen`。
- L4 approval record 必须包含 `provider_revalidation_ref=configs/poyo-current-provider-revalidation-contract.json`；缺失或不匹配时 preflight 必须 blocked。
- 第一轮 L4 smoke 的样本计划收紧为 Momcozy 消毒器 3 张 `gpt-image-2` 图片 + 1 条 `seedance-2` 15 秒 9:16 image-to-video，总预算止损上限 `$3.00`、单任务 `$2.50`、零自动重试。产物只进入 `pending_review` 素材库，不做 approved brand token、发布或商业交付验收。

## 4. 变更流程

1. 先确认本次改动是否只是文档措辞、阈值映射或 provider catalog 更新。
2. 如果涉及 provider catalog、价格、审核规则或默认模型，先人工核对 poyo.ai 当前产品页面/API 文档。
3. 同步更新 `docs/architecture/poyo-model-matrix-stable.md` 与 `src/pipeline/model_thresholds.py`，不能只改其中一个。
4. 如快照日期变化，同步更新 `configs/poyo-model-matrix-stale-warning-contract.json` 的 `snapshot_date` 和 `snapshot_catalog`。
5. 如真实 smoke 前的 provider 文档或样本范围发生变化，同步更新 `configs/poyo-current-provider-revalidation-contract.json`、`configs/authorized-live-token-smoke-sample-plan-contract.json` 和相关 preflight 测试。
6. 运行本地静态守卫，不用真实 key，不消耗 token。

## 5. 本地验证

```bash
.venv/bin/python -m pytest tests/test_poyo_model_matrix_stale_warning.py tests/test_token_smoke_preflight.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_poyo_model_matrix_stale_warning.py tests/test_token_smoke_preflight.py tests/test_docs_link_check_scope.py
git diff --check
```

测试入口：[`tests/test_poyo_model_matrix_stale_warning.py`](../../tests/test_poyo_model_matrix_stale_warning.py)。

## 6. 失败处理

- 缺少快照警告：先补矩阵顶部 warning，再更新 contract 中的必需短语。
- link-check scope 失败：把本 runbook 保持在 `configs/docs-link-check-scope.txt` 和 `.github/workflows/ci.yml` 的 lychee 参数中。
- 充值前验证被误跳过：停止真实 smoke，不设置 `RUN_TOKEN_SMOKE=1`，先完成 poyo.ai 当前产品页面/API 文档重验。
- `provider_revalidation_ref` 不匹配：停止真实 smoke，刷新公开文档重验契约或修正私有 approval record；不要手动绕过 preflight。
