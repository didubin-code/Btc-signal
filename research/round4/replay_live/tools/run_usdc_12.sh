#!/bin/bash
# usdc_12: the usdc_11 pipeline (replay_pub/tools/pr5_official.sh, function one()) reproduced verbatim for a new range, with
# only the paths and the --from/--to arguments changed. Engine, scripts, options (--venues proxy --proxy-dir usdc --warm 86400),
# post-processing chain (pr4_summarize -> gzip -> pr5_eval -> loser_min1 -> .done) are the same files and the same order.
# --to is 2026-11-15T00:15:00Z instead of the briefed 2026-11-16T00:45:00Z because data.binance.vision has not published the
# BTCUSDC 1s archives for 2026-11-15 and 2026-11-16 (HTTP 404 NoSuchKey at 2026-11-16 02:10 UTC); closes in [from, to) are scored,
# so the last scored close is 2026-11-15 00:00 UTC, the last one whose decision seconds are all covered by published prices.
set -u
SC=/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad; RP=$SC/incident_20261114T0015Z/replay_pub
W=$SC/round4/replay_live; O=$W/out
N=$SC/node26131/node_modules/node/bin/node; export NODE_PATH=/home/user/work/pkg27/test/node_modules
feed=usdc; from=2026-11-12T16:30:00Z; to=2026-11-15T00:15:00Z; name=12
b=$O/${feed}_${name}
[ -s $b.done ] && { echo "already done: $(cat $b.done)"; exit 0; }
cd $O && $N $RP/tools/replay_chrono_pr5.js --server $SC/r29/builds/P/pinradar_server.js --sec $W/data/sec --venues proxy --proxy-dir $feed --markets $W/data/kalshi/markets_range.ndjson \
  --from ${from} --to ${to} --warm 86400 --out $b.ndjson --trace $b.trace.ndjson > $b.log 2>&1 \
  && python3 -I $RP/tools/pr4_summarize.py $b.ndjson $b.trace.ndjson $b.sum.ndjson >> $b.log 2>&1 \
  && gzip -f $b.trace.ndjson && python3 -I $RP/tools/pr5_eval.py $b $RP/out_pr5 && python3 -I $RP/tools/loser_min1.py $b && tail -n 2 $b.log | tr '\n' ' ' > $b.done
echo "$(date -u +%T) $feed $name $(cat $b.done 2>/dev/null | cut -c1-140)"
