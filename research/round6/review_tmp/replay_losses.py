import json, collections, math
from math import lgamma, exp
rows = [json.loads(l) for l in open('round4/causal/features_R_exact.ndjson')]
rows = [r for r in rows if r['family'] == 'usdc' and r['in_dedup']]
for r in rows: r['lost'] = r['side'] != r['truth']
L = sorted([r for r in rows if r['lost']], key=lambda r: r['closeUTC'])
print('28 replay losses (close UTC, tau, cushion bps, bk):')
print('  ' + ' | '.join('%s t%.0f c%.1f bk%s' % (r['closeUTC'][5:16], r['tau'], r['cushion_bps'], r['bk']) for r in L))
bymonth = collections.Counter(r['closeUTC'][:7] for r in L); nmonth = collections.Counter(r['closeUTC'][:7] for r in rows)
print('  per month losses/entries: ' + ', '.join('%s %d/%d' % (m, bymonth[m], nmonth[m]) for m in sorted(nmonth)))
byday = collections.Counter(r['closeUTC'][:10] for r in L); print('  days with >1 loss:', {d: c for d, c in byday.items() if c > 1})
def lchoose(n, k): return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
def hyper_ge(k, n_b, k_a, n_a):
    Kt = k + k_a; Nt = n_a + n_b
    return sum(exp(lchoose(n_b, j) + lchoose(n_a, Kt - j) - lchoose(Nt, Kt)) for j in range(k, min(Kt, n_b) + 1))
def seg(lo, hi): S = [r for r in rows if lo <= r['closeUTC'] < hi]; return len(S), sum(r['lost'] for r in S)
a = seg('2026-01', '2026-09'); b = seg('2026-09', '2026-11'); c = seg('2026-11', '2026-12'); d = seg('2026-11-02', '2026-12')
print('  Jan-Aug %d/%d (%.3f%%) | Sep-Oct %d/%d (%.3f%%) Fisher vs Jan-Aug P=%.3f | Nov 1-12 %d/%d (%.3f%%) Fisher vs Jan-Oct P=%.5f | Nov 2-12 %d/%d (%.3f%%) Fisher vs Jan-Nov1 P=%.4f' % (a[0], a[1], 100 * a[1] / a[0], b[0], b[1], 100 * b[1] / b[0], hyper_ge(b[1], b[0], a[1], a[0]), c[0], c[1], 100 * c[1] / c[0], hyper_ge(c[1], c[0], a[1] + b[1], a[0] + b[0]), d[0], d[1], 100 * d[1] / d[0], hyper_ge(d[1], d[0], 28 - d[1], len(rows) - d[0])))
# day-level clustering: losses per day vs Poisson expectation given each day's entries
days = collections.defaultdict(lambda: [0, 0])
for r in rows: days[r['closeUTC'][:10]][0] += 1; days[r['closeUTC'][:10]][1] += r['lost']
p = 28 / len(rows); exp_multi = sum(1 - exp(-n * p) * (1 + n * p) for n, k in days.values()); obs_multi = sum(1 for n, k in days.values() if k >= 2)
print('  days with >=2 losses: observed %d, expected under independence %.2f (over %d days)' % (obs_multi, exp_multi, len(days)))
