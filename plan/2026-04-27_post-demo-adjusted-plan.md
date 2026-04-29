# 路特创新视频创作平台 — 演示后调整执行计划

> 日期: 2026-04-27 (演示后)
> 调整原因: 演示反馈 — pipeline 可控性不足、视频太短、文案质量需提升、需尽快真实分发
> 核心原则: **整个 pipeline 必须可控，每个节点输出可查看、可编辑、可重跑**

---

## 一、演示反馈与问题诊断

### 反馈汇总

| # | 反馈 | 严重程度 | 根因 | 解决方向 |
|---|------|---------|------|---------|
| 1 | 视频生成质量好，但**太短** | 高 | S1 pipeline 硬编码 `duration: 5`，seedance 实际支持 10s | 前端加时长滑块，后端传参 |
| 2 | 担忧**前期文案质量** | 高 | strategy/script prompt 品牌调性约束弱，USP 未充分展开 | 优化 prompt，加入 tone_of_voice 强化 |
| 3 | pipeline **节点输出不可控** | 最高 | S1 串行一次性跑完 11 步，无中途介入 | 每步产物持久化 + 前端编辑重跑 |
| 4 | 希望**尽快真正发出去** | 高 | DistributionView 只展示，无真实发布 API | 提升分发连接器优先级 |

### 当前架构瓶颈

```
当前: 用户输入 → [一次性跑完11步] → 最终结果
         ↑ 无法介入              ↓ 只能看不能改

目标: 用户输入 → Step1 → [暂停/编辑/重跑] → Step2 → [暂停/编辑/重跑] → ... → 最终结果
                         ↑ 每步都可介入                  ↑ 每步都可介入
```

---

## 二、调整后执行计划（本周 + 下周）

### 核心新增：Pipeline 可控性架构（P0-新）

**设计原则：**
- 每个 step 的输出序列化为 `pipeline_state` JSON
- 用户可在任意 step 完成后**暂停**，查看/编辑/重跑
- 编辑后的状态持久化，不丢失
- 支持从任意 step **断点恢复**

**实现路径：**
1. 后端：S1 pipeline 拆分为可独立调用的 step API（`/scenario/s1/step/{step_name}`）
2. 后端：新增 `pipeline_state` 存储（先文件系统，后迁移 PG）
3. 前端：OneShotResultView 每个 tab 增加「编辑」+「重新生成」按钮
4. 前端：新增 Step-by-Step 模式切换（全自动 vs 逐步确认）

---

### 任务清单（按优先级排序）

#### P0-1: Pipeline 节点可控（新增最高优先级）

**目标：** 每个 step 产物可查看、可编辑、可重跑

**后端工作：**
- [ ] 新增 `POST /scenario/s1/step/{step}` API — 支持从任意 step 开始/重跑
- [ ] S1 pipeline 改造 — 每个 step 独立化，输入输出通过 `pipeline_state` 传递
- [ ] 新增 `PUT /scenario/s1/state/{label}` — 保存用户编辑后的中间状态
- [ ] 新增 `GET /scenario/s1/state/{label}` — 恢复断点继续执行
- [ ] `pipeline_state` 文件存储（ interim，等 PG 完成后迁移）

**前端工作：**
- [ ] OneShotResultView 每个 tab（briefs/scripts/videos/thumbnails/media）增加「编辑」按钮
- [ ] BriefsView → 可编辑 description、key_message、usp_priority
- [ ] ScriptsView → 可编辑 segment 的 voiceover、visual_description
- [ ] VideoPromptsView → 可编辑 prompt 文本，重新生成视频
- [ ] ThumbnailsView → 可编辑 style/concept，重新生成图片
- [ ] MediaView → 可重新生成单个 clip/audio/thumbnail
- [ ] 新增「逐步模式」切换开关：全自动跑完 vs 每步暂停确认

**预计时间：** 2-2.5 天

---

#### P0-2: 视频时长可调（快速修复）

**目标：** 用户可设定 5-10 秒视频时长，默认 10 秒

**后端：**
- [ ] S1 pipeline 接收 `video_duration` 参数，传给 seedance skill
- [ ] 当前硬编码 `"duration": 5` → `"duration": config.get("video_duration", 10)`

