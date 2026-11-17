# Round 7, sections 4–7 — Protection versus usability, prevention replay, additional inputs (2026-11-16)
PR11 as frozen (PR11_DECLARATION.md, sha256 82ed0eca…03c3, 19:00:38 UTC); every evaluation below was run after that line. Files: round7/eval.

## 4.1 Reversal losses with uncertainty (exact rule; the displayed variant gave the same counts)
| Evidence set | Baseline (first LOCKED ≤ 0.2 % in the final 120 s) | PR11 (θ = 0.05 %) | Notes |
|---|---|---|---|
| TEST primary: Sep 1 – Nov 12 2026, scale 0.82, official outcomes, cushion ≥ 5 bps | 4,474 entries, 9 lost (0.20 %) | 4,452 entries, 0 lost; upper-95 % 0.067 % | C1 ✓, C2 ✓ (0 of 9 baseline losses admitted) (E1c) |
| TEST primary, proxy-defined outcomes (path risk), all entries | 6,389 / 58 (the proxy outcome ignores the basis the engine includes; not the production baseline) | 6,299 / 0; upper 0.0475 % | C1 ✓ (E1b) |
| TEST primary, official outcomes, ALL entries | 6,389 / 17 (0.27 %) | 6,350 / 5 (0.079 %; upper 0.17 %) | the 5 are cushions 1.0–2.7 bps at 3–9 s left, where the replay's whole-minute basis decides the outcome (E1a); judged on live data: 61 such live entries, 0 lost (live_sensitivity.txt) |
| TEST unscaled, official, ≥ 5 bps | 4,479 / 4 | 4,457 / 0 (upper 0.067 %) | E2a |
| TEST scale 0.866, official, ≥ 5 bps | 4,478 / 7 | 4,456 / 0 (upper 0.067 %) | E3a |
| Nov 13–15 replays (scaled / unscaled), official | 85 / 1 (the Nov 15 loss) / 85 / 0 | 85 / 0 | E4 |
| FIT 2026 (development), official, ≥ 5 bps | 15,235+ / 3 | 15,158 / 0 (upper 0.020 %) | E5a |
| FIT 2026 (development), proxy outcomes, all | 19,833 / 84 | 19,648 / 0 (upper 0.015 %) | E5b |
| 2023-10 … 2026-01 proxy windows (development), path risk | 74,136 / 49 (0.066 %) | 73,962 / 3 (0.0041 %; upper 0.0105 %) | qtable/policy_ext_history.txt (interpolated table) |
| LIVE Nov 12–16, 373 settled windows, official | 353 / 2 (0.57 %) | 351 / 0 (upper 0.85 %) | E6; the live sample cannot bound 0.1 % |
Sensitivity (the four frozen tables, TEST primary ≥ 5 bps): θ = 0.2 %: 1 loss in 4,474 (KXBTC15M-26SEP151430-30, cushion 30.7 bps at 74 s, bucket 6; the same window loses under θ = 0.2 % in every cohort); θ = 0.1 %, 0.05 %, 0.025 %: 0 losses.

## 4.2 Historical losses prevented, winners withheld, time at entry
* TEST primary (≥ 5 bps): all 9 baseline losses are outside PR11's admitted set (prevented); 228 of 4,474 baseline windows get no PR11 entry at all (5.1 %); the rest are admitted later: time left at entry p10/median/p90 falls from 23/39/76 s (baseline) to 17/29/55 s; entries with more than 60 s left fall from 826 to 318 of 4,452.
* Live: PR11 admits a second in 351 of the 353 baseline windows, median 36 s left (baseline 80 s); the baseline's two losses are not admitted at any second before their moves (4.3).

## 4.3 Executable entries retained (live tape Nov 13–16, 170 windows with books; ask ≤ 99.9 ¢, size ≥ 10 contracts, book ≤ 3 s old — book age on the tape is 0.3 s median, 1 s maximum)
| θ table | tape windows with ≥ 1 executable PR11 second | share | by time left 90–120 / 60–90 / 30–60 / 10–30 / 0–10 s | asks ≤ 99.9 / ≤ 99.8 / ≤ 99.5 | median size at the ask |
|---|---|---|---|---|---|
| baseline (first LOCKED) | 145 | 85 % | median 83 s | 145 / 104 / 39 | 11,220 |
| 0.2 % | 51 | 30 % | 21 / 9 / 14 / 6 / 1 | 51 / 21 / 5 | 64,353 |
| 0.1 % | 31 | 18 % | 14 / 3 / 10 / 3 / 1 | 31 / 8 / 0 | 86,994 |
| 0.05 % (frozen) | 10 | 5.9 % | 2 / 2 / 3 / 2 / 1 | 10 / 2 / 0 | 68,596 |
| 0.025 % | 8 | 4.7 % | 0 / 3 / 2 / 2 / 1 | 8 / 0 / 0 | 11,387 |
C3 at the frozen table: 10 windows, 5.9 % ≥ 5 % and ≥ 8: ✓, narrowly. Why so few: PR11 admits seconds in 159 of the 170 tape windows, but at those seconds the called side usually has NO offer at all (the book is one-sided once the outcome is clear; "no ask" in 152 of 159), and where an offer exists it is 99.9 ¢ in 8 of 10 cases. The usable PR11 opportunity is roughly one window in seventeen, at 99.9 ¢, with very large size.
Stronger protection as opportunity falls: yes — the TEST loss count under the four tables is 1 / 0 / 0 / 0 while executable windows fall 51 / 31 / 10 / 8; the 0.1 % table has three times the usable entries of the frozen table with the same zero TEST losses, but it was not selected and its selection would be a new specification requiring its own separated test.

