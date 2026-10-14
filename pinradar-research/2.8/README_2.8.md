# BTC Pin Radar 2.8: install, verify, forward-test, roll back

Built Oct 14 2026 on branch `claude/btc-pin-radar-research-xpe585` in both repos.

* **Nothing here places orders.**
* **Nothing has been deployed.**
* **Production 2.3 is untouched:**
  * `btc-ai-backend` `main` is still `c9e0df6`;
  * `Btc-signal` `main` is still `f3eb239`.

## 1. What 2.8 is

| Area | What changes |
|---|---|
| Probability engine, LOCKED rule, TRADE NOW rule | Unchanged from 2.6 and 2.7, except where a defect is fixed (D1, D4–D6 below). 2.8 makes the same decisions as 2.7 in every check:<ul><li>17,458 replayed seconds over 58 real contracts: 0 mismatches. This check calls the inner functions.</li><li>20,000 hostile fuzz cases: 0 violations.</li><li>4,800 live-simulation decisions replayed through 2.7's production `computeLockSnapshot`: 0 differences, apart from the 7 seconds with the live index down, where the D1 gate acts. A deliberately broken build (HIGH promoted to LOCKED) fails this check with 253 differences.</li></ul> |
| Defect fixes (change decisions only where the defect was) | **D1.** If the live index lost venue quorum, the last good 1 Hz value was treated as 0 ms old with no gate. Reproduced on 2.6 and 2.7: a LOCKED + TRADE NOW call was produced from a stale index. Now it is a hard gate: DATA UNRELIABLE. **D2.** Official BRTI freshness was judged by arrival time, so a value 60 s old at its source counted as fresh. Now the source time also counts. **D3.** A zero-size best ask level was shown as the "buy at ≤" price. Found by the round-3 independent review, and present in 2.6 and 2.7 too: **D4.** A PROVEN (price-only, proxy) bound skipped the official-BRTI gates. The page could show TRADE NOW and "MATHEMATICALLY FINAL" while the official reference disagreed; now that state is withheld (HIGH CONFIDENCE) like an ordinary LOCKED. **D5.** An official REVERSAL WARNING kept the proxy's ">99.9 % / <0.1 %" and its guarantee text; now the official reference's numbers are shown. **D6.** After the close, 58 or 59 official values (the clock tolerance) counted as "decided" and were labelled MATHEMATICALLY FINAL 60/60; now only exactly 60/60. |
| Economics | Fee settings are read from Kalshi's series record (`fee_type`, `fee_multiplier`) instead of being hard-coded. Fee arithmetic is exact (integer). A per-order-size expected-value table shows that at 99 ¢ one contract pays a 1 ¢ fee (the whole edge) while 10 contracts pay 0.1 ¢ each. The three decisions are shown separately: outcome confidence, trade value, execution readiness. |
| Honesty | Flip risk is shown with the range of loss rates the same number has meant historically, e.g. "≈0.5 % (plausible 0.08–0.8 %)". Labels are **PREDICTED LOCKED**, **MATHEMATICALLY FINAL** (only after the close with the official accumulator at 60/60, or the price-only bound) and **OFFICIALLY SETTLED**. |
| Evidence | A hash-chained, append-only ledger commits every first call before the outcome exists. Calibration points are committed too. Two anytime-valid monitors run on it: a failure alarm (latched once it fires) and a proof of edge. Five candidate models run in shadow on the same live inputs, defined in `PREREGISTRATION.md` (`pinradar-2.8-prereg-v2`). The chain survives:<ul><li>a restart: open windows and their committed calls are restored, and windows that closed meanwhile are settled;</li><li>a failed disk write: retried in order;</li><li>a crash mid-write: the torn line is cut off;</li><li>a corrupt row: the verified prefix is kept and the original is set aside.</li></ul> |
| Operations | Latency percentiles at every stage, including how old a signal was when your browser drew it. A record/replay tape lets any live decision be reproduced by the production function. |

## 2. Files

