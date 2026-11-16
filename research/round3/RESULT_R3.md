# BTC Pin Radar, round 3: engineering decision

2026-11-15. Nothing has been published or deployed. No trades were made or are authorised. Authoritative record with every finding,
withdrawal, hypothesis and identity: `$SC/round3/RECORD.md` (`$SC` = `/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad`).

## Decision: FAILED against the frozen criteria. A specific correction remains, frozen, with the test that would decide it.

**What was tried.** An EXIT ALERT (page H1.6): sell the side you hold when the server's own flip risk for it first reaches 1 % after
having been lock-grade. Rationale: in all four losses the server's risk crossed its LOCKED limit before, or within 0.7 s after, the
adverse move, while Kalshi still paid 99.8–99.9 ¢ for 3–7 s (Nov 11, Nov 13) or the warning came seconds before the move (Nov 7, 9).

**What the evidence says, after costs, on real Kalshi prices.**
- Live markets Nov 12–15 (192 entries, 1 loss): the alert would have turned −58 ¢ into +28 ¢ per contract over the set. The loss
  exited at 99.9 ¢; nine false alarms cost 0.2–5.6 ¢ each.
- Oct 15–Nov 12 markets (227 entries like yours, 2 losses): the alert would have turned −200 ¢ into about −256 ¢ at a 3 s reaction.
  One loss recovered 93 ¢ (Nov 11). One was uncatchable (the market collapsed 0.3 s after the step). Two false alarms were whipsaws:
  the market knocked the held side down to 80 ¢ and to 1–12 ¢, you would have sold, and the window then settled in your favour
  (−47 ¢ and −99 ¢).
- Pooled: 47 alerts, +193 ¢ saved, −162 ¢ paid: about +0.65 ¢ per alert, roughly +0.02 ¢ per entry, with the sign decided by single
  events. Frozen criterion P2 (net ≥ 0 on each set) fails on the second set; P3 (median false-alarm cost ≤ 1 ¢) fails narrowly on the
  first (1.2 ¢ at 3 s). Per the declaration, that is a FAIL. I am not softening it.

**Why this is the limit and not a defect.** The market usually reprices within a second of the move (5 of 7 replay losses; Nov 7 in
1.2 s). Nov 13's 6.7 s of grace was the exception. When the market has already moved by the time the alert sounds, selling realises
the panic price, and the panic reverses often enough to cost as much as the losses it avoids. No signal in our data separates the two
at the moment of the alert.

**What remains, specifically.** The same candidate, frozen (not retuned), scored on prospective data by the same frozen script, with
one pre-registered variant: act on the alert only while the held side's bid is still ≥ 99 ¢ (do not sell into a move already priced).
On the recorded cases that keeps Nov 11 and Nov 13 and avoids one of the two whipsaws; that is a hypothesis, not a result. The data
to decide it (1 Hz order books and Kalshi prints) is already being collected hourly, read-only. The decisive events occur about once
per 1,000–2,000 entries on each side, so this is a matter of months, not days. Section 7 gives the target and stopping rule.

---

## 1. Status
| | |
|---|---|
| Live server | I2, commit `3125bbc0…`, sha256 `ca51a0c6…`; calibration 2.02 / 1.0 / 0.52; LOCKED ≤ 0.5 %; warning 10 %. Unchanged. |
| Live page | H1.1, sha256 `8bf43b57…` (`main` = `fe16325a…`). Unchanged. |
| Local, frozen | H1.6: commit `c1d66cffe42e16abc01cd40713d1b2f233e5bb5c`, sha256 `c13a605fab3be9e08d1785f680e3face11e4ec8e4a710f39495bf07177850f02`, parent `fe16325a…`, one file; bundle `$SC/h16/h16_release.bundle`. Not pushed. H1.5 (`d5587f23`) and earlier: superseded. |
| Running | I2 ingestion readings every 6 h (100 of 288 windows, 0 gaps; stops at 288 or on a revert); hourly read-only `/tape` pulls since 01:46 UTC (8,044 rows with books so far); live two-test scoreboard. |
| Not needed for this work | The I2 readings (ingestion only). |

