# 明日开发 + 测试计划

> 日期：2026-04-29 | 基于：4/28-29 全部交付 + Layer 5 完成

---

## 一、当前状态简报

**五层闭环全部就绪：**

| 层 | 完成度 | 关键能力 |
|----|--------|---------|
| L1 内容策略 | 80% | Product/Campaign Context注入，Data Usage Rules，3 briefs |
| L2 叙事设计 | 80% | scripts并行化，storyboard分镜，keyframe关键帧锚定 |
| L3 生成控制 | 60% | Seedance锚定，continuity_chain，quality_gate 7检查 |
| L4 工作流工程 | 80% | StepRunner，4-Gate审批，3候选评分，Smart/Expert双模式 |
| L5 商业化分发 | 新上线 | Publish Engine，Metrics Poller，Performance Dashboard |

**代码状态：** 后端全量 py_compile 通过，前端 tsc --noEmit 零错误。

---

## 二、上午——测试验证（3h）

### 2.1 Pre-flight（30min）

```bash
# 1. 确认 .env 有所有 API key
grep -E "OPENAI|POYO|API_KEY|DATABASE_URL" .env

# 2. 启动 Docker PG
docker compose up -d postgres

# 3. 诊断所有 API
python scripts/diagnose_apis.py
# 预期: 7/8 PASS, 1 WARN (ElevenLabs)

# 4. 启动服务
uvicorn src.api:app --reload --port 8001 &
cd web && npm run dev &
```

### 2.2 S1 商品直拍——端到端真实测试（90min）

**测试 A：Smart Create 全自动**
```bash
curl -X POST localhost:8001/scenario/s1 \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"product_catalog":{"products":[{"name":"Maternity Pillow","usps":["ergonomic","breathable"],"category":"pregnancy_sleep_aid","usage_scenario":"Bedroom, third trimester","pain_points":["Cannot sleep after 28 weeks","Lower back pain"],"target_audience":"Pregnant women 25-35","competitor_context":["PharMeDoc cheaper but less versatile"]}]},"brand_guidelines":{"brand_name":"Momcozy","tone_of_voice":{"archetype":"Caregiver","keywords":["warm","empowering"],"do_examples":["Your body is doing something incredible. Let it rest."],"dont_examples":["Revolutionary ergonomic design with patented technology"]}},"target_platforms":["tiktok","shopify"],"target_languages":["en"],"video_duration":30}'
```
验收：success=True，steps_completed=12，final_video_path 非空

**测试 B：Expert Studio Gate 审批**
1. 前端打开 localhost:3001 → 选择 Product Showcase → 填入产品信息
2. 展开 Product Details，填入 pain_points 等 → Continue
3. AI 推荐确认 → Start（默认 Expert）
4. Gate 1：查看 3 个候选脚本 → 选 1 个推荐 → Approve
5. 观察后续 Gate 2-4 流程

**测试 C：持久化验证**
```bash
# 执行到步骤 3 → 杀掉 uvicorn → 重启 → 继续执行
```
验收：重启后状态恢复，可从断点继续

### 2.3 S3 网红二创——质量层验证（60min）

**测试 D：remix_script LLM 模式**
```bash
curl -X POST localhost:8001/scenario/s3 \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"video_url":"<测试视频URL>","product":{"name":"Maternity Pillow","usps":["ergonomic"],"pain_points":["Cannot sleep"],"target_audience":"Pregnant women 25-35"},"video_duration":30}'
```
验收：identity_card 非空，clip_paths > 0

### 2.4 记录结果

创建 `docs/spike/2026-04-29_test-results.md`，记录每条测试的 pass/fail 和真实错误。

---

## 三、下午——缺陷修复 + 参数调优（3h）

### 3.1 基于测试结果修复 P0 缺陷

从上午测试结果中提取所有失败点，按严重度排序修复。

### 3.2 Seedance 参数调优

如果 Seedance API 可用：
- 测试不同的 prompt 措辞对视频质量的影响
- 调节 duration 参数观察输出稳定性
- 测试 keyframe 锚定 vs 纯文本生成的画质差异

### 3.3 产出 3 条可播放视频

目标：S1 Maternity Pillow × 2（不同时长）+ S1 Baby Monitor × 1

---

## 四、傍晚——收尾（2h）

### 4.1 前端生产构建验证
```bash
cd web && npm run build
```

### 4.2 Layer 5 Dashboard 首次填充
发布测试视频 → 手动触发 metrics pull → 验证 Dashboard 展示数据

### 4.3 文档更新
更新 `docs/spike/2026-04-29_test-results.md` 和 changelog

---

## 五、Bug Watch List

| # | 风险 | 检测 | 缓解 |
|---|------|------|------|
| B1 | Remotion 绑定失败 | npx remotion --version 崩溃 | ffmpeg stub 回退 |
| B2 | Seedance 403 | clip_paths 为空 | stub 回退已就绪 |
| B3 | Kimi API 超时 | strategy > 120s | 已优化到 3 briefs，约 45s |
| B4 | PG 连接失败 | health 显示 pg_available=false | SQLite 自动回退 |
| B5 | Expert 模式刷新丢状态 | 刷新后空白 | P0-4 已修复（localStorage） |
| B6 | 前端旧端口占用 | port 3000/3001 冲突 | 用 3001，kill 旧进程 |
