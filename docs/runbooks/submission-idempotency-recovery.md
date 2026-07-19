---
title: Submission idempotency recovery
doc_type: workflow
module: backend-frontend
topic: tenant-scoped-submit-idempotency
status: stable
created: 2026-07-12
updated: 2026-07-12
owner: self
source: human+ai
---

# Submission idempotency recovery

## 触发场景

以下任一情况进入本 runbook：

- `POST /fast/submit` 或 `POST /scenario/{scenario}/submit` 已发出，但浏览器遇到网络错误、timeout、dispatch 后 abort，或代理 `500`/`502`/`503`/`504`；
- UI 长时间停在“确认任务是否已创建”、`reserved`、`initializing` 或 `unknown`；
- readback 返回 `recovery_required`；
- 同一个用户动作出现 `409 idempotency_payload_conflict`；
- `503 idempotency_store_unavailable`、`503 submission_state_uncertain`，或迁移后缺少 `idempotency_records`；
- 浏览器刷新或切换账号后无法重新绑定原 Fast/Scenario 任务。

## 影响范围与预期 MTTR

- **影响范围**：Fast Mode 和 S1-S5 的 canonical async submit、任务 readback、浏览器 pending state；blocking/legacy mutation 不在本契约内。
- **预期 MTTR**：客户端歧义恢复 2-5 分钟；数据库/迁移故障 15-30 分钟；`recovery_required` 的业务处置取决于人工确认，不以自动重跑作为 MTTR 手段。

## 不变量与安全边界

1. 一个明确的 Start/Generate 动作只对应一个稳定 `Idempotency-Key`。
2. 歧义响应后禁止 blind second POST；只能用原 key 执行 `GET /submissions/idempotency`。
3. tenant 来自服务端认证上下文。浏览器缓存不是 tenant authority；跨 tenant 与未知 key 都投影为同一个 `404 submission_not_found`。
4. 服务端只存 key hash，不存、回显或记录 raw key。事故单、日志、截图和命令输出不得包含 raw key、请求 payload、`X-API-Key`、Authorization 或 provider credential。
5. 浏览器唯一允许持久化 raw key 的位置是 pipeline store v2 的最小 `pendingSubmission`；不得附带请求 payload、prompt、model secret、provider/auth credential。
6. `provider_max_retries=0` 不变。本 runbook 不授权 provider retry、production migration、deploy、publish 或 delivery。
7. `recovery_required` 保留原 job identity，但不授权自动恢复或重新发送 provider mutation。

## 当前 active recovery schema contract

当前 active recovery 使用精确的有序 `current 16-table contract`；任何生产前备份、隔离恢复、
row parity 与 verify 都必须使用同一顺序。历史 2026-07-10 的 12-table、W1-15/16
阶段的 13-table 与 W1-22 阶段的 14-table 数字只属于带日期的历史证据，不是当前
恢复目标。

```text
tenants
admin_accounts
api_keys
admin_sessions
threads
pipeline_states
brand_packages
influencers
video_metrics
publish_logs
error_logs
audit_logs
idempotency_records
acceptance_records
job_budget_accounts
provider_cost_attempts
```

`scripts/pg_dump_logical.py`、`scripts/pg_restore_logical.py`、
`scripts/verify_restored_database.py`、Alembic/fresh-init/SQLite fixtures 与
`docs/runbooks/provider-cost-ledger-per-job-budget.md` 必须保持该 active set；
只恢复 `idempotency_records` 或只恢复业务表都不构成可恢复状态。

## 前 2-5 分钟立即诊断

只收集非敏感字段：HTTP status、stable detail code、response trace ID、kind、scenario、pending phase、resource ID（若已有）和时间。

1. 判断错误是否为结构化 `503 idempotency_store_unavailable`。
   - 是：这是 claim/downstream work 之前的确定失败。不要自动 retry；先恢复 durable store，再由用户明确继续同一动作。
   - 否：dispatch 后的网络错误、abort、timeout、`500`/`502`/`503`/`504`、`submission_state_uncertain` 都按歧义处理。
2. 检查浏览器 `pendingSubmission` 是否仍存在；不要复制其 raw key 到日志或工单。
3. 使用浏览器原 tenant/API-key 上下文执行 readback。若账号/API key 已切换，先恢复原 tenant 上下文，不要删除 pending record 或新建任务。
4. 若服务端异常，使用既有 secret-safe 运维通道检查 PostgreSQL 健康、`idempotency_records` 是否存在、required-table health 和后端错误类型。不要读取或打印 `.env`。
5. 以 ledger `record id` 或已经返回的 `resource_id` 追踪生命周期；不要要求服务端查找或输出 raw key。

## 浏览器 ambiguous readback 流程

