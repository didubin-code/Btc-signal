#!/bin/bash
# D3: exact replays of the I2 file and the build-9 file on the three capture tapes (per-second dumps)
SC=/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad
NODE=$SC/node26131/node_modules/node/bin/node; export NODE_PATH=/home/user/work/pkg27/test/node_modules
RT=$SC/incident_20261114T0015Z/tools/replay_tape28.js
I2=$SC/round4/impl/base_I2_pinradar_server.js; B9=$SC/round7/impl/pinradar_server_PR11.js
T1=$SC/incident_20261114T0015Z/own_capture_2/tape_since_boot.ndjson; T2=$SC/round3/tape/pull_20261115T014056Z.ndjson; T3=$SC/round4/impl/replay/pull/tape_full_20261116T023520Z.ndjson
cd $SC/round8/d3
for eng in I2 B9; do f=${!eng}; for tp in T1 T2 T3; do t=${!tp}; echo "== $eng $tp $(date -u +%T)"; PR11_MODE=gate $NODE $SC/round8/scripts/dump_replay.js $f $t $SC/round8/d3/${eng}_${tp}.ndjson $RT; done; done
echo "D3 DONE $(date -u +%FT%TZ)"