## 4.4 Sensitivity to feed, stale inputs and settlement uncertainty (live rows)
Index 3 bps less favourable: 13 % of admitted row-seconds lost, 36 of 351 admitted windows lose their entry; official reference older than 2.5 s at an admitted second: 0; cushions below 5 bps among PR11 live entries: 61 of 351 (0 lost) — the class the replay cannot resolve. Basis in production enters the expected settlement scaled by (unknown prints)/60; PR11 admits small raw cushions only when few prints remain, where that scaling is smallest.

## 5. Prevention replay of every qualifying loss (exact and displayed variants; eval/E7_*.txt)
| Incident (UTC / Pacific) | Baseline entry (exact / displayed) | PR11 at that second | Any later admitted second before the move? | Classification |
|---|---|---|---|---|
| KXBTC15M-26NOV110415-15, Nov 11 09:15 / 01:15 PST | 45.6 s, 0.192 % / 47.2 s, 0.219 % (observer; replay trace: LOCKED 54.3–42.3 s at 9.3–10.0 bps) | h 46, R 12.4 bps < R* 31; displayed second h 48, R 11.6 < 31 | none: R ≤ 13.3 bps on every second 54–42 s; the move at 41.8 s | ENTRY PREVENTED (both). Caveat: no production rows exist for Nov 11; the per-second cushion is the production-parity replay's (production entry time and risk confirmed by the observer) |
| KXBTC15M-26NOV131915-15, Nov 14 00:15 / Nov 13 16:15 PST | 91.8 s, 0.188 % / 95.8 s, 0.240 % (ask 99.9 × 336k) | h 92, R 14.9 < R* 55 (displayed: h 96, 14.9 < 57) | none: R 14.9 on every LOCKED second 113.8–90.8 s (R* 55–66); the move at 90.3 s; after it the side had no ask | ENTRY PREVENTED (both) |
| KXBTC15M-26NOV151330-30, Nov 15 18:30 / 10:30 PST | 101.6 s, 0.199 % / 114.6 s, 0.248 % (ask 99.6 / 99.4) | h 102, R 18.3 < R* 60 (displayed: h 115, 19.1 < 66) | none: R 18.0–19.3 on every LOCKED second 124.6–93.6 s (R* 56–68); the move at 93.1 s | ENTRY PREVENTED (both) |
| KXBTC15M-26NOV071730-30, Nov 7 22:30 / 14:30 PST | no entry under the baseline (observer primary NONE) | PR11 ⊂ baseline | — | NOT QUALIFYING (no entry under either rule) |
| KXBTC15M-26NOV092000-00, Nov 10 01:00 / Nov 9 17:00 PST | no entry (LOCKED withdrawn 24 s before the move) | PR11 ⊂ baseline | — | NOT QUALIFYING |
Comparable winners and other periods: the 15 live winners in the losses' cells (cushion 10–20 bps, regime 3–4, 90–120 s) are likewise not admitted at their baseline second (R 15–20 < R* 55–68); 10 of them have an admitted executable second later, 5 none (E6 json). On TEST the 9 baseline losses (≥ 5 bps) are prevented and 0 of 4,452 admitted entries lose; the one θ = 0.2 % loss shows the limit: a 30.7-bps cushion at 74 s in the most volatile regime is admitted by the loosest table and lost.
What a "warning after entry" would have been: nothing here is a warning; PR11 acts before entry by withholding LOCKED. A routine price-based DO NOT TRADE message is not counted.

## 6. Additional inputs — specific purpose test
Hypothesis that would justify a new input: that the reversals were preceded by information not in the server's inputs. Round 4 (book_precursor, trade flow, input ages) found no advance signal in books or trade flow; the official print lagged the proxy by 0.2–1.3 s but the proxy led. In the three qualifying losses the move arrived 3–4 s (Nov 14, Nov 15) and 4 s (Nov 11) after the entry second with no measurable precursor in cushion, sigma or book; the live losses-vs-winners table shows no entry-time separation. The information that decides PR11 (gap, recorded prints, seconds left, the frozen table) is already in the server. No new input, field or faster collection changes the decision; the existing observer tape capture (round 6) records what PR11 needs for its prospective test (the `pr11Admit` fields are written to the /predictions rows and the tape rows).

## 7. Supporting work kept separate
* The observer tape-capture release (round6/collector/OBSERVER_TAPE_RELEASE.md) is unchanged and still undeployed; it is not part of PR11.
* Discriminator v3 (round5/DISCRIMINATOR_v3.md) continues on the baseline population: N = 22, K = 0 at the 18:31 UTC reading (12 at 12:31 + 10 new 90–120 s entries, all correct). If PR11 is released in gate mode the observer's primary-v1 population becomes the PR11-admitted population (LOCKED is withheld elsewhere), so v3 would end at the release and a PR11 discriminator would start; the record keeps v1→v3 history.
* A loss-rate test cannot identify a cause or validate a correction by itself: PR11's claim is a bound from the price history plus zero-loss consistency on separated data, not a causal finding about November.
