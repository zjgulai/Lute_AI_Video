# ai-generated-code:215
---
title: Momcozy 英雄之旅 — 深度深化版
structure: hero_journey
brand: Momcozy
duration: 60s
platform: TikTok/抖音/小红书/YouTube/朋友圈
visual_style: warm_lifestyle
version: 2.0.0
---

# Momcozy 英雄之旅 — 深度深化分镜脚本

## 执行摘要

本脚本为Momcozy英雄之旅结构的完整生产级分镜，包含：
- 每镜的精确画面构图（镜头角度、景别、运动）
- AI图生图/图生视频的优化Prompt（适配Kling/Runway/即梦）
- 角色一致性控制方案（2x2 Grid Hack）
- 音频设计（配音、音效、音乐）
- 多平台变体参数

---

## 角色一致性控制

### 主角设定

| 属性 | 描述 |
|------|------|
| **姓名** | Sarah（代称，可替换） |
| **年龄** | 28-32岁 |
| **身份** | 新手妈妈，产后3-6个月 |
| **外貌** | 自然素颜，略带疲惫但真实，中长发，不刻意造型 |
| **服装** | S01-S02: 舒适家居服（灰色/蓝色系）；S04-S05: Momcozy珊瑚粉色系 |
| **关键特征** | 左手无名指婚戒、自然微卷中长发、温和眼神 |

### 2x2 Grid Hack 执行

**步骤1: 生成角色参考表**
```
Character reference sheet for Sarah, 30-year-old new mom, 
4-panel grid: 
- front view: gentle eyes, natural makeup, medium wavy hair, warm smile
- side profile: hair texture, nose shape, jawline
- back view: hair length and style from behind
- close-up expression: tired but loving eyes, authentic emotion
consistent soft lighting, neutral bedroom background,
wearing comfortable grey loungewear, wedding ring on left hand,
realistic photography, documentary style --ar 1:1 --style raw
```

**步骤2: 锁定参数**
- 所有后续镜头必须引用 `--cref [reference_image_url]`
- 服装颜色随情绪变化：冷色调（困境）→ 珊瑚粉（解放）
- 发型保持一致，仅随场景微调（居家松散→外出整理）

---

## S01 | 痛点共鸣 | 0-5s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 特写（胸部以上） |
| **角度** | 平视，略低于眼平线（增强脆弱感） |
| **构图** | 三分法，面部在右侧1/3线，左侧留白给窗户冷光 |
| **深度** | f/1.8，面部清晰，背景完全虚化 |
| **运动** | 静态镜头，仅妈妈眨眼和轻微呼吸 |
| **灯光** | 月光/路灯冷光从左侧窗户进入，右侧暗部 |
| **色调** | 色温6500K，偏蓝，饱和度-20% |

### 场景细节
- **环境**：主卧，凌晨3:15，床头柜数字闹钟显示"3:15 AM"
- **道具**：笨重吸奶器（传统款式，带管线和电源适配器）、皱巴巴的纸巾、半杯冷水
- **声音**：吸奶器嗡嗡声（约60dB）、远处空调低频声

### AI生成Prompt

**图生图（Midjourney/即梦）:**
```
Cinematic close-up portrait of exhausted new mother at 3am, 
sitting on bed edge, bulky traditional breast pump with tubes and 
power adapter on nightstand, digital alarm clock showing 3:15 AM, 
crumpled tissues and half-empty water glass nearby, 
cold blue moonlight from window left side, right side in shadow, 
shallow depth of field f/1.8, face sharp background blurred, 
empty eyes looking out window, muted desaturated color palette, 
documentary photography style, authentic and raw, 
--ar 9:16 --style raw --cref [character_ref_url]
```

**图生视频（Kling/Runway）:**
```
Static camera, subtle breathing motion, eyes blinking slowly, 
cold blue light flickering slightly from window, 
breast pump machine humming with slight vibration, 
very slow push-in 5% over 5 seconds, 
maintain documentary realism, no fast movement
```

**即梦中文Prompt:**
```
纪录片风格特写，疲惫的新手妈妈凌晨3点坐在床边，床头柜上有笨重的传统吸奶器和管线，数字闹钟显示3:15，冷蓝色月光从窗户照入，面部清晰背景虚化，眼神空洞望向窗外，真实 raw 风格，9:16竖屏
```

---

