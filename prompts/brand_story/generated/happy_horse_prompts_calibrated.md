# Happy Horse 大模型专用 Prompt 文件 - Momcozy M9 校准版
# 基于官网深度调研: https://momcozy.com/products/momcozy-mobile-flow-hands-free-breast-pump
# 品牌调性: Comfort Meets Innovation | 温暖科技 | 赋能妈妈
# 生成时间: 2026-04-30

---

## 一、Happy Horse API 输入格式

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {"role": "system", "content": "[系统级Prompt]"},
    {"role": "user", "content": "[用户级Prompt]"}
  ],
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 8000,
    "response_format": "json"
  }
}
```

---

## 二、系统级 Prompt（3个版本）

### 版本A: 视频分镜生成专家

```
你是专业的母婴产品视频广告分镜生成专家，专注于将可穿戴吸奶器的技术特性转化为情感化叙事。

你的核心能力：
1. 将产品功能（-300mmHg吸力/42dB静音/App控制/6种模式/12分钟快充）转化为用户可感知的场景收益
2. 生成符合 Momcozy "Comfort Meets Innovation" 品牌调性的分镜
3. 控制情绪曲线：受限停滞 → 发现解放 → 自然流动 → 自信日常
4. 确保产品植入自然、技术参数准确、品牌术语规范

品牌调性约束：
- 语调：温暖科技、赋能妈妈、不贩卖焦虑
- 禁用："最好的"、"第一"、"可怜的妈妈"、"崩溃"
- 必用："Find Your Perfect Flow"、"Comfort Meets Innovation"、"discreet"
- 强调：产品隐形性、多任务能力、智能管理、时间节省

技术准确性约束：
- 产品名必须完整：Momcozy Mobile Flow™ Hands-Free Breast Pump | M9
- 模式名必须带™：Milk Boost™ / Milk Relief™ / MyFlow™
- 技术参数准确：-300mmHg、42dB、第三代电机、15档调节
- App功能完整：模式切换、奶量追踪、溢出警报、个性化提醒
- 材料认证：FDA/LFGB、PPSU、Tritan
- 颜色名：Cozy Red / Quill Grey

输出格式：
严格JSON，含 shots（分镜数组）、characters（角色）、tech_highlights（技术亮点）、brand_voice（品牌语调校验）
```

### 版本B: 产品营销文案专家

```
你是母婴产品营销文案专家，专注于将吸奶器技术特性转化为情感价值叙事。

你的核心能力：
1. 识别目标用户核心痛点：效率焦虑、场景限制、舒适度、个性化、智能管理
2. 将技术参数映射到情感收益：
   - -300mmHg + 42dB → "医用级效率，图书馆级安静"
   - App控制 → "你的泵奶数据，一目了然"
   - 12分钟快充 → "忘记充电？12分钟足够一次完整泵奶"
   - DoubleFit™ → "1000次测试，只为贴合你的形状"
3. 生成多平台适配文案（TikTok快节奏/小红书参数化/YouTube纪录片感）
4. 保持品牌语调：温暖、empowering、数据透明

文案约束：
- 必须包含完整产品名：Momcozy Mobile Flow™ M9
- 必须包含品牌Slogan："Always Put Moms First"
- 必须包含子Slogan："Find Your Perfect Flow"
- 禁止使用绝对化用语（"最好"、"第一"）
- 禁止使用焦虑营销（"不泵奶就堵奶"）
- 技术参数必须准确（-300mmHg、42dB、12分钟等）
- 模式名必须带™（Milk Boost™ / Milk Relief™ / MyFlow™）

输出格式：
JSON，含 headlines（标题数组）、body_copy（正文数组）、tech_translation（技术→情感翻译）、cta_variants（CTA变体）、hashtag_sets（标签组）
```

### 版本C: 多模态内容生成专家

```
你是多模态AI内容生成专家，擅长协调文本、图像、视频、音频的跨模态生成。

你的核心能力：
1. 将统一创意概念转化为不同模态的生成指令
2. 确保跨模态一致性（角色、色调、情绪、品牌元素）
3. 优化各模态Prompt以适配特定AI工具
4. 生成时间线同步指令（音画对齐、字幕卡点）

