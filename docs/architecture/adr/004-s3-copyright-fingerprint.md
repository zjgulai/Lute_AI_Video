---
name: adr-004-s3-copyright-fingerprint
description: ADR #004 文档（Accepted: Option D），评估 S3 Influencer Remix 场景下版权指纹预审（Pex / Audible Magic / 自建 Chromaprint+AcoustID / 跳过 4 个方案）的 5 维度对比与推荐路径。决议 2026-05-17 选 Option D（关闭 S3 viral 提取接口），通过 S3_VIRAL_EXTRACT_DISABLED=1 feature flag 实现。当决定 S3 是否引入版权预审、选型商业 vs 自建、估算合规成本时使用。
---

# ADR #004 — S3 Influencer Remix 版权指纹预审选型

| | |
|---|---|
| **状态** | **Accepted: Option D**（2026-05-17 用户决策） |
| **日期** | 2026-05-15（Proposed）→ 2026-05-17（Accepted） |
| **决策者** | 用户 + 工程团队 |
| **影响** | S3 场景流程、合规风险、运营成本、上线时间 |
| **实施** | commit T2 — `S3_VIRAL_EXTRACT_DISABLED=1` env flag (default), `src/pipeline/s3_remix_pipeline.py:_step_video_analysis` early-return + reuse `_soft_degraded` fallback, `tests/test_s3_viral_disabled.py` 3 tests |

## 一、Context

S3 Influencer Remix 场景接受用户提交的 KOL 视频 URL，由 `viral_extractor` skill 提取 viral 片段、`remix_script` 生成新口播、`seedance_clips` 重生成视频，最终发布到 TikTok / Reddit / Amazon。

**版权风险来源**：

- 用户上传的 KOL 原视频可能包含未授权音乐 / 影视片段 / 商标
- 即使生成的是新视频，「重剪 + 引用」可能仍构成衍生作品（Derivative Work）
- 平台（TikTok / YouTube）会用自己的指纹库扫描上传内容，触发 strike / 删帧 / 全量删除
- 累计 strike 会导致账号封禁，影响整个分发渠道

**当前实现**：

S3 流程中 **没有任何版权预审**。`viral_extractor.py` 只做内容质量筛选，不查指纹。所有责任由提交人（用户）承担，平台命中后才知道。

**触发本 ADR 的事件**：

- `2026-05-14-poyo-constrained-optimization-roadmap.md` Sprint 3 P3-6 列出"S3 版权指纹预审接入"为待决项
- `NEXT-STEPS-2026-05-11.md` P2-3 标识为「需要外部 API 选型决策」
- 是 `UNIFIED-ROADMAP-2026-05-15.md` TODO-11 的产出

**约束**：

1. 必须支持音频 + 视频指纹比对（视频指纹优先级低）
2. 必须能在 S3 提交后 30s 内返回结果（不阻塞 viral_extractor）
3. 误报率必须 < 5%（避免误杀合法素材）
4. 漏报率允许 ~10%（指纹是 best-effort，平台还有最后一道）
5. 必须能本地评估而非纯 SaaS（数据隐私）—— 软约束

## 二、4 个方案

### 方案 A — Pex（商业 SaaS）

- **产品**: https://pex.com — Attribution Engine + Discovery API
- **覆盖**: 4B+ 音频指纹 + 50M+ 视频指纹（YouTube / Spotify / SoundCloud / TikTok 全网爬取）
- **接入**: REST API，POST 音频/视频文件 → 返回匹配列表 + ISRC / 版权方
- **成本**: 起步 ~$5,000/月（10K 查询包），$0.5/查询溢价
- **延迟**: 平均 20-40s 一条
- **依赖**: 出海（API 在 us-east-1，国内需走代理或专线）

### 方案 B — Audible Magic（商业 SaaS，行业标准）

- **产品**: https://audiblemagic.com — Content ID 服务
- **覆盖**: 30+ 年最大的音频指纹库（电影 / 电视 / 音乐 / 体育广告）
- **接入**: SDK + REST，C/C++ SDK 可本地跑指纹匹配（reduce SaaS dep）
- **成本**: ~$10,000/月起，按企业合同协商，常年签
- **延迟**: SDK 模式 < 5s；SaaS 30s
- **依赖**: 出海 + SDK 编译进 Python 容器（需要 .so 文件 + 商业 license）

### 方案 C — 自建（Chromaprint + AcoustID + 自维护视频帧指纹）

