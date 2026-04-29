# Layer 5 商业化分发 — GAP 分析

> 基于端到端视频内容工作流文档与 AI_vedio 产品对照

## 五层完成度总览

| 层 | 完成度 | 关键交付 | 关键缺口 |
|----|--------|---------|---------|
| L1 内容策略 | 80% | strategy + Product Context + Data Rules + 3 briefs | 市场本地化(NA/EU)、内容类型参数 |
| L2 叙事设计 | 80% | scripts + storyboard + keyframe_images | 分镜语义化不够结构化 |
| L3 生成控制 | 60% | Seedance锚定 + continuity_chain + quality_gate | 风格一致性管理、多版本变体 |
| L4 工作流工程 | 80% | StepRunner + Gate审批 + 候选评分 + 双模式 | 变量库管理、知识库/RAG |
| L5 商业化分发 | 20% | 仅 mock 连接器 | 真实发布、数据追踪、效果复盘 |

## L5 当前状态

- `src/connectors/tiktok_connector.py` — mock 实现，返回假 post_id
- `src/connectors/shopify_connector.py` — mock 实现
- `src/connectors/registry.py` — 连接器注册表
- `web/src/components/DistributionView.tsx` — 分发面板 UI
- `GET /distribution/platforms` — 返回平台列表
- `POST /distribution/publish` — mock 发布

## L5 目标状态（对照文档）

| 能力 | 文档定义 | 当前 | 差距 |
|------|---------|------|------|
| **平台分发** | 按平台特性重构内容（TikTok短钩子、Meta信息密度高、Pinterest生活方式） | 无平台适配 | 🔴 需要内容+平台匹配逻辑 |
| **投放适配** | 钩子A/B测试、多人群版本、多场景版本 | 无 | 🔴 需要变量化内容变体 |
| **转化漏斗** | 视频→落地页→购买，每层有对应内容 | 无 | 🔴 需要CTA嵌入和追踪 |
| **数据追踪** | 每条视频有投放KPI（CTR/CVR/CPA）和自然流KPI（完播/收藏/互动） | 无 | 🔴 需要数据收集和聚合 |
| **效果复盘** | 按视频类型/平台/市场做结构化复盘，回写到内容策略 | 无 | 🔴 需要复盘→策略回写循环 |
| **商业化分发** | TikTok Shopify YouTube Pinterest Reddit | mock | 🔴 需要真实 API 集成 |

## 对照文档的盲区（已识别）

1. **内容类型矩阵缺失** — 文档定义 4 种内容类型（带货/品牌/知识IP/短剧），当前只有输入驱动的 3 场景
2. **市场本地化缺失** — 文档详细区分 NA/EU 内容调性，当前无市场维度的内容差异
3. **变量库未系统化** — 文档强调变量库是规模化前提，当前字段分散在各处
4. **评估闭环缺失** — 文档定义四层 KPI 体系，当前只有技术质量审计
