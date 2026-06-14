---
title: Gate Approve Idempotency Contract
doc_type: workflow
module: backend
topic: gate-approve-idempotency
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Gate Approve Idempotency Contract

## 触发场景

修改 gate approve、候选项选择、自动 resume、StepRunner background task、前端 gate 确认按钮或网络重试逻辑时，先检查本契约。

## 影响范围

Gate approve 是人工确认到继续执行的边界。用户双击、浏览器重试、移动网络重复提交或前端 retry 如果重复启动 background resume，会导致同一 label 被并发恢复、step 输出被重写、`approved_at` 被刷新，最终表现为进度跳动、重复生成或状态不可复现。

## 预期 MTTR

5-10 min。大多数问题能通过本地 idempotency contract test 定位。

## 当前契约

机器可读契约：`configs/gate-approve-idempotency-contract.yaml`

行为规则：

- 第一次 approve：写入选择、推进 `current_step`，router 启动一次 background resume。
- 相同 `selected_ids` 重复 approve：返回 `approved=true`、`idempotent=true`，不改 state，不启动 background resume。
- 不同 `selected_ids` 重复 approve：返回 conflict/error，不改 state，不启动 background resume。

## 相关代码

- [`src/pipeline/gate_manager.py`](../../src/pipeline/gate_manager.py) — `approve_gate()` 幂等判断和 state 写入。
- [`src/routers/scenario.py`](../../src/routers/scenario.py) — `approve_gate_decision()` background resume 启动点。
- [`tests/test_gate_approve_idempotency_contract.py`](../../tests/test_gate_approve_idempotency_contract.py) — 重复 approve 与 router 不重复 resume 契约。
- [`tests/test_s1_gate_full_flow.py`](../../tests/test_s1_gate_full_flow.py) — S1 gate approve 既有成功/错误路径。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_gate_approve_idempotency_contract.py tests/test_s1_gate_full_flow.py -q
```

该测试只读写 pytest 临时目录中的 state JSON，不访问生产，不触发 `/api/fast/*`、`/scenario/*` 真实生成、gate candidate 生成、上传、发布或外部 provider。

## 分类响应

- 重复 approve 返回 409：检查 `approve_gate()` 是否在 `approved=true` 且 `selected_ids` 相同时走 idempotent success。
- 重复 approve 启动 background resume：检查 router 是否在 `result["idempotent"] is True` 时直接返回。
- 重复 approve 改写 `approved_at`：检查幂等分支是否没有调用 `state_manager.save()`。
- 不同选择覆盖旧选择：必须保留 conflict/error，不允许 silent overwrite。

## 永久 fix

1. 所有 approve retry 必须先判断已批准状态。
2. 幂等分支不得写 state、不得记录新的 A/B choice、不得启动 background resume。
3. 前端可以安全重试相同 payload，但不能依赖不同 payload 覆盖已批准 gate。
4. 不要用真实生成接口验证该契约；本地 state 即可覆盖风险。
