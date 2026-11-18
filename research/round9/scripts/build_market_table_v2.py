"""Market-level comparison table, version 2 (round 9). Changes from version 1: (a) the exposure is computed in the exposure table's
units (bps of the current index, the server's recorded idx), as build 10 does; (b) in the capture windows the candidate's per-second
decision is the build-10 engine run CHRONOLOGICALLY with its own lock memory (chrono dump), so entries may fall on the opposite side
of a withheld baseline lock; (c) in reconstruction windows the candidate's opposite-side behaviour after a withheld lock is
approximated from the served REVERSAL WARNING rows (fresh classification of the leader; hysteresis not reproduced) and labelled.
usage: python3 -I build_market_table_v2.py <config.json> <out dir>"""
import sys, json, glob, os, math, bisect, collections, csv, datetime
cfg = json.load(open(sys.argv[1])); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
RST = json.load(open(cfg['rstar']))['rstar']; RSTAR = {int(k): v for k, v in RST.items()}
I2_FIRST_CLOSE = cfg['i2_first_close_ms']; LAGS = cfg['lags']; BOOK_MAX_AGE = cfg['book_max_age_ms']; PRICES = cfg['prices']
LOCK_MAX_FLIP = cfg.get('lock_max_flip', 0.005); DENOM = cfg.get('denominator', 'index')
rows_by = {}; rows_src = {}
for src in cfg['rows_dirs']:
    for p in sorted(glob.glob(src['dir'] + '/*.ndjson')):
        tk = os.path.basename(p)[:-7]
        if tk in rows_by: continue
        rs = [json.loads(x) for x in open(p) if x.strip()]; rs.sort(key=lambda r: r['ts']); rows_by[tk] = rs; rows_src[tk] = src['label']
mk = {}; mk_src = {}
for src in cfg['markets_dirs']:
    for p in glob.glob(src['dir'] + '/*.json'):
        tk = os.path.basename(p)[:-5]; m = json.load(open(p))
        if tk not in mk and m.get('result') in ('yes', 'no'): mk[tk] = m; mk_src[tk] = src['label']
books = collections.defaultdict(list); tape_tk = set()
with open(cfg['tape']) as f:
    for line in f:
        try: r = json.loads(line)
        except Exception: continue
        if r.get('k') != 'd' or not r.get('kal'): continue
        tk = r['kal']['ticker']; tape_tk.add(tk)
        if r.get('ob'): books[tk].append((r.get('obTs') or r['ts'], r['ob']))
for tk in books: books[tk].sort()
BT = {tk: [b[0] for b in B] for tk, B in books.items()}
def levels(ob, side):
    other = ob.get('no') if side == 'UP' else ob.get('yes'); lv = [(round(100 - p, 2), s) for p, s in (other or []) if s and s > 0]; lv.sort(key=lambda x: x[0]); return lv
def offer_at(tk, ts, side, max_age=BOOK_MAX_AGE):
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right(BT[tk], ts) - 1
    if i < 0 or ts - B[i][0] > max_age: return {'book': False, 'ask': None, 'size': 0, 'age': None if i < 0 else ts - B[i][0]}
    lv = levels(B[i][1], side); o = {'book': True, 'age': ts - B[i][0], 'ask': lv[0][0] if lv else None, 'size': lv[0][1] if lv else 0}
    for p in PRICES: o['depth_le_%s' % p] = sum(s for a, s in lv if a <= p + 1e-9)
    o['ladder'] = [(a, s) for a, s in lv if a <= 99.9 + 1e-9]; return o
def available(o): return bool(o and o.get('book') and o.get('ask') is not None and o['ask'] <= 99.9 + 1e-9 and o['size'] >= 10)
# chronological own-memory candidate dump (capture windows)
chrono = {}; chrono_ts = collections.defaultdict(list)
for p in cfg['chrono_candidate']:
    for line in open(p):
        r = json.loads(line); chrono[(r['ticker'], r['ts'])] = r; chrono_ts[r['ticker']].append(r['ts'])
for tk in chrono_ts: chrono_ts[tk].sort()
def chrono_row(tk, ts, tol=600):
    L = chrono_ts.get(tk)
    if not L: return None
    i = bisect.bisect_left(L, ts); best = None
    for j in (i - 1, i):
        if 0 <= j < len(L) and abs(L[j] - ts) <= tol and (best is None or abs(L[j] - ts) < abs(best - ts)): best = L[j]
    return chrono.get((tk, best)) if best is not None else None
def rule(tau, gap, strike, idx):
    px = idx if (DENOM == 'index' and idx and idx > 0) else strike
    cushion = abs(gap) / px * 1e4; h = min(120, max(1, math.ceil(tau - 1e-9)))
    R = cushion * 60.0 / h if h <= 59 else cushion
    return cushion, h, R, RSTAR[h]
