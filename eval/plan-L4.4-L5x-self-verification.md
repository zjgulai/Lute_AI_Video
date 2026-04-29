# L4.4 + L5.x 审计自证实施计划

> **目标：** 在关键审计节点（strategy/script/edit/thumbnail）注入 rejection notes 到下一轮执行，并建立每个节点的「审计自证」闭环——节点执行时自我断言 quality floor，输出可追溯的审计链。

---

## 架构决策

### Layer 4.4: Human Rejection Notes Auto-Inject

当人类审查者在 4 个检查点提交 `CHANGES_REQUESTED`（含 `reviewer_notes`），这些 notes 自动注入到被拒绝节点的输入上下文，无需人类手动复述问题。

**注入机制：** `routing.py` 中的 `route_after_*` 函数在检测到 `changes_requested` 时，将 rejection notes 写入 state 的 `rejection_feedback` dict。节点重执行时读取该 dict 并注入到 LLM prompt。

**与 L4.1（audit-driven routing）的区别：** L4.1 在*路由阶段*用 audit score 决定是否跳过 human；L4.4 在*人类拒绝了之后*把 notes 带回去。

### Layer 5.x: 审计自证（Audit Self-Verification）

每个节点的执行结果在被审计之前，**节点自身**输出一个 `self_verification` dict，包含：
- `node_name`: 节点标识
- `output_summary`: 产出的关键指标（script count, score, fields populated）
- `quality_thresholds_met`: bool — 节点自评是否达到最低质量标准
- `verification_details`: 每个 threshold 的检查结果

这个自证被 audit node 读入并作为审计的一个额外 criterion。由此形成：

```
Node → output + self_verification → AuditNode → AuditReport(含 self-verification 评价)
```

---

## 实现计划

### Task 1: State 字段扩展

**Objective:** 添加 `rejection_feedback` 和 `self_verifications` 到 `VideoPipelineState`

**Files:**
- Modify: `src/models/state.py:72-74`

**变更：**
```python
    # ── Telemetry ──
    pipeline_metrics: dict[str, Any]

    # ── Human Rejection Feedback (L4.4) ──
    rejection_feedback: dict[str, str]  # Keyed by node_key, value = reviewer_notes

    # ── Self-Verification (L5.x) ──
    self_verifications: dict[str, dict[str, Any]]  # Keyed by node_name
```

### Task 2: Routing 中注入 rejection notes

**Objective:** 当 `route_after_*` 检测到 `changes_requested` 时，将 `reviewer_notes` 写入 `rejection_feedback`

**Files:**
- Modify: `src/graph/routing.py`

**变更：** 修改 `route_after_strategy` 等 4 个函数——在返回回退节点名称之前，先写入 `rejection_feedback`。

```python
# 在 route_after_strategy 中，返回 "strategy_node" 之前：
rejection_feedback = dict(state.get("rejection_feedback", {}))
review = state.get("human_reviews", {}).get("strategy_review")
notes = ""
if isinstance(review, dict):
    notes = review.get("reviewer_notes", "")
elif hasattr(review, "reviewer_notes"):
    notes = review.reviewer_notes
if notes:
    rejection_feedback["strategy"] = notes
    state["rejection_feedback"] = rejection_feedback
# 同上 for script, edit, thumbnail
```

因为 routing 函数接收 `VideoPipelineState`（TypedDict）并返回 `str`，不能直接修改 dict。方案：**改为在 `_retry_guard` 的同级注入**。实际更干净的方案是：routing 函数只做路由决策，在 `nodes.py` 的 audit nodes 中注入 feedback——因为 audit node 在 `CHANGES_REQUESTED` 之后重新执行，它可以看到 `human_reviews` 中的 notes。

修正设计：**在 strategy/script/editing/thumbnail_audit_node 中注入。** 当 audit node 检测到 `current_step` 表示是 re-entry（如 `strategy_complete` 时再次进入），从 `human_reviews` 读 notes 写入 `rejection_feedback`。

### Task 3: Audit nodes 注入 rejection feedback + 自证收集

**Objective:** 4 个 audit nodes 检测 re-entry 时读 `human_reviews` 写 `rejection_feedback`，同时收集 `self_verifications`

**Files:**
- Modify: `src/graph/nodes.py` — 4 个 audit node 函数

**变更模式（以 strategy_audit_node 为例）：**

