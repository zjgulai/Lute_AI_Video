---
title: C2PA local verification checklist
doc_type: workflow
module: compliance
topic: c2pa-pipeline
status: stable
created: 2026-06-07
updated: 2026-07-23
owner: self
source: human+ai
description: 验证 local_draft、required fail-closed、fixture signing 与本地 Reader 回读；不宣称受信、独立验证或法律合规。
related:
  - file: ../architecture/adr/006-c2pa-content-credentials.md
    relation: implements-decision-of
  - file: ./transparency-delivery.md
    relation: related
---

# C2PA local verification checklist

## 安全与证据边界

- 不访问外部 CA、timestamp service、validator 或目标平台。
- 不读取/打印 private key，不把 certificate/key 写入仓库。
- `local_draft` 的唯一成功状态是 `unsigned_pending_review`。
- `required` 缺少 dependency/certificate/key、签名失败或 Reader 回读失败时必须抛出
  stable `C2PASigningError`；禁止返回原路径伪装成功。
- fixture certificate 成功只能记录 `signed_local_readback`。它不证明 signer 受信、
  独立 validation、平台 retention 或法律合规。

## 1. Locked dependency 与静态契约

```bash
.venv/bin/pytest -q \
  tests/test_c2pa_signer_contract.py \
  tests/test_transparency_sidecar.py \
  tests/test_transparency_producer_coverage.py
.venv/bin/ruff check src/tools/c2pa_signer.py src/models/transparency.py
```

要求：

- `c2pa-python==0.36.0` 同时存在于 `pyproject.toml` 和 `uv.lock`；
- manifest 使用 `c2pa.created` 与 AI-generated digital source type；
- required policy 不允许 dependency/config/sign/readback graceful degradation；
- local draft 不调用 Signer/Reader，并保持 package/publish authority 受限。

## 2. Fixture signing/readback

项目测试 fixture 创建临时有效 media、certificate/key，并通过 injected/local
`c2pa-python` Signer/Builder/Reader 验证：

- 输出写入新路径，不覆盖 unsigned input；
- Reader 返回 active manifest，包含 AI-generated action；
- `claimSignature.validated` 与 `assertion.dataHash.match` 存在；
- 除 fixture credential untrusted 外，不接受 validation failure；
- changed bytes、错误 cert/key、错误 manifest 或异常 Reader 全部 fail closed。

不要用任意字节伪装 MP4 做手工签名 smoke；那只能测试错误路径，不能证明媒体签名成功。

## 3. Producer/acceptance/publish 回归

```bash
.venv/bin/pytest -q \
  tests/test_transparency_producer_coverage.py \
  tests/test_artifact_acceptance_service.py \
  tests/test_transparency_disclosure.py \
  tests/test_publish_attempt_service.py
```

required signed artifact 必须由 Reader 再验证后才能进入 accepted authority；sidecar、artifact
或 Reader truth 改变会阻断 consume/package/publish。真实 publish 不属于本检查清单。

## 4. Production 前置 gate

上线 required signing 前仍需：

1. W4-06 owner/legal scope；
2. W4-07 production credential trust chain、KMS/HSM/secret mount、rotation/revocation；
3. W4-08 independent validator + target-platform preservation；
4. 单独批准的 backup/migration/deploy 和 provider-off acceptance。

任一缺失时保持 production signing/publish gate 关闭，不允许用 `C2PA_ENABLED=0` 的无签名
fallback 继续走 accepted delivery。

## 相关代码

- `src/tools/c2pa_signer.py`
- `src/models/transparency.py`
- `src/services/transparency_provenance.py`
- [Transparency delivery](./transparency-delivery.md)
