"""Reviewer recomputation for round6/feed (read-only on inputs). usage: python3 -I recompute.py <out.txt>"""
import sys, json, math, bisect, glob, os, collections, datetime as dt
import numpy as np
SP = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
outp = sys.argv[1]; out = []
def P(*a):
    s = ' '.join(str(x) for x in a); out.append(s); print(s, flush=True)
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
def rms(x): x = np.asarray(x, float); return math.sqrt(np.mean(x * x)) if len(x) else float('nan')
def utc(s): return dt.datetime.fromtimestamp(s, dt.timezone.utc).strftime('%m-%d %H:%M')
# ---------------------------------------------------------------- trades -> fit-type index and variants
def load_trades(p):
    T = []; Pp = []
    for l in open(p):
        if not l.strip(): continue
        o = json.loads(l); T.append(o['t']); Pp.append(o['p'])
    return T, Pp
def last_series(T, Pp, t0, t1, stale):
    o = {}
    for s in range(t0, t1):
        i = bisect.bisect_left(T, s + 1) - 1
        o[s] = Pp[i] if i >= 0 and (s + 1) - T[i] <= stale else None
    return o
PT = SP + '/incident_20261114T0015Z/public_trades/'
pairs = [(PT + 'cb_20261112T2125_1113T2244.ndjson', PT + 'kr_20261112T2125_1113T2244.ndjson'), (PT + 'cb_20261113T2244_0036.ndjson', PT + 'kr_20261113T2244_0036.ndjson')]
variants = {'author(cb1/kr.8,stale30)': {}, 'cb_only': {}, 'kr_only': {}, 'equal_w': {}, 'stale_inf': {}, 'both_required': {}}
ranges = []; nostat = collections.Counter()
for cbf, krf in pairs:
    Tc, Pc = load_trades(cbf); Tk, Pk = load_trades(krf)
    t0 = int(min(Tc[0], Tk[0])) + 1; t1 = int(max(Tc[-1], Tk[-1])); ranges.append((t0, t1))
    cbs, krs = last_series(Tc, Pc, t0, t1, 30.0), last_series(Tk, Pk, t0, t1, 30.0)
    cbi, kri = last_series(Tc, Pc, t0, t1, 1e9), last_series(Tk, Pk, t0, t1, 1e9)
    # per-second trade presence
    cbset = set(int(t) for t in Tc); krset = set(int(t) for t in Tk)
    for s in range(t0, t1):
        a, b = cbs[s], krs[s]
        if s not in cbset: nostat['cb_no_trade_in_second'] += 1
        if s not in krset: nostat['kr_no_trade_in_second'] += 1
        if a is None: nostat['cb_stale>30'] += 1
        if b is None: nostat['kr_stale>30'] += 1
        nostat['seconds'] += 1
        V = variants
        if a is not None and b is not None: V['author(cb1/kr.8,stale30)'][s] = (a + 0.8 * b) / 1.8; V['equal_w'][s] = (a + b) / 2; V['both_required'][s] = (a + 0.8 * b) / 1.8
        elif a is not None: V['author(cb1/kr.8,stale30)'][s] = a; V['equal_w'][s] = a
        elif b is not None: V['author(cb1/kr.8,stale30)'][s] = b; V['equal_w'][s] = b
        if a is not None: V['cb_only'][s] = a
        if b is not None: V['kr_only'][s] = b
        ai, bi = cbi[s], kri[s]
        if ai is not None and bi is not None: V['stale_inf'][s] = (ai + 0.8 * bi) / 1.8
        elif ai is not None: V['stale_inf'][s] = ai
fit = variants['author(cb1/kr.8,stale30)']
P('FIT-TYPE rebuilt; ranges', ranges, '| per-second stats', dict(nostat))
inrng = lambda s: any(a <= s < b for a, b in ranges)
# ---------------------------------------------------------------- rows (scoreboard) and tapes
rows = []
for f in sorted(glob.glob(SP + '/r30/live/scoreboard/rows/*.ndjson')):
    for l in open(f):
        if l.strip(): rows.append(json.loads(l))
