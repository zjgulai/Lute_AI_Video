---
title: 企业 AI 图文视频全场景收敛路线图
doc_type: workflow
module: project
topic: enterprise-ai-content-all-scenarios-closure
status: stable
created: 2026-07-11
updated: 2026-07-21
owner: self
source: human+ai
---

# 企业 AI 图文视频全场景收敛路线图

> Clean-clone SSOT：本路线图及其引用的 tracked specifications、plans 与 runbooks。Ignored agent-local execution journals 仅是可选、非权威痕迹；clean clone 不得依赖它们完成 build、test、review、migration、deploy、rollback 或 evidence interpretation。

## 1. 目标与状态定义

目标：让 Fast Mode 与 S1–S5 在同一企业级安全、成本、质量、透明度、发布和指标合同下运行，覆盖 AI 文本、图片、音频和视频。

状态：

- `complete`：代码、测试和当前允许的验收证据均闭环；
- `in_progress`：本分支正在执行；
- `pending_local`：可在无外部副作用条件下实施；
- `blocked_external`：需要 owner、法律、基础设施或精确 L4 授权；
- `accepted_boundary`：工程已完成，但真实外部证据按边界单列。

执行分支：`codex/enterprise-ai-content-closure-20260711`。

默认禁止：provider submit、生产数据库写入、live deploy、publish、webhook send、delivery acceptance、metrics live pull、证书/私钥操作、off-host backup 实际上传。

## 2. Wave 0 — 基线、设计与治理

- [x] `complete` W0-01：确认 clean `main == origin/main`，基线 SHA 为 `c7a00b0710563b141ab21ed2152de12ba884f5e7`。
- [x] `complete` W0-02：创建 `codex/enterprise-ai-content-closure-20260711`，不使用 worktree，不自动 commit。
- [x] `complete` W0-03：重新运行 backend/frontend/build 和生产只读基线，区分 L1/L2/L3/L4/L5。
- [x] `complete` W0-04：完成 backend、frontend、ops/docs 并行审计，排除已关闭历史项。
- [x] `complete` W0-05：写入总设计 `docs/superpowers/specs/2026-07-11-enterprise-ai-content-all-scenarios-closure-design.md`。
- [x] `complete` W0-06：写入 Wave 1 逐文件 TDD 实施计划，并完成无占位符、类型和 spec 覆盖自审。
- [x] `complete` W0-07：在 `AGENTS.md` 增加本路线图和总设计入口，删除已过期的“所有场景已完整 E2E”过宽表述。
- [x] `complete` W0-08：把 agent-local planning journal 同步为本路线图入口，已完成历史计划移到完成区；journal 不作为 clean-clone 依赖。

## 3. Wave 1 — P0 安全、调用与发布止血

### 3.1 Protected media 与租户隔离

- [x] `complete` W1-01：定义 public/protected media path policy；`brand_assets`/`demo` 为显式 global，其余 tenant/default runtime roots 均为 protected。
- [x] `complete` W1-02：修改 `src/routers/media.py`，签名绑定 canonical path、tenant、purpose、expiry；签名生成先验证当前租户所有权，并移除 client-held API key 的 HMAC fallback。
- [x] `complete` W1-03：protected media 无 token 时拒绝；跨租户签名返回 `404`；有效本租户签名可匿名读取；public root 可按策略匿名读取；basename fallback 已移除。
- [x] `complete` W1-04：前端 protected media 已通过 `useSignedMediaUrl` just-in-time 获取短期签名；30 秒提前刷新、hard expiry、pending refresh、stale/unmount 和 short-TTL 防循环均有测试，签名 URL 不写入业务 state/database。
- [x] `complete` W1-05：`web/src/components/api.ts` 只接受 browser/configured API same-origin、固定参数集合的签名 URL；签名异常、畸形/encoded trusted-origin path 均 fail-closed，Fast 只允许规范化 cross-origin HTTP(S) preview，绝不回退 unsigned protected URL。
- [x] `complete` W1-06：修改 `deploy/lighthouse/ai_video_locations.conf`，移除整个 `backend_output` 的 direct alias/try_files，所有 runtime media 经 backend 验证。
- [x] `complete` W1-07：backend 匿名、跨租户、过期、path/token/tenant/purpose/expiry 篡改、public、exact path、Nginx bypass，以及 frontend signed URL/hook/四类 wrapper/DOM 与 imperative guard 均已覆盖；主控 fresh evidence 为 Task2 `36 passed`、frontend full `286 passed`、lint/typecheck/diff-check exit `0`，双独立复审 `APPROVED`。
- [x] `complete` W1-07A：`portfolio-ops-stable.md` 的 active media 配置已改为 canonical backend proxy，旧 alias/try_files 仅保留不可复制的 historical 警告；section/fence semantic contract 覆盖 whitespace directive、历史段充数、空壳文档和可复制历史 block，controller fresh `11 passed`、Ruff/diff-check clean，独立复审 `APPROVED`。

