# Verification package v2: PR11 build 10 versus the deployed I2 server, after the independent audit (2026-11-18)
Read COMPARISON_REPORT_v2.md first, then ERRATA.md (what round 8 got wrong). CLAIMS.md maps every number to its inputs, script and output. REPRODUCE.md gives versions and commands. The round-8 package (PR11_b9_vs_I2_verification_package_20261117.tar.gz, sha256 7847ed21…) is unchanged and still holds the round-8 outputs; this package is self-contained for every round-9 number and includes the same input data.

## Contents
- audit_received/ — the independent audit bundle exactly as received (zip sha256 a007537d… and its extracted files); outputs/audit_reproduction/ — its scripts re-run here (identical counts).
- sources/ — baseline I2 (sha256 ca51a0c6…), build 9 (a341016f…, superseded), build 10 (c82e301b…), diffs I2→b10 and b9→b10, both builders, the four frozen floor tables, the pooled and bucketed exceedance tables (q_full_usdc_fit.json, q_usdc_fit.json) and their builders, the frozen declaration (see ERRATA items 3–5). sources/provenance/ — PROVENANCE_binance_BTCUSDC.ndjson (2,279 fetch records: URL, status, bytes, sha256 of every Binance Vision daily 1-s kline zip and checksum file), the USDT equivalent, fetch_binance_1s.py (download + conversion to one 86,400-double file per UTC day) with its http_util.py helper, and usdc_1s_f64_files.sha256 (the hash of every local day file).
- scripts/ — round-9 tools (chrono_replay.js, score_chrono.py, denominator_regression.py, units_boundary_tests.js, build_market_table_v2.py + configs, summarize_v2.py, policy_eval_v3.py) and the shared tools they call (replay_tape28.js, run_replay_pr11.js, run_selftest_pr11.js, dump_replay.js, policy_eval2.py).
- data/ — the three 1-s capture tapes, the frozen tape snapshot (21:08 UTC Nov 17), prediction rows and Kalshi results, the 21:14 UTC pull, the TEST primary replay trace (865,000 rows), its window records and proxy outcomes.
- outputs/ — chrono (own-memory replays I2/b9/b10, scores, units regressions), table_v2 (the corrected market table, summaries per stratum, per-bucket exceedance), table_v2a_b9_strike_chrono (build 9 units with own memory, to separate the two corrections), historical (TEST primary in both units), d3_recorded_state_b10, replay_accounting_b10, the Kalshi fee-rounding page as fetched.
- tests/ — build 10 self-tests (gate/off/shadow), existing boundary tests, units boundary tests on build 10 and on build 9 (expected failures).
- COMPARISON_REPORT_v2.md, ERRATA.md, PR11_RELEASE.md (identity and approval statement v8), CLAIMS.md, REPRODUCE.md, MANIFEST.sha256.

## Still not independently verifiable from this package
- That production served what its rows and tapes record (the server's own public endpoints are the source; the I2 replay reproduces 8,099 of 8,100 served decisions).
- The 757 MB of 1-s closes behind the exposure tables: not included, but rebuildable from the listed Binance Vision URLs with the included script; the per-day hashes let a rebuild be checked.
- The FIT 2026 development traces (not included; development data).
- About half of the server's state-mutating decisions (the half-second ticks) are not in any capture; the own-memory replays run on the recorded 1 Hz subset.
- Deployment facts from Render (authenticated); the public /health endpoint and GitHub branches are the third-party-checkable parts.
No credentials, keys or account identifiers; no personal trade data. Hashes establish identity, not correctness.
