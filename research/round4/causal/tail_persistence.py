"""Sudden-move risk after apparent calm (owner section 4). Replay R_exact entries (dedup), time-ordered. Trailing statistics known at
entry (previous N settled windows): share with standardized realized surprise r <= -3, mean |r|. Forward: loss rate and P(r <= -3)."""
import json, sys, math, time
inp, outp, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
KN = [(3, 0.456, 0.878, 1.216), (25, 1.025, 1.739, 1.216), (130, 1.664, 2.577, 1.044)]
def law(t):
    t = min(130, max(3, t)); lt = math.log(t)
    for a, b in zip(KN, KN[1:]):
        if t <= b[0]: f = (lt - math.log(a[0])) / (math.log(b[0]) - math.log(a[0])); return a[3] + f * (b[3] - a[3])
    return KN[-1][3]
def units(t, W=60):
    u = sorted(x for x in (t - j for j in range(W)) if x > 1e-9); n = len(u); return sum(u[i] * (2 * (n - 1 - i) + 1) for i in range(n)) / (W * W)
rows = [json.loads(l) for l in open(inp) if l.strip()]; rows = [r for r in rows if r.get('in_dedup') and r.get('sig')]; rows.sort(key=lambda r: r['closeTs'])
for r in rows:
    sgn = 1 if r['side'] == 'UP' else -1; ce = r.get('c_eff_usd') if r.get('c_eff_usd') is not None else r['cushion_usd']
    r['_r'] = (sgn * r['marginUsd'] - ce) / (law(r['tau']) * r['sig'] * r['strike'] / 1e4 * math.sqrt(max(units(r['tau']), 1e-9))); r['_c'] = ce
hist = []; out = []
for r in rows:
    t0 = r['closeTs'] - 900; past = [h for h in hist if h[0] <= t0][-N:]
    if len(past) >= N // 2:
        out.append({'won': r['won'], 'r': r['_r'], 'tau': r['tau'], 'c': r['_c'], 'pf': r['pf'], 'share3': sum(1 for h in past if h[1] <= -3) / len(past), 'mabs': sum(abs(h[1]) for h in past) / len(past)})
    hist.append((r['closeTs'], r['_r']))
L = ['TAIL PERSISTENCE: trailing N=%d settled entries known at entry; %d entries scored' % (N, len(out))]
def table(key, edges, label, S):
    L.append(label)
    for lo, hi in zip(edges, edges[1:]):
        b = [x for x in S if lo <= x[key] < hi]
        if not b: continue
        k = sum(1 for x in b if not x['won']); E = sum(x['pf'] for x in b)
        L.append('  %s [%.3f,%.3f): n %5d | losses %2d (1 in %s, O/E %.2f) | fwd P(r<=-3) %.2f%% | P(r<=-4) %.2f%%' % (key, lo, hi, len(b), k, ('%.0f' % (len(b) / k)) if k else 'inf', k / E if E else float('nan'), 100 * sum(1 for x in b if x['r'] <= -3) / len(b), 100 * sum(1 for x in b if x['r'] <= -4) / len(b)))
table('share3', [0, 0.01, 0.02, 0.04, 0.08, 1.01], 'All entries, by trailing share of r<=-3:', out)
table('mabs', [0, 0.8, 1.0, 1.2, 1.5, 100], 'All entries, by trailing mean |r|:', out)
big = [x for x in out if x['tau'] >= 30 and x['c'] >= 50]
table('share3', [0, 0.01, 0.02, 0.04, 0.08, 1.01], 'tau>=30 & c_eff>=50 USD, by trailing share of r<=-3:', big)
table('mabs', [0, 0.8, 1.0, 1.2, 1.5, 100], 'tau>=30 & c_eff>=50 USD, by trailing mean |r|:', big)
open(outp, 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))
