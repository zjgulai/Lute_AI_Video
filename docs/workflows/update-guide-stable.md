---
title: AI Video 历史更新与功能增加操作指南
doc_type: workflow
module: project
topic: update-and-feature-addition-guide
status: historical
created: 2026-04-30
updated: 2026-08-01
owner: self
source: human+ai
---

# 历史更新与功能增加操作指南

本文档仅保留旧入口的路径兼容性，不作为当前执行入口。旧版内容包含已
废弃的主机侧构建、直接同步、固定测试凭据和破坏性 Docker 命令，不能
复制到本地、CI 或生产环境执行。

当前开发验证以仓库 CI 和项目测试入口为准；生产 deploy、灾备和 token
smoke 的唯一索引是 [Production Operations](../runbooks/production-operations.md)。
发布身份、exact image archive、恢复优先和 provider-off 边界以
[Lighthouse 生产部署指南](deploy-lighthouse-stable.md) 为准。
