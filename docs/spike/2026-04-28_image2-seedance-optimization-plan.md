# Image2 + Seedance 2.0 深度优化计划

## 网红二创视频质量保障架构

---

## 一、先承认硬边界

在展开计划之前，有几件事必须说清楚。这不是泼冷水，而是定义"能解决"和"不能完全解决"的边界线。

**Seedance 对图片参考的遵循度远不如对文本提示词的遵循度。** Image2 的关键帧是**建议性锚点**，不是**确定性模板**。Seedance 可能修改角度、光照、面部细节，甚至可能忽略参考图转而更遵循文本提示词。这意味着"先定图后生视频"能把 "10 抽 1 中" 降到 "3 抽 1 中"，但不能降到 "1 抽 1 中"。如果要零容忍，需要在体系里加一层自动质量检测 + 自动重试 + 人工审核的闭合回路。

**gpt-image-2 没有 "character identity" 概念。** 你给它两次 prompt "a Chinese female influencer, 28, warm smile, medium build"，它产出的是两个"像"的人，不是同一个人的两张图。跨镜头的人物一致性不靠 prompt 解决，要靠外部的 identity card 机制。

**真人二创的核心矛盾：** 观众认识原视频里的网红。观众知道她长什么样、笑什么弧度、手怎么动。任何 AI 生成的人脸都会跟观众的记忆对比，哪怕偏差 5%，观众都能感知到"假"。这是心理学问题，不是纯技术问题。

---

## 二、核心架构决策：混合管线而非纯合成管线

传统 S3 管线的隐性假设是："下载原视频 → 分析结构 → AI 重新生成所有内容"。这条路径在人物一致性上注定失败。

改为**三通道混合管线**：

```
原视频输入
    │
    ├── 通道A【保留层】→ 直接保留原视频的 talking-head 片段（网红对镜头说话）
    │       条件：画面中网红脸部占比 > 30%
    │
    ├── 通道B【替换层】→ 保留网红画面，用 AI 替换手中的产品
    │       条件：画面中产品占比 > 20%，网红手部可见
    │       技术：inpainting / product-swap overlay
    │
    └── 通道C【生成层】→ 完全 AI 生成（产品特写、B-roll、转场）
            条件：无网红脸部、纯产品/场景/文字
            技术：Image2 关键帧 + Seedance 视频 → 本期重点
```

**这条决策基于一个简单逻辑：** 网红的脸 = 整个视频的信任锚点。你不需要完美生成她的脸，你只需要**不在她脸上动刀**。保留她真实的脸，观众就信了 70%。剩下 30% 的产品替换和 B-roll 用 AI 完美处理。

---

## 三、通道C 的深层设计：Image2 → Seedance 全链路

这是本文的核心——当必须 AI 生成视频片段时，如何做到人物一致性、动作流畅性、镜头连续性。

### 3.1 人物身份卡 Character Identity Card

**问题：** 跨多个 Shot 生成 AI 内容时，人物长相不一致。

**方案：** 新增一个 `character_identity` 步骤，插在 `video_analysis` 和 `storyboard` 之间。

**输入：** 原视频中最佳人脸帧（面部清晰、正面、光照好、无遮挡）。

自动筛选逻辑：
```
1. 每秒提取 3 帧
2. 人脸检测（MediaPipe/face-api.js）
3. 人脸质量评分：
   - 清晰度（Laplacian variance ≥ 500）
   - 正面度（yaw/pitch/roll 角度 ≤ 15°）
   - 光照均匀度（直方图均衡性）
   - 表情自然度（非眨眼、非说话嘴型）
4. 选 Top 3 帧作为 identity card
5. 用 CLIP 嵌入向量存储身份特征
```

**输出：** `identity_card` 对象，包含：
```json
{
  "reference_frames": ["path/to/face_1.jpg", "path/to/face_2.jpg", "path/to/face_3.jpg"],
  "face_embedding": [0.123, -0.456, ...],
  "attributes": {
    "skin_tone": "#E8C9A0",
    "face_shape": "oval",
    "hair_style": "long straight dark brown",
    "body_build": "medium",
    "typical_clothing": "casual white blouse"
  }
}
```

这个 identity card 被**所有后续生成步骤共享**。无论生成 Shot 1、Shot 2 还是 Shot 3，都从同一张 card 出发。

### 3.2 关键帧生成 Keyframe Generation

**问题：** Image2 每次独立生成，人物外观不一致。

**方案：** 新增 `keyframe_images` 步骤，插在 `storyboard` 和 `video_prompts` 之间。12 步 pipeline 变为 13 步。

**关键帧生成策略——三张图锁定一致性：**

对于每个 Shot N，不是只生成一张关键帧，而是：

