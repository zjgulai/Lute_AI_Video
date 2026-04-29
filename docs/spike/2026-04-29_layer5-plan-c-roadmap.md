# Layer 5 方案 C — 数据飞轮自动回写策略（路线图）

> 状态：已设计，待方案 B 数据积累后启动
> 预估：方案 B 上线 + 积累 30-50 条视频数据后可行

## 核心逻辑

系统根据历史视频的效果数据，在 strategy 生成时自动加权推荐：

```
历史数据 → 效果归因 → 策略偏好 → 下一条视频的 generation

例如:
- 过去 10 条视频中，"Pain Point" hook 类型平均完播率 72%，"Data Drop" 仅 38%
  → strategy prompt 中加入: "Prefer Pain Point or Scene Drop hooks. Avoid Data Drop."
- "新手妈妈" 人群的 CTR 比 "双职工家庭" 高 40%
  → strategy prompt 中加入: "Target first-time moms as primary audience"
- 30s 视频的 CVR 比 60s 高 25%
  → strategy prompt 中加入: "Prefer 30s duration for this product"
```

## 关键模块

1. **效果归因引擎** — 按 hook 类型、目标人群、视频时长、平台等多维切片分析
2. **策略偏好生成器** — 将归因结果转为自然语言指令，注入 strategy prompt
3. **A/B 测试调度** — 自动分配 20% 流量做对照测试，验证归因假设
4. **置信度门控** — 样本量不足时不自动回写，仅建议
