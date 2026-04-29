# Layer 5 商业化分发闭环 — 设计规格

> 状态：已设计，待审阅 | 版本：v1.0 | 日期：2026-04-30

---

## 一、目标与范围

### 1.1 目标

在现有 4 层（内容策略 → 叙事设计 → 生成控制 → 工作流工程）之上，构建第 5 层"商业化分发闭环"，实现：

- 将 AI 生成的视频**真实发布**到 TikTok 和 Shopify
- 定时从平台**拉取效果数据**（完播率、CTR、CVR、关注增量、销量）
- 在 Dashboard **可视化对比**视频效果，支持按场景/平台/时间维度分析
- 为未来的方案 C（数据飞轮自动回写策略）积累数据基础

### 1.2 范围

- **覆盖场景：** S1 商品直拍、S2 品牌宣传、S3 网红二创（三个场景统一）
- **覆盖平台：** TikTok（Business API）+ Shopify（Admin API）
- **核心指标：** 完播率、CTR、CVR、关注增量、销量
- **不做：** 自动策略回写（方案 C）、多市场本地化（NA/EU 分化）、A/B 测试调度

### 1.3 不做的事情（防蔓延）

- 不修改现有 pipeline 步骤、skill、场景逻辑
- 不改变前端 Stage 0-3 的任何页面
- 不增加新的数据库迁移流程（在现有 PostgreSQL/SQLite 架构上扩展）
- 不做 Google Ads、Meta Ads、Amazon 等其他平台的发布

---

## 二、架构概览

```
┌──────────────────────────────────────────────────────┐
│                  现有管线 (Layer 1-4)                  │
│  strategy → scripts → ... → assemble → audit         │
│                         │                             │
│                    final_video.mp4                    │
│                    + metadata (script, USPs)           │
└─────────────────────────┬────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│  Layer 5 — 商业化分发闭环                              │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ Publish   │   │  Metrics  │   │Dashboard │         │
│  │ Engine    │   │  Poller   │   │ (前端)   │         │
│  │           │   │  (定时)   │   │          │         │
│  └─────┬─────┘   └─────┬─────┘   └────┬─────┘         │
│        │               │               │              │
│   ┌────▼────┐     ┌────▼────┐     ┌───▼────┐         │
│   │TikTok   │     │video_   │     │ 效果   │         │
│   │Shopify  │     │metrics  │     │ 看板   │         │
│   │API      │     │ table   │     │ 3视图  │         │
│   └─────────┘     └─────────┘     └────────┘         │
└──────────────────────────────────────────────────────┘
```

**约束：** Layer 5 完全在现有架构之外。不修改任何 pipeline 步骤、skill、场景逻辑。只在管线输出端和 API 层追加新能力。

---

## 三、数据模型

### 3.1 video_metrics 表

每一行是**一个视频在某个时间点在一平台的快照**。同一视频多次拉取产生多行，支持趋势展示。

```sql
CREATE TABLE video_metrics (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        TEXT NOT NULL,          -- pipeline 产出的视频标识
    scenario        TEXT NOT NULL,          -- S1/S2/S3
    platform        TEXT NOT NULL,          -- tiktok / shopify
    post_id         TEXT,                   -- 平台侧帖子 ID
    post_url        TEXT,                   -- 可直接打开的链接
    metrics         JSONB NOT NULL DEFAULT '{}',  -- 指标快照
    pulled_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMP,              -- 首次发布时间
    
    -- 索引
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 查询优化
CREATE INDEX idx_vm_video_id ON video_metrics(video_id);
CREATE INDEX idx_vm_scenario ON video_metrics(scenario);
CREATE INDEX idx_vm_platform ON video_metrics(platform);
CREATE INDEX idx_vm_pulled_at ON video_metrics(pulled_at);
```

### 3.2 metrics JSONB 结构

