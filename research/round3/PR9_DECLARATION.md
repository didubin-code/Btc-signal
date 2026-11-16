# PR9: exit-on-risk-step response policy, declared before evaluation (2026-11-15, round 3)

**What has already been seen (disclosed).** The four incidents' Kalshi trade prints and the Nov 13 order books (B6 in RECORD.md);
the count and risk levels of withdrawals after displayed entries on the 204 live markets (33 of 192 entries left LOCKED, mostly
by soft gates; risk at withdrawal in winners median 0.08 %, max 1.9 %). NOT yet seen: Kalshi trade prices in those live
windows apart from Nov 13; anything about the Oct 15–Nov 12 replay markets' Kalshi prices.

**Hypothesis.** After a displayed entry (first LOCKED reading with centre risk < 0.25 % in the final 120 s), selling the held
side when the server's flip risk for that side first reaches a threshold ("risk step") recovers most of the stake in the
losing windows, because Kalshi's price lags the source move by seconds, at a small cost in the winning windows where the
step is followed by recovery.

**Triggers (fixed).** T1: held-side flip risk ≥ 0.5 % (the server's LOCKED limit). T2: ≥ 1 %. T3: ≥ 2 %. T5: the server's
'deteriorating' rule (risk doubled within 3.5 s and > 0.2 %). T4: REVERSAL WARNING (≥ 10 %), the existing alarm. Soft-gate
withdrawals with no risk step do not trigger.

**Execution model (fixed, labelled scenarios).** Reaction delays d ∈ {1, 2, 3, 5} s after the server row that crossed the
threshold (page poll ≈ 1 s is inside d). Exit price: where an order book is on file, the best bid of the held side at the first
book at or after trigger + d, and the depth there; where only trade prints exist, the lowest YES (or NO) price printed in
[t+d, t+d+2 s] among taker-sell prints, else the first print after t+d; where no print exists within 10 s, the exit is marked
unpriced and reported separately. Position sizes 10, 100, 1,000 contracts: filled fully if depth at the best bid covers the size,
otherwise walked down the recorded ladder (books) or marked partial (prints only). Fees: Kalshi taker formula 0.07 × p × (1−p)
per contract, rounded up to the cent per order, applied to entry and exit. Entry price: the recorded ask at the entry row.

**Data (fixed).** (a) Live: 204 markets Nov 12–15 (production rows + Kalshi final-240 s prints; 18 with order books).
(b) Replay-joined: Oct 15–Nov 12 2026 markets (engine replay on the Binance feed, Kalshi prints): all losses of the entry
or first-LOCKED side, all won windows with a risk step ≥ 0.5 % after entry, 120 random won windows without one. Replay timing
is on a 1 s grid, so lead times there carry ±1 s. (c) Prospective: tape pulls from 01:46 UTC Nov 15 on, untouched.

**Acceptance criteria (fixed).**
- P1 (losses): with d = 3 s, the trigger exits each actual displayed-entry loss on file (Nov 11, Nov 13, and any in set b) at a
  price ≥ 90 ¢ on the held side, measured on prints; at least one trigger must do so for every loss, or the failure is named.
- P2 (net): over set (a) and over set (b) separately, total cents per contract (exit policy minus hold, after fees, d = 3 s,
  10 contracts) is ≥ 0, with the loss cases included and nothing excluded.
- P3 (cost): unnecessary exits (trigger fired, window won) cost ≤ 1.0 ¢ per contract at the median and occur in ≤ 15 % of
  entries for the trigger chosen.
- P4 (lead): in the losses, the trigger precedes the first Kalshi print below 95 ¢ by ≥ 2 s in at least two thirds of cases.
- P5 (implementation): the page raises the exit alarm within 1.5 s of the server row that crossed the threshold, with the
  held side, the threshold crossed and the recorded ask/bid shown; regression tests cover stale readings, reconnects, restarts,
  market rollover and soft-gate flickers (no alarm without a risk step).
Trigger selection: the lowest threshold among T2, T3 that passes P2–P4 is preferred (fewer late exits); T1 is reported.
Thresholds are not changed after the results. If no trigger passes, the result is FAIL with the failed criterion.

**What this cannot show.** Two losing entries and about ten replay losses cannot establish the loss-side value to better than
a factor of two; the prospective tape pulls are the only untouched evidence and they accumulate at about one loss per
400–750 entries. The policy is a response rule, not a forecast improvement; it does not change the probability of a reversal.
