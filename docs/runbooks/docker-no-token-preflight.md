---
title: Docker 无 Token 预检 Runbook
doc_type: workflow
module: deploy
topic: docker-no-token-preflight
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# Docker 无 Token 预检 Runbook

## 触发场景

CI 或部署预检需要确认 Docker image 与 compose 文件仍可解析，但当前没有 poyo.ai 余额，不能触发真实生成链路。

## 影响范围

- GitHub Actions 主 CI 的 `docker-build` job
- GitHub Actions deploy workflow 的 `preflight` 与 `build-images` job
- 本地维护 `Dockerfile.backend`、`docker-compose.yml`、`deploy/lighthouse/docker-compose.prod.yml` 时的预检口径

## 预期 MTTR

2-5 min。失败通常来自 compose YAML、路径、env file 或 Docker build context 配置漂移。

## 相关代码

- `Dockerfile.backend`
- `docker-compose.yml`
- `deploy/lighthouse/docker-compose.prod.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `tests/test_docker_no_token_preflight.py`

## 立即诊断

CI 预检只允许两类动作：

通用命令形态是 `docker compose config --quiet`；实际 workflow 必须显式指定 compose 文件。

```bash
: > .env
: > deploy/lighthouse/.env.prod
docker compose -f docker-compose.yml config --quiet
docker compose -f deploy/lighthouse/docker-compose.prod.yml config --quiet
```

Backend image build 只允许 cache-only validation：

```yaml
uses: docker/build-push-action@v5
with:
  push: false
  load: false
```

## 边界

- 不启动容器。
- 不调用 `/health`。
- 不读取生产 secret。
- 不触发 provider，包括 DeepSeek、poyo.ai、Seedance、SiliconFlow、TikTok、Shopify、Supabase。
- 不把 `API_KEY`、`DEEPSEEK_API_KEY`、`POYO_API_KEY`、`SILICONFLOW_API_KEY` 等凭证作为 Docker build args、workflow env 或 compose 预检输入。

## 分类响应

### compose config 失败

1. 先看错误指向的 compose 文件和 service。
2. 如果是 env file 缺失，保留空文件预检，不要改成读取生产 env。
3. 如果是路径不存在，修 compose 文件或部署脚本的相对路径。
4. 重新运行 `pytest tests/test_docker_no_token_preflight.py -q`。

### backend image build 失败

1. 确认失败发生在 dependency install、COPY 路径或 system package install。
2. 不为修 build 传入 provider key。
3. 只允许保留 `APT_MIRROR`、`PIP_INDEX_URL` 这类下载源 build args。
4. 重新运行 workflow 静态测试和目标 build。

## 永久 fix

- 所有 Docker 预检变更必须先更新 `tests/test_docker_no_token_preflight.py`。
- 真 provider smoke 只能留在 P2 充值后的显式手动流程，不能混入 Docker build / compose config 预检。
