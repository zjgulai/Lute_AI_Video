# Fortune Red Cinema — 影视级发财红设计系统

> **项目**: Root Innovation Video Creation Platform  
> **版本**: v1.0 Final  
> **模式**: 浅色模式 (Light Mode) + 深色影视模式 (Dark Cinema Mode)  
> **核心色**: 发财红 #D75C70  
> **设计哲学**: 深色模式下发财红如 DaVinci Resolve 指示灯般发光工作；浅色模式下如人民币般喜庆温暖。金色引导线赋予卡片间流程以影视品质感。

---

## 目录

1. [色彩系统 Color System](#1-色彩系统-color-system)
2. [深色模式色彩映射 Dark Mode Mapping](#2-深色模式色彩映射-dark-mode-mapping)
3. [浅色模式色彩映射 Light Mode Mapping](#3-浅色模式色彩映射-light-mode-mapping)
4. [文字层级 Typography](#4-文字层级-typography)
5. [引导线系统 Connector Lines](#5-引导线系统-connector-lines--核心设计)
6. [组件配色 Component Colors](#6-组件配色-component-colors)
7. [按钮系统 Button System](#7-按钮系统-button-system)
8. [卡片系统 Card System](#8-卡片系统-card-system)
9. [表单系统 Form System](#9-表单系统-form-system)
10. [导航栏 Navigation](#10-导航栏-navigation)
11. [选项卡 Tabs](#11-选项卡-tabs)
12. [状态反馈 Status & Feedback](#12-状态反馈-status--feedback)
13. [分割线与边框 Dividers & Borders](#13-分割线与边框-dividers--borders)
14. [渐变方案 Gradients](#14-渐变方案-gradients)
15. [电影感特效 Cinematic Effects](#15-电影感特效-cinematic-effects)
16. [当前网站 vs 优化对比](#16-当前网站-vs-优化对比)
17. [实施优先级清单](#17-实施优先级清单-implementation-checklist)
18. [CSS Variables 快速接入](#18-css-variables-快速接入)

---

## 1. 色彩系统 Color System

### 1.1 核心色板（通用，不区分模式）

| Token | HEX | RGB | HSL | 用途说明 |
|-------|-----|-----|-----|---------|
| `--fortune-red` | `#D75C70` | 215, 92, 112 | 350°, 60%, 61% | 品牌主色，Active态，选中边框 |
| `--cinnabar` | `#D04E5A` | 208, 78, 90 | 355°, 56%, 58% | 品牌深色调，渐变终点 |
| `--neon-red` | `#FF4D6A` | 255, 77, 106 | 350°, 100%, 65% | 核心发光色，CTA按钮，Focus态 |
| `--misty-pink` | `#EAAFB7` | 234, 175, 183 | 352°, 58%, 80% | 辅助粉色，引导线，轻边框 |
| `--coral-orange` | `#F37969` | 243, 121, 105 | 7°, 85%, 68% | CTA强调，Hover边框 |
| `--ember-glow` | `#B44658` | 180, 70, 88 | 350°, 44%, 49% | Hover次级强调 |
| `--crimson-mist` | `#8C3C4B` | 140, 60, 75 | 350°, 40%, 39% | 装饰性边框，错误态边框 |

### 1.2 影视暗色基底（Dark Mode Only）

| Token | HEX | RGB | 用途说明 |
|-------|-----|-----|---------|
| `--cinema-black` | `#100C0D` | 16, 12, 13 | 页面最底层背景 |
| `--film-reel` | `#1C1415` | 28, 20, 21 | 卡片/面板背景 |
| `--dark-slate` | `#2A1E20` | 42, 30, 32 | 二级面板/侧边栏/选中卡片背景 |
| `--charcoal-rose` | `#3A2A2D` | 58, 42, 45 | 三级层级/折叠面板 |
| `--warm-shadow` | `#4E3A3D` | 78, 58, 61 | 默认边框/分割线 |

### 1.3 人民币品质点缀（通用）

| Token | HEX | RGB | 用途说明 |
|-------|-----|-----|---------|
| `--gold-foil` | `#DCBE78` | 220, 190, 120 | VIP标签/成就徽章/进度条/关键引导线 |
| `--antique-gold` | `#B99B5F` | 185, 155, 95 | 引导线/时间轴 |
| `--pale-gold` | `#A58C5A` | 165, 140, 90 | 轻分割线/辅助装饰线 |
| `--jade-accent` | `#78AF8C` | 120, 175, 140 | 成功状态/已完成路径 |
| `--cool-steel` | `#829BAF` | 130, 155, 175 | 信息提示/技术参数 |

### 1.4 浅色模式专用背景色

| Token | HEX | RGB | 用途说明 |
|-------|-----|-----|---------|
| `--canvas-light` | `#FCF6F7` | 252, 246, 247 | 浅色模式页面背景 |
| `--surface-white` | `#FFFFFF` | 255, 255, 255 | 卡片表面/面板 |
| `--elevated-white` | `#FEFBFA` | 254, 251, 250 | 悬浮层/Dropdown/Modal |
| `--accent-cream` | `#F2EBC8` | 242, 235, 200 | 特色功能区/Hero区块背景 |

---

## 2. 深色模式色彩映射 Dark Mode Mapping

> 深色模式为**主要推荐模式**，具有影视专业感。

### 2.1 页面层级背景

| 层级 | Token | 值 | CSS Variable |
|------|-------|-----|-------------|
| 页面背景 | `--dm-bg-page` | `#100C0D` | `var(--cinema-black)` |
| 卡片背景 | `--dm-bg-card` | `#1C1415` | `var(--film-reel)` |
| 二级面板 | `--dm-bg-panel` | `#2A1E20` | `var(--dark-slate)` |
| 三级层级 | `--dm-bg-layer3` | `#3A2A2D` | `var(--charcoal-rose)` |
| 选中卡片背景 | `--dm-bg-selected` | `#2A1E20` | `var(--dark-slate)` |
| Hover卡片背景 | `--dm-bg-hover` | `#1C1415` | `var(--film-reel)` |
| 侧边面板 | `--dm-bg-sidebar` | `#2A1E20` | `var(--dark-slate)` |
| Modal/Dropdown | `--dm-bg-elevated` | `#1C1415` | `var(--film-reel)` |

### 2.2 边框映射

| 状态 | Token | 值 | 宽度 |
|------|-------|-----|------|
| 默认边框 | `--dm-border-default` | `#4E3A3D` | 1px |
| 选中边框 | `--dm-border-selected` | `#D75C70` | 2px |
| Hover边框 | `--dm-border-hover` | `#FF4D6A` | 2px + glow |
| 错误边框 | `--dm-border-error` | `#8C3C4B` | 2px |
| 成功边框 | `--dm-border-success` | `#78AF8C` | 1px |
| 金色强调边框 | `--dm-border-gold` | `#DCBE78` | 1px |

### 2.3 文字颜色

| 层级 | Token | 值 | 用途 |
|------|-------|-----|------|
| Display标题 | `--dm-text-display` | `#FFF8F5` | Hero大标题 |
| H1标题 | `--dm-text-h1` | `#FAF0EB` | 页面标题 |
| H2副标题 | `--dm-text-h2` | `#EBDCD7` | 区块标题 |
| 正文 | `--dm-text-body` | `#D2C3BE` | 内容文字 |
| 辅助文字 | `--dm-text-muted` | `#A0918E` | Caption/辅助说明 |
| 占位符 | `--dm-text-placeholder` | `#6E6260` | 输入框占位符 |
| 禁用文字 | `--dm-text-disabled` | `#4E413F` | 禁用态文字 |
| 链接文字 | `--dm-text-link` | `#D75C70` | 可点击链接 |
| Active链接 | `--dm-text-link-active` | `#FF4D6A` | 当前页链接 |

---

## 3. 浅色模式色彩映射 Light Mode Mapping

> 浅色模式为**辅助模式**，用于需要明亮环境的场景。

### 3.1 页面层级背景

| 层级 | Token | 值 | CSS Variable |
|------|-------|-----|-------------|
| 页面背景 | `--lm-bg-page` | `#FCF6F7` | `var(--canvas-light)` |
| 卡片背景 | `--lm-bg-card` | `#FFFFFF` | `var(--surface-white)` |
| 二级面板 | `--lm-bg-panel` | `#FEFBFA` | `var(--elevated-white)` |
| 选中卡片背景 | `--lm-bg-selected` | `#FCF6F7` | `var(--canvas-light)` |
| Hover卡片背景 | `--lm-bg-hover` | `#FFFFFF` | `var(--surface-white)` |
| 特色功能区 | `--lm-bg-accent` | `#F2EBC8` | `var(--accent-cream)` |
| Modal/Dropdown | `--lm-bg-elevated` | `#FEFBFA` | `var(--elevated-white)` |

### 3.2 边框映射

| 状态 | Token | 值 | 宽度 |
|------|-------|-----|------|
| 默认边框 | `--lm-border-default` | `#EAAFB7` | 1px |
| 选中边框 | `--lm-border-selected` | `#D75C70` | 2px |
| Hover边框 | `--lm-border-hover` | `#F37969` | 2px |
| 错误边框 | `--lm-border-error` | `#CD374F` | 2px |
| 成功边框 | `--lm-border-success` | `#82AE8E` | 1px |

### 3.3 文字颜色

| 层级 | Token | 值 | 用途 |
|------|-------|-----|------|
| H1标题 | `--lm-text-h1` | `#56151F` | 页面标题(FR 900) |
| H2副标题 | `--lm-text-h2` | `#801F2F` | 区块标题(FR 800) |
| 正文 | `--lm-text-body` | `#3C1E1E` | 内容文字 |
| 辅助文字 | `--lm-text-muted` | `#801F2F` | Caption(FR 800) |
| 占位符 | `--lm-text-placeholder` | `#B49696` | 输入框占位符 |
| 链接文字 | `--lm-text-link` | `#D75C70` | 可点击链接 |
| 禁用文字 | `--lm-text-disabled` | `#A0918E` | 禁用态 |

---

## 4. 文字层级 Typography

### 4.1 深色模式字体栈

```css
/* 深色模式文字系统 */
--dm-font-display: 600 32px/1.2 "Inter", "Noto Sans SC", sans-serif;  /* #FFF8F5 */
--dm-font-h1: 600 24px/1.3 "Inter", "Noto Sans SC", sans-serif;       /* #FAF0EB */
--dm-font-h2: 600 20px/1.4 "Inter", "Noto Sans SC", sans-serif;       /* #EBDCD7 */
--dm-font-body: 400 15px/1.6 "Inter", "Noto Sans SC", sans-serif;     /* #D2C3BE */
--dm-font-caption: 400 13px/1.5 "Inter", "Noto Sans SC", sans-serif;  /* #A0918E */
--dm-font-small: 400 12px/1.5 "Inter", "Noto Sans SC", sans-serif;    /* #A0918E */
```

### 4.2 浅色模式字体栈

```css
/* 浅色模式文字系统 */
--lm-font-display: 600 32px/1.2 "Inter", "Noto Sans SC", sans-serif;  /* #56151F */
--lm-font-h1: 600 24px/1.3 "Inter", "Noto Sans SC", sans-serif;       /* #56151F */
--lm-font-h2: 600 20px/1.4 "Inter", "Noto Sans SC", sans-serif;       /* #801F2F */
--lm-font-body: 400 15px/1.6 "Inter", "Noto Sans SC", sans-serif;     /* #3C1E1E */
--lm-font-caption: 400 13px/1.5 "Inter", "Noto Sans SC", sans-serif;  /* #801F2F */
```

---

## 5. 引导线系统 Connector Lines（核心设计）

> 卡片与卡片之间的连接线、流程线、时间轴线、步骤引导线的完整配色与样式规范。

### 5.1 引导线色彩定义

| 线类型 | Token | HEX | 透明度 | 线宽 | 线型 | 圆角 | 发光效果 | 用途 |
|--------|-------|-----|--------|------|------|------|---------|------|
| 主流程线 | `--line-primary-flow` | `#EAAFB7` | 60% | 2px | 实线 | — | 无 | 卡片间主要纵向流程连接 |
| 金线引导 | `--line-gold-thread` | `#DCBE78` | 80% | 3px | 粗实线 | 圆头(round) | 无 | 关键推荐路径/重要引导 |
| 激活轨迹 | `--line-glow-trail` | `#FF4D6A` | 50% | 3px | 实线 | 圆头 | 3px光晕扩散 | 当前激活步骤连线 |
| 已完成路径 | `--line-complete` | `#78AF8C` | 70% | 2px | 实线 | — | 无 | 已完成的步骤路径 |
| 虚线辅助 | `--line-dashed-guide` | `#8C6E73` | 40% | 1.5px | 虚线 | — | 无 | 可选步骤/弱关联路径 |

### 5.2 卡片边框线（引导线系统的延伸）

| 状态 | Token | HEX | 宽度 | 圆角 | 发光效果 |
|------|-------|-----|------|------|---------|
| 默认卡片边框 | `--card-border-default` | `#4E3A3D` | 1px | 12px | 无 |
| 选中卡片边框 | `--card-border-selected` | `#D75C70` | 2px | 12px | 无 |
| Hover卡片边框 | `--card-border-hover` | `#FF4D6A` | 2px | 12px | 5px霓虹光晕 |
| 成功卡片边框 | `--card-border-success` | `#78AF8C` | 1px | 12px | 无 |
| 错误卡片边框 | `--card-border-error` | `#8C3C4B` | 2px | 12px | 无 |

### 5.3 引导线使用原则

```
1. 纵向主流程（如：定主角 → 找冲突 → 定调性）
   → 使用 Primary Flow #EAAFB7 (粉色实线 2px)

2. 关键推荐路径（如：AI推荐的 optimal path）
   → 使用 Gold Thread #DCBE78 (金色粗实线 3px, 圆头)

3. 当前用户所在的步骤连线
   → 使用 Glow Trail #FF4D6A (红色发光实线 3px + glow)

4. 用户已完成的步骤路径
   → 使用 Complete Path #78AF8C (翡翠绿实线 2px)

5. 可选/非必须步骤
   → 使用 Dashed Guide #8C6E73 (灰色虚线 1.5px, 40%透明度)

6. 状态变化规则：
   - 未访问：Dashed Guide
   - 当前步骤：Glow Trail（红色发光）
   - 已完成：Complete Path（翡翠绿）
   - 推荐路径：Gold Thread（金色）
```

### 5.4 引导线CSS实现参考

```css
/* 主流程线 */
.connector-primary {
  width: 2px;
  background: rgba(234, 175, 183, 0.6);
  border-radius: 1px;
}

/* 金线引导 */
.connector-gold {
  width: 3px;
  background: rgba(220, 190, 120, 0.8);
  border-radius: 2px;
  stroke-linecap: round;
}

/* 激活轨迹（带发光） */
.connector-glow {
  width: 3px;
  background: rgba(255, 77, 106, 0.5);
  border-radius: 2px;
  box-shadow: 0 0 6px rgba(255, 77, 106, 0.4), 0 0 12px rgba(255, 77, 106, 0.2);
}

/* 已完成路径 */
.connector-complete {
  width: 2px;
  background: rgba(120, 175, 140, 0.7);
}

/* 虚线辅助 */
.connector-dashed {
  width: 1.5px;
  background: repeating-linear-gradient(
    to bottom,
    rgba(140, 110, 115, 0.4) 0px,
    rgba(140, 110, 115, 0.4) 6px,
    transparent 6px,
    transparent 12px
  );
}

/* 箭头样式 */
.connector-arrow::after {
  content: '';
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 8px solid currentColor;
}
```

---

## 6. 组件配色 Component Colors

### 6.1 深色模式全局组件

| 组件 | 背景色 | 边框色 | 文字色 | 特殊效果 |
|------|--------|--------|--------|---------|
| 页面背景 | `#100C0D` | — | — | — |
| 内容卡片 | `#1C1415` | `#4E3A3D` 1px | `#D2C3BE` | border-radius: 12px |
| 选中卡片 | `#2A1E20` | `#D75C70` 2px | `#FAF0EB` | border-radius: 12px |
| Hover卡片 | `#1C1415` | `#FF4D6A` 2px | `#FAF0EB` | 5px霓虹光晕 |
| 侧边面板 | `#2A1E20` | `#4E3A3D` 1px | `#D2C3BE` | — |
| Modal弹窗 | `#1C1415` | `#4E3A3D` 1px | `#FAF0EB` | backdrop: rgba(0,0,0,0.7) |
| Dropdown | `#1C1415` | `#4E3A3D` 1px | `#D2C3BE` | — |
| Tooltip | `#3A2A2D` | `#4E3A3D` 1px | `#EBDCD7` | — |
| 标签Badge(Required) | `#DCBE78` | — | `#100C0D` | border-radius: 6px, 金箔底 |
| 标签Badge(Recommended) | `#3A2A2D` | `#B99B5F` 1px | `#DCBE78` | 金色边框 |
| 进度条背景 | `#2A1E20` | — | — | — |
| 进度条填充 | `#DCBE78` | — | — | 金色填充 |
| 进度条已完成 | `#78AF8C` | — | — | 翡翠绿填充 |
| 滚动条轨道 | `#2A1E20` | — | — | — |
| 滚动条滑块 | `#4E3A3D` | — | — | Hover: `#6E5A5D` |

### 6.2 浅色模式全局组件

| 组件 | 背景色 | 边框色 | 文字色 | 特殊效果 |
|------|--------|--------|--------|---------|
| 页面背景 | `#FCF6F7` | — | — | — |
| 内容卡片 | `#FFFFFF` | `#EAAFB7` 1px | `#3C1E1E` | border-radius: 12px |
| 选中卡片 | `#FCF6F7` | `#D75C70` 2px | `#3C1E1E` | border-radius: 12px |
| Hover卡片 | `#FFFFFF` | `#F37969` 2px | `#3C1E1E` | — |
| 侧边面板 | `#FEFBFA` | `#EAAFB7` 1px | `#3C1E1E` | — |
| Modal弹窗 | `#FEFBFA` | `#EAAFB7` 1px | `#3C1E1E` | — |
| 标签Badge(Required) | `#D75C70` | — | `#FFFFFF` | border-radius: 6px |
| 标签Badge(Recommended) | `#F2EBC8` | — | `#7D6D1D` | 米黄底 |
| 进度条背景 | `#EFBEC6` | — | — | — |
| 进度条填充 | `#D75C70` | — | — | — |

---

## 7. 按钮系统 Button System

### 7.1 深色模式按钮

| 按钮类型 | 背景色 | 边框 | 文字色 | 圆角 | Hover效果 | 用途 |
|----------|--------|------|--------|------|----------|------|
| **Primary** | `#FF4D6A` | — | `#FFFFFF` | 10px | 外发光 `box-shadow: 0 0 8px rgba(255,77,106,0.5)` | 核心操作：创建视频 |
| **Secondary** | `#1C1415` | `#D75C70` 2px | `#D75C70` | 10px | 背景变为 `#2A1E20` | 次要操作：保存草稿 |
| **Ghost** | transparent | `#4E3A3D` 1px | `#A0918E` | 10px | 边框变为 `#6E5A5D`, 文字变白 | 取消/返回 |
| **CTA** | `#F37969` | — | `#FFFFFF` | 10px | 外发光 `box-shadow: 0 0 8px rgba(243,121,105,0.5)` | 核心转化：立即生成 |
| **Text Button** | transparent | — | `#D75C70` | — | 下划线出现, 文字变为 `#FF4D6A` | 文字链接式按钮 |
| **Icon Button** | `#2A1E20` | `#4E3A3D` 1px | `#A0918E` | 8px | 背景 `#3A2A2D`, 文字变白 | 图标按钮 |
| **Disabled** | `#3A2A2D` | — | `#6E6260` | 10px | 无 | 不可操作态 |

### 7.2 浅色模式按钮

| 按钮类型 | 背景色 | 边框 | 文字色 | 圆角 | Hover效果 | 用途 |
|----------|--------|------|--------|------|----------|------|
| **Primary** | `#D75C70` | — | `#FFFFFF` | 10px | 背景变为 `#CD374F` | 核心操作 |
| **Secondary** | `#FCF6F7` | `#D75C70` 2px | `#D75C70` | 10px | 背景变为 `#EFBEC6` | 次要操作 |
| **Ghost** | `#FFFFFF` | `#EAAFB7` 1px | `#644646` | 10px | 边框变为 `#D75C70` | 取消/返回 |
| **CTA** | `#F37969` | — | `#FFFFFF` | 10px | 背景变为 `#EF4D38` | 核心转化 |
| **Disabled** | `#EFBEC6` | — | `#A7293D` | 10px | 无 | 不可操作态 |

---

## 8. 卡片系统 Card System

### 8.1 卡片规格（深色模式）

```css
/* 基础卡片 */
.card {
  background: #1C1415;
  border: 1px solid #4E3A3D;
  border-radius: 12px;
  padding: 20px 24px;
  color: #D2C3BE;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  transition: all 0.25s ease;
}

/* 选中卡片 */
.card-selected {
  background: #2A1E20;
  border: 2px solid #D75C70;
  border-radius: 12px;
  padding: 20px 24px;
  color: #FAF0EB;
  box-shadow: 0 4px 20px rgba(215, 92, 112, 0.15);
}

/* Hover卡片 */
.card-hover {
  background: #1C1415;
  border: 2px solid #FF4D6A;
  border-radius: 12px;
  padding: 20px 24px;
  color: #FAF0EB;
  box-shadow: 
    0 4px 20px rgba(0, 0, 0, 0.4),
    0 0 12px rgba(255, 77, 106, 0.25),
    0 0 4px rgba(255, 77, 106, 0.4);
  transform: translateY(-2px);
}

/* 卡片标题 */
.card-title {
  font-weight: 600;
  font-size: 16px;
  color: #FAF0EB;
  margin-bottom: 8px;
}

/* 卡片内分割线 */
.card-divider {
  height: 1px;
  background: #4E3A3D;
  margin: 16px 0;
}
```

### 8.2 卡片间引导线布局

```
        ┌──────────┐
        │  定主角   │ ← 卡片A (当前步骤 = Glow Trail 红色发光)
        │ Required │
        └────┬─────┘
             │ Primary Flow #EAAFB7 (粉色 2px)
             ▼
        ┌──────────┐
        │  找冲突   │ ← 卡片B (当前步骤)
        │ Required │
        └────┬─────┘
             │ Glow Trail #FF4D6A (红色发光 3px)
             │
             │ Gold Thread #DCBE78 (金色 3px) ← 推荐路径
             │         \
             ▼          \
        ┌──────────┐     \
        │  定调性   │      \
        │Recommended      \
        └──────────┘       \
                            \
                         ┌──────────┐
                         │  定风格   │ ← 可选步骤 (Dashed Guide 灰色虚线)
                         │ Optional │
                         └──────────┘
```

---

## 9. 表单系统 Form System

### 9.1 深色模式表单

| 元素 | 样式规格 |
|------|---------|
| 输入框背景 | `#1C1415` |
| 输入框边框(默认) | `#4E3A3D` 1px |
| 输入框边框(Focus) | `#FF4D6A` 2px + 发光 |
| 输入框边框(错误) | `#8C3C4B` 2px |
| 输入框边框(成功) | `#78AF8C` 2px |
| 占位符文字 | `#6E6260` |
| 输入文字 | `#FAF0EB` |
| 标签文字 | `#EBDCD7` |
| 辅助说明 | `#A0918E` |
| 必填标记 | `#FF4D6A` |
| 文本域背景 | `#1C1415` |
| 选择器背景 | `#1C1415` |
| 选择器下拉背景 | `#2A1E20` |
| 选择器选项Hover | `#3A2A2D` |
| 复选框背景(未选) | `#2A1E20` |
| 复选框背景(选中) | `#D75C70` |
| 复选框边框 | `#4E3A3D` |
| 开关轨道(关闭) | `#2A1E20` |
| 开关轨道(开启) | `#D75C70` |
| 开关滑块 | `#FAF0EB` |

### 9.2 Focus发光效果CSS

```css
/* 输入框Focus霓虹发光 */
.input:focus {
  outline: none;
  border: 2px solid #FF4D6A;
  box-shadow: 
    0 0 0 3px rgba(255, 77, 106, 0.1),
    0 0 12px rgba(255, 77, 106, 0.2),
    inset 0 1px 2px rgba(0, 0, 0, 0.2);
  background: #1C1415;
  color: #FAF0EB;
}
```

---

## 10. 导航栏 Navigation

### 10.1 深色模式导航栏

```css
.navbar {
  background: #1C1415;
  border-bottom: 1px solid #3A2A2D;
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 32px;
}

/* Logo区域 */
.navbar-logo {
  background: #FF4D6A;
  color: #FFFFFF;
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 600;
  box-shadow: 0 0 8px rgba(255, 77, 106, 0.3);
}

/* 导航链接 */
.nav-link {
  color: #A0918E;
  font-size: 14px;
  font-weight: 500;
  padding: 8px 0;
  transition: color 0.2s ease;
}

.nav-link:hover {
  color: #FAF0EB;
}

.nav-link.active {
  color: #FF4D6A;
  border-bottom: 2px solid #FF4D6A;
}

/* 语言切换 */
.lang-switch {
  background: #2A1E20;
  border: 1px solid #4E3A3D;
  color: #DCBE78;
  padding: 6px 14px;
  border-radius: 16px;
  font-size: 13px;
}
```

---

## 11. 选项卡 Tabs

### 11.1 深色模式选项卡

```css
/* 选项卡容器 */
.tab-container {
  display: flex;
  gap: 8px;
  padding: 4px;
}

/* 未选中选项卡 */
.tab {
  background: #1C1415;
  border: 1px solid #4E3A3D;
  color: #A0918E;
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab:hover {
  border-color: #6E5A5D;
  color: #D2C3BE;
}

/* 选中选项卡 */
.tab-active {
  background: #D75C70;
  border: none;
  color: #FFFFFF;
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(215, 92, 112, 0.3);
}

/* 二级选项卡（更紧凑） */
.tab-secondary {
  background: transparent;
  border: 1px solid #4E3A3D;
  color: #A0918E;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
}

.tab-secondary-active {
  background: #2A1E20;
  border: 2px solid #D75C70;
  color: #FAF0EB;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}
```

---

## 12. 状态反馈 Status & Feedback

### 12.1 状态色板

| 状态 | 背景色 | 文字色 | 边框色 | 图标色 | 用途 |
|------|--------|--------|--------|--------|------|
| Success | `#78AF8C` | `#100C0D` | — | — | 视频生成完成 |
| Success(深色底) | `rgba(120,175,140,0.15)` | `#78AF8C` | `#78AF8C` | `#78AF8C` | 深色模式成功提示 |
| Warning | `#D6C155` | `#100C0D` | — | — | 素材即将过期 |
| Warning(深色底) | `rgba(214,193,85,0.15)` | `#D6C155` | `#D6C155` | `#D6C155` | 深色模式警告 |
| Error | `#C03340` | `#FFFFFF` | — | — | 生成失败 |
| Error(深色底) | `rgba(192,51,64,0.15)` | `#C03340` | `#C03340` | `#C03340` | 深色模式错误 |
| Info | `#6A89AF` | `#FFFFFF` | — | — | 新功能上线 |
| Info(深色底) | `rgba(106,137,175,0.15)` | `#829BAF` | `#829BAF` | `#829BAF` | 深色模式信息 |
| Progress | `#DCBE78` | `#100C0D` | — | — | 处理中/加载 |
| Progress(深色底) | `rgba(220,190,120,0.15)` | `#DCBE78` | `#DCBE78` | `#DCBE78` | 深色模式进度 |
| Loading | — | `#DCBE78` | — | `#DCBE78` | 旋转loading图标 |

### 12.2 Toast/通知组件

```css
/* Toast基础 */
.toast {
  border-radius: 10px;
  padding: 14px 20px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.toast-success {
  background: rgba(120, 175, 140, 0.15);
  border: 1px solid #78AF8C;
  color: #78AF8C;
}

.toast-error {
  background: rgba(192, 51, 64, 0.15);
  border: 1px solid #C03340;
  color: #C03340;
}

.toast-warning {
  background: rgba(214, 193, 85, 0.15);
  border: 1px solid #D6C155;
  color: #D6C155;
}

.toast-info {
  background: rgba(130, 155, 175, 0.15);
  border: 1px solid #829BAF;
  color: #829BAF;
}
```

---

## 13. 分割线与边框 Dividers & Borders

### 13.1 分割线系统

| 类型 | 深色模式 | 浅色模式 | 用途 |
|------|---------|---------|------|
| Light(轻) | `#4E3A3D` | `#EAAFB7` | 卡片内部分割 |
| Subtle(微) | `#3A2A2D` | `#EFBEC6` | 模块间分割 |
| Strong(强) | `#8C3C4B` | `#E08090` | 区块分隔/错误线 |
| Gold(金色) | `#B99B5F` | `#D4BC7E` | 特色分割/时间轴刻度 |

### 13.2 边框系统

| 场景 | 深色模式 | 浅色模式 |
|------|---------|---------|
| 默认组件边框 | `#4E3A3D` 1px | `#EAAFB7` 1px |
| 选中组件边框 | `#D75C70` 2px | `#D75C70` 2px |
| Hover组件边框 | `#FF4D6A` 2px + glow | `#F37969` 2px |
| 禁用组件边框 | `#3A2A2D` 1px | `#EFBEC6` 1px |
| 错误组件边框 | `#8C3C4B` 2px | `#CD374F` 2px |
| 成功组件边框 | `#78AF8C` 1px | `#82AE8E` 1px |

---

## 14. 渐变方案 Gradients

### 14.1 深色模式渐变

| 渐变名称 | 起始色 | 结束色 | 应用场景 |
|----------|--------|--------|---------|
| Brand Gradient | `#D75C70` | `#D04E5A` | 品牌按钮Hover |
| Energy Gradient | `#FF4D6A` | `#D75C70` | CTA按钮、重要通知背景 |
| Gold Gradient | `#DCBE78` | `#B99B5F` | VIP标签、成就徽章 |
| Luxury Gradient | `#1C1415` | `#DCBE78` | Hero区暗角到金色光晕 |
| Subtle Gradient | `#100C0D` | `#1C1415` | 页面顶部微渐变 |
| Warm-Cool | `#D75C70` | `#829BAF` | 冷暖对比装饰区 |

### 14.2 浅色模式渐变

| 渐变名称 | 起始色 | 结束色 | 应用场景 |
|----------|--------|--------|---------|
| Brand Gradient | `#D75C70` | `#D04E5A` | 品牌按钮 |
| Energy Gradient | `#F37969` | `#D75C70` | CTA按钮 |
| Cream Gradient | `#F2EBC8` | `#EAAFB7` | 柔和装饰背景 |
| Gold Gradient | `#DCBE78` | `#F37969` | 特色功能区 |

### 14.3 CSS渐变代码

```css
/* 品牌渐变 */
.gradient-brand {
  background: linear-gradient(135deg, #D75C70 0%, #D04E5A 100%);
}

/* 能量发光渐变 */
.gradient-energy {
  background: linear-gradient(135deg, #FF4D6A 0%, #D75C70 100%);
}

/* 金色品质渐变 */
.gradient-gold {
  background: linear-gradient(135deg, #DCBE78 0%, #B99B5F 100%);
}

/* 暗角渐变（从中心向边缘变暗） */
.gradient-vignette {
  background: radial-gradient(ellipse at center, #1C1415 0%, #100C0D 70%);
}

/* 顶部光晕渐变 */
.gradient-top-glow {
  background: linear-gradient(180deg, #1C1415 0%, #100C0D 100%);
}
```

---

## 15. 电影感特效 Cinematic Effects

### 15.1 霓虹发光效果

```css
/* 霓虹发光 - 用于Primary按钮、Focus输入框 */
.neon-glow {
  box-shadow: 
    0 0 4px rgba(255, 77, 106, 0.4),
    0 0 12px rgba(255, 77, 106, 0.3),
    0 0 24px rgba(255, 77, 106, 0.15);
}

/* 悬停时增强发光 */
.neon-glow:hover {
  box-shadow: 
    0 0 6px rgba(255, 77, 106, 0.6),
    0 0 18px rgba(255, 77, 106, 0.4),
    0 0 36px rgba(255, 77, 106, 0.2);
}

/* 脉冲发光动画 */
@keyframes neon-pulse {
  0%, 100% { 
    box-shadow: 0 0 4px rgba(255, 77, 106, 0.4), 0 0 12px rgba(255, 77, 106, 0.2);
  }
  50% { 
    box-shadow: 0 0 8px rgba(255, 77, 106, 0.6), 0 0 20px rgba(255, 77, 106, 0.35);
  }
}

.neon-pulse {
  animation: neon-pulse 2s ease-in-out infinite;
}
```

### 15.2 暗角效果

```css
/* 页面暗角 */
.vignette {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse at center, transparent 50%, rgba(16, 12, 13, 0.6) 100%);
  z-index: 9999;
}
```

### 15.3 深度阴影

```css
/* 卡片深度阴影 */
.shadow-cinema {
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.3),
    0 8px 24px rgba(0, 0, 0, 0.4),
    0 16px 48px rgba(0, 0, 0, 0.2);
}

/* Hover时阴影加深 */
.shadow-cinema-hover:hover {
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.4),
    0 12px 32px rgba(0, 0, 0, 0.5),
    0 24px 64px rgba(0, 0, 0, 0.3);
  transform: translateY(-2px);
}
```

### 15.4 胶片颗粒效果

```css
/* 胶片颗粒纹理叠加（可选） */
.film-grain::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.02;
  background-image: url("data:image/svg+xml,..."); /* noise texture */
  pointer-events: none;
  z-index: 1;
}
```

---

## 16. 当前网站 vs 优化对比

### 16.1 当前问题诊断

| # | 问题 | 影响 |
|---|------|------|
| 1 | 背景色偏暖白/冷灰，缺乏影视感 | 与视频创作工具属性不匹配 |
| 2 | 主色（暗棕红）不突出，视觉扁平 | 品牌辨识度低，行动路径不清 |
| 3 | 点缀色单一，只有红色 | 缺少金色/绿色的品质感与功能区分 |
| 4 | 卡片层级模糊，边框太淡 | 表单边界不清，影响填写体验 |
| 5 | 缺少卡片间引导线设计 | 用户不清楚步骤流程和当前位置 |
| 6 | 整体偏"网站"而非"工具" | 缺乏专业剪辑软件的沉浸感 |

### 16.2 优化对照

| 元素 | 当前 | 优化后（深色Cinema） | 优化后（浅色） |
|------|------|---------------------|---------------|
| 页面背景 | `#F5F0EA` 暖白 | `#100C0D` 影院极黑 | `#FCF6F7` 暖画布 |
| 导航Logo | `#8C6A6E` 暗棕 | `#FF4D6A` 霓虹红发光 | `#D75C70` 发财红 |
| 导航文字(Active) | `#8C6A6E` | `#FF4D6A` + 下划线 | `#D75C70` + 下划线 |
| 选项卡Active | `#8C6A6E` 填充 | `#D75C70` 填充 + 阴影 | `#D75C70` 填充 |
| 选项卡Inactive | 灰白底+灰边框 | `#1C1415` + `#4E3A3D`边框 | `#FFF` + `#EAAFB7`边框 |
| 卡片背景 | `#FFFFFF` | `#1C1415` 胶片色 | `#FFFFFF` |
| 卡片边框 | `#D9D0CB` 灰 | `#4E3A3D` 暖阴影 | `#EAAFB7` 柔雾粉 |
| 卡片选中边框 | 不明显 | `#D75C70` 2px | `#D75C70` 2px |
| 卡片Hover边框 | 无 | `#FF4D6A` 2px + 发光 | `#F37969` 2px |
| 引导线 | 无 | 5级色彩系统 | 5级色彩系统 |
| Required标签 | 棕色底 | `#DCBE78` 金箔底 | `#D75C70` 红底 |
| 输入框Focus | 无特殊效果 | `#FF4D6A` 2px + 霓虹发光 | `#D75C70` 2px |
| 进度条 | 灰色 | `#DCBE78` 金色 | `#D75C70` 红色 |
| 文字层级 | 灰/棕 | 6级暖白渐变 | 6级红色渐变 |
| 整体质感 | 通用网站 | 专业剪辑软件 | 温暖专业平台 |

---

## 17. 实施优先级清单 Implementation Checklist

### P0 — 立即执行（核心骨架）

- [ ] 页面背景改为 `#100C0D` (Cinema Black)
- [ ] 导航Logo改为 `#FF4D6A` (Neon Red) + 微发光
- [ ] 一级选项卡Active态改为 `#D75C70` 填充
- [ ] 定义全局CSS Variables（第18节完整变量表）
- [ ] 文字层级系统上线（Display→Placeholder 6级）

### P1 — 本周完成（核心体验）

- [ ] 卡片背景改为 `#1C1415` + 默认边框 `#4E3A3D`
- [ ] 卡片选中态：背景 `#2A1E20` + 边框 `#D75C70` 2px
- [ ] 卡片Hover态：边框 `#FF4D6A` 2px + 霓虹光晕
- [ ] **卡片引导线5级系统上线**（⭐ 核心功能）
  - Primary Flow 粉色主流程线
  - Gold Thread 金色关键路径线
  - Glow Trail 红色激活发光轨迹
  - Complete Path 翡翠绿已完成线
  - Dashed Guide 灰色虚线可选路径
- [ ] 输入框Focus态：边框 `#FF4D6A` 2px + 霓虹发光效果
- [ ] 按钮系统：Primary `#FF4D6A` 发光 + Secondary + Ghost
- [ ] 标签Badge：Required改 `#DCBE78` 金箔底

### P2 — 下周完成（品质提升）

- [ ] 进度指示器改为 `#DCBE78` (Gold Foil) 金色
- [ ] 状态反馈色系统（Success/Warning/Error/Info）
- [ ] Toast通知组件深色模式样式
- [ ] 分割线系统（Light/Subtle/Strong/Gold）
- [ ] 导航栏完整样式（含语言切换器）
- [ ] 表单系统完整样式（含选择器/复选框/开关）
- [ ] 渐变方案实现（Brand/Energy/Gold）

### P3 — 后续优化（细节打磨）

- [ ] Hero区域暗角渐变效果 `#100C0D → #1C1415`
- [ ] 背景叠加2%胶片颗粒纹理
- [ ] 冷暖对比区域设计（发财红 + 冷钢蓝 `#829BAF`）
- [ ] 交互动画优化（卡片浮起、按钮脉冲、引导线流动）
- [ ] 浅色模式完整实现（作为可切换主题）
- [ ] 响应式适配检查
- [ ] 无障碍对比度审计

---

## 18. CSS Variables 快速接入

### 18.1 根变量定义（复制即用）

```css
/* ============================================
   Fortune Red Cinema — CSS Design Tokens
   ============================================ */

:root {
  /* ---- 核心色（通用） ---- */
  --fortune-red: #D75C70;
  --cinnabar: #D04E5A;
  --neon-red: #FF4D6A;
  --misty-pink: #EAAFB7;
  --coral-orange: #F37969;
  --ember-glow: #B44658;
  --crimson-mist: #8C3C4B;
  --gold-foil: #DCBE78;
  --antique-gold: #B99B5F;
  --pale-gold: #A58C5A;
  --jade-accent: #78AF8C;
  --cool-steel: #829BAF;

  /* ---- 浅色模式背景色 ---- */
  --canvas-light: #FCF6F7;
  --surface-white: #FFFFFF;
  --elevated-white: #FEFBFA;
  --accent-cream: #F2EBC8;
}

/* ============================================
   深色模式（主要推荐）
   ============================================ */
[data-theme="dark"] {
  /* 背景层级 */
  --bg-page: #100C0D;
  --bg-card: #1C1415;
  --bg-panel: #2A1E20;
  --bg-layer3: #3A2A2D;
  --bg-selected: #2A1E20;
  --bg-hover: #1C1415;
  --bg-elevated: #1C1415;

  /* 边框 */
  --border-default: #4E3A3D;
  --border-selected: #D75C70;
  --border-hover: #FF4D6A;
  --border-error: #8C3C4B;
  --border-success: #78AF8C;
  --border-gold: #DCBE78;

  /* 文字 */
  --text-display: #FFF8F5;
  --text-h1: #FAF0EB;
  --text-h2: #EBDCD7;
  --text-body: #D2C3BE;
  --text-muted: #A0918E;
  --text-placeholder: #6E6260;
  --text-disabled: #4E413F;
  --text-link: #D75C70;
  --text-link-active: #FF4D6A;

  /* 引导线 */
  --line-primary: rgba(234, 175, 183, 0.6);
  --line-gold: rgba(220, 190, 120, 0.8);
  --line-glow: rgba(255, 77, 106, 0.5);
  --line-complete: rgba(120, 175, 140, 0.7);
  --line-dashed: rgba(140, 110, 115, 0.4);

  /* 卡片边框 */
  --card-border: 1px solid #4E3A3D;
  --card-border-selected: 2px solid #D75C70;
  --card-border-hover: 2px solid #FF4D6A;
  --card-radius: 12px;

  /* 按钮 */
  --btn-primary-bg: #FF4D6A;
  --btn-primary-text: #FFFFFF;
  --btn-primary-glow: 0 0 8px rgba(255, 77, 106, 0.5);
  --btn-secondary-bg: #1C1415;
  --btn-secondary-border: 2px solid #D75C70;
  --btn-secondary-text: #D75C70;
  --btn-ghost-bg: transparent;
  --btn-ghost-border: 1px solid #4E3A3D;
  --btn-ghost-text: #A0918E;
  --btn-cta-bg: #F37969;
  --btn-cta-text: #FFFFFF;
  --btn-disabled-bg: #3A2A2D;
  --btn-disabled-text: #6E6260;

  /* 输入框 */
  --input-bg: #1C1415;
  --input-border: 1px solid #4E3A3D;
  --input-border-focus: 2px solid #FF4D6A;
  --input-text: #FAF0EB;
  --input-placeholder: #6E6260;
  --input-focus-glow: 0 0 12px rgba(255, 77, 106, 0.2);

  /* 阴影 */
  --shadow-card: 0 4px 16px rgba(0, 0, 0, 0.4);
  --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.5);
  --shadow-glow-red: 0 0 12px rgba(255, 77, 106, 0.25);
  --shadow-glow-gold: 0 0 12px rgba(220, 190, 120, 0.2);

  /* 导航 */
  --nav-bg: #1C1415;
  --nav-border: 1px solid #3A2A2D;
  --nav-link: #A0918E;
  --nav-link-active: #FF4D6A;

  /* 分割线 */
  --divider-light: #4E3A3D;
  --divider-subtle: #3A2A2D;
  --divider-strong: #8C3C4B;
  --divider-gold: #B99B5F;
}

/* ============================================
   浅色模式（辅助）
   ============================================ */
[data-theme="light"] {
  /* 背景层级 */
  --bg-page: #FCF6F7;
  --bg-card: #FFFFFF;
  --bg-panel: #FEFBFA;
  --bg-selected: #FCF6F7;
  --bg-hover: #FFFFFF;
  --bg-elevated: #FEFBFA;

  /* 边框 */
  --border-default: #EAAFB7;
  --border-selected: #D75C70;
  --border-hover: #F37969;
  --border-error: #CD374F;
  --border-success: #82AE8E;
  --border-gold: #D4BC7E;

  /* 文字 */
  --text-display: #56151F;
  --text-h1: #56151F;
  --text-h2: #801F2F;
  --text-body: #3C1E1E;
  --text-muted: #801F2F;
  --text-placeholder: #B49696;
  --text-disabled: #A0918E;
  --text-link: #D75C70;
  --text-link-active: #D75C70;

  /* 引导线（浅色模式透明度更高） */
  --line-primary: rgba(234, 175, 183, 0.8);
  --line-gold: rgba(220, 190, 120, 0.9);
  --line-glow: rgba(255, 77, 106, 0.7);
  --line-complete: rgba(120, 175, 140, 0.85);
  --line-dashed: rgba(160, 140, 145, 0.5);

  /* 卡片边框 */
  --card-border: 1px solid #EAAFB7;
  --card-border-selected: 2px solid #D75C70;
  --card-border-hover: 2px solid #F37969;
  --card-radius: 12px;

  /* 按钮 */
  --btn-primary-bg: #D75C70;
  --btn-primary-text: #FFFFFF;
  --btn-primary-glow: none;
  --btn-secondary-bg: #FCF6F7;
  --btn-secondary-border: 2px solid #D75C70;
  --btn-secondary-text: #D75C70;
  --btn-ghost-bg: #FFFFFF;
  --btn-ghost-border: 1px solid #EAAFB7;
  --btn-ghost-text: #644646;
  --btn-cta-bg: #F37969;
  --btn-cta-text: #FFFFFF;
  --btn-disabled-bg: #EFBEC6;
  --btn-disabled-text: #A7293D;

  /* 输入框 */
  --input-bg: #FFFFFF;
  --input-border: 1px solid #EAAFB7;
  --input-border-focus: 2px solid #D75C70;
  --input-text: #3C1E1E;
  --input-placeholder: #B49696;
  --input-focus-glow: 0 0 0 3px rgba(215, 92, 112, 0.1);

  /* 阴影 */
  --shadow-card: 0 2px 12px rgba(0, 0, 0, 0.08);
  --shadow-elevated: 0 8px 24px rgba(0, 0, 0, 0.12);
  --shadow-glow-red: none;
  --shadow-glow-gold: none;

  /* 导航 */
  --nav-bg: #FEFBFA;
  --nav-border: 1px solid #EAAFB7;
  --nav-link: #644646;
  --nav-link-active: #D75C70;

  /* 分割线 */
  --divider-light: #EAAFB7;
  --divider-subtle: #EFBEC6;
  --divider-strong: #E08090;
  --divider-gold: #D4BC7E;
}
```

### 18.2 Tailwind 配置快速接入

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        // 核心色
        'fortune-red': '#D75C70',
        'cinnabar': '#D04E5A',
        'neon-red': '#FF4D6A',
        'misty-pink': '#EAAFB7',
        'coral': '#F37969',
        'ember': '#B44658',
        'crimson-mist': '#8C3C4B',
        // 金色系
        'gold-foil': '#DCBE78',
        'antique-gold': '#B99B5F',
        'pale-gold': '#A58C5A',
        // 功能色
        'jade': '#78AF8C',
        'cool-steel': '#829BAF',
        // 深色基底
        'cinema-black': '#100C0D',
        'film-reel': '#1C1415',
        'dark-slate': '#2A1E20',
        'charcoal-rose': '#3A2A2D',
        'warm-shadow': '#4E3A3D',
        // 浅色背景
        'canvas-light': '#FCF6F7',
        'elevated-white': '#FEFBFA',
        'accent-cream': '#F2EBC8',
      },
      borderRadius: {
        'card': '12px',
        'tab': '10px',
        'badge': '6px',
        'input': '10px',
      },
      boxShadow: {
        'cinema': '0 4px 16px rgba(0, 0, 0, 0.4)',
        'cinema-hover': '0 8px 32px rgba(0, 0, 0, 0.5)',
        'neon-red': '0 0 12px rgba(255, 77, 106, 0.25)',
        'neon-red-strong': '0 0 20px rgba(255, 77, 106, 0.4)',
        'gold': '0 0 12px rgba(220, 190, 120, 0.2)',
      },
    },
  },
};
```

---

## 附录：色板速查卡

### 深色模式速查

```
页面   ████████ #100C0D    卡片   ████████ #1C1415    面板   ████████ #2A1E20
三级   ████████ #3A2A2D    边框   ████████ #4E3A3D
主红   ████████ #D75C70    发光   ████████ #FF4D6A    余烬   ████████ #B44658
金箔   ████████ #DCBE78    古金   ████████ #B99B5F    翡翠   ████████ #78AF8C
冷钢   ████████ #829BAF    薄雾   ████████ #8C3C4B
标题   ████████ #FFF8F5    正文   ████████ #D2C3BE    辅助   ████████ #A0918E
```

### 引导线速查

```
主流程线    ────  #EAAFB7  60%  实线  2px
金线引导    ────  #DCBE78  80%  粗线  3px  圆头
激活轨迹    ────  #FF4D6A  50%  发光  3px  ✨
已完成      ────  #78AF8C  70%  实线  2px
虚线辅助    - - - #8C6E73  40%  虚线  1.5px
```

---

> **文档结束**。本设计系统包含完整的 Design Tokens，可直接用于 React/Vue/Angular 开发，支持通过 `data-theme="dark"` / `data-theme="light"` 切换主题。
