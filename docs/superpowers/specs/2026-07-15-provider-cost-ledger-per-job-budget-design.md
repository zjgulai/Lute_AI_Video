---
title: W1-27–W1-30 Provider 成本账本与单任务硬预算设计
doc_type: architecture
module: backend-storage
topic: provider-cost-ledger-per-job-budget
status: approved
created: 2026-07-15
updated: 2026-07-15
owner: self
source: human+ai
---

# W1-27–W1-30 Provider 成本账本与单任务硬预算设计

## 1. 决策摘要

本规格只闭环路线图 W1-27–W1-30：

- 把进程内 `cost_tracker` 迁移为 PostgreSQL/SQLite 持久化账本；
- 按 provider 的真实计费维度保存 LLM token、TTS 输入 UTF-8 bytes、图片数量和视频
  task/时长事实；
- 让每次真实付费 mutation intent 恰好对应一条持久化 attempt；
- 在 provider mutation 前原子预留单任务预算，并让 hard cap 在并发和重启后
  仍然成立。

用户已逐节批准完整设计，并于 2026-07-15 明确批准本书面规格。实施计划前的
官方价格复核随后发现原 §9.3、§13.2 和测试矩阵中的 TTS duration 计费前提与
SiliconFlow 当前官方合同冲突；用户同日明确批准 §26 的证据修正。本规格现已把
TTS billing truth 全面修正为 exact provider-input UTF-8 bytes。随后对 DeepSeek
当前价格与 response schema 的交叉复核又发现 aggregate-only `llm_tokens.v1` 无法
区分 cache-hit/cache-miss input；用户同日明确批准 §27 的证据修正。本规格现已把
DeepSeek billing truth 全面修正为 exact cache-hit/cache-miss/output components 并
恢复 `approved`。实施 Task 0 后又发现 executable plan 对 PoYo GPT Image 2
medium/high 美元价格做了三位小数近似，而官方表格与同一行 credits 都保留四位
小数；这会破坏 exact billing truth。规格现暂停为
`pending_gpt_image_price_correction_approval`，§28 给出第三项证据修正提案。用户已于
2026-07-16 明确批准该修正；规格恢复 `approved`。该批准只允许重新执行 Task 0、
修正 RED matrix 并继续已批准的本地实现，仍不授权 provider 调用或生产动作。

固定决策如下：

1. W1-26 真实 publish/reconciliation 继续保持 `blocked_external`，不与本批
   合并。
2. W1-30 只建立“一租户、一 canonical job、一个 hard-cap account”。租户月度、
   rolling window、组织总额、预付余额和账户级余额均不在本批。
3. 采用中心化 `ProviderCostService`，不异步重写旧 tracker，也不引入
   outbox/worker。
4. 每条付费路径必须持有不可变的内部 `ProviderExecutionContext`。canonical
   async Fast/S1–S5 复用已持久化的 server-owned resource ID；同步和 legacy
   路径在任何 provider-capable 工作前创建 server-owned compatibility job ID。
5. 客户端 `output_label`、artifact label、请求体预算和客户端上报 spend 永远
   不是预算 authority 或 account key。
6. 新增 `job_budget_accounts` 和 `provider_cost_attempts` 两个持久化边界；
   monetary arithmetic 统一使用整数 USD nanos：
   `1 USD = 1_000_000_000 nanos`。
7. attempt 生命周期固定为 `reserved`、`submission_started`、`submitted`、
   `settled`、`released`、`ambiguous`、`accounting_error`。
8. provider mutation 前必须完成原子 reservation；成功按实际计费事实结算；
   只有明确未提交或明确不计费才能释放；不确定与会计错误继续占用 reservation。
9. 同一 logical operation + ordinal 只能有一个 attempt。相同 fingerprint
   重放只读已有状态；冲突或重启恢复不得重新提交 mutation。
10. `ProviderCostService` 永不重试 mutation。poll/status/download 可对同一
    provider task 做有界只读重试。
11. 价格来自仓库内、versioned、server-owned、精确 provider/model/operation/
    billing-kind 匹配的 catalog。mutation 路径不在线抓价，不允许 wildcard 或
    未知规则 fallback。
12. 真实 provider mutation 必须有显式、合法、正数的
    `PROVIDER_JOB_BUDGET_USD`。已验证的既有 authorization 只能降低这个
    server ceiling，不能抬高。
13. Stub、no-media 和明确 no-submit 分支不创建 provider attempt，成本为零；
    已提交、结果不明或已收费的 attempt 绝不能被 stub 覆盖。
14. 所有仍可到达的 paid LLM、PoYo、Seedance、GPT Image、CosyVoice、
    DALL-E、ElevenLabs 和 admin connectivity 路径，必须集成新服务或在网络前
    fail closed；禁止保留未记账 fallback。
15. 本批不新增 cost HTTP endpoint、前端预算编辑器或 public budget API。
    只提供 tenant-bound 的内部 service/repository readback。

路线 B（把旧 tracker 改为 async 并继续让各 client 自行记账）不能形成统一的
reserve/submit/settle transaction，也无法阻止 legacy 绕过，拒绝采用。

路线 C（先引入 outbox、队列和异步 billing worker）能扩大恢复能力，但会把本批
从成本安全边界扩成执行架构重写；W1-27–W1-30 不需要该复杂度，拒绝采用。

## 2. 背景与当前事实

### 2.1 路线图断点

当前连续可本地闭环的工作是：

- W1-27：持久化 cost ledger，绑定 tenant/job/attempt/provider/model；
- W1-28：按真实 provider billing facts 记账；
- W1-29：canonical paid paths 每次成功 attempt 恰好一条记录，stub 和明确
  未提交不计费；
- W1-30：submit 前原子预留，失败释放，重启后 hard cap 有效。

W1-26 需要真实平台 credential、单 post 授权、删除/回滚方案和人工验收；
W1-31 需要真实 provider billing 单样本对账。两者都保持 external gate。

### 2.2 当前实现缺口

仓库审计确认：

- `src/tools/cost_tracker.py` 使用 module-level list，最多保留 10,000 条，
  进程重启即丢失；
- 当前 identity 只有宽泛 `api` 和可选 `thread_id`，不绑定 tenant、
  canonical job、provider attempt、model、billing kind 或 external task ID；
- `LLMClient` 成功后按一个 unit 计费，且在返回 content 前丢失 provider usage；
- `PoyoClient.submit_poll_download()` 把 image 路径误记为
  `poyo_video`，并在 download 完成后才记账；
- Seedance native image-to-video 和部分 PoYo-backed 路径没有账本记录；
- CosyVoice 按一个 unit 计费，没有保存 exact provider-input UTF-8 byte count；
- 若 provider 已成功但 download、artifact verification 或后续业务步骤失败，
  当前路径可能完全不记成本；
- `StepRunner.check_budget()` 只检查进程内已记录值，只覆盖 Expert mode，
  检查与 provider submit 不是同一 transaction；
- generic retry helper 仍可能把 mutation 与 poll/download 包在同一重试范围；
- legacy DALL-E、ElevenLabs 和 admin provider connectivity 仍可到达付费
  mutation。

所以现有实现不能证明 exactly-once accounting、并发 hard cap、重启恢复或真实
billing-unit truth。

## 3. 目标、非目标与证据上限

### 3.1 目标

- 建立 tenant-bound、job-bound、restart-safe 的预算 account；
- 在 provider mutation 前用一个数据库 transaction 原子预留预算；
- 每个真实 outbound mutation intent 建立一条 durable attempt；
- 冻结 attempt 使用的 provider、canonical model、operation、billing kind、
  price rule 和 reservation facts；