| Branch path | Goes to | Action |
|---|---|---|
| `btc-ai-backend: pinradar-research/2.8/dist/pinradar_server.js` | a **new** branch `pinradar-2.8` of `btc-ai-backend`, repo root, as `pinradar_server.js` | new Render service only |
| `Btc-signal: pinradar-research/2.8/btc_pin_radar_28.html` | `Btc-signal`, as a **new file** `btc_pin_radar_28.html` | does not replace the 2.3 page |
| `pinradar-research/versions/2.3/…` | rollback copies | byte-identical to live 2.3 |
| `pinradar-research/2.8/tools/` | your computer | ledger pull, forward report, tape replay |

SHA-256 values are in `2.8/SHA256SUMS.txt`. Dependencies are unchanged: only `ws`. No environment variable is required.

## 3. Install next to 2.3 (production keeps running)

1. **GitHub.** In `didubin-code/btc-ai-backend`, create the branch `pinradar-2.8` from `main`. On that branch, upload `dist/pinradar_server.js` as `pinradar_server.js`, replacing it on that branch only. A commit to a non-`main` branch does not redeploy anything that tracks `main`.
2. **Render.** Choose **New + → Web Service**, repo `btc-ai-backend`, branch `pinradar-2.8`.
   * Build command: `npm install`.
   * Start command: `node pinradar_server.js`.
   * Name: `btc-pin-radar-28`.
   * Copy `KALSHI_KEY_ID` / `KALSHI_PRIVATE_KEY` from `btc-pin-radar` only if you want the official BRTI check. Without them everything runs as PROXY. Public Kalshi REST is enough for the market, book, settlement and fee record.
3. **Persistence (recommended, a cost decision for you).** The forward evidence lives in memory unless a disk is attached. Two options:
   * **Persistent disk.** Attach a Render disk (paid) at `/var/data` and set:
     * `LEDGER_FILE=/var/data/ledger28.ndjson`
     * `TAPE_FILE=/var/data/tape28.ndjson`
     * optionally `PRED_LOG_FILE=/var/data/pred28.ndjson`

     The chain then survives restarts, and so do open windows and their committed calls. Run a single instance: Render already turns off zero-downtime deploys when a disk is attached, so two processes never write one file.
   * **No disk.** Run `node tools/ledger_pull28.js https://btc-pin-radar-28.onrender.com ledger28.ndjson --anchors anchors28.txt` from your computer every 5–10 minutes (cron). It is free and verifies the chain on every pull.
     * Exit codes: 0 ok; 3 FORK (nothing appended: investigate); 4 the server has entries it could not store yet (disk problem).
     * A restart starts a new verified chain. Calls committed in a window that was open during the restart are still scored from the pulled file. If that window's outcome never arrives, it counts as unresolved.
     * If you pull too rarely and the server's in-memory window (`LEDGER_MAX` = 50,000 entries, about 10 days) moves past your last entry, the gap stays visible and fails G2.
   * With a disk, `/ledger` serves only entries already written to it. After a disk-write failure and a restart, a pulled copy therefore can never disagree with the server's chain. If the puller ever sees a different entry at the same position of the same chain, it stops with `FORK` and appends nothing.
   * The tape (about 80 MB/day) rotates at `TAPE_FILE_MAX_MB` (default 256) into one `.prev` file, so it cannot fill the disk the ledger is on.
     * Size the disk for about 2 MB/day of ledger plus 2 × `TAPE_FILE_MAX_MB`.
     * `PRED_LOG_FILE` (a 2.7 feature) has no cap; leave it unset on a small disk.
4. **Page.** Upload `btc_pin_radar_28.html` to `Btc-signal` as a new file, open `https://didubin-code.github.io/Btc-signal/btc_pin_radar_28.html`, and set the backend URL to the 2.8 service. Its settings are stored separately from the 2.3 page.

## 4. Verify after deploy (about 5 minutes; vol warm-up takes about 15 minutes)

* `/health` → `"version":"pin-radar-2.8"`, `"build":"2.8-2026-10-14"`, and `v28.fees.verified:true` once Kalshi's series record has been read. If it shows false, look at `v28.fees.error`.
* `/selftest` → `"passed":134,"total":134`.
* `/fees` → shows the fee type and multiplier Kalshi reports for KXBTC15M, plus two example fees.
  * A multiplier in [0.1, 4] from Kalshi's record is used for TRADE NOW, including per-fill rounding when configured.
  * Anything else (null, empty, out of range) is rejected, and the default schedule is kept with `verified:false`.
