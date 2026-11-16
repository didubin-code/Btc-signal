#!/usr/bin/env python3
"""Matched-winner analysis for R_disp losses.
Usage: python3 -I matched.py <features_R_disp.ndjson> <out matched.txt>
For every loss: 25 nearest winning entries of the same family by standardized Euclidean distance over
(tau, cushion bps, sig), with bk required equal when >= 25 such winners exist. Standardization uses the
population std of each feature over all winners of the family.
"""
import sys, os, json, math, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import quantile, median, pstdev, clopper_pearson, binom_cdf, fmt_ci

FEAT, OUT = sys.argv[1], sys.argv[2]
K = 25
rows = [json.loads(ln) for ln in open(FEAT)]
# Entries at the last trace row (tau=0.25) have no post-entry rows: for the dynamics summaries treat them as
# "no risk observed after entry" (max_risk := 0, crossed := False) and min cushion := entry cushion. Counted below.
N_NOPOST = 0
for r in rows:
    if r['n_post'] == 0:
        N_NOPOST += 1
        r['max_risk'] = 0.0; r['min_c_bps'] = r['cushion_bps']; r['min_c_usd'] = r['cushion_usd']; r['crossed'] = False
        r['final_c_bps'] = r['cushion_bps']; r['final_side'] = r['side']; r['final_st'] = r['st']; r['final_risk'] = r['pf']
L = []
def P(s=''): L.append(s)

ENTRY_FEATS = [  # (key, label, higher-is-what)
    ('cushion_bps', 'feed cushion bps (matched on)'),
    ('c_eff_bps', 'basis-adjusted cushion bps'),
    ('sig', 'sig (matched on)'),
    ('tau', 'tau (matched on)'),
    ('pf', 'pf at entry'),
    ('pfc', 'pfc at entry'),
    ('dc10_bps', 'pre-entry 10 s cushion change bps'),
    ('dc20_bps', 'pre-entry 20 s cushion change bps'),
    ('mu', 'mu (USD)'),
    ('mu_signed_usd', 'mu signed toward call (USD)'),
    ('secs_since_first_locked', 'secs since first LOCKED'),
    ('lock_streak_s', 'same-side LOCKED streak s'),
    ('max_risk_prev30', 'max entry-side risk prev 30 s'),
    ('soft', 'soft gates'),
    ('bk_changed_30', 'bk changed prev 30 s (0/1)'),
    ('marginBps', 'settlement margin bps (NOT knowable at entry)'),
    ('basis_err_usd', 'realized basis - mu (USD; NOT knowable at entry)'),
]
def val(e, k):
    v = e.get(k)
    if isinstance(v, bool): return 1.0 if v else 0.0
    return v

def pct_rank(x, xs):
    """share of xs strictly below x plus half the ties (mid-rank), in %"""
    if x is None or not xs: return None
    below = sum(1 for y in xs if y < x); ties = sum(1 for y in xs if y == x)
    return 100.0 * (below + 0.5 * ties) / len(xs)

def fmt(v, nd=3):
    if v is None: return 'None'
    if isinstance(v, bool): return 'Y' if v else 'N'
    if isinstance(v, float): return ('%.' + str(nd) + 'f') % v
    return str(v)

