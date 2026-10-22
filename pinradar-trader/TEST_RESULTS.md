# Pin Radar Trader 5.0: test results

These tests were actually run on 2026-10-17, 2026-10-18 and 2026-10-22, offline. The only exception is the read-only public Kalshi API check below.
* Node v22.22.0.
* No real network calls to Kalshi and no orders.
* The live-order path runs only against a local mock.

The outputs below are verbatim.

## What the tests establish

* **Engine.** `engine/pinradar_server.js` is byte-identical to btc-ai-backend `pinradar-research/2.8.1/dist/pinradar_server.js`. Both hash to SHA-256 `55d0555c65e4f8a4e00355aaa2db7d1f0574918978f3749d6c8ff55d97522a0d`.
  * 2.8.1 is the corrected engine. Its own suite is recorded in `pinradar-research/2.8.1/TEST_RESULTS.md`: self-test 150/150, late-LOCKED 15/15, DATA UNRELIABLE 6/6, page 17/17, and the 2.8 suites. That suite was not re-run here.
  * Here, the engine runs inside the trader with `LOCK_MAX_FLIP=0.002`. Its self-test passes 149/150. The one failure is the expected assertion that a 0.468 % flip IS locked, which holds only at the 0.5 % threshold. That is the threshold change, not a defect.
* **Regression.** The trader runs its real main loop with the embedded engine, the two read-only readings per tick and the policy. It reproduces the validation's 0.2 % replay (`replay/thr02_usdc.ndjson`) exactly: the first LOCKED second and side are identical in **663 / 663** windows (Aug 1–8, 2026). Every contract in range was evaluated. The results were the same before and after the safety fixes below.
* **Execution and safety.** These run against a local mock Kalshi API with a generated RSA key:
  * request signatures;
  * order JSON, with responses in the CreateOrderV2Response shape;
  * the order outcomes: fill, no-fill, routing miss, rejection, timeout, HTTP 503;
  * provisional booking and reconciliation by `client_order_id`;
  * halts;
  * the $5 open-exposure limit, and one entry per window;
  * an unarmed `LIVE=1` sending nothing;
  * no key material in any endpoint or the ledger.
* **Hardening** (`hardening_test.js`): every fix from the safety review below is tested, in a separate process with a prepared ledger.
* **Not established.** Real fills, real Kalshi acceptance of the order format, and profitability.
  * The replay's order book is **synthetic**: it is reconstructed from real Kalshi prints in the previous 15 s.
  * Its 37 paper fills (all won, +$7.17) exercise the order path only. **They are not an execution or profit estimate.** The print-based execution study in the validation report is the reference, and it shows the small-size edge decaying to about zero by September 2026.
  * The synthetic book keeps prints for 15 s, so it often contains stale lower prices (median paper fill 96.4 ¢, minimum 90 ¢). A live book at a LOCKED moment is usually at 99 ¢ or more.

## Safety review (2026-10-17) and fixes

The review was an independent, adversarial review of the trader code in five areas:
* orders and money limits;
* state, halts and settlement;
* how the engine is used;
* operations and credentials;
* the Kalshi order schema.

Each finding was then challenged by a separate verifier, who tried to refute it. Every confirmed finding is fixed and tested:

| Finding (verified severity) | Fix | Test |
|---|---|---|
| A restart reset today's realised P&L and trade count, so a restart cleared the −$10/day limit (high). | Restore sets the day first and replays the **whole** ledger, not the last 2,000 lines. | hardening: "restart keeps today's realised loss…", "a halt 2,500 lines back is restored" |
| One unauthenticated GET (`/engine//x:99999`) crashed the process (high). | Only plain paths are forwarded. Engine route errors are caught. An `unhandledRejection` handler stops a rejection from crashing the process. | hardening: "a malformed /engine/ route is refused and the process stays up" |
| `/livecheck` showed the account balance and positions to anyone, with CORS `*` (medium/high). | Admin token in the `X-Admin-Token` header; no CORS; only KXBTC15M positions. | hardening: "/livecheck needs the admin token…" |
| A timeout or 5xx order that did fill was never booked (medium). | 5xx/408 → unknown. Halt, window marked used, provisional booking at the limit, then reconciliation via `GET /portfolio/orders` by `client_order_id`. Settlement waits for reconciliation. | live_mock: timeout, HTTP 503, reconcile (fill / no fill) |
| A restart mid-order (attempt without result) restored nothing (medium). | Halt, provisional booking, window used, reconcile. Idempotent across restarts. | hardening: "restart mid-order…" |
| LIVE could arm with the default `/tmp` ledger, and ledger write errors were swallowed (medium). | Live needs an explicit `TRADER_LEDGER_FILE`. A failing write is a halt reason and shows in `/health`. | hardening: "LIVE does not arm without…", "a failing ledger write is a halt reason" |
| The trader's PEM parsing differed from the engine's (low). | Same normalisation as the engine. The key is test-signed at start. A key that cannot sign never arms, and is a rejection with no request sent. | hardening + unit |
| The stress test was checked only at the walked average, not at the IOC limit (low). | The stressed value at the limit must be ≥ 0. | unit: "stressed value at the limit" |
| The exchange-open gate read index 0; KXBTC15M is on index 2 (low). | Reads `exchange_index_statuses[2]`. A missing entry counts as closed. | unit: "exchange status…" |
| A void or non-binary market never settled and blocked trading for good (low). | Settles at P&L 0, frees the exposure, and halts for review if LIVE. | hardening + unit |
| Paper results counted as the live record after switching to live (low). | Forward record and daily totals kept per mode. Paper positions are not restored into a live trader. | hardening: "LIVE restore…" |
| Duplicate WINDOW records after a restart (low). | Restored windows are not summarised again. | hardening |
| Resume through a GET with the token in the URL (low). | `POST /halt?on=0` with the `X-Admin-Token` header only. A repeated manual halt is written once. The 403 text no longer claims a restart clears halts. | hardening |
| A missing `expiration_value` parsed as 0 (found while testing). | Parsed as null. | unit |

Also added: on SIGTERM (Render stop or redeploy), the trader stops ticking, waits for an order in flight, writes `STOP` and exits.

**Second pass (2026-10-18).** The fix diff itself was then reviewed and verified adversarially in the same way. Its confirmed findings are also fixed and tested:

| Finding (verified severity) | Fix | Test |
|---|---|---|
| A provisional position restored after a restart was never reconciled, and reconciliation gave up after 20 tries, so trading could stay blocked for good (high). | Every provisional LIVE position is scheduled for lookup at restore. Retries run every 30 s, then every 5 min, with no limit. | hardening: "a restored provisional LIVE position is reconciled after a restart…" |
| A restart in dry run (the disarm step) skipped the lookup (medium). | The lookup needs only the credentials, not live mode. | same test, disarmed case |
| An order could be sent although its write-ahead `ORDER_ATTEMPT` record had just failed to write (low). | No order is sent and trading halts. | live_mock: "ledger write fails before an order…" |
| The day's trade count was not the same in-process and after a restart around provisional orders (low). | A provisional order is counted once, and uncounted if Kalshi shows no fill. | hardening: "tradesToday…" |
| A ledger-write halt could never clear while running, and the failed records were lost (low). | Failed records are queued, written in order once the disk is back, and the halt then clears. A torn last line is closed at open. | hardening: "ledger: failed writes are retried…" |
| The README described booking at the limit only (low). | Updated. | — |

Eight further candidates were rejected by the verifiers in this pass. One of them was hardened anyway: a ledger path that is a directory now halts trading instead of failing at boot. The other examples: a single "not found" lookup 5 s after a timeout, a 2xx reply without `fill_count` (which the spec requires), and an order missing from the first page of `GET /portfolio/orders`.

Twelve candidate findings were rejected by the verifiers as not reachable in the default or documented configuration. Examples: the fee schedule, configurable thresholds, and CPU-heavy public routes.

## Production readiness (2026-10-22)

