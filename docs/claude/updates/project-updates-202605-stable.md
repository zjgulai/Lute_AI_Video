---
title: 项目更新记录 (2026-05)
doc_type: knowledge
module: project
status: stable
created: 2026-05-08
updated: 2026-05-08
owner: self
source: human+ai
---

# 项目更新记录 (2026-05)

本文档按日期记录 2026 年 5 月的全部项目变更，供追溯和审计。
原始来源为 CLAUDE.md Overview 段落，因体积过大提取至此。

**2026-05-06 更新:**

- UI 主题从暗黑剧场翻转为 **Warm Light Professional Theme** (`#FDF8F6` 暖白底 + `#D75C70` Fortune Red accent)
- Portfolio 完成性能优化: TOP50 高质量素材 + nginx 静态直送 + poster thumbnail
- Footage 页面统一弹窗预览 + Materials 分类过滤(视频/图片/音频)
- **E2E 联调测试** (婴儿暖奶器品类): P0 三场景(Fast Mode/S1/S5)全部执行，报告见
`tmp/outputs/test-report-baby-bottle-warmer-e2e-20260506.md`
- **修复**: S5 strategy LLM 超时 60s → 120s (`s5_brand_vlog_pipeline.py`)
- **修复**: S1 `product_name` 字段读取错误，从 `"name"` 改为优先 `"product_name"`
(`s1_product_pipeline.py:100`)
- **修复**: Footage 页面无 thumbnail fallback icon 在 light 主题下对比度不足
(`text-white/40` → `text-[var(--text-muted)]`)
- CloudBase / Render are documented as alternative deploy paths but are not the canonical target.

**2026-05-07 更新 (Phase 2 架构归一化完成):**

- **双运行时架构统一**: S3/S4/S5 全部接入 `StepRunner` + `run_step()` 接口，与 S1 统一为
StepRunner 主运行时 + LangGraph 兼容运行时。`step_runner.py` 的 `_SCENARIO_CONFIGS`
集中管理 s1/s3/s4/s5 的 step_order 与 pipeline_class 映射。
- `**_pipeline` 延迟初始化**: `compile_pipeline()` 从模块导入时执行改为 `get_pipeline()`
工厂函数首次调用时延迟初始化，避免启动时即建立 PostgresSaver 连接。
- **SkillRegistry 实例隔离**: `_skills` 从类变量改为实例变量，每个 `SkillRegistry()` 实例
拥有独立的 skill 副本，并发/测试场景互不干扰。
- **API key 租户化 (P2-8)**: 新增 `api_keys` 表 + Alembic 迁移，`verify_api_key` 改为 async
函数，支持 PG 查询验证 + 环境变量 fallback。新增 `tenant_id` contextvar。
- **nginx rate limit**: 生产限流从 FastAPI middleware 内存实现迁移到 nginx
`limit_req_zone` + 各 API location 内显式 `limit_req`，前端 / 与 /_next/ 不限流。
- **LLMClient 缓存 TTL**: `_clients` 增加 300s TTL + 20 上限 + `key_hash` 租户维度，防止
死连接池堆积和无界内存增长。
- **target_languages 收口**: 6 处硬编码 `["en"]` 统一改为 `config.DEFAULT_LANGUAGES`。

**2026-05-07 更新 (Phase 4 完成):**

- **pyright 类型检查**: `pyproject.toml` 配置 `[tool.pyright]`，启用
`reportMissingTypeArgument` + `reportPossiblyUnboundVariable`，`src` + `tests` 0 错误。
发现并修复 2 个真实运行时缺陷（test_s1_e2e.py / test_media_clients.py 的 async 调用缺少 await）。
- **Prometheus exporter (T4.2)**: 新增 `src/telemetry_prometheus.py`，暴露 6 个指标
（pipeline_runs_total、pipeline_duration_seconds、step_duration_seconds 等），
`/telemetry/prometheus` 端点返回 Prom exposition 格式。
- **LangGraph 代理层 (T4.4)**: `/pipeline/*` 6 个端点保留 API 契约，内部代理到 StepRunner。
前端 7 个死函数标记 `@deprecated`，指引调用方迁移到 `/scenario/*` 端点。
- **死代码清理 (T4.3)**: 删除 `_try_save_metrics` 静默 ImportError、test_i18n.py ES/FR/DE
死测试、telemetry/cost_tracker 死函数，共 273 行清理。

