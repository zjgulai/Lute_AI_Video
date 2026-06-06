---
title: AI Video Project 2.0 E2E 测试计划
doc_type: workflow
module: ai-video-2.0
topic: e2e-test-plan
status: stable
created: 2026-06-06
updated: 2026-06-06
owner: self
source: human+ai
---

# AI Video Project 2.0 E2E 测试计划

## 目标

在模型/API key 配置控制面完成后，建立一条可审计的端到端测试链路。默认不触发真实 provider，不消耗 poyo 额度，不把 dry-run 或 fixture 结果声明为商业交付完成。真实 poyo smoke 只在用户再次明确授权、充值完成、环境门禁通过后执行。

## 证据边界

| 层级 | 范围 | Provider 调用 | 可声明结论 |
|---|---|---:|---|
| L0 | lint、typecheck、unit、build | 否 | 代码结构和类型约束通过 |
| L1 | 本地 UI 与配置页渲染 | 否 | 配置入口和前端状态可用 |
| L2 | fixture、dry-run、mock provider、preflight | 否 | 工作流契约、门禁和账本可审计 |
| L3 | 生产非 token smoke、生产非 token Playwright | 否 | 生产路由、认证、静态页面、非生成路径可用 |
| L4 | 授权真实 token smoke | 是 | 局部 provider 链路可用，不等于商业交付完成 |

C1-C8 最高证据等级仍保持 L2。C9 只有在用户明确授权真实 token smoke 后，才能对被测试的小范围路径升级为 L4。

## 生产模型和 Key 盘点

### 当前生产主链路

| 类别 | Provider | 关键 env | 默认模型/用途 | 测试策略 |
|---|---|---|---|---|
| 文本/推理 | DeepSeek | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL`, `DEFAULT_LLM_PROVIDER` | `deepseek` 为默认文本提供方；Fast Mode 会降到低延迟 chat 模型 | L2 只验证配置注入；L4 才允许真实调用 |
| 图像生成 | poyo.ai | `POYO_API_KEY`, `POYO_API_BASE_URL`, `POYO_IMAGE_MODEL` | GPT image 类模型，经 poyo 接入 | L2 验证 prompt hash 和 job ledger；L4 小样本 |
| 视频生成 | poyo.ai | `POYO_API_KEY`, `POYO_API_BASE_URL`, `POYO_VIDEO_MODEL` | Seedance 视频生成 | L2 禁止真实调用；L4 只跑最小样本 |
| TTS | SiliconFlow CosyVoice | `SILICONFLOW_API_KEY`, `SILICONFLOW_API_BASE`, `COSYVOICE_MODEL`, `COSYVOICE_VOICE` | 旁白和音频生成 | L2 验证配置和任务边界；L4 可选 |
| 后端访问 | Internal API | `API_KEY`, `PLAYWRIGHT_API_KEY` | 后端 API 认证和生产 E2E | L3/L4 验收必须使用非 demo production key；demo key 或缺 key 只能得到跳过后的部分 smoke |

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
.venv/bin/python -m pytest tests/test_token_smoke_preflight.py
```

如果相关测试文件不存在或命名变化，先用 `rg "token_smoke_preflight|commercial_token_smoke_preflight" tests src scripts` 定位实际测试入口。

检查项：

- 缺少授权记录时 preflight 必须 blocked。
- 缺少 `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 时必须 blocked。
- demo `API_KEY` 或 demo `PLAYWRIGHT_API_KEY` 不允许进入真实 token smoke。
- `scripts/p2_recharge_smoke_checklist.py --execute` 必须自动执行 preflight；preflight blocked 时不得启动 `smoke.sh` 或 Playwright。
- provider job ledger 只暴露 prompt hash、artifact refs、status，不暴露 prompt payload 或品牌资产原文。
- C1-C8 不生成 approved brand token。

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

2026-06-06 当前有效验收结果：使用生产 API key、`RUN_TOKEN_SMOKE=0` 执行后，生产套件为 `50 passed, 2 skipped`。缺少 `PLAYWRIGHT_API_KEY` 或只提供 `ai_video_demo_2026` 时，authenticated production checks 会跳过；这种结果只能说明页面级 smoke 可运行，不能作为生产验收通过。

检查项：

- `/`、`/settings`、S1-S5、Fast Mode、资源页可以打开。
- authenticated production checks 必须使用非 demo production key。
- `@token-smoke` 默认跳过，不触发真实 provider。
- 生产错误页和离线状态有明确展示。
- `/api/fast/generate` token path 不在默认 smoke 中执行。

### L4 授权真实 poyo token smoke

目的：在用户明确授权后，用最小样本验证 poyo 图像/视频生成链路。

执行前置条件：

- 用户在当前会话再次明确授权真实 token smoke。
- poyo 账号已充值，预算和止损阈值明确。
- `API_KEY` 和 `PLAYWRIGHT_API_KEY` 是非 demo production key。
- `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 已配置。
- no-token preflight 已通过。
- 生产日志和 artifact 目录可检查。

