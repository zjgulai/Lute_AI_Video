---
title: W1-31 Single-Sample Provider Billing Reconciliation Implementation Plan
doc_type: workflow
module: provider-cost
topic: w1-31-provider-billing-reconciliation
status: stable
created: 2026-07-18
updated: 2026-07-20
owner: self
source: human+ai
---

# W1-31 单样本 Provider Billing Reconciliation 实施计划

**目标：** 在不接触生产的前提下，增加一个 exact、private、durable one-shot runner，
最终以一次 PoYo `gpt-image-2` low/1K 调用核对官方价格、provider task charge 与本地
provider-cost ledger。

**证据边界：** 本地开发/fixture 为 L2；只有 exact live gate 全部通过并实际产生一条
logged provider side effect 才能达到本任务的 L4 single-task evidence。任何本地测试、
dry-run、credential presence 或 terminal poll 都不能单独冒充 live reconciliation。

## Task 1 — RED：冻结私有授权与 preflight

- [x] exact sample/cap/charge/scope/model/endpoint 合同测试；
- [x] 两个不同具体人类身份、UTC expiry、exact statement、官方证据 freshness；
- [x] duplicate key、未知字段、float/NaN/模板值、仓库内非 `tmp/` record 全部拒绝；
- [x] key 只检查 presence，输出永不含 value。

## Task 2 — GREEN：strict record builder 与 no-token report

- [x] 实现 strict immutable record parser；
- [x] 实现 private builder，默认 `0600`、不覆盖；
- [x] 实现 JSON preflight report，明确 supported/forbidden claims；
- [x] 不构造 provider client、不初始化账本、不发网络请求。

## Task 3 — RED/GREEN：durable one-shot 与 canonical execution

- [x] `O_EXCL` consumption marker 在 client construction 前创建；
- [x] marker 已存在、崩溃后重启、同 record 第二次执行均 fail closed；
- [x] 独立 SQLite ledger + exact `$0.01` validated authorization；
- [x] canonical `GPTImageClient` low/1K/one-image path；
- [x] mutation retry 固定为零，status/download 只针对同一 task；
- [x] provider/ledger 三方一致才输出 reconciled。

## Task 4 — 安全输出与失败真值

- [x] summary 不含 prompt、key、raw body、artifact URL、绝对路径；
- [x] ambiguous/accounting_error/settled-artifact-failure 不被包装成 success；
- [x] marker 与 SQLite ledger 可在 restart 后只读复核；
- [x] 不执行 production DB、deploy、publish、delivery 或 Git 动作。

## Task 5 — 验证、文档与独立审查

- [x] focused pytest、affected provider-cost regression、Ruff、Pyright、compile、diff、
  secret/log scan；
- [x] 同步 runbook、roadmap、Kiro、SDD report；
- [x] 两遍主线程自审；
- [x] 独立六维只读审查，修复清单回主线程，同一线程复验至通过。

## Task 6 — exact live gate

- [x] 当前官方价格/API 文档复核；
- [x] 私有双人 exact record；
- [x] `POYO_API_KEY` presence 与人工 funded-account evidence；
- [x] dry-run/preflight 全绿；
- [x] 只消费一次 record，最多一次 mutation；
- [ ] 三方对账并记录 L4 summary；任一失败则停止且不复用 authority。

**只读恢复入口：** `scripts/read_w1_31_billing_ledger.py` 仅打开 private run
directory 的 SQLite ledger，不加载 provider credential/config，也不执行 status 或
mutation。它不能恢复已消费 authority。
