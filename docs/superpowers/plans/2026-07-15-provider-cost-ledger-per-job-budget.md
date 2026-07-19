---
title: W1-27-W1-30 Provider Cost Ledger and Per-Job Budget Implementation Plan
doc_type: workflow
module: provider-cost
topic: provider-cost-ledger-per-job-budget
status: stable
created: 2026-07-15
updated: 2026-07-20
owner: self
source: human+ai
---

# W1-27–W1-30 Provider 成本账本与单任务硬预算实施计划

> **执行规则：** 仅在本计划再次获得用户明确批准后，按 Task 0 → Task 10 顺序在
> 主线程逐项实施。用户禁止 subagent；所有 checkbox 只能在新鲜证据通过后勾选。

> **RESUMED — 2026-07-16:** 用户已批准规格 §28 的 GPT Image 2 exact USD-nanos
> 修正。批准后的 Task 0 官方核价与 RED matrix 修正进行中；通过前不得进入 GREEN。

**目标：** 用 PostgreSQL/SQLite 持久化账本替代进程内 `cost_tracker`，按 provider
真实计费事实记录每个 paid mutation attempt，并在网络前原子预留 tenant-bound、
job-bound hard cap；本批不执行任何真实 provider 或生产动作。

**已批准规格：**
`docs/superpowers/specs/2026-07-15-provider-cost-ledger-per-job-budget-design.md`
（`status: approved`，包含已批准的 §26 TTS UTF-8 bytes 与 §27 DeepSeek cache-token
修正）。

**架构：** 新增 immutable `ProviderExecutionContext`、strict billing-fact models、
versioned price catalog、specialized `ProviderCostRepository` 和
`ProviderCostService`。入口先建立 server-owned job/account；provider client 只在
durable reserve 与 `submission_started` 后执行一次 mutation。同步成功先 settle，
异步 submit 先保存 task ID，再只读 poll；任何不确定结果保留 reservation。未覆盖的
paid provider/model/region 在 client 构造或网络前 fail closed。

**技术栈：** Python 3.11+、Pydantic v2、FastAPI、asyncpg、SQLite、Alembic、httpx、
LangChain、pytest/pytest-asyncio、Ruff、disposable PostgreSQL 18、Next.js 16、
React 19、TypeScript、Vitest、ESLint。

## 全局约束

- 保留当前 Wave 1A/W1-22–W1-25 大型 dirty worktree；不得 reset、restore、覆盖、
  删除、批量格式化或顺手修改无关文件。
- 不使用 subagent。主线程 self-review 不等于 independent review；若独立 Codex review
  未实际完成，最终状态只能是
  `implementation_complete_local / independent_review_pending`、
  `independent_review=false`。
- 不读取 `.env`、`.env.prod`、私钥或 credential 文件内容。测试只通过 dependency
  injection/`monkeypatch` 使用显式 fixture 字符串。
- 不执行真实 HTTP/provider call、token smoke、SSH、production migration/write、
  deploy、publish、delivery、metrics live pull、stage、commit、push、PR 或 merge。
- 不新增 public cost/budget HTTP route、request field、OpenAPI schema、前端预算 UI、
  invoice dashboard 或 dependency。
- `PROVIDER_JOB_BUDGET_USD` 与 catalog 都是 server-owned；普通请求不能提交 cap、
  spend、account ID、price rule、authorization path 或 attempt ordinal。
- Catalog 运行时不联网、不使用 wildcard/alias/default-price fallback。官方价格发生
  变化时停止实施、重新打开规格，不在 GREEN 中静默改价。
- Provider mutation retry 固定为零。只有同一已知 task/resource 的 status、receipt
  或 artifact download 可以有界重试。
- 同一 logical operation 的 ordinal 由 repository 在 account lock 内分配；客户端和
  provider client 都不能传数字 ordinal。相同 fingerprint 只读重放；新 ordinal 只由
  persisted server regeneration epoch 授权。
- Code-owned operation registry entry 同时冻结 bounded logical-operation template 与
  finite `catalog_operation`。Server-derived item/candidate slot 只形成实例身份与
  fingerprint；catalog lookup 只能使用 registry 的 exact `catalog_operation`，不得
  解析、prefix-match 或 wildcard-match 实例字符串。
- No-key/no-media/local-fixture 分支可以零 attempt；一旦进入 `submission_started`、取得
  task ID 或收到 paid success，禁止回退 silent/stub success。
- 稳定错误码固定为：
  `provider_execution_context_missing`、`provider_budget_configuration_invalid`、
  `provider_cost_rule_unavailable`、`provider_budget_exhausted`、
  `provider_cost_store_unavailable`、`provider_cost_attempt_conflict`、
  `provider_cost_usage_invalid`、`provider_cost_outcome_ambiguous`、
  `provider_cost_accounting_error`、`provider_cost_artifact_failed`、
  `provider_cost_legacy_path_blocked`。
