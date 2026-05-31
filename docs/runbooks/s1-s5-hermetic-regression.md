---
title: S1-S5 Hermetic Regression Runbook
doc_type: workflow
module: testing
topic: s1-s5-hermetic-regression
status: stable
created: 2026-05-31
updated: 2026-05-31
owner: self
source: human+ai
---

# S1-S5 Hermetic Regression Runbook

## Purpose

Use this command before recharge or before risky workflow edits. It validates S1-S5 scenario logic, gate configuration, continuity utilities and degradation paths without calling POYO, Seedance, DeepSeek, SiliconFlow, TikTok, Shopify or Supabase.

## Command

```bash
make test-hermetic-scenarios
```

Equivalent direct command:

```bash
bash scripts/run_s1_s5_hermetic_regression.sh
```

Pass extra pytest flags after the script when needed:

```bash
bash scripts/run_s1_s5_hermetic_regression.sh --timeout=60
```

## Token Boundary

The script explicitly clears external provider and publishing credentials:

- `DEEPSEEK_API_KEY`
- `POYO_API_KEY`
- `SEEDANCE_API_KEY`
- `SILICONFLOW_API_KEY`
- `ELEVENLABS_API_KEY`
- `TIKTOK_ACCESS_TOKEN`
- `SHOPIFY_ADMIN_TOKEN`
- `SUPABASE_SERVICE_KEY`

Do not add production URLs, `RUN_TOKEN_SMOKE=1`, curl commands or scenario submit smoke calls to this script. Real generation remains P2 after POYO recharge.

## Covered Files

The command currently covers:

- `tests/test_s1_e2e.py`
- `tests/test_s2_e2e.py`
- `tests/test_s2_deprecated_shim_boundary.py`
- `tests/test_s3_e2e.py`
- `tests/test_s4_e2e.py`
- `tests/test_s5_e2e.py`
- `tests/test_gate_scenario_configs.py`
- `tests/test_scenario_step_regenerate_router.py`
- `tests/test_continuity_storyboard_grid.py`
- `tests/test_candidate_scorer_continuity.py`
- `tests/test_s1_continuity_pipeline.py`
- `tests/test_pipeline_degradation_chain.py`
- `tests/test_fault_injection.py`
