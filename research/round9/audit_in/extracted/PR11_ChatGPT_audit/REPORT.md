# Independent ChatGPT audit of PR11 build 9 versus I2

Decision: hold release approval for two specific corrections/reconciliations. The supplied comparison is reproducible, but its replay does not simulate the candidate's own evolving lock state. A second, smaller issue is a denominator mismatch between the historical exposure table and the implementation. These findings do not establish that PR11 causes a losing trade. They do invalidate the claim that the supplied replay establishes all candidate behavior as withholding-only.

This audit executed the attached source locally. It did not access Render or change any running service. The supplied deployment captures establish what Claude captured, not independently authenticated live service behavior today.

## Identities and checks reproduced

- Attachment: `PR11_b9_vs_I2_verification_package_20261117.tar.gz`.
- All 148 entries in the supplied SHA256 manifest matched.
- Baseline source: `ca51a0c6f7cfd117f4db6f75ca1dec56e7c277674c97920fc82706b01548040f`.
- Candidate source: `a341016f9e22ae52089bb194e028ac97ccb24a34cc53c1ef09e8a032e44dbecf`.
- Recreated market_table.csv and summary_all.txt match the supplied outputs byte for byte.
- Candidate self-tests: 167/167 in gate, off and shadow. Baseline: 134/134. Boundaries: 29/29.
- Re-ran both exact files on T1, T2 and T3: 8,100 decisions per engine. Supplied-state replay reproduces the reported 8,099/8,100 I2 parity, 780 candidate withholds, and 22 reconstruction/missing-sample disagreements.
- Runtime here: Node 24.22.3, Python 3.12.14, ws 8.22.0. This is additional verification, not a replacement for testing on the intended deployment runtime.

## What the supplied method actually reports

These are reproduced outputs of Claude's method, not endorsed whole-path candidate results after the findings below.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Entries / losses | 403 / 2 | 401 / 0 |
| First-entry offers with recorded books | 173 / 202 | 7 / 200 |
| Windows with any eligible quoted offer, among 212 with books | 179 | 10 |
| Winners delayed | — | 380, median 32 seconds |
| Candidate first-entry quotes still available and admitted after 3 seconds | — | 2 of the original 7 |
| Same 3-second comparison with quoted ladder depth for 80,000 contracts | — | 1 of the original 7 |

The seven initial candidate offers comprise five at 99.9 cents and two at 99.8 cents. Quote depth is not a fill guarantee. The 80,000 quantity is the supplied scenario, not a recommendation or verification of the user's actual position. Missing books are not evidence that no offer existed.

Only 28 of the 424 table windows are labelled exact-replay windows; 396 rely on the offline reconstruction. That reconstruction does not recover missing sample checks or independently evolve candidate state. The reported candidate observations are retrospective counterfactuals, not a prospective deployment of the candidate.

## Finding A — candidate lock memory is overwritten with baseline memory

`scripts/round7/replay_tape28.js`, restoreAndDecide, assigns `S.LOCK25` from `rec.lock25` before EVERY decision. `dump_replay.js` invokes that restore for both engines. This is useful for checking calculation parity on recorded state. It is not sufficient for testing a policy that changes when LOCKED first occurs.

In the supplied candidate, `classify25` sets `ls.lockedSide` only when the actual decision becomes LOCKED or PROVEN LOCKED. PR11 withholds some of those decisions. `m25Decide` subsequently uses `lockedSide` to generate a REVERSAL WARNING and to retain the originally locked side. Consequently baseline memory and candidate memory can diverge.

The included `sequential_audit.js` preserves each engine's own LOCK25 between captured decisions, restores the same external observations otherwise, and seeds only the first observed decision in each market from recorded state. It uses no future samples. It is still a replay at the captured one-second decisions, not proof that unrecorded page-request decisions have been recovered.

Results over the 8,100 captured decisions in 28 markets:

- Baseline control: zero state/side differences against the supplied-state I2 replay. Eight rows have an internal lockedSide difference without a state/side difference.
- Candidate: 106 state/side differences in two markets. There are 485 differences if internal lockedSide is included; these are not 485 distinct trade changes.
- Candidate qualifying markets: 24 in the supplied-state replay; 25 when it retains its own lock history.
- The affected state/side markets are `KXBTC15M-26NOV131915-15` (84 rows) and `KXBTC15M-26NOV151930-30` (22 rows).

Concrete example, the November 13 Pacific / November 14 UTC loss:

| Field | Value |
|---|---|
| Ticker | KXBTC15M-26NOV131915-15 |
| Decision timestamp | 1794615293309 ms = 2026-11-14 00:14:53.309 UTC |
| Time remaining | 6.691 seconds |
| Replay with baseline state injected | REVERSAL WARNING, UP |
| Candidate keeping its own state | LOCKED, DOWN |
| Candidate reversal probability | 0.000842 (0.0842%) |
| Candidate exposure / floor | 14.31 / 14 bps |
| Action line | LOCKED — TOO LATE |

