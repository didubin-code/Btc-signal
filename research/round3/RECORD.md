# BTC Pin Radar investigation: authoritative record (round 3)

Started 2026-11-15 01:40 UTC. Supersedes nothing; it consolidates. Earlier files stay as evidence and are linked.
Root: `/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/` (written `$SC` below). Checkpoint: `$SC/round3/CHECKPOINT.md`.
Execution log (time-stamped, append-only): `$SC/r30/live/EXECUTION_LOG.md`.

## A. Code identities and deployment status (verified)

| Item | Identity | Status |
|---|---|---|
| Production server | release I2, commit `3125bbc022fab0240132a432c0d947c1330d3235`, file sha256 `ca51a0c6f7cfd117f4db6f75ca1dec56e7c277674c97920fc82706b01548040f`, config hash `8245f376…` | live on Render `btc-pin-radar`; calibration factors 2.02 / 1.0 / 0.52; LOCKED at flip ≤ 0.5 %; REVERSAL WARNING at 10 % |
| Pre-I2 server (rollback target) | sha256 `0efd86c9…`, blob `add858df…` | one authorised revert available (R30/R31 rules) |
| Live page | H1.1, sha256 `8bf43b5758d8877a53a93958c85a9cfd3e36bfc8bd137fd3a15e9c447b93a498`, commit `fe16325a…` on `main` of `didubin-code/Btc-signal` | served; verified 23:46 UTC Nov 14 |
| Page H1.5 (local) | commit `d5587f2333c532278a247dfe8faac6a0cee4e857`, sha256 `eb572aa7…`; worktree `$SC/h15/wt` | NOT published; superseded by H1.6 as the candidate; display safeguard only |
| **Page H1.6 (local, PR9 candidate)** | commit `c1d66cffe42e16abc01cd40713d1b2f233e5bb5c`, sha256 `c13a605fab3be9e08d1785f680e3face11e4ec8e4a710f39495bf07177850f02`; worktree `$SC/h16/wt`, bundle `$SC/h16/h16_release.bundle`; `$SC/h16/README_H16.md` | NOT published; H1.5 + EXIT ALERT for the held position; 1,314 of 1,314 checks; publish only on the owner's word after the PR9 decision |
| Superseded page builds | H1.4 (`b2f08048`, earlier `016a0e24`, `153591d1`), H1.3 (`9ac99465`), H1.2 (`33dafbca`) | never publish |
| Observer | `pinradar-observer` (read-only) | unchanged |
| Suspended services | btc-ai-backend, Live Trader (Auto-Deploy off), btc-shadow-trader | stay suspended |
| Scheduled task | `trig_01AWURAiWTamv5T6YUir94XR`, every 6 h at :31 UTC: I2 ingestion reading + live two-test scoreboard | running; stops at 288 eligible windows (about Nov 17) or after a revert |

## B. Verified findings (with the exact evidence)

B1. **Your entry rule, as the screen showed it, loses about 1 in 750.** "≈0.2 %" is one significant figure, so it first appears at a
centre below 0.25 %. Replay 2022–2026 (production engine, four non-repeating sets): 743 of 557,669 = 1 in 751. Evidence:
`$SC/final_directive/wf/WF_RESULT.txt`.

B2. **The server's risk at that entry was not understated on average, in any volatility bucket.** PR7 (2023–2026, 571,222
windows, one entry per window, day-bootstrap): observed/expected losses at the displayed entry = 0.81 pooled; by bucket
0.47, 0.47, 0.60, 0.58, 1.11, 0.70, 0.56. A refitted active factor (fit 2019–2022) failed its frozen criteria (O/E 2.7 and 1.8).
Evidence: `$SC/calib_r1/PR7_RESULT.txt`, declaration `PR7_DECLARATION.md` (sha256 `e0019721…`).

