---
title: 全站 UI/UX 审计与优化方案
doc_type: analysis
module: frontend
topic: site-ui-ux-audit
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# 全站 UI/UX 审计与优化方案

## 边界

- 本轮只做页面交互、布局、可访问性、空态、错误态和可测试性优化。
- 禁止触发真实生成链路：不调用 `/api/fast/submit`、`/api/fast/generate`、`/scenario/*/submit`、`/scenario/*/gate/*/generate`、`/scenario/*/gate/*/approve`。
- 允许访问静态页面、`/health`、只读 portfolio/admin session 探测和本地 lint/type/build。

## 5 个 Loop 结论

### Loop 1：页面与设计系统基线

- 页面入口集中在 `web/src/app`，核心路径为 `/`、`/s1`-`/s5`、`/fast`、`/works`、`/library`、`/settings`、`/admin/*`。
- 设计系统已有 Fortune Red light theme、`apple-card`、`apple-btn`、`skeleton`、`EmptyState` 等基础资产；问题不是缺组件，而是使用不一致。
- 生产页面健康检查通过：`/`、`/s1?mode=expert`、`/library`、`/works`、`/admin/login` 均返回 200。

### Loop 2：全局导航与响应式

- Home 顶栏和 `TopHeader` 存在重复实现，移动端 Home 顶栏没有隐藏品牌标题，容易挤压导航和右侧管理入口。
- 已将 Home 顶栏对齐 `TopHeader` 的响应式策略：移动端隐藏长标题、压缩 gap、保留图标和主导航。
- 后续应把 Home header 与 `TopHeader` 抽成单一实现，避免后续导航项新增时两处漂移。

### Loop 3：S1-S5/Fast 工作流入口

- `/s1`-`/s5` 使用 `useSearchParams()` 包在 `Suspense` 中，但 fallback 原来是 `null`；慢设备、弱网或 hydration 阻塞时会出现短暂白屏。
- 已新增 `RoutePageSkeleton` 并用于 `/s1`-`/s5`，把白屏改为有语义的加载骨架。
- Fast Mode 页面本轮不触发生成测试；只保留静态渲染和 build 验证。

### Loop 4：Library/Works/Admin 辅助页面

- `/library` 原来也使用 `Suspense fallback={null}`，已接入 `RoutePageSkeleton`。
- `/works` 视频预览弹层缺少 `role="dialog"`、Escape 关闭和焦点恢复；已接入 `useModalBehavior`。
- `AssetPickerModal` 已补 `role="dialog"`、`aria-modal`、标题关联、初始焦点和 Escape 关闭。
- `Admin Logs` 详情弹层已补 Escape 关闭、初始焦点和键盘打开日志行能力。
- `MaterialsTab`、`InfluencersTab`、`ConfirmModal`、`AssetLibrary` 的关闭按钮已改为本地化 `common.close` 或更具体的英文 aria label。

### Loop 5：测试与技术债收口

- 本轮修复优先走低风险 UI 层，不改业务状态机、不改 API contract、不改变生成参数。
- 需要持续保留无 token 验证清单：`eslint`、`tsc --noEmit`、page smoke、`next build`、生产只读页面 200 检查。
- Playwright Chromium 已恢复；本轮只跑只读页面与 i18n smoke，截图差异和移动端真实断点检查归入 P1-8。

## 当前优化 TODO

- [x] 将 S1-S5 和 Library 的空白 fallback 改为页面骨架。
- [x] 修复 Home 顶栏移动端布局挤压风险。
- [x] 补 Works、AssetPicker、Admin Logs 关键弹层的 dialog/focus/Escape 行为。
- [x] 关闭按钮 aria label 本地化或语义化。
- [x] 抽象 Home header 与 `TopHeader`，消除双实现漂移。
- [x] 给 `QuickTemplate` 下拉菜单补 Escape 关闭、焦点恢复和键盘选择。
- [x] 给 `AssetLibrary` 旧预览弹层补 `useModalBehavior`，和 Library/Works 预览行为统一。
- [x] 补桌面与移动端截图测试。
- [x] 增加 UI-only Playwright 配置和请求拦截，确保默认不运行任何真实生成接口。
- [ ] 充值后再跑真实 S1-S5 生成链路和 Gate 交互闭环。

## 不立即处理的取舍

- 不在本轮重做视觉风格。Fortune Red 设计系统已经存在，当前主要债务是状态、响应式和可访问性一致性。
- 不在本轮重构 SceneSelector。它当前未被主页面引用，优先级低于活跃路径。
- 不在本轮改 admin 全站 i18n。Admin 面向平台管理员，当前更高优先级是可访问性与操作反馈。
