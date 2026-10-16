# BTC Pin Radar Trader 5.0

This trader replaces `live-trader-4.17.js` for Kalshi's 15-minute BTC contracts (KXBTC15M).

* It evaluates every window automatically.
* It buys only when the validated Pin Radar engine and every trader check agree.
* It risks at most **$5 per trade, fee included**.

> **Status (2026-10-16).** The code is built and tested offline only:
> * no deployment;
> * no real orders;
> * v4.17, its Render service and production Pin Radar are unchanged.
>
> It runs in **dry run** unless it is explicitly armed (see *Going live*). It is **not yet validated for real money**: the forward record it keeps is the first independent evidence.

The original v4.17 and its supporting files are archived and checksummed in `../trader-archive/live-trader-4.17/` (run `bash verify_archive.sh` there). The originals on `main` were not changed.

## How it decides

The decision engine is **Pin Radar 2.8.1**.
* Location: `engine/pinradar_server.js`, a byte-identical copy of btc-ai-backend `pinradar-research/2.8.1/dist/pinradar_server.js`.
* SHA-256: `55d0555c65e4f8a4e00355aaa2db7d1f0574918978f3749d6c8ff55d97522a0d`.
* It runs in-process with `LOCK_MAX_FLIP=0.002`, the 0.2 % LOCKED threshold.
* The trader refuses to start if the file's hash differs.

Every 500 ms the trader takes a read-only engine reading. It reads twice: once to find the side and the ask, then again at the actual order size. The engine's own background classifier keeps its state, exactly as on the Pin Radar page.

A buy needs **all** of the following (`lib/policy.js`). Every block reason is recorded per window.

| Check | Rule |
|---|---|
| Reversal risk | Engine state LOCKED, with modelled flip risk ≤ 0.2 %. Never on HIGH CONFIDENCE, REVERSAL WARNING or DATA UNRELIABLE. |
| Data integrity | No hard gate. Volatility history full. Basis model warm (≥ 12 settled windows). |
| Engine execution decision | The engine's action line says **TRADE NOW**. This already requires:<br>• a fresh book (≤ 1.5 s);<br>• enough offers for the order;<br>• cautious edge after fee ≥ 0.5 ¢;<br>• the edge surviving a 1.645 σ adverse move during the 12 s order time;<br>• the side offered at ≥ 90 ¢;<br>• enough time left. |
| Timing | ≥ 15 s before the close. This is the validated 15 s buffer. |
| Price | Limit between 90 ¢ and 99 ¢. 99.9 ¢ has no edge after the fee. |
| Expected value | Cautious edge recomputed at the **exact limit and size**, fee included: ≥ 0.5 ¢ per contract. |
| Size | The most contracts with contracts × limit + Kalshi fee ≤ $5. The fee is `ceil(0.07·C·P·(1−P))`. $5 buys 5 contracts at 99 ¢ ($4.96) or at 90 ¢ ($4.54). |
| Liquidity | The book is walked to the worst level needed. The order is a limit at that level, IOC. |
| Per window | One entry per window, never the other side, at most 2 attempts. |
| Risk state | All of:<br>• not halted;<br>• no order in flight;<br>• daily loss < $10;<br>• no unreviewed loss;<br>• ≤ 96 trades per day;<br>• open exposure ≤ $5;<br>• Kalshi exchange confirmed active (live). |

Orders are reused from v4.17's working order layer (`lib/kalshi.js`):
* `POST /portfolio/events/orders`;
* RSA-PSS signed;
* `bid` buys YES; `ask` sells YES, which buys NO at 1 − price;
* `immediate_or_cancel`, `exchange_index -1`.

There are no exits: positions are held to settlement.

### Evidence: modelled versus observed

The trader reports these separately (`/stats`) and never mixes them.

* **Modelled.** `pFlip` / `pFlipCons` in every decision are the engine's model outputs. They are not observed rates.
* **Observed in backtest** (btc-ai-backend `pinradar-research/validation/VALIDATION_REPORT.md` §G, `thr02_summary.md`). This engine at the 0.2 % threshold was replayed over 25,982 real Kalshi contracts:
  * first LOCKED wrong: 15 / 16,700 unseen (0.090 %, 95 % CI 0.050–0.148 %);
  * LOCKED at T−20 wrong: 1 / 15,601;
  * small size with the 15 s buffer and 12 s order time: +0.22 ¢/contract (CI +0.14 to +0.29) over 5,158 trades, 2 lost.

  Caveats:
  * the price feed was a substitute (Binance BTCUSDC), not the live 3-venue index;
  * fills were modelled from other traders' prints, an upper bound;
  * the small-size edge **decayed to about zero by September 2026**.
* **Observed forward.** The trader's own settled record, with a one-sided 95 % Clopper–Pearson upper bound on its loss rate.

## Files

```
trader.js                 main loop, risk state, settlement, HTTP endpoints (VERSION pinradar-trader-5.0)
lib/policy.js             the entry decision (pure function), sizing, book walk
lib/kalshi.js             Kalshi REST client: signing, order building and refusals, result parsing, fee
lib/ledger.js             append-only, SHA-256 hash-chained JSONL ledger
engine/pinradar_server.js Pin Radar 2.8.1 engine (do not edit: the hash is checked at boot)
test/                     run_all.js, unit_test.js, live_mock_test.js, engine_replay_test.js
TEST_RESULTS.md           the recorded test runs
```

