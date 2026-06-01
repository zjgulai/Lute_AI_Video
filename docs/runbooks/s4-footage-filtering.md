---
title: S4 Footage Filtering Contract
doc_type: workflow
module: frontend
topic: s4-footage-filtering
status: stable
created: 2026-06-01
updated: 2026-06-01
owner: self
source: human+ai
---

# S4 Footage Filtering Contract

## 触发场景

修改 `/works` 场景筛选、`/library` Materials tab、`/portfolio` 文件扫描、S4 输出文件命名或 `live_shoot` / `live_shoot_to_video` 场景别名时，先检查本契约。

## 影响范围

S4 实拍素材生成会同时产生成品视频和中间素材。成品应出现在 `/works` 的 Live Shoot 筛选下；中间素材应出现在 `/library` Materials tab。别名遗漏会让 S4 成品落入 `other`，用户点击 Live Shoot 后看不到作品。

## 预期 MTTR

2-5 min。大多数漂移可由前端 Vitest 或后端 portfolio contract test 直接定位。

## 当前契约

机器可读契约：`configs/s4-footage-filtering-contract.yaml`

行为规则：

- `/works` 只读取 `kind=final_work`，并把 `s4`、`live_shoot`、`live_shoot_to_video`、`s4_live_shoot` 统一归入 Live Shoot。
- `/works` 在缺少 `scenario` 字段时必须回退到文件名前缀判断，覆盖 `s4_*`、`live_shoot_*`、`live_shoot_to_video_*` 和 `s4_live_shoot_*`。
- `/library` Materials tab 只读取 `kind=creation_intermediate`，不得把 `renders` / `fast_mode` 成品混入素材库。
- 后端 `/portfolio` 必须保持 `renders` 视频为 `final_work`，`seedance`、`gpt_images`、`audio`、`keyframes` 等生成过程资产为 `creation_intermediate`。

## 相关代码

- [`web/src/app/works/page.tsx`](../../web/src/app/works/page.tsx) — `/works` 场景筛选和 fallback 推断。
- [`web/src/app/library/MaterialsTab.tsx`](../../web/src/app/library/MaterialsTab.tsx) — `/library` Materials tab 素材列表。
- [`src/routers/portfolio.py`](../../src/routers/portfolio.py) — portfolio `kind` 分层。
- [`web/src/app/works/works-page-filtering.test.tsx`](../../web/src/app/works/works-page-filtering.test.tsx) — Live Shoot 前端筛选回归。
- [`tests/test_portfolio_s4_filtering_contract.py`](../../tests/test_portfolio_s4_filtering_contract.py) — S4 final/intermediate 后端分层契约。

## 立即诊断

```bash
cd web
npm test -- --run src/app/works/works-page-filtering.test.tsx
```

```bash
.venv/bin/python -m pytest tests/test_portfolio_s4_filtering_contract.py -q
```

这些测试只使用 mocked portfolio response 或 pytest 临时目录文件，不访问生产，不触发 `/api/fast/*`、`/scenario/*` 真实生成、gate candidate、上传、发布或外部 provider。

## 分类响应

- Live Shoot 筛选后为空：检查 `SCENE_FILTER_BY_SCENARIO` 和 `SCENE_FILTER_BY_FILENAME_PREFIX` 是否覆盖全部 S4 alias。
- `/library` 出现成品视频：检查 `MaterialsTab` 是否仍请求 `kind=creation_intermediate`，以及 fallback 是否排除 `renders` / `fast_mode`。
- `/works` 缺少 S4 成品：检查 `/portfolio` 是否仍把 `renders/*.mp4` 标为 `final_work`。
- 中间素材缺失：检查 `/portfolio` 是否仍把 `seedance` / `gpt_images` / `audio` / `keyframes` 等标为 `creation_intermediate`。

## 永久 fix

1. 新增 S4 场景别名或输出命名时，同步更新机器契约和前端筛选测试。
2. 不用真实 POYO 生成验证筛选契约；mocked response 与临时文件足够覆盖分层风险。
3. `/works` 与 `/library` 的职责边界继续用 `kind` 表达，不回退到易漂移的 category 手工拼接。
