---
title: Admin Logs keyboard navigation guard
doc_type: workflow
module: frontend
topic: admin-logs-keyboard-navigation
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Admin Logs keyboard navigation guard

## 目的

锁定 `/admin/logs` 表格行和详情弹层的键盘可达性，避免后续改版后只保留鼠标点击路径，导致键盘用户无法打开日志详情或关闭后丢失焦点。

## 不变量

- 日志行必须保留 `tabIndex={0}`，并暴露 `role="button"` 和可读 `aria-label`。
- `Enter` 和 `Space` 必须打开对应日志详情。
- 详情弹层必须保留 `role="dialog"`、`aria-modal="true"`、`aria-labelledby="admin-log-detail-title"` 和 `aria-describedby="admin-log-detail-description"`。
- 详情弹层打开后初始焦点必须落到关闭按钮。
- 关闭按钮必须是显式 `type="button"`，并保留 `aria-label="Close log detail"`。
- `Escape` 关闭详情弹层后，焦点必须恢复到触发打开的日志行。
- 该检查只使用 mocked `adminFetchJson`，不触发生成接口、不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或 provider。

## 验证命令

```bash
cd web
npm test -- --run src/app/admin/logs/page.test.tsx
npx tsc --noEmit -p tsconfig.json
```

## 修改流程

1. 修改 `/admin/logs` 表格或详情弹层前，先更新 `web/src/app/admin/logs/page.test.tsx`。
2. 如果日志行交互从 `<tr>` 改为独立按钮，同步更新 `configs/admin-logs-keyboard-navigation-contract.yaml`。
3. 如果替换弹层行为，必须继续复用或等价实现 `useModalBehavior` 的 Escape 关闭、初始焦点和焦点恢复能力。
4. 保持该测试为 hermetic：只 mock `adminFetchJson`，不接入真实 admin backend。

## 相关文件

- `web/src/app/admin/logs/page.tsx`
- `web/src/app/admin/logs/page.test.tsx`
- `web/src/hooks/useModalBehavior.ts`
- `configs/admin-logs-keyboard-navigation-contract.yaml`
