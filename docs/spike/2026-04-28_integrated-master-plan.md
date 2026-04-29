# AI 视频创作平台 — 整合总计划

> 版本：v1.0 | 日期：2026-04-28
> 整合范围：战略全景规划 (Apr 26) + 多场景路线图 (Apr 26) + 演示后调整计划 (Apr 27-28) + Image2+Seedance 质量优化计划 (Apr 28)
> 原则：场景架构一致、时间压缩并行、多智能体协作

---

## 一、四份文档的一致性整合

### 1.1 场景架构 — 统一设计

四份文档对场景的定义收敛到以下共识：

```
┌─────────────────────────────────────────────────────────────┐
│                    两大核心路径                               │
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │ 原创路径 Original    │    │ 二创路径 Remix               │ │
│  │ (S1∪S2)             │    │ (S3)                        │ │
│  │                     │    │                             │ │
│  │ S1: 商品直拍         │    │ 原视频下载 → 结构分析        │ │
│  │   有产品没素材       │    │   → 人物身份卡提取          │ │
│  │   → AI全生成         │    │   → A/B/C通道分流           │ │
│  │                     │    │   → 质量门控                 │ │
│  │ S2: 品牌宣传         │    │   → 混合合成                 │ │
│  │   brand_mode=S2     │    │                             │ │
│  │   审计严格/多语      │    │                             │ │
│  └────────┬────────────┘    └──────────┬──────────────────┘ │
│           │                            │                    │
│           └──────────┬─────────────────┘                    │
│                      ↓                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              共享 Skill 层 (SkillRegistry)           │   │
│  │  storyboard | seedance_prompt | video_prompts       │   │
│  │  tts_audio | thumbnail_images | assemble_final      │   │
│  │  character_identity | keyframe_images | quality_gate│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  S4 (live_shoot_to_video): 暂缓，等 S1+S3 生产级后评估       │
└─────────────────────────────────────────────────────────────┘
```

**与各文档的对照：**

| 文档 | 原始场景设计 | 整合后 | 一致性 |
|------|-------------|--------|--------|
| 战略全景 (Apr 26) | 两条核心路径(原创+二创)，S4暂缓 | 完全一致 | ✅ |
| 多场景路线图 (Apr 26) | 4场景 S1-S4 | S1+S2合并，S4暂缓 | ✅ 已收敛 |
| 演示后调整 (Apr 27) | S1作为核心验证场景 | S1优先跑通 | ✅ |
| Image2+Seedance (Apr 28) | S1 Channel C + S3 A/B/C | 完全嵌合 | ✅ |

### 1.2 质量层与管线层的关系

**管线层（已有）** — 定义"做什么"：11步 pipeline，从 brief 到 assembled mp4
**质量层（新增）** — 定义"怎么做好"：Image2 锚定 + continuity chain + quality gate

质量层**不是新管线**，而是**嵌入现有管线步骤之间的 quality enforcement 节点**：

```
现有: ... storyboard → video_prompts → seedance_clips → ...
                                                          ↑
新增: ... storyboard → keyframe_images → video_prompts(含continuity) 
                         ↓                    ↓
                    quality_gate         seedance_clips(image_to_video)
                                              ↓
                                         quality_gate
```

### 1.3 时间线整合 — 压缩后的4周路线

| 原计划 | 当前进度 | 整合后 |
|--------|----------|--------|
| Sprint 0 (Apr 27-May 3): 决策+spike | Phase 1-2 已完成 ✅ | Week 1 加速完成 Phase 3 收尾 + 启动质量层Sprint A |
| Sprint 1 (May 4-10): 基建拉直 | 未开始 | Week 1-2: 基建并行（Remotion/TTS/缩略图真实化） |
| Sprint 2-3 (May 11-24): S3生产级 | 未开始 | Week 2-3: 质量层 Sprint B-C + S3混合管线 |
| Sprint 4-5 (May 25-Jun 7): S1落地 | 未开始 | Week 3-4: S1+S2合并落地 + 分发连接器 |