```
Shot N 的关键帧包 = {
  "character_frame":  // 人物参考帧 — 来自 identity card，始终复用同一组人脸图
  "product_frame":    // 产品参考帧 — 来自产品图库，展示正确角度
  "composition_frame" // 构图参考帧 — 本镜头新生成，融合人物+产品+场景
}
```

**构图参考帧的 prompt 构建逻辑：**

```
A {identity_card.attributes.body_build} woman with {identity_card.attributes.face_shape} face,
{identity_card.attributes.hair_style}, wearing {identity_card.attributes.typical_clothing},
holding {product_name} in her hands, demonstrating {shot.visual_description},
{shot.shot_type} shot, {shot.camera_movement},
warm natural lighting, lifestyle setting, authentic expression.
Reference person: attached face images.
Reference product: attached product image.
```

**调用链：**
```
gpt-image-2(composition_prompt, reference_images=[
    identity_card.reference_frames[0],  // 附加人物参考
    product_reference_image,             // 附加产品参考
])
```

**效果：** Image2 有了三重锚定——人物长相、产品外观、场景构图。三个锚点协作，大幅缩小 AI 的自由发挥空间。

**关键帧数量：** 每个 Shot 生成 3-5 个候选关键帧，由质量评分系统自动选最优一帧。如果最优帧仍然不达标（面部相似度低于阈值），进入 retry 循环。

### 3.3 跨镜头连续性链 Continuity Chain

**问题：** Shot 1 的关键帧和 Shot 2 的关键帧之间没有关联，导致视觉跳跃。

**方案：** 引入"前镜头末帧 → 后镜头首帧"的传递链。

```
Shot 1: Image2 生成关键帧 → Seedance 生成视频 → 提取末帧 → 
    ↓
Shot 2: 末帧作为 additional_reference → Image2 生成关键帧（受 Shot 1 末帧约束）→ 
    ↓
    Seedance 生成视频 → 提取末帧 →
    ↓
Shot 3: 末帧作为 additional_reference → ...
```

**修改 video_prompts 步骤：** 同时注入 `@image1`（首帧关键帧）和隐式的末帧约束：

```
@image1 Starting frame: {keyframe_for_this_shot}
Previous shot ends with: {last_frame_of_previous_shot_description}
Continue smoothly from previous shot's ending position.
{shot.visual_description}
Camera: {shot.camera_movement}, {shot.shot_type}
Duration: {shot.duration}s
```

`@image1` 硬锚定首帧，文本描述软约束末帧衔接点。Seedance 会尝试让视频的起始帧贴近 @image1，同时让内容的终态朝文本描述的方向走。

### 3.4 产品一致性产品定位 Product Anchor

**问题：** 产品在 AI 生成中变形、颜色错误、角度不自然。

**方案：** 为每个产品维护一组"产品锚定图"：

```
product_anchor_pack = {
    "front_angle": "product_front.png",
    "45_degree_angle": "product_45deg.png",
    "side_angle": "product_side.png",
    "top_down_angle": "product_top.png",
    "in_hand_reference": "product_in_hand.jpg"
}
```

当 storyboard 指定了 shot_type 和 camera angle 时，自动选择最接近角度的产品锚定图作为 Image2 的参考输入。

**产品锚定图的来源：**
- 品牌方上传（品牌资产包）
- 从原视频中自动抠图提取（如果原视频中有清晰的产品展示）
- gpt-image-2 根据产品名称生成后再人工确认

### 3.5 质量门控系统 Quality Gate

**问题：** 怎么知道生成结果是否可接受？不能靠人眼逐条判断。

**方案：** 在每个生成步骤后插入自动质量检测，不达标自动 retry。

**检测维度：**

| 检测项 | 方法 | 阈值 | Retry 策略 |
|--------|------|------|-----------|
| 人脸一致性 | CLIP embedding 余弦相似度 vs identity card | ≥ 0.85 | 重新生成关键帧 |
| 人脸清晰度 | Laplacian variance | ≥ 500 | 重新生成关键帧 |
| 产品形态一致性 | 边缘检测 + 原图模板比对 | 边缘偏差 ≤ 15% | 重新生成关键帧 |
| 服装一致性 | 衣服区域颜色直方图 vs identity card | 色差 ΔE ≤ 10 | 重新生成关键帧 |
| 帧间流畅度 | 光流分析（optical flow magnitude） | 标准差 ≤ 均值 × 1.5 | 重新生成该片段 |
| 视频时长 | ffprobe 检测 | ≥ 期望时长的 75% | 重新生成该片段 |
| 总体人脸存在 | 人脸检测确认 | 至少 1 张人脸 | 重新生成 |