- 对同步与异步 provider 分别定义可验证的 success、settlement 和 failure
  位置；
- 把 mutation retry 收敛为零，同时保留同一 async task 的只读恢复；
- 所有 paid paths 都受相同 execution context、budget 和 ledger gate；
- PostgreSQL 18 与 SQLite 使用相同的状态机和 conservation invariant；
- 通过 fake transport、disposable PostgreSQL 18 和本地 restart/concurrency
  测试形成 L1/L2 证据。

### 3.2 非目标

- 不建立 tenant monthly budget、organization budget、rolling window、
  prepaid credit、account balance 或账单系统；
- 不建立 public cost API、budget mutation API、前端 budget/spend UI；
- 不在线获取 provider price，不把 provider price page 当运行时依赖；
- 不对旧进程内 `_records` 做 backfill；
- 不执行真实 provider、真实 billing、production publish、production migration、
  deploy、SSH、credential 或 secret 操作；
- 不证明 provider invoice、credit、tax、折扣、汇率或账单最终一致；
- 不自动恢复 ambiguous submission，不自动重提 mutation；
- 不引入 outbox、message broker、billing worker 或多币种；
- 不改变 artifact acceptance、publish authority、transparency 或 metrics 合同；
- 不把 W1-31 billing reconciliation 合并为本地完成声明。

### 3.3 完成状态与固定边界

实现、验证和独立复核全部通过时，本批最高只能标为 `completed_local`。如果实现
完成但独立复核未完成，状态必须是：

- `implementation_complete_local / independent_review_pending`
- `independent_review=false`

无论本地结果如何，固定边界都是：

- `production unchanged`
- `provider_call=false`
- `provider_attempt_made=false`
- `real_connector_call=false`
- `database_write=local-test-only`
- `live_publish=false`
- `live_send=false`
- `billing_reconciliation=false`

## 4. 核心不变量

### 4.1 Authority

1. tenant、budget job ID、cap、budget source 和 policy version 都由服务端产生或
   验证；
2. 浏览器和普通 HTTP request body 不能选择 account ID、job key、cap、spend、
   price rule 或 attempt ordinal；
3. paid path 缺少完整 `ProviderExecutionContext` 时，在 provider client
   mutation 构造或发送前失败；
4. account 创建后，tenant/job/scenario/cap/source/policy identity 不可变；
5. authorization object 只能降低 server cap，不能扩大权限；
6. no-media/stub 分支不能伪装为真实 paid success，真实 paid failure 也不能降级
   成 stub success。

### 4.2 Conservation

对每个 account 始终满足：

~~~text
0 < cap_usd_nanos
0 <= reserved_usd_nanos
0 <= settled_usd_nanos
reserved_usd_nanos + settled_usd_nanos <= cap_usd_nanos
~~~

规则：

- reserve 增加 account 的 `reserved_usd_nanos`；
- settle 释放该 attempt 的完整 reservation，并把合法 actual cost 增加到
  `settled_usd_nanos`；
- release 只释放完整 reservation，不增加 settled；
- ambiguous、submitted 和 accounting_error 保持 reservation；
- 任意 transition 失败必须 rollback account 与 attempt 的全部变化；
- 任何计算 overflow、负数、float、非法精度或不完整事实都 fail closed。

### 4.3 Exactly-once

1. 每个 outbound paid mutation intent 只有一个 server-owned attempt UUID；
2. 每个 account 内 `logical_operation + ordinal` 唯一；
3. 相同 operation key 的重放必须匹配完整 immutable fingerprint；
4. fingerprint 相同则返回 durable attempt，不发送第二次 mutation；
5. fingerprint 不同则返回 conflict，不修改 account，不发送网络；
6. `released`、`ambiguous`、`accounting_error`、`submitted` 或 `settled`
   attempt 都不能用相同 ordinal 再提交；
7. 用户或系统未来明确授权 regeneration 时，必须使用新的 ordinal 和新的
   reservation；server-owned `regeneration_epoch_ref` 属于 mutation-intent
   fingerprint，因此即使 prompt 与 slot 完全相同，不同 epoch 也不会被误判为
   原 attempt replay；
8. 同一 trusted regeneration epoch 在同一 account + logical operation 下只能
   消费一次；相同 fingerprint 仍只读 replay，不重复消费；同一 epoch 可以为
   不同 server-owned operation slots 各自授权一次；
9. 本账本的 exactly-once 是本系统 mutation intent 与 accounting identity
   的 exactly-once，不虚构 provider 端天然支持幂等。

### 4.4 数据最小化

账本允许保存：

- tenant/job/attempt 的 bounded internal identifier；
- provider、canonical model、allowlisted billing region、operation、media/billing
  kind；
- integer billing facts、integer nanos、price rule identity；
- bounded external task/trace identifier；
- stable safe error code 和 lifecycle timestamp。

账本禁止保存：

- prompt、script、用户输入、产品文案；
- secret、token、credential、authorization header；
- 原始 provider request/response body；
- 音视频、图片或 artifact bytes；
- 本地绝对路径；
- 未清洗的 provider error/message/traceback；
- 任意 PII 或可变的客户端上报 spend。

## 5. 总体架构

### 5.1 组件

~~~text
Canonical/Compatibility Job Creation
              |
              v
ProviderExecutionContext
              |
              v
ProviderCostService ----> Versioned Price Catalog
       |                         |
       v                         v
ProviderCostRepository <-> Billing-Fact Adapters
       |
       +--> job_budget_accounts
       +--> provider_cost_attempts
       |
       v
One provider mutation -> sync settle OR async submitted/poll/settle
~~~

职责分离：

- `ProviderExecutionContext`：携带 server-owned execution/budget authority；
- `ProviderCostService`：校验、reserve、transition、settle、release 和安全
  readback，不执行自动 retry；
- `ProviderCostRepository`：实现 account/attempt 的原子 CAS 与 conservation；
- billing-fact adapter：从 provider 特定 response、task truth 或确定性媒体测量中
  提取严格事实；
- price catalog：把严格事实映射为 reservation upper bound 与 settlement cost；
- provider client：只执行一条已授权 mutation，并把结构化结果交回 service。

### 5.2 为什么不复用 BaseRepository

该边界需要：

- account 与 attempt 同时加锁；
- reserve/check/create 必须是一个 transaction；
- transition 需要 state-specific compare-and-set；
- PostgreSQL 与 SQLite 都要阻止并发 overspend；
- stored truth 解析异常必须 fail closed。

因此使用 specialized repository。不能采用 BaseRepository 的普通
read-then-write 模式，也不能先查余额再单独 insert attempt。

### 5.3 无新 HTTP surface

本批不新增 cost/budget route。内部 readback 用于：

- 当前 job 的 account conservation 检查；
- attempt lifecycle 与安全错误码审计；
- 本地测试、runbook 和后续 W1-31 reconciliation 输入。

HTTP 入口仍使用既有 tenant/auth boundary；只在内部创建 execution context 和
预算 account。不得把 repository model 直接暴露给浏览器。

## 6. ProviderExecutionContext 与 job identity

### 6.1 不可变字段

内部 context 至少包含：

- `tenant_id`；
- `budget_job_kind`；
- `budget_job_id`；
- `scenario_or_resource_type`；
- `effective_cap_usd_nanos`；
- `budget_source_kind`；
- `budget_policy_version`；
- 可选的 trusted authorization reference；
- 当前 generation/policy version；
- mutation retry cap，W1-27–W1-30 固定为零。

