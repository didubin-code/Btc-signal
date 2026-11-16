"""Threshold sweep on the UNSCALED year traces: first LOCKED/PROVEN row with 0<tau<=120 and pf<=thr, for several thr; [90,120] entries/losses by period."""
import json, sys, gzip, glob, collections
recs, D, outp = sys.argv[1:4]
win = {json.loads(l)['ticker']: json.loads(l) for l in open(recs) if l.strip()}
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
THR = [0.002, 0.0023, 0.0026, 0.0028, 0.0031, 0.0034, 0.0038, 0.0045]
first = {t: {} for t in THR}
for f in sorted(glob.glob(D + '/usdc_*.trace.ndjson.gz')):
    with gzip.open(f, 'rt') as fh:
        for l in fh:
            r = json.loads(l); tk = r['tk']
            if tk not in win or not (0 < r['tau'] <= 120) or r.get('pf') is None or not isL(r.get('st')) or r['pf'] > THR[-1]: continue
            for t in THR:
                if r['pf'] <= t:
                    d = first[t]
                    if tk not in d or r['tau'] > d[tk]['tau']: d[tk] = r
SEP = 1788220800; NOV1 = 1793491200
out = []
for t in THR:
    E = first[t]; B = [(tk, r) for tk, r in E.items() if 90 <= r['tau'] <= 120]
    def cnt(cond): 
        S = [(tk, r) for tk, r in B if cond(win[tk]['closeTs'])]; return len(S), sum(1 for tk, r in S if r['side'] != win[tk]['truth'])
    a = cnt(lambda c: True); b = cnt(lambda c: c < SEP); c = cnt(lambda c: SEP <= c < NOV1); d = cnt(lambda c: c >= NOV1)
    allb = len(E), sum(1 for tk, r in E.items() if r['side'] != win[tk]['truth'])
    out.append('thr %.4f: all bins %d/%d | [90,120] year %d/%d (%.3f%%) | before Sep 1 %d/%d | Sep 1-Oct 31 %d/%d | Nov 1-12 %d/%d' % (t, allb[0], allb[1], a[0], a[1], 100 * a[1] / max(1, a[0]), b[0], b[1], c[0], c[1], d[0], d[1]))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
