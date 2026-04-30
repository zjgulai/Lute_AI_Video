---
name: brand-story-workflow
description: |
  品牌故事视频AI制作的完整工作流skill。覆盖从品牌brief到成片的6步方法论：
  概念提炼→脚本结构→分镜生成→视觉锁定→动画制作→品牌安全审核。
  适用于品牌宣传片(brand_campaign)、创始人故事、产品溯源、用户证言等场景。
  核心原则：ingredients-to-video（素材驱动），而非text-to-video（提示词赌博）。
  触发场景：用户提到"品牌故事""品牌宣传片""founder story""product origin""品牌视频""brand video"
version: 1.0.0
---

# 品牌故事视频AI制作工作流

## 核心原则

**Ingredients-to-Video > Text-to-Video**

品牌安全的核心不是生成器的随机性，而是前置控制素材质量。
AI视频生成器（Kling/Runway/Sora）只是最终组装线，质量由输入的"原材料"决定。

---

## 六步工作流

### Step 1: 品牌概念提炼 (Concept Extraction)

**输入**: 品牌brief / 产品资料 / 创始人访谈
**输出**: 3个核心叙事钩子 + 品牌调性关键词

**方法**:
1. 从brief中提取"冲突"——品牌解决什么痛点
2. 找到"情感锚点"——用户与品牌连接的情绪
3. 确定"差异化主张"——一句话说清为什么选你

**输出模板**:
```
品牌: [名称]
核心冲突: [用户痛点]
情感锚点: [情绪关键词]
差异化主张: [一句话]
调性关键词: [3-5个形容词]
目标时长: [15s/30s/60s]
目标平台: [TikTok/YouTube/抖音/小红书]
```

---

### Step 2: 脚本结构生成 (Script Structuring)

**四种经典品牌故事结构**:

| 结构类型 | 适用场景 | 核心公式 | 时长 |
|----------|----------|----------|------|
| 英雄之旅 | 品牌破局故事 | 痛点→探索→转折→胜利 | 60s |
| 创始人故事 | 信任建立 | 初心→困境→坚持→成就 | 30-60s |
| 产品溯源 | 品质背书 | 原料→工艺→匠心→成品 | 30s |
| 用户证言 | 社交证明 | 怀疑→尝试→惊喜→推荐 | 15-30s |

**脚本输出格式**:
```
[场景编号] | [画面描述] | [旁白/对话] | [时长] | [情绪曲线]
```

---

### Step 3: 分镜故事板 (Storyboard Generation)

**关键控制点**:
1. **角色一致性**: 使用2x2 Grid Hack生成角色参考表
2. **场景连贯性**: 每镜必须包含"入画动机→画面主体→出画引导"
3. **品牌元素预埋**: Logo位置、品牌色占比、产品露出时机

**2x2 Grid Hack 方法**:
```
1. 在Ideogram/Midjourney中生成角色4视图（正/侧/背/表情）
2. 使用--cref参数锁定角色特征
3. 生成角色在不同场景中的统一形象
4. 建立角色参考表供后续镜头调用
```

**分镜输出模板**:
```json
{
  "shot_id": "S01",
  "type": "establishing/medium/closeup/detail",
  "description": "画面内容描述",
  "character": "角色动作/表情",
  "product": "产品露出方式",
  "mood": "氛围关键词",
  "transition": "与下镜的衔接方式",
  "reference_prompt": "图生图用的精确prompt"
}
```

---

### Step 4: 视觉风格锁定 (Visual Style Lock)

**品牌视觉三要素**:
1. **色彩系统**: 主色/辅色/点缀色的精确色值 + 画面占比
2. **字体系统**: 标题字体/正文字体/品牌字体（如画面含文字）
3. **构图规则**: 安全区、Logo区、产品焦点区的网格系统

**风格参数模板**:
```json
{
  "style_name": "luxury_minimal",
  "color_palette": {
    "primary": "#1A1A1A",
    "secondary": "#C9A96E",
    "accent": "#FFFFFF",
    "bg_ratio": [0.7, 0.2, 0.1]
  },
  "typography": {
    "title_font": "Noto Serif SC",
    "body_font": "Noto Sans SC",
    "brand_font": "Custom"
  },
  "composition": {
    "safe_zone": "90% center",
    "logo_position": "bottom_right",
    "product_focus": "golden_ratio",
    "depth_of_field": "shallow"
  },
  "lighting": "soft_natural",
  "texture": "matte_premium",
  "motion_style": "slow_cinematic"
}
```

---

### Step 5: 动画制作 (Motion Production)