浏览器必须在 POST 之前同步持久化 pending record。收到歧义结果后：

1. 把 phase 改为 `recovering`，保留同一个 key。
2. 在约 0、1、2、5 秒执行 bounded `GET /submissions/idempotency`。
3. `reserved` / `initializing`：继续 readback；此时 Scenario state 或 Fast task handle 可能尚未创建，不要提前调用 resource status，也不要 POST。
4. `queued` / `running`：绑定 readback 返回的原 `resource_id`，再进入对应 status polling。
5. `completed` / `failed` 等 terminal：绑定并处理原结果；完成 terminal handling 后才能清理 pending record。
6. `recovery_required`：直接显示恢复失败状态，不假定 resource status endpoint 一定存在，不自动 resume，不 POST。
7. bounded lookup 用尽：phase 设为 `unknown` 并保留 pending record。只提供“继续查询”（GET）。
8. 只有用户明确选择“放弃并开始新提交”后，才允许创建新 action/key；必须提示原 job 可能已经产生不可逆 provider side effect。

结构化 `409 idempotency_payload_conflict` 不是网络歧义：保留原 pending/action 信息，禁止自动生成 replacement key。先确认是否在同一 tenant 下改变了 payload、scenario、operation 或 effective policy。

## `recovery_required` 处置

`recovery_required` 表示 durable mapping 仍在，但非终态 owner 在 graceful shutdown、heartbeat/lease 丢失或 crash 后无法安全续跑。

- 把它与 `failed`、`404`、`queued` 分开呈现。
- 保留原 `task_id` / `label` 与 ledger 记录，禁止把 same-key replay 当成新执行。
- 检查是否已有 allowlisted terminal result 或 tenant-owned Scenario state；有证据时只做原 job 的只读结果投影。
- 当前版本不持久化 request-scoped provider credential/attempt authority，因此不能自动恢复付费 worker。
- 若业务方决定重新生成，必须明确放弃原 unknown/recovery job 后创建新 action/key；这是一项新的付费风险决策，不是技术 retry。

## 本地迁移与验收顺序

本地和 CI 只使用 isolated SQLite 与 disposable PostgreSQL 18，不连接生产：

1. 验证 Alembic 从当前 prior head 经 `d5e6f7a8b9c0`、`e8f1a2b3c4d5`、`f9a2b3c4d5e6`、`a6b7c8d9e0f1`、`b7c8d9e0f1a2` 到 `c8d9e0f1a2b3` 的 upgrade，并在 disposable database 上执行 downgrade/upgrade round trip；生产 schema downgrade 不属于自动 rollback。
2. 验证 fresh init SQL、Alembic upgrade 和 SQLite init 都包含当前 16-table set；其中 `idempotency_records`、`acceptance_records`、`job_budget_accounts`、`provider_cost_attempts` 的 columns、status checks、tenant/key unique 与 account/attempt constraints 必须一致。
3. 验证 concurrent claim 只有一个 owner；same payload replay、changed payload conflict、cross-tenant independence 和 stale lease reconciliation 都通过。
4. 运行 canonical HTTP、CORS、restart/readback 与前端 ambiguity/reload 测试；所有 provider 边界必须使用 fake，`provider_call=false`。
5. 运行 full backend/frontend gates、OpenAPI/types drift、secret scan 与 `git diff --check`。

最小 focused gate：

```bash
.venv/bin/pytest -q \
  tests/test_submission_idempotency_repository.py \
  tests/test_submission_idempotency_service.py \
  tests/test_submit_idempotency_router.py \
  tests/test_backend_route_auth_contract.py

cd web
npm test -- --run \
  src/lib/idempotentSubmission.test.ts \
  src/stores/persistence.test.ts
npx tsc --noEmit -p tsconfig.json
```

通过这些测试只代表 local/fixture acceptance，不代表 production 已迁移或部署。

## 生产迁移、部署与新恢复基线

以下步骤必须有独立 production-write/deploy 授权。默认状态始终是
`production unchanged`、`provider_call=false`；provider mutation、billing
reconciliation 与 live submit 在本 runbook 中保持关闭。

1. **provider-off gate**：先禁用 canonical、legacy、admin 与 background
   provider mutation，确认 reserve/client construction 前稳定 fail closed；只保留
   tenant-bound readback、health 与 status。旧 binary 不得在 provider enabled 状态下先运行。
2. **verified backup**：在任何 schema 变更前完成当前生产 schema 与 media 的
   verified backup，确认 manifest、checksum、schema signature、server/client major、
   当前 16-table logical dump、空恢复目标，并完成 isolated restore + row parity。
   历史 2026-07-10 的 12-table、W1-15/16 的 13-table 与 W1-22 的 14-table 只保留为
   带日期的验收事实，不改变当前恢复目标。