**压缩逻辑：** 原8周压缩为4周，通过两轴并行实现：
- **轴1（纵向并行）：** 基础设施 + 管线可控性 + 内容质量 + 前端UI 四条轨道同时推进
- **轴2（横向并行）：** S1和S3共享质量层，一次开发两边复用

---

## 二、当前状态基线（Apr 28 晨）

### 已完成 ✅

| 领域 | 项目 | 证据 |
|------|------|------|
| 持久化 | PG dual-write + SQLite fallback | `src/storage/db.py`, `state_manager.py` |
| 脚本 | script_writer LLM 升级 | `src/skills/script_writer.py`, system prompt v2 |
| 安全 | 5项关键安全修复 | Phase 2 审计 |
| API | Seedance HTTP/1.1 兼容 | `seedance_client.py: http2=False` |
| TTS | 静音 MP3 fallback | `elevenlabs_tts.py: _build_silent_mp3()` |
| 诊断 | API 诊断脚本 | `scripts/diagnose_apis.py` |

### 进行中 🔄

| 项目 | 阻塞 | 位置 |
|------|------|------|
| Phase 3 E2E 真实管线 | Remotion 绑定(需宿主机npm install) | `docs/spike/2026-04-28_phase3-runbook.md` |
| Seedance 连接性测试 | 需真实运行 | runbook Step 3 |

### 待启动 ⏳

| 项目 | 来源 | 优先级 |
|------|------|--------|
| 管线可控性(step-by-step) | 演示后调整计划 P0-1 | **最高** |
| 视频时长可调 | 演示后调整计划 P0-2 | 高 |
| 文案 prompt 优化 | 演示后调整计划 P0-3 | 高 |
| Image2 单锚点验证 | 质量计划 Sprint A | 高 |
| 品牌资产 UI | 多场景路线图 R9b-2 | 中 |
| 分发连接器 | 多场景路线图 R9b-4 | 中 |

---

## 三、执行架构：四轨并行多智能体

```
                    ┌─────────────────────────────────────┐
                    │       集成与协调 Agent (主控)        │
                    │   - 统一场景架构检验                  │
                    │   - 跨轨依赖管理                      │
                    │   - 每日站会同步                      │
                    └──────────┬──────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ↓                      ↓                      ↓
┌───────────────┐   ┌─────────────────┐   ┌─────────────────────┐
│ 轨1: 基础设施  │   │ 轨2: 管线可控性  │   │ 轨3: 内容质量       │
│               │   │                 │   │                     │
│ - Remotion修复 │   │ - Step API      │   │ - character_identity│
│ - 真实媒体生成 │   │ - State 编辑UI  │   │ - keyframe_images   │
│ - PG 无缝迁移  │   │ - 逐步模式      │   │ - continuity_chain  │
│ - CI/构建     │   │ - 视频时长      │   │ - quality_gate      │
│               │   │ - 文案prompt    │   │ - E2E 对比验证      │
│               │   │                 │   │                     │
│ Agent: infra  │   │ Agent: control  │   │ Agent: quality      │
└───────┬───────┘   └────────┬────────┘   └──────────┬──────────┘
        │                    │                        │
        └────────────────────┼────────────────────────┘
                             │
                             ↓
                    ┌─────────────────┐
                    │ 轨4: 前端 UI     │
                    │                 │
                    │ - SceneSelector │
                    │   整合新功能    │
                    │ - 质量仪表盘    │
                    │ - 生产构建     │
                    │                 │
                    │ Agent: frontend │
                    └─────────────────┘
```

### 各轨 Agent 职责

| Agent | 职责范围 | 关键交付 | 依赖 |
|-------|---------|---------|------|
| **Coordinator** | 跨轨依赖管理、场景一致性审计、集成测试 | 每日同步报告 | 无 |
| **Infra (轨1)** | Remotion修复、真实媒体验证、PG迁移、Docker化 | 真实mp4产出 | 宿主机npm |
| **Control (轨2)** | Step API、状态UI、编辑重跑、逐步模式 | 可控管线前端 | 轨1(PG) |
| **Quality (轨3)** | 身份卡、关键帧、连续性链、质量门控 | 质量对比报告 | 轨1(Seedance) |
| **Frontend (轨4)** | Web UI整合、质量仪表盘、生产构建 | 可部署前端 | 轨2(API) |

