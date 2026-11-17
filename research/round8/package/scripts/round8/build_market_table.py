"""Market-level comparison table: baseline (deployed I2 as served) vs candidate (PR11 build 9) under the owner's
entry rule, one entry per market. See round8/PLAN_R8.md (frozen). Inputs are the production server's own
per-second prediction rows (geometry, risk, reference state), its tape rows (order books, served state),
Kalshi finalized results, the frozen exposure table and the exact-replay dumps (D3) where 1-s samples exist.
usage: python3 -I build_market_table.py <config.json> <out dir>"""
import sys, json, glob, os, math, bisect, collections, csv, datetime
cfg = json.load(open(sys.argv[1])); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
RST = json.load(open(cfg['rstar']))['rstar']; RSTAR = {int(k): v for k, v in RST.items()}
I2_FIRST_CLOSE = cfg['i2_first_close_ms']; LAGS = cfg['lags']; BOOK_MAX_AGE = cfg['book_max_age_ms']; PRICES = cfg['prices']; SIZES = cfg['sizes']
# ---------- rows (prediction log) ----------
rows_by = {}; rows_src = {}
for src in cfg['rows_dirs']:
    for p in sorted(glob.glob(src['dir'] + '/*.ndjson')):
        tk = os.path.basename(p)[:-7]
        if tk in rows_by: continue
        rs = [json.loads(x) for x in open(p) if x.strip()]; rs.sort(key=lambda r: r['ts']); rows_by[tk] = rs; rows_src[tk] = src['label']
# ---------- results ----------
mk = {}; mk_src = {}
for src in cfg['markets_dirs']:
    for p in glob.glob(src['dir'] + '/*.json'):
        tk = os.path.basename(p)[:-5]; m = json.load(open(p))
        if tk not in mk and m.get('result') in ('yes', 'no'): mk[tk] = m; mk_src[tk] = src['label']
# ---------- tape: books, served state, reference ----------
books = collections.defaultdict(list); served = {}; tape_tk = set()
with open(cfg['tape']) as f:
    for line in f:
        try: r = json.loads(line)
        except Exception: continue
        if r.get('k') != 'd' or not r.get('kal'): continue
        tk = r['kal']['ticker']; tape_tk.add(tk)
        if r.get('ob'): books[tk].append((r.get('obTs') or r['ts'], r['ob']))
        served[(tk, r['ts'])] = r.get('out')
for tk in books: books[tk].sort()
BT = {tk: [b[0] for b in B] for tk, B in books.items()}
def levels(ob, side):
    other = ob.get('no') if side == 'UP' else ob.get('yes')
    lv = [(round(100 - p, 2), s) for p, s in (other or []) if s and s > 0]
    lv.sort(key=lambda x: x[0]); return lv
def offer_at(tk, ts, side, max_age=BOOK_MAX_AGE):
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right(BT[tk], ts) - 1
    if i < 0 or ts - B[i][0] > max_age: return {'book': False, 'ask': None, 'size': 0, 'age': None if i < 0 else ts - B[i][0]}
    lv = levels(B[i][1], side)
    o = {'book': True, 'age': ts - B[i][0], 'ask': lv[0][0] if lv else None, 'size': lv[0][1] if lv else 0}
    for p in PRICES: o['depth_le_%s' % p] = sum(s for a, s in lv if a <= p + 1e-9)
    o['ladder'] = [(a, s) for a, s in lv if a <= 99.9 + 1e-9]
    return o
def available(o): return bool(o and o.get('book') and o.get('ask') is not None and o['ask'] <= 99.9 + 1e-9 and o['size'] >= 10)
# ---------- D3 exact replay dumps ----------
d3 = {}; d3i2 = {}
for p in cfg['d3_b9']:
    for line in open(p):
        r = json.loads(line); d3[(r['ticker'], r['ts'])] = r
for p in cfg['d3_i2']:
    for line in open(p):
        r = json.loads(line); d3i2[(r['ticker'], r['ts'])] = r
