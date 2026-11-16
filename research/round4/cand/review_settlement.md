# Adversarial review: PR10 settlement floor — settlement semantics, incident replay, execution, build (2026-11-16)

Disclosure: the reviewer is an instance of the same model family as the author, briefed by the author; its independence is limited to not having
written the code. Read-only; every number was recomputed with `python3 -I` from the named files; this is the only file written. Paths: `scratchpad/`.

## Findings (blocking / material / minor)
1. BLOCKING — the lookup's regime axis is not the axis the table was built on. FIT cells use the usdc replay's raw-sigma bucket; the live
   rows use the 3-venue composite's raw-sigma bucket (server 1624-1632, edges [0.15,0.22,0.3,0.4,0.55,0.8] at 1536). On the same 202
   windows the replay sigma is 1.19x the live raw sigma and only 135 of 202 windows share a bucket (round4/replay_live/compare.txt 468-472).
   Nov 14: live bucket 3 (sigma field 0.3695, raw <= 0.359) -> 100|normal|15-17.5 = 0/334 -> 0.15 % -> admitted; the FIT-feed engine on
   the same window reports bucket 4 (compare.txt "REPLAY ... sigma 0.4193-0.4219 bucket 4") -> 100|active|15-17.5 = 8/830 = 1.02 % ->
   withheld. Scaling live raw sigma by 1.183 moves 28 of 261 live admissions to another group, 26 out of admission (20 not even LOCKED);
   live coverage falls to ~83 % (A2 fails). Fix: bucket the live sigma on the FIT feed's scale (or rebuild the cells from a comparable feed).
2. MATERIAL — A6 fails as declared and is misreported. eval_pr10.py:90 drops null asks, hence "asks ... <= 99.9: 194 of 194". A null ask is
   `LOCKED — TOO LATE` = empty offer ladder on the called side (server m25Decide sets askCents only `if (lv && lv.length)`; bookFromKal
   makes asks from sized other-side bids); all 67 null-ask candidate entries are TOO LATE and the 17 with a tape book show an EMPTY
   other-side ladder (ask = 100). Declared denominator: 93 of 136 later-than-production entries = 68 % (all 261: 74 %) vs >= 90 %.
   Production's own entries: 45/283 = 16 % had no offer; the delay raises that to 26 %. Fix: null ask = no offer; report A6 FAIL.
3. MATERIAL — A4's TEST clause fails by the declaration's own text and no verdict is printed: 270 (exact) / 332 (disp) TEST admissions sit
   in cells with TEST rate > 1 %, 242 / 301 of them in cells with >= 1 real TEST loss. "By construction" also fails for missing cells: 3 TEST
   admissions had no FIT cell; p_emp None -> 0.0 (eval_pr10.py:29) and the A4 counter treats None as 0 (line 89). Fix: PASS/FAIL per criterion.
4. MATERIAL — wrong basis for 191 of 301 live windows: eval_pr10.py:77 `mu_tape.get(tk, -3.4)`; only 110 windows are on the tape. Residual
   (official - strike) - (gap + mu) at the last row: tape-present median -0.36 USD (sd 3.2), tape-absent median +3.88 USD — the default is
   3.7 USD (0.55 bps, a fifth of a bin) too negative. Both incidents are on the tape (mu +1.213 / -1.668). Fix: log geo.basisMeanUsd in the rows.
5. MATERIAL — the floor is mostly the smoothing prior, in both directions. 85 % of TEST and 86 % of live admissions (exact) sit in FIT cells with
   ZERO losses, where the value shown is 0.5/(n+1): the Nov 14 cell is 0/334 (0.15 %; exact 95 % upper 1.10 %; one loss moves it to 0.33 % and
   the exact rule withholds), and 11-16 % of admissions sit in cells with upper95 > 1 %. Conversely 120|normal|27.5-30 is 0/26 -> 1.85 %: it
   un-LOCKs a 28-bps cushion at pf 0.02 % (26NOV130730-30, won). Fix: floor on the upper bound, or pool to the 5-bps bins of
   settle/vulnerability_table.py; never show a prior as "0.2 %".
