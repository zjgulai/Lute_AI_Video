# Momcozy 品牌 UI 深度优化计划 v3（最终执行版）

**制定**: 2026-04-30 · **修订**: v3（含品牌呼吸感 + 英文字体搭配）  
**依据**: Momcozy 品牌 VI 2025 确认版 × 当前最新产品形态（24 组件）  
**原则**: 暖栗红品牌调性 × 呼吸感间距 × Montserrat+Inter 黄金搭配 × 反 AI slop

---

## 零、v3 增量（v2.1 → v3）

| 新增维度 | 内容 |
|---------|------|
| **呼吸感** | 最小字号上移（10→11, 11→12）、间距上移一档（p-3→p-4）、body 行高 1.47→1.55 |
| **字体搭配** | Montserrat letter-spacing +0.02em、h2 字重 600→500(Medium)、Inter 低字号用 Regular |

---

## 一、品牌核心资产

```
品牌主色·暖栗红    #6A2B3A    包容、稳定、呵护
品牌辅色·豆沙粉    #B27A7E    细腻、温柔、治愈
暖色扩展浅         #FCE4E2 → #FFF0EF → #FEF9F6
暖色扩展深         #D9A8A3 → #EDD3D1
冷色辅助            #6B8578 → #CDE4D5 → #E5F2EB
中性深色           #35353B (主文字) · #59585E (辅文字) · #9FA0A0 (三灰色)
中性浅色           #F8EEE8 (暖白卡底) · #FEF9F6 (全局背景)

英文字体           Montserrat (Display) · Inter (Body)
中文字体           梦源黑体 W20/W16/W10
气质关键词         温暖 / 呵护 / 包容 / 稳定 / 细腻 / 现代 / 专业
```

---

## 二、当前 UI vs VI 差距

| 维度 | 当前 | Momcozy | 偏差 |
|------|------|---------|------|
| 品牌主色 | `#7CB342` 路特绿 | `#6A2B3A` 暖栗红 | 🔴 |
| 背景底色 | `#f5f5f7` 冷灰 | `#FEF9F6` 暖肤白 | 🟡 |
| 边框/分割 | `#d2d2d7` / `#e8e8ed` | `#D9A8A3` / `#EDD3D1` | 🟡 |
| 英文字体 | Source Serif 4 (衬线) | Montserrat (几何无衬线) | 🔴 |
| 中文字体 | 系统默认 | 梦源黑体 | 🟡 |
| 最小字号 | 9-10px (430处) | ≥11px | 🔴 新增 |
| 间距节奏 | gap-2/p-3 主导 | gap-3/p-4 主导 | 🟡 新增 |
| 行高 | 1.47 | 1.55 (Inter 最佳带) | 🟡 新增 |
| h2 字重 | 600 (SemiBold) | 500 (Medium) | 🟡 新增 |

---

## 三、分 Phase 执行

### Phase 1: Design Token 迁移 + 呼吸感 + 字体搭配 (45min)

**文件**: `web/src/app/globals.css`

#### 1.1 CSS 变量替换

| 变量 | 当前 | 目标 |
|------|------|------|
| `--color-accent` / `--color-accent-hover` | `#7CB342` / `#5A8F2E` | `#6A2B3A` / `#4E1F2A` |
| `--brand-primary` / `--brand-primary-light` | `#7CB342` / `rgba(124,179,66,0.1)` | `#6A2B3A` / `rgba(106,43,58,0.08)` |
| `--brand-primary-mid` / `--brand-primary-glow` | `rgba(124,179,66,0.15)` / `rgba(124,179,66,0.4)` | `rgba(106,43,58,0.12)` / `rgba(106,43,58,0.3)` |
| `--accent-smart` | `#5B8DEF` | `#7A96BB` |
| `--accent-expert` | `#7C3AED` | `#6A2B3A` |
| `--ink-primary` / `--ink-secondary` / `--ink-tertiary` | `#1d1d1f` / `#86868b` / `#aeaeb2` | `#35353B` / `#59585E` / `#9FA0A0` |
| `--surface-card` / `--surface-subtle` / `--surface-hover` | `#ffffff` / `#f5f5f7` / `#e8e8ed` | `#FFF0EF` / `#FCE4E2` / `#EDD3D1` |
| `--border-default` / `--border-hover` | `#e8e8ed` / `#d2d2d7` | `#EDD3D1` / `#D9A8A3` |
| `--status-error` / `--status-error-light` | `#ff453a` / `rgba(255,69,58,0.1)` | `#6A2B3A` / `rgba(106,43,58,0.08)` |
| Legacy 全部变量 | 同上映射 | 同值 |

