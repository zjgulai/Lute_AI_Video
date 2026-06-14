---
title: Settings API key accessibility guard
doc_type: workflow
module: frontend
topic: settings-api-key-accessibility
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Settings API key accessibility guard

## 目的

锁定 Settings 面板中 API key 输入、连接测试状态和保存动作的可访问性契约，避免后续 UI 改版后出现无 label、无 hint、状态不可公告或按钮语义漂移。

## 不变量

- API key 输入框必须有稳定 `id="settings-api-key"`。
- API key label 必须通过 `htmlFor="settings-api-key"` 绑定输入框。
- API key hint 必须有 `id="settings-api-key-hint"`，输入框通过 `aria-describedby` 关联该 hint。
- 连接测试成功必须使用 `role="status"` 和 `aria-live="polite"`。
- 连接测试失败必须使用 `role="alert"` 和 `aria-live="assertive"`。
- Save / Test / Reset / Close 都必须是显式 `type="button"`，避免未来被包进表单后产生隐式 submit。
- Settings dialog 必须保留 `role="dialog"`、`aria-modal="true"`、`aria-labelledby` 和 `aria-describedby`。
- 该检查只运行 jsdom UI 测试，不触发生成接口、不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或 provider。

## 验证命令

```bash
cd web
npm test -- --run src/components/SettingsPanel.test.tsx
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 修改 Settings API key 输入区前，先更新 `SettingsPanel.test.tsx`。
2. 如果更换 id 或提示文案，同步更新 `configs/settings-api-key-accessibility-contract.yaml`。
3. 如果调整连接测试 UI，必须保留成功/失败的 live region 语义。
4. 不要在 Settings snapshot 中展示完整 API key；展示逻辑继续走 `maskApiKeyForDisplay()`。

## 相关文件

- `web/src/components/SettingsPanel.tsx`
- `web/src/components/SettingsPanel.test.tsx`
- `web/src/components/api.ts`
- `configs/settings-api-key-accessibility-contract.yaml`