## Run and test locally

```
npm install            # ws 8.18.0 (venue / Kalshi streaming); nothing else
npm test               # unit + selftest + live_mock + engine_replay
node trader.js         # dry run on :10000 (needs network to the venues and Kalshi)
```

`engine_replay` needs the validation data set built by btc-ai-backend `pinradar-research/validation/pipeline`. Point `PR_DATA` at it. Without it, the test reports SKIPPED.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `LIVE` | off | Request real orders. This alone does nothing: see `TRADER_LIVE_ARM`. |
| `TRADER_LIVE_ARM` | — | Must equal `I-ACCEPT-REAL-MONEY-RISK`, together with `LIVE=1` and credentials, to arm. |
| `KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY` | — | Kalshi API key; the PEM may use `\n`. Also used by the engine for the authenticated order-book stream. Never printed. |
| `MAX_TRADE_USD` | 5 | Per-trade cap, fee included. Capped by `ABSOLUTE_MAX_TRADE_USD`. |
| `ABSOLUTE_MAX_TRADE_USD` | 5 | Raising the cap needs both variables changed. |
| `MAX_OPEN_USD` | 5 | Total unsettled cost. |
| `DAILY_LOSS_LIMIT_USD` | 10 | Halts at −$10 realised in a UTC day. |
| `HALT_AFTER_LOSSES` | 1 | Consecutive losses that halt trading until a person resumes. |
| `MAX_TRADES_PER_DAY` | 96 | |
| `MAX_ATTEMPTS_PER_WINDOW` | 2 | IOC attempts per window (no-fills). |
| `LOCK_MAX_FLIP` | 0.002 | LOCKED threshold. Changing it leaves the validated configuration. |
| `TRADER_MIN_ASK_CENTS` / `TRADER_MAX_ASK_CENTS` | 90 / 99 | Price band. |
| `TRADER_MIN_EDGE_CENTS` | 0.5 | Cautious edge at the limit, after the fee. |
| `TRADER_MIN_TAU_SEC` | 15 | Seconds before the close. |
| `TRADER_MAX_BOOK_AGE_MS` | 1500 | |
| `REQUIRE_WARM_VOL`, `REQUIRE_WARM_BASIS` | 1, 1 | Trade only with the engine in its validated warm state. |
| `REQUIRE_EXCHANGE_OPEN` | on when live | Kalshi `/exchange/status` must say trading is active (polled every 60 s). |
| `TRADER_TICK_MS` | 500 | |
| `EXEC_SEC` | 12 | Order time used in the engine's stress test. |
| `TRADER_LEDGER_FILE` | `/tmp/pinradar_trader_ledger.jsonl` | **Put it on a persistent disk.** Halts, positions and the forward record are restored from it after a restart. |
| `PINRADAR_STATE_FILE` | — | Engine state: the basis model and its own ledger. On a persistent disk, the engine is warm right after a restart. Without it, the trader waits about 3 h (12 settled windows) before it can trade. |
| `TRADER_HALT` / `TRADER_HALT_FILE` | — | Halt by environment variable, or by the presence of a file. |
| `TRADER_ADMIN_TOKEN` | — | Needed to resume over HTTP. Without it, resume is disabled; restart after review instead. |
| `KALSHI_BASE` | `https://api.elections.kalshi.com/trade-api/v2` | |
| `EXCHANGE_INDEX`, `KALSHI_TIMEOUT_MS`, `PORT` | -1, 6000, 10000 | |
| `ALLOW_ENGINE_MISMATCH` | off | Never set this in production. |

## Endpoints

| Route | |
|---|---|
| `/health` | Mode, halts, the last decision. |
| `/status` | The full last decision and engine reading, risk state, positions. |
| `/windows?n=` | Per-window evaluation: ticks, LOCKED, engine TRADE NOW, buys, top block reasons. |
| `/trades`, `/ledger?n=`, `/ledger/verify` | Ledger records; hash-chain check. |
| `/stats` | Modelled, backtest and forward evidence. |
| `/config` | Configuration, with credentials redacted to "set / not set". |
| `/live`, `/livecheck` | Order results; balance and positions (read-only, authenticated). |
| `/halt?on=1` | Halt. No token needed. |
| `/halt?on=0&token=…` | Resume. |
| `/selftest` | No network, no orders. |
| `/engine/<route>` | Read-only passthrough to the engine's own GET routes, e.g. `/engine/health`. |

## Deployment

Deployment is a **new, separate** Render web service. **It needs your authorization, because it adds hosting cost.**

**Do not change the v4.17 service.** That means its branch, root directory, start command and environment all stay as they are. Do not merge into `main`.

1. In Render, create a **New → Web Service** from `didubin-code/Btc-signal`:
   * branch `claude/btc-pin-radar-research-xpe585`, or a release branch you choose;
   * **Root Directory** `pinradar-trader`;
   * Runtime Node ≥ 20;
   * **Build** `npm install`;
   * **Start** `node trader.js`;
   * health check path `/health`.