**删除**: `--color-brand-green`, `--color-green-bg-light`, `--color-green-border-light`

#### 1.2 字体替换

```css
/* 删除 */
@import url('...Source+Serif+4...');

/* 新增 */
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600&family=Inter:wght@400;500&display=swap');

:root {
  --font-display: 'Montserrat', -apple-system, sans-serif;
  --font-body: 'Inter', -apple-system, sans-serif;
}
```

#### 1.3 呼吸感（body + headings）

```css
body {
  line-height: 1.55;               /* ← 从 1.47 提升 (Inter 最佳阅读带) */
}

h1, h2, .font-display {
  font-family: 'Montserrat', var(--font-display);
  font-weight: 400;
  letter-spacing: 0.02em;          /* ← 新增: Montserrat 字距放松 */
}
h2 { font-weight: 500; }          /* ← 从 600 → 500 (Montserrat Medium, 低字号避重锤感) */
```

#### 1.4 组件样式修正

| 类 | 目标 |
|----|------|
| `.apple-card` | padding 默认给 16px，组件可覆盖但不低于 12px |
| `.apple-btn` | `font-size: 14px` → `13px` (but 保持 padding 不变) |
| `.apple-btn-primary:hover` | `rgba(124,179,66,0.04)` → `rgba(106,43,58,0.06)` |
| `.apple-input:focus` | `box-shadow: 0 0 0 3px rgba(106,43,58,0.12)` |
| `.apple-toast` | 背景 `rgba(124,179,66,0.95)` → `rgba(106,43,58,0.95)` |
| `.apple-btn-success` | `var(--color-brand-green)` → `var(--color-success)` (`#6B8578`) |
| `.apple-btn-danger` | `var(--color-error)` → `var(--status-error)` (自动跟随) |

#### 1.5 阴影暖化

```css
--shadow-sm: 0 1px 3px rgba(106, 43, 58, 0.04);
--shadow-md: 0 4px 12px rgba(106, 43, 58, 0.06);
--shadow-lg: 0 8px 30px rgba(106, 43, 58, 0.08);
```

**Phase 1 自证**: `grep '#7CB342\|#5A8F2E\|#69FF68\|#E6F5E0\|#C5E0B0\|Source Serif' globals.css` → 0。

---

### Phase 2: 组件级硬编码修正 + 字号/间距呼吸升级 (2h)

**策略**: 逐文件替换硬编码色值 → CSS 变量，同步上移最小字号和间距。

#### 2.0 字号/间距升级规则（贯穿所有组件）

| 原始 | 目标 | 原因 |
|------|------|------|
| `text-[9px]` | `text-[10px]` | 不低于 10px |
| `text-[10px]` | `text-[11px]` | 最小可读字号 |
| `text-[11px]` | `text-xs` (12px) | 辅助信息放松 |
| `p-2` / `py-2` / `px-2` | `p-3` / `py-3` / `px-3` | 卡片内留白 |
| `p-3` | `p-4` | 主内容卡片 |
| `gap-1` / `gap-2` | `gap-2` / `gap-3` | 元素间距 |
| `space-y-2` | `space-y-3` | 区块间距 |

#### 2.1 组件改动清单（24 文件）