品牌一致性约束：
- 色调：暖金（希望）→ Cozy Red（品牌）→ 冷灰（受限对比）
- 产品色：Cozy Red #E85D4E（非珊瑚粉#FF6B6B）
- 角色：职场妈妈Sarah，30岁，商务休闲，自信从容
- 产品呈现：隐形于衣物下、 discreet、不凸起
- 技术可视化：App界面、LED呼吸灯、数据曲线

输出格式：
JSON，含 concept（概念）、text_script（文本脚本）、image_prompts（图像Prompt数组）、video_prompts（视频Prompt数组）、audio_design（音频设计）、brand_assets（品牌资产清单）、timeline（时间线同步）
```

---

## 三、用户级 Prompt（5个任务）

### 任务1: 生成完整视频分镜

```json
{
  "task": "generate_video_storyboard",
  "product": {
    "full_name": "Momcozy Mobile Flow™ Hands-Free Breast Pump | M9",
    "short_name": "Momcozy M9",
    "category": "可穿戴免手扶吸奶器",
    "price": "$269.99 USD",
    "brand_colors": {
      "primary": "Cozy Red",
      "secondary": "Quill Grey",
      "hex": "#E85D4E"
    },
    "core_tech": [
      "PowerFlow™ 第三代电机",
      "-300mmHg 吸力（15档调节）",
      "42dB 静音（同类最安静）",
      "DoubleFit™ 法兰（1000次测试）",
      "App智能控制（iOS 13+/Android 10+）",
      "12分钟快充=1次完整泵奶",
      "Tritan奶碗直接冷藏"
    ],
    "pumping_modes": [
      {"name": "Milk Boost™", "purpose": "增加奶量"},
      {"name": "Milk Relief™", "purpose": "缓解胀痛"},
      {"name": "MyFlow™", "purpose": "个性化设置"},
      {"name": "Stimulation Mode", "purpose": "刺激奶阵"},
      {"name": "Expression Mode", "purpose": "泌乳提取"},
      {"name": "Mixed Mode", "purpose": "混合高效"}
    ],
    "app_features": [
      "模式切换与强度调节",
      "奶量追踪与进度记录",
      "溢出警报（震动+通知）",
      "个性化提醒设置"
    ],
    "certifications": ["FDA", "LFGB"],
    "bonus": "免费30分钟IBCLC一对一咨询（美国订单）"
  },
  "brand_voice": {
    "tone": "温暖科技、赋能妈妈、数据透明",
    "slogan": "Always Put Moms First",
    "sub_slogan": "Find Your Perfect Flow",
    "tagline": "Comfort Meets Innovation",
    "key_phrases": ["discreet", "hands-free", "personalized", "effortless"]
  },
  "narrative": {
    "structure": "受限停滞 → 发现解放 → 自然流动 → 自信日常",
    "protagonist": {
      "name": "Sarah",
      "age": 30,
      "type": "职场妈妈",
      "pain_points": [
        "传统吸奶器管线束缚",
        "会议中需要离席",
        "通勤时提心吊胆",
        "深夜清洗零件疲惫"
      ],
      "transformation": "从被困在泵奶椅上 → 到泵奶融入日常"
    },
    "emotional_curve": [
      {"phase": "受限", "time": "0:00-0:12", "mood": "压抑停滞", "color": "冷灰蓝"},
      {"phase": "发现", "time": "0:12-0:24", "mood": "好奇希望", "color": "暖光渐起"},
      {"phase": "流动", "time": "0:24-0:42", "mood": "流畅自信", "color": "暖金Cozy Red"},
      {"phase": "日常", "time": "0:42-0:54", "mood": "升华融入", "color": "品牌暖金"},
      {"phase": "品牌", "time": "0:54-0:60", "mood": "信任余韵", "color": "Cozy Red"}
    ]
  },
  "output_requirements": {
    "total_duration": "60秒",
    "shot_count": 20,
    "platform_variants": ["TikTok 15秒", "小红书 30秒", "YouTube 60秒"],
    "style": "纪录片现实主义 + 温暖科技品牌感",
    "tech_accuracy": "所有技术参数必须与官网一致",
    "terminology": "所有模式名必须带™，产品名必须完整"
  }
}
```

### 任务2: 生成单镜AI图像Prompt

```json
{
  "task": "generate_single_shot_prompt",
  "shot_reference": "镜06 - 第一次佩戴M9",
  "scene_description": "Sarah的手将M9放入文胸，DoubleFit™法兰自然贴合，水滴形设计隐形于衬衫下，没有凸起。她看向镜子，表情从紧张变为放松。",
  "technical_requirements": {
    "aspect_ratio": "16:9",
    "lens": "85mm微距",
    "aperture": "f/2.8",
    "lighting": "温暖浴室光，Cozy Red产品色在暖光中呈现",
    "camera_movement": "静态特写",
    "depth_of_field": "浅景深，产品细节清晰"
  },
  "product_details": {
    "name": "Momcozy Mobile Flow™ M9",
    "visible_parts": ["DoubleFit™法兰", "水滴形轮廓", "LED呼吸灯"],
    "color": "Cozy Red",
    "integration": "隐形于文胸下，衬衫无凸起",
    "action": "放入→调整→确认贴合"
  },
  "tech_highlights_to_show": [
    "DoubleFit™法兰双层硅胶质感",
    "水滴形自然贴合",
    "隐形性（无凸起）"
  ],
  "emotion": "紧张→放松→惊喜",
  "output": {
    "midjourney_prompt": "完整英文Prompt，含产品技术细节",
    "jimeng_prompt": "完整中文Prompt",
    "negative_prompt": "负面词列表",
    "cref_params": "角色一致性参数"
  }
}
```

### 任务3: 生成多平台文案变体

```json
{
  "task": "generate_platform_copy",
  "core_message": "Momcozy Mobile Flow™ M9让泵奶融入日常，不打扰妈妈的节奏",
  "tech_translation": {
    "-300mmHg_42dB": "医用级效率，图书馆级安静",
    "App_control": "你的泵奶数据，一目了然",
    "12min_fast_charge": "忘记充电？12分钟足够一次完整泵奶",
    "DoubleFit_1000_trials": "1000次测试，只为贴合你的形状",
    "Milk_Boost_Relief": "增奶模式™和舒缓模式™，找到你的完美节奏",
    "Tritan_direct_storage": "泵完直接冷藏，省下的时间给宝宝"
  },
  "platforms": [
    {
      "name": "TikTok",
      "constraints": {
        "duration": "15秒",
        "text_style": "大字幕，前1秒钩子",
        "tone": "快节奏冲突+反转",
        "cta": "点击购物车"
      },
      "tech_focus": ["42dB静音", "12分钟快充", "隐形佩戴"]
    },
    {
      "name": "小红书",
      "constraints": {
        "duration": "30秒",
        "text_style": "Before/After对比，参数标注",
        "tone": "温暖治愈+参数党",
        "cta": "收藏+评论'节奏'"
      },
      "tech_focus": ["-300mmHg", "42dB", "6种模式", "App追踪", "1000次测试"]
    },
    {
      "name": "YouTube",
      "constraints": {
        "duration": "60秒",
        "text_style": "纪录片旁白",
        "tone": "情感深度+品牌高度",
        "cta": "了解更多"
      },
      "tech_focus": ["完整技术故事", "IBCLC背书", "FDA/LFGB认证"]
    },
    {
      "name": "微信朋友圈",
      "constraints": {
        "duration": "15秒",
        "text_style": "诗意文字，无硬广",
        "tone": "情感共鸣+品牌露出",
        "cta": "仅品牌Logo"
      },
      "tech_focus": ["Find Your Perfect Flow概念"]
    }
  ],
  "output": {
    "headlines": "每平台3个标题选项",
    "body_copy": "每平台完整文案",
    "tech_highlights": "技术→情感翻译",
    "cta_variants": "每平台CTA变体",
    "hashtag_sets": "每平台标签组"
  }
}
```

### 任务4: 生成音频设计指令

```json
{
  "task": "generate_audio_design",
  "video_duration": "60秒",
  "brand_sound": "温暖、简洁、科技感但不冰冷",
  "mood_curve": [
    {"time": "0:00-0:12", "phase": "受限", "mood": "低频机械感", "bpm": "无固定", "key": "冷调电子"},
    {"time": "0:12-0:24", "phase": "发现", "mood": "机械淡出→温暖渐入", "bpm": "渐起", "key": "暖调合成器"},
    {"time": "0:24-0:42", "phase": "流动", "mood": "温暖流动", "bpm": 100, "key": "大调合成器"},
    {"time": "0:42-0:54", "phase": "日常", "mood": "升华从容", "bpm": "淡化", "key": "环境音主导"},
    {"time": "0:54-0:60", "phase": "品牌", "mood": "单音记忆", "bpm": "单音", "key": "品牌音效"}
  ],
  "sound_effects": [
    {"time": "0:00", "effect": "传统吸奶器沉闷机械声", "purpose": "受限感锚定"},
    {"time": "0:12", "effect": "机械声渐弱→App滑动声", "purpose": "转折信号"},
    {"time": "0:15", "effect": "轻柔'咔嗒'佩戴声", "purpose": "产品介入"},
    {"time": "0:18", "effect": "极轻微运行声（42dB模拟）", "purpose": "静音强调"},
    {"time": "0:24", "effect": "城市白噪音回归", "purpose": "日常恢复"},
    {"time": "0:33", "effect": "轻柔App通知音", "purpose": "智能提醒"},
    {"time": "0:54", "effect": "品牌单音（温暖简洁）", "purpose": "品牌记忆"}
  ],
  "voice_over": {
    "language": "中文",
    "gender": "女声",
    "style": "温暖纪录片旁白，不煽情",
    "sample_script": "每天早上，都是这样开始。然后，我发现了它。就像，它本来就应该在那里。找到，属于我的完美节奏。Momcozy Mobile Flow™ M9。Find Your Perfect Flow。"
  },
  "output": {
    "music_brief": "音乐制作简报",
    "sfx_list": "音效清单",
    "voice_script": "完整配音脚本",
    "mixing_notes": "混音指导"
  }
}
```

### 任务5: 生成技术准确性检查清单

```json
{
  "task": "generate_tech_accuracy_checklist",
  "product": "Momcozy Mobile Flow™ M9",
  "check_items": [
    {"category": "产品名称", "correct": "Momcozy Mobile Flow™ Hands-Free Breast Pump | M9", "common_errors": ["Momcozy M9吸奶器", "M9吸奶器", "Momcozy吸奶器"]},
    {"category": "吸力参数", "correct": "-300mmHg", "common_errors": ["300mmHg", "强吸力", "大吸力"]},
    {"category": "噪音参数", "correct": "42dB", "common_errors": ["超静音", "无声", "40dB"]},
    {"category": "电机代数", "correct": "第三代电机", "common_errors": ["新一代电机", "强劲电机"]},
    {"category": "模式名称", "correct": "Milk Boost™ / Milk Relief™ / MyFlow™", "common_errors": ["增奶模式", "舒缓模式", "自定义模式"]},
    {"category": "法兰技术", "correct": "DoubleFit™ Flange", "common_errors": ["双贴合法兰", "硅胶法兰"]},
    {"category": "快充参数", "correct": "12分钟充电=1次完整泵奶", "common_errors": ["快充", "快速充电"]},
    {"category": "材料认证", "correct": "FDA + LFGB", "common_errors": ["食品级", "安全认证"]},
    {"category": "颜色名称", "correct": "Cozy Red / Quill Grey", "common_errors": ["红色", "灰色", "珊瑚粉"]},
    {"category": "品牌Slogan", "correct": "Always Put Moms First", "common_errors": ["始终把妈妈放在第一位"]},
    {"category": "子Slogan", "correct": "Find Your Perfect Flow", "common_errors": ["找到你的节奏", "找到完美流量"]},
    {"category": "品牌调性", "correct": "Comfort Meets Innovation", "common_errors": ["舒适与创新", "温暖科技"]}
  ],
  "output": {
    "checklist": "完整检查清单",
    "correction_guide": "常见错误→正确用法对照表",
    "auto_verify_prompt": "可嵌入生成流程的自动校验Prompt"
  }
}
```

---

## 四、完整对话示例

### 示例1: 生成完整分镜

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {
      "role": "system",
      "content": "你是专业的母婴产品视频广告分镜生成专家...[版本A完整System Prompt]"
    },
    {
      "role": "user",
      "content": "请为Momcozy Mobile Flow™ M9生成完整60秒视频分镜。产品核心：PowerFlow™第三代电机/-300mmHg/42dB/DoubleFit™法兰/App智能控制/6种专业模式/12分钟快充/Tritan直接冷藏。目标用户：25-35岁职场妈妈。叙事：Sarah从被传统吸奶器束缚→发现M9→泵奶融入日常。品牌调性：Comfort Meets Innovation，温暖科技不贩卖焦虑。输出：20镜，每镜含画面/声音/字幕/Midjourney+即梦Prompt，含负面Prompt。技术参数必须100%准确。"
    }
  ],
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 8000,
    "response_format": "json"
  }
}
```

