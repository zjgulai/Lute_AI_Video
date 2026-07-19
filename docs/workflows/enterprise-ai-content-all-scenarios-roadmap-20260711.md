---
title: 企业 AI 图文视频全场景收敛路线图
doc_type: workflow
module: project
topic: enterprise-ai-content-all-scenarios-closure
status: stable
created: 2026-07-11
updated: 2026-07-20
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
- [ ] `blocked_external` W1-21：由 GitHub owner 配置 Environment reviewers、secrets 和固定审批人；仓库内只能验证 workflow 声明，不能证明外部设置已生效。

### 3.5 发布真实性与持久化人工验收

- [x] `completed_local` W1-22：新增 tenant-bound、artifact-bound、single-use acceptance record schema/repository/API；本地 focused/full、disposable PG18、OpenAPI/recovery 与独立复核已通过，生产 migration/deploy 未执行。
- [x] `completed_local` W1-23：两条发布路由只接受服务端 acceptance id，并以 `artifact:publish|all`、单平台单次 attempt、durable audit、single-use consume、无自动重试/恢复闭环；focused/full、fake connector、disposable PG18、OpenAPI/前端与独立复核已通过。生产 migration/deploy 和真实 publish 未执行。
- [ ] `implementation_complete_local / independent_review_pending` W1-24：TikTok/Shopify credential、publish/status runtime mock、精确 `simulated` truth、发布 outcome matrix 与 status 503/502/200 已按批准规格实现；focused `600 passed`、本地 PG18 `2 passed`、backend `3415 passed, 9 skipped, 14 deselected`、frontend `67 files/388 tests` 与 build 均通过。`independent_review=false`，未达到 `completed_local`；生产、真实 credential/connector/status、live publish 均未验收。
- [x] `completed_local` W1-25：发布请求已使用 strict platform options；TikTok Direct Post v2、Shopify Admin GraphQL `2026-07`、consume 前 read-only preflight、strict durable `publish-receipt.v1`、tenant-bound attempt readback、receipt-only legacy status 和 canonical default-off env 已按批准规格实现。Focused `885 passed`、本地 PG18 compat/rollback/re-upgrade/fresh-init 各阶段 `2/2`、backend `3585 passed, 9 skipped, 14 deselected`、frontend `67 files/390 tests` 与 build 均通过。后续独立 Codex 审查完成，两个前端建议经规格核验为有意的 fail-closed/W5 UI deferred 边界，`accepted_actionable_findings=0`。生产、真实 credential/connector/status、live publish/reconciliation 均未验收。
- [ ] `blocked_external` W1-26：真实 sandbox/production publish 需要平台凭证、单 post 授权、删除/回滚方案和人工验收记录。

### 3.6 成本账本与预算

- [x] `completed_local / independent_review=true` W1-27：cost ledger 已迁移到 PostgreSQL/SQLite durable repository，绑定 tenant/job/attempt/provider/model；DeepSeek、SiliconFlow TTS、PoYo GPT Image 2 与 Seedance 2 均接入 reserve/settlement，并通过 Task 10 全量 recovery、migration、backup、frontend 与静态门。
- [x] `completed_local / independent_review=true` W1-28：LLM exact token usage、TTS strict provider-input UTF-8 bytes、image unit 与 video task/seconds 计费事实均有本地账本合同；provider `311 passed`、affected regression `467 passed`、backend/frontend/OpenAPI 全量门通过。
- [x] `completed_local / independent_review=true` W1-29：canonical provider paths 统一为单次付费 attempt、`max_retries=0`、ambiguous/accounting-error 保留与无自动恢复；当时的 16-table recovery、PG18 migration lifecycle、SQLite parity 与 schema-first runbooks 已同步，后续 W3-09 已将固定表清单升级为动态发现。
- [x] `completed_local / independent_review=true` W1-30：provider submit 前原子预算预留、失败释放、重启后 hard cap、finite server-owned scopes 与 regeneration epoch 已通过 Task 5–9 独立复核；Task 10 full gate 与最终独立复核 `PASS / APPROVE`, `accepted_actionable_findings=0`。
- [x] `retired_after_consumed_attempt` W1-31：2026-07-19 的唯一授权 mutation 返回 HTTP 403 且未重试；authority 已消费，账单对账不再是发布门禁。2026-07-20 起所有 W1-31 execute 入口均在 provider client 构造前永久 fail-closed；历史 ledger 只读保留，禁止复用或自动补跑。