- 日志与账本不得保存 prompt、script、原始 text、request/response body、secret、
  provider URL、artifact bytes/绝对路径、原始异常消息或 PII。
- 每个行为改动遵循 RED → 确认预期失败 → 最小 GREEN → focused regression →
  Ruff/scoped diff checkpoint。同一路径第三次验证仍失败时停止 patch 并重审边界。
- 固定证据上限：`production unchanged`、`provider_call=false`、
  `provider_attempt_made=false`、`real_connector_call=false`、
  `database_write=local-test-only`、`live_publish=false`、`live_send=false`、
  `billing_reconciliation=false`。

## 冻结 catalog（实现时必须逐项复核，禁止自行推断）

Catalog ID 固定为 `provider-cost-catalog.2026-07-15.v1`，所有金额使用 integer USD
nanos，所有规则精确匹配 provider、model、billing region、operation、media type 与
billing fact kind。

Task 0 重新核价时记录 exact `checked_at_utc`；首版每条 rule 的
`effective_from_utc` 必须等于该值，`effective_to_utc=null`。不 backfill 更早 attempt，
不允许通过移动时间窗绕过 price/contract drift。

§28 获批后的新鲜核价时间固定为 `checked_at_utc=2026-07-15T17:01:24Z`；首版
catalog 所有 rule 的 `effective_from_utc` 使用该值。

本批 finite `catalog_operation` vocabulary 固定为 `chat_completion`、
`speech_synthesis`、`image_generation`、`text_to_video`、`image_to_video`。同一
provider/model 在多个允许 operation 价格相同时也必须有各自 exact rule，不能用
workflow logical-operation instance、prefix 或 wildcard 代替。

DeepSeek model-contract metadata 同时冻结：两个 allowed V4 model 的
`context_window_tokens=1_000_000`、`provider_max_output_tokens=384_000`，以及本应用
`application_max_output_tokens=4_096`。LLM reservation input ceiling 固定为
`995_904`；caller 不得覆盖这些值，Task 0 若发现官方 drift 必须停止实施。

| Provider/model/region | Component | Unit price | Unit size |
|---|---|---:|---:|
| DeepSeek `deepseek-v4-flash` / `deepseek_global_usd` | cache-hit input | `2_800_000` nanos | `1_000_000` tokens |
| DeepSeek `deepseek-v4-flash` / `deepseek_global_usd` | cache-miss input | `140_000_000` nanos | `1_000_000` tokens |
| DeepSeek `deepseek-v4-flash` / `deepseek_global_usd` | output | `280_000_000` nanos | `1_000_000` tokens |
| DeepSeek `deepseek-v4-pro` / `deepseek_global_usd` | cache-hit input | `3_625_000` nanos | `1_000_000` tokens |
| DeepSeek `deepseek-v4-pro` / `deepseek_global_usd` | cache-miss input | `435_000_000` nanos | `1_000_000` tokens |
| DeepSeek `deepseek-v4-pro` / `deepseek_global_usd` | output | `870_000_000` nanos | `1_000_000` tokens |
| SiliconFlow `FunAudioLLM/CosyVoice2-0.5B` / `siliconflow_global_usd` | input UTF-8 bytes | `7_150_000_000` nanos | `1_000_000` bytes |

PoYo `seedance-2` no-video-input per-second rules：480p `100_000_000`、720p
`200_000_000`、1080p `450_000_000` nanos；`seedance-2-fast`：480p
`70_000_000`、720p `140_000_000` nanos。JSON rule 使用 `duration_ms`，对应
`unit_size=1000`。`reference_video_urls` 当前必须 zero-network blocked；不得套用
no-video-input rule。`reference_audio_urls` 也没有本批 exact operation/rule，必须
zero-network blocked；仅 reference-image input 可使用冻结的 image-to-video rule。

对应 expected charged credits/second 使用 integer microcredits：standard
480/720/1080 = `20_000_000/40_000_000/90_000_000`，fast 480/720 =
`14_000_000/28_000_000`。`seedance-2` 4K、所有 video-reference input 和其他未列
resolution 本批都必须 zero-network blocked，即使官方存在其他价位也不静默扩表。

PoYo `gpt-image-2` 每 generation rules：low 1K/2K/4K =
`10_000_000/20_000_000/40_000_000` nanos；medium 的待批准 exact 修正 =
`42_400_000/44_800_000/80_800_000`；high 的待批准 exact 修正 =
`168_800_000/177_600_000/320_800_000`。Adapter 必须按官方 auto/custom/4K
downgrade 规则冻结 effective billed resolution；无法确定时网络前阻断。

