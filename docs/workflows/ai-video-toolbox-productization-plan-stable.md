---
title: AI Video 工具箱产品化实施计划
doc_type: workflow
module: ai-video-2.0
topic: toolbox-productization
status: stable
created: 2026-06-05
updated: 2026-06-16
owner: self
source: human+ai
related:
  - file: ../architecture/ai-video-commercial-toolbox-architecture-review-20260603.md
    relation: implements
  - file: ./ai-video-commercial-toolbox-phase0-backlog-review-20260603.md
    relation: refines
  - file: ./ai-video-project-2-0-code-readiness-plan-review-20260604.md
    relation: follows-boundary
  - file: ./ai-video-project-2-0-final-self-proof-stable.md
    relation: extends-after
---

# AI Video 工具箱产品化实施计划

> 状态边界：本文定义并追踪 `电商商品图`、`产品六视图`、`电商视觉图`、`数字人`、`故事版` 五个独立工具的后端与前端产品化实施顺序。当前代码已覆盖 T1-T9 的 L2 dry-run / preflight 层，但仍不授权真实 provider 调用、不生成 approved brand token、不改变 S1-S5 场景语义。

## 1. 结论

当前已完成 AI Video 2.0 dry-run 合约、门禁、job ledger、只读注入、prompt preview audit、品牌 token 候选治理、工具箱独立产品层、工具产物只读回注、Momcozy S5/toolbox L2 fixture 矩阵和工具级 provider readiness preflight。

工具箱已经具备 `/toolbox` 导航、五个工具页、统一 API、工具级 run state、artifact/job ledger/audit summary 与 refs-only injection draft。真实生成仍未授权；T9 只是授权前置门禁，不代表 live smoke 已执行。

2026-06-16 checklist drift sync：T0-T8 checklist 已按当前代码与 GAP 表同步为完成态。该完成态只表示 `L2-fixture-or-dry-run`、preflight、job ledger、audit summary 与 refs-only injection 已实现；不表示真实 provider 调用、live smoke、approved brand token、delivery acceptance 或 publish 已授权或执行。

因此下一阶段目标不是继续堆 provider，而是建立一个可复用的工具箱产品层：

```text
S1-S5 场景工作流
  -> 继续保留完整视频生产路径

Toolbox 独立工具层
  -> 处理单点创作任务
  -> 产物可回注 S1-S5
  -> 所有生成计划进入 prompt preview audit / job ledger / quality gate
```

## 2. 范围

### 2.1 首批工具

| 工具 | 业务用途 | 主要输出 | 首批证据等级 |
|---|---|---|---|
| 电商商品图 | 商品主图、白底图、详情页基础图 | product image set | `L2-fixture-or-dry-run` |
| 产品六视图 | 产品一致性和后续视频 reference 底座 | six-view image/reference manifest | `L2-fixture-or-dry-run` |
| 电商视觉图 | banner、A+ content、广告视觉、社媒视觉 | ecommerce visual pack | `L2-fixture-or-dry-run` |
| 数字人 | presenter demo、口播、产品演示 | presenter plan / avatar job draft | `L2-fixture-or-dry-run` |
| 故事版 | brief/script 到 shot list、镜头节奏、EDL seed | storyboard package | `L2-fixture-or-dry-run` |

### 2.2 非目标

- 不在本阶段真实调用 POYO、Seedance、Runway、Kling、Veo、Sora、HeyGen、ElevenLabs 或其他 provider。
- 不把数字人、voice clone、真人肖像或儿童相关素材直接上线为可生成资产。
- 不把 `工具箱` 放进 `素材库`。素材库管理资产，工具箱执行创作任务。
- 不把工具页做成营销 landing page。它是运营工作台。
- 不绕过已有 `BrandAssetToken`、`ProviderPromptCompiler`、`ProductionJobLedger`、`QualityContract`。

## 3. 产品信息架构

### 3.1 顶部导航

新增一级导航：

```text
首页 / 作品 / 素材库 / 工具箱 / 设置
```

路由：

```text
/toolbox
/toolbox/product-image
/toolbox/six-view
/toolbox/ecommerce-visual
/toolbox/digital-human
/toolbox/storyboard
```

### 3.2 工具箱首页

