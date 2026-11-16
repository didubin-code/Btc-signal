"""The scale the model consumes vs the scale it is fed. Rebuild the fit-type index (Coinbase 1.0 / Kraken 0.8 last-trade, 1 Hz,
30-s staleness; the construction of incident tools/index_compare.py) from the public trade files, and compare with production's
own composite index (rows: idx, 1 Hz) and the official BRTI spot (rows: spot, ref OFFICIAL, deduplicated when unchanged) on the
same seconds, using (a) the model's own sigma definition (RMS of 1-s returns over 120 s and 900 s, combined as RMS; the fit-type
series is continuous so both windows exist; production's value is the row field sigma / LIVE_VOL_SCALE 1.03, which also carries the
input-age inflation, usually ~1), (b) like-for-like 120-s RMS on the composite where the final 300 s allow it, (c) variance scaling
at 1..30 s. usage: python3 -I fit_scale.py <rows dir> <tape own_capture_2> <out.txt> <cb1> <kr1> <cb2> <kr2>"""
import sys, json, math, bisect, glob, os, collections
import numpy as np
rowsdir, tape, outp, cb1, kr1, cb2, kr2 = sys.argv[1:8]
def load_trades(p):
    T = []; P = []
    for l in open(p):
        if l.strip():
            o = json.loads(l); T.append(o['t']); P.append(o['p'])
    return T, P
def last_series(T, P, t0, t1, stale=30.0):
    out = {}
    for s in range(t0, t1):
        i = bisect.bisect_left(T, s + 1) - 1
        out[s] = P[i] if i >= 0 and (s + 1) - T[i] <= stale else None
    return out
def build_fit(cbf, krf):
    Tc, Pc = load_trades(cbf); Tk, Pk = load_trades(krf)
    t0 = int(min(Tc[0], Tk[0])) + 1; t1 = int(max(Tc[-1], Tk[-1]))
    cbs, krs = last_series(Tc, Pc, t0, t1), last_series(Tk, Pk, t0, t1); fit = {}
    for s in range(t0, t1):
        a, b = cbs[s], krs[s]
        if a is not None and b is not None: fit[s] = (1.0 * a + 0.8 * b) / 1.8
        elif a is not None: fit[s] = a
        elif b is not None: fit[s] = b
    return fit, (t0, t1), len(Tc), len(Tk)
