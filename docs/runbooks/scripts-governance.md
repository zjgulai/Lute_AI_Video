---
title: Scripts directory governance
doc_type: workflow
module: project
topic: scripts-governance
status: stable
created: 2026-06-01
updated: 2026-06-05
owner: self
source: human+ai
---

# Scripts directory governance

## 1. 目标

`scripts/` 只保留可复用、可解释、可审计的项目脚本。一次性修复、机器同步、provider 探测、历史 E2E 工具必须被显式分类，禁止默认 CI、部署或 hermetic regression 隐式调用。

治理契约在 `configs/scripts-governance-contract.json`。新增、迁移或归档脚本时，先更新契约，再运行 `tests/test_scripts_governance.py`。

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
| `scripts/brand_review_audit.py` | active_reusable |
| `scripts/brand_token_intake.py` | active_reusable |
| `scripts/commercial_token_smoke_preflight.py` | active_reusable |
| `scripts/create_admin.py` | active_reusable |
| `scripts/dev_start.py` | active_reusable |
| `scripts/diagnose_apis.py` | active_reusable |
| `scripts/generate_portfolio_posters.py` | active_reusable |
| `scripts/generate_portfolio_thumbnails.py` | active_reusable |
| `scripts/no_token_commercial_benchmark.py` | active_reusable |
| `scripts/p2_recharge_smoke_checklist.py` | active_reusable |
| `scripts/portfolio_index.py` | active_reusable |
| `scripts/portfolio_thumbnail_coverage.py` | active_reusable |
| `scripts/prepare_demo_cache.py` | active_reusable |
| `scripts/refresh_brand_assets.sh` | active_reusable |
| `scripts/render_video.py` | active_reusable |
| `scripts/run_pipeline.py` | active_reusable |
| `scripts/run_s1_s5_hermetic_regression.sh` | active_reusable |
| `scripts/run_s1_video.py` | active_reusable |
| `scripts/scrape_momcozy.py` | active_reusable |
| `scripts/start_api.sh` | active_reusable |
| `scripts/start_backend.sh` | active_reusable |

### manual_deploy_scripts

| path | status |
| --- | --- |
| `scripts/backup_production.sh` | manual_deploy_only |
| `scripts/pg_dump_logical.py` | manual_deploy_only |
| `scripts/pg_restore_logical.py` | manual_deploy_only |
| `scripts/phase0_watchdog.sh` | manual_deploy_only |
| `scripts/release_finalize_v0.4.0.sh` | manual_deploy_only |
| `scripts/release_smoke_v0.4.0.sh` | manual_deploy_only |
| `scripts/run_alembic_upgrade.sh` | manual_deploy_only |
| `scripts/sync_lighthouse_to_output.sh` | manual_deploy_only |
| `scripts/sync_output_to_lighthouse.sh` | manual_deploy_only |

### provider_probe_scripts

| path | status |
| --- | --- |
| `scripts/authorized_live_token_smoke_harness.py` | provider_probe |
| `scripts/debug_poyo_403.py` | provider_probe |
| `scripts/diagnose_poyo.py` | provider_probe |
| `scripts/discover_poyo_models.py` | provider_probe |
| `scripts/probe_sora2pro.py` | provider_probe |
| `scripts/test_poyo_all_media.py` | provider_probe |
| `scripts/test_poyo_image.py` | provider_probe |
| `scripts/test_poyo_image_models.py` | provider_probe |
| `scripts/test_poyo_music.py` | provider_probe |
| `scripts/test_poyo_music_detail.py` | provider_probe |
| `scripts/test_poyo_music_status.py` | provider_probe |
| `scripts/test_poyo_seedance.py` | provider_probe |
| `scripts/test_poyo_tts.py` | provider_probe |

### legacy_one_off_scripts

| path | status |
| --- | --- |
| `scripts/apply_fix_patch.py` | archive_candidate |
| `scripts/fix_page_mac.py` | archive_candidate |
| `scripts/fix_remotion.sh` | archive_candidate |
| `scripts/overwrite_fix.py` | archive_candidate |
| `scripts/patch_api_submit_review.py` | archive_candidate |
| `scripts/phase1_sync.py` | archive_candidate |
| `scripts/phase2_sync.py` | archive_candidate |
| `scripts/phase3_sync.py` | archive_candidate |
| `scripts/run_s1_video_now.py` | archive_candidate |
| `scripts/sync_brand_color.py` | archive_candidate |
| `scripts/sync_bugfix.py` | archive_candidate |
| `scripts/sync_bugfix_v2.py` | archive_candidate |
| `scripts/sync_p4.py` | archive_candidate |
| `scripts/sync_phase6.py` | archive_candidate |
| `scripts/sync_phase7.py` | archive_candidate |
| `scripts/sync_plan_to_mac.py` | archive_candidate |
| `scripts/sync_resume_fix.py` | archive_candidate |
| `scripts/sync_s1.py` | archive_candidate |

### historical_e2e_scripts

| path | status |
| --- | --- |
| `scripts/e2e_influencer_remix.py` | historical_e2e |
| `scripts/e2e_verify_distribution.py` | historical_e2e |
| `scripts/run_5scenario_e2e.py` | historical_e2e |
| `scripts/run_s1_e2e.py` | historical_e2e |
| `scripts/test_media_skills_e2e.py` | historical_e2e |
| `scripts/test_pipeline_quality.py` | historical_e2e |
| `scripts/test_s1_unified_e2e.py` | historical_e2e |

## 4. 执行边界

新增脚本前先判断能否并入现有脚本。新脚本必须有稳定用途名，不能使用 `fix`、`patch`、`overwrite`、`bugfix`、`phase`、`test_`、`_v2`、`_now` 作为核心语义，除非同时被契约标记为非 active。

`provider_probe_scripts` 只能在充值后、显式设置 key 和确认变量后运行。默认 CI、`Makefile`、Lighthouse deploy、`run_s1_s5_hermetic_regression.sh` 不得调用这些脚本。

`legacy_one_off_scripts` 的下一步是迁移到 `archive/scripts/` 或删除。迁移、删除、批量重命名前必须先列出 diff 和影响范围，并获得确认。

`generated_artifact_policies` 命中的文件可以清理，但清理动作属于目录治理变更，状态是 `cleanup_requires_confirmation`，不在普通 TODO 中隐式执行。