`/toolbox` 是工具目录和最近任务工作台，不是介绍页。

首屏结构：

```text
Header: 工具箱标题 + evidence level + dry-run 状态
Tool Grid: 五个工具入口
Recent Runs: 最近工具运行记录
Audit Queue: blocked / review_required / accepted 摘要
Provider Readiness: no-token / approval-required 状态
```

### 3.3 单工具页面

五个工具页统一交互骨架：

```text
左栏: 工具输入
  - SKU / brief / platform / aspect ratio / style preset
  - brand bundle refs
  - asset refs

中栏: 计划与预览
  - prompt preview
  - storyboard / layout / image set plan
  - provider capability warnings

右栏: 审计与账本
  - Quality Gate
  - Repair Plan
  - Job Ledger
  - Artifact Manifest

底部: 结果与回注
  - artifact gallery
  - compare variants
  - inject into S1-S5
```

页面上只允许出现 dry-run、preview、prepare、audit、review 等动作。真实生成按钮在 C9/C21 授权条件满足前必须禁用或隐藏。

## 4. 后端设计

### 4.1 新增模块

```text
src/models/toolbox_contracts.py
src/pipeline/toolbox/__init__.py
src/pipeline/toolbox/registry.py
src/pipeline/toolbox/planner.py
src/pipeline/toolbox/audit.py
src/routers/toolbox.py
tests/test_toolbox_contracts.py
tests/test_toolbox_router.py
tests/fixtures/toolbox/
```

原则：

- `src/routers/toolbox.py` 只负责 request intake、response projection 和 auth dependency。
- `src/pipeline/toolbox/` 只负责编排 dry-run 计划、prompt preview、ledger draft 和 gate。
- 工具箱不直接读写 S1-S5 场景状态。
- 回注 S1-S5 时只传 artifact refs、contract refs、bundle ids，不传 prompt payload 或品牌资产原文。

### 4.2 后端 API

```text
GET  /toolbox/tools
POST /toolbox/{tool_id}/plan
POST /toolbox/{tool_id}/prompt-preview
POST /toolbox/{tool_id}/run
GET  /toolbox/runs/{run_id}
GET  /toolbox/runs/{run_id}/artifacts
POST /toolbox/runs/{run_id}/inject
```

首批 `POST /run` 默认只创建 dry-run job record：

```text
mode=dry_run
evidence_level=L2-fixture-or-dry-run
provider_call=false
delivery_accepted=false
```

### 4.3 核心合约

```text
ToolboxTool
ToolboxRequest
ToolboxPlan
ToolboxPromptPreview
ToolboxAudit
ToolboxRunState
ToolboxArtifact
ToolboxInjectionTarget
ToolboxProviderReadiness
```

合约规则：

- `tool_id` 必须来自固定枚举。
- `brand_bundle_ref` 只能引用已存在 bundle 或候选 bundle id，不能携带原始品牌文本。
- `asset_refs` 只能是受治理资产引用，不能是本地任意路径。
- `prompt_preview` 必须脱敏。
- `job_record` 必须包含 `prompt_hash`、`provider_profile_id`、`idempotency_key`。
- `delivery_accepted=false` 是默认状态。

## 5. 五个工具的具体契约

### 5.1 电商商品图

输入：

- `product_ref`
- `sku_metadata`
- `platform`
- `aspect_ratio`
- `image_type`: `main_white_bg`、`lifestyle`、`detail`、`comparison`、`thumbnail`
- `brand_bundle_ref`
- `reference_asset_refs`

输出：

- `ProductImagePlan`
- `ProductImagePromptPreview`
- `ProductImageArtifactManifest`

必须 gate：

- 产品事实不得被改写。
- logo、包装、配色不得越权使用。
- 功效 claim 必须有 evidence ref。
- 母婴产品不得出现医疗化、恐吓式或儿童不安全画面。

### 5.2 产品六视图

输入：

- `product_ref`
- `seed_image_refs`
- `required_views`: `front`、`back`、`left`、`right`、`top`、`detail`
- `consistency_level`
- `brand_bundle_ref`

输出：

- `SixViewPlan`
- `SixViewReferenceManifest`
- `ViewConsistencyAudit`

