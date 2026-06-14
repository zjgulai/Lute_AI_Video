---
title: Lighthouse nginx timeout parity
doc_type: workflow
module: deploy
topic: lighthouse-nginx-timeout-parity
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Lighthouse nginx timeout parity

## 目的

锁定 Tencent Lighthouse 上 AI Video 长任务路由的 nginx timeout，避免 S1-S5、Fast Mode 或 legacy pipeline 长请求被 nginx 提前截断成 504。

## 不变量

- 长任务路由只在 `deploy/lighthouse/ai_video_locations.conf` 中维护，不复制到多个 server block。
- `/api/scenario/`、`/api/fast/`、`/api/pipeline/` 必须保留 `proxy_read_timeout 1500s`。
- `/api/scenario/`、`/api/fast/`、`/api/pipeline/` 必须保留 `proxy_send_timeout 1500s`。
- 上述三个路由必须保留 `proxy_connect_timeout 60s` 和 `proxy_buffering off`。
- `video.lute-tlz-dddd.top` 与 IP fallback `101.34.52.232 _` 必须共同 include `/etc/nginx/ai_video_locations.conf`。
- 该检查只读取本地 nginx 配置和文档，不触发生成接口、不访问生产、不消耗 poyo.ai tokens。

## 验证命令

```bash
.venv/bin/python -m pytest tests/test_lighthouse_nginx_timeout_contract.py -q
```

## 修改流程

1. 修改 `deploy/lighthouse/ai_video_locations.conf` 的 long-running route timeout 前，先更新 `configs/lighthouse-nginx-timeout-contract.yaml`。
2. 如果新增长任务路由，同步加入 contract、测试和 `docs/workflows/deploy-lighthouse-stable.md`。
3. 不要只改 `nginx.conf` 的单个 server block；AI Video route parity 依赖 shared include。
4. 真机部署验证仍走部署 smoke；本守卫只做本地静态一致性检查。

## 相关文件

- `deploy/lighthouse/nginx.conf`
- `deploy/lighthouse/ai_video_locations.conf`
- `docs/workflows/deploy-lighthouse-stable.md`
- `configs/lighthouse-nginx-timeout-contract.yaml`
- `tests/test_lighthouse_nginx_timeout_contract.py`
