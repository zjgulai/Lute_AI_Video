---
name: phase1-signoff-checklist
description: Phase 1 灰度发布 sign-off 决策清单。watchdog 已 42h+ 零告警 + 6 scenario e2e PASS + 19 prod e2e tests + 真实 .mp4 已生成 — 满足启动条件。User 决策开放 S2 + S5 给 ≤10 邀请用户后填写本表。
doc_type: runbook
module: release-management
topic: phase1-grayscale-rollout
status: stable
created: 2026-05-17
updated: 2026-05-17
owner: User (sign-off) + AI (evidence)
related:
  - file: ../../.kiro/plan/MASTER-PLAN-STATUS-2026-05-17.md
    relation: continues-from
---

# Phase 1 灰度发布 — Sign-off Checklist

## 一、启动前置（AI 已交付）

- [x] **生产 v0.2.5+ healthy**: `https://video.lute-tlz-dddd.top/health` 返 200
- [x] **persistence/remotion/media_tools 全绿**: pg_available=true, ffmpeg_ok=true, ytdlp/whisper/clip 全 true
- [x] **watchdog 42h+ 零告警**: 5/15 evening 起 0 alerts
- [x] **真实 e2e .mp4 已生成**: `OVCCX03ISB9N54NF.mp4` (4.8MB) + 多个 portfolio seedance 视频
- [x] **6 scenario non-demo 模式跑通**: Fast Mode + S1-S5 全部 verified
- [x] **19 prod e2e tests + 4 新 spec 38 tests = 总 59 tests** ready
- [x] **/metrics Prometheus endpoint 暴露**: 8 metric families 可见
- [x] **Prometheus alert rules 6 条 + Grafana dashboard 已就位**: deploy/lighthouse/

## 二、待 user 决策

### 2.1 邀请 list（≤10 用户）

User 提供 email + 内部账号绑定方式。建议优先：
- [ ] 公司内部 maternity team 3 人
- [ ] 已合作 KOL 2 人
- [ ] 早期投资人 2 人
- [ ] 团队成员 / 朋友 3 人

### 2.2 开放 scenario 选择

- [ ] **S2 brand_campaign**: 自动化品牌战役（最稳定 — production 测试 progress 0.58 reached）
- [ ] **S5 brand_vlog**: 六视图 VLOG（**注意**：本日发现 `vlog_strategy` 在 `selected_models=["str"]` 输入下 crash — 已本地修复 commit pending，部署后 unblock）

**建议**：先开 S2，**待 vlog_strategy 修复部署后**再开 S5。

### 2.3 流量上限 + 配额

- [ ] **每用户单日 视频数上限**: 建议 5-10
- [ ] **总池单日 视频数上限**: 建议 50（控制 POYO/DeepSeek API cost）
- [ ] **POYO 余额监控阈值**: 余额 < $10 时停服，钉钉告警

### 2.4 反馈渠道

- [ ] 钉钉群：邀请用户进入「AI 视频内测群」
- [ ] 反馈表单：Google Form 或 Lark 表单
- [ ] 紧急联系人：User 本人 + 1 个备用

## 三、user 操作步骤

```
Step 1: 填写本 checklist 第 2 节
Step 2: 在邀请用户的 platform 账号生成专属 API key（4 个 user 各 1 把）
        参见 docs/runbooks/key-rotation.md 的"创建新 key"章节
Step 3: 群发 invitation email + 操作手册（README.md "Quick Start" 章节）
Step 4: 标记本文档 status: "phase1-active" + 注明 launch date
Step 5: 启动 7-day ROI 数据采集 (B3)
```

## 四、监控应急 SOP

灰度期间任何告警触发：
1. **第一时间** 钉钉群 @user
2. SSH 到 host，看 `docker logs ai_video_backend --since 10m`
3. 看 `/telemetry/errors` 最新 100 条
4. 查 `/metrics` 异常 metric family
5. 决策：halt（停服）/ degrade（限流）/ continue（容忍）

完整 incident response 见 [docs/runbooks/](../runbooks/) 5 个 runbook。

## 五、Phase 1 退出 / 升级标准

7 天后启动 B3 ROI 报告。判定 Phase 2 全量开放标准：

- ✅ 100% scenario completion rate（无 fatal error）
- ✅ 平均生成时间 < 15min/video
- ✅ POYO content-policy 拒答率 < 10%
- ✅ User satisfaction (问卷) > 8/10
- ✅ 0 安全事件 / 0 数据泄露
- ✅ 累计成本可承受
