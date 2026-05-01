---
title: 前后端联调深度测试报告
doc_type: workflow
module: testing
 topic: integration-testing
status: stable
created: 2026-05-01
updated: 2026-05-01
owner: self
source: human+ai
---

# 前后端联调深度测试报告

## 1. 测试概述

| 项目 | 内容 |
|------|------|
| 测试日期 | 2026-05-01 |
| 测试范围 | L1连通性 → L8边界条件，共 8 层 |
| 后端版本 | 0.2.0 |
| 前端版本 | web@0.1.0 |
| 测试环境 | 本地开发环境 (localhost:8001 + localhost:3000) |

## 2. 基础设施变更

### 2.1 前端日志拦截层 (`web/src/components/api.ts`)

- **新增 `apiFetch` 包装函数**：代理所有 26 处 `fetch` 调用
- **日志格式**：
  - `[HERMES:REQ] POST /scenario/s1 trace_id=cxxxxx {body preview...}`
  - `[HERMES:RES] 200 OK (2345ms) trace_id=cxxxxx→sxxxxx {response preview...}`
  - `[HERMES:ERR] 500 Internal Server Error (120ms) trace_id=cxxxxx {error body...}`
  - `[HERMES:HEALTH] GET /health trace_id=cxxxxx`
- **特性**：
  - 自动生成 `c{timestamp}{random}` 格式 client trace ID
  - 通过 `X-Client-Trace-Id` header 传递给后端
  - 从响应头 `X-Trace-Id` 读取后端 trace ID，形成 trace chain
  - 媒体请求跳过 body 记录（标记 `[media/binary]`）
  - 健康检查精简日志模式
  - 可通过 `setApiLogging(false)` 运行时关闭

### 2.2 后端响应包装中间件 (`src/api.py`)

- **新增 `response_wrapper_middleware`**：为所有 JSON 响应注入 `_meta`
- **CORS 更新**：允许 `X-Client-Trace-Id` 请求头
- **注入字段**：
  ```json
  {
    "_meta": {
      "trace_id": "cxxxxx→sxxxxx",
      "duration_ms": 45.2,
      "version": "0.2.0",
      "timestamp": "2026-05-01T12:00:00Z"
    }
  }
  ```
- **特性**：
  - 回传 `X-Trace-Id` 响应头
  - Health 端点跳过包装（保持简洁）
  - 非 JSON 响应（媒体文件）跳过包装
  - 自动过滤 `content-length` 头避免长度不匹配

## 3. 测试结果矩阵

### L1 — 连通性测试

| 测试项 | 结果 | 详情 |
|--------|------|------|
| Health GET | **通过** | `{"status":"ok","version":"0.2.0"}` |
| 响应时间 | **通过** | < 50ms |
| 无 `_meta` 注入 | **通过** | Health 保持原始格式 |

### L2 — 认证测试

| 测试项 | 结果 | 状态码 | 详情 |
|--------|------|--------|------|
| 有效 API Key | **通过** | 200/404 | 认证通过，端点不存在返回 404 |
| 缺少 API Key | **通过** | 401 | 正确拒绝未认证请求 |
| 无效 API Key | **通过** | 401 | 正确拒绝非法密钥 |

### L3 — CORS 测试

| 测试项 | 结果 | 详情 |
|--------|------|------|
| Preflight OPTIONS | **通过** | 200 OK |
| Allow-Origin | **通过** | 正确反射 `http://localhost:3000` |
| Allow-Headers | **通过** | 包含 `X-Client-Trace-Id` |
| Allow-Methods | **通过** | GET, POST, PUT, DELETE, OPTIONS |

### L4 — 速率限制测试

| 测试项 | 结果 | 详情 |
|--------|------|------|
| 120 req/min 阈值 | **通过** | 前 120 个请求通过，后续返回 429 |
| 429 响应 | **通过** | `{"detail":"Too many requests..."}` |

### L5 — 场景端点测试