**2026-05-07 更新 (生产部署修复):**

- **ChunkLoadError 修复**: `/footage` 页面 `Failed to load chunk 12k1vegccjm7k.js`。
根因：浏览器缓存旧 HTML + Turbopack content-hash 变化。修复：nginx `location /`
添加 `Cache-Control: no-store`，`location /_next/` 添加 `max-age=31536000, immutable`；
`deploy.sh` 构建前清理 `.next/standalone/` / `.next/static/` 旧产物。
- **循环导入修复**: `src/graph/nodes.py` 顶层 `from src.routers._state import _register_background_task` 导致 `_state.py` → `pipeline.py` → `nodes.py` → `_state.py`
循环。改为 `nodes.py` 内 `_register_bg()` helper 函数延迟导入。
- **nginx 语法修复**: `limit_req off;` 不是有效 nginx 语法，`location /health` 与
`/api/media/` 改为 `limit_req zone=api_limit burst=100/1000 nodelay;`。
- **nginx 限流误伤前端 (429 风暴) 修复**: `server` 块顶层 `limit_req zone=api_limit burst=20 nodelay` 会被未显式覆盖的 `location` 默认继承，前端 `/` 和 `/_next/` 也跟着
限流。Next.js 首页冷启动 1s 内 30+ 并发请求秒爆 burst=20，浏览器看到 429 风暴。
修复：删除顶层声明，改为 7 个 API location 内部各自显式 `limit_req`，前端 location
不限流。验证：50 并发 `/api/*` → 21×404 + 29×429（限流正常），30 并发 `/` → 全 200。

**2026-05-07 更新 (Admin Panel Phase 1):**

- **Admin Panel 全链路接线**: 新增 `/api/admin/*` 端点群 + `/admin` 前端页面，完成 Phase 1
后台管理系统。包含：Dashboard 概览、Tenant 管理(CRUD + API Key 生命周期)、
System Logs 查看、System Health 状态监控。
- **双层认证架构**: Admin session-cookie 认证(邮箱+密码)与租户 API key 认证完全独立，
零交叉。`verify_admin_session` 依赖注入模式与 `verify_api_key` 对称。
- **CORS credentials 支持**: `allow_credentials=True` 启用，Admin cookie (HttpOnly)
跨域可正常发送。
- **Response wrapper cookie 保留**: 修复中间件重建 JSONResponse 时丢失 Set-Cookie
header 的缺陷（admin login 设置的 session cookie 会被正确传递）。
- **后台任务**: startup 注册 3 个周期性任务 — health check(5min)、session cleanup(1h)、
log cleanup(1h)。
- **error_logs 持久化**: `ErrorCollector.collect()` 自动写入 `error_logs` 表，
Admin Logs 页面可查询。保留 30 天(可配置 `ADMIN_LOG_RETENTION_DAYS`)。
- **Alembic 迁移**: `2d6b8e9c0f1a_admin_panel_phase1.py` 创建 4 张新表
(`admin_accounts`, `admin_sessions`, `tenants`, `error_logs`)。
- **初始管理员脚本**: `scripts/create_admin.py <email> <password>` 创建首个 admin 账号。

**2026-05-08 更新 (4-Option Plan 全面落地):**