B3. **On real Kalshi settlements the picture is NOT the same, and the difference is conditional.** Splitting PR7's data: the 2026
official-results set (real settlements, replay on the Binance feed, 26,330 displayed entries) has O/E 1.23 (64 lost, 52.2
expected; 1 in 411), against 0.41–0.71 on the proxy-settlement sets. The excess is concentrated: entries with under 30 s left
O/E 6.27 (46 of 3,609 lost, 1 in 78); cushion under 10 bps 1.80; margin-inclusive risk above 0.7 % 9.53. Entries with 30–119 s
left: O/E 0.36–0.51 (17 of 17,508, 1 in 1,030). 36 of the 64 real-settlement losses show NO reversal in the replay feed at all:
they are basis losses (the feed's 60 s average and Kalshi's BRTI disagreed by a few dollars), not visible moves. Caveat: the
replay feed (Binance USDT) carries a far larger and noisier basis to BRTI than the live 3-venue index, and the live server
switches to the official BRTI accumulator inside the final minute (all 192 live entries show ref=OFFICIAL; |official − proxy| at
entry median 2.7 USD, p90 7.2, max 21.4). So the live rate of basis losses is expected to be lower; it is not yet measured
(0 losses in 28 live entries under 30 s). Evidence: `$SC/round3/CONDITIONAL.txt`.

B4. **Proxy flatness, delivery delay, the I2 restart and sampling artifacts are ruled out as causes.** Tape alive (125–175
trades in the 30 s before each move); engine rebuilt from raw Coinbase/Kraken trades reproduces production (LOCKED same in
97 % of seconds); 2,100 of 2,100 decisions since the restart identical on both builds. Evidence:
`$SC/final_directive/INCIDENTS.md`, `fidelity/FIDELITY.txt`, `$SC/incident_20261114T0015Z/INCIDENT_FINDINGS.md`.

B5. **The server's own LOCKED withdrawal is fast; its REVERSAL WARNING is slow.** Withdrawal (flip risk of the held side
reaching 0.5 %) came 0.4 s (Nov 13) and 0.6 s (Nov 11) after the first adverse source trade, and 9 s (Nov 7) and 24 s
(Nov 9) before it. The warning (10 %) came 6.4 s, 3.6 s, 0.9 s and 0.8 s after the move. Evidence: `$SC/round3/INCIDENTS_EXEC.md`
(this round), `$SC/final_directive/incidents/comparison.json`.

B6. **Kalshi kept paying near 99.8–99.9¢ for YES for seconds after each move.** Verified from Kalshi's own public trade
record and, for Nov 13, from the order books in the owner's evidence ZIP (sha256 `a76da70a…`, `tape.json`, 300 rows for
`KXBTC15M-26NOV131915-15`):
- Nov 13: book at 00:13:29.215 UTC best YES bid 99.8 × 137,098 contracts (age 303 ms); 00:13:30.215 bid 99.8 × 16,463 (age 620 ms);
  00:13:31–35 bid 99.9 × 47,000–218,000; 00:13:36.294 bid 99.8 × 23,335; 00:13:37.294 bid 91.7 × 111 (age 297 ms); 00:13:38 81; 00:13:39 45.
  Trades: YES traded at 99.9 (sellers hitting the bid) until +6.56 s after the move; first trade below 99 at +6.71 s, below 90 at +7.72 s,
  below 50 at +8.95 s. The REVERSAL WARNING was issued at +6.4 s, 0.3 s before the bid collapsed.
- Nov 11: last YES trade ≥ 99.5 at +1.2 s, ≥ 99 at +3.8 s, ≥ 98 at +4.2 s, ≥ 95 at +5.6 s; first below 90 at +5.8 s. Warning at +3.6 s.
- Nov 7: YES traded at 99.9 until +1.15 s, then 74–99.9 within the next second; LOCKED had been withdrawn 9 s before the move.
- Nov 9 (DOWN call): the move itself happened inside one second (YES 0.6¢ → 90¢); LOCKED had been withdrawn 24 s before.
Snapshots and prints are not guaranteed fills; sizes at the best bid on Nov 13 were large (16,000–218,000 contracts).
Evidence: `$SC/round3/exec/nov*_trades.json`, `$SC/round3/exec/nov13_book.json`.

