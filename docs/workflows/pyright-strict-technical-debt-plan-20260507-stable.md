---
title: pyright Strict 模式技术债专项排期
doc_type: workflow
module: governance
topic: type-safety-roadmap
status: stable
created: 2026-05-07
updated: 2026-05-31
owner: self
source: human+ai
---

# pyright Strict 模式技术债专项排期

> **历史语境（2026-05-31）**：本文是 2026-05-07 的 pyright strict 专项排期。当前仓库已进入渐进式类型治理阶段，实际启用规则以 `pyproject.toml` 的 `[tool.pyright]` 为准；近期类型边界收口以 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md) 的 P1-4 记录为准。本文不再作为当前执行计划。

## 1. 现状快照（2026-05-07）

| 指标 | 数值 |
|------|------|
| pyright 配置 | **无**（`pyproject.toml` 无 `[tool.pyright]`） |
| Basic 模式错误 | **244** 处 / 57 文件 |
| Strict 模式错误 | **5,694** 处 / ~85 文件 |
| 错误根因 TOP1 | `dict[str, Any]` + `total=False` → Unknown 级联（97%） |
| 错误根因 TOP2 | 缺失泛型参数（`dict`/`list` 未标注类型） |
| 高风险文件 | `s1_product_pipeline.py`(578) / `s3_remix_pipeline.py`(436) / `s5_brand_vlog_pipeline.py`(435) |

**核心结论**：这不是「代码质量差」，是 `TypedDict(total=False)` + `dict[str, Any]` 的设计选择导致了类型信息在传播中丢失。修复需要**结构性改造**，不是逐行打补丁。

---

## 2. 总体策略：渐进式启用

**禁止大爆炸式改造**。生产环境代码库，每批修改后必须跑通全量测试 + E2E。

策略：从 basic → strict 逐条规则开启，每批聚焦一类错误，改完一批验证一批。

```
Phase A: 配 basic → 修 244 基础错误 ──────────────────────→ 可独立发布
Phase B: MissingTypeArgument + PossiblyUnboundVariable ─────→ 可独立发布
Phase C: total=False → NotRequired ─────────────────────────→ 可独立发布（最大改动）
Phase D: 剩余 strict 规则 ──────────────────────────────────→ 可独立发布
Phase E: CI 接入 + 回归验证 ───────────────────────────────→ 可独立发布
```

---

## 3. 分阶段详细计划

### Phase A — 配置 + 基础错误治理（Week 1，2-3 天）

**目标**：`pyright` basic 模式零错误。

**配置**（`pyproject.toml`）：
```toml
[tool.pyright]
pythonVersion = "3.11"
pythonPlatform = "All"
include = ["src", "tests"]
exclude = ["**/node_modules", "**/migrations"]

# Phase A: basic mode (default)
# 后续阶段逐步启用以下 strict 规则：
# reportMissingTypeArgument = true      # Phase B
# reportPossiblyUnboundVariable = true  # Phase B
# reportUnknownMemberType = true        # Phase C/D
# reportUnknownParameterType = true     # Phase D
# reportUnknownVariableType = true      # Phase C/D
```

**修复内容**（244 错误分类）：

| 错误类别 | 数量 | 修复方式 | 示例 |
|----------|------|---------|------|
| 未绑定变量 | ~41 | `if/else` 分支补全或初始值 | `x = None` 前置 |
| 缺失导入 | ~30 | 补 import 或 `# type: ignore` | `from typing import Any` |
| None 安全调用 | ~12 | `isinstance` guard 或 `assert` | `if state is not None:` |
| Enum 字面量不匹配 | ~15 | 改用 `.value` 或修正字面量 | `Language.EN.value` |
| 多余比较 | ~20 | 删除或修正 | `if x == True:` → `if x:` |
| 其他 | ~116 | 逐条分析 | — |

**验收标准**：
- `pyright src tests` 返回 0 错误
- `make test` 全量通过
- `make lint` 无新增 ruff 错误

