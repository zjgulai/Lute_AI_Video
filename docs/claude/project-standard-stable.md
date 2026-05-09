---
title: AI Video Pipeline — Claude Code 项目标准
doc_type: workflow
module: claude
status: stable
created: 2026-05-09
updated: 2026-05-09
owner: self
source: human+ai
---

# AI Video Pipeline — Claude Code 项目标准

> 项目架构、技术栈和快速参考见根目录 [`CLAUDE.md`](../../CLAUDE.md)。
> 本文档专注 Agent 协作流程和质量门禁。

## 1. Project Overview

| 字段 | 内容 |
|------|------|
| 项目名称 | AI Video Pipeline (Short Video Agent v0.2.0) |
| 业务领域 | 跨境电商短视频 AI 自动化生产 |
| 主要技术栈 | Python 3.12 + FastAPI, Next.js 16 + React 19, PostgreSQL, LangGraph |
| 核心模块 | 16-node pipeline (strategy→script→compliance→storyboard→asset→media→edit→audio→caption→thumbnail→distribution→analytics) |
| 主要负责人 | 项目负责人 + AI 协作助手 |

## 2. Collaboration Principle

AI 助手是软件开发辅助 Agent，职责是帮助工程师分析需求、搜索代码、制定计划、实现功能、补充测试和整理文档。

**AI 不能替代工程师承担最终责任。** 以下变更必须先提出计划并等待人工确认：

- 数据库 schema 变更（迁移、删表、改列类型）
- 公共 API 行为变更（新增/修改/删除端点）
- 认证/授权逻辑变更
- 生产环境配置变更
- 涉及外部 API 密钥/凭证的变更
- 单次改动超过 5 个文件的 refactor
- 删除已有测试或降低测试覆盖率

## 3. Agent 体系总览

13 个 Agent 按职责分为 4 层：

```
┌─────────────────────────────────────────────────────────────┐
│  决策层 (Planning)                                          │
│  metis → prometheus → momus                                 │
│  意图分析 → 方案制定 → 计划审查                              │
├─────────────────────────────────────────────────────────────┤
│  分析层 (Analysis)                                          │
│  explore → oracle → systematic-debugging                    │
│  代码搜索 → 架构判断 → 根因调试                              │
├─────────────────────────────────────────────────────────────┤
│  执行层 (Execution)                                         │
│  sisyphus → hephaestus → sisyphus-junior                    │
│  任务编排 → 深度实现 → 快速修复                              │
├─────────────────────────────────────────────────────────────┤
│  支持层 (Support)                                           │
│  atlas → multimodal-looker → ai-code-acceptance             │
│  文档兜底 → 视觉分析 → 代码验收                              │
└─────────────────────────────────────────────────────────────┘
```

### Agent 职责速查

| Agent | 调用时机 | 核心职责 | 工具权限 |
|-------|---------|---------|---------|
| **metis** | 需求模糊时 | 分析真实意图、识别歧义、找出必须追问的问题 | 只读 |
| **prometheus** | 编码前 | 制定技术方案、任务拆解、测试计划、回滚方案 | 只读 |
| **momus** | 计划完成后 / 代码完成后 | 审查计划的完整性、风险、可执行性；审查代码质量 | 只读 |
| **explore** | 需要定位代码时 | 查找入口、调用链、相似实现、相关测试 | 只读 + Bash |
| **oracle** | 复杂 bug / 架构判断 | 根因分析、方案比较、风险评估 | 只读 + Bash |
| **systematic-debugging** | 任何 bug / 测试失败 | 四阶段调试：根因调查→模式分析→假设验证→实现修复 | 全工具 |
| **sisyphus** | 复杂任务已确认 | 拆解任务、判断调用哪个 agent、跟踪执行状态 | 全工具 |
| **hephaestus** | 深度实现 | 端到端代码实现、测试补充、保持项目风格 | 全工具 |
| **sisyphus-junior** | 简单任务（单文件、<20 行） | 直接执行，不再委派 | 全工具 |
| **atlas** | 文档、总结、轻量分析 | 整理技术文档、生成 README、总结实现过程 | 全工具 |
| **multimodal-looker** | 分析图片/PDF/设计稿 | 提取视觉信息、输出前端实现建议 | 只读 |
| **ai-code-acceptance** | AI 代码完成后 | 验收审查：变更摘要→影响映射→自动化验证→人工走查→风险评估→回滚计划 | 只读 |
| **brainstorming** | 新功能/创意工作前 | 设计探索、需求澄清、方案对比、设计文档输出 | — |

