"""Entries and losses by seconds-left bin from replay outputs (records ndjson + trace), exact rule (first row 0<tau<=120, LOCKED/PROVEN,
pf<=0.002) and displayed rule (pf<0.0025). Same method for the scaled run and the unscaled chunks. usage: python3 -I eval_scaled.py <label> <records.ndjson>... -- <trace.ndjson or .gz>..."""
import sys, json, gzip, math, collections
args = sys.argv[1:]; label = args[0]; i = args.index('--'); recs_f = args[1:i]; traces_f = args[i + 1:]
win = {}
for f in recs_f:
    for l in open(f):
        if not l.strip(): continue
        r = json.loads(l); win[r['ticker']] = r
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
first = {'exact': {}, 'disp': {}}
def opener(f): return gzip.open(f, 'rt') if f.endswith('.gz') else open(f)
for f in traces_f:
    with opener(f) as fh:
        for l in fh:
            r = json.loads(l); tk = r['tk']
            if tk not in win or not (0 < r['tau'] <= 120) or r.get('pf') is None or not isL(r.get('st')): continue
            for rule, cond in (('exact', r['pf'] <= 0.002), ('disp', r['pf'] < 0.0025)):
                if cond and (tk not in first[rule] or r['tau'] > first[rule][tk]['tau']): first[rule][tk] = r
def cp_upper(k, n):
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k + 1))
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
print('%s: windows %d (closes %s .. %s)' % (label, len(win), min(w['closeTs'] for w in win.values()), max(w['closeTs'] for w in win.values())))
for rule in ('exact', 'disp'):
    E = first[rule]; print('  rule %s: entries %d, losses %d' % (rule, len(E), sum(1 for tk, r in E.items() if r['side'] != win[tk]['truth'])))
    for lab, lo, hi in [('0-29.99', 0, 29.999), ('30-59.99', 30, 59.999), ('60-89.99', 60, 89.999), ('90-120', 90, 120)]:
        B = [(tk, r) for tk, r in E.items() if lo <= r['tau'] <= hi]; k = sum(1 for tk, r in B if r['side'] != win[tk]['truth'])
        cush = sorted(abs(r['gap'] + (r.get('mu') or 0)) / win[tk]['strike'] * 1e4 for tk, r in B)
        print('    tau %-9s n=%5d lost=%2d rate=%.3f%% upper95=%.3f%% | cushion bps median %.1f p10 %.1f | losses: %s' % (lab, len(B), k, 100 * k / max(1, len(B)), 100 * cp_upper(k, len(B)) if B else float('nan'), cush[len(cush) // 2] if cush else float('nan'), cush[len(cush) // 10] if cush else float('nan'),
              ', '.join('%s tau %.2f pf %.4f cushion %.1f bps bk %s' % (tk[-14:], r['tau'], r['pf'], abs(r['gap'] + (r.get('mu') or 0)) / win[tk]['strike'] * 1e4, r['bk']) for tk, r in B if r['side'] != win[tk]['truth'])))