必须 gate：

- 六个视角不能互相矛盾。
- 关键产品结构不能消失、变形或新增。
- 不得把竞品图、未授权图或含 PII 的素材作为 reference。
- 后续注入视频时必须以 `reference_manifest_id` 传递，不直接复制原图路径。

### 5.3 电商视觉图

输入：

- `campaign_brief`
- `channel`: `shopify`、`amazon`、`tiktok`、`reels`、`youtube_shorts`
- `visual_format`: `banner`、`a_plus`、`social_ad`、`detail_module`
- `copy_blocks`
- `brand_bundle_ref`
- `product_image_refs`

输出：

- `EcommerceVisualPlan`
- `LayoutVariantManifest`
- `CopySafeZoneAudit`

必须 gate：

- 文案不得超出版式安全区。
- 商品与 CTA 不得互相遮挡。
- 平台比例和文本密度必须符合目标渠道。
- 品牌视觉一致性是独立审计维度，不能只看图像美观度。

### 5.4 数字人

输入：

- `presenter_policy`
- `avatar_ref`
- `script_ref`
- `voice_policy`
- `consent_ref`
- `brand_bundle_ref`
- `platform`

输出：

- `DigitalHumanPlan`
- `PresenterShotContract`
- `AvatarRightsAudit`
- `VoiceRightsAudit`

必须 gate：

- 没有肖像授权，不允许真实 avatar 生成。
- 没有声音授权，不允许 voice clone。
- 儿童、家庭、母婴场景不得制造误导性医疗或身份暗示。
- 真实 provider 只能在显式授权和预算上限存在时运行。

### 5.5 故事版

输入：

- `brief`
- `script_ref`
- `duration_target`
- `platform`
- `storyboard_grid`: `6`、`9`、`12`、`24`
- `brand_bundle_ref`
- `asset_refs`

输出：

- `StoryboardPackage`
- `ShotLedger`
- `CameraMotionPlan`
- `AssetRequirementManifest`
- `EditDecisionSeed`

必须 gate：

- 90 秒以上视频必须有 timeline block 和 review checkpoint。
- 不能用单镜头结构伪装长视频。
- S3/S4 必须保留 source fingerprint、rights 和 remix boundary。
- 分镜产物要能回注 S1-S5 的 `storyboards` 或 `continuity_storyboard_grid` 上游。

## 6. 前端设计

### 6.1 新增文件

```text
web/src/app/toolbox/page.tsx
web/src/app/toolbox/[toolId]/page.tsx
web/src/components/toolbox/ToolboxHome.tsx
web/src/components/toolbox/ToolboxNav.tsx
web/src/components/toolbox/ToolCard.tsx
web/src/components/toolbox/ToolRunForm.tsx
web/src/components/toolbox/ToolPromptPreviewPanel.tsx
web/src/components/toolbox/ToolAuditPanel.tsx
web/src/components/toolbox/ToolJobLedgerPanel.tsx
web/src/components/toolbox/ToolArtifactGallery.tsx
web/src/components/toolbox/ToolInjectPanel.tsx
```

更新：

```text
web/src/components/Nav.tsx
web/src/components/api.ts
web/src/components/types.ts
web/src/i18n/translations.ts
web/src/types/api.generated.ts
```

### 6.2 UI 原则

- 工具箱是生产工作台，避免 hero、营销卡片和说明型大段文案。
- 页面密度高，但分区清晰：输入、计划、审计、产物。
- 所有真实生成入口必须显示授权状态和 evidence level。
- 按钮只用于明确动作：`生成计划`、`预览 Prompt`、`Dry-run`、`查看账本`、`回注场景`。
- 工具卡片展示输入要求、输出类型、可回注场景和当前 provider 状态。

### 6.3 页面状态

| 状态 | UI 表达 |
|---|---|
| `not_configured` | 显示缺少 provider/profile/brand bundle，但允许查看计划 |
| `ready_dry_run` | 允许 plan、preview、dry-run |
| `blocked` | 显示 blocking gate 和 repair plan |
| `review_required` | 显示人工审核项，不允许交付 |
| `accepted_dry_run` | 可回注 S1-S5，但不等于商业交付 |
| `authorized_live_ready` | 仅在 C21 授权记录和 env gate 满足后出现 |

