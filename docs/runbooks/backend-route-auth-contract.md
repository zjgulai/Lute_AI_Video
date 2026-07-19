---
title: Backend Route Auth Contract
doc_type: workflow
module: backend
topic: route-auth-contract
status: stable
created: 2026-05-31
updated: 2026-07-13
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

`media.router` 是 mixed router：`GET /api/media/{media_path:path}` 只允许
`brand_assets` 与 `demo` 两个显式 public root 匿名读取；其他 protected path
必须携带绑定 canonical path、tenant、purpose 与 expiry 的 tenant-bound token。
`GET /api/media/sign` 通过 `verify_api_key` 取得 `AuthContext`，只使用认证上下文
中的 tenant，不接受 client 自报 tenant。

创作 API、资产 API、portfolio、telemetry、legacy `/api/assets/*` 必须通过 `verify_api_key` 挂载或 endpoint dependency 保护。

`submissions.router` 也必须通过 mount-level `verify_api_key` dependency 保护。其
`GET /submissions/idempotency` 是 tenant-bound readback：tenant 只来自
`AuthContext`，unknown 与 cross-tenant key 都返回相同 `404`，并且该 GET 不执行
第二次 `provider:submit` authorization 或 generation mutation。它不得被加入
`public_routes`，也不得因“恢复页面需要”改成匿名 readback。

`acceptance_records.router` 必须通过 mount-level `verify_api_key`，并在 endpoint
层要求 `artifact:accept` 或 `all`；只有 `provider:submit` 的 key 必须返回 `403`。
当前 HTTP surface 精确限定为 `POST /acceptance-records`（create）、
`GET /acceptance-records/{acceptance_id}`（read）与
`POST /acceptance-records/{acceptance_id}/revoke`（revoke）。不得公开 consume
endpoint；single-use consume 只保留为 internal service boundary。Distribution
接入已达到 `W1-23 completed_local`：`POST /distribution/publish` 与 deprecated
`POST /publish/{video_id}` 继续受 mount-level `verify_api_key` 保护，并在 endpoint
层要求 `artifact:publish` 或 `all`。`artifact:accept` alone 和
`provider:submit` alone 都不足。两条 route 只接受相同的 strict
`acceptance_id` + single-platform + metadata body；client artifact path、body
human assertion 与 legacy `video_id` 都不是 authority。不存在 public consume
endpoint。

`completed_local` 只说明本地 contract/service/route 证据闭合，不是 live publish
或 production acceptance。当前边界保持 `production unchanged`、
`provider_call=false`、`live_publish=false`。

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
4. 新增 tenant-bound readback router 时仍使用 mount-level `verify_api_key`，并在
   `api_key_router_mounts` 中登记；read-only 不等于 public。
5. Acceptance create/read/revoke 同步核对 `acceptance_record_routes`，保持
   `artifact:accept|all`，并确认 `provider:submit` alone 不足。
6. Publish adapter 同步核对 `publish_acceptance_routes`，保持
   `artifact:publish|all`、single-platform、无 client path/body assertion、无
   public consume。
7. Admin route 只使用 `verify_admin_session`，不要混入租户 API key。
8. Admin 写操作补 `verify_csrf_token`，除非是 login。
9. 运行 `pytest tests/test_backend_route_auth_contract.py -q`。

## 禁止事项

- 不要新增未记录的公开 route。
- 不要把 `/scenario/*`、`/pipeline/*`、`/fast/*`、upload、publish、telemetry error 等敏感接口放入公开 allowlist。
- 不要把 `/submissions/idempotency` 放入公开 allowlist，或接受 client 自报 tenant。
- 不要公开 acceptance consume route，或让 `artifact:accept`、
  `provider:submit`、client path、legacy path/body assertion 变成 publish authority。
- 不要把 `W1-23 completed_local` 写成 production migration、live publish 或
  delivery evidence。
- 不要用 demo API key 作为 admin auth 替代品。

Publish consume、uncertain outcome、no-retry/no-restore 与 route-block-first
rollback 见 [Publish acceptance consumption](./publish-acceptance-consumption.md)。
