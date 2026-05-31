---
title: Health Endpoint No-Secret Contract
doc_type: workflow
module: backend
topic: health-no-secret
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# Health Endpoint No-Secret Contract

## 触发场景

新增或调整 `/health`、数据库健康探针、Remotion 探针、media tools 探针、response wrapper、部署 smoke 或公开健康检查字段时，先检查本契约。

## 影响范围

`/health` 是公开 endpoint，用于负载均衡、部署 smoke 和生产状态检查。它可以暴露能力状态，但不得暴露 `DATABASE_URL`、provider API key、token、password、签名 secret 或服务器绝对路径。

## 预期 MTTR

2-5 min。泄密风险通常能通过本地单测定位到新增探针返回值或错误字符串。

## 当前契约

机器可读契约：`configs/health-endpoint-no-secret-contract.yaml`

允许的顶层字段：

- `status`
- `version`
- `remotion`
- `persistence`
- `media_tools`

禁止出现在响应值里的内容类型：

- provider API key，例如 `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY`
- `DATABASE_URL` 或任何带账号密码的 DSN
- password、token、signing secret
- 服务器绝对路径，例如 `/Users/...`、`/app/...`、`/var/...`

脱敏标记：

- secret、token、password、DSN：`[redacted]`
- 内部绝对路径：`[internal-path]`

## 相关代码

- [`src/routers/health.py`](../../src/routers/health.py) — `/health` 组装和递归脱敏。
- [`tests/test_health_endpoint_no_secret_guard.py`](../../tests/test_health_endpoint_no_secret_guard.py) — 本契约的行为和静态守卫。
- [`configs/api-response-metadata-contract.yaml`](../../configs/api-response-metadata-contract.yaml) — `/health` 跳过 `_meta` 但仍保留 `X-Trace-Id` 的响应契约。

## 立即诊断

```bash
.venv/bin/python -m pytest tests/test_health_endpoint_no_secret_guard.py -q
```

该测试只调用本地函数和 mock 探针，不访问生产，不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

如需手动检查本地实例：

```bash
curl -sS http://localhost:8001/health | python -m json.tool
```

检查输出中不得出现真实 secret、`postgresql://`、`mysql://`、`redis://`、`/Users/`、`/app/`、`/var/`。

## 分类响应

- 输出出现 provider key：检查新增探针是否把 `os.environ`、client config 或异常原文直接返回。
- 输出出现 `DATABASE_URL`：检查 `check_pg_health()` 或数据库连接异常是否被原样塞进 `persistence.error`。
- 输出出现绝对路径：检查 Remotion、ffmpeg、node、media tool 的错误消息；公开响应中只能保留能力状态或 `[internal-path]`。
- 输出缺少能力字段：确认新增脱敏逻辑只替换敏感字符串，不删除 `status`、`version`、`remotion`、`persistence`、`media_tools`。

## 永久 fix

1. `/health` 返回前必须经过递归脱敏。
2. 新增健康探针字段时同步更新 `configs/health-endpoint-no-secret-contract.yaml`。
3. 不要把 provider config、完整 DSN、secret 环境变量或本机路径作为健康检查字段直接返回。
4. 不要用真实生成接口验证 `/health`；健康检查只验证本地能力状态。
