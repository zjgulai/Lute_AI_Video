# 双架构大模型 API 分配方案

> 日期：2026-04-29
> 目标：制定两套可切换的架构方案，兼具稳定性、性价比、响应速度

---

## 一、Pipeline 节点全映射

首先明确项目所有 pipeline 步骤与工具的对应关系：

| # | Pipeline 步骤 | Skill | 工具类 | 任务类型 |
|---|---|---|---|---|
| 1 | `strategy` | `product-to-video-strategy` | `LLMClient` | 文本：策略生成 |
| 2 | `scripts` | `script-writer-skill` | `LLMClient` | 文本：脚本生成 |
| 3 | `compliance` | `brand-compliance-skill` | `LLMClient` | 文本：合规检查 |
| 4 | `storyboards` | `storyboard-skill` | `LLMClient` | 文本：故事板 |
| 5 | `keyframe_images` | `keyframe-images` → `gpt-image-generate-skill` | `GPTImageClient` | **图像：关键帧** |
| 6 | `video_prompts` | `video-prompts-skill` | `LLMClient` | 文本：视频提示词 |
| 7 | `thumbnail_prompts` | `thumbnail-prompts-skill` | `LLMClient` | 文本：缩略图提示词 |
| 8 | `seedance_clips` | `seedance-video-generate-skill` | `SeedanceClient` | **视频：片段生成** |
| 9 | `tts_audio` | `elevenlabs-tts-skill` | `ElevenLabsClient` | **语音：旁白生成** |
| 10 | `thumbnail_images` | `gpt-image-generate-skill` | `GPTImageClient` | **图像：缩略图** |
| 11 | `assemble_final` | `remotion-assemble-skill` | Remotion (本地) | 本地：视频组装 |
| 12 | `audit` | `media-quality-audit-skill` | `LLMClient` | 文本：质量审核 |

**关键发现**：
- 文本类节点（1-4, 6-7, 12）已经通过 `LLMClient` 统一路由，当前 `DEFAULT_LLM_PROVIDER=kimi`，**无需改造**
- 需要改造的只有多媒体节点（5, 8, 9, 10）— 图像、视频、语音
- 代码架构已支持多后端（`GPTImageClient` 有 `_poyo_generate` 和 `_openai_generate`；`SeedanceClient` 有 poyo/官方双后端；`ElevenLabsClient` 有 poyo/官方双后端）

---

## 二、架构 A：Kimi + 硅基流动（国内优先）

### 2.1 设计原则
- **国内服务器优先**：最小化网络延迟
- **价格透明**：按量计费，无积分焦虑
- **稳定性优先**：99.9% SLA，自研推理加速

### 2.2 各节点分配

| Pipeline 节点 | 推荐模型 | 规格 | 单价 | 选择理由 |
|---|---|---|---|---|
| **文本全节点** | Kimi K2 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 中文最强，推理深度好，已配置 |
| **关键帧图像** | Kolors | `Kwai-Kolors/Kolors` | ¥0.3/张 | 国内服务器，1秒出图，中文场景优秀 |
| **缩略图图像** | Kolors | `Kwai-Kolors/Kolors` | ¥0.3/张 | 同上 |
| **视频片段** | HunyuanVideo | `tencent/HunyuanVideo` | ~¥1-2/段 | 腾讯开源，国内服务器，速度快 |
| **语音旁白** | CosyVoice | `FunAudioLLM/CosyVoice2-0.5B` | 免费或¥0.1/段 | 100ms响应，中文TTS优秀，部分免费 |
| **图像理解/审核** | Kimi K2 多模态 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 已支持多模态输入 |

### 2.3 成本估算（单条 15 秒视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核（文本） | ~8K tokens | ¥1/百万tokens | ~¥0.01 |
| 关键帧 | 2-3 张 | ¥0.3/张 | ¥0.6-0.9 |
| 视频片段 | 1-2 段 | ~¥1.5/段 | ¥1.5-3 |
| 语音旁白 | 1 段 | 免费/¥0.1 | ¥0-0.1 |
| 缩略图 | 2 张 | ¥0.3/张 | ¥0.6 |
| **合计** | — | — | **~¥2.7-4.7** |

### 2.4 环境变量配置

```bash
# ========== 架构 A: Kimi + 硅基流动 ==========

# --- 文本 LLM（所有文本节点）---
DEFAULT_LLM_PROVIDER=kimi
KIMI_API_KEY=你的KimiKey
KIMI_MODEL=kimi-k2-0905-preview

# --- 多媒体生成（硅基流动）---
SILICONFLOW_API_KEY=你的硅基流动Key
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1

# 图像生成模型选择
IMAGE_MODEL=siliconflow:kolors        # 选项: kolors, flux
# 视频生成模型选择  
VIDEO_MODEL=siliconflow:hunyuanvideo  # 选项: hunyuanvideo, wan
# 语音生成模型选择
TTS_MODEL=siliconflow:cosyvoice       # 选项: cosyvoice

# --- 备选（留空禁用）---
POYO_API_KEY=""
OPENAI_API_KEY=""
SEEDANCE_API_KEY=""
ELEVENLABS_API_KEY=""
```

