#!/usr/bin/env python3
"""Check engine conventions in one chunk: fixed[T] vs trace alignment, pf by state, side flips."""
import sys, json, gzip, collections
D = sys.argv[1]; ch = sys.argv[2]
wins = {}
with open(D + ch + '.ndjson') as f:
    for ln in f:
        w = json.loads(ln); wins[w['ticker']] = w
tr = collections.defaultdict(list)
with gzip.open(D + ch + '.trace.ndjson.gz', 'rt') as f:
    for ln in f:
        r = json.loads(ln); tr[r['tk']].append(r)
# 1. alignment of fixed[T] with trace rows
for off in (0.75, -0.25, 1.75):
    match = tot = 0
    for tk, w in wins.items():
        rows = {r['tau']: r for r in tr[tk]}
        for T, fx in w['fixed'].items():
            r = rows.get(float(T) - off)
            if r is None: continue
            tot += 1
            if r['st'] == fx['st'] and r['side'] == fx['side'] and abs(r['pf'] - fx['pFlip']) < 2e-6: match += 1
    print('fixed[T] vs trace row at tau=T-%.2f: %d/%d match (st, side, pf)' % (off, match, tot))
# firstLocked.tau vs first LOCKED row in trace
m = tot = 0; fl_outside = 0; fl_in_trace_but_null = 0
for tk, w in wins.items():
    fl = w['firstLocked']
    first_lock_row = next((r for r in tr[tk] if r['st'] in ('LOCKED', 'PROVEN LOCKED')), None)
    if fl:
        tot += 1
        if fl['tau'] > 124.25: fl_outside += 1
        elif first_lock_row and abs(first_lock_row['tau'] - fl['tau']) < 1e-6: m += 1
    elif first_lock_row: fl_in_trace_but_null += 1
print('firstLocked present: %d ; tau outside trace range (>124.25): %d ; matches first LOCKED trace row: %d ; firstLocked null but LOCKED row in trace: %d' % (tot, fl_outside, m, fl_in_trace_but_null))
# 2. pf by state
st_pf = collections.defaultdict(lambda: [1e9, -1e9, 0])
for tk, rows in tr.items():
    for r in rows:
        s = st_pf[r['st']]; s[0] = min(s[0], r['pf']); s[1] = max(s[1], r['pf']); s[2] += 1
for st, (mn, mx, n) in sorted(st_pf.items()):
    print('state %-18s n=%7d pf min=%.6f max=%.6f' % (st, n, mn, mx))
# non-locked rows with pf<=0.005
c = collections.Counter()
for tk, rows in tr.items():
    for r in rows:
        if r['pf'] <= 0.005 and r['st'] not in ('LOCKED', 'PROVEN LOCKED'): c[(r['st'], r['soft'] > 0, r['hard'] > 0)] += 1
print('non-LOCKED rows with pf<=0.005 by (state, soft>0, hard>0):', dict(c))
# pf exactly at thresholds
cnt = collections.Counter()
for tk, rows in tr.items():
    for r in rows:
        if r['st'] in ('LOCKED', 'PROVEN LOCKED'):
            cnt['pf<0.0025'] += r['pf'] < 0.0025
            cnt['pf<=0.002'] += r['pf'] <= 0.002
            cnt['0.002<pf<0.0025'] += 0.002 < r['pf'] < 0.0025
            cnt['pf==0.002'] += r['pf'] == 0.002
            cnt['pf==0.0025'] += r['pf'] == 0.0025
            cnt['pf==0.005'] += r['pf'] == 0.005
            cnt['pf>0.005'] += r['pf'] > 0.005
print('LOCKED rows threshold counts:', dict(cnt))
# 3. PROVEN LOCKED rows
for tk, rows in tr.items():
    for r in rows:
        if r['st'] == 'PROVEN LOCKED': print('PROVEN LOCKED:', json.dumps(r))
# 4. REVERSAL WARNING: pf range, side relation to previous row
rw = collections.Counter()
for tk, rows in tr.items():
    prev = None
    for r in rows:
        if r['st'] == 'REVERSAL WARNING':
            rw[('side_same_as_prev' if prev and prev['side'] == r['side'] else 'side_changed_or_first', 'pf<0.5' if r['pf'] < 0.5 else 'pf>=0.5')] += 1
        prev = r
print('REVERSAL WARNING rows by (side vs prev, pf):', dict(rw))
# 5. mu constant within window?
nonconst = sum(1 for tk, rows in tr.items() if len(set(r['mu'] for r in rows)) > 1)
print('windows where mu varies within trace: %d / %d' % (nonconst, len(tr)))
nonconst_sig = sum(1 for tk, rows in tr.items() if len(set(r['sig'] for r in rows)) > 1)
print('windows where sig varies within trace: %d / %d' % (nonconst_sig, len(tr)))
# gap vs sign side consistency: is side always the sign of gap?
inc = collections.Counter()
for tk, rows in tr.items():
    for r in rows:
        if r['gap'] == 0: inc['gap0'] += 1
        elif (r['gap'] > 0) != (r['side'] == 'UP'): inc[r['st']] += 1
print('rows where side != sign(gap), by state:', dict(inc))
# 6. losers: windows where wrongLockedSeconds>0 or a LOCKED row with wrong side
losers = [w for w in wins.values() if any(r['st'] in ('LOCKED','PROVEN LOCKED') and r['side'] != w['truth'] for r in tr[w['ticker']])]
print('windows with a LOCKED row on the wrong side: %d' % len(losers))
for w in losers[:2]:
    print('--- loser', w['ticker'], 'truth', w['truth'], 'strike', w['strike'], 'official', w['official'], 'marginUsd', w['marginUsd'])
    for r in tr[w['ticker']]:
        if r['tau'] <= 121:
            print('  tau=%6.2f %-17s %-4s pf=%.6f pfc=%.6f gap=%8.2f sig=%.4f bk=%d soft=%d hard=%d mu=%.2f' % (r['tau'], r['st'], r['side'], r['pf'], r['pfc'], r['gap'], r['sig'], r['bk'], r['soft'], r['hard'], r['mu']))
