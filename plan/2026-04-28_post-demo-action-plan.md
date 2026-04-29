# 演示后落地执行计划 — 2026-04-28

> 基于 04-27 演示结果 + 战略全景规划 + 高危风险清单制定
> 原则：从"能演示"到"能产出"，聚焦真实视频闭环

---

## 一、今日演示复盘（04-27）

### 验证通过的能力

| 能力项 | 演示状态 | 说明 |
|--------|----------|------|
| S1 手动工作流 | 可用 | 11 步可逐一点击执行，UI 状态反馈正常 |
| 内容审计/编辑 | 可用 | strategy/scripts/storyboards/prompts 均可编辑保存 |
| 媒体预览 | 已修复 | PortfolioGallery 模态框播放正常，VideoWorkflow 片段可播放 |
| Kimi 策略生成 | 已修复 | 120s 超时 + JSON 解析容错，策略brief可正常产出 |
| API_KEY 鉴权 | 已修复 | 前后端 X-API-Key 同步，CORS 已收紧 |
| 安全自检 | 通过 | 11 项安全检查全部通过 |

### 演示中暴露的未解决阻塞

| 问题 | 严重度 | 影响范围 | 根因 |
|------|--------|----------|------|
| **数据重启丢失** | P0 | 所有 pipeline 状态 | MemorySaver 默认，PG 未启用 |
| **script_writer 是模板** | P0 | 脚本质量差 | skill 是硬编码模板，无 LLM |
| **storyboard 是规则** | P0 | 分镜无创意 | 纯 heuristic，无 LLM |
| **brand_compliance 是匹配** | P1 | 合规审核虚设 | 只检查关键词，无语义分析 |
| **无真实分发** | P1 | DistributionView | 仅输出 JSON 计划 |
| **前端 dev 模式** | P2 | 演示/部署 | npm run dev，未 build |

---

## 二、明日核心目标（04-28）

> **单一定位：让 S1 pipeline 产出第一条非 stub 的真实视频**

### 目标定义（可验收）

1. **数据持久化生效**：uvicorn 重启后，已执行的 pipeline 步骤不丢失，可继续执行
2. **脚本质量升级**：script_writer 接入 LLM（Kimi），产出自然语言脚本（非模板填充）
3. **端到端跑一次 S1（产品：孕妇枕）**：从配置完成 → audit 结束，产出至少一个有效视频文件
4. **失败点记录**：任何步骤失败，记录错误日志和上下文，写入 `docs/spike/2026-04-28_s1-real-failures.md`

---

## 三、明日执行计划（按时段）

### Phase 1: 环境准备与持久化（09:00-10:30）

#### Task 1.1: 启用 PostgreSQL 持久化（P0，1.5h）

**执行步骤：**
```bash
# 1. 确认 Docker PG 已运行
docker ps | grep ai_video_postgres

# 2. 切换默认 checkpointer
# 修改 src/pipeline/s1_product_pipeline.py
# 将 checkpointer = MemorySaver() 改为 Postgres 连接
```

**代码修改点：**
- `src/pipeline/s1_product_pipeline.py`: StepRunner 初始化时，使用 Postgres 替代 memory dict
- `src/pipeline/state_manager.py`: 确保 `save_state()` 和 `load_state()` 默认写 PG，而非仅 JSON 文件
- `src/api.py`: `/pipeline/{id}/state` 从 PG 读取，而非全局变量

**验收标准：**
```bash
# 1. 启动后端
uvicorn src.api:app --port 8001

# 2. 执行 S1 前几步（到 strategy）
curl -X POST http://localhost:8001/scenario/s1 ...

# 3. 重启后端（Ctrl+C 再启动）

# 4. 查询同一 pipeline_id，状态存在且内容一致
curl http://localhost:8001/pipeline/{id}/state
# 期望：返回 strategy 步骤的完整数据，非空
```

**阻塞预案：**
- 若 Docker PG 连接失败 → 改用 SQLite 文件作为 fallback，确保重启不丢数据
- 若 asyncpg 报错 → 检查 `DATABASE_URL`，确认用户名密码正确

---

### Phase 2: 脚本生成质量升级（10:30-12:30）

#### Task 2.1: script_writer skill 接入 LLM（P0，2h）

**现状问题：**
- `src/skills/script_writer.py` 使用硬编码模板，产出类似：
  ```
  "还在用传统孕妇枕？试试 Momcozy！"
  ```
- 无 LLM 调用，无创意，无多语言质感

**改造方案：**
1. 参照 `product_strategy.py` 的 LLM 调用模式
2. 编写 script_writer 专用的 system prompt（要求：口语化、有节奏、适配短视频）
3. 输入：brief（topic, target_audience, key_message, usp_priority）
4. 输出：3-segment 脚本（hook/body/cta），每个 segment 包含 voiceover + visual_description

**prompt 设计要点：**
- 中文场景：产出中文脚本，口语化，带停顿标记（…）
- 时长控制：hook 3-5s, body 15-25s, cta 3-5s，总时长 30-40s
- USP 自然融入：不硬塞，用场景带出来
- 品牌关键词必须出现（从 brand_guidelines 读取）