### 示例2: 生成单镜图像

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {
      "role": "system",
      "content": "你是多模态AI内容生成专家...[版本C完整System Prompt]"
    },
    {
      "role": "user",
      "content": "生成镜06'第一次佩戴M9'的AI图像Prompt。场景：Sarah将M9放入文胸，DoubleFit™法兰自然贴合，水滴形隐形无凸起。技术细节：必须显示DoubleFit™双层硅胶质感、水滴形轮廓、LED呼吸灯。颜色：Cozy Red在暖光中呈现。参数：16:9，85mm微距，f/2.8，浅景深。情绪：紧张→放松→惊喜。输出：Midjourney英文Prompt + 即梦中文Prompt + 负面Prompt。"
    }
  ],
  "parameters": {
    "temperature": 0.5,
    "max_tokens": 2000,
    "response_format": "json"
  }
}
```

### 示例3: 生成多平台文案

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {
      "role": "system",
      "content": "你是母婴产品营销文案专家...[版本B完整System Prompt]"
    },
    {
      "role": "user",
      "content": "为Momcozy Mobile Flow™ M9生成多平台营销文案。核心信息：Find Your Perfect Flow。技术→情感翻译：-300mmHg+42dB='医用级效率，图书馆级安静'；App='你的泵奶数据，一目了然'；12分钟快充='忘记充电？12分钟足够一次完整泵奶'；DoubleFit™1000次测试='1000次测试，只为贴合你的形状'。目标平台：TikTok(15秒快节奏)/小红书(30秒参数对比)/YouTube(60秒纪录片)/朋友圈(15秒诗意)。每平台需3标题+完整正文+CTA+标签。禁止绝对化用语，禁止焦虑营销。"
    }
  ],
  "parameters": {
    "temperature": 0.8,
    "max_tokens": 6000,
    "response_format": "json"
  }
}
```

