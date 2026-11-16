"""Period 1 (rows idx = tick composite, rows spot = BRTI, fit-type from trades): same-subset regime comparison, and a VWAP-per-second
construction variant for the fit-type index (sensitivity)."""
import json, math, bisect, glob, collections
import numpy as np
SP = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
PT = SP + '/incident_20261114T0015Z/public_trades/'
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
def rms(x): x = np.asarray(x, float); return math.sqrt(np.mean(x * x)) if len(x) else float('nan')
def load(p):
    T = []; Pp = []; Q = []
    for l in open(p):
        if l.strip(): o = json.loads(l); T.append(o['t']); Pp.append(o['p']); Q.append(o['q'])
    return T, Pp, Q
def last_series(T, Pp, t0, t1, stale=30.0):
    o = {}
    for s in range(t0, t1):
        i = bisect.bisect_left(T, s + 1) - 1
        o[s] = Pp[i] if i >= 0 and (s + 1) - T[i] <= stale else None
    return o
def vwap_series(T, Pp, Q, t0, t1, stale=30.0):
    pv = collections.defaultdict(float); vv = collections.defaultdict(float)
    for t, p, qq in zip(T, Pp, Q): s = int(t); pv[s] += p * qq; vv[s] += qq
    o = {}; last = None; lastt = None
    for s in range(t0, t1):
        if vv.get(s, 0) > 0: last = pv[s] / vv[s]; lastt = s
        o[s] = last if last is not None and lastt is not None and s - lastt <= stale else None
    return o
fit = {}; vw = {}
for cbf, krf in ((PT + 'cb_20261112T2125_1113T2244.ndjson', PT + 'kr_20261112T2125_1113T2244.ndjson'), (PT + 'cb_20261113T2244_0036.ndjson', PT + 'kr_20261113T2244_0036.ndjson')):
    Tc, Pc, Qc = load(cbf); Tk, Pk, Qk = load(krf)
    t0 = int(min(Tc[0], Tk[0])) + 1; t1 = int(max(Tc[-1], Tk[-1]))
    cbs, krs = last_series(Tc, Pc, t0, t1), last_series(Tk, Pk, t0, t1)
    cbv, krv = vwap_series(Tc, Pc, Qc, t0, t1), vwap_series(Tk, Pk, Qk, t0, t1)
    for s in range(t0, t1):
        for src, dst in ((cbs, krs, fit), (cbv, krv, vw)) if False else (((cbs, krs), fit), ((cbv, krv), vw)):
            a, b = src[0][s], src[1][s]
            if a is not None and b is not None: dst[s] = (a + 0.8 * b) / 1.8
            elif a is not None: dst[s] = a
            elif b is not None: dst[s] = b
