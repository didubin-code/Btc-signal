import json, os, collections, math, datetime as dt
L = json.load(open('round6/review_tmp/live_entries.json')); R = 'r30/live/scoreboard/rows/'
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
byday = collections.defaultdict(list); miss = 0
for r in L:
    if not (90 <= r['tau'] <= 120) or r['close'] > '2026-11-16T07:00:00Z': continue
    p = R + r['tk'] + '.ndjson'
    if not os.path.exists(p): miss += 1; continue
    best = None
    for l in open(p):
        if not l.strip(): continue
        a = json.loads(l)
        if a.get('gap') is None or not a.get('strike'): continue
        if best is None or abs(a['tau'] - r['tau']) < abs(best['tau'] - r['tau']): best = a
    if best is None or abs(best['tau'] - r['tau']) > 1.5: miss += 1; continue
    byday[r['close'][:10]].append(dict(c=abs(best['gap']) / best['strike'] * 1e4, s=best.get('sigma'), bk=best.get('regime'), lost=(r['side'] != r['truth']), pf=r['pf']))
print('live [90,120] entries with a production row at the entry second (no row file or no row within 1.5 s: %d):' % miss)
allc = []
for d in sorted(byday):
    v = byday[d]; allc += v
    print('  %s n=%3d cushion median %.1f p10 %.1f | <15 bps %d | sigma median %.3f | bk mix %s | lost %d' % (d, len(v), q([x['c'] for x in v], .5), q([x['c'] for x in v], .1), sum(1 for x in v if x['c'] < 15), q([x['s'] for x in v if x['s']], .5), dict(sorted(collections.Counter(x['bk'] for x in v).items())), sum(x['lost'] for x in v)))
print('  all: n=%d cushion median %.1f p10 %.1f, <15 bps %d, sigma median %.3f; losses cushion/sigma: %s' % (len(allc), q([x['c'] for x in allc], .5), q([x['c'] for x in allc], .1), sum(1 for x in allc if x['c'] < 15), q([x['s'] for x in allc if x['s']], .5), [(round(x['c'], 1), x['s'], x['bk']) for x in allc if x['lost']]))
