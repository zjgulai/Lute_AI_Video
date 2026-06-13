---
title: AI Video Project 2.0 E2E 测试计划
doc_type: workflow
module: ai-video-2.0
topic: e2e-test-plan
status: stable
created: 2026-06-06
updated: 2026-06-13
owner: self
source: human+ai
---

# AI Video Project 2.0 E2E 测试计划

## 目标

在模型/API key 配置控制面完成后，建立一条可审计的端到端测试链路。默认不触发真实 provider，不消耗 poyo 额度，不把 dry-run 或 fixture 结果声明为商业交付完成。真实 provider E2E 只在用户再次明确授权、充值完成、环境门禁通过后执行，并拆成两段：后端/provider 受控提交，以及前端只读验证产物在作品库和媒体预览中可见。

## 2026-06-11 正式执行口径

本计划进入“真实 provider + 前后端联动”阶段，但执行默认仍 fail-closed。

首轮正式 E2E 不直接运行完整 `RUN_TOKEN_SMOKE=1 npm run e2e:prod`。原因是当前 production `@token-smoke` 覆盖 Fast Mode、S1 gate、S1 step-by-step、S2-S5 submit/status，范围大于本阶段要验证的 Momcozy 消毒器 3 图 + 1 视频样本包。首轮执行采用更小的两段式路径：

| 阶段 | 证据等级 | 是否调用 provider | 目标 | 默认状态 |
|---|---|---:|---|---|
| `L0/L1` 本地质量门 | L0/L1 | 否 | 保证代码和 UI 控制面可运行 | 必跑 |
| `L2` no-token preflight | L2 | 否 | 验证授权、预算、provider readiness、payload 边界 | 必跑 |
| `L3` 生产非 token E2E | L3 | 否 | 验证生产路由、认证、只读 API、设置页、作品库 | 必跑 |
| `L4A` authorized-live provider smoke | L4 | 是 | 只提交 Momcozy 消毒器 3 图 + 1 视频样本包 | 授权后执行 |
| `L4B` frontend read-only artifact E2E | L3/L4-readback | 否 | 验证 L4A 产物进入 `pending_review` 并在 `/library` 可见 | L4A 后执行 |
| `L4C-1` Fast Mode minimal token smoke | L4 | 是 | 只验证 `fast-mode-submit.prod.spec.ts` 的 Fast Mode submit/status | 2026-06-11 已执行；暴露 submit-count / artifact-disposition 守卫缺口 |
| `L4C-1R` Fast Mode single-submit token smoke | L4 | 是 | 只验证拆分后的 single-submit spec | 2026-06-11 授权 retry 已通过；产物进入 tenant-scoped pending_review |
| `L4C-2R` S2 no-media after-fix single-submit token smoke | L4 | 是（仅 DeepSeek 文本） | 只验证 `/scenario/s2` + `enable_media_synthesis=false` | 已通过；未触发 poyo/Seedance/TTS/assemble/keyframe |
| `L4C-3` S1 no-media single-submit token smoke | L4 | 否（失败发生在 provider 前） | 只验证 `/scenario/s1` + `enable_media_synthesis=false` | 已执行一次授权 submit；HTTP 500 失败止损 |
| `L4C-3R-prep` S1 config/import gate | L4 | 否 | 只同步 `src/config.py` 并验证 S1 import | 已通过；未运行 Playwright / submit |
| `L4C-3R` S1 no-media after-config-sync token smoke | L4 | 是（DeepSeek 文本；后台 health probe caveat） | 只验证 `/scenario/s1` + `enable_media_synthesis=false` | 业务路径通过；媒体生成执行为 0 |
| `L4C-3H-prep` admin health probe isolation | L4 | 否 | 只同步 admin health probe guard 并观察日志 | 已通过；370 秒窗口无 provider probe |
| `L4C-4` S1 no-media clean-log single-submit token smoke | L4 | 是（仅 DeepSeek 文本） | 复验 `/scenario/s1` + clean-log 6 分钟窗口 | 业务路径通过；执行级 provider 为 0；strict clean-log 因 skill 注册日志失败 |
| `L4C-4R-prep` S1 no-media logging/import hygiene | L4 | 否 | 只同步 no-media S1 import/logging hygiene 并观察 no-submit 日志 | 已通过；370 秒窗口无 provider、media skill 注册或 submit 日志 |
| `L4C-4R` S1 no-media clean-log after-import-hygiene | L4 | 是（仅 DeepSeek 文本） | 复验 `/scenario/s1` + clean-log 6 分钟窗口 | 已通过；单 spec、单 submit、媒体/provider forbidden 计数为 0 |
| `L4C-5` S2 no-media clean-log single-submit | L4 | 是（仅 DeepSeek 文本） | 复验 `/scenario/s2` + clean-log 6 分钟窗口 | 已通过；单 spec、单 submit、媒体/provider forbidden 计数为 0 |
| `L4C-6` S3 no-media clean-log single-submit | L4 | 是（仅 DeepSeek 文本） | 验证 `/scenario/s3` + no-media + clean-log | 已通过；单 spec、单 submit、媒体/provider forbidden 计数为 0 |
| `L4C-7` S4 no-media clean-log single-submit | L4 | 是（仅 DeepSeek 文本） | 验证 `/scenario/s4` + no-media + clean-log | 已通过；单 spec、单 submit、媒体/provider forbidden 计数为 0 |
| `L4C-8R` S5 no-media after-timeout-fix single-submit | L4 | 是（仅 DeepSeek 文本） | 验证 `/scenario/s5` + no-media + clean-log | 已通过；单 spec、单 submit、媒体/provider forbidden 计数为 0 |
| `L4D` real media provider staged smoke | L4 | 是 | image-only → video-only → image+video → S2 bounded media pilot → frontend readback | 已通过至 `L4D-5Z`；S2 bounded media 只验证到 `seedance_clips`，产物保持 tenant-scoped `pending_review` |
| `L4C-2+` production `@token-smoke` slices | L4 | 是 | S1/S2-S5/gate/media/poster/quality 等更宽场景联测 | 暂缓；需重新授权 |

### 执行决策

- **允许制定计划**：已允许。本文件是正式计划。
- **允许执行 no-token 检查**：允许，最高只到 `L2` / `L3`。
- **允许执行真实 provider**：未授权前禁止。必须满足“再次授权 + 私有 records + funded provider key + 执行开关”组合。
- **允许声明通过**：只有相应阶段证据存在时才允许声明；`L2`/`L3` 不能替代 `L4A`，`L4A` 也不能替代 delivery acceptance 或 publish allowed。

### 当前本地基线

截至 2026-06-11，真实 provider E2E 计划前的本地前端质量门已恢复：

```bash
cd web
npm run lint
npx tsc --noEmit -p tsconfig.json
npm test -- --run   # 52 passed test files, 234 passed tests
npm run build
```

后端最近一次全量基线为 `.venv/bin/python -m pytest tests -q`：`1888 passed, 11 skipped, 12 deselected`。该基线证明本地质量门恢复，不证明 provider runtime 成功。

### 2026-06-11 Phase A/B 执行结果

[事实] Phase A 本地质量门已复跑通过：

- `.venv/bin/python -m pytest tests -q`：`1888 passed, 11 skipped, 12 deselected`。
- `make lint`：通过，实际执行 `.venv/bin/python -m ruff check src tests scripts`。
- `cd web && npm run lint`：通过。
- `cd web && npx tsc --noEmit -p tsconfig.json`：通过。
- `cd web && npm test -- --run`：`52 passed` test files、`234 passed` tests。
- `cd web && npm run build`：通过，24 个 app routes 完成生成。
- `git diff --check`：通过。

[事实] Phase B no-token preflight/readiness 已复跑通过：

- `scripts/p2_recharge_smoke_checklist.py`：dry-run，未执行命令，列出缺失 production key、provider key、approval/account readiness records、execute flags 和 private poyo payloads。
- `scripts/build_authorized_live_smoke_packet.py --include-preflight`：`evidence_level=L2-fixture-or-dry-run`，`no_provider_call=true`，`provider_call_allowed=false`，`blocked=true`。
- `scripts/build_authorized_live_test_plan_readiness_report.py`：`ready_for_test_plan_discussion=true`，`ready_for_live_execution=false`，`provider_call_allowed=false`。
- `.venv/bin/python -m pytest tests/test_token_smoke_preflight.py tests/test_authorized_live_smoke_packet_builder.py tests/test_authorized_live_test_plan_readiness_report.py tests/test_p2_recharge_smoke_checklist.py -q`：`36 passed`。

[事实] Phase C 正式非 token E2E 已使用非 demo `PLAYWRIGHT_API_KEY` 执行通过：`RUN_TOKEN_SMOKE=0 .venv/bin/python scripts/production_non_token_e2e_check.py --execute`，结果 `50 passed, 4 skipped`。当时 4 个 skipped 中包含 `library-portfolio` 的 2 个 L4B 待审素材回读检查；原因是生产 `creation_intermediate` 当时没有 `pending_review` 资产，不能把 L4A/L4B 证据缺口降级成前端失败。

[事实] 已新增 Phase C fail-closed 辅助入口 `scripts/production_non_token_e2e_check.py`。默认 dry-run 只输出 readiness；`--execute` 只在非 demo `PLAYWRIGHT_API_KEY` 存在且 `RUN_TOKEN_SMOKE` 未启用时运行 `npm run e2e:prod`，并强制子进程 `RUN_TOKEN_SMOKE=0`。

[事实] L4A 授权前 no-token readiness 已复跑：`tmp/outputs/l4a-authorized-live-smoke-packet-20260611-152010.json` 和 `tmp/outputs/l4a-test-plan-readiness-20260611-152010.json` 均已生成；`ready_for_test_plan_discussion=true`，`ready_for_live_execution=false`，`provider_call_allowed=false`。随后用户给出精确授权，并完成真实 provider smoke：`tmp/outputs/l4a-authorized-live-provider-smoke-20260611-152953.log` 和 `tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json` 记录 `status=submitted`、`provider_call_executed=true`、`blocked_reasons=[]`。

[事实] L4B 生产只读回读已完成：`tmp/outputs/l4b-production-readback-20260611-160827.json` 记录 `provider_call_executed=false`、`pending_review_count=4`、`final_work_total=0`、`final_work_smoke_assets=0`，生产 Playwright `web/e2e/production/library-portfolio.prod.spec.ts` 在 `RUN_TOKEN_SMOKE=0` 下结果为 `2 passed`。

[判断] 当前可声明的最高证据为：本地质量门和 no-token readiness 达到 `L2-fixture-or-dry-run`，Phase C 生产非 token E2E 达到 `L3-production-read-only`，Momcozy 消毒器样本包达到 `L4-authorized-live` provider smoke，并完成 `L4B` 生产只读回读。`L4C-4R`、`L4C-5`、`L4C-6`、`L4C-7`、`L4C-8R` 可声明 S1-S5 no-media clean-log single-submit token smoke 通过。`L4D-5Y` 可声明 S2 bounded media pilot 在生产真实 provider 下通过到 `seedance_clips`：一次 `/api/scenario/s2` submit、1 个 poyo image job、1 个 poyo Seedance job、provider retry 为 0、产物进入 tenant-scoped `pending_review`，且 `final_work=0`。`L4D-5Z` 可声明该批 S2 bounded media 产物在 `/api/portfolio` 与 `/library?tab=materials` 只读回归中可见。仍不能声明 S1/S3/S4/S5 media generation、S2 full media/final assembly、S1 gate/step-by-step、完整 token suite、商业交付、delivery acceptance、publish allowed 或 approved brand token。

