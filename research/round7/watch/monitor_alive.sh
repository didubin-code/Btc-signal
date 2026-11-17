#!/bin/bash
# Is the monitoring itself alive? Reports MONITORING UNAVAILABLE (never a clean pass) when the attended loop's last check is older than
# MAX_LOOP_S (default 180 s) or, after the window, the hourly watch heartbeat is older than 65 min. usage: monitor_alive.sh <out dir> [loop|hourly]
OUT=$1; MODE=${2:-loop}; NOW=$(date -u +%s); T=$(date -u +%FT%TZ)
if [ "$MODE" = "loop" ]; then
  F="$OUT/STATUS_WINDOW.txt"; if [ ! -s "$F" ]; then echo "$T MONITORING UNAVAILABLE: no window check has run"; exit 3; fi
  LAST=$(tail -1 "$F" | cut -c1-16); LS=$(date -u -d "${LAST:0:4}-${LAST:4:2}-${LAST:6:2}T${LAST:9:2}:${LAST:11:2}:${LAST:13:2}Z" +%s 2>/dev/null || echo 0); AGE=$((NOW-LS))
  if [ $AGE -gt ${MAX_LOOP_S:-180} ]; then echo "$T MONITORING UNAVAILABLE: last window check $AGE s ago (loop stopped or interrupted)"; exit 3; fi
  if [ -s "$OUT/FLAG" ]; then echo "$T FLAG PRESENT (last check $AGE s ago): $(tail -1 "$OUT/FLAG" | cut -c1-200)"; exit 4; fi
  echo "$T monitoring alive: last window check $AGE s ago"; exit 0
else
  H="$OUT/heartbeat.json"; if [ ! -s "$H" ]; then echo "$T MONITORING UNAVAILABLE: no hourly watch heartbeat"; exit 3; fi
  LS=$(python3 -I -c "import json,sys; print(int(json.load(open(sys.argv[1]))['last_run_ms']//1000))" "$H"); AGE=$((NOW-LS))
  if [ $AGE -gt 3900 ]; then echo "$T MONITORING UNAVAILABLE: hourly watch heartbeat $AGE s old (missed check)"; exit 3; fi
  echo "$T monitoring alive: hourly watch heartbeat $AGE s old"; exit 0
fi
