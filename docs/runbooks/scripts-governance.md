---
title: Scripts directory governance
doc_type: workflow
module: project
topic: scripts-governance
status: stable
created: 2026-06-01
updated: 2026-08-01
owner: self
source: human+ai
---

# Scripts directory governance

## 1. 目标

`scripts/` 只保留可复用、可解释、可审计的项目脚本。一次性修复、机器同步、provider 探测、历史 E2E 工具必须被显式分类，禁止默认 CI、部署或 hermetic regression 隐式调用。

治理契约在 `configs/scripts-governance-contract.json`。`scripts/**` 下所有 Python
与 shell 文件都进入文件系统递归治理，包括 tracked、untracked、ignored 和 nested
文件；只排除 `__pycache__`/bytecode。新增、迁移或归档前先更新契约与门禁。

## 2. 分类规则

- `active_reusable_scripts`：稳定可复用脚本，允许被文档或 CI 明确引用。
- `manual_deploy_scripts`：生产备份、迁移、发布、同步类脚本，只允许人工显式执行。
- `provider_probe_scripts`：可能访问 poyo.ai 或其他 provider 的脚本，默认不允许 CI、部署、无 token smoke 调用。
- `legacy_one_off_scripts`：历史一次性修复或同步脚本，保留但视为 `archive_candidate`。
- `historical_e2e_scripts`：旧 E2E 工具，不能替代当前 `tests/` 和 hermetic regression。
- `generated_artifact_policies`：`scripts/__pycache__/**`、`scripts/**/*.pyc` 是生成产物，状态为 `cleanup_requires_confirmation`；本轮不直接删除，后续清理前先确认。

## 3. 当前分类清单

### active_reusable_scripts

| path | status |
| --- | --- |
| `scripts/check_openapi_types_drift.py` | active_reusable |
| `scripts/check_step_order_consistency.py` | active_reusable |
| `scripts/project_version.py` | active_reusable |
| `scripts/check_pyright_ratchet.py` | active_reusable |
| `scripts/backup_manifest.py` | active_reusable |
| `scripts/brand_review_audit.py` | active_reusable |
| `scripts/brand_token_intake.py` | active_reusable |
| `scripts/build_authorized_live_approval_record.py` | active_reusable |
| `scripts/build_authorized_live_smoke_packet.py` | active_reusable |
| `scripts/build_authorized_live_test_plan_readiness_report.py` | active_reusable |
| `scripts/build_pending_review_asset_packet.py` | active_reusable |
| `scripts/build_pending_review_decision_record.py` | active_reusable |
| `scripts/build_provider_account_readiness_record.py` | active_reusable |
| `scripts/build_w5_acceptance_plan.py` | active_reusable |
| `scripts/build_w5_fast_runtime_binding.py` | active_reusable |
| `scripts/check_w5_fast_readiness.py` | active_reusable |
| `scripts/build_w1_31_billing_approval.py` | active_reusable |
| `scripts/w1_31_provider_billing_reconciliation.py` | active_reusable |
| `scripts/commercial_token_smoke_preflight.py` | active_reusable |
| `scripts/l4c_token_smoke_plan.py` | active_reusable |
| `scripts/create_admin.py` | active_reusable |
| `scripts/dev_start.py` | active_reusable |
| `scripts/generate_portfolio_posters.py` | active_reusable |
| `scripts/generate_portfolio_thumbnails.py` | active_reusable |
| `scripts/no_token_commercial_benchmark.py` | active_reusable |
| `scripts/monitoring_fixture_receiver.py` | active_reusable |
| `scripts/production_non_token_e2e_check.py` | active_reusable |
| `scripts/production_readonly_log_gate.py` | active_reusable |
| `scripts/portfolio_index.py` | active_reusable |
| `scripts/portfolio_thumbnail_coverage.py` | active_reusable |
| `scripts/prepare_demo_cache.py` | active_reusable |
| `scripts/read_w1_31_billing_ledger.py` | active_reusable |
| `scripts/refresh_brand_assets.sh` | active_reusable |
| `scripts/run_s1_s5_hermetic_regression.sh` | active_reusable |
| `scripts/scrape_momcozy.py` | active_reusable |
| `scripts/start_api.sh` | active_reusable |
| `scripts/start_backend.sh` | active_reusable |

### manual_deploy_scripts

| path | status |
| --- | --- |
| `scripts/bootstrap_postgres.py` | manual_deploy_only |
| `scripts/backup_production.sh` | manual_deploy_only |
| `scripts/install_backup_cron.sh` | manual_deploy_only |
| `scripts/offhost_backup.py` | manual_deploy_only |
| `scripts/pg_dump_logical.py` | manual_deploy_only |
| `scripts/pg_restore_logical.py` | manual_deploy_only |
| `scripts/restore_backup_database.sh` | manual_deploy_only |
| `scripts/verify_restored_database.py` | manual_deploy_only |
| `scripts/phase0_watchdog.sh` | manual_deploy_only |
| `scripts/release_finalize_v0.4.0.sh` | manual_deploy_only |
| `scripts/run_alembic_upgrade.sh` | manual_deploy_only |
| `scripts/deploy_alembic_gate.sh` | manual_deploy_only |

### provider_probe_scripts

