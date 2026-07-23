---
title: Transparency delivery and disclosure
doc_type: workflow
module: backend-frontend
topic: transparency-delivery
status: stable
created: 2026-07-23
updated: 2026-07-23
owner: self
source: human+ai
---

# Transparency delivery and disclosure

## 触发场景

- Fast 或 S1-S5 结果页显示“透明度完整性不可验证”；
- evidence package 下载返回 `404`、`409` 或 `503`；
- acceptance/publish 因 transparency authority 不一致而 fail closed；
- TikTok/Shopify fixture payload 缺少服务端 AI-generated 可见披露。

本 runbook 只覆盖本地/fixture/read-only 诊断，不授权生产写入、certificate 操作、真实
provider/publish/delivery、独立 validator 或平台上传。

## 不变量

1. 结果与复核界面始终显示 AI-generated 标签；缺少 resource identity 或校验失败时只
   显示不可验证状态，不隐藏标签，也不开放 package。
2. `GET /api/transparency/{resource_type}/{resource_id}` 和 `/package` 都需要有效
   `X-API-Key`，只读取 authenticated tenant 的 exact durable submission。
3. 服务端重新验证 terminal record、strict projection、canonical tenant path、sidecar
   digest、detached digest、record identity、artifact bytes，以及 required signing 的本地
   Reader truth。任一不一致均 fail closed，不从 PostgreSQL 回退 filesystem truth。
4. ZIP 只包含 exact immutable sidecar JSON 和其 `.sha256` detached digest；client 不重建、
   补写或修改 package。
5. `signed_local_readback` 只表示当前本地 Reader 校验了 AI-generated manifest 和绑定
   integrity。它不是受信签发者、独立验证、目标平台保留或法律合规证据。
6. accepted publish 必须绑定同一 sidecar facts。TikTok description 最后恰有一条
   `AI-generated content.`；Shopify media title/alt 以 `[AI-generated] ` 开头。client
   不能删除或重复该标记，追加标记后的平台长度限制在 acceptance consume 和 connector
   mutation 前验证。
7. durable `publish-receipt.v1` 继续只记录 provider operation/resource truth；不得把
   disclosure 字段写成 provider 已验证或平台已保留 C2PA。

## Read-only API

```text
GET /api/transparency/fast/{task_id}
GET /api/transparency/fast/{task_id}/package
GET /api/transparency/scenario/{label}
GET /api/transparency/scenario/{label}/package
```

成功 projection 的 `verification_scope` 只有：

- `provenance_only`：有生成来源 sidecar，没有最终媒体签名；
- `unsigned_pending_review`：最终媒体是 local draft，待人工审核；
- `local_reader_only`：required C2PA 已由本地 Reader 回读，但未独立验证。

## Failure matrix

| HTTP / UI | 含义 | 行动 |
|---|---|---|
| `404 transparency_not_found` | unknown、cross-tenant、非 terminal 或非法 resource identity | 核对 authenticated tenant 与 durable resource；不得枚举其他 tenant。 |
| `409 transparency_integrity_error` | projection、sidecar、digest、artifact 或 Reader truth 不一致 | 锁定 package/acceptance/publish，保留文件与日志，修复根因后重新生成新的 authority。 |
| `503 transparency_store_unavailable` | durable submission store 不可用或返回不可信数据 | 停止，不 fallback 到 memory/filesystem。 |
| UI “透明度完整性不可验证” | identity 缺失、请求失败或服务端 fail closed | 标签继续显示；package button 必须不存在。 |

## 本地验证

```bash
.venv/bin/pytest -q \
  tests/test_transparency_disclosure.py \
  tests/test_artifact_acceptance_service.py \
  tests/test_publish_attempt_service.py \
  tests/test_publish_attempt_contracts.py

cd web
npm test -- --run \
  src/components/TransparencyStatus.test.tsx \
  src/components/apiTransparency.test.ts
npm run check:api-types
```

同时运行 source Pyright、test ratchet、Ruff、frontend lint/typecheck/build 和 docs governance。
所有 fixture connector 必须使用 injected transport；不得为了验证披露而启用真实 publish。

## 外部证据边界

- W4-06 owner/legal：法规适用、operator role、geography、例外与可见标签文案；
- W4-07 production certificate：受信链与 private-key custody；
- W4-08 independent validation：exact media validator 结果和目标平台 retention。

在三项全部完成前，最高结论只能是本地 L2 engineering provenance closure。

## 相关实现

- `src/services/transparency_disclosure.py`
- `src/models/transparency.py`
- `src/services/artifact_acceptance.py`
- `src/services/publish_attempt.py`
- `web/src/components/TransparencyStatus.tsx`
- [ADR-006](../architecture/adr/006-c2pa-content-credentials.md)
- [Artifact acceptance lifecycle](./artifact-acceptance-lifecycle.md)
- [Publish receipt calibration](./publish-receipt-protocol-calibration.md)
