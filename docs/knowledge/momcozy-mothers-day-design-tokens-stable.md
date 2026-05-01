---
title: Momcozy Mother’s Day 活动页设计要素与 Token（附件 + 线上采样）
doc_type: knowledge
module: web
topic: design-tokens-momcozy-campaign
status: stable
created: 2026-05-01
updated: 2026-05-01
owner: self
source: human+ai
---

# Momcozy Mother’s Day 活动页 — 设计要素提取

本文档汇总 **URL 可验证采样**（`https://momcozy.com/pages/mothers-day-sale` 页面 HTML 内联样式 + Shopify 主题 CSS 变量）与 **附件 Hero 截图** 的补充色值，用于本项目 UI 调性对齐；并区分 **全站 Warm Chestnut** 与 **活动 Hero/Campaign** 两套语义。

**采样方法说明**：等价于 DevTools 对指定节点的样式读取 — 从页面源码中提取 `mother26_countdown`、`banner-tabs` 等区块的内联 `<style>`，并从 HTML `:root` 读取 `--font-family-*`。

---

## 1. 字体（Theme）

| 角色 | 线上取值 | 备注 |
|------|-----------|------|
| `--font-family-1` / `-2` / `-3` | `Montserrat, sans-serif` | 主题三档变量均指向 Montserrat |
| Hero 内联区块 | 未单独声明 `font-family` | 继承主题，即 **Montserrat** |

**字重需求**：活动 H1 强调行使用 `font-weight: 800`（见下文 `.banner-title p strong`）。本项目 [`web/src/app/globals.css`](../web/src/app/globals.css) 的 Google Fonts 引入需包含 **600–800** 档（已在同文件更新）。

---

## 2. Hero 倒计时区 — 字号 / 字重 / 行高（内联 CSS）

选择器与桌面默认（`max-width: 1024px` 与 `768px` 另有覆盖，文内简称「大屏 / 中屏 / 小屏」）。

### 2.1 标题与副标题

| 选择器 | 属性 | 大屏默认 |
|--------|------|-----------|
| `.banner-title` | `color` | `#fff` |
| | `font-size` | `44px` |
| | `font-weight` | `500` |
| | `line-height` | `0.8` |
| | `text-align` | `left` |
| `.banner-title p strong` | `font-size` | `76px` |
| | `font-weight` | `800` |
| | `letter-spacing` | `1px` |
| `.banner-subtitle` | `font-size` | `24px` |
| | `font-weight` | `400` |
| | `line-height` | `120%` |
| | `padding` | `50px 0 16px` |
| `.countdown-title`（日期文案） | `font-size` | `16px` |
| | `font-weight` | `500` |
| | `line-height` | `120%` |
| | `color` | `#fff` |
| `.mother26__code-desc`（若启用码说明） | `font-size` | `30px` |

**响应式摘录**

- ≤1024px：`.banner-subtitle` → `15px`；`.banner-title p strong` → `48px`；`.countdown-title` → `10px`。
- ≤768px：`.banner-title` → `26px`、`text-align: center`；`.banner-title p strong` → `55px`、`letter-spacing: 0.5px`；`.banner-subtitle` → `14px`、`text-align: center`。

### 2.2 倒计时格子（`.mother26_countdown .brand-countdown`）

| 元素 | 属性 | 大屏默认 |
|------|------|-----------|
| `.countdown-item` | `width` × `height` | `68px` × `73px` |
| | `border-radius` | `8px` |
| | `background` | `#efd8bf` |
| | `color`（数字/标签共用容器） | 数字区实为 `#7b2e40`（见子项） |
| `.countdown-item .num` | `font-size` | `30px` |
| | `font-weight` | `600` |
| | `line-height` | `1` |
| `.countdown-item .label` | `font-size` | `10px` |
| | `font-weight` | `500` |
| | `line-height` | `1.2` |
| `.countdown-dot`（冒号） | `color` | `#efd8bf` |
| | `font-size` | `34px` |
| | `font-weight` | `500` |

小屏详见源码 `@media (max-width: 1024px)` / `(max-width: 768px)`（格子宽高、`border-radius`、`num`/`label` 字号均有缩放）。

---