def utc(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
def pt(ms): return (datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc) - datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M PST')
table = []; excluded = []; recon_check = collections.Counter(); disagreements = []
for tk in sorted(set(rows_by) | tape_tk):
    rec = {'ticker': tk, 'rows_source': rows_src.get(tk), 'in_tape': tk in tape_tk, 'result_source': mk_src.get(tk), 'denominator': DENOM}
    rs = rows_by.get(tk)
    if not rs: excluded.append({'ticker': tk, 'reason': 'no prediction rows (geometry not recorded; tape rows only)', 'in_tape': True, 'result': (mk.get(tk) or {}).get('result')}); continue
    r120 = [r for r in rs if 0 < r['tau'] <= 120 and r.get('strike')]
    closeMs = int(round(sorted(r['ts'] + r['tau'] * 1000 for r in rs)[len(rs) // 2] / 1000.0)) * 1000
    rec.update({'close_utc': utc(closeMs), 'close_pt': pt(closeMs), 'closeMs': closeMs, 'stratum': 'pre-I2' if closeMs < I2_FIRST_CLOSE else 'I2', 'rows_in_120s': len(r120)})
    m = mk.get(tk)
    if len(r120) < 115: excluded.append({'ticker': tk, 'reason': 'incomplete rows inside the final 120 s (%d)' % len(r120), 'in_tape': tk in tape_tk, 'result': (m or {}).get('result')}); continue
    if not m: excluded.append({'ticker': tk, 'reason': 'no finalized Kalshi result', 'in_tape': tk in tape_tk, 'result': None}); continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; strike = r120[0]['strike']
    rec.update({'strike': strike, 'official': float(m['official']) if m.get('official') not in (None, '') else None, 'result': m['result'], 'truth': truth})
    exact_tk = tk in chrono_ts
    rec['candidate_method'] = 'exact chronological replay (build 10 engine, own lock memory, 1-s samples)' if exact_tk else 'reconstruction from recorded engine state (index-unit floor, official state; opposite side after a withheld lock approximated from REVERSAL WARNING rows)'
    rec['books_rows_in_120s'] = sum(1 for r in r120 if (offer_at(tk, r['ts'], 'UP') or {}).get('book'))
    r120.sort(key=lambda r: -r['tau'])
    per = []; cand_locked_side = None
    for r in r120:
        st = r.get('state'); pf = r.get('pFlip'); gap = r.get('gap')
        if gap is None or pf is None: per.append({'r': r, 'elig': False, 'eligd': False, 'cand_admit': False, 'cand_admitd': False, 'cand_locked': False}); continue
        served_side = r.get('side') or ('UP' if gap > 0 else 'DOWN'); leader = 'UP' if gap > 0 else 'DOWN'
        cushion, h, R, rstar = rule(r['tau'], gap, strike, r.get('idx'))
        locked = st in ('LOCKED', 'PROVEN LOCKED'); elig = locked and pf <= 0.002; eligd = locked and pf < 0.0025
        in_min = r['tau'] <= 60; official_ok = (r.get('ref') == 'OFFICIAL') if in_min else True; floor_ok = R >= rstar - 1e-9
        reasons = ([] if floor_ok else ['floor']) + ([] if official_ok else ['official'])
        p = {'r': r, 'side': served_side, 'elig': elig, 'eligd': eligd, 'locked': locked, 'cushion': cushion, 'h': h, 'R': R, 'rstar': rstar, 'floor_ok': floor_ok, 'official_ok': official_ok, 'reasons': reasons, 'kind': None, 'cand_side': None, 'cand_pf': None, 'cand_locked': False}
        # reconstruction of the candidate at this second
        if locked: rc_locked = floor_ok and official_ok; rc_side = served_side; rc_pf = pf; kind = 'same side'
        elif st == 'REVERSAL WARNING' and leader != served_side and (cand_locked_side is None or cand_locked_side == leader):
            rc_pf = r.get('pWin'); rc_side = leader
            rc_locked = rc_pf is not None and rc_pf <= LOCK_MAX_FLIP and (r.get('gatesSoft') or 0) == 0 and (r.get('gatesHard') or 0) == 0 and floor_ok and official_ok; kind = 'opposite side after a withheld lock (reconstruction)'
        else: rc_locked = False; rc_side = None; rc_pf = None; kind = None
        p.update({'recon_locked': rc_locked, 'recon_side': rc_side, 'recon_pf': rc_pf})
        if exact_tk:
            ex = chrono_row(tk, r['ts'])
            if ex is not None:
                ex_locked = ex['state'] in ('LOCKED', 'PROVEN LOCKED'); p.update({'exact': True, 'cand_locked': ex_locked, 'cand_side': ex['side'] if ex_locked else None, 'cand_pf': ex['pFlip'], 'cand_action': ex.get('action'), 'ex_state': ex['state'], 'ex_reason': (ex.get('pr11') or {}).get('reason')})
                if ex_locked and ex['side'] != served_side: kind = 'opposite side (exact chronological replay)'
                elif ex_locked: kind = 'same side'
                recon_check['rows'] += 1
                if rc_locked != ex_locked or (ex_locked and rc_side != ex['side']):
                    recon_check['disagree'] += 1; recon_check['disagree_' + ('recon_locked' if rc_locked else 'engine_locked')] += 1
                    disagreements.append({'ticker': tk, 'tau': r['tau'], 'served': st, 'served_side': served_side, 'recon_locked': rc_locked, 'recon_side': rc_side, 'engine': ex['state'], 'engine_side': ex['side'], 'engine_reason': p['ex_reason'], 'dt_ms': ex['ts'] - r['ts']})
                if locked and not ex_locked and p['ex_reason']: reasons = [p['ex_reason']] + [x for x in reasons if x != p['ex_reason']]; p['reasons'] = reasons
            else: p.update({'exact': False, 'cand_locked': rc_locked, 'cand_side': rc_side, 'cand_pf': rc_pf})
        else: p.update({'exact': False, 'cand_locked': rc_locked, 'cand_side': rc_side, 'cand_pf': rc_pf})
        p['kind'] = kind if p['cand_locked'] else None
        p['cand_admit'] = bool(p['cand_locked'] and p['cand_pf'] is not None and p['cand_pf'] <= 0.002); p['cand_admitd'] = bool(p['cand_locked'] and p['cand_pf'] is not None and p['cand_pf'] < 0.0025)
        if p['cand_locked'] and cand_locked_side is None: cand_locked_side = p['cand_side']
        per.append(p)
    def entry(p, which):
        r = p['r']; side = p['cand_side'] if which == 'cand' else p['side']; pfv = p['cand_pf'] if which == 'cand' else r['pFlip']
        o = offer_at(tk, r['ts'], side); e = {'tau': r['tau'], 'ts': r['ts'], 'utc': utc(r['ts']), 'side': side, 'pFlip': pfv, 'served_state': r['state'], 'kind': p.get('kind') if which == 'cand' else 'served', 'action': p.get('cand_action') if which == 'cand' else r.get('action'),
            'cushion_usd': abs(r['gap']), 'cushion_bps': round(p['cushion'], 2), 'sigma_bps': r.get('sigma'), 'regime': r.get('regime'), 'n_recorded': r.get('n'), 'h': p['h'], 'R': round(p['R'], 2), 'rstar': p['rstar'], 'ref': r.get('ref'), 'brtiAgeMs': r.get('brtiAgeMs'), 'lost': side != truth, 'offer': o}
        for L in LAGS:
            oL = offer_at(tk, r['ts'] + L * 1000, side); e['offer_lag%d' % L] = oL
            pL = next((q for q in per if abs(q['r']['ts'] - (r['ts'] + L * 1000)) <= 600), None)
            e['admit_lag%d' % L] = (bool(pL['cand_admit'] and pL['cand_side'] == side) if (pL and which == 'cand') else (bool(pL['elig']) if pL else None))
        return e
    base = next((p for p in per if p['elig']), None); based = next((p for p in per if p['eligd']), None)
    cand = next((p for p in per if p['cand_admit']), None); candd = next((p for p in per if p['cand_admitd']), None)
    rec['baseline'] = entry(base, 'base') if base else None; rec['baseline_disp'] = entry(based, 'base') if based else None
    rec['candidate'] = entry(cand, 'cand') if cand else None; rec['candidate_disp'] = entry(candd, 'cand') if candd else None
    rec['baseline_eligible_seconds'] = sum(1 for p in per if p['elig']); rec['candidate_admitted_seconds'] = sum(1 for p in per if p['cand_admit'])
    rec['candidate_available_admitted_seconds'] = sum(1 for p in per if p['cand_admit'] and available(offer_at(tk, p['r']['ts'], p['cand_side'])))
    rec['baseline_available_eligible_seconds'] = sum(1 for p in per if p['elig'] and available(offer_at(tk, p['r']['ts'], p['side'])))
    rec['withheld_reasons_at_eligible_seconds'] = dict(collections.Counter((p['reasons'][0] if p['reasons'] else 'engine not locked at its own tick') for p in per if p['elig'] and not (p['cand_admit'] and p['cand_side'] == p['side'])))
    opp = [p for p in per if p['cand_locked'] and base and p['r']['tau'] < base['r']['tau'] and p['cand_side'] != base['side']]
    rec['opposite_side_locked_seconds'] = len(opp); rec['opposite_side_first'] = ({'tau': opp[0]['r']['tau'], 'side': opp[0]['cand_side'], 'kind': opp[0]['kind'], 'action': opp[0].get('cand_action'), 'lost': opp[0]['cand_side'] != truth, 'offer_available': any(available(offer_at(tk, p['r']['ts'], p['cand_side'])) for p in opp)} if opp else None)
    rec['candidate_entry_kind'] = cand['kind'] if cand else None
    rec['exact_rows_matched'] = sum(1 for p in per if p.get('exact')); rec['served_reversal_warning_seconds'] = sum(1 for p in per if p['r'].get('state') == 'REVERSAL WARNING')
    rec['delay_s'] = (round(base['r']['tau'] - cand['r']['tau'], 1) if base and cand else None)
    rec['class'] = ('baseline no entry' if not base else 'candidate withheld entirely' if not cand else 'candidate opposite side' if cand['cand_side'] != base['side'] else 'candidate same second' if abs(base['r']['tau'] - cand['r']['tau']) < 0.05 else 'candidate delayed') if (base or cand) else 'no entry under either rule'
    if cand and not base: rec['class'] = 'candidate entry without a baseline entry'
    table.append(rec)
json.dump({'config': cfg, 'windows': table, 'excluded': excluded, 'recon_vs_exact_per_second': dict(recon_check), 'recon_vs_exact_disagreements': disagreements}, open(OUT + '/market_table.json', 'w'))
cols = ['ticker', 'close_utc', 'close_pt', 'stratum', 'candidate_method', 'denominator', 'result', 'truth', 'strike', 'official', 'rows_in_120s', 'in_tape', 'books_rows_in_120s', 'class', 'delay_s', 'candidate_entry_kind',
        'b_tau', 'b_side', 'b_pFlip', 'b_cushion_bps', 'b_h', 'b_R', 'b_rstar', 'b_ref', 'b_ask', 'b_size', 'b_depth99.9', 'b_lost', 'c_tau', 'c_side', 'c_pFlip', 'c_cushion_bps', 'c_h', 'c_R', 'c_rstar', 'c_action', 'c_ask', 'c_size', 'c_depth99.9', 'c_lost', 'c_ask_lag1', 'c_ask_lag3', 'c_ask_lag5',
        'opposite_side_locked_seconds', 'opposite_side_first', 'served_reversal_warning_seconds', 'withheld_reasons_at_eligible_seconds', 'baseline_eligible_seconds', 'candidate_admitted_seconds', 'candidate_available_admitted_seconds', 'exact_rows_matched']
with open(OUT + '/market_table.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(cols)
    for rec in table:
        b = rec['baseline'] or {}; c = rec['candidate'] or {}; bo = b.get('offer') or {}; co = c.get('offer') or {}; g = lambda e, k: e.get(k) if e else None
        w.writerow([rec['ticker'], rec['close_utc'], rec['close_pt'], rec['stratum'], rec['candidate_method'][:30], rec['denominator'], rec['result'], rec['truth'], rec['strike'], rec['official'], rec['rows_in_120s'], rec['in_tape'], rec['books_rows_in_120s'], rec['class'], rec['delay_s'], rec['candidate_entry_kind'],
            g(b, 'tau'), g(b, 'side'), g(b, 'pFlip'), g(b, 'cushion_bps'), g(b, 'h'), g(b, 'R'), g(b, 'rstar'), g(b, 'ref'), bo.get('ask'), bo.get('size'), bo.get('depth_le_99.9'), g(b, 'lost'), g(c, 'tau'), g(c, 'side'), g(c, 'pFlip'), g(c, 'cushion_bps'), g(c, 'h'), g(c, 'R'), g(c, 'rstar'), g(c, 'action'), co.get('ask'), co.get('size'), co.get('depth_le_99.9'), g(c, 'lost'),
            (c.get('offer_lag1') or {}).get('ask'), (c.get('offer_lag3') or {}).get('ask'), (c.get('offer_lag5') or {}).get('ask'), rec['opposite_side_locked_seconds'], json.dumps(rec['opposite_side_first']), rec['served_reversal_warning_seconds'], json.dumps(rec['withheld_reasons_at_eligible_seconds']), rec['baseline_eligible_seconds'], rec['candidate_admitted_seconds'], rec['candidate_available_admitted_seconds'], rec['exact_rows_matched']])
with open(OUT + '/exclusions.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['ticker', 'reason', 'in_tape', 'result']); w.writeheader(); [w.writerow(e) for e in excluded]
print('windows', len(table), 'excluded', len(excluded), 'classes', dict(collections.Counter(r['class'] for r in table)), 'entry kinds', dict(collections.Counter(r['candidate_entry_kind'] for r in table if r['candidate'])), 'recon vs exact per second', dict(recon_check))
