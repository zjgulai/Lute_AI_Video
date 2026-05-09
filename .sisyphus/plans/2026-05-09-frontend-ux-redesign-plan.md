---
name: frontend-ux-redesign-plan
description: Phased UX/IA redesign plan for Short Video Factory frontend. Preserves existing color palette (Fortune Red, cream, ink, pale-gold, jade). Authored from a senior product designer's lens — structure first, then language, then visual rhythm. Use when executing the post-review optimization roadmap.
---

# Short Video Factory · 前端体验重构计划

> **作者视角**：一位关心"用户为什么用、为什么留下来、为什么推荐"的资深产品设计师。
> **不做的事**：换配色、换字体家族、推翻已有组件库、做大爆改。
> **做的事**：**先重组结构，再校准语言，最后打磨节奏**。
> **评分目标**：现状 5.5/10 → 第二阶段后 7.5/10 → 第四阶段后 8.5/10。

## 核心约束（不可违反）

| 类别 | 约束 |
|---|---|
| **配色** | 保留 `--fortune-red` `--pure-white` `--elegant-cream` `--gold-foil` `--jade-accent` `--cinnabar` `--misty-pink` 全部 token；不引入新主色 |
| **字体** | 保留 `Montserrat` (display) + `Inter` (body) + `SF Mono` |
| **品牌气质** | 保留"东方胶片"调性：film grain、暖色卡片、墨玉文字层级 |
| **不重写** | `apple-card` `apple-btn` `apple-input` 三个核心样式类；`SceneTabs` `Nav` `AssetCard` 三个核心组件 |
| **后端改动** | 仅当前端无法独立完成时才动后端，且必须最小侵入 |

## 设计哲学（贯穿四个阶段）

1. **Information Architecture > Visual Polish** — 用户说"乱"是结构问题，不是色彩问题。
2. **One Concept Per Page** — 当前 `/brand-packages` 同时承载"品牌包/创作产物/已完成作品"三种心智，必须拆。
3. **Defaults Are the Product** — 首屏看到中文、Continue 不灰、空状态有方向，比 10 个新功能重要。
4. **Less Chrome, More Content** — 砍掉重复 filter、重复按钮、装饰性图标，让卡片本身说话。
5. **Restraint Over Decoration** — 一个 Fortune Red 主色 + 一个 jade 辅色就够了，不要在每个组件叠 5 个状态色。

---

## Phase 1 · 信息架构重塑（Week 1，最高优先级）

> **设计师视角**：这一阶段不画一行 CSS。先画导航树、再画状态机，最后才动代码。

### 1.1 心智模型重新定义

**当前糟糕状态**（用户实测，3 个页面互相窃取语义）：

```
/brand-packages     → 品牌资产 = 425 个 mp4/mp3/png 流水线产物 + 2 个真品牌资产
/footage            → 创作画廊 = 又是一批流水线 mp4
/influencers        → 网红管理（孤儿路由，导航里没有）
```

**目标状态**（按"资产生命周期"分层）：

```
顶部导航栏（4 项，有序，覆盖核心场景）
├─ 首页（/）              — 创作入口
├─ 我的作品（/works）     — 已发布/可发布的最终视频（新增独立路由）
├─ 资产库（/library）     — Tab：素材 / 品牌包 / 网红
└─ 设置（/settings）
```

**路由迁移映射表**（明确无歧义）：

| 旧路由 | 状态 | 新去向 |
|---|---|---|
| `/footage` | 301 重定向 | `/works`（只显示 final 作品）+ `/library?tab=materials`（中间素材） |
| `/brand-packages` | 301 重定向 | `/library?tab=brand_kit` |
| `/influencers` | 301 重定向 | `/library?tab=influencers` |
| `/s1` `/s2` `/s3` `/s5` `/fast` | 不变 | 保留 |
| `/result` | 不变 | 保留（单次结果详情） |
| `/admin/*` | 不变 | 保留 |

`资产库`内部用 Tab 分三层：

