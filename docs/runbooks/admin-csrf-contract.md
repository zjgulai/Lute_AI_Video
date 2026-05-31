---
title: Admin CSRF Contract
doc_type: workflow
module: admin
topic: csrf-contract
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# Admin CSRF Contract

## 触发场景

新增或调整 `/api/admin/*` 写操作、admin login/logout、`adminFetch`、admin cookie 属性、admin 前端 mutating 调用时，先检查本契约。

## 影响范围

Admin API 使用 session cookie，不使用租户 `X-API-Key`。所有 admin 写操作必须有两层保护：`verify_admin_session` 和 `verify_csrf_token`。登录是唯一例外，因为它还没有 session，并负责创建 `admin_session` 与 `admin_csrf` cookie。

## 预期 MTTR

2-5 min。大多数漂移能通过静态契约测试定位到 route dependency、cookie path 或前端 helper。

## 当前契约

机器可读契约：`configs/admin-csrf-contract.yaml`

后端规则：

- `POST /api/admin/auth/login` 免 CSRF，因为它创建 session。
- 其他 `/api/admin/*` 的 `POST` / `PUT` / `PATCH` / `DELETE` 必须依赖 `verify_admin_session` 和 `verify_csrf_token`。
- `GET` / `HEAD` / `OPTIONS` 只需 session，不做 CSRF 校验。
- `admin_session` cookie 保持 `HttpOnly` 且 `path=/api/admin`。
- `admin_csrf` cookie 必须 `HttpOnly=false` 且 `path=/`，这样 `/admin/*` 页面能读取它并给 `/api/admin/*` 请求附加 `X-CSRF-Token`。

前端规则：

- admin mutating calls must use `adminFetch` or `adminFetchJson`。
- `adminFetch` 必须 `credentials=include`。
- `adminFetch` 必须删除 `X-API-Key`，admin session 与租户 API key 不允许混用。
- `adminFetch` 对 `POST` / `PUT` / `PATCH` / `DELETE` 从 `admin_csrf` cookie 读取 token，并设置 `X-CSRF-Token` header。
- `adminFetch` 对 `GET` / `HEAD` / `OPTIONS` 不附加 `X-CSRF-Token`。

## 相关代码

- [`src/routers/_admin_deps.py`](../../src/routers/_admin_deps.py) — `verify_admin_session`、`verify_csrf_token`、CSRF 常量。
- [`src/routers/admin/auth.py`](../../src/routers/admin/auth.py) — login/logout cookie 创建和删除。
- [`web/src/components/api.ts`](../../web/src/components/api.ts) — `adminFetch` / `adminFetchJson`。
- [`tests/test_admin_csrf.py`](../../tests/test_admin_csrf.py) — CSRF dependency 行为测试。
- [`tests/test_admin_csrf_contract.py`](../../tests/test_admin_csrf_contract.py) — 跨后端/前端静态契约。
- [`web/src/components/adminCsrfContract.test.ts`](../../web/src/components/adminCsrfContract.test.ts) — `adminFetch` header 行为测试。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_admin_csrf.py tests/test_admin_csrf_contract.py tests/test_backend_route_auth_contract.py -q
cd web && npm test -- --run src/components/adminCsrfContract.test.ts
```

这些测试只检查本地代码和 mocked fetch，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 分类响应

- Admin 写操作缺 CSRF：检查该 endpoint 是否在函数参数中声明 `_csrf: None = Depends(verify_csrf_token)`。
- 前端 POST/PUT/PATCH/DELETE 缺 `X-CSRF-Token`：检查是否绕过了 `adminFetch`，或 `admin_csrf` cookie 是否仍是 `path=/`。
- 登录后写操作 403 `Missing CSRF cookie`：优先检查浏览器是否能在 `/admin/*` 页面读到 `admin_csrf`；不要把 cookie path 改回 `/api/admin`。
- Admin 请求误带 `X-API-Key`：检查调用方是否使用了普通 `apiFetch` 或手写 `fetch`。

## 永久 fix

1. 新增 admin 写操作时先更新或确认 `configs/admin-csrf-contract.yaml`。
2. 后端写操作必须同时依赖 session 和 CSRF，login 以外不得豁免。
3. 前端 admin mutating calls 只能走 `adminFetch` / `adminFetchJson`。
4. 不要把 `admin_csrf` 设为 `HttpOnly`；前端必须能读取它来实现 double-submit。
5. 不要把 `admin_session` 放宽到 `path=/`；session cookie 继续限制在 `/api/admin`。
