"""Live feature table (round 4). Inputs: production per-second rows (r30/live/scoreboard/rows), market results (scoreboard/markets),
observer window lines (r30/live/observer_lines.txt and, if present, round4/causal/observer_backfill/observer_lines_nov02_nov09.txt).
Outputs: live_features.ndjson (one row per market with each entry rule's first row and post-entry dynamics for the displayed rule),
live_tables.txt. Entry rules on rows with 0 < tau <= 120 and state LOCKED/PROVEN LOCKED: R_lock (any), R_disp (pFlip < 0.0025),
R_exact (pFlip <= 0.002), R_01 (pFlip <= 0.001), R_pfc (pFlipCons <= 0.001). Prices: ask is the recorded ask of the called side."""
import json, glob, os, re, sys, statistics as st, math, datetime
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R4 = SC + '/round4/causal'
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
RULES = {'R_lock': lambda r: True, 'R_disp': lambda r: r.get('pFlip') is not None and r['pFlip'] < 0.0025, 'R_exact': lambda r: r.get('pFlip') is not None and r['pFlip'] <= 0.002,
         'R_01': lambda r: r.get('pFlip') is not None and r['pFlip'] <= 0.001, 'R_pfc': lambda r: r.get('pFlipCons') is not None and r['pFlipCons'] <= 0.001}
mk = {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(L + '/scoreboard/markets/*.json')}
out = []; 
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; m = mk.get(tk)
    if not m or m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rs = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    rs = [r for r in rs if r.get('tau') is not None]
    rec = {'tk': tk, 'truth': truth, 'strike': rs[0].get('strike') if rs else None, 'rules': {}}
    for name, cond in RULES.items():
        e = next((r for r in rs if 0 < r['tau'] <= 120 and isL(r.get('state')) and cond(r)), None)
        if not e: rec['rules'][name] = None; continue
        sgn = 1 if e['side'] == 'UP' else -1; strike = e.get('strike') or rec['strike']
        cush = (sgn * e['gap'] / strike * 1e4) if (e.get('gap') is not None and strike) else None
        # pre-entry cushion change over 20 s and 10 s (rows at tau+20, tau+10 if present)
        def cush_at(tau_target):
            cand = [r for r in rs if r.get('gap') is not None and abs(r['tau'] - tau_target) <= 0.6]
            return (sgn * cand[0]['gap'] / strike * 1e4) if cand and strike else None
        c20, c10 = cush_at(e['tau'] + 20), cush_at(e['tau'] + 10)
        rr = {'tau': e['tau'], 'side': e['side'], 'won': e['side'] == truth, 'ask': e.get('ask'), 'pFlip': e.get('pFlip'), 'pFlipCons': e.get('pFlipCons'), 'cushionBps': round(cush, 2) if cush is not None else None,
              'cushChg20': round(cush - c20, 2) if (cush is not None and c20 is not None) else None, 'cushChg10': round(cush - c10, 2) if (cush is not None and c10 is not None) else None,
              'sigma': e.get('sigma'), 'regime': e.get('regime'), 'offDiv': e.get('offDiv'), 'brtiAgeMs': e.get('brtiAgeMs'), 'soft': e.get('gatesSoft'), 'hard': e.get('gatesHard'), 'ref': e.get('ref')}
        # post-entry dynamics
        after = [r for r in rs if r['tau'] < e['tau'] and r.get('pFlip') is not None and r.get('state') not in ('DATA UNRELIABLE', 'AWAITING SETTLEMENT') and r.get('side')]
        risk = lambda r: r['pFlip'] if r['side'] == e['side'] else 1 - r['pFlip']
        mx = max((risk(r) for r in after), default=None)
        first = {}
        for thr in (0.005, 0.01, 0.02, 0.10):
            f = next((r for r in after if risk(r) >= thr), None); first[str(thr)] = f['tau'] if f else None
        cushes = [sgn * r['gap'] / strike * 1e4 for r in after if r.get('gap') is not None and strike]
        rr.update({'maxRiskAfter': mx, 'firstTauAt': first, 'minCushionAfterBps': round(min(cushes), 2) if cushes else None, 'crossed': bool(cushes) and min(cushes) < 0,
                   'warned': mx is not None and mx >= 0.10, 'lockLost': mx is not None and mx >= 0.005})
        rec['rules'][name] = rr
    out.append(rec)
json.dump(out, open(R4 + '/live_features.json', 'w'))
# ---- tables
Ls = []
def q(xs, p):
    xs = sorted(xs); 
    if not xs: return None
    k = (len(xs) - 1) * p; f = math.floor(k); c = min(f + 1, len(xs) - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)
Ls.append('LIVE MARKETS: %d with results (rows cover the final 300 s)' % len(out))
for name in RULES:
    es = [r['rules'][name] for r in out if r['rules'][name]]
    lost = [e for e in es if not e['won']]
    asks = [e['ask'] for e in es if e.get('ask') is not None]
    Ls.append('%-7s entries %3d (%.0f %% of markets), lost %d, median tau %.1f | ask: n %d median %.1f, p25 %.1f, p75 %.1f, share >= 99.5: %.0f %%, share < 99: %.0f %%' % (
        name, len(es), 100 * len(es) / len(out), len(lost), st.median([e['tau'] for e in es]) if es else float('nan'), len(asks), st.median(asks) if asks else float('nan'), q(asks, .25) or 0, q(asks, .75) or 0,
        100 * sum(1 for a in asks if a >= 99.5) / max(1, len(asks)), 100 * sum(1 for a in asks if a < 99) / max(1, len(asks))))
