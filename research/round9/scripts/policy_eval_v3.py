"""Exposure-gate policy on window traces with the exposure expressed in the exposure table's units (bps of the CURRENT proxy price p[t],
looked up in the 1-s close files) or, for comparison, of the strike (the round-7 convention). Otherwise identical to policy_eval2.py:
entry at the first second in the final 120 s where the engine is LOCKED/PROVEN LOCKED with pf <= 0.002 AND R >= R*(h, theta);
R = |gap+mu| bps x (60/h if tau <= 60 else 1), h = ceil(tau); optional cushion floor (bps, raw) and proxy outcomes.
usage: python3 -I policy_eval_v3.py <q.json> <label> <records.ndjson> -- <trace.ndjson> -- <out.txt> --sec <dir of YYYY-MM-DD.f64> --denominator index|strike [--floor 5] [--outcomes json] [--mu0]"""
import sys, json, gzip, math, collections, datetime, os
import numpy as np
args = sys.argv[1:]; qf, label = args[0], args[1]; i1 = args.index('--'); i2 = args.index('--', i1 + 1)
recs_f = args[2:i1]; traces_f = args[i1 + 1:i2]; outp = args[i2 + 1]; mu0 = '--mu0' in args
secdir = args[args.index('--sec') + 1]; denom = args[args.index('--denominator') + 1]
floor = float(args[args.index('--floor') + 1]) if '--floor' in args else 0.0
outcomes = json.load(open(args[args.index('--outcomes') + 1])) if '--outcomes' in args else None
q = json.load(open(qf)); H = q['H']; ex = q['exceed']; tot = q['totals']; THETAS = [0.002, 0.001, 0.0005, 0.00025]
def rstar_tab(theta):
    return {h: next(R for R in range(len(ex['%d|all' % h])) if ex['%d|all' % h][R] <= theta * tot['%d|all' % h]) for h in H}
RT = {th: rstar_tab(th) for th in THETAS}
def rstar(th, h):
    t = RT[th]
    if h <= H[0]: return t[H[0]]
    if h >= H[-1]: return t[H[-1]]
    for a, b in zip(H, H[1:]):
        if a <= h <= b: return t[a] + (t[b] - t[a]) * (h - a) / (b - a)
win = {}
for f in recs_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        if not l.strip(): continue
        r = json.loads(l); tk = r['ticker']
        truth = r.get('truth') or ('UP' if r.get('result') == 'yes' else 'DOWN' if r.get('result') == 'no' else None)
        if outcomes is not None: truth = outcomes[tk]['proxyTruth'] if tk in outcomes else None
        if truth and r.get('strike') and r.get('closeTs'): win[tk] = (truth, float(r['strike']), int(r['closeTs']))
days = {}
def price_at(ts_s):
    d = datetime.datetime.fromtimestamp(ts_s, datetime.timezone.utc); key = d.strftime('%Y-%m-%d')
    if key not in days:
        p = os.path.join(secdir, key + '.f64'); arr = np.fromfile(p, dtype='<f8') if os.path.exists(p) else None
        if arr is not None:
            bad = ~np.isfinite(arr) | (arr <= 0)
            if bad.any(): idx = np.where(~bad, np.arange(len(arr)), 0); np.maximum.accumulate(idx, out=idx); arr = arr[idx]
        days[key] = arr
    arr = days[key]
    if arr is None: return None
    return float(arr[d.hour * 3600 + d.minute * 60 + d.second])
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
ent = {th: {} for th in THETAS + ['base']}; nopx = 0; rows_used = 0
for f in traces_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        r = json.loads(l); tk = r['tk']
        if tk not in win: continue
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None or not isL(r.get('st')) or r.get('pf') is None or r['pf'] > 0.002: continue
        truth, strike, closeTs = win[tk]; ce = r['gap'] + (0.0 if mu0 else (r.get('mu') or 0.0))
        if ce == 0: continue
        px = strike
        if denom == 'index':
            p = price_at(closeTs - tau)
            if p is None or not (p > 0): nopx += 1; continue
            px = p
        leader = 'UP' if ce > 0 else 'DOWN'; h = math.ceil(tau - 1e-9); g = abs(ce) / px * 1e4; graw = abs(ce) / strike * 1e4
        if graw < floor: continue
        R = g * (60.0 / h if tau <= 60 else 1.0); rows_used += 1
        rec = (tau, g, R, leader != truth, r['pf'], r.get('bk'))
        if tk not in ent['base'] or tau > ent['base'][tk][0]: ent['base'][tk] = rec
        for th in THETAS:
            if R >= rstar(th, h) and (tk not in ent[th] or tau > ent[th][tk][0]): ent[th][tk] = rec
def cp_upper(k, n):
    if n == 0: return float('nan')
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k + 1)) if 0 < p < 1 else (1.0 if p <= 0 else 0.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
out = []; P = out.append
P('EXPOSURE-GATE POLICY PR11 on %s | windows %d | exposure denominator %s (%s) | cushion floor %.1f bps (raw, strike units) | mu %s | outcomes %s | eligible trace rows used %d, rows without a price %d' % (label, len(win), denom, 'bps of the current proxy price p[t] from the 1-s closes' if denom == 'index' else 'bps of the strike (round-7 convention)', floor, 'ignored' if mu0 else 'included', 'proxy-defined' if outcomes else 'official settlement', rows_used, nopx))
P('  policy        | entries  lost   rate      upper95   | tau p10/median/p90 | cushion p10/median/p90 (bps) | tau>60 (lost) | tau<=60 (lost)')
pct = lambda a, qq: a[min(len(a) - 1, int(qq * len(a)))] if a else float('nan')
for th in ['base'] + THETAS:
    E = ent[th]; n = len(E); k = sum(1 for v in E.values() if v[3]); taus = sorted(v[0] for v in E.values()); gs = sorted(v[1] for v in E.values())
    P('  %-13s | %7d  %4d  %.4f%%  %.4f%%  | %5.1f/%5.1f/%5.1f | %5.1f/%5.1f/%5.1f | %6d (%d) | %6d (%d)' % ('baseline' if th == 'base' else 'theta %.3f%%' % (100 * th), n, k, 100 * k / max(1, n), 100 * cp_upper(k, n), pct(taus, .1), pct(taus, .5), pct(taus, .9), pct(gs, .1), pct(gs, .5), pct(gs, .9), sum(1 for v in E.values() if v[0] > 60), sum(1 for v in E.values() if v[0] > 60 and v[3]), sum(1 for v in E.values() if v[0] <= 60), sum(1 for v in E.values() if v[0] <= 60 and v[3])))
    if th != 'base' and k: P('      losses (tau, cushion, R, pf): ' + '; '.join('%.1f s, %.1f, %.1f, %.4f' % (v[0], v[1], v[2], v[4]) for v in E.values() if v[3]))
for th in THETAS:
    rem = [tk for tk in ent['base'] if tk not in ent[th]]
    P('  theta %.3f%%: baseline windows not admitted %d (of which baseline losses %d); baseline losses admitted by the policy %d' % (100 * th, len(rem), sum(1 for tk in rem if ent['base'][tk][3]), sum(1 for tk, v in ent['base'].items() if v[3] and tk in ent[th])))
json.dump({str(th): {tk: list(v) for tk, v in E.items()} for th, E in ent.items()}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