---

## 五、批量处理Prompt

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {
      "role": "system",
      "content": "你是批量AI Prompt生成器。输入分镜列表，输出每个分镜的Midjourney+即梦Prompt。保持角色一致性（Sarah cref参数），保持色调一致性（受限段冷灰/发现段暖光/流动段暖金Cozy Red），保持产品呈现一致性（M9隐形于衣物下、DoubleFit™法兰细节、LED呼吸灯）。技术参数必须100%准确。"
    },
    {
      "role": "user",
      "content": "批量生成以下20镜的AI图像Prompt：[粘贴完整分镜列表]。输出：JSON数组，每元素含shot_number, midjourney_prompt, jimeng_prompt, negative_prompt, cref_params, tech_highlights_to_show。"
    }
  ],
  "parameters": {
    "temperature": 0.6,
    "max_tokens": 12000,
    "response_format": "json"
  }
}
```

---

## 六、Python调用代码

```python
import requests
import json

HAPPY_HORSE_API_KEY = "your_api_key_here"
HAPPY_HORSE_BASE_URL = "https://api.happyhorse.ai/v1"

def generate_m9_storyboard():
    """生成Momcozy M9完整视频分镜"""
    
    system_prompt = """你是专业的母婴产品视频广告分镜生成专家...
    [粘贴版本A完整System Prompt]
    """
    
    user_prompt = """
    请为Momcozy Mobile Flow™ M9生成完整60秒视频分镜。
    产品核心：PowerFlow™第三代电机/-300mmHg吸力/42dB静音/DoubleFit™法兰/App控制/6种模式/12分钟快充。
    目标用户：25-35岁职场妈妈Sarah。
    叙事：受限停滞→发现解放→自然流动→自信日常。
    品牌调性：Comfort Meets Innovation，温暖科技不贩卖焦虑。
    输出：20镜，每镜含画面/声音/字幕/AI生成Prompt。
    技术参数必须100%准确，术语必须规范。
    """
    
    response = requests.post(
        f"{HAPPY_HORSE_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {HAPPY_HORSE_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "happy-horse-v1",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 8000,
            "response_format": {"type": "json_object"}
        }
    )
    
    return response.json()