### 2.5 优劣势

| 优势 | 劣势 |
|---|---|
| ✅ 全部国内服务器，延迟最低 | ⚠️ HunyuanVideo 质量可能不如 Sora/Seedance |
| ✅ 价格透明，按量计费，无积分焦虑 | ⚠️ 需要新增硅基流动客户端适配代码 |
| ✅ 新用户 2000万 Token 免费额度 | ⚠️ 双 Key 管理（Kimi + 硅基流动） |
| ✅ 部分模型永久免费 | |
| ✅ 语音 100ms 极速响应 | |

---

## 三、架构 B：Kimi + poyo（海外精品）

### 3.1 设计原则
- **质量优先**：使用全球顶级的生成模型
- **价格优势**：poyo 比官方直调低 30-80%
- **统一管理**：一个 poyo Key 覆盖所有多媒体

### 3.2 poyo.ai 模型矩阵（精选）

#### 图像生成模型

| 模型 | 价格 | 特点 | 推荐场景 |
|---|---|---|---|
| **GPT-4o Image** | **$0.02/张** ⭐ | OpenAI 原生，文本渲染精准 | **首选** —  cheapest |
| Nano Banana 2 | $0.025/张 | 最便宜，大批量 | 备选 |
| Nano Banana Pro | $0.04/张 | 1K/2K/4K 同价 | 需要高清时 |
| Seedream 5.0 | — | 字节跳动，99%+文字精度 | 需要中文字体时 |
| Kling O3 Image | $0.018/张 | 快手 | 备选 |

#### 视频生成模型

| 模型 | 价格 | 特点 | 推荐场景 |
|---|---|---|---|
| **Wan 2.5** | **$0.15/条** ⭐ | 阿里，中文场景理解好 | **首选** — 性价比 |
| Seedance-2 | $0.10-0.20/条 | 字节跳动，720p/1080p | 需要高质量时 |
| Wan 2.2 Fast | $0.03-0.06/条 | 阿里，极速版 | 快速迭代/测试 |
| Sora 2 | $0.025-0.15/条 | OpenAI，带音频 | 需要品牌感时 |
| Veo 3.1 Fast | $0.05-0.10/条 | Google，物理真实感强 | 需要物理模拟时 |

#### 语音/音乐模型

| 模型 | 特点 | 推荐场景 |
|---|---|---|
| **Suno v5** | 歌词转歌曲，含人声分离 | **首选** — 功能最全 |
| ElevenLabs (via poyo) | 专业 TTS，多语言 | 需要特定音色时 |

### 3.3 各节点分配（优化版）

| Pipeline 节点 | poyo 模型 | 规格 | 单价 | 选择理由 |
|---|---|---|---|---|
| **文本全节点** | Kimi K2 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 中文最强，已配置 |
| **关键帧图像** | **GPT-4o Image** | `gpt-4o-image` | **$0.02/张** | 最便宜+质量高，文本渲染好 |
| **缩略图图像** | **GPT-4o Image** | `gpt-4o-image` | **$0.02/张** | 同上 |
| **视频片段** | **Wan 2.5** | `wan-2.5` | **$0.15/条** | 性价比最高，中文场景好 |
| **语音旁白** | **Suno v5** | `suno-v5` | 积分制 | 功能最全，含人声分离 |
| **图像理解/审核** | Kimi K2 多模态 | `kimi-k2-0905-preview` | ~¥1/百万tokens | 已支持 |

### 3.4 成本估算（单条 15 秒视频）

| 环节 | 用量 | 单价 | 成本 |
|---|---|---|---|
| 策略+脚本+提示词+审核（文本） | ~8K tokens | ~¥1/百万tokens | ~¥0.01 |
| 关键帧 | 2-3 张 | $0.02/张 | ~¥0.12-0.18 |
| 视频片段 | 1-2 段 | $0.15/段 | ~¥1.05-2.10 |
| 语音旁白 | 1 段 | 积分制 | ~¥0.3-0.5 |
| 缩略图 | 2 张 | $0.02/张 | ~¥0.24 |
| **合计** | — | — | **~¥1.7-3.0** |

> 💡 **比架构 A 便宜约 30-40%！** 但前提是 poyo 余额充足。

### 3.5 环境变量配置