---

## 四、Week 1 执行计划 (Apr 28 - May 2)

### Day 1: Apr 28 (今日)

**轨1 — Infra：Phase 3 收尾**
- [ ] 运行 `scripts/fix_remotion.sh` 修复 Remotion 绑定（需宿主机执行）
- [ ] `python scripts/diagnose_apis.py` 确认 API 状态
- [ ] 启动服务：Docker PG + uvicorn + npm dev
- [ ] 执行 S1 E2E (孕妇枕)：11步全部跑通
- [ ] 记录失败点到 `docs/spike/2026-04-28_s1-real-failures.md`
- [ ] 如 Remotion 不可用，使用 ffmpeg stub 回退

**轨2 — Control：Step API 设计**
- [ ] 设计 `/scenario/s1/step/{step}` API schema
- [ ] 设计 pipeline_state 增量更新协议
- [ ] 设计前端编辑组件接口 (EditableBrief, EditableScript)

**轨3 — Quality：代码准备**
- [ ] 审查 `seedance_client.py` 确认 `image_to_video()` 参数接口
- [ ] 审查 `gpt_image_generate.py` 确认可复用为关键帧生成
- [ ] 审查 `storyboard.py` 确认 shot 描述结构可驱动关键帧 prompt
- [ ] 创建 `character_identity.py` 骨架（人脸检测 + CLIP embedding）

**轨4 — Frontend：组件规划**
- [ ] 审查现有 SceneSelector / OneShotResultView 组件结构
- [ ] 设计质量仪表盘 UI 布局
- [ ] 列出需新增/修改的前端组件清单

**依赖协调：**
- 轨2 不需要等轨1 — Step API 可以先设计 schema，PG 后端延后接入
- 轨3 不需要等轨1 — 代码审查不依赖运行环境
- 轨4 不需要等轨2 — 可以先设计 UI 原型

### Day 2: Apr 29

**轨1 — Infra：真实媒体生成**
- [ ] 修复 Seedance 真实调用（如 Day1 失败）
- [ ] 修复 ElevenLabs TTS 真实调用（如 API key 缺失则用 stub）
- [ ] 修复 GPT-Image 真实缩略图生成
- [ ] 组装第一个完整的真实 S1 视频（即使质量不佳）
- [ ] PG 迁移验证：重启后端确认状态不丢失

**轨2 — Control：后端 Step API**
- [ ] 实现 `POST /scenario/s1/step/{step}` — 执行单步
- [ ] 实现 `GET /scenario/s1/state/{label}` — 读取状态
- [ ] 实现 `PUT /scenario/s1/state/{label}` — 更新编辑后的状态
- [ ] 实现 `POST /scenario/s1/resume` — 从 current_step 继续
- [ ] 实现 `POST /scenario/s1/regenerate` — 重跑指定步骤

**轨3 — Quality：character_identity 实现**
- [ ] 实现人脸检测（face_recognition 或 mediapipe）
- [ ] 实现人脸质量评分（清晰度 + 正面度 + 光照）
- [ ] 实现 CLIP embedding 提取和存储
- [ ] 单元测试：输入一张网红照片，输出 identity_card JSON

**轨4 — Frontend：UI 原型**
- [ ] SceneSelector 增加视频时长滑块 + 逐步/全自动切换
- [ ] OneShotResultView 每个 tab 增加编辑按钮（骨架）
- [ ] 质量仪表盘 UI 原型（静态数据）

### Day 3: Apr 30

**轨1 — Infra：Docker化**
- [ ] 编写 `docker-compose.yml` 全栈（PG + Backend + Frontend + Nginx）
- [ ] 测试 `docker-compose up` 一键启动
- [ ] 前端生产构建 `npm run build`

**轨2 — Control：前端编辑功能**
- [ ] EditableBrief 组件（可编辑 description, key_message, usp_priority）
- [ ] EditableScript 组件（可编辑 segment voiceover, visual_description）
- [ ] 编辑保存 → PUT state API → 重新生成联动
- [ ] 逐步模式 UI（StepByStepView，每步暂停显示「编辑」「下一步」）