6. MATERIAL — production failure modes (eval + build as spec). (a) Missing cells fail open: 120/627 grid cells absent from FIT, 204/627 give no
   floor in the build (n < 20 dropped), cbin(NaN) -> no floor when strike/gap is NaN (rollover: strike = prior official value, ~4.6 s late;
   covered only because strikeIssue is a hard gate and the floor runs after the gates). (b) Group flapping: 43/301 live windows change group
   inside the final 120 s; 61/301 have raw sigma within 15 % of 0.22/0.40 at 120 s; Nov 15's cushion crossed 17.5 bps at 93.6 s (17.78 ->
   16.54), floor 0.46 % -> 1.02 %, LOCKED badge off/on. (c) Horizon: hround clamps at 120 (eval_pr10.py:15) but the build applies the floor
   wherever LOCKED/HIGH CONFIDENCE shows, to LOCK_MAX_TAU = 300 s (server 1294): the gate replay binds at tau 159.9 s with
   "120|active|35-37.5" (impl/replay/out_PR10_gate_tape_full: all 12 examples at tau > 120) — a 119-s cell on a 160-s horizon, never
   evaluated. Below 20 s the 19.25-s cell is applied to tau 1.8-19 s although the gap is already in settlement-average terms (required move
   per remaining print |gap|*60/n: ~5x larger at 4 s than at 19 s). (d) mu unavailable -> basisMean25 = 0 (server 1574-1577; the basis
   model restarted at n = 0 on the Nov 13 redeploy): <= 0.3 bps. (e) Stale index: hard gate only above min(3 s, 100 ms x tau) (397-399,
   2878): ~1 bps unseen move. (f) DATA UNRELIABLE (188 live rows in the final 120 s): untouched by the build, correct.
   Fix: fail closed on a miss/NaN; cells at 150/180/240/300 s and 5/10/15 s (cushion as required move per print below 60 s); group hysteresis.
7. MATERIAL — PR10 build (impl/pinradar_server_PR10.js 110-118): settleFloor29Lookup = |gapUsd + mu| / strike x 1e4, h = min(120, max(20,
   10*ceil(tau/10 - 1e-9))), quiet 0-1 / normal 2-3 / active 4-6, mu = geo.basisMeanUsd, bucket = geo.regime.bucket — identical to
   build_cells.py:31-34 and eval_pr10.py:15-18; the embedded table equals cells.json FIT for every cell with n >= 20 (423 cells, 0
   disagreements in n, k). Differences from what was evaluated: floors on 20-300 s not 20-120 (6c); cells with n < 20 give no floor (the
   eval used them); settleFloor29Apply (128-137) overwrites pFlip/pWin/pFlipCons after m25Decide fixed the trade action and evConsCents
   on the un-floored pFlipCons, so "TRADE NOW, edge x¢" can sit next to a floored risk; the soft gate (120-126) withholds LOCKED so
   `lockedSide` (1738) is set later, moving REVERSAL WARNING / EXIT and the official-reference reversal (3254-3257) with it; predLog27
   (4329) logs the floored pFlip, so future evaluations must read `settleFloor` to recover the model value. Default mode is shadow (no change).
8. MINOR — settlement semantics. Truth comes from Kalshi's result/official value (eval_pr10.py:72, summaries): 28,541 windows, 0 exact ties,
   0 truth/margin disagreements; strike chain checked (server 4229-4235); 2-dp rounding via strike - 0.005 (3231). build_cells.py:33 omits
   the tie rule vulnerability_table.py:35 applies (no effect here). Alignment: settleAlign "incl" in all 36 saved /health copies;
   settleVarUnitsDiscrete (453) and proxyWindowAverage (2739) honour SETTLE_ALIGN but the live pf path m25VarUnits (1363) and
   decompose.py:20-22 hard-code incl, so `excl` would silently split the engine; Kalshi's "sixty seconds ... before 1:30 PM" reads as excl,
   the server chose incl empirically (335-337) — irrelevant to the floor, a 1-s tau shift for pf. Leader = sign(gap + mu), gap = expected
   settlement - strike, mu = official - proxy (337-339, 1419): the right object, identical in server, cells and lookup (a live trader also sees
   the official BRTI spot: rows ref OFFICIAL / offDiv); FIT cushions carry usdc basis noise sd 6.0 USD vs 3.2 USD live.