**Retry 上限：** 每步骤最多 5 次。5 次后仍然不达标，输出 warning 并降级到以下策略：
- 人脸质量不达标 → 改用库存素材或文字卡片代替该 shot
- 产品形态不达标 → 使用原始产品图片做静态插入
- 帧间不流畅 → 在两 shot 间插入 fade 转场掩盖

---

## 四、通道B 的补充设计：产品替换 Product Swapping

通道B 解决的是"保留网红画面，只替换手中的产品"——最高性价比的方案，因为它完全绕开了人脸生成问题。

**技术路径：**

1. **原视频产品区域检测：** 用 Grounding DINO 或 SAM 检测原视频中网红手持产品的区域
2. **产品掩码提取：** 逐帧提取产品 mask
3. **目标产品叠加：** 将目标产品的对应角度图片贴合到 mask 区域
4. **边缘融合：** 用泊松混合（Poisson blending）消除硬边
5. **光照适配：** 调整产品图片的色温、亮度匹配原视频场景

通道B 处理手部产品替换，通道C 处理没有原画面的 B-roll 和产品特写，两者互补。

---

## 五、完整管线架构（13 步）

```
原视频输入
    │
    ├─ [1] video_analysis ──── 分析原视频结构、hook、segments
    ├─ [2] character_identity ─ NEW — 提取人物身份卡
    ├─ [3] scene_decomposition ─ NEW — 判断每个 segment 走通道 A/B/C
    ├─ [4] remix_script ────── 改写脚本（保留风格，替换产品）
    │
    ├── 通道A（保留层）── 直接输出原片段路径
    ├── 通道B（替换层）── 
    │       ├─ [5b] product_detect ── 检测产品区域
    │       └─ [6b] product_swap ──── 替换产品
    │
    ├── 通道C（生成层）── 
    │       ├─ [5c] storyboard ───── 分镜规划
    │       ├─ [6c] keyframe_images ─ NEW — 生成关键帧包
    │       │       ├─ quality_gate: 人脸 → CLIP 相似度 ≥ 0.85
    │       │       └─ quality_gate: 产品 → 边缘偏差 ≤ 15%
    │       ├─ [7c] video_prompts ─── 生成 Seedance 提示词（注入首帧+末帧约束）
    │       ├─ [8c] seedance_clips ── image_to_video 生成视频片段
    │       │       └─ quality_gate: 流畅度 → optical flow 检测
    │       └─ [9c] thumbnail_prompts + thumbnail_images
    │
    ├─ [10] tts_audio ──────── 语音合成
    ├─ [11] assemble_final ─── 合成（通道A原片段 + 通道B替换片段 + 通道C生成片段）
    └─ [12] audit ──────────── 全链路质量审计
```

---

## 六、实施路线图

### Sprint A（本周，2-3 天）：Image2 单锚点验证

**目标：** 验证"先定图后生视频"在真实场景中是否有效。

**任务：**
1. 新增 `character_identity` step（仅提取、不联动）
2. 新增 `keyframe_images` step（用 storyboard 的 visual_description 生成关键帧）
3. 修改 `_step_seedance_clips` 读取 keyframe path，传入 `image_to_video`
4. 跑通 S1（孕妇枕）+ S3（一条网红视频）各一条，对比有无 Image2 锚定的质量差异
5. 输出 `docs/spike/image2-seedance-comparison.md`（并排对比截图）

**验收：** 有 Image2 锚定的 clip 在人物/产品稳定性上明显优于纯 text_to_video

### Sprint B（下周，3-4 天）：全链路集成 + 连续性链

**目标：** 把单锚点扩展为全链路 continuity chain。

**任务：**
1. 实现末帧提取（从 Seedance 生成的 mp4 提取最后一帧）
2. 实现 continuity chain（Shot N 末帧 → Shot N+1 首帧约束）
3. 添加产品锚定图自动匹配
4. 添加 quality_gate 基础版（人脸 CLIP 相似度 + 产品边缘检测）
5. 实现 retry 循环（最多 5 次）

**验收：** 3-shot 视频的跨镜头人物一致性显著提升，产品形态稳定

### Sprint C（第三周，2-3 天）：通道B 产品替换

**目标：** 实现产品区域检测和替换，构成完整混合管线。

**任务：**
1. 实现 product_detect skill（SAM 分割）
2. 实现 product_swap skill（泊松融合）
3. 实现 scene_decomposition skill（A/B/C 通道分流）

**验收：** 一条网红原视频，产品被无缝替换为目标产品，人脸原封不动

### Sprint D（第四周，2 天）：质量闭环 + 降级策略

**目标：** 全链路 quality gate 上线，不达标的自动降级。

**任务：**
1. 完善 quality_gate 全部 7 项检测
2. 实现降级策略（库存素材、静态卡片、fade 转场）
3. 端到端跑 5 条真实网红视频，统计通过率和失败模式