**前端：**
- [ ] SceneSelector 增加「视频时长」滑块：5s / 7s / 10s（默认 10s）
- [ ] 仅对 product_direct / live_shoot 场景显示

**预计时间：** 0.5 天

---

#### P0-3: 文案质量提升

**目标：** 强化品牌调性约束，USP 充分展开，文案更精准

**优化点：**
- [ ] `product_strategy.py` — prompt 中加入 `tone_of_voice` 深度约束
  - 当前 prompt 只有基础 scenario awareness，需增加：
  - "品牌人格: {archetype}"
  - "关键词: {keywords}"
  - "禁止使用的词汇/语调"
  - "必须出现的品牌主张"
- [ ] `script_writer.py` — 增加 USP 权重映射
  - P0 USP 必须在 hook 和前 3 秒出现
  - P1 USP 在 solution 段出现
  - P2 USP 在 CTA 前 reinforcement
- [ ] `brand_compliance.py` — 增加文案质量评分维度
  - 品牌关键词出现频率
  - USP 覆盖率
  - 调性一致性

**预计时间：** 1 天

---

#### P1-1: PG 持久化（支撑可控性的基础设施）

**目标：** 编辑后的中间状态不丢失，支持多人协作

**为什么优先级从 P0 降到 P1：**
- 可控性先用文件系统存储 `pipeline_state` 即可快速上线
- PG 持久化是"不丢失"的保障，但先用文件系统也能跑
- PG 完成后无缝迁移

**工作：**
- [ ] `src/storage/db.py` — asyncpg 连接池
- [ ] `src/storage/models.py` — SQL schema（threads, pipeline_states, brand_packages）
- [ ] `src/storage/repository.py` — Repository CRUD
- [ ] 改造 `src/api.py` — 替换内存 dict
- [ ] `pipeline_state` JSONB 存储，支持版本历史

**预计时间：** 3-4 天

---

#### P1-2: 真实分发连接器（优先级提升）

**目标：** 内容真正发到 TikTok / Shopify

**为什么从 P2 提升到 P1：**
- 演示中领导明确关注"尽快真正发出去"
- 有真实分发才能形成闭环，平台才有商业价值

**工作：**
- [ ] `src/connectors/tiktok_connector.py` — TikTok 发布 API
  - 需申请 TikTok for Business 开发者账号
  - 视频上传 + 标题/标签 + 发布
- [ ] `src/connectors/shopify_connector.py` — Shopify 商品视频/博客 API
  - 需 Shopify Partner 账号
  - 商品媒体上传 + 博客文章发布
- [ ] DistributionView 前端改造 — 增加「发布」按钮和状态追踪
- [ ] 发布状态持久化（等 PG 完成后）

**预计时间：** 3-5 天
**阻塞点：** 需 TikTok/Shopify 开发者账号申请和审核（1-3 工作日）

---

#### P2: 其余任务（按原顺序延后）

| 任务 | 原计划 | 新安排 | 原因 |
|------|--------|--------|------|
| R9b-1 网红管理 Web UI | P1 | P2 | 等 PG 完成后进行 |
| R9b-2 品牌资产包 Web UI | P1 | P2 | 等 PG 完成后进行 |
| R9a-4 可观测性 | P1 | P2 | 先保障核心功能 |
| R9c-1 认证与多租户 | P2 | P2 | 不变 |
| R9c-2 速率限制 | P2 | P2 | 不变 |
| R9c-3 前端生产优化 | P2 | P2 | 不变 |

---

## 三、本周具体排期（4月28日-5月2日）

| 日期 | 任务 | 交付物 | 验收标准 |
|------|------|--------|---------|
| **周一 4/28** | P0-2 视频时长 + P0-3 文案 prompt 优化 | 前端滑块 + 后端参数传递 + prompt v2 | S1 生成视频可设为 10s，文案中出现品牌关键词 |
| **周二 4/29** | P0-1 可控性：后端 step API + state 存储 | `/scenario/s1/step/{step}` API + pipeline_state 文件存储 | 可从 step 3 开始重跑，编辑后的 brief 能保存 |
| **周三 4/30** | P0-1 可控性：前端编辑重跑 | OneShotResultView 各 tab 增加编辑+重跑按钮 | 用户可修改脚本后重新生成视频 |
| **周四 5/1** | P0-1 可控性：逐步模式 + 整合测试 | 「全自动/逐步」切换 + E2E 测试 | 两种模式都能完整跑通 S1 |
| **周五 5/2** | P1-1 PG 持久化启动 | storage/ 目录 + DB schema 设计 | pipeline_state 可写入/读取 PG |

