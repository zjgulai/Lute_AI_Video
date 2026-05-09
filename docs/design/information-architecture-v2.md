---
name: information-architecture-v2
description: Frontend information architecture v2 for Short Video Factory. Defines the 4-tab top navigation, the route migration map, and the backend `kind` field contract that supports the new asset-lifecycle model. Use when implementing Phase 1 of the UX redesign.
---

# Information Architecture v2

> **写在前面**：这份文档是 Phase 1 全部代码改动的"宪法"。任何路由、导航、API 字段的修改必须先在这里更新，再去改代码。

## 1. 设计原则

1. **资产按"生命周期"分层，而不是按"存储来源"分层**。用户不关心一段视频来自 Seedance 还是手动上传；用户关心它是「能发的成品」「在做的素材」还是「品牌底子」。
2. **One Concept Per Page** — 每个顶层路由只承担一个心智模型。
3. **路由 URL 是产品语言** — `/works`「我的作品」、`/library`「资产库」，名字就告诉你能在那里做什么。
4. **保留可深链的 URL** — 所有旧外链通过 301 自动到位，不破坏书签和分享链接。

---

## 2. 顶部导航（4 项）

```
┌─────────────────────────────────────────────────────────────┐
│  Logo  首页 ──┬── 我的作品 ── 资产库 ─── 设置  ────  中/EN │
└────────┴──────┴──────────────────────────────────────────────┘
```

| 序 | 名称 | 路由 | i18n 键 | 入口职责 |
|---|---|---|---|---|
| 1 | 首页 | `/` | `nav.home` | **创作起点**：5 个场景 + Fast Mode |
| 2 | 我的作品 | `/works` | `nav.works` | **成品仓库**：所有 `final_work`（可发布、可分享、可下载）|
| 3 | 资产库 | `/library` | `nav.library` | **生产素材**：原始素材 / 品牌包 / 网红档案 |
| 4 | 设置 | `/settings` | `nav.settings` | API key、后端 URL、语言、个人信息 |

### 为什么是 4 项不是 5 项？

- 「**网红**」从顶级降为 `/library` 的子 Tab。
  - 当前线上影响者数量 = 0，独立顶级路由是结构浪费。
  - 网红只在 S3 流程里被引用，属于"生产资产"性质，归入 Library 更准确。
- 「**素材**」「**品牌包**」「**网红**」三类共享同一个心智："为创作准备的物料"。
- 「**作品**」单独成项，是因为这是用户的**结果**，不是过程。结果和过程必须视觉分离。

### 文字预算

```
首页 (2) + 我的作品 (4) + 资产库 (3) + 设置 (2) = 11 汉字
```

满足计划约束 ≤ 12 汉字，留 1 字余量给可能的语言切换浮动。

---

## 3. 路由迁移映射表（权威版本）

| 旧路由 | 当前职责 | 新去向 | 重定向类型 |
|---|---|---|---|
| `/` | 首页 / 场景选择 | `/`（不变） | — |
| `/s1` `/s2` `/s3` `/s5` | 场景表单 | 同上不变 | — |
| `/fast` | Fast Mode 入口 | 同上不变 | — |
| `/result` | 单次流水线结果展示 | 同上不变 | — |
| `/settings` | 设置面板 | `/settings`（顶级独立化） | — |
| `/footage` | "AI Portfolio" — 实际混合：成品 mp4 + 中间素材 | **拆分**：成品 → `/works`，中间素材 → `/library?tab=materials` | 默认重定向到 `/works`（user intent 多数是看成品） |
| `/brand-packages` | "Brand Assets" — 实际承担 425 项混合资产 | `/library?tab=brand_kit` | 301 |
| `/influencers` | "Influencers" 孤儿路由 | `/library?tab=influencers` | 301 |
| `/admin/*` | 管理后台 | 不变 | — |

> **重定向实现**：每个旧路由的 `page.tsx` 改为只导出一个 Server Component，调用 `next/navigation` 的 `redirect(target)`。不再渲染任何 UI。

---

## 4. `/library` 内部结构（三 Tab 设计）

