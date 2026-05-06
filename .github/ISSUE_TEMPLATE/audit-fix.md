---
name: 审计修复任务(Audit Fix)
about: 来源于 2026-05-06 双审计的修复任务,从优化路线图派生
title: "[T1.x] <任务标题>"
labels: ["audit-fix"]
assignees: []
---

<!--
使用说明:
- 任务来源:docs/workflows/optimization-plan-mece-audit-2026-05-06-stable.md
- 标题前缀必须用任务 ID(T1.1 / T2.5 / T3.6 等),便于检索与依赖追踪
- 创建后立即补打标签:phase-N / priority-pX / dim-dX-<name>
-->

## 任务 ID

<!-- 例:T1.1 -->

## 维度 / Phase / Priority

- 维度: <!-- D1 架构 / D2 隔离 / D3 错误 / D4 商业 / D5 持久化 / D6 体验 / D7 质量 / D8 部署 -->
- Phase: <!-- 1 / 2 / 3 / 4 -->
- Priority: <!-- P0 / P1 / P2 / P3 -->
- Effort(人日): <!-- 估时 -->

## Audit Source(必填,链回审计原文行号)

- [ ] `docs/analysis/mece_deep_audit_final_20260506.md` —— 第 ___ 行
- [ ] `eval/architecture-deep-audit-report-20260506.md` —— 第 ___ 行

## 决策依据

<!-- 该任务对应优化路线图的哪个决策(D1~D7)。例:决策 5(多租户隔离粒度) -->

## 目标

<!-- 一句话:做完这件事,什么发生了改变?
不要写成"修复 XX bug",要写成"消除 XX 静默失败,使前端能在 YY 场景下看到 ZZ 错误码"。 -->

## 实现要点

<!-- 从 optimization-plan-mece-audit-2026-05-06-stable.md 对应任务卡片复制 -->

## 相关文件

<!-- 用 file:line 格式,便于跳转
- src/tools/poyo_client.py:43
- src/tools/seedance_client.py:99-105
-->

## 依赖

- 阻塞此任务:<!-- T1.x / 无 -->
- 此任务阻塞:<!-- T1.y, T2.z / 无 -->

## 验收标准

- [ ] 单元测试新增/修改:<!-- 文件路径 + 测试名 -->
- [ ] E2E / 手工验证:<!-- 具体步骤 -->
- [ ] CI 通过:lint + test + typecheck
- [ ] 路线图状态更新:在 `optimization-plan-mece-audit-2026-05-06-stable.md` 第 7 节"执行日志"追加 `YYYY-MM-DD T1.x 完成 commit:<sha>`

## 风险与回滚

<!-- 该改动可能影响什么?如何回滚? -->

## 参考资料

<!-- 相关 PR、文档、外部链接 -->