- **统一异步执行框架 (A+B 合并)**: 所有场景(S1-S5)统一走 `POST /scenario/{s}/submit`
→ 返回 `{label, status: "queued"}` → 前端指数退避轮询 `GET /scenario/{s}/status/{label}`。
`StageProgress` 组件从 S1 独占泛化为全场景通用，按 scenario 映射到 3 阶段进度条
(writing → visuals → export)。Gate approve 后的后台续跑复用同一框架。
- **S3-S5 Gate 系统配置 (Phase 1C)**: `gate_manager.py` 从 S1-hardcoded 重构为
per-scenario 配置：`SCENARIO_GATE_DEFINITIONS` 定义 s1/s2/s3/s4/s5 各自的 gate 集合
与 after_step 映射；`candidate_scorer.py` 新增 `remix_script`、`character_identity`、
`vlog_strategy` 评分维度。`step_runner.py` 的 gate 触发逻辑也改为按 scenario 读取。
- **POYO Sanitizer Phase 2 (C)**: 新增 7 条英文规则（baby bottle / nipple / areola /
formula milk / baby food / postpartum / bottle feeding）+ 4 条中文规则（奶瓶 / 奶嘴 /
辅食 / 产后）。`poyo_client.py` 在 submit 时存储原始 input，failed 任务中检测
"content" 字样即触发 `poyo_cm_rejection` 结构化日志，保留原始 prompt 用于规则扩展。
新增 `tests/test_poyo_safety.py` 15 个单元测试。
- **监控告警基础设施 (D)**: 新增 `deploy/lighthouse/prometheus-alerts.yml`（6 条规则：
pipeline 错误率 / step p99 / API 5xx / API 延迟 / 后台任务激增 / pipeline 停滞）。
新增 `deploy/lighthouse/grafana-dashboard.json`（8 panel：runs/min、error rate、
step duration p50/p95/p99、API rate+latency、active tasks、runs today、avg duration、5xx count）。

**2026-05-08 更新 (生产部署修复):**

- **page.tsx TypeScript 构建错误** — `useExpertStore` 解构缺少 `setShowStageProgress` /
`currentStepIdx` / `setCurrentStepIdx`，Next.js `npm run build` 失败。补充解构后本地构建通过。
- **nginx `/telemetry/` 路由缺失** — `/telemetry/prometheus` 请求被路由到前端 404。
新增 `/telemetry/` location 转发到 backend。
- **nginx `/api/admin/` 路由前缀被 strip** — `/api/` catch-all `proxy_pass http://backend/`
去掉 `/api` 前缀，backend 收到 `/admin/auth/login` 不匹配 router 注册的 `/api/admin/auth/login`。
新增 `/api/admin/` location 保留完整前缀转发。
- **SSL 证书被 rsync 误删为空目录** — `server.crt` / `server.key` 不在本地 `deploy/lighthouse/`
中，`rsync --delete` 删除远程证书文件后 docker 创建空目录占位，nginx 挂载失败。
修复：重新生成自签名证书；**防御措施**：deploy.sh 前手动备份 SSL 文件，或改用 `rsync --exclude`。
- **prometheus-client 未装进容器** — `requirements.txt` 中已有 `prometheus-client>=0.20`，
但 backend image 未 rebuild（deploy.sh Phase 0 旧逻辑 `mtime` 比较在 `IMG_BUILT_TS=0`
时不触发警告）。已通过 `docker compose build backend` rebuild image 固化。
- **bcrypt 未装进容器** — Admin router 因 `No module named 'bcrypt'` 被跳过，login 500。
已通过 image rebuild 固化，`requirements.txt` 已包含 `bcrypt>=4.2`。
- **Alembic 不在 requirements.txt 中** — `alembic` 用于本地开发迁移，但生产部署也依赖它
执行 `alembic upgrade head`。当前生产表通过手动 SQL 创建。**已修复**：`alembic>=1.13`
已加入 `requirements.txt`，image rebuild 后容器内可直接执行 `alembic upgrade head`。
- **admin_accounts 表未创建** — Admin Panel 表通过 Alembic 迁移 `2d6b8e9c0f1a` 创建，
但生产从未运行过该迁移。直接用 asyncpg 执行 SQL 建表 + 插入初始 admin 账号。

**2026-05-08 更新 (结构简化):**

- **nginx.conf proxy header 提取** — 新增 `deploy/lighthouse/proxy_params.conf` 统一 4 个
proxy header，13 个 location 块全部改为 `include /etc/nginx/proxy_params.conf;`，
消除 ~60 行重复。`docker-compose.prod.yml` 同步挂载该文件。
- `**/telemetry/` burst 提升** — `burst=20` → `burst=100`，避免 Prometheus scraper 被限流。
- **page.tsx store 订阅拆分** — `currentStepIdx` / `showSteps` 从 `useExpertStore` 迁移到
`usePipelineStore`（它们描述的是全局 loading 状态，与 expert 模式无关）。
`useExpertStore` 字段从 10 个减至 6 个，根页面不再因 expert 无关状态变化而重渲染。