context 必须使用不可变模型；进入 provider-capable call graph 后不得由普通 dict
或 request payload 覆盖。

### 6.2 Canonical async jobs

以下路径复用提交幂等层已预分配并持久化的 server-owned resource ID：

- `POST /fast/submit` 的 task ID；
- `POST /scenario/{scenario}/submit` 的 scenario resource ID/label。

account identity 为 tenant + bounded job kind + server-owned resource ID。
同一幂等提交重放必须得到同一 budget account。

### 6.3 同步与 legacy compatibility jobs

仍能触发 provider 的同步或 legacy 路径，必须在 provider-capable 工作开始前创建
新的 server-owned compatibility job ID，并持久化 account：

- synchronous Fast generation；
- direct scenario execution；
- legacy pipeline start；
- legacy paid skill/agent entrypoint；
- admin provider connectivity。

客户端 `output_label` 只能继续作为展示或 artifact metadata。即使格式合法，
也不能成为 budget job ID。

无法建立 tenant-bound compatibility identity 的 legacy path 必须 zero-network
fail closed；不能回退到旧 tracker。

## 7. 预算来源与 account 初始化

### 7.1 Server ceiling

真实 provider mutation 必须有 `PROVIDER_JOB_BUDGET_USD`。解析规则：

- 只接受 canonical positive decimal string；
- 最多 9 位小数，精确转换为 USD nanos；
- 拒绝 float、scientific notation、`NaN`、`Infinity`、符号歧义、空白和
  overflow；
- 转换结果必须大于零并可安全存入 signed 64-bit integer；
- 缺失或非法配置时，所有真实 paid mutation 在网络前失败。

`.env.example` 可以用注释示例记录历史 `5.00`，但运行时没有隐式
`$5.00` fallback。测试只能通过明确 dependency/config injection 提供 cap。

### 7.2 Trusted authorization

现有 L4/token-smoke approval 可在 trusted in-process harness 中被既有严格
validator 解析成不可变 authorization object。普通 HTTP 不得提交文件路径、
approval JSON 或预算字段。

存在合法 authorization 时：

~~~text
effective_cap =
  min(
    server_job_cap,
    authorization_budget_limit,
    authorization_per_job_cost_ceiling
  )
~~~

缺少某个非必填 approval ceiling 时只忽略该项；server job cap 永远必须存在。
任何 approval 过期、绑定不符、字段非法或校验失败都在网络前失败。

现有 token-smoke preflight 的 `float` budget projection 只能保留作兼容展示，不能
成为 nanos hard-cap authority。Trusted adapter 必须从原始、已授权的 approval JSON
使用 Decimal hooks 重新解析，验证 `budget_limit` display string、
`budget_limit_usd`、`max_total_cost_usd` 与 `per_job_cost_ceiling_usd` 的 exact decimal
一致性和大小关系，然后直接转换为 integer nanos 并产出 frozen validated object。
已丢失原始 numeric token 的普通 dict/float projection、HTTP path 或 request body
都不能恢复为 trusted budget authority。

### 7.3 Account 创建冲突

account 以 tenant + job kind + job ID 唯一。重复初始化时：

- cap、scenario、source 和 policy identity 完全相同：返回已有 account；
- 任一 immutable field 不同：返回 store/authority conflict；
- 不允许通过“较大值覆盖”“最后写入优先”或客户端 retry 修改 cap。

## 8. Versioned price catalog

### 8.1 Catalog authority

价格 catalog 是仓库内、reviewed、versioned 的 server-owned 配置。每条规则必须
精确匹配：

- provider；
- canonical model；
- allowlisted provider billing region；
- finite `catalog_operation`；
- media type；
- billing fact kind。

`catalog_operation` 是 code-owned provider action vocabulary，与 attempt 用于
exactly-once identity 的实例级 `logical_operation` 不同。代码注册表把稳定的
workflow operation template 映射到有限 `catalog_operation`；server-derived
item/candidate slot 只参与 logical-operation instance 与 fingerprint，price lookup
不得解析、prefix-match 或 wildcard-match 实例字符串。

禁止：

- wildcard provider/model；
- 模糊 model alias；
- 未知模型套默认价；
- mutation 时在线 fetch 最新价格；
- 由 provider response 或 request body 选择 price rule；
- catalog 解析失败后继续调用 provider。

首版 catalog 的 `checked_at_utc` 在 Task 0 重新打开全部官方合同后记录，
`effective_from_utc` 必须等于该时间，`effective_to_utc=null`。本批不 backfill
该时间之前的 attempt；runtime 时间不在 declared window 内时 rule 不可用。若
Task 0 发现价格或合同漂移，停止实施并重新审批，不能移动时间窗掩盖 drift。

### 8.2 Rule 内容

每条 price rule 至少包含：

- stable `price_rule_id`；
- `catalog_version` 与 rule version；
- exact match key；
- billing fact schema version；
- 一个非空 immutable component bundle；
- 每个 component 的 stable name、exact quantity field、integer
  `unit_price_usd_nanos` 与 positive integer `unit_size`；
- reservation formula；
- settlement dimension；
- declared effective window；
- official evidence reference 与 checked date。

PoYo rule 还必须冻结 optional provider-charge cross-check：每个 component 的 exact
integer `provider_credit_micro_units_per_unit`，其中
`1 credit = 1_000_000 microcredits`。Expected credits 使用与 USD-nanos component
相同的 billable quantity/unit size 做 exact integer division；出现非整除或 overflow
即 rule 非法。该值只用于验证 terminal status 的 provider-reported
`credits_amount`，不得替换或改写 USD-nanos settlement。

金额计算只使用整数：

~~~text
component_cost =
  ceil(billable_units * unit_price_usd_nanos / unit_size)

attempt_cost =
  sum(component_cost for component in frozen_rule.components)
~~~

ceil 在每个独立计费 component 上执行，避免因截断低估。所有乘法先做 overflow
检查。component name 和 quantity field 不得重复，facts 中未被 rule 消费的字段也
不得静默影响金额。DeepSeek rule bundle 固定为 cache-hit input、cache-miss input
与 output 三个 component；单维 TTS/image/video rule 使用一个 component。

### 8.3 Reservation 与 settlement

- reservation adapter 根据 server-validated request upper bound 生成有限的
  maximum billing facts；
- 无法证明有限 upper bound 时，不得提交 provider；
- settlement adapter 只接受 provider usage、冻结的 provider billed-input fact、
  terminal task truth 或确定性媒体测量；
- actual cost 必须小于等于该 attempt 的 reservation；
- catalog 更新只影响新 reservation；
- attempt 冻结 rule ID/version、formula 和 reservation facts，历史金额不重算。

### 8.4 Local truth 与 invoice truth

`settled` 只表示：

> validated local billing facts × frozen catalog rule 已完成本地结算。

它不证明 provider invoice 相同。若 provider response 提供 bounded cost、credit
或 currency fact，可作为独立 provider-reported fact 保存，但不得覆盖本地
settlement，也不得改变 account cap。

W1-31 才负责用一次精确授权的真实 billing sample 对账。

PoYo 的 terminal status 提供 `credits_amount`（charged credits）但不提供最终视频
时长。本批把 JSON number 直接严格解析为 integer microcredits，禁止先经过 binary
float。只有 provider-reported credits 与冻结 rule 根据 request/task billing facts
计算的 expected microcredits 完全一致，才允许本地 USD-nanos settle；缺失、非法或
不一致进入 `accounting_error`。该 cross-check 仍不等于 invoice reconciliation。

