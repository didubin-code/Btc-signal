#!/usr/bin/env python3
import sys, json, gzip, os, collections, statistics, datetime
D = sys.argv[1]; E = sys.argv[2]
def show(ch, tk, lo, hi):
    w = None
    with open(D + ch + '.ndjson') as f:
        for ln in f:
            x = json.loads(ln)
            if x['ticker'] == tk: w = x; break
    print('---', ch, tk, 'strike', w['strike'], 'official', w['official'], 'truth', w['truth'], 'margin', w['marginUsd'], 'firstLocked', json.dumps(w['firstLocked']))
    with gzip.open(D + ch + '.trace.ndjson.gz', 'rt') as f:
        for ln in f:
            r = json.loads(ln)
            if r['tk'] == tk and lo <= r['tau'] <= hi:
                print('  tau=%6.2f %-17s %-4s pf=%.6f pfc=%.6f gap=%8.2f gap+mu=%8.2f sig=%.4f bk=%d soft=%d hard=%d mu=%.2f' % (r['tau'], r['st'], r['side'], r['pf'], r['pfc'], r['gap'], r['gap'] + r['mu'], r['sig'], r['bk'], r['soft'], r['hard'], r['mu']))
show('usdc_11', 'KXBTC15M-26NOV010715-15', 0, 40)
show('usdc_11', 'KXBTC15M-26NOV010245-45', 25, 45)
show('usdc_01', 'KXBTC15M-26JAN171245-45', 15, 30)
# relation between side and sign(gap+mu) for LOCKED rows in one chunk
for ch in ('usdc_11', 'usdc_04'):
    c = collections.Counter()
    with gzip.open(D + ch + '.trace.ndjson.gz', 'rt') as f:
        for ln in f:
            r = json.loads(ln)
            if r['st'] in ('LOCKED', 'PROVEN LOCKED'):
                c[('side==sign(gap)', (r['gap'] > 0) == (r['side'] == 'UP')), ('side==sign(gap+mu)', (r['gap'] + r['mu'] > 0) == (r['side'] == 'UP')), ('side==sign(gap-mu)', (r['gap'] - r['mu'] > 0) == (r['side'] == 'UP'))] += 1
    print(ch, 'LOCKED rows:', dict(c))
# mu by month in usdc entries (R_disp)
bym = collections.defaultdict(list)
for fn in sorted(os.listdir(E)):
    if fn.endswith('.ndjson') and fn.startswith('usdc'):
        with open(os.path.join(E, fn)) as f:
            for ln in f:
                r = json.loads(ln); e = r['entries']['R_disp']
                if e: bym[datetime.datetime.fromtimestamp(r['closeTs'], datetime.timezone.utc).strftime('%Y-%m')].append(e['mu'])
for m, xs in sorted(bym.items()):
    xs.sort(); n = len(xs)
    print('%s n=%5d mu p5=%7.2f p50=%7.2f p95=%7.2f min=%7.2f max=%7.2f' % (m, n, xs[int(0.05*n)], xs[n//2], xs[int(0.95*n)], xs[0], xs[-1]))
# daily mu in Nov
byd = collections.defaultdict(list)
with open(os.path.join(E, 'usdc_11.ndjson')) as f:
    for ln in f:
        r = json.loads(ln); e = r['entries']['R_disp']
        if e: byd[datetime.datetime.fromtimestamp(r['closeTs'], datetime.timezone.utc).strftime('%m-%d')].append((e['mu'], e['won']))
for d, xs in sorted(byd.items()):
    mus = sorted(x[0] for x in xs)
    print('  %s n=%3d mu min=%7.2f med=%7.2f max=%7.2f losses=%d' % (d, len(xs), mus[0], mus[len(mus)//2], mus[-1], sum(1 for x in xs if not x[1])))
