---
title: Env example no-secret drift guard
doc_type: workflow
module: platform
topic: env-example-no-secret-drift
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Env example no-secret drift guard

## 目的

锁定 `.env.example`、配置默认值和活跃部署 env 文档的 secret 边界，防止真实 provider key、tenant key、token 或生产 `.env.prod` 内容被误提交。

## 不变量

- `.env.example` 中带 `KEY` / `TOKEN` / `SECRET` / `PASSWORD` 的变量只能使用空值、`sk-your-*`、`local-dev-api-key-change-me`、`ai_video_demo_2026` 或等价占位符。
- `src/config.py` 中敏感环境变量 fallback 必须为空字符串；真实值只能来自运行环境。
- 活跃部署 env 文档只能出现占位符、demo/test key、`[redacted]` 或 shell 变量引用。
- 测试不读取真实生产 secret，包括 `deploy/lighthouse/.env.prod`、本地 `.env` 或任何 gitignored 生产 secret。
- 文档说明真实 smoke 需要 key 时，只能用 `<production-api-key>`、`<funded-poyo-key>` 等占位符。

## 验证命令

```bash
.venv/bin/python -m pytest tests/test_env_config_ssot.py -q
```

## 修改流程

1. 修改 `.env.example`、`src/config.py` provider/env 默认值或部署 env 文档前，先运行 focused test。
2. 新增敏感变量时，只在 `.env.example` 放占位符，不填真实 key。
3. 更新生产配置时只改 gitignored `deploy/lighthouse/.env.prod` 或 CI secrets，不把值复制进文档。
4. 发现泄漏时立即走 `docs/runbooks/key-rotation.md`，不要只删除文本。

## 相关文件

- `.env.example`
- `src/config.py`
- `tests/test_env_config_ssot.py`
- `configs/env-example-no-secret-contract.yaml`
- `deploy/lighthouse/.env.prod`：真实生产 secret 文件，gitignored，测试明确不读取。