**轨3 — Quality：keyframe_images 实现**
- [ ] 编写关键帧生成 prompt 模板（从 identity_card + storyboard shot 构建）
- [ ] 集成 gpt-image-2：传入 identity_card.reference_frames 作为参考图
- [ ] 实现候选帧评比（选 CLIP 相似度最高的关键帧）
- [ ] 修改 `seedance_clips` 步骤读取 keyframe path 并传入 `image_to_video`

**轨4 — Frontend：质量仪表盘**
- [ ] 实现质量评分卡片组件
- [ ] 集成轨3的 quality_gate 输出数据
- [ ] 失败步骤高亮 + 重试按钮

### Day 4: May 1

**轨1 — Infra：CI + 部署准备**
- [ ] 编写 CI 脚本（lint + test + build）
- [ ] 环境变量模板 `.env.example`
- [ ] README 更新（一键启动指南）

**轨2 — Control：端到端测试**
- [ ] 逐步模式 E2E 测试：S1 逐步执行，每步编辑
- [ ] 全自动模式 E2E 测试：S1 一键跑通
- [ ] 重启后恢复测试：执行到 step 5 → 重启 → 继续 step 6

**轨3 — Quality：S1 对比验证**
- [ ] 跑两条 S1（孕妇枕）：一条纯 text_to_video，一条 image_to_video 锚定
- [ ] 并排截图对比质量差异
- [ ] 输出对比报告 `docs/spike/image2-seedance-comparison.md`

**轨4 — Frontend：整合测试**
- [ ] 前端完整流程测试：选场景 → 逐步执行 → 编辑 → 重新生成 → 查看更多
- [ ] 响应式适配测试
- [ ] 性能测试（首屏加载、API 响应时间）

### Day 5: May 2

**全轨：集成验收**

- [ ] **集成测试 1：** S1（孕妇枕）从 SceneSelector → 逐步模式 → 编辑脚本 → 生成视频 → 查看结果
- [ ] **集成测试 2：** S3（网红视频）下载 → 分析 → 身份卡提取 → 生成二创视频
- [ ] **集成测试 3：** 重启后端 → 确认状态恢复 → 继续未完成的管线
- [ ] **集成测试 4：** `docker-compose up` → 浏览器访问 → 全流程走通

**验收清单：**
- [ ] 至少 1 条真实 S1 mp4（非 ffmpeg stub）
- [ ] 管线在重启后状态不丢失
- [ ] 用户可编辑步骤输出并重新生成
- [ ] character_identity 可提取人脸
- [ ] keyframe_images 可为每个 shot 生成关键帧
- [ ] image_to_video 至少跑通 1 条（Image2 锚定模式）

---

## 五、Week 2-4 概要（执行中动态调整）

### Week 2 (May 5-9): 全链路集成

**轨3 — Quality (Sprint B)：**
- continuity_chain 实现（Shot N 末帧 → Shot N+1 首帧约束）
- 产品锚定图自动匹配
- quality_gate 基础版（人脸 CLIP 相似度 + 产品边缘检测）
- retry 循环（最多 5 次）

**轨2 — Control：**
- S3 管线可控性（step-by-step API 适配 S3）
- 多语言管线分流（EN/ES/FR/DE 各产出一条）

**轨1 — Infra：**
- 分发连接器启动（TikTok Business API 申请 + 集成）
- 可观测性增强（trace_id + 结构化错误收集）

**轨4 — Frontend：**
- 品牌资产上传 UI
- 网红管理 UI

### Week 3 (May 12-16): 混合管线

**轨3 — Quality (Sprint C)：**
- 通道B 产品替换：product_detect skill (SAM分割) + product_swap skill (泊松融合)
- scene_decomposition skill (A/B/C 通道分流)
- S3 混合管线端到端运行（通道A原片段 + 通道B替换片段 + 通道C生成片段）

**轨2 — Control：**
- 分发面板 UI（发布按钮 + 状态追踪 + 失败重试）
- 审计仪表盘（quality_gate 结果可视化）

### Week 4 (May 19-23): 质量闭环