## 9. 数据模型

### 9.1 job_budget_accounts

逻辑字段：

| 字段 | 规则 |
|---|---|
| `account_id` | server-owned UUID |
| `tenant_id` | 非空、不可变 |
| `job_kind` | bounded enum、不可变 |
| `job_id` | server-owned、bounded、不可变 |
| `scenario_or_resource_type` | bounded、不可变 |
| `cap_usd_nanos` | 正整数、不可变 |
| `reserved_usd_nanos` | 非负整数 |
| `settled_usd_nanos` | 非负整数 |
| `budget_source_kind` | server config 或 validated authorization |
| `budget_source_ref` | bounded internal reference，可空 |
| `budget_policy_version` | 非空、不可变 |
| `created_at` / `updated_at` | UTC、timezone-aware truth |

约束：

- unique `tenant_id + job_kind + job_id`；
- `cap_usd_nanos > 0`；
- `reserved_usd_nanos >= 0`；
- `settled_usd_nanos >= 0`；
- `reserved_usd_nanos + settled_usd_nanos <= cap_usd_nanos`；
- repository transition 后必须重新 normalize returned row，再 commit。

### 9.2 provider_cost_attempts

逻辑字段：

| 字段 | 规则 |
|---|---|
| `attempt_id` | server-owned UUID |
| `account_id` | FK to budget account |
| `tenant_id` / job identity | 与 account 一致、不可变 |
| `logical_operation` | bounded stable operation key |
| `catalog_operation` | code-owned finite provider action，与冻结 rule 一致 |
| `ordinal` | 非负 server-owned integer |
| `attempt_fingerprint` | canonical immutable fields 的 digest |
| `regeneration_epoch_ref` | 可空、server-owned 的 trusted epoch 消费标记 |
| `provider` / `canonical_model` | 精确、不可变 |
| `provider_billing_region` | allowlisted server-owned scope，不保存原始 URL |
| `media_type` / `billing_fact_kind` | 精确、不可变 |
| `price_rule_id` / version | reserve 时冻结 |
| `reservation_billing_facts` | strict versioned JSON |
| `settlement_billing_facts` | strict versioned JSON，可空 |
| `reserved_usd_nanos` | 正整数、不可变 |
| `settled_usd_nanos` | settled 前为零 |
| provider-reported cost facts | bounded、独立、可空 |
| `state` | 七态之一 |
| `external_task_id` / `provider_trace_id` | bounded、清洗、可空 |
| `safe_error_code` | allowlisted、可空 |
| `reservation_expires_at` | 仅 pre-submit reserved recovery 使用 |
| lifecycle timestamps | UTC、state-coherent |

约束：

- unique `account_id + logical_operation + ordinal`；
- attempt identity、fingerprint、provider/model/rule/reservation facts 不可变；
- `settled_usd_nanos <= reserved_usd_nanos`；
- state-specific field coherence 使用 repository validation 与数据库
  constraint 双重保证；
- external ID 只保存 bounded identifier，不保存 URL/body/message；
- malformed stored JSON、unknown state 或 account/attempt identity contradiction
  必须翻译为 typed store unavailable/accounting failure，不泄漏 parser exception。

### 9.3 Billing facts union

所有 quantities 都是 integer，禁止 float 和字符串数字：

- `llm_tokens.v1`：
  `input_tokens`、`input_cache_hit_tokens`、`input_cache_miss_tokens`、
  `output_tokens`、`total_tokens`；
- `tts_utf8_bytes.v1`：
  `input_utf8_bytes`；
- `image_count.v1`：
  `image_count`；
- `video_task.v1`：
  `task_count`，可携带不参与计价的 bounded `duration_ms`；
- `video_duration.v1`：
  `task_count` 与必填 `duration_ms`。

Catalog rule 决定 exact kind。一个 model 若按 task 计价，不能提交
`video_duration.v1` 来改变金额；反之亦然。LLM total 与 input/output 必须满足
provider contract 的内部一致性：
`input_cache_hit_tokens + input_cache_miss_tokens == input_tokens` 且
`input_tokens + output_tokens == total_tokens`。任何缺失、负数、bool-as-int、
overflow 或结构矛盾都进入 accounting failure；不得把缺失 cache split 的 input
全部猜成 cache miss 后冒充 actual settlement。

JSON 在入库前 canonicalize；PostgreSQL JSONB 和 SQLite text readback 必须得到
同一 normalized model。

## 10. Attempt 状态机

### 10.1 合法状态

~~~text
reserved
  |-- clearly no submit/no charge --> released
  |-- persist before mutation ----> submission_started

submission_started
  |-- synchronous known success --> settled
  |-- async task accepted --------> submitted
  |-- proven no submit/no charge -> released
  |-- acknowledgement uncertain -> ambiguous
  |-- success but facts invalid --> accounting_error

submitted
  |-- terminal paid success -----> settled
  |-- proven terminal no-charge -> released
  |-- provider outcome unknown --> ambiguous
  |-- success but facts invalid -> accounting_error
~~~

`settled`、`released`、`ambiguous` 和 `accounting_error` 是本批的 terminal
accounting states。`submission_started` 与 `submitted` 都是 durable nonterminal
state：前者在恢复时不得重放 mutation，后者只允许 poll/read/download，不允许
再次 submit。

### 10.2 Reserve

同一个 transaction：

1. lock/find account；
2. validate immutable account identity；
3. validate operation key、ordinal、fingerprint 和 price rule；
4. 计算 exact maximum reservation；
5. 检查 `reserved + settled + new_reservation <= cap`；
6. 增加 account reserved；
7. insert `reserved` attempt；
8. normalize account/attempt projection；
9. commit。

余额不足返回 stable budget-exhausted truth。不得创建零金额 attempt，不得发送
网络。

### 10.3 submission_started

所有确定性 input、credential/readiness、model、rule 和 local file precondition
应在 reserve 前完成。reserve 后、真正执行 mutation 前必须持久化
`submission_started`。

这个 write 是重启安全线：

- crash 时仍为 `reserved`：证明 mutation 尚未进入允许发送区，可在 expiry 后
  安全 release；
- crash 时为 `submission_started`：不能证明 mutation 未发出，必须 hold；
- provider client 不得先发请求再补写该状态。

### 10.4 Settle

同一个 transaction：

1. lock account 与 attempt；
2. validate state、identity、frozen rule 和 settlement facts；
3. 计算 actual nanos；
4. 若 actual 大于 reservation，进入 `accounting_error` 并保持完整
   reservation；
5. 否则 account reserved 减去完整 reservation；
6. account settled 增加 actual；
7. attempt 写入 settlement facts、actual 和 `settled`；
8. normalize 后 commit。

reservation 与 actual 的差额立即回到账户可用额度，但 attempt 仍保留原始
reservation amount 作为历史事实。

### 10.5 Release

release 只允许在 provider adapter 能证明以下任一事实时执行：

- mutation 没有离开本进程；
- transport 明确证明 request 未发送；
- provider 明确拒绝且合同证明该结果不计费；
- async terminal failure 有明确 no-charge contract。

release transaction 减少 account reserved 的完整 attempt reservation，并把
attempt 标为 `released`。通用 timeout、disconnect、ack loss、解析异常或
“大概率没收费”都不满足 release 条件。

### 10.6 Ambiguous 与 accounting_error