## 2. Audit of the earlier work against your decision (enter at "≈0.2 %" in the final two minutes)
| Check | Finding |
|---|---|
| Rounded ≈0.2 % vs exact ≤ 0.20 % | ≈0.2 % = centre < 0.25 %. Scored both ways: 1 in 751 and 1 in 940 (2022–2026 replays). |
| First qualifying entry vs later readings | One entry per window, first qualifying reading. "First LOCKED at 0.5 %" (1 in 292) is a different rule. |
| Conditional vs overall calibration | On real settlements: ≥ 30 s left O/E 0.36–0.51; under 30 s 6.27 (46 of 3,609 lost); cushion < 10 bps 1.80. Overall figures hide this. |
| Real settlements vs proxies | Real O/E 1.23 (1 in 411) vs proxy 0.41–0.71; 36 of 64 real losses are basis losses with no visible reversal. Caveat: the replay feed carries a larger basis than the live index; live uses the official BRTI in the final minute (all 192 live entries). |
| Fitting, leakage, re-examination | In-sample tuning of the two-test thresholds withdrawn; walk-forward fixed the look-ahead; every replay year examined; untouched = data after 01:46 UTC Nov 15. |
| Correlated observations | One decision per window; day bootstrap; 821 independent extreme events behind the cushion table. |
| Executable prices | Measured from Kalshi sale prints and 1 Hz books. The earlier statement that no order-book history existed was wrong; withdrawn. |

## 3. The four losses (timelines: `$SC/round3/INCIDENTS_EXEC.md`)
| | Nov 7 | Nov 9 | Nov 11 | Nov 13 |
|---|---|---|---|---|
| Your rule met | No | No | Yes (47 s, 0.219 %) | Yes (96 s, 0.240 %) |
| Risk ≥ 0.5 % (LOCKED withdrawn) | 9.1 s before the move | 24.2 s before | +0.6 s | +0.4 s |
| Risk ≥ 1 % (alert) | n/a | n/a | +0.6 s (3.4 %) | +0.7 s (1.38 % on the page) |
| REVERSAL WARNING (10 %) | +0.9 s | +0.8 s | +3.6 s | +6.4 s |
| Last Kalshi print ≥ 99, held side | +1.15 s | at the move | +3.8 s | +6.7 s |
| 3 s reaction after the alert | n/a | n/a | 93.7 ¢ (prints) | 99.9 ¢ (book, 16k–218k at the bid) |
| Mechanism | jump at the 0.5 % edge; repriced in 1.2 s | one-second jump | time decay + shrinking cushion, −28 USD in 1 s, lag 2–4 s | time decay, −79 USD in 1 s, lag 6.7 s |
| Confidence | high | high | high | highest |
| Unresolved | why the lag differs (1 s vs 7 s): who sells first; not predictable from our data | | | |

Common mechanism: none in the forecast (the ≈0.2 % was about right or cautious for these conditions on average; no individual window
can be shown to have been mis-forecast). In the response: the risk step precedes the price collapse in some losses, not in others.

## 4. Mechanisms tested this round
- Liquidity precursor in the book (Nov 13): none (121k–150k at the bid until the move).
- Cross-feed early warning: none (BRTI lagged the proxy by ≈ 2 s; browser feed agreed).
- Market lag after the source move: ≤ 1 s in 5 of 7 replay losses; 1.7 s (Nov 11); 6.7 s (Nov 13); 21 s once.
- Basis losses (late, thin entries on the replay feed): a separate class no exit rule catches; live exposure not yet measured.
- Whipsaws: 2 of 35 owner-like false alarms cost 47 and 99 ¢ (market overreaction that reversed).

## 5. What was built and how it was challenged: H1.6
`$SC/h16/README_H16.md`. Built from the live page by exact replacement in four steps; lock thresholds and lock logic byte-identical.
- Fires once per deterioration at the 1 % step on a fresh reading (≤ 1.5 s), ≤ 5 min left, after the side was ≤ 0.5 % in this market
  (declared position) or after your entry rule was met (no declaration); re-arms at ≤ 0.5 %; shows the side's best Kalshi bid, depth
  within 5 ¢ and book age; the declared position survives a reload within the market and is cleared at the market change.
