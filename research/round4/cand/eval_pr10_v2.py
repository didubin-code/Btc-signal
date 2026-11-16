"""v2 (2026-11-16): versioned corrections after the two adversarial reviews; the original eval_pr10.py / eval_pr10.txt are preserved unchanged.
Corrections: (1) TEST split = the declared 2026-09-01 (v1 constant was 2026-09-05); (2) A6: a null ask is NO OFFER (LOCKED - TOO LATE, empty
ladder) and counts against the criterion, with the declared denominator (entries later than production) and all entries; (3) A4 verdicts
printed per clause (FIT point rate <= 0.5 %% for every admitted entry; TEST rate <= 1 %% for every admitted entry); (4) live basis mean from the
nearest preceding /health copy (basis.mean) when the window has no tape row, instead of a constant; (5) a missing or n<20 cell falls back to the
next smaller populated cushion bin of the same horizon and regime (fail closed: no floor -> no admission if none); (6) optional sensitivity
SIGMA_SCALE (env) multiplies the live raw sigma before bucketing (the FIT feed reads 1.19x the live raw sigma: review_settlement.md finding 1).
PR10 evaluation (criteria frozen in PR10_DECLARATION.md). Candidate: displayed risk = max(pf, p_emp(h, g, c)) with p_emp from the
FIT cells (windows before 2026-09-01); LOCKED iff production LOCKED/PROVEN and displayed <= 0.5 %; entry rules exact (<= 0.2 %) and
rounded (< 0.25 %) in the final 120 s. Sets: TEST replay (Sep 1 - Nov 12, usdc traces) and LIVE rows (Nov 12-16). Incidents table
for Nov 7, 9, 11 (replay traces, reconstruction) and Nov 14 00:15, Nov 15 18:30 (production rows).
usage: python3 -I eval_pr10.py <cells.json> <out_full_mu dir> <out prefix>"""
import json, sys, gzip, glob, os, math, collections, time, statistics as st
SIGMA_SCALE = float(os.environ.get('SIGMA_SCALE', '1.0')); SPLIT = 1788220800   # 2026-09-01T00:00:00Z (declared)
SIG_EDGES = [0.15, 0.22, 0.3, 0.4, 0.55, 0.8]
def bucket_of(sig_raw):
    b = 0
    for e in SIG_EDGES:
        if sig_raw >= e: b += 1
    return b
cells_f, D, outp = sys.argv[1], sys.argv[2], sys.argv[3]
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R3 = SC + '/round3'
C = json.load(open(cells_f)); FIT, TEST = C['FIT'], C['TEST']
CB = [0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35, 37.5, 40, 50, 75, 1e9]
def cbin(c):
    for lo, hi in zip(CB, CB[1:]):
        if lo <= c < hi: return '%g-%g' % (lo, hi if hi < 1e9 else 999)
def grp(bk): return 'quiet' if bk <= 1 else 'normal' if bk <= 3 else 'active'
def hround(tau): return int(min(120, max(20, 10 * math.ceil(tau / 10 - 1e-9))))
def p_emp(tau, bk, c_bps, table=FIT):
    h, g = hround(tau), grp(bk); key = '%d|%s|%s' % (h, g, cbin(c_bps)); cell = table.get(key)
    if cell and cell['n'] >= 20: return cell['rate'], key, cell
    # v2 (5): fall back to the next smaller populated cushion bin (a smaller cushion is riskier, so the floor is conservative)
    i = next((j for j, (lo, hi) in enumerate(zip(CB, CB[1:])) if lo <= c_bps < hi), None)
    while i is not None and i > 0:
        i -= 1; k2 = '%d|%s|%s' % (h, g, '%g-%g' % (CB[i], CB[i + 1] if CB[i + 1] < 1e9 else 999)); c2 = table.get(k2)
        if c2 and c2['n'] >= 20: return c2['rate'], key + '->' + k2, c2
    return 1.0, key + '->none', None   # fail closed
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
def evaluate(rows, truth, strike, mu_fn):
    """rows: list of dicts with tau, st, side, pf, gap, bk (sorted by tau desc, final 120 s and before). Returns per-rule results."""
    out = {}
    for rule, cond in (('exact', lambda d: d <= 0.002), ('disp', lambda d: d < 0.0025)):
        prod = cand = None; first_withheld = None
        for r in rows:
            if not (0 < r['tau'] <= 120) or r['pf'] is None: continue
            mu = mu_fn(r); ce = r['gap'] + mu; c_bps = abs(ce) / strike * 1e4
            pe, key, cell = p_emp(r['tau'], r['bk'], c_bps)
            disp = max(r['pf'], pe if pe is not None else 0.0) if r['st'] != 'PROVEN LOCKED' else r['pf']
            lockc = isL(r['st']) and disp <= 0.005
            if prod is None and isL(r['st']) and cond(r['pf']):
                prod = {'tau': r['tau'], 'pf': r['pf'], 'side': r['side'], 'c_bps': c_bps, 'bk': r['bk'], 'ask': r.get('ask')}
            if prod is not None and cand is None and isL(r['st']) and cond(r['pf']) and not (lockc and cond(disp)) and first_withheld is None:
                first_withheld = {'tau': r['tau'], 'disp': disp, 'p_emp': pe, 'cell': key}
            if cand is None and lockc and cond(disp):
                cand = {'tau': r['tau'], 'disp': disp, 'pf': r['pf'], 'p_emp': pe, 'cell': key, 'side': r['side'], 'c_bps': c_bps, 'bk': r['bk'], 'ask': r.get('ask'),
                        'cell_fit_rate': cell['rate'] if cell else None, 'cell_test': (TEST.get(key) or {}).get('rate')}
        out[rule] = {'prod': prod, 'cand': cand, 'first_withheld': first_withheld,
                     'prod_won': (prod['side'] == truth) if prod else None, 'cand_won': (cand['side'] == truth) if cand else None}
    return out