- `ambiguous`：无法确定 provider 是否接受、执行或收费；
- `accounting_error`：provider success/收费事实已知或高度确定，但缺少合法
  usage、UTF-8 byte count、duration、count、rule 或 cost 超过 reservation。

二者都保留完整 reservation，不自动 retry、不自动 release、不把业务结果包装为
stub。安全错误码和已有 bounded external ID 必须持久化，供人工或 W1-31
reconciliation 使用。

### 10.7 Expiry 与 restart

只有始终处于 `reserved`、没有 `submission_started_at` 且
`reservation_expires_at` 已过的 attempt 可以自动 release。

以下状态即使过期也不能自动释放：

- `submission_started`；
- `submitted`；
- `ambiguous`；
- `accounting_error`。

重启恢复只读取 durable state：

- `submitted` 可恢复同一个 task ID 的只读 poll；
- `submission_started` 保持 reservation，不能自动重提或释放；只有新的明确证据
  才能把它分类为 `released` 或 `ambiguous`；
- `settled` 只恢复 business projection/download，不重提；
- `ambiguous` 和 `accounting_error` 停止并要求人工处理；
- 同一 ordinal 永远不能因进程重启而 resubmit。

## 11. Repository transaction 语义

### 11.1 PostgreSQL

- 配置了 PostgreSQL 时必须使用经过现有 production readiness 验证的连接；
- reserve/settle/release 对 account row 使用 row lock；
- account 与 attempt 采用固定 lock order，避免 deadlock；
- unique/check/FK/state constraints 是 repository validation 的 defense in
  depth；
- acquire、transaction、driver 或 returned-row normalization 失败全部
  rollback；
- 不能在 store unavailable 时回退 SQLite 或进程内 tracker。

### 11.2 SQLite

- 使用项目级 async lock；
- mutation transaction 使用 `BEGIN IMMEDIATE`；
- 与 PostgreSQL 相同的 compare-and-set、identity、state 和 conservation
  validation；
- 先 normalize returned truth，再 commit；
- lock/commit/parse 失败不得留下半个 account transition。

SQLite 是 local/dev parity，不是配置了生产 PostgreSQL 后的 silent fallback。

### 11.3 Idempotent repository API

repository/service 操作必须满足：

- same reserve fingerprint：返回已有 attempt；
- same terminal transition payload：返回已有 terminal truth；
- conflicting transition、amount、facts 或 external ID：fail closed；
- stale state：不修改 row，不重新调用 provider；
- tenant mismatch：表现为 not found/authorization failure，不泄漏跨租户存在性。

## 12. 统一 provider 执行流

所有真实 paid mutation 使用以下顺序：

~~~text
validate execution context
-> validate credential/readiness/model/exact price rule
-> derive finite maximum reservation facts
-> atomic reserve
-> persist submission_started
-> invoke at most one provider mutation
-> classify acknowledgement
-> extract/measure strict billing facts
-> settle OR submitted OR release OR ambiguous OR accounting_error
-> project business result
~~~

规则：

1. `ProviderCostService` 自身不执行 mutation retry；
2. provider client 不能在 service 外自行 `track()`；
3. 只有 durable accounting transition 成功后才能返回 paid business success；
4. accounting store failure不能被吞掉，也不能返回成功；
5. paid success 后的 artifact failure 不回滚 settled cost；
6. stub/no-provider path 在进入上述流之前被严格、显式分类。

## 13. Provider-specific billing truth

### 13.1 LLM

- reviewed model-contract metadata freezes `context_window_tokens=1_000_000` and
  `provider_max_output_tokens=384_000` for both allowed V4 models；当前 application
  request policy freezes `application_max_output_tokens=4_096`，且 caller 不能覆盖；
- mutation 前按 server-approved maximum request envelope reserve：maximum input
  `1_000_000 - 4_096` 全部使用 cache-miss component，再加 `4_096` output
  component；任一 envelope drift、非法 override 或 app cap 超 provider max 都在网络前
  阻断；
- catalog 只匹配 exact `deepseek-v4-flash` 或 `deepseek-v4-pro`；active
  low-latency `deepseek-chat` call site 迁移到 `deepseek-v4-flash`，旧 alias、未知
  model 和不匹配 provider endpoint 全部在网络前阻断；
- 保留完整 provider response，不能先只返回 `response.content`；
- 从官方 response usage 提取 input、cache-hit input、cache-miss input、output 和
  total token，并执行 §9.3 的两条 conservation checks；
- usage 合法且 cost 不超 reservation 后 settle，再返回 content；
- success response 缺 usage/cache split、usage 类型错误或内部矛盾：
  `accounting_error`；
- timeout、disconnect 或 response acknowledgement 不明：
  `ambiguous`；
- 明确 pre-submit/local rejection 或合同证明 no-charge 的 provider rejection：
  `released`；
- generic LLM retry wrapper 不再包住 mutation。

### 13.2 TTS

- provider adapter 在任何 mutation 前冻结最终 `text` 字段；禁止 reservation 后
  再做 trim、normalize、translate、template expansion 或 voice-dependent rewrite；
- 用严格 UTF-8 编码计算 exact `input_utf8_bytes`；bool-as-int、空输入、编码失败、
  unpaired surrogate、超 provider 上限或 catalog rule 不匹配全部在网络前阻断；
- 按 exact provider/model/region 的 `tts_utf8_bytes.v1` rule 和该 byte count
  reserve；attempt fingerprint 绑定输入 digest，但账本和日志不保存原始文本；
- 执行一次 speech mutation；
- provider 成功返回 audio bytes/trace 后，使用 reservation 时冻结的同一
  `input_utf8_bytes` 结算；response 不得用输出 duration 改写 billing fact；
- 结算成功后，音频 bytes 才进入受控 staging artifact 和确定性 duration/format
  probe；这些 probe 只属于 artifact QA；
- provider success 后 audio bytes 写入、duration/format probe、artifact move 或
  verification 失败只影响业务 artifact，不撤销 settled cost；
- provider acknowledgement 不明进入 `ambiguous`；成功 response 到达但冻结的
  input fact/rule 已损坏则进入 `accounting_error` 并保持 reservation；
- silent/stub audio 只有在明确 no-submit 的 local policy 下为零成本。

### 13.3 PoYo/Seedance async image/video

- submit 前按 exact model/operation/billing kind reserve；
- 一次 submit 返回合法 task ID 后进入 `submitted`；
- status GET 可对同一 task 做有界重试；
- poll exhaustion 保持 `submitted`，供后续只读恢复，不新建 mutation；
- terminal success 必须先把 status `credits_amount` 无 float 地解析为 strict
  microcredits，并与冻结 rule 的 expected microcredits 完全一致；匹配后才按
  task/count/duration truth settle，再下载 artifact；
- terminal success 后 download 失败只影响业务 artifact，不改变 settled cost；
- submit 2xx 但 task ID 缺失/矛盾，或 ack 丢失：
  `ambiguous`；
- terminal failed 只有在 exact adapter 能证明 no-charge 时 release；无法证明
  billing outcome 时进入 `ambiguous` 并保留 reservation；PoYo terminal `failed` +
  strict zero charged microcredits 是可接受的 no-charge proof，nonzero charged credits
  进入 `accounting_error`，missing/invalid credits 进入 `ambiguous`；
- PoYo image 与 video 必须使用不同 exact operation/media kind，不能再用
  `poyo_video` 统一计价；