The DOWN lock persists for the final seven captured decisions. DOWN was the published winning side in the supplied result. This does not undo the refusal of the original losing UP entry and is not evidence of a new losing trade. It does contradict “no LOCKED on either side afterwards,” “candidate only withholds,” and the assertion that the recorded-state replay validates full candidate behavior. Whether it had an executable offer must be scored, not inferred from the state name or action line.

No aggregate replacement for 401 entries is claimed here: most windows lack the inputs for this exact chronological replay. Claude needs to correct the exact subset and label the limits of the reconstructed remainder.

## Finding B — historical and live exposure use different denominators

`sources/build_q_full.py` constructs historical moves as:

`abs(future_mean - current_price) / current_price * 10000`

`sources/pinradar_server_PR11_b9_c03385dc.js`, pr11Exposure, uses:

`abs(expected_settlement - strike) / strike * 10000`

and multiplies by 60 / remaining_prints inside the minute. The latter required dollar move must be expressed in the table's units before comparing to that table. Strike and current price are not identical. The declaration also contains the mismatch, so merely checking implementation against that declaration cannot catch it.

Recorded first qualifying candidate row:

| Field | Value |
|---|---|
| Ticker | KXBTC15M-26NOV152000-00 |
| Timestamp | 1794790749094 ms = 2026-11-16 00:59:09.094 UTC |
| Time remaining | 50.906 seconds; h = 51 |
| Strike / current proxy index | 64,707.58 / 64,883.71 |
| Exposure using strike | 32.0173418 bps |
| Exposure in table's current-price units | 31.9304292 bps |
| Frozen floor | 32 bps |

Build 9 admits that row; consistent units would withhold it at that timestamp. This was one admitted row in one market in the three tapes. It was a winner and there was no offer in the supplied entry snapshot, so no realized loss or execution harm is demonstrated. The discrepancy is small but is an actual threshold-comparison inconsistency. The included script reproduces the scan. Correcting units is not an invitation to tune the frozen floor to observed outcomes.

## Claims that the package cannot establish

1. The historical table uses absolute moves pooled over all seconds. Dividing its 0.05% two-sided rate by two assumes directional symmetry. Even symmetry would not establish the conditional loss rate among policy-selected, quoted entries. The claimed 3.6-times margin below break-even is not demonstrated by this calculation. Do not replace it with a different asserted safety multiple.
2. The supplied builder computes pooled and annual counts. Its comments mention volatility buckets, but the accumulation shown does not calculate a guarantee for every bucket. An all-regime pooled floor is not a maximum-per-regime bound.
3. The 92-million-second historical input and round-7 TEST/FIT replay traces are absent. Their derivation and reported 0/4,452 and 0/6,299 results cannot be independently reproduced from this package. Hashes and summaries are not substitutes for those inputs. Previously examined incidents remain diagnostic cases.
4. The candidate's supplied 0/401 has a two-sided exact 95% upper limit near 0.92% under the binomial calculation. It does not establish a loss rate below approximately 0.09% break-even. This statement does not depend on treating the unresolved comparison as a final valid strategy backtest.

## Fee and execution qualifications

`summarize.py` applies a whole-cent ceiling to fees and applies the quadratic fee once to an order's ladder VWAP. These are declared simulation assumptions; they have not been authenticated as this user's actual fill fees. Kalshi's current fee schedule specifies fee-plus-position-cost rounding to a centicent, and the API documentation distinguishes direct-member $0.0001 balance precision from non-direct-member $0.01 precision and describes per-order fill accumulation. Account-specific applicability must be checked or both cases reported. This is particularly relevant to small-size net figures; it does not rescue the sparse opportunity counts.

Official sources checked during this audit:

- https://kalshi.com/docs/kalshi-fee-schedule.pdf (effective July 7, 2026)
- https://docs.kalshi.com/getting_started/fee_rounding

No actual fill or profitable trading edge has been verified. The available quotes can disappear during reaction and order latency. Net figures should remain explicitly hypothetical.

## Bounded next action

Send this audit and its reproducer to Claude. Correct the chronological replay and denominator issue, rerun only affected comparisons, and return one reconciled release decision. Keep the historical thresholds frozen; do not deploy a looser table from examined outcomes. Preserve current production and existing authorizations. Do not deploy or change rollback authority on the basis of this audit request. Time-of-day research remains tabled for this release.

The completed tests are useful and should be reused. They demonstrate code consistency in the covered cases; they do not prove a near-certain tradable signal.
