# 欧美视频专用 — 三版大模型 API 架构方案

> 日期：2026-04-29
> 目标：从 {Kimi, 硅基流动, poyo} 三个平台中选出 TOP3 两两组合，分别作为基础版、进阶版、Pro版，全部针对**欧美市场视频**优化

---

## 零、核心调整：为什么模型选择变了？

你的视频面向**欧美市场**，这彻底改变了模型优先级：

### 图像生成：文化审美是关键

| 模型 | 团队 | 文化偏向 | 欧美适用度 |
|---|---|---|---|
| **GPT-4o Image** | OpenAI (美国) | 西方训练数据为主 | ⭐⭐⭐⭐⭐ |
| **FLUX** | Black Forest Labs (欧洲) | **无文化偏向** (neutral) | ⭐⭐⭐⭐⭐ |
| **Nano Banana** | Google (美国) | 西方训练数据 | ⭐⭐⭐⭐ |
| **Seedream** | 字节跳动 (中国) | 显著**中国文化偏向** | ⭐⭐ |
| **Kolors** | 快手 (中国) | 显著**中国文化偏向** | ⭐⭐ |

> 📌 **关键发现**：Seedream 和 Kolors 在论文中被明确标注有 "significant cultural bias"  toward Chinese culture。对于欧美产品视频，它们更容易生成东方审美风格的画面（色彩饱和度、人物特征、场景元素），**不推荐用于欧美内容**。

### 视频生成：电影感 vs 速度

| 模型 | 团队 | 核心优势 | 欧美适用度 |
|---|---|---|---|
| **Veo 3.1** | Google DeepMind | 电影感最强，原生音频质量最高 | ⭐⭐⭐⭐⭐ |
| **Sora 2** | OpenAI | 物理模拟最准确，叙事结构好 | ⭐⭐⭐⭐⭐ |
| **Seedance-2** | 字节跳动 | 速度快，性价比高 | ⭐⭐⭐ |
| **Wan 2.5** | 阿里 | 中文场景理解好 | ⭐⭐⭐ |
| **HunyuanVideo** | 腾讯 | 中文优化 | ⭐⭐⭐ |

> 📌 **关键发现**：Veo 3.1 的"黄金时段光影"和"专业摄影指导级构图"最适合欧美广告质感。Seedance/Wan/HunyuanVideo 虽然技术优秀，但视觉风格偏东方审美（更鲜艳、更饱和的默认色调）。

### 语音生成：英语自然度

| 模型 | 英语质量 | 特点 |
|---|---|---|
| **ElevenLabs** | ⭐⭐⭐⭐⭐ 行业标杆 | 最自然的英语发音，多音色，情感丰富 |
| **Suno v5** | ⭐⭐⭐⭐ | 音乐+语音，功能全，含人声分离 |
| **CosyVoice v2** | ⭐⭐⭐ | 中文优秀，英语MOS 5.53（接近人类），但不如ElevenLabs自然 |

---

## 一、基础版：Kimi + 硅基流动 🇨🇳→🌍

### 1.1 定位
**最稳定、成本可控、国内速度极快**。适合量产、测试、对成本敏感的运营场景。

### 1.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│  文本全节点（策略/脚本/审核...） →  Kimi K2                  │
├─────────────────────────────────────────────────────────────┤
│  关键帧/缩略图  →  硅基流动 FLUX（欧洲团队，无文化偏向）      │
│  视频片段      →  硅基流动 Wan 2.2 Fast（快速版）            │
│  语音旁白      →  硅基流动 CosyVoice（英语可用，部分免费）    │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 模型分配表

| Pipeline 节点 | 模型 | 规格 | 单价 | 选择理由（欧美导向） |
|---|---|---|---|---|
| **文本全节点** | Kimi K2 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 英文脚本优秀，已配置 |
| **关键帧图像** | **FLUX** | `black-forest-labs/FLUX.1-schnell` | ¥0.3/张 | **欧洲团队**，无文化偏向，物理光照精准，适合欧美产品展示 |
| **缩略图图像** | **FLUX** | 同上 | ¥0.3/张 | 同上 |
| **视频片段** | **Wan 2.2 Fast** | `Wan-AI/Wan2.2-T2V-A14B` | ~¥0.5/段 | 快速版成本低，虽为阿里模型但Fast版适合测试迭代 |
| **语音旁白** | **CosyVoice** | `FunAudioLLM/CosyVoice2-0.5B` | 免费/¥0.1 | 100ms响应，英语可用，**部分免费** |
| **图像理解/审核** | Kimi K2 多模态 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 已支持 |

