"""Live production rows vs the usdc_12 replay chunk. Reads only finished outputs; writes compare.txt, loss_traces.txt, warned_traces.txt.
  python3 -I compare.py"""
import json, gzip, glob, os, statistics, datetime, hashlib
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
W, L, RP = SC + '/round4/replay_live', SC + '/r30/live/scoreboard', SC + '/incident_20261114T0015Z/replay_pub'
H = SC + '/r30/live/health'
UTC = datetime.timezone.utc
iso = lambda t: datetime.datetime.fromtimestamp(t, UTC).strftime('%Y-%m-%d %H:%M:%SZ')
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
EXACT = lambda pf: pf <= 0.002
DISP = lambda pf: pf < 0.0025
f6 = lambda x: 'None' if x is None else ('%.6f' % x)
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()

# ---------- replay (usdc_12) ----------
rec = {}
for l in open(W + '/out/usdc_12.ndjson'):
    r = json.loads(l); rec[r['ticker']] = r
tr = {}
with gzip.open(W + '/out/usdc_12.trace.ndjson.gz', 'rt') as f:
    for l in f:
        r = json.loads(l); tr.setdefault(r['tk'], []).append(r)
for k in tr: tr[k].sort(key=lambda r: -r['tau'])
# ---------- live ----------
live, lres = {}, {}
for p in sorted(glob.glob(L + '/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]
    rs = [json.loads(l) for l in open(p) if l.strip()]
    rs.sort(key=lambda r: -r['tau']); live[tk] = rs
    mp = L + '/markets/' + tk + '.json'
    lres[tk] = json.load(open(mp)) if os.path.exists(mp) else None
# live basis mean from saved /health copies (approximate; the rows carry no basis mean)
mus = []
for p in glob.glob(H + '/*.json'):
    try:
        h = json.load(open(p))
        if h.get('basis') and h['basis'].get('mean') is not None and h.get('ts'): mus.append((h['ts'], float(h['basis']['mean']), h['basis'].get('n')))
    except Exception: pass
mus.sort()
def mu_live(ts_ms):
    if not mus: return None
    return min(mus, key=lambda x: abs(x[0] - ts_ms))

def norm_live(r):
    return {'tau': r['tau'], 'st': r.get('state'), 'side': r.get('side'), 'pf': r.get('pFlip'), 'pfc': r.get('pFlipCons'), 'gap': r.get('gap'),
            'sig': r.get('sigma'), 'bk': r.get('regime'), 'ts': r.get('ts'), 'idx': r.get('idx'), 'spot': r.get('spot'), 'offDiv': r.get('offDiv'), 'mu': None}
def entry(rows, rule):
    for r in rows:
        if 0 < r['tau'] <= 120 and isL(r['st']) and r.get('pf') is not None and rule(r['pf']): return r
    return None
def first_locked(rows):
    for r in rows:
        if 0 < r['tau'] <= 120 and isL(r['st']): return r
    return None
def min_pf_locked(rows):
    v = [r['pf'] for r in rows if 0 < r['tau'] <= 120 and isL(r['st']) and r.get('pf') is not None]
    return min(v) if v else None
def at120(rows):
    for r in rows:
        if r['tau'] <= 120: return r
    return None
def truth_of(tk):
    t = rec[tk]['truth'] if tk in rec else None
    m = lres.get(tk)
    tl = {'yes': 'UP', 'no': 'DOWN'}.get((m or {}).get('result'))
    return t, tl
def desc(e, strike, truth, mu=None):
    if e is None: return 'no entry'
    sg = 1 if e['side'] == 'UP' else -1
    cush = e['gap'] * sg if e.get('gap') is not None else None
    s = 'tau %6.2f %-4s pf %s pfc %s gap %+8.2f (side-signed %+7.2f USD = %+6.2f bps) sigma %s bucket %s' % (
        e['tau'], e['side'], f6(e['pf']), f6(e['pfc']), e['gap'] if e.get('gap') is not None else float('nan'), cush if cush is not None else float('nan'),
        cush / strike * 1e4 if cush is not None else float('nan'), e.get('sig'), e.get('bk'))
    if e.get('mu') is not None: s += ' mu %+.2f' % e['mu']
    s += ' -> %s' % ('WON' if truth and e['side'] == truth else 'LOST' if truth else 'result unknown')
    return s

out = []
P = lambda *a: out.append(' '.join(str(x) for x in a))
P('LIVE PRODUCTION vs REPLAY (chunk usdc_12) — written %s' % datetime.datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))
P('=' * 120)
P('Replay chunk : %s/out/usdc_12.*' % W)
P('  engine     : %s/r29/builds/P/pinradar_server.js  sha256 %s' % (SC, sha(SC + '/r29/builds/P/pinradar_server.js')))
P('               (the file pr5_official.sh used for usdc_11; byte-identical to r30_pkg/r30/release_identity/production/pinradar_server.js)')
P('  prices     : Binance BTCUSDC 1 s klines (data.binance.vision daily archives) 2026-11-11 .. 2026-11-14; 2026-11-15 and 2026-11-16 NOT PUBLISHED (HTTP 404 NoSuchKey)')
P('  markets    : Kalshi public API /markets (settled KXBTC15M), closes 2026-11-11 00:00 .. 2026-11-16 01:00 UTC, 477 markets, 1 gap (Nov 12 08:15-10:00, 8 windows; also absent from the original markets_all.ndjson)')
P('  scored     : closes in [2026-11-12 16:30, 2026-11-15 00:15) UTC = %d windows (%s .. %s); warm-up 86400 s; basis samples at end %s' % (
    len(rec), min(rec, key=lambda t: rec[t]['closeTs']), max(rec, key=lambda t: rec[t]['closeTs']), open(W + '/out/usdc_12.log').readline().strip()))
P('Live rows    : %s/rows/<ticker>.ndjson, %d windows (%s .. %s); results from %s/markets/<ticker>.json' % (L, len(live), min(live), max(live), L))
P('  live build : P (sha256 0efd86c9...) until the redeploy at ~2026-11-13 23:00 UTC, then I2 (sha256 ca51a0c6..., ingestion revision, basis model restarted at n=0) — from the saved /health copies')
P('Rules        : exact = first row with 0 < tau <= 120, state LOCKED or PROVEN LOCKED, pFlip <= 0.002; displayed = same with pFlip < 0.0025.')
P('               live fields: tau,state,side,pFlip,pFlipCons,gap,sigma(=sigmaBps: raw x LIVE_VOL_SCALE 1.03 x input-age inflation),regime(bucket)')
P('               replay trace: tau,st,side,pf,pfc,gap,sig(=sigmaRawBps, unscaled),bk,mu(basis mean used). gap = expected settlement - strike, USD.')
P('')

# ---------- window sets ----------
common = sorted(t for t in live if t in rec)
only_live = sorted(t for t in live if t not in rec)
only_rep = sorted(t for t in rec if t not in live)
P('WINDOW SETS')
P('-' * 120)
P('windows in live set: %d | in replay chunk: %d | in BOTH: %d' % (len(live), len(rec), len(common)))
P('live windows not replayed: %d  (closes %s .. %s: all need 2026-11-15/16 prices, which the archive has not published)' % (len(only_live), only_live[0] if only_live else '-', only_live[-1] if only_live else '-'))
P('replay windows not in live: %d %s' % (len(only_rep), only_rep))
# truth agreement + live coverage
dis = [t for t in common if truth_of(t)[0] != truth_of(t)[1]]
P('result disagreement live vs replay (Kalshi result both ways): %d %s' % (len(dis), dis))
short = [(t, len(live[t]), live[t][0]['tau'], live[t][-1]['tau']) for t in common if not any(r['tau'] <= 1.5 for r in live[t]) or not any(r['tau'] >= 119 for r in live[t])]
P('live windows whose rows do not cover tau 120 .. ~1: %d %s' % (len(short), short[:10]))
P('replay windows with < 120 trace rows at tau <= 120: %d' % sum(1 for t in common if sum(1 for r in tr.get(t, []) if 0 < r['tau'] <= 120) < 120))
P('')

# ---------- entries ----------
E = {}
for t in common:
    strike = rec[t]['strike']
    lrows = [norm_live(r) for r in live[t]]
    rrows = tr.get(t, [])
    E[t] = {'strike': strike, 'truth': truth_of(t)[0], 'live': {'exact': entry(lrows, EXACT), 'disp': entry(lrows, DISP), 'fl': first_locked(lrows), 'minpf': min_pf_locked(lrows), 'at120': at120(lrows)},
            'rep': {'exact': entry(rrows, EXACT), 'disp': entry(rrows, DISP), 'fl': first_locked(rrows), 'minpf': min_pf_locked(rrows), 'at120': at120(rrows)}}
for rule, label in (('exact', 'EXACT RULE  (LOCKED, pFlip <= 0.002, 0 < tau <= 120)'), ('disp', 'DISPLAYED RULE (LOCKED, pFlip < 0.0025, 0 < tau <= 120)')):
    P(label); P('-' * 120)
    nl = sum(1 for t in common if E[t]['live'][rule]); nr = sum(1 for t in common if E[t]['rep'][rule]); nb = sum(1 for t in common if E[t]['live'][rule] and E[t]['rep'][rule])
    nn = sum(1 for t in common if not E[t]['live'][rule] and not E[t]['rep'][rule])
    P('entries: live %d | replay %d | both %d | neither %d   (of %d common windows)' % (nl, nr, nb, nn, len(common)))
    ll = [t for t in common if E[t]['live'][rule] and E[t]['truth'] and E[t]['live'][rule]['side'] != E[t]['truth']]
    lr = [t for t in common if E[t]['rep'][rule] and E[t]['truth'] and E[t]['rep'][rule]['side'] != E[t]['truth']]
    P('losses (entry side != result): live %d %s | replay %d %s' % (len(ll), ll, len(lr), lr))
    sides = [t for t in common if E[t]['live'][rule] and E[t]['rep'][rule] and E[t]['live'][rule]['side'] != E[t]['rep'][rule]['side']]
    P('both entered with different sides: %d %s' % (len(sides), sides))
    d = [(t, E[t]['rep'][rule]['tau'] - E[t]['live'][rule]['tau']) for t in common if E[t]['live'][rule] and E[t]['rep'][rule]]
    if d:
        v = sorted(x for _, x in d)
        P('tau difference replay - live (s), windows with entries in both (n=%d): median %+.2f mean %+.2f min %+.2f max %+.2f; p10 %+.2f p90 %+.2f' % (
            len(v), statistics.median(v), statistics.mean(v), v[0], v[-1], v[int(0.1 * (len(v) - 1))], v[int(0.9 * (len(v) - 1))]))
        bins = [(-1e9, -30, '< -30'), (-30, -10, '-30 .. -10'), (-10, -3, '-10 .. -3'), (-3, -1, '-3 .. -1'), (-1, 1, '-1 .. +1'), (1, 3, '+1 .. +3'), (3, 10, '+3 .. +10'), (10, 30, '+10 .. +30'), (30, 1e9, '> +30')]
        P('  histogram (replay earlier = positive):')
        for lo, hi, nm in bins:
            c = sum(1 for x in v if lo <= x < hi)
            P('    %-12s %4d %s' % (nm, c, '#' * c))
        P('  per-window tau differences (ticker: replay tau, live tau, diff):')
        for t, x in d:
            P('    %s: %6.2f %6.2f %+7.2f' % (t, E[t]['rep'][rule]['tau'], E[t]['live'][rule]['tau'], x))
    ol = [t for t in common if E[t]['live'][rule] and not E[t]['rep'][rule]]
    orp = [t for t in common if E[t]['rep'][rule] and not E[t]['live'][rule]]
    P('windows where ONLY LIVE entered: %d' % len(ol))
    for t in ol:
        e = E[t]['live'][rule]; o = E[t]['rep']
        P('    %s  live: %s' % (t, desc(e, E[t]['strike'], E[t]['truth'])))
        P('    %s  replay: first LOCKED %s; lowest LOCKED pFlip in final 120 s: %s' % (' ' * len(t), ('tau %.2f %s pf %s' % (o['fl']['tau'], o['fl']['side'], f6(o['fl']['pf']))) if o['fl'] else 'never LOCKED', f6(o['minpf'])))
    P('windows where ONLY REPLAY entered: %d' % len(orp))
    for t in orp:
        e = E[t]['rep'][rule]; o = E[t]['live']
        P('    %s  replay: %s' % (t, desc(e, E[t]['strike'], E[t]['truth'])))
        P('    %s  live: first LOCKED %s; lowest LOCKED pFlip in final 120 s: %s' % (' ' * len(t), ('tau %.2f %s pf %s' % (o['fl']['tau'], o['fl']['side'], f6(o['fl']['pf']))) if o['fl'] else 'never LOCKED', f6(o['minpf'])))
    P('')

# ---------- sigma at tau 120 ----------
P('SIGMA AT TAU 120 (first row with tau <= 120 in each engine; live sigma is sigmaBps = raw x 1.03 x inflation, replay sig is sigmaRawBps)'); P('-' * 120)
rat = []
for t in common:
    a, b = E[t]['rep']['at120'], E[t]['live']['at120']
    if a and b and a.get('sig') and b.get('sig'): rat.append((t, a['sig'], b['sig'], a['sig'] / b['sig']))
v = sorted(x[3] for x in rat)
P('windows with both values: %d | median ratio replay/live %.4f (p10 %.4f, p90 %.4f, mean %.4f) | median of ratio x 1.03 (removing LIVE_VOL_SCALE) %.4f' % (
    len(v), statistics.median(v), v[int(0.1 * (len(v) - 1))], v[int(0.9 * (len(v) - 1))], statistics.mean(v), statistics.median(v) * 1.03))
P('replay sig at 120: median %.4f | live sigma at 120: median %.4f' % (statistics.median(x[1] for x in rat), statistics.median(x[2] for x in rat)))
bk_same = sum(1 for t in common if E[t]['rep']['at120'] and E[t]['live']['at120'] and E[t]['rep']['at120'].get('bk') == E[t]['live']['at120'].get('bk'))
P('same volatility bucket at tau 120: %d of %d' % (bk_same, len(common)))
P('')

# ---------- server LOCKED at all (context) ----------
P('CONTEXT: first LOCKED row at any pFlip in the final 120 s'); P('-' * 120)
fl_l = sum(1 for t in common if E[t]['live']['fl']); fl_r = sum(1 for t in common if E[t]['rep']['fl'])
P('windows with any LOCKED row (tau <= 120): live %d | replay %d | both %d' % (fl_l, fl_r, sum(1 for t in common if E[t]['live']['fl'] and E[t]['rep']['fl'])))
wl = [t for t in common if E[t]['live']['fl'] and E[t]['truth'] and E[t]['live']['fl']['side'] != E[t]['truth']]
wr = [t for t in common if E[t]['rep']['fl'] and E[t]['truth'] and E[t]['rep']['fl']['side'] != E[t]['truth']]
P('first-LOCKED side wrong: live %d %s | replay %d %s' % (len(wl), wl, len(wr), wr))
P('')

# ---------- the named windows ----------
NAMED = [('LOSS', 'KXBTC15M-26NOV131915-15'), ('LOSS', 'KXBTC15M-26NOV151330-30'), ('WARNED-AND-WON', 'KXBTC15M-26NOV150830-30'), ('WARNED-AND-WON', 'KXBTC15M-26NOV151130-30'),
         ('WARNED-AND-WON', 'KXBTC15M-26NOV141330-30'), ('WARNED-AND-WON', 'KXBTC15M-26NOV151930-30')]
P('THE NAMED WINDOWS'); P('-' * 120)
def summarize_rows(rows, label, strike, truth):
    s = []
    e1, e2, fl = entry(rows, EXACT), entry(rows, DISP), first_locked(rows)
    s.append('  %s first LOCKED (tau<=120): %s' % (label, desc(fl, strike, truth) if fl else 'never LOCKED in the final 120 s'))
    s.append('  %s exact-rule entry       : %s' % (label, desc(e1, strike, truth)))
    s.append('  %s displayed-rule entry   : %s' % (label, desc(e2, strike, truth)))
    if fl:
        sg = 1 if fl['side'] == 'UP' else -1
        after = [r for r in rows if r['tau'] < fl['tau']]
        neg = next((r for r in after if r.get('gap') is not None and r['gap'] * sg < 0), None)
        left = next((r for r in after if not isL(r['st']) and r['st'] not in ('AWAITING SETTLEMENT',)), None)
        rw = next((r for r in after if r['st'] == 'REVERSAL WARNING'), None)
        mg = min((r['gap'] * sg for r in after if r.get('gap') is not None), default=None)
        s.append('  %s after the lock: gap first crossed the strike at %s; state first left LOCKED at %s; first REVERSAL WARNING at %s; smallest side-signed gap later %s' % (
            label, ('tau %.2f' % neg['tau']) if neg else 'never', ('tau %.2f (%s)' % (left['tau'], left['st'])) if left else 'never', ('tau %.2f' % rw['tau']) if rw else 'never', ('%+.2f USD' % mg) if mg is not None else 'n/a'))
    return s
for kind, t in NAMED:
    m = lres.get(t) or {}
    r = rec.get(t)
    strike = (r or {}).get('strike') or (float(m['strike']) if m.get('strike') else None)
    truth = truth_of(t)[0] or truth_of(t)[1]
    close = r['closeTs'] if r else None
    P('%s %s  close %s  strike %s  official %s  result %s  (replayed: %s)' % (kind, t, iso(close) if close else '(not in replay chunk; live close per ticker)', strike, (r or {}).get('official', m.get('official')), truth, 'yes' if t in tr else 'NO - needs 2026-11-15/16 prices, not published'))
    if t in live:
        for s in summarize_rows([norm_live(x) for x in live[t]], 'LIVE  ', strike, truth): P(s)
    else: P('  LIVE   : not in live set')
    if t in tr:
        for s in summarize_rows(tr[t], 'REPLAY', strike, truth): P(s)
    P('')

# ---------- overlap with usdc_11 (same engine, same prices, same markets; only the basis warm-up differs) ----------
P('DETERMINISM / WARM-UP CHECK: windows shared with the original usdc_11 chunk (closes 2026-11-12 16:30 .. 23:45)'); P('-' * 120)
rec11 = {}
for l in open(RP + '/out_full_mu/usdc_11.ndjson'):
    r = json.loads(l)
    if r['ticker'] in rec: rec11[r['ticker']] = r
tr11 = {}
with gzip.open(RP + '/out_full_mu/usdc_11.trace.ndjson.gz', 'rt') as f:
    for l in f:
        r = json.loads(l)
        if r['tk'] in rec11: tr11.setdefault(r['tk'], []).append(r)
ov = sorted(rec11)
same_rec = 0; diff_fields = {}
for t in ov:
    a = dict(rec[t]); b = dict(rec11[t]); a.pop('basisN', None); b.pop('basisN', None)
    if a == b: same_rec += 1
    else:
        for k in a:
            if a[k] != b.get(k): diff_fields[k] = diff_fields.get(k, 0) + 1
P('shared windows: %d | identical records (all fields except basisN): %d | fields differing: %s' % (len(ov), same_rec, diff_fields))
P('basisN at those windows: usdc_12 %s .. %s | usdc_11 %s .. %s' % (rec[ov[0]]['basisN'], rec[ov[-1]]['basisN'], rec11[ov[0]]['basisN'], rec11[ov[-1]]['basisN']))
n_rows = n_same = 0; dpf = dpfc = dmu = dsig = 0.0; st_diff = 0; ent_diff = []
for t in ov:
    A = {r['tau']: r for r in tr[t]}; B = {r['tau']: r for r in tr11.get(t, [])}
    for tau, ra in A.items():
        rb = B.get(tau)
        if rb is None: continue
        n_rows += 1
        if all(ra.get(k) == rb.get(k) for k in ('st', 'side', 'pf', 'pfc', 'gap', 'sig', 'bk', 'soft', 'hard', 'mu')): n_same += 1
        if ra.get('st') != rb.get('st') or ra.get('side') != rb.get('side'): st_diff += 1
        for k, acc in (('pf', 'dpf'), ('pfc', 'dpfc'), ('mu', 'dmu'), ('sig', 'dsig')):
            if ra.get(k) is not None and rb.get(k) is not None:
                v = abs(ra[k] - rb[k])
                if acc == 'dpf': dpf = max(dpf, v)
                elif acc == 'dpfc': dpfc = max(dpfc, v)
                elif acc == 'dmu': dmu = max(dmu, v)
                else: dsig = max(dsig, v)
    e12, e11 = entry(tr[t], EXACT), entry(tr11.get(t, []), EXACT)
    if (e12 or {}).get('tau') != (e11 or {}).get('tau') or (e12 or {}).get('side') != (e11 or {}).get('side'): ent_diff.append((t, (e12 or {}).get('tau'), (e11 or {}).get('tau')))
P('trace rows compared (same ticker and tau): %d | identical in all fields: %d | state/side differs: %d | max |d pf| %.3g, max |d pfc| %.3g, max |d mu| %.3g USD, max |d sig| %.3g' % (n_rows, n_same, st_diff, dpf, dpfc, dmu, dsig))
P('exact-rule entries differing (ticker, tau usdc_12, tau usdc_11): %d %s' % (len(ent_diff), ent_diff))
mu12 = [r['mu'] for t in ov for r in tr[t] if r.get('mu') is not None]; mu11 = [r['mu'] for t in ov for r in tr11.get(t, []) if r.get('mu') is not None]
P('basis mean (mu) over the shared rows: usdc_12 median %+.2f (min %+.2f max %+.2f) | usdc_11 median %+.2f (min %+.2f max %+.2f)' % (statistics.median(mu12), min(mu12), max(mu12), statistics.median(mu11), min(mu11), max(mu11)))
P('')
P('LIVE BASIS MEAN (from saved /health copies; the live rows carry none): %s' % '; '.join('%s n=%s mean=%+.3f' % (datetime.datetime.fromtimestamp(x[0] / 1000, UTC).strftime('%m-%d %H:%M'), x[2], x[1]) for x in mus[::6]))
P('REPLAY BASIS MEAN at the exact-rule entries: median %+.2f, range %+.2f .. %+.2f' % tuple(
    (statistics.median(v), min(v), max(v)) if (v := [E[t]['rep']['exact']['mu'] for t in common if E[t]['rep']['exact'] and E[t]['rep']['exact'].get('mu') is not None]) else (float('nan'),) * 3))
open(W + '/compare.txt', 'w').write('\n'.join(out) + '\n')

# ---------- trace files ----------
def live_table(rows):
    s = ['    %8s %6s %-18s %-4s %10s %10s %9s %8s %3s %10s %10s %7s %3s %10s %10s' % ('ts', 'tau', 'state', 'side', 'pFlip', 'pFlipCons', 'gap', 'sigma', 'rg', 'idx', 'spot', 'offDiv', 'n', 'recAvg', 'crit')]
    for r in rows:
        if r['tau'] > 125: continue
        s.append('    %8s %6.2f %-18s %-4s %10s %10s %9s %8s %3s %10s %10s %7s %3s %10s %10s' % (str(r['ts'])[-8:], r['tau'], r.get('state'), r.get('side'), r.get('pFlip'), r.get('pFlipCons'), r.get('gap'), r.get('sigma'), r.get('regime'), r.get('idx'), r.get('spot'), r.get('offDiv'), r.get('n'), r.get('recAvg'), r.get('crit')))
    return s
def write_traces(path, items, title):
    o = [title, '=' * 120, 'Replay trace rows are printed verbatim (JSON, one decision per second, tau 125 down to 0; fields tk,tau,st,side,pf,pfc,gap,sig,bk,soft,hard,mu).',
         'Live rows (production /predictions log, tau <= 125) follow as a table for the same window. gap = expected settlement - strike (USD); live sigma is scaled (x1.03), replay sig is raw.', '']
    for kind, t in items:
        r = rec.get(t); m = lres.get(t) or {}
        strike = (r or {}).get('strike') or (float(m['strike']) if m.get('strike') else None)
        truth = truth_of(t)[0] or truth_of(t)[1]
        o.append('#' * 120); o.append('%s %s  close %s  strike %s  official %s  result %s' % (kind, t, iso(r['closeTs']) if r else 'n/a (not replayed)', strike, (r or {}).get('official', m.get('official')), truth)); o.append('#' * 120)
        if t in tr:
            for s in summarize_rows(tr[t], 'REPLAY', strike, truth): o.append(s)
        else: o.append('  REPLAY: NOT REPLAYED — this window needs 2026-11-15/16 BTCUSDC 1 s prices, which data.binance.vision had not published at run time (HTTP 404 NoSuchKey).')
        if t in live:
            for s in summarize_rows([norm_live(x) for x in live[t]], 'LIVE  ', strike, truth): o.append(s)
        o.append('')
        if t in tr:
            o.append('--- REPLAY TRACE, tau 125 -> 0 (%d rows) ---' % len(tr[t]))
            for x in tr[t]: o.append(json.dumps(x, separators=(',', ':')))
            o.append('')
        if t in live:
            o.append('--- LIVE ROWS, tau <= 125 (%d rows) ---' % sum(1 for x in live[t] if x['tau'] <= 125))
            o.extend(live_table(live[t])); o.append('')
    open(path, 'w').write('\n'.join(o) + '\n')
write_traces(W + '/loss_traces.txt', [x for x in NAMED if x[0] == 'LOSS'], 'LOSS WINDOWS: replay trace (usdc_12) and live rows')
write_traces(W + '/warned_traces.txt', [x for x in NAMED if x[0] != 'LOSS'], 'WARNED-AND-WON WINDOWS: replay trace (usdc_12) and live rows')
print('\n'.join(out))
