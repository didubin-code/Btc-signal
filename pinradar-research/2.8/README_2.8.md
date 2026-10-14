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
| Probability engine, LOCKED rule, TRADE NOW rule | Unchanged from 2.6 and 2.7. 2.8 makes the same decisions as 2.7 in all of these: 17,458 replayed seconds over 58 real contracts (0 mismatches), 20,000 hostile fuzz cases (0 violations) and an end-to-end live-path simulation. |
| Defect fixes (change decisions only where the defect was) | **D1.** If the live index lost venue quorum, the last good 1 Hz value was treated as 0 ms old with no gate. Reproduced on 2.6 and 2.7: a LOCKED + TRADE NOW call was produced from a stale index. Now it is a hard gate: DATA UNRELIABLE. **D2.** Official BRTI freshness was judged by arrival time, so a value 60 s old at its source counted as fresh. Now the source time also counts. **D3.** A zero-size best ask level was shown as the "buy at ≤" price. |
| Economics | Fee settings are read from Kalshi's series record (`fee_type`, `fee_multiplier`) instead of being hard-coded. Fee arithmetic is exact (integer). A per-order-size expected-value table shows that at 99 ¢ one contract pays a 1 ¢ fee (the whole edge) while 10 contracts pay 0.1 ¢ each. The three decisions are shown separately: outcome confidence, trade value, execution readiness. |
| Honesty | Flip risk is shown with the range of loss rates the same number has meant historically, e.g. "≈0.5 % (plausible 0.08–0.8 %)". Labels are **PREDICTED LOCKED**, **MATHEMATICALLY FINAL** (only after the close with the official accumulator at 60/60, or the price-only bound) and **OFFICIALLY SETTLED**. |
| Evidence | A hash-chained, append-only ledger commits every first call before the outcome exists. Two anytime-valid monitors run on it: a failure alarm and a proof of edge. Five candidate models run in shadow on the same live inputs, defined in `PREREGISTRATION.md`. |
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
   * **Persistent disk.** Attach a Render disk (paid) at `/var/data` and set `LEDGER_FILE=/var/data/ledger28.ndjson`, `TAPE_FILE=/var/data/tape28.ndjson` and optionally `PRED_LOG_FILE=/var/data/pred28.ndjson`. The chain then survives restarts.
   * **No disk.** Run `node tools/ledger_pull28.js https://btc-pin-radar-28.onrender.com ledger28.ndjson` from your computer every 5–10 minutes. It is free and verifies the chain on every pull. A restart then starts a new verified segment.
4. **Page.** Upload `btc_pin_radar_28.html` to `Btc-signal` as a new file, open `https://didubin-code.github.io/Btc-signal/btc_pin_radar_28.html`, and set the backend URL to the 2.8 service. Its settings are stored separately from the 2.3 page.

## 4. Verify after deploy (about 5 minutes; vol warm-up takes about 15 minutes)

* `/health` → `"version":"pin-radar-2.8"`, `"build":"2.8-2026-10-14"`, and `v28.fees.verified:true` once Kalshi's series record has been read. If it shows false, look at `v28.fees.error`.
* `/selftest` → `"passed":128,"total":128`.
* `/fees` → shows the fee type and multiplier Kalshi reports for KXBTC15M, plus two example fees. If Kalshi's record shows a maker fee or a different multiplier, TRADE NOW automatically uses it.
* `/ledger/verify` → `"ok":true`. Write down `head` now and then: any later rewrite of an earlier entry changes every subsequent hash.
* `/shadow` → six policies, with open windows filling up during the final 300 s of each window.
* `/latency` → `bgSnapshotMs.p99` is a few ms. `clientSignalAgeAtDisplayMs` fills once the 2.8 page is open.

## 5. Forward test (the only evidence that can still be independent)

* Run the service for **at least 21 days and 1,500 LOCKED windows**.
* Pull the ledger regularly.
* Save `/latency` daily.
* Optionally pull `/tape?format=ndjson` daily, which calibration needs.
* Then run:

```
node pinradar-research/2.8/tools/forward_report28.js --ledger ledger28.ndjson --tape tape28.ndjson --latency latency.json --config <CONFIG28_HASH from /v28> --out report.json
```

The tool recomputes every pre-registered gate from committed entries only. It prints IN PROGRESS, PASS or FAIL.

**Stop rules:**
* the failure monitor alarms, which `/monitors` shows and the page shows as FAILURE ALARM;
* more than 3 losses in 200 consecutive LOCKED windows.

When a stop rule fires, stop relying on LOCKED and investigate. Do not retune on a handful of outcomes.

## 6. Reproduce every offline check

```
bash pinradar-research/2.8/test/run_all28.sh      # ~4 min, no network, installs jsdom inside 2.8/test only
```

It covers: build (sha-checked) → selftest 128/128 → core tests 55/55 → page tests 38/38 → fuzz 20,000 → replay parity
(58 contracts) → live-path simulation with LIVE = REPLAY → adversarial scenarios 1–20 → settlement arithmetic 18/18 → BRTI mock 4/4.

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
| `TAPE_FILE` / `TAPE_MAX` | – / `3000` | record/replay tape file / decision records kept in memory |
| `MONITOR_P0` | `0.005` | failure-alarm null hypothesis (the LOCKED standard) |

## 9. What is not verified

* **Real profitability.** All TRADE NOW evidence, past and forward, uses hypothetical fills on the visible book. Even the historical point estimate is about +1 ¢ per contract over about 5 trades a day, with a confidence interval that includes zero.
* **Kalshi fee rounding unit and maker fees for KXBTC15M.** These are read from the series record at runtime where Kalshi provides them. The rounding unit is not in the record, so cent rounding is assumed.
* **The official BRTI path with real messages.** It needs your key's CF Benchmarks entitlement; see the 2.7 README section 6.
* **The probability model on data after Oct 13.** That is exactly what the forward test measures.
