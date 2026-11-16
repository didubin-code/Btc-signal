"""R5-1: the two cohorts side by side. LIVE = observer window lines (production /predictions rows, primary rule v1: first row with
0 < tau <= 120, LOCKED or PROVEN LOCKED, pFlip <= 0.002 inclusive). REPLAY = round4/causal/features_R_exact.ndjson (usdc family,
de-duplicated; first trace row with 0 < tau <= 120, LOCKED/PROVEN, pf <= 0.002; trace rows at tau = k + 0.25, 1 Hz).
usage: python3 -I cohorts.py <observer_lines.txt> <observer_lines_nov02_nov09.txt> <features_R_exact.ndjson> <features_R_disp.ndjson> <out.txt>"""
import sys, re, json, math, collections, datetime as dt
obs1, obs2, fx, fd, outp = sys.argv[1:6]
RX = re.compile(r'\[window\] (KXBTC15M-\S+) close=(\S+) .*?coverage=(\w+) (\d+)/300s.*?primary\(pinradar-primary-v1\) (new-crossing|existing-lock|unknown-prior) at (\S+) tau=([\d.]+)s (UP|DOWN) pFlip=([\d.e-]+) (PROVEN LOCKED|LOCKED)(.*?)\| later: lostLocked=(\S+) pFlip>0.2%=(\S+) warning=(\S+) directionFlip=(\S+) observedToClose=(\S+) \| settlement=(yes|no|unknown)')
live = {}; nolines = collections.Counter()
for f in (obs1, obs2):
    for line in open(f):
        if '[window]' not in line: continue
        if 'primary=NONE' in line: nolines['primary=NONE'] += 1; continue
        if 'primary=NOT DETERMINABLE' in line: nolines['NOT DETERMINABLE'] += 1; continue
        m = RX.search(line)
        if not m: nolines['unparsed'] += 1; continue
        tk = m.group(1)
        if tk in live: nolines['repeat'] += 1; continue
        x = m.group(11); ask = re.search(r'ask=([\d.]+)c', x); size = re.search(r'sizeAtAsk=([\d.]+)', x); dep = re.search(r'askDepthUsd=([\d.]+)', x); age = re.search(r'bookAgeMs=(\d+)', x); fill = re.search(r'\$1000fillable=(\w+)', x); tc = re.search(r'timingCertain=(\w+)', x)
        live[tk] = dict(tk=tk, close=m.group(2), coverage=m.group(3), secs=int(m.group(4)), entryType=m.group(5), at=m.group(6), tau=float(m.group(7)), side=m.group(8), pf=float(m.group(9)), state=m.group(10),
                        ask=float(ask.group(1)) if ask else None, size=float(size.group(1)) if size else None, depth=float(dep.group(1)) if dep else None, bookAge=int(age.group(1)) if age else None,
                        fillable=(fill.group(1) == 'true') if fill else None, timingCertain=(tc.group(1) == 'true') if tc else None, noOffer=('NO OFFER' in x), lostLocked=m.group(12), riskUp=m.group(13), warned=m.group(14),
                        truth=('UP' if m.group(17) == 'yes' else 'DOWN' if m.group(17) == 'no' else None))
        live[tk]['won'] = (live[tk]['side'] == live[tk]['truth']) if live[tk]['truth'] else None
L = sorted(live.values(), key=lambda r: r['close'])
rep = {}; repd = {}
for l in open(fx):
    r = json.loads(l)
    if r['family'] == 'usdc' and r['in_dedup']: rep[r['ticker']] = r
for l in open(fd):
    r = json.loads(l)
    if r['family'] == 'usdc' and r['in_dedup']: repd[r['ticker']] = r