**轨3 — Quality (Sprint D)：**
- quality_gate 全部 7 项检测完善
- 降级策略（库存素材、静态卡片、fade 转场）
- 5 条真实网红视频端到端统计

**全轨：**
- 生产部署（docker-compose 生产配置 + SSL + 日志轮转）
- 文档完善（用户指南 + 开发者文档 + API 文档）

---

## 六、新增 Skill 清单（与现有 13 个的整合）

### 现有 Skill（不变）

| # | Skill | 场景 | 状态 |
|---|-------|------|------|
| 1 | product-strategy | S1/S2 | ✅ |
| 2 | script-writer | ALL | ✅ (LLM升级后) |
| 3 | brand-compliance | S2 | ✅ |
| 4 | viral-extractor | S3 | ✅ |
| 5 | video-analysis | S3 | ✅ |
| 6 | remix-script | S3 | ✅ |
| 7 | storyboard | ALL | ✅ |
| 8 | seedance-prompt | ALL | ✅ |
| 9 | thumbnail-prompt | ALL | ✅ |
| 10 | gpt-image-thumbnail | ALL | ✅ |
| 11 | seedance-video-generate | ALL | ✅ |
| 12 | elevenlabs-tts | ALL | ✅ |
| 13 | remotion-assemble | ALL | ✅ |

### 新增 Skill（质量层）

| # | Skill | 场景 | 插入位置 | Sprint |
|---|-------|------|----------|--------|
| 14 | character-identity | S3 | video_analysis → storyboard | A |
| 15 | keyframe-images | S1/S3 | storyboard → video_prompts | A |
| 16 | scene-decomposition | S3 | character_identity → remix_script | C |
| 17 | quality-gate | ALL | 每个媒体步骤后 | B |
| 18 | product-detect | S3 | remix_script → storyboard (通道B) | C |
| 19 | product-swap | S3 | product_detect → assemble (通道B) | C |

### Skill 调用依赖图

```
S1 (原创路径):
  product-strategy → script-writer → brand-compliance → storyboard 
    → keyframe-images(NEW) → video-prompts → seedance-clips(image_to_video)
      → [quality-gate(NEW)] → tts-audio → assemble-final

S3 (二创路径):
  video-analysis → character-identity(NEW) → scene-decomposition(NEW)
    ├─ 通道A: 原片段直接 → assemble-final
    ├─ 通道B: product-detect(NEW) → product-swap(NEW) → assemble-final
    └─ 通道C: remix-script → storyboard → keyframe-images(NEW) 
                → video-prompts(含continuity) → seedance-clips(image_to_video)
                  → [quality-gate(NEW)] → assemble-final
```

---

## 七、风险矩阵（整合版）

| # | 风险 | 概率 | 影响 | 缓解 | 所属轨 |
|---|------|------|------|------|--------|
| R1 | Remotion 绑定无法修复 | 中 | 中 | ffmpeg stub 回退，轨1继续 | 轨1 |
| R2 | Seedance 真实调用持续失败 | 中 | 高 | HTTP/1.1已修复；如仍失败用stub，轨3独立验证 | 轨1/3 |
| R3 | gpt-image-2 参考图注入不生效 | 中 | 中 | 轨3 第一天就验证，不生效则降级为纯text_to_video | 轨3 |
| R4 | 轨2/轨3 并行修改同一文件冲突 | 低 | 中 | 轨2改API层，轨3改skill层，接口约定先行 | ALL |
| R5 | 时间不足以完成全部4轨 | 高 | 中 | Week 1末评估进度，取舍决策：轨2(可控性) > 轨3(质量) > 轨4(UI) | Coordinator |
| R6 | ElevenLabs key 缺失 | 高 | 低 | 已有silent MP3 fallback，不阻塞 | 轨1 |
| R7 | poyo.ai 服务不稳定 | 中 | 高 | HTTP/1.1 + timeout + retry已修复；如持续不稳定通知用户 | 轨3 |

---

## 八、场景一致性自查表

