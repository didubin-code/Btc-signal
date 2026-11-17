#!/usr/bin/env python3
"""Measure, on the archived decision rows (no samples needed), how often the official settlement reference was unusable at recorded LOCKED /
PROVEN LOCKED seconds inside the settlement minute, using the server's own validity rules (brtiOfficialState27): feed enabled, last value
present/finite/positive, feed age <= 2500 ms, in the minute: accumulator received for this window (or just opened, <= 1 print expected),
window_size within 2 of the clock count, accumulator value within 5 % of the last spot. usage: official_state_scan.py tape_all.ndjson"""
import sys, json, math, collections
BRTI_STALE_MS, BRTI_COUNT_TOL = 2500, 2
def official_ok(r):
    b = r.get('brti') or {}
    if not b.get('enabled'): return 'disabled'
    last = b.get('last')
    if not last: return 'no data'
    v = last.get('value')
    if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0): return 'value invalid'
    lt = last.get('localTs')
    if lt is None or r['ts'] - lt > BRTI_STALE_MS: return 'stale'
    close = r['kal']['closeMs']; tau = (close - r['ts']) / 1000.0
    if tau < 60:
        exp = max(0, min(60, int(math.floor((r['ts'] - (close - 60000)) / 1000.0))))
        w = b.get('win')
        if not w or w.get('closeMs') != close:
            return 'ok (just opened)' if exp <= 1 else 'accumulator not received'
        size = w.get('size')
        if not (isinstance(size, (int, float)) and 0 <= size <= 60) or abs(size - exp) > BRTI_COUNT_TOL: return 'window_size inconsistent'
        wv = w.get('value')
        if size > 0 and not (isinstance(wv, (int, float)) and math.isfinite(wv) and wv > 0 and abs(wv / v - 1) < 0.05): return 'accumulator value implausible'
        return 'ok (partial %d/60)' % size if size < 60 else 'ok (60/60)'
    return 'ok (before the minute)'
tot = collections.Counter(); byWin = collections.defaultdict(lambda: {'locked': 0, 'bad': 0})
n = 0
for l in open(sys.argv[1]):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd' or not r.get('kal') or not r.get('out'): continue
    tau = (r['kal']['closeMs'] - r['ts']) / 1000.0
    if not (0 < tau <= 60): continue
    if r['out'].get('state') not in ('LOCKED', 'PROVEN LOCKED'): continue
    n += 1; st = official_ok(r); tot[st] += 1
    w = byWin[r['kal']['ticker']]; w['locked'] += 1
    if not st.startswith('ok'): w['bad'] += 1
bad = sum(c for k, c in tot.items() if not k.startswith('ok'))
print('recorded LOCKED/PROVEN seconds inside the settlement minute:', n, '| official reference unusable at', bad, '(%.2f %%)' % (100.0 * bad / max(1, n)))
for k, c in tot.most_common(): print('  %-34s %6d' % (k, c))
wins = [t for t, w in byWin.items() if w['bad']]
print('windows with any such second:', len(wins), 'of', len(byWin), '| windows where EVERY locked second had an unusable reference:', sum(1 for t, w in byWin.items() if w['bad'] == w['locked']))
print('examples:', sorted(wins)[:8])
