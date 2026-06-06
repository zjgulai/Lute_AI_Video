---
title: AI Video 2.0 最终自证状态
doc_type: workflow
module: ai-video-2.0
topic: final-self-proof
status: stable
created: 2026-06-04
updated: 2026-06-06
owner: self
source: human+ai
---

# AI Video 2.0 最终自证状态

## 结论

AI Video 2.0 已形成一套可审计的商业视频 dry-run 工具层：商业合约、离线质量门禁、provider 信号、prompt compiler、生产任务账本、场景只读注入、prompt preview audit、品牌 token 审核、长视频审计、工具箱图像工具 L2 矩阵、工具级 provider readiness preflight、poyo 公开文档重验、authorized-live 最小样本计划、私有 approval/account readiness 构建器、no-token smoke 启动包与 no-token benchmark 均已有本地测试证据。

当前最高证据等级仍是 `L2-fixture-or-dry-run`。C21-C29 真实 token smoke 前置门禁已完成 no-token 准备，但没有用户逐字授权句、私有 approval record、私有 provider account readiness record 和双确认执行变量，不允许进入 provider 调用。

## Completed Commits

| Scope | Commits |
| --- | --- |
| C1/C2/C5 commercial contract and offline gate | `b83a957` |
| C3/C4 provider signal, prompt compiler, job ledger | `fee6526` |
| C6 read-only scenario injection API/UI | `9137e63`, `68c66db`, `9fa2663`, `45d8c1d`, `33f217e`, `aed6765` |
| C7 longform contract and S3/S4 blueprint/gate | `2b70ee6`, `6f9e082`, `9c51d20` |
| C8 product control panels | `39ee5c9`, `51c84a2`, `257f012` |
| C9 no-token preflight and authorized-live harness guard | `99cfdf1`, `ba1de5f` |
| C10-C14 brand token intake, review, runtime injection, preview, prompt audit | `d953018`, `950c0cc`, `2bdd61b`, `8197d9c`, `68379a7`, `54ee947`, `cb6ca5f` |
| C15 prompt preview audit API and OpenAPI types | `8198496`, `38d6df4` |
| C16 prompt preview audit UI | `ca540e4`, `2b3a3e7` |
| C17 brand review audit bundle and dry-run CLI | `281d8ee`, `e966745` |
| C18 longform audit bundle and fixture coverage | `380e6e2`, `c25a749` |
| C19 no-token commercial benchmark | `0ab0c3c`, `4b1a9b4` |
| C20 backend/frontend dry-run acceptance | `22b976d`, `0cc6800` |
| C21 approval record gate hardening | `1f36f4e` |
| C22 Momcozy S5/toolbox L2 fixture matrix | `8d790fc` |
| C23 toolbox provider readiness preflight | `70f33b7` |
| C24-C29 poyo revalidation, sample plan, private records, no-token smoke packet | `768cd1a`, `74c2d3b`, `52bc8cc`, `5eb655b`, `cbd2268`, `ecbae24`, `890d569` |

Plan source: `docs/superpowers/plans/2026-06-04-ai-video-2-0-remaining-implementation-plan.md`.

## Evidence Grade

- **Current grade**: `L2-fixture-or-dry-run`.
- **No provider calls**: C15-C29 implementation and tests did not call POYO, DeepSeek, SiliconFlow, Seedance, OpenAI, Runway, Kling, Google Veo, or other external generation providers.
- **No approval upgrade**: C21-C29 preflight still requires an approval record with `scope=c21-token-smoke`, exact C21 user authorization statement, provider/model, positive finite budget, current provider revalidation ref, current sample plan ref, private provider account readiness record, `CONFIRM_P2_TOKEN_SMOKE=1`, `RUN_TOKEN_SMOKE=1`, provider keys, non-demo production API keys, job ledger readiness and audit bundle readiness.

## Supported Claims

- The project can represent commercial video requirements as typed contracts and offline gate decisions.
- S1-S5 can expose commercial injection metadata as read-only state without leaking prompt payload or brand asset source body.
- Prompt preview audit can run as a dry-run workflow and expose sanitized audit evidence.
- Brand tokens remain candidate-only until explicit review builds a reviewed generation-scoped bundle.
- S3/S4 longform risk surfaces are represented through timeline, EDL, source rights, caption safe-zone and reframe audit objects.
- The no-token benchmark can summarize readiness and blockers without provider side effects.
- Momcozy S5 and toolbox image-generation samples are represented as L2 fixture refs only: `product-image`, `six-view`, `ecommerce-visual` all target S5 without provider submission, delivery acceptance, publishing, or approved brand token claims.
- Toolbox provider readiness can evaluate C21 approval, API key presence, provider capability, budget stop-loss and `sample_plan.toolbox_tool_ids` without provider side effects.
- poyo public documentation has been revalidated as `L1-public-doc-revalidation` evidence only; it supports model/endpoint/cost assumptions but does not prove key validity, balance or runtime success.
- The authorized-live sample plan is bounded to Momcozy sterilizer 3 image assets + 1 15s vertical image-to-video sample, max 4 provider calls, total budget <= `$3.00`, per-job <= `$2.50`, zero automatic retries, and `pending_review` asset status only.
- Private approval and account readiness builders can create secret-free records under `tmp/` or outside the repo, while rejecting generic confirmations, underfunded account readiness and formal repo output paths.
- The no-token smoke packet and P2 recharge checklist can show the exact authorization sentence, required private records and command preview before any `--execute` path is reached.
- C20 backend and frontend acceptance passed locally: backend target pytest `63 passed`, repo-wide `ruff check src tests scripts` passed, OpenAPI types were up to date, frontend lint/typecheck/Vitest passed with `199` tests.

## Forbidden Claims

- Do not claim commercial production readiness.
- Do not claim provider live smoke has run.
- Do not claim approved brand tokens are available.
- Do not claim candidate brand token ledgers are approved for runtime injection.
- Do not claim customer evidence has been collected.
- Do not claim any generated artifact has delivery acceptance.
- Do not claim publishing is allowed.

## Known Blockers

- **C21 live provider call** is blocked until the user provides the exact authorization statement required by the plan.
- **poyo account readiness** is blocked until an operator manually checks the provider console and creates a private `AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD` without API key text.
- **Provider capability evidence** is public-doc-only for this branch; real key validity, account balance, content moderation and runtime success remain unproven until authorized live execution.
- **Brand data assets** are copied and modeled only as governed assets; runtime use still requires explicit review and scope-bound approval.
- **Longform production** is structurally audited, but real source footage, transcript, EDL, timeline manifest, safe-zone verification and artifact manifest remain needed for live evidence.
- **Delivery and publish gates** intentionally remain locked without human review and acceptance evidence.
- **Toolbox authorized live** remains blocked unless the approval record explicitly lists the exact toolbox tool ids under `sample_plan.toolbox_tool_ids`.

## Next Evidence For L4

To attempt `L4-authorized-live`, the user must first provide this exact statement with concrete values:

```text
我明确授权 C21 运行一次真实 token smoke，允许调用 provider，使用的 provider/model 范围是 poyo/gpt-image-2 + poyo/seedance-2，测试范围是 Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频，预算上限是 $3.00。
```

Then create an approval JSON pointed to by `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD`, create a private `AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD`, generate the no-token smoke packet, set `CONFIRM_P2_TOKEN_SMOKE=1` and `RUN_TOKEN_SMOKE=1`, provide non-demo production API keys plus required provider keys, and run the C21 preflight. Only after the preflight passes should `scripts/p2_recharge_smoke_checklist.py --execute` be used for the tiny provider call.