# ---------- TEST replay set
win = {}
for f in sorted(glob.glob(D + '/usdc_*.ndjson')):
    if '.sum.' in f or '.loser.' in f: continue
    for l in open(f):
        r = json.loads(l)
        if r['closeTs'] >= SPLIT: win[r['ticker']] = {'truth': r['truth'], 'strike': r['strike'], 'closeTs': r['closeTs'], 'm': r['marginUsd']}
traces = collections.defaultdict(list)
for f in sorted(glob.glob(D + '/usdc_*.trace.ndjson.gz')):
    if not any(x in f for x in ('usdc_08', 'usdc_09', 'usdc_10', 'usdc_11')): continue
    with gzip.open(f, 'rt') as fh:
        for l in fh:
            r = json.loads(l)
            if r['tk'] in win: traces[r['tk']].append(r)
res_test = {}
for tk, w in win.items():
    rs = sorted(traces.get(tk, []), key=lambda r: -r['tau'])
    if not rs: continue
    res_test[tk] = evaluate(rs, w['truth'], w['strike'], lambda r: r.get('mu') or 0.0); res_test[tk]['m'] = w['m']; res_test[tk]['closeTs'] = w['closeTs']
# ---------- LIVE set
mu_tape = {}
for l in open(R3 + '/tape/tape_all.ndjson'):
    try: r = json.loads(l)
    except Exception: continue
    tk = (r.get('kal') or {}).get('ticker')
    if tk and r.get('basisMu') is not None and tk not in mu_tape: mu_tape[tk] = r['basisMu']
mk = {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(L + '/scoreboard/markets/*.json')}
HC = []
for hp in glob.glob(L + '/health/health_*.json') + glob.glob(R3 + '/tape/health/health_*.json'):
    try:
        h = json.load(open(hp)); b = h.get('basis') or {}
        if h.get('ts') and b.get('mean') is not None: HC.append((h['ts'], float(b['mean'])))
    except Exception: pass
HC.sort()
def mu_health(close_ms):
    prev = [m for t, m in HC if t <= close_ms]
    if prev: return prev[-1], 'health-prev'
    nxt = [m for t, m in HC if t > close_ms]
    return (nxt[0], 'health-next') if nxt else (0.0, 'none')
MU_SRC = collections.Counter()
res_live = {}
for p in sorted(glob.glob(L + '/scoreboard/rows/*.ndjson')):
    tk = os.path.basename(p)[:-7]; m = mk.get(tk)
    if not m or m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rs = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    rows = [{'tau': r['tau'], 'st': r.get('state'), 'side': r.get('side'), 'pf': r.get('pFlip'), 'gap': r.get('gap'),
             'bk': (bucket_of(float(r['sigma']) / 1.03 * SIGMA_SCALE) if (SIGMA_SCALE != 1.0 and r.get('sigma') is not None) else r.get('regime')), 'ask': r.get('ask')}
            for r in rs if r.get('tau') is not None and r.get('gap') is not None and r.get('regime') is not None and r.get('strike')]
    if not rows: continue
    strike = rs[0].get('strike') or float(m.get('strike') or 0)
    if tk in mu_tape: mu, src = mu_tape[tk], 'tape'
    else: mu, src = mu_health(int(rs[0]['ts'] + 1000 * rs[0]['tau']))   # close time from the first row
    MU_SRC[src] += 1
    res_live[tk] = evaluate(rows, truth, strike, lambda r: mu); res_live[tk]['mu'] = mu; res_live[tk]['mu_src'] = src; res_live[tk]['m'] = (float(m['official']) - strike) if m.get('official') else None