## 3. 三期卡片 + 时间轴（`.banner-tabs`）

### 3.1 进度条轨与激活段

| 元素 | 属性 | 取值 |
|------|------|------|
| `.progress-bar-bg` | `height` | `6px`（≤767px → `4px`） |
| `.progress-item`（非激活） | `background` | `rgba(247, 238, 228, 0.3)` |
| `.progress-item.active` | `background` | `#f6e2ca` |
| | `border-radius` | `50px` |
| | `width`（桌面） | `calc((100% - 80px) / 3 + 40px)` |

### 3.2 当前阶段圆点（SVG）

- `circle`：`fill="#78273D"`，`stroke="#EFD4BF"`，`stroke-width="3.80952"`（viewBox `20×20`）。

### 3.3 卡片容器（激活 vs 未激活）

| 状态 | `.card-content` `background` | `border-radius` | `padding`（桌面激活） |
|------|------------------------------|-----------------|------------------------|
| `.tab-card.active` | `#f7e7de` | `8px` | `26px 32px` |
| `.tab-card:not(.active)` | `#d9bba3` | `8px` | `24px` |

激活卡片右侧可用 `--card-icon` 做 `::before` 装饰图（宽高远大于文案区，与大屏截图一致）。

### 3.4 卡片标题 / 正文 / Date pill

**激活态**

| 选择器 | 关键样式 |
|--------|-----------|
| `.tab-card.active .card-title` | `color: #77253c`、`font-size: 26px`、`font-weight: 600`、`line-height: 130%` |
| `.tab-card.active .card-description` | `color: #77253c`、`font-size: 16px`、`font-weight: 500` |
| `.tab-card.active .card-date` | `background: linear-gradient(90deg, #b36a6f -7.04%, #7b2e40 100%)`、`color: #fff`、`padding: 6px 16px`、`border-radius: 18px 20px 20px 18px`、`font-size: 16px`、`font-weight: 600`、`min-width: 163px` |

**未激活态**

| 选择器 | 关键样式 |
|--------|-----------|
| `.tab-card:not(.active) .card-title` | `font-size: 28px`（注意反直觉：未激活标题字号略大于激活），其余同色 `#77253c` |
| `.tab-card:not(.active) .card-date` | `background: #af7666`、`color: #f0ebe3`、`font-size: 14px`、`border-radius: 20px` |

≤1024px / ≤767px breakpoint 下文案与 pill 字号显著缩小（如标题 `14px`、描述 `8px`），详见页面内联样式。

---

## 4. 页面分区背景色（HTML section `style` 抽样）

以下为 Mother’s Day 页 **区块级** `--bg-color`，用于 Landing 分段配色参考（非单一 Hero 渐变）。

| 色值 | 出现语境（节选） |
|------|------------------|
| `#faf5f2` | 多段促销 / 列表容器 |
| `#f7e7de` | 卡片促销条、部分内容条 |
| `#fcf8f4` | 宽 section |
| `#fde9dd` | Mystery Box / 强调粉橘分段 |
| `#fef8f1` | FAQ 等区域 |
| `#f9f6eb` | Footer 上沿 |

