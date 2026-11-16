import re, sys, math, collections, json
RX = re.compile(r'\[window\] (KXBTC15M-\S+) close=(\S+) .*?coverage=(\w+) (\d+)/300s.*?primary\(pinradar-primary-v1\) (new-crossing|existing-lock|unknown-prior) at (\S+) tau=([\d.]+)s (UP|DOWN) pFlip=([\d.e-]+) (PROVEN LOCKED|LOCKED)(.*?)\| later: lostLocked=(\S+) pFlip>0.2%=(\S+) warning=(\S+) directionFlip=(\S+) observedToClose=(\S+) \| settlement=(yes|no|unknown)')
CUT = '2026-11-16T07:00:00Z'
files = sys.argv[1:]
live = {}; skipped = collections.Counter(); seen = collections.defaultdict(list)
for f in files:
    for line in open(f):
        if '[window]' not in line: continue
        m0 = re.search(r'\[window\] (KXBTC15M-\S+) close=(\S+)', line)
        if m0: seen[m0.group(1)].append(line.strip()[:400])
        if 'primary=NONE' in line: skipped['NONE'] += 1; continue
        if 'primary=NOT DETERMINABLE' in line: skipped['ND'] += 1; continue
        m = RX.search(line)
        if not m: skipped['unparsed'] += 1; continue
        tk = m.group(1)
        if tk in live: skipped['repeat'] += 1; continue
        truth = 'UP' if m.group(17) == 'yes' else 'DOWN' if m.group(17) == 'no' else None
        live[tk] = dict(tk=tk, close=m.group(2), type=m.group(5), tau=float(m.group(7)), side=m.group(8), pf=float(m.group(9)), truth=truth, wrong=('signal WRONG' in line))
print('repeated tickers (first 400 chars of each occurrence):')
for tk, ls in seen.items():
    if len(ls) > 1:
        for x in ls: print('   ', x[:230])
L = [r for r in live.values() if r['close'] <= CUT]
print('entries with close <= %s: %d, skipped %s' % (CUT, len(L), dict(skipped)))
losses = [r for r in L if r['truth'] and r['side'] != r['truth']]
print('losses', len(losses), 'truth None', sum(1 for r in L if r['truth'] is None))
def pois_ge(k, lam): return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))
def pois_ci(k, conf=0.95):
    from math import lgamma, exp, log
    def cdf(x, lam): return sum(exp(-lam + i * log(lam) - lgamma(i + 1)) for i in range(x + 1))
    a = (1 - conf) / 2; lo = 0.0
    if k > 0:
        l, h = 0.0, k + 1.0
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
for name, sel in (('all', lambda r: True), ('[90,120]', lambda r: 90 <= r['tau'] <= 120), ('tau<90', lambda r: r['tau'] < 90), ('[90,119.99]', lambda r: 90 <= r['tau'] < 120)):
    S = [r for r in L if sel(r)]; E = sum(r['pf'] for r in S); O = sum(1 for r in S if r['truth'] and r['side'] != r['truth'])
    lo, hi = pois_ci(O)
    print('%-14s n=%4d  sum pFlip E=%.3f (mean %.5f)  O=%d  O/E=%.2f  P(>=O|E)=%.3f  exact 95%% CI for O [%.2f, %.2f] -> O/E [%.2f, %.2f]' % (name, len(S), E, E / len(S), O, O / E, pois_ge(O, E), lo, hi, lo / E, hi / E))
S = [r for r in L if 90 <= r['tau'] <= 120]
print('[90,120] by period: Nov 2-12 n=%d lost=%d | Nov 13-16 n=%d lost=%d | Nov 12-16 n=%d lost=%d' % (sum(1 for r in S if r['close'] < '2026-11-13'), sum(1 for r in S if r['close'] < '2026-11-13' and r['side'] != r['truth']), sum(1 for r in S if r['close'] >= '2026-11-13'), sum(1 for r in S if r['close'] >= '2026-11-13' and r['side'] != r['truth']), sum(1 for r in S if r['close'] >= '2026-11-12'), sum(1 for r in S if r['close'] >= '2026-11-12' and r['side'] != r['truth'])))
pfs = sorted(r['pf'] for r in S); print('[90,120] pf at entry: median %.5f p10 %.5f p90 %.5f; share with pf >= 0.0018: %.2f' % (pfs[len(pfs)//2], pfs[len(pfs)//10], pfs[9*len(pfs)//10], sum(1 for p in pfs if p >= 0.0018) / len(pfs)))
# after the cut-off (discriminator data, reported as N and K only)
A = [r for r in live.values() if r['close'] > CUT and 90 <= r['tau'] <= 120]
print('after cut-off (discriminator population so far): N=%d K=%d (latest close %s)' % (len(A), sum(1 for r in A if r['truth'] and r['side'] != r['truth']), max(r['close'] for r in A) if A else None))
