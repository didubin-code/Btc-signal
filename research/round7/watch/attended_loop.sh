#!/bin/bash
# Attended-window loop: one window_check every INTERVAL s for MINUTES minutes; exits 3 at once when FLAG appears (so the session is
# re-invoked immediately), 0 at the end. usage: attended_loop.sh <minutes> <interval s> <sha> <release> <mode> <build-from-ms> <out dir>
MIN=$1; INT=$2; shift 2; END=$(( $(date +%s) + MIN*60 )); OUT=${5}
rm -f "$OUT/FLAG"
while [ $(date +%s) -lt $END ]; do
  bash "$(dirname "$0")/window_check.sh" "$@" || { echo "FLAG raised at $(date -u +%FT%TZ): loop exits for evaluation"; exit 3; }
  python3 -I -c "import time; time.sleep($INT)"
done
echo "attended loop finished at $(date -u +%FT%TZ) with no flag"
