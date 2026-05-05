---
title: 婴儿暖奶器品类 — 前后端联调测试计划
doc_type: workflow
module: test
topic: baby-bottle-warmer-e2e
status: stable
created: 2026-05-06
updated: 2026-05-06
owner: self
source: human+ai
---

## 1. 测试目标

以**婴儿暖奶器(Baby Bottle Warmer)**为真实品类案例,验证 P0 三场景在 Lighthouse 生产环境的端到端可用性。覆盖从前端表单输入到后端 pipeline 执行、产物生成、portfolio 展示的全链路。

**核心关注点:**
- 中文产品输入 → 后端翻译 → 英文脚本/视频生成 链路是否通畅
- 前端 UI 状态(loading/progress/gate)与后端 pipeline 状态是否同步
- 产物(mp4/png/mp3)能否被 nginx 静态直送、portfolio 展示、弹窗预览
- 主题翻转后各页面视觉一致性

## 2. 测试品类定义

| 字段 | 值 |
|------|-----|
| 产品名(中文) | 婴儿智能恒温暖奶器 |
| 产品名(英文) | Smart Baby Bottle Warmer |
| 核心卖点 | 3分钟快速均匀加热、37°C-50°C精准控温、UV消毒烘干一体、≤30dB超静音 |
| 目标人群 | 0-12个月新生儿妈妈 |
| 目标市场 | 北美(Amazon/Walmart) + 欧洲(OTTO/Bol) |
| 竞品锚点 | Philips Avent vs Dr. Brown's |
| 输入语言 | 中文(后端自动翻译为英文) |
| 预期视频时长 | 15-30s |

## 3. 场景优先级矩阵

| 优先级 | 场景 | 前端路由 | 后端端点 | 预期耗时 | 测试重点 |
|--------|------|----------|----------|----------|----------|
| **P0** | 快速模式 | `/fast` | `POST /fast/generate` | 3-5 min | 最短链路,UI反馈实时性,产物立即可播 |
| **P0** | 商品直拍(S1) | `/s1` | `POST /scenario/s1` | 15-30 min | 完整16步pipeline,gate检查点,step-by-step |
| **P0** | 品牌VLOG(S5) | `/s5` | `POST /scenario/s5` | 20-30 min | 角色身份系统,六视图选择,最长链路稳定性 |
| P1 | 品牌活动(S2) | `/s2` | `POST /scenario/s2` | 15-25 min | 品牌合规检查,多语言脚本(EN/ES/FR/DE) |
| P1 | KOL混剪(S3) | `/s3` | `POST /scenario/s3` | 15-25 min | 视频分析skill,remix脚本生成 |
| P2 | 实景拍摄(S4) | `/s4` | `POST /scenario/s4` | 10-20 min | 直播切片,场景自动识别 |

## 4. P0 场景详细测试用例

### 4.1 快速模式 (Fast Mode)

**前置条件**
- 环境: `https://101.34.52.232`
- API Key: `ai_video_demo_2026`
- 外部依赖: DeepSeek V4-Pro + POYO video 可用

| 步骤 | 前端操作 | 前端期望 | 后端调用 | 验收标准 |
|------|----------|----------|----------|----------|
| 1 | 进入 `/fast` | 页面加载,主题色 Warm Light,输入框可用 | `GET /api/health` 200 | 无控制台报错,无404资源 |
| 2 | Prompt输入:"婴儿暖奶器,深夜静音快速加热,妈妈安心睡眠,15秒" | 文本正常输入,字数统计正确 | - | 无XSS过滤误杀 |
| 3 | 选择时长15s,点击"立即生成" | 按钮禁用,loading动画,进度条出现 | `POST /fast/generate` 200 | 请求体包含user_prompt+duration |
| 4 | 等待3-5分钟 | 进度条有阶段性更新(非卡住) | pipeline 执行完成,output/fast_mode/ 下有产物 | 产物文件 > 1MB |
| 5 | 结果页面展示 | 视频缩略图+下载按钮+重新生成 | `/api/media/fast_mode/...` 返回视频流 | 视频可播放,时长≈15s |
| 6 | 进入 `/footage` 查看 | 新产物出现在"全部"或"视频"分类 | `GET /api/portfolio/?limit=50` 包含新产物 | poster正常,弹窗可播 |

**前后端联调检查清单**
- [ ] 前端 `apiFetch("/fast/generate")` 请求体与后端 `FastModeRequest` schema 匹配
- [ ] 后端返回的 `video_url` 前端能正确拼接为 `/api/media/...`
- [ ] 视频通过 nginx 静态直送(非穿透 FastAPI),响应头含 `Cache-Control`
- [ ] `/footage` 弹窗预览该视频: autoplay + controls 正常,Info bar 显示文件名/大小
- [ ] 主题色一致性: `/fast` 页面无残留暗色元素,按钮 hover 状态正确