B7. **The two-test page standard (H1.3–H1.5) calls when nothing is left to buy.** 0 of 48 live calls had an offer on the called
side. Evidence: `$SC/final_directive/audit/exec_feasibility.json`, `$SC/calib_r1/usefulness/`.

B9. **The page polls the server about four times a second** (via=radar signals every ≈0.25 s on Nov 13), so page latency is
≈0.25 s, not 1 s. On Nov 13 the page received the first non-LOCKED reading at 00:13:29.693 (+0.38 s after the move, centre
0.83 %), centre ≥ 1 % at +0.68 s and ≥ 2 % at +0.89 s; Kalshi's 99.8–99.9 bid lasted until +7.0 s. Evidence: `$SC/round3/INCIDENTS_EXEC.md`.

B10. **In the replays, a risk step is an early and selective exit signal for reversal losses.** Proxy sets 2022–2026, 683
displayed-entry losses: the held side's risk reached 0.5 % in 679, 1 % in 621, 2 % in 581 and 10 % in 449 within 10 s of the
state change; median lead before the cushion crossed zero 14 s (T1), 11 s (T2 1 %), 9 s (T3 2 %), 4 s (T4 10 %). Winners reaching
each: 5.2 %, 1.9 %, 1.0 %, 0.23 % of entries. On the real-settlement 2026 set the basis losses (no visible move) are not caught by
any step: 36 of 64 had no step at all. Evidence: `$SC/round3/LEADS.txt`.

B8. **I2 ingestion**: 100 of 100 eligible windows since the deploy with no missing decision (before: 36–46 of every 96 had a gap).
Before/after, not proof of cause. Evidence: `$SC/r30/live/EXECUTION_LOG.md`.

B11. **PR9, live set (Nov 12–15, 192 displayed entries, Kalshi sale prints for all, order books for 12; corrected script):** hold
total −58.2 ¢ per contract over all entries (191 wins of 0.1–2.7 ¢ each after the entry fee, one loss of −99.9); exit at the first
1 % step (T2) with a 3 s reaction: fired in 10 entries (5.2 %), policy total +28.3 ¢ (+86.5 vs hold); the one loss exited at 99.9
(book); 9 unnecessary exits costing 0.2–5.6 ¢ each (median 1.2, mean 1.5), priced from actual sales into the bid. At 2 % (T3):
fired in 4 (2.1 %), policy +33.1 ¢, 3 unnecessary exits (median 2.4 ¢). The REVERSAL WARNING (T4) with a 3 s reaction: the loss
exited at 43 ¢ (policy −21.4 ¢). Evidence: `$SC/round3/exec/pr9_live.txt|json`. The result is dominated by one loss; it is a
mechanics check, not a rate estimate.

B12. **PR9, replay-joined set (Oct 15–Nov 12 2026; engine replay on the Binance feed; Kalshi sale prints; 238 scored entries = all
19 losses, 99 won windows with a risk step, 120 random controls).** Eleven entries are feed-disagreement artifacts: Kalshi priced the
held side at 0.1–87 ¢ while the Binance-feed replay said LOCKED (the live radar, on the 3-venue index with the official BRTI in the
final minute, does not produce these); 9 of the 11 "lost" cheaply. Among the 227 owner-like entries (held side ≥ 99 ¢ at entry):
2 losses. Nov 11: step at +11 s after entry (4.3 %), market lag 3.7 s, exit at +1/+2/+3/+5 s = 97.4/94.9/93.7/69.0.
Oct 17 06:00: risk jumped to 88 % in one second with 20 s left, market collapsed 0.28 s after the step: exit 0.3 ¢, uncatchable.
Unnecessary 1 % exits among owner-like winners: 35 (median cost 0.3 ¢, mean 4.3 ¢ at 3 s), of which two whipsaws cost 46.8 and 98.7 ¢
(the market dropped the held side to 80 ¢ and to 1–12 ¢ after a 2 % and a 21 % step, then settled for it). Population frequency of
the 1 % step after a displayed entry in this period: 50 of 3,737 (1.3 %); 2 % step 0.8 %. Evidence: `$SC/round3/exec/pr9_replay.txt`,
`pr9_replay_clean.txt`, `whipsaw.txt`, `market_lag.txt`.

