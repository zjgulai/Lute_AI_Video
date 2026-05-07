---
title: Claude Code 使用洞察报告(2026-04-07 至 2026-05-07)
doc_type: knowledge
module: claude-code
topic: usage-insights
status: stable
created: 2026-05-07
updated: 2026-05-07
owner: self
source: ai
---

# Claude Code 使用洞察报告

**统计区间**: 2026-04-07 至 2026-05-07
**会话总数**: 85(分析 73)· 消息 575 · 累计时长 257 小时 · 提交 43

---

## 一览(At a Glance)

### 做得好的地方

你在跑一个紧凑的「诊断 → 修复 → 验证 → 提交 → 部署」闭环,而且不怕推 Claude 把这个闭环关上(典型一句:「deploy already」)。把大目标拆成命名波次/阶段(Wave 1/2、V3.2 迭代、Phase 1/2 等),并用「继续」在中断后续上来,让你能在跨多次会话的长任务中保持节奏。其中 **skill card 萃取流水线** 尤其亮眼 —— 你持续把临时工作转成可复用的归档知识,而不是任凭它蒸发。详见《让人印象深刻的工作流》。

### 拖累你的地方

**Claude 这边**: 你想要诊断或限定范围的计划,它却经常直接动手编辑或大范围探索;批量操作(尤其是 sed 重写)两次把文件清空。自我验证也不一致 —— 部署偶尔后端没同步、bug 多轮修复仍然存活。

**你这边**: 长会话放大了上游 API 错误的成本;模糊的开场提示(如「update claude」)会强制多轮澄清才进入正题。

详见《摩擦点》。

### 立即可做的优化

- **Hooks**: PostToolUse/Stop 阶段自动跑类型检查 + 烟测,能拦住空 CSS / 后端未同步这类问题进生产。
- **Plan 模式**: 涉及 3+ 文件的重构或主题迁移,先出计划再动手,你来批准。
- **resume.md 约定**: API 5xx 中断时,「继续」可以从落盘上下文恢复,不用重新摸索。

### 长期值得追的方向

- **自主部署-验证-回滚流水线**: Claude 改完代码 → 跑 E2E → 检测 console/network 回归 → 失败原子回滚。把吃掉了 portfolio 与 UI 迁移会话的 iterate-fix-redeploy 循环消掉。
- **并行 Agent 知识库丰富化**: 8-12 个专长 agent 夜间并发跑,自动抽 skill / 修链接 / 审计图谱,把手工分阶段任务变成自维护图谱。
- **TDD 自治调试**: 从你的 bug 报告写失败 E2E,然后自动循环到全绿。把「session 结束 video preview 仍坏」变成「12 个测试全绿,这是 PR」。

---

## 项目分布(Project Areas)

### 1. 生产 Web 部署 / Bug 修复 — 12 会话

诊断与修复生产问题:nginx 限流(429)、SSL/DNS 配置、连接失败、前端 bug。重度依赖 Bash + Edit 系统化排障,通过 rsync 部署,跨多个级联问题管理 nginx 配置。

### 2. AI 视频/Portfolio 项目开发 — 10 会话

构建 AI 视频生成平台 + portfolio 画廊 + admin panel + GitHub Pages demo。涉及多文件 TypeScript 改动、暗→暖光主题迁移、E2E 测试、API 路由 + demo mode + 视频预览问题修复,Claude 编排前后端联动。

### 3. 知识库 / Skill Card 萃取 — 11 会话

从研究论文中萃取可复用 skill card(自我改进 LLM agent / A/B 测试 / AdaNEN / 个性化文案生成)并归档进结构化知识库。Claude 通过并行 agent 增强、修复死链、审计图谱、提升健康分,同时归档 session 总结。

### 4. VOC 标签词典 / 数据分析 — 8 会话

跨多个版本(V3.2、v3.9)迭代 VOC 标签词典,完成跨 sheet 字段覆盖,产出样式化 HTML 报告给干系人。Claude 处理表格字段补全、Zendesk 覆盖率对比、股票池验证等审计驱动分析。

### 5. 项目组织 / 会话归档 — 9 会话

按统一命名规范重组目录、创建 CLAUDE.md、更新 .gitignore、归档每日产物到带日期 logs。Claude 用于文档编写、README 更新、捕获跨会话可复用工作流。

---

## 你的协作风格

> **关键模式**: 你是一个主动副驾驶 —— 战略性中断,容忍迭代摩擦,期望 Claude 端到端执行,且严格守住你声明的范围。

