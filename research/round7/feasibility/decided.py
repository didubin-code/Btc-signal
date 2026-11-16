"""Exact settlement mathematics. Contract: YES iff mean of the 60 BRTI prints in the final minute >= strike K (ties YES).
With n official prints known (sum S_n) and r = 60 - n unknown prints p_i > 0:
  YES is certain iff S_n >= 60 K  (remaining prints can only add a non-negative amount);
  NO is never certain before the last print (the remaining prints are unbounded above).
Live production rows carry n and recAvg (mean of the known prints): decided iff n * recAvg >= 60 * K.
Report, per settled live window, the first tau at which YES became certain (if ever) and the cushion required.
usage: python3 -I decided.py <rows dir> <markets dir>"""
import sys, json, glob, os
rowsdir, mkdir = sys.argv[1:3]
nwin = 0; decided = []; never = 0; yes_wins = 0
for p in sorted(glob.glob(rowsdir + '/*.ndjson')):
    tk = os.path.basename(p)[:-7]; mp = mkdir + '/' + tk + '.json'
    if not os.path.exists(mp): continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    nwin += 1
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    first = None
    for r in rows:
        n = r.get('n') or 0; ra = r.get('recAvg'); K = r.get('strike')
        if n and ra and K and n * ra >= 60 * K:
            first = (r['tau'], n, ra, K, (ra - K) / K * 1e4); break
    if m['result'] == 'yes': yes_wins += 1
    if first: decided.append((tk, m['result']) + first)
    else: never += 1
print('settled live windows: %d (YES %d); windows where YES became mathematically certain before the close: %d; never certain before the last print: %d' % (nwin, yes_wins, len(decided), never))
for d in decided: print('  %s result=%s first certain at tau=%.2f s with n=%d known prints, mean %.2f vs K %.2f (cushion %.0f bps)' % d)
print('arithmetic: certainty with n known prints requires mean_known/K >= 60/n, i.e. a cushion of at least %s' % ', '.join('%d prints: %.2f %%' % (n, (60 / n - 1) * 100) for n in (59, 58, 57, 55, 50, 45, 30)))