**Trade-frequency funnel** (`/funnel`, persistent in the ledger). This is the 7-day replay below; its order book is **synthetic**.

| Stage | Windows |
|---|---|
| Evaluated | 663 |
| LOCKED at ≤ 0.2 % | 599 |
| Executable | 481 |
| Positive EV | 37 |
| Attempted | 37 |
| Filled (paper) | 37 |

Why the LOCKED windows were not traded:

| Reason | Windows |
|---|---|
| No edge at the market price (the engine's EV rule: the market already priced the side at about 99.x ¢) | 444 |
| Nobody selling the called side below 100 ¢ | 88 |
| LOCKED with less than the order time left | 30 |
| Data | 0 |
| Risk limits | 0 |

**Directional record** of all 599 LOCKED windows: 598 correct, 1 wrong. The one wrong call is the same as in the validation replay.

So the dominant gate is economic, and it is mathematically justified: by the time a call is LOCKED, the market usually prices it so high that a buy has no edge after the fee. It is not a defect. A live book will show the true split.

**Change from this analysis.** The trader's own 99 ¢ upper price cap was removed (now 99.9 ¢). It was stricter than the validated engine rule, which has no upper cap. With the 0.5 ¢ minimum edge, the EV checks alone reject anything above about 99.3 ¢, and 99.9 ¢ never passes. Paper trades rose from 33 to 37, all within the EV rule.

**Other additions:**
* A halt after the first live fill, for review.
* An account guard. When live, KXBTC15M orders from the last 20 min not placed by this trader, or positions it does not know about, halt it. This stops two traders running on one account.
* `TRADER_VIEW_TOKEN` on the data routes.
* Up to 3 IOC attempts per window while the signal stays valid, at least 1 s apart.
* The settled outcome of every LOCKED window is recorded as an `OUTCOME` record, off the trading tick.

**Live Kalshi public API check** (2026-10-22, read-only, no credentials):

| Check | Result |
|---|---|
| `GET /exchange/status` | Per-index breakdown present; index 2 trading active, read by the trader. |
| `GET /series/KXBTC15M` | `exchange_index` 2; `fee_type` quadratic; `fee_multiplier` 1, which matches the trader's fee formula. |
| Live open market | Parsed by the engine: ticker, strike, close time. |
| Live order book (`yes_dollars` / `no_dollars`) | Parsed by the engine into cents. |
| Trader's `marketResult` on a settled market | Returned `no` and the official value. |

Not checked here: the authenticated order calls. They need the Kalshi key on the service. `/livecheck` and the first live order (with the first-fill halt) are their check.

## `npm test` (test/run_all.js)

```
PASS unit          unit: 47/47 passed  (0.2 s)
PASS selftest      selftest: 10/10 passed  (0.2 s)
PASS live_mock     live_mock: 29/29 passed  (2.6 s)
PASS hardening     hardening: 18/18 passed  (15.0 s)
PASS engine_replay engine_replay: 12/12 passed  (37.9 s)
all suites passed
```

## unit (test/unit_test.js)

```
ok   BUY when every gate passes; plan within $5 incl. fee
ok   blocks: not LOCKED (HIGH CONFIDENCE)
ok   blocks: REVERSAL WARNING
ok   blocks: flip risk above 0.2 % even if the engine says LOCKED
ok   blocks: DATA UNRELIABLE
ok   blocks: hard gate on a LOCKED signal
ok   blocks: engine not warm (volatility envelope)
ok   blocks: engine basis cold
ok   blocks: engine says SIT OUT (no edge)
ok   blocks: engine says TOO LATE
ok   blocks: market disagrees (ask 85 c)
ok   blocks: price above 99 c
ok   blocks: stale book
ok   blocks: no offers
ok   blocks: too thin for the size
ok   blocks: edge at the exact limit too small
ok   blocks: already entered this window
ok   blocks: other side in this window
ok   blocks: attempts used up
ok   blocks: halted
ok   blocks: order in flight
ok   blocks: daily loss limit
ok   blocks: consecutive losses
ok   blocks: daily trade count
ok   blocks: open exposure
ok   blocks: not a KXBTC15M market
ok   blocks: implausible strike
ok   blocks: window closed
ok   blocks: exchange not confirmed open when required
ok   DOWN call buys NO from the NO asks
ok   sizing never exceeds the cap at any price 50-99.9 c
ok   sizing: fee is Kalshi ceil(0.07 C P (1-P)) to the cent
ok   walk: multi-level fill
ok   walk: not enough depth -> null
ok   order mapping YES / NO and refusals
ok   ledger: hash chain verifies, and an edited line is detected
ok   blocks: stressed value at the limit < 0 (engine stress passed only at the walked average)
ok   fill price booking: DOWN fill reported in YES terms (2 c) or NO terms (98 c) both book 98 c; implausible -> the limit
ok   funnel: each reason maps to the first funnel stage that blocked it
ok   funnel: summary separates LOCKED predictions, the trade funnel and settled P&L
ok   retry: after an unfilled IOC the next attempt waits RETRY_SPACING_MS, then may go while the signal is valid
ok   order outcome: HTTP 503 / 502 / 408 are unknown (the order may exist), 400 is rejected, market_not_found is a routing miss
ok   order outcome: a key that cannot sign is a rejection with no request sent
ok   order result: CreateOrderV2Response (top-level fill_count, average_fill_price, average_fee_paid)
ok   exchange status: reads exchange index 2 (KXBTC15M), not the top-level index 0; a missing index fails closed
ok   market result: a finalized market without yes/no is non-binary; an open one is not settled
ok   findOrder: matches client_order_id in GetOrders and reads fill_count_fp and costs
unit: 47/47 passed
```

## selftest (trader /selftest, no network)

```
ok   sizing: $5 at 99 c buys 5 contracts for <= $5 incl. fee
ok   sizing: $5 at 90 c buys 5 contracts (5 x 0.90 + fee 0.04 = 4.54; 6 would cost 5.44)
ok   walk: limit is the worst level needed
ok   order: UP = bid YES at the limit
ok   order: DOWN at 97 c = ask YES at 0.03
ok   order: refuses a non-KXBTC15M ticker
ok   engine: byte-identical to the validated 2.8.1 build
ok   engine: LOCKED threshold is the trader threshold
ok   cap: max trade <= absolute cap
ok   engine self-test (149/150; at LOCK_MAX_FLIP=0.002 the 0.5 %-threshold check that a 0.468 % flip IS locked is expected to fail) :: {"fails":["2.6 quiet tape: a 99.6% model call is NOT locked; active tape: a 99.1% model call IS locked"]}
selftest: 10/10 passed
```

## live_mock (test/live_mock_test.js)

```
ok   mode is LIVE only when armed with the phrase and keys
ok   every signed request verifies with the public key (RSA-PSS SHA-256 over ts+METHOD+path)
ok   first order: bid YES 5 @ 0.9900 IOC, deterministic client id, exchange_index -1
ok   second entry in the same window refused (no POST)
ok   next window refused while the $5 position is unsettled (max open exposure)
ok   DOWN no-fill: ask YES at 0.0100, no position
ok   market_not_found skips without halting
ok   exactly 4 orders sent (fill, no-fill, routing miss, rejection)
ok   win settles: +$0.04 (5 x $1 - $4.96), forward 1/1
ok   rejection (HTTP 400) latches a halt
ok   no key material or admin token in /config /health /live /stats or the ledger
ok   resume with a wrong token is refused
ok   ledger hash chain verifies
ok   every POST was a KXBTC15M IOC buy within $5
ok   no response: outcome unknown, trading halted
ok   while halted nothing is sent
ok   timeout: the unknown order is booked provisionally as a full fill at the limit ($4.96)
ok   timeout: reconcile finds the executed order by client_order_id and books it (5 contracts, $4.96)
ok   HTTP 503 on order create is an unknown outcome (halt + provisional booking), not a plain rejection
ok   reconcile: no fill on Kalshi -> the provisional position is removed, nothing settles
ok   first live fill halts trading until a person resumes (FIRST_FILL_HALT default on)
ok   orders on the account from another trader halt this one
ok   an untracked KXBTC15M position on the account halts this trader
ok   a clean account passes the guard
ok   ledger write fails before an order: no order sent, trading halted
ok   loss settles: -$4.96, forward 0/1
ok   after a loss trading halts for review
ok   LIVE=1 without the arm phrase is a DRY-RUN
ok   dry run sends no order to Kalshi (paper fill only)
live_mock: 29/29 passed
```

## hardening (test/hardening_test.js)

```
ok   restart keeps today's realised loss and trade count; the daily limit still blocks after a resume + restart
ok   a halt 2,500 lines back is restored
ok   restart mid-order: halts, books the order provisionally, marks the window used; a second restart does not double it
ok   LIVE restore: paper positions dropped, real ones kept; forward record per mode; paper losses do not count toward the live day
ok   LIVE does not arm without an explicit TRADER_LEDGER_FILE
ok   LIVE does not arm with a private key that cannot sign
ok   a key with its newlines collapsed (accepted by the engine) arms and signs
ok   a failing ledger write is a halt reason
ok   restart does not write duplicate WINDOW records
ok   a finalized market without a yes/no result settles at P&L 0 and frees the exposure
ok   tradesToday: provisional order later reconciled as unfilled counts 0 after a restart
ok   ledger: failed writes are retried in order and the error clears when they land
ok   a restored provisional LIVE position is reconciled after a restart (armed, and disarmed with credentials)
ok   /livecheck needs the admin token (403 without or with a wrong one) and sends no CORS header
ok   resume is POST-only with the X-Admin-Token header (GET and a query token are refused); a repeated halt is written once
ok   a malformed /engine/ route is refused and the process stays up; a valid one still works
ok   TRADER_VIEW_TOKEN protects the data routes (/stats, /funnel, /ledger); /health stays open
ok   ?n= that is not a number falls back to the default
hardening: 18/18 passed
```

## engine_replay, default range (test/engine_replay_test.js: 2026-08-01, 96 windows, as run by npm test)

The book is synthetic (see above). "Top blocks" counts the trader ticks on which a LOCKED window was not bought, by the first reason given.

```
{
 "range": "2026-08-01T00:00:00Z .. 2026-08-02T00:00:00Z",
 "warmSec": 86400,
 "engineSha256": "55d0555c65e4f8a4",
 "lockMaxFlip": 0.002,
 "windows": 96,
 "evaluatedSeconds": 28800,
 "secondsWithSyntheticBook": 28765,
 "windowsLocked": 77,
 "windowsEngineTradeNow": 2,
 "buyTicks": 2,
 "orders": 2,
 "fills": 2,
 "settled": 2,
 "won": 2,
 "lost": 0,
 "paperPnlUsd": 0.46,
 "halts": [],
 "topBlocksWhileLocked": [
  [
   "engine says SIT OUT / LOCKED — TOO LATE: LOCKED UP, but nobody is selling UP: th",
   952
  ],
  [
   "engine says SIT OUT / LOCKED — TOO LATE: LOCKED DOWN, but nobody is selling DOWN",
   892
  ],
  [
   "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED UP, but no edge at #¢ (worth",
   601
  ],
  [
   "engine says TOO LATE / LOCKED — TOO LATE: LOCKED DOWN with # s left: an order ne",
   599
  ],
  [
   "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED DOWN, but no edge at #¢ (wor",
   560
  ],
  [
   "engine says TOO LATE / LOCKED — TOO LATE: LOCKED UP with # s left: an order need",
   539
  ]
 ],
 "funnel": {
  "locked": 77,
  "executable": 62,
  "positiveEv": 2,
  "attempted": 2,
  "filled": 2,
  "missedBy": {
   "data": 0,
   "timing": 6,
   "liquidity": 9,
   "ev": 60,
   "risk": 0,
   "unfilled": 0,
   "other": 0
  },
  "firstLockedTauSec": {
   "median": 52.3,
   "p10": 22.3,
   "p90": 91.3,
   "n": 77
  },
  "topMissedReasons": [
   [
    "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED DOWN, but no edge at #¢ (worth it only",
    31
   ],
   [
    "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED UP, but no edge at #¢ (worth it only a",
    29
   ],
   [
    "engine says SIT OUT / LOCKED — TOO LATE: LOCKED UP, but nobody is selling UP: the market t",
    6
   ],
   [
    "engine says TOO LATE / LOCKED — TOO LATE: LOCKED DOWN with # s left: an order needs # s",
    4
   ],
   [
    "engine says SIT OUT / LOCKED — TOO LATE: LOCKED DOWN, but nobody is selling DOWN: the mark",
    3
   ]
  ],
  "directional": {
   "withOutcome": 77,
   "correct": 77,
   "wrong": 0
  }
 },
 "regression": {
  "windows": 96,
  "identical": 96,
  "differences": []
 },
 "wallSec": 38,
 "note": "SYNTHETIC book from real Kalshi prints (15 s look-back); fills/P&L exercise the order path only and are not an execution estimate"
}
  fill KXBTC15M-26AUG010715-15 DOWN 5 @ 99.1 c, cost $4.97 -> WON 0.03
  fill KXBTC15M-26AUG011315-15 DOWN 5 @ 90.7 c, cost $4.57 -> WON 0.43
ok   every order sent: LOCKED, flip risk <= 0.2 %, >= 15 s left, 90 to <99.9 c, cautious edge >= 0.5 c at the limit, <= $5, DRY-RUN :: 2 orders, 0 violating
ok   at most one fill per window :: 2 fills in 2 windows
ok   nothing sent after a halt :: no halt
ok   ledger hash chain verifies :: {"ok":true,"lines":181,"head":"5326757ed8cf9bbb348b5d140f994b1ea06f7bdc3da50d2f4581a5702c953a9e"}
ok   no tick errors :: 0
ok   every eligible contract evaluated (one WINDOW record each) :: 96 / 96
ok   every fill settled with the official Kalshi result :: 2 / 2
ok   funnel: LOCKED / attempted / filled counts match the windows and orders :: {"locked":77,"executable":62,"positiveEv":2,"attempted":2,"filled":2}
ok   funnel: every LOCKED window not traded has a recorded reason :: {"data":0,"timing":6,"liquidity":9,"ev":60,"risk":0,"unfilled":0,"other":0}
ok   directional record: a settled outcome for every LOCKED window :: 77 / 77
ok   directional record: wrong first-LOCKED calls equal the validation replay's :: 0 vs 0
ok   first LOCKED (second and side) identical to the 0.2 % validation replay :: 96 / 96
engine_replay: 12/12 passed
```

## engine_replay, extended (PR_REPLAY_TO=2026-08-08T00:00:00Z: 7 days, 663 windows)

This run was made on 2026-10-22, with the funnel and the 99.9 ¢ price cap. The run covers 7 days. Nine windows are absent from `markets_usdc.ndjson`, removed by the validation's data cleaning.

```
{
 "range": "2026-08-01T00:00:00Z .. 2026-08-08T00:00:00Z",
 "warmSec": 86400,
 "engineSha256": "55d0555c65e4f8a4",
 "lockMaxFlip": 0.002,
 "windows": 663,
 "evaluatedSeconds": 198900,
 "secondsWithSyntheticBook": 198673,
 "windowsLocked": 599,
 "windowsEngineTradeNow": 37,
 "buyTicks": 37,
 "orders": 37,
 "fills": 37,
 "settled": 37,
 "won": 37,
 "lost": 0,
 "paperPnlUsd": 7.17,
 "halts": [],
 "topBlocksWhileLocked": [
  [
   "engine says SIT OUT / LOCKED — TOO LATE: LOCKED UP, but nobody is selling UP: th",
   10241
  ],
  [
   "engine says SIT OUT / LOCKED — TOO LATE: LOCKED DOWN, but nobody is selling DOWN",
   9692
  ],
  [
   "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED UP, but no edge at #¢ (worth",
   5806
  ],
  [
   "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED DOWN, but no edge at #¢ (wor",
   5210
  ],
  [
   "engine says TOO LATE / LOCKED — TOO LATE: LOCKED DOWN with # s left: an order ne",
   4472
  ],
  [
   "engine says TOO LATE / LOCKED — TOO LATE: LOCKED UP with # s left: an order need",
   4332
  ]
 ],
 "funnel": {
  "locked": 599,
  "executable": 481,
  "positiveEv": 37,
  "attempted": 37,
  "filled": 37,
  "missedBy": {
   "data": 0,
   "timing": 30,
   "liquidity": 88,
   "ev": 444,
   "risk": 0,
   "unfilled": 0,
   "other": 0
  },
  "firstLockedTauSec": {
   "median": 57.3,
   "p10": 24.3,
   "p90": 128.3,
   "n": 599
  },
  "topMissedReasons": [
   [
    "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED DOWN, but no edge at #¢ (worth it only",
    232
   ],
   [
    "engine says SIT OUT / LOCKED — DO NOT TRADE: LOCKED UP, but no edge at #¢ (worth it only a",
    210
   ],
   [
    "engine says SIT OUT / LOCKED — TOO LATE: LOCKED UP, but nobody is selling UP: the market t",
    46
   ],
   [
    "engine says SIT OUT / LOCKED — TOO LATE: LOCKED DOWN, but nobody is selling DOWN: the mark",
    42
   ],
   [
    "engine says TOO LATE / LOCKED — TOO LATE: LOCKED UP with # s left: an order needs # s",
    16
   ]
  ],
  "directional": {
   "withOutcome": 599,
   "correct": 598,
   "wrong": 1
  }
 },
 "regression": {
  "windows": 663,
  "identical": 663,
  "differences": []
 },
 "wallSec": 249.1,
 "note": "SYNTHETIC book from real Kalshi prints (15 s look-back); fills/P&L exercise the order path only and are not an execution estimate"
}
  fill KXBTC15M-26AUG010715-15 DOWN 5 @ 99.1 c, cost $4.97 -> WON 0.03
  fill KXBTC15M-26AUG011315-15 DOWN 5 @ 90.7 c, cost $4.57 -> WON 0.43
  fill KXBTC15M-26AUG022230-30 DOWN 5 @ 97.5 c, cost $4.89 -> WON 0.11
  fill KXBTC15M-26AUG030015-15 DOWN 5 @ 90.9 c, cost $4.58 -> WON 0.42
  fill KXBTC15M-26AUG030130-30 DOWN 5 @ 98.3 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG030200-00 UP 5 @ 97.4 c, cost $4.88 -> WON 0.12
  fill KXBTC15M-26AUG030845-45 UP 5 @ 90.8 c, cost $4.57 -> WON 0.43
  fill KXBTC15M-26AUG030930-30 DOWN 5 @ 95.6 c, cost $4.8 -> WON 0.2
  fill KXBTC15M-26AUG031300-00 UP 5 @ 90 c, cost $4.54 -> WON 0.46
  fill KXBTC15M-26AUG040215-15 DOWN 5 @ 98.4 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG040745-45 UP 5 @ 91.6 c, cost $4.61 -> WON 0.39
  fill KXBTC15M-26AUG041030-30 UP 5 @ 90 c, cost $4.54 -> WON 0.46
  fill KXBTC15M-26AUG041315-15 UP 5 @ 98.2 c, cost $4.92 -> WON 0.08
  fill KXBTC15M-26AUG041330-30 UP 5 @ 98.3 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG041345-45 DOWN 5 @ 93.3 c, cost $4.7 -> WON 0.3
  fill KXBTC15M-26AUG041515-15 UP 5 @ 98.7 c, cost $4.94 -> WON 0.06
  fill KXBTC15M-26AUG051300-00 DOWN 5 @ 98.4 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG051545-45 DOWN 5 @ 91.2 c, cost $4.59 -> WON 0.41
  fill KXBTC15M-26AUG051615-15 UP 5 @ 97.3 c, cost $4.88 -> WON 0.12
  fill KXBTC15M-26AUG051630-30 UP 5 @ 93.1 c, cost $4.69 -> WON 0.31
  fill KXBTC15M-26AUG060530-30 DOWN 5 @ 98 c, cost $4.91 -> WON 0.09
  fill KXBTC15M-26AUG060600-00 UP 5 @ 98.8 c, cost $4.95 -> WON 0.05
  fill KXBTC15M-26AUG061100-00 DOWN 5 @ 96.1 c, cost $4.82 -> WON 0.18
  fill KXBTC15M-26AUG061215-15 DOWN 5 @ 91.3 c, cost $4.6 -> WON 0.4
  fill KXBTC15M-26AUG061230-30 UP 5 @ 99.1 c, cost $4.97 -> WON 0.03
  fill KXBTC15M-26AUG061715-15 UP 5 @ 96.4 c, cost $4.84 -> WON 0.16
  fill KXBTC15M-26AUG062115-15 UP 5 @ 97.2 c, cost $4.87 -> WON 0.13
  fill KXBTC15M-26AUG062130-30 UP 5 @ 98.7 c, cost $4.94 -> WON 0.06
  fill KXBTC15M-26AUG062215-15 DOWN 5 @ 99.2 c, cost $4.97 -> WON 0.03
  fill KXBTC15M-26AUG062345-45 UP 5 @ 95.3 c, cost $4.78 -> WON 0.22
  fill KXBTC15M-26AUG070230-30 UP 5 @ 98.9 c, cost $4.96 -> WON 0.04
  fill KXBTC15M-26AUG070515-15 UP 5 @ 95.1 c, cost $4.77 -> WON 0.23
  fill KXBTC15M-26AUG070630-30 UP 5 @ 98.6 c, cost $4.94 -> WON 0.06
  fill KXBTC15M-26AUG070930-30 DOWN 5 @ 99.2 c, cost $4.97 -> WON 0.03
  fill KXBTC15M-26AUG071045-45 DOWN 5 @ 98.3 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG071600-00 DOWN 5 @ 90.2 c, cost $4.55 -> WON 0.45
  fill KXBTC15M-26AUG071745-45 UP 5 @ 92.7 c, cost $4.67 -> WON 0.33
ok   every order sent: LOCKED, flip risk <= 0.2 %, >= 15 s left, 90 to <99.9 c, cautious edge >= 0.5 c at the limit, <= $5, DRY-RUN :: 37 orders, 0 violating
ok   at most one fill per window :: 37 fills in 37 windows
ok   nothing sent after a halt :: no halt
ok   ledger hash chain verifies :: {"ok":true,"lines":1410,"head":"74ba4a5e90d4873ae7bde56e211a5c051de2b99f8c450ed345d392f982ba3121"}
ok   no tick errors :: 0
ok   every eligible contract evaluated (one WINDOW record each) :: 663 / 663
ok   every fill settled with the official Kalshi result :: 37 / 37
ok   funnel: LOCKED / attempted / filled counts match the windows and orders :: {"locked":599,"executable":481,"positiveEv":37,"attempted":37,"filled":37}
ok   funnel: every LOCKED window not traded has a recorded reason :: {"data":0,"timing":30,"liquidity":88,"ev":444,"risk":0,"unfilled":0,"other":0}
ok   directional record: a settled outcome for every LOCKED window :: 599 / 599
ok   directional record: wrong first-LOCKED calls equal the validation replay's :: 1 vs 1
ok   first LOCKED (second and side) identical to the 0.2 % validation replay :: 663 / 663
engine_replay: 12/12 passed
```

## How to reproduce

```
cd pinradar-trader
npm test                                                     # all suites; engine_replay needs PR_DATA (default /home/user/data_val)
PR_REPLAY_TO=2026-08-08T00:00:00Z node test/engine_replay_test.js
bash ../trader-archive/live-trader-4.17/verify_archive.sh    # the archived v4.17 equals main
```
