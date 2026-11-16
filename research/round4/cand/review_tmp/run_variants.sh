#!/bin/bash
cd /tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/cand/review_tmp
RP=/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/replay_pub/out_full_mu
C=/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/cand/cells.json
echo "start $(date -u +%T)"
python3 -I build_cells_w5.py $RP cells_w5.json > build_w5.log 2>&1; echo "build_w5 done $(date -u +%T)"
python3 -I eval_w5.py cells_w5.json $RP eval_w5 > eval_w5.log 2>&1; echo "eval_w5 done $(date -u +%T)"
python3 -I eval_down.py $C $RP eval_down > eval_down.log 2>&1; echo "eval_down done $(date -u +%T)"
python3 -I eval_all.py $C $RP eval_all > eval_all.log 2>&1; echo "eval_all done $(date -u +%T)"
python3 -I eval_w5down.py cells_w5.json $RP eval_w5down > eval_w5down.log 2>&1; echo "eval_w5down done $(date -u +%T)"
python3 -I build_cells_sep1.py $RP cells_sep1.json > build_sep1.log 2>&1; echo "build_sep1 done $(date -u +%T)"
python3 -I eval_sep1.py cells_sep1.json $RP eval_sep1 > eval_sep1.log 2>&1; echo "eval_sep1 done $(date -u +%T)"
echo ALLDONE
