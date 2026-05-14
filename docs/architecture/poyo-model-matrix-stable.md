---
name: poyo-model-matrix-stable
description: poyo.ai模型库速查表，覆盖2026-05 catalog在售模型ID、能力边界、Gate阈值、场景适配建议。当工程师或运营需要快速选择/切换模型时使用，是 src/pipeline/model_thresholds.py 的人类可读文档。
doc_type: architecture
module: ai-video
topic: model-matrix
status: stable
created: 2026-05-14
updated: 2026-05-14
owner: AIVideoIntel
source: ai
related:
  - file: ../workflows/2026-05-14-poyo-constrained-optimization-roadmap.md
    relation: implements
  - file: ../../src/pipeline/model_thresholds.py
    relation: machine-readable-counterpart
---

# poyo.ai 模型库速查表（2026-05）

> **目的**：把 poyo.ai 在售模型 + 我们的 Gate 阈值 + 场景适配建议 整合成单页速查。代码层面对应 [`src/pipeline/model_thresholds.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/model_thresholds.py)。
> **数据来源**：poyo.ai 官网 / docs / changelog 2026-05 snapshot + [优化排期路线图](../workflows/2026-05-14-poyo-constrained-optimization-roadmap.md) 决策 D/F。
> **更新节奏**：poyo 新模型上线后由 @AIVideoIntel 同步本表 + 同步 `model_thresholds.py`。

---

## 一、视频生成模型

### 1.1 Premium 档（首选）

| Model ID | Provider | Max | 特色 | Gate 阈值 | 场景首选 |
|:---|:---|:---|:---|:---:|:---|
| `seedance-2` | ByteDance | 15s / 1080p | 原生音视频联合生成；8+ 语言唇形同步；多镜头叙事；最多 12 参考资产 | **0.65** | **S1 / S5** |
| `kling-3-0/standard` | Kuaishou | 15s / 720p | 多镜头（6 shot）；3 人角色一致性；6+ 语言原生音频；运动控制 | **0.60** | **S3** |
| `kling-3-0/pro` | Kuaishou | 15s / 1080p | Kling 3.0 全部能力 + 增强写实度 | **0.60** | **S2** |
| `kling-3-0/4k` | Kuaishou | 15s / 4K | 4K 原生输出 | 0.60 | 高端 hero shot |
| `sora-2-official` | OpenAI | 4/8/12/16/20s / 1024p | 固定时长档位；同步音频；改进物理引擎 | 0.62 | hero shot 备选 |
| `sora-2-pro-official` | OpenAI | tiers / 1080p | Pro 输出 | 0.62 | 高端短片 |
| `veo-3-1` | Google | **8s** / 4K | lite/fast/high-quality 三档；4K 原生 | **0.58** | 8s 内短片 hero shot（**非长视频**） |
| `runway-gen-4-5` | Runway | 10s / 1080p | 专业运动；可选参考图 | **0.62** | **S2 备选** |
| `wan-2-7-video` | Alibaba | 15s / 1080p | 多镜头；最广宽高比支持；面部运动控制 | **0.55** | S1/S2 降级 |

### 1.2 Mid 档（备选 / 降级）

| Model ID | Provider | Max | 特色 | Gate 阈值 | 用途 |
|:---|:---|:---|:---|:---:|:---|
| `seedance-2-fast` | ByteDance | 15s / 720p | Seedance 2 fast variant，30% 折扣 | **0.65** | S4 快创首选 |
| `seedance-1-5-pro` | ByteDance | 15s / 1080p | Seedance 2 前代 | 0.62 | legacy |
| `kling-o3` / `kling-o3-4k` | Kuaishou | 8s / 1080p~4K | 高语义理解；运动控制 | 0.58 | 短场景 |
| `kling-2-6` | Kuaishou | 10s / 1080p | 2 人角色一致性；原生 CN/EN 音频 | 0.58 | legacy mid |
| `kling-2-5-turbo-pro` | Kuaishou | 10s / 1080p | Turbo 草稿模式；50% 折扣 | **0.55** | **S4 turbo / 草稿** |
| `wan-2-6` | Alibaba | 15s / 1080p | 多镜头序列 | **0.55** | **S3 降级** |
| `wan-2-5` | Alibaba | 3-15s | 灵活时长按秒计费 | 0.55 | 按需 |

### 1.3 Budget 档（最后降级）

| Model ID | Provider | Max | 特色 | Gate 阈值 | 用途 |
|:---|:---|:---|:---|:---:|:---|
| `wan-2-2-fast` | Alibaba | 480p/720p | 极速；40% 折扣 | **0.50** | **S4 budget 降级** |
| `hailuo-2-3` | MiniMax | 10s / 768p~1080p | 可选首帧引导 | 0.55 | 替代 budget 选项 |
| `happy-horse` | Alibaba | 8s / 1080p | 原 default；运动好；参考视频支持 | 0.55 | **已退役** 仅兼容入口 |

---

## 二、图像生成模型

### 2.1 Premium 档

| Model ID | Provider | Max | 特色 | Gate 阈值 | 用途 |
|:---|:---|:---|:---|:---:|:---|
| `gpt-image-2` | OpenAI | 1024² | 优秀提示词理解；图中文本渲染；单图编辑 | **0.65** | **当前 keyframe / thumbnail 默认** |
| `gpt-4o-image` | OpenAI | text/edit | GPT-4 视觉推理 | 0.65 | 高端 keyframe |
| `seedream-5-0-lite` | ByteDance | 1024² | 下一代图像；多参考；改进质量 | 0.62 | Premium 备选 |
| `flux-2` | Black Forest Labs | 1024² | 32B 参数；优秀文字渲染；多参考 | 0.60 | 设计感强的关键帧 |
| `wan-2-7-image-pro` | Alibaba | 可变 | Alibaba 图像旗舰 | 0.60 | 备选 |

### 2.2 Budget 档

| Model ID | Provider | Max | 特色 | Gate 阈值 | 用途 |
|:---|:---|:---|:---|:---:|:---|
| `nano-banana-pro` | Google | 1024² + 4K 同价 | Gemini 3 Pro；多图合成；实时数据 | **0.60** | 4K 关键帧 |
| `nano-banana` | Google | 默认档 | Gemini 2.5 Flash；最低成本 | 0.55 | 缩略图批量 |

---

## 三、按场景的推荐链（与 model_thresholds.py 一致）

| 场景 | 首选 | 备选 | 降级 | 时长能力 |
|:---|:---|:---|:---|:---|
| **S1 商品直拍** | `seedance-2` | `kling-3-0/pro` | `wan-2-7-video` | 15s × 4-6 段 = 60-90s |
| **S2 品牌宣传** | `kling-3-0/pro` | `runway-gen-4-5` | `wan-2-7-video` | 15s × 4 段 = 60s |
| **S3 网红二创** | `kling-3-0/standard` | `seedance-2` | `wan-2-6` | 15s × 2 段 = 30s |
| **S4 直播拍摄** | `seedance-2-fast` | `kling-2-5-turbo-pro` | `wan-2-2-fast` | 10-15s × 6 段 |
| **S5 品牌VLOG** | `seedance-2` | `kling-3-0/pro` | `wan-2-7-video` | 15s × 6 段 = 90s |

---

## 四、Gate Threshold 速查（决策 F 落地）

代码权威源：[`src/pipeline/model_thresholds.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/model_thresholds.py)