class Pre:
    def __init__(self, series):
        ks = sorted(series); self.t0 = ks[0]; N = ks[-1] - ks[0] + 2
        s2 = np.zeros(N); c = np.zeros(N)
        for s in ks:
            a = series.get(s - 1); b = series[s]
            if a and b: i = s - self.t0; s2[i] = ((b - a) / a * 1e4) ** 2; c[i] = 1
        self.S = np.concatenate([[0.0], np.cumsum(s2)]); self.C = np.concatenate([[0], np.cumsum(c)]); self.N = N
    def rmsw(self, end, Lw):
        hi = end - self.t0 + 1; lo = max(hi - Lw, 0)
        if hi < 1 or hi > self.N: return None
        n = int(self.C[hi] - self.C[lo]); s2 = self.S[hi] - self.S[lo]
        return math.sqrt(s2 / n) if n >= max(5, Lw // 3) else None
    def sigma(self, end):
        a, b = self.rmsw(end, 120), self.rmsw(end, 900)
        return math.sqrt((a * a + b * b) / 2) if a and b else None
Pf, Pv = Pre(fit), Pre(vw)
rows = []
for f in sorted(glob.glob(SP + '/r30/live/scoreboard/rows/*.ndjson')):
    for l in open(f):
        if l.strip(): rows.append(json.loads(l))
rows.sort(key=lambda r: r['ts']); seen = set(); fr = []
for r in rows:
    s = r['ts'] // 1000
    if s in seen or s not in fit: continue
    seen.add(s); fr.append(r)
ra = []; rv = []
for r in fr:
    end = r['ts'] // 1000 - 1; a = Pf.sigma(end); b = Pv.sigma(end)
    if a and b and r.get('sigma'): ra.append(r['sigma'] / 1.03 / a); rv.append(r['sigma'] / 1.03 / b)
print('VWAP-per-second variant: rows sigma/1.03 / fit-type sigma: last-trade median %.3f | VWAP median %.3f (n=%d)' % (q(ra, .5), q(rv, .5), len(ra)))
# same-subset regime comparison on period-1 seconds: comp = rows idx, brti = rows spot (dedup), fit
comp = {r['ts'] // 1000: r['idx'] for r in fr if r.get('idx')}
spot = {}
for r in fr:
    s = r['ts'] // 1000
    if r.get('ref') == 'OFFICIAL' and r.get('spot') and (r.get('brtiAgeMs') or 9e9) < 1500: spot[s] = float(r['spot'])
for s in sorted(spot):
    if s - 1 in spot and spot[s] == spot[s - 1]: del spot[s]
cm = set(comp) & set(spot) & set(fit)
blocks = collections.defaultdict(list)
for s in cm:
    if s + 1 in cm: blocks[s // 60].append(s)
brms = {b: rms([1e4 * math.log(spot[s + 1] / spot[s]) for s in ss]) for b, ss in blocks.items() if len(ss) >= 40}
cuts = [q(list(brms.values()), 1 / 3), q(list(brms.values()), 2 / 3)]
def ac1(S, ss):
    Rr = {s: 1e4 * math.log(S[s + 1] / S[s]) for s in ss if s + 1 in S and s in S}
    x = [Rr[s] for s in Rr if s + 1 in Rr]; y = [Rr[s + 1] for s in Rr if s + 1 in Rr]
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 100 else float('nan')
print('SAME-SUBSET terciles (period 1 rows; BRTI = rows spot): lag-1 autocorr and RMS ratios at h=1,2,5,30')
for lab, sel in (('calm', lambda b: brms[b] < cuts[0]), ('middle', lambda b: cuts[0] <= brms[b] < cuts[1]), ('active', lambda b: brms[b] >= cuts[1])):
    B = [b for b in brms if sel(b)]; ss = [s for b in B for s in blocks[b]]
    line = 'ac1 brti %+.3f comp %+.3f fit %+.3f' % (ac1(spot, ss), ac1(comp, ss), ac1(fit, ss))
    for h in (1, 2, 5, 30):
        sh = [s for s in ss if s + h in cm]
        c = [1e4 * math.log(comp[s + h] / comp[s]) for s in sh]; b = [1e4 * math.log(spot[s + h] / spot[s]) for s in sh]; f = [1e4 * math.log(fit[s + h] / fit[s]) for s in sh]
        line += ' | h=%2d comp/brti %.3f fit/brti %.3f comp/fit %.3f' % (h, rms(c) / rms(b), rms(f) / rms(b), rms(c) / rms(f))
    print('   %-7s blocks %4d (BRTI 1-s RMS cut %.2f/%.2f) | %s' % (lab, len(B), cuts[0], cuts[1], line))
# by model bucket (rows regime) same subset
reg = {r['ts'] // 1000: r.get('regime') for r in fr}
for grp, name in (((1, 2, 3), 'buckets 1-3'), ((4,), 'bucket 4'), ((5,), 'bucket 5'), ((6,), 'bucket 6')):
    ss = [s for s in cm if reg.get(s) in grp]
    line = []
    for h in (1, 5, 30):
        sh = [s for s in ss if s + h in cm]
        if len(sh) < 300: line.append('h=%d n/a' % h); continue
        c = [1e4 * math.log(comp[s + h] / comp[s]) for s in sh]; b = [1e4 * math.log(spot[s + h] / spot[s]) for s in sh]; f = [1e4 * math.log(fit[s + h] / fit[s]) for s in sh]
        line.append('h=%2d comp/brti %.3f fit/brti %.3f comp/fit %.3f (n=%d)' % (h, rms(c) / rms(b), rms(f) / rms(b), rms(c) / rms(f), len(sh)))
    print('   %-12s | ' % name + ' | '.join(line))
