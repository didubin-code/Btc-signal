"""Per-second record of one window: served state, geometry, the build-9 rule (reconstruction) and, where a 1-s
capture exists, the exact build-9 engine's decision; with the called side's best offer.
usage: python3 -I incident_seconds.py <ticker> <rows dirs comma> <markets dirs comma> <tape_all.ndjson> <rstar.json> <B9 dumps comma or -> <out.txt>"""
import sys, json, glob, os, math, bisect
tk, rowsdirs, mkdirs, tape, rf, b9f, outp = sys.argv[1], sys.argv[2].split(','), sys.argv[3].split(','), sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]
RSTAR = {int(k): v for k, v in json.load(open(rf))['rstar'].items()}
rows = None
for d in rowsdirs:
    p = d + '/' + tk + '.ndjson'
    if os.path.exists(p): rows = [json.loads(x) for x in open(p) if x.strip()]; break
m = None
for d in mkdirs:
    p = d + '/' + tk + '.json'
    if os.path.exists(p): m = json.load(open(p)); break
books = []
with open(tape) as f:
    for line in f:
        try: r = json.loads(line)
        except Exception: continue
        if r.get('k') == 'd' and r.get('kal') and r['kal']['ticker'] == tk and r.get('ob'): books.append((r.get('obTs') or r['ts'], r['ob'], r.get('out')))
books.sort(key=lambda b: b[0]); BT = [b[0] for b in books]
ex = {}
if b9f != '-':
    for p in b9f.split(','):
        for line in open(p):
            r = json.loads(line)
            if r['ticker'] == tk: ex[r['ts']] = r
ets = sorted(ex)
def exact_at(ts):
    i = bisect.bisect_left(ets, ts)
    for j in (i - 1, i):
        if 0 <= j < len(ets) and abs(ets[j] - ts) <= 600: return ex[ets[j]]
    return None
def offer(ts, side):
    i = bisect.bisect_right(BT, ts) - 1
    if i < 0 or ts - BT[i] > 3000: return 'no book'
    ob = books[i][1]; other = ob.get('no') if side == 'UP' else ob.get('yes')
    lv = sorted(((round(100 - p, 2), s) for p, s in (other or []) if s > 0))
    return ('%.1f x %d' % (lv[0][0], lv[0][1])) if lv else 'no ask'
truth = {'yes': 'UP', 'no': 'DOWN'}.get((m or {}).get('result'))
out = ['%s  result %s (%s)  strike %s  official %s  | rows %s | exact engine rows %d' % (tk, (m or {}).get('result'), truth, rows[0].get('strike') if rows else None, (m or {}).get('official'), 'yes' if rows else 'NONE', len(ex))]
out.append('  tau     served state      side  pFlip     gap$   cushion n  h   R     R*   ref       recon          exact engine (b9)                      offer(called side)')
for r in sorted(rows or [], key=lambda r: -r['tau']):
    if not (0 < r['tau'] <= 125) or r.get('gap') is None: continue
    tau = r['tau']; side = r.get('side'); cushion = abs(r['gap']) / r['strike'] * 1e4; h = min(120, max(1, math.ceil(tau - 1e-9))); R = cushion * 60 / h if h <= 59 else cushion
    locked = r['state'] in ('LOCKED', 'PROVEN LOCKED'); elig = locked and r['pFlip'] <= 0.002
    official_ok = (r.get('ref') == 'OFFICIAL') if tau <= 60 else True; floor_ok = R >= RSTAR[h] - 1e-9
    recon = 'ADMIT' if (locked and floor_ok and official_ok) else ('withheld:' + ('floor' if not floor_ok else 'official')) if locked else '-'
    e = exact_at(r['ts']); es = ('%s%s' % (e['state'], (' [' + (e['pr11'] or {}).get('reason', '') + ']') if e['state'] not in ('LOCKED', 'PROVEN LOCKED') and (e.get('pr11') or {}).get('reason') else '')) if e else '(no capture)'
    out.append('  %6.1f  %-17s %-5s %.5f %8.2f %6.1f %2s %3d %6.1f %3d  %-9s %-14s %-38s %s%s' % (tau, r['state'], side, r['pFlip'], r['gap'], cushion, r.get('n'), h, R, RSTAR[h], r.get('ref'), recon, es, offer(r['ts'], side), '   <- baseline-eligible' if elig else ''))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out[:3])); print('... lines', len(out))
