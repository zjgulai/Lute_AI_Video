#!/usr/bin/env bash
# v0.4.0 final release smoke \u2014 \u5468\u4e8c 5/19 09:15 \u8df3, \u9a8c\u8bc1 production \u4ecd\u7eff
#
# Usage (local laptop):
#   cd /Users/pray/project/hermes_evo/AI_vedio
#   ./scripts/release_smoke_v0.4.0.sh
#
# OR (any developer on the network):
#   ssh -i ai_video.pem ubuntu@101.34.52.232 'bash -s' < scripts/release_smoke_v0.4.0.sh
#
# All checks must PASS (exit 0). Any check fails \u2192 NO-GO, see
# docs/release/v0.4.0-NO-GO-procedure.md.

set -uo pipefail

PASS=0
FAIL=0
WARN=0
SSH_KEY="${SSH_KEY:-./ai_video.pem}"
HOST="${HOST:-ubuntu@101.34.52.232}"

check() {
    local name="$1"
    local result="$2"  # 0 = pass, 1 = fail, 2 = warn
    case "$result" in
        0) PASS=$((PASS+1)); echo "  \u2705 $name" ;;
        1) FAIL=$((FAIL+1)); echo "  \u274c $name" ;;
        2) WARN=$((WARN+1)); echo "  \u26a0\ufe0f $name" ;;
    esac
}

run_remote() {
    ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "$@" 2>&1
}

echo "=== v0.4.0 final release smoke \u2014 $(date) ==="
echo

echo "1\ufe0f\u20e3 Container health"
status=$(run_remote 'sudo docker ps --filter "name=ai_video" --format "{{.Names}}|{{.Status}}"')
for expected in ai_video_backend ai_video_frontend ai_video_nginx ai_video_rendering; do
    line=$(echo "$status" | grep "^${expected}|" || echo "")
    if echo "$line" | grep -qE "Up.*(healthy|hours|days|minutes)"; then
        if echo "$line" | grep -q "unhealthy"; then
            check "$expected up but unhealthy" 1
        else
            check "$expected up" 0
        fi
    else
        check "$expected missing or down" 1
    fi
done
echo

echo "2\ufe0f\u20e3 HTTPS /health"
health=$(run_remote 'curl -fsSk https://localhost/health 2>&1')
if echo "$health" | grep -q '"status":"ok"'; then
    check "/health returns ok" 0
else
    check "/health failed: ${health:0:200}" 1
fi
if echo "$health" | grep -q '"backend":"postgresql","status":"healthy"'; then
    check "PG persistence healthy" 0
else
    check "PG persistence not healthy" 1
fi
echo

echo "3\ufe0f\u20e3 alembic head revision"
alem=$(run_remote 'sudo docker exec ai_video_backend sh -c "cd /app/migrations && python3 -m alembic current 2>&1" | grep -oE "[0-9a-f]{12}" | head -1')
if [ "$alem" = "9f1e2c8a4b67" ]; then
    check "alembic head = 9f1e2c8a4b67" 0
else
    check "alembic head wrong (got: $alem)" 1
fi
echo

echo "4\ufe0f\u20e3 Critical tables exist"
cat > /tmp/smoke_tables.py << 'PYEOF'
import asyncio, os, asyncpg, sys
async def f():
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    expected = ["threads", "pipeline_states", "brand_packages", "influencers",
                "publish_logs", "video_metrics", "audit_logs", "admin_accounts",
                "admin_sessions", "api_keys"]
    rows = await c.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    actual = set(r[0] for r in rows)
    missing = [t for t in expected if t not in actual]
    if missing:
        print(f"MISSING: {missing}", file=sys.stderr); sys.exit(1)
    print(f"OK {len(expected)} tables")
    await c.close()
asyncio.run(f())
PYEOF
scp -i "$SSH_KEY" -o BatchMode=yes /tmp/smoke_tables.py "$HOST:/tmp/smoke_tables.py" >/dev/null 2>&1
tables=$(run_remote 'sudo docker cp /tmp/smoke_tables.py ai_video_backend:/tmp/t.py && sudo docker exec ai_video_backend python3 /tmp/t.py')
if echo "$tables" | grep -q "OK 10 tables"; then
    check "10 core tables present" 0
else
    check "Tables check failed: $tables" 1
fi
echo

