# 会说话的 UI 2.0 — 完整迭代执行计划

**版本**: v2.0 · **日期**: 2026-04-30  
**依赖**: 设计文档 `conversational-ui-2.0-design.md`  
**原则**: Phase 顺序执行，每 Phase 有独立自证条件，旧代码保留不删除

## 执行前注意事项（基于对当前代码的最终审查）

| # | 注意 | 影响 |
|---|------|------|
| 1 | `SceneForm.tsx` 已 895 行，追加 GuidedForm 条件渲染应控制在 20 行内（仅路由逻辑） | GuidedForm 内部逻辑全部自包含 |
| 2 | `page.tsx` 已 1121 行，`isGenerating` 和底部条抽取为 `useExecutionBar` hook | 新建 `web/src/hooks/useExecutionBar.ts` |
| 3 | `FastModePanel` 由 `page.tsx:844` 直接渲染，不走 SceneForm | 保留此行为，快速模式无 GuidedForm |
| 4 | Nav 当前仅 2 项（首页、品牌资产），`footage` 通过 AssetLibrary 弹窗访问 | Phase 8 需同步更新 Nav 组件 |
| 5 | S4 实拍素材的结果中 `briefs[0].topic` 可能为 null | 发布区提取时加 `?.` 可选链 + 空字符串 fallback |

---

## 执行总览

| Phase | 模块 | 新建文件 | 修改文件 | 工时 |
|-------|------|---------|---------|------|
| 1 | 数据层 | — | 3 | 1.5h |
| 2 | 核心组件 | 5 | — | 3h |
| 3 | 集成替换 | — | 3 | 1h |
| 4 | 回退兼容 | — | 1 | 0.5h |
| 5 | 执行页 | 2 | 3 | 2h |
| 6 | 发布阶段 | 1 | 1 | 1.5h |
| 7 | 数据复盘 | 1 | 1 | 1.5h |
| 8 | 创作画廊 | 1 | 3 | 1.5h |
| 9 | 品牌资产 | 1 | 1 | 1.5h |
| **合计** | | **11** | **16** | **14h** |

> Phase 5 新建含 `useExecutionBar.ts` hook；Phase 8 修改含 `Nav.tsx`。

---

## Phase 1: 数据层 (1.5h)

**目标**: 所有新 UI 所需的类型、数据和翻译就位。

### 1.1 `web/src/components/types.ts`
新增类型定义：
- `CardPriority` — `"required" | "recommended" | "optional"`
- `VideoType` — `{ id, name, desc }` 视频类型条目
- `GuidedCard` — `{ priority, stepName, stepIcon, question, reason, connectionText, fieldKey, inputType }`
- `CardStep` — 步骤隐喻名映射
- `LiveSummaryEntry` — 预览面板条目
- `TemplatePreset` — 快捷模板数据结构

### 1.2 `web/src/demo-data.ts`
新增数据：
- 6 个场景 × N 种视频类型的卡片序列定义
- 3 个模板预设 (Momcozy M5 品牌形象片/产品种草/默认空白)
- 6 个场景的纵轴视频类型列表

### 1.3 `web/src/i18n/translations.ts`
新增翻译 key（zh/en 各 ~50 条）：
- 引导问题文案 (`card.question.*`)
- 连接线文字 (`card.connection.*`)
- 步骤隐喻名 (`step.meta.*`)
- 预览面板标签 (`summary.*`)
- 执行页叙事文案 (`exec.narrative.*`)
- 发布区文案 (`publish.*`)
- 画廊/品牌资产导航文案 (`gallery.*`, `brand.*`)

**自证**: `grep 'card\.' translations.ts | wc -l` ≥ 30

---

## Phase 2: 核心组件 (3h)

### 2.1 `GuidedForm.tsx`（新建）
矩阵导航 + 卡片渲染引擎 + 右预览栏 + 模板按钮。
- Props: `scene`, `videoType`, `onSubmit`
- 内部状态: 当前焦点卡片 index，已填写值 map，折叠状态
- 渲染: 左区卡片流 + 右区 `LiveSummary` + 顶部模板下拉

### 2.2 `GuidedCard.tsx`（新建）
单张引导卡片组件。
- Props: `card: GuidedCard`, `value`, `onChange`, `isFocused`, `onFocus`
- 状态: 展开/折叠（填完后自动折叠）
- 渲染: 优先级色标 + 步骤名/emoji + 引导问题 + 原因说明 + 输入框

### 2.3 `CardConnector.tsx`（新建）
连接线组件。渲染上下两张卡片之间的竖线 + 引导文字 + 箭头。

### 2.4 `LiveSummary.tsx`（新建）
右侧实时预览面板。纯前端从已填数据提取结构化摘要。

### 2.5 `QuickTemplate.tsx`（新建）
模板下拉选择器。复用上次配置 / 品牌预设 / 空白。

**自证**: `npm run build` 无报错。5 个组件文件存在且可 import。

---

## Phase 3: 集成替换 (1h)

### 3.1 `SceneForm.tsx`
⚠️ 文件已 895 行，改动控制在 20 行以内。仅添加条件路由：
```tsx
{scene !== "fast_mode" ? <GuidedForm scene={scene} onSubmit={onSubmit} loading={loading} /> : (原有表单)}
```
GuidedForm 的所有状态、逻辑、渲染全部自包含在新建组件内。

### 3.2 `SceneTabs.tsx`
无改动——横轴保持现有 6 个标签。

### 3.3 `page.tsx`
提交流程不变。`startSmartCreate` 中 `scenario` 路由保持现有逻辑。

