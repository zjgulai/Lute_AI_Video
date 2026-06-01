---
title: AssetPicker request boundary guard
doc_type: workflow
module: frontend
topic: asset-picker-request-boundary
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# AssetPicker request boundary guard

## 目的

锁定 `AssetPickerModal` 的请求边界：素材选择器只能列出现有 portfolio 媒体并返回已存在的 media URL，不负责上传、生成、gate candidate、pipeline 启动或 regenerate。

## 不变量

- 打开 picker 时只允许调用 `/portfolio/?limit=200&sort=recent`。
- picker 内禁止调用 `/api/upload`、`/api/assets/upload`、`/api/files/upload`。
- picker 内禁止调用 `/fast/generate`、`/fast/submit`、`/scenario/*`、`/pipeline/*`、`/gate/*`。
- 点击 Confirm 只把已选 portfolio path 通过 `getMediaUrl()` 映射后交给 `onPick()`。
- i18n hydration 不得造成重复 portfolio listing 请求。
- 该检查只使用 mocked `apiFetch`，不触发生成接口、不访问真实后端、不消耗 poyo.ai tokens。

## 验证命令

```bash
cd web
npm test -- --run src/components/AssetPickerModal.test.tsx
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 修改 `AssetPickerModal` 请求逻辑前，先更新 `web/src/components/AssetPickerModal.test.tsx`。
2. 如果 picker 需要支持新的只读列表接口，同步更新 `configs/asset-picker-request-boundary-contract.yaml`。
3. 上传仍归 `AssetUploader` / `GuidedCard` 文件上传分支，不得塞进 picker。
4. 生成、regenerate、gate candidate 仍归对应 pipeline/gate 组件，不得从 picker 发起。

## 相关文件

- `web/src/components/AssetPickerModal.tsx`
- `web/src/components/AssetPickerModal.test.tsx`
- `web/src/components/GuidedCard.tsx`
- `configs/asset-picker-request-boundary-contract.yaml`