**验收标准：**
```python
# 1. 直接测试 skill
from src.skills.script_writer import ScriptWriterSkill
skill = ScriptWriterSkill()
result = await skill.execute({
    "briefs": [{...}],  # 孕妇枕的 brief
    "brand_guidelines": {"tone_of_voice": {...}}
})
# 期望：voiceover 不是模板，是自然语言；visual_description 具体有画面感

# 2. UI 验证
# 进入 VideoWorkflow → 执行 strategy → 执行 scripts
# 点击"查看" → 脚本读起来像人写的，不是填空
```

**阻塞预案：**
- 若 LLM 超时 → 缩短 prompt，减少 brief 数量，或增加 timeout 到 180s
- 若 JSON 解析失败 → 复用 `llm_client._parse_json()` 的 markdown 容错逻辑

---

### Phase 3: 端到端真实跑通（14:00-18:00）

#### Task 3.1: 完整执行 S1 pipeline（孕妇枕）（P0，4h）

**执行路径：**
1. 前端：选择 "product_direct" → 产品名 "孕妇枕" → 品牌 "Momcozy"
2. 点击 "配置完成 →" → 进入 VideoWorkflow
3. 手动执行：strategy → scripts → compliance → storyboards → video_prompts → thumbnail_prompts
4. 媒体生成：seedance_clips → tts_audio → thumbnail_images
5. 最终：assemble_final → audit

**重点观察点（每步记录）：**

| 步骤 | 观察指标 | 期望结果 |
|------|----------|----------|
| strategy | brief 质量 | 5 个 brief 各有差异，topic 具体不空洞 |
| scripts | 脚本自然度 | 非模板填充，voiceover 口语化 |
| compliance | 审核结果 | 通过或给出具体 FLAG 原因 |
| storyboards | 分镜细节 | shot_type 多样，有镜头运动描述 |
| video_prompts | prompt 质量 | 英文，含场景描述、光影、运镜 |
| seedance_clips | 视频生成 | 输出真实 mp4，>100KB，可播放 |
| tts_audio | 音频生成 | 输出真实 mp3，有语音内容 |
| thumbnail_images | 图片生成 | 输出真实 png，>10KB |
| assemble_final | 最终视频 | 输出合成 mp4，含视频+音频 |
| audit | 审计报告 | 有评分，指出具体问题 |

**问题记录格式：**
任何步骤失败或产出质量不达标，记录到 `docs/spike/2026-04-28_s1-real-failures.md`：
```markdown
## [步骤名] — [问题简述]
- 时间：2026-04-28 HH:MM
- 输入：[关键输入摘要]
- 预期：[应该发生什么]
- 实际：[发生了什么]
- 错误日志：[关键日志片段]
- 根因分析：[你的判断]
- 临时绕过：[怎么让演示继续]
```

**验收标准：**
- 最低线：`output/` 目录出现至少 1 个由 Seedance 生成的 mp4 文件（非 ffmpeg stub）
- 目标线：`assemble_final` 产出完整合成视频（视频+配音+字幕）
- 理想线：audit 给出 PASS 或 WARN（非 FAIL）

---

### Phase 4: 文档与复盘（18:00-19:00）

#### Task 4.1: 更新明日计划与风险清单（1h）

1. **填写 failures.md**：记录今天遇到的所有问题
2. **更新计划文件**：根据今天的实际进展，调整 04-29 计划
3. **确认优先级**：如果今天只完成了持久化+LLM脚本，明天继续 media 生成；如果全跑通，明天做 S3 spike

---

## 四、风险应对预案

| 风险 | 概率 | 应对 |
|------|------|------|
| Seedance API 不可用或超时 | 中 | 用 ffmpeg 生成 stub，但标记为 stub，记录到 failures |
| ElevenLabs API 不可用 | 中 | 用 ffmpeg 生成静音 mp3，标记 stub |
| Kimi 策略/脚本再次超时 | 中 | 已设 120s，若仍超时，拆分为 2 次调用（策略先，脚本后） |
| Remotion 渲染失败 | 高 | 检查 rendering/ 目录是否有 node_modules，如无则跳过 assemble |
| PG 连接失败 | 低 | fallback 到 SQLite 文件 |
| 前端构建失败 | 低 | 保持 dev 模式继续演示 |

---

## 五、验收清单（18:00 自测）

- [ ] uvicorn 重启后，`/pipeline/{id}/state` 返回非空数据
- [ ] script_writer 产出非模板脚本（至少 hook 段不像硬编码）
- [ ] `output/seedance/` 目录有 >100KB 的 .mp4 文件
- [ ] `output/tts/` 目录有 >1KB 的 .mp3 文件
- [ ] `output/remotion/` 或 `output/assemble/` 有最终合成文件（如有 Remotion）
- [ ] `docs/spike/2026-04-28_s1-real-failures.md` 已创建（无论是否有失败）

---

## 六、与整体路线的对齐

| 本周目标（Sprint 0） | 今天完成度 | 明天聚焦 |
|----------------------|------------|----------|
| 决定 A/B/C 路径 | 未决策 | 默认按 A 路径执行（垂直工厂） |
| 真实模式 spike | 演示了 UI，未跑通真实生成 | **核心任务** |
| PG 持久化 | 代码齐，未切换默认 | **上午必完成** |
| S2 合并到 S1 | 未决策 | 暂不处理，保持现状 |
| 失败点记录 | 无 | **全天记录** |

> **明日一句话目标：让孕妇枕的 S1 pipeline 在重启后还能继续跑，并且脚本不再像机器人写的。**

---

*计划制定：2026-04-27 晚间*
*下次更新：04-28 18:00 后根据实际进展调整*
