#!/usr/bin/env python3
import sys, json, os, collections, statistics
E = sys.argv[1]
rows = []
for fn in sorted(os.listdir(E)):
    if fn.endswith('.ndjson') and fn.startswith('usdc'):
        with open(os.path.join(E, fn)) as f:
            for ln in f: rows.append(json.loads(ln))
print('usdc windows', len(rows))
def q(xs, ps):
    xs = sorted(xs); n = len(xs)
    return [round(xs[min(n-1, int(p*n))], 4) for p in ps]
for rule in ('R_disp', 'R_exact', 'R_lock', 'R_01', 'R_pfc'):
    ents = [r['entries'][rule] for r in rows if r['entries'][rule]]
    losses = [e for e in ents if not e['won']]
    print('%-8s entries=%d losses=%d sum_pf=%.2f median_tau=%s' % (rule, len(ents), len(losses), sum(e['pf'] for e in ents), statistics.median(e['tau'] for e in ents)))
ents = [r['entries']['R_disp'] for r in rows if r['entries']['R_disp']]
ps = [0.01, 0.05, 0.1, 0.2, 0.25, 0.4, 0.5, 0.6, 0.75, 0.8, 0.9, 0.95, 0.99]
print('quantiles', ps)
for k in ('mu', 'mu_bps', 'sig', 'cushion_bps', 'cushion_usd', 'tau', 'pf', 'pfc', 'secs_since_first_locked', 'lock_streak_s'):
    xs = [e[k] for e in ents if e[k] is not None]
    print('%-26s n=%d  %s' % (k, len(xs), q(xs, ps)))
for k in ('dc10_bps', 'dc20_bps'):
    xs = [e[k] for e in ents if e[k] is not None]
    print('%-26s n=%d (null=%d) %s' % (k, len(xs), len(ents) - len(xs), q(xs, ps)))
print('bk counts', collections.Counter(e['bk'] for e in ents))
print('soft>0', sum(1 for e in ents if e['soft'] > 0), 'hard>0', sum(1 for e in ents if e['hard'] > 0))
print('state at entry', collections.Counter(e['st'] for e in ents))
print('entry_is_scan_start', sum(1 for e in ents if e['entry_is_scan_start']))
print('cushion<=0 at entry', sum(1 for e in ents if e['cushion_usd'] <= 0))
print('mu sign: neg', sum(1 for e in ents if e['mu'] < 0), 'zero', sum(1 for e in ents if e['mu'] == 0), 'pos', sum(1 for e in ents if e['mu'] > 0))
print('tau bins', collections.Counter(('120' if e['tau'] >= 119 else '90-119' if e['tau'] >= 90 else '60-89' if e['tau'] >= 60 else '30-59' if e['tau'] >= 30 else '<30') for e in ents))
print('losses by tau bin', collections.Counter(('120' if e['tau'] >= 119 else '90-119' if e['tau'] >= 90 else '60-89' if e['tau'] >= 60 else '30-59' if e['tau'] >= 30 else '<30') for e in ents if not e['won']))
print('losses:'); 
for r in rows:
    e = r['entries']['R_disp']
    if e and not e['won']:
        print('  %s %s tau=%.2f side=%s truth=%s cush=%.1fbps pf=%.5f sig=%.3f bk=%d dc20=%s min_c=%.1f cross=%s class=%s margin=%.2f mu=%.2f' % (r['chunk'], r['ticker'], e['tau'], e['side'], r['truth'], e['cushion_bps'], e['pf'], e['sig'], e['bk'], e['dc20_bps'], e['min_c_bps'], e['crossed'], e['loss_class'], r['marginUsd'], e['mu']))
