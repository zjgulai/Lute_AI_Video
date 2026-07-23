---
title: "ADR-008: Transparency evidence boundary"
name: transparency-evidence-boundary
description: 采用 C2PA、服务端 provenance sidecar 与可见 AI 标签作为内容透明度工程方案，并明确本地回读、法律适用、受信证书、独立验证和平台留存的证据边界。
doc_type: architecture
module: compliance
topic: content-provenance
status: stable
created: 2026-07-23
updated: 2026-07-23
owner: User
source: human+ai
related:
  - file: ./006-c2pa-content-credentials.md
    relation: supersedes
  - file: ../../runbooks/transparency-delivery.md
    relation: implemented-via
  - file: ../../runbooks/c2pa-cert-application.md
    relation: external-prerequisite
---

# ADR-008: Transparency evidence boundary

| | |
|---|---|
| 状态 | Accepted, supersedes ADR-006 |
| 日期 | 2026-07-23 |
| 决策者 | User |
| 影响 | C2PA、provenance、acceptance、transparency package、publish metadata |

## Context

ADR-006 决定采用 C2PA，但把法律充分性、生产信任和平台展示写成了已经成立的结论。
当前系统需要同时保存机器可验证的生成来源和用户可见的 AI-generated 提示，并明确
工程证据能够证明什么。单独的 UI 文字无法提供 artifact-bound provenance；单独嵌入
C2PA 也不能证明证书受信、平台会保留 manifest、用户会看到标签或法律义务已经满足。

EU Regulation 2024/1689 Article 50(2) 要求相关 provider 的合成内容输出在技术可行范围
内以 machine-readable 形式标记并可检测；Article 50(4) 对特定 deep-fake deployer 另有
清晰披露义务。法规文本没有把 C2PA 写成唯一技术方案。项目主体角色、地域、内容类型、
例外和最终义务必须由 W4-06 owner/legal 记录确定，工程团队不自行宣称法律合规。

## Decision

采用多层、fail-closed 的透明度边界：

1. 每个真实或 simulated producer 写入严格 hash-only `transparency-record.v1`，聚合为
   immutable `transparency-sidecar.v1` 与 detached SHA-256。
2. 最终 image/video 在 `required` policy 下必须由当前 pinned `c2pa-python` Signer 写入
   AI-generated manifest，并由同一进程 Reader 回读；失败则不产生可验收 authority。
3. 没有生产证书的本地草稿只能标记 `unsigned_pending_review`；本地 fixture certificate
   的成功状态只能叫 `signed_local_readback`，不能叫 trusted、independently validated
   或 compliant。
4. Fast 和 S1-S5 结果/复核界面始终显示 AI-generated 标签。只有 durable projection、
   sidecar、detached digest、artifact bytes 和本地 Reader truth 全部一致时，服务端才
   开放 transparency evidence package。
5. human acceptance 绑定 exact sidecar/C2PA facts；publish 在 consume 前后重新验证同一
   authority，并由服务端追加不可由 client 删除的 TikTok/Shopify 可见披露。
6. provider receipt 只证明平台 operation/resource 的观察事实，不证明 transparency
   manifest 被独立验证或在目标平台留存。

## External gates

- W4-06：owner/legal 确认 operator role、geography、内容类型、例外和可见标签规则。
- W4-07：受信 production signing credential、private-key custody、rotation/revocation
  和 HSM/KMS/secret mount 证据。
- W4-08：独立 validator 对 exact media 的结果，以及目标平台上传后 preservation 和
  最终用户可见披露证据。

这些 gate 任一缺失时，不得把本地 `signed_local_readback` 或 evidence package 提升为
production trust、independent validation、platform retention 或 legal compliance。

## Alternatives considered

- 只显示 UI/水印：不采用，不能提供 artifact-bound machine-readable provenance。
- 只使用 C2PA、不显示文字披露：不采用，无法保证目标平台或用户实际看到披露。
- 自签证书作为生产信任：不采用，本地链路测试不建立外部 trust anchor。
- 第三方签名服务：未批准；成本、数据边界、SLA 和 custody 需要新的设计与授权。

## Consequences

- 正面：provenance、acceptance、package 和 publish metadata 使用同一服务端 authority，
  缺失或不一致时 fail closed。
- 代价：sidecar、artifact、certificate、Reader 和 platform metadata 都进入验收矩阵；
  生产证书与独立 validator 仍是外部依赖。
- 未验证：生产签名时延/容量、CA 费用/审批周期、平台 manifest 保留和法律充分性。

## References

- [EU Regulation 2024/1689, Article 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng)
- [C2PA Content Credentials specification](https://spec.c2pa.org/specifications/specifications/2.2/specs/ContentCredentials.html)
- [Transparency delivery runbook](../../runbooks/transparency-delivery.md)
- [C2PA local checklist](../../runbooks/c2pa-dry-run-checklist.md)