def inbin(t, lo, hi): return lo <= t <= hi
BINS = [('0-29.99', 0, 29.999), ('30-59.99', 30, 59.999), ('60-89.99', 60, 89.999), ('90-120', 90, 120.0)]
def pois_ge(k, lam): return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))
def cp_upper(k, n, conf=0.95):
    if n == 0: return 1.0
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log(1 - p)) for i in range(k + 1)) if 0 < p < 1 else (1.0 if p <= 0 else 0.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 1 - conf: lo = mid
        else: hi = mid
    return (lo + hi) / 2
out = []
P = out.append
P('COHORTS SIDE BY SIDE (written %s)' % dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'))
P('live lines: %d entries (%s .. %s); skipped: %s' % (len(L), L[0]['close'], L[-1]['close'], dict(nolines)))
P('replay exact-rule entries (usdc, dedup): %d (%s .. %s); displayed-rule: %d' % (len(rep), min(r['closeUTC'] for r in rep.values()), max(r['closeUTC'] for r in rep.values()), len(repd)))
def table(name, rows, tau_key, won_key):
    P('  %s: %d entries, %d lost' % (name, len(rows), sum(1 for r in rows if r[won_key] is False)))
    for lab, lo, hi in BINS:
        B = [r for r in rows if inbin(r[tau_key], lo, hi)]; k = sum(1 for r in B if r[won_key] is False)
        P('    tau %-9s n=%5d lost=%2d rate=%.3f%% upper95=%.3f%%' % (lab, len(B), k, 100 * k / len(B) if B else float('nan'), 100 * cp_upper(k, len(B)) if B else float('nan')))
for r in rep.values(): r['won'] = (r['side'] == r['truth'])
for r in repd.values(): r['won'] = (r['side'] == r['truth'])
P(''); P('A. FULL COHORTS, inclusive bins (the live table of round 4 split 90-119.9 and 120 apart; here [90,120] is one bin, as in the replay)')
table('LIVE Nov 2-16 (observer primary v1)', L, 'tau', 'won')
table('REPLAY exact rule, all 2026 (usdc)', list(rep.values()), 'tau', 'won')
table('REPLAY displayed rule, all 2026 (usdc)', list(repd.values()), 'tau', 'won')
cut = '2026-11-02T00:00:00Z'; cut2 = '2026-11-13T00:00:00Z'
P(''); P('B. PERIODS: replay before Nov 2 (disjoint from live) | replay Nov 2-12 (same windows as live) | live Nov 2-12 | live Nov 13-16')
table('REPLAY exact before Nov 2', [r for r in rep.values() if r['closeUTC'] < cut], 'tau', 'won')
table('REPLAY exact Nov 2-12', [r for r in rep.values() if r['closeUTC'] >= cut], 'tau', 'won')
table('LIVE Nov 2-12', [r for r in L if r['close'] < cut2], 'tau', 'won')
table('LIVE Nov 13-16', [r for r in L if r['close'] >= cut2], 'tau', 'won')
P(''); P('C. SAME WINDOWS (Nov 2-12, both cohorts available): entry agreement under the exact rule')
common_tk = [tk for tk in live if tk in rep or True]
livewin = {tk for tk in live if live[tk]['close'] < cut2}
repwin_all = set()
# all replay windows Nov 2-12 (entries or not) are not in the features file (entries only); use entries only for agreement and report the limitation
both = [tk for tk in livewin if tk in rep]; live_only = [tk for tk in livewin if tk not in rep]
rep_nov = {tk for tk, r in rep.items() if r['closeUTC'] >= cut}
rep_only = [tk for tk in rep_nov if tk not in live and live.get(tk) is None]
P('  live entries Nov 2-12: %d | replay entries Nov 2-12: %d | both entered: %d | live-only: %d | replay-only (not a live entry, or the live window had no qualifying signal): %d' % (len(livewin), len(rep_nov), len(both), len(live_only), len(rep_only)))
d = [live[tk]['tau'] - rep[tk]['tau'] for tk in both]; d.sort()
if d: P('  tau(live) - tau(replay) at the first qualifying row, both entered (n=%d): median %.2f s, p10 %.2f, p90 %.2f, min %.2f, max %.2f (positive = live earlier)' % (len(d), d[len(d) // 2], d[len(d) // 10], d[9 * len(d) // 10], d[0], d[-1]))
sides = sum(1 for tk in both if live[tk]['side'] != rep[tk]['side']); P('  side disagreements among both-entered: %d' % sides)
for lab, lo, hi in BINS:
    lv = [tk for tk in livewin if inbin(live[tk]['tau'], lo, hi)]; rv = [tk for tk in rep_nov if inbin(rep[tk]['tau'], lo, hi)]
    bb = [tk for tk in lv if tk in rep and inbin(rep[tk]['tau'], lo, hi)]
    P('    bin %-9s live entries %4d | replay entries %4d | live entries also replay entries in the same bin %4d (%.0f %%) | live entries that the replay entered later/other bin %3d | live entries the replay never entered %3d' % (lab, len(lv), len(rv), len(bb), 100 * len(bb) / max(1, len(lv)), sum(1 for tk in lv if tk in rep and not inbin(rep[tk]['tau'], lo, hi)), sum(1 for tk in lv if tk not in rep)))
P(''); P('D. SIGNIFICANCE OF THE [90,120] COMPARISON under different framings (H0 rate from the replay; one window = one observation)')
l90 = [r for r in L if inbin(r['tau'], 90, 120)]; k90 = sum(1 for r in l90 if r['won'] is False)
r90 = [r for r in rep.values() if inbin(r['tau'], 90, 120)]; kr = sum(1 for r in r90 if r['won'] is False)
r90b = [r for r in r90 if r['closeUTC'] < cut]; krb = sum(1 for r in r90b if r['won'] is False)
rd90 = [r for r in repd.values() if inbin(r['tau'], 90, 120)]; kd = sum(1 for r in rd90 if r['won'] is False)
P('  live [90,120]: %d entries, %d lost | replay exact [90,120]: %d entries, %d lost (upper95 %.3f %%) | replay exact before Nov 2: %d / %d (upper95 %.3f %%) | replay displayed [90,120]: %d / %d' % (len(l90), k90, len(r90), kr, 100 * cp_upper(kr, len(r90)), len(r90b), krb, 100 * cp_upper(krb, len(r90b)), len(rd90), kd))
for lab, rate in (('replay exact point rate (0 losses -> 0: P undefined; use upper95)', cp_upper(kr, len(r90))), ('replay displayed point rate', kd / len(rd90)), ('replay displayed upper95', cp_upper(kd, len(rd90)))):
    lam = len(l90) * rate
    P('  H0 = %s = %.4f %%: expected live losses %.3f; P(>= %d) = %.4f; Bonferroni x4 bins = %.4f' % (lab, 100 * rate, lam, k90, pois_ge(k90, lam), min(1, 4 * pois_ge(k90, lam))))
# pooled and profile
P('  POOLED all bins: live %d lost of %d; replay exact rate %.4f %% -> expected %.2f, P(>= %d) = %.3f; replay displayed rate %.4f %% -> expected %.2f, P = %.3f' % (
    sum(1 for r in L if r['won'] is False), len(L), 100 * sum(1 for r in rep.values() if r['won'] is False) / len(rep), len(L) * sum(1 for r in rep.values() if r['won'] is False) / len(rep), sum(1 for r in L if r['won'] is False), pois_ge(sum(1 for r in L if r['won'] is False), len(L) * sum(1 for r in rep.values() if r['won'] is False) / len(rep)),
    100 * sum(1 for r in repd.values() if r['won'] is False) / len(repd), len(L) * sum(1 for r in repd.values() if r['won'] is False) / len(repd), pois_ge(sum(1 for r in L if r['won'] is False), len(L) * sum(1 for r in repd.values() if r['won'] is False) / len(repd))))
# profile: expected losses per bin at replay displayed rates (the exact rule has 0 in the top bin)
P('  PROFILE (expected live losses per bin at the replay displayed-rule rates, vs observed):')
for lab, lo, hi in BINS:
    lb = [r for r in L if inbin(r['tau'], lo, hi)]; rb = [r for r in repd.values() if inbin(r['tau'], lo, hi)]
    rate = sum(1 for r in rb if r['won'] is False) / max(1, len(rb)); P('    %-9s live n=%4d observed %d expected %.2f' % (lab, len(lb), sum(1 for r in lb if r['won'] is False), len(lb) * rate))
P(''); P('E. LIVE [90,120] by period: Nov 2-12 %d entries %d lost | Nov 13-16 %d entries %d lost' % (sum(1 for r in l90 if r['close'] < cut2), sum(1 for r in l90 if r['close'] < cut2 and r['won'] is False), sum(1 for r in l90 if r['close'] >= cut2), sum(1 for r in l90 if r['close'] >= cut2 and r['won'] is False)))
P('  live [90,120] entries with entryType existing-lock: %d, new-crossing: %d; PROVEN LOCKED entries: %d' % (sum(1 for r in l90 if r['entryType'] == 'existing-lock'), sum(1 for r in l90 if r['entryType'] == 'new-crossing'), sum(1 for r in L if r['state'] == 'PROVEN LOCKED')))
P('  the three live losses: ' + ' | '.join('%s close %s tau %.1f %s pf %.4f ask %s type %s' % (r['tk'], r['close'], r['tau'], r['side'], r['pf'], r['ask'], r['entryType']) for r in L if r['won'] is False))
json.dump({'live': L, 'replay_exact_90_120': [{'ticker': r['ticker'], 'closeUTC': r['closeUTC'], 'tau': r['tau'], 'won': r['won']} for r in r90]}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
