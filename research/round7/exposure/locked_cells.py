"""FIT cell table restricted to engine-LOCKED rows (pf <= 0.002): losses / rows / distinct windows by tau-bin x R-bin and tau-bin x raw-gap-bin,
with the model's expected losses (sum of pf) -> O/E per cell. Also the distribution of gap at the baseline entry second (first LOCKED pf<=0.002 in [0,120]).
usage: python3 -I locked_cells.py <records...> -- <traces...> -- <out.txt>"""
import sys, json, gzip, math, collections
args = sys.argv[1:]; i1 = args.index('--'); i2 = args.index('--', i1 + 1)
win = {}
for f in args[:i1]:
    for l in open(f):
        if not l.strip(): continue
        r = json.loads(l)
        if r.get('truth') and r.get('strike'): win[r['ticker']] = (r['truth'], float(r['strike']))
TB = [('0-10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120.01)]
RB = [('<10', 0, 10), ('10-15', 10, 15), ('15-20', 15, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120), ('>=120', 120, 1e9)]
cellR = collections.defaultdict(lambda: [0, 0, 0.0, set(), set()]); cellG = collections.defaultdict(lambda: [0, 0, 0.0, set(), set()])
base = {}
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
for f in args[i1 + 1:i2]:
    for l in gzip.open(f, 'rt'):
        r = json.loads(l); tk = r['tk']
        if tk not in win: continue
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None or not isL(r.get('st')) or r.get('pf') is None or r['pf'] > 0.002: continue
        truth, strike = win[tk]; ce = r['gap'] + (r.get('mu') or 0.0)
        if ce == 0: continue
        leader = 'UP' if ce > 0 else 'DOWN'; rem = min(60, math.ceil(tau - 1e-9)); g = abs(ce) / strike * 1e4; R = g * (60.0 / rem if tau <= 60 else 1.0)
        lost = leader != truth
        tb = next(n for n, lo, hi in TB if lo <= tau < hi)
        for table, val in ((cellR, R), (cellG, g)):
            rb = next(n for n, lo, hi in RB if lo <= val < hi); c = table[(tb, rb)]; c[0] += 1; c[1] += int(lost); c[2] += r['pf']; c[3].add(tk)
            if lost: c[4].add(tk)
        if tk not in base or tau > base[tk][0]: base[tk] = (tau, g, R, lost, r['pf'], r.get('bk'))
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
for name, table in (('R = required adverse mean move of the remaining prints (bps)', cellR), ('raw cushion |gap| (bps)', cellG)):
    P('ENGINE-LOCKED ROWS (pf <= 0.002) by seconds left x %s: lost windows/windows [rows: lost/n, O/E = lost rows / sum pf]' % name)
    P('  tau \\ bin   ' + ''.join('%-30s' % n for n, _, _ in RB))
    for tn, _, _ in TB:
        line = '  %-10s ' % tn
        for rn, _, _ in RB:
            n, k, e, W, LW = table.get((tn, rn), [0, 0, 0.0, set(), set()])
            line += ('%d/%d [%d/%d O/E %.2f]' % (len(LW), len(W), k, n, (k / e) if e > 0 else float('nan'))).ljust(30) if n else '-'.ljust(30)
        P(line)
    P('')
P('BASELINE ENTRIES (first LOCKED pf <= 0.002 second in the final 120 s): %d windows, %d lost' % (len(base), sum(1 for v in base.values() if v[3])))
gs = sorted(v[1] for v in base.values()); P('  cushion at entry (bps): p10 %.1f p25 %.1f median %.1f p75 %.1f p90 %.1f' % tuple(gs[int(q * len(gs))] for q in (0.1, 0.25, 0.5, 0.75, 0.9)))
ts = sorted(v[0] for v in base.values()); P('  tau at entry (s): p10 %.1f p25 %.1f median %.1f p75 %.1f p90 %.1f' % tuple(ts[int(q * len(ts))] for q in (0.1, 0.25, 0.5, 0.75, 0.9)))
P('  entries with tau > 60: %d (lost %d); tau <= 60: %d (lost %d)' % (sum(1 for v in base.values() if v[0] > 60), sum(1 for v in base.values() if v[0] > 60 and v[3]), sum(1 for v in base.values() if v[0] <= 60), sum(1 for v in base.values() if v[0] <= 60 and v[3])))
P('  losses (tau, cushion bps, R bps, pf, bucket): ' + '; '.join('%.1f s, %.1f, %.1f, %.4f, %s' % (v[0], v[1], v[2], v[4], v[5]) for v in base.values() if v[3]))
P('  baseline entries by cushion bin: ' + ', '.join('%s: %d (lost %d)' % (rn, sum(1 for v in base.values() if lo <= v[1] < hi), sum(1 for v in base.values() if lo <= v[1] < hi and v[3])) for rn, lo, hi in RB))
P('  baseline entries with tau > 60 by cushion bin: ' + ', '.join('%s: %d (lost %d)' % (rn, sum(1 for v in base.values() if v[0] > 60 and lo <= v[1] < hi), sum(1 for v in base.values() if v[0] > 60 and lo <= v[1] < hi and v[3])) for rn, lo, hi in RB))
open(args[i2 + 1], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