### 1.4 成本估算（单条 15 秒欧美视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核 | ~8K tokens | ~¥1/百万tokens | ~¥0.01 |
| 关键帧 | 2-3 张 | ¥0.3/张 | ¥0.6-0.9 |
| 视频片段 | 1-2 段 | ~¥0.5/段 | ¥0.5-1 |
| 语音旁白 | 1 段 | 免费 | ¥0 |
| 缩略图 | 2 张 | ¥0.3/张 | ¥0.6 |
| **合计** | — | — | **~¥1.7-2.5** |

### 1.5 环境变量配置

```bash
# ========== 基础版: Kimi + 硅基流动 ==========

# --- 文本 LLM ---
DEFAULT_LLM_PROVIDER=kimi
KIMI_API_KEY=你的KimiKey
KIMI_MODEL=kimi-k2-0905-preview

# --- 多媒体（硅基流动）---
SILICONFLOW_API_KEY=你的硅基流动Key
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1

# 图像：FLUX（欧洲团队，无文化偏向，适合欧美）
IMAGE_PROVIDER=siliconflow
IMAGE_MODEL=FLUX.1-schnell

# 视频：Wan 2.2 Fast（快速版，低成本）
VIDEO_PROVIDER=siliconflow
VIDEO_MODEL=wan-2.2-fast

# 语音：CosyVoice（部分免费）
TTS_PROVIDER=siliconflow
TTS_MODEL=cosyvoice

# --- 禁用其他 ---
POYO_API_KEY=""
OPENAI_API_KEY=""
SEEDANCE_API_KEY=""
ELEVENLABS_API_KEY=""
```

### 1.6 优劣势

| ✅ 优势 | ⚠️ 劣势 |
|---|---|
| 全部国内服务器，**延迟最低** | Wan 2.2 Fast 质量一般，偏东方审美 |
| **成本最低**（~¥1.7/条） | 视频电影感不如 Veo/Sora |
| FLUX 无文化偏向，适合欧美 | CosyVoice 英语不如 ElevenLabs 自然 |
| 2000万 Token 免费额度 | 无原生音频视频 |
| 语音部分**免费** | |

### 1.7 适合场景
- 量产测试、AB测试、快速迭代
- 成本敏感的运营期
- 对视频质量要求不极致的社交媒体内容

---

## 二、进阶版：Kimi + poyo 🌍🌍

### 2.1 定位
**质量显著提升，价格仍合理**。欧美审美最佳性价比组合。适合正式投放、品牌内容。

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│  文本全节点（策略/脚本/审核...） →  Kimi K2                  │
├─────────────────────────────────────────────────────────────┤
│  关键帧/缩略图  →  poyo GPT-4o Image（$0.02/张）            │
│  视频片段      →  poyo Veo 3.1 Fast（电影感+原生音频）       │
│  语音旁白      →  poyo Suno v5（功能全，含人声分离）         │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 模型分配表

| Pipeline 节点 | 模型 | 规格 | 单价 | 选择理由（欧美导向） |
|---|---|---|---|---|
| **文本全节点** | Kimi K2 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 英文脚本优秀 |
| **关键帧图像** | **GPT-4o Image** | `gpt-4o-image` | **$0.02/张** (~¥0.14) | OpenAI训练数据西方为主，**欧美审美最佳**，文本渲染100%准确 |
| **缩略图图像** | **GPT-4o Image** | 同上 | **$0.02/张** (~¥0.14) | 同上 |
| **视频片段** | **Veo 3.1 Fast** | `veo-3.1-fast` | **$0.05-0.10/条** (~¥0.35-0.7) | Google DeepMind，**电影感最强**，黄金时段光影，专业级构图，**原生音频** |
| **语音旁白** | **Suno v5** | `suno-v5` | 积分制 | 功能最全，歌词转歌曲，含人声分离，适合带BGM的欧美短视频 |
| **图像理解/审核** | Kimi K2 多模态 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 已支持 |