### 3.2 统一生成安全合同

- [x] `completed_local` W1-08：新增 strict `GenerationSafetyIntent` 和服务端派生的 versioned effective policy，只覆盖现阶段真实可执行的 media toggle、pending/quarantine disposition、retry=0、tenant 与 permission；durable budget、artifact transition 和 transparency 继续分别由 W1-27–30 与 W4 实现，不能在 normalizer 中伪完成。
- [x] `completed_local` W1-08A：DB tenant permission 的 null/empty/malformed/wrong-type 解析 fail-closed；env/test-bundle 的 `all` 必须按 key type 显式授予，fresh schema default 改为空权限并只生成 migration、不执行生产 SQL。
- [x] `completed_local` W1-09：Fast、S1–S5 blocking endpoint、unified async submit 与 legacy `/pipeline/start` 均消费同一 strict resolver，禁止 Pydantic 先行 coercion、S2 hardcode media true、S3–S5 丢字段和 S5 raw JSON 重解释。Legacy contract 仅保留真实可运行的 `product_direct/s1`，S2–S5 使用统一 submit。
- [x] `completed_local` W1-09A：effective policy/state authority 字段已设为 server-owned；public state edit、regenerate、Gate 和 legacy/cached state 均在 mutation 前校验 exact persisted policy/profile，missing/corrupt/unknown-version fail-closed。
- [x] `completed_local` W1-10：前端 `scenarioPayload`/Fast payload 与 OpenAPI schema 对齐，只有实际用户点击显式发送 media=true + pending_review + retry=0；缺失意图默认 no-media。OpenAPI types 已用项目生成器刷新并通过 drift guard。
- [x] `completed_local` W1-11：已用真实 StepRunner/SkillRegistry/SkillCallable/provider-client boundary 的 fake transport 覆盖 no-media、exact bounded profile、retry=0、Gate candidate、force/regenerate 和单次 provider attempt；continuation routes 还要求当前 key 重新具备 `provider:submit`。
- [x] `completed_local` W1-11A：Fast task/status 已绑定 tenant；per-run Seedance/CosyVoice client 不跨租户保留凭证，video/TTS/silent fallback 均写 tenant disposition/run path；fallback 与 requested-TTS failure 只投影为 bounded。

### 3.3 Mutation、幂等与 S1 重复 pipeline

- [x] `completed_local` W1-12：`apiFetch` 只自动重试 GET/HEAD/OPTIONS；POST/PUT/PATCH/DELETE 为零重试；每个读取 attempt 有独立 timeout，caller abort 与内部 timeout 组合且 mutation 不重试。
- [x] `completed_local` W1-13：S1 blind legacy fallback 保持移除；Fast 与 S1-S5 canonical async submit 的 ambiguous response 已通过 browser-persisted action key、0/1/2/5 秒 tenant-bound GET readback、reload recovery 与 no-second-POST 回归闭环。
- [x] `completed_local` W1-13A：后端 S1 broad `TypeError` 全链重放已移除；fake provider 成功后异常的 submit attempt 仍恰好一次。
- [x] `completed_local` W1-14：Recommendation 默认使用本地建议；渲染阶段不调用 S1 provider-capable API，真实生成只由显式 Start 动作触发。
- [x] `completed_local` W1-15：`/fast/submit` 与 `/scenario/{scenario}/submit` 强制 tenant-scoped `Idempotency-Key`；同 key/同 canonical payload 返回原 job，payload/operation/scenario/effective policy 变化返回 `409`，跨 tenant 不泄漏。
- [x] `completed_local` W1-16：PostgreSQL/SQLite `idempotency_records` 已覆盖原子 claim、owner lease/CAS、Fast durable result、S1-S5 label binding、并发/restart/readback 与 `recovery_required`；生产迁移、deploy 和 worker 自动续跑仍未执行/不在本项。

### 3.4 Token smoke 治理