| Tab | 内容 | 操作 |
|---|---|---|
| **素材** | 用户上传的原始视频/图片 + 流水线中间产物（折叠默认隐藏） | 上传、删除、重用 |
| **品牌包** | Logo / 品牌色 / Brand Voice / 字体规范 | 编辑、关联场景 |
| **网红** | 合作网红档案 | 增删改 |

### 1.2 交付物

- [ ] `docs/design/information-architecture-v2.md` — 导航树 + 路由映射表 + 后端字段对应（不写代码先写文档）
- [ ] `docs/design/asset-lifecycle-state-machine.md` — 一张图说清楚一个文件从生成到归档的状态流转
- [ ] [Nav.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/Nav.tsx) 改为 4 项导航（首页 / 我的作品 / 资产库 / 设置）
- [ ] **新建 `/works` 路由**（[web/src/app/works/page.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/works/page.tsx)）— 只渲染 `kind=final_work` 的资产
- [ ] **新建 `/library` 路由**（[web/src/app/library/page.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/library/page.tsx)）+ 三个 Tab 子组件 `MaterialsTab` `BrandKitTab` `InfluencersTab`，分别复用现有 `/footage` `/brand-packages` `/influencers` 的有效逻辑
- [ ] 旧路由 `/footage` `/brand-packages` `/influencers` 改为重定向页面（在各自 `page.tsx` 顶部用 `redirect()` from `next/navigation`），不再渲染 UI
- [ ] 后端 `/api/assets` 返回字段加 `kind: "brand_kit" | "creation_intermediate" | "final_work"`

### 1.3 QA 验证场景（可执行）

**V1.3.a 导航信息架构 — Playwright + 人工路由验证**

```
工具：Playwright MCP（ignoreHTTPSErrors context）
步骤：
  1. browser_navigate → https://101.34.52.232/
  2. browser_snapshot → 顶栏 Nav 子元素
  3. 断言：导航链接数量 === 4
  4. 断言：顺序文本 === ["首页","我的作品","资产库","设置"]
  5. 断言：所有链接 innerText.length 汇总 ≤ 12（汉字计为 2）
  6. browser_click → "资产库"
  7. 断言：URL 最终为 /library
  8. browser_navigate → https://101.34.52.232/brand-packages
  9. 断言：URL 最终重定向到 /library?tab=brand_kit
  10. browser_navigate → https://101.34.52.232/influencers
  11. 断言：URL 最终重定向到 /library?tab=influencers
  12. browser_navigate → https://101.34.52.232/footage
  13. 断言：URL 最终重定向到 /works
通过条件：全部断言通过；顶栏无英文原文
失败处理：记入 findings.md，阻塞进入 Phase 2
```

**V1.3.b 2-Click-to-Final-Video 场景 — Playwright 真实用户路径**

```
场景：用户已生成过 1 支 S1 视频（测试前通过 API seed 一条 final_work）
步骤：
  1. browser_navigate → https://101.34.52.232/
  2. 记录 click_count = 0
  3. browser_click → 导航"我的作品"；click_count++
  4. browser_wait_for → 作品列表 grid 渲染完毕（[data-asset-card] 至少 1 个）
  5. 断言：URL 为 /works
  6. browser_click → 第一张卡片；click_count++
  7. 断言：出现可播放 <video> 元素，src 非空
通过条件：click_count ≤ 2 且视频 src 可播放（HEAD 200）
```

**V1.3.c 品牌包 Tab 数据纯净度 — API + DOM 双重验证**

```
工具：curl + Playwright
步骤：
  1. curl https://101.34.52.232/api/assets?kind=brand_kit -H "X-API-Key: ..." | jq '. | length'
  2. 断言：返回数量 ≤ 20
  3. browser_navigate → /library?tab=brand_kit
  4. 断言：DOM 中 [data-asset-card] 数量等于 API 返回数量
  5. 断言：无 filename 形如 seedance_* / cosyvoice_* / poyo_img_*（用正则扫 DOM）
通过条件：全部断言通过
```

**V1.3.d 文档产出验证 — 文件存在性**

```
步骤：
  1. ls docs/design/information-architecture-v2.md
  2. ls docs/design/asset-lifecycle-state-machine.md
  3. grep -c "^## " docs/design/information-architecture-v2.md
通过条件：两个文档存在；IA v2 至少含 4 个 H2 区块（导航树/路由映射/后端字段/决策）
```