## S02 | 探索尝试 | 5-15s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 中景到特写混合 |
| **角度** | 手持镜头，轻微晃动 |
| **构图** | 中心构图，混乱感 |
| **深度** | f/4，环境信息保留 |
| **运动** | 快速剪辑，每镜2-3秒 |
| **灯光** | 混合光源（室内暖光+卫生间冷光+室外日光） |
| **色调** | 色温不统一，强调混乱感 |

### 4镜蒙太奇序列

#### S02-A | 枕头支撑 | 5-7s
**画面**: 妈妈在床上用枕头堆支撑笨重吸奶器，姿势别扭，管线缠绕
**Prompt**:
```
Medium shot of mother awkwardly propping bulky breast pump 
with multiple pillows in bed, tubes tangled around her arms, 
uncomfortable twisted posture, warm bedroom lighting mixed with 
cold device screen glow, frustrated expression, handheld camera 
feel with slight shake, documentary style --ar 9:16 --style raw
```

#### S02-B | 卫生间困境 | 7-9s
**画面**: 狭小卫生间，妈妈坐在马桶盖上使用吸奶器，尴尬而匆忙
**Prompt**:
```
Tight shot in small bathroom, mother sitting on toilet lid 
using breast pump, embarrassed expression, looking at door 
 nervously, cold fluorescent lighting, confined space feeling, 
reflection in mirror showing awkward posture, gritty realism, 
handheld camera --ar 9:16 --style raw
```

#### S02-C | 噪音惊醒 | 9-12s
**画面**: 吸奶器噪音突然变大，宝宝在床上扭动要醒，妈妈慌乱关机器
**Prompt**:
```
Close-up of baby crib, baby stirring awake from noise, 
mother's panicked hands rushing to turn off pump, 
motion blur on hands, dramatic lighting change as device 
screen goes dark, tension and anxiety, handheld chaos --ar 9:16 --style raw
```

#### S02-D | 出门负担 | 12-15s
**画面**: 妈妈出门，背着巨大的母婴包，包口露出吸奶器管线，表情疲惫
**Prompt**:
```
Medium shot mother leaving house carrying oversized diaper bag 
with pump tubes sticking out, exhausted expression, bright 
daylight contrasting with her fatigue, heavy bag pulling her 
shoulder down, urban background blurred, documentary style --ar 9:16 --style raw
```

### 剪辑节奏
- 每镜2.5秒，硬切衔接
- 音效：环境音突变（卧室→卫生间→卧室→街道）
- 音乐：低频紧张弦乐，节奏加快

---

## S03 | 转折发现 | 15-25s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 特写（面部+手机屏幕） |
| **角度** | 45度俯视（模拟自拍视角） |
| **构图** | 面部占2/3，手机占1/3右下角 |
| **深度** | f/2.8，面部和手机都清晰 |
| **运动** | 缓慢推入，从面部到手机屏幕 |
| **灯光** | 手机屏幕光+环境光渐变 |
| **色调** | 从冷6500K渐变到暖4500K |

### 光线变化设计
```
0%  : 冷蓝环境光，面部阴影明显
25% : 手机屏幕亮起，冷白光
50% : Momcozy视频出现，暖光开始渗透
75% : 面部被暖金光照亮
100%: 珊瑚粉色光晕出现，希望感
```

### AI生成Prompt

**图生图:**
```
Close-up of mother's face illuminated by phone screen, 
scrolling social media, Momcozy wearable breast pump video 
appearing on screen, eyes shifting from numb exhaustion to 
curious surprise to hopeful brightness, 
lighting transitioning from cold blue 6500K to warm golden 4500K, 
coral pink light accent gradually appearing on face edges, 
cinematic lighting change, shallow depth f/2.8, 
sense of discovery and hope, documentary style --ar 9:16 --style raw
```

**图生视频:**
```
Slow push-in from face to phone screen over 10 seconds, 
screen content changing from social feed to Momcozy video, 
mother's eyes tracking content, pupil dilation subtle, 
lighting gradient from cold to warm synchronized with content, 
very smooth camera movement, no shake
```

---

## S04 | 品牌解决 | 25-40s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 中景到特写混合 |
| **角度** | 平视或略低（赋权感） |
| **构图** | 黄金分割，妈妈在左/右1/3，环境展示 |
| **深度** | f/2.8-f/4，产品清晰，环境柔和 |
| **运动** | 稳定器平滑运动，慢速跟拍 |
| **灯光** | 自然光为主，珊瑚粉环境光点缀 |
| **色调** | 色温4500K，暖调，饱和度+10% |

