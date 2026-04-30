---
title: API 路由与安全依赖矩阵（审计附录）
doc_type: analysis
module: audit
topic: api-matrix
status: draft
created: 2026-04-30
updated: 2026-04-30
owner: self
source: ai+human
---

# API 路由矩阵（FastAPI）

说明：`Y` = 依赖 `X-API-Key`（`verify_api_key`）；`N` = 无该依赖（任意知道 URL 的客户端可调用，仍需满足 CORS/网络边界）。

## `src/api.py` 主应用

| 方法 | 路径 | API Key |
|------|------|--------|
| GET | /health | N |
| POST | /pipeline/start | Y |
| GET | /pipeline/{thread_id}/state | Y |
| POST | /pipeline/{thread_id}/review/{review_node} | Y |
| GET | /pipeline/{thread_id}/output | Y |
| GET | /pipeline/{thread_id}/distribution | Y |
| GET | /pipeline/{thread_id}/export | Y |
| POST | /scenario/s1 | Y |
| POST | /scenario/s2 | Y |
| POST | /scenario/s3 | Y |
| POST | /scenario/s4 | Y |
| POST | /scenario/s5 | Y |
| POST | /fast/generate | Y |
| POST | /scenario/s1/start | Y |
| POST | /scenario/s1/step/{step_name} | Y |
| POST | /scenario/s1/regenerate | Y |
| POST | /scenario/s1/resume | Y |
| GET | /scenario/s1/state/{label} | Y |
| PUT | /scenario/s1/state/{label} | Y |
| GET | /scenario/{scenario}/state/{label}/steps | Y |
| POST | /scenario/{scenario}/step/{step_name} | Y |
| PUT | /scenario/{scenario}/state/{label} | Y |
| POST | /scenario/{scenario}/regenerate/{label}/{step_name} | Y |
| GET | /scenario/{scenario}/gate/{label}/{gate_id} | Y |
| POST | /scenario/{scenario}/gate/{label}/{gate_id}/generate | Y |
| POST | /scenario/{scenario}/gate/{label}/{gate_id}/approve | Y |
| POST | /scenario/{scenario}/gate/{label}/{gate_id}/regenerate/{candidate_id} | Y |
| POST | /distribution/publish | Y |
| GET | /distribution/status/{platform}/{post_id} | Y |
| GET | /distribution/platforms | Y |
| POST | /publish/{video_id} | Y |
| GET | /metrics/{video_id} | Y |
| GET | /dashboard/overview | Y |
| POST | /metrics/pull | Y |
| POST | /api/upload | Y（在 multipart 可用时注册） |
| GET | /api/files | Y |
| GET | /api/media/{media_path:path} | **N** |

## `src/api_assets.py`（prefix `/api/assets`）

路由级 **未** 挂载 `Depends(verify_api_key)`，与主应用多数接口不一致。

| 方法 | 路径（相对 prefix） | API Key |
|------|---------------------|--------|
| POST | /upload | N |
| POST | /brand-packages | N |
| GET | /brand-packages/{package_id} | N |
| GET | /brand-packages | N |
| DELETE | /brand-packages/{package_id} | N |
| POST | /influencers | N |
| GET | /influencers/{influencer_id} | N |
| GET | /influencers | N |
| PUT | /influencers/{influencer_id}/product-links | N |
| DELETE | /influencers/{influencer_id} | N |
| POST | /remix-brief | N |
| GET | /{asset_id} | N |
| GET | / | N |
| PUT | /{asset_id}/tags | N |
| DELETE | /{asset_id} | N |

## `src/telemetry_endpoint.py`（prefix `/telemetry`）

| 方法 | 路径 | API Key |
|------|------|--------|
| GET | /metrics | N |
| GET | /errors | N |

## 审计备注（摘要）

- **鉴权不一致**：作品集列表需 Key，静态媒体 `GET /api/media/...` 不需 Key — 适合浏览器 `<video src>`/新标签打开，但 **知道或可枚举路径即可拉取文件**（与 Nginx 生产暴露面一致时需网络层或签名 URL 策略）。
- **`/api/assets/*` 无 Key**：内存态品牌/网红数据与上传接口在 **面向公网** 时属 **高危缺省**，应至少与主 API 对齐鉴权或独立 service token。