- [x] `completed_local` W1-17：token path 已声明绑定 `production-provider` Environment，并限 `main`、canonical HTTPS、strict TLS、read-only dependency 与串行 concurrency；Environment 实际配置仍单列 W1-21。
- [x] `completed_local` W1-18：workflow 在安装/Playwright 前校验 private plan/approval、finite exact budget、logical refs、submit=1、retry=0、pending_review、Fast media authority、短期 UTC expiry、当前 run/attempt 与 commit SHA；production key 只注入 validator 和 token run 两步。
- [x] `completed_local` W1-19：一次 workflow 只允许一个固定 allowlist spec，强制 `--workers=1 --retries=0`；token trace/screenshot/test-results 关闭，完整 token suite 不可被全局解锁。
- [x] `completed_local` W1-20：静态 tests 动态枚举全部 production `@token-smoke` specs，对照 Playwright/validator allowlist，并证明未列入的 mutation spec 在 token mode 不可达。
- [ ] `blocked_external` W1-21：2026-07-21 GitHub API 只读核验显示 `production-read-only-dry-run` 已存在但无 protection rule、无 Environment secret，`production` Environment 不存在。需要 GitHub owner 配置受限 dry-run 身份、两组 Environment secrets/branch policy，并为 `production` 配置固定审批人；不得复用或上传仓库根目录私钥。

### 3.5 发布真实性与持久化人工验收

- [x] `completed_local` W1-22：新增 tenant-bound、artifact-bound、single-use acceptance record schema/repository/API；本地 focused/full、disposable PG18、OpenAPI/recovery 与独立复核已通过。2026-07-21 schema/application 已随 provider-off release 部署，但未执行 acceptance mutation 或 authenticated functional acceptance。
- [x] `completed_local` W1-23：两条发布路由只接受服务端 acceptance id，并以 `artifact:publish|all`、单平台单次 attempt、durable audit、single-use consume、无自动重试/恢复闭环；focused/full、fake connector、disposable PG18、OpenAPI/前端与独立复核已通过。2026-07-21 schema/application 已 provider-off 部署，真实 publish 未执行。
- [x] `completed_local / independent_review=true` W1-24：TikTok/Shopify credential、publish/status runtime mock、精确 `simulated` truth、发布 outcome matrix 与 status truth 已按批准规格实现；后续 W1-25 将外部 status lookup 收敛为 durable receipt readback。2026-07-21 独立六维审查发现的五组 source type-contract 问题已由主线程修复且无 suppression；同一审查线程复验 `PASS / APPROVE`、`accepted_actionable_findings=0`，fresh source Pyright `0 errors`、focused `580 passed`、Ruff/docs/diff clean。在该 review checkpoint，既有业务行为已随 production SHA `95c2d0460ccb1566b7a612cee3592cebb3439cef` provider-off 部署，而 follow-up type-contract 修复尚不是 production evidence；其后续发布状态必须按实时 Git/main/runtime 重新核验。真实 credential/connector/status、live publish 均未验收。
- [x] `completed_local` W1-25：发布请求已使用 strict platform options；TikTok Direct Post v2、Shopify Admin GraphQL `2026-07`、consume 前 read-only preflight、strict durable `publish-receipt.v1`、tenant-bound attempt readback、receipt-only legacy status 和 canonical default-off env 已按批准规格实现。Focused `885 passed`、本地 PG18 compat/rollback/re-upgrade/fresh-init 各阶段 `2/2`、backend `3585 passed, 9 skipped, 14 deselected`、frontend `67 files/390 tests` 与 build 均通过。后续独立 Codex 审查完成，两个前端建议经规格核验为有意的 fail-closed/W5 UI deferred 边界，`accepted_actionable_findings=0`。代码已随 2026-07-21 provider-off release 部署；真实 credential/connector/status、live publish/reconciliation 均未验收。
- [ ] `blocked_external` W1-26：真实 sandbox/production publish 需要平台凭证、单 post 授权、删除/回滚方案和人工验收记录。

### 3.6 成本账本与预算

- [x] `completed_local / independent_review=true` W1-27：cost ledger 已迁移到 PostgreSQL/SQLite durable repository，绑定 tenant/job/attempt/provider/model；DeepSeek、SiliconFlow TTS、PoYo GPT Image 2 与 Seedance 2 均接入 reserve/settlement，并通过 Task 10 全量 recovery、migration、backup、frontend 与静态门。
- [x] `completed_local / independent_review=true` W1-28：LLM exact token usage、TTS strict provider-input UTF-8 bytes、image unit 与 video task/seconds 计费事实均有本地账本合同；provider `311 passed`、affected regression `467 passed`、backend/frontend/OpenAPI 全量门通过。
- [x] `completed_local / independent_review=true` W1-29：canonical provider paths 统一为单次付费 attempt、`max_retries=0`、ambiguous/accounting-error 保留与无自动恢复；当时的 16-table recovery、PG18 migration lifecycle、SQLite parity 与 schema-first runbooks 已同步，后续 W3-09 已将固定表清单升级为动态发现。
- [x] `completed_local / independent_review=true` W1-30：provider submit 前原子预算预留、失败释放、重启后 hard cap、finite server-owned scopes 与 regeneration epoch 已通过 Task 5–9 独立复核；Task 10 full gate 与最终独立复核 `PASS / APPROVE`, `accepted_actionable_findings=0`。
- [x] `retired_after_consumed_attempt` W1-31：2026-07-19 的唯一授权 mutation 返回 HTTP 403 且未重试；authority 已消费，账单对账不再是发布门禁。2026-07-20 起所有 W1-31 execute 入口均在 provider client 构造前永久 fail-closed；历史 ledger 只读保留，禁止复用或自动补跑。

