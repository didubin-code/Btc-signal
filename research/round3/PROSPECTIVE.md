# PR9 prospective readings (untouched data: markets closing at or after 2026-11-15 02:00 UTC)

Frozen definitions (RESULT_R3.md section 7, PR9_DECLARATION.md): entry = first LOCKED reading with centre risk < 0.25 % in the final
120 s; alert = held-side flip risk first >= 1 % (T2); reaction 3 s; exit at the held side's best bid in the first book at or after
trigger + 3 s (else prints); fees on both arms; 10 contracts. Scorer: `exec/exit_eval.py` (frozen), split by `exec/prospective_eval.py`.
Pre-registered variant: act only if the held side's best bid at the trigger is still >= 99 c. Target: 12 fired alerts that are losses
or whipsaws (about 10,000 entries); stop early at pooled net per alert < -2 c after 6 such events (fail) or > +4 c with bootstrap lower
limit > 0 after 8 (pass).

## Reading 1: 2026-11-15 18:40 UTC (first prospective loss)
Files: `exec/pr9_live_20261115T1840Z.{json,txt}`, `exec/pr9_prospective_20261115T1840Z.txt`.

| Set | Entries | Lost | Hold | Plain rule (T2, 3 s) | False alarms | Variant (bid >= 99 at trigger) |
|---|---|---|---|---|---|---|
| Examined (close < 02:00Z Nov 15) | 195 | 1 | -58.0 c | +28.5 c (+86.5): fired 10 | 9: median 1.2 c, worst 5.6 c | +41.8 c (+99.8): acts 1 |
| Prospective (close >= 02:00Z) | 57 | 1 | -85.2 c | -46.7 c (+38.5): fired 5 | 4: median 0.8 c, worst 9.8 c | -85.5 c (-0.3): acts 1 |

Event 1 (loss, prospective): KXBTC15M-26NOV151330-30, close 18:30:00 UTC. Entry rule met at 18:28:05 (tau 114.6, centre 0.248 %,
ask 99.4); displayed ~0.2 % from 18:28:18 (0.199 %) to 18:28:26; cushion +116 to +120 USD (18 bps), book 99.5 x 3,700-10,700.
At 18:28:26 the Kalshi bid slipped to 99.1 (72 contracts) while the server's risk still read 0.21 %; at 18:28:27 the index fell
~20 USD, the server's risk stepped 0.21 % -> 11.1 % (REVERSAL WARNING) and the book read 75 bid in the same second (book age 5 ms);
18:28:28 bid 58 (index -70 USD more, cushion +26); 18:28:29 bid 51 (cushion +8). The window then hovered within +-15 USD of the
strike for 90 s (YES 20-87 c) and settled 2.45 USD below it. Plain rule: exit at +3 s = 52 c (book), net -49.3 vs hold -99.5: save
+50.2. Variant: bid at the trigger 58 -> holds -> -99.5. Market lag: the market led the server's risk step by about one second.
Whipsaws so far: none (largest false alarm 9.8 c: KXBTC15M-26NOV150830-30, exit at 90.8 after a 2.7 % step, the window recovered).

Pooled net per fired alert, all sets (replay-joined owner-like included from RESULT_R3): (+31 + 38.5) / (47 + 5) = +1.3 c; live sets
only: +125 / 15 = +8.3 c. Sign still set by single events. Events toward the target: 1 of 12. Stopping rule: not reached.

Disclosure: `prospective_eval.py` (the split and the variant's implementation) was written after this loss was seen; the variant's
definition was fixed before it (RESULT_R3 section 7). The examined set counts 195 entries here against 192 in RESULT_R3 because
three markets closing before 02:00Z had their rows fetched after the round-3 run; their totals are unchanged (+86.5).
