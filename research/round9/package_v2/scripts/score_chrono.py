"""Score chronological own-memory replays (one or more engines) against the Kalshi results and the recorded books.
Per market: first entry under the owner's rule (first LOCKED/PROVEN LOCKED with exact pFlip <= 0.002 inside the final 120 s, any side),
later LOCKED seconds on the opposite side, REVERSAL WARNING seconds, outcome, offers at the entry and 1/3/5/10 s later (books from the
tape records, <= 3 s old; ask = 100 - opposite-side bid), and the comparison with the recorded-state replay's entry.
usage: python3 -I score_chrono.py <markets dirs comma> <tapes comma> <out.txt> <label=chrono.ndjson> [label=chrono.ndjson ...] [--d3 label=dir]"""
import sys, json, glob, os, bisect, collections
mkdirs, tapes, outp = sys.argv[1].split(','), sys.argv[2].split(','), sys.argv[3]
engines = {}; d3dir = None
for a in sys.argv[4:]:
    if a.startswith('--d3='): d3dir = a[5:]; continue
    k, v = a.split('=', 1); engines[k] = v
mk = {}
for d in mkdirs:
    for p in glob.glob(d + '/*.json'):
        m = json.load(open(p)); tk = os.path.basename(p)[:-5]
        if m.get('result') in ('yes', 'no') and tk not in mk: mk[tk] = m
books = collections.defaultdict(list)
for t in tapes:
    for l in open(t):
        try: r = json.loads(l)
        except Exception: continue
        if r.get('k') == 'd' and r.get('kal') and r.get('ob'): books[r['kal']['ticker']].append((r.get('obTs') or r['ts'], r['ob']))
for tk in books: books[tk].sort()
BT = {tk: [b[0] for b in B] for tk, B in books.items()}
def levels(ob, side):
    other = ob.get('no') if side == 'UP' else ob.get('yes'); lv = [(round(100 - p, 2), s) for p, s in (other or []) if s and s > 0]; lv.sort(); return lv
def offer(tk, ts, side):
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right(BT[tk], ts) - 1
    if i < 0 or ts - B[i][0] > 3000: return {'book': False}
    lv = levels(B[i][1], side); o = {'book': True, 'age': ts - B[i][0], 'ask': lv[0][0] if lv else None, 'size': lv[0][1] if lv else 0, 'depth999': sum(s for a, s in lv if a <= 99.9 + 1e-9), 'depth998': sum(s for a, s in lv if a <= 99.8 + 1e-9)}
    return o
def avail(o): return bool(o and o.get('book') and o.get('ask') is not None and o['ask'] <= 99.9 + 1e-9 and o['size'] >= 10)
def fmt(o):
    if o is None: return 'no tape'
    if not o.get('book'): return 'no book'
    return ('%.1f x %d' % (o['ask'], o['size'])) if o['ask'] is not None else 'no ask'
rows = {k: collections.defaultdict(list) for k in engines}
for k, f in engines.items():
    for l in open(f):
        r = json.loads(l); rows[k][r['ticker']].append(r)
d3entry = {}
if d3dir:
    for p in glob.glob(d3dir + '/B9_T*.ndjson'):
        for l in open(p):
            r = json.loads(l)
            if 0 < r['tau'] <= 120 and r['state'] in ('LOCKED', 'PROVEN LOCKED') and (r['pFlip'] or 1) <= 0.002 and r['ticker'] not in d3entry: d3entry[r['ticker']] = r