促销卡片上还出现 **`--btn-bg-color: #9D5456`**、`--btn-hover-bg-color: #77253C`**、`--text-color: #333333`**（与 [`pd.css`](https://cdn.shopify.com/s/files/1/0559/2321/2486/t/79/assets/pd.css) 中 `--title-color: #9c5455` 同族）。

---

## 5. 附件 Hero 截图补充（光学抽样，用于渐变 / 深色托底）

线上内联样式以 **分段纯色与单品配图** 为主；若需复刻「大片摄影 + 上下分区」观感，可在 `--campaign-hero-*` 上使用以下 **近似 hex**（与 [`web/src/app/globals.css`](../web/src/app/globals.css) 中变量一致）：

- 上层暖陶土参照：`#9B6254`
- 下层深托底：`#4A2C2A`
- 非强调卡纸色：`#F2E1D9`
- 强调卡纸色：`#FDF2F0`
- 主白字：`#FFFFFF`
- 卡片标题莓红：`#702F3B`
- Date pill（与线上 gradient 并存方案）：`#8C4E5E`

**注意**：具体以 **第 3、4 节线上 hex** 为工程默认值；本节用于艺术方向与渐变 stop 设计。

---

## 6. Mood 分档（附件中的非 Momcozy 参考）

勿与 Mother’s Day tokens 混用为单一切面；如需 A/B 或子品牌页，单独命名：

| 代号 | 来源 | 特征 |
|------|------|------|
| **Mood-A — Mother’s Day Warm Terracotta** | Momcozy 活动页 + Hero 截图 | 低饱和陶土/酒红、圆角卡片、轻线时间轴 |
| **Mood-B — Organic Yellow Condensed** | Dojolia 附件 | 黄径向渐变、`#000` 粗 condensed 标题、白 pill 徽章 |
| **Mood-C — Vivid Flavor Grid** | 口味卡片附件 | 薄荷底 `#E0F7E0`、每卡独立高饱和渐变、blob + 实拍抠图、全大写 condensed 标题、五星甜度条 |

本项目默认产品调性建议以 **Mood-A** 对齐；B/C 仅作扩展 moodboard。

---

## 7. 组件映射 — 本项目代码 vs Momcozy 模块

| Momcozy 模块 | 行为 / 视觉 | 本项目对应 | 缺口 |
|--------------|-------------|------------|------|
| Hero + H1 拆行强调 | 双行 `<strong>`、800 字重 | [`SplashScreen.tsx`](../web/src/components/SplashScreen.tsx) 顶区标题 | Splash 当前为单行 `Momcozy`、字重 500；若对齐活动需多行结构与 800 档 |
| `simple-countdown` | 四格 + 冒号 + 标签 | 无现成同源组件 | 需新建 `CampaignCountdown` 或扩展 `ExecutionBar` / 活动页专用块 |
| `.banner-tabs` 三态进度条 + 圆点 | 三段比例条 + SVG 节点 | [`StageProgress.tsx`](../web/src/components/StageProgress.tsx) 为三阶段流水线进度 | Momcozy 为 **等分时间轴 + 中点激活点**；数据结构不同，需 **新「PhaseTabs」** 或主题化 StageProgress |
| 三期 `.tab-card` | 激活扩宽 + 右侧 `::before` 图 | [`GuidedCard`](../web/src/components/GuidedCard.tsx)、[`AssetCard`](../web/src/components/AssetCard.tsx) | 缺少 **横向三卡 + progress 联动 + 渐变 date pill** 的复合区块 |
| Date pill | 圆角 capsule / gradient | 可用 `rounded-full` + `bg-gradient-to-r` | 无封装 `DatePill`；建议小颗粒组件 |
| 顶栏促销 Marquee | emoji + CTA | [`Nav.tsx`](../web/src/components/Nav.tsx) | 无 announcement bar；可加可选 `TopPromoBar` |
| 商品卡 | 白底圆角 16px、`#644f48` 标题（`activity-resources.css`） | [`AssetCard`](../web/src/components/AssetCard.tsx) 等 | 色与圆角可对齐 `--campaign-*` + 现有 surface tokens |

---

## 8. 工程内 Token 草案位置

Campaign 语义变量已写入 [`web/src/app/globals.css`](../web/src/app/globals.css) `:root`（`--campaign-*`）。全站继续使用 `--brand-*` / `--surface-*`；活动 / 封面 / 运营页优先用 `--campaign-*`，避免全局粉面被季节性活动拖偏。

---

## 9. 仍建议人工复核项

1. Hero **背景图 URL** 与 **摄影师版权** — 本项目应使用自有素材或授权图，仅复用色与布局节奏。  
2. **暗色模式**：Momcozy 该页未提供 dark tokens；若本站需要，须基于对比度单独推导。  
3. 活动结束后面向 `simple-countdown` 的脚本可能 **隐藏倒计时** — 采样时需注意节点是否 `display: none`。  

---

## 参考链接

- 活动页：`https://momcozy.com/pages/mothers-day-sale`  
- 主题字体变量与内联样式：页面 HTML（`mother26_countdown`、`banner-tabs` 区块）。  
- 辅助配色：`pd.css`（Shopify CDN `.../assets/pd.css`）、`activity-resources.css`。
