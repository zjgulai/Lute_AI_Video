---
name: asset-lifecycle-state-machine
description: Canonical state machine describing every stage of an asset's life inside Short Video Factory — upload, pipeline intermediate, final work, published. Maps each state to a backend category, a `kind` discriminator, a frontend surface, and a user-visible label. Use when designing UI, debugging data misclassification, or adding new producers/consumers of assets.
---

# Asset Lifecycle State Machine

> 一张图看懂 Short Video Factory 里每个文件的"人生阶段"。
> 这份文档的唯一目的：让 IA、后端和前端三方对一个资产**现在处于哪个状态**达成共识。

## 1. 六个状态（State）

| 状态 | 含义 | 典型例子 |
|---|---|---|
| **`brand_kit`** | 品牌底子。用户主动维护的"身份资产"。 | Logo、主色、Brand Voice 文档、字体规范 |
| **`uploaded`** | 用户原始上传。等待进入流水线或被复用。 | 手机拍的产品图、抖音下载的参考视频 |
| **`intermediate`** | 流水线中间产物。单步可用但不是最终交付。 | Seedance 生成的某个 clip、CosyVoice 的 TTS 片段、关键帧图 |
| **`pending_review`** | 已真实生成但还未人工确认的待审素材。只能复核、预览、筛选，不能发布或写入正式品牌资产。 | 授权 poyo smoke 生成的 Momcozy 消毒器 3 图 + 15 秒视频 |
| **`final_work`** | 完整流水线成片。可发布、可分享、可下载。 | `renders/s1_with_audio.mp4`、`fast_mode/xxx.mp4` |
| **`published`** | 已分发到外部平台。 | TikTok 视频 URL、Shopify 商品页嵌入 |

---

## 2. 完整状态机图

```
                        ┌───────────────┐
                        │   brand_kit   │◄─────── 用户主动上传（不参与流程转移）
                        │  (logo/color/ │           仅在流水线启动时作为 reference 被读取
                        │   voice/font) │
                        └───────────────┘

                                │ (referenced by pipeline, never consumed)
                                ▼
    ┌──────────┐             ┌─────────────────────────────┐
    │   user   │  upload     │                             │
    │          │───────────▶│         uploaded            │
    └──────────┘             │  (uploads/, manual drop)   │
                              └──────┬──────────────────────┘
                                     │ consumed as pipeline input
                                     ▼
                              ┌───────────────────────────────┐
                              │        intermediate           │
                              │                               │
                              │  ┌──────────┐ ┌──────────┐    │
                              │  │ seedance │ │gpt_images│    │
                              │  └──────────┘ └──────────┘    │
                              │  ┌──────────┐ ┌──────────┐    │
                              │  │  audio   │ │keyframes │    │
                              │  └──────────┘ └──────────┘    │
                              │  ┌──────────────────────┐     │
                              │  │ character_identity   │     │
                              │  │ thumbnails           │     │
                              │  └──────────────────────┘     │
                              │  ┌──────────────────────┐     │
                              │  │ pending_review       │     │
                              │  │ (authorized smoke)   │     │
                              │  └──────────────────────┘     │
                              └──────┬────────────────────────┘
                                     │ assemble_final node succeeds
                                     ▼
                              ┌───────────────────────────────┐
                              │         final_work            │
                              │                               │
                              │  ┌──────────┐ ┌──────────┐    │
                              │  │ renders  │ │fast_mode │    │
                              │  └──────────┘ └──────────┘    │
                              └──────┬────────────────────────┘
                                     │ user clicks "发布"
                                     ▼
                              ┌───────────────────────────────┐
                              │         published             │
                              │  (TikTok / Shopify / Reddit)  │
                              └───────────────────────────────┘
```

---

## 3. 状态 ↔ 后端 `category` ↔ 前端 `kind` 映射表

| 状态 (state) | 存储分桶 (backend `category`) | API discriminator (`kind`) | 前端 Surface | 用户可见标签 |
|---|---|---|---|---|
| `brand_kit` | N/A（走 `/api/assets/brand-packages` in-memory） | `brand_kit` | `/library?tab=brand_kit` | 品牌包 |
| `uploaded` | `uploads/` | `creation_intermediate` | `/library?tab=materials` | 原始素材 |
| `intermediate` | `seedance/` `gpt_images/` `audio/` `keyframes/` `character_identity/` `thumbnails/` `demo/` `quality-test/` `assets/` | `creation_intermediate` | `/library?tab=materials`（折叠分类：AI 生成）| 中间素材 |
| `pending_review` | `pending_review/` | `creation_intermediate` + `review_status=pending_review` | `/library?tab=materials` | 待审 |
| `final_work` | `renders/` `fast_mode/` | `final_work` | `/works` | 我的作品 |
| `published` | 仅在 `publish_logs` 表中有记录 | N/A（当前不是文件） | `/works` 的发布状态 badge | 已发布 |

