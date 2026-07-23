---
title: Scenario State Persistence Schema Contract
doc_type: workflow
module: backend
topic: scenario-state-persistence
status: stable
created: 2026-06-01
updated: 2026-07-22
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
- `regenerate_chain`
- `soft_degraded_reasons`

默认空值必须稳定：

- `gates` 是 `{}`，不是缺失字段。
- `errors`、`media_synthesis_errors`、`structured_errors`、`regenerate_chain`、
  `soft_degraded_reasons` 是 `[]`。
- `pipeline_degraded` 是 `false`。
- `degraded_reason` 是 `null`。

`config.pipeline_completion_metric_v1` 是 server-owned 的 terminal metric claim：初始化
state 不得由 caller 预置；只有 `completed_bounded`、`completed_full`、`policy_blocked` 或
`pipeline_degraded=true` 的终态可以写入。claim 必须先 durable save，再发射一次
Prometheus completion；相同 state/label 的重复 `resume()` 看到有效 claim 后不得重复增加
counter。该顺序优先防止重复告警；如果进程在 claim 保存后、metric 发射前崩溃，可能漏掉一次
进程内 counter，因此它不是跨存储事务的 exactly-once outbox 证明。

质量回退状态写入 `config.quality_rewind`，仅允许四个字段：

- `upstream_step`：必须实际重跑的上游 step。
- `consumer_step`：发出回退信号且在上游成功前被阻塞的消费 step。
- `attempt`：从 `1` 开始，最大值为 `2`。
- `status`：只允许 `awaiting_upstream` 或 `upstream_completed`。

`resume()` 在消费 step 发出回退后必须立即返回；无论走 `run_step()` 还是
`regenerate_step()`，上游成功前都不能再次执行消费 step，也不能先创建新的 regeneration
epoch。上游成功后状态转为 `upstream_completed`，消费 step 成功后删除该 envelope。
filesystem、SQLite 与 PostgreSQL 都必须原样保存这个 envelope，重启不能把它当成完成或丢弃。

回退次数的 SSOT 是上游 step 持久化的 `_quality_attempt`，signal 的 `attempt` 只做一致性校验；
回退、跳跃、缺失、错误类型或达到上限都以 `quality_rewind_attempt_invalid` 在创建 epoch 前
fail-closed。有效回退先更新 audit chain、两个 step 状态、cursor 和 envelope，再由
`persist_trusted_regeneration_epoch()` 把新 epoch 与完整状态机写入同一次首次 durable save。
未知、空值或错误类型 upstream 使用 `quality_rewind_upstream_invalid` 降级并把 consumer 标记为
`error`，不能标记为完成。

两个审计数组共用严格 persistence validator：字段存在时必须是“对象元素组成的 JSON array”；
`{}`、字符串、`[1]`、`null` 均触发稳定 `scenario_state_integrity_error:<field>`，PG 错误不得回退到
filesystem。旧 filesystem state 缺少字段时保持原 shape，由 API legacy default 投影为空数组；
旧 PG column 缺失时 repository edge 显式补 `[]`。这两个仅限字段缺失的 legacy edge 不适用于
任何错误类型值。

## 相关代码

- [`src/pipeline/step_runner.py`](../../src/pipeline/step_runner.py) — S1-S5 初始 state shape。
- [`src/pipeline/state_manager.py`](../../src/pipeline/state_manager.py) — filesystem / PostgreSQL 双写与读取。
- [`src/pipeline/scenario_config.py`](../../src/pipeline/scenario_config.py) — S1-S5 step order 单一来源。
- [`src/pipeline/gate_manager.py`](../../src/pipeline/gate_manager.py) — gate state 写入与 approve 推进。
- [`tests/test_scenario_state_persistence_schema_contract.py`](../../tests/test_scenario_state_persistence_schema_contract.py) — hermetic schema contract。

## 立即诊断

```bash
.venv/bin/python -m pytest \
  tests/test_scenario_state_persistence_schema_contract.py \
  tests/test_quality_score_feedback.py -q
```

这些测试只使用 pytest 临时目录、测试 SQLite 或显式授权的 disposable PostgreSQL 18，
不访问生产，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 分类响应

- 缺少顶层字段：优先修 `StepRunner.init_state()`，让 filesystem 初始 state 与 PG load 形态一致。
- step order 漂移：修 `src/pipeline/scenario_config.py` 或调用方，不在测试里硬编码新顺序。
- `gates` 缺失：初始化时写 `{}`；后续 gate manager 再写具体 gate，不依赖字段缺失表达状态。
- degraded 字段缺失：初始化时写 `pipeline_degraded=false`、`degraded_reason=null`、`structured_errors=[]`，避免恢复执行时根据缺失字段猜状态。
- `quality_rewind` 丢失或提前清除：检查 state 是否绕过 `PipelineStateManager`，并验证 SQLite/PG
  load 前已经删除 filesystem cache，避免把文件读取误当成数据库回读。
- 消费 step 在回退期间可执行：检查 `run_step()`、`regenerate_step()` 与 `resume()` 是否都在
  provider epoch 或 step 执行前经过同一个 quality-rewind guard。
- 出现 `scenario_state_integrity_error:*`：停止恢复执行；定位产生坏 JSON 的 writer 或旧手工数据，
  不要把坏值改写为空数组，也不要依赖 filesystem cache 掩盖 PG 损坏。
- 出现 `quality_rewind_attempt_invalid`：对照 upstream `_quality_attempt`、signal `attempt` 和
  `regenerate_chain`；禁止手工重置计数或再次签发 epoch。
- contract 配置漂移：先更新 `configs/scenario-state-persistence-contract.yaml`，再补测试和本 runbook。

## 永久 fix

1. 新增 state 字段时先更新 contract YAML。
2. filesystem save、PG save、PG load 和 PG backfill 必须保持字段集合一致。
3. 前端或 legacy proxy 不要依赖字段缺失表达默认值。
4. `regenerate_chain` 是追加式审计记录；`quality_rewind` 是有限状态机，不能互相替代。
5. schema contract 只能使用本地临时 state 或受保护的 disposable database，不用真实生成接口验证。
