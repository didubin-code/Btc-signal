"""Binance-proxy / live raw sigma ratio by live regime bucket and by sigma level, on the common windows (as rowcompare.py; first row of each second)."""
import json, glob, os, math, collections, sys
tr, rowsdir = sys.argv[1:3]
rep = collections.defaultdict(dict)
for l in open(tr):
    r = json.loads(l); rep[r['tk']][int(math.floor(r['tau']))] = r
ratios = collections.defaultdict(list); pfr = collections.defaultdict(list); n = 0
for p in glob.glob(rowsdir + '/*.ndjson'):
    tk = os.path.basename(p)[:-7]
    if tk not in rep: continue
    seen = set()
    for l in open(p):
        if not l.strip(): continue
        a = json.loads(l); s = int(math.floor(a['tau']))
        if s in seen or s < 1 or s > 120: continue
        seen.add(s); b = rep[tk].get(s)
        if not b or not a.get('sigma') or not b.get('sig'): continue
        n += 1; lv = a['sigma'] / 1.03; rt = b['sig'] / lv
        ratios[('bk', a.get('regime'))].append(rt); ratios[('all',)].append(rt)
        lvl = '<0.3' if lv < 0.3 else '0.3-0.5' if lv < 0.5 else '0.5-0.8' if lv < 0.8 else '0.8-1.2' if lv < 1.2 else '>=1.2'
        ratios[('live sigma', lvl)].append(rt)
        if a.get('pFlip') and b.get('pf') and a['pFlip'] > 0 and b['pf'] > 0 and s >= 90: pfr[('bk', a.get('regime'))].append(b['pf'] / a['pFlip']); pfr[('all',)].append(b['pf'] / a['pFlip'])
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
print('rows %d; Binance/live raw sigma ratio (same second) by live regime bucket and live sigma level; pf ratio at [90,120]:' % n)
for k in sorted(ratios, key=str):
    v = ratios[k]; print('  %-24s n=%6d median %.3f p10 %.3f p90 %.3f | implied scale 1.03/median = %.3f %s' % (k, len(v), q(v, .5), q(v, .1), q(v, .9), 1.03 / q(v, .5), ('| pf ratio [90,120] median %.2f' % q(pfr[k], .5)) if k in pfr else ''))