- 所有 reachable Seedance modes 都进入 paid-path inventory。当前 PoYo catalog 只覆盖
  text-to-video 与 reference-image-to-video 的 no-video-input rules；
  `reference_video_urls`、`reference_audio_urls`、4K 和 direct/native Seedance 本批在
  网络前阻断，不能套用相近价格。

### 13.4 图片

- 按 exact rule 的 billable image count 结算；
- provider response 返回多个结果时，adapter 只接受合同规定的 billable count；
- terminal `credits_amount` 必须与 quality/effective-resolution/count rule 的 expected
  microcredits 完全一致；provider credits 只作 cross-check，不改写 local cost；
- success count 缺失、非整数、与 request/response 矛盾时进入
  `accounting_error`；
- local placeholder、fixture image 和 no-key stub 不创建 paid attempt。

### 13.5 Legacy DALL-E、ElevenLabs 与 admin connectivity

- 若继续可达，必须在调用前建立 compatibility job context 和 account；
- 必须走同一 reserve/transition/settle 服务；
- 无法提供可靠 billing facts 或 finite reservation upper bound 时，必须在网络前
  阻断；
- admin connectivity 不得因为“只做测试”而绕过 tenant、budget 或 ledger；
- 不允许 legacy path 双写新 ledger 与旧 `_records`。

## 14. Stub、no-media 与 degraded 行为

### 14.1 合法零成本

以下条件同时成立时可以不创建 attempt：

- generation policy 明确选择 no-media 或 local fixture；
- provider mutation function 未被调用；
- network construction guard 证明零 outbound mutation；
- business result 明确标注 simulated/stub/degraded truth；
- `provider_attempt_made=false`。

### 14.2 禁止伪装

以下情况不能降级为零成本 stub：

- 已写 `submission_started` 后发生 timeout/disconnect；
- 已取得 external task ID；
- provider 已返回 paid success；
- settlement facts 缺失；
- download/verification 失败；
- store transition 失败；
- provider outcome ambiguous。

这些路径必须保留 reservation，并返回稳定的 degraded/failed accounting truth。

## 15. Retry、恢复与重新生成

### 15.1 Mutation

- mutation retry cap 固定为零；
- generic `retry_with_backoff` 不得包裹 provider mutation；
- service 不能因 database retry、HTTP retry、background task restart 或用户刷新
  再发 mutation；
- provider 支持 idempotency key 时可使用 attempt ID，但不能依赖它替代本地
  ledger。

### 15.2 Read-only operations

以下操作可以有界重试：

- async status poll；
- 已知 artifact URL 的 download；
- 不产生新 provider work 的 receipt/readback；
- database transaction 在确认 mutation 尚未执行前的 safe retry。

read retry 不创建新 ordinal，不增加 reservation。

### 15.3 Regeneration

任何未来明确授权的 regeneration 都是新的 logical ordinal：

- 新 attempt UUID；
- 新 reservation；
- 独立 external task ID；
- 旧 attempt 保持原始 terminal truth；
- 不能覆盖、复用或删除旧 settled/ambiguous accounting evidence。
- `regeneration_epoch_ref` 随新 attempt 持久化；同一 account + logical operation
  再次提交同一 epoch 且 fingerprint 不同必须在锁内冲突；同一 epoch 与相同
  fingerprint 只读 replay；不同 server-owned slot 可以在同一 regeneration
  execution 中各自消费该 epoch 一次。

## 16. 错误分类与安全投影

内部至少区分以下稳定类别：

| 类别 | Network | Attempt/account 结果 |
|---|---:|---|
| context/authority 缺失 | 0 | 无 attempt |
| budget config 非法 | 0 | 无 attempt |
| price rule 缺失/非法 | 0 | 无 attempt |
| account/store 初始化失败 | 0 | rollback，无 mutation |
| budget exhausted | 0 | 无新 attempt 或 reserve rollback |
| attempt fingerprint conflict | 0 | existing truth 不变 |
| deterministic pre-submit failure | 0 | reserved 可 release |
| explicit no-submit/no-charge rejection | 至多 1 次尝试 | released |
| async accepted | 1 | submitted，reservation held |
| sync/async paid success | 1 | settled |
| ack/outcome 不确定 | 1 | ambiguous，reservation held |
| usage/UTF-8 bytes/duration/count 缺失 | 1 | accounting_error，reservation held |
| actual cost 超 reservation | 1 | accounting_error，reservation held |
| paid success 后 artifact failure | 1 | cost 保持 settled |

外部错误只暴露 allowlisted code、attempt ID（仅在 tenant-bound/authorized
projection 中）和安全 retry truth。不得暴露 raw provider body、prompt、token、
absolute path、host、credential 或原始 exception text。

本批不新增 public error schema；具体 HTTP status 继续复用现有 route 的安全错误
投影，并在 implementation plan 中按当前 route contract 锁定。

## 17. 旧 tracker 迁移

### 17.1 Authority 移除

完成实现后：

- provider clients 不再调用旧 `track()`；
- StepRunner 不再以旧 `check_budget()` 作为 hard-cap authority；
- module-level `_records` 不再决定运行时行为；
- 不允许新旧 dual-write；
- 若旧模块仍因兼容测试暂存，必须没有 reachable paid authority，并在无调用后
  删除。

### 17.2 不做 backfill

旧记录：

- 有界且会截断；
- 不含 tenant/canonical job/attempt/model/task ID；
- 单位不可靠；
- 重启后不完整。

因此不能被伪造成 durable accounting history。Migration 只从新 account/attempt
开始记账。

## 18. Migration 与 schema parity

### 18.1 Additive migration

实现阶段新增一条 Alembic revision：

- 创建 `job_budget_accounts`；
- 创建 `provider_cost_attempts`；
- 添加 FK、unique、check 和查询 indexes；
- 不修改或回填既有业务表；
- PostgreSQL timestamp 使用 timezone-aware UTC；
- downgrade 只删除本 revision 所有对象。

同时更新 fresh-init schema 与 SQLite initialization，使新数据库和现有数据库
升级后结构一致。

### 18.2 必测生命周期

disposable PostgreSQL 18 必须验证：

1. 前一 revision -> 新 revision upgrade；
2. 创建 account/attempt 并验证 concurrency/conservation；
3. downgrade 回前一 revision；
4. 证明新表/index/constraint 已删除，旧表数据仍在；
5. re-upgrade；
6. fresh-init 与 Alembic head parity。

SQLite 必须验证：

- 新库 fresh init；
- 现有库兼容初始化；
- account/attempt transition parity；
- restart 后 reservation/settlement truth 不丢失。

### 18.3 Production rollout 与 rollback

本规格不授权 production rollout。未来 rollout 必须：

1. 先禁用所有 provider mutation；
2. 备份并执行 schema-first migration；
3. 验证表、constraint、readiness 和 server budget/catalog config；
4. 部署新 binary；
5. 只在单独授权后启用 provider submit。

应用 rollback 到旧 binary 前必须先禁用 provider submit。旧 binary 不理解新
ledger，绝不能在 provider enabled 状态运行，否则会绕过 hard cap。

生产 schema downgrade 不能作为自动 rollback：必须先停止 mutation、保留 ledger
备份并人工处理所有 `submitted`、`ambiguous` 和 `accounting_error`
reservation。当前批次只在 disposable database 执行 downgrade。

## 19. 可观测性与内部 readback

内部 readback 至少支持：

- tenant + job 查询 account cap/reserved/settled；
- tenant + attempt 查询 lifecycle、rule identity、safe facts 和 safe error；
- logical operation + ordinal 查重；
- 查找 `submitted`、`ambiguous`、`accounting_error` 供运维处理；
- 只释放满足严格 pre-submit expiry 条件的 `reserved`。

