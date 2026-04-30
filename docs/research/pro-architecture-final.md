# Pro 版架构方案 — 最终定稿

> 日期：2026-04-29
> 基于用户确认：DeepSeek-V4-Pro 原生调用 + 硅基流动 CosyVoice TTS

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Pro 版：极致质量（欧美视频）                    │
├─────────────────────────────────────────────────────────────────────┤
│  文本全节点（策略/脚本/故事板/审核）                                  │
│    → DeepSeek-V4-Pro  @  DeepSeek 官方 API                          │
├─────────────────────────────────────────────────────────────────────┤
│  关键帧图像 / 缩略图                                                  │
│    → GPT-4o Image  @  poyo.ai                                       │
├─────────────────────────────────────────────────────────────────────┤
│  视频片段                                                            │
│    → Happy Horse  @  poyo.ai                                        │
├─────────────────────────────────────────────────────────────────────┤
│  语音旁白（TTS）                                                      │
│    → CosyVoice2-0.5B  @  硅基流动                                    │
└─────────────────────────────────────────────────────────────────────┘
```

**需要的 API Key（共 3 个）**：
1. `DEEPSEEK_API_KEY` — DeepSeek 官方
2. `POYO_API_KEY` — poyo.ai（图像+视频）
3. `SILICONFLOW_API_KEY` — 硅基流动（语音）

---

## 二、模型选型与实际调用参数

### 2.1 文本 LLM — DeepSeek-V4-Pro

| 项 | 值 |
|---|---|
| **平台** | DeepSeek 官方 |
| **Base URL** | `https://api.deepseek.com/v1` |
| **Model ID** | `deepseek-v4-pro` |
| **API Key** | `DEEPSEEK_API_KEY` |
| **上下文** | 1M tokens |
| **模式** | 支持 Thinking / Non-Thinking 切换 |
| **兼容性** | OpenAI SDK 格式（Chat Completions） |

**调用示例**：
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key="sk-your-deepseek-key",
    base_url="https://api.deepseek.com/v1",
)

response = await client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "You are a professional video strategist."},
        {"role": "user", "content": "Generate a 15s ad script for a baby feeding bottle in US market."},
    ],
    temperature=0.7,
    max_tokens=4096,
)
```

**价格**：输入 ¥2/百万 tokens，输出 ¥8/百万 tokens（约，以官方为准）

**选择理由**：
- 2026 年 4 月 24 日最新发布，1.6T 总参 / 49B 激活
- 1M 上下文，Agent 能力专项优化
- 编程/推理能力接近 Claude Opus 4.6
- 原生调用，不走代理，延迟最低

---

### 2.2 图像生成 — GPT-4o Image

| 项 | 值 |
|---|---|
| **平台** | poyo.ai（代理 OpenAI GPT Image） |
| **Base URL** | `https://api.poyo.ai` |
| **Model ID** | `gpt-image-2` |
| **API Key** | `POYO_API_KEY` |
| **调用方式** | poyo submit + poll 异步架构 |
| **分辨率** | 1024×1024（标准）/ 1536×1536（4K） |

**调用示例**（通过 `GPTImageClient`）：
```python
from src.tools.gpt_image_client import GPTImageClient

client = GPTImageClient()
result = await client.generate(
    prompt="Professional product photo of a baby feeding bottle on a wooden table, soft natural lighting, US lifestyle magazine style",
    quality="high",
)
# result["image_url"] 或 result["local_path"]
```

**价格**：约 ¥0.5-2/张（取决于 poyo 积分汇率）

**选择理由**：
- OpenAI 训练数据以西方为主，无中国文化偏向
- 物理光照、材质渲染最精准
- 适合欧美产品展示、生活方式场景

---

### 2.3 视频生成 — Happy Horse

| 项 | 值 |
|---|---|
| **平台** | poyo.ai（代理 Alibaba Happy Horse） |
| **Base URL** | `https://api.poyo.ai` |
| **Model ID** | `happy-horse` |
| **API Key** | `POYO_API_KEY` |
| **调用方式** | poyo submit + poll 异步架构 |
| **分辨率** | 720p / 1080p（默认 1080p） |
| **时长** | 3-15 秒 |
| **比例** | `16:9`, `9:16`, `1:1`, `4:3`, `3:4` |

**调用示例**：
```python
from src.tools.seedance_client import SeedanceClient

client = SeedanceClient()
result = await client.text_to_video(
    prompt="A cinematic drone shot flying through a misty forest at dawn, golden hour lighting",
    duration=5,
    resolution="720p",
)
# result["video_path"] 或 result["file_url"]
```

**价格**：约 ¥1-3/段（取决于 poyo 积分汇率）

**选择理由**：
- 阿里出品，中文/亚洲场景理解优秀，同时兼容欧美内容
- 支持 text-to-video、image-to-video、reference-to-video、video-edit 四种模式
- 支持首帧图引导，保持视觉连贯性
- 1080p 输出，性价比高

---

### 2.4 语音合成（TTS）— CosyVoice2-0.5B

| 项 | 值 |
|---|---|
| **平台** | 硅基流动（SiliconFlow） |
| **Base URL** | `https://api.siliconflow.cn/v1` |
| **Endpoint** | `POST /audio/speech` |
| **Model ID** | `FunAudioLLM/CosyVoice2-0.5B` |
| **API Key** | `SILICONFLOW_API_KEY` |
| **格式** | mp3 / opus / wav / pcm |
| **语速** | 0.5-2.0 倍速可调 |