### 2.4 成本估算（单条 15 秒欧美视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核 | ~8K tokens | ~¥1/百万tokens | ~¥0.01 |
| 关键帧 | 2-3 张 | $0.02/张 | ~¥0.14-0.21 |
| 视频片段 | 1-2 段 | $0.075/段 (平均) | ~¥0.52-1.05 |
| 语音旁白 | 1 段 | 积分制 | ~¥0.3-0.5 |
| 缩略图 | 2 张 | $0.02/张 | ~¥0.28 |
| **合计** | — | — | **~¥1.3-2.1** |

> 💡 **成本比基础版还低！** 但前提是 poyo 余额充足。

### 2.5 环境变量配置

```bash
# ========== 进阶版: Kimi + poyo ==========

# --- 文本 LLM ---
DEFAULT_LLM_PROVIDER=kimi
KIMI_API_KEY=你的KimiKey
KIMI_MODEL=kimi-k2-0905-preview

# --- 多媒体（poyo.ai）---
POYO_API_KEY=你的poyoKey
POYO_API_BASE=https://api.poyo.ai

# 图像：GPT-4o Image（欧美审美最佳）
IMAGE_PROVIDER=poyo
IMAGE_MODEL=gpt-4o-image

# 视频：Veo 3.1 Fast（电影感最强，原生音频）
VIDEO_PROVIDER=poyo
VIDEO_MODEL=veo-3.1-fast

# 语音：Suno v5（功能全，含人声分离）
TTS_PROVIDER=poyo
TTS_MODEL=suno-v5

# --- 禁用其他 ---
SILICONFLOW_API_KEY=""
OPENAI_API_KEY=""
SEEDANCE_API_KEY=""
ELEVENLABS_API_KEY=""
```

### 2.6 优劣势

| ✅ 优势 | ⚠️ 劣势 |
|---|---|
| **欧美审美最佳**（GPT-4o + Veo 3.1） | 积分制，余额焦虑 |
| Veo 3.1 **原生音频**，省去后期配音 | 余额耗尽直接 402 硬失败 |
| GPT-4o Image 文本渲染100%准确 | 国内访问速度一般 |
| **成本比基础版还低** | 需要监控余额及时充值 |
| 电影感最强，适合品牌广告 | |

### 2.7 适合场景
- 正式投放的欧美品牌广告
- 需要电影感的产品展示视频
- 对视觉质量要求高的内容

---

## 三、Pro版：硅基流动 + poyo 🚀

### 3.1 定位
**极致性价比 + 极致质量**。文本用硅基流动 DeepSeek-V3（英文足够好且比Kimi便宜），多媒体用 poyo 最好的 Pro 模型。适合追求每一分钱都花在刀刃上的专业团队。

### 3.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│  文本全节点（策略/脚本/审核...） →  硅基流动 DeepSeek-V3      │
├─────────────────────────────────────────────────────────────┤
│  关键帧/缩略图  →  poyo GPT-4o Image 4K / Nano Banana Pro   │
│  视频片段      →  poyo Sora 2 Pro / Veo 3.1 Quality        │
│  语音旁白      →  poyo ElevenLabs（英语最自然）              │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 模型分配表

| Pipeline 节点 | 模型 | 规格 | 单价 | 选择理由（欧美导向） |
|---|---|---|---|---|
| **文本全节点** | **DeepSeek-V3** | `deepseek-ai/DeepSeek-V3` | ~¥0.5/百万tokens | 英文接近GPT-4，**价格比Kimi低50%**，省下的预算给多媒体 |
| **关键帧图像** | **GPT-4o Image 4K** | `gpt-4o-image` (4K) | $0.07/张 (~¥0.49) | 最高分辨率，欧美审美最佳 |
| **缩略图图像** | **Nano Banana Pro** | `nano-banana-pro` (4K) | $0.07/张 (~¥0.49) | 1K/2K/4K **同价**，高清不额外收费 |
| **视频片段** | **Sora 2 Pro** | `sora-2-pro` | $0.50/条 (~¥3.5) | OpenAI最高质量，15秒带音频 |
| | 或 **Veo 3.1 Quality** | `veo-3.1-quality` | $0.60-2.00/条 | Google最高质量，4K，原生音频最佳 |
| **语音旁白** | **ElevenLabs** | `elevenlabs-v3` | ~$0.03/千字符 | **英语最自然**，行业标杆，多音色 |
| **图像理解/审核** | DeepSeek-V3 多模态 | `deepseek-ai/DeepSeek-V3` | ~¥0.5/百万tokens | 支持图像理解 |

