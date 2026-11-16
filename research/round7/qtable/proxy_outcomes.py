"""Proxy-defined settlement outcome for each window of the usdc replay records: the mean of the 60 one-second closes at close-59..close (incl alignment)
of the same proxy series the replay engine consumed, versus the strike (ties UP). Writes ticker -> {proxyMean, proxyTruth, officialTruth, strike}.
usage: python3 -I proxy_outcomes.py <sec dir> <out.json> <records...>"""
import sys, json, datetime as dt, numpy as np, os
secdir, outp = sys.argv[1:3]; recs = sys.argv[3:]
cache = {}
def day(d):
    if d not in cache:
        p = os.path.join(secdir, d + '.f64'); cache[d] = np.fromfile(p, dtype='<f8') if os.path.exists(p) else None
    return cache[d]
out = {}
for f in recs:
    for l in open(f):
        if not l.strip(): continue
        r = json.loads(l); ct = r.get('closeTs')
        if not ct or not r.get('strike'): continue
        t0 = ct - 59; vals = []
        for t in range(t0, ct + 1):
            d = dt.datetime.fromtimestamp(t, dt.timezone.utc); a = day(d.strftime('%Y-%m-%d'))
            if a is None: vals = None; break
            v = a[d.hour * 3600 + d.minute * 60 + d.second]
            if not np.isfinite(v) or v <= 0: vals = None; break
            vals.append(v)
        if vals is None: continue
        m = float(np.mean(vals)); out[r['ticker']] = {'proxyMean': m, 'proxyTruth': 'UP' if m >= r['strike'] else 'DOWN', 'officialTruth': r.get('truth'), 'strike': r['strike'], 'official': r.get('official')}
json.dump(out, open(outp, 'w'))
n = len(out); agree = sum(1 for v in out.values() if v['officialTruth'] == v['proxyTruth'])
print('windows', n, 'proxy outcome agrees with the official settlement in', agree, '(%.2f%%)' % (100 * agree / n))