| path | status |
| --- | --- |
| `scripts/w5_fast_one_shot_operator.py` | provider_probe |

### legacy_one_off_scripts

| path | status |
| --- | --- |
| `scripts/diagnose_apis.py` | archive_candidate |
| `scripts/render_video.py` | archive_candidate |
| `scripts/run_pipeline.py` | archive_candidate |
| `scripts/authorized_live_token_smoke_harness.py` | archive_candidate |
| `scripts/l4d_image_only_smoke.py` | archive_candidate |
| `scripts/l4d_paired_smoke.py` | archive_candidate |
| `scripts/l4d_video_only_smoke.py` | archive_candidate |
| `scripts/debug_poyo_403.py` | archive_candidate |
| `scripts/diagnose_poyo.py` | archive_candidate |
| `scripts/discover_poyo_models.py` | archive_candidate |
| `scripts/probe_sora2pro.py` | archive_candidate |
| `scripts/p2_recharge_smoke_checklist.py` | archive_candidate |
| `scripts/release_smoke_v0.4.0.sh` | archive_candidate |
| `scripts/run_s1_video_now.py` | archive_candidate |
| `scripts/run_s1_video.py` | archive_candidate |
| `scripts/e2e_influencer_remix.py` | archive_candidate |
| `scripts/e2e_verify_distribution.py` | archive_candidate |
| `scripts/run_5scenario_e2e.py` | archive_candidate |
| `scripts/run_s1_e2e.py` | archive_candidate |

### historical_e2e_scripts

| path | status |
| --- | --- |
No current scripts are classified as `historical_e2e`; executable historical
mutation runners have been converted to fail-closed `archive_candidate` stubs.

## 4. 执行边界

新增脚本前先判断能否并入现有脚本。新脚本必须有稳定用途名，不能使用 `fix`、`patch`、`overwrite`、`bugfix`、`phase`、`test_`、`_v2`、`_now` 作为核心语义，除非同时被契约标记为非 active。

`provider_probe_scripts` 当前只允许 `scripts/w5_fast_one_shot_operator.py`。
它必须绑定全新的 W5 exact activation/runtime binding、USD-nanos 预算、单次消费标记、
幂等键和 retry-zero 策略。充值、key 或通用确认变量不能授权任何其他脚本。
默认 CI、`Makefile`、Lighthouse deploy、`run_s1_s5_hermetic_regression.sh` 不得调用它。

旧版 Lighthouse 双向同步、一次性 patch/fix/phase/sync 源码已从工作树删除，历史内容只由
Git history 保存。`release_smoke_v0.4.0.sh` 仅保留无条件 fail-closed 兼容 stub。
当前执行入口不得调用任何归档候选；生产操作统一从
`docs/runbooks/production-operations.md` 进入。

`scripts/backup_production.sh` 与 `scripts/install_backup_cron.sh` 都属于生产写操作。Lighthouse rsync 会把普通文件模式统一为 `0644`，所以 cron 与人工命令必须显式使用 `/bin/bash` 调用，不能依赖 executable bit。安装器把执行文件复制到 root-owned 的 `/usr/local/libexec/ai-video-backup/`，常规重跑只替换带 `ai-video-production-backup` marker 的行；发现指向 current source、历史 `/opt/ai-video/scripts/backup_production.sh` 或 root-owned runtime 的旧无 marker 行时必须显式设置 `MIGRATE_LEGACY=1`，精确移除这些 AI Video job，并始终保留其他 cron 任务。

安装器的 `MODE=verify` 是只读运行时漂移门禁：它逐字节比较 reviewed backup、logical
dump、canonical manifest 三份 `/opt/ai-video/current/scripts/` 源文件与 root-owned
runtime，拒绝符号链接、非 root owner/group 和模式漂移，并要求唯一 managed cron 行和
预期命令完全一致；它不复制文件、不改 crontab、日志或 lock。默认安装模式完成写入后也
运行同一校验，未得到 `backup_runtime_verification=passed` 不得声称 runtime 安装完成。

`scripts/production_readonly_log_gate.py` 只做本地 backend log / summary 回放，不创建 key、不访问生产、不调用 provider。它用于 L4D/L4E 这类生产只读回归的日志判定：允许 `GET /portfolio` 和本地健康检查噪音（`127.0.0.1 /health`、当前 renderer UDS 的 `http://rendering/health` 日志；为历史证据回放兼容退役的 `rendering:3001/health` 形式），继续禁止外部 health/admin/media 请求、scenario/Fast submit、provider、publish、delivery 和 approved brand token 相关日志。

`legacy_one_off_scripts` 只允许保留无条件 fail-closed 的兼容 stub，并且配置路径集合
必须与工作树中带统一 retirement marker 的 stub 集合完全相等。每个 stub 在敌意确认变量
与伪凭据下都必须保持不可执行、无网络并返回 `2`。可执行历史源码不得迁移到工作树内的
`archive/`；历史内容由 Git history 保存。删除或批量重命名前仍必须先列出 diff 和影响范围，
并获得确认。

`generated_artifact_policies` 命中的文件可以清理，但清理动作属于目录治理变更，状态是 `cleanup_requires_confirmation`，不在普通 TODO 中隐式执行。
