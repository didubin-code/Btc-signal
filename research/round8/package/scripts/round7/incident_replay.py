"""Chronological replay of a production window under PR11: every second of the final 125 s with the engine's state/risk as served, the required
adverse move R, the frozen threshold R*(h), PR11 admission (exact and displayed), and the executable offer from the tape books; marks the move
(first second the gap fell by more than 5 bps from its value 3 s earlier, or the state left LOCKED). usage: python3 -I incident_replay.py <rstar.json> <rows.ndjson> <market.json> <tape_all.ndjson|-> <ticker>"""
import sys, json, math, bisect, collections
rstar_f, rows_f, m_f, tape, tk = sys.argv[1:6]
RSTAR = {int(k): v for k, v in json.load(open(rstar_f))['rstar'].items()}
m = json.load(open(m_f)); truth = 'UP' if m['result'] == 'yes' else 'DOWN'
books = []
if tape != '-':
    for l in open(tape):
        try: r = json.loads(l)
        except Exception: continue
        if r.get('k') == 'd' and r.get('ob') and r.get('kal') and r['kal'].get('ticker') == tk: books.append((r.get('obTs') or r['ts'], r['ob']))
books.sort(); BT = [b[0] for b in books]
def offer(ts, side):
    i = bisect.bisect_right(BT, ts) - 1
    if i < 0 or ts - books[i][0] > 3000: return '-'
    ob = books[i][1]; other = ob.get('no') if side == 'UP' else ob.get('yes')
    lv = sorted(((round(100 - p, 2), s) for p, s in (other or []) if s > 0), key=lambda x: x[0])
    return ('%.1f x %.0f' % (lv[0][0], lv[0][1])) if lv else 'no ask'
rows = sorted((json.loads(x) for x in open(rows_f) if x.strip()), key=lambda r: -r['tau'])
print('%s  result %s  strike %.2f  official %s' % (tk, truth, m['strike'], m.get('official')))
print('  tau    state              side  pFlip     cushion   n   h   R      R*   exact  disp   offer(called side)')
hist = []
for r in rows:
    tau = r['tau']
    if tau > 125 or tau <= 0 or r.get('gap') is None: continue
    n = r.get('n') or 0
    if n >= 1 and tau <= 60: h = max(1, 60 - n); R = abs(r['gap']) / r['strike'] * 1e4 * 60.0 / h
    else: h = min(120, max(1, math.ceil(tau - 1e-9))); R = abs(r['gap']) / r['strike'] * 1e4
    side = 'UP' if r['gap'] > 0 else 'DOWN'; cushion = abs(r['gap']) / r['strike'] * 1e4
    lk = r.get('state') in ('LOCKED', 'PROVEN LOCKED'); pf = r.get('pFlip')
    ex = lk and pf is not None and pf <= 0.002 and R >= RSTAR[h]; dp = lk and pf is not None and pf < 0.0025 and R >= RSTAR[h]
    hist.append((tau, r['gap'] / r['strike'] * 1e4))
    mv = ''
    for t0, g0 in hist:
        if t0 - tau >= 3 and (g0 - r['gap'] / r['strike'] * 1e4) * (1 if g0 > 0 else -1) > 5: mv = ' <-- move'; break
    print('  %6.1f %-18s %-5s %-9s %6.1f  %2d %3d  %6.1f %3d   %-6s %-6s %s%s' % (tau, r.get('state'), side, ('%.5f' % pf) if pf is not None else '-', cushion, n, h, R, RSTAR[h], 'ADMIT' if ex else '-', 'ADMIT' if dp else '-', offer(r['ts'], side), mv))