Ls.append('')
es = [r['rules']['R_disp'] for r in out if r['rules']['R_disp']]
def bins(key, edges, labels):
    rows = []
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        sub = [e for e in es if e.get(key) is not None and lo <= e[key] < hi]
        rows.append('%s: %d entries, %d lost, %d warned (>=10 %%), %d lock lost (>=0.5 %%)' % (lab, len(sub), sum(1 for e in sub if not e['won']), sum(1 for e in sub if e['warned']), sum(1 for e in sub if e['lockLost'])))
    return rows
Ls.append('R_disp by tau at entry: ' + ' | '.join(bins('tau', [0, 30, 60, 90, 119.9, 121], ['<30', '30-59', '60-89', '90-119', '120'])))
Ls.append('R_disp by cushion bps: ' + ' | '.join(bins('cushionBps', [-1e9, 5, 10, 20, 40, 1e9], ['<5', '5-10', '10-20', '20-40', '>=40'])))
Ls.append('R_disp by 20 s cushion change (bps): ' + ' | '.join(bins('cushChg20', [-1e9, -5, -1, 1, 5, 1e9], ['<-5', '-5..-1', '-1..1', '1..5', '>5'])))
Ls.append('R_disp by regime: ' + ' | '.join(bins('regime', [0, 2, 4, 7], ['0-1 quiet', '2-3 normal', '4-6 active'])))
Ls.append('R_disp by |offDiv| USD: ' + ' | '.join('%s: %d entries, %d lost' % (lab, len(sub), sum(1 for e in sub if not e['won'])) for lab, sub in [(lab, [e for e in es if e.get('offDiv') is not None and lo <= abs(e['offDiv']) < hi]) for lo, hi, lab in [(0, 2, '<2'), (2, 5, '2-5'), (5, 10, '5-10'), (10, 1e9, '>=10')]]))
Ls.append('')
Ls.append('R_disp entries that reached a warning (entry-side risk >= 10 %) after entry, and the losses:')
for r in out:
    e = r['rules']['R_disp']
    if e and (e['warned'] or not e['won']):
        Ls.append('  %s %s won=%s tau %.1f ask %s pf %.4f cushion %.1f bps chg20 %s sigma %s regime %s | max risk %.3f, first >=0.5%% at tau %s, >=1%% %s, >=10%% %s, min cushion %s bps, crossed %s' % (
            r['tk'][-13:], e['side'], e['won'], e['tau'], e['ask'], e['pFlip'], e['cushionBps'] or 0, e['cushChg20'], e['sigma'], e['regime'], e['maxRiskAfter'] or 0, e['firstTauAt']['0.005'], e['firstTauAt']['0.01'], e['firstTauAt']['0.1'], e['minCushionAfterBps'], e['crossed']))
# ---- observer lines (primary rule <= 0.2 %): entries by tau bin and outcome
files = [L + '/observer_lines.txt', R4 + '/observer_backfill/observer_lines_nov02_nov09.txt']
seen = {}; 
for f in files:
    if not os.path.exists(f): continue
    for line in open(f):
        m = re.search(r'\[window\] (KXBTC15M-\S+) close=(\S+) .*?primary\(pinradar-primary-v1\) (new-crossing|existing-lock) at \S+ tau=([\d.]+)s (UP|DOWN) pFlip=([\d.e-]+) (PROVEN LOCKED|LOCKED)(.*?)\| later: lostLocked=(\S+) pFlip>0.2%=(\S+) warning=(\S+) .*?settlement=(yes|no)', line)
        if not m or 'coverage=complete' not in line and 'coverage=partial' not in line: continue
        tk = m.group(1)
        if tk in seen: continue
        ask = re.search(r'ask=([\d.]+)c', m.group(8)); dep = re.search(r'sizeAtAsk=([\d.]+)', m.group(8))
        truth = 'UP' if m.group(12) == 'yes' else 'DOWN'
        seen[tk] = {'tau': float(m.group(4)), 'side': m.group(5), 'pf': float(m.group(6)), 'ask': float(ask.group(1)) if ask else None, 'sizeAtAsk': float(dep.group(1)) if dep else None, 'noOffer': 'NO OFFER' in m.group(8),
                    'won': m.group(5) == truth, 'lostLocked': m.group(9) != 'no', 'warning': m.group(11) != 'no', 'close': m.group(2)}
O = list(seen.values())
Ls.append('')
Ls.append('OBSERVER primary rule (<= 0.2 %% centre, final 120 s): %d entries (%s .. %s), %d lost, %d with no offer on the called side' % (len(O), min(o['close'] for o in O) if O else '', max(o['close'] for o in O) if O else '', sum(1 for o in O if not o['won']), sum(1 for o in O if o['noOffer'])))
for lo, hi, lab in [(0, 30, '<30'), (30, 60, '30-59'), (60, 90, '60-89'), (90, 119.9, '90-119'), (119.9, 121, '120')]:
    sub = [o for o in O if lo <= o['tau'] < hi]; asks = [o['ask'] for o in sub if o['ask'] is not None]
    Ls.append('  tau %s: %d entries, %d lost, %d warned, %d lock lost | ask median %s, share >= 99.5: %s' % (lab, len(sub), sum(1 for o in sub if not o['won']), sum(1 for o in sub if o['warning']), sum(1 for o in sub if o['lostLocked']), ('%.1f' % st.median(asks)) if asks else '—', ('%.0f %%' % (100 * sum(1 for a in asks if a >= 99.5) / len(asks))) if asks else '—'))
Ls.append('  losses: ' + '; '.join('%s tau %.1f %s pf %.4f ask %s' % (o['close'], o['tau'], o['side'], o['pf'], o['ask']) for o in O if not o['won']))
open(R4 + '/live_tables.txt', 'w').write('\n'.join(Ls) + '\n'); print('\n'.join(Ls))
