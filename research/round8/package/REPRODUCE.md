# Reproduction (from the package root)
Runtime used: Node.js v26.13.1 for the server files and replays (the server requires the npm package `ws` 8.22.0 and Node built-ins only: fs, crypto, url, http); Python 3.13.18, standard library only (run with `python3 -I`). Headless renders of the page (round 7) used Node v22 + Playwright and are not needed for any number in this report.
```
bash unpack.sh                                   # data/unpacked/{tape_all.ndjson, T1..T3.ndjson, rows/, markets/, rows_ext/, markets_new/, d3/}
export NODE_PATH=<directory whose node_modules contains ws@8.22.0>
# 1. identities
sha256sum sources/pinradar_server_I2_3125bbc0.js sources/pinradar_server_PR11_b9_c03385dc.js sources/rstar_0.050.json
diff -u sources/pinradar_server_I2_3125bbc0.js sources/pinradar_server_PR11_b9_c03385dc.js | diff - sources/I2_to_PR11_b9.diff && echo diff-matches
# 2. self-tests and boundary tests
PR11_MODE=gate node scripts/round7/run_selftest_pr11.js sources/pinradar_server_PR11_b9_c03385dc.js     # also PR11_MODE=off / shadow
node scripts/round8/run_selftest_generic.js sources/pinradar_server_I2_3125bbc0.js
PR11_MODE=gate node scripts/round7/boundary_tests.js sources/pinradar_server_PR11_b9_c03385dc.js
# 3. exact replays (D3): per-second dumps of both engines on the three captures, then validation
mkdir -p out/d3
for T in T1 T2 T3; do node scripts/round8/dump_replay.js sources/pinradar_server_I2_3125bbc0.js data/unpacked/$T.ndjson out/d3/I2_$T.ndjson scripts/round7/replay_tape28.js; done
for T in T1 T2 T3; do PR11_MODE=gate node scripts/round8/dump_replay.js sources/pinradar_server_PR11_b9_c03385dc.js data/unpacked/$T.ndjson out/d3/B9_$T.ndjson scripts/round7/replay_tape28.js; done
python3 -I scripts/round8/validate_d3.py out/d3/I2_T1.ndjson,out/d3/I2_T2.ndjson,out/d3/I2_T3.ndjson out/d3/B9_T1.ndjson,out/d3/B9_T2.ndjson,out/d3/B9_T3.ndjson sources/rstar_0.050.json out/d3_validation.txt
# (the shipped dumps in data/unpacked/d3 were produced by exactly these commands; config_package.json points at them)
# 4. market-level table and statistics
python3 -I scripts/round8/build_market_table.py scripts/round8/config_package.json out
for f in all I2 pre-I2 books exact; do python3 -I scripts/round8/summarize.py out/market_table.json out/summary_$f.txt $f; done
python3 -I scripts/round8/baseline_tape_only.py data/unpacked/tape_all.ndjson out/exclusions.csv data/unpacked/markets,data/unpacked/markets_new out/baseline_tape_only.txt
# 5. incidents
python3 -I scripts/round8/incident_seconds.py KXBTC15M-26NOV131915-15 data/unpacked/rows,data/unpacked/rows_ext data/unpacked/markets,data/unpacked/markets_new data/unpacked/tape_all.ndjson sources/rstar_0.050.json data/unpacked/d3/B9_T1.ndjson out/incident_nov14.txt
python3 -I scripts/round8/incident_seconds.py KXBTC15M-26NOV151330-30 data/unpacked/rows,data/unpacked/rows_ext data/unpacked/markets,data/unpacked/markets_new data/unpacked/tape_all.ndjson sources/rstar_0.050.json - out/incident_nov15.txt
# 6. the four frozen tables on the same denominator (reconstruction only): copy config_package.json, change "rstar" to sources/rstar_0.200.json etc. and add "use_exact": false, then run step 4 with that config
# 7. opportunity reconciliation on the three captures (corrected and erroneous scripts)
PR11_MODE=gate node scripts/round7/coverage_b8.js sources/pinradar_server_PR11_b9_c03385dc.js scripts/round7/replay_tape28.js data/unpacked/T1.ndjson data/unpacked/T2.ndjson data/unpacked/T3.ndjson
PR11_MODE=gate node scripts/round7/coverage_b8_wrongbook.js sources/pinradar_server_PR11_b9_c03385dc.js scripts/round7/replay_tape28.js data/unpacked/T1.ndjson data/unpacked/T2.ndjson data/unpacked/T3.ndjson   # reproduces the ERRONEOUS 24/27
# 8. official-reference scan, small counts
python3 -I scripts/round7/official_state_scan.py data/unpacked/tape_all.ndjson
python3 -I scripts/round8/misc_counts.py data/unpacked/rows,data/unpacked/rows_ext data/unpacked/markets,data/unpacked/markets_new data/unpacked/d3/I2_T1.ndjson,data/unpacked/d3/I2_T2.ndjson,data/unpacked/d3/I2_T3.ndjson out/misc_counts.txt
# 9. results re-check against Kalshi (network): curl -s https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC15M-26NOV131915-15
```
Expected: out/market_table.csv and out/summary_all.txt byte-identical to outputs/round8/main/ (verified on 2026-11-17 by re-running from the package copy); d3_validation.txt identical in counts; self-tests 167/167 (candidate, every mode) and 134/134 (baseline); boundary 29/29.
