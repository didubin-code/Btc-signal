import re, sys, math, collections, json
RX = re.compile(r'\[window\] (KXBTC15M-\S+) close=(\S+) .*?coverage=(\w+) (\d+)/300s.*?primary\(pinradar-primary-v1\) (new-crossing|existing-lock|unknown-prior) at (\S+) tau=([\d.]+)s (UP|DOWN) pFlip=([\d.e-]+) (PROVEN LOCKED|LOCKED)(.*?)\| later: lostLocked=(\S+) pFlip>0.2%=(\S+) warning=(\S+) directionFlip=(\S+) observedToClose=(\S+) \| settlement=(yes|no|unknown)')
files = sys.argv[1:]
live = {}; per_file = collections.defaultdict(set); skipped = collections.Counter(); allwin = collections.Counter()
for f in files:
    for line in open(f):
        if '[window]' not in line: continue
        m0 = re.search(r'\[window\] (KXBTC15M-\S+)', line); tk0 = m0.group(1) if m0 else None
        allwin[tk0] += 1; per_file[f].add(tk0)
        if 'primary=NONE' in line: skipped['NONE'] += 1; continue
        if 'primary=NOT DETERMINABLE' in line: skipped['ND'] += 1; continue
        m = RX.search(line)
        if not m: skipped['unparsed'] += 1; continue
        tk = m.group(1)
        if tk in live: skipped['repeat'] += 1; continue
        truth = 'UP' if m.group(17) == 'yes' else 'DOWN' if m.group(17) == 'no' else None
        live[tk] = dict(tk=tk, close=m.group(2), type=m.group(5), tau=float(m.group(7)), side=m.group(8), pf=float(m.group(9)), truth=truth, wrong=('signal WRONG' in line))
inboth = set.intersection(*per_file.values()) if len(per_file) > 1 else set()
print('files', {f.split('/')[-1]: len(s) for f, s in per_file.items()}, 'window lines total', sum(allwin.values()), 'distinct tickers', len(allwin), 'tickers appearing in both files', len(inboth), 'tickers repeated', sum(1 for v in allwin.values() if v > 1))
L = list(live.values())
print('entries', len(L), 'skipped', dict(skipped), 'closes', min(r['close'] for r in L), max(r['close'] for r in L))
print('truth None among entries:', sum(1 for r in L if r['truth'] is None))
losses = [r for r in L if r['truth'] and r['side'] != r['truth']]
print('losses', len(losses), [(r['tk'], r['close'], r['tau'], r['pf'], r['type']) for r in losses], 'signal WRONG flags', sum(1 for r in L if r['wrong']))
def pois_ge(k, lam): return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))
def pois_ci(k, conf=0.95):
    # exact Poisson CI via chi-square relation, by bisection
    from math import lgamma, exp, log
    def cdf(x, lam): return sum(exp(-lam + i * log(lam) - lgamma(i + 1)) for i in range(x + 1))
    a = (1 - conf) / 2
    lo = 0.0
    if k > 0:
        l, h = 0.0, k * 1.0 + 1
        for _ in range(100):
            mid = (l + h) / 2
            if 1 - cdf(k - 1, mid) < a: l = mid
            else: h = mid
        lo = (l + h) / 2
    l, h = k * 1.0, k + 50.0
    for _ in range(100):
        mid = (l + h) / 2
        if cdf(k, mid) > a: l = mid
        else: h = mid
    return lo, (l + h) / 2
for name, sel in (('all', lambda r: True), ('[90,120]', lambda r: 90 <= r['tau'] <= 120), ('tau<90', lambda r: r['tau'] < 90), ('[90,119.99]', lambda r: 90 <= r['tau'] < 120), ('tau==120 bucket (>=119.5)', lambda r: r['tau'] >= 119.5)):
    S = [r for r in L if sel(r)]; E = sum(r['pf'] for r in S); O = sum(1 for r in S if r['truth'] and r['side'] != r['truth'])
    lo, hi = pois_ci(O)
    print('%-28s n=%4d  sum pFlip E=%.3f  O=%d  O/E=%.2f  P(>=O|E)=%.3f  exact 95%% CI for O [%.2f, %.2f] -> O/E [%.2f, %.2f]  entry types %s' % (name, len(S), E, O, O / E if E else float('nan'), pois_ge(O, E), lo, hi, lo / E, hi / E, dict(collections.Counter(r['type'] for r in S))))
# cushion-known subset: Nov 12-16 [90,120]
S = [r for r in L if 90 <= r['tau'] <= 120 and r['close'] >= '2026-11-12T00:00:00Z']
print('[90,120] closes >= Nov 12: n=%d losses=%d' % (len(S), sum(1 for r in S if r['truth'] and r['side'] != r['truth'])))
S = [r for r in L if 90 <= r['tau'] <= 120 and r['close'] >= '2026-11-13T00:00:00Z']
print('[90,120] closes >= Nov 13: n=%d losses=%d' % (len(S), sum(1 for r in S if r['truth'] and r['side'] != r['truth'])))
# entries per day at [90,120]
days = collections.Counter(r['close'][:10] for r in L if 90 <= r['tau'] <= 120)
print('[90,120] entries per day:', sorted(days.items()))
json.dump(L, open(sys.argv[0].replace('live_check.py', 'live_entries.json'), 'w'))
