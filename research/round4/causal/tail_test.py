"""Realized settlement move versus the model's path law, by month and regime (round 4, owner Q2/Q3/Q4).
For each de-duplicated R_exact / R_disp entry (features from the replay analysis): side-signed basis-adjusted cushion c_eff (USD) at
entry; the model's settlement sigma at entry sigma_tot = kappa(tau) * sig * strike/1e4 * sqrt(units(tau)) (settleVarUnitsDiscrete,
W=60, align incl, as in the server); realized surprise e = side-signed final margin minus c_eff; r = e / sigma_tot.
Reports: cushion at entry in USD, bps and sigma units (settlement terms); empirical one-sided tail P(r <= -z) vs the server's path
law S(z)/2 with (A,B) interpolated in log-tau; by month, by bucket, by tau bin. Losses are exactly the entries with e < -c_eff.
usage: python3 -I tail_test.py <features ndjson> <out.txt>"""
import json, sys, math, time, collections, statistics as st
inp, outp = sys.argv[1], sys.argv[2]
KNOTS = [(3, 0.456, 0.878, 1.216), (25, 1.025, 1.739, 1.216), (130, 1.664, 2.577, 1.044)]
def law(tau):
    t = min(KNOTS[-1][0], max(KNOTS[0][0], tau)); lt = math.log(t)
    for a, b in zip(KNOTS, KNOTS[1:]):
        if t <= b[0]:
            f = (lt - math.log(a[0])) / (math.log(b[0]) - math.log(a[0])); return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3]))
    k = KNOTS[-1]; return (k[1], k[2], k[3])
def units(t, W=60):
    u = sorted(x for x in (t - j for j in range(W)) if x > 1e-9); n = len(u)
    s = sum(u[i] * (2 * (n - 1 - i) + 1) for i in range(n)); return s / (W * W), n
def surv(z, A, B): r = abs(z) / A; return (1 + r * r) ** (-B)
rows = [json.loads(l) for l in open(inp) if l.strip()]
rows = [r for r in rows if r.get('in_dedup') and r.get('sig') and r.get('strike')]
rec = []
for r in rows:
    sgn = 1 if r['side'] == 'UP' else -1
    c_eff = r.get('c_eff_usd'); 
    if c_eff is None: c_eff = r['cushion_usd'] + (r.get('mu_signed_usd') or 0)
    m_s = sgn * r['marginUsd']; e = m_s - c_eff
    A, B, kappa = law(r['tau']); un, n = units(r['tau'])
    sig_tot = kappa * r['sig'] * r['strike'] / 1e4 * math.sqrt(max(un, 1e-9))
    rec.append({'m': time.strftime('%Y-%m', time.gmtime(r['closeTs'])), 'tau': r['tau'], 'bk': r['bk'], 'c': c_eff, 'c_bps': c_eff / r['strike'] * 1e4, 'z_c': c_eff / sig_tot, 'r': e / sig_tot, 'won': r['won'], 'A': A, 'B': B, 'sig_tot': sig_tot, 'pf': r['pf'], 'req': abs(c_eff) * 60 / max(n, 1)})
L = ['TAIL TEST on %d de-duplicated entries (%s)' % (len(rec), inp.split('/')[-1])]
def q(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = math.floor(k); c = min(f + 1, len(xs) - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)
L.append('Cushion at entry (basis-adjusted): USD p10/p50/p90 %.1f / %.1f / %.1f | bps %.2f / %.2f / %.2f | in model sigma units z_c %.2f / %.2f / %.2f | required index move over the remaining prints (USD) p50 %.1f' % (
    q([x['c'] for x in rec], .1), q([x['c'] for x in rec], .5), q([x['c'] for x in rec], .9), q([x['c_bps'] for x in rec], .1), q([x['c_bps'] for x in rec], .5), q([x['c_bps'] for x in rec], .9), q([x['z_c'] for x in rec], .1), q([x['z_c'] for x in rec], .5), q([x['z_c'] for x in rec], .9), q([x['req'] for x in rec], .5)))
lost = [x for x in rec if not x['won']]
L.append('Losses: %d; their cushion USD %s; z_c %s; realized r %s' % (len(lost), [round(x['c'], 1) for x in lost], [round(x['z_c'], 2) for x in lost], [round(x['r'], 2) for x in lost]))
def tail_table(sub, label):
    out = ['  %s: n %d' % (label, len(sub))]
    for z in (2, 3, 4, 5, 6):
        emp = sum(1 for x in sub if x['r'] <= -z); mod = sum(surv(z, x['A'], x['B']) / 2 for x in sub)
        gau = sum(0.5 * math.erfc(z / math.sqrt(2)) for x in sub)
        out.append('    P(r <= -%d): empirical %d (%.4f %%), path law expects %.1f, Gaussian %.2f -> ratio emp/law %.2f' % (z, emp, 100 * emp / len(sub), mod, gau, emp / mod if mod else float('nan')))
    loss_sub = [x for x in sub if not x['won']]; exp_pf = sum(x['pf'] for x in sub)
    out.append('    losses %d vs sum pf %.2f (O/E %.2f)' % (len(loss_sub), exp_pf, len(loss_sub) / exp_pf if exp_pf else float('nan')))
    return out
L.append('ALL:'); L += tail_table(rec, 'all')
L.append('By tau bin:')
for lo, hi, lab in [(0, 30, '<30 s'), (30, 60, '30-59'), (60, 90, '60-89'), (90, 121, '90-120')]: L += tail_table([x for x in rec if lo <= x['tau'] < hi], lab)
L.append('By bucket:')
for b in range(7): L += tail_table([x for x in rec if x['bk'] == b], 'bk %d' % b)
L.append('By month (entries with tau >= 30 s):')
for m in sorted(set(x['m'] for x in rec)): L += tail_table([x for x in rec if x['m'] == m and x['tau'] >= 30], m)
L.append('By month (all entries):')
for m in sorted(set(x['m'] for x in rec)): L += tail_table([x for x in rec if x['m'] == m], m)
L.append('Substantial cushion (c_eff >= 50 USD) and tau >= 30 s, by month:')
for m in sorted(set(x['m'] for x in rec)): L += tail_table([x for x in rec if x['m'] == m and x['tau'] >= 30 and x['c'] >= 50], m)
open(outp, 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))
