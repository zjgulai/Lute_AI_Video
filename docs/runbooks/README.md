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
| [background-task-registry-leak.md](./background-task-registry-leak.md) | 后台 task 完成、失败、取消后 registry 残留 | 5-10 min |
| [health-endpoint-no-secret.md](./health-endpoint-no-secret.md) | 公开 `/health` 泄露 provider key、DSN、token 或内部路径 | 2-5 min |
| [poyo-rejection.md](./poyo-rejection.md) | POYO 图片/视频生成内容审核拒绝 | 5-10 min |
| [pipeline-stuck.md](./pipeline-stuck.md) | Pipeline 卡在 running 状态超阈值 | 10-20 min |
| [db-pool-exhausted.md](./db-pool-exhausted.md) | asyncpg 连接池耗尽 | 5-10 min |
| [brand-assets-refresh.md](./brand-assets-refresh.md) | 品牌资产抓取刷新 / 新增产品 / 灾难恢复 | 2-5 min |
| [docker-no-token-preflight.md](./docker-no-token-preflight.md) | Docker build / compose 预检必须保持无 token、无外部 provider 调用 | 2-5 min |
| [gate-approve-idempotency.md](./gate-approve-idempotency.md) | Gate approve 重复提交、网络重试、background resume 重复启动 | 5-10 min |
| [key-rotation.md](./key-rotation.md) | API key rotation（泄露/定期/授权变更） | 30-45 min |
| [p2-recharge-smoke-checklist.md](./p2-recharge-smoke-checklist.md) | poyo.ai 充值后真实 smoke 的 dry-run 与双确认执行入口 | 5-15 min |
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