## 4. Wave 2 — 运行正确性与数据一致性

### 4.1 生命周期与错误语义

- [ ] `in_progress` W2-01：当前 no-media/bounded 与 Fast full-media 已按 required artifact/error 真值投影；S1–S5 unrestricted full-media 的全步骤/全 artifact 成功推导仍未统一，不能标完成。
- [ ] `in_progress` W2-02：bounded/no-media 已统一为 `completed_bounded` 且不冒充 full success；全仓 fixture 的 `simulated=true` 语义尚未闭合。
- [ ] `in_progress` W2-03：S1 broad replay、当前 exact profiles、Fast fallback/provider-attempt 错误语义已有统一回归；所有 unrestricted full-media provider step 的付费后异常仍待覆盖。
- [ ] `in_progress` W2-04：StageProgress、Fast 和 OneShot 已支持 full/bounded/error 三态，bounded media 可见且明确不可发布/交付；其余 degraded/pending-review 恢复动作仍待全 UI 统一。

### 4.2 PostgreSQL、migration 与 readiness

- [ ] `pending_local` W2-05：production 配置 DATABASE_URL 后连接或初始化异常必须 fail-fast；SQLite fallback 仅 development/test 显式开启。
- [ ] `pending_local` W2-06：拆分 liveness/readiness；PG/migration/required tables 异常使 readiness 非 2xx，Docker health 使用 readiness。
- [ ] `pending_local` W2-07：修复被吞掉的 Alembic exception/logging，保留脱敏根因。
- [ ] `pending_local` W2-08：定义 PostgreSQL 18 canonical bootstrap，空库和历史库均可达到同一 migration head。
- [ ] `pending_local` W2-09：CI/disposable PG18 验证 fresh bootstrap、upgrade 和 required schema，不访问生产数据库。

### 4.3 State、quality 与 provider keys

- [ ] `in_progress` W2-10：`regenerate_chain`、`soft_degraded_reasons` 等字段已进入 init SQL、repository、filesystem/fake-PG save/load 与场景 status projection；generic API contract 和 W2-11 的 SQLite/disposable PG18 parity 仍未完成。
- [ ] `pending_local` W2-11：filesystem、SQLite、fake PG row、disposable PG18 round-trip 完全一致。
- [ ] `pending_local` W2-12：把 quality-score rewind 改为有界状态机；真实执行序列重新运行 upstream 后才能进入 consumer。
- [ ] `pending_local` W2-13：GPTImageClient、ElevenLabsClient 等全部使用 request-scoped provider key；双租户 fake transport 验证无串扰。

### 4.4 前端场景正确性

- [ ] `pending_local` W2-14：StageProgress 从后端 canonical `step_order`/status 判断完成，S4 thumbnails 后不得提前完成。
- [ ] `pending_local` W2-15：Gate polling 静止、timeout 和 polling exception 均 fail-closed，显示可重试状态，不自动推进 Gate。
- [ ] `pending_local` W2-16：S5 GuidedCard 支持六文件/六素材选择、真实 drag/drop、键盘操作和可见错误。
- [ ] `pending_local` W2-17：Review/Completion 移动布局、focus-visible、reduced-motion 和关键 admin i18n 建立 UI-only gate。

## 5. Wave 3 — 可复现构建、可观测性、灾备与部署

### 5.1 依赖、解释器与类型门

- [ ] `pending_local` W3-01：选择并固化生产 Python 版本；CI 在相同版本和完整生产 dependency set 上运行关键测试/import/health。
- [ ] `pending_local` W3-02：让 Docker/CI 消费 canonical lock；禁止 `requirements.txt >=` 在同 SHA 上产生漂移镜像。
- [ ] `pending_local` W3-03：修复 Pyright `executionEnvironments` 配置，增加真实 `make typecheck` target 和 CI gate；逐模块消除可信错误。
- [ ] `pending_local` W3-04：增加 pip/npm/image vulnerability scan；Dependabot security updates 和 alerts 由 owner 开启并记录状态。

### 5.2 Prometheus、Grafana 与通知

- [ ] `pending_local` W3-05：使 alert/dashboard 查询与 exporter 指标名、label 和 status 枚举一致。
- [ ] `pending_local` W3-06：用 `promtool` 和查询合同覆盖所有 rule；不存在指标必须使测试红。
- [ ] `pending_local` W3-07：仓库管理 Prometheus/Alertmanager，或记录外部 scrape/notification 的可验证配置合同。
- [ ] `blocked_external` W3-08：合成 5xx/provider failure 触发真实通知并验证恢复通知，需要通知渠道授权。

