#!/usr/bin/env bash
# Run S1-S5 scenario regression without external provider calls.

set -euo pipefail

export API_KEY="${API_KEY:-test-api-key-for-pytest}"
export PYTEST_INCLUDE_HERMETIC_SLOW="${PYTEST_INCLUDE_HERMETIC_SLOW:-1}"

export DEEPSEEK_API_KEY=""
export POYO_API_KEY=""
export SEEDANCE_API_KEY=""
export SILICONFLOW_API_KEY=""
export ELEVENLABS_API_KEY=""
export TIKTOK_ACCESS_TOKEN=""
export TIKTOK_OPEN_ID=""
export SHOPIFY_STORE_URL=""
export SHOPIFY_ADMIN_TOKEN=""
export SUPABASE_URL=""
export SUPABASE_SERVICE_KEY=""

python -m pytest \
  tests/test_s1_e2e.py \
  tests/test_s2_e2e.py \
  tests/test_s2_deprecated_shim_boundary.py \
  tests/test_s3_e2e.py \
  tests/test_s4_e2e.py \
  tests/test_s5_e2e.py \
  tests/test_gate_scenario_configs.py \
  tests/test_scenario_step_regenerate_router.py \
  tests/test_continuity_storyboard_grid.py \
  tests/test_candidate_scorer_continuity.py \
  tests/test_s1_continuity_pipeline.py \
  tests/test_pipeline_degradation_chain.py \
  tests/test_fault_injection.py \
  --tb=short \
  -q \
  "$@"
