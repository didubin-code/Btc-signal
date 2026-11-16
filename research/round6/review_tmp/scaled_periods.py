import json, collections, datetime as dt, math
B = json.load(open('round6/review_tmp/scaled_b90.json')); L = json.load(open('round6/review_tmp/live_entries.json'))
def ts(s): return int(dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).timestamp())
SEP, NOV2, NOV1, NOV12 = ts('2026-09-01T00:00:00Z'), ts('2026-11-02T00:00:00Z'), ts('2026-11-01T00:00:00Z'), ts('2026-11-12T00:00:00Z')
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
print('SCALED [90,120] cohort (year) by period: n, losses, cushion median/p10, share <15 bps, sigma median, cushion/(sig*sqrt(tau)) median')
for lab, lo, hi in (('Jan 15-Aug 31', 0, SEP), ('Sep 1-Oct 31', SEP, NOV1), ('Nov 1-11', NOV1, NOV12), ('Nov 12', NOV12, 1e12), ('Sep 1-Nov 12', SEP, 1e12)):
    S = [v for v in B.values() if lo <= v['close'] < hi]; c = [v['cush'] for v in S]
    print('  %-14s n=%5d lost=%d cushion median %.1f p10 %.1f | <15 bps %.2f | sig median %.3f | z median %.2f' % (lab, len(S), sum(v['lost'] for v in S), q(c, .5), q(c, .1), sum(1 for x in c if x < 15) / max(1, len(c)), q([v['sig'] for v in S], .5), q([v['cush'] / (v['sig'] * math.sqrt(v['tau'])) for v in S], .5)))
print('  by day, Nov 2-12 (scaled cohort): day n cushion-median sig-median')
for d in range(2, 13):
    lo = ts('2026-11-%02dT00:00:00Z' % d); S = [v for v in B.values() if lo <= v['close'] < lo + 86400]
    print('    Nov %2d n=%3d cushion median %.1f sig median %.3f' % (d, len(S), q([v['cush'] for v in S], .5), q([v['sig'] for v in S], .5)))
live90 = {r['tk']: r for r in L if 90 <= r['tau'] <= 120 and r['close'] <= '2026-11-16T07:00:00Z'}
shared = [tk for tk in live90 if tk in B]
print('live [90,120] entries %d; also [90,120] entries of the SCALED year cohort (same window): %d (Nov 2-12 live: %d); losses among shared: live %d scaled %d' % (len(live90), len(shared), sum(1 for tk in live90 if live90[tk]['close'] < '2026-11-13'), sum(1 for tk in shared if live90[tk]['side'] != live90[tk]['truth']), sum(1 for tk in shared if B[tk]['lost'])))
sepnov = [tk for tk, v in B.items() if v['close'] >= SEP]
print('comparable Sep-Nov [90,120] cohort: %d entries, of which %d are also live [90,120] entries (shared outcomes); disjoint part: %d entries, %d losses' % (len(sepnov), sum(1 for tk in sepnov if tk in live90), len(sepnov) - sum(1 for tk in sepnov if tk in live90), sum(1 for tk in sepnov if tk not in live90 and B[tk]['lost'])))
