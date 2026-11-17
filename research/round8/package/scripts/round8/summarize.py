"""Statistics from the market-level table (one entry per market). usage: python3 -I summarize.py <market_table.json> <out.txt> [filter: all|I2|pre-I2|books|exact]"""
import sys, json, math, random, collections, datetime
D = json.load(open(sys.argv[1])); FILT = sys.argv[3] if len(sys.argv) > 3 else 'all'
W0 = D['windows']; EXC = D['excluded']; SIZES = D['config']['sizes']; LAGS = D['config']['lags']
def keep(w):
    if FILT == 'all': return True
    if FILT in ('I2', 'pre-I2'): return w['stratum'] == FILT
    if FILT == 'books': return w['in_tape'] and w['books_rows_in_120s'] > 0
    if FILT == 'exact': return w['candidate_method'].startswith('exact')
W = [w for w in W0 if keep(w)]
out = []; P = out.append
def cp(k, n, a=0.05):
    if n == 0: return (float('nan'), float('nan'))
    import math
    def betainv(p, a_, b_):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if ibeta(mid, a_, b_) < p: lo = mid
            else: hi = mid
        return (lo + hi) / 2
    def ibeta(x, a_, b_):
        # regularized incomplete beta via continued fraction (Numerical Recipes betacf)
        if x <= 0: return 0.0
        if x >= 1: return 1.0
        lbeta = math.lgamma(a_ + b_) - math.lgamma(a_) - math.lgamma(b_) + a_ * math.log(x) + b_ * math.log(1 - x)
        def betacf(a_, b_, x):
            MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
            qab, qap, qam = a_ + b_, a_ + 1, a_ - 1; c, d = 1.0, 1 - qab * x / qap
            if abs(d) < FPMIN: d = FPMIN
            d = 1 / d; h = d
            for m in range(1, MAXIT + 1):
                m2 = 2 * m; aa = m * (b_ - m) * x / ((qam + m2) * (a_ + m2)); d = 1 + aa * d
                if abs(d) < FPMIN: d = FPMIN
                c = 1 + aa / c
                if abs(c) < FPMIN: c = FPMIN
                d = 1 / d; h *= d * c; aa = -(a_ + m) * (qab + m) * x / ((a_ + m2) * (qap + m2)); d = 1 + aa * d
                if abs(d) < FPMIN: d = FPMIN
                c = 1 + aa / c
                if abs(c) < FPMIN: c = FPMIN
                d = 1 / d; de = d * c; h *= de
                if abs(de - 1) < EPS: break
            return h
        if x < (a_ + 1) / (a_ + b_ + 2): return math.exp(lbeta) * betacf(a_, b_, x) / a_
        return 1 - math.exp(lbeta) * betacf(b_, a_, 1 - x) / b_
    lo = 0.0 if k == 0 else betainv(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else betainv(1 - a / 2, k + 1, n - k)
    return lo, hi
def cp_upper1(k, n):  # one-sided 95 % upper
    return cp(k, n, 0.10)[1]
def pct(a, q):
    a = sorted(x for x in a if x is not None and not (isinstance(x, float) and math.isnan(x)))
    return a[min(len(a) - 1, int(q * len(a)))] if a else float('nan')
def boot_rate(entries, B=2000, seed=8, block='day'):
    # entries: list of (dayKey, lost); block bootstrap over days
    by = collections.defaultdict(list)
    for d, l in entries: by[d].append(l)
    days = sorted(by); rnd = random.Random(seed); rates = []
    for _ in range(B):
        n = k = 0
        for d in (rnd.choice(days) for _ in days): n += len(by[d]); k += sum(by[d])
        rates.append(k / n if n else float('nan'))
    return pct(rates, .025), pct(rates, .975), len(days)
def daykey(w, block='day'):
    t = datetime.datetime.fromtimestamp(w['closeMs'] / 1000, datetime.timezone.utc)
    return t.strftime('%Y-%m-%d') if block == 'day' else t.strftime('%Y-%m-%d') + 'h%02d' % (t.hour // 3 * 3)
def avail(o): return bool(o and o.get('book') and o.get('ask') is not None and o['ask'] <= 99.9 + 1e-9 and o['size'] >= 10)
def fee_cents(C, p_dollars): return math.ceil(7 * C * p_dollars * (1 - p_dollars) - 1e-9)
def fill(o, C, mode):
    if not avail(o): return None
    if mode == 'best': return o['ask'] if o['size'] >= C else None
    lad = o.get('ladder') or []; rem = C; cost = 0.0
    for a, s in lad:
        take = min(rem, s); cost += take * a; rem -= take
        if rem <= 1e-9: break
    return cost / C if rem <= 1e-9 else None
P('FILTER %s: windows in table %d (examined %d incl. %d excluded: %s)' % (FILT, len(W), len(W0) + len(EXC), len(EXC), dict(collections.Counter(e['reason'].split(' (')[0] for e in EXC))))
P('strata ' + str(dict(collections.Counter(w['stratum'] for w in W))) + ' | candidate method ' + str(dict(collections.Counter(w['candidate_method'].split(' (')[0] for w in W))) + ' | windows with tape books inside 120 s: %d' % sum(1 for w in W if w['books_rows_in_120s'] > 0))
for rule, bk, ck in (('EXACT (pFlip <= 0.002)', 'baseline', 'candidate'), ('ROUNDED DISPLAY (pFlip < 0.0025)', 'baseline_disp', 'candidate_disp')):
    P('== entry rule %s' % rule)
    for name, key in (('baseline I2 as served', bk), ('candidate build 9', ck)):
        E = [w for w in W if w[key]]; k = sum(1 for w in E if w[key]['lost']); n = len(E)
        lo, hi = cp(k, n); blo, bhi, nd = boot_rate([(daykey(w), int(w[key]['lost'])) for w in E]) if n else (float('nan'), float('nan'), 0)
        b3lo, b3hi, n3 = boot_rate([(daykey(w, '3h'), int(w[key]['lost'])) for w in E], block='3h') if n else (float('nan'), float('nan'), 0)
        taus = [w[key]['tau'] for w in E]; cus = [w[key]['cushion_bps'] for w in E]; cusd = [w[key]['cushion_usd'] for w in E]; sig = [w[key]['sigma_bps'] for w in E]
        P('  %-22s entries %4d  lost %d  won %d | loss rate %.3f%%  exact 95%% CI [%.3f%%, %.3f%%]  one-sided 95%% upper %.3f%% | day-block bootstrap 95%% [%.3f%%, %.3f%%] over %d days; 3-h blocks [%.3f%%, %.3f%%] over %d blocks' % (name, n, k, n - k, 100 * k / max(1, n), 100 * lo, 100 * hi, 100 * cp_upper1(k, n), 100 * blo, 100 * bhi, nd, 100 * b3lo, 100 * b3hi, n3))
        P('  %-22s time left p10/med/p90 %5.1f/%5.1f/%5.1f s | cushion bps p10/med/p90 %5.1f/%5.1f/%5.1f | cushion USD med %.2f | sigma bps/sqrt(s) med %.3f | regime %s' % ('', pct(taus, .1), pct(taus, .5), pct(taus, .9), pct(cus, .1), pct(cus, .5), pct(cus, .9), pct(cusd, .5), pct(sig, .5), dict(collections.Counter(w[key]['regime'] for w in E))))
    B = [w for w in W if w[bk]]; C = [w for w in W if w[ck]]
    P('  baseline entries withheld entirely by the candidate: %d (losing %d, winning %d): %s' % (sum(1 for w in B if not w[ck]), sum(1 for w in B if not w[ck] and w[bk]['lost']), sum(1 for w in B if not w[ck] and not w[bk]['lost']), [w['ticker'] for w in B if not w[ck]]))
    dl = [w[bk]['tau'] - w[ck]['tau'] for w in B if w[ck]]
    P('  baseline entries delayed by the candidate: %d of %d (same second %d); delay median %.1f s, p90 %.1f s, max %.1f; delayed > 30 s: %d, > 60 s: %d | baseline winners delayed: %d' % (sum(1 for x in dl if x > 0.05), len(dl), sum(1 for x in dl if x <= 0.05), pct(dl, .5), pct(dl, .9), max(dl) if dl else float('nan'), sum(1 for x in dl if x > 30), sum(1 for x in dl if x > 60), sum(1 for w in B if w[ck] and not w[bk]['lost'] and w[bk]['tau'] - w[ck]['tau'] > 0.05)))
    P('  candidate entries absent from the baseline under the same definition: %d' % sum(1 for w in W if w[ck] and not w[bk]))
    P('  withheld reasons at baseline-eligible seconds (all windows): %s' % dict(sum((collections.Counter(w['withheld_reasons_at_eligible_seconds']) for w in W), collections.Counter())))
    # groups
    for gname, gf, groups in (('time left at entry', lambda e: e['tau'], [(90, 120), (60, 90), (30, 60), (0, 30)]), ('cushion at entry (bps)', lambda e: e['cushion_bps'], [(0, 10), (10, 20), (20, 40), (40, 1e9)])):
        P('  groups by %s:' % gname)
        for lo, hi in groups:
            gb = [w for w in B if lo < gf(w[bk]) <= hi] if gname.startswith('time') else [w for w in B if lo <= gf(w[bk]) < hi]
            gc = [w for w in C if lo < gf(w[ck]) <= hi] if gname.startswith('time') else [w for w in C if lo <= gf(w[ck]) < hi]
            P('    %-10s baseline n %4d lost %d (upper95 %.2f%%) | candidate n %4d lost %d (upper95 %.2f%%)' % ('%g-%g' % (lo, min(hi, 999)), len(gb), sum(1 for w in gb if w[bk]['lost']), 100 * cp_upper1(sum(1 for w in gb if w[bk]['lost']), len(gb)) if gb else float('nan'), len(gc), sum(1 for w in gc if w[ck]['lost']), 100 * cp_upper1(sum(1 for w in gc if w[ck]['lost']), len(gc)) if gc else float('nan')))
    # opportunity at entries
    P('  -- quoted opportunity at the entry second (books from the tape, <= 3 s old; ask derived from the opposite side bids) --')
    for name, key in (('baseline', bk), ('candidate', ck)):
        E = [w for w in W if w[key]]; withbook = [w for w in E if (w[key]['offer'] or {}).get('book')]; av = [w for w in withbook if avail(w[key]['offer'])]
        asks = [w[key]['offer']['ask'] for w in withbook if w[key]['offer']['ask'] is not None]
        P('    %-9s entries %d | book at the entry second %d (no book %d) | available offer (<= 99.9, size >= 10) %d = %.1f%% of entries with a book | ask: <=99.5 %d, 99.6-99.7 %d, 99.8 %d, 99.9 %d, >99.9 %d, no ask %d' % (name, len(E), len(withbook), len(E) - len(withbook), len(av), 100 * len(av) / max(1, len(withbook)), sum(1 for a in asks if a <= 99.5), sum(1 for a in asks if 99.5 < a <= 99.7), sum(1 for a in asks if abs(a - 99.8) < .01), sum(1 for a in asks if abs(a - 99.9) < .01), sum(1 for a in asks if a > 99.95), len(withbook) - len(asks)))
        sz = [w[key]['offer']['size'] for w in av]; dp = [w[key]['offer'].get('depth_le_99.9') for w in av]; d98 = [w[key]['offer'].get('depth_le_99.8') for w in av]
        P('    %-9s among available: size at best p10/med/p90 %.0f/%.0f/%.0f | depth <= 99.9 p10/med/p90 %.0f/%.0f/%.0f | depth <= 99.8 med %.0f | lost among available %d' % ('', pct(sz, .1), pct(sz, .5), pct(sz, .9), pct(dp, .1), pct(dp, .5), pct(dp, .9), pct(d98, .5), sum(1 for w in av if w[key]['lost'])))
        P('    %-9s fillable at the entry second: ' % '' + ' | '.join('C=%d: best-only %d, ladder<=99.9 %d' % (Cn, sum(1 for w in av if fill(w[key]['offer'], Cn, 'best') is not None), sum(1 for w in av if fill(w[key]['offer'], Cn, 'ladder') is not None)) for Cn in SIZES))
        for L in LAGS:
            oL = [w[key].get('offer_lag%d' % L) for w in av]; adm = [w[key].get('admit_lag%d' % L) for w in av]
            P('    %-9s after %2d s: book present %d of %d available entries, offer still available %d, offer <= 99.9 and (candidate) still admitted %d, available at <= 99.8 %d' % ('', L, sum(1 for o in oL if o and o.get('book')), len(av), sum(1 for o in oL if avail(o)), sum(1 for o, a in zip(oL, adm) if avail(o) and (a or key.startswith('baseline'))), sum(1 for o in oL if avail(o) and o['ask'] <= 99.8 + 1e-9)))
        # net results
        for mode in ('best', 'ladder'):
            line = []
            for Cn in SIZES:
                pnl = []; dk = []; lost = 0; filled = 0
                for w in av:
                    px = fill(w[key]['offer'], Cn, mode)
                    if px is None: continue
                    filled += 1; f = fee_cents(Cn, px / 100); v = (Cn * (100 - px) - f) if not w[key]['lost'] else (-Cn * px - f); pnl.append(v); dk.append((daykey(w), v)); lost += int(w[key]['lost'])
                if not pnl: line.append('C=%d: none fillable' % Cn); continue
                by = collections.defaultdict(list)
                for d, v in dk: by[d].append(v)
                days = sorted(by); rnd = random.Random(8); means = []
                for _ in range(1000):
                    s = []; [s.extend(by[d]) for d in (rnd.choice(days) for _ in days)]; means.append(sum(s) / len(s))
                line.append('C=%d: fillable %d, lost %d, total %+.0f USD, mean %+.2f USD/entry (day-boot 95%% %+.2f..%+.2f), per contract %+.3f c' % (Cn, filled, lost, sum(pnl) / 100, sum(pnl) / len(pnl) / 100, pct(means, .025) / 100, pct(means, .975) / 100, sum(pnl) / len(pnl) / Cn))
            P('    %-9s hypothetical hold-to-settlement net, fee ceil(0.07·C·P·(1−P)) per order, fill = %s: ' % ('', 'full size at the best ask only if the best size covers it' if mode == 'best' else 'ladder within the same snapshot up to 99.9 c, VWAP') + ' | '.join(line))
    if rule.startswith('EXACT'):
        P('  -- per-second (labelled, not market-level) --')
        P('    baseline eligible seconds %d (with an available offer %d) | candidate admitted seconds %d (with an available offer %d) | windows with >= 1 available admitted second: candidate %d, baseline %d, of %d windows with books' % (sum(w['baseline_eligible_seconds'] for w in W), sum(w['baseline_available_eligible_seconds'] for w in W), sum(w['candidate_admitted_seconds'] for w in W), sum(w['candidate_available_admitted_seconds'] for w in W), sum(1 for w in W if w['candidate_available_admitted_seconds'] > 0), sum(1 for w in W if w['baseline_available_eligible_seconds'] > 0), sum(1 for w in W if w['books_rows_in_120s'] > 0)))
        P('    windows where the candidate admitted the other side after the baseline entry (before close): %d' % sum(1 for w in W if w['candidate_admitted_after_baseline_entry_other_side']))
        P('    exact-replay windows %d: recorded rows matched to the exact engine %d, reconstruction-vs-engine disagreements %d (all = missing-sample withholds)' % (sum(1 for w in W if w['candidate_method'].startswith('exact')), sum(w['exact_rows_matched'] for w in W), sum(w['recon_vs_exact_disagreements'] for w in W)))
open(sys.argv[2], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