---

### 4.2 商品直拍 (S1 Product Direct)

**前置条件**
- 产品 catalog JSON 准备(见第5节)
- S1 支持 auto 和 step_by_step 两种模式,本测试覆盖 auto 模式

| 步骤 | 前端操作 | 前端期望 | 后端调用 | 验收标准 |
|------|----------|----------|----------|----------|
| 1 | 进入 `/s1` | 场景选择页加载,5张场景卡片可点击 | - | 卡片hover/选中态正常 |
| 2 | 填写产品表单:名称/卖点/人群/价格/图片 | 表单验证通过,图片预览正常 | `POST /api/upload` (如有图片) | 表单无必填项漏报 |
| 3 | 点击"开始创作",选择auto模式 | 进入 `VideoWorkflow`,显示StageProgress | `POST /scenario/s1` 200 | 返回包含 `thread_id` |
| 4 | 观察 pipeline 执行 | StepByStepView 实时更新当前步骤 | 轮询 `GET /scenario/s1/state/{label}/steps` | 步骤状态与后端一致 |
| 5 | strategy_audit gate | score 0.60-0.90 时 GatePanel 弹出 | `GET /scenario/s1/gate/...` 返回3候选 | CandidateSelector 可横向对比 |
| 6 | 选择候选并批准 | 点击"批准",显示"pipeline续跑中" | `POST gate/.../approve` 200 | 后台任务启动,HTTP不504 |
| 7 | pipeline 完成 | 显示完成,进入 `/result` | `GET /scenario/s1/state/...` 返回完整state | 产物字段非空 |
| 8 | 下载/预览产物 | 下载mp4,预览keyframe | `/api/media/renders/...` 200 | 视频完整,声音正常 |
| 9 | footage 验证 | 进入 `/footage` → finished tab | 产物在 renders 分类 | GalleryGrid 缩略图+弹窗播放正常 |

**前后端联调检查清单**
- [ ] `POST /scenario/s1` 请求体包含完整 product_catalog + `api_keys`
- [ ] `thread_id` 可通过 `GET /pipeline/state/{thread_id}` 追踪
- [ ] Gate 3 候选的 `thumbnail_url` 前端能正确渲染对比
- [ ] approve 后 `contextvars` 路由覆写(D10)正确生效,pipeline 续跑到 `__end__`
- [ ] 产物在 `output/renders/` 且通过 `/api/media/renders/...` 可访问
- [ ] `/footage` 中该产物: `category=renders`, `thumbnail_path` 非空,弹窗播放有声音
- [ ] 主题一致性: `/s1` 各步骤卡片、GatePanel、SettingsPanel 无暗色残留

---

### 4.3 品牌 VLOG (S5 Brand VLOG)

**前置条件**
- 角色身份配置(妈妈/爸爸/育儿专家/宝宝)理解清楚
- S5 是链路最长的场景,需要确认 nginx 1500s timeout 足够

| 步骤 | 前端操作 | 前端期望 | 后端调用 | 验收标准 |
|------|----------|----------|----------|----------|
| 1 | 进入 `/s5` | VlogSixView 加载,6个角色卡片 | - | 卡片hover/选中态正常 |
| 2 | 选择角色"新手妈妈",填写品牌故事 | 表单可编辑,字数限制提示 | - | 表单验证通过 |
| 3 | 点击"生成VLOG" | 进入长链路执行,进度条持久显示 | `POST /scenario/s5` 200 | 请求成功,返回thread_id |
| 4 | 等待20-30分钟 | 页面不崩溃,polling不503 | pipeline 完成 | 产物在 output/seedance/ 或 output/renders/ |
| 5 | 查看结果 | `/result` 显示视频+6视图摘要 | state 包含 character_identity + keyframes | 视频内容与角色一致 |
| 6 | footage 验证 | `/footage` → materials tab → 视频分类 | 产物在 TOP50 | poster 正常,弹窗可播 |

**前后端联调检查清单**
- [ ] `POST /scenario/s5` 不因 28min+ 执行超时而 504(nginx 1500s)
- [ ] `character_identity` skill 输出与选定角色一致(妈妈≠专家)
- [ ] 6 视图模型选择前端状态正确传递到后端
- [ ] 产物视频在 `/footage` 中可被分类过滤"视频"正确筛选出
- [ ] 弹窗预览: 视频 controls 可用,info bar 显示正确文件名和标签

## 5. 测试数据准备

### 5.1 产品 Catalog (S1/S2 使用)