73 个会话、575 条消息、257 小时(单月)告诉了一切:你是 **重度日常使用者**,把 Claude Code 当作开发流的延伸,不是「派活儿等结果」的顾问。常常进入数小时深潜,而不是发完任务就走。

工具使用 Top:
- **Bash 2,481 次** — 你期望 Claude 执行,不只是建议
- **Read 1,112 / Edit + Write 1,091** — 在活代码上一起迭代

频繁使用「继续」,Top 目标包含 `continue_planned_work` 和 `session_archival`,说明你 **把工作切成阶段性块**,信任 Claude 跨会话维持上下文。

**实用主义 + 中断驱动**:
- 在范围清晰的任务上(Wave 1/2 完成、知识库清理、skill 萃取)放手让 Claude 跑
- 出现漂移立即打断 —— 比如 Claude「broadly explore admin files without integration plan」时你要求「proper wiring plan」,或代码改完没推时你直接「deploy already」
- 容忍模糊与恢复:扛住 sed 损坏文件、API 错误「继续」恢复、多次上游 5xx,不放弃会话
- **低容忍**:Claude 主动做未请求的改动 — 你打断诊断中跑去编辑的会话,拒绝过自动化清理

多语言指令(中英混杂)+ 跨域工作(nginx / WeChat 导出器 / 股票分析 / VOC 词典 / AI skill card)显示你是 **跨基础设施、前端、数据流水线、个人知识系统的通才构建者**。

---

## 让人印象深刻的工作流

### 1. 生产级部署纪律

修复总是配合验证、原子提交、单流程部署。例如:诊断 nginx server 块顶层 limit_req 继承导致 429 → 改配置 → 部署 → 更新 CLAUDE.md,一次完成。步骤跳过你会推回来(「deploy already, what are you waiting for」),把诊断到生产的闭环卡得很紧。

### 2. 多波次接续规划

把大计划拆成命名波次和阶段(Wave 1/Wave 2、V3.2 迭代、Phase 1/Phase 2),用「继续」恰好接上断点。这种结构让你 257 小时的长跑能从 API 错误和上下文限制中优雅恢复,不丢势头。

### 3. Skill Card 萃取流水线

你已建出可复用工作流:把会话蒸馏成 skill card(自我改进 LLM agent / AdaNEN / A/B 实验设计 / 个性化文案生成)→ 自审计 → 同步到知识图谱 → 归档带日期 session 总结。让工作复利累积进不断生长的知识库,而不是任由洞察蒸发。

---

## 摩擦点(Friction)

### 1. API 错误中断任务

上游 API 5xx 与会话终止反复打断执行,被迫用「继续」或压缩手动恢复。建议把长会话拆成更小、可提交的块,降低中断成本。

样例:
- `/init` 创建 CLAUDE.md 在代码库探索完毕但尚未落盘时挂掉,零交付物。
- 知识库 Phase 1 出 6 张卡,Phase 2 被 API 错误打断,被迫手动恢复。

### 2. 没规划/没确认范围就动手

Claude 经常在你想要诊断/计划/收紧范围时直接跳进编辑或宽泛探索。前置说「diagnose only, no edits」或要求进 plan mode 可以避免这类中断。

样例:
- ERR_CONNECTION_CLOSED 诊断中,Claude 跑去改代码,你只想要分析。
- Admin Panel 接线任务,Claude 没出整合方案就开始大范围探索 admin 文件,被你打断要求「proper plan」。

### 3. 验证不充分 + 危险批改

多步任务常带遗留 bug 或要多轮修。Claude 没自审,或用了不安全的批操作。要求显式验收 + 多文件改写时禁用 sed,可大幅降低返工。

样例:
- 批量 sed 两次把 globals.css 清成 0 行,组件文件被清空,被迫 git restore + 全部重写。
- Portfolio 展示走了多轮(错误 API 路径 `/api/api/portfolio` / demo mode 缓存 / 缺 chunk / 限流),会话结束 video preview 还坏着。

---

## 建议(Suggestions)

### 想加进 CLAUDE.md 的内容

#### Deployment Workflow

```md
## Deployment Workflow
- After completing code changes, proactively deploy without waiting for explicit instruction when the task context implies deployment
- Always sync BOTH frontend AND backend changes during deploy; verify with self-check before reporting completion
- Store SSH credentials and deployment paths in a server inventory file for reuse
```

**为什么**: 多次会话出现「deploy already」与后端漏同步导致返工,以及反复要求 SSH 凭证。

#### Safety Rules