## 4. 决策树：什么时候用什么 Agent

```
用户请求
  │
  ├─ 是新功能 / 创意工作？
  │    └─ 调用 brainstorming → 设计确认后 → prometheus
  │
  ├─ 是 Bug / 测试失败 / 异常行为？
  │    ├─ 简单问题（单文件、已知范围）
  │    │   └─ 调用 sisyphus-junior 直接修复
  │    └─ 复杂问题（根因不明、跨模块）
  │        └─ 调用 systematic-debugging
  │           根因确认后 → prometheus 制定修复计划
  │
  ├─ 是代码审查 / PR Review / AI 输出验收？
  │    └─ 调用 ai-code-acceptance
  │
  ├─ 是文档整理 / 变更说明 / 总结？
  │    └─ 调用 atlas
  │
  ├─ 需要分析图片 / 设计稿 / PDF？
  │    └─ 调用 multimodal-looker
  │
  ├─ 是复杂实现任务（多文件、涉及架构）？
  │    └─ metis → prometheus → momus → sisyphus → momus(最终审查)
  │
  └─ 是简单任务（单文件改动、<20 行、无架构影响）？
       └─ 直接执行（无需 agent 流程）
```

## 5. 标准流程

### 5.1 简单任务流程（单文件、<20 行、无架构影响）

不需要 agent 流程。直接执行：

1. 读取相关代码
2. 修改
3. 运行相关测试验证
4. 汇报修改摘要

### 5.2 复杂任务流程（多文件、涉及架构、新增功能）

```
metis ──→ prometheus ──→ momus ──→ sisyphus ──→ hephaestus ──→ momus
分析意图   制定计划      审查计划    拆解+编排       深度实现        最终审查
```

**各阶段交付物：**

| 阶段 | 交付物 | 决策点 |
|------|--------|--------|
| metis | 目标理解 + 关键歧义 + 必须追问的问题 | 用户澄清后进入下一阶段 |
| prometheus | 需求理解 + 影响范围 + 推荐方案 + 测试计划 + 回滚方案 | 用户确认方案 |
| momus | 审查结论（通过/有条件通过/不通过）+ 必须修改的问题 | 问题修复后重新审查 |
| sisyphus | 子任务拆解 + 涉及文件 + 执行顺序 + 风险点 | 按计划执行 |
| hephaestus | 修改文件 + 核心改动 + 测试结果 + 风险点 | — |
| momus(最终) | 代码审查结论 + P0/P1/P2 分级问题 | 修复后提交 |

### 5.3 Bug 修复流程

```
systematic-debugging
  ├── Phase 1: 根因调查（错误信息、复现、近期变更、证据收集）
  ├── Phase 2: 模式分析（找正常案例、对比差异）
  ├── Phase 3: 假设验证（最小改动测试假设）
  └── Phase 4: 实现修复（创建失败测试→修复→验证）
```

**关键规则：**
- 未完成 Phase 1 根因调查，不得提出修复方案
- 尝试 3 次修复仍未成功 → 停止修复，质疑架构，与人工讨论

### 5.4 新功能流程

```
brainstorming
  ├── 探索项目上下文
  ├── 追问澄清（一次一个问题）
  ├── 提出 2-3 个方案 + 推荐
  ├── 用户确认设计
  └── 输出设计文档 → 调用 prometheus 制定实现计划
```

## 6. Agent 配置说明

### 6.1 配置文件位置

Agent 定义文件放在项目根目录的 `.claude/agents/` 下：

```
.claude/agents/
├── metis.md
├── prometheus.md
├── momus.md
├── explore.md
├── oracle.md
├── sisyphus.md
├── hephaestus.md
├── sisyphus-junior.md
├── atlas.md
├── brainstorming.md
├── multimodal-looker.md
├── systematic-debugging.md
└── ai-code-acceptance.md
```

### 6.2 Agent 文件格式

每个 `.md` 文件由两部分组成：

