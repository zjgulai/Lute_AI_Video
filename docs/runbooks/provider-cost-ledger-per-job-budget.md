---
name: runbook-provider-cost-ledger-per-job-budget
description: Provider cost ledger and per-job budget recovery. Use for local validation or an explicitly authorized incident review involving DeepSeek reservation, exact usage settlement, ambiguous outcomes, accounting errors, or stale reservations.
---

# Runbook — Provider Cost Ledger / Per-Job Budget

| | |
|---|---|
| **触发场景** | `provider_cost_*` contract error、attempt 停在 `reserved`/`submission_started`、账本金额与 provider usage 不一致，或预算预留拒绝 |
| **影响范围** | 付费 LLM mutation、Task 6 SiliconFlow TTS、Task 7 PoYo image/video 账单入口，以及 Task 8 legacy/admin fail-closed 边界 |
| **预期 MTTR** | 5–30 分钟（本地故障）；真实账务对账不在本 runbook 授权范围 |
| **相关代码** | [`src/tools/llm_client.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/llm_client.py) · [`src/tools/poyo_client.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_client.py) · [`src/tools/cost_tracker.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/cost_tracker.py) · [`src/routers/admin/logs.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/admin/logs.py) · [`src/services/provider_cost.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/services/provider_cost.py) · [`src/storage/provider_cost_repository.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/provider_cost_repository.py) · [`configs/provider-cost-catalog.v1.json`](file:///Users/pray/project/hermes_evo/AI_vedio/configs/provider-cost-catalog.v1.json) |

## 0. 先确认边界

W1-27--W1-30 的完成证据仍只限 local/fixture/disposable PostgreSQL。W1-31
是唯一后续例外：2026-07-19 已消费一份 exact one-shot authority 并执行一次真实
PoYo mutation，provider 返回 HTTP 403，ledger 保留 `ambiguous` 与 `$0.01`
reservation，未自动重试、未取得 task/charge fact、未完成 billing reconciliation。

当前合并边界：`production unchanged` · `provider_call=true (W1-31 only)` ·
`provider_attempt_made=true (count=1)` · `database_write=local-authorized-live-ledger-only` ·
`live_publish=false` · `live_send=false` · `billing_reconciliation=false` ·
`invoice_reconciliation=false`

Task 5 DeepSeek、Task 6 SiliconFlow TTS、Task 7 PoYo GPT Image 2/Seedance 2、
Task 8 legacy/admin 阻断与旧 tracker 退役、以及 Task 9 Fast/S1-S5/Gate/
regenerate/restart closure 均为 `completed_local / independent_review=true`。
Task 5--9 的同线程独立审查均为 `PASS / APPROVE`，`accepted_actionable_findings=0`。
Task 9 还锁定了 finite server-owned operation scopes、trusted regeneration epoch、
tenant/job context 与 no-media/bounded terminal truth；它没有新增 HTTP 或 frontend
contract。Task 10 已完成全量验证、migration lifecycle、backup/restore、文档与独立
审查；同一只读审查线程返回 `PASS / APPROVE` 且 `accepted_actionable_findings=0`，
因此整批 W1-27--W1-30 当前为 `completed_local / independent_review=true`。这仍只
表示 local/fixture/disposable evidence，不表示 production migration、invoice truth
或 live provider acceptance。
此前 TTS fixture `21 passed`、provider-cost/context regression `90 passed`、Fast
fallback/metadata `2 passed, 11 deselected`、Task 8 聚焦 `453 passed, 2 skipped`、
Task 9 hermetic `280 passed` 与 expanded provider-cost `763 passed, 2 deselected`
均为 local/fixture/disposable evidence；native pytest 仍可能受 macOS `dyld`
加载 asyncpg/codec 扩展影响，不能把 fixture 证据外推为 native green。

不要在诊断命令中打印或读取 `.env`、API key、完整 prompt、完整 provider response 或账本中的敏感原文。没有单独的 owner authorization 时，不执行真实 provider request、生产迁移、生产数据库写入或 billing reconciliation。

## 1. 合同速查

- DeepSeek paid mutation 只允许 `deepseek-v4-flash` / `deepseek-v4-pro`、`deepseek_global_usd`、`https://api.deepseek.com` 和 `chat_completion`。
- 每次 mutation 由服务端固定预留 `995904` 个最大 input tokens（按全 cache-miss）和 `4096` 个最大 output tokens；caller 不能覆盖 `max_completion_tokens`。
- Task 6 SiliconFlow TTS 只允许 `FunAudioLLM/CosyVoice2-0.5B`、
  `https://api.siliconflow.com/v1` 与 `siliconflow_global_usd`。账单事实是最终
  provider `input` 的严格 UTF-8 byte count；fingerprint 只保留 digest 与 byte
  count，不保存原文。流程固定为 `reserve → submission_started → one POST →
  settle → artifact probe`。artifact probe 失败使用
  `provider_cost_artifact_failed`，成本仍保持 `settled`；timeout/ack loss 保持
  `provider_cost_outcome_ambiguous`，不得 silent/stub fallback。
- SDK client 只能在 durable `reserved → submission_started` 成功后构造；一次 mutation 使用 `max_retries=0`，没有 generic retry 或 provider fallback。
- response 必须提供五个 strict integer facts：`prompt_tokens`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`completion_tokens`、`total_tokens`。同时满足：
  - `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`
  - `total_tokens = prompt_tokens + completion_tokens`
- usage 解析失败、cache split 矛盾、负数/bool/overflow、或实际 usage 超过冻结 envelope → `accounting_error`；timeout、disconnect、ack loss → `ambiguous`。两者都不能自动重试或返回 content。
- stable `operation_key` 是 provider template；`operation_instance` 是 bounded server-owned slot（例如 `variant.standard.brief.0.lang.en`）。workflow regeneration epoch 是独立的 trusted authority，用于同一 logical operation 分配新 ordinal；`regeneration_epoch_ref` 会随 attempt 持久化，同一 account + logical operation 的同一 epoch 只能消费一次，跨 slot 可各自消费一次；prompt digest 只在 fingerprint 中，不作为 logical-operation 名称。
- 脚本类 Gate 的 candidate generation/regeneration 与 scorer 共享同一持久化 epoch；相同 prompt 只有在新 epoch 下才会得到新 ordinal。媒体或尚未接入账本的 Gate 仍在 provider/network 前 fail closed。

## 2. 状态与恢复规则

```text
reserved → submission_started → settled
        ├→ released          (仅 submit 前确定未发送，或过期 reserved)
        ├→ ambiguous          (provider outcome 不确定，保留 reservation)
        └→ accounting_error   (provider response 已到但账务事实无效，保留 reservation)
submission_started → submitted → settled | ambiguous | accounting_error
```

1. 先只读查询 tenant-bound `account` 与 `attempt`，确认 `attempt_id`、`logical_operation`、`ordinal`、model、region、reservation 和 state；禁止使用跨 tenant 的 ID 作为恢复依据。
2. `reserved` 过期可以由受控 expiry path release；`submission_started`、`submitted`、`ambiguous`、`accounting_error` 过期也不能自动释放或重发。
3. `ambiguous` 只能走 provider-owned reconciliation/人工授权流程；本地 run 不得猜测成功/失败，不得恢复已消费的 authority。
4. `accounting_error` 先保留原始结构化 usage/错误码供审计，`settled_usd_nanos` 必须为 `0`；修复账务代码后重新运行 fixture，不修改历史 attempt 伪造 settled。
5. 同一 epoch 与同一 fingerprint 的 replay 必须返回原 attempt；新的
   `regeneration_epoch_ref` 属于 mutation-intent fingerprint，因此即使 prompt
   相同也必须先持久化新 epoch，再申请新的 ordinal。客户端重启不改变 hard cap
   或已记录状态。

### Account / readback / operation scope

- `job_budget_accounts` 是唯一 budget authority：`tenant_id + job_kind + job_id`
  唯一，`cap_usd_nanos`、source kind/ref 与 policy version 创建后不可由 caller
  覆盖。每次诊断先按 tenant-bound identity 读取 account，再读取该 account 的
  attempt；禁止用裸 `attempt_id` 或跨租户 job label 恢复。
- `provider_cost_attempts` 的 safe projection 只可返回 identity、state、ordinal、
  frozen rule、reservation/settlement facts、bounded external id 和 safe error code。
  不返回 prompt、credential、完整 provider response、原始路径或异常文本。
- `operation_key` 是稳定 catalog template；`operation_instance` 必须来自
  server-owned finite scenario/step/gate/candidate slot。caller 传入的 scope label
  会被覆盖或 fail closed，不能通过 `client.elevated`、wildcard 或未注册 step
  扩大账本 slot。
- 服务端 route 必须在构造 paid client 前绑定 tenant/job account、generation policy
  与 operation scope；重启 readback 只恢复 durable state，不会自动重新 submit。

## 3. 只读诊断与本地复现

从仓库根目录执行，不设置任何 provider key：

```bash
git status --short --branch
rg -n "deepseek-chat|deepseek-reasoner|retry_with_backoff|cost_tracker|raw_preview" src/tools/llm_client.py src/agents src/skills src/pipeline
.venv/bin/pytest -q tests/test_provider_paid_path_inventory.py tests/test_admin_health_provider_probe_guard.py
.venv/bin/pytest -q tests/test_provider_cost_llm.py
.venv/bin/pytest -q tests/test_provider_cost_models.py tests/test_provider_budget_config.py tests/test_provider_price_catalog.py tests/test_provider_cost_repository.py tests/test_provider_cost_service.py tests/test_provider_execution_context.py tests/test_provider_job_context_routes.py tests/test_provider_retry_policy.py tests/test_provider_cost_llm.py
.venv/bin/pytest -q tests/test_backup_production_contract.py tests/test_pg_restore_logical.py tests/test_run_alembic_upgrade.py
PYTEST_INCLUDE_HERMETIC_SLOW=1 .venv/bin/pytest -q tests/test_provider_cost_pg18.py -m hermetic_slow
make ci
git diff --check
```

这些命令使用 fake response、disposable SQLite/PG fixture 或静态检查；通过不代表 provider 已调用，也不代表生产账本已迁移。若要查看本地 fixture 的状态，使用测试返回的 safe projection；不要直接输出完整 `provider_cost_attempts` JSON。

## 4. 分类响应

### A. `provider_cost_rule_unavailable` / `provider_execution_context_missing`

先停止该 paid path，检查 model、endpoint、catalog version、tenant/job context、server cap 与 `provider_max_retries=0`。不要通过改 caller cap、切换 alias、启用 OpenAI/Anthropic/Kimi 或临时 fallback 绕过 fail-closed gate。

### B. `provider_cost_outcome_ambiguous`

这是 provider 是否收到请求不确定，不是普通可重试错误。保持 reservation，记录 safe error code 和 attempt identity，等待明确授权的 reconciliation 设计；不要再次 POST。

### C. `provider_cost_accounting_error`

检查五个 usage facts、两条 conservation equation、frozen model contract 和账本 price rule。保留 `accounting_error`，不要把 provider success 当作业务 success 返回给 caller；修复后仅重跑 fake/fixture。

### D. `provider_cost_artifact_failed`

provider 已成功且账本已结算，但本地 staging、format 或 duration probe 失败。删除不完整的本地 artifact，保留 `settled` attempt，不重发 provider mutation，也不生成 silent/stub 音频覆盖真实结果。

### E. 预算预留失败或重启后 cap 异常

核对 tenant-bound account 的 immutable cap、account source、attempt reservation 与 repository CAS。先做只读 replay/readback；不要删除 ledger rows、降低 cap、或直接写 `settled`。若涉及真实生产数据库，停止并升级给 owner。

## 5. Schema-first rollout 与 provider-off rollback

W1-31 的首次 one-shot authority 已消费并以 `provider_outcome_ambiguous` 结束；它
不能复用或自动重试。未来任何生产
rollout 必须由 owner 单独授权，并严格按以下顺序执行：

1. 先关闭全部 provider mutation（canonical、legacy、admin、background worker），
   验证新请求在 reserve/client construction 前稳定 fail closed；保留只读
   readback/health/status。
2. 对当前生产 schema 与 media 做 verified backup，确认 manifest、checksum、
   server/client major、schema signature、16-table logical dump、恢复目标为空，
   并完成 isolated restore + row parity；没有恢复 marker 不得继续。
3. 以 schema-first 方式执行 migration，逐项验证唯一 Alembic head、required tables、
   provider-cost constraints/indexes、account/attempt metadata 与 readback；本批
   只在 disposable PostgreSQL 18 执行 downgrade。生产 schema downgrade 不是自动
   rollback，也不能作为旧 binary 的先行步骤。
4. 只读核对 tenant/job account、reserved/settled conservation 与 stale-attempt
   状态；确认数据库写入、provider mutation 和 billing reconciliation 仍关闭。
5. 最后才部署经过审批的 binary/config，并保持 provider-off，完成健康、路由、
   migration/readiness 和 no-provider smoke；任何 binary rollback 也必须先回到
   provider-off，再按 owner 审批评估 schema 兼容性。
6. W1-31 真实 invoice/billing reconciliation 另需精确 provider sample、预算、
   双人确认和单独授权；本 runbook 永不自动发起外部账务调用。

本地/fixture 验证不得读取 `.env`、生产 DSN 或 credential，不执行真实 provider
request、生产 migration、deploy、publish、delivery 或 reconciliation。

## 6. W1-31 exact gate 与本地证据

W1-31 使用独立入口
`scripts/w1_31_provider_billing_reconciliation.py`，只允许一个 PoYo
`gpt-image-2` low/1K/1-image 样本。它不复用 C21 的 3-image + 1-video harness，
也不接受动态 provider/model/quality/resolution/budget。

Live 前必须全部满足：

1. 使用 `scripts/build_w1_31_billing_approval.py` 生成 `tmp/` 或仓库外的 `0600`
   private record；
2. `approved_by` 与 `confirmed_by` 是两个不同的具体人类，第二确认人于 30 分钟内
   人工确认可用 credits 至少为 2；
3. 24 小时内重新检查 PoYo model/API/status 官方页面，仍为 2 credits / `$0.01`；
4. exact authorization statement、`max_provider_calls=1`、`max_retries=0`、两小时内
   expiry 与 `$0.01` hard cap 全部匹配；
5. `POYO_API_KEY` 通过 presence-only 检查；不得打印 value，也不得从 `.env` 加载；
6. no-token preflight 为 `blocked=false`，且 code-owned consumption marker 不存在。

执行命令还需显式设置 `AI_VIDEO_W1_31_EXECUTE=1` 并传 `--execute`。runner 在
provider client construction 前以 `O_EXCL` 创建 approval-ID-bound `0600` marker；
无论后续是否 submit、是否返回 task ID、是否成功 settle，该 approval 都不得复用。
同一 task 的 status/download 可以有界重试，但 mutation 只能发生一次。

如果执行进程在 summary 前终止，不得复用 approval。使用
`scripts/read_w1_31_billing_ledger.py --run-directory <private-run-dir>` 只读重开
SQLite ledger；该命令不读取 key、不调用 provider，只报告 bounded account/attempt
事实，供人工决定是否需要新的 reconciliation 授权。

只有官方 expected 2 credits / `$0.01`、terminal `credits_amount=2_000_000`、本地
ledger `settled=10_000_000` USD nanos 且 conservation 完全一致，才可记录
`single_task_charge_reconciled=true`。这仍不是月账单或 invoice 对账；报告必须保留
`invoice_reconciliation=false`、`production_unchanged=true`。

当前实现的成功路径仍只有 local/fake-transport evidence。2026-07-19 的唯一真实
mutation 是 L4 authorized-live failed attempt：`provider_attempt_made=true`，但
`billing_reconciliation=false`、`invoice_reconciliation=false`，authority 已消费，
ledger 为 `ambiguous`。不得声称零扣费、task 一定未创建、credential 有效或 403
根因已知；任何 repaired attempt 都需要新的 exact authorization 与 fresh dual-human
funded evidence。

## 7. 相关文档

- `docs/superpowers/specs/2026-07-15-provider-cost-ledger-per-job-budget-design.md` — approved design source (historical planning material, not a production execution entrypoint)
- `docs/superpowers/plans/2026-07-15-provider-cost-ledger-per-job-budget.md` — approved implementation checklist (historical planning material, not a production execution entrypoint)
- `docs/superpowers/specs/2026-07-18-w1-31-provider-billing-reconciliation-design.md` — W1-31 exact single-sample design
- `docs/superpowers/plans/2026-07-18-w1-31-provider-billing-reconciliation.md` — W1-31 implementation and live-gate checklist
- [`docs/runbooks/deepseek-timeout.md`](./deepseek-timeout.md) — 上游可用性诊断（仍需遵守本 runbook 的 no-call boundary）
