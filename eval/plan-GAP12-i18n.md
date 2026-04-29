# GAP-12: 多语言 i18n 支持（ES/FR/DE）

> **目标：** 让管道能生成英语以外的脚本语言（西班牙语 ES、法语 FR、德语 DE）。
> ES/FR/DE 已在 `Language` enum 中定义，但无翻译数据。策略/脚本/字幕三个节点需要翻译。

---

## 现状分析

| Agent | 当前语言处理 | i18n 依赖度 |
|---|---|---|
| `StrategyAgent` | mock briefs 硬编码 `Language.EN` | 低——brief 是结构化的，用英文写 brief 也 OK |
| `ScriptWriterAgent` | `_SCRIPT_TEMPLATES` 全是英文文案 + `script.id` 硬编码 `-EN` | **高**——voiceover/cta/hashtags 要翻译 |
| `StoryboardAgent` | 从 script segments 继承 | 低——visual 描述保持英文 |
| `CaptionAgent` | 从 script segments 继承 text | 低——字幕文本从 script 继承 |
| `DistributionAgent` | 从 scripts 继承 platform/title | 低——scheduled_time 无语言依赖 |
| `AudioDesignerAgent` | 无 | 无关 |
| `MediaGenerationAgent` | 无 | 无关 |
| `ThumbnailAgent` | 无 | 无关（prompt 可保持英文） |
| `ComplianceAgent` | rules 硬编码中文？需要检查 | **中**——规则语言需适应 |
| `EditorAgent` | 无 | 无关 |

**关键结论：** 80% 的翻译工作集中在 `ScriptWriterAgent` 的 `_SCRIPT_TEMPLATES`。策略 Agent 和合规 Agent 的 mock 数据也需要翻译，但影响面小。

---

## 架构设计

### 翻译策略分层

```
i18n_translate(text, target_lang)
├── 生产模式: LLM 翻译（接现有 llm.invoke_json）
└── 开发模式: MockTranslationService（预置模板）
```

### MockTranslationService

不依赖外部翻译 API，基于语言代码选择预置模板。**核心原则：**
1. 英语 mock 模板直接翻译成 ES/FR/DE 版本
2. 翻译质量要求：自然语言，不是机翻腔
3. 每个语言至少一个完整模板供 E2E 测试

### 文件结构

```
src/agents/
├── prompts/
│   ├── script_writer_en.py       # 已有
│   ├── script_writer_es.py       # 新增——西班牙语 prompt + 模板
│   ├── script_writer_fr.py       # 新增——法语 prompt + 模板
│   ├── script_writer_de.py       # 新增——德语 prompt + 模板
│   ├── strategy_en.py            # 已有
│   ├── strategy_es.py            # 新增
│   ├── strategy_fr.py            # 新增
│   ├── strategy_de.py            # 新增
│   └── __init__.py               # 修改——加 loader
└── i18n.py                       # 新增——翻译服务
```

---

## 实现任务

### Task 1: 创建 `src/agents/i18n.py`

一个轻量的 `I18nService` 类，核心 API：

| 方法 | 功能 |
|---|---|
| `get_prompt(agent_name, lang)` | 返回对应语言版本的提示词模块引用 |
| `translate_script_template(template_id, target_lang)` | 返回该模板的翻译版 |
| `get_translated_templates(target_lang)` | 返回该语言全部的脚本模板字典 |
| `supported_languages()` | 返回当前支持的 languages list |

服务本身使用「字典映射」方式——英文模板预置在 `_SCRIPT_TEMPLATES` 中，各语言版本存储在 `_TRANSLATED_TEMPLATES[lang_code]` 里。

使用方式：
```python
from src.agents.i18n import I18nService
i18n = I18nService()
templates = i18n.get_translated_templates("es")
scripts = self._mock_scripts(briefs, templates_override=templates)
```

### Task 2: 翻译 ES/FR/DE 的 Script 模板（3 个 prompt 文件）

创建 `prompts/script_writer_es.py`、`script_writer_fr.py`、`script_writer_de.py`。

每个文件包含：
- 对应语言的 `SYSTEM_PROMPT`（翻译后的提示词）
- `USER_MESSAGE_TEMPLATE`（翻译后的用户消息模板）
- 3 个核心脚本模板（BRIEF-001, BRIEF-003, BRIEF-005——覆盖 tutorial, product, unboxing）

法国语模板示例（`script_writer_fr.py`）：
```python
SCRIPT_WRITER_SYSTEM_PROMPT_FR = """Vous êtes un copywriter primé spécialisé dans les vidéos courtes..."""
_SCRIPT_TEMPLATES_FR = {
    "BRIEF-001": {
        "hook": "Allaiter au travail ne signifie pas se cacher dans un placard.",
        "hook_visual": "...",
        ...
    },
}
```

**注意：** 完整 5 个模板（BRIEF-001 到 BRIEF-005）的翻译量太大。每个语言翻译 **3 个模板**（001/tutorial, 003/product, 005/unboxing），覆盖多语言 pipeline 测试即可。

### Task 3: 重构 `ScriptWriterAgent` 支持多语言

- `run()` 方法接受 `target_languages: list[str]`（从 state 传入）
- 非 EN 语言时，调用 `I18nService.get_translated_templates(lang)`
- **LLM 模式：** 用对应语言的 system prompt + user message
- **Mock 模式：** 用预置模板，language 字段设为对应 Language 枚举

修改点：
```python
async def run(self, briefs, brand_guidelines, strategy_audit=None, target_languages=None):
```

### Task 4: 测试

**File:** `tests/test_i18n.py` — 12 个测试

| 类 | 测试数 | 覆盖 |
|---|---|---|
| `TestI18nService` | 5 | 获取支持语言、get_prompt、翻译模板存在性、回退到英文 |
| `TestTranslatedScripts` | 4 | ES/FR/DE 至少一个模板存在，voiceover 用对应语言 |
| `TestMultiLangScriptWriter` | 3 | agent 多语言 mock、LLM fallback |

### Task 5: 回归

期望：301 + 12 = 313 passed, 7 skipped

---

## 质量门槛

- [x] ES/FR/DE 各至少 3 个翻译好的脚本模板
- [x] ScriptWriterAgent 支持 `target_languages` 参数
- [x] 不存在的语言 → 回退到英文（例如 `pt` 用 `en`）
- [x] 不改变现有英文行为
- [x] 12 个新测试
- [x] 全回归通过

---

## 不包含的范围（明确不做的）

- ❌ 不翻译 `compliance.py` 规则（维护太复杂，保持英文）
- ❌ 不翻译 `strategy_agent` 的 mock briefs（brief 结构比文案重要）
- ❌ 不翻译 thumbnail prompts（保持英文 prompt 生成）  
- ❌ 不翻译 storyboard/audio/distribution（影响面小）