rows.sort(key=lambda r: r['ts'])
P('rows total', len(rows))
tapes = [SP + '/incident_20261114T0015Z/own_capture_2/tape_since_boot.ndjson', SP + '/round3/tape/tape_all.ndjson', SP + '/round3/tape/pull_20261115T014056Z.ndjson', SP + '/round3/tape/_new.ndjson']
drows = {}  # second -> first d row
ring = {}
for tp in tapes:
    for l in open(tp):
        try: o = json.loads(l)
        except Exception: continue
        if o.get('k') == 's':
            ring.setdefault(int(o['t'] // 1000), (o['t'], o['v']))
        elif o.get('k') == 'd':
            drows.setdefault(o['ts'] // 1000, o)
P('tape d rows (distinct seconds)', len(drows), 'ring seconds', len(ring))
# dedup BRTI prints by seq (as author) and a per-row (reused) series for the section-27 reproduction
brti = {}; seqs = {}; comp = {}; perrow = []; reuse = 0; age_by_sec = {}; tick_phase = []
lastseq = None
for s in sorted(drows):
    o = drows[s]; li = (o.get('liveIdx') or {}); v = li.get('value')
    if v: comp[s] = float(v)
    if o.get('ageMs') is not None: age_by_sec[s] = o['ageMs']
    tick_phase.append(o['ts'] % 1000)
    b = ((o.get('brti') or {}).get('last') or {})
    if b.get('value') and b.get('sourceTs'):
        ss = int(b['sourceTs'] // 1000); sq = b.get('seq')
        if sq not in seqs: seqs[sq] = ss; brti.setdefault(ss, float(b['value']))
        else: reuse += 1
        perrow.append((s, float(v) if v else None, float(b['value']), sq == lastseq, (o.get('kal') or {}).get('ticker'))); lastseq = sq
P('tape: comp seconds', len(comp), 'unique prints', len(brti), 'reused rows', reuse, '| tick phase ms p10/p50/p90', q(tick_phase, .1), q(tick_phase, .5), q(tick_phase, .9))
# Binance
bn = {}; days = {}
secdir = SP + '/round4/replay_live/data/sec/usdc'
for s in list(comp) + [x for x in fit]:
    d = dt.datetime.fromtimestamp(s, dt.timezone.utc); key = d.strftime('%Y-%m-%d')
    if key not in days:
        p = os.path.join(secdir, key + '.f64'); days[key] = np.fromfile(p, dtype='<f8') if os.path.exists(p) else None
    a = days[key]
    if a is not None:
        v = a[d.hour * 3600 + d.minute * 60 + d.second]
        if np.isfinite(v) and v > 0: bn[s] = float(v)
# rows' spot as BRTI for period 1 (dedup by value change, age < 1500 ms)
spot = {}
for r in rows:
    s = r['ts'] // 1000
    if r.get('ref') == 'OFFICIAL' and r.get('spot') and (r.get('brtiAgeMs') or 9e9) < 1500 and s not in spot: spot[s] = float(r['spot'])
for s in sorted(spot):
    if s - 1 in spot and spot[s] == spot[s - 1]: del spot[s]
# ---------------------------------------------------------------- (1) alignment
def rets(S, h=1):
    return {s: 1e4 * math.log(S[s + h] / S[s]) for s in S if s + h in S and S[s] > 0 and S[s + h] > 0}
def xcorr(A, B, lags, label):
    Ra, Rb = rets(A), rets(B); line = []
    for lag in lags:
        x = []; y = []
        for s in Ra:
            if s + lag in Rb: x.append(Ra[s]); y.append(Rb[s + lag])
        line.append('lag %+d: %.3f (n=%d)' % (lag, float(np.corrcoef(x, y)[0, 1]) if len(x) > 50 else float('nan'), len(x)))
    P('  ' + label + ' | ' + ' | '.join(line))
P(''); P('(1) ALIGNMENT, 1-s log returns, A(t) vs B(t+lag)')
xcorr(fit, bn, (-2, -1, 0, 1, 2), 'fit-type(t) vs Binance(t+lag) [both last-trade-of-second; expect lag 0]')
xcorr(variants['cb_only'], bn, (-1, 0, 1), 'Coinbase-last(t) vs Binance(t+lag)')
xcorr(fit, brti, (-2, -1, 0, 1, 2), 'fit-type(t) vs BRTI tape print stamped (t+lag) [period 2]')
xcorr(fit, spot, (-2, -1, 0, 1, 2), 'fit-type(t) vs rows spot deduped at row-second (t+lag) [period 1]')
xcorr(comp, brti, (-2, -1, 0, 1, 2), 'composite tick(t) vs BRTI print stamped (t+lag) [tapes]')
xcorr(comp, fit, (-2, -1, 0, 1, 2), 'composite tick(t) vs fit-type(t+lag)')
xcorr(bn, brti, (-1, 0, 1, 2), 'Binance(t) vs BRTI(t+lag) [author: +1 = 0.71]')
# ---------------------------------------------------------------- (2) dedup / missing prints
P(''); P('(2) DEDUP: missing prints and reuse')
secs = sorted(comp); miss = [s for s in secs if s not in brti]
P('  seconds with composite but no unique print:', len(miss), '(%.1f %%)' % (100 * len(miss) / len(secs)))
byday = collections.defaultdict(lambda: [0, 0])
for s in secs:
    k = utc(s)[:5]; byday[k][1] += 1; byday[k][0] += (s not in brti)
P('  missing by day: ' + ', '.join('%s %.1f %% (n=%d)' % (k, 100 * v[0] / v[1], v[1]) for k, v in sorted(byday.items())))
Rc = rets(comp)
a_m = [abs(Rc[s]) for s in Rc if s not in brti]; a_p = [abs(Rc[s]) for s in Rc if s in brti]
P('  |composite 1-s return| mean: seconds WITHOUT print %.3f bps (n=%d) vs WITH print %.3f bps (n=%d); RMS %.3f vs %.3f' % (np.mean(a_m), len(a_m), np.mean(a_p), len(a_p), rms(a_m), rms(a_p)))
# run lengths of missing
runs = collections.Counter(); cur = 0
for s in secs:
    if s not in brti: cur += 1
    elif cur: runs[min(cur, 5)] += 1; cur = 0
P('  missing-run lengths (1,2,3,4,5+):', [runs[k] for k in (1, 2, 3, 4, 5)])
# print value consistency: tape print vs rows spot at the same source second
both = [s for s in brti if s in spot]
dif = [1e4 * (brti[s] - spot[s]) / spot[s] for s in both]
P('  tape print vs rows spot (same second): n=%d, |diff| median %.3f bps, max %.3f bps' % (len(both), q([abs(x) for x in dif], .5), max(abs(x) for x in dif) if dif else float('nan')))
# section 27 reproduction: per-window brti/comp 1-s RMS ratio, per-row (with reuse) vs dedup
win = collections.defaultdict(list)
for s, c, b, reused, tk in perrow:
    if tk and c: win[tk].append((s, c, b))
per_row_r = []; dedup_r = []; pooled_c = []; pooled_b = []; pooled_c2 = []; pooled_b2 = []
for tk, L in win.items():
    L.sort();
    if len(L) < 200: continue
    cs = [x[1] for x in L]; bs = [x[2] for x in L]
    rc = np.diff(np.log(cs)) * 1e4; rb = np.diff(np.log(bs)) * 1e4
    per_row_r.append(rms(rb) / rms(rc))
    ss = [x[0] for x in L]
    d_c = [1e4 * math.log(comp[s + 1] / comp[s]) for s in ss if s + 1 in comp and s in brti and s + 1 in brti]
    d_b = [1e4 * math.log(brti[s + 1] / brti[s]) for s in ss if s + 1 in comp and s in brti and s + 1 in brti]
    if len(d_c) > 100: dedup_r.append(rms(d_b) / rms(d_c)); pooled_c2 += d_c; pooled_b2 += d_b
    pooled_c += list(rc); pooled_b += list(rb)
P('  section-27 reproduction, per-window median BRTI/composite 1-s RMS: per-row series %.3f (p10 %.3f p90 %.3f, %d windows) | dedup series %.3f (p10 %.3f p90 %.3f, %d windows) | pooled per-row %.3f | pooled dedup %.3f' % (q(per_row_r, .5), q(per_row_r, .1), q(per_row_r, .9), len(per_row_r), q(dedup_r, .5), q(dedup_r, .1), q(dedup_r, .9), len(dedup_r), rms(pooled_b) / rms(pooled_c), rms(pooled_b2) / rms(pooled_c2)))
# ---------------------------------------------------------------- (3) estimator fidelity: inflation
P(''); P('(3) ESTIMATOR: input-age inflation from the server formula, joined tape ageMs x rows tau')
def var_units(tau, W=60):
    t = max(0.0, tau); d = sorted(t - off for off in range(W) if t - off > 1e-9); n = len(d)
    return sum(d[i] * (2 * (n - 1 - i) + 1) for i in range(n)) / (W * W), n
def infl(tau, age_ms):
    units, n = var_units(tau); a = max(0, age_ms) / 1000.0; nLock = 60 - n
    stale = a * (min(60, n + min(nLock, a)) / 60) ** 2
    return math.sqrt((units + stale) / units) if units > 0 else 1.0
bands = [(240, 301), (120, 240), (90, 120), (30, 90), (0, 30)]
inf_by = collections.defaultdict(list); age_all = []
for r in rows:
    s = r['ts'] // 1000
    if s in age_by_sec and age_by_sec[s] is not None:
        a = age_by_sec[s]; age_all.append(a)
        for lo, hi in bands:
            if lo <= r['tau'] < hi: inf_by[(lo, hi)].append(infl(r['tau'], a))
P('  index input age ms (tape ageMs): p50 %.0f p90 %.0f p99 %.0f (n=%d)' % (q(age_all, .5), q(age_all, .9), q(age_all, .99), len(age_all)))
for b in bands:
    v = inf_by[b]
    if v: P('  tau %3d-%3d: inflation median %.4f p90 %.4f p99 %.4f (n=%d)' % (b[0], b[1], q(v, .5), q(v, .9), q(v, .99), len(v)))
# ---------------------------------------------------------------- (a) model-definition ratio, author's method + cells + variants
class Pre:
    """prefix sums of squared 1-s simple returns (bps) of a 1 Hz dict series; window (end-Lw, end]"""
    def __init__(self, series):
        ks = sorted(series); self.t0 = ks[0]; N = ks[-1] - ks[0] + 2
        s2 = np.zeros(N); c = np.zeros(N)
        for s in ks:
            a = series.get(s - 1); b = series[s]
            if a and b: i = s - self.t0; s2[i] = ((b - a) / a * 1e4) ** 2; c[i] = 1
        self.S = np.concatenate([[0.0], np.cumsum(s2)]); self.C = np.concatenate([[0], np.cumsum(c)]); self.N = N
    def rms(self, end, Lw):
        hi = end - self.t0 + 1; lo = hi - Lw
        if hi < 1 or hi > self.N: return None, 0
        lo = max(lo, 0); n = int(self.C[hi] - self.C[lo]); s2 = self.S[hi] - self.S[lo]
        return (math.sqrt(s2 / n), n) if n >= max(5, Lw // 3) else (None, n)
    def sigma(self, end):
        a, _ = self.rms(end, 120); b, _ = self.rms(end, 900)
        return (math.sqrt((a * a + b * b) / 2) if a and b else None), a, b
PRE = {name: Pre(series) for name, series in variants.items()}
def sig_cached(key, series, end): return PRE['author(cb1/kr.8,stale30)' if key == 'author' else key].sigma(end)
def rms_vol(series, end, Lw): return PRE['author(cb1/kr.8,stale30)'].rms(end, Lw)
P(''); P('(a) MODEL-DEFINITION RATIO recomputed: rows sigma/1.03 / fit-type sigma(120,900)')
frows = [r for r in rows if inrng(r['ts'] // 1000)]
seen = set(); frows2 = []
for r in frows:
    s = r['ts'] // 1000
    if s in seen: continue
    seen.add(s); frows2.append(r)
frows = frows2
P('  rows in fit periods (first per second):', len(frows))
R = collections.defaultdict(list)
for r in frows:
    end = r['ts'] // 1000 - 1; sf, f120, f900 = sig_cached('author', fit, end)
    if sf is None or not r.get('sigma'): continue
    live = r['sigma'] / 1.03; rr = live / sf
    s = r['ts'] // 1000; a = age_by_sec.get(s)
    raw = live / infl(r['tau'], a) if a is not None else None
    R['all'].append(rr)
    if raw is not None: R['all_raw(period2,infl removed)'].append(raw / sf); R['all_period2_unadjusted'].append(rr)
    for lo, hi in bands:
        if lo <= r['tau'] < hi: R['tau %d-%d' % (lo, hi)].append(rr)
    reg = r.get('regime'); cush = abs(r['gap']) / r['idx'] * 1e4 if r.get('gap') is not None and r.get('idx') else None
    if reg in (3, 4): R['regime 3-4'].append(rr)
    if reg in (3, 4) and 90 <= r['tau'] <= 120: R['regime 3-4 & tau 90-120'].append(rr)
    if reg in (3, 4) and 90 <= r['tau'] <= 120 and cush is not None and 10 <= cush <= 25: R['regime 3-4 & tau 90-120 & cushion 10-25'].append(rr)
    if reg in (3, 4) and 90 <= r['tau'] <= 120 and cush is not None and 15 <= cush <= 18: R['regime 3-4 & tau 90-120 & cushion 15-18'].append(rr)
    if cush is not None and 15 <= cush <= 18 and 90 <= r['tau'] <= 120: R['tau 90-120 & cushion 15-18 (any regime)'].append(rr)
    R['day ' + utc(s)[:5]].append(rr)
    R['regime %s' % reg].append(rr)
for k in sorted(R):
    v = R[k]; P('   %-48s n=%6d median %.3f p10 %.3f p90 %.3f  mean-of-squares ratio %.3f' % (k, len(v), q(v, .5), q(v, .1), q(v, .9), math.sqrt(np.mean(np.array(v) ** 2))))
P('  variants of the fit-type construction (same rows, median of rows sigma/1.03 / variant sigma):')
for name, series in variants.items():
    v = []
    for r in frows:
        end = r['ts'] // 1000 - 1; sf, _, _ = sig_cached(name, series, end)
        if sf and r.get('sigma'): v.append(r['sigma'] / 1.03 / sf)
    P('   %-28s n=%6d median %.3f p10 %.3f p90 %.3f' % (name, len(v), q(v, .5), q(v, .1), q(v, .9)))
# 1-s RMS level per variant on common seconds (fit periods), plus composite (rows idx) and Binance
common = set(fit) & set(variants['both_required']) & set(variants['kr_only'])
rows_idx = {r['ts'] // 1000: r['idx'] for r in frows if r.get('idx')}
P('  1-s RMS (bps) on seconds common to all variants + rows idx:')
cs = [s for s in common if s in rows_idx and s + 1 in rows_idx and all(s + 1 in V for V in variants.values())]
line = []
for name, V in list(variants.items()) + [('rows idx (composite)', rows_idx), ('binance', bn)]:
    x = [1e4 * math.log(V[s + 1] / V[s]) for s in cs if s in V and s + 1 in V]
    line.append('%s %.3f' % (name, rms(x)))
P('   n=%d | ' % len(cs) + ' | '.join(line))
# ---------------------------------------------------------------- (5) day-by-day comp/brti from the tapes (transfer to Nov 15-16)
P(''); P('(5) comp/BRTI RMS ratio by day (tapes, dedup prints), h = 1, 5, 30, 60')
for d in sorted(byday):
    line = []
    for h in (1, 5, 30, 60):
        ss = [s for s in comp if utc(s)[:5] == d and s + h in comp and s in brti and s + h in brti]
        if len(ss) < 500: line.append('h=%d n/a' % h); continue
        c = [1e4 * math.log(comp[s + h] / comp[s]) for s in ss]; b = [1e4 * math.log(brti[s + h] / brti[s]) for s in ss]
        line.append('h=%2d %.3f (n=%d)' % (h, rms(c) / rms(b), len(ss)))
    P('   %s | ' % d + ' | '.join(line))
# by regime bucket of the rows (tape seconds joined to rows' regime)
regime_of = {r['ts'] // 1000: r.get('regime') for r in rows}
P('  comp/BRTI by model regime bucket (rows joined), h=1,2,5,30:')
for grp, name in (((1, 2, 3), 'buckets 1-3'), ((4,), 'bucket 4'), ((5,), 'bucket 5'), ((6,), 'bucket 6')):
    line = []
    for h in (1, 2, 5, 30):
        ss = [s for s in comp if regime_of.get(s) in grp and s + h in comp and s in brti and s + h in brti]
        if len(ss) < 300: line.append('h=%d n/a' % h); continue
        c = [1e4 * math.log(comp[s + h] / comp[s]) for s in ss]; b = [1e4 * math.log(brti[s + h] / brti[s]) for s in ss]
        line.append('h=%2d %.3f (n=%d)' % (h, rms(c) / rms(b), len(ss)))
    P('   %-12s | ' % name + ' | '.join(line))
# ---------------------------------------------------------------- (6) regime terciles: autocorrelation of each series
P(''); P('(6) REGIME TERCILES (60-s blocks by BRTI 1-s RMS): lag-1 autocorr of brti / comp returns, variance ratio comp/brti at h=1,2,3,5, and fit-type/BRTI where available')
cm = set(comp) & set(brti)
blocks = collections.defaultdict(list)
for s in cm:
    if s + 1 in cm: blocks[s // 60].append(s)
brms = {b: rms([1e4 * math.log(brti[s + 1] / brti[s]) for s in ss]) for b, ss in blocks.items() if len(ss) >= 40}
cuts = [q(list(brms.values()), 1 / 3), q(list(brms.values()), 2 / 3)]
def ac1(S, ss):
    Rr = {s: 1e4 * math.log(S[s + 1] / S[s]) for s in ss if s + 1 in S and s in S}
    x = [Rr[s] for s in Rr if s + 1 in Rr]; y = [Rr[s + 1] for s in Rr if s + 1 in Rr]
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 100 else float('nan')
for lab, sel in (('calm', lambda b: brms[b] < cuts[0]), ('middle', lambda b: cuts[0] <= brms[b] < cuts[1]), ('active', lambda b: brms[b] >= cuts[1])):
    B = [b for b in brms if sel(b)]; ss = [s for b in B for s in blocks[b]]
    line = 'ac1 brti %+.3f comp %+.3f' % (ac1(brti, ss), ac1(comp, ss))
    ssf = [s for s in ss if s in fit]
    if len(ssf) > 500: line += ' fit %+.3f bn %+.3f' % (ac1(fit, ssf), ac1(bn, [s for s in ss if s in bn]))
    for h in (1, 2, 3, 5):
        sh = [s for s in ss if s + h in cm]
        c = [1e4 * math.log(comp[s + h] / comp[s]) for s in sh]; b = [1e4 * math.log(brti[s + h] / brti[s]) for s in sh]
        line += ' | h=%d comp/brti %.3f' % (h, rms(c) / rms(b))
        shf = [s for s in sh if s in fit and s + h in fit]
        if len(shf) > 500: line += ' fit/brti %.3f' % (rms([1e4 * math.log(fit[s + h] / fit[s]) for s in shf]) / rms([1e4 * math.log(brti[s + h] / brti[s]) for s in shf]))
    P('   %-7s blocks %4d | %s' % (lab, len(B), line))
# ---------------------------------------------------------------- (7) settlement quantity
P(''); P('(7) SETTLEMENT QUANTITY: 60-s change of trailing 60-s mean, comp/brti, with BRTI shifted by lag; and horizon 90/120 returns')
def mean60(S, s):
    v = [S[t] for t in range(s - 59, s + 1) if t in S]
    return (sum(v) / len(v)) if len(v) >= 55 else None
for lag in (-1, 0, 1):
    Bsh = {s + lag: v for s, v in brti.items()}
    xs = []; ys = []
    for s in sorted(cm):
        a = mean60(Bsh, s); b = mean60(Bsh, s + 60); c = mean60(comp, s); d = mean60(comp, s + 60)
        if a and b and c and d: xs.append(1e4 * math.log(b / a)); ys.append(1e4 * math.log(d / c))
    P('   BRTI shift %+d: n=%d ratio comp/brti %.3f corr %.3f' % (lag, len(xs), rms(ys) / rms(xs), float(np.corrcoef(xs, ys)[0, 1])))
for h in (90, 120):
    ss = [s for s in cm if s + h in cm]
    c = [1e4 * math.log(comp[s + h] / comp[s]) for s in ss]; b = [1e4 * math.log(brti[s + h] / brti[s]) for s in ss]
    P('   plain %d-s returns: n=%d comp/brti %.3f' % (h, len(ss), rms(c) / rms(b)))
# settlement innovation from tau=100: mean of prints stamped close-59..close minus index at close-100
closes = set()
for s, o in drows.items():
    cm_ = (o.get('kal') or {}).get('closeMs')
    if cm_: closes.add(int(cm_) // 1000)
xs = []; ys = []
for c in sorted(closes):
    for tau in (100,):
        s0 = c - tau
        mb = mean60(brti, c); mc = mean60(comp, c)
        if mb and mc and s0 in brti and s0 in comp: xs.append(1e4 * math.log(mb / brti[s0])); ys.append(1e4 * math.log(mc / comp[s0]))
P('   settlement innovation from tau=100 (mean60 at close vs index at close-100): n=%d comp/brti %.3f corr %.3f' % (len(xs), rms(ys) / rms(xs) if xs else float('nan'), float(np.corrcoef(xs, ys)[0, 1]) if len(xs) > 10 else float('nan')))
# fit-type variance signature vs composite (ratio of 60-s RMS to 1-s RMS), fit periods
P(''); P('(8) VARIANCE SIGNATURE (RMS_h/sqrt(h) / RMS_1) in the fit periods on common seconds of fit-type, rows idx, spot')
cm2 = set(fit) & set(rows_idx) & set(spot)
base = {}
for name, S in (('fit-type', fit), ('composite', rows_idx), ('official', spot), ('binance', bn), ('cb_only', variants['cb_only'])):
    line = []
    for h in (1, 5, 30, 60):
        ss = [s for s in cm2 if s + h in cm2 and s in S and s + h in S]
        x = rms([1e4 * math.log(S[s + h] / S[s]) for s in ss]) / math.sqrt(h)
        if h == 1: base[name] = x
        line.append('h=%2d %.3f (x%.3f)' % (h, x, x / base[name]))
    P('   %-10s | ' % name + ' | '.join(line))
open(outp, 'w').write('\n'.join(out) + '\n')
