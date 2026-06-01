---
title: Frontend store persistence migration guard
doc_type: runbook
module: frontend
topic: zustand-persistence
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Frontend store persistence migration guard

## 目的

锁定 Zustand store 的 localStorage 持久化边界，避免旧浏览器缓存、坏 JSON、非法枚举或运行时 UI 状态污染当前 S1-S5 工作流。

## 不变量

- `ai-video-app-store` 只持久化 `mode`、`pipelineMode`、`videoDuration`。
- `ai-video-pipeline-store` 只持久化 `activePipeline`、`dismissedPipelineLabels`。
- `APP_STORE_PERSIST_VERSION` 和 `PIPELINE_STORE_PERSIST_VERSION` 变更时必须同步更新 migration。
- 坏 JSON 必须被 `createSafeJSONStorage` 清理，不允许 hydration 抛错导致页面不可用。
- 非法 payload 必须回到安全默认值，不持久化 `loading`、`showSettings`、`workflowState`、`reviewState` 等运行时状态。
- 该检查只读或写 localStorage 测试夹具，不触发生成接口、不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或 provider。

## 验证命令

```bash
cd web
npm test -- --run src/stores/persistence.test.ts
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 新增或删除持久化字段前，先更新 `web/src/stores/persistence.ts` 的类型、partialize 和 migrate。
2. 增加版本号，保留旧版本 payload 的迁移测试。
3. 运行 focused test，确认坏 JSON、非法枚举和超长 dismissed label 队列仍能恢复。
4. Review localStorage key 是否仍为 `ai-video-app-store` / `ai-video-pipeline-store`，避免无意丢失用户偏好。

## 相关文件

- `web/src/stores/persistence.ts`
- `web/src/stores/useAppStore.ts`
- `web/src/stores/usePipelineStore.ts`
- `web/src/stores/persistence.test.ts`
- `configs/frontend-store-persistence-migration-contract.yaml`