**风险**：低。基础错误大多是真正的 bug（未绑定变量、None 安全）。

---

### Phase B — 泛型参数 + 边界变量（Week 2，2-3 天）

**目标**：启用 `reportMissingTypeArgument` + `reportPossiblyUnboundVariable`。

**修复内容**：

| 规则 | 错误数 | 修复方式 |
|------|--------|---------|
| `reportMissingTypeArgument` | ~422 | `dict` → `dict[str, Any]`，`list` → `list[str]`，`Callable` → `Callable[..., Any]` |
| `reportPossiblyUnboundVariable` | ~41 | 补全 `if/else` 分支，或前置默认值 |

**关键文件**（按错误数排序）：
```
s1_product_pipeline.py      ~120  missing type argument
s3_remix_pipeline.py        ~90   missing type argument
s5_brand_vlog_pipeline.py   ~85   missing type argument
routers/scenario.py         ~65   missing type argument
pipeline/gate_manager.py    ~45   missing type argument
skills/media_quality_audit.py ~30 missing type argument
```

**批量修复策略**：
使用正则 + 人工复核：
```python
# 查找: dict\b(?!\[)  → 替换为 dict[str, Any]
# 查找: list\b(?!\[)  → 替换为 list[Any] 或 list[str]（根据上下文）
# 查找: Callable\b(?!\[) → 替换为 Callable[..., Any]
```

**验收标准**：
- 启用两项规则后 `pyright` 返回 0 错误
- 全量测试通过

**风险**：中。泛型标注改动面大（422 处），但修改本身机械、低风险。

---

### Phase C — total=False 治理（Week 3-4，3-4 天）

**目标**：`VideoPipelineState(total=False)` → `NotRequired` 显式标注，或迁移到 Pydantic BaseModel。

**这是最大改动，有两种方案**：

#### 方案 C1：TypedDict + NotRequired（推荐，改动量适中）

```python
# Before
class VideoPipelineState(TypedDict, total=False):
    product_catalog: dict[str, Any]
    scripts: list[Script]
    ...

# After
class VideoPipelineState(TypedDict):
    product_catalog: NotRequired[dict[str, Any]]
    scripts: NotRequired[list[Script]]
    ...
```

**优点**：保留 TypedDict 的轻量特性，LangGraph 兼容。
**缺点**：仍需逐字段标注 `NotRequired`。

#### 方案 C2：Pydantic BaseModel（改动量大，但类型最强）

```python
class VideoPipelineState(BaseModel):
    model_config = ConfigDict(extra="allow")  # 允许增量字段
    product_catalog: dict[str, Any] = {}
    scripts: list[Script] = []
    ...
```

**优点**：类型最强，IDE 提示最好，自动验证。
**缺点**：LangGraph 的 StateGraph 要求 TypedDict；改为 BaseModel 需验证 LangGraph 兼容性。StepRunner 路径不受影响。

**推荐 C1**。理由：
- LangGraph 兼容路径仍需 TypedDict（虽然无生产流量，但代码仍在）
- 改动量可控（30+ 字段，每个加 `NotRequired[]` 包裹）
- 无需改动节点函数签名

**关键改动点**：
1. `src/models/state.py:30` — `VideoPipelineState` 定义
2. `src/graph/nodes.py` — 所有 `state.get("key", default)` 可改为 `state["key"]`（类型已保证存在）
3. `src/pipeline/*.py` — 同理

**验收标准**：
- `reportUnknownMemberType` + `reportUnknownVariableType` 启用后 0 错误
- 5 场景 E2E 测试通过

**风险**：高。触及核心 state 定义，影响所有 pipeline 文件。必须逐文件验证。

---

### Phase D — 剩余 Strict 规则（Week 5，2-3 天）

**目标**：启用所有 remaining strict 规则。

