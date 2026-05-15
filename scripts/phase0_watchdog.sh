#!/usr/bin/env bash
# Phase 0 24h watchdog — runs hourly via cron, alerts when 3 SOP metrics breach threshold.
#
# Metrics tracked (per deploy plan §五):
#   1. empty final_video count       — silent assemble failure / partial_artifacts misjudge / Phase 0 #1 leak
#   2. heuristic scoring count       — gpt-4o vision degradation
#   3. stuck run count               — budget #2 / state loss #1 / background interruption
#
# Output: appends one line per hour to /var/log/phase0_watchdog.log
# Alert:  also writes to /var/log/phase0_watchdog_alerts.log if any threshold breached
#
# Install:
#   sudo cp /opt/ai-video/scripts/phase0_watchdog.sh /usr/local/bin/phase0_watchdog.sh
#   sudo chmod +x /usr/local/bin/phase0_watchdog.sh
#   echo "0 * * * * /usr/local/bin/phase0_watchdog.sh" | sudo tee -a /etc/cron.d/phase0_watchdog
#
# Uninstall:
#   sudo rm /etc/cron.d/phase0_watchdog /usr/local/bin/phase0_watchdog.sh /var/log/phase0_watchdog*.log

set -euo pipefail

LOG_FILE="/var/log/phase0_watchdog.log"
ALERT_FILE="/var/log/phase0_watchdog_alerts.log"

# Thresholds (SOP §五)
THRESH_EMPTY=5       # > 5 empty final_video / hour = alert (the SOP says "> 5%", we approximate as count)
THRESH_HEURISTIC=10  # baseline empirical, tune after first 24h
THRESH_STUCK=2       # > 2 stuck runs / hour = alert

# Pull last 1h of backend logs
LOGS=$(sudo docker logs --since 1h ai_video_backend 2>&1 || true)

# Count occurrences (defensive: empty result -> 0)
EMPTY=$(echo "$LOGS" | grep -cE 'final_video_path[":= ]+""' || true)
HEUR=$(echo "$LOGS" | grep -cE 'heuristic.*[Tt]rue|heuristic_score' || true)
STUCK=$(echo "$LOGS" | grep -cE 'stuck|pending.*[0-9]{4}s|step status=pending' || true)
ERRORS=$(echo "$LOGS" | grep -cE 'pipeline_degraded.*[Tt]rue|HTTP 5[0-9][0-9]|Exception' || true)

TS=$(date -Iseconds)
LINE="[$TS] empty=$EMPTY heuristic=$HEUR stuck=$STUCK errors=$ERRORS"
echo "$LINE" | sudo tee -a "$LOG_FILE" > /dev/null

# Alert path
ALERT_REASONS=""
if [ "$EMPTY" -gt "$THRESH_EMPTY" ]; then
    ALERT_REASONS="$ALERT_REASONS empty=$EMPTY>${THRESH_EMPTY}"
fi
if [ "$HEUR" -gt "$THRESH_HEURISTIC" ]; then
    ALERT_REASONS="$ALERT_REASONS heuristic=$HEUR>${THRESH_HEURISTIC}"
fi
if [ "$STUCK" -gt "$THRESH_STUCK" ]; then
    ALERT_REASONS="$ALERT_REASONS stuck=$STUCK>${THRESH_STUCK}"
fi

if [ -n "$ALERT_REASONS" ]; then
    echo "[$TS] ALERT$ALERT_REASONS" | sudo tee -a "$ALERT_FILE" > /dev/null
    # Backend health snapshot for forensics
    HEALTH=$(curl -fsSk https://localhost/health 2>&1 | head -c 200 || echo "(health probe failed)")
    echo "[$TS] health: $HEALTH" | sudo tee -a "$ALERT_FILE" > /dev/null
fi
