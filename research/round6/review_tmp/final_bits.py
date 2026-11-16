from math import lgamma, exp, log
def lchoose(n, k): return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
def hyper_ge(k, n_b, k_a, n_a):
    Kt = k + k_a; Nt = n_a + n_b
    return sum(exp(lchoose(n_b, j) + lchoose(n_a, Kt - j) - lchoose(Nt, Kt)) for j in range(k, min(Kt, n_b) + 1))
def cp_upper(k, n):
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(exp(lchoose(n, j) + j * log(p) + (n - j) * log(1 - p)) for j in range(k + 1))
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
print('disjoint windows only: live Nov 13-16 2/126 vs comparable Sep-Nov minus the 289 shared windows 3/1876: Fisher P=%.4f | vs year minus shared 4/9332: P=%.4f | vs unscaled year minus its ~250 shared 0/7031: P=%.4f' % (hyper_ge(2, 126, 3, 1876), hyper_ge(2, 126, 4, 9332), hyper_ge(2, 126, 0, 7031)))
print('CP upper95 for 3/2165 = %.3f%% ; for 4/9621 = %.3f%% ; for 2/417 = %.2f%% ; for 2/126 = %.2f%%' % (100 * cp_upper(3, 2165), 100 * cp_upper(4, 9621), 100 * cp_upper(2, 417), 100 * cp_upper(2, 126)))
print('Nov 1-12 replay all bins 6/1043 vs Jan-Oct 22/25186: Fisher P=%.5f ; Nov 1 alone 3 losses in one day' % hyper_ge(6, 1043, 22, 25186))
print('live all bins Nov 2-16 3/1248 vs replay Nov 1-12 6/1043: Fisher (live higher) P=%.3f ; live vs replay Jan-Oct 22/25186: P=%.3f' % (hyper_ge(3, 1248, 6, 1043), hyper_ge(3, 1248, 22, 25186)))
print('expected live losses at [90,120] if H1 p=0.5%% over 417 entries: %.2f; observed 2' % (417 * 0.005))