**自证**: SceneForm 选择 brand_vlog 场景 → 渲染 GuidedForm，选择 fast_mode → 渲染旧表单。

---

## Phase 4: 回退兼容 (0.5h)

- 旧表单代码保留，加 `className={USE_GUIDED_FORM ? "hidden" : ""}`
- 功能开关: `NEXT_PUBLIC_USE_GUIDED_FORM=true` 启用（`false` 回退旧版）
- `page.tsx` 顶部读取环境变量

---

## Phase 5: 执行页优化 (2h)

### 5.1 `StageProgress.tsx`
`S1_STEPS` 数组每项加 `narrative` 字段。渲染时展示叙事文案替代技术标签。

### 5.2 `page.tsx`
⚠️ 文件已 1121 行，避免进一步膨胀。新增逻辑抽取为独立 hook。
- 新建 `web/src/hooks/useExecutionBar.ts`：`isGenerating` 状态 + Smart Create 底部条渲染函数 + Expert Studio 保持不变
- `page.tsx` 仅调用 `const { isGenerating, ExecutionBar } = useExecutionBar()` 并渲染 `<ExecutionBar />`

### 5.3 `OneShotResultView.tsx`
改造为「导演回放」滚动叙事版：
- 视频播放器 → 创作脚本 → 关键帧画廊 → 质量报告 → 发布区 → 数据复盘 → 下载
- 原有 tab 结构保留为折叠区

### 5.4 `CreativeSummary.tsx`（新建）
创作小结卡片。右下角弹出，3s 收起。

**自证**: Smart Create 生成中 → 页面底部显示胶囊条 + 可浏览其他页面。

---

## Phase 6: 发布阶段 (1.5h)

### 6.1 `OneShotResultView.tsx`
底部新增发布区段（质量报告下方）。

### 6.2 `PublishFlow.tsx`（新建）
- AI 推荐平台 + 标题/描述自动填充 + 一键发布
- 平台选择交互：点击名称切换选中态
- 发布完成静默替换为确认文字
- 信息衔接: `result.briefs[0]` + `result.scripts[0]` 自动填充

**自证**: 结果页底部可见发布区，标题/描述/标签自动填充，点击发布按钮成功。

---

## Phase 7: 数据复盘 (1.5h)

### 7.1 `OneShotResultView.tsx`
底部发布区下方继续滚动到数据复盘区。

### 7.2 `InsightReport.tsx`（新建）
- 按视频类型展示北极星指标
- AI 总结句（纯前端从指标提取）
- 指标比较（↑15%）+ 下一步建议
- ROI 分解树（仅销售型视频）
- 原有 `PerformanceDashboard` 折叠为「查看详细数据」

**自证**: 品牌形象片结果 → 展示完播率+粉丝增长（非 ROI），产品种草结果 → 展示 ROI 分解树。

---

## Phase 8: 创作画廊 (1.5h)

### 8.1 `footage/page.tsx`
重命名 UI 标题为「创作画廊」。⚠️ 同步更新 `Nav.tsx` 添加「创作画廊」链接（当前 Nav 仅 2 项：首页、品牌资产，footage 通过 header 弹窗访问）。

### 8.2 双 tab 结构
- 成品 tab: `GalleryGrid` 按场景分组，3 列卡片网格
- 素材 tab: 按类型分组（实拍片段/品牌资产/音频素材）

### 8.3 `GalleryGrid.tsx`（新建）
3 列卡片网格组件。每卡 3:2 比例，场景图标/缩略图 + 标题 + 一个关键指标 + 时间戳。

### 8.4 音频展示规则
TTS 配音不出现在画廊。独立上传的品牌音频出现在素材区。

**自证**: 画廊页成品 tab 显示按场景分组的视频卡片，素材 tab 显示按类型分组的文件。

---

## Phase 9: 品牌资产管理 (1.5h)

### 9.1 `brand-packages/page.tsx`
重构为「品牌资产」全品类内容仓库：
- 左侧垂直导航树（品牌身份/已产出内容）
- 右侧卡片网格（按选中类型展示）

### 9.2 `AssetCard.tsx`（新建）
自适应卡片——视频用 3:2 横向卡，图片用正方形缩略网格，音频用波形条卡片，文本用摘要卡。

### 9.3 自动归类逻辑
创作流程中上传/生成的内容自动进入对应分类：
- 管道生成完成 → AI 视频 + AI 图片
- TTS 步骤 → AI 音频
- 上传产品图 → 品牌身份 → 产品图片
- 上传实拍 → 品牌原创

### 9.4 跨类型搜索 + 来源筛选器
顶部搜索栏 + 来源筛选（AI生成/人工上传/品牌导入）。

**自证**: 生成一条视频后，品牌资产页的「AI 视频」和「AI 图片」分类自动新增条目。

---

## 回退测试清单

- [ ] S1 商品直拍: Smart Create 一键生成 → 导演回放 → 发布 → 数据复盘
- [ ] S3 网红二创: 上传视频 URL → 生成 → 发布
- [ ] S5 品牌VLOG: 卡片引导填写 → 上传六视图 → 生成 → 发布
- [ ] Expert Studio: 逐步执行 → Gate 审核 → 完成
- [ ] 快速模式: 一句话 → 10s 出片
- [ ] 旧版回退: `NEXT_PUBLIC_USE_GUIDED_FORM=false` → 旧表单正常渲染
- [ ] 网络错误: 断网 → toast 提示 → 重连恢复
