---
name: runbooks-index
description: Runbooks 索引文档，列出所有运维事故应急手册及其触发场景、相关告警与对应 SOP。当需要查找特定故障模式的处理方法、新事故复盘后归档、或新人 oncall 训练时使用。
---

# Runbooks Index

事故应急手册。每个 runbook 对应一类已观察过 ≥ 1 次的故障模式。新的故障模式不应该走「即兴排查」，必须先看这里有没有。

## 编写约定

每个 runbook 必须包含：

1. **触发场景**（用什么信号判断这是这类故障）
2. **影响范围**（哪些用户/接口/资源受影响）
3. **预期 MTTR**（处理这类故障应该多快）
4. **相关代码**（file:// 链接，方便快速定位）
5. **立即诊断**（前 2-5 分钟做什么命令）
6. **分类响应**（不同子场景的具体步骤）
7. **永久 fix**（怎么让这类故障不再发生）

## 现有 Runbooks

| 文件 | 故障模式 | 预期 MTTR |
|---|---|---|
| [admin-csrf-contract.md](./admin-csrf-contract.md) | Admin 写操作 CSRF、cookie path、前端 `adminFetch` 契约漂移 | 2-5 min |
| [deepseek-timeout.md](./deepseek-timeout.md) | DeepSeek LLM API 超时 / 不可用 / 限速 | 5-15 min |
| [api-rate-limit-contract.md](./api-rate-limit-contract.md) | FastAPI fallback rate-limit、skip path、429 响应契约漂移 | 2-5 min |
| [api-response-metadata-contract.md](./api-response-metadata-contract.md) | JSON API `_meta` / `X-Trace-Id` / 错误响应契约漂移 | 2-5 min |
| [backend-route-auth-contract.md](./backend-route-auth-contract.md) | FastAPI 路由鉴权边界、公开 route allowlist、admin session/CSRF 契约 | 2-5 min |
| [artifact-acceptance-lifecycle.md](./artifact-acceptance-lifecycle.md) | Human acceptance create/replay/read/revoke、expiry、integrity 与 internal single-use consume 边界 | 2-30 min |
| [publish-acceptance-consumption.md](./publish-acceptance-consumption.md) | Acceptance-bound publish、uncertain consume、no-retry/no-restore 与 route-block-first rollback | 2-30 min |
| [publish-connector-truth.md](./publish-connector-truth.md) | W1-24 historical connector truth baseline（当前入口见 W1-25 receipt runbook） | 2-30 min |
| [publish-receipt-protocol-calibration.md](./publish-receipt-protocol-calibration.md) | TikTok/Shopify current protocol、durable receipt、preflight、readback 与 no-retry recovery | 2-30 min |
| [transparency-delivery.md](./transparency-delivery.md) | Fast/S1-S5 透明度只读 projection、evidence package、UI 标签与服务端 publish disclosure | 2-15 min |
| [provider-cost-ledger-per-job-budget.md](./provider-cost-ledger-per-job-budget.md) | W1-27–W1-30 provider exact usage、durable reservation/settlement、finite operation scope、schema-first recovery 与 local-only budget rollback | 5-30 min |
| [background-task-registry-leak.md](./background-task-registry-leak.md) | 后台 task 完成、失败、取消后 registry 残留 | 5-10 min |
| [health-endpoint-no-secret.md](./health-endpoint-no-secret.md) | 公开 `/health` 泄露 provider key、DSN、token 或内部路径 | 2-5 min |
| [media-url-sanitizer.md](./media-url-sanitizer.md) | 前后端媒体 URL builder / signer 接受危险 scheme、开放 URL 或 traversal 输入 | 2-5 min |
| [c2pa-dry-run-checklist.md](./c2pa-dry-run-checklist.md) | C2PA local draft、required fail-closed 与本地 Reader 回读边界 | 5-15 min |
| [c2pa-cert-application.md](./c2pa-cert-application.md) | 可选 production C2PA credential 调研、申请与钥匙托管前置清单 | 30-60 min |
| [poyo-rejection.md](./poyo-rejection.md) | POYO 图片/视频生成内容审核拒绝 | 5-10 min |
| [pipeline-stuck.md](./pipeline-stuck.md) | Pipeline 卡在 running 状态超阈值 | 10-20 min |
| [monitoring-ownership.md](./monitoring-ownership.md) | Prometheus 指标/规则、Alertmanager receiver、Grafana provisioning 与 `/metrics` 边界漂移 | 10-30 min |
| [postgresql-readiness-bootstrap.md](./postgresql-readiness-bootstrap.md) | PostgreSQL readiness、空库 bootstrap 与历史库 migration 分流 | 5-30 min |
| [submission-idempotency-recovery.md](./submission-idempotency-recovery.md) | Fast/S1-S5 async submit timeout、ambiguous readback、`recovery_required` 与迁移后恢复基线 | 2-30 min |
| [regenerate-downstream-invalidation.md](./regenerate-downstream-invalidation.md) | Step regenerate 后下游 step 和 gate candidate / approval 失效规则漂移 | 5-10 min |
| [s4-footage-filtering.md](./s4-footage-filtering.md) | S4 Live Shoot 成品与中间素材在 /works / /library 的筛选分层漂移 | 2-5 min |
| [db-pool-exhausted.md](./db-pool-exhausted.md) | asyncpg 连接池耗尽 | 5-10 min |

