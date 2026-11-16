import json, sys, math, collections, random, bisect
from math import lgamma, exp
fx = sys.argv[1]
rows = []
for l in open(fx):
    r = json.loads(l)
    if r['family'] != 'usdc' or not r['in_dedup']: continue
    rows.append((r['closeUTC'], r['tau'], r['side'] != r['truth']))
BINS = [(0, 29.999), (30, 59.999), (60, 89.999), (90, 120.0)]
def binof(t): return next(i for i, (lo, hi) in enumerate(BINS) if lo <= t <= hi)
cuts = ['2026-%02d-01' % m for m in range(2, 12)]
cells = [(bisect.bisect_right(cuts, c[:10]), binof(t)) for c, t, _ in rows]
N = len(rows); ncell = collections.Counter(cells); kcell = collections.Counter(cl for cl, r in zip(cells, rows) if r[2]); K = sum(r[2] for r in rows)
def lchoose(n, k): return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
def hyper_ge(k, n_b, k_a, n_a):
    Kt = k + k_a; Nt = n_a + n_b
    return sum(exp(lchoose(n_b, j) + lchoose(n_a, Kt - j) - lchoose(Nt, Kt)) for j in range(k, min(Kt, n_b) + 1))
def split_p(nc, kc, ci, bins):
    nA = sum(v for (c, b), v in nc.items() if c < ci and b in bins); kA = sum(v for (c, b), v in kc.items() if c < ci and b in bins)
    nB = sum(v for (c, b), v in nc.items() if c >= ci and b in bins); kB = sum(v for (c, b), v in kc.items() if c >= ci and b in bins)
    if nA == 0 or nB == 0 or kA + kB == 0: return 1.0
    return hyper_ge(kB, nB, kA, nA)
ALL = {0, 1, 2, 3}; SETS = (ALL, {0}, {1}, {2}, {3}, {1, 2})
obs_sep = split_p(ncell, kcell, 8, ALL); obs_sep3089 = split_p(ncell, kcell, 8, {1, 2})
obs_minall = min(split_p(ncell, kcell, ci, ALL) for ci in range(1, 11))
obs_minbins = min(split_p(ncell, kcell, ci, s) for ci in range(1, 11) for s in SETS)
obs_min3089 = min(split_p(ncell, kcell, ci, {1, 2}) for ci in range(1, 11))
print('Fisher one-sided P: Sep-1 all bins %.4f | Sep-1 30-89 s %.4f | min over 10 month cuts, all bins %.4f | min over cuts, 30-89 s %.4f | min over cuts x 6 bin-sets %.4f' % (obs_sep, obs_sep3089, obs_minall, obs_min3089, obs_minbins))
for ci, cut in enumerate(cuts, start=1): print('   cut %s all P=%.4f | 30-89 P=%.4f' % (cut, split_p(ncell, kcell, ci, ALL), split_p(ncell, kcell, ci, {1, 2})))
random.seed(5); NP = 20000; c = collections.Counter()
for _ in range(NP):
    idx = random.sample(range(N), K); kc = collections.Counter(cells[i] for i in idx)
    if split_p(ncell, kc, 8, ALL) <= obs_sep: c['sep_all'] += 1
    if split_p(ncell, kc, 8, {1, 2}) <= obs_sep3089: c['sep_3089'] += 1
    if min(split_p(ncell, kc, ci, ALL) for ci in range(1, 11)) <= obs_minall: c['min_all'] += 1
    if min(split_p(ncell, kc, ci, {1, 2}) for ci in range(1, 11)) <= obs_min3089: c['min_3089'] += 1
    if min(split_p(ncell, kc, ci, s) for ci in range(1, 11) for s in SETS) <= obs_minbins: c['min_bins'] += 1
print('permutation (%d random placements of the 28 losses over the 26,229 entries): Sep-1 all-bins %.3f | Sep-1 30-89 s %.3f | scan over 10 cuts (all bins) %.3f | scan over cuts (30-89 s) %.3f | scan over cuts x bin-sets %.3f' % (NP, c['sep_all'] / NP, c['sep_3089'] / NP, c['min_all'] / NP, c['min_3089'] / NP, c['min_bins'] / NP))
