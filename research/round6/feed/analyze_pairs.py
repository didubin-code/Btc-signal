"""Mechanism analysis on the paired per-second feeds (pairs.json). usage: python3 -I analyze_pairs.py <pairs.json> <out.txt>"""
import sys, json, math, collections
import numpy as np
D = json.load(open(sys.argv[1])); outp = sys.argv[2]
ser = {k: {int(s): v for s, v in D[k].items()} for k in ('brti', 'comp', 'ring', 'bn')}
win = {tk: int(cm) // 1000 for tk, cm in D['win'].items()}
closes = sorted(set(win.values()))
def tau_of(s):
    # seconds to the next close at or after s (windows are 900 s apart; tape covers the final 300 s)
    import bisect
    i = bisect.bisect_left(closes, s)
    return (closes[i] - s) if i < len(closes) else None
out = []; P = out.append
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
# ---------- 1. coverage and missing prints
secs = sorted(set(ser['comp']))
P('PAIRED FEEDS: composite seconds %d | BRTI print seconds %d | ring seconds %d | Binance seconds %d' % (len(ser['comp']), len(ser['brti']), len(ser['ring']), len(ser['bn'])))
miss = sum(1 for s in secs if s not in ser['brti']); P('  seconds with a composite tick but no BRTI print for that source second: %d (%.1f %%); consecutive-second pairs available: brti %d, comp %d' % (miss, 100 * miss / len(secs), sum(1 for s in ser['brti'] if s + 1 in ser['brti']), sum(1 for s in secs if s + 1 in ser['comp'])))
# repeated values (exact equality of consecutive values)
for k in ('brti', 'comp', 'ring', 'bn'):
    S = ser[k]; pairs = [(S[s], S[s + 1]) for s in S if s + 1 in S]
    P('  %-5s consecutive pairs %6d, identical consecutive values %5d (%.1f %%)' % (k, len(pairs), sum(1 for a, b in pairs if a == b), 100 * sum(1 for a, b in pairs if a == b) / max(1, len(pairs))))
# ---------- 2. variance ratios across horizons on COMMON seconds (returns requiring both endpoints present in every series compared)
def rets(S, h, sec_set):
    out = {}
    for s in sec_set:
        if s in S and s + h in S: out[s] = 1e4 * math.log(S[s + h] / S[s])
    return out
P(''); P('VARIANCE SCALING: RMS of h-second log returns / sqrt(h) (bps/sqrt s), on seconds where ALL listed series have both endpoints')
def table(keys, label):
    P('  ' + label)
    common = set.intersection(*(set(ser[k]) for k in keys))
    for h in (1, 2, 3, 5, 10, 20, 30, 60):
        R = {k: rets(ser[k], h, common) for k in keys}
        ss = set.intersection(*(set(R[k]) for k in keys))
        if len(ss) < 500: P('    h=%2d n=%d (too few)' % (h, len(ss))); continue
        vals = {k: np.array([R[k][s] for s in ss]) for k in keys}
        line = '    h=%2d s  n=%6d | ' % (h, len(ss)) + ' | '.join('%s %.3f' % (k, math.sqrt(np.mean(vals[k] ** 2)) / math.sqrt(h)) for k in keys)
        if 'brti' in keys and 'comp' in keys: line += ' | comp/brti %.3f' % (math.sqrt(np.mean(vals['comp'] ** 2)) / math.sqrt(np.mean(vals['brti'] ** 2)))
        if 'bn' in keys and 'brti' in keys: line += ' | bn/brti %.3f' % (math.sqrt(np.mean(vals['bn'] ** 2)) / math.sqrt(np.mean(vals['brti'] ** 2)))
        if 'ring' in keys and 'comp' in keys: line += ' | ring/comp %.3f' % (math.sqrt(np.mean(vals['ring'] ** 2)) / math.sqrt(np.mean(vals['comp'] ** 2)))
        P(line)
table(['brti', 'comp'], 'A. BRTI vs composite (all tape seconds)')
table(['brti', 'comp', 'bn'], 'B. BRTI vs composite vs Binance (Nov 13-15 seconds)')
table(['brti', 'comp', 'ring'], 'C. BRTI vs composite vs the 1 Hz ring sample (full-tape seconds)')
# ---------- 3. autocorrelation of 1-s returns and cross-correlation
P(''); P('AUTOCORRELATION of 1-s returns (lag 1, 2, 3) and the implied noise share (a negative lag-1 autocorrelation rho implies i.i.d. noise variance ~ -rho of the 1-s variance)')
common = set(ser['brti']) & set(ser['comp'])
for k in ('brti', 'comp', 'bn', 'ring'):
    S = ser[k]; R = rets(S, 1, set(S))
    for lag in (1, 2, 3):
        x = []; y = []
        for s in R:
            if s + lag in R: x.append(R[s]); y.append(R[s + lag])
        if lag == 1: rho1 = float(np.corrcoef(x, y)[0, 1])
        if lag == 1: line = '  %-5s n=%6d lag1 %+.3f' % (k, len(x), rho1)
        else: line += ' lag%d %+.3f' % (lag, float(np.corrcoef(x, y)[0, 1]))
    P(line)
P('CROSS-CORRELATION of 1-s returns, composite(t) vs BRTI(t+lag): which leads?')
Rc = rets(ser['comp'], 1, common); Rb = rets(ser['brti'], 1, common)
for lag in (-3, -2, -1, 0, 1, 2, 3):
    x = []; y = []
    for s in Rc:
        if s + lag in Rb: x.append(Rc[s]); y.append(Rb[s + lag])
    P('  lag %+d: corr %.3f (n=%d)' % (lag, float(np.corrcoef(x, y)[0, 1]), len(x)))
Rn = rets(ser['bn'], 1, set(ser['bn']))
P('CROSS-CORRELATION Binance(t) vs BRTI(t+lag):')
for lag in (-2, -1, 0, 1, 2):
    x = []; y = []
    for s in Rn:
        if s + lag in Rb: x.append(Rn[s]); y.append(Rb[s + lag])
    if len(x) > 100: P('  lag %+d: corr %.3f (n=%d)' % (lag, float(np.corrcoef(x, y)[0, 1]), len(x)))
# ---------- 4. by regime (60-s realised vol tercile of BRTI, per 60-s block) and by remaining time
P(''); P('BY REGIME (blocks of 60 s; tercile of the block\'s BRTI 1-s RMS) and BY REMAINING TIME: comp/brti RMS ratio at h = 1, 5, 30 s')
blocks = collections.defaultdict(list)
for s in common:
    if s + 1 in common: blocks[s // 60].append(s)
brms = {}
for b, ss in blocks.items():
    if len(ss) >= 40: brms[b] = math.sqrt(np.mean([(1e4 * math.log(ser['brti'][s + 1] / ser['brti'][s])) ** 2 for s in ss]))
cuts = [q(list(brms.values()), 1 / 3), q(list(brms.values()), 2 / 3)]
def ratio_for(sel_blocks, h):
    ss = [s for b in sel_blocks for s in blocks[b] if s + h in common]
    if len(ss) < 300: return None, len(ss)
    c = np.array([1e4 * math.log(ser['comp'][s + h] / ser['comp'][s]) for s in ss]); r = np.array([1e4 * math.log(ser['brti'][s + h] / ser['brti'][s]) for s in ss])
    return math.sqrt(np.mean(c ** 2)) / math.sqrt(np.mean(r ** 2)), len(ss)
for lab, sel in (('calm third (BRTI 1-s RMS < %.2f)' % cuts[0], lambda b: brms[b] < cuts[0]), ('middle third', lambda b: cuts[0] <= brms[b] < cuts[1]), ('active third (>= %.2f)' % cuts[1], lambda b: brms[b] >= cuts[1])):
    B = [b for b in brms if sel(b)]
    P('  %-36s blocks %4d | ' % (lab, len(B)) + ' | '.join('h=%2d: %s' % (h, ('%.3f (n=%d)' % ratio_for(B, h)) if ratio_for(B, h)[0] else 'n/a') for h in (1, 5, 30)))
for lab, lo, hi in (('final 0-60 s', 0, 60), ('60-120 s', 60, 120), ('120-300 s', 120, 300)):
    B = [b for b in brms if any(lo < (tau_of(s) or -1) <= hi for s in blocks[b][:1])]
    P('  remaining time %-12s blocks %4d | ' % (lab, len(B)) + ' | '.join('h=%2d: %s' % (h, ('%.3f (n=%d)' % ratio_for(B, h)) if ratio_for(B, h)[0] else 'n/a') for h in (1, 5, 30)))
# ---------- 5. what matters for settlement: the 60-print average's innovation
P(''); P('SETTLEMENT-RELEVANT: RMS change of the trailing 60-s mean over 60 s (bps), BRTI vs composite, on common seconds')
def mean60(S, s):
    v = [S[t] for t in range(s - 59, s + 1) if t in S]
    return (sum(v) / len(v)) if len(v) >= 55 else None
xs = []; ys = []
for s in sorted(common):
    a = mean60(ser['brti'], s); b = mean60(ser['brti'], s + 60); c = mean60(ser['comp'], s); d = mean60(ser['comp'], s + 60)
    if a and b and c and d: xs.append(1e4 * math.log(b / a)); ys.append(1e4 * math.log(d / c))
if xs: P('  n=%d | BRTI mean60 60-s change RMS %.2f bps | composite %.2f bps | ratio comp/brti %.3f | corr %.3f' % (len(xs), math.sqrt(np.mean(np.array(xs) ** 2)), math.sqrt(np.mean(np.array(ys) ** 2)), math.sqrt(np.mean(np.array(ys) ** 2)) / math.sqrt(np.mean(np.array(xs) ** 2)), float(np.corrcoef(xs, ys)[0, 1])))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
