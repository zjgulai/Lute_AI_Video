---
name: c2pa-cert-application
description: Production C2PA signing credential 的供应商调研、申请材料和 private-key custody 前置清单；不把 C2PA 当作唯一法律方案，也不预估未经核实的价格或周期。
doc_type: runbook
module: compliance
topic: c2pa-pipeline
status: stable
created: 2026-05-17
updated: 2026-07-23
owner: User (operations) + AI (drafting support)
related:
  - file: ../architecture/adr/006-c2pa-content-credentials.md
    relation: implements-decision-of
---

# Production C2PA credential — owner action runbook

## 一、进入条件

EU Regulation 2024/1689 Article 50 的官方文本要求相关 AI system provider 在技术可行
范围内提供 machine-readable、detectable marking，并对部分 deployer 场景规定可见披露；
法规没有指定 C2PA 是唯一方案。

只有以下条件全部满足才启动采购/申请：

- W4-06 owner/legal 已书面确认 operator role、geography、内容类型、例外与披露要求；
- engineering owner 选择 C2PA 作为 production provenance 机制；
- security owner 批准 private-key custody、rotation、revocation 与 incident response；
- 目标 independent validator/trust list 和平台 preservation 验收方法已经确定。

供应商资格、费用、审批周期和平台支持在执行时通过官方渠道重新核实。旧日期、估价或
非官方邮件地址不得作为采购事实。

## 二、供应商调研

可向 DigiCert、GlobalSign 或其他明确提供适用 C2PA signing credential 的供应商发起
官方询价，但不得预设其当前产品可用。每家必须回答：

- credential profile、algorithm/EKU 与 C2PA trust list 兼容性；
- certificate chain、revocation/status service 与 timestamp 支持；
- hardware-backed key generation、HSM/KMS/remote signing 选项；
- key export policy、rotation/reissue、breach revocation 和 audit log；
- 目标独立 validator 的可验证方法；
- 当前正式价格、审批材料、SLA 和续期流程。

## 三、材料最小化

供应商确认为必要后，由 owner 通过批准的私密渠道提供：

- 公司注册/授权材料；
- signing identity 与业务用途说明；
- 域名或组织控制证明（仅当供应商要求）；
- 安全联系人、账单联系人与 incident contact；
- 计划使用的 HSM/KMS/remote signing 架构。

不要把营业执照、身份证件、私钥、申请表或供应商凭证放入仓库、issue、普通日志或
Codex 记忆。本文不包含实际联系人、邮箱或 PII 模板。

## 四、签发与 custody 验收

1. 优先在 HSM/KMS/approved remote signer 内生成不可导出的 private key。
2. 如供应商流程必须导入 key，使用 approved secret mount；禁止写入 image、Git、共享
   volume、普通 `.env` 或命令历史。
3. 记录 certificate chain、fingerprint、validity、EKU、owner、rotation/revocation 和
   emergency disable procedure，但不记录 private key material。
4. 在隔离环境签署 exact fixture media；由本地 Reader 和独立 validator 分别检查。
5. 本地状态仍叫 `signed_local_readback`；只有 W4-08 独立结果可记录 independent evidence。
6. 在目标平台的授权样本上传后验证 manifest/label preservation；平台 receipt 不能替代
   这一检查。

## 五、失败与停止规则

- 供应商不能证明适用 credential/trust path：停止，不使用普通 TLS/self-signed cert
  冒充 production trust。
- private key custody 不满足 security owner：停止，不导出到主机文件作为临时绕过。
- Reader/validator/平台 preservation 任一失败：保持 acceptance/publish/delivery gate
  关闭，保留证据并修根因。
- 法律 scope 未批准：只保留本地 engineering provenance，不宣称合规。

## 六、当前状态

当前仓库仅有 pinned `c2pa-python`、strict sidecar、fixture signing 和本地 Reader 回读
证据。W4-06/W4-07/W4-08 均是独立外部 gate；本 runbook 本身不证明申请已发送、证书已
签发、生产已配置、平台已保留或法律已验收。

## 相关资料

- [ADR-006](../architecture/adr/006-c2pa-content-credentials.md)
- [C2PA local checklist](./c2pa-dry-run-checklist.md)
- [Transparency delivery](./transparency-delivery.md)
- [EU Regulation 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng)
- [C2PA Content Credentials specification](https://spec.c2pa.org/specifications/specifications/2.2/specs/ContentCredentials.html)
