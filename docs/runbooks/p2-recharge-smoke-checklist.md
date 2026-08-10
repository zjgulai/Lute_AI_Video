---
title: P2 Recharge Smoke Checklist Historical Record
doc_type: workflow
module: qa
topic: p2-recharge-smoke-checklist
status: historical
created: 2026-05-31
updated: 2026-08-01
owner: self
source: human+ai
---

# P2 Recharge Smoke Checklist Historical Record

本文件不作为当前执行入口。P2/C21 充值后 smoke 已退役；对应脚本仅保留为
无条件失败的历史兼容桩，不能读取凭据、启动子进程、访问生产或调用 provider。

当前唯一允许的 provider 执行路径是新建且逐次授权的 W5 exact-authorization
计划。历史 P2/C21 的授权记录、余额检查、环境变量和命令不能转换、复用或作为
W5 权限。生产 E2E token job 同样硬禁用，只保留不可执行的契约参考。

如需新的真实生成验证，必须从当前 W5 计划、独立 activation/runtime binding、
全新 idempotency key、明确预算与零自动重试边界重新开始；通用“充值后执行”或
`RUN_TOKEN_SMOKE` 不再授予任何执行权限。
