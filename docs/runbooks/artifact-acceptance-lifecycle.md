---
title: Artifact acceptance lifecycle
doc_type: workflow
module: backend
topic: single-use-human-acceptance
status: stable
created: 2026-07-12
updated: 2026-07-13
owner: self
source: human+ai
---

# Artifact acceptance lifecycle

## 触发场景

以下任一情况进入本 runbook：

- reviewer 要为 canonical async Fast 或 S1-S5 的最终视频创建 accepted/rejected 记录；
- create 的响应丢失，需要判断是 owner `201`、idempotent replay `200` 还是 `409` conflict；
- read/revoke 返回 `404`、`409` 或 `503`；
- acceptance 已过期，或记录创建后最终文件被替换、删除、截断；
- W1-23 publish attempt 报告 uncertain consume，需要按 attempt correlation
  判断 acceptance 是否由本次尝试消费；
- migration/restore 后缺少 `acceptance_records` 或 provider-cost ledger，或
  16-table recovery contract 漂移。

## 影响范围与预期 MTTR

- **影响范围**：acceptance create/read/revoke、review authority、过期/撤销状态、
  W1-23 publish 前置校验与 consume correlation；本地 runbook 不执行 live
  publish/delivery。
- **预期 MTTR**：请求/权限问题 2-5 分钟；文件 integrity 或数据库问题 15-30 分钟；生产 migration/deploy 不在本 runbook 的默认授权范围。

## 不变量与前置条件

1. HTTP surface 只有：
   - `POST /acceptance-records`（create）；
   - `GET /acceptance-records/{acceptance_id}`（read）；
   - `POST /acceptance-records/{acceptance_id}/revoke`（revoke）。
2. 三条 route 都要求有效 `X-API-Key`，且 reviewer permission 必须是 `artifact:accept` 或 `all`。只有 `provider:submit` 的 key 不足，返回 `403 Insufficient permission`。
3. `tenant_id`、reviewer identity、scenario、artifact digest/size、status、expiry 与 consume metadata 都由服务端决定；request 不得自报这些 authority fields。
4. accepted source 必须来自当前 tenant 的 durable Fast/Scenario submission，状态为 `completed`，并投影到 exact canonical final video path：`pending_review`、`.mp4`/`.webm`、`full_media_success=true`、`is_stub=false`、`pipeline_degraded=false`。请求路径必须与 durable source 的最终路径逐字一致，文件必须存在于 tenant-owned output root。
5. rejected decision 仍要求 terminal (`completed`/`failed`) 且存在合法 final-video projection；它不会生成可 consume 的 authority。
6. create 使用一个 action-stable `Idempotency-Key`。服务端只持久化 hash，不记录或回显 raw key；日志、工单和截图不得包含 raw key、`X-API-Key`、请求正文或 provider credential。
7. 当前 **no UI**：没有新增 review UI。当前 **no HTTP consume**：consume 只存在于 internal service boundary。
8. W1-23 integration 已达到 `completed_local`：只有 `artifact:publish|all` 的
   canonical/deprecated adapter 可把 acceptance ID 传入 shared service；
   `artifact:accept`、`provider:submit`、client path 和 body human assertion
   都不是 publish authority。该状态不等于 production migration 或 live publish。

## Create / replay / conflict

请求体只包含 source identity、exact artifact path、decision、review notes 与 bounded expiry；create 的状态码契约是：

| 结果 | HTTP | 行为 |
|---|---:|---|
| owner | `201` | 首次创建记录；`accepted` 进入 `available`，`rejected` 进入 `rejected`。 |
| replay | `200` | 同 tenant、同 key、同 fingerprint 返回原记录，`idempotent_replay=true`，不创建第二条 decision。 |
| conflict | `409 acceptance_payload_conflict` | 同 tenant/key 的 fingerprint 不同；不改原记录。 |
| already available | `409 acceptance_already_available` | 同 tenant/path 已有另一条 available acceptance；不泄露另一条记录内容。 |

若新的 decision 是 rejection，repository 会在同一事务中先把该 tenant/path 上更早的 `available` 记录改为 `revoked`，并以新 rejection ID 记录 `revoked_by_record_id`，随后写入 rejected 记录。**rejection revokes an older available record**；它不消费该记录，也不授权 publish。

## Read、expiry 与 revoke

- `GET /acceptance-records/{acceptance_id}` 成功为 `200`。unknown 与 cross-tenant ID 都返回同一个 `404 acceptance_not_found`，不得提供可枚举差异。
- expiry 以数据库时间为准。read/revoke/internal consume 前会 reconcile：只有 `available` 且 `expires_at <= DB now` 的记录变成 `expired`；client clock 不具 authority，过期不会自动续期或重新 available。
- `POST /acceptance-records/{acceptance_id}/revoke` 成功为 `200`。对已经 `revoked` 的记录 replay 仍返回同一 revoked 记录和原 `revoked_at`。
- consumed、expired、rejected 记录不可 revoke，返回 `409 acceptance_not_revocable`。

## Internal single-use consume 与 changed-file integrity

`consume_for_publish(...)` 是 internal、single-use、tenant-bound 操作，不是 HTTP endpoint。它在消费前重新打开 stored canonical path，重新计算 exact bytes 的 SHA-256 与 size：

- path、digest 或 size 与创建时记录不同，或文件已缺失，返回 `409 acceptance_artifact_integrity_mismatch`；记录保持未消费；
- 记录已经过期，返回 `409 acceptance_expired`；
- revoked、rejected、consumed 或其他非 available 状态返回 `409 acceptance_not_available`；
- repository 通过 compare-and-set 把 `available` 原子改为 `consumed`，并写入 consumer operation/resource；并发调用只能有一个 winner。