def summarize(res, label):
    Ls = ['== %s: %d windows' % (label, len(res))]
    for rule in ('exact', 'disp'):
        P = [(tk, v[rule]) for tk, v in res.items() if v[rule]['prod']]
        Cn = [(tk, v[rule]) for tk, v in res.items() if v[rule]['cand']]
        pl = sum(1 for tk, v in P if v['prod_won'] is False); cl = sum(1 for tk, v in Cn if v['cand_won'] is False)
        delays = [v['prod']['tau'] - v['cand']['tau'] for tk, v in P if v['cand']]
        withheld = [tk for tk, v in P if not v['cand']]
        prevented = [tk for tk, v in P if v['prod_won'] is False and not v['cand']]
        not_prev = [tk for tk, v in P if v['prod_won'] is False and v['cand'] and v['cand_won'] is False]
        a4_fit = sum(1 for tk, v in Cn if (v['cand']['cell_fit_rate'] or 0) > 0.005); a4_test = sum(1 for tk, v in Cn if v['cand']['cell_test'] is not None and v['cand']['cell_test'] > 0.01)
        asks_ok = [v['cand']['ask'] for tk, v in Cn if v['cand'].get('ask') is not None]
        later = [(tk, v) for tk, v in P if v['cand'] and v['cand']['tau'] < v['prod']['tau'] - 1e-6]
        a6_later_ok = sum(1 for tk, v in later if v['cand'].get('ask') is not None and v['cand']['ask'] <= 99.9); a6_all_ok = sum(1 for tk, v in Cn if v['cand'].get('ask') is not None and v['cand']['ask'] <= 99.9)
        prod_nooffer = sum(1 for tk, v in P if v['prod'].get('ask') is None)
        Ls.append('  rule %s v2 VERDICTS: A1 %s (candidate losses %d vs production %d, new losses %s) | A2 %s (coverage %.1f %%) | A4 FIT clause %s (%d admitted entries in cells with FIT rate > 0.5 %%), A4 TEST clause %s (%d in cells with TEST rate > 1 %%) | A6 %s: offers <= 99.9 at %d of %d later-than-production entries (%.0f %%; null ask = no offer) and %d of %d all entries (%.0f %%); production itself had no offer at %d of %d entries' % (
            rule, 'PASS' if (cl <= pl and not [t for t, v in Cn if v['cand_won'] is False and (next((x for x in P if x[0] == t), (None, {'prod_won': True}))[1]['prod_won'] is not False)]) else 'FAIL', cl, pl, [t[-14:] for t, v in Cn if v['cand_won'] is False and (next((x for x in P if x[0] == t), (None, {'prod_won': True}))[1]['prod_won'] is not False)],
            'PASS' if 100 * len(Cn) / max(1, len(P)) >= 85 else 'FAIL', 100 * len(Cn) / max(1, len(P)), 'PASS' if a4_fit == 0 else 'FAIL', a4_fit, 'PASS' if a4_test == 0 else 'FAIL', a4_test,
            'PASS' if (later and 100 * a6_later_ok / len(later) >= 90) else 'FAIL', a6_later_ok, len(later), 100 * a6_later_ok / max(1, len(later)), a6_all_ok, len(Cn), 100 * a6_all_ok / max(1, len(Cn)), prod_nooffer, len(P)))
        Ls.append('  rule %s: production entries %d (losses %d, 1 in %s) | candidate entries %d (losses %d, 1 in %s) | coverage %.1f %% (A2 >= 85) | withheld for good %d | losses prevented %s | losses not prevented (delayed, still lost) %s | delay median %.1f s, >60 s %.1f %% (A3) | A4: entries in cells with FIT rate > 0.5 %%: %d, TEST rate > 1 %%: %d | asks at candidate entries <= 99.9: %d of %d' % (
            rule, len(P), pl, ('%.0f' % (len(P) / pl)) if pl else 'inf', len(Cn), cl, ('%.0f' % (len(Cn) / cl)) if cl else 'inf', 100 * len(Cn) / max(1, len(P)), len(withheld), [t[-14:] for t in prevented], [t[-14:] for t in not_prev],
            st.median(delays) if delays else 0, 100 * sum(1 for d in delays if d > 60) / max(1, len(delays)), a4_fit, a4_test, sum(1 for a in asks_ok if a <= 99.9), len(asks_ok)))
        # delayed-loss detail
        for tk, v in P:
            if v['prod_won'] is False:
                Ls.append('    LOSS %s: production %s tau %.1f pf %.4f cushion %.1f bps bk %s | candidate: %s' % (tk[-14:], rule, v['prod']['tau'], v['prod']['pf'], v['prod']['c_bps'], v['prod']['bk'],
                          ('entry tau %.1f disp %.4f (p_emp %s, cell %s)' % (v['cand']['tau'], v['cand']['disp'], ('%.4f' % v['cand']['p_emp']) if v['cand']['p_emp'] is not None else '-', v['cand']['cell'])) if v['cand'] else 'WITHHELD for the whole window (first withheld at tau %.1f, disp %.4f, cell %s)' % (v['first_withheld']['tau'], v['first_withheld']['disp'], v['first_withheld']['cell']) if v['first_withheld'] else 'no entry'))
    return Ls
