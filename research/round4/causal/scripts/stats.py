"""Small deterministic statistics helpers (no scipy)."""
import math

def _log_binom_pmf(n, k, p):
    if p <= 0: return 0.0 if k == 0 else -math.inf
    if p >= 1: return 0.0 if k == n else -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log1p(-p)

def binom_cdf(n, k, p):
    """P(X <= k) for X ~ Bin(n, p), summing k+1 terms (k small in our use)."""
    if k < 0: return 0.0
    if k >= n: return 1.0
    return min(1.0, sum(math.exp(_log_binom_pmf(n, x, p)) for x in range(0, k + 1)))

def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided binomial CI by bisection on the binomial CDF."""
    if n == 0: return (None, None)
    if k == 0: lo = 0.0
    else:
        a, b = 0.0, 1.0
        for _ in range(200):           # find p with P(X >= k | p) = alpha/2  <=>  P(X <= k-1 | p) = 1 - alpha/2
            m = (a + b) / 2
            if binom_cdf(n, k - 1, m) > 1 - alpha / 2: a = m
            else: b = m
        lo = (a + b) / 2
    if k == n: hi = 1.0
    else:
        a, b = 0.0, 1.0
        for _ in range(200):           # find p with P(X <= k | p) = alpha/2
            m = (a + b) / 2
            if binom_cdf(n, k, m) > alpha / 2: a = m
            else: b = m
        hi = (a + b) / 2
    return (lo, hi)

def binom_test_two_sided_ge(k, n, p0):
    """One-sided exact p-value P(X >= k | p0) (used for 'more losses than expected' checks)."""
    return 1.0 - binom_cdf(n, k - 1, p0)

def quantile(xs, q):
    """Deterministic empirical quantile (linear interpolation on sorted values)."""
    xs = sorted(xs); n = len(xs)
    if n == 0: return None
    if n == 1: return xs[0]
    pos = q * (n - 1); i = int(math.floor(pos)); f = pos - i
    return xs[i] if i + 1 >= n else xs[i] * (1 - f) + xs[i + 1] * f

def median(xs):
    return quantile(xs, 0.5)

def mean(xs):
    xs = list(xs); return sum(xs) / len(xs) if xs else None

def pstdev(xs):
    xs = list(xs); m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) if xs else None

def fmt_rate(k, n):
    if n == 0: return 'n/a'
    if k == 0: return '0 (none)'
    return '1 in %.0f' % (n / k)

def fmt_ci(k, n):
    lo, hi = clopper_pearson(k, n)
    if lo is None: return 'n/a'
    return '[%.3f%%, %.3f%%]' % (100 * lo, 100 * hi)