2. Use a paid instance that does not sleep, and attach a **persistent disk**, e.g. mounted at `/data`. Set:
   * `TRADER_LEDGER_FILE=/data/trader_ledger.jsonl`;
   * `PINRADAR_STATE_FILE=/data/pinradar_state.json`.
3. Set the environment for **dry run**:
   * do **not** set `LIVE` or `TRADER_LIVE_ARM`;
   * setting `KALSHI_KEY_ID` / `KALSHI_PRIVATE_KEY` is optional in dry run. It gives the engine the streamed order book. The trader then makes only read-only authenticated calls (`/livecheck`).
4. Turn auto-deploy off, so a push cannot change a running trader unannounced.
5. Verify the service:
   * `/selftest` → `ok: true`, 10/10;
   * `/config` → `mode: DRY-RUN`, engine `sha256` equals `expected`, `lockMaxFlip: 0.002`;
   * `/ledger/verify` → `ok: true`.
6. Let it run in dry run. Watch `/windows` and `/stats`:
   * every window is evaluated;
   * paper trades appear only on LOCKED / TRADE NOW;
   * there are no tick errors (`/health`).

   Paper fills assume the displayed offers were still there, so they are optimistic.

## Going live

Go live **only with your explicit authorization**. Real money is at risk.

Before arming:
* At least several days of dry run with no tick errors. Read `/windows` block reasons and paper trades.
* Decide how v4.17 and 5.0 will coexist. **Do not run both live on the same Kalshi account** unless their combined exposure is acceptable. Each sizes and halts independently.
* `/livecheck` shows the expected balance, and no unexpected open positions.
* Know how to halt (`/halt?on=1`, or `TRADER_HALT=1`) and how to roll back (below).
* The order JSON is v4.17's working schema. It has not been re-verified here against current Kalshi documentation. The first live order is the check: it is IOC and at most $5, and any rejection halts trading.

To arm, set `LIVE=1` and `TRADER_LIVE_ARM=I-ACCEPT-REAL-MONEY-RISK` (credentials must be set), then restart. Confirm `/health` → `mode: LIVE`. Each order is at most $5 including the fee. The trader halts on:
* any rejection or unknown outcome;
* the first loss (`HALT_AFTER_LOSSES=1`);
* −$10 in a day.

To disarm, remove `LIVE` or `TRADER_LIVE_ARM` and restart. The trader is then in dry run.

### After a halt

Halts are kept in the ledger and survive restarts.
1. Read `/status` and `/trades`.
2. Check `/livecheck` positions against the ledger. For an *unknown outcome*, the trader logs a `RECONCILE` record 5 s later.
3. Resume with `/halt?on=0&token=<TRADER_ADMIN_TOKEN>`. This writes a `RESUME` record and also resets the consecutive-loss count.

## Rollback to v4.17

v4.17 was never modified.
* `live-trader-4.17.js` is on `main`, unchanged.
* Its Render service was not touched.

Rolling back therefore means only removing 5.0:

1. Halt 5.0: `/halt?on=1`, or set `TRADER_HALT=1`.
2. Check `/livecheck`. Open positions settle by themselves at the close; 5.0 never exits early.
3. Suspend or delete the **new** 5.0 service. Keep its disk if you want the ledger.
4. If v4.17 was paused during the trial, resume its service as it was. Its environment values are in its Render dashboard; the key names are listed in `trader-archive/live-trader-4.17/ENV_KEYS_v4.17.txt`.
5. If the v4.17 file is ever in doubt, check it with `bash trader-archive/live-trader-4.17/verify_archive.sh`. The script compares the archive with the blob on `main` (commit `4426774`). To restore it: `git checkout 4426774 -- live-trader-4.17.js`.

The engine can also be rolled back on its own. Any earlier validated engine is in btc-ai-backend `pinradar-research/`. Swapping it needs a matching `ENGINE_SHA256_EXPECTED` and a re-run of `npm test`, and it leaves the validated configuration.

## Limitations

* **Backtest evidence only, on a substitute feed.**
  * The validation used Binance BTCUSDC. Live, the engine uses a Coinbase / Kraken / Bitstamp index.
  * The last ~20 s of a window are feed-dependent.
  * Kalshi book history does not exist, so execution was modelled from prints.
* **The edge is small and has decayed.** About +0.2 ¢ per contract before decay, ≈ 0 by September 2026. At $5 per trade, one loss costs as much as about 120 wins earn at 99 ¢ ($4.96 lost against 4 ¢ per win), or about 10 wins at 90 ¢. The trader halts after one loss so that a person reviews it.
* **Order schema** is inherited from v4.17. It was not re-verified against current Kalshi documentation (see *Going live*).
* **Paper fills are optimistic.** Live fills are booked at the limit, the most the IOC order could pay.
* **Warm-up.** No trading until the volatility history is full and the basis model has ≥ 12 settled windows. Use `PINRADAR_STATE_FILE` on a persistent disk.
