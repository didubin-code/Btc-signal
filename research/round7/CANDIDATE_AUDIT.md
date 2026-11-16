# Round 7, section 3 — Candidate audit against the clarified requirement (2026-11-16)
The clarified requirement (owner, round 7): identify, before entry, conditions where the remaining settlement cushion gives demonstrably stronger protection against reversal while an executable offer remains, even at 99.8–99.9 ¢; substantially fewer opportunities are acceptable; a policy that never permits entry is not.
Every original test, verdict and record stands unchanged. No failed candidate is declared successful here. Categories: F1 = failed to reduce risk; F2 = failed validation outside its development data; F3 = reduced opportunities beyond a limit that was assumed, not stated by the owner; F4 = produced no executable opportunities; F5 = could not be evaluated reliably.

| Candidate | What it was | Original verdict (record) | Category under the clarified requirement | Note |
|---|---|---|---|---|
| A, B/B′ | earlier LOCKED threshold / calibration variants | failed frozen criteria (final_directive/AUDIT.md) | F1 | not re-opened |
| PR1 (Nov 14) | alert when a LOCKED call is withdrawn before the warning | lead over the warning 0–1 s: not carried forward (INCIDENT_FINDINGS §6) | F1 | an exit aid, not entry protection |
| PR2/PR3 standards (Nov 14) | "margin-inclusive risk ≤ 0.05 % / 0.01 %, 30–120 s left" | 6 reversals in 55,589 (0.05 %); 0 in-sample at 0.01 %, chosen after seeing them (PR3) | F2 (chosen on examined data), F3 (coverage assumed) | the thresholds were tuned on the data that showed the reversals |
| PR4 | the 0.01 % standard on unseen years and shifted windows | passed on unseen data with the buffer rule (replay_pub/PR4_*) | F5 for the clarified requirement | validated on the engine's own risk, not on executable offers; the page H1.2 that carried it was superseded |
| PR5 | model-free quiet-market safeguard (cushion table) | built into the two-test standard | see two-test | — |
| Two-test lock standard (H1.3+, PR6 walk-forward) | margin risk ≤ 0.001 % and cushion ≥ 1-in-100,000 move | thresholds tuned in sample (withdrawn); walk-forward audit; live 87 calls, 87 held; declines ~76 % of entries | F3 (and partly F4: live asks at those calls median 99.9) | the closest precursor of PR11 in spirit; its cushion test was a quantile of the whole 2020–2026 history including each decision's own future, and it was never evaluated for executable offers |
| C1, C2 (PR7) | recalibration of the active-regime ratio | O/E 2.67 and 1.81 vs production 0.81; G1–G5 failed (calib_r1) | F1 | — |
| PR8 | cushion-shrink rule | failed (round 2) | F1 | — |
| PR9 / H1.6 | exit alert at the 1 % step (sell the held side) | P2 fails on the replay-joined set; P3 marginal; prospective 1 of 12 events (round 3) | not an entry-protection candidate | kept frozen for its own prospective test |
| Bid-≥99 variant | act only while the held side's bid ≥ 99 | did nothing on the Nov 15 loss (bid already 58) | not entry protection | — |
| PR10 | settlement-history floor on the displayed risk | A4 TEST clause failed; A6 offers 66–72 % vs ≥ 90 % required (round 4) | F2 (A4) and F3 (A6) | A6's 90 % was an assumed opportunity-retention limit; the owner has since said fewer opportunities are acceptable. PR10's A4 failure (no out-of-sample risk reduction in the owner's entry class) stands on its own, so PR10 is not revived. A re-specification under the clarified objective is PR11, a different rule, not PR10 with a lower A6 |
| LIVE_VOL_SCALE 1.17 | feed-scale correction | withdrawn: production already at the fit scale (+4 %) (round 6) | F1 (premise refuted) | — |
| H1.2–H1.5 pages | superseded page standards | superseded; not publishable | — | — |

Audit of the two criteria the owner asked about:
* A2-type coverage floors (≥ 85 % of baseline entries retained; PR10) and A6 (≥ 90 % of entries with an offer ≤ 99.9 ¢) encoded an assumption that most existing entries must survive. The owner's clarified position removes the retention assumption but keeps the executable-offer requirement. PR11 therefore carries no retention criterion; its usability criterion (C3) is a floor of 5 % of tape windows with an executable admitted second and at least 8 such windows, and the full opportunity curve is reported so the trade-off is visible rather than assumed.
* Nothing in this audit changes a verdict. Where a rejected candidate's criterion was the retention limit (PR10 A6), the record notes it; PR10 still fails A4.