```toml
[tool.pyright]
# Phase D 新增
reportUnknownMemberType = true
reportUnknownParameterType = true
reportUnknownVariableType = true
reportUnknownArgumentType = true
```

**预计新增错误**：~200-300（主要是函数参数无类型、返回值未标注）。

**修复策略**：
- 从「高频调用函数」开始：`_serialize`, `_safe_error`, `get_request_api_key`
- 对「内部辅助函数」用 `# type: ignore` 快速跳过（不是核心业务逻辑）
- 对「API 层函数」必须补齐类型（影响 OpenAPI schema）

**验收标准**：
- `pyright --level strict` 或等效全规则启用后 0 错误
- 全量测试 + E2E 通过

**风险**：中。剩余错误分散，但单处改动小。

---

### Phase E — CI 接入 + 回归（Week 5 末尾，1-2 天）

**目标**：类型检查成为 CI 门禁。

**改动**：
1. `Makefile` 新增 `make typecheck` 目标
2. `.github/workflows/ci.yml` 新增 pyright 步骤
3. `CLAUDE.md` 更新开发规范：「所有新代码必须通过 pyright basic」

```makefile
# Makefile 新增
typecheck:
	pyright src tests

ci: lint typecheck test
```

**验收标准**：
- CI 绿（lint + typecheck + test）
- 新 PR 若引入 pyright 错误，CI 自动 block

**风险**：低。纯流程改动。

---

## 4. 时间线汇总

| 阶段 | 内容 | 工作日 | 周次 | 可独立发布 |
|------|------|--------|------|-----------|
| A | 配置 + 244 基础错误 | 2-3 | W1 | ✅ |
| B | 泛型参数 + 边界变量 | 2-3 | W2 | ✅ |
| C | total=False → NotRequired | 3-4 | W3-W4 | ✅ |
| D | 剩余 strict 规则 | 2-3 | W5 | ✅ |
| E | CI 接入 + 回归 | 1-2 | W5 | ✅ |
| **合计** | | **10-15** | **5 周** | |

---

## 5. 资源与依赖

### 前置条件
- [ ] pyright 安装：`pip install pyright` 或 `npm install -g pyright`
- [ ] 每个 Phase 开始前创建独立分支：`git checkout -b feat/pyright-phase-X`
- [ ] 每个 Phase 结束后 PR review + 合并

### 与其他工作的冲突
| 冲突项 | 缓解 |
|--------|------|
| 业务功能开发（新 scenario / 新 skill） | Phase A/B 期间可并行；Phase C 建议冻结 pipeline 相关改动 |
| 生产 hotfix | hotfix 优先，pyright 工作暂停 |
| 多语言重新上线 | 若未来重新引入 ES/FR/DE，需在 pyright 配置中排除相关 prompt 文件 |

### 建议排期
- **批次 1**：Phase A + B（W1-W2，~5 天）— 可穿插在业务迭代中
- **批次 2**：Phase C + D + E（W3-W5，~7 天）— 建议集中窗口，减少冲突

---

## 6. 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| pyright 错误数 | 5,694 | 0 |
| 类型覆盖率 | ~40%（估算） | >90% |
| CI 类型检查门禁 | 无 | 有（`make ci` 包含 `make typecheck`） |
| 新 PR 类型错误率 | 无法统计 | <5%（CI block） |

---

## 7. 不做事项（明确边界）

- ❌ 不改前端 TypeScript 类型（独立排期，用 tsc --strict）
- ❌ 不迁移 LangGraph 到 BaseModel（T4.4 已决定保留 LangGraph 兼容层）
- ❌ 不修复第三方库的类型 stub（如 langgraph 内部类型问题，用 `# type: ignore`）
- ❌ 不追求 100% 类型覆盖率（内部脚本 / 一次性工具允许 `# type: ignore`）

---

**文档生效日期**: 2026-05-07
**下次复核日期**: Phase A 完成时（预计 2026-05-14）
