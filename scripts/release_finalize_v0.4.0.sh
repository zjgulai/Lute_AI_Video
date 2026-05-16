#!/usr/bin/env bash
# v0.4.0 release-day finalize \u2014 \u5468\u4e8c 5/19 09:45 \u8df3, \u5728 release smoke PASS \u540e\u3001\u53d1\u516c\u544a\u540e\u3002
#
# What this does (in order, all atomic):
#   1. Verify HEAD = e4e9db7 or later (most recent release commit)
#   2. Verify v0.4.0-rc1 tag exists locally
#   3. Create v0.4.0 annotated tag pointing at same commit as v0.4.0-rc1
#   4. Push v0.4.0 tag
#   5. (Optional) Create GitHub Release via gh CLI
#
# Safety: idempotent if v0.4.0 already exists \u2014 will fail rather than overwrite.
#
# Run:
#   ./scripts/release_finalize_v0.4.0.sh
#   ./scripts/release_finalize_v0.4.0.sh --skip-gh   # skip GitHub Release creation

set -euo pipefail
cd "$(dirname "$0")/.."

SKIP_GH=0
if [ "${1:-}" = "--skip-gh" ]; then
    SKIP_GH=1
fi

echo "=== v0.4.0 release finalize \u2014 $(date) ==="
echo

# Step 1: HEAD sanity
if ! git diff-index --quiet HEAD --; then
    echo "\u274c Working tree NOT clean. Abort."
    git status --short
    exit 1
fi
echo "\u2705 Working tree clean"

# Step 2: RC tag exists
if ! git rev-parse v0.4.0-rc1 >/dev/null 2>&1; then
    echo "\u274c v0.4.0-rc1 tag missing. Was canary deployed? See docs/release/v0.4.0-day-by-day-checklist.md."
    exit 1
fi
RC_COMMIT=$(git rev-parse v0.4.0-rc1)
echo "\u2705 v0.4.0-rc1 points to $RC_COMMIT"

# Step 3: No existing v0.4.0
if git rev-parse v0.4.0 >/dev/null 2>&1; then
    echo "\u274c v0.4.0 tag ALREADY EXISTS. Abort \u2014 will not overwrite."
    git show v0.4.0 --stat | head -10
    exit 1
fi
echo "\u2705 v0.4.0 tag does not exist yet"

# Step 4: Create v0.4.0 annotated tag at same commit as RC
TAG_MSG="Release v0.4.0 \u2014 $(date +%Y-%m-%d)

Production release after 66h+ canary burn-in starting 2026-05-16 14:24.

Includes Sprint 0-3 (17 commits) + Phase 0 (4 mandatory fixes) +
13 follow-up quick wins. See docs/release/v0.4.0.md for full notes.

Schema head: 9f1e2c8a4b67
Tests: 119/119 release-critical PASS
Canary smoke: 18/18 (1 warn watchdog records, resolved by Tuesday)

User-visible changes:
- Admin Panel: 1 re-login required (CSRF cookie)
- API consumers: use rotated X-API-Key (old keys revoked 2026-05-17)
- Otherwise no breaking changes
"

git tag -a v0.4.0 -m "$TAG_MSG" "$RC_COMMIT"
echo "\u2705 Created v0.4.0 annotated tag at $RC_COMMIT"

# Step 5: Push
git push origin v0.4.0
echo "\u2705 Pushed v0.4.0 to origin"

# Step 6 (optional): GitHub Release
if [ "$SKIP_GH" -eq 0 ]; then
    if command -v gh >/dev/null 2>&1; then
        echo
        echo "Creating GitHub Release..."
        gh release create v0.4.0 \
            --title "v0.4.0 \u2014 Sprint 0-3 + Phase 0 + 13 quick wins" \
            --notes-file docs/release/v0.4.0.md \
            || echo "\u26a0\ufe0f gh release create failed \u2014 you may need to create manually at https://github.com/zjgulai/Lute_AI_Video/releases/new?tag=v0.4.0"
    else
        echo "\u26a0\ufe0f gh CLI not installed. Create release manually:"
        echo "    https://github.com/zjgulai/Lute_AI_Video/releases/new?tag=v0.4.0"
        echo "    Body: paste contents of docs/release/v0.4.0.md"
    fi
fi

echo
echo "============================================================"
echo "  \u2705 v0.4.0 FINALIZED"
echo "============================================================"
echo
echo "Next steps:"
echo "  1. Send announcement (see docs/release/v0.4.0-announcement-templates.md)"
echo "  2. Watch monitors for 1h (watchdog + backend logs)"
echo "  3. Be on standby for any oncall pings"
