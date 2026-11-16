import json, sys, math, collections, random, datetime as dt
fx = sys.argv[1]
rows = []; dup = collections.Counter(); fam = collections.Counter(); nodedup = 0
for l in open(fx):
    r = json.loads(l); fam[(r['family'], r['in_dedup'])] += 1
    if r['family'] != 'usdc' or not r['in_dedup']: continue
    dup[r['ticker']] += 1; rows.append(r)
print('family/in_dedup counts', dict(fam), '| usdc dedup rows', len(rows), 'distinct tickers', len(dup), 'repeated tickers', sum(1 for v in dup.values() if v > 1))
print('truth None:', sum(1 for r in rows if r.get('truth') not in ('UP', 'DOWN')), 'closes', min(r['closeUTC'] for r in rows), max(r['closeUTC'] for r in rows))
for r in rows: r['lost'] = r['side'] != r['truth']
print('entries', len(rows), 'losses', sum(r['lost'] for r in rows), 'sum pf', round(sum(r['pf'] for r in rows), 2), 'O/E', round(sum(r['lost'] for r in rows) / sum(r['pf'] for r in rows), 3))
BINS = [('0-29.99', 0, 29.999), ('30-59.99', 30, 59.999), ('60-89.99', 60, 89.999), ('90-120', 90, 120.0), ('30-89', 30, 89.999)]
def pois_ge(k, lam): return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k)) if k > 0 else 1.0
def split_p(rows, cut):
    A = [r for r in rows if r['closeUTC'] < cut]; B = [r for r in rows if r['closeUTC'] >= cut]
    if not A or not B: return None
    ka, kb = sum(r['lost'] for r in A), sum(r['lost'] for r in B)
    lam = len(B) * ka / len(A)
    return pois_ge(kb, lam), len(A), ka, len(B), kb
print('Sep 1 split, all bins:', split_p(rows, '2026-09-01'))
for lab, lo, hi in BINS:
    print('  Sep 1 split, bin', lab, split_p([r for r in rows if lo <= r['tau'] <= hi], '2026-09-01'))
# scan over month boundaries (Feb..Nov) for all bins and each bin
cuts = ['2026-%02d-01' % m for m in range(2, 12)]
print('scan over month-boundary splits (one-sided P that the later period has more losses at the earlier rate):')
for cut in cuts:
    s = split_p(rows, cut); s3 = split_p([r for r in rows if 30 <= r['tau'] <= 89.999], cut)
    print('  cut %s all-bins P=%.3f (%d/%d vs %d/%d) | 30-89 s P=%.3f (%d/%d vs %d/%d)' % (cut, s[0], s[2], s[1], s[4], s[3], s3[0], s3[2], s3[1], s3[4], s3[3]))
# permutation: shuffle loss labels among entries (preserving dates/bins), min over the 10 cuts
random.seed(7)
def minp(rows_, bins=False):
    best = 1.0
    for cut in cuts:
        s = split_p(rows_, cut)
        if s: best = min(best, s[0])
    return best
obs_all = minp(rows); obs_sep = split_p(rows, '2026-09-01')[0]
labels = [r['lost'] for r in rows]; NP = 4000; cnt_min = 0; cnt_sep = 0
# per-bin scan: min over cuts x bins (4 bins) for the bin-specific claim
def minp_bins(rows_):
    best = 1.0
    for lab, lo, hi in BINS[:4]:
        sub = [r for r in rows_ if lo <= r['tau'] <= hi]
        best = min(best, minp(sub))
    return best
obs_bins = minp_bins(rows); cnt_bins = 0
for i in range(NP):
    random.shuffle(labels)
    for r, l in zip(rows, labels): r['lost'] = l
    if minp(rows) <= obs_all: cnt_min += 1
    if split_p(rows, '2026-09-01')[0] <= obs_sep: cnt_sep += 1
    if minp_bins(rows) <= obs_bins: cnt_bins += 1
print('observed: Sep-1 all-bins P=%.4f; min over 10 month cuts P=%.4f; min over cuts x 4 bins P=%.4f' % (obs_sep, obs_all, obs_bins))
print('permutation (%d shuffles of loss labels over entries): P(Sep-1 P <= obs)=%.3f | P(min-over-cuts <= obs)=%.3f | P(min over cuts x bins <= obs)=%.3f' % (NP, cnt_sep / NP, cnt_min / NP, cnt_bins / NP))
