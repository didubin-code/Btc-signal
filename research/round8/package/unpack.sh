#!/bin/bash
# unpack the package data into data/unpacked (run from the package root)
set -e; mkdir -p data/unpacked/d3
gunzip -c data/tape_all_d_rows_20261117T2108Z.ndjson.gz > data/unpacked/tape_all.ndjson
gunzip -c data/T1_tape_since_boot_20261114T0034Z.ndjson.gz > data/unpacked/T1.ndjson
gunzip -c data/T2_pull_20261115T014056Z.ndjson.gz > data/unpacked/T2.ndjson
gunzip -c data/T3_tape_full_20261116T023520Z.ndjson.gz > data/unpacked/T3.ndjson
tar -xzf data/prediction_rows_r30_live_scoreboard.tar.gz -C data/unpacked          # rows/, markets/
tar -xzf data/prediction_rows_ext_and_markets_new_20261117T2122Z.tar.gz -C data/unpacked   # rows_ext/, markets_new/
tar -xzf data/d3_exact_replay_dumps.tar.gz -C data/unpacked && mv -f data/unpacked/d3/*.ndjson data/unpacked/d3/ 2>/dev/null || true
echo unpacked; ls data/unpacked
