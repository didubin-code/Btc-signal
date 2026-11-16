import json, sys, gzip, math, collections, datetime as dt
recs, trace, chunk01 = sys.argv[1:4]
win = {}; dupe = collections.Counter(); truth_bad = 0
for l in open(recs):
    if not l.strip(): continue
    r = json.loads(l); dupe[r['ticker']] += 1; win[r['ticker']] = r
    if r.get('truth') not in ('UP', 'DOWN'): truth_bad += 1
print('scaled year records: lines %d distinct tickers %d repeated %d truth not UP/DOWN %d' % (sum(dupe.values()), len(win), sum(1 for v in dupe.values() if v > 1), truth_bad))
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
first = {}; nrows = 0; rowdup = collections.Counter(); spot = {}
with open(trace) as fh:
    for l in fh:
        nrows += 1
        r = json.loads(l); tk = r['tk']
        if tk in ('KXBTC15M-26JAN131800-00', 'KXBTC15M-26JAN150000-00', 'KXBTC15M-26FEB011200-00'): spot[(tk, r['tau'])] = (r.get('sig'), r.get('pf'), r.get('st'), r.get('bk'))
        if tk not in win or not (0 < r['tau'] <= 120) or r.get('pf') is None or not isL(r.get('st')) or r['pf'] > 0.002: continue
        if tk not in first or r['tau'] > first[tk]['tau']: first[tk] = r
print('trace rows', nrows)
SPLIT = 1788220800; NOV2 = 1762041600  # 2026-11-02T00:00:00Z
cush = lambda tk, r: abs(r['gap'] + (r.get('mu') or 0)) / win[tk]['strike'] * 1e4
B90 = [(tk, r) for tk, r in first.items() if 90 <= r['tau'] <= 120]
print('scaled [90,120]: n=%d losses=%d' % (len(B90), sum(1 for tk, r in B90 if r['side'] != win[tk]['truth'])))
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
for lab, cond in (('before Sep 1', lambda tk: win[tk]['closeTs'] < SPLIT), ('Sep 1 - Nov 1', lambda tk: SPLIT <= win[tk]['closeTs'] < NOV2), ('Nov 2 - 12', lambda tk: win[tk]['closeTs'] >= NOV2), ('Nov 9 - 12', lambda tk: win[tk]['closeTs'] >= NOV2 + 7 * 86400)):
    B = [(tk, r) for tk, r in B90 if cond(tk)]; c = [cush(tk, r) for tk, r in B]; k = sum(1 for tk, r in B if r['side'] != win[tk]['truth'])
    bk = collections.Counter(r['bk'] for tk, r in B); sig = [r['sig'] for tk, r in B]
    print('  %-14s n=%5d lost=%d cushion bps median %.1f p10 %.1f p90 %.1f | share <15 bps %.2f | sig median %.3f | bk %s' % (lab, len(B), k, q(c, .5), q(c, .1), q(c, .9), sum(1 for x in c if x < 15) / max(1, len(c)), q(sig, .5), dict(sorted(bk.items()))))
# cushion in sigma units (cushion_usd / (sig * sqrt(tau)))? sig is bps/sqrt(s): cushion_bps / (sig*sqrt(tau))
for lab, cond in (('before Sep 1', lambda tk: win[tk]['closeTs'] < SPLIT), ('Sep 1 - Nov 12', lambda tk: win[tk]['closeTs'] >= SPLIT), ('Nov 2 - 12', lambda tk: win[tk]['closeTs'] >= NOV2)):
    B = [(tk, r) for tk, r in B90 if cond(tk)]; z = [cush(tk, r) / (r['sig'] * math.sqrt(r['tau'])) for tk, r in B]
    print('  %-14s cushion/(sig*sqrt(tau)) median %.2f p10 %.2f | pf at entry median %.5f' % (lab, q(z, .5), q(z, .1), q([r['pf'] for tk, r in B], .5)))
# spot check vs unscaled chunk 01: sig equal? pf differs?
us = {}
with gzip.open(chunk01, 'rt') as fh:
    for l in fh:
        r = json.loads(l)
        if (r['tk'], r['tau']) in spot: us[(r['tk'], r['tau'])] = (r.get('sig'), r.get('pf'), r.get('st'), r.get('bk'))
n_eq_sig = n_eq_pf = n = 0
for k, v in spot.items():
    if k in us:
        n += 1; n_eq_sig += (v[0] == us[k][0]); n_eq_pf += (v[1] == us[k][1])
print('spot check scaled vs unscaled on %d rows: sig equal %d, pf equal %d; examples:' % (n, n_eq_sig, n_eq_pf))
for k in list(spot)[:3]:
    if k in us: print('   ', k, 'scaled', spot[k], 'unscaled', us[k])
json.dump({tk: dict(tau=r['tau'], pf=r['pf'], cush=cush(tk, r), sig=r['sig'], bk=r['bk'], close=win[tk]['closeTs'], lost=(r['side'] != win[tk]['truth'])) for tk, r in B90}, open(sys.argv[4], 'w'))