3. **migration artifact preflight**：确认 migration runner 的 offline SQL 从当前
   revision 动态解析到唯一 current head `c8d9e0f1a2b3`，并覆盖
   `idempotency_records`、acceptance 与 provider-cost ledger migrations；固定旧
   revision range 或缺少任一表时立即停止。
4. **schema-first**：执行已 review 的 additive migration，验证唯一 Alembic head、
   当前 16-table set、所有 provider-cost/account/attempt constraints/indexes 与
   tenant-bound readback；生产 schema downgrade 不是自动 rollback。
5. **read-only verification**：只读核对 revision、required-table health、account/
   attempt conservation、reserved/settled/ambiguous 状态与 stale-attempt 规则；
   继续保持 provider mutation 与 billing reconciliation 关闭。
6. **provider-off binary rollout**：最后才部署经过审批的 binary/config，保持
   provider-off，检查 `/health`、CORS `Idempotency-Key` preflight、缺 header 的
   deterministic `400`、tenant-bound readback 和 no-token smoke（`RUN_TOKEN_SMOKE=0`）。
   binary rollback 也必须先回到 provider-off，再由 owner 评估 schema compatibility。

应用 rollback 只回滚 code/image，保留 additive ledger tables；正常应用回滚不得
执行 migration downgrade/drop table。尤其已有 claim 或 provider attempt 后，删除
任一 ledger 会重新打开 duplicate-paid-submit 或不可恢复成本状态风险。表删除只能在
更晚的独立数据保留决策和显式授权下进行。

## 故障分类与响应

| 信号 | 含义 | 响应 |
|---|---|---|
| `400 idempotency_key_required` | caller 未升级 | 给 canonical async POST 增加稳定 header；不要改成 server fallback key |
| `400 idempotency_key_invalid` | duplicate/格式/长度错误 | 修 caller，确保 exactly one 16-128 char opaque key |
| `409 idempotency_payload_conflict` | same tenant/key 的 canonical request 不同 | 不改原记录、不自动换 key；确认是否为真正的新动作 |
| `404 submission_not_found` | 当前 tenant 不可见 | 检查是否账号/tenant 已切换；响应不能暴露其他 tenant 是否存在 |
| `503 idempotency_store_unavailable` | claim 前 durable store 不可用 | 恢复 PG/table；禁止自动 mutation retry |
| `503 submission_state_uncertain` | claim 后状态更新不确定 | 只用 same-key GET readback；禁止第二 POST |
| `reserved` / `initializing` | owner 正在准备或尚未创建 resource state | 继续 readback，不提前 status，不 POST |
| `unknown` | bounded readback 尚无确定结果 | 保留 pending；提供 continue-query GET |
| `recovery_required` | owner 丢失且不能安全续跑 | 保留原 identity；人工决定 abandon/new action |
| cross-tenant 与 unknown 同为 `404` | 防枚举边界正常 | 不增加可区分错误或日志回显 |

## 永久修复与防回归

- 所有 repository-owned async callers、production Playwright specs 和 API examples 必须显式发送 action-stable `Idempotency-Key`。
- CORS allowlist 必须包含 `Idempotency-Key`；`submissions.router` 必须通过 `verify_api_key` 挂载。
- ledger 继续使用 tenant-scoped key hash、secret-free fingerprint、CAS terminal/lease transition；不得退回 memory/filesystem authority。
- browser mutation retry 保持 0；reload/hydration 只做 GET。
- 每次调整 pending schema 都升级 persistence version、补 migration test，并重新审计 payload/credential 排除项。
- 每次 schema/table-set 变更都同步 fresh init、Alembic、SQLite、health、logical dump/restore/verify 和 DR 文档；历史验收数字保留其时间上下文。

## 相关实现与文档

- [API endpoint reference](../reference/api-endpoints.md)
- Approved design: `docs/superpowers/specs/2026-07-12-tenant-scoped-submit-idempotency-design.md`
- [Frontend persistence migration](./frontend-store-persistence-migration.md)
- [Backend route auth contract](./backend-route-auth-contract.md)
- [Disaster recovery runbook](../disaster_recovery_runbook.md)
- `src/services/submission_idempotency.py`
- `src/storage/idempotency_repository.py`
- `src/routers/submissions.py`
- `src/routers/scenario.py`
- `web/src/lib/idempotentSubmission.ts`
- `web/src/stores/persistence.ts`
- `migrations/alembic/versions/d5e6f7a8b9c0_add_submission_idempotency_records.py`
- `scripts/pg_dump_logical.py`
- `scripts/pg_restore_logical.py`
- `scripts/verify_restored_database.py`