对应 expected credits/generation 使用 integer microcredits：low =
`2_000_000/4_000_000/8_000_000`，medium =
`8_480_000/8_960_000/16_160_000`，high =
`33_760_000/35_520_000/64_160_000`。`size=auto` 或省略 size 强制 effective 1K；
custom size 只允许 requested 2K/4K；requested 4K 只有 16:9、9:16、21:9 或一边
exact 3840px 的合法 custom size 保持 4K，其余合法 4K request 按 effective 2K
结算。

只允许 `https://api.deepseek.com`、`https://api.poyo.ai` 和
`https://api.siliconflow.com/v1` 映射到上述 USD region。China SiliconFlow endpoint、
custom endpoint、unknown model/quality/resolution/operation 均无匹配 rule。

官方证据：

- DeepSeek：[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、
  [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)；
- PoYo：[Seedance 2 model](https://poyo.ai/models/seedance-2)、
  [Seedance 2 API](https://docs.poyo.ai/api-manual/video-series/seedance-2)、
  [GPT Image 2 model](https://poyo.ai/models/gpt-image-2)、
  [GPT Image 2 API](https://docs.poyo.ai/api-manual/image-series/gpt-image-2)；
- SiliconFlow：[TTS billing](https://docs.siliconflow.com/en/userguide/capabilities/text-to-speech)、
  [USD pricing](https://www.siliconflow.com/pricing)、
  [global endpoint](https://docs.siliconflow.com/en/userguide/quickstart)。

## 文件结构

### 新建

- `src/models/provider_cost.py`
- `src/services/provider_price_catalog.py`
- `src/services/provider_execution.py`
- `src/services/provider_cost.py`
- `src/storage/provider_cost_repository.py`
- `configs/provider-cost-catalog.v1.json`
- `migrations/alembic/versions/b7c8d9e0f1a2_add_provider_cost_ledger.py`
- `tests/test_provider_cost_models.py`
- `tests/test_provider_budget_config.py`
- `tests/test_provider_price_catalog.py`
- `tests/test_provider_cost_repository.py`
- `tests/test_provider_cost_pg18.py`
- `tests/test_provider_cost_service.py`
- `tests/test_provider_execution_context.py`
- `tests/test_provider_cost_llm.py`
- `tests/test_provider_cost_tts.py`
- `tests/test_provider_cost_poyo.py`
- `tests/test_provider_paid_path_inventory.py`
- `tests/test_provider_job_context_routes.py`
- `tests/test_provider_cost_log_safety.py`
- `docs/runbooks/provider-cost-ledger-per-job-budget.md`
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`

### 修改

- `src/config.py`、`.env.example`
- `src/storage/db.py`、`src/storage/migrations/001_init.sql`
- `src/pipeline/generation_policy.py`、`src/pipeline/state_manager.py`、
  `src/pipeline/step_runner.py`、`src/pipeline/gate_manager.py`、
  `src/pipeline/token_smoke_preflight.py`、`src/pipeline/authorized_live_harness.py`、
  `src/pipeline/candidate_scorer.py`
- `src/routers/scenario.py`、`src/routers/pipeline.py`、`src/routers/admin/logs.py`
- `src/services/fast_mode.py`、`src/tasks/fast_task_registry.py`
- `src/tools/cost_tracker.py`、`src/tools/llm_client.py`、
  `src/tools/poyo_client.py`、`src/tools/seedance_client.py`、
  `src/tools/cosyvoice_client.py`、`src/tools/gpt_image_client.py`、
  `src/tools/dalle_client.py`、`src/tools/elevenlabs_client.py`
- Active `deepseek-chat` call sites：`src/agents/strategy.py`、
  `src/agents/script_writer.py`、`src/skills/product_strategy.py`、
  `src/skills/script_writer.py`
- Direct scenario operation-scope callers only where required：
  `src/pipeline/s1_product_pipeline.py`、`src/pipeline/s2_brand_pipeline_v2.py`、
  `src/pipeline/s3_remix_pipeline.py`、`src/pipeline/s4_live_shoot_pipeline.py`、
  `src/pipeline/s5_brand_vlog_pipeline.py`
- Existing cost/retry/provider/route/state/backup/schema tests affected by the new strict contract，
  including `tests/test_sprint3_compliance_resilience.py`、
  `tests/test_provider_retry_policy.py`、`tests/test_generation_policy_step_guard.py`、
  `tests/test_fast_mode_token_smoke_contract.py`、`tests/test_admin_health_provider_probe_guard.py`、
  `tests/test_token_smoke_preflight.py`、`tests/test_authorized_live_provider_harness.py`、
  `tests/test_run_alembic_upgrade.py` and `tests/conftest.py`
- Current runbook index、API reference、roadmap、project guide、Kiro 与 SDD state documents，
  only after fresh evidence

### 明确不修改

- Acceptance、publish、delivery、metrics、C2PA/transparency 的业务合同或 schema
- Public request/OpenAPI surface、frontend product components、stores 或 generated types
- Production `.env.prod`、deploy/SSH files、credential/key files
- Archive/research/draft 历史正文
- W1-26 live publish harness、W1-31 real billing reconciliation
- Existing idempotency/acceptance/publish migration bodies or their frozen baselines

---

## Task 0：批准规格、基线与价格证据冻结

**只读证据：** approved spec、scoped `git status`、Alembic head、paid-path inventory、
focused baseline、official price pages。

- [x] 确认规格为 `status: approved`，本计划获得独立的 implementation approval，且
  当前 branch/worktree 与计划记录一致。
- [x] 从 `migrations/` 运行 Alembic heads，确认唯一 head 仍是
  `a6b7c8d9e0f1`；确认新 revision `b7c8d9e0f1a2`、计划文件和 Task 13 report
  无冲突。
- [x] 用 `rg` 重新枚举所有 paid mutation、`cost_tracker`、mutation retry、
  `deepseek-chat` alias、admin provider probe 与 provider client construction；保存
  exact manifest，不读取 secret。
- [x] 重新打开上述官方一手价格/response 页面并记录 checked date。任一 exact model、
  unit、price、endpoint 或 response field 漂移时停止实施并回到规格审批。
- [x] 运行当前 cost/provider/retry/generation-policy/route focused baseline，记录真实
  pass/fail；历史测试失败不得被归为本计划通过证据。

## Task 1：Strict models、预算解析与 versioned catalog

**RED files：** `tests/test_provider_cost_models.py`、
`tests/test_provider_budget_config.py`、`tests/test_provider_price_catalog.py`。

- [x] RED：冻结七态 attempt、两类 account/source、allowlisted billing region、十个
  stable error code 与所有 strict field bounds；拒绝 coercion、unknown field、
  bool-as-int、negative、overflow、malformed JSON。
- [x] RED：冻结五个 billing-fact union。DeepSeek facts 必须满足两个 conservation
  equations；TTS UTF-8 bytes、image count、video task/duration 均为 strict integer。
- [x] RED：`PROVIDER_JOB_BUDGET_USD` 只接受无空白 canonical positive decimal，最多
  9 位小数；拒绝 exponent、sign ambiguity、NaN/Infinity、zero、overflow。缺失配置
  不提供隐式 `$5` fallback。
- [x] RED：missing/invalid budget 不得破坏 app import、health、no-media 或 local-fixture
  flow；只有进入 provider-capable account initialization 才返回 stable pre-network
  failure，且不能 silent fallback。
- [x] RED：catalog loader 验证 exact key、effective window、evidence date、component
  name/quantity uniqueness、finite catalog-operation vocabulary、integer nanos/unit
  size、no-float/no-wildcard/no-alias。
- [x] RED：model-contract metadata strict 验证 1,000,000 context、384,000 provider max
  output、4,096 application max output 与 995,904 derived input ceiling；caller override、
  app cap 超 provider max、sum mismatch 或 drift 均 zero-network。
- [x] RED：逐条锁定本计划冻结的 DeepSeek、PoYo 和 SiliconFlow 数值；验证每个
  component 独立 ceil、sum、overflow、PoYo microcredits 按同一 quantity/unit size
  exact division 且无 remainder，以及 catalog update 不重算历史 rule。
- [x] GREEN：实现 `src/models/provider_cost.py`、strict budget parser、
  `src/services/provider_price_catalog.py` 与 `configs/provider-cost-catalog.v1.json`。
- [x] GREEN：`src/config.py` 只暴露 default-off/strict path；`.env.example` 使用注释示例
  `PROVIDER_JOB_BUDGET_USD=5.00`，不形成 runtime fallback。
- [x] 运行三个 focused suites、Ruff、JSON parse、secret scan 与 scoped diff check。

## Task 2：两表 migration 与原子 repository

**RED files：** `tests/test_provider_cost_repository.py`、
`tests/test_provider_cost_pg18.py`，以及 existing schema/backup/restore/readiness tests。

- [x] RED：`job_budget_accounts` 覆盖 UUID、tenant/job/scenario identity、immutable cap/
  source/policy、reserved/settled nanos、UTC timestamps、unique tenant+kind+job 与
  conservation checks。
- [x] RED：`provider_cost_attempts` 覆盖 account FK、logical operation、server ordinal、
  fingerprint、provider/model/region/catalog operation/media/fact/rule、reservation/
  settlement facts、nanos、state、bounded non-authoritative provider-reported cost facts、
  safe external IDs/error、expiry/lifecycle timestamps。
- [x] RED：数据库约束至少覆盖 positive/nonnegative money、settled<=reserved、
  state-dependent required/forbidden fields、unique account+operation+ordinal、bounded
  enums 与 child-before-parent deletion。
- [x] RED：PostgreSQL reserve/transition 使用固定 account→attempt lock order 与
  `FOR UPDATE`；SQLite 使用 project lock + `BEGIN IMMEDIATE`；store/configured PG
  failure 不回退 SQLite 或 memory。
- [x] RED：same fingerprint replay、different fingerprint conflict、trusted new epoch
  分配 `max(ordinal)+1`、terminal transition idempotency、tenant isolation、malformed
  stored JSON fail closed。
- [x] GREEN：新增 revision `b7c8d9e0f1a2`（down revision exact
  `a6b7c8d9e0f1`），同步 `001_init.sql`、fresh SQLite、compat schema 与 DB readiness。
- [x] GREEN：实现 specialized `ProviderCostRepository`；禁止复用普通
  read-then-write `BaseRepository`。
- [x] 验证 SQLite fresh/existing/restart，PostgreSQL 18 upgrade、downgrade、re-upgrade、
  fresh-init、20-way concurrent reserve 和 exact row conservation。

## Task 3：ProviderCostService 与完整状态机

**RED file：** `tests/test_provider_cost_service.py`。

- [x] RED：account initialize 相同 identity idempotent，不同 cap/source/scenario/policy
  conflict；trusted authorization 只能通过 injected validated object 降低 server cap。
- [x] RED：trusted approval 从原始 JSON 用 Decimal hooks 解析并直接产出 integer nanos；
  exact 校验 display/numeric/total/per-job ceilings。现有 float report 字段只作兼容展示，
  raw dict/float/HTTP path/request body 不能成为 authority。
- [x] RED：`reserve_or_replay` 只接受 code-owned operation registry key、immutable
  fingerprint 与 optional trusted regeneration epoch；numeric ordinal 不在 API 中。
- [x] RED：实现 `reserved -> submission_started -> settled|submitted|released|ambiguous|
  accounting_error` 和 `submitted -> settled|released|ambiguous|accounting_error` 的
  exact CAS；非法/stale transition 零写入。
- [x] RED：只有未进入 `submission_started` 的 expired `reserved` 可自动 release；
  restart 后 `submission_started`/`submitted`/`ambiguous`/`accounting_error` 全部 hold。
- [x] RED：actual<=reservation 才 settle 并退回差额；actual>reservation 进入
  `accounting_error` 且保持完整 reservation；任一 transaction failure 全 rollback。
- [x] RED：safe external task/trace ID 有长度/字符 allowlist；raw URL/body/message/path
  不能进入 model、repository 或 log。
- [x] GREEN：实现 `ProviderCostService`、factory/injection hooks、typed errors、安全
  account/attempt readback；service 不包含任何 provider mutation 或 retry。
- [x] 运行 service+repository focused suites、20-way concurrency、restart 与 fault
  injection；Ruff/diff clean。

## Task 4：Immutable execution context、job identity 与持久化恢复

**RED files：** `tests/test_provider_execution_context.py`、
`tests/test_provider_job_context_routes.py` 的 context/account 部分。

- [x] RED：`ProviderExecutionContext` frozen 且只含 server-owned tenant、job kind/ID、
  scenario、effective cap/source/policy、bounded trusted authorization reference、
  generation policy version、retry=0 与 trusted regeneration epoch；普通 dict/request
  不得覆盖。
- [x] RED：contextvar 并发隔离、nested token reset、background task copy 与 explicit
  persisted-state reconstruction；missing/corrupt/wrong-tenant/unknown-version 均
  pre-network fail。
- [x] RED：canonical `/fast/submit` 使用预分配 task ID，`/scenario/{s}/submit` 使用
  预分配 scenario resource ID；idempotent replay 必须返回同一 account。
- [x] RED：direct Fast/S1–S5 创建 `compat_*` server UUID；legacy `/pipeline/start`
  复用其 server-owned thread ID；client `output_label` 永远不成为 account key。
- [x] RED：authorized-live harness 只有在既有 preflight pass 且 strict Decimal adapter
  产出 frozen authorization 后才能注入 context；不得给公开 report/OpenAPI 新增 nanos
  字段，不得在普通请求中接受 approval path。
- [x] RED：state/config 中只持久化 safe execution projection/account ref；public state
  edit、Gate、regenerate、cached/legacy state 不能修改或伪造这些字段。
- [x] RED：StepRunner、GateManager、regenerate 与 restart scope 从 persisted truth
  绑定 context；regeneration epoch 先持久化，再允许 repository 分配新 ordinal。
- [x] GREEN：实现 `src/services/provider_execution.py` 并接入 router/state/runner/gate/
  Fast registry；任何 account 初始化失败都发生在 provider-capable work 前。
- [x] 运行 tenant concurrency、idempotent replay、direct compatibility、state tamper、
  Gate/regenerate/restart focused tests。

## Task 5：DeepSeek exact usage 与 LLM mutation 收敛

**RED file：** `tests/test_provider_cost_llm.py`，plus existing LLM/retry/Fast/agent tests。

- [x] RED：`LLMClient` 在 mutation 前解析 exact provider/model/endpoint rule；只允许
  `deepseek-v4-flash`/`deepseek-v4-pro` + `deepseek_global_usd`。
- [x] RED：reservation 使用 frozen 995,904 maximum input 全 cache-miss，加 frozen 4,096
  maximum output；caller 不能改变 `max_completion_tokens`，无 finite envelope/rule/
  context/cap 时禁止 client construction/network。
- [x] RED：一次 `_async_invoke` 后保留完整 response metadata，提取五个 usage integers，
  验证两个 conservation equations，settle 后才返回 content。
- [x] RED：missing cache split、contradiction、bool/negative/overflow、actual over reserve
  进入 `accounting_error`；timeout/disconnect/ack loss 进入 `ambiguous`；两者都不
  retry、不 fallback。
- [x] RED：active `deepseek-chat` call sites 全部变为 `deepseek-v4-flash`；
  `deepseek-chat`、`deepseek-reasoner`、OpenAI、Anthropic、Kimi 和 unknown model 在
  当前 catalog 下 zero-network blocked。
- [x] GREEN：移除包住 LLM mutation 的 generic retry，保留兼容的 string return API；
  provider success 后 accounting failure 不得返回 content。
- [x] GREEN：同步 Fast Mode、strategy/script agents 与 skills 的 exact model tests；
  historical research/archive 文档不改。
- [x] GREEN：trusted regeneration epoch 的 `epoch_ref` 持久化到 attempt；同一
  account + logical operation 的同一 epoch 只能分配一次新 ordinal，跨 server-owned
  slots 仍可在同一 regeneration execution 中各自分配一次。
- [x] GREEN：脚本类 Gate 的 candidate generation/regeneration 与 candidate scorer
  使用同一持久化 epoch；相同 prompt 的 regeneration 获得新 ordinal，同 epoch
  重放只读 replay；媒体/非账本 Gate 仍在网络前阻断。
- [x] 运行 fake response、network-construction guard、alias static scan、concurrency、
  retry=0 与 existing LLM/Fast focused suites。

## Task 6：SiliconFlow TTS exact UTF-8 bytes 与 artifact 分界

**RED file：** `tests/test_provider_cost_tts.py`，plus existing CosyVoice/Fast/audio tests。

- [x] RED：只允许 exact `FunAudioLLM/CosyVoice2-0.5B`、
  `https://api.siliconflow.com/v1` 与 `siliconflow_global_usd`；`.cn`、custom URL、
  unknown model/region 在 client construction/network 前阻断。Voice 继续遵守既有
  provider request validator，但不是 price-catalog dimension，不得阻断其他合法 voice。
- [x] RED：冻结最终 provider `input`，严格 `encode("utf-8")`；覆盖 ASCII、CJK、emoji、
  combining marks、unpaired surrogate、empty、oversize；fingerprint 只含 digest/byte
  count，不存原文。
- [x] RED：exact byte count reserve → `submission_started` → 一次 speech POST → 用同一
  byte fact settle；response duration/size 不改变 cost。
- [x] RED：provider success 后先 settle，再写 staging file/format-duration probe；任何
  local artifact failure 保持 settled。Timeout/ack loss 保持 reservation，不能转 silent
  MP3。
- [x] RED：missing-key/no-media 明确 no-submit 可返回标注 fallback 且零 attempt；provider
  已开始后禁止 silent/stub fallback。
- [x] GREEN：把 source default/global active docs 切到 `.com` endpoint；production env
  不读取、不修改。保留 duration probe 仅作 artifact QA。
- [x] 运行 exact byte arithmetic、log/data-minimization、artifact failure、fallback、
  Fast TTS focused suites和 network guard。

**Task 6 closeout (2026-07-17):** `completed_local / independent_review=true`。
Fresh fixture evidence is Task 6 TTS `21 passed` (fake asyncpg/SQLite/fake HTTP),
provider-cost/context regression `90 passed`, and Fast fallback/metadata `2 passed,
11 deselected`; target Pyright is `0 errors, 0 warnings, 0 informations`, scoped Ruff,
Python compile, and `git diff --check` are clean. The same read-only reviewer returned
`PASS / APPROVE` with `Critical=0`, `High=0`, `Medium=0`, `Low=1` nonblocking status-doc
note. Native pytest remains unavailable because macOS `dyld` blocks the repository's
asyncpg/codec extensions; no provider, production, external network, or real-database
action was performed.

## Task 7：PoYo GPT Image 2 与 Seedance 2 async accounting

**RED file：** `tests/test_provider_cost_poyo.py`，plus current PoYo/GPT Image/Seedance tests。

- [ ] RED：`PoyoClient` 将 submit、poll/status、settle、download 显式分段；同一 attempt
  只允许一次 submit，poll/download 可有界重试且不能创建新 attempt。
- [ ] RED：valid task ID 后持久化 `submitted`；poll exhaustion 保持 submitted；ack loss/
  missing/conflicting task ID 进入 ambiguous；terminal no-charge 只有 exact contract
  证明时 release。
- [ ] RED：terminal status 的 `credits_amount` 直接从 JSON number 严格解析为 integer
  microcredits，不得经过 float；只有与 frozen rule expected microcredits 完全相等才可
  settle。`finished` 的 missing/negative/overflow/noncanonical/mismatch 均
  accounting_error 并 hold。
- [ ] RED：PoYo terminal `failed` 只有 strict zero charged microcredits 才 release；
  nonzero credits 进入 accounting_error，missing/invalid credits 进入 ambiguous；running/
  queued 的 credits 不触发 terminal transition。
- [ ] RED：GPT Image 2 冻结 exact quality、size、requested/effective resolution 与 count=1；
  literal 实现本计划的 auto/custom/4K downgrade truth。Terminal charged credits 匹配后
  先 settle；download failure 不撤销 cost。
- [ ] RED：`gpt-image-2-edit` 与任何未冻结 image model/operation 即使出现在 provider
  availability 中也必须 zero-network blocked；availability 不等于 catalog support。
- [ ] RED：PoYo image 不能再记为 `poyo_video`；multiple/missing files、count mismatch、
  unknown quality/resolution 均 accounting_error 或 pre-network block。
- [ ] RED：Seedance 只允许 `seedance-2`/`seedance-2-fast` 的 current no-video-input
  text/image operation、exact resolution、4–15s duration。Reference-video/native
  Seedance、reference-audio、standard 4K 与任何未列 resolution 没有 matching rule，
  必须 zero-network blocked。
- [ ] RED：terminal charged credits 匹配后，使用冻结且被 provider 接受的 task/
  duration/resolution facts settle，再 download；paid failure/settlement failure 不得降级
  `_stub_mode`。
- [ ] GREEN：移除 whole submit+poll retry loops 与 post-download legacy `track()`；保留
  no-key/no-media pre-submit stub truth。
- [ ] 运行 full price matrix、async restart、download failure、no-retry、network guard、
  log safety 与 existing image/video focused suites。

## Task 8：未定价 legacy/admin 路径阻断与旧 tracker 退役

**RED file：** `tests/test_provider_paid_path_inventory.py`，plus existing admin/legacy tests。

- [ ] RED：direct OpenAI GPT Image、DALL-E、ElevenLabs、PoYo music/lyrics TTS、native
  Seedance、unsupported LLM provider/model 没有 exact catalog rule 时全部在 network
  client construction 前返回 stable blocked truth。
- [ ] RED：admin external-provider health 不得再通过 `LLMClient.ainvoke("", "hi")` 产生
  paid mutation；改为 disabled/config readiness，不创建 account/attempt/network。
- [ ] RED：静态 inventory 枚举 `httpx` POST/mutation SDK calls、`retry_with_backoff`、
  `_execute_with_retry`、`submit_poll_download` 与所有 provider constructors；每条只能是
  cost-integrated 或 explicit zero-network blocked。
- [ ] RED：`src/tools/cost_tracker.py` 不再包含 float price、module `_records`、soft/hard
  runtime authority。残留 `track/check_budget/set_thread_id` runtime import 使测试失败。
- [ ] GREEN：把旧 tracker 收敛为 fail-closed compatibility tombstone 或删除已确认无
  caller 的 symbols；StepRunner 移除 Expert-only process-local budget check。
- [ ] GREEN：更新旧 Sprint 3/cost tests 为 durable service/legacy-disabled truth；禁止
  为保留旧测试而双写新 ledger 与 `_records`。
- [ ] 运行 paid-path inventory、admin no-provider guard、global socket/client-construction
  guard、retry static scan、Ruff 与 scoped diff。

## Task 9：Fast、S1–S5、Gate/regenerate 与 restart 全路径闭环

**RED file：** `tests/test_provider_job_context_routes.py`，plus current async/direct/state/
Gate/regenerate/hermetic suites。

- [ ] RED：Fast async owner/replay/recovery、Scenario async S1–S5、direct Fast/S1–S5、
  legacy pipeline start 都在 provider-capable work 前拥有 tenant-bound account/context。
- [ ] RED：相同 canonical idempotency submission 重放同一 account/attempt，不重复
  mutation；不同 request fingerprint conflict 且 zero network。
- [ ] RED：StepRunner 的 code-owned registry entry 包含 stable scenario/step template、
  finite catalog operation 和 bounded server-derived item/candidate slot schema；实例级
  logical operation/fingerprint 绑定 slot，同 fingerprint restart 返回 durable attempt，
  不自动 resubmit。
- [ ] RED：Gate candidate generation、candidate regenerate、step force/regenerate 与 quality
  regenerate 只有在 server epoch 已持久化后获得新 ordinal；client candidate/label 不能
  直接选择 ordinal。
- [ ] RED：no-media S1–S5 与 refs-only paths 为零 attempt；bounded profiles 的
  provider job caps 仍限制数量，但不能替代 monetary hard cap。
- [ ] RED：missing/invalid budget、catalog、context、account store 在任何 paid mutation
  构造前失败；业务投影保留 bounded degraded reason，不泄漏金额以外敏感事实。
- [ ] GREEN：补齐 operation scopes、persisted execution projection 与 route/service
  binding；不得新增 HTTP 字段或 frontend contract。
- [ ] 运行 Fast/S1–S5 hermetic、idempotency、Gate/regenerate、state tamper、restart、
  multi-tenant concurrency 与 no-provider suites。

## Task 10：全量验证、文档、证据与审查

- [ ] 运行所有新 W1-27–W1-30 suites 与受影响的 W1-08/W1-11/W1-15/W1-16 provider/
  idempotency/generation-policy regression。
- [ ] Disposable PostgreSQL 18 执行 prior-head → `c8d9e0f1a2b3` upgrade、metadata/check/
  index proof、downgrade、re-upgrade、fresh-init、concurrency/restart repository/service
  tests；只记录 local-test DB writes。
- [ ] 运行 SQLite fresh/existing/compat/restart、backup/restore/schema readiness、
  Alembic single-head、fresh-init table-set 与 logical dump contracts。
- [ ] 运行 backend Ruff、focused/full pytest/`make ci`；记录 fresh exact counts，禁止用
  truncated output 下结论。
- [ ] 运行 OpenAPI drift 证明无新 public surface；运行 frontend Vitest、ESLint、
  TypeScript 与 Next build 证明无意外 public behavior change。
- [ ] 运行 paid-path static inventory、zero-network guard、log/secret/prompt/path scan、
  catalog no-float/wildcard/alias scan、`git diff --check` 与 temporary artifact scan。
- [ ] 编写 `docs/runbooks/provider-cost-ledger-per-job-budget.md`：状态机、error matrix、
  account/readback、restart、expiry、blocked providers、schema-first rollout、provider-off
  rollback、W1-31 exact gate。
- [ ] 锁定未来 production rollback 顺序：先禁用全部 provider mutation，再备份并
  schema-first migrate/verify，最后部署或回滚 binary；旧 binary 在 provider enabled
  状态下不得运行。Production schema downgrade 不是自动 rollback，本批只在
  disposable PostgreSQL 18 执行 downgrade。
- [ ] 用新鲜证据同步 tracked roadmap、AGENTS 与 provider-cost runbook
  index、API reference、Kiro 与 SDD progress；不得把 local settled 说成 invoice truth。
- [ ] Main-thread self-review pass 1：authority、transaction、conservation、exact price/
  billing fact、retry、restart、tenant、privacy、安全与 rollback。
- [ ] Main-thread self-review pass 2：paid-path completeness、tests、migration lifecycle、
  docs、diff scope、generated artifacts 与 claim/evidence alignment。
- [ ] 尝试项目允许的独立 Codex review；只有实际完成且 accepted actionable findings=0
  才能记录 `independent_review=true`。不可用/超时不得算通过。
- [ ] 最终状态只可根据真实证据二选一：
  `completed_local / independent_review=true`，或
  `implementation_complete_local / independent_review_pending`、
  `independent_review=false`；两者都必须保留全局固定证据边界。

## 实施批准门

本计划与规格 §28 exact price correction 均已获批准；当前重新执行 Task 0。批准仍
不包含 stage、commit、push、PR、merge、deploy、production migration、provider
call、token smoke、publish 或 delivery。
## Task 0 manifest correction — direct OpenAI vision scoring

Task 0 found one reachable paid mutation omitted from the original file manifest:
`src/pipeline/candidate_scorer.py` directly constructs OpenAI `gpt-4o` vision chat
completion. The approved catalog has no rule for this provider/model/operation, so this file
is now part of the Task 7 zero-network legacy/unsupported-path blocking surface and the
Task 8 paid-path inventory gate. This is a completeness correction under the already-approved
fail-closed architecture, not an expansion of the catalog or provider authority.