**五一假期后（5/6-5/9）：**
- P1-1 PG 持久化完成
- P1-2 分发连接器启动（需先申请开发者账号）

---

## 四、可控性架构详细设计

### State 结构

```json
{
  "label": "s1_1234567890",
  "scenario": "product_direct",
  "config": {
    "product_catalog": {...},
    "brand_guidelines": {...},
    "target_platforms": ["tiktok", "shopify"],
    "video_duration": 10
  },
  "steps": {
    "strategy": {
      "status": "done",
      "output": {"briefs": [...]},
      "edited": false,
      "started_at": "...",
      "completed_at": "..."
    },
    "scripts": {
      "status": "done",
      "output": {"scripts": [...]},
      "edited": true,
      "edited_output": {"scripts": [...]},
      "started_at": "..."
    },
    "storyboards": {"status": "pending", ...},
    "video_prompts": {"status": "pending", ...},
    "thumbnails": {"status": "pending", ...},
    "seedance_clips": {"status": "pending", ...},
    "tts_audio": {"status": "pending", ...},
    "thumbnail_images": {"status": "pending", ...},
    "final_video": {"status": "pending", ...},
    "audit": {"status": "pending", ...}
  },
  "current_step": "scripts",
  "mode": "step_by_step"
}
```

### API 设计

```
POST /scenario/s1/start        # 启动 pipeline，返回 label
POST /scenario/s1/step/{step}  # 执行指定 step（从 state 读取输入）
PUT  /scenario/s1/state/{label} # 更新 state（用户编辑后保存）
GET  /scenario/s1/state/{label} # 获取当前 state
POST /scenario/s1/resume       # 从 current_step 继续执行
POST /scenario/s1/regenerate   # 重跑指定 step（使用 edited_output 或原始输入）
```

### 前端交互流程

```
用户点击"开始生成"
  → 如果选择"逐步模式":
    → 执行 Step1 (strategy)
    → 展示 briefs，显示「编辑」+「下一步」按钮
    → 用户可编辑 brief → 点击「下一步」
    → 执行 Step2 (scripts) ...
  → 如果选择"全自动模式":
    → 串行执行所有 step（同当前行为）
    → 完成后展示所有结果
    → 用户可在各 tab 编辑并「重新生成」对应 step
```

---

## 五、风险提示

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Step 重跑时依赖前序 step 输出格式变化 | 中 | 高 | 严格定义每个 step 的输入输出 schema，变更时版本化 |
| 文件系统存储 `pipeline_state` 在并发时冲突 | 中 | 中 | 先用文件锁/UUID 隔离，PG 完成后解决 |
| Seedance 10s 视频生成时间更长 | 高 | 低 | 前端进度条时间需调整，用户体验仍可接受 |
| TikTok/Shopify 开发者账号审核慢 | 高 | 中 | 五一假期前提交申请，同时准备 mock 连接器做演示 |

---

## 六、文件变更预期

### 新建
```
src/pipeline/state_manager.py          # pipeline_state 读写管理
src/pipeline/step_runner.py            # 独立 step 执行器
web/src/components/EditableBrief.tsx   # 可编辑 brief 卡片
web/src/components/EditableScript.tsx  # 可编辑 script 卡片
web/src/components/StepByStepView.tsx  # 逐步模式 UI
```

### 修改
```
src/pipeline/s1_product_pipeline.py    # 拆分为可独立调用的 step
src/api.py                             # +step API + state API
src/skills/product_strategy.py         # prompt v2（品牌调性强化）
src/skills/script_writer.py            # prompt v2（USP 权重映射）
web/src/components/SceneSelector.tsx   # +视频时长滑块 + 模式切换
web/src/components/OneShotResultView.tsx # +编辑按钮 + 重跑逻辑
web/src/components/api.ts              # +step/regenerate API
```

---

*计划调整时间: 2026-04-27*
*下次评审: 周三 4/30 检查 P0-1 可控性进度*