## 7. 分阶段 TODO

### T0 文档与边界收口

- [x] 建立本实施计划。
- [x] 将本计划追加为后续代码实现的 source-of-truth。
- [x] 确认旧研究文档仍是依据，不声明工具箱代码完成。

测试：

```bash
git diff --check
```

提交：

```text
docs: 固化AI视频工具箱产品化实施计划
```

### T1 后端工具箱合约

- [x] 新增 `src/models/toolbox_contracts.py`。
- [x] 定义 `tool_id` 枚举和五类工具 request/plan/artifact/audit。
- [x] 新增 fixture 覆盖正常、blocked、review_required。
- [x] 保证 schema 不携带 prompt payload 或品牌资产原文。

测试：

```bash
.venv/bin/python -m pytest tests/test_toolbox_contracts.py
.venv/bin/ruff check src/models/toolbox_contracts.py tests/test_toolbox_contracts.py
git diff --check
```

提交：

```text
feat: 建立AI视频工具箱合约底座
```

### T2 后端 dry-run router

- [x] 新增 `src/routers/toolbox.py`。
- [x] 挂载 `/toolbox/*`，继承 API key auth。
- [x] 实现 `GET /tools`、`POST /plan`、`POST /prompt-preview`、`POST /run`、`GET /runs/{id}`。
- [x] `run` 默认只写 dry-run job ledger，不触发 provider。

测试：

```bash
.venv/bin/python -m pytest tests/test_toolbox_router.py
.venv/bin/ruff check src/routers/toolbox.py src/pipeline/toolbox tests/test_toolbox_router.py
git diff --check
```

提交：

```text
feat: 增加工具箱dry-run接口
```

### T3 OpenAPI 与前端类型

- [x] 运行 OpenAPI drift check。
- [x] 仅在 drift 真实存在时更新 `web/src/types/api.generated.ts`。
- [x] 在 `web/src/components/api.ts` 增加 toolbox API helpers。

测试：

```bash
.venv/bin/python scripts/check_openapi_types_drift.py
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

提交：

```text
chore: 同步工具箱接口类型
```

### T4 前端导航与工具箱首页

- [x] `Nav.tsx` 增加 `工具箱` 一级入口。
- [x] `translations.ts` 增加 zh/en 文案。
- [x] 新增 `/toolbox` 首页。
- [x] 展示五个工具卡片、最近 runs、dry-run evidence 状态。

测试：

```bash
cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && npm test
git diff --check
```

提交：

```text
feat: 增加AI视频工具箱导航与首页
```

### T5 故事版与产品六视图页面

- [x] 新增 `storyboard` 工具页。
- [x] 新增 `six-view` 工具页。
- [x] 展示 prompt preview、audit、job ledger、artifact placeholder。
- [x] 回注按钮只生成 injection draft，不修改 S1-S5 运行状态。

测试：

```bash
cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && npm test
.venv/bin/python -m pytest tests/test_toolbox_router.py tests/test_toolbox_contracts.py
git diff --check
```

提交：

```text
feat: 增加故事版与六视图工具页面
```

### T6 电商商品图与电商视觉图页面

- [x] 新增 `product-image` 工具页。
- [x] 新增 `ecommerce-visual` 工具页。
- [x] 支持 platform、aspect ratio、image type、layout variant。
- [x] 显示 product truth、claim、safe-zone、brand alignment gate。

测试：

```bash
cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && npm test
.venv/bin/python -m pytest tests/test_toolbox_router.py tests/test_toolbox_contracts.py
git diff --check
```

提交：

```text
feat: 增加电商商品图与视觉图工具页面
```

### T7 数字人工具 dry-run

- [x] 新增 `digital-human` 工具页。
- [x] 显示 avatar、voice、consent、likeness、children-safety gate。
- [x] 默认不提供真实生成入口。
- [x] 只有授权记录和 provider readiness 通过后才显示 live-ready 状态。

测试：

```bash
cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && npm test
.venv/bin/python -m pytest tests/test_toolbox_router.py tests/test_toolbox_contracts.py
git diff --check
```

提交：

```text
feat: 增加数字人工具dry-run门禁
```

### T8 工具箱回注 S1-S5

- [x] 新增 `ToolboxInjectionDraft`。
- [x] 支持工具产物回注 S1-S5 的 runtime config 或 step injection refs。
- [x] 只传 refs、ids、checks，不传 prompt payload。
- [x] UI 展示 planned refs vs current step refs 的差异。

测试：

```bash
.venv/bin/python -m pytest tests/test_toolbox_router.py tests/test_scenario_injection_plan.py tests/test_scenario_commercial_injection_projection.py
cd web && npm run lint && npx tsc --noEmit -p tsconfig.json && npm test
git diff --check
```

提交：

```text
feat: 支持工具箱产物回注场景计划
```

### T9 授权真实生成前置

- [x] 复用 C21 授权记录门禁。
- [x] 对每个工具增加 provider readiness preflight。
- [x] 工具级真实 smoke 必须有 provider/model/budget/user approval。
- [x] smoke 结果只升级局部 provider/tool 证据，不升级整体商业交付等级。

实现文件：

- `src/pipeline/toolbox/provider_readiness.py`
- `src/routers/toolbox.py`
- `tests/test_authorized_live_provider_harness.py`
- `configs/authorized-live-token-smoke-approval-template.json`

测试：

```bash
.venv/bin/python -m pytest tests/test_authorized_live_provider_harness.py tests/test_toolbox_router.py
git diff --check
```

提交：

```text
feat: 增加工具箱授权真实生成前置门禁
```

## 8. 优先级

实现顺序固定为：

```text
故事版
  -> 产品六视图
  -> 电商商品图
  -> 电商视觉图
  -> 数字人