d3_ts = collections.defaultdict(list)
for (tk, ts) in d3: d3_ts[tk].append(ts)
for tk in d3_ts: d3_ts[tk].sort()
def d3_row(tk, ts, tol=600):
    L = d3_ts.get(tk)
    if not L: return None
    i = bisect.bisect_left(L, ts); best = None
    for j in (i - 1, i):
        if 0 <= j < len(L) and abs(L[j] - ts) <= tol and (best is None or abs(L[j] - ts) < abs(best - ts)): best = L[j]
    return d3.get((tk, best)) if best is not None else None
# ---------- the rule on recorded fields (engine convention: h = ceil(tau), R scaled by 60/h once a print has passed) ----------
def rule(tau, gap, strike):
    cushion = abs(gap) / strike * 1e4; h = min(120, max(1, math.ceil(tau - 1e-9)))
    R = cushion * 60.0 / h if h <= 59 else cushion
    return cushion, h, R, RSTAR[h]
def utc(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
def pt(ms): return (datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc) - datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M PST')
# ---------- per window ----------
table = []; excluded = []
for tk in sorted(set(rows_by) | tape_tk):
    rec = {'ticker': tk, 'rows_source': rows_src.get(tk), 'in_tape': tk in tape_tk, 'result_source': mk_src.get(tk)}
    rs = rows_by.get(tk)
    if not rs:
        excluded.append({'ticker': tk, 'reason': 'no prediction rows (geometry not recorded; tape rows only)', 'in_tape': True, 'result': (mk.get(tk) or {}).get('result')}); continue
    r120 = [r for r in rs if 0 < r['tau'] <= 120 and r.get('strike')]
    closeMs = int(round(sorted(r['ts'] + r['tau'] * 1000 for r in rs)[len(rs) // 2] / 1000.0)) * 1000
    rec.update({'close_utc': utc(closeMs), 'close_pt': pt(closeMs), 'closeMs': closeMs, 'stratum': 'pre-I2' if closeMs < I2_FIRST_CLOSE else 'I2', 'rows_in_120s': len(r120), 'seconds_covered': len(set(int(r['tau']) for r in r120))})
    m = mk.get(tk)
    if len(r120) < 115: excluded.append({'ticker': tk, 'reason': 'incomplete rows inside the final 120 s (%d)' % len(r120), 'in_tape': tk in tape_tk, 'result': (m or {}).get('result')}); continue
    if not m: excluded.append({'ticker': tk, 'reason': 'no finalized Kalshi result', 'in_tape': tk in tape_tk, 'result': None}); continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; strike = r120[0]['strike']
    rec.update({'strike': strike, 'official': float(m['official']) if m.get('official') not in (None, '') else None, 'result': m['result'], 'truth': truth,
                'strike_matches_kalshi': (abs(float(m['strike']) - strike) <= 0.011) if m.get('strike') is not None else None, 'official_minus_strike_usd': (float(m['official']) - strike) if m.get('official') not in (None, '') else None})
    exact_tk = (tk in d3_ts) and cfg.get('use_exact', True); rec['candidate_method'] = 'exact replay (build 9 engine on 1-s samples)' if exact_tk else 'reconstruction from recorded engine state (rows: gap, tau, reference; missing-sample requirement not evaluable)'
    rec['books_rows_in_120s'] = sum(1 for r in r120 if (offer_at(tk, r['ts'], 'UP') or {}).get('book'))
    r120.sort(key=lambda r: -r['tau'])
    per = []
    for r in r120:
        st = r.get('state'); pf = r.get('pFlip'); gap = r.get('gap')
        if gap is None or pf is None: per.append({'r': r, 'elig': False, 'eligd': False}); continue
        side = r.get('side') or ('UP' if gap > 0 else 'DOWN')
        cushion, h, R, rstar = rule(r['tau'], gap, strike)
        locked = st in ('LOCKED', 'PROVEN LOCKED'); elig = locked and pf <= 0.002; eligd = locked and pf < 0.0025
        in_min = r['tau'] <= 60; official_ok = (r.get('ref') == 'OFFICIAL') if in_min else True
        floor_ok = R >= rstar - 1e-9
        reasons = ([] if floor_ok else ['floor']) + ([] if official_ok else ['official'])
        recon = locked and floor_ok and official_ok
        ex = d3_row(tk, r['ts']) if exact_tk else None
        if ex is not None:
            ex_locked = ex['state'] in ('LOCKED', 'PROVEN LOCKED'); pr = ex.get('pr11') or {}
            cand_locked = ex_locked; ex_reason = pr.get('reason'); ex_pf = ex.get('pFlip')
            if locked and not ex_locked and ex_reason: reasons = [ex_reason] + [x for x in reasons if x != ex_reason]
        else:
            cand_locked = recon; ex_reason = None; ex_pf = None
        per.append({'r': r, 'side': side, 'elig': elig, 'eligd': eligd, 'locked': locked, 'cushion': cushion, 'h': h, 'R': R, 'rstar': rstar, 'floor_ok': floor_ok, 'official_ok': official_ok,
                    'cand_locked': cand_locked, 'cand_admit': cand_locked and pf <= 0.002, 'cand_admitd': cand_locked and pf < 0.0025, 'reasons': reasons, 'exact': ex is not None, 'ex_reason': ex_reason, 'ex_pf': ex_pf, 'recon': recon})
    def entry(p):
        r = p['r']; o = offer_at(tk, r['ts'], p['side']); e = {'tau': r['tau'], 'ts': r['ts'], 'utc': utc(r['ts']), 'side': p['side'], 'pFlip': r['pFlip'], 'state': r['state'], 'cushion_usd': abs(r['gap']), 'cushion_bps': round(p['cushion'], 2), 'sigma_bps': r.get('sigma'), 'regime': r.get('regime'),
            'n_recorded': r.get('n'), 'h': p['h'], 'R': round(p['R'], 2), 'rstar': p['rstar'], 'ref': r.get('ref'), 'brtiAgeMs': r.get('brtiAgeMs'), 'server_ask': r.get('ask'), 'lost': p['side'] != truth, 'offer': o}
        for L in LAGS:
            oL = offer_at(tk, r['ts'] + L * 1000, p['side']); e['offer_lag%d' % L] = oL
            pL = next((q for q in per if abs(q['r']['ts'] - (r['ts'] + L * 1000)) <= 600), None); e['admit_lag%d' % L] = (pL['cand_admit'] if pL else None)
        return e
    base = next((p for p in per if p['elig']), None); based = next((p for p in per if p['eligd']), None)
    cand = next((p for p in per if p['cand_admit']), None); candd = next((p for p in per if p['cand_admitd']), None)
    rec['baseline'] = entry(base) if base else None; rec['baseline_disp'] = entry(based) if based else None
    rec['candidate'] = entry(cand) if cand else None; rec['candidate_disp'] = entry(candd) if candd else None
    rec['first_locked_any_tau'] = next((r['tau'] for r in r120 if r.get('state') in ('LOCKED', 'PROVEN LOCKED')), None)
    rec['baseline_eligible_seconds'] = sum(1 for p in per if p['elig']); rec['candidate_admitted_seconds'] = sum(1 for p in per if p['cand_admit'])
    rec['candidate_available_admitted_seconds'] = sum(1 for p in per if p['cand_admit'] and available(offer_at(tk, p['r']['ts'], p['side'])))
    rec['baseline_available_eligible_seconds'] = sum(1 for p in per if p['elig'] and available(offer_at(tk, p['r']['ts'], p['side'])))
    rec['withheld_reasons_at_eligible_seconds'] = dict(collections.Counter((p['reasons'][0] if p['reasons'] else ('exact-engine not locked' if not p['cand_locked'] else 'none')) for p in per if p['elig'] and not p['cand_admit']))
    rec['exact_rows_matched'] = sum(1 for p in per if p.get('exact')); rec['recon_vs_exact_disagreements'] = sum(1 for p in per if p.get('exact') and p['locked'] and (p['recon'] != p['cand_locked']))
    adm = [(round(p['r']['tau'], 1), p['side']) for p in per if p['cand_admit']]
    rec['candidate_admitted_sides'] = sorted(set(s for _, s in adm)); rec['candidate_admitted_after_baseline_entry_other_side'] = (sum(1 for t, s in adm if base and t < base['r']['tau'] and s != base['side']) if base else 0)
    rec['delay_s'] = (round(base['r']['tau'] - cand['r']['tau'], 1) if base and cand else None)
    rec['class'] = ('baseline no entry' if not base else 'candidate withheld entirely' if not cand else 'candidate same second' if abs(base['r']['tau'] - cand['r']['tau']) < 0.05 else 'candidate delayed')
    table.append(rec)
json.dump({'config': cfg, 'windows': table, 'excluded': excluded}, open(OUT + '/market_table.json', 'w'))
cols = ['ticker', 'close_utc', 'close_pt', 'stratum', 'rows_source', 'result_source', 'candidate_method', 'result', 'truth', 'strike', 'official', 'official_minus_strike_usd', 'rows_in_120s', 'in_tape', 'books_rows_in_120s', 'class', 'delay_s',
        'b_tau', 'b_side', 'b_pFlip', 'b_cushion_bps', 'b_cushion_usd', 'b_sigma_bps', 'b_regime', 'b_h', 'b_R', 'b_rstar', 'b_ref', 'b_ask', 'b_size', 'b_depth99.9', 'b_book_age_ms', 'b_lost',
        'c_tau', 'c_side', 'c_pFlip', 'c_cushion_bps', 'c_cushion_usd', 'c_sigma_bps', 'c_regime', 'c_h', 'c_R', 'c_rstar', 'c_ref', 'c_ask', 'c_size', 'c_depth99.9', 'c_book_age_ms', 'c_lost', 'c_ask_lag1', 'c_ask_lag3', 'c_ask_lag5', 'c_ask_lag10',
        'withheld_reasons_at_eligible_seconds', 'baseline_eligible_seconds', 'candidate_admitted_seconds', 'candidate_available_admitted_seconds', 'candidate_admitted_sides', 'exact_rows_matched', 'recon_vs_exact_disagreements', 'bd_tau', 'cd_tau']
with open(OUT + '/market_table.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(cols)
    for rec in table:
        b = rec['baseline'] or {}; c = rec['candidate'] or {}; bo = b.get('offer') or {}; co = c.get('offer') or {}
        def g(e, k): return e.get(k) if e else None
        w.writerow([rec['ticker'], rec['close_utc'], rec['close_pt'], rec['stratum'], rec['rows_source'], rec['result_source'], rec['candidate_method'], rec['result'], rec['truth'], rec['strike'], rec['official'], rec['official_minus_strike_usd'], rec['rows_in_120s'], rec['in_tape'], rec['books_rows_in_120s'], rec['class'], rec['delay_s'],
            g(b, 'tau'), g(b, 'side'), g(b, 'pFlip'), g(b, 'cushion_bps'), g(b, 'cushion_usd'), g(b, 'sigma_bps'), g(b, 'regime'), g(b, 'h'), g(b, 'R'), g(b, 'rstar'), g(b, 'ref'), bo.get('ask'), bo.get('size'), bo.get('depth_le_99.9'), bo.get('age'), g(b, 'lost'),
            g(c, 'tau'), g(c, 'side'), g(c, 'pFlip'), g(c, 'cushion_bps'), g(c, 'cushion_usd'), g(c, 'sigma_bps'), g(c, 'regime'), g(c, 'h'), g(c, 'R'), g(c, 'rstar'), g(c, 'ref'), co.get('ask'), co.get('size'), co.get('depth_le_99.9'), co.get('age'), g(c, 'lost'),
            (c.get('offer_lag1') or {}).get('ask'), (c.get('offer_lag3') or {}).get('ask'), (c.get('offer_lag5') or {}).get('ask'), (c.get('offer_lag10') or {}).get('ask'),
            json.dumps(rec['withheld_reasons_at_eligible_seconds']), rec['baseline_eligible_seconds'], rec['candidate_admitted_seconds'], rec['candidate_available_admitted_seconds'], '/'.join(rec['candidate_admitted_sides']), rec['exact_rows_matched'], rec['recon_vs_exact_disagreements'], g(rec['baseline_disp'], 'tau'), g(rec['candidate_disp'], 'tau')])
with open(OUT + '/exclusions.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['ticker', 'reason', 'in_tape', 'result']); w.writeheader(); [w.writerow(e) for e in excluded]
print('windows in table', len(table), 'excluded', len(excluded), collections.Counter(e['reason'].split(' (')[0] for e in excluded))
print('strata', collections.Counter(r['stratum'] for r in table), 'methods', collections.Counter(r['candidate_method'][:12] for r in table), 'classes', collections.Counter(r['class'] for r in table))