这项 integrity 检查证明的是“当前文件仍是 reviewer 接受的 exact bytes”。read `200` 只展示 stored projection，不等于文件未被改变，也不等于 publish 已获授权。

W1-23 使用 `consumed_by_operation=distribution.publish` 与
`consumed_by_resource_id=<publish_attempt_id>` 做 durable correlation。若 consume
抛出 store error，不能推断 CAS 失败；只允许一次 tenant-bound read-only outcome
inspection：

- `available_not_consumed`：本次未消费，可在修复 store 后由 operator 显式重试；
- `consumed_by_this_attempt`：本次已消费，禁止 connector 与同 acceptance retry；
- `consumed_by_another_attempt` / `not_available`：关联另一个 attempt 或停止；
- `unknown`：`acceptance_consumed=null`，禁止 retry、restore 或 connector call。

任何已消费或可能已消费的记录都 **no restore**。Backend/frontend 都 **no
automatic retry**；另一次真实 publish 需要新的 human acceptance。

## Safe error contract

错误响应只使用 stable code 或经过清洗的 validation fields，不回显 credential、raw key、请求 input、内部异常或数据库细节：

| HTTP | Code / shape | Operator action |
|---:|---|---|
| `400` | `acceptance_key_required` | create 缺少 action-stable `Idempotency-Key`；修 caller，不生成 server fallback key。 |
| `400` | `acceptance_key_invalid` | duplicate/格式/长度不合法；修 caller。 |
| `403` | `Insufficient permission` | key 缺少 `artifact:accept|all`；`provider:submit` alone 不足。 |
| `404` | `acceptance_not_found` | source/record/file 对当前 tenant 不可见；保持 cross-tenant 非枚举。 |
| `409` | `acceptance_payload_conflict` | same key 的 create fingerprint 改变；不得覆盖或自动换 key。 |
| `409` | `acceptance_source_not_terminal` | durable source 仍在执行；等待 terminal 后再 review。 |
| `409` | `acceptance_source_not_eligible` | accepted source 不是 full/non-stub/non-degraded final video，或 source projection 不合法。 |
| `409` | `acceptance_artifact_mismatch` | request path 不是 durable exact final path。 |
| `409` | `acceptance_already_available` | 该 tenant/path 已有另一条 available 记录。 |
| `409` | `acceptance_not_revocable` | 当前状态不能 revoke。 |
| `409` | `acceptance_not_available` | internal consume 时记录不再 available。 |
| `409` | `acceptance_expired` | internal consume 前 DB-time expiry 已生效。 |
| `409` | `acceptance_artifact_integrity_mismatch` | internal consume 发现 changed/missing file；禁止 publish。 |
| `422` | sanitized `type` / `loc` / `msg` | request JSON/schema 不合法；响应不得包含 input/context/url/credential。 |
| `503` | `acceptance_store_unavailable` | durable ledger 不可用；停止 create/revoke/consume，不 fallback 到 memory/filesystem。 |

Create owner 是 `201`；create replay、read、revoke 均是 `200`。不要把 read/revoke `200` 解释成 publish/delivery 成功。

## 本地验证与 16-table recovery contract

```bash
.venv/bin/python -m pytest \
  tests/test_backup_production_contract.py \
  tests/test_run_alembic_upgrade.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_openapi_types_drift_guard.py -q

cd web
npm run check:api-types
```

当前 application recovery set 精确为以下 16 个有序表，`acceptance_records` 必须紧随
`idempotency_records`，provider-cost ledger tables 追加在其后：

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

dump、restore、verify 与 hermetic schema fixture 的顺序必须完全一致。历史、带日期的
12/13/14-table evidence 保持其当时事实；当前恢复目标固定为上述 16-table contract，
不把历史数字当作当前 schema。

W1-23 没有增加第 15 张表；`publish_logs` 在同一 order 中包含 nullable `tenant_id`、
`acceptance_id` 与 `updated_at` correlation columns。W1-27--W1-30 的两张 ledger
表必须随 schema-first backup 一起恢复，不能仅恢复业务表。未来生产启用顺序必须是
provider-off → verified backup/restore → schema-first migration → read-only verification
→ provider-off binary rollout。Rollback 必须先保持 provider-off 并 block
canonical/deprecated 两条 mutation routes，再按 owner 审批回滚 safe application；
schema downgrade 不是 application rollback。

## 生产边界

本批证据仅为本地/fixture governance：`production unchanged`、
`provider_call=false`、`live_publish=false`。它不证明 production migration、
deployed reviewer/publisher permission assignment、live acceptance、publish、
delivery 或 enterprise full-chain completion。任何 production write、deploy 或
真实 publish 都需要单独授权。

## 相关实现与文档

- [API endpoint reference](../reference/api-endpoints.md)
- [Backend route auth contract](./backend-route-auth-contract.md)
- [Publish acceptance consumption](./publish-acceptance-consumption.md)
- Approved design: `docs/superpowers/specs/2026-07-12-single-use-human-acceptance-record-design.md`
- `src/routers/acceptance_records.py`
- `src/services/artifact_acceptance.py`
- `src/storage/acceptance_repository.py`
- `migrations/alembic/versions/e8f1a2b3c4d5_add_acceptance_records.py`
- `scripts/pg_dump_logical.py`
- `scripts/pg_restore_logical.py`
- `scripts/verify_restored_database.py`