### 4镜生活方式蒙太奇

#### S04-A | 厨房自由 | 25-30s
**画面**: 妈妈在开放式厨房做饭，Momcozy可穿戴吸奶器自然贴合在内衣里，她自如地切菜、炒菜，偶尔微笑看婴儿监视器里的宝宝
**Prompt**:
```
Medium shot of mother cooking in modern open kitchen, 
Momcozy wearable breast pump discreetly fitting inside bra, 
natural hand movements chopping vegetables and stirring, 
occasional warm smile checking baby monitor, 
bright natural window light from right, coral pink ambient 
lighting from kitchen pendant lights, warm lifestyle photography, 
smooth stabilizer movement following her actions --ar 9:16 --style raw
```

#### S04-B | 公园散步 | 30-34s
**画面**: 妈妈在公园小径散步，穿着休闲，吸奶器完全隐形，她深呼吸享受阳光，推婴儿车或抱着宝宝
**Prompt**:
```
Full shot mother walking in sunny park path, wearing casual 
comfortable coral pink outfit, Momcozy pump completely invisible 
under clothing, deep breath enjoying sunshine, pushing stroller 
or carrying baby, dappled sunlight through trees, fresh green 
environment, sense of freedom and nature, warm natural lighting, 
lifestyle documentary style --ar 9:16 --style raw
```

#### S04-C | 办公从容 | 34-37s
**画面**: 妈妈在家庭办公区或咖啡厅工作，笔记本电脑前，专注而从容，吸奶器安静运行，咖啡杯旁边
**Prompt**:
```
Medium shot mother working at laptop in home office or cafe, 
focused and composed expression, Momcozy pump operating silently, 
coffee cup and notebook on desk, soft natural light from window, 
coral pink accent in stationery or wall art, professional yet 
relaxed atmosphere, smooth camera movement, lifestyle photography --ar 9:16 --style raw
```

#### S04-D | 静音守护 | 37-40s
**画面**: 夜晚，宝宝安睡，妈妈躺在床上使用Momcozy，静音运行，她温柔地看着宝宝，只有小夜灯微光
**Prompt**:
```
Tender night scene, baby sleeping peacefully in crib, 
mother lying in bed using Momcozy pump with zero noise, 
gentle loving gaze at baby, warm dim night light 2700K, 
soft shadows, intimate and peaceful atmosphere, 
silent operation implied through visual calm, 
coral pink glow from device indicator subtle, 
lifestyle documentary --ar 9:16 --style raw
```

### 产品特写插入（可选）
在S04-A到S04-D之间插入2秒产品hero shot:
```
Extreme close-up of Momcozy wearable pump, showing compact 
design, soft silicone texture, LED indicator in coral pink, 
macro lens detail, premium material visible, clean background, 
product photography style --ar 9:16 --style raw
```

---

## S05 | 胜利蜕变 | 40-55s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 中景到全景 |
| **角度** | 略低平视（hero shot） |
| **构图** | 中心构图，黄金分割 |
| **深度** | f/4-f/5.6，全景清晰 |
| **运动** | 稳定器环绕或缓慢推入 |
| **灯光** | 黄金时段自然光（日出/日落） |
| **色调** | 色温4000K，暖金调，饱和度+15% |

### 3镜蜕变序列

#### S05-A | 阳光微笑 | 40-45s
**画面**: 妈妈抱着宝宝在户外阳光下， genuine smile，宝宝也笑，互动温馨，背景是公园或花园
**Prompt**:
```
Beautiful medium shot of transformed mother holding baby 
in golden hour sunlight, both with genuine joyful smiles, 
interactive tender moment, mother wearing coral pink Momcozy 
branded dress or accessory, lush green garden background, 
bright warm natural lighting 4000K, sun flare subtle, 
hero shot composition, sense of happiness and freedom, 
lifestyle photography --ar 9:16 --style raw
```

#### S05-B | 朋友聚会 | 45-50s
**画面**: 妈妈与朋友们在咖啡厅/餐厅聚会，她自如地参与对话，不再焦虑地看时间或找哺乳室，自信而放松
**Prompt**:
```
Medium shot of mother gathering with friends at cafe, 
confidently engaged in conversation, no anxiety about time 
or nursing room, relaxed posture, friends laughing around her, 
coral pink elements in scene decor or her outfit, warm ambient 
lighting, sense of community and belonging, lifestyle documentary --ar 9:16 --style raw
```