```bash
# ========== 架构 B: Kimi + poyo ==========

# --- 文本 LLM（所有文本节点）---
DEFAULT_LLM_PROVIDER=kimi
KIMI_API_KEY=你的KimiKey
KIMI_MODEL=kimi-k2-0905-preview

# --- 多媒体生成（poyo.ai）---
POYO_API_KEY=你的poyoKey
POYO_API_BASE=https://api.poyo.ai

# 图像生成模型选择
IMAGE_MODEL=poyo:gpt-4o-image      # 选项: gpt-4o-image, nano-banana-2, nano-banana-pro, seedream-5
# 视频生成模型选择
VIDEO_MODEL=poyo:wan-2.5           # 选项: wan-2.5, seedance-2, sora-2, veo-3.1-fast
# 语音生成模型选择
TTS_MODEL=poyo:suno-v5             # 选项: suno-v5, elevenlabs

# --- 备选（留空禁用）---
OPENAI_API_KEY=""
SEEDANCE_API_KEY=""
ELEVENLABS_API_KEY=""
SILICONFLOW_API_KEY=""
```

### 3.6 优劣势

| 优势 | 劣势 |
|---|---|
| ✅ 模型质量最高（GPT-4o/Sora/Wan） | ❌ 积分制，余额焦虑 |
| ✅ 价格比官方直调低 30-80% | ❌ 余额耗尽时直接 402 硬失败 |
| ✅ 一个 Key 覆盖所有多媒体 | ❌ 国内访问速度一般 |
| ✅ 成本比架构 A 低 30-40% | ❌ 需要监控余额，及时充值 |
| ✅ 视频模型选择更多（Sora/Veo/Seedance） | |

---

## 四、双架构对比总表

| 维度 | 架构 A：Kimi + 硅基流动 | 架构 B：Kimi + poyo |
|---|---|---|
| **定位** | 国内优先，稳定为王 | 海外精品，质量为王 |
| **图像模型** | Kolors / FLUX | GPT-4o Image |
| **图像单价** | ¥0.3/张 | $0.02/张 (~¥0.14) |
| **视频模型** | HunyuanVideo | Wan 2.5 / Seedance-2 |
| **视频单价** | ~¥1.5/段 | $0.15/段 (~¥1.05) |
| **语音模型** | CosyVoice | Suno v5 |
| **语音单价** | 免费/¥0.1 | 积分制 |
| **单条视频成本** | ~¥2.7-4.7 | ~¥1.7-3.0 |
| **国内延迟** | ✅ 极快（<100ms） | ⚠️ 一般（200-500ms） |
| **稳定性** | ✅ 99.9% SLA | ⚠️ 依赖余额 |
| **免费额度** | ✅ 2000万 Token | ❌ 无 |
| **余额焦虑** | ✅ 无 | ❌ 有 |
| **代码改造量** | 需新增硅基流动客户端 | 无需改造（已有 poyo 支持） |
| **推荐场景** | 生产环境、长期运营 | 演示、测试、追求最高质量 |

---

## 五、切换方案设计

### 5.1 环境变量切换（推荐）

通过统一的环境变量控制架构切换：

```bash
# 切换开关
MEDIA_PROVIDER=siliconflow   # 选项: siliconflow, poyo, official

# 根据开关自动选择模型
IMAGE_MODEL=${MEDIA_PROVIDER}:kolors       # 或 poyo:gpt-4o-image
VIDEO_MODEL=${MEDIA_PROVIDER}:hunyuanvideo # 或 poyo:wan-2.5
TTS_MODEL=${MEDIA_PROVIDER}:cosyvoice      # 或 poyo:suno-v5
```

### 5.2 运行时热切换

在 SettingsPanel 前端增加「多媒体提供商」下拉框：
- 选项 1：硅基流动（国内稳定）
- 选项 2：poyo.ai（海外精品）

切换后写入 `localStorage`，刷新页面生效。

### 5.3 Fallback 策略（高级）

代码层面实现自动 fallback：
```python
# 伪代码
async def generate_image(prompt):
    providers = [PRIMARY_IMAGE_PROVIDER, FALLBACK_IMAGE_PROVIDER]
    for provider in providers:
        try:
            return await provider.generate(prompt)
        except (InsufficientCredits, TimeoutError):
            continue
    # 所有 provider 失败，返回 stub
    return generate_stub_image()
```

---

## 六、实施建议

### 推荐策略：双轨并行

| 阶段 | 动作 | 时间 |
|---|---|---|
| **Phase 0** | 立即给 poyo.ai 充值 ¥50-100，恢复当前服务 | 5分钟 |
| **Phase 1** | 注册硅基流动账号，获取 API Key | 10分钟 |
| **Phase 2** | 我帮你封装硅基流动客户端，适配现有 Skill 接口 | 1-2天 |
| **Phase 3** | 在 SettingsPanel 增加「多媒体提供商」切换开关 | 半天 |
| **Phase 4** | 对比测试两套架构的生成质量和速度 | 1天 |
| **Phase 5** | 根据测试结果，设定默认架构 | 即时 |

### 最终推荐

- **开发/测试阶段**：用架构 B（poyo），成本低，模型质量高
- **生产/演示阶段**：用架构 A（硅基流动），稳定性高，无余额焦虑
- **长期运营**：双轨并行，主走硅基流动，poyo 作为高质量备选

---

*方案制定完成。请确认后进入实施阶段。*
