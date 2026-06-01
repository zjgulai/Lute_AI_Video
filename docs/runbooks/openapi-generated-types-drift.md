---
title: OpenAPI generated types drift guard
doc_type: workflow
module: api
topic: openapi-generated-types
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# OpenAPI generated types drift guard

## 目的

保证 `web/src/types/api.generated.ts` 与本地 FastAPI OpenAPI schema 一致，避免后端路由、Pydantic model 或 response schema 改动后前端类型静默漂移。

## 不变量

- 默认检查只比较，不改写 `api.generated.ts`。
- 只有显式 `--write` 或 `npm run typegen:api` 才会更新生成文件。
- schema 来源是本地 `src.api.app.openapi()`，不访问生产、不访问 `localhost:8001/openapi.json`。
- 生成器必须是 `web/package.json` 和 `web/package-lock.json` 锁定的 `openapi-typescript@7.13.0`。
- 该流程不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或任何 provider。

## 常用命令

从项目根目录检查漂移：

```bash
.venv/bin/python scripts/check_openapi_types_drift.py
```

从 `web/` 目录检查漂移：

```bash
npm run check:api-types
```

后端 schema 确实变更后，重新生成前端类型：

```bash
npm run typegen:api
```

等价根目录命令：

```bash
.venv/bin/python scripts/check_openapi_types_drift.py --write
```

## 失败处理

如果检查失败并提示 `api.generated.ts is stale`：

1. 确认本次后端路由或 schema 变更是预期的。
2. 运行 `cd web && npm run typegen:api`。
3. Review `web/src/types/api.generated.ts` 的 diff，确认没有意外删除 legacy `/api/assets/*` 兼容面。
4. 运行 `python scripts/check_openapi_types_drift.py` 复验。

如果失败提示找不到 `openapi-typescript`：

```bash
cd web
npm install
```

## 相关文件

- `scripts/check_openapi_types_drift.py`
- `web/src/types/api.generated.ts`
- `web/package.json`
- `configs/openapi-generated-types-drift-contract.yaml`
- `tests/test_openapi_types_drift_guard.py`