#### S05-C | 工作专注 | 50-55s
**画面**: 妈妈在现代办公环境或家庭办公室，专注工作，偶尔看宝宝照片微笑，专业而从容
**Prompt**:
```
Medium shot mother focusing on work at modern desk, 
professional and composed, occasional warm smile looking at 
baby photo on desk, Momcozy pump discreetly operating, 
clean modern office environment, bright natural light, 
coral pink accent in office supplies or artwork, 
sense of empowerment and balance, smooth camera movement --ar 9:16 --style raw
```

---

## S06 | 品牌收尾 | 55-60s

### 画面深化

| 项目 | 精确描述 |
|------|----------|
| **景别** | 全景到特写 |
| **角度** | 正面平视 |
| **构图** | 中心对称，极简 |
| **深度** | f/8，全部清晰 |
| **运动** | Logo微缩放，文字淡入 |
| **灯光** | 均匀柔光，无阴影 |
| **色调** | 珊瑚粉色渐变，品牌标准色 |

### 动态设计
```
55.0s: 纯色背景淡入（珊瑚粉渐变）
55.5s: Momcozy logo从中心缩放进入（ease-out）
56.0s: "Always Put Moms First"文字逐字淡入
57.0s: "Chosen by 5 Million Moms"小字从底部滑入
58.0s: CTA按钮"Shop Now"/"了解更多"出现
59.0s:  subtle particle effects（光点飘动）
60.0s: 定格
```

### AI生成Prompt

**图生图（收尾帧）:**
```
Minimalist brand closing frame, Momcozy logo centered and prominent, 
coral pink gradient background from #FF6B8A to #FFB8C9, 
clean modern typography "Always Put Moms First" below logo, 
subtle particle effects of soft light dots floating, 
social proof text "Chosen by 5 Million Moms" at bottom, 
elegant and memorable composition, premium finish, 
brand guideline compliant, 9:16 vertical format --ar 9:16 --style raw
```

**动态元素（视频）:**
```
Logo scale from 80% to 100% with ease-out over 2 seconds, 
text fade-in staggered 0.3s intervals, 
particle effects gentle floating upward, 
gradient background subtle breathing animation, 
overall calm and premium motion
```

---

## 音频设计

### 配音脚本

| 时段 | 旁白 | 情绪指导 |
|------|------|----------|
| 0-5s | "凌晨3点，又一次..." | 疲惫、低语、缓慢 |
| 5-15s | "试过各种方法，但总是被困住..." | 无奈、加速、紧张 |
| 15-25s | "直到那一天，我看到了不一样的可能..." | 希望、明亮、转折 |
| 25-40s | "原来，哺乳可以这么自由。wearable, silent, 随时随地..." | 惊喜、轻快、解放 |
| 40-55s | "不只是解决了吸奶的问题，更是找回了做自己的自由。" | 自豪、温暖、坚定 |
| 55-60s | "Momcozy | Always Put Moms First | 加入我们" | 邀请、温暖、行动 |

### 音乐情绪板

| 段落 | 音乐风格 | 参考曲目 |
|------|----------|----------|
| S01 | 极简钢琴单音，低频 | Ólafur Arnalds - Near Light |
| S02 | 紧张弦乐，节奏加快 | Hans Zimmer - Time (紧张段落) |
| S03 | 弦乐渐强，希望出现 | Explosions in the Sky - Your Hand in Mine |
| S04 | 轻快原声吉他，温暖 | Jack Johnson - Better Together |
| S05 | 史诗感但温暖，升华 | Coldplay - Fix You (高潮段落) |
| S06 | 品牌音效，简洁收尾 | Apple 广告风格音效 |

### 音效设计

| 时点 | 音效 | 作用 |
|------|------|------|
| 0s | 低频嗡嗡声（吸奶器） | 建立压抑氛围 |
| 5s | 快速切换的环境音 | 强调混乱 |
| 15s | 手机通知声→音乐转折 | 希望信号 |
| 25s | 环境音变温暖（厨房/公园） | 解放感 |
| 40s | 宝宝笑声/鸟鸣 | 幸福感 |
| 55s | 品牌音效标识 | 记忆点 |

---

## 多平台变体参数

### TikTok/抖音 15s极速版