日志只记录 bounded internal IDs、state transition、safe code、integer nanos 和
catalog version。日志不得记录 prompt、provider body、secret、artifact path 或
原始 exception message。

本批不建立 invoice dashboard；数据库 readback 也不宣称 billing reconciliation。

## 20. 测试设计

### 20.1 Config、catalog 与 arithmetic

- `PROVIDER_JOB_BUDGET_USD` 缺失、空白、零、负数、指数、NaN、Infinity、
  超过 9 位小数和 overflow 全部 pre-network fail；
- exact decimal -> nanos；
- exact rule match，拒绝 wildcard/alias/unknown/stale/malformed rule；
- code-owned operation registry 把 dynamic logical-operation instance 映射到有限 exact
  `catalog_operation`，拒绝字符串解析、prefix 或 wildcard lookup；
- component name/quantity uniqueness、integer ceil、三组件 DeepSeek sum、overflow
  和 no-float guard；
- PoYo expected-credit micro-units 与 terminal `credits_amount` exact equality；JSON
  number 不得经过 float，缺失/非法/mismatch 全部 hold；
- catalog update 不重算已有 attempt。

### 20.2 Repository 与 state machine

- account 初始化 idempotency 与 immutable conflict；
- 20-way concurrent reserve 不 overspend；
- reserve/settle/release/hold conservation；
- actual 等于/小于 reservation；
- actual 大于 reservation -> accounting_error 且 hold；
- duplicate transition idempotency；
- conflicting transition zero mutation；
- only-expired-reserved 自动 release；
- submitted/ambiguous/accounting_error restart 后继续 hold；
- 同一 regeneration epoch 的重复使用在 restart/concurrency 下仍只能得到
  `provider_cost_attempt_conflict`，不得增加 attempt 或 reservation；
- tenant isolation；
- malformed JSON/state/account identity fail closed；
- PostgreSQL/SQLite parity。

### 20.3 Provider fake transports

- DeepSeek-like response 的 input/cache-hit/cache-miss/output/total token；
- LLM reservation 把 maximum input 全部按 cache miss 计价，settlement 使用 exact
  split，且两个 conservation equations 必须成立；
- LLM model envelope 锁定 1,000,000 context、384,000 provider maximum output 与
  4,096 application output cap；caller override 或 metadata drift zero-network；
- LLM success 缺 usage/cache split、usage contradiction、ack loss；
- `deepseek-chat`/`deepseek-reasoner`/unknown model zero-network，active low-latency
  path 只使用 exact `deepseek-v4-flash`；
- TTS exact input UTF-8 byte count，覆盖 ASCII、CJK、emoji 与组合字符；
- TTS reservation 后输入不可变、原文不落账本/日志；
- TTS provider success 后先 settle，同一 input byte fact 不受输出 duration 影响；
- TTS duration/format probe failure 只失败 artifact，cost 仍 settled；
- TTS invalid Unicode、空输入、byte overflow、unknown region/rule 均 zero-network；
- PoYo image exact count；
- Seedance task-based 与 seconds-based rule；
- PoYo terminal charged credits 的 strict microcredit parse/equality，且不能覆盖
  USD-nanos settlement；
- async accepted -> submitted -> terminal settle；
- terminal success 后 download failure，cost 仍 settled；
- terminal explicit no-charge failure release；
- timeout/disconnect ambiguous；
- actual 超 reservation；
- store failure zero network 或 durable held state；
- stub/no-media/no-key local policy 零 attempt、零 cost；
- provider submitted 后禁止 stub fallback。

### 20.4 Paid-path completeness

测试或静态 contract 必须覆盖每个可达 paid mutation：

- LLM client；
- PoYo image/video；
- Seedance native 与 PoYo-backed；
- GPT Image；
- CosyVoice；
- DALL-E；
- ElevenLabs；
- admin provider connectivity；
- Fast、S1–S5、pipeline/step/legacy compatibility callers。

每个路径只能出现两种结果：

1. 完整 execution context + cost service；
2. provider mutation 构造前 zero-network block。

禁止第三种 untracked fallback。

### 20.5 Full gates

实现完成前至少执行：

- focused cost/service/repository/provider tests；
- disposable PostgreSQL 18 upgrade/downgrade/re-upgrade/fresh-init；
- SQLite existing/new/restart tests；
- full backend pytest；
- Ruff；
- docs/security/log-safety checks；
- OpenAPI drift，证明没有新增 cost HTTP surface；
- frontend regression/build 仅用于证明 public behavior 未被意外改变；
- `git diff --check`；
- independent review。

所有 fake provider tests 必须有 network-construction guard，不能把偶发外网失败
当作 accepted RED/GREEN 证据。

## 21. 验收矩阵

| Roadmap item | 本地完成证据 |
|---|---|
| W1-27 | PostgreSQL/SQLite 两表、tenant/job/attempt/provider/model identity、restart readback |
| W1-28 | DeepSeek cache-hit/cache-miss/output token、TTS input UTF-8 bytes、image count、video task/seconds 的 strict facts 与 exact rule settlement |
| W1-29 | canonical + reachable legacy paid path 全覆盖；每次 paid success 一条 attempt；stub/no-submit 零 attempt |
| W1-30 | submit 前 atomic reserve、并发无 overspend、release/hold truth、restart hard cap |

W1-31 不在矩阵内；本地 catalog 计算与真实 provider invoice 一致性仍为
`billing_reconciliation=false`。

## 22. Definition of Done

只有同时满足以下条件，W1-27–W1-30 才能标为 `completed_local`：

1. 正式规格与 executable implementation plan 都获得明确批准；
2. 两表 schema、repository、service、context、catalog 和 adapters 完成；
3. 所有 reachable paid mutation 已集成或 pre-network blocked；
4. 旧 tracker 不再拥有 runtime authority；
5. 20-way concurrency、restart、state machine 和 provider fake matrix 通过；
6. disposable PostgreSQL 18 与 SQLite parity 通过；
7. full backend、Ruff、docs/security、OpenAPI/frontend regression 通过；
8. independent review 完成且 accepted actionable findings 为零；
9. roadmap、runbook、project guide、计划与 evidence report 同步；
10. 最终报告逐字保留本规格的证据边界。

任一 independent review、migration lifecycle、paid-path inventory 或 full gate 未完成，
不得使用 `completed_local`。

## 23. 后续工作

- W1-31：一次精确授权的 provider billing reconciliation；
- W5：逐场景 authorized-live sample 与人工 acceptance；
- W6：跨租户/多场景并发、worker/process restart 与生产容量 smoke；
- tenant monthly/org budget、multi-currency、invoice/credit reconciliation；
- 如确有规模需求，再单独设计 outbox/worker。

这些后续项不能反向放宽当前 hard-cap、no-retry、hold-on-ambiguity 或
server-owned authority。

## 24. 官方合同参考

本规格用官方一手资料约束 billing facts 与异步 task truth：

- DeepSeek cache-hit/cache-miss/output price components 与 exact model IDs：
  [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)；
- DeepSeek chat completion response 的完整 `usage`：
  [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)；