## 证据边界

| 层级 | 范围 | Provider 调用 | 可声明结论 |
|---|---|---:|---|
| L0 | lint、typecheck、unit、build | 否 | 代码结构和类型约束通过 |
| L1 | 本地 UI 与配置页渲染 | 否 | 配置入口和前端状态可用 |
| L2 | fixture、dry-run、mock provider、preflight | 否 | 工作流契约、门禁和账本可审计 |
| L2.5 | provider 公开文档重验 | 否 | 当前模型、端点、价格有公开文档依据，但不证明 key/余额/runtime 成功 |
| L3 | 生产非 token smoke、生产非 token Playwright | 否 | 生产路由、认证、静态页面、非生成路径可用 |
| L4A | 授权真实 provider smoke | 是 | 局部 provider 提交链路可用，不等于前端展示或商业交付完成 |
| L4B | provider 产物前端只读回读 | 否 | 已生成产物可通过后端 API 和前端作品库被只读查看，不等于交付验收 |
| L4D isolated media | 单 image、单 video、1+1 paired provider smoke | 是 | provider-backed image/video 基础链路可用，产物留在 tenant-scoped `pending_review` |
| L4D S2 bounded media | S2 单场景 bounded media pilot 到 `seedance_clips` | 是 | S2 的最小真实媒体链路可用，不等于 full media、final assembly、publish 或 delivery |
| L4D frontend regression | S2 bounded media 产物只读回读 | 否 | `/api/portfolio` 与 `/library` 可读该批 pending_review 产物，poster cache 不作为独立素材卡片 |

C1-C8 最高证据等级仍保持 L2。C9 在用户明确授权并满足双确认后，可将受控样本路径切到 `L4A`；截至 `2026-06-11`，Momcozy 消毒器 3 图 + 1 视频样本已完成两次 scoped `L4-authorized-live` 执行（均保持 pending_review 边界）。后续 provider 复跑仍需重新授权、重新生成私有 records、重新固化证据包。

## 生产模型和 Key 盘点

### 当前生产主链路

| 类别 | Provider | 关键 env | 默认模型/用途 | 测试策略 |
|---|---|---|---|---|
| 文本/推理 | DeepSeek | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL`, `DEFAULT_LLM_PROVIDER` | `deepseek` 为默认文本提供方；Fast Mode 会降到低延迟 chat 模型 | L2 只验证配置注入；L4A 才允许真实调用 |
| 图像生成 | poyo.ai | `POYO_API_KEY`, `POYO_API_BASE_URL`, `POYO_IMAGE_MODEL` | GPT image 类模型，经 poyo 接入 | L2 验证 prompt hash 和 job ledger；L4A 小样本 |
| 视频生成 | poyo.ai | `POYO_API_KEY`, `POYO_API_BASE_URL`, `POYO_VIDEO_MODEL` | Seedance 视频生成 | L2 禁止真实调用；L4A 只跑最小样本 |
| TTS | SiliconFlow CosyVoice | `SILICONFLOW_API_KEY`, `SILICONFLOW_API_BASE`, `COSYVOICE_MODEL`, `COSYVOICE_VOICE` | 旁白和音频生成 | L2 验证配置和任务边界；L4C 前另行授权 |
| 后端访问 | Internal API | `API_KEY`, `PLAYWRIGHT_API_KEY` | 后端 API 认证和生产 E2E | L3/L4B 验收必须使用非 demo production key；demo key 或缺 key 只能得到跳过后的部分 smoke |

### 候选或备用链路

| 类别 | Provider | 关键 env | 用途 | 当前测试边界 |
|---|---|---|---|---|
| 视频备用 | Seedance direct | `SEEDANCE_API_KEY` | poyo 外的视频生成备用链路 | 只作为候选配置展示，未进入默认生产路径 |
| 通用多模态 | OpenAI | `OPENAI_API_KEY` | 文本、图像、可能的 future provider | 只做配置和替换候选，不作为当前默认 |
| 通用文本 | Anthropic | `ANTHROPIC_API_KEY` | 文案、审计、长上下文候选 | 只做配置和替换候选 |
| 语音备用 | ElevenLabs | `ELEVENLABS_API_KEY` | legacy TTS | 不参与默认生产 smoke |

### 非模型但会影响端到端的 Key

| 类别 | 关键 env | 用途 | 测试边界 |
|---|---|---|---|
| TikTok 发布 | `TIKTOK_ACCESS_TOKEN` | 分发发布 | C1-C8 不触发真实发布 |
| Shopify | `SHOPIFY_API_KEY`, `SHOPIFY_STORE_URL` | 商品和店铺连接 | 只测配置存在和失败展示 |
| YouTube | `YOUTUBE_API_KEY` | 分发或素材链路 | 不纳入当前 poyo smoke |

配置页面属于运营侧本地控制面，用于选择 provider、填写 key、将 key 以请求上下文传入后端。生产服务器长期 secrets 仍以部署环境变量为准，前端配置不能替代 `.env.prod` 或 secrets 管理。

## 测试分层

### L0 本地静态和单元检查

目的：证明配置页和 2.0 工具箱相关代码没有破坏现有构建。

固定命令：

```bash
cd web
npm run lint
npx tsc --noEmit -p tsconfig.json
npm test
npm run build
cd ..
git diff --check
```

通过标准：

- `SettingsPanel` 配置页测试覆盖 provider 列表、key 保存、清空、masked 展示。
- `api.ts` 测试覆盖 provider key 注入，不把空 key 或未启用 provider 注入请求。
- build 不依赖真实 provider key。

### L1 本地 UI 验证

目的：证明用户可以从产品入口进入配置页，并能理解“品牌内容生成及管理引擎”的 provider 配置结构。

检查项：

- `/settings` 能在后端离线时渲染。
- 模型 provider 分类清晰：文本、图像、视频、语音、分发。
- API key 输入框不明文回显已保存 key。
- 没有“生成”“发布”“真实测试”按钮误导用户直接消耗 token。
- 页面视觉和主站一致，不引入独立风格。

### L2 后端 no-token 和 preflight

目的：证明真实生成前的门禁、账本、provider 配置形状正确。

固定命令：

```bash
.venv/bin/python scripts/commercial_token_smoke_preflight.py --pretty
.venv/bin/python scripts/p2_recharge_smoke_checklist.py
.venv/bin/python scripts/build_authorized_live_smoke_packet.py --include-preflight
.venv/bin/python scripts/build_authorized_live_test_plan_readiness_report.py
.venv/bin/python scripts/build_authorized_live_approval_record.py --print-required-statement --approved-by <operator-name> --approval-statement ignored
.venv/bin/python scripts/build_provider_account_readiness_record.py --checked-by <operator-name> --available-credit-usd 3.00 --output tmp/outputs/poyo-account-readiness.json
.venv/bin/python -m pytest tests/test_token_smoke_preflight.py
```

如果相关测试文件不存在或命名变化，先用 `rg "token_smoke_preflight|commercial_token_smoke_preflight" tests src scripts` 定位实际测试入口。

检查项：

- 缺少授权记录时 preflight 必须 blocked。
- 缺少 `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 时必须 blocked。
- demo `API_KEY` 或 demo `PLAYWRIGHT_API_KEY` 不允许进入真实 token smoke。
- `scripts/p2_recharge_smoke_checklist.py --execute` 必须自动执行 preflight；preflight blocked 时不得启动 `smoke.sh` 或 Playwright。
- approval record 必须绑定 `configs/poyo-current-provider-revalidation-contract.json`，否则 provider capability evidence 必须 blocked。
- approval record 必须绑定 `configs/authorized-live-token-smoke-sample-plan-contract.json`，否则 sample plan contract 必须 blocked。
- 私有 approval record 必须由 `scripts/build_authorized_live_approval_record.py` 或等价校验流程生成；泛化确认文本不得提升为 L4 授权。
- 私有 provider account readiness record 必须由 `scripts/build_provider_account_readiness_record.py` 或等价校验流程生成；余额不足或缺失时必须 blocked。
- `scripts/build_authorized_live_smoke_packet.py` 只生成 no-token 启动包和 preflight 投影，不执行真实 smoke，不提升证据等级。
- `scripts/build_authorized_live_test_plan_readiness_report.py` 只证明可以讨论正式测试计划；默认 `ready_for_test_plan_discussion=true` 但 `ready_for_live_execution=false`。
- provider job ledger 只暴露 prompt hash、artifact refs、status，不暴露 prompt payload 或品牌资产原文。
- C1-C8 不生成 approved brand token。

### L2.5 poyo 当前公开文档重验

目的：在不触发 provider 的情况下，确认进入 L4A 前使用的 poyo 模型、端点和成本边界不是旧的 2026-05 矩阵假设。

2026-06-06 已重验的公开文档证据记录在 `configs/poyo-current-provider-revalidation-contract.json`，证据等级为 `L1-public-doc-revalidation`，只支持以下结论：

- poyo 公开 API 文档仍显示 `https://api.poyo.ai`、`/api/generate/submit`、`/api/generate/status/{task_id}` 的异步任务架构。
- poyo 公开模型页仍列出 `seedance-2` / `seedance-2-fast`；`seedance-2` 支持 480p、720p、1080p 与 4-15 秒短片。
- poyo 公开模型页仍列出 `gpt-image-2` / `gpt-image-2-edit`；支持低/中/高质量、1K/2K/4K、单图返回。
- 这不证明 API key 有效、账户余额充足、内容审核会通过、runtime 不限流，也不证明商业交付完成。

第一轮 L4A 样本计划记录在 `configs/authorized-live-token-smoke-sample-plan-contract.json`。该计划已从 Fast+S1 连通性 smoke 收紧为报告对齐的 Momcozy 消毒器资产包：3 张 `gpt-image-2` 图片 + 1 条 `seedance-2` 15 秒 9:16 image-to-video。预算止损为总额 `$3.00`、单任务 `$2.50`、零自动重试。产物只能进入 `pending_review` 素材库，不能写入 approved brand token、delivery accepted 或 publish allowed。

固定命令：

```bash
.venv/bin/python -m pytest tests/test_token_smoke_preflight.py tests/test_poyo_model_matrix_stale_warning.py -q
```

### L3 生产非 token E2E

目的：证明部署后的生产站点、认证、路由、非生成路径正常。

固定命令：

```bash
cd web
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
RUN_TOKEN_SMOKE=0 \
npm run e2e:prod
```

默认 `web/playwright.prod.config.ts` 会跳过 `@token-smoke`。不得设置 `RUN_TOKEN_SMOKE=1`。

2026-06-07（旧基线）非 token 验收基线：使用生产 API key、`RUN_TOKEN_SMOKE=0` 执行后，生产套件为 `50 passed, 2 skipped`。缺少 `PLAYWRIGHT_API_KEY` 或只提供 `ai_video_demo_2026` 时，authenticated production checks 会跳过；该结果只能说明页面级 smoke 可运行，不能作为生产验收通过。
2026-06-08（更新）本地重跑 `npm run e2e:prod`（`PLAYWRIGHT_API_KEY` 与 `API_KEY` 均未设置）结果为 `39 passed, 15 skipped`，新增 `library-portfolio` 断言在无 key 下保持 skip；该结果同样不能作为生产验收通过。
2026-06-11（当前 Phase C）使用非 demo `PLAYWRIGHT_API_KEY` 通过 `scripts/production_non_token_e2e_check.py --execute` 执行，结果为 `50 passed, 4 skipped`。其中 `library-portfolio` 的 2 个 skipped 是证据门禁行为：生产当前没有 `pending_review` 的 `creation_intermediate` 资产，所以 L4B 回读不成立；Phase C 非 token 生产前后端联动成立。
2026-06-07 已完成一次受控 real-smoke（`tmp/outputs/authorized-live-poyo-smoke-rerun-20260607-summary.json`）并落库 `output/pending_review/momcozy_sterilizer_smoke_20260607`，其中 `provider_call_executed=true`、`blocked_reasons=[]`，证据等级 `L4-authorized-live`。
2026-06-11 已完成本轮受控 real-smoke（`tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json`），3 张图片和 1 条 15 秒视频已下载到 `output/pending_review/momcozy_sterilizer_smoke_20260611/` 并生成 `tmp/outputs/pending-review-asset-packet-20260611.json`。随后已同步到生产租户待审目录并部署 portfolio 租户扫描补丁，L4B 只读回读证据为 `tmp/outputs/l4b-production-readback-20260611-160827.json`。

