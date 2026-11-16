"""Joint distribution of (cushion bin, engine sigma bucket) for LOCKED pf<=0.002 rows at 90 <= tau <= 120, FIT traces (bk field) vs live rows (regime field),
and losses per cell (windows). Shows whether the live entries occupied input regions absent from FIT."""
import sys, json, gzip, glob, os, collections
RP = sys.argv[1]; L = sys.argv[2]
CB = [('<10', 0, 10), ('10-15', 10, 15), ('15-20', 15, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('>=45', 45, 1e9)]
def cb(g): return next(n for n, lo, hi in CB if lo <= g < hi)
win = {}
for f in glob.glob(RP + '/out_full_mu/usdc_0[1-8].ndjson'):
    for l in open(f):
        if l.strip():
            r = json.loads(l)
            if r.get('truth') and r.get('strike'): win[r['ticker']] = (r['truth'], float(r['strike']))
fit = collections.defaultdict(lambda: [set(), set()])
for f in sorted(glob.glob(RP + '/out_full_mu/usdc_0[1-8].trace.ndjson.gz')):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l); tk = r['tk']
        if tk not in win or not (90 <= r['tau'] <= 120) or r.get('st') not in ('LOCKED', 'PROVEN LOCKED') or r.get('pf') is None or r['pf'] > 0.002 or r.get('gap') is None: continue
        ce = r['gap'] + (r.get('mu') or 0); g = abs(ce) / win[tk][1] * 1e4; c = fit[(cb(g), r.get('bk'))]; c[0].add(tk)
        if (('UP' if ce > 0 else 'DOWN') != win[tk][0]): c[1].add(tk)
live = collections.defaultdict(lambda: [set(), set()]); sig = collections.defaultdict(list)
for p in glob.glob(L + '/scoreboard/rows/*.ndjson'):
    tk = os.path.basename(p)[:-7]; mp = L + '/scoreboard/markets/' + tk + '.json'
    if not os.path.exists(mp): continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    for l in open(p):
        r = json.loads(l)
        if not (90 <= r['tau'] <= 120) or r.get('state') not in ('LOCKED', 'PROVEN LOCKED') or r.get('pFlip') is None or r['pFlip'] > 0.002 or r.get('gap') is None: continue
        g = abs(r['gap']) / r['strike'] * 1e4; c = live[(cb(g), r.get('regime'))]; c[0].add(tk); sig[r.get('regime')].append(r['sigma'])
        if (('UP' if r['gap'] > 0 else 'DOWN') != truth): c[1].add(tk)
bks = sorted(set(k[1] for k in list(fit) + list(live)), key=lambda x: (x is None, x))
print('LOCKED pf<=0.002 rows at 90-120 s: windows (lost) by cushion bin x engine bucket')
print('  FIT 2026 (bk):   ' + ''.join('%-16s' % ('bk=%s' % b) for b in bks))
for n, _, _ in CB: print('  %-8s' % n + ''.join('%-16s' % ('%d (%d)' % (len(fit[(n, b)][0]), len(fit[(n, b)][1])) if (n, b) in fit else '-') for b in bks))
print('  LIVE Nov 12-16 (regime): ' + ''.join('%-16s' % ('rg=%s' % b) for b in bks))
for n, _, _ in CB: print('  %-8s' % n + ''.join('%-16s' % ('%d (%d)' % (len(live[(n, b)][0]), len(live[(n, b)][1])) if (n, b) in live else '-') for b in bks))
print('  live sigma by regime: ' + ', '.join('%s: %.3f-%.3f' % (b, min(v), max(v)) for b, v in sorted(sig.items(), key=lambda x: (x[0] is None, x[0]))))
