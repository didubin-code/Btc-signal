#!/bin/bash
# One attended-window check (read-only GETs): identity via deploy_verify.sh, then the per-second rows served since the last check
# (/predictions?since=<cursor>&format=ndjson) judged by monitor_rules.py (the one evaluator). Writes one line to STATUS_WINDOW.txt and,
# on any failure, the file FLAG (the attended loop exits on it). usage: window_check.sh <expected sha> <expected release> <expected mode> <build-from-ms> <out dir>
EXP_SHA=$1; EXP_REL=$2; EXP_MODE=$3; BUILD_FROM=$4; OUT=$5; mkdir -p "$OUT/live_pred"; T=$(date -u +%Y%m%dT%H%M%SZ); D=$(dirname "$0")
V=$(bash "$D/deploy_verify.sh" "$EXP_SHA" "$EXP_REL" "$EXP_MODE" "$OUT/verify_runs" 2>&1 | tail -1)
CUR=$(cat "$OUT/pred_cursor" 2>/dev/null || echo 0)
code=$(curl -sS --max-time 30 -o "$OUT/live_pred/pred_$T.ndjson" -w '%{http_code}' "https://btc-pin-radar.onrender.com/predictions?since=$CUR&n=5000&format=ndjson")
python3 -I "$D/monitor_rules.py" --rows "$OUT/live_pred/pred_$T.ndjson" --build-from "$BUILD_FROM" --out "$OUT" --verify-line "$V" --http "$code" --stamp "$T"