* `/ledger/verify` → `"ok":true`. It re-checks only new entries; `?full=1` re-hashes everything, at most once a minute.
  * **Anchors.** Run the puller with `--anchors anchors28.txt` (with a disk too: it is the evidence copy). Each pull appends the head of your pulled file with the time.
    * **Publish that file often, outside the server and outside your copy of the ledger**, for example by committing it to a git repository every hour. The commit history is the timestamp.
    * Pass the heads to the report as `--anchor h1,h2,…`.
    * The hash chain alone proves only that the file is internally consistent. Published heads prove that nothing up to them was later rewritten, deleted or invented.
    * A window counts only if a published head comes at or after it in its own chain segment (each restart without a disk starts a segment). Later windows count as unresolved (limit 2 %), so publish at least hourly.
    * Use the puller's heads, not `/ledger/verify`'s: that head can include entries you have not pulled.
* `/shadow` → six policies, with open windows filling up during the final 300 s of each window.
* `/latency` → `bgSnapshotMs.p99` is a few ms. `clientSignalAgeAtDisplayMs` fills once the 2.8 page is open; it is reported by browsers, so it is informational only. The ledger receives an hourly latency histogram, and G6 is computed from those.

## 5. Forward test (the only evidence that can still be independent)

* Run the service for **at least 21 days and 3,000 LOCKED windows** (about 35 days at about 85 LOCKED windows a day). The maximum is 90 days. These are pre-registered (`PREREGISTRATION.md`, v2): 3,000 windows gives 85 % power to show a loss rate below 0.75 % if the true rate is the development 0.37 %.
* Pull the ledger regularly (no-disk setup), and publish the `/ledger/verify` head daily (section 4).
* Calibration (G5) and latency (G6) evidence is committed to the ledger, so the tape and `/latency` snapshots are optional.
  * `/tape` is a rolling in-memory buffer of about 10 windows (≈ 2.5 h).
  * With `TAPE_FILE` on the disk, decisions are replayable for the tape that is kept: the current file and one `.prev`. That is about 6 days at the default `TAPE_FILE_MAX_MB` = 256. Raise it, with a larger disk, to keep more.
* On the deployed build, run `run_all28.sh` and `GET /selftest`. If both pass, that is your G1 attestation.
* Then run:

```
node pinradar-research/2.8/tools/forward_report28.js --ledger ledger28.ndjson --g1 PASS --config <CONFIG28_HASH from /v28> --anchor <published heads, comma-separated> --out report.json
```

The test ends at the first window by which there are 3,000 LOCKED windows and 21 days (or at day 90). Later windows are not scored, so re-running the report later gives the same verdict. `--since` produces an exploratory report, not a verdict.

