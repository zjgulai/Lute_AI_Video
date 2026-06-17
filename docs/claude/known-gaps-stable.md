---
title: 已知缺口与待办清单
doc_type: knowledge
module: project
status: stable
created: 2026-05-08
updated: 2026-06-17
owner: self
source: human+ai
---

# 已知缺口与待办清单

最近一次盘点：**2026-06-11** — 完整路径修复已恢复本地质量门可信度，并补齐命令入口、rendering deploy 防回归守卫、前端热路径类型边界和“真实 provider + 前后端联动”E2E 正式计划。本轮已复跑 Phase A/B no-token 证据门：后端全量 `pytest tests -q` 通过，结果 `1888 passed, 11 skipped, 12 deselected`；前端 `npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过，当前 Vitest 结果为 `52 passed` test files、`234 passed` tests；Phase B readiness 守卫 `36 passed`。Phase C 已使用非 demo production key 执行 `scripts/production_non_token_e2e_check.py --execute`，结果 `50 passed, 4 skipped`；其中 `library-portfolio` 的 L4B 待审素材回读检查因当时生产无 `pending_review` 资产按证据门禁跳过。随后用户给出精确授权，已完成 Momcozy 消毒器 3 张 poyo `gpt-image-2` 图片 + 1 条 poyo `seedance-2` 15 秒竖版图片驱动视频的 `L4-authorized-live` smoke：`tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json` 显示 `status=submitted`、`provider_call_executed=true`、`blocked_reasons=[]`。产物已同步到生产租户待审目录并完成 L4B 只读回读：`tmp/outputs/l4b-production-readback-20260611-160827.json` 显示 `pending_review_count=4`、`final_work_total=0`，生产 Playwright `library-portfolio.prod.spec.ts` 结果 `2 passed`。随后执行 `L4C-1` Fast Mode 最小扩展 token smoke：`tmp/outputs/l4c-fast-mode-token-smoke-summary-20260611-162852.json` 显示 `provider_call_executed=true`、`token_smoke_executed=true`、Playwright `3 passed, 1 skipped`，两个 poyo Seedance 任务均完成且未观察到 submit retry；但该 spec 内含两个 submit 用例，实际 submit 计数为 `2`，且 Fast Mode 当时把产物写入 `output/fast_mode` 而不是 `pending_review`。本轮已补 `L4C-1R` single-submit / retry=0 / pending_review 守卫；首次 guarded run 因生产 volume 权限在视频 provider 之前失败，权限修复后经用户重新授权执行 retry，`tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json` 显示 `decision=passed`、Playwright `1 passed`、任务 `fast_1781169431_7e4af0b5` 完成，poyo task `T17OTAHIXMPBNYXX` 仅 submit 1 次且 `poyo_retrying_submit_count=0`，产物为 tenant-scoped `pending_review` / `creation_intermediate`，未进入 `final_work`。随后执行 `L4C-2` S2 no-media single-submit：`tmp/outputs/l4c-2-s2-no-media-single-submit-summary-20260611-174120.json` 显示 `decision=failed_stopped`，Playwright 30s timeout 后发现生产 S2 `enable_media_synthesis=false` 仍进入 poyo image generation，已产生 3 个 poyo image task；已立即重启 backend 止损，未观察到 Seedance 视频日志、未发现这些 task 的落盘产物。根因修复已最小部署到生产 `src/pipeline/s2_brand_pipeline_v2.py`，生产 health 恢复 200；随后经用户重新授权执行 `L4C-2R` after-fix single-submit，`tmp/outputs/l4c-2r-s2-no-media-single-submit-summary-20260611-095826.json` 显示 `decision=passed`、Playwright `1 passed (11.1s)`，S2 开始后 poyo/Seedance/TTS/assemble/keyframe 执行态计数均为 `0`，DeepSeek 文本请求计数为 `2`，远端只新增 `pipeline_states/s2_momcozy_1781172006.json` 且媒体路径字段为空。随后执行 `L4C-3` S1 no-media single-submit 的前置最小代码同步并 hash verify 通过，但唯一一次授权 live submit 返回 HTTP 500；生产日志根因为 `ImportError: cannot import name 'MAX_CLIPS_PER_DEMO' from 'src.config'`，provider 执行态计数均为 `0`，没有第二次提交。`L4C-3R-prep` 已同步 `src/config.py`、重启 backend、hash verify 和容器 import smoke 通过；随后经用户重新授权执行 `L4C-3R`，Playwright `1 passed (8.3s)`，`/scenario/s1` 返回 200，S1 no-media 在 keyframe 前停止，媒体字段与近期媒体文件均为空；但同一日志窗口内存在后台 admin health check 对 poyo `/v1/models` 和 SiliconFlow `/v1/models` 的探测，因此只能声明业务路径和媒体生成边界通过，不能声明整个日志窗口绝对无 provider-looking 日志。随后用户授权 `L4C-3H-prep`，已同步 `src/config.py` 与 `src/routers/admin/logs.py`，重启 backend、health/hash verify 通过，并在 370 秒 no-submit 观察窗口中确认 DeepSeek/poyo/SiliconFlow 外部 HTTP、poyo submit、Seedance、TTS、assemble、keyframe 与 gate candidate 日志均为 `0`。所有产物仍未发布、未写入 approved brand token、未做 delivery acceptance；实际扣费只能以 provider 控制台为准。

本次新增状态：用户随后授权并执行 `L4C-4` S1 no-media clean-log single-submit token smoke。唯一一次 Playwright live spec 业务断言通过，`/scenario/s1` 返回 200，6 分钟窗口内 DeepSeek 文本请求 `2` 次，`api.poyo.ai`、`api.siliconflow.cn`、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate 的执行级计数均为 `0`；state 显示 `enable_media_synthesis=false`、媒体路径全空、`final_video_path` 为空、`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。但日志窗口仍出现 8 行媒体 skill `registered` 噪音，包含 Seedance/TTS/assemble/keyframe 词元，因此 `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-summary-20260611-230535.json` 判定为 `failed_strict_clean_log_registration_noise`。随后用户授权 `L4C-4R-prep`，本轮只同步 `src/pipeline/__init__.py` 与 `src/pipeline/s1_product_pipeline.py`，远端原文件已备份到 `/opt/ai-video/backups/l4c4r-prep-s1-logging-20260612-000910/`，backend 已重启，生产 `/api/health` 返回 `ok`，本地/远端/容器 hash verify 通过；370 秒 no-submit 日志窗口内 `/scenario` submit、DeepSeek/poyo/SiliconFlow 外部 HTTP、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate 和媒体 skill `registered` 计数均为 `0`。证据摘要为 `tmp/outputs/l4c-4r-prep-s1-logging-import-hygiene-sync-summary-20260612-000910.json`，`decision=passed`。随后用户授权 `L4C-4R` 同一单 spec clean-log 复验；`tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-summary-20260612-001.json` 固化 `decision=passed`，Playwright `1 passed (11.7s)`，spec 观察 submit 次数为 `1`，生产 label `s1_1781229202_7b5148d1`，370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai`、`api.siliconflow.cn`、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration 和媒体 skill `registered` 均为 `0`。随后用户授权 `L4C-5` S2 no-media clean-log single-submit；`tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-summary-20260612-002.json` 固化 `decision=passed`，Playwright `1 passed (7.2s)`，spec 观察 submit 次数为 `1`，生产 label `s2_momcozy_1781230204`，370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai`、`api.siliconflow.cn`、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration 和媒体 skill `registered` 均为 `0`。当前可声明 L4C-4R S1 no-media 与 L4C-5 S2 no-media clean-log single-submit 通过；不得外推为 S1 media/gate、S3-S5、完整 token suite、发布、delivery acceptance 或 approved brand token。

2026-06-14 补充收口：`L4C-6` S3 no-media、`L4C-7` S4 no-media 与 `L4C-8R` S5 no-media single-submit clean-log 均已完成并在 runbook 中登记；`L4D-5Y` 已完成 S2 bounded media provider smoke（1 次 scenario submit、1 个 poyo image job、1 个 poyo Seedance job，停在 `seedance_clips`），`L4D-5Z` 已完成同批产物的 `/api/portfolio` 与 `/library?tab=materials` 只读回归，matching `final_work=0`。PR `#2` 已合并，历史执行分支 `codex/s1-continuity-storyboard` 的本地与远端分支已删除，并以 `8d4d2c0` 归档分支清理记录。当前默认下一步不是追加 provider 消耗，而是 no-provider 的文档、CI/read-only guard 与证据索引收口；任何 S2 full media、S1/S3/S4/S5 media generation、TTS、assemble、quality audit、publish 或 delivery acceptance 都必须重新定义范围、预算、止损和精确授权。

2026-06-16 Dependabot 补充收口：Dependabot 队列当前 open PR 数为 `0`。PR `#13` (`eslint@10.5.0`) 与 PR `#11` (`typescript@6.0.3`) 已在最终复核后关闭为 `upstream-blocked`，均保留 `dependencies`、`frontend`、`blocked-upstream` 标签和 closeout 评论。PR `#13` 的 `Frontend quality gate` 在 `react/display-name` 规则加载时报 `contextOrFilename.getFilename is not a function`，根因为当前 `eslint-config-next` 依赖链中的 `eslint-plugin-react` / `eslint-plugin-import` / `eslint-plugin-jsx-a11y` 尚未声明 ESLint 10 兼容；PR `#11` 在 `npm ci` 阶段被 `openapi-typescript@7.13.0` 的 `typescript@^5.x` peer dependency 阻塞。两者均不得通过 `--force` 或 `--legacy-peer-deps` 绕过，后续只在上游依赖发布兼容版本并由 Dependabot 重新开 PR 后重新复核。

2026-06-16 ToolBox checklist 漂移收口：`docs/workflows/ai-video-toolbox-productization-plan-stable.md` 已将 T0-T8 checklist 从历史待办态同步为完成态，并补充边界说明。该完成态只表示工具箱 `L2-fixture-or-dry-run`、preflight、job ledger、audit summary 与 refs-only injection 已实现；真实 provider 调用、live smoke、approved brand token、delivery acceptance 和 publish 仍未授权、未执行。

2026-06-16 默认生产 E2E strict read-only no-provider baseline 收口：先为 `scripts/production_non_token_e2e_check.py` 增加 `--strict-read-only`，在保持 `RUN_TOKEN_SMOKE=0` 与 `@token-smoke` 默认跳过的同时排除 `P4-4` error-path POST tests；随后用户授权执行 `TODO-P0-3 strict read-only no-provider baseline`。生产 Playwright 结果为 `46 passed, 2 skipped`，本地执行日志 `tmp/debug/todo-p0-3-strict-readonly-playwright-20260616162614.log`、本地摘要 `tmp/debug/todo-p0-3-strict-readonly-summary-20260616082614.json`、生产 backend 日志 `tmp/debug/todo-p0-3-strict-readonly-backend-20260616163427.log` 与结构化统计 `tmp/debug/todo-p0-3-strict-readonly-log-summary-20260616082614.json` 均已生成。统计显示 `non_get_count=0`、`scenario_submit_count=0`、`fast_submit_count=0`、provider/publish/delivery/approved brand token 禁止项计数为 `0`。边界：前端背景 `GET /api/admin/auth/session` 返回 `401` 共 `37` 次；portfolio 为验证待审素材未进入正式作品，执行 `GET /portfolio?...kind=final_work` 只读查询 `9` 次，`final_work` 写入/匹配仍为 `0`。本轮未执行 provider 调用、未触发 `/api/scenario/*` submit、未触发 Fast Mode submit、未发布、未做 delivery acceptance、未写入 approved brand token。

2026-06-16 L4D-5Y/L4D-5Z 证据索引复核收口：按 `TODO-P0-4` 授权只读核对 `tmp/debug` 证据、portfolio/read-only evidence 与 runbook 文档一致性。`L4D-5Y` bounded S2 provider smoke 已由 final summary、readback 与 provider-boundary gate 交叉验证：仅 1 次 `/api/scenario/s2` submit，poyo HTTP submit 总数为 `2` 且仅对应本轮 1 个 image job + 1 个 Seedance video job，readback 计数 `image=1`、`video=1`，`provider_max_retries=0`，停止点为 `seedance_clips`，产物位于 tenant-scoped `pending_review`，`final_work` 匹配数为 `0`，publish/delivery/approved brand token 禁止项计数为 `0`。`L4D-5Z` frontend/library read-only regression 与 refined log gate 均通过：Playwright `3 passed`，只读验证同批 pending_review 视频/keyframe 可见，poster cache 仅作为 `thumbnail_path`，matching `final_work=0`，scenario/Fast submit、provider、mutating publish/delivery、admin health/media 背景请求禁止项均为 `0`。证据边界保持不变：本复核不代表 S2 full media/final assembly、S1/S3/S4/S5 media generation、TTS、thumbnail、assemble、media quality audit、publish 或 delivery acceptance 已执行。

2026-06-16 Production key 生命周期治理收口：按 `TODO-P0-5R` 授权只处理 masked key `-NSK...4Y9A`。生产 DB 元数据确认该 key 属于 `momcozy-marketing`，描述为 `l4d5r-s2-bounded-media-smoke-20260612`，创建于 `2026-06-12T22:35:31.044877`，撤销前 `expires_at=null`、`revoked_at=null`、状态为 `active_no_expiry`。本轮已在生产 DB 将同一 key 的 `revoked_at` 设置为 `2026-06-16T23:55:49.350863`，撤销后只读 `GET /api/portfolio/?limit=1` 返回 `401 Invalid or expired API key`，并删除本地明文 env 文件 `tmp/debug/.l4d5r-playwright-key.env`。sanitized summary 为 `tmp/debug/todo-p0-5r-key-lifecycle-closeout-summary-20260616235720.json`，记录 `key_material_logged=false`、provider/scenario/Fast submit/publish/delivery/approved brand token 写入均为 `false`。

2026-06-17 P2 多租户隔离本地层收口：`TODO-P2-2` 已完成第一层 no-provider 验收。只运行本地 unit/fixture 测试 `.venv/bin/pytest tests/test_concurrency_isolation.py tests/test_auth_context.py tests/test_p0_media_tenant_security.py tests/test_backend_route_auth_contract.py -q`，结果 `24 passed`。覆盖范围包括 request-scoped provider API key `contextvars` 并发隔离、tenant_id contextvar 并发隔离、auth tenant 持久化与 cross-tenant state 拒绝、tenant-scoped pending_review/portfolio/assets 隔离、metrics repository tenant filter，以及 backend route auth contract。`tests/loadtest_multi_tenant.py` 仍仅作为 locust soak/load 脚本保留；本轮未执行生产压测、未创建或使用 production API key、未触发 provider、未执行 `/api/scenario/*` submit 或 Fast Mode submit。

2026-06-17 P2 Quality ML 本地 no-provider readiness 修复收口：`TODO-P2-3A` 此前失败根因为 `tests/test_media_tools.py` 的 mock-mode 测试未显式隔离外部工具探测，且 `src/tools/video_downloader.py` 的 `download_and_transcribe()` 只检查 `"[MOCK]"`，无法识别 `_mock_metadata()` 返回的 `"[MOCK_DOWNLOAD ...]"` synthetic path，导致本地已安装 `faster-whisper` 时 fake path 进入真实 PyAV 解码。现已最小修复：产品代码改为显式识别 mock download marker，测试 fixture 强制 mock 模式，并新增回归测试保证 mock download path 不会进入真实 transcription backend。复跑 import smoke 时使用 `DATABASE_URL=`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，`src.quality.clip_alignment`、`src.quality.nr_quality`、`src.quality.scene_analysis`、`src.quality.face_consistency`、`src.quality.safe_zone`、`src.skills.media_quality_audit`、`src.routers.health` 均 import 成功，`/health` 的 `media_tools` contract 可返回，`ClipAligner` 初始化仍保持 lazy-load，不下载权重；sanitized summary 为 `tmp/debug/todo-p2-3a-quality-ml-local-readiness-after-fix-20260617092804.json`，closeout summary 为 `tmp/debug/todo-p2-3a-quality-ml-local-after-fix-closeout-20260617092838.json`。随后运行目标集 `DATABASE_URL= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/pytest tests/test_health_media_tools.py tests/test_clip_alignment.py tests/test_media_tools.py tests/test_quality_signals.py -q`，结果 `54 passed`。证据等级保持 `L2-fixture-or-dry-run`；本轮未访问生产容器、未调用 provider、未执行 `/api/scenario/*` submit 或 Fast Mode submit，不外推为生产容器 Quality ML 可用性。

2026-06-17 P2 CloudBase / Render 替代部署路径本地 docs/config drift 审计：`TODO-P2-4` 已完成本地文档与配置层复核，不部署。`render.yaml` 可被 PyYAML 正常解析，仍是 backend-only Render Blueprint，指向 `Dockerfile.backend`，`DEFAULT_LLM_PROVIDER=deepseek`，`API_KEY` 由 Render 生成，`CORS_ORIGINS` 与 `DATABASE_URL` 仍为空占位；但该 blueprint 未定义 frontend、rendering、nginx 或 canonical domain routing，且 `buildFilter` 未覆盖 `Dockerfile.backend` 会 COPY 的 `migrations`、`strategy_source`、`rendering` 等触发路径，因此只可作为 overseas backend prototype reference，不能作为 canonical production deploy。`deploy/tencent-cloudbase.md` 与 `deploy/CLOUDBASE_STEP_BY_STEP.md` 仍可作为 CloudBase 手动部署参考，但默认 GitHub Pages URL、`ai_video_demo_2026` demo key 与 `https://zjgulai.github.io` CORS 口径已不是当前 production auth/tenant smoke 口径；使用前必须替换为目标前端域名、非 demo key、真实 persistence/object storage 策略。`docs/deploy/cloudbase.md` 是更早 legacy reference，含手动镜像推送、`web/dist` static export 与 `sk-...` placeholder，不作为当前执行 SOP。Lighthouse 仍是 canonical target。sanitized summary 为 `tmp/debug/todo-p2-4-alt-deploy-doc-config-audit-20260617100616.json`；本轮未执行生产部署、provider 调用、`/api/scenario/*` submit、Fast Mode submit、发布、delivery acceptance 或 approved brand token write。

2026-06-17 P2 publish / delivery acceptance / approved brand token 本地 fail-closed guard 收口：`TODO-P2-5` 已完成本地代码层最小修复。此前 `ProductionJobLedger`、`commercial_gate`、ToolBox contract 已能表达“生成成功不等于交付/发布”，但真实 publish 路由 `POST /distribution/publish` 与 `POST /publish/{video_id}` 只校验 API key，未强制消费 human-sourced `delivery_acceptance`。现已在 `src/routers/distribution.py` 增加统一守卫：发布前必须存在 `source=human`、human reviewer、`delivery_accepted=true`、`publish_allowed=true`，且 `approved_brand_token_write` 不得为 true；LLM-sourced suggestion / approval 字段不能作为发布授权。新增 `tests/test_distribution_publish_guard.py` 覆盖无人工验收、LLM 来源、approved brand token write claim、合法人工验收后才调用 connector，以及 `/publish/{video_id}` 在缺少人工验收时先于文件查找 fail-closed。`tests/test_publish_e2e.py` 的真实 `/distribution/publish` 示例也已补齐人工验收字段。sanitized summary 为 `tmp/debug/todo-p2-5-publish-boundary-local-guard-20260617102120.json`；`ruff` 目标检查通过，目标 pytest 集 `48 passed`。证据等级为 `L2-fixture-or-dry-run`；本轮未执行真实发布、delivery acceptance、approved brand token write、生产部署、provider 调用、`/api/scenario/*` submit 或 Fast Mode submit。

2026-06-17 P2 metrics / webhook / analytics 本地 no-provider readiness 收口：`TODO-P2-1A` 已完成本地 fixture 层验证。运行 `DATABASE_URL= .venv/bin/pytest tests/test_metrics_dashboard.py tests/test_video_metrics_integration.py tests/test_metrics_repository.py tests/test_metrics_poller.py tests/test_webhook_manager.py tests/test_portfolio_mechanism.py tests/test_agents.py -q`，结果 `109 passed`。覆盖 `/metrics/*` 与 `/dashboard/overview` 的本地路由、空数据、存储禁用契约、`VideoMetricsRepository`、`MetricsPoller` bounded concurrency 与单任务失败隔离、`WebhookManager` URL 安全与 dispatch failure isolation、portfolio hook 以及 analytics agent mock 输出。sanitized summary 为 `tmp/debug/todo-p2-1-metrics-webhook-analytics-local-readiness-20260617104654.json`。证据等级为 `L2-fixture-or-dry-run`；`MetricsPoller` 的 TikTok/Shopify fetcher 仍是 stub，未执行真实 platform metrics pull，未配置 webhook.site 或外部接收端，未验证生产 PG/Alembic 表状态、生产 scheduler、生产 `/metrics/*` readback 或前端 `PerformanceDashboard` 真数据渲染；未执行生产部署、provider 调用、`/api/scenario/*` submit、Fast Mode submit、真实 publish、delivery acceptance 或 approved brand token write。

2026-06-17 P2 metrics / webhook / analytics 生产只读探测：`TODO-P2-1B` 已执行 GET-only probe，结果为部分通过、authenticated business metrics readback 阻塞。生产 `/api/health` 返回 `200`，`status=ok`，`persistence.backend=postgresql`、`pg_available=true`、`tables_verified=true`；生产 Prometheus `/metrics` 返回 `200`，可见 runtime/process samples。使用本机现有 `deploy/lighthouse/.env.prod` 与 `.env` 中的 legacy `API_KEY` 候选访问 `/api/dashboard/overview?days=7` 与 `/api/metrics/todo-p2-1-readonly-probe-nonexistent` 均返回 `401`，因此不得声明 authenticated dashboard 或 video metrics readback 已通过。静态代码复核显示 `src/api.py` startup 未注册 `MetricsPoller.pull_all` 周期任务，`src/routers/metrics.py` 仅提供手动 `POST /metrics/pull` 触发入口，本轮未调用该 POST；`src/tasks/metrics_poller.py` 的 TikTok/Shopify fetcher 仍为 stub。sanitized summary 为 `tmp/debug/todo-p2-1b-production-readonly-metrics-webhook-analytics-20260617105544.json`；本轮未创建 production key、未执行 POST/PUT/PATCH/DELETE、未调用 provider、未执行 `/api/scenario/*` submit、Fast Mode submit、真实 publish、delivery acceptance、approved brand token write 或 webhook 外发。

2026-06-17 P2 metrics / webhook / analytics authenticated readback 尝试：`TODO-P2-1C` 已按授权创建 1 个 `momcozy-marketing` 临时 non-demo production key，写入 `expires_at`，只执行 GET 探测并立即撤销。`/api/health` 返回 `200`，Prometheus `/metrics` 返回 `200`；但 `/api/dashboard/overview?days=7` 与 `/api/metrics/todo-p2-1-readonly-probe-nonexistent` 均返回 `503 Authentication backend unavailable`。撤销后同 key 只读认证返回 `401 Invalid or expired API key`，生产 DB 复核该 key lifecycle 为 `revoked`。根因已用容器内只读 introspection 复现：`api_keys.expires_at` 是 `timestamp without time zone`，asyncpg 返回 `tzinfo=None`，而 `verify_api_key()` 与 `datetime.now(UTC)` 比较会抛 `TypeError: can't compare offset-naive and offset-aware datetimes`。因此当前不能安全使用带过期时间的 production API key 做 authenticated readback；需要先修复 API key `expires_at` datetime 边界。sanitized summaries 为 `tmp/debug/todo-p2-1c-authenticated-metrics-dashboard-readonly-20260617120500.json` 与 `tmp/debug/todo-p2-1c-authenticated-readonly-root-cause-20260617133330.json`；本轮未展示明文 key，未调用 `/metrics/pull`，未执行 provider、`/api/scenario/*` submit、Fast Mode submit、webhook 外发、生产部署、publish、delivery acceptance 或 approved brand token write。

2026-06-17 P2 API key `expires_at` datetime 边界本地修复：`TODO-P2-1D` 已完成本地代码层最小修复。`src/routers/_deps.py` 新增 `_as_utc_datetime()`，将 DB 返回的 naive datetime 按 UTC 规范化后再比较，避免生产 `timestamp without time zone` 与 `datetime.now(UTC)` 比较抛 `TypeError`。`tests/test_auth_context.py` 新增 naive future 可通过、naive expired 被拒绝、aware future 可通过三类回归测试。验证：`ruff` 目标检查通过，`tests/test_auth_context.py` 结果 `9 passed`，auth/route/metrics 目标集 `83 passed`。sanitized summary 为 `tmp/debug/todo-p2-1d-api-key-expires-datetime-local-fix-20260617134324.json`。证据等级仅为 `L2-fixture-or-dry-run`；本轮未同步生产、未重启 backend、未创建新的 production key、未做 authenticated production readback，未调用 provider、`/api/scenario/*` submit、Fast Mode submit、`/metrics/pull`、webhook 外发、publish、delivery acceptance 或 approved brand token write。

2026-06-17 P2 API key `expires_at` 修复生产同步与 authenticated readback 复验：`TODO-P2-1E` 已按授权只同步 `src/routers/_deps.py` 到生产，远端原文件备份到 `/opt/ai-video/backups/todo-p2-1e-api-key-expires-20260617142804/`，重启 `ai_video_backend` 后 `/api/health` 返回 `200` 且 Docker health 为 `healthy`。hash verify 通过：本地、远端 `/opt/ai-video/src/routers/_deps.py` 与容器 `/app/src/routers/_deps.py` 均为 `c1f9b884a73fcd01dc1a90b351892ae55a2254e5fa130f3799af95a3b544f94e`。随后创建 1 个 2 小时临时 non-demo production key（tenant=`momcozy-marketing`，masked=`BSot...Baas`，key_id=`c892dd23-01f8-452f-bc0f-c433e13de0b3`），只执行 GET：`/api/health=200`、`/metrics=200`、`/api/dashboard/overview?days=7=200`、`/api/metrics/todo-p2-1-readonly-probe-nonexistent=200`，未再出现 503。验证后已撤销该 key，post-revoke readback 返回 `401 Invalid or expired API key`，生产 DB lifecycle 为 `revoked`。sanitized summary 为 `tmp/debug/todo-p2-1e-production-sync-authenticated-readback-20260617143000.json`。本轮未执行全量生产部署、provider 调用、`/api/scenario/*` submit、Fast Mode submit、`/metrics/pull`、webhook 外发、publish、delivery acceptance 或 approved brand token write。

> 上一次盘点：2026-06-09 — 完成综合技术债务审计（221 项发现，报告见 `docs/claude/debt-audit/debt-audit-report-2026-06-09.md`），并执行首批治理修复。详细执行记录见 `docs/claude/debt-audit/debt-remediation-execution-plan-2026-06-09.md`。

> 更早盘点：2026-06-03 — 补充 AI 商业化视频生成技术调研、长视频生产覆盖审计与工具库架构规格，作为 S1-S5 后续无代码阶段方案内化依据。

## 当前执行入口

- **当前长期 TODO 来源**：本文件的“完整 TODO list”继续维护项目长期 P1/P2 缺口。
- **当前 AI Video 2.0 执行入口**：`docs/superpowers/plans/2026-06-04-ai-video-2-0-remaining-implementation-plan.md` 是 C15-C22 的原始分步计划；[`docs/workflows/ai-video-toolbox-productization-plan-stable.md`](../workflows/ai-video-toolbox-productization-plan-stable.md) 追踪工具箱 T1-T9/C23；[`docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md`](../workflows/ai-video-project-2-0-e2e-test-plan-stable.md) 是“真实 provider + 前后端联动”E2E 正式计划；[`docs/workflows/l4d-real-media-provider-evidence-index-stable.md`](../workflows/l4d-real-media-provider-evidence-index-stable.md) 是当前 L4D 真实媒体证据索引；[`docs/workflows/ai-video-project-2-0-final-self-proof-stable.md`](../workflows/ai-video-project-2-0-final-self-proof-stable.md) 记录 C1-C36 自证状态。当前已完成 `L4C` S1-S5 no-media clean-log single-submit 阶段、Fast Mode single-submit pending_review token smoke、L4D image-only/video-only/image+video/S2 bounded media provider smoke 和 frontend read-only readback。仍不得外推为 S1/S3/S4/S5 media generation、S2 full media/final assembly、gate、TTS、assemble、quality audit、publish、delivery acceptance 或 approved brand token。
- **L4C/L4D 下一阶段入口**：`configs/l4c-token-smoke-plan-template.json` + `scripts/l4c_token_smoke_plan.py` 仍是 L4C no-execute 计划验证门。L4D 当前默认停止在 S2 bounded media + frontend read-only readback，下一步只做 no-provider 的文档、CI/read-only guard 与证据索引收口。任何新的 provider submit、full media、poster/quality、publish 或 delivery acceptance 都必须重新定义目标、预算、submit/job cap、artifact disposition、失败止损和精确授权。
- **历史计划文档用途**：`docs/workflows/`、`docs/architecture/`、`.kiro/plan/` 中的旧 Sprint / Phase / TODO 只保留为决策背景、事故复盘或历史证据；除非本文件重新引用，否则不作为当前执行计划。
- **当前研究 / 架构 / 流程引用**：2026-06-03 至 2026-06-04 新增 `docs/research/ai-video-commercial-technology-research-review-20260603.md`、`docs/research/ai-video-longform-production-research-audit-review-20260603.md`、`docs/research/aihot-image-video-product-technology-research-review-20260604.md`、[`docs/architecture/ai-video-commercial-toolbox-architecture-review-20260603.md`](../architecture/ai-video-commercial-toolbox-architecture-review-20260603.md)、[`docs/architecture/brand-asset-token-contract-review-20260603.md`](../architecture/brand-asset-token-contract-review-20260603.md)、[`docs/architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md`](../architecture/provider-prompt-compiler-media-job-ledger-review-20260603.md)、[`docs/architecture/quality-contract-brand-rights-audit-review-20260603.md`](../architecture/quality-contract-brand-rights-audit-review-20260603.md)、[`docs/workflows/ai-video-commercial-toolbox-phase0-backlog-review-20260603.md`](../workflows/ai-video-commercial-toolbox-phase0-backlog-review-20260603.md)、[`docs/workflows/brand-data-asset-directory-intake-review-20260603.md`](../workflows/brand-data-asset-directory-intake-review-20260603.md)、[`docs/workflows/ai-video-project-2-0-cross-analysis-plan-review-20260603.md`](../workflows/ai-video-project-2-0-cross-analysis-plan-review-20260603.md) 与 [`docs/workflows/ai-video-project-2-0-code-readiness-plan-review-20260604.md`](../workflows/ai-video-project-2-0-code-readiness-plan-review-20260604.md)，用于后续 S1-S5 工具库、Market Signal Intelligence、Brand Asset Token、Provider Prompt Compiler、Production Job Ledger、Quality Contract、长视频生产对象、品牌数据资产目录接入和 Project 2.0 代码前实施计划；十一份均为 `review` 状态，不替代本文件的 TODO list。
- **真实调用授权边界**：L4A/L4B 首轮已完成；任何继续扩大到 S1-S5、Fast Mode、gate、media/poster/quality 的真实调用都归入 `L4C`，必须先通过 no-execute 计划验证并重新取得精确授权、预算和产物处置边界。
- **50-loop 迭代边界**：P1-16~P1-65 只允许修 CI、测试、文档、静态防护、本地 hermetic 质量门；不得触发 `/api/fast/generate`、`/api/fast/submit`、`/scenario/*` 真实生成、gate candidate 生成、上传、发布或 POYO 直连脚本。该边界已在 `P1-65` 复核中闭环。