| 检查项 | 战略计划要求 | 整合方案 | 一致性 |
|--------|-------------|---------|--------|
| 核心路径为 原创+二创 两条 | ✅ | 整合方案保持原创(S1∪S2)和二创(S3)两条核心路径 | ✅ |
| S4 暂缓 | ✅ | 整合方案不做S4增强，不增加footage_analyzer | ✅ |
| S2 合并到 S1，用 brand_mode 标志位 | 建议中 | Week 3-4 执行，当前保持独立但共享 Skill 层 | ✅ |
| 不新增场景 | ✅ | 新增的是质量层和可控性，非新场景 | ✅ |
| 先跑通一条真实视频 | ✅ | Day 1-2 目标即为 S1 E2E 真实产出 | ✅ |
| Skill + Pipeline 两层架构 | ✅ | 质量层以新 Skill 形式注入，不破坏架构 | ✅ |
| 品牌资产入库是核心护城河 | ✅ | Week 2 轨4 做品牌资产 UI | ✅ |
| 多语言先不铺 | 建议 Sprint 6 | Week 2 轨2 做基础验证(各语言1条) | ⚠️ 略有提前 |
| 分发连接器做1个平台 | Sprint 7 | Week 2 轨1 启动TikTok | ⚠️ 提前但可并行 |

**唯一偏离：** 多语言和分发连接器的启动时间略早于战略计划建议。理由是：
- 多语言验证不新增代码，只是用已有 prompt 跑一次真实模式
- 分发连接器 API 申请需要时间（1-3工作日审核），提前提交不占用开发资源

---

## 九、执行命令速查

### Day 1 立即执行

```bash
# 轨1: 修复 Remotion（在宿主机执行）
cd ~/project/hermes_evo/AI_vedio/rendering/
rm -rf node_modules package-lock.json && npm install
npx remotion --version

# 轨1: 诊断所有 API
cd ~/project/hermes_evo/AI_vedio
source .venv/bin/activate
python scripts/diagnose_apis.py

# 轨1: 启动服务
docker start ai_video_postgres
uvicorn src.api:app --reload --port 8001 &
cd web/ && npm run dev &

# 轨1: 跑 S1 E2E
# 打开 http://localhost:3000 → 选商品直拍 → 孕妇枕/Momcozy → 逐步执行

# 轨3: 审查关键接口（只读，不修改）
grep -n "image_to_video\|first_frame\|last_frame" src/tools/seedance_client.py
grep -n "class.*Skill\|def execute" src/skills/storyboard.py

# 轨2: 查看当前 API 结构
grep -n "def.*step\|def.*state\|/scenario/" src/api.py
```

### 每日站会检查点 (18:00)

```bash
# Coordinator 收集各轨状态
# 轨1: 真实 mp4 产出？有/无，文件路径？
ls -la output/seedance/ output/assemble/
# 轨2: Step API 可用？
curl -s http://localhost:8001/scenario/s1/state/TEST-001
# 轨3: 人物身份卡可提取？
python -c "from src.skills.character_identity import CharacterIdentitySkill; print('OK')"
# 轨4: 前端构建成功？
cd web && npm run build 2>&1 | tail -5
```

---

## 十、附录：文档索引

| 文档 | 路径 | 角色 |
|------|------|------|
| 战略全景规划 | `docs/strategy/2026-04-26_strategic-plan.md` | 场景架构 + 8周路线图 |
| 多场景路线图 | `plan/2026-04-26_multi-scenario-roadmap.md` | R9a/b/c 详细任务 |
| 演示后调整计划 | `plan/2026-04-27_post-demo-adjusted-plan.md` | 可控性优先 + 分发 |
| Phase 2 执行计划 | `plan/2026-04-27_phase2_execution_plan.md` | PG持久化 + 多Agent并行 |
| Phase 3 Runbook | `docs/spike/2026-04-28_phase3-runbook.md` | E2E 真实管线执行步骤 |
| Image2+Seedance 优化 | `docs/spike/2026-04-28_image2-seedance-optimization-plan.md` | 质量层详细设计 |
| **整合总计划 (本文)** | `docs/spike/2026-04-28_integrated-master-plan.md` | 一致性整合 + 多轨执行 |

---

*计划制定：2026-04-28*
*下次更新：每日 18:00 五轨站会*
