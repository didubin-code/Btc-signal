import math, random
from math import lgamma, exp, log
def lchoose(n, k): return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
def hyper_ge(k, n_live, k_hist, n_hist):
    """one-sided Fisher: P(losses in the live sample >= k | total losses K=k+k_hist fixed, sizes fixed)"""
    K = k + k_hist; N = n_live + n_hist
    return sum(exp(lchoose(n_live, j) + lchoose(n_hist, K - j) - lchoose(N, K)) for j in range(k, min(K, n_live) + 1))
def pois_ge(k, lam): return 1 - sum(exp(-lam) * lam ** i / math.factorial(i) for i in range(k))
def binom_ge(k, n, p): return 1 - sum(exp(lchoose(n, j) + j * log(p) + (n - j) * log(1 - p)) for j in range(k))
def betabinom_ge(k, n, a, b):
    """predictive P(X >= k) for X ~ BetaBinomial(n, a, b)"""
    return 1 - sum(exp(lchoose(n, j) + lgamma(j + a) + lgamma(n - j + b) - lgamma(n + a + b) + lgamma(a + b) - lgamma(a) - lgamma(b)) for j in range(k))
print('=== (b) live [90,120] 2 of 417 vs historical cohorts: record (Poisson, plug-in rate) | exact two-sample Fisher one-sided | Bayesian predictive (Jeffreys Beta(k+.5, n-k+.5) on the historical rate)')
for lab, kh, nh in (('ORIGINAL unscaled year 0/7281', 0, 7281), ('comparable Sep-Nov 3/2165', 3, 2165), ('comparable full-year 4/9621', 4, 9621), ('threshold-eq Sep-Nov 2/1945', 2, 1945), ('threshold-eq year 2/8675', 2, 8675), ('cushion>=15 Sep-Nov 1/1571', 1, 1571), ('cushion>=15 year 1/7458', 1, 7458)):
    rate = kh / nh; lam = 417 * rate
    print('  %-32s Poisson plug-in P=%-7s | Fisher P=%.4f | predictive P=%.4f | Fisher x4 bins=%.3f' % (lab, ('%.4f' % pois_ge(2, lam)) if kh else 'undef', hyper_ge(2, 417, kh, nh), betabinom_ge(2, 417, kh + .5, nh - kh + .5), min(1, 4 * hyper_ge(2, 417, kh, nh))))
print('  record used upper95 0.041%% as plug-in for the 0/7281 case: P=%.4f; the exact Fisher P for 2/417 vs 0/7281 is %.4f (= C(417,2)/C(7698,2))' % (pois_ge(2, 417 * 0.000411), hyper_ge(2, 417, 0, 7281)))
print('=== disjoint live part only (Nov 13-16: 2 of 126; the 291 Nov 2-12 live entries are the same windows as part of the comparable cohort)')
for lab, kh, nh in (('comparable Sep-Nov 3/2165', 3, 2165), ('comparable full-year 4/9621', 4, 9621), ('unscaled year 0/7281', 0, 7281), ('cushion>=15 Sep-Nov 1/1571', 1, 1571)):
    print('  %-32s Poisson P=%.4f | Fisher P=%.4f | predictive P=%.4f' % (lab, pois_ge(2, 126 * kh / nh) if kh else float('nan'), hyper_ge(2, 126, kh, nh), betabinom_ge(2, 126, kh + .5, nh - kh + .5)))
print('=== cushion cell 15-20 bps at [90,120]: live 2 of 20 (cushions known for 129 of 417 live entries only)')
for lab, kh, nh in (('comparable year 0/2068', 0, 2068), ('comparable Sep-Nov 0/524', 0, 524), ('unscaled year 0/1644', 0, 1644)):
    print('  %-28s Fisher P=%.2e (x20 cells = %.4f) | record-style plug-in of the upper95 bound: P=%.4f | if the whole 417 had the Nov 12-16 composition (2 of ~65): Fisher P=%.2e' % (lab, hyper_ge(2, 20, kh, nh), min(1, 20 * hyper_ge(2, 20, kh, nh)), pois_ge(2, 20 * (1 - 0.05 ** (1 / nh))), hyper_ge(2, 65, kh, nh)))