## 4. Wave 2 — 运行正确性与数据一致性

### 4.1 生命周期与错误语义

- [x] `completed_local / independent_review=true` W2-01：S1–S5 统一由 canonical completion truth 按 scenario step order、必需 artifact、audit、error/degraded 和 exact lifecycle envelope 推导 `completed_full|completed_bounded|error`；StepRunner、持久化/水合、在线/持久 readback 和 wrapper 均消费同一真值。当前 request-derived profile 仍只授权 no-media/bounded，未开放 full-media provider authority。
- [x] `completed_local / independent_review=true` W2-02：Seedance/GPT Image/CosyVoice/Remotion/Fast 及 S1–S5 keyframe/clip/audio/thumbnail/final assemble 聚合均保留 exact boolean `simulated`；final assemble 还要求 `is_stub=false`，missing/non-boolean/true 一律不能进入 `completed_full`。最终 backend `4035 passed`、hermetic `282 passed`、core Pyright `0 errors`。
- [x] `completed_local / independent_review=true` W2-03：DeepSeek、GPT Image、Seedance、CosyVoice 已覆盖 explicit rejection、ambiguous submit/poll、artifact failure、accounting failure、restart readback 与单 mutation/no fallback；focused `160 passed`，未发现需要修改 provider adapter 的新缺陷。
- [x] `completed_local / independent_review=true / browser_fixture_blocked_environment` W2-04：PipelineStatusBar 复用 canonical classifier，矛盾 terminal envelope fail-closed，并区分 pending_review、bounded、recovery_required、degraded、error、paused；OneShot full pending-review 明示人工验收且 `publish_allowed!==true` 时无 publish panel；Fast/page recovery 保留同一 idempotency key且只读检查，不自动重提。前端 `68 files/400 tests`、lint、TypeScript、OpenAPI、32-route build 均通过；独立复验 `PASS / APPROVE`、`accepted_actionable_findings=0`。本机 Playwright bundled Chromium 缺失，system Chrome 在 navigation 前启动挂起，browser fixture 未形成应用断言证据。

### 4.2 PostgreSQL、migration 与 readiness

- [x] `completed_local / independent_review=true` W2-05：production 配置 DATABASE_URL 后连接或初始化异常 fail-fast，verification 失败关闭并丢弃 pool；SQLite fallback 仅 development/test 通过精确 `SQLITE_FALLBACK_ENABLED=1` 显式开启。
- [x] `completed_local / independent_review=true` W2-06：已拆分 process-only liveness 与 sanitized database readiness；PG/migration/current-schema required schema 异常使 readiness 非 2xx，legacy health 不会重新打开不可信 pool，release Docker health 使用 readiness。
- [x] `completed_local / independent_review=true` W2-07：应用 startup/readiness 不执行 migration；Alembic/code-head/database failure 保留稳定脱敏状态，deploy gate 的 heads/current/upgrade 失败只输出固定安全码。
- [x] `completed_local / independent_review=true` W2-08：PostgreSQL 18 canonical bootstrap 已分流；空库 baseline+atomic head stamp、旧 lineage 拒绝保留、历史库 Alembic upgrade 均达到或保持同一唯一 head。
- [ ] `local_disposable_complete / independent_review=true / remote_ci_blocked_external` W2-09：guarded disposable PG18 已验证 fresh bootstrap、non-empty/old-lineage refusal、historical upgrade、idempotent re-upgrade、required schema 与 HTTP readiness；用户禁止 GitHub 更新期间 remote CI 仍未执行，不能标为完整 W2-09。

### 4.3 State、quality 与 provider keys

