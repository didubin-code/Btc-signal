import json, sys, math, collections, random, bisect
fx = sys.argv[1]
rows = []; dup = collections.Counter()
for l in open(fx):
    r = json.loads(l)
    if r['family'] != 'usdc' or not r['in_dedup']: continue
    dup[r['ticker']] += 1; rows.append((r['closeUTC'], r['tau'], r['side'] != r['truth'], r['pf'], r['truth'] in ('UP', 'DOWN')))
print('usdc dedup rows', len(rows), 'repeated tickers', sum(1 for v in dup.values() if v > 1), 'truth missing', sum(1 for r in rows if not r[4]))
print('entries', len(rows), 'losses', sum(r[2] for r in rows), 'sum pf %.2f' % sum(r[3] for r in rows), 'O/E %.3f' % (sum(r[2] for r in rows) / sum(r[3] for r in rows)))
BINS = [(0, 29.999), (30, 59.999), (60, 89.999), (90, 120.0)]
def binof(t): return next(i for i, (lo, hi) in enumerate(BINS) if lo <= t <= hi)
cuts = ['2026-%02d-01' % m for m in range(2, 12)]
# cells: (month index 0..9 => period index by cut, bin)
def cutidx(c):  # number of cuts <= close date -> 0..10
    return bisect.bisect_right(cuts, c[:10])
N = len(rows); cells = [(cutidx(c), binof(t)) for c, t, _, _, _ in rows]
ncell = collections.Counter(cells); kcell = collections.Counter(cl for cl, r in zip(cells, rows) if r[2])
def pois_ge(k, lam): return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k)) if k > 0 else 1.0
def split_p(nc, kc, ci, bins):
    nA = sum(v for (c, b), v in nc.items() if c < ci and b in bins); kA = sum(v for (c, b), v in kc.items() if c < ci and b in bins)
    nB = sum(v for (c, b), v in nc.items() if c >= ci and b in bins); kB = sum(v for (c, b), v in kc.items() if c >= ci and b in bins)
    if nA == 0 or nB == 0: return 1.0, (nA, kA, nB, kB)
    return pois_ge(kB, nB * kA / nA), (nA, kA, nB, kB)
ALL = {0, 1, 2, 3}
print('Sep 1 split (cut index 8): all bins', split_p(ncell, kcell, 8, ALL), '| 30-89 s', split_p(ncell, kcell, 8, {1, 2}), '| <30', split_p(ncell, kcell, 8, {0}), '| [90,120]', split_p(ncell, kcell, 8, {3}))
print('scan of month-boundary cuts, all bins / 30-89 s:')
for ci, cut in enumerate(cuts, start=1):
    a = split_p(ncell, kcell, ci, ALL); b = split_p(ncell, kcell, ci, {1, 2})
    print('   cut %s all P=%.4f %s | 30-89 P=%.4f %s' % (cut, a[0], a[1], b[0], b[1]))
def stat_all(kc): return min(split_p(ncell, kc, ci, ALL)[0] for ci in range(1, 11))
def stat_bins(kc): return min(split_p(ncell, kc, ci, bins)[0] for ci in range(1, 11) for bins in (ALL, {0}, {1}, {2}, {3}, {1, 2}))
obs_sep = split_p(ncell, kcell, 8, ALL)[0]; obs_all = stat_all(kcell); obs_bins = stat_bins(kcell); obs_3089 = split_p(ncell, kcell, 8, {1, 2})[0]
K = sum(r[2] for r in rows); random.seed(11); NP = 20000; c_sep = c_all = c_bins = c_3089 = 0
cum = []; s = 0
for cl in cells: cum.append(cl)
for _ in range(NP):
    idx = random.sample(range(N), K); kc = collections.Counter(cells[i] for i in idx)
    if split_p(ncell, kc, 8, ALL)[0] <= obs_sep: c_sep += 1
    if stat_all(kc) <= obs_all: c_all += 1
    if stat_bins(kc) <= obs_bins: c_bins += 1
    if split_p(ncell, kc, 8, {1, 2})[0] <= obs_3089: c_3089 += 1
print('observed: Sep-1 all-bins P=%.4f (perm %.3f) | min over 10 cuts P=%.4f (perm %.3f) | Sep-1 30-89 s P=%.4f (perm %.3f) | min over cuts x {all,4 bins,30-89} P=%.4f (perm %.3f)' % (obs_sep, c_sep / NP, obs_all, c_all / NP, obs_3089, c_3089 / NP, obs_bins, c_bins / NP))