**2026-05-08 更新 (Gate 系统 + 上传测试扩展):**

- **Gate manager skill params 扩展** — `gate_manager.py` 新增 `remix_script`（S3）和
`vlog_strategy`（S5）的 `_build_skill_params` 分支，支持非 S1 场景的 gate 候选生成。
- **Gate 全链路测试** — `test_s1_gate_full_flow.py` 扩展 approve 成功路径测试（candidate
选择 + edited_output 写入 + current_step 推进）。新增 `test_gate_scenario_configs.py`
验证 S3/S4/S5 的 per-scenario gate 定义和 step_runner gate 触发逻辑。
- **Assets 上传 E2E** — 新增 `test_upload_e2e.py`，验证 multipart upload → 后端落盘 →
`/api/files` 列出 → `/api/media/` 可访问的完整链路。
- **Brand Packages 上传面板** — `brand-packages/page.tsx` 集成 `AssetUploader` 组件，
支持在品牌资产页面直接上传文件。

**2026-05-08 更新 (代码简化 /simplify 审查修复):**

- `**gate_manager.py` `_extract_step_input` 修复** — `remix_script` 分支原代码直接读取
`state["steps"]["video_analysis"]["output"]`，跳过 `_extract_step_input()` 辅助函数，
导致用户编辑 `video_analysis` 后的 `edited_output` 被忽略。修复后 S3 gate 候选生成
正确优先读取编辑版本 (`_build_skill_params` line ~911)。
- **删除复述代码的 WHAT 注释** — `gate_manager.py` 两处 `# S3: remix-script-skill expects...`
/ `# S5: product-strategy-skill expects...` 注释复述字典字面量内容，已删除。
- `**test_upload_e2e.py` 清理** — 删除 5 处 `from src.config import OUTPUT_DIR` 死导入；
提取 `upload_dir` fixture 统一收口 6 处重复的 `monkeypatch.setattr(...)`；精简
`test_upload_rejects_dotdot_filename` 多行 docstring。
- `**test_gate_scenario_configs.py` 清理** — 删除未使用的 `_get_gate_defs` / `_get_step_order` 导入。
- `**isolated_state_dir` fixture 提取到 conftest.py** — 原在 `test_s1_gate_full_flow.py`
和 `test_gate_scenario_configs.py` 各复制一份，现提取到 `tests/conftest.py` 全局复用。
- **测试验证** — `test_gate_scenario_configs.py`(52) + `test_s1_gate_full_flow.py`(41)
  - `test_upload_e2e.py`(10) 共 103 测试全部通过。

**2026-05-08 更新 (部署流程加固):**

- `**bcrypt` / `prometheus-client` / `alembic` 固化到 backend image** — 之前用
`docker exec pip install` + `docker commit` 临时修复，image rebuild 后丢失。
现 `requirements.txt` 已包含三项依赖，`Dockerfile.backend` rebuild 后全部固化。
Admin router 正常加载（`/api/admin/` 返回 401 而非 404），`alembic upgrade head`
可在容器内直接执行。
- `**Dockerfile.backend` 删除多余 `asyncpg` 安装** — 第 24 行 `pip install asyncpg>=0.29`
与 `requirements.txt` 重复，已删除。节省一层 layer，build 时间减少 ~1s。
- **deploy.sh Phase 0 hash 检测替代 mtime** — 原 `git log mtime` vs `docker inspect Created`
比较在 `IMG_BUILT_TS=0`（首次部署/无法获取 image 时间）时不触发警告。
改为 `sha256sum requirements.txt` 本地 hash vs image 内记录的 hash 比较，
不受 mtime 影响，首次部署也会正确提示 rebuild。
- **nginx `restart` → `--force-recreate`** — `docker-compose restart nginx` 只重启进程，
不重新挂载 volume。新增 `proxy_params.conf` 时 volume 变更不生效，导致 nginx
`[emerg] open() "/etc/nginx/proxy_params.conf" failed`。改为 `--force-recreate`
确保 volume 挂载始终与 `docker-compose.prod.yml` 一致。

