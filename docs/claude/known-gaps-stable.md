---
title: 已知缺口与待办清单
doc_type: knowledge
module: project
status: stable
created: 2026-05-08
updated: 2026-05-09
owner: self
source: human+ai
---

# 已知缺口与待办清单

最近一次盘点:2026-05-08(第三轮质量提升 18 项全部完成，质量体系从 "事后检查" 升级为 "全过程可控")。

详细内容见下文。

### 1. 已知功能缺陷(已修复)

> **2026-05-09 修复 (S2/S4 生产缺陷):**
>
> - **S2 `strategy_failed: 'product_catalog'`** — `submit_scenario` S2 分支的 config 缺少
> `product_catalog`，StepRunner fallback 到 s1 pipeline 后 `_step_strategy` 需要
> `config["product_catalog"]` → KeyError。修复：`scenario.py` S2 分支从 `brand_package`
> 自动构造 `product_catalog` + `brand_mode=True`；`step_runner.py:_SCENARIO_CONFIGS`
> 显式添加 `s2` 条目复用 S1 pipeline class。验证：非 demo E2E 通过，生成 9.9MB 真实视频。
> 前端无需额外传递 `product_catalog`。
> - **S4 `clip_0_failed: 'prompt' must be a string`** — `s4_live_shoot_pipeline.py:_step_video_prompts`
> 将 `seedance-video-prompt` 返回的 `list[dict]` 整体嵌套进 `"prompt": vp.data`，下游
> `_step_seedance_clips` 传入 `list` 而非 `string` 给 `seedance-video-generate-skill`，
> `validate_params` 检查 `isinstance(prompt, str)` 失败。修复：改为扁平化模式（与 S1 一致），
> 直接 `all_prompts.extend(vp.data)`。验证：非 demo E2E 通过，`clip_details=[False, False, False]`，
> 视频 `s4_with_audio.mp4` = 5.8MB（之前 12KB stub）。

