"""Statistics from the version-2 market table. usage: python3 -I summarize_v2.py <market_table.json> <out.txt> [all|I2|pre-I2|books|exact]"""
import sys, json, math, random, collections, datetime
D = json.load(open(sys.argv[1])); FILT = sys.argv[3] if len(sys.argv) > 3 else 'all'
W0 = D['windows']; EXC = D['excluded']; SIZES = [100, 1000, 10000, 80000]; LAGS = D['config']['lags']
def keep(w):
    if FILT == 'all': return True
    if FILT in ('I2', 'pre-I2'): return w['stratum'] == FILT
    if FILT == 'books': return w['in_tape'] and w['books_rows_in_120s'] > 0
    if FILT == 'exact': return w['candidate_method'].startswith('exact')
W = [w for w in W0 if keep(w)]; out = []; P = out.append
def ibeta(x, a_, b_):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lbeta = math.lgamma(a_ + b_) - math.lgamma(a_) - math.lgamma(b_) + a_ * math.log(x) + b_ * math.log(1 - x)
    def betacf(a_, b_, x):
        MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300; qab, qap, qam = a_ + b_, a_ + 1, a_ - 1; c, d = 1.0, 1 - qab * x / qap
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
def betainv(p, a_, b_):
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if ibeta(mid, a_, b_) < p: lo = mid
        else: hi = mid
    return (lo + hi) / 2
def cp(k, n, a=0.05):
    if n == 0: return (float('nan'), float('nan'))
    return (0.0 if k == 0 else betainv(a / 2, k, n - k + 1)), (1.0 if k == n else betainv(1 - a / 2, k + 1, n - k))
def cp_upper1(k, n): return cp(k, n, 0.10)[1]
def pct(a, q):
    a = sorted(x for x in a if x is not None and not (isinstance(x, float) and math.isnan(x))); return a[min(len(a) - 1, int(q * len(a)))] if a else float('nan')