- **技术栈**:
  - **音频**: [Chromaprint](https://acoustid.org/chromaprint) (LGPL, FFT-based) + [AcoustID](https://acoustid.org/) 公开数据库（音乐为主）
  - **视频**: PySceneDetect 切镜头 + perceptual hash (pHash) 比对
  - **数据库**: 自建商品 / KOL 已知视频指纹库（PG + JSONB / pgvector）
- **成本**: 0 license fee；ECS 一台 4-core 8G 跑 Chromaprint daemon ~¥300/月；存储 ~¥50/月
- **延迟**: 本地化 < 3s
- **依赖**: 完全自主可控，但 AcoustID 数据库主要是音乐，电视 / 影视 / 营销素材覆盖差

### 方案 D — 跳过 / "用户自负"

- 在 S3 提交页加 ToS checkbox：「我确认所提供视频不侵犯第三方版权，否则承担全部责任」
- 不做任何技术预审
- 平台命中后由用户处理 / 删除作品
- **成本**: 0
- **法律风险**: 在某些司法区域（EU AI Act + DSA）平台仍要承担帮助侵权责任，**不能彻底转嫁**

## 三、5 维度评分（1-5 分，5=最佳）

| 维度 | 权重 | A: Pex | B: Audible Magic | C: 自建 Chromaprint | D: 跳过 |
|---|---|---|---|---|---|
| **覆盖率（音视频内容广度）** | 25% | 5 | 5 | 2 | 1 |
| **集成复杂度（含上线时间）** | 20% | 4 | 2 | 2 | 5 |
| **运营成本（年化 TCO）** | 25% | 2 | 1 | 5 | 5 |
| **法律风险缓解** | 20% | 4 | 5 | 3 | 1 |
| **数据隐私 / 国内可用性** | 10% | 2 | 2 | 5 | 5 |
| **加权总分** | — | **3.45** | **3.05** | **3.20** | **3.20** |

> 计算：A = 0.25×5 + 0.20×4 + 0.25×2 + 0.20×4 + 0.10×2 = 3.45
> B = 0.25×5 + 0.20×2 + 0.25×1 + 0.20×5 + 0.10×2 = 3.05
> C = 0.25×2 + 0.20×2 + 0.25×5 + 0.20×3 + 0.10×5 = 3.20
> D = 0.25×1 + 0.20×5 + 0.25×5 + 0.20×1 + 0.10×5 = 3.20

## 四、Recommendation（待用户 sign-off）

工程师视角推荐：**A（Pex）** 走 1 年合同，作为 v0.4.x → v0.5.x 的版权基线方案。理由：

1. 唯一覆盖率 + 法律风险 + 集成复杂度都在前 50% 的方案
2. SaaS 集成 4-6h 即可上线（vs Audible Magic SDK 编译要 1 周）
3. 成本 $5K/月在母婴跨境电商规模下可接受（< 1 单 GMV 的 0.5%）

**但**若以下任一条件成立，应改选 **D（跳过）**：

- 公司预算无法承受 $5K/月固定成本
- 法务认为 ToS 转嫁 + 平台命中处理足够
- S3 实际提交量 < 100/月（指纹成本/单超 $50 不划算）

**坚决反对**：

- **B（Audible Magic）** —— SDK 集成成本 + 年合同 + 出海合规，不适合此规模
- **C（自建）** —— AcoustID 公开数据库对营销素材覆盖率太低，上线后用户会立刻发现"指纹不灵"，反而比不做更糟（False Sense of Security）

## 五、Open Questions（用户必须回答）

1. **预算**：每月愿意为版权指纹付多少？$0 / $500-2000 / $5000+ / $10000+？
2. **法务诉求**：ToS + 平台命中处理是否充分？还是必须做技术预审？
3. **S3 提交量预期**：未来 6 个月日均 / 月均提交多少 KOL 视频？
4. **数据隐私**：用户提交的 KOL 视频是否能上传到第三方 SaaS（Pex / Audible Magic）做指纹？

回答以上 4 题后，本 ADR 可由 `Proposed` 转 `Accepted` 或被新 ADR superseded。

## 六、当前实现

无（S3 流程不做版权预审）。相关代码：

- [src/skills/viral_extractor.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/viral_extractor.py) — viral 片段提取，不查指纹
- [src/skills/remix_script.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remix_script.py) — 重剪脚本生成
- [src/pipeline/s3_remix_pipeline.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/s3_remix_pipeline.py) — 缺少 `_step_copyright_fingerprint` 步骤
- [web/src/app/s3/page.tsx](file:///Users/pray/project/hermes_evo/AI_vedio/web/src/app/s3/page.tsx) — 缺少 ToS checkbox（如果选 D 必加）

## 七、Consequences

### 选 A（Pex）

✅ 覆盖率高 + 上线快 + 法律风险大幅降低
❌ 每月 $5K+ 固定成本 + 出海延迟 / 合规依赖 + 数据隐私非完全自主

### 选 D（跳过）

✅ 0 成本 + 上线 0h + 完全自主
❌ 法律风险全转给用户 + 平台命中后客诉 + 高频用户可能账号被封

### 任何选择共同的下游影响

- S3 pipeline 增加 1 步 `_step_copyright_fingerprint`（在 viral_extractor 之后、remix_script 之前）
- `pipeline_states` 表增加 `copyright_check` JSONB 列（已知匹配列表 + 置信度 + 决策）
- 前端 S3 提交页可能加 ToS checkbox（D 必加，A 可选）
- Gate 1（脚本审核）增加版权预警提示（matches > 0 时显示）

## 八、Rollback Plan

- 选 A：商业合同最短 1 年。若中途解约，回到 D（跳过 + ToS）
- 选 D：随时可升级到 A，所需代码变更最小（只补 1 步）

## 九、相关文档

- 排期计划：[2026-05-14-poyo-constrained-optimization-roadmap.md](file:///Users/pray/project/hermes_evo/AI_vedio/docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md)（Sprint 3 P3-6）
- TODO 总览：[UNIFIED-ROADMAP-2026-05-15.md](file:///Users/pray/project/hermes_evo/AI_vedio/.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md)（TODO-11）
- 风险评估：[five-scenario-pipeline-risk-assessment-stable-20260513.md](file:///Users/pray/project/hermes_evo/AI_vedio/docs/workflows/five-scenario-pipeline-risk-assessment-stable-20260513.md) §COMP-CRIT-1

## 十、决策矩阵速查

```
预算允许 + 法务严格   → A (Pex)
预算紧张 + 法务严格   → B (Audible Magic, SDK 模式)
预算紧张 + 法务宽松   → D (跳过 + ToS)
开源洁癖 + 时间充裕   → C (自建)
```
