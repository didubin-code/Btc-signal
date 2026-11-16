"""Live LOCKED pf<=0.002 entries at 90-120 s (first such second per window): entry-time information for losses vs winners in the same
cushion/regime cells: cushion, sigma, regime, 20-s cushion change before entry, 60-s index move before entry, BRTI age, time left, and
the subsequent minimum cushion. Only information available at the entry second is used for the comparison columns."""
import json, glob, os
L = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/r30/live'
ent = []
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; mp = L + '/scoreboard/markets/' + tk + '.json'
    if not os.path.exists(mp): continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    e = None
    for i, r in enumerate(rows):
        if 90 <= r['tau'] <= 120 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and r['pFlip'] <= 0.002 and r.get('gap') is not None:
            side = 'UP' if r['gap'] > 0 else 'DOWN'; sgn = 1 if side == 'UP' else -1
            g = lambda rr: sgn * rr['gap'] / rr['strike'] * 1e4
            prev20 = next((rr for rr in rows[:i] if rr['tau'] >= r['tau'] + 20), None); prev60 = next((rr for rr in rows[:i] if rr['tau'] >= r['tau'] + 60), None)
            later = rows[i + 1:]
            e = {'tk': tk, 'lost': side != truth, 'tau': r['tau'], 'cushion': g(r), 'sigma': r['sigma'], 'regime': r.get('regime'), 'pf': r['pFlip'],
                 'd20': (g(r) - g(prev20)) if prev20 else None, 'd60': (g(r) - g(prev60)) if prev60 else None, 'brtiAge': r.get('brtiAgeMs'), 'ask': r.get('ask'),
                 'sig20': (r['sigma'] - prev20['sigma']) if prev20 else None, 'minLater': min((g(rr) for rr in later), default=None)}
            break
    if e: ent.append(e)
print('live first LOCKED pf<=0.002 entries at 90-120 s: %d, lost %d' % (len(ent), sum(1 for e in ent if e['lost'])))
def cell(e): return ('15-20' if 15 <= e['cushion'] < 20 else '10-15' if 10 <= e['cushion'] < 15 else '20-30' if 20 <= e['cushion'] < 30 else '>=30' if e['cushion'] >= 30 else '<10', e['regime'])
print('  %-26s %-6s %6s %6s %5s %3s %7s %7s %7s %6s %5s %7s' % ('ticker', 'lost', 'tau', 'cush', 'sigma', 'rg', 'd20', 'd60', 'sig20', 'age', 'ask', 'minLtr'))
for e in sorted(ent, key=lambda e: (not e['lost'], e['cushion'])):
    if e['lost'] or cell(e) in {cell(x) for x in ent if x['lost']}:
        print('  %-26s %-6s %6.1f %6.1f %5.2f %3s %7s %7s %7s %6s %5s %7s' % (e['tk'], 'LOST' if e['lost'] else 'won', e['tau'], e['cushion'], e['sigma'], e['regime'], '%.1f' % e['d20'] if e['d20'] is not None else '-', '%.1f' % e['d60'] if e['d60'] is not None else '-', '%.2f' % e['sig20'] if e['sig20'] is not None else '-', e['brtiAge'], e['ask'], '%.1f' % e['minLater'] if e['minLater'] is not None else '-'))
import statistics as st
W = [e for e in ent if not e['lost'] and cell(e) in {cell(x) for x in ent if x['lost']}]
for k in ('cushion', 'sigma', 'd20', 'd60', 'sig20', 'brtiAge'):
    v = [e[k] for e in W if e[k] is not None]
    if v: print('  comparable winners (%d): %s median %.2f, p10 %.2f, p90 %.2f' % (len(W), k, st.median(v), sorted(v)[int(0.1 * len(v))], sorted(v)[int(0.9 * len(v))]))
