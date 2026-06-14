---
title: Regenerate Downstream Invalidation Contract
doc_type: workflow
module: backend
topic: regenerate-downstream-invalidation
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Regenerate Downstream Invalidation Contract

## 触发场景

修改 `/scenario/{scenario}/regenerate/{label}/{step_name}`、`invalidate_downstream()`、S1-S5 step order、gate definitions、gate candidate 生成或前端 regenerate 按钮时，先检查本契约。

## 影响范围

Regenerate 会让当前 step 的输出发生变化。所有下游 step 以及由当前/下游 step 触发的 gate candidates 都依赖旧输入，必须失效。否则用户重生成脚本、关键帧或 prompts 后，系统可能继续使用旧候选项、旧审批结果或旧 final review。

## 预期 MTTR

5-10 min。大多数漂移能通过本地 state invalidation contract test 定位。

## 当前契约

机器可读契约：`configs/regenerate-downstream-invalidation-contract.yaml`

行为规则：

- 被 regenerate 的 step 本身先保持现状，随后由 `StepRunner.regenerate_step()` 重跑。
- 该 step 后面的所有 downstream steps 置为 `pending`，清空 `output/edited_output`，写入 `invalidated_by`。
- 当前 step 及 downstream step 触发的 gate 必须从 `state.gates` 删除。
- 上游 gate 必须保留。
- 被删除的 gate 写入 `state.invalidated_gates`，用于诊断和前端刷新。

## 相关代码

- [`src/pipeline/step_editor.py`](../../src/pipeline/step_editor.py) — downstream step/gate invalidation。
- [`src/pipeline/gate_manager.py`](../../src/pipeline/gate_manager.py) — S1-S5 gate definitions。
- [`src/routers/scenario.py`](../../src/routers/scenario.py) — regenerate route。
- [`tests/test_regenerate_downstream_invalidation_contract.py`](../../tests/test_regenerate_downstream_invalidation_contract.py) — state/gate invalidation contract。
- [`tests/test_scenario_step_regenerate_router.py`](../../tests/test_scenario_step_regenerate_router.py) — router regenerate coverage。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_regenerate_downstream_invalidation_contract.py tests/test_scenario_step_regenerate_router.py -q
```

该测试只读写 pytest 临时目录中的 state JSON，不访问生产，不触发 `/api/fast/*`、`/scenario/*` 真实生成、gate candidate 生成、上传、发布或外部 provider。

## 分类响应

- 下游 step 仍是 `done`：检查 `invalidate_downstream()` 是否使用 `scenario_config` 的当前 step order。
- 旧 gate candidates 仍存在：检查 gate definitions 的 `after_step` 是否在当前 step 或 downstream steps 中，并从 `state.gates` 删除。
- 上游 gate 被误删：检查 invalidation 范围是否包含了 regenerated step 之前的 steps。
- `current_step` 不正确：应指向第一个 pending step，通常是 regenerated step 的下一个 step。

## 永久 fix

1. Step invalidation 与 gate invalidation 必须使用同一个场景 step order。
2. 新增 gate definition 时同步覆盖 regenerate invalidation 测试。
3. 不要用真实生成接口验证该契约；本地 state JSON 足够覆盖风险。