```md
## Safety Rules
- NEVER use batch sed commands to modify CSS or component files - they have repeatedly clobbered globals.css and component files to 0 lines. Use the Edit/Write tools instead.
- When user asks for 'diagnosis', 'analysis', or 'review', DO NOT make code edits. Stop after providing the analysis and wait for explicit fix approval.
```

**为什么**: 两次 sed 损坏需要 git restore;诊断会话被未授权的编辑中断过至少一次。

#### Session Archival

```md
## Session Archival
- At end of significant work sessions, archive a summary to logs/YYYY-MM-DD_NNN_会话总结.md covering: deliverables, workflows used, and reuse tips
- Use atomic commits with clear messages and push after each logical unit
```

**为什么**: 4+ 会话把 session archival 列为目标,格式高度一致(logs / 日期目录 / session 总结),固化下来可省掉重复解释。

---

### 推荐试用的功能

#### Custom Skills(自定义 Skill)

通过 slash command 触发的可复用 prompt 模板。
你的 session 归档、skill card 萃取、部署流程是反复发生的,做成 `/archive` `/extract-skill` `/deploy` 命令能省掉每次重新解释的开销。

```bash
mkdir -p .claude/skills/archive && cat > .claude/skills/archive/SKILL.md << 'EOF'
# Session Archive
Create logs/$(date +%Y-%m-%d)_NNN_会话总结.md with:
1. Core deliverables (files created/modified)
2. Workflows used
3. Reuse tips for future sessions
Then git add, commit with message '档案: session summary', and push.
EOF
```

#### Hooks(钩子)

在 pre-commit、post-edit 等生命周期事件自动跑命令。
你之前有一次专门要做 hooks 的会话被打断;`buggy_code(15)` 与 `incomplete_fix` 这类问题用 pre-commit 类型检查/测试就能在部署前拦住。

```json
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "npx tsc --noEmit 2>&1 | head -20"}]
    }]
  }
}
```

#### Headless 模式

从脚本/CI 非交互式跑 Claude。
你做大量重复部署、跨会话累计 43 次提交 — headless 让你把「fix lint errors before deploy」这种动作脚本化,无需开交互会话。

```bash
claude -p "run tests, fix any lint errors, then commit with conventional commit message" \
  --allowedTools "Edit,Read,Bash,Grep"
```

---

### 推荐养成的使用习惯

#### Pre-Deploy 自检清单

声明部署完成前,自动跑核对:前后端是否都同步 + 线上端点是否正常返回。

> 多次部署级联问题(`/api/api/portfolio` 路径错、后端漏推、static chunk 缺失、媒体限流)。标准化 post-deploy 验证(curl + diff + 日志扫描)能更早拦住。Top 摩擦项 `buggy_code(15)` 与 `wrong_approach(13)` 直接被验证关卡 cover。

可复制 prompt:

```
After deploying, run a verification checklist: (1) curl the production endpoint
and confirm 200, (2) diff frontend and backend repos to confirm both synced,
(3) check server logs for 5xx in last 5 min, (4) confirm no rate-limit issues.
Report each item with ✅/❌ before saying 'done'.
```

#### 多文件重构先出计划

3+ 文件的改动(尤其 CSS/主题迁移),先写出计划获批,再动。

> sed 损坏与「admin panel 无计划探索」事故都来自直接动手。28 次 multi-file-changes 成功 vs. 13 次 wrong_approach,显式 plan 模式可以扭转比例。配合「永远不用 sed 改代码文件」的硬规则。

可复制 prompt:

```
Before any refactor touching 3+ files, output a written plan as: (1) files
to modify, (2) exact change per file, (3) verification steps, (4) rollback
plan. Wait for my 'approved' before executing. Use Edit/Write tools only -
never sed for code files.
```

#### API 错误恢复协议

上游 5xx 中断时,落盘进度日志,保证「继续」能精确接上。

> 至少 4 个会话被 API 错误打断中段(CLAUDE.md 没建成、知识图谱审计中断、portfolio 工作截断)。每个里程碑后写持久 log,让恢复变成确定性的,不再依赖会话记忆。

可复制 prompt:

```
After each completed subtask in a multi-step plan, append a line to
.claude/resume.md with: timestamp, task done, next task, key context.
If we hit an error and I say '继续', read .claude/resume.md first to
restore context before proceeding.
```

---

## 远期机会(On the Horizon)

随着 AI 辅助开发从单任务协助走向自主多 agent 编排,你的使用模式有以下放量机会。

### 1. 自主「部署-验证-回滚」流水线

