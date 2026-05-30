---
title: 视频生成速度优化部署与验证计划
doc_type: workflow
module: pipeline
topic: speed-optimization-deploy
status: stable
created: 2026-05-23
updated: 2026-05-31
owner: self
source: human+ai
---

# 视频生成速度优化部署与验证计划

> **历史语境（2026-05-31）**：本文是视频生成速度专项部署计划，保留为该专项的部署、监控和回滚参考。它不是当前“继续下一步”的执行入口；当前技术债 TODO 以 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md) 为准。未充值 POYO 前，不执行本文的真实生产 smoke 或 token 消耗项。

> 关联文档：
> - 根因分析：`docs/analysis/video-generation-speed-root-cause-analysis.md`
> - 优化方案：`docs/analysis/video-generation-speed-optimization-plan.md`
> - 当前已知缺口入口：[`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md)

---

## 一、部署前检查清单

### 1.1 代码状态确认

```bash
# 确认当前分支与改动范围
git status
git diff --stat src/skills/seedance_video_generate.py src/pipeline/s4_live_shoot_pipeline.py src/pipeline/s5_brand_vlog_pipeline.py src/pipeline/step_runner.py src/skills/keyframe_images.py src/pipeline/s1_product_pipeline.py
```

预期改动 7 个文件（6 个源码 + 1 个测试），约 80 行净增。

### 1.2 测试验证（本地）

```bash
# 1. 关键 E2E 测试
.venv/bin/python -m pytest tests/test_s4_e2e.py tests/test_s5_e2e.py tests/test_frame_variance.py -v -q

# 2. Lint
.venv/bin/python -m ruff check src/pipeline/s4_live_shoot_pipeline.py src/pipeline/s5_brand_vlog_pipeline.py src/pipeline/step_runner.py src/skills/seedance_video_generate.py src/skills/keyframe_images.py src/pipeline/s1_product_pipeline.py

# 3. 全量测试（可选，CI 已覆盖）
make test
```

### 1.3 配置检查

| 配置项 | 当前值 | 是否需要调整 |
|--------|--------|-------------|
| `QUALITY_MODE` | `observe`（默认） | 保持 — P0-3 在此模式下生效 |
| `SKIP_THUMBNAIL_IN_AUTO` | 未设置 | 按需启用，见 Phase 2 |

---

## 二、分阶段部署

### Phase 0: 备份（5 分钟）

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video

# 备份当前代码
cp -r src src-backup-20260523-speed-opt
cp -r tests tests-backup-20260523-speed-opt

# 记录当前部署版本
git rev-parse HEAD > .deployed-before-speed-opt
```

### Phase 1: 后端部署（10 分钟）

```bash
# 1. rsync 改动文件（仅 7 个文件）
rsync -avz --relative \
  src/skills/seedance_video_generate.py \
  src/pipeline/s4_live_shoot_pipeline.py \
  src/pipeline/s5_brand_vlog_pipeline.py \
  src/pipeline/step_runner.py \
  src/skills/keyframe_images.py \
  src/pipeline/s1_product_pipeline.py \
  tests/test_s4_e2e.py \
  ubuntu@101.34.52.232:/opt/ai-video/

# 2. 重启 backend 容器
ssh ubuntu@101.34.52.232 \
  'cd /opt/ai-video/deploy/lighthouse && sudo docker-compose -f docker-compose.prod.yml up -d --no-deps --build backend'

# 3. 验证启动
sleep 5
curl -fsSk https://101.34.52.232/health | python3 -m json.tool
```

**回滚**: 如发现问题，`rsync` 反向同步 `src-backup-20260523-speed-opt/` 然后重启容器。

### Phase 2: 缩略图跳过开关（可选，2 分钟）

仅在需要进一步降低 S1/S2/S3 时间时启用：

```bash
# 编辑 .env.prod，追加一行
SKIP_THUMBNAIL_IN_AUTO=1

# 重启 backend 使环境变量生效
ssh ubuntu@101.34.52.232 \
  'cd /opt/ai-video/deploy/lighthouse && sudo docker-compose -f docker-compose.prod.yml up -d --no-deps backend'
```

**注意**: 跳过缩略图后，平台发布时需独立生成封面图。

### Phase 3: 前端（本次不涉及）

本次优化全部为后端改动，前端无需重新构建或部署。

---

## 三、部署后验证

### 3.1 快速冒烟（5 分钟）

```bash
# 1. Health check
curl -fsSk https://101.34.52.232/health

# 2. Fast Mode（不受改动影响，作为非回归基线）
curl -X POST https://101.34.52.232/api/fast/generate \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a baby bottle in natural lighting"}'

# 3. S1 auto mode（验证 P0-3 + P1-1 + P2-1）
curl -X POST https://101.34.52.232/api/scenario/s1 \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_catalog": {
      "product_name": "Test Pump",
      "description": "Wearable breast pump for moms"
    },
    "mode": "auto"
  }'
```

### 3.2 时间对比验证（30 分钟）

使用同一组输入，在优化前后各跑一次，记录时间：

```bash
# 记录开始时间
curl -s -w "\n%{time_total}\n" -X POST ...

# 对比指标
# - 优化前 S1 auto: ~244s (参考值)
# - 优化后 S1 auto: ~152s (目标)
# - 优化前 S4 auto: ~210s
# - 优化后 S4 auto: ~155s
# - 优化前 S5 auto: ~312s
# - 优化后 S5 auto: ~185s
```

### 3.3 质量非回归验证

```bash
# 对比优化前后的 audit_report 评分
# 同一组输入跑两次，比较 audit_report.total_score
# 预期差异 < 0.05
```

### 3.4 S5 连续性验证（关键）

```bash
# S5 必须验证：keyframe 覆盖时并发、无 keyframe 时串行 fallback
# 1. 有 product_sku.views 的 S5 请求 → 应走并发分支
# 2. 无 product_sku.views 的 S5 请求 → 应走串行 fallback
# 查看后端日志确认分支
ssh ubuntu@101.34.52.232 'sudo docker logs --tail 50 ai_video_backend'
```

---

## 四、监控项

部署后 24h 内关注：

| 指标 | 检查方式 | 正常范围 |
|------|---------|---------|
| S4 clip 生成时间 | 日志中 `seedance_clips` step duration | < 40s（3 clips） |
| S5 clip 生成时间 | 日志中 `seedance_clips` step duration | < 40s（5 clips，有 keyframe） |
| frame_variance 跳过 | `seedance_video_generate.py` 日志无 `frame_variance` 记录 | observe 模式下应无记录 |
| 错误率 | `/telemetry/prometheus` `pipeline_errors_total` | 无异常增长 |
| audit 评分 | `audit_report.total_score` | 与优化前差异 < 0.05 |

---

## 五、回滚方案

### 5.1 代码回滚（2 分钟）

```bash
ssh ubuntu@101.34.52.232
cd /opt/ai-video
rsync -av src-backup-20260523-speed-opt/ src/
sudo docker-compose -f deploy/lighthouse/docker-compose.prod.yml up -d --no-deps --build backend
```

### 5.2 配置回滚（1 分钟）

```bash
# 如启用了 SKIP_THUMBNAIL_IN_AUTO
sed -i '/SKIP_THUMBNAIL_IN_AUTO/d' .env.prod
sudo docker-compose -f deploy/lighthouse/docker-compose.prod.yml up -d --no-deps backend
```

### 5.3 触发回滚的条件

- 任一场景的 E2E 测试在生产环境失败
- audit_report 评分下降 > 0.10
- S5 视频出现明显连续性断裂（视觉不连贯）
- 错误率异常增长

---

## 六、后续迭代

### 6.1 已识别但未实施的优化

根因分析中识别了以下优化，但不在本次范围内：

| 根因 | 优化方向 | 复杂度 | 预期收益 |
|------|---------|--------|---------|
| LLM 模型选择（V4-Pro reasoning） | 按步骤选择轻量模型（strategy/script 用 V3） | 中 | 40-100s |
| Pipeline 12 步串行 | 步骤合并/并行（如 strategy+script 合并） | 高 | 30-60s |
| LangGraph checkpoint 每步持久化 | 批量写入或内存缓存 | 中 | 2-5s |
| Seedance 轮询间隔（5s 固定） | 改用 webhook 或 SSE 推送 | 高（需 API 侧支持）| 10-30s |

### 6.2 数据驱动优化

部署后收集 1 周真实数据，评估：

1. **实际收益** vs 预估收益的差异
2. **质量影响** — audit_report 评分分布变化
3. **并发安全性** — S4/S5 并发模式下失败率是否增加
4. **资源压力** — poyo.ai / Seedance API 并发请求是否触发限流

基于数据决定是否：
- 调整 `Semaphore(4)` 并发数
- 扩大/缩小 keyframe 限制公式
- 启用 `SKIP_THUMBNAIL_IN_AUTO`

---

*计划制定于 2026-05-23，配合视频生成速度优化代码改动使用。*