```
┌────────────────────────────────────────────────────────────┐
│  ← 返回首页    资产库                              + 上传 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   素材  |  品牌包  |  网红                                 │
│   ────                                                     │
│                                                            │
│   [搜索框                          ][筛选]                 │
│                                                            │
│   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                          │
│   │卡片 │ │卡片 │ │卡片 │ │卡片 │                          │
│   └─────┘ └─────┘ └─────┘ └─────┘                          │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 4.1 Tab：素材（`/library?tab=materials`）

| 内容来源 | 说明 |
|---|---|
| 用户上传的原始素材 | `/api/assets` 中 `kind=creation_intermediate` 且 `source=user_upload` |
| 流水线生成的中间产物 | `/portfolio/?category=seedance|gpt_images|audio|keyframes` |
| **不显示** | `final_work`（在 `/works`）、`brand_kit`（在另一个 Tab） |

筛选维度（**只保留一层**，砍掉旧 `/brand-packages` 的双重 filter）：
- 类型：全部 / 视频 / 图片 / 音频
- 来源（次要，折叠）：用户上传 / AI 生成

### 4.2 Tab：品牌包（`/library?tab=brand_kit`）

| 内容来源 | 说明 |
|---|---|
| Logo / 品牌色 / 字体 | 用户主动上传，`kind=brand_kit` |
| Brand Voice 文档 | 文本资产，`kind=brand_kit` 且 `mime_type=text/*` |
| **不显示** | 任何流水线产物 |

预期数量：**≤ 20 项**（设计预算）。如果超过 20，UI 触发"建议归档"提示。

### 4.3 Tab：网红（`/library?tab=influencers`）

直接复用 [influencers/page.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/influencers/page.tsx#L21) 的 CRUD 逻辑，但：
- 嵌入到 `/library` 的 Tab 容器内（不再是独立路由）
- 删除当前空状态的"重复 Add Influencer 按钮"问题
- 表单 a11y 改造留到 Phase 3

---

## 5. `/works` 设计

```
┌────────────────────────────────────────────────────────────┐
│  ← 返回首页    我的作品                                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   [所有] [商品直拍] [品牌宣传] [网红二创] [品牌VLOG]       │
│                                                            │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐                      │
│   │成品视频 │ │成品视频 │ │成品视频 │                      │
│   │商品直拍 │ │品牌VLOG │ │商品直拍 │                      │
│   │5月9日   │ │5月8日   │ │5月7日   │                      │
│   └─────────┘ └─────────┘ └─────────┘                      │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

| 内容来源 | 说明 |
|---|---|
| 后端：`/portfolio/?category=renders` | `final_work` 严格定义：经过完整 16-node pipeline 的 `assemble_final` 输出 |
| 后端：`/portfolio/?category=fast_mode` | Fast Mode 直出的成品 |
| 前端：localStorage `hermes_gallery_items` | 兼容旧版本本地存储的成品（向后兼容） |

筛选：按场景（all / s1 / s2 / s3 / s5）。

卡片信息层级（重要，避免暴露原始文件名）：
1. **主标题**：`{briefs[0].product_name}` 或 i18n `scene.{id}.title`，**不显示** `s1.mp4`
2. **副标题**：场景标签（小胶囊）
3. **角标**：日期（`5月9日`）+ 时长（`30s`）
4. **悬浮显示**：原始文件名（debugging 友好）

---

## 6. 后端 API 字段契约（`kind` 引入）

### 6.1 当前问题

[`/portfolio/`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py#L23-L38) 用 `category` 字段（`renders` / `seedance` / `gpt_images` 等）—— 这是**存储分桶**，不是**生命周期阶段**。前端要做大量字符串猜测（[brand-packages/page.tsx:106-123](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/brand-packages/page.tsx#L106-L123) `inferSourceFromPath` 全是脆的 includes）。

### 6.2 新增 `kind` 字段（最小侵入）

在 [PortfolioFile](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py#L68) 模型中增加：

```python
class PortfolioFile(BaseModel):
    # ... 现有字段保留
    kind: Literal["final_work", "creation_intermediate", "brand_kit"] = "creation_intermediate"
```

`kind` 派生规则（在 `_scan_portfolio()` 中计算，**不需要新存储**）：

```python
# Mapping: category → kind
KIND_BY_CATEGORY = {
    "renders":      "final_work",        # 完整流水线成片
    "fast_mode":    "final_work",        # Fast Mode 成片
    "seedance":     "creation_intermediate",
    "gpt_images":   "creation_intermediate",
    "audio":        "creation_intermediate",
    "keyframes":    "creation_intermediate",
    "thumbnails":   "creation_intermediate",
    "character_identity": "creation_intermediate",
    "fast_mode":    "final_work",
    "uploads":      "creation_intermediate",  # 用户原始上传
    "assets":       "creation_intermediate",  # 通用
    "demo":         "creation_intermediate",
    "quality-test": "creation_intermediate",
}
# brand_kit 暂时不会出现在 portfolio 扫描里
# （它通过 /api/assets/brand-packages 走另一条路）
```

### 6.3 前端查询能力

新增查询参数 `kind`：

```
GET /portfolio/?kind=final_work&limit=50
GET /portfolio/?kind=creation_intermediate
```

**向后兼容**：`category` 参数保留可用，老前端不破坏。

### 6.4 不修改的点

- [`/api/assets`](file:///Users/pray/project/hermes_evo/AI_vedio/src/api_assets.py#L223)（`api_assets.py`，遗留 in-memory dict 路由）：保持不变。在 AGENTS.md 里被标为"不要新增功能"，因此 brand_kit / influencer 数据继续走它，但**前端不依赖它来推断 kind**。
- 流水线代码：不动。
- 数据库 schema：不动。
- 文件存储路径：不动。

---

## 7. 状态机（资产生命周期）

详见独立文档：[asset-lifecycle-state-machine.md](./asset-lifecycle-state-machine.md)。

简版：

```
            ┌─────────┐    upload      ┌─────────────┐
            │  user   │ ─────────────> │  uploads/   │
            └─────────┘                └─────────────┘
                                              │
                                              │ used as input
                                              ▼
            ┌─────────┐    pipeline   ┌─────────────────┐
            │ trigger │ ────────────> │ creation_       │
            │ pipeline│                │ intermediate    │
            └─────────┘                │ (seedance/      │
                                       │  gpt_images/    │
                                       │  audio/         │
                                       │  keyframes/)    │
                                       └─────────────────┘
                                              │
                                              │ assemble_final
                                              ▼
                                       ┌─────────────────┐
                                       │  final_work     │
                                       │  (renders/      │
                                       │   fast_mode/)   │
                                       └─────────────────┘
                                              │
                                              │ publish
                                              ▼
                                       ┌─────────────────┐
                                       │  published      │
                                       │  (TikTok/etc.)  │
                                       └─────────────────┘

            ┌─────────┐    upload      ┌─────────────┐
            │  user   │ ─────────────> │  brand_kit  │ (logo/colors/voice)
            └─────────┘                └─────────────┘
                                              │
                                              │ referenced
                                              ▼
                                        pipeline input
```

---

## 8. 决策日志

| 时间 | 决策 | 理由 | 影响范围 |
|---|---|---|---|
| 2026-05-09 | `/footage` 默认 301 到 `/works` 而不是 `/library?tab=materials` | 实测多数用户 intent 是看成品而非中间素材 | 路由层 |
| 2026-05-09 | 网红降为 `/library` 子 Tab 而非顶级 | 当前实例数=0，独立路由是结构浪费 | 顶栏 |
| 2026-05-09 | `kind` 在后端派生而不要新存储 | 最小侵入；现有 category 已足够推断 | 后端 1 文件 |
| 2026-05-09 | 不动 `/api/assets` 路由 | AGENTS.md 明确遗留路由 | 兼容性 |
| 2026-05-09 | `/works` 卡片标题用 `briefs[0].product_name` 不用 filename | 用户语言 vs 工程语言 | 前端展示 |

---

## 9. Phase 1 实施 checklist（与计划锚定）

- [ ] 本文档（`information-architecture-v2.md`）写完并被用户审阅
- [ ] [`asset-lifecycle-state-machine.md`](./asset-lifecycle-state-machine.md) 写完并被用户审阅
- [ ] [`Nav.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/Nav.tsx) 改 4 项导航
- [ ] [`web/src/app/works/page.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/works/page.tsx) 新建
- [ ] [`web/src/app/library/page.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/library/page.tsx) 新建 + 三 Tab 子组件
- [ ] `/footage` `/brand-packages` `/influencers` 改为 301 重定向
- [ ] [`src/routers/portfolio.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py) 增加 `kind` 字段
- [ ] V1.3.a / V1.3.b / V1.3.c / V1.3.d 全部跑通