- PoYo submit/status 异步 task 合同：
  [API Overview](https://docs.poyo.ai/api-manual/overview)、
  [Task Status](https://docs.poyo.ai/api-manual/task-management/status)；
- PoYo model pricing 入口：
  [PoYo Pricing](https://poyo.ai/pricing)；
- SiliconFlow TTS 按输入文本 UTF-8 byte count 计费：
  [Text to Speech](https://docs.siliconflow.com/en/userguide/capabilities/text-to-speech)；
- SiliconFlow speech 返回 audio bytes/trace、未提供 duration billing fact：
  [Create Speech](https://docs.siliconflow.com/cn/api-reference/audio/create-speech)；
- SiliconFlow 官方价格页的 speech unit：
  [中国价格](https://siliconflow.cn/pricing)、
  [国际价格](https://www.siliconflow.com/pricing)。

这些链接只证明 response/task/billing dimension 的设计依据。实现时仍需把 exact
model price 以 reviewed catalog rule 冻结；本地测试不证明当前真实账单价格。

## 25. 当前审批边界

截至 2026-07-15：

- conversational design：已批准；
- 本 written specification：TTS、DeepSeek 与 PoYo GPT Image 2 exact USD-nanos 三项
  证据修正均已批准；
- executable implementation plan：已批准实施，§28 后的 Task 0 复核进行中；
- business code/migration：尚未开始；Task 1 strict RED tests 已创建，但其中旧
  medium/high price expectations 不是可接受证据；
- production/provider/live action：未授权。

下一步重新打开官方价格页、记录新的 exact `checked_at_utc`、修正 executable plan
与 RED matrix，再重新通过 Task 0；Task 0 未通过前不继续 GREEN。

## 26. 2026-07-15 TTS billing dimension 证据修正（已批准并合入）

实施计划的官方合同复核发现：

- SiliconFlow TTS 指南明确写明按输入文本的 UTF-8 byte count 计费；
- 中国价格页将 CosyVoice2-0.5B 列在“每千 UTF-8”语音价格下；
- 国际价格页将同一模型列为 `$7.15 / M UTF-8 bytes`；
- speech response 仍只返回 audio bytes 和 trace ID，不返回输出 duration billing
  fact。

因此，原 `tts_duration.v1`、按最大输出时长 reserve、成功后 probe duration 再
settle 的设计不能作为 billing truth。已批准 amendment 是：

1. 用 `tts_utf8_bytes.v1` 替换 `tts_duration.v1`；唯一计费 quantity 为严格整数
   `input_utf8_bytes`；
2. reservation 在 submit 前对 exact provider input UTF-8 bytes 计算，因而不需要
   猜测输出时长；
3. provider 返回成功 audio bytes/trace 后，用同一 immutable input byte fact
   settle；duration probe 只保留为 artifact QA，不再决定成本；
4. catalog 采用 exact provider/model/region rule；若缺少匹配的 reviewed USD
   rule，则网络前阻断；
5. W1-31 继续负责与真实 provider billing 对账，本地 settled 不冒充 invoice
   truth。

用户已于 2026-07-15 明确确认本 amendment。前述设计正文、测试矩阵、验收矩阵、
官方合同参考与 billing-region identity 已经同步。随后发现的 DeepSeek cache-token
问题由 §27 单独记录，不反向撤销本 TTS 决策。

## 27. 2026-07-15 DeepSeek cache-token billing dimension 修正（已批准并合入）

实施计划的官方价格与 response schema 交叉复核发现：

- `deepseek-v4-flash` 和 `deepseek-v4-pro` 分别对 cache-hit input、cache-miss
  input 和 output 使用三个不同价格；
- 官方 response `usage` 提供 `prompt_tokens`、`prompt_cache_hit_tokens`、
  `prompt_cache_miss_tokens`、`completion_tokens` 和 `total_tokens`；
- 原 `llm_tokens.v1` 只有 aggregate input/output/total，无法把一次成功响应按三个
  component 精确结算；把全部 input 按 cache-miss 价格只是一种保守估算，不能冒充
  W1-28 的 actual billing truth；
- `deepseek-chat` 与 `deepseek-reasoner` 官方将在 2026-07-24 15:59 UTC 弃用，当前
  Fast Mode、agent 和 skill 中仍有 active `deepseek-chat` call site。

已批准 amendment 是：

1. 保留 schema version 名 `llm_tokens.v1`，但在首次实现前把其必填字段冻结为
   `input_tokens`、`input_cache_hit_tokens`、`input_cache_miss_tokens`、
   `output_tokens`、`total_tokens`；
2. 强制 `input_cache_hit_tokens + input_cache_miss_tokens == input_tokens` 且
   `input_tokens + output_tokens == total_tokens`；缺失、负数、bool-as-int、overflow
   或矛盾全部进入 `accounting_error`，不得猜测或回退 aggregate price；
3. price catalog 的 exact rule 改为一个 immutable component bundle，分别冻结
   cache-hit input、cache-miss input 和 output 的 integer USD-nanos/unit-size；每个
   component 独立 ceil 后求和；
4. reservation 把 server-validated maximum input 全部按 cache-miss 价格计算，并
   加上 configured maximum output；settlement 使用 response 的 exact 三分量；
5. catalog 只接受 `deepseek-v4-flash` 与 `deepseek-v4-pro` exact model ID。实施计划
   把 active low-latency `deepseek-chat` call sites 迁移到
   `deepseek-v4-flash`，默认 reasoning path 继续使用 `deepseek-v4-pro`；任何未知或
   旧 alias 在网络前阻断；
6. W1-31 继续负责真实账单对账；本地 exact response settlement 仍保持
   `billing_reconciliation=false`。

用户已于 2026-07-15 明确确认本 amendment。§8.2、§9.3、§13.1、LLM 测试矩阵、
验收矩阵、官方合同参考与审批边界已经同步；implementation plan 可继续编制，但
仍需单独获得明确批准后才能修改业务代码或 migration。

## 28. 2026-07-15 PoYo GPT Image 2 exact USD-nanos 修正（已批准并合入）

Task 0 官方价格复核显示，PoYo GPT Image 2 官方模型页同时列出 credits 与美元金额：

- low 1K/2K/4K：`2/4/8 credits`，`$0.010/$0.020/$0.040`；
- medium 1K/2K/4K：`8.48/8.96/16.16 credits`，
  `$0.0424/$0.0448/$0.0808`；
- high 1K/2K/4K：`33.76/35.52/64.16 credits`，
  `$0.1688/$0.1776/$0.3208`。

已批准 executable plan 错把 medium/high 美元金额近似成三位小数：
`$0.042/$0.045/$0.081` 与 `$0.169/$0.178/$0.321`。这些近似值既不等于官方
美元列，也不能与已冻结 microcredits 形成 exact cross-check，不能进入本地账本。

已批准 amendment：

1. low USD nanos 保持 `10_000_000/20_000_000/40_000_000`；
2. medium USD nanos 修正为
   `42_400_000/44_800_000/80_800_000`；
3. high USD nanos 修正为
   `168_800_000/177_600_000/320_800_000`；
4. expected microcredits 保持
   `8_480_000/8_960_000/16_160_000` 与
   `33_760_000/35_520_000/64_160_000`；
5. 不扩大 provider、model、quality、resolution、operation 或 endpoint allowlist；
6. 批准后重新执行官方页面核验并用新的 exact `checked_at_utc` 作为首版所有 rule
   的 `effective_from_utc`，不沿用已失效的 Task 0 PASS 声明。

该修正只恢复已批准的 exact billing truth，不授权 provider call、生产动作或
W1-31 invoice reconciliation。

用户已于 2026-07-16 明确确认本 amendment。首版 catalog 仍须先通过批准后的新鲜
官方核价，并使用该次核验的 exact `checked_at_utc`。
