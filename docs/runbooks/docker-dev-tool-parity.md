---
title: Docker dev tool parity
doc_type: workflow
module: ci
topic: docker-dev-tool-parity
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Docker Dev Tool Parity

## 1. 适用范围

本 runbook 约束 Dockerfile、CI 和 lockfile 中的测试/开发工具一致性。机器可读契约是 [`configs/docker-dev-tool-parity-contract.json`](../../configs/docker-dev-tool-parity-contract.json)，测试入口是 [`tests/test_docker_dev_tool_parity.py`](../../tests/test_docker_dev_tool_parity.py)。

## 2. 当前规则

- Python dev tools 必须同时存在于 `pyproject.toml` 的 `project.optional-dependencies.dev` 和 `requirements.txt`，且版本约束一致。
- 当前 Python dev tools 包括 `pytest`、`pytest-asyncio`、`pytest-mock`、`pytest-timeout`、`pytest-cov` 和 `ruff`。
- 前端 dev tools 必须同时存在于 `web/package.json` 和 `web/package-lock.json` 根包记录中。
- `web/Dockerfile` 必须精确复制 `package.json package-lock.json`，并使用 `npm ci --ignore-scripts`。
- `web/Dockerfile` 禁止使用 `package-lock.json*`、`npm install` fallback 或 `||` 兜底。
- GitHub Actions 中的 Node job 必须使用 `npm ci`，并用 `web/package-lock.json` 作为 npm cache dependency path。

## 3. 变更流程

1. 新增 Python 测试工具时，同步更新 `pyproject.toml`、`requirements.txt` 和 contract。
2. 新增前端测试/构建工具时，先执行 `npm install --save-dev <pkg>` 更新 `web/package.json` 与 `web/package-lock.json`，再更新 contract。
3. 改 Dockerfile 前先确认是否会破坏 `npm ci` 的 lockfile fail-fast 语义。
4. 本守卫只做本地静态检查，不启动容器、不运行 Docker build、不触发生产、不访问 provider。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_docker_dev_tool_parity.py tests/test_docker_no_token_preflight.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_docker_dev_tool_parity.py tests/test_docker_no_token_preflight.py tests/test_docs_link_check_scope.py
git diff --check
```

## 5. 失败处理

- Python 工具缺失：同步 `pyproject.toml` 与 `requirements.txt`，不要只改一个入口。
- 前端 lockfile 缺失：运行 npm lockfile 更新流程，不手写 `package-lock.json`。
- Dockerfile 出现 `npm install` fallback：移除 fallback，让 lockfile 漂移在构建时失败。