**图生视频优先级**:
1. 先产出高质量静态图（Midjourney/Flux/即梦）
2. 使用图生视频赋予运动（Kling/Runway/Veo）
3. 控制运动幅度：品牌视频宜"微动"而非"大场面"

**运动控制参数**:
```
- 运镜: pan_left / pan_right / push_in / pull_out / static
- 主体运动: subtle_breathe / slow_rotate / gentle_float
- 时长: 3-5秒/镜（品牌视频不宜单镜过长）
- 情绪节奏: build(积累)→peak(高潮)→release(释放)
```

---

### Step 6: 品牌安全审核 (Brand Guard)

**审核清单**:
- [ ] Logo清晰度与位置合规
- [ ] 品牌色占比不低于10%
- [ ] 产品展示符合广告法（无绝对化用语）
- [ ] 角色形象无文化敏感元素
- [ ] 音乐版权合规
- [ ] 字幕错别字检查
- [ ] 画面无竞品露出

---

## 工具链推荐

| 环节 | 首选工具 | 备选工具 | 成本估算 |
|------|----------|----------|----------|
| 脚本 | Kimi/Claude | GPT-4o | $0.01-0.05/次 |
| 角色设计 | Ideogram | Midjourney | $0.02-0.12/张 |
| 场景图 | 即梦/Flux | Midjourney | $0.02-0.08/张 |
| 图生视频 | Kling 3.0 | Runway/Veo | $0.15-0.50/5s |
| 数字人 | HeyGen | 剪映数字人 | $0.5-2/分钟 |
| 配音 | ElevenLabs | Fish Audio | $0.01-0.05/分钟 |
| 音乐 | Suno v4 | Udio | $0.05-0.20/首 |
| 剪辑 | 剪映AI | CapCut | 免费-$10/月 |

---

## 与AI_vedio流水线集成点

### 现有节点扩展

```python
# strategy_agent.py 新增 brand_story 场景策略
BRAND_STORY_STRATEGIES = {
    "hero_journey": "适用于品牌破局/创新故事，强调冲突与解决",
    "founder_story": "适用于信任建立，强调真实与情感",
    "product_origin": "适用于品质背书，强调工艺与匠心",
    "testimonial": "适用于社交证明，强调转变与推荐"
}

# script_agent.py 新增品牌故事脚本模板
BRAND_STORY_TEMPLATES = {
    "15s_hook": "0-3s钩子→3-12s主体→12-15s CTA",
    "30s_narrative": "0-5s建立→5-20s发展→20-25s高潮→25-30s CTA",
    "60s_epic": "三幕结构，每幕20s，含转折点"
}

# quality_agent.py 新增品牌安全检查
BRAND_GUARD_CHECKS = [
    "logo_visibility",
    "color_compliance", 
    "product_claim_accuracy",
    "cultural_sensitivity"
]
```

### 新增专用节点建议

```
brand_concept_agent    # 从brief提炼品牌叙事钩子
storyboard_agent       # 脚本→分镜→参考图prompt
style_lock_agent       # 品牌资产→视觉约束参数
consistency_agent      # 跨镜头角色/场景一致性校验
brand_guard_agent      # 品牌安全合规审核
```

---

## 常见陷阱与规避

| 陷阱 | 现象 | 规避方法 |
|------|------|----------|
| 提示词赌博 | 反复生成碰运气 | 改用ingredients-to-video，前置控制素材 |
| 角色崩坏 | 跨镜头角色不一致 | 2x2 Grid Hack + 角色参考表锁定 |
| 品牌色漂移 | 画面色调不统一 | 风格参数模板 + 后期LUT统一 |
| 恐怖谷效应 | 数字人过于逼真但不自然 | 控制口型同步精度，避免长镜头 |
| 广告法违规 | 绝对化用语/虚假宣传 | brand_guard_agent审核清单 |

---

## 交付标准

一个合格的品牌故事视频AI制作工作流交付物应包含：

1. **概念文档**: 品牌钩子 + 调性关键词 + 目标平台
2. **脚本表格**: 分镜编号/画面/旁白/时长/情绪曲线
3. **角色参考表**: 4视图角色图 + 特征锁定参数
4. **风格参数文件**: JSON格式的色彩/字体/构图规则
5. **分镜参考图**: 每镜一张高质量静态图
6. **运动参数表**: 每镜的运镜/主体运动/时长
7. **品牌安全报告**: 审核清单通过状态

---

## 版本历史

- v1.0.0 (2026-04-30): 初始版本，覆盖6步工作流 + 4种故事结构 + 工具链