---
name: c2pa-content-credentials
description: ADR-006 — 采用 C2PA Content Credentials 对 AI 生成视频签名以满足 EU AI Act 2026-08-02 deadline。决定 CA 选型、签名算法、镜像集成方式、验证策略。runbook 见 docs/runbooks/c2pa-cert-application.md。
doc_type: adr
module: compliance
topic: content-provenance
status: deprecated
created: 2026-05-17
updated: 2026-07-23
decision_makers: User
related:
  - file: ../../runbooks/c2pa-cert-application.md
    relation: implemented-via
  - file: ./008-transparency-evidence-boundary.md
    relation: superseded-by
---

# ADR-006: C2PA Content Credentials for AI-Generated Videos

> **Superseded by ADR-008.** 以下内容保留为 2026-05-17 的原始历史决策，不代表当前法律、信任或平台留存结论。

## Context

EU AI Act Article 50 强制要求自 **2026-08-02** 起，AI 生成的视频内容必须携带可验证的 provenance 元数据（C2PA Content Credentials），否则在欧盟市场分发违规。

我们的产品 (短视频 AI Pipeline) 主要面向跨境电商 (TikTok / Facebook / Instagram)，部分流量来自欧洲，因此必须合规。

## Decision

**Accepted Option A: CA-issued publisher cert + c2pa-python in backend image**

1. **签名 CA**: DigiCert 或 GlobalSign（并行询价，2 周内选定）
2. **签名算法**: ES256 (ECDSA P-256) — C2PA spec 推荐 + 性能合理
3. **集成位置**: backend image 内嵌 `c2pa-python` SDK，每个生成视频在 `remotion_assemble` 后立即签名
4. **元数据**: `c2pa.actions.ai_generated` claim + `c2pa.author` + `c2pa.created` timestamp
5. **存储**: 签名后 .mp4 直接覆盖原文件，原始 unsigned 版本在 portfolio 不保留
6. **验证**: Adobe Inspector / contentcredentials.org/verify 双源验证

## Alternatives considered

- **Option B: 自签 cert** — 拒绝。Adobe Inspector / TikTok / Facebook 校验器不信任自签 cert，欧盟监管不认可。
- **Option C: 第三方 SaaS (e.g., Truepic)** — 拒绝。每视频 $0.05-$0.20 成本不可控，外部依赖增 SLA 风险。
- **Option D: 不签名 + 在 UI 加 "AI generated" 文字水印** — 拒绝。不符合 EU AI Act 技术要求。

## Consequences

### Positive
- ✅ 满足 EU AI Act 8/2 deadline
- ✅ 用户在 TikTok 看到 "C2PA verified" 徽章，增加信任度
- ✅ 一次集成，长期受益（cert 1 年自动续）

### Negative
- ⚠️ Backend image 增 ~30MB (c2pa-python + dependencies)
- ⚠️ 每视频签名增 100-300ms 处理时间
- ⚠️ Cert 年费 ~$500
- ⚠️ Private key 安全管理负担（chmod 600 + 不入 git）

### Risk
- ⏰ CA 审批 7-14 天 — 必须 6/15 前发送，否则 8/2 前到不了手
- ⚠️ c2pa-python 与 ffmpeg 二进制兼容性需要测试

## Implementation roadmap

```
B4 ─ 申请 CA cert         (user, 6/15 deadline)
   ↓ wait 7-14 d
B5 ─ c2pa-python 入镜像   (AI, 1 d)
   ↓
B6 ─ Adobe Inspector 验证 (user + AI, 3 d)
   ↓
8/2 ─ EU AI Act 生效 hard deadline
```

详细操作步骤见 [c2pa-cert-application.md](../../runbooks/c2pa-cert-application.md)。

## Related

- [EU AI Act Article 50](https://artificialintelligenceact.eu/article/50/)
- [C2PA Spec 2.0](https://c2pa.org/specifications/specifications/2.0/specs/C2PA_Specification.html)
- [c2pa-python](https://github.com/contentauth/c2pa-python)
- [Adobe Content Credentials Inspector](https://contentcredentials.org/verify)