B13. **Market lag is usually under a second.** In the replay-joined losses with a visible adverse second, Kalshi's first print below
99 came within the same second as the move in 5 of 7 (Binance 1 s grid), 1.7 s after on Nov 11, 21 s after on Oct 19. Nov 13's
6.7 s lag is the exception. Evidence: `$SC/round3/exec/market_lag.txt`.

## C. Withdrawn explanations

W1. "The active-tape factor 0.52 made Nov 11's reading about twice too low" (final_directive report, Nov 14). Withdrawn by
PR7: bucket-4 O/E 1.11 at the displayed entry. Erratum prepended to `$SC/final_directive/FINAL_RESULT.md`, `MECHANISMS.md`, `AUDIT.md`.
W2. "No reversal in 127,301 calls" as evidence of reliability: in-sample by construction. Withdrawn Nov 14 (AUDIT.md).
W3. "1 in 37,000" / "1 in 12,000" upper limits for the two-test rule: the recipe was designed with knowledge of the test years.
Withdrawn in round 2; removed from page H1.5.
W4. "Pre-sell order-book history is not recorded anywhere we can read" (round-2 report): wrong. The owner's evidence ZIP holds
1 Hz order books for 6 windows (incl. Nov 13); `own_capture_2/tape_since_boot.ndjson` holds 7; production's `/tape` endpoint
serves the last 3,000 decision rows (about 2.5 h) with books, read-only. Corrected in this round.

## D. Hypotheses tested, results, rejection reasons

| # | Hypothesis | Test | Result | Why rejected / kept |
|---|---|---|---|---|
| D1 | One-test stricter risk limit (0.01 %, 0.005 %, …) makes LOCKED reliable | PR4 replay | 7 and 3 reversals | fails; tightening to zero losses is selection |
| D2 | Two-test rule (risk ≤ 0.001 % + cushion floor) | PR5, PR6 walk-forward | 0 reversals in 110,882–138,706 | survives as a label; not executable (B7); design saw the test years |
| D3 | Stale/frozen input, delivery delay, restart, sampling artifact caused the locks | incident reconstruction | contradicted | B4 |
| D4 | Time decay alone produces entries | decay scan | 44 % of crossings have a flat/shrinking cushion; those lose 1 in 615 vs 1 in 688 | supported as a modest factor, not a defect |
| D5 | Active-tape factor understates risk; refit it | PR7 | O/E 1.11 in bucket 4; refits fail G1–G5 | rejected; premise wrong (W1) |
| D6 | Shrinking cushion before entry raises risk | PR8 | O/E ratio 1.32 (95 % 1.04–1.62) | supported narrowly; displayed risk still not understated |
| D7 | Liquidity thinning precedes the move (Kalshi book) | Nov 13 book | bid size at 99.8 was 121k–150k until the move, then 16k 0.3 s after | not supported on the one case with books; more cases needed |
| D8 | Cross-feed disagreement gives early warning | Nov 13 tape (idx, liveIdx, BRTI) | proxy index led; BRTI lagged ~2 s; browser feed agreed | no early warning available from feeds |
| D9 | An exit on a risk step (held side ≥ 1 %) improves executable outcomes after costs | PR9: live set (B11), replay-joined set (B12, B13); page H1.6 implemented and tested | Live: +86.5 ¢ vs hold (one loss exited at 99.9; 9 small costs). Owner-like replay-joined at a 3 s reaction: −56 ¢ vs hold (one loss saved +93, one uncatchable, two whipsaws −47 and −99, 33 small costs). Pooled: about +0.65 ¢ per fired step, i.e. ≈ +0.01–0.03 ¢ per entry, sign set by single events | **FAILED the frozen criteria** (P2 on set b; P3 marginal on set a). Candidate frozen for prospective evaluation; not a release |

## E. Remaining plausible mechanisms and the test that distinguishes them

