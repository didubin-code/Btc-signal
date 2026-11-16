"""Uncertainty of the exceedance at the frozen thresholds, accounting for correlated seconds: per-day exceedance counts at R*(h) for
h in {10, 30, 60, 90, 120} over the threshold history (same construction as build_q_full.py), then a moving-block bootstrap over days
(blocks of 7 days, 2,000 resamples) for the pooled exceedance, and the number of distinct exceedance episodes (runs of consecutive
exceeding seconds) as the effective count of events. usage: python3 -I q_uncertainty.py <sec dir> <from> <to> <rstar.json> <out.txt>"""
import sys, os, json, datetime as dt, numpy as np
secdir, dfrom, dto, rstar_f, outp = sys.argv[1:6]
RS = {int(k): v for k, v in json.load(open(rstar_f))['rstar'].items()}
H = [10, 30, 60, 90, 120]
d0 = dt.date.fromisoformat(dfrom); d1 = dt.date.fromisoformat(dto)
days = []; d = d0
while d < d1: days.append(d); d += dt.timedelta(days=1)
def load(day):
    p = os.path.join(secdir, day.isoformat() + '.f64'); return np.fromfile(p, dtype='<f8') if os.path.exists(p) else np.full(86400, np.nan)
cnt = {h: [] for h in H}; tot = {h: [] for h in H}; episodes = {h: 0 for h in H}; prev_tail = None
months = sorted(set((x.year, x.month) for x in days))
for (y, m) in months:
    mdays = [x for x in days if (x.year, x.month) == (y, m)]
    arr = np.concatenate([load(mdays[0] - dt.timedelta(days=1))[-1000:]] + [load(x) for x in mdays] + [load(mdays[-1] + dt.timedelta(days=1))[:200]])
    off = 1000; bad = ~np.isfinite(arr) | (arr <= 0); pf = arr.copy()
    if bad.any():
        idx = np.where(~bad, np.arange(len(arr)), 0); np.maximum.accumulate(idx, out=idx); pf = arr[idx]
    cbad = np.concatenate([[0], np.cumsum(bad)]); S = np.concatenate([[0.0], np.cumsum(pf)])
    for h in H:
        t = np.arange(off, off + len(mdays) * 86400)
        mean = (S[t + h + 1] - S[t + 1]) / h if h <= 60 else (S[t + h + 1] - S[t + h - 59]) / 60
        M = np.abs(mean - pf[t]) / pf[t] * 1e4; ok = (cbad[t + h + 1] - cbad[t - 900] == 0)
        ex = (M >= RS[h]) & ok
        for i in range(len(mdays)):
            cnt[h].append(int(ex[i * 86400:(i + 1) * 86400].sum())); tot[h].append(int(ok[i * 86400:(i + 1) * 86400].sum()))
        e = ex.astype(np.int8); episodes[h] += int(((e[1:] == 1) & (e[:-1] == 0)).sum() + (1 if e[0] == 1 else 0))
    print('%04d-%02d' % (y, m), flush=True)
rng = np.random.default_rng(20261116); out = []; P = out.append
P('EXCEEDANCE AT THE FROZEN THRESHOLDS: pooled rate, day-block bootstrap (7-day blocks, 2000 resamples) and distinct episodes; history %s..%s, %d days' % (dfrom, dto, len(days)))
for h in H:
    c = np.array(cnt[h]); n = np.array(tot[h]); nd = len(c); B = 7; nb = int(np.ceil(nd / B))
    rates = []
    for _ in range(2000):
        starts = rng.integers(0, nd - B + 1, size=nb); sel = np.concatenate([np.arange(s, s + B) for s in starts])[:nd]
        rates.append(c[sel].sum() / n[sel].sum())
    rates = np.array(rates); pooled = c.sum() / n.sum()
    yearly = {}
    for i, day in enumerate(days): yearly.setdefault(day.year, [0, 0]); yearly[day.year][0] += c[i]; yearly[day.year][1] += n[i]
    P('  h=%3d R*=%2d bps: pooled %.4f %% (%d exceedance-seconds of %d) | block-bootstrap 95 %% interval %.4f-%.4f %% | distinct episodes %d | days with any exceedance %d of %d | by year: %s' % (
        h, RS[h], 100 * pooled, c.sum(), n.sum(), 100 * np.percentile(rates, 2.5), 100 * np.percentile(rates, 97.5), episodes[h], int((c > 0).sum()), nd, ', '.join('%d: %.4f %%' % (yv, 100 * v[0] / v[1]) for yv, v in sorted(yearly.items()))))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