- [x] `completed_local / independent_review=true` W2-10：机器契约、初始 state、filesystem/repository projection、live status 和 durable async snapshot/readback 均保留 `regenerate_chain`、`soft_degraded_reasons`；共享 validator 使 FS/PG 错误类型稳定 fail-closed，同线程独立复验 `PASS / APPROVE`。
- [x] `completed_local / independent_review=true` W2-11：filesystem、真实 SQLite、fake PG row 与 guarded disposable PostgreSQL 18 均完成数据库回读；测试先删除 filesystem cache，并原样保留 cursor、tenant、审计数组与 pending `quality_rewind`，PG18 `5 passed`。
- [x] `completed_local / independent_review=true` W2-12：quality-score rewind 使用持久化有界 envelope；首次 durable save 同时包含 epoch+完整 rewind，durable `_quality_attempt` 是 SSOT，resume/direct run/regenerate、crash、stale/exhausted attempt 和畸形 upstream 均 fail-closed；成功后按 upstream→consumer 精确清理。
- [x] `completed_local / independent_review=true` W2-13：DeepSeek、GPT Image、PoYo、Seedance、CosyVoice 在双并发 tenant fake-key 上保持 request scope；构造期 transport 全部 lazy，retained ElevenLabs paid path 在构造前阻塞。Batch C 最终 backend `4103 passed`、hermetic `283 passed`、独立复验 `accepted_actionable_findings=0`。

### 4.4 前端场景正确性

- [x] `completed_local / independent_review=true` W2-14：live/durable status 暴露 canonical `step_order` 与最小 gate status；StageProgress 仅从服务端 coherent terminal truth 完成，候选与选择不出现在轮询响应。
- [x] `completed_local / independent_review=true` W2-15：Gate polling 按 S1-S5 场景调用 canonical status；exception、三次静止、360 次 timeout、degraded/recovery/invalid/null cursor 及完整九字段 terminal contradiction 均 fail-closed。next gate、final step 或精确 bounded/full lifecycle 才推进；重试只读且不重复 approval POST。
- [x] `completed_local / independent_review=true` W2-16：S5 GuidedCard 支持恰好六文件/六素材、drop、Enter/Space、部分失败保留与可见错误；AssetPicker 跨筛选保留已选项并严格返回用户点击顺序，提交双六项数组。
- [x] `completed_local / independent_review=true` W2-17：Review/Completion 响应式布局、全局 focus-visible/reduced-motion 和 admin 双语表头/空态/详情/状态/分页/ARIA 已闭环；登录 401/422 使用当前 locale 稳定错误。三轮同线程只读审查最终 `PASS / APPROVE`、`accepted_actionable_findings=0`；fresh frontend `69 files/433 tests`、backend `4103 passed`、UI-only Playwright `2 passed`、静态/构建/文档 gate 全绿。

## 5. Wave 3 — 可复现构建、可观测性、灾备与部署

### 5.1 依赖、解释器与类型门

- [x] `completed_local` W3-01：生产、CI、Ruff、Pyright 与锁文件统一为 CPython `3.12.13`；最终 locked backend image 的离线 import、non-root 与缺 key fail-closed 已实测。
- [x] `completed_local` W3-02：Docker/Compose/Render/CI 统一消费 `pyproject.toml + uv.lock`；`requirements.txt` 仅为受漂移检查约束的 generated compatibility export。
- [x] `completed_local` W3-03：生产 `src` Pyright 为 `0 errors`；历史 test diagnostics 与 `src/tests/scripts` suppression/config 均由不可在普通门禁刷新、只允许减少的 exact ratchet 约束。
- [x] `completed_local / blocked_external_github` W3-04：pip/npm 与 Trivy/Grype High+Critical 门禁、精确 30 天风险记录和最终镜像证据已闭环；Dependabot security updates/alerts 仍需 GitHub owner 配置与外部证据。

### 5.2 Prometheus、Grafana 与通知

- [x] `completed_local / independent_review=true` W3-05：alert/dashboard 查询与 exporter 指标名、label、status 枚举和 durable completion truth 已对齐；同一独立审查线程四轮修复复验后 `PASS / APPROVE`。
- [x] `completed_local / independent_review=true` W3-06：固定 digest 的 `promtool`/`amtool`、全部 rule firing/resolved fixture 与 exporter/query/dashboard 合同已进入 blocking gate；不存在的指标、label 或枚举会使测试红。
- [x] `completed_local / independent_review=true` W3-07：仓库管理 provider-off Prometheus/Alertmanager/Grafana 配置、内部 scrape 边界、fixture receiver 和 ownership runbook；真实 receiver/通知仍由 W3-08 单独授权。
- [ ] `blocked_external` W3-08：合成 5xx/provider failure 触发真实通知并验证恢复通知，需要通知渠道授权。

### 5.3 Off-host DR