检查项：

- `/`、`/settings`、S1-S5、Fast Mode、资源页可以打开。
- authenticated production checks 必须使用非 demo production key。
- `@token-smoke` 默认跳过，不触发真实 provider。
- 生产错误页和离线状态有明确展示。
- `/api/fast/generate` token path 不在默认 smoke 中执行。

### L4A 授权真实 provider smoke

目的：在用户明确授权后，用最小样本验证 poyo 图像/视频生成链路。

执行前置条件：

- 用户在当前会话明确授权真实 token smoke（首次执行后再次执行需按“再次确认+更新私有 records”流程）。
- poyo 账号已充值，预算和止损阈值明确。
- `API_KEY` 和 `PLAYWRIGHT_API_KEY` 是非 demo production key。
- `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 已配置。
- 私有 approval record 已绑定 `provider_revalidation_ref=configs/poyo-current-provider-revalidation-contract.json`。
- 私有 approval record 已绑定 `sample_plan_ref=configs/authorized-live-token-smoke-sample-plan-contract.json`。
- 私有 provider account readiness record 已确认 poyo 控制台余额覆盖 `$3.00` 样本计划，并且不记录 API key 原文。
- 私有 poyo payload JSON 已放在 `tmp/` 或 repo 外部，并通过 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS` 提供；不得写入正式 docs/configs/src。
- no-token 启动包已生成并复核，确认授权句、样本计划、账户 readiness 环境变量和执行命令 preview 均与 runbook 一致。
- no-token preflight 已通过。
- 生产日志和 artifact 目录可检查。

2026-06-11 执行状态：

- 授权前 no-token readiness 记录仍为 `tmp/outputs/l4a-authorized-live-smoke-packet-20260611-152010.json` 和 `tmp/outputs/l4a-test-plan-readiness-20260611-152010.json`，用于证明 fail-closed 门禁。
- 本轮私有 approval/account readiness/poyo payloads 已生成在 `tmp/outputs/` 或私有配置路径；输出不打印 API key 原文。
- `scripts/p2_recharge_smoke_checklist.py --execute` 已在 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`、`RUN_TOKEN_SMOKE=1` 下执行；日志为 `tmp/outputs/l4a-authorized-live-provider-smoke-20260611-152953.log`。
- 汇总 `tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json` 显示 `status=submitted`、`provider_call_executed=true`、`blocked_reasons=[]`，provider job refs 为 `0K4K8A3DLKREWJQO`、`YH2UB4QFC4H380KL`、`CSWOZOYCVOPARHCD`、`9GUN6SYY41RGODIG`。
- 本地待审素材目录为 `output/pending_review/momcozy_sterilizer_smoke_20260611/`；资产仍为 `pending_review`，`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。
- L4B 已通过：本次素材已同步到生产 `output/tenants/momcozy-marketing/pending_review/momcozy_sterilizer_smoke_20260611/`，`src/routers/portfolio.py` 租户级 pending_review 扫描补丁已最小部署到 Lighthouse 后端；生产 API 回读 `pending_review_count=4`、`final_work_total=0`，生产 Playwright `library-portfolio.prod.spec.ts` 结果 `2 passed`。
- L4C-1 已执行：用户授权只运行 `fast-mode-submit.prod.spec.ts`；`tmp/outputs/l4c-token-smoke-plan-readiness-20260611-162852.json` 显示计划门 `blocked=false`；`tmp/outputs/l4c-fast-mode-token-smoke-summary-20260611-162852.json` 显示 Playwright `3 passed, 1 skipped`，两个 poyo Seedance 任务完成且未观察到 submit retry。注意：该 spec 内含两个 submit 用例，实际 submit 计数为 `2`；Fast Mode 当前产物路径为 `output/fast_mode`，未满足 pending_review-only 存储边界；后续 `L4C-2+` 必须先补 `max_submit_count=1` 与产物处置守卫。
- L4C-1R 首次 guarded run 执行一次授权 submit：`tmp/outputs/l4c-1r-token-smoke-plan-readiness-20260611-170131.json` 显示 no-execute 计划门通过；`tmp/outputs/l4c-1r-fast-mode-single-submit-summary-20260611-170131.json` 显示 `submit_count_observed=1`、`video_provider_submit_executed=false`。任务阻塞于 `/app/output/tenants/default` 权限，未提交 poyo/Seedance video provider；随后只修复 volume 权限，没有追加 submit。
- L4C-1R retry after volume-permission fix 已在用户重新授权后通过：`tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json` 显示 `decision=passed`，Playwright `1 passed (8.8m)`；生产任务 `fast_1781169431_7e4af0b5` 完成，poyo task `T17OTAHIXMPBNYXX` 仅 submit 1 次，`poyo_retrying_submit_count=0`；产物为 `tenant_pending_review`，在 `/api/portfolio` 中是 `creation_intermediate` / `pending_review`，未进入 `final_work`。后续任何第三次 submit 或 `L4C-2+` 必须重新授权。

私有 approval record 生成入口：

```bash
python scripts/build_authorized_live_approval_record.py \
  --approved-by <operator-name> \
  --approval-statement '我授权在生产环境 https://video.lute-tlz-dddd.top 使用 poyo image + poyo Seedance 执行 Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频的真实调用 smoke，预算上限 $3.00，自动重试 0，不发布、不写入正式 brand token，产物只进入待审素材库。' \
  --output tmp/outputs/authorized-live-token-smoke-approval.json

python scripts/build_provider_account_readiness_record.py \
  --checked-by <operator-name> \
  --available-credit-usd 3.00 \
  --output tmp/outputs/poyo-account-readiness.json
```

统一入口：

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD=<private-account-readiness-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

当前 `--execute` 入口会先跑 no-token preflight，再进入 `scripts/authorized_live_token_smoke_harness.py --execute --enable-poyo-http-submitter --pretty`。只有 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`、私有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS` 同时存在时才会接线 provider submitter；执行范围仍只能是本节 3 图 + 1 视频资产包。

C31 已新增 no-token submitter facade contract：`src/pipeline/authorized_live_poyo_submitter.py` 只接受 injected transport，不导入 `PoyoClient`、`httpx`、`POYO_API_KEY` 或 `os.environ`。`tests/test_authorized_live_poyo_submitter.py` 使用 fake transport 证明 job scope、model、视频 reference refs、prompt 不回显和 failure no-retry 边界。该 contract 仍不是真实 provider submitter；进入真实 L4 仍需精确授权、私有 approval/account readiness、生产 key、provider key 与 execute flags 满足后，接线真实 transport。

C32 已新增 no-token submitter factory gate：`build_authorized_live_poyo_submitter()` 默认在未设置 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 时返回 `None`，即使启用该 gate 也必须由调用方注入 transport 和 private payloads，不能从 CLI、环境变量或模块默认值隐式构建真实 provider client。`scripts/authorized_live_token_smoke_harness.py` 仍不接线该 factory，不导入 `PoyoClient`、`httpx` 或 `POYO_API_KEY`。

C33 已新增 no-token poyo submit/status HTTP adapter contract：`AuthorizedLivePoyoSubmitPollTransport` 只使用 injected HTTP client 和 injected authorization token 构造 `/api/generate/submit`、`/api/generate/status/{task_id}` 请求；fake HTTP 测试验证 request body、headers、finished task file refs、token/prompt 不回显、非 finished 或缺 artifact 时失败即停。该 adapter 仍未接线 CLI，也未执行真实 HTTP 请求。

C34 已新增 no-token HTTP submitter assembly gate：`build_authorized_live_poyo_submitter_from_http()` 只在 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 时，把调用方私有注入的 authorization token、HTTP client 和 private payloads 组装成 `AuthorizedLivePoyoSubmitter`。未启用 gate 时返回 `None`；启用后缺任一私有输入都会 fail-closed。`scripts/authorized_live_token_smoke_harness.py` 仍不接线该 helper，因此默认 CLI 仍不能真实调用 poyo。

C35 已新增私有 poyo runtime 接线 contract：`build_authorized_live_poyo_runtime_submitter()` 从 injected env mapping 读取 `POYO_API_KEY`、`POYO_API_BASE_URL` 和 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS`，并只在 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 时组装 submitter。CLI 只在 `--enable-poyo-http-submitter` 且 execute 模式下传入 lazy factory；preflight blocked 或 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1` 缺失时不会构造 submitter。

C36 已统一执行入口为带 `--enable-poyo-http-submitter` 的真实接线路径：`scripts/p2_recharge_smoke_checklist.py --execute`。未满足 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS`、`AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD`、`AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD` 任一项，或 fail-closed 条件触发时，均不会调用 provider。

截至 2026-06-11，该路径已有两次 scoped 真实执行记录。最新一次为 `tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json`：`status=submitted`、`provider_call_executed=true`、`blocked_reasons=[]`、4 条产物均为 `pending_review`（3 图 1 视频）、`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。

真实样本范围：

| 顺序 | 场景 | 样本 | 目的 | 预算策略 |
|---:|---|---|---|---|
| 1 | 工具箱：电商商品图 | 消毒器 45 度主图，白底/浅灰，产品居中约 70% | 形成可入库待审主图素材 | 失败即停 |
| 2 | 工具箱：电商视觉图 | UV 双重消毒卖点图 | 形成 claim-safe 卖点视觉 | 失败后不自动重试 |
| 3 | 工具箱：电商视觉图 | 厨房日常使用场景图 | 形成家庭场景素材 | 失败后不自动重试 |
| 4 | 工具箱：故事版 / 图片驱动视频 | 15 秒 9:16 Hook → 痛点 → UV/烘干卖点 → CTA | 用 3 张图片 refs 生成待审短视频 | 失败后不自动重试 |

失败处理：

- 403 或 key invalid：停止，检查 provider 控制台和部署 env。
- 429 或 quota：停止，不重试，记录额度和速率限制。
- content rejection：保留 provider 返回原因，回到 prompt/gate 修复，不直接换更宽松模型。
- artifact missing：检查 job ledger、对象存储、nginx `/api/assets/` 或 `/media/` 路由。
- state stuck：检查后端日志、pipeline state、任务状态回写，不重复提交同一任务。

### L4B 前后端只读联动验证

目的：在 `L4A` 真实 provider 已经产生待审资产后，用生产前端和后端只读 API 验证产物可被用户路径看到，但不再次触发 provider。

执行前置条件：

- `L4A` 本次执行的 summary JSON 已存在，且 `provider_call_executed=true`、`blocked_reasons=[]`。
- summary 中每个 provider job 都有 `provider_job_id` 或等价 job ref、`artifact_ref` / `media_url` / 本地 pending-review 路径。
- 产物状态仍为 `pending_review`。
- `delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。
- `PLAYWRIGHT_API_KEY` 是非 demo production key。
- `RUN_TOKEN_SMOKE=0`。

后端只读验证命令：

```bash
BASE=https://video.lute-tlz-dddd.top
API_KEY=<production-api-key>

