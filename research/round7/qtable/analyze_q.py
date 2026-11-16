"""Read the exceedance table and print: Q_all(R,h) at selected R; R*(h) for theta in {0.1, 0.05, 0.025} % (two-sided, i.e. conservative);
per-year stability; per-volatility-bucket exceedance at fixed R (does recent calm predict fewer large moves at the horizons that matter?).
usage: python3 -I analyze_q.py <q.json> <out.txt>"""
import sys, json, math
d = json.load(open(sys.argv[1])); H = d['H']; ex = d['exceed']; tot = d['totals']
def Q(h, b, R): return ex['%d|%s' % (h, b)][R] / tot['%d|%s' % (h, b)] if tot['%d|%s' % (h, b)] else float('nan')
def rstar(h, b, theta):
    e = ex['%d|%s' % (h, b)]; n = tot['%d|%s' % (h, b)]
    for R in range(len(e)):
        if e[R] <= theta * n: return R
    return None
out = []; P = out.append
P('EXCEEDANCE TABLE Q(R,h) = P(|settlement-mean move over horizon h| >= R bps), usdc 1-s closes %s..%s (two-sided)' % (d['from'], d['to']))
P('seconds per horizon: ' + ', '.join('h=%d: %d' % (h, tot['%d|all' % h]) for h in H[::4]))
RS = [5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200]
P('  h   | ' + ''.join('R>=%-4d   ' % R for R in RS))
for h in H: P('  %3d | ' % h + ''.join('%8.4f%% ' % (100 * Q(h, 'all', R)) for R in RS))
P(''); P('R*(h) = smallest R with Q(R,h) <= theta  [all years | 2023 | 2024 | 2025 | 2026(Jan-Aug)]')
for theta in (0.002, 0.001, 0.0005, 0.00025):
    P('  theta = %.3f %%: ' % (100 * theta) + ' '.join('h%d:%s' % (h, '/'.join(str(rstar(h, b, theta)) for b in ('all', 'y2023', 'y2024', 'y2025', 'y2026'))) for h in H))
P(''); P('BY ENGINE-LIKE VOLATILITY BUCKET (sigma at t; c0 = calmest): Q(R,h) at the horizons of the owner\'s rule and inside the minute')
for h in (120, 90, 60, 30, 10):
    P('  h=%d seconds: ' % h + ' | '.join('%s n=%d' % (b, tot['%d|%s' % (h, b)]) for b in ('c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6')))
    for R in (10, 15, 20, 30, 45, 60, 90):
        P('    R>=%3d: ' % R + ' | '.join('%9.4f%%' % (100 * Q(h, b, R)) for b in ('c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6')))
P(''); P('CALM (rms120-only sigma < 0.22 %/15min) vs NOT CALM: Q(R,h)')
for h in (120, 90, 60, 30):
    P('  h=%d: ' % h + ', '.join('R>=%d: calm %.4f%% notcalm %.4f%%' % (R, 100 * Q(h, 'calm', R), 100 * Q(h, 'notcalm', R)) for R in (15, 20, 30, 45, 60)))
open(sys.argv[2], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