```json
{
  "product_name": "Smart Baby Bottle Warmer Pro",
  "product_name_zh": "婴儿智能恒温暖奶器Pro",
  "category": "baby_feeding",
  "target_audience": "0-12个月新生儿父母",
  "key_selling_points": [
    "3分钟快速均匀加热,告别冷热不均",
    "37°C-50°C精准控温,营养不流失",
    "UV紫外线消毒+热风烘干,一机多用",
    "≤30dB超静音设计,夜间不吵醒宝宝"
  ],
  "price_usd": 49.99,
  "competitors": ["Philips Avent", "Dr. Brown's"],
  "images": ["uploads/bottle-warmer-01.jpg"]
}
```

### 5.2 Fast Mode Prompt 模板

```
Baby bottle warmer, quick 3-minute heating, precise temperature control at 40°C,
ultra-quiet for nighttime use, mom sleeping peacefully next to crib, cozy nursery
ambient lighting, 15 seconds
```

### 5.3 S5 品牌故事模板

```
Brand: WarmCare
Story: A mother-designed brand born from 2am feeding struggles. Every product
is tested by 100+ real moms before launch. Mission: make feeding time the
warmest moment of the day.
```

## 6. 环境要求

| 环境 | 地址 | 用途 |
|------|------|------|
| 生产 | `https://101.34.52.232` | 主测试环境 |
| 本地 | `http://localhost:3000` + `http://localhost:8001` | 对比验证 |
| 监控 | `https://101.34.52.232/api/health` | 健康检查 |

**测试前必查:**
```bash
# 后端健康
curl -k https://101.34.52.232/api/health
# 前端可达
curl -k -I https://101.34.52.232/footage
# portfolio 接口正常
curl -k 'https://101.34.52.232/api/portfolio/?limit=50&sort=quality' \
  -H 'X-API-Key: ai_video_demo_2026'
# nginx 静态直送正常
curl -k -I 'https://101.34.52.232/api/media/thumbnails/portfolio_posters/...'
```

## 7. 验收标准

### 7.1 P0 必须通过

| 场景 | 通过标准 |
|------|----------|
| 快速模式 | 从输入prompt到可播放视频 ≤ 5分钟,产物质量可接受(无明显画面崩坏) |
| S1 商品直拍 | 完整pipeline走完,至少通过1个gate检查点,最终mp4 ≥ 10秒 |
| S5 品牌VLOG | pipeline不中途崩溃,产物与选定角色身份一致,视频可播放 |
| Footage | 三场景产物均出现在 `/footage`,poster+弹窗预览全部正常 |
| 主题一致性 | `/fast` `/s1` `/s5` `/footage` 无暗色残留,按钮/表单状态正常 |

### 7.2 阻塞项定义

以下任一情况发生即视为测试阻塞,需暂停并修复:
- `POST /scenario/s1` 或 `/fast/generate` 返回 5xx
- pipeline 执行中 `pipeline_degraded = True` 且无有效错误上报
- GatePanel 弹出后 approve 导致 pipeline 无限挂起(> 45min)
- `/footage` 弹窗预览视频黑屏/无声(排除浏览器静音)
- nginx 返回 404 导致 `/api/media/` 无法访问产物

## 8. 测试执行顺序

```
Day 1 (上午): 环境检查 → 快速模式 × 3次 → 验收
Day 1 (下午): S1 商品直拍 × 2次(auto+step_by_step) → 验收
Day 2 (上午): S5 品牌VLOG × 2次(不同角色) → 验收
Day 2 (下午): /footage 全链路验证 → 主题一致性走查 → 报告
```

## 9. 风险与回滚

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| POYO video API 临时不可用 | 中 | Fast/S5 产物无法生成 | 观察后端降级路径(mock mode),验证pipeline不崩溃 |
| DeepSeek API 限流 | 低 | 脚本生成延迟/失败 | 确认 fallback 到 `deepseek-chat`(V3) 是否生效 |
| nginx 配置错误导致媒体404 | 低 | 产物无法预览 | 检查 `deploy/lighthouse/nginx.conf` try_files 配置 |
| 主题翻转后某页面崩样式 | 中 | 用户感知差 | 快速修复:回滚 `web/src/app/footage/page.tsx` 到上一版 |
| S5 执行超时(> 28min) | 高 | 客户端504 | 使用 async submit + polling,不走同步等待 |

**回滚方案:**
- 前端: `git revert c4dd6ed` (footage弹窗) + `git revert d3e8bd3` (主题翻转)
- 后端 portfolio: `git revert 02849c9`
- nginx: 恢复 `deploy/lighthouse/nginx.conf` 中 `/api/media/` 为纯 proxy_pass

## 10. 测试输出物

- [ ] 三场景产物(mp4)存档到 `output/renders/` 或 `output/fast_mode/`
- [ ] `portfolio_index.json` 自动更新,包含新产物
- [ ] 测试报告: 记录每次执行耗时、成功率、阻塞项
- [ ] 截图: `/fast` `/s1` `/s5` `/footage` 关键页面状态