def daykey(w): return datetime.datetime.fromtimestamp(w['closeMs'] / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
def boot_rate(entries, B=2000, seed=8):
    by = collections.defaultdict(list)
    for d, l in entries: by[d].append(l)
    days = sorted(by); rnd = random.Random(seed); rates = []
    for _ in range(B):
        n = k = 0
        for d in (rnd.choice(days) for _ in days): n += len(by[d]); k += sum(by[d])
        rates.append(k / n if n else float('nan'))
    return pct(rates, .025), pct(rates, .975), len(days)
def avail(o): return bool(o and o.get('book') and o.get('ask') is not None and o['ask'] <= 99.9 + 1e-9 and o['size'] >= 10)
def fill(o, C, mode):
    if not avail(o): return None
    if mode == 'best': return o['ask'] if o['size'] >= C else None
    lad = o.get('ladder') or []; rem = C; cost = 0.0
    for a, s in lad:
        take = min(rem, s); cost += take * a; rem -= take
        if rem <= 1e-9: break
    return cost / C if rem <= 1e-9 else None
def cost_dollars(C, p_cents, feemode):
    """Total cost of buying C contracts at p (cents each) incl. fee, in dollars. Kalshi quadratic taker fee 0.07·C·P·(1−P).
    legacy_cent: fee rounded up to the whole cent per order (the production server's default model). doc_nondirect / doc_direct:
    Kalshi's published rounding (docs.kalshi.com, Fee Rounding): trade fee = ceil to $0.000001 of the model fee; the balance change
    (revenue − fee) is aligned to the user's precision ($0.01 non-direct, $0.0001 direct member) by a rounding fee."""
    P = p_cents / 100.0; model = 0.07 * C * P * (1 - P); rev = C * P
    if feemode == 'legacy_cent': return rev + math.ceil(model * 100 - 1e-9) / 100
    fee6 = math.ceil(model * 1e6 - 1e-9) / 1e6; grid = 0.01 if feemode == 'doc_nondirect' else 0.0001
    return math.ceil((rev + fee6) / grid - 1e-9) * grid
P('FILTER %s: windows in table %d (examined %d incl. %d excluded: %s) | denominator %s' % (FILT, len(W), len(W0) + len(EXC), len(EXC), dict(collections.Counter(e['reason'].split(' (')[0] for e in EXC)), D['config'].get('denominator')))
P('strata ' + str(dict(collections.Counter(w['stratum'] for w in W))) + ' | candidate method ' + str(dict(collections.Counter(w['candidate_method'].split(' (')[0] for w in W))) + ' | windows with tape books inside 120 s: %d | reconstruction-vs-exact per-second check (capture windows): %s' % (sum(1 for w in W if w['books_rows_in_120s'] > 0), D.get('recon_vs_exact_per_second')))
for rule, bk, ck in (('EXACT (pFlip <= 0.002)', 'baseline', 'candidate'), ('ROUNDED DISPLAY (pFlip < 0.0025)', 'baseline_disp', 'candidate_disp')):
    P('== entry rule %s' % rule)
    for name, key in (('baseline I2 as served', bk), ('candidate build 10', ck)):
        E = [w for w in W if w[key]]; k = sum(1 for w in E if w[key]['lost']); n = len(E); lo, hi = cp(k, n)
        blo, bhi, nd = boot_rate([(daykey(w), int(w[key]['lost'])) for w in E]) if n else (float('nan'), float('nan'), 0)
        taus = [w[key]['tau'] for w in E]; cus = [w[key]['cushion_bps'] for w in E]
        P('  %-22s entries %4d  lost %d  won %d | loss rate %.3f%%  exact 95%% CI [%.3f%%, %.3f%%]  one-sided 95%% upper %.3f%% | day-block bootstrap 95%% [%.3f%%, %.3f%%] over %d days | time left p10/med/p90 %5.1f/%5.1f/%5.1f s | cushion bps med %.1f' % (name, n, k, n - k, 100 * k / max(1, n), 100 * lo, 100 * hi, 100 * cp_upper1(k, n), 100 * blo, 100 * bhi, nd, pct(taus, .1), pct(taus, .5), pct(taus, .9), pct(cus, .5)))
    B = [w for w in W if w[bk]]; C = [w for w in W if w[ck]]
    P('  baseline entries withheld entirely by the candidate: %d (losing %d, winning %d): %s' % (sum(1 for w in B if not w[ck]), sum(1 for w in B if not w[ck] and w[bk]['lost']), sum(1 for w in B if not w[ck] and not w[bk]['lost']), [w['ticker'] for w in B if not w[ck]]))
    same = [w for w in B if w[ck] and w[ck]['side'] == w[bk]['side']]; dl = [w[bk]['tau'] - w[ck]['tau'] for w in same]
    P('  same-side candidate entries %d: delayed %d (same second %d); delay median %.1f s, p90 %.1f s, max %.1f; > 30 s: %d, > 60 s: %d | baseline winners delayed: %d' % (len(same), sum(1 for x in dl if x > 0.05), sum(1 for x in dl if x <= 0.05), pct(dl, .5), pct(dl, .9), max(dl) if dl else float('nan'), sum(1 for x in dl if x > 30), sum(1 for x in dl if x > 60), sum(1 for w in same if not w[bk]['lost'] and w[bk]['tau'] - w[ck]['tau'] > 0.05)))
    opp = [w for w in W if w[ck] and (not w[bk] or w[ck]['side'] != w[bk]['side'])]
    P('  candidate entries on the OPPOSITE side of the baseline entry (or without a baseline entry): %d — kinds %s; lost %d; with an available offer at that second %d; actions %s' % (len(opp), dict(collections.Counter(w[ck]['kind'] for w in opp)), sum(1 for w in opp if w[ck]['lost']), sum(1 for w in opp if avail(w[ck]['offer'])), dict(collections.Counter((w[ck].get('action') or 'n/a') for w in opp))))
    for w in opp: P('      %s result %s | baseline %s | candidate %.1f s %s pFlip %.5f [%s] action %s offer %s' % (w['ticker'], w['truth'], ('%.1f s %s %s' % (w[bk]['tau'], w[bk]['side'], 'LOST' if w[bk]['lost'] else 'won')) if w[bk] else 'none', w[ck]['tau'], w[ck]['side'], w[ck]['pFlip'], w[ck]['kind'], w[ck].get('action'), ('%.1f x %d' % (w[ck]['offer']['ask'], w[ck]['offer']['size'])) if w[ck]['offer'] and w[ck]['offer'].get('ask') is not None else ('no ask' if w[ck]['offer'] and w[ck]['offer'].get('book') else 'no book')))
    P('  windows with any opposite-side candidate LOCKED second after the baseline entry: %d (reconstruction-kind %d, exact %d); with an available offer on that side %d' % (sum(1 for w in W if w['opposite_side_first']), sum(1 for w in W if w['opposite_side_first'] and 'reconstruction' in (w['opposite_side_first']['kind'] or '')), sum(1 for w in W if w['opposite_side_first'] and 'exact' in (w['opposite_side_first']['kind'] or '')), sum(1 for w in W if w['opposite_side_first'] and w['opposite_side_first']['offer_available'])))
    P('  withheld reasons at baseline-eligible seconds: %s' % dict(sum((collections.Counter(w['withheld_reasons_at_eligible_seconds']) for w in W), collections.Counter())))
    for gname, gf, groups in (('time left at entry', lambda e: e['tau'], [(90, 120), (60, 90), (30, 60), (0, 30)]), ('cushion at entry (bps)', lambda e: e['cushion_bps'], [(0, 10), (10, 20), (20, 40), (40, 1e9)])):
        P('  groups by %s:' % gname)
        for lo, hi in groups:
            sel = (lambda e: lo < gf(e) <= hi) if gname.startswith('time') else (lambda e: lo <= gf(e) < hi)
            gb = [w for w in B if sel(w[bk])]; gc = [w for w in C if sel(w[ck])]
            P('    %-10s baseline n %4d lost %d | candidate n %4d lost %d' % ('%g-%g' % (lo, min(hi, 999)), len(gb), sum(1 for w in gb if w[bk]['lost']), len(gc), sum(1 for w in gc if w[ck]['lost'])))
    P('  -- quoted opportunity at the entry second (books <= 3 s old; ask = 100 - opposite-side bid) --')
    for name, key in (('baseline', bk), ('candidate', ck)):
        E = [w for w in W if w[key]]; withbook = [w for w in E if (w[key]['offer'] or {}).get('book')]; av = [w for w in withbook if avail(w[key]['offer'])]; asks = [w[key]['offer']['ask'] for w in withbook if w[key]['offer']['ask'] is not None]
        P('    %-9s entries %d | book at the entry second %d | available offer %d (%.1f%% of with-book) | ask <=99.5 %d, 99.6-99.7 %d, 99.8 %d, 99.9 %d, none %d | depth <= 99.9 med %.0f | lost among available %d' % (name, len(E), len(withbook), len(av), 100 * len(av) / max(1, len(withbook)), sum(1 for a in asks if a <= 99.5), sum(1 for a in asks if 99.5 < a <= 99.7), sum(1 for a in asks if abs(a - 99.8) < .01), sum(1 for a in asks if abs(a - 99.9) < .01), len(withbook) - len(asks), pct([w[key]['offer'].get('depth_le_99.9') for w in av], .5), sum(1 for w in av if w[key]['lost'])))
        P('    %-9s fillable at the entry second: ' % '' + ' | '.join('C=%d: best-only %d, ladder %d' % (Cn, sum(1 for w in av if fill(w[key]['offer'], Cn, 'best') is not None), sum(1 for w in av if fill(w[key]['offer'], Cn, 'ladder') is not None)) for Cn in SIZES))
        for L in LAGS:
            oL = [w[key].get('offer_lag%d' % L) for w in av]; adm = [w[key].get('admit_lag%d' % L) for w in av]
            P('    %-9s after %2d s: offer still available %d of %d, still available and still eligible/admitted %d, available at <= 99.8 %d' % ('', L, sum(1 for o in oL if avail(o)), len(av), sum(1 for o, a in zip(oL, adm) if avail(o) and a), sum(1 for o in oL if avail(o) and o['ask'] <= 99.8 + 1e-9)))
        for feemode in ('legacy_cent', 'doc_nondirect', 'doc_direct'):
            line = []
            for Cn in SIZES:
                pnl = []; lost = 0
                for w in av:
                    px = fill(w[key]['offer'], Cn, 'ladder')
                    if px is None: continue
                    cost = cost_dollars(Cn, px, feemode); v = (Cn * 1.0 - cost) if not w[key]['lost'] else -cost; pnl.append(v); lost += int(w[key]['lost'])
                line.append('C=%d: fillable %d, lost %d, total %+.2f USD, per contract %+.4f c' % (Cn, len(pnl), lost, sum(pnl), 100 * sum(pnl) / max(1, len(pnl)) / Cn) if pnl else 'C=%d: none fillable' % Cn)
            P('    %-9s HYPOTHETICAL hold-to-settlement net (ladder fill within the snapshot, fee %s): ' % ('', feemode) + ' | '.join(line))
    if rule.startswith('EXACT'):
        P('  -- per-second (labelled) --')
        P('    baseline eligible seconds %d (with an available offer %d) | candidate admitted seconds %d (with an available offer %d) | windows with >= 1 available admitted second: candidate %d, baseline %d, of %d windows with books | served REVERSAL WARNING seconds %d' % (sum(w['baseline_eligible_seconds'] for w in W), sum(w['baseline_available_eligible_seconds'] for w in W), sum(w['candidate_admitted_seconds'] for w in W), sum(w['candidate_available_admitted_seconds'] for w in W), sum(1 for w in W if w['candidate_available_admitted_seconds'] > 0), sum(1 for w in W if w['baseline_available_eligible_seconds'] > 0), sum(1 for w in W if w['books_rows_in_120s'] > 0), sum(w['served_reversal_warning_seconds'] for w in W)))
open(sys.argv[2], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