Ls = ['PR10 EVALUATION v2 (corrections 1-6 in the header; cells %s; SIGMA_SCALE %.3f; FIT cells from windows before 2026-09-01; TEST = Sep 1-Nov 12 replay usdc; LIVE = production rows %s)' % (os.path.basename(cells_f), SIGMA_SCALE, time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime()))]
Ls.append('live basis-mean sources: %s (tape = window on the tape; health-prev = nearest preceding /health copy; none = 0)' % dict(MU_SRC))
Ls += summarize(res_test, 'TEST replay'); Ls += summarize(res_live, 'LIVE production rows')
# ---------- incidents (section 6)
inc = [('KXBTC15M-26NOV071730-30', 'Nov 7 22:30 UTC (replay reconstruction)'), ('KXBTC15M-26NOV092000-00', 'Nov 9 01:00 UTC (replay reconstruction)'), ('KXBTC15M-26NOV110415-15', 'Nov 11 09:15 UTC (replay reconstruction)'),
       ('KXBTC15M-26NOV131915-15', 'Nov 14 00:15 UTC (production rows)'), ('KXBTC15M-26NOV151330-30', 'Nov 15 18:30 UTC (production rows)')]
Ls.append(''); Ls.append('== INCIDENTS (chronological candidate replay; the move time = first second the entry side risk reached 1 %)')
for tk, lab in inc:
    src = res_test.get(tk) or res_live.get(tk)
    if not src: Ls.append('  %s: not in the evaluated sets' % lab); continue
    # move time from the rows
    rows = sorted(traces.get(tk, []), key=lambda r: -r['tau']) if tk in traces else None
    if rows is None:
        rs = sorted((json.loads(x) for x in open('%s/scoreboard/rows/%s.ndjson' % (L, tk)) if x.strip()), key=lambda r: -r['tau'])
        rows = [{'tau': r['tau'], 'pf': r.get('pFlip'), 'side': r.get('side'), 'st': r.get('state')} for r in rs]
    for rule in ('exact', 'disp'):
        v = src[rule]; prod = v['prod']
        if not prod: Ls.append('  %s | rule %s: NOT QUALIFYING (no production entry under this rule)' % (lab, rule)); continue
        side = prod['side']; risk = lambda r: (r['pf'] if r['side'] == side else 1 - r['pf']) if r['pf'] is not None else None
        mv = next((r['tau'] for r in rows if r['tau'] < prod['tau'] and risk(r) is not None and risk(r) >= 0.01), None)
        cand = v['cand']; fw = v['first_withheld']
        if cand and cand['tau'] >= prod['tau'] - 1e-6: cls = 'NOT PREVENTED (candidate admitted the same entry)'
        elif cand and mv is not None and cand['tau'] > mv: cls = 'NOT PREVENTED (withheld at %.1f s, admitted at %.1f s before the move at %.1f s)' % (fw['tau'], cand['tau'], mv)
        elif cand and (mv is None or cand['tau'] <= mv): cls = 'ENTRY PREVENTED before the move (admitted only at %.1f s, after the move at %s s)' % (cand['tau'], ('%.1f' % mv) if mv is not None else 'none') if v['prod_won'] is False else 'withheld then admitted later (winner)'
        else: cls = 'ENTRY PREVENTED (no candidate entry in the window)' if v['prod_won'] is False else 'withheld for the whole window (winner)'
        Ls.append('  %s | rule %s: production entry tau %.1f pf %.4f (cushion %.1f bps, bk %s, won %s) | candidate at that moment: %s | later candidate entry: %s | move at tau %s | lead (withholding before the move) %s s | %s' % (
            lab, rule, prod['tau'], prod['pf'], prod['c_bps'], prod['bk'], v['prod_won'], ('WITHHELD disp %.4f cell %s' % (fw['disp'], fw['cell'])) if fw and abs(fw['tau'] - prod['tau']) < 1e-6 else ('admitted' if cand and abs(cand['tau'] - prod['tau']) < 1e-6 else 'see classification'),
            ('tau %.1f disp %.4f' % (cand['tau'], cand['disp'])) if cand else 'none', ('%.1f' % mv) if mv is not None else 'none', ('%.1f' % (fw['tau'] - mv)) if (fw and mv is not None) else '-', cls))
json.dump({'test': res_test, 'live': res_live}, open(outp + '.json', 'w'))
open(outp + '.txt', 'w').write('\n'.join(Ls) + '\n'); print('\n'.join(Ls))