```json
{
  "watch_rate": 0.72,      // 完播率 (0-1)
  "ctr": 0.042,            // 点击率
  "cvr": 0.028,            // 转化率
  "followers_gained": 15,  // 关注增量
  "sales": 3,              // 销量
  "likes": 124,            // 点赞
  "comments": 8,           // 评论
  "shares": 22,            // 分享
  "views": 4520,           // 播放量
  "watch_time_avg": 18.2   // 平均观看时长 (秒)
}
```

**设计决策：** JSONB 而非固定列，因为不同平台的可用指标不同（TikTok 有完播率但 Shopify 没有，Shopify 有销量但 TikTok 没有）。JSONB 让后续扩展不加列。

---

## 四、后端组件

### 4.1 Publish Engine — `src/connectors/publish_engine.py`

```python
class PublishEngine:
    """发布引擎：将视频发布到目标平台"""
    
    async def publish(video_path, metadata, platforms) -> list[PublishResult]:
        """发布单条视频到多个平台，返回每个平台的发布结果"""
        ...
    
    async def publish_to_tiktok(video_path, metadata) -> PublishResult:
        """发布到 TikTok"""
        ...
    
    async def publish_to_shopify(video_path, metadata) -> PublishResult:
        """发布到 Shopify"""
        ...
```

**TikTok 发布流程：**
1. 调用 TikTok Content Posting API，上传视频文件
2. 设置标题（从 metadata 中提取脚本的 hook 文本）
3. 设置话题标签（从 metadata 中提取 hashtags）
4. 返回 post_id 和 post_url

**Shopify 发布流程：**
1. 上传视频到 Shopify Files API
2. 将视频关联到对应产品（从 metadata 中提取 product_name 匹配 Shopify 产品）
3. 返回 product_media_id 和 admin_url

**与现有代码的关系：**
- 替换 `src/connectors/tiktok_connector.py` 和 `src/connectors/shopify_connector.py` 的 mock 实现
- 新增 `src/connectors/publish_engine.py` 作为统一发布入口
- 保持 `src/connectors/registry.py` 的连接器注册模式

### 4.2 Metrics Poller — `src/tasks/metrics_poller.py`

```python
class MetricsPoller:
    """定时拉取平台效果数据"""
    
    def __init__(self):
        self.repo = MetricsRepository()
    
    async def pull_all(self):
        """拉取所有已发布且未过期的视频"""
        active_posts = await self.repo.get_active_posts()
        for post in active_posts:
            await self.pull_single(post)
    
    async def pull_single(self, post):
        """拉取单条视频的最新指标并存储"""
        metrics = await self._fetch_from_platform(post.platform, post.post_id)
        await self.repo.save_metrics(post.video_id, post.scenario, 
                                       post.platform, post.post_id, 
                                       post.post_url, metrics)
    
    async def _fetch_from_tiktok(self, post_id):
        """TikTok Insights API"""
        ...
    
    async def _fetch_from_shopify(self, post_id):
        """Shopify Analytics API"""
        ...
```

**定时策略：**
- 发布后 0-24h：每 2 小时拉一次（快速反馈）
- 发布后 24-72h：每 6 小时拉一次（稳定期）
- 发布后 3d+：每 12 小时拉一次（长尾）
- 发布后 30d+：停止拉取

实现方式：FastAPI 的 `BackgroundTasks` 或独立的 `asyncio.create_task`。不引入 Celery 等重型调度库——MVP 阶段用简单的定时任务循环。

### 4.3 API 端点

