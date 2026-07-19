---
title: Frontend store persistence migration guard
doc_type: workflow
module: frontend
topic: zustand-persistence
status: stable
created: 2026-06-01
updated: 2026-07-12
owner: self
source: human+ai
---

# Frontend store persistence migration guard

## 目的

锁定 Zustand store 的 localStorage 持久化边界，避免旧浏览器缓存、坏 JSON、非法枚举或运行时 UI 状态污染当前 S1-S5 工作流。

## 不变量

- `ai-video-app-store` 只持久化 `mode`、`pipelineMode`、`videoDuration`。
- `ai-video-pipeline-store` v2 只持久化 `activePipeline`、`dismissedPipelineLabels`、`pendingSubmission`。
- `pendingSubmission` 是 async submit 歧义恢复的最小 allowlist：
  `kind`、可选 `scenario`、`idempotencyKey`、`createdAt`、`phase`、可选
  `resourceId`。不得增加 request body、payload、prompt、model 参数或结果快照。
- `idempotencyKey` 是唯一允许在浏览器 pending record 中持久化的 raw action key；
  它不是 tenant authority。服务端每次 readback 都必须重新使用当前认证上下文绑定 tenant。
- 禁止持久化 `X-API-Key`、Authorization、`api_keys`、provider token/key、
  password/private key、cookie/session、DSN 或其他 authentication/credential 字段。
- `APP_STORE_PERSIST_VERSION` 和 `PIPELINE_STORE_PERSIST_VERSION` 变更时必须同步更新 migration。
- 坏 JSON 必须被 `createSafeJSONStorage` 清理，不允许 hydration 抛错导致页面不可用。
- 非法 payload 必须回到安全默认值，不持久化 `loading`、`showSettings`、`workflowState`、`reviewState` 等运行时状态。
- v1 或未知旧 payload 迁移到 v2 时，缺失/非法的 `pendingSubmission` 必须变为
  `null`；未知字段必须被 allowlist 丢弃，不能因为“恢复方便”复制到 v2。
- `submitting` / `recovering` / `bound` / `unknown` 是允许的 pending phase；
  `bound` 必须有 `resourceId`。`unknown` 在 reload 后保留并只做 same-key GET
  readback，不能触发自动 mutation POST。
- 当浏览器 API key/account 改变时保留 pending record，提示恢复原 tenant；不能因
  readback `404` 自动删除 pending 或创建新 idempotency key。
- 该检查只读或写 localStorage 测试夹具，不触发生成接口、不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或 provider。

## 验证命令

```bash
cd web
npm test -- --run src/stores/persistence.test.ts
npm test -- --run src/lib/idempotentSubmission.test.ts
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 新增或删除持久化字段前，先更新 `web/src/stores/persistence.ts` 的类型、partialize 和 migrate。
2. 增加版本号，保留旧版本 payload 的迁移测试；pipeline v2 的
   `pendingSubmission` 仍必须使用逐字段 allowlist，不得 spread 原对象。
3. 增加恶意/陈旧 payload fixture，至少包含 `user_prompt`、`api_keys`、
   `authentication`、provider credential 和未知 runtime 字段，并断言序列化结果中不存在这些字段。
4. 运行 focused test，确认坏 JSON、非法枚举、非法 idempotency key、缺失
   `resourceId` 的 `bound` phase 和超长 dismissed label 队列都安全恢复。
5. 验证 browser recovery 在 POST 前先同步 persist，timeout/reload 后只使用原 key
   执行 `GET /submissions/idempotency`，不会发第二次 mutation。
6. Review localStorage key 是否仍为 `ai-video-app-store` / `ai-video-pipeline-store`，避免无意丢失用户偏好。

## v2 最小 pending 示例

允许：

```json
{
  "kind": "scenario",
  "scenario": "s1",
  "idempotencyKey": "00000000-0000-4000-8000-000000000000",
  "createdAt": 1783830000000,
  "phase": "recovering"
}
```

禁止：

```json
{
  "payload": {"user_prompt": "..."},
  "api_keys": {"provider": "..."},
  "authentication": {"X-API-Key": "..."}
}
```

示例中的值只用于说明 schema，不是可用 credential。raw idempotency key 也不得复制到
日志、错误上报、analytics、URL 或服务端持久化。

## 相关文件

- `web/src/stores/persistence.ts`
- `web/src/stores/useAppStore.ts`
- `web/src/stores/usePipelineStore.ts`
- `web/src/stores/persistence.test.ts`
- `web/src/lib/idempotentSubmission.ts`
- `web/src/lib/idempotentSubmission.test.ts`
- `configs/frontend-store-persistence-migration-contract.yaml`
- `docs/runbooks/submission-idempotency-recovery.md`