- 1,314 browser checks; the Nov 13 page readings with the recorded books; latency 8 ms; stale, reconnect, reload, rollover,
  soft-gate, null-field and re-declaration cases; a randomised run against an independent model.
- Three independent adversarial reviews: 9 confirmed defects in earlier builds, each fixed with its own regression test; the third
  review found none. The evaluation script was reviewed separately and corrected (same-subset totals, fees on both arms, books by their
  own timestamp, sale prints only, trigger gates, the DST boundary).
- Live alert frequency without a declaration: 10 of 204 markets (4.9 %), median 55 s before the close.

## 6. PR9 in numbers (criteria frozen in `$SC/round3/PR9_DECLARATION.md`, sha256 `bfa3e640…`)
| Set | Entries | Lost | Hold | 1 % step, 3 s reaction | False alarms | Losses |
|---|---|---|---|---|---|---|
| Live Nov 12–15 | 192 | 1 | −58.2 ¢ | +28.3 ¢ (+86.5) | 9: median 1.2 ¢, worst 5.6 ¢ | exited at 99.9 (+99.8) |
| Oct 15–Nov 12, owner-like | 227 | 2 | −200 ¢ | ≈ −256 ¢ (−56) | 35: median 0.3 ¢, mean 4.3 ¢, worst 98.7 ¢ | +93.2 and +0.2 |
| Oct 15–Nov 12, feed artifacts (excluded) | 11 | 9 | cheap (held side priced 0.1–87 ¢ at entry) | | | |

P1 met (both actual entry-losses exited ≥ 90 ¢ on prints with a 3 s reaction). P2 met on set (a), **failed on set (b)**. P3 failed
narrowly on set (a) at 3 s (passes at 1–2 s), met on (b). P4 met with n = 3 (two of three losses had ≥ 2 s). P5 met.
Position sizes: the live loss had 16,000–218,000 contracts at the bid; books in the final 120 s hold ≥ 1,000 at the best bid 81 % of
the time and ≥ 10,000 within 1 ¢ 94 % of the time, so size up to 1,000 is not the constraint; the price is.

## 7. The test that would change the decision (prospective, read-only, already collecting)
- Claim: per fired alert, saves exceed costs. Measured so far +0.65 ¢ per alert from 47 alerts, driven by 2 saves, 1 miss and 2
  whipsaws.
- Data: hourly `/tape` pulls (1 Hz books for every market) + Kalshi prints; scored by the same frozen script, both the plain rule and
  the pre-registered "bid still ≥ 99 ¢" variant.
- Target: 12 fired alerts that are losses or whipsaws in total (about 10,000 entries, roughly 5 months at the current ≈ 65 entries a
  day), or 150 days. Interim readings every 1,000 entries, reported only when a loss or whipsaw occurs.
- Stopping rule: stop early if the pooled net per alert is below −2 ¢ after 6 such events (fail) or above +4 ¢ with a bootstrap
  lower limit above 0 after 8 (pass). Nothing is deployed for this; no trade is needed.

## 8. If you want the alert on screen meanwhile
H1.6 is complete and tested as software. Its value as information is real (you see the bid at the moment the radar's confidence
breaks); its value as a trading rule is not shown. If you want it on screen anyway, say "publish H1.6": one push of commit
`c1d66cffe42e16abc01cd40713d1b2f233e5bb5c` to `main`, served sha256 `c13a605f…` verified, rollback = revert that commit (H1.1 byte for
byte). I am not asking for that approval; the evidence does not support it as a fix.

## 9. Plainly
- The radar's number was not the problem in your two entries. The price you paid was: 99.7–99.9 ¢ for a 1-in-400 to 1-in-750 event
  leaves no room for error, and no alert we can build sells reliably before the market does.
- What would change the economics is not a better alert but a better price: entering earlier and cheaper, or not entering when the
  gain is 0.1 ¢. That is a different question from the one you asked, and I have not studied it.