## 2026-06-14 执行 TODO（当前权威）

本节是 2026-06-14 之后的执行矩阵。执行原则保持“执行一步、测试一步、验收一步”：每一项只在对应证据通过后推进；任何生产 submit、provider 调用、发布、delivery acceptance 或 approved brand token 写入都必须另行取得精确授权。

### P0：立即收口，不消耗 provider

| ID | 任务 | 当前状态 | 执行边界 | 验收口径 |
|---|---|---|---|---|
| TODO-P0-1 | Dependabot PR 分批复核与合并 | closed_upstream_blocked | all-green 低风险 PR 已完成分批合并；失败或 unstable PR 已记录阻塞并关闭，不合并 | 当前 open Dependabot PR 为 `0`；PR `#13` 与 `#11` 已关闭为 upstream-blocked；恢复条件是上游发布兼容版本、Dependabot 重新开 PR 并重新跑绿 CI |
| TODO-P0-2 | ToolBox 产品化计划 checklist 漂移收口 | completed_docs_sync | 已对齐 `docs/workflows/ai-video-toolbox-productization-plan-stable.md` 的状态表与 TODO；未改业务代码 | 文档不再同时表达“已实现”和“未完成”的冲突状态；真实 provider / live smoke / publish 边界仍为未授权 |
| TODO-P0-3 | 默认生产 E2E no-provider baseline | strict_read_only_passed | 已用 `--strict-read-only` 运行 `RUN_TOKEN_SMOKE=0` 生产 E2E；排除 `@token-smoke` 与 `P4-4` POST error-path tests | Playwright `46 passed, 2 skipped`；`non_get_count=0`；scenario/Fast submit、provider、publish、delivery、approved brand token 均为 `0`；`GET /api/admin/auth/session` 401 背景请求 `37` 次，`GET /portfolio?...kind=final_work` 只读查询 `9` 次且 `final_work` 写入/匹配为 `0` |
| TODO-P0-4 | L4D-5Y/L4D-5Z 证据索引复核 | completed_evidence_index_verified | 已只读核对 `tmp/debug`、portfolio/read-only evidence 与 runbook 文档一致性；未执行 provider、submit、发布或生产部署 | `L4D-5Y` 仅证明 S2 bounded media 到 `seedance_clips`，image job=1、video job=1、provider retry=0、产物进入 tenant-scoped `pending_review`；`L4D-5Z` 仅证明 frontend/library read-only 可见性与 refined log gate 通过；不外推 full media/S1-S5/publish/delivery |
| TODO-P0-5 | Production key 生命周期治理 | completed_key_lifecycle_closed | 已撤销 active masked key `-NSK...4Y9A`，并删除本地明文 env 文件；未执行 provider、submit、发布或生产部署 | 撤销前生产 DB 显示该 key 为 `active_no_expiry`；撤销后 `revoked_at` 已设置，post-revoke 只读认证返回 `401 Invalid or expired API key`；sanitized summary 未记录明文 key/hash |

### P1：受控真实链路补证，需逐项授权

| ID | 任务 | 当前状态 | 授权要求 | 验收口径 |
|---|---|---|---|---|
| TODO-P1-1 | S1 bounded media single-submit smoke | blocked_by_authorization | 需限定 submit=1、image/video job cap、预算、artifact_disposition=pending_review、retry=0 | 只进入 tenant-scoped `pending_review` 或 quarantine；`final_work=0`；无 publish/delivery/token write |
| TODO-P1-2 | S3 bounded media single-submit smoke | blocked_by_authorization | 同上，且先做 no-provider readiness 与 import/log gate | 只证明 S3 bounded media，不外推 S1/S2/S4/S5 |
| TODO-P1-3 | S4 bounded media single-submit smoke | blocked_by_authorization | 同上，重点验证 live-shoot continuity 输入和 media stop point | 无 TTS/assemble/audit/publish，产物 pending_review |
| TODO-P1-4 | S5 bounded media single-submit smoke | blocked_by_authorization | 同上，重点验证 vlog strategy、model selector 与 keyframe input | 无 full-chain assembly，产物 pending_review |
| TODO-P1-5 | S2 full-media 分段计划 | blocked_by_plan | 先拆成 TTS、thumbnail、assemble、media_quality_audit、final assembly 五个 stop point | 每个 stop point 单独 spec、单独预算、单独止损；不得一次跑完整链 |
| TODO-P1-6 | S1 gate / step-by-step 真实 token flow | blocked_by_plan | 先做 no-provider readiness，再授权 gate candidate 单步 | gate candidate 数量、重试、产物处置和日志门禁全部可计数 |

### P2：工程韧性与产品闭环

| ID | 任务 | 当前状态 | 执行边界 | 验收口径 |
|---|---|---|---|---|
| TODO-P2-1 | metrics / webhook / analytics 真实闭环 | production_auth_readback_passed | 本地/fixture readiness 已通过；API key `expires_at` 修复已同步生产并通过 authenticated GET readback；真实 metrics 事件链仍未执行 | `109 passed` 覆盖 metrics router/repository/poller、webhook manager、portfolio hook 与 analytics agent；生产 `/api/health` 显示 PostgreSQL `tables_verified=true`，`/metrics` 可达；`TODO-P2-1E` authenticated `/api/dashboard/overview` 与 `/api/metrics/{video_id}` 均返回 200，post-revoke 返回 401；但 `MetricsPoller` 未注册 startup scheduler，TikTok/Shopify fetcher 仍为 stub，未调用 `/metrics/pull`，webhook.site 与前端真数据未验证 |
| TODO-P2-2 | 多租户并发与 API key 隔离压测 | local_no_provider_passed | 本地 unit/fixture 层已通过；生产只读压测仍需单独授权，不运行 locust 生产压测 | `24 passed` 覆盖 provider API key/tenant contextvars 并发隔离、auth tenant 持久化、cross-tenant state 拒绝、portfolio/assets/metrics tenant filter 与 route auth contract；无 provider、submit、production key 或生产压测 |
| TODO-P2-3 | Quality ML 依赖生产可用性验证 | local_no_provider_passed | 本地 import smoke 与目标 pytest 集已通过；生产容器 smoke 未执行 | after-fix summary `tmp/debug/todo-p2-3a-quality-ml-local-readiness-after-fix-20260617092804.json`；closeout summary `tmp/debug/todo-p2-3a-quality-ml-local-after-fix-closeout-20260617092838.json`；目标集 `54 passed`；证据等级仅为 `L2-fixture-or-dry-run`，不外推生产容器可用性 |
| TODO-P2-4 | CloudBase / Render 替代部署路径复核 | docs_config_audited_no_deploy | 已完成本地 docs/config drift 审计；不部署、不 live verify | `render.yaml` YAML parse OK 但仅为 backend-only prototype reference，`DATABASE_URL` 为空且 build trigger 覆盖不完整；CloudBase 文档可作手动参考但 GitHub Pages/demo key/CORS 默认值需替换；`docs/deploy/cloudbase.md` 为 legacy reference；summary `tmp/debug/todo-p2-4-alt-deploy-doc-config-audit-20260617100616.json` |
| TODO-P2-5 | publish / delivery acceptance / approved brand token 设计复核 | local_fail_closed_guard_implemented | 已完成本地 publish 路由 fail-closed guard；不执行真实发布或生产操作 | `POST /distribution/publish` 与 `POST /publish/{video_id}` 必须携带 human-sourced `delivery_acceptance`，LLM suggestion 不可作为授权，`approved_brand_token_write=true` 被拒绝；`ruff` 目标检查通过，目标 pytest `48 passed`；summary `tmp/debug/todo-p2-5-publish-boundary-local-guard-20260617102120.json`；证据等级仅为 `L2-fixture-or-dry-run` |

### 当前禁止外推

- `L4D-5Y` 只证明 S2 bounded media 到 `seedance_clips`，不证明 S2 full media/final assembly。
- `L4D-5Z` 只证明 portfolio/library read-only 可见性与 `final_work=0`，不证明发布可用。
- `RUN_TOKEN_SMOKE=1 --list` 只证明 spec 可枚举，不证明真实 E2E 已执行。
- Dependabot checks 绿色只证明对应 PR 的 CI 通过，不自动证明生产兼容；高风险依赖仍需本地目标测试和人工合并授权。

### 本轮执行记录

- `TODO-P0-1` 已开始：PR `#6` (`yt-dlp>=2026.6.9`) 只读复核通过，diff 仅 `requirements.txt` 一行，GitHub checks 全绿，`mergeable=MERGEABLE`、`mergeStateStatus=CLEAN`，本地独立 worktree 目标测试 `tests/test_media_tools.py tests/test_health_media_tools.py` 结果 `39 passed`。尚未合并；合并需要下一步明确授权。
- PR `#6` 已在用户授权后合并到 `main`，merge commit 为 `022b15dc5884aa267c05749f2e2fdda9cfe45ce2`；合并后本地 `main` 已 fast-forward 到 `origin/main`，目标测试 `tests/test_media_tools.py tests/test_health_media_tools.py` 复跑结果 `39 passed`。
- PR `#5` (`@vitejs/plugin-react 6.0.1 -> 6.0.2`) 只读复核完成，GitHub checks 全绿，`mergeable=MERGEABLE`、`mergeStateStatus=CLEAN`，diff 仅 `web/package.json` 与 `web/package-lock.json`。本地独立 worktree 的 clean `npm ci` 超过 150 秒无输出，已终止并清理 worktree；因此本地 clean-install 验证未完成，暂不进入合并授权候选。
- PR `#10` (`alembic>=1.18.4`) 只读复核通过，diff 仅 `requirements.txt` 一行，GitHub checks 全绿，`mergeable=MERGEABLE`、`mergeStateStatus=CLEAN`。本地独立 worktree + 临时 venv 验证 Alembic `1.18.4` 可解析 migration tree（head `e4b9c1d2a6f0`，revision count `11`），并复跑 `tests/test_postgres.py::TestThreadIdSchema`，结果 `2 passed`。尚未合并；合并需要下一步明确授权。
- PR `#10` 已在用户授权后合并到 `main`，merge commit 为 `dba3ea9d3af7bf84e13d69f128c0a10cea347dc8`；合并后本地 `main` 已 fast-forward 到 `origin/main`，Alembic `1.18.4` migration tree 解析复跑通过，`tests/test_postgres.py::TestThreadIdSchema` 复跑结果 `2 passed`。
- PR `#3` (`transformers>=5.12.0`) 只读复核完成，GitHub checks 全绿，`mergeable=MERGEABLE`、`mergeStateStatus=CLEAN`，diff 仅 `requirements.txt` 一行；但该变更是生产依赖大版本更新。临时 venv 安装 `transformers>=5.12.0` 超过 120 秒无输出后已中止并清理，未完成 clean install/import 验证；PR worktree 中仅复跑现有 fallback 合约 `tests/test_clip_alignment.py`，结果 `4 passed`。暂不进入合并授权候选。
- PR `#12` (`faster-whisper>=1.2.1`) CI 失败已完成只读诊断：Python 3.11 与 3.12 失败同源，均为 `tests/test_markdown_frontmatter_compliance.py::test_fully_compliant_frontmatter_values_use_project_vocab`，断言 `source: ai+human` 不在允许集合 `{human+ai, ai, human}`。该失败与 `faster-whisper` 变更无直接关系；`origin/main` 中 `docs/workflows/2026-06-14-s1-continuity-storyboard-branch-cleanup-stable.md` 仍为 `source: ai+human`，本地工作区已修为 `source: human+ai`，本地 `tests/test_markdown_frontmatter_compliance.py` 结果 `4 passed`。该 docs-only frontmatter 修复已纳入本轮提交/推送范围，推送后需观察 PR `#12` checks 是否自动重新触发；PR `#12` 暂不进入合并授权候选。
- PR `#13` (`eslint 9.39.4 -> 10.5.0`) 已完成 upstream-blocked closeout：diff 仅 `web/package.json` 与 `web/package-lock.json`；最终复核时只有 `Frontend quality gate` 失败，其余 CI / e2e-ui checks 通过。失败日志为 `ESLint: 10.5.0` 加载 `react/display-name` 时抛 `contextOrFilename.getFilename is not a function`，堆栈位于 `eslint-config-next/node_modules/eslint-plugin-react`。2026-06-16 npm metadata 显示 `eslint-config-next@16.2.9` 仍依赖未声明 ESLint 10 兼容的 `eslint-plugin-react@7.37.5`、`eslint-plugin-import@2.32.0`、`eslint-plugin-jsx-a11y@6.10.2`；PR 已保留 `blocked-upstream` 标签、追加 closeout 评论并关闭。
- PR `#11` (`typescript 5.9.3 -> 6.0.3`) 已完成 upstream-blocked closeout：diff 仅 `web/package.json` 与 `web/package-lock.json`；最终复核时 `Frontend quality gate`、Python 3.11、Python 3.12 与 UI-only visual regression 均在 `npm ci` 前置安装阶段失败。失败根因为 `openapi-typescript@7.13.0` peer dependency 仍要求 `typescript@^5.x`，而本 PR 安装 `typescript@6.0.3`；2026-06-16 npm metadata 显示 `openapi-typescript@7.13.0` 仍为 latest 且未支持 TypeScript 6。PR 已保留 `blocked-upstream` 标签、追加 closeout 评论并关闭。

## 1.01 2026-06-11 L4B 生产只读回读已通过

- **生产同步** — 已把本轮 L4A 产物同步到生产 Docker volume 的 `output/tenants/momcozy-marketing/pending_review/momcozy_sterilizer_smoke_20260611/`，并最小同步 `src/routers/portfolio.py` 到 Lighthouse 后端。远端原 `portfolio.py` 已备份为 `/opt/ai-video/src/routers/portfolio.py.bak-20260611160250`。
- **后端重启与健康** — 只重启 `ai_video_backend`，未跑全量 deploy，未重建前端，未触发 provider。`https://video.lute-tlz-dddd.top/api/health` 恢复 200。
- **后端只读回读** — `tmp/outputs/e2e-portfolio-creation-intermediate-20260611-160526.json` 显示 `total=4`、`pending_review_count=4`，4 个资产均为 `tenant_id=momcozy-marketing`、`kind=creation_intermediate`、`category=pending_review`。`tmp/outputs/e2e-portfolio-final-work-20260611-160526.json` 显示 `total=0`，本次 smoke 资产没有进入 `final_work`。
- **前端只读回读** — 修正 `web/e2e/production/library-portfolio.prod.spec.ts`，避免测试把生产页面强制切到 demo-data；在 `RUN_TOKEN_SMOKE=0` 下复跑生产 spec，结果 `2 passed`。
- **证据摘要** — `tmp/outputs/l4b-production-readback-20260611-160827.json` 固化 L4B 结果：`provider_call_executed=false`、`pending_review_count=4`、`final_work_total=0`、`final_work_smoke_assets=0`、`playwright_result=2 passed`。
- **证据边界** — 当前可声明“本轮 L4B 生产只读回读通过”；仍不得声明商业交付完成、delivery accepted、publish allowed、approved brand token 或可直接发布。

## 1.02 2026-06-11 L4C-1 Fast Mode 最小 token smoke 已执行

