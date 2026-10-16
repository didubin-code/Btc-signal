# Pin Radar Trader 5.0: test results

These tests were actually run on 2026-10-16, offline.
* Node v22.22.0.
* No real network calls to Kalshi and no orders.
* The live-order path runs only against a local mock.

The outputs below are verbatim.

## What the tests establish

* **Engine.** `engine/pinradar_server.js` is byte-identical to btc-ai-backend `pinradar-research/2.8.1/dist/pinradar_server.js`. Both hash to SHA-256 `55d0555c65e4f8a4e00355aaa2db7d1f0574918978f3749d6c8ff55d97522a0d`.
  * 2.8.1 is the corrected engine. Its own suite is recorded in `pinradar-research/2.8.1/TEST_RESULTS.md`: self-test 150/150, late-LOCKED 15/15, DATA UNRELIABLE 6/6, page 17/17, and the 2.8 suites. That suite was not re-run here.
  * Here, the engine runs inside the trader with `LOCK_MAX_FLIP=0.002`. Its self-test passes 149/150. The one failure is the expected assertion that a 0.468 % flip IS locked, which holds only at the 0.5 % threshold. That is the threshold change, not a defect.
* **Regression.** The trader runs its real main loop with the embedded engine, the two read-only readings per tick and the policy. It reproduces the validation's 0.2 % replay (`replay/thr02_usdc.ndjson`) exactly: the first LOCKED second and side are identical in **663 / 663** windows (Aug 1–8, 2026). Every contract in range was evaluated.
* **Execution and safety.** These run against a local mock Kalshi API with a generated RSA key:
  * request signatures;
  * order JSON (YES/NO mapping, IOC, deterministic client id);
  * the five order outcomes (fill, no-fill, routing miss, rejection, timeout);
  * halts on rejection, unknown outcome and loss;
  * a refused resume with a wrong token;
  * the $5 open-exposure limit, and one entry per window;
  * an unarmed `LIVE=1` sending nothing;
  * no key material in any endpoint or the ledger.
* **Not established.** Real fills, real Kalshi order-schema acceptance and profitability.
  * The replay's order book is **synthetic**: it is reconstructed from real Kalshi prints in the previous 15 s.
  * Its 33 paper fills (all won, +$7.05) exercise the order path only. **They are not an execution or profit estimate.** The print-based execution study in the validation report is the reference, and it shows the small-size edge decaying to about zero by September 2026.
  * The synthetic book keeps prints for 15 s, so it often contains stale lower prices (median paper fill 96.4 ¢, minimum 90 ¢). A live book at a LOCKED moment is usually at 99 ¢ or more.

## `npm test` (test/run_all.js)

```
PASS unit          unit: 36/36 passed  (0.1 s)
PASS selftest      selftest: 10/10 passed  (0.3 s)
PASS live_mock     live_mock: 20/20 passed  (2.1 s)
PASS engine_replay engine_replay: 8/8 passed  (50.5 s)
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
unit: 36/36 passed
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
ok   loss settles: -$4.96, forward 0/1
ok   after a loss trading halts for review
ok   LIVE=1 without the arm phrase is a DRY-RUN
ok   dry run sends no order to Kalshi (paper fill only)
live_mock: 20/20 passed
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
 "buyTicks": 1,
 "orders": 1,
 "fills": 1,
 "settled": 1,
 "won": 1,
 "lost": 0,
 "paperPnlUsd": 0.43,
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
 "regression": {
  "windows": 96,
  "identical": 96,
  "differences": []
 },
 "wallSec": 54.7,
 "note": "SYNTHETIC book from real Kalshi prints (15 s look-back); fills/P&L exercise the order path only and are not an execution estimate"
}
  fill KXBTC15M-26AUG011315-15 DOWN 5 @ 90.7 c, cost $4.57 -> WON 0.43
ok   every order sent: LOCKED, flip risk <= 0.2 %, >= 15 s left, 90-99 c, <= $5, DRY-RUN :: 1 orders, 0 violating
ok   at most one fill per window :: 1 fills in 1 windows
ok   nothing sent after a halt :: no halt
ok   ledger hash chain verifies :: {"ok":true,"lines":100,"head":"59add665b1ae3ae595db4e2b41d4e792a9859196ccdb8e9c572d2efe94da9823"}
ok   no tick errors :: 0
ok   every eligible contract evaluated (one WINDOW record each) :: 96 / 96
ok   every fill settled with the official Kalshi result :: 1 / 1
ok   first LOCKED (second and side) identical to the 0.2 % validation replay :: 96 / 96
engine_replay: 8/8 passed
```

## engine_replay, extended (PR_REPLAY_TO=2026-08-08T00:00:00Z: 7 days, 663 windows)

The run covers 7 days. Nine windows are absent from `markets_usdc.ndjson`, removed by the validation's data cleaning.

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
 "buyTicks": 33,
 "orders": 33,
 "fills": 33,
 "settled": 33,
 "won": 33,
 "lost": 0,
 "paperPnlUsd": 7.05,
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
 "regression": {
  "windows": 663,
  "identical": 663,
  "differences": []
 },
 "wallSec": 337.2,
 "note": "SYNTHETIC book from real Kalshi prints (15 s look-back); fills/P&L exercise the order path only and are not an execution estimate"
}
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
  fill KXBTC15M-26AUG061715-15 UP 5 @ 96.4 c, cost $4.84 -> WON 0.16
  fill KXBTC15M-26AUG062115-15 UP 5 @ 97.2 c, cost $4.87 -> WON 0.13
  fill KXBTC15M-26AUG062130-30 UP 5 @ 98.7 c, cost $4.94 -> WON 0.06
  fill KXBTC15M-26AUG062345-45 UP 5 @ 95.3 c, cost $4.78 -> WON 0.22
  fill KXBTC15M-26AUG070230-30 UP 5 @ 98.9 c, cost $4.96 -> WON 0.04
  fill KXBTC15M-26AUG070515-15 UP 5 @ 95.1 c, cost $4.77 -> WON 0.23
  fill KXBTC15M-26AUG070630-30 UP 5 @ 98.6 c, cost $4.94 -> WON 0.06
  fill KXBTC15M-26AUG071045-45 DOWN 5 @ 98.3 c, cost $4.93 -> WON 0.07
  fill KXBTC15M-26AUG071600-00 DOWN 5 @ 90.2 c, cost $4.55 -> WON 0.45
  fill KXBTC15M-26AUG071745-45 UP 5 @ 92.7 c, cost $4.67 -> WON 0.33
ok   every order sent: LOCKED, flip risk <= 0.2 %, >= 15 s left, 90-99 c, <= $5, DRY-RUN :: 33 orders, 0 violating
ok   at most one fill per window :: 33 fills in 33 windows
ok   nothing sent after a halt :: no halt
ok   ledger hash chain verifies :: {"ok":true,"lines":795,"head":"240acc042153c135d3691ef6893e2fcebf3f6aa92883eb3fa39508d11703095d"}
ok   no tick errors :: 0
ok   every eligible contract evaluated (one WINDOW record each) :: 663 / 663
ok   every fill settled with the official Kalshi result :: 33 / 33
ok   first LOCKED (second and side) identical to the 0.2 % validation replay :: 663 / 663
engine_replay: 8/8 passed
```

## How to reproduce

```
cd pinradar-trader
npm test                                                     # all suites; engine_replay needs PR_DATA (default /home/user/data_val)
PR_REPLAY_TO=2026-08-08T00:00:00Z node test/engine_replay_test.js
bash ../trader-archive/live-trader-4.17/verify_archive.sh    # the archived v4.17 equals main
```