**2026-05-08 更新 (第三轮质量提升 — 18 项全部完成):**

本轮将质量体系从 "事后检查" 升级为 "全过程可控"，引入行业框架 (Hook-Retain-Reward-Action, AIDA)
和 ML 算法。所有新 ML 依赖均采用 lazy import，不强制安装。

- **P0 — 生产级紧急修复 (4 项)**:
  - `seedance_video_generate.py`: 新增 `_check_frame_variance()` — ffmpeg 抽 3 帧缩放到 32x32，
    MSE 检测静态图 (阈值 50) + 平均亮度检测黑屏 (阈值 20)。集成到 `_self_verify` 的 `all_ok`。
  - `remotion_assemble.py`: 新增 `_check_av_sync()` — ffprobe 分别读取视频/音频流 duration，
    绝对差异 >0.5s 或相对差异 >5% 报 `av_desync`。集成到 `_self_verify`。
  - `media_quality_audit.py`: 扩展 `_audit_final_video()` — `_get_video_specs()` 提取 width/height/
    fps/bitrate，分辨率非 9:16 / fps<25 / bitrate<1.5Mbps 均扣分。
  - `auditor.py`: Hook Strength 从纯 duration 检查扩展为 duration×0.4 + text×0.6。新增
    `_score_hook_text()` 检测 8 类 curiosity gap + pattern interrupt 信号。

- **P1 — 质量显著提升 (6 项)**:
  - `src/quality/clip_alignment.py`: CLIP `openai/clip-vit-base-patch32` 文本-图像对齐，
    sigmoid 归一化，阈值 0.28(强)/0.18(弱)。lazy import transformers+torch。
  - `src/quality/nr_quality.py`: BRISQUE-like 无参考质量评估。pyiqa BRISQUE 优先，
    fallback 到 OpenCV Laplacian 方差 + Michelson 对比度 + 亮度分布。
  - `auditor.py`: 新增 Information Density criterion — words-per-second 2.5-3.5 optimal。
  - `auditor.py`: 新增 Emotional Arc criterion — `_score_emotional_arc()` 检查 negative→positive
    转换、CTA urgency、hook attention 信号。
  - `seedance_prompt.py`: `_score_prompt_quality()` 检查 action/camera/lighting/shot_type/
    forbidden_words 五项齐全度，返回 per-prompt quality_score。
  - `script_writer.py`: `_self_check_script()` 检查 hook 强度、USP 覆盖、时长合规、
    segment 完整性，结果写入 `_self_check` 字段。

- **P2 — 竞争壁垒 (4 项)**:
  - `src/quality/scene_analysis.py`: PySceneDetect `ContentDetector` 场景边界检测，
    对比 expected_segments 计算 structural_match。
  - `src/quality/face_consistency.py`: DeepFace (Facenet) → MediaPipe face_mesh landmark
    cosine similarity 双层 fallback，替换 histogram 方法。
  - `src/quality/safe_zone.py`: TikTok/YouTube Shorts/Instagram Reels 平台 UI 遮挡区检查，
    drawtext y 表达式解析。
  - `src/quality/ab_tracker.py` + `gate_manager.py`: gate 选择记录 + performance 数据关联。
    `compute_variant_performance()` 按 variant (standard/creative/conservative) 聚合。

- **P3 — 长期规划 (4 项)**:
  - `src/quality/viral_predictor.py`: 8 因子加权 ensemble（hook/density/cta/emotion/
    thumbnail/video），未来可替换为 LightGBM。
  - `src/quality/ctr_estimator.py`: thumbnail CTR + script conversion heuristic 预估。
  - `src/quality/dynamic_thresholds.py`: 读取 ABTracker 数据，按 winning variant 自动调整
    hook_duration_max 等阈值。
  - `src/quality/skill_versioning.py`: SkillMonitor 记录 latency/success/fallback rate，
    SkillVersionRegistry 版本管理。

---
