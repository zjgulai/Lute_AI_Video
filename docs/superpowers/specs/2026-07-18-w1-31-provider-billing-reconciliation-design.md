---
title: W1-31 单样本 Provider Billing Reconciliation 设计
doc_type: architecture
module: backend-operations
topic: provider-billing-reconciliation
status: stable
created: 2026-07-18
updated: 2026-07-18
owner: self
source: human+ai
---

# W1-31 单样本 Provider Billing Reconciliation 设计

## 1. 目标与证据边界

W1-31 只执行一个 PoYo `gpt-image-2` 文生图样本，并核对三份独立事实：

1. 当前官方价格：`low` + `1K` + 1 image = 2 credits = `$0.01`；
2. 同一 provider task terminal status 返回的 `credits_amount`；
3. 本地 durable provider-cost ledger 的 reservation、settlement 与 conservation。

三者完全一致时，只允许声明 `single_task_charge_reconciled=true`。本任务不读取或
声明月账单、发票、全账户余额、生产数据库、发布、交付或全链路 acceptance；因此
`invoice_reconciliation=false`、`production unchanged` 始终成立。

## 2. 精确样本

| 字段 | 冻结值 |
|---|---|
| provider / endpoint | `poyo` / `https://api.poyo.ai` |
| model | `gpt-image-2` |
| workflow | text-to-image |
| quality / size / effective resolution | `low` / `1:1` / `1K` |
| output count | exactly 1 image |
| expected provider charge | `2_000_000` microcredits = 2 credits |
| expected ledger charge | `10_000_000` USD nanos = `$0.01` |
| hard cap | exactly `$0.01` |
| mutation retries | `0` |
| prompt | code-owned neutral calibration prompt; never logged or persisted in evidence |

价格页面和 API 文档必须在 live preflight 当日重新核验。若官方合同变化，停止执行并
更新规格/catalog；不得通过放宽比较或扩大预算继续。

## 3. 授权与 one-shot

Live record 必须是私有 JSON，位于 `tmp/` 或仓库外，并绑定：

- exact scope `w1-31-provider-billing-reconciliation`；
- 两个不同的具体人类身份 `approved_by` / `confirmed_by`；
- exact provider/model/sample/charge/cap；
- 第二确认人于 30 分钟内人工核验的可用 credits，至少覆盖 2 credits；
- `max_provider_calls=1`、`max_retries=0`；
- exact authorization statement、UTC approval/expiry；
- 当前官方价格证据 URL 与检查时间。

执行器在 provider client construction 前以 `O_CREAT|O_EXCL` 写入 `0600` consumption
marker。marker 一旦存在，本 record 永久不可再次执行；即使进程在 submit 前崩溃，也
必须重新取得新的 exact authorization，不能修复后复用。

## 4. 执行顺序

1. 严格解析私有 record，拒绝 duplicate key、float/NaN/Infinity、未知字段、模板值、
   身份相同、过期、价格/样本/cap 不一致；
2. 只检查 `POYO_API_KEY` 是否非空，不打印值；
3. 原子消费 approval-ID-bound one-shot marker；
4. 创建独立 `tmp/` run directory 与 SQLite ledger；不读取 `DATABASE_URL` 或生产 DSN；
5. 创建 effective cap `$0.01` 的 validated provider budget authorization；
6. 绑定 server-owned execution context，写 durable reserve 与
   `submission_started`；
7. 调用 canonical `GPTImageClient`，mutation 最多一次；
8. 只读 poll 同一个 task；terminal charge 缺失/非法/不一致进入现有
   `ambiguous`/`accounting_error`，不重发；
9. 从 repository readback account/attempt，比较 expected/provider/ledger 三方事实；
10. 输出不含 key、prompt、provider body、artifact URL 或绝对路径的 JSON summary。

进程退出后使用 `scripts/read_w1_31_billing_ledger.py` 只读打开同一 SQLite 文件；该
命令不加载 credential/config、不调用 provider，可用于崩溃后核对 durable state。

## 5. 失败语义

- Preflight failure：`provider_call_executed=false`，record 不消费；
- marker 创建失败/已存在：阻断，不构造 provider client；
- submit acknowledgement 不确定：保留 `ambiguous`，marker 已消费，不重试；
- terminal charge 不一致：保留 `accounting_error`，不伪造 reconciliation；
- provider settled 但 artifact download/probe 失败：保留 settled charge，报告 artifact
  failure；不重发；
- summary 写入失败：不改变 provider/ledger truth，marker 仍证明 authority 已消费。

## 6. 验证与审查

Fixture tests 必须证明 exact record、dual confirmation、expiry、key-presence-only、
one-shot crash/replay、单 mutation、三方一致/不一致、safe serialization、SQLite restart
readback 和 canonical no-retry。实现完成后，由独立只读线程从需求完整性、逻辑正确性、
边界情况、代码质量、测试覆盖、实际运行结果六方面审查；主线程修复并让同一审查线程
复验，直至 `PASS / APPROVE` 或记录明确 blocker。