- **授权范围** — 用户授权只运行 `web/e2e/production/fast-mode-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`--retries=0`，预算上限 `$2.00`，不运行 user-journey / S1 gate / S1 step-by-step / scenario multi-submit。
- **计划门禁** — `tmp/outputs/l4c-token-smoke-plan-readiness-20260611-162852.json` 显示 `blocked=false`、`ready_for_l4c_operator_review=true`，且计划只允许 `fast-mode-submit.prod.spec.ts`。
- **执行结果** — `tmp/outputs/l4c-fast-mode-token-smoke-summary-20260611-162852.json` 显示 Playwright `3 passed, 1 skipped`；两个 poyo Seedance provider task `YHUW7BP5TLUHMTC1`、`JPRCUUAFNJTK6MB6` 均完成，远程生成文件 `seedance_YHUW7BP5_ba8b.mp4`、`seedance_JPRCUUAF_f3cb.mp4` 存在。
- **重试边界** — Playwright 显式 `--retries=0`；生产日志未出现 `poyo: retrying submit+poll`，两个 provider submit 均为 `attempt=1`。
- **授权边界缺口** — 本次没有重复运行命令，也没有 Playwright retry；但授权文本中的“不做第二次提交”若按严格 submit 次数解释，本次 spec 内两个 submit 用例导致实际 submit 计数为 `2`。后续 `L4C-2+` 必须先增加 `max_submit_count=1` 守卫或拆分单 submit spec。
- **产物处置缺口** — 授权要求产物只进入 `pending_review`；当前 Fast Mode 实现把生成文件保留在 `output/fast_mode`。这些文件没有进入 `final_work`、approved brand token、delivery acceptance 或 publish flow，但 pending_review-only 存储边界未满足。
- **证据边界** — 当前可声明“L4C-1 Fast Mode submit/status 功能 smoke 通过，并暴露 submit-count 与 pending_review-only 产物处置守卫缺口”；不得声明严格单提交授权完全闭环，不得声明 S1/S2-S5/gate/media/poster/quality 已通过，不得声明 delivery accepted、publish allowed 或 approved brand token。

## 1.04 2026-06-11 L4C-1R retry after volume-permission fix 已通过

- **授权范围** — 用户重新授权只运行 `web/e2e/production/fast-mode-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`，预算上限 `$2.00`，不运行 Fast Mode multi-submit、user-journey、S1 gate、S1 step-by-step 或 scenario multi-submit。
- **计划门禁** — `tmp/outputs/l4c-1r-retry-token-smoke-plan-readiness-20260611-171600.json` 显示 `blocked=false`、`allowed_specs=["fast-mode-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`，且执行前未触发 provider。
- **生产执行** — `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-playwright-20260611-171600.log` 显示 `1 passed (8.8m)`；生产任务 `fast_1781169431_7e4af0b5` 状态为 `done`，poyo task 为 `T17OTAHIXMPBNYXX`。
- **provider 边界** — 过滤后的生产后端日志 `tmp/outputs/l4c-1r-retry-production-backend-evidence-20260611-171600.log` 显示 `poyo: submitting task` 计数 `1`、`poyo: task submitted` 计数 `1`、`poyo: retrying submit` 计数 `0`。日志中的 `poyo: polling attempt=N` 只是状态轮询次数，不是 submit retry。
- **产物处置** — 状态回读 `tmp/outputs/l4c-1r-retry-fast-mode-status-20260611-171600.json` 显示 `success=true`、`is_stub=false`、`artifact_disposition=pending_review`、`artifact_review_status=pending_review`、`artifact_storage_scope=tenant_pending_review`，文件路径为 `/app/output/tenants/default/pending_review/fast_mode/fast_1781169431_7e4af0b5/seedance_T17OTAHI_66fd.mp4`，大小 `1916459` bytes。
- **前后端回读** — 远端文件证据 `tmp/outputs/l4c-1r-retry-remote-artifact-files-20260611-171600.txt` 显示文件 owner 为 `appuser:appgroup`；`tmp/outputs/l4c-1r-retry-portfolio-creation-intermediate-20260611-171600.json` 中目标资产为 `kind=creation_intermediate`、`review_status=pending_review`，`tmp/outputs/l4c-1r-retry-portfolio-final-work-20260611-171600.json` 中本次 task `target_count=0`。
- **证据摘要** — `tmp/outputs/l4c-1r-retry-fast-mode-single-submit-summary-20260611-171600.json` 固化本轮 `L4-authorized-live` 结果：`decision=passed`、`provider_max_retries=0`、`max_submit_count=1`、`poyo_retrying_submit_count=0`。
- **证据边界** — 当前可声明“Fast Mode single-submit + pending_review artifact disposition 最小生产 token smoke 通过”；不得声明实际扣费金额、delivery accepted、publish allowed、approved brand token、S1/S2-S5/gate/media/poster/quality 已通过。任何第三次 submit 仍需重新授权。

## 1.05 2026-06-11 L4C-2 S2 no-media single-submit 失败止损

- **授权范围** — 用户授权只运行 `web/e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`，预算上限 `$1.00`，并明确 `enable_media_synthesis=false`、不允许 Seedance/TTS/assemble/media synthesis。
- **执行结果** — `tmp/outputs/l4c-2-s2-no-media-single-submit-playwright-20260611-174120.log` 显示 Playwright 在 30s test timeout 失败，未通过业务断言；没有重跑。
- **范围违背** — 生产日志 `tmp/outputs/l4c-2-s2-no-media-production-backend-evidence-after-stop-20260611-174120.log` 显示 S2 已开始，且出现 3 次 poyo image submit，task id 为 `78BSCUGXZADGMCUH`、`83WVI2HST7TOLZF0`、`E48NL40OIALQV82N`。未观察到 `seedance:` 视频生成日志。
- **止损动作** — 发现范围违背后立即重启 `ai_video_backend`，`tmp/outputs/l4c-2-s2-no-media-after-restart-clean-window-20260611-174120.log` 显示 `09:43:55Z` 后 poyo/Seedance/S2 日志为 0；生产 `/api/health` 恢复 `status=ok`。
- **产物检查** — `tmp/outputs/l4c-2-s2-no-media-remote-artifact-search-20260611-174120.txt` 未发现上述 3 个 task id 的落盘文件；近期只发现 `/app/output/pipeline_states/s2_momcozy_1781170902.json`。
- **根因与修复** — `S2BrandCampaignPipeline.run(enable_media_synthesis=False)` 原先只在结果拼装阶段跳过媒体字段，但 `StepRunner.resume()` 仍执行完整 S2 step order 到 `keyframe_images`。本轮已修复为 no-media 只运行 `keyframe_images` 之前的步骤，并补 `tests/test_s2_e2e.py` 防回归；修复文件已最小部署到生产，远端原文件备份为 `/opt/ai-video/src/pipeline/s2_brand_pipeline_v2.py.bak-l4c2-20260611174814`。
- **证据摘要** — `tmp/outputs/l4c-2-s2-no-media-single-submit-summary-20260611-174120.json` 固化 `decision=failed_stopped`、`poyo_image_submit_count=3`、`seedance_video_log_count=0`、`production_fix_deployed=true`、`rerun_performed=false`。
- **证据边界** — 不得声明 L4C-2 通过，不得声明修复已完成生产 smoke 复验，不得声明实际扣费金额、delivery accepted、publish allowed 或 approved brand token。L4C-2 复跑必须重新授权。

## 1.06 2026-06-11 L4C-2R S2 no-media after-fix single-submit 已通过

- **授权范围** — 用户重新授权只运行 `web/e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`，预算上限 `$1.00`，只允许 DeepSeek 文本调用，不允许 poyo image、Seedance、TTS、assemble 或 media synthesis。
- **计划门禁** — `tmp/outputs/l4c-2r-s2-no-media-token-smoke-plan-readiness-livekey-20260611-095826.json` 显示 `blocked=false`、`allowed_specs=["scenario-s2-no-media-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`；执行前未触发 provider。
- **生产执行** — `tmp/outputs/l4c-2r-s2-no-media-single-submit-playwright-20260611-095826.log` 显示 `1 passed (11.1s)`；外层 zsh wrapper 在测试通过后误用只读变量名 `status`，导致 shell command 非业务性返回错误，但没有重跑 spec。
- **provider 边界** — `tmp/outputs/l4c-2r-s2-no-media-production-provider-counts-refined-20260611-095826.json` 显示 S2 开始后 `poyo_http_request_count=0`、`poyo_submit_execution_count=0`、`seedance_execution_count=0`、`tts_execution_count=0`、`assemble_execution_count=0`、`keyframe_execution_count=0`；DeepSeek 文本请求计数为 `2`，`s2_complete_no_media_count=1`。
- **产物处置** — `tmp/outputs/l4c-2r-s2-no-media-recent-output-files-20260611-095826.txt` 显示远端只新增 `/app/output/pipeline_states/s2_momcozy_1781172006.json`；`tmp/outputs/l4c-2r-s2-no-media-state-summary-20260611-095826.json` 显示 `keyframe_images`、`clip_paths`、`audio_paths`、`thumbnail_image_paths` 长度均为 `0`，`final_video_path` 为空。
- **证据摘要** — `tmp/outputs/l4c-2r-s2-no-media-single-submit-summary-20260611-095826.json` 固化 `decision=passed`、`evidence_level=L4-authorized-live`、`submit_count_observed_by_spec=1`、`provider_error_count=0`、生产 health `status=ok`。
- **证据边界** — 当前只可声明“L4C-2R S2 no-media after-fix single-submit token smoke 通过”；不得外推为 S1/S2-S5/gate/media/poster/quality 通过，不得声明 delivery accepted、publish allowed、approved brand token 或实际 provider 扣费金额。

## 1.07 2026-06-11 L4C-3 S1 no-media single-submit 失败止损

- **工程修复** — 发现 S1 no-media 与修复前 S2 存在同类执行层缺口：`enable_media_synthesis=false` 只影响结果字段，不阻止 `StepRunner.resume()` 进入 `keyframe_images`。本轮已修复 `S1ProductDirectPipeline.run()`、`/scenario/s1`、`/scenario/s1/start` auto 和 unified `/scenario/s1/submit`，使 no-media 在 `keyframe_images` 之前停止。
- **测试守卫** — `tests/test_s1_continuity_pipeline.py` 新增/更新 no-media 防回归，断言不调用 full `resume()`，执行步骤只到 `strategy`、`scripts`、`compliance`、`storyboards`、`continuity_storyboard_grid`。
- **production spec** — 新增 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，仅允许一次 `/api/scenario/s1` submit，payload 固定 `enable_media_synthesis=false`，并检查 `keyframe_images`、`clip_paths`、`audio_paths`、`thumbnail_image_paths` 与 `final_video_path` 均为空。
- **计划门禁** — 用户授权后生成 `tmp/outputs/l4c-3-s1-no-media-token-smoke-plan-readiness-livekey-20260611-101904.json`，显示 `blocked=false`、`allowed_specs=["scenario-s1-no-media-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。
- **生产同步** — 用户随后授权 L4C-3 前置最小代码同步，只允许同步 `src/pipeline/s1_product_pipeline.py` 和 `src/routers/scenario.py`。远端原文件已备份到 `/opt/ai-video/backups/l4c3-s1-no-media-20260611-102747/`；backend 已重启；`tmp/outputs/l4c-3-production-code-sync-hash-check-after-sync-20260611-102747.txt` 显示两个授权文件本地与生产 hash 均一致，`/api/health` 返回 `status=ok`。
- **生产执行** — 同步成功后只运行 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts` 一次，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`。Playwright 日志 `tmp/outputs/l4c-3-s1-no-media-single-submit-playwright-20260611-102747.log` 显示唯一测试失败，断言期望 HTTP 200、实际收到 HTTP 500。
- **根因** — 生产后端日志 `tmp/outputs/l4c-3-s1-no-media-production-backend-evidence-20260611-102747.log` 显示失败发生在 provider 前：`ImportError: cannot import name 'MAX_CLIPS_PER_DEMO' from 'src.config' (/app/src/config.py)`。本地 `src/pipeline/s1_product_pipeline.py` 已依赖 `src.config` 中的 `MAX_CLIPS_PER_DEMO` / `MAX_THUMBNAILS_PER_DEMO`，但本轮授权同步范围不包含 `src/config.py`，导致生产容器缺少该常量。
- **provider 边界** — `tmp/outputs/l4c-3-s1-no-media-production-provider-counts-20260611-102747.json` 显示 `poyo_http_request_count=0`、`poyo_submit_execution_count=0`、`seedance_execution_count=0`、`tts_execution_count=0`、`assemble_execution_count=0`、`keyframe_execution_count=0`、`deepseek_http_request_count=0`。本次没有第二次 submit。
- **证据摘要** — `tmp/outputs/l4c-3-s1-no-media-single-submit-summary-20260611-102747.json` 固化 `decision=failed_stopped`、`evidence_level=L4-authorized-live`、`submit_count=1`、HTTP 500 根因和零 provider 执行态计数。
- **证据边界** — 当前只可声明“L4C-3 已执行一次授权 live submit，但在 provider 前因生产配置代码不同步失败止损”；不得声明 L4C-3 通过、S1 no-media 生产路径已验证、provider 已调用、产物已生成、delivery accepted、publish allowed 或 approved brand token。
- **L4C-3R-prep 已通过** — 用户授权只同步 `src/config.py`、备份远端原文件、重启 backend、执行 `/api/health`、hash verify 和容器 import smoke，不允许 Playwright live spec、submit 或 provider 调用。本轮远端原文件备份到 `/opt/ai-video/backups/l4c3r-prep-config-20260611-183914/`；`tmp/outputs/l4c-3r-prep-config-hash-verify-20260611-183914.txt` 显示本地、远端和容器内 `src/config.py` hash 均为 `e54498c02e1d0ad3ca5f7c26bebf17e7f3bf985fe75a8aaee85a215a5306669a`；`tmp/outputs/l4c-3r-prep-container-import-smoke-20260611-183914.txt` 显示 `import_ok=true`，`MAX_CLIPS_PER_DEMO=3`、`MAX_THUMBNAILS_PER_DEMO=2`。
- **L4C-3R-prep 边界** — `tmp/outputs/l4c-3r-prep-provider-log-counts-after-restart-20260611-183914.json` 显示重启后的 prep 窗口内 DeepSeek、poyo、SiliconFlow 外部 HTTP 计数均为 `0`，poyo/Seedance/TTS/assemble/keyframe 执行计数均为 `0`。更宽的 pre-prep 日志窗口中存在 admin health check 对 DeepSeek、poyo `/v1/models` 和 SiliconFlow 的历史探测，不能归因到本次 config sync/import smoke。
- **历史边界** — 本节记录 `L4C-3R-prep` 完成时的配置同步/import 证据；后续 `L4C-3R` live submit 结果以 `1.08` 为准。

## 1.08 2026-06-11 L4C-3R S1 no-media after-config-sync single-submit 业务路径通过

- **授权范围** — 用户重新授权只运行 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`，只允许一次 `/api/scenario/s1` submit，`enable_media_synthesis=false`，允许 DeepSeek 文本调用，不允许 poyo image、Seedance、TTS、assemble、keyframe 或 gate candidate generation。
- **计划门禁** — `tmp/outputs/l4c-3r-s1-no-media-token-smoke-plan-readiness-livekey-20260611-184923.json` 显示 `blocked=false`、`allowed_specs=["scenario-s1-no-media-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`；`tmp/outputs/l4c-3r-s1-no-media-playwright-list-20260611-184923.txt` 只枚举 1 个测试。
- **生产执行** — `tmp/outputs/l4c-3r-s1-no-media-single-submit-playwright-20260611-184923.log` 显示 `1 passed (8.3s)`，没有 Playwright retry；生产日志显示 label `s1_1781175031_a8117a86`，`/scenario/s1` 返回 200。
- **状态回读** — `tmp/outputs/l4c-3r-s1-no-media-state-summary-20260611-184923.json` 显示 `enable_media_synthesis=false`，`strategy`、`scripts`、`compliance`、`storyboards`、`continuity_storyboard_grid` 为 done，`keyframe_images` 及后续媒体步骤保持 pending；`keyframe_images`、`clip_paths`、`audio_paths`、`thumbnail_image_paths` 长度均为 `0`，`final_video_path` 为空，`errors_len=0`，`media_synthesis_errors_len=0`。
- **媒体产物检查** — `tmp/outputs/l4c-3r-s1-no-media-remote-artifact-search-20260611-184923.txt` 未发现该 label 下产物或近 15 分钟新增媒体文件。
- **provider 边界** — `tmp/outputs/l4c-3r-s1-no-media-production-provider-counts-refined-20260611-184923.json` 显示 DeepSeek 文本请求 `3` 次，poyo image/video submit、Seedance generation、TTS generation、assemble generation、keyframe generation、gate candidate generation 均为 `0`。
- **后台探测 caveat** — 同一日志窗口在 `/scenario/s1` 返回 200 后出现 admin health check 对 poyo `/v1/models` 和 SiliconFlow `/v1/models` 的 GET 探测，各 `1` 次。这不是 poyo image、Seedance、TTS、assemble、keyframe 或 gate candidate 生成，但意味着本轮不得声明“整个 backend 日志窗口绝对无 provider-looking 日志”。
- **证据摘要** — `tmp/outputs/l4c-3r-s1-no-media-single-submit-summary-20260611-184923.json` 固化 `decision=passed_with_background_probe_caveat`。
- **证据边界** — 当前只可声明“L4C-3R S1 no-media after-config-sync 单提交业务路径通过，媒体生成边界通过，带后台 provider health probe caveat”；不得声明 delivery accepted、publish allowed、approved brand token、final_work 创建、S1 media generation、S1 gate/step-by-step、user journey、S2-S5 或完整 token suite 通过。

## 1.09 2026-06-11 admin provider health probe 本地隔离已实现

- **根因** — `src/routers/admin/logs.py::run_health_checks()` 原先每 5 分钟在后台主动检查 DeepSeek、poyo `/v1/models` 和 SiliconFlow `/models`，会在 token smoke 的生产日志窗口中出现 provider-looking HTTP 日志，即使业务路径没有触发媒体 provider。
- **本地修复** — 新增 `ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED` 配置，默认关闭外部 provider health probe；关闭时 admin health 仍返回 `deepseek`、`poyo`、`siliconflow` 三个服务键，但状态为 `skipped`、`reason=external_provider_health_checks_disabled`。Postgres 与 Remotion health check 保持执行。
- **可选恢复** — 只有显式设置 `ADMIN_EXTERNAL_PROVIDER_HEALTH_CHECKS_ENABLED=1/true/yes/on` 时，admin health 才会恢复 DeepSeek/poyo/SiliconFlow 外部探测。
- **测试证据** — `tests/test_admin_health_provider_probe_guard.py` 覆盖默认跳过和显式开启两种路径；`.venv/bin/python -m pytest tests/test_admin_health_provider_probe_guard.py tests/test_admin_endpoints_smoke.py -q` 通过，结果 `8 passed`；`.venv/bin/ruff check src/config.py src/routers/admin/logs.py tests/test_admin_health_provider_probe_guard.py` 通过。
- **L4C-3H-prep 生产同步** — 用户授权后只同步 `src/config.py` 与 `src/routers/admin/logs.py`，远端原文件备份到 `/opt/ai-video/backups/l4c3h-admin-health-probe-20260611-222821/`，backend 已重启，`/api/health` 返回 `ok`，本地/远端/容器内两个文件 hash 均一致。
- **生产观察窗口** — `tmp/outputs/l4c-3h-prep-observation-counts-20260611-222821.json` 显示从 `2026-06-11T14:31:16Z` 起 370 秒 no-submit backend 日志窗口内，`scenario_submit_count=0`、DeepSeek/poyo/SiliconFlow 外部 HTTP 计数均为 `0`，poyo submit、Seedance generation、TTS generation、assemble generation、keyframe generation 与 gate candidate generation 均为 `0`；匹配行文件 `tmp/outputs/l4c-3h-prep-observation-matches-20260611-222821.txt` 为 0 行。
- **证据摘要** — `tmp/outputs/l4c-3h-prep-admin-provider-health-probe-sync-summary-20260611-222821.json` 固化 `decision=passed`。
- **证据边界** — 当前只可声明“admin provider health probe 隔离已在生产同步并通过 no-submit 日志窗口验证”；不得声明任何 Playwright live spec、S1/S2-S5/gate/media/poster/quality 新路径已通过。

## 1.10 2026-06-11 L4C-4 S1 no-media clean-log single-submit strict clean-log 未通过

- **授权范围** — 用户授权只运行 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`，只允许一次 `/api/scenario/s1` submit，`enable_media_synthesis=false`，允许 DeepSeek 文本调用，并观察 submit 开始后 6 分钟 backend 日志。
- **计划与执行** — `tmp/outputs/l4c-4-s1-no-media-clean-log-token-smoke-plan-readiness-livekey-20260611-230535.json` 显示 `blocked=false`、只允许 `scenario-s1-no-media-single-submit.prod.spec.ts`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。唯一一次 live run 的日志 `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-playwright-20260611-230535.log` 显示 `1 passed (13.4s)`，没有重跑。shell wrapper 因 zsh 无 `PIPESTATUS` 在测试完成后报错，结果已通过日志固化，未做第二次 submit。
- **业务与状态证据** — 生产 label 为 `s1_1781190534_6dcf8877`；`tmp/outputs/l4c-4-s1-no-media-clean-log-state-summary-20260611-230535.json` 显示 `enable_media_synthesis=false`、媒体路径长度均为 `0`、`final_video_path` 为空，`delivery_accepted=false`、`publish_allowed=false`、`approved_brand_token_write=false`。`tmp/outputs/l4c-4-s1-no-media-clean-log-remote-artifact-search-20260611-230535.txt` 未发现该 label 的媒体或近期 final_work 产物。
- **日志窗口证据** — `tmp/outputs/l4c-4-s1-no-media-clean-log-production-provider-counts-20260611-230535.json` 显示 6 分钟窗口内 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance execution、TTS execution、assemble execution、keyframe execution、gate candidate generation 均为 `0`。
- **阻塞项** — 同一日志窗口仍有 8 行媒体 skill `registered` 噪音，见 `tmp/outputs/l4c-4-s1-no-media-clean-log-registration-noise-matches-20260611-230535.txt`；这些行包含 `elevenlabs-tts-skill`、`keyframe-images`、`remotion-assemble-skill`、`seedance-video-generate-skill` 等词元。它们不是执行级 provider 调用，但按本轮 “clean-log” 授权口径仍污染日志。
- **证据摘要** — `tmp/outputs/l4c-4-s1-no-media-clean-log-single-submit-summary-20260611-230535.json` 固化 `decision=failed_strict_clean_log_registration_noise`。
- **证据边界** — 当前只可声明“L4C-4 S1 no-media 单提交业务路径通过，执行级 provider/media 生成边界通过，但 strict clean-log 未通过”；不得声明 L4C-4 clean-log passed、delivery accepted、publish allowed、approved brand token、final_work 创建、S1 media generation、gate/step-by-step、S2-S5 或完整 token suite 通过。
- **当时下一步** — 先做最小 import/logging hygiene 修复，使 no-media S1 不在 submit 窗口内注册或打印媒体 skill 日志；修复需另行授权生产同步。该动作后续已在 `1.11` 完成，同一单 spec clean-log 复验已在 `1.12` 完成。

## 1.11 2026-06-12 L4C-4R-prep S1 no-media logging/import hygiene 已通过

- **授权范围** — 用户授权只修改并同步与 S1 no-media 媒体 skill 注册日志污染直接相关的最小文件；不允许运行 Playwright live spec、`/scenario/*` submit、provider 生成调用、发布、approved brand token 写入或 delivery acceptance。
- **工程修复** — `src/pipeline/__init__.py` 不再在包 import 时注册 scenario/media skills；`src/pipeline/s1_product_pipeline.py` 改为只在实际执行媒体步骤时 lazy import/register 对应 media skills，no-media S1 import 只保留 strategy/script/compliance/storyboard/continuity 等前置 skills。
- **本地验证** — S1 import smoke 显示 forbidden media skills 注册集合为空；聚焦测试 `5 passed`，`ruff check src/pipeline/__init__.py src/pipeline/s1_product_pipeline.py tests/test_s1_continuity_pipeline.py` 通过。
- **生产同步** — 只同步 `src/pipeline/__init__.py` 与 `src/pipeline/s1_product_pipeline.py`。远端原文件备份到 `/opt/ai-video/backups/l4c4r-prep-s1-logging-20260612-000910/`；backend 已重启；`/api/health` 在同步前、重启后、观察后均返回 `status=ok`。
- **hash verify** — `tmp/outputs/l4c-4r-prep-hash-verify-20260612-000910.txt` 显示本地、远端宿主机、backend 容器三方 hash 一致：`src/pipeline/__init__.py=263d0ca1e868c6f4938de3ad7f5f1a83b71f2bf44659f4db342d4fbe8a7dd92a`，`src/pipeline/s1_product_pipeline.py=623f6ffba96b4a31c31e4116f4cb6b1ab1a6b3378f21a1c1e1d1eed9cda99315`。
- **日志窗口证据** — `tmp/outputs/l4c-4r-prep-observation-counts-20260612-000910.json` 显示 370 秒 no-submit backend 窗口内 `/scenario` submit、DeepSeek/poyo/SiliconFlow 外部 HTTP、poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration 与媒体 skill `registered` 计数均为 `0`。
- **证据摘要** — `tmp/outputs/l4c-4r-prep-s1-logging-import-hygiene-sync-summary-20260612-000910.json` 固化 `decision=passed`。
- **证据边界** — 本节完成时只可声明“L4C-4R-prep 生产同步和 no-submit clean-log 验证通过”；不得声明 `L4C-4R` live submit 已通过。该 live submit 复验后续已在 `1.12` 完成。

## 1.12 2026-06-12 L4C-4R S1 no-media clean-log single-submit 已通过

- **授权范围** — 用户授权只运行 `web/e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`，只允许一次 `/api/scenario/s1` submit，`enable_media_synthesis=false`，允许 DeepSeek 文本调用，不允许 poyo/Seedance/TTS/assemble/keyframe/gate candidate/media skill registered 日志。
- **计划门禁** — `tmp/outputs/l4c-4r-s1-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-001.json` 显示 `blocked=false`、`allowed_specs=["scenario-s1-no-media-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。
- **生产执行** — `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-playwright-20260612-001.log` 显示 `1 passed (11.7s)`，没有 retry；生产 label 为 `s1_1781229202_7b5148d1`。
- **日志窗口证据** — `tmp/outputs/l4c-4r-s1-no-media-clean-log-observation-counts-20260612-001.json` 显示 370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration、media skill `registered` 和 stop-loss status 均为 `0`。`scenario_s1_submit=2` 是同一次 HTTP 200 的应用日志与 uvicorn access 日志两行，spec 观察 submit 次数为 `1`。
- **产物边界** — spec 已断言媒体输出字段为空；本轮没有额外执行 scenario state read、发布、approved brand token 写入或 delivery acceptance。
- **证据摘要** — `tmp/outputs/l4c-4r-s1-no-media-clean-log-single-submit-summary-20260612-001.json` 固化 `decision=passed`。
- **证据边界** — 当前只可声明“L4C-4R S1 no-media clean-log single-submit token smoke 通过”；不得外推为 S1 media generation、gate/step-by-step、S2-S5、完整 token suite、publish、delivery acceptance 或 approved brand token write。

## 1.13 2026-06-12 L4C-5 S2 no-media clean-log single-submit 已通过

- **授权范围** — 用户授权只运行 `web/e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts`，`RUN_TOKEN_SMOKE=1`、`PLAYWRIGHT_PROD_WORKERS=1`、`PLAYWRIGHT_MAX_SUBMIT_COUNT=1`、`PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`、`PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`、`--retries=0`、`--workers=1`，只允许一次 `/api/scenario/s2` submit，`enable_media_synthesis=false`，允许 DeepSeek 文本调用，不允许 poyo/Seedance/TTS/assemble/keyframe/gate candidate/media skill registered 日志。
- **计划门禁** — `tmp/outputs/l4c-5-s2-no-media-clean-log-token-smoke-plan-readiness-livekey-20260612-002.json` 显示 `blocked=false`、`allowed_specs=["scenario-s2-no-media-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`；Playwright `--list` 只枚举 1 个测试。
- **生产执行** — `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-playwright-20260612-002.log` 显示 `1 passed (7.2s)`，没有 retry；生产 label 为 `s2_momcozy_1781230204`。
- **日志窗口证据** — `tmp/outputs/l4c-5-s2-no-media-clean-log-observation-counts-20260612-002.json` 显示 370 秒窗口内 DeepSeek text calls `2`，`api.poyo.ai=0`、`api.siliconflow.cn=0`，poyo submit、Seedance/TTS/assemble/keyframe/gate candidate、thumbnail media registration、media skill `registered` 和 stop-loss status 均为 `0`。`scenario_s2_submit=2` 是同一次 HTTP 200 的应用日志与 uvicorn access 日志两行，spec 观察 submit 次数为 `1`。
- **产物边界** — spec 已断言媒体输出字段为空；本轮没有额外执行 scenario state read、发布、approved brand token 写入或 delivery acceptance。
- **证据摘要** — `tmp/outputs/l4c-5-s2-no-media-clean-log-single-submit-summary-20260612-002.json` 固化 `decision=passed`。
- **证据边界** — 当前只可声明“L4C-5 S2 no-media clean-log single-submit token smoke 通过”；不得外推为 S2 media generation、S3-S5、S1 gate/step-by-step、完整 token suite、publish、delivery acceptance 或 approved brand token write。

## 1.03 2026-06-11 L4C-1R single-submit 守卫首次执行但未完成视频产物

- **工程守卫** — 新增 `fast-mode-single-submit.prod.spec.ts`，计划验证器新增 `max_submit_count`、`provider_max_retries` 和 `artifact_policy.storage_scope`；Fast Mode 请求支持 `artifact_disposition=pending_review` 与 `provider_max_retries=0`，Seedance 客户端支持把 video provider attempt 限制为 1。
- **计划门禁** — `tmp/outputs/l4c-1r-token-smoke-plan-readiness-20260611-170131.json` 显示 `blocked=false`、`allowed_specs=["fast-mode-single-submit.prod.spec.ts"]`、`max_submit_count=1`、`provider_max_retries=0`。
- **生产执行** — 只运行 1 个测试，实际 `submit_count_observed=1`；任务 `fast_1781168782_cc749671` 在 `llm` 阶段失败，错误为 `[Errno 13] Permission denied: '/app/output/tenants/default'`。
- **provider 边界** — 本次到达 DeepSeek LLM enhancement，但未出现 `poyo: submitting task`、未生成 poyo/Seedance video task、未发生 poyo retry。证据为 `tmp/outputs/l4c-1r-fast-mode-single-submit-playwright-20260611-170131.log` 与 `tmp/outputs/l4c-1r-provider-log-evidence-20260611-170131.log`。
- **生产修复** — 已把生产 `/app/output/tenants` owner 修为 `appuser:appgroup`，并完成空目录写入/删除预检；`/api/health` 返回 200。该修复未触发 provider，也没有第二次 submit。
- **证据边界** — 该次首次执行只能声明“single-submit 守卫生效，并定位/修复 pending_review volume 权限阻塞”；不能声明该次执行已完成 L4C-1R 视频生成、pending_review 产物创建、delivery accepted、publish allowed 或 approved brand token。后续通过状态以 `1.04` 为准。

## 1.00 2026-06-11 L4A authorized-live provider smoke 已执行

- **授权输入** — 用户明确授权在生产环境 `https://video.lute-tlz-dddd.top` 使用 poyo image + poyo Seedance 执行 Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频真实调用 smoke，预算上限 `$3.00`，自动重试 `0`，不发布、不写入正式 brand token，产物只进入待审素材库；检查人为 `pray`。
- **执行证据** — `scripts/p2_recharge_smoke_checklist.py --execute` 已在 `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`、`RUN_TOKEN_SMOKE=1` 和私有 records/payloads 满足后执行；日志为 `tmp/outputs/l4a-authorized-live-provider-smoke-20260611-152953.log`，汇总为 `tmp/outputs/authorized-live-poyo-smoke-20260611-summary-enriched.json`。
- **provider 结果** — 4 个 provider job 均返回：`0K4K8A3DLKREWJQO`、`YH2UB4QFC4H380KL`、`CSWOZOYCVOPARHCD`、`9GUN6SYY41RGODIG`；汇总状态为 `status=submitted`、`provider_call_executed=true`、`blocked_reasons=[]`。
- **待审产物** — 本地待审包位于 `output/pending_review/momcozy_sterilizer_smoke_20260611/`，包含 `main_45.png`、`uv_benefit.png`、`kitchen_scene.png`、`i2v_15s.mp4`；review packet 为 `tmp/outputs/pending-review-asset-packet-20260611.json`。`uv_benefit` 被标记为 `regenerate_or_edit_before_brand_use`，其余资产仍需人工 review。
- **生产回读缺口（已在 1.01 闭环）** — L4A 执行后，生产 `/api/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc` 一度使用当前 tenant key 返回 `total=0`、`pending_review_count=0`。根因是本次产物只在本地 `output/pending_review`，尚未同步到生产可扫描目录；同时 portfolio 原实现只扫描顶层 `pending_review`，tenant key 无法读取 default 待审资产。
- **工程修复（已部署）** — `src/routers/portfolio.py` 已支持扫描 `output/tenants/<tenant>/pending_review/...`；`tests/test_p0_media_tenant_security.py` 增加 tenant-scoped pending_review 可见性与 default pending_review 隔离测试；L4B 生产只读回读结果见 `1.01`。
- **验证结果** — `.venv/bin/python -m pytest tests/test_p0_media_tenant_security.py tests/test_portfolio_s4_filtering_contract.py tests/test_pending_review_asset_packet.py -q` 通过，结果 `15 passed`；`.venv/bin/ruff check src/routers/portfolio.py tests/test_p0_media_tenant_security.py` 通过；`git diff --check -- src/routers/portfolio.py tests/test_p0_media_tenant_security.py` 通过。
- **证据边界** — 本节只声明“L4A 受控 provider smoke 成功提交并生成待审资产”；L4B 生产只读回读见 `1.01`。不得声明商业交付完成、delivery accepted、publish allowed、approved brand token 或可直接发布。

## 0.99 2026-06-11 L4A 授权前 readiness 摸排

- **状态说明** — 本节记录 2026-06-11 授权执行前的 no-token readiness；当前 L4A 结果以 `1.00` 为准。
- **no-token 证据包** — 已生成 `tmp/outputs/l4a-authorized-live-smoke-packet-20260611-152010.json`，证据等级 `L2-fixture-or-dry-run`，`no_provider_call=true`，`provider_call_allowed=false`。
- **test-plan readiness** — 已生成 `tmp/outputs/l4a-test-plan-readiness-20260611-152010.json`，`ready_for_test_plan_discussion=true`，`ready_for_live_execution=false`。
- **已满足项** — 当前环境中 `API_KEY` / `PLAYWRIGHT_API_KEY` 为非 demo，`POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 均存在；job ledger 与 audit bundle fixture readiness 为 pass。
- **阻塞项** — 当前会话没有精确 C21 授权语句，缺 `AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD`、`AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS`、`AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1`、`AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`，且 `RUN_TOKEN_SMOKE` 未启用。
- **授权前证据边界** — 在该 no-token readiness 时间点，只能声明“L4A 测试计划可讨论”；不能声明 L4A 已授权、provider 账户余额有效、runtime 成功、产物质量通过或商业交付完成。当前真实执行结果以 `1.00` 为准。

## 0.98 2026-06-11 E2E Phase A/B no-token 执行闭环

- **Phase A 本地质量门** — `.venv/bin/python -m pytest tests -q` 通过，结果 `1888 passed, 11 skipped, 12 deselected`；`make lint`、前端 `npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 和 `git diff --check` 均通过。
- **Phase B fail-closed readiness** — `p2_recharge_smoke_checklist.py` 保持 dry-run；launch packet 为 `L2-fixture-or-dry-run`、`no_provider_call=true`、`provider_call_allowed=false`；readiness report 为 `ready_for_test_plan_discussion=true`、`ready_for_live_execution=false`；相关 pytest 守卫 `36 passed`。
- **Phase C 正式非 token E2E** — 已为 active tenant `momcozy-marketing` 生成专用非 demo Playwright key，并用 `RUN_TOKEN_SMOKE=0 .venv/bin/python scripts/production_non_token_e2e_check.py --execute` 跑通生产前后端联动，结果 `50 passed, 4 skipped`。helper 仍在缺 key/demo key 或 truthy `RUN_TOKEN_SMOKE` 时 fail-closed。
- **L4B 证据门禁修正** — `web/e2e/production/library-portfolio.prod.spec.ts` 的 UI 回读用例现在与 API 回读用例一致：先只读查询 `creation_intermediate` 中是否存在 `pending_review` 资产；不存在时明确 skip，不把“未执行 L4A / 当前无待审资产”误报为前端失败。
- **证据边界** — 该阶段当时可声明 `L2-fixture-or-dry-run` 与 `L3-production-read-only` 的 Phase C 通过；不能声明 `L4A` provider smoke、`L4B` 待审素材回读通过、provider runtime 成功、delivery acceptance、publish allowed 或 approved brand token。当前 `L4A` 真实执行结果以 `1.00` 为准，`L4B` 只读回读结果以 `1.01` 为准。

## 0.97 2026-06-11 真实 provider 前后端 E2E 计划正式化

- **执行口径** — `docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md` 已把首轮真实 provider 联测拆成 `L4A` 受控 provider smoke、`L4B` 前端只读回读和 `L4C` 扩展 token Playwright；首轮不直接运行完整 `RUN_TOKEN_SMOKE=1 npm run e2e:prod`。
- **runbook 对齐** — `docs/runbooks/production-e2e-token-smoke.md` 已同步新路径：`L4A` 通过 `scripts/p2_recharge_smoke_checklist.py --execute` 执行 Momcozy 3 图 + 1 视频样本，`L4B` 用 `library-portfolio.prod.spec.ts` 且 `RUN_TOKEN_SMOKE=0` 验证 `/library` 只读可见。
- **证据边界** — 2026-06-07 历史样本仍只证明 scoped `L4-authorized-live`；下一次真实执行必须重新授权、重新生成私有 approval/account readiness records、重新固化 evidence record。
- **边界** — 本轮只制定正式计划和 runbook，不设置 `RUN_TOKEN_SMOKE=1`，不调用 poyo/DeepSeek/SiliconFlow，不执行生产 Playwright。

## 0.96 2026-06-11 Phase 3 media step output selector 收口

- **媒体 selector 抽取** — 新增 `web/src/lib/pipelineStepOutput.ts`，集中解析 `seedance_clips`、`tts_audio`、`thumbnail_images`、`assemble_final` 的兼容输出形状。
- **共享数据接口** — `extractSeedanceClipOutput()` 同时支持 `{ clip_paths, clip_details, total_duration, target_duration }` 与 legacy `string[]`；`extractTtsAudioPaths()`、`extractThumbnailImagePaths()`、`extractFinalVideoPath()` 覆盖现有兼容字段。
- **组件重复减少** — `StepByStepView` 与 `VideoWorkflow` 保留原 UI 展示差异，但媒体路径、clip detail、final video path 的读取不再各自维护格式判断。
- **测试覆盖** — 新增 `pipelineStepOutput.test.ts`，覆盖新旧 Seedance 格式、clip detail 清洗、音频/缩略图路径 fallback、最终视频路径字段优先级与 render JSON 路径。
- **验证闭环** — 局部 `tsc`、目标 ESLint、`pipelineStepOutput`/`pipelineOutputPreview`/`StepByStepView` 测试通过；完整 `cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过，Vitest 当前结果为 `52 passed` test files、`234 passed` tests。
- **边界** — 本轮只完成前端媒体 step output 数据 selector 收口，未改变 UI 合并策略，未执行真实 provider，未证明真实媒体生成链路成功。

## 0.95 2026-06-11 Phase 3 step output preview 边界收口

- **预览 helper 抽取** — 新增 `web/src/lib/pipelineOutputPreview.ts`，用 `summarizeStepOutputPreview()` 把 step output 的数组计数、quality status、summary、字段计数和 primitive text 预览抽成纯函数。
- **组件断言减少** — `StepByStepView` 删除本地 `getOutputPreview()` 中的 `output as { overall_status?: string; summary?: string }` 断言，改为消费结构化 `StepOutputPreview`。
- **重复计算减少** — step 行渲染时只计算一次 `outputPreview`，不再在条件判断和文本渲染处重复调用预览逻辑。
- **测试覆盖** — 新增 `pipelineOutputPreview.test.ts`，覆盖数组、audit status、summary 截断、字段计数、primitive text、空值和空对象。
- **验证闭环** — 局部 `tsc`、目标 ESLint、`pipelineOutputPreview` + `StepByStepView` 测试通过；完整 `cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过，Vitest 当前结果为 `51 passed` test files、`231 passed` tests。
- **边界** — 本轮只处理 step output 行内预览的前端纯函数边界，未抽离完整 `StepOutput` JSX，未改变后端输出结构，未触发 provider 真调用。

## 0.94 2026-06-11 Phase 3 workflow/step-by-step 状态边界收口

- **状态 normalizer** — 新增 `web/src/lib/pipelineState.ts`，提供 `normalizeStepByStepState()`、`normalizeWorkflowState()` 与 payload 版本 normalizer，把 `{ state }` 包裹响应、脏 `steps`、`errors`、`soft_degraded_reasons` 收口后再进入 UI store。
- **StepByStepView 接口收口** — `StepByStepView` 的 `state`、`onStepComplete`、`onResume` 从裸 `Record<string, unknown>` 改为 store 的 `StepByStepState`；run/regenerate/resume/save 后的 API 返回统一归一化。
- **VideoWorkflow 接口收口** — `VideoWorkflow` 不再在 refresh/run/regenerate/resume 路径中 `as WorkflowState`，统一使用 `normalizeWorkflowStatePayload()`；step order、duration、soft degraded reasons 通过 helper 提取。
- **首页接线收口** — 首页取消 `stepByStepState as Record<string, unknown>`；恢复 partial state、expert session state、step-by-step 初始化 state 均先归一化；workflow/step-by-step 完成后进入 `oneshotResult` 仍走 `normalizePipelineResult()`。
- **测试覆盖** — 新增 `pipelineState.test.ts`，覆盖嵌套 payload 提取、非对象 payload fail-safe、step map fallback、step_order/duration/degraded reasons 清洗。
- **验证闭环** — 局部 `tsc`、目标 ESLint、`pipelineState`/`pipelineResult`/`StepByStepView` 测试通过；完整 `cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过，Vitest 当前结果为 `50 passed` test files、`228 passed` tests。
- **边界** — 本轮只处理前端 workflow/step-by-step 状态输入边界，未改变后端 StepRunner schema，未执行真实生成，证据等级仍为 `L2-fixture-or-dry-run`。

## 0.93 2026-06-11 Phase 3 pipeline result 类型边界收口

- **完成结果契约** — 新增 `web/src/lib/pipelineResult.ts`，用 `normalizePipelineResult()` 把轮询完成 payload 从 `unknown` 收口为 store 已有的 `PipelineResult`；非对象 payload 进入空结果对象，函数、symbol、`undefined` 等非 JSON 值归一化为 `null`。
- **步骤状态契约** — `StageProgress` 使用 `normalizePipelineSteps()` 接收 `data.steps`，不再把后端返回值整体强转为 `Record<string, Record<string, unknown>>`；非对象 step 会保留为 `{ output }`，避免破坏完成态计算。
- **页面断言移除** — `StageProgress.onComplete` 从 `(result: unknown) => void` 改为 `(result: PipelineResult) => void`；首页 smart-create 完成回调不再 `asRecord(result)` 或 `result as GalleryResult`。
- **Gallery 字段读取收口** — `saveToGallery()` 改为接收 `PipelineResult`，通过 `extractGalleryResultFields()` 只读取支持的 briefs/scripts/thumbnail/video/audit score 形状，避免脏 payload 直接污染 localStorage。
- **测试覆盖** — 新增 `pipelineResult.test.ts`，覆盖 completion payload 归一化、非对象拒绝、steps map 收口、gallery 字段提取。
- **验证闭环** — 局部 `npx tsc --noEmit -p tsconfig.json`、目标 ESLint、`pipelineResult` + `StageProgress` 测试通过；完整 `cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过，Vitest 当前结果为 `49 passed` test files、`225 passed` tests。
- **边界** — 本轮只处理前端完成结果与 step 状态的输入边界，未改后端响应 schema，未触发 provider 真调用，证据等级仍为 `L2-fixture-or-dry-run`。

## 0.92 2026-06-11 Phase 3 gate candidate 类型边界收口

- **Candidate data contract** — `CandidateSelector` 新增 `CandidateData` JSON-like 类型、`CandidateVariant`、`normalizeCandidateData()` 与 `normalizeCandidates()`，把 gate candidate 的 UI 输入从 `unknown` 收口为可预览、可诊断、可序列化的数据形状。
- **GatePanel 接线** — 后端 `fetchGateState()` 返回的候选列表不再直接 `as Candidate[]`，统一通过 `normalizeCandidates()` 进入 UI；demo candidates 也通过 `normalizeCandidateData()` 归一化，避免测试数据绕过正式接口。
- **轮询状态读取收口** — `GatePanel` 稳定性 hash 改为 `summarizeRuntimeStatuses()`，只读取运行态对象的 `status` 字段，不再把 gate/step 对象整体强转为 `Record<string, unknown>`。
- **测试覆盖** — `CandidateSelector.test.tsx` 增加脏 backend payload 归一化用例，覆盖 fallback id、variant fallback、score clamp、`undefined -> null` 和 recommended 布尔收窄。
- **验证闭环** — `cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过；Vitest 当前结果为 `48 passed` test files、`221 passed` tests。
- **边界** — 本轮只收口 Gate candidate 前端类型接口，未删除 legacy endpoint，未改后端候选生成 schema，未触发 provider 真调用。

## 0.91 2026-06-11 完整路径修复与质量门恢复

- **前端构建门恢复** — 修复 `SceneForm.tsx` legacy form JSX 收口；`continuityDirections.ts` 导出并收口 `extractContinuityDirections` / `truncatePreview`，同时兼容 snake_case 与 camelCase 连续性字段；`usePipelineStore` 对齐后端可返回 `current_step: null` 的运行态。
- **命令入口对齐** — `web/package.json` 的 `lint` 与 CI 前端门禁一致；`Makefile` 通过 `PYTHON ?= .venv/bin/python` 执行 pytest/ruff，并把 lint surface 固定为 `src tests scripts`；主 CI 与 deploy preflight 同步扩展到 `ruff check src tests scripts`。
- **部署脆弱点收口** — `deploy/lighthouse/deploy.sh` 新增 `REBUILD_RENDERING`、显式 `build rendering`、`force-recreate rendering` 与容器内 `/health` 检查；`build-and-deploy.sh` 透传 `REBUILD_RENDERING`；GitHub deploy 默认 `REBUILD_BACKEND=1 REBUILD_RENDERING=1 RUN_TOKEN_SMOKE=0`。
- **测试脆弱点收口** — TikTok / Shopify no-token mock publish 移除隐藏随机失败；`bg_registry` 取消语义测试改为重新抛出 `CancelledError`；`page-smoke` 模块导入测试增加显式 60s timeout，避免重导入 smoke 在全量并发时假红。
- **文档/治理同步** — root governance contract 登记 `CHANGELOG.md`、`LICENSE`、`SECURITY.md`；2026-06-09 两份 debt-audit 文档补齐 frontmatter；README 本地验证命令与实际可运行入口对齐。
- **验证闭环** — `.venv/bin/python -m pytest tests -q` 通过，结果 `1888 passed, 11 skipped, 12 deselected`；`make lint` 通过；`cd web && npm run lint`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run`、`npm run build` 均通过；`git diff --check` 通过。
- **边界** — 本轮只达到 `L2-fixture-or-dry-run` / 本地构建运行证据等级；没有设置 `RUN_TOKEN_SMOKE=1`，没有调用 poyo/DeepSeek/SiliconFlow/TikTok/Shopify 真实 provider，不升级为生产商业交付证明。

## 0.89 2026-06-07 P2-2 内容审核样本回灌与差异隔离

- **错误码补齐** — `src/models/enums.py` 增加 `ErrorCode.CONTENT_MODERATION_REJECTED`，并在 `src/tools/error_classifier.py` 将内容审核类消息（`content_moderation`/`content_violation`/`safety_block`）映射为该错误码。
- **提示词清洗闭环** — `src/tools/poyo_safety.py` 对应替换词清单与 `docs/poyo-trigger-words.md` 显式一致，`ErrorCode.CONTENT_MODERATION_REJECTED` 在 `_is_recoverable()` 中定义为 `False`，避免自动重试。
- **fixtures 与回灌** — 新增 `tests/fixtures/commercial_video/poyo_content_rejection_samples.json`，包含：
  - `sanitization_cases`：触发词/替换词对照；
  - `runtime_rejection_messages`：`poyo` 运行时拒绝消息模板。
- **回归测试** — `tests/test_poyo_safety.py::test_fixture_terms_are_replaced` 与 `tests/test_negative_integration.py::test_poyo_runtime_error_classifies_to_content_moderation_rejection` 用 fixtures 做参数化回灌，新增 fixture 读取与 runtime 分类路径覆盖。
  - 结果：`pytest tests/test_poyo_safety.py tests/test_negative_integration.py`，`34 passed`。
- **运行护栏对齐** — `docs/runbooks/poyo-rejection.md` 与 `docs/poyo-trigger-words.md` 联动：新增触发词/替换词需同时更新 fixtures 与文档。
- **边界** — P2-2 当前仍属 `L2-fixture-or-dry-run` 内容治理补强：未发起新的 provider 调用，不改变 `/api/fast/*`、`/scenario/*`、发布链路、`brand token` 发放状态。

## 0.90 2026-06-07 生产部署后回归复盘清单

- **新增回归 SOP** — 新增 `docs/runbooks/production-post-deploy-regression-checklist.md`，统一 `RUN_TOKEN_SMOKE=0` 下的 deploy 后页面/API/容器/日志复核顺序。
- **复核内容** — 包含 `deploy/lighthouse/smoke.sh` 结果复盘、关键页面状态码清单、关键 API 只读校验、远端容器 `RestartCount` 与异常日志抽样、以及回归证据 JSON 模板。
- **边界控制** — 文件明确要求 demo key 模式下跳过鉴权 API 细项，并要求以 `tmp/outputs/production-post-deploy-regression-YYYYMMDD.json` 固化结果后才能作为 P2-3 交付证据。
- **执行状态** — 已在 2026-06-07 产线执行过一次完整检查，已形成 `tmp/outputs/production-post-deploy-regression-20260607.json` 证据，当前判定为 `demo` 鉴权模式下 PASS（`toolbox` 步骤跳过，未触发 provider）。
- **状态** — P2-3 已从执行清单收口为可复跑清单；正式 PASS 判据仍等待下一轮回归循环后签字确认。

## 0.88 2026-06-07 AI Video 2.0 P1-65 50-loop checkpoint review

- **结论** — 对 `P1-16`~`P1-64` 执行结果做完税式复核后，确认本轮 50-loop 已具备闭环证据：全部项完成、未发现新增阻塞项，且未引入 provider 真调用前提外扩散。
- **排序结果** — 技术债优先级重排为两层：
  - **P1 可收尾项（保持现状）**：`api key hermetic`、`timeout/deploy`、`docs/test/CI`、`前端 error path` 与 `provider runtime 无泄露` 相关项继续保持阻断性防护，不允许放松；
  - **P2 前置项（下阶段）**：S1-S5 实际 provider smoke、`C2PA` 商业签发闭环、品牌资产入库交付链路、发布/分发上线链条、长视频生产后续对象落地。
  这部分不属于 P1 50-loop 技术债处理范围。
- **门禁决策** — `P1-65` 已完成并合入执行结论：`P1-16~P1-64` 收口，`P1` 主线不再新增功能任务，下一阶段从 `P2-1` 按充值后授权执行路径推进。
- **边界对齐** — 尽管本次复核完成，但授权真实执行仍受 `C21/C24~C35` 约束：需用户逐字授权、`approval record`、`provider account readiness`、`AI_VIDEO_AUTHORIZED_LIVE_*` 门禁与 `RUN_TOKEN_SMOKE=1` 同时满足后，才允许进入 `L4-authorized-live`。

## 0.86 2026-06-06 AI Video 2.0 C35 private poyo runtime wiring contract

- **新增私有 runtime 接线** — `src/pipeline/authorized_live_poyo_runtime.py` 新增 `build_authorized_live_poyo_runtime_submitter()`，只有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 时才从 injected env mapping 读取 `POYO_API_KEY`、`POYO_API_BASE_URL` 和 `AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS`，并组装 C34 HTTP submitter。
- **私有 payload loader** — `load_authorized_live_poyo_payloads()` 只允许 payload JSON 位于 `tmp/` 或 repo 外部，拒绝正式目录，避免 prompt payload 被写入正式资产；loader 只返回 `AuthorizedLivePoyoPayload` 映射，不生成 provider job。
- **显式 CLI opt-in** — `scripts/authorized_live_token_smoke_harness.py` 新增 `--enable-poyo-http-submitter`，默认不启用；`run_authorized_live_harness()` 新增 lazy `submitter_factory`，preflight blocked 或 execute gate 未通过时不会构造 submitter。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_harness.py tests/test_authorized_live_poyo_runtime.py` 通过，结果 `17 passed`；授权 smoke 串联回归 `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_poyo_runtime.py tests/test_authorized_live_harness.py tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `65 passed`；docs governance `12 passed`；相关 `ruff check`、`git diff --check` 和 scoped secret scan 通过。
- **边界** — C35 只证明真实调用所需私有 payload/runtime 接线可以 fail-closed 审计；没有精确授权句、私有 approval/account readiness records、生产部署、真实 provider response 和 artifact side effect，不能升级为 `L4-authorized-live`。

## 0.87 2026-06-07 AI Video 2.0 P1-64 C2PA runbook dry-run checklist

- **新增 runbook** — `docs/runbooks/c2pa-dry-run-checklist.md` 补齐 C2PA 签名链路 dry-run 自检：`sign_video` `no-op` 兼容、`build_manifest` 字段完整性、缺证书退化可执行、安全边界（不访问 CA）、与 `c2pa-cert-application` 的衔接。
- **验证结果** — `.venv/bin/python -m pytest tests/test_sprint3_compliance_resilience.py -k c2pa` 通过，结果 `2 passed`；当前仅覆盖 C2PA dry-run 失败退化面，未触发真实证书申请或签名发布流程。
- **边界** — P1-64 仍是前置执行清单与回归可视化，不是 EU/商用签发完成证明；未到 `C2PA_ENABLED=1` + production certificate 完整签名验收前，不产生对外发布结论。

## 0.85 2026-06-06 AI Video 2.0 C34 no-token HTTP submitter assembly gate

- **新增 HTTP submitter assembly gate** — `src/pipeline/authorized_live_poyo_submitter.py` 新增 `build_authorized_live_poyo_submitter_from_http()`，把已有 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1` 门禁、injected authorization token、injected HTTP client 和 private payloads 组装为 `AuthorizedLivePoyoSubmitter`。
- **默认阻断** — 未设置 transport gate 时，即使传入 token、HTTP client 和 payloads，helper 也只返回 `None`，不构造 transport、不发 submit/status 请求。
- **接线约束** — gate 启用后缺 token、缺 HTTP client 或缺 private payloads 都会 fail-closed；token 仍只能由调用方私有注入，模块不读取 env secret、不导入真实 HTTP client。
- **CLI 默认无接线** — `tests/test_authorized_live_poyo_submitter.py` 继续静态检查 `scripts/authorized_live_token_smoke_harness.py` 不导入 submitter factory、HTTP assembly helper、`PoyoClient`、`httpx` 或 `POYO_API_KEY`。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py` 通过，结果 `17 passed`；授权 smoke 串联回归 `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_harness.py tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `55 passed`；docs governance `12 passed`；相关 `ruff check`、`git diff --check` 和 scoped secret scan 通过。
- **边界** — C34 只证明 HTTP adapter 可由私有运行时输入显式组装；未接线 CLI、未读取真实 key、未提交 provider job、未验证 poyo 余额或 runtime 成功，不能升级为 `L4-authorized-live`。

## 0.84 2026-06-06 AI Video 2.0 C33 poyo submit/status HTTP adapter contract

- **新增 HTTP adapter contract** — `src/pipeline/authorized_live_poyo_submitter.py` 新增 `AuthorizedLivePoyoSubmitPollTransport`，只通过 injected `PoyoSubmitPollHttpClient` 构造 poyo `/api/generate/submit` 和 `/api/generate/status/{task_id}` 请求，不导入真实 HTTP client、不读取环境变量。
- **请求形状守卫** — fake HTTP 测试确认 submit body 固定为 `{"model": model, "input": input_payload}`，headers 只由 injected authorization token 构造；adapter 返回值只包含 `provider_job_id`、`file_url`、`thumbnail_url`，不回显 token 或 prompt。
- **失败即停** — 空 authorization token、非 `finished` status、finished task 缺失 `file_url` 都会阻断；adapter 不做失败重试、不返回 stub。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py` 通过，结果 `14 passed`；授权 smoke 串联回归 `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_harness.py tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `52 passed`；docs governance `12 passed`；相关 `ruff check` 和 `git diff --check` 通过。
- **边界** — C33 只证明真实 transport 的 submit/status 请求适配层可用 fake HTTP 审计；未接线 CLI、未提交 provider job、未轮询真实任务、未验证 poyo key / 余额 / runtime 成功，不能升级为 `L4-authorized-live`。

## 0.83 2026-06-06 AI Video 2.0 C32 no-token submitter factory gate

- **新增工厂门禁** — `src/pipeline/authorized_live_poyo_submitter.py` 新增 `AUTHORIZED_LIVE_POYO_TRANSPORT_ENV=AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT` 与 `build_authorized_live_poyo_submitter()`。默认未设置门禁时返回 `None`，不构建 submitter、不调用 transport。
- **接线约束** — 即使 `AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1`，factory 也必须同时收到 injected transport 和 private payloads；缺任一项直接 `ValueError` 阻断，避免 CLI 或环境变量隐式拼出真实 provider 调用。
- **CLI 默认无接线** — `tests/test_authorized_live_poyo_submitter.py` 继续静态检查 `scripts/authorized_live_token_smoke_harness.py` 不导入 `AuthorizedLivePoyoSubmitter`、`build_authorized_live_poyo_submitter`、`PoyoClient`、`httpx` 或 `POYO_API_KEY`。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py` 通过，结果 `10 passed`；授权 smoke 串联回归 `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_harness.py tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `48 passed`；docs governance `12 passed`；相关 `ruff check` 和 `git diff --check` 通过。
- **边界** — C32 只证明真实 transport 接线前的 no-token factory gate 可审计；未提交 provider job，未读取 poyo key，未验证 poyo key / 余额 / runtime 成功，不能升级为 `L4-authorized-live`。

## 0.82 2026-06-06 AI Video 2.0 C31 no-token submitter facade contract

- **新增 contract facade** — `src/pipeline/authorized_live_poyo_submitter.py` 新增 `AuthorizedLivePoyoSubmitter`，在进入真实 provider transport 前校验 `MediaJobSpec` 是否属于 Momcozy 消毒器样本计划、provider 是否为 `poyo`、model 是否为 `gpt-image-2` / `seedance-2`、视频 job 是否引用三张授权图片 artifact refs。
- **fake transport 测试** — `tests/test_authorized_live_poyo_submitter.py` 使用 fake transport 覆盖图片 job、视频 job、越界 job、transport failure、prompt payload 不回显和无 provider client/env 访问静态守卫。
- **零重试边界** — facade 每个 job 只调用一次 injected transport；transport failure 直接抛出，不自动重试、不返回 stub。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_harness.py` 通过，结果 `13 passed`；授权 smoke 串联回归 `.venv/bin/python -m pytest tests/test_authorized_live_poyo_submitter.py tests/test_authorized_live_harness.py tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `44 passed`；docs governance `12 passed`；相关 `ruff check` 和 `git diff --check` 通过。
- **边界** — C31 只证明授权真实 smoke 的 submitter contract 可在 fake transport 下审计；模块不导入 `PoyoClient`、`httpx`、`POYO_API_KEY` 或 `os.environ`，未提交 provider job，未验证 poyo key / 余额 / runtime 成功，不能升级为 `L4-authorized-live`。

## 0.81 2026-06-06 AI Video 2.0 C24-C29 真实 smoke 前置门禁闭环

- **公开文档重验** — `configs/poyo-current-provider-revalidation-contract.json` 固化 poyo 当前公开 API / `seedance-2` / `gpt-image-2` 文档证据，证据等级仅为 `L1-public-doc-revalidation`，不证明 key、余额、runtime、内容审核或商业交付。
- **最小样本计划** — `configs/authorized-live-token-smoke-sample-plan-contract.json` 将首轮 L4 限定为 Momcozy 消毒器 3 张 `gpt-image-2` 图片 + 1 条 `seedance-2` 15 秒 9:16 image-to-video，总预算 `$3.00`、单任务 `$2.50`、零自动重试；产物只能进入 `pending_review` 素材库。
- **私有授权记录** — `scripts/build_authorized_live_approval_record.py` 要求逐字匹配 C21 授权句，拒绝 `继续下一步` / `同意下一步` 等泛化确认，并拒绝把 approval record 写入正式 repo 目录。
- **账户 readiness 记录** — `scripts/build_provider_account_readiness_record.py` 只记录人工查看 poyo 控制台后的余额/key 配置确认，不记录 API key 原文；余额不足 `$3.00` 时被 preflight 阻断。
- **no-token 启动包** — `scripts/build_authorized_live_smoke_packet.py --include-preflight` 汇总授权句、私有记录 env、sample plan、provider revalidation、命令 preview 和 preflight projection；`scripts/p2_recharge_smoke_checklist.py` 默认 dry-run 已提示先生成该启动包。
- **执行入口边界** — `scripts/p2_recharge_smoke_checklist.py --execute` 不再指向旧 Fast/S1 或整套 Playwright token smoke，而是指向 `scripts/authorized_live_token_smoke_harness.py --execute --pretty`；未显式接线 provider submitter 时 fail-closed，不调用 provider。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_smoke_packet_builder.py tests/test_p2_recharge_smoke_checklist.py tests/test_token_smoke_preflight.py` 通过，结果 `31 passed`；随后 checklist 串联回归 `.venv/bin/python -m pytest tests/test_p2_recharge_smoke_checklist.py tests/test_authorized_live_smoke_packet_builder.py` 通过，结果 `12 passed`；相关 `ruff check` 和 `git diff --check` 通过。
- **边界** — C24-C29 只证明真实 smoke 前的 no-token 门禁输入、私有记录生成规则和执行 preview 可审计；未设置 `RUN_TOKEN_SMOKE=1` 执行，未调用 provider，未验证 poyo key / 余额 / runtime 成功，不能升级为 `L4-authorized-live`。

## 0.80 2026-06-06 AI Video 2.0 C23 工具箱 provider readiness preflight

- **新增入口** — `src/pipeline/toolbox/provider_readiness.py` 和 `GET /toolbox/{tool_id}/provider-readiness` 支持工具级授权前置检查，复用 C21 approval record、API key presence、provider capability、budget stop-loss 与 job ledger/audit readiness。
- **工具授权范围** — `configs/authorized-live-token-smoke-approval-template.json` 的 `sample_plan.toolbox_tool_ids` 必须包含精确工具 id 或 `*`；未列入的工具不能继承其他工具授权。
- **默认阻断** — approval template 仍是 `template_only: true`，即使设置 `RUN_TOKEN_SMOKE=1` 和 fixture API key，也会以 fail-closed 结果阻断真实调用。
- **验证结果** — `.venv/bin/python -m pytest tests/test_authorized_live_provider_harness.py tests/test_toolbox_router.py tests/test_token_smoke_preflight.py tests/test_authorized_live_harness.py` 通过，结果 `34 passed`；`ruff check` 和 `git diff --check` 通过。
- **边界** — C23 只证明工具级 provider readiness 可以在 no-call 模式下阻断或标记 ready；未提交 provider job，未生成媒体，未形成 delivery accepted 或 publish allowed 结论。

## 0.79 2026-06-06 AI Video 2.0 C22 Momcozy S5/toolbox L2 fixture 矩阵

- **新增 fixture** — `tests/fixtures/toolbox/momcozy_toolbox_l2_fixture_matrix.json` 覆盖 Momcozy S5 与 `product-image`、`six-view`、`ecommerce-visual` 等工具箱样本。
- **benchmark 接入** — `scripts/no_token_commercial_benchmark.py` 纳入工具箱 fixture 矩阵，只报告 L2 evidence refs，不读取 provider secret，不提交 provider job。
- **契约覆盖** — `tests/test_toolbox_contracts.py` 与 `tests/test_no_token_commercial_benchmark.py` 约束工具样本必须保持 refs-only、no delivery accepted、no publish allowed。
- **边界** — C22 只证明 Momcozy 工具箱样本可以进入 dry-run 证据矩阵；不代表真实图片生成质量、真实品牌 token 通过或商业交付完成。

## 0.78 2026-06-06 AI Video 2.0 C21 授权审批止损门禁

- **新增模板** — `configs/authorized-live-token-smoke-approval-template.json` 定义 C21 approval record 所需字段，默认 `template_only: true`，不会被误认为已授权。
- **预算止损** — `src/pipeline/token_smoke_preflight.py` 与 `src/pipeline/authorized_live_harness.py` 校验 provider/model、positive finite budget、sample count、provider call ceiling、per-job cost ceiling、retry ceiling 和 halt-on-failure policy。
- **真实执行锁** — `AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1` 与有效 approval record 均满足前，harness 只能 dry-run，不会提交真实 provider job。
- **验证边界** — `tests/test_token_smoke_preflight.py`、`tests/test_authorized_live_harness.py` 与 `tests/test_p2_recharge_smoke_checklist.py` 覆盖缺失 approval、模板未转正、预算字段缺失和 execute flag 缺失等阻断路径。
- **边界** — C21 是授权前置门禁，不是授权本身；没有用户固定授权语句和真实 approval record 时，不能进入 `L4-authorized-live`。

## 0.76 2026-06-04 AI Video 2.0 C19 no-token benchmark 证据边界

- **新增入口** — `scripts/no_token_commercial_benchmark.py` 汇总 brand review、runtime injection、prompt preview audit、commercial gate、production job ledger 与 longform audit 的 dry-run 状态；默认不读取 provider secret，不提交 provider job。
- **检查结果** — `.venv/bin/python -m pytest tests/test_no_token_commercial_benchmark.py -q` 通过，结果 `2 passed in 0.31s`。
- **报告摘要** — `.venv/bin/python scripts/no_token_commercial_benchmark.py --pretty` 输出 `benchmark_id=no_token_commercial_benchmark_20260604152421`，`evidence_level=L2-fixture-or-dry-run`，`provider_calls_made=false`，`authorized_live=false`。
- **状态分布** — benchmark 报告中 `brand_review_candidate_only=blocked`，`runtime_injection_reviewed_bundle=pass`，`prompt_preview_audit=review_required`，`commercial_quality_gate=review_required`，`production_job_ledger=prepared`，`longform_audit=review_required`；汇总为 `blocked_count=1`、`review_required_count=3`。
- **禁止声明** — 当前报告显式禁止声明 `approved brand tokens available`、`candidate ledger approved for runtime injection`、`commercial production ready`、`customer evidence collected`、`delivery accepted`、`provider job submitted`、`publish allowed`。
- **边界** — 本轮只做本地 fixture / dry-run 汇总，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或任何外部 provider。

## 0.77 2026-06-04 AI Video 2.0 C20 dry-run acceptance

- **后端目标集合** — `.venv/bin/python -m pytest tests/test_brand_token_intake.py tests/test_brand_token_review.py tests/test_brand_review_audit_bundle.py tests/test_runtime_injection_executor.py tests/test_runtime_prompt_preview.py tests/test_prompt_preview_audit_bundle.py tests/test_prompt_preview_audit_workflow.py tests/test_prompt_preview_audit_router.py tests/test_longform_audit_bundle.py tests/test_no_token_commercial_benchmark.py tests/test_commercial_gate.py tests/test_production_job_ledger.py` 通过，结果 `63 passed in 1.30s`。
- **后端质量门** — `.venv/bin/python -m ruff check src tests scripts` 通过，结果 `All checks passed!`；为满足该门禁，历史 `scripts/` lint 债已用机械 ruff 修复单独收口。
- **接口漂移** — `.venv/bin/python scripts/check_openapi_types_drift.py` 通过，结果 `OpenAPI generated types are up to date.`。
- **前端质量门** — `cd web && npm run lint` 通过；`cd web && npx tsc --noEmit -p tsconfig.json` 通过；`cd web && npm test` 通过，结果 `43 passed (43)` test files、`199 passed (199)` tests。
- **边界** — C20 只证明 dry-run toolchain 的本地可运行性和只读/fixture 证据一致性；不访问生产、不触发真实生成、不提交 provider job、不形成 delivery accepted 或 publish allowed 结论。

## 0.18 2026-05-31 P1-6 全站 UI/UX 无 token 审计与首轮修复

- **页面加载反馈** — `/s1`-`/s5` 和 `/library` 不再使用 `Suspense fallback={null}`，统一改为 `RoutePageSkeleton`，避免慢设备或 hydration 阻塞时出现无反馈白屏。
- **移动端顶栏** — Home 顶栏对齐 `TopHeader` 的响应式策略：移动端隐藏长标题、压缩间距、保留主导航和管理入口，降低小屏横向挤压。
- **弹层可访问性** — `/works` 预览、`AssetPickerModal`、`Admin Logs` 详情弹层补 `role="dialog"`、`aria-modal`、Escape 关闭和初始焦点；Admin Logs 行补键盘 Enter/Space 打开。
- **关闭按钮语义** — `MaterialsTab`、`InfluencersTab`、`ConfirmModal`、`AssetLibrary` 等关闭按钮改为本地化或更具体 aria label，减少屏幕阅读器中的硬编码英文噪音。
- **审计文档** — 新增 UI/UX 专项方案，记录 5 个 loop 的发现、已完成项、保留债务和后续无 token / 充值后测试边界。
- **验证边界** — 本轮只允许静态页面、只读页面、lint/type/build 与 UI-only 测试；不调用真实生成、Gate candidate 或 POYO 相关接口。

## 0.19 2026-05-31 P1-7 前端布局与弹层单一化

- **Header 单一化** — `TopHeader` 增加 `actions` 插槽，Home 删除内联 header 复制实现，后续导航视觉和 `PipelineStatusBar` 只从 `TopHeader` 演进。
- **QuickTemplate 键盘菜单** — 快捷模板下拉补 `aria-haspopup/menu/menuitem`、Escape 关闭、打开后聚焦首项、Arrow/Home/End 选择和关闭后焦点恢复。
- **AssetLibrary 弹层统一** — 旧作品集弹层补 `role="dialog"`、`aria-modal`、标题关联、Escape 关闭和初始焦点；预览层补独立 dialog/focus/Escape，不再使用 `role="presentation"`。
- **验证边界** — 仍只做前端 UI 行为和静态验证，不触发 `/api/fast/*`、`/scenario/*/submit` 或 Gate candidate 生成接口。

## 0.20 2026-05-31 P1-8 UI-only Playwright 视觉回归

- **独立配置** — 新增 `web/playwright.ui.config.ts` 和 `npm run e2e:ui`，默认只运行 `web/e2e/ui-only/`，不复用会触发真实 API key 依赖的生产 smoke。
- **视觉基线** — 为 `/`、`/s1?mode=expert`、`/works`、`/library` 建立 desktop/mobile Chromium viewport 截图基线，覆盖核心导航、S1 表单、作品页和资产库布局。
- **交互 smoke** — `QuickTemplate` 覆盖打开、首项聚焦、Arrow/Home 键导航、Escape 关闭和焦点恢复。
- **Token 防护** — 测试运行时写入 fake API key + demo mode，只 mock `/health`、admin session、portfolio 等只读接口；任何 `/fast/*` 生成、`/scenario/*` 生成/Gate、`/pipeline/*` mutating、上传、发布类请求都会被 451 拦截并使测试失败。
- **稳定性取舍** — 视觉基线使用固定 viewport 而非 full-page；full-page 在 S1 长表单下存在 3px 高度抖动，容易把无意义排版噪声变成误报。

## 0.21 2026-05-31 P1-9 UI-only 视觉回归 CI 接入

- **独立 workflow** — 新增 `.github/workflows/e2e-ui.yml`，只在 `web/src/**`、`web/e2e/ui-only/**`、`web/playwright.ui.config.ts`、`web/package*.json` 或 workflow 自身变更时触发。
- **macOS runner 选择** — UI 截图基线当前为 `darwin` 后缀；CI 使用 `macos-latest` + Chromium，避免 Ubuntu 字体/平台后缀造成非产品问题的假失败。
- **无 token 边界** — workflow 不读取任何生产 secret；运行 `NEXT_PUBLIC_IS_DEMO=true npm run e2e:ui`，测试自身仍会 mock 只读接口并拦截生成、上传、发布类请求。
- **失败证据** — CI 失败时上传 Playwright HTML report 与 `web/test-results/ui-only/` trace，便于定位布局差异或误触发 token-consuming endpoint。

## 0.22 2026-05-31 P1-10 UI-only 无 token 护栏测试

- **配置护栏** — 新增 `web/src/lib/uiOnlyE2eGuard.test.ts`，用 Vitest 锁定 `npm run e2e:ui` 必须指向 `playwright.ui.config.ts`，且 UI config 不允许依赖 `PLAYWRIGHT_PROD_URL` / `PLAYWRIGHT_API_KEY`。
- **请求护栏** — 静态检查 `web/e2e/ui-only/site-ui.visual.spec.ts` 必须保留 `GENERATION_ENDPOINT_PATTERNS`、451 拦截、fake API key 和 demo mode。
- **CI 护栏** — 静态检查 `.github/workflows/e2e-ui.yml` 不引用 `secrets.`、`PLAYWRIGHT_API_KEY`、`PLAYWRIGHT_PROD_URL` 或 `e2e:prod`，确保无余额阶段的 UI-only CI 不漂移到生产 smoke。
- **Vitest 稳定性** — `web/vitest.config.ts` 默认 `testTimeout` 提高到 15s，和此前 page smoke 手工验证命令一致，避免模块导入 smoke 在 CI 机器上因 5s 默认值误失败。

## 0.23 2026-05-31 P1-11 前端 CI 硬门禁对齐

- **TypeScript 不再软失败** — `.github/workflows/ci.yml` 已移除 `continue-on-error: true`，`npx tsc --noEmit -p tsconfig.json` 失败会阻断主 CI。
- **前端主质量门闭环** — `frontend-test` job 升级为 `Frontend quality gate`，顺序执行 `npx eslint src e2e playwright.ui.config.ts playwright.prod.config.ts`、TypeScript、`npm test -- --run` 和 `npm run build`。
- **无 token 边界** — `next build` 只设置 `NEXT_PUBLIC_IS_DEMO=true`，不读取生产 API key、POYO key 或 `PLAYWRIGHT_*` 生产 smoke 变量。
- **职责边界** — UI-only Playwright 视觉回归仍由 `.github/workflows/e2e-ui.yml` 独立负责；主 CI 负责更快的静态、单测和构建失败前置。

## 0.24 2026-05-31 P1-12 production E2E token smoke 隔离

- **默认跳过真实任务** — `web/playwright.prod.config.ts` 默认 `grepInvert: /@token-smoke/`，本地和 CI 的 `e2e:prod` 不再默认执行会创建真实后台任务、启动 S1 step 或触发 gate candidate 的生产 spec。
- **显式开启条件** — `.github/workflows/e2e-prod.yml` 新增 `run_token_smoke` 手动 input，并把结果传入 `RUN_TOKEN_SMOKE`；当显式开启但仍使用 `ai_video_demo_2026` fallback key 时直接失败，避免误以为已经跑通真实 smoke。
- **生产 spec 标记** — `fast-mode-submit`、`user-journey`、`s1-gate`、`s1-step-by-step` 中的真实任务创建/编排测试已标记 `@token-smoke`；只读页面、i18n、portfolio、health 和 422/401 错误路径继续默认可跑。
- **防回归测试** — 新增 `prodE2eTokenGuard.test.ts`，静态检查 prod config、workflow input 和已知 token-smoke 测试标题，防止生产 E2E 默认 CI 再漂移到真实生成路径。

## 0.25 2026-05-31 P1-13 production deploy preflight 对齐

- **部署前端门禁对齐主 CI** — `.github/workflows/deploy.yml` 的 `preflight` 现在执行 `npm ci`、`npx eslint src e2e playwright.ui.config.ts playwright.prod.config.ts`、`npx tsc --noEmit -p tsconfig.json`、`npm test -- --run` 和 `npm run build`。
- **构建不依赖生产 token** — deploy preflight 的 frontend build 设置 `NEXT_PUBLIC_IS_DEMO=true`，只验证 Next 构建完整性，不读取生产 API key 或 POYO key。
- **远程部署默认无真实 smoke** — GitHub Actions 调用 Lighthouse deploy 时显式传入 `RUN_TOKEN_SMOKE=0`；真实生成 smoke 仍只能按当前 `L4A/L4B/L4C` 计划手动显式开启。
- **防回归测试** — `tests/test_deploy_workflow.py` 已补静态检查，锁定 deploy preflight 前端质量门和 `RUN_TOKEN_SMOKE=0` 默认值。

## 0.26 2026-05-31 P1-14 deploy pytest timeout 依赖闭环

- **失败证据** — 本地复现 `.venv/bin/python -m pytest tests/test_deploy_workflow.py --timeout=60 -q` 失败，错误为 `unrecognized arguments: --timeout=60`；说明 GitHub deploy preflight 依赖 `pytest-timeout` 但 dev 依赖未声明。
- **依赖修复** — `pyproject.toml` 的 `dev` extra、`requirements.txt` development 区和 `uv.lock` 已加入 `pytest-timeout`，使 `python -m pytest ... --timeout=60` 在 CI 安装路径中可用。
- **防回归测试** — `tests/test_deploy_workflow.py` 新增静态检查：只要 deploy preflight 保留 `--timeout=60`，就必须在 `pyproject.toml` 和 `requirements.txt` 中声明 `pytest-timeout`。
- **20-loop 队列起点** — 本轮把 P1-14~P1-33 定义为充值前 20 个可执行 loop；每个 loop 必须能通过本地静态、unit、lint 或文档验证闭环，不依赖真实 POYO 余额。

## 0.27 2026-05-31 P1-15 CI Python lint parity

- **ruff 口径统一** — `.github/workflows/ci.yml` 和 `.github/workflows/deploy.yml` 已从 `ruff check src/` 改为 `ruff check src tests`，让测试目录继续受主 CI 和 deploy preflight 保护。
- **防回归测试** — `tests/test_deploy_workflow.py` 新增 CI / deploy workflow 静态检查，锁定 `ruff check src tests` 口径，避免后续只 lint `src`。
- **本地证据** — `.venv/bin/ruff check src tests --statistics` 通过，说明当前把 `tests` 纳入 CI 不会制造红灯。

## 0.28 2026-05-31 P1-16 CI hermetic env guard

- **pytest env 显式化** — `.github/workflows/ci.yml` 和 `.github/workflows/deploy.yml` 的 Python test step 已显式设置 `API_KEY` 为测试值，并把 `DEEPSEEK_API_KEY`、`POYO_API_KEY`、`SEEDANCE_API_KEY`、`SILICONFLOW_API_KEY`、`ELEVENLABS_API_KEY`、TikTok、Shopify、Supabase 等外部凭证置空。
- **防 secrets 漂移** — `tests/test_deploy_workflow.py` 新增 hermetic env 静态检查，断言 CI / deploy pytest env 不引用 `secrets.*`，且所有外部 provider / 发布平台 key 都只能是空值或测试值。
- **50-loop 队列扩展** — 当前充值前队列扩展到 P1-16~P1-65，覆盖 CI、防护、文档治理、无 token hermetic 回归、前端错误路径和部署脚本静态守卫。

## 0.29 2026-05-31 P1-17 Python dev dependency parity

- **requirements 补齐** — `requirements.txt` development 区补 `pytest-mock>=3.12` 和 `pytest-cov>=4.1`，与 `pyproject.toml` 的 `dev` extra 对齐。
- **一致性守卫** — 新增 `tests/test_python_dependency_parity.py`，静态检查 `pyproject.toml` dev dependencies 必须同时出现在 `requirements.txt` 和 `uv.lock`。
- **目的边界** — 该检查只覆盖 Python developer tooling 依赖一致性，不改变 runtime dependency，不触发外部服务。

## 0.30 2026-05-31 P1-18 README package-manager drift cleanup

- **README 对齐 npm** — README 前端 prerequisites、install、dev、test、lint 和 E2E 命令已从 `pnpm` 改为 `npm`，与 `web/package-lock.json` 和 GitHub Actions `npm ci` 保持一致。
- **防回归测试** — 新增 `tests/test_readme_frontend_tooling.py`，静态检查 README 不再出现 `pnpm`，且保留 `npm ci`、`npm run dev`、`npm test -- --run`、`npm run e2e:ui`、`npm run e2e:prod` 等当前命令。
- **边界** — 本轮只修当前 README；历史 research / archived 文档中的旧命令暂不清理，避免破坏历史语境。

## 0.31 2026-05-31 P1-19 e2e-prod secret/runbook coverage

- **新增 runbook** — 新增 `docs/runbooks/production-e2e-token-smoke.md`，明确 `e2e-prod` 默认跳过 `@token-smoke`；2026-06-11 后当前正式路径为 `L4A` 受控 provider smoke、`L4B` 前端只读回读，完整 `run_token_smoke=true` 只保留为 `L4C` 扩展入口。
- **显式失败条件** — runbook 记录：如果 `run_token_smoke=true` 但仍使用 `ai_video_demo_2026`，workflow 会失败，避免误以为已经跑通真实生成 smoke；当前首轮不以该入口执行。
- **防回归测试** — `prodE2eTokenGuard.test.ts` 已检查 runbook 必须包含 `PROD_DEMO_API_KEY`、`run_token_smoke`、`RUN_TOKEN_SMOKE=1`、`@token-smoke` 和充值前置说明。

## 0.32 2026-05-31 P1-20 production Playwright no-mutation scan

- **风险请求扫描** — `prodE2eTokenGuard.test.ts` 会遍历 `web/e2e/production/*.prod.spec.ts`，扫描 `request.post/put/patch/delete` 指向 `/api/fast/submit`、`/api/scenario/`、`/api/pipeline/`、上传、发布、分发等高风险 endpoint 的调用。
- **默认不新增真实生成** — 未标记 `@token-smoke` 的高风险 mutating request 会使测试失败，防止 production E2E 默认集合重新混入真实任务创建、gate candidate 生成或发布类动作。
- **负向路径显式 allowlist** — 现有 422/401 错误路径保留默认可跑，但必须在 `SAFE_NEGATIVE_MUTATION_TEST_TITLES` 中逐条列名，避免把“不会消耗 token”的判断隐藏在测试正文里。

## 0.33 2026-05-31 P1-21 deploy rsync exclude parity

- **部署同步 SSOT** — `.github/workflows/deploy.yml` 的 `Rsync to server` 步骤不再维护 inline `--exclude` 列表，改为 `--exclude-from='deploy/lighthouse/rsync-excludes.txt'`。
- **排除项覆盖** — 静态测试锁定 `.git`、`.env`、`.venv`、`output`、`tmp`、frontend build/report artifacts、`rendering/node_modules` 和 Lighthouse 生产 secret/cert/pem 文件必须在 excludes 清单中。
- **维护边界** — 后续新增部署排除项只改 `deploy/lighthouse/rsync-excludes.txt`；GitHub Actions 不再复制一份容易漂移的列表。

## 0.34 2026-05-31 P1-22 smoke script token guard tests

- **脚本静态守卫** — 新增 `tests/test_lighthouse_smoke_token_guard.py`，只读 `deploy/lighthouse/deploy.sh` 和 `deploy/lighthouse/smoke.sh`，不执行部署、不发 HTTP 请求。
- **真实生成 curl 约束** — 测试会合并 bash 续行并扫描 `curl` / `$CURL` 命令；命中 `/api/fast/generate`、`/api/fast/submit`、`/api/scenario/`、`/api/pipeline/start` 或 `/gate/` 的调用必须位于 `RUN_TOKEN_SMOKE=1` guard 内。
- **默认 smoke 边界** — 注释、echo 和无 `X-API-Key` 的 401 鉴权负向探针不算真实生成风险；只有带鉴权的真实 curl 命令受约束，避免误伤文档化提示，同时防止默认部署 smoke 偷跑生成链路。

## 0.35 2026-05-31 P1-23 S1-S5 hermetic regression command

- **固定入口** — 新增 `scripts/run_s1_s5_hermetic_regression.sh` 与 `make test-hermetic-scenarios`，把 S1-S5、gate config、step regenerate、continuity、candidate scorer、degradation/fault 注入等无 token 回归集合固定为一个命令。
- **凭证清空** — 脚本显式清空 DeepSeek、POYO、Seedance、SiliconFlow、ElevenLabs、TikTok、Shopify、Supabase 等外部凭证，并默认 `PYTEST_INCLUDE_HERMETIC_SLOW=1`。
- **文档与守卫** — 新增 `docs/runbooks/s1-s5-hermetic-regression.md` 和 `tests/test_scenario_hermetic_regression_command.py`，防止命令漂移到生产 URL、curl、`RUN_TOKEN_SMOKE=1` 或真实生成 endpoint。

## 0.36 2026-05-31 P1-24 POYO diagnostic script gating

- **显式二次确认** — `debug_poyo_403.py`、`diagnose_poyo.py`、`discover_poyo_models.py`、`probe_sora2pro.py` 都要求 `CONFIRM_POYO_PROBE=1`，只设置 `POYO_API_KEY` 不会运行真实 submit。
- **消耗提示** — 4 个脚本的 docstring / 错误信息都明确说明会提交真实 poyo.ai generation request，可能消耗 credits；这类脚本只允许充值后人工运行。
- **默认入口隔离** — 新增 `tests/test_poyo_probe_script_guard.py`，确认 Makefile、CI、deploy、e2e-prod 和 S1-S5 hermetic 脚本不会默认调用 POYO probe；同时收紧 `diagnose_poyo.py` 的 key 打印为短 mask。

## 0.37 2026-05-31 P1-25 UI visual baseline SOP

- **新增 SOP** — 新增 `docs/runbooks/ui-visual-baseline-sop.md`，明确 UI-only snapshot 更新必须先复现失败、确认 UI/source 变更、再执行 `npm run e2e:ui -- --update-snapshots`。
- **防止随手更新** — SOP 要求更新后审查 `git diff -- web/e2e/ui-only`，并复跑 `npm run e2e:ui` 与 `npm test -- --run src/lib/uiOnlyE2eGuard.test.ts`。
- **无 token 边界** — `uiOnlyE2eGuard.test.ts` 现在检查 SOP 必须保留 `GENERATION_ENDPOINT_PATTERNS`、`PLAYWRIGHT_API_KEY`、`RUN_TOKEN_SMOKE=1` 和 “Do not update baselines” 等约束文本。

## 0.38 2026-05-31 P1-26 Runtime media image guard 扩展

- **裸 img 收口** — `SceneSelector`、`works`、`OneShotResultView`、`VideoWorkflow`、`AssetCard` 的后端运行时缩略图 / 生成图已改用 `RuntimeMediaImage`。
- **单一例外点** — `web/src` 中唯一允许的 `<img>` 和 `@next/next/no-img-element` 例外保留在 `RuntimeMediaImage.tsx`，用于后端 / 用户资产 URL，避免把动态媒体路径塞进 Next image allowlist。
- **防回归测试** — 新增 `runtimeMediaImageGuard.test.ts`，递归扫描 `web/src/**/*.tsx`，除 `RuntimeMediaImage.tsx` 外不允许出现裸 `<img>` 或 `@next/next/no-img-element`，并锁定已知运行时媒体消费者必须继续使用该组件。

## 0.39 2026-05-31 P1-27 admin 页面可访问性 smoke

- **统一 smoke** — 新增 `admin-accessibility-smoke.test.tsx`，用 mocked `adminFetchJson` / `adminFetch` 覆盖 admin login、layout、sidebar、dashboard、logs、health、tenants 的本地渲染，不访问真实后端。
- **语义修复** — `AdminLoginPage` 补 `label`、`role="alert"`、`aria-describedby`；`AdminSidebar` 补 `aria-label` 与 active link `aria-current`；`AdminLayout` 补 loading `role="status"` 与 logout `aria-label`。
- **表单与弹层语义** — logs 筛选补 `aria-label` / `aria-pressed`；tenants 搜索和创建弹层补 labeled fields、dialog 语义、关闭按钮 aria label 与创建错误 alert。
- **测试环境收口** — `vitest.setup.ts` 显式设置 React 19 `IS_REACT_ACT_ENVIRONMENT`，避免 createRoot 单测刷屏 `act(...)` 环境警告，降低 CI 输出噪音。

## 0.40 2026-05-31 P1-28 i18n translation completeness guard

- **完整性 guard** — 新增 `translationCompleteness.test.ts`，锁定 `translations.zh` / `translations.en` key 集合必须一致，防止只补一端语言。
- **源码引用扫描** — 测试递归扫描 `web/src` 非测试源码中的静态 `t("...")` 调用；动态前缀如 `t("platform." + id)` 不误判，但明确写死的 key 必须存在。
- **空值收口** — EN 侧 `upload.count`、`review.scripts`、`asset.count` 不再为空；同步补齐 `upload.cancel`、`pipeline.error`、`pipeline.paused`、`gate.awaitingApproval`。
- **无 token 边界** — 该 guard 只读取本地源码和翻译表，不访问后端、不触发生成接口。

## 0.41 2026-05-31 P1-29 apiFetch error normalization tests

- **S1 step-by-step 错误标准化** — `startS1StepByStep`、`runS1Step`、`regenerateS1Step`、`resumeS1`、`fetchS1State`、`updateS1State` 的非 2xx 分支统一抛 `ApiError`，不再降级为只含 statusText 的普通 `Error`。
- **401/422/429 契约测试** — 新增 `apiFetchErrorNormalization.test.ts`，mock `fetch` 覆盖 401 API key 错误、422 field errors、429 retry metadata，防止前端 toast / 表单错误丢结构化信息。
- **实现边界** — 仅收口活跃 S1 手动执行 API；旧 LangGraph proxy、deprecated S2/S3 wrapper 是否迁移到 `ApiError` 留给后续单独任务，避免扩大本轮行为变更。
- **无 token 边界** — 测试全程使用 mocked `fetch`，不访问后端、不触发 `/scenario/*` 真实生成。

## 0.42 2026-05-31 P1-30 env config SSOT drift guard

- **静态 SSOT guard** — 新增 `tests/test_env_config_ssot.py`，锁定 `DEFAULT_LLM_PROVIDER=deepseek`、`DEEPSEEK_API_BASE=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-v4-pro`、`POYO_API_BASE_URL=https://api.poyo.ai`、`POYO_IMAGE_MODEL=gpt-image-2`、`POYO_VIDEO_MODEL=seedance-2`。
- **覆盖范围** — guard 同时检查 `src/config.py` fallback、`.env.example`、`render.yaml` 和两篇 CloudBase 部署文档；不读取 gitignored `deploy/lighthouse/.env.prod`，避免接触真实 secret。
- **配置补齐** — `render.yaml` 增加 DeepSeek/POYO 非 secret 默认值，并补 `DEEPSEEK_API_KEY` 空占位；CloudBase 文档补齐同一组默认值。
- **历史边界** — `docs/research`、旧 Sprint 计划和已标注历史快照的 poyo 模型矩阵不参与本 guard，避免把历史研究文档误当当前部署真相。

## 0.43 2026-05-31 P1-31 docs link-check scope hardening

- **阻断式 link check** — `.github/workflows/ci.yml` 的 `docs-link-check` 不再 `fail: false` 或 `continue-on-error: true`，lychee 失败会阻断主 CI。
- **当前文档 allowlist** — 新增 `configs/docs-link-check-scope.txt`，只纳入 README、AGENTS、当前 TODO / project standard、API reference、runbooks、ADR、active deploy/workflow/knowledge/product docs。
- **历史资料隔离** — `.kiro/plan/*`、`docs/research/*`、`docs/superpowers/plans/*`、`docs/superpowers/specs/*` 不进入阻断式 link check；需要恢复为当前资产时先进入 allowlist。
- **防回归测试** — 新增 `tests/test_docs_link_check_scope.py`，锁定 lychee 的 offline/local exclude、禁止宽 glob、要求 CI 参数与 scope 清单完全一致。
- **无 token 边界** — 本轮只改 GitHub Actions 文档检查和静态测试，不访问网络、不触发真实生成、不读取 provider secret。

## 0.44 2026-05-31 P1-32 Docker build no-token preflight

- **compose config-only 预检** — `.github/workflows/ci.yml` 与 `.github/workflows/deploy.yml` 新增 `Docker compose config validation (no start)`，只创建空 `.env` / `.env.prod` 并执行 `docker compose ... config --quiet`。
- **Docker build secret 边界** — `tests/test_docker_no_token_preflight.py` 锁定 CI/deploy 的 `docker/build-push-action@v5` 只能 `push: false`、`load: false`，且 build args 只能是 `APT_MIRROR`、`PIP_INDEX_URL`。
- **禁止误触发 runtime smoke** — 同一测试禁止 compose 预检步骤出现启动容器、`curl`、`/api/fast`、`/api/scenario`、`/api/pipeline`、Gate 或 `RUN_TOKEN_SMOKE=1`。
- **Runbook 固化** — 新增 `docs/runbooks/docker-no-token-preflight.md` 并纳入 `configs/docs-link-check-scope.txt`，说明 Docker 预检只验证配置和构建上下文，不读取生产 secret、不触发 provider。
- **无 token 边界** — 本轮没有运行 Docker compose、没有请求 `/health`、没有调用 DeepSeek/POYO/SiliconFlow 等外部服务。

## 0.45 2026-05-31 P1-33 P2 recharge smoke checklist dry-run

- **默认 dry-run 入口** — 新增 `scripts/p2_recharge_smoke_checklist.py`，默认只输出充值后真实 smoke 的 checklist 和将要执行的命令，不访问生产、不触发 provider。
- **双确认执行** — `--execute` 必须同时设置 `CONFIRM_P2_TOKEN_SMOKE=1` 与 `RUN_TOKEN_SMOKE=1`，缺任一开关都会以配置错误退出。
- **demo key 拒绝** — 脚本拒绝使用 `ai_video_demo_2026` 作为 `API_KEY` 或 `PLAYWRIGHT_API_KEY` 执行真实 smoke，避免误以为已经跑通非 demo 生产路径。
- **Runbook 固化** — 新增 `docs/runbooks/p2-recharge-smoke-checklist.md` 并纳入 docs link-check scope，明确充值前只跑 dry-run，充值后再执行 `deploy/lighthouse/smoke.sh` token path 与 `npm run e2e:prod`。
- **防回归测试** — 新增 `tests/test_p2_recharge_smoke_checklist.py`，覆盖默认 dry-run、双确认、demo key 拒绝、runbook 与 link-check scope。

## 0.46 2026-05-31 P1-34 backend route auth contract scan

- **路由鉴权契约** — 新增 `configs/backend-route-auth-contract.yaml`，明确公开路由只允许 `/health`、Prometheus `/metrics`、`/api/media/{media_path:path}` 和 admin login。
- **router mount 守卫** — 新增 `tests/test_backend_route_auth_contract.py`，静态检查 `src/api.py` 中 pipeline/scenario/distribution/metrics/assets/portfolio/legacy assets/telemetry 都必须通过 `verify_api_key` 挂载。
- **admin 双层 auth 守卫** — 同一测试扫描 `/api/admin/*` endpoint：login 以外必须依赖 `verify_admin_session`，写操作必须额外依赖 `verify_csrf_token`。
- **公开面防漂移** — 任何新增未记录公开 route 都会失败；要新增公开 route 必须先更新 contract 并写 reason。
- **Runbook 固化** — 新增 `docs/runbooks/backend-route-auth-contract.md` 并纳入 docs link-check scope，作为后续新增 backend route 的审查入口。

## 0.47 2026-05-31 P1-35 API response metadata guard

- **响应元信息契约** — 新增 `configs/api-response-metadata-contract.yaml`，锁定非 `/health` JSON response 必须包含 `_meta.trace_id`、`duration_ms`、`version` 和 `timestamp`。
- **Trace header 守卫** — 新增 `tests/test_api_response_metadata_contract.py`，用本地 ASGI app 覆盖 `X-Client-Trace-Id` 回显到 `X-Trace-Id`，并确认 `_meta.trace_id` 与 header 一致。
- **错误响应 shape** — 同一测试覆盖缺失 API key 的 401 响应，要求保留 `detail` 并注入 `_meta`；契约文件同时要求 429 继续保留 `retry_after_sec`。
- **`/health` 边界** — `/health` 仍返回 `X-Trace-Id`，但不注入 `_meta`，避免健康检查 body 被通用 wrapper 扩写。
- **Runbook 固化** — 新增 `docs/runbooks/api-response-metadata-contract.md` 并纳入 docs link-check scope，后续改 middleware、rate limit、错误 handler 或前端 `ApiError` 解析时先跑该守卫。

## 0.48 2026-05-31 P1-36 rate-limit config/test parity

- **限流契约固化** — 新增 `configs/api-rate-limit-contract.yaml`，锁定 FastAPI fallback middleware 为 `120 req / 60s / IP`、最多追踪 `1000` 个 IP。
- **skip path 守卫** — 契约和测试锁定 `/health` 与 `/api/media/` 必须跳过 FastAPI fallback 限流，避免健康检查和作品集媒体并发加载被误伤。
- **429 行为测试** — 新增 `tests/test_api_rate_limit_contract.py`，用本地 ASGI app 对 `/api/files` 负向鉴权路径连续请求触发 429，确认响应保留 `detail`、`retry_after_sec`、`_meta` 和 `X-Trace-Id`。
- **无 token 边界** — 429 行为测试只触发 401/429 本地路径，不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或任何外部 provider。
- **Runbook 固化** — 新增 `docs/runbooks/api-rate-limit-contract.md` 并纳入 docs link-check scope，后续改 nginx / FastAPI 限流或 429 呈现时先跑该守卫。

## 0.49 2026-05-31 P1-37 health endpoint no-secret guard

- **公开健康检查脱敏** — `src/routers/health.py` 在返回前递归清洗健康 payload，替换 provider key、DSN、password、token、signing secret 和服务器绝对路径。
- **错误字符串防泄漏** — 新增 `tests/test_health_endpoint_no_secret_guard.py`，mock 数据库和 Remotion 探针返回含 `DATABASE_URL`、`POYO_API_KEY`、`DEEPSEEK_API_KEY`、`MEDIA_SIGN_SECRET` 与本地绝对路径的错误，确认 `/health` 只暴露 `[redacted]` / `[internal-path]`。
- **契约固化** — 新增 `configs/health-endpoint-no-secret-contract.yaml`，锁定 `/health` 允许的顶层字段和禁止值类型。
- **响应边界保持** — `/health` 继续跳过 `_meta`，但保留 `status`、`version`、`remotion`、`persistence`、`media_tools` 能力状态。
- **Runbook 固化** — 新增 `docs/runbooks/health-endpoint-no-secret.md` 并纳入 docs link-check scope，后续新增健康探针字段必须先跑该守卫。

## 0.50 2026-05-31 P1-38 admin CSRF doc/test parity

- **跨层契约固化** — 新增 `configs/admin-csrf-contract.yaml`，锁定 admin CSRF cookie/header、只读方法、写操作方法、login 豁免和前端 helper 规则。
- **cookie path 修复** — `admin_csrf` cookie 从 `path=/api/admin` 改为 `path=/`，保证 `/admin/*` 前端页面能读取 cookie 并为 `/api/admin/*` mutating request 附加 `X-CSRF-Token`；`admin_session` 仍保持 `HttpOnly` + `path=/api/admin`。
- **后端静态守卫** — 新增 `tests/test_admin_csrf_contract.py`，确认 admin 写操作除 login 外必须依赖 `verify_admin_session` 和 `verify_csrf_token`，login 必须设置浏览器可读 CSRF cookie。
- **前端行为守卫** — 新增 `web/src/components/adminCsrfContract.test.ts`，确认 `adminFetch` 对 POST 附加 `X-CSRF-Token`、删除 `X-API-Key`、对 GET 不附加 CSRF header。
- **Runbook 固化** — 新增 `docs/runbooks/admin-csrf-contract.md` 并纳入 docs link-check scope，后续改 admin auth、cookie 或前端调用约定时先跑该守卫。

## 0.51 2026-05-31 P1-39 background task registry leak guard

- **自动清理行为锁定** — 新增 `tests/test_bg_registry_leak_contract.py`，覆盖 background task 正常 completed、failed、externally cancelled 后无需 shutdown 也会从 registry 移除。
- **shutdown 行为复用** — 保留并联跑 `tests/test_bg_registry.py`，继续覆盖 FastAPI lifespan shutdown 会取消并清空注册任务。
- **契约固化** — 新增 `configs/background-task-registry-contract.yaml`，锁定通用注册入口、snapshot 字段、自动清理触发条件和 shutdown 行为。
- **无 token 边界** — 测试只创建本地 asyncio task，不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。
- **Runbook 固化** — 新增 `docs/runbooks/background-task-registry-leak.md` 并纳入 docs link-check scope，后续新增 fire-and-forget task 先跑该守卫。

## 0.52 2026-06-01 P1-40 scenario state persistence schema guard

- **初始化 shape 锁定** — 新增 `tests/test_scenario_state_persistence_schema_contract.py`，逐一初始化 S1-S5 state，并读取 pytest 临时目录中的 filesystem JSON，断言 `schema_version`、`label`、`scenario`、`tenant_id`、`config`、`steps`、`current_step`、`mode`、`trace_id`、`errors`、`media_synthesis_errors`、`gates`、`pipeline_degraded`、`degraded_reason`、`structured_errors` 全部存在。
- **FS / PG shape 对齐** — `StepRunner.init_state()` 初始化时显式写入 `gates={}`、`pipeline_degraded=false`、`degraded_reason=null`、`structured_errors=[]`，避免 filesystem fallback 与 PG load 默认字段不一致。
- **契约固化** — 新增 `configs/scenario-state-persistence-contract.yaml`，锁定 S1-S5、允许 mode、顶层字段、JSON object/list 字段和每个 step record 的 required keys。
- **无 token 边界** — 测试只调用 `StepRunner.init_state()`，不访问 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。
- **Runbook 固化** — 新增 `docs/runbooks/scenario-state-persistence-schema.md` 并纳入 docs link-check scope，后续改 state persistence、step order、gate state 或 PG projection 先跑该守卫。
- **验证闭环** — `pytest tests/test_scenario_state_persistence_schema_contract.py tests/test_docs_link_check_scope.py -q` 通过，结果 `12 passed`；`pytest tests/test_s1_gate_full_flow.py tests/test_gate_scenario_configs.py tests/test_phase0_regression.py -q` 通过，结果 `110 passed`；`ruff check src tests --statistics` 和 `git diff --check` 通过。

## 0.53 2026-06-01 P1-41 gate approve idempotency guard

- **重复提交幂等化** — `approve_gate()` 对已 approved 且 `selected_ids` 完全一致的重复请求返回 `approved=true`、`idempotent=true`，不再返回 error，也不重写 `approved_at` 或 step output。
- **冲突提交保护** — 已 approved gate 收到不同 `selected_ids` 时仍返回 conflict/error，避免 silent overwrite 既有人工选择。
- **背景恢复去重** — `approve_gate_decision()` 收到 `idempotent=true` 时直接返回 `resumed=false`、`resuming=false`，不创建 background task，不重复调用 `StepRunner.resume()`。
- **契约固化** — 新增 `configs/gate-approve-idempotency-contract.yaml` 和 `tests/test_gate_approve_idempotency_contract.py`，覆盖底层 state 不变与 router 不重复 resume。
- **Runbook 固化** — 新增 `docs/runbooks/gate-approve-idempotency.md` 并纳入 docs link-check scope，后续改 gate approve、前端重试或 background resume 先跑该守卫。
- **验证闭环** — `pytest tests/test_gate_approve_idempotency_contract.py tests/test_s1_gate_full_flow.py tests/test_docs_link_check_scope.py -q` 通过，结果 `50 passed`；`pytest tests/test_gate23_lifecycle.py tests/test_gate_scenario_configs.py -q` 通过，结果 `65 passed`；`ruff check src tests --statistics` 和 `git diff --check` 通过。

## 0.54 2026-06-01 P1-42 regenerate downstream invalidation guard

- **Gate 失效规则锁定** — `invalidate_downstream()` 现在会根据场景 gate definitions 删除“当前 regenerated step 或 downstream step 触发”的 gate entries，避免旧 candidates、旧 approval 或 final review 在上游重生成后继续生效。
- **上游审批保留** — 重生成 `keyframe_images` 等中游 step 时，`gate_1_script` 这类上游 gate 保留；只清理当前 step 及其下游 gate。
- **审计字段** — 被清理的 gate 写入 `state.invalidated_gates`，包含 `gate_id`、`after_step`、`invalidated_by`，方便前端刷新和后续诊断。
- **契约固化** — 新增 `configs/regenerate-downstream-invalidation-contract.yaml` 和 `tests/test_regenerate_downstream_invalidation_contract.py`，覆盖 S1 从 `scripts` 与 `keyframe_images` 发起 regenerate 的 gate 失效边界。
- **Runbook 固化** — 新增 `docs/runbooks/regenerate-downstream-invalidation.md` 并纳入 docs link-check scope，后续改 regenerate、step order 或 gate definitions 先跑该守卫。
- **验证闭环** — `pytest tests/test_regenerate_downstream_invalidation_contract.py tests/test_scenario_step_regenerate_router.py tests/test_docs_link_check_scope.py -q` 通过，结果 `11 passed`；`pytest tests/test_gate_approve_idempotency_contract.py tests/test_s1_gate_full_flow.py tests/test_gate23_lifecycle.py tests/test_gate_scenario_configs.py -q` 通过，结果 `111 passed`；`ruff check src tests --statistics` 和 `git diff --check` 通过。

## 0.55 2026-06-01 P1-43 S4 footage asset filtering regression

- **Live Shoot alias 锁定** — `/works` 的 S4 筛选现在把 `s4`、`live_shoot`、`live_shoot_to_video`、`s4_live_shoot` 场景值和文件名前缀统一归入 Live Shoot，避免缺少 `scenario` 字段的 S4 成品落入 `other`。
- **前端回归测试** — 新增 `web/src/app/works/works-page-filtering.test.tsx`，用 mocked portfolio response 覆盖 `live_shoot_*` 与 `live_shoot_to_video_*` 成品在 Live Shoot filter 下仍可见。
- **后端分层契约** — 新增 `tests/test_portfolio_s4_filtering_contract.py`，确认 S4 `renders/*.mp4` 只进入 `final_work`，S4 `seedance/*.mp4` 中间素材只进入 `creation_intermediate`。
- **契约固化** — 新增 `configs/s4-footage-filtering-contract.yaml` 和 `docs/runbooks/s4-footage-filtering.md`，后续改 `/works`、`/library`、portfolio `kind` 或 S4 输出命名先跑该守卫。
- **无 token 边界** — 本轮只用 mocked response、pytest 临时目录文件和静态文档检查，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.56 2026-06-01 P1-44 media URL sanitizer guard

- **前端 URL builder 收口** — `getMediaUrl()` 和 `getSignedMediaUrl()` 复用同一 sanitizer，拒绝 `http(s):`、`javascript:`、`data:`、`blob:`、`//host/path`、query/hash 和 `..` / `%2e%2e` / `%252e%252e` traversal 输入。
- **签名请求前置拒绝** — `getSignedMediaUrl()` 对非法路径直接返回空字符串，不再请求 `/api/media/sign`，避免把危险 path 交给后端 fallback。
- **后端 basename fallback 防护** — `_resolve_media_path()` 在 basename fallback 前先解码并拒绝 scheme、protocol-relative URL、空段、`.`、`..`、query/hash 和编码 traversal，避免 `https://evil/secret.mp4` 命中本地同名文件。
- **契约固化** — 新增 `configs/media-url-sanitizer-contract.yaml` 和 `docs/runbooks/media-url-sanitizer.md`，后续改 portfolio thumbnail、upload preview、media signer 或 runtime media component 先跑该守卫。
- **无 token 边界** — 本轮只用字符串单测、mocked fetch 和 pytest 临时目录文件，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.57 2026-06-01 P1-45 thumbnail coverage dry-run

- **只读覆盖率脚本** — 新增 `scripts/portfolio_thumbnail_coverage.py`，按 portfolio 分类扫描 `output/` 下有效视频和既有 `thumbnails/portfolio_posters/*.jpg`，输出 text / JSON 覆盖率。
- **无生成防护** — 新增 `tests/test_thumbnail_coverage_dry_run.py`，确认 dry-run 不调用 `ensure_poster()`、不创建 poster 目录、不触发 `ffmpeg` 或 provider。
- **文档漂移修正** — `docs/runbooks/thumbnail-missing.md` 明确 `/api/portfolio/` request path 当前是 `generate_missing=False` 只读 listing，不再描述为会自动批量补图；历史缺图修复必须显式运行 `scripts/generate_portfolio_thumbnails.py`。
- **契约固化** — 新增 `configs/thumbnail-coverage-dry-run-contract.yaml`，锁定 dry-run 检查范围、最小视频体积、禁止生成和阈值检查命令。
- **无 token 边界** — 本轮只读本地 `output/` 或 pytest 临时目录，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.58 2026-06-01 P1-46 OpenAPI generated types drift guard

- **本地 schema 生成** — 新增 `scripts/check_openapi_types_drift.py`，直接导出本地 `src.api.app.openapi()`，不再要求先启动 `localhost:8001`。
- **漂移检查默认只读** — `.venv/bin/python scripts/check_openapi_types_drift.py` 只在临时目录生成类型并比较 `web/src/types/api.generated.ts`，只有 `--write` 才改写生成文件。
- **生成器版本锁定** — `web/package.json` 新增 `check:api-types`，`typegen:api` 改为本地 guard，`openapi-typescript` 固定为 `7.13.0` 并进入 `package-lock.json`。
- **契约固化** — 新增 `configs/openapi-generated-types-drift-contract.yaml` 和 `docs/runbooks/openapi-generated-types-drift.md`，明确 no remote schema、no localhost schema、no provider calls。
- **无 token 边界** — 本轮只导入本地 FastAPI app、生成 OpenAPI schema 和 TypeScript 类型，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.59 2026-06-01 P1-47 frontend store persistence migration guard

- **持久化契约集中化** — 新增 `web/src/stores/persistence.ts`，统一 `APP_STORE_PERSIST_VERSION`、`PIPELINE_STORE_PERSIST_VERSION`、partialize、migrate 和 safe storage。
- **坏数据恢复** — `createSafeJSONStorage()` 遇到坏 JSON 会清理对应 localStorage key 并返回空状态；非法 `mode`、`pipelineMode`、`videoDuration`、`activePipeline` 会回到安全默认值。
- **运行时状态隔离** — `ai-video-app-store` 只保留用户偏好，`ai-video-pipeline-store` 只保留 active pipeline 和 dismissed labels，避免 `loading`、`workflowState`、`reviewState` 等运行时状态跨会话污染。
- **契约固化** — 新增 `configs/frontend-store-persistence-migration-contract.yaml` 和 `docs/runbooks/frontend-store-persistence-migration.md`，后续改 store 持久化字段必须同步 migration 和 focused test。
- **无 token 边界** — 本轮只运行 Vitest / TypeScript / 静态文档检查，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.60 2026-06-01 P1-48 API key storage fallback guard

- **存储边界收口** — `setApiKey()` 现在 localStorage 可用时只写 localStorage，并清理旧 cookie fallback；只有 localStorage 不可用时才写 cookie fallback。
- **清除逻辑修复** — `setApiKey("")` 或空白字符串会清除 localStorage 与 cookie fallback，不再把空白 key 持久化。
- **展示脱敏集中化** — 新增 `maskApiKeyForDisplay()`，Settings snapshot 复用该 helper，短 key 只显示 `Set`，长 key 只显示极短 prefix/suffix。
- **契约固化** — 新增 `configs/api-key-storage-fallback-contract.yaml`、`docs/runbooks/api-key-storage-fallback.md` 和 `web/src/components/apiKeyStorage.test.ts`，后续改 API key 存储、清除或展示规则先跑 focused test。
- **无 token 边界** — 本轮只操作 jsdom localStorage/cookie 和静态文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.61 2026-06-01 P1-49 Settings API key accessibility guard

- **输入语义补齐** — Settings API key 输入新增稳定 `id`、`label htmlFor`、hint `aria-describedby` 和 `autocomplete="current-password"`，避免 screen reader 只读到裸 password input。
- **状态公告补齐** — 连接测试成功使用 `role="status"` / `aria-live="polite"`，失败使用 `role="alert"` / `aria-live="assertive"`，错误结果不再只靠视觉颜色表达。
- **动作语义补齐** — Settings dialog 补 `role="dialog"` / `aria-modal` / `aria-labelledby` / `aria-describedby`，Close / Test / Reset / Save 均为显式 `type="button"`。
- **契约固化** — 新增 `configs/settings-api-key-accessibility-contract.yaml`、`docs/runbooks/settings-api-key-accessibility.md`，并扩展 `SettingsPanel.test.tsx`，后续改 Settings key 输入区先跑 focused test。
- **无 token 边界** — 本轮只运行 jsdom UI 测试、TypeScript、lint 和静态文档检查，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.62 2026-06-01 P1-50 admin logs keyboard navigation guard

- **日志行键盘入口固化** — `/admin/logs` 日志行保留 `tabIndex={0}`，新增 `role="button"` 和 `aria-label`，并用测试锁定 `Enter` / `Space` 打开详情。
- **详情弹层焦点闭环** — 详情弹层保留 `role="dialog"` / `aria-modal` / `aria-labelledby` / `aria-describedby`；打开后聚焦关闭按钮，`Escape` 关闭后焦点恢复到触发行。
- **关闭按钮语义补齐** — 详情关闭按钮新增显式 `type="button"`，避免未来表格筛选区或弹层重构时变成隐式 submit。
- **契约固化** — 新增 `configs/admin-logs-keyboard-navigation-contract.yaml`、`docs/runbooks/admin-logs-keyboard-navigation.md`，并扩展 `web/src/app/admin/logs/page.test.tsx`。
- **无 token 边界** — 本轮只使用 mocked `adminFetchJson` 和 jsdom UI 测试，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.63 2026-06-01 P1-51 AssetPicker request boundary guard

- **请求边界固化** — `AssetPickerModal` 只允许调用 `/portfolio/?limit=200&sort=recent` 获取现有媒体；测试显式禁止 `/api/upload`、`/api/assets/upload`、`/api/files/upload`、`/fast/*`、`/scenario/*`、`/pipeline/*` 和 `/gate/*`。
- **确认动作无副作用** — Confirm 只把已选 portfolio path 经 `getMediaUrl()` 映射后回传 `onPick()`，不发上传、生成、regenerate 或 gate 请求。
- **重复只读请求收口** — 移除素材列表加载 effect 对 `t` 的依赖，避免 i18n hydration 后重复拉取 portfolio listing。
- **契约固化** — 新增 `configs/asset-picker-request-boundary-contract.yaml`、`docs/runbooks/asset-picker-request-boundary.md` 和 `web/src/components/AssetPickerModal.test.tsx`。
- **无 token 边界** — 本轮只使用 mocked `apiFetch`、静态源码检查和 jsdom UI 测试，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.64 2026-06-01 P1-52 env example no-secret drift guard

- **`.env.example` 占位符守卫** — `KEY` / `TOKEN` / `SECRET` / `PASSWORD` 类变量只能为空、demo/test 值或占位符；真实 provider key 形态会使测试失败。
- **配置默认值守卫** — `src/config.py` 中敏感 env fallback 必须保持空字符串，避免把真实 key 或伪生产 key 写入代码默认值。
- **活跃部署文档守卫** — 扫描 CloudBase、local-run、Lighthouse、P2 smoke 等活跃 env 文档的敏感行，只允许占位符、变量引用或 `[redacted]`。
- **生产 secret 边界明确** — 新增 `configs/env-example-no-secret-contract.yaml` 和 `docs/runbooks/env-example-no-secret-drift.md`；测试明确不读取 gitignored 的 `deploy/lighthouse/.env.prod`。
- **无 token 边界** — 本轮只做静态文件扫描和文档治理，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.65 2026-06-01 P1-53 Lighthouse nginx timeout parity

- **长任务 timeout 守卫** — 静态检查 `deploy/lighthouse/ai_video_locations.conf` 中 `/api/scenario/`、`/api/fast/`、`/api/pipeline/` 必须保留 `proxy_read_timeout 1500s`、`proxy_send_timeout 1500s` 和 `proxy_buffering off`。
- **shared include 守卫** — 检查 canonical `video.lute-tlz-dddd.top` 与 IP fallback `101.34.52.232 _` 都 include `/etc/nginx/ai_video_locations.conf`，避免两个入口配置漂移。
- **部署文档对齐** — `docs/workflows/deploy-lighthouse-stable.md` 明确 timeout 来源是 `ai_video_locations.conf`，而不是笼统归因到 `nginx.conf`。
- **契约固化** — 新增 `configs/lighthouse-nginx-timeout-contract.yaml`、`docs/runbooks/lighthouse-nginx-timeout-parity.md` 和 `tests/test_lighthouse_nginx_timeout_contract.py`。
- **无 token 边界** — 本轮只读取本地 nginx 配置和文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.66 2026-06-01 P1-54 rsync exclude artifact guard

- **产物分类守卫** — 新增 `tests/test_lighthouse_rsync_artifact_guard.py`，按 source/env、dependencies/cache、frontend build、test reports/traces、runtime outputs/screenshots 分类检查 `deploy/lighthouse/rsync-excludes.txt`。
- **exclude 清单补齐** — 新增 `.mypy_cache`、`coverage`、`htmlcov`、`.coverage`、`web/blob-report`、`tmp/outputs`、`tmp/screenshots`、`web/tmp`、`web/tmp/screenshots` 等本地产物排除项。
- **同步入口守卫** — 测试确认本地 wrapper 和 GitHub deploy 都使用 shared exclude file，GitHub Actions 不维护 inline exclude 副本。
- **契约固化** — 新增 `configs/lighthouse-rsync-artifact-exclude-contract.yaml`、`docs/runbooks/lighthouse-rsync-artifact-exclude.md`，并纳入 docs link-check scope。
- **无 token 边界** — 本轮只读取本地脚本、配置和文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.67 2026-06-01 P1-55 script naming/location governance audit

- **脚本分类契约** — 新增 `configs/scripts-governance-contract.json`，把 `scripts/` 顶层脚本分为 `active_reusable_scripts`、`manual_deploy_scripts`、`provider_probe_scripts`、`legacy_one_off_scripts` 和 `historical_e2e_scripts`。
- **危险命名守卫** — 新增 `tests/test_scripts_governance.py`，要求所有顶层脚本必须被分类；带 `fix`、`patch`、`overwrite`、`bugfix`、`phase`、`test_`、`_v2`、`_now` 等一次性语义的脚本不得标为 `active_reusable`。
- **默认入口隔离** — 测试确认 `Makefile`、主 CI、deploy workflow、Lighthouse deploy 和无 token hermetic regression 不调用 `provider_probe_scripts`。
- **清理边界明确** — `scripts/__pycache__/**` 和 `scripts/**/*.pyc` 被标注为 `cleanup_requires_confirmation`；本轮不直接删除或迁移，避免未确认的目录治理变更。
- **无 token 边界** — 本轮只做静态文件扫描、契约和文档治理，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.68 2026-06-01 P1-56 root directory pollution guard

- **根目录允许清单** — 新增 `configs/root-directory-governance-contract.json`，把 tracked 顶层文件和目录分为 `allowed_root_files`、`allowed_root_directories` 和 `legacy_tracked_root_directories`。
- **污染模式守卫** — 新增 `tests/test_root_directory_governance.py`，禁止 tracked 根文件使用 screenshot、tmp、draft、analysis、debug、final、report、output 等临时语义或图片、视频、日志、备份后缀。
- **本地-only 忽略补齐** — `.gitignore` 显式补 `worktrees/`、`.ruff_cache/`、`coverage/`、`web/blob-report/`、`web/playwright-report/`、`web/test-results/`、`web/tmp/`，避免本地工具产物被误提交。
- **落点文档化** — 新增 `docs/runbooks/root-directory-governance.md`，明确文档进 `docs/` / `drafts/docs/`，分析进 `drafts/analysis/`，截图进 `tmp/screenshots/`，输出进 `tmp/outputs/`，历史材料进 `archive/`。
- **无 token 边界** — 本轮只读取 git 索引、`.gitignore`、配置和文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.69 2026-06-01 P1-57 Markdown frontmatter compliance scan

- **扫描范围固化** — 新增 `tests/test_markdown_frontmatter_compliance.py`，只扫描 git-tracked `docs/**/*.md` 和 `drafts/**/*.md`，不把本地未跟踪草稿纳入 CI。
- **必填字段守卫** — 新增 `configs/markdown-frontmatter-compliance-contract.json`，锁定 `title`、`doc_type`、`module`、`topic`、`status`、`created`、`updated`、`owner`、`source`。
- **历史缺口登记** — 当前 62 个历史 Markdown 缺口被精确标记为 `legacy_backfill_required`；新增 Markdown 不允许加入例外，必须直接补齐 frontmatter。
- **枚举对齐** — 3 个已完整但使用 `doc_type: runbook` 的 runbook 调整为 `doc_type: workflow`，与 AGENTS.md 文档元信息枚举一致。
- **无 token 边界** — 本轮只读取本地 Markdown、配置和文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.70 2026-06-01 P1-58 archive/draft link drift scan

- **历史链接扫描** — 新增 `tests/test_archive_draft_link_drift.py`，从 `configs/docs-link-check-scope.txt` 读取当前阻断式文档范围，扫描 Markdown links 和 frontmatter `file:`。
- **漂移契约固化** — 新增 `configs/archive-draft-link-drift-contract.json`，将 `.kiro/`、`tmp/`、`archive/`、`drafts/`、`docs/research/`、`docs/superpowers/plans|specs/` 等目标统一视为历史/临时引用。
- **当前入口防误导** — `docs/claude/updates/project-updates-202605-stable.md` 和 ADR-004 的 `.kiro` / `tmp` 链接已补“历史证据 / 不作为当前执行入口”语境。
- **历史计划链接边界** — `known-gaps` 中的 `superpowers/plans` 链接保留为历史记录；测试要求新增同类链接必须进入契约并带非当前入口提示。
- **无 token 边界** — 本轮只读取本地 Markdown、配置和文档，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.71 2026-06-01 P1-59 poyo model matrix stale warning guard

- **快照边界守卫** — 新增 `tests/test_poyo_model_matrix_stale_warning.py`，静态确认 `poyo-model-matrix-stable.md` 明确为 2026-05-31 / 2026-05 catalog snapshot，不保证代表 poyo.ai 当前最新目录、价格或审核规则。
- **充值前重验契约** — 新增 `configs/poyo-model-matrix-stale-warning-contract.json`，锁定真实 token smoke、`RUN_TOKEN_SMOKE=1`、部署默认模型切换和成本测算前必须重验 poyo.ai 当前产品页面/API 文档。
- **Runbook 固化** — 新增 `docs/runbooks/poyo-model-matrix-stale-warning.md` 并纳入 docs link-check scope，后续改矩阵、`src/pipeline/model_thresholds.py` 或 provider catalog 描述时先跑该守卫。
- **无 token 边界** — 本轮只读取本地 Markdown、JSON 配置和 CI 文件，不访问生产、不触发 `/api/fast/*`、`/scenario/*`、gate candidate、上传、发布或外部 provider。

## 0.72 2026-06-01 P1-60 release smoke token opt-in guard

- **release smoke 脚本守卫** — 新增 `tests/test_release_smoke_token_opt_in_guard.py`，静态扫描 `scripts/release_smoke_v0.4.0.sh` 中的 token-consuming curl，要求全部位于 `RUN_TOKEN_SMOKE=1` 分支内。
- **默认路径收紧** — `scripts/release_smoke_v0.4.0.sh` 不再默认向 `/api/fast/generate` 发请求；Fast Mode 真实生成 smoke 仅在充值后显式设置 `RUN_TOKEN_SMOKE=1` 时运行。
- **契约与 runbook** — 新增 `configs/release-smoke-token-opt-in-contract.json` 和 `docs/runbooks/release-smoke-token-opt-in.md`，并纳入 docs link-check scope。
- **无 token 边界** — 本轮只做本地静态扫描和脚本文本调整，不执行 release smoke、不 SSH、不 curl 生产、不触发 provider。

## 0.73 2026-06-01 P1-61 workflow trigger path audit

- **path filter 合同** — 新增 `configs/workflow-trigger-path-audit-contract.json` 和 `tests/test_workflow_trigger_path_audit.py`，锁定 path-filtered workflow 必须覆盖对应 source/spec/config/lockfile。
- **生产 E2E 触发修复** — `.github/workflows/e2e-prod.yml` 新增 `web/package-lock.json` path，避免依赖锁变化后 production E2E 不触发。
- **主 CI 边界** — 测试确认 `.github/workflows/ci.yml` 不使用 `paths` / `paths-ignore`，继续作为 broad quality gate。
- **无 token 边界** — 本轮只读取本地 YAML/JSON/Markdown，不触发 GitHub Actions、不运行 Playwright、不访问生产、不消耗 provider token。

## 0.74 2026-06-01 P1-62 Dockerfile dev-tool parity guard

- **dev-tool 合同** — 新增 `configs/docker-dev-tool-parity-contract.json` 和 `tests/test_docker_dev_tool_parity.py`，锁定 Python dev tools、前端 dev tools、Node workflow npm cache 与 lockfile 口径。
- **前端 Dockerfile fail-fast** — `web/Dockerfile` 改为精确复制 `package.json package-lock.json`，并删除 `npm install` fallback，只允许 `npm ci --ignore-scripts`。
- **runbook 固化** — 新增 `docs/runbooks/docker-dev-tool-parity.md` 并纳入 docs link-check scope，后续改测试工具、Dockerfile 或 lockfile 时先跑该守卫。
- **无 token 边界** — 本轮只做本地静态检查和 Dockerfile 文本修正，不执行 Docker build、不启动容器、不访问生产、不触发 provider。

## 0.75 2026-06-01 P1-63 Remotion no-provider-key guard

- **Remotion 合同** — 新增 `configs/remotion-no-provider-key-contract.json` 和 `tests/test_remotion_no_provider_key_guard.py`，锁定 tracked `rendering/` 文件不得引用 provider key 或 provider API host。
- **运行环境边界** — 测试确认 Remotion 只允许 `NODE_ENV`、`PORT`、`OUTPUT_DIR` 与 Chromium/Remotion 本地控制变量；Lighthouse `rendering` service 不使用 `env_file`，只接收本地渲染运行变量。
- **CI/deploy 漂移防护** — 静态扫描 `.github/workflows/ci.yml` 与 `.github/workflows/deploy.yml`，未来新增 rendering 工作目录步骤时不得注入 provider env 或 `RUN_TOKEN_SMOKE=1`。
- **runbook 固化** — 新增 `docs/runbooks/remotion-no-provider-key.md` 并纳入 docs link-check scope，后续改 rendering、compose 或 CI rendering 步骤时先跑该守卫。
- **无 token 边界** — 本轮只做本地静态检查和文档契约，不执行 Docker build、不运行 Remotion render、不启动容器、不访问生产、不触发 provider。

## 0.17 2026-05-31 P1-5 文档漂移清理

- **当前计划入口收口** — 本文件明确为当前技术债 TODO 的唯一入口；后续继续执行时从“完整 TODO list”读取下一项，避免多个历史路线图并行竞争。
- **历史路线图标注** — `2026-05-14-poyo-constrained-optimization-roadmap.md`、`five-scenario-pipeline-risk-assessment-stable-20260513.md`、`2026-05-15-sprint-0-3-review-and-deploy-plan.md`、`2026-05-23-video-speed-optimization-deploy-plan.md` 已标注为历史快照或专项计划，不再作为当前待办来源。
- **架构与类型计划去漂移** — `multi-agent-video-system-design.md` 标注为早期产品/架构蓝图；`pyright-strict-technical-debt-plan-20260507-stable.md` 标注为类型治理历史计划，当前类型边界收口状态以本文件 P1-4 和 `pyproject.toml` 为准。
- **模型矩阵风险提示** — `poyo-model-matrix-stable.md` 明确为 2026-05 快照；真实消耗 POYO token 前需要重新核对 poyo.ai 当前模型目录和价格，不再把旧快照当“最新产品形态”。
- **边界** — 本轮不归档、不删除、不移动旧文档；只补历史语境和当前入口，避免破坏已有链接。

> 更早盘点：2026-05-31 — P1-4 类型边界热区收口。

## 0.16 2026-05-31 P1-4 类型边界热区收口

- **运行时契约集中化** — 新增 `src/models/runtime_contracts.py`，用轻量 `TypedDict` 固化跨模块 shape；不引入 Pydantic runtime validation，不改变现有 API JSON。
- **Fast Mode result 边界** — `FastModeService.generate()` 返回类型改为 `FastModeResult`，`model_info` / `timing` 也有显式结构；移除 `video_result` 上的 `union-attr` ignore，并对非 dict 视频结果显式失败。
- **Seedance result 边界** — `SeedanceClient.text_to_video()` / `image_to_video()` / `_stub_result()` 等返回 `SeedanceVideoResult`，避免调用方继续猜测 `local_path`、`video_url`、`_stub_mode` 字段是否存在。
- **Telemetry response 边界** — `PipelineMetrics.get_summary()`、`ErrorCollector.get_errors()`、`/telemetry/metrics`、`/telemetry/errors` 接入 `TelemetrySummary` / `TelemetryErrorsResponse`；同时修复无 running loop 时错误持久化调度产生的 unawaited coroutine warning。
- **Continuity audit 边界** — `build_continuity_audit_summary()` 返回 `ContinuityAuditSummary`，`build_transitions_from_clip_details()` 返回 `TransitionMetadata`；旧版只有 `micro_shots`、没有 `clip_groups` 的 grid 不再因缺 director metadata 被误降分。
- **防回归测试** — 新增 `tests/test_runtime_contracts.py`，锁定关键函数返回注解、Seedance stub shape、telemetry route annotation，以及 Fast Mode 不再依赖 `union-attr` ignore。
- **验证闭环** — 目标 `ruff` 通过；`pytest tests/test_runtime_contracts.py tests/test_continuity_utils.py tests/test_fast_mode_async.py tests/test_pipeline_degradation_chain.py tests/test_fault_injection.py -q` 通过，结果 `55 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P1-3 S2 deprecated wrapper 去留决策。

## 0.15 2026-05-31 P1-3 S2 deprecated wrapper 去留决策

- **决策：保留但冻结** — `src/pipeline/s2_brand_pipeline.py` 继续作为 backwards-compat shim，只 re-export `S2BrandCampaignPipeline` 并发出 `DeprecationWarning`；不得在旧文件继续添加 pipeline 行为。
- **生产调用面已迁移** — `/scenario/s2` 的生产路由直接导入 `src.pipeline.s2_brand_pipeline_v2`，不经过旧 shim；旧路径仅服务外部脚本、notebook 或历史调用。
- **删除条件明确** — 删除不是本轮默认动作；需要先确认外部调用迁移窗口，且按项目规则单独取得删除确认后再执行。
- **防回归测试** — 新增 `tests/test_s2_deprecated_shim_boundary.py`，锁定生产路由直连 v2、旧 shim warning-only alias、canonical import path 与 removal policy。
- **文档引用去漂移** — 已更新当前路线图与历史计划引用，把“直接删除 wrapper”改为“冻结兼容 shim，删除需迁移窗口 + 单独确认”。
- **验证闭环** — `ruff check src/pipeline/s2_brand_pipeline.py tests/test_s2_deprecated_shim_boundary.py tests/test_s2_e2e.py` 通过；`pytest tests/test_s2_deprecated_shim_boundary.py tests/test_s2_e2e.py -q` 通过，结果 `19 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P1-2 LangGraph proxy 契约收口。

## 0.14 2026-05-31 P1-2 LangGraph proxy 契约收口

- **字段契约显式化** — `src/routers/pipeline.py` 新增 `LEGACY_PROXY_STEP_OUTPUT_MAP` 与 `LEGACY_PROXY_REQUIRED_STATE_FIELDS`，把 StepRunner → legacy `/pipeline/*` 的字段映射从函数内部隐式逻辑提升为可测试契约。
- **兼容 shape 已测试** — 新增 `tests/test_pipeline_proxy_contract.py`，覆盖完整 StepRunner state、半完成 state、not_found state；锁定 `distribution_plans` 默认空列表、`human_reviews` 空 dict、`pipeline_complete` 推导和 legacy step output 字段。
- **review 行为继续冻结为 no-op** — 现有 `tests/test_human_review_deprecated.py` 继续锁定 `/pipeline/{thread_id}/review/{review_node}` 返回 `idempotent_skip`，真实审批入口仍是 `/scenario/{s}/gate/{label}/{gate_id}/approve`。
- **API reference 去漂移** — `docs/reference/api-endpoints.md` 已修正：`/pipeline/start` 返回 synthetic UUID + StepRunner label，review 不再描述 resume/reject，state 字段列出 pinned compatibility fields。
- **验证闭环** — `ruff check src/routers/pipeline.py tests/test_pipeline_proxy_contract.py tests/test_human_review_deprecated.py` 通过；`pytest tests/test_pipeline_proxy_contract.py tests/test_human_review_deprecated.py -q` 通过，结果 `7 passed`。

> 更早盘点：2026-05-31 — P1-1 api_assets.py legacy shim 边界收口。

## 0.13 2026-05-31 P1-1 api_assets.py legacy shim 边界收口

- **兼容面冻结** — `src/api_assets.py` 明确标注为 `/api/assets/*` legacy compatibility surface；brand package / influencer CRUD 保留给现有前端 OpenAPI types 和 library tab，不再承接新业务域。
- **现代 assets 边界明确** — 新上传、文件列表、portfolio、运行时媒体能力继续归 `src/routers/assets.py`、`src/routers/portfolio.py`、`src/routers/media.py`，避免 `/api/assets/*` 与 `/api/upload` / `/api/files` 继续混淆。
- **防回归测试** — 新增 `tests/test_api_assets_legacy_boundary.py`，断言 `api_assets.router.prefix == "/api/assets"`、legacy brand/influencer/remix 路由仍存在，并断言现代 assets router 不抢占 `/api/assets` 前缀。
- **PG cutover 状态修正** — `docs/architecture/api-assets-pg-cutover-2026-05-15.md` 已更新为 stable boundary：`BRAND_PACKAGE_USE_PG=1` adapter 已存在，但生产 PG `id` 仍是 UUID，`BPKG-*` 业务 ID 持久化仍需 staging/restart smoke 验收。
- **验证闭环** — `ruff check src/api_assets.py tests/test_api_assets_legacy_boundary.py tests/test_asset_stores_cutover.py` 通过；`pytest tests/test_api_assets_legacy_boundary.py tests/test_asset_stores_cutover.py -q` 通过，结果 `24 passed`。

> 更早盘点：2026-05-31 — P0-4 前端运行时媒体图片策略。

## 0.12 2026-05-31 P0-4 前端运行时媒体图片策略

- **运行时媒体统一入口** — 新增 `RuntimeMediaImage`，集中承载后端 portfolio、用户上传、缩略图、素材预览等运行时 URL；业务组件不再直接散落原生 `<img>`。
- **静态资产不走运行时入口** — `BrandKitTab` 的 `/brand/momcozy-logo.svg` 改用 `next/image`，避免把可静态优化的 public 资产误归入运行时媒体策略。
- **策略边界** — `RuntimeMediaImage` 内部保留唯一 `@next/next/no-img-element` 例外说明；该组件只用于后端/用户资产 URL，不用于静态 public 图片或已知可 allowlist 的 CDN 图片。
- **验证闭环** — `npm exec eslint src` 无 warning；`npm exec tsc -- --noEmit` 通过；`npm test -- --run src/app/__tests__/page-smoke.test.ts --testTimeout=15000` 通过，结果 `16 passed`；`DirectorPlayback` / `QualityDashboard` / `CompareView` 目标测试通过，结果 `6 passed`。

> 更早盘点：2026-05-31 — P0-3 前端真实 warning 清理。

## 0.11 2026-05-31 P0-3 前端真实 warning 清理

- **admin hook dependency 已收口** — `admin/logs`、`admin/tenants`、`admin/tenants/[tenantId]` 的 load 函数改为 `useCallback`，effect 依赖不再捕获 stale closure。
- **筛选语义保持明确** — logs/tenants 页将输入态与已应用筛选态分离，避免为了修 hook warning 变成输入即请求；Search / Apply 仍是显式触发查询入口。
- **unused warning 已清理** — 删除未使用的 `Link`、`newKeyId`、`detailLoading`、`TAB_IDS`、`VideoListView` 内未使用 `t`，移除过期 `no-console` disable；page smoke mock 的 `isApiError` 不再声明未使用参数。
- **验证闭环** — `npm exec tsc -- --noEmit` 通过；`npm test -- --run src/app/__tests__/page-smoke.test.ts --testTimeout=15000` 通过，结果 `16 passed`；`npm exec eslint src` 仅剩 11 个 `@next/next/no-img-element` warning，全部属于 P0-4。

> 更早盘点：2026-05-31 — P0-2 FastAPI lifespan shutdown 集成测试。

## 0.10 2026-05-31 P0-2 FastAPI lifespan shutdown 集成测试

- **新增真实 lifespan 测试** — `tests/test_bg_registry.py` 通过 monkeypatch `src.api._run_startup()` 注入一个无外部依赖的长任务，再使用 `TestClient(api.app)` 触发真实 FastAPI lifespan enter/exit。
- **验证 shutdown 行为** — context 退出后测试断言长任务收到 cancellation，并且 `get_background_task_snapshot()` 返回空 dict，覆盖 `src.api._lifespan()` → `cancel_background_tasks()` 的真实调用链。
- **边界** — fake startup 只替换启动副作用，不替换 lifespan cleanup；不会触发 DB、admin loop、外部 API 或 POYO token。
- **验证闭环** — `ruff check tests/test_bg_registry.py` 通过；`pytest tests/test_bg_registry.py -q` 结果 `3 passed`；`ruff check src tests --statistics` 通过；S1-S5 无 token hermetic 回归集合通过，结果 `138 passed, 12 deselected`。

> 更早盘点：2026-05-31 — P0 本地质量门第一批执行结果。

## 0.9 2026-05-31 P0 本地质量门第一批执行结果

- **repo-wide ruff 已恢复可用** — `ruff check tests --fix` 清理历史测试文件中的 import 顺序、未使用 import、无占位符 f-string、`datetime.UTC` 迁移等机械噪音；剩余 `tests/test_api.py` 顶层未使用 `httpx` import 改为 `importlib.util.find_spec("httpx")` 可用性检测。
- **质量门结果** — `ruff check tests --statistics` 通过；`ruff check src tests --statistics` 通过。后续可以把 `ruff check src tests` 重新作为本地质量门使用。
- **目标测试结果** — `pytest tests/test_api.py tests/test_bg_registry.py -q` 通过，结果 `9 passed`；S1-S5 无 token hermetic 回归集合通过，结果 `137 passed, 12 deselected`。
- **边界** — 本轮只做 ruff 可自动修复和一个 import 检测手工修复，不改变 API 语义、不触发外部服务、不消费 POYO token。

### 完整 TODO list

- [x] **P0-1：恢复 Python repo-wide lint 可信度** — 清理 `src tests` ruff 噪音，使 `ruff check src tests` 重新可作为质量门。
- [x] **P0-2：补 FastAPI lifespan shutdown 集成测试** — 构造无外部依赖的注册任务，验证 app 退出时 registry 会取消、等待并清理后台任务。
- [x] **P0-3：清理前端真实 hook warning** — 优先处理 admin 页 `react-hooks/exhaustive-deps`、未使用变量；保留 `<img>` 策略 warning 到单独决策。
- [x] **P0-4：建立前端运行时媒体图片策略** — 明确后端运行时 URL 哪些必须原生 `<img>`，哪些可迁移 `next/image`，避免一边 suppress 一边新增债务。
- [x] **P1-1：收口 `api_assets.py` legacy shim 边界** — 明确 `/api/assets/*` in-memory shim 的冻结规则、迁移条件和删除前置测试。
- [x] **P1-2：收口 LangGraph proxy 契约** — 明确 `/pipeline/*` best-effort state 转换字段，补最小兼容测试，避免 legacy 字段缺失隐性回归。
- [x] **P1-3：确认 S2 deprecated wrapper 去留** — 检索调用面与文档引用，已冻结为 warning-only alias；删除前需要外部迁移窗口与单独确认。
- [x] **P1-4：类型边界热区收口** — 已补运行时 `TypedDict` 契约，覆盖 `fast_mode` result、telemetry endpoint、continuity audit、Seedance result，不做全仓 `Any` 大重构。
- [x] **P1-5：文档漂移清理** — 已将当前执行入口固定到本文件，历史探索/路线图/部署计划文档已标注历史语境，不再作为当前计划来源。
- [x] **P1-6：全站 UI/UX 无 token 审计与首轮修复** — 完成 5 loop 审计，修复路由白屏 fallback、Home 顶栏移动端挤压和关键弹层可访问性。
- [x] **P1-7：前端布局与弹层单一化** — Home header 已复用 `TopHeader`，`QuickTemplate` 与 `AssetLibrary` 旧弹层键盘/焦点行为已收口。
- [x] **P1-8：UI-only Playwright 视觉回归** — 已补桌面/移动端截图基线、QuickTemplate 交互 smoke 和 token-consuming request 硬拦截。
- [x] **P1-9：UI-only 视觉回归 CI 接入** — 已新增 macOS Chromium workflow，避免无余额阶段的前端布局回归只能靠本地手动跑。
- [x] **P1-10：UI-only 无 token 护栏测试** — 已新增 Vitest 静态检查，防止 `e2e:ui` 配置、请求拦截或 CI workflow 漂移到真实生成路径。
- [x] **P1-11：前端 CI 硬门禁对齐** — 已移除 TypeScript 软失败，并把 eslint、TypeScript、Vitest、Next build 收口到主前端 CI。
- [x] **P1-12：production E2E token smoke 隔离** — 已让 `e2e:prod` 默认跳过 `@token-smoke`，真实任务创建和 gate candidate 生成只能显式 opt-in。
- [x] **P1-13：production deploy preflight 对齐** — 已让 GitHub deploy preflight 跑完整前端质量门，并显式保持远程部署 `RUN_TOKEN_SMOKE=0`。
- [x] **P1-14：deploy pytest timeout 依赖闭环** — 已为 deploy preflight 的 `pytest --timeout=60` 补齐 `pytest-timeout` 依赖、lockfile 和静态防回归测试。
- [x] **P1-15：CI Python lint parity** — 已将主 CI / deploy preflight 的 ruff 口径统一到 `src tests`，避免测试代码重新积累 lint 债。
- [x] **P1-16：CI hermetic env guard** — 已固化 CI 中外部 provider key 的空值或测试值，避免 GitHub runner 继承真实生成凭证。
- [x] **P1-17：Python dev dependency parity** — 已建立 `pyproject.toml`、`requirements.txt`、`uv.lock` 的测试工具依赖一致性检查。
- [x] **P1-18：README package-manager drift cleanup** — 已修正 README 中 `pnpm` 与当前 `package-lock.json` / GitHub Actions `npm` 的漂移。
- [x] **P1-19：e2e-prod secret/runbook coverage** — 已补 `PROD_DEMO_API_KEY`、`run_token_smoke` 和 `@token-smoke` 的 GitHub Actions runbook。
- [x] **P1-20：production Playwright no-mutation scan** — 已增强静态扫描，默认 prod E2E 不允许新增未标记的高风险 mutating endpoint 请求。
- [x] **P1-21：deploy rsync exclude parity** — 已对齐 GitHub deploy rsync excludes 与 Lighthouse `rsync-excludes.txt`，减少部署上下文漂移。
- [x] **P1-22：smoke script token guard tests** — 已为 `deploy/lighthouse/deploy.sh` 和 `smoke.sh` 增加静态测试，锁定所有生成接口必须受 `RUN_TOKEN_SMOKE=1` 保护。
- [x] **P1-23：S1-S5 hermetic regression command** — 已固化无 token 的 S1-S5 hermetic 回归命令和文档入口。
- [x] **P1-24：POYO diagnostic script gating** — 已审计已跟踪的 `scripts/*poyo*`、`probe_*`，确保直连 POYO 的脚本有显式 key/用途提示，且不被 CI 默认调用。
- [x] **P1-25：UI visual baseline SOP** — 已补 UI-only 截图基线更新 SOP，避免随手更新 snapshot 掩盖真实布局回归。
- [x] **P1-26：Runtime media image guard 扩展** — 已扩大前端静态测试，防止运行时媒体又绕过 `RuntimeMediaImage`。
- [x] **P1-27：admin 页面可访问性 smoke** — 已为 admin 关键页面补无后端依赖的可访问性/渲染 smoke。
- [x] **P1-28：i18n translation completeness guard** — 已补翻译 key 完整性检查，减少 EN/ZH 页面复制漂移。
- [x] **P1-29：apiFetch error normalization tests** — 已覆盖 401/422/429 的前端错误呈现，避免异常路径 silent failure。
- [x] **P1-30：env config SSOT drift guard** — 已锁定 `DEFAULT_LLM_PROVIDER`、POYO/DeepSeek 配置默认值与文档一致性。
- [x] **P1-31：docs link-check scope hardening** — 已收紧 docs link check 的离线范围和允许失败边界，避免文档链接债继续隐藏。
- [x] **P1-32：Docker build no-token preflight** — 已为 Docker build / compose 校验补不触发外部 provider 的验证说明和静态测试。
- [x] **P1-33：P2 recharge smoke checklist dry-run** — 已在充值前完成 P2 真 smoke checklist 的 dry-run 脚本和操作清单，充值后填 key 并双确认执行。
- [x] **P1-34：backend route auth contract scan** — 已静态检查需要鉴权和无需鉴权的 FastAPI router 边界，避免新增敏感路由漏挂 `verify_api_key`。
- [x] **P1-35：API response metadata guard** — 已锁定 JSON response `_meta`、`X-Trace-Id` 和错误响应 shape，防止前端错误追踪失效。
- [x] **P1-36：rate-limit config/test parity** — 已静态和单测确认 `/health` skip、业务路由限流、429 响应呈现保持一致。
- [x] **P1-37：health endpoint no-secret guard** — 已确认 `/health` 只暴露能力状态，不泄露 provider key、数据库 URL 或内部路径。
- [x] **P1-38：admin CSRF doc/test parity** — 已对齐 admin CSRF 测试、runbook 和前端调用约定。
- [x] **P1-39：background task registry leak guard** — 已扩展 snapshot 测试，确认失败任务、取消任务和完成任务都不会长期残留。
- [x] **P1-40：scenario state persistence schema guard** — 已为 S1-S5 state JSON 关键字段增加 hermetic schema 断言，并补齐 filesystem 初始字段默认值。
- [x] **P1-41：gate approve idempotency guard** — 已用无 token 测试确认相同选择重复 approve 不重复恢复、不破坏状态，不同选择保持 conflict。
- [x] **P1-42：regenerate downstream invalidation guard** — 已锁定 step regenerate 后下游步骤和当前/下游 gate 状态的失效规则。
- [x] **P1-43：S4 footage asset filtering regression** — 已为 S4 `live_shoot` 在 `/works` / `/library` 的筛选逻辑补前后端无 token 回归证据。
- [x] **P1-44：media URL sanitizer guard** — 已锁定 portfolio、thumbnail、upload preview 的媒体 URL 不接受绝对 URL、危险 scheme 或 traversal 输入。
- [x] **P1-45：thumbnail coverage dry-run** — 已新增只读覆盖率脚本和契约，检查作品集缩略图覆盖率时不重新生成媒体。
- [x] **P1-46：OpenAPI generated types drift guard** — 已建立本地 schema → `api.generated.ts` 的漂移检查和显式写入流程，不访问生产或 localhost schema。
- [x] **P1-47：frontend store persistence migration guard** — 已覆盖 Zustand/localStorage 版本迁移、坏 JSON 清理、非法 payload 恢复和运行时状态隔离。
- [x] **P1-48：API key storage fallback guard** — 已覆盖 localStorage primary、cookie fallback、masking 和清除逻辑，不暴露完整 key。
- [x] **P1-49：Settings API key accessibility guard** — 已为 Settings key 输入、保存、连接测试成功/失败状态补可访问性和回归测试。
- [x] **P1-50：admin logs keyboard navigation guard** — 已锁定 Admin Logs 行键盘打开、详情弹层关闭和焦点恢复行为。
- [x] **P1-51：AssetPicker request boundary guard** — 已确认素材选择器只调用只读 portfolio listing，不触发上传或生成。
- [x] **P1-52：env example no-secret drift guard** — 已检查 `.env.example`、deploy env 文档和配置默认值不包含真实 secret。
- [x] **P1-53：Lighthouse nginx timeout parity** — 已静态检查 nginx 长任务 timeout 与部署文档一致。
- [x] **P1-54：rsync exclude artifact guard** — 已防止 `.next`、报告、截图、tmp 输出等本地产物进入远程部署同步。
- [x] **P1-55：script naming/location governance audit** — 已固化 `scripts/` 分类契约、provider probe 默认入口隔离和 generated artifact 清理确认边界。
- [x] **P1-56：root directory pollution guard** — 已建立根目录允许清单、临时/截图/报告类 tracked 根文件守卫和本地-only 忽略契约。
- [x] **P1-57：Markdown frontmatter compliance scan** — 已固化 tracked `docs/**/*.md` / `drafts/**/*.md` 元信息扫描、legacy backfill 清单和 doc_type 枚举守卫。
- [x] **P1-58：archive/draft link drift scan** — 已固化当前文档范围内历史/临时链接 allowlist、非当前入口语境检查和新增漂移守卫。
- [x] **P1-59：poyo model matrix stale warning guard** — 已锁定 poyo 模型矩阵必须标注快照时间和充值前重验提示。
- [x] **P1-60：release smoke token opt-in guard** — 已审计 release smoke 脚本，确认生成接口不会默认执行。
- [x] **P1-61：workflow trigger path audit** — 已检查 GitHub Actions path filters 是否覆盖对应测试/配置文件。
- [x] **P1-62：Dockerfile dev-tool parity guard** — 已确认 Docker/CI 需要的测试工具和 lockfile 一致。
- [x] **P1-63：Remotion no-provider-key guard** — 已确认 rendering build/test 不读取 provider API key，并固化静态守卫。
- [x] **P1-64：C2PA runbook dry-run checklist** — 在不申请真实证书的前提下固化 C2PA 后续执行清单。
- [x] **P1-65：50-loop checkpoint review** — 已对 P1-16~P1-64 执行结果复核并完成排序：当前未形成新增 P1 阻塞，执行入口切至 `P2-1`（充值后受控 live smoke/交付链路）。
- [x] **P2-1：真实 provider + 前后端联动 E2E 执行** — 已完成分层闭环：`L4A` Momcozy 3 图 + 1 视频受控 provider smoke 通过；`L4B` `/library` 生产只读回读通过；`L4C` Fast Mode single-submit pending_review、S1-S5 no-media clean-log single-submit 均完成；`L4D` image-only、video-only、image+video paired、S2 bounded media provider smoke 与 frontend read-only readback 均完成。剩余的 S1/S3/S4/S5 media generation、S2 full media/final assembly、gate approve/regenerate、poster/quality、publish 和 delivery acceptance 必须另立阶段并重新授权。
- [x] **P2-2：POYO 内容审核样本回灌** — 将真实失败 prompt / response 分类写入 hermetic fixture 或 sanitizer 规则，避免只靠生产人工观察。
- [x] **P2-3：生产部署后回归证据固化** — 已新增 `production-post-deploy-regression-checklist.md`，覆盖 Lighthouse 健康检查、页面/API smoke、容器与日志核验、回归证据模板。

> 更早盘点：2026-05-31 — 遗留技术债深度汇总与执行计划。

## 0.8 2026-05-31 遗留技术债深度汇总与执行计划

### 证据基线

- **后端局部质量门已通过** — `ruff check src/tasks/bg_registry.py tests/test_bg_registry.py` 通过；`tests/test_bg_registry.py` 通过；S1-S5 无 token hermetic 回归集合通过，结果 `137 passed, 12 deselected`。
- **后端全量 lint 仍不可作为 CI 门禁** — `ruff check src tests` 当前仍有 `176 errors`，其中 `174` 项可自动修复，主要集中在历史测试文件的 import 顺序、未使用 import、无占位符 f-string、`datetime.UTC` 迁移和少量疑似 stale import。
- **前端无 error 但仍有 warning 债** — `npm exec eslint src --quiet` 无 error；完整 `npm exec eslint src` 仍有 `21 warnings`，主要是 admin 页 hook dependency、未使用变量，以及运行时媒体 `<img>` 策略未统一。
- **工作区变更量大** — 当前存在大量 modified / untracked 文件。继续推进前必须按主题分批验证和提交，避免把已完成修复、文档计划、历史探索和后续实验混成一个不可回滚变更包。
- **真实生产验证当时受 POYO 余额约束** — 2026-05-31 当时只做 hermetic / mock / unit / lint / 类型收口；2026-06-11 已完成 Momcozy 样本的 `L4A` 受控 provider smoke 与 `L4B` 生产只读回读，S2-S5、gate 真 API key 路径和质量评分生产闭环仍需按 `L4C` 另行授权。

### 债务分层

- **P0：本地质量门债务** — repo-wide Python lint 失败会让 CI 口径失真；必须先把 `tests/` 中可自动修复的 ruff 噪音分批清掉，再处理少量真实 stale import 或路径漂移。
- **P0：前端 hook warning 债务** — admin 页 `react-hooks/exhaustive-deps` warning 属于真实 stale closure 风险，不应和 `<img>` 性能策略 warning 混放处理。
- **P0：生命周期验证债务** — registry 现在有 shutdown cleanup 和公开 snapshot helper，但还缺一个更接近 FastAPI lifespan 的集成测试，验证 app 退出时真实注册任务会被取消并清理。
- **P1：兼容层边界债务** — `src/api_assets.py` 仍是 `/api/assets/*` legacy in-memory shim；`/pipeline/*` LangGraph proxy 仍是 best-effort state 转换；S2 deprecated wrapper 清理仍需先确认调用面和文档。
- **P1：类型边界债务** — 后端仍大量使用 `dict[str, Any]`，但不适合全仓一次性重写；应优先收口 `fast_mode` result、telemetry endpoint、continuity diagnostics、Seedance clip detail 这些跨模块热输出。
- **P1：文档漂移债务** — 2026-05-31 已完成首轮收口：当前执行入口固定为本文件；高风险旧路线图、风险评估、部署计划和早期架构设计已补历史语境。
- **P2：生产验证债务** — S2-S5 真实 API key gate、POYO 内容审核、thumbnail/quality/media 工具链和部署后 smoke 都不能在无余额阶段闭环，只能先准备 checklist 与 mock 证据。

### 执行计划

1. **先稳定质量门** — 以 `tests/` 为第一批，运行 ruff auto-fix 能覆盖的 import/order/f-string/datetime 规则；每批只处理一个规则族，避免把行为变更混入格式修复。
2. **再清前端真实 warning** — 优先修 admin 页 hook dependency 和未使用变量；`<img>` warning 单独建立运行时媒体策略，确认哪些必须保留原生 `<img>`，哪些可迁移 `next/image`。
3. **补生命周期集成测试** — 在不触发外部服务的前提下构造注册任务，覆盖 lifespan shutdown 对 registry 的取消、等待和清理语义。
4. **收口热路径类型边界** — 只处理跨前后端或跨 pipeline 的输出结构，避免在低 ROI 的内部 `dict[str, Any]` 上做大规模重构。
5. **整理兼容层决策** — 为 `api_assets.py`、LangGraph proxy、S2 wrapper 分别给出保留、冻结、迁移或删除条件；删除或批量移动前单独确认。
6. **文档去漂移** — 将仍有效的 TODO 汇入 stable 文档；把只描述历史探索的内容标注为历史背景，不再作为执行计划来源。
7. **按 L4C 授权扩展生产 smoke** — 若继续覆盖 S1-S5、Fast Mode、gate approve/regenerate、media/poster/quality、admin/library 关键路径，需先重新确认预算、范围、重试策略和产物处置边界，并把失败样本回灌到 hermetic 测试。

## 0.7 2026-05-31 bg_registry 测试封装收口

- **新增公开只读 snapshot helper** — `src/tasks/bg_registry.py` 新增 `get_background_task_snapshot()`，只返回 `label`、`started_at`、`done`、`cancelled` 等测试和诊断需要的元数据，不暴露内部 task registry dict 本体。
- **测试不再读取私有 dict** — `tests/test_bg_registry.py` 已改为通过 snapshot 断言注册、完成和取消状态；fixture 通过 `cancel_background_tasks(timeout=1.0)` 做前后清理，减少测试间残留。
- **边界** — `_background_tasks` 仍保留为模块内部实现细节；业务调用仍通过 `register_background_task()` 和兼容 re-export，不改变 runtime 行为。
- **验证闭环** — 已通过 `ruff check src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`，以及完整无 token hermetic 集合 `137 passed, 12 deselected`。

> 更早盘点：2026-05-31 — background task registry 单一化。

## 0.6 2026-05-31 background task registry 单一化

- **删除失活重复定义** — `src/routers/_state.py` 中旧 `_background_tasks` dict 已删除；该变量自 registry 迁移后没有真实引用，继续保留会误导维护者以为存在两个任务注册源。
- **保留兼容 re-export** — `_state.py` 继续 re-export `_register_background_task`，现有 `scenario.py` / `pipeline.py` 调用路径不变。
- **验证闭环** — 已通过 `ruff check src/routers/_state.py src/routers/scenario.py src/routers/pipeline.py src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`、`tests/test_scenario_step_regenerate_router.py`，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-31 — background task shutdown cleanup。

## 0.5 2026-05-31 background task shutdown cleanup

- **registry 增加集中 shutdown helper** — `src/tasks/bg_registry.py` 新增 `cancel_background_tasks(timeout=5.0)`，会取消 registry 内未完成任务、等待有限时间，并清理已完成/已取消记录。
- **lifespan 退出时调用 cleanup** — `src/api.py` 的 lifespan 在 `finally` 中调用 `cancel_background_tasks()`；启动逻辑不变，只补退出路径。
- **边界** — 本轮不改变请求期间 background task 注册、完成 callback、失败日志和业务任务执行语义；只处理 app shutdown 时原本缺失的集中清理。
- **验证闭环** — 已通过 `ruff check src/api.py src/tasks/bg_registry.py tests/test_bg_registry.py`、`tests/test_bg_registry.py`、`tests/test_scenario_step_regenerate_router.py`、`no_on_event_deprecation` import 检查，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-30 — FastAPI lifespan 迁移。

## 0.4 2026-05-30 FastAPI lifespan 迁移

- **`on_event` deprecation warning 已关闭** — `src/api.py` 将原 `@app.on_event("startup")` 启动逻辑迁移为 `FastAPI(lifespan=...)`，启动内容保持原样：DB 初始化、thread index restore、cache eviction、生产 API key 检查、portfolio hook、admin background tasks。
- **shutdown cleanup 后续已补** — 初始迁移不顺手改后台任务取消逻辑；2026-05-31 已在 background task registry 增加集中 shutdown cleanup。
- **验证闭环** — 已通过 `ruff check src/api.py`、`tests/test_scenario_step_regenerate_router.py`、`no_on_event_deprecation` import 检查，以及完整无 token hermetic 集合 `135 passed, 12 deselected`。

> 更早盘点：2026-05-30 — S1-S5 前端降级提示口径收口。

## 0.3 2026-05-30 soft degraded 展示口径收口

- **reason 不再直出内部码值** — `getSoftDegradedReasonLabel()` 改为 reason 白名单映射；未知 reason 统一显示 `degraded.reason.unknown`，不再把 `internal_backend_code` 这类字符串替换下划线后展示给用户。
- **detail 不再直出后端 `_degraded_detail`** — `getSoftDegradedSummary()` 改为按 reason 读取 `degraded.detail.*` 翻译；未知 reason 或未配置 detail 时不展示 detail，避免 fallback_reason、异常文本、内部字段名泄漏到 UI。
- **三条热路径自动复用** — `StageProgress`、`StepByStepView`、`VideoWorkflow` 都已通过共享 `softDegraded` helper 继承新口径，无需分别维护展示逻辑。
- **验证闭环** — 已通过 `vitest src/lib/softDegraded.test.ts`、目标 `eslint` 与 `tsc --noEmit`。

> 更早盘点：2026-05-28 — S1-S5 前端工作流技术债本地收口，目标 lint、`tsc --noEmit` 和目标 Vitest 验证通过。

## 0.2 2026-05-29 前端热路径 lint 收口

- **Fast Mode 面板** — `FastModePanel` 移除未使用的 `getMediaUrl` import，避免 lint 噪音掩盖真实改动。
- **S1-S5 Expert 表单** — `SceneForm` 删除未使用的 `SCENE_ICON_MAP`，保留实际渲染仍在使用的平台 icon map 和场景标题 icon。
- **首页场景入口** — `SceneSelector` recent works 缩略图保留原生 `<img>`，并补精确 `@next/next/no-img-element` 例外说明；这些缩略图来自后端运行时媒体路径，不引入 Next image allowlist 配置债。
- **验证闭环** — 已通过 `eslint src/components/FastModePanel.tsx src/components/SceneForm.tsx src/components/SceneSelector.tsx` 与 `tsc --noEmit`。
- **后端 hermetic 回归** — 已通过 `tests/test_scenario_step_regenerate_router.py`、`tests/test_gate_scenario_configs.py`、`tests/test_continuity_storyboard_grid.py`、`tests/test_candidate_scorer_continuity.py`、`tests/test_s1_continuity_pipeline.py`、`tests/test_s3_e2e.py`、`tests/test_s4_e2e.py`、`tests/test_s5_e2e.py`，结果 `135 passed, 12 deselected`；FastAPI `on_event` deprecation warning 已在 2026-05-30 lifespan 迁移中关闭。

> 更早盘点：2026-05-22 — S1 连续分镜能力向 S2-S5 抽象迁移完成，13 个 POYO 模型 ID 修正，Kling/Wan/Hailuo 参数适配。历史记录详见 [`docs/superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md`](../../superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md)，不作为当前执行入口。

## 0.1 2026-05-28 本地技术债收口

下列项已完成本地验证，作为 S1-S5 工作流继续实测前的稳定性基线：

- **GuidedForm 连续性参数传递** — `buildGuidedScenarioConfig()` 抽出 S1-S5 共享配置合成逻辑，`continuity_required`、`reference_image_url`、`source_video_url`、`character_reference_url` 不再只停留在前端表单态；目标单测覆盖 S1-S5 配置输出。
- **Smart Create 场景路由与连续性透传** — `buildSmartCreatePayload()` 和 `getScenarioPagePath()` 收口前端 payload 与跳转映射，`live_shoot_to_video` 明确路由到 `/s4`，避免 S4 误落回 S1 默认链路。
- **结果/分发/作品/审核展示类型债** — `api.ts`、`OneShotResultView`、`DistributionView`、`PublishPanel`、`works/page.tsx`、`ReviewPanel` 已移除本轮目标显式 `any`，用局部宽类型、类型守卫和边界归一化替代直接结构假设。
- **Step-by-step 与工作流编排类型债** — `AssetCard`、`types.ts`、`StepByStepView`、`VideoWorkflow` 已完成目标 lint；`VideoWorkflow` 保留 backend-runtime thumbnail 原生 `<img>`，并用精确 lint 例外说明原因，避免 Next image allowlist 与运行时媒体路径耦合。
- **验证闭环** — 已通过目标 `eslint`、`tsc --noEmit`、`guidedScenarioConfig` / `scenarioContinuity` / `scenarioRouting` Vitest；真实 POYO 余额相关端到端仍保留为后续人工实测项。

> 更早盘点：2026-05-11 (v0.2.4) — Tier-2/Tier-3/HU-05/Brand Assets Phase 1-4 全部上线。

## 0. 2026-05-11 / v0.2.4 关闭项总览

下列项已在 v0.2.0 → v0.2.4 区间被实际修复并上线生产，从未闭项中移除：

- **配置漂移 `DEFAULT_LLM_PROVIDER`** — `4bf096b` (v0.2.1) — `src/config.py:115` 标注为
  SSOT，4 个镜像文件（render.yaml / .env.prod / 2 篇 deploy 文档）全部对齐 `deepseek`。
- **Redis/Celery legacy** — `4bf096b` 验证 src/ 与 tests/ 完全无引用，requirements 也无；
  AGENTS.md 历史描述已修订。
- **Long pipeline UX (HTTP 超时)** — 异步 submit + `/status` 轮询已在 2026-05-08 上线，
  nginx 1500s 退居兜底。
- **S2-S5 Gate 系统** — `gate_manager.py` per-scenario + 52 个 `test_gate_scenario_configs.py`
  + `_build_skill_params` 扩展（`remix_script` / `vlog_strategy`）。
- **admin.py 0600 → backend 502** — `5c4d192` (v0.2.1) 在 `deploy.sh` 加 Phase 0.5
  防御 chmod + 头部注释带 `--chmod=F644,D755`。
- **GAP-A 防双击** — `db89079` (v0.2.1) `useSubmitting` 接入 5 个 submit 入口。
- **GAP-B 422 inline error** — `db89079` + `74f5310` 字段级红框 + `aria-invalid` +
  Pydantic `loc` 自动映射。
- **GAP-C `parseApiError` + ApiError class + 429 retry** — `db89079`，4 个 API helper
  改为抛 `ApiError`，前端展示 `(retry in Ns)` 后缀。
- **HU-05 `cardCopyEn` 100 条 zh→en 映射** — `4bf096b` (v0.2.2)，`GuidedCard` /
  `CardConnector` 渲染时 `tCardCopy(text, locale)`。
- **Creation Guide 重构** — `c52cad8` (v0.2.2) 抽取独立 `CreationGuide.tsx`，5-tab
  导航（Overview / Scenes / Frontend / Admin / Runbooks），加 ~120 i18n 翻译。
- **Brand Kit Tab 数据流断链** — `2238a84` (v0.2.3) `BrandKitTab.tsx` 改为 fetch
  `/api/portfolio/?kind=brand_kit`，137 张 momcozy 抓取图全部可见。
- **品牌资产 product 元信息** — `74f5310` (v0.2.4) `PortfolioFile` 增加 6 个产品字段
  （title / slug / brand / source_url / description / price），LRU 读 info.json。
- **QuickTemplate 抓取数据流** — `7daadc1` (v0.2.4) 新增 `/api/portfolio/brand-presets`
  endpoint，前端 fetch + merge over demo-data，刷新 scraper 不需重新部署 frontend。
- **3 篇 ADR + 5 篇 Runbook** — `4bf096b` + `7daadc1` 落入 `docs/architecture/adr/`
  + `docs/runbooks/`。

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
已在 2026-06-17 完成本地/fixture readiness：metrics router、repository、poller 与 analytics
agent 相关目标集通过，结果 `109 passed`。同日生产 GET-only probe 显示 `/api/health` 可达且
PostgreSQL `tables_verified=true`，Prometheus `/metrics` 可达；但本机现有 legacy `API_KEY`
候选访问 `/api/dashboard/overview` 与 `/api/metrics/{video_id}` 均返回 `401`，authenticated
business metrics readback 未通过。随后 `TODO-P2-1C` 按授权创建带 `expires_at` 的临时
tenant key 做 authenticated GET probe，因 `api_keys.expires_at` 是 naive timestamp，而
`verify_api_key()` 使用 aware `datetime.now(UTC)` 比较，触发 `TypeError` 并返回 503；
该 key 已撤销。`TODO-P2-1D` 已在本地修复该 datetime 边界并通过 `83 passed` 目标集，但
`TODO-P2-1E` 已将修复同步到生产并完成 authenticated GET readback 复验：`/api/dashboard/overview`
与 `/api/metrics/{video_id}` 均返回 200，post-revoke 返回 401。静态代码复核显示
`MetricsPoller.pull_all` 未注册到 `src/api.py` startup，只有手动 `POST /metrics/pull` 入口；
本轮未调用该 POST。`MetricsPoller` 的 TikTok/Shopify fetcher 仍是 stub，前端
`PerformanceDashboard` 显示真数据未验证。
- **E. Assets 上传链路** ✅ 后端单元测试已覆盖（`test_upload_e2e.py` 10 测试验证
multipart → 落盘 → `/api/files` 列出 → `/api/media/` 访问完整链路；含认证/扩展名/大小限制
负向测试）。前端 `brand-packages/page.tsx` 已集成 `AssetUploader` 上传面板（Header 右侧
上传按钮 + 可折叠上传区域，上传完成后自动刷新列表）。仍待: 生产未走通"上传 → 管线
引用 → 出现在最终视频"的闭环（uploaded 文件尚未被 keyframe/seedance 步骤实际引用验证）。
`/influencers` 列表 CRUD 在生产是否真存了 PG 未验证。
- **F. Webhook 事件分发** `src/tools/webhook_manager.py` 的 `audit.completed` /
`pipeline.completed` 事件已在本地 fixture 层覆盖 URL 安全、in-process listener、HTTP dispatch
与 failure isolation；测试使用 mock 网络依赖。Phase D 期间生产 `WEBHOOK_URLS` 为空，仍从未
触发真实外部接收端。需要配上接收端(可临时用 webhook.site)再跑受控事件验证。
- **G. 错误降级路径** `pipeline_degraded = True` 在 5 场景中未被触发(都走绿)。Mock POYO /
DeepSeek 故障下的"降级 + 终止 + 错误上报"链路、`error_collector` FIFO、`/telemetry`
端点的可见性,均未做负向测试。
- **H. 多用户并发 + API Key 隔离** `contextvars` 隔离机制在单机单请求 OK。同时跑 2+ 场景
使用不同 API key 时是否真的不串(尤其 LLM client + POYO client + Seedance client 三处
contextvars 读取),没压测过。
- **I. i18n 切换** `zh-CN` / `en` 在生产页面切换后,所有按钮 / 表单 / 报错 / SettingsPanel /
GatePanel / DistributionView 文案是否都从翻译表读取(无硬编码中文/英文残留),未走查。
- **J. 备用部署目标** `render.yaml`(海外)与 `deploy/tencent-cloudbase.md` /
`deploy/CLOUDBASE_STEP_BY_STEP.md`(国内 CloudBase) 已在 2026-06-17 做本地 docs/config
drift 审计但仍未部署验证。`render.yaml` 当前已是 `DEFAULT_LLM_PROVIDER=deepseek`，风险
不再是 `kimi` 默认值，而是 backend-only blueprint、`DATABASE_URL` 默认空、build trigger
覆盖不完整，以及 CloudBase 文档仍默认 GitHub Pages/demo key/CORS。
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

### 6. 2026-05-22 新增（S1 连续分镜向 S2-S5 迁移）

> 历史记录详见 [`docs/superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md`](../../superpowers/plans/2026-05-22-s1-continuity-migration-s2-s5.md)，不作为当前执行入口。

**已完成：**
- S3/S4/S5 后端 `continuity_storyboard_grid` step 接入
- `src/pipeline/continuity_utils.py` 共享抽象层（8 函数，24 测试）
- 13 个 POYO 模型 ID 修正（`kling-3-0` → `kling-3.0` 等）
- Kling sound / Wan aspect_ratio / Hailuo duration+resolution 参数适配
- S2/S3/S5 前端 `continuity_mode` 配置
- S2 `run_step` 缺失修复

**仍待完成：**
- **P0 — S3 E2E 全量验证**：代码完成，POYO 账户 402 insufficient credits，充值后重跑
- **P1 — S4 前端 `continuity_mode`**：SceneForm.tsx 中 S4 (`live_shoot`) 无独立表单块
- **P2 — `continuity_storyboard_grid` skill 品牌适配**：S2 `brand_mode=True` 时 micro_shots 硬编码 bottle warmer，需 LLM 驱动品牌分镜生成
- **P3 — 生产部署验证**：5 场景各跑一次 mock-mode 验证 continuity 产物存在

### 7. 2026-05-23 新增（视频生成速度优化）

> 详见 [`docs/analysis/video-generation-speed-root-cause-analysis.md`](../../analysis/video-generation-speed-root-cause-analysis.md) + [`docs/analysis/video-generation-speed-optimization-plan.md`](../../analysis/video-generation-speed-optimization-plan.md)。

**已完成（6 项全部实施）：**

| 编号 | 优化项 | 文件 | 预估收益 | 状态 |
|------|--------|------|----------|------|
| P0-3 | frame_variance 在 observe/off 模式下跳过 | `seedance_video_generate.py` | 15-30s/3clips | 已上线 |
| P0-2 | S4 clips 并发化（Semaphore(4) + gather） | `s4_live_shoot_pipeline.py` | 60s | 已上线 |
| P0-1 | S5 移除 sleep + 条件并发化 | `s5_brand_vlog_pipeline.py` | 100-130s | 已上线 |
| P1-1 | auto 模式减少 step-started state save | `step_runner.py` | 2-5s | 已上线 |
| P1-2 | auto 模式可选跳过 thumbnail_images | `step_runner.py` | 15-30s | 已上线（默认关闭）|
| P2-1 | keyframe 数量按 clips 需求限制 | `keyframe_images.py` + `s1_product_pipeline.py` | 30-120s | 已上线 |

**累计预估收益**：
- S1 典型场景：244s -> ~152s（提速 38%）
- S4 典型场景：210s -> ~155s（提速 26%）
- S5 典型场景：312s -> ~185s（提速 41%）

**验证结果**：16/16 相关测试通过，ruff lint 全通过。

**仍待完成：**
- **生产部署验证**：`.env.prod` 追加 `SKIP_THUMBNAIL_IN_AUTO=1`（如需要启用缩略图跳过）
- **收益实测**：同一组输入在优化前后跑时间对比，确认实际收益符合预期
- **质量非回归**：优化前后 audit_report 评分差异 < 0.05

### 8. 2026-05-25 新增（S1-S5 工作流阶段 3/4 收敛）

**已完成：**
- `S4/S5` gate step order 已与真实执行链路对齐，不再跳过 `continuity_storyboard_grid`
- `S4 gate_3_thumbnails`、`S5 gate_3_final` 已支持 state-assembled candidate，Gate Direct 契约已修正
- `S3/S4` continuity step 改为显式 skill 注册，不再依赖隐式 import 顺序
- continuity fallback 现在会写出 `_soft_degraded`、`_degraded_reason`、`_degraded_detail`，不再静默伪装成正常成功
- `status` API 与前端 `StageProgress` / `VideoWorkflow` / `StepByStepView` 已可显示 `soft_degraded_reasons` 摘要，continuity fallback 不再只存在于后端 state
- 前端已把 `soft_degraded_reasons.reason` 从内部码值映射为稳定用户文案，避免直接展示 `continuity_skill_fallback` 这类实现细节
- `tests/test_s3_e2e.py`、`tests/test_s5_e2e.py` 已改为 hermetic 回归：默认 patch `VideoDownloader`、`LLMClient`、`SeedanceClient`、`GPTImageClient`、TTS、audit，不再依赖外网、额度或内容审核状态
- hermetic 回归已分层：默认 `pytest` 仅跑 fast 集；完整慢集通过 `PYTEST_INCLUDE_HERMETIC_SLOW=1 pytest ...` 或 `make test-hermetic-full` 触发
- `continuity_storyboard_grid` 已从 bottle-warmer 硬编码模板收口为输入驱动：会吸收 `usage_scenario`、storyboard 文本、USP、品牌色，S5 本地 `clip_groups` 也会保留 `shot_type / product_angle / model_in_shot`
- `S2` 的品牌包语义已接入 continuity：`values`、`voice_guidelines`/`tone_of_voice`、`visual_constraints` 现在会进入 continuity prompt 和 `visual_identity`
- `S3` 的 creator/platform 语义已接入 continuity：`influencer_name`、source/target platform、`original_style_preserved` 与 remix `keep_notes` 现在会进入 continuity prompt；S3 fallback `clip_groups` 也会保留 creator pacing 和平台语境
- `S5` 的 vlog scene/persona 语义已接入 continuity：`scene_id` 对应的场景名称/描述、`story_description`、`selected_models` persona 现在会进入本地 continuity `clip_groups` 和 `visual_identity`
- `S1` 的 platform / brand narrative 语义已接入 continuity：`target_platforms`、brand tone、brand colors、`target_audience` 现在会进入共享 continuity prompt 与 `visual_identity`
- shared continuity 已补稳定导演意图结构：`clip_groups` 现在会产出 `scene_beat`、`beat_summary`、`transition_intent`，并透传到 `seedance-video-prompt`
- `S5` 本地 continuity 也已对齐这套结构：`_vlog_shots_to_clip_groups()` 现在同样会输出 `scene_beat`、`beat_summary`、`transition_intent`
- continuity audit 已开始消费这套结构：`asset_ready_audit` 新增 `director_intent_metadata` 检查，`continuity_score` 与 `continuity_direction_summary` 也已纳入 `scene_beat / transition_intent`
- gate 评分已开始消费导演意图元数据：`candidate_scorer._score_clip_candidate()` 现在会识别 `Narrative beat / Beat summary / Transition intent`，将其计入 `director_intent` 维度
- `video_prompts / vlog_strategy` 评分也已开始消费导演意图：`video_prompts` 新增专用 scorer，`vlog_strategy` scorer 也已从旧的 `title/hook/segments` 假设收口到当前真实的 `shots` 结构
- `S1/S3/S4/S5` 的 `seedance_clips.clip_details` 已开始直接透传 `scene_beat`、`beat_summary`、`transition_intent`，下游评分、audit 和诊断不再只能从 prompt 文本反推导演意图
- `candidate_scorer` 已进一步收口到结构化优先：`seedance_clips` 评分现在先读 `clip_details` 内的 `scene_beat / beat_summary / transition_intent`，只有结构化字段缺失时才回退到 prompt 文本解析
- `video_prompts` 评分也已收口到同一优先级：现在先读结构化 `scene_beat / beat_summary / transition_intent`，文本里的 `Narrative beat / Beat summary / Transition intent` 只保留为 fallback
- status / gate 诊断输出也已接入 continuity 导演意图：`/scenario/{scenario}/status/{label}` 与 `get_gate_state()` 现在都会返回 `continuity_diagnostics`，其中包含 `continuity_score`、`director_intent_metadata` 和逐段 `clip_directions`
- 前端 status / gate 面板也已接入这份诊断：`StageProgress` 与 `GatePanel` 现在会展示 `continuity_score`、`director_intent_metadata` 和前两段 `clip_directions`
- 候选比较卡片也已开始消费 continuity 摘要：`CandidateSelector` 现在会从 `continuity_direction_summary` / `clip_details` / 单条导演意图字段中抽取前两段 `scene_beat + transition_intent` 直接展示
- 候选卡片的 continuity 可解释性也已补齐：当 `score.breakdown.director_intent` 存在时，`CandidateSelector` 会直接显示导演意图得分，和卡片里的 `scene_beat / transition_intent` 摘要对齐
- 候选卡片 explanation 也已按 continuity 优先重排：当 explanation 文本包含 `director_intent=...` 时，`CandidateSelector` 会把它提到最前面；若文本里没有但 breakdown 有该维度，也会自动补到 explanation 前缀
- gate/status 顶部诊断摘要也已统一顺序：`StageProgress` 与 `GatePanel` 现在都通过同一个 helper 按“director_intent 状态优先，continuity score 次之”的顺序展示
- 结果页/质量视图 continuity 解释也已对齐：`DirectorPlayback` 与 `QualityDashboard` 现在复用同一份 continuity diagnostics helper，并展示逐段 `scene_beat / transition_intent`
- 版本对比卡片 continuity 解释也已接入：`CompareView` 现在会在版本卡片里直接展示 `director_intent` 摘要、`continuity score` 和首段 `scene_beat / transition_intent`
- 已选版本决策区 continuity verdict 已接入：`CompareView` 底部 action 区现在会对当前选中版本重复展示同一份 continuity diagnostics，下载/发布前无需再回看卡片
- continuity 已进入统一对比表：`CompareView` 的 quality comparison table 现在新增 `Director intent` 与 `Continuity score` 两行，版本间 continuity 差异不再只存在于卡片摘要
- continuity 已补表格解释行：`CompareView` 的 quality comparison table 现在还会显示 `Continuity verdict`，直接给出每个版本的 continuity 摘要与首段导演意图
- `CompareView` 的 continuity 信息已做轻量去重：版本卡片现在只保留 continuity 摘要，逐段 `scene_beat / transition_intent` 细节下沉到统一对比表和已选版本 verdict
- `CompareView` 的 `Continuity verdict` 已加长度控制：长 `transition_intent` 会在表格中软截断，完整内容保留在 hover `title`
- `CompareView` 的统一对比表已做视觉分组：continuity 三行现在归入独立 `Continuity diagnostics` section，与普通 `Quality criteria` 分区显示
- `CompareView` 的 continuity section 已压成 compact summary：`Director intent` 与 `Continuity score` 现在合并为一行 `Continuity summary`，继续压缩纵向高度
- `CompareView` 的 `Continuity summary` 已改成 badge/pill 形态：状态与分数用紧凑标签显示，进一步降低表格文本密度
- `CompareView` 的 `Continuity verdict` 已从原生 `title` 升级为可 focus tooltip：截断预览之外，完整文案现在可通过 hover/focus 稳定查看
- `CompareView` 的 verdict tooltip 已抽成轻量复用组件：`InlineTooltip` 现已接管 continuity verdict 的 hover/focus 展示，避免 tooltip 逻辑继续内嵌增长
- `InlineTooltip` 已在 `GatePanel` continuity diagnostics 复用：长 `beatSummary` / `transitionIntent` 不再直接撑开审批面板，完整文案通过 hover/focus 查看
- `InlineTooltip` 已在 `StageProgress` continuity diagnostics 复用：运行中视图里的长 `beatSummary` / `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 已在 `QualityDashboard` continuity diagnostics 复用：结果页质量面板里的长 `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 已在 `DirectorPlayback` continuity diagnostics 复用：结果页导演回放视图里的长 `transitionIntent` 现在也走统一 tooltip 口径
- `InlineTooltip` 本身已收口为轻量可配组件：现支持 `placement`、默认移动端安全宽度，以及 `focus/active` 下的稳定显示
- continuity 相关截断逻辑已抽成共享 util：`truncateDiagnosticText()` 现收口到 `web/src/lib/diagnosticText.ts`，`GatePanel` / `StageProgress` / `QualityDashboard` / `DirectorPlayback` 不再各自维护一份副本
- `StageProgress` 的历史 hook warning 已清理：stage completion tracking 改用 `ref + stageCompletionKey`，不再在 effect dependency 内嵌复杂表达式
- `StageProgress` polling 启动 effect 的 `exhaustive-deps` suppress 已移除：初始 timer 现在通过 `pollRef.current()` 调用最新 poll callback，不再捕获 stale callback
- `StageProgress` 的卸载安全已补齐：poll response、completion delay、celebration reset 都会检查 mounted 状态并在 unmount cleanup 中清理 timer
- `StageProgress` 轮询失败阈值路径已补测试：连续 status 请求失败达到阈值后会停止继续 schedule poll，并显示连接中断提示
- `StageProgress` 服务端错误态已停止 elapsed timer：status 返回 `error` / `pipeline_degraded` 后不再继续后台计时
- `StageProgress` timer cleanup 已收口为内部 helper：poll timeout、elapsed interval、completion delay、celebration reset 不再分散手写清理逻辑
- `StageProgress` 服务端错误通知已去重：同一错误签名只触发一次 `onError`，避免重复 status/error 路径重复通知父组件
- `StageProgress` gate pause 通知已去重：同一 `current_step` 的 `paused/awaiting_approval` 只触发一次 `onGatePause`
- `StageProgress` paused 语义已补回归：等待 gate 审核期间继续 elapsed 计时与 status polling，用于保留总等待时间并感知审批后的恢复
- `StageProgress` paused polling 已降频：进入 `paused/awaiting_approval` 后 status polling 从 2s 调整为 10s，elapsed 仍按秒计时
- `StageProgress` polling cadence 常量已提升到模块级：base/paused/max/failure threshold 不再在组件 render 内重复声明
- `StageProgress` stage definitions 命名已收口：局部 `STAGES` 改为 `stageDefs`，避免把模块级稳定定义误读成 render 内新建常量；未引入无收益 `useMemo`
- `StageProgress` stage runtime 派生逻辑已抽为纯函数：progress、active stage、completion key 可直接单测，不再完全埋在组件 render 内
- `StageProgress` 剩余时间估算已抽为纯函数：`estimateRemainingSeconds()` 覆盖 early elapsed、complete、同类型平均耗时 fallback 边界
- `StageProgress` 总进度计算已抽为纯函数：`deriveTotalProgress()` 统一产出 total steps/done/progress，并覆盖空 stage 边界
- `StageProgress` 初始 polling timer cleanup 已复用内部 helper：首次 status 请求前 unmount 不会再触发后台 status 请求
- Smart Create 的 `StageProgress` 父级错误消费已接入：`page.tsx` 现在传入 `onError`，status 返回 `error` / `pipeline_degraded` 时会停止 execution bar、清理 active pipeline 并弹页面级 toast，同时保留进度面板内的错误详情
- Smart Create 错误恢复逻辑已补行为级回归：`handleSmartCreateStageError()` 覆盖停止生成、清理 active pipeline、toast 展示和空错误 fallback
- continuity 规则导演层已增强：`continuity_storyboard_grid` 现在会派生 `director_profile`，把 `story_arc`、`audience_tension`、`brand_promise`、`platform_pacing`、`creator_cadence` 注入 `visual_identity`、`clip_groups` 和 Seedance prompt
- continuity 组合回归已通过：`tests/test_continuity_storyboard_grid.py`、`test_candidate_scorer_continuity.py`、`test_s1_continuity_pipeline.py`、`test_s3_e2e.py`、`test_s4_e2e.py`、`test_s5_e2e.py` 共 `75 passed, 12 deselected`
- LLM director planner 评估已落 ADR-007：当前不在默认 continuity 热路径引入 LLM，未来如实现必须 feature-flagged、schema-validated，并保留 deterministic fallback
- 非 S1 推荐阶段已收口：`RecommendPanel` 不再为 S2-S5 调用 `startS1StepByStep()`，改用本地 config 摘要，避免“其他场景 auto + gate”口径下仍误触发 S1 逐步接口
- GuidedForm continuity 配置已从 S1-only 扩展到 S1-S5：`product_direct`、`brand_campaign`、`influencer_remix`、`live_shoot_to_video`、`brand_vlog` 都会提交 `continuity_mode`、`storyboard_grid`、`transition_style`
- Smart Create async submit 已统一透传 continuity 参数，S2-S5 不再因为前端 payload 裁剪而丢失 continuity 配置；S5 专用 endpoint 类型也已补齐这些字段
- S4 前端场景路由已修正：`live_shoot_to_video` 现在会映射到 `/scenario/s4/submit` 与 `/s4` 页面，不再回退到 S1
- 前端 API wrapper 类型债已收口一层：`web/src/components/api.ts` 不再使用显式 `any` 返回类型，场景运行、StepRunner、发布、dashboard wrapper 已改为结构化宽类型，`eslint src/components/api.ts` 与 `tsc --noEmit` 均通过
- 首页编排层 lint 债已清零：`web/src/app/page.tsx` 移除未使用 import/store setter，并补齐实际依赖的 hook dependency，`eslint src/app/page.tsx` 已无 warning
- 结果/分发链路类型债已收口一层：`DistributionView`、`PublishPanel`、`OneShotResultView` 已移除显式 `any`，改用 distribution plan、publish result、one-shot result 的局部结构化宽类型；`tsc --noEmit` 通过，目标 lint 仅剩 `OneShotResultView` 两处 Next.js `<img>` 性能 warning
- 结果/作品/审批展示链路 lint 已进一步清零：`OneShotResultView` 对后端运行时媒体 URL 保留原生 `<img>` 并补精确 lint 例外，`works/page.tsx` 与 `ReviewPanel` 已移除显式 `any` 和未用表达式；目标 lint、`tsc --noEmit`、continuity/routing 单测均通过
- Step-by-step 展示链路类型债已收口：`AssetCard`、`components/types.ts`、`StepByStepView` 已移除显式 `any`；`AssetCard` 的 render-time `Math.random()` 已替换为确定性波形高度，避免 React purity warning；目标 lint、`tsc --noEmit`、continuity/routing 单测均通过

**当前剩余缺口：**
- **P0 — S2-S5 step-by-step 已收口为产品选择**：后端通用 `step/regenerate` 已接到 `StepRunner`，前端入口和推荐阶段现在都明确为“仅 `S1` 开放 step-by-step，其他场景走 auto + gate”。剩余问题只是不确定未来是否要补真正的多场景逐步交互
- **P1 — hermetic 测试提速已基本达标**：`S3/S4/S5` 三套回归已从约 74s 降到约 25s，`S3+S5` 组合约 15s。当前问题已从“过慢影响本地回归”收缩为“后续可按需继续做增量优化”
- **P2 — LLM director planner 已决策延后**：ADR-007 明确默认保留 deterministic `director_profile`，不在无 poyo token 阶段扩展默认热路径
- **P3 — 生产侧 continuity / gate 真流量验证未完成**：本轮修的是本地正确性，不是生产 API 真流量验收

**建议下一步顺序：**
1. 继续清理无 poyo token 也能验证的前端/文档口径不一致
2. 保持 continuity 产物质量增强在 hermetic / mock / unit 层推进
3. 如需继续扩大真实调用范围，按 `L4C` 重新取得单独授权、预算和执行边界后再跑

---
