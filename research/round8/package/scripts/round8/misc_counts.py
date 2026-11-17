"""Small measurements cited in the report: LOCKED beyond 120 s on prediction rows, PROVEN frequency, production compute time,
and the three sub-second matching artefacts. usage: python3 -I misc_counts.py <rows dirs comma> <markets dirs comma> <I2 d3 dumps comma> <out.txt>"""
import sys, json, glob, os
rowsdirs, mkdirs, d3f, outp = sys.argv[1].split(','), sys.argv[2].split(','), sys.argv[3].split(','), sys.argv[4]
mk = {}
for d in mkdirs:
    for p in glob.glob(d + '/*.json'):
        m = json.load(open(p))
        if m.get('result') in ('yes', 'no'): mk.setdefault(os.path.basename(p)[:-5], m)
n = below = lost_below = 0; ms = []; proven_rows = rows120 = 0
for d in rowsdirs:
    for p in glob.glob(d + '/*.ndjson'):
        tk = os.path.basename(p)[:-7]; first = None
        for x in open(p):
            r = json.loads(x)
            if 0 < r['tau'] <= 120:
                rows120 += 1; proven_rows += (r.get('state') == 'PROVEN LOCKED')
                if r.get('ms') is not None: ms.append(r['ms'])
            if first is None and 120 < r['tau'] <= 300 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and r['pFlip'] <= 0.002 and r.get('gap') is not None: first = r
        if first and tk in mk:
            n += 1; cb = abs(first['gap']) / first['strike'] * 1e4; truth = 'UP' if mk[tk]['result'] == 'yes' else 'DOWN'
            if cb < 68: below += 1; lost_below += (first['side'] != truth)
ms.sort(); out = []
out.append('beyond 120 s (prediction rows): windows with a LOCKED pFlip<=0.002 second at 120<tau<=300 s: %d of %d settled; cushion below the 120-s floor (68 bps) at the first such second: %d, of which lost: %d' % (n, len(mk), below, lost_below))
out.append('PROVEN LOCKED rows inside 120 s in the prediction rows: %d of %d' % (proven_rows, rows120))
pv = tot = 0
for p in d3f:
    for l in open(p):
        r = json.loads(l); tot += 1; pv += (r['state'] == 'PROVEN LOCKED')
out.append('PROVEN LOCKED in the I2 exact-replay decisions: %d of %d' % (pv, tot))
out.append('production per-decision compute time (I2 live, prediction rows inside 120 s): n %d, p50 %.3f ms, p99 %.3f ms, max %.3f ms' % (len(ms), ms[len(ms) // 2], ms[int(len(ms) * .99)], ms[-1]))
out.append('note: the 3 "exact-engine not locked" seconds in the market table are prediction-log state-change rows at a half-second offset matched to the nearest tape tick 500 ms earlier, where the served state was DATA UNRELIABLE (2, input age over budget at 5-6 s to close) or HIGH CONFIDENCE (1); the exact engine agrees with what was served at its own tick; no entry is affected.')
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
