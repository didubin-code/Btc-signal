"""Model-free settlement exposure. For every trace row (1 Hz, 0 < tau <= 120) the leader is the side of the expected settlement
(gap + mu > 0 -> UP). The required adverse path to reverse the settlement: the mean of the remaining prints must fall short of the
present level by R = (gap + mu) * 60 / r where r = remaining prints (incl alignment: prints at close-59..close, so r = min(60, ceil(tau)));
before the settlement minute (tau > 60) R = gap + mu (the whole cushion, with tau - 60 s of free movement before the minute).
R in bps of price. Tabulates P(leader loses) by tau bin x R bin with exact 95 % upper bounds, and policy entries: the first second in
the final 120 s with R >= R* (variant A: regardless of the engine's state; variant B: and the engine LOCKED with pf <= 0.002).
usage: python3 -I exposure_table.py <label> <records: ndjson files (ticker,truth/result,strike,official)> -- <traces> -- <out.txt> [--mu0]
   records may be out_full_mu records (truth, marginUsd) or proxy_markets (result yes/no, official, strike)."""
import sys, json, gzip, math, collections
args = sys.argv[1:]; label = args[0]; i1 = args.index('--'); i2 = args.index('--', i1 + 1)
recs_f = args[1:i1]; traces_f = args[i1 + 1:i2]; outp = args[i2 + 1]; mu0 = '--mu0' in args
win = {}
for f in recs_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        if not l.strip(): continue
        r = json.loads(l); tk = r['ticker']
        truth = r.get('truth') or ('UP' if r.get('result') == 'yes' else 'DOWN' if r.get('result') == 'no' else None)
        if truth and r.get('strike'): win[tk] = (truth, float(r['strike']), r.get('closeTs'))
TB = [('0-10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120.01)]
RB = [('<10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120), ('120-200', 120, 200), ('>=200', 200, 1e9)]
cell = collections.defaultdict(lambda: [0, 0, set(), set()])
RSTAR = [0, 10, 15, 20, 30, 40, 60, 80, 100, 120, 160, 200]
entA = {r: {} for r in RSTAR}; entB = {r: {} for r in RSTAR}
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
nrows = 0
for f in traces_f:
    for l in (gzip.open(f, 'rt') if f.endswith('.gz') else open(f)):
        r = json.loads(l); tk = r['tk']
        if tk not in win: continue
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None: continue
        truth, strike, _ = win[tk]; ce = r['gap'] + (0.0 if mu0 else (r.get('mu') or 0.0))
        if ce == 0: continue
        leader = 'UP' if ce > 0 else 'DOWN'; rem = min(60, math.ceil(tau - 1e-9)); R = abs(ce) / strike * 1e4 * (60.0 / rem if tau <= 60 else 1.0)
        lost = leader != truth; nrows += 1
        tb = next(n for n, lo, hi in TB if lo <= tau < hi); rb = next(n for n, lo, hi in RB if lo <= R < hi)
        c = cell[(tb, rb)]; c[0] += 1; c[1] += int(lost); c[2].add(tk)
        if lost: c[3].add(tk)
        for rs in RSTAR:
            if R >= rs:
                if tk not in entA[rs] or tau > entA[rs][tk][0]: entA[rs][tk] = (tau, leader, R)
                if isL(r.get('st')) and r.get('pf') is not None and r['pf'] <= 0.002 and (tk not in entB[rs] or tau > entB[rs][tk][0]): entB[rs][tk] = (tau, leader, R)
def cp_upper(k, n):
    if n == 0: return float('nan')
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k + 1)) if 0 < p < 1 else (1.0 if p <= 0 else 0.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
out = []; P = out.append
P('SETTLEMENT EXPOSURE TABLE: %s | windows %d | rows (0<tau<=120) %d | mu %s' % (label, len(win), nrows, 'ignored' if mu0 else 'included'))
P('P(leader loses) by seconds left x required adverse mean move R of the remaining prints (bps): lost rows/rows, w = lost windows/windows (upper 95 % on windows)')
P('  tau \\ R      ' + ''.join('%-30s' % n for n, _, _ in RB))
for tn, _, _ in TB:
    line = '  %-11s ' % tn
    for rn, _, _ in RB:
        n, k, W, LW = cell.get((tn, rn), [0, 0, set(), set()]); line += ('%d/%d w%d/%d (%.3f%%)' % (k, n, len(LW), len(W), 100 * cp_upper(len(LW), len(W)))).ljust(30) if n else '-'.ljust(30)
    P(line)
P(''); P('POLICY ENTRIES (first second in the final 120 s with R >= R*; one entry per window; A: any engine state, B: and LOCKED pf <= 0.002)')
P('  R*    | A: windows  losses  rate     upper95   median tau  p10 tau  share<=30s | B: windows  losses  rate     upper95   median tau')
for rs in RSTAR:
    A = entA[rs]; B = entB[rs]; ka = sum(1 for tk, (t, s, R) in A.items() if s != win[tk][0]); kb = sum(1 for tk, (t, s, R) in B.items() if s != win[tk][0])
    ta = sorted(t for t, s, R in A.values()); tbv = sorted(t for t, s, R in B.values())
    P('  %4d  | %7d  %5d  %.4f%%  %.4f%%  %6.1f  %6.1f  %4.0f%% | %7d  %5d  %.4f%%  %.4f%%  %6.1f' % (rs, len(A), ka, 100 * ka / max(1, len(A)), 100 * cp_upper(ka, len(A)), ta[len(ta) // 2] if ta else float('nan'), ta[len(ta) // 10] if ta else float('nan'), 100 * sum(1 for t in ta if t <= 30) / max(1, len(ta)), len(B), kb, 100 * kb / max(1, len(B)), 100 * cp_upper(kb, len(B)), tbv[len(tbv) // 2] if tbv else float('nan')))
json.dump({'label': label, 'windows': len(win), 'cells': {str(k): [v[0], v[1], len(v[2]), len(v[3])] for k, v in cell.items()}, 'entriesA': {str(rs): [[tk, t, s, R, s != win[tk][0]] for tk, (t, s, R) in A.items()] for rs, A in entA.items()}, 'entriesB': {str(rs): [[tk, t, s, R, s != win[tk][0]] for tk, (t, s, R) in B.items()] for rs, B in entB.items()}}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
