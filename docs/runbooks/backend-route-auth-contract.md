---
title: Backend Route Auth Contract
doc_type: workflow
module: backend
topic: route-auth-contract
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# Backend Route Auth Contract

## 触发场景

新增或调整 FastAPI router、endpoint、admin API、media route、metrics route 时，必须先检查路由鉴权边界，避免敏感接口漏挂鉴权依赖。

## 当前契约

契约文件：`configs/backend-route-auth-contract.yaml`

公开路由只能出现在 `public_routes`：

- `GET /health`
- `GET /metrics`
- `GET /api/media/{media_path:path}`
- `POST /api/admin/auth/login`

创作 API、资产 API、portfolio、telemetry、legacy `/api/assets/*` 必须通过 `verify_api_key` 挂载或 endpoint dependency 保护。

Admin API 使用独立 session cookie 鉴权：

- 只允许 `POST /api/admin/auth/login` 无 session，因为它创建 session。
- 其他 `/api/admin/*` endpoint 必须依赖 `verify_admin_session`。
- Admin 的 `POST` / `PUT` / `PATCH` / `DELETE` 必须额外依赖 `verify_csrf_token`，login 除外。

## 本地验证

```bash
pytest tests/test_backend_route_auth_contract.py -q
```

该测试只做静态扫描，不启动 FastAPI，不访问数据库，不请求外部 provider。

## 修改流程

1. 新增 route 前先判断是否真的需要公开。
2. 公开 route 必须加入 `configs/backend-route-auth-contract.yaml` 并写明 reason。
3. 创作 API route 优先挂在已有 `verify_api_key` router 下。
4. Admin route 只使用 `verify_admin_session`，不要混入租户 API key。
5. Admin 写操作补 `verify_csrf_token`，除非是 login。
6. 运行 `pytest tests/test_backend_route_auth_contract.py -q`。

## 禁止事项

- 不要新增未记录的公开 route。
- 不要把 `/scenario/*`、`/pipeline/*`、`/fast/*`、upload、publish、telemetry error 等敏感接口放入公开 allowlist。
- 不要用 demo API key 作为 admin auth 替代品。