### 1.4 非目标（明确不做）

- 不改 `/s1` `/s2` `/s3` `/s5` 场景表单页内部布局
- 不动流水线监控逻辑
- 不引入新色

---

## Phase 2 · 语言系统校准（Week 1–2，与 P1 并行）

> **设计师视角**：i18n 不是翻译问题，是品牌问题。中英混排让产品看起来像 demo，不像产品。

### 2.1 默认 locale 修复

```ts
// I18nProvider.tsx — 新初始化逻辑
const detectInitialLocale = (): Locale => {
  if (typeof window === 'undefined') return 'zh';
  const stored = localStorage.getItem('app-locale');
  if (stored === 'zh' || stored === 'en') return stored;
  return navigator.language?.startsWith('zh') ? 'zh' : 'en';
};
```

### 2.2 文案三层规则

| 层 | 规则 | 例 |
|---|---|---|
| **导航/标题** | 100% 走 i18n，禁止英文硬编码 | `t('nav.library')` → 「资产库」 |
| **占位符** | 跟随 locale；中文用真实样例，英文用 `e.g.` 前缀 | 中：「例如：M5 免手扶吸奶器」/ 英：`e.g. M5 hands-free pump` |
| **CTA 按钮** | 短动词；ZH ≤ 4 字、EN ≤ 12 chars | `继续` / `Continue` ；`生成视频` / `Generate` |

### 2.3 文案审查清单

线上抓到的"必修"文案：

- [ ] `Brand Assets` → 「品牌资产」（H1）
- [ ] `AI Portfolio` → 「我的作品」
- [ ] `Influencers` → 「合作网红」
- [ ] `Asset Upload` → 「上传素材」
- [ ] `Continue →` → 「下一步 →」
- [ ] `Quick Templates` → 「快速模板」
- [ ] `Add Influencer` → 「添加网红」
- [ ] `scene.other.title`（裸键泄露）→ 加翻译键 + fallback 到「未分类」
- [ ] 错误文案「后端连接失败，显示本地数据」→ 「暂时无法连接服务器，已为你显示本地缓存的资产，刷新后将重试」
- [ ] 空状态文案统一句式：「{对象名}还是空的 + 一句"为什么应该填" + 主 CTA」

### 2.4 交付物

- [ ] `web/src/i18n/translations.ts` 翻译键覆盖率 100%（用脚本扫描所有 `t(\`xxx\`)` 调用）
- [ ] `web/src/i18n/I18nProvider.tsx` 默认 locale 修复
- [ ] 顶栏「中 / EN」按钮显示当前态（不再只显示「中」一个字）
- [ ] 所有英文硬编码 H1/H2/Button 用 `t()` 替换（grep `[A-Z][a-z]+ [A-Z][a-z]+` 反查）

### 2.5 QA 验证场景（可执行）

**V2.5.a i18n 覆盖率扫描 — 脚本统计**

