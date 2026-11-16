# PR10 adversarial statistical review (2026-11-16 ~02:35 UTC)

Disclosure: the reviewer is an instance of the same model family as the author and was briefed by the author; its independence
is limited to not having written the code. Every number below was recomputed with `python3 -I` from eval_pr10.json, cells.json,
the out_full_mu window files, the live tape and the replay engine source; helper scripts and the five modified copies of the
evaluation live in round4/cand/review_tmp/ (analysis1-3.py, tape_mu.py, eval_{w5,down,all,w5down,sep1}.py). Originals untouched.

1. Look-ahead / leakage: none found (minor). replay_chrono_pr5.js is chronological: the official value enters only 5 s after
   close through addBasisSample, so `mu` is the trailing basis mean at the decision; `bk` is the trailing regime; the FIT table
   uses closes before the split and the TEST evaluation reads FIT only. Live `basisMu` is constant within a window and first read
   at tau ~300 s. Caveat: 191 of 301 live windows have no tape row and get the default -3.4 USD, which sits at the 5th percentile
   of observed values (median -0.76, 5-95 % [-3.6, +1.4]) - a ~0.4 bps cushion bias that can move a bin only at its edge.
   Resolve: take basisMu from the live engine for every window, or show the result with mu = 0 for the 191.
2. Split mislabelled (minor). The code's SPLIT 1788566400 is 2026-09-05T00Z, not Sep 1 as declared and recorded; 376 windows
   closing Sep 1-4 are FIT by code. No leakage (build and eval share the constant). Rerun at the true Sep 1 split: 11 -> 4 losses,
   coverage 85.1 % (6,396 production entries). Resolve: correct the declaration/record text.
3. The design is not out of sample (material). The cell axes (horizon, regime group, basis-adjusted cushion) are exactly the
   strongest separators found in causal/summary.txt item 4 and settle/vulnerability_table.txt, both built on ALL 28,541 windows
   including TEST and its 11 losses; the live losses' cells were known (declared). PR10_DECLARATION.md and build_cells.py carry
   the same mtime (02:10:47 UTC; the header says 02:20), the evaluation ran at 02:13. "Out of sample" holds for the table values
   only, not for the choice of variables, bins (2.5 bps), rounding (up) or regime grouping.
4. Headline significance (material, in the candidate's favour). P(<= 4 losses in a random 5,156-of-6,035 subset | 11) = 0.00026;
   because the candidate's entries are a subset, this IS the one-sided Fisher test of withheld (7/879 = 0.80 %) vs admitted
   (4/5,156 = 0.08 %). Dependence: day-stratified permutation of the withheld labels p = 0.0001; day-cluster bootstrap of the rate
   difference 95 % CI [0.16 %, 1.38 %]. Multiplicity: Bonferroni x28 -> 0.0073 (x34 counting PR5's q and factor sub-variants
   -> 0.009). The replay association is real. Note that "withheld for good" is outcome-dependent (a window stays withheld because
   its cushion never grew into an admitting cell, the same path that loses), so this tests the rule's informativeness, not calibration.
5. Where the reduction lives (BLOCKING for the claim as stated). tau < 30 s: 707 of 1,117 production entries withheld (63 %),
   4 of 5 losses prevented, p = 0.40 - random withholding of 63 % does as well. tau >= 30 s: 172 of 4,918 withheld, 3 of 6
   prevented, p = 0.0008, and all three sit in the active regime (12 withheld, 3 losses; Oct 4 4.9 bps, Nov 2 10.8 bps, Nov 11
   6.2 bps); normal/quiet tau >= 30: 160 withheld, 0 of 2 prevented (Sep 6, Nov 1 02:45). Owner's class (tau >= 30, cushion
   >= 50 USD): 144 withheld, 1 of 3 prevented, p = 0.11. "Fewer losses at 85 % coverage" is a blunt sub-30-s cut plus three
   active-regime events; in the class that produced both live losses it is not significant.
6. Feed mismatch makes most of the TEST gain non-transferable (BLOCKING). The replay baseline runs on Binance USDC with a basis
   to the official index (mu median -8 USD, -23 USD in Nov; realised error p95 8.7 USD ~1.3 bps). Live rows carry ref OFFICIAL in
   91,446 of 91,527 rows: the live cushion is measured against the settlement index through the final 300 s, not only the final
   minute. The sub-30-s class that supplies 80 % of PR10's withholding and 4 of its 7 prevented losses is the settlement-basis
   class (F10: 12 of 19 such losses had the feed on the called side at close; live 0 of 113 late entries). The replay's 11/6,035 is
   therefore not the live loss profile (2/283, both 90-120 s and 15-18 bps, O/E 6.3 per F14), and in that profile see finding 5.