**Frontmatter（YAML 头）：**
```yaml
---
name: agent-name                 # 调用名（/agent-name）
description: 一句话说明用途      # 显示在补全列表中
tools:                           # 该 agent 可用的工具（可选）
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - Write
---
```

**Body（Markdown 正文）：**
- Agent 的角色定义
- 职责（Responsibilities）
- 规则（Rules）
- 输出格式（Output Format）

### 6.3 调用方式

在 Claude Code 对话中输入 `/` 触发 agent 选择：

```
/metis              分析这个需求的真实意图
/prometheus         为这个功能制定实现计划
/momus              审查这个计划
/explore            搜索这个函数的调用链
/oracle             分析这个 bug 的根因
/systematic-debugging  系统调试这个测试失败
/sisyphus           拆解这个复杂任务
/hephaestus         实现这个已确认的功能
/sisyphus-junior    修复这个简单 bug
/atlas              整理这个变更的文档
/brainstorming      探索这个新功能的设计
/multimodal-looker  分析这张设计稿
/ai-code-acceptance 验收这段 AI 生成的代码
```

### 6.4 Agent 间调用

Agent 可以调用其他 Agent。例如 sisyphus 的 workflow 中定义了：

```
1. 如果需求不清楚，先调用 metis
2. 如果需要计划，先调用 prometheus
3. 如果计划复杂，交给 momus 审查
4. 如果需要定位代码，调用 explore
5. 如果涉及复杂架构，调用 oracle
6. 如果计划已确认，交给 hephaestus 实现
7. 如果只是小任务，交给 sisyphus-junior
```

### 6.5 添加新 Agent

1. 在 `.claude/agents/` 下创建 `agent-name.md`
2. 编写 frontmatter + 角色定义
3. 在 `docs/claude/project-standard-stable.md` 的 Agent 总览表中注册
4. 在决策树中补充调用场景

## 7. 质量门禁

### 7.1 提交前必须检查

```bash
make lint          # ruff 检查
make typecheck     # pyright 类型检查
make test          # pytest 测试
```

### 7.2 高风险变更门禁

以下变更必须通过 `ai-code-acceptance` 审查：

- 修改 `src/config.py`（全局配置）
- 修改数据库迁移文件
- 修改认证/授权相关代码
- 修改 CI/CD 配置
- 新增外部依赖
- 修改生产部署脚本

### 7.3 测试门禁

- 新功能必须有测试覆盖
- Bug 修复必须先有失败测试，修复后测试通过
- 不得删除已有测试（除非测试本身已过时）

## 8. 常见错误

| 错误 | 正确做法 |
|------|---------|
| 跳过 metis 直接开始实现 | 需求模糊时必须先调用 metis |
| prometheus 跳过测试计划 | 每个计划必须包含测试方案和回滚方案 |
| momus 只给泛泛建议 | 必须指出具体问题，给出通过/不通过结论 |
| explore 修改代码 | explore 只读搜索，不修改 |
| oracle 直接给出修复 | oracle 只分析不修复 |
| sisyphus 自己执行全部代码 | sisyphus 拆解+委派，hephaestus 负责深度实现 |
| hephaestus 跳过测试 | 必须补充或更新测试 |
| 3 次修复失败后继续尝试 | 停止，质疑架构，与人工讨论 |

## 9. 快速参考

### 典型任务应该调用的 Agent

| 任务类型 | 推荐 Agent |
|---------|-----------|
| "帮我实现 X 功能"（需求清楚） | prometheus → momus → hephaestus |
| "帮我实现 X 功能"（需求模糊） | metis → prometheus → momus → hephaestus |
| "这个测试失败了" | systematic-debugging |
| "这段代码为什么不对" | oracle / systematic-debugging |
| "搜索 Y 函数的调用链" | explore |
| "审查这个 PR" | ai-code-acceptance |
| "整理一下这次变更" | atlas |
| "按这个设计稿实现页面" | multimodal-looker → prometheus → hephaestus |

### 命令速查

```bash
# 启动后端
source .venv/bin/activate && uvicorn src.api:app --reload --port 8001

# 启动前端
cd web && npm run dev

# 检查
make lint
make typecheck
make test

# 提交前全量检查
make ci
```
