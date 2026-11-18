# Reproduction (package root; Node v26.13.1 with ws 8.22.0 on NODE_PATH; Python 3.13 with numpy for policy_eval_v3.py, standard library otherwise)
```
# unpack data (same layout as the round-8 package)
mkdir -p data/unpacked/d3 && for f in data/T1_*.gz data/T2_*.gz data/T3_*.gz; do gunzip -c $f > data/unpacked/$(basename $f | cut -c1-2).ndjson; done
gunzip -c data/tape_all_d_rows_20261117T2108Z.ndjson.gz > data/unpacked/tape_all.ndjson
tar -xzf data/prediction_rows_r30_live_scoreboard.tar.gz -C data/unpacked; tar -xzf data/prediction_rows_ext_and_markets_new_20261117T2122Z.tar.gz -C data/unpacked
gunzip -c data/TEST_primary_usdc_s082.trace.ndjson.gz > data/unpacked/usdc_s082.trace.ndjson; gunzip -c data/TEST_primary_usdc_s082.records.ndjson.gz > data/unpacked/usdc_s082.ndjson
# 1. identities and tests
sha256sum sources/pinradar_server_*.js; diff -u sources/pinradar_server_I2_3125bbc0.js sources/pinradar_server_PR11_b10_1fd2ea1f.js | diff - sources/I2_to_PR11_b10.diff && echo diff-matches
PR11_MODE=gate node scripts/run_selftest_pr11.js sources/pinradar_server_PR11_b10_1fd2ea1f.js        # also off / shadow: 173 checks
PR11_MODE=gate node scripts/units_boundary_tests.js sources/pinradar_server_PR11_b10_1fd2ea1f.js     # 11/11; on the b9 file 8 failures
# 2. the independent audit, re-run (needs the round-8 package layout: point it at a directory holding sources/ scripts/round7/replay_tape28.js data/unpacked/{T1,T2,T3}.ndjson data/unpacked/d3/*)
node audit_received/PR11_ChatGPT_audit/sequential_audit.js <round8 package dir> B9 out/audit; python3 -I audit_received/PR11_ChatGPT_audit/denominator_audit.py <round8 package dir> out/audit/denominator_audit.json
# 3. chronological own-memory replays and scores
for E in I2:sources/pinradar_server_I2_3125bbc0.js B9:sources/pinradar_server_PR11_b9_c03385dc.js B10:sources/pinradar_server_PR11_b10_1fd2ea1f.js; do PR11_MODE=gate node scripts/chrono_replay.js ${E#*:} scripts/replay_tape28.js out/${E%%:*}_chrono data/unpacked/T1.ndjson data/unpacked/T2.ndjson data/unpacked/T3.ndjson; done
python3 -I scripts/score_chrono.py data/unpacked/markets,data/unpacked/markets_new data/unpacked/T1.ndjson,data/unpacked/T2.ndjson,data/unpacked/T3.ndjson out/scores.txt I2=out/I2_chrono.ndjson B9=out/B9_chrono.ndjson B10=out/B10_chrono.ndjson
python3 -I scripts/denominator_regression.py out/B10_chrono.ndjson sources/rstar_0.050.json out/denominator_regression_B10.txt --engine-uses index   # and B9 with --engine-uses strike
# 4. corrected market table (edit the paths in scripts/config_v2.json to data/unpacked/... and out/B10_chrono.ndjson)
python3 -I scripts/build_market_table_v2.py scripts/config_v2.json out/table_v2; for f in all I2 books exact; do python3 -I scripts/summarize_v2.py out/table_v2/market_table.json out/table_v2/summary_$f.txt $f; done
# 5. historical TEST evaluation in table units (needs the 1-s day files rebuilt with sources/provenance/fetch_binance_1s.py into <secdir>)
python3 -I scripts/policy_eval_v3.py sources/q_full_usdc_fit.json "TEST primary 0.82" data/unpacked/usdc_s082.ndjson -- data/unpacked/usdc_s082.trace.ndjson -- out/E1c_index.txt --sec <secdir> --denominator index --floor 5
python3 -I scripts/policy_eval_v3.py sources/q_full_usdc_fit.json "TEST primary 0.82" data/unpacked/usdc_s082.ndjson -- data/unpacked/usdc_s082.trace.ndjson -- out/E1c_strike.txt --sec <secdir> --denominator strike --floor 5   # strike units need no price files; pass any directory
# 6. recorded-state dumps and replay accounting for build 10
PR11_MODE=gate node scripts/dump_replay.js sources/pinradar_server_PR11_b10_1fd2ea1f.js data/unpacked/T1.ndjson out/B10_T1.ndjson scripts/replay_tape28.js
PR11_MODE=gate node scripts/run_replay_pr11.js sources/pinradar_server_PR11_b10_1fd2ea1f.js data/unpacked/T1.ndjson out/gate_T1.json scripts/replay_tape28.js
```
Expected: outputs/ reproduced byte for byte for the table and summaries (verified for round 8's layout; round 9's scripts were run from the same data).