统一入口：

```bash
CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 \
AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD=<private-approval-json> \
API_KEY=<production-api-key> \
PLAYWRIGHT_API_KEY=<production-api-key> \
POYO_API_KEY=<funded-poyo-key> \
DEEPSEEK_API_KEY=<deepseek-key> \
SILICONFLOW_API_KEY=<siliconflow-key> \
python scripts/p2_recharge_smoke_checklist.py --execute
```

真实样本范围：

| 顺序 | 场景 | 样本 | 目的 | 预算策略 |
|---:|---|---|---|---|
| 1 | Fast Mode | 1 条 15s 以内短视频 | 验证最短 text-to-video 链路 | 成功即停 |
| 2 | S1 商品直拍 | 1 个商品、单路径 | 验证脚本、关键帧、视频任务、状态回写 | 失败后不自动重试 |
| 3 | S5 Brand VLOG | 可选 1 条短样本 | 验证品牌人物/口播链路 | 需要用户单独确认 |

失败处理：

- 403 或 key invalid：停止，检查 provider 控制台和部署 env。
- 429 或 quota：停止，不重试，记录额度和速率限制。
- content rejection：保留 provider 返回原因，回到 prompt/gate 修复，不直接换更宽松模型。
- artifact missing：检查 job ledger、对象存储、nginx `/api/assets/` 或 `/media/` 路由。
- state stuck：检查后端日志、pipeline state、任务状态回写，不重复提交同一任务。

## 场景矩阵

| 场景 | 当前优先级 | L2 no-token | L3 prod non-token | L4 token smoke | 备注 |
|---|---:|---:|---:|---:|---|
| `/settings` 配置控制面 | P0 | 是 | 是 | 否 | 不应触发 provider |
| Fast Mode | P0 | 是 | 是 | 是 | poyo 首个最小样本 |
| S1 商品直拍 | P0 | 是 | 是 | 是 | 2.0 主验证路径 |
| S5 Brand VLOG | P1 | 是 | 是 | 可选 | 品牌资产目录接入后再扩大 |
| 工具箱：电商商品图 | P1 | 是 | 是 | 可选 | 先验证配置和 job ledger |
| 工具箱：产品六视图 | P1 | 是 | 是 | 可选 | 真实生成需成本确认 |
| 工具箱：电商视觉图 | P1 | 是 | 是 | 可选 | 先走图像 provider mock |
| 工具箱：数字人 | P2 | 是 | 是 | 否 | 需单独评估 HeyGen/Avatar 成本 |
| 工具箱：故事版 | P0 | 是 | 是 | 否 | 可用 L2 验证核心价值 |
| S2/S3/S4 | P2 | 是 | 是 | 否 | 长视频和 remix 权利门禁先行 |

## 下一轮开发 TODO

1. [x] 为 `/settings` 增加 Playwright 页面级 smoke，覆盖后端离线、provider 分类、key masked 展示。实现文件：`web/e2e/ui-only/settings-config.smoke.spec.ts`。
2. [x] 为 `api.ts` 增加请求 payload 审计测试，确保 disabled provider 和空 key 不会进入后端。实现文件：`web/src/components/apiProviderConfig.test.ts`。
3. [x] 为生产非 token E2E 增加 `/settings` 路由覆盖，不改变 `@token-smoke` 默认跳过策略。实现文件：`web/e2e/production/smoke.prod.spec.ts`。
4. [x] 为 poyo 授权 smoke 准备 approval record 模板和预算止损字段，但不在未授权状态下执行 provider 调用。实现文件：`configs/authorized-live-token-smoke-approval-template.json`。
5. [x] 在品牌资产目录接入后，把 S5 和工具箱图像生成样本加入 L2 fixture 矩阵。实现文件：`tests/fixtures/toolbox/momcozy_toolbox_l2_fixture_matrix.json`。
6. [x] 移除生产 `@token-smoke` spec 中残留的 demo key fallback，统一通过 production helper 管控 authenticated smoke。实现文件：`web/e2e/production/helpers.ts`、`web/e2e/production/s1-gate.prod.spec.ts`、`web/e2e/production/s1-step-by-step.prod.spec.ts`。
7. [x] 强制 P2 充值后统一入口在任何 token-consuming 命令前执行 no-token preflight。实现文件：`scripts/p2_recharge_smoke_checklist.py`、`tests/test_p2_recharge_smoke_checklist.py`。

## 阶段验收

进入 poyo token smoke 前必须满足：

- L0 全绿。
- L1 `/settings` 页面验收通过。
- L2 preflight 在无授权状态下正确 blocked，在授权记录和 key 完整时才变为可执行。
- P2 充值后统一入口 blocked 时不得启动真实 smoke 子进程。
- L3 生产非 token E2E 使用非 demo production key 通过，且结果不低于当前 `50 passed, 2 skipped` 基线。
- 用户明确授权 L4，并确认预算、样本数、失败停止规则。

未满足以上条件时，结论只能停留在 L2/L3，不能声明真实商业视频生成链路已完成。
