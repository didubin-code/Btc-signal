"""Period 2 (own_capture_2 ring, Nov 13 22:46 - Nov 14 00:29): ring-based 120-s and 900-s RMS (server formula) vs fit-type, separately;
ring/fit-type 1-s RMS over the whole cycle vs the final 300 s; by position in the 15-min cycle."""
import json, math, bisect, glob, collections
import numpy as np
SP = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
PT = SP + '/incident_20261114T0015Z/public_trades/'
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
def rms(x): x = np.asarray(x, float); return math.sqrt(np.mean(x * x)) if len(x) else float('nan')
def load_trades(p):
    T = []; Pp = []
    for l in open(p):
        if l.strip(): o = json.loads(l); T.append(o['t']); Pp.append(o['p'])
    return T, Pp
def last_series(T, Pp, t0, t1, stale=30.0):
    o = {}
    for s in range(t0, t1):
        i = bisect.bisect_left(T, s + 1) - 1
        o[s] = Pp[i] if i >= 0 and (s + 1) - T[i] <= stale else None
    return o
Tc, Pc = load_trades(PT + 'cb_20261113T2244_0036.ndjson'); Tk, Pk = load_trades(PT + 'kr_20261113T2244_0036.ndjson')
t0 = int(min(Tc[0], Tk[0])) + 1; t1 = int(max(Tc[-1], Tk[-1]))
cbs, krs = last_series(Tc, Pc, t0, t1), last_series(Tk, Pk, t0, t1); fit = {}
for s in range(t0, t1):
    a, b = cbs[s], krs[s]
    if a is not None and b is not None: fit[s] = (a + 0.8 * b) / 1.8
    elif a is not None: fit[s] = a
    elif b is not None: fit[s] = b
ring = []; d = {}
for l in open(SP + '/incident_20261114T0015Z/own_capture_2/tape_since_boot.ndjson'):
    try: o = json.loads(l)
    except Exception: continue
    if o.get('k') == 's': ring.append((o['t'], o['v']))
    elif o.get('k') == 'd': d.setdefault(o['ts'] // 1000, o)
ring = sorted(set(ring)); ts_ring = [p[0] for p in ring]
def ringRmsVol(L, now, rg):
    cut = now - L * 1000 - 500; s2 = 0.0; n = 0; prev = None
    for p in rg:
        if p[0] < cut: prev = p; continue
        if prev and prev[1] > 0 and p[0] > prev[0]:
            dtt = max(0.25, (p[0] - prev[0]) / 1000.0); r = (p[1] - prev[1]) / prev[1] * 1e4 / math.sqrt(dtt)
            if prev[0] >= cut: s2 += r * r; n += 1
        prev = p
    return (math.sqrt(s2 / n), n) if n >= max(5, L // 3) else (None, n)
def rms_vol(series, end, Lw):
    s2 = n = 0
    for s in range(end - Lw + 1, end + 1):
        a, b = series.get(s - 1), series.get(s)
        if a and b: s2 += ((b - a) / a * 1e4) ** 2; n += 1
    return (math.sqrt(s2 / n), n) if n >= max(5, Lw // 3) else (None, n)
r120 = []; r900 = []; rcomb = []
for s, o in sorted(d.items()):
    now = o['ts']
    if now - ts_ring[0] < 905 * 1000 or s < t0 + 901: continue
    i = bisect.bisect_right(ts_ring, now); sub = ring[max(0, i - 1000):i]
    v120, _ = ringRmsVol(120, now, sub); v900, _ = ringRmsVol(900, now, sub)
    end = s - 1; f120, _ = rms_vol(fit, end, 120); f900, _ = rms_vol(fit, end, 900)
    if v120 and v900 and f120 and f900:
        r120.append(v120 / f120); r900.append(v900 / f900); rcomb.append(math.sqrt((v120 ** 2 + v900 ** 2) / 2) / math.sqrt((f120 ** 2 + f900 ** 2) / 2))
print('period 2 rows with full ring history: n=%d | ring120/fit120 median %.3f (p10 %.3f p90 %.3f) | ring900/fit900 median %.3f (p10 %.3f p90 %.3f) | combined median %.3f' % (len(r120), q(r120, .5), q(r120, .1), q(r120, .9), q(r900, .5), q(r900, .1), q(r900, .9), q(rcomb, .5)))
# pooled 1-s RMS ring vs fit over all ring seconds, and by position in the 15-min cycle
rs = {int(t // 1000): v for t, v in ring}
allsec = [s for s in rs if s + 1 in rs and s in fit and s + 1 in fit]
def ratio(ss):
    a = [1e4 * math.log(rs[s + 1] / rs[s]) for s in ss]; b = [1e4 * math.log(fit[s + 1] / fit[s]) for s in ss]
    return rms(a) / rms(b), rms(a), rms(b)
print('pooled ring/fit 1-s RMS over all ring seconds: n=%d ratio %.3f (ring %.3f fit %.3f)' % (len(allsec), *ratio(allsec)))
for lo, hi in ((0, 300), (300, 600), (600, 900)):
    ss = [s for s in allsec if lo <= (s % 900) < hi]
    print('  cycle position %3d-%3d s since open: n=%d ratio %.3f (ring %.3f fit %.3f)' % (lo, hi, len(ss), *ratio(ss)))
# decision-tick composite vs fit on the same final-300-s seconds
comp = {s: o['liveIdx']['value'] for s, o in d.items() if (o.get('liveIdx') or {}).get('value')}
ss = [s for s in comp if s + 1 in comp and s in fit and s + 1 in fit]
a = [1e4 * math.log(comp[s + 1] / comp[s]) for s in ss]; b = [1e4 * math.log(fit[s + 1] / fit[s]) for s in ss]
ss2 = [s for s in ss if s in rs and s + 1 in rs]
c = [1e4 * math.log(rs[s + 1] / rs[s]) for s in ss2]; b2 = [1e4 * math.log(fit[s + 1] / fit[s]) for s in ss2]
print('final-300-s seconds: tick/fit %.3f (n=%d) | ring/fit %.3f (n=%d)' % (rms(a) / rms(b), len(ss), rms(c) / rms(b2), len(ss2)))
# h-scaling ring vs fit over all ring seconds
for h in (1, 2, 5, 30, 60):
    sh = [s for s in rs if s + h in rs and s in fit and s + h in fit]
    a = [1e4 * math.log(rs[s + h] / rs[s]) for s in sh]; b = [1e4 * math.log(fit[s + h] / fit[s]) for s in sh]
    print('  h=%2d ring/fit %.3f (n=%d)' % (h, rms(a) / rms(b), len(sh)))
