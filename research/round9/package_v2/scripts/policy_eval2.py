"""Exposure-gate policy on window traces: entry at the first second in the final 120 s where the engine is LOCKED/PROVEN LOCKED with
pf <= PF (exact 0.002; displayed variant 0.0025 exclusive) AND R >= Rstar(h, theta) from the exceedance table (linear interpolation
between the table's horizons; h = ceil(tau), R = |gap+mu| bps * (60/h if tau <= 60 else 1)). Reports entries, losses, tau and cushion
distributions, and the engine's expected losses (sum pf) for the admitted entries; for each theta in the list, plus the baseline (theta = none).
usage: python3 -I policy_eval.py <q.json> <label> <records...> -- <traces...> -- <out.txt> [--mu0] [--pf 0.002|0.0025x]"""
import sys, json, gzip, math, collections
args = sys.argv[1:]; qf, label = args[0], args[1]; i1 = args.index('--'); i2 = args.index('--', i1 + 1)
recs_f = args[2:i1]; traces_f = args[i1 + 1:i2]; outp = args[i2 + 1]; mu0 = '--mu0' in args
pfmode = args[args.index('--pf') + 1] if '--pf' in args else '0.002'
outcomes = json.load(open(args[args.index('--outcomes') + 1])) if '--outcomes' in args else None
floor = float(args[args.index('--floor') + 1]) if '--floor' in args else 0.0
THETAS = [0.002, 0.001, 0.0005, 0.00025]
import os
RT = {th: {int(k): v for k, v in json.load(open(os.path.join(qf, 'rstar_%s.json' % n)))['rstar'].items()} for th, n in zip(THETAS, ('0.200', '0.100', '0.050', '0.025'))}
def rstar(th, h): return RT[th][min(120, max(1, h))]
win = {}
for f in recs_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        if not l.strip(): continue
        r = json.loads(l); tk = r['ticker']
        truth = r.get('truth') or ('UP' if r.get('result') == 'yes' else 'DOWN' if r.get('result') == 'no' else None)
        if outcomes is not None:
            truth = outcomes[tk]['proxyTruth'] if tk in outcomes else None
        if truth and r.get('strike'): win[tk] = (truth, float(r['strike']))
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
def admit_pf(pf): return (pf <= 0.002) if pfmode == '0.002' else (pf < 0.0025)
ent = {th: {} for th in THETAS + ['base']}
for f in traces_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        r = json.loads(l); tk = r['tk']
        if tk not in win: continue
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None or not isL(r.get('st')) or r.get('pf') is None or not admit_pf(r['pf']): continue
        truth, strike = win[tk]; ce = r['gap'] + (0.0 if mu0 else (r.get('mu') or 0.0))
        if ce == 0: continue
        leader = 'UP' if ce > 0 else 'DOWN'; h = math.ceil(tau - 1e-9); g = abs(ce) / strike * 1e4; R = g * (60.0 / h if tau <= 60 else 1.0)
        if g < floor: continue
        rec = (tau, g, R, leader != truth, r['pf'], r.get('bk'), tk)
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
P('EXPOSURE-GATE POLICY PR11 (frozen tables in %s) on %s | windows %d | pf rule %s | mu %s | outcomes %s | cushion floor %.1f bps' % (qf, label, len(win), pfmode, 'ignored' if mu0 else 'included', 'PROXY-DEFINED' if outcomes is not None else 'official settlement', floor))
P('R*(h): ' + ' || '.join('theta %.3f%%: ' % (100 * th) + ' '.join('h%d:%d' % (h, RT[th][h]) for h in (5, 10, 20, 30, 45, 60, 90, 120)) for th in THETAS))
P('  policy        | entries  lost   rate      upper95   | tau p10/median/p90 | cushion p10/median/p90 (bps) | entries tau>60 (lost) | tau<=60 (lost) | sum pf (model E) | O/E')
for th in ['base'] + THETAS:
    E = ent[th]; n = len(E); k = sum(1 for v in E.values() if v[3]); taus = sorted(v[0] for v in E.values()); gs = sorted(v[1] for v in E.values()); spf = sum(v[4] for v in E.values())
    pct = lambda a, qq: a[min(len(a) - 1, int(qq * len(a)))] if a else float('nan')
    P('  %-13s | %7d  %4d  %.4f%%  %.4f%%  | %5.1f/%5.1f/%5.1f | %5.1f/%5.1f/%5.1f | %6d (%d) | %6d (%d) | %8.2f | %s' % ('baseline' if th == 'base' else 'theta %.3f%%' % (100 * th), n, k, 100 * k / max(1, n), 100 * cp_upper(k, n), pct(taus, .1), pct(taus, .5), pct(taus, .9), pct(gs, .1), pct(gs, .5), pct(gs, .9), sum(1 for v in E.values() if v[0] > 60), sum(1 for v in E.values() if v[0] > 60 and v[3]), sum(1 for v in E.values() if v[0] <= 60), sum(1 for v in E.values() if v[0] <= 60 and v[3]), spf, ('%.2f' % (k / spf)) if spf > 0 else 'nan'))
    if k: P('      losses (ticker, tau, cushion, R, pf, bucket): ' + '; '.join('%s %.1f s, %.1f, %.1f, %.4f, %s' % (v[6], v[0], v[1], v[2], v[4], v[5]) for v in E.values() if v[3]))
# windows admitted by baseline but not by policy, with their losses
for th in THETAS:
    rem = [tk for tk in ent['base'] if tk not in ent[th]]; remlost = sum(1 for tk in rem if ent['base'][tk][3])
    P('  theta %.3f%%: baseline windows not admitted %d (of which baseline losses %d); baseline losses admitted by the policy %d' % (100 * th, len(rem), remlost, sum(1 for tk, v in ent['base'].items() if v[3] and tk in ent[th])))
json.dump({str(th): {tk: list(v) for tk, v in E.items()} for th, E in ent.items()}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
