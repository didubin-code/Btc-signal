"""Full-year comparable cohort: exact-rule entries and losses by bin, by period (before Sep 1 / Sep 1 - Nov 12), by cushion at [90,120],
plus the unscaled chunks on the same windows. usage: python3 -I year_eval.py <scaled records> <scaled trace> <out_full_mu dir> <out.txt>"""
import sys, json, gzip, glob, math
recs_f, trace_f, D, outp = sys.argv[1:5]
win = {json.loads(l)['ticker']: json.loads(l) for l in open(recs_f) if l.strip()}
SPLIT = 1788220800; isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
def firsts(files, thr):
    first = {}
    for f in files:
        op = gzip.open(f, 'rt') if f.endswith('.gz') else open(f)
        for l in op:
            r = json.loads(l); tk = r['tk']
            if tk not in win or not (0 < r['tau'] <= 120) or r.get('pf') is None or not isL(r.get('st')) or r['pf'] > thr: continue
            if tk not in first or r['tau'] > first[tk]['tau']: first[tk] = r
    return first
def cp_upper(k, n):
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k + 1))
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
def cp_lower(k, n):
    if k == 0: return 0.0
    lo, hi = 0.0, 1.0
    def sf(p): return 1 - sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k))
    for _ in range(60):
        mid = (lo + hi) / 2
        if sf(mid) < 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
out = []; P = out.append
cush = lambda tk, r: abs(r['gap'] + (r.get('mu') or 0)) / win[tk]['strike'] * 1e4
def table(name, E, periods=True):
    P('%s: entries %d, losses %d' % (name, len(E), sum(1 for tk, r in E.items() if r['side'] != win[tk]['truth'])))
    for lab, lo, hi in [('0-29.99', 0, 29.999), ('30-59.99', 30, 59.999), ('60-89.99', 60, 89.999), ('90-120', 90, 120)]:
        B = [(tk, r) for tk, r in E.items() if lo <= r['tau'] <= hi]; k = sum(1 for tk, r in B if r['side'] != win[tk]['truth'])
        P('   tau %-9s n=%5d lost=%2d rate=%.3f%% [95%% %.3f-%.3f%%]' % (lab, len(B), k, 100 * k / max(1, len(B)), 100 * cp_lower(k, len(B)) if B else 0, 100 * cp_upper(k, len(B)) if B else float('nan')))
    B90 = [(tk, r) for tk, r in E.items() if 90 <= r['tau'] <= 120]
    if periods:
        for lab, cond in (('before Sep 1', lambda tk: win[tk]['closeTs'] < SPLIT), ('Sep 1 - Nov 12', lambda tk: win[tk]['closeTs'] >= SPLIT)):
            B = [(tk, r) for tk, r in B90 if cond(tk)]; k = sum(1 for tk, r in B if r['side'] != win[tk]['truth'])
            P('   [90,120] %-14s n=%5d lost=%2d rate=%.3f%% [95%% %.3f-%.3f%%]' % (lab, len(B), k, 100 * k / max(1, len(B)), 100 * cp_lower(k, len(B)) if B else 0, 100 * cp_upper(k, len(B)) if B else float('nan')))
    for lab, lo, hi in [('<10 bps', 0, 10), ('10-15', 10, 15), ('15-20', 15, 20), ('20-30', 20, 30), ('>=30', 30, 1e9), ('>=15 (live-like)', 15, 1e9)]:
        B = [(tk, r) for tk, r in B90 if lo <= cush(tk, r) < hi]; k = sum(1 for tk, r in B if r['side'] != win[tk]['truth'])
        P('   [90,120] cushion %-16s n=%5d lost=%2d rate=%.3f%% [95%% %.3f-%.3f%%]' % (lab, len(B), k, 100 * k / max(1, len(B)), 100 * cp_lower(k, len(B)) if B else 0, 100 * cp_upper(k, len(B)) if B else float('nan')))
    L = [(tk, r) for tk, r in B90 if r['side'] != win[tk]['truth']]
    P('   [90,120] losses: ' + '; '.join('%s close %s tau %.2f pf %.4f cushion %.1f bps bk %s' % (tk[-14:], win[tk].get('closeUTC', win[tk]['closeTs']), r['tau'], r['pf'], cush(tk, r), r['bk']) for tk, r in L))
    return E
P('FULL-YEAR COMPARABLE COHORT (LIVE_VOL_SCALE 0.866; %d windows, closes %s .. %s)' % (len(win), min(w['closeTs'] for w in win.values()), max(w['closeTs'] for w in win.values())))
S = table('SCALED exact rule', firsts([trace_f], 0.002))
P(''); U = table('UNSCALED exact rule, same windows (chunks usdc_01-11)', firsts(sorted(glob.glob(D + '/usdc_*.trace.ndjson.gz')), 0.002))
P(''); T = table('UNSCALED threshold-equivalent (pf <= 0.0031), same windows', firsts(sorted(glob.glob(D + '/usdc_*.trace.ndjson.gz')), 0.0031), periods=False)
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
