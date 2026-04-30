# 封面重设计 + 加载性能优化 — 设计规格

**日期**: 2026-04-30  
**来源**: Momcozy 品牌调性要求 × 当前 splash 1.7MB PNG × portfolio 10MB PNG

---

## 一、问题定义

| # | 问题 | 当前 | 根因 |
|---|------|------|------|
| 1 | 封面不符品牌 | 绿色 `#7CB342` 底 + 产品大图 | 路特旧品牌色，未迁移 Momcozy |
| 2 | 封面加载慢 | 1.7MB PNG 阻塞首帧 | 全尺寸 PNG + 无 WebP |
| 3 | 按钮坐标硬编码 | `BTN_X=72 Y=820` 像素级映射 | 图片变化即失效 |
| 4 | Portfolio 拖慢首页 | 6 张 PNG 合计 ~10MB | 懒加载缺失 + 未转 WebP |

---

## 二、设计目标

1. **零外部图片封面**：纯 CSS/HTML，加载 0KB
2. **Momcozy 品牌色**：暖栗红 `#6A2B3A` 全屏
3. **Montserrat 字体**：VI 规定英文标题
4. **呼吸感间距**：v3 计划规范
5. **Portfolio WebP 化**：10MB → ~2MB

---

## 三、封面设计

### 3.1 视觉结构

```
┌──────────────────────────────────────────────┐
│              暖栗红 #6A2B3A                    │
│         radial-gradient(中心微亮)              │
│                                              │
│           AI 视频创作平台                      │
│        13px · rgba(255,255,255,0.5)           │
│                                              │
│                 Momcozy                      │
│              32px · Montserrat 500 · white    │
│                                              │
│          为妈妈的舒适不断进化                   │
│        18px · 梦源黑体 W16 · rgba(255,255,255,0.8)│
│                                              │
│      Evolving for Mom and Cozy               │
│     13px · Inter 400 · rgba(255,255,255,0.55)│
│                                              │
│      数字化-数据科学部 创作                    │
│      12px · rgba(255,255,255,0.4)            │
│                                              │
│              ┌────────────┐                  │
│              │  开始创作   │                  │
│              └────────────┘                  │
│        16px · 圆角 24px · 白底半透明          │
└──────────────────────────────────────────────┘
```

### 3.2 动画

```
Logo:             slideUp 400ms ease-out
Slogan:           slideUp 400ms ease-out · delay 100ms
Department Credit: slideUp 400ms ease-out · delay 150ms
Button:           slideUp 400ms ease-out · delay 200ms
退出:             整体 opacity 0 · 600ms ease-in-out
```

### 3.3 按钮交互

```
默认:   bg-white/15 · text-white · border-white/20
Hover:  bg-white/25 · border-white/40 · scale(1.02)
Active: scale(0.98)
```

### 3.4 响应式

```
>768px:   logo 32px · 间距 24px
≤768px:   logo 24px · 间距 16px
```

---

## 四、性能优化

### 4.1 封面

| 项目 | 当前 | 改造后 |
|------|------|--------|
| 素材 | `splash-final.png` 1.7MB | 0KB (纯 CSS) |
| 加载阻塞 | 是 (大 PNG) | 否 |
| 首次内容绘制 | 依赖图片下载 | 即时渲染 |

### 4.2 Portfolio

| 步骤 | 操作 |
|------|------|
| ① | `cwebp -q 80` 批量转 WebP |
| ② | 清理原 PNG 文件 (`rm *.png`) |
| ③ | 代码中 `portfolio/*.png` → `portfolio/*.webp` |
| ④ | 所有 `<img>` 加 `loading="lazy"` |
| ⑤ | 所有 `<img>` 加显式 `width` / `height` |

### 4.3 SplashScreen.tsx 改动

```tsx
// 删除
import splash-final.png
<image> 标签
useContainMetrics()          // 整个 hook 删除
BTN_X/Y/W/H 硬编码坐标       // 删除

// 替换为
<div style={{ background: "radial-gradient(ellipse at 50% 30%, #7A3A4A 0%, #6A2B3A 70%)" }}>
  <h1>Momcozy</h1>
  <p class="slogan-zh">为妈妈的舒适不断进化</p>
  <p class="slogan-en">Evolving for Mom and Cozy</p>
  <span class="credit">数字化-数据科学部 创作</span>
  <button>开始创作</button>
</div>
```

---

## 五、执行清单

| # | 文件 | 操作 |
|---|------|------|
| 1 | `SplashScreen.tsx` | 重写为纯 CSS/HTML 封面 |
| 2 | `web/public/portfolio/` | PNG→WebP 批量转换 |
| 3 | `demo-data.ts` | `portfolio/*.png` → `portfolio/*.webp` |
| 4 | `AssetLibrary.tsx` | `<img>` 加 `loading="lazy"` |
| 5 | 清理 | `rm web/public/splash-*.png` |

**预估**: 封面重写 30min · 图片转换 15min · 合计 45min。

## 六、自审

- 无 TBD/TODO · 无外部依赖 · 0KB 封面素材 · Momcozy 品牌色准确 · 响应式覆盖