The tool recomputes every pre-registered gate from committed entries only:
* Each window is scored from its first committed calls (never from the server's summary), under the configuration in force when those calls were made.
* Any chain break fails G2.

The verdict is one of:

| Verdict | Meaning |
|---|---|
| FAIL | G2 (integrity; unresolved ≥ 2 %; downtime > 5 %) or the stop rule failed; or, at the end, a gate failed |
| IN PROGRESS | the test has not ended |
| NOT DEMONSTRATED | the end was reached and nothing failed, but the reliability bound was not reached |
| INCOMPLETE | evidence is missing (G1 attestation, published heads, calibration coverage or latency) |
| PASS (decision support) | G1–G6 pass |

It also prints a verdict for each shadow candidate.

**Stop rules:**
* the failure monitor alarms, which `/monitors` shows and the page shows as FAILURE ALARM. The alarm is latched: it stays on even if later wins pull the e-value back below 20 (Ville's inequality covers the maximum);
* more than 3 losses in 200 consecutive LOCKED windows.

When a stop rule fires, stop relying on LOCKED and investigate. Do not retune on a handful of outcomes.

## 6. Reproduce every offline check

```
bash pinradar-research/2.8/test/run_all28.sh      # ~5 min, no network, installs jsdom inside 2.8/test only
```

It needs only a clone of `btc-ai-backend` on the research branch: the 2.7 page source is in `pinradar-research/pkg27_page`. It writes nothing tracked. It rebuilds into a temp directory and checks that the committed `dist` files are byte-identical builds of the sources.

It covers, in order:
* build reproducibility
* selftest 134/134
* core tests 61/61
* page tests 41/41
* fuzz 20,000 (2.8 vs 2.7 invariants)
* replay parity (58 real contracts, 17,458 seconds)
* live-path simulation:
  * LIVE = REPLAY on the file tape and on the in-memory `/tape`;
  * **2.8 = 2.7** on the same recorded live inputs through the production `computeLockSnapshot`, except where D1 applies;
  * ledger and tape integrity;
  * HTTP endpoints.
* adversarial scenarios 1–20
* settlement arithmetic 18/18
* BRTI mock 4/4
* property tests (`test/props28.js`):
  * settlement brute force, 140,000 integer-cent checks;
  * exact half-cent ties;
  * m25PUp monotone in the gap, 509,040 evaluations;
  * recalibration monotone.
* round-3 regressions 54/54 (`test/regress28.js`; every check fails on the build that had the defect)

`node --expose-gc test/soak28.js dist/pinradar_server.js 24` is the 24 h memory/latency soak (about 3 min). With `--expose-gc`, the heap is measured after a full GC: 18 MB at hour 1, 42 MB at hour 24, as bounded buffers fill.

## 7. Roll back

* **Side-by-side install:** suspend or delete the `btc-pin-radar-28` service and the `btc_pin_radar_28.html` file. Production was never changed.
* **If you ever replace `main`:**
  1. Upload `pinradar-research/versions/2.3/pinradar_server.js` to `btc-ai-backend` `main`, and the 2.3 page to `Btc-signal` `main`.
  2. Check that `/health` shows `pin-radar-2.3`.
  3. A merge to `main` redeploys every Render service that tracks it. Do it with no open positions.

## 8. Settings (all optional; defaults are the validated values)

| Env var | Default | Meaning |
|---|---|---|
| all 2.6 / 2.7 settings | unchanged | `LOCK_MAX_FLIP=0.005`, `MIN_EDGE_CENTS=0.5`, `RECAL_*`, `BRTI_*`, … Changing any of them changes `CONFIG28_HASH` and voids the forward test. |
| `FEE_TAKER_MULT` / `FEE_MAKER_MULT` | `0.07` / from the series record (`0` unless `fee_type` names maker fees) | override the fee coefficients |
| `FEE_ROUNDING` | `cent` | `centicent` if Kalshi confirms $0.0001 fee rounding (cent is the conservative reading) |
| `FEE_PER_FILL` | `0` | `1` rounds the fee per price level, which is conservative if Kalshi rounds per trade |
| `LADDER_SIZES` | `1,5,10,25,50,100` | order sizes in the EV table |
| `LEDGER_FILE` / `LEDGER_MAX` | – / `50000` | append-only ledger file (persistent disk) / entries kept in memory |
| `TAPE_FILE` / `TAPE_MAX` | – / `3000` | record/replay tape file / decision records kept in memory (≈ 10 windows; index samples are kept for the same span + 960 s, so a pulled `/tape` replays) |
| `TAPE_FILE_MAX_MB` | `256` | the tape file rotates at this size into one `.prev` file (at most 2× on disk). Tape digests committed to the ledger can be checked only while the tape file still exists |
| `MONITOR_P0` | `0.005` | failure-alarm null hypothesis (the LOCKED standard) |

## 9. What is not verified

* **Real profitability.** All TRADE NOW evidence, past and forward, uses hypothetical fills on the visible book. Even the historical point estimate is about +1 ¢ per contract over about 5 trades a day, with a confidence interval that includes zero.
* **Kalshi fee rounding unit and maker fees for KXBTC15M.** These are read from the series record at runtime where Kalshi provides them. The rounding unit is not in the record, so cent rounding is assumed.
* **The official BRTI path with real messages.** It needs your key's CF Benchmarks entitlement; see the 2.7 README section 6.
* **The probability model on data after Oct 13.** That is exactly what the forward test measures.
