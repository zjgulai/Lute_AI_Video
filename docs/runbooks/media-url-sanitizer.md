---
title: Media URL Sanitizer Contract
doc_type: workflow
module: frontend
topic: media-url-sanitizer
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# Media URL Sanitizer Contract

## 触发场景

修改 `getMediaUrl()`、`getSignedMediaUrl()`、`RuntimeMediaImage`、portfolio thumbnail 字段、upload preview 字段、`/api/media/sign` 或 `/api/media/{media_path}` 时，先检查本契约。

## 影响范围

媒体 URL 进入 `<img src>`、`<video src>`、`poster`、`audio src` 和下载链接。任何未过滤的绝对 URL、dangerous scheme、protocol-relative URL、query/hash 注入或编码 traversal 都可能导致前端展示异常、同名文件 basename fallback 误命中，或后续打开外部地址时形成安全边界漂移。

## 预期 MTTR

2-5 min。前端 sanitizer 测试能直接定位 DOM URL 构造问题；后端 media resolver 测试能定位 signing / basename fallback 问题。

## 当前契约

机器可读契约：`configs/media-url-sanitizer-contract.yaml`

行为规则：

- `getMediaUrl()` 只接受相对 media path、`/api/media/...` path 和 `output/...` path。
- `getMediaUrl()` 必须拒绝 `http(s):`、`javascript:`、`data:`、`blob:`、`//host/path`、`..`、单层或多层编码 `..`、query 和 fragment。
- `getSignedMediaUrl()` 必须先执行同一 sanitizer；非法路径不得请求 `/api/media/sign`。
- 后端 `_resolve_media_path()` 必须在 basename fallback 前拒绝 scheme、protocol-relative URL、query/hash、空段、`.`、`..` 和单层或多层编码 traversal。
- `output/` 前缀可在前端规范化为 OUTPUT_DIR 下的相对路径，避免旧接口返回 `output/renders/...` 时生成错误 URL。

## 相关代码

- [`web/src/components/api.ts`](../../web/src/components/api.ts) — frontend media URL builder / signer。
- [`src/routers/media.py`](../../src/routers/media.py) — backend media resolver / signer。
- [`web/src/components/mediaUrlSanitizer.test.ts`](../../web/src/components/mediaUrlSanitizer.test.ts) — frontend sanitizer contract。
- [`tests/test_p0_media_tenant_security.py`](../../tests/test_p0_media_tenant_security.py) — backend media resolver security contract。

## 立即诊断

```bash
cd web
npm test -- --run src/components/mediaUrlSanitizer.test.ts
```

```bash
.venv/bin/python -m pytest tests/test_p0_media_tenant_security.py -q
```

这些测试只构造本地字符串、mocked fetch 或 pytest 临时目录文件，不访问生产，不触发 `/api/fast/*`、`/scenario/*` 真实生成、gate candidate、上传、发布或外部 provider。

## 分类响应

- 前端仍生成 `/api/media/https%3A/...`：检查 `hasUnsafeMediaInput()` 是否在 demo mode 和 real mode 前都执行。
- `getSignedMediaUrl()` 对非法路径仍发请求：检查它是否复用 `encodeSafeMediaPath()`，不得维护第二套解析逻辑。
- 后端签名了 `https://evil/.../secret.mp4`：检查 `_validated_media_request_path()` 是否在 basename fallback 之前执行。
- 合法 portfolio path 变空：确认输入是否是相对 path、`/api/media/...` 或 `output/...`；其它绝对本机路径不应作为前端媒体契约。

## 永久 fix

1. 所有运行时媒体 URL 统一经过 `getMediaUrl()` 或 `getSignedMediaUrl()`。
2. 不在业务组件里手写 `/api/media/${path}`。
3. 新增 media path 来源时同步补 sanitizer 测试，不用真实媒体生成验证该契约。
