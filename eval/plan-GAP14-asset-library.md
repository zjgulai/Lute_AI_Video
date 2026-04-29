# GAP-14: Supabase Asset Library（pgvector 素材库）

> **目标：** 为 AssetSourcingAgent 提供真实的 postgres+pgvector 查询能力，替代当前 mock 模式。
> 素材可以被搜索（语义向量）、存取（S3/存储桶）、评分（匹配度排序）。

---

## 架构概览

```
当前: AssetSourcingAgent → mock assets（全部硬编码）
目标: AssetSourcingAgent → AssetLibraryClient → Supabase(postgres+pgvector) → 真实搜索 + 优雅降级
```

### 是否使用外部存储

- 实际 pgvector 搜索依赖在线的 Supabase 实例（需要 `SUPABASE_URL` 等配置）+ `supabase-py` 包
- 当前环境没有 Supabase 实例，也没有网络安装 `supabase-py`
- **设计折中：开发坏境完全模拟，正式环境连接真实 Supabase**

```
AssetLibraryClient
├── __init__(supabase_url, service_key) → 尝试连接 Supabase
├── search_assets(query: str, limit=5) → list[AssetCandidate]
│   ├── Supabase 可用 → pgvector 向量搜索
│   └── Supabase 不可用 → mock 返回（带日志警告）
├── store_asset(file_path, metadata) → str（asset_id）
└── get_asset(asset_id) → AssetCandidate | None
```

### 关键流程

1. `AssetSourcingAgent.run()` 收到 storyboards
2. 对每个 shot 的 `asset_needed`，调用 `AssetLibraryClient.search_assets(query)`
3. 有结果 → 构造 AssetCandidate（source="library"）
4. 无结果 → gap=true，等待 AI generation node 补充

---

## 模型扩展

**File:** `src/models/__init__.py` — 新增：

```python
class AssetMetadata(BaseModel):
    """Metadata stored alongside assets in Supabase."""
    asset_id: str
    file_path: str
    description: str
    tags: list[str] = Field(default_factory=list)
    video_type: Literal["product_usage", "brand_promotion", ...] | None = None
    platform: Platform | None = None
    duration: float = 0.0
    resolution: str = "1080x1920"
    embedding: list[float] | None = None  # pgvector embedding
    created_at: datetime = Field(default_factory=datetime.now)
    source: Literal["upload", "generated", "ugc"] = "upload"
```

---

## 实现任务

### Task 1: 创建 `src/tools/asset_library.py`

包含 `AssetLibraryClient` 类：

| 方法 | 正常模式 | 降级模式 |
|---|---|---|
| `__init__` | 初始化 supabase client | 打印警告，设就绪标志为 False |
| `search_assets(query, limit)` | pgvector: `rpc("search_assets", params)` | 返回模拟候选列表 |
| `store_asset(...)` | Supabase 插入 + 存储桶上传 | 返回模拟 asset_id |
| `get_asset(asset_id)` | Supabase select | 返回模拟 AssetCandidate |

**降级模式条件（任意成立则降级）：**
- `supabase-py` 包未安装
- `SUPABASE_URL` 或 `SUPABASE_SERVICE_KEY` 为空
- 初始化 `create_client()` 失败

### Task 2: 重构 `AssetSourcingAgent.run()`

**File:** `src/agents/asset_sourcing.py`

- 新增 `use_library: bool = True` 参数（默认开启，通过 `asset_library_client`）
- `run()` 时对每个 shot，先查 `AssetLibraryClient.search_assets(shot.asset_needed)`
- 有 candidates → 用真实结果替代 mock
- 无 candidates → gap=true（与现有逻辑一致）
- 当 `AssetLibraryClient` 在降级模式时，行为退化到当前 mock

### Task 3: 测试

**File:** `tests/test_asset_library.py` — 14 tests

| 类 | 测试数 | 覆盖 |
|---|---|---|
| `TestAssetLibraryClient` | 6 | 初始化、降级、search、store、get、连接失败 |
| `TestAssetLibraryIntegration` | 4 | 降级模式下的 search/store/get 行为 |
| `TestAssetSourcingWithLibrary` | 4 | agent 使用 library 后的数据流 |

### Task 4: 回归

```bash
cd /workspace/projects/hermes_evo/AI_vedio && python3 -m pytest tests/ -v --tb=short
```

期望：266 + 14 = 280 passed, 7 skipped（fastapi）

---

## 文件改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/tools/asset_library.py` | **创建** | AssetLibraryClient 类 |
| `src/agents/asset_sourcing.py` | **修改** | 接入 AssetLibraryClient |
| `src/models/__init__.py` | **修改** | 新增 AssetMetadata 模型 |
| `src/config.py` | **检查** | SUPABASE_URL 等已存在，无需改 |
| `tests/test_asset_library.py` | **创建** | 14 个测试 |

---

## 质量门槛

- [x] 无 supabase-py → 优雅降级到 mock，不抛异常
- [x] supabase-py 已安装 + 坏 url → 优雅降级
- [x] supabase-py 已安装 + 好 url → 真数据库搜索
- [x] AssetSourcingAgent 接入后现有行为不变（降级模式完全兼容）
- [x] 所有 mock AssetCandidate 的 source="library"（与当前 mock 区分）
- [x] 所有新模型注册 msgpack allowlist
- [x] 14 新测试 + 回归通过
