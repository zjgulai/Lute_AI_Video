---
name: adr-index
description: ADR 索引文档，列出本仓库所有架构决策记录（ADR）的编号、标题、状态与摘要。当寻找特定决策、做新决策前查重、或新加 ADR 时使用。
---

# Architecture Decision Records

记录"为什么这样做"的决策。每个 ADR 是不可变的历史记录：决策一旦做出就 freeze，新决策开新文件 supersede 旧的。

## 编号约定

- `NNN-kebab-case-name.md`
- 编号严格递增，**不复用、不重排**
- 即使被 Superseded，文件保留作为历史

## 现有 ADR

| # | 标题 | 状态 | 摘要 |
|---|---|---|---|
| [001](./001-dual-runtime.md) | Dual Runtime Strategy | Accepted | Python FastAPI 后端 + Node.js Remotion 渲染服务，通过 HTTP + 共享 volume 通信 |
| [002](./002-two-layer-auth.md) | Two-Layer Auth Architecture | Accepted | 业务接口 `X-API-Key` 无状态 + 管理后台 Cookie session 有状态，两套并行 |
| [003](./003-db-strategy.md) | PostgreSQL First, SQLite Fallback | Accepted | 生产 PG fail-fast，本地 dev / CI SQLite 默认，禁止静默退化 |
| [004](./004-s3-copyright-fingerprint.md) | S3 Copyright Fingerprint Selection | **Accepted: Option D** | 2026-05-17 决议：关闭 S3 viral 提取接口（`S3_VIRAL_EXTRACT_DISABLED=1` 默认）。Pex/Audible Magic/自建均超预算或工期，跳过技术方案，等业务需求重启再评估 |
| [005](./005-poster-extraction-everywhere.md) | Poster Extraction at Every Video Producer | Accepted | 2026-05-17 决议：废弃"靠 pipeline.completed 单一钩子"模型，改为 `ensure_poster()` 在 4 个写 mp4 的代码路径内联调用 + portfolio router backstop，解决 fast_mode 等旁路场景视频卡片黑底问题 |
| [006](./006-c2pa-content-credentials.md) | C2PA Content Credentials for AI-Generated Videos | Accepted | 2026-05-17 决议：采用 CA-issued publisher cert + c2pa-python 在 backend image 内对 AI 生成视频签名，满足 EU AI Act 2026-08-02 provenance 要求 |
| [007](./007-defer-llm-director-planner.md) | Defer LLM Director Planner for Continuity | Accepted | 2026-05-27 决议：continuity 导演层默认保留确定性 `director_profile`，暂不引入 LLM planner；未来只能作为 feature-flagged 增强并带 schema 校验与 deterministic fallback |

## 写新 ADR

1. 复制下方模板（任选一个现有 ADR 即可）
2. 文件名 `NNN-kebab-case-name.md`，编号取目录最大值 + 1
3. 写完 `Status: Proposed`，PR 提交评审
4. 评审通过后改 `Status: Accepted`，merge
5. 后续如果决策被推翻，开新 ADR `Status: Accepted, supersedes #NNN`，把旧 ADR 改 `Status: Superseded by #MMM`

## 模板结构

```markdown
# ADR #NNN — Short Title

| | |
|---|---|
| 状态 | Proposed / Accepted / Superseded by #MMM |
| 日期 | YYYY-MM-DD |
| 决策者 | 工程团队 / 个人名 |
| 影响 | 哪些模块、哪些工作流 |

## 一、Context
为什么需要做决策？背景、约束、痛点。

## 二、Decision
我们决定怎么做？一句话讲清楚。

## 三、当前实现
对应的代码文件、行号、入口函数。带 file:// 链接。

## 四、Consequences
好处 + 代价，必须诚实写代价。

## 五、Alternatives Considered
其他方案 + 为什么拒绝。每个拒绝都要给理由。

## 六、Rollback Plan
如果未来要推翻这个决策，怎么走？

## 七、相关代码
file:// 链接索引。
```

## 不写 ADR 的场景

- 实现细节（变量命名、函数拆分）
- 一次性的 bug 修复
- 三方库版本升级
- 文档/typo 修复

**经验法则**：如果半年后另一个工程师问「为什么这么干」，答案需要超过 1 段话，就值得写 ADR。