```python
from src.pipeline.model_thresholds import get_threshold, is_acceptable

get_threshold("seedance_clips", model_id="seedance-2")   # 0.65
get_threshold("seedance_clips", model_id="wan-2-2-fast") # 0.50
get_threshold("scripts")                                  # 0.60 (LLM-backed)

is_acceptable(0.48, "seedance_clips", model_id="seedance-2")  # False
```

| 模型 tier | Threshold | 含义 |
|:---|:---:|:---|
| Premium video (Seedance 2, gpt-image-2) | **0.65** | 严格门控，低于则不 ★ 推荐 |
| Premium video (Kling 3.0, Runway) | **0.60–0.62** | 标准门控 |
| Mid-tier (Kling 2.x, Wan 2.6) | **0.55–0.58** | 适度容忍 |
| Budget (Wan 2.2 fast, Hailuo) | **0.50** | 降级路径不阻塞 |
| LLM-backed steps (scripts, strategy, ...) | **0.60** | 与模型无关 |

---

## 五、变更日志

| 日期 | 变更 | 影响 |
|:---|:---|:---|
| 2026-05-14 | `POYO_VIDEO_MODEL` 默认值 `happy-horse` → `seedance-2`（Sprint 0 S0-1） | 所有走 poyo 路径的视频生成升级到 15s + 多镜头 |
| 2026-05-14 | `model_thresholds.py` 落地，gate_manager 接入（Sprint 0 S0-3） | Gate 推荐不再无条件 ★，sub-threshold 候选不被推荐 |
| 2026-05-13 | 决策 D 模型约束 = poyo only；决策 F 阈值差异化 | 本文档诞生 |

---

*更新本表流程：(1) poyo 上新模型 → @AIVideoIntel 评估能力 → (2) 加入 `model_thresholds.py` + 本文档 §一/§二 → (3) 路线图 §三 推荐链按需调整。*