- [x] `completed_local / independent_review=true` W3-09：恢复 API/CLI 强制 exact stats，逻辑备份/恢复动态发现 public base tables，并在任何写入前要求 target/stats/JSONL 精确同集；未知边、重复表、环、畸形行数和省略 stats 均 fail-closed。final recovery contract `71 passed`，disposable PostgreSQL 18 动态 dump/restore/parity `1 passed`，同一独立审查线程最终 `PASS / APPROVE`。
- [x] `completed_local / independent_review=true` W3-10：strict `source-manifest.v1` 与 `backup-manifest.v1`/detached SHA 绑定 Git/OCI/image、Alembic/PG、动态逐表行数、媒体精确集和所有恢复 artifact；create no-clobber，中途失败清理本次输出且允许修正重试，backup publish 与 restore 均先验证 canonical SSOT。
- [x] `completed_local / independent_review=true` W3-11：实现 provider-neutral create-only object-store protocol、zero-client dry-run 与 fake-store tests；仅验证 version/checksum/encryption receipt metadata，不选择 provider、不实现自定义加密、不接凭证或真实 bucket，post-put 不确定结果不重试。
- [ ] `blocked_external` W3-12：配置 versioned/immutable bucket、KMS 和 retention，需要基础设施 owner 授权。
- [ ] `blocked_external` W3-13：模拟 Lighthouse 主机不可用，从 off-host 副本恢复 PG18 与媒体并核对 parity。

### 5.4 Atomic deploy 与 provenance

- [x] `complete` W3-14：GitHub run `29793757819` 在 exact `main` SHA `95c2d0460ccb1566b7a612cee3592cebb3439cef` 上完成 provenance、full preflight、backend/frontend/rendering SHA-tagged build/runtime smoke、SBOM、三镜像 scan/Critical enforcement 与 exact release bundle upload；只有后续 restricted remote dry-run 因 Environment secrets 为空而 fail-closed。
- [x] `complete` W3-15：2026-07-21 授权维护窗口使用已审查 immutable image bundle 完成 live deploy；release compose 无 live source/`.next` bind mount，应用切换时共享 nginx/portal-auth 未重建，AI Video location snippet 经备份、`nginx -t`、reload 与 rollback-ready 检查。该证据是 maintenance-window deploy，不是 zero-downtime 声明。
- [x] `completed_local` W3-16：canonical wrapper 默认 dry-run，非法 `DRY_RUN` 在 SSH/key 检查前立即退出；dry/live 都强制 clean、同步 `origin/main` 的 `main`，live 还要求 `RELEASE_SOURCE_SHA` 精确匹配 reviewed HEAD。focused deploy contract `39 passed`、bash syntax 与 scoped diff clean；后续已授权 live 执行证据单列在 W3-15/W3-19。
- [ ] `blocked_external` W3-17：workflow provenance/build contract 已由 run `29793757819` 验证，SSH 仅接受 pinned known-hosts；但 `production-read-only-dry-run` Environment 的五个 `DRY_RUN_*` secrets 均未配置，remote dry-run 在 SSH 构造前 fail-closed，未生成 deletion artifact。修复需要独立受限账号/密钥和 GitHub owner 配置，禁止回退复用 `DEPLOY_*` 或现有生产私钥。
- [x] `completed_local` W3-18：rendering health 只有 Remotion/ffmpeg/Chromium 全部 ready 才返回 200；provider-backed smoke 只接受 200，500 不再作为业务成功；聚焦合约已包含在 `154 passed`。
- [x] `complete` W3-19：2026-07-21 的精确授权 provider-off live deploy 已验证 canonical wrapper `exit=0`，随后独立 L3 acceptance 通过 HTTPS/pages、PostgreSQL readiness、auth guards、容器/restart、日志与浏览器检查；provider、publish、delivery 与 token smoke 均为零调用。

## 6. Wave 4 — 透明度、C2PA、文档与体验

### 6.1 透明度与 C2PA

