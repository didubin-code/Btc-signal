"""Unconditional exceedance table of the settlement-mean move. For every second t of the 1-s close series p (one venue proxy index),
horizon h (seconds to close) and the settlement mean of the prints that remain unknown: for h <= 60 the next h prints, for h > 60 the
60 prints ending at t+h. M(t,h) = mean - p[t] in bps of p[t]. Q(R,h) = P(|M| >= R) over all seconds (both signs pooled; the leader's
adverse side is one of them, so the one-sided probability is ~Q/2; Q is reported two-sided and used as the conservative bound).
Also conditioned on the engine-like volatility bucket at t (sigma = 1.03 * RMS(rms120, rms900) of 1-s log returns, in %/15 min,
bucket edges [0.15,0.22,0.3,0.4,0.55,0.8]) and a 'calm' split by rms120 alone. usage: python3 -I build_q.py <sec dir> <from YYYY-MM-DD> <to (excl)> <out.json>"""
import sys, os, json, datetime as dt, numpy as np
secdir, dfrom, dto, outp = sys.argv[1:5]
H = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 75, 90, 105, 120]
RMAX = 600; EDGES = np.array([0.15, 0.22, 0.3, 0.4, 0.55, 0.8])
d0 = dt.date.fromisoformat(dfrom); d1 = dt.date.fromisoformat(dto)
days = []
d = d0
while d < d1:
    days.append(d); d += dt.timedelta(days=1)
# monthly chunks with a 2-day tail for horizons and the 900-s vol lookback
counts = {}; totals = {}
def key(h, b): return '%d|%s' % (h, b)
for h in H:
    for b in ['all', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'calm', 'notcalm', 'y2023', 'y2024', 'y2025', 'y2026']:
        counts[key(h, b)] = np.zeros(RMAX + 1, dtype=np.int64); totals[key(h, b)] = 0
def load(day):
    p = os.path.join(secdir, day.isoformat() + '.f64')
    return np.fromfile(p, dtype='<f8') if os.path.exists(p) else np.full(86400, np.nan)
i = 0
months = sorted(set((d.year, d.month) for d in days))
calm_edge = None
for (y, m) in months:
    mdays = [d for d in days if (d.year, d.month) == (y, m)]
    prev = mdays[0] - dt.timedelta(days=1)
    arr = np.concatenate([load(prev)[-1000:]] + [load(d) for d in mdays] + [load(mdays[-1] + dt.timedelta(days=1))[:200]])
    off = 1000; n_main = len(mdays) * 86400
    bad = ~np.isfinite(arr) | (arr <= 0)
    pf = arr.copy()
    if bad.any():
        idx = np.where(~bad, np.arange(len(arr)), 0); np.maximum.accumulate(idx, out=idx); pf = arr[idx]
    cbad = np.concatenate([[0], np.cumsum(bad)])
    lr = np.zeros(len(pf)); lr[1:] = np.diff(np.log(pf)) * 1e4
    sq = lr * lr; cs = np.concatenate([[0.0], np.cumsum(sq)])
    def rms(w):
        out = np.full(len(pf), np.nan); out[w:] = np.sqrt((cs[w + 1:] - cs[1:len(pf) - w + 1]) / w); return out
    r120 = rms(120); r900 = rms(900)
    sig = 1.03 * np.sqrt((r120 ** 2 + r900 ** 2) / 2) * 30 / 100   # %/15min
    bucket = np.searchsorted(EDGES, sig, side='right')
    S = np.concatenate([[0.0], np.cumsum(pf)])
    t = np.arange(off, off + n_main)
    for h in H:
        if h <= 60: mean = (S[t + h + 1] - S[t + 1]) / h
        else: mean = (S[t + h + 1] - S[t + h - 59]) / 60
        M = np.abs(mean - pf[t]) / pf[t] * 1e4
        ok = (cbad[t + h + 1] - cbad[t - 900] == 0) & np.isfinite(sig[t])
        Mi = np.minimum(np.floor(M), RMAX).astype(np.int64)
        def acc(name, mask):
            mm = ok & mask
            if mm.any():
                counts[key(h, name)] += np.bincount(Mi[mm], minlength=RMAX + 1); totals[key(h, name)] += int(mm.sum())
        acc('all', np.ones(len(t), bool)); acc('y%d' % y, np.ones(len(t), bool))
        for b in range(7): acc('c%d' % b, bucket[t] == b)
        acc('calm', r120[t] * 30 / 100 * 1.03 < 0.22); acc('notcalm', r120[t] * 30 / 100 * 1.03 >= 0.22)
    print('%04d-%02d done, seconds %d' % (y, m, n_main), flush=True)
# exceedance = reverse cumsum
res = {'H': H, 'RMAX': RMAX, 'from': dfrom, 'to': dto, 'totals': totals, 'exceed': {}}
for k, c in counts.items():
    ex = np.cumsum(c[::-1])[::-1]   # ex[R] = count of |M| >= R (floor)
    res['exceed'][k] = ex.tolist()
json.dump(res, open(outp, 'w'))
print('written', outp)