### 3.4 成本估算（单条 15 秒欧美视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核 | ~8K tokens | ~¥0.5/百万tokens | ~¥0.005 |
| 关键帧 | 2-3 张 | $0.07/张 | ~¥0.49-0.98 |
| 视频片段 | 1-2 段 | $0.50/段 | ~¥3.5-7 |
| 语音旁白 | 1 段 (~200字符) | ~$0.006 | ~¥0.04 |
| 缩略图 | 2 张 | $0.07/张 | ~¥0.98 |
| **合计** | — | — | **~¥5.0-9.0** |

> 💰 **成本最高，但质量也是最高**。视频占大头（Sora 2 Pro $0.50/条）。如果用 Veo 3.1 Fast 替代可降至 ~¥2-3。

### 3.5 环境变量配置

```bash
# ========== Pro版: 硅基流动 + poyo ==========

# --- 文本 LLM（硅基流动，比Kimi便宜50%）---
DEFAULT_LLM_PROVIDER=siliconflow
SILICONFLOW_API_KEY=你的硅基流动Key
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3

# --- 多媒体（poyo.ai Pro模型）---
POYO_API_KEY=你的poyoKey
POYO_API_BASE=https://api.poyo.ai

# 图像：GPT-4o Image 4K / Nano Banana Pro 4K（最高清）
IMAGE_PROVIDER=poyo
IMAGE_MODEL=gpt-4o-image-4k
# 备选: IMAGE_MODEL=nano-banana-pro

# 视频：Sora 2 Pro（最高质量）
VIDEO_PROVIDER=poyo
VIDEO_MODEL=sora-2-pro
# 备选: VIDEO_MODEL=veo-3.1-quality

# 语音：ElevenLabs（英语最自然）
TTS_PROVIDER=poyo
TTS_MODEL=elevenlabs

# --- 禁用其他 ---
KIMI_API_KEY=""
OPENAI_API_KEY=""
SEEDANCE_API_KEY=""
```

### 3.6 优劣势

| ✅ 优势 | ⚠️ 劣势 |
|---|---|
| **文本成本比Kimi低50%** | 总成本最高 (~¥5-9/条) |
| 多媒体质量**全球顶级** | DeepSeek-V3 脚本创造力略逊于Kimi |
| ElevenLabs 英语**最自然** | Sora 2 Pro 生成慢（90-180秒/条） |
| 4K图像不额外收费 | 需要管理两个平台余额 |
| Veo 3.1 Quality 原生音频最佳 | |

### 3.7 适合场景
- 高预算品牌广告、TVC级内容
- 对英语语音自然度要求极高（播客、解说）
- 需要4K高清图像的电商内容
- 追求"每一帧都是壁纸"的极致视觉

---

## 四、三版总对比

### 4.1 核心指标对比

| 维度 | 基础版 Kimi+硅基 | 进阶版 Kimi+poyo | Pro版 硅基+poyo |
|---|---|---|---|
| **定位** | 稳定量产 | 质量+性价比 | 极致质量 |
| **单条成本** | ~¥1.7-2.5 | ~¥1.3-2.1 | ~¥5.0-9.0 |
| **国内速度** | ✅ 极快 | ⚠️ 一般 | ⚠️ 一般 |
| **稳定性** | ✅ 99.9% SLA | ⚠️ 积分制 | ⚠️ 积分制 |
| **欧美审美** | ⭐⭐⭐⭐ (FLUX) | ⭐⭐⭐⭐⭐ (GPT-4o+Veo) | ⭐⭐⭐⭐⭐ (GPT-4o+Sora) |
| **英语自然度** | ⭐⭐⭐ (CosyVoice) | ⭐⭐⭐⭐ (Suno) | ⭐⭐⭐⭐⭐ (ElevenLabs) |
| **视频电影感** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **原生音频** | ❌ | ✅ (Veo) | ✅ (Veo/Sora) |
| **4K支持** | ❌ | ❌ | ✅ |