`buggy_code(15)` 与反复部署摩擦(sed 损坏、漏同步后端、video preview bug)预示:自主部署 agent 可以执行改动 → 跑生产 E2E → 通过 console/network 监控自动检测回归 → 失败原子回滚,把「deploy already」这类时刻变成无人值守。这能压掉吃掉了 portfolio 与 UI 迁移的 iterate-fix-redeploy 循环。

**怎么试**: Claude Code Hooks(PostToolUse/Stop) + Playwright MCP 浏览器验证 + 自定义回滚 bash。SubagentStop hook 把测试结果作为部署放行条件。

可复制 prompt:

```
Build me an autonomous deploy-verify-rollback workflow for my web project.
Specifically: (1) Create a .claude/hooks configuration that runs a pre-deploy
snapshot (git rev-parse HEAD + rsync backup), (2) executes deploy via my
existing rsync command, (3) runs a Playwright MCP script that visits the
homepage, key routes, and triggers the video preview + portfolio gallery,
capturing console errors and failed network requests, (4) on any failure,
auto-rolls back to the snapshot and posts a diagnostic report. Also create
a /deploy-safe slash command that orchestrates the full flow. Test it
end-to-end on a trivial CSS change first, then validate it would have
caught the previous video-preview-still-broken regression.
```

### 2. 并行 Agent 知识库丰富化

你那次唯一的并行 agent 会话把 vault 健康分从 96.2 提升到 97.1(三个并发增强器)。想象夜间扇出 8-12 个专长 agent,同时跑 skill 萃取 / 死链审计 / 交叉引用生成 / 元数据校验 / session 归档 / 健康打分,把知识管理从手工分阶段(你的 Phase 2 经常死于 API 错误)变成自维护、持续进化的图谱。

**怎么试**: 单消息内多次 Task 调用获得真实并行,配合 `.claude/agents/` 自定义 subagent。cron 触发 headless Claude Code 让其每夜跑一遍。

可复制 prompt:

```
Design and implement a parallel knowledge-vault enrichment system using
Claude Code subagents. Create specialized agents in .claude/agents/ for:
skill-extractor, broken-link-auditor, metadata-validator, cross-reference-
generator, session-archiver, health-scorer, and tag-dictionary-updater.
Then write a single orchestrator prompt I can run nightly that dispatches
all agents in parallel via the Task tool, aggregates their outputs, resolves
conflicts, commits results atomically, and emits a daily diff report
showing health score delta. Make each agent idempotent and resumable so
API errors mid-run don't lose work. Run it once now against my current
vault and show me the parallelism in action.
```

### 3. TDD 自治调试到全绿

`wrong_approach(13)` + 部分达成(11)— 多来自路径错误(`/api/api/portfolio`)、后端缺改、修复不完全等只在自审时被发现的问题。一个 test-first agent 可以从你的 bug 报告写失败 E2E,然后自动循环:实现 → 跑测试 → 分析失败 → 修订,直到全部通过或它请求帮助。把「video preview 在会话末仍坏」变成「12 个生成测试全绿,PR 在这里」。

**怎么试**: Claude Code bash 工具 + 紧密的 test-runner 循环 + TodoWrite 跟踪失败断言 + SubagentStop hook 强制「测试不绿不退出」。Playwright 或 pytest 做测试底座。

可复制 prompt:

```
I want you to operate in strict test-driven autonomous mode for the next
bug I describe. Workflow: (1) Read my bug report and write 3-7 failing E2E
tests (Playwright for frontend, pytest for backend) that capture the
desired behavior including edge cases I might have missed, (2) commit the
failing tests, (3) enter an iteration loop: implement a fix, run the full
test suite, parse failures, revise—maximum 8 iterations, (4) on each
iteration log a TodoWrite entry with hypothesis and result, (5) only stop
when all tests pass OR you've identified a genuine blocker requiring my
input (then surface a precise question, not a status update). Start with
this bug: [PASTE BUG HERE]. Do not deploy or modify production until I
see the green test run.
```

---

## 趣味结尾

**标题**: 用户在 Claude 完成代码改动但忘了真正部署后,直接来了一句「deploy already, what are you waiting for」。

**原文细节**: 在 footage 页面 bug 修复会话中,Claude 完成多文件改动但没主动部署,被用户来了一记不耐烦的推一把。

---

## 来源

- **数据来源**: `/Users/pray/.claude/usage-data/report.html`
- **生成方式**: Claude Code `/insights` 命令(2026-05-07)
- **本中文版**: 由 Claude Opus 4.7 翻译整理,保留事实、术语、统计数字精确不变