```

原因：

- 故事版决定视频、长视频、演示视频和后期裁剪的结构。
- 六视图决定产品一致性，是商品图、视频 reference 和数字人演示的底座。
- 商品图依赖产品 truth 和六视图。
- 电商视觉图依赖商品图、品牌 bundle 和版式安全区。
- 数字人涉及肖像、声音、授权和儿童安全，是合规风险最高的工具。

## 9. 自证规则

- 每个 TODO 独立测试、独立提交。
- 禁止 `git add .`。
- C1-C8/T1-T9 preflight 最高证据等级保持 `L2-fixture-or-dry-run`。
- 真实 provider 调用只能在 T9 且用户显式授权后执行。
- `job succeeded` 不等于 `delivery accepted`。
- `accepted_dry_run` 不等于商业交付。
- 数字人和 voice clone 必须单独检查 consent，不复用普通 brand token。
- 工具箱 UI 不能出现发布、上线、商业交付完成等动作。

## 10. 当前 GAP

| GAP | 当前状态 | 覆盖阶段 |
|---|---|---|
| 顶部导航没有工具箱 | 已实现，`Nav.tsx` 提供 `/toolbox` 一级入口 | T4 |
| 没有 `/toolbox` 路由 | 已实现，含首页和动态工具页 | T4/T5/T6/T7 |
| 没有后端 toolbox router | 已实现，含 tools/plan/prompt-preview/run/runs/artifacts/inject/audit-summary/provider-readiness | T2/T8/T9 |
| 没有工具级统一 contract | 已实现，保持 refs-only 和 L2 边界 | T1 |
| 没有工具级 prompt preview | 已实现，sanitized preview 不暴露 raw prompt | T2/T3 |
| 没有工具级 job ledger UI | 已实现 dry-run job ledger 可见性 | T4-T8 |
| 商品图独立工具 | 已实现 dry-run 页面和 L2 fixture | T6/C22 |
| 六视图独立工具 | 已实现 dry-run 页面和 L2 fixture | T5/C22 |
| 电商视觉图独立工具 | 已实现 dry-run 页面和 L2 fixture | T6/C22 |
| 数字人工具 | 已实现 dry-run 页面和 consent gate，live 仍需单独授权 | T7/T9 |
| 故事版独立工具 | 已实现 dry-run 页面和长视频 review floor | T5 |
| 工具产物回注 S1-S5 | 已实现 refs-only injection draft/audit summary，不写场景状态 | T8 |
| 授权真实生成 | 前置门禁已实现；真实调用未授权、未执行 | T9 |
