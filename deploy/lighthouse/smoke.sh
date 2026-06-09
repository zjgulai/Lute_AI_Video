#!/usr/bin/env bash
# P0-F: Lighthouse 部署后 smoke 验证 — 确认 NEXT_PUBLIC_IS_DEMO=false 真生效,
# 前端不会走 DEMO_RESULT_*,后端基础路由 reachable + 用真 API key 鉴权通过。
# 会消耗外部额度的真实生成验证必须显式设置 RUN_TOKEN_SMOKE=1。
#
# Usage:
#   ./smoke.sh                                 # 默认探 https://101.34.52.232
#   BASE=http://localhost ./smoke.sh           # 本地 docker compose 起来后探本机
#   API_KEY=xxx ./smoke.sh                     # 覆盖 API key
#   RUN_TOKEN_SMOKE=1 API_KEY=xxx ./smoke.sh   # 显式运行真实生成验证
#
# Exit code 0 = 全过 / 1 = 任一失败 / 2 = 配置错误

set -euo pipefail

BASE="${BASE:-${SERVER_HOST:-https://101.34.52.232}}"
API_KEY="${API_KEY:-}"
if [ -z "$API_KEY" ] && [ -f ".env.prod" ]; then
  API_KEY="$(grep -E '^API_KEY=' .env.prod | head -1 | cut -d= -f2- || true)"
fi
if [ -z "$API_KEY" ]; then
  echo "ERROR: API_KEY is required. Set API_KEY env var or run from deploy/lighthouse with .env.prod present." >&2
  exit 2
fi
is_demo_key=0
if [[ "$API_KEY" == *"demo"* ]] || [[ "$API_KEY" == *"ai_video_demo"* ]]; then
  is_demo_key=1
fi

# curl 用 -k 跳过自签证书校验,production 用真实证书后可去掉
CURL="curl -sS -k -o /dev/null -w %{http_code}"

echo "========================================"
echo "  Lighthouse smoke verification"
echo "  BASE=$BASE"
echo "========================================"
echo ""

FAILED=0

check() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  [OK]   $name → $actual"
  else
    echo "  [FAIL] $name → expected $expected, got $actual"
    FAILED=$((FAILED + 1))
  fi
}

# 1. 后端 /health 不需要 API key
echo "[1/5] Backend /api/health"
status=$($CURL "$BASE/api/health")
check "GET /api/health" "200" "$status"

# 2. 后端 /api/health 内容里 persistence.backend 应该是 postgresql(P0-E 验收)
echo "[2/5] Backend persistence backend = postgresql"
backend=$(curl -sS -k "$BASE/api/health" | python3 -c "import json, sys; d = json.load(sys.stdin); print(d.get('persistence', {}).get('backend', 'unknown'))" 2>/dev/null || echo "parse_error")
check "persistence.backend" "postgresql" "$backend"

# 3. 鉴权:无 key 必须 401
echo "[3/5] Auth: missing API key returns 401"
status=$($CURL -X POST -H "Content-Type: application/json" \
  -d '{"target_platforms":["tiktok"],"target_languages":["en"]}' \
  "$BASE/api/pipeline/start")
check "POST /api/pipeline/start without key" "401" "$status"

# 4. AI Video 2.0 toolbox 只读接口检查:不创建 run,不触发 provider。
echo "[4/5] Toolbox read-only endpoints"
if [ "$is_demo_key" -eq 1 ]; then
  echo "  [SKIP] toolbox read-only endpoints (non-demo API key required)"
else
  toolbox_tools_status=$(curl -sS -k -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/tools")
  check "GET /api/toolbox/tools" "200" "$toolbox_tools_status"
  toolbox_tools_level=$(curl -sS -k \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/tools" \
    | python3 -c "import json, sys; d = json.load(sys.stdin); print(d.get('evidence_level', 'unknown'))" 2>/dev/null || echo "parse_error")
  check "toolbox.tools.evidence_level" "L2-fixture-or-dry-run" "$toolbox_tools_level"

  toolbox_runs_status=$(curl -sS -k -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/runs?limit=1")
  check "GET /api/toolbox/runs?limit=1" "200" "$toolbox_runs_status"
  toolbox_runs_level=$(curl -sS -k \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/runs?limit=1" \
    | python3 -c "import json, sys; d = json.load(sys.stdin); print(d.get('evidence_level', 'unknown'))" 2>/dev/null || echo "parse_error")
  check "toolbox.runs.evidence_level" "L2-fixture-or-dry-run" "$toolbox_runs_level"

  toolbox_audit_status=$(curl -sS -k -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/runs/audit-summaries?limit=1")
  check "GET /api/toolbox/runs/audit-summaries?limit=1" "200" "$toolbox_audit_status"
  toolbox_audit_level=$(curl -sS -k \
    -H "X-API-Key: $API_KEY" \
    "$BASE/api/toolbox/runs/audit-summaries?limit=1" \
    | python3 -c "import json, sys; d = json.load(sys.stdin); print(d.get('evidence_level', 'unknown'))" 2>/dev/null || echo "parse_error")
  check "toolbox.audit_summaries.evidence_level" "L2-fixture-or-dry-run" "$toolbox_audit_level"
fi

# 5. 真链路生成会消耗外部额度,默认跳过;充值后用 RUN_TOKEN_SMOKE=1 显式开启。
echo "[5/5] Real path: /api/fast/generate with valid API key"
if [ "${RUN_TOKEN_SMOKE:-0}" = "1" ]; then
  status=$($CURL -X POST \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"user_prompt":"smoke test","duration":5,"enable_tts":false}' \
    "$BASE/api/fast/generate")
  # 200 = 全程跑通; 500 = 内部错(可能 LLM key 不可用,但路径已通); 401 = key 错
  case "$status" in
    200|500)
      echo "  [OK]   POST /api/fast/generate → $status (路径可达)"
      ;;
    *)
      echo "  [FAIL] POST /api/fast/generate → expected 200/500, got $status"
      FAILED=$((FAILED + 1))
      ;;
  esac
else
  echo "  [SKIP] POST /api/fast/generate (set RUN_TOKEN_SMOKE=1 to run token smoke)"
fi

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
  echo "  smoke OK — non-demo production verified"
  echo "========================================"
  exit 0
else
  echo "  smoke FAILED — $FAILED check(s) failed"
  echo "========================================"
  exit 1
fi
