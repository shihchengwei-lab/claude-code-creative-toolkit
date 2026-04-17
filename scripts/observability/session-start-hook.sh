#!/usr/bin/env bash
# Session-start hook — pushes observability digest on threshold crossing.
#
# Install as a Claude Code SessionStart hook. See docs/architecture.md §observability.
#
# Prints reminders to stdout when:
#   - Any pending refusal exists  (every session)
#   - Mechanism memory >= 5 entries AND not shown in last 7 days
#   - Gate events >= 50 entries   AND not shown in last 7 days
#
# Also sanity-checks that the installed pre-commit hook matches the tracked template.

set -uo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$REPO_ROOT" || exit 0

STATE_FILE=".git/saa-digest-last-shown.json"
NOW_EPOCH=$(date +%s)
WEEK=$((7 * 24 * 3600))

# ---- Pre-commit template health ----
TEMPLATE="scripts/git-hooks/pre-commit"
INSTALLED=".git/hooks/pre-commit"
if [ -f "$TEMPLATE" ] && [ -f "$INSTALLED" ]; then
  TEMPLATE_SHA=$(sha256sum "$TEMPLATE" 2>/dev/null | cut -d' ' -f1)
  INSTALLED_SHA=$(sha256sum "$INSTALLED" 2>/dev/null | cut -d' ' -f1)
  if [ -n "$TEMPLATE_SHA" ] && [ -n "$INSTALLED_SHA" ] \
     && [ "$TEMPLATE_SHA" != "$INSTALLED_SHA" ]; then
    echo "warn: .git/hooks/pre-commit differs from template"
    echo "      reinstall:  cp $TEMPLATE $INSTALLED && chmod +x $INSTALLED"
    echo ""
  fi
elif [ -f "$TEMPLATE" ] && [ ! -f "$INSTALLED" ]; then
  echo "warn: pre-commit hook not installed"
  echo "      install:  cp $TEMPLATE $INSTALLED && chmod +x $INSTALLED"
  echo ""
fi

# ---- Read last-shown timestamps ----
last_shown() {
  local key=$1
  [ -f "$STATE_FILE" ] || { echo "0"; return; }
  python -c "
import json,sys
try:
    d = json.load(open('$STATE_FILE'))
    print(d.get('$key', 0))
except Exception:
    print(0)
" 2>/dev/null || echo "0"
}

update_shown() {
  local key=$1
  local now=$2
  python -c "
import json
try:
    d = json.load(open('$STATE_FILE'))
except Exception:
    d = {}
d['$key'] = $now
json.dump(d, open('$STATE_FILE', 'w'))
" 2>/dev/null || true
}

# ---- Read config paths (via Python helper for YAML support) ----
read_cfg_path() {
  local key=$1
  python -c "
import sys
sys.path.insert(0, 'scripts')
from _config import load_config
cfg = load_config()
parts = '$key'.split('.')
val = cfg
for p in parts:
    val = val[p]
print(val)
" 2>/dev/null
}

REFUSAL_LOG=$(read_cfg_path "audit.refusal_log")
MECH_MEMORY=$(read_cfg_path "memory.mechanism_memory")
GATE_EVENTS=$(read_cfg_path "gate_events")

# ---- Pending refusals (always print if > 0) ----
if [ -n "$REFUSAL_LOG" ] && [ -f "$REFUSAL_LOG" ]; then
  PENDING=$(python -c "
import json
n = 0
for line in open('$REFUSAL_LOG'):
    line = line.strip()
    if not line: continue
    try:
        e = json.loads(line)
        if e.get('user_decision') is None:
            n += 1
    except: pass
print(n)
" 2>/dev/null || echo "0")
  if [ "$PENDING" -gt 0 ]; then
    echo "info: $PENDING pending refusal(s) awaiting resolution"
    echo "      review: python scripts/memory/refusal_status.py"
    echo ""
  fi
fi

# ---- Mechanism memory threshold (>= 5, show once per 7d) ----
# Using `wc -l` not `grep -c .` — on an empty file grep prints "0" AND exits 1,
# causing `|| echo 0` to fire and produce "0\n0" in command substitution,
# which then fails integer comparison.
if [ -n "$MECH_MEMORY" ] && [ -f "$MECH_MEMORY" ]; then
  MECH_COUNT=$(wc -l < "$MECH_MEMORY" 2>/dev/null || echo 0)
  MECH_COUNT=${MECH_COUNT// /}
  if [ "$MECH_COUNT" -ge 5 ] 2>/dev/null; then
    LAST=$(last_shown "mechanism")
    if [ $((NOW_EPOCH - LAST)) -ge "$WEEK" ]; then
      echo "info: mechanism memory has $MECH_COUNT entries"
      echo "      digest: python scripts/observability/health_digest.py"
      echo ""
      update_shown "mechanism" "$NOW_EPOCH"
    fi
  fi
fi

# ---- Gate events threshold (>= 50, show once per 7d) ----
if [ -n "$GATE_EVENTS" ] && [ -f "$GATE_EVENTS" ]; then
  GATE_COUNT=$(wc -l < "$GATE_EVENTS" 2>/dev/null || echo 0)
  GATE_COUNT=${GATE_COUNT// /}
  if [ "$GATE_COUNT" -ge 50 ] 2>/dev/null; then
    LAST=$(last_shown "gate_events")
    if [ $((NOW_EPOCH - LAST)) -ge "$WEEK" ]; then
      echo "info: gate events has $GATE_COUNT fail records"
      echo "      digest: python scripts/observability/health_digest.py"
      echo ""
      update_shown "gate_events" "$NOW_EPOCH"
    fi
  fi
fi

exit 0
