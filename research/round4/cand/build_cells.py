"""Empirical settlement-vulnerability cells (candidate PR10 lookup). De-duplicated 2026 replay (usdc feed, real settlements):
for every window and every horizon h in 20,30,...,120 s (trace row at tau = h - 0.75), the leader (sign of gap + mu), its
basis-adjusted cushion in bps, its regime group (bucket 0-1 quiet, 2-3 normal, 4-6 active) and whether the official settlement
went against it. Cells: horizon x regime group x cushion bin (0-2.5, 2.5-5, 5-7.5, ..., 37.5-40, 40-50, 50-75, 75+ bps).
Two tables: FIT (windows closing before 2026-09-01) and TEST (2026-09-01 to 2026-11-12), plus ALL. Rate = (k + 0.5)/(n + 1)
(Jeffreys-style smoothing), with k, n and the exact 95 % upper bound stored. usage: python3 -I build_cells.py <out_full_mu dir> <out.json>"""
import json, sys, gzip, glob, math, collections
D, outp = sys.argv[1], sys.argv[2]
H = list(range(20, 121, 10)); want = {h: h - 0.75 for h in H}
CB = [0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35, 37.5, 40, 50, 75, 1e9]
def cbin(c):
    for lo, hi in zip(CB, CB[1:]):
        if lo <= c < hi: return '%g-%g' % (lo, hi if hi < 1e9 else 999)
    return None
def grp(bk): return 'quiet' if bk <= 1 else 'normal' if bk <= 3 else 'active'
win = {}
for f in sorted(glob.glob(D + '/usdc_*.ndjson')):
    if '.sum.' in f or '.loser.' in f: continue
    for l in open(f):
        r = json.loads(l); win[r['ticker']] = (r['marginUsd'], r['strike'], r['closeTs'])
SPLIT = 1788566400  # 2026-09-01T00:00:00Z
cells = {'FIT': collections.defaultdict(lambda: [0, 0]), 'TEST': collections.defaultdict(lambda: [0, 0]), 'ALL': collections.defaultdict(lambda: [0, 0])}
for f in sorted(glob.glob(D + '/usdc_*.trace.ndjson.gz')):
    with gzip.open(f, 'rt') as fh:
        for l in fh:
            r = json.loads(l); tau = r['tau']
            for h in H:
                if abs(tau - want[h]) < 0.01:
                    w = win.get(r['tk']); 
                    if not w: break
                    m, strike, cts = w; ce = r['gap'] + (r.get('mu') or 0.0)
                    if ce == 0: break
                    sgn = 1 if ce > 0 else -1; c_bps = abs(ce) / strike * 1e4; lost = (sgn * m) < 0
                    key = '%d|%s|%s' % (h, grp(r['bk']), cbin(c_bps))
                    for per in (('FIT' if cts < SPLIT else 'TEST'), 'ALL'):
                        cells[per][key][0] += 1; cells[per][key][1] += int(lost)
                    break
def upper(k, n):
    if n == 0: return 1.0
    if k == n: return 1.0
    def cdf(p):
        return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log(1 - p)) for i in range(k + 1))
    a, b = 1e-12, 1 - 1e-12
    for _ in range(60):
        mid = (a + b) / 2
        if cdf(mid) > 0.025: a = mid
        else: b = mid
    return (a + b) / 2
out = {per: {k: {'n': v[0], 'k': v[1], 'rate': (v[1] + 0.5) / (v[0] + 1), 'upper95': upper(v[1], v[0])} for k, v in cells[per].items()} for per in cells}
out['_meta'] = {'horizons': H, 'cushionEdgesBps': CB[:-1] + ['inf'], 'regimeGroups': 'quiet=bk0-1, normal=bk2-3, active=bk4-6', 'split': '2026-09-01T00:00:00Z', 'rateSmoothing': '(k+0.5)/(n+1)', 'source': 'out_full_mu usdc (de-duplicated real settlements), leader = sign(gap+mu) at tau=h-0.75'}
json.dump(out, open(outp, 'w'))
# print the active-regime slice at h=120,90,60 for a quick look (ALL)
for h in (120, 100, 90, 60):
    row = []
    for lo, hi in zip(CB, CB[1:]):
        key = '%d|active|%s' % (h, '%g-%g' % (lo, hi if hi < 1e9 else 999)); c = out['ALL'].get(key)
        if c: row.append('%g: %d/%d=%.2f%%' % (lo, c['k'], c['n'], 100 * c['rate']))
    print('ALL h=%d active | ' % h + ' | '.join(row))
print('FIT windows', sum(1 for w in win.values() if w[2] < SPLIT), 'TEST windows', sum(1 for w in win.values() if w[2] >= SPLIT))
