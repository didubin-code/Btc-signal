"""Decompose why the exact <= 0.2 % threshold was crossed (owner Q1), using the live server's own model via model_probe.js.
For a market: rows (1 Hz, final 300 s) from the scoreboard; mu from the tape's basisMu (else -3.4). Reference row = first row with
tau <= 120 (tau ~119.6); entry row = first LOCKED row with pFlip <= 0.002. Reproduction check: model pf vs recorded pFlip on every
row from the reference to the entry. Shapley decomposition of ln(pf_entry / pf_ref) over the four inputs that changed: tau (clock and
settlement-averaging units), gap (cushion), sigma (volatility estimate), bucket (regime -> recalibration ratio); S (index level) and mu
are held at the entry values (their effect is negligible and reported separately). Output: JSON + text per market."""
import json, glob, os, sys, math, itertools, subprocess
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R3 = SC + '/round3'
F = SC + '/r30_pkg/r30/release_identity/I2/pinradar_server.js'; PROBE = SC + '/round4/decomp/model_probe.js'
def model(inputs):
    tmp = SC + '/round4/decomp/_in.json'; json.dump(inputs, open(tmp, 'w'))
    out = subprocess.run(['node', PROBE, F, tmp], capture_output=True, text=True, timeout=120).stdout.strip().split('\n')
    return json.loads(out[-1])
mu_tape = {}
for l in open(R3 + '/tape/tape_all.ndjson'):
    try: r = json.loads(l)
    except Exception: continue
    tk = (r.get('kal') or {}).get('ticker')
    if tk and r.get('basisMu') is not None and tk not in mu_tape: mu_tape[tk] = r['basisMu']
def units(t, W=60):
    u = sorted(x for x in (t - j for j in range(W)) if x > 1e-9); n = len(u)
    return sum(u[i] * (2 * (n - 1 - i) + 1) for i in range(n)) / (W * W), n
res_all = {}
for tk in sys.argv[1:]:
    rs = sorted((json.loads(x) for x in open('%s/scoreboard/rows/%s.ndjson' % (L, tk)) if x.strip()), key=lambda r: -r['tau'])
    rs = [r for r in rs if r.get('tau') is not None and r.get('gap') is not None and r.get('sigma') and r.get('idx')]
    mu = mu_tape.get(tk, -3.4)
    ref = next(r for r in rs if r['tau'] <= 120.5)
    ent = next(r for r in rs if 0 < r['tau'] <= 120 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and r['pFlip'] <= 0.002)
    seg = [r for r in rs if ent['tau'] <= r['tau'] <= ref['tau']]
    inp = [{'tau': r['tau'], 'gap': r['gap'], 'sigma': r['sigma'], 'S': r['idx'], 'mu': mu, 'bucket': r['regime'], 'rec': r['pFlip']} for r in seg]
    out = model(inp)
    err = [abs(math.log(o['model']['pf'] / o['rec'])) for o in out if o['rec'] and o['model']['pf']]
    # Shapley over the 4 factors between ref (0) and entry (1) states
    X0 = {'tau': ref['tau'], 'gap': ref['gap'], 'sigma': ref['sigma'], 'bucket': ref['regime']}; X1 = {'tau': ent['tau'], 'gap': ent['gap'], 'sigma': ent['sigma'], 'bucket': ent['regime']}
    factors = ['tau', 'gap', 'sigma', 'bucket']; combos = []
    for k in range(5):
        for sub in itertools.combinations(factors, k): combos.append(sub)
    inputs = [dict(tau=(X1 if 'tau' in c else X0)['tau'], gap=(X1 if 'gap' in c else X0)['gap'], sigma=(X1 if 'sigma' in c else X0)['sigma'], bucket=(X1 if 'bucket' in c else X0)['bucket'], S=ent['idx'], mu=mu, combo='|'.join(c)) for c in combos]
    vals = {o['combo']: math.log(max(o['model']['pf'], 1e-12)) for o in model(inputs)}
    shap = {}
    for f in factors:
        s = 0.0
        for c in combos:
            if f in c: continue
            k = len(c); w = math.factorial(k) * math.factorial(4 - k - 1) / math.factorial(4)
            s += w * (vals['|'.join(sorted(c + (f,), key=factors.index))] - vals['|'.join(c)])
        shap[f] = s
    total = vals['|'.join(factors)] - vals['']
    un0, n0 = units(ref['tau']); un1, n1 = units(ent['tau'])
    sgn = 1 if ent['side'] == 'UP' else -1
    cush = {'usd': sgn * ent['gap'] + sgn * mu, 'bps': (sgn * ent['gap'] + sgn * mu) / ent['strike'] * 1e4, 'requiredMoveUsd': abs(sgn * ent['gap'] + sgn * mu) * 60 / max(n1, 1),
            'ref_usd': sgn * ref['gap'] + sgn * mu}
    res = {'ticker': tk, 'mu': mu, 'ref': {'tau': ref['tau'], 'gap': ref['gap'], 'sigma': ref['sigma'], 'bucket': ref['regime'], 'pFlip_rec': ref['pFlip'], 'state': ref['state'], 'units': un0},
           'entry': {'tau': ent['tau'], 'gap': ent['gap'], 'sigma': ent['sigma'], 'bucket': ent['regime'], 'pFlip_rec': ent['pFlip'], 'pFlipCons_rec': ent.get('pFlipCons'), 'ask': ent.get('ask'), 'units': un1, 'ref_field': ent.get('ref'), 'offPUp': ent.get('offPUp')},
           'reproduction': {'rows': len(out), 'median_abs_log_err': sorted(err)[len(err) // 2] if err else None, 'max_abs_log_err': max(err) if err else None, 'pf_model_entry': out[-1]['model']['pf'], 'pf_model_ref': out[0]['model']['pf']},
           'ln_change_total': total, 'shapley_ln': shap, 'shapley_share': {k: v / total for k, v in shap.items()} if total else None, 'cushion_entry': cush,
           'per_row': [{'tau': o['tau'], 'rec': o['rec'], 'model': round(o['model']['pf'], 6), 'gap': o['gap'], 'sigma': o['sigma'], 'bucket': o['bucket']} for o in out]}
    res_all[tk] = res
    print('%s: mu %.2f | ref tau %.1f gap %.1f sigma %.4f bk %s pf %.5f (model %.5f) | entry tau %.1f gap %.1f sigma %.4f bk %s pf %.5f (model %.5f) ask %s | reproduction: %d rows, median |ln err| %.3f, max %.3f' % (
        tk, mu, ref['tau'], ref['gap'], ref['sigma'], ref['regime'], ref['pFlip'], out[0]['model']['pf'], ent['tau'], ent['gap'], ent['sigma'], ent['regime'], ent['pFlip'], out[-1]['model']['pf'], ent.get('ask'), len(out), res['reproduction']['median_abs_log_err'] or 0, res['reproduction']['max_abs_log_err'] or 0))
    print('   ln(pf_entry/pf_ref) = %.3f (factor %.2f): Shapley shares: ' % (total, math.exp(total)) + ', '.join('%s %.3f (%.0f %%)' % (k, shap[k], 100 * shap[k] / total if total else 0) for k in factors))
    print('   cushion at entry: %.1f USD, %.2f bps, required move over remaining prints %.1f USD (ref cushion %.1f USD); units(tau) %.1f -> %.1f' % (cush['usd'], cush['bps'], cush['requiredMoveUsd'], cush['ref_usd'], un0, un1))
json.dump(res_all, open(SC + '/round4/decomp/decomp_results.json', 'w'), indent=1)