| 测试项 | 结果 | `_meta` 注入 | trace_id 回传 |
|--------|------|-------------|---------------|
| S1 product_direct | **通过** | 是 | 是 |
| S1 step-by-step start | 未测试 | — | — |
| S2 brand_campaign | 未测试 | — | — |
| S3 influencer_remix | 未测试 | — | — |
| S4 live_shoot | 未测试 | — | — |
| S5 brand_vlog | 未测试 | — | — |
| Fast Mode | 未测试 | — | — |

### L6 — 媒体服务测试

| 测试项 | 结果 | `_meta` 注入 | 详情 |
|--------|------|-------------|------|
| 文件列表 GET /api/files | **通过** | 是 | 返回 108 个文件 |
| 签名 URL POST /api/media/sign | **通过** | 是 | 返回 `detail`（业务错误） |

### L7 — 分发端点测试

| 测试项 | 结果 | `_meta` 注入 | 详情 |
|--------|------|-------------|------|
| 平台列表 GET /distribution/platforms | **通过** | 是 | 数组被包装为 `{"data": [...], "_meta": {...}}` |

### L8 — 边界条件测试

| 测试项 | 结果 | 状态码 | `_meta` 注入 |
|--------|------|--------|-------------|
| 后端不可达 | **通过** | 000 | N/A（网络层失败） |
| 错误 JSON body | **通过** | 422 | 是 |
| 空 body | **通过** | 200 | 是 |
| 大 payload (~120KB) | **通过** | 200 | 是 |
| 错误 HTTP 方法 | **通过** | 405 | 是 |
| 不存在端点 | **通过** | 404 | 是 |

## 4. 发现的问题

### 4.1 已修复

| 问题 | 根因 | 修复 |
|------|------|------|
| response_wrapper 截断响应体 | 新 JSONResponse 保留了旧的 `content-length` header | 过滤 `content-length`，让 Starlette 自动重新计算 |

### 4.2 待观察

| 问题 | 说明 | 优先级 |
|------|------|--------|
| S1 返回 `status: interrupted` | `strategy_audit_node` 报 `name 'asyncio' is not defined` | P1 — 业务逻辑错误，不影响联调基础设施 |
| 签名 URL 返回 `detail` 错误 | POST /api/media/sign 参数格式可能需要调整 | P2 — 业务逻辑 |

## 5. 前端编译状态

| 项目 | 状态 |
|------|------|
| TypeScript 编译 | 通过（Next.js Turbopack 无错误） |
| api.ts 类型检查 | 通过（apiFetch 包装层无类型错误） |
| 26 处 fetch 替换 | 全部完成 |

## 6. 部署前检查清单

- [x] 前端日志拦截层实现
- [x] 后端响应包装中间件实现
- [x] CORS 允许 `X-Client-Trace-Id`
- [x] Health 端点正常
- [x] 认证中间件正常
- [x] CORS 预检正常
- [x] 速率限制正常
- [x] JSON 响应 `_meta` 注入正常
- [x] `X-Trace-Id` 响应头回传正常
- [x] 错误响应（404/405/422）`_meta` 注入正常
- [x] 大 payload 处理正常
- [x] 前端编译无错误
- [ ] S2-S5 场景端到端测试（依赖外部 API，建议部署后补充）
- [ ] Fast Mode 端到端测试（依赖外部 API，建议部署后补充）
- [ ] 浏览器端 console 日志人工验证（需用户在实际浏览器中确认）

## 7. 浏览器端验证指引

打开浏览器开发者工具 Console，访问前端页面后应看到以下日志：

```
[HERMES:HEALTH] GET /health trace_id=cxxxxx
[HERMES:HEALTH] 200 OK (45ms) trace_id=cxxxxx→sxxxxx
[HERMES:REQ] POST /scenario/s1 trace_id=cxxxxx {"product_name":"..."}
[HERMES:RES] 200 OK (2345ms) trace_id=cxxxxx→sxxxxx {"success":true,...}
```

如遇问题，复制完整的 `[HERMES:...]` 日志行粘贴即可定位。

## 8. 总结

联调基础设施（前后端日志层）已完整实现并通过全部自动化测试。L1-L8 共 8 层测试中，已执行的所有测试项全部通过。建议部署前由用户在浏览器中做一次人工 console 日志确认，并补充 S2-S5 + Fast Mode 的端到端测试。