9. Incident replay (FIT cells, production rows, mu as given) reproduces the table. Nov 14 (mu +1.21): candidate LOCKED from 113.8 s (floor
   0.15 % < pf), displayed = pf every second, exact entry 91.8 s / disp 95.8 s = production, move 90.3 s (1.76 %): NOT PREVENTED, correct as
   specified; mu in {-3.4, 0, +4.21} and the 12.5-15 bin (0.10 %) still admit; only the group flips it (finding 1). Nov 15 (mu -1.67): floor
   1.12 % (8/756) at 119.6-110.6 s and 0.72 % (5/762) at 109.6-100.6 s — not LOCKED while production showed LOCKED 0.20-0.36 %; LOCKED at
   0.46 % (3/757) 99.6-94.6 s, never <= 0.25 %; 1.02 % at 93.6 s; move 92.6 s (REVERSAL 11.1 %, market led ~1 s): ENTRY PREVENTED under both
   rules, robust to mu +/-3 USD, to the adjacent bins (1.02 % / 0.40 %) and to bucket 5; with bucket 3 the disp rule admits at 0.22 %.
10. Execution. Candidate later than production in 136 of 261 live windows (median 8.3 s, max 91 s); where both moments carry an ask (93),
   candidate minus production ask mean +0.15 c, median +0.10 c, max +2.8 c, higher in 57 %. Row asks match the tape (100 - best other-side
   bid) in 78/78 checks. Depth is not the issue: best-level size min 25 (production) / 79 (candidate), p10 331, >= 25k contracts <= 99.9 in
   every priced book; the issue is no offer at all (finding 2). The 22 withheld live windows: 21 winners + Nov 15; 17 are tau 1.8-25.6 s with
   0.6-2.9 bps floored 9.7-15 % by the 20/30-s 0-2.5 cells (6c), 9 of them with an offer at 99.5-99.9, 8 with none; the other 4 are 26-28 bps
   at 116-120 s floored 0.36-1.85 % by n = 26-400 cells (finding 5). TEST: 879 windows withheld (14.6 %) for 7 of 11 losses, 4 at tau <= 15 s.
11. MINOR — appetite. displayed = max(pf, p_emp) and candidate LOCKED needs production LOCKED: nothing production refuses is admitted. The PROVEN
   LOCKED bypass (eval 29; build 131) needs 0.9975 x recorded prints to clear the strike (server 394, 1477, 1633): the one live PROVEN row is
   tau 0.71 s, 59 prints, TOO LATE. The lock-bookkeeping shift (finding 7) is a side effect, not a raise.
12. MINOR — wording. No "impossible"/"guaranteed" claim in eval_pr10.txt or PR10_DECLARATION.md; "withheld for good" means "whole window";
   settle/vulnerability_table.txt prints zero-count cells as "1 in inf" (h=90 normal 15-20: 0/790), which reads as impossibility — print the bound.

## Verdict
Settlement logic as stated is correct (real Kalshi results, ties-as-YES, strike chain, incl alignment consistent in production) and the build's
lookup matches build_cells.py. Nov 15 "prevented" is correct and robust; Nov 14 "not prevented" holds only for the live-feed bucket and is an
artefact of a regime axis inconsistent with the FIT feed (bucket 4 there -> withheld). A6 fails as declared (68-74 %, reported 100 %) and A4's
TEST clause fails unreported; the build floors 120-300 s on the 120-s cell, untested. Not acceptable as written.