- [x] `completed_local` W4-01：已定义 strict `transparency-record.v1` / `transparency-sidecar.v1`，覆盖文本、图片、音频、视频的 hash-only facts、relative artifact identity、ordered parent/source chain、canonical detached digest 与 scoped no-clobber write/readback；独立审查首轮 3 个 Medium 已用 RED/GREEN 修复，同线程复验 `PASS / APPROVE`。
- [x] `completed_local / independent_review=true` W4-02：Fast 与 S1–S5 UI 始终显示 AI-generated label；tenant-bound read-only projection 与 ZIP 绑定 exact sidecar/detached digest，缺失或冲突 fail-closed；acceptance 与 server-owned TikTok/Shopify metadata 保留人工编辑和来源事实。独立审查发现并复验关闭 1 个 High package TOCTOU，最终 `PASS / APPROVE`、`accepted_actionable_findings=0`；本地 Reader 不代表法律合规或独立验证。
- [x] `completed_local` W4-03：已通过 uv pin `c2pa-python==0.36.0`，使用当前 `C2paSignerInfo` / `Signer.from_info` / `Builder.sign` / `Reader`，required 模式在 SDK、证书、签名、active manifest、AI action、claim signature 或 data hash 缺失时 fail-closed；本地测试证书仅声明 `signed_local_readback`，不冒充受信或独立验证。
- [x] `completed_local / independent_review=true` W4-04：Fast 与 S1–S5 的 canonical text/image/audio/video producer 已进入有限映射的 append-only provenance boundary；regeneration/human edit/Gate approval 延伸 parent/source chain，skip/simulated media 只记录显式 simulated facts，S2 external refs 保持 pending source truth，所有真实 image/video 先进入 immutable snapshot 再经过 server-owned C2PA policy boundary。FS/SQLite/PG 严格持久化同一 transparency projection；同一审查线程完成修复复验并返回 `PASS / APPROVE`。
- [x] `completed_local / independent_review=true` W4-05：`acceptance-create.v2` 已绑定 exact sidecar path/digest、最终 C2PA status 与 artifact bytes；required 只允许实际 Reader 复验的 `signed_local_readback`，publish inspect/consume 重新校验 sidecar、bytes 和 Reader truth，旧 v1 仅保留 read/revoke/replay 而不能授权 publish。同一审查线程返回 `accepted_actionable_findings=0`；W4-08 外部 validator 仍未完成。
- [ ] `blocked_external` W4-06：owner/legal 确认 provider/deployer/EU 范围及是否签署 Code of Practice；未确认前 EU delivery blocked。
- [ ] `blocked_external` W4-07：申请符合信任策略的证书并接入 HSM/KMS/secret mount；不得把凭证写入仓库。
- [ ] `blocked_external` W4-08：用独立 C2PA validator 验证真实样本和目标平台保留行为。

### 6.2 文档、版本和安全事实源

- [ ] `pending_local` W4-09：版本由单一构建源生成，在 backend health、web package、tag、release notes、AGENTS/README 一致。
- [ ] `pending_local` W4-10：API key/test-bundle/tenant/admin 权限合同以代码测试为准，同步 AGENTS、CLAUDE 和 Creation Guide。
- [ ] `pending_local` W4-11：建立唯一 canonical deploy/DR/token-smoke SOP；旧 `status: stable` 破坏性文档改 historical/archived，删除可复制 live 命令。
- [ ] `pending_local` W4-12：CI 文档治理禁止 active docs 出现 live `down --volumes`、未预览 `rsync --delete` 和 `.env.prod` key 提取。
- [ ] `pending_local` W4-13：把 `known-gaps` 拆为 current backlog 和 append-only history；ignored agent-local journals 仅保留指向当前 tracked 路线图的可选指针。

## 7. Wave 5 — Fast 与 S1–S5 纵向验收

### 7.1 共用 harness

- [x] `completed_local` W5-01：Fast/S1–S5 参数化 no-provider contract 已绑定 tenant、`generation-safety.v2`、canonical step order、pending-review disposition、audit、transparency 和场景人工门禁；`independent_review=true`。
- [x] `completed_local` W5-02：single-submit L4 draft-plan generator 已逐场景绑定精确 USD-nanos 预算、sample、retry=0、有限 job cap、pending-review-only、停止条件和确定性 digest；它不绑定 runtime profile，也不创建执行/provider authority；`independent_review=true`。
- [x] `completed_local` W5-03：HU-03 四项人工 rubric 与 Fast/S1–S5 brand/source/rights/ownership/model-product review records 已使用严格 tenant/scenario/sample/半开时间窗校验；所有 promotion/provider/publish/delivery 标志恒为 false；`independent_review=true`。

本批仅有 L2 local/fixture/static 证据。独立审查首轮发现 1 High、2 Medium、1 Low，主线程以 RED/GREEN 修复后，同一审查线程复验 `PASS / APPROVE`、`accepted_actionable_findings=0`。主线程最终 `make ci` 为 `4334 passed, 9 skipped, 22 deselected`、Ruff/Pyright/ratchet 全绿；未调用 provider、生产、publish、delivery 或 GitHub，W5-04 及后续场景切片不因本地 harness 完成而解锁。

### 7.2 场景切片

