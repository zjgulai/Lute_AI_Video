---
title: Docker dev tool parity
doc_type: workflow
module: ci
topic: docker-dev-tool-parity
status: stable
created: 2026-06-01
updated: 2026-07-22
owner: self
source: human+ai
---

# Docker Dev Tool Parity

## 1. 适用范围

本 runbook 约束 Dockerfile、CI 和 lockfile 中的测试/开发工具一致性。机器可读契约是 [`configs/docker-dev-tool-parity-contract.json`](../../configs/docker-dev-tool-parity-contract.json)，测试入口是 [`tests/test_docker_dev_tool_parity.py`](../../tests/test_docker_dev_tool_parity.py)。

## 2. 当前规则

- `pyproject.toml` 与 `uv.lock` 是 Python dependency 的唯一 authority；Docker 和 CI
  必须执行 `uv sync --locked`，不得从 `requirements.txt` 安装。
- `requirements.txt` 仅是 `uv export --locked --extra dev --no-hashes --no-emit-project`
  生成的兼容输出；漂移测试必须逐行核对重新生成结果。
- Python dev tools 仅声明在 `project.optional-dependencies.dev`，当前包括 `pytest`、
  `pytest-asyncio`、`pytest-mock`、`pytest-timeout`、`pytest-cov`、`ruff`、`pyright`
  和 `pip-audit`。
- 前端 dev tools 必须同时存在于 `web/package.json` 和 `web/package-lock.json` 根包记录中。
- `web/Dockerfile` 必须精确复制 `package.json package-lock.json`，并使用 `npm ci --ignore-scripts`。
- `web/Dockerfile` 禁止使用 `package-lock.json*`、`npm install` fallback 或 `||` 兜底。
- GitHub Actions 中的 Node job 必须使用 `npm ci`，并用 `web/package-lock.json` 作为 npm cache dependency path。

## 3. 变更流程

1. 新增 Python 测试工具时只修改 `pyproject.toml`，执行 `uv lock`，再用受控
   `uv export` 命令重新生成 `requirements.txt`；不得手改 lock 或导出文件。
2. 新增前端测试/构建工具时，先执行 `npm install --save-dev <pkg>` 更新 `web/package.json` 与 `web/package-lock.json`，再更新 contract。
3. 改 Dockerfile 前先确认是否会破坏 `npm ci` 的 lockfile fail-fast 语义。
4. 本守卫只做本地静态检查，不启动容器、不运行 Docker build、不触发生产、不访问 provider。
5. 调用网络 CLI 的 loopback hermetic fixture 必须同时设置 `NO_PROXY` 与 `no_proxy`
   为 `127.0.0.1,localhost`。否则新版本 CLI 可能继承开发机代理，把本地 fixture
   转发到外部代理并产生伪 5xx；真实运行代码仍应保留调用方配置的代理语义。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_docker_dev_tool_parity.py tests/test_docker_no_token_preflight.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_docker_dev_tool_parity.py tests/test_docker_no_token_preflight.py tests/test_docs_link_check_scope.py
git diff --check
```

## 5. 失败处理

- Python 工具缺失：修改 `pyproject.toml` 后重新生成 `uv.lock` 和兼容导出；不要
  把 `requirements.txt` 提升为第二套 authority。
- 前端 lockfile 缺失：运行 npm lockfile 更新流程，不手写 `package-lock.json`。
- Dockerfile 出现 `npm install` fallback：移除 fallback，让 lockfile 漂移在构建时失败。
