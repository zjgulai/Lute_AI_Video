---
title: API Rate Limit Contract
doc_type: workflow
module: backend
topic: rate-limit-contract
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# API Rate Limit Contract

## 触发场景

新增或调整 FastAPI middleware、nginx limit、`/health`、`/api/media/`、上传/发布/生成 API、429 错误呈现时，先检查本契约。

## 影响范围

影响直接访问 backend 的本地开发、内部探针、绕过 nginx 的 fallback 场景，以及前端对 429 retry 信息的展示。生产主限流仍以 nginx 为主，FastAPI 内存限流只作为 fallback。

## 预期 MTTR

2-5 min。大多数漂移能由 `tests/test_api_rate_limit_contract.py` 定位到配置、跳过路径或 429 响应结构。

## 当前契约

机器可读契约：`configs/api-rate-limit-contract.yaml`

FastAPI fallback middleware 规则：

- 每 IP `60s` 窗口最多 `120` 次请求。
- 最多保留 `1000` 个 IP 的窗口状态，超出后按 LRU 淘汰。
- 优先从 `X-Forwarded-For` 取第一个 IP；没有该 header 时使用 `request.client.host`。
- `/health` 跳过限流。
- `/api/media/` 跳过限流，避免作品集和素材库高并发静态媒体加载误伤。

429 响应规则：

- HTTP status 必须是 `429`。
- JSON body 必须保留 `detail: "Too many requests. Please slow down."`。
- JSON body 必须保留 `retry_after_sec: 60`。
- 通用 response wrapper 必须继续注入 `_meta`，并回显 `X-Trace-Id`。

## 相关代码

- [`src/api.py`](../../src/api.py) — `rate_limit_middleware` 和 `response_wrapper_middleware`。
- [`configs/api-response-metadata-contract.yaml`](../../configs/api-response-metadata-contract.yaml) — 429 `_meta` 和 trace header 结构契约。
- [`tests/test_api_rate_limit_contract.py`](../../tests/test_api_rate_limit_contract.py) — 本契约的行为和静态守卫。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_api_rate_limit_contract.py -q
```

该测试只请求本地 ASGI app 的 `/api/files` 负向鉴权路径来触发 429，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 分类响应

- 429 不出现：检查 `_rate_max_requests` 是否被改大、是否新增了过宽的 skip path、是否把业务 route 错误放进 allowlist。
- 429 body 缺 `retry_after_sec`：检查 `src/api.py` 中 rate-limit JSONResponse 的 content，不要改成纯字符串错误。
- 429 缺 `_meta`：检查 middleware 顺序，`response_wrapper_middleware` 必须能包住 rate-limit 返回。
- `/health` 被限流：确认 `request.url.path == "/health"` 仍在 skip 条件中。
- `/api/media/` 被限流：确认 `request.url.path.startswith("/api/media/")` 仍在 skip 条件中，并检查 nginx 是否有同等豁免。

## 永久 fix

1. 保持 `configs/api-rate-limit-contract.yaml` 为 FastAPI fallback 限流 SSOT。
2. 修改 `_rate_window_sec`、`_rate_max_requests`、`_rate_max_ips` 或 skip 规则时，同步更新契约和测试。
3. 不要把 `/api/fast/*`、`/scenario/*`、`/pipeline/*`、upload、publish 加入 skip。
4. 不要用真实生成接口做 rate-limit smoke；使用 401 负向路径或静态测试即可。
5. 生产 nginx 限流调整必须同时检查 Lighthouse nginx 文档和 `/api/media/` 豁免。