新增 4 个端点（追加到 `src/api.py` 或独立路由）：

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/publish/{video_id}` | 发布视频到指定平台 |
| `GET` | `/metrics/{video_id}` | 获取单条视频的效果数据 |
| `GET` | `/dashboard/overview` | 获取 Dashboard 聚合数据 |
| `POST` | `/metrics/pull` | 手动触发拉取（调试用） |

### 4.4 存储层

- `src/storage/metrics_repository.py` — 新增（当前已有 schema 定义但未实现 CRUD）
- 复用现有的 `PipelineStateManager` 的 dual-write 模式（PG + SQLite）

---

## 五、前端组件

### 5.1 PerformanceDashboard — `web/src/components/PerformanceDashboard.tsx`

三个视图切换，替换现有的 `DistributionView.tsx`。

**视图 1：视频效果列表（默认）**
- 展示所有已发布视频的行级指标
- 筛选器：场景（S1/S2/S3）、平台（TikTok/Shopify）、时间范围
- 每行可展开查看历史趋势折线图
- CTR > 4% 绿色高亮，< 2% 红色提示

**视图 2：场景聚合**
- 三个卡片，每个场景的平均完播/CTR/CVR
- 点击卡片进入该场景下的视频列表

**视图 3：平台对比**
- TikTok vs Shopify 并排指标
- 按场景分组展示各平台效果差异

### 5.2 PublishPanel — `web/src/components/PublishPanel.tsx`

发布操作的 UI：
- 选择已完成视频 → 选择平台（支持多选）→ 编辑标题和描述 → 确认发布
- 发布中展示进度（上传中 / 处理中 / 已发布）
- 发布完成后展示 post_url

### 5.3 集成点

- `PerformanceDashboard` 作为 Stage 3 的一个新 tab（与 Briefs/Scripts/Videos/Quality 并列）
- `PublishPanel` 嵌入 `OneShotResultView` 的 Media tab 中
- 导航栏不变，独立入口在 Stage 3 结果页中

---

## 六、数据流

### 6.1 发布流

```
用户操作             后端               外部平台
─────────          ──────             ─────────
选择视频+平台  →  验证视频存在
                 检查 API key      →  TikTok Auth
                 上传视频文件      →  TikTok Content API
                 设置标题/标签
                 记录 post_id
                 返回 post_url
用户看到"已发布"
```

### 6.2 拉取流

```
定时触发           后端               外部平台
─────────         ──────             ─────────
每 6h 唤醒    →  查询活跃 posts    →  TikTok Insights API
                 逐条拉取 metrics   →  Shopify Analytics API
                 写入 video_metrics
                 更新 pulled_at
Dashboard 刷新时读取最新数据
```

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 无真实 TikTok/Shopify API 密钥 | 高 | 发布阻塞 | 保留 mock 模式；API key 缺失时显示"需要配置 API Key"引导 |
| TikTok API 政策变化 | 中 | 拉取失败 | 拉取失败不影响已发布视频；标记 `pulled_error` 并跳过 |
| Shopify 产品匹配失败 | 中 | 视频发布了但未关联产品 | 发布前增加产品搜索确认步骤 |
| 拉取频率过高触发限流 | 低 | 暂时无法获取新数据 | 指数退避重试 |
| 视频文件过大 | 低 | 上传超时 | 前端预检文件大小；超过限制提示压缩 |

---

## 八、验收标准

1. 用户可发布 S1 视频到 TikTok，获得真实 post URL
2. 用户可发布 S1 视频到 Shopify，视频出现在对应产品页
3. Dashboard 可展示发布后 24h 内的完播率和 CTR 数据
4. Dashboard 可按 S1/S2/S3 场景聚合指标
5. 发布/拉取失败时，用户收到可操作的错误信息（非 500）
6. mock 模式仍可用（未配置真实 API key 时）

---

## 九、不做的事情（方案 C 路线图）

以下能力不在本规格范围内，但设计留有扩展点：

- 效果数据自动回写 strategy prompt（方案 C）
- 多市场本地化内容（NA/EU 模板分化）
- 钩子类型 / pain_point / 人群的跨视频归因分析
- Google Ads、Meta Ads、Amazon 平台接入
- 自动 A/B 测试调度
- 不同内容类型（带货/品牌/知识IP）的独立 KPI 体系

---

*设计规格：v1.0 | 待审阅 | 下一步：writing-plans*
