"""Signed tails and volatility-normalised tails from q2. (1) up vs down exceedance at the policy horizons; (2) empirical P(z >= z0) per engine-like bucket
vs the Gaussian 2*Phi(-z0), where z = |M| / (sigma_1s * sqrt(V(h))) uses each second's own engine-like sigma: ratio >> 1 = tails fatter than the
recent-volatility Gaussian; a ratio that is much larger in calm buckets than in active ones = jumps do not scale with recent calm."""
import sys, json, math
d = json.load(open(sys.argv[1])); H = d['H']; ex = d['exceed']; tot = d['totals']; zx = d['zexceed']; zt = d['ztotals']
def Q(h, b, R): return ex['%d|%s' % (h, b)][R] / tot['%d|%s' % (h, b)]
def Phi(x): return 0.5 * math.erfc(-x / math.sqrt(2))
out = []; P = out.append
P('SIGNED EXCEEDANCE (settlement mean above now by >= R = "up"; below = "down"), fraction of all seconds')
for h in (10, 30, 60, 90, 120):
    P('  h=%3d: ' % h + ', '.join('R>=%d: up %.4f%% down %.4f%%' % (R, 100 * Q(h, 'up', R), 100 * Q(h, 'down', R)) for R in (15, 20, 30, 45, 60, 90)))
P(''); P('VOLATILITY-NORMALISED TAILS: P(|M| >= z * sigma_1s * sqrt(V(h))) per bucket, with the Gaussian 2*Phi(-z); ratio in brackets')
for h in (10, 30, 60, 90, 120):
    P('  h=%d' % h)
    for z0 in (2.0, 3.0, 4.0, 5.0, 6.0):
        g = 2 * Phi(-z0); zi = int(round(z0 / 0.05))
        P('    z>=%.0f (Gauss %.5f%%): ' % (z0, 100 * g) + ' | '.join('%s %.5f%% [x%.0f]' % (b, 100 * zx['%d|%s' % (h, b)][zi] / zt['%d|%s' % (h, b)], (zx['%d|%s' % (h, b)][zi] / zt['%d|%s' % (h, b)]) / g) for b in ('all', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6')))
open(sys.argv[2], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
