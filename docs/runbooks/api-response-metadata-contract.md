---
title: API Response Metadata Contract
doc_type: workflow
module: backend
topic: response-metadata-contract
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# API Response Metadata Contract

## 触发场景

新增或调整 FastAPI middleware、错误处理、rate limit、API key 鉴权、前端 `ApiError` 解析、链路追踪字段时，先检查本契约。

## 影响范围

影响所有 JSON API 的前端错误提示、toast、日志追踪和生产排障。`/health` 是唯一明确跳过 `_meta` 注入的 JSON endpoint，但仍必须返回 `X-Trace-Id`。

## 预期 MTTR

2-5 min。契约漂移通常能通过单测定位到 middleware、错误响应或文档 scope。

## 当前契约

机器可读契约：`configs/api-response-metadata-contract.yaml`

所有非 `/health` JSON 响应必须包含：

- `_meta.trace_id`
- `_meta.duration_ms`
- `_meta.version`
- `_meta.timestamp`

Trace header 规则：

- 请求带 `X-Client-Trace-Id` 时，响应 `X-Trace-Id` 必须回显同一个值。
- 请求不带 `X-Client-Trace-Id` 时，后端生成 server trace id，并同时写入 `X-Trace-Id` 与 `_meta.trace_id`。

错误响应规则：

- 普通 `HTTPException` JSON 响应保留 `detail`，并注入 `_meta`。
- 429 rate-limit JSON 响应保留 `detail`、`retry_after_sec`，并注入 `_meta`。
- 非 JSON 响应不注入 `_meta`，但仍保留 `X-Trace-Id`。

## 相关代码

- [`src/api.py`](../../src/api.py) — `response_wrapper_middleware`、rate limit middleware。
- [`src/routers/_deps.py`](../../src/routers/_deps.py) — API key 鉴权错误来源。
- [`tests/test_api_response_metadata_contract.py`](../../tests/test_api_response_metadata_contract.py) — 本契约的行为和静态守卫。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_api_response_metadata_contract.py -q
```

本测试只访问本地 ASGI app，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

如需手动确认本地运行实例：

```bash
curl -i -H 'X-Client-Trace-Id: local-health-001' http://localhost:8001/health
curl -i -H 'X-Client-Trace-Id: local-error-001' http://localhost:8001/api/files
```

第二条命令预期返回 401，并且 JSON body 同时包含 `detail` 和 `_meta`。

## 分类响应

- `_meta` 缺失：先检查 `src/api.py` 的 `response_wrapper_middleware` 是否仍在所有 JSON response 之后执行，且没有新增绕过 `body_iterator` 的 response 类型。
- `X-Trace-Id` 缺失：检查 wrapper 是否在 `/health` 或非 JSON 分支前已经写 header。
- 401/422 错误丢 `detail`：检查 `HTTPException` 是否被自定义 handler 转换为非 dict 或非 JSON response。
- 429 错误丢 `retry_after_sec`：检查 rate limit middleware 的 JSON body，不能只返回字符串或覆盖结构化字段。
- 前端无法显示结构化错误：同时运行 `web/src/lib/apiFetchErrorNormalization.test.ts`，确认前端没有把 `_meta` 或 retry 信息压扁成普通 `Error.message`。

## 永久 fix

1. 保持 `configs/api-response-metadata-contract.yaml` 为响应元信息 SSOT。
2. 修改 middleware 或错误处理时同步更新 `tests/test_api_response_metadata_contract.py`。
3. 新增公开或受保护 JSON endpoint 后，至少用一个本地 ASGI 测试覆盖成功响应或错误响应。
4. 不要让 `/api/fast/*`、`/scenario/*`、gate candidate 或上传发布接口成为本契约 smoke 的默认探针。
5. 不要在错误响应中删除 `detail`，前端仍依赖它做用户可读错误提示。