## Configs ↔ Runbooks 关系

部分 runbook 存在对应的机器可验证契约文件（`configs/*.yaml` / `configs/*.json`），用于 CI 静态断言。两者的关系如下：

| Contract | Runbook | 关系 |
|---|---|---|
| `configs/admin-csrf-contract.yaml` | [admin-csrf-contract.md](./admin-csrf-contract.md) | 契约定义机器断言的字段/行为；runbook 描述诊断与修复流程 |
| `configs/api-rate-limit-contract.yaml` | [api-rate-limit-contract.md](./api-rate-limit-contract.md) | 同上 |
| `configs/api-response-metadata-contract.yaml` | [api-response-metadata-contract.md](./api-response-metadata-contract.md) | 同上 |
| `configs/backend-route-auth-contract.yaml` | [backend-route-auth-contract.md](./backend-route-auth-contract.md) | 同上 |
| `configs/health-endpoint-no-secret-contract.yaml` | [health-endpoint-no-secret.md](./health-endpoint-no-secret.md) | 同上 |
| `configs/media-url-sanitizer-contract.yaml` | [media-url-sanitizer.md](./media-url-sanitizer.md) | 同上 |
| `configs/prometheus-metrics-contract.yaml` | [monitoring-ownership.md](./monitoring-ownership.md) | 指标 schema、低基数 label、rule/dashboard 查询与内部 monitoring ownership 契约 |
| `configs/gate-approve-idempotency-contract.yaml` | [gate-approve-idempotency.md](./gate-approve-idempotency.md) | 同上 |
| `configs/scenario-state-persistence-contract.yaml` | [scenario-state-persistence-schema.md](./scenario-state-persistence-schema.md) | 同上 |
| `configs/regenerate-downstream-invalidation-contract.yaml` | [regenerate-downstream-invalidation.md](./regenerate-downstream-invalidation.md) | 同上 |
| `configs/s4-footage-filtering-contract.yaml` | [s4-footage-filtering.md](./s4-footage-filtering.md) | 同上 |
| … | … | 其余 24 对遵循相同模式 |

**规则**: 修改契约时必须同步更新对应的 runbook；新增 runbook 时如有 CI 可验证行为，应同时添加契约文件。

*Last synced: 2026-07-22 — configs/ (41 files) ↔ docs/runbooks/ (57 files); Batch E2 monitoring changes are local-only evidence pending independent review.*
| [brand-assets-refresh.md](./brand-assets-refresh.md) | 品牌资产抓取刷新 / 新增产品 / 灾难恢复 | 2-5 min |
| [docker-no-token-preflight.md](./docker-no-token-preflight.md) | Docker build / compose 预检必须保持无 token、无外部 provider 调用 | 2-5 min |
| [gate-approve-idempotency.md](./gate-approve-idempotency.md) | Gate approve 重复提交、网络重试、background resume 重复启动 | 5-10 min |
| [key-rotation.md](./key-rotation.md) | API key rotation（泄露/定期/授权变更） | 30-45 min |
| [p2-recharge-smoke-checklist.md](./p2-recharge-smoke-checklist.md) | poyo.ai 充值后真实 smoke 的 dry-run 与双确认执行入口 | 5-15 min |
| [production-post-deploy-regression-checklist.md](./production-post-deploy-regression-checklist.md) | Lighthouse 部署后回归复盘清单（页面/API/容器/日志） | 10-20 min |
| [scenario-state-persistence-schema.md](./scenario-state-persistence-schema.md) | S1-S5 state JSON 初始化、filesystem fallback、PG projection 字段契约漂移 | 5-10 min |
| [thumbnail-missing.md](./thumbnail-missing.md) | /works 或 /library 视频卡片黑底无缩略图 | 5-15 min |

## 灾难恢复

灾难级别故障（数据丢失、长时间不可恢复）走单独的：

- [disaster_recovery_runbook.md](../disaster_recovery_runbook.md) — 数据备份/恢复/RPO/RTO

## 写新 Runbook 的时机

只在以下情况写新 runbook：

1. 故障已发生 ≥ 1 次（不要写 "也许会发生" 的）
2. 处理流程超过 3 步（一步搞定的不需要 runbook）
3. 跨多个组件（单组件可以放该组件的代码注释里）

**经验法则**：oncall 半夜被叫醒时，能照着这份 runbook 一步步操作的，才算合格。

## 维护

- 每个事故复盘后必须 review 对应 runbook，更新 / 新建
- 每季度做一次 "tabletop drill"：抽 1 个 runbook 让另一个工程师按步骤跑，看是否能完整恢复

## 相关文档

- [ADR 索引](../architecture/adr/README.md) — 架构决策
- [部署指南](../../deploy/local-run.md) — 日常部署