7. Reference class = policy, not calibration (material). The floor implies 77.4 expected losses among the 879 withheld entries;
   7 occurred (11x over-prediction), while production's <= 0.2 % implies 1.76 (4x under, P(>= 7) = 0.002). Among admitted
   entries: floor 4.79, pf 6.19, observed 4. Cells pool all leaders regardless of sigma/pf, so for LOCKED rows p_emp is not a
   probability; max(pf, p_emp) is a cut on (tau, regime, cushion). Admission = "cell with zero FIT losses and n >= 249": 181 of
   the 186 admitting cells have k_FIT = 0. Resolve: present PR10 as an entry rule and evaluate it as one; or build the cells from
   LOCKED rows (then the per-cell counts are 0-3 and the floor collapses to the production rate).
8. A4 as written is ill-posed; a defensible test passes (material). The 270 flagged entries: 28 in k = 0 cells with n_T <= 48
   (pure smoothing: 0.5/(n+1) > 1 % iff n <= 48), 100 in k = 1 cells (n_T 75-122, raw 0.8-1.3 %), 142 in three k = 2 cells
   (n_T 216-248, raw 0.81-0.93 %, smoothed 1.0-1.15 %). The author's "9 of 91 cells exceed FIT's upper95, ~2 expected" is not a
   test (the exceedance probability is not 2.5 %). Defensible: per-cell binomial P(k_T | n_T, FIT upper95) < 0.05 in 0 of 129
   used cells; pooled TEST losses in used cells 22 vs 18.3 expected under the smoothed FIT rates (Poisson p = 0.22): PASS. The
   raw FIT rate in those cells is 5/71,297 = 0.007 % vs TEST 22/19,684 = 0.112 % (16x): the winner's curse of selecting k = 0
   cells, which the Jeffreys smoothing absorbs. Restated bound: 11 % of admitted entries sit in cells whose FIT upper95 exceeds
   1 % (k = 0, 249 <= n < 368) and 59 % in cells with upper95 > 0.5 %; "<= 0.5 % by construction" is true of point estimates only.
9. Live "1 of 2 prevented" (material): P(>= 1 of the 2 losses in a random 22-of-283 withheld set) = 0.15; Fisher 1/22 vs 1/261
   p = 0.15; bins and rounding were fixed knowing both loss cells. Retrospective, as the declaration itself says. In form it is
   robust: Nov 15 is withheld in all six variants (cell rates 0.46-0.97 %), Nov 14 is admitted in all (0.08-0.15 %).
10. Sensitivity (material): TEST exact rule, production 11 losses. 5-bps bins: 2 losses but coverage 71.4 % (live 82.0 %) - A2
    FAILS; round-down horizon: 5 losses, 85.8 %; ALL table (in-sample): 4, 86.3 %; 5-bps + round-down: 4, 71.6 %; true Sep-1
    split: 4, 85.1 %. Loss counts are stable (2-5); coverage is not: A2 (>= 85 %) passes only with the declared 2.5-bps bins,
    by 0.1-0.9 points. Resolve: declare coverage as a reported quantity with a CI, not a pass/fail edge.
11. Missing cells admit silently (minor): 3 TEST entries were admitted in cells absent from FIT (120|normal|40-50,
    120|quiet|27.5-30, 80|normal|40-50; p_emp = None -> floor 0); none lost. PROVEN LOCKED bypass is negligible (21 replay rows,
    1 live). Resolve: treat a missing cell as withhold or fall back to the next coarser bin.
12. Delay and economics (minor): 49 % of admitted TEST entries are delayed (median 10 s, p90 30 s, 34 > 60 s); A3's "median
    0 s" is the same-moment majority. Later entries buy at higher asks (record: >= 99.5 share 84 % -> 91 %), and per-entry live
    P&L is negative under both rules (-0.61 vs -0.36 cents). The 14.6 % coverage loss is concentrated in sub-30-s entries.

Verdict: the out-of-sample claim "fewer losses at 85 % coverage" is supported as a replay statistic (p = 0.0003, robust to day
clustering and multiplicity) but NOT as evidence about the live system's losses: 4 of the 7 prevented losses and 80 % of the
withholding fall in the sub-30-s USDC-basis class that the live radar (official reference) does not share, the owner's class
shows 1 of 3 prevented (p = 0.11), and coverage clears 85 % only under the declared binning. Single most important caveat: the
TEST gain is mostly a feed artefact of the replay baseline, so the result does not transfer to the loss class seen live.