```yaml
structure:
  S01: 3s  # 凌晨3点痛点
  S03: 3s  # 发现Momcozy
  S04: 5s  # 自由场景（仅厨房+公园）
  S06: 4s  # 品牌+CTA

editing:
  pace: fast_cut  # 每镜硬切
  text: large_bold  # 大字幕
  music: trending  # 热门BGM
  effects: quick_zoom  # 快速缩放

adjustments:
  - 前1秒必须出现"凌晨3点"画面
  - 加#解放双手 #哺乳期 #新手妈妈 标签
  - CTA: "点击购物车"
```

### 小红书 30s种草版

```yaml
structure:
  S01: 5s  # 痛点共鸣
  S02: 5s  # 探索（仅2镜）
  S03: 5s  # 转折
  S04: 10s # 解决（详细展示）
  S06: 5s  # 收尾

editing:
  pace: medium
  text: annotated  # 注解式文字
  music: warm_lifestyle
  effects: before_after  # 前后对比

adjustments:
  - 增加"Before/After"对比标签
  - 加#哺乳期好物 #吸奶器推荐 #Momcozy
  - 结尾引导收藏+评论"想要链接"
  - 产品特写增加参数标注（静音/可穿戴/APP控制）
```

### YouTube 60s纪录片版

```yaml
structure:
  S01: 8s   # 延长痛点
  S02: 12s  # 完整4镜蒙太奇
  S03: 10s  # 延长转折
  S04: 15s  # 完整4镜+产品特写
  S05: 12s  # 完整3镜蜕变
  S06: 5s   # 品牌收尾

editing:
  pace: cinematic
  text: minimal  # 极少文字
  music: full_orchestral  # 完整配乐
  effects: smooth_transition  # 流畅转场

adjustments:
  - 增加真实用户访谈片段（可穿插）
  - 产品功能细节展示（APP界面、穿戴方式）
  - 结尾增加"了解更多"卡片
  - 可扩展为3-5分钟品牌纪录片
```

### 微信朋友圈 15s情感版

```yaml
structure:
  S01: 4s  # 痛点
  S04: 6s  # 解决（仅夜晚静音场景）
  S05: 3s  # 微笑
  S06: 2s  # 品牌

editing:
  pace: gentle
  text: poetic  # 诗意文字
  music: soft_piano
  effects: slow_fade  # 缓慢淡入淡出

adjustments:
  - 弱化CTA，强调情感共鸣
  - 文字:"每个妈妈，都值得被温柔对待"
  - 无硬广感，适合朋友圈传播
  - 结尾仅品牌logo，无购买链接
```

---

## 生产执行清单

### 阶段1: 静态图生成（每镜1-3张参考图）

| 镜号 | 工具 | 数量 | 优先级 |
|------|------|------|--------|
| S01 | Midjourney/即梦 | 3张 | P0 |
| S02-A~D | Midjourney/即梦 | 4张 | P0 |
| S03 | Midjourney/即梦 | 3张 | P0 |
| S04-A~D | Midjourney/即梦 | 4张 | P0 |
| S05-A~C | Midjourney/即梦 | 3张 | P0 |
| S06 | Midjourney/即梦 | 2张 | P1 |

### 阶段2: 图生视频（每镜5-10秒）

| 镜号 | 工具 | 参数 |
|------|------|------|
| S01 | Kling 3.0 | 微动，呼吸感，5s |
| S02 | Kling 3.0 | 快速剪辑，10s |
| S03 | Kling 3.0 | 光线渐变，10s |
| S04 | Kling 3.0 | 生活方式运动，15s |
| S05 | Kling 3.0 | 慢速环绕，15s |
| S06 | Runway/After Effects | 动态图形，5s |

### 阶段3: 后期合成

- **剪辑**: 剪映专业版 / Premiere Pro
- **调色**: 统一为warm lifestyle色调（S01-S02冷调除外）
- **字幕**: 动态字幕，平台适配
- **音效**: 分层混音（环境音+音乐+旁白+音效）
- **品牌元素**: Logo动画、品牌色校正

---

## 品牌安全最终检查

- [ ] 无医疗效果承诺
- [ ] 无绝对化用语
- [ ] 500万用户数据有依据
- [ ] 用户形象真实自然
- [ ] 产品展示符合实际功能
- [ ] 音乐版权合规
- [ ] 所有AI生成素材无侵权
- [ ] 多平台适配合规（各平台广告政策）

---

*本深化版脚本可直接投入AI视频生产工作流，覆盖从概念到成片的完整执行路径。*