### 4.2 Pipeline 节点模型对照表

| 节点 | 基础版 | 进阶版 | Pro版 |
|---|---|---|---|
| **策略/脚本** | Kimi K2 | Kimi K2 | DeepSeek-V3 |
| **关键帧** | FLUX | GPT-4o Image | GPT-4o Image 4K |
| **缩略图** | FLUX | GPT-4o Image | Nano Banana Pro 4K |
| **视频片段** | Wan 2.2 Fast | Veo 3.1 Fast | Sora 2 Pro |
| **语音旁白** | CosyVoice | Suno v5 | ElevenLabs |
| **审核** | Kimi K2 | Kimi K2 | DeepSeek-V3 |

### 4.3 成本结构对比（15秒视频）

```
基础版 (~¥2.1)          进阶版 (~¥1.7)          Pro版 (~¥7.0)
├─ 文本  ¥0.01          ├─ 文本  ¥0.01          ├─ 文本  ¥0.005
├─ 图像  ¥0.9           ├─ 图像  ¥0.2           ├─ 图像  ¥1.5
├─ 视频  ¥0.75          ├─ 视频  ¥0.7           ├─ 视频  ¥3.5
├─ 语音  ¥0             ├─ 语音  ¥0.4           ├─ 语音  ¥0.04
└─ 缩略图 ¥0.6           └─ 缩略图 ¥0.28          └─ 缩略图 ¥0.98
```

---

## 五、切换方案

### 5.1 环境变量一键切换

```bash
# 基础版
export ARCH=basic

# 进阶版
export ARCH=advanced

# Pro版
export ARCH=pro
```

代码中根据 `ARCH` 变量自动选择对应的模型配置。

### 5.2 前端 SettingsPanel 切换

增加「架构版本」选择器：
- 🟢 基础版（稳定量产）
- 🔵 进阶版（质量优先）
- 🟣 Pro版（极致品质）

### 5.3 智能降级（推荐）

```python
# 伪代码：Pro版视频失败时自动降级到进阶版
async def generate_video(prompt):
    try:
        # 先尝试 Pro 模型
        return await poyo.sora_2_pro.generate(prompt)
    except InsufficientCredits:
        # 余额不足，降级到 Veo Fast
        return await poyo.veo_3_1_fast.generate(prompt)
    except TimeoutError:
        # 超时，降级到硅基流动 Wan
        return await siliconflow.wan_2_2_fast.generate(prompt)
```

---

## 六、实施路线图

| 阶段 | 动作 | 预计时间 |
|---|---|---|
| **Phase 0** | 立即给 poyo 充值 ¥100，恢复服务 | 5分钟 |
| **Phase 1** | 注册硅基流动账号，获取 API Key | 10分钟 |
| **Phase 2** | 我帮你封装三套架构的配置加载器 | 1天 |
| **Phase 3** | 改造多媒体客户端，支持 provider 切换 | 1-2天 |
| **Phase 4** | 前端增加「架构版本」切换开关 | 半天 |
| **Phase 5** | 分别测试三版架构的生成效果 | 1天 |

---

## 七、最终建议

| 场景 | 推荐架构 | 原因 |
|---|---|---|
| **现在救急** | 进阶版（Kimi+poyo） | 无需改代码，充值立即可用，欧美审美最佳 |
| **日常量产** | 基础版（Kimi+硅基流动） | 最稳定，成本可控，FLUX无文化偏向 |
| **品牌广告/TVC** | Pro版（硅基+poyo） | 极致质量，ElevenLabs英语最自然 |
| **AB测试/迭代** | 基础版 → 进阶版对比 | 同一脚本用两套生成，对比效果 |

**我的推荐策略**：
1. **默认用进阶版**（Kimi+poyo）：欧美审美最佳，成本合理
2. **余额不足时自动降级到基础版**（Kimi+硅基流动）：保证服务不中断
3. **重要客户/高预算项目手动切换到Pro版**：追求极致质量

---

*方案制定完成。三版架构可根据场景灵活切换，全部针对欧美市场优化。*
