"""Live tail test and volatility check (round 4). For each live market with a result: the R_exact entry row (first LOCKED row in the final
120 s with pFlip <= 0.002) and the row at tau ~120; basis-adjusted cushion c_eff = side-signed gap + mu (mu from the tape's basisMu when
present, else the health copy's basis.mean -3.4); model settlement sigma sigma_tot = kappa(tau)*sigma_row*idx/1e4*sqrt(units(tau));
realized surprise r = (side-signed official margin - c_eff)/sigma_tot. Also: realized 1-s volatility of the official BRTI ('spot') and
of the composite index ('idx') over the final 300 s (bps per sqrt s, RMS of 1-s log changes), versus the server's sigma at tau 120."""
import json, glob, os, math, statistics as st, sys, time
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R3 = SC + '/round3'
KNOTS = [(3, 0.456, 0.878, 1.216), (25, 1.025, 1.739, 1.216), (130, 1.664, 2.577, 1.044)]
def law(tau):
    t = min(KNOTS[-1][0], max(KNOTS[0][0], tau)); lt = math.log(t)
    for a, b in zip(KNOTS, KNOTS[1:]):
        if t <= b[0]:
            f = (lt - math.log(a[0])) / (math.log(b[0]) - math.log(a[0])); return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3]))
    k = KNOTS[-1]; return (k[1], k[2], k[3])
def units(t, W=60):
    u = sorted(x for x in (t - j for j in range(W)) if x > 1e-9); n = len(u)
    return sum(u[i] * (2 * (n - 1 - i) + 1) for i in range(n)) / (W * W), n
def surv(z, A, B): r = abs(z) / A; return (1 + r * r) ** (-B)
# basisMu per market from the tape (first row with basisMu)
mu_tape = {}
for l in open(R3 + '/tape/tape_all.ndjson'):
    try: r = json.loads(l)
    except Exception: continue
    tk = (r.get('kal') or {}).get('ticker')
    if tk and r.get('basisMu') is not None and tk not in mu_tape: mu_tape[tk] = r['basisMu']
