---
name: api-assets-pg-cutover-design-2026-05-15
description: 设计文档 — api_assets.py 内存字典迁移到 PG 持久化。当评估 brand_packages / influencers 重启数据丢失问题、设计 cutover 路径、加 PG-backed 资产 CRUD 时使用。当前状态：表已存在，repository 骨架已存在，cutover 未做。
doc_type: design
module: ai-video
topic: api-assets-pg-cutover
status: in-progress
created: 2026-05-15
updated: 2026-05-15
owner: Sisyphus
source: ai
related:
  - file: ../../.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md
    relation: implements-todo-16
---

# api_assets.py PG Cutover — 设计文档

> **状态**: in-progress. NEXT-STEPS-2026-05-11 P2-2 / UNIFIED-ROADMAP TODO-16。当前提交不做 cutover —— 仅落 repository test coverage + 文档化路径，避免在 Phase 0 部署稳定期改 prod 写入路径。

## 一、问题陈述

[src/api_assets.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/api_assets.py) 维护两个**内存字典**：

```python
_brand_packages: dict[str, BrandAssetPackage] = {}
_influencers: dict[str, InfluencerProfile] = {}
```

后果：
- backend 容器重启 → 所有 brand_package / influencer 数据丢失
- 多 worker 部署不可能（各 worker 持各自字典，互不通气）
- 当前生产单 worker 跑，重启=丢数据，但用户已经习惯了从前端重传

## 二、当前已就位的基础设施

意外发现 —— 工作量比预期小：

| 组件 | 状态 |
|---|---|
| PG 表 `brand_packages` | ✅ 已在 [src/storage/migrations/001_init.sql](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/migrations/001_init.sql):46-53 |
| PG 表 `influencers` | ✅ 已在 001_init.sql:56-64 |
| 生产 PG 实际存在 | ✅ Phase 0 部署时已通过 `\d` 验证 |
| [BrandPackageRepository](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/repository.py#L252) | ✅ 骨架已存在（空 subclass，继承 BaseRepository CRUD） |
| [InfluencerRepository](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/repository.py#L257) | ✅ 同上 |
| `BaseRepository` CRUD | ✅ create / get_by_id / get_by_field / update / delete / list_all 全实现 |

**结论**: 不需要新建表、不需要新建 alembic migration、不需要新写 repository。**只缺**：（1）测试覆盖 prove 骨架真的工作，（2）将 api_assets.py 的字典读写改为 repository 调用。

## 三、Cutover 计划（分 3 个 PR）

### PR 1（本 PR）— Repository 测试覆盖

新建 [tests/test_brand_influencer_repository.py](file:///Users/pray/project/hermes_evo/AI_vedio/tests/test_brand_influencer_repository.py)：
- 在 SQLite fallback 模式跑（PG 测试要 docker-compose，CI 慢；SQLite 同样覆盖逻辑）
- 7 case：
  1. create brand_package + get_by_id round-trip
  2. update brand_package brand_guidelines
  3. delete brand_package
  4. list_all brand_packages 返回顺序
  5. create influencer + get_by_id
  6. get_by_field influencer.platform
  7. influencer profile JSONB roundtrip

不动 api_assets.py。

### PR 2（跟进）— api_assets.py 改用 repository

```python
# Before:
_brand_packages: dict[str, BrandAssetPackage] = {}
_brand_packages[package.package_id] = package

# After:
_brand_repo = BrandPackageRepository()
await _brand_repo.create({
    "id": package.package_id,
    "name": package.brand_name,
    "brand_guidelines": package.dict(),
    "assets": package.assets or [],
})
```

注意：字段映射
- pydantic model `BrandAssetPackage.package_id` ↔ PG table `id`
- pydantic model `brand_name` ↔ PG table `name`
- 整个 model 序列化到 `brand_guidelines` JSONB（重命名为 `payload` 更准确，但表已存在，保持兼容）

风险：
- 现在内存字典 ID 是 `BPKG-XXXXXX` 格式（来自 uuid hex slice），PG `id` 列是 UUID type → 需要保持 string 或迁移 schema 到 TEXT
- 兼容方案：用 `get_by_field("name", brand_name)` 而不是 `get_by_id`，避开 UUID 冲突

### PR 3（跟进）— 数据迁移（生产已有数据）

生产环境 backend 重启过几次，所以内存字典本来就空，不需要迁移已有数据。但需要：
- 写 `scripts/migrate_brand_packages_to_pg.py` 用于读取任何遗留 JSON 文件备份（如果存在）
- 加 e2e 测试：重启 backend 后 brand_package 列表非空

## 四、为什么不在本会话做 cutover

1. **scope**: 本会话已做 8 个 TODO，多个涉及生产 deploy。再加 cutover 涉及 prod 写路径变更，超出"focused session"范围
2. **Phase 0 监控期**: cutover 后 24h 必须密切监控 brand_package CRUD 错误率。Phase 0 watchdog 当前监控的是 video pipeline 指标，没覆盖 asset CRUD
3. **decoupling**: 测试 + 文档先行确保骨架可信，cutover 可以下个 sprint 单独 1h 完成

## 五、验收标准

### PR 1（本 PR）

- 7/7 test_brand_influencer_repository.py 测试 PASS（SQLite 模式）
- ruff clean
- 不改 production code path（api_assets.py 不动）

### PR 2

- api_assets.py 4 个端点（create brand / list brand / create influencer / list influencer）走 repository
- 现有 test_asset_models.py 测试不退化
- 部署到 lighthouse 后重启 backend 验证：brand_package 列表持久化

### PR 3

- e2e 测试覆盖 backend restart → brand_package list 不为空

## 六、风险

| 风险 | 缓解 |
|---|---|
| **字段类型不匹配** (package_id 字符串 vs id UUID) | PR 2 用 get_by_field("name") 绕过；如真要迁移到 UUID 主键，用 alembic + casting migration |
| **PR 2 cutover bug 影响生产** | 部署前 staging 验证 + 用 feature flag `BRAND_PACKAGE_USE_PG=1` 渐进 |
| **测试不覆盖 PG-only 行为** (asyncpg vs sqlite3 SQL 方言) | 本 PR 测试默认 SQLite；后续可加 pytest-postgresql 跑 PG 测试 |

## 七、相关代码

- 内存字典：[src/api_assets.py:30-31](file:///Users/pray/project/hermes_evo/AI_vedio/src/api_assets.py#L30-L31)
- 表 schema：[src/storage/migrations/001_init.sql:46-64](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/migrations/001_init.sql#L46-L64)
- Repository 骨架：[src/storage/repository.py:252-260](file:///Users/pray/project/hermes_evo/AI_vedio/src/storage/repository.py#L252-L260)
- Pydantic models：[src/models/brand.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/models/brand.py) + [src/models/influencer.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/models/influencer.py)