### 5.3 Off-host DR

- [x] `completed_local` W3-09：逻辑备份/恢复动态发现 public base tables，安全处理标识符与 FK 拓扑；未知边、重复表、环和 dump 中不存在的目标表 fail-closed。focused contract `154 passed`，并在 disposable PostgreSQL 18 的旧三表 schema 上完成实际 dump/restore/parity（3 tables / 3 rows，Alembic revision 一致）。
- [ ] `pending_local` W3-10：manifest 记录 Git SHA、migration head、source hash、image digest、row/file counts 和 checksums。
- [ ] `pending_local` W3-11：实现加密 off-host adapter、dry-run 和 mock object-store tests；本地日志不输出凭证。
- [ ] `blocked_external` W3-12：配置 versioned/immutable bucket、KMS 和 retention，需要基础设施 owner 授权。
- [ ] `blocked_external` W3-13：模拟 Lighthouse 主机不可用，从 off-host 副本恢复 PG18 与媒体并核对 parity。

### 5.4 Atomic deploy 与 provenance

- [ ] `implementation_complete_local` W3-14：workflow 已构建/test/scan SHA-tagged backend/frontend/rendering images并输出 digest、SBOM、scan 与 exact archive；本地 workflow/compose 合约通过，真实 GitHub run 与 artifact 尚待 versioned source。
- [ ] `implementation_complete_local` W3-15：release compose 无 live source/`.next` bind mount，source 进入不可覆盖的 versioned release；应用在维护窗口内切换，共享 nginx/portal-auth 不重建，只备份、校验并 reload AI Video location snippet。尚未 live deploy，不是 zero-downtime。
- [x] `completed_local` W3-16：canonical wrapper 默认 dry-run，非法 `DRY_RUN` 在 SSH/key 检查前立即退出；dry/live 都强制 clean、同步 `origin/main` 的 `main`，live 还要求 `RELEASE_SOURCE_SHA` 精确匹配 reviewed HEAD。focused deploy contract `39 passed`、bash syntax 与 scoped diff clean；尚未执行 rsync 或 deploy。
- [ ] `implementation_complete_local` W3-17：tag/workflow dispatch 必须精确等于实时 `origin/main` tip，SSH 只接受 pinned known-hosts；无生产 secret 的 restricted dry-run 与 deletion artifact 位于 live approval 之前。真实 GitHub Environment/secret/run 尚未验证。
- [x] `completed_local` W3-18：rendering health 只有 Remotion/ffmpeg/Chromium 全部 ready 才返回 200；provider-backed smoke 只接受 200，500 不再作为业务成功；聚焦合约已包含在 `154 passed`。
- [ ] `blocked_external` W3-19：下一次 no-token live deploy 验证 wrapper `exit=0` 和独立 L3 acceptance，需精确部署授权。

## 6. Wave 4 — 透明度、C2PA、文档与体验

### 6.1 透明度与 C2PA

- [ ] `pending_local` W4-01：定义所有 AI 文本、图片、音频、视频的 transparency sidecar schema 和 provenance chain。
- [ ] `pending_local` W4-02：UI、下载包、publish metadata 显示 AI-generated label，保留人工编辑与来源记录。
- [ ] `pending_local` W4-03：选择并 pin 当前 c2pa-python，按官方 `Signer`/`Builder.sign_file` API 实现，不使用已漂移接口。
- [ ] `pending_local` W4-04：Fast/S1–S5 所有 image/video producer 进入同一 signing/verification boundary。
- [ ] `pending_local` W4-05：策略要求签名时缺 SDK/证书/签名/独立验证一律禁止 publish/delivery；非 EU/local draft 可按明确策略保留 unsigned pending-review。
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

- [ ] `pending_local` W5-01：为 Fast/S1–S5 建立参数化 no-provider contract：tenant、safety policy、step order、artifact disposition、audit、transparency。
- [ ] `pending_local` W5-02：建立 single-submit L4 plan generator，逐场景绑定预算、sample、retry=0、job cap、pending-review-only 和停止条件。
- [ ] `pending_local` W5-03：建立 HU-03 人工 rubric record 和 brand/source/rights review record。

### 7.2 场景切片

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