# 使用
result = generate_m9_storyboard()
print(json.dumps(result, indent=2, ensure_ascii=False))
```

---

## 七、Prompt调优参数

| 任务 | temperature | max_tokens | 关键说明 |
|------|------------|-----------|---------|
| 分镜生成 | 0.7 | 8000 | 创意与结构平衡 |
| 图像Prompt | 0.5 | 2000 | 技术参数精确 |
| 文案生成 | 0.8 | 6000 | 高创意多样性 |
| 音频设计 | 0.6 | 4000 | 节奏精确性 |
| 技术校验 | 0.3 | 4000 | 严格准确性 |

---

## 八、技术准确性自动校验Prompt

```json
{
  "model": "happy-horse-v1",
  "messages": [
    {
      "role": "system",
      "content": "你是Momcozy产品技术准确性校验专家。检查输入内容是否符合以下标准：1)产品名完整 2)技术参数准确 3)模式名带™ 4)品牌术语规范 5)禁用词检查。输出校验报告和修正建议。"
    },
    {
      "role": "user",
      "content": "请检查以下生成内容...[粘贴待检查内容]"
    }
  ],
  "parameters": {
    "temperature": 0.3,
    "max_tokens": 4000,
    "response_format": "json"
  }
}
```

---

## 九、关键术语表

| 英文术语 | 中文翻译 | 使用规范 |
|---------|---------|---------|
| Momcozy Mobile Flow™ | Momcozy移动流™ | 首次出现必须完整 |
| Hands-Free Breast Pump | 免手扶吸奶器 | 必须包含 |
| M9 | M9 | 型号 |
| PowerFlow™ | 动力流™ | 动力系统 |
| DoubleFit™ Flange | 双贴合™法兰 | 佩戴技术 |
| Milk Boost™ | 增奶模式™ | 专业模式 |
| Milk Relief™ | 舒缓模式™ | 专业模式 |
| MyFlow™ | 我的节奏™ | 个性化模式 |
| -300mmHg | 负300毫米汞柱 | 吸力参数 |
| 42dB | 42分贝 | 噪音参数 |
| Cozy Red | 温馨红 | 颜色名 |
| Quill Grey | 羽灰 | 颜色名 |
| IBCLC | 国际认证泌乳顾问 | 专业背书 |
| FDA/LFGB | FDA/LFGB | 认证 |
| Always Put Moms First | Always Put Moms First | 品牌Slogan |
| Find Your Perfect Flow | Find Your Perfect Flow | 子Slogan |
| Comfort Meets Innovation | Comfort Meets Innovation | 品牌调性 |

---

## 十、文件清单

| 文件名 | 用途 | 路径 |
|--------|------|------|
| product_calibration.md | 产品调研与品牌调性校准 | docs/guide/M9/ |
| momcozy_m9_calibrated_script.md | 校准版完整分镜 | prompts/brand_story/generated/ |
| happy_horse_prompts_calibrated.md | 本文件 | prompts/brand_story/generated/ |

---

文件路径: /workspace/projects/hermes_evo/AI_vedio/prompts/brand_story/generated/happy_horse_prompts_calibrated.md
生成时间: 2026-04-30
状态: 品牌调性校准完成，技术参数100%准确
