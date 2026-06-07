---
title: POYO 内容审核触发词回灌清单
doc_type: knowledge
module: quality
topic: poyo-content-moderation
status: stable
created: 2026-06-07
updated: 2026-06-07
owner: self
source: human+ai
---

# POYO 内容审核触发词回灌清单

本清单用于 P2-2 内容审核样本回灌：新增触发词先入 `poyo_safety.py` 的
`_SUBSTITUTIONS`，再补充到 `tests/fixtures/commercial_video/poyo_content_rejection_samples.json`。

## 已知触发词（当前）

| 触发词 | 替换词 | 备注 |
|---|---|---|
| breast pump | wearable wellness device | 规避 `breast pump` 拒绝 |
| breastfeeding | feeding | 与喂养语义对齐 |
| lactation | wellness | 语义保留 |
| baby bottle | infant feeding container | 触发概率较高 |
| nipple | feeding tip | 与物理部件语义保留 |
| formula milk | prepared nutrition | 低风险替换 |
| postpartum | new parent | 场景语义保留 |
| 吸奶器 | 可穿戴设备 | 母婴中文高频词 |
| 奶瓶 | 婴儿容器 | 中文复合词替换 |
| 奶嘴 | 喂养配件 | 避免二级拒绝 |
| 产后 | 恢复期 | 中文泛化替换 |

## 回灌与追踪

- `docs/runbooks/poyo-rejection.md`：处理流程与归因。
- `tests/fixtures/commercial_video/poyo_content_rejection_samples.json`：回灌样本（运行时用于单测）。
- `tests/test_poyo_safety.py`：抽样/回灌样本覆盖。
- `tests/test_negative_integration.py`：`content_moderation`/`content_violation`/`safety_block` 消息分类覆盖。

## 维护规则

1. 新词入库后先补 fixture，再补对应替换规则。
2. 规则变更需补 `tests/test_poyo_safety.py` 至少 1 条回归。
3. 30 天内新增 ≥ 5 个新词，触发一次 runbook 风险复核。
