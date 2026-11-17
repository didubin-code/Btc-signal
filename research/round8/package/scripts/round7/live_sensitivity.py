"""PR11 on live rows: (1) first-admitted entries with raw cushion < 5 bps (the class the replay cannot resolve) and their outcomes;
(2) sensitivity of admissions to an index error of +/-3 bps (the composite-vs-official basis scale): how many first-admitted seconds would
not be admitted with gap reduced by 3 bps, and how many windows gain/lose an admitted second; (3) sensitivity to stale input: rows with
brtiAgeMs > 2500 at admitted seconds."""
import json, glob, os, math
L = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/r30/live'
RS = {int(k): v for k, v in json.load(open('/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round7/qtable/rstar_0.050.json'))['rstar'].items()}
def hR(r, shift_bps=0.0):
    n = r.get('n') or 0; tau = r['tau']; g = abs(r['gap']) / r['strike'] * 1e4 - shift_bps
    if n >= 1 and tau <= 60: h = max(1, 60 - n); R = g * 60.0 / h
    else: h = min(120, max(1, math.ceil(tau - 1e-9))); R = g
    return h, R
tot = 0; sub5 = 0; sub5lost = 0; flip = 0; adm_rows = 0; adm_rows_minus3 = 0; stale = 0; win_adm = 0; win_adm_m3 = 0; lost_adm = 0
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; mp = L + '/scoreboard/markets/' + tk + '.json'
    if not os.path.exists(mp): continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; tot += 1
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    first = None; any_adm = False; any_adm_m3 = False
    for r in rows:
        if not (0 < r['tau'] <= 120) or r.get('gap') is None or r.get('state') not in ('LOCKED', 'PROVEN LOCKED') or r.get('pFlip') is None or r['pFlip'] > 0.002: continue
        h, R = hR(r); h3, R3 = hR(r, 3.0)
        if R >= RS[h]:
            adm_rows += 1; any_adm = True
            if (r.get('brtiAgeMs') or 0) > 2500: stale += 1
            if first is None:
                first = r; side = 'UP' if r['gap'] > 0 else 'DOWN'; lost = side != truth; lost_adm += int(lost)
                if abs(r['gap']) / r['strike'] * 1e4 < 5: sub5 += 1; sub5lost += int(lost)
        if R3 >= RS[h3]: adm_rows_minus3 += 1; any_adm_m3 = True
    win_adm += int(any_adm); win_adm_m3 += int(any_adm_m3)
print('settled live windows %d; PR11 first-admitted entries %d (lost %d); of which raw cushion < 5 bps: %d (lost %d)' % (tot, win_adm, lost_adm, sub5, sub5lost))
print('admitted row-seconds %d; with the index 3 bps less favourable: %d (%.1f%%); windows with any admitted second %d -> %d' % (adm_rows, adm_rows_minus3, 100 * adm_rows_minus3 / max(1, adm_rows), win_adm, win_adm_m3))
print('admitted row-seconds with official reference older than 2.5 s: %d' % stale)