| # | 文件 | 色值替换 | 字号/间距升级 |
|---|------|---------|-------------|
| 1 | `page.tsx` | ~30 处绿色/灰色 → CSS vars | toast 字号、卡片 padding |
| 2 | `SplashScreen.tsx` | `backgroundColor: "#7CB342"` → `var(--color-accent)` | — |
| 3 | `Nav.tsx` | 5 处 → CSS vars | 字号 11→12 |
| 4 | `SceneTabs.tsx` | 6 处 → CSS vars | 选中态 padding |
| 5 | `SceneForm.tsx` | ~11 处（含 VLOG 区 8 处） | 标签字号 11→12, section gap |
| 6 | `ReviewPanel.tsx` | ~10 处 | badge/textarea |
| 7 | `OneShotResultView.tsx` | ~8 处 | tab/badge/stat |
| 8 | `VideoWorkflow.tsx` | ~6 处 | step label |
| 9 | `StageProgress.tsx` | 2 处 | 进度标签 |
| 10 | `GatePanel.tsx` | 5 处 | gate step |
| 11 | `StepByStepView.tsx` | ~4 处 | step item |
| 12 | `PipelineMonitor.tsx` | ~3 处 | node label |
| 13 | `RecommendPanel.tsx` | ~3 处 | rec card |
| 14 | `DistributionView.tsx` | ~3 处 | platform card |
| 15 | `AssetLibrary.tsx` | ~3 处 | asset card |
| 16 | `SettingsPanel.tsx` | ~3 处 | settings form |
| 17 | `brand-packages/page.tsx` | ~5 处 | header icon, empty state |
| 18 | `footage/page.tsx` | ~5 处 | header, upload |
| 19 | `influencers/page.tsx` | ~5 处 | header, form |
| **20** | **`VlogSixView.tsx`** | **2 处** `#86868b` → `var(--ink-secondary)` | label padding |
| **21** | **`VlogModelSelector.tsx`** | **自动跟随** (已用 CSS vars) | model card gap |
| **22** | **`FastModePanel.tsx`** | **~4 处** | form spacing |
| **23** | **`CompareView.tsx`** | **~3 处** | version card |
| **24** | **`PublishPanel.tsx`** | **~3 处** | publish form |

**Phase 2 自证**: `grep -r '#7CB342\|#5A8F2E\|#69FF68\|#E6F5E0\|text-\[9px\]' web/src/ --include='*.tsx' --include='*.ts' --include='*.css'` → 0。

---

### Phase 3: 质感升级 (30min)

#### 3.1 启动页品牌化
```tsx
SplashScreen: style={{ backgroundColor: "var(--color-accent)" }}
```

#### 3.2 中文字体
```css
body { font-family: '梦源黑体', 'Noto Sans SC', var(--font-body); }
```

#### 3.3 暗色调模式
```css
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #35353B;
    --color-surface: #4A4947;
    --color-text-primary: #FEF9F6;
    --color-text-secondary: #D9D9D9;
    --color-border: #595757;
    --color-border-light: #4A4947;
  }
}
```

#### 3.4 取消按钮品牌化
```tsx
// page.tsx 取消按钮 hover 已用 var(--status-error) = #6A2B3A ✅
```

---

## 四、执行参数

| 指标 | 值 |
|------|-----|
| 改动文件 | 24（含新增 VlogSixView, FastModePanel） |
| 总替换处 | ~180 |
| Phase 1 | 45min (token + 字体 + 呼吸) |
| Phase 2 | 2h (24 文件逐行) |
| Phase 3 | 30min |
| **总计** | **3h 15min** |

## 五、自证清单

- [ ] Phase 1: `globals.css` 无绿色残留、无 Source Serif 残留、行高为 1.55、h2 字重 500
- [ ] Phase 2: 全项目 `grep` 无硬编码绿色色值、无 `text-[9px]`
- [ ] Phase 3: SplashScreen 暖栗红、暗色模式无断裂、取消按钮品牌红 hover
- [ ] 回退: S1/S3/S5 三场景全链路无 layout break