**验收：** 5 条视频中 ≥ 4 条通过全部 quality gate，失败的有明确的降级输出

---

## 七、成本估算

| 资源 | 单条视频成本 | 说明 |
|------|-------------|------|
| 原视频下载 | $0 | YouTube/小红书/抖音下载 |
| video_analysis | ~$0.005 | LLM 分析（短文本） |
| character_identity | ~$0.02 | 人脸检测 + CLIP embedding |
| keyframe_images | ~$0.16 | 3 shots × 2 attempts × gpt-image-2 |
| seedance_clips | poyo 代理价 | 3 shots × 2 attempts |
| quality_gate | ~$0.01 | 图像检测 API |
| tts_audio | ~$0.11 | ElevenLabs（如有 key） |
| assemble_final | ~$0.05 | Remotion 渲染计算 |
| **单条总成本** | **~$0.50-1.00 不含 Seedance** | Seedance 价格取决于 poyo 代理 |

重试策略会使成本浮动：如果第一轮全部通过，成本 ≈ $0.50；如果 3 个 shot 各需 retry 2 次，成本 ≈ $1.50。

---

## 八、风险的诚实评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Seedance 忽略 Image2 参考图 | 中 | 人物不一致 | 增加 retry 次数，降级到通道B |
| gpt-image-2 跨 shot 面孔不一致 | 中 | 人物跳跃 | identity card CLIP 约束 + retry |
| 原视频人脸质量差（低分辨率、侧脸） | 高 | identity card 失效 | 降级到"不生成人脸内容"策略 |
| Seedance 视频动作不流畅 | 低（HTTP/1.1 修复后） | 片段报废 | optical flow 检测 + retry |
| 成本超出预期 | 中 | 预算压力 | 设置日生成上限，优先通道B |
| poyo.ai 服务不稳定 | 中 | 阻塞生成 | HTTP/1.1 + timeout + retry 已修复 |

---

## 九、核心总结

Image2 + Seedance 可以解决 60% 的问题：
- 产品形态稳定性 → 大幅改善
- 单镜头内人物/场景一致性 → 显著改善
- 生成随机性 → 从"10 抽 1"变"3 抽 1"

但还有 40% 必须靠架构设计解决：
- 跨镜头人物一致性 → 需要 identity card + continuity chain
- 网红真实感 → AI 无法完美复制真人，必须靠通道A（保留原画面）
- 极端姿势/手部动作 → 靠 quality gate 检测 + retry + 降级

**最关键的一句话：对于网红二创场景，"保留原画面中网红的脸"比"生成一个像网红的脸"重要十倍。** 混合管线的通道A（保留层）是整个方案的投资回报率最高的部分——零成本、零风险、100%真实。把 Image2+Seedance 的火力集中在通道C 的产品特写和 B-roll 上，不要在网红脸上赌 AI 的随机性。

---

## 十、附录：当前代码能力与缺口对照

### 已具备的能力

| 组件 | 文件 | 状态 |
|------|------|------|
| Seedance client (image_to_video) | `src/tools/seedance_client.py` | 就绪，支持 @image1/@image2 |
| GPT-Image 生成 | `src/skills/gpt_image_generate.py` | 就绪，已有 self-verification |
| Storyboard 分镜 | `src/skills/storyboard.py` | 就绪，输出结构化 shot 描述 |
| Pipeline 回退链 | `src/pipeline/s1_product_pipeline.py` | 就绪，11 步全部有 fallback |
| SkillRegistry | `src/skills/registry.py` | 就绪，支持动态注册 |
| Remotion 渲染 | `src/skills/remotion_assemble.py` | 就绪，有 ffmpeg fallback |
| TTS 语音合成 | `src/skills/elevenlabs_tts.py` | 就绪，有 silent MP3 fallback |
| PostgreSQL 持久化 | `src/storage/db.py` | 就绪，dual-write + SQLite fallback |

### 需新增的能力

| 组件 | 优先级 | 所属 Sprint | 说明 |
|------|--------|------------|------|
| character_identity | P0 | A | 人脸检测 + CLIP embedding |
| keyframe_images | P0 | A | GPT-Image 关键帧生成 |
| continuity_chain | P1 | B | 末帧提取 + 传递 |
| product_anchor_pack | P1 | B | 产品多角度锚定图 |
| quality_gate | P1 | B | 7 项自动检测 |
| scene_decomposition | P2 | C | A/B/C 通道分流 |
| product_detect | P2 | C | SAM 分割 + 掩码提取 |
| product_swap | P2 | C | 泊松混合替换 |
| degrade_strategy | P3 | D | 自动降级策略 |
