---
title: Scenario State Persistence Schema Contract
doc_type: workflow
module: backend
topic: scenario-state-persistence
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Scenario State Persistence Schema Contract

## 触发场景

修改 `StepRunner.init_state()`、`PipelineStateManager.save/load()`、S1-S5 step order、gate state、PG state projection 或本地 filesystem fallback 时，先检查本契约。

## 影响范围

S1-S5 的 step-by-step、gate approve、regenerate、legacy `/pipeline/*` proxy、前端进度展示和恢复执行都依赖 state JSON。filesystem 与 PostgreSQL 形态不一致会导致本地测试通过但生产恢复失败，或生产恢复正常但本地 fallback 丢字段。

## 预期 MTTR

5-10 min。大多数漂移能通过本地 contract test 定位。

## 当前契约

机器可读契约：`configs/scenario-state-persistence-contract.yaml`

初始化 state 必须包含：

- `schema_version`
- `label`
- `scenario`
- `tenant_id`
- `config`
- `steps`
- `current_step`
- `mode`
- `trace_id`
- `errors`
- `media_synthesis_errors`
- `gates`
- `pipeline_degraded`
- `degraded_reason`
- `structured_errors`

默认空值必须稳定：

- `gates` 是 `{}`，不是缺失字段。
- `errors`、`media_synthesis_errors`、`structured_errors` 是 `[]`。
- `pipeline_degraded` 是 `false`。
- `degraded_reason` 是 `null`。

## 相关代码

- [`src/pipeline/step_runner.py`](../../src/pipeline/step_runner.py) — S1-S5 初始 state shape。
- [`src/pipeline/state_manager.py`](../../src/pipeline/state_manager.py) — filesystem / PostgreSQL 双写与读取。
- [`src/pipeline/scenario_config.py`](../../src/pipeline/scenario_config.py) — S1-S5 step order 单一来源。
- [`src/pipeline/gate_manager.py`](../../src/pipeline/gate_manager.py) — gate state 写入与 approve 推进。
- [`tests/test_scenario_state_persistence_schema_contract.py`](../../tests/test_scenario_state_persistence_schema_contract.py) — hermetic schema contract。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_scenario_state_persistence_schema_contract.py -q
```

该测试只调用 `StepRunner.init_state()` 并读取 pytest 临时目录里的 JSON 文件，不访问生产，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 分类响应

- 缺少顶层字段：优先修 `StepRunner.init_state()`，让 filesystem 初始 state 与 PG load 形态一致。
- step order 漂移：修 `src/pipeline/scenario_config.py` 或调用方，不在测试里硬编码新顺序。
- `gates` 缺失：初始化时写 `{}`；后续 gate manager 再写具体 gate，不依赖字段缺失表达状态。
- degraded 字段缺失：初始化时写 `pipeline_degraded=false`、`degraded_reason=null`、`structured_errors=[]`，避免恢复执行时根据缺失字段猜状态。
- contract 配置漂移：先更新 `configs/scenario-state-persistence-contract.yaml`，再补测试和本 runbook。

## 永久 fix

1. 新增 state 字段时先更新 contract YAML。
2. filesystem save、PG save、PG load 和 PG backfill 必须保持字段集合一致。
3. 前端或 legacy proxy 不要依赖字段缺失表达默认值。
4. schema contract 只能使用本地临时 state，不用真实生成接口验证。