```bash
# 在 web/ 目录运行
# 1. 统计所有 t("xxx") 和 t(`xxx`) 调用
TOTAL_KEYS=$(grep -roE 't\(["`][a-zA-Z][^"`]+["`]\)' src/ | sort -u | wc -l)
# 2. 统计 translations.ts 中 zh 的键数
ZH_KEYS=$(grep -cE '^\s+"[a-z]+\.[a-z]+.*":' src/i18n/translations.ts)
# 3. 期望 TOTAL_KEYS 中的每个 key 都能在 zh 字典里找到
for key in $(grep -roE 't\(["`]([a-zA-Z][^"`]+)["`]\)' src/ | grep -oE '["`][^"`]+["`]' | tr -d '`"' | sort -u); do
  grep -q "\"$key\":" src/i18n/translations.ts || echo "MISSING: $key"
done
```
通过条件：MISSING 输出为空；TOTAL_KEYS ≥ 200（粗估当前规模）

**V2.5.b 默认 locale 检测 — Playwright**

```
步骤：
  1. 清除 localStorage & cookies
  2. browser_run_code_unsafe → newContext({ locale: 'zh-CN' })
  3. browser_navigate → https://101.34.52.232/
  4. browser_evaluate → document.documentElement.lang
  5. 断言：返回 "zh-CN"
  6. browser_evaluate → document.querySelector('h1')?.innerText
  7. 断言：不匹配正则 /^[A-Za-z\s]+$/（意味着不是纯英文）
通过条件：首屏 H1 为中文
```

**V2.5.c 中英混排检测 — DOM 扫描**

```
步骤：
  1. 在所有 6 个路由（/, /library, /s1, /s2, /s3, /s5, /fast）执行：
  2. browser_evaluate →
     const texts = Array.from(document.querySelectorAll('h1,h2,h3,button,a,label'))
       .map(e => e.innerText.trim()).filter(Boolean);
     const mixedCases = texts.filter(t =>
       /[\u4e00-\u9fa5]/.test(t) && /[A-Z][a-z]{3,}/.test(t)
     );
     return mixedCases;
  3. 断言：返回数组为空（忽略已知白名单：Momcozy, MP4, API, SKU, CosyVoice, Seedance, poyo）
通过条件：所有 6 个路由返回 []
```

**V2.5.d 切换 locale 不刷新 — Playwright**

```
步骤：
  1. browser_navigate → /
  2. const h1Before = h1.innerText
  3. browser_click → 语言开关按钮
  4. browser_wait_for → text="中"→"EN"（或反之）
  5. const h1After = h1.innerText
  6. 断言：h1After !== h1Before 且 window.performance.navigation.type !== 1（未刷新）
通过条件：切换无页面 reload 且文案变更
```

---

## Phase 3 · 表单与转化路径（Week 2–3）

> **设计师视角**：表单是产品最贵的资产，因为这是用户付出注意力的地方。每多一个无关字段，转化率掉 5%。

### 3.0 实施目标确认（先解决"改哪个表单"）

线上实测：[`SceneForm.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/SceneForm.tsx#L13) 的环境变量 `NEXT_PUBLIC_USE_GUIDED_FORM` 默认 `!== "false"` 即默认 **true**，这意味着：

- **默认渲染：** [`GuidedForm.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/GuidedForm.tsx)（326 行，分步引导）
- **被 hidden：** `SceneForm.tsx` 内部的 legacy 大表单（用 `className="hidden"` 包裹）

**Phase 3 实施目标的明确边界：**

| 改动对象 | 是否要做 |
|---|---|
| **`GuidedForm.tsx`** | ✅ **主要改动目标**（默认线上启用） |
| `SceneForm.tsx` legacy 块 | ⚠️ 只补 `<label htmlFor>` 即可，不重构（用户看不到） |
| 环境变量 `NEXT_PUBLIC_USE_GUIDED_FORM` | ❌ 不变（保持 default true） |
| `FastModePanel.tsx` 表单 | ✅ 同步改 label 关联 |
| `influencers` 模态表单 | ✅ 改 label htmlFor + chip input |

> **决策**：Phase 3 的所有"label / a11y / sticky CTA / missing fields 提示"工作以 `GuidedForm.tsx` 为主战场。`SceneForm.tsx` 仅做最小修补，让 fallback 也合规但不投入精力优化它。

### 3.1 GuidedForm 重构（不重写，只精修）

#### 问题清单（实测）

1. 10 个 input/textarea **零 `<label>` 零 `aria-*`**
2. 主 CTA「Continue →」**首次访问就 disabled**，且 y=2242（首屏 3 屏外）
3. Quick Templates 副标题中英混排
4. Product Details / Brand Voice 折叠区让用户不知道"哪些字段是必填的"

#### 设计动作

1. **字段分层**：把 10 个字段拆成 **3 个必填（产品名、卖点、品牌名）+ 其他可选**，可选字段全部进入"高级（Advanced）"折叠区，**默认收起**。
2. **Sticky 主 CTA**：把「下一步」按钮固定在视窗底部右下角，浮起时带 `--fortune-red` 微光（用现有 `--line-glow` token），桌面端 sticky，移动端 fixed。
3. **缺失提示**：
   ```tsx
   {missingRequired.length > 0 && (
     <span className="text-[12px] text-[var(--text-muted)] ml-2">
       还缺：{missingRequired.join(' · ')}
     </span>
   )}
   ```
4. **Label 改造**（每个 input）：
   ```tsx
   <label htmlFor="product-name" className="block text-xs font-medium text-[var(--text-body)] mb-1">
     产品名称 <span className="text-[var(--fortune-red)]">*</span>
   </label>
   <input id="product-name" name="product_name" aria-required="true" ... />
   ```
5. **Quick Template 反馈**：点击后 toast「已套用『USP Demo』模板」+ 高亮被预填字段 600ms（用 `--bg-selected` token 闪一下，复用现有色）。

### 3.2 影响者表单（influencers）

- [ ] 模态框中所有 `<label>` 加 `htmlFor`
- [ ] 删除空状态时**重复出现的「Add Influencer」按钮**（顶部 + 中间空状态共 2 次，保留中间一个）
- [ ] Platforms / Style Tags 输入框改用 chip 输入（每输入一个标签按 Enter 形成胶囊），而不是逗号分隔的 plain text

### 3.3 交付物

- [ ] [GuidedForm.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/GuidedForm.tsx) **主要改动**：全字段 `<label htmlFor>` 关联 + sticky CTA + missing 提示
- [ ] [SceneForm.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/SceneForm.tsx) **最小修补**：legacy 块的 input 加 `<label htmlFor>`（hidden 也要合规），不做其他重构
- [ ] [FastModePanel.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/components/FastModePanel.tsx) 同步加 label
- [ ] 新组件 `FormFieldGroup`（label + input + hint + error 四件套）抽出来复用
- [ ] 新组件 `StickyActionBar`（sticky CTA 容器）
- [ ] 新组件 `TagInput`（chip 输入）
- [ ] [influencers/page.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/influencers/page.tsx) 模态表单改 label + chip input + 删除重复按钮（**注意**：Phase 1 已把此页重定向到 `/library?tab=influencers`，实际改动应在新建的 `InfluencersTab` 子组件里，旧 `page.tsx` 仅保留 redirect）

### 3.4 QA 验证场景（可执行）

**V3.4.a Lighthouse Accessibility 评分**

```bash
# 在本地或 CI 运行
npx lighthouse https://101.34.52.232/ \
  --only-categories=accessibility \
  --output=json --output-path=./tmp/lh-home.json \
  --chrome-flags="--ignore-certificate-errors"
# 同理扫 /library /s1 /fast
jq '.categories.accessibility.score * 100' tmp/lh-home.json
```
通过条件：4 个高频页 accessibility score ≥ 95

**V3.4.b 表单 label 关联率 — Playwright DOM**

```
步骤：
  1. browser_navigate → /s1
  2. browser_evaluate → 验证默认渲染的是 GuidedForm（不是 hidden 的 SceneForm legacy）：
     const guided = document.querySelector('[data-guided-form]');
     const legacy = document.querySelector('[data-legacy-form]');
     return { guidedVisible: !!guided && getComputedStyle(guided).display !== 'none',
              legacyHidden: !legacy || getComputedStyle(legacy).display === 'none' };
  3. 断言：guidedVisible === true && legacyHidden === true
  4. browser_evaluate →
     const fields = document.querySelectorAll('[data-guided-form] input, [data-guided-form] textarea, [data-guided-form] select');
     const noLabel = Array.from(fields).filter(f => {
       const id = f.id;
       if (!id) return true;
       return !document.querySelector(`label[for="${id}"]`);
     });
     return { total: fields.length, noLabel: noLabel.length };
  5. 断言：noLabel === 0 且 total > 0
通过条件：GuidedForm 默认可见且所有字段都有 <label htmlFor>
```

**V3.4.c 键盘可导航性 — Playwright**

```
步骤：
  1. browser_navigate → /s1
  2. 循环 browser_press_key("Tab") × 30
  3. 每次记录 document.activeElement 的 tag + id + role
  4. 断言：能 tab 到所有必填字段 + 主 CTA
  5. 断言：无元素被 tab 跳过（tabindex=-1 只允许在明确 skip-link）
通过条件：keyboard-only 可完成"产品名 → 卖点 → 品牌名 → 下一步"全流程
```

**V3.4.d Sticky CTA 可见性 — Playwright**

```
步骤：
  1. browser_navigate → /s1
  2. browser_resize → 1440x900
  3. browser_evaluate → 主 CTA 按钮 getBoundingClientRect()
  4. 断言：rect.bottom <= 900 && rect.top >= 0（视窗内可见）
  5. 断言：button.disabled === true（空表单）
  6. 断言：按钮旁边存在 text 包含"还缺"或"需要填写"的元素
  7. browser_fill_form → 填完 3 个必填字段
  8. 断言：button.disabled === false 且 missing 提示消失
通过条件：全部断言通过
```

**V3.4.e CTA 响应时延 — 前端 telemetry**

```
步骤：
  1. browser_run_code_unsafe → 注入 performance.mark
  2. browser_click → 主 CTA
  3. 测 performance.measure('cta-response', 'click', 'state-changed')
  4. 断言：duration < 200ms
通过条件：p95 < 200ms（重复 10 次）
```

---

## Phase 4 · 视觉节奏与质感打磨（Week 3–4）

> **设计师视角**：到这一步配色已经定了、结构已经清了、文案已经顺了，最后做的是"呼吸感"。

### 4.1 间距与字号节律（不改色，只改节奏）

线上实测的字号混乱：H1 = 18px / 64px / H3 = 12px / 15.75px。**这不是"高端"，是"随手"**。

定义一套节律 token（写进 `globals.css`，复用现有色）：

```css
/* Type scale — 1.25 modular */
--ts-display:    32px;   /* 首屏品牌名 Momcozy */
--ts-h1:         24px;   /* 页面 H1 */
--ts-h2:         18px;   /* 区块标题 */
--ts-h3:         14px;   /* 卡片标题 */
--ts-body:       13px;   /* 正文 */
--ts-caption:    12px;   /* 辅助文字 */

/* Spacing scale — 4pt grid */
--sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
--sp-6: 24px; --sp-8: 32px; --sp-12: 48px; --sp-16: 64px;
```

应用规则：**所有 padding / margin / gap 必须从 token 选**，不再出现 `gap-3 mb-6 p-12` 混搭无章。

### 4.2 卡片网格密度

`/brand-packages` 当前一屏渲染 425 张卡片，卡片间距过密（`gap-3` = 12px）。

调整：

- 网格间距 `gap-3` → `gap-4`（12 → 16px），呼吸更舒展
- 卡片内 padding `p-3` → `p-4`（12 → 16px）
- 卡片标题字重 600 → 500（视觉更克制，与 cream 背景更协调）

### 4.3 空状态系统化

5 个空状态画 5 个**统一风格的极简插画**（线性、单色、用 `--misty-pink` 描边，无填充）：

| 场景 | 插画概念 | CTA |
|---|---|---|
| 网红列表为空 | 一支虚线人形 + 「+」 | 添加你的第一位合作网红 |
| 素材库为空 | 一张胶片格 + 上传箭头 | 上传你的第一段素材 |
| 品牌包为空 | 一个调色盘轮廓 | 创建你的第一个品牌包 |
| 我的作品为空 | 一台播放器轮廓 | 去首页创作第一支视频 |
| 搜索无结果 | 放大镜 + 问号 | 换个关键词试试 |

### 4.4 加载状态

把骨架屏的 `animate-pulse` bg-color 从 `--bg-panel` 改成 `linear-gradient` shimmer（仍然用 cream/pink 色域，不引入新色）。

### 4.5 移动端适配（最低限度）

不做完整 mobile redesign，只确保 5 个高频页 ≥ 375px 不横向溢出：

- [ ] 首页：5 个场景卡 → 移动端竖排 + 横滑
- [ ] `/library`：左侧分类 sidebar → 顶部 horizontal chip
- [ ] 顶栏：Nav 折叠成 hamburger
- [ ] SceneForm：Quick Templates 4 列 → 2x2
- [ ] 作品卡片：`grid-cols-2 md:grid-cols-3` 已 OK，验证即可

### 4.6 交付物

- [ ] `web/src/app/globals.css` 加 type-scale + spacing-scale token
- [ ] `web/src/components/EmptyState.tsx` 新组件（统一空状态）
- [ ] 5 个 SVG 插画（设计师独立产出，不要 AI 生图）
- [ ] 5 个高频页移动端截图验收（375 / 414 / 768）

### 4.7 QA 验证场景（可执行）

**V4.7.a Type scale 收敛 — 源码扫描**

```bash
cd web/
# 抓所有 Tailwind 任意字号类
grep -rohE 'text-\[[0-9]+(\.[0-9]+)?(px|rem)\]' src/ | sort -u > /tmp/typescale.txt
# 抓所有 hard-coded fontSize 样式
grep -rohE 'fontSize:\s*["`][0-9]+(\.[0-9]+)?(px|rem)["`]' src/ | sort -u >> /tmp/typescale.txt
wc -l /tmp/typescale.txt
```
通过条件：字号种类 ≤ 6；所有新增组件必须用 `--ts-*` CSS 变量或预定义 utility 类

**V4.7.b Spacing scale 收敛 — 源码扫描**

```bash
# 抓所有 Tailwind padding/margin/gap 任意值
grep -rohE '(p|m|gap|space-[xy])-\[[0-9]+(px|rem)\]' src/ | sort -u > /tmp/spacing.txt
# 抓标准化 gap/p 值
grep -rohE 'className="[^"]*\b(gap|p|m|space-[xy])-[0-9]+\b' src/ | \
  grep -oE '(gap|p|m|space-[xy])-[0-9]+' | sort -u >> /tmp/spacing.txt
wc -l /tmp/spacing.txt
```
通过条件：spacing 种类 ≤ 8

**V4.7.c 移动端视口扫描 — Playwright 多分辨率**

```
步骤：
  1. 对每个分辨率 [375, 414, 768] 和每个路由 [/, /library, /s1, /fast, /result]：
  2. newContext({ viewport: { width, height: 812 }, ignoreHTTPSErrors: true })
  3. browser_navigate → url
  4. browser_evaluate →
     ({
       bodyScrollWidth: document.body.scrollWidth,
       windowInnerWidth: window.innerWidth,
       overflowing: document.body.scrollWidth > window.innerWidth + 1
     })
  5. 断言：overflowing === false
  6. browser_take_screenshot → tmp/mobile/{route}-{width}.png
通过条件：15 个组合（3 分辨率 × 5 路由）全部不溢出
```

**V4.7.d 空状态三件套 — Playwright DOM 扫描**

```
步骤：
  每个空状态页面（/library?tab=influencers 无数据、/library?tab=brand_kit 无数据 等）：
  1. browser_navigate
  2. browser_evaluate →
     const empty = document.querySelector('[data-empty-state]');
     return {
       hasIllustration: !!empty?.querySelector('svg[data-illustration]'),
       hasText: (empty?.querySelector('[data-empty-title]')?.innerText || '').length > 0,
       hasCTA: !!empty?.querySelector('button[data-empty-cta]')
     };
  3. 断言：三个都为 true
通过条件：5 个空状态全部三件套齐全
```

**V4.7.e 设计 token 使用率 — 语义化 class 抽样**

```bash
# 抽 10 个随机组件文件，验证颜色值是否都用 CSS variable
for f in $(find src/components -name "*.tsx" | shuf -n 10); do
  echo "=== $f ==="
  # 找出所有 hard-coded hex 颜色（非注释）
  grep -nE '#[0-9a-fA-F]{3,8}' "$f" | grep -v '//' || echo "  ✓ clean"
done
```
通过条件：≥ 80% 采样文件无硬编码 hex（剩余 ≤ 20% 是 svg stroke 等合理例外）

---

## Phase 5 · 长流水线 UX（Week 4，可选）

> 如果前 4 个阶段顺利，再做这一个；否则推迟到下一轮。

### 5.1 问题

S1/S2/S3/S5 流水线 5–30 分钟，当前 UX 是全屏 loading 遮罩 + 步骤文字。用户：
- 不能切走做别的事
- 不知道大概还有多久
- 失败了不知道如何重试

### 5.2 设计动作

- [ ] 流水线开始后：loading 遮罩 5 秒后**自动收起**，进度移到顶部 sticky 状态条
- [ ] 状态条显示：当前步骤名 + 预计剩余分钟（基于 [page.tsx:248-261](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/page.tsx#L248-L261) 的 duration 估算）
- [ ] 用户可关闭浏览器，pipeline 继续；完成后通过浏览器通知 + 邮件提醒
- [ ] 失败状态展示「这一步出错了 + 一键重试 + 跳过此步」三选项

### 5.3 QA 验证场景（可执行）

**V5.3.a 流水线后台运行 — Playwright 多 tab**

```
步骤：
  1. browser_navigate → /s1，填表单并点击"下一步"开始流水线
  2. browser_wait_for → text="流水线运行中" 或 progress bar 出现
  3. browser_wait_for time=8 秒（等 loading 遮罩自动收起）
  4. 断言：遮罩 display=none；顶部 sticky 状态条可见
  5. browser_click → 导航"资产库"
  6. 断言：页面切到 /library，流水线状态条仍可见在顶部
  7. browser_navigate_back → 回到流水线页
  8. 断言：流水线状态未重置，仍在运行
通过条件：全部断言通过，流水线不被路由切换打断
```

**V5.3.b 失败恢复 UX — Playwright + API mock**

```
步骤：
  1. 用 API 提交一个故意失败的流水线（例如非法 product_catalog）
  2. browser_wait_for → text="这一步出错" 或类似失败提示
  3. 断言：页面出现 3 个按钮 "重试"、"跳过此步"、"查看详情"
  4. browser_click → "重试"
  5. 断言：流水线状态变回 running
通过条件：失败后用户有明确可操作路径，且重试 UI 响应
```

**V5.3.c 浏览器通知 — 用户交互测试（半自动）**

```
步骤：
  1. browser_run_code_unsafe → navigator.permissions.query({name:'notifications'}).then(p => p.state)
  2. 断言：首次访问时曾弹出通知权限请求（或检查本地存储）
  3. 关闭浏览器 → 等待流水线完成 → 重开
  4. 人工验证：收到系统通知 / 或 /library 顶部显示"你的作品已完成"badge
通过条件：至少一种提醒渠道生效
```

---

## 执行节奏

| 周 | 主要交付 | 影响 |
|---|---|---|
| W1 | Phase 1 IA + Phase 2 i18n | 用户首屏体验从"乱"到"顺" |
| W2 | Phase 3 表单 + Phase 2 收尾 | 转化率 +20% 预期 |
| W3 | Phase 4 视觉节奏 | 产品质感从"demo"到"产品" |
| W4 | Phase 5 流水线 UX（可选） | 从"工具"到"伙伴" |

## 跟踪清单

- [ ] **Phase 1 完成时**：用户测试（5 人），找到最终视频耗时 < 30s
- [ ] **Phase 2 完成时**：i18n key 覆盖率 = 100%，无中英混排
- [ ] **Phase 3 完成时**：Lighthouse a11y ≥ 95
- [ ] **Phase 4 完成时**：设计 token 覆盖率 ≥ 90%
- [ ] **Phase 5 完成时**：用户可关闭浏览器后流水线仍完成

---

## 决策日志（Decision Log）

记录每个阶段中需要在「正确」和「省事」之间选时的判断：

| 时间 | 决策 | 理由 |
|---|---|---|
| 2026-05-09 | 不重写 `apple-card` 等核心样式类 | 已稳定且与品牌一致；重写收益低、风险高 |
| 2026-05-09 | 保留 `/footage` 路由 301 到 `/library` | 外链可能被收藏，破坏成本 > 重构收益 |
| 2026-05-09 | i18n 默认 zh-CN 而不是 EN | 主用户群是中文母语者，且 lang 标签已是 zh-CN |
| 2026-05-09 | 不引入新色 | 用户明确要求 + 现有 24 色 token 已饱和 |