def rms_vol(series, end, Lw):
    s2 = n = 0
    for s in range(end - Lw + 1, end + 1):
        a, b = series.get(s - 1), series.get(s)
        if a and b: s2 += ((b - a) / a * 1e4) ** 2; n += 1
    return (math.sqrt(s2 / n), n) if n >= max(5, Lw // 3) else (None, n)
def sigma_model(series, end):
    a, _ = rms_vol(series, end, 120); b, _ = rms_vol(series, end, 900)
    return (math.sqrt((a * a + b * b) / 2) if a and b else None), a, b
out = []; P = out.append
fit1, rng1, nc1, nk1 = build_fit(cb1, kr1); fit2, rng2, nc2, nk2 = build_fit(cb2, kr2)
P('FIT-TYPE INDEX rebuilt: period 1 %s..%s (%d Coinbase, %d Kraken trades, %d seconds) | period 2 %s..%s (%d, %d, %d seconds)' % (rng1[0], rng1[1], nc1, nk1, len(fit1), rng2[0], rng2[1], nc2, nk2, len(fit2)))
fit = dict(fit1); fit.update(fit2)
# ---- production rows (1 Hz: first row of each second) in the fit periods
comp = {}; spot = {}; rows = []; regime = {}
for f in sorted(glob.glob(rowsdir + '/*.ndjson')):
    for l in open(f):
        if not l.strip(): continue
        r = json.loads(l); s = r['ts'] // 1000
        if not ((rng1[0] <= s < rng1[1]) or (rng2[0] <= s < rng2[1])): continue
        if s in comp: continue
        if r.get('idx'): comp[s] = float(r['idx'])
        if r.get('ref') == 'OFFICIAL' and r.get('spot') and (r.get('brtiAgeMs') or 9e9) < 1500: spot[s] = float(r['spot'])
        rows.append(r)
# own-capture tape rows (period 2) add liveIdx and BRTI prints by source second
for l in open(tape):
    try: o = json.loads(l)
    except Exception: continue
    if o.get('k') != 'd': continue
    s = o['ts'] // 1000; li = (o.get('liveIdx') or {}).get('value')
    if li and s not in comp: comp[s] = float(li)
    b = ((o.get('brti') or {}).get('last') or {})
    if b.get('value') and b.get('sourceTs'): spot.setdefault(int(b['sourceTs'] // 1000), float(b['value']))
# dedupe unchanged consecutive spot values (print not yet arrived): drop a second whose spot equals the previous second's
for s in sorted(spot):
    if s - 1 in spot and spot[s] == spot[s - 1]: del spot[s]
P('production rows in the fit periods: %d; composite seconds %d; official spot seconds (fresh, changed) %d' % (len(rows), len(comp), len(spot)))
# ---- (a) the model's own sigma: production sigma/1.03 vs fit-type sigma(120,900) at the same second
ratios = collections.defaultdict(list); r120 = collections.defaultdict(list)
for r in rows:
    end = r['ts'] // 1000 - 1; sf, f120, f900 = sigma_model(fit, end)
    if sf is None or not r.get('sigma'): continue
    live = float(r['sigma']) / 1.03
    key = ('all',); ratios[key].append(live / sf)
    ratios[('regime', int(r['regime']) if r.get('regime') is not None else -1)].append(live / sf)
    tb = '90-120' if 90 <= r['tau'] <= 120 else '<90' if r['tau'] < 90 else '>120'; ratios[('tau', tb)].append(live / sf)
    # like-for-like 120-s RMS where the composite has 120 s of history in the rows (tau <= 180)
    if r['tau'] <= 180:
        c120, _ = rms_vol(comp, end, 120)
        if c120 and f120: r120[('all',)].append(c120 / f120); r120[('regime', int(r['regime']))].append(c120 / f120)
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
P(''); P('(a) MODEL-DEFINITION SIGMA: production (row sigma / 1.03, includes input-age inflation) divided by the fit-type sigma (RMS of 120-s and 900-s 1-s RMS) at the same second')
for k, v in sorted(ratios.items(), key=lambda kv: str(kv[0])):
    P('   %-18s n=%6d  median %.3f  p10 %.3f  p25 %.3f  p75 %.3f  p90 %.3f' % (str(k), len(v), q(v, .5), q(v, .1), q(v, .25), q(v, .75), q(v, .9)))
P('(b) LIKE-FOR-LIKE 120-s RMS of 1-s returns: composite index (rows) / fit-type index, same seconds, rows with 120 s of composite history')
for k, v in sorted(r120.items(), key=lambda kv: str(kv[0])):
    P('   %-18s n=%6d  median %.3f  p10 %.3f  p90 %.3f' % (str(k), len(v), q(v, .5), q(v, .1), q(v, .9)))
# ---- (c) variance scaling on common seconds
P(''); P('(c) VARIANCE SCALING (RMS of h-s log returns / sqrt h, bps/sqrt s) on seconds where fit-type, composite and official spot all have both endpoints')
common = set(fit) & set(comp) & set(spot)
for h in (1, 2, 3, 5, 10, 20, 30, 60):
    ss = [s for s in common if s + h in common]
    if len(ss) < 500: P('   h=%2d: n=%d (too few)' % (h, len(ss))); continue
    F = np.array([1e4 * math.log(fit[s + h] / fit[s]) for s in ss]); C = np.array([1e4 * math.log(comp[s + h] / comp[s]) for s in ss]); S = np.array([1e4 * math.log(spot[s + h] / spot[s]) for s in ss])
    rm = lambda x: math.sqrt(np.mean(x * x)) / math.sqrt(h)
    P('   h=%2d s  n=%6d | fit-type %.3f | composite %.3f | official %.3f | composite/fit-type %.3f | fit-type/official %.3f | composite/official %.3f' % (h, len(ss), rm(F), rm(C), rm(S), rm(C) / rm(F), rm(F) / rm(S), rm(C) / rm(S)))
# autocorrelation of the fit-type 1-s returns
R = {s: 1e4 * math.log(fit[s + 1] / fit[s]) for s in fit if s + 1 in fit}
x = [R[s] for s in R if s + 1 in R]; y = [R[s + 1] for s in R if s + 1 in R]
P('   fit-type 1-s return lag-1 autocorrelation %+.3f (n=%d); identical consecutive values %.1f %%' % (float(np.corrcoef(x, y)[0, 1]), len(x), 100 * sum(1 for s in fit if s + 1 in fit and fit[s] == fit[s + 1]) / max(1, sum(1 for s in fit if s + 1 in fit))))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