mk = {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(L + '/scoreboard/markets/*.json')}
rec = []; vol = []
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; m = mk.get(tk)
    if not m or m.get('result') not in ('yes', 'no') or m.get('official') is None or not m.get('strike'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; official = float(m['official']); strike = float(m['strike'])
    rs = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau']); rs = [r for r in rs if r.get('tau') is not None]
    # realized vol over the final 300 s from spot (BRTI) and idx
    def rms(key):
        xs = [(r['tau'], r[key]) for r in rs if r.get(key)]
        d = [math.log(b[1] / a[1]) * 1e4 / math.sqrt(max(0.25, a[0] - b[0])) for a, b in zip(xs, xs[1:]) if a[0] > b[0] and a[1] > 0 and b[1] > 0]
        return math.sqrt(sum(x * x for x in d) / len(d)) if len(d) >= 50 else None
    v_brti, v_idx = rms('spot'), rms('idx')
    r120 = next((r for r in rs if r['tau'] <= 121 and r.get('sigma')), None)
    if r120 and v_brti and v_idx: vol.append({'tk': tk, 'sigma120': r120['sigma'], 'regime': r120.get('regime'), 'vBrti': v_brti, 'vIdx': v_idx})
    e = next((r for r in rs if 0 < r['tau'] <= 120 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and r['pFlip'] <= 0.002), None)
    if not e or e.get('gap') is None or not e.get('sigma') or not e.get('idx'): continue
    sgn = 1 if e['side'] == 'UP' else -1; mu = mu_tape.get(tk, -3.4)
    c_eff = sgn * e['gap'] + sgn * mu; m_s = sgn * (official - strike); A, B, kappa = law(e['tau']); un, n = units(e['tau'])
    sig_tot = kappa * e['sigma'] * e['idx'] / 1e4 * math.sqrt(un)
    rec.append({'tk': tk, 'tau': e['tau'], 'won': e['side'] == truth, 'c': c_eff, 'c_bps': c_eff / strike * 1e4, 'z_c': c_eff / sig_tot, 'r': (m_s - c_eff) / sig_tot, 'A': A, 'B': B, 'pf': e['pFlip'], 'sigma': e['sigma'], 'regime': e.get('regime'), 'sig_tot': sig_tot, 'req': abs(c_eff) * 60 / max(n, 1), 'mu_src': 'tape' if tk in mu_tape else 'health'})
Ls = ['LIVE TAIL TEST: %d R_exact entries with official results (Nov 12-16 2026)' % len(rec)]
def q(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = math.floor(k); c = min(f + 1, len(xs) - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)
Ls.append('Cushion at entry (basis-adjusted): USD p10/p50/p90 %.1f / %.1f / %.1f | bps %.2f / %.2f / %.2f | model sigma units z_c %.2f / %.2f / %.2f | required move over remaining prints p50 %.1f USD' % (
    q([x['c'] for x in rec], .1), q([x['c'] for x in rec], .5), q([x['c'] for x in rec], .9), q([x['c_bps'] for x in rec], .1), q([x['c_bps'] for x in rec], .5), q([x['c_bps'] for x in rec], .9), q([x['z_c'] for x in rec], .1), q([x['z_c'] for x in rec], .5), q([x['z_c'] for x in rec], .9), q([x['req'] for x in rec], .5)))
lost = [x for x in rec if not x['won']]
Ls.append('Losses: %s' % ['%s tau %.1f c %.1f USD (%.1f bps) z_c %.2f r %.2f sigma %.3f regime %s' % (x['tk'][-13:], x['tau'], x['c'], x['c_bps'], x['z_c'], x['r'], x['sigma'], x['regime']) for x in lost])
def tail_table(sub, label):
    out = ['  %s: n %d' % (label, len(sub))]
    for z in (2, 3, 4, 5, 6):
        emp = sum(1 for x in sub if x['r'] <= -z); mod = sum(surv(z, x['A'], x['B']) / 2 for x in sub)
        out.append('    P(r <= -%d): empirical %d (%.3f %%), path law expects %.2f -> ratio %.2f' % (z, emp, 100 * emp / max(1, len(sub)), mod, emp / mod if mod else float('nan')))
    out.append('    losses %d vs sum pf %.3f (O/E %.2f)' % (sum(1 for x in sub if not x['won']), sum(x['pf'] for x in sub), sum(1 for x in sub if not x['won']) / max(1e-9, sum(x['pf'] for x in sub))))
    return out
Ls += tail_table(rec, 'all live')
for lo, hi, lab in [(0, 30, '<30 s'), (30, 60, '30-59'), (60, 90, '60-89'), (90, 121, '90-120')]: Ls += tail_table([x for x in rec if lo <= x['tau'] < hi], lab)
Ls += tail_table([x for x in rec if x['tau'] >= 30 and x['c'] >= 50], 'tau >= 30 and c_eff >= 50 USD')
Ls.append('r distribution (all): p1 %.2f p5 %.2f p50 %.2f | share r <= -2: %.1f %% (replay usdc all months at tau>=30: about 2-6 %%)' % (q([x['r'] for x in rec], .01), q([x['r'] for x in rec], .05), q([x['r'] for x in rec], .5), 100 * sum(1 for x in rec if x['r'] <= -2) / len(rec)))
Ls.append('')
Ls.append('VOLATILITY CHECK over the final 300 s, %d markets: server sigma at tau 120 vs realized 1-s RMS vol of BRTI (spot) and of the composite index (idx), bps/sqrt s' % len(vol))
if vol:
    rb = [v['vBrti'] / v['sigma120'] for v in vol]; ri = [v['vIdx'] / v['sigma120'] for v in vol]; rbi = [v['vBrti'] / v['vIdx'] for v in vol]
    Ls.append('  ratio realized BRTI vol / server sigma: p10 %.2f p50 %.2f p90 %.2f | realized idx vol / server sigma: p50 %.2f | BRTI vol / idx vol: p10 %.2f p50 %.2f p90 %.2f' % (q(rb, .1), q(rb, .5), q(rb, .9), q(ri, .5), q(rbi, .1), q(rbi, .5), q(rbi, .9)))
    for g, lab in [((0, 1), 'quiet 0-1'), ((2, 3), 'normal 2-3'), ((4, 6), 'active 4-6')]:
        sub = [v for v in vol if v.get('regime') is not None and g[0] <= v['regime'] <= g[1]]
        if sub: Ls.append('  regime %s: n %d, BRTI/sigma p50 %.2f, idx/sigma p50 %.2f, BRTI/idx p50 %.2f' % (lab, len(sub), st.median([v['vBrti'] / v['sigma120'] for v in sub]), st.median([v['vIdx'] / v['sigma120'] for v in sub]), st.median([v['vBrti'] / v['vIdx'] for v in sub])))
open(sys.argv[1], 'w').write('\n'.join(Ls) + '\n'); print('\n'.join(Ls))