E1. **Response timing (D9), after PR9.** What decides the sign is the ratio of catchable losses (market lag ≥ reaction time) to
whipsaws (market overreacts and recovers) per fired step, plus the small-cost rate. Measured so far: 2 catchable losses, 1
uncatchable, 2 whipsaws, 42 small costs in 47 fired steps across both sets. Distinguishing data: the hourly tape pulls (books at
1 Hz) and Kalshi prints over the coming weeks, scored with the same frozen script. Pre-registered variant to score alongside, not
to adopt: exit only if the held side's bid is still ≥ 99 ¢ at the step (avoids selling into a panic already under way; on the
recorded cases it keeps Nov 11 and Nov 13 and avoids one of the two whipsaws).
E2. **Market lag after the source move.** The Kalshi price lagged the Coinbase move by 1.2 s (Nov 7) to 6.7 s (Nov 13). Test:
distribution of "time from first adverse source trade to first Kalshi trade below 99" across losses (needs source tapes:
available for the 4 incidents; for 2026 replay losses only the Binance 1 s grid).
E3. **Jump frequency conditional on observables** (time of day, dispersion, book depth): not testable with the data in hand
beyond D7; recorded as a limit.

## F. Scheduled evidence collection running now
- I2 reading + two-test scoreboard: every 6 h (see A).
- Tape pulls (`/tape`, read-only, order books): see CHECKPOINT for the task once created.

## G. After the decision (appended 2026-11-15, 18:45 UTC)
- **G1 (verified). I2 stale episode and hold.** One episode of 234 s past the 6 s gate (cause 'other'), 10:34:07-10:38:07 UTC Nov 15,
  found at the 12:31 UTC reading; `respond.py --past` returned REVERT R7 on the identity-guard counter (+151 in 6 h). Determination:
  the counter's increase equals the guard's steady background (20.8-25.2/h in every 6-h interval), the guard cannot stall the record
  (list fallback in the same poll, I2 line 1893), no 429/stated wait/age/book refusals, process alive; cause undetermined (production
  logs nothing; error text overwritten); Kalshi matched 1,257-1,404 trades/min during the stall; the single-market endpoint I2 polls
  differs from production's list query, so an endpoint-specific failure is not excluded. Revert not executed; the one hold used
  (`r30/live/HOLD_USED.json`); any later such finding = REVERT R5. Owner informed; one word reverts. Note:
  `r30/live/readings/20261115T1232Z/episode/EPISODE_NOTE.md`. Hourly read-only /health snapshots added to the tape-pull script.
- **G2 (verified). Third alerted loss: KXBTC15M-26NOV151330-30 (close 18:30 UTC Nov 15).** Observer primary rule: LOCKED UP 0.199 %
  at tau 101.6 s, settled DOWN (64507.75 vs strike 64510.2, 2.45 USD). Mechanism: a ~120 USD fall in 3 s at tau 94-91 s from an
  18 bps cushion, then 90 s hovering at the strike. Market lag about -1 s (the bid slipped one second before the server's risk
  stepped; both moved within the same second). Two-test standard (margin-inclusive risk <= 0.001 %): no call (pFlipCons 0.39-0.51 %).
  Alerted losses since 2026-11-10 16:45 UTC: 3. Timelines: `r30/live/readings/20261115T1832Z/loss_1830/`, tape rows 18:25-18:30.
- **G3 (verified). First prospective PR9 reading** (`PROSPECTIVE.md`): prospective set 57 entries, 1 loss; plain rule +38.5 c
  (save +50.2 on G2, four false alarms worst 9.8 c); pre-registered variant -0.3 c (holds through G2 because the bid was 58 at the
  trigger). 1 of 12 target events; stopping rule not reached. Decision FAILED stands; nothing deployed or published.
- **Code identities unchanged:** live server I2 (`ca51a0c6…`), live page H1.1 (`8bf43b57…`), H1.6 frozen (`c13a605f…`, commit
  `c1d66cff…`), not pushed. `pull_tape.sh` extended (health snapshot); `exec/prospective_eval.py` added.