- [x] `completed_local / independent_review=true` W5-04 readiness：只读 CLI 已将一个私有 Fast activation record 严格绑定到 canonical W5 draft 的 tenant、sample、plan、预算、job cap、optional media 和半开 UTC 时间窗；重复键、浮点/非有限值、UTF-8 超限、深嵌套、坏路径、symlink、非普通文件和读取竞态均 fail-closed。readiness 永远保持 `provider_call_allowed=false`、`execution_authorized=false`、publish/delivery=false，不创建 runtime profile、provider-cost account 或 one-shot consume truth。同一独立线程三轮审查后返回 `PASS / APPROVE`、`accepted_actionable_findings=0`；最终主线程 `make ci` 为 `4376 passed, 9 skipped, 22 deselected`。
- [x] `completed_local / independent_review=true` W5-04 runtime binding：私有 binding 已绑定完整 canonical activation digest、exact Fast request/key digest、固定 DeepSeek/PoYo envelope、pending-review/retry-zero、预算与 job caps；新 owner 在同一 durable idempotency insert 中单次消费 activation，existing exact replay 先于当前私有 packet 加载并保持只读。独立审查首轮 1 High、2 Medium、1 Low 全部 RED/GREEN 修复，同一线程复验 `PASS / APPROVE`、`accepted_actionable_findings=0`；最终主线程 `make ci` 为 `4400 passed, 9 skipped, 23 deselected`，disposable PG18 bootstrap `6 passed, 1 deselected` 与 concurrency `1 passed`。证据仍是 local/provider-off，尚未迁移或部署到生产，也未执行真实 Fast/provider submit。
- [ ] `blocked_external` W5-04：Fast 单提交真实视频、pending-review、成本、透明度和人工验收。
- [ ] `blocked_external` W5-05：S1 strategy→assemble→audit→Gate→acceptance 全链单样本。
- [ ] `blocked_external` W5-06：S2 brand strategy→media→brand/HU-03→acceptance 全链单样本。
- [ ] `blocked_external` W5-07：S3 source rights→analysis→remix→media→acceptance 全链单样本。
- [ ] `blocked_external` W5-08：S4 footage ownership→continuity→media→audit→acceptance 全链单样本。
- [ ] `blocked_external` W5-09：S5 六视图→角色连续→multi-clip→audit→acceptance 全链单样本。

### 7.3 发布、交付与指标

- [ ] `blocked_external` W5-10：使用已验收 artifact 做单平台 sandbox/controlled publish，验证真实 post id 和回滚。
- [ ] `blocked_external` W5-11：delivery acceptance 由授权人员记录，不由 agent 自证。
- [ ] `blocked_external` W5-12：active post allowlist 后执行单 post metrics pull，验证 TikTok/Shopify mapping 和 attribution。

## 8. Wave 6 — 企业容量与最终接受

- [ ] `pending_local` W6-01：双租户/多场景并发 fake-provider 压测，验证 context、state、media、budget、idempotency 不串扰。
- [ ] `pending_local` W6-02：worker/process restart 测试，验证 job resume、cost reservation、acceptance single-use 和 artifact state 保持一致。
- [ ] `pending_local` W6-03：限流、backpressure、queue saturation 和 bounded shutdown 测试。
- [ ] `blocked_external` W6-04：受控生产容量 smoke，需并发、预算、时段和停止条件授权。
- [ ] `blocked_external` W6-05：联合演练 alert、off-host restore、atomic rollback 和 owner escalation。
- [ ] `pending_local` W6-06：最终 security/code/spec review，所有 Critical/Important findings 清零。
- [ ] `pending_local` W6-07：生成场景×证据等级×artifact×reviewer×platform 的 acceptance matrix。
- [ ] `blocked_external` W6-08：owner 签署企业全场景生产接受；在此之前不得声明完整商业闭环。

## 9. 已关闭且不重建的历史项

- PostgreSQL 18 schema-backed backup 与 12-table isolated restore；
- suspected tenant key replacement/revoke；
- Lighthouse sidecar rsync exclude 与 rendering Alpine mirror；
- no-token 部署层 L4/L3 验收和 PR #74 dry-run terminal closeout；
- 已并入 main 的 Dependabot 分支；
- S3/S4/S5 Gate identifier parity、本地 degradation fault injection、injected webhook receiver；
- metrics connector 基础 mapping；剩余项是 active post、attribution 与授权 live pull；
- S4 `@material` prompt reference；真实 frame conditioning 是独立产品能力，不作为已完成项扩大解释。

## 10. 路线图更新规则

- 每个 task 只有在 fresh test/command evidence 和独立 review 后才能标记 `complete`；
- L4/L5 task 不能用 fixture 或旧记录改成 `complete`；
- 每波结束同步本文件、当前实施计划、AGENTS 入口和 acceptance evidence；
- 不自动 commit、push、PR、merge、deploy 或外部发送；需要时由用户明确授权。