out = []; P = out.append; summ = {k: collections.Counter() for k in engines}; table = []
tickers = sorted(set().union(*[set(v) for v in rows.values()]))
for tk in tickers:
    m = mk.get(tk); truth = ('UP' if m['result'] == 'yes' else 'DOWN') if m else None
    line = {'ticker': tk, 'truth': truth}
    for k in engines:
        R = sorted(rows[k][tk], key=lambda r: r['ts']); R120 = [r for r in R if 0 < r['tau'] <= 120]
        ent = next((r for r in R120 if r['state'] in ('LOCKED', 'PROVEN LOCKED') and r['pFlip'] is not None and r['pFlip'] <= 0.002), None)
        opp = [r for r in R120 if ent and r['ts'] > ent['ts'] and r['state'] in ('LOCKED', 'PROVEN LOCKED') and r['side'] != ent['side']]
        rev = [r for r in R120 if r['state'] == 'REVERSAL WARNING']
        lockedAny = [r for r in R120 if r['state'] in ('LOCKED', 'PROVEN LOCKED')]
        e = None
        if ent:
            o0 = offer(tk, ent['ts'], ent['side']); lags = {L: offer(tk, ent['ts'] + L * 1000, ent['side']) for L in (1, 3, 5, 10)}
            still = {L: next((q for q in R120 if abs(q['ts'] - (ent['ts'] + L * 1000)) <= 600), None) for L in (1, 3, 5, 10)}
            e = {'tau': ent['tau'], 'side': ent['side'], 'pFlip': ent['pFlip'], 'action': ent['action'], 'lost': (ent['side'] != truth) if truth else None, 'offer': o0, 'lags': lags,
                 'stillLocked': {L: bool(q and q['state'] in ('LOCKED', 'PROVEN LOCKED') and q['side'] == ent['side']) for L, q in still.items()}, 'pr11': ent.get('pr11')}
            summ[k]['entries'] += 1; summ[k]['lost'] += int(e['lost'] or 0); summ[k]['entry_book'] += int(bool(o0 and o0.get('book'))); summ[k]['entry_avail'] += int(avail(o0))
            for L in (1, 3, 5, 10): summ[k]['avail_lag%d' % L] += int(avail(lags[L]) and e['stillLocked'][L])
        line[k] = {'entry': e, 'oppositeLockedSeconds': len(opp), 'oppositeFirst': ({'tau': opp[0]['tau'], 'side': opp[0]['side'], 'action': opp[0]['action'], 'offer': fmt(offer(tk, opp[0]['ts'], opp[0]['side'])), 'anyAvail': any(avail(offer(tk, r['ts'], r['side'])) for r in opp), 'lost': (opp[0]['side'] != truth) if truth else None} if opp else None),
                   'reversalWarningSeconds': len(rev), 'lockedSeconds': len(lockedAny), 'ownLockedSideFinal': R[-1]['ownLockedSide'] if R else None}
        if opp: summ[k]['markets_with_opposite_locked'] += 1; summ[k]['opposite_locked_seconds'] += len(opp); summ[k]['opposite_with_avail'] += int(line[k]['oppositeFirst']['anyAvail'])
        summ[k]['markets'] += 1; summ[k]['rev_seconds'] += len(rev)
        if truth and ent and ent['side'] == truth: summ[k]['won'] += 1
    line['d3_recorded_state_entry'] = ({'tau': d3entry[tk]['tau'], 'side': d3entry[tk]['side']} if tk in d3entry else None)
    table.append(line)
P('CHRONOLOGICAL OWN-MEMORY REPLAY SCORES (28 capture markets; each engine keeps its own lock memory; first decision of each market seeded with the recorded memory, all null)')
for k in engines:
    s = summ[k]; P('  %-4s markets %d | entries %d lost %d won %d | entry with a book %d, available offer at entry %d, available & still LOCKED after 1/3/5/10 s: %d/%d/%d/%d | markets with a later opposite-side LOCKED %d (seconds %d; any available offer on that side %d) | REVERSAL WARNING seconds %d' % (k, s['markets'], s['entries'], s['lost'], s['won'], s['entry_book'], s['entry_avail'], s['avail_lag1'], s['avail_lag3'], s['avail_lag5'], s['avail_lag10'], s['markets_with_opposite_locked'], s['opposite_locked_seconds'], s['opposite_with_avail'], s['rev_seconds']))
P('  per market:')
for line in table:
    parts = []
    for k in engines:
        e = line[k]['entry']; o = line[k]['oppositeFirst']
        parts.append('%s: %s%s%s' % (k, ('entry %.1f s %s pf %.5f %s offer %s%s' % (e['tau'], e['side'], e['pFlip'], 'LOST' if e['lost'] else 'won', fmt(e['offer']), ' [' + e['action'] + ']' if e['action'] and 'TOO LATE' in e['action'] else '')) if e else 'no entry', (' | opposite LOCKED %d s from %.1f s %s (%s, offer %s, %s)' % (line[k]['oppositeLockedSeconds'], o['tau'], o['side'], o['action'], o['offer'], 'LOST' if o['lost'] else 'won') if o else ''), (' | REV %d s' % line[k]['reversalWarningSeconds'] if line[k]['reversalWarningSeconds'] else '')))
    P('    %s result %s | %s | recorded-state b9 entry: %s' % (line['ticker'], line['truth'], ' || '.join(parts), line['d3_recorded_state_entry']))
json.dump({'summary': {k: dict(v) for k, v in summ.items()}, 'table': table}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out[:4]))
