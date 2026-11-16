"""Diagnostic (not a validated candidate): at each live exact-rule entry, the ratio k_pre of realized 1-s BRTI volatility to the server's
sigma, measured only on rows BEFORE the entry within the final 300 s (information available at entry), and the model pf recomputed with
sigma * max(1, k_pre). Reports how many entries would then exceed 0.2 % / 0.25 %, and the two losses' corrected pf. Also k over the
full final 300 s (not available at entry; for reference)."""
import json, glob, os, sys, math, subprocess, statistics as st
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R3 = SC + '/round3'
F = SC + '/r30_pkg/r30/release_identity/I2/pinradar_server.js'; PROBE = SC + '/round4/decomp/model_probe.js'
def model(inputs):
    tmp = SC + '/round4/decomp/_in2.json'; json.dump(inputs, open(tmp, 'w'))
    out = subprocess.run(['node', PROBE, F, tmp], capture_output=True, text=True, timeout=300).stdout.strip().split('\n'); return json.loads(out[-1])
mu_tape = {}
for l in open(R3 + '/tape/tape_all.ndjson'):
    try: r = json.loads(l)
    except Exception: continue
    tk = (r.get('kal') or {}).get('ticker')
    if tk and r.get('basisMu') is not None and tk not in mu_tape: mu_tape[tk] = r['basisMu']
mk = {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(L + '/scoreboard/markets/*.json')}
def rms(xs):
    d = [math.log(b[1] / a[1]) * 1e4 / math.sqrt(max(0.25, a[0] - b[0])) for a, b in zip(xs, xs[1:]) if a[0] > b[0] and a[1] > 0 and b[1] > 0]
    return math.sqrt(sum(x * x for x in d) / len(d)) if len(d) >= 30 else None
inputs = []; meta = []
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; m = mk.get(tk)
    if not m or m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rs = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau']); rs = [r for r in rs if r.get('tau') is not None]
    e = next((r for r in rs if 0 < r['tau'] <= 120 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and r['pFlip'] <= 0.002 and r.get('gap') is not None and r.get('sigma') and r.get('idx')), None)
    if not e: continue
    pre = [(r['tau'], r['spot']) for r in rs if r['tau'] > e['tau'] and r.get('spot')]; pre_idx = [(r['tau'], r['idx']) for r in rs if r['tau'] > e['tau'] and r.get('idx')]
    allb = [(r['tau'], r['spot']) for r in rs if r.get('spot')]
    vb_pre, vi_pre, vb_all = rms(pre), rms(pre_idx), rms(allb)
    k_pre = (vb_pre / e['sigma']) if vb_pre else None
    mu = mu_tape.get(tk, -3.4)
    inputs.append({'tau': e['tau'], 'gap': e['gap'], 'sigma': e['sigma'] * max(1.0, k_pre or 1.0), 'S': e['idx'], 'mu': mu, 'bucket': e['regime'], 'k': k_pre or 1.0, 'tk': tk})
    meta.append({'tk': tk, 'won': e['side'] == truth, 'tau': e['tau'], 'pf': e['pFlip'], 'sigma': e['sigma'], 'k_pre': k_pre, 'k_all': (vb_all / e['sigma']) if vb_all else None, 'vb_pre': vb_pre, 'vi_pre': vi_pre, 'n_pre': len(pre), 'regime': e['regime']})
out = model(inputs)
for mt, o in zip(meta, out): mt['pf_corr'] = o['model']['pf']
L_ = ['VOLATILITY-CORRECTED ENTRY DIAGNOSTIC: %d live exact-rule entries' % len(meta)]
ks = [m['k_pre'] for m in meta if m['k_pre']]; L_.append('k_pre = realized BRTI 1-s vol before entry / server sigma at entry: p10 %.2f p50 %.2f p90 %.2f (n %d); k over the whole final 300 s p50 %.2f' % (sorted(ks)[len(ks)//10], st.median(ks), sorted(ks)[9*len(ks)//10], len(ks), st.median([m['k_all'] for m in meta if m['k_all']])))
for thr, lab in ((0.002, 'exact 0.2 %'), (0.0025, 'displayed < 0.25 %')):
    keep = [m for m in meta if m['pf_corr'] <= thr] if thr == 0.002 else [m for m in meta if m['pf_corr'] < thr]
    L_.append('with sigma x max(1, k_pre): entries still qualifying at %s: %d of %d (%.0f %%); losses among them: %d of 2' % (lab, len(keep), len(meta), 100 * len(keep) / len(meta), sum(1 for m in keep if not m['won'])))
for m in meta:
    if not m['won']: L_.append('  LOSS %s tau %.1f: recorded pf %.5f, sigma %.4f, k_pre %.2f (BRTI vol pre %.3f, idx vol pre %.3f, n %d rows), corrected pf %.5f' % (m['tk'][-13:], m['tau'], m['pf'], m['sigma'], m['k_pre'] or 0, m['vb_pre'] or 0, m['vi_pre'] or 0, m['n_pre'], m['pf_corr']))
# distribution of corrected pf among winners
pw = sorted(m['pf_corr'] for m in meta if m['won']); L_.append('corrected pf among winners: p50 %.5f p90 %.5f p99 %.5f; share > 0.2 %%: %.0f %%' % (pw[len(pw)//2], pw[9*len(pw)//10], pw[99*len(pw)//100], 100 * sum(1 for x in pw if x > 0.002) / len(pw)))
open(SC + '/round4/decomp/vol_check_entry.txt', 'w').write('\n'.join(L_) + '\n'); print('\n'.join(L_))