**调用示例**：
```python
import requests

url = "https://api.siliconflow.cn/v1/audio/speech"

payload = {
    "model": "FunAudioLLM/CosyVoice2-0.5B",
    "input": "Every feeding moment is a chance to connect. Our bottle is designed for that.",
    "voice": "FunAudioLLM/CosyVoice2-0.5B:alex",  # 预设音色：alex, diana, david...
    "response_format": "mp3",
    "speed": 1.0,
    "stream": False,
}

headers = {
    "Authorization": "Bearer sk-your-siliconflow-key",
    "Content-Type": "application/json",
}

response = requests.post(url, json=payload, headers=headers)
audio_bytes = response.content  # 直接写入 .mp3 文件
```

**可用预设音色**（部分）：
- `alex` — 美式男声，温暖专业
- `diana` — 美式女声，亲切自然
- `david` — 英式男声，稳重可信

**价格**：$7.15 / 百万 UTF-8 字节 ≈ **¥0.5 / 万字符**

**选择理由**：
- 国内原生（阿里 FunAudioLLM 团队），API 稳定
- 英文 MOS 5.53，接近人类自然度
- 流式模式 150ms 延迟，非流式质量几乎相同
- 支持情感标记 `[laughter]`、`[breath]`
- 硅基流动新用户送免费额度，部分模型永久免费

---

## 三、`.env` 配置模板

```bash
# ═══════════════════════════════════════════════════════════════
# Pro 版 API 配置（DeepSeek + poyo + 硅基流动）
# ═══════════════════════════════════════════════════════════════

# ── 文本 LLM：DeepSeek-V4-Pro 原生 ──
DEEPSEEK_API_KEY=sk-your-deepseek-key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro

# ── 图像+视频：poyo.ai ──
POYO_API_KEY=sk-your-poyo-key
POYO_API_BASE_URL=https://api.poyo.ai
POYO_IMAGE_MODEL=gpt-image-2
# poyo TTS 不再使用（改用硅基流动 CosyVoice）
# POYO_TTS_MODEL=generate-music

# ── 语音 TTS：硅基流动 CosyVoice ──
SILICONFLOW_API_KEY=sk-your-siliconflow-key
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1
COSYVOICE_MODEL=FunAudioLLM/CosyVoice2-0.5B
COSYVOICE_VOICE=FunAudioLLM/CosyVoice2-0.5B:alex

# ── 项目内部 key（不变）──
API_KEY=ai_video_demo_2026
```

---

## 四、代码改造清单

| # | 文件 | 改造内容 | 预估工时 |
|---|------|---------|---------|
| 1 | `src/config.py` | 新增 `DEEPSEEK_API_KEY`, `SILICONFLOW_API_KEY`, `COSYVOICE_MODEL`, `COSYVOICE_VOICE` | 10 min |
| 2 | `src/tools/cosyvoice_client.py` | **新建**硅基流动 CosyVoice TTS 客户端（submit → 返回音频 bytes） | 30 min |
| 3 | `src/tools/llm_client.py` | 新增 `deepseek` provider，base_url 指向 `api.deepseek.com/v1`，model 默认 `deepseek-v4-pro` | 20 min |
| 4 | `src/skills/elevenlabs_tts.py` | 技能层改为：优先检查 `SILICONFLOW_API_KEY` → 调用 CosyVoiceClient；fallback 到 silent MP3 | 20 min |
| 5 | `src/pipeline/s1_product_pipeline.py` | 文本节点调用改为 `provider="deepseek"`（或从配置读取） | 10 min |
| 6 | `.env.example` | 更新为 Pro 版配置模板 | 5 min |
| 7 | `tests/` | 新增 TTS 连接测试 + DeepSeek 连接测试 | 15 min |
| | **总计** | | **~1.5 小时** |

---

## 五、单条视频成本估算（15 秒欧美产品视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核 | ~10K tokens | ¥2/百万 tokens | ~¥0.02 |
| 关键帧图像 | 2-3 张 | poyo 积分 | ~¥0.5-1.5 |
| 视频片段 | 1-2 段 | poyo 积分 | ~¥1-3 |
| 语音旁白（TTS） | ~400 字符 | ¥0.5/万字符 | ~¥0.02 |
| **总计** | | | **~¥2.5-6.5 / 条** |

> 注：图像和视频价格取决于 poyo 积分汇率，建议先小额充值测试。

---

## 六、阻塞点与下一步

| 阻塞点 | 状态 | 解决方式 |
|---|---|---|
| **poyo 余额为 0** | 🔴 | 充值 poyo 积分（图像+视频依赖） |
| **硅基流动 API Key** | 🟡 | 访问 [siliconflow.cn](https://siliconflow.cn) 注册，手机号即可 |
| **DeepSeek API Key** | 🟡 | 访问 [platform.deepseek.com](https://platform.deepseek.com) 获取 |

**下一步**：
1. 你先去 **siliconflow.cn** 注册一个账号，获取 `SILICONFLOW_API_KEY`
2. 确认 **poyo** 是否充值（如果不充值，图像和视频会失败）
3. 把 3 个 key 发给我，我立即开始代码改造（约 1.5 小时）