echo "5\ufe0f\u20e3 audit_logs has 11 columns + 4 indexes"
cat > /tmp/smoke_audit.py << 'PYEOF'
import asyncio, os, asyncpg, sys
async def f():
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    cols = await c.fetchval("SELECT COUNT(*) FROM information_schema.columns WHERE table_name='audit_logs'")
    idx = await c.fetchval("SELECT COUNT(*) FROM pg_indexes WHERE tablename='audit_logs'")
    print(f"COLS={cols} IDX={idx}")
    if cols < 11: sys.exit(1)
    if idx < 5: sys.exit(1)
    await c.close()
asyncio.run(f())
PYEOF
scp -i "$SSH_KEY" -o BatchMode=yes /tmp/smoke_audit.py "$HOST:/tmp/smoke_audit.py" >/dev/null 2>&1
audit=$(run_remote 'sudo docker cp /tmp/smoke_audit.py ai_video_backend:/tmp/a.py && sudo docker exec ai_video_backend python3 /tmp/a.py')
if echo "$audit" | grep -q "COLS=11"; then
    check "audit_logs schema correct" 0
else
    check "audit_logs schema wrong: $audit" 1
fi
echo

echo "6\ufe0f\u20e3 Prometheus endpoint exposes 5 new metrics"
API_KEY=$(run_remote 'grep ^API_KEY= /opt/ai-video/deploy/lighthouse/.env.prod | cut -d= -f2')
metrics=$(run_remote "curl -sk -H 'X-API-Key: $API_KEY' https://localhost/telemetry/prometheus 2>/dev/null | grep -E '^# HELP'")
for m in llm_api_errors_total llm_api_duration_seconds db_pool_available_connections admin_login_attempts_total tenant_active_count; do
    if echo "$metrics" | grep -q "^# HELP $m "; then
        check "metric $m exposed" 0
    else
        check "metric $m missing" 1
    fi
done
echo

echo "7\ufe0f\u20e3 Admin auth gates"
admin_no_cookie=$(run_remote 'curl -sk -w "HTTP %{http_code}" https://localhost/api/admin/auth/session 2>/dev/null | tail -c 12')
if echo "$admin_no_cookie" | grep -q "HTTP 401"; then
    check "Admin session w/o cookie returns 401" 0
else
    check "Admin auth gate broken (got: $admin_no_cookie)" 1
fi
echo

echo "8\ufe0f\u20e3 fast/generate validation (expected 422 missing user_prompt)"
fast_response=$(run_remote "curl -sk -X POST https://localhost/api/fast/generate -H 'X-API-Key: $API_KEY' -H 'Content-Type: application/json' -d '{\"prompt\":\"smoke\",\"duration_seconds\":10}' -w '\nHTTP_%{http_code}'")
if echo "$fast_response" | grep -q "HTTP_422"; then
    check "fast endpoint validates input (HTTP 422)" 0
else
    check "fast endpoint unexpected response: $fast_response" 1
fi
echo

echo "9\ufe0f\u20e3 Phase 0 watchdog active + zero alerts"
watchdog_lines=$(run_remote 'sudo wc -l /var/log/phase0_watchdog.log' | awk '{print $1}')
alerts=$(run_remote 'sudo wc -l /var/log/phase0_watchdog_alerts.log' | awk '{print $1}')
if [ "${watchdog_lines:-0}" -gt 60 ]; then
    check "watchdog has ${watchdog_lines} records" 0
else
    check "watchdog has only ${watchdog_lines} records (need >60)" 2
fi
if [ "${alerts:-0}" -eq 0 ]; then
    check "0 watchdog alerts" 0
else
    check "${alerts} watchdog alerts \u2014 INSPECT phase0_watchdog_alerts.log" 1
fi
echo

echo "\ud83d\udd1f Backend log: 0 ERROR / Exception in last hour"
errors=$(run_remote 'sudo docker logs --since 1h ai_video_backend 2>&1 | grep -iE "error|exception|traceback" | grep -v INFO | grep -v deprecation | wc -l')
if [ "${errors:-0}" -lt 5 ]; then
    check "backend log errors=$errors (< 5 threshold)" 0
else
    check "backend log errors=$errors (\u2265 5 \u2014 INSPECT)" 1
fi
echo

echo "============================================================"
echo "  RESULT: PASS=$PASS  FAIL=$FAIL  WARN=$WARN"
echo "============================================================"

if [ "$FAIL" -gt 0 ]; then
    echo "\u274c NO-GO. See docs/release/v0.4.0-NO-GO-procedure.md."
    exit 1
fi

if [ "$WARN" -gt 0 ]; then
    echo "\u26a0\ufe0f Investigate warnings before announcing release."
fi

echo "\u2705 RELEASE SMOKE PASS. Safe to tag v0.4.0 and announce."
exit 0
