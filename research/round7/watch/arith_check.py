#!/usr/bin/env python3
"""Independent arithmetic spot-check of the settlement exposure, computed from the declaration's definition and the raw tape samples —
not from the production helper. For each case: the engine's values (payload.signal.geometry / pr11) vs an independent recomputation.
usage: arith_check.py <rstar_0.050.json> <case>=<payload.json>:<tape.ndjson> ..."""
import sys, json, math
tab = json.load(open(sys.argv[1]))['rstar']; tab = {int(k): v for k, v in tab.items()}
def samples_of(tape):
    S = []
    for l in open(tape):
        if l.startswith('{"k":"s"') or '"k": "s"' in l[:12]:
            o = json.loads(l); S.append((o['t'], o['v']))
    S.sort(); return S
def nearest(S, t, tol=600):
    lo, hi = 0, len(S) - 1; best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if S[mid][0] < t: lo = mid + 1
        else: hi = mid - 1
    for i in (lo - 1, lo):
        if 0 <= i < len(S) and abs(S[i][0] - t) <= tol and (best is None or abs(S[i][0] - t) < abs(best[0] - t)): best = S[i]
    return best
rows = []
for arg in sys.argv[2:]:
    name, rest = arg.split('='); pl, tape = rest.split(':')
    p = json.load(open(pl)); sig = p['signal']; g = sig['geometry']; pr = sig['pr11']; K = sig['strike']; close = p['market']['closeMs']; ts = p['ts']
    S = samples_of(tape)
    # independent: prints passed = whole seconds of the final minute elapsed by the decision time (print k at close-60s+k s, k=1..60)
    win_start = close - 60000
    tau = (close - ts) / 1000.0
    n_lock = 0 if ts < win_start else min(60, int(math.floor((ts - win_start) / 1000.0)))
    n_rem = 60 - n_lock
    idx = p['index']['value'] if p.get('index') and p['index'].get('value') is not None else g['index']
    # matching as stated by the engine's comment: each sample belongs to the print second it is nearest to (rounded), kept only if
    # within 600 ms, each print second keeping its nearest sample; a print that passed < 1.1 s ago with no sample takes the live index
    by_sec = {}
    for t, v in S:
        if t > ts or t < close - 61000: continue
        off = int(round((close - t) / 1000.0))
        if off < 0 or off >= 60: continue
        d = abs(close - off * 1000 - t)
        if d > 600: continue
        if off not in by_sec or d < by_sec[off][1]: by_sec[off] = (v, d)
    lsum = 0.0; lobs = 0
    for off in range(0, 60):
        tp = close - off * 1000
        if tp > ts: continue
        if off in by_sec: lsum += by_sec[off][0]; lobs += 1
        elif ts - tp <= 1100: lsum += idx; lobs += 1
    locked_mean = lsum / lobs if lobs else float('nan')
    # the engine's expected settlement (b6 and b7 geometry): sampled seconds at their mean, the rest at the index
    exp_settle = (locked_mean * n_lock + idx * n_rem) / 60.0 if n_lock > 0 and lobs else idx
    gap = exp_settle - K
    # the b7 exposure rule: a passed second without a sample is an unknown print (valued at the index, counted with the unknown prints)
    n_missing = n_lock - lobs; r_unknown = min(60, n_rem + n_missing)
    gap_x = ((locked_mean * lobs + idx * r_unknown) / 60.0 - K) if (n_missing > 0 and lobs > 0) else gap
    cushion_bps = abs(gap_x) / K * 1e4
    if n_lock >= 1 and tau <= 60: h = max(1, min(60, r_unknown)); R = cushion_bps * 60.0 / h
    else: h = min(120, max(1, math.ceil(tau - 1e-9))); R = cushion_bps
    rstar = tab[h]; admit = R >= rstar
    side = 'UP' if gap > 0 else 'DOWN'
    off = (p.get('settlement') or {})
    eng = {'tau': sig['tau'], 'nLock': g.get('nLock'), 'n': g.get('nRemaining', g.get('n')), 'lockedMean': g.get('lockedMean'), 'expSettle': g.get('expectedSettle'), 'gapUsd': g.get('gapUsd'), 'side': sig['side'],
           'nKnown': pr.get('nKnown'), 'nMissing': pr.get('nMissing'), 'h': pr.get('h'), 'R': pr.get('R'), 'rstar': pr.get('rstar'), 'admit': pr.get('admit'), 'applies': pr.get('applies')}
    ind = {'tau': round(tau, 2), 'nLock': n_lock, 'n': n_rem, 'lockedMean': round(locked_mean, 2) if lobs else None, 'expSettle': round(exp_settle, 2), 'gapUsd': round(gap, 2), 'side': side, 'nKnown': lobs if 0 < tau <= 120 else None, 'nMissing': n_missing if 0 < tau <= 120 else None, 'h': h if 0 < tau <= 120 else None, 'R': round(R, 2) if 0 < tau <= 120 else None, 'rstar': rstar if 0 < tau <= 120 else None, 'admit': admit if 0 < tau <= 120 else None, 'applies': 0 < tau <= 120}
    diffs = []
    for k in ('nLock', 'n', 'nKnown', 'nMissing', 'h', 'rstar', 'admit', 'applies', 'side'):
        if eng.get(k) != ind.get(k) and not (k == 'n' and eng.get(k) is None): diffs.append(k)
    for k, tol in (('lockedMean', 0.6), ('expSettle', 0.6), ('gapUsd', 0.6), ('R', 0.2), ('tau', 0.05)):
        a, b = eng.get(k), ind.get(k)
        if a is not None and b is not None and abs(a - b) > tol: diffs.append(k)
    acc = (p.get('signal', {}).get('officialPanel') or {})
    print('%-14s engine %s' % (name, json.dumps(eng)))
    print('%-14s indep  %s  -> %s' % ('', json.dumps(ind), 'AGREE' if not diffs else 'DIFF ' + str(diffs)))
    rows.append((name, not diffs))
print('ARITH SPOT-CHECK', 'PASS' if all(ok for _, ok in rows) else 'FAIL', [n for n, ok in rows if not ok])
