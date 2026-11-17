"""Baseline-only extension: windows that have tape rows (served state, books) but no prediction rows (no geometry),
so the candidate cannot be evaluated there. Baseline entry = first served LOCKED/PROVEN with pFlip <= 0.002 inside 120 s.
usage: python3 -I baseline_tape_only.py <tape_all.ndjson> <exclusions.csv> <markets dirs comma> <out.txt>"""
import sys, json, csv, os, collections, bisect
tape, excf, mkdirs, outp = sys.argv[1], sys.argv[2], sys.argv[3].split(','), sys.argv[4]
tks = [r['ticker'] for r in csv.DictReader(open(excf)) if r['reason'].startswith('no prediction rows')]
S = set(tks); rows = collections.defaultdict(list)
with open(tape) as f:
    for line in f:
        try: r = json.loads(line)
        except Exception: continue
        k = r.get('kal') or {}
        if k.get('ticker') in S: rows[k['ticker']].append(r)
def levels(ob, side):
    other = ob.get('no') if side == 'UP' else ob.get('yes'); lv = [(round(100 - p, 2), s) for p, s in (other or []) if s and s > 0]; lv.sort(); return lv
out = []; P = out.append; n = lost = avail = 0; asks = []
for tk in sorted(rows):
    m = None
    for d in mkdirs:
        p = d + '/' + tk + '.json'
        if os.path.exists(p): m = json.load(open(p)); break
    if not m or m.get('result') not in ('yes', 'no'): P('%s: no result' % tk); continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; rs = sorted(rows[tk], key=lambda r: r['ts']); ent = None
    for r in rs:
        tau = (r['kal']['closeMs'] - r['ts']) / 1000; o = r.get('out') or {}
        if 0 < tau <= 120 and o.get('state') in ('LOCKED', 'PROVEN LOCKED') and o.get('pFlip') is not None and o['pFlip'] <= 0.002: ent = (tau, o.get('side'), o['pFlip'], r); break
    if not ent: P('%s: no baseline entry' % tk); continue
    tau, side, pf, r = ent; lv = levels(r['ob'], side) if r.get('ob') and r['ts'] - (r.get('obTs') or r['ts']) <= 3000 else None
    ask = lv[0][0] if lv else None; size = lv[0][1] if lv else 0; ok = ask is not None and ask <= 99.9 and size >= 10
    n += 1; lost += int(side != truth); avail += int(ok); asks.append(ask)
    P('%s entry %.1f s side %s pFlip %.5f ask %s size %s %s' % (tk, tau, side, pf, ask, size, 'LOST' if side != truth else 'won'))
P('baseline-only windows (tape rows, no geometry): %d with a result; entries %d, lost %d, available offer at entry %d, asks <= 99.9: %d, 99.8: %d' % (len(tks), n, lost, avail, sum(1 for a in asks if a is not None and a <= 99.9), sum(1 for a in asks if a is not None and abs(a - 99.8) < .01)))
open(outp, 'w').write('\n'.join(out) + '\n'); print(out[-1])
