---
name: runbook-poyo-rejection
description: Runbook 文档，处理 POYO Happy Horse / GPT Image API 内容审核拒绝时的诊断、规避词清单更新与流水线恢复步骤。当 keyframe / thumbnail 步骤连续出现 content_violation 错误时使用。
---

# Runbook — POYO Content Moderation Rejection

| | |
|---|---|
| **触发场景** | poyo API 返回 `content_violation` / `safety_block` / HTTP 400 `flagged` |
| **影响范围** | media_generation / thumbnail_images / seedance_clips 步骤 |
| **预期 MTTR** | 5-10 分钟（添加规避词后流水线 retry） |
| **相关代码** | [`src/tools/poyo_safety.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_safety.py) · [`src/tools/poyo_client.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_client.py) |

## 一、症状识别

| 信号源 | 内容 |
|---|---|
| 后端日志 | `poyo_client: content moderation rejected` 或 HTTP 400 `flagged_content` |
| state | `state.media_synthesis_errors` 含 `content_violation` |
| 前端 | 缩略图渲染失败，gate 候选缺图 |

## 二、立即诊断

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232

sudo docker logs --tail 500 ai_video_backend 2>&1 \
  | grep -iE "poyo.*reject|content_violation|flagged" | tail -20

sudo docker logs --tail 500 ai_video_backend 2>&1 \
  | grep -B 5 "content_violation" | grep "prompt" | head -5

sudo docker exec ai_video_backend grep -nE "^[[:space:]]*\"" src/tools/poyo_safety.py | head -30
```

## 三、分类响应

### 场景 A: 单个 prompt 偶发拒绝

- **判断**：当前 batch 只有 1 个 prompt 命中
- **响应**：**无需介入**。poyo_safety.py 已有自动重试 + 同义词替换。流水线会自动 retry 3 次，仍失败则降级为占位图但流水线继续。

### 场景 B: 新的触发词 / 高频拒绝（同一关键词在 1 小时内 ≥ 3 个 prompt 命中）

- **判断**：步骤 1 日志中出现新词 X 反复拒绝
- **响应**：
  1. 复刻 prompt 到本地测试：`docker exec ai_video_backend python3 -c "
     from src.tools.poyo_safety import sanitize_for_poyo
     text = '<paste prompt>'
     print(sanitize_for_poyo(text))"`
  2. 如果 sanitized 输出不变 → 关键词未被覆盖，需添加
  3. 编辑 [`src/tools/poyo_safety.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_safety.py) `_SUBSTITUTIONS`，添加 `"<触发词>": "<中性替代>"`
  4. 写单测（参考 `tests/test_poyo_safety.py`）保护新规则
  5. 提交 → push → 灰度部署：`rsync src/tools/poyo_safety.py + docker compose restart backend`
  6. 验证：重新跑失败 pipeline → 应通过

### 场景 C: POYO 整体平台拒绝率激增

- **判断**：步骤 1 拒绝事件远超历史均值
- **响应**：
  1. 检查是否 poyo 平台升级了审核策略（[poyo 文档](https://api.poyo.ai/docs)）
  2. 评估切换到 Seedance / DALL-E fallback：当前 `src/tools/poyo_client.py` 已支持 multi-provider 切换
  3. 临时降级：在 `.env.prod` 添加 `POYO_FALLBACK_TO_DALLE=1`（如已实现），重启 backend

## 四、规避词维护原则

`_SUBSTITUTIONS` 是核心规则：

- **目标**：保留 prompt 语义，仅替换触发审核的词
- **优先级**：母婴/喂养场景词汇（"breast", "nursing", "feeding", "newborn"）→ 友好替代（"caring", "comfort", "infant")
- **测试**：每次新加规则必须配套 `tests/test_poyo_safety.py` 测试
- **同步**：规则更新后在 [`docs/poyo-trigger-words.md`](../poyo-trigger-words.md) 和
  `tests/fixtures/commercial_video/poyo_content_rejection_samples.json` 同步

## 五、根因记录

故障恢复后：

1. 命中新触发词的 prompt 先在
   `tests/fixtures/commercial_video/poyo_content_rejection_samples.json` 记录，再同步到
   [`docs/poyo-trigger-words.md`](../poyo-trigger-words.md)
2. 如果一周内新增 ≥ 5 个触发词：评估是否需要主动联系 poyo 平台沟通母婴场景白名单
3. 关注 [`src/agents/strategy.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/agents/strategy.py) 的 LLM 是否在生成 prompt 时本身就过激（前移防御）

## 六、相关 Runbook

- [deepseek-timeout.md](./deepseek-timeout.md)
- [pipeline-stuck.md](./pipeline-stuck.md)