> **关键约定**：前端永远只根据 `kind` 派发到哪个页面；`category` 只在素材 Tab 的次级筛选里作为"来源标签"露出。

---

## 4. 转移规则（Transitions）

| From | To | 触发条件 | 数据动作 | 用户可见反馈 |
|---|---|---|---|---|
| — | `brand_kit` | 用户在 `/library?tab=brand_kit` 上传 Logo / 填写品牌色 | `POST /api/assets/brand-packages` | "品牌包已更新" toast |
| — | `uploaded` | 用户在 `/library?tab=materials` 或场景表单中上传素材 | `POST /api/upload` → 存 `uploads/` | "上传成功" toast + 卡片显现 |
| `uploaded` | `intermediate` | 流水线节点消费该素材（e.g. `storyboard` → `media_generation`） | 生成新文件到 `seedance/` 等 | 流水线进度条推进 |
| — | `intermediate` | 流水线自主生成（e.g. Seedance、GPT-Image） | 写入对应 category 目录 | 进度条推进 |
| — | `pending_review` | 授权真实 smoke 或人工导入待审资产 | 写入 `pending_review/` 并返回 `review_status=pending_review` | 素材库出现"待审" badge |
| `intermediate[N]` | `final_work` | `assemble_final` 节点成功，Remotion 组装 | 写入 `renders/` | "成片已生成" toast + `/works` 出现新卡片 |
| — | `final_work` | Fast Mode 直接产出 | 写入 `fast_mode/` | 同上 |
| `final_work` | `published` | 用户点击 `PublishPanel` 的发布按钮 | 调分发 connector + 写 `publish_logs` | 卡片角标变为"已发布 on TikTok" |

### 不允许的转移

- `final_work` → `intermediate`（成片不会回退到中间状态）
- `pending_review` → `final_work`（待审素材必须先被人工纳入场景或正式流水线，不能直接变成成片）
- `pending_review` → `published`（未人工验收不得发布）
- `published` → 任何其他状态（已发布不可撤回，除非用户手动重新上传）
- `brand_kit` → 任何（品牌包是独立字典，不流动）

---

## 5. 为什么这个状态机是对的

### 5.1 解决的老问题

| 老问题 | 新状态机怎么解决 |
|---|---|
| `/brand-packages` 把 425 个中间产物混进"品牌资产" | `kind=brand_kit` 单独隔离；扫描结果 ≤ 20 项 |
| `/footage` 里 `s1.mp4` 和 `seedance_xxxx.mp4` 都显示 | `/works` 只取 `kind=final_work`；中间产物在 `/library` |
| 前端 `inferSourceFromPath` 用 `includes('seedance')` 猜测来源 | 后端直接返回 `kind`，前端不再做字符串猜谜 |
| 成片和素材混排后用户找不到"能发的东西" | `/works` 专为成片服务，卡片标题是产品名而非文件名 |

### 5.2 保持正交的原则

每个状态**回答一个问题**：

- `brand_kit` — 「这是我的品牌身份吗？」
- `uploaded` — 「这是我主动放进来的原料吗？」
- `intermediate` — 「这是机器正在做的中间步骤吗？」
- `pending_review` — 「这是已经真实生成、但还需要人工决定能不能成为品牌资产吗？」
- `final_work` — 「这是能交给客户/市场的成品吗？」
- `published` — 「这已经发出去了吗？」

同一个文件**不能同时**处于两个状态——这是检验状态机健康度的标尺。

---

## 6. 实施提醒（给 Phase 1 的下一步）

1. 后端 [`portfolio.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py) 加 `kind` 字段时，直接用第 3 节映射表。
2. 前端 `/works` 页查询：`GET /portfolio/?kind=final_work&limit=50&sort=recent`。
3. 前端 `/library?tab=materials` 查询：`GET /portfolio/?kind=creation_intermediate`。
4. 前端 `/library?tab=brand_kit` 查询：`GET /api/assets/brand-packages`（保持现状）。
5. 前端 `/library?tab=influencers` 查询：`GET /api/assets/influencers`（保持现状）。

---

## 7. 未来扩展（非 Phase 1 范围）

这几个状态是**预留的**但当前不实现，避免过度设计：

| 状态 | 何时需要 |
|---|---|
| `draft` | 当流水线支持"暂存未跑完"的场景 |
| `archived` | 当用户主动归档不想删的旧作品 |
| `template` | 当 final_work 被标为可复用模板给他人 |

这些状态加入时，**只需在 `kind` 字段里加枚举值**，不破坏现有契约。