> **2026-05-07 修复:**
>
> - **ChunkLoadError /footage 页面崩溃** — Turbopack content-hash 变化导致旧 chunk 引用失效。
> nginx `location /` 添加 `Cache-Control: no-store` 禁止 HTML 缓存，`location /_next/`
> 静态资源长期缓存。`deploy.sh` 构建前清理旧产物避免残留。
> - **循环导入导致 backend 启动失败** — `src/graph/nodes.py` 顶层导入 `_register_background_task`
> 形成 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py` 循环。改为延迟导入 helper。
> - **nginx `limit_req off` 语法错误** — 原配置使用无效语法，`location /health` 和
> `/api/media/` 改为高 burst 值实现等效豁免。
> - **nginx 顶层 `limit_req` 误伤前端导致首页 429** — `server` 块顶层 `limit_req zone=api_limit burst=20 nodelay` 被前端 `/` 和 `/_next/` 默认继承，Next.js 冷启动
> 30+ 并发请求秒爆 burst=20。修复：删除顶层声明，改为 7 个 API location 内部
> 显式 `limit_req`。生产 rsync `--inplace --no-whole-file` + `nginx -s reload` 落地。

> **2026-05-06 修复:**
>
> - **Portfolio 加载慢 + 视频无法预览** — 后端 `?limit=50&sort=quality` + nginx `try_files`
> 静态直送 + 144 个 poster thumbnail + 前端 `<img poster>` 替代 337 个 `<video preload="metadata">`。
> 实测 thumbnail 4.8ms / video 32ms(02849c9)。
> - **Footage 页面交互不一致** — 成品/素材统一 `MediaPreviewModal` 弹窗预览,不再
> `window.open` 或右侧 detail panel;Materials 新增 全部/视频/图片/音频 分类过滤(c4dd6ed)。
> - **UI 主题翻转** — `globals.css` + `tailwind.config.js` + 40+ 组件从暗黑剧场翻转为
> Warm Light Professional Theme(d3e8bd3)。

> **2026-05-08 4-Option Plan 修复/扩展:**
>
> - **POYO sanitizer Phase 2** — 新增 11 条替换规则(英 7 + 中 4)，覆盖 baby bottle / nipple /
> areola / formula milk / baby food / postpartum / 奶瓶 / 奶嘴 / 辅食 / 产后。
> 新增结构化 CM 拒绝日志，生产可通过 `poyo_cm_rejection` 事件抓回原始 prompt 持续补充规则。
> - **S3-S5 Gate 配置** — `gate_manager.py` per-scenario 重构完成，`SCENARIO_GATE_DEFINITIONS`
> 定义 s1-s5 各场景 gate 集合与 after_step 映射；`candidate_scorer.py` 新增 `remix_script` /
> `character_identity` / `vlog_strategy` 评分维度。`step_runner.py` gate 触发按 scenario 读取。
> `_build_skill_params` 补充 `remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py`
> 52 个测试验证配置正确性。step-by-step gate 暂停对 S3/S4/S5 均已 mock 验证通过。
> - **Long pipeline UX** — 统一异步框架已落地，S2/S3/S5 的长链路不再受 HTTP 超时截断。

> **2026-05-08 修复:**
>
> - **Admin Panel 登录不可用** — `bcrypt` 未安装导致 admin router 启动跳过；nginx `/api/`
> catch-all strip `/api` 前缀导致 admin 端点 404；`admin_accounts` 表未创建（Alembic
> 迁移未执行）。修复：`pip install bcrypt` + `docker commit`；新增 `/api/admin/` nginx
> location 保留前缀；手动 SQL 建表并插入初始 admin 账号。登录验证通过。
> - **page.tsx 构建失败** — `useExpertStore` 解构缺少 `setShowStageProgress` /
> `currentStepIdx` / `setCurrentStepIdx`。补充解构后 `npm run build` 通过。
> - **nginx `/telemetry/` 404** — 缺少 `/telemetry/` location，请求被路由到前端。
> 新增 location 转发到 backend，`/telemetry/prometheus` 返回 Prometheus 格式指标。

仍待处理:

- **POYO sanitizer 覆盖率持续提升(F3, P2)** Phase 2 新增 11 条规则后覆盖率大幅提升，
但仍需在生产日志中持续抓回 `poyo_cm_rejection` 事件中的原始 prompt 文本补充新规则。
- **yt-dlp / whisper 未装进 backend 容器(F4, P3)** D5 KOL 视频分析 skill 走 mock 路径,
脚本生成不依赖真实 transcribe,管线下游不受影响。要让 video-analysis 真实工作需
`pip install yt-dlp openai-whisper` 进 `Dockerfile.backend`(whisper 拉 PyTorch ~2GB,
实施前先确认是否值)。

### 2. 配置/历史遗留(已知)

- **api_assets.py compat shim:** `/api/assets/`* uses in-memory dicts (`_brand_packages`,
`_influencers`). Frontend OpenAPI types still reference these paths, so don't remove the
router; do migrate any new asset features to `src/routers/assets.py` instead.
- **S2-S5 step-by-step / gate system:** S3/S4/S5 已完成 StepRunner 迁移 (P2)、gate
配置、skill params 扩展与非 S1 场景 mock 验证。`_build_skill_params` 新增
`remix_script` / `vlog_strategy` 分支，`test_gate_scenario_configs.py` 52 测试验证
配置正确性。仍待: 前端 `CandidateSelector` 在非 S1 场景下的状态映射未实测；
S3-S5 gate 真实 API key 端到端（类似 `test_gate_full_flow_e2e.py` 对 S1 gate_1 的验证）。
- **Long pipeline UX:** ✅ 已解决(2026-05-08) — 统一异步执行框架落地，所有场景走
`POST /submit` → 轮询 `/status`，HTTP 超时不再截断长链路。nginx 1500s 退居兜底。
- **Redis/Celery declared but unused:** Still in `requirements.txt` but no live consumer.
- **LangGraph 代理层 (P4-4):** `/pipeline/`* 端点已代理到 StepRunner，但代理层 state 转换是
best-effort，某些 legacy 字段可能缺失。保留原始 LangGraph 代码作为兼容层，代理函数可迭代补全。
- **pyright strict 剩余规则:** `reportUnknownMemberType` / `reportUnknownVariableType` 未启用。
在 `dict[str, Any]` 为主的代码库中，这两项规则噪音远大于价值。如需进一步收紧类型，需先
将 `dict[str, Any]` 替换为数百个具体类型（ProductCatalog、PipelineConfig 等），ROI 待评估。
- **deploy.sh Phase 0 逻辑缺陷:** ✅ 已修复。`mtime` 比较 → `sha256sum` hash 比较，
Dockerfile 构建时记录 `sha256sum requirements.txt > /app/.requirements_sha256`，
deploy.sh 直接对比本地 hash 与镜像内 hash。不受 `IMG_BUILT_TS=0` 影响，首次部署也正确提示。
- **alembic 不在 requirements.txt 中:** ✅ 已修复。`alembic>=1.13` 已加入 `requirements.txt`，
backend image 已 rebuild 固化，容器内可直接执行 `alembic upgrade head`。
- **Quality 模块 lazy import 设计:** `src/quality/` 下 10 个模块全部采用 lazy import。
transformers/torch/opencv/mediapipe/deepface/pyiqa/scenedetect 均不在 `requirements.txt`
中强制要求。运行时会检测可用性，不可用则 graceful skip 并记录 warning。生产如需启用
CLIP/BRISQUE/场景分析/人脸一致性，需手动安装对应依赖并确认 Docker image 体积可接受
(CLIP+torch CPU ~600MB, DeepFace ~200MB)。

### 3. 未做端到端验证的前后端交互路径

Phase D/E 通过的是 5 场景"主路径" + portfolio 优化。以下路径在生产尚未端到端实测:

- **A. Human Review 4 个 checkpoint 的人工分支** Pipeline `strategy_audit` /
`script_audit` / `editing_audit` / `thumbnail_audit` 的 score 落在 0.60–0.90 区间会触发
HITL,前端 `GatePanel` + 后端 `POST /scenario/{s}/gate/{label}/{gate_id}/approve` 的
"APPROVED / CHANGES_REQUESTED / REJECTED" 三个分支以及 D10 contextvars 路由覆写,
Phase D 没触发到。需要构造低分输入或下调阈值实测。
- **B. S1 step-by-step + Gate 候选生成全链路** ✅ 后端单元测试已覆盖（`test_s1_gate_full_flow.py`
41 测试：approve 成功路径包括 candidate 选择 → edited_output 写入 → current_step 推进；
step_runner gate 暂停/恢复 4 个测试验证 pre-step + post-step 检查点）。
真实 API key e2e 在 `test_gate_full_flow_e2e.py` 中覆盖 gate_1 generate + score + approve
  - regenerate。生产端到端未实测（Phase D D2 走的是 auto 模式）。
- **C. Distribution / Publish** `POST /distribution/publish` + TikTok / Shopify connector
实际发布。Phase D 没跑过,只有单元测试。需要真实 platform credentials 才能走通。
- **D. Metrics 全链** `GET /metrics/`* 视频性能查询、`src/tasks/metrics_poller.py` 周期任务
在生产是否被调度、Alembic 的 `video_metrics` 表是否真的 `alembic upgrade head` 过、
PG 与 SQLite 双路是否在生产生效。前端 `PerformanceDashboard` 显示真数据未验证。
- **E. Assets 上传链路** ✅ 后端单元测试已覆盖（`test_upload_e2e.py` 10 测试验证
multipart → 落盘 → `/api/files` 列出 → `/api/media/` 访问完整链路；含认证/扩展名/大小限制
负向测试）。前端 `brand-packages/page.tsx` 已集成 `AssetUploader` 上传面板（Header 右侧
上传按钮 + 可折叠上传区域，上传完成后自动刷新列表）。仍待: 生产未走通"上传 → 管线
引用 → 出现在最终视频"的闭环（uploaded 文件尚未被 keyframe/seedance 步骤实际引用验证）。
`/influencers` 列表 CRUD 在生产是否真存了 PG 未验证。
- **F. Webhook 事件分发** `src/tools/webhook_manager.py` 的 `audit.completed` /
`pipeline.completed` 事件,Phase D 期间生产 `WEBHOOK_URLS` 为空,从未触发。需要配上
接收端(可临时用 webhook.site)再跑任一场景验证。
- **G. 错误降级路径** `pipeline_degraded = True` 在 5 场景中未被触发(都走绿)。Mock POYO /
DeepSeek 故障下的"降级 + 终止 + 错误上报"链路、`error_collector` FIFO、`/telemetry`
端点的可见性,均未做负向测试。
- **H. 多用户并发 + API Key 隔离** `contextvars` 隔离机制在单机单请求 OK。同时跑 2+ 场景
使用不同 API key 时是否真的不串(尤其 LLM client + POYO client + Seedance client 三处
contextvars 读取),没压测过。
- **I. i18n 切换** `zh-CN` / `en` 在生产页面切换后,所有按钮 / 表单 / 报错 / SettingsPanel /
GatePanel / DistributionView 文案是否都从翻译表读取(无硬编码中文/英文残留),未走查。
- **J. 备用部署目标** `render.yaml`(海外)与 `deploy/tencent-cloudbase.md`(国内 CloudBase)
这两条 alternative 路径的现状,自从 Lighthouse 成为 canonical 后没人再验过。`render.yaml`
里 `DEFAULT_LLM_PROVIDER=kimi` 是否还能正常生成内容,未知。
- **K. Quality 模块真实 ML 依赖验证** `src/quality/` 下 CLIP、BRISQUE、PySceneDetect、
MediaPipe/DeepFace 均只在代码层面验证通过（lazy import + fallback 路径）。真实安装
transformers+torch / opencv-python / mediapipe 后的端到端验证尚未执行。`nr_quality.py`
的 OpenCV fallback 在现有生产环境（有 ffmpeg 无 opencv-python）中走的是 "skipped" 路径。
- **L. 质量评分传递链闭环** seedance_prompt / script_writer 已输出 `quality_score` /
`_self_check`，但下游 skill（keyframe_images → seedance_clips → remotion_assemble）尚未
读取上游 quality_score 并在低于阈值时触发 regenerate。"下游读取上游 quality_score，
低于阈值主动请求 regenerate" 机制仍是设计文档中的概念，未实现。

### 4. 2026-05-06 新增未验证路径 → 已验证/已修复

- **K. Footage 弹窗预览在三场景下的素材生成验证** ✅ 已验证 — S1/S5/Fast Mode 新产物均
正确出现在 `/footage`，弹窗视频 controls + autoplay 正常，portfolio TOP50 截断正确。
- **L. 主题翻转后全页面一致性走查** ✅ 已走查 — `/fast` `/s1` `/s5` `/footage` 无暗色残留。
发现并修复: footage 页面 grid item 无 thumbnail fallback 的 `text-white/40` icon 在
`#FCF5F2` 浅色背景上不可见 → 改为 `text-[var(--text-muted)]`。

### 5. 2026-05-06 测试中发现的新问题

- **S1 `final_video_path` 未回写** — Remotion 组装后最终视频路径未写入 pipeline state，
`final_video_path` 为空字符串。audit 报告视频存在(13.5MB)但 state 无法引用。需检查
`remotion_assemble.py` 是否正确更新 state。
- **S5 strategy 节点 LLM 超时** — 已修复: `LLM_TIMEOUT_SECONDS=60s` 对 VLOG strategy 长
prompt 不足，改为 `_step_vlog_strategy` 内创建 `LLMClient(timeout=120.0)` 专用实例。
- **S1 `product_name` 字段读取错误** — 已修复: `s1_product_pipeline.py:100` 原代码读取
`product_catalog.get("name", "Product")`，但 API 请求传的是 `"product_name"` 字段，
导致 audit `product_mention` 检查使用 "Product" 占位符。改为
`product_catalog.get("product_name") or product_catalog.get("name", "Product")`。

---