print('=== (c) period change, two-sample exact (Fisher one-sided) vs the record\'s plug-in Poisson')
for lab, ka, na, kb, nb in (('all bins Jan-Aug 17/19833 vs Sep-Nov 11/6396', 17, 19833, 11, 6396), ('30-89 s 4/11192 vs 6/3590', 4, 11192, 6, 3590), ('comparable [90,120] 1/7456 vs 3/2165', 1, 7456, 3, 2165)):
    print('  %-48s plug-in Poisson P=%.4f | Fisher P=%.4f' % (lab, pois_ge(kb, nb * ka / na), hyper_ge(kb, nb, ka, na)))
print('=== (d) discriminator v2: exact sequential error probabilities (binomial increments; looks at 400/800/1600; reject K>=3/4/6; accept K<=2 at look 3)')
def seq(p):
    # distribution of K after each look; state = K among continuing paths
    from functools import lru_cache
    def binpmf(n, j): return exp(lchoose(n, j) + j * log(p) + (n - j) * log(1 - p))
    dist = {0: 1.0}; rej = [0, 0, 0]
    for li, (n, thr) in enumerate(((400, 3), (400, 4), (800, 6))):
        new = {}
        for k, pr in dist.items():
            for j in range(0, n + 1):
                q = pr * binpmf(n, j)
                if q < 1e-15: 
                    if j > 20: break
                    continue
                new[k + j] = new.get(k + j, 0) + q
        dist = {}
        for k, pr in new.items():
            if k >= thr: rej[li] += pr
            else: dist[k] = dist.get(k, 0) + pr
    acc = sum(pr for k, pr in dist.items() if k <= 2); unres = sum(pr for k, pr in dist.items() if k > 2)
    return rej, acc, unres
for p in (0.00013, 0.00042, 0.00064, 0.0014, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.007):
    rej, acc, unres = seq(p)
    print('  p=%.4f  reject by look: %.3f %.3f %.3f (total %.3f)  accept %.3f  unresolved %.3f  | single-look checks: P(K>=3|400)=%.4f P(K>=4|800)=%.4f P(K>=6|1600)=%.4f P(K<=2|1600)=%.3f' % (p, rej[0], rej[0] + rej[1], sum(rej), sum(rej), acc, unres, binom_ge(3, 400, p), binom_ge(4, 800, p), binom_ge(6, 1600, p), 1 - binom_ge(3, 1600, p)))
# predictive error rates integrating over the uncertainty of p0 (3 of 2165, Jeffreys) and of p1 (2 of 417)
random.seed(3)
def beta_sample(a, b):
    x = random.gammavariate(a, 1); y = random.gammavariate(b, 1); return x / (x + y)
for lab, a, b in (('p0 ~ posterior of 3/2165', 3.5, 2162.5), ('p0 ~ posterior of 4/9621', 4.5, 9617.5), ('p ~ posterior of live 2/417', 2.5, 415.5)):
    R = A = U = 0; M = 400
    for _ in range(M):
        pp = beta_sample(a, b); rej, acc, unres = seq(pp); R += sum(rej); A += acc; U += unres
    print('  %-28s averaged over the posterior: reject %.3f accept %.3f unresolved %.3f' % (lab, R / M, A / M, U / M))
print('=== (e) live calibration O/E with exact Poisson 95%% intervals (from live_check2): all 3/1.948 -> O/E 1.54 [0.32, 4.50]; [90,120] 2/0.510 -> 3.92 [0.47, 14.2]; tau<90 1/1.438 -> 0.70 [0.02, 3.87]')
print('=== record arithmetic checks: P(>=2|417*0.001386)=%.4f  x4=%.3f ; P(>=2|417*0.000416)=%.4f x4=%.3f ; P(>=2|126*0.001386)=%.4f ; P(>=2|417*0.000637)=%.4f ; P(>=2|417*0.000134)=%.4f ; P(>=3|1.95)=%.3f ; P(>=2|0.51)=%.3f' % (pois_ge(2, 417 * 3 / 2165), 4 * pois_ge(2, 417 * 3 / 2165), pois_ge(2, 417 * 4 / 9621), 4 * pois_ge(2, 417 * 4 / 9621), pois_ge(2, 126 * 3 / 2165), pois_ge(2, 417 / 1571), pois_ge(2, 417 / 7458), pois_ge(3, 1.95), pois_ge(2, 0.51)))
print('  P(>=3 of 2000 | full-year comparable 0.042%%)=%.3f ; P(>=3 of 2000 | unscaled upper 0.041%%)=%.3f ; P(<=1 of 2000 | 0.48%% live)=%.4f' % (pois_ge(3, 2000 * 0.00042), pois_ge(3, 2000 * 0.00041), 1 - pois_ge(2, 2000 * 0.0048)))
