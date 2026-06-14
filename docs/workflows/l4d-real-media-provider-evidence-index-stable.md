---
title: L4D 真实媒体 Provider 证据索引
doc_type: workflow
module: ai-video-2.0
topic: l4d-real-media-provider-evidence-index
status: stable
created: 2026-06-13
updated: 2026-06-13
owner: self
source: human+ai
---

# L4D 真实媒体 Provider 证据索引

## 当前结论

截至 2026-06-13，L4D 已完成到 S2 bounded media + frontend read-only readback：

- `L4D-5Y`：一次 S2 bounded media provider smoke 通过，只到 `seedance_clips` 后停止。
- `L4D-5Z`：同一批 S2 bounded media 产物在 `/api/portfolio` 与 `/library?tab=materials` 只读回归中可见。
- 产物边界：tenant-scoped `pending_review`，matching `final_work=0`。
- 安全边界：不发布、不 delivery acceptance、不写 approved brand token。

该结论不能外推为 S2 full media/final assembly，也不能外推为 S1/S3/S4/S5 media generation。

权威执行口径仍以 [Production E2E Token Smoke Runbook](../runbooks/production-e2e-token-smoke.md) 和 [AI Video Project 2.0 E2E 测试计划](ai-video-project-2-0-e2e-test-plan-stable.md) 为准。

## 收口证据包

| 阶段 | 类型 | 判定 | 主证据 | 关键事实 |
|---|---|---|---|---|
| `L4D-5X-sync-prep` | production sync / no-provider | passed | `tmp/debug/l4d5x-final-summary-20260613133623.json` | 只同步 `src/skills/keyframe_images.py`；health、hash、import/introspection、6 分钟 no-submit/provider log gate 均通过 |
| `L4D-5X-post-sync` | container contract / no-provider | passed | `tmp/debug/l4d5x-post-sync-contract-summary-20260613135041.json` | mocked `SkillRegistry.execute`；`_max_shots=1`；正常与 fallback 路径都只生成 1 张 keyframe；fallback 只写 `/tmp` |
| `L4D-5Y` | production provider smoke | passed | `tmp/debug/l4d5y-final-summary-20260613132543.json` | 1 次 `/api/scenario/s2` submit；1 个 poyo image job；1 个 poyo Seedance job；provider/backend retry `0` |
| `L4D-5Y` | provider-boundary log gate | passed | `tmp/debug/l4d5y-provider-boundary-gate-20260613132543.json` | 无 fallback text-to-video、TTS、thumbnail、assemble、media_quality_audit、gate candidate、`final_work`、publish、delivery、approved brand token |
| `L4D-5Y` | production readback | passed | `tmp/debug/l4d5y-readback-20260613132543.json` | keyframe 与 clip 均位于 `tenants/momcozy-marketing/pending_review/l4d5s_s2_bounded_keyframe_20260613132543/` |
| `L4D-5Z` | frontend/library read-only regression | passed | `tmp/debug/l4d5z-final-summary-20260613135315.json` | `library-portfolio.prod.spec.ts` 3 tests passed；视频/keyframe 可见；poster cache 只作为 `thumbnail_path` |
| `L4D-5Z` | read-only backend log gate | passed | `tmp/debug/l4d5z-refined-log-gate-20260613135315.json` | backend 仅观察到 `/portfolio/` GET；non-GET `0`；forbidden hits `{}` |

## 已验证边界

| 边界 | 当前状态 |
|---|---|
| scenario submit ceiling | `L4D-5Y` 为 1 次 `/api/scenario/s2` submit |
| provider job cap | `image=1`、`video=1` |
| provider/backend retry | `0` |
| artifact disposition | `pending_review` |
| tenant scope | `momcozy-marketing` |
| bounded stop point | `seedance_clips` |
| final work | matching `final_work=0` |
| publish / delivery | 未执行，且日志 gate 为 0 |
| approved brand token write | 未执行，且日志 gate 为 0 |
| temp production key | run 后撤销，post-revoke auth 返回 401 |

## 不得外推的结论

- 不得声明 S2 full media/final assembly 已通过。
- 不得声明 S1/S3/S4/S5 media generation 已通过。
- 不得声明 TTS、thumbnail、assemble、media_quality_audit 已通过。
- 不得声明 S1 gate、S1 step-by-step 或完整 `@token-smoke` suite 已通过。
- 不得声明商业交付、delivery acceptance、publish allowed 或 approved brand token 可写。

## Read-Only Guard 固化

正式 read-only log gate：

```bash
python scripts/production_readonly_log_gate.py \
  --backend-log tmp/debug/<run>-backend.log \
  --summary tmp/debug/<run>-summary.json \
  --output tmp/debug/<run>-readonly-log-gate.json
```

脚本边界：

- 允许：`GET /portfolio`、本地 `127.0.0.1 /health`、`rendering:3001/health`。
- 禁止：外部 `/api/admin/auth/session`、`/api/health`、`/health`、`/api/media`、scenario/Fast submit、provider、publish、delivery、`final_work`、approved brand token。

本地回归命令：

```bash
.venv/bin/python -m pytest tests/test_production_readonly_log_gate.py -q
```

## 默认下一步

默认不继续追加 provider 消耗。下一步只做 no-provider 的治理动作：

- 将 read-only guard 继续纳入脚本治理与测试清单。
- 复用 `library-portfolio.prod.spec.ts` 的 bounded target 参数化能力，做未来只读回归。
- 如果要进入 S2 full media 或其他场景 media generation，必须重新定义阶段、预算、submit/job cap、stop-loss 和精确授权。
