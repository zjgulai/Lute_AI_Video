---
name: adr-002-two-layer-auth
description: ADR #002 文档，记录"X-API-Key 业务接口 + Cookie session 管理后台"双层认证架构的决策依据、当前实现位置、租户隔离机制与回退路径。当审计认证流、添加新路由的鉴权、调试 401/403、或评估 RBAC 演进时使用。
---

# ADR #002 — Two-Layer Auth Architecture

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-05-11（追溯记录 Phase 1 Admin Panel 决策） |
| **决策者** | 工程团队 |
| **影响** | 所有 router 的 dependency、前端登录流、租户隔离边界 |

## 一、Context

系统存在两类完全不同的访问者：

1. **业务用户**（部门用户、外部租户）：通过前端 SettingsPanel 输入 API Key → 调创作 API（`/scenario/*`、`/fast/generate`、`/portfolio/*`）。Key 跟着每个请求走 `X-API-Key` header，**无状态**，无浏览器 session 概念。Demo key `ai_video_demo_2026` 是只读的。
2. **平台管理员**：登录 `/admin/login` → 浏览器拿 session cookie → 在 `/admin/dashboard`/`/tenants`/`/keys`/`/logs`/`/health` 几个页面看监控、发 key、看审计日志。**有状态**，登录 + bcrypt + 限速 + 自动过期。

如果两套用户共用一套鉴权机制（比如都用 API Key），管理员页面就失去了「登录状态」概念，无法做 24h 自动过期、撤销 session、RBAC 等基础功能；如果都用 cookie session，业务调用方需要每次先 POST `/login` 拿 cookie，外部租户接入门槛升高。

## 二、Decision

**业务接口走 X-API-Key、管理后台走 Cookie session，两套互不干扰**。

| | 业务接口 | 管理后台 |
|---|---|---|
| 路径前缀 | `/scenario/*`、`/fast/*`、`/portfolio/*`、`/assets/*`、`/metrics/*`、`/pipeline/*` | `/api/admin/*`、`/admin/login` 页面 |
| 凭证 | `X-API-Key` header | `admin_session` cookie（HttpOnly + Secure） |
| 校验函数 | [`verify_api_key`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/_deps.py#L38) | [`verify_admin_session`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/admin.py#L42) |
| 存储 | `tenants.api_keys` 表（明文 key 的 sha256） | `admin_sessions` 表（token sha256 + expires_at） |
| 过期 | 永久（直到 admin 撤销） | 24h（hardcoded） |
| 限速 | 全局 120 req/60s/IP（rate-limit middleware） | `/admin/login` 5 wrong → 429（按 IP） |
| 状态 | 无状态 | 有状态 |
| Demo 模式 | `ai_video_demo_2026` 只读 | 无 demo |

## 三、当前实现

### 业务接口侧（`X-API-Key`）
- 入口：[`src/routers/_deps.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/_deps.py) 的 `verify_api_key(request, x_api_key)`
- 校验顺序：
  1. `X-API-Key` header 必填，否则 401
  2. 与 `os.environ["API_KEY"]` 直接比对 → 通过则放行（管理员/单租户场景）
  3. 否则查 `tenants.api_keys` 表 sha256(key) 是否存在 → 通过则把 `tenant_id` 写入 `request.state`（多租户）
  4. Demo key `ai_video_demo_2026` 写操作返回 403（Read-only）
- 每个 router 通过 `Depends(verify_api_key)` 接入

### 管理后台侧（Cookie session）
- 登录：[`src/routers/admin.py:52`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/admin.py#L52) `POST /api/admin/auth/login`
  - bcrypt.checkpw 验证密码（永远走完 hash 计算避免 timing attack）
  - 5 次失败按 IP 锁定，第 6 次直接 429
  - 成功生成 32-byte token，sha256 后存表，HttpOnly cookie 写浏览器
- 校验：`verify_admin_session(request)` 从 cookie 读 token → sha256 → 查 `admin_sessions` → 检查 `expires_at` → 返回 `admin_id`
- 登出：删 `admin_sessions` 行 + 清 cookie
- 自动过期：DB 层 `expires_at` 字段 + 每次校验时检查

## 四、Consequences

### 好处
- **职责清晰**：业务调用方不需要懂 cookie，浏览器用户不需要管 API Key
- **故障隔离**：admin login bug 不会影响业务流量；rate-limit 规则可以独立调
- **审计粒度**：admin 操作（发 key、改 tenant）走 audit_logs；业务调用走 metrics
- **多租户原生**：API Key 表自然支持「按 key 找租户」「批量撤销某租户所有 key」
- **未来 RBAC 友好**：admin session 已有 `admin_id`，加 role 字段即可分级

### 代价
- **两套校验代码**：维护负担 +1，每次加新路由要明确选哪一种
- **测试矩阵翻倍**：业务接口要测 401/403/429，admin 要测登录/登出/过期/限速
- **前端两个状态**：localStorage 存 API key + cookie 存 session，前端要分辨
- **错误码混淆**：401 在两侧含义不同（API Key 无效 vs session 过期），靠路径区分

## 五、Alternatives Considered

### A. 全部用 API Key
- admin 页面无法做「登录后 24h 自动过期」
- 撤销 session 需要管理员手动转 admin key 失效，体验差
- **拒绝**：admin 体验严重退化

### B. 全部用 OAuth2 + JWT
- 引入完整 OAuth provider（Auth0/Keycloak）→ 运维成本暴涨
- 业务调用方要先走 token 流，外部接入门槛升高
- **拒绝**：杀鸡用牛刀

### C. 共享 session 机制 + role 字段区分 admin/user
- 业务用户被迫走浏览器 cookie 流，无法 server-to-server 调用
- **拒绝**：违反业务 API 的无状态契约

## 六、Rollback Plan

如果未来要做 SSO / OAuth：
1. **保留 X-API-Key 兼容层**（外部租户已经在用，不能强制迁移）
2. **新加 `/auth/oauth/*` 路由 + 新的 `verify_oauth_session`**
3. **admin 后台先迁移**（影响面小）
4. **业务接口跟进**（按租户分批）

回退是渐进的，**不允许一刀切**。

## 七、相关代码

- [`src/routers/_deps.py:38`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/_deps.py#L38) — `verify_api_key`
- [`src/routers/admin.py:42-180`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/admin.py#L42-L180) — 登录/登出/session 校验
- [`src/api.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/api.py) — middleware 与 router 挂载
- [`web/src/components/api.ts`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/api.ts) — 前端 API Key 注入
- [`web/src/app/admin/login/page.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/admin/login/page.tsx) — 前端登录流