def run_family(family, full_blocks):
    fam_rows = [r for r in rows if r['family'] == family]
    winners = [r for r in fam_rows if r['won']]
    losses = [r for r in fam_rows if not r['won']]
    losses.sort(key=lambda r: (r['closeTs'], r['ticker']))
    sd = {k: pstdev([w[k] for w in winners]) for k in ('tau', 'cushion_bps', 'sig')}
    by_bk = collections.defaultdict(list)
    for w in winners: by_bk[w['bk']].append(w)
    P('=' * 118)
    P('FAMILY=%s  winners=%d  losses=%d  standardization std: tau=%.3f cushion_bps=%.3f sig=%.4f' % (family, len(winners), len(losses), sd['tau'], sd['cushion_bps'], sd['sig']))
    P('winners per bk: %s' % dict(sorted((k, len(v)) for k, v in by_bk.items())))
    P()
    agg = collections.defaultdict(list)   # feature -> list of loss percentile ranks
    agg_above = collections.defaultdict(lambda: [0, 0, 0])  # feature -> [above median, below median, ties]
    pooled = []          # all matched winner records (with repeats)
    pooled_ids = set()
    per_loss_rows = []
    for li, lo in enumerate(losses, 1):
        cands = by_bk[lo['bk']] if len(by_bk[lo['bk']]) >= K else winners
        bk_equal = len(by_bk[lo['bk']]) >= K
        def dist(w):
            return math.sqrt(((w['tau'] - lo['tau']) / sd['tau']) ** 2 + ((w['cushion_bps'] - lo['cushion_bps']) / sd['cushion_bps']) ** 2 + ((w['sig'] - lo['sig']) / sd['sig']) ** 2)
        scored = sorted(((dist(w), w['ticker'], w) for w in cands), key=lambda t: (t[0], t[1]))[:K]
        m = [t[2] for t in scored]; dmax = scored[-1][0]
        pooled.extend(m); pooled_ids.update(w['ticker'] for w in m)
        minc = [w['min_c_bps'] for w in m]; mr = [w['max_risk'] for w in m]
        sh = {thr: sum(1 for w in m if w['max_risk'] >= thr) / len(m) for thr in (0.005, 0.01, 0.10)}
        cross_share = sum(1 for w in m if w['crossed']) / len(m)
        # feature comparison
        comp = []
        for k, label in ENTRY_FEATS:
            xs = [val(w, k) for w in m if val(w, k) is not None]
            x = val(lo, k)
            pr = pct_rank(x, xs) if xs else None
            if pr is not None and not label.endswith('(NOT knowable at entry)') or (pr is not None):
                agg[k].append(pr)
                med = median(xs)
                if x > med: agg_above[k][0] += 1
                elif x < med: agg_above[k][1] += 1
                else: agg_above[k][2] += 1
            comp.append((k, label, x, median(xs) if xs else None, quantile(xs, 0.1) if xs else None, quantile(xs, 0.9) if xs else None, pr, len(xs)))
        per_loss_rows.append((lo, m, dmax, bk_equal, minc, mr, sh, cross_share, comp))
        if full_blocks:
            P('-' * 118)
            P('LOSS %2d  %s  close %s  side=%s truth=%s marginUsd=%+.2f (%+.2f bps)  class(strict)=%s' % (
                li, lo['ticker'], lo['closeUTC'], lo['side'], lo['truth'], lo['marginUsd'], lo['marginBps'], lo['loss_class']))
            P('         refined class: %s' % lo['loss_class_refined'])
            P('  ENTRY  tau=%.2f  cushion=%+.2f bps (%+.2f USD)  basis-adj cushion=%+.2f bps  sig=%.4f bk=%d soft=%d hard=%d  mu=%+.2f (signed toward call %+.2f)  pf=%.5f pfc=%.5f' % (
                lo['tau'], lo['cushion_bps'], lo['cushion_usd'], lo['c_eff_bps'], lo['sig'], lo['bk'], lo['soft'], lo['hard'], lo['mu'], lo['mu_signed_usd'], lo['pf'], lo['pfc']))
            P('         dc10=%s dc20=%s bps  bk_changed_30=%s (hist %d s)  secs_since_first_locked=%s  lock_streak=%d s%s  max_risk_prev30=%s  basis_reliance=%s' % (
                fmt(lo['dc10_bps'], 2), fmt(lo['dc20_bps'], 2), fmt(lo['bk_changed_30']), lo['bk_hist_s'], fmt(lo['secs_since_first_locked'], 2), lo['lock_streak_s'],
                ' (censored at trace start)' if lo['lock_streak_censored'] else '', fmt(lo['max_risk_prev30'], 4), lo['basis_reliance']))
            P('  POST   n_post=%d  min cushion=%+.2f bps @tau %s  max entry-side risk=%.4f @tau %s  first tau risk>=0.005: %s  >=0.01: %s  >=0.10: %s  >=0.5: %s' % (
                lo['n_post'], lo['min_c_bps'], fmt(lo['min_c_tau'], 2), lo['max_risk'], fmt(lo['max_risk_tau'], 2), fmt(lo['t_risk_005'], 2), fmt(lo['t_risk_01'], 2), fmt(lo['t_risk_10'], 2), fmt(lo['t_risk_50'], 2)))
            P('         crossed=%s t_cross=%s  lock withdrawn (state) at tau %s  side flip at tau %s  rows LOCKED same side after entry=%d  REVERSAL WARNING rows=%d  final: side=%s st=%s cushion=%+.2f bps risk=%.4f' % (
                fmt(lo['crossed']), fmt(lo['t_cross'], 2), fmt(lo['t_unlock_state'], 2), fmt(lo['t_side_flip'], 2), lo['n_post_locked_same_side'], lo['n_post_warning'], lo['final_side'], lo['final_st'], lo['final_c_bps'], lo['final_risk']))
            P('         realized basis (official - feed@0.25s)=%s USD vs mu=%+.2f -> basis error=%s USD' % (fmt(lo['realized_basis_usd'], 2), lo['mu'], fmt(lo['basis_err_usd'], 2)))
            P('  MATCHED WINNERS n=%d  bk equal required: %s  max std distance=%.3f  tau %.2f..%.2f  cushion %.2f..%.2f bps  sig %.4f..%.4f' % (
                len(m), 'yes' if bk_equal else 'NO (relaxed)', dmax, min(w['tau'] for w in m), max(w['tau'] for w in m), min(w['cushion_bps'] for w in m), max(w['cushion_bps'] for w in m), min(w['sig'] for w in m), max(w['sig'] for w in m)))
            P('         post-entry: min cushion bps median=%+.2f p10=%+.2f p90=%+.2f | max entry-side risk median=%.4f p90=%.4f | share reaching risk>=0.005: %.0f%%  >=0.01: %.0f%%  >=0.10 (warning) and still won: %.0f%% | share whose feed crossed strike: %.0f%%' % (
                median(minc), quantile(minc, 0.1), quantile(minc, 0.9), median(mr), quantile(mr, 0.9), 100 * sh[0.005], 100 * sh[0.01], 100 * sh[0.10], 100 * cross_share))
            P('         entry-time features, loss vs matched winners (median [p10, p90]; loss percentile rank within the 25):')
            for k, label, x, med, p10, p90, pr, nx in comp:
                P('           %-48s loss=%-10s winners med=%-10s [%s, %s]  rank=%s%s' % (label, fmt(x), fmt(med), fmt(p10), fmt(p90), ('%.0f%%' % pr) if pr is not None else 'n/a', ('  (n=%d)' % nx) if nx < len(m) else ''))
        else:
            per_loss_rows[-1] = per_loss_rows[-1]
    if not full_blocks:
        P('  compact per-loss table (FAMILY=%s):' % family)
        P('  %-26s %6s %7s %7s %5s %3s %7s %8s %6s | %8s %8s %6s | %12s %12s %7s %7s %7s' % ('ticker', 'tau', 'cushbps', 'ceffbps', 'sig', 'bk', 'mu', 'sfl', 'strk', 'min_c', 'maxrisk', 'class', 'mw_minc_med', 'mw_maxr_med', '>=.005', '>=.01', '>=.10'))
        for lo, m, dmax, bk_equal, minc, mr, sh, cs, comp in per_loss_rows:
            P('  %-26s %6.2f %7.2f %7.2f %5.2f %3d %7.2f %8s %6d | %8.2f %8.4f %6s | %12.2f %12.4f %6.0f%% %6.0f%% %6.0f%%' % (
                lo['ticker'], lo['tau'], lo['cushion_bps'], lo['c_eff_bps'], lo['sig'], lo['bk'], lo['mu'], fmt(lo['secs_since_first_locked'], 1), lo['lock_streak_s'],
                lo['min_c_bps'], lo['max_risk'], 'rev' if lo['loss_class'] == 'reversal' else 'basis', median(minc), median(mr), 100 * sh[0.005], 100 * sh[0.01], 100 * sh[0.10]))
    # ---- aggregate ----
    P()
    P('AGGREGATE (FAMILY=%s): %d losses x %d matched winners = %d winner-matches (%d distinct winning markets)' % (family, len(losses), K, len(pooled), len(pooled_ids)))
    n = len(pooled)
    for thr in (0.005, 0.01, 0.10, 0.5):
        k = sum(1 for w in pooled if w['max_risk'] >= thr)
        ku = len(set(w['ticker'] for w in pooled if w['max_risk'] >= thr))
        kl = sum(1 for lo in losses if lo['max_risk'] >= thr)
        P('  entry-side risk reached >= %-5s after entry: matched winners %4d/%d = %5.1f%% (distinct markets %d/%d = %.1f%%) | losses %d/%d = %.1f%%' % (
            thr, k, n, 100 * k / n, ku, len(pooled_ids), 100 * ku / len(pooled_ids), kl, len(losses), 100 * kl / len(losses)))
    kc = sum(1 for w in pooled if w['crossed']); kcl = sum(1 for lo in losses if lo['crossed'])
    P('  feed-only cushion went negative after entry: matched winners %d/%d = %.1f%% | losses %d/%d = %.1f%%' % (kc, n, 100 * kc / n, kcl, len(losses), 100 * kcl / len(losses)))
    # all winners baseline
    for thr in (0.005, 0.01, 0.10):
        k = sum(1 for w in winners if w['max_risk'] >= thr)
        P('  (baseline, ALL %s winners) risk >= %-5s after entry: %d/%d = %.1f%%' % (family, thr, k, len(winners), 100 * k / len(winners)))
    P()
    P('  Losses with NO warning at all after entry (max entry-side risk < 0.005, lock never withdrawn): %d of %d: %s' % (
        sum(1 for lo in losses if lo['max_risk'] < 0.005), len(losses), ' '.join(lo['ticker'] for lo in losses if lo['max_risk'] < 0.005)))
    P('  Losses whose risk never reached 0.10 (no REVERSAL WARNING-level signal): %d of %d' % (sum(1 for lo in losses if lo['max_risk'] < 0.10), len(losses)))
    P()
    P('  Warnings in matched winners vs losses (rows that reached entry-side risk >= 0.10 after entry):')
    ww = [w for w in pooled if w['max_risk'] >= 0.10]; lw = [lo for lo in losses if lo['max_risk'] >= 0.10]
    def desc(xs, key, nd=3):
        v = [x[key] for x in xs if x[key] is not None]
        return 'median=%s p10=%s p90=%s (n=%d)' % (fmt(median(v), nd), fmt(quantile(v, 0.1), nd), fmt(quantile(v, 0.9), nd), len(v)) if v else 'n/a'
    for key, label, nd in (('max_risk', 'max entry-side risk', 4), ('t_risk_10', 'tau when risk first >= 0.10', 2), ('t_risk_005', 'tau when risk first >= 0.005', 2), ('min_c_bps', 'min cushion bps', 2), ('n_post_warning', 'REVERSAL WARNING rows after entry', 1), ('tau', 'entry tau', 2)):
        P('    %-36s winners-with-warning: %-52s losses-with-warning: %s' % (label, desc(ww, key, nd), desc(lw, key, nd)))
    # time from entry to first warning
    def lead(xs):
        v = [x['tau'] - x['t_risk_10'] for x in xs if x['t_risk_10'] is not None]
        return 'median=%s p10=%s p90=%s (n=%d)' % (fmt(median(v), 2), fmt(quantile(v, 0.1), 2), fmt(quantile(v, 0.9), 2), len(v)) if v else 'n/a'
    P('    %-36s winners-with-warning: %-52s losses-with-warning: %s' % ('seconds from entry to first risk>=0.10', lead(ww), lead(lw)))
    def lead2(xs):
        v = [x['tau'] - x['t_risk_005'] for x in xs if x['t_risk_005'] is not None]
        return 'median=%s p10=%s p90=%s (n=%d)' % (fmt(median(v), 2), fmt(quantile(v, 0.1), 2), fmt(quantile(v, 0.9), 2), len(v)) if v else 'n/a'
    P('    %-36s winners-with-warning: %-52s losses-with-warning: %s' % ('seconds from entry to first risk>=0.005', lead2(ww), lead2(lw)))
    P()
    P('  Entry-time features: where does each loss sit within its own 25 matched winners? (percentile rank; under "no difference"')
    P('  ranks are uniform: ~10%% of losses below the winners\' p10, ~10%% above p90, half above the median). Sign test = exact two-sided')
    P('  binomial test of #losses above vs below the matched-winner median (ties dropped).')
    P('  %-48s %5s %9s %9s %9s %9s %9s %10s' % ('feature', 'n', 'mean rk', 'median rk', '<=p10', '>=p90', 'above/below', 'sign p'))
    for k, label in ENTRY_FEATS:
        prs = [p for p in agg[k] if p is not None]
        if not prs: continue
        a, b, t = agg_above[k]
        nn = a + b
        if nn:
            kk = min(a, b); pv = min(1.0, 2 * binom_cdf(nn, kk, 0.5))
        else: pv = None
        P('  %-48s %5d %8.1f%% %8.1f%% %9d %9d %9s %10s' % (label, len(prs), sum(prs) / len(prs), median(prs), sum(1 for p in prs if p <= 10), sum(1 for p in prs if p >= 90), '%d/%d' % (a, b), ('%.3f' % pv) if pv is not None else 'n/a'))
    P()
    # binary / threshold features: loss share vs pooled matched-winner share, exact binomial P(X >= k | n_losses, p_matched)
    P('  Binary entry-time features: share among losses vs share among their pooled matched winners (exact binomial P(X>=k | n, p_matched)):')
    def bshare(xs, fn):
        v = [fn(x) for x in xs if fn(x) is not None]
        return (sum(1 for x in v if x), len(v))
    for label, fn in (('bk changed in prev 30 s', lambda x: x['bk_changed_30']), ('soft gate > 0', lambda x: x['soft'] > 0),
                      ('cushion fell > 1 bps in prev 20 s (dc20 < -1)', lambda x: None if x['dc20_bps'] is None else x['dc20_bps'] < -1),
                      ('cushion rose > 1 bps in prev 20 s (dc20 > +1)', lambda x: None if x['dc20_bps'] is None else x['dc20_bps'] > 1),
                      ('mu helps the call (signed mu > 0)', lambda x: x['mu_signed_usd'] > 0),
                      ('feed on other side at entry (c <= 0)', lambda x: x['cushion_usd'] <= 0),
                      ('basis-adjusted cushion < 10 USD', lambda x: x['c_eff_usd'] < 10),
                      ('max entry-side risk prev 30 s >= 0.05', lambda x: None if x['max_risk_prev30'] is None else x['max_risk_prev30'] >= 0.05),
                      ('secs since first LOCKED < 10', lambda x: None if x['secs_since_first_locked'] is None else x['secs_since_first_locked'] < 10),
                      ('same-side LOCKED streak <= 2 s', lambda x: x['lock_streak_s'] <= 2)):
        kl, nl = bshare(losses, fn); kw, nw = bshare(pooled, fn)
        pw = kw / nw if nw else 0
        pv = (1.0 - binom_cdf(nl, kl - 1, pw)) if nl and kl > 0 else 1.0
        pv_lo = binom_cdf(nl, kl, pw) if nl else 1.0
        P('    %-50s losses %2d/%2d = %5.1f%%   matched winners %4d/%4d = %5.1f%%   P(X>=k)=%.3f  P(X<=k)=%.3f' % (label, kl, nl, 100 * kl / nl if nl else 0, kw, nw, 100 * pw, pv, pv_lo))
    P()
    k5 = sum(1 for w in winners if w['max_risk'] >= 0.5)
    P('  ALL %s winners reaching entry-side risk >= 0.5 after entry: %d/%d = %.2f%%; losses: %d/%d' % (family, k5, len(winners), 100 * k5 / len(winners), sum(1 for lo in losses if lo['max_risk'] >= 0.5), len(losses)))
    P()
    return losses, pooled

P('# MATCHED-WINNER ANALYSIS  (generated by scripts/matched.py)')
P('# Source: features_R_disp.ndjson. Primary = de-duplicated set (= usdc family). For each R_disp loss, the %d nearest R_disp' % K)
P('# winners of the same family by standardized Euclidean distance over (tau, cushion bps, sig), bk required equal when >= %d' % K)
P('# winners share the bk. Percentile ranks are mid-ranks. "risk" = entry-side flip risk (pf, or 1-pf if the called side flipped).')
P('# All numbers come from the replay files; nothing is simulated.')
P('# %d entries (both families) sit on the last trace row (tau=0.25) and have no post-entry rows; they are treated as' % N_NOPOST)
P('#   max_risk=0, not crossed, min cushion = entry cushion.')
P()
run_family('usdc', True)
P()
P('#' * 118)
P('# ROBUSTNESS: same analysis within the usdt family (same markets, BTC/USDT feed). Compact per-loss table + aggregate only.')
P('#' * 118)
run_family('usdt', False)
with open(OUT, 'w') as f: f.write('\n'.join(L) + '\n')
print('wrote', OUT, len(L), 'lines')