curl -fsS "$BASE/api/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc" \
  -H "X-API-Key: $API_KEY" \
  > tmp/outputs/e2e-portfolio-creation-intermediate-YYYYMMDD.json

curl -fsS "$BASE/api/portfolio/?kind=final_work&limit=500&sort=size_desc" \
  -H "X-API-Key: $API_KEY" \
  > tmp/outputs/e2e-portfolio-final-work-YYYYMMDD.json
```

后端只读验收：

- `creation_intermediate` 中能找到本次 `L4A` 产物 refs 或同一 batch/category 的 `pending_review` 资产。
- `final_work` 中不得出现这些 `pending_review` 资产。
- API 响应不回显 prompt body、API key、provider payload 原文。
- 只读请求不得包含 `POST`、`PUT`、`PATCH`、`DELETE`。

前端只读验证命令：

```bash
cd web
RUN_TOKEN_SMOKE=0 \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/library-portfolio.prod.spec.ts \
  --reporter=list,html
```

前端只读验收：

- `/library?tab=materials` 可见 `Materials` tab。
- 页面存在 `data-kind="creation_intermediate"` 的素材卡。
- 页面存在 `data-review-status="pending_review"` 的素材卡。
- 页面显示 `Pending review` / `待审` badge。
- 测试期间拦截到的 `/api/**` mutation 调用为空。

### L4C 扩展 token Playwright 套件

目的：在 `L4A` 和 `L4B` 都稳定后，再考虑扩展到更宽的前后端 token smoke。

默认不执行。执行前必须重新评估本节风险，因为当前 `@token-smoke` 规格会覆盖 Fast Mode、S1 gate、S1 step-by-step、S2-S5 submit/status，可能创建多个真实任务。

进入 L4C 前先复制并填写 `configs/l4c-token-smoke-plan-template.json` 到 `tmp/outputs/` 或私有路径，再运行 no-execute 计划验证器：

```bash
AI_VIDEO_L4C_TOKEN_SMOKE_PLAN_RECORD=<private-l4c-plan-json> \
PLAYWRIGHT_API_KEY=<production-api-key> \
python scripts/l4c_token_smoke_plan.py --json
```

该脚本只产出 `L2-fixture-or-dry-run` 的结构化 readiness 证据，不执行 Playwright，不调用 provider。只有报告中 `blocked=false` 且人工再次确认后，才允许复制报告里的 command preview 进入真实 L4C 执行。

2026-06-11 `L4C-1` 已按上述门禁执行最小范围：

```bash
cd web
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/fast-mode-submit.prod.spec.ts \
  --reporter=list --retries=0 --workers=1
```

结果：`3 passed, 1 skipped`。证据见 `tmp/outputs/l4c-fast-mode-token-smoke-summary-20260611-162852.json`。这只覆盖 Fast Mode submit/status，不覆盖 S1/S2-S5/gate/media/poster/quality。该 spec 实际触发两个 Fast Mode submit，且 Fast Mode 当前把生成文件落在 `output/fast_mode` 而不是 `pending_review`；后续真实调用前必须在计划验证器或 spec 层增加 `max_submit_count=1` 与 pending_review-only 产物处置约束。

2026-06-11 `L4C-1R` 已补单提交守卫并执行一次：

```bash
cd web
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_MAX_SUBMIT_COUNT=1 \
PLAYWRIGHT_PROVIDER_MAX_RETRIES=0 \
PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/fast-mode-single-submit.prod.spec.ts \
  --reporter=list --retries=0 --workers=1
```

首次结果：执行 1 个测试，1 次 submit，任务 `fast_1781168782_cc749671` 因 `/app/output/tenants/default` 权限失败阻塞于 video provider submit 之前；后续已修复 production volume 权限，但当时没有做第二次 submit。证据见 `tmp/outputs/l4c-1r-fast-mode-single-submit-summary-20260611-170131.json`。

2026-06-11 用户重新授权后执行 `L4C-1R retry after volume-permission fix`，仍只运行 `fast-mode-single-submit.prod.spec.ts`，仍固定 `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`。结果：Playwright `1 passed (8.8m)`；任务 `fast_1781169431_7e4af0b5` 完成，poyo task `T17OTAHIXMPBNYXX` 只出现 1 次 submit，生产日志 `poyo: retrying submit` 计数为 `0`；状态回读显示 `success=true`、`is_stub=false`、`artifact_review_status=pending_review`、`artifact_storage_scope=tenant_pending_review`，文件路径在 `/app/output/tenants/default/pending_review/fast_mode/fast_1781169431_7e4af0b5/`，大小 `1916459` bytes。`/api/portfolio` 只读回读显示目标资产为 `kind=creation_intermediate`、`review_status=pending_review`，且未进入 `final_work`。证据见 `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json`。

当前可声明 `L4C-1R` 最小 Fast Mode single-submit pending_review token smoke 通过。不得把该结果外推为 S1/S2-S5/gate/media/poster/quality 通过；不得声明 delivery acceptance、publish allowed、approved brand token write 或实际 provider 扣费金额。任何第三次 submit 或更宽 `L4C-2+` 必须重新生成 plan、重新跑 validator，并取得新的精确授权。

2026-06-11 已为 `L4C-2` 准备最小扩展 spec：`web/e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts`。该 spec 只允许一次 `/api/scenario/s2` submit，payload 固定 `enable_media_synthesis=false`，并在测试内检查 `PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0` 和 `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review|quarantine`。它的目标是不进入 Seedance/TTS/assemble media generation，但仍可能调用文本 LLM，因此仍属于 L4C token smoke，必须重新授权后执行。

首次 `L4C-2` 已在用户授权后执行并失败止损：`tmp/outputs/l4c-2-s2-no-media-single-submit-summary-20260611-174120.json` 显示 `decision=failed_stopped`。Playwright 在 30s timeout 失败，生产日志显示 S2 no-media 请求仍触发 3 次 poyo `gpt-image-2` submit（task id `78BSCUGXZADGMCUH`、`83WVI2HST7TOLZF0`、`E48NL40OIALQV82N`），未观察到 Seedance 视频日志。发现范围违背后已重启 backend 止损，`09:43:55Z` 后未再观察到 poyo/Seedance/S2 日志；未发现上述 task id 的落盘产物。根因为 S2 no-media 原先只在结果拼装阶段跳过媒体字段，但 `StepRunner.resume()` 仍执行完整 step order 到 `keyframe_images`；修复已最小部署到生产，生产 health 正常。不得声明首次 L4C-2 通过。

用户重新授权后已执行 `L4C-2R` after-fix single-submit：`tmp/outputs/l4c-2r-s2-no-media-single-submit-summary-20260611-095826.json` 显示 `decision=passed`、Playwright `1 passed (11.1s)`、`submit_count_observed_by_spec=1`。生产日志精确计数显示 S2 开始后 `poyo_http_request_count=0`、`poyo_submit_execution_count=0`、`seedance_execution_count=0`、`tts_execution_count=0`、`assemble_execution_count=0`、`keyframe_execution_count=0`，只观察到 2 次 DeepSeek 文本请求和 1 次 `s2: complete (no media synthesis)`。远端 output 只新增 `/app/output/pipeline_states/s2_momcozy_1781172006.json`，媒体路径字段为空。当前只可声明 S2 no-media after-fix 单提交通过；不得外推为 S1/S2-S5/gate/media/poster/quality 通过。

2026-06-11 已为 `L4C-3` 准备 S1 no-media 单提交候选：新增 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，payload 固定 `enable_media_synthesis=false`，只允许一次 `/api/scenario/s1` submit，并检查媒体字段为空。同步修复 S1 no-media 执行层边界：`S1ProductDirectPipeline.run()`、`/scenario/s1`、`/scenario/s1/start` auto 和 unified `/scenario/s1/submit` 均在 `keyframe_images` 之前停止，不再先执行完整 media step order 后隐藏结果字段。用户随后给出精确授权，`tmp/outputs/l4c-3-s1-no-media-token-smoke-plan-readiness-livekey-20260611-101904.json` 显示 `blocked=false`，且 Playwright `--list` 只枚举 1 个测试；第一次 preflight 因生产 `/opt/ai-video/src/pipeline/s1_product_pipeline.py` 与 `/opt/ai-video/src/routers/scenario.py` 未包含本地 no-media 修复而在 live submit 前阻断，证据为 `tmp/outputs/l4c-3-s1-no-media-preflight-blocked-summary-20260611-101904.json`。

用户随后授权 L4C-3 前置最小代码同步：只同步 `src/pipeline/s1_product_pipeline.py` 与 `src/routers/scenario.py`、备份远端原文件、重启 backend、执行 `/api/health` 与 hash verify。`tmp/outputs/l4c-3-production-code-sync-hash-check-after-sync-20260611-102747.txt` 显示两个授权文件本地与生产 hash 均一致，生产 health 为 `ok`。同步成功后只运行 `scenario-s1-no-media-single-submit.prod.spec.ts` 一次，结果 `tmp/outputs/l4c-3-s1-no-media-single-submit-summary-20260611-102747.json` 显示 `decision=failed_stopped`：Playwright 期望 HTTP 200、实际收到 HTTP 500；生产日志根因为 `ImportError: cannot import name 'MAX_CLIPS_PER_DEMO' from 'src.config' (/app/src/config.py)`。失败发生在 provider 前，poyo/Seedance/TTS/assemble/keyframe/DeepSeek 执行态计数均为 `0`，没有第二次 submit。不得声明 L4C-3 已通过或 S1 no-media 生产路径已验证。

用户随后授权 `L4C-3R-prep`，只同步 `src/config.py`、备份远端原文件、重启 backend、执行 `/api/health`、hash verify 和容器 import smoke，不允许运行 Playwright live spec 或任何 submit。`tmp/outputs/l4c-3r-prep-config-sync-import-smoke-summary-20260611-183914.json` 显示 `decision=passed`：生产原文件备份到 `/opt/ai-video/backups/l4c3r-prep-config-20260611-183914/`，本地/远端/容器内 `src/config.py` hash 一致，容器 `import src.pipeline.s1_product_pipeline` 通过，`MAX_CLIPS_PER_DEMO=3`、`MAX_THUMBNAILS_PER_DEMO=2` 可用。重启后的 prep 日志窗口中 DeepSeek、poyo、SiliconFlow 外部 HTTP 计数均为 `0`，poyo/Seedance/TTS/assemble/keyframe 执行计数均为 `0`。更宽 pre-prep 窗口中存在 admin health check 对 provider model/LLM 的历史探测，不能归因到本次 config sync/import smoke。

用户随后授权并执行 `L4C-3R` S1 no-media after-config-sync single-submit token smoke。`tmp/outputs/l4c-3r-s1-no-media-token-smoke-plan-readiness-livekey-20260611-184923.json` 显示 `blocked=false`，只允许 `scenario-s1-no-media-single-submit.prod.spec.ts`，`max_submit_count=1`，`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。执行结果 `tmp/outputs/l4c-3r-s1-no-media-single-submit-playwright-20260611-184923.log` 显示 `1 passed (8.3s)`，生产 `/scenario/s1` 返回 200，label 为 `s1_1781175031_a8117a86`。状态回读 `tmp/outputs/l4c-3r-s1-no-media-state-summary-20260611-184923.json` 显示 `enable_media_synthesis=false`，只完成 `strategy`、`scripts`、`compliance`、`storyboards`、`continuity_storyboard_grid`，`keyframe_images` 及后续媒体步骤保持 pending，所有媒体路径字段为空，未发现近期媒体文件。

本轮 provider 边界不能写成无 caveat 的 clean pass：`tmp/outputs/l4c-3r-s1-no-media-production-provider-counts-refined-20260611-184923.json` 显示 DeepSeek 文本请求 `3` 次，poyo image/video submit、Seedance generation、TTS generation、assemble generation、keyframe generation、gate candidate generation 均为 `0`；但 `/scenario/s1` 返回 200 后，后台 admin health check 产生 poyo `/v1/models` 和 SiliconFlow `/v1/models` GET 探测各 `1` 次。因此本轮可声明“业务路径与媒体生成边界通过，带后台 provider health probe caveat”，不得声明“全日志窗口绝对无 provider-looking 日志”。

已实现并同步 admin provider health checks 隔离：`ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED` 默认关闭外部 provider probe，`run_health_checks()` 对 DeepSeek、poyo、SiliconFlow 返回 `skipped` 而不触发外部 HTTP；Postgres/Remotion 检查保留。测试 `tests/test_admin_health_provider_probe_guard.py` 覆盖默认跳过和显式开启，相关 admin smoke 通过。用户随后授权 `L4C-3H-prep`，只同步 `src/config.py` 与 `src/routers/admin/logs.py`，远端原文件备份到 `/opt/ai-video/backups/l4c3h-admin-health-probe-20260611-222821/`，backend 重启，`/api/health` 返回 `ok`，hash verify 显示本地/远端/容器一致。

`tmp/outputs/l4c-3h-prep-observation-counts-20260611-222821.json` 显示从 `2026-06-11T14:31:16Z` 起 370 秒 no-submit backend 日志窗口内，`scenario_submit_count=0`、DeepSeek/poyo/SiliconFlow 外部 HTTP 计数均为 `0`，poyo submit、Seedance generation、TTS generation、assemble generation、keyframe generation 与 gate candidate generation 均为 `0`；`tmp/outputs/l4c-3h-prep-observation-matches-20260611-222821.txt` 为 0 行。证据摘要见 `tmp/outputs/l4c-3h-prep-admin-provider-health-probe-sync-summary-20260611-222821.json`。

用户随后授权并执行 `L4C-4` S1 no-media clean-log single-submit token smoke。`tmp/outputs/l4c-4-s1-no-media-clean-log-token-smoke-plan-readiness-livekey-20260611-230535.json` 显示 `blocked=false`、只允许 `scenario-s1-no-media-single-submit.prod.spec.ts`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。唯一一次 live run 日志 `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-playwright-20260611-230535.log` 显示 `1 passed (13.4s)`，生产 label 为 `s1_1781190534_6dcf8877`。shell wrapper 在测试完成后因 zsh 无 `PIPESTATUS` 报错，结果已通过 Playwright 日志固化，未重跑 spec，也没有第二次 submit。

`L4C-4` 状态回读 `tmp/outputs/l4c-4-s1-no-media-clean-log-state-summary-20260611-230535.json` 显示 `enable_media_synthesis=false`，媒体路径长度均为 `0`，`final_video_path` 为空，`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`；`tmp/outputs/l4c-4-s1-no-media-clean-log-remote-artifact-search-20260611-230535.txt` 未发现该 label 的媒体或近期 final_work 产物。6 分钟日志窗口 `tmp/outputs/l4c-4-s1-no-media-clean-log-production-provider-counts-20260611-230535.json` 显示 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance execution、TTS execution、assemble execution、keyframe execution、gate candidate generation 均为 `0`。

`L4C-4` 不得写成 clean-log 通过：`tmp/outputs/l4c-4-s1-no-media-clean-log-registration-noise-matches-20260611-230535.txt` 记录 8 行媒体 skill `registered` 日志，包含 `elevenlabs-tts-skill`、`keyframe-images`、`remotion-assemble-skill`、`seedance-video-generate-skill` 等词元。它们不是执行级 provider 调用，但按本轮 clean-log 授权口径仍属于日志污染。证据摘要 `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-summary-20260611-230535.json` 固化 `decision=failed_strict_clean_log_registration_noise`。

`L4C-4` 当时的下一步不是扩大到完整 token suite，而是进入 `L4C-4R-prep`：最小修复 no-media S1 路径的 import/logging hygiene，使媒体 skill 注册日志不出现在 submit 6 分钟窗口。任何修复同步、S1 clean-log 复验、S2-S5、gate、media/poster/quality 或完整 suite 仍需新的 plan、validator 和精确授权。

用户随后授权并执行 `L4C-4R-prep` S1 no-media logging/import hygiene 同步。只同步 `src/pipeline/__init__.py` 与 `src/pipeline/s1_product_pipeline.py`，远端原文件备份到 `/opt/ai-video/backups/l4c4r-prep-s1-logging-20260612-000910/`，backend 已重启，生产 `/api/health` 在同步前、重启后、观察后均返回 `ok`。

`L4C-4R-prep` hash evidence：`tmp/outputs/l4c-4r-prep-hash-verify-20260612-000910.txt` 显示本地、远端宿主机、backend 容器三方一致：`src/pipeline/__init__.py=263d0ca1e868c6f4938de3ad7f5f1a83b71f2bf44659f4db342d4fbe8a7dd92a`，`src/pipeline/s1_product_pipeline.py=623f6ffba96b4a31c31e4116f4cb6b1ab1a6b3378f21a1c1e1d1eed9cda99315`。

`L4C-4R-prep` log evidence：`tmp/outputs/l4c-4r-prep-observation-counts-20260612-000910.json` 显示 370 秒 no-submit backend 窗口内 `/scenario` submit、DeepSeek/poyo/SiliconFlow 外部 HTTP、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration 和媒体 skill `registered` 计数均为 `0`。证据摘要 `tmp/outputs/l4c-4r-prep-s1-logging-import-hygiene-sync-summary-20260612-000910.json` 固化 `decision=passed`。

`L4C-4R-prep` 完成后的当时下一步是申请 `L4C-4R` 同一单 spec clean-log 复验授权：仍只允许 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，`max_submit_count=1`，provider/backend retry `0`，自动重试 `0`，`enable_media_synthesis=false`，禁止 poyo/Seedance/TTS/assemble/keyframe/gate candidate，禁止发布、approved brand token 写入和 delivery acceptance。该复验已在下段完成，不得直接扩大到 S2-S5、gate、media/poster/quality 或完整 token suite。

用户随后授权并执行 `L4C-4R` S1 no-media clean-log after-import-hygiene single-submit token smoke。`tmp/outputs/l4c-4r-s1-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-001.json` 显示 `blocked=false`、只允许 `scenario-s1-no-media-single-submit.prod.spec.ts`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。

`L4C-4R` 执行证据：`tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-playwright-20260612-001.log` 显示 `1 passed (11.7s)`，没有 retry，生产 label 为 `s1_1781229202_7b5148d1`。`tmp/outputs/l4c-4r-s1-no-media-clean-log-observation-counts-20260612-001.json` 显示 370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration、media skill `registered` 和 stop-loss status 均为 `0`。`scenario_s1_submit=2` 是同一次 HTTP 200 的应用日志与 uvicorn access 日志两行，spec 观察 submit 次数为 `1`。证据摘要 `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-summary-20260612-001.json` 固化 `decision=passed`。

`L4C-4R` 完成后的当时下一步不得直接跑完整 token suite。应重新选择一个最小风险切片，例如 S1 no-media 状态只读补证、S2 no-media clean-log 复验、或下一条明确不进入媒体生成的 scenario slice；每一片都必须重新生成 L4C plan、validator 通过，并取得精确授权。S2 no-media clean-log 复验已在 `L4C-5` 完成。

用户随后授权并执行 `L4C-5` S2 no-media clean-log single-submit token smoke。`tmp/outputs/l4c-5-s2-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-002.json` 显示 `blocked=false`、只允许 `scenario-s2-no-media-single-submit.prod.spec.ts`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。

`L4C-5` 执行证据：`tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-playwright-20260612-002.log` 显示 `1 passed (7.2s)`，没有 retry，生产 label 为 `s2_momcozy_1781230204`。`tmp/outputs/l4c-5-s2-no-media-clean-log-observation-counts-20260612-002.json` 显示 370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration、media skill `registered` 和 stop-loss status 均为 `0`。`scenario_s2_submit=2` 是同一次 HTTP 200 的应用日志与 uvicorn access 日志两行，spec 观察 submit 次数为 `1`。证据摘要 `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-summary-20260612-002.json` 固化 `decision=passed`。

2026-06-12 已继续完成 `L4C-6` S3 no-media、`L4C-7` S4 no-media、`L4C-8R` S5 no-media clean-log single-submit token smoke。S3/S4/S5 均只允许一次 submit，payload 固定 `enable_media_synthesis=false`，实际仅触发 DeepSeek 文本调用，poyo、Seedance、TTS、assemble、keyframe、gate candidate 和媒体 skill registered 计数均为 `0`。`L4C-8` 首次因 Playwright test-level 30 秒 timeout 失败，但 backend 已返回 200 且 forbidden 计数为 0；修复 S5 spec timeout 后，用户重新授权 `L4C-8R` 并通过。当前 L4C no-media clean-log 阶段已覆盖 S1-S5，不得把该结果外推为任何媒体生成链路通过。

下一步不得直接跑完整 token suite，也不得直接进入 S1-S5 full media generation。应进入 `L4D` 真实 media provider 阶梯计划，从 image-only、video-only、image+video、frontend readback 逐级授权和验证。

2026-06-12 已执行 `L4D-1` poyo image-only single-job media smoke。执行前新增并使用 `scripts/l4d_image_only_smoke.py` 专用入口，代码层面只允许 `momcozy_sterilizer_main_45_image_authorized_live_fixture` 的 1 次 `gpt-image-2` image job，并拒绝旧的完整资产包 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`。执行证据 `tmp/outputs/l4d-1-image-only-execute-20260612-122336.json` 显示 `status=submitted`、`provider_call_executed=true`、`image_job_count=1`、`video_job_count=0`、`blocked_reasons=[]`、`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。provider 返回了 `media_url`，但本地拉取待审副本时 CDN 返回 403，因此没有进入 `pending_review` 可浏览素材库；已写入受控 quarantine 记录 `tmp/outputs/l4d-1-image-only-quarantine-20260612042615.json` 和 `output/tenants/default/quarantine/l4d_image_only_20260612042615/l4d_image_only_quarantine_manifest.json`。不得把 `L4D-1` 外推为 `L4D-4` frontend readback 或素材库可见。

同日已执行 `L4D-1R` 只读诊断与本地 materialization。`tmp/outputs/l4d-1r-media-url-diagnostic-20260612-123136.json` 显示无新增 submit，poyo status read 返回 HTTP 200、task `finished`、文件 URL 为 `cdn.doculator.org` `.png`。HEAD 和默认 GET 均返回 403；带浏览器 `User-Agent` 的 GET 返回 200 `image/png`，大小 `1431644` bytes。因此根因不是生成失败，而是 CDN 对默认非浏览器请求/HEAD 的访问策略。随后只下载同一个已生成文件，写入 `output/tenants/default/pending_review/l4d_image_only_20260612043209/main_45.png` 和 `tmp/outputs/l4d-1r-pending-review-materialized-20260612043209.json`；本地 portfolio scan 识别为 `category=pending_review`、`kind=creation_intermediate`、`tenant_id=default`、`review_status=pending_review`。这仍不是生产站点 `L4D-4` readback；生产远端同步和 `/api/portfolio` 验证必须另行授权。

同日用户授权 `L4D-4-prep corrected backend-output-volume pending_review sync + production readback`。本轮只同步两个文件到生产 backend 实际 output volume：`/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/default/pending_review/l4d_image_only_20260612043209/`。hash verify 通过，`/api/health` 返回 ok，且 `final_work` 匹配数为 `0`。但 `/api/portfolio` readback 未看到该图，证据 `tmp/outputs/l4d-4-prep-corrected-volume-readback-failed-20260612151907.json` 记录 `decision=failed_readback_tenant_scope_mismatch`。根因是当前非 demo `PLAYWRIGHT_API_KEY` 对应生产 tenant `momcozy-marketing`，而本轮授权同步到 `tenants/default`；portfolio router 会按 auth tenant 过滤，因此该 key 看不到 `tenant_id=default` 资产。下一步必须二选一：授权把同一资产同步到 `tenants/momcozy-marketing/pending_review/...` 并按 `tenant_id=momcozy-marketing` 验证，或提供/授权一个 `tenant_id=default` 的非 demo production key。

随后用户授权并执行 `L4D-4R-prep momcozy-marketing tenant pending_review sync + production readback`。同一两文件同步到 `/var/lib/docker/volumes/lighthouse_backend_output/_data/tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/`，hash verify 通过，`/api/health` 返回 ok。生产 `/api/portfolio` 回读证据 `tmp/outputs/l4d-4r-prep-momcozy-marketing-production-readback-20260612-1520.json` 显示 `decision=passed`、`match_count=1`、`final_work_match_count=0`，目标图片为 `category=pending_review`、`kind=creation_intermediate`、`review_status=pending_review`、`tenant_id=momcozy-marketing`、`size_bytes=1431644`。本轮未调用 provider、未 submit、未发布、未写 final_work 或 approved brand token。

同日用户授权并执行 `L4D-2 poyo Seedance video-only single-job media smoke`。执行前新增并使用 `scripts/l4d_video_only_smoke.py` 专用入口，代码层面只允许 `momcozy_sterilizer_i2v_l4d_video_only_fixture` 的 1 次 `seedance-2` video job，输入固定为已存在的 `tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/main_45.png`，并拒绝旧完整资产包和 image-only execute gate。dry-run 证据 `tmp/outputs/l4d-2-video-only-dry-run-20260612-155828.json` 显示 `blocked_reasons=[]` 且未调用 provider。真实执行证据 `tmp/outputs/l4d-2-video-only-execute-20260612-155843.json` 显示 `status=submitted`、`provider_call_executed=true`、`image_job_count=0`、`video_job_count=1`、`blocked_reasons=[]`，poyo task 为 `7J9FKRVT4FGC4EQH`。返回视频只下载同一 provider media URL，写入 `output/tenants/momcozy-marketing/pending_review/l4d_video_only_20260612160601/seedance_video.mp4`，大小 `2474327` bytes，SHA-256 `ebadde1a4385cb8394fd1f2f4a3a169af7102a73818d638a8d24b94904f98a91`。生产同步证据 `tmp/outputs/l4d-2-video-only-production-sync-20260612-160657.json` 显示 hash verify 通过、`/api/health=ok`。生产 `/api/portfolio` 回读证据 `tmp/outputs/l4d-2-video-only-production-readback-20260612-160805.json` 显示 `decision=passed`、`match_count=1`、`final_work_match_count=0`，目标视频为 `category=pending_review`、`kind=creation_intermediate`、`review_status=pending_review`、`tenant_id=momcozy-marketing`、`mime_type=video/mp4`。本轮未生成图片、未执行 TTS/assemble/keyframe/gate candidate、未发布、未写 final_work 或 approved brand token。

同日用户授权并执行 `L4D-3 poyo image+Seedance paired single-chain media smoke`。执行前新增并使用 `scripts/l4d_paired_smoke.py` 专用入口，代码层面只允许 1 次 `gpt-image-2` image job 和 1 次 `seedance-2` video job，video job 的 `reference_asset_ids` 只能指向本轮 image artifact；实际 runtime 会先下载本轮 image 输出，再以该图片字节构造 video 输入。dry-run 证据 `tmp/outputs/l4d-3-paired-dry-run-20260612-161851.json` 显示 `blocked_reasons=[]` 且未调用 provider。真实执行证据 `tmp/outputs/l4d-3-paired-execute-20260612-161905.json` 显示 `status=submitted`、`provider_call_executed=true`、`image_job_count=1`、`video_job_count=1`、`blocked_reasons=[]`，poyo image task 为 `DEBMWQB3WRE6LNBF`，video task 为 `JQB119K0BWYO4360`。返回产物写入 `output/tenants/momcozy-marketing/pending_review/l4d_paired_20260612162837/`：`paired_image.png` 大小 `1667434` bytes，SHA-256 `695c8c0cca9d487c7877d67fab4c530f7cf1823a6b0597ee78beb6417f5cbba9`；`paired_video.mp4` 大小 `2298916` bytes，SHA-256 `8e953fa9c95c6d1e1b5d84082f634860e3f5ea5fd4a5227b455bb343f79fea9f`。生产同步证据 `tmp/outputs/l4d-3-paired-production-sync-20260612-162913.json` 显示 hash verify 通过、`/api/health=ok`。生产 `/api/portfolio` 回读证据 `tmp/outputs/l4d-3-paired-production-readback-20260612-163016.json` 显示 `decision=passed`、图片和视频 `match_count=1`、二者 `final_work_match_count=0`，且均为 `category=pending_review`、`kind=creation_intermediate`、`review_status=pending_review`、`tenant_id=momcozy-marketing`。本轮未执行 TTS/assemble/keyframe/gate candidate、未运行 S1-S5 full media、未发布、未写 final_work 或 approved brand token。

同日用户授权并执行 `L4D-4 frontend/library read-only pending_review readback`。只允许运行 `web/e2e/production/library-portfolio.prod.spec.ts`，`RUN_TOKEN_SMOKE=0`，不允许 provider 调用。执行前补充该 spec 的精确 target path 只读断言，覆盖 L4D-2 视频、L4D-3 图片和 L4D-3 视频。`--list` 只枚举该文件 3 个测试；正式执行证据 `tmp/outputs/l4d-4-library-readonly-playwright-20260612-163739.log` 显示 `3 passed (10.3s)`，其中包括 `/api/portfolio` 精确路径 readback、matching `final_work=0`、以及 `/library?tab=materials` pending-review 卡片只读渲染。backend 日志窗口证据 `tmp/outputs/l4d-4-library-readonly-summary-20260612-163833.json` 显示 provider submit、poyo、Seedance、TTS、assemble、keyframe、gate candidate、publish、delivery acceptance 计数均为 `0`。

同日用户授权并执行 `L4D-5-prep S2 bounded media pilot spec/readiness`。只新增并运行 `web/e2e/production/scenario-s2-bounded-media-pilot-readiness.prod.spec.ts` 的只读 readiness。`--list` 只枚举该文件 1 个测试；正式执行证据 `tmp/outputs/l4d-5-prep-s2-bounded-media-readiness-playwright-20260612.log` 显示 `1 passed (1.1s)`，只检查 `RUN_TOKEN_SMOKE=0`、`max_submit_count=1`、`provider/backend retry=0`、`artifact_disposition=pending_review` 和 `GET /api/health=ok`。证据摘要 `tmp/outputs/l4d-5-prep-s2-bounded-media-readiness-summary-20260612.json` 记录 `provider_call_executed=false`、`scenario_s2_submit_executed=false`。结论：S2 live media pilot 仍被阻断，因为 `/api/scenario/s2` 尚未显式接收并强制执行 `artifact_disposition=pending_review`，且 `enable_media_synthesis=true` 还没有被证明是 bounded pending-review-only 路径。

同日用户授权并执行 `L4D-5-fix-prep S2 artifact disposition + bounded media isolation`。本轮只修改本地 S2 后端与 readiness spec，不同步生产、不执行 `/api/scenario/s2` submit、不调用 provider。`S2BrandCampaignRequest` 新增 `artifact_disposition`，router 将其传入 `S2BrandCampaignPipeline`，pipeline 在 `pending_review` / `quarantine` 下只运行到 `seedance_clips` 后停止，并强制 `final_video_path=""`、`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。验证证据 `tmp/outputs/l4d-5-fix-prep-s2-bounded-media-readiness-summary-20260612.json` 显示：`provider_call_executed=false`、`scenario_s2_submit_executed=false`、readiness spec `1 passed`、`/api/health=ok`；本地测试 `tests/test_s2_e2e.py` 20 passed，router/shim 测试 8 passed，ruff/eslint/token guard/diff-check 均通过。下一步必须先做生产同步与 no-submit 验证，不能直接 live submit。

同日用户授权并执行 `L4D-5-fix-sync-prep S2 bounded media production sync + no-submit verification`。只同步三份后端文件：`src/routers/_state.py`、`src/routers/scenario.py`、`src/pipeline/s2_brand_pipeline_v2.py`；远端原文件备份到 `/opt/ai-video/backups/l4d5-fix-sync-prep-20260612-173119/`。backend 重启成功；`/api/health` 在重启后有一次瞬时 502，第一次重试即返回 `ok`。local/remote/container hash 全部一致，容器 import smoke 成功。370 秒 backend no-submit 日志窗口 forbidden total 为 `0`：无 `/scenario/s2`、poyo、SiliconFlow、Seedance、TTS、assemble、keyframe、gate candidate、`final_work`、publish、approved brand token write。证据汇总：`tmp/outputs/l4d-5-fix-sync-prep-summary-20260612-174020.json`。本轮未调用 provider、未执行 scenario submit、未运行 Playwright live submit。

2026-06-13 已完成 `L4D-5X` S2 keyframe cap/fallback isolation production sync 与容器 contract smoke。`src/skills/keyframe_images.py` 同步到生产后，`/api/health`、hash verify、container import/introspection 和 6 分钟 no-submit/provider log gate 均通过；证据为 `tmp/debug/l4d5x-final-summary-20260613133623.json`。随后只在容器内用 mocked `SkillRegistry.execute` 做 no-provider contract smoke：`_max_shots=1`、`provider_max_retries=0` 时，正常路径和 fallback 路径都只生成 1 张 keyframe，fallback 只写 `/tmp`，不写 output volume；证据为 `tmp/debug/l4d5x-post-sync-contract-summary-20260613135041.json`。

同日用户授权并执行 `L4D-5Y S2 bounded media keyframe-input verified provider smoke`。只运行 `web/e2e/production/scenario-s2-bounded-media-pilot-live.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`，`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`，`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`，`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`，`PLAYWRIGHT_EXPLICIT_SPEC=scenario-s2-bounded-media-pilot-live.prod.spec.ts`。执行结果 `1 passed (10.0m)`，生产 label 为 `l4d5s_s2_bounded_keyframe_20260613132543`。证据 `tmp/debug/l4d5y-final-summary-20260613132543.json` 显示：一次 scenario submit、poyo submit 总数 `2`（1 image + 1 video）、readback 中 `image_job_count=1`、`video_job_count=1`、provider retry `0`、Playwright retry `0`；keyframe 路径为 `/app/output/tenants/momcozy-marketing/pending_review/l4d5s_s2_bounded_keyframe_20260613132543/keyframes/poyo_img_keyframe_script-BRIEF-001-en_000_8511.png`，Seedance clip 路径为 `/app/output/tenants/momcozy-marketing/pending_review/l4d5s_s2_bounded_keyframe_20260613132543/clips/seedance_DDMO5J2C_28df.mp4`。日志和状态中未出现 fallback text-to-video、best image missing、TTS、thumbnail、assemble、media_quality_audit、gate candidate、`final_work`、publish、delivery 或 approved brand token。临时 production key 已撤销，post-revoke auth 返回 401。

同日已完成 `L4D-5Z frontend/library read-only portfolio regression for L4D-5Y assets`。`web/e2e/production/library-portfolio.prod.spec.ts` 已参数化支持 `PLAYWRIGHT_LIBRARY_BOUNDED_RUN_LABEL` 等目标变量；本轮只读运行指向 `l4d5s_s2_bounded_keyframe_20260613132543`，结果 `3 passed`。证据 `tmp/debug/l4d5z-final-summary-20260613135315.json` 显示 refined log gate 通过，生产 backend 仅观察到 `/portfolio/` GET，非 GET 为 `0`，forbidden hits 为空；该 spec 验证 pending_review 视频/keyframe 可见、poster cache 只作为 `thumbnail_path` 而不是独立素材卡片、matching `final_work` count 为 `0`。临时 key 已撤销，raw key env 已删除。

当前 L4D 阶段的默认停止条件：不继续追加 provider 消耗，不把 `L4D-5Y` 外推为 S2 full media 或 S1/S3/S4/S5 media generation。下一步优先收口文档、CI/read-only guard 和证据索引；任何新的 provider submit、full media、TTS、assemble、quality audit、publish 或 delivery acceptance 都必须重新定义目标、预算、止损和精确授权。

L4D 收口证据索引见 [L4D 真实媒体 Provider 证据索引](l4d-real-media-provider-evidence-index-stable.md)。

后续 `L4C` 单片候选命令模板：

```bash
cd web
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_MAX_SUBMIT_COUNT=1 \
PLAYWRIGHT_PROVIDER_MAX_RETRIES=0 \
PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/<authorized-spec>.prod.spec.ts \
  --reporter=list --retries=0 --workers=1
```

进入下一轮 `L4C` 前必须补充：

- 明确本轮允许执行哪些 spec。
- 明确总预算和每个 spec 的上限。
- 明确是否允许 S1/S5 进入媒体生成阶段。
- 明确失败后是否允许重试。默认不允许自动重试。
- 明确是否要临时把 `PLAYWRIGHT_PROD_WORKERS=1` 固定为串行。
- 明确 `max_submit_count`、provider/backend retry 次数和超出 submit ceiling 时的失败规则。
- 明确产物仍为 `pending_review`，且 `delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。

## L4D 真实 media provider 阶梯计划

`L4D` 的目标是验证真实媒体 provider 生成链路本身，而不是一次性验证完整 S1-S5 编排。每一层都必须单独授权、单独预算、单独止损；上一层通过只允许进入下一层讨论，不自动授权下一层执行。

| 阶段 | Provider 范围 | 允许 submit | 预算建议 | 成功证据 | 禁止项 |
|---|---|---:|---:|---|---|
| `L4D-0` media readiness gate | 无真实 provider | 0 | `$0` | health ok、hash/import clean、pending_review 路径可写、plan/authorization records ready | 不调用 `/scenario/*`、不调用 poyo/SiliconFlow |
| `L4D-1` image-only smoke | poyo `gpt-image-2` | 1 image job | `$1.00` | 已执行：provider job submitted，`L4D-1R` 已本地物化为 tenant-scoped pending_review；`L4D-4R-prep` 生产 tenant readback 已通过 | 禁止视频、TTS、发布、final_work |
| `L4D-2` video-only smoke | poyo `seedance-2` | 1 video job | `$2.00` | 已执行：1 条短视频进入 tenant-scoped `pending_review`，`final_work=0`，无 image/TTS/assemble | 禁止图片生成、TTS、发布、final_work |
| `L4D-3` image+video paired smoke | poyo image + poyo Seedance | 1 image + 1 video | `$3.00` | 已执行：本轮 image artifact 被 video job 使用，二者均进入 tenant-scoped `pending_review`，`final_work=0` | 禁止多图批量、TTS、assemble、发布 |
| `L4D-4` frontend read-only readback | 无新增 provider | 0 | `$0` | 已执行：`/api/portfolio` 与 `/library?tab=materials` 可见待审产物，`final_work=0`，backend forbidden 日志为 0 | 禁止 POST/PUT/PATCH/DELETE |
| `L4D-5-prep` S2 bounded media readiness | 无真实 provider | 0 | `$0` | 已执行：只读 readiness 通过，发现 S2 disposition/bounded media blocker | 禁止 `/api/scenario/s2` submit |
| `L4D-5-fix-prep` S2 bounded media implementation | 无真实 provider | 0 | `$0` | 已执行：本地 S2 支持 artifact disposition，bounded media 停在 `seedance_clips` | 禁止生产 submit |
| `L4D-5-fix-sync-prep` production sync | 无真实 provider | 0 | `$0` | 已执行：同步三份后端文件，hash/import/health/no-submit 日志验证通过 | 禁止 `/api/scenario/s2` submit |
| `L4D-5-post-sync-readiness` S2 bounded media readiness | 无真实 provider | 0 | `$0` | 已执行并通过：单 readiness spec、无 submit/provider | 禁止 submit/provider |
| `L4D-5X` keyframe cap/fallback isolation | 无真实 provider | 0 | `$0` | 已执行并通过：生产 sync + container contract smoke，`_max_shots=1` 生效 | 禁止写 output volume 或 provider |
| `L4D-5Y` S2 bounded media provider smoke | S2 单场景、poyo image + Seedance | 1 scenario submit | `$3.00` | 已执行并通过：1 image + 1 video，到 `seedance_clips` 后停止，产物进入 tenant-scoped `pending_review` | 禁止 TTS、thumbnail、assemble、audit、gate、final_work、publish |
| `L4D-5Z` frontend read-only regression | 无新增 provider | 0 | `$0` | 已执行并通过：S2 bounded media 视频/keyframe 可见，poster cache 不作为独立资产，`final_work=0` | 禁止任何 mutation API |

### L4D 执行原则

- `L4D-1` 只验证 image provider，不得顺手触发视频。
- `L4D-2` 只验证 video provider；输入图像必须来自已存在的待审资产或受控静态引用，不得同时生成新图片。
- `L4D-3` 才允许 image+video 串联，但仍只允许 1+1。
- `L4D-4` 必须是只读，不得消费 provider 额度。
- `L4D-5Y` 是当前唯一通过的 scenario media pilot，只覆盖 S2 bounded media 到 `seedance_clips`；不得外推到 S2 full media、final assembly 或其他场景。
- 所有真实产物默认 `delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。

### L4D-1 授权模板

```text
我授权在生产环境 https://video.lute-tlz-dddd.top 执行 L4D-1 poyo image-only single-job media smoke。

允许范围：
- 只允许 1 次 poyo gpt-image-2 image job
- 使用非 demo production PLAYWRIGHT_API_KEY/API_KEY
- 使用 funded POYO_API_KEY
- 产物只进入 tenant-scoped pending_review
- 不允许 Seedance / TTS / assemble / scenario full media / publish / final_work / approved brand token write / delivery acceptance

预算与止损：
- 总预算上限 $1.00
- 自动重试 0
- provider/backend retry 0
- 遇到 401/403/422/429/quota/content rejection/provider error/missing artifact/test timeout 立即停止
- 不做第二次 image job，除非我重新授权

检查人：pray
```

## 正式执行顺序

### Phase A: 本地质量门

```bash
.venv/bin/python -m pytest tests -q
make lint

cd web
npm run lint
npx tsc --noEmit -p tsconfig.json
npm test -- --run
npm run build
cd ..
git diff --check
```

验收：

- 所有命令通过。
- 不要求真实 provider key。
- 不设置 `RUN_TOKEN_SMOKE=1`。

### Phase B: no-token authorization preflight

```bash
.venv/bin/python scripts/p2_recharge_smoke_checklist.py
.venv/bin/python scripts/build_authorized_live_smoke_packet.py --include-preflight
.venv/bin/python scripts/build_authorized_live_test_plan_readiness_report.py
.venv/bin/python -m pytest \
  tests/test_token_smoke_preflight.py \
  tests/test_authorized_live_smoke_packet_builder.py \
  tests/test_authorized_live_test_plan_readiness_report.py \
  tests/test_p2_recharge_smoke_checklist.py \
  -q
```

验收：

- 未授权时必须 blocked 或 dry-run。
- 输出只允许作为 `L2` 证据。
- 不访问 provider。

### Phase C: 生产非 token E2E 基线

预检命令：

```bash
.venv/bin/python scripts/production_non_token_e2e_check.py --json
```

正式执行命令：

```bash
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
.venv/bin/python scripts/production_non_token_e2e_check.py --execute
```

验收：

- `production_non_token_e2e_check.py` 返回 `ready_for_phase_c_execution=true`。
- `@token-smoke` 被跳过。
- authenticated checks 使用非 demo key。
- 不触发 `/api/fast/generate`、`/api/fast/submit`、`/scenario/*` mutation、gate candidate 生成、上传或发布。
- 若 `library-portfolio` 因没有 `pending_review` 资产 skip，只能说明 L4B 待审素材回读前置条件缺失；不得把 skip 计入 L4B 通过。
- 结果写入 `tmp/outputs/e2e-prod-non-token-YYYYMMDD.json` 或同等执行摘要。

### Phase D: L4A 真实 provider 最小样本

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD=<private-account-readiness-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1 \
AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

验收：

- 只执行 Momcozy 消毒器 3 图 + 1 视频样本包。
- 自动重试为 0。
- 产物进入 `pending_review`。
- 不写入 approved brand token。
- 不发布。
- summary 写入 `tmp/outputs/authorized-live-poyo-smoke-YYYYMMDD-summary.json` 或同等私有输出。

### Phase E: L4B 前端只读回读

```bash
cd web
RUN_TOKEN_SMOKE=0 \
PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top \
PLAYWRIGHT_API_KEY=<production-api-key> \
npx playwright test -c playwright.prod.config.ts \
  e2e/production/library-portfolio.prod.spec.ts \
  --reporter=list,html
```

验收：

- 生产前端能只读看到本次或同 batch `pending_review` 素材。
- 无 mutation API 调用。
- 产物仍不进入 `final_work`。

### Phase F: 证据包归档

输出位置：

- 临时执行证据：`tmp/outputs/real-provider-e2e-YYYYMMDD.json`
- 截图或 Playwright report：`tmp/screenshots/` 或 `web/playwright-report/`，不提升为正式资产。
- 若形成稳定 SOP 更新，再同步 `docs/runbooks/production-e2e-token-smoke.md`。

证据包必须包含：

- 执行人和时间。
- 授权记录路径，不包含密钥原文。
- account readiness record 路径，不包含密钥原文。
- provider job ids / task ids。
- backend trace ids / response `_meta.trace_id`。
- artifact refs / media URLs。
- 前端验证截图或 Playwright result 摘要。
- 成本估算和实际扣费记录。
- `delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false` 的确认。

## 场景矩阵

| 场景 | 当前优先级 | L2 no-token | L3 prod non-token | L4A provider smoke | L4B frontend readback | L4C expanded token | 备注 |
|---|---:|---:|---:|---:|---:|---:|---|
| `/settings` 配置控制面 | P0 | 是 | 是 | 否 | 否 | 否 | 不应触发 provider |
| Fast Mode | P0 | 是 | 是 | 否 | 否 | 是（L4C-1R） | single-submit pending_review token smoke 已通过 |
| S1 商品直拍 | P0 | 是 | 是 | 否 | 否 | 是（L4C-4R no-media） | no-media clean-log 已通过，media generation 未验证 |
| S2 Brand Campaign | P1 | 是 | 是 | 是（L4D-5Y bounded media） | 是（L4D-5Z readback） | 是（L4C-5 no-media） | no-media clean-log 已通过；bounded media 到 `seedance_clips` 已通过；full media/final assembly 未验证 |
| S3 Influencer Remix | P1 | 是 | 是 | 否 | 否 | 是（L4C-6 no-media） | no-media clean-log 已通过，media generation 未验证 |
| S4 Live Shoot | P1 | 是 | 是 | 否 | 否 | 是（L4C-7 no-media） | no-media clean-log 已通过，media generation 未验证 |
| S5 Brand VLOG | P1 | 是 | 是 | 否 | 否 | 是（L4C-8R no-media） | no-media clean-log 已通过，media generation 未验证 |
| 工具箱：电商商品图 | P0 | 是 | 是 | 是（已执行两次） | 是（2026-06-11） | 可选 | 首轮 Momcozy 消毒器主图 |
| 工具箱：产品六视图 | P1 | 是 | 是 | 可选 | 可选 | 可选 | 真实生成需成本确认 |
| 工具箱：电商视觉图 | P0 | 是 | 是 | 是（已执行两次） | 是（2026-06-11） | 可选 | 首轮 Momcozy 消毒器卖点图和场景图 |
| 工具箱：数字人 | P2 | 是 | 是 | 否 | 否 | 否 | 需单独评估 HeyGen/Avatar 成本 |
| 工具箱：故事版 | P0 | 是 | 是 | 是（已执行两次） | 是（2026-06-11） | 可选 | 首轮 15 秒 image-to-video |
| L4D real media provider | P0 | 是 | 是 | L4D-1/L4D-2/L4D-3/L4D-5Y 已通过 | L4D-4/L4D-5Z 已通过 | 暂停追加 | 已完成 image-only、video-only、image+video、S2 bounded media provider smoke 与 frontend readback；默认进入文档/CI guard 收口，不继续 provider 消耗 |

## 下一轮开发 TODO

1. [x] 为 `/settings` 增加 Playwright 页面级 smoke，覆盖后端离线、provider 分类、key masked 展示。实现文件：`web/e2e/ui-only/settings-config.smoke.spec.ts`。
2. [x] 为 `api.ts` 增加请求 payload 审计测试，确保 disabled provider 和空 key 不会进入后端。实现文件：`web/src/components/apiProviderConfig.test.ts`。
3. [x] 为生产非 token E2E 增加 `/settings` 路由覆盖，不改变 `@token-smoke` 默认跳过策略。实现文件：`web/e2e/production/smoke.prod.spec.ts`。
4. [x] 为 poyo 授权 smoke 准备 approval record 模板和预算止损字段，但不在未授权状态下执行 provider 调用。实现文件：`configs/authorized-live-token-smoke-approval-template.json`。
5. [x] 在品牌资产目录接入后，把 S5 和工具箱图像生成样本加入 L2 fixture 矩阵。实现文件：`tests/fixtures/toolbox/momcozy_toolbox_l2_fixture_matrix.json`。
6. [x] 移除生产 `@token-smoke` spec 中残留的 demo key fallback，统一通过 production helper 管控 authenticated smoke。实现文件：`web/e2e/production/helpers.ts`、`web/e2e/production/s1-gate.prod.spec.ts`、`web/e2e/production/s1-step-by-step.prod.spec.ts`。
7. [x] 强制 P2 充值后统一入口在任何 token-consuming 命令前执行 no-token preflight。实现文件：`scripts/p2_recharge_smoke_checklist.py`、`tests/test_p2_recharge_smoke_checklist.py`。
8. [x] 增加 poyo 当前公开文档重验契约，并绑定到真实 smoke approval record/preflight。实现文件：`configs/poyo-current-provider-revalidation-contract.json`、`src/pipeline/token_smoke_preflight.py`。
9. [x] 增加授权真实 smoke 最小样本计划契约，并绑定到 approval record/preflight。实现文件：`configs/authorized-live-token-smoke-sample-plan-contract.json`、`src/pipeline/token_smoke_preflight.py`。
10. [x] 增加私有 authorized-live approval record 构建器，要求精确授权句并拒绝写入正式目录。实现文件：`scripts/build_authorized_live_approval_record.py`、`tests/test_authorized_live_approval_record_builder.py`。
11. [x] 增加私有 provider account readiness 构建器，要求人工余额确认并绑定到 preflight。实现文件：`scripts/build_provider_account_readiness_record.py`、`tests/test_provider_account_readiness_record_builder.py`。
12. [x] 增加 no-token authorized-live smoke 启动包，并串联到 P2 recharge checklist dry-run。实现文件：`scripts/build_authorized_live_smoke_packet.py`、`tests/test_authorized_live_smoke_packet_builder.py`、`scripts/p2_recharge_smoke_checklist.py`。
13. [x] 增加正式测试计划讨论 readiness report，区分可讨论测试计划与可执行真实调用。实现文件：`scripts/build_authorized_live_test_plan_readiness_report.py`、`tests/test_authorized_live_test_plan_readiness_report.py`。
14. [x] 将首轮授权真实 smoke 样本计划从 Fast+S1 连通性样本调整为 Momcozy 消毒器 3 图 + 1 条 15 秒竖版图片驱动视频资产包，并保持 `pending_review` 素材库边界。实现文件：`configs/authorized-live-token-smoke-sample-plan-contract.json`、`configs/authorized-live-token-smoke-approval-template.json`、`src/pipeline/token_smoke_preflight.py`。
15. [x] 增加 no-token poyo submitter factory gate，默认不构建 submitter，启用后仍要求 injected transport/private payloads。实现文件：`src/pipeline/authorized_live_poyo_submitter.py`、`tests/test_authorized_live_poyo_submitter.py`。
16. [x] 增加 no-token poyo submit/status HTTP adapter contract，使用 fake HTTP client 验证 request shape、artifact refs 和失败即停。实现文件：`src/pipeline/authorized_live_poyo_submitter.py`、`tests/test_authorized_live_poyo_submitter.py`。
17. [x] 增加 no-token HTTP submitter assembly gate，把 transport gate、injected token、injected HTTP client 和 private payloads 显式组装，同时保持默认 CLI 不接线。实现文件：`src/pipeline/authorized_live_poyo_submitter.py`、`tests/test_authorized_live_poyo_submitter.py`。
18. [x] 增加私有 poyo payload loader、runtime submitter factory 和 CLI 显式 opt-in flag，默认仍不构造真实 submitter。实现文件：`src/pipeline/authorized_live_poyo_runtime.py`、`src/pipeline/authorized_live_harness.py`、`scripts/authorized_live_token_smoke_harness.py`、`tests/test_authorized_live_poyo_runtime.py`。
19. [x] 增加生产 `/portfolio` / `materials` 边界 Playwright 覆盖：验证 `creation_intermediate` pending_review 资产可见且详情页不触发非 GET 的 mutation call。实现文件：`web/e2e/production/library-portfolio.prod.spec.ts`。
20. [x] 正式拆分真实 provider 前后端 E2E 为 `L4A` 受控 provider smoke、`L4B` 前端只读回读、`L4C` 扩展 token Playwright，并同步 runbook 执行口径。实现文件：`docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md`、`docs/runbooks/production-e2e-token-smoke.md`。
21. [x] 修复 `/portfolio` 对租户级待审素材的扫描能力，支持 `output/tenants/<tenant>/pending_review/...`；顶层 `pending_review` 仍保持 default 隔离，避免跨租户泄露。实现文件：`src/routers/portfolio.py`、`tests/test_p0_media_tenant_security.py`。
22. [x] 将 2026-06-11 L4A 待审产物同步到生产 `output/tenants/momcozy-marketing/pending_review/momcozy_sterilizer_smoke_20260611/`，部署 portfolio 扫描补丁后执行 L4B 只读回读。证据文件：`tmp/outputs/l4b-production-readback-20260611-160827.json`。
23. [x] 完成 L4C S1-S5 no-media clean-log single-submit 阶段，并正式制定 L4D 真实 media provider 分级授权计划。实现文件：`docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md`、`docs/runbooks/production-e2e-token-smoke.md`。
24. [x] 完成 L4D S2 bounded media provider smoke 与 frontend/library read-only 回归收口。证据文件：`tmp/debug/l4d5y-final-summary-20260613132543.json`、`tmp/debug/l4d5z-final-summary-20260613135315.json`。

## 阶段验收

进入下一次 L4A provider smoke 前必须满足：

- L0 全绿。
- L1 `/settings` 页面验收通过。
- L2 preflight 在无授权状态下正确 blocked，在授权记录和 key 完整时才变为可执行。
- P2 充值后统一入口 blocked 时不得启动真实 smoke 子进程。
- L2.5 provider 公开文档重验已完成且 approval record 绑定当前 revalidation ref。
- L2.5 authorized-live sample plan 已完成且 approval record 绑定当前 sample plan ref。
- 私有 approval record 构建器已验证，且模板或泛化确认不会绕过 preflight。
- 私有 provider account readiness 构建器已验证，且余额不足、缺失或记录 API key 原文不会绕过 preflight。
- no-token authorized-live smoke 启动包已验证，且默认 P2 recharge checklist dry-run 会提示先生成启动包。
- no-token test-plan readiness report 已验证，且能明确给出“可讨论测试计划 / 不可执行真实调用”的分层结论。
- no-token poyo submitter factory gate 已验证，且默认 CLI 不接线真实 provider transport。
- no-token poyo submit/status HTTP adapter 已验证，且默认 CLI 不接线真实 HTTP client。
- no-token HTTP submitter assembly gate 已验证，且默认 CLI 不接线该 helper。
- 私有 poyo runtime submitter factory 已验证，且默认 CLI 不启用 `--enable-poyo-http-submitter`。
- L3 生产非 token E2E 使用非 demo production key 通过，且结果不低于当前可执行基线（`50 passed, 4 skipped`）。`library-portfolio` 在没有 `pending_review` 资产时应 skip；有本次 L4A 产物时必须实跑命中。
- `/portfolio` 与 `Materials` tab 的 pending_review 只读边界已覆盖：有本次 L4A 产物时，`creation_intermediate` 与 `pending_review` 可见，`/library?tab=materials` 未发起 `POST/PUT/PATCH/DELETE`。2026-06-11 L4B 已通过；若未来生产无 `pending_review` 资产，该项应保持 skip，不能声明 L4B 通过。
- 用户明确授权 L4A，并确认预算、样本数、失败停止规则。

已满足以上条件并完成一次 scoped 执行后，可声明“受控 `L4-authorized-live`（样本包）已完成”；仍不能声明商业交付完成、delivery acceptance、或可直接发布。

进入 L4B 前必须额外满足：本次 L4A summary 存在、`provider_call_executed=true`、`blocked_reasons=[]`、产物为 `pending_review`，且 `RUN_TOKEN_SMOKE=0`。进入 L4C 前必须重新定义 spec 范围、预算、是否允许 S1/S5 进入媒体生成、重试策略和串行 workers；默认不执行 L4C。L4D 已通过到 S2 bounded media + frontend readback；下一次进入 L4D 只能以新的明确目标启动，且必须重新确认 provider 余额、预算上限、单 job 数、产物处置、失败即停、日志 forbidden 关键词和是否允许下一层级。默认不再追加 provider 消耗。