```python
@timed_node
async def strategy_audit_node(state: VideoPipelineState) -> dict[str, Any]:
    retry_counts = dict(state.get("retry_counts", {}))
    rejection_feedback = dict(state.get("rejection_feedback", {}))
    self_verifications = dict(state.get("self_verifications", {}))

    is_reentry = state.get("current_step") == "strategy_complete"
    if is_reentry:
        retry_counts["strategy"] = retry_counts.get("strategy", 0) + 1
        # L4.4: inject rejection notes if present
        review = state.get("human_reviews", {}).get("strategy_review")
        if review:
            notes = review.get("reviewer_notes", "") if isinstance(review, dict) else getattr(review, "reviewer_notes", "")
            if notes:
                rejection_feedback["strategy"] = notes

    # L5.x: collect self-verification from previous node's output
    agent = AuditorAgent()
    calendar = state.get("weekly_calendar")
    if not calendar:
        return {"errors": ["No weekly_calendar to audit"]}

    # Build self-verification
    brief_count = len(calendar.briefs)
    platforms = set()
    for b in calendar.briefs:
        for p in b.target_platforms:
            platforms.add(p.value if hasattr(p, "value") else str(p))
    self_verifications["strategy_node"] = {
        "node_name": "strategy_node",
        "output_summary": f"{brief_count} briefs covering {len(platforms)} platforms, week {calendar.week}",
        "quality_thresholds_met": brief_count > 0 and len(platforms) > 0,
        "verification_details": {
            "has_briefs": brief_count > 0,
            "has_platforms": len(platforms) > 0,
            "week_set": bool(calendar.week),
        },
    }

    report = await agent.run_strategy_audit(...)
    ...
    return {
        ...,
        "rejection_feedback": rejection_feedback,
        "self_verifications": self_verifications,
    }
```

同样的模式应用到其他 3 个 audit node。

### Task 4: 自证测试

**Objective:** 为每个 audit node 写自证测试——验证 self_verification 在正常路径和 re-entry 路径都正确生成

**Files:**
- Create: `tests/test_self_verification.py`

**测试范围（8 tests）：**

| Test | 节点 | 场景 | 验证 |
|---|---|---|---|
| test_strategy_self_verification | strategy_audit_node | 正常路径 | brief_count, platforms, thresholds_met |
| test_strategy_self_verification_empty | strategy_audit_node | 无日历 | thresholds_met=False |
| test_script_self_verification | script_audit_node | 正常路径 | script_count, avg_duration |
| test_script_self_verification_empty | script_audit_node | 无脚本 | thresholds_met=False |
| test_edit_self_verification | editing_audit_node | 正常路径 | comp_count, timeline_events |
| test_edit_self_verification_empty | editing_audit_node | 无组合 | thresholds_met=False |
| test_thumbnail_self_verification | thumbnail_audit_node | 正常路径 | variant_count |
| test_thumbnail_self_verification_empty | thumbnail_audit_node | 无缩略图 | thresholds_met=False |

### Task 5: Rejection feedback 注入测试

**Objective:** 验证 rejection notes 在 re-entry 路径正确注入

**Files:**
- Add to: `tests/test_self_verification.py`（或分离文件）

**测试范围（4 tests）：**

| Test | 验证 |
|---|---|
| test_strategy_rejection_injected | strategy_audit_node 在 re-entry 时从 human_reviews 读取 notes 写入 rejection_feedback |
| test_script_rejection_injected | 同上 for script |
| test_edit_rejection_injected | 同上 for edit |
| test_thumbnail_rejection_injected | 同上 for thumbnail |

### Task 6: E2E 自证验证

**Objective:** 完整跑一次 pipeline，验证 self_verifications 在最终 state 中存在且包含所有 16 个节点

**Files:**
- Add to: `tests/test_e2e_pipeline.py`

**测试（1 test）：**
```python
async def test_pipeline_has_self_verifications(self):
    compiled = compile_pipeline()
    state = {...}  # minimal init
    async for event in compiled.astream(state, config):
        pass
    full_state = compiled.get_state(config).values
    assert "self_verifications" in full_state
    assert len(full_state["self_verifications"]) >= 12  # at least all worker nodes
```

### Task 7: 完整回归

```bash
cd /workspace/projects/hermes_evo/AI_vedio && python3 -m pytest tests/ -v --tb=short
```

---

## 质量门槛

每个 task 完成后必须：

1. ✅ 测试通过（该 task 的所有 test）
2. ✅ CI 风格检查不报错（语法）
3. ✅ 不影响现有 236 个测试（完整回归）
4. ✅ `self_verification` 对每个节点有 `quality_thresholds_met` bool
5. ✅ `rejection_feedback` 只在 re-entry 时被写入，首次路径不产生

---

## 文件名和结构总览

| 文件 | 变更类型 | 内容 |
|---|---|---|
| `src/models/state.py` | 修改 | +`rejection_feedback`, +`self_verifications` 字段 |
| `src/graph/nodes.py` | 修改 | 4 个 audit node 注入 rejection + 自证 |
| `tests/test_self_verification.py` | 新建 | 12 tests（8 自证 + 4 注入）|
| `tests/test_e2e_pipeline.py` | 修改 | +1 E2E 自证存在性测试 |
