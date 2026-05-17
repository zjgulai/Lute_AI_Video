---
name: c2pa-cert-application
description: C2PA cert 申请清单 + 模板邮件 + 流程跟踪。EU AI Act 8/2 deadline 强制 AI 生成视频签名。最迟 6/15 必须发送 CA 申请，CA 审批 7-14 天，B5 c2pa-python 镜像 1 day，B6 Adobe Inspector 验证 3 天。关键路径总 21-28 天。
doc_type: runbook
module: compliance
topic: c2pa-pipeline
status: stable
created: 2026-05-17
updated: 2026-05-17
owner: User (operations) + AI (drafting support)
related:
  - file: ../architecture/adr/006-c2pa-content-credentials.md
    relation: implements-decision-of
---

# C2PA Cert 申请 — User Action Runbook

## 一、Why now

EU AI Act 自 **2026-08-02** 起强制要求 AI 生成内容（含视频）携带 C2PA Content Credentials 签名，否则在欧洲市场发布违规。

关键路径：

```
6/15 (latest) ─ 发送 CA 申请
   ↓ 7-14 天 CA 审批
6/22 ~ 6/29 ─ 收到 publisher cert
   ↓ 1 天 B5 c2pa-python 入镜像
6/23 ~ 6/30 ─ 镜像就绪
   ↓ 3 天 B6 Adobe Inspector 验证
6/26 ~ 7/03 ─ 验证完成
   ↓ buffer for surprises
8/2 ─ EU AI Act 生效（hard deadline）
```

**今天 5/17 起到 6/15 还有 29 天 buffer。User 必须在 6/15 前 send。**

## 二、CA 二选一

| CA | 价格估算 | 流程 | 备注 |
|---|---|---|---|
| **DigiCert** | $400-$800/yr | 在线申请 + 公司验证 | 主流，文档清楚 |
| **GlobalSign** | $300-$700/yr | 在线申请 + 法人电话验证 | 价格更友好 |

**推荐**：同时询价两家，选回复快 + 价格 OK 的。

## 三、所需材料 checklist

User 收集（约 1h）:

- [ ] **公司营业执照** (PDF)
- [ ] **法人身份证 / passport** (PDF)
- [ ] **域名 ownership 证明**: `lute-tlz-dddd.top` WHOIS 截图 + DNS TXT 记录（CA 要求验证）
- [ ] **业务用途说明**: "AI-generated short video content for cross-border e-commerce, distributed to TikTok/Facebook/Instagram"
- [ ] **技术联系人邮箱** (User 提供)
- [ ] **公司账单地址 + 付款方式**

## 四、申请邮件模板（DigiCert）

```
Subject: C2PA Publisher Certificate Request — Lute / video.lute-tlz-dddd.top

To: cert-request@digicert.com

Dear DigiCert,

We are applying for a C2PA Content Credentials publisher certificate for
our AI-generated video product.

Company:           Lute (路特)
Product:           Short Video AI Pipeline
Production domain: https://video.lute-tlz-dddd.top
Business:          Cross-border e-commerce video content (maternity products)
                   distributed to TikTok / Facebook / Instagram
EU AI Act:         Required to sign AI-generated content per 2026-08-02 deadline

Cert requirements:
- Identifier:      AI-generated content metadata
- Validity:        1 year (auto-renew preferred)
- Algorithm:       ES256 (ECDSA P-256)
- Key usage:       digitalSignature

Attachments:
1. Business license (公司营业执照).pdf
2. Legal representative ID.pdf
3. Domain ownership proof (WHOIS + DNS TXT).pdf

Please confirm:
- Total fee
- Estimated approval timeline
- Technical onboarding contact

Best regards,
[User Name]
[User Email]
[Phone]
```

## 五、收到 cert 后

User 把 cert + private key 安全交付给运维（不要 commit 到 git）：

```
production:/opt/ai-video/secrets/
├── c2pa-cert.pem        # public cert (chmod 644)
└── c2pa-key.pem         # private key (chmod 600, owner=ai-video)
```

然后 AI 推进 B5（c2pa-python 入 backend image）+ B6（Adobe Inspector 验证）。

## 六、Status tracking

| Date | Stage | Owner | Status |
|---|---|---|---|
| 5/17 | runbook ready | AI | ✅ |
| TBD | 发送 CA 申请 | User | ⏳ |
| TBD | 收到 cert | User | ⏳ |
| TBD | B5 c2pa-python 入镜像 | AI | ⏳ blocked on cert |
| TBD | B6 Adobe Inspector 验证 | User+AI | ⏳ blocked on B5 |
| 8/2 | EU AI Act 生效 deadline | n/a | ⚠️ |

## 七、Fallback if CA approval delays

如 6/29 仍未收到 cert：
1. 启动 **GlobalSign 平行申请**（应早做）
2. **emergency option**: 用 [Adobe Content Authenticity Initiative free dev cert](https://contentauthenticity.org/developer-tools) — 非生产可用，但能 demo 流程
3. 评估 8/2 后的 graceful degradation：在视频 metadata 加 `_unsigned_pending_c2pa: true` 标记，避免完全停服
