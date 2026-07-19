---
title: Remotion no provider key
doc_type: workflow
module: rendering
topic: remotion-no-provider-key
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Remotion No Provider Key

## 1. 适用范围

本 runbook 约束 `rendering/` 子包、Lighthouse rendering service 和 CI/deploy 中的 Remotion 构建/测试边界。机器可读契约是 [`configs/remotion-no-provider-key-contract.json`](../../configs/remotion-no-provider-key-contract.json)，测试入口是 [`tests/test_remotion_no_provider_key_guard.py`](../../tests/test_remotion_no_provider_key_guard.py)。

## 2. 当前规则

- `rendering/` 只能做本地 Remotion bundle/render、clip concat、audio mux 和 health probe。
- `rendering/` 禁止读取 `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`SEEDANCE_API_KEY`、发布平台 token 或 `RUN_TOKEN_SMOKE`。
- `rendering/` 禁止引用 provider API host，例如 `api.poyo.ai`、`api.deepseek.com`、`api.siliconflow.cn`、`api.siliconflow.com`。
- 允许的环境变量只限本地运行控制：`NODE_ENV`、`PORT`、`OUTPUT_DIR`、`PUPPETEER_SKIP_DOWNLOAD`、`PUPPETEER_EXECUTABLE_PATH`、`REMOTION_CHROME_EXECUTABLE`。
- Lighthouse `rendering` service 不使用 `env_file`，只接收 `NODE_ENV=production`、`PORT=3001` 和 `OUTPUT_DIR=/app/output`。
- 本地 `docker-compose.yml` 不单独定义 provider-enabled rendering service，只把 `./rendering` 作为后端容器内本地工具目录挂载。

## 3. 变更流程

1. 修改 `rendering/` 前先确认该逻辑是否属于本地组装；需要调用 provider 的逻辑必须放回 backend tools/skills/pipeline 层。
2. 新增 rendering 环境变量时先更新 contract，并说明它不是 provider credential。
3. CI/deploy 如需新增 `working-directory: rendering` 或 `cd rendering` 步骤，禁止注入 provider key，禁止设置 `RUN_TOKEN_SMOKE=1`。
4. 本守卫只做本地静态检查，不执行 Docker build、不运行 Remotion render、不启动容器、不访问生产、不消耗 poyo.ai tokens。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_remotion_no_provider_key_guard.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_remotion_no_provider_key_guard.py tests/test_docs_link_check_scope.py
git diff --check
```

## 5. 失败处理

- `rendering/` 出现 provider key：删除该读取点，把 provider 调用放回后端 provider client。
- `rendering` compose service 出现 `env_file`：移除，避免 `.env.prod` 中的 provider credentials 泄入渲染容器。
- CI rendering 步骤注入 provider env：拆分为无 token build/test；真实生成 smoke 继续走 P2 充值后的专用流程。
