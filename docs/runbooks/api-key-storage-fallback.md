---
title: API key storage fallback guard
doc_type: workflow
module: frontend
topic: api-key-storage
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# API key storage fallback guard

## 目的

锁定浏览器端 `X-API-Key` 的存储、清除和展示边界，避免本地测试时因 cookie 残留、隐私模式 localStorage 失败或完整 key 展示导致错误鉴权和泄露风险。

## 不变量

- `ai_video_api_key` 默认只写 localStorage。
- cookie fallback 只在 localStorage 不可用时写入，不作为常规双写副本。
- `setApiKey("")` 或空白字符串必须清除 localStorage 与 cookie fallback。
- `resetApiConfig()` 必须同时清理 API base、API key 和 demo mode。
- Settings snapshot 使用 `maskApiKeyForDisplay()`，不要记录完整 API key，不要在 UI 中展示完整 key。
- 该测试只操作浏览器测试环境的 localStorage/cookie，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或 provider。

## 验证命令

```bash
cd web
npm test -- --run src/components/apiKeyStorage.test.ts
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 修改 `getApiKey()`、`setApiKey()`、`storageGet()`、`storageSet()` 或 `storageRemove()` 前，先更新 `apiKeyStorage.test.ts`。
2. 如果调整 mask 规则，同步更新 `maskApiKeyForDisplay()` 和 Settings snapshot。
3. 清除逻辑必须覆盖 localStorage 和 cookie fallback，不能只写入空字符串。
4. 不要把 tenant API key 混入 admin cookie session；admin 请求仍走 `adminFetch()` 并删除 `X-API-Key`。

## 相关文件

- `web/src/components/api.ts`
- `web/src/components/SettingsPanel.tsx`
- `web/src/components/ApiKeyGate.tsx`
- `web/src/components/apiKeyStorage.test.ts`
- `configs/api-key-storage-fallback-contract.yaml`
