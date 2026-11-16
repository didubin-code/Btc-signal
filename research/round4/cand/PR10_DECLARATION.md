# PR10: empirical settlement-vulnerability floor (candidate), declared before evaluation (2026-11-16 02:20 UTC)

**Disclosure of what has been examined.** All 2026 replay windows (usdc feed, real settlements, Jan 15–Nov 12) have been read
for calibration tables (round4/settle/vulnerability_table.txt, round4/causal/*), including the loss list; the live Nov 12–16
rows and both live losses are examined in detail (their cells are known: Nov 14 00:15 = h 92 s, normal regime, 15.1 bps;
Nov 15 18:30 = h 102 s, active regime, 18.1 bps). The candidate's lookup table will be built from windows closing BEFORE
2026-09-01 (FIT) and evaluated on Sep 1–Nov 12 replay windows (TEST) and on the live rows Nov 12–16; the five incidents are
diagnostic cases and are reported separately (section 6 table), never as validation. Candidates tried before this one:
A, B, B′, C1, C2, the two-test standard, exit triggers T1–T5 × 4 delays, the bid≥99 variant (family size for multiplicity).

**Hypothesis.** The production flip risk conditions on the current volatility estimate and on a parametric tail law. When
that conditioning fails (the live Nov 13–15 cluster: 2 losses in 118 exact entries at 90–120 s left, 0.147 expected), the
unconditional real-settlement loss frequency of the entry's (horizon, regime, cushion) cell is a floor the displayed risk
should not go below. Mechanism claim: the cell frequency is a sigma-free, settlement-based measure of how often a cushion of
that size has been exhausted over that remaining time in that regime.

**Candidate (fixed).** p_emp(h, g, c) = smoothed real-settlement loss frequency of the leader in cell (horizon h rounded up to
the next 10 s in 20..120, regime group g of the current bucket (0–1 quiet, 2–3 normal, 4–6 active), basis-adjusted cushion c
in 2.5-bps bins), from the FIT table. Displayed risk = max(pf_production, p_emp). LOCKED iff displayed risk ≤ 0.5 % (all other
production conditions unchanged). Owner's entry rules evaluated on the displayed risk exactly as today (exact ≤ 0.2 %, rounded
< 0.25 %). No other parameter; no threshold search; the bins and smoothing are fixed above.

**Acceptance criteria (fixed).**
- A1 (losses): on TEST and on live Nov 12–16 separately, candidate entries' loss count ≤ production entries' loss count, with
  no new loss created (an entry admitted later by the candidate that loses while production's earlier entry would also have lost
  counts as "not prevented", not as new).
- A2 (coverage): windows with a candidate entry (exact rule) ≥ 85 % of windows with a production entry, on TEST and on live.
- A3 (delay): median delay of the candidate's first exact entry versus production's ≤ 30 s; share of entries delayed by more
  than 60 s ≤ 15 %.
- A4 (bound): every admitted candidate entry sits in a cell whose FIT loss frequency ≤ 0.5 % (by construction) and whose TEST
  frequency is ≤ 1.0 % (stability of the cells out of sample).
- A5 (incidents, diagnostic only): the section-6 table for Nov 7, 9, 11, 14 (00:15), 15 with classification per the owner's
  definitions; a non-qualifying incident is not a prevented trade.
- A6 (execution): the entries the candidate admits later must have an offer at ≤ 99.9 ¢ at the admitted moment in ≥ 90 % of
  live cases (observer/live rows), otherwise the candidate has traded a loss for an unavailable entry.
- Fail if A1 or A2 or A3 or A4 fails. A1 passing by the two live losses alone is reported as retrospective, not validation.

**What this cannot show.** With 4 replay losses in the owner's class, TEST cannot demonstrate a realized loss reduction; the
candidate's protective value is a bound on the unconditional cell risk, demonstrated only as that bound plus the (retrospective)
live incidents. Prospective evaluation continues under PROSPECTIVE.md with this candidate added.